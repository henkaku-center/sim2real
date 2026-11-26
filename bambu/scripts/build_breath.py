"""Breathing test dome (Ø100) for the V3 head: FreeCAD Part builder.

Run with FreeCAD's bundled Python:
    /Applications/FreeCAD.app/Contents/Resources/bin/python -I build_breath.py PARAMS.json REPO_ROOT OUT_DIR

Parts (assembly coordinates in OUT_DIR/assembly, print orientation in OUT_DIR):
  breath-dome       Ø100 hemisphere: 3 mm rib layer, 1 mm skin cells (no through holes),
                    lung window at the apex, mouth window at the front, 3 screw tabs
  breath-base       pedestal on the head lid + floor + lung capsule cup on a post + mouth cup
  head-lid-breath   the delivered V3 lid with four Ø2.2 holes for the pedestal screws
  lung-ring, mouth-ring           clamp rings for the membrane and the lips
  lung-membrane-mold, mouth-lips-mold   open trays for casting silicone (or use balloon rubber)
"""
import json
import math
import os
import sys

sys.path.append(os.environ.get("FREECAD_LIB", "/Applications/FreeCAD.app/Contents/Resources/lib"))
import FreeCAD  # noqa: E402
import Import  # noqa: E402
import MeshPart  # noqa: E402
import Part  # noqa: E402

V = FreeCAD.Vector
BIG = 400.0


def cyl(r, h, base, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*base), V(*d))


def mouth_placement(m, c):
    """Local frame: +Z along the mouth axis, origin at the sphere centre."""
    rot = FreeCAD.Rotation(V(0, 0, 1), m["azimuth_deg"]).multiply(FreeCAD.Rotation(V(0, 1, 0), m["theta_deg"]))
    return FreeCAD.Placement(c, rot)


def mouth_stack(p):
    """Axial positions s (distance from the sphere centre) of the mouth capsule layers."""
    d, m = p["dome"], p["mouth"]
    r_in, ro = d["outer_r"] - d["rib_t"], m["ring_outer_d"] / 2
    ring_top = math.sqrt(r_in ** 2 - ro ** 2) - m["head_clear"]  # at the ring's outer edge
    ring_bot = ring_top - m["ring_t"]
    flange_top = ring_bot - m["lip_t"]
    flange_bot = flange_top - m["flange_t"]
    cav_bot = flange_top - m["cavity_depth"]
    back = cav_bot - m["back_wall"]
    return {"ring_top": ring_top, "ring_bot": ring_bot, "flange_top": flange_top, "flange_bot": flange_bot,
            "cav_bot": cav_bot, "back": back}


def lung_stack(p, floor_top):
    d, l = p["dome"], p["lung"]
    r_in = d["outer_r"] - d["rib_t"]
    ro = l["ring_outer_d"] / 2
    ring_top = floor_top + math.sqrt(r_in ** 2 - ro ** 2) - l["head_clear"]
    ring_bot = ring_top - l["ring_t"]
    flange_top = ring_bot - l["membrane_t"]
    flange_bot = flange_top - l["flange_t"]
    cav_bot = flange_top - l["cavity_depth"]
    cone_bot = flange_bot - (ro - l["post_d"] / 2)  # 45-degree cone from the post to the flange
    return {"ring_top": ring_top, "ring_bot": ring_bot, "flange_top": flange_top, "flange_bot": flange_bot,
            "cav_bot": cav_bot, "cone_bot": cone_bot}


def cells(p, c):
    """Ring layout of rhombic skin cells; returns (dir, up) unit vectors in world coordinates."""
    d = p["dome"]
    cp = d["cells"]
    R, a, web = d["outer_r"], cp["half"], cp["web"]
    m = p["mouth"]
    mdir = mouth_placement(m, V(0, 0, 0)).Rotation.multVec(V(0, 0, 1))
    mouth_ang = math.atan(max(m["window"]) / 2 / R) + (a + web + cp["window_margin"]) / R
    theta_rim = math.acos(cp["rim_band"] / R)
    theta = max(math.radians(cp["theta_min_deg"]), math.asin(p["lung"]["window_d"] / 2 / R) + (a + cp["window_margin"]) / R)
    out, k = [], 0
    while theta + a / R < theta_rim:
        n = int(2 * math.pi * R * math.sin(theta) // (2 * a + web * math.sqrt(2)))
        for j in range(n):
            phi = 2 * math.pi * (j + 0.5 * (k % 2)) / n
            dvec = V(math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta))
            if math.acos(max(-1.0, min(1.0, dvec.dot(mdir)))) < mouth_ang:
                continue
            up = V(0, 0, 1) - dvec * dvec.z
            up.normalize()
            out.append((dvec, up))
        theta += (2 * a + web) / R  # rows not nested: ring counts differ, so keep a full web between rows
        k += 1
    return out


def dome(p, floor_top):
    d = p["dome"]
    c = V(d["center_xy"][0], d["center_xy"][1], floor_top)
    R, rib, skin = d["outer_r"], d["rib_t"], d["skin_t"]
    body = Part.makeSphere(R, c).cut(Part.makeSphere(R - rib, c))
    body = body.common(Part.makeBox(BIG, BIG, BIG, V(c.x - BIG / 2, c.y - BIG / 2, floor_top)))
    # screw tabs inside the rim
    t = d["tabs"]
    for az in t["azimuth_deg"]:
        rot = FreeCAD.Rotation(V(0, 0, 1), az)
        tab = Part.makeBox(t["depth"] + 1.5, t["width"], t["height"], V(R - rib - t["depth"], -t["width"] / 2, 0))
        tab = tab.common(Part.makeSphere(R - 0.5, V(0, 0, 0)))
        tab.Placement = FreeCAD.Placement(c, rot)
        body = body.fuse(tab)
    tools = []
    # 1 mm skin cells: pockets cut from the inside, the outer surface stays closed
    cp = d["cells"]
    a = cp["half"]
    for dvec, up in cells(p, c):
        east = up.cross(dvec)
        q = c + dvec * (R - skin)
        pts = [q + up * a, q + east * a, q - up * a, q - east * a]
        face = Part.Face(Part.makePolygon(pts + [pts[0]]))
        tools.append(face.extrude(dvec * -(rib - skin + 1.5)))
    # lung window at the apex
    tools.append(cyl(p["lung"]["window_d"] / 2, R + 5, (c.x, c.y, floor_top + R - 25)))
    # mouth window: an ellipse cut along the mouth axis
    m = p["mouth"]
    pl = mouth_placement(m, c)
    ell = Part.Ellipse(V(0, 0, 0), max(m["window"]) / 2, min(m["window"]) / 2)
    face = Part.Face(Part.Wire(ell.toShape()))
    face.rotate(V(0, 0, 0), V(0, 0, 1), 90 if m["window"][1] > m["window"][0] else 0)
    face.translate(V(0, 0, R + 3))
    win = face.extrude(V(0, 0, -(rib + 8)))
    win.Placement = pl.multiply(win.Placement)
    tools.append(win)
    # tube notch in the rim
    rn = d["rim_notch"]
    az = math.radians(rn["azimuth_deg"])
    tools.append(cyl(rn["d"] / 2, 20, (c.x + (R - 10) * math.cos(az), c.y + (R - 10) * math.sin(az), floor_top),
                     (math.cos(az), math.sin(az), 0)))
    body = body.cut(Part.makeCompound(tools))
    for az in t["azimuth_deg"]:
        r = R - rib - t["depth"] / 2
        x, y = c.x + r * math.cos(math.radians(az)), c.y + r * math.sin(math.radians(az))
        body = body.cut(cyl(t["pilot_d"] / 2, t["pilot_depth"], (x, y, floor_top - 0.1)))
    return body.removeSplitter()


def lung_capsule(p, floor_top, c):
    l = p["lung"]
    s = lung_stack(p, floor_top)
    ro = l["ring_outer_d"] / 2
    rp = l["post_d"] / 2
    post = cyl(rp, s["cone_bot"] - floor_top + 0.5, (c.x, c.y, floor_top - 0.5))
    cone = Part.makeCone(rp, ro, s["flange_bot"] - s["cone_bot"], V(c.x, c.y, s["cone_bot"]))
    flange = cyl(ro, l["flange_t"], (c.x, c.y, s["flange_bot"]))
    ez = floor_top + l["channel_exit_above_floor"]
    barb = cyl(l["barb_od"] / 2, l["barb_len"] + 0.5, (c.x - rp + 0.5, c.y, ez), (-1, 0, 0))
    body = post.fuse([cone, flange, barb])
    cuts = [cyl(l["free_d"] / 2, l["cavity_depth"] + 1, (c.x, c.y, s["cav_bot"])),
            cyl(l["channel_d"] / 2, s["cav_bot"] - ez + 0.5, (c.x, c.y, ez)),
            cyl(l["channel_d"] / 2, rp + l["barb_len"] + 1, (c.x, c.y, ez), (-1, 0, 0))]
    br = l["bolt_circle_d"] / 2
    for i in range(l["bolts"]):
        ang = 2 * math.pi * (i + 0.5) / l["bolts"]
        cuts.append(cyl(l["pilot_d"] / 2, l["pilot_depth"] + 0.1,
                        (c.x + br * math.cos(ang), c.y + br * math.sin(ang), s["flange_top"] - l["pilot_depth"])))
    return body, cuts


def mouth_capsule(p, floor_top, c):
    m = p["mouth"]
    s = mouth_stack(p)
    pl = mouth_placement(m, c)
    ro = m["ring_outer_d"] / 2
    body = cyl(ro, s["flange_top"] - s["back"], (0, 0, s["back"]))
    body = body.fuse(cyl(m["barb_od"] / 2, m["barb_len"] + 0.5, (0, 0, s["back"] + 0.5), (0, 0, -1)))
    cuts = [cyl(m["free_d"] / 2, m["cavity_depth"] + 1, (0, 0, s["cav_bot"])),
            cyl(m["channel_d"] / 2, s["cav_bot"] - s["back"] + m["barb_len"] + 1, (0, 0, s["back"] - m["barb_len"] - 0.5))]
    br = m["bolt_circle_d"] / 2
    for i in range(m["bolts"]):
        ang = 2 * math.pi * (i + 0.5) / m["bolts"]
        cuts.append(cyl(m["pilot_d"] / 2, m["pilot_depth"] + 0.1,
                        (br * math.cos(ang), br * math.sin(ang), s["flange_top"] - m["pilot_depth"])))
    body.Placement = pl.multiply(body.Placement)
    for t in cuts:
        t.Placement = pl.multiply(t.Placement)
    # vertical fin from the floor up to the capsule axis
    bb = body.BoundBox
    axis_z = (pl.multVec(V(0, 0, s["back"])).z + pl.multVec(V(0, 0, s["flange_top"])).z) / 2
    fin = Part.makeBox(bb.XMax - bb.XMin - 2, m["fin_t"], axis_z - floor_top + 0.5,
                       V(bb.XMin + 1, c.y - m["fin_t"] / 2, floor_top - 0.5))
    return body.fuse(fin), cuts


def base(p, floor_top):
    b, h = p["base"], p["head"]
    d = p["dome"]
    c = V(d["center_xy"][0], d["center_xy"][1], floor_top)
    pd = b["pedestal"]
    x0, x1 = pd["x"]
    y0, y1 = pd["y"]
    z0, z1 = h["lid_top_z"], b["floor_bottom_z"]
    w = pd["wall"]
    ped = Part.makeBox(x1 - x0, y1 - y0, z1 - z0 + 0.5, V(x0, y0, z0))
    ped = ped.cut(Part.makeBox(x1 - x0 - 2 * w, y1 - y0 - 2 * w, z1 - z0 + 2, V(x0 + w, y0 + w, z0 - 1)))
    for x, y in pd["screws_xy"]:
        ped = ped.fuse(cyl(pd["boss_d"] / 2, z1 - z0 + 0.5, (x, y, z0)))
    floor = cyl(d["outer_r"], b["floor_t"], (c.x, c.y, b["floor_bottom_z"]))
    lung, lcuts = lung_capsule(p, floor_top, c)
    mouth, mcuts = mouth_capsule(p, floor_top, c)
    body = ped.fuse([floor, lung, mouth])
    cuts = lcuts + mcuts
    for x, y in pd["screws_xy"]:
        cuts.append(cyl(pd["pilot_d"] / 2, pd["pilot_depth"], (x, y, z0 - 0.1)))
    t = d["tabs"]
    for az in t["azimuth_deg"]:
        r = d["outer_r"] - d["rib_t"] - t["depth"] / 2
        cuts.append(cyl(b["floor_screw_clear_d"] / 2, b["floor_t"] + 2,
                        (c.x + r * math.cos(math.radians(az)), c.y + r * math.sin(math.radians(az)), b["floor_bottom_z"] - 1)))
    return body.cut(Part.makeCompound(cuts)).removeSplitter()


def ring(r_in, r_out, t, bolts, bolt_r, hole_d):
    body = cyl(r_out, t, (0, 0, 0)).cut(cyl(r_in, t + 2, (0, 0, -1)))
    for i in range(bolts):
        ang = 2 * math.pi * (i + 0.5) / bolts
        body = body.cut(cyl(hole_d / 2, t + 2, (bolt_r * math.cos(ang), bolt_r * math.sin(ang), -1)))
    return body


def mold(r_pocket, depth, bolts, bolt_r, pin_d, plate_t, margin, bead=None):
    side = 2 * (r_pocket + margin)
    body = Part.makeBox(side, side, plate_t + depth, V(-side / 2, -side / 2, 0))
    body = body.cut(cyl(r_pocket, depth + 1, (0, 0, plate_t)))
    if bead:  # lip bead: an extra-deep stadium groove along Y in the pocket floor
        L, W, H = bead
        slot = Part.makeBox(W, L - W, H + 0.01, V(-W / 2, -(L - W) / 2, plate_t - H))
        slot = slot.fuse([cyl(W / 2, H + 0.01, (0, (L - W) / 2, plate_t - H)), cyl(W / 2, H + 0.01, (0, -(L - W) / 2, plate_t - H))])
        body = body.cut(slot)
    for i in range(bolts):
        ang = 2 * math.pi * (i + 0.5) / bolts
        body = body.fuse(cyl(pin_d / 2 - 0.05, depth, (bolt_r * math.cos(ang), bolt_r * math.sin(ang), plate_t - 0.01)))
    return body.removeSplitter()


def lid_with_holes(p, root):
    h, pd = p["head"], p["base"]["pedestal"]
    shape = Part.Shape()
    shape.read(os.path.join(root, h["dir"], h["lid_step"]))
    for x, y in pd["screws_xy"]:
        shape = shape.cut(cyl(pd["lid_hole_d"] / 2, 20, (x, y, h["lid_bottom_z"] - 5)))
    return shape.removeSplitter()


def export(shape, stem, placement=None):
    s = shape.copy()
    if placement is not None:
        s.Placement = placement.multiply(s.Placement)
    bb = s.BoundBox
    if placement is not None:
        s.translate(V(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, -bb.ZMin))
    s.exportStep(stem + ".step")
    MeshPart.meshFromShape(Shape=s, LinearDeflection=0.04, AngularDeflection=0.2).write(stem + ".stl")


def single(name, shape):
    sol = shape.Solids
    if not shape.isValid() or len(sol) != 1:
        raise SystemExit(f"{name}: invalid or {len(sol)} solids")
    return sol[0]


def main(params_path, root, out):
    p = json.load(open(params_path))
    os.makedirs(os.path.join(out, "assembly"), exist_ok=True)
    floor_top = p["base"]["floor_bottom_z"] + p["base"]["floor_t"]
    d = p["dome"]
    c = V(d["center_xy"][0], d["center_xy"][1], floor_top)
    l, m, mo = p["lung"], p["mouth"], p["molds"]
    ls, ms = lung_stack(p, floor_top), mouth_stack(p)
    lung_ring = ring(l["free_d"] / 2, l["ring_outer_d"] / 2, l["ring_t"], l["bolts"], l["bolt_circle_d"] / 2, 2.2)
    mouth_ring = ring(m["free_d"] / 2, m["ring_outer_d"] / 2, m["ring_t"], m["bolts"], m["bolt_circle_d"] / 2, 2.2)
    lung_ring_asm = lung_ring.copy()
    lung_ring_asm.translate(V(c.x, c.y, ls["ring_bot"]))
    mouth_ring_asm = mouth_ring.copy()
    mouth_ring_asm.translate(V(0, 0, ms["ring_bot"]))
    mouth_ring_asm.Placement = mouth_placement(m, c).multiply(mouth_ring_asm.Placement)
    flip = FreeCAD.Placement(V(0, 0, 0), FreeCAD.Rotation(V(1, 0, 0), 180))
    upright = FreeCAD.Placement()
    parts = {
        "breath-dome": (dome(p, floor_top), None, upright),
        "breath-base": (base(p, floor_top), None, upright),
        "head-lid-breath": (lid_with_holes(p, root), None, flip),
        "lung-ring": (lung_ring, lung_ring_asm, upright),
        "mouth-ring": (mouth_ring, mouth_ring_asm, upright),
        "lung-membrane-mold": (mold(l["ring_outer_d"] / 2, l["membrane_t"], l["bolts"], l["bolt_circle_d"] / 2,
                                    mo["pin_d"], mo["plate_t"], mo["margin"]), None, upright),
        "mouth-lips-mold": (mold(m["ring_outer_d"] / 2, m["lip_t"], m["bolts"], m["bolt_circle_d"] / 2,
                                 mo["pin_d"], mo["plate_t"], mo["margin"], bead=m["bead"]), None, upright),
    }
    report = {"floor_top_z": floor_top, "lung_stack": ls, "mouth_stack": ms}
    for name, (shape, asm, orient) in parts.items():
        shape = single(name, shape)
        asm = single(name, asm) if asm is not None else shape
        if name not in ("lung-membrane-mold", "mouth-lips-mold"):
            export(asm, os.path.join(out, "assembly", name))
        export(shape, os.path.join(out, name), orient)
        bb = asm.BoundBox
        report[name] = {"volume_mm3": shape.Volume, "centroid_mm": list(asm.CenterOfMass),
                        "bbox_mm": [[bb.XMin, bb.YMin, bb.ZMin], [bb.XMax, bb.YMax, bb.ZMax]]}
    json.dump(report, open(os.path.join(out, "cad.json"), "w"), indent=1)
    print(json.dumps({k: round(v["volume_mm3"]) for k, v in report.items() if isinstance(v, dict) and "volume_mm3" in v}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
