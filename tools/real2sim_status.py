"""Evidence state of sim-to-real calibration, for tools/check_design.py.

Reads committed evidence only: run logs under reference/evidence/real2sim/
and reference/real2sim/measurements.yaml. Standard library plus PyYAML.
"""
import json
from pathlib import Path

import yaml

EVIDENCE_DIR = "reference/evidence/real2sim"
MEASUREMENTS = "reference/real2sim/measurements.yaml"


def measured_runs(root: Path) -> list[str]:
    """Committed run logs that claim a real robot and carry a torso track."""
    found = []
    for path in sorted((root / EVIDENCE_DIR).glob("*.jsonl")):
        try:
            with open(path, encoding="utf-8") as f:
                header = json.loads(f.readline())
        except (OSError, ValueError):
            continue
        if header.get("evidence") == "measured" and "torso_pose" in header.get("channels", {}):
            found.append(str(path.relative_to(root)))
    return found


def weighed(root: Path) -> bool:
    try:
        data = yaml.safe_load((root / MEASUREMENTS).read_text()) or {}
    except OSError:
        return False
    return (data.get("masses_g") or {}).get("robot_complete_with_battery") is not None


def stage(root: Path) -> dict:
    runs = measured_runs(root)
    return {
        "stage": "Sim-to-real calibration",
        "state": "recorded" if runs else "unverified",
        "evidence": runs or "no measured run recorded",
        "robot_weighed": weighed(root),
        "scope": ("tools/real2sim.py (record, marker tracking, parameter fit, report) is validated on synthetic "
                  "data only. Servo values and masses stay unmeasured-nominal; no simulation parameter has been "
                  "fitted from a real robot, and recorded runs do not change the model by themselves. "
                  "See reference/REAL2SIM-CAPTURE.md."),
    }
