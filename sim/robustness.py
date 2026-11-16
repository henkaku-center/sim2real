"""Does a motion's outcome survive the parameters nobody measured?

The twin's masses, servo gain, friction and collision shapes are estimates.
Parameter agreement alone does not establish trust: numerical validity and
physical comparisons are also needed. This module compares coarse outcomes
over a fixed engineering stress grid, then separately screens the wave's
trajectory and timestep convergence. The grid is not a measured uncertainty
distribution and its pass counts are not probabilities of real success.

The grid (54 runs per motion):
- whole-robot centre of mass moved -15, 0, +15 mm along the body and
  -8, 0, +8 mm across it;
- collision with the record's boxes, or with the convex hulls of the drawn parts;
- servo gain and sliding friction at nominal, low (0.6, 0.5) and high (1.6, 1.2).

Distances travelled and slip are not compared: they change with every small
parameter change (DECISIONS.md D26, D27) and are not predictions.

The instructor observed forward tipping during a real wave (2026-11-16).
The exact support contacts and installed command were not measured. The grid
can reproduce forward tipping, but this does not identify its physical cause
or independently validate the modified wave. See DECISIONS.md D28.

Usage:
  uv run python -m sim.robustness                 every stock motion
  uv run python -m sim.robustness --motion wave   one motion, with its failures
  uv run python -m sim.robustness --check-wave    independent acceptance gate
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from pathlib import Path

import numpy as np

from sim import twin
from sim.manifest import load_manifest
from sim.motions import ctrl_schedule, flatten, load_motions

COM_DX_MM = (-15.0, 0.0, 15.0)
COM_DY_MM = (-8.0, 0.0, 8.0)
COLLISION = ("box", "hull")
GAIN_FRICTION = ((1.0, 1.0), (0.6, 0.5), (1.6, 1.2))
GRID = tuple(itertools.product(COM_DX_MM, COM_DY_MM, COLLISION, GAIN_FRICTION))
NOMINAL = (0.0, 0.0, "box", (1.0, 1.0))
UPRIGHT_ABOVE = 0.95  # torso up-axis z component at the end
IN_AIR_ABOVE = 0.5  # fraction of the motion a foot is off the floor
SETTLE_STEPS = 500


def hull_collision_xml(xml: str) -> str:
    """The same model colliding with the convex hulls of its drawn meshes instead of its boxes."""
    xml, boxes = re.subn(r'(<geom name="\w+_geom" type="box" group="3")', r'\1 contype="0" conaffinity="0"', xml)
    xml, meshes = re.subn(r'(<geom name="\w+_visual"[^>]*?)\s+contype="0" conaffinity="0"', r"\1", xml, flags=re.S)
    assert boxes and meshes, "the twin's collision boxes or drawn meshes were not found"
    return xml


def outcome(steps: list, variation=NOMINAL, design: str | None = None, *, timestep=None, contact_timeconst=None) -> dict:
    """Replay `steps` (motions.yaml format) on one variation of the twin."""
    import mujoco

    dx_mm, dy_mm, collision, (gain, friction) = variation
    manifest = load_manifest()
    xml = twin.build(design, manifest=manifest).xml
    model = twin.compile_xml(hull_collision_xml(xml) if collision == "hull" else xml)
    torso = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "torso")
    share = model.body_subtreemass[torso] / model.body_mass[torso]  # move the whole robot's centre, via the torso
    model.body_ipos[torso, 0] += dx_mm / 1000 * share
    model.body_ipos[torso, 1] += dy_mm / 1000 * share
    model.geom_friction[:, 0] *= friction
    model.actuator_gainprm[:, 0] *= gain
    model.actuator_biasprm[:, 1] *= gain
    if timestep is not None:
        model.opt.timestep = timestep
    if contact_timeconst is not None:
        if contact_timeconst < 2 * model.opt.timestep:
            raise ValueError("Contact time constant must be at least twice the timestep")
        model.geom_solref[:, 0] = contact_timeconst

    data = mujoco.MjData(model)
    # body_ipos changes derived inertia/solver constants. Refresh before replay;
    # see MuJoCo programming/simulation, "Model changes".
    mujoco.mj_setConst(model, data)
    mujoco.mj_resetData(model, data)
    schedule = ctrl_schedule(flatten(steps, manifest.raw["poses"]), manifest, model.opt.timestep)
    floor = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    feet = {j.name: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"{j.leg}_lower")
            for j in manifest.joints if j.role == "foot"}
    moving = schedule[-1][0] if schedule else 0
    settle_steps = round(1.0 / model.opt.timestep)
    if moving < settle_steps:  # a single pose: judge it once the robot has settled into it
        moving += settle_steps
    touching = dict.fromkeys(feet, 0)
    i = 0
    counted = 0
    min_up = 1.0
    max_penetration = 0.0
    body_contact_steps = 0
    finite = True
    # For a wave, exclude preparation and the return-to-stand, but not later
    # recovery: a transient failure during the waving interval remains visible.
    lift = next((ev.time_ms / 1000 for ev in flatten(steps, manifest.raw["poses"])
                 if ev.targets_deg.get("L3", 0) >= 100), None)
    wave_count = 0
    wave_contact = 0
    wave_min_up = 1.0
    for step in range(moving + settle_steps):
        while i < len(schedule) and schedule[i][0] <= step:
            data.ctrl[schedule[i][1]] = schedule[i][2]
            i += 1
        mujoco.mj_step(model, data)
        # Refresh positions/contacts at the integrated state, not the previous
        # step's state. Do not let a later recovery hide a transient failure.
        mujoco.mj_forward(model, data)
        finite = finite and bool(np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all())
        if step >= round(0.5 / model.opt.timestep):
            min_up = min(min_up, float(data.xmat[torso].reshape(3, 3)[2, 2]))
            floor_contacts = [c for c in data.contact[:data.ncon] if floor in (c.geom1, c.geom2)]
            max_penetration = max(max_penetration, max((-float(c.dist) for c in floor_contacts), default=0.0))
            body_contact_steps += any(int(model.geom_bodyid[c.geom2 if c.geom1 == floor else c.geom1]) == torso for c in floor_contacts)
        if round(0.5 / model.opt.timestep) <= step < moving:
            counted += 1
            on_floor = {int(model.geom_bodyid[c.geom2 if c.geom1 == floor else c.geom1])
                        for c in data.contact[: data.ncon] if floor in (c.geom1, c.geom2)}
            for name, body in feet.items():
                touching[name] += body in on_floor
            if lift is not None and step * model.opt.timestep >= lift + 0.3:
                wave_count += 1
                wave_contact += feet.get("L3") in on_floor
                wave_min_up = min(wave_min_up, float(data.xmat[torso].reshape(3, 3)[2, 2]))
    air = {name: 1 - count / counted for name, count in touching.items()}
    return {
        "upright": bool(data.xmat[torso].reshape(3, 3)[2, 2] > UPRIGHT_ABOVE),
        "feet_in_air": sorted(name for name, frac in air.items() if frac > IN_AIR_ABOVE),
        "air_fraction": {name: round(float(frac), 3) for name, frac in air.items()},
        "minimum_up_axis": round(min_up, 6),
        "maximum_tilt_deg": round(float(np.degrees(np.arccos(np.clip(min_up, -1, 1)))), 3),
        "maximum_floor_penetration_mm": round(max_penetration * 1000, 3),
        "body_floor_contact_s": round(body_contact_steps * model.opt.timestep, 6),
        "finite": finite,
        "solver_warnings": int(sum(w.number for w in data.warning)),
        "timestep_s": float(model.opt.timestep),
        "wave_contact_fraction": wave_contact / wave_count if wave_count else None,
        "wave_maximum_tilt_deg": float(np.degrees(np.arccos(np.clip(wave_min_up, -1, 1)))) if wave_count else None,
    }


def _key(result: dict) -> tuple:
    return result["upright"], tuple(result["feet_in_air"])


def survey(steps: list, design: str | None = None, grid=GRID) -> dict:
    """Coarse parameter agreement only; this does NOT establish numerical validity."""
    nominal = _key(outcome(steps, NOMINAL, design))
    counts: dict[tuple, int] = {}
    differing = []
    upright = 0
    for variation in grid:
        key = _key(outcome(steps, variation, design))
        counts[key] = counts.get(key, 0) + 1
        upright += key[0]
        if key != nominal:
            differing.append({"com_dx_mm": variation[0], "com_dy_mm": variation[1], "collision": variation[2],
                              "gain_friction": list(variation[3]), "upright": key[0], "feet_in_air": list(key[1])})
    return {
        "nominal": {"upright": nominal[0], "feet_in_air": list(nominal[1])},
        "runs": len(grid),
        "agree": counts.get(nominal, 0),
        "coarse_agreement": counts.get(nominal, 0) == len(grid),
        "upright": upright,
        "differing": differing,
    }


# Engineering screening tolerances, not measured contact properties. Fixed
# before accepting the wave; a failure is not a reason to widen these bounds.
WAVE_LIMITS = {"penetration_mm": 1.0, "tilt_deg": 20.0,
               "wave_contact_fraction": 0.01, "tilt_change_deg": 1.0,
               "penetration_change_mm": 0.25, "contact_fraction_change": 0.02}


def wave_failures(result: dict) -> list[str]:
    failures = []
    if not result["finite"] or result["solver_warnings"]:
        failures.append("nonfinite-state-or-solver-warning")
    if not result["upright"] or result["wave_maximum_tilt_deg"] is None or result["wave_maximum_tilt_deg"] > WAVE_LIMITS["tilt_deg"]:
        failures.append("wave-tilt-or-final-posture")
    if result["wave_contact_fraction"] is None or result["wave_contact_fraction"] > WAVE_LIMITS["wave_contact_fraction"]:
        failures.append("waving-foot-contact")
    if result["body_floor_contact_s"]:
        failures.append("body-floor-contact")
    if result["maximum_floor_penetration_mm"] > WAVE_LIMITS["penetration_mm"]:
        failures.append("excessive-floor-penetration")
    return failures


def wave_audit(steps: list, design: str | None = None) -> dict:
    """Explicit release screen: nominal and extreme corners at three timesteps.

    Passing this finite screen is not physical validation. Failure must prevent
    promotion of a coarse grid result to a trustworthy simulation claim.
    """
    cases = [NOMINAL, (-15., -8., "box", (0.6, 0.5)),
             (15., 8., "box", (0.6, 0.5)), (15., 8., "hull", (1.6, 1.2))]
    runs = []
    converged = True
    for variation in cases:
        results = [outcome(steps, variation, design, timestep=dt) for dt in (.002, .001, .0005)]
        for r in results:
            runs.append({"variation": variation, "result": r, "failures": wave_failures(r)})
        for a, b in zip(results, results[1:]):
            converged &= abs(a["maximum_tilt_deg"] - b["maximum_tilt_deg"]) <= WAVE_LIMITS["tilt_change_deg"]
            converged &= abs(a["maximum_floor_penetration_mm"] - b["maximum_floor_penetration_mm"]) <= WAVE_LIMITS["penetration_change_mm"]
            converged &= max(abs(a["air_fraction"][k] - b["air_fraction"][k]) for k in a["air_fraction"]) <= WAVE_LIMITS["contact_fraction_change"]
    root = Path(__file__).resolve().parents[1]
    paths = ["sim/robustness.py", "manifest/motions.yaml", "manifest/twin.yaml", "manifest/robot.yaml"]
    import mujoco
    return {"status": "simulated-unmeasured-parameters", "engine": mujoco.__version__,
            "design": design or twin.default_design(),
            "limits": WAVE_LIMITS, "converged": bool(converged),
            "accepted": bool(converged and all(not r["failures"] for r in runs)),
            "input_sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
            "runs": runs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--motion")
    parser.add_argument("--design")
    parser.add_argument("--check-wave", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    motions = load_motions()["motions"]
    if args.check_wave:
        result = wave_audit(motions["wave"], args.design)
        text = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.write_text(text)
        print(text)
        return 0 if result["accepted"] else 1
    names = [args.motion] if args.motion else sorted(motions)
    print("SIMULATED, unmeasured parameters. Outcome = ends upright + feet mostly off the floor.")
    for name in names:
        result = survey(motions[name], args.design)
        nominal = result["nominal"]
        label = "AGREEMENT" if result["coarse_agreement"] else "SENSITIVE"
        print(f"{name:16} {label} {result['agree']:2}/{result['runs']} agree; ends upright in {result['upright']:2}/{result['runs']}; "
              f"nominal: {'upright' if nominal['upright'] else 'not upright'}, in air {nominal['feet_in_air'] or 'none'}", flush=True)
        if args.motion:
            for row in result["differing"]:
                print("   ", row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
