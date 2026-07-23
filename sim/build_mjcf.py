"""Generate models/sesame.xml from manifest/robot.yaml.

Joint order, names, limits, and angle conventions come from the manifest
(canonical). Geometry below is PLACEHOLDER primitive geometry — rough
palm-sized quadruped proportions — pending measured dimensions/masses from
the v117/v121 STLs and the physical robot (NEEDS-HARDWARE). Do not trust
dimensions; do trust joint semantics.

Usage: uv run python -m sim.build_mjcf   (rewrites models/sesame.xml)
"""

from __future__ import annotations

from pathlib import Path

from sim.manifest import Manifest, load_manifest

MODEL_PATH = Path(__file__).parent.parent / "models" / "sesame.xml"

# --- PLACEHOLDER dimensions (meters) and masses (kg) ---
TORSO_HALF = (0.050, 0.040, 0.028)  # half-sizes of torso box
TORSO_MASS = 0.200
HIP_OFFSET = (0.038, 0.040)  # |x|, |y| of hip joint from torso center
UPPER_LEN = 0.045
UPPER_MASS = 0.030  # printed part + foot servo carried on the segment
LOWER_LEN = 0.055
LOWER_MASS = 0.012
LEG_RADIUS = 0.008
SPAWN_Z = 0.05  # torso center height at keyframe "rest" (lying, legs sprawled)

TIMESTEP = 0.002
# PLACEHOLDER servo gain/force: MG90S nominal stall 0.176 N·m (unmeasured).
ACT_KP = 0.6
ACT_FORCE = 0.176


def _leg_xml(m: Manifest, hip_name: str, foot_name: str) -> str:
    hip = m.joint(hip_name)
    fx = 1.0 if "front" in hip.leg else -1.0
    sy = 1.0 if "left" in hip.leg else -1.0  # y-left frame: left = +y
    hx, hy = fx * HIP_OFFSET[0], sy * HIP_OFFSET[1]
    hip_lo, hip_hi = m.internal_range(hip)
    foot = m.joint(foot_name)
    foot_lo, foot_hi = m.internal_range(foot)
    # Hinge axes along +x (forward); mirroring handled by manifest signs.
    return f"""
      <body name="{hip.leg}_upper" pos="{hx:.4f} {hy:.4f} 0">
        <joint name="{hip.name}" type="hinge" axis="1 0 0"
               range="{hip_lo:.6f} {hip_hi:.6f}" damping="0.01"/>
        <geom name="{hip.leg}_upper_geom" type="capsule" mass="{UPPER_MASS}"
              fromto="0 0 0 0 {sy * UPPER_LEN:.4f} 0" size="{LEG_RADIUS}"/>
        <body name="{hip.leg}_lower" pos="0 {sy * UPPER_LEN:.4f} 0">
          <joint name="{foot.name}" type="hinge" axis="1 0 0"
                 range="{foot_lo:.6f} {foot_hi:.6f}" damping="0.01"/>
          <geom name="{hip.leg}_lower_geom" type="capsule" mass="{LOWER_MASS}"
                fromto="0 0 0 0 {sy * LOWER_LEN:.4f} 0" size="{LEG_RADIUS * 0.8:.4f}"/>
        </body>
      </body>"""


def build_xml(m: Manifest | None = None) -> str:
    m = m or load_manifest()
    # Legs grouped per leg: (hip, foot) names from the manifest roles.
    by_leg = {j.leg: {} for j in m.joints}
    for j in m.joints:
        by_leg[j.leg][j.role] = j.name
    legs = "".join(
        _leg_xml(m, names["hip"], names["foot"]) for names in by_leg.values()
    )
    # Actuators in canonical channel order (index = firmware servo channel).
    actuators = "".join(
        f"""
    <position name="{j.name}" joint="{j.name}" kp="{ACT_KP}"
              forcerange="-{ACT_FORCE} {ACT_FORCE}"
              ctrlrange="{m.internal_range(j)[0]:.6f} {m.internal_range(j)[1]:.6f}"/>"""
        for j in m.joints
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!-- GENERATED from manifest/robot.yaml by sim/build_mjcf.py — do not edit by hand.
     Geometry is PLACEHOLDER; joint order/limits/conventions are canonical. -->
<mujoco model="sesame">
  <option timestep="{TIMESTEP}"/>
  <compiler angle="radian" autolimits="true"/>
  <default>
    <geom friction="0.9 0.005 0.0001" condim="3"/>
  </default>
  <worldbody>
    <light pos="0 0 1.5" dir="0 0 -1"/>
    <geom name="floor" type="plane" size="2 2 0.05" rgba="0.85 0.85 0.85 1"/>
    <body name="torso" pos="0 0 {SPAWN_Z}">
      <freejoint name="root"/>
      <geom name="torso_geom" type="box" size="{TORSO_HALF[0]} {TORSO_HALF[1]} {TORSO_HALF[2]}"
            mass="{TORSO_MASS}" rgba="0.9 0.75 0.5 1"/>{legs}
    </body>
  </worldbody>
  <actuator>{actuators}
  </actuator>
</mujoco>
"""


def main() -> None:
    MODEL_PATH.write_text(build_xml())
    print(f"wrote {MODEL_PATH}")


if __name__ == "__main__":
    main()
