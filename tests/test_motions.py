"""Schema and playback checks for manifest/motions.yaml (stock motion library)."""

import numpy as np
import pytest

from sim.manifest import load_manifest
from sim.motions import ctrl_schedule, duration_ms, flatten, load_motions, play_native

UPSTREAM_MOTION_COUNT = 19  # movement-sequences.h pose/animation inventory


@pytest.fixture(scope="module")
def manifest():
    return load_manifest()


@pytest.fixture(scope="module")
def doc():
    return load_motions()


def _walk(steps):
    for step in steps:
        yield step
        if "repeat" in step:
            yield from _walk(step["repeat"]["steps"])


def test_all_upstream_motions_present(doc):
    assert len(doc["motions"]) == UPSTREAM_MOTION_COUNT
    for expected in ("rest", "stand", "wave", "walk", "walk_backward",
                     "turn_left", "turn_right", "pushup", "dance", "dead"):
        assert expected in doc["motions"]


def test_steps_are_well_formed(doc, manifest):
    joint_names = {j.name for j in manifest.joints}
    pose_names = set(manifest.raw["poses"])
    for name, steps in doc["motions"].items():
        for step in _walk(steps):
            keys = set(step) & {"pose", "set", "wait", "repeat"}
            assert len(keys) == 1, f"{name}: step must have exactly one action: {step}"
            if "pose" in step:
                assert step["pose"] in pose_names
            elif "set" in step:
                assert set(step["set"]) <= joint_names, f"{name}: unknown joint"
            elif "wait" in step:
                assert 0 < step["wait"] <= 10_000
            elif "repeat" in step:
                assert 1 <= step["repeat"]["count"] <= 100


def test_targets_within_soft_limits(doc, manifest):
    limits = {j.name: j.limits_deg for j in manifest.joints}
    for name, steps in doc["motions"].items():
        for step in _walk(steps):
            for jname, deg in step.get("set", {}).items():
                lo, hi = limits[jname]
                assert lo <= deg <= hi, (
                    f"{name}: {jname}={deg}° outside soft limits [{lo},{hi}]"
                )


def test_flatten_wave(doc, manifest):
    events = flatten(doc["motions"]["wave"], manifest.raw["poses"])
    assert events[0].time_ms == 0.0
    assert events[0].targets_deg["R1"] == 135  # stand pose applied at t=0
    assert duration_ms(events) == pytest.approx(200 + 200 + 300 + 4 * 600)
    # schedule maps to channels and internal radians monotonically
    schedule = ctrl_schedule(events, manifest, 0.002)
    steps = [s for s, _, _ in schedule]
    assert steps == sorted(steps)
    assert all(0 <= c < 8 for _, c, _ in schedule)


def test_walk_moves_forward():
    _, data = play_native("walk")
    assert np.all(np.isfinite(data.qpos))
    assert data.qpos[0] > 0.05, "walk should translate the robot along +x"


def test_walk_backward_moves_backward():
    _, data = play_native("walk_backward")
    assert data.qpos[0] < -0.05, "walk_backward should translate along -x"


def test_turns_rotate():
    for name in ("turn_left", "turn_right"):
        _, data = play_native(name)
        yaw_deg = abs(np.degrees(2 * np.arctan2(data.qpos[6], data.qpos[3])))
        assert yaw_deg > 45, f"{name} should rotate the torso substantially"


def test_wave_returns_to_stand():
    _, data = play_native("wave")
    assert data.qpos[2] > 0.04, "robot should end standing"
    assert abs(data.qpos[0]) < 0.05 and abs(data.qpos[1]) < 0.05, (
        "wave should not translate the robot"
    )


def test_wave_paw_stays_off_the_ground():
    # Regression: with placeholder kinematics the "waving" L3 paw repeatedly
    # hit the floor. With STL-measured geometry it must wave in the air.
    import mujoco

    from sim.build_mjcf import MODEL_PATH
    from sim.manifest import load_manifest
    from sim.motions import flatten, load_motions

    man = load_manifest()
    doc = load_motions()
    events = flatten(doc["motions"]["wave"], man.raw["poses"])
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    sched = ctrl_schedule(events, man, model.opt.timestep)
    lower = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "front_left_lower")
    tip_local = np.array([0, 0.047, 0])
    i, min_tip = 0, np.inf
    for step in range(sched[-1][0]):
        while i < len(sched) and sched[i][0] <= step:
            data.ctrl[sched[i][1]] = sched[i][2]
            i += 1
        mujoco.mj_step(model, data)
        if step * model.opt.timestep * 1000 >= 700:  # during the waving loop
            tip = data.xpos[lower] + data.xmat[lower].reshape(3, 3) @ tip_local
            min_tip = min(min_tip, tip[2])
    assert min_tip > 0.02, f"waving paw dipped to {min_tip:.4f} m — hitting the ground"


def test_playback_is_deterministic():
    a = play_native("pushup")[1].qpos.copy()
    b = play_native("pushup")[1].qpos.copy()
    assert np.array_equal(a, b)
