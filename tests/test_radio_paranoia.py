"""Radio paranoia agent: madness curve, macro lines and ears, without radio/Claude/robot."""

import argparse
import io
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import radio_paranoia as rp  # noqa: E402
import sesame_remote  # noqa: E402
from sim.manifest import load_manifest  # noqa: E402


def decision(delta, motion="stand", face="idle", text="x"):
    return {"interpretation": text, "mutter": "…", "suspicion_delta": delta, "motion": motion, "face": face}


def test_vocabulary_exists_in_firmware():
    motions = yaml.safe_load((ROOT / "manifest/motions.yaml").read_text())["motions"]
    faces = set(re.findall(r"X\((\w+)\)", (ROOT / "firmware/sesame-s3/vendor/face-bitmaps.h").read_text()))
    assert set(rp.MOTIONS) <= set(motions)
    assert set(rp.FACES) <= faces
    assert rp.SCHEMA["properties"]["motion"]["enum"] == rp.MOTIONS


def test_phase_thresholds():
    assert [rp.phase_of(x).name for x in (0.0, 0.249, 0.25, 0.5, 0.79, 0.8, 1.0)] == [
        "calm", "calm", "suspicious", "convinced", "convinced", "frenzy", "frenzy"]


def test_suspicion_decays_and_clamps_delta():
    mind = rp.Mind(level=0.5)
    step = mind.update(decision(9.0, motion="point", face="angry"))
    assert step.level == pytest.approx(0.5 * rp.DECAY + 0.4)  # delta clamped to 0.4
    mind = rp.Mind(level=0.1)
    assert mind.update(decision(-9.0)).level == 0.0


def test_motion_outside_phase_falls_back_to_phase_default():
    step = rp.Mind().update(decision(0.0, motion="worm", face="freaky"))
    assert (step.phase, step.motion, step.face) == ("calm", "stand", "idle")


def test_frenzy_is_a_fit_then_relapse():
    mind = rp.Mind(level=0.7)
    step = mind.update(decision(0.4, motion="worm", face="freaky"))
    assert step.fit and step.phase == "frenzy" and step.motion == "worm"
    assert (mind.level, mind.fits, mind.just_recovered) == (rp.RELAPSE, 1, True)
    assert "発作" in rp.prompt(mind, "時報")
    mind.update(decision(0.0))
    assert not mind.just_recovered


def test_evidence_board_keeps_newest():
    mind = rp.Mind()
    for i in range(rp.EVIDENCE + 3):
        mind.update(decision(0.0, text=str(i)))
    assert mind.evidence == [str(i) for i in range(3, rp.EVIDENCE + 3)]


def test_tuck_pose_follows_manifest_and_limits():
    manifest = load_manifest()
    cmd = rp.tuck_command(manifest)
    values = [float(v) for v in cmd.split()[1:]]
    assert cmd.split()[0] == "pose" and len(values) == 8
    # q_hip=+90 and q_foot=-90 for the point-symmetric signs R1 R2 L1 L2 R4 R3 L3 L4
    assert values == [180, 0, 0, 180, 180, 0, 180, 0]
    for j, v in zip(manifest.joints, values):
        assert j.limits_deg[0] <= v <= j.limits_deg[1], j.name


def test_fit_appends_blind_recovery():
    body = rp.Body(tuck="pose T", tuck_ms=1234)
    calm = rp.Step("calm", 0.1, "wave", "happy", False, "")
    fit = rp.Step("frenzy", 0.9, "worm", "freaky", True, "")
    assert body.lines(calm) == ["motion wave", "face happy"]
    assert body.lines(fit) == ["motion worm", "face freaky", "pose T", "wait 1234", "motion stand", "face confused"]


def args(**kw):
    base = dict(sdr=None, gain=None, mic=False, mic_device=None, file=None)
    return argparse.Namespace(**{**base, **kw})


def test_sdr_rate_overrides_wbfm_preset():
    cmd = rp.source_command(args(sdr=80.0, gain=30))
    assert cmd[:3] == ["rtl_fm", "-f", "80.0M"]
    assert cmd.index("-r") > cmd.index("-M") and cmd[cmd.index("-r") + 1] == "16000"
    assert cmd[-1] == "-"


def test_mic_and_file_sources_emit_16k_mono_pcm():
    mac = rp.source_command(args(mic=True), platform="darwin")
    linux = rp.source_command(args(mic=True), platform="linux")
    f = rp.source_command(args(file="a.mp3"))
    assert mac[1:5] == ["-f", "avfoundation", "-i", ":0"]
    assert linux[1:5] == ["-f", "pulse", "-i", "default"]
    assert f[:4] == ["ffmpeg", "-re", "-i", "a.mp3"]
    alsa = rp.source_command(args(mic=True, mic_device="alsa:plughw:CARD=Device,DEV=0"), platform="linux")
    assert alsa[1:5] == ["-f", "alsa", "-i", "plughw:CARD=Device,DEV=0"]
    for cmd in (mac, linux, f):
        assert cmd[-9:] == ["-ac", "1", "-ar", "16000", "-f", "s16le", "-loglevel", "error", "-"]


def test_rms_and_ear_keep_newest_chunks():
    loud = (1000).to_bytes(2, "little", signed=True) * 4
    assert rp.rms(loud) == pytest.approx(1000)
    assert rp.rms(b"\x00\x00" * 4) == 0 and rp.rms(b"") == 0
    q = rp.queue.Queue(maxsize=2)
    rp.ear(io.BytesIO(b"aabbccdd"), 2, q)  # never consumed: oldest chunks dropped
    assert [q.get(), q.get()] == [b"dd", None]


class FakeBrain:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.prompts = []

    def think(self, mind, transcript):
        self.prompts.append(rp.prompt(mind, transcript))
        return self.decisions.pop(0)


class FakeRobot:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def command(self, text):
        if self.fail:
            raise OSError("timed out")
        self.sent.append(text)
        return True, "OK"

    def busy(self):
        return False


def test_run_escalates_to_fit_and_logs(capsys):
    brain = FakeBrain([decision(0.3, "turn_left", "thinking"), decision(0.4, "crab", "angry"),
                       None, decision(0.4, "worm", "freaky")])
    robot = FakeRobot()
    body = rp.Body(robot, tuck="pose T", tuck_ms=0)
    log = io.StringIO()
    rp.run(["天気", "北の風", "（無音）", "時報"], brain, rp.Mind(), body, log, clock=lambda: 0)
    assert robot.sent == ["motion turn_left", "face thinking", "motion crab", "face angry",
                          "motion worm", "face freaky", "pose T", "motion stand", "face confused"]
    rows = [json.loads(line) for line in log.getvalue().splitlines()]
    assert [r["phase"] for r in rows] == ["suspicious", "convinced", "frenzy"]
    assert rows[-1]["fit"] and rows[0]["transcript"] == "天気"


def test_lost_link_does_not_stop_listening(capsys):
    brain = FakeBrain([decision(0.0), decision(0.0)])
    rp.run(["a", "b"], brain, rp.Mind(), rp.Body(FakeRobot(fail=True)))
    assert capsys.readouterr().err.count("帽子が効いている") == 2


def test_dry_run_prints_lines(capsys):
    rp.run(["a"], FakeBrain([decision(0.0, "wave", "happy")]), rp.Mind(), rp.Body())
    assert "(dry) motion wave; face happy" in capsys.readouterr().out


def test_remote_run_lines_tolerates_and_waits():
    robot, slept = FakeRobot(), []
    robot.command = lambda t: (robot.sent.append(t), (not t.startswith("bad"), "x"))[1]
    lines = sesame_remote.split_lines("?bad one; wait 250", "motion stand\nbad two", "never")
    assert sesame_remote.run_lines(robot, lines, sleep=slept.append) == 1
    assert robot.sent == ["bad one", "motion stand", "bad two"]
    assert slept == [0.25, 0.25]
