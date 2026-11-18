"""Close-up of the hinge: assembled, pulled apart, and bent."""
import sys, numpy as np, trimesh, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
OUT = sys.argv[1]
f1, f2 = trimesh.load(f"{OUT}/seg1-frame.stl"), trimesh.load(f"{OUT}/seg2-frame.stl")
DX2, PX, LOCK_Y = -112.177, -55.975, 7.0
light = np.array([0.3, -0.6, 0.75]); light /= np.linalg.norm(light)
grey, blue, steel, dark = np.array([.75, .76, .78]), np.array([.55, .7, .95]), np.array([.85, .6, .2]), np.array([.2, .2, .2])
def screw(y, dz=0):
    shank = trimesh.creation.cylinder(radius=1.45, height=22, sections=24); shank.apply_translation([0, 0, -6])
    head = trimesh.creation.cone(radius=3.0, height=1.8, sections=24); head.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    head.apply_translation([0, 0, 6.8])
    m = trimesh.util.concatenate([shank, head]); m.apply_translation([PX, y, dz]); return m
def tf(m, dx=0, dz=0, yaw=0):
    m = m.copy(); m.apply_translation([dx, 0, dz])
    if yaw:
        m.apply_translation([-PX, 0, 0]); m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 0, 1])); m.apply_translation([PX, 0, 0])
    return m
def scene(ax, items, elev, azim, lim, title):
    tris, cols = [], []
    for m, rgb in items:
        sh = 0.4 + 0.6 * np.clip(m.face_normals @ light, 0, 1)
        tris.append(m.triangles); cols.append(np.c_[np.outer(sh, rgb), np.ones(len(sh))])
    ax.add_collection3d(Poly3DCollection(np.concatenate(tris), facecolors=np.concatenate(cols), linewidths=0))
    ax.set_xlim(*lim[0]); ax.set_ylim(*lim[1]); ax.set_zlim(*lim[2])
    ax.set_box_aspect([lim[0][1] - lim[0][0], lim[1][1] - lim[1][0], lim[2][1] - lim[2][0]])
    ax.view_init(elev, azim); ax.set_axis_off(); ax.set_title(title, fontsize=11)
def clip(m, x0, x1):  # keep only the frame ends near the hinge
    return m.slice_plane([x0, 0, 0], [1, 0, 0]).slice_plane([x1, 0, 0], [-1, 0, 0])
s1 = clip(f1, -75, -20); s2 = clip(tf(f2, DX2), -92, -37)
lim = [(-92, -20), (-36, 36), (-30, 25)]
fig = plt.figure(figsize=(16, 11), dpi=110)
scene(fig.add_subplot(2, 2, 1, projection="3d"), [(s1, grey), (s2, blue), (screw(0), steel), (screw(LOCK_Y), dark)], 25, -55, lim,
      "1. Assembled: seg 1 tongue (grey) between seg 2 fork tabs (blue)\npivot screw (orange) + lock screw (black), heads countersunk on top")
scene(fig.add_subplot(2, 2, 2, projection="3d"), [(tf(s1, 22), grey), (s2, blue), (screw(0, 20), steel), (screw(LOCK_Y, 20), dark)], 25, -55,
      [(-92, 0), (-36, 36), (-30, 45)], "2. Pulled apart: tongue slides in between the 2 tabs,\nthen the screws go in from the top")
scene(fig.add_subplot(2, 2, 3, projection="3d"), [(s1, grey), (s2, blue), (screw(0), steel), (screw(LOCK_Y), dark)], 0, -90, lim,
      "3. Side view: top tab / tongue / bottom tab, 0.5 mm play each side\nscrew threads into the bottom tab (no nut)")
scene(fig.add_subplot(2, 2, 4, projection="3d"), [(s1, grey), (tf(s2, yaw=25), blue), (screw(0), steel)], 89, -90, [(-95, -15), (-45, 45), (-30, 25)],
      "4. Top view, bent 25 deg (lock screw out): turns on the pivot,\nup to 35 deg before anything touches")
plt.tight_layout(); plt.savefig(f"{OUT}/hinge-closeup.png", bbox_inches="tight")
