"""SafeAction gate: clamping, rate limiting, watchdog, and stop semantics."""

import math

import pytest

from sim.safeaction import SafeActionGate, load_safeaction


@pytest.fixture()
def gate():
    return SafeActionGate.create()


def test_config_schema():
    cfg = load_safeaction()
    assert cfg["limits"]["max_rate_deg_s"] <= 600, "cap below MG90S mechanical slew"
    assert cfg["watchdog"]["failsafe"] == "rest"
    cmds = {v["cmd"] for v in cfg["vocabulary"]}
    assert {"pose", "servo", "motion", "stop", "rest", "heartbeat"} <= cmds


def test_targets_clamped_to_soft_limits(gate):
    assert gate.cmd_pose(0, [500, -500, 90, 90, 90, 90, 90, 90])
    assert gate.target_deg[0] == 180  # R1 soft limit hi
    assert gate.target_deg[1] == 0  # R2 soft limit lo


def test_rate_limit_bounds_step(gate):
    gate.cmd_pose(0, [180, 90, 90, 90, 90, 90, 90, 90])
    gate.step(now_ms=2, dt_ms=2)
    max_deg_per_step = 300 * 2 / 1000  # 0.6 deg per 2 ms step
    assert gate.current_deg[0] == pytest.approx(90 + max_deg_per_step)
    # converges eventually and never overshoots
    for t in range(2, 2000, 2):
        gate.cmd_heartbeat(t)
        gate.step(now_ms=t, dt_ms=2)
    assert gate.current_deg[0] == pytest.approx(180)


def test_step_returns_internal_radians(gate):
    ctrl = gate.step(now_ms=1, dt_ms=1)
    assert all(c == pytest.approx(0.0) for c in ctrl), "neutral pose = q 0"
    gate.cmd_pose(1, [135, 90, 90, 90, 90, 90, 90, 90])
    for t in range(2, 400, 2):
        gate.cmd_heartbeat(t)
        ctrl = gate.step(now_ms=t, dt_ms=2)
    assert ctrl[0] == pytest.approx(math.radians(45))


def test_watchdog_fires_failsafe_rest(gate):
    gate.cmd_pose(0, [180, 90, 90, 90, 90, 90, 90, 90])
    for t in range(0, 300, 2):
        gate.step(now_ms=t, dt_ms=2)
    assert gate.current_deg[0] > 120, "moving toward commanded target"
    # silence past the 500 ms timeout -> failsafe to rest
    for t in range(300, 1600, 2):
        gate.step(now_ms=t, dt_ms=2)
    assert gate.in_failsafe
    assert gate.current_deg[0] == pytest.approx(90), "returned to rest"


def test_stop_freezes_position(gate):
    gate.cmd_pose(0, [180, 90, 90, 90, 90, 90, 90, 90])
    for t in range(0, 100, 2):
        gate.step(now_ms=t, dt_ms=2)
    frozen = list(gate.current_deg)
    gate.cmd_stop(100)
    for t in range(100, 400, 2):
        gate.cmd_heartbeat(t)
        gate.step(now_ms=t, dt_ms=2)
    assert gate.current_deg == pytest.approx(frozen)


def test_faulty_jump_rejected_and_freezes(gate):
    # steps beyond max_jump_deg (180) can't happen with clamped absolute
    # targets from neutral, so drive to one edge first
    gate.cmd_pose(0, [45, 90, 90, 90, 90, 90, 90, 90])
    for t in range(0, 400, 2):
        gate.cmd_heartbeat(t)
        gate.step(now_ms=t, dt_ms=2)
    cfg_jump = gate.config["limits"]["max_jump_deg"]
    assert cfg_jump <= 180
    # artificially lower the jump limit to test the freeze path
    gate.config["limits"]["max_jump_deg"] = 30
    assert not gate.cmd_pose(400, [180, 90, 90, 90, 90, 90, 90, 90])
    assert gate.stopped


def test_heartbeat_keeps_watchdog_fed(gate):
    gate.cmd_pose(0, [135, 90, 90, 90, 90, 90, 90, 90])
    for t in range(0, 2000, 2):
        if t % 300 == 0:
            gate.cmd_heartbeat(t)
        gate.step(now_ms=t, dt_ms=2)
    assert not gate.in_failsafe
    assert gate.current_deg[0] == pytest.approx(135)
