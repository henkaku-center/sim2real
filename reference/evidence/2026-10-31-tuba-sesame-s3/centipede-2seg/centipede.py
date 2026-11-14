"""Two-segment centipede body for the Sesame V3 kit (4 legs, 2 per segment).

Segment 1 (front, "head"): V3 frame with only the FRONT servo bays (L1, R1),
moved back so the hip shafts sit at the segment centre,
battery in the native V3 battery bay, toggle switch in the front wall.
Segment 2 (rear, "body"): V3 frame with only the REAR servo bays (L2, R2),
moved forward so the hip shafts sit at the segment centre,
PCB on the native V3 spacers, USB at the rear like V3.

Each segment = frame + V3 bottom cover (its bay tabs moved the same way) + base + cap.
  base: the V3 head-cover band below Z_SPLIT (same 4 head screws into the frame).
  cap:  a round dome with a skirt over the base, held by 2 M2x5 screws at the ends.
Hinge: fork (seg 2) + tongue (seg 1). Pivot = a long countersunk self-tapping screw
(clearance + countersink in the top tab and tongue, threads into the bottom tab; M3 bolt + nut also fits).
A second screw ("lock") beside the pivot makes the body rigid for walking tests.
Run: python centipede.py <kit> <out>
"""
import json, math, sys
import numpy as np, trimesh, manifold3d as mf

KIT, OUT = sys.argv[1], sys.argv[2]
T = 1.2                 # cap wall
Z_SPLIT = 19.0          # base keeps the V3 band below this
SKIRT_Z = 15.2          # cap skirt bottom (V3 ribbon notches end at Z 14.97)
FIT = 0.25              # skirt / band clearance
PIN = 12.5              # pivot distance from each frame end
HR = 11.0               # hinge tongue/tab radius around the pivot
BOLT = 3.3              # clearance hole (2.9 mm self-tapper or M3)
PILOT = 2.4             # self-tap pilot in the bottom fork tab
LOCK_Y = 7.0            # lock bolt offset from the pivot
Z_TOP, Z_BOT = 4.968, -10.732                       # V3 frame top / bottom
TABS = [(Z_TOP - 4.0, Z_TOP), (Z_BOT, Z_BOT + 4.0)]  # fork tabs (seg 2)
TONGUE = (Z_BOT + 4.5, Z_TOP - 4.5)                  # tongue (seg 1), 0.5 mm play each side
X_FRONT, X_REAR = 43.702, -43.475                    # V3 frame ends
DX2 = X_REAR - 2 * PIN - X_FRONT                     # seg 2 offset in X (assembly)
mf.set_circular_segments(96)

def load(f):
    m = trimesh.load(f"{KIT}/{f}")
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                               tri_verts=np.asarray(m.faces, np.uint32)))
def box(x0, x1, y0, y1, z0, z1):
    return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])
def above(m, z): return m.trim_by_plane([0, 0, 1], z)
def below(m, z): return m.trim_by_plane([0, 0, -1], -z)
def zcyl(x, y, r, z0, z1): return mf.Manifold.cylinder(z1 - z0, r, r).translate([x, y, z0])
def xcyl(x0, x1, y, z, r): return mf.Manifold.cylinder(x1 - x0, r, r).rotate([0, 90, 0]).translate([x0, y, z])
def ycyl(x, y0, y1, z, r): return mf.Manifold.cylinder(y1 - y0, r, r).rotate([-90, 0, 0]).translate([x, y0, z])

frame, cover, head = load("internal-frame.stl"), load("bottom-cover.stl"), load("head-cover.stl")
dat = json.load(open(f"{KIT}/assembly.json"))

# ---- frames: keep one pair of servo bays (outside |Y| 31.875), moved to the segment centre ----
BAY_Y = 31.875
hip = dat["hip_shaft_xy_mm"]
SHIFT = {True: -hip["L1"][0], False: -hip["L2"][0]}     # front bays back / rear bays forward: hips at X 0
def bays(front, by=BAY_Y):
    x0, x1 = (-1, 60) if front else (-60, -1)
    return box(x0, x1, by, 60, -20, 10) + box(x0, x1, -60, -by, -20, 10)
def centred(m, front, by=BAY_Y):  # m without any bays, plus one pair moved to the centre
    core = m - bays(True) - bays(False)
    # Take the bays a little deeper (by - 0.4) so they overlap the core (face-to-face contact
    # gives non-manifold edges), but keep the overlap only where the core is solid at the new place.
    ext = box(-60, 60, by - 0.4, 60, -20, 10) + box(-60, 60, -60, -by + 0.4, -20, 10)
    side = box(-1, 60, -60, 60, -20, 10) if front else box(-60, -1, -60, 60, -20, 10)
    strip = box(-60, 60, by - 0.4, BAY_Y, -20, 10) + box(-60, 60, -BAY_Y, -by + 0.4, -20, 10)
    moved = (m ^ ext ^ side).translate([SHIFT[front], 0, 0])
    return core + (moved - (strip - core))
def hinge_plate(x_end, sign, z0, z1, into=6.0):
    """Neck from the frame end wall out to a disc around the pivot (sign: +1 = +X)."""
    px = x_end + sign * PIN
    neck = box(min(x_end - sign * into, px), max(x_end - sign * into, px), -HR, HR, z0, z1)
    return neck + zcyl(px, 0, HR, z0, z1), px
def bolt_holes(px):  # tongue: clearance for both screws, it turns on the pivot shank
    return zcyl(px, 0, BOLT / 2, -30, 30) + zcyl(px, LOCK_Y, BOLT / 2, -30, 30)
def fork_holes(px):
    """Long countersunk self-tapping screws (~2.9 mm), no nut: clearance + countersink in the
    top tab, pilot in the bottom tab so the screw threads into it. An M3 bolt + nut also fits."""
    h = None
    for y in (0, LOCK_Y):
        c = zcyl(px, y, BOLT / 2, TABS[1][1] + 0.5, 30)                     # top tab + gap: clearance
        cs = mf.Manifold.cylinder(1.8, BOLT / 2, 3.2).translate([px, y, Z_TOP - 1.8])   # 90 deg countersink, 6.4 mm
        pilot = zcyl(px, y, PILOT / 2, -30, TABS[1][1] + 0.5)               # bottom tab: self-tap pilot
        h = (c + cs + pilot) if h is None else h + c + cs + pilot
    return h

tongue, px1 = hinge_plate(X_REAR, -1, *TONGUE)
frame1 = (centred(frame, True) + tongue) - bolt_holes(px1)      # front segment: L1/R1 at its centre
fork = mf.Manifold.batch_boolean([hinge_plate(X_FRONT, +1, *t)[0] for t in TABS], mf.OpType.Add)
px2 = X_FRONT + PIN
frame2 = (centred(frame, False) + fork) - fork_holes(px2)       # rear segment: L2/R2 at its centre
def centred_cover(front):
    """Cover: its body edge is a chamfer right at |Y| 31.8, which the plain cut slices into
    slivers. Move only the bay tabs (|Y| > 32.4) and join each to the body with a bridge block."""
    core = cover - bays(True) - bays(False)
    parts = []
    for t in (cover ^ bays(front, 32.4)).decompose():
        x0, y0, z0, x1, y1, z1 = t.bounding_box()
        ys = (30.5, 32.6) if y0 > 0 else (-32.6, -30.5)
        bridge = box(x0 + 0.3, x1 - 0.3, ys[0], ys[1], z0 + 0.2, z1 - 0.2) ^ cover.hull()   # inset: no shared faces
        parts.append(t + bridge)
    return core + mf.Manifold.batch_boolean(parts, mf.OpType.Add).translate([SHIFT[front], 0, 0])
cover1, cover2 = centred_cover(True), centred_cover(False)

# ---- bases: V3 band below Z_SPLIT + wire notch at the hinge end + cap screw bosses ----
band = below(head, Z_SPLIT)
SCREW_Y, SCREW_Z = 12.0, 16.9          # M2x5 cap screws, horizontal along X at both ends
def end_x(m, z, sign):  # outer X of the band wall at height z, y = SCREW_Y
    s = (m ^ box(-60, 60, SCREW_Y - 0.5, SCREW_Y + 0.5, z - 0.5, z + 0.5)).bounding_box()
    return s[3] if sign > 0 else s[0]
def boss(sign):
    xo = end_x(band, SCREW_Z, sign)
    xi = xo - sign * 6.0                # 6 mm deep from the outer face (wall + boss)
    top = box(min(xo, xi), max(xo, xi), SCREW_Y - 3, SCREW_Y + 3, Z_SPLIT - 4.0, Z_SPLIT)
    foot = box(min(xo, xo - sign * 1.5), max(xo, xo - sign * 1.5), SCREW_Y - 3, SCREW_Y + 3, Z_SPLIT - 8.0, Z_SPLIT - 7.9)
    return mf.Manifold.batch_hull([top, foot]) ^ below(head.hull(), Z_SPLIT)   # 45-ish wedge, stays inside the V3 outline
def pilot(sign):
    xo = end_x(band, SCREW_Z, sign)
    return xcyl(xo - 8 if sign > 0 else xo - 1, xo + 1 if sign > 0 else xo + 8, SCREW_Y, SCREW_Z, 0.8)
def wire_notch(sign):  # bottom-open cable slot in the hinge-end wall, 12 x 8 mm
    return box(36, 60, -6, 6, 0, 13.0) if sign > 0 else box(-60, -36, -6, 6, 0, 13.0)

# Switch (blue mini toggle, MTS-102 type): 6.5 mm hole in the seg 1 front wall, Z 10.
SW_Z, SW_D = 10.0, 6.5
sw_hole = xcyl(30, 60, 0, SW_Z, SW_D / 2)

base1 = (band + boss(+1) + boss(-1)) - pilot(+1) - pilot(-1) - wire_notch(-1) - sw_hole
base2 = (band + boss(+1) + boss(-1)) - pilot(+1) - pilot(-1) - wire_notch(+1)

# ---- caps: round dome + skirt over the band, ledge resting on the band top ----
O = mf.CrossSection.batch_hull([head.slice(z) for z in np.linspace(SKIRT_Z, Z_SPLIT - 0.05, 6)])   # band outer envelope
O = O.simplify(0.05).hull()
O_in, O_out = O.offset(FIT, mf.JoinType.Round).simplify(0.02), O.offset(FIT + T, mf.JoinType.Round).simplify(0.02)
b = O.bounds(); XC = (b[0] + b[2]) / 2; HX, HY = (b[2] - b[0]) / 2, (b[3] - b[1]) / 2
H = 37.0                                 # dome height above Z_SPLIT
def dome(cs, h, n=40):
    """Round dome on a rounded-rect footprint: footprint scaled by cos(t) at height h*sin(t)."""
    c = (XC, (b[1] + b[3]) / 2)
    rings = [slab(cs.translate([-c[0], -c[1]]).scale([math.cos(t), math.cos(t)]).translate([c[0], c[1]]),
                  Z_SPLIT + h * math.sin(t), Z_SPLIT + h * math.sin(t) + 0.01)
             for t in np.linspace(0, math.radians(86), n)]
    return mf.Manifold.batch_hull(rings)
def slab(cs, z0, z1): return mf.Manifold.extrude(cs, z1 - z0).translate([0, 0, z0])
outer = slab(O_out, SKIRT_Z, Z_SPLIT) + dome(O_out, H)
inner_skirt = slab(O_in, SKIRT_Z - 1, Z_SPLIT)
inner_dome = above(dome(O_in.offset(-0.6, mf.JoinType.Round), H - T), Z_SPLIT + 1.0)
ledge_hole = slab(O.offset(-1.4, mf.JoinType.Round), Z_SPLIT - 0.5, Z_SPLIT + 1.5)   # ledge = 1.65 mm ring resting on the band top
cap = outer - inner_skirt - inner_dome - ledge_hole
def cap_holes(sign):
    xo = end_x(band, SCREW_Z, sign)
    return xcyl(xo - 2 if sign > 0 else xo - 6, xo + 6 if sign > 0 else xo + 2, SCREW_Y, SCREW_Z, 1.15)
cap = cap - cap_holes(+1) - cap_holes(-1)
usb = box(-75, -30.9, -17.4, -5.4, 19.9, 26.9)             # exact V3 USB opening (seg 2 rear)
cap1, cap2 = cap, cap - usb

# ---- assembly + checks ---------------------------------------------------
def yaw(m, deg):   # rotate seg 2 about the pivot (assembly coords)
    p = X_REAR - PIN
    return m.translate([-p, 0, 0]).rotate([0, 0, deg]).translate([p, 0, 0])
def at2(m): return m.translate([DX2, 0, 0])
seg1 = [frame1, cover1, base1, cap1]
seg2 = [at2(m) for m in (frame2, cover2, base2, cap2)]
legs_zone = lambda front: box(-60, 60, BAY_Y, 90, -60, 22.1) + box(-60, 60, -90, -BAY_Y, -60, 22.1)
def moved_bay(front): return ((frame ^ bays(front)).translate([SHIFT[front], 0, 0]))
pcb = box(-35, 35, -25, 25, 7.97, 7.97 + 1.6)
pcb_space = box(-35, 35, -25, 25, 7.97, 7.97 + 20)   # board + 20 mm of parts (ESP32 on headers, hub)
pcb_mid = box(-30, 30, -21, 21, 7.97, 7.97 + 30)     # taller parts away from the board corners (V3-like)
battery = box(3.5 - 25.5, 3.5 + 25.5, -14, 14, -13, 1)  # V3 battery envelope 51 x 28 x 14

def vol(m): return round(m.volume(), 3)
checks = {"pivot_x_seg1": round(px1, 3), "pivot_x_seg2_local": round(px2, 3), "seg2_offset_x": round(DX2, 3)}
checks["pivot_aligned"] = round(abs((px2 + DX2) - px1), 4)
checks["frame_single_solid"] = [len(frame1.decompose()), len(frame2.decompose())]
checks["moved_bays_identical_to_v3_mm3"] = [vol((frame1 ^ legs_zone(True)) - moved_bay(True)) + vol(moved_bay(True) - frame1),
                                            vol((frame2 ^ legs_zone(False)) - moved_bay(False)) + vol(moved_bay(False) - frame2)]
checks["hip_x_in_segment_mm"] = [round(hip["L1"][0] + SHIFT[True], 3), round(hip["L2"][0] + SHIFT[False], 3)]
checks["covers_single_solid"] = [len(cover1.decompose()), len(cover2.decompose())]
bosses = boss(+1) + boss(-1)
checks["band_unchanged_below_14_mm3"] = vol(below(base2, 14) - bosses - below(head, 14) - wire_notch(+1)) + vol(below(head, 14) - wire_notch(+1) - below(base2, 14))
checks["cap_vs_base_overlap_mm3"] = [vol(cap1 ^ base1), vol(cap2 ^ base2)]
top = head.slice(Z_SPLIT - 0.05)
checks["cap_ledge_rests_on_band_mm2"] = round(top.area() - (top - O.offset(-1.4, mf.JoinType.Round)).area(), 1)
checks["cap_inner_top_z"] = round(Z_SPLIT + H - T, 1)
checks["cap_size_mm"] = [round(v, 1) for v in cap.bounding_box()]
checks["pcb_space_blocked_mm3 (20 mm / 30 mm mid / board)"] = [vol(pcb_space ^ (base2 + cap2)), vol(pcb_mid ^ (base2 + cap2)), vol(pcb ^ frame2)]
checks["battery_blocked_by_hinge_mm3"] = vol(battery ^ frame1) - vol(battery ^ frame)
checks["usb_opening_blocked_mm3"] = vol(box(-75, -30.9, -17.4, -5.4, 19.9, 26.9) ^ (base2 + cap2))
checks["switch_wall_mm"] = round((base1 ^ xcyl(30, 60, 0, SW_Z + SW_D / 2 + 1, 0.3)).volume() / (math.pi * 0.09), 2)
checks["switch_body_space_blocked_mm3 (13 wide x 8 tall x 16 deep)"] = vol(box(43.7 - 2.0 - 16, 43.7 - 2.0, -6.5, 6.5, SW_Z - 4, SW_Z + 4) ^ (frame1 + base1 + cap1))
checks["switch_nut_zone_blocked_mm3"] = vol(box(43.7, 52, -5, 5, SW_Z - 4.6, SW_Z + 4.6) ^ (frame1 + cover1 + cap1))
checks["switch_nut_flat_face"] = [round(v, 2) for v in (base1 ^ box(40, 60, -6, 6, SW_Z - 5, SW_Z + 5)).bounding_box()]
checks["hinge_parts_touch_mm3"] = vol(tongue.translate([0, 0, 0]) ^ at2(fork))
sweep = {}
for a in (-35, -30, -25, -15, 0, 15, 25, 30, 35):
    s2 = [yaw(m, a) for m in seg2]
    hit = sum((p ^ q).volume() for p in seg1 for q in s2)
    sweep[a] = round(hit, 2)
checks["yaw_collision_mm3_by_deg"] = sweep
checks["max_half_width_mm"] = round(max(-cap.bounding_box()[1], cap.bounding_box()[4]), 1)
checks["overall_length_frames_mm"] = round(X_FRONT - (X_REAR + DX2), 1)
# Balance (estimated masses, g; X of each mass in assembly coords).
FEET_Y = 50.0                                        # foot Y in stand (raised feet start at 49)
feet = {"L1": (0.0, FEET_Y), "R1": (0.0, -FEET_Y), "L2": (DX2, FEET_Y), "R2": (DX2, -FEET_Y)}   # hips at segment centres
servo_x1, servo_x2 = dat["servo_mounts"]["L1"]["caseCenter"][0] + SHIFT[True], dat["servo_mounts"]["L2"]["caseCenter"][0] + SHIFT[False] + DX2
PLA = 1.24e-3 * 0.55                                 # printed part ~55 % of solid (walls + 25 % infill)
masses = [  # (name, g, x)
    ("seg1 frame+base+cap+cover", (frame1.volume() + base1.volume() + cap1.volume() + cover1.volume()) * PLA, 0.0),
    ("seg1 4 servos + 2 legs", 4 * 13.4 + 8, servo_x1),
    ("battery (V3 bay, 1S ~1000 mAh)", 30, 3.5), ("switch + OLED", 8, 30),
    ("seg2 frame+base+cap+cover", (frame2.volume() + base2.volume() + cap2.volume() + cover2.volume()) * PLA, DX2),
    ("seg2 4 servos + 2 legs", 4 * 13.4 + 8, servo_x2),
    ("PCB + ESP32 + hub + wires", 35, DX2), ("hinge bolts", 4, X_REAR - PIN)]
M = sum(m for _, m, _ in masses); cx = sum(m * x for _, m, x in masses) / M
def line_dist(p, a, b):
    (ax, ay), (bx, by) = a, b
    return abs((bx - ax) * (ay - p[1]) - (ax - p[0]) * (by - ay)) / math.hypot(bx - ax, by - ay)
checks["mass_g_est"] = round(M)
checks["com_x_mm"] = round(cx, 1)
checks["support_x_range_mm"] = [round(feet["L2"][0], 1), round(feet["L1"][0], 1)]
checks["com_margin_4_feet_mm"] = round(min(cx - feet["L2"][0], feet["L1"][0] - cx, FEET_Y), 1)
checks["com_off_diagonal_mm (trot pairs)"] = [round(line_dist((cx, 0), feet["L1"], feet["R2"]), 1), round(line_dist((cx, 0), feet["R1"], feet["L2"]), 1)]
checks["com_margin_3_feet_mm (one foot lifted)"] = {k: round(min(line_dist((cx, 0), feet[a], feet[b]) for a, b in
    [(p, q) for i, p in enumerate(o) for q in o[i + 1:]]), 1) for k in feet for o in [[f for f in feet if f != k]]}
for name, m in (("frame1", frame1), ("frame2", frame2), ("cover1", cover1), ("cover2", cover2), ("base1", base1), ("base2", base2), ("cap1", cap1), ("cap2", cap2)):
    checks[f"{name}_parts_volume"] = [len(m.decompose()), round(m.volume(), 1)]
print(json.dumps(checks, indent=1))
json.dump(checks, open(f"{OUT}/centipede-checks.json", "w"), indent=1)

def export(m, name, flip=False):
    mm = m.to_mesh(); tm = trimesh.Trimesh(mm.vert_properties[:, :3], mm.tri_verts, process=False)
    tm.export(f"{OUT}/{name}.stl")
    p = tm.copy()
    if flip: p.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
    p.apply_translation([0, 0, -p.bounds[0][2]]); p.export(f"{OUT}/{name}-print.stl")
export(frame1, "seg1-frame", flip=True); export(frame2, "seg2-frame", flip=True)   # PCB-side face down, like V3
export(cover1, "seg1-cover"); export(cover2, "seg2-cover")
export(base1, "seg1-base"); export(base2, "seg2-base")
export(cap1, "seg1-cap"); export(cap2, "seg2-cap")
