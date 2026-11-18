import sys, numpy as np, trimesh, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
KIT, OUT = sys.argv[1], sys.argv[2]
L = lambda f: trimesh.load(f)
head = L(f"{OUT}/round-head-1.2mm.stl"); v3 = L(f"{KIT}/head-cover.stl"); lid = L(f"{KIT}/head-lid.stl")
frame = L(f"{KIT}/internal-frame.stl"); cover = L(f"{KIT}/bottom-cover.stl")
light = np.array([0.4, -0.5, 0.8]); light /= np.linalg.norm(light)
def add(ax, m, rgb, a=1.0, dx=0):
    m = m.copy(); m.apply_translation([dx, 0, 0])
    sh = 0.45 + 0.55 * np.clip(m.face_normals @ light, 0, 1)
    pc = Poly3DCollection(m.triangles, facecolors=np.c_[np.outer(sh, rgb), np.full(len(sh), a)], linewidths=0)
    ax.add_collection3d(pc)
def scene(ax, elev, azim, items, lim):
    tris, cols = [], []
    for m, rgb, a, dx in [(i + (1.0, 0))[:4] if len(i) < 4 else i for i in items]:
        m = m.copy(); m.apply_translation([dx, 0, 0])
        sh = 0.45 + 0.55 * np.clip(m.face_normals @ light, 0, 1)
        tris.append(m.triangles); cols.append(np.c_[np.outer(sh, rgb), np.full(len(sh), a)])
    ax.add_collection3d(Poly3DCollection(np.concatenate(tris), facecolors=np.concatenate(cols), linewidths=0))
    ax.set_xlim(*lim[0]); ax.set_ylim(*lim[1]); ax.set_zlim(*lim[2]); ax.set_box_aspect([lim[0][1]-lim[0][0], lim[1][1]-lim[1][0], lim[2][1]-lim[2][0]])
    ax.view_init(elev, azim); ax.set_axis_off()
mint, grey, dark, white = np.array([.66,.9,.82]), np.array([.62,.64,.66]), np.array([.25,.25,.27]), np.array([.93,.93,.9])
fig = plt.figure(figsize=(14, 6.5), dpi=130)
lim = [(-130, 130), (-55, 55), (-20, 60)]
ax = fig.add_subplot(1, 2, 1, projection="3d")
scene(ax, 22, -60, [(frame, grey, 1, -70), (cover, dark, 1, -70), (v3, white, 1, -70), (lid, white, 1, -70),
                    (frame, grey, 1, 70), (cover, dark, 1, 70), (head, mint, 1, 70)], lim)
ax.set_title("V3 head (left)  vs  new rounded glow head (right)", fontsize=12)
ax2 = fig.add_subplot(1, 2, 2, projection="3d")
lim2 = [(-60, 60), (-60, 60), (-20, 60)]
scene(ax2, 8, 20, [(frame, grey, 1, 0), (cover, dark, 1, 0), (head, mint, 1, 0)], lim2)
ax2.set_title("Front three-quarter: OLED window + rounded dome", fontsize=12)
plt.tight_layout(); plt.savefig(f"{OUT}/round-head-preview.png", bbox_inches="tight")
import manifold3d as mf
mm = mf.Manifold(mf.Mesh(vert_properties=np.asarray(head.vertices, np.float32), tri_verts=np.asarray(head.faces, np.uint32)))
print("reload status", mm.status(), "vol", round(mm.volume(),1))
