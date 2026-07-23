"""Generate models/sesame.xml from manifest/robot.yaml.

Joint order, names, limits, and angle conventions come from the manifest
(canonical). Kinematic layout and link dimensions are MEASURED from the
upstream v117/v121 STLs (dorianborian/sesame-robot, Apache-2.0) by fitting
servo-horn circles in the assembly-coordinate meshes — see docs in repo
history and tests. Masses remain estimates (printed volumes x PLA density +
nominal servo mass) until weighed (NEEDS-HARDWARE).

Kinematics (confirmed against the upstream angle guide):
- Hip joints (R1,R2,L1,L2): VERTICAL axis; sweep the whole leg horizontally.
  Internal q=0 (firmware 90°): leg straight out sideways. Positive internal q
  sweeps OUTWARD (front legs toward the front, back legs toward the back),
  giving the X-stance at stand (all hips +45°).
- Foot joints (R3,R4,L3,L4): horizontal axis perpendicular to the femur;
  pitch a paddle blade. Internal q=0: paddle horizontal (in line with femur).
  Positive internal q = paddle DOWN (stand: +90°, blade vertical, lifting
  the body).

Usage: uv run python -m sim.build_mjcf   (rewrites models/sesame.xml)
"""

from __future__ import annotations

from pathlib import Path

from sim.manifest import Manifest, load_manifest

MODEL_PATH = Path(__file__).parent.parent / "models" / "sesame.xml"

# --- Dimensions measured from upstream STLs (meters, assembly frame mm/1000).
# Assembly frame: x fore-aft (front at -x), y up, z lateral (right at +z).
# MuJoCo frame: x forward, y left, z up.
TORSO_HALF = (0.0396, 0.0271, 0.0181)  # covers: 79.2 x 54.2 x 36.2 mm
HIP_X = 0.0245  # |x| of hip axis from body center (asm x=1.5, center 26)
HIP_Y = 0.0230  # |y| lateral offset of hip axis (asm z=+-23.0)
LEG_PLANE_DZ = -0.0018  # leg working plane below torso center (asm y 15.25 vs 17)
UPPER_LEN = 0.0369  # hip axis -> foot axis (asm z 23.0 -> 59.9)
UPPER_HALF = (0.0100, 0.0185, 0.0090)  # femur block 20.3 x (37) x 18 approx
FOOT_LEN = 0.0470  # foot axis -> paddle tip (asm z 59.9 -> 106.9)
FOOT_HALF = (0.0047, 0.0235, 0.0095)  # paddle blade 9.5 x 47 x 19 mm
UPPER_MASS = 0.019  # printed ~5.5 g + foot servo 13.4 g (unweighed)
FOOT_MASS = 0.005  # printed ~5 g (unweighed)
TORSO_MASS = 0.190  # frame+covers+4 hip servos+electronics (unweighed)
SPAWN_Z = 0.0185  # torso center height at rest (body bottom on the ground)

TIMESTEP = 0.002
# PLACEHOLDER servo gain/force: MG90S nominal stall 0.176 N*m (unmeasured).
ACT_KP = 0.6
ACT_FORCE = 0.176


def _leg_xml(m: Manifest, hip_name: str, foot_name: str) -> str:
    hip = m.joint(hip_name)
    foot = m.joint(foot_name)
    fx = 1.0 if "front" in hip.leg else -1.0
    sy = 1.0 if "left" in hip.leg else -1.0  # y-left frame: left = +y
    hip_lo, hip_hi = m.internal_range(hip)
    foot_lo, foot_hi = m.internal_range(foot)
    # Hip: vertical axis. Positive internal q must sweep OUTWARD; the
    # manifest sign (point-symmetric servo mounting) matches the required
    # axis flip exactly: +z for {front_right, back_left}, -z otherwise.
    hip_axis = f"0 0 {hip.sign}"
    # Foot: axis along body x at rest; positive internal q = paddle down.
    # Right paddles extend -y (axis +x), left extend +y (axis -x).
    foot_axis = f"{-sy:.0f} 0 0"
    return f"""
      <body name="{hip.leg}_upper" pos="{fx * HIP_X:.4f} {sy * HIP_Y:.4f} {LEG_PLANE_DZ}">
        <joint name="{hip.name}" type="hinge" axis="{hip_axis}"
               range="{hip_lo:.6f} {hip_hi:.6f}" damping="0.01"/>
        <site name="{hip.leg}_hip" pos="0 0 0"/>
        <geom name="{hip.leg}_upper_geom" type="box" mass="{UPPER_MASS}" group="3"
              pos="0 {sy * UPPER_LEN / 2:.4f} 0"
              size="{UPPER_HALF[0]} {UPPER_HALF[1]} {UPPER_HALF[2]}" rgba="{LEG_RGBA}"/>
        <geom name="{hip.leg}_upper_visual" type="mesh" mesh="{hip.leg}_upper"
              mass="0" group="2" contype="0" conaffinity="0" rgba="{LEG_RGBA}"/>
        <body name="{hip.leg}_lower" pos="0 {sy * UPPER_LEN:.4f} 0">
          <joint name="{foot.name}" type="hinge" axis="{foot_axis}"
                 range="{foot_lo:.6f} {foot_hi:.6f}" damping="0.01"/>
          <site name="{hip.leg}_knee" pos="0 0 0"/>
          <site name="{hip.leg}_paw" pos="0 {sy * FOOT_LEN:.4f} 0"/>
          <geom name="{hip.leg}_lower_geom" type="box" mass="{FOOT_MASS}" group="3"
                pos="0 {sy * FOOT_LEN / 2:.4f} 0"
                size="{FOOT_HALF[0]} {FOOT_HALF[1]} {FOOT_HALF[2]}" rgba="{LEG_RGBA}"/>
          <geom name="{hip.leg}_lower_visual" type="mesh" mesh="{hip.leg}_lower"
                mass="0" group="2" contype="0" conaffinity="0" rgba="{LEG_RGBA}"/>
        </body>
      </body>"""


LEG_RGBA = "0.80 0.12 0.08 1"  # crab red
BODY_RGBA = "0.92 0.88 0.80 1"  # printed cream
MESH_NAMES = [
    "torso_frame", "torso_bottom", "torso_top",
    "front_left_upper", "front_left_lower", "front_right_upper", "front_right_lower",
    "back_left_upper", "back_left_lower", "back_right_upper", "back_right_lower",
]


def build_xml(m: Manifest | None = None) -> str:
    m = m or load_manifest()
    by_leg = {j.leg: {} for j in m.joints}
    for j in m.joints:
        by_leg[j.leg][j.role] = j.name
    legs = "".join(
        _leg_xml(m, names["hip"], names["foot"]) for names in by_leg.values()
    )
    meshes = "".join(
        f"""
    <mesh name="{name}" file="{name}.stl"/>"""
        for name in MESH_NAMES
    )
    actuators = "".join(
        f"""
    <position name="{j.name}" joint="{j.name}" kp="{ACT_KP}"
              forcerange="-{ACT_FORCE} {ACT_FORCE}"
              ctrlrange="{m.internal_range(j)[0]:.6f} {m.internal_range(j)[1]:.6f}"/>"""
        for j in m.joints
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!-- GENERATED from manifest/robot.yaml by sim/build_mjcf.py — do not edit by hand.
     Kinematics/dimensions measured from upstream v117/v121 STLs; masses estimated. -->
<mujoco model="sesame">
  <option timestep="{TIMESTEP}"/>
  <compiler angle="radian" autolimits="true" meshdir="../assets/mesh"/>
  <default>
    <geom friction="0.9 0.005 0.0001" condim="3"/>
    <site size="0.0025" rgba="0.1 0.9 0.3 0.6"/>
  </default>
  <asset>{meshes}
  </asset>
  <worldbody>
    <light pos="0 0 1.5" dir="0 0 -1"/>
    <geom name="floor" type="plane" size="2 2 0.05" rgba="0.85 0.85 0.85 1"/>
    <body name="torso" pos="0 0 {SPAWN_Z}">
      <freejoint name="root"/>
      <geom name="torso_geom" type="box" size="{TORSO_HALF[0]} {TORSO_HALF[1]} {TORSO_HALF[2]}"
            mass="{TORSO_MASS}" group="3" rgba="0.9 0.75 0.5 1"/>
      <geom name="torso_frame_visual" type="mesh" mesh="torso_frame" mass="0"
            group="2" contype="0" conaffinity="0" rgba="{BODY_RGBA}"/>
      <geom name="torso_bottom_visual" type="mesh" mesh="torso_bottom" mass="0"
            group="2" contype="0" conaffinity="0" rgba="{BODY_RGBA}"/>
      <geom name="torso_top_visual" type="mesh" mesh="torso_top" mass="0"
            group="2" contype="0" conaffinity="0" rgba="{BODY_RGBA}"/>
      <geom name="face_geom" type="box" size="0.002 0.016 0.011"
            pos="{TORSO_HALF[0]:.4f} 0 0.004" mass="0.001"
            contype="0" conaffinity="0" rgba="0.15 0.2 0.9 1"/>
      <site name="torso_center" pos="0 0 0"/>
      <site name="face" pos="{TORSO_HALF[0]:.4f} 0 0.004"/>
      <site name="rear" pos="-{TORSO_HALF[0]:.4f} 0 0.004"/>{legs}
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
