# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "pyserial", "faster-whisper"]
# ///
"""Mic test: read the AE-MICAMP stream from the SuperMini over USB, show a
live level bar, and print each spoken phrase as text (Whisper, offline).
With the robot firmware (build 19+) a recognised command (sit, stand, hello,
wave, dance, walk, rest, stop; also "can you sit?", "sick" -> sit) is sent as
`voice WORD`: the face shows the word, and on battery the legs move.

    uv run body/mic-test/listen.py --wifi       # on battery: laptop joined to Sesame-S3-XXXX

    uv run body/mic-test/listen.py              # level bar + words
    uv run body/mic-test/listen.py --levels     # level bar only
    uv run body/mic-test/listen.py --save x.wav # also save everything heard
"""
import argparse, glob, re, socket, sys, threading, time, urllib.request, wave
import numpy as np, serial
from scipy.signal import butter, sosfilt, sosfilt_zi

RATE, N = 16000, 256
# Commands the robot knows, plus words Whisper often hears instead of them.
COMMANDS = {
    "sit": ["sit", "sits", "sitting", "sick", "set", "seat", "sid", "sip", "zit", "shit", "sat"],
    "stand": ["stand", "stands", "standing", "stan", "stamp", "stun", "stunned", "stent", "stanley"],
    "hello": ["hello", "hi", "hey", "hallo", "hullo"],
    "wave": ["wave", "waves", "waving", "wait", "weave"],
    "dance": ["dance", "dancing", "dense", "dan", "dancer", "dancers"],
    "walk": ["walk", "walking", "work", "wok", "woke", "walks"],
    "stop": ["stop", "stops", "top", "stuff"],
    "rest": ["rest", "relax", "sleep", "lie"],
}
PROMPT = "Commands: sit, sit down, stand, stand up, hello, wave, dance, walk, stop, rest. Can you sit? Can you stand?"

def command_for(text):
    """First command in the text, also from sound-alikes ('sick' -> sit) and questions ('can you stand?')."""
    for w in re.sub(r"[^a-z ]", " ", text.lower()).split():
        for cmd, alikes in COMMANDS.items():
            if w in alikes: return cmd
    return None

def frames(port, sock=None):
    buf = b""; renewed = 0.0
    while True:
        if sock:                                # Wi-Fi: each UDP packet is one frame
            try: buf += sock.recv(2048)
            except socket.timeout: continue
        else:
            if time.time() - renewed > 1:      # robot firmware streams only while leased
                port.write(b"mic on\n"); renewed = time.time()
            buf += port.read(4096)
        while True:
            i = buf.find(b"\xa5\x5a")
            if i < 0 or len(buf) < i + 2 + 2 * N: buf = buf[max(0, len(buf) - 1):] if i < 0 else buf[i:]; break
            yield np.frombuffer(buf[i + 2:i + 2 + 2 * N], "<i2"); buf = buf[i + 2 + 2 * N:]

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=None); ap.add_argument("--levels", action="store_true")
    ap.add_argument("--model", default="base.en"); ap.add_argument("--save")
    ap.add_argument("--wifi", action="store_true", help="robot on battery: join its Wi-Fi first")
    ap.add_argument("--robot", default="192.168.4.1")
    a = ap.parse_args()
    sock = port = None
    if a.wifi:                                  # battery: robot AP at 192.168.4.1, audio by UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.bind(("0.0.0.0", 5005)); sock.settimeout(0.5)
        def lease():
            while True:
                try: urllib.request.urlopen(f"http://{a.robot}/mic", timeout=1).read()
                except Exception as e: print(f"\n[wifi] robot not reachable ({e}); is the laptop on its Wi-Fi?")
                time.sleep(1)
        threading.Thread(target=lease, daemon=True).start()
    else:
        port = serial.Serial(a.port or sorted(glob.glob("/dev/cu.usbmodem*"))[0], 921600, timeout=0.1)
    def send(cmd):
        if port: port.write(f"voice {cmd}\n".encode()); return "sent over USB (face only)"
        try: return urllib.request.urlopen(f"http://{a.robot}/voice?w={cmd}", timeout=2).read().decode()
        except urllib.error.HTTPError as e: return e.read().decode()
        except Exception as e: return f"send failed: {e}"
    model = None
    if not a.levels:
        from faster_whisper import WhisperModel
        model = WhisperModel(a.model, device="cpu", compute_type="int8")
    out = wave.open(a.save, "wb") if a.save else None
    if out: out.setnchannels(1); out.setsampwidth(2); out.setframerate(RATE)
    print("Speak now (Ctrl+C to stop)")
    # Speech band only: the mic picks up strong rumble below 100 Hz and ADC hiss.
    sos = butter(4, [150, 4000], btype="band", fs=RATE, output="sos"); zi = sosfilt_zi(sos) * 0
    # Noise floor = 20th percentile of the last 2 s (the robot's own servo and Wi-Fi
    # noise makes the level jump around, so an average never settles).
    recent, speech, quiet, phrase, shown, started, peak = [], False, 0, [], 0.0, 0.0, 0.0
    for raw in frames(port, sock):
        if out: out.writeframes(raw.tobytes())
        f, zi = sosfilt(sos, raw.astype(np.float32), zi=zi)
        rms = float(np.sqrt(np.mean(f ** 2)))
        if time.time() - shown > 0.1:
            shown = time.time()
            sys.stdout.write(f"\rlevel {rms:6.0f} {'#' * min(50, int(rms / 150)):50s} {'SPEECH' if speech else '      '}"); sys.stdout.flush()
        if model is None: continue
        recent = (recent + [rms])[-125:]
        noise = max(150.0, float(np.percentile(recent, 20)))
        if not speech:
            if rms > noise * 3: speech, quiet, phrase, started, peak = True, 0, [f], time.time(), rms
            continue
        phrase.append(f); peak = max(peak, rms)
        # Phrase ends after 0.35 s back near the floor (well below this phrase's peak).
        quiet = quiet + 1 if rms < max(noise * 1.6, peak * 0.2) else 0
        if quiet >= 22 or len(phrase) >= 190:            # 0.35 s quiet or 3 s max
            speech = False
            loud = sum(1 for p in phrase if np.sqrt(np.mean(p ** 2)) > noise * 3)
            if loud < 6: continue                         # a click or bump, not speech (< 0.1 s loud)
            audio = np.concatenate(phrase) / 32768
            audio /= max(0.05, float(np.abs(audio).max()))
            t = time.time()
            # temperature=0 only: Whisper's retry-at-higher-temperature on unclear audio
            # took 8-18 s on robot noise; a short command never needs more tokens.
            segs, _ = model.transcribe(audio.astype(np.float32), language="en", beam_size=3, vad_filter=False,
                                       temperature=0.0, condition_on_previous_text=False, without_timestamps=True,
                                       max_new_tokens=20, initial_prompt=PROMPT,
                                       hotwords="sit stand hello wave dance walk stop rest")
            text = " ".join(s.text for s in segs if s.no_speech_prob < 0.6).strip()
            print(f"\n[heard] {text or '(nothing clear)'}   ({len(audio) / RATE:.1f} s audio, recognised in {time.time() - t:.1f} s)")
            cmd = command_for(text)
            if cmd: print(f"[command] {cmd} -> robot: {send(cmd)}")
            if port: port.reset_input_buffer()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print()
