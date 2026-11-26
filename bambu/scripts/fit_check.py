"""Assembly-path and printability checks for the screw-free V3 crown mount (variant v3-crown).

    uv run python -I bambu/scripts/fit_check.py --params bambu/params-v3crown.json

All numbers are penetration depths (mm, signed distance of sampled surface points; > 0 = inside the
other part) or overhang areas (mm^2), fixed seeds.  Writes <build_dir>/fit_check.json and exits 1 if a
check fails.
  1. head-lid in the head-cover rail: no more interference than the kit lid itself; the added crown
     clears the head cover (ears) along the whole rear-to-front insertion path;
  2. stopper key: seated without interference; it blocks the lid within `key_lock_mm` of rearward travel;
  3. dome on the crown: seated without interference; lifting it engages the snap barbs within
     `snap_lock_mm`; finger deflection needed while lowering it stays within the designed spring travel;
     lowering the dome over the standing robot never touches a leg;
  4. printability: downward-facing area below each part's allowed overhang slope (bed contact excluded).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from sesame_model import BAMBU, ROOT, SesameModel, load_params  # noqa: E402

N_SAMPLES = 15000


def samples(mesh, n=N_SAMPLES, seed=0):
    return trimesh.sample.sample_surface(mesh, n, seed=seed)[0]


def penetration(points, mesh):
    """Deepest sampled point of `points` inside `mesh` (mm); 0 if none inside."""
    near = points[np.all((points > mesh.bounds[0] - 1) & (points < mesh.bounds[1] + 1), axis=1)]
    if len(near) == 0:
        return 0.0
    d = trimesh.proximity.signed_distance(mesh, near)
    return float(max(d.max(), 0.0))


def shifted(points, d):
    return points + np.asarray(d, float)


def overhang(mesh, slope_limits=(25, 30, 40, 45)):
    """Downward-facing area by slope from horizontal (deg), excluding faces on the bed (z = 0)."""
    n, a = mesh.face_normals, mesh.area_faces
    zmin = mesh.triangles[:, :, 2].max(axis=1)
    down = (n[:, 2] < -1e-3) & (zmin > 0.05)
    slope = np.degrees(np.arccos(np.clip(-n[:, 2], -1, 1)))
    out, lo = {}, 0
    for hi in slope_limits:
        out[f"{lo}-{hi}deg_mm2"] = round(float(a[down & (slope >= lo) & (slope < hi)].sum()), 1)
        lo = hi
    return out


def floating_islands(mesh, pitch=0.2, min_area_mm2=1.0):
    """Regions that start in mid-air in print orientation (no grounded material within 2 voxels in the
    layer below), as the slicer's 'floating region' warning.  A floating region is followed upward
    while it stays apart from grounded material and reported once it reaches min_area_mm2, so a web
    that starts from a point and grows (e.g. between two openings) is caught, while voxel noise at a
    wall edge or the apex of a pointed arch merges with the wall before it gets that large."""
    from scipy import ndimage
    vg = mesh.voxelized(pitch).fill()
    occ, o = vg.matrix, vg.transform[:3, 3]
    out, prev, prev_float, prev_done = [], None, None, None
    for k in range(occ.shape[2]):
        layer = occ[:, :, k]
        flt, done = np.zeros_like(layer), np.zeros_like(layer)
        if prev is not None and layer.any():
            lab, n = ndimage.label(layer)
            grounded = ndimage.binary_dilation(prev & ~prev_float, iterations=2)
            near_done = ndimage.binary_dilation(prev_done, iterations=2)
            for i in range(1, n + 1):
                comp = lab == i
                if (comp & grounded).any():
                    continue
                flt |= comp
                area = comp.sum() * pitch * pitch
                if (comp & near_done).any():
                    done |= comp
                elif area >= min_area_mm2:
                    done |= comp
                    xs, ys = np.nonzero(comp)
                    out.append({"z_mm": round(float(o[2] + k * pitch), 2), "area_mm2": round(float(area), 2),
                                "xy_mm": [round(float(o[0] + xs.mean() * pitch), 1), round(float(o[1] + ys.mean() * pitch), 1)]})
        prev, prev_float, prev_done = layer, flt, done
    return out


def legs_gap_while_lowering(params, dome):
    """Lower the dome from 80 mm above its seat over the standing robot: smallest dome-leg distance."""
    import fcl
    from analyze import bvh
    model = SesameModel(params)
    legs = trimesh.util.concatenate([m for p, _, m in model.posed(params["poses"]["stand"])
                                     if m is not None and p.group != "torso"])
    lo, do = bvh(legs), bvh(dome)
    dmin = []
    for dz in np.arange(0.0, 80.01, 2.0):
        do.setTranslation(np.array([0.0, 0.0, dz]))
        dmin.append(fcl.distance(lo, do, fcl.DistanceRequest(), fcl.DistanceResult()))
    return round(min(dmin), 2)


def printability(params, res, ok):
    fc, stl = params["fit_check"], BAMBU / params["paths"]["stl_dir"]
    lim = fc["overhang_min_slope_deg"]
    res["overhang"], res["floating_islands"] = {}, {}
    for name, allowed in lim.items():
        m = trimesh.load(stl / f"{name}.stl")
        oh = overhang(m)
        bad = sum(v for k, v in oh.items() if int(k.split("-")[1].split("deg")[0]) <= allowed)
        oh["below_allowed_mm2"] = round(bad, 1)
        res["overhang"][name] = oh
        ok[f"printable_{name}"] = bad <= fc["overhang_tolerance_mm2"][name]
        isl = floating_islands(m, 0.25 if name == "shell-dome" else 0.2)
        res["floating_islands"][name] = isl
        ok[f"no_floating_{name}"] = not isl


def headarms(params):
    """Variant v3-headarms: lid still fits the new head; arms clear the servo ribbons; the dome drops in at the
    insertion angle, turns into the lock (only the detent interferes), is held against lift and press and
    keyed in rotation; lowering it never touches a leg; printability."""
    import fcl
    from analyze import bvh
    fc, body = params["fit_check"], params["body"]
    stl = BAMBU / params["paths"]["stl_dir"]
    kit = ROOT / body["frame_dir"]
    dz18 = [0, 0, body["frame_to_robot_z"]]
    kit_head = trimesh.load(kit / "head-cover.stl").apply_translation(dz18)
    kit_lid = trimesh.load(kit / "head-lid.stl").apply_translation(dz18)
    head = trimesh.load(stl / "assembly" / "head-mount.stl")
    arms = trimesh.load(stl / "assembly" / "head-arms.stl")
    dome = trimesh.load(stl / "assembly" / "shell-dome.stl")
    ha = json.loads((BAMBU / params["paths"]["build_dir"] / "job.json").read_text())["head_arms"]
    cx, cy = ha["center"][:2]
    th, sense = ha["twist_deg"], ha["twist_sense"]
    res, ok = {}, {}

    p_lid = samples(kit_lid)
    res["kit_lid_in_kit_head_mm"] = round(penetration(p_lid, kit_head), 3)
    res["kit_lid_in_head_mount_mm"] = round(penetration(p_lid, head), 3)
    ok["lid_fits_like_kit"] = res["kit_lid_in_head_mount_mm"] <= res["kit_lid_in_kit_head_mm"] + 0.05
    rib = json.loads((kit / "head-cable-clearance.json").read_text())
    rpts = np.vstack([np.array(q["points_mm"]) for q in rib["paths"]]) + dz18
    from scipy.spatial import cKDTree
    dd, _ = cKDTree(samples(arms, 200000, seed=4)).query(rpts)
    res["arms_to_kit_ribbon_paths_mm"] = round(float(dd.min()), 2)
    ok["arms_clear_ribbons"] = res["arms_to_kit_ribbon_paths_mm"] >= fc["ribbon_clearance_mm"]

    def turned(pts, deg):
        a = np.radians(deg)
        q = pts - [cx, cy, 0]
        return np.c_[q[:, 0] * np.cos(a) - q[:, 1] * np.sin(a), q[:, 0] * np.sin(a) + q[:, 1] * np.cos(a), q[:, 2]] + [cx, cy, 0]

    # dome points near the rim at the two sides (lugs and rim band), head points of the arm tips
    p_dome = samples(dome, 200000, seed=5)
    p_dome = p_dome[(p_dome[:, 2] < ha["rim_z"] + 12) & (np.abs(p_dome[:, 1]) > 60) & (np.abs(p_dome[:, 0] - cx) < 35)]
    p_tip = samples(head, 300000, seed=6)
    p_tip = p_tip[np.abs(p_tip[:, 1]) > ha["tip"]["y_back"] - 1]

    def pen(deg, dz):  # dome turned by deg (about its axis) and raised by dz, both directions of contact
        a = penetration(turned(p_dome, deg) + [0, 0, dz], head)
        b = penetration(turned(p_tip - [0, 0, dz], -deg), dome)
        return max(a, b)

    ins = -sense * th
    res["drop_in_max_mm"] = round(max(pen(ins, dz) for dz in np.arange(0.0, 30.01, 1.0)), 3)
    ok["drops_in_at_insertion_angle"] = res["drop_in_max_mm"] <= 0.05
    twist = [(round(float(a), 2), pen(ins + sense * a, 0.0)) for a in np.arange(0.0, th + 0.01, 0.25)]
    res["twist_max_mm"] = round(max(p for _, p in twist), 3)
    res["twist_max_at_deg"] = max(twist, key=lambda r: r[1])[0]
    res["seated_mm"] = round(pen(0.0, 0.0), 3)
    ok["seated"] = res["seated_mm"] <= 0.05
    ok["detent_clicks"] = fc["detent_min_mm"] <= res["twist_max_mm"] <= fc["detent_max_mm"]
    lift = next((round(float(dz), 2) for dz in np.arange(0.05, 2.01, 0.05) if pen(0.0, dz) > 0.1), None)
    press = next((round(float(dz), 2) for dz in np.arange(0.05, 2.01, 0.05) if pen(0.0, -dz) > 0.1), None)
    res["lift_catches_after_mm"], res["press_bears_after_mm"] = lift, press
    ok["lift_locked"] = lift is not None and lift <= fc["lift_lock_mm"]
    ok["press_supported"] = press is not None and press <= fc["press_lock_mm"]
    fwd = next((round(float(a), 2) for a in np.arange(0.05, 3.01, 0.05) if pen(sense * a, 0.0) > 0.1), None)
    back = next((round(float(a), 2) for a in np.arange(0.05, 3.01, 0.05) if pen(-sense * a, 0.0) > 0.1), None)
    res["rotation_stop_after_deg"], res["rotation_detent_after_deg"] = fwd, back
    ok["rotation_keyed"] = all(v is not None and v <= fc["rotation_lock_deg"] for v in (fwd, back))

    model = SesameModel(params)
    legs = trimesh.util.concatenate([m for p, _, m in model.posed(params["poses"]["stand"])
                                     if m is not None and p.group != "torso"])
    lo = bvh(legs)
    gaps = {}
    for name, deg in (("insertion_angle", ins), ("locked_angle", 0.0)):
        dm = dome.copy()
        dm.vertices = turned(dm.vertices, deg)
        do = bvh(dm)
        g = []
        for dz in np.arange(0.0, 80.01, 2.0):
            do.setTranslation(np.array([0.0, 0.0, dz]))
            g.append(fcl.distance(lo, do, fcl.DistanceRequest(), fcl.DistanceResult()))
        gaps[name] = round(min(g), 2)
    dm = dome.copy()
    tw = []
    for a in np.arange(0.0, th + 0.01, 1.0):
        dm.vertices = turned(dome.vertices, ins + sense * a)
        tw.append(fcl.distance(lo, bvh(dm), fcl.DistanceRequest(), fcl.DistanceResult()))
    gaps["while_turning"] = round(min(tw), 2)
    res["dome_min_leg_gap_mm"] = gaps
    ok["dome_install_clears_legs"] = min(gaps.values()) > 0.5

    printability(params, res, ok)
    res["overhang"]["head-mount (supports expected)"] = overhang(trimesh.load(stl / "head-mount.stl"))
    return res, ok


def mushroom(params):
    """Variant v3-mushroom: stem-lid in the rail, stem path while the lid slides in, key, dome on the stem
    (seat, snap, rotation key, prong deflection), dome lowered over the legs, printability."""
    fc, body = params["fit_check"], params["body"]
    stl = BAMBU / params["paths"]["stl_dir"]
    kit = ROOT / body["frame_dir"]
    dz18 = [0, 0, body["frame_to_robot_z"]]
    head = trimesh.load(kit / "head-cover.stl").apply_translation(dz18)
    kit_lid = trimesh.load(kit / "head-lid.stl").apply_translation(dz18)
    sl = trimesh.load(stl / "assembly" / "stem-lid.stl")
    key = trimesh.load(stl / "assembly" / "lid-key.stl")
    dome = trimesh.load(stl / "assembly" / "shell-dome.stl")
    st = json.loads((BAMBU / params["paths"]["build_dir"] / "job.json").read_text())["stem"]
    ax, ay = st["axis_xy"]
    zl = st["lid_top_z"]
    res, ok = {}, {}

    # 1. lid in the rail; the stem must clear the head cover (ears) along the rear-to-front slide
    p_sl = samples(sl, 120000, seed=1)
    lid_pts, stem_pts = p_sl[p_sl[:, 2] < zl + 0.3], p_sl[p_sl[:, 2] >= zl + 0.3]
    res["kit_lid_in_head_mm"] = round(penetration(samples(kit_lid), head), 3)
    res["lid_in_head_mm"] = round(penetration(lid_pts, head), 3)
    ok["lid_fits_like_kit"] = res["lid_in_head_mm"] <= res["kit_lid_in_head_mm"] + 0.05
    res["stem_slide_in_max_mm"] = round(max(penetration(stem_pts + [-dx, 0, 0], head) for dx in np.arange(0.0, 120.1, 2.0)), 3)
    ok["stem_slides_in"] = res["stem_slide_in_max_mm"] <= 0.05
    rib = json.loads((kit / "head-cable-clearance.json").read_text())
    rpts = np.vstack([np.array(q["points_mm"]) for q in rib["paths"]]) + dz18
    from scipy.spatial import cKDTree
    dd, _ = cKDTree(samples(sl, 200000, seed=4)).query(rpts)
    res["stem_lid_to_kit_ribbon_paths_mm"] = round(float(dd.min()), 2)
    ok["stem_lid_clears_ribbons"] = res["stem_lid_to_kit_ribbon_paths_mm"] >= fc["ribbon_clearance_mm"]

    # 2. stopper key
    p_key = samples(key, 5000)
    res["key_in_head_mm"] = round(penetration(p_key, head), 3)
    res["key_in_lid_mm"] = round(penetration(p_key, sl), 3)
    lock = next((round(float(dx), 2) for dx in np.arange(0.1, 3.01, 0.1)
                 if penetration(shifted(p_key, [-dx, 0, 0]), head) > 0.1), None)
    res["key_blocks_rearward_after_mm"] = lock
    ok["key_seated"] = res["key_in_head_mm"] <= 0.05 and res["key_in_lid_mm"] <= 0.05
    ok["key_locks"] = lock is not None and lock <= fc["key_lock_mm"]

    # 3. dome on the stem (only the apex region can touch)
    z_lo = st["rib_top_at_r_out"] - st["ribs"]["tip_h"] - 30
    p_dome = samples(dome, 150000, seed=5)
    p_dome = p_dome[(p_dome[:, 2] > z_lo) & (np.hypot(p_dome[:, 0] - ax, p_dome[:, 1] - ay) < st["ribs"]["r_out"] + 6)]
    p_top = samples(sl, 300000, seed=2)
    p_top = p_top[p_top[:, 2] > z_lo]
    res["dome_in_stem_mm"] = round(penetration(p_dome, sl), 3)
    res["stem_in_dome_mm"] = round(penetration(p_top, dome), 3)
    ok["dome_seated"] = max(res["dome_in_stem_mm"], res["stem_in_dome_mm"]) <= 0.1
    knob = p_top[p_top[:, 2] > st["cut_z"] + st["knob_gap"] - 0.05]
    snap = next((round(float(dz), 2) for dz in np.arange(0.05, 3.01, 0.05)
                 if penetration(shifted(knob, [0, 0, -dz]), dome) > 0.1), None)
    res["knob_catches_after_lift_mm"] = snap
    ok["snap_locks"] = snap is not None and snap <= fc["snap_lock_mm"]

    def turned(pts, deg):
        a = np.radians(deg)
        q = pts - [ax, ay, 0]
        return np.c_[q[:, 0] * np.cos(a) - q[:, 1] * np.sin(a), q[:, 0] * np.sin(a) + q[:, 1] * np.cos(a), q[:, 2]] + [ax, ay, 0]

    fin = p_top[(p_top[:, 2] > st["cut_z"] - 6) & (np.hypot(p_top[:, 0] - ax, p_top[:, 1] - ay) > st["fin"]["r"][0] - 0.1)]
    rot = {}
    for sgn in (1, -1):
        rot[sgn] = next((round(float(a), 2) for a in np.arange(0.1, 5.01, 0.1)
                         if penetration(turned(fin, -sgn * a), dome) > 0.05), None)
    res["rotation_play_deg"] = [rot[1], rot[-1]]
    ok["rotation_keyed"] = all(v is not None and v <= fc["rotation_lock_deg"] for v in rot.values())
    # lowering the dome: the ribs/fin must never be in the way; each prong half must bend towards the slot
    # (y -> axis) by less than its free travel and the designed limit
    rest = p_top[(p_top[:, 2] < st["cut_z"] - 3) | (np.abs(p_top[:, 0] - ax) > st["prong_half_x"] + 0.05)]
    res["lowering_ribs_fin_max_mm"] = round(max(penetration(rest + [0, 0, -dz], dome) for dz in np.arange(0.5, 30.01, 0.5)), 3)
    ok["lowering_ribs_fin_clear"] = res["lowering_ribs_fin_max_mm"] <= 0.05
    need = 0.0
    tip = p_top[(p_top[:, 2] > st["cut_z"] - 3) & (np.abs(p_top[:, 0] - ax) <= st["prong_half_x"] + 0.05)]
    for side in (1, -1):
        half = tip[(tip[:, 1] - ay) * side > 0]
        for dz in np.arange(0.25, 12.01, 0.25):
            s_in = next((s for s in np.arange(0.0, 3.01, 0.05)
                         if penetration(half + [0, -side * s, -dz], dome) <= 0.02), 9.0)
            need = max(need, s_in)
    res["lowering_max_prong_deflection_mm"] = round(float(need), 2)
    ok["prongs_flex_enough"] = (0.5 <= need <= fc["max_prong_deflection_mm"]) and need <= st["slot"] / 2 - 0.2
    res["lowering_dome_min_leg_gap_mm"] = legs_gap_while_lowering(params, dome)
    ok["lowering_clears_legs"] = res["lowering_dome_min_leg_gap_mm"] > 0.5

    printability(params, res, ok)
    return res, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", required=True)
    args = ap.parse_args()
    params = load_params(args.params)
    if params["shell"]["variant"] in ("v3-mushroom", "v3-headarms"):
        res, ok = (mushroom if params["shell"]["variant"] == "v3-mushroom" else headarms)(params)
        res["ok"] = ok
        out = BAMBU / params["paths"]["build_dir"] / "fit_check.json"
        out.write_text(json.dumps(res, indent=1))
        print(json.dumps(res, indent=1))
        return 0 if all(ok.values()) else 1
    fc = params["fit_check"]
    stl = BAMBU / params["paths"]["stl_dir"]
    body = params["body"]
    kit = ROOT / body["frame_dir"]
    dz18 = [0, 0, body["frame_to_robot_z"]]
    head = trimesh.load(kit / "head-cover.stl").apply_translation(dz18)
    kit_lid = trimesh.load(kit / "head-lid.stl").apply_translation(dz18)
    key = trimesh.load(stl / "assembly" / "lid-key.stl")
    dome = trimesh.load(stl / "assembly" / "shell-dome.stl")
    job = json.loads((BAMBU / params["paths"]["build_dir"] / "job.json").read_text())
    lid_top = job["crown"]["lid_top_z"]
    res, ok = {}, {}

    # 1. lid in the rail (kit lid + bayonet socket + key slot: cuts only)
    lid = trimesh.load(stl / "assembly" / "head-lid.stl")
    crown = trimesh.load(stl / "assembly" / "crown.stl")
    p_lid, p_kit = samples(lid), samples(kit_lid)
    res["kit_lid_in_head_mm"] = round(penetration(p_kit, head), 3)
    res["lid_in_head_mm"] = round(penetration(p_lid, head), 3)
    ok["lid_fits_like_kit"] = res["lid_in_head_mm"] <= res["kit_lid_in_head_mm"] + 0.05

    # 2. crown bayonet: drop in with the lugs in the notches, turn, then it must not lift out
    b = job["crown"]["bayonet"]
    ax, ay = job["crown"]["axis_xy"]
    p_cr = samples(crown, 40000, seed=3)

    def turned(pts, deg):
        a = np.radians(deg)
        q = pts - [ax, ay, 0]
        r = np.c_[q[:, 0] * np.cos(a) - q[:, 1] * np.sin(a), q[:, 0] * np.sin(a) + q[:, 1] * np.cos(a), q[:, 2]]
        return r + [ax, ay, 0]

    low = p_cr[p_cr[:, 2] < lid_top + 3.0]  # tube, seat and lugs: the only parts near the lid
    unlocked = turned(low, -b["turn_deg"])
    res["crown_drop_in_max_mm"] = round(max(max(penetration(unlocked + [0, 0, dz], lid), penetration(unlocked + [0, 0, dz], head))
                                           for dz in np.arange(0.0, 20.01, 1.0)), 3)
    res["crown_turn_max_mm"] = round(max(penetration(turned(low, -a), lid) for a in np.arange(0.0, b["turn_deg"] + 0.1, 5.0)), 3)
    lift = None
    for dz in np.arange(0.05, 2.01, 0.05):
        if penetration(low + [0, 0, dz], lid) > 0.1:
            lift = round(float(dz), 2)
            break
    res["crown_lugs_catch_after_lift_mm"] = lift
    ok["crown_drops_in"] = res["crown_drop_in_max_mm"] <= 0.05
    ok["crown_turns"] = res["crown_turn_max_mm"] <= 0.05
    ok["crown_locked"] = lift is not None and lift <= fc["bayonet_lock_mm"]

    # nothing of the crown may hang under the lid, where the kit routes the servo ribbons
    rib = json.loads((kit / "head-cable-clearance.json").read_text())
    rpts = np.vstack([np.array(q["points_mm"]) for q in rib["paths"]]) + dz18
    from scipy.spatial import cKDTree
    dd, _ = cKDTree(samples(crown, 200000, seed=4)).query(rpts)
    res["crown_to_kit_ribbon_paths_mm"] = round(float(dd.min()), 2)
    ok["crown_clears_ribbons"] = res["crown_to_kit_ribbon_paths_mm"] >= fc["ribbon_clearance_mm"]

    # stopper key
    p_key = samples(key, 5000)
    res["key_in_head_mm"] = round(penetration(p_key, head), 3)
    res["key_in_lid_mm"] = round(penetration(p_key, lid), 3)
    lock = None
    for dx in np.arange(0.1, 3.01, 0.1):
        if penetration(shifted(p_key, [-dx, 0, 0]), head) > 0.1:
            lock = round(float(dx), 2)
            break
    res["key_blocks_rearward_after_mm"] = lock
    ok["key_seated"] = res["key_in_head_mm"] <= 0.05 and res["key_in_lid_mm"] <= 0.05
    ok["key_locks"] = lock is not None and lock <= fc["key_lock_mm"]
    lid = crown  # the dome checks below are against the crown

    # 3. dome on the crown (only points near the thin dome wall / the crown top can interfere)
    c = np.asarray(job["dome"]["center"])
    rin = job["crown"]["dome_inner_r"]
    p_dome = samples(dome, 120000)
    p_dome = p_dome[(p_dome[:, 2] > job["crown"]["seat_z"] - 12) & (p_dome[:, 2] < job["crown"]["seat_z"] + 35)]
    p_top = samples(lid, 200000, seed=2)
    p_top = p_top[np.linalg.norm(p_top - c, axis=1) > rin - 4.0]  # seat rim, fingers, barbs
    res["dome_in_crown_mm"] = round(penetration(p_dome, lid), 3)
    res["crown_in_dome_mm"] = round(penetration(p_top, dome), 3)
    p_lid = p_top
    ok["dome_seated"] = max(res["dome_in_crown_mm"], res["crown_in_dome_mm"]) <= 0.1
    snap = None
    for dz in np.arange(0.1, 4.01, 0.1):  # lift the dome: barbs must catch the window edges
        if penetration(shifted(p_lid, [0, 0, -dz]), dome) > 0.2:
            snap = round(float(dz), 2)
            break
    res["snap_catches_after_lift_mm"] = snap
    ok["snap_locks"] = snap is not None and snap <= fc["snap_lock_mm"]
    # finger deflection needed while lowering: smallest inward (towards the axis) shift of each barb that
    # clears the dome wall at every height of the descent
    need = 0.0
    for fg in job["crown"]["fingers"]:
        ph = np.radians(fg["phi_deg"])
        er = np.array([np.cos(ph), np.sin(ph), 0.0])
        hz = np.array(fg["barb_hz"])
        z0b, z1b = hz[:, 1].min() - 0.5, hz[:, 1].max() + 0.5
        h_proj = p_lid @ er - c @ er
        tang = p_lid @ np.array([-np.sin(ph), np.cos(ph), 0.0])
        barb = p_lid[(p_lid[:, 2] > z0b) & (p_lid[:, 2] < z1b) & (np.abs(tang - c @ np.array([-np.sin(ph), np.cos(ph), 0.0])) < fg["barb_width"] / 2 + 0.5)
                     & (h_proj > hz[:, 0].min() + 0.5)]
        for dz in np.arange(0.5, 25.01, 0.5):
            for s_in in np.arange(0.0, 4.01, 0.1):
                if penetration(barb - er * s_in + [0, 0, -dz], dome) <= 0.02:
                    break
            need = max(need, s_in)
    res["lowering_max_finger_deflection_mm"] = round(float(need), 2)
    ok["fingers_flex_enough"] = 0.5 <= res["lowering_max_finger_deflection_mm"] <= fc["max_finger_deflection_mm"]
    model = SesameModel(params)
    legs = trimesh.util.concatenate([m for p, _, m in model.posed(params["poses"]["stand"])
                                     if m is not None and p.group != "torso"])
    import fcl
    from analyze import bvh
    lo, do = bvh(legs), bvh(dome)
    dmin = []
    for dz in np.arange(0.0, 80.01, 2.0):
        do.setTranslation(np.array([0.0, 0.0, dz]))
        dmin.append(fcl.distance(lo, do, fcl.DistanceRequest(), fcl.DistanceResult()))
    res["lowering_dome_min_leg_gap_mm"] = round(min(dmin), 2)
    ok["lowering_clears_legs"] = res["lowering_dome_min_leg_gap_mm"] > 0.5

    # 4. printability (print-orientation STLs)
    lim = fc["overhang_min_slope_deg"]
    res["overhang"] = {}
    for name, allowed in lim.items():
        m = trimesh.load(stl / f"{name}.stl")
        oh = overhang(m)
        res["overhang"][name] = oh
        bad = sum(v for k, v in oh.items() if int(k.split("-")[1].split("deg")[0]) <= allowed)
        res["overhang"][name]["below_allowed_mm2"] = round(bad, 1)
        ok[f"printable_{name}"] = bad <= fc["overhang_tolerance_mm2"][name]
    res["floating_islands"] = {}
    for name in lim:
        isl = floating_islands(trimesh.load(stl / f"{name}.stl"), 0.25 if name == "shell-dome" else 0.2)
        res["floating_islands"][name] = isl
        ok[f"no_floating_{name}"] = not isl
    res["ok"] = ok
    out = BAMBU / params["paths"]["build_dir"] / "fit_check.json"
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return 0 if all(ok.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
