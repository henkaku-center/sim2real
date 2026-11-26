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
    assert LINE["layout"] == "tabletop-v0"
    assert [s["id"] for s in LINE["steps"]] == ["print", "harvest", "order", "unpack", "kit", "solder", "flash", "assemble", "walk_off"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["instances"]["kit_arm"].update(machine="missing"),
        lambda d: d["steps"][1].update(actor="nobody"),
        lambda d: d["steps"][1].update(visits={"main": ["nowhere"]}),
        lambda d: d["steps"][5].update(visits={"middle": ["jig_left"]}),
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
    np.testing.assert_allclose(line_twin.target_point(LINE, "pallet"), [0.48, -0.04, 0.05], atol=1e-9)


def test_everything_fits_on_the_table():
    fit = line_twin.footprints(LINE)
    assert set(fit) >= {"printer_1", "printer_2", "printer_3", "jig", "pallet"}
    assert all(entry["on_table"] for entry in fit.values()), fit


@needs_models
def test_reach_record_is_current_and_reports_the_known_gaps():
    record = line_twin.build_record(LINE)
    committed = json.loads(line_twin.record_path(LINE).read_text())
    assert record == committed
    reach = {(r["actor"], r["gripper"], r["target"]): r for r in record["reach"]}
    # One arm in front of the middle printer reaches only that printer's bed.
    assert reach[("harvest_arm", "main", "bed_2")]["reachable"]
    assert 120 < reach[("harvest_arm", "main", "bed_1")]["residual_mm"] < 160
    # A pedestal standing on the table keeps both grippers far above the jig.
    assert 300 < reach[("assembly_arms", "left", "jig_right")]["residual_mm"] < 400
    assert sum(r["reachable"] for r in record["reach"]) == 6
    assert record["rehearsals"]["kit_servo"]["feasible"]
    assert record["rehearsals"]["kit_servo"]["worst_residual_mm"] <= 5.0


@needs_models
def test_reach_is_deterministic():
    model, data = line_twin.build_model(LINE)
    assert line_twin.reach_results(LINE, model, data) == line_twin.reach_results(LINE, model, data)
