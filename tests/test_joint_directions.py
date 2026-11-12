"""Joint directions: the manifest's typed table, its signs, the generated twins
and the leg-clearance evidence must tell the same story.

The table is what the instructor confirmed on a built robot on 2026-11-12
(DECISIONS.md D24). Everything computed here is CAD or simulation; no device.
A hip turns in the horizontal plane and, once its leg is fitted, one way only
from Rest. A foot swings in a vertical plane.
"""
import json
from pathlib import Path
import sys

import mujoco
import numpy as np
import pytest
import yaml

from sim import twin
from sim.manifest import load_manifest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import leg_clearance as lc  # noqa: E402

DESIGNS = ["internal-frame-s3", "internal-frame-s3-two-eyes"]
# Instructor-confirmed, firmware degrees: (points at 0, at 90, at 180), fitted travel.
CONFIRMED = {
    "L1": (("forward", "out_left", "back"), [0, 90]),      # front-left hip: 90 -> 0, forward only
    "R1": (("back", "out_right", "forward"), [90, 180]),   # front-right hip: 90 -> 180, forward only
    "L2": (("forward", "out_left", "back"), [90, 180]),    # rear-left hip: 90 -> 180, backward only
    "R2": (("back", "out_right", "forward"), [0, 90]),     # rear-right hip: 90 -> 0, backward only
    "L3": (("down", "out", "up"), [0, 180]),
    "R3": (("up", "out", "down"), [0, 180]),
    "L4": (("up", "out", "down"), [0, 180]),
    "R4": (("down", "out", "up"), [0, 180]),
}
HIP_WORDS, FOOT_WORDS = {"forward", "back", "out_left", "out_right"}, {"down", "up", "out"}


@pytest.fixture(scope="module")
def raw():
    return yaml.safe_load((ROOT / "manifest/robot.yaml").read_text())


@pytest.fixture(scope="module")
def manifest():
    return load_manifest()


def typed(raw):
    return {j["name"]: (tuple(j["points_at_deg"][deg] for deg in (0, 90, 180)), j["fitted_travel_deg"])
            for j in raw["joints"]}


def hip_word(vector):
    """Horizontal direction of a leg in the body frame: X forward, Y left."""
    x, y = float(vector[0]), float(vector[1])
    assert abs(float(vector[2])) < 0.2 * np.hypot(x, y), "a hip leaves the horizontal plane"
    if abs(x) > abs(y):
        return "forward" if x > 0 else "back"
    return "out_left" if y > 0 else "out_right"


def foot_word(vector):
    unit = np.asarray(vector, float) / np.linalg.norm(vector)
    if abs(unit[2]) > 0.7:
        return "down" if unit[2] < 0 else "up"
    assert abs(unit[2]) < 0.2, "a foot is neither level nor vertical at a quarter turn"
    return "out"


def test_manifest_holds_the_confirmed_table(raw):
    assert typed(raw) == {name: (points, travel) for name, (points, travel) in CONFIRMED.items()}
    assert raw["conventions"]["firmware_neutral_deg"] == 90
    for joint in raw["joints"]:
        points, (low, high) = joint["points_at_deg"], joint["fitted_travel_deg"]
        assert set(points) == {0, 90, 180}
        assert set(points.values()) <= (HIP_WORDS if joint["role"] == "hip" else FOOT_WORDS)
        soft_low, soft_high = joint["limits_deg"]
        assert soft_low <= low <= 90 <= high <= soft_high, joint["name"]
        if joint["role"] == "hip":
            # One way only from Rest, 90 degrees in all, straight out at Rest on its own side.
            assert sorted((low, high)) in ([0, 90], [90, 180])
            assert points[90] == ("out_left" if "left" in joint["leg"] else "out_right")
            # The soft limits add only the 10 degrees the stock walk and point use on the other side.
            assert (low - soft_low, soft_high - high) in ((0, 10), (10, 0)), joint["name"]
        else:
            assert (low, high) == (0, 180) == (soft_low, soft_high) and points[90] == "out"


def test_signs_agree_with_the_typed_directions(raw, manifest):
    """Positive internal q: a hip turns toward its own end of the body, a foot swings down."""
    for joint in manifest.joints:
        points, (low, high) = raw["joints"][joint.channel]["points_at_deg"], raw["joints"][joint.channel]["fitted_travel_deg"]
        positive = round(manifest.to_firmware(joint, np.pi / 2))   # firmware degrees at q = +90
        negative = round(manifest.to_firmware(joint, -np.pi / 2))
        assert {positive, negative} == {0, 180}
        if joint.role == "hip":
            own_end = "forward" if "front" in joint.leg else "back"
            assert points[positive] == own_end, joint.name
            assert points[negative] == ("back" if own_end == "forward" else "forward")
            # The fitted sweep is the positive-q side of Rest, never the other.
            assert sorted((90, positive)) == [low, high], joint.name
        else:
            assert (points[positive], points[negative]) == ("down", "up"), joint.name
    # Standing is positive on every joint: hips out to their ends, feet down.
    stand = raw["poses"]["stand"]
    for joint in manifest.joints:
        assert manifest.to_internal(joint, stand[joint.name]) > 0
        low, high = raw["joints"][joint.channel]["fitted_travel_deg"]
        assert low <= stand[joint.name] <= high


@pytest.mark.parametrize("name", DESIGNS + [twin.LEGACY_UPSTREAM])
def test_generated_models_point_where_the_manifest_says(raw, manifest, name):
    model = twin.load_model(name)
    data = mujoco.MjData(model)
    torso = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "torso")
    joint_id = lambda joint: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
    for joint in manifest.joints:
        hip = next(j for j in manifest.joints if j.leg == joint.leg and j.role == "hip")
        foot = next(j for j in manifest.joints if j.leg == joint.leg and j.role == "foot")
        seen = []
        for deg in (0, 90, 180):
            mujoco.mj_resetData(model, data)
            data.qpos[model.jnt_qposadr[joint_id(joint.name)]] = manifest.to_internal(joint, deg)
            mujoco.mj_forward(model, data)
            frame = data.xmat[torso].reshape(3, 3)
            hip_axis, foot_axis = data.xanchor[joint_id(hip.name)], data.xanchor[joint_id(foot.name)]
            if joint.role == "hip":
                seen.append(hip_word(frame.T @ (foot_axis - hip_axis)))
            else:
                lower = model.jnt_bodyid[joint_id(foot.name)]
                seen.append(foot_word(frame.T @ (data.xipos[lower] - foot_axis)))
        assert tuple(seen) == typed(raw)[joint.name][0], (name, joint.name)


@pytest.mark.parametrize("design", DESIGNS)
def test_leg_clearance_free_side_is_the_fitted_travel(raw, design):
    """The side with the whole 90 degrees clear of the head cover is the side a fitted hip turns to."""
    evidence = json.loads((ROOT / lc.PRINTING / design / lc.EVIDENCE).read_text())
    assert lc.verify(ROOT / lc.PRINTING / design)["fresh"]
    table = typed(raw)
    for name, hip in evidence["hips"].items():
        points, (low, high) = table[name]
        free, blocked = hip["toward_end"], hip["toward_middle"]
        far = low if free["servo_direction"] == "decreasing" else high
        assert far in (0, 180) and sorted((90, far)) == [low, high], name
        assert points[(0, 90, 180).index(far)] == {"front": "forward", "rear": "back"}[free["body_direction"]]
        # The other side meets the head cover after about 13 degrees: not a side to sweep.
        assert blocked["servo_direction"] != free["servo_direction"]
        assert blocked["partner"] == "head-cover" and blocked["first_contact_deg"] < 15
        assert "head-cover" not in [band["partner"] for band in hip["contact_bands"]
                                    if low < band["servo_deg"][1] and band["servo_deg"][0] < high]
    for name, foot in evidence["feet"].items():
        assert foot["free_servo_deg"] == table[name][1] == [0, 180]


def test_leg_clearance_placement_points_where_the_manifest_says(raw):
    import trimesh
    assembly = json.loads((ROOT / lc.PRINTING / DESIGNS[0] / "assembly.json").read_text())
    meshes = {name: trimesh.load(ROOT / lc.LEGS / f"{name}-v117.stl", process=False, force="mesh")
              for hip, foot in lc.PRINTS.items() for name in (hip, foot)}
    table = typed(raw)
    for hip, foot in lc.PRINTS.items():
        leg = lc.Leg(hip, assembly, meshes)
        hips, feet = [], []
        # With the hip at Rest the foot axis lies along body X, through this point.
        axis = trimesh.transform_points([leg.foot_centre], leg.transform(90))[0]
        paddle = meshes[foot].bounds.mean(0)   # middle of the foot print, in its drawing frame
        for deg in (0, 90, 180):
            centre = trimesh.transform_points(meshes[hip].vertices, leg.transform(deg)).mean(0)
            hips.append(hip_word([centre[0] - leg.hx, centre[1] - leg.hy, 0.0]))
            offset = trimesh.transform_points([paddle], leg.transform(90, deg))[0] - axis
            feet.append(foot_word([0.0, offset[1], offset[2]]))
        assert tuple(hips) == table[hip][0] and tuple(feet) == table[foot][0], (hip, foot)


def test_stock_motions_keep_fitted_hips_on_their_side_except_the_known_ten_degrees(raw):
    """Upstream walk and point put R2 at 100: the one place a stock target leaves the fitted sweep."""
    motions = yaml.safe_load((ROOT / "manifest/motions.yaml").read_text())
    outside = set()
    for motion, steps in motions["motions"].items():
        for targets in lc._expand(steps, raw["poses"]):
            for name, value in targets.items():
                low, high = raw["joints"][[j["name"] for j in raw["joints"]].index(name)]["fitted_travel_deg"]
                if not low <= value <= high:
                    outside.add((motion, name, value))
    assert outside == {("walk", "R2", 100), ("point", "R2", 100)}
