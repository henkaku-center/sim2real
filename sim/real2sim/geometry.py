"""Small quaternion helpers (w, x, y, z; unit; batched over leading axes)."""

from __future__ import annotations

import numpy as np


def normalize(q: np.ndarray) -> np.ndarray:
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def conj(q: np.ndarray) -> np.ndarray:
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = np.moveaxis(np.asarray(a, dtype=float), -1, 0)
    bw, bx, by, bz = np.moveaxis(np.asarray(b, dtype=float), -1, 0)
    return np.stack([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ], axis=-1)


def rotate(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate vectors v by quaternions q."""
    q = np.asarray(q, dtype=float)
    v = np.asarray(v, dtype=float)
    w, u = q[..., :1], q[..., 1:]
    t = 2.0 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def rotvec(q: np.ndarray) -> np.ndarray:
    """Rotation vector (axis * angle, radians) of unit quaternions, angle <= pi."""
    q = np.asarray(q, dtype=float)
    q = np.where(q[..., :1] < 0.0, -q, q)
    s = np.linalg.norm(q[..., 1:], axis=-1, keepdims=True)
    angle = 2.0 * np.arctan2(s, q[..., :1])
    scale = np.where(s > 1e-12, angle / np.maximum(s, 1e-12), 2.0)
    return q[..., 1:] * scale


def from_rotvec(r: np.ndarray) -> np.ndarray:
    r = np.asarray(r, dtype=float)
    angle = np.linalg.norm(r, axis=-1, keepdims=True)
    half = 0.5 * angle
    scale = np.where(angle > 1e-12, np.sin(half) / np.maximum(angle, 1e-12), 0.5)
    return np.concatenate([np.cos(half), r * scale], axis=-1)


def from_matrix(m: np.ndarray) -> np.ndarray:
    """Unit quaternion of one 3x3 rotation matrix."""
    m = np.asarray(m, dtype=float)
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0.0:
        s = 2.0 * np.sqrt(trace + 1.0)
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = normalize(np.array(q))
    return q if q[0] >= 0 else -q


def to_matrix(q: np.ndarray) -> np.ndarray:
    return np.stack([rotate(q, axis) for axis in np.eye(3)], axis=-1)


def mean(q: np.ndarray) -> np.ndarray:
    """Average of nearby unit quaternions (sign-aligned to the first)."""
    q = np.asarray(q, dtype=float)
    signs = np.where((q @ q[0]) < 0.0, -1.0, 1.0)[:, None]
    return normalize((q * signs).mean(axis=0))


def relative(ref_p, ref_q, p, q):
    """Pose (p, q) expressed in the reference pose's frame."""
    inv = conj(ref_q)
    return rotate(inv, np.asarray(p) - np.asarray(ref_p)), mul(inv, q)


def compose(a_p, a_q, b_p, b_q):
    """Pose a followed by pose b expressed in a's frame."""
    return np.asarray(a_p) + rotate(a_q, b_p), mul(a_q, b_q)
