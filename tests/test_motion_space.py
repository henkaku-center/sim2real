"""manifest/motion_space.yaml: the eight-axis motion space must match MuJoCo."""

import itertools
import math

import mujoco
import numpy as np
import pytest

from sim.motion_space import (
    AXES,
    LEGS,
    Settler,
    axis_range,
    decode,
    feasible,
    firmware_pose,
    gait,
    load_space,
    project,
    tilt_limit,
    within_budget,
)


@pytest.fixture(scope="module")
def settler():
    return Settler()


def _random_feasible(n, seed):
    """Feasible standing poses (lift is a gait axis, so it stays 0)."""
    space, rng = load_space(), np.random.default_rng(seed)
    lo = np.array([space["ranges"][a][0] for a in AXES], dtype=float)
    hi = np.array([space["ranges"][a][1] for a in AXES], dtype=float)
    lo[AXES.index("lift")] = hi[AXES.index("lift")] = 0.0
    out = []
    while len(out) < n:
        z = dict(zip(AXES, rng.uniform(lo, hi)))
        if feasible(z):
            out.append(z)
    return out


def _paw_bottoms(s):
    """World z of each paddle's lowest corner (m)."""
    out = []
    for leg in LEGS:
        g = mujoco.mj_name2id(s.model, mujoco.mjtObj.mjOBJ_GEOM, f"{leg}_lower_geom")
        rot, size = s.data.geom_xmat[g].reshape(3, 3), s.model.geom_size[g]
        out.append(min((s.data.geom_xpos[g] + rot @ (size * c))[2]
                       for c in itertools.product((-1, 1), repeat=3)))
    return np.array(out)


def test_centre_is_feasible_and_matches_stand_hips():
    q = decode({})
    assert feasible({})
    assert [q[n] for n in ("R1", "R2", "L1", "L2")] == [45, 45, 45, 45]
    assert all(40 < q[n] < 50 for n in ("R3", "R4", "L3", "L4"))


def test_firmware_pose_is_channel_ordered_degrees():
    fw = firmware_pose({})
    assert len(fw) == 8 and fw[:4] == pytest.approx([135, 45, 45, 135])


def test_inverse_kinematics_puts_every_paw_on_the_floor(settler):
    for z in _random_feasible(25, seed=1):
        settler.place(decode(z), z["pitch"], z["roll"])
        paws = _paw_bottoms(settler)
        assert paws == pytest.approx([paws.min()] * 4, abs=3e-4), z


def test_lift_raises_the_named_diagonal(settler):
    settler.place(decode({"lift": 10}))
    fr, fl, br, bl = _paw_bottoms(settler) - _paw_bottoms(settler).min()
    assert fr == pytest.approx(0.010, abs=5e-4) and bl == pytest.approx(0.010, abs=5e-4)
    assert fl == pytest.approx(0, abs=5e-4) and br == pytest.approx(0, abs=5e-4)


@pytest.mark.parametrize("axis,legs", [
    ("surge", (1, 1, 1, 1)), ("spread", (1, 1, -1, -1)),
    ("yaw", (1, -1, 1, -1)), ("stride", (1, -1, -1, 1)),
])
def test_hip_axes_sweep_paws_as_documented(settler, axis, legs):
    def paws_x(z):
        settler.place(decode(z))
        torso = settler.data.xpos[settler.torso][0]
        return np.array([settler.data.site_xpos[mujoco.mj_name2id(
            settler.model, mujoco.mjtObj.mjOBJ_SITE, f"{leg}_paw")][0] - torso for leg in LEGS])
    moved = paws_x({axis: 10}) - paws_x({})
    assert np.sign(moved).tolist() == list(legs)


def test_feasible_poses_have_no_self_collision(settler):
    for z in _random_feasible(200, seed=2):
        settler.place(decode(z))
        settler.data.qpos[2] += 0.2  # lift off the floor; only leg-leg contacts remain
        mujoco.mj_forward(settler.model, settler.data)
        hits = [c for c in settler.data.contact[: settler.data.ncon] if c.dist < 0]
        assert not hits, z


def test_recorded_ranges_and_safe_box():
    space = load_space()
    for axis in AXES:
        lo, hi = axis_range(axis)
        rlo, rhi = space["ranges"][axis]
        assert lo <= rlo + 1e-9 and hi >= rhi - 1e-9, axis  # recorded range is feasible
        assert rlo - lo <= 0.5 and hi - rhi <= 0.5, axis  # and not needlessly narrow
    box, center = space["safe_box"], space["center"]
    for signs in itertools.product((-1, 1), repeat=len(AXES)):
        assert feasible({a: center[a] + s * box[a] for a, s in zip(AXES, signs)})


def test_budget_rule_is_inside_the_feasible_set():
    b, rng = load_space()["budget"], np.random.default_rng(4)
    for _ in range(3000):
        hips = rng.normal(size=4)
        hips *= b["hip_l1_deg"] / np.abs(hips).sum() * rng.uniform() ** 0.25
        h = rng.uniform(*b["height_mm"])
        tilt = rng.normal(size=2)
        tilt *= b["tilt_l1_fraction"] * tilt_limit(h) / np.abs(tilt).sum() * rng.uniform() ** 0.5
        z = dict(zip(AXES[:4], hips)) | {"height": h, "pitch": tilt[0], "roll": tilt[1],
                                         "lift": rng.uniform(-1, 1) * b["lift_mm"]}
        assert within_budget(z) and feasible(z), z


def test_project_shrinks_towards_centre_keeping_direction():
    wild = {"pitch": 20, "height": 30, "stride": 60}
    z = project(wild)
    assert feasible(z)
    center = load_space()["center"]
    scale = (z["stride"] - center["stride"]) / 60
    assert 0 < scale < 1
    assert z["pitch"] == pytest.approx(20 * scale) and z["height"] == pytest.approx(42 + (30 - 42) * scale)


def test_feasible_poses_hold_in_mujoco(settler):
    failed = [z for z in _random_feasible(150, seed=3) if not settler.holds(z)[0]]
    assert not failed


def test_trot_walks_and_turns(settler):
    fwd = settler.drive(lambda t: gait(t, 2, stride=20, lift=10))
    back = settler.drive(lambda t: gait(t, 2, stride=-20, lift=10))
    left = settler.drive(lambda t: gait(t, 2, steer=10, lift=10))
    assert fwd["forward_mm_s"] > 80 and abs(fwd["turn_deg_s"]) < 5
    assert back["forward_mm_s"] < -80
    assert left["turn_deg_s"] > 30 and abs(left["forward_mm_s"]) < 10
    assert not any(r["body_down"] or r["max_tilt_deg"] > 15 for r in (fwd, back, left))


def test_gait_slope_matches_recorded_rate(settler):
    k = load_space()["gait"]["forward_mm_s_per_deg_hz"]
    got = settler.drive(lambda t: gait(t, 1, stride=10, lift=10))["forward_mm_s"]
    assert got == pytest.approx(k * 10 * 1, rel=0.15)
    assert math.isfinite(got)
