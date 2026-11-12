"""The design-driven twin: generated MJCF and dynamics record per printing design.

Numbers asserted here are simulation-model numbers: printed masses estimated
from mesh volume, purchased parts nominal. None is a measurement.
"""

import copy
import json
import math

import mujoco
import numpy as np
import pytest
import trimesh
import yaml
from scipy.spatial import cKDTree

from sim import build_mjcf, twin
from sim.manifest import REPO_ROOT, load_manifest

BASE = "internal-frame-s3"
EYES = "internal-frame-s3-two-eyes"
SIX = "internal-frame-s3-two-eyes-six-legs"
DESIGNS = [BASE, EYES]
CORNERS = {"front_left": (1, 1), "front_right": (1, -1), "back_left": (-1, 1), "back_right": (-1, -1)}


@pytest.fixture(scope="module")
def manifest():
    return load_manifest()


@pytest.fixture(scope="module")
def records():
    return {d: twin.load_record(d) for d in DESIGNS}


@pytest.fixture(scope="module")
def models():
    return {d: twin.load_model(d) for d in DESIGNS}


def assembly(design):
    return json.loads((twin.design_dir(design) / "assembly.json").read_text())


def body(record, name):
    return next(b for b in record["bodies"] if b["name"] == name)


def joint(record, name):
    return next(j for j in record["joints"] if j["name"] == name)


def part(record, part_id):
    return next(p for p in record["mass_table"] if p["id"] == part_id)


# ------------------------------------------------------------ drift and names


def test_committed_models_and_records_follow_their_inputs():
    assert twin.check_all() == [], "regenerate with: uv run python -m sim.twin"


def test_generation_is_repeatable():
    first, second = twin.build(BASE), twin.build(BASE)
    assert first.xml == second.xml and first.record_text == second.record_text
    assert first.record["mjcf"]["sha256"] == twin._sha(twin.model_path(BASE))


def test_a_changed_input_makes_the_committed_files_stale(monkeypatch):
    spec = twin.load_spec()
    changed = copy.deepcopy(spec)
    next(r for r in changed["mass_table"] if r["id"] == "battery")["mass_kg"] = 0.050
    monkeypatch.setattr(twin, "load_spec", lambda *a, **k: changed)
    problems = twin.check_all()
    assert len(problems) == 4 and all("stale relative to its inputs" in p for p in problems)
    for name in ("models/internal-frame-s3.xml", "assets/printing/internal-frame-s3-two-eyes/dynamics.json"):
        assert any(p.startswith(name) for p in problems)


def test_record_names_every_input_by_hash(records):
    for design in DESIGNS:
        hashes = records[design]["source_hashes"]
        for path in ("manifest/robot.yaml", "manifest/twin.yaml", "sim/twin.py",
                     f"assets/printing/{design}/assembly.json",
                     f"assets/printing/{design}/internal-frame.stl", "assets/stl/upstream/L1-v117.stl"):
            assert hashes[path] == twin._sha(REPO_ROOT / path)
        assert len(hashes) == 6 + 5 + 8  # manifests, code and assembly; body prints; leg prints


def test_models_are_addressable_by_name():
    assert twin.default_design() == BASE
    assert twin.model_path() == REPO_ROOT / "models" / f"{BASE}.xml"
    assert twin.model_path(EYES).name == f"{EYES}.xml"
    # The upstream narrow body keeps its file and gains an explicit name.
    assert twin.model_path(twin.LEGACY_UPSTREAM) == build_mjcf.MODEL_PATH
    assert build_mjcf.MODEL_PATH.read_text() == build_mjcf.build_xml()
    legacy = twin.load_model(twin.LEGACY_UPSTREAM)
    assert float(legacy.body_mass.sum()) == pytest.approx(0.287, abs=1e-9)


def test_default_hardware_is_the_course_s3_and_the_s2_board_is_historical(manifest, records):
    spec = twin.load_spec()
    current = twin.hardware_profile(spec, manifest)
    assert current["name"] == "sesame_s3" and current["status"] == "current-course-default"
    assert (current["mcu_board"], current["servo_driver"]) == ("esp32_s3_supermini", "pca9685")
    # Wiring and calibration are read from robot.yaml, never copied.
    assert current["robot_yaml"] == "hardware_profiles.sesame_s3"
    assert manifest.raw["hardware_profiles"]["sesame_s3"]["pca_address"] == 0x40
    # robot.yaml owns both board names; twin.yaml only points at them.
    assert manifest.raw["mcu"]["board"] == "esp32_s3_supermini"
    assert manifest.raw["mcu"]["servo_driver"] == "pca9685"
    for profile in spec["hardware"]["profiles"].values():
        assert not {"mcu_board", "servo_driver"} & set(profile)
    old = twin.hardware_profile(spec, manifest, "lolin_s2_mini_baseline")
    assert old["status"] == "historical-upstream-baseline"
    assert (old["mcu_board"], old["servo_driver"]) == ("lolin_esp32_s2_mini", "direct-gpio-pwm")
    for design in DESIGNS:
        assert records[design]["hardware_profile"]["mcu_board"] == "esp32_s3_supermini"


# ------------------------------------------------------------- mesh integrals


def test_mesh_integrals_are_exact_for_a_box():
    box = trimesh.creation.box(extents=(2.0, 3.0, 5.0))
    box.apply_translation((7.0, -1.0, 0.5))
    solid = twin.mesh_solid(np.asarray(box.triangles, dtype=float))
    assert solid.volume == pytest.approx(30.0, abs=1e-12)
    assert solid.com == pytest.approx([7.0, -1.0, 0.5], abs=1e-12)
    expected = 30.0 / 12 * np.diag([9 + 25, 4 + 25, 4 + 9])
    assert solid.inertia == pytest.approx(expected, abs=1e-10)


@pytest.mark.parametrize("path", ["assets/stl/upstream/L1-v117.stl",
                                  "assets/printing/internal-frame-s3/internal-frame.stl"])
def test_mesh_integrals_match_trimesh(path):
    solid = twin.mesh_solid(twin.read_stl(REPO_ROOT / path))
    reference = trimesh.load(REPO_ROOT / path, force="mesh")
    assert solid.volume == pytest.approx(reference.volume, rel=1e-9)
    assert solid.com == pytest.approx(reference.center_mass, abs=1e-6)
    assert solid.inertia == pytest.approx(reference.moment_inertia, rel=1e-6, abs=1e-3)


# ---------------------------------------------------------------- kinematics


@pytest.mark.parametrize("design", DESIGNS)
def test_joint_origins_and_axes_come_from_the_design(design, records, manifest):
    record, shafts = records[design], assembly(design)["hip_shaft_xy_mm"]
    frame_top = assembly(design)["servo_flange_seat_z_mm"]
    for hip in (j for j in manifest.joints if j.role == "hip"):
        foot = next(j for j in manifest.joints if j.leg == hip.leg and j.role == "foot")
        fx, lat = CORNERS[hip.leg]
        h, f = joint(record, hip.name), joint(record, foot.name)
        assert np.array(h["origin_m"][:2]) * 1000 == pytest.approx(shafts[hip.name], abs=1e-6)
        # Hip axis is vertical; positive internal angle sweeps the leg outward.
        assert h["axis"] == [0, 0, -fx * lat] and h["axis"][2] == hip.sign
        # Foot axis lies fore-aft, 36.86 mm outboard of the hip shaft; positive is paddle down.
        assert f["axis"] == [-lat, 0, 0]
        offset = (np.array(f["origin_m"]) - np.array(h["origin_m"])) * 1000
        assert offset == pytest.approx([0, lat * 36.86, 0], abs=1e-6)
        # Both axes lie in the leg plane, 24.108 mm below the top of the upper print.
        assert h["origin_m"][2] * 1000 == pytest.approx(frame_top + 17.17 - 24.107758, abs=1e-5)
        assert h["limits_firmware_deg"] == list(hip.limits_deg)
        assert h["range_rad"] == pytest.approx(manifest.internal_range(hip), abs=1e-6)
        assert f["range_rad"] == pytest.approx(manifest.internal_range(foot), abs=1e-6)
    assert [j["name"] for j in record["joints"]] == [j.name for j in manifest.joints]


def test_course_hip_shafts_are_the_wide_v3_frame(records):
    r = records[BASE]
    assert joint(r, "L1")["origin_m"][:2] == pytest.approx([0.028217465, 0.037975], abs=1e-9)
    assert joint(r, "R2")["origin_m"][:2] == pytest.approx([-0.028583896, -0.037975], abs=1e-9)
    # The upstream narrow body put the hips at (+-24.5, +-23.0) mm.
    assert (build_mjcf.HIP_X, build_mjcf.HIP_Y) == (0.0245, 0.0230)


@pytest.mark.parametrize("design", DESIGNS)
def test_wide_side_of_every_upper_print_faces_the_middle(design, records):
    boxes = records[design]["contact"]["collision_boxes_m"]
    for leg, (fx, lat) in CORNERS.items():
        centre, half = (np.array(boxes[f"{leg}_upper_geom"][k]) * 1000 for k in ("centre", "half_size"))
        toward_middle = -fx * (centre[0] - fx * half[0])  # extent from the hip shaft toward x = 0
        toward_corner = fx * (centre[0] + fx * half[0])
        assert toward_middle == pytest.approx(13.947, abs=1e-3), leg
        assert toward_corner == pytest.approx(6.373, abs=1e-3), leg
        # The foot print sits on the corner side of the hip shaft, outboard of it.
        foot = np.array(boxes[f"{leg}_lower_geom"]["centre"]) * 1000
        assert fx * foot[0] == pytest.approx(7.025, abs=1e-3) and lat * foot[1] > 0


@pytest.mark.parametrize("design", DESIGNS)
def test_upper_print_top_is_17_17_mm_above_the_frame_top(design, records):
    record, frame_top = records[design], assembly(design)["servo_flange_seat_z_mm"]
    for leg in CORNERS:
        box = record["contact"]["collision_boxes_m"][f"{leg}_upper_geom"]
        top = body(record, f"{leg}_upper")["origin_in_parent_m"][2] + box["centre"][2] + box["half_size"][2]
        assert top * 1000 - frame_top == pytest.approx(17.17, abs=1e-5)


def placed_vertices(model, data, geom):
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, geom)
    mesh = model.geom_dataid[gid]
    start = model.mesh_vertadr[mesh]
    local = model.mesh_vert[start:start + model.mesh_vertnum[mesh]]
    world = local @ data.geom_xmat[gid].reshape(3, 3).T + data.geom_xpos[gid]
    torso = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "torso")
    return (world - data.xpos[torso]) * 1000  # CAD frame, mm (torso is unrotated at spawn)


@pytest.mark.parametrize("pose", ["rest", "standing"])
def test_leg_meshes_sit_where_the_design_record_placed_them(pose, models, manifest):
    # Independent placement of the same unchanged leg prints, recorded with the
    # base design (Rest and Standing). Vertices must coincide: a mirrored or
    # swapped print could match the bounds but not the points.
    clearance = json.loads((twin.design_dir(BASE) / "head-cable-clearance.json").read_text())
    model = models[BASE]
    data = mujoco.MjData(model)
    target = manifest.pose_internal("stand" if pose == "standing" else "rest")
    for j in manifest.joints:
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, j.name)
        data.qpos[model.jnt_qposadr[jid]] = target[j.name]
    mujoco.mj_forward(model, data)
    samples = [s for s in clearance["leg_samples"] if s["pose"] == pose]
    assert len(samples) == 8
    for sample in samples:
        j = manifest.joint(sample["part"])
        geom = f"{j.leg}_{'upper' if j.role == 'hip' else 'lower'}_visual"
        placed = placed_vertices(model, data, geom)
        assert placed.min(axis=0) == pytest.approx(sample["bounds_mm"][0], abs=0.01), sample["part"]
        assert placed.max(axis=0) == pytest.approx(sample["bounds_mm"][1], abs=0.01), sample["part"]
        distance, _ = cKDTree(placed).query(np.array(sample["points_mm"]))
        assert distance.max() < 0.01, f"{sample['part']} {pose}: {distance.max():.4f} mm"


# -------------------------------------------------------- record versus MuJoCo


@pytest.mark.parametrize("design", DESIGNS)
def test_compiled_model_agrees_with_the_record(design, records, models, manifest):
    record, model = records[design], models[design]
    assert (model.nq, model.nu, model.njnt) == (15, 8, 9)
    assert float(model.opt.timestep) == record["simulation"]["timestep_s"] == 0.002
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    torso = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "torso")
    assert float(model.body_mass.sum()) == pytest.approx(record["totals"]["mass_kg"], abs=1e-9)
    assert data.subtree_com[torso] - data.xpos[torso] == pytest.approx(record["totals"]["com_torso_m"], abs=1e-9)
    assert data.xpos[torso][2] == pytest.approx(record["simulation"]["spawn_height_m"], abs=1e-12)
    for b in record["bodies"]:
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, b["name"])
        assert float(model.body_mass[bid]) == pytest.approx(b["mass_kg"], abs=1e-9)
        assert model.body_ipos[bid] == pytest.approx(b["com_m"], abs=1e-9)
        i = b["inertia_kg_m2"]
        matrix = np.array([[i["xx"], i["xy"], i["xz"]], [i["xy"], i["yy"], i["yz"]], [i["xz"], i["yz"], i["zz"]]])
        assert sorted(model.body_inertia[bid]) == pytest.approx(sorted(np.linalg.eigvalsh(matrix)), rel=1e-6)
        parent = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, model.body_parentid[bid])
        assert parent == (b["parent"] or "world")
    for i, j in enumerate(manifest.joints):
        assert mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i) == j.name
        assert model.actuator_ctrlrange[i] == pytest.approx(manifest.internal_range(j), abs=1e-5)
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, j.name)
        recorded = joint(record, j.name)
        assert model.jnt_range[jid] == pytest.approx(recorded["range_rad"], abs=1e-9)
        assert data.xanchor[jid] - data.xpos[torso] == pytest.approx(recorded["origin_m"], abs=1e-9)
        assert data.xaxis[jid] == pytest.approx(recorded["axis"], abs=1e-12)
    actuators = record["actuators"]
    assert actuators["order"] == [j.name for j in manifest.joints]
    assert model.actuator_gainprm[:, 0] == pytest.approx(actuators["kp_Nm_per_rad"])
    assert model.actuator_forcerange[:, 1] == pytest.approx(actuators["force_limit_Nm"])
    assert model.dof_damping[6:] == pytest.approx(actuators["joint_damping_Nm_s_per_rad"], abs=1e-9)
    floor = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    assert model.geom_friction[floor] == pytest.approx(record["contact"]["floor_friction"])
    sites = {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_SITE, i) for i in range(model.nsite)}
    assert sites == {"torso_center", "face", "rear"} | {f"{leg}_{s}" for leg in CORNERS for s in ("hip", "knee", "paw")}


def test_actuator_and_contact_values_are_read_not_repeated(records, manifest):
    servo = manifest.raw["servo_model"]
    actuators = records[BASE]["actuators"]
    assert actuators["status"] == "unmeasured-nominal" == records[BASE]["contact"]["status"]
    assert actuators["force_limit_Nm"] == servo["stall_torque_Nm_at_4v8"] == 0.176
    speed = math.radians(60) / servo["speed_s_per_60deg_at_4v8"]
    assert actuators["no_load_speed_rad_s"] == pytest.approx(speed, rel=1e-8) == pytest.approx(10.4719755)
    # Linear torque-speed line: a saturated servo reaches zero net torque at the nominal speed.
    assert actuators["joint_damping_Nm_s_per_rad"] == pytest.approx(0.176 / speed, rel=1e-8)
    assert actuators["joint_damping_Nm_s_per_rad"] == pytest.approx(0.016806762, abs=1e-9)
    assert records[BASE]["contact"]["floor_friction"] == [0.9, 0.005, 0.0001]


# ---------------------------------------------------------------- mass table


def test_mass_and_centre_of_mass_numbers(records):
    base, eyes = records[BASE]["totals"], records[EYES]["totals"]
    assert base["mass_kg"] == pytest.approx(0.337776752, abs=1e-8)
    assert np.array(base["com_torso_m"]) * 1000 == pytest.approx([0.7591, 0.0673, 5.1257], abs=1e-4)
    assert base["mass_by_status_kg"] == pytest.approx({"estimated": 0.125576752, "unmeasured-nominal": 0.2122,
                                                       "measured": 0.0}, abs=1e-8)
    assert eyes["mass_kg"] == pytest.approx(0.37445878, abs=1e-8)
    assert np.array(eyes["com_torso_m"]) * 1000 == pytest.approx([1.2802, 0.1020, 5.9456], abs=1e-4)
    assert eyes["mass_by_status_kg"] == pytest.approx({"estimated": 0.15625878, "unmeasured-nominal": 0.2182,
                                                       "measured": 0.0}, abs=1e-8)
    for record in records.values():
        assert sum(p["mass_kg"] for p in record["mass_table"]) == pytest.approx(record["totals"]["mass_kg"], abs=1e-8)
        assert sum(b["mass_kg"] for b in record["bodies"]) == pytest.approx(record["totals"]["mass_kg"], abs=1e-8)


@pytest.mark.parametrize("design", DESIGNS)
def test_every_mass_has_an_honest_status(design, records, manifest):
    record = records[design]
    assert record["status"] == "simulated-model-unmeasured-parameters"
    for p in record["mass_table"]:
        assert p["status"] == ("estimated" if p["kind"] == "printed" else "unmeasured-nominal"), p["id"]
        assert p["mass_kg"] > 0 and p["basis"]
    assert not any(p["status"] == "measured" for p in record["mass_table"])
    # Eight servos at the manifest's nominal mass, the foot servos on the foot links.
    servos = [p for p in record["mass_table"] if p["row"] in ("hip-servo", "foot-servo")]
    assert len(servos) == 8 and all(p["mass_kg"] == manifest.raw["servo_model"]["mass_kg"] for p in servos)
    assert {p["body"] for p in servos if p["row"] == "foot-servo"} == {f"{leg}_lower" for leg in CORNERS}
    assert part(record, "battery")["mass_kg"] == 0.047
    assert np.array(part(record, "battery")["com_torso_m"]) * 1000 == pytest.approx([3.5, 0, -6])
    for leg in CORNERS:
        assert body(record, f"{leg}_upper")["mass_kg"] == pytest.approx(0.0042, abs=2e-5)
        assert body(record, f"{leg}_lower")["mass_kg"] == pytest.approx(0.0172, abs=2e-5)


def test_printed_masses_are_volume_times_density_times_fill(records):
    spec = twin.load_spec()
    density = spec["materials"]["pla"]["density_kg_m3"]
    fill = spec["print_profiles"]["body-kit"]["fill_fraction"]
    assert (density, fill, spec["print_profiles"]["legs"]["fill_fraction"]) == (1240.0, 0.605, 0.651)
    frame = trimesh.load(twin.design_dir(BASE) / "internal-frame.stl", force="mesh")
    assert part(records[BASE], "internal-frame")["mass_kg"] == pytest.approx(frame.volume * 1e-9 * density * fill, rel=1e-8)
    assert part(records[BASE], "internal-frame")["mass_kg"] == pytest.approx(0.045086, abs=1e-6)
    assert part(records[EYES], "internal-frame")["mass_kg"] == pytest.approx(0.059328, abs=1e-6)


def test_fill_assumptions_reproduce_the_slicer_estimates(records):
    # The declared fill fractions are tied to slicer receipts, not free numbers.
    receipt = json.loads((twin.design_dir(BASE) / "slice-check.json").read_text())
    sliced = sum(p["mass_kg"] for p in records[BASE]["mass_table"] if p["row"] in ("internal-frame", "pcb-spacer"))
    assert sliced * 1000 == pytest.approx(receipt["estimated_filament_g"], rel=0.005)  # 45.25 g
    legs = sum(p["mass_kg"] for p in records[BASE]["mass_table"] if p["row"] in ("upper-leg", "foot"))
    assert legs * 1000 == pytest.approx(32.0, rel=0.005)  # assets/print/README.md: about 32 g per set


def test_weighing_one_part_is_one_table_edit():
    spec = copy.deepcopy(twin.load_spec())
    row = next(r for r in spec["mass_table"] if r["id"] == "internal-frame")
    row.update(mass_kg=0.0500, status="measured", source="hypothetical scale reading for this test")
    weighed, nominal = twin.build(BASE, spec).record, twin.build(BASE).record
    assert part(weighed, "internal-frame")["mass_kg"] == 0.05
    assert part(weighed, "internal-frame")["status"] == "measured"
    assert weighed["totals"]["mass_by_status_kg"]["measured"] == 0.05
    delta = 0.05 - part(nominal, "internal-frame")["mass_kg"]
    assert weighed["totals"]["mass_kg"] - nominal["totals"]["mass_kg"] == pytest.approx(delta, abs=1e-9)
    # Same shape, heavier part: the centre of mass moves toward the frame.
    assert weighed["totals"]["com_torso_m"][2] < nominal["totals"]["com_torso_m"][2]


def test_status_and_mass_must_agree(tmp_path):
    spec = yaml.safe_load(twin.TWIN_PATH.read_text())
    next(r for r in spec["mass_table"] if r["id"] == "head-lid")["mass_kg"] = 0.01  # still `estimated`
    path = tmp_path / "twin.yaml"
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ValueError, match="measured"):
        twin.load_spec(path)
    spec = yaml.safe_load(twin.TWIN_PATH.read_text())
    next(r for r in spec["mass_table"] if r["id"] == "battery")["status"] = "verified"
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ValueError, match="unknown status"):
        twin.load_spec(path)


def test_mass_scaling_is_for_what_if_studies_only():
    heavier = twin.build(BASE, mass_scale={"battery": 1.1}).record
    assert part(heavier, "battery")["mass_kg"] == pytest.approx(0.0517)
    assert twin.compile_xml(twin.build(BASE, mass_scale={"battery": 1.1}).xml).body_mass.sum() == pytest.approx(
        0.337776752 + 0.0047, abs=1e-8)


# ------------------------------------------------------------------ variants


def test_two_eye_variant_changes_only_what_the_design_changed(records):
    base, eyes = records[BASE], records[EYES]
    widen = assembly(EYES)["variant"]["widen_mm"]
    for b, e in zip(base["joints"], eyes["joints"]):
        shift = (np.array(e["origin_m"]) - np.array(b["origin_m"])) * 1000
        side = 1 if "left" in b["leg"] else -1
        assert shift == pytest.approx([0, side * widen / 2, 0], abs=1e-6), b["name"]
        assert (b["axis"], b["range_rad"]) == (e["axis"], e["range_rad"])
    for leg in CORNERS:  # unchanged leg prints and servos
        for link in ("upper", "lower"):
            b, e = body(base, f"{leg}_{link}"), body(eyes, f"{leg}_{link}")
            assert (b["mass_kg"], b["com_m"], b["inertia_kg_m2"]) == (e["mass_kg"], e["com_m"], e["inertia_kg_m2"])
    extra = {p["id"] for p in eyes["mass_table"]} - {p["id"] for p in base["mass_table"]}
    assert extra == {"oled-display.2"}  # one display module per display window
    assert body(eyes, "torso")["mass_kg"] - body(base, "torso")["mass_kg"] == pytest.approx(0.036682, abs=1e-6)
    wider = eyes["contact"]["collision_boxes_m"]["torso_geom"]["half_size"][1]
    assert (wider - base["contact"]["collision_boxes_m"]["torso_geom"]["half_size"][1]) * 1000 == pytest.approx(15, abs=1e-3)


def test_six_leg_design_is_out_of_scope_with_a_stated_reason():
    assert SIX not in twin.generated_designs()
    with pytest.raises(twin.UnsupportedDesign, match=r"hip mounts \['L5', 'R5'\] have no matching joint"):
        twin.build(SIX)
    with pytest.raises(twin.UnsupportedDesign, match="no printing design"):
        twin.build("not-a-design")
