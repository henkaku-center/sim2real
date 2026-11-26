"""Verify the generated shell against the self-righting requirements.

    uv run python -I bambu/scripts/analyze.py [--skip-mujoco] [--params bambu/params-s3wide.json]

Writes bambu/build/report.json and preview PNGs in bambu/preview/.
Checks (all numeric, fixed seeds):
  1. static equilibria of the tucked robot+shell on a flat floor (exact, convex hull faces)
     with the CoM perturbed by +-com_perturbation_mm along 26 directions;
  2. quasi-static orientation basins;
  3. face / electronics inside the hull with margin (tucked and standing);
  4. clearance between shell parts and every leg over the walking ROM, the tuck sweep and
     every pose of manifest/motions.yaml (tricks are informational);
  5. MuJoCo drop tests (rigid tucked body) and fallen-state recovery sequences (articulated).
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import sys

import fcl
import numpy as np
import trimesh
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from design import SHELL_DENSITY_G_CM3, VARIANT_PARTS  # noqa: E402
from sesame_model import BAMBU, SesameModel, load_params  # noqa: E402
from stability import basins, equilibria, hull_inside_margin  # noqa: E402

ROOT = BAMBU.parent
MANIFEST_JOINTS = {"R1": ("front_right", "hip"), "R2": ("back_right", "hip"), "L1": ("front_left", "hip"),
                   "L2": ("back_left", "hip"), "R3": ("front_right", "knee"), "R4": ("back_right", "knee"),
                   "L3": ("front_left", "knee"), "L4": ("back_left", "knee")}
PROTECT_KINDS = ("electronics", "battery")
BELLY_TILT_DEG = 15.0


def load_shell(stl_dir=None, variant=None, params=None):
    params = params or load_params()
    stl_dir = pathlib.Path(stl_dir or BAMBU / params.get("paths", {}).get("stl_dir", "stl"))
    variant = variant or params["shell"]["variant"]
    parts = {}
    for name in VARIANT_PARTS[variant]:
        mesh = trimesh.load(stl_dir / "assembly" / f"{name}.stl", force="mesh")
        parts[name] = mesh
    cad = json.loads((stl_dir / "cad.json").read_text())
    extra = [(cad[k]["volume_mm3"] / 1000 * SHELL_DENSITY_G_CM3, np.array(cad[k]["centroid_mm"])) for k in parts]
    if "led-tape" in cad:  # mass only; no mesh (it lies inside the shell wall's hull)
        extra.append((cad["led-tape"]["mass_g"], np.array(cad["led-tape"]["centroid_mm"])))
    return parts, extra, cad


def firmware_to_q(manifest, name, deg):
    j = next(j for j in manifest["joints"] if j["name"] == name)
    return (deg - 90.0) * j["sign"]


def bvh(mesh):
    m = fcl.BVHModel()
    m.beginModel(len(mesh.vertices), len(mesh.faces))
    m.addSubModel(np.asarray(mesh.vertices, float), np.asarray(mesh.faces, np.int32))
    m.endModel()
    return fcl.CollisionObject(m, fcl.Transform())


def min_distance(a, b):
    req, res = fcl.DistanceRequest(enable_nearest_points=True), fcl.DistanceResult()
    return fcl.distance(a, b, req, res)


def leg_pose_grid(params):
    w = params["walking_rom"]
    hips = np.arange(w["hip_deg"][0], w["hip_deg"][1] + 1e-9, w["step_deg"])
    knees = np.arange(w["knee_deg"][0], w["knee_deg"][1] + 1e-9, w["step_deg"])
    return [(float(h), float(k)) for h in hips for k in knees]


def check_static(model, params, shell, extra):
    acc = params["acceptance"]
    out = {}
    shell_pts = np.vstack([m.vertices for m in shell.values()])
    for pose_name in ("tuck", "stand"):
        pose = params["poses"][pose_name]
        mass, com = model.mass_properties(pose, extra)
        body = [(p, mesh) for p, _, mesh in model.posed(pose) if mesh is not None]
        pts = np.vstack([mesh.vertices for _, mesh in body] + [shell_pts])
        hull, eq = equilibria(pts, com, min_report_margin=-5.0)
        stable = [e for e in eq if e["stable"] and not e["micro"]]
        belly = [e for e in stable if e["tilt_deg"] < BELLY_TILT_DEG]
        others = [e for e in stable if e["tilt_deg"] >= BELLY_TILT_DEG]
        micro = [e for e in eq if e["micro"]]
        # protection: every electronics / battery / top-cover vertex inside the hull by >= margin
        prot = {}
        for p, mesh in body:
            if p.kind in PROTECT_KINDS or p.label == "COMPOUND001":
                key = "top_cover" if p.label == "COMPOUND001" else p.kind
                m = float(hull_inside_margin(hull, mesh.vertices).min())
                prot[key] = min(prot.get(key, np.inf), m)
        out[pose_name] = {"mass_g": round(float(mass), 1), "com_mm": com.round(2).tolist(),
                          "hull_extent_mm": [pts.min(0).round(1).tolist(), pts.max(0).round(1).tolist()],
                          "stable_faces": stable, "belly_faces": len(belly), "other_stable_faces": others,
                          "micro_wells": {"count": len(micro), "max_depth_mm": max([e["depth_mm"] for e in micro], default=0.0),
                                          "max_margin_mm": max([e["margin_mm"] for e in micro], default=0.0)},
                          "protection_margin_mm": {k: round(v, 2) for k, v in prot.items()}}
        if pose_name == "tuck":
            worst = []
            dirs = [np.array(d, float) for d in itertools.product((-1, 0, 1), repeat=3) if any(d)]
            for d in dirs:
                g = com + acc["com_perturbation_mm"] * d / np.linalg.norm(d)
                _, e2 = equilibria(pts, g, min_report_margin=-5.0)
                bad = [e for e in e2 if e["stable"] and not e["micro"] and e["tilt_deg"] >= BELLY_TILT_DEG]
                worst.append({"dir": d.tolist(), "other_stable": len(bad),
                              "max_margin_mm": max([e["margin_mm"] for e in bad], default=None),
                              "max_depth_mm": max([e["depth_mm"] for e in bad], default=0.0),
                              "belly_stable": any(e["stable"] and e["tilt_deg"] < BELLY_TILT_DEG for e in e2)})
            out[pose_name]["com_perturbation"] = worst
            b = basins(pts, com)
            out[pose_name]["basins"] = b[:8]
            out[pose_name]["belly_basin_fraction"] = round(sum(x["fraction"] for x in b if x["tilt_deg"] < BELLY_TILT_DEG), 4)
    return out


def check_clearance(model, params, shell):
    acc = params["acceptance"]
    manifest = yaml.safe_load((ROOT / "manifest" / "robot.yaml").read_text())
    motions = yaml.safe_load((ROOT / "manifest" / "motions.yaml").read_text())["motions"]
    shell_objs = {k: bvh(v) for k, v in shell.items()}

    def leg_min(pose, legs=None):
        meshes = model.group_meshes(pose)
        best = (np.inf, None)
        for (group, leg), mesh in meshes.items():
            if group == "torso" or (legs and leg not in legs):
                continue
            o = bvh(mesh)
            for sname, so in shell_objs.items():
                d = min_distance(o, so)
                if d < best[0]:
                    best = (d, f"{group}:{leg} vs {sname}")
        return best

    res = {}
    walk = []
    for hip, knee in leg_pose_grid(params):
        d, what = leg_min({"hip": hip, "knee": knee})
        walk.append((d, hip, knee, what))
    walk.sort()
    res["walking_rom"] = {"min_mm": round(walk[0][0], 2), "at": {"hip": walk[0][1], "knee": walk[0][2], "pair": walk[0][3]},
                          "ok": walk[0][0] >= acc["rom_clearance_mm"]}
    sweep = []
    for knee in np.arange(90, -90.01, -5):
        d, what = leg_min({"hip": params["poses"]["tuck"]["hip"], "knee": float(knee)})
        sweep.append((d, float(knee), what))
    sweep.sort()
    res["tuck_sweep"] = {"min_mm": round(sweep[0][0], 2), "at_knee": sweep[0][1], "pair": sweep[0][2],
                         "ok": sweep[0][0] >= acc["rom_clearance_mm"]}
    # torso parts vs the shell (static): the saddle sits on the top cover by design
    torso = model.group_meshes(params["poses"]["stand"])[("torso", None)]
    to = bvh(torso)
    res["torso_vs_shell_mm"] = {k: round(min_distance(to, o), 3) for k, o in shell_objs.items()}
    if model.s3 is not None:  # the S3 lid sits on the carrier; the hip servo cases must stay clear
        servos = [m for p, _, m in model.posed(params["poses"]["stand"])
                  if p.group == "torso" and p.kind == "servo" and m is not None]
        servo = trimesh.util.concatenate(servos)
        so = bvh(servo)
        res["hip_servos_vs_shell_mm"] = {k: round(min_distance(so, o), 3) for k, o in shell_objs.items()
                                         if not k.startswith("dome-bracket")}
        if "servo_mounts" in model.s3 and any(k.startswith("dome-bracket") for k in shell):  # brackets rest on the ears
            ear_top = model.s3["deck_top_z"] + params["mount"]["bracket"]["ear_top_above_deck"]
            pts = trimesh.sample.sample_surface(servo, 400000, seed=0)[0]
            pts = pts[pts[:, 2] > ear_top + 0.05]
            for k, mesh in shell.items():
                if k.startswith("dome-bracket"):
                    near = pts[np.linalg.norm(pts[:, :2] - mesh.bounds.mean(0)[:2], axis=1) < 60]
                    inside = mesh.contains(near)
                    d = trimesh.proximity.ProximityQuery(mesh).signed_distance(near)
                    res["hip_servos_vs_shell_mm"][k] = round(float(-d.max()), 3) if not inside.any() else -1.0
    # every pose reached by the stock motion library (tricks are informational)
    walking = {"walk", "walk_backward", "turn_left", "turn_right", "stand", "rest"}
    rows = {}
    for name, steps in motions.items():
        state = {j: 90.0 for j in MANIFEST_JOINTS}
        worst = (np.inf, None)

        def visit(steps):
            nonlocal worst
            for st in steps:
                if "pose" in st:
                    state.update(manifest["poses"][st["pose"]])
                elif "set" in st:
                    state.update(st["set"])
                elif "repeat" in st:
                    visit(st["repeat"]["steps"])
                    continue
                else:
                    continue
                pose = {"hip": {}, "knee": {}}
                for j, (leg, role) in MANIFEST_JOINTS.items():
                    pose[role][leg] = firmware_to_q(manifest, j, state[j])
                d, what = leg_min(pose)
                if d < worst[0]:
                    worst = (d, what, dict(state))
        visit(steps)
        rows[name] = {"min_mm": round(worst[0], 2), "pair": worst[1], "walking": name in walking,
                      "ok": worst[0] >= acc["rom_clearance_mm"]}
    res["motions"] = rows
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-mujoco", action="store_true")
    ap.add_argument("--params", help="params JSON (default bambu/params.json)")
    args = ap.parse_args()
    params = load_params(args.params)
    model = SesameModel(params)
    shell, extra, cad = load_shell(params=params)
    report = {"revision": params["revision"], "params": params,
              "variant": params["shell"]["variant"],
              "mass_g": {"robot": round(model.mass_properties(params["poses"]["stand"])[0], 1),
                         **{k: round(m, 1) for k, (m, _) in zip(list(shell) + ["led-tape"], extra)}},
              "body_mass_breakdown": model.summary(params["poses"]["stand"]),
              "cad": cad}
    report["static"] = check_static(model, params, shell, extra)
    report["clearance"] = check_clearance(model, params, shell)
    if not args.skip_mujoco:
        from sim_check import run_all  # noqa: E402
        report["mujoco"] = run_all(model, params, shell, extra)
        if params["acceptance"].get("max_other_rest_depth_mm"):  # shallow rests allowed: prove they do not hold
            from sim_check import drop_tests_com_error  # noqa: E402
            report["mujoco"]["drop_com_error"] = drop_tests_com_error(model, params, shell, extra)
    st = report["static"]["tuck"]
    acc_depth = params["acceptance"].get("max_other_rest_depth_mm", 0.0)  # 0: any non-belly rest fails
    verdict = {
        "monostable_tucked": st["belly_faces"] >= 1 and all(e["depth_mm"] <= acc_depth for e in st["other_stable_faces"]),
        "monostable_with_com_error": all((w["other_stable"] == 0 or w["max_depth_mm"] <= acc_depth) and w["belly_stable"]
                                         for w in st["com_perturbation"]),
        "electronics_protected": all(v >= params["acceptance"]["protect_margin_mm"]
                                     for pose in ("tuck", "stand") for v in report["static"][pose]["protection_margin_mm"].values()),
        "walking_rom_clear": report["clearance"]["walking_rom"]["ok"]
        and all(r["ok"] for r in report["clearance"]["motions"].values() if r["walking"]),
        "tuck_sweep_clear": report["clearance"]["tuck_sweep"]["ok"],
    }
    if "hip_servos_vs_shell_mm" in report["clearance"]:
        verdict["hip_servos_clear"] = min(report["clearance"]["hip_servos_vs_shell_mm"].values()) >= 0.5
    if "mujoco" in report:
        verdict["mujoco_drop_success_rate"] = report["mujoco"]["drop"]["success_rate"]
        verdict["mujoco_recovery_all"] = all(r["recovered"] for r in report["mujoco"]["recovery"])
        if "drop_com_error" in report["mujoco"]:
            verdict["mujoco_drop_com_error_all"] = report["mujoco"]["drop_com_error"]["all_ok"]
    report["verdict"] = verdict
    out = BAMBU / params.get("paths", {}).get("build_dir", "build") / "report.json"
    out.write_text(json.dumps(report, indent=1, default=float))
    print(json.dumps({"mass_g": report["mass_g"], "verdict": verdict,
                      "tuck_other_stable": [(e["tilt_deg"], e["margin_mm"]) for e in st["other_stable_faces"]],
                      "com_perturbation_bad": [w for w in st["com_perturbation"] if w["other_stable"] or not w["belly_stable"]],
                      "protection": {p: report["static"][p]["protection_margin_mm"] for p in ("tuck", "stand")},
                      "clearance": {k: v for k, v in report["clearance"].items() if k != "motions"},
                      "motions_bad": {k: v for k, v in report["clearance"]["motions"].items() if not v["ok"]}},
                     indent=1, default=float))
    ok = all(v is True or (isinstance(v, float) and v >= 1.0) for v in verdict.values())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
