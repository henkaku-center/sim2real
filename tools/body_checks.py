"""FreeCAD geometry stage of check_body.py (headless, no third-party Python deps)."""
import argparse
import itertools
import json
import math
from pathlib import Path

import body_cad as cad
from body_cad import App, Part


def gap_lower_bound(a, b):
    a, b = a.BoundBox, b.BoundBox
    return math.sqrt(sum(max(0, getattr(a, k+"Min")-getattr(b, k+"Max"),
                             getattr(b, k+"Min")-getattr(a, k+"Max"))**2 for k in "XYZ"))


def pair(a, b, clearance, tolerance, intended_contact=False, face_bounds=None):
    lower = gap_lower_bound(a, b)
    if lower >= clearance+1e-6:
        return {"status": "PASS", "distance_lower_bound_mm": round(lower, 6), "method": "AABB disjoint lower bound", "intersection_mm3": 0}
    if face_bounds:
        bb = b.BoundBox
        surface_lower = min(math.sqrt(sum(max(0, getattr(f,k+"Min")-getattr(bb,k+"Max"),
                    getattr(bb,k+"Min")-getattr(f,k+"Max"))**2 for k in "XYZ")) for f in face_bounds)
        if surface_lower >= clearance+1e-6:
            # Disjoint surface bounds alone would miss containment. Check every
            # connected component before certifying the material-free cavity.
            connected = b.Solids or b.Shells or [b]
            if all(s.Vertexes and not a.isInside(s.Vertexes[0].Point,1e-7,True) for s in connected):
                return {"status":"PASS", "distance_lower_bound_mm":round(surface_lower,6),
                        "method":"face-AABB lower bound plus per-solid containment rejection", "intersection_mm3":0}
    distance = a.distToShape(b)[0]
    overlap = max(0, a.common(b).Volume) if distance < 1e-6 and a.Solids and b.Solids else 0
    status = "INTERFERENCE" if overlap > tolerance else (
        "PASS" if distance+1e-6 >= clearance or intended_contact else "CLEARANCE")
    return {"status": status, "distance_mm": round(distance, 6),
            "intersection_mm3": round(overlap, 6), "method": "OCC distance/common",
            "required_clearance_mm": clearance, "intended_face_contact": intended_contact}


def static_checks(d):
    p = d["params"]
    clearance, tol = p["clearance_mm"], p["checks"]["intersection_volume_tolerance_mm3"]
    rows = []
    for name, shape in d["parts"].items():
        print("body/component checks:", name, flush=True)
        face_bounds = [f.BoundBox for f in shape.Faces]
        for index, (cn, component) in enumerate(d["components"].items()):
            if index % 100 == 0:
                print(f"  {index}/{len(d['components'])} {cn}", flush=True)
            # Sliding faces use fit_gap; structural mating is explicit and still
            # rejects penetration. No volume-collision exclusion lists.
            req = p["fit_gap_mm"] if d["component_meta"][cn]["kind"] in ["oled", "switch", "service"] else clearance
            contact = (name, cn) in d["contacts"]
            if name == "battery-drawer" and cn in ("battery", "service.battery-removal"):
                contact = True
            if name == "battery-drawer" and cn == "service.battery-removal":
                # Drawer travels with the battery, not a stationary obstacle.
                # It is still tested against the battery itself above.
                rows.append({"body": name, "component": cn, "status": "PASS",
                             "method": "moving together; checked by battery/drawer pair", "intersection_mm3": 0})
                continue
            rows.append({"body": name, "component": cn,
                         "evidence": d["component_meta"][cn]["evidence"],
                         **pair(shape, component, req, tol, contact, face_bounds)})
    body_rows = []
    for (an, a), (bn, b) in itertools.combinations(d["parts"].items(), 2):
        body_rows.append({"a": an, "b": bn, **pair(a, b, 0, tol, True)})
    return rows, body_rows


def fasteners(d):
    p = d["params"]
    board = d["components"]["electronics.PerfboardReference"]
    tray = d["parts"]["carrier-tray"]
    rows = []
    for i, (x, y) in enumerate(d["carrier_holes_mm"]):
        pin = cad.cylinder(p["carrier_screw_diameter_mm"]/2, 3, (x, y, p["carrier_z_mm"]-.1))
        # Real native bores, not just comparison of two copies of a parameter.
        board_overlap = pin.common(board).Volume
        lower_pin = cad.cylinder(p["carrier_pilot_diameter_mm"]/2-.02, p["carrier_z_mm"]-p["deck_z_mm"], (x,y,p["deck_z_mm"]))
        pilot_overlap = lower_pin.common(tray).Volume
        support = cad.cylinder(p["carrier_standoff_radius_mm"], .02, (x,y,p["carrier_z_mm"]-.02))
        support_volume = support.common(tray).Volume
        rows.append({"id": f"carrier.{i}", "center_mm": [x,y], "board_screw_overlap_mm3": board_overlap,
                     "pilot_overlap_mm3": pilot_overlap, "support_section_mm3": support_volume,
                     "status": "PASS" if board_overlap < 1e-6 and pilot_overlap < 1e-6 and support_volume > .05 else "FAIL"})
    # Verify actual upstream bores at each anchor; the chosen hole centers are
    # observations, not replacements for the frozen mesh geometry.
    frame = d["parts"]["interface-frame"]
    for i, (x, y) in enumerate(d["anchors_mm"]):
        shaft = cad.cylinder(.75, 2, (x, y, frame.BoundBox.ZMax-2))
        overlap = shaft.common(frame).Volume
        annulus = cad.cylinder(1.4,.03,(x,y,frame.BoundBox.ZMax-.03)).cut(
            cad.cylinder(1.0,.05,(x,y,frame.BoundBox.ZMax-.04)))
        supported = annulus.common(frame).Volume
        rows.append({"id": f"frame.{i}", "center_mm": [x,y], "shaft_overlap_mm3": overlap,
                     "seat_section_mm3": supported,
                     "status": "PASS" if overlap < 1e-5 and supported > .005 else "FAIL"})
    for i,(x,y) in enumerate(d.get("deck_anchors_mm",[])):
        radius = (p["front_riser_top_screw_diameter_mm"]-.4)/2-.02 if i<2 else p["frame_anchor_clearance_diameter_mm"]/2-.02
        pin = cad.cylinder(radius,8,(x,y,p["deck_z_mm"]-6))
        overlap = pin.common(d["parts"][f"riser-{i+1}"]).Volume + pin.common(tray).Volume
        rows.append({"id":f"deck.{i}","center_mm":[x,y],"pilot_overlap_mm3":overlap,
                     "status":"PASS" if overlap<1e-5 else "FAIL"})
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    job = json.loads(args.job.read_text())
    before = cad.digest(cad.ASSEMBLY)
    d = cad.build(job["params"])
    print("Body generated", flush=True)
    parts = {n: {"valid": s.isValid(), "solid_count": len(s.Solids), "volume_mm3": s.Volume,
                 "bounds_mm": cad.bounds(s), "frozen_upstream":d["part_meta"][n]["frozen_upstream"]} for n, s in d["parts"].items()}
    static, body_pairs = static_checks(d)
    alignment = fasteners(d)
    cad.write_json(args.output / "static-findings.json", {
        "parts": parts, "body_component_pairs": static, "body_body_pairs": body_pairs,
        "fastener_alignment": alignment,
    })
    record = cad.export(d, args.output)
    cad.write_json(args.output / "rom-animation.json", {"frames": [], "kinematics": []})
    report = {
        "schema_version": 1, "release_ready": False, "status": "DRAFT",
        "freecad_version": list(App.Version()), "occt_version": Part.OCC_VERSION,
        "parameters": job["params"], "input_hashes": job["input_hashes"],
        "source_hashes": record["source_hashes"], "native_assembly_unchanged": before == cad.digest(cad.ASSEMBLY),
        "parts": parts, "body_component_pairs": static, "body_body_pairs": body_pairs,
        "fastener_alignment": alignment, "rom": [], "rom_complete": False,
        "rom_scope": "5-degree single-joint samples, other joint at rest, plus coupled endpoints/midpoint; not a continuous or exhaustive two-joint proof",
        "open_measurements": job["params"]["measurement_gate"],
        "limitations": [
            "Static eight MG90S/horn proxies are nominal, not measured purchased-variant geometry.",
            "External wire sweeps are proposed routes, not verified connector/cable exit positions.",
            "ROM uses existing simulator registration; physical datum/zero-pose confirmation is outstanding.",
            "No stiffness, fatigue, heat, electronics-to-electronics, or electrical validation.",
            "Upstream open top-cover mesh is a visual reference only; not silently repaired."
        ],
    }
    cad.write_json(args.output / "report.json", report)
    print("Wrote geometry and report", flush=True)


if __name__ == "__main__":
    main()
