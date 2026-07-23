"""Interactive native viewer for models/sesame.xml.

Linux:  uv run python sim/view.py [--pose rest|stand]
macOS:  uv run mjpython sim/view.py [--pose rest|stand]   (mjpython required)

Opens the MuJoCo viewer with the servo controls set to the named manifest
pose (default: stand). Use the viewer's Control pane to move individual
joints; actuator index = firmware servo channel.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

import mujoco
import mujoco.viewer

from sim.build_mjcf import MODEL_PATH
from sim.manifest import load_manifest


def main() -> None:
    manifest = load_manifest()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pose",
        default="stand",
        choices=sorted(manifest.raw["poses"]),
        help="manifest pose to command at startup (default: stand)",
    )
    args = parser.parse_args()

    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    pose = manifest.pose_internal(args.pose)
    data.ctrl[:] = [pose[j.name] for j in manifest.joints]
    print(f"commanding pose '{args.pose}':")
    for j in manifest.joints:
        print(f"  ch{j.channel} {j.name:<2} ({j.leg} {j.role}): "
              f"{manifest.to_firmware(j, pose[j.name]):6.1f}° fw / {pose[j.name]:+.3f} rad")
    mujoco.viewer.launch(model, data)


if __name__ == "__main__":
    main()
