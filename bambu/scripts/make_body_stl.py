"""Write body-only (no legs) STLs from the upstream printed parts, Z-up, in millimetres.

Usage:  uv run python -I make_body_stl.py UPSTREAM_STL_DIR OUT_DIR [TOP_COVER_NAME]

Upstream STLs are Y-up assembly coordinates; rotate +90 deg about X to Z-up.
- OUT/body-assembled.stl : frame + bottom cover + top cover, assembled (preview / check)
- OUT/print/*.stl        : each part alone, upright, dropped onto z=0 and centred on XY
"""
import sys, pathlib
import numpy as np
import trimesh

src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
top = sys.argv[3] if len(sys.argv) > 3 else "Top-Cover-Enclosed-v117"
parts = {
    "bottom-cover": src / "Bottom-Cover-v121.stl",
    "internal-frame": src / "Internal-Frame-v121.stl",
    "top-cover": src / "top-covers" / f"{top}.stl",
}
y_up_to_z_up = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])

meshes = {}
for name, path in parts.items():
    m = trimesh.load(path, force="mesh")
    m.apply_transform(y_up_to_z_up)
    meshes[name] = m

body = trimesh.util.concatenate(list(meshes.values()))
lo, hi = body.bounds
body.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
(out / "print").mkdir(parents=True, exist_ok=True)
body.export(out / "body-assembled.stl")
print(f"body-assembled.stl size={(hi - lo).round(1)} mm")

for name, m in meshes.items():
    lo, hi = m.bounds
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    m.export(out / "print" / f"{name}.stl")
    print(f"print/{name}.stl size={(hi - lo).round(1)} mm watertight={m.is_watertight}")
