"""Fit simulation parameters to run logs by matching torso height, roll and pitch.

For each run the logged servo targets are replayed through the command
interface's ramp into a MuJoCo rollout; the simulated torso motion is compared
with the marker track, and ``scipy.optimize.least_squares`` adjusts the
parameters. Everything is addressed by element name on a compiled ``MjModel``
(servo joints from the manifest, their position actuators, the free-joint
torso), so it does not depend on how the model was generated.

Both tracks are expressed relative to the pose the robot holds in the rest
window at the start of the run. That removes the unknown camera/world frame;
it assumes the run starts at rest on the floor and that the marker frame is
aligned with the torso frame (see reference/REAL2SIM-CAPTURE.md).

Honesty rules built in here:
- a parameter the torso track cannot determine is left at its nominal value
  and reported as such, never returned as a fitted number;
- the result carries the evidence label of its logs (synthetic or measured),
  and logs with different labels cannot be mixed in one fit.
"""

from __future__ import annotations

import copy
import math
import os
from dataclasses import asdict, dataclass, field

import mujoco
import numpy as np
from mujoco import rollout as mj_rollout
from scipy.optimize import least_squares

from sim.manifest import Manifest, load_manifest
from sim.real2sim import geometry as g
from sim.real2sim.runlog import RunLog

# Residual units, in the resting torso's frame (x forward, y left, z up). Height,
# roll and pitch follow the legs directly; forward/sideways position and yaw
# integrate foot slip, which is sensitive to tiny changes (in simulation and on a
# real floor), so those channels get a much larger unit.
SIGMA_POSITION_M = np.array([np.inf, np.inf, 0.0015])
SIGMA_ATTITUDE_RAD = np.array([math.radians(1.5), math.radians(1.5), np.inf])
RESIDUAL_CLIP = 50.0  # a diverged rollout must not produce infinite residuals
REST_SETTLE_S = 0.8  # skip this much of the rest hold before averaging the reference pose
END_MARGIN_S = 0.35  # ignore samples this close to the end of the commands
OFFSET_WINDOW_S = 0.3  # least squares may move the time offset this far from the coarse estimate
PRIOR_WEIGHT = 0.05  # weak pull toward nominal, in residual units per parameter scale
# Central-difference steps in parameter scales, coarse to fine. Foot slip makes the
# simulated track rough at the sub-millimetre level, so slopes are taken across
# wide secants first and only then refined.
FD_STEPS = (1.0, 0.35)
UNIDENTIFIABLE_STD = 0.5  # freeze a parameter that cannot be resolved to half its scale


@dataclass(frozen=True)
class ParamDef:
    name: str
    label: str
    unit: str
    semantics: str
    scale: float  # plausible uncertainty; the optimiser works in these units
    lower: float
    upper: float


PARAMS = {p.name: p for p in [
    ParamDef("kp_scale", "Servo position gain", "× model", "multiplies each servo actuator's kp", 0.3, 0.2, 5.0),
    ParamDef("kv", "Servo damping gain", "N·m·s/rad", "set on all servo actuators", 0.002, 0.0, 0.01),
    ParamDef("torque_limit_scale", "Servo torque limit", "× model", "multiplies each servo's force range", 0.3, 0.2, 5.0),
    ParamDef("speed_limit", "Servo speed limit", "deg/s", "rate limit on each servo's position reference", 150.0, 30.0, 2000.0),
    ParamDef("joint_damping_scale", "Joint damping", "× model", "multiplies each servo joint's damping", 0.5, 0.05, 20.0),
    ParamDef("armature", "Joint armature", "kg·m²", "set on all servo joints", 1e-4, 0.0, 2e-3),
    ParamDef("friction", "Foot–floor sliding friction", "–", "set on the floor and every robot collision geom", 0.3, 0.05, 3.0),
    ParamDef("mass_scale", "Mass scale", "× model", "multiplies every robot body's mass and inertia", 0.2, 0.3, 3.0),
]}
TIME_OFFSET = ParamDef("time_offset", "Command-to-video time offset", "s",
                       "host time = video time + offset", 0.02, -math.inf, math.inf)
DEFAULT_PARAMS = tuple(PARAMS)


class ModelView:
    """Name-based access to the servo joints, actuators and torso of a model."""

    def __init__(self, model: mujoco.MjModel, manifest: Manifest | None = None):
        self.model = model
        self.manifest = manifest or load_manifest()
        self.joint_names = [j.name for j in self.manifest.joints]
        joints = []
        for name in self.joint_names:
            joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if joint < 0:
                raise ValueError(f"model has no joint named {name!r} (manifest joint)")
            joints.append(joint)
        self.dofs = np.array([model.jnt_dofadr[j] for j in joints])
        actuators = []
        for name, joint in zip(self.joint_names, joints):
            found = [a for a in range(model.nu)
                     if model.actuator_trntype[a] == mujoco.mjtTrn.mjTRN_JOINT and model.actuator_trnid[a, 0] == joint]
            if len(found) != 1:
                raise ValueError(f"expected exactly one actuator on joint {name!r}, found {len(found)}")
            a = found[0]
            position = (model.actuator_gaintype[a] == mujoco.mjtGain.mjGAIN_FIXED
                        and model.actuator_biastype[a] == mujoco.mjtBias.mjBIAS_AFFINE
                        and model.actuator_gainprm[a, 0] == -model.actuator_biasprm[a, 1])
            if not position:
                raise ValueError(f"actuator on joint {name!r} is not a position actuator")
            actuators.append(a)
        self.actuators = np.array(actuators)
        free = [j for j in range(model.njnt) if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE]
        if not free:
            raise ValueError("model has no free joint: cannot locate the torso")
        self.root_qpos = int(model.jnt_qposadr[free[0]])
        self.torso = int(model.jnt_bodyid[free[0]])
        self.robot_bodies = np.array([b for b in range(model.nbody) if model.body_rootid[b] == self.torso])
        self.contact_geoms = np.array([i for i in range(model.ngeom)
                                       if model.geom_contype[i] or model.geom_conaffinity[i]])
        self.signs = np.array([j.sign for j in self.manifest.joints], dtype=float)

    def nominal(self, name: str) -> float:
        m = self.model
        if name == "kv":
            return float(-m.actuator_biasprm[self.actuators, 2].mean()) + 0.0
        if name == "armature":
            return float(m.dof_armature[self.dofs].mean())
        if name == "friction":
            return float(m.geom_friction[self.contact_geoms, 0].max())
        if name == "speed_limit":
            return 60.0 / float(self.manifest.raw["servo_model"]["speed_s_per_60deg_at_4v8"])
        if name in PARAMS:
            return 1.0
        raise KeyError(name)

    def physical(self, name: str, value: float) -> tuple[float, str] | None:
        """Scale parameters as the physical mean they imply (for reports)."""
        m = self.model
        if name == "kp_scale":
            return value * float(m.actuator_gainprm[self.actuators, 0].mean()), "N·m/rad"
        if name == "torque_limit_scale":
            return value * float(m.actuator_forcerange[self.actuators, 1].mean()), "N·m"
        if name == "joint_damping_scale":
            return value * float(m.dof_damping[self.dofs].mean()), "N·m·s/rad"
        if name == "mass_scale":
            return value * float(m.body_mass[self.robot_bodies].sum()), "kg total"
        return None

    def apply(self, values: dict[str, float]) -> mujoco.MjModel:
        """Return a copy of the model with the parameter values applied."""
        base, m = self.model, copy.copy(self.model)
        a, d = self.actuators, self.dofs
        if "kp_scale" in values:
            m.actuator_gainprm[a, 0] = base.actuator_gainprm[a, 0] * values["kp_scale"]
            m.actuator_biasprm[a, 1] = base.actuator_biasprm[a, 1] * values["kp_scale"]
        if "kv" in values:
            m.actuator_biasprm[a, 2] = -values["kv"]
        if "torque_limit_scale" in values:
            if not base.actuator_forcelimited[a].all():
                raise ValueError("torque_limit_scale needs force-limited servo actuators")
            m.actuator_forcerange[a] = base.actuator_forcerange[a] * values["torque_limit_scale"]
        if "joint_damping_scale" in values:
            m.dof_damping[d] = base.dof_damping[d] * values["joint_damping_scale"]
        if "armature" in values:
            m.dof_armature[d] = values["armature"]
        if "friction" in values:
            m.geom_friction[self.contact_geoms, 0] = values["friction"]
        if "mass_scale" in values:
            m.body_mass[self.robot_bodies] = base.body_mass[self.robot_bodies] * values["mass_scale"]
            m.body_inertia[self.robot_bodies] = base.body_inertia[self.robot_bodies] * values["mass_scale"]
        if {"armature", "mass_scale"} & set(values):
            mujoco.mj_setConst(m, mujoco.MjData(m))  # refresh inertia-derived constants
        return m


# ---- commands -> control ----------------------------------------------------


def ramp(target: np.ndarray, rate_per_step: float | None, start: np.ndarray) -> np.ndarray:
    """Rate-limit a (nstep, n) target array; ``None`` or a large rate is a no-op.

    Each step moves at most ``rate_per_step`` toward the target, as the
    firmware's slew limiter does.
    """
    if rate_per_step is None or not np.isfinite(rate_per_step):
        return target
    if np.abs(np.diff(target, axis=0, prepend=start[None])).max() <= rate_per_step:
        return target
    out = np.empty_like(target)
    current = start.astype(float).copy()
    changes = np.flatnonzero(np.any(np.diff(target, axis=0) != 0.0, axis=1)) + 1
    if len(changes) <= len(target) // 8:  # piecewise-constant targets: closed form per segment
        edges = [0, *changes.tolist(), len(target)]
        for a, b in zip(edges[:-1], edges[1:]):
            delta = target[a] - current
            covered = np.minimum(np.arange(1, b - a + 1)[:, None] * rate_per_step, np.abs(delta))
            out[a:b] = current + np.sign(delta) * covered
            current = out[b - 1].copy()
        return out
    for i in range(len(target)):
        current += np.clip(target[i] - current, -rate_per_step, rate_per_step)
        out[i] = current
    return out


def command_reference(log: RunLog, view: ModelView, dt: float, nstep: int) -> np.ndarray:
    """Logged targets -> (nstep, nu) position references in internal radians.

    Zero-order hold of the logged targets, then the command interface's ramp
    (``command_interface.slew_rate_deg_s``) in firmware degrees, starting from
    neutral exactly as the reference firmware does after ``arm``.
    """
    neutral = view.manifest.neutral_deg
    names = view.joint_names
    degrees = np.full((nstep, len(names)), neutral)
    for t, targets in log.targets():
        first = min(max(int(math.ceil(t / dt)), 0), nstep)
        for name, value in targets.items():
            degrees[first:, names.index(name)] = value
    rate = log.header["command_interface"]["slew_rate_deg_s"]
    degrees = ramp(degrees, rate * dt if rate else None, np.full(len(names), neutral))
    ctrl = np.zeros((nstep, view.model.nu))
    ctrl[:, view.actuators] = np.radians(degrees - neutral) * view.signs
    return ctrl


# ---- runs -------------------------------------------------------------------


@dataclass
class Run:
    name: str
    log: RunLog
    nstep: int
    ctrl: np.ndarray  # (nstep, nu) before the servo speed limit
    rest: tuple[float, float]  # rest window on the command clock
    t_end: float
    marker_origin: np.ndarray  # marker centre in the torso frame, metres
    offset0: float = 0.0  # coarse video -> command clock offset
    t_video: np.ndarray = field(default_factory=lambda: np.zeros(0))  # samples used
    meas_p: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))  # torso motion relative to rest
    meas_q: np.ndarray = field(default_factory=lambda: np.zeros((0, 4)))


def _measured_relative(run: Run, offset: float, min_rest: int = 3):
    """Measured torso motion relative to the rest window, for a given offset."""
    log = run.log
    tau = log.pose_t + offset
    rest = (tau >= run.rest[0]) & (tau <= run.rest[1])
    if rest.sum() < min_rest:
        return None
    ref_p = log.pose_position[rest].mean(axis=0)
    ref_q = g.mean(log.pose_quaternion[rest])
    motion = (tau > run.rest[1]) & (tau < run.t_end - END_MARGIN_S)
    p, q = g.relative(ref_p, ref_q, log.pose_position[motion], log.pose_quaternion[motion])
    # Marker motion -> torso motion: the marker sits at marker_origin in the torso frame.
    p = p + run.marker_origin - g.rotate(q, run.marker_origin)
    return log.pose_t[motion], p, q


def _sample(track_p: np.ndarray, track_q: np.ndarray, dt: float, tau: np.ndarray):
    """Interpolate a simulated track (steps 0..nstep) at command-clock times."""
    x = np.clip(tau / dt, 0.0, len(track_p) - 1.000001)
    i = np.floor(x).astype(int)
    f = (x - i)[:, None]
    q0, q1 = track_q[i], track_q[i + 1]
    q1 = np.where(np.sum(q0 * q1, axis=1, keepdims=True) < 0.0, -q1, q1)
    return track_p[i] * (1 - f) + track_p[i + 1] * f, g.normalize(q0 * (1 - f) + q1 * f)


def _sim_relative(run: Run, dt: float, track_p, track_q, tau):
    ref = int(round(0.5 * (run.rest[0] + run.rest[1]) / dt))
    p, q = _sample(track_p, track_q, dt, tau)
    return g.relative(track_p[ref], track_q[ref], p, q)


def _errors(sim_p, sim_q, meas_p, meas_q):
    """Position error (m) and attitude error (rotation vector, rad) per sample."""
    return sim_p - meas_p, g.rotvec(g.mul(g.conj(meas_q), sim_q))


def rms(position_error: np.ndarray, attitude_error: np.ndarray) -> dict[str, float]:
    """Sim-versus-measured RMS: all axes, and the slip-insensitive part on its own."""
    def root(values):
        return float(np.sqrt(values.sum(axis=1).mean())) if len(values) else float("nan")
    p2, a2 = position_error ** 2, attitude_error ** 2
    return {"position_mm": 1000.0 * root(p2), "attitude_deg": math.degrees(root(a2)),
            "height_mm": 1000.0 * root(p2[:, 2:]), "tilt_deg": math.degrees(root(a2[:, :2]))}


def prepare_run(log: RunLog, view: ModelView, name: str) -> Run:
    if "torso_pose" not in log.header["channels"] or not len(log.pose_t):
        raise ValueError(f"{name}: the log has no torso_pose samples; run the marker tracker first")
    targets = log.targets()
    if not targets:
        raise ValueError(f"{name}: the log has no commanded targets")
    dt = float(view.model.opt.timestep)
    offs = [c["t"] for c in log.commands if c["text"] == "off" and c["t"] > targets[-1][0]]
    t_end = offs[0] if offs else targets[-1][0] + 1.0
    first = targets[0][0]
    second = targets[1][0] if len(targets) > 1 else t_end
    if second - first < REST_SETTLE_S + 0.3:
        raise ValueError(f"{name}: the run must start with a rest hold of at least {REST_SETTLE_S + 0.3:.1f} s")
    nstep = int(math.ceil(t_end / dt))
    return Run(name=name, log=log, nstep=nstep, ctrl=command_reference(log, view, dt, nstep),
               rest=(first + REST_SETTLE_S, second - 0.1), t_end=t_end,
               marker_origin=np.array(log.header["channels"]["torso_pose"]["marker_origin_in_torso_m"], dtype=float))


# ---- simulation -------------------------------------------------------------


class Simulator:
    """Batched, deterministic rollouts of parameter sets (mujoco.rollout)."""

    def __init__(self, view: ModelView, threads: int | None = None):
        self.view = view
        self.dt = float(view.model.opt.timestep)
        self.threads = threads or min(os.cpu_count() or 1, 8)
        self.pool = mj_rollout.Rollout(nthread=self.threads)
        self.datas = [mujoco.MjData(view.model) for _ in range(self.threads)]
        data = mujoco.MjData(view.model)
        kind = mujoco.mjtState.mjSTATE_FULLPHYSICS
        self.state0 = np.zeros(mujoco.mj_stateSize(view.model, kind))
        mujoco.mj_getState(view.model, data, self.state0, kind)

    def close(self) -> None:
        self.pool.close()

    def tracks(self, run: Run, values: list[dict[str, float]]):
        """Torso position/quaternion tracks (k, nstep + 1, 3 | 4) for k parameter sets."""
        view, k = self.view, len(values)
        models = [view.apply(v) for v in values]
        start = run.ctrl[0]
        ctrl = np.stack([ramp(run.ctrl, math.radians(v["speed_limit"]) * self.dt if "speed_limit" in v else None,
                              start) for v in values])
        state, _ = self.pool.rollout(models, self.datas, np.tile(self.state0, (k, 1)), ctrl)
        qpos = np.concatenate([np.tile(self.state0[None, None, :], (k, 1, 1)), state], axis=1)[:, :, 1:]
        root = view.root_qpos
        return qpos[:, :, root:root + 3], qpos[:, :, root + 3:root + 7]


def coarse_offset(run: Run, track_p, track_q, dt: float, step: float = 0.02) -> float:
    """Grid search for the video->command offset against the nominal rollout."""
    t = run.log.pose_t
    best, best_cost = None, math.inf
    span = run.t_end - END_MARGIN_S - run.rest[1]
    period = float(np.median(np.diff(t))) if len(t) > 1 else 1.0
    needed = max(8, int(0.6 * span / period))
    for offset in np.arange(run.rest[0] - t.max(), run.t_end - t.min(), step):
        relative = _measured_relative(run, offset)
        if relative is None or len(relative[0]) < needed:
            continue
        t_video, p, q = relative
        sim_p, sim_q = _sim_relative(run, dt, track_p, track_q, t_video + offset)
        e_p, e_q = _errors(sim_p, sim_q, p, q)
        cost = float(((e_p / SIGMA_POSITION_M) ** 2).sum(axis=1).mean()
                     + ((e_q / SIGMA_ATTITUDE_RAD) ** 2).sum(axis=1).mean())
        if not math.isfinite(cost):
            continue
        if cost < best_cost:
            best, best_cost = float(offset), cost
    if best is None:
        raise ValueError(f"{run.name}: the video does not cover the rest hold and the motion; "
                         "record from before the run starts until after it ends")
    return best


# ---- results ----------------------------------------------------------------


@dataclass
class ParamResult:
    name: str
    label: str
    unit: str
    semantics: str
    nominal: float
    value: float
    std: float | None  # one-sigma from the fit, None when not fitted
    status: str  # nominal | fitted from synthetic data | fitted from a measured run | measured directly
    note: str = ""
    physical: str = ""  # e.g. "0.60 -> 0.74 N·m/rad"


@dataclass
class RunResult:
    name: str
    evidence: str
    time_offset_s: float
    t: list[float]  # command-clock seconds of each compared sample
    measured: list[list[float]]  # x, y, z (m) + rotation vector (rad), torso motion relative to rest
    before: list[list[float]]
    after: list[list[float]]
    rms_before: dict[str, float]  # position_mm, attitude_deg, height_mm, tilt_deg
    rms_after: dict[str, float]


@dataclass
class FitResult:
    evidence: str
    params: list[ParamResult]
    runs: list[RunResult]
    rms_before: dict[str, float]
    rms_after: dict[str, float]
    samples: int
    evaluations: int
    sigma_position_mm: tuple = tuple(1000.0 * SIGMA_POSITION_M)
    sigma_attitude_deg: tuple = tuple(np.degrees(SIGMA_ATTITUDE_RAD))
    notes: list[str] = field(default_factory=list)

    def value(self, name: str) -> float:
        return next(p.value for p in self.params if p.name == name)

    def to_json(self) -> dict:
        return asdict(self)


STATUS = {"synthetic": "fitted from synthetic data", "measured": "fitted from a measured run"}


def _format(value: float) -> str:
    return f"{value:.4g}"


def fit(model: mujoco.MjModel, logs: dict[str, RunLog], params=DEFAULT_PARAMS, *,
        manifest: Manifest | None = None, fixed: dict[str, tuple[float, str]] | None = None,
        loss: str = "soft_l1", max_evaluations: int = 8, threads: int | None = None) -> FitResult:
    """Fit ``params`` (names from PARAMS) plus one time offset per run.

    ``fixed`` maps a parameter to (value, provenance) for quantities measured
    directly, e.g. a weighed mass; they are applied and never fitted.
    """
    evidences = {log.evidence for log in logs.values()}
    if len(evidences) != 1 or evidences - set(STATUS):
        raise ValueError(f"all logs must share one evidence label out of {sorted(STATUS)}; got {sorted(evidences)}")
    evidence = evidences.pop()
    unknown = [p for p in [*params, *(fixed or {})] if p not in PARAMS]
    if unknown:
        raise ValueError(f"unknown parameters {unknown}; choose from {list(PARAMS)}")
    fixed = dict(fixed or {})
    names = [p for p in params if p not in fixed]
    view = ModelView(model, manifest)
    sim = Simulator(view, threads)
    try:
        return _fit(view, sim, logs, names, fixed, evidence, loss, max_evaluations)
    finally:
        sim.close()


def _fit(view, sim, logs, names, fixed, evidence, loss, max_evaluations) -> FitResult:
    dt = sim.dt
    runs = [prepare_run(log, view, name) for name, log in logs.items()]
    constants = {name: value for name, (value, _) in fixed.items()}
    nominal = {name: view.nominal(name) for name in PARAMS}
    base = {**{name: nominal[name] for name in names}, **constants}

    # Coarse time sync against the nominal model, then freeze the sample set.
    for run in runs:
        track_p, track_q = sim.tracks(run, [base])
        run.offset0 = coarse_offset(run, track_p[0], track_q[0], dt)
        run.t_video, run.meas_p, run.meas_q = _measured_relative(run, run.offset0)
    samples = sum(len(run.t_video) for run in runs)

    # Optimiser variables: physical parameters, then one time offset per run, in scale units.
    defs = [PARAMS[name] for name in names] + [TIME_OFFSET] * len(runs)
    x0 = np.array([nominal[name] for name in names] + [run.offset0 for run in runs])
    scale = np.array([d.scale for d in defs])
    lower = np.array([PARAMS[name].lower for name in names] + [run.offset0 - OFFSET_WINDOW_S for run in runs])
    upper = np.array([PARAMS[name].upper for name in names] + [run.offset0 + OFFSET_WINDOW_S for run in runs])
    n_physical = len(names)
    active = np.ones(len(x0), dtype=bool)
    evaluations = 0

    def run_errors(run, track_p, track_q, offset):
        sim_p, sim_q = _sim_relative(run, dt, track_p, track_q, run.t_video + offset)
        return _errors(sim_p, sim_q, run.meas_p, run.meas_q)

    def residual_batch(xs: np.ndarray) -> np.ndarray:
        """Residuals (k, m) for k full parameter vectors (physical units)."""
        nonlocal evaluations
        evaluations += len(xs)
        values = [{**constants, **dict(zip(names, x[:n_physical]))} for x in xs]
        rows = [[] for _ in xs]
        for r, run in enumerate(runs):
            track_p, track_q = sim.tracks(run, values)
            for k, x in enumerate(xs):
                e_p, e_q = run_errors(run, track_p[k], track_q[k], x[n_physical + r])
                rows[k] += [(e_p / SIGMA_POSITION_M).ravel(), (e_q / SIGMA_ATTITUDE_RAD).ravel()]
        prior = PRIOR_WEIGHT * (xs - x0) / scale
        data = np.stack([np.concatenate(row) for row in rows])
        data = np.clip(np.nan_to_num(data, nan=RESIDUAL_CLIP, posinf=RESIDUAL_CLIP, neginf=-RESIDUAL_CLIP),
                       -RESIDUAL_CLIP, RESIDUAL_CLIP)
        return np.hstack([data, prior])

    def expand(u: np.ndarray) -> np.ndarray:
        x = x0.copy()
        x[active] = x0[active] + u * scale[active]
        return x

    def residual(u: np.ndarray) -> np.ndarray:
        return residual_batch(expand(u)[None])[0]

    def jacobian(u: np.ndarray, step: float = FD_STEPS[0]) -> np.ndarray:
        """Central differences over all active parameters in one batch of rollouts."""
        x = expand(u)
        index = np.flatnonzero(active)
        up = np.minimum(x[index] + step * scale[index], upper[index])
        down = np.maximum(x[index] - step * scale[index], lower[index])
        xs = np.tile(x, (2 * len(index), 1))
        for k, i in enumerate(index):
            xs[2 * k, i], xs[2 * k + 1, i] = up[k], down[k]
        r = residual_batch(xs)
        return ((r[0::2] - r[1::2]) / ((up - down) / scale[index])[:, None]).T

    # Screen: a parameter whose own effect on the track is below the noise stays nominal.
    notes: dict[int, str] = {}
    j0 = jacobian(np.zeros(active.sum()))
    for i in range(n_physical):
        norm = float(np.linalg.norm(j0[:-len(x0), i]))
        if norm == 0.0 or 1.0 / norm > UNIDENTIFIABLE_STD:
            active[i] = False
            notes[i] = ("not identifiable from these runs: its effect on torso height, roll and pitch is too "
                        f"small to resolve it to within {_format(UNIDENTIFIABLE_STD * scale[i])} {defs[i].unit}, "
                        "so it stays nominal")

    u_lower, u_upper = (lower[active] - x0[active]) / scale[active], (upper[active] - x0[active]) / scale[active]
    u = np.zeros(active.sum())
    for step in FD_STEPS:
        solution = least_squares(residual, u, jac=lambda v, h=step: jacobian(v, h), bounds=(u_lower, u_upper),
                                 loss=loss, f_scale=3.0, max_nfev=max_evaluations, xtol=1e-4, ftol=1e-6)
        u = np.clip(solution.x, u_lower, u_upper)
    x = expand(u)

    # One-sigma uncertainty from the Gauss-Newton covariance, inflated by the misfit.
    jac = jacobian(u, FD_STEPS[-1])
    final = residual(u)
    dof = max(len(final) - active.sum(), 1)
    inflation = max(1.0, float(final @ final) / dof)
    covariance = np.linalg.pinv(jac.T @ jac) * inflation
    std = np.full(len(x0), np.nan)
    # Never claim finer resolution than the smallest secant the search used: below
    # that the simulated track is rough (foot slip), so the formal value is optimistic.
    std[active] = np.maximum(np.sqrt(np.diag(covariance)), FD_STEPS[-1]) * scale[active]

    def metrics(vector):
        values = [{**constants, **dict(zip(names, vector[:n_physical]))}]
        out = []
        for r, run in enumerate(runs):
            track_p, track_q = sim.tracks(run, values)
            out.append(run_errors(run, track_p[0], track_q[0], vector[n_physical + r]))
        return out

    before, after = metrics(x0), metrics(x)

    def series(run, errors):
        e_p, e_q = errors
        return np.hstack([run.meas_p + e_p, g.rotvec(g.mul(run.meas_q, g.from_rotvec(e_q)))])

    run_results = []
    for r, run in enumerate(runs):
        measured = np.hstack([run.meas_p, g.rotvec(run.meas_q)])
        run_results.append(RunResult(
            name=run.name, evidence=run.log.evidence, time_offset_s=float(x[n_physical + r]),
            t=np.round(run.t_video + x[n_physical + r], 4).tolist(),
            measured=np.round(measured, 6).tolist(),
            before=np.round(series(run, before[r]), 6).tolist(),
            after=np.round(series(run, after[r]), 6).tolist(),
            rms_before=rms(*before[r]), rms_after=rms(*after[r])))

    def overall(errors):
        return rms(np.vstack([e[0] for e in errors]), np.vstack([e[1] for e in errors]))

    results = []
    for i, name in enumerate(names):
        definition = PARAMS[name]
        fitted = bool(active[i])
        note = notes.get(i, "")
        if fitted and std[i] > UNIDENTIFIABLE_STD * scale[i]:
            note = (f"weakly determined (±{_format(std[i])} {definition.unit}): its effect overlaps "
                    "another parameter's; treat the value as provisional")
        physical = view.physical(name, 1.0)
        results.append(ParamResult(
            name=name, label=definition.label, unit=definition.unit, semantics=definition.semantics,
            nominal=nominal[name], value=float(x[i]) if fitted else nominal[name],
            std=float(std[i]) if fitted else None,
            status=STATUS[evidence] if fitted else "nominal", note=note,
            physical=(f"{_format(physical[0] * nominal[name])} → {_format(physical[0] * x[i])} {physical[1]}"
                      if physical and fitted else "")))
    for name, (value, provenance) in fixed.items():
        definition = PARAMS[name]
        results.append(ParamResult(name=name, label=definition.label, unit=definition.unit,
                                   semantics=definition.semantics, nominal=nominal[name], value=float(value),
                                   std=None, status="measured directly", note=provenance))
    for r, run in enumerate(runs):
        i = n_physical + r
        results.append(ParamResult(
            name=f"time_offset[{run.name}]", label=f"{TIME_OFFSET.label} ({run.name})", unit="s",
            semantics=TIME_OFFSET.semantics, nominal=float("nan"), value=float(x[i]), std=float(std[i]),
            status=STATUS[evidence], note=f"coarse estimate {run.offset0:.3f} s; there is no nominal value"))

    fit_notes = []
    if evidence == "synthetic":
        fit_notes.append("Synthetic data: this validates the pipeline only. No robot was measured.")
    if not solution.success:
        fit_notes.append(f"Optimiser stopped early: {solution.message}")
    return FitResult(evidence=evidence, params=results, runs=run_results, rms_before=overall(before),
                     rms_after=overall(after), samples=samples, evaluations=evaluations, notes=fit_notes)
