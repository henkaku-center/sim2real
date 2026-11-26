"""Derive the shell geometry from the robot model and build it with FreeCAD.

    uv run python -I bambu/scripts/design.py            # writes bambu/build/job.json + bambu/stl/*
    uv run python -I bambu/scripts/design.py --params bambu/params-s3wide.json   # S3 body -> */s3-wide/

The dome is a spherical shell whose centre sits `center_above_com` mm above the
centre of mass of the *tucked* robot (shell and mount included), so the
distance from the CoM to the hull grows monotonically from the belly to the
apex: no resting state except belly-down.  The CoM depends on the shell's own
mass, so geometry and mass are iterated to a fixed point.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import subprocess
import sys

import numpy as np
import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from sesame_model import BAMBU, ROOT, SesameModel, load_params  # noqa: E402

FREECAD_PY = os.environ.get("FREECAD_PYTHON", "/Applications/FreeCAD.app/Contents/Resources/bin/python")
SHELL_DENSITY_G_CM3 = 1.20  # thin walls print as solid perimeters

def offset_half_profile(points, gap):
    """Offset an open (y, z) half profile (bottom -> top centre) outward along its vertex normals."""
    pts = np.asarray(points, float)
    seg = np.diff(pts, axis=0)
    seg_n = np.c_[seg[:, 1], -seg[:, 0]]  # walking up/inward, outward is to the right
    seg_n /= np.linalg.norm(seg_n, axis=1)[:, None]
    normals = np.vstack([seg_n[:1], seg_n[:-1] + seg_n[1:], seg_n[-1:]])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    out = pts + gap * normals
    out[-1, 0] = 0.0
    return [tuple(p) for p in out]


def leg_sweep(model: SesameModel, pose: dict, leg: str, clearance: float):
    """Knee point/axis in `pose` and the cylinder that bounds the lower leg's full knee sweep."""
    tf = model.transforms(pose)
    l = model.legs[leg]
    th = tf[("femur", leg)]
    knee = trimesh.transform_points([l.knee_point], th)[0]
    axis = th[:3, :3] @ l.knee_axis
    verts = np.vstack([mesh.vertices for p, _, mesh in model.posed(pose)
                       if p.group == "foot" and p.leg == leg and mesh is not None])
    rel = verts - knee
    ax = rel @ axis
    radial = np.linalg.norm(rel - np.outer(ax, axis), axis=1)
    return {"knee": knee.tolist(), "axis": axis.tolist(), "radius": float(radial.max() + clearance),
            "axial_lo": float(ax.min() - clearance), "axial_hi": float(ax.max() + clearance)}


def in_slot(p, slots, pad, roof_deg=None):
    """Inside a knee slot (cylinder, plus its pointed roof when roof_deg is set) grown by pad."""
    for s in slots:
        axis = np.asarray(s["axis"])
        rel = np.asarray(p) - s["knee"]
        a = rel @ axis
        radial = rel - a * axis
        if not s["axial_lo"] - pad <= a <= s["axial_hi"] + pad:
            continue
        if np.linalg.norm(radial) <= s["radius"] + pad:
            return True
        if roof_deg:  # teardrop roof: tangent lines at roof_deg from the vertical meet above the cylinder
            up = np.array([0.0, 0.0, 1.0]) - axis * axis[2]
            up /= np.linalg.norm(up)
            v, w = radial @ up, np.linalg.norm(radial - (radial @ up) * up)
            phi = math.radians(roof_deg)
            if v >= 0 and w * math.sin(phi) + v * math.cos(phi) <= s["radius"] + pad:
                return True
    return False


def perforation(center, com, R, t, rim_z, slots, pp, delta, roof_deg=None):
    """Graded rhombic holes.  A hole bridged by the floor is a flat facet; it must not hold the
    body, so the facet's half-length along the meridian stays below the CoM offset e*sin(theta)."""
    axis = center - com
    e = np.linalg.norm(axis)
    axis = axis / e
    tilt = math.atan(delta / e)  # an off-axis CoM moves the unstable apex by this angle
    ref = np.array([1.0, 0.0, 0.0]) - axis[0] * axis
    ref /= np.linalg.norm(ref)
    side = np.cross(axis, ref)
    web, margin = pp["min_web"], pp["facet_margin"]

    def half(theta):
        return min(pp["max_half"], e * math.sin(max(theta - tilt, 0.0)) - margin)

    holes, rings = [], []
    theta = math.radians(pp["solid_cap_deg"])
    while half(theta) < pp["min_half"]:
        theta += 0.005
    prev, n_prev, a_prev, theta_prev, phase = [], None, None, None, 0.0
    root2 = math.sqrt(2)
    while True:
        if n_prev is not None:
            # nested row: same count, half-pitch stagger, row pitch = mean half-diagonal + web/sqrt(2)
            th = theta_prev + (a_prev + web / root2 + 0.25) / R
            for _ in range(3):
                circ = 2 * math.pi * R * math.sin(th)
                a = min(half(th), (circ / n_prev - web * root2) / 2)
                th = theta_prev + ((a_prev + a) / 2 + web / root2 + 0.25) / R
            if a >= pp["regrid_ratio"] * half(th):
                theta, n, phase = th, n_prev, phase + 0.5
            else:  # holes may grow: start a new, unstaggered row with a larger pitch
                th = theta_prev + (2 * a_prev + web) / R
                a = half(th + a_prev / R)
                theta = theta_prev + (a_prev + a + web) / R
                a = half(theta)
                n = int(2 * math.pi * R * math.sin(theta) // (2 * a + web * root2))
                phase = 0.0
        else:
            n = int(2 * math.pi * R * math.sin(theta) // (2 * half(theta) + web * root2))
        circ = 2 * math.pi * R * math.sin(theta)
        a = min(half(theta), (circ / n - web * root2) / 2)
        if theta >= math.pi or center[2] + R * math.cos(theta + a / R) < rim_z + pp["solid_rim_band"]:
            break
        ring = []
        for j in range(n):
            phi = 2 * math.pi * (j + phase) / n
            d = math.cos(theta) * axis + math.sin(theta) * (math.cos(phi) * ref + math.sin(phi) * side)
            up = axis - np.dot(axis, d) * d
            up /= np.linalg.norm(up)
            east = np.cross(up, d)
            p = center + R * d
            corners = [p + up * a, p - up * a, p + east * a, p - east * a, p]
            if any(in_slot(c, slots, web, roof_deg) for c in corners):
                continue
            # 45-degree diamonds keep a web >= `web` iff their L1 centre distance >= a1 + a2 + web*sqrt(2)
            if any(abs(np.dot(q["p"] - p, up)) + abs(np.dot(q["p"] - p, east))
                   < a + q["half_meridian"] + web * root2 - 1e-6 for q in prev):
                continue
            ring.append({"dir": d.tolist(), "up": up.tolist(), "half_meridian": a, "half_azimuth": a,
                         "theta_deg": math.degrees(theta), "phi_deg": math.degrees(phi), "p": p})
        holes += ring
        rings.append({"theta_deg": round(math.degrees(theta), 2), "half": round(a, 2), "count": len(ring), "n": n})
        prev, n_prev, a_prev, theta_prev = ring, n, a, theta
    for h in holes:
        h.pop("p")
    return holes, rings, tilt


def spiral_cells(center, com, R, t, rim_z, slots, pp, delta, roof_deg=None):
    """Equal-pitch rhombic cells on one spherical spiral, matched to an addressable LED tape.

    The tape lies on the inner surface (radius R_tape); consecutive LEDs, and consecutive spiral
    turns, are `pitch` apart measured there, so every cell sits over one LED.  All cells share one
    size; the spiral starts where the flat-facet rule (half <= e*sin(theta - tilt) - margin) allows
    that size and ends above the knee slots and rim lugs, so the tape never crosses an opening.
    """
    axis = center - com
    e = np.linalg.norm(axis)
    axis = axis / e
    tilt = math.atan(delta / e)
    ref = np.array([1.0, 0.0, 0.0]) - axis[0] * axis
    ref /= np.linalg.norm(ref)
    side = np.cross(axis, ref)
    web, margin, pitch = pp["min_web"], pp["facet_margin"], pp["pitch"]
    tape = pp["led_tape"]
    r_tape = R - t - tape["inner_offset"]
    row = pp.get("row_spacing", pitch)  # distance between spiral turns (measured at the tape radius)
    half = pp.get("half") or (pitch * R / r_tape - web * math.sqrt(2)) / 2
    half_m = pp.get("half_meridian") or max(half, (row * R / r_tape - web * math.sqrt(2)) / 2 if row > pitch else half)
    theta0 = tilt + math.asin(min(1.0, (half_m + margin) / e))
    z_end = max(rim_z + pp["end_above_rim"], max(sl["knee"][2] + sl["radius"] for sl in slots) + web) if slots \
        else rim_z + pp["end_above_rim"]
    theta_end = math.acos(max(-1.0, min(1.0, (z_end - center[2]) / R))) - half_m / R
    k = row / r_tape / (2 * math.pi)  # d(theta)/d(phi): one row spacing per turn
    phi, theta, s_acc, length = math.radians(pp.get("start_azimuth_deg", 180.0)), theta0, pitch, 0.0
    dphi = 0.002
    holes, turns0 = [], phi
    # passive cells (no LED) may continue the same spiral below the tape, down to the rim band
    theta_last = theta_end
    if pp.get("passive_below"):
        theta_last = math.acos(max(-1.0, min(1.0, (rim_z + pp["solid_rim_band"] - center[2]) / R))) - half_m / R
    tape_end_index = None
    while theta <= theta_last:
        if theta > theta_end and tape_end_index is None:
            tape_end_index = len(holes)
            tape_length = length
        if s_acc >= pitch - 1e-9:
            d = math.cos(theta) * axis + math.sin(theta) * (math.cos(phi) * ref + math.sin(phi) * side)
            up = axis - np.dot(axis, d) * d
            up /= np.linalg.norm(up)
            east = np.cross(up, d)
            p = center + R * d
            corners = [p + up * half_m, p - up * half_m, p + east * half, p - east * half, p]
            hit = any(in_slot(c, slots, web, roof_deg) for c in corners)
            if theta > theta_end and hit:  # passive cell over a knee slot: leave it out
                s_acc -= pitch
            else:
                holes.append({"dir": d.tolist(), "up": up.tolist(), "half_meridian": half_m, "half_azimuth": half,
                              "theta_deg": math.degrees(theta), "phi_deg": math.degrees(phi) % 360,
                              "in_slot": hit, "led": theta <= theta_end})
                s_acc -= pitch
        ds = r_tape * math.sqrt(k ** 2 + math.sin(theta) ** 2) * dphi
        phi += dphi
        theta += k * dphi
        s_acc += ds
        length += ds
    if any(h["in_slot"] and h["led"] for h in holes):
        raise SystemExit("LED cells reach a knee slot: raise perforation.end_above_rim")
    if tape_end_index is None:
        tape_length = length
    leds = [h for h in holes if h["led"]]
    for h in holes:
        h.pop("in_slot")
    length = tape_length
    pos = np.array([center + r_tape * np.array(h["dir"]) for h in leds])
    info = {"layout": "spiral", "pitch_mm": pitch, "row_spacing_mm": row, "half_mm": round(half, 2),
            "half_meridian_mm": round(half_m, 2), "cells": len(leds),
            "passive_cells": len(holes) - len(leds),
            "theta_deg": [round(math.degrees(theta0), 2), round(math.degrees(theta_end), 2)],
            "turns": round((phi - turns0) / (2 * math.pi), 2), "tape_length_mm": round(length, 1),
            "tape_radius_mm": round(r_tape, 2), "z_end_mm": round(z_end, 2),
            "min_edgewise_bend_radius_mm": round(r_tape * math.tan(theta0), 1),
            "tape_mass_g": round(length / 1000 * tape["mass_g_per_m"], 1),
            "tape_centroid_mm": pos.mean(axis=0).round(3).tolist()}
    return holes, [info], tilt


def make_job(model: SesameModel, com: np.ndarray, params: dict, out_dir=None):
    sp, mp = params["shell"], params.get("mount", {})
    R, t, e = sp["sphere_radius"], sp["thickness"], sp["center_above_com"]
    center = com + np.array([0.0, 0.0, e])
    slots = [leg_sweep(model, params["poses"]["tuck"], leg, sp["knee_slot_clearance"]) for leg in model.legs]
    layout = spiral_cells if sp["perforation"].get("layout") == "spiral" else perforation
    holes, rings, tilt = layout(center, com, R, t, sp["rim_z"], slots,
                                sp["perforation"], params["acceptance"]["com_perturbation_mm"],
                                sp.get("slot_roof_slope_deg"))
    pin_ring = next(h for h in holes if abs(h["theta_deg"] - holes[0]["theta_deg"]) < 1e-6)
    pin_dir = np.array(pin_ring["dir"]) * [1, 1, 0]
    pin_dir /= np.linalg.norm(pin_dir)
    pin_z = float(center[2] + R * math.cos(math.radians(pin_ring["theta_deg"])))
    so = sp.get("socket", {"fit": 0.2, "wall": 2.0, "roof": 1.0, "below_pin": 9.0, "pin_d": 2.0})
    bore_top = center[2] + R - t - so["roof"]
    mast_d = mp.get("mast_outer_d", 12.0)
    socket = {"outer_r": mast_d / 2 + so["fit"] + so["wall"], "inner_r": mast_d / 2 + so["fit"],
              "bottom_z": pin_z - so["below_pin"], "roof": so["roof"], "pin_dir": pin_dir.tolist(),
              "pin_z": pin_z, "pin_r": so["pin_d"] / 2}

    dome = {"center": center.tolist(), "radius": R, "thickness": t, "rim_z": sp["rim_z"],
            "holes": holes, "slots": slots, "socket": socket,
            "hole_skin": sp.get("hole_skin"), "hole_skin_side": sp.get("hole_skin_side", "outer")}
    if sp["variant"] == "v3-crown":
        dome.update({"cap_slope_deg": sp["cap_slope_deg"], "tip_radius": sp["tip_radius"],
                     "slot_roof_slope_deg": sp.get("slot_roof_slope_deg")})
        crown = v3_crown_job(model, params, center, R, t)
        dome["holes"] = [h for h in holes if not _hole_blocked(h, center, R, crown)]
        dome["windows"] = crown["dome_windows"]
        return {"out_dir": str(out_dir or BAMBU / "stl"), "com_tuck": com.tolist(), "variant": sp["variant"],
                "dome": dome, "crown": crown, "rings": rings, "apex_tilt_allowance_deg": math.degrees(tilt)}
    if sp["variant"] == "v3-headarms":
        dome.update({"cap_slope_deg": sp["cap_slope_deg"], "tip_radius": sp["tip_radius"],
                     "slot_roof_slope_deg": sp.get("slot_roof_slope_deg")})
        arms = v3_headarms_job(params, center, R, t)
        dome["lugs"] = arms["dome_lugs"]
        dome["print_ties"] = sp.get("print_ties")
        dome["rim_band"] = sp.get("rim_band")
        return {"out_dir": str(out_dir or BAMBU / "stl"), "com_tuck": com.tolist(), "variant": sp["variant"],
                "dome": dome, "head_arms": arms, "rings": rings, "apex_tilt_allowance_deg": math.degrees(tilt)}
    if sp["variant"] == "v3-mushroom":
        dome.update({"cap_slope_deg": sp["cap_slope_deg"], "tip_radius": sp["tip_radius"],
                     "slot_roof_slope_deg": sp.get("slot_roof_slope_deg")})
        stem = v3_stem_job(params, center, R, t)
        dome["apex"] = stem["apex"]
        return {"out_dir": str(out_dir or BAMBU / "stl"), "com_tuck": com.tolist(), "variant": sp["variant"],
                "dome": dome, "stem": stem, "rings": rings, "apex_tilt_allowance_deg": math.degrees(tilt)}
    if sp["variant"] == "v3-brackets":
        dome["lugs"], brackets = v3_bracket_job(model, params, center, R, t, sp["rim_z"])
        return {"out_dir": str(out_dir or BAMBU / "stl"), "com_tuck": com.tolist(), "variant": sp["variant"],
                "dome": dome, "brackets": brackets, "rings": rings, "apex_tilt_allowance_deg": math.degrees(tilt)}
    if sp["variant"] == "s3-cover":
        cover, mount = s3_cover_job(model, params, center, bore_top, pin_dir, pin_z)
        return {"out_dir": str(out_dir or BAMBU / "stl"), "com_tuck": com.tolist(), "variant": sp["variant"],
                "dome": {"center": center.tolist(), "radius": R, "thickness": t, "rim_z": sp["rim_z"],
                         "holes": holes, "slots": slots, "socket": socket},
                "cover": cover, "mount": mount, "rings": rings, "apex_tilt_allowance_deg": math.degrees(tilt)}

    tc = mp["top_cover"]
    profile = [tuple(p) for p in tc["profile_yz"]]
    g = mp["top_cover_fit_gap"]
    w = mp["wall"]
    inner = offset_half_profile(profile, g)[:-1]
    top_in = profile[-1][1] + g
    inner_profile = [(-inner[0][0], 40.0)] + [(-y, z) for y, z in inner] + [(-inner[-1][0], top_in), (inner[-1][0], top_in)] \
        + [(y, z) for y, z in reversed(inner)] + [(inner[0][0], 40.0)]
    y_skirt = np.interp(mp["skirt_bottom_z"], [z for _, z in profile[:-1]], [y for y, _ in profile[:-1]]) + g + w
    plate_top = top_in + mp["plate"]
    ch = 2.0
    outer_profile = [(-y_skirt, mp["skirt_bottom_z"]), (-y_skirt, plate_top - ch), (-y_skirt + ch, plate_top),
                     (y_skirt - ch, plate_top), (y_skirt, plate_top - ch), (y_skirt, mp["skirt_bottom_z"])]
    x0, x1 = tc["flat_x"][0] + tc["rear_inset"], tc["flat_x"][1] - tc["front_inset"]
    vs = mp["vertical_screws"]
    vertical = [[center[0] + vs["radius"] * math.cos(math.radians(a)), center[1] + vs["radius"] * math.sin(math.radians(a))]
                for a in vs["angles_deg"]]
    mount = {"x_range": [x0, x1], "outer_profile": outer_profile, "inner_profile": inner_profile,
             "screws": [[x, mp["screw_z"]] for x in mp["screw_x"]], "screw_r": mp["screw_clear_d"] / 2,
             "vertical_screws": vertical, "pilot_r": vs["pilot_d"] / 2, "pilot_depth": vs["depth"],
             "guide_hole_r": vs["guide_hole_d"] / 2, "cavity_top_z": top_in,
             "mast_xy": center[:2].tolist(), "plate_top_z": plate_top, "mast_top_z": bore_top - 0.5,
             "mast_outer_r": mp["mast_outer_d"] / 2, "mast_inner_r": mp["mast_inner_d"] / 2, "mast_floor": 1.0,
             "gusset_r": mp["gusset_r"], "gusset_h": mp["gusset_h"],
             "ceiling_fillet_r": mp["ceiling_fillet"]["r"], "ceiling_fillet_h": mp["ceiling_fillet"]["h"],
             "pin_dir": pin_dir.tolist(), "pin_z": pin_z, "pin_r": so["pin_d"] / 2}
    job = {"out_dir": str(out_dir or BAMBU / "stl"), "com_tuck": com.tolist(), "variant": sp["variant"],
           "dome": {"center": center.tolist(), "radius": R, "thickness": t, "rim_z": sp["rim_z"],
                    "holes": holes, "slots": slots, "socket": socket},
           "mount": mount, "rings": rings, "apex_tilt_allowance_deg": math.degrees(tilt)}
    return job


_ENVELOPE_CACHE = {}


def _polar(center, phi_deg, theta, r):
    """Point at polar angle theta (rad, from +Z) and azimuth phi on a sphere of radius r about center."""
    ph = math.radians(phi_deg)
    return (np.asarray(center, float) + r * np.array([math.sin(theta) * math.cos(ph), math.sin(theta) * math.sin(ph),
                                                      math.cos(theta)])).tolist()


def _hole_blocked(h, center, R, crown):
    """Holes must leave a solid ring where the crown seats and solid surrounds at the snap windows."""
    th = math.radians(h["theta_deg"])
    a = h["half_meridian"] / R
    if abs(th - crown["seat_theta"]) < a + math.radians(crown["seat_band_deg"]):
        return True
    d = np.asarray(h["dir"])
    for w in crown["dome_windows"]:
        ang = math.acos(np.clip(np.dot(d, w["dir"]), -1, 1))
        if ang * R < h["half_meridian"] * 1.42 + max(w["half_meridian"], w["half_azimuth"]) + crown["window_web"]:
            return True
    return False


def v3_crown_job(model, params, center, R, t):
    """Screw-free mount for the V3 body: the kit's sliding head lid (rail profile unchanged) carries a
    45-degree crown that seats on a solid ring inside the dome; two snap fingers on the crown click into
    windows of the dome (squeeze through the windows to release); a separate stopper key dropped
    through the lid's rear stops it sliding out of the head-cover rail (pull the key to release).
    Every part prints without supports: lid+crown upright, dome rim-down, key flat."""
    cp, body = params["crown"], params["body"]
    src = ROOT / body["frame_dir"]
    lid_top = float(cp["lid_top_z"]) + body["frame_to_robot_z"]
    rin = R - t
    slope = math.radians(cp["slope_deg"])
    cx, cy, cz = center

    def r_cone(z):  # outer surface of the crown
        return cp["base_r"] + (z - lid_top) / math.tan(slope)

    lo, hi = lid_top, cz + rin  # bisection: crown outer cone meets the inner sphere
    for _ in range(80):
        z = (lo + hi) / 2
        lo, hi = (z, hi) if r_cone(z) ** 2 + (z - cz) ** 2 < rin ** 2 else (lo, z)
    z_seat = (lo + hi) / 2
    seat_theta = math.acos((z_seat - cz) / rin)
    f = cp["fingers"]
    th_w = seat_theta - math.radians(f["window_offset_deg"])
    z_w = cz + rin * math.cos(th_w)

    def h_at(r, z):  # horizontal radius of the sphere r (about the dome centre) at height z
        return math.sqrt(max(r * r - (z - cz) ** 2, 0.0))

    windows, fingers = [], []
    rho = rin - f["gap"] - f["thick"] / 2
    z_wl = z_w - f["window_h"] / 2  # horizontal window sill: the barb's flat underside locks on it
    z_b = z_wl + f["lock_play"]
    bh = f["barb_tip_h"]
    h_tip0, h_tip1 = h_at(R, z_b) - 0.3, h_at(R, z_b + bh) - 0.3  # never proud of the outer surface
    h_face = h_at(rin - f["gap"], z_b + bh)  # finger outer face
    z_r = z_b + bh + (h_tip1 - h_face) + 0.6  # 45-degree ramp back into the finger
    barb = [(h_face - 0.8, z_b), (h_tip0, z_b), (h_tip1, z_b + bh), (h_face - 0.8, z_r)]
    th_tip = math.acos((z_r + f["tip_extend"] - cz) / rho)
    z_wu = z_r + 0.6  # window side height; a 45-degree gable closes it (self-supporting)
    for phi in f["phi_deg"]:
        d = np.array(_polar([0, 0, 0], phi, th_w, 1.0))
        windows.append({"dir": d.tolist(), "phi_deg": phi, "z_lo": z_wl, "z_hi": z_wu, "half_w": f["window_width"] / 2,
                        "h_in": h_at(rin, z_wu + f["window_width"]) - 2.0, "h_out": h_at(R, z_wl) + 2.0,
                        "half_meridian": (z_wu - z_wl + f["window_width"] / 2) / 2, "half_azimuth": f["window_width"] / 2})
        fingers.append({"phi_deg": phi, "rho": rho, "theta_root": seat_theta + math.radians(f["root_extend_deg"]),
                        "theta_tip": th_tip, "thick": f["thick"], "width": f["width"],
                        "barb_hz": barb, "barb_width": f["barb_width"]})
    return {"lid_step": str(src / cp["lid_step"]), "lid_dz": body["frame_to_robot_z"], "lid_top_z": lid_top,
            "axis_xy": [cx, cy], "base_r": cp["base_r"], "slope_deg": cp["slope_deg"], "wall": cp["wall"],
            "wall_top": cp.get("wall_top"), "wall_top_band": cp.get("wall_top_band"),
            "seat_z": z_seat, "seat_r": r_cone(z_seat), "seat_theta": seat_theta, "seat_band_deg": cp["seat_band_deg"],
            "seat_gap": cp["seat_gap"], "dome_center": list(center), "dome_inner_r": rin,
            "windows": cp["windows"], "fingers": fingers, "dome_windows": windows, "window_web": f["window_web"],
            "slot_roof_slope_deg": params["shell"].get("slot_roof_slope_deg"),
            "key": cp["key"], "bayonet": cp["bayonet"], "print_brace": cp.get("print_brace")}


def v3_headarms_job(params, center, R, t):
    """Twist-lock mount for the V3 body: two arms grown from the sides of the head cover (screwed to the frame
    at its four corners) run out through the leg-free side corridor to just inside the dome rim.  Each arm tip
    is a C-channel open sideways (seat below, ledge above, stop wall at one end, detent bump near the open
    end); a block lug on the dome's inner rim (printed on the bed) slides into it when the dome is turned by
    twist_deg.  The dome prints rim-down without supports; the head prints rim-down with supports."""
    sp, ha, body = params["shell"], params["head_arms"], params["body"]
    cx, cy, cz = center
    rim = sp["rim_z"]
    tip, lug, det = ha["tip"], ha["lug"], ha["detent"]
    t_rim = max(t, sp["rim_band"]["t"]) if sp.get("rim_band") else t
    r_in_rim = math.sqrt((R - t_rim) ** 2 - (rim - cz) ** 2)
    z_seat = rim - tip["z_seat_gap"]
    z_ledge = rim + lug["h"] + lug["gap_ledge"]
    if z_ledge >= tip["z_top"] - 2.0 or tip["y_out"] > r_in_rim - 0.5:
        raise SystemExit("head arms: ledge too thin or seat outside the dome rim")
    sides, lugs = [], []
    for s in (1, -1):
        d = -s * ha["twist_sense"]  # +x travel direction of this side's lug while turning to lock
        x_open, x_stop = cx - d * tip["half_len"], cx + d * tip["half_len"]
        lx = sorted([x_open + d * lug["open_margin"], x_stop - d * lug["gap_stop"]])
        y_in = tip["y_face"] + lug["gap_face"]
        lugs.append({"x": lx, "y": sorted([s * y_in, s * (R + 2)]), "z": [rim, rim + lug["h"]], "pilots": [],
                     "pilot_r": 0.0, "pilot_depth": 0.0})
        sides.append({"s": s, "d": d, "x_open": x_open, "x_stop": x_stop,
                      "detent_x": x_open + d * det["from_open"], "lug_x": lx})
    travel = 2 * tip["half_len"] + 0.5 - lug["gap_stop"]  # lug's far end must clear the open end when lowered
    if math.radians(ha["twist_deg"]) * tip["y_face"] < travel:
        raise SystemExit(f"head arms: twist {ha['twist_deg']} deg too small for {travel:.1f} mm of travel")
    return {"head_step": str(ROOT / body["frame_dir"] / ha["head_step"]), "head_dz": body["frame_to_robot_z"],
            "x0": cx, "center": list(center), "rim_z": rim, "r_in_rim": r_in_rim, "z_seat": z_seat, "z_ledge": z_ledge,
            "root": ha["root"], "web": ha["web"], "tip": tip, "detent": det, "sides": sides,
            "twist_deg": ha["twist_deg"], "twist_sense": ha["twist_sense"], "dome_lugs": lugs}


def v3_stem_job(params, center, R, t):
    """Mushroom mount for the V3 body: one printed part = the kit's sliding head lid (rail profile unchanged)
    with a stem standing on it.  Ribs under the dome's 30-degree inner cap carry it; two spring prongs inside
    the stem's top pass through a hole in the apex, and their knob (the dome's own tip shape, split by the
    slot) snaps onto the flat left by cutting the tip off.  A fin on one rib rises through a keyway and sets
    the rotation (knee slots).  The dome prints rim-down, the stem-lid upright on the lid, the key flat."""
    sp, st, body = params["shell"], params["stem"], params["body"]
    src = ROOT / body["frame_dir"]
    cap = math.radians(sp["cap_slope_deg"])
    cx, cy, cz = center
    a_out, a_in = cz + R / math.cos(cap), cz + (R - t) / math.cos(cap)  # sharp apex of the outer / inner cone
    tip_cone_r = sp["tip_radius"] * math.sin(cap)  # radius where the round tip meets the cone
    r_hole = st["prong_r"] + st["hole_clear"]
    r_knob = r_hole + st["knob_overlap"]
    if r_knob <= tip_cone_r or st["prong_half_x"] >= st["prong_r"]:
        raise SystemExit("stem: knob must sit on the cone part of the tip; prong flats must cut the prongs")
    z_cut = a_out - r_knob * math.tan(cap)  # outer cone radius there is r_knob
    wall = z_cut - (a_in - r_hole * math.tan(cap))  # dome material under the flat at the hole's edge
    if wall < st["min_wall_at_hole"]:
        raise SystemExit(f"stem: only {wall:.2f} mm of dome wall under the knob")
    z_prong0 = z_cut - st["prong_len"]

    def under_dome(r):  # top of the stem's ribs / housing at radius r: the dome's inner cone minus the gap
        return a_in - r * math.tan(cap) - st["gap"]

    if under_dome(st["ribs"]["r_out"]) < z_prong0 + 5.0:
        raise SystemExit("stem: ribs reach below the prong roots")
    flat_x = st["prong_half_x"] + st["flat_clear"]
    fin = dict(st["fin"])
    return {"lid_step": str(src / st["lid_step"]), "lid_dz": body["frame_to_robot_z"],
            "lid_top_z": float(st["lid_top_z"]) + body["frame_to_robot_z"], "axis_xy": [cx, cy],
            "dome_center": list(center), "dome_radius": R, "cap_slope_deg": sp["cap_slope_deg"],
            "tip_radius": sp["tip_radius"], "apex_in_z": a_in, "apex_out_z": a_out,
            "gap": st["gap"], "root_r": st["root_r"], "tube_r": st["tube_r"], "tube_bore_r": st["tube_bore_r"],
            "housing_r": st["housing_r"], "housing_bore_r": st["housing_bore_r"], "housing_top_z": under_dome(st["housing_r"]),
            "prong_r": st["prong_r"], "prong_z0": z_prong0, "slot": st["slot"], "prong_half_x": st["prong_half_x"],
            "knob_r": r_knob, "knob_gap": st["knob_gap"], "cut_z": z_cut, "wall_at_hole": wall,
            "ribs": st["ribs"], "rib_top_at_r_out": under_dome(st["ribs"]["r_out"]), "fin": fin,
            "lighten": st.get("lighten"), "key": st["key"],
            "apex": {"axis_xy": [cx, cy], "cut_z": z_cut, "knob_r": r_knob + st["hole_clear"], "hole_r": r_hole,
                     "flat_x": flat_x, "fin_phi_deg": fin["phi_deg"], "fin_half_w": fin["width"] / 2 + fin["clear"],
                     "fin_r": [fin["r"][0] - fin["clear"], fin["r"][1] + fin["clear"]]}}


def v3_bracket_job(model, params, center, R, t, rim_z):
    """Mast-free mount for the V3 body: per side, a bracket clamped on the two inner hip-servo ears
    (between the front and rear hip servos) runs out under a lug moulded inside the dome rim; two
    screws go upward through counterbores in the bracket tab into the lug.  Only the foot spans the
    ears; the stem and tab stay narrow because the knee servos swing inward when a hip goes negative
    (walk uses -10 deg).  The bracket bottom is flat (prints on its underside without supports)."""
    bp = params["mount"]["bracket"]
    s3 = model.s3
    z_ear = s3["deck_top_z"] + bp["ear_top_above_deck"]
    lugs, brackets = [], []
    for side, front, back in ((1, "front_left", "back_left"), (-1, "front_right", "back_right")):
        mounts = s3["servo_mounts"]
        ears = [min(mounts[front]["holes"], key=lambda h: abs(h[0])), min(mounts[back]["holes"], key=lambda h: abs(h[0]))]
        hole_y = abs(ears[0][1])
        xs = [h[0] for h in ears]
        xc = (min(xs) + max(xs)) / 2
        y_w = side * center[1] + math.sqrt((R - t) ** 2 - (center[2] - rim_z) ** 2 - (xc - center[0]) ** 2)
        y_t1 = y_w - bp["tab_wall_gap"]
        y_t0 = y_t1 - bp["tab_len"]
        y0, y1 = hole_y - bp["foot_half_y"], hole_y + bp["foot_half_y"]
        z_f = z_ear + bp["foot_thick"]
        c = bp["tab_chamfer"]
        profile = [(y0, z_ear), (y_t1 - c, z_ear), (y_t1, z_ear + c), (y_t1, rim_z), (y_t0 - bp["stem_rise_len"], rim_z),
                   (y1, z_f), (y0, z_f)]
        y_s = y_w - bp["lug_depth"] + 5.0
        screws = [[xc - bp["lug_screw_dx"], side * y_s], [xc + bp["lug_screw_dx"], side * y_s]]
        brackets.append({"name": "dome-bracket-" + ("left" if side > 0 else "right"), "side": side,
                         "profile_yz": [[side * y, z] for y, z in profile],
                         "foot": {"x": [min(xs) - bp["foot_pad"], max(xs) + bp["foot_pad"]],
                                  "y": sorted([side * y0, side * y1]), "z": [z_ear, z_f]},
                         "stem_x": [xc - bp["stem_half_x"], xc + bp["stem_half_x"]],
                         "tab_x": [xc - bp["tab_half_x"], xc + bp["tab_half_x"]], "tab_from_abs_y": y_t0 - 1.0,
                         "ear_holes": [[x, side * hole_y] for x in xs], "ear_hole_r": bp["ear_screw_clear_d"] / 2,
                         "ear_z": [z_ear, z_f], "tab_holes": screws, "tab_hole_r": bp["tab_screw_clear_d"] / 2,
                         "tab_z": [z_ear, rim_z], "counterbore_r": bp["counterbore_d"] / 2,
                         "counterbore_top_z": rim_z - bp["screw_seat_thick"]})
        lugs.append({"x": [xc - bp["lug_half_x"], xc + bp["lug_half_x"]],
                     "y": sorted([side * (y_w - bp["lug_depth"]), side * (y_w + 3.0)]), "z": [rim_z, rim_z + bp["lug_height"]],
                     "pilots": screws, "pilot_r": bp["lug_pilot_d"] / 2, "pilot_depth": bp["lug_pilot_depth"]})
    return lugs, brackets


def leg_envelope_near_body(model, params, half_xy, pad):
    """Z band and inner |y| of every leg surface within the body footprint (+pad) over the walking ROM
    and the tuck sweep (surface samples, fixed seed).  Independent of the shell, so cached per input."""
    key = json.dumps([params["walking_rom"], params["poses"]["tuck"], params["body"], list(half_xy), pad], sort_keys=True)
    if key not in _ENVELOPE_CACHE:
        _ENVELOPE_CACHE[key] = _leg_envelope(model, params, half_xy, pad)
    return _ENVELOPE_CACHE[key]


def _leg_envelope(model, params, half_xy, pad):
    w = params["walking_rom"]
    poses = [(h, k) for h in np.arange(w["hip_deg"][0], w["hip_deg"][1] + 1e-9, w["step_deg"])
             for k in np.arange(w["knee_deg"][0], w["knee_deg"][1] + 1e-9, 15.0)]
    poses += [(params["poses"]["tuck"]["hip"], k) for k in np.arange(90.0, -90.01, -15.0)]
    pts = []
    for h, k in poses:
        for (group, _), mesh in model.group_meshes({"hip": float(h), "knee": float(k)}).items():
            if group != "torso":
                pts.append(np.vstack([mesh.vertices, trimesh.sample.sample_surface(mesh, 4000, seed=0)[0]]))
    p = np.vstack(pts)
    p = p[(np.abs(p[:, 0]) < half_xy[0] + pad) & (np.abs(p[:, 1]) < half_xy[1] + pad)]
    return float(p[:, 2].min()), float(p[:, 2].max()), float(np.abs(p[:, 1]).min())


def s3_cover_job(model, params, center, bore_top, pin_dir, pin_z):
    """Lid for the widened S3 frame, clamped by the four carrier screws (longer M1.6, driven from above
    through the bosses); the mast carries the dome.  Femurs pass the carrier's long edges at hip 90 deg,
    so inside their Z band (+ ROM clearance) the lid stays within |y| <= y_limit (end walls and bosses
    only, sides open for cables); the full-width box and roof sit above the band."""
    mp, cp, body = params["mount"], params["mount"]["cover"], params["body"]
    s3 = model.s3
    c = params["acceptance"]["rom_clearance_mm"] + cp["leg_extra_clearance"]
    z_lo, z_hi, y_in = leg_envelope_near_body(model, params, cp["outer_half_mm"], 6.0)
    top = s3["pcb_top_z"]
    roof_bottom = top + body["electronics_height_above_pcb_mm"] + cp["roof_clearance"]
    roof_top = roof_bottom + cp["roof"]
    band = [max(z_lo - c, top + cp["boss_floor"] + 1.0), z_hi + c]
    assert roof_bottom > band[1] + 3, "electronics below the femur band: lower the roof differently"
    cover = {"outer_half": cp["outer_half_mm"], "wall": cp["wall"], "pcb_top_z": top,
             "roof_bottom_z": roof_bottom, "roof_top_z": roof_top, "leg_band_z": band, "y_limit": y_in - c,
             "leg_envelope": {"z": [z_lo, z_hi], "min_abs_y": y_in},
             "bosses": [h[:2] for h in s3["pcb_holes"]], "boss_r": cp["boss_r"], "bore_r": cp["bore_d"] / 2,
             "screw_r": cp["screw_clear_d"] / 2, "boss_floor": cp["boss_floor"],
             "end_window": [cp["end_window_half_y"], top + cp["end_window_top_above_pcb"]]}
    mount = {"mast_xy": center[:2].tolist(), "plate_top_z": roof_top, "mast_top_z": bore_top - 0.5,
             "mast_outer_r": mp["mast_outer_d"] / 2, "mast_inner_r": mp["mast_inner_d"] / 2,
             "gusset_r": mp["gusset_r"], "gusset_h": mp["gusset_h"],
             "pin_dir": pin_dir.tolist(), "pin_z": pin_z, "pin_r": params["shell"]["socket"]["pin_d"] / 2}
    return cover, mount


def run_freecad(job_path, out_dir):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    res = subprocess.run([FREECAD_PY, "-I", str(BAMBU / "scripts" / "build_shell.py"), str(job_path)],
                         env=env, capture_output=True, text=True)
    if res.returncode:
        raise SystemExit(res.stdout[-3000:] + res.stderr[-3000:])
    return json.loads((pathlib.Path(out_dir) / "cad.json").read_text())


VARIANT_PARTS = {"one-piece": ("shell-onepiece",), "two-piece": ("shell-dome", "shell-mount"),
                 "s3-cover": ("shell-dome", "s3-top-cover"),
                 "v3-brackets": ("shell-dome", "dome-bracket-left", "dome-bracket-right"),
                 "v3-crown": ("shell-dome", "crown", "head-lid", "lid-key"),
                 "v3-mushroom": ("shell-dome", "stem-lid", "lid-key"),
                 "v3-headarms": ("shell-dome", "head-arms")}


def shell_masses(cad, variant):
    return [(cad[k]["volume_mm3"] / 1000 * SHELL_DENSITY_G_CM3, np.array(cad[k]["centroid_mm"]))
            for k in VARIANT_PARTS[variant]]


def main(params=None, out_dir=None, build_dir=None, quiet=False):
    params = params or load_params()
    paths = params.get("paths", {})
    out_dir = pathlib.Path(out_dir or BAMBU / paths.get("stl_dir", "stl"))
    build_dir = pathlib.Path(build_dir or BAMBU / paths.get("build_dir", "build"))
    model = SesameModel(params)
    tuck = params["poses"]["tuck"]
    extra = [(42.0, np.array([0.0, 0.0, 95.0]))]  # first guess
    job_path = build_dir / "job.json"
    job_path.parent.mkdir(parents=True, exist_ok=True)
    prev = None
    for it in range(6):
        _, com = model.mass_properties(tuck, extra)
        job = make_job(model, com, params, out_dir)
        job_path.write_text(json.dumps(job, indent=1))
        cad = run_freecad(job_path, out_dir)
        extra = shell_masses(cad, params["shell"]["variant"])
        if job["rings"] and job["rings"][0].get("layout") == "spiral":  # the LED tape rides with the shell
            info = job["rings"][0]
            cad["led-tape"] = {"mass_g": info["tape_mass_g"], "centroid_mm": info["tape_centroid_mm"],
                               "length_mm": info["tape_length_mm"], "leds": info["cells"]}
            (out_dir / "cad.json").write_text(json.dumps(cad, indent=1))
            extra.append((info["tape_mass_g"], np.array(info["tape_centroid_mm"])))
        _, com_new = model.mass_properties(tuck, extra)
        shift = float(np.linalg.norm(com_new - com))
        quiet or print(f"iteration {it}: shell parts {[round(m, 1) for m, _ in extra]} g, "
              f"CoM {com_new.round(2)} (moved {shift:.2f} mm), holes {len(job['dome']['holes'])}")
        if shift < params["shell"]["com_fixed_point_tol_mm"]:
            break
        prev = com_new
    summary = {
        "com_tuck_used_for_center": com.tolist(), "com_tuck_final": com_new.tolist(),
        "dome_center": job["dome"]["center"], "rings": job["rings"],
        "apex_tilt_allowance_deg": job["apex_tilt_allowance_deg"],
        "variant": params["shell"]["variant"],
        "masses_g": dict(zip(VARIANT_PARTS[params["shell"]["variant"]], [m for m, _ in extra])), "cad": cad}
    (build_dir / "design.json").write_text(json.dumps(summary, indent=1))
    return summary


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--params", help="params JSON (default bambu/params.json)")
    main(load_params(ap.parse_args().params))
