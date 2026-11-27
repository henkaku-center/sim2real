"""Sesame mind skeleton: specs, library, memory, reflexes and ears, without Claude/Jev/robot."""

import array
import io
import json
import math
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sesame_mind as sm  # noqa: E402
from sim.manifest import load_manifest  # noqa: E402

M = load_manifest()
OSC = {"kind": "osc", "base": "stand", "hz": 1.0, "seconds": 2,
       "joints": [{"joint": "R1", "amp": 20, "offset": 5, "phase": 0.25}]}
KEYS = {"kind": "keys", "base": "rest",
        "keys": [{"ms": 1000, "angles": [{"joint": "L1", "deg": 40}]}, {"ms": 1000, "angles": []}]}


def stand_fw():
    return [M.raw["poses"]["stand"][j.name] for j in M.joints]


def test_osc_frames_follow_the_sine_around_the_base():
    poses = list(sm.frames(M, OSC, hz=4, intensity=1.0))
    assert len(poses) == 9  # 2 s at 4 Hz, both ends
    r1 = [j.name for j in M.joints].index("R1")
    j = M.joint("R1")
    for i, p in enumerate(poses):
        q = math.radians(5 + 20 * math.sin(2 * math.pi * (i / 4 + 0.25)))
        want = M.to_firmware(j, M.pose_internal("stand")["R1"] + q)
        assert p[r1] == pytest.approx(min(max(want, j.limits_deg[0]), j.limits_deg[1]), abs=0.051)
    others = [k for k in range(8) if k != r1]
    assert all([p[k] for k in others] == [stand_fw()[k] for k in others] for p in poses)


def test_frames_clamp_to_manifest_soft_limits():
    wild = {"kind": "osc", "base": "rest", "hz": 1, "seconds": 1,
            "joints": [{"joint": j.name, "amp": 300, "offset": 0, "phase": 0} for j in M.joints]}
    for p in sm.frames(M, wild, intensity=1.0):
        for deg, j in zip(p, M.joints):
            assert j.limits_deg[0] <= deg <= j.limits_deg[1]


def test_keys_interpolate_then_return_and_intensity_scales():
    assert sm.duration(KEYS) == 2.0
    full = sm.angles(M, KEYS, 0.5)
    assert full["L1"] == pytest.approx(20)  # halfway to 40
    assert sm.angles(M, KEYS, 1.0)["L1"] == pytest.approx(40)
    assert sm.angles(M, KEYS, 1.5)["L1"] == pytest.approx(20)  # back toward base
    assert sm.angles(M, KEYS, 0.5, scale=0.5)["L1"] == pytest.approx(10)
    assert sm.angles(M, KEYS, 5.0) == {}


def test_validate_rejects_bad_specs():
    sm.validate(M, OSC)
    sm.validate(M, KEYS)
    for bad in ({**OSC, "joints": [{"joint": "Z9", "amp": 1}]}, {**OSC, "base": "moon"},
                {**OSC, "seconds": 60}, {"kind": "dance"}):
        with pytest.raises(ValueError):
            sm.validate(M, bad)


def test_library_seeds_firmware_motions_and_persists_learned(tmp_path):
    path = tmp_path / "library.json"
    lib = sm.Library(path)
    assert "wave" in lib.names() and lib.items["wave"]["spec"] == {"kind": "firmware", "name": "wave"}
    lib.add("wiggle", "くねくね", OSC)
    assert set(json.loads(path.read_text())) == {"wiggle"}  # built-ins are not written
    assert sm.Library(path).items["wiggle"]["spec"] == OSC


def test_memory_roundtrip_and_notes(tmp_path):
    mem = sm.Memory(tmp_path)
    mem.add({"t": 1, "text": "a"})
    mem.add({"t": 2, "text": "b"})
    mem.notes = "- 手を振るのが好き"
    again = sm.Memory(tmp_path)
    assert [e["text"] for e in again.recent(1)] == ["b"]
    assert again.notes == "- 手を振るのが好き"
    assert sm.Memory().notes == ""


def test_rule_reflex():
    lib, r = sm.Library(), sm.RuleReflex()
    assert r.decide(sm.Moment("chat", "walk_backward して"), lib).action == "walk_backward"
    assert r.decide(sm.Moment("chat", "猫みたいな動きを作って"), lib).action == sm.NEW
    assert r.decide(sm.Moment("radio", "作って"), lib).action == sm.NONE  # only chat invents
    assert r.decide(sm.Moment("sound", loudness=4000, onset=True), lib).action == "shake"


def test_jev_request_and_tolerant_parse():
    lib = sm.Library()
    body = sm.jev_request(sm.Moment("voice", "こんにちは", 900.0), lib, "notes")
    qs = body["questions"]
    assert body["model"] == "jev-latest" and json.loads(body["state"])["heard"] == "こんにちは"
    assert qs["action"]["options"][-2:] == [sm.NEW, sm.NONE] and len(qs["action"]["options"]) <= 255
    assert qs["intensity"]["criteria"] == list(sm.INTENSITY)
    opts = qs["action"]["options"]
    d = sm.jev_decision({"answers": {"action": {"answer": "wave", "confidence": 0.9},
                                     "intensity": {"score": 1.5}, "addressed": {"probability": 0.8}}}, opts)
    assert (d.action, d.intensity, d.addressed, d.confidence) == ("wave", 0.5, 0.8, 0.9)
    d = sm.jev_decision({"action": {"selected": "moonwalk"}}, opts)
    assert (d.action, d.intensity, d.addressed) == (sm.NONE, 0.5, None)


def test_design_schema_and_spec_of():
    schema = sm.design_schema(M)
    assert schema["properties"]["joints"]["items"]["properties"]["joint"]["enum"] == [j.name for j in M.joints]
    design = {"name": "wiggle", "about": "くねくね", **OSC, "keys": []}
    assert sm.spec_of(design) == ("wiggle", "くねくね", OSC)
    assert sm.spec_of({"name": "n", "about": "a", **KEYS, "hz": 0, "seconds": 0, "joints": []})[2] == KEYS


TROT = {"kind": "axes", "hz": 2, "seconds": 1,
        "axes": [{"axis": "stride", "amp": 15, "offset": 0, "phase": 0},
                 {"axis": "lift", "amp": 10, "offset": 0, "phase": 0.25}]}


def test_axes_frames_are_the_motion_space_trot():
    from sim.motion_space import firmware_pose, gait
    for i, p in enumerate(sm.frames(M, TROT, hz=10, intensity=1.0)):
        want = firmware_pose(gait(i / 10, 2, stride=15, lift=10), M)
        assert p == pytest.approx(want, abs=0.051)


def test_axes_frames_shrink_wild_poses_into_the_motion_space():
    from sim.motion_space import feasible, firmware_pose, load_space, project
    crouch = {"kind": "axes_keys", "keys": [{"ms": 500, "axes": [{"axis": "height", "value": -30},
                                                                  {"axis": "pitch", "value": 20}]}]}
    last = list(sm.frames(M, crouch, hz=10, intensity=1.0))[-1]
    z = project({"height": load_space()["center"]["height"] - 30, "pitch": 20})
    assert feasible(z) and -8 < z["height"] - 42 < 0 and 0 < z["pitch"] < 20
    assert last == pytest.approx(firmware_pose(z, M), abs=0.051)


def test_axes_specs_validate_and_round_trip_the_schema():
    sm.validate(M, TROT)
    with pytest.raises(ValueError, match="axes"):
        sm.validate(M, {**TROT, "axes": [{"axis": "R1", "amp": 1}]})
    schema = sm.design_schema(M)
    assert schema["properties"]["axes"]["items"]["properties"]["axis"]["enum"] == list(sm.AXES)
    design = {"name": "trot", "about": "とことこ", **TROT, "base": "stand", "joints": [],
              "keys": [{"ms": 100, "axes": [], "angles": []}]}
    assert sm.spec_of(design) == ("trot", "とことこ", TROT)
    keyed = {"name": "bow", "about": "おじぎ", "kind": "axes_keys", "base": "stand", "hz": 0, "seconds": 0,
             "axes": [], "joints": [], "keys": [{"ms": 400, "axes": [{"axis": "pitch", "value": -4}], "angles": []}]}
    assert sm.spec_of(keyed)[2] == {"kind": "axes_keys", "keys": [{"ms": 400, "axes": [{"axis": "pitch", "value": -4}]}]}
    assert "stride" in sm.DESIGN_SYSTEM and "axes_keys" in sm.DESIGN_SYSTEM


class FakeSpine:
    manifest = M
    robot = None

    def __init__(self):
        self.played = []

    def start(self, entry, intensity=0.5, tempo=1.0):
        self.played.append((entry["spec"], intensity))
        self.tempo = tempo


class FakeDesigner:
    def __init__(self, spec=OSC):
        self.spec = spec

    def design(self, moment, library, notes=""):
        return "wiggle", "くねくね", self.spec

    def ruminate(self, recent, notes=""):
        return f"- {len(recent)} things happened"


class BrokenReflex:
    by = "jev"

    def decide(self, *a):
        raise OSError("no route to host")


def test_mind_invents_learns_and_replays(tmp_path):
    spine = FakeSpine()
    mind = sm.Mind(sm.RuleReflex(), sm.Library(tmp_path / "lib.json"), sm.Memory(tmp_path), spine,
                   FakeDesigner(), clock=lambda: 7.0)
    entry = mind.handle(sm.Moment("chat", "くねくねする動きを作って"))
    assert entry["did"] == "wiggle" and "new motion" in entry["note"] and entry["t"] == 7.0
    assert spine.played == [(OSC, 0.6)]
    assert mind.handle(sm.Moment("chat", "wiggle もう一回"))["did"] == "wiggle"  # no designer needed now
    mind.ruminate()
    assert mind.memory.notes == "- 2 things happened"


def test_mind_survives_bad_designs_and_reflex_outages(tmp_path):
    spine = FakeSpine()
    mind = sm.Mind(BrokenReflex(), sm.Library(), sm.Memory(), spine, FakeDesigner({"kind": "dance"}))
    assert mind.handle(sm.Moment("chat", "wave"))["by"] == "rules"
    entry = mind.handle(sm.Moment("chat", "新しいのを作って"))
    assert entry["did"] == sm.NONE and "design failed" in entry["note"]
    assert len(spine.played) == 1
    mind.designer.ruminate = lambda *a: (_ for _ in ()).throw(RuntimeError("offline"))
    mind.ruminate()  # logged, not raised
    assert mind.memory.notes == ""


class SlowLLMReflex:
    by = "llm:claude"

    def __init__(self, answers):
        self.answers = iter(answers)

    def decide(self, moment, library, notes=""):
        time.sleep(0.2)
        return sm.Decision(next(self.answers), 0.6, 1.0, by=self.by)


class SlowDesigner(FakeDesigner):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def design(self, moment, library, notes=""):
        self.calls += 1
        time.sleep(0.2)
        return super().design(moment, library, notes)


def test_model_reflex_designs_in_parallel_and_drops_unused_designs(tmp_path):
    spine, designer = FakeSpine(), SlowDesigner()
    mind = sm.Mind(SlowLLMReflex([sm.NEW, "wave", sm.NEW]), sm.Library(tmp_path / "lib.json"), sm.Memory(tmp_path),
                   spine, designer)
    t0 = time.monotonic()
    entry = mind.handle(sm.Moment("chat", "くねくねして"))
    assert entry["did"] == "wiggle" and time.monotonic() - t0 < 0.35  # max(0.2, 0.2), not their sum
    assert mind.handle(sm.Moment("chat", "手を振って"))["did"] == "wave" and designer.calls == 2
    assert "wiggle_2" not in mind.library.items  # the early design for "wave" was not kept
    designer.design = lambda *a: (_ for _ in ()).throw(RuntimeError("overloaded"))
    assert "design failed: overloaded" in mind.handle(sm.Moment("chat", "もう一つ"))["note"]
    rules = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(), FakeSpine(), SlowDesigner())
    rules.handle(sm.Moment("chat", "wave"))
    assert rules.designer.calls == 0  # the rules reflex pays for no design


def test_mind_shows_thinking_then_idle_and_cue_rejects_command_chains(tmp_path):
    sent = []

    class Robot:
        def command(self, text):
            sent.append(text)
            return True, "OK FACE"

    spine = FakeSpine()
    spine.robot = Robot()
    mind = sm.Mind(sm.RuleReflex(), sm.Library(tmp_path / "lib.json"), sm.Memory(tmp_path), spine, FakeDesigner())
    mind.handle(sm.Moment("chat", "くねくねする動きを作って"))   # designed motion
    mind.handle(sm.Moment("chat", "wave"))                     # firmware motion sets its own face
    mind.handle(sm.Moment("chat", "ふーん"))                   # nothing to do
    time.sleep(0.1)
    assert sorted(sent) == sorted(["face thinking", "face idle", "face thinking", "face thinking", "face idle"])
    assert mind.cue("surprised") and not mind.cue("happy;off") and not mind.cue("")


def test_remote_ear_state_reaches_latest_and_sets_faces_once(tmp_path):
    sent = []

    class Robot:
        def command(self, text):
            sent.append(text)
            return True, "OK FACE"

    spine = FakeSpine()
    spine.robot = Robot()
    spine.health = "ok"
    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(tmp_path), spine)
    assert json.loads(sm.latest(mind))["ear"] is None
    mind.hear_ear({"s": "listening", "level": 0.4})
    mind.hear_ear({"s": "listening", "level": 7})
    mind.hear_ear({"s": "thinking"})
    ear = mind.hear_ear({"s": "heard", "text": "立って" * 100})
    assert ear["level"] == 0 and len(ear["text"]) == 200
    assert json.loads(sm.latest(mind))["ear"]["s"] == "heard"
    with pytest.raises(ValueError):
        mind.hear_ear({"s": "face happy;off"})
    time.sleep(0.1)
    assert sorted(sent) == ["face surprised", "face thinking"]  # one face per state change
    mind.ear["t"] -= 60
    assert json.loads(sm.latest(mind))["ear"] is None  # stale


def test_spine_dry_run_and_streaming():
    sent = []

    class FakeRobot:
        def command(self, text):
            sent.append(text)
            return True, "OK"

    sm.Spine(M).play({"spec": OSC})  # dry: prints, sends nothing
    assert sm.Spine(M, FakeRobot(), hz=4, sleep=lambda s: None).play({"spec": OSC}) == 0
    assert len(sent) == 10 and sent[-1] == "motion stand"  # stands up again afterwards
    assert all(s.startswith("pose ") and len(s.split()) == 9 for s in sent[:-1])


def tone(level, seconds):
    n = int(sm.RATE * seconds)
    return array.array("h", [int(level * math.sqrt(2) * math.sin(i / 3)) for i in range(n)]).tobytes()


def test_utterances_split_on_silence_and_flag_onsets():
    audio = tone(50, 1.0) + tone(5000, 0.5) + tone(50, 1.0) + tone(1000, 0.3) + tone(50, 1.0)
    events = list(sm.utterances(io.BytesIO(audio)))
    speech = [v for k, v in events if k == "speech"]
    sounds = [v for k, v in events if k == "sound"]
    assert len(speech) == 2
    assert len(speech[0]) >= 0.5 * sm.RATE * 2  # whole loud stretch plus its silent tail
    assert sounds == [pytest.approx(5000, rel=0.05)]  # one per bang; the 1000 RMS voice is not one


def test_chat_server_accepts_posts_from_the_robot_page(tmp_path):
    import queue
    import urllib.request
    moments = queue.Queue()
    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(tmp_path), FakeSpine())
    server = sm.serve(0, mind, moments)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        req = urllib.request.Request(base + "/say", "wave".encode(), method="POST",
                                     headers={"Origin": "http://sesame-s3-8b2c.local", "Content-Type": "text/plain"})
        with urllib.request.urlopen(req) as r:
            assert r.status == 202 and r.headers["Access-Control-Allow-Origin"] == "*"
        assert moments.get_nowait() == sm.Moment("chat", "wave")
        with urllib.request.urlopen(base + "/log") as r:
            assert r.headers["Access-Control-Allow-Origin"] == "*" and json.loads(r.read()) == []
    finally:
        server.shutdown()


def no_claude_auth(monkeypatch, tmp_path):
    for env in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "TYPESAFE_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path / "anthropic"))


def test_settings_validate_persist_and_refuse_keys(tmp_path, monkeypatch):
    no_claude_auth(monkeypatch, tmp_path)
    st = sm.Settings(tmp_path)
    assert st.values["reflex"] == "rules" and st.public()["claude_auth"] == ""
    st.update({"reflex": "jev", "anthropic_key": "sk-secret", "live": 1, "unknown": "x"})
    with pytest.raises(ValueError):
        st.update({"designer": "gpt"})
    again = sm.Settings(tmp_path)
    view = again.public()
    assert view["reflex"] == "jev" and view["live"] is True and "unknown" not in view
    assert "sk-secret" not in (tmp_path / "config.json").read_text()  # keys never arrive over HTTP
    assert (tmp_path / "config.json").stat().st_mode & 0o777 == 0o600


def test_claude_auth_sources(tmp_path, monkeypatch):
    no_claude_auth(monkeypatch, tmp_path)
    assert sm.claude_auth() == ""
    creds = tmp_path / "anthropic" / "credentials"
    creds.mkdir(parents=True)
    (creds / "default.json").write_text("{}")  # what `ant auth login` leaves behind
    assert sm.claude_auth() == "profile"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert sm.claude_auth() == "key"


def test_build_reports_missing_keys_and_falls_back(tmp_path, monkeypatch):
    no_claude_auth(monkeypatch, tmp_path)
    st = sm.Settings(tmp_path)
    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(), sm.Spine(M))
    status = mind.configure(st)  # designer claude without a key
    assert status["designer"] == "none" and "ant auth login" in status["error"] and status["reflex"] == "rules"
    st.update({"reflex": "llm", "reflex_brain": "local", "designer": "local", "local_model": "tiny"})
    status = mind.configure(st)
    assert (status["reflex"], status["designer"], status["error"]) == ("llm:local", "local", "")
    st.update({"reflex": "jev", "jev_url": "http://localhost:9/v1/systemone"})
    assert mind.configure(st)["reflex"] == "jev" and mind.reflex.url.startswith("http://localhost:9")


def test_local_brain_and_llm_reflex():
    sent = []

    def post(body):
        sent.append(body)
        return {"choices": [{"message": {"content": 'Sure! {"action": "wave_2", "intensity": -1, "addressed": 0.7}'}}]}

    brain = sm.LocalBrain("http://localhost:8080/v1/", "tiny", post=post)
    lib = sm.Library()
    lib.add("wave", "前足をふりふり", {"kind": "keys", "base": "stand", "keys": [{"ms": 300, "angles": []}]})
    d = sm.LLMReflex(brain).decide(sm.Moment("chat", "手を振って"), lib)
    assert (d.action, d.intensity, d.addressed, d.by) == ("wave_2", 0.0, 0.7, "llm:local")  # stock wave is hidden
    rf = sent[0]["response_format"]["json_schema"]
    assert sent[0]["model"] == "tiny" and rf["schema"]["properties"]["action"]["enum"] == ["wave_2", sm.NEW, sm.NONE]
    sm.LLMReflex(brain, use_stock=True).decide(sm.Moment("chat", "x"), lib)
    assert "dance" in sent[-1]["response_format"]["json_schema"]["schema"]["properties"]["action"]["enum"]
    assert sm.local_models("http://127.0.0.1:9/v1") == []  # nothing listening


def test_config_endpoint_round_trip(tmp_path, monkeypatch):
    import queue
    import urllib.request
    no_claude_auth(monkeypatch, tmp_path)
    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(tmp_path), sm.Spine(M))
    mind.configure(sm.Settings(tmp_path))
    server = sm.serve(0, mind, queue.Queue())
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        body = json.dumps({"designer": "none", "typesafe_key": "ts-secret", "local_url": "http://127.0.0.1:9/v1"})
        with urllib.request.urlopen(urllib.request.Request(base + "/config", body.encode(), method="POST")) as r:
            view = json.loads(r.read())
        assert not view["typesafe_key_set"] and "ts-secret" not in json.dumps(view)
        assert view["status"] == {"reflex": "rules", "designer": "none", "robot": "", "body": "off", "error": ""}
        assert view["local_models"] == []
        with urllib.request.urlopen(base + "/thoughts") as r:
            assert "ウラシマの頭の中" in r.read().decode()
        with urllib.request.urlopen(base + "/trace") as r:
            assert json.loads(r.read()) == []
        bad = urllib.request.Request(base + "/config", b'{"reflex": "psychic"}', method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(bad)
        assert e.value.code == 400
        with urllib.request.urlopen(base + "/space") as r:
            assert r.headers["Content-Type"].startswith("text/plain") and "stride" in r.read().decode()
    finally:
        server.shutdown()


# ---------------------------------------------------------------- voice body


def excited_pcm(seconds=1.5):
    """Rising 330 -> 430 Hz syllables as int16 bytes, like the simulator's excited voice."""
    from sim.voice_motion import synth_utterance
    audio = synth_utterance("excited")
    reps = int(seconds * sm.RATE / len(audio)) + 1
    pcm = [int(max(-1, min(1, x)) * 32767) for x in list(audio) * reps]
    return array.array("h", pcm).tobytes()


def quiet_body():
    body = sm.VoiceBody(M, FakeSpine())
    body.started = True  # no loop/sender threads: the test steps frames itself
    return body


def test_voice_body_hears_prosody_and_poses_inside_limits():
    body = quiet_body()
    body.set_mode("both")
    pcm = excited_pcm()
    for i in range(0, len(pcm), 3200):  # 100 ms chunks, as the ears read them
        body.feed(pcm[i:i + 3200])
        while not body.frames.empty():
            target = body.step(body.frames.get())
    state = body.state()
    assert state["arousal"] > 0.5 and state["amp"] > 0.3 and state["f0"] > 300
    for deg, j in zip(body.pose(target), M.joints):
        assert j.limits_deg[0] <= deg <= j.limits_deg[1]
    assert body.pose(body.cpg.base) == [float(x) for x in stand_fw()]


def test_voice_body_off_ignores_audio_and_words():
    body = quiet_body()
    body.feed(excited_pcm(0.3))
    assert body.frames.empty() and body.hear_words("落ち着いて") == "-"


def test_mind_routes_words_to_the_body_and_skips_the_spine(tmp_path):
    spine = FakeSpine()
    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(tmp_path), spine)
    mind.body.started = True
    settings = sm.Settings(tmp_path)
    settings.update({"body": "words"})
    mind.configure(settings)
    assert mind.handle(sm.Moment("chat", "おいで")) ["did"] == "body:approach"
    assert mind.handle(sm.Moment("chat", "こんにちは"))["did"] == "body:-"
    assert mind.handle(sm.Moment("sound", loudness=5000, onset=True)) is None
    assert spine.played == [] and mind.body.state()["intent"] == "-"  # no step yet
    mind.body.step(sm.VoiceBody.SILENCE)
    assert mind.body.state()["intent"] == "approach"
    with pytest.raises(ValueError):
        settings.update({"body": "dance"})
    settings.update({"body": "off"})
    mind.configure(settings)
    mind.handle(sm.Moment("chat", "wave"))
    assert spine.played  # back to the reflex and library


def test_body_endpoint(tmp_path):
    import queue
    import urllib.request
    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(tmp_path), sm.Spine(M))
    mind.configure(sm.Settings(tmp_path))
    server = sm.serve(0, mind, queue.Queue())
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/body") as r:
            assert r.headers["Access-Control-Allow-Origin"] == "*"
            state = json.loads(r.read())
        assert state["mode"] == "off" and state["mic"] is False and state["f0"] is None
    finally:
        server.shutdown()


def test_body_drives_the_simulated_robot(tmp_path):
    import time
    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(tmp_path), sm.Spine(M))
    settings = sm.Settings(tmp_path)
    settings.update({"host": "sim", "live": True, "body": "words"})
    mind.configure(settings)
    try:
        robot = mind.spine.robot
        assert robot is sm.sim_robot() and robot.host == "sim"
        mind.handle(sm.Moment("chat", "あそぼう"))  # play: a lively trot
        deadline = time.monotonic() + 5
        while mind.body.sent < 10 and time.monotonic() < deadline:
            time.sleep(0.1)
        state = mind.body.state()
        assert state["robot"] == "sim" and state["intent"] == "play" and state["sent"] >= 10, state
        assert robot.mode == "run" and not state["error"]
        assert 'id=body' in sm.PAGE and "sim.mjpg" in sm.PAGE
    finally:
        settings.update({"body": "off", "live": False})
        mind.configure(settings)
        mind.link and mind.link.set()


def test_announce_tells_the_robot_where_the_mind_is(tmp_path):
    import threading
    sent = []

    class Robot:
        def __init__(self, host):
            self.host = host

        def get(self, path):
            return True, "mode=0 outputs=0 mind=" + (sent[-1].split()[1] if sent else "-") + "\n"

        def command(self, text):
            sent.append(text)
            return True, "OK MIND " + text.split()[1]

    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(tmp_path), FakeSpine())
    mind.configure(sm.Settings(tmp_path))
    assert sm.lan_url("127.0.0.1", 8765) == "http://127.0.0.1:8765"
    stop = threading.Event()
    stop.set()  # one round
    sm.announce(mind, ["127.0.0.1"], 8765, stop=stop, robot_of=Robot)
    sm.announce(mind, ["127.0.0.1"], 8765, stop=stop, robot_of=Robot)  # already told: nothing new
    assert sent == ["mind http://127.0.0.1:8765"]


def test_mic_on_demand_opens_only_while_the_body_listens(monkeypatch):
    import argparse
    import queue
    import threading
    import time
    starts, fed = [], []
    silence = [sys.executable, "-c", "import sys,time\nwhile True: sys.stdout.buffer.write(bytes(3200)); "
               "sys.stdout.flush(); time.sleep(0.05)"]
    monkeypatch.setattr(sm, "source_command", lambda args: starts.append(1) or silence)

    class Body:
        mode = "off"

        def feed(self, data):
            fed.append(len(data))

    body = Body()
    args = argparse.Namespace(sdr=None, mic=True, mic_on_demand=True, whisper_model=None, silence_rms=300.0)
    threading.Thread(target=sm.hear, args=(args, queue.Queue(), body, 0.02), daemon=True).start()
    time.sleep(0.3)
    assert starts == [] and fed == []  # body off: the microphone stays closed
    body.mode = "prosody"
    deadline = time.monotonic() + 5
    while not fed and time.monotonic() < deadline:
        time.sleep(0.02)
    assert starts == [1] and fed
    body.mode = "off"
    time.sleep(0.5)
    n = len(fed)
    time.sleep(0.3)
    assert len(fed) == n and starts == [1]  # closed again, not restarted


def test_robot_caches_the_mdns_address_and_looks_again_after_a_failure(monkeypatch):
    import urllib.request
    from sesame_remote import Robot
    looked, opened = [], []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"OK"

    def urlopen(url, timeout):
        opened.append(url)
        if len(opened) == 3:
            raise OSError("no route")
        return Reply()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(sm.time, "sleep", lambda s: None)
    robot = Robot("sesame-s3-test.local", resolve=lambda name: looked.append(name) or f"10.0.0.{len(looked)}")
    assert robot.get("/status") == (True, "OK") and robot.command("stop")[0]
    assert looked == ["sesame-s3-test.local"] and opened[1].startswith("http://10.0.0.1/cmd")
    assert robot.get("/status") == (True, "OK")  # third open fails, the name is looked up again
    assert len(looked) == 2 and opened[-1] == "http://10.0.0.2/status"
    assert robot.base == "http://sesame-s3-test.local"


def test_console_keeps_printed_lines_for_the_pages():
    out = io.StringIO()
    console = sm.Console(keep=3)
    tee = console.tee(out)
    print("> motion dance", file=tee)
    tee.write("OK MOT")
    tee.write("ION dance\n\n  (spine) no link\nhalf")
    assert out.getvalue().startswith("> motion dance\nOK MOTION dance")  # still reaches the terminal/log
    assert [line for _, line in console.recent()] == ["> motion dance", "OK MOTION dance", "  (spine) no link"]
    print("next", file=tee)
    assert [line for _, line in console.recent(2)] == ["  (spine) no link", "halfnext"]  # a partial line waits
    assert tee.encoding == out.encoding


def test_ease_shapes_a_key_and_tempo_rescales_time():
    eased = {"kind": "keys", "base": "stand", "keys": [{"ms": 1000, "ease": "in", "angles": [{"joint": "L1", "deg": 40}]},
                                                       {"ms": 1000, "ease": "out", "angles": []}]}
    sm.validate(M, eased)
    assert sm.angles(M, KEYS, 0.5)["L1"] == pytest.approx(20)  # linear: halfway at half time
    assert sm.angles(M, eased, 0.5)["L1"] == pytest.approx(10)  # in: a quarter of the way (wind-up)
    assert sm.angles(M, eased, 1.5)["L1"] == pytest.approx(10)  # out: already 3/4 of the way back
    with pytest.raises(ValueError):
        sm.validate(M, {**eased, "keys": [{"ms": 500, "ease": "bounce", "angles": []}]})
    normal = list(sm.frames(M, eased, hz=20, intensity=1.0))
    fast = list(sm.frames(M, eased, hz=20, intensity=1.0, tempo=2.0))
    slow = list(sm.frames(M, eased, hz=20, intensity=1.0, tempo=0.1))  # clamped to 0.5
    assert (len(normal), len(fast), len(slow)) == (41, 21, 81)
    assert fast[10] == normal[20] and slow[80] == normal[40]
    design = {"name": "flick", "about": "ため", "kind": "keys", "base": "stand", "hz": 0, "seconds": 0,
              "axes": [], "joints": [], "keys": [{"ms": 800, "ease": "in", "axes": [], "angles": []},
                                                 {"ms": 200, "ease": "linear", "axes": [], "angles": []}]}
    assert [k.get("ease") for k in sm.spec_of(design)[2]["keys"]] == ["in", None]
    assert sm.design_schema(M)["properties"]["keys"]["items"]["properties"]["ease"]["enum"] == list(sm.EASE)


def test_speed_words_set_the_tempo():
    lib = sm.Library()
    assert sm.RuleReflex().decide(sm.Moment("chat", "速く dance"), lib).tempo == 1.5
    assert sm.RuleReflex().decide(sm.Moment("chat", "ゆっくり wave"), lib).tempo == 0.6
    assert sm.RuleReflex().decide(sm.Moment("chat", "dance"), lib).tempo == 1.0


def test_trace_shows_reasoning_design_and_curve(tmp_path):
    class Brainy:
        by = "fake"

        def decide(self, moment, library, notes=""):
            return sm.Decision(sm.NEW, 1.0, 0.9, by="fake", tempo=2.0, why="まだ無い動き", considered=3)

    class Designer:
        by = "fake"

        def design(self, moment, library, notes=""):
            return ("flick", "ため", {"kind": "axes_keys", "keys": [
                {"ms": 800, "ease": "in", "axes": [{"axis": "height", "value": -6}]},
                {"ms": 200, "axes": [{"axis": "height", "value": 4}, {"axis": "pitch", "value": 2}]}]}, "溜めて弾く")

    mind = sm.Mind(Brainy(), sm.Library(), sm.Memory(tmp_path), FakeSpine(), Designer())
    mind.handle(sm.Moment("chat", "寒いね"))
    [e] = sm.trace(mind)
    assert (e["why"], e["considered"], e["design"]["why"], e["did"]) == ("まだ無い動き", 3, "溜めて弾く", "flick")
    c = e["motion"]["curve"]
    assert list(c["series"]) == ["height", "pitch"] and c["unit"] == "axis"
    assert c["keys"] == [{"t": 0.4, "ease": "in"}, {"t": 0.5, "ease": "linear"}]  # tempo 2 halves time
    assert len(c["t"]) == 21 and c["series"]["height"][-1] == pytest.approx(4)
    assert sm.curve(M, {"kind": "firmware", "name": "dance"}) is None


def test_a_reset_robot_is_armed_again():
    class Robot:
        def __init__(self):
            self.armed, self.sent = False, []

        def command(self, text):
            self.sent.append(text)
            if text == "arm run":
                self.armed = True
                return True, "OK ARMED"
            return (True, "OK") if self.armed else (False, "ERR arm run first")

    robot, t = Robot(), [0.0]
    clock = lambda: t[0]  # noqa: E731
    assert sm.armed_command(robot, "pose 90 90 90 90 90 90 90 90", clock) == (True, "OK")
    assert robot.sent == ["pose 90 90 90 90 90 90 90 90", "arm run", "pose 90 90 90 90 90 90 90 90"]
    assert sm.armed_command(robot, "stop", clock) == (True, "OK") and robot.sent[-1] == "stop" and len(robot.sent) == 4
    robot.armed, t[0] = False, 5.0  # reset again while moving: a sagging battery
    assert sm.armed_command(robot, "pose 1", clock) == (False, "ERR robot keeps resetting (battery low?)")
    assert robot.sent[-1] == "pose 1" and "arm run" not in robot.sent[4:]
    t[0] = 40.0  # quiet for the window: try again
    assert sm.armed_command(robot, "pose 2", clock) == (True, "OK") and robot.sent[-2:] == ["arm run", "pose 2"]


def test_guest_port_only_talks_and_shows_thoughts(tmp_path):
    import queue
    import urllib.error
    import urllib.request
    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(tmp_path), sm.Spine(M))
    moments, t = queue.Queue(), [100.0]
    server = sm.serve_guest(0, mind, moments, sm.Gate(every=4.0, clock=lambda: t[0]))
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, body):
        return urllib.request.urlopen(urllib.request.Request(base + path, body.encode(), method="POST"))

    try:
        with urllib.request.urlopen(base + "/") as r:
            assert "話しかける" in r.read().decode() and r.headers["Cache-Control"] == "no-store"
        r = post("/say", "こんにちは")
        assert r.status == 202 and moments.get_nowait().text == "こんにちは"
        assert abs(json.loads(r.read())["t"] - time.time()) < 5  # the page matches its card by this
        with pytest.raises(urllib.error.HTTPError) as e:
            post("/say", "もう一回")  # within 4 s
        assert e.value.code == 429 and json.loads(e.value.read())["wait_s"] == 4.0
        t[0] += 4.0
        assert post("/say", "あ" * 500).status == 202 and len(moments.get_nowait().text) == 200
        for path, body in (("/config", '{"live": true}'), ("/ruminate", ""), ("/ear", '{"s": "heard"}'), ("/cue", "x")):
            with pytest.raises(urllib.error.HTTPError) as e:
                post(path, body)
            assert e.value.code == 404  # settings stay on the admin port
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/config")
        with urllib.request.urlopen(base + "/latest") as r:
            assert json.loads(r.read()) == {"n": 0, "t": 0, "robot": "dry", "doing": "", "ear": None}
        mind.memory.add({"t": 5.0, "text": "x" * 4000, "did": "none"})
        with urllib.request.urlopen(base + "/latest") as r:
            assert json.loads(r.read()) == {"n": 1, "t": 5.0, "robot": "dry", "doing": "none", "ear": None}
        import gzip
        req = urllib.request.Request(base + "/trace", headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req) as r:
            assert r.headers["Content-Encoding"] == "gzip"
            assert json.loads(gzip.decompress(r.read()))[0]["text"] == "x" * 4000
    finally:
        server.shutdown()


def test_gate_spaces_messages_and_stops_for_the_day():
    t, day = [0.0], ["2026-11-26"]
    gate = sm.Gate(every=4.0, daily=2, clock=lambda: t[0], today=lambda: day[0])
    assert gate.wait_s() == 0 and gate.wait_s() == 4.0
    t[0] = 4.0
    assert gate.wait_s() == 0
    t[0] = 100.0
    assert gate.wait_s() == math.inf  # two used today
    day[0] = "2026-11-27"
    assert gate.wait_s() == 0


def test_designed_motions_stand_up_after_and_the_stand_button(tmp_path):
    class Robot:
        sent = []

        def command(self, text):
            self.sent.append(text)
            return True, "OK"

    robot = Robot()
    spine = sm.Spine(M, robot, hz=10, sleep=lambda s: None)
    spine.play({"spec": {"kind": "axes_keys", "keys": [{"ms": 300, "axes": [{"axis": "height", "value": -4}]}]}})
    assert robot.sent[0].startswith("pose ") and robot.sent[-1] == "motion stand"
    assert spine.health == "ok"
    mind = sm.Mind(sm.RuleReflex(), sm.Library(), sm.Memory(tmp_path), FakeSpine())
    e = mind.stand()
    assert (e["did"], e["source"]) == ("stand", "button") and mind.spine.played[-1][0]["name"] == "stand"
    assert sm.trace(mind)[-1]["motion"]["kind"] == "firmware"


def test_pads_list_learned_first_and_play_at_once(tmp_path):
    import queue
    import urllib.error
    import urllib.request
    lib = sm.Library()
    lib.add("hop", "ぴょん", {"kind": "axes_keys", "keys": [{"ms": 300, "axes": [{"axis": "height", "value": 3}]}]})
    lib.add("sway", "ゆらゆら", {"kind": "axes_keys", "keys": [{"ms": 300, "axes": [{"axis": "roll", "value": 2}]}]})
    mind = sm.Mind(sm.RuleReflex(), lib, sm.Memory(tmp_path), FakeSpine())
    server = sm.serve_guest(0, mind, queue.Queue())
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/motions") as r:
            pads = json.loads(r.read())
        assert [p["name"] for p in pads[:3]] == ["sway", "hop", "rest"] and pads[2]["stock"]
        body = json.dumps({"name": "hop", "tempo": 5, "intensity": 0.9}).encode()
        assert urllib.request.urlopen(urllib.request.Request(base + "/play", body, method="POST")).status == 202
        assert mind.spine.played[-1][0]["keys"][0]["axes"][0]["axis"] == "height" and mind.spine.tempo == 2.0
        e = sm.trace(mind)[-1]
        assert (e["source"], e["did"], e["tempo"], e["intensity"]) == ("pad", "hop", 2.0, 0.9)
        import time
        time.sleep(0.45)
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(urllib.request.Request(base + "/play", b'{"name": "nope"}', method="POST"))
        assert err.value.code == 400
    finally:
        server.shutdown()
