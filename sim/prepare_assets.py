"""Generate body-local visual meshes from the upstream printed-part STLs.

Inputs:  assets/stl/upstream/*.stl  (dorianborian/sesame-robot, Apache-2.0,
         v117 legs / v121 frame+covers, assembly coordinates in mm, y-up)
Outputs: assets/mesh/*.stl          (binary STL, meters, body-local frames,
                                     referenced by models/sesame.xml)
         web/public/meshes/*.glb    (same meshes for the browser renderer)

Coordinate facts (measured; see DECISIONS.md D2 and repo history):
- assembly frame: x fore-aft with FRONT at -x (OLED window in the top cover
  is on the low-x face), y up, z lateral with +z = robot LEFT.
- hip axes at (x=1.5, z=+-23.04), leg plane y=15.25, foot axes at z=+-59.9.
- torso center at (x=26, y=17, z=0).
- Leg files are drawn as FRONT-corner templates: files at z+ belong to the
  LEFT slot, files at z- to the RIGHT slot; back corners are the same
  templates rotated 180 deg about vertical. (Engraved part labels may not
  match the slot we assign; geometrically the slots are correct. Verify the
  engraving against a physical robot when available - NEEDS-HARDWARE.)

Usage: uv run python -m sim.prepare_assets
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

REPO = Path(__file__).parent.parent
UPSTREAM = REPO / "assets" / "stl" / "upstream"
MESH_OUT = REPO / "assets" / "mesh"
GLB_OUT = REPO / "web" / "public" / "meshes"

# asm (mm, y-up) -> robot/body local (m, z-up): x=-ax, y=az, z=ay, then /1000
M_ASM = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=float)
R_Z180 = np.diag([-1.0, -1.0, 1.0])

TORSO_ORIGIN = np.array([26.0, 17.0, 0.0])
HIP = {"left": np.array([1.5, 15.25, 23.04]), "right": np.array([1.5, 15.25, -23.04])}
FOOT = {"left": np.array([1.5, 15.25, 59.9]), "right": np.array([1.5, 15.25, -59.9])}

# output name -> (upstream file, asm origin, extra rotation)
PARTS: dict[str, tuple[str, np.ndarray, np.ndarray]] = {
    "torso_frame": ("Internal-Frame-v121.stl", TORSO_ORIGIN, np.eye(3)),
    "torso_bottom": ("Bottom-Cover-v121.stl", TORSO_ORIGIN, np.eye(3)),
    "torso_top": ("Top-Cover-Enclosed-v117.stl", TORSO_ORIGIN, np.eye(3)),
    "front_left_upper": ("R1-v117.stl", HIP["left"], np.eye(3)),
    "front_left_lower": ("R3-v117.stl", FOOT["left"], np.eye(3)),
    "front_right_upper": ("L1-v117.stl", HIP["right"], np.eye(3)),
    "front_right_lower": ("L3-v117.stl", FOOT["right"], np.eye(3)),
    # A 180-deg yaw maps a LEFT-slot template to a back-RIGHT corner and
    # vice versa (rotation, not mirror!):
    "back_left_upper": ("R2-v117.stl", HIP["right"], R_Z180),
    "back_left_lower": ("R4-v117.stl", FOOT["right"], R_Z180),
    "back_right_upper": ("L2-v117.stl", HIP["left"], R_Z180),
    "back_right_lower": ("L4-v117.stl", FOOT["left"], R_Z180),
}


def convert(name: str, upstream: str, origin: np.ndarray, extra: np.ndarray) -> None:
    mesh = trimesh.load(UPSTREAM / upstream)
    verts = (mesh.vertices - origin) @ M_ASM.T @ extra.T / 1000.0
    out = trimesh.Trimesh(vertices=verts, faces=mesh.faces, process=False)
    MESH_OUT.mkdir(parents=True, exist_ok=True)
    GLB_OUT.mkdir(parents=True, exist_ok=True)
    out.export(MESH_OUT / f"{name}.stl")
    out.export(GLB_OUT / f"{name}.glb")


def main() -> None:
    for name, (upstream, origin, extra) in PARTS.items():
        convert(name, upstream, origin, extra)
        print(f"wrote {name}: assets/mesh/{name}.stl + web/public/meshes/{name}.glb")


if __name__ == "__main__":
    main()
