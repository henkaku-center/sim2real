"""One agent command: generate geometry, check fit/ROM/walls, and render review.

Run with `uv run python tools/check_body.py`. FreeCAD is a separate interpreter;
the uv environment owns manifest/mesh/report tooling. Default exit is nonzero on
geometric failures; --require-release additionally rejects unmeasured hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.manifest import load_manifest
from sim import build_mjcf, prepare_assets


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freecad_command():
    executable = os.environ.get("FREECAD_PYTHON")
    mac = Path("/Applications/FreeCAD.app/Contents/Resources/bin/python")
    if executable:
        executable = str(Path(executable).resolve())
    elif mac.exists():
        executable = str(mac)
    else:
        raise RuntimeError("Set FREECAD_PYTHON to the Python in a FreeCAD 1.1.3 environment (see reference/BODY-CAD.md)")
    env = os.environ.copy()
    lib = os.environ.get("FREECAD_LIB") or (str(mac.parent.parent / "lib") if executable == str(mac) else "")
    if lib:
        env["PYTHONPATH"] = lib
    env["QT_QPA_PLATFORM"] = "offscreen"
    return executable, env


def make_job(params):
    manifest = load_manifest()
    legs = []
    step = params["checks"]["rom_step_deg"]
    if not 0 < step <= 5:
        raise ValueError("ROM sampling must be positive and no coarser than 5 degrees")
    for hip in [j for j in manifest.joints if j.role == "hip"]:
        foot = next(j for j in manifest.joints if j.leg == hip.leg and j.role == "foot")
        sy = 1 if "left" in hip.leg else -1
        fx = 1 if "front" in hip.leg else -1
        hc = np.array([fx*build_mjcf.HIP_X, sy*build_mjcf.HIP_Y, build_mjcf.LEG_PLANE_DZ])*1000
        fc = hc + [0, sy*build_mjcf.UPPER_LEN*1000, 0]
        ranges = [np.degrees(manifest.internal_range(j)).tolist() for j in [hip, foot]]
        samples = [np.linspace(lo, hi, math.ceil((hi-lo)/step)+1).tolist() for lo, hi in ranges]
        poses = [(q, 0, "hip") for q in samples[0]]+[(0,q,"foot") for q in samples[1]]
        poses += [(h, f, "coupled-grid") for h in [ranges[0][0], sum(ranges[0])/2, ranges[0][1]]
                  for f in [ranges[1][0], sum(ranges[1])/2, ranges[1][1]]]
        leg = {"name": hip.leg, "hip_joint": hip.name, "foot_joint": foot.name,
               "hip_center_mm": hc.tolist(), "foot_center_mm": fc.tolist(),
               "hip_axis": [0,0,hip.sign], "foot_axis": [-sy,0,0],
               "soft_ranges_internal_deg": ranges, "poses": poses}
        for role, origin in [("upper",hc),("lower",fc)]:
            source, asm_origin, extra = prepare_assets.PARTS[hip.leg+"_"+role]
            rot = extra @ prepare_assets.M_ASM
            mat = np.eye(4)
            mat[:3,:3], mat[:3,3] = rot, origin-rot@asm_origin
            leg[role] = {"source": "assets/stl/upstream/"+source, "source_to_rest_matrix": mat.ravel().tolist()}
        legs.append(leg)
    files = [ROOT/"manifest/robot.yaml", ROOT/"sim/build_mjcf.py", ROOT/"sim/prepare_assets.py",
             ROOT/"tools/body_cad.py", ROOT/"tools/body_checks.py", ROOT/"tools/check_body.py",
             ROOT/"tools/body_motion.py", ROOT/"tools/render_body.py"]
    return {"params": params, "legs": legs,
            "input_hashes": {str(p.relative_to(ROOT)): sha(p) for p in files}}


def mesh_checks(out, params):
    assembly = json.loads((out/"assembly.json").read_text())
    results = {}
    for part in assembly["parts"]:
        name = part["id"].removeprefix("body.")
        mesh = trimesh.load(out/part["files"]["stl"], force="mesh")
        # Deterministic face-centroid rays into material. This is a sampled local
        # thickness screen, not a certified global medial-axis thickness proof.
        limit = params["checks"]["wall_sample_limit"]
        ids = np.unique(np.linspace(0, len(mesh.faces)-1, min(limit,len(mesh.faces))).astype(int))
        centers, normals = mesh.triangles_center[ids], mesh.face_normals[ids]
        eps = .001
        origins = centers - normals*eps
        locations, ray_ids, _ = mesh.ray.intersects_location(origins, -normals, multiple_hits=False)
        thickness = np.linalg.norm(locations-origins[ray_ids],axis=1)+eps
        below = thickness < params["minimum_wall_mm"]-.03
        fail_ids = ray_ids[below]
        rotation = part["print_rotation_axis_angle"]
        transform = trimesh.transformations.rotation_matrix(math.radians(rotation[3]),rotation[:3])
        printable = mesh.copy()
        printable.apply_transform(transform)
        zmin = printable.bounds[0,2]
        # Downward triangles off the bed exceed the slope threshold. Reports
        # possible bridges too; support choice requires slicer review.
        overhang = (printable.face_normals[:,2] < -math.sin(math.radians(params["checks"]["overhang_from_vertical_deg"]))) & (printable.triangles_center[:,2] > zmin+.25)
        results[name] = {
            "watertight": bool(mesh.is_watertight), "winding_consistent": bool(mesh.is_winding_consistent),
            "positive_volume": bool(mesh.volume>0), "connected_meshes": len(mesh.split(only_watertight=False)),
            "sampled_minimum_wall_mm": float(thickness.min()) if len(thickness) else None,
            "wall_samples": len(ids), "ray_hits": len(thickness), "thin_samples": int(below.sum()),
            "thin_sample_locations_mm": centers[fail_ids].round(4).tolist()[:30],
            "wall_status": "FAIL" if below.any() or len(thickness)!=len(ids) else "PASS-SAMPLED",
            "wall_scope": "face-centroid inward rays; finite sampling can miss small features; no global guarantee",
            "print_size_mm": printable.extents.tolist(),
            "fits_build_volume": bool(np.all(printable.extents<=params["checks"]["build_volume_mm"])),
            "overhang_area_mm2": float(printable.area_faces[overhang].sum()),
            "overhang_triangles": int(overhang.sum()), "support_review_required": bool(overhang.any()),
            "frozen_upstream": part["frozen_upstream"],
        }
    return results


def summarize(report):
    failures = [r for r in report["body_component_pairs"] if r["status"] != "PASS"]
    body_failures = [r for r in report["body_body_pairs"] if r["status"] != "PASS"]
    rom = [r for r in report["rom"] if r["status"] != "PASS"]
    invalid = [n for n,r in report["parts"].items() if not r["valid"] or r["solid_count"]!=1]
    mesh_failures = [n for n,r in report["mesh_checks"].items() if not r["watertight"] or not r["winding_consistent"] or r["wall_status"]=="FAIL" or not r["fits_build_volume"]]
    report["summary"] = {"body_component_pairs": len(report["body_component_pairs"]),
                         "static_failures": len(failures), "body_body_failures": len(body_failures),
                         "rom_pairs": len(report["rom"]), "rom_failures": len(rom),
                         "invalid_parts": invalid, "mesh_or_wall_failures": mesh_failures,
                         "alignment_failures": sum(r["status"]!="PASS" for r in report["fastener_alignment"])}
    frozen={n for n,r in report["parts"].items() if r.get("frozen_upstream")}
    report["summary"]["new_body_static_failures"] = sum(r["body"] not in frozen for r in failures)
    report["summary"]["frozen_interface_static_failures"] = sum(r["body"] in frozen for r in failures)
    report["summary"]["new_body_rom_failures"] = sum(r["body"] not in frozen for r in rom)
    report["summary"]["frozen_interface_rom_failures"] = sum(r["body"] in frozen for r in rom)
    report["new_body_geometry_pass"] = not (report["summary"]["new_body_static_failures"] or
        report["summary"]["new_body_rom_failures"] or body_failures or set(invalid)-frozen or
        set(mesh_failures)-frozen or report["summary"]["alignment_failures"]) and report["rom_complete"]
    report["geometry_pass"] = not (failures or body_failures or rom or invalid or mesh_failures or report["summary"]["alignment_failures"]) and report["rom_complete"]
    report["status"] = "PASS-GEOMETRY-NEEDS-HARDWARE" if report["geometry_pass"] else "FAIL-DRAFT"
    report["release_ready"] = report["geometry_pass"] and not report["open_measurements"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--params", type=Path, default=ROOT/"assets/body/params.json")
    parser.add_argument("--output", type=Path, default=ROOT/"assets/body/v1")
    parser.add_argument("--skip-rom", action="store_true", help="Diagnostic only: incomplete report, cannot pass")
    parser.add_argument("--postprocess-only", action="store_true")
    parser.add_argument("--require-release", action="store_true")
    args = parser.parse_args()
    params = json.loads(args.params.read_text())
    out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    if not args.postprocess_only:
        executable, env = freecad_command()
        # Invalidate previous acceptance before doing any expensive kernel work.
        # A crash must never leave yesterday's PASS beside partially new exports.
        write_json(out/"report.json", {"schema_version":1,"status":"BUILD-INCOMPLETE",
                                      "release_ready":False,"geometry_pass":False,
                                      "parameters":params})
        with tempfile.TemporaryDirectory(prefix="sesame-body-") as tmp:
            job_path = Path(tmp)/"job.json"
            write_json(job_path, make_job(params))
            # Static solid checks/export run in FreeCAD; motion runs below in FCL.
            cmd = [executable,"-u",str(ROOT/"tools/body_checks.py"),"--job",str(job_path),"--output",str(out)]
            result = subprocess.run(cmd,env=env,cwd=ROOT)
            if result.returncode:
                write_json(out/"report.json", {"schema_version":1,"status":"BUILD-ERROR",
                    "release_ready":False,"geometry_pass":False,"parameters":params,
                    "kernel_exit_code":result.returncode})
                return 2
    report = json.loads((out/"report.json").read_text())
    if report.get("parameters") != params:
        raise ValueError("Report parameters differ from requested parameters; rebuild before postprocessing")
    if not args.skip_rom:
        from body_motion import run_motion
        report["rom"] = run_motion(out, make_job(params), ROOT)
        report["rom_complete"] = True
        report["rom_backend"] = "python-fcl 0.7.0.11 / FCL 0.7 triangle BVH + containment; mesh deflection added to clearance"
    report["mesh_checks"] = mesh_checks(out, params)
    summarize(report)
    write_json(out/"report.json",report)
    from render_body import render_review
    render_review(out,report)
    print(json.dumps({"status":report["status"],**report["summary"]},indent=2))
    return 0 if report["release_ready" if args.require_release else "geometry_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
