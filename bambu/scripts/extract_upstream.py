"""Extract the upstream Sesame STEP assembly into per-solid STL leaves + parts.json.

Run with FreeCAD's bundled Python (1.1.x):
    /Applications/FreeCAD.app/Contents/Resources/bin/python -I \
        bambu/scripts/extract_upstream.py \
        bambu/vendor/sesame-robot/hardware/cad/Sesame-ESP32-v122.step bambu/build/upstream

Coordinates are left in the upstream STEP frame (mm, y-up); sesame_model.py
converts them. Servo-spline cylinder axes are recorded for leg kinematics.
"""
import json
import os
import sys

FREECAD_LIB = os.environ.get("FREECAD_LIB", "/Applications/FreeCAD.app/Contents/Resources/lib")
sys.path.append(FREECAD_LIB)
import FreeCAD  # noqa: E402
import Import  # noqa: E402
import MeshPart  # noqa: E402
import Part  # noqa: E402

MIN_MESH_VOLUME_MM3 = 50.0
SPLINE_VOLUME_RANGE_MM3 = (100.0, 140.0)


def main(step, out_dir):
    leaves_dir = os.path.join(out_dir, "leaves")
    os.makedirs(leaves_dir, exist_ok=True)
    doc = FreeCAD.newDocument("upstream")
    Import.insert(step, doc.Name)
    rows = []
    for o in doc.Objects:
        if o.TypeId != "Part::Feature" or o.Shape.isNull() or not o.Shape.Solids:
            continue
        s = o.Shape.copy()
        s.Placement = o.getGlobalPlacement()
        b = s.BoundBox
        chain, p = [], o
        while p.InList:
            p = p.InList[0]
            chain.append(p.Label)
        row = {"name": o.Name, "label": o.Label, "vol": s.Volume,
               "com": list(s.CenterOfGravity) if s.Volume > 0 else None,
               "lo": [b.XMin, b.YMin, b.ZMin], "hi": [b.XMax, b.YMax, b.ZMax],
               "chain": chain, "stl": None, "spline_axis": None}
        lo, hi = SPLINE_VOLUME_RANGE_MM3
        if lo < s.Volume < hi:
            cyl = [f for f in s.Faces if isinstance(f.Surface, Part.Cylinder)]
            if cyl:
                f = max(cyl, key=lambda f: f.Area)
                row["spline_axis"] = list(f.Surface.Axis)
        if s.Volume > MIN_MESH_VOLUME_MM3:
            m = MeshPart.meshFromShape(Shape=s, LinearDeflection=0.2, AngularDeflection=0.3)
            row["stl"] = f"leaves/{o.Name}.stl"
            m.write(os.path.join(out_dir, row["stl"]))
        rows.append(row)
    with open(os.path.join(out_dir, "parts.json"), "w") as fh:
        json.dump({"source": os.path.basename(step), "units": "mm", "frame": "upstream STEP (y-up)",
                   "parts": rows}, fh, indent=1)
    print(f"{len(rows)} solids, {sum(1 for r in rows if r['stl'])} meshed")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
