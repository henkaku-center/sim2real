"""Build the self-righting turtle shell (dome) and its top-cover mount with FreeCAD Part.

Run with FreeCAD's bundled Python; all numbers come from a job JSON written by
design.py (robot frame, mm):
    /Applications/FreeCAD.app/Contents/Resources/bin/python -I build_shell.py JOB.json
Writes print-oriented <out_dir>/<part>.{step,stl}, assembly-coordinate copies in
<out_dir>/assembly/, and <out_dir>/cad.json (volumes, centroids).  Parts:
  shell-onepiece  dome + mast + saddle, one print (variant "one-piece")
  drill-guide     saddle-shaped jig for the top-cover screw holes of the one-piece variant
  shell-dome, shell-mount   the two-piece variant (mast in a socket, filament cross-pin)
  shell-dome, s3-top-cover  variant "s3-cover": the dome on a lid + mast for the widened S3 frame
  shell-dome-print          variant "v3-headarms" with dome.print_ties: the dome plus slot membranes (slice this)
"""
import json
import math
import os
import sys

sys.path.append(os.environ.get("FREECAD_LIB", "/Applications/FreeCAD.app/Contents/Resources/lib"))
import FreeCAD  # noqa: E402
import MeshPart  # noqa: E402
import Part  # noqa: E402

V = FreeCAD.Vector


def vec(p):
    return V(*[float(x) for x in p])


def ogive(c, r, cap_slope_deg, tip_r):
    """Sphere below the polar angle where its slope equals cap_slope, tangent cone above, round tip.
    Every downward-facing inner surface is then at least cap_slope from horizontal (printed rim-down)."""
    tc = math.radians(cap_slope_deg)
    alpha = math.pi / 2 - tc  # cone half-angle from the axis
    apex = c.z + r / math.cos(tc)
    z0, r0 = c.z + r * math.cos(tc), r * math.sin(tc)
    tip_c = apex - tip_r / math.sin(alpha)
    z_k = tip_c + tip_r * math.sin(alpha)  # tangent circle of the tip sphere
    cone = Part.makeCone(r0, (apex - z_k) * math.tan(alpha), z_k - z0, V(c.x, c.y, z0))
    return Part.makeSphere(r, c).fuse([cone, Part.makeSphere(tip_r, V(c.x, c.y, tip_c))]).removeSplitter(), tip_c


def slot_tools(d):
    """Knee-sweep cutters (cylinders, with a pointed roof when slot_roof_slope_deg is set)."""
    tools = []
    for s in d["slots"]:
        axis = vec(s["axis"])
        base = vec(s["knee"]) + axis * s["axial_lo"]
        length = s["axial_hi"] - s["axial_lo"]
        tool = Part.makeCylinder(s["radius"], length, base, axis)
        if d.get("slot_roof_slope_deg"):  # pointed roof: the slot top prints without bridging
            up = V(0, 0, 1) - axis * axis.z
            up.normalize()
            side = axis.cross(up)
            phi = math.radians(d["slot_roof_slope_deg"])
            rs = s["radius"]
            tr = [up * (rs * math.cos(phi)) + side * (rs * math.sin(phi)), up * (rs / math.cos(phi)),
                  up * (rs * math.cos(phi)) - side * (rs * math.sin(phi)), V(0, 0, 0)]
            tr = [base + q for q in tr]
            tool = tool.fuse(Part.Face(Part.makePolygon(tr + [tr[0]])).extrude(axis * length))
        tools.append(tool)
    return tools


def slot_ties(job):
    """Print aid for the dome: a thin membrane filling each knee slot, mid-wall, from the bed up to the
    slot roof.  Without it the rim is four free-standing, inward-leaning petals that sway under the nozzle
    (failed print, 2026-11-17).  Cut the membranes out along the slot edges after printing."""
    d = job["dome"]
    c, r, t, tie = vec(d["center"]), d["radius"], d["thickness"], d["print_ties"]["t"]
    big = 4 * r
    r_hi, r_lo = r - (t - tie) / 2, r - (t + tie) / 2
    if d.get("cap_slope_deg"):
        skin = ogive(c, r_hi, d["cap_slope_deg"], d["tip_radius"] - (t - tie) / 2)[0].cut(
            ogive(c, r_lo, d["cap_slope_deg"], d["tip_radius"] - (t + tie) / 2)[0])
    else:
        skin = Part.makeSphere(r_hi, c).cut(Part.makeSphere(r_lo, c))
    skin = skin.common(Part.makeBox(big, big, big, V(c.x - big / 2, c.y - big / 2, d["rim_z"])))
    return skin.common(Part.makeCompound(slot_tools(d)))


def dome(job, socket=True):
    d = job["dome"]
    c, r, t = vec(d["center"]), d["radius"], d["thickness"]
    big = 4 * r
    if d.get("cap_slope_deg"):
        outer, tip_c = ogive(c, r, d["cap_slope_deg"], d["tip_radius"])
        inner, _ = ogive(c, r - t, d["cap_slope_deg"], d["tip_radius"] - t)
        body = outer.cut(inner)
    else:
        body = Part.makeSphere(r, c).cut(Part.makeSphere(r - t, c))
    body = body.common(Part.makeBox(big, big, big, V(c.x - big / 2, c.y - big / 2, d["rim_z"])))
    rb = d.get("rim_band")
    if rb:  # wall thickened inward from the rim up to z_top (stiffer petals, holds the lugs); 45-degree step back
        ri = r - rb["t"]
        rho0 = math.sqrt(ri ** 2 - (rb["z_top"] - c.z) ** 2)
        h = rb["t"] + 1.0
        band = Part.makeSphere(r - t + 0.05, c).cut(Part.makeSphere(ri, c))
        band = band.common(Part.makeBox(big, big, rb["z_top"] + h - d["rim_z"], V(c.x - big / 2, c.y - big / 2, d["rim_z"])))
        band = band.cut(Part.makeCone(rho0, rho0 + h, h, V(c.x, c.y, rb["z_top"])))
        body = body.fuse(band)
    t_cut = max(t, rb["t"]) if rb else t  # hole cutters must cross the thick band too
    reach = r * 0.25 + 5.0 if d.get("cap_slope_deg") else 1.0  # radial prisms must also cross the cone cap

    # perforation: rhombic (45-degree) prisms, extruded along the local normal
    tools = []
    for h in d["holes"]:
        n, up = vec(h["dir"]), vec(h["up"])
        east = up.cross(n)
        p = c + n * (r + reach)
        a, b = h["half_meridian"], h["half_azimuth"]
        pts = [p + up * a, p + east * b, p - up * a, p - east * b]
        face = Part.Face(Part.makePolygon(pts + [pts[0]]))
        tools.append(face.extrude(n * -(reach + t_cut + 1.5)))
    for w in d.get("windows", []):  # snap windows: flat sill (lock face), vertical sides, 45-degree gable
        phi = math.radians(w["phi_deg"])
        er, et = V(math.cos(phi), math.sin(phi), 0), V(-math.sin(phi), math.cos(phi), 0)
        b = w["half_w"]
        base = V(c.x, c.y, 0) + er * w["h_in"]
        poly = [base + et * -b + V(0, 0, w["z_lo"]), base + et * b + V(0, 0, w["z_lo"]), base + et * b + V(0, 0, w["z_hi"]),
                base + V(0, 0, w["z_hi"] + b), base + et * -b + V(0, 0, w["z_hi"])]
        tools.append(Part.Face(Part.makePolygon(poly + [poly[0]])).extrude(er * (w["h_out"] - w["h_in"])))
    if tools and d.get("hole_skin"):  # blind pockets leaving a thin skin of the wall
        tools = Part.makeCompound(tools)
        if d.get("hole_skin_side", "outer") == "outer":
            body = body.cut(tools.cut(Part.makeSphere(r - t + d["hole_skin"], c)))
        else:
            body = body.cut(tools.common(Part.makeSphere(r - d["hole_skin"], c)))
    elif tools:
        body = body.cut(Part.makeCompound(tools))

    # knee-sweep slots for the tuck motion
    for tool in slot_tools(d):
        body = body.cut(tool)

    for lug in d.get("lugs", []):  # rim lugs for the bracket screws; bottom flush with the rim (prints on the bed)
        (x0, x1), (y0, y1), (z0, z1) = lug["x"], lug["y"], lug["z"]
        block = Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0)).common(Part.makeSphere(r - t + 0.2, c))
        body = body.fuse(block)
        for x, y in lug["pilots"]:
            body = body.cut(Part.makeCylinder(lug["pilot_r"], lug["pilot_depth"] + 1, V(x, y, z0 - 1)))
    if d.get("apex"):  # mushroom stem: hole + knob pocket at the tip, keyway for the fin
        ap = d["apex"]
        ax, ay = ap["axis_xy"]
        fx, top = ap["flat_x"], c.z + 2 * r
        strip = Part.makeBox(2 * fx, 4 * ap["knob_r"], top, V(ax - fx, ay - 2 * ap["knob_r"], 0))
        body = body.cut(Part.makeCylinder(ap["hole_r"], top, V(ax, ay, 0)).common(strip))
        body = body.cut(Part.makeCylinder(ap["knob_r"], top - ap["cut_z"], V(ax, ay, ap["cut_z"])).common(strip))
        r0, r1 = ap["fin_r"]
        key = Part.makeBox(r1 - r0, 2 * ap["fin_half_w"], top, V(r0, -ap["fin_half_w"], 0))
        key.rotate(V(0, 0, 0), V(0, 0, 1), ap["fin_phi_deg"])
        key.translate(V(ax, ay, 0))
        body = body.cut(key.common(Part.makeBox(4 * r, 4 * r, top, V(ax - 2 * r, ay - 2 * r, c.z))))
    if not socket or d.get("lugs") or d.get("cap_slope_deg"):
        return body.removeSplitter()
    # socket for the mast, hanging from the apex
    so = d["socket"]
    top = c.z + r - t / 2
    sock = Part.makeCylinder(so["outer_r"], top - so["bottom_z"], V(c.x, c.y, so["bottom_z"]))
    sock = sock.common(Part.makeSphere(r - t / 2, c))
    body = body.fuse(sock)
    bore_top = c.z + r - t - so["roof"]
    body = body.cut(Part.makeCylinder(so["inner_r"], bore_top - so["bottom_z"] + 1, V(c.x, c.y, so["bottom_z"] - 1)))
    pin = vec(so["pin_dir"])
    body = body.cut(Part.makeCylinder(so["pin_r"], 4 * so["outer_r"], V(c.x, c.y, so["pin_z"]) - pin * 2 * so["outer_r"], pin))
    return body.removeSplitter()


def saddle(job):
    m = job["mount"]
    x0, x1 = m["x_range"]

    def prism(profile):
        pts = [V(x0, y, z) for y, z in profile]
        face = Part.Face(Part.makePolygon(pts + [pts[0]]))
        return face.extrude(V(x1 - x0, 0, 0))

    return prism(m["outer_profile"]).cut(prism(m["inner_profile"]))


def mount(job, one_piece=False):
    m, d = job["mount"], job["dome"]
    body = saddle(job)
    if not one_piece:
        for x, z in m["screws"]:
            body = body.cut(Part.makeCylinder(m["screw_r"], 60, V(x, -30, z), V(0, 1, 0)))
    cx, cy = m["mast_xy"]
    z0 = m["plate_top_z"]
    c, r, t = vec(d["center"]), d["radius"], d["thickness"]
    z1 = c.z + r - t / 2 if one_piece else m["mast_top_z"]  # one-piece: the mast runs into the ceiling
    mast = Part.makeCylinder(m["mast_outer_r"], z1 - z0 + 0.5, V(cx, cy, z0 - 0.5))
    gusset = Part.makeCone(m["gusset_r"], m["mast_outer_r"], m["gusset_h"], V(cx, cy, z0 - 0.5))
    parts = [mast, gusset]
    if one_piece:  # flare into the ceiling; widening upward at < 45 deg so it prints unsupported
        h = m["ceiling_fillet_h"]
        zc = c.z + r - t - h
        parts.append(Part.makeCone(m["mast_outer_r"], m["ceiling_fillet_r"], h + t / 2, V(cx, cy, zc)))
    body = body.fuse(parts)
    if one_piece:
        body = body.common(Part.makeSphere(r - t / 2, c).fuse(Part.makeBox(400, 400, c.z, V(c.x - 200, c.y - 200, 0))))
        bore_top = c.z + r - t - 2.0
    else:
        bore_top = z1
    body = body.cut(Part.makeCylinder(m["mast_inner_r"], bore_top - z0 - m["mast_floor"], V(cx, cy, z0 + m["mast_floor"])))
    if one_piece:
        for x, y in m["vertical_screws"]:
            body = body.cut(Part.makeCylinder(m["pilot_r"], m["pilot_depth"] + 1, V(x, y, m["cavity_top_z"] - 1)))
    else:
        pin = vec(m["pin_dir"])
        body = body.cut(Part.makeCylinder(m["pin_r"], 4 * m["mast_outer_r"], V(cx, cy, m["pin_z"]) - pin * 2 * m["mast_outer_r"], pin))
    return body.removeSplitter()


def s3_cover(job):
    """Lid for the widened S3 frame (see design.s3_cover_job): a roofed box above the femur band,
    end walls and screw bosses below it kept inside |y| <= y_limit, open sides for cables, and the mast."""
    cv, m = job["cover"], job["mount"]
    hx, hy = cv["outer_half"]
    w, pcb, zr, zt = cv["wall"], cv["pcb_top_z"], cv["roof_bottom_z"], cv["roof_top_z"]
    b0, b1 = cv["leg_band_z"]
    yl = cv["y_limit"]
    box = Part.makeBox(2 * hx, 2 * hy, zt - b1, V(-hx, -hy, b1))
    box = box.cut(Part.makeBox(2 * (hx - w), 2 * (hy - w), zr - b1 + 1, V(-hx + w, -hy + w, b1 - 1)))
    ends = [Part.makeBox(w, 2 * yl, b1 - pcb + 0.5, V(sx, -yl, pcb)) for sx in (-hx, hx - w)]
    bosses = [Part.makeCylinder(cv["boss_r"], zt - pcb, V(x, y, pcb)) for x, y in cv["bosses"]]
    body = box.fuse(ends + bosses)
    big = 4 * hx
    band = [Part.makeBox(big, big, b1 - b0, V(-big / 2, sy, b0)) for sy in (yl, -yl - big)]
    ey, ez = cv["end_window"]
    body = body.cut(band + [Part.makeBox(2 * hx + 2, 2 * ey, ez - pcb + 1, V(-hx - 1, -ey, pcb - 1))])

    cx, cy = m["mast_xy"]
    z1 = m["mast_top_z"]
    body = body.fuse([Part.makeCylinder(m["mast_outer_r"], z1 - zt + 0.5, V(cx, cy, zt - 0.5)),
                      Part.makeCone(m["gusset_r"], m["mast_outer_r"], m["gusset_h"], V(cx, cy, zt - 0.5))])
    body = body.cut(Part.makeCylinder(m["mast_inner_r"], z1 - zt + 1, V(cx, cy, zt)))
    pin = vec(m["pin_dir"])
    body = body.cut(Part.makeCylinder(m["pin_r"], 4 * m["mast_outer_r"], V(cx, cy, m["pin_z"]) - pin * 2 * m["mast_outer_r"], pin))
    for x, y in cv["bosses"]:  # driver bore from the roof, M1.6 clearance through the floor
        body = body.cut(Part.makeCylinder(cv["bore_r"], zt - pcb - cv["boss_floor"] + 1, V(x, y, pcb + cv["boss_floor"])))
        body = body.cut(Part.makeCylinder(cv["screw_r"], cv["boss_floor"] + 2, V(x, y, pcb - 1)))
    return body.removeSplitter()


def bracket(b):
    """Side bracket: wide foot over the two ear screws, narrow stem, tab with counterbored screw holes."""
    def prism(x0, x1):
        pts = [V(x0, y, z) for y, z in b["profile_yz"]]
        solid = Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(x1 - x0, 0, 0))
        return solid

    (fx0, fx1), (fy0, fy1), (fz0, fz1) = b["foot"]["x"], b["foot"]["y"], b["foot"]["z"]
    body = prism(*b["stem_x"]).fuse(Part.makeBox(fx1 - fx0, fy1 - fy0, fz1 - fz0, V(fx0, fy0, fz0)))
    ya = b["tab_from_abs_y"]
    keep = Part.makeBox(400, 200, 400, V(-200, ya if b["side"] > 0 else -ya - 200, -200))
    body = body.fuse(prism(*b["tab_x"]).common(keep))
    holes = [Part.makeCylinder(b["ear_hole_r"], b["ear_z"][1] - b["ear_z"][0] + 2, V(x, y, b["ear_z"][0] - 1)) for x, y in b["ear_holes"]]
    for x, y in b["tab_holes"]:
        holes.append(Part.makeCylinder(b["tab_hole_r"], b["tab_z"][1] - b["tab_z"][0] + 2, V(x, y, b["tab_z"][0] - 1)))
        holes.append(Part.makeCylinder(b["counterbore_r"], b["counterbore_top_z"] - b["tab_z"][0] + 1, V(x, y, b["tab_z"][0] - 1)))
    return body.cut(holes).removeSplitter()


def _kit_lid(cr):
    lid = Part.read(cr["lid_step"])
    lid = lid.Solids[0] if lid.Solids else Part.makeSolid(lid)
    lid.translate(V(0, 0, cr["lid_dz"]))
    return lid


def _bayonet_layout(cr):
    b = cr["bayonet"]
    return [b["phase_deg"] + 360.0 * k / b["count"] for k in range(b["count"])]


def crown(job, locked=True):
    """45-degree crown with gothic windows and two snap fingers; below it a 45-degree seat, a tube
    through the lid and bayonet lugs that turn under the lid.  Printed upright on its lugs."""
    cr = job["crown"]
    b = cr["bayonet"]
    ax, ay = cr["axis_xy"]
    z0, r0, w = cr["lid_top_z"], cr["base_r"], cr["wall"]
    zb = b["lid_bottom_z"]
    sl = math.radians(cr["slope_deg"])
    wh = w / math.sin(sl)
    cd = b["seat_depth"]
    rs = r0 - cd  # tube radius below the countersink
    h = (cr["seat_z"] - z0) + 15.0
    z_c = z0 - cd  # cone continues 45 degrees down into the lid's countersink
    outer = Part.makeCone(rs, rs + (h + cd) / math.tan(sl), h + cd, V(ax, ay, z_c))
    # inner cones start 1 mm lower, so their base radius is 1/tan(slope) smaller (until 2026-11-13 it was
    # not, and every crown wall came out 1/tan(slope) mm thinner horizontally than `wall` asked for)
    inner = Part.makeCone(rs - wh - 1 / math.tan(sl), rs - wh + (h + cd + 1) / math.tan(sl), h + cd + 2, V(ax, ay, z_c - 1))
    if cr.get("wall_top"):  # thicker band under the seat, where the fingers root and the print brace bites
        wt = cr["wall_top"] / math.sin(sl)
        z_t = cr["seat_z"] - cr["wall_top_band"]
        top = Part.makeCone(rs - wt - 1 / math.tan(sl), rs - wt + (h + cd + 1) / math.tan(sl), h + cd + 2, V(ax, ay, z_c - 1))
        r_ti = rs - wh + (z_t - z_c) / math.tan(sl)  # thin wall's inner surface at z_t
        band = Part.makeCylinder(rs + 2 * h + 10, h + 40, V(ax, ay, z_t - 20)).cut(  # 45-degree step, no ledge
            Part.makeCone(r_ti + 20, 0, r_ti + 20, V(ax, ay, z_t - 20)))
        outer = outer.cut(inner).fuse(outer.cut(top).common(band))
    else:
        outer = outer.cut(inner)
    shell = outer.common(Part.makeSphere(cr["dome_inner_r"] - cr["seat_gap"], vec(cr["dome_center"])))
    z_lug = zb + b["lip"] + b["lug_gap"]  # lugs turn inside a groove within the lid's thickness
    tube = Part.makeCylinder(rs, z_c - z_lug + 0.3, V(ax, ay, z_lug)).cut(
        Part.makeCylinder(rs - b["tube_wall"], z_c - z_lug + 2, V(ax, ay, z_lug - 1)))
    body = shell.fuse(tube)

    win = cr["windows"]  # gothic windows: vertical sides, pointed top (faces >= 45 degrees); count 0 = closed cone
    slant = (cr["seat_z"] - z0) / math.sin(sl)
    s0 = win["bottom_margin"]
    s1 = s0 + 0.4 * (slant - win["top_margin"] - s0)
    for _ in range(30 if win["count"] else 0):
        r_s1 = r0 - wh / 2 + s1 * math.cos(sl)
        s1 = slant - win["top_margin"] - 1.45 * (r_s1 * 2 * math.pi / win["count"] - win["strut"]) / 2
    cuts = []
    for k in range(win["count"]):
        phi = math.radians(win["phase_deg"] + 360.0 * k / win["count"])
        er, et = V(math.cos(phi), math.sin(phi), 0), V(-math.sin(phi), math.cos(phi), 0)
        def pt(s, u):
            return V(ax, ay, z0) + er * (r0 - wh / 2 + s * math.cos(sl)) + V(0, 0, s * math.sin(sl)) + et * u
        def half(s):
            return ((r0 - wh / 2 + s * math.cos(sl)) * 2 * math.pi / win["count"] - win["strut"]) / 2
        hb, ht = half(s0), half(s1)
        poly = [pt(s0, -hb), pt(s0, hb), pt(s1, ht), pt(s1 + 1.45 * ht, 0), pt(s1, -ht)]
        face = Part.Face(Part.makePolygon(poly + [poly[0]]))
        face.translate(er * -6)
        cuts.append(face.extrude(er * 12))
    if cuts:
        body = body.cut(cuts)

    parts = []
    c = vec(cr["dome_center"])
    for f in cr["fingers"]:  # spring fingers following the dome's inner sphere (gap kept constant)
        phi = math.radians(f["phi_deg"])
        et = V(-math.sin(phi), math.cos(phi), 0)
        er = V(math.cos(phi), math.sin(phi), 0)
        tf, rho = f["thick"], f["rho"]
        ths = [f["theta_tip"] + (f["theta_root"] - f["theta_tip"]) * i / 24 for i in range(25)]
        prof = [c + (er * math.sin(th) + V(0, 0, math.cos(th))) * (rho + tf / 2) for th in ths]
        prof += [c + (er * math.sin(th) + V(0, 0, math.cos(th))) * (rho - tf / 2) for th in reversed(ths)]
        face = Part.Face(Part.makePolygon(prof + [prof[0]]))
        half = math.degrees(f["width"] / 2 / (rho * math.sin(f["theta_tip"])))
        face.rotate(c, V(0, 0, 1), -half)
        parts.append(face.revolve(c, V(0, 0, 1), 2 * half))
        bw = f["barb_width"]
        poly = [V(c.x, c.y, 0) + er * hh + V(0, 0, zz) for hh, zz in f["barb_hz"]]
        face = Part.Face(Part.makePolygon([q - et * (bw / 2) for q in poly] + [poly[0] - et * (bw / 2)]))
        parts.append(face.extrude(et * bw))
    lugs = []
    for a in _bayonet_layout(cr):  # lugs at the tube's foot; chamfered tops ease the twist
        ph = math.radians(a + (b["turn_deg"] if locked else 0.0))
        er, et = V(math.cos(ph), math.sin(ph), 0), V(-math.sin(ph), math.cos(ph), 0)
        lw = b["lug_w"] / 2
        q = [V(ax, ay, z_lug) + er * (rs - 1.0) - et * lw, V(ax, ay, z_lug) + er * b["lug_r"] - et * lw,
             V(ax, ay, z_lug) + er * b["lug_r"] + et * lw, V(ax, ay, z_lug) + er * (rs - 1.0) + et * lw]
        lugs.append(Part.Face(Part.makePolygon(q + [q[0]])).extrude(V(0, 0, b["lug_t"])))
    body = body.fuse(parts + lugs)
    if not locked:
        return body.removeSplitter()
    return body.removeSplitter()


def crown_brace(job):
    """Print aid for the crown: a thin cylinder from the bed (the lugs' underside) up to the solid band
    above the windows, its top following the cone's underside at `gap` (wider than a line, so the two
    walls do not fuse), joined to it by small tabs.  It keeps the wide crown ring from swaying or tipping
    on its narrow foot; snap the tabs and slide the cylinder off downwards (the cone narrows below it)."""
    cr, pb = job["crown"], job["crown"]["print_brace"]
    b = cr["bayonet"]
    ax, ay = cr["axis_xy"]
    z0, r0 = cr["lid_top_z"], cr["base_r"]
    sl = math.radians(cr["slope_deg"])
    rs = r0 - b["seat_depth"]
    z_c = z0 - b["seat_depth"]
    z_bed = b["lid_bottom_z"] + b["lip"] + b["lug_gap"]
    slant = (cr["seat_z"] - z0) / math.sin(sl)
    s_k = slant - cr["windows"]["top_margin"] / 2  # middle of the solid band above the windows
    r_k = r0 + s_k * math.cos(sl)  # the cone's outer surface there
    r_in, r_out = r_k - pb["wall"] / 2, r_k + pb["wall"] / 2
    if r_in - pb["gap"] <= b["lug_r"] + 1.0:
        raise SystemExit("crown brace: too close to the lugs")
    h = (r_out + 10 - rs) * math.tan(sl)

    def above_cone(dz):  # everything above the cone's outer surface shifted by dz
        return Part.makeCone(rs, rs + (h + 20) / math.tan(sl), h + 20, V(ax, ay, z_c + dz))

    top = z_c + (r_out - rs) * math.tan(sl) + 2.0
    ring = Part.makeCylinder(r_out, top - z_bed, V(ax, ay, z_bed)).cut(
        Part.makeCylinder(r_in, top - z_bed + 2, V(ax, ay, z_bed - 1)))
    brace = ring.cut(above_cone(-pb["gap"]))
    tabs = []
    for k in range(pb["tabs"]):
        box = Part.makeBox(r_out + 2, pb["tab_w"], top - z_bed, V(0, -pb["tab_w"] / 2, z_bed))
        box.rotate(V(0, 0, 0), V(0, 0, 1), 360.0 * k / pb["tabs"])
        box.translate(V(ax, ay, 0))
        tabs.append(ring.common(box).common(above_cone(-pb["gap"] - 0.8)).cut(above_cone(pb["bite"])))
    return brace.fuse(tabs).removeSplitter()


def head_lid(job):
    """Kit head lid (printed upside down like the kit) with the crown's countersunk bayonet socket
    (three notches) and the stopper-key slot."""
    cr = job["crown"]
    b = cr["bayonet"]
    lid = _kit_lid(cr)
    ax, ay = cr["axis_xy"]
    z0, r0 = cr["lid_top_z"], cr["base_r"]
    cd, cl = b["seat_depth"], b["clear"]
    rs = r0 - cd
    zb = b["lid_bottom_z"]
    g0 = zb + b["lip"]  # groove floor; the lip below it keeps the lid's underside closed
    g1 = g0 + b["lug_gap"] + b["lug_t"] + b["groove_clear"]
    cuts = [Part.makeCone(rs + cl, r0 + cl + 2.0, cd + 2.0, V(ax, ay, z0 - cd)),
            Part.makeCylinder(rs + cl, z0 - zb + 2, V(ax, ay, zb - 1)),
            Part.makeCylinder(math.hypot(b["lug_r"], b["lug_w"] / 2) + cl, g1 - g0 + 1.0, V(ax, ay, g0 - 1.0))]  # open underneath
    for a in _bayonet_layout(cr):  # entry notches from the top down to the groove floor
        ph = math.radians(a)
        er, et = V(math.cos(ph), math.sin(ph), 0), V(-math.sin(ph), math.cos(ph), 0)
        lw = b["lug_w"] / 2 + cl
        q = [V(ax, ay, g0) + er * (rs - 1.0) - et * lw, V(ax, ay, g0) + er * (b["lug_r"] + cl) - et * lw,
             V(ax, ay, g0) + er * (b["lug_r"] + cl) + et * lw, V(ax, ay, g0) + er * (rs - 1.0) + et * lw]
        cuts.append(Part.Face(Part.makePolygon(q + [q[0]])).extrude(V(0, 0, z0 - g0 + 1)))
    k = cr["key"]
    (kx0, kx1), (ky0, ky1) = k["x"], k["y"]
    cuts.append(Part.makeBox(kx1 - kx0 + 2 * k["clear"], ky1 - ky0 + 2 * k["clear"], 30,
                             V(kx0 - k["clear"], ky0 - k["clear"], z0 - 15)))
    return lid.cut(cuts).removeSplitter()


def head_arms(job):
    """Kit head cover with two twist-lock arms (see design.v3_headarms_job).  Returns (head + arms, arms only)."""
    ha = job["head_arms"]
    head = Part.read(ha["head_step"])
    head = head.Solids[0] if head.Solids else Part.makeSolid(head)
    head.translate(V(0, 0, ha["head_dz"]))
    x0, ro, we, tp = ha["x0"], ha["root"], ha["web"], ha["tip"]

    def box(xr, yr, zr):
        (x_0, x_1), (y_0, y_1), (z_0, z_1) = sorted(xr), sorted(yr), sorted(zr)
        return Part.makeBox(x_1 - x_0, y_1 - y_0, z_1 - z_0, V(x_0, y_0, z_0))

    add = []
    for sd in ha["sides"]:
        s, d = sd["s"], sd["d"]
        add.append(box([x0 - ro["half_w"], x0 + ro["half_w"]], [s * ro["y0"], s * ro["y1"]], ro["z"]))
        prof = [(ro["y0"], we["z_bottom"]), (we["y_flat_end"], we["z_bottom"]), (we["y_drop_end"], tp["z_bottom"]),
                (tp["y_back"], tp["z_bottom"]), (tp["y_back"], tp["z_top"]), (we["y_flat_end"], we["z_top"]), (ro["y0"], we["z_top"])]
        pts = [V(x0 - we["half_w"], s * y, z) for y, z in prof]
        add.append(Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(2 * we["half_w"], 0, 0)))
        x_end = sd["x_stop"] + d * tp["stop_t"]
        y_ledge = tp["y_face"] + tp["ledge_out"]
        add += [box([sd["x_open"], x_end], [s * tp["y_back"], s * tp["y_out"]], [tp["z_bottom"], ha["z_seat"]]),  # seat
                box([sd["x_open"], x_end], [s * tp["y_back"], s * tp["y_face"]], [tp["z_bottom"], tp["z_top"]]),  # back
                box([sd["x_open"], sd["x_stop"]], [s * tp["y_face"], s * y_ledge], [ha["z_ledge"], tp["z_top"]]),  # ledge
                box([sd["x_stop"], x_end], [s * tp["y_back"], s * tp["y_out"]], [tp["z_bottom"], tp["z_top"]]),  # stop
                Part.makeCylinder(ha["detent"]["protrude"], ha["z_ledge"] - ha["z_seat"] + 0.2,
                                  V(sd["detent_x"], s * tp["y_face"], ha["z_seat"] - 0.1))]
    full = head.fuse(add).removeSplitter()
    return full, full.cut(head)


def stem_lid(job):
    """Mushroom stem printed upright on the kit head lid (one part): lid with the key slot and lightening
    pockets in its top face, a hollow stem with a 45-degree root flare, ribs whose tops follow the dome's
    inner 30-degree cap, one rib rising as the rotation fin, and two spring prongs inside the stem's top
    housing whose knob is the dome's own tip shape (split by the slot)."""
    st = job["stem"]
    ax, ay = st["axis_xy"]
    zl = st["lid_top_z"]
    cap = math.radians(st["cap_slope_deg"])

    def under(s):
        return st["apex_in_z"] - s * math.tan(cap) - st["gap"]

    lid = _kit_lid(st)
    k = st["key"]
    (kx0, kx1), (ky0, ky1) = k["x"], k["y"]
    lid = lid.cut(Part.makeBox(kx1 - kx0 + 2 * k["clear"], ky1 - ky0 + 2 * k["clear"], 30,
                               V(kx0 - k["clear"], ky0 - k["clear"], zl - 15)))
    lt = st.get("lighten")
    if lt:
        z_floor = lid.BoundBox.ZMin + lt["floor"]
        (x0, x1), (y0, y1) = lt["x"], lt["y"]
        pocket = Part.makeBox(x1 - x0, y1 - y0, zl + 1 - z_floor, V(x0, y0, z_floor))
        keep = [Part.makeBox(x1 - x0 + 2, lt["rib"], 10, V(x0 - 1, ay - lt["rib"] / 2, z_floor - 1)),
                Part.makeBox(lt["rib"], y1 - y0 + 2, 10, V(ax - lt["rib"] / 2, y0 - 1, z_floor - 1)),
                Part.makeCylinder(lt["boss_r"], 10, V(ax, ay, z_floor - 1))]
        lid = lid.cut(pocket.cut(keep))

    z_p0 = st["prong_z0"]
    rt, rh = st["tube_r"], st["housing_r"]
    prof = [(0, zl - 0.5), (st["root_r"], zl - 0.5), (st["root_r"], zl), (rt, zl + st["root_r"] - rt),
            (rt, z_p0 - (rh - rt)), (rh, z_p0), (rh, under(rh)), (st["housing_bore_r"], under(st["housing_bore_r"])),
            (0, under(st["housing_bore_r"]))]
    pts = [V(ax + s, ay, z) for s, z in prof]
    stem = Part.Face(Part.makePolygon(pts + [pts[0]])).revolve(V(ax, ay, 0), V(0, 0, 1), 360)
    rb = st["tube_bore_r"]
    z_f = z_p0 - 1.0 - rb  # lower bore (lightening) with a 45-degree cone roof
    bore = [V(ax, ay, zl), V(ax + rb, ay, zl), V(ax + rb, ay, z_f), V(ax, ay, z_f + rb)]
    stem = stem.cut(Part.Face(Part.makePolygon(bore + [bore[0]])).revolve(V(ax, ay, 0), V(0, 0, 1), 360))
    stem = stem.cut(Part.makeCylinder(st["housing_bore_r"], 200, V(ax, ay, z_p0)))

    hx, top = st["prong_half_x"], st["apex_out_z"] + 5
    strip = Part.makeBox(2 * hx, 40, top, V(ax - hx, ay - 20, 0))
    prong = Part.makeCylinder(st["prong_r"], st["cut_z"] + st["knob_gap"] + 0.5 - (z_p0 - 0.5), V(ax, ay, z_p0 - 0.5))
    outer, _ = ogive(vec(st["dome_center"]), st["dome_radius"], st["cap_slope_deg"], st["tip_radius"])
    z_k = st["cut_z"] + st["knob_gap"]
    knob = outer.common(Part.makeCylinder(st["knob_r"], top - z_k, V(ax, ay, z_k)))
    slot = Part.makeBox(40, st["slot"], top, V(ax - 20, ay - st["slot"] / 2, z_p0))
    prongs = prong.fuse(knob).common(strip).cut(slot)

    ribs = []
    rb_ = st["ribs"]
    fin = st["fin"]
    r_out, z_tip = rb_["r_out"], st["rib_top_at_r_out"] - rb_["tip_h"]
    s0 = rh - 0.5
    for i in range(rb_["count"]):
        phi = rb_["phase_deg"] + 360.0 * i / rb_["count"]
        is_fin = abs((phi - fin["phi_deg"] + 180) % 360 - 180) < 1e-6
        w = fin["width"] if is_fin else rb_["thick"]
        poly = [(s0, z_tip - (r_out - s0)), (r_out, z_tip), (r_out, under(r_out)), (s0, under(s0))]
        shapes = [poly]
        if is_fin:
            f0, f1 = fin["r"]
            shapes.append([(f0, under(f0) - 1.0), (f1, under(f1) - 1.0), (f1, top), (f0, top)])
        for j, pl in enumerate(shapes):
            q = [V(s, -w / 2, z) for s, z in pl]
            solid = Part.Face(Part.makePolygon(q + [q[0]])).extrude(V(0, w, 0))
            if j:
                solid = solid.common(outer)
            solid.rotate(V(0, 0, 0), V(0, 0, 1), phi)
            solid.translate(V(ax, ay, 0))
            ribs.append(solid)
    return lid.fuse([stem, prongs] + ribs).removeSplitter()


def lid_key(job):
    """Stopper key: a forked plate through the lid slot; barbs snap under the lid, the tip blocks the lid
    from sliding back past the head-cover rear panel, the head (with a pull hole) rests on the lid."""
    cr = job.get("crown") or job["stem"]
    k = cr["key"]
    (kx0, kx1), (ky0, ky1) = k["x"], k["y"]
    zb = k["lid_bottom_z"] + cr["lid_dz"]
    zt = cr["lid_top_z"]
    yc, hy = (ky0 + ky1) / 2, (ky1 - ky0) / 2
    z_tip = zb - k["below"]
    hh, b, sl = k["head_half_y"], k["barb"], k["slit"] / 2
    zbarb = zb - 0.15  # barb shoulder just under the lid
    prof = [(yc - hy, z_tip + 0.6), (yc - hy + 0.6, z_tip), (yc + hy - 0.6, z_tip), (yc + hy, z_tip + 0.6),
            (yc + hy + b, zbarb - 1.2), (yc + hy + b, zbarb - 0.3), (yc + hy, zbarb),
            (yc + hy, zt), (yc + hh, zt), (yc + hh, zt + k["head_h"]), (yc - hh, zt + k["head_h"]), (yc - hh, zt),
            (yc - hy, zt), (yc - hy, zbarb), (yc - hy - b, zbarb - 0.3), (yc - hy - b, zbarb - 1.2)]
    pts = [V(kx0, y, z) for y, z in prof]
    key = Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(kx1 - kx0, 0, 0))
    slit_top = zb + k["slit_top_above_lid_bottom"]
    key = key.cut(Part.makeBox(kx1 - kx0 + 2, 2 * sl, slit_top - z_tip + 1, V(kx0 - 1, yc - sl, z_tip - 1)))
    key = key.cut(Part.makeCylinder(k["pull_hole_d"] / 2, kx1 - kx0 + 2, V(kx0 - 1, yc, zt + k["head_h"] / 2 + 0.2), V(1, 0, 0)))
    return key.removeSplitter()


def onepiece(job):
    return dome(job, socket=False).fuse(mount(job, one_piece=True)).removeSplitter()


def drill_guide(job):
    m = job["mount"]
    body = saddle(job)
    for x, y in m["vertical_screws"]:
        body = body.cut(Part.makeCylinder(m["guide_hole_r"], 30, V(x, y, m["cavity_top_z"] - 10)))
    return body.removeSplitter()


def export(shape, path_stem, placement=None):
    s = shape.copy()
    if placement is not None:
        s.Placement = placement.multiply(s.Placement)
        bb = s.BoundBox
        s.translate(V(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, -bb.ZMin))
    s.exportStep(path_stem + ".step")
    mesh = MeshPart.meshFromShape(Shape=s, LinearDeflection=0.05, AngularDeflection=0.2)
    mesh.write(path_stem + ".stl")
    return s


def main(job_path):
    job = json.load(open(job_path))
    out = job["out_dir"]
    os.makedirs(out, exist_ok=True)
    report = {}
    if job.get("variant") == "v3-crown":
        builders = (("shell-dome", dome), ("crown", crown), ("head-lid", head_lid), ("lid-key", lid_key))
    elif job.get("variant") == "v3-headarms":
        builders = (("shell-dome", dome),)
        if job["dome"].get("print_ties"):  # what to slice: the dome with its slot membranes
            tied = dome(job).fuse(slot_ties(job)).removeSplitter()
            if not tied.isValid() or len(tied.Solids) != 1:
                raise SystemExit(f"shell-dome-print: invalid or multi-solid result ({len(tied.Solids)} solids)")
            export(tied.Solids[0], os.path.join(out, "shell-dome-print"), FreeCAD.Placement())
        full, arms = head_arms(job)
        if not full.isValid() or len(full.Solids) != 1:
            raise SystemExit(f"head-mount: invalid or multi-solid result ({len(full.Solids)} solids)")
        export(full.Solids[0], os.path.join(out, "assembly", "head-mount"))
        export(full.Solids[0], os.path.join(out, "head-mount"), FreeCAD.Placement())  # rim on the bed, like the kit
        export(arms, os.path.join(out, "assembly", "head-arms"))
        bb = arms.BoundBox
        com = sum((so.CenterOfMass * so.Volume for so in arms.Solids), V(0, 0, 0)) * (1.0 / arms.Volume)
        report["head-arms"] = {"volume_mm3": arms.Volume, "centroid_mm": list(com),
                               "bbox_mm": [[bb.XMin, bb.YMin, bb.ZMin], [bb.XMax, bb.YMax, bb.ZMax]], "area_mm2": arms.Area,
                               "solids": len(arms.Solids), "note": "arms only (mass model); print head-mount.stl"}
    elif job.get("variant") == "v3-mushroom":
        builders = (("shell-dome", dome), ("stem-lid", stem_lid), ("lid-key", lid_key))
    elif job.get("variant") == "v3-brackets":
        builders = [("shell-dome", dome)] + [(b["name"], lambda job, b=b: bracket(b)) for b in job["brackets"]]
    elif job.get("variant") == "s3-cover":
        builders = (("shell-dome", dome), ("s3-top-cover", s3_cover))
    else:
        builders = (("shell-onepiece", onepiece), ("drill-guide", drill_guide),
                    ("shell-dome", dome), ("shell-mount", mount))
    for name, fn in builders:
        shape = fn(job)
        if not shape.isValid() or len(shape.Solids) != 1:
            raise SystemExit(f"{name}: invalid or multi-solid result ({len(shape.Solids)} solids)")
        shape = shape.Solids[0]
        export(shape, os.path.join(out, "assembly", name))
        rot = FreeCAD.Placement(V(0, 0, 0), FreeCAD.Rotation(V(1, 0, 0), 0))
        if name == "lid-key":  # print flat: the YZ profile on the bed
            rot = FreeCAD.Placement(V(0, 0, 0), FreeCAD.Rotation(V(0, 1, 0), 90))
        if name == "head-lid":  # like the kit: outer face down
            rot = FreeCAD.Placement(V(0, 0, 0), FreeCAD.Rotation(V(1, 0, 0), 180))
        if name == "crown":  # print the unlocked (as-inserted) orientation; geometry is identical up to a turn
            shape_print = crown(job, locked=False).Solids[0]
        export(shape_print if name == "crown" else shape, os.path.join(out, name), rot)  # print orientation, on the bed
        if name == "crown" and job["crown"].get("print_brace"):  # what to slice: the crown on its print aid
            braced = shape_print.fuse(crown_brace(job)).removeSplitter()
            if not braced.isValid() or len(braced.Solids) != 1:
                raise SystemExit(f"crown-print: invalid or multi-solid result ({len(braced.Solids)} solids)")
            export(braced.Solids[0], os.path.join(out, "crown-print"), rot)
            print(f"crown-print: brace {braced.Volume - shape_print.Volume:.0f} mm3")
        bb = shape.BoundBox
        report[name] = {"volume_mm3": shape.Volume, "centroid_mm": list(shape.CenterOfMass),
                        "bbox_mm": [[bb.XMin, bb.YMin, bb.ZMin], [bb.XMax, bb.YMax, bb.ZMax]],
                        "area_mm2": shape.Area}
    json.dump(report, open(os.path.join(out, "cad.json"), "w"), indent=1)
    print(json.dumps({k: round(v["volume_mm3"]) for k, v in report.items()}))


if __name__ == "__main__":
    os.makedirs(json.load(open(sys.argv[1]))["out_dir"] + "/assembly", exist_ok=True)
    main(sys.argv[1])
