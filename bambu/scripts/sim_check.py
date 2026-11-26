"""MuJoCo dynamic checks for the self-righting shell (floor-only contact, fixed seeds).

1. drop: the tucked robot + shell as one rigid body, released 3 mm above a flat floor in
   seeded random orientations (some with a small spin), plus the exactly balanced supine
   state.  Success = belly down (tilt < max_upright_tilt_deg) after 4 s.
2. recovery: the articulated robot starts fallen in the stand pose (supine, sides, nose,
   tail, diagonals), then runs the tuck -> passive roll -> stand-up sequence with
   torque-limited position servos.  Success = standing upright on its feet at the end.

Leg-vs-shell collisions are excluded here (checked geometrically in analyze.py); only the
floor touches the robot.  Units inside MuJoCo are SI.
"""
from __future__ import annotations

import math

import mujoco
import numpy as np
import trimesh

FLOOR_FRICTION = 0.6
SERVO_TORQUE_NM = 0.176  # MG90S nominal stall at 4.8 V (manifest)
SERVO_KP = 1.2
SERVO_RATE_DEG_S = 200.0
DT = 0.001


def _inertia(parts):
    """parts: list of (mass_g, com_mm, mesh|None) -> (mass kg, com m, 3x3 inertia kg m^2 about com)."""
    m = np.array([p[0] for p in parts]) / 1000
    c = np.array([p[1] for p in parts]) / 1000
    M = m.sum()
    com = (m[:, None] * c).sum(0) / M
    I = np.zeros((3, 3))
    for (mass_g, com_mm, mesh), mi, ci in zip(parts, m, c):
        if mesh is not None and mesh.is_watertight and mesh.volume > 1e-6:
            own = np.asarray(mesh.moment_inertia) * (mi / (mesh.volume * 1e-9)) * 1e-15  # density-1 mm^5 -> kg m^2
        elif mesh is not None:
            ext = np.ptp(mesh.vertices, axis=0) / 1000
            own = np.diag(mi / 12 * np.array([ext[1] ** 2 + ext[2] ** 2, ext[0] ** 2 + ext[2] ** 2, ext[0] ** 2 + ext[1] ** 2]))
        else:
            own = np.zeros((3, 3))
        r = ci - com
        I += own + mi * (np.dot(r, r) * np.eye(3) - np.outer(r, r))
    return M, com, I


def _set_inertial(body, mass, com, inertia):
    body.explicitinertial = True
    body.mass = mass
    body.ipos = com
    body.fullinertia = [inertia[0, 0], inertia[1, 1], inertia[2, 2], inertia[0, 1], inertia[0, 2], inertia[1, 2]]


def _add_mesh_geom(spec, body, name, mesh, rgba, origin_m):
    hull = mesh.convex_hull
    v = hull.vertices / 1000 - origin_m
    spec.add_mesh(name=name, uservert=v.ravel().tolist(), userface=hull.faces.ravel().tolist())
    body.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=name, rgba=rgba, contype=2, conaffinity=1,
                  friction=[FLOOR_FRICTION, 0.005, 0.0001], density=0)


def _new_spec():
    spec = mujoco.MjSpec()
    spec.option.timestep = DT
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.visual.global_.offwidth = 1280
    spec.visual.global_.offheight = 960
    spec.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                     rgb1=[1, 1, 1], rgb2=[0.92, 0.94, 0.97], width=64, height=64)
    spec.worldbody.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, size=[2, 2, 0.01], rgba=[0.82, 0.82, 0.82, 1],
                            contype=1, conaffinity=2, friction=[FLOOR_FRICTION, 0.005, 0.0001])
    spec.worldbody.add_light(pos=[0, 0, 1.5], dir=[0, 0, -1])
    return spec


def _shell_parts(shell, extra):
    meshes = list(shell.values())
    return [(m, c, meshes[i] if i < len(meshes) else None) for i, (m, c) in enumerate(extra)]  # e.g. LED tape: mass only


def rigid_model(model, params, shell, extra, com_offset_mm=(0.0, 0.0, 0.0)):
    pose = params["poses"]["tuck"]
    parts = [(p.mass_g, com, mesh) for p, com, mesh in model.posed(pose)] + _shell_parts(shell, extra)
    M, com, I = _inertia(parts)
    spec = _new_spec()
    body = spec.worldbody.add_body(name="robot")
    body.add_freejoint()
    _set_inertial(body, M, np.asarray(com_offset_mm, float) / 1000, I)  # CoM error relative to the geometry
    pts = np.vstack([mesh.vertices for _, _, mesh in parts if mesh is not None])
    _add_mesh_geom(spec, body, "hull", trimesh.PointCloud(pts).convex_hull, [0.3, 0.65, 0.45, 1], com)
    return spec.compile(), com


def _quat_from_matrix(R):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, R.ravel())
    return q


def _settle_height(m, d, R):
    """Place the body so its lowest vertex is 3 mm above the floor."""
    verts = m.mesh_vert.reshape(-1, 3)
    z = (verts @ R.T)[:, 2].min()
    return -z + 0.003


def drop_tests(model, params, shell, extra, com_offset_mm=(0.0, 0.0, 0.0), n=None):
    acc = params["acceptance"]
    m, com = rigid_model(model, params, shell, extra, com_offset_mm)
    rng = np.random.default_rng(acc["drop_seed"])
    cases = []
    for i in range(acc["drop_tests"] if n is None else n):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        R = np.zeros(9)
        mujoco.mju_quat2Mat(R, q)
        w = rng.normal(scale=1.5, size=3) if i % 3 == 0 else np.zeros(3)
        cases.append((f"random-{i:03d}", R.reshape(3, 3), w))
    flip = np.diag([1.0, -1.0, -1.0])
    cases.append(("supine-balanced", flip, np.zeros(3)))
    tilt = np.array([[1, 0, 0], [0, math.cos(0.009), -math.sin(0.009)], [0, math.sin(0.009), math.cos(0.009)]])
    cases.append(("supine-0.5deg", tilt @ flip, np.zeros(3)))
    out = []
    for name, R, w in cases:
        d = mujoco.MjData(m)
        d.qpos[:3] = [0, 0, _settle_height(m, d, R)]
        d.qpos[3:7] = _quat_from_matrix(R)
        d.qvel[3:6] = w
        mujoco.mj_forward(m, d)
        steps = int(4.0 / DT)
        for _ in range(steps):
            mujoco.mj_step(m, d)
        up = d.xmat[1].reshape(3, 3)[:, 2]
        tilt_deg = math.degrees(math.acos(np.clip(up[2], -1, 1)))
        out.append({"case": name, "final_tilt_deg": round(tilt_deg, 2),
                    "ok": tilt_deg < acc["max_upright_tilt_deg"], "speed": round(float(np.linalg.norm(d.qvel)), 4)})
    random_rows = [r for r in out if r["case"].startswith("random")]
    return {"cases": out, "success_rate": round(sum(r["ok"] for r in random_rows) / len(random_rows), 4),
            "failures": [r for r in out if not r["ok"]]}


# ----------------------------------------------------------------------------- articulated
def articulated_model(model, params, shell, extra):
    spec = _new_spec()
    torso = spec.worldbody.add_body(name="torso")
    torso.add_freejoint()
    step_pose = {"hip": 45.0, "knee": 90.0}
    groups: dict = {}
    for p, com, mesh in model.posed(step_pose):
        groups.setdefault((p.group, p.leg), []).append((p.mass_g, com, mesh))
    tparts = groups[("torso", None)] + _shell_parts(shell, extra)
    n_body = len(groups[("torso", None)])
    M, com, I = _inertia(tparts)
    _set_inertial(torso, M, com, I)
    for i, (_, _, mesh) in enumerate(tparts):
        if mesh is not None:
            _add_mesh_geom(spec, torso, f"torso{i}", mesh, [0.9, 0.85, 0.75, 1] if i < n_body else [0.3, 0.65, 0.45, 1], np.zeros(3))
    for name, leg in model.legs.items():
        femur = torso.add_body(name=f"{name}_femur", pos=leg.hip_point / 1000)
        Mf, cf, If = _inertia(groups[("femur", name)])
        _set_inertial(femur, Mf, cf - leg.hip_point / 1000, If)
        femur.add_joint(name=f"{name}_hip", type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 0, leg.hip_sign],
                        damping=0.004, armature=2e-5)
        for i, (_, _, mesh) in enumerate(groups[("femur", name)]):
            if mesh is not None:
                _add_mesh_geom(spec, femur, f"{name}_f{i}", mesh, [0.8, 0.3, 0.15, 1], leg.hip_point / 1000)
        foot = femur.add_body(name=f"{name}_foot", pos=(leg.knee_point - leg.hip_point) / 1000)
        Mk, ck, Ik = _inertia(groups[("foot", name)])
        _set_inertial(foot, Mk, ck - leg.knee_point / 1000, Ik)
        foot.add_joint(name=f"{name}_knee", type=mujoco.mjtJoint.mjJNT_HINGE, axis=(leg.knee_axis * leg.knee_sign).tolist(),
                       damping=0.004, armature=2e-5)
        for i, (_, _, mesh) in enumerate(groups[("foot", name)]):
            if mesh is not None:
                _add_mesh_geom(spec, foot, f"{name}_k{i}", mesh, [0.85, 0.5, 0.2, 1], leg.knee_point / 1000)
        for j in ("hip", "knee"):
            spec.add_actuator(name=f"{name}_{j}", target=f"{name}_{j}", trntype=mujoco.mjtTrn.mjTRN_JOINT,
                              gaintype=mujoco.mjtGain.mjGAIN_FIXED, biastype=mujoco.mjtBias.mjBIAS_AFFINE,
                              gainprm=[SERVO_KP] + [0] * 9, biasprm=[0, -SERVO_KP, -0.02] + [0] * 7,
                              forcelimited=True, forcerange=[-SERVO_TORQUE_NM, SERVO_TORQUE_NM])
    return spec.compile()


def _targets(legs, hip_q, knee_q):
    """Actuator targets (joint angle relative to the STEP pose) for internal q in degrees."""
    out = []
    for _ in legs:
        out += [math.radians(hip_q - 45.0), math.radians(knee_q - 90.0)]
    return np.array(out)


SEQUENCE = [  # (duration s, hip q, knee q) — linear interpolation at <= SERVO_RATE_DEG_S
    ("fallen, stand pose held", 1.5, 45, 90),
    ("tuck 1: hips to 90", 0.6, 90, 90),
    ("tuck 2: knees up", 1.4, 90, -90),
    ("passive righting", 2.5, 90, -90),
    ("stand 1: knees down", 1.6, 90, 90),
    ("stand 2: hips to 45", 0.8, 45, 90),
    ("settle", 1.0, 45, 90),
]
SEQUENCE_NO_TUCK = [("fallen, stand pose held", 1.5, 45, 90), ("passive righting", 4.5, 45, 90),
                    ("settle", 1.0, 45, 90)]
FALLEN = {
    "supine": (1, 0, 0, 180), "left-side": (1, 0, 0, 90), "right-side": (1, 0, 0, -90),
    "nose-down": (0, 1, 0, 90), "tail-down": (0, 1, 0, -90), "supine-diag-45": (1, 1, 0, 180),
    "left-side-nose-45": (1, 1, 0, 90), "right-side-tail-45": (1, -1, 0, -100),
}


def _axis_angle(ax, ay, az, deg):
    q = np.zeros(4)
    mujoco.mju_axisAngle2Quat(q, np.array([ax, ay, az], float) / np.linalg.norm([ax, ay, az]), math.radians(deg))
    return q


def recovery_tests(model, params, shell, extra, frames_for=None, sequence=None):
    sequence = sequence or SEQUENCE
    m = articulated_model(model, params, shell, extra)
    legs = list(model.legs)
    results, frames = [], []
    for name, aa in FALLEN.items():
        d = mujoco.MjData(m)
        d.qpos[3:7] = _axis_angle(*aa)
        hip0, knee0 = math.radians(0.0), math.radians(0.0)
        d.qpos[7:] = [hip0, knee0] * 4
        d.ctrl[:] = _targets(legs, 45, 90)
        mujoco.mj_forward(m, d)
        lowest = min((d.geom_xpos[g][2] for g in range(1, m.ngeom)), default=0)
        # lift so the lowest geom vertex clears the floor
        zmin = np.inf
        for g in range(1, m.ngeom):
            mid = m.geom_dataid[g]
            if mid < 0:
                continue
            v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
            zmin = min(zmin, (v @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g])[:, 2].min())
        d.qpos[2] += -zmin + 0.003
        mujoco.mj_forward(m, d)
        log, cur = [], (45.0, 90.0)
        t_phase = 0.0
        for label, dur, hq, kq in sequence:
            n = int(dur / DT)
            start = cur
            span = max(abs(hq - start[0]), abs(kq - start[1]))
            ramp = span / SERVO_RATE_DEG_S if span else 0.0
            for i in range(n):
                s = min(1.0, (i * DT) / ramp) if ramp else 1.0
                d.ctrl[:] = _targets(legs, start[0] + s * (hq - start[0]), start[1] + s * (kq - start[1]))
                mujoco.mj_step(m, d)
                if frames_for == name and (i == n - 1 or (label == "passive righting" and i % 500 == 0)):
                    frames.append((f"{label} t={t_phase + i * DT:.1f}s", d.qpos.copy()))
            cur = (hq, kq)
            up = d.xmat[1].reshape(3, 3)[:, 2]
            log.append({"phase": label, "t_end_s": round(t_phase + dur, 2),
                        "tilt_deg": round(math.degrees(math.acos(np.clip(up[2], -1, 1))), 1),
                        "torso_z_mm": round(float(d.xpos[1][2]) * 1000, 1)})
            t_phase += dur
        righted = next(r for r in log if r["phase"] == "passive righting")
        final = log[-1]
        results.append({"case": name, "after_righting_tilt_deg": righted["tilt_deg"],
                        "final_tilt_deg": final["tilt_deg"], "final_torso_z_mm": final["torso_z_mm"],
                        "recovered": righted["tilt_deg"] < 15 and final["tilt_deg"] < 10 and final["torso_z_mm"] > 25,
                        "log": log})
    return results, (m, frames)


def drop_tests_com_error(model, params, shell, extra, n=40):
    """Drop tests with the CoM displaced by com_perturbation_mm along the 26 grid directions."""
    import itertools
    acc = params["acceptance"]
    rows = []
    for dv in itertools.product((-1, 0, 1), repeat=3):
        if not any(dv):
            continue
        off = acc["com_perturbation_mm"] * np.array(dv, float) / np.linalg.norm(dv)
        r = drop_tests(model, params, shell, extra, off, n)
        rows.append({"dir": list(dv), "success_rate": r["success_rate"],
                     "failures": [(f["case"], f["final_tilt_deg"]) for f in r["failures"]]})
    return {"per_direction": rows, "min_success_rate": min(r["success_rate"] for r in rows),
            "all_ok": all(not r["failures"] for r in rows)}


def run_all(model, params, shell, extra):
    drop = drop_tests(model, params, shell, extra)
    rec, _ = recovery_tests(model, params, shell, extra)
    passive, _ = recovery_tests(model, params, shell, extra, sequence=SEQUENCE_NO_TUCK)
    for r in passive:
        r["recovered"] = r["final_tilt_deg"] < 10 and r["final_torso_z_mm"] > 25
    return {"floor_friction": FLOOR_FRICTION, "servo_torque_nm": SERVO_TORQUE_NM, "drop": drop, "recovery": rec,
            "passive_only_stand_pose": [{k: r[k] for k in ("case", "final_tilt_deg", "final_torso_z_mm", "recovered")}
                                        for r in passive]}
