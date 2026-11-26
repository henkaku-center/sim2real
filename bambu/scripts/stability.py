"""Static rolling-stability analysis of a rigid body on a flat, hard, level floor.

For a rigid body the floor touches only its convex hull.  With the centre of
mass G, the body rests (quasi-statically) only where the support function
h(u) = max_v (v - G).u has a local minimum.  For a polyhedral hull the stable
equilibria are exactly the hull faces whose perpendicular foot of G lies
inside the face; edges are saddles and vertices are maxima.  We report every
such face, its tilt from the intended "belly down" orientation and the signed
margin of G's projection inside the face (negative = unstable by that many mm),
plus quasi-static basins of attraction on a sampled orientation sphere.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull

DOWN = np.array([0.0, 0.0, -1.0])


def fibonacci_sphere(n: int) -> np.ndarray:
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = np.pi * (1 + 5 ** 0.5) * i
    return np.c_[np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)]


def _faces(hull: ConvexHull, tol=1e-6):
    """Merge coplanar hull triangles -> list of (normal, offset, [triangles])."""
    groups: dict = {}
    for simplex, eq in zip(hull.simplices, hull.equations):
        key = tuple(np.round(eq / 1e-4).astype(np.int64))  # 1e-4 mm/rad grid
        groups.setdefault(key, (eq[:3], eq[3], []))[2].append(hull.points[simplex])
    return list(groups.values())


def _signed_margin(p, tris, n):
    """Signed distance of p (in the face plane) to the boundary of a planar triangle fan."""
    # boundary edges = edges that occur once
    edges = {}
    for t in tris:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            ka, kb = tuple(np.round(t[a], 6)), tuple(np.round(t[b], 6))
            key = (ka, kb) if ka < kb else (kb, ka)
            edges[key] = edges.get(key, 0) + 1
    boundary = [np.array(k) for k, c in edges.items() if c == 1]
    d = min(_point_segment(p, a, b) for a, b in boundary)
    inside = any(_in_tri(p, t, n) for t in tris)
    return d if inside else -d


def _point_segment(p, a, b):
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-12), 0, 1)
    return float(np.linalg.norm(p - (a + t * ab)))


def _in_tri(p, t, n):
    """Orientation-independent point-in-triangle test (scipy simplices are unordered)."""
    s = [np.dot(np.cross(t[(i + 1) % 3] - t[i], p - t[i]), n) for i in range(3)]
    return min(s) >= -1e-9 or max(s) <= 1e-9


def equilibria(points: np.ndarray, com: np.ndarray, min_report_margin=-15.0, micro_depth_mm=0.02):
    """Stable (and near-stable) resting faces of conv(points) about com.

    depth_mm is the CoM rise needed to tip over the nearest face edge, sqrt(h^2 + m^2) - h.
    Faces with depth below micro_depth_mm (mesh tessellation facets, hole bridges near the
    apex) are flagged `micro`: they hold only against disturbances of a few microjoules.
    """
    hull = ConvexHull(points)
    rows = []
    for n, off, tris in _faces(hull):
        dist = -(np.dot(n, com) + off)  # >0: com inside
        foot = com + dist * n
        margin = _signed_margin(foot, tris, n)
        if margin < min_report_margin:
            continue
        area = sum(0.5 * np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0])) for t in tris)
        tilt = np.degrees(np.arccos(np.clip(np.dot(n, DOWN), -1, 1)))
        depth = float(np.hypot(dist, max(margin, 0.0)) - dist)
        rows.append({"normal": n.round(4).tolist(), "tilt_deg": round(float(tilt), 2),
                     "com_height_mm": round(float(dist), 2), "margin_mm": round(float(margin), 2),
                     "area_mm2": round(float(area), 1), "stable": bool(margin > 0),
                     "depth_mm": round(depth, 5), "micro": bool(margin > 0 and depth < micro_depth_mm)})
    rows.sort(key=lambda r: -r["margin_mm"])
    return hull, rows


def basins(points: np.ndarray, com: np.ndarray, n_dirs=30000, smooth_mm=2.0):
    """Quasi-static steepest-descent basins of h(u) on a Fibonacci sphere of contact normals.

    h is smoothed with a log-sum-exp of width smooth_mm so that sampled descent does not stall
    in the V-shaped creases along hull edges (edges are never true minima).
    """
    hull = ConvexHull(points)
    v = hull.points[hull.vertices] - com
    dirs = fibonacci_sphere(n_dirs)
    proj = v @ dirs.T
    hmax = proj.max(axis=0)
    h = hmax + smooth_mm * np.log(np.exp((proj - hmax) / smooth_mm).sum(axis=0))
    tri = ConvexHull(dirs).simplices
    nbr = [set() for _ in range(n_dirs)]
    for a, b, c in tri:
        nbr[a] |= {b, c}
        nbr[b] |= {a, c}
        nbr[c] |= {a, b}
    nxt = np.array([min([i, *nbr[i]], key=lambda j: h[j]) for i in range(n_dirs)])
    root = nxt.copy()
    for _ in range(n_dirs):
        new = root[root]
        if np.array_equal(new, root):
            break
        root = new
    out = []
    for r in np.unique(root):
        frac = float(np.mean(root == r))
        tilt = np.degrees(np.arccos(np.clip(np.dot(dirs[r], DOWN), -1, 1)))
        out.append({"direction": dirs[r].round(3).tolist(), "tilt_deg": round(float(tilt), 1),
                    "h_mm": round(float(h[r]), 2), "fraction": round(frac, 4)})
    out.sort(key=lambda r: -r["fraction"])
    return out


def hull_inside_margin(hull: ConvexHull, pts: np.ndarray) -> np.ndarray:
    """Distance of each point inside the hull (negative = outside)."""
    return -(pts @ hull.equations[:, :3].T + hull.equations[:, 3]).max(axis=1)
