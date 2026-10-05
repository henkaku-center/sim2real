"""Scripted FreeCAD body source. Units mm, torso-local x-forward/y-left/z-up.

Native electronics remain read-only. Upstream frame, bottom and leg templates
are immutable references, rather than remodeled approximations of servo pockets.
No GUI, recompute/save of the electronics, network, or hidden workbench state.
"""
from pathlib import Path
import hashlib
import gzip
import json
import math
import os
import struct
import zipfile
import xml.etree.ElementTree as ET

import FreeCAD as App  # Must precede Mesh (otherwise some bundles exit silently).
import Part
import Mesh
import MeshPart

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARAMS = ROOT / "assets/body/params.json"
ASSEMBLY = ROOT / "assets/cad/Sesame-S3-Assembly.FCStd"
SNAPSHOT = ROOT / "assets/cad/instructions/assembly-cad-snapshot.json"
UPSTREAM = ROOT / "assets/stl/upstream"
V = App.Vector


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def bounds(shape):
    b = shape.BoundBox
    return [[b.XMin, b.YMin, b.ZMin], [b.XMax, b.YMax, b.ZMax]]


def box(size, origin):
    return Part.makeBox(*size, V(*origin))


def cylinder(radius, height, origin, direction=(0, 0, 1)):
    return Part.makeCylinder(radius, height, V(*origin), V(*direction))


def moved(shape, offset):
    s = shape.copy()
    s.translate(V(*offset))
    return s


def union(shapes):
    shapes = list(shapes)
    return shapes[0].multiFuse(shapes[1:]).removeSplitter() if len(shapes) > 1 else shapes[0]


def tube_route(points, radius):
    """Capsule sweep of a ball along a polyline, including rounded bend volumes."""
    shapes = []
    for a, b in zip(points, points[1:]):
        delta = V(*b) - V(*a)
        if delta.Length > 1e-6:
            shapes.append(cylinder(radius, delta.Length, a, tuple(delta)))
    shapes += [Part.makeSphere(radius, V(*p)) for p in points]
    return union(shapes)


def world(obj):
    s = obj.Shape.copy()
    s.Placement = obj.getGlobalPlacement().multiply(obj.Placement.inverse()).multiply(s.Placement)
    return s


def asm_to_body():
    # Matches sim.prepare_assets.M_ASM and TORSO_ORIGIN, in mm (not metres).
    return App.Matrix(-1, 0, 0, 26, 0, 0, 1, 0, 0, 1, 0, -17, 0, 0, 0, 1)


def mesh_solid(path, matrix=None):
    mesh = Mesh.Mesh(str(path))
    if mesh.CountFacets == 0 or not mesh.isSolid():
        raise ValueError(f"Not a closed mesh / LFS pointer: {path}")
    if matrix:
        mesh.transform(matrix)
    key = hashlib.sha256((digest(path)+str(matrix)+Part.OCC_VERSION).encode()).hexdigest()
    cache = ROOT / "assets/cad/upstream/body-cache" / (key+".brep")
    if cache.exists():
        solid = Part.Shape()
        solid.read(str(cache))
    else:
        s = Part.Shape()
        s.makeShapeFromMesh(mesh.Topology, 1e-5)
        solid = Part.makeSolid(s).removeSplitter()
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(f".{os.getpid()}.tmp.brep")
        solid.exportBrep(str(temporary))
        temporary.replace(cache)
    if not solid.isValid() or solid.Volume <= 0:
        raise ValueError(f"Invalid faceted reference: {path}")
    return solid, mesh


def load_electronics():
    snap = json.loads(SNAPSHOT.read_text())
    if snap["documents"]["assembly"]["saved_file_sha256"] != digest(ASSEMBLY):
        raise ValueError("Assembly snapshot is stale; refresh it before body fitting")
    doc = App.openDocument(str(ASSEMBLY))
    shapes, meta = {}, {}
    for row in snap["objects"]:
        if not row["export_visible_geometry"]:
            continue
        obj = doc.getObject(row["native_object"])
        if obj.TypeId in ("App::DocumentObjectGroup", "App::Part"):
            continue  # containers duplicate their already enumerated leaves
        s = world(obj)
        if s.isNull():
            raise ValueError(f"Empty visible electronics object: {obj.Name}")
        shapes[obj.Name] = s
        appearance = row.get("appearance", {}).get("materials", [])
        meta[obj.Name] = {
            "id": row["id"], "native_object": obj.Name, "label": obj.Label,
            "solid_count": len(s.Solids),
            "color": appearance[0]["DiffuseColor"][:3] if appearance else [0.25, 0.3, 0.35],
        }
    mount = doc.MountingHoleParameters
    holes = sorted([tuple(world(o).BoundBox.Center)[:2] for o in doc.Objects
                    if o.Name.startswith("MountingHole_") and hasattr(o, "Shape")])
    if len(holes) != 4:
        # Named cutters in this revision are MountHole_*; use their native datum.
        holes = [(x, y) for x in [mount.InsetX.Value, doc.Carrier.Length.Value - mount.InsetX.Value]
                 for y in [mount.InsetY.Value, doc.Carrier.Width.Value - mount.InsetY.Value]]
    return doc, shapes, meta, holes, mount.Diameter.Value


def build(params=None):
    p = params or json.loads(DEFAULT_PARAMS.read_text())
    for path, expected in json.loads((ROOT / "assets/body/frozen-inputs.json").read_text()).items():
        if digest(ROOT / path) != expected:
            raise ValueError(f"Frozen interface/leg input changed: {path}")
    w, gap = p["wall_mm"], p["fit_gap_mm"]
    if w < p["minimum_wall_mm"] or gap <= 0:
        raise ValueError("Wall below configured minimum or nonpositive fit gap")
    if p["carrier_z_mm"] <= p["deck_z_mm"] + 2*w:
        raise ValueError("Carrier must be above the deck")
    print("Loading authoritative electronics", flush=True)
    doc, native, native_meta, holes, hole_d = load_electronics()
    offset = [*p["carrier_translation_xy_mm"], p["carrier_z_mm"]]
    components = {"electronics." + n: moved(s, offset) for n, s in native.items()}
    cm = {"electronics." + n: {**native_meta[n], "kind": "electronics", "evidence": "native CAD"} for n in native}
    parts, pm = {}, {}
    print("Converting frozen interface meshes", flush=True)
    frame, frame_mesh = mesh_solid(UPSTREAM / "Internal-Frame-v121.stl", asm_to_body())
    bottom, bottom_mesh = mesh_solid(UPSTREAM / "Bottom-Cover-v121.stl", asm_to_body())
    top_reference = Mesh.Mesh(str(UPSTREAM / "Top-Cover-Enclosed-v117.stl"))
    if top_reference.CountFacets == 0:
        raise ValueError("Empty upstream top cover / LFS pointer")
    top_reference.transform(asm_to_body())

    def part(name, s, color, frozen=False, print_rotation=None):
        parts[name] = s
        pm[name] = {"id": "body." + name, "color": color, "frozen_upstream": frozen,
                    "print_rotation_axis_angle": print_rotation or [1, 0, 0, 0]}

    def component(name, s, color, kind, evidence="assumed envelope"):
        components[name] = s
        cm[name] = {"id": name, "color": color, "kind": kind, "evidence": evidence}

    part("interface-frame", frame, [0.65, 0.68, 0.73], True, print_rotation=[1,0,0,180])
    part("bottom-cover", bottom, [0.65, 0.68, 0.73], True)
    X, Y = p["body_size_xy_mm"]
    z, cz, top = p["deck_z_mm"], p["carrier_z_mm"], p["cover_top_z_mm"]
    # Old board attachment bores, fitted to 24-vertex rings in the upstream STL.
    # Their vertices are independently checked by check_body.py; no servo datum changes.
    anchor_asm = [(2.06894, -10.06272), (2.00544, 14.70228),
                  (33.7885, -7.18772), (33.7885, 13.21228)]
    anchors = [(26-a, b) for a, b in anchor_asm]
    deck_anchors = [(x, p["front_riser_post_y_mm"][i] if i<2 else y) for i,(x,y) in enumerate(anchors)]
    frame_top = frame.BoundBox.ZMax
    for i, (x, y) in enumerate(anchors):
        dx,dy = deck_anchors[i]
        radius = p["frame_anchor_radius_mm"]
        sleeve = cylinder(radius, z-frame_top, (dx, dy, frame_top))
        if i<2:
            # Inset the tall columns out of the hip sweep, keeping the exact old
            # attachment bore and a short screw accessible above the base foot.
            sleeve = sleeve.fuse(box([2*radius,abs(y-dy)+2*radius,w], [x-radius,min(y,dy)-radius,frame_top]))
            sleeve = sleeve.cut(cylinder(p["frame_anchor_clearance_diameter_mm"]/2,w+2,(x,y,frame_top-1)))
            sleeve = sleeve.cut(cylinder((p["front_riser_top_screw_diameter_mm"]-.4)/2,9,(dx,dy,z-8)))
        else:
            sleeve = sleeve.cut(cylinder(p["frame_anchor_clearance_diameter_mm"]/2,z-frame_top+2,(x,y,frame_top-1)))
        sleeve = sleeve.removeSplitter()
        part(f"riser-{i+1}", sleeve, [0.85, 0.63, 0.27])
    print("Constructing tray, drawer and cover", flush=True)
    tray = box([X, Y, w], [-X/2, -Y/2, z])
    # Open top tray. Battery exits +X below the carrier; body is outside full leg sweep.
    tray = tray.fuse(box([X, Y, cz-z-w], [-X/2, -Y/2, z+w]).cut(
        box([X-2*w, Y-2*w, cz-z], [-X/2+w, -Y/2+w, z+w])))
    bx, by, bz = p["battery"]["size_mm"]
    pad = p["battery"]["fit_padding_mm"]
    battery_z = z+2*w+gap
    drawer_width = by+2*(pad+w)
    opening_h = bz+2*pad+w+2*gap
    # Open the mouth to the tray rim: no 35mm unsupported bridge over the drawer.
    tray = tray.cut(box([X, drawer_width+2*gap, cz-z-w+1], [0, -drawer_width/2-gap, z+w]))
    # Drawer slides on the base. Two side rails constrain it below the electronics.
    for sy in [-1, 1]:
        yy = sy*(drawer_width/2+gap)
        tray = tray.fuse(box([bx+2*pad, w, w], [-bx/2-pad, yy if sy>0 else yy-w, z+w]))
    for i,(x,y) in enumerate(deck_anchors):
        bore = (p["front_riser_top_screw_diameter_mm"]+.4)/2 if i<2 else p["frame_anchor_clearance_diameter_mm"]/2
        head = 2.6 if i<2 else 1.6
        depth = head-bore  # 90-degree countersunk head; leaves >=1.25 mm floor
        tray = tray.cut(cylinder(bore,w+2,(x,y,z-1)))
        tray = tray.cut(Part.makeCone(bore,head,depth,V(x,y,z+w-depth)))
    carrier_holes = [(x+offset[0], y+offset[1]) for x, y in holes]
    standoff_bottom = z+w
    for x, y in carrier_holes:
        tray = tray.fuse(cylinder(p["carrier_standoff_radius_mm"], cz-standoff_bottom, (x, y, standoff_bottom)))
        tray = tray.cut(cylinder(p["carrier_pilot_diameter_mm"]/2, cz-z+2, (x, y, z-1)))
    # Four cover fasteners live outside the carrier and battery.
    cover_holes = [(sx*(X/2-w-4), sy*(Y/2-w-2)) for sx in [-1, 1] for sy in [-1, 1]]
    for x, y in cover_holes:
        tray = tray.fuse(cylinder(3, cz-z, (x, y, z)))
        tray = tray.cut(cylinder((p["cover_screw_diameter_mm"]-0.4)/2, cz-z+2, (x, y, z-1)))
    # Eight open channels through the tray rim, later swept wires follow their centers.
    wire_routes = {}
    wire_r = p["wires"]["servo_bundle_radius_mm"]
    for side in [-1, 1]:
        for j, xx in enumerate([-21, -7, 7, 21]):
            exit_point = p["wires"]["servo_exit_points_mm"][f"{side}.{j}"]
            points = [(xx, side*8, cz+32), (xx, side*(Y/2+5), cz+32),
                      (xx, side*(Y/2+5), z+8), (xx, side*28, z+8),
                      (xx, side*28, 28), exit_point]
            key = f"wire.servo.{side}.{j}"
            wire_routes[key] = points
            component(key, tube_route(points, wire_r), [0.75, 0.22, 0.12], "wire")
            tray = tray.cut(tube_route(points, wire_r+p["wires"]["routing_clearance_mm"]))
            if p["wires"]["open_entry_channels"]:
                radius = wire_r+p["wires"]["routing_clearance_mm"]
                yy = Y/2-w-1 if side>0 else -Y/2-1
                tray = tray.cut(box([2*radius,w+2,cz-z-8+radius+1], [xx-radius,yy,z+8-radius]))
    part("carrier-tray", tray.removeSplitter(), [0.23, 0.50, 0.62])

    drawer_len = X/2+bx/2+pad+gap
    drawer = box([drawer_len, drawer_width, w], [-bx/2-pad, -drawer_width/2, z+w+gap])
    # Low side fences, with a strap threaded through slots in the drawer floor.
    for sy in [-1, 1]:
        drawer = drawer.fuse(box([bx+2*pad, w, bz/2], [-bx/2-pad, sy*(by/2+pad)+(0 if sy>0 else -w), z+2*w+gap]))
    drawer = drawer.fuse(box([w, drawer_width+6*w, opening_h-gap], [X/2+gap, -drawer_width/2-3*w, z+w+gap]))
    handle_x = X/2+gap+w
    handle_z = z+w+gap
    outline = [V(handle_x,-7.5,handle_z),V(handle_x+w,-7.5,handle_z+w),
               V(handle_x+w,-7.5,z+w+9),V(handle_x,-7.5,z+w+9),V(handle_x,-7.5,handle_z)]
    drawer = drawer.fuse(Part.Face(Part.makePolygon(outline)).extrude(V(0,15,0)))
    for sy in [-1, 1]:
        drawer = drawer.cut(box([p["battery"]["strap_width_mm"], p["battery"]["strap_thickness_mm"]+1, w+2],
                                [-p["battery"]["strap_width_mm"]/2, sy*(by/2+pad/2)-1, z+w-1]))
    # The drawer flange is secured to the front wall, preventing slide-out.
    drawer_screws = []
    for sy in [-1, 1]:
        yy = sy*(drawer_width/2+2*w)
        origin = (X/2-w-1, yy, z+w+opening_h/2)
        drawer = drawer.cut(cylinder(1.2, 3*w+2, origin, (1,0,0)))
        parts["carrier-tray"] = parts["carrier-tray"].cut(cylinder(.85, 3*w+2, origin, (1,0,0)))
        drawer_screws.append(list(origin))
    part("battery-drawer", drawer.removeSplitter(), [0.85, 0.63, 0.27])
    component("battery", box([bx, by, bz], [-bx/2, -by/2, battery_z]), [0.25, 0.25, 0.28], "battery", "published envelope")
    component("service.battery-removal", box([bx+X, by, bz], [-bx/2, -by/2, battery_z]),
              [0.4, 0.5, 0.6], "service", "straight +X pack removal sweep; unplug lead first")
    component("battery.connector", box(p["battery"]["connector_size_mm"], [-bx/2, by/2+4.5, battery_z+1]), [0.8, 0.15, 0.12], "connector")

    cover_bottom = cz+gap
    cover = box([X, Y, top-cover_bottom], [-X/2, -Y/2, cover_bottom]).cut(
        box([X-2*w, Y-2*w, top-cover_bottom-w+1], [-X/2+w, -Y/2+w, cover_bottom-1]))
    for x, y in cover_holes:
        cover = cover.fuse(cylinder(3, top-cover_bottom, (x, y, cover_bottom)))
        cover = cover.cut(cylinder((p["cover_screw_diameter_mm"]+0.4)/2, top-cover_bottom+2, (x, y, cover_bottom-1)))
    # Cable entry scallops also cut the cover. Roof exit then routes outside the legs.
    for pts in wire_routes.values():
        cover = cover.cut(tube_route(pts, wire_r+p["wires"]["routing_clearance_mm"]))
        if p["wires"]["open_entry_channels"]:
            radius = wire_r+p["wires"]["routing_clearance_mm"]
            yy = Y/2-w-1 if pts[1][1]>0 else -Y/2-1
            cover = cover.cut(box([2*radius,w+2,pts[0][2]+radius-cover_bottom+1],
                                  [pts[0][0]-radius,yy,cover_bottom-1]))
    usb = components["electronics."+p["usb"]["native_object"]].BoundBox
    ux, uy, uz = usb.XMax, usb.Center.y, usb.Center.z
    usb_access = box([p["usb"]["service_length_mm"], p["usb"]["plug_width_mm"], p["usb"]["plug_height_mm"]],
                     [ux, uy-p["usb"]["plug_width_mm"]/2, uz-p["usb"]["plug_height_mm"]/2])
    component("service.usb", usb_access, [0.2, 0.75, 0.85], "service")
    cover = cover.cut(box([X, p["usb"]["plug_width_mm"]+2*gap, p["usb"]["plug_height_mm"]+2*gap],
                         [ux, uy-p["usb"]["plug_width_mm"]/2-gap, uz-p["usb"]["plug_height_mm"]/2-gap]))

    sw = p["switch"]
    sy, sz = sw["center_yz_mm"]
    # Shaft along -X; depth 10mm assumed from behind panel, footprint in YZ.
    sw_x = -X/2+w+gap
    component("switch.body", box([sw["body_size_mm"][2], sw["body_size_mm"][0], sw["body_size_mm"][1]],
                                [sw_x, sy-sw["body_size_mm"][0]/2, sz-sw["body_size_mm"][1]/2]), [0.2, 0.2, 0.2], "switch")
    component("switch.shaft", cylinder(sw["thread_diameter_mm"]/2, 10, (sw_x, sy, sz), (-1, 0, 0)), [0.7, 0.7, 0.7], "switch")
    component("switch.nut", cylinder(sw["nut_diameter_mm"]/2, 2, (-X/2-2, sy, sz), (1, 0, 0)).cut(
        cylinder(sw["thread_diameter_mm"]/2, 4, (-X/2-3, sy, sz), (1, 0, 0))), [0.65, 0.65, 0.7], "switch")
    component("service.switch-lever", Part.makeSphere(sw["lever_length_mm"], V(-X/2-10, sy, sz)), [0.8, 0.7, 0.5], "service")
    cover = cover.cut(cylinder(sw["panel_hole_diameter_mm"]/2, w+2, (-X/2-1, sy, sz), (1, 0, 0)))

    oled = p["oled"]
    oy, oz = oled["center_yz_mm"]
    ow, oh, ot = oled["pcb_size_mm"]
    ox = X/2-w-gap-oled["glass_depth_mm"]-ot
    component("oled.pcb", box([ot, ow, oh], [ox, oy-ow/2, oz-oh/2]), [0.10, 0.26, 0.5], "oled", "published PCB XY; other dimensions assumed")
    aw, ah = oled["window_size_mm"]
    component("oled.glass", box([oled["glass_depth_mm"], aw, ah], [ox+ot, oy-aw/2, oz-ah/2]), [0.05, 0.1, 0.13], "oled")
    margin = oled["rear_edge_margin_mm"]
    component("oled.rear-envelope", box([oled["back_clearance_mm"], ow-2*margin, oh-2*margin], [ox-oled["back_clearance_mm"], oy-ow/2+margin, oz-oh/2+margin]), [0.2, 0.3, 0.5], "service")
    cover = cover.cut(box([w+2, aw+2*gap, ah+2*gap], [X/2-w-1, oy-aw/2-gap, oz-ah/2-gap]))
    # Vertical U-channels hold PCB edges; it slides in from the open cover bottom.
    for side in [-1, 1]:
        yy = oy+side*(ow/2+gap)
        rail = box([X/2-ox, w, oh+2*w], [ox-w, yy if side>0 else yy-w, oz-oh/2-w])
        lip = box([w, w+1.5, oh+2*w], [ox-w, yy-1.5 if side>0 else yy-w, oz-oh/2-w])
        cover = cover.fuse(rail).fuse(lip)
    cover = cover.fuse(box([X/2-ox+w, ow+2*(w+gap), w], [ox-w, oy-ow/2-w-gap, oz+oh/2+gap]))
    part("face-cover", cover.removeSplitter(), [0.90, 0.91, 0.86], print_rotation=[1, 0, 0, 180])

    # External peripheral harnesses, explicit approximate swept keep-outs.
    be=p["wires"]["battery_exit_offset_mm"]
    se=p["wires"]["switch_exit_offset_mm"]
    oe=p["wires"]["oled_exit_offset_mm"]
    periph_routes = {
        "wire.battery": [[-bx/2+be[0], by/2+be[1], battery_z+be[2]], [-bx/2+6, 28, battery_z+2.5], [-28, 28, cz+6]],
        "wire.switch": [[sw_x+se[0], sy+se[1], sz+se[2]], [-38, 0, cz+6], [-28, 26, cz+6]],
        "wire.oled": [[ox+oe[0], oy+oe[1], oz+oe[2]], [38, oy, cz+8], [10, 26, cz+8]],
    }
    for name, points in periph_routes.items():
        wire_routes[name] = points
        component(name, tube_route(points, p["wires"]["peripheral_bundle_radius_mm"]), [0.3, 0.5, 0.8], "wire")

    # Nominal servo/horn proxies, explicitly not certified purchased-variant CAD.
    # Hip case vertical; knee case/shaft travels with upper leg, used by ROM checker.
    for front in [True, False]:
        for left in [True, False]:
            leg = ("front" if front else "back") + ("_left" if left else "_right")
            hx, hy = p["servo"]["hip_shaft_xy_mm"][leg]
            length, width, height = p["servo"]["case_size_mm"]
            center_dx = (-1 if front else 1)*p["servo"]["shaft_to_case_center_x_mm"]
            case = box([length, width, height], [hx+center_dx-length/2, hy-width/2, p["servo"]["hip_case_bottom_z_mm"]])
            # Proxy location awaits exact case-to-shaft datum; reports retain conflicts.
            component("servo."+leg+".hip", case, [0.18, 0.2, 0.24], "servo")
            component("horn."+leg+".hip", cylinder(p["servo"]["horn_radius_mm"], p["servo"]["horn_thickness_mm"], (hx, hy, p["servo"]["hip_horn_bottom_z_mm"])), [0.8, 0.8, 0.8], "horn")
            # Moving knee proxy remains in the canonical simulator rest frame.
            hx, hy = (24.5 if front else -24.5), (23 if left else -23)
            ky = hy+(36.9 if left else -36.9)
            component("servo."+leg+".foot", box([width, length, height], [hx-width/2, ky-length+6, -1.8]), [0.18, 0.2, 0.24], "servo")
            component("horn."+leg+".foot", cylinder(p["servo"]["horn_radius_mm"], p["servo"]["horn_thickness_mm"], (hx, ky, -1.8), (1, 0, 0)), [0.8, 0.8, 0.8], "horn")

    # Intended face contacts do not authorize ANY volume penetration.
    contacts = {( "carrier-tray", "electronics.PerfboardReference"),
                ("face-cover", "switch.nut"), ("face-cover", "oled.pcb")}
    return {"params": p, "parts": parts, "part_meta": pm, "components": components,
            "component_meta": cm, "native": native, "native_meta": native_meta,
            "electronics_offset_mm": offset, "carrier_holes_mm": carrier_holes,
            "carrier_hole_diameter_mm": hole_d, "anchors_mm": anchors,
            "deck_anchors_mm": deck_anchors,
            "frame_anchor_asm_mm": anchor_asm, "cover_holes_mm": cover_holes,
            "drawer_screws_mm": drawer_screws, "contacts": contacts,
            "wire_routes": wire_routes, "doc": doc,
            "top_reference_mesh": top_reference,
            "frozen_meshes": {"interface-frame": frame_mesh, "bottom-cover": bottom_mesh}}


def triangulate(shape, deflection=0.1):
    m = MeshPart.meshFromShape(Shape=shape, LinearDeflection=deflection,
                               AngularDeflection=0.3, Relative=False)
    if not m.CountFacets:
        raise ValueError("Empty output mesh")
    return m


def write_stl(path, mesh):
    """Deterministic binary STL, avoiding a tool-specific timestamp/header."""
    with Path(path).open("wb") as f:
        f.write(b"Sesame S3 body; mm; generated by tools/body_cad.py".ljust(80, b"\0"))
        f.write(struct.pack("<I", mesh.CountFacets))
        for facet in mesh.Facets:
            values = list(facet.Normal) + [v for point in facet.Points for v in point]
            f.write(struct.pack("<12fH", *values, 0))


def write_3mf(path, mesh, name):
    ns = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ET.register_namespace("", ns)
    model = ET.Element("{"+ns+"}model", {"unit": "millimeter", "xml:lang": "en-US"})
    resources = ET.SubElement(model, "resources")
    obj = ET.SubElement(resources, "object", {"id": "1", "type": "model", "name": name})
    me = ET.SubElement(obj, "mesh")
    vertices = ET.SubElement(me, "vertices")
    vv, ff = mesh.Topology
    for v in vv:
        ET.SubElement(vertices, "vertex", dict(zip(["x", "y", "z"], [f"{x:.7f}" for x in v])))
    triangles = ET.SubElement(me, "triangles")
    for face in ff:
        ET.SubElement(triangles, "triangle", dict(zip(["v1", "v2", "v3"], map(str, face))))
    ET.SubElement(ET.SubElement(model, "build"), "item", {"objectid": "1"})
    content = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    rel = '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for filename, data in [("[Content_Types].xml", content), ("_rels/.rels", rel), ("3D/3dmodel.model", ET.tostring(model))]:
            info = zipfile.ZipInfo(filename, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)


def export_step(shape, path):
    import re
    shape.exportStep(str(path))
    # OCC embeds wall clock time in FILE_NAME; normalize only this metadata.
    text = Path(path).read_text()
    text = re.sub(r"'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'", "'2026-01-01T00:00:00'", text)
    # The translator also increments a process-global PRODUCT label on each call.
    text = re.sub(r"'Open CASCADE STEP translator [0-9.]+ \d+'", "'Sesame scripted body'", text)
    Path(path).write_text(text)


def export(design, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    scene, part_records = [], []
    vv, ff = design["top_reference_mesh"].Topology
    scene.append({"id": "reference.upstream-top-cover", "kind": "reference", "color": [.55,.58,.6],
                  "vertices": [list(v) for v in vv], "faces": ff})
    for name, shape in design["parts"].items():
        print("Exporting", name, flush=True)
        meta = design["part_meta"][name]
        mesh = design["frozen_meshes"].get(name) or triangulate(shape,design["params"]["checks"]["mesh_deflection_mm"])
        write_stl(out / (name+".stl"), mesh)
        export_step(shape, out / (name+".step"))
        printable = mesh.copy()
        axis_angle = meta["print_rotation_axis_angle"]
        rotation = App.Placement(V(0, 0, 0), App.Rotation(V(*axis_angle[:3]), axis_angle[3])).toMatrix()
        printable.transform(rotation)
        b = printable.BoundBox
        translation = [-b.XMin, -b.YMin, -b.ZMin]
        printable.translate(*translation)
        write_3mf(out / (name+".3mf"), printable, name)
        vv, ff = mesh.Topology
        scene.append({"id": meta["id"], "kind": "body", "color": meta["color"],
                      "vertices": [list(v) for v in vv], "faces": ff})
        part_records.append({**meta, "files": {ext: name+"."+ext for ext in ["step", "stl", "3mf"]},
                             "bounds_mm": bounds(shape), "volume_mm3": shape.Volume,
                             "print_translation_mm": translation, "assembly_transform": "identity"})
    # One native-frame electronics STEP, paired with stable-ID per-leaf metadata.
    print("Exporting native electronics STEP and tessellated scene", flush=True)
    export_step(Part.makeCompound(list(design["native"].values())), out / "electronics-reference.step")
    for name, shape in design["components"].items():
        meta = design["component_meta"][name]
        if not shape.Faces:
            continue
        mesh = triangulate(shape, 0.2)
        vv, ff = mesh.Topology
        scene.append({"id": name, "kind": meta["kind"], "color": meta["color"],
                      "vertices": [list(v) for v in vv], "faces": ff})
    export_step(Part.makeCompound(list(design["parts"].values())+list(design["components"].values())), out / "assembled-preview.step")
    (out / "scene.json.gz").write_bytes(gzip.compress(json.dumps(scene, separators=(",", ":")).encode(), mtime=0))
    record = {
        "schema_version": 1, "status": "DRAFT-NEEDS-HARDWARE; consult report.json",
        "upstream_top_reference": {"closed": design["top_reference_mesh"].isSolid(),
                                   "facets": design["top_reference_mesh"].CountFacets,
                                   "bounds_mm": bounds(design["top_reference_mesh"])},
        "frame": "mm; torso-local x-forward, y-left, z-up; same axes as MuJoCo, multiply by .001 for metres",
        "parts": part_records, "electronics_translation_mm": design["electronics_offset_mm"],
        "electronics_rotation_xyzw": [0, 0, 0, 1], "electronics_reference_step_frame": "original native carrier frame",
        "native_object_bindings": design["native_meta"],
        "carrier_holes_mm": design["carrier_holes_mm"], "frame_anchors_mm": design["anchors_mm"],
        "deck_anchors_mm": design["deck_anchors_mm"],
        "wire_routes_mm": design["wire_routes"],
        "assembly_order": [
            {"id": "body.mount-risers", "parts": ["body.interface-frame", "body.bottom-cover"]+[f"body.riser-{i}" for i in range(1,5)], "action": "Retain upstream frame and bottom. Attach risers at old PCB bores; confirm screw engagement."},
            {"id": "body.mount-tray", "parts": ["body.carrier-tray"], "action": "Fasten inset front riser feet with short M1.6 screws first. Seat tray using front M2.5 and rear long M1.6 countersunk screws, flush below drawer. Verify screw engagement and stiffness."},
            {"id": "body.battery", "parts": ["body.battery-drawer", "battery"], "action": "Thread hook-and-loop strap through floor, retain battery, slide drawer inward along -X, secure two flange screws."},
            {"id": "body.carrier", "parts": ["carrier.display"], "action": "Lower complete circuitry along -Z onto four corner standoffs; fit M1.6 screws after measuring carrier holes."},
            {"id": "body.face-and-switch", "parts": ["body.face-cover", "oled.pcb", "switch.body"], "action": "Slide OLED into U rails from below; retain with removable tape at open rail ends. Mount switch through rear panel with its nut."},
            {"id": "body.route-and-close", "parts": ["body.face-cover"], "action": "Route eight servo bundles through open channels and check slack at all poses; lower cover and fasten four screws. USB enters +X side opening."}
        ],
        "guide_gate": "Keep C hidden until report.release_ready is true AND instructor confirms physical assembly. Current draft is not a print-approved build step.",
        "source_hashes": {"assembly": digest(ASSEMBLY), "snapshot": digest(SNAPSHOT), **{p.name: digest(p) for p in sorted(UPSTREAM.glob('*.stl'))}},
        "export_hashes": {p.name: digest(p) for p in sorted(out.iterdir()) if p.suffix in (".step", ".stl", ".3mf")},
    }
    write_json(out / "assembly.json", record)
    return record
