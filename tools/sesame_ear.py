#!/usr/bin/env python3
"""A microphone somewhere else (e.g. the Raspberry Pi) as an ear for the sesame mind.

Listens on a local microphone, cuts speech by loudness, transcribes it with
whisper.cpp and posts the text to the mind's `/say`, the same door the chat box
uses. The mind and the robot stay where they are; only words cross the network
(Tailscale), so the ear works from any Wi-Fi.

With a foot pedal (any USB pedal that shows up as a keyboard or mouse, e.g. the
PCsensor FootSwitch) it is push-to-talk: hold the pedal, speak, let go; only
that stretch is transcribed. Without one it cuts speech by loudness.

    python3 tools/sesame_ear.py --mind http://100.112.210.74:8765 \\
        --mic-device alsa:plughw:CARD=Device,DEV=0 --whisper-model ~/models/whisper/ggml-small-q5_1.bin
    python3 tools/sesame_ear.py --dry ...     # print what it heard, post nothing
    python3 tools/sesame_ear.py --unit ...    # print a systemd unit with these arguments
"""
from __future__ import annotations

import argparse
import collections
import fcntl
import getpass
import glob
import queue
import re
import shlex
import struct
import subprocess
import sys
import threading
import time
import urllib.request
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radio_paranoia import rms, source_command, transcribe  # noqa: E402
from sesame_mind import utterances  # noqa: E402


def post_first(minds, path, body, timeout, opener=urllib.request.urlopen):
    """POST to the first mind in the comma-separated list that answers: a mind on this
    box (connection refused at once when it is not running), else the Mac's."""
    error = OSError("no mind given")
    for mind in filter(None, (m.strip() for m in minds.split(","))):
        req = urllib.request.Request(mind.rstrip("/") + path, body, method="POST",
                                     headers={"Content-Type": "text/plain; charset=utf-8"})
        try:
            with opener(req, timeout=timeout) as r:
                return mind, r.status
        except OSError as e:
            error = e
    raise error


def say(minds, text, timeout=10.0):
    return post_first(minds, "/say", text.encode(), timeout)


def cue(minds, face, timeout=3.0):
    """Ask the mind to show an OLED face now; in the background, failures ignored."""
    def send():
        try:
            post_first(minds, "/cue", face.encode(), timeout)
        except OSError:
            pass

    threading.Thread(target=send, daemon=True).start()


def voiced_s(pcm, silence_rms, frame_ms=100):
    """Seconds above the speech threshold; the trailing quiet the cutter keeps does not count."""
    n = int(16000 * frame_ms / 1000) * 2
    return sum(rms(pcm[i:i + n]) >= silence_rms for i in range(0, len(pcm), n)) * frame_ms / 1000


EVENT = struct.Struct("llHHi")  # struct input_event on 64-bit Linux
EV_KEY = 1
EVIOCGRAB = 0x40044590
FRAME = 3200  # 100 ms of 16 kHz s16le
# whisper.cpp --prompt: sets the register. A word list cost ~0.5 s per clip on a Pi 5
# and doubled short answers (喜んで。喜んで。); this short one costs nothing measurable.
PROMPT = "ロボットへのお願い。"
# whisper's stock hallucinations on noise (YouTube outros)
HALLUCINATIONS = ("ご視聴ありがとう", "チャンネル登録", "最後までご視聴", "おやすみなさい。", "字幕")
LOOP = re.compile(r"(.{1,24}?)\1{2,}")  # 喜んで喜んで喜んで… / a sentence three times over


def fast_flags(pcm):
    """Greedy decoding without fallback, and an encoder context cut to the clip
    (1500 = 30 s; ~50 per second plus margin, 256 at least). On a Pi 5 with the
    small model this takes a 2-4 s clip from ~9 s to ~1.5 s; tighter contexts
    start repeating words."""
    seconds = len(pcm) / (16000 * 2)
    return ("-bs", "1", "-bo", "1", "-nf", "-ac", str(min(1500, max(256, int(seconds * 50) + 96))))


class Pedal:
    """Held while any key or button on the pedal's input devices is down."""

    def __init__(self, paths=(), grab=True):
        self.held, self.lock, self.down = set(), threading.Lock(), threading.Event()
        for path in paths:
            f = open(path, "rb", buffering=0)
            if grab:  # keep the pedal's keystrokes out of the console
                try:
                    fcntl.ioctl(f, EVIOCGRAB, 1)
                except OSError:
                    pass
            threading.Thread(target=self._read, args=(f, path), daemon=True).start()

    def _read(self, f, key):
        while data := f.read(EVENT.size * 16):
            self.feed(data, key)

    def feed(self, data, source=""):
        for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _, _, kind, code, value = EVENT.unpack_from(data, i)
            if kind != EV_KEY or value == 2:  # 2 = autorepeat
                continue
            with self.lock:
                (self.held.add if value else self.held.discard)((source, code))
                self.down.set() if self.held else self.down.clear()


def find_pedal(spec):
    if spec == "off":
        return []
    if spec == "auto":
        return sorted(glob.glob("/dev/input/by-id/*FootSwitch*-event-*"))
    return [spec]


def clipped(pcm, limit=32000):
    """Share of samples at the rails: above ~1 % the mic gain is too high."""
    n = len(pcm) // 2
    return sum(abs(v) >= limit for v in memoryview(pcm[: n * 2]).cast("h")) / n if n else 0.0


def keep_clip(folder, pcm, text, keep=30):
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    stem = time.strftime("%Y%m%d-%H%M%S")
    with wave.open(str(folder / f"{stem}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    (folder / f"{stem}.txt").write_text(text + "\n")
    for old in sorted(folder.glob("*.wav"))[:-keep]:
        old.unlink(missing_ok=True)
        old.with_suffix(".txt").unlink(missing_ok=True)


def hand_over(args, pcm, post):
    """Transcribe one stretch and post it; whisper's [音楽] / (拍手) and its YouTube
    outros on noise mean no speech."""
    t = time.monotonic()
    extra = fast_flags(pcm) + (("--prompt", args.prompt) if getattr(args, "prompt", "") else ())
    text = transcribe(pcm, args.whisper_cmd, args.whisper_model, args.language, extra).strip()
    took, clip = time.monotonic() - t, clipped(pcm)
    if getattr(args, "keep", None):
        keep_clip(args.keep, pcm, text)
    note = f"(rms {rms(pcm):.0f}, clipped {clip:.1%}, whisper {took:.1f} s)"
    if not text or text.startswith(("[", "(")) or any(h in text for h in HALLUCINATIONS) or LOOP.search(text):
        print(f"  (ear) dropped {text!r} {note}", flush=True)
        return None
    print(f"👂 {text}  {note}", flush=True)
    if not args.dry:
        try:
            post(args.mind, text)
        except OSError as e:
            print(f"  (mind) not reached: {e}", file=sys.stderr, flush=True)
    return text


def push_to_talk(args, stream, is_down, post=say, pre=3, tail=2, max_s=30.0, show=None):
    """Keep what the mic heard while the pedal was down, plus `pre` frames before the
    press and `tail` after the release (audio lags the pedal), and hand it over.
    Transcribing runs on another thread so the next press is not lost. `show(face)`
    gives instant feedback on the robot: surprised while held, thinking after."""
    show = show or (lambda face: None)
    jobs = queue.Queue()

    def work():
        while (pcm := jobs.get()) is not None:
            if voiced_s(pcm, args.silence_rms) >= args.min_s:
                hand_over(args, pcm, post)
            else:
                print("  (pedal) nothing loud enough", flush=True)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    before, buf, after = collections.deque(maxlen=pre), None, 0
    while data := stream.read(FRAME):
        if is_down():
            if buf is None:
                print("🦶 listening", flush=True)
                show("surprised")
                buf = bytearray(b"".join(before))
            buf += data
            after = 0
        elif buf is not None:
            if after == 0:
                show("thinking")
            buf += data
            after += 1
        else:
            before.append(data)
        if buf is not None and (after >= tail or len(buf) >= max_s * 16000 * 2):
            jobs.put(bytes(buf))
            buf, after = None, 0
            before.clear()
    jobs.put(None)
    worker.join()


def listen(args, post=say, popen=subprocess.Popen, once=False, pedal=None):
    """Run the microphone; restart it if it dies (USB unplugged, ALSA busy)."""
    while True:
        proc = popen(source_command(args), stdout=subprocess.PIPE)
        try:
            if pedal is not None:
                show = None if args.dry else (lambda face: cue(args.mind, face))
                push_to_talk(args, proc.stdout, pedal.down.is_set, post, show=show)
            else:
                for kind, pcm in utterances(proc.stdout, silence_rms=args.silence_rms):
                    if kind == "speech" and voiced_s(pcm, args.silence_rms) >= args.min_s:
                        hand_over(args, pcm, post)
        finally:
            proc.terminate()
            proc.wait()
        if once:
            return
        time.sleep(2)


def unit(argv):
    """systemd system unit running this file with the same arguments (minus --unit)."""
    root = Path(__file__).resolve().parent.parent
    args = [sys.executable, str(Path(__file__).resolve()), *[a for a in argv if a != "--unit"]]
    cmd = " ".join(shlex.quote(a.replace("%", "%%").replace("$", "$$")) for a in args)
    return f"""[Unit]
Description=Sesame ear (microphone -> sesame mind /say)
Wants=network-online.target
After=network-online.target sound.target tailscaled.service

[Service]
User={getpass.getuser()}
WorkingDirectory={root}
Environment=PYTHONUNBUFFERED=1
ExecStart={cmd}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mind", default="http://127.0.0.1:8765,http://100.112.210.74:8765",
                   help="the mind's admin URL; with a comma list the first that answers is used "
                        "(default: a mind on this box, else the Mac's tailnet IP: the Pi runs without MagicDNS)")
    p.add_argument("--mic-device", default="alsa:plughw:CARD=Device,DEV=0",
                   help="ffmpeg input: alsa:DEVICE or pulse:NAME on Linux, ':0' on macOS")
    p.add_argument("--whisper-cmd", default="whisper-cli")
    p.add_argument("--whisper-model", default=str(Path.home() / "models/whisper/ggml-small-q5_1.bin"))
    p.add_argument("--language", default="ja")
    p.add_argument("--silence-rms", type=float, default=450.0,
                   help="speech threshold (int16 RMS; the Pi's USB mic idles near 200)")
    p.add_argument("--min-s", type=float, default=0.4, help="ignore sounds shorter than this")
    p.add_argument("--prompt", default=PROMPT, help="whisper initial prompt ('' for none)")
    p.add_argument("--keep", default="~/sesame-ear-clips", help="save the last 30 clips + text here ('' for none)")
    p.add_argument("--pedal", default="auto",
                   help="push-to-talk input device: auto (a USB FootSwitch if plugged in), off, or /dev/input/...")
    p.add_argument("--dry", action="store_true", help="print, do not post")
    p.add_argument("--unit", action="store_true", help="print a systemd unit and exit")
    a = p.parse_args(argv)
    if a.unit:
        sys.stdout.write(unit(argv))
        return 0
    a.mic, a.sdr, a.file = True, None, None
    if not Path(a.whisper_model).expanduser().exists():
        raise SystemExit(f"no whisper model at {a.whisper_model}")
    a.whisper_model = str(Path(a.whisper_model).expanduser())
    paths = find_pedal(a.pedal)
    pedal = Pedal(paths) if paths else None
    mode = f"push-to-talk on {', '.join(paths)}" if pedal else "by loudness"
    print(f"ear: {a.mic_device} -> {a.mind}/say, {mode}" + (" (dry)" if a.dry else ""), flush=True)
    listen(a, pedal=pedal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
