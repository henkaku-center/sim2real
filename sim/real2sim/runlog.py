"""Run log: one robot run as JSON Lines (schema ``sesame-run-log`` version 1).

Line 1 is a header; every later line is one timestamped record.

Header (required keys)::

    {"type": "header", "schema": "sesame-run-log", "version": 1,
     "evidence": "measured" | "dry-run" | "synthetic",
     "joints": ["R1", ...],            # manifest joint names, manifest order
     "angle_convention": "...",        # firmware degrees, see ANGLE_CONVENTION
     "clocks": {"host": "...", ...},   # one description per clock used
     "command_interface": {"transport": ..., "mode": ..., "slew_rate_deg_s": 60.0 | null},
     "channels": {...}}                # one declaration per measured channel

Records (``t`` is seconds on the named ``clock``; clocks are NOT assumed to be
synchronised with each other — the fit estimates the video-to-host offset)::

    {"type": "command", "t": 1.2, "clock": "host", "text": "pose 90 ...",
     "targets_deg": {"R1": 90.0, ...}}          # targets optional (arm/off/...)
    {"type": "reply", "t": 1.21, "clock": "host", "text": "OK TARGETS ..."}
    {"type": "torso_pose", "t": 0.033, "clock": "video",
     "position_m": [x, y, z], "quaternion_wxyz": [w, x, y, z]}
    {"type": "imu", "t": 0.01, "clock": "device",
     "accel_m_s2": [x, y, z], "gyro_rad_s": [x, y, z]}

``torso_pose`` is the pose of the marker frame in the frame named by
``channels.torso_pose.frame``; position in metres, orientation as a unit
quaternion that rotates marker-frame vectors into that frame. ``imu`` is
reserved for a later sensor; its frame and units are declared the same way.

``evidence`` is the honesty label carried into every report: only a log
written by the recorder against real hardware may say ``measured``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

SCHEMA = "sesame-run-log"
VERSION = 1
EVIDENCE = ("measured", "dry-run", "synthetic")
RECORD_TYPES = ("command", "reply", "torso_pose", "imu")
ANGLE_CONVENTION = (
    "targets_deg are firmware degrees 0..180 at the servo boundary, neutral 90; "
    "internal q = deg2rad(deg - 90) * sign per manifest/robot.yaml"
)
_VECTORS = {
    "torso_pose": (("position_m", 3), ("quaternion_wxyz", 4)),
    "imu": (("accel_m_s2", 3), ("gyro_rad_s", 3)),
}


class RunLogError(ValueError):
    """Raised when a run log does not satisfy the schema."""


@dataclass
class RunLog:
    header: dict
    commands: list[dict] = field(default_factory=list)  # all command records
    replies: list[dict] = field(default_factory=list)
    pose_t: np.ndarray = field(default_factory=lambda: np.zeros(0))
    pose_position: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    pose_quaternion: np.ndarray = field(default_factory=lambda: np.zeros((0, 4)))
    imu_t: np.ndarray = field(default_factory=lambda: np.zeros(0))
    imu_accel: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    imu_gyro: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))

    @property
    def joints(self) -> list[str]:
        return list(self.header["joints"])

    @property
    def evidence(self) -> str:
        return self.header["evidence"]

    def targets(self) -> list[tuple[float, dict[str, float]]]:
        """Time-ordered (host seconds, {joint: firmware degrees}) target changes."""
        return [(c["t"], c["targets_deg"]) for c in self.commands if "targets_deg" in c]


def make_header(
    *,
    evidence: str,
    joints: Iterable[str],
    command_interface: dict,
    clocks: dict[str, str] | None = None,
    channels: dict | None = None,
    **extra,
) -> dict:
    header = {
        "type": "header",
        "schema": SCHEMA,
        "version": VERSION,
        "evidence": evidence,
        "joints": list(joints),
        "angle_convention": ANGLE_CONVENTION,
        "clocks": clocks or {"host": "seconds since the recorder started (time.monotonic)"},
        "command_interface": command_interface,
        "channels": channels or {},
    }
    header.update(extra)
    return header


def torso_pose_channel(
    *, frame: str, frame_definition: str, marker_origin_in_torso_m: list[float], **extra
) -> dict:
    """Header declaration for the ``torso_pose`` channel (frame and units)."""
    channel = {
        "source": "printed ArUco marker on the head lid, fixed camera",
        "frame": frame,
        "frame_definition": frame_definition,
        "position_unit": "m",
        "orientation": "unit quaternion w,x,y,z rotating marker-frame vectors into the frame",
        "body_frame": "marker frame: x toward the robot's face, y to its left, z up out of the lid",
        "marker_origin_in_torso_m": list(marker_origin_in_torso_m),
    }
    channel.update(extra)
    return channel


def _finite_vector(value, size: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == size
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value)
    )


def validate_header(header: dict) -> list[str]:
    errors = []
    if not isinstance(header, dict) or header.get("type") != "header":
        return ["line 1: first line must be the header record"]
    if header.get("schema") != SCHEMA:
        errors.append(f"header: schema must be {SCHEMA!r}")
    if header.get("version") != VERSION:
        errors.append(f"header: unsupported version {header.get('version')!r} (this reader: {VERSION})")
    if header.get("evidence") not in EVIDENCE:
        errors.append(f"header: evidence must be one of {EVIDENCE}")
    joints = header.get("joints")
    if not (isinstance(joints, list) and joints and all(isinstance(j, str) for j in joints)
            and len(set(joints)) == len(joints)):
        errors.append("header: joints must be a non-empty list of unique names")
    if not isinstance(header.get("angle_convention"), str):
        errors.append("header: angle_convention must state the degree convention")
    if not (isinstance(header.get("clocks"), dict) and header["clocks"]):
        errors.append("header: clocks must describe every clock used")
    interface = header.get("command_interface")
    if not isinstance(interface, dict) or "slew_rate_deg_s" not in interface:
        errors.append("header: command_interface.slew_rate_deg_s is required (null = no firmware ramp)")
    else:
        rate = interface["slew_rate_deg_s"]
        if rate is not None and not (isinstance(rate, (int, float)) and math.isfinite(rate) and rate > 0):
            errors.append("header: command_interface.slew_rate_deg_s must be positive or null")
    channels = header.get("channels")
    if not isinstance(channels, dict):
        errors.append("header: channels must be an object")
    else:
        for name, channel in channels.items():
            if name not in _VECTORS:
                errors.append(f"header: unknown channel {name!r}")
            elif not (isinstance(channel, dict) and isinstance(channel.get("frame"), str)):
                errors.append(f"header: channel {name} must state its frame")
        pose = channels.get("torso_pose")
        if isinstance(pose, dict) and not _finite_vector(pose.get("marker_origin_in_torso_m"), 3):
            errors.append("header: channels.torso_pose.marker_origin_in_torso_m must be x, y, z in metres")
    return errors


def validate_records(header: dict, records: Iterable[dict], first_line: int = 2) -> list[str]:
    errors: list[str] = []
    joints = set(header.get("joints") or [])
    clocks = header.get("clocks") or {}
    channels = header.get("channels") or {}
    last_t: dict[tuple[str, str], float] = {}
    for number, record in enumerate(records, first_line):
        where = f"line {number}"
        if not isinstance(record, dict) or record.get("type") not in RECORD_TYPES:
            errors.append(f"{where}: type must be one of {RECORD_TYPES}")
            continue
        kind = record["type"]
        t, clock = record.get("t"), record.get("clock")
        if not (isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t)):
            errors.append(f"{where}: t must be a finite number of seconds")
            continue
        if clock not in clocks:
            errors.append(f"{where}: clock {clock!r} is not declared in the header")
            continue
        stream = (kind, clock)
        if t < last_t.get(stream, -math.inf):
            errors.append(f"{where}: {kind} time goes backwards on clock {clock!r}")
        last_t[stream] = t
        if kind in ("command", "reply"):
            if not isinstance(record.get("text"), str):
                errors.append(f"{where}: {kind} needs the exact text sent or received")
            targets = record.get("targets_deg")
            if targets is not None:
                if kind != "command" or not isinstance(targets, dict) or not targets:
                    errors.append(f"{where}: targets_deg belongs to a command and must not be empty")
                    continue
                for joint, degrees in targets.items():
                    if joint not in joints:
                        errors.append(f"{where}: unknown joint {joint!r}")
                    elif not (isinstance(degrees, (int, float)) and not isinstance(degrees, bool)
                              and 0.0 <= degrees <= 180.0):
                        errors.append(f"{where}: {joint} target must be 0..180 firmware degrees")
        else:
            if kind not in channels:
                errors.append(f"{where}: channel {kind} is not declared in the header")
            for key, size in _VECTORS[kind]:
                if not _finite_vector(record.get(key), size):
                    errors.append(f"{where}: {key} must be {size} finite numbers")
            quaternion = record.get("quaternion_wxyz")
            if kind == "torso_pose" and _finite_vector(quaternion, 4):
                if abs(math.sqrt(sum(v * v for v in quaternion)) - 1.0) > 1e-3:
                    errors.append(f"{where}: quaternion_wxyz must have unit length")
    return errors


def validate(header: dict, records: Iterable[dict]) -> list[str]:
    """Return every schema violation (empty list = valid)."""
    errors = validate_header(header)
    return errors if errors else validate_records(header, records)


def read_lines(path: Path) -> tuple[dict, list[dict]]:
    header, records = None, []
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise RunLogError(f"{path}: line {number}: not JSON ({error.msg})") from error
            if header is None:
                header = record
            else:
                records.append(record)
    if header is None:
        raise RunLogError(f"{path}: empty run log")
    return header, records


def from_records(header: dict, records: list[dict], source: str = "run log") -> RunLog:
    """Validate and index records. Raises RunLogError listing the violations."""
    errors = validate(header, records)
    if errors:
        shown = "\n  ".join(errors[:10])
        more = f"\n  … and {len(errors) - 10} more" if len(errors) > 10 else ""
        raise RunLogError(f"{source}: invalid run log:\n  {shown}{more}")
    poses = [r for r in records if r["type"] == "torso_pose"]
    imu = [r for r in records if r["type"] == "imu"]
    return RunLog(
        header=header,
        commands=[r for r in records if r["type"] == "command"],
        replies=[r for r in records if r["type"] == "reply"],
        pose_t=np.array([r["t"] for r in poses], dtype=float),
        pose_position=np.array([r["position_m"] for r in poses], dtype=float).reshape(-1, 3),
        pose_quaternion=np.array([r["quaternion_wxyz"] for r in poses], dtype=float).reshape(-1, 4),
        imu_t=np.array([r["t"] for r in imu], dtype=float),
        imu_accel=np.array([r["accel_m_s2"] for r in imu], dtype=float).reshape(-1, 3),
        imu_gyro=np.array([r["gyro_rad_s"] for r in imu], dtype=float).reshape(-1, 3),
    )


def load(path: Path | str) -> RunLog:
    path = Path(path)
    header, records = read_lines(path)
    return from_records(header, records, source=str(path))


def write(path: Path | str, header: dict, records: Iterable[dict]) -> Path:
    """Validate, then write header + records as JSON Lines."""
    path = Path(path)
    records = list(records)
    from_records(header, records, source=str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in [header, *records]:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    return path


def pose_records(times, positions, quaternions, clock: str = "video", **extra) -> list[dict]:
    """Build ``torso_pose`` records from arrays (quaternions are renormalised)."""
    out = []
    for t, p, q in zip(times, positions, quaternions):
        q = np.asarray(q, dtype=float)
        q = q / np.linalg.norm(q)
        out.append({"type": "torso_pose", "t": round(float(t), 6), "clock": clock,
                    "position_m": [round(float(v), 6) for v in p],
                    "quaternion_wxyz": [round(float(v), 7) for v in q], **extra})
    return out


def with_torso_poses(path: Path | str, channel: dict, records: list[dict],
                     clock_description: str, out: Path | str | None = None) -> Path:
    """Add (or replace) the torso_pose channel of an existing log file."""
    header, existing = read_lines(Path(path))
    header = dict(header)
    header["channels"] = {**header.get("channels", {}), "torso_pose": channel}
    header["clocks"] = {**header.get("clocks", {}), records[0]["clock"]: clock_description} if records else header["clocks"]
    kept = [r for r in existing if r.get("type") != "torso_pose"]
    return write(out or path, header, kept + records)
