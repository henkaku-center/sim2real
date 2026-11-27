#!/usr/bin/env python3
"""A microphone somewhere else (e.g. the Raspberry Pi) as an ear for the sesame mind.

Listens on a local microphone, cuts speech by loudness, transcribes it with
whisper.cpp and posts the text to the mind's `/say`, the same door the chat box
uses. The mind and the robot stay where they are; only words cross the network
(Tailscale), so the ear works from any Wi-Fi.

    python3 tools/sesame_ear.py --mind http://100.112.210.74:8765 \\
        --mic-device alsa:plughw:CARD=Device,DEV=0 --whisper-model ~/models/whisper/ggml-small-q5_1.bin
    python3 tools/sesame_ear.py --dry ...     # print what it heard, post nothing
    python3 tools/sesame_ear.py --unit ...    # print a systemd unit with these arguments
"""
from __future__ import annotations

import argparse
import getpass
import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radio_paranoia import rms, source_command, transcribe  # noqa: E402
from sesame_mind import utterances  # noqa: E402


def say(mind, text, timeout=10.0):
    req = urllib.request.Request(mind.rstrip("/") + "/say", text.encode(), method="POST",
                                 headers={"Content-Type": "text/plain; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def voiced_s(pcm, silence_rms, frame_ms=100):
    """Seconds above the speech threshold; the trailing quiet the cutter keeps does not count."""
    n = int(16000 * frame_ms / 1000) * 2
    return sum(rms(pcm[i:i + n]) >= silence_rms for i in range(0, len(pcm), n)) * frame_ms / 1000


def listen(args, post=say, popen=subprocess.Popen, once=False):
    """Run the microphone; restart it if it dies (USB unplugged, ALSA busy)."""
    while True:
        proc = popen(source_command(args), stdout=subprocess.PIPE)
        try:
            for kind, pcm in utterances(proc.stdout, silence_rms=args.silence_rms):
                if kind != "speech" or voiced_s(pcm, args.silence_rms) < args.min_s:
                    continue
                text = transcribe(pcm, args.whisper_cmd, args.whisper_model, args.language).strip()
                if not text or text.startswith(("[", "(")):  # whisper's [音楽] / (拍手) for non-speech
                    continue
                print(f"👂 {text}  (rms {rms(pcm):.0f})", flush=True)
                if not args.dry:
                    try:
                        post(args.mind, text)
                    except OSError as e:
                        print(f"  (mind) not reached: {e}", file=sys.stderr, flush=True)
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
    p.add_argument("--mind", default="http://100.112.210.74:8765",
                   help="the mind's admin URL (the Mac's tailnet IP: the Pi runs without MagicDNS)")
    p.add_argument("--mic-device", default="alsa:plughw:CARD=Device,DEV=0",
                   help="ffmpeg input: alsa:DEVICE or pulse:NAME on Linux, ':0' on macOS")
    p.add_argument("--whisper-cmd", default="whisper-cli")
    p.add_argument("--whisper-model", default=str(Path.home() / "models/whisper/ggml-small-q5_1.bin"))
    p.add_argument("--language", default="ja")
    p.add_argument("--silence-rms", type=float, default=450.0,
                   help="speech threshold (int16 RMS; the Pi's USB mic idles near 200)")
    p.add_argument("--min-s", type=float, default=0.4, help="ignore sounds shorter than this")
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
    print(f"ear: {a.mic_device} -> {a.mind}/say" + (" (dry)" if a.dry else ""), flush=True)
    listen(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
