"""Load the canonical robot manifest and convert between angle conventions.

The manifest (manifest/robot.yaml) is the single source of truth. Internal
angles are radians with q = deg2rad(firmware_deg - neutral) * sign, so q = 0
is the rest pose for every joint.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest" / "robot.yaml"


@dataclass(frozen=True)
class Joint:
    name: str
    channel: int
    gpio_pin: int
    leg: str  # front_left | front_right | back_left | back_right
    role: str  # hip | foot
    limits_deg: tuple[float, float]  # firmware degrees, soft limits
    sign: int  # internal positive-direction multiplier


@dataclass(frozen=True)
class Manifest:
    raw: dict
    joints: tuple[Joint, ...]
    neutral_deg: float

    def joint(self, name: str) -> Joint:
        return next(j for j in self.joints if j.name == name)

    def to_internal(self, joint: Joint, firmware_deg: float) -> float:
        """Firmware degrees [0..180] -> internal radians (0 = rest)."""
        return math.radians(firmware_deg - self.neutral_deg) * joint.sign

    def to_firmware(self, joint: Joint, internal_rad: float) -> float:
        """Internal radians -> firmware degrees."""
        return math.degrees(internal_rad * joint.sign) + self.neutral_deg

    def internal_range(self, joint: Joint) -> tuple[float, float]:
        """Joint range in internal radians (sorted lo < hi)."""
        a = self.to_internal(joint, joint.limits_deg[0])
        b = self.to_internal(joint, joint.limits_deg[1])
        return (min(a, b), max(a, b))

    def pose_internal(self, pose_name: str) -> dict[str, float]:
        """Named pose (firmware degrees in manifest) -> internal radians."""
        pose = self.raw["poses"][pose_name]
        return {j.name: self.to_internal(j, pose[j.name]) for j in self.joints}


def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    with open(path) as f:
        raw = yaml.safe_load(f)
    joints = tuple(
        Joint(
            name=j["name"],
            channel=j["channel"],
            gpio_pin=j["gpio_pin"],
            leg=j["leg"],
            role=j["role"],
            limits_deg=(float(j["limits_deg"][0]), float(j["limits_deg"][1])),
            sign=int(j["sign"]),
        )
        for j in raw["joints"]
    )
    return Manifest(
        raw=raw,
        joints=joints,
        neutral_deg=float(raw["conventions"]["firmware_neutral_deg"]),
    )
