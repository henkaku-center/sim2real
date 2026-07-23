"""Schema and consistency checks for manifest/robot.yaml (the canonical contract).

These tests exist to catch the most likely early bugs: joint-order mismatches,
degrees/radians confusion, and pin-map drift from the firmware ground truth.
"""

from pathlib import Path

import pytest
import yaml

MANIFEST_PATH = Path(__file__).parent.parent / "manifest" / "robot.yaml"

# Ground truth from dorianborian/sesame-robot firmware (Apache-2.0):
# movement-sequences.h enum order and sesame-firmware-main.ino S2 Mini pins.
FIRMWARE_CHANNEL_ORDER = ["R1", "R2", "L1", "L2", "R4", "R3", "L3", "L4"]
S2_MINI_PINS = [1, 2, 4, 6, 8, 10, 13, 14]


@pytest.fixture(scope="module")
def manifest():
    with open(MANIFEST_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def joints(manifest):
    return manifest["joints"]


def test_top_level_keys(manifest):
    for key in ("schema_version", "robot", "conventions", "servo_bus",
                "servo_model", "joints", "calibration", "poses"):
        assert key in manifest, f"missing top-level key: {key}"
    assert manifest["schema_version"] == 1
    assert manifest["robot"] == "sesame"


def test_eight_joints_in_firmware_channel_order(joints):
    assert len(joints) == 8
    names = [j["name"] for j in joints]
    assert names == FIRMWARE_CHANNEL_ORDER, (
        "joint list order must match the firmware servo channel enum"
    )
    assert [j["channel"] for j in joints] == list(range(8)), (
        "channel field must equal list index"
    )


def test_pin_map_matches_s2_mini_baseline(joints):
    assert [j["gpio_pin"] for j in joints] == S2_MINI_PINS


def test_leg_and_role_cover_the_quadruped(joints):
    legs = {(j["leg"], j["role"]) for j in joints}
    expected = {
        (leg, role)
        for leg in ("front_left", "front_right", "back_left", "back_right")
        for role in ("hip", "foot")
    }
    assert legs == expected, "each of 4 legs needs exactly one hip and one foot"
    # Naming convention: 1/2 are hips, 3/4 are feet; L*/R* match leg side.
    for j in joints:
        side = "left" if j["name"].startswith("L") else "right"
        assert side in j["leg"]
        assert j["role"] == ("hip" if j["name"][1] in "12" else "foot")


def test_limits_are_sane(joints):
    for j in joints:
        lo, hi = j["limits_deg"]
        assert 0 <= lo < hi <= 180, f"{j['name']}: bad limits {lo}..{hi}"


def test_signs_mirror_left_right(joints):
    for j in joints:
        assert j["sign"] in (-1, 1)
        expected = -1 if j["name"].startswith("L") else 1
        assert j["sign"] == expected, f"{j['name']}: sign convention broken"


def test_servo_bus(manifest):
    bus = manifest["servo_bus"]
    assert bus["pwm_hz"] == 50
    lo, hi = bus["pulse_us"]
    assert lo == 732 and hi == 2929, "must match firmware attach(pin, 732, 2929)"
    assert bus["angle_range_deg"] == [0, 180]


def test_servo_model_marked_unmeasured(manifest):
    sm = manifest["servo_model"]
    assert sm["type"] == "MG90S"
    assert sm["status"] == "unmeasured-nominal", (
        "nominal values must stay flagged until physically measured"
    )
    assert 0 < sm["mass_kg"] < 0.05
    assert 0 < sm["stall_torque_Nm_at_4v8"] < 1.0


def test_calibration_covers_all_joints(manifest, joints):
    subtrim = manifest["calibration"]["subtrim_deg"]
    assert set(subtrim) == {j["name"] for j in joints}
    for name, val in subtrim.items():
        assert -128 <= val <= 127, f"{name}: subtrim must fit int8_t"


def test_poses_within_limits(manifest, joints):
    limits = {j["name"]: j["limits_deg"] for j in joints}
    poses = manifest["poses"]
    for pose_name in ("rest", "stand"):
        pose = poses[pose_name]
        assert set(pose) == set(limits), f"{pose_name}: must specify all 8 joints"
        for jname, deg in pose.items():
            lo, hi = limits[jname]
            assert lo <= deg <= hi, f"{pose_name}.{jname}={deg} outside [{lo},{hi}]"


def test_known_pose_values(manifest):
    # Ground truth from movement-sequences.h runRestPose / runStandPose.
    assert all(v == 90 for v in manifest["poses"]["rest"].values())
    assert manifest["poses"]["stand"] == {
        "R1": 135, "R2": 45, "L1": 45, "L2": 135,
        "R4": 0, "R3": 180, "L3": 0, "L4": 180,
    }


def test_neutral_maps_to_zero_radians(manifest):
    assert manifest["conventions"]["firmware_neutral_deg"] == 90
