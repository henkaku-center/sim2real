"""Semantic behavior assertions over motion telemetry signatures.

This is the layer that was missing when the hip-axis and servo-sign bugs
slipped through: self-consistency tests (determinism, parity, symmetry)
cannot detect a wrong *interpretation* of the robot. These tests encode what
each motion MEANS ("a bow drops the head", "turn_left yaws CCW", "the waving
paw is airborne") as numeric invariants, verified against the prior-art
simulator where noted.

Expected cost: ~15 s for all motions (headless, no rendering).
"""

import pytest

from sim.telemetry import motion_signature

_cache: dict[str, dict] = {}


def sig(name: str) -> dict:
    if name not in _cache:
        _cache[name] = motion_signature(name)
    return _cache[name]


def test_rest_lies_flat_and_still():
    s = sig("rest")
    assert s["max_z"] - s["min_z"] < 0.01
    assert s["upright_final"] > 0.99
    assert all(v > 0.9 for v in s["paw_air_frac"].values()), "paddles flat, off ground"


def test_stand_lifts_body_level():
    s = sig("stand")
    assert s["final_z"] > 0.04
    assert s["upright_final"] > 0.99
    assert abs(s["pitch_min"]) < 0.01 and abs(s["pitch_max"]) < 0.01


def test_bow_drops_the_head():
    s = sig("bow")
    assert s["pitch_min"] < -0.015, "face end must dip below rear end"
    assert s["upright_final"] > 0.99
    assert abs(s["disp_x"]) < 0.03 and abs(s["disp_y"]) < 0.03


def test_dance_sits_back_face_up():
    # Verified against prior-art sim (user QC 2026-07-23): dance sits back on
    # its haunches, face end raised, rocking — NOT a play-bow.
    s = sig("dance")
    assert s["pitch_max"] > 0.05, "face end must rise well above rear end"
    assert s["upright_final"] > 0.99
    assert abs(s["yaw_deg"]) < 30


def test_wave_raises_only_the_front_left_paw():
    s = sig("wave")
    air = s["paw_air_frac"]
    assert air["L3"] > 0.5, "waving paw airborne most of the motion"
    for other in ("R3", "R4", "L4"):
        assert air[other] < 0.3, f"{other} should stay planted"
    assert abs(s["disp_x"]) < 0.05 and abs(s["disp_y"]) < 0.05
    assert s["upright_final"] > 0.99


def test_freaky_raises_the_right_side_paws():
    s = sig("freaky")
    air = s["paw_air_frac"]
    assert air["R3"] > 0.5 and air["R4"] > 0.5
    assert air["L3"] < 0.3 and air["L4"] < 0.3


def test_pushup_dips_the_chest():
    s = sig("pushup")
    assert s["pitch_min"] < -0.015
    assert s["upright_final"] > 0.99
    assert abs(s["disp_x"]) < 0.03


def test_walk_travels_forward_upright():
    s = sig("walk")
    assert s["disp_x"] > 0.05, "walk travels toward the face"
    assert s["upright_final"] > 0.9


def test_walk_backward_travels_backward():
    s = sig("walk_backward")
    assert s["disp_x"] < -0.05
    assert s["upright_final"] > 0.9


def test_turn_left_yaws_ccw():
    s = sig("turn_left")
    assert s["yaw_deg"] > 90
    assert abs(s["disp_x"]) < 0.05 and abs(s["disp_y"]) < 0.05


def test_turn_right_yaws_cw():
    s = sig("turn_right")
    assert s["yaw_deg"] < -90
    assert abs(s["disp_x"]) < 0.05 and abs(s["disp_y"]) < 0.05


def test_dead_ends_flat_on_the_ground():
    s = sig("dead")
    assert s["final_z"] < 0.02
    assert s["upright_final"] > 0.99


@pytest.mark.xfail(
    reason="placeholder masses/CoM: 'point' flips the robot in sim; the real "
    "robot points stably. Revisit after weighing parts (NEEDS-HARDWARE).",
    strict=True,
)
def test_point_stays_upright():
    s = sig("point")
    assert s["upright_final"] > 0.9
    assert abs(s["yaw_deg"]) < 45
