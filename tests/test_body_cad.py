"""Body detector regressions and immutable-interface checks.

Full fit acceptance is deliberately opt-in: BODY_CAD_ACCEPTANCE=1 runs the real
pipeline and fails on fit problems. Ordinary unit tests do not certify the draft.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_body import freecad_command, make_job, mesh_checks


def test_frozen_leg_and_servo_interfaces():
    lock = json.loads((ROOT/"assets/body/frozen-inputs.json").read_text())
    for path, expected in lock.items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected, path


def test_committed_body_review_is_fresh_and_complete():
    out=ROOT/"assets/body/v1"
    report=json.loads((out/"report.json").read_text())
    assert report["parameters"] == json.loads((ROOT/"assets/body/params.json").read_text())
    assert report["rom_complete"] and report["native_assembly_unchanged"]
    for path,expected in report["input_hashes"].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected, f"Regenerate body review: {path}"
    assembly=json.loads((out/"assembly.json").read_text())
    for path,expected in assembly["export_hashes"].items():
        assert hashlib.sha256((out/path).read_bytes()).hexdigest()==expected,path
    assert len(report["body_component_pairs"]) == len(report["parts"])*len({r["component"] for r in report["body_component_pairs"]})
    for name in ['assembled.png','front.png','rear.png','top-open.png','exploded.png','rom-sweep.png']:
        assert (out/name).stat().st_size > 1000


def test_rom_job_uses_manifest_ranges_and_moves_both_links():
    from sim.manifest import load_manifest
    manifest = load_manifest()
    params = json.loads((ROOT/"assets/body/params.json").read_text())
    job = make_job(params)
    assert len(job["legs"]) == 4
    for leg in job["legs"]:
        for i, role in enumerate(["hip", "foot"]):
            joint = manifest.joint(leg[role+"_joint"])
            expected = np.degrees(manifest.internal_range(joint))
            samples = sorted({r[i] for r in leg["poses"] if r[2] == role})
            assert np.allclose([samples[0], samples[-1]], expected)
            assert max(np.diff(samples)) <= params["checks"]["rom_step_deg"] + 1e-8
        assert len([r for r in leg["poses"] if r[2] == "coupled-grid"]) == 9


def test_occ_detector_rejects_overlap_and_tight_fit(tmp_path):
    try:
        executable, env = freecad_command()
    except RuntimeError:
        if os.getenv("REQUIRE_BODY_CAD") == "1":
            raise
        pytest.skip("FreeCAD interpreter unavailable; BODY-CAD CI runs this test")
    # Actual boolean volumes/distances, including containment and allowed contact.
    script = """
import sys
sys.path.insert(0, sys.argv[1])
from body_checks import pair
from body_cad import box, cylinder, triangulate, write_3mf, export_step
from body_checks import fasteners
from pathlib import Path
import tempfile
a=box([10,10,10],[0,0,0])
assert pair(a,box([2,2,2],[1,1,1]),.6,.001)['status']=='INTERFERENCE'
assert pair(a,box([2,2,2],[9,1,1]),.6,.001,True)['status']=='INTERFERENCE'
assert pair(a,box([2,2,2],[10,1,1]),.6,.001,True)['status']=='PASS'
assert pair(a,box([2,2,2],[10.3,1,1]),.6,.001)['status']=='CLEARANCE'
assert pair(a,box([2,2,2],[10.7,1,1]),.6,.001)['status']=='PASS'
faces=[f.BoundBox for f in a.Faces]
assert pair(a,box([2,2,2],[1,1,1]),.6,.001,face_bounds=faces)['status']=='INTERFERENCE'
# A deliberately displaced standoff axis must hit the real board rather than
# passing because the same nominal hole coordinate was compared to itself.
board=box([10,10,1.6],[0,0,10]).cut(cylinder(1,3,[3,3,9]))
tray=cylinder(2.7,10,[3,3,0]).cut(cylinder(.7,12,[3,3,-1]))
d={'params':{'carrier_screw_diameter_mm':1.6,'carrier_pilot_diameter_mm':1.4,
 'carrier_standoff_radius_mm':2.7,'carrier_z_mm':10,'deck_z_mm':0},
 'components':{'electronics.PerfboardReference':board},
 'parts':{'carrier-tray':tray,'interface-frame':a},'carrier_holes_mm':[(3,3)],'anchors_mm':[]}
assert fasteners(d)[0]['status']=='PASS'
d['carrier_holes_mm']=[(4,3)]
assert fasteners(d)[0]['status']=='FAIL'
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'part.3mf'; mesh=triangulate(a)
 write_3mf(p,mesh,'test'); first=p.read_bytes(); write_3mf(p,mesh,'test'); assert p.read_bytes()==first
 p=Path(td)/'part.step'; export_step(a,p); first=p.read_bytes(); export_step(a,p); assert p.read_bytes()==first
print('detector mutations passed')
"""
    result = subprocess.run([executable,"-c",script,str(ROOT/"tools")],env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode == 0, result.stdout+result.stderr
    assert "detector mutations passed" in result.stdout


def test_thickness_detector_finds_thin_wall(tmp_path):
    import trimesh
    mesh = trimesh.creation.box([20,10,.8])
    mesh.export(tmp_path/"thin.stl")
    (tmp_path/"assembly.json").write_text(json.dumps({"parts":[{
        "id":"body.thin","files":{"stl":"thin.stl"},"print_rotation_axis_angle":[1,0,0,0],"frozen_upstream":False}]}))
    params=json.loads((ROOT/"assets/body/params.json").read_text())
    result=mesh_checks(tmp_path,params)["thin"]
    assert result["wall_status"] == "FAIL"
    assert result["sampled_minimum_wall_mm"] == pytest.approx(.8, abs=1e-5)


def test_motion_bvh_detects_containment_and_rotated_interference():
    import trimesh
    from body_motion import collision_object, check_pair
    body=trimesh.creation.box([10,10,10])
    moving=trimesh.creation.box([2,2,2])
    a,b=collision_object(body),collision_object(moving)
    transform=np.eye(4)
    assert check_pair(body,moving,a,b,transform,.6)["status"] == "CONTAINMENT"
    transform[:3,3]=[7,0,0]
    assert check_pair(body,moving,a,b,transform,.6)["status"] == "PASS"
    transform=trimesh.transformations.rotation_matrix(np.pi/4,[0,0,1])
    transform[:3,3]=[5.5,0,0]
    assert check_pair(body,moving,a,b,transform,.6)["status"] == "CONTACT_OR_INTERFERENCE"


@pytest.mark.skipif(os.getenv("BODY_CAD_ACCEPTANCE") != "1", reason="Run BODY_CAD_ACCEPTANCE=1 for full fit acceptance; draft is not certified")
def test_body_geometry_acceptance(tmp_path):
    result = subprocess.run([sys.executable,str(ROOT/"tools/check_body.py"),"--output",str(tmp_path)],cwd=ROOT,timeout=7200)
    report=json.loads((tmp_path/"report.json").read_text())
    assert result.returncode == 0, report["summary"]
    assert report["geometry_pass"] and report["rom_complete"]
