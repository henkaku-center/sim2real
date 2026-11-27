"""Print check: overhang area (> 45 deg, not on the bed) per print STL, plus V3 frame baseline."""
import sys, glob, math, numpy as np, trimesh
def overhang(f):
    m = trimesh.load(f); nz = m.face_normals[:, 2]; zc = m.triangles_center[:, 2]
    down = (nz < -math.sin(math.radians(45))) & (zc > 0.3)
    return round(float(m.area_faces[down].sum()), 1), [round(v, 1) for v in m.extents]
for f in sorted(glob.glob(f"{sys.argv[1]}/*-print.stl")) + [f"{sys.argv[2]}/internal-frame-print.stl"]:
    print(f.split("/")[-1], *overhang(f))
