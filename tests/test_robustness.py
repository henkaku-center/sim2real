"""Simulated outcomes are trusted only where they survive the unmeasured parameters."""

import pytest

from sim import robustness
from sim.motions import load_motions

# The wave as upstream wrote it, kept here because a built robot contradicted
# the nominal twin on it (instructor observation, 2026-11-16, DECISIONS.md D28).
UPSTREAM_WAVE = [
    {"pose": "stand"}, {"wait": 200},
    {"set": {"R4": 80, "L3": 180, "L2": 90, "R1": 100}}, {"wait": 200},
    {"set": {"L3": 180}}, {"wait": 300},
    {"repeat": {"count": 4, "steps": [{"set": {"L3": 180}}, {"wait": 300}, {"set": {"L3": 100}}, {"wait": 300}]}},
    {"pose": "stand"},
]
# Folding the rear foot first, without moving the front-right hip forward.
REAR_FIRST_ONLY = [
    {"pose": "stand"}, {"wait": 200},
    {"set": {"R4": 80, "L2": 90, "R1": 100}}, {"wait": 300},
    {"set": {"L3": 180}}, {"wait": 300},
    {"repeat": {"count": 4, "steps": [{"set": {"L3": 180}}, {"wait": 300}, {"set": {"L3": 100}}, {"wait": 300}]}},
    {"pose": "stand"},
]


@pytest.fixture(scope="module")
def wave():
    return load_motions()["motions"]["wave"]


def test_grid_covers_centre_of_mass_collision_shape_gain_and_friction():
    assert len(robustness.GRID) == 54 and robustness.NOMINAL in robustness.GRID
    assert {v[2] for v in robustness.GRID} == {"box", "hull"}
    assert max(v[0] for v in robustness.GRID) == 15 and min(v[0] for v in robustness.GRID) == -15


def test_course_wave_coarse_outcome_agrees_on_the_tested_grid(wave):
    result = robustness.survey(wave)
    assert result["nominal"] == {"upright": True, "feet_in_air": ["L3"]}
    assert result["coarse_agreement"], result["differing"]


def test_wider_variant_coarse_outcome_keeps_l3_mostly_airborne(wave):
    # At the far corner of the grid (centre of mass 15 mm forward and 8 mm left) the
    # heavier variant balances on two feet with the folded foot just clear of the floor.
    result = robustness.survey(wave, "internal-frame-s3-two-eyes")
    assert result["agree"] >= 52
    assert all(row["upright"] and "L3" in row["feet_in_air"] for row in result["differing"])


def test_nominal_twin_alone_would_have_passed_the_wave_that_tips_a_real_robot():
    # The reason outcomes are judged over the grid: the nominal run of the
    # upstream wave looks fine, but the real robot tips forward.
    assert robustness.outcome(UPSTREAM_WAVE)["feet_in_air"] == ["L3"]
    result = robustness.survey(UPSTREAM_WAVE)
    assert not result["coarse_agreement"]
    forward = [row for row in result["differing"] if row["com_dx_mm"] == 15]
    assert len(forward) >= 15, "with the centre of mass 15 mm forward the upstream wave tips"
    assert all("R4" in row["feet_in_air"] for row in forward), "the folded rear foot is the one left in the air"


def test_folding_the_rear_foot_first_is_not_enough_on_its_own():
    assert not robustness.survey(REAR_FIRST_ONLY)["coarse_agreement"]


def test_recovering_after_tipping_does_not_pass_wave_screen(wave):
    transient = wave[:-1] + [{"set": {"R1": 100}}, {"wait": 500}, {"pose": "stand"}]
    r = robustness.outcome(transient, (15., 0., "box", (1., 1.)))
    assert r["upright"] and r["feet_in_air"] == ["L3"]
    assert "wave-tilt-or-final-posture" in robustness.wave_failures(r)


def test_unconverged_contact_does_not_pass_release_screen(wave):
    # This tests rejection, not validation of the current simulation. The
    # independent --check-wave command remains nonzero until contact is fixed.
    r = robustness.wave_audit(wave, "internal-frame-s3-two-eyes")
    assert not r["accepted"] and not r["converged"]
    assert any("excessive-floor-penetration" in run["failures"] for run in r["runs"])
