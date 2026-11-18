"""Rounded thin glow head for the Sesame V3 frame.

Keeps the V3 head-cover below Z_BAND (screw bosses, ribbon/battery notches,
USB opening) unchanged and replaces everything above it with a rounded,
thin-walled dome. Keeps the original OLED front plate and switch rear plate
and adds tunnels through the new wall. No lid: remove the 4 head screws to open.
"""
import json, math, sys
import numpy as np, trimesh, manifold3d as mf

KIT, OUT = sys.argv[1], sys.argv[2]
T = float(sys.argv[3]) if len(sys.argv) > 3 else 1.2   # dome wall (mm)
Z_BAND = 16.0          # keep V3 shell below this (notches end at Z 15)
R = 18.0               # dome corner sphere radius
CX, CY, CZ = (-31.0, 28.0), 17.0, 40.0   # sphere centres: rear/front X, +-Y, Z
mf.set_circular_segments(96)

def load(f):
    m = trimesh.load(f"{KIT}/{f}")
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                               tri_verts=np.asarray(m.faces, np.uint32)))
def box(x0, x1, y0, y1, z0, z1):
    return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])
def above(m, z): return m.trim_by_plane([0, 0, 1], z)
def below(m, z): return m.trim_by_plane([0, 0, -1], -z)

orig = load("head-cover.stl")
band = below(orig, Z_BAND)
outline = orig.slice(Z_BAND - 0.01).hull()          # outer footprint at the joint

def dome(r, inset):
    slab = mf.Manifold.extrude(outline.offset(-inset, mf.JoinType.Round), 0.02).translate([0, 0, Z_BAND - 0.01])
    balls = [mf.Manifold.sphere(r).translate([x, s * CY, CZ]) for x in CX for s in (1, -1)]
    return mf.Manifold.batch_hull([slab] + balls)

outer = above(dome(R, 0), Z_BAND)
inner = dome(R - T, T) + mf.Manifold.extrude(outline.offset(-T, mf.JoinType.Round), 2).translate([0, 0, Z_BAND - 1.5])
shell = outer - inner

orig_hull = below(above(orig, Z_BAND), 52.0).hull()  # V3 shell volume (no ears)
cavity = orig_hull - orig               # V3 interior only (sleeves fuse into the V3 wall)

# OLED: keep the V3 front plate around the window, fill the gap to the new wall, cut a tunnel.
win = mf.Manifold.batch_hull([box(30, 36.4, -11.8, 11.8, 29.6, 42.6), box(56, 56.1, -14.6, 14.6, 27.2, 45.0)])  # flared visor
front_keep = orig ^ box(32, 45, -16, 16, 26.5, 46)
# V3 inner front-wall plane (normal = display normal): keep the sleeve in front of it.
front_sleeve = (outer ^ box(32, 70, -16.2, 16.2, 25.6, 46.6)).trim_by_plane([0.96, 0.0, 0.28], 44.7)
# Switch: keep the V3 rear plate around the bore, sleeve to the new wall, tunnel along the bore.
sw = json.load(open(f"{KIT}/assembly.json"))["head_fit"]["switch_opening"]
c, n = np.array(sw["centre_mm"]), np.array(sw["normal"])
theta = math.degrees(math.atan2(n[0], n[2]))
bore = mf.Manifold.cylinder(40, 3.0, 3.0).translate([0, 0, -20]).rotate([0, theta, 0]).translate(c.tolist())
rear_keep = orig ^ box(-45, -35, -7, 7, Z_BAND - 0.5, 45)
# USB: keep the V3 rear wall around the port, sleeve to the new wall, cut the opening through.
usb = box(-70, -30.9, -17.9, -4.9, 19.4, 27.4)
usb_keep = orig ^ box(-46, -28, -20, -2.3, Z_BAND - 0.5, 30)
usb_sleeve = (outer ^ box(-70, -30, -19.6, -3.2, 17.7, 29.1)) - cavity
rear_sleeve = (outer ^ mf.Manifold.cylinder(40, 4.8, 4.8).translate([0, 0, -20]).rotate([0, theta, 0]).translate(c.tolist())) - cavity

head = (band + shell + front_keep + front_sleeve + rear_keep + rear_sleeve + usb_keep + usb_sleeve) - win - bore - usb
head = mf.Manifold.batch_boolean([q for q in head.decompose() if q.volume() > 1.0], mf.OpType.Add)  # drop zero-volume slivers

# ---- checks -------------------------------------------------------------
frame = load("internal-frame.stl")
legs_zone = box(-80, 80, 31.6, 90, -60, 22.1) + box(-80, 80, -90, -31.6, -60, 22.1)
b = head.bounding_box()
checks = {
    "wall_mm": T,
    "volume_mm3": round(head.volume(), 1),
    "mass_g_PLA_100pct": round(head.volume() * 1.24e-3, 1),
    "bounds_mm": [round(v, 1) for v in b],
    "watertight_genus": head.genus(),
    "band_unchanged_mm3": round((below(head, Z_BAND - 0.6) - below(orig, Z_BAND - 0.6)).volume()
                                + (below(orig, Z_BAND - 0.6) - below(head, Z_BAND - 0.6)).volume(), 3),
    "v3_volume_outside_new_mm3": round((orig_hull - (outer + box(-60, 60, -40, 40, 0, Z_BAND))).volume(), 2),
    "oled_tunnel_blocked_mm3": round((head ^ box(36.4, 70, -11.25, 11.25, 29.95, 42.1)).volume(), 3),
    "switch_bore_blocked_mm3": round((head ^ mf.Manifold.cylinder(40, 2.5, 2.5).translate([0, 0, -20]).rotate([0, theta, 0]).translate(c.tolist())).volume(), 3),
    "usb_opening_blocked_mm3": round((head ^ box(-70, -30.9, -17.4, -5.4, 19.9, 26.9)).volume(), 3),
    "v3_interior_intrusion_mm3": round(((head - orig) ^ below(cavity, 51.5)).trim_by_plane([-0.96, 0.0, -0.28], -44.7).volume(), 2),
    "frame_overlap_mm3": round((head ^ frame).volume(), 3),
    "leg_zone_overlap_mm3": round((head ^ legs_zone).volume(), 3),
}
m = head.to_mesh(); tm = trimesh.Trimesh(m.vert_properties[:, :3], m.tri_verts)
nz = tm.face_normals[:, 2]; dome_faces = tm.triangles_center[:, 2] > Z_BAND + 0.5
down = dome_faces & (nz < -1e-3)
checks["max_overhang_deg_from_vertical"] = round(float(np.degrees(np.arcsin(-nz[down])).max()) if down.any() else 0, 1)
checks["overhang_area_over45_mm2"] = round(float(tm.area_faces[down & (nz < -math.sin(math.radians(45)))].sum()), 1)
tm.merge_vertices(); checks["watertight"] = bool(tm.is_watertight); checks["parts"] = len(head.decompose()); checks["status"] = str(head.status())
for q in head.decompose(): print("part", round(q.volume(),1), [round(v,1) for v in q.bounding_box()])
print(json.dumps(checks, indent=1))
tm.export(f"{OUT}/round-head-{T:.1f}mm.stl")
p = tm.copy(); p.apply_translation([0, 0, -p.bounds[0][2]]); p.export(f"{OUT}/round-head-{T:.1f}mm-print.stl")
json.dump(checks, open(f"{OUT}/round-head-{T:.1f}mm-checks.json", "w"), indent=1)
