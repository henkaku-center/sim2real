"""Build and check the Ø100 breathing test dome for the V3 head.

    uv run python -I bambu/scripts/breath.py          -> bambu/stl/breath/*, bambu/build/breath-report.json,
                                                         bambu/preview/breath-*.png
Checks (numeric; exit code 1 on failure):
  * every part is one valid closed solid (FreeCAD) and a watertight STL
  * the dome clears the lung/mouth capsules and rings (screw-head allowance)
  * the base sits on the lid without penetrating it and clears the head shell and ears
  * no leg touches the base or dome over the walking ROM and every manifest motion pose
    (upstream leg meshes moved onto the V3 hip shafts and servo seat)
Also reports membrane bubble volumes for the pump/syringe choice.
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
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analyze import MANIFEST_JOINTS, bvh, firmware_to_q, leg_pose_grid, min_distance  # noqa: E402
from render import COLORS, render  # noqa: E402
from sesame_model import BAMBU, SesameModel, load_params  # noqa: E402

ROOT = BAMBU.parent
OUT = BAMBU / "stl" / "breath"
FREECAD_PY = os.environ.get("FREECAD_PYTHON", "/Applications/FreeCAD.app/Contents/Resources/bin/python")
V3_HIPS = {"front_left": (28.217465, 37.975), "front_right": (28.217465, -37.975),
           "back_left": (-28.583896, 37.975), "back_right": (-28.583896, -37.975)}
V3_SEAT_Z = 4.967756901865376      # assembly.json servo_flange_seat_z_mm
UPSTREAM_SEAT_Z = 23.0             # upstream frame top in the bambu robot frame
MIN_CLEAR = {"dome_vs_capsules": 1.0, "base_vs_shell": 0.5, "legs": 3.0}


def build(params_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    res = subprocess.run([FREECAD_PY, "-I", str(BAMBU / "scripts" / "build_breath.py"), str(params_path), str(ROOT), str(OUT)],
                         env=env, capture_output=True, text=True)
    if res.returncode:
        raise SystemExit(res.stdout[-3000:] + res.stderr[-3000:])
    return json.loads((OUT / "cad.json").read_text())


def v3_leg_meshes(model, pose):
    """Upstream femur/foot meshes for `pose`, moved onto the V3 hip shafts and servo seat."""
    out = {}
    for (group, leg), mesh in model.group_meshes(pose).items():
        if group == "torso":
            continue
        hx, hy = model.legs[leg].hip_point[:2]
        tx, ty = V3_HIPS[leg]
        out[(group, leg)] = mesh.copy().apply_translation([tx - hx, ty - hy, V3_SEAT_Z - UPSTREAM_SEAT_Z])
    return out


def leg_clearance(model, params, objs):
    manifest = yaml.safe_load((ROOT / "manifest" / "robot.yaml").read_text())
    motions = yaml.safe_load((ROOT / "manifest" / "motions.yaml").read_text())["motions"]
    poses = [("grid", {"hip": h, "knee": k}) for h, k in leg_pose_grid(params)]
    for name, steps in motions.items():
        state = {j: 90.0 for j in MANIFEST_JOINTS}

        def visit(st_list):
            for st in st_list:
                if "repeat" in st:
                    visit(st["repeat"]["steps"])
                    continue
                if "pose" in st:
                    state.update(manifest["poses"][st["pose"]])
                elif "set" in st:
                    state.update(st["set"])
                else:
                    continue
                pose = {"hip": {}, "knee": {}}
                for j, (leg, role) in MANIFEST_JOINTS.items():
                    pose[role][leg] = firmware_to_q(manifest, j, state[j])
                poses.append((name, pose))
        visit(steps)
    worst = {}
    for label, pose in poses:
        for key, mesh in v3_leg_meshes(model, pose).items():
            o = bvh(mesh)
            for oname, so in objs.items():
                d = min_distance(o, so)
                if d < worst.get(label, (np.inf,))[0]:
                    worst[label] = (d, f"{key[0]}:{key[1]} vs {oname}")
    return {k: {"min_mm": round(v[0], 2), "pair": v[1], "ok": v[0] >= MIN_CLEAR["legs"]} for k, v in worst.items()}


def bubble_volume_ml(free_r, h):
    return math.pi * h * (3 * free_r ** 2 + h ** 2) / 6 / 1000


def bubble_mesh(center, free_r, h, z_axis=(0, 0, 1), n_phi=24, n_az=48):
    """Spherical-cap stand-in for the inflated membrane (open surface, preview only)."""
    h = max(h, 0.3)
    rho = (free_r ** 2 + h ** 2) / (2 * h)
    phi_max = math.acos((rho - h) / rho)
    verts = [[0.0, 0.0, h]]
    for i in range(1, n_phi + 1):
        ph = phi_max * i / n_phi
        for j in range(n_az):
            a = 2 * math.pi * j / n_az
            verts.append([rho * math.sin(ph) * math.cos(a), rho * math.sin(ph) * math.sin(a), h - rho + rho * math.cos(ph)])
    faces = [[0, 1 + j, 1 + (j + 1) % n_az] for j in range(n_az)]
    for i in range(n_phi - 1):
        r0, r1 = 1 + i * n_az, 1 + (i + 1) * n_az
        for j in range(n_az):
            k = (j + 1) % n_az
            faces += [[r0 + j, r1 + j, r1 + k], [r0 + j, r1 + k, r0 + k]]
    s = trimesh.Trimesh(np.array(verts), np.array(faces), process=False)
    s.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], z_axis))
    return s.apply_translation(center)


def main():
    params_path = BAMBU / "breath_params.json"
    bp = json.loads(params_path.read_text())
    cad = build(params_path)
    model = SesameModel(load_params())
    head = ROOT / bp["head"]["dir"]
    asm = {n: trimesh.load(OUT / "assembly" / f"{n}.stl", force="mesh")
           for n in ("breath-dome", "breath-base", "head-lid-breath", "lung-ring", "mouth-ring")}
    prints = {p.stem: trimesh.load(p, force="mesh") for p in sorted(OUT.glob("*.stl"))}
    cover = trimesh.load(head / bp["head"]["cover_stl"], force="mesh")
    lid0 = trimesh.load(head / bp["head"]["lid_stl"], force="mesh")
    rep = {"revision": bp["revision"], "cad": cad}

    rep["watertight"] = {k: bool(m.is_watertight) for k, m in prints.items()}
    dens = bp["density_g_cm3"]
    rep["volume_cm3"] = {k: round(v["volume_mm3"] / 1000, 2) for k, v in cad.items() if isinstance(v, dict) and "volume_mm3" in v}
    rep["mass_estimate_g"] = {"breath-dome (thin walls, ~solid)": round(cad["breath-dome"]["volume_mm3"] / 1000 * dens, 1),
                              "breath-base (4 walls + 20 % infill, ~0.6 g/cm3)": round(cad["breath-base"]["volume_mm3"] / 1000 * 0.6, 1)}

    o = {k: bvh(m) for k, m in asm.items()}
    floor_top = cad["floor_top_z"]
    dome = asm["breath-dome"]
    upper = dome.vertices[dome.vertices[:, 2] > floor_top + 2.0]
    _, d_base, _ = trimesh.proximity.closest_point(asm["breath-base"], upper)
    rep["clearance_mm"] = {
        "dome_vs_lung_ring": round(min_distance(o["breath-dome"], o["lung-ring"]), 2),
        "dome_vs_mouth_ring": round(min_distance(o["breath-dome"], o["mouth-ring"]), 2),
        "dome_(z>floor+2)_vs_base": round(float(d_base.min()), 2),
        "base_vs_head_shell_and_ears": round(min_distance(o["breath-base"], bvh(cover)), 2),
    }
    sd = trimesh.proximity.signed_distance(lid0, asm["breath-base"].vertices)  # >0 inside the lid
    rep["base_penetration_into_lid_mm"] = round(float(max(sd.max(), 0.0)), 3)
    rep["lid_removed_volume_mm3"] = round(float(lid0.volume - asm["head-lid-breath"].volume), 2)

    l, m = bp["lung"], bp["mouth"]
    ls, ms = cad["lung_stack"], cad["mouth_stack"]
    window_edge_z = floor_top + math.sqrt(bp["dome"]["outer_r"] ** 2 - (l["window_d"] / 2) ** 2)
    rep["lung"] = {"membrane_plane_z": round(ls["ring_bot"], 2), "window_edge_z": round(window_edge_z, 2),
                   "recess_mm": round(window_edge_z - ls["ring_bot"], 2),
                   "bubble_ml": {f"h={h}mm": round(bubble_volume_ml(l["free_d"] / 2, h), 1) for h in (8, 12, 16, 20, 25)}}
    rep["mouth"] = {"lip_plane_s": round(ms["ring_bot"], 2), "outer_surface_s": bp["dome"]["outer_r"],
                    "recess_mm": round(bp["dome"]["outer_r"] - ms["ring_bot"], 2)}

    rep["legs"] = leg_clearance(model, load_params(), {"breath-base": o["breath-base"], "breath-dome": o["breath-dome"]})
    rep["checks"] = {
        "watertight": all(rep["watertight"].values()),
        "dome_clears_capsules": min(rep["clearance_mm"]["dome_vs_lung_ring"], rep["clearance_mm"]["dome_vs_mouth_ring"],
                                    rep["clearance_mm"]["dome_(z>floor+2)_vs_base"]) >= MIN_CLEAR["dome_vs_capsules"],
        "base_clears_shell": rep["clearance_mm"]["base_vs_head_shell_and_ears"] >= MIN_CLEAR["base_vs_shell"],
        "base_does_not_penetrate_lid": rep["base_penetration_into_lid_mm"] <= 0.01,
        "legs_clear_all_poses": all(v["ok"] for v in rep["legs"].values()),
    }
    (BAMBU / "build").mkdir(exist_ok=True)
    (BAMBU / "build" / "breath-report.json").write_text(json.dumps(rep, indent=1, default=float))

    # previews
    prev = BAMBU / "preview"
    prev.mkdir(exist_ok=True)
    frame = trimesh.load(head / "internal-frame.stl", force="mesh")
    bottom = trimesh.load(head / "bottom-cover.stl", force="mesh")
    legs = v3_leg_meshes(model, {"hip": 45, "knee": 90})
    green = (0.30, 0.65, 0.45, 1)
    lung_c = np.array([*bp["dome"]["center_xy"], ls["ring_bot"]])
    az, th = math.radians(m["azimuth_deg"]), math.radians(m["theta_deg"])
    n = np.array([math.sin(th) * math.cos(az), math.sin(th) * math.sin(az), math.cos(th)])
    mouth_c = np.array([*bp["dome"]["center_xy"], floor_top]) + n * (ms["ring_bot"] + m["bead"][2])
    sheet = []
    views = [{"azimuth": 150, "elevation": -18, "title": "", "distance": 420, "lookat": (0, 0, 55)},
             {"azimuth": 180, "elevation": -8, "title": "front", "distance": 420, "lookat": (0, 0, 55)}]
    for h in bp["preview_inflation_mm"]:
        meshes = [("frame", frame, COLORS["torso"]), ("bottom", bottom, COLORS["torso"]), ("cover", cover, COLORS["torso"]),
                  ("lid", asm["head-lid-breath"], COLORS["mount"]), ("base", asm["breath-base"], COLORS["mount"]),
                  ("lring", asm["lung-ring"], (0.2, 0.2, 0.2, 1)), ("mring", asm["mouth-ring"], (0.2, 0.2, 0.2, 1)),
                  ("dome", dome, green),
                  ("lung", bubble_mesh(lung_c, l["free_d"] / 2, h), (0.95, 0.55, 0.6, 1)),
                  ("lips", bubble_mesh(mouth_c, m["free_d"] / 2, h * 0.25, n), (0.85, 0.35, 0.4, 1))]
        meshes += [(f"{k}", v, COLORS[k[0]]) for k, v in legs.items()]
        v = [dict(x, title=f"membrane +{h:.0f} mm  {x['title']}") for x in views]
        sheet.append(render(meshes, v, size=(480, 400), floor_z=-48.6))
    from PIL import Image
    img = Image.new("RGB", (960, 400 * len(sheet)), "white")
    for i, s in enumerate(sheet):
        img.paste(s, (0, 400 * i))
    img.save(prev / "breath-inflation.png")
    names = ["breath-dome", "breath-base", "head-lid-breath", "lung-ring", "mouth-ring", "lung-membrane-mold", "mouth-lips-mold"]
    tiles = [render([(k, prints[k], green if k == "breath-dome" else COLORS["mount"])],
                    [{"azimuth": 135, "elevation": -35, "title": f"{k}.stl", "distance": 300 if k in ("breath-dome", "breath-base") else 160,
                      "lookat": tuple(prints[k].bounds.mean(axis=0))}], size=(360, 300), floor_z=0.0) for k in names]
    img = Image.new("RGB", (360 * 4, 600), "white")
    for i, t in enumerate(tiles):
        img.paste(t, (360 * (i % 4), 300 * (i // 4)))
    img.save(prev / "breath-print-parts.png")

    print(json.dumps({k: rep[k] for k in ("volume_cm3", "mass_estimate_g", "clearance_mm", "base_penetration_into_lid_mm",
                                            "lid_removed_volume_mm3", "lung", "mouth", "checks")}, indent=1, ensure_ascii=False))
    worst = sorted(rep["legs"].items(), key=lambda kv: kv[1]["min_mm"])[:4]
    print("closest leg poses:", worst)
    return 0 if all(rep["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
