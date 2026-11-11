"""High-level steps: add a marker track to a log, fit logs, write the report, demo."""

from __future__ import annotations

import json
from pathlib import Path

import mujoco
import yaml

from sim import twin
from sim.real2sim import fit as fitting
from sim.real2sim import marker, report, runlog, synthetic

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = twin.model_path()  # the course robot's generated twin (manifest/twin.yaml default design)
MEASUREMENTS_PATH = ROOT / "reference" / "real2sim" / "measurements.yaml"
SHEET_PATH = ROOT / "reference" / "real2sim" / "marker-sheet.pdf"


def load_model(path: Path | str = MODEL_PATH) -> mujoco.MjModel:
    return mujoco.MjModel.from_xml_path(str(path))


def load_measurements(path: Path | str = MEASUREMENTS_PATH) -> dict:
    path = Path(path)
    return yaml.safe_load(path.read_text()) if path.exists() else {}


def rest_height(model: mujoco.MjModel) -> float:
    """Torso-centre height of the model lying in its rest pose (after settling)."""
    data = mujoco.MjData(model)
    mujoco.mj_step(model, data, 500)
    return float(data.qpos[fitting.ModelView(model).root_qpos + 2])


def marker_origin(model: mujoco.MjModel, measurements: dict) -> tuple[list[float], str]:
    """Marker centre in the torso frame: measured height if recorded, else the model's lid height."""
    height = (measurements.get("marker") or {}).get("centre_height_above_floor_at_rest_mm")
    if height is None:
        return list(synthetic.MARKER_ORIGIN_IN_TORSO_M), "model lid height (unmeasured)"
    return [0.0, 0.0, height / 1000.0 - rest_height(model)], "measured marker height above the floor"


def add_track(log_path: Path | str, track: marker.Track, origin: list[float], origin_source: str,
              out: Path | str | None = None) -> Path:
    """Write the tracked torso poses into a run log (replacing any earlier track)."""
    if not len(track.times):
        raise ValueError("the head marker was not found in any frame")
    channel = runlog.torso_pose_channel(
        frame=track.frame, frame_definition=track.frame_definition, marker_origin_in_torso_m=origin,
        marker_origin_source=origin_source, camera=track.camera.to_json(),
        tracking={"frames_total": track.frames_total, "frames_with_marker": len(track.times),
                  "median_reprojection_px": round(float(sorted(track.reprojection_px)[len(track.times) // 2]), 3),
                  "notes": track.notes})
    records = runlog.pose_records(track.times, track.positions, track.quaternions, clock="video")
    return runlog.with_torso_poses(log_path, channel, records,
                                   "seconds from the start of the video (container timestamps)", out)


def fixed_from_measurements(model: mujoco.MjModel, measurements: dict) -> dict[str, tuple[float, str]]:
    """Directly measured quantities that replace fitted parameters (currently the total mass)."""
    grams = (measurements.get("masses_g") or {}).get("robot_complete_with_battery")
    if grams is None:
        return {}
    view = fitting.ModelView(model)
    total = float(model.body_mass[view.robot_bodies].sum())
    return {"mass_scale": (grams / 1000.0 / total, f"weighed {grams:g} g complete robot; model total {1000 * total:.0f} g")}


def fit_and_report(logs: dict[str, runlog.RunLog], out_dir: Path | str, *, model: mujoco.MjModel | None = None,
                   params=fitting.DEFAULT_PARAMS, measurements: dict | None = None, title: str | None = None):
    """Fit, then write fit.json and report.html into ``out_dir``. Returns (result, report path)."""
    model = model or load_model()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fixed = {}
    if all(log.evidence == "measured" for log in logs.values()):
        fixed = fixed_from_measurements(model, measurements if measurements is not None else load_measurements())
    result = fitting.fit(model, logs, params, fixed=fixed)
    hidden = None
    if result.evidence == "synthetic":
        hidden = {}
        for name, log in logs.items():
            truth = log.header.get("synthetic", {})
            hidden.update(truth.get("hidden_parameters", {}))
            hidden[f"time_offset[{name}]"] = truth.get("hidden_time_offset_s")
    data = result.to_json()
    (out_dir / "fit.json").write_text(json.dumps(data, indent=1) + "\n")
    path = out_dir / "report.html"
    path.write_text(report.render(data, hidden, title or "Sesame sim-to-real calibration"))
    return result, path


def summary(result: fitting.FitResult) -> str:
    """Plain-text summary with the honesty label first."""
    lines = []
    if result.evidence == "synthetic":
        lines.append("SYNTHETIC DATA: validates the pipeline only. No robot was measured.")
    b, a = result.rms_before, result.rms_after
    lines.append(f"torso position RMS {b['position_mm']:.2f} -> {a['position_mm']:.2f} mm, "
                 f"attitude RMS {b['attitude_deg']:.2f} -> {a['attitude_deg']:.2f} deg "
                 f"(height {b['height_mm']:.2f} -> {a['height_mm']:.2f} mm, "
                 f"roll/pitch {b['tilt_deg']:.2f} -> {a['tilt_deg']:.2f} deg)")
    for p in result.params:
        std = f" ± {p.std:.3g}" if p.std is not None and p.std == p.std else ""
        lines.append(f"  {p.name:<24} {p.value:.4g}{std} {p.unit}  [{p.status}] {p.note}")
    return "\n".join(lines)


# Hidden parameter changes of the synthetic demo, per command interface.
DEMO = {
    "reference firmware ramp (60 deg/s)": {
        "sequences": ("lift", "sway"), "slew": "manifest", "offsets": (-1.8, 0.137),
        "hidden": {"kp_scale": 0.5, "friction": 0.45},
        "params": ("kp_scale", "friction", "speed_limit", "torque_limit_scale")},
    "no firmware ramp": {
        "sequences": ("steps", "lift"), "slew": None, "offsets": (-1.8, 0.137),
        "hidden": {"kp_scale": 1.6, "speed_limit": 300.0, "friction": 0.5},
        "params": ("kp_scale", "speed_limit", "friction")},
}


def demo(out_dir: Path | str, video: bool = True, seed: int = 10) -> dict:
    """Synthetic end-to-end example: record -> (video -> track) -> fit -> report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = load_model()
    outputs = {}
    for index, (label, case) in enumerate(DEMO.items()):
        logs = {}
        for k, (sequence, offset) in enumerate(zip(case["sequences"], case["offsets"])):
            path = out_dir / f"case{index + 1}-{sequence}.jsonl"
            if video and index == 0 and k == 0:  # one run goes through a rendered video and the tracker
                video_path = out_dir / f"case{index + 1}-{sequence}.avi"
                header, records, camera = synthetic.synthesize_video(
                    model, sequence, case["hidden"], video_path, seed=seed + k, time_offset_s=offset,
                    slew_rate_deg_s=case["slew"])
                runlog.write(path, header, records)
                add_track(path, marker.track_video(video_path, camera), list(synthetic.MARKER_ORIGIN_IN_TORSO_M),
                          "synthetic scene value")
            else:
                header, records = synthetic.synthesize(model, sequence, case["hidden"], seed=seed + k,
                                                       time_offset_s=offset, slew_rate_deg_s=case["slew"])
                runlog.write(path, header, records)
            logs[sequence] = runlog.load(path)
        result, report_path = fit_and_report(logs, out_dir / f"case{index + 1}", model=model, params=case["params"],
                                             title=f"Synthetic example: {label}")
        outputs[label] = (result, report_path)
    return outputs
