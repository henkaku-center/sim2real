"""Scaled test print of the dome: the hole pattern becomes thin skins (blind pockets).

Run with FreeCAD's bundled Python after design.py has written the job JSON:
    /Applications/FreeCAD.app/Contents/Resources/bin/python -I build_test_dome.py \
        bambu/build/job.json bambu/stl/test [--diameter 100] [--thickness 3] [--skin 1]
The dome of the job (centre, rim, holes, knee slots) is scaled uniformly so its outer
diameter is `--diameter`; the wall thickness is NOT scaled.  Each rhombic hole is replaced
by a pocket that leaves a spherical skin of `--skin` mm, cut either from the outside
(pattern visible, inner face smooth) or from the inside (outer face a smooth sphere).
Writes <out_dir>/test-dome-d<D>-<side>.{step,stl} on the bed (rim down) and test-dome.json.
Dome only: no mast, socket or saddle, so this piece does not mount on the robot.
"""
import argparse
import json
import os
import sys

sys.path.append(os.environ.get("FREECAD_LIB", "/Applications/FreeCAD.app/Contents/Resources/lib"))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import FreeCAD  # noqa: E402
import Part  # noqa: E402
from build_shell import V, export, vec  # noqa: E402


def test_dome(d, k, t, skin, side):
    """Scaled dome; `k` scales every length of the job except the wall `t` and `skin`."""
    c = vec(d["center"]) * k
    r = d["radius"] * k
    big = 4 * r
    body = Part.makeSphere(r, c).cut(Part.makeSphere(r - t, c))
    body = body.common(Part.makeBox(big, big, big, V(c.x - big / 2, c.y - big / 2, d["rim_z"] * k)))

    prisms = []
    for h in d["holes"]:
        n, up = vec(h["dir"]), vec(h["up"])
        east = up.cross(n)
        p = c + n * (r + 1.0)
        a, b = h["half_meridian"] * k, h["half_azimuth"] * k
        pts = [p + up * a, p + east * b, p - up * a, p - east * b]
        face = Part.Face(Part.makePolygon(pts + [pts[0]]))
        prisms.append(face.extrude(n * -(t + 2.5)))
    prisms = Part.makeCompound(prisms)
    if side == "outer":  # keep the inner `skin` of the wall
        pockets = prisms.cut(Part.makeSphere(r - t + skin, c))
    else:  # keep the outer `skin` of the wall
        pockets = prisms.common(Part.makeSphere(r - skin, c))
    body = body.cut(pockets)

    for s in d["slots"]:
        axis = vec(s["axis"])
        base = vec(s["knee"]) * k + axis * (s["axial_lo"] * k)
        body = body.cut(Part.makeCylinder(s["radius"] * k, (s["axial_hi"] - s["axial_lo"]) * k, base, axis))
    return body.removeSplitter()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("out_dir")
    ap.add_argument("--diameter", type=float, default=100.0, help="outer sphere diameter, mm")
    ap.add_argument("--thickness", type=float, default=3.0, help="wall thickness, mm (not scaled)")
    ap.add_argument("--skin", type=float, default=1.0, help="wall left under each hole, mm")
    ap.add_argument("--side", choices=("outer", "inner", "both"), default="both", help="where the pockets open")
    args = ap.parse_args()
    if not 0 < args.skin < args.thickness:
        raise SystemExit("need 0 < skin < thickness")
    d = json.load(open(args.job))["dome"]
    k = args.diameter / (2 * d["radius"])
    os.makedirs(args.out_dir, exist_ok=True)
    report = {"source_job": os.path.abspath(args.job), "scale": k, "radius_mm": d["radius"] * k,
              "thickness_mm": args.thickness, "skin_mm": args.skin, "pockets": len(d["holes"]), "parts": {}}
    for side in ("outer", "inner") if args.side == "both" else (args.side,):
        shape = test_dome(d, k, args.thickness, args.skin, side)
        if not shape.isValid() or len(shape.Solids) != 1:
            raise SystemExit(f"{side}: invalid or multi-solid result ({len(shape.Solids)} solids)")
        name = f"test-dome-d{args.diameter:g}-{side}"
        s = export(shape.Solids[0], os.path.join(args.out_dir, name), FreeCAD.Placement())
        bb = s.BoundBox
        report["parts"][name] = {"volume_mm3": s.Volume, "mass_g_pla_solid": s.Volume / 1000 * 1.24,
                                 "bbox_mm": [bb.XLength, bb.YLength, bb.ZLength]}
    json.dump(report, open(os.path.join(args.out_dir, "test-dome.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
