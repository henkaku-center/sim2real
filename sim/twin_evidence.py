"""Simulated evidence for a design variant against its base design.

For each variant listed in manifest/twin.yaml this writes
assets/printing/<variant>/dynamics-evidence.json with, for both designs:
- mass and rest-pose centre of mass from the dynamics records, and the change;
- static stability in the Standing pose: distance from the projected centre of
  mass to the nearest edge of the support polygon (the convex hull of the
  foot/floor contact points after the stand command settles);
- the same margin over a seeded sample of mass-table perturbations, because
  every mass is an estimate or a nominal value;
- the telemetry signature of Stand and every stock motion (sim/telemetry.py),
  and how far each motion's end state moves when every commanded angle is
  nudged by 1e-9 rad, so that comparisons know which motions are repeatable.

This is MuJoCo simulation with unmeasured parameters. It is not a measurement,
a physical stability test or an acceptance of the variant.

Usage:
  uv run python -m sim.twin_evidence            regenerate (about a minute)
  uv run python -m sim.twin_evidence --check    exit 1 when inputs changed
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from pathlib import Path

import numpy as np

from sim import twin
from sim.manifest import MANIFEST_PATH, REPO_ROOT, load_manifest
from sim.motions import MOTIONS_PATH, ctrl_schedule, flatten, load_motions
from sim.telemetry import motion_signature

EVIDENCE_NAME = "dynamics-evidence.json"
SCHEMA = "sim2real-dynamics-evidence/1"
STATUS = "simulated-unmeasured-parameters"
SCOPE = (
    "MuJoCo simulation of the generated twins. Printed masses are estimated from mesh "
    "volume; purchased parts, actuator and contact parameters are nominal. No part was "
    "weighed and no physical stability, motion or assembly test was run."
)
SETTLE_STEPS = 2000  # 4 s of the stand command before the support polygon is read
REFERENCE_STEPS = 1000
UNCERTAINTY = {"seed": 20261112, "samples": 32, "spread": 0.2}

# Declared agreement between this file and a recomputation on another platform.
TOLERANCES = {
    "margin_mm": 0.5, "height_mm": 0.5, "stand_qpos": 1e-3,
    "signature": {"disp_m": 0.002, "yaw_deg": 1.0, "z_m": 0.001, "pitch_m": 0.001,
                  "upright": 0.01, "air_frac": 0.02, "paw_max_z_m": 0.001},
    "sensitive_signature": {"disp_m": 0.04, "yaw_deg": 10.0, "z_m": 0.003, "pitch_m": 0.005,
                            "upright": 0.02, "air_frac": 0.1, "paw_max_z_m": 0.005},
}
NUDGE_RAD = 1e-9  # change of every commanded angle used to tell repeatable motions from sensitive ones
SENSITIVE_ABOVE_MM = 0.1  # a motion whose end state moves more than this is `sensitive`
SETTLE_AFTER_MOTION = 500  # as sim.motions.play_native and sim.telemetry


def evidence_path(variant: str) -> Path:
    return twin.design_dir(variant) / EVIDENCE_NAME


def _hull(points: np.ndarray) -> np.ndarray:
    """Convex hull of 2-D points, counter-clockwise (monotone chain)."""
    pts = sorted(set(map(tuple, np.round(points, 9).tolist())))
    if len(pts) < 3:
        return np.array(pts)

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def support_margin(polygon: np.ndarray, point: np.ndarray) -> tuple[float, int]:
    """Signed distance from point to the nearest polygon edge (positive inside), and that edge."""
    if len(polygon) < 3:
        return -math.inf, -1
    best, edge = math.inf, -1
    for i in range(len(polygon)):
        a, b = polygon[i], polygon[(i + 1) % len(polygon)]
        side = b - a
        inside = (side[0] * (point[1] - a[1]) - side[1] * (point[0] - a[0])) / math.hypot(*side)
        if inside < best:
            best, edge = inside, i
    return best, edge


def standing(model, manifest=None, steps: int = SETTLE_STEPS) -> dict:
    """Command the Standing pose from the spawn state, settle, and read stability."""
    import mujoco

    manifest = manifest or load_manifest()
    data = mujoco.MjData(model)
    stand = manifest.pose_internal("stand")
    data.ctrl[:] = [stand[j.name] for j in manifest.joints]
    for _ in range(steps):
        mujoco.mj_step(model, data)
    torso = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "torso")
    floor = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    feet = {mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{j.leg}_lower_geom"): j.name
            for j in manifest.joints if j.role == "foot"}
    points, owners = [], []
    for k in range(data.ncon):
        contact = data.contact[k]
        pair = {int(contact.geom1), int(contact.geom2)}
        if floor in pair and (pair - {floor}) and next(iter(pair - {floor})) in feet:
            points.append(contact.pos[:2].copy())
            owners.append(feet[next(iter(pair - {floor}))])
    com = data.subtree_com[torso].copy()
    polygon = _hull(np.array(points)) if points else np.zeros((0, 2))
    margin, edge = support_margin(polygon, com[:2])
    centroid = polygon.mean(axis=0) if len(polygon) else np.zeros(2)
    nearest = "none"
    if edge >= 0:
        mid = (polygon[edge] + polygon[(edge + 1) % len(polygon)]) / 2 - centroid
        nearest = (("front" if mid[0] > 0 else "rear") if abs(mid[0]) > abs(mid[1])
                   else ("left" if mid[1] > 0 else "right"))
    return {
        "settle_steps": steps,
        "margin_mm": round(margin * 1000, 4),
        "nearest_edge": nearest,
        "tilt_to_tip_deg": round(math.degrees(math.atan2(margin, com[2])), 3),
        "com_height_mm": round(float(com[2]) * 1000, 4),
        "com_from_support_centroid_mm": [round(float(v) * 1000, 4) for v in com[:2] - centroid],
        "support_polygon_mm": [[round(float(v) * 1000, 3) for v in p] for p in polygon],
        "support_length_mm": round(float(np.ptp(polygon[:, 0])) * 1000, 3) if len(polygon) else 0.0,
        "support_width_mm": round(float(np.ptp(polygon[:, 1])) * 1000, 3) if len(polygon) else 0.0,
        "feet_in_contact": sorted(set(owners)),
        "torso_height_mm": round(float(data.qpos[2]) * 1000, 4),
        "upright": round(float(data.xmat[torso].reshape(3, 3)[2, 2]), 6),
        "max_joint_speed_rad_s": round(float(np.abs(data.qvel).max()), 6),
    }


def stand_reference(model, manifest=None, steps: int = REFERENCE_STEPS) -> list[float]:
    """Generalised positions after `steps` of the stand command (determinism reference)."""
    import mujoco

    manifest = manifest or load_manifest()
    data = mujoco.MjData(model)
    stand = manifest.pose_internal("stand")
    data.ctrl[:] = [stand[j.name] for j in manifest.joints]
    for _ in range(steps):
        mujoco.mj_step(model, data)
    return [float(v) for v in data.qpos]


def command_sensitivity(model, manifest, motion: str) -> dict:
    """How far the end of a motion moves when every commanded angle is NUDGE_RAD larger."""
    import mujoco

    events = flatten(load_motions()["motions"][motion], manifest.raw["poses"])
    schedule = ctrl_schedule(events, manifest, model.opt.timestep)
    ends = []
    for nudge in (0.0, NUDGE_RAD):
        data = mujoco.MjData(model)
        i = 0
        for step in range((schedule[-1][0] if schedule else 0) + SETTLE_AFTER_MOTION):
            while i < len(schedule) and schedule[i][0] <= step:
                data.ctrl[schedule[i][1]] = schedule[i][2] + nudge
                i += 1
            mujoco.mj_step(model, data)
        ends.append(data.qpos[:3].copy())
    moved = float(np.abs(ends[0] - ends[1]).max()) * 1000
    return {"end_shift_mm": round(moved, 6), "sensitive": moved > SENSITIVE_ABOVE_MM}


def mass_uncertainty(design: str, seed: int, samples: int, spread: float) -> dict:
    """Standing margin over seeded, independent +-spread scalings of every mass-table row."""
    spec, manifest = twin.load_spec(), load_manifest()
    rows = [row["id"] for row in spec["mass_table"]]
    rng = np.random.default_rng(seed)
    margins, masses = [], []
    for _ in range(samples):
        scale = dict(zip(rows, rng.uniform(1 - spread, 1 + spread, len(rows)).tolist()))
        what_if = twin.build(design, spec, manifest, mass_scale=scale)
        margins.append(standing(twin.compile_xml(what_if.xml), manifest)["margin_mm"])
        masses.append(what_if.record["totals"]["mass_kg"])
    return {
        "margin_mm": {"min": round(min(margins), 4), "median": round(float(np.median(margins)), 4),
                      "max": round(max(margins), 4)},
        "mass_kg": {"min": round(min(masses), 6), "max": round(max(masses), 6)},
    }


def _rounded(value, digits: int = 6):
    if isinstance(value, dict):
        return {k: _rounded(v, digits) for k, v in value.items()}
    return round(float(value), digits) + 0.0


def _mass(record: dict) -> dict:
    totals = record["totals"]
    return {"mass_kg": totals["mass_kg"], "com_mm": [round(v * 1000, 4) for v in totals["com_torso_m"]],
            "mass_by_status_kg": totals["mass_by_status_kg"]}


def inputs(variant: str, base: str) -> dict[str, str]:
    paths = [twin.model_path(base), twin.record_path(base), twin.model_path(variant),
             twin.record_path(variant), MANIFEST_PATH, MOTIONS_PATH, Path(__file__),
             REPO_ROOT / "sim" / "telemetry.py", REPO_ROOT / "sim" / "motions.py"]
    return {p.relative_to(REPO_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def evidence(variant: str) -> dict:
    import mujoco

    base = twin.load_spec()["designs"]["variants"][variant]
    manifest = load_manifest()
    records = {name: twin.load_record(name) for name in (base, variant)}
    models = {name: twin.load_model(name) for name in (base, variant)}
    mass = {name: _mass(records[name]) for name in (base, variant)}
    stand = {name: standing(models[name], manifest) for name in (base, variant)}
    unsure = {name: mass_uncertainty(name, **UNCERTAINTY) for name in (base, variant)}
    names = sorted(load_motions()["motions"])
    motions = {name: {design: _rounded(motion_signature(name, design=design)) for design in (base, variant)}
               for name in names}
    nudged = {name: {design: command_sensitivity(models[design], manifest, name) for design in (base, variant)}
              for name in names}
    added = sorted({p["id"] for p in records[variant]["mass_table"]} - {p["id"] for p in records[base]["mass_table"]})
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "scope": SCOPE,
        "variant": variant,
        "base": base,
        "engine": {"name": "MuJoCo", "version": mujoco.__version__},
        "generated_on": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
        "inputs": inputs(variant, base),
        "mass": {
            base: mass[base], variant: mass[variant],
            "change": {
                "mass_kg": round(mass[variant]["mass_kg"] - mass[base]["mass_kg"], 9),
                "mass_percent": round(100 * (mass[variant]["mass_kg"] / mass[base]["mass_kg"] - 1), 3),
                "com_mm": [round(a - b, 4) for a, b in zip(mass[variant]["com_mm"], mass[base]["com_mm"])],
                "parts_only_in_variant": added,
            },
        },
        "standing": {
            "definition": ("Stand command from the spawn state, settled for settle_steps. Margin is the "
                           "distance from the projected whole-robot centre of mass to the nearest edge of "
                           "the convex hull of the foot/floor contact points; positive is inside."),
            base: stand[base], variant: stand[variant],
            "change": {"margin_mm": round(stand[variant]["margin_mm"] - stand[base]["margin_mm"], 4)},
        },
        "mass_uncertainty": {
            "method": ("Every mass-table row scaled independently and uniformly within +-spread, "
                       "seeded; the standing margin recomputed for each sample."),
            **UNCERTAINTY, base: unsure[base], variant: unsure[variant],
        },
        "stand_reference": {"steps": REFERENCE_STEPS,
                            base: stand_reference(models[base], manifest),
                            variant: stand_reference(models[variant], manifest)},
        "motions": motions,
        "command_sensitivity": {
            "method": (f"Each motion replayed with every commanded angle {NUDGE_RAD:g} rad larger; "
                       f"end_shift_mm is the largest change of the final torso position. Above "
                       f"{SENSITIVE_ABOVE_MM} mm the motion is `sensitive` and compared with the loose tolerances."),
            **nudged,
        },
        "tolerances": TOLERANCES,
        "not_established": [
            "Any measured mass, centre of mass, friction or servo response",
            "Physical stability, motion or durability of either design",
            "Second-display electronics, cable routing and leg clearances of the variant",
            "Behaviour outside the Standing pose and the stock motions listed here",
        ],
    }


def variants() -> dict[str, str]:
    return dict(twin.load_spec()["designs"]["variants"])


def write(variant: str) -> dict:
    result = evidence(variant)
    evidence_path(variant).write_text(json.dumps(result, indent=2) + "\n")
    return result


def check(variant: str) -> list[str]:
    """Problems with the committed evidence of one variant; empty when its inputs are unchanged."""
    path = evidence_path(variant)
    name = path.relative_to(REPO_ROOT).as_posix()
    hint = "run `uv run python -m sim.twin_evidence`"
    if not path.exists():
        return [f"{name} is missing; {hint}"]
    recorded = json.loads(path.read_text())
    base = variants()[variant]
    problems = []
    if recorded.get("status") != STATUS or recorded.get("base") != base:
        problems.append(f"{name} does not describe {variant} against {base} as {STATUS}; {hint}")
    try:
        current = inputs(variant, base)
    except OSError as error:
        return [f"{name}: missing input: {error}"]
    changed = sorted(k for k in set(current) | set(recorded.get("inputs", {}))
                     if current.get(k) != recorded.get("inputs", {}).get(k))
    if changed:
        problems.append(f"{name} is stale relative to {', '.join(changed)}; {hint}")
    return problems


def check_all() -> list[str]:
    return [problem for variant in variants() for problem in check(variant)]


def summary(result: dict) -> str:
    base, variant = result["base"], result["variant"]
    change, stand = result["mass"]["change"], result["standing"]
    return (f"{variant} against {base} ({result['status']}): mass {change['mass_kg'] * 1000:+.1f} g "
            f"({change['mass_percent']:+.1f}%), rest CoM shift {change['com_mm']} mm; standing margin "
            f"{stand[base]['margin_mm']:.1f} -> {stand[variant]['margin_mm']:.1f} mm "
            f"(nearest edge {stand[base]['nearest_edge']} -> {stand[variant]['nearest_edge']})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail when the evidence inputs changed")
    args = parser.parse_args()
    if args.check:
        problems = check_all()
        for problem in problems:
            print(problem, file=sys.stderr)
        if not problems:
            print(f"current: {', '.join(variants())}")
        return 1 if problems else 0
    for variant in variants():
        result = write(variant)
        print(f"wrote {evidence_path(variant).relative_to(REPO_ROOT)}")
        print(summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
