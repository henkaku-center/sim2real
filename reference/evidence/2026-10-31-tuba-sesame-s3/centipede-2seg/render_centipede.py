"""Preview: assembled 2-segment body (straight and bent 25 deg) with seg 2 cap lifted."""
import sys, numpy as np, trimesh, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
KIT, OUT = sys.argv[1], sys.argv[2]
L = lambda f: trimesh.load(f)
p = {n: L(f"{OUT}/{n}.stl") for n in ("seg1-frame", "seg2-frame", "seg1-base", "seg2-base", "seg1-cap", "seg2-cap")}
c1, c2 = L(f"{OUT}/seg1-cover.stl"), L(f"{OUT}/seg2-cover.stl")
DX2, PX = -112.177, -55.975
light = np.array([0.4, -0.5, 0.8]); light /= np.linalg.norm(light)
pink, grey, dark, white = np.array([.96, .66, .8]), np.array([.62, .64, .66]), np.array([.25, .25, .27]), np.array([.93, .93, .9])
def place(m, dx=0, dz=0, yaw=0):
    m = m.copy(); m.apply_translation([dx, 0, dz])
    if yaw:
        m.apply_translation([-PX, 0, 0]); m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 0, 1])); m.apply_translation([PX, 0, 0])
    return m
def scene(ax, elev, azim, items, lim, title):
    tris, cols = [], []
    for m, rgb in items:
        sh = 0.45 + 0.55 * np.clip(m.face_normals @ light, 0, 1)
        tris.append(m.triangles); cols.append(np.c_[np.outer(sh, rgb), np.ones(len(sh))])
    ax.add_collection3d(Poly3DCollection(np.concatenate(tris), facecolors=np.concatenate(cols), linewidths=0))
    ax.set_xlim(*lim[0]); ax.set_ylim(*lim[1]); ax.set_zlim(*lim[2])
    ax.set_box_aspect([lim[0][1] - lim[0][0], lim[1][1] - lim[1][0], lim[2][1] - lim[2][0]])
    ax.view_init(elev, azim); ax.set_axis_off(); ax.set_title(title, fontsize=12)
def robot(yaw=0, lift=0):
    s1 = [(p["seg1-frame"], grey), (c1, dark), (p["seg1-base"], white), (p["seg1-cap"], pink)]
    s2 = [(place(p["seg2-frame"], DX2, yaw=yaw), grey), (place(c2, DX2, yaw=yaw), dark),
          (place(p["seg2-base"], DX2, yaw=yaw), white), (place(p["seg2-cap"], DX2, lift, yaw=yaw), pink)]
    return [(m, c) for m, c in s1] + s2
fig = plt.figure(figsize=(15, 6.5), dpi=120)
lim = [(-175, 60), (-80, 80), (-25, 135)]
scene(fig.add_subplot(1, 2, 1, projection="3d"), 20, -60, robot(0, 50), lim,
      "Sphere-style domes from Z 27; seg 2 cap lifted (2 screws)")
scene(fig.add_subplot(1, 2, 2, projection="3d"), 60, -90, robot(25), [(-175, 60), (-110, 110), (-25, 85)],
      "Top view, bent 25 deg on the pivot (lock screw out); legs at segment centres")
plt.tight_layout(); plt.savefig(f"{OUT}/centipede-preview.png", bbox_inches="tight")
