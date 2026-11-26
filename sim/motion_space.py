"""Sesame's motion space: eight named axes instead of eight servos.

The 8 joints are 4 hip yaws (sweep a leg horizontally) and 4 foot pitches
(lower a paddle). Most of the 8-D joint box cannot stand: paws all on one
side of the body tip it over, nearly horizontal paddles overload the servos
and sag, legs on one side collide when both sweep inward. This module
re-expresses the joints in eight body-level axes and checks a pose with
analytic rules that were fitted against MuJoCo settling runs (see
`manifest/motion_space.yaml` and `reference/MOTION-SPACE.md`).

Hip axes are symmetric patterns of the paws' forward sweep (degrees):

    surge   all paws forward (body moves back)      FR+ FL+ BR+ BL+
    spread  front paws forward, back paws back      FR+ FL+ BR- BL-
    yaw     right paws forward, left paws back      FR+ FL- BR+ BL-
    stride  diagonal FR/BL forward, FL/BR back      FR+ FL- BR- BL+

Foot axes are solved by inverse kinematics so every paw touches a flat floor:

    height  torso centre above the floor (mm)
    pitch   nose up (deg)
    roll    right side up (deg)
    lift    raise diagonal FR/BL (+) or FL/BR (-) paws off the floor (mm)

`decode` maps axes to internal joint degrees; `violations` lists broken
rules; `project` scales a pose towards the centre until it is feasible, so a
too-wild motion keeps its shape and just gets smaller.

    uv run python -m sim.motion_space            # check the YAML's numbers in MuJoCo
    uv run python -m sim.motion_space --text     # the space as text for an LLM prompt
    uv run python -m sim.motion_space --html     # rebuild web/public/motion-space/index.html
"""

from __future__ import annotations

import gzip
import json
import math
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

from sim.build_mjcf import (
    FOOT_HALF,
    FOOT_LEN,
    FOOT_MASS,
    HIP_X,
    HIP_Y,
    LEG_PLANE_DZ,
    MODEL_PATH,
    TORSO_HALF,
    TORSO_MASS,
    UPPER_HALF,
    UPPER_LEN,
    UPPER_MASS,
)
from sim.manifest import Manifest, load_manifest

SPACE_PATH = Path(__file__).parent.parent / "manifest" / "motion_space.yaml"
VIEWER_PATH = Path(__file__).parent.parent / "web" / "public" / "motion-space" / "index.html"

AXES = ("surge", "spread", "yaw", "stride", "height", "pitch", "roll", "lift")
LEGS = ("front_right", "front_left", "back_right", "back_left")
SX = np.array([1, 1, -1, -1])  # +1 front, -1 back
SY = np.array([-1, 1, -1, 1])  # +1 left, -1 right
PATTERN = {
    "all": np.array([1, 1, 1, 1]),
    "fb": np.array([1, 1, -1, -1]),
    "lr": np.array([1, -1, 1, -1]),
    "diag": np.array([1, -1, -1, 1]),
}
HIP_PATTERN = {"surge": "all", "spread": "fb", "yaw": "lr", "stride": "diag"}


@lru_cache(maxsize=1)
def load_space(path: Path = SPACE_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _manifest() -> Manifest:
    return load_manifest()


def _legs(m: Manifest) -> tuple[list[str], list[str]]:
    """Hip and foot joint names per leg, in LEGS order."""
    hips = [next(j.name for j in m.joints if j.leg == leg and j.role == "hip") for leg in LEGS]
    feet = [next(j.name for j in m.joints if j.leg == leg and j.role == "foot") for leg in LEGS]
    return hips, feet


def _rot(pitch_deg: float, roll_deg: float) -> np.ndarray:
    """Body -> world rotation for nose-up pitch and right-side-up roll."""
    a, b = -math.radians(pitch_deg), -math.radians(roll_deg)
    ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
    return ry @ rx


def _femur(i: int, hip_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Hip axis point and femur direction (body frame) for leg i."""
    h = math.radians(hip_deg)
    u = np.array([SX[i] * math.sin(h), SY[i] * math.cos(h), 0.0])
    return np.array([SX[i] * HIP_X, SY[i] * HIP_Y, LEG_PLANE_DZ]), u


def _paw(i: int, hip_deg: float, foot_deg: float, rot: np.ndarray) -> np.ndarray:
    """Lowest edge of the paddle tip (body frame) for the given attitude."""
    hip, u = _femur(i, hip_deg)
    f = math.radians(foot_deg)
    d = math.cos(f) * u + np.array([0, 0, -math.sin(f)])
    n = math.sin(f) * u + np.array([0, 0, math.cos(f)])
    tip = hip + UPPER_LEN * u + FOOT_LEN * d
    a = np.array([-u[1], u[0], 0.0])  # foot axis
    corners = [tip + e * FOOT_HALF[2] * n + w * FOOT_HALF[0] * a for e in (1, -1) for w in (1, -1)]
    return min(corners, key=lambda p: (rot @ p)[2])


def _foot_ik(i: int, hip_deg: float, rot: np.ndarray, height: float, lift: float) -> float | None:
    """Smallest foot angle (deg, within +-90) that lowers the paw to world z=lift."""
    hip, u = _femur(i, hip_deg)
    r3 = rot[2]
    ru, rz = r3 @ u, r3[2]
    side = abs(r3 @ np.array([-u[1], u[0], 0.0])) * FOOT_HALF[0]  # lower end of the tip edge
    c0 = height + r3 @ (hip + UPPER_LEN * u) - side
    best = None
    for edge in (1, -1):  # the two long edges of the paddle tip
        a = FOOT_LEN * ru + edge * FOOT_HALF[2] * rz
        b = -FOOT_LEN * rz + edge * FOOT_HALF[2] * ru
        rho, k = math.hypot(a, b), lift - c0
        if abs(k) > rho:
            continue
        base, spread = math.atan2(b, a), math.acos(k / rho)
        for phi in (base - spread, base + spread):
            phi = (phi + math.pi) % (2 * math.pi) - math.pi
            if abs(phi) <= math.pi / 2 + 1e-9 and (best is None or phi < best):
                best = phi
    return None if best is None else math.degrees(best)


def full(z: Mapping[str, float]) -> dict[str, float]:
    """Axes with unspecified entries filled from the centre pose."""
    center = load_space()["center"]
    unknown = set(z) - set(AXES)
    if unknown:
        raise ValueError(f"unknown axes {sorted(unknown)}")
    return {a: float(z.get(a, center[a])) for a in AXES}


def hip_angles(z: Mapping[str, float]) -> np.ndarray:
    """Internal hip degrees per leg (LEGS order)."""
    z = full(z)
    forward = sum(z[a] * PATTERN[p] for a, p in HIP_PATTERN.items())
    return load_space()["hip_center_deg"] + SX * forward


def decode(z: Mapping[str, float], m: Manifest | None = None) -> dict[str, float] | None:
    """Axes -> internal joint degrees by name; None if a paw cannot reach the floor."""
    m = m or _manifest()
    z = full(z)
    hips = hip_angles(z)
    rot = _rot(z["pitch"], z["roll"])
    raised = PATTERN["diag"] * z["lift"] > 0
    feet = [_foot_ik(i, hips[i], rot, z["height"] / 1000, abs(z["lift"]) / 1000 * raised[i])
            for i in range(4)]
    if any(f is None for f in feet):
        return None
    hip_names, foot_names = _legs(m)
    out = dict(zip(hip_names, hips.tolist())) | dict(zip(foot_names, feet))
    return {j.name: out[j.name] for j in m.joints}


def firmware_pose(z: Mapping[str, float], m: Manifest | None = None) -> list[float] | None:
    """Axes -> firmware degrees in channel order (what `pose` takes)."""
    m = m or _manifest()
    q = decode(z, m)
    if q is None:
        return None
    return [m.to_firmware(j, math.radians(q[j.name])) for j in m.joints]


def _com(hips: np.ndarray, feet: np.ndarray) -> np.ndarray:
    total, mass = np.zeros(3), TORSO_MASS
    for i in range(4):
        hip, u = _femur(i, hips[i])
        f = math.radians(feet[i])
        d = math.cos(f) * u + np.array([0, 0, -math.sin(f)])
        total += UPPER_MASS * (hip + UPPER_LEN / 2 * u)
        total += FOOT_MASS * (hip + UPPER_LEN * u + FOOT_LEN / 2 * d)
        mass += UPPER_MASS + FOOT_MASS
    return total / mass


def _margin(points: np.ndarray, p: np.ndarray) -> float:
    """Signed distance of p inside the convex hull of points (xy)."""
    from scipy.spatial import ConvexHull

    eq = ConvexHull(points[:, :2]).equations
    return float(-np.max(eq[:, :2] @ p[:2] + eq[:, 2]))


def _lowest_body_point(hips: np.ndarray, rot: np.ndarray, height: float) -> float:
    """World z of the lowest torso or femur corner."""
    corners = [np.array([a * TORSO_HALF[0], b * TORSO_HALF[1], c * TORSO_HALF[2]])
               for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)]
    for i in range(4):
        hip, u = _femur(i, hips[i])
        v = np.array([-u[1], u[0], 0.0])
        corners += [hip + s * u + a * UPPER_HALF[0] * v + c * np.array([0, 0, UPPER_HALF[2]])
                    for s in (0, UPPER_LEN) for a in (-1, 1) for c in (-1, 1)]
    return height + min((rot @ p)[2] for p in corners)


def measures(z: Mapping[str, float], m: Manifest | None = None) -> dict[str, float] | None:
    """Quantities the rules test, for the pose with every paw on the floor."""
    m = m or _manifest()
    z = full(z) | {"lift": 0.0}
    q = decode(z, m)
    if q is None:
        return None
    hip_names, foot_names = _legs(m)
    hips = np.array([q[n] for n in hip_names])
    feet = np.array([q[n] for n in foot_names])
    rot = _rot(z["pitch"], z["roll"])
    h = z["height"] / 1000
    paws = np.array([rot @ _paw(i, hips[i], feet[i], rot) for i in range(4)])
    side = {"right": hips[0] + hips[2], "left": hips[1] + hips[3]}
    return {
        "support_margin_mm": 1000 * _margin(paws, rot @ _com(hips, feet)),
        "clearance_mm": 1000 * _lowest_body_point(hips, rot, h),
        "foot_min_deg": float(feet.min()),
        "hip_pair_sum_min_deg": float(min(side.values())),
    }


def violations(z: Mapping[str, float], m: Manifest | None = None) -> list[str]:
    """Broken rules for a pose; empty when Sesame can hold it (lift is a gait axis:
    its paws only need to reach, the stance is judged with all paws down)."""
    m = m or _manifest()
    rules = load_space()["rules"]
    zf = full(z)
    q = decode(zf, m)
    if q is None:
        return ["unreachable"]
    out = []
    for j in m.joints:
        lo, hi = np.degrees(m.internal_range(j))
        if not lo - 1e-6 <= q[j.name] <= hi + 1e-6:
            out.append(f"limit {j.name}")
    if abs(zf["lift"]) > rules["lift_max_mm"]:
        out.append("lift")
    got = measures(zf, m)
    if got is None:
        return out + ["unreachable"]
    for key in ("support_margin_mm", "clearance_mm", "foot_min_deg", "hip_pair_sum_min_deg"):
        if got[key] < rules[key]:
            out.append(key)
    return out


def feasible(z: Mapping[str, float], m: Manifest | None = None) -> bool:
    return not violations(z, m)


def tilt_limit(height: float) -> float:
    """Max |pitch| (= max |roll|) at this height, other axes centred (deg)."""
    table = load_space()["tilt_by_height"]
    keys = sorted(table)
    return float(np.interp(height, keys, [table[k] for k in keys]))


def within_budget(z: Mapping[str, float]) -> bool:
    """The simple inner rule from motion_space.yaml (implies `feasible`)."""
    b, z = load_space()["budget"], full(z)
    return (sum(abs(z[a]) for a in HIP_PATTERN) <= b["hip_l1_deg"]
            and b["height_mm"][0] <= z["height"] <= b["height_mm"][1]
            and abs(z["pitch"]) + abs(z["roll"]) <= b["tilt_l1_fraction"] * tilt_limit(z["height"])
            and abs(z["lift"]) <= b["lift_mm"])


def project(z: Mapping[str, float], m: Manifest | None = None, steps: int = 20) -> dict[str, float]:
    """Scale the pose's offset from the centre until it is feasible (shape kept)."""
    zf, center = full(z), load_space()["center"]
    if feasible(zf, m):
        return zf
    at = lambda s: {a: center[a] + s * (zf[a] - center[a]) for a in AXES}  # noqa: E731
    lo, hi = 0.0, 1.0
    for _ in range(steps):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if feasible(at(mid), m) else (lo, mid)
    return at(lo)


def axis_range(axis: str, step: float = 0.25, m: Manifest | None = None) -> tuple[float, float]:
    """Feasible interval of one axis with every other axis at the centre."""
    center = load_space()["center"][axis]
    ends = []
    for sign in (-1, 1):
        v = center
        while feasible({axis: v + sign * step}, m) and abs(v - center) < 200:
            v += sign * step
        ends.append(v)
    return ends[0], ends[1]


def gait(t: float, hz: float, stride: float = 0.0, steer: float = 0.0, lift: float = 8.0,
         **pose: float) -> dict[str, float]:
    """Diagonal trot at time t (s). The lifted pair leads the swing by a quarter
    cycle: stride > 0 walks forward, < 0 backward; steer > 0 turns left (it
    oscillates `spread`); `pose` holds other axes, e.g. height=45."""
    s = math.sin(2 * math.pi * hz * t)
    c = math.sin(2 * math.pi * (hz * t + 0.25))
    return full(pose) | {"stride": stride * s, "spread": steer * s, "lift": lift * c}


# ---------------------------------------------------------------- MuJoCo check


def physics_model():
    """models/sesame.xml without its visual meshes (massless, non-colliding),
    so the check runs without the Git LFS assets."""
    import mujoco

    spec = mujoco.MjSpec.from_file(str(MODEL_PATH))
    for g in list(spec.geoms):
        if g.type == mujoco.mjtGeom.mjGEOM_MESH:
            spec.delete(g)
    for mesh in list(spec.meshes):
        spec.delete(mesh)
    return spec.compile()


class Settler:
    """Place Sesame in a pose on the floor, hold it, report how it settled."""

    def __init__(self, m: Manifest | None = None):
        import mujoco

        self.mj = mujoco
        self.m = m or _manifest()
        self.model = physics_model()
        self.data = mujoco.MjData(self.model)
        ids = lambda kind, names: [mujoco.mj_name2id(self.model, kind, n) for n in names]  # noqa: E731
        self.qadr = [self.model.jnt_qposadr[i] for i in ids(mujoco.mjtObj.mjOBJ_JOINT, [j.name for j in self.m.joints])]
        self.act = ids(mujoco.mjtObj.mjOBJ_ACTUATOR, [j.name for j in self.m.joints])
        self.floor, self.torso_geom = ids(mujoco.mjtObj.mjOBJ_GEOM, ["floor", "torso_geom"])
        self.torso = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "torso")
        self.lower = set(ids(mujoco.mjtObj.mjOBJ_GEOM, [f"{leg}_lower_geom" for leg in LEGS]))
        self.upper = set(ids(mujoco.mjtObj.mjOBJ_GEOM, [f"{leg}_upper_geom" for leg in LEGS]))
        self.force = float(self.model.actuator_forcerange[0, 1])

    def place(self, q: Mapping[str, float], pitch: float = 0.0, roll: float = 0.0) -> None:
        """Joints at q (internal degrees), torso at the attitude, lowest point on the floor."""
        mj, d = self.mj, self.data
        mj.mj_resetData(self.model, d)
        a, b = -math.radians(pitch) / 2, -math.radians(roll) / 2
        qy, qx = np.array([math.cos(a), 0, math.sin(a), 0]), np.array([math.cos(b), math.sin(b), 0, 0])
        quat = np.zeros(4)
        mj.mju_mulQuat(quat, qy, qx)
        d.qpos[3:7] = quat
        d.qpos[2] = 0.5
        for adr, j in zip(self.qadr, self.m.joints):
            d.qpos[adr] = math.radians(q[j.name])
        mj.mj_forward(self.model, d)
        low = min(
            (d.geom_xpos[g] + d.geom_xmat[g].reshape(3, 3) @ (self.model.geom_size[g] * [x, y, z]))[2]
            for g in range(self.model.ngeom) if g != self.floor
            for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)
        )
        d.qpos[2] = 0.5 - low + 0.0005
        mj.mj_forward(self.model, d)

    def settle(self, q: Mapping[str, float], pitch: float = 0.0, roll: float = 0.0,
               seconds: float = 1.5) -> dict:
        mj, d = self.mj, self.data
        self.place(q, pitch, roll)
        for i, j in zip(self.act, self.m.joints):
            d.ctrl[i] = math.radians(q[j.name])
        n = int(seconds / self.model.opt.timestep)
        load, mid = 0.0, None
        for k in range(n):
            mj.mj_step(self.model, d)
            if k >= n // 2:
                load = max(load, float(np.max(np.abs(d.actuator_force))) / self.force)
                if mid is None:
                    mid = d.xpos[self.torso].copy()
        x = d.xmat[self.torso].reshape(3, 3)
        paws, body, femur = set(), False, False
        for c in d.contact[: d.ncon]:
            if self.floor not in (c.geom1, c.geom2):
                continue
            g = c.geom2 if c.geom1 == self.floor else c.geom1
            body |= g == self.torso_geom
            femur |= g in self.upper
            if g in self.lower:
                paws.add(g)
        return {
            "height_mm": 1000 * float(d.xpos[self.torso][2]),
            "pitch": math.degrees(math.asin(np.clip(x[2, 0], -1, 1))),
            "roll": -math.degrees(math.asin(np.clip(x[2, 1], -1, 1))),
            "body_down": body or femur,
            "paws_down": len(paws),
            "load": load,  # peak |servo torque| / stall torque, second half of the hold
            "drift_mm": 1000 * float(np.linalg.norm(d.xpos[self.torso] - mid)),
        }

    def drive(self, fn, seconds: float = 4.0, hz: float = 20.0, rate: float = 300.0) -> dict:
        """Stream fn(t) -> axes like the host spine: projected `pose` frames at hz,
        servos slewing at `rate` deg/s as the firmware does. Returns speeds in
        the robot's own heading frame (after a 0.5 s settle)."""
        mj, d, m = self.mj, self.data, self.m
        z0 = project(fn(0.0), m)
        q = decode(z0, m)
        self.place(q, z0["pitch"], z0["roll"])
        cur = np.array([q[j.name] for j in m.joints])
        d.ctrl[self.act] = np.radians(cur)
        dt = self.model.opt.timestep
        for _ in range(int(0.5 / dt)):
            mj.mj_step(self.model, d)
        heading = lambda: math.atan2(d.xmat[self.torso][3], d.xmat[self.torso][0])  # noqa: E731
        prev_p, prev_h = d.xpos[self.torso].copy(), heading()
        fwd = side = turned = tilt = 0.0
        body = False
        per, target = max(1, round(1 / hz / dt)), cur.copy()
        for k in range(int(seconds / dt)):
            if k % per == 0:
                q = decode(project(fn(k * dt), m), m)
                target = np.array([q[j.name] for j in m.joints])
            cur += np.clip(target - cur, -rate * dt, rate * dt)
            d.ctrl[self.act] = np.radians(cur)
            mj.mj_step(self.model, d)
            tilt = max(tilt, math.degrees(math.acos(min(1.0, d.xmat[self.torso][8]))))
            if k % 10 == 0:
                h, p = heading(), d.xpos[self.torso].copy()
                turned += (h - prev_h + math.pi) % (2 * math.pi) - math.pi
                dp, prev_p, prev_h = p - prev_p, p, h
                fwd += dp[0] * math.cos(h) + dp[1] * math.sin(h)
                side += -dp[0] * math.sin(h) + dp[1] * math.cos(h)
                body |= any(self.floor in (c.geom1, c.geom2) and self.torso_geom in (c.geom1, c.geom2)
                            for c in d.contact[: d.ncon])
        return {"forward_mm_s": 1000 * fwd / seconds, "side_mm_s": 1000 * side / seconds,
                "turn_deg_s": math.degrees(turned) / seconds, "max_tilt_deg": tilt, "body_down": body}

    def holds(self, z: Mapping[str, float]) -> tuple[bool, dict]:
        """Does the simulated robot hold this pose as commanded?"""
        tol = load_space()["sim_check"]
        zf = full(z)
        got = self.settle(decode(zf, self.m), zf["pitch"], zf["roll"])
        ok = (not got["body_down"] and got["paws_down"] >= 3
              and abs(got["pitch"] - zf["pitch"]) < tol["attitude_deg"]
              and abs(got["roll"] - zf["roll"]) < tol["attitude_deg"]
              and abs(got["height_mm"] - zf["height"]) < tol["height_mm"]
              and got["load"] < tol["load"] and got["drift_mm"] < tol["drift_mm"])
        return ok, got


# ---------------------------------------------------------------- text for LLMs

MEANING = {
    "surge": ("deg", "4本の足先をそろって前へ（胴体は後ろへ下がる）"),
    "spread": ("deg", "前脚は前へ・後脚は後ろへ開く（負で前後の脚を胴の下に寄せる）"),
    "yaw": ("deg", "右の足先は前・左は後ろ（足を着いたまま胴をひねる）"),
    "stride": ("deg", "対角ペア 右前+左後 を前・左前+右後 を後ろ（トロットの一歩）"),
    "height": ("mm", "胴体の高さ（しゃがむ／伸びる）"),
    "pitch": ("deg", "鼻先を上げる（負で下げる）"),
    "roll": ("deg", "右側を上げる（負で左側を上げる）"),
    "lift": ("mm", "対角ペア 右前+左後(+) または 左前+右後(-) の足を床から上げる。歩行専用"),
}


def describe() -> str:
    """The motion space as plain Japanese text for an LLM prompt, from motion_space.yaml."""
    space = load_space()
    c, r, b, g = space["center"], space["ranges"], space["budget"], space["gait"]
    off = lambda a, v: v - c[a]  # noqa: E731
    lines = [
        "# セサミの動作空間（8軸）",
        "四足ロボット「セサミ」の8個のサーボを、胴体を基準にした8本の軸で表す。"
        "値はすべて中心姿勢からの差分（中心 = 全部0。高さ0は胴体中心が床から"
        f"{c['height']:g} mm、脚は斜め45°のX字）。足の角度はコードが逆運動学で解き、4本の足先を床に着ける。",
        "",
        "## 軸（単位、意味、単独で動かせる範囲）",
    ]
    for a in AXES:
        unit, text = MEANING[a]
        lines.append(f"- {a} [{unit}]: {text}。{off(a, r[a][0]):+g}〜{off(a, r[a][1]):+g}")
    tilt = ", ".join(f"{off('height', h):+g}→±{t:g}" for h, t in space["tilt_by_height"].items())
    lines += [
        "",
        "## 組み合わせの予算（この内側ならどんな組み合わせでも立っていられる）",
        f"- |surge|+|spread|+|yaw|+|stride| ≤ {b['hip_l1_deg']:g}（どのhipサーボにも4軸の合計がかかる）",
        f"- height は {off('height', b['height_mm'][0]):+g}〜{off('height', b['height_mm'][1]):+g}、"
        f"|pitch|+|roll| ≤ {b['tilt_l1_fraction']:g} × その高さの傾き上限",
        f"- 高さごとの傾き上限（height差分→±度）: {tilt}。脚が短いので傾きは数度しか取れない",
        f"- |lift| ≤ {b['lift_mm']:g}。止まったまま lift すると2本足になって揺れるので、振動の中でだけ使う",
        "- 範囲を超えた姿勢は、中心に向かって縮めて再生される（形は保たれ、小さくなる）",
        "",
        "## 歩く・曲がる（対角トロット）",
        "lift を stride または spread より 1/4 周期先に振る（同じ hz、lift の phase を +0.25）。",
        f"- 前進: stride 振幅A・phase 0、lift 振幅8〜12・phase +0.25。速さ ≈ {g['forward_mm_s_per_deg_hz']:g}×A×hz mm/s",
        "- 後退: lift の phase を -0.25（= 0.75）にする",
        f"- 左旋回: spread 振幅A・phase 0、lift phase +0.25。≈ {g['turn_deg_s_per_deg_hz']:g}×A×hz °/s。"
        "右旋回は lift phase -0.25。yaw を振っても曲がらない",
        "- stride と spread を同時に振ると弧を描いて歩く",
        f"- hz は {g['hz'][0]:g}〜{g['hz'][1]:g}。サーボの速さの上限から 2π×hz×(stride振幅+spread振幅) ≤ 300 °/s"
        "（例: 2 Hz なら合計24°まで）。超えると遅くなる",
        "- lift が 4 mm 未満だと足が擦れて進まない",
        "",
        "## 表現のヒント",
        "- うなずき: pitch を振る。首かしげ・ゆらゆら: roll。のび／しゃがみ: height。",
        "- 足踏み: lift だけを振る。くねくね: yaw。胴を前後に揺らす: surge。",
        "- 片足を高く上げる手振りはこの空間では表せない（関節を直接動かす）",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- report


def report(samples: int = 800, seed: int = 0) -> None:
    """Recompute the numbers recorded in manifest/motion_space.yaml."""
    space = load_space()
    print("single-axis ranges at the centre (rules only):")
    for a in AXES:
        lo, hi = axis_range(a)
        print(f"  {a:7s} [{lo:7.2f}, {hi:7.2f}]   yaml {space['ranges'][a]}")
    box = space["safe_box"]
    corners = [{a: space["center"][a] + s * box[a] for a, s in zip(AXES, signs)}
               for signs in np.array(np.meshgrid(*[[-1, 1]] * len(AXES))).T.reshape(-1, len(AXES))]
    print(f"safe box corners feasible: {sum(feasible(c) for c in corners)}/{len(corners)}")
    settler, rng = Settler(), np.random.default_rng(seed)
    lo = np.array([r[0] for r in space["ranges"].values()])
    hi = np.array([r[1] for r in space["ranges"].values()])
    lo[AXES.index("lift")] = hi[AXES.index("lift")] = 0.0
    held = n = 0
    while n < samples:
        z = dict(zip(AXES, rng.uniform(lo, hi)))
        if feasible(z):
            n += 1
            held += settler.holds(z)[0]
    print(f"random feasible poses held in MuJoCo: {held}/{n} (seed {seed})")
    print("trot (lift 10 mm): forward mm/s by hz x stride; turn deg/s by hz x steer")
    for hz in (0.5, 1, 2, 3):
        fwd = [settler.drive(lambda t: gait(t, hz, stride=a, lift=10))["forward_mm_s"] for a in (5, 10, 20, 30)]
        turn = [settler.drive(lambda t: gait(t, hz, steer=a, lift=10))["turn_deg_s"] for a in (5, 10, 20, 30)]
        print(f"  hz {hz:3}: forward {np.round(fwd).astype(int)}  turn {np.round(turn).astype(int)}")


# ---------------------------------------------------------------- viewer


def viewer_data(m: Manifest | None = None) -> dict:
    """Everything sim/motion_space.js needs, as JSON-ready values."""
    m = m or _manifest()
    hips, feet = _legs(m)
    dims = dict(HIP_X=HIP_X, HIP_Y=HIP_Y, LEG_PLANE_DZ=LEG_PLANE_DZ, UPPER_LEN=UPPER_LEN,
                UPPER_HALF=list(UPPER_HALF), FOOT_LEN=FOOT_LEN, FOOT_HALF=list(FOOT_HALF),
                TORSO_HALF=list(TORSO_HALF), UPPER_MASS=UPPER_MASS, FOOT_MASS=FOOT_MASS, TORSO_MASS=TORSO_MASS)
    joints = [{"name": j.name, "leg": j.leg, "role": j.role, "sign": j.sign, "limits_deg": list(j.limits_deg),
               "internal_deg": [float(x) for x in np.degrees(m.internal_range(j))]} for j in m.joints]
    return {"axes": list(AXES), "legs": list(LEGS), "sx": SX.tolist(), "sy": SY.tolist(),
            "pattern": {k: v.tolist() for k, v in PATTERN.items()}, "hipPattern": HIP_PATTERN,
            "dims": dims, "space": load_space(), "joints": joints, "legHip": hips, "legFoot": feet,
            "neutral": m.neutral_deg, "meaning": MEANING, "text": describe()}


def viewer_html() -> str:
    """The self-contained interactive viewer (no network, no dependencies)."""
    here = Path(__file__).parent
    template = (here / "motion_space_viewer.html").read_text()
    data = json.dumps(viewer_data(), ensure_ascii=False, separators=(",", ":"))
    return template.replace("/*CORE*/", (here / "motion_space.js").read_text()).replace("/*DATA*/", data)


def firmware_header(html: str) -> str:
    """The viewer gzipped into a C++ header for the S3 firmware's /space page."""
    gz = gzip.compress(html.encode(), mtime=0)
    rows = ",\n".join(",".join(str(b) for b in gz[k:k + 40]) for k in range(0, len(gz), 40))
    return ("// Generated by `python -m sim.motion_space --firmware-header`; do not edit.\n"
            "// Motion-space viewer (sim2real sim/motion_space_viewer.html), gzip.\n#pragma once\n#include <stddef.h>\n"
            f"#include <stdint.h>\nconstexpr size_t SPACE_UI_GZ_LEN = {len(gz)};\n"
            f"constexpr uint8_t SPACE_UI_GZ[] = {{\n{rows}}};\n")


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if "--text" in args:
        print(describe())
    elif "--html" in args:
        VIEWER_PATH.parent.mkdir(parents=True, exist_ok=True)
        VIEWER_PATH.write_text(viewer_html())
        print(f"wrote {VIEWER_PATH}")
    elif "--firmware-header" in args:
        out = Path(args[args.index("--firmware-header") + 1])
        out.write_text(firmware_header(viewer_html()))
        print(f"wrote {out}")
    else:
        report()
