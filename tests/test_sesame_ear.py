import argparse
import pytest
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


def key(code, value):
    return ear.EVENT.pack(0, 0, ear.EV_KEY, code, value)


def test_pedal_is_down_while_any_key_is_held_and_ignores_repeat_and_other_events():
    pedal = ear.Pedal()
    pedal.feed(ear.EVENT.pack(0, 0, 4, 4, 7) + key(48, 1), "kbd")  # MSC_SCAN then b down
    assert pedal.down.is_set()
    pedal.feed(key(272, 1), "mouse")
    pedal.feed(key(48, 2) + key(48, 0), "kbd")                      # repeat, then up
    assert pedal.down.is_set()                                       # mouse button still held
    pedal.feed(key(272, 0), "mouse")
    assert not pedal.down.is_set()


def test_push_to_talk_keeps_only_the_pressed_stretch_with_pre_and_tail(monkeypatch):
    quiet, loud = bytes(FRAME), LOUD * (FRAME // 2)
    # idle (noise at 4) | pressed 0.8 s | released | pressed 0.5 s | released
    frames = [quiet] * 4 + [loud] + [loud] * 8 + [quiet] * 7 + [loud] * 5 + [quiet] * 3
    down = [False] * 5 + [True] * 8 + [False] * 7 + [True] * 5 + [False] * 3
    tick = iter(down)
    got = []
    monkeypatch.setattr(ear, "transcribe", lambda pcm, *a: got.append(len(pcm) // FRAME) or "歩いて")
    posted, faces = [], []
    ear.push_to_talk(args(), io.BytesIO(b"".join(frames)), lambda: next(tick),
                     post=lambda mind, text: posted.append(text), show=faces.append)
    assert faces == ["surprised", "thinking"] * 2
    assert got == [3 + 8 + 2, 3 + 5 + 2]   # pre + held + tail, for both presses
    assert posted == ["歩いて", "歩いて"]


def test_push_to_talk_drops_a_silent_press(monkeypatch):
    monkeypatch.setattr(ear, "transcribe", lambda *a: pytest.fail("silence must not reach whisper"))
    tick = iter([True] * 5 + [False] * 5)
    ear.push_to_talk(args(), io.BytesIO(bytes(FRAME) * 10), lambda: next(tick), post=lambda *a: None)


def test_hand_over_passes_prompt_drops_outros_and_measures_clipping(monkeypatch, tmp_path):
    calls = []
    said = iter(["ご視聴ありがとうございました", "立って"])
    monkeypatch.setattr(ear, "transcribe", lambda pcm, *a: calls.append(a) or next(said))
    posted = []
    a = args(prompt="立って。", keep=str(tmp_path))
    rail = (32767).to_bytes(2, "little", signed=True) * 100 + bytes(200 * 2)
    assert ear.clipped(rail) == pytest.approx(1 / 3)
    assert ear.hand_over(a, rail, lambda mind, text: posted.append(text)) is None
    assert ear.hand_over(a, rail, lambda mind, text: posted.append(text)) == "立って"
    assert posted == ["立って"] and calls[0][-1][-2:] == ("--prompt", "立って。")
    assert len(list(tmp_path.glob("*.wav"))) >= 1


def test_fast_flags_fit_the_encoder_to_the_clip_and_loops_are_dropped(monkeypatch):
    sec = 16000 * 2
    ac = lambda pcm: int(ear.fast_flags(pcm)[ear.fast_flags(pcm).index("-ac") + 1])
    assert ac(bytes(sec * 2)) == 256 and ac(bytes(sec * 4)) == 296 and ac(bytes(sec * 40)) == 1500
    assert ear.fast_flags(bytes(sec))[:5] == ("-bs", "1", "-bo", "1", "-nf")
    for loop in ("喜んで" * 9, "サウナに入ってください。" * 30):
        monkeypatch.setattr(ear, "transcribe", lambda *a, t=loop: t)
        assert ear.hand_over(args(prompt=""), bytes(sec), lambda *a: pytest.fail("loop posted")) is None
    monkeypatch.setattr(ear, "transcribe", lambda *a: "もっともっと速く")
    assert ear.hand_over(args(prompt=""), bytes(sec), lambda *a: None) == "もっともっと速く"
