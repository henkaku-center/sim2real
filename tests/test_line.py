"""Line twin: the description is consistent and its reach evidence is current."""

import copy
import json

import numpy as np
import pytest

from sim import line as line_twin

LINE = line_twin.load_line()
needs_models = pytest.mark.skipif(
    bool(line_twin.missing_models(LINE)),
    reason="third-party models not cached; run tools/fetch_line_models.py",
)


def test_description_is_consistent():
    assert LINE["layout"] == "tabletop-v1"
    assert [s["id"] for s in LINE["steps"]] == ["print", "harvest", "order", "unpack", "kit", "transfer", "solder", "flash", "assemble", "walk_off"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["instances"]["kit_arm"].update(machine="missing"),
        lambda d: d["steps"][1].update(actor="nobody"),
        lambda d: d["steps"][1].update(visits={"main": ["nowhere"]}),
        lambda d: d["steps"][6].update(visits={"middle": ["jig_left"]}),
        lambda d: d["steps"][0].update(evidence="proven"),
        lambda d: d["machines"]["so101"].update(commit="141aea7"),
        lambda d: d["targets"]["bed_1"].update({True: "bed"}),  # YAML reads a bare `on:` key as true
    ],
)
def test_inconsistent_descriptions_are_rejected(mutate):
    broken = copy.deepcopy(LINE)
    mutate(broken)
    with pytest.raises(line_twin.LineError):
        line_twin.validate_line(broken)


def test_targets_resolve_in_the_line_frame():
    np.testing.assert_allclose(line_twin.target_point(LINE, "bed_2"), [-0.52, 0.22, 0.15], atol=1e-9)
    np.testing.assert_allclose(line_twin.target_point(LINE, "pallet"), [0.48, -0.06, 0.06], atol=1e-9)


def test_everything_fits_on_the_table():
    fit = line_twin.footprints(LINE)
    assert set(fit) >= {"printer_1", "printer_2", "printer_3", "jig", "pallet"}
    assert all(entry["on_table"] for entry in fit.values()), fit


@needs_models
def test_reach_record_is_current_and_every_target_is_reachable():
    record = line_twin.build_record(LINE)
    committed = json.loads(line_twin.record_path(LINE).read_text())
    assert record == committed
    assert len(record["reach"]) == 14
    assert all(r["reachable"] and r["residual_mm"] <= 5 for r in record["reach"]), record["findings"]
    assert record["findings"] == []
    assert record["rehearsals"]["kit_servo"]["feasible"]


def test_first_layout_record_keeps_its_findings():
    """tabletop-v0 copied the trailer picture; its gaps stay on record for comparison."""
    first = json.loads((line_twin.LINE_DIR / "tabletop-v0" / line_twin.RECORD_NAME).read_text())
    assert sum(r["reachable"] for r in first["reach"]) == 6
    assert len(first["findings"]) == 8


@needs_models
def test_reach_is_deterministic():
    model, data = line_twin.build_model(LINE)
    assert line_twin.reach_results(LINE, model, data) == line_twin.reach_results(LINE, model, data)


def test_previs_follows_the_storyboard_length_and_order():
    from sim import line_previs

    previs = line_previs.load_previs(LINE)
    assert [shot["id"] for shot in previs["shots"]] == list(range(1, 13))
    assert sum(shot["seconds"] for shot in previs["shots"]) == 59
    too_long = copy.deepcopy(previs)
    too_long["shots"][0]["seconds"] = 6
    with pytest.raises(line_twin.LineError):
        line_previs.validate_previs(LINE, too_long)
    bad_target = copy.deepcopy(previs)
    bad_target["shots"][0]["events"][0]["points"] = ["nowhere"]
    with pytest.raises(line_twin.LineError):
        line_previs.validate_previs(LINE, bad_target)


@needs_models
def test_previs_arm_waypoints_are_reachable():
    from sim import line_previs

    result = line_previs.summary(LINE, line_previs.load_previs(LINE))
    assert result["worst_waypoint_error_mm"] <= 5.0
    assert sum(shot["arm_waypoints"] for shot in result["shots"]) >= 40
