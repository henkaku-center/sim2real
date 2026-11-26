"""The MuJoCo stand-in for the S3's command interface (sim/live_robot.py)."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

from sim.live_robot import LINK_HOLD_S, RUN_RATE_DEG_S, SimRobot

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from sesame_remote import run_lines  # noqa: E402

STAND = "pose 135 45 45 135 0 180 0 180"


@pytest.fixture
def robot():
    return SimRobot()


def test_needs_arm_run_and_goes_limp_when_off(robot):
    assert robot.command(STAND) == (False, "ERR arm run first")
    assert robot.command("motion stand")[0] is False
    assert robot.command("arm run")[0]
    assert (robot.model.actuator_gainprm[:, 0] > 0).all()
    assert robot.command("off")[0]
    assert (robot.model.actuator_gainprm[:, 0] == 0).all()
    assert robot.command("dance please")[0] is False


def test_pose_is_rate_limited_then_stands(robot):
    robot.command("arm run")
    start = robot.ctrl.copy()
    robot.command(STAND)
    robot.advance(0.1)
    moved = np.degrees(np.abs(robot.ctrl - start))
    assert moved.max() == pytest.approx(RUN_RATE_DEG_S * 0.1, abs=1.0)
    for _ in range(10):
        robot.command("heartbeat")
        robot.advance(0.2)
    assert robot.data.qpos[2] > 0.04  # torso up on the paddles
    assert np.degrees(np.abs(robot.joints() - robot.target)).max() < 3


def test_pose_clamps_to_soft_limits(robot):
    robot.command("arm run")
    robot.command("pose 0 180 180 0 0 180 0 180")  # hips beyond their soft limits
    lo = np.array([robot.m.internal_range(j)[0] for j in robot.m.joints])
    hi = np.array([robot.m.internal_range(j)[1] for j in robot.m.joints])
    assert ((robot.target >= lo - 1e-9) & (robot.target <= hi + 1e-9)).all()


def test_link_loss_freezes_and_holds():
    robot = SimRobot(rate_deg_s=60)  # slow enough to still be moving when the link drops
    robot.command("arm run")
    robot.command(STAND)
    robot.advance(LINK_HOLD_S + 0.1)  # no heartbeat
    held = robot.ctrl.copy()
    robot.advance(0.5)
    assert np.allclose(robot.ctrl, held)
    stand = np.array([robot.m.pose_internal("stand")[j.name] for j in robot.m.joints])
    assert np.degrees(np.abs(held - stand)).max() > 10  # froze mid-way, short of the target


def test_motions_play_through_run_lines_like_the_robot(robot):
    def sleep(s):
        robot.advance(s)

    assert run_lines(robot, ["?arm run", "motion wave"], sleep=sleep) == 0
    assert not robot.busy()
    assert "motion=none" in robot.get("/status")[1]
    assert robot.get("/cmd?c=heartbeat") == (True, "OK")


def test_renders_jpeg(robot):
    pytest.importorskip("PIL")
    try:
        renderer = robot.mj.Renderer(robot.model, 120, 160)
    except Exception as e:  # headless CI without a GL context
        pytest.skip(f"no offscreen GL: {e}")
    cam = robot.mj.MjvCamera()
    cam.distance = 0.4
    data = robot.render_jpeg(renderer, cam, robot.mj.MjvOption())
    assert data[:2] == b"\xff\xd8" and len(data) > 1000
    assert math.isfinite(robot.t)
