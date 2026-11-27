import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import sesame_ear as ear  # noqa: E402

LOUD = (2000).to_bytes(2, "little", signed=True)
FRAME = 1600 * 2  # 100 ms at 16 kHz


class Proc:
    def __init__(self, pcm):
        self.stdout = io.BytesIO(pcm)

    def terminate(self):
        pass

    def wait(self):
        pass


def args(**kw):
    base = dict(mic=True, sdr=None, file=None, mic_device="alsa:plughw:CARD=Device,DEV=0", silence_rms=300.0,
                min_s=0.4, whisper_cmd="whisper-cli", whisper_model="m.bin", language="ja", dry=False,
                mind="http://mind:8765")
    return argparse.Namespace(**{**base, **kw})


def test_speech_is_transcribed_and_posted_short_clicks_and_tags_are_not(monkeypatch):
    speech = LOUD * (FRAME // 2) * 10 + bytes(FRAME * 8)   # 1 s talk, 0.8 s quiet
    click = LOUD * (FRAME // 2) * 1 + bytes(FRAME * 8)     # 0.1 s talk -> too short
    music = LOUD * (FRAME // 2) * 6 + bytes(FRAME * 8)
    heard = iter(["こんにちは", "[音楽]"])
    monkeypatch.setattr(ear, "transcribe", lambda pcm, *a: next(heard))
    posted, cmds = [], []

    def popen(cmd, stdout):
        cmds.append(cmd)
        return Proc(speech + click + music)

    ear.listen(args(), post=lambda mind, text: posted.append((mind, text)), popen=popen, once=True)
    assert posted == [("http://mind:8765", "こんにちは")]
    assert cmds[0][0] == "ffmpeg" and "plughw:CARD=Device,DEV=0" in cmds[0][4]  # alsa: on Linux


def test_dry_run_posts_nothing_and_unit_keeps_arguments(monkeypatch):
    monkeypatch.setattr(ear, "transcribe", lambda pcm, *a: "やあ")
    posted = []
    ear.listen(args(dry=True), post=lambda *a: posted.append(a),
               popen=lambda cmd, stdout: Proc(LOUD * (FRAME // 2) * 10 + bytes(FRAME * 8)), once=True)
    assert posted == []
    text = ear.unit(["--mind", "http://m:8765", "--unit"])
    exec_line = next(line for line in text.splitlines() if line.startswith("ExecStart="))
    assert exec_line.endswith("sesame_ear.py --mind http://m:8765") and "Restart=always" in text
