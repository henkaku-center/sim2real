"""Stock motion playback: expand manifest/motions.yaml into timed ctrl events.

Semantics (shared contract with the browser worker — keep in sync):
- A motion flattens to a list of events (time_ms, {joint: firmware_deg}).
- Events at the same time merge (later steps win per joint).
- During playback, an event applies when sim time reaches
  step_index = round(time_ms / 1000 / timestep); ctrl is set BEFORE that step.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from sim.manifest import Manifest, load_manifest

MOTIONS_PATH = Path(__file__).parent.parent / "manifest" / "motions.yaml"


@dataclass(frozen=True)
class Event:
    time_ms: float
    targets_deg: dict[str, float]  # firmware degrees, only joints that change


def load_motions(path: Path = MOTIONS_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def flatten(steps: list, poses: dict[str, dict[str, float]]) -> list[Event]:
    """Expand nested steps into merged, time-ordered events."""
    events: dict[float, dict[str, float]] = {}
    t = 0.0

    def apply(targets: dict[str, float]) -> None:
        events.setdefault(t, {}).update(targets)

    def walk_steps(steps: list) -> None:
        nonlocal t
        for step in steps:
            if "pose" in step:
                apply(dict(poses[step["pose"]]))
            elif "set" in step:
                apply({k: float(v) for k, v in step["set"].items()})
            elif "wait" in step:
                t += float(step["wait"])
            elif "repeat" in step:
                for _ in range(int(step["repeat"]["count"])):
                    walk_steps(step["repeat"]["steps"])
            else:
                raise ValueError(f"unknown step: {step}")

    walk_steps(steps)
    return [Event(time_ms, targets) for time_ms, targets in sorted(events.items())]


def duration_ms(events: list[Event]) -> float:
    return events[-1].time_ms if events else 0.0


def ctrl_schedule(
    events: list[Event], manifest: Manifest, timestep: float
) -> list[tuple[int, int, float]]:
    """Events -> (step_index, channel, internal_radians), time-ordered."""
    out = []
    for ev in events:
        step_index = round(ev.time_ms / 1000.0 / timestep)
        for name, deg in ev.targets_deg.items():
            j = manifest.joint(name)
            out.append((step_index, j.channel, manifest.to_internal(j, deg)))
    return out


def play_native(motion_name: str, settle_steps: int = 500):
    """Run a motion in native MuJoCo; returns (model, data) at the end.

    Starts from the default state, plays the full schedule, then holds the
    final targets for settle_steps.
    """
    import mujoco

    from sim.build_mjcf import MODEL_PATH

    manifest = load_manifest()
    doc = load_motions()
    events = flatten(doc["motions"][motion_name], manifest.raw["poses"])
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    schedule = ctrl_schedule(events, manifest, model.opt.timestep)
    total_steps = (schedule[-1][0] if schedule else 0) + settle_steps
    i = 0
    for step in range(total_steps):
        while i < len(schedule) and schedule[i][0] <= step:
            _, channel, value = schedule[i]
            data.ctrl[channel] = value
            i += 1
        mujoco.mj_step(model, data)
    return model, data
