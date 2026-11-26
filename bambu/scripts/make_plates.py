"""Arrange the print parts on Bambu Lab P1S plates (256 x 256 mm) and write plain 3MF projects.

    uv run python -I bambu/scripts/make_plates.py [--variant v3-headarms]

Plate 1a: the dome alone.  Plate 1b: the crown on its print brace (crown-print.stl), the lid and the
key.  The two tall parts get plates of their own: nested in one plate, a crown that tipped over took
the dome with it (failed print, 2026-11-12).  Plate 2: the V3 kit parts (frame, bottom cover, head
cover, four PCB spacers).  Every object keeps its print orientation; positions are plate
coordinates (origin at the front-left corner).  Checks: inside the bed with brims, pairwise gaps.
Writes bambu/stl/v3crown/plates/plate*.3mf and a JSON report.
"""
import json
import pathlib
import sys
import zipfile

import fcl
import numpy as np
import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analyze import bvh  # noqa: E402
from sesame_model import BAMBU, ROOT  # noqa: E402

BED, MARGIN, BRIM, DOME_BRIM, MIN_GAP = 256.0, 3.0, 5.0, 10.0, 5.0
NEST_HEAD_DEG, NEST_MIN_GAP = 65.0, 2.5  # v3-headarms one-run plate: head inside the dome
V, K = BAMBU / "stl" / "v3crown", ROOT / "reference" / "frame-and-cover_261105"
OUT = V / "plates"


def place(path, x, y):
    m = trimesh.load(path)
    m.apply_translation([x - m.bounds[:, 0].mean(), y - m.bounds[:, 1].mean(), -m.bounds[0][2]])
    return m


def write_3mf(path, objects):
    """Minimal 3MF (core spec): one object per part, absolute coordinates in mm."""
    res, build = [], []
    for i, (name, m) in enumerate(objects.items(), start=1):
        vs = "".join(f'<vertex x="{v[0]:.4f}" y="{v[1]:.4f}" z="{v[2]:.4f}"/>' for v in m.vertices)
        ts = "".join(f'<triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>' for f in m.faces)
        res.append(f'<object id="{i}" name="{name}" type="model"><mesh><vertices>{vs}</vertices>'
                   f'<triangles>{ts}</triangles></mesh></object>')
        build.append(f'<item objectid="{i}"/>')
    model = ('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<resources>{"".join(res)}</resources><build>{"".join(build)}</build></model>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns='
                   '"http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" '
                   'ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension='
                   '"model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns='
                   '"http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target='
                   '"/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
                   '</Relationships>')
        z.writestr("3D/3dmodel.model", model)


def check(plate, brims, min_gap=MIN_GAP):
    rows, ok = {}, True
    for n, m in plate.items():
        lo, hi, b = m.bounds[0], m.bounds[1], brims.get(n, 0.0)
        inside = lo[0] - b >= 0 and lo[1] - b >= 0 and hi[0] + b <= BED and hi[1] + b <= BED and hi[2] <= BED
        rows[n] = {"xy_mm": [lo[:2].round(1).tolist(), hi[:2].round(1).tolist()], "height_mm": round(float(hi[2]), 1),
                   "inside_bed": bool(inside)}
        ok &= bool(inside)
    names, gaps = list(plate), {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            g = fcl.distance(bvh(plate[a]), bvh(plate[b]), fcl.DistanceRequest(), fcl.DistanceResult())
            gaps[f"{a} / {b}"] = round(float(g), 1)
            ok &= g >= min_gap
    return {"parts": rows, "gaps_mm": gaps, "ok": bool(ok)}


def main_headarms():
    """Variant v3-headarms: plate 1 = the dome alone (tree supports for the cap); plate 2 = the body parts with the new head
    (head-mount.stl, rim down, supports under the arms) instead of the kit head cover, plus the kit lid."""
    v = BAMBU / "stl" / "v3headarms"
    out = v / "plates"
    out.mkdir(parents=True, exist_ok=True)
    c = BED / 2
    dome = v / "shell-dome-print.stl"  # the dome with its knee-slot membranes, when built
    p1 = {"shell-dome": place(dome if dome.exists() else v / "shell-dome.stl", c, c)}
    hm = trimesh.load(v / "head-mount.stl").extents
    p2 = {"head-mount": place(v / "head-mount.stl", MARGIN + 5 + hm[0] / 2, c)}
    x2, y = MARGIN + 5 + hm[0] + 10, MARGIN + 5
    for name, f in (("internal-frame", "internal-frame-print.stl"), ("bottom-cover", "bottom-cover.stl")):
        e = trimesh.load(K / f).extents
        p2[name] = place(K / f, x2 + e[0] / 2, y + e[1] / 2)
        y += e[1] + 8
    x3 = x2 + max(trimesh.load(K / f).extents[0] for f in ("internal-frame-print.stl", "bottom-cover.stl")) + 8
    m = trimesh.load(K / "head-lid-print.stl")
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
    m.apply_translation([x3 - m.bounds[0][0], MARGIN + 5 - m.bounds[0][1], -m.bounds[0][2]])
    p2["head-lid"] = m
    for i in range(4):
        p2[f"pcb-spacer-{i + 1}"] = place(K / "pcb-spacer.stl", x3 + 6, m.bounds[1][1] + 12 + i * 12)
    # optional one-run layout: the head stands on the bed inside the dome, turned so its arm tips point between a
    # side lug and a knee slot (65 deg: 2.6 mm to the dome wall, vs 1.2 mm unturned).  Outer brim only on the dome.
    p3 = {"shell-dome": p1["shell-dome"].copy()}
    h = trimesh.load(v / "head-mount.stl")
    h.apply_translation([-h.bounds[:, 0].mean(), -h.bounds[:, 1].mean(), -h.bounds[0][2]])
    h.apply_transform(trimesh.transformations.rotation_matrix(np.radians(NEST_HEAD_DEG), [0, 0, 1]))
    h.apply_translation([*p3["shell-dome"].bounds[:, :2].mean(axis=0), 0.0])
    p3["head-mount"] = h
    nested = check(p3, {"shell-dome": DOME_BRIM}, min_gap=NEST_MIN_GAP)
    report = {"bed_mm": BED, "plate1-shell-dome": check(p1, {"shell-dome": DOME_BRIM}),
              "plate2-body-head-mount": check(p2, {"head-mount": BRIM}),
              "plate-dome-with-head": nested}
    for name, plate in (("plate1-shell-dome", p1), ("plate2-body-head-mount", p2), ("plate-dome-with-head", p3)):
        write_3mf(out / f"{name}.3mf", plate)
    (out / "plates.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v["ok"] if isinstance(v, dict) else v for k, v in report.items()}))
    return 0 if all(v["ok"] for k, v in report.items() if isinstance(v, dict)) else 1


def main():
    if "--variant" in sys.argv and sys.argv[sys.argv.index("--variant") + 1] == "v3-headarms":
        return main_headarms()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "plate1-new-parts.3mf").unlink(missing_ok=True)  # the old nested layout
    c = BED / 2
    lid, key = trimesh.load(V / "head-lid.stl").extents, trimesh.load(V / "lid-key.stl").extents
    p1a = {"shell-dome": place(V / "shell-dome.stl", c, c)}
    p1b = {"crown-print": place(V / "crown-print.stl", c, c),
           "head-lid": place(V / "head-lid.stl", BED - MARGIN - lid[0] / 2, BED - MARGIN - lid[1] / 2),
           "lid-key": place(V / "lid-key.stl", BED - MARGIN - key[0] / 2, MARGIN + key[1] / 2)}
    p2, y = {}, MARGIN
    for name, f in (("internal-frame", "internal-frame-print.stl"), ("bottom-cover", "bottom-cover.stl"),
                    ("head-cover", "head-cover-print.stl")):
        e = trimesh.load(K / f).extents
        p2[name] = place(K / f, MARGIN + 5 + e[0] / 2, y + e[1] / 2)
        y += e[1] + 8
    for i in range(4):
        p2[f"pcb-spacer-{i + 1}"] = place(K / "pcb-spacer.stl", 130 + i * 12, 20)
    report = {"bed_mm": BED, "plate1a-shell-dome": check(p1a, {"shell-dome": DOME_BRIM}),
              "plate1b-crown-lid-key": check(p1b, {"crown-print": BRIM}),
              "plate2-kit-parts": check(p2, {})}
    for name, plate in (("plate1a-shell-dome", p1a), ("plate1b-crown-lid-key", p1b), ("plate2-kit-parts", p2)):
        write_3mf(OUT / f"{name}.3mf", plate)
    (OUT / "plates.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v["ok"] if isinstance(v, dict) else v for k, v in report.items()}))
    return 0 if all(v["ok"] for k, v in report.items() if isinstance(v, dict)) else 1


if __name__ == "__main__":
    sys.exit(main())
