import sys, numpy as np, trimesh
for f in sys.argv[1:]:
    m = trimesh.load(f)  # STL load merges identical positions, like a slicer
    e = np.sort(m.edges, axis=1); u, c = np.unique(e, axis=0, return_counts=True)
    bad = u[c != 2]
    print(f.split('/')[-1], "faces", len(m.faces), "bad_edges", len(bad), "counts", np.unique(c, return_counts=True))
    for a, b in bad[:8]: print("  ", m.vertices[a].round(3), m.vertices[b].round(3))
