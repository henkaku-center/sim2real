"""Fast (no CAD) screen of shell shape / size / tuck pose for the static self-righting criterion.

    uv run python -I bambu/scripts/quick_screen.py --params bambu/params-v3crown.json \
        --R 86 90 94 --e 16 20 --tuck 90,-90 75,-90

The shell is a point cloud of its outer surface: a sphere (radius R, centre e above the tucked CoM)
from the rim plane up to the polar angle where its slope reaches `cap_slope_deg`, then the tangent
cone up to a rounded tip (support-free when printed rim-down).  Openings are ignored for the hull
(the perforation rule keeps their bridging facets non-holding).  Shell mass = area x wall x solid
fraction x density, placed at the surface centroid; `extra_parts` in the params add fixed masses
(the crown).  Reports the worst non-belly resting margin over the CoM perturbation set (0 = only
belly-down rests), the shell size and its mass.  CAD + analyze.py remain the acceptance check.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analyze import BELLY_TILT_DEG  # noqa: E402
from sesame_model import SesameModel, load_params  # noqa: E402
from design import in_slot, leg_sweep  # noqa: E402
from stability import equilibria, fibonacci_sphere  # noqa: E402


def shell_surface(center, R, rim_z, cap_slope_deg, tip_r, n=6000):
    """Outer surface points (and per-point area weights) of the sphere band + tangent cone cap."""
    tc = math.radians(cap_slope_deg)  # polar angle where the sphere slope equals the cap slope
    d = fibonacci_sphere(n)
    pts, w = [], []
    a_sph = 4 * math.pi * R ** 2 / n
    for u in d:
        th = math.acos(np.clip(u[2], -1, 1))
        p = center + R * u
        if p[2] < rim_z:
            continue
        if th >= tc:
            pts.append(p)
            w.append(a_sph)
    # cone: apex on the axis at R / cos(tc); half-angle (90 - cap_slope) from the axis
    apex = center[2] + R / math.cos(tc)
    r0, z0 = R * math.sin(tc), center[2] + R * math.cos(tc)
    half = math.pi / 2 - tc
    zt = apex - tip_r / math.sin(half) + tip_r * math.sin(half)  # top of the cone part (tip sphere tangent)
    for z in np.linspace(z0, zt, 25):
        r = (apex - z) * math.tan(half)
        m = max(8, int(2 * math.pi * r / 5))
        for ang in np.linspace(0, 2 * math.pi, m, endpoint=False):
            pts.append([center[0] + r * math.cos(ang), center[1] + r * math.sin(ang), z])
            w.append(2 * math.pi * r * (zt - z0) / 25 / math.cos(half) / m)
    tip_c = apex - tip_r / math.sin(half)
    for u in fibonacci_sphere(400):
        if u[2] > math.cos(half):
            pts.append([center[0] + tip_r * u[0], center[1] + tip_r * u[1], tip_c + tip_r * u[2]])
            w.append(1e-6)
    return np.array(pts), np.array(w), apex


def evaluate(model, params, R, e, cap_slope, tuck, iters=4):
    sp = params["shell"]
    rho = sp.get("density_g_cm3", 1.24) / 1000
    pose = {"hip": tuck[0], "knee": tuck[1]}
    extra = [(m["mass_g"], np.array(m["com_mm"], float)) for m in params.get("extra_parts", [])]
    body_pts = np.vstack([m.vertices for _, _, m in model.posed(pose) if m is not None])
    slots = [leg_sweep(model, pose, leg, sp["knee_slot_clearance"]) for leg in model.legs]
    _, com = model.mass_properties(pose, extra)
    for _ in range(iters):  # shell mass moves the CoM, which moves the shell
        center = com + np.array([0, 0, e])
        pts, w, apex = shell_surface(center, R, sp["rim_z"], cap_slope, sp.get("tip_radius", 6.0))
        keep = np.array([not in_slot(q, slots, 0.0) for q in pts])  # knee-sweep slots cut through the rim
        pts, w = pts[keep], w[keep]
        mass = w.sum() * sp["thickness"] * sp.get("solid_fraction", 0.55) * rho
        c_shell = (pts * w[:, None]).sum(0) / w.sum()
        _, com = model.mass_properties(pose, extra + [(mass, c_shell)])
    allp = np.vstack([body_pts, pts])
    worst, n_bad, deepest = 0.0, 0, 0.0
    dirs = [np.zeros(3)] + [np.array(v, float) for v in itertools.product((-1, 0, 1), repeat=3) if any(v)]
    for dv in dirs:
        g = com + (params["acceptance"]["com_perturbation_mm"] * dv / np.linalg.norm(dv) if dv.any() else 0)
        _, eq = equilibria(allp, g, min_report_margin=-5)
        bad = [x for x in eq if x["stable"] and not x["micro"] and x["tilt_deg"] >= BELLY_TILT_DEG]
        n_bad += bool(bad)
        worst = max([worst] + [x["margin_mm"] for x in bad])
        deepest = max([deepest] + [x["depth_mm"] for x in bad])
    return {"R": R, "e": e, "cap_slope": cap_slope, "tuck": list(tuck), "worst_other_margin_mm": round(worst, 2), "deepest_other_mm": round(deepest, 3),
            "dirs_bad": n_bad, "shell_g": round(mass, 1), "width_mm": round(2 * R, 1),
            "top_z_mm": round(float(pts[:, 2].max()), 1), "rim_z": sp["rim_z"], "com_tuck": com.round(2).tolist()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", required=True)
    ap.add_argument("--R", type=float, nargs="+", required=True)
    ap.add_argument("--e", type=float, nargs="+", required=True)
    ap.add_argument("--cap", type=float, nargs="+", default=[45.0], help="cap slope from horizontal, deg")
    ap.add_argument("--tuck", nargs="+", default=["90,-90"], help="hip,knee pairs")
    args = ap.parse_args()
    params = load_params(args.params)
    model = SesameModel(params)
    for R, e, cap, tk in itertools.product(args.R, args.e, args.cap, args.tuck):
        tuck = tuple(float(v) for v in tk.split(","))
        print(json.dumps(evaluate(model, params, R, e, cap, tuck)), flush=True)


if __name__ == "__main__":
    main()
