"""Run log schema, recorder and simulated firmware (no hardware)."""

import copy
import json

import pytest

from sim.manifest import load_manifest
from sim.real2sim import recorder, runlog


@pytest.fixture(scope="module")
def dry():
    return recorder.dry_run("lift")


def _with_pose(header, records):
    header = copy.deepcopy(header)
    header["clocks"]["video"] = "seconds since the first frame"
    header["clocks"]["device"] = "device milliseconds / 1000"
    header["channels"] = {
        "torso_pose": runlog.torso_pose_channel(frame="camera", frame_definition="test",
                                                marker_origin_in_torso_m=[0, 0, 0.019]),
        "imu": {"frame": "imu chip axes", "accel_unit": "m/s^2", "gyro_unit": "rad/s"},
    }
    poses = runlog.pose_records([0.0, 0.02], [[0.1, 0.2, 0.3]] * 2, [[2.0, 0, 0, 0]] * 2)
    imu = [{"type": "imu", "t": 0.01, "clock": "device", "accel_m_s2": [0, 0, 9.81], "gyro_rad_s": [0, 0, 0]}]
    return header, records + poses + imu


def test_dry_run_log_is_valid_and_round_trips(dry, tmp_path):
    header, records = _with_pose(*dry)
    path = runlog.write(tmp_path / "run.jsonl", header, records)
    log = runlog.load(path)
    assert log.evidence == "dry-run" and log.header["version"] == runlog.VERSION
    assert log.joints == [j.name for j in load_manifest().joints]
    assert log.pose_position.shape == (2, 3) and log.imu_accel.shape == (1, 3)
    assert abs(log.pose_quaternion[0, 0] - 1.0) < 1e-9, "pose_records must normalise quaternions"
    assert json.loads(path.read_text().splitlines()[0])["type"] == "header"
    assert log.header["command_interface"]["slew_rate_deg_s"] == 60.0  # manifest controller_rate_deg_s


@pytest.mark.parametrize("mutate, message", [
    (lambda h, r: h.update(version=2), "unsupported version"),
    (lambda h, r: h.update(evidence="real"), "evidence must be"),
    (lambda h, r: h["command_interface"].pop("slew_rate_deg_s"), "slew_rate_deg_s is required"),
    (lambda h, r: h["channels"].pop("torso_pose"), "channel torso_pose is not declared"),
    (lambda h, r: h["channels"]["torso_pose"].pop("frame"), "must state its frame"),
    (lambda h, r: r.append({"type": "command", "t": 99.0, "clock": "host", "text": "pose", "targets_deg": {"X9": 90}}),
     "unknown joint"),
    (lambda h, r: r.append({"type": "command", "t": 99.0, "clock": "host", "text": "pose", "targets_deg": {"R1": 181}}),
     "0..180 firmware degrees"),
    (lambda h, r: r.append({"type": "reply", "t": 0.0, "clock": "host", "text": "late"}), "goes backwards"),
    (lambda h, r: r.append({"type": "reply", "t": 99.0, "clock": "wall", "text": "x"}), "not declared in the header"),
    (lambda h, r: r.append({"type": "torso_pose", "t": 9.0, "clock": "video", "position_m": [0, 0, 0],
                            "quaternion_wxyz": [1, 1, 0, 0]}), "unit length"),
    (lambda h, r: r.append({"type": "torso_pose", "t": 9.0, "clock": "video", "position_m": [0, float("nan"), 0],
                            "quaternion_wxyz": [1, 0, 0, 0]}), "3 finite numbers"),
    (lambda h, r: r.append({"type": "telemetry", "t": 1.0, "clock": "host"}), "type must be one of"),
])
def test_validator_rejects_violations(dry, mutate, message):
    header, records = _with_pose(*copy.deepcopy(dry))
    assert runlog.validate(header, records) == []
    mutate(header, records)
    errors = runlog.validate(header, records)
    assert any(message in error for error in errors), errors
    with pytest.raises(runlog.RunLogError):
        runlog.from_records(header, records)


def test_recorder_speaks_the_firmware_console(dry):
    header, records = dry
    texts = [r["text"] for r in records if r["type"] == "command"]
    assert texts[:2] == ["export", "arm run"] and texts[-1] == "off"
    assert "heartbeat" not in texts and header["recorder"]["heartbeats_sent"] > 80
    replies = [r["text"] for r in records if r["type"] == "reply"]
    assert any(t.startswith('{"version":1') for t in replies), "export reply is logged"
    assert "OK ARMED outputs OFF until target" in replies and "OK OFF" in replies
    assert not header["recorder"]["device_errors"] and not header["recorder"]["clamped_deg"]
    log = runlog.from_records(header, records)
    targets = log.targets()
    rest, stand = load_manifest().raw["poses"]["rest"], load_manifest().raw["poses"]["stand"]
    assert targets[0][1] == rest, "every run starts from the rest preamble"
    assert targets[1][1] == stand
    assert targets[1][0] - targets[0][0] == pytest.approx(recorder.PREAMBLE_REST_S, abs=0.02)
    # Firmware-like timing: the 90 degree move to stand takes 1.5 s at 60 deg/s before the 1.0 s hold starts.
    assert targets[2][0] - targets[1][0] == pytest.approx(1.5 + 1.0, abs=0.02)
    assert max(len(t.encode()) for t in texts) <= recorder.MAX_LINE_BYTES


def test_all_sequences_stay_inside_manifest_limits():
    manifest = load_manifest()
    for name in recorder.sequence_names(manifest):
        for event in recorder.sequence_events(name, manifest):
            for joint, degrees in event.targets_deg.items():
                low, high = manifest.joint(joint).limits_deg
                assert low <= degrees <= high, (name, joint, degrees)


def test_uncalibrated_device_refuses_and_nothing_is_logged_as_a_run():
    clock = recorder.FakeClock()
    firmware = recorder.SimulatedFirmware(clock=clock, calibrated=False)
    with pytest.raises(recorder.RecorderError, match="did not arm.*verified"):
        recorder.record(firmware, "lift", clock=clock, sleep=clock.sleep)
    assert not firmware.armed


def test_device_limits_clamp_targets_and_the_log_says_so():
    clock = recorder.FakeClock()
    firmware = recorder.SimulatedFirmware(clock=clock, limits_deg={"R3": (85.0, 95.0)})
    header, records = recorder.record(firmware, "stand", clock=clock, sleep=clock.sleep)
    assert header["recorder"]["clamped_deg"] == {"R3": [180.0, 95.0]}
    log = runlog.from_records(header, records)
    assert log.targets()[-1][1]["R3"] == 95.0, "the log holds the effective target"


def test_simulated_firmware_ramp_and_watchdog():
    clock = recorder.FakeClock()
    firmware = recorder.SimulatedFirmware(clock=clock)
    firmware.write("arm run")
    firmware.write("pose 135 45 45 135 0 180 0 180")
    assert firmware.read_lines() == ["OK ARMED outputs OFF until target",
                                     "OK TARGETS (soft/measured/electrical clamps applied)"]
    clock.sleep(0.25)
    firmware.write("heartbeat")
    assert firmware.current["R3"] == pytest.approx(90 + 60 * 0.25)  # 60 deg/s ramp from neutral
    clock.sleep(0.6)  # no heartbeat for more than 500 ms
    assert firmware.read_lines() == ["OFF watchdog >500ms"] and not firmware.armed
    firmware.write("pose 90 90 90 90 90 90 90 90")
    assert firmware.read_lines() == ["ERR arm run first"]


def test_missed_heartbeats_abort_the_recording():
    clock = recorder.FakeClock()
    firmware = recorder.SimulatedFirmware(clock=clock)
    with pytest.raises(recorder.RecorderError, match="released the outputs"):
        recorder.record(firmware, "lift", clock=clock, sleep=clock.sleep, heartbeat_s=0.7)


def test_line_transport_frames_lines_and_bounds_length():
    class Device:
        def __init__(self):
            self.sent, self.incoming, self.closed = [], [b"OK ARM", b"ED\r\nCH4 cur", b"rent=90.00\n"], False

        def write(self, data):
            self.sent.append(data)

        def read(self, size):
            return self.incoming.pop(0) if self.incoming else b""

        def close(self):
            self.closed = True

    device = Device()
    transport = recorder.LineTransport(device)
    transport.write("arm run")
    assert device.sent == [b"arm run\n"]
    assert transport.read_lines() == [] and transport.read_lines() == ["OK ARMED"]
    assert transport.read_lines() == ["CH4 current=90.00"]
    with pytest.raises(recorder.RecorderError):
        transport.write("x" * 160)
    transport.close()
    assert device.closed
