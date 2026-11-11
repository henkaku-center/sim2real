"""Simulated evidence for the two-eye variant against the base course twin.

Everything here is MuJoCo simulation with unmeasured parameters. The tests
recompute the committed evidence and assert what each motion means on both
designs; they do not establish anything about a built robot.

Expected cost: about 40 s (two designs, every stock motion, 64 what-if builds).
"""

import json
import math

import mujoco
import numpy as np
import pytest

from sim import twin, twin_evidence
from sim.manifest import load_manifest
from sim.motions import load_motions
from sim.telemetry import motion_signature

BASE = "internal-frame-s3"
EYES = "internal-frame-s3-two-eyes"
DESIGNS = [BASE, EYES]
MOTIONS = sorted(load_motions()["motions"])

_signatures: dict[tuple[str, str], dict] = {}


def sig(design: str, motion: str) -> dict:
    if (design, motion) not in _signatures:
        _signatures[design, motion] = motion_signature(motion, design=design)
    return _signatures[design, motion]


@pytest.fixture(scope="module")
def evidence():
    return json.loads(twin_evidence.evidence_path(EYES).read_text())


@pytest.fixture(scope="module")
def manifest():
    return load_manifest()


@pytest.fixture(scope="module")
def stands(manifest):
    return {d: twin_evidence.standing(twin.load_model(d), manifest) for d in DESIGNS}


# ------------------------------------------------------- what the record is


def test_evidence_follows_its_inputs():
    assert twin_evidence.variants() == {EYES: BASE}
    assert twin_evidence.check_all() == [], "regenerate with: uv run python -m sim.twin_evidence"


def test_changed_inputs_make_the_evidence_stale(monkeypatch):
    real = twin_evidence.inputs

    def changed(variant, base):
        return {**real(variant, base), f"models/{EYES}.xml": "0" * 64}

    monkeypatch.setattr(twin_evidence, "inputs", changed)
    (problem,) = twin_evidence.check_all()
    assert f"stale relative to models/{EYES}.xml" in problem


def test_evidence_says_exactly_what_it_is(evidence):
    text = twin_evidence.evidence_path(EYES).read_text().lower()
    assert evidence["status"] == "simulated-unmeasured-parameters"
    assert (evidence["variant"], evidence["base"]) == (EYES, BASE)
    assert "no part was weighed" in evidence["scope"].lower()
    assert "verified" not in text and "validated" not in text and "accepted" not in text
    assert len(evidence["not_established"]) >= 3
    assert evidence["engine"] == {"name": "MuJoCo", "version": mujoco.__version__}
    for design in DESIGNS:
        assert evidence["mass"][design]["mass_by_status_kg"]["measured"] == 0.0


# -------------------------------------------------------- mass and geometry


def test_mass_and_centre_of_mass_change(evidence):
    base, eyes = twin.load_record(BASE)["totals"], twin.load_record(EYES)["totals"]
    change = evidence["mass"]["change"]
    assert change["mass_kg"] == pytest.approx(eyes["mass_kg"] - base["mass_kg"], abs=1e-9)
    assert change["mass_kg"] == pytest.approx(0.036682, abs=1e-6)  # +36.7 g
    assert change["mass_percent"] == pytest.approx(10.86, abs=0.01)
    assert change["com_mm"] == pytest.approx([0.5211, 0.0347, 0.8199], abs=1e-4)  # forward and up
    assert change["parts_only_in_variant"] == ["oled-display.2"]
    assert evidence["mass"][BASE]["mass_kg"] == base["mass_kg"]
    assert evidence["mass"][EYES]["com_mm"] == pytest.approx(np.array(eyes["com_torso_m"]) * 1000, abs=1e-4)


def test_support_margin_geometry():
    square = twin_evidence._hull(np.array([[0, 0], [2, 0], [2, 2], [0, 2], [1, 1], [1, 0.5]], dtype=float))
    assert len(square) == 4  # interior points dropped
    margin, _ = twin_evidence.support_margin(square, np.array([1.0, 1.0]))
    assert margin == pytest.approx(1.0)
    margin, edge = twin_evidence.support_margin(square, np.array([1.75, 1.0]))
    assert margin == pytest.approx(0.25)
    assert {tuple(square[edge]), tuple(square[(edge + 1) % 4])} == {(2.0, 0.0), (2.0, 2.0)}
    assert twin_evidence.support_margin(square, np.array([2.5, 1.0]))[0] == pytest.approx(-0.5)  # outside
    assert twin_evidence.support_margin(square[:2], np.array([1.0, 0.0]))[0] == -math.inf  # no polygon


# -------------------------------------------------------- standing stability


@pytest.mark.parametrize("design,margin,height,width", [
    (BASE, 68.58, 52.32, 138.32),
    (EYES, 68.05, 53.28, 168.41),
])
def test_standing_margin(design, margin, height, width, stands, evidence):
    s = stands[design]
    assert s["feet_in_contact"] == ["L3", "L4", "R3", "R4"]
    assert s["upright"] > 0.9999 and s["max_joint_speed_rad_s"] < 1e-3, "settled and level"
    assert s["margin_mm"] == pytest.approx(margin, abs=0.5)
    assert s["nearest_edge"] == "front"
    assert s["com_height_mm"] == pytest.approx(height, abs=0.5)
    assert s["support_width_mm"] == pytest.approx(width, abs=0.5)
    assert s["support_length_mm"] == pytest.approx(139.1, abs=0.5)
    assert s["torso_height_mm"] == pytest.approx(48.8, abs=0.5)
    assert s["tilt_to_tip_deg"] == pytest.approx(math.degrees(math.atan2(s["margin_mm"], s["com_height_mm"])), abs=1e-3)
    committed, tolerance = evidence["standing"][design], evidence["tolerances"]
    assert s["margin_mm"] == pytest.approx(committed["margin_mm"], abs=tolerance["margin_mm"])
    assert s["com_height_mm"] == pytest.approx(committed["com_height_mm"], abs=tolerance["height_mm"])
    assert s["nearest_edge"] == committed["nearest_edge"]
    assert len(committed["support_polygon_mm"]) == 8  # two outer corners of each foot


def test_widening_moves_the_feet_apart_but_not_the_limiting_edge(stands, evidence):
    widen = json.loads((twin.design_dir(EYES) / "assembly.json").read_text())["variant"]["widen_mm"]
    assert stands[EYES]["support_width_mm"] - stands[BASE]["support_width_mm"] == pytest.approx(widen, abs=0.5)
    # The nearest edge stays the front one, whose distance the widening does not change;
    # the variant's centre of mass sits 0.5 mm further forward, so the margin drops by 0.5 mm.
    assert stands[EYES]["margin_mm"] - stands[BASE]["margin_mm"] == pytest.approx(-0.52, abs=0.2)
    assert evidence["standing"]["change"]["margin_mm"] == pytest.approx(-0.52, abs=0.01)


def test_margin_under_seeded_mass_uncertainty(evidence):
    recorded = evidence["mass_uncertainty"]
    settings = {k: recorded[k] for k in ("seed", "samples", "spread")}
    assert settings == {"seed": 20261112, "samples": 32, "spread": 0.2} == twin_evidence.UNCERTAINTY
    for design, low in ((BASE, 68.38), (EYES, 67.80)):
        again = twin_evidence.mass_uncertainty(design, **settings)
        for key in ("min", "median", "max"):
            assert again["margin_mm"][key] == pytest.approx(recorded[design]["margin_mm"][key], abs=0.5)
        assert again["mass_kg"] == pytest.approx(recorded[design]["mass_kg"], abs=1e-6)  # same seed, same draws
        assert again["margin_mm"]["min"] == pytest.approx(low, abs=0.5)
        nominal = evidence["standing"][design]["margin_mm"]
        assert again["margin_mm"]["min"] < nominal < again["margin_mm"]["max"]


# --------------------------------------------------------------- determinism


@pytest.mark.parametrize("design", DESIGNS)
def test_stand_is_bit_identical_and_matches_the_committed_reference(design, evidence, manifest):
    model = twin.load_model(design)
    first = twin_evidence.stand_reference(model, manifest)
    assert first == twin_evidence.stand_reference(model, manifest), "same machine: bit-identical"
    reference = evidence["stand_reference"]
    assert reference["steps"] == 1000
    np.testing.assert_allclose(first, reference[design], atol=evidence["tolerances"]["stand_qpos"])
    assert first[2] == pytest.approx(0.0488, abs=5e-4), "standing lifts the torso to about 49 mm"


# ------------------------------------------------------------------- motions


def _close(new, old, tolerance, what):
    def near(a, b, tol, name):
        assert abs(a - b) <= tol, f"{what} {name}: {a} vs committed {b} (tolerance {tol})"

    near(new["disp_x"], old["disp_x"], tolerance["disp_m"], "disp_x")
    near(new["disp_y"], old["disp_y"], tolerance["disp_m"], "disp_y")
    turn = (new["yaw_deg"] - old["yaw_deg"] + 180) % 360 - 180
    near(turn, 0.0, tolerance["yaw_deg"], "yaw_deg")
    for key in ("final_z", "min_z", "max_z"):
        near(new[key], old[key], tolerance["z_m"], key)
    for key in ("pitch_min", "pitch_max"):
        near(new[key], old[key], tolerance["pitch_m"], key)
    near(new["upright_final"], old["upright_final"], tolerance["upright"], "upright_final")
    for paw in old["paw_air_frac"]:
        near(new["paw_air_frac"][paw], old["paw_air_frac"][paw], tolerance["air_frac"], f"air {paw}")
        near(new["paw_max_z"][paw], old["paw_max_z"][paw], tolerance["paw_max_z_m"], f"paw_max_z {paw}")


@pytest.mark.parametrize("design", DESIGNS)
@pytest.mark.parametrize("motion", MOTIONS)
def test_signature_matches_the_committed_evidence(design, motion, evidence):
    assert set(evidence["motions"]) == set(MOTIONS) and len(MOTIONS) == 19
    sensitive = evidence["command_sensitivity"][motion][design]["sensitive"]
    tolerance = evidence["tolerances"]["sensitive_signature" if sensitive else "signature"]
    _close(sig(design, motion), evidence["motions"][motion][design], tolerance, f"{design} {motion}")


def test_only_bow_is_sensitive_to_a_nanoradian(evidence):
    sensitive = {m for m in MOTIONS for d in DESIGNS if evidence["command_sensitivity"][m][d]["sensitive"]}
    assert sensitive == {"bow"}
    for motion in set(MOTIONS) - sensitive:
        for design in DESIGNS:
            assert evidence["command_sensitivity"][motion][design]["end_shift_mm"] < 1e-3


# What each motion means, asserted on both designs (compare tests/test_behavior.py
# for the upstream-body baseline). Thresholds are in metres on an 87 mm long body.


@pytest.mark.parametrize("design", DESIGNS)
def test_rest_lies_flat_and_still(design):
    s = sig(design, "rest")
    assert s["max_z"] - s["min_z"] < 0.01 and s["upright_final"] > 0.99
    assert all(v > 0.9 for v in s["paw_air_frac"].values()), "paddles flat, off the ground"


@pytest.mark.parametrize("design", DESIGNS)
def test_stand_lifts_the_body_level(design):
    s = sig(design, "stand")
    assert s["final_z"] == pytest.approx(0.0488, abs=5e-4)
    assert s["upright_final"] > 0.99
    assert abs(s["pitch_min"]) < 0.01 and abs(s["pitch_max"]) < 0.01
    assert abs(s["disp_x"]) < 0.01 and abs(s["disp_y"]) < 0.01


@pytest.mark.parametrize("design", DESIGNS)
def test_bow_drops_the_head(design):
    s = sig(design, "bow")
    assert s["pitch_min"] < -0.015, "face end dips below the rear end"
    assert s["upright_final"] > 0.99
    assert abs(s["disp_x"]) < 0.06 and abs(s["disp_y"]) < 0.06  # sensitive motion: loose


@pytest.mark.parametrize("design", DESIGNS)
def test_dance_sits_back_face_up_and_stays_upright(design):
    s = sig(design, "dance")
    assert s["pitch_max"] > 0.03, "face end at least 30 mm above the rear end"
    assert s["pitch_min"] > -0.01, "never a play-bow"
    assert s["upright_final"] > 0.99 and abs(s["yaw_deg"]) < 30


@pytest.mark.parametrize("design", DESIGNS)
def test_wave_raises_only_the_front_left_paw(design):
    s = sig(design, "wave")
    air = s["paw_air_frac"]
    assert air["L3"] > 0.5
    assert all(air[other] < 0.3 for other in ("R3", "R4", "L4"))
    assert abs(s["disp_x"]) < 0.05 and abs(s["disp_y"]) < 0.05 and s["upright_final"] > 0.99
    assert s["paw_max_z"]["L3"] > 0.08, "waving paw rises well above the standing foot axis"


@pytest.mark.parametrize("design", DESIGNS)
def test_freaky_raises_the_right_side_paws(design):
    air = sig(design, "freaky")["paw_air_frac"]
    assert air["R3"] > 0.5 and air["R4"] > 0.5 and air["L3"] < 0.3 and air["L4"] < 0.3


# Simulated difference, recorded as found: over four push-ups the wider variant
# creeps about 65 mm backward where the base creeps about 16 mm.
@pytest.mark.parametrize("design,creep", [(BASE, -0.016), (EYES, -0.065)])
def test_pushup_dips_the_chest(design, creep):
    s = sig(design, "pushup")
    assert s["pitch_min"] < -0.015 and s["upright_final"] > 0.99
    assert s["disp_x"] == pytest.approx(creep, abs=0.01)


@pytest.mark.parametrize("design", DESIGNS)
def test_walks_travel_along_the_body_axis(design):
    forward, backward = sig(design, "walk"), sig(design, "walk_backward")
    assert forward["disp_x"] > 0.05 and forward["upright_final"] > 0.9
    assert backward["disp_x"] < -0.05 and backward["upright_final"] > 0.9


@pytest.mark.parametrize("design", DESIGNS)
def test_turns_rotate_roughly_in_place(design):
    left, right = sig(design, "turn_left"), sig(design, "turn_right")
    assert left["yaw_deg"] > 90 and right["yaw_deg"] < -90
    for s in (left, right):
        assert abs(s["disp_x"]) < 0.06 and abs(s["disp_y"]) < 0.06


@pytest.mark.parametrize("design", DESIGNS)
def test_dead_ends_flat_on_the_ground(design):
    s = sig(design, "dead")
    assert s["final_z"] < 0.02 and s["upright_final"] > 0.99


@pytest.mark.parametrize("design", DESIGNS)
def test_point_and_every_other_motion_end_upright(design):
    # With servo speed bounded at the manifest's nominal value no stock motion
    # tips either design over in simulation, `point` included.
    s = sig(design, "point")
    assert s["upright_final"] > 0.99 and abs(s["yaw_deg"]) < 45
    assert s["paw_air_frac"]["L3"] > 0.5, "the pointing paw is the front-left one"
    for motion in MOTIONS:
        assert sig(design, motion)["upright_final"] > 0.99, motion
