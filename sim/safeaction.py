"""SafeAction gate: the simulator-side implementation of manifest/safeaction.yaml.

Every command path into the simulated robot (and eventually the real one)
goes through `SafeActionGate`: soft-limit clamping, per-servo rate limiting,
watchdog with rest failsafe, and stop semantics. Policies and scripts never
write ctrl directly.

Time is robot time in milliseconds (sim time * 1000), not wall time, so the
gate is deterministic and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from sim.manifest import Manifest, load_manifest

SAFEACTION_PATH = Path(__file__).parent.parent / "manifest" / "safeaction.yaml"


def load_safeaction(path: Path = SAFEACTION_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


@dataclass
class SafeActionGate:
    manifest: Manifest
    config: dict
    # state (firmware degrees, channel order)
    current_deg: list[float] = field(default_factory=list)
    target_deg: list[float] = field(default_factory=list)
    last_command_ms: float = 0.0
    stopped: bool = False
    in_failsafe: bool = False

    @classmethod
    def create(cls, manifest: Manifest | None = None, config: dict | None = None):
        manifest = manifest or load_manifest()
        config = config or load_safeaction()
        neutral = manifest.neutral_deg
        start = [neutral] * len(manifest.joints)
        return cls(
            manifest=manifest,
            config=config,
            current_deg=list(start),
            target_deg=list(start),
        )

    # ---- command vocabulary ----

    def clamp(self, channel: int, deg: float) -> float:
        j = self.manifest.joints[channel]
        lo, hi = j.limits_deg
        return min(max(float(deg), lo), hi)

    def cmd_pose(self, now_ms: float, targets_deg: list[float]) -> bool:
        """Set 8 targets. Returns False (and freezes) on a faulty jump."""
        if len(targets_deg) != len(self.manifest.joints):
            return False
        max_jump = self.config["limits"]["max_jump_deg"]
        clamped = [self.clamp(ch, d) for ch, d in enumerate(targets_deg)]
        if any(abs(d - c) > max_jump for d, c in zip(clamped, self.current_deg)):
            self.cmd_stop(now_ms)
            return False
        self.target_deg = clamped
        self.last_command_ms = now_ms
        self.stopped = False
        self.in_failsafe = False
        return True

    def cmd_servo(self, now_ms: float, channel: int, deg: float) -> bool:
        if not 0 <= channel < len(self.manifest.joints):
            return False
        targets = list(self.target_deg)
        targets[channel] = deg
        return self.cmd_pose(now_ms, targets)

    def cmd_stop(self, now_ms: float) -> None:
        self.target_deg = list(self.current_deg)
        self.stopped = True
        self.last_command_ms = now_ms

    def cmd_rest(self, now_ms: float) -> None:
        rest = self.manifest.raw["poses"]["rest"]
        self.target_deg = [rest[j.name] for j in self.manifest.joints]
        self.stopped = False
        self.last_command_ms = now_ms

    def cmd_heartbeat(self, now_ms: float) -> None:
        self.last_command_ms = now_ms

    # ---- per-step output ----

    def step(self, now_ms: float, dt_ms: float) -> list[float]:
        """Advance rate-limited servo state; returns internal-radian ctrl."""
        timeout = self.config["watchdog"]["timeout_ms"]
        if not self.in_failsafe and now_ms - self.last_command_ms > timeout:
            # watchdog fired: approach the failsafe pose autonomously
            failsafe = self.config["watchdog"]["failsafe"]
            pose = self.manifest.raw["poses"][failsafe]
            self.target_deg = [pose[j.name] for j in self.manifest.joints]
            self.stopped = False
            self.in_failsafe = True
        max_step = self.config["limits"]["max_rate_deg_s"] * dt_ms / 1000.0
        for ch, (cur, tgt) in enumerate(zip(self.current_deg, self.target_deg)):
            delta = min(max(tgt - cur, -max_step), max_step)
            self.current_deg[ch] = cur + delta
        return [
            self.manifest.to_internal(j, self.current_deg[ch])
            for ch, j in enumerate(self.manifest.joints)
        ]
