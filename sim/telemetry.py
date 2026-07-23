"""Behavioral telemetry: compact numeric signatures for motion playback.

Purpose: catch convention/kinematics errors (wrong axis, sign, front/back,
left/right)早 — without rendering. Semantic expectations about motions
("a bow drops the head", "turn_left yaws CCW", "the waving paw stays
airborne") are encoded as assertions over these metrics in
tests/test_behavior.py.

Signature metrics (all SI / degrees, world frame, z-up x-forward):
- disp_x, disp_y     final torso displacement
- yaw_deg            final torso yaw
- final_z, min_z, max_z   torso center height over the motion
- pitch_min/pitch_max     signed face-vs-rear height difference extremes
                          (positive = face end higher than rear end)
- upright_final      cos of final torso tilt (1 = level)
- paw_air_frac[J]    fraction of motion time foot J had no floor contact
- paw_max_z[J]       max height of foot J's paddle tip

CLI: uv run python -m sim.telemetry [motion ...]
"""

from __future__ import annotations

import numpy as np

from sim.manifest import load_manifest
from sim.motions import ctrl_schedule, flatten, load_motions


def motion_signature(motion_name: str, settle_steps: int = 500) -> dict:
    import mujoco

    from sim.build_mjcf import FOOT_LEN, MODEL_PATH, TORSO_HALF

    manifest = load_manifest()
    doc = load_motions()
    events = flatten(doc["motions"][motion_name], manifest.raw["poses"])
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    schedule = ctrl_schedule(events, manifest, model.opt.timestep)
    total_steps = (schedule[-1][0] if schedule else 0) + settle_steps

    torso = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "torso")
    floor = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    feet = {}  # foot joint name -> (body id, lower geom id, +y or -y tip)
    for j in manifest.joints:
        if j.role != "foot":
            continue
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"{j.leg}_lower")
        geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{j.leg}_lower_geom")
        sy = 1.0 if "left" in j.leg else -1.0
        feet[j.name] = (body, geom, np.array([0.0, sy * FOOT_LEN, 0.0]))

    min_z, max_z = np.inf, -np.inf
    pitch_min, pitch_max = np.inf, -np.inf
    contact_steps = {name: 0 for name in feet}
    paw_max_z = {name: -np.inf for name in feet}
    ex = np.array([TORSO_HALF[0], 0.0, 0.0])

    i = 0
    for step in range(total_steps):
        while i < len(schedule) and schedule[i][0] <= step:
            _, channel, value = schedule[i]
            data.ctrl[channel] = value
            i += 1
        mujoco.mj_step(model, data)

        min_z = min(min_z, data.qpos[2])
        max_z = max(max_z, data.qpos[2])
        R = data.xmat[torso].reshape(3, 3)
        c = data.xpos[torso]
        face_z = (c + R @ ex)[2]
        rear_z = (c - R @ ex)[2]
        pitch_min = min(pitch_min, face_z - rear_z)
        pitch_max = max(pitch_max, face_z - rear_z)

        touching = set()
        for k in range(data.ncon):
            con = data.contact[k]
            for name, (_, geom, _) in feet.items():
                if {con.geom1, con.geom2} == {geom, floor}:
                    touching.add(name)
        for name, (body, _, tip) in feet.items():
            if name in touching:
                contact_steps[name] += 1
            tip_z = (data.xpos[body] + data.xmat[body].reshape(3, 3) @ tip)[2]
            paw_max_z[name] = max(paw_max_z[name], tip_z)

    q = data.qpos
    return {
        "disp_x": float(q[0]),
        "disp_y": float(q[1]),
        "yaw_deg": float(np.degrees(2 * np.arctan2(q[6], q[3]))),
        "final_z": float(q[2]),
        "min_z": float(min_z),
        "max_z": float(max_z),
        "pitch_min": float(pitch_min),
        "pitch_max": float(pitch_max),
        "upright_final": float(data.xmat[torso].reshape(3, 3)[2, 2]),
        "paw_air_frac": {
            name: 1.0 - contact_steps[name] / total_steps for name in feet
        },
        "paw_max_z": {name: float(v) for name, v in paw_max_z.items()},
    }


def main() -> None:
    import sys

    names = sys.argv[1:] or sorted(load_motions()["motions"])
    for name in names:
        sig = motion_signature(name)
        air = " ".join(f"{k}:{v:.2f}" for k, v in sig["paw_air_frac"].items())
        print(
            f"{name:14s} disp=({sig['disp_x']:+.3f},{sig['disp_y']:+.3f}) "
            f"yaw={sig['yaw_deg']:+7.1f} z=[{sig['min_z']:.3f},{sig['max_z']:.3f}] "
            f"pitch=[{sig['pitch_min']:+.3f},{sig['pitch_max']:+.3f}] "
            f"up={sig['upright_final']:+.2f}  air {air}"
        )


if __name__ == "__main__":
    main()
