"""Pre-visualisation of the trailer inside the line twin.

Plays manifest/line_previs.yaml in the model built from manifest/line.yaml and
cuts the shots into one video. It is an animatic: arms follow inverse-kinematics
waypoints in joint space, loose objects follow written paths, and each Sesame
shows a named pose or plays the stock walk kinematically. Nothing is simulated
dynamically, so it shows staging, reach and timing, not that a step would work.

Usage:
  uv run python -m sim.line_previs --summary        shots, length and worst waypoint error
  uv run python -m sim.line_previs --render DIR     write DIR/previs.mp4 and DIR/previs.html
  uv run python -m sim.line_previs --render DIR --shot 8     one shot only
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

from sim import line as line_twin
from sim.manifest import REPO_ROOT, load_manifest
from sim.motions import flatten, load_motions

PREVIS_PATH = REPO_ROOT / "manifest" / "line_previs.yaml"
EVENT_TYPES = ("goto", "pick_place", "prop", "grow", "pallet", "sesame")
MAX_SECONDS = 60.0
STATUS_COLOURS = {"works-today": (107, 158, 47), "demo-level": (28, 138, 217), "concept": (214, 95, 139)}  # BGR


def load_previs(line: dict, path: Path = PREVIS_PATH) -> dict:
    previs = yaml.safe_load(path.read_text())
    validate_previs(line, previs)
    return previs


def validate_previs(line: dict, previs: dict) -> None:
    error = line_twin.LineError
    if previs.get("schema_version") != 1:
        raise error("line_previs.yaml: unsupported schema_version")
    props, targets = line.get("props", {}), line["targets"]
    sesames = {n for n, i in line["instances"].items() if i["machine"] == "sesame"}
    total = 0.0
    for shot in previs["shots"]:
        where = f"shot {shot.get('id')}"
        if shot.get("status") not in line_twin.EVIDENCE:
            raise error(f"{where}: unknown status")
        if any(len(shot["camera"][key]) != 6 for key in ("from", "to")):
            raise error(f"{where}: a camera needs six numbers")
        total += shot["seconds"]
        for event in shot.get("events", []):
            kind = event.get("type")
            if kind not in EVENT_TYPES:
                raise error(f"{where}: unknown event type {kind}")
            if not 0 <= event["start"] <= event["end"] <= shot["seconds"]:
                raise error(f"{where}: {kind} event times lie outside the shot")
            points = list(event.get("points", [])) + [event[k] for k in ("pick", "place") if k in event]
            for point in points:
                if isinstance(point, str) and point not in targets:
                    raise error(f"{where}: unknown target {point}")
            if kind in ("goto", "pick_place"):
                machine = line["machines"][line["instances"][event["actor"]]["machine"]]
                if event["gripper"] not in machine.get("grippers", {}):
                    raise error(f"{where}: {event['actor']} has no gripper {event['gripper']}")
            names = [event[k] for k in ("name", "item") if k in event] + list(event.get("carries", []))
            if any(name not in props for name in names):
                raise error(f"{where}: unknown prop in {names}")
            if kind == "sesame" and event["who"] not in sesames:
                raise error(f"{where}: unknown Sesame {event['who']}")
    if total > MAX_SECONDS:
        raise error(f"the pre-visualisation runs {total:g} s; the limit is {MAX_SECONDS:g} s")


def _point(line: dict, value) -> np.ndarray:
    return line_twin.target_point(line, value) if isinstance(value, str) else np.array(value, dtype=float)


def _smooth(s: float) -> float:
    s = min(1.0, max(0.0, s))
    return s * s * (3 - 2 * s)


def _along(points: list[np.ndarray], s: float) -> np.ndarray:
    """Position at fraction s of a path, with eased, equally timed segments."""
    if len(points) == 1:
        return points[0]
    scaled = min(1.0, max(0.0, s)) * (len(points) - 1)
    index = min(int(scaled), len(points) - 2)
    return points[index] + _smooth(scaled - index) * (points[index + 1] - points[index])


class Stage:
    """The compiled model plus everything needed to pose it for one instant of a shot."""

    def __init__(self, line: dict, previs: dict):
        import mujoco

        self.mj, self.line, self.previs = mujoco, line, previs
        self.model, self.data = line_twin.build_model(line)
        self.home = self.data.qpos.copy()
        self.rng = np.random.default_rng(line["reach"]["seed"])
        self.manifest = load_manifest()
        poses = self.manifest.raw["poses"]
        self.walk = flatten(load_motions()["motions"]["walk"], poses)
        self.prop_mocap, self.prop_geom, self.prop_size = {}, {}, {}
        for name in line.get("props", {}):
            body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, f"prop/{name}")
            geom = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, f"prop/{name}")
            self.prop_mocap[name], self.prop_geom[name] = self.model.body_mocapid[body], geom
            self.prop_size[name] = self.model.geom_size[geom].copy()
        pallet = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "pallet")
        self.pallet_mocap, self.pallet_home = self.model.body_mocapid[pallet], np.array(line["fixtures"]["pallet"]["pos"], dtype=float)
        self.sesames = {n: i for n, i in line["instances"].items() if i["machine"] == "sesame"}
        self.plans = {shot["id"]: self._plan(shot) for shot in previs["shots"]}

    # -- arms ---------------------------------------------------------------
    def _plan(self, shot: dict) -> list[dict]:
        """Joint keyframes for every arm event of a shot, with waypoint errors."""
        settings, last = self.line["reach"], {}
        plans = []
        for event in shot.get("events", []):
            if event["type"] not in ("goto", "pick_place"):
                plans.append(None)
                continue
            site = line_twin.gripper_site(self.line, event["actor"], event["gripper"])
            if event["type"] == "goto":
                points = [_point(self.line, p) for p in event["points"]]
            else:
                pick, place = _point(self.line, event["pick"]), _point(self.line, event["place"])
                lift = np.array([0.0, 0.0, event.get("lift", 0.07)])
                points = [pick + lift, pick, pick + lift, place + lift, place, place + lift]
            keys, errors, joints = [], [], None
            previous = last.get(site)
            for point in points:
                error, q, joints = line_twin.solve_reach(self.model, self.data, site, point, tolerance=settings["tolerance_m"], restarts=settings["restarts"], rng=self.rng, start=previous)
                keys.append(q)
                errors.append(round(error * 1000, 1))
                previous = q
            qadr = self.model.jnt_qposadr[joints]
            start = last.get(site, self.home[qadr])
            last[site] = keys[-1]
            plans.append({"site": site, "qadr": qadr, "keys": [np.array(start)] + keys, "errors_mm": errors, "points": points})
        return plans

    def worst_error_mm(self) -> float:
        return max((e for plans in self.plans.values() for plan in plans if plan for e in plan["errors_mm"]), default=0.0)

    # -- Sesame -------------------------------------------------------------
    def _pose_sesame(self, who: str, joints_rad: dict[str, float], xy, yaw_deg: float, lift: float = 0.0) -> None:
        mj, model, data = self.mj, self.model, self.data
        root = model.jnt_qposadr[mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, f"{who}/root")]
        for name, value in joints_rad.items():
            data.qpos[model.jnt_qposadr[mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, f"{who}/{name}")]] = value
        # A free joint's coordinates are world coordinates, whatever frame the model was attached in.
        half = math.radians(yaw_deg) / 2
        data.qpos[root : root + 3] = [xy[0], xy[1], 0.0]
        data.qpos[root + 3 : root + 7] = [math.cos(half), 0.0, 0.0, math.sin(half)]
        mj.mj_kinematics(model, data)
        paws = [data.site_xpos[mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, f"{who}/{leg}_paw")][2] for leg in ("front_left", "front_right", "back_left", "back_right")]
        data.qpos[root + 2] += 0.004 + lift - min(paws)

    def _hide_sesame(self, who: str) -> None:
        mj, model = self.mj, self.model
        root = model.jnt_qposadr[mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, f"{who}/root")]
        self.data.qpos[root + 2] = -5.0

    def _walk_pose(self, seconds: float) -> dict[str, float]:
        """Stock walk at a time since it began: targets interpolated between its frames."""
        period = self.walk[-1].time_ms
        t = (seconds * 1000.0) % period if period else 0.0
        state = dict(self.manifest.raw["poses"]["stand"])
        before, after, t0, t1 = dict(state), dict(state), 0.0, period
        for event in self.walk:
            if event.time_ms <= t:
                state.update(event.targets_deg)
                before, t0 = dict(state), event.time_ms
            else:
                after = dict(state)
                after.update(event.targets_deg)
                t1 = event.time_ms
                break
        else:
            after = dict(state)
        s = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
        blended = {name: before[name] + s * (after[name] - before[name]) for name in before}
        return {j.name: self.manifest.to_internal(j, blended[j.name]) for j in self.manifest.joints}

    # -- one instant ----------------------------------------------------------
    def pose(self, shot: dict, t: float) -> None:
        mj, model, data, line = self.mj, self.model, self.data, self.line
        data.qpos[:] = self.home
        positions: dict[str, np.ndarray] = {}
        carried: dict[str, str] = {}
        pallet = self.pallet_home.copy()
        for name, geom in self.prop_geom.items():
            model.geom_size[geom] = self.prop_size[name]
        stand = self.manifest.pose_internal("stand")
        for who, instance in self.sesames.items():
            if who.startswith("elder"):
                self._pose_sesame(who, stand, instance["pos"][:2], instance.get("yaw", 0.0))
            else:
                self._hide_sesame(who)
        for event, plan in zip(shot.get("events", []), self.plans[shot["id"]]):
            kind, start, end = event["type"], event["start"], event["end"]
            s = 1.0 if end <= start else (t - start) / (end - start)
            if kind in ("goto", "pick_place"):
                keys = plan["keys"]
                scaled = min(1.0, max(0.0, s)) * (len(keys) - 1)
                index = min(int(scaled), len(keys) - 2)
                data.qpos[plan["qadr"]] = keys[index] + _smooth(scaled - index) * (keys[index + 1] - keys[index])
                if kind == "pick_place":
                    item = event["item"]
                    if scaled < 2:
                        positions.setdefault(item, np.array(event["from"], dtype=float) if "from" in event else plan["points"][1])
                    elif scaled < 5:
                        carried[item] = plan["site"]
                    else:
                        carried.pop(item, None)
                        positions[item] = np.array(event["rest"], dtype=float) if "rest" in event else plan["points"][4]
            elif kind == "prop" and t >= start:
                positions[event["name"]] = _along([_point(line, p) for p in event["points"]], s)
            elif kind == "grow" and t >= start:
                size = np.array(event["size_from"]) + _smooth(s) * (np.array(event["size_to"]) - np.array(event["size_from"]))
                model.geom_size[self.prop_geom[event["name"]]] = size / 2
                positions[event["name"]] = np.array(event["at"], dtype=float) + [0, 0, size[2] / 2]
            elif kind == "pallet":
                points = [_point(line, p) for p in event["points"]]
                pallet = _along(points, s) if t >= start else points[0]
                for name in event.get("carries", []):
                    if name in positions:
                        positions[name] = positions[name] + (pallet - points[0])
            elif kind == "sesame" and start <= t <= end + 1e-9:
                if "walk" in event:
                    a, b = (np.array(p, dtype=float) for p in event["walk"])
                    self._pose_sesame(event["who"], self._walk_pose(t - start), a + min(1.0, max(0.0, s)) * (b - a), event["yaw"])
                else:
                    self._pose_sesame(event["who"], self.manifest.pose_internal(event["pose"]), event["at"][:2], event["yaw"], lift=event["at"][2])
        data.mocap_pos[self.pallet_mocap] = pallet
        for name, mocap in self.prop_mocap.items():
            data.mocap_pos[mocap] = positions.get(name, line_twin.PARKED)
        mj.mj_forward(model, data)
        if carried:
            for name, site in carried.items():
                site_id = mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, site)
                data.mocap_pos[self.prop_mocap[name]] = data.site_xpos[site_id] - [0, 0, self.prop_size[name][2]]
            mj.mj_forward(model, data)


def _tilt_shift(cv2, frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(frame, (0, 0), 5)
    return (frame * (1 - mask) + blurred * mask).astype(np.uint8)


def render(line: dict, previs: dict, out: Path, only: int | None = None) -> Path:
    import cv2

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to write the pre-visualisation video")
    out.mkdir(parents=True, exist_ok=True)
    stage = Stage(line, previs)
    mj = stage.mj
    width, height = previs["size"]
    fps = previs["fps"]
    renderer = mj.Renderer(stage.model, height, width)
    camera = mj.MjvCamera()
    rows = np.linspace(0, 1, height)[:, None, None]
    mask = np.clip((np.abs(rows - 0.54) - 0.22) / 0.40, 0, 1) if previs.get("tilt_shift") else None
    path = out / ("previs.mp4" if only is None else f"previs-shot-{only:02d}.mp4")
    encoder = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)],
        stdin=subprocess.PIPE,
    )
    clock = 0.0
    for shot in previs["shots"]:
        frames = round(shot["seconds"] * fps)
        if only is None or shot["id"] == only:
            a, b = np.array(shot["camera"]["from"], dtype=float), np.array(shot["camera"]["to"], dtype=float)
            label = f"{shot['id']:02d}  {shot['title']}"
            for frame in range(frames):
                t = frame / fps
                stage.pose(shot, t)
                view = a + _smooth(frame / max(1, frames - 1)) * (b - a)
                camera.lookat[:] = view[:3]
                camera.distance, camera.azimuth, camera.elevation = view[3], view[4], view[5]
                renderer.update_scene(stage.data, camera)
                image = cv2.cvtColor(renderer.render(), cv2.COLOR_RGB2BGR)
                if mask is not None:
                    image = _tilt_shift(cv2, image, mask)
                cv2.rectangle(image, (0, height - 54), (width, height), (40, 38, 36), -1)
                cv2.putText(image, label, (22, height - 19), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
                tag = shot["status"].replace("-", " ")
                cv2.putText(image, tag, (width - 420, height - 19), cv2.FONT_HERSHEY_SIMPLEX, 0.75, STATUS_COLOURS[shot["status"]], 2, cv2.LINE_AA)
                total = clock + t
                cv2.putText(image, f"0:{int(total):02d}", (width - 110, height - 19), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (210, 210, 210), 2, cv2.LINE_AA)
                encoder.stdin.write(image.tobytes())
        clock += shot["seconds"]
    encoder.stdin.close()
    encoder.wait()
    renderer.close()
    if only is None:
        (out / "previs.html").write_text(previs_html(line, previs, summary(line, previs, stage)))
    return path


def previs_html(line: dict, previs: dict, result: dict) -> str:
    from html import escape

    rows, clock = "", 0
    for shot in previs["shots"]:
        rows += (
            f"<tr><td><button data-t=\"{clock}\">{shot['id']:02d}</button></td><td>0:{clock:02d}</td><td>{escape(shot['title'])}</td>"
            f"<td>{shot['seconds']:g} s</td><td><span class=\"tag {shot['status']}\">{shot['status'].replace('-', ' ')}</span></td></tr>"
        )
        clock += shot["seconds"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache"><title>Sesame makes Sesame: pre-visualisation</title>
<style>
body{{margin:0;background:#fbf7ef;color:#2b2a33;font:16px/1.55 ui-rounded,system-ui,sans-serif}}
main{{max-width:860px;margin:0 auto;padding:24px 16px 60px}}h1{{color:#3a8fe6;font-size:clamp(28px,8vw,44px);margin:0 0 6px;line-height:1.1}}
h2{{font-size:21px;margin:30px 0 8px}}video{{display:block;width:100%;border-radius:14px;background:#000;position:sticky;top:0;z-index:2}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e9e1d2;font-size:14px}}td,th{{text-align:left;padding:7px 9px;border-bottom:1px solid #e9e1d2}}
button{{border:0;background:#3a8fe6;color:#fff;border-radius:999px;padding:6px 12px;font:inherit;font-weight:700}}.note{{color:#6d6a75;font-size:14px}}
.tag{{display:inline-block;padding:1px 8px;border-radius:999px;color:#fff;font-size:12px;font-weight:700;white-space:nowrap}}
.works-today{{background:#2f9e6b}}.demo-level{{background:#d98a1c}}.concept{{background:#8b5fd6}}li{{margin-bottom:6px}}
</style></head><body><main>
<p class="note">Pre-visualisation · line twin {escape(line['layout'])} · {result['seconds']:g} s · {len(previs['shots'])} shots</p>
<h1>Sesame makes Sesame</h1>
<video id="v" src="previs.mp4" controls playsinline muted></video>
<h2>Shots</h2>
<p class="note">Tap a number to jump to that shot.</p>
<table><thead><tr><th></th><th>At</th><th>Shot</th><th>Length</th><th>In practice</th></tr></thead><tbody>{rows}</tbody></table>
<h2>What this is</h2>
<ul>
<li>An animatic played inside the digital twin: the real published arm and robot models at true scale, in the layout the twin found workable.</li>
<li>Arms move through inverse-kinematics waypoints; the worst waypoint error is {result['worst_waypoint_error_mm']} mm.</li>
<li>Loose objects, hands, screens and printers are plain boxes on written paths. Nothing is simulated dynamically, so this shows staging, reach and timing only.</li>
<li>The Sesame plays its stock walk as joint angles while sliding along a path; its feet are not driving it.</li>
</ul>
<p><a href="./">Line twin findings</a></p>
</main><script>
const v=document.getElementById('v');
document.querySelectorAll('button[data-t]').forEach(b=>b.addEventListener('click',()=>{{v.currentTime=Number(b.dataset.t)+0.05;v.play();}}));
</script></body></html>
"""


def summary(line: dict, previs: dict, stage: Stage | None = None) -> dict:
    stage = stage or Stage(line, previs)
    shots = []
    for shot in previs["shots"]:
        errors = [e for plan in stage.plans[shot["id"]] if plan for e in plan["errors_mm"]]
        shots.append({"id": shot["id"], "title": shot["title"], "seconds": shot["seconds"], "status": shot["status"], "arm_waypoints": len(errors), "worst_waypoint_error_mm": max(errors, default=0.0)})
    return {"layout": line["layout"], "seconds": sum(s["seconds"] for s in previs["shots"]), "shots": shots, "worst_waypoint_error_mm": stage.worst_error_mm()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--render", type=Path)
    parser.add_argument("--shot", type=int)
    args = parser.parse_args(argv)
    line = line_twin.load_line()
    previs = load_previs(line)
    if args.render:
        print(render(line, previs, args.render, args.shot))
        return 0
    result = summary(line, previs)
    print(f"{result['layout']}: {len(result['shots'])} shots, {result['seconds']:g} s, worst arm waypoint error {result['worst_waypoint_error_mm']} mm")
    for shot in result["shots"]:
        print(f"  {shot['id']:02d} {shot['title']:<18} {shot['seconds']:>3g} s  {shot['status']:<12} {shot['arm_waypoints']:>2} waypoints, worst {shot['worst_waypoint_error_mm']} mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
