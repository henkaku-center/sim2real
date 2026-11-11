"""Printed fiducial marker: sheet, detection, torso pose, camera calibration.

Choice (DECISIONS.md D23): OpenCV's ArUco detector with ``DICT_4X4_50`` and
``cv2.solvePnP(..., SOLVEPNP_IPPE_SQUARE)`` for the single head-lid marker;
a ChArUco board and ``cv2.calibrateCamera`` for the camera intrinsics.

Frames. The marker frame follows OpenCV: origin at the marker centre, x to the
right of the printed marker, y to its top, z out of the paper. The sheet's
FRONT strip is at the marker's top, so the body frame written to the run log
(x toward the robot's face, y to its left, z up) is the marker frame turned
+90 degrees about z. Camera frame: OpenCV, x right, y down, z forward.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from sim.real2sim import geometry as g

DICTIONARY = cv2.aruco.DICT_4X4_50
HEAD_ID, FLOOR_ID = 0, 1
HEAD_SIZE_MM = 40.0  # head lid is about 72 x 52 mm
FLOOR_SIZE_MM = 80.0
BOARD_SQUARES = (6, 8)  # ChArUco calibration board, columns x rows
BOARD_SQUARE_MM, BOARD_MARKER_MM, BOARD_FIRST_ID = 25.0, 18.0, 10
PAGE_MM = (210.0, 297.0)  # A4 portrait
BODY_FROM_MARKER = g.from_rotvec(np.array([0.0, 0.0, math.pi / 2]))  # FRONT strip is at marker +y
UNCALIBRATED_HFOV_DEG = 65.0  # typical phone main camera; a guess, not a measurement


def dictionary():
    return cv2.aruco.getPredefinedDictionary(DICTIONARY)


def board():
    count = (BOARD_SQUARES[0] * BOARD_SQUARES[1]) // 2
    return cv2.aruco.CharucoBoard(BOARD_SQUARES, BOARD_SQUARE_MM / 1000.0, BOARD_MARKER_MM / 1000.0,
                                  dictionary(), np.arange(BOARD_FIRST_ID, BOARD_FIRST_ID + count))


def marker_cells(marker_id: int) -> np.ndarray:
    """6 x 6 boolean matrix (True = black) of a marker including its border."""
    image = cv2.aruco.generateImageMarker(dictionary(), marker_id, 6, borderBits=1)
    return image < 128


# ---- printable sheet ---------------------------------------------------------


def _marker_ops(marker_id: int, x: float, y: float, size: float) -> list[tuple]:
    """One black square with the white cells drawn on top (no seams between cells)."""
    cells, cell = marker_cells(marker_id), size / 6.0
    ops = [("rect", x, y, size, size)]
    for row in range(1, 5):
        for col in range(1, 5):
            if not cells[row, col]:
                ops.append(("white", x + col * cell, y + row * cell, cell, cell))
    return ops


def _board_ops(x: float, y: float) -> list[tuple]:
    """ChArUco board as 1 mm pixel runs (25 mm squares, 3 mm marker modules: exact at 1 px/mm)."""
    width, height = (int(n * BOARD_SQUARE_MM) for n in BOARD_SQUARES)
    image = board().generateImage((width, height), marginSize=0, borderBits=1) < 128
    ops = []
    for row in range(height):
        edges = np.flatnonzero(np.diff(np.concatenate([[0], image[row].astype(np.int8), [0]])))
        ops += [("rect", x + a, y + row, b - a, 1.0) for a, b in zip(edges[0::2], edges[1::2])]
    # Merge identical runs on consecutive rows into taller rectangles.
    merged: dict[tuple[float, float], list[float]] = {}
    out = []
    for _, rx, ry, rw, rh in ops:
        key = (rx, rw)
        if key in merged and abs(merged[key][0] + merged[key][1] - ry) < 1e-9:
            merged[key][1] += rh
        else:
            if key in merged:
                out.append(("rect", rx, merged[key][0], rw, merged[key][1]))
            merged[key] = [ry, rh]
    out += [("rect", rx, start, rw, tall) for (rx, rw), (start, tall) in merged.items()]
    return sorted(out, key=lambda op: (op[2], op[1]))


def sheet_pages() -> list[list[tuple]]:
    """Drawing operations (millimetres, origin top-left) for the two A4 pages."""
    page1: list[tuple] = [
        ("text", 15, 16, 5.0, "Sesame real-to-sim marker sheet"),
        ("text", 15, 23, 3.2, "Print at 100 % / actual size (not 'fit to page'). Then measure the bar below: it must be 100 mm."),
        ("line", 15, 34, 115, 34, 0.4),
    ]
    page1 += [("line", 15 + 10 * i, 31 if i % 5 == 0 else 32.5, 15 + 10 * i, 34, 0.4) for i in range(11)]
    page1 += [("text", 118, 35, 3.2, "100 mm scale bar (ticks every 10 mm)")]
    # Head marker: 52 x 60 mm cut-out (the lid is about 52 mm wide), marker 40 mm, FRONT strip on top.
    hx, hy = 20.0, 48.0
    page1 += [("dash", hx, hy, 52.0, 60.0), ("text", hx + 13.5, hy + 8.5, 4.0, "FRONT (face)"),
              ("poly", [(hx + 26.0, hy + 1.5), (hx + 23.0, hy + 4.5), (hx + 29.0, hy + 4.5)])]
    page1 += _marker_ops(HEAD_ID, hx + 6.0, hy + 14.0, HEAD_SIZE_MM)
    page1 += [("text", hx, hy + 66, 3.2, "Head marker, 40 mm, id 0. Cut on the dashed line; stick it flat on the"),
              ("text", hx, hy + 71, 3.2, "head lid, centred, FRONT arrow toward the face. Black square must be 40 mm."),
              ("text", 15, 138, 3.2, "Floor marker, 80 mm, id 1 (optional): tape it flat on the floor, in view, clear of the robot.")]
    page1 += _marker_ops(FLOOR_ID, 25.0, 148.0, FLOOR_SIZE_MM)
    page1 += [("text", 15, 245, 3.2, "Keep the white margin around each marker. Matte paper; no tape over the black squares."),
              ("text", 15, 251, 3.2, "Generated by tools/real2sim.py sheet (OpenCV ArUco DICT_4X4_50). Nothing has been measured yet.")]
    bx, by = 30.0, 40.0
    page2 = [
        ("text", 15, 16, 5.0, "Camera calibration board (ChArUco 6 x 8, 25 mm squares)"),
        ("text", 15, 23, 3.2, "Print at 100 %. Keep it flat (tape it to a book). Film it for 20 s from different angles"),
        ("text", 15, 28, 3.2, "and distances with the same camera mode used for the robot video."),
        ("text", 15, 252, 3.2, "Squares must measure 25 mm. Board 150 x 200 mm."),
    ] + _board_ops(bx, by)
    return [page1, page2]


def sheet_svg(page: list[tuple]) -> str:
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_MM[0]:g}mm" height="{PAGE_MM[1]:g}mm" '
           f'viewBox="0 0 {PAGE_MM[0]:g} {PAGE_MM[1]:g}">',
           f'<rect width="{PAGE_MM[0]:g}" height="{PAGE_MM[1]:g}" fill="#fff"/>']
    for op in page:
        if op[0] in ("rect", "white"):
            fill = ' fill="#fff"' if op[0] == "white" else ""
            out.append(f'<rect x="{op[1]:.3f}" y="{op[2]:.3f}" width="{op[3]:.3f}" height="{op[4]:.3f}"{fill}/>')
        elif op[0] == "dash":
            out.append(f'<rect x="{op[1]:.3f}" y="{op[2]:.3f}" width="{op[3]:.3f}" height="{op[4]:.3f}" '
                       'fill="none" stroke="#000" stroke-width="0.2" stroke-dasharray="2 1.5"/>')
        elif op[0] == "line":
            out.append(f'<line x1="{op[1]:.3f}" y1="{op[2]:.3f}" x2="{op[3]:.3f}" y2="{op[4]:.3f}" '
                       f'stroke="#000" stroke-width="{op[5]:g}"/>')
        elif op[0] == "poly":
            points = " ".join(f"{x:.3f},{y:.3f}" for x, y in op[1])
            out.append(f'<polygon points="{points}"/>')
        elif op[0] == "text":
            text = op[4].replace("&", "&amp;").replace("<", "&lt;")
            out.append(f'<text x="{op[1]:g}" y="{op[2]:g}" font-family="Helvetica, Arial, sans-serif" '
                       f'font-size="{op[3]:g}">{text}</text>')
    return "\n".join(out + ["</svg>", ""])


def sheet_pdf(pages: list[list[tuple]]) -> bytes:
    """Minimal vector PDF (A4, millimetre-exact, built-in Helvetica, no compression)."""
    k = 72.0 / 25.4  # points per millimetre

    def content(page) -> bytes:
        parts = [f"{k:.6f} 0 0 {-k:.6f} 0 {PAGE_MM[1] * k:.4f} cm 0 g 0 G"]  # mm units, origin top-left
        for op in page:
            if op[0] == "rect":
                parts.append(f"{op[1]:.3f} {op[2]:.3f} {op[3]:.3f} {op[4]:.3f} re f")
            elif op[0] == "white":
                parts.append(f"1 g {op[1]:.3f} {op[2]:.3f} {op[3]:.3f} {op[4]:.3f} re f 0 g")
            elif op[0] == "dash":
                parts.append(f"0.2 w [2 1.5] 0 d {op[1]:.3f} {op[2]:.3f} {op[3]:.3f} {op[4]:.3f} re S [] 0 d")
            elif op[0] == "line":
                parts.append(f"{op[5]:g} w {op[1]:.3f} {op[2]:.3f} m {op[3]:.3f} {op[4]:.3f} l S")
            elif op[0] == "poly":
                (x0, y0), rest = op[1][0], op[1][1:]
                parts.append(f"{x0:.3f} {y0:.3f} m " + " ".join(f"{x:.3f} {y:.3f} l" for x, y in rest) + " h f")
            elif op[0] == "text":
                text = op[4].replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
                parts.append(f"BT /F1 {op[3]:g} Tf 1 0 0 -1 {op[1]:g} {op[2]:g} Tm ({text}) Tj ET")
        return "\n".join(parts).encode("latin-1")

    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for page in pages:
        stream = content(page)
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_MM[0] * k:.4f} {PAGE_MM[1] * k:.4f}] "
                        f"/Resources << /Font << /F1 3 0 R >> >> /Contents {len(objects)} 0 R >>").encode())
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Count {len(kids)} /Kids [{' '.join(kids)}] >>".encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def sheet_raster(page: list[tuple], px_per_mm: int = 8) -> np.ndarray:
    """Grey raster of the geometry on a page (text omitted); used by tests and previews."""
    image = np.full((int(PAGE_MM[1] * px_per_mm), int(PAGE_MM[0] * px_per_mm)), 255, np.uint8)
    for op in page:
        if op[0] in ("rect", "white"):
            x0, y0 = round(op[1] * px_per_mm), round(op[2] * px_per_mm)
            x1, y1 = round((op[1] + op[3]) * px_per_mm), round((op[2] + op[4]) * px_per_mm)
            image[y0:y1, x0:x1] = 255 if op[0] == "white" else 0
    return image


# ---- camera ------------------------------------------------------------------


@dataclass
class Camera:
    matrix: np.ndarray  # 3 x 3 intrinsics, pixels
    dist: np.ndarray  # OpenCV distortion coefficients
    size: tuple[int, int]  # width, height
    calibrated: bool
    source: str
    rms_px: float | None = None

    def to_json(self) -> dict:
        return {"matrix": self.matrix.tolist(), "dist": self.dist.ravel().tolist(), "size": list(self.size),
                "calibrated": self.calibrated, "source": self.source, "rms_px": self.rms_px}

    @classmethod
    def from_json(cls, data: dict) -> "Camera":
        return cls(np.array(data["matrix"], dtype=float), np.array(data["dist"], dtype=float),
                   tuple(data["size"]), bool(data["calibrated"]), data["source"], data.get("rms_px"))

    def scaled_to(self, size: tuple[int, int]) -> "Camera":
        """Same camera at another resolution with the same aspect ratio."""
        if tuple(size) == tuple(self.size):
            return self
        sx, sy = size[0] / self.size[0], size[1] / self.size[1]
        if abs(sx - sy) > 0.01 * sx:
            raise ValueError(f"calibration is for {self.size}, video is {size}: different aspect ratio")
        matrix = self.matrix.copy()
        matrix[0] *= sx
        matrix[1] *= sy
        return Camera(matrix, self.dist, tuple(size), self.calibrated, self.source, self.rms_px)


def guessed_camera(size: tuple[int, int], hfov_deg: float = UNCALIBRATED_HFOV_DEG) -> Camera:
    """Pinhole guess for an uncalibrated camera: square pixels, centred, no distortion."""
    focal = 0.5 * max(size) / math.tan(math.radians(hfov_deg) / 2)
    matrix = np.array([[focal, 0, size[0] / 2], [0, focal, size[1] / 2], [0, 0, 1.0]])
    return Camera(matrix, np.zeros(5), tuple(size), False,
                  f"uncalibrated guess: {hfov_deg:g} degree field of view along the long side, no distortion")


def _detector():
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(dictionary(), parameters)


def detect(gray: np.ndarray, detector=None) -> dict[int, np.ndarray]:
    """Marker id -> 4 x 2 corner pixels (top-left, top-right, bottom-right, bottom-left)."""
    corners, ids, _ = (detector or _detector()).detectMarkers(gray)
    return {} if ids is None else {int(i): c.reshape(4, 2) for i, c in zip(ids.ravel(), corners)}


def marker_pose(corners: np.ndarray, size_m: float, camera: Camera, previous_q: np.ndarray | None = None):
    """Marker pose in the camera frame: (position m, quaternion wxyz, reprojection px).

    A small square seen nearly face-on has two plausible orientations. Both
    IPPE solutions are compared: the lower reprojection error wins unless the
    other is nearly as good and closer to the previous frame's orientation.
    """
    half = size_m / 2
    points = np.array([[-half, half, 0], [half, half, 0], [half, -half, 0], [-half, -half, 0]], dtype=np.float64)
    count, rvecs, tvecs, errors = cv2.solvePnPGeneric(points, corners.astype(np.float64), camera.matrix,
                                                      camera.dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
    if not count:
        return None
    candidates = [(g.from_matrix(cv2.Rodrigues(r)[0]), t.ravel(), float(e.ravel()[0]))
                  for r, t, e in zip(rvecs, tvecs, errors)]
    best = candidates[0]
    if previous_q is not None and len(candidates) > 1 and candidates[1][2] < 2.0 * candidates[0][2] + 0.2:
        def angle(q):
            return float(np.linalg.norm(g.rotvec(g.mul(g.conj(previous_q), q))))
        best = min(candidates, key=lambda c: angle(c[0]))
    return best[1], best[0], best[2]


# ---- video -> torso pose track -----------------------------------------------


@dataclass
class Track:
    times: np.ndarray
    positions: np.ndarray
    quaternions: np.ndarray  # body frame (x toward the face) in `frame`
    reprojection_px: np.ndarray
    frame: str
    frame_definition: str
    frames_total: int
    camera: Camera
    notes: list[str] = field(default_factory=list)


def frame_poses(gray: np.ndarray, camera: Camera, detector=None, previous_q=None):
    """(head pose, floor pose) in the camera frame; either may be None."""
    found = detect(gray, detector)
    head = marker_pose(found[HEAD_ID], HEAD_SIZE_MM / 1000.0, camera, previous_q) if HEAD_ID in found else None
    floor = marker_pose(found[FLOOR_ID], FLOOR_SIZE_MM / 1000.0, camera) if FLOOR_ID in found else None
    return head, floor


def track_frames(frames, camera: Camera | None = None, max_reprojection_px: float = 3.0) -> Track:
    """Track the head marker through an iterable of (time_s, BGR or grey image)."""
    detector = _detector()
    times, positions, quaternions, errors, floors = [], [], [], [], []
    total, previous_q, rejected = 0, None, 0
    for t, image in frames:
        total += 1
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if camera is None:
            camera = guessed_camera((gray.shape[1], gray.shape[0]))
        else:
            camera = camera.scaled_to((gray.shape[1], gray.shape[0]))
        head, floor = frame_poses(gray, camera, detector, previous_q)
        if floor is not None and floor[2] <= max_reprojection_px:
            floors.append(floor)
        if head is None:
            continue
        if head[2] > max_reprojection_px:
            rejected += 1
            continue
        previous_q = head[1]
        times.append(t), positions.append(head[0]), quaternions.append(head[1]), errors.append(head[2])
    if camera is None:
        raise ValueError("the video has no frames")
    notes = [f"head marker found in {len(times)} of {total} frames"]
    if rejected:
        notes.append(f"{rejected} detections dropped for reprojection error above {max_reprojection_px:g} px")
    if not camera.calibrated:
        notes.append("camera NOT calibrated: intrinsics are a guess; expect several percent error in "
                     "distances and a few degrees in tilt (see reference/REAL2SIM-CAPTURE.md)")
    positions = np.array(positions, dtype=float).reshape(-1, 3)
    quaternions = np.array(quaternions, dtype=float).reshape(-1, 4)
    frame = "camera"
    definition = "fixed camera, OpenCV convention: x right, y down, z along the optical axis"
    if len(floors) >= 5 and len(times):
        floor_p = np.median(np.array([f[0] for f in floors]), axis=0)
        floor_q = g.mean(np.array([f[1] for f in floors]))
        positions, quaternions = g.relative(floor_p, floor_q, positions, quaternions)
        frame = "floor_marker"
        definition = ("origin at the floor marker's centre, z up out of the floor, x to the right of the printed "
                      f"marker, y to its top; floor marker pose averaged over {len(floors)} frames (fixed camera)")
        notes.append("floor marker used as the world frame")
    if len(quaternions):
        quaternions = g.mul(quaternions, BODY_FROM_MARKER)
    return Track(np.array(times, dtype=float), positions, quaternions, np.array(errors, dtype=float),
                 frame, definition, total, camera, notes)


def video_frames(path: Path | str, every: int = 1):
    """Yield (time_s, frame) from a video file using the container's timestamps."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"cannot open video {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    index, last = 0, -1.0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            # Presentation time of the frame just read; a constant one-frame shift on
            # some backends is absorbed by the fitted time offset.
            t = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if not (t > last):
                t = index / fps
            last = t
            if index % every == 0:
                yield t, frame
            index += 1
    finally:
        capture.release()


def track_video(path: Path | str, camera: Camera | None = None) -> Track:
    return track_frames(video_frames(path), camera)


def calibrate_camera(frames, max_views: int = 40, min_corners: int = 8) -> Camera:
    """Intrinsics from views of the printed ChArUco board (cv2.calibrateCamera)."""
    charuco = cv2.aruco.CharucoDetector(board())
    views, size = [], None
    for _, image in frames:
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        size = (gray.shape[1], gray.shape[0])
        corners, ids, _, _ = charuco.detectBoard(gray)
        if ids is not None and len(ids) >= min_corners:
            object_points, image_points = board().matchImagePoints(corners, ids)
            views.append((object_points.astype(np.float32), image_points.astype(np.float32)))
    if len(views) < 5:
        raise ValueError(f"only {len(views)} usable views of the calibration board; need at least 5 "
                         "from clearly different angles")
    step = max(1, len(views) // max_views)
    views = views[::step][:max_views]
    rms, matrix, dist, _, _ = cv2.calibrateCamera([v[0] for v in views], [v[1] for v in views], size, None, None,
                                                  flags=cv2.CALIB_FIX_K3)
    return Camera(matrix, dist.ravel(), size, True,
                  f"cv2.calibrateCamera on {len(views)} ChArUco views", float(rms))


def save_camera(camera: Camera, path: Path | str) -> None:
    Path(path).write_text(json.dumps(camera.to_json(), indent=2) + "\n")


def load_camera(path: Path | str) -> Camera:
    return Camera.from_json(json.loads(Path(path).read_text()))


# ---- synthetic views (tests and the pipeline demo) ---------------------------


def marker_texture(marker_id: int, size_mm: float, px_per_mm: float = 10.0, margin_mm: float = 6.0):
    """(image, physical width m) of a marker with its white margin."""
    side = int(round(size_mm * px_per_mm))
    margin = int(round(margin_mm * px_per_mm))
    image = cv2.aruco.generateImageMarker(dictionary(), marker_id, side, borderBits=1)
    image = cv2.copyMakeBorder(image, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=255)
    return image, (size_mm + 2 * margin_mm) / 1000.0


def board_texture(px_per_mm: int = 8):
    width, height = (int(n * BOARD_SQUARE_MM) for n in BOARD_SQUARES)
    image = board().generateImage((width * px_per_mm, height * px_per_mm), marginSize=0, borderBits=1)
    image = cv2.copyMakeBorder(image, 80, 80, 80, 80, cv2.BORDER_CONSTANT, value=255)
    return image, (width + 160 / px_per_mm) / 1000.0, (height + 160 / px_per_mm) / 1000.0


def render(camera: Camera, planes: list[tuple], noise: float = 2.0, seed: int = 0) -> np.ndarray:
    """Grey image of textured planes: [(texture, width m, height m, position, quaternion)].

    Each plane's frame is the OpenCV marker frame (x right, y to the top, z
    out), pose given in the camera frame. Rendered at 2x and reduced so edges
    are anti-aliased; Gaussian pixel noise is seeded.
    """
    width, height = camera.size
    scale = 2
    canvas = np.full((height * scale, width * scale), 128, np.uint8)
    matrix = camera.matrix.copy()
    matrix[:2] *= scale
    for texture, plane_w, plane_h, position, quaternion in planes:
        corners = np.array([[-plane_w / 2, plane_h / 2, 0], [plane_w / 2, plane_h / 2, 0],
                            [plane_w / 2, -plane_h / 2, 0], [-plane_w / 2, -plane_h / 2, 0]])
        rvec = cv2.Rodrigues(g.to_matrix(np.asarray(quaternion, dtype=float)))[0]
        pixels, _ = cv2.projectPoints(corners, rvec, np.asarray(position, dtype=float), matrix, camera.dist)
        th, tw = texture.shape[:2]
        source = np.array([[0, 0], [tw, 0], [tw, th], [0, th]], dtype=np.float32)
        homography = cv2.getPerspectiveTransform(source, pixels.reshape(4, 2).astype(np.float32))
        cv2.warpPerspective(texture, homography, (width * scale, height * scale), dst=canvas,
                            flags=cv2.INTER_AREA, borderMode=cv2.BORDER_TRANSPARENT)
    image = cv2.resize(canvas, (width, height), interpolation=cv2.INTER_AREA).astype(np.float32)
    image = cv2.GaussianBlur(image, (0, 0), 0.6)
    image += np.random.default_rng(seed).normal(0.0, noise, image.shape)
    return np.clip(image, 0, 255).astype(np.uint8)


def look_at(camera_position, target, up=(0.0, 0.0, 1.0)):
    """World pose expressed in a camera placed at camera_position looking at target.

    Returns (position, quaternion) of the WORLD frame in the camera frame
    (OpenCV camera axes), for building synthetic scenes.
    """
    camera_position, target = np.asarray(camera_position, dtype=float), np.asarray(target, dtype=float)
    forward = target - camera_position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.asarray(up, dtype=float))
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    rotation = np.stack([right, down, forward])  # rows: camera axes in world coordinates
    return -rotation @ camera_position, g.from_matrix(rotation)
