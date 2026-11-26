"""Digital twin of the tabletop assembly line described by manifest/line.yaml.

The line twin composes published MuJoCo models of real open-source machines
(SO-101, OpenArm, this repository's Sesame twin) with placeholder printers and
fixtures on one table, and answers geometric questions with numbers:

- does every machine and fixture fit on the table;
- can each robot's gripper point reach the targets its steps name
  (position-only inverse kinematics inside the published joint limits);
- a scripted, kinematic rehearsal of one station.

It does not model grasping, soldering, printing, collisions or timing, and
nothing here was measured on hardware. See manifest/line.yaml for the limits.

Third-party models live in the ignored assets/line/upstream/ cache; fetch them
with `uv run python tools/fetch_line_models.py`.

Usage:
  uv run python -m sim.line                 regenerate assets/line/<layout>/reach.json
  uv run python -m sim.line --check         exit 1 when the committed record is stale
  uv run python -m sim.line --summary       print the findings
  uv run python -m sim.line --render DIR    write stills and the rehearsal video to DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import yaml

from sim.manifest import REPO_ROOT

LINE_PATH = REPO_ROOT / "manifest" / "line.yaml"
LINE_DIR = REPO_ROOT / "assets" / "line"
UPSTREAM_DIR = LINE_DIR / "upstream"
RECORD_NAME = "reach.json"
RECORD_SCHEMA = "sim2real-line-reach/1"
RECORD_STATUS = "simulated-geometry-unmeasured"
GEOMETRY_STATUSES = ("upstream-model", "unmeasured-nominal", "concept")
EVIDENCE = ("works-today", "demo-level", "concept")
NON_ROBOT_ACTORS = ("human", "agent")
COLOURS = {
    "yellow": (0.98, 0.86, 0.36, 1),
    "pink": (0.97, 0.66, 0.74, 1),
    "mint": (0.60, 0.87, 0.66, 1),
    "blue": (0.23, 0.56, 0.90, 1),
    "orange": (0.96, 0.55, 0.20, 1),
    "green": (0.18, 0.62, 0.36, 1),
    "dark": (0.13, 0.13, 0.15, 1),
    "card": (0.76, 0.62, 0.44, 1),
    "skin": (0.90, 0.72, 0.60, 1),
    "paper": (0.93, 0.94, 0.96, 1),
}
PARKED = [0.0, 0.0, -5.0]


class LineError(ValueError):
    """The line description is inconsistent."""


def load_line(path: Path = LINE_PATH) -> dict:
    line = yaml.safe_load(path.read_text())
    validate_line(line)
    return line


def validate_line(line: dict) -> None:
    if line.get("schema_version") != 1:
        raise LineError("manifest/line.yaml: unsupported schema_version")
    machines, instances, fixtures = line["machines"], line["instances"], line["fixtures"]
    for name, machine in machines.items():
        if machine.get("status") not in GEOMETRY_STATUSES:
            raise LineError(f"machine {name}: status must be one of {GEOMETRY_STATUSES}")
        if "model" not in machine and "box" not in machine:
            raise LineError(f"machine {name}: needs a model or a placeholder box")
        if "model" in machine and not machine["model"].startswith("repo:") and len(machine.get("commit", "")) != 40:
            raise LineError(f"machine {name}: an upstream model needs a full pinned commit")
    for name, instance in instances.items():
        if instance["machine"] not in machines:
            raise LineError(f"instance {name}: unknown machine {instance['machine']}")
    if set(instances) & set(fixtures):
        raise LineError("instances and fixtures share a name")
    for name, target in line["targets"].items():
        if target["at"] not in instances and target["at"] not in fixtures:
            raise LineError(f"target {name}: unknown place {target['at']}")
        if set(target) - {"at", "surface", "offset"}:
            raise LineError(f"target {name}: unknown keys {sorted(map(str, set(target) - {'at', 'surface', 'offset'}))}")
    seen = set()
    for step in line["steps"]:
        if step["id"] in seen:
            raise LineError(f"step {step['id']}: duplicate id")
        seen.add(step["id"])
        if step.get("evidence") not in EVIDENCE:
            raise LineError(f"step {step['id']}: evidence must be one of {EVIDENCE}")
        actor = step["actor"]
        if actor not in instances and actor not in fixtures and actor not in NON_ROBOT_ACTORS:
            raise LineError(f"step {step['id']}: unknown actor {actor}")
        for gripper, names in step.get("visits", {}).items():
            grippers = machines[instances[actor]["machine"]].get("grippers", {})
            if gripper not in grippers:
                raise LineError(f"step {step['id']}: {actor} has no gripper {gripper}")
            for target in names:
                if target not in line["targets"]:
                    raise LineError(f"step {step['id']}: unknown target {target}")
    for name, rehearsal in line.get("rehearsals", {}).items():
        if rehearsal["step"] not in seen:
            raise LineError(f"rehearsal {name}: unknown step {rehearsal['step']}")
        for key in ("pick", "place"):
            if rehearsal[key] not in line["targets"]:
                raise LineError(f"rehearsal {name}: unknown target {rehearsal[key]}")


def target_point(line: dict, name: str) -> np.ndarray:
    """World position of a named target, in the line frame."""
    target = line["targets"][name]
    place = target["at"]
    if place in line["fixtures"]:
        base = np.array(line["fixtures"][place]["pos"], dtype=float)
    else:
        instance = line["instances"][place]
        base = np.array(instance["pos"], dtype=float)
        if target.get("surface") == "bed":
            base = base + np.array([0.0, 0.0, line["machines"][instance["machine"]]["bed"]["height"]])
    return base + np.array(target.get("offset", [0, 0, 0]), dtype=float)


def footprints(line: dict) -> dict[str, dict]:
    """Table-fit check for placeholder machines and fixtures (axis-aligned boxes)."""
    half = np.array(line["table"]["size"]) / 2
    result = {}
    boxes = {name: (fixture["pos"], fixture["size"]) for name, fixture in line["fixtures"].items() if not fixture.get("off_table")}
    for name, instance in line["instances"].items():
        machine = line["machines"][instance["machine"]]
        if "box" in machine:
            boxes[name] = (instance["pos"], machine["box"])
    for name, (pos, size) in sorted(boxes.items()):
        overhang = np.abs(np.array(pos[:2])) + np.array(size[:2]) / 2 - half
        result[name] = {"on_table": bool((overhang <= 1e-9).all()), "overhang_m": [round(max(0.0, v), 4) for v in overhang]}
    return result


def model_path(machine: dict) -> Path:
    model = machine["model"]
    if model.startswith("repo:"):
        return REPO_ROOT / model.removeprefix("repo:")
    return UPSTREAM_DIR / model


def missing_models(line: dict) -> list[Path]:
    return sorted({model_path(m) for m in line["machines"].values() if "model" in m and not model_path(m).exists()})


def _yaw_quat(degrees: float) -> list[float]:
    half = math.radians(degrees) / 2
    return [math.cos(half), 0.0, 0.0, math.sin(half)]


def build_spec(line: dict):
    """Compose the whole line as one MuJoCo spec. Requires the upstream cache."""
    import mujoco

    missing = missing_models(line)
    if missing:
        raise FileNotFoundError(f"missing models (run tools/fetch_line_models.py): {[str(p) for p in missing]}")
    spec = mujoco.MjSpec()
    spec.modelname = f"line-{line['layout']}"
    spec.visual.global_.offwidth, spec.visual.global_.offheight = 1920, 1080
    world = spec.worldbody
    spec.visual.headlight.ambient = [0.28, 0.28, 0.28]
    spec.visual.headlight.diffuse = [0.18, 0.18, 0.18]
    spec.visual.headlight.specular = [0.0, 0.0, 0.0]
    spec.visual.rgba.haze = [0.96, 0.94, 0.90, 1]
    spec.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT, rgb1=[0.96, 0.94, 0.90], rgb2=[0.86, 0.90, 0.94], width=256, height=1536)
    sun = world.add_light(pos=[-1.5, -1.5, 3.0], dir=[0.45, 0.5, -1.0], diffuse=[0.42, 0.40, 0.36], specular=[0.1, 0.1, 0.1])
    sun.type = mujoco.mjtLightType.mjLIGHT_DIRECTIONAL
    box, plane = mujoco.mjtGeom.mjGEOM_BOX, mujoco.mjtGeom.mjGEOM_PLANE
    sx, sy = line["table"]["size"]
    thickness = line["table"]["thickness"]
    world.add_geom(name="floor", type=plane, size=[4, 4, 0.1], pos=[0, 0, -0.75], rgba=[0.93, 0.90, 0.85, 1], contype=0, conaffinity=0)
    world.add_geom(name="table", type=box, size=[sx / 2, sy / 2, thickness / 2], pos=[0, 0, -thickness / 2], rgba=[0.86, 0.74, 0.56, 1])
    world.add_geom(name="mat", type=box, size=[sx / 2 - 0.08, sy / 2 - 0.06, 0.001], pos=[0, 0, 0.001], rgba=[0.62, 0.80, 0.70, 1], contype=0, conaffinity=0)

    for name, fixture in line["fixtures"].items():
        fx, fy, fz = fixture["size"]
        body = world.add_body(name=name, pos=fixture["pos"], mocap=fixture["kind"] == "pallet")
        rgba = COLOURS.get(fixture.get("colour"), (0.80, 0.68, 0.48, 1))
        if fixture["kind"] == "jig":
            rgba = COLOURS["blue"]
        elif fixture["kind"] in ("belt", "stand"):
            rgba = (0.25, 0.26, 0.28, 1)
        body.add_geom(type=box, size=[fx / 2, fy / 2, 0.003], pos=[0, 0, 0.003], rgba=rgba, contype=0, conaffinity=0)
        if fixture["kind"] == "tray":
            wall = 0.004
            for dx, dy, hx, hy in ((1, 0, wall / 2, fy / 2), (-1, 0, wall / 2, fy / 2), (0, 1, fx / 2, wall / 2), (0, -1, fx / 2, wall / 2)):
                body.add_geom(type=box, size=[hx, hy, fz / 2], pos=[dx * (fx - wall) / 2, dy * (fy - wall) / 2, fz / 2], rgba=rgba, contype=0, conaffinity=0)
        else:
            body.add_geom(type=box, size=[fx / 2, fy / 2, fz / 2], pos=[0, 0, fz / 2], rgba=rgba, contype=0, conaffinity=0)

    for name, instance in line["instances"].items():
        machine = line["machines"][instance["machine"]]
        quat = _yaw_quat(instance.get("yaw", 0.0))
        if "model" in machine:
            child = mujoco.MjSpec.from_file(str(model_path(machine)))
            for geom in list(child.worldbody.geoms):
                if geom.type == plane:  # each model's own floor would cover the table
                    child.delete(geom)
            for light in list(child.worldbody.lights):
                child.delete(light)
            if "tint" in instance:  # recolour the model's red printed parts
                for geom in child.geoms:
                    if geom.rgba[0] > 0.6 and geom.rgba[1] < 0.4 and geom.rgba[2] < 0.4:
                        geom.rgba = COLOURS[instance["tint"]]
            frame = world.add_frame(pos=instance["pos"], quat=quat)
            with warnings.catch_warnings():
                # Children carry their own solver options; the line keeps MuJoCo's defaults.
                warnings.simplefilter("ignore", UserWarning)
                spec.attach(child, prefix=f"{name}/", frame=frame)
            continue
        bx, by, bz = machine["box"]
        bed = machine["bed"]
        body = world.add_body(name=name, pos=instance["pos"], quat=quat)
        post, dark = 0.01, [0.12, 0.12, 0.13, 1]
        for dx in (-1, 1):
            for dy in (-1, 1):
                body.add_geom(type=box, size=[post, post, bz / 2], pos=[dx * (bx / 2 - post), dy * (by / 2 - post), bz / 2], rgba=dark, contype=0, conaffinity=0)
        for z in (post, bz - post):
            for dy in (-1, 1):
                body.add_geom(type=box, size=[bx / 2, post, post], pos=[0, dy * (by / 2 - post), z], rgba=dark, contype=0, conaffinity=0)
            for dx in (-1, 1):
                body.add_geom(type=box, size=[post, by / 2, post], pos=[dx * (bx / 2 - post), 0, z], rgba=dark, contype=0, conaffinity=0)
        body.add_geom(name=f"{name}/bed", type=box, size=[bed["size"][0] / 2, bed["size"][1] / 2, 0.004], pos=[0, 0, bed["height"] - 0.004], rgba=[0.2, 0.2, 0.22, 1], contype=0, conaffinity=0)

    for name, rehearsal in line.get("rehearsals", {}).items():
        item = rehearsal["item"]
        body = world.add_body(name=f"item/{name}", mocap=True, pos=target_point(line, rehearsal["pick"]).tolist())
        body.add_geom(type=box, size=[v / 2 for v in item["size"]], rgba=COLOURS.get(item.get("colour"), (0.5, 0.5, 0.5, 1)), contype=0, conaffinity=0)
    for name, prop in line.get("props", {}).items():
        body = world.add_body(name=f"prop/{name}", mocap=True, pos=PARKED)
        body.add_geom(name=f"prop/{name}", type=box, size=[v / 2 for v in prop["size"]], rgba=COLOURS[prop["colour"]], contype=0, conaffinity=0)
    return spec


def build_model(line: dict):
    import mujoco

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        model = build_spec(line).compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    return model, data


def gripper_site(line: dict, instance: str, gripper: str) -> str:
    machine = line["machines"][line["instances"][instance]["machine"]]
    return f"{instance}/{machine['grippers'][gripper]}"


def chain_joints(model, site_id: int) -> list[int]:
    """Hinge and slide joints between the world and a site's body."""
    import mujoco

    joints, body = [], model.site_bodyid[site_id]
    while body > 0:
        for j in range(model.body_jntadr[body], model.body_jntadr[body] + model.body_jntnum[body]):
            if model.jnt_type[j] in (mujoco.mjtJoint.mjJNT_HINGE, mujoco.mjtJoint.mjJNT_SLIDE):
                joints.append(j)
        body = model.body_parentid[body]
    return sorted(joints)


def solve_reach(model, data, site: str, point: np.ndarray, *, tolerance: float, restarts: int, rng, start: np.ndarray | None = None):
    """Position-only damped least-squares IK. Returns (error_m, qpos of the chain, joints)."""
    import mujoco

    site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, site)
    if site_id < 0:
        raise LineError(f"model has no site {site}")
    joints = chain_joints(model, site_id)
    qadr, dadr = model.jnt_qposadr[joints], model.jnt_dofadr[joints]
    limited = model.jnt_limited[joints].astype(bool)
    low = np.where(limited, model.jnt_range[joints, 0], -math.pi)
    high = np.where(limited, model.jnt_range[joints, 1], math.pi)
    jacp = np.zeros((3, model.nv))
    saved = data.qpos.copy()
    best_error, best_q = math.inf, None
    for attempt in range(restarts + 1):
        if attempt == 0:
            q = np.clip(saved[qadr] if start is None else start, low, high)
        else:
            q = rng.uniform(low, high)
        for _ in range(200):
            data.qpos[qadr] = q
            mujoco.mj_kinematics(model, data)
            mujoco.mj_comPos(model, data)
            error = point - data.site_xpos[site_id]
            distance = float(np.linalg.norm(error))
            if distance < tolerance / 5:
                break
            mujoco.mj_jacSite(model, data, jacp, None, site_id)
            jac = jacp[:, dadr]
            step = jac.T @ np.linalg.solve(jac @ jac.T + 1e-4 * np.eye(3), error)
            norm = float(np.linalg.norm(step))
            if norm > 0.3:
                step *= 0.3 / norm
            q = np.clip(q + step, low, high)
        if distance < best_error:
            best_error, best_q = distance, q.copy()
        if best_error <= tolerance:
            break
    data.qpos[:] = saved
    mujoco.mj_forward(model, data)
    return best_error, best_q, joints


def reach_results(line: dict, model, data) -> list[dict]:
    settings = line["reach"]
    rng = np.random.default_rng(settings["seed"])
    results = []
    for step in line["steps"]:
        for gripper, names in step.get("visits", {}).items():
            site = gripper_site(line, step["actor"], gripper)
            base = np.array(line["instances"][step["actor"]]["pos"], dtype=float)
            for name in names:
                point = target_point(line, name)
                error, _, _ = solve_reach(model, data, site, point, tolerance=settings["tolerance_m"], restarts=settings["restarts"], rng=rng)
                results.append(
                    {
                        "step": step["id"],
                        "actor": step["actor"],
                        "gripper": gripper,
                        "target": name,
                        "point_m": [round(float(v), 4) for v in point],
                        "horizontal_distance_from_base_m": round(float(np.linalg.norm(point[:2] - base[:2])), 3),
                        "residual_mm": round(error * 1000),
                        "reachable": bool(error <= settings["tolerance_m"]),
                    }
                )
    return results


def rehearsal_plan(line: dict, model, data, name: str) -> dict:
    """Joint-space waypoints for one scripted rehearsal, with their IK residuals."""
    settings = line["reach"]
    rehearsal = line["rehearsals"][name]
    site = gripper_site(line, rehearsal["actor"], rehearsal["gripper"])
    pick, place = target_point(line, rehearsal["pick"]), target_point(line, rehearsal["place"])
    lift = np.array([0.0, 0.0, rehearsal["lift_m"]])
    labels = ["above_pick", "pick", "above_pick", "above_place", "place", "above_place"]
    points = [pick + lift, pick, pick + lift, place + lift, place, place + lift]
    rng = np.random.default_rng(settings["seed"])
    waypoints, previous = [], None
    for label, point in zip(labels, points):
        error, q, joints = solve_reach(model, data, site, point, tolerance=settings["tolerance_m"], restarts=settings["restarts"], rng=rng, start=previous)
        previous = q
        waypoints.append({"label": label, "point_m": [round(float(v), 4) for v in point], "residual_mm": round(error * 1000, 1), "q": q, "joints": joints})
    return {"name": name, "site": site, "waypoints": waypoints, "pick": pick, "place": place, "seconds": rehearsal["seconds"]}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_record(line: dict) -> dict:
    model, data = build_model(line)
    reach = reach_results(line, model, data)
    rehearsals = {}
    for name in line.get("rehearsals", {}):
        plan = rehearsal_plan(line, model, data, name)
        worst = max(w["residual_mm"] for w in plan["waypoints"])
        rehearsals[name] = {
            "waypoints": [{"label": w["label"], "point_m": w["point_m"], "residual_mm": w["residual_mm"]} for w in plan["waypoints"]],
            "worst_residual_mm": worst,
            "feasible": bool(worst <= line["reach"]["tolerance_m"] * 1000),
        }
    fit = footprints(line)
    unreachable = [f"{r['step']}: {r['actor']} {r['gripper']} cannot reach {r['target']} (short by {r['residual_mm']} mm)" for r in reach if not r["reachable"]]
    off_table = [f"{name} overhangs the table" for name, f in fit.items() if not f["on_table"]]
    return {
        "schema": RECORD_SCHEMA,
        "status": RECORD_STATUS,
        "layout": line["layout"],
        "limits": line["reach"]["note"].strip(),
        "inputs": {
            "manifest/line.yaml": _sha256(LINE_PATH),
            "models": {name: m.get("commit", _sha256(model_path(m))) for name, m in sorted(line["machines"].items()) if "model" in m},
        },
        "model": {"bodies": int(model.nbody), "joints": int(model.njnt), "actuators": int(model.nu), "meshes": int(model.nmesh)},
        "table_fit": fit,
        "reach": reach,
        "rehearsals": rehearsals,
        "findings": off_table + unreachable,
    }


def record_path(line: dict) -> Path:
    return LINE_DIR / line["layout"] / RECORD_NAME


def render(line: dict, out: Path, fps: int = 30) -> list[Path]:
    """Offscreen stills of the layout and a video of each rehearsal."""
    import cv2
    import mujoco

    out.mkdir(parents=True, exist_ok=True)
    model, data = build_model(line)
    renderer = mujoco.Renderer(model, 720, 1280)
    camera = mujoco.MjvCamera()
    written = []

    def shot(lookat, distance, azimuth, elevation):
        camera.lookat[:] = lookat
        camera.distance, camera.azimuth, camera.elevation = distance, azimuth, elevation
        renderer.update_scene(data, camera)
        return cv2.cvtColor(renderer.render(), cv2.COLOR_RGB2BGR)

    views = {
        "overview": ([0.0, 0.0, 0.1], 2.6, 90, -32),
        "printers": ([-0.52, 0.05, 0.12], 1.3, 70, -25),
        "kitting": ([0.25, -0.15, 0.08], 0.95, 110, -32),
        "assembly": ([0.66, 0.25, 0.05], 1.7, 125, -20),
    }
    for name, view in views.items():
        path = out / f"{name}.jpg"
        cv2.imwrite(str(path), shot(*view), [cv2.IMWRITE_JPEG_QUALITY, 88])
        written.append(path)

    for name in line.get("rehearsals", {}):
        plan = rehearsal_plan(line, model, data, name)
        site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, plan["site"])
        mocap = model.body_mocapid[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"item/{name}")]
        joints = plan["waypoints"][0]["joints"]
        qadr = model.jnt_qposadr[joints]
        home = data.qpos[qadr].copy()
        keys = [home] + [w["q"] for w in plan["waypoints"]] + [home]
        frames_per = max(2, int(plan["seconds"] * fps / (len(keys) - 1)))
        path = out / f"{name}.mp4"
        if shutil.which("ffmpeg") is None:
            print(f"skipped {path.name}: ffmpeg is not installed", file=sys.stderr)
            continue
        encoder = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1280x720", "-r", str(fps), "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)],
            stdin=subprocess.PIPE,
        )
        for segment in range(len(keys) - 1):
            for frame in range(frames_per):
                s = frame / frames_per
                s = s * s * (3 - 2 * s)
                data.qpos[qadr] = (1 - s) * keys[segment] + s * keys[segment + 1]
                mujoco.mj_forward(model, data)
                held = 2 <= segment + (1 if s >= 1 else 0) and segment < 5
                if segment < 2:
                    data.mocap_pos[mocap] = plan["pick"]
                elif held:
                    data.mocap_pos[mocap] = data.site_xpos[site_id]
                else:
                    data.mocap_pos[mocap] = plan["place"]
                mujoco.mj_forward(model, data)
                encoder.stdin.write(shot(*views["kitting"]).tobytes())
        encoder.stdin.close()
        encoder.wait()
        data.qpos[qadr] = home
        mujoco.mj_forward(model, data)
        written.append(path)
    renderer.close()
    page = out / "index.html"
    page.write_text(report_html(line, build_record(line), [p.name for p in written]))
    written.append(page)
    return written


def report_html(line: dict, record: dict, media: list[str]) -> str:
    """A small phone-friendly page: stills, the rehearsal video and the findings."""
    from html import escape

    reachable = sum(r["reachable"] for r in record["reach"])
    actors = {s["id"]: s for s in line["steps"]}
    rows = "".join(
        f"<tr class=\"{'ok' if r['reachable'] else 'bad'}\"><td>{escape(r['step'])}</td><td>{escape(r['actor'])} {escape(r['gripper'])}</td>"
        f"<td>{escape(r['target'])}</td><td>{'reaches' if r['reachable'] else 'short by ' + str(round(r['residual_mm'])) + ' mm'}</td></tr>"
        for r in record["reach"]
    )
    steps = "".join(
        f"<tr><td>{i}</td><td>{escape(s['actor'])}</td><td>{escape(s['does'])}</td><td><span class=\"tag {s['evidence']}\">{s['evidence'].replace('-', ' ')}</span></td></tr>"
        for i, s in enumerate(actors.values(), 1)
    )
    machines = "".join(
        f"<li><b>{escape(m['name'])}</b>: {m['status'].replace('-', ' ')}. <a href=\"{escape(m['project'])}\">{escape(m['project'].removeprefix('https://github.com/'))}</a>, {escape(m['licence'])}."
        f"{' ' + escape(' '.join(m['note'].split())) if 'note' in m else ''}</li>"
        for m in line["machines"].values()
    )
    stills = "".join(f"<figure><img src=\"{name}\" alt=\"{name[:-4]} view\"><figcaption>{name[:-4].capitalize()}</figcaption></figure>" for name in media if name.endswith(".jpg"))
    videos = "".join(f"<figure><video src=\"{name}\" controls loop muted playsinline></video><figcaption>Rehearsal: {name[:-4].replace('_', ' ')} (scripted motion, no grasp physics)</figcaption></figure>" for name in media if name.endswith(".mp4"))
    findings = "".join(f"<li>{escape(f)}</li>" for f in record["findings"]) or "<li>None.</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache"><title>Line twin {escape(line['layout'])}</title>
<style>
body{{margin:0;background:#fbf7ef;color:#2b2a33;font:16px/1.55 ui-rounded,system-ui,sans-serif}}
main{{max-width:860px;margin:0 auto;padding:24px 16px 60px}}h1{{color:#3a8fe6;font-size:clamp(28px,8vw,44px);margin:0 0 6px;line-height:1.1}}
h2{{font-size:21px;margin:34px 0 8px}}figure{{margin:0 0 14px;background:#fff;border:1px solid #e9e1d2;border-radius:14px;overflow:hidden}}
img,video{{display:block;width:100%}}figcaption{{padding:8px 12px;font-size:13px;color:#6d6a75}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e9e1d2;font-size:14px}}td,th{{text-align:left;padding:7px 9px;border-bottom:1px solid #e9e1d2;vertical-align:top}}
tr.bad td:last-child{{color:#c0392b;font-weight:700}}tr.ok td:last-child{{color:#2f9e6b}}.note{{color:#6d6a75;font-size:14px}}
.tag{{display:inline-block;padding:1px 8px;border-radius:999px;color:#fff;font-size:12px;font-weight:700;white-space:nowrap}}
.works-today{{background:#2f9e6b}}.demo-level{{background:#d98a1c}}.concept{{background:#8b5fd6}}.big{{font-size:20px}}li{{margin-bottom:6px}}
</style></head><body><main>
<p class="note">Digital twin · layout {escape(line['layout'])} · simulated geometry, nothing measured</p>
<h1>Sesame line twin</h1>
<p class="big"><b>{reachable} of {len(record['reach'])}</b> gripper targets are reachable in this layout.</p>
{stills}{videos}
<p><a href="previs.html">Watch the trailer pre-visualisation</a> (if it has been rendered into this folder).</p>
<h2>Findings</h2><ul>{findings}</ul>
<h2>Reach, target by target</h2>
<table><thead><tr><th>Step</th><th>Gripper</th><th>Target</th><th>Result</th></tr></thead><tbody>{rows}</tbody></table>
<p class="note">{escape(record['limits'])}</p>
<h2>The loop</h2>
<table><thead><tr><th></th><th>Who</th><th>What</th><th>In practice</th></tr></thead><tbody>{steps}</tbody></table>
<h2>Machines</h2><ul>{machines}</ul>
<p class="note">Model: {record['model']['bodies']} bodies, {record['model']['joints']} joints, {record['model']['meshes']} meshes, composed in MuJoCo from manifest/line.yaml.</p>
</main></body></html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--render", type=Path)
    args = parser.parse_args(argv)
    line = load_line()
    if args.render:
        for path in render(line, args.render):
            print(path)
        return 0
    record = build_record(line)
    text = json.dumps(record, indent=2) + "\n"
    path = record_path(line)
    if args.summary:
        reachable = sum(r["reachable"] for r in record["reach"])
        print(f"{line['layout']}: {reachable}/{len(record['reach'])} gripper targets reachable")
        for finding in record["findings"]:
            print(f"  - {finding}")
        return 0
    if args.check:
        if not path.exists() or path.read_text() != text:
            print(f"stale: {path.relative_to(REPO_ROOT)} (run `uv run python -m sim.line`)", file=sys.stderr)
            return 1
        print(f"current: {path.relative_to(REPO_ROOT)}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
