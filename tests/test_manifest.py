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
# The S2 Mini is the historical upstream baseline, not the course board.
FIRMWARE_CHANNEL_ORDER = ["R1", "R2", "L1", "L2", "R4", "R3", "L3", "L4"]
S2_MINI_PINS = [1, 2, 4, 6, 8, 10, 13, 14]
# Hip soft limits for the course body: 10 degrees toward the middle, 90 toward
# the ends (CAD-derived leg clearance, DECISIONS.md D21 and D24).
COURSE_HIP_LIMITS = {"R1": [80, 180], "R2": [0, 100], "L1": [0, 100], "L2": [80, 180]}


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


def test_course_board_is_named_and_s2_facts_are_labelled_historical(manifest):
    mcu = manifest["mcu"]
    assert (mcu["board"], mcu["servo_driver"]) == ("esp32_s3_supermini", "pca9685")
    assert "sesame_s3" in manifest["hardware_profiles"]
    assert mcu["upstream_baseline"] == {"status": "historical-upstream-baseline",
                                        "board": "lolin_esp32_s2_mini", "servo_driver": "direct-gpio-pwm"}
    assert manifest["servo_bus"]["pulse_us_status"] == "historical-upstream-baseline"
    # Each S2 pin carries its label on the same line, wherever a reader lands.
    lines = [line for line in MANIFEST_PATH.read_text().splitlines() if line.strip().startswith("gpio_pin:")]
    assert len(lines) == 8 and all("historical upstream S2 Mini pin" in line for line in lines)


def test_hip_limits_are_the_course_body_values(manifest, joints):
    assert {j["name"]: j["limits_deg"] for j in joints if j["role"] == "hip"} == COURSE_HIP_LIMITS
    assert all(j["limits_deg"] == [0, 180] for j in joints if j["role"] == "foot")
    # Calibration saved under the identity these limits replaced stays readable.
    assert manifest["hardware_profiles"]["sesame_s3"]["calibration_compatible_manifest_ids"] == [
        "e669b916d178ac0a", "bd7675604b98ae46", "8d75c0ea0b2c68e7"]


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


def test_signs_encode_point_symmetric_servo_mounting(joints):
    # From the upstream angle guide: the positive direction is 90->180 for
    # {R1,L2,R3,L4} but 90->0 for {R2,L1,R4,L3}. Positive internal q turns a hip
    # toward its own end of the body, in the horizontal plane, and swings a foot
    # down. tests/test_joint_directions.py checks that against the typed table.
    for j in joints:
        assert j["sign"] in (-1, 1)
        expected = 1 if j["leg"] in ("front_right", "back_left") else -1
        assert j["sign"] == expected, f"{j['name']}: sign convention broken"


def test_internal_ranges_identical_per_role(joints):
    # With correct signs, all hips (and all feet) share one internal range.
    def internal_range(j):
        lo, hi = j["limits_deg"]
        a, b = (lo - 90) * j["sign"], (hi - 90) * j["sign"]
        return (min(a, b), max(a, b))

    for role, expected in (("hip", (-10, 90)), ("foot", (-90, 90))):
        for j in joints:
            if j["role"] == role:
                assert internal_range(j) == expected, (
                    f"{j['name']}: {role} internal range mismatch"
                )


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
