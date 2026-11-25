"""Offline tests: real loopback HTTP, native SafeAction, PTY and relay; no devices/keys."""
from contextlib import contextmanager
import http.client
import io
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import wave

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.voice_demo.client import Controller, ServerUnavailable, request_plan
from tools.voice_demo.inputs import PushToTalk, Recorder
from tools.voice_demo.plan import Catalog, InvalidPlan
from tools.voice_demo.playback import Player, PlaybackError, SerialLink
from tools.voice_demo.providers import FakeProvider, OpenAIProvider, ProviderError, check_wav, provider_from_env
from tools.voice_demo.server import Server
from tools.voice_demo.simulator import SimulatedRobot
from tools.voice_demo import inputs

TOKEN = "test-only-device-token-not-a-credential"


@pytest.fixture(scope="module")
def catalog():
    return Catalog()


@pytest.fixture(scope="module")
def robot(catalog):
    with SimulatedRobot(catalog) as robot:
        yield robot


@pytest.fixture
def link(robot):
    with SerialLink(robot.port, log=lambda _: None) as link:
        link.off()
        yield link


@contextmanager
def serving(catalog, provider=None):
    with Server(("127.0.0.1", 0), TOKEN, catalog, provider or FakeProvider(catalog)) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", server
        finally:
            server.shutdown()
            thread.join(timeout=2)


def wav(seconds=.1):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x00\x00" * int(16000 * seconds))
    return stream.getvalue()


def wait_for(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.01)
    assert predicate(), "condition did not become true before deadline"


def assert_off(link):
    status, rows = link.status()
    assert status["mode"] == "0" and status["outputs"] == "0" and rows == {}


def test_catalog_and_schema_follow_manifests(catalog):
    assert len(catalog.motions) == 19
    assert set(catalog.unavailable) == {"walk", "point"}
    assert len(catalog.available) == 17
    assert "happy" in catalog.faces and "defualt" not in catalog.faces
    schema = catalog.schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["steps"]["items"]["anyOf"][0]["properties"]["name"]["enum"] == catalog.available
    assert catalog.validate(catalog.plan([{"type": "motion", "name": "bow"}])) == [9725]


@pytest.mark.parametrize("step,reason", [
    ({"type": "face_bitmap", "data": "00"}, "reserved"),
    ({"type": "exec", "code": "off"}, "unknown step"),
    ({"type": "motion", "name": "fly"}, "unknown motion"),
    ({"type": "motion", "name": []}, "unknown motion"),
    ({"type": "motion", "name": "bow\noff"}, "unknown motion"),
    ({"type": "motion", "name": "walk"}, "fitted travel"),
    ({"type": "motion", "name": "point"}, "fitted travel"),
    ({"type": "face", "name": "default", "hold_ms": 0}, "unknown face"),
    ({"type": "face", "name": "happy", "hold_ms": True}, "hold_ms"),
    ({"type": "rest", "serial": "arm run"}, "expected fields"),
    ({"type": "pose", "angles": [90]*7, "duration_ms": 1000, "hold_ms": 0}, "eight angles"),
    ({"type": "pose", "angles": [80, 90, 90, 90, 90, 90, 90, 90], "duration_ms": 1000, "hold_ms": 0}, "fitted travel"),
    ({"type": "pose", "angles": [90, 90, 90, 90, float("nan"), 90, 90, 90], "duration_ms": 1000, "hold_ms": 0}, "finite"),
    ({"type": "pose", "angles": [True]*8, "duration_ms": 1000, "hold_ms": 0}, "finite"),
    ({"type": "pose", "angles": [10**400]*8, "duration_ms": 1000, "hold_ms": 0}, "finite"),
    ({"type": "pose", "angles": [180, 90, 90, 90, 90, 90, 90, 90], "duration_ms": 100, "hold_ms": 0}, "at least 1500"),
])
def test_validator_rejects_untrusted_steps(catalog, step, reason):
    with pytest.raises(InvalidPlan, match=reason):
        catalog.validate(catalog.plan([step]))


def test_plan_bounds_contract_and_entire_sequence(catalog):
    with pytest.raises(InvalidPlan, match="1..32"):
        catalog.validate(catalog.plan([{"type": "rest"}] * 33))
    with pytest.raises(InvalidPlan, match="duration bound"):
        catalog.validate(catalog.plan([{"type": "motion", "name": "bow"}] * 20))
    plan = catalog.plan([{"type": "rest"}])
    plan["contract"] = "old firmware"
    with pytest.raises(InvalidPlan, match="mismatch"):
        catalog.validate(plan)
    plan["version"] = True
    with pytest.raises(InvalidPlan, match="version"):
        catalog.validate(plan)


def test_fake_provider_known_creative_and_unknown(catalog, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VOICE_PROVIDER", raising=False)
    fake = provider_from_env(catalog)
    assert isinstance(fake, FakeProvider)
    for text in ("do a bow", "say hello to the audience", "move like a snake", "お辞儀", "蛇"):
        plan, notes = fake.generate(text)
        catalog.validate(plan)
        assert "fake" in notes[0]
    assert fake.generate("move like a snake")[0]["steps"][0]["type"] == "pose"
    assert fake.generate("walk backward")[0]["steps"][0]["name"] == "walk_backward"
    with pytest.raises(InvalidPlan):
        fake.generate("unrecognised request")
    with pytest.raises(InvalidPlan, match="unsupported"):
        fake.generate("draw an image")
    assert fake.transcribe(wav()) == "do a bow"


def test_wav_validation():
    check_wav(wav())
    for data in (b"bad", wav()[:-2], wav(31), b"a" * 1_000_001):
        with pytest.raises(InvalidPlan):
            check_wav(data)


def test_server_text_audio_auth_and_failures(catalog):
    with serving(catalog) as (url, server):
        result = request_plan(url, TOKEN, text="say hello to the audience")
        assert result["transcript"] == "say hello to the audience"
        assert result["plan"]["steps"][1]["name"] == "wave"
        audio_result = request_plan(url, TOKEN, audio=wav())
        assert audio_result["transcript"] == "do a bow" and "fixed transcript" in audio_result["notes"][0]
        with pytest.raises(ServerUnavailable, match="HTTP 401"):
            request_plan(url, "wrong", text="bow")
        with pytest.raises(ServerUnavailable, match="HTTP 422"):
            request_plan(url, TOKEN, text="make a bitmap")
        for body, mime, code in ((b"broken", "audio/wav", 422), (b"{", "application/json", 422),
                                 (b"[]", "application/json", 422), (b"hello", "text/plain", 415)):
            req = urllib.request.Request(url + "/prompt", body, {"Authorization": "Bearer " + TOKEN, "Content-Type": mime})
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req, timeout=2)
            assert error.value.code == code
        # Oversized Content-Length is rejected before reading the body. Sending
        # a megabyte after the rejection can legitimately get EPIPE on macOS.
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("POST", "/prompt", b"x", {"Authorization": "Bearer " + TOKEN,
                           "Content-Type": "audio/wav", "Content-Length": "1000001"})
        assert connection.getresponse().status == 413
        connection.close()
        server.slot.acquire()
        server.slot.acquire()
        try:
            with pytest.raises(ServerUnavailable, match="HTTP 503"):
                request_plan(url, TOKEN, text="bow")
        finally:
            server.slot.release()
            server.slot.release()


def test_real_provider_wire_contract_without_keys_or_network(catalog, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-not-a-key")
    provider = OpenAIProvider(catalog)
    calls = []

    def request(endpoint, body, content_type="application/json"):
        calls.append((endpoint, body, content_type))
        if endpoint == "audio/transcriptions":
            return {"text": "bow"}
        return {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps({"plan": catalog.plan([{"type": "rest"}]), "notes": []})}]}]}
    monkeypatch.setattr(provider, "request", request)
    assert provider.transcribe(wav()) == "bow"
    assert b"gpt-transcribe" in calls[0][1] and b'filename="prompt.wav"' in calls[0][1]
    provider.generate("bow")
    body = json.loads(calls[1][1])
    assert body["store"] is False and body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["properties"]["plan"] == catalog.schema()
    for response in ({"status": "incomplete"}, {"status": "completed", "output": [
        {"type": "message", "content": [{"type": "refusal", "refusal": "declined"}]}]},
        {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]}):
        monkeypatch.setattr(provider, "request", lambda *a, **k: response)
        with pytest.raises(ProviderError):
            provider.generate("bow")


def test_serial_grammar_modes_rate_clamp_and_stop(link, catalog):
    link.write("pose " + "90 " * 7 + "90")
    assert link.line(time.monotonic() + .5, tolerate_off=True) == "ERR arm run first"
    link.begin_lease(3)
    assert link.command("arm run", "OK ARMED") == "OK ARMED outputs OFF until target"
    assert link.status()[0]["outputs"] == "0"
    started = time.monotonic()
    link.command("servo R1 180", "OK TARGETS")
    time.sleep(.15)
    status, rows = link.status()
    channel = catalog.interface["joint_map"][0]["default_nvs_channel"]
    elapsed = time.monotonic() - started
    assert 90 < rows[channel][0] <= 90 + catalog.rate * elapsed + 1
    assert rows[channel][1] == 180
    link.command("stop", "OK STOP")
    _, rows = link.status()
    assert rows[channel][0] == rows[channel][1] and status["mode"] == "5"
    link.command("servo R1 0", "OK TARGETS")  # actual firmware clamps, unlike plan validator
    assert link.status()[1][channel][1] == 80
    link.write("pose 90 90 90 90 90 90 90 90 extra")
    assert link.line(time.monotonic() + .5, tolerate_off=True).startswith("ERR")
    link.device.write(b"x" * 160 + b"\n")
    assert link.line(time.monotonic() + .5, tolerate_off=True) == "ERR line too long (discarded)"


def test_watchdog_releases_outputs_without_any_host_heartbeat(link):
    link.command("arm run", "OK ARMED")
    link.command("pose 100 80 80 100 90 90 90 90", "OK TARGETS")
    start = time.monotonic()
    line = link.expect("OFF watchdog", start + 1.5, tolerate_off=True)
    assert line == "OFF watchdog >500ms"
    assert .45 <= time.monotonic() - start < 1.5
    assert_off(link)


def test_heartbeat_lease_cannot_keep_a_stalled_player_armed(link):
    link.command("arm run", "OK ARMED")
    link.command("pose 100 80 80 100 90 90 90 90", "OK TARGETS")
    link.begin_lease(.15)
    assert link.expect("OFF command", time.monotonic() + .5, tolerate_off=True) == "OFF command"
    assert link.failure is not None
    # failure stays latched; a new plan cannot silently resume.
    with pytest.raises(PlaybackError, match="lease expired"):
        link.begin_lease(1)


def test_player_http_to_custom_sequence_keeps_heartbeat_and_ends_off(link, catalog):
    logs = []
    plan = catalog.plan([{"type": "face", "name": "happy", "hold_ms": 100},
                         {"type": "pose", "angles": [100, 80, 80, 100, 100, 80, 100, 80],
                          "duration_ms": 900, "hold_ms": 100}, {"type": "rest"}])

    class Provider(FakeProvider):
        def generate(self, text):
            return plan, []
    with serving(catalog, Provider(catalog)) as (url, _):
        result = request_plan(url, TOKEN, text="make a custom movement")
        started = time.monotonic()
        Player(link, catalog, log=logs.append).play(result["plan"])
        assert time.monotonic() - started > 1
        assert any("complete" in line for line in logs)
        assert_off(link)


def test_stock_completion_is_not_confused_with_start_ack(link, catalog):
    started = time.monotonic()
    Player(link, catalog, log=lambda _: None).play(catalog.plan([{"type": "motion", "name": "stand"}]))
    assert 1.4 < time.monotonic() - started < 3
    assert_off(link)


@pytest.mark.parametrize("options,reason", [({"fresh": True}, "unverified"), ({"narrow": True}, "would clamp")])
def test_device_overlay_refusal_without_calibration_writes(catalog, options, reason):
    with SimulatedRobot(catalog, **options) as robot, SerialLink(robot.port) as link:
        link.off()
        with pytest.raises(PlaybackError, match=reason):
            Player(link, catalog).play(catalog.plan([{"type": "motion", "name": "stand"}]))
        assert_off(link)


def test_invalid_last_step_rejects_whole_plan_before_arm(link, catalog):
    sent = []
    original = link.write
    link.write = lambda command: (sent.append(command), original(command))[1]
    plan = catalog.plan([{"type": "rest"}, {"type": "face_bitmap"}])
    with pytest.raises(InvalidPlan, match="reserved"):
        Player(link, catalog).play(plan)
    assert "arm run" not in sent
    assert_off(link)


def test_server_down_still_offers_offline_keys(link, catalog):
    logs = []
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))  # bound but not listening; no external network
        controller = Controller(Player(link, catalog, log=logs.append),
                                f"http://127.0.0.1:{unavailable.getsockname()[1]}", TOKEN, log=logs.append,
                                requester=lambda *a, **k: request_plan(*a, **k, timeout=.25))
        try:
            assert controller.prompt(text="bow")
            wait_for(lambda: any("REQUEST FAILED" in line for line in logs))
            assert_off(link)
            controller.local("rest")
            wait_for(lambda: any("PLAY complete" in line for line in logs))
            wait_for(lambda: not controller.playing)
            assert_off(link)
        finally:
            controller.close()


def test_offline_preempts_slow_server_and_discards_late_plan(link, catalog):
    requested, release, returned = threading.Event(), threading.Event(), threading.Event()
    logs = []

    def delayed(*args, **kwargs):
        requested.set()
        assert release.wait(3)
        returned.set()
        return {"transcript": "late bow", "plan": catalog.plan([{"type": "motion", "name": "bow"}]), "notes": []}
    controller = Controller(Player(link, catalog, log=logs.append), "http://unused", TOKEN,
                            requester=delayed, log=logs.append)
    try:
        controller.prompt(text="bow")
        assert requested.wait(1)
        controller.local("stand")
        wait_for(lambda: any("PLAY complete" in line for line in logs))
        assert controller.network_busy  # local playback did not wait for network
        release.set()
        assert returned.wait(1)
        wait_for(lambda: not controller.network_busy and not controller.playing)
        assert not any('"name": "bow"' in line or "HEARD" in line for line in logs)
        assert_off(link)
    finally:
        release.set()
        controller.close()


def test_stop_cancels_local_playback(link, catalog):
    logs = []
    controller = Controller(Player(link, catalog, log=logs.append), "http://unused", TOKEN, log=logs.append)
    try:
        controller.local("bow")
        wait_for(lambda: any('"name": "bow"' in line for line in logs))
        started = time.monotonic()
        controller.stop()
        wait_for(lambda: not controller.playing)
        assert time.monotonic() - started < .5
        assert_off(link)
    finally:
        controller.close()


def test_press_release_repeat_and_offline_cancel_audio(link, catalog):
    logs, sent = [], []
    controller = Controller(Player(link, catalog, log=logs.append), "http://unused", TOKEN, log=logs.append)
    controller.prompt = lambda **kwargs: sent.append(kwargs)

    class Audio:
        starts = 0
        finishes = []

        def start(self):
            self.starts += 1

        def finish(self, *, discard=False):
            self.finishes.append(discard)
            return None if discard else wav()
    audio = Audio()
    ptt = PushToTalk(controller, audio, log=logs.append)
    try:
        ptt.edge(True)
        ptt.edge(True)
        ptt.edge(False)
        assert audio.starts == 1 and len(sent) == 1 and sent[0]["audio"] == wav()
        ptt.edge(True)
        ptt.key("3")
        assert audio.finishes[-1] is True
        wait_for(lambda: any("PLAY complete" in line for line in logs))
    finally:
        controller.close()


def test_recorder_subprocess_is_bounded_and_memory_only():
    recorder = Recorder()
    recorder.command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\0' * 960000)"]
    recorder.start()
    recorder.process.wait(timeout=3)
    audio = recorder.finish()
    assert len(audio) == 960044
    check_wav(audio)
    assert recorder.process is None and recorder.data == bytearray()


def test_linux_event_decoder_with_separate_button_and_keyboard(monkeypatch):
    button_r, button_w = os.pipe()
    keyboard_r, keyboard_w = os.pipe()
    devices = {"button": button_r, "keyboard": keyboard_r}
    monkeypatch.setattr(inputs, "open", lambda path, *a, **k: os.fdopen(os.dup(devices[path]), "rb", buffering=0), raising=False)
    finish, events, errors = threading.Event(), [], []

    class PTT:
        def edge(self, pressed):
            events.append(("edge", pressed))

        def key(self, key):
            events.append(("key", key))

    def run():
        try:
            inputs.linux_inputs(PTT(), ["button", "keyboard"], finish=finish)
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        pack = lambda code, value: inputs.INPUT_EVENT.pack(0, 0, 1, code, value)
        os.write(button_w, pack(57, 1) + pack(57, 2) + pack(57, 0))
        wait_for(lambda: len(events) == 2)
        os.write(keyboard_w, pack(2, 1) + pack(2, 0))
        wait_for(lambda: len(events) == 3)
        assert events == [("edge", True), ("edge", False), ("key", "1")]
        assert not errors
    finally:
        finish.set()
        thread.join(timeout=1)
        for fd in (button_r, button_w, keyboard_r, keyboard_w):
            os.close(fd)


@pytest.mark.skipif(sys.platform != "linux", reason="GPIO is an optional Linux-only backend")
def test_gpio_optional_dependency_configuration():
    gpiod = pytest.importorskip("gpiod")
    from datetime import timedelta
    from gpiod.line import Bias, Edge
    settings = gpiod.LineSettings(edge_detection=Edge.BOTH, bias=Bias.PULL_UP,
                                  debounce_period=timedelta(milliseconds=20))
    assert settings.edge_detection == Edge.BOTH
    assert settings.debounce_period.total_seconds() == .02
