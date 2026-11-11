"""Marker sheet, detection and pose recovery on synthetic frames (no camera).

Stated tolerances, ideal pinhole camera, 1280x720, marker 0.35-0.6 m away:
position within 1.5 mm across the image and 6 mm along the optical axis,
attitude within 1.5 degrees; motion relative to the first frame within 2.5 mm
RMS. Real lenses, motion blur and rolling shutter are not simulated here.
"""

import math

import cv2
import numpy as np
import pytest

from sim.real2sim import geometry as g
from sim.real2sim import marker, pipeline

SIZE = (1280, 720)


@pytest.fixture(scope="module")
def camera():
    camera = marker.guessed_camera(SIZE)
    camera.calibrated, camera.source = True, "synthetic pinhole"
    return camera


def test_sheet_geometry_scale_bar_and_committed_pdf():
    pages = marker.sheet_pages()
    found = marker.detect(marker.sheet_raster(pages[0], 8))
    side = {i: float(np.linalg.norm(c[1] - c[0])) / 8 for i, c in found.items()}
    assert side[marker.HEAD_ID] == pytest.approx(40.0, abs=0.2) and marker.HEAD_SIZE_MM <= 40.0
    assert side[marker.FLOOR_ID] == pytest.approx(80.0, abs=0.2)
    bar = [op for op in pages[0] if op[0] == "line" and op[2] == op[4]]
    assert len(bar) == 1 and bar[0][3] - bar[0][1] == pytest.approx(100.0)
    cut = next(op for op in pages[0] if op[0] == "dash")
    assert cut[3] <= 52.0 and cut[4] <= 72.0, "head cut-out must fit the 72 x 52 mm lid"
    pdf = marker.sheet_pdf(pages)
    assert pdf.startswith(b"%PDF-1.4") and pdf.count(b"/Type /Page ") == 2
    assert f"{210 * 72 / 25.4:.4f} {297 * 72 / 25.4:.4f}".encode() in pdf, "A4 media box"
    assert pipeline.SHEET_PATH.read_bytes() == pdf, "regenerate: uv run python tools/real2sim.py sheet"
    assert marker.sheet_svg(pages[0]).startswith('<svg xmlns="http://www.w3.org/2000/svg" width="210mm"')


def test_calibration_board_layout_matches_opencv():
    corners, ids, _, _ = cv2.aruco.CharucoDetector(marker.board()).detectBoard(marker.sheet_raster(marker.sheet_pages()[1], 8))
    assert len(ids) == (marker.BOARD_SQUARES[0] - 1) * (marker.BOARD_SQUARES[1] - 1)
    object_points, image_points = marker.board().matchImagePoints(corners, ids)
    board = next(op for op in marker.sheet_pages()[1] if op[0] == "rect")
    expected = (np.array([30.0, 40.0]) + object_points.reshape(-1, 3)[:, :2] * 1000.0) * 8
    assert board[1] >= 30.0 and np.abs(expected - image_points.reshape(-1, 2)).max() < 1.0  # within 0.125 mm


def test_known_poses_are_recovered(camera):
    texture, width = marker.marker_texture(marker.HEAD_ID, marker.HEAD_SIZE_MM)
    rng = np.random.default_rng(1)
    face_camera = g.from_rotvec(np.array([math.pi, 0.0, 0.0]))
    for k in range(12):
        position = np.array([rng.uniform(-0.12, 0.12), rng.uniform(-0.06, 0.06), rng.uniform(0.35, 0.6)])
        quaternion = g.mul(face_camera, g.from_rotvec(rng.normal(size=3) * np.array([0.5, 0.5, 1.5])))
        image = marker.render(camera, [(texture, width, width, position, quaternion)], seed=k)
        corners = marker.detect(image)[marker.HEAD_ID]
        found_p, found_q, reprojection = marker.marker_pose(corners, marker.HEAD_SIZE_MM / 1000.0, camera)
        error = np.abs(found_p - position)
        assert error[0] < 0.0015 and error[1] < 0.0015 and error[2] < 0.006, (k, error)
        angle = math.degrees(np.linalg.norm(g.rotvec(g.mul(g.conj(quaternion), found_q))))
        assert angle < 1.5 and reprojection < 1.0, (k, angle, reprojection)


def _scene(camera, count=16):
    """Body moves 60 mm forward, rises 30 mm, yaws 25 and pitches 8 degrees above a floor marker."""
    head, head_w = marker.marker_texture(marker.HEAD_ID, marker.HEAD_SIZE_MM)
    floor, floor_w = marker.marker_texture(marker.FLOOR_ID, marker.FLOOR_SIZE_MM)
    world_p, world_q = marker.look_at([0.05, -0.42, 0.34], [0.05, 0.0, 0.02])
    frames, truth_p, truth_q = [], [], []
    for k in range(count):
        s = k / (count - 1)
        body_p = np.array([0.10 + 0.06 * s, 0.02, 0.037 + 0.03 * math.sin(math.pi * s)])
        body_q = g.mul(g.from_rotvec([0, 0, math.radians(25) * s]),
                       g.from_rotvec([0, math.radians(8) * math.sin(math.pi * s), 0]))
        head_pose = g.compose(world_p, world_q, body_p, g.mul(body_q, g.conj(marker.BODY_FROM_MARKER)))
        floor_pose = g.compose(world_p, world_q, np.zeros(3), np.array([1.0, 0, 0, 0]))
        frames.append((k / 30.0, marker.render(camera, [(floor, floor_w, floor_w, *floor_pose),
                                                        (head, head_w, head_w, *head_pose)], seed=k)))
        truth_p.append(body_p), truth_q.append(body_q)
    return frames, np.array(truth_p), np.array(truth_q)


def _relative_error(track, truth_p, truth_q):
    p, q = g.relative(track.positions[0], track.quaternions[0], track.positions, track.quaternions)
    tp, tq = g.relative(truth_p[0], truth_q[0], truth_p, truth_q)
    position = 1000.0 * float(np.sqrt(((p - tp) ** 2).sum(axis=1).mean()))
    attitude = float(np.degrees(np.linalg.norm(g.rotvec(g.mul(g.conj(tq), q)), axis=1)).max())
    return position, attitude


def test_track_in_floor_marker_frame_and_cost_of_no_calibration(camera):
    frames, truth_p, truth_q = _scene(camera)
    track = marker.track_frames(frames, camera)
    assert track.frame == "floor_marker" and len(track.times) == len(frames)
    # Body frame convention: x toward FRONT, z up; absolute pose in the floor marker's frame.
    assert np.abs(track.positions - truth_p).max() < 0.005
    assert np.degrees(np.linalg.norm(g.rotvec(g.mul(g.conj(truth_q), track.quaternions)), axis=1)).max() < 1.5
    position, attitude = _relative_error(track, truth_p, truth_q)
    assert position < 2.5 and attitude < 1.5, (position, attitude)

    # Uncalibrated: focal length guessed 10 % short. The track is flagged and gets worse, not useless.
    wrong = marker.guessed_camera(SIZE, 2 * math.degrees(math.atan(math.tan(math.radians(32.5)) / 0.9)))
    guessed = marker.track_frames(frames, wrong)
    assert any("NOT calibrated" in note for note in guessed.notes)
    worse_position, worse_attitude = _relative_error(guessed, truth_p, truth_q)
    assert position < worse_position < 6.0 and worse_attitude < 2.5, (worse_position, worse_attitude)


def test_camera_calibration_from_board_views(camera, tmp_path):
    texture, width, height = marker.board_texture()
    rng = np.random.default_rng(3)
    views = []
    for k in range(10):
        position = np.array([rng.uniform(-0.05, 0.05), rng.uniform(-0.04, 0.04), rng.uniform(0.32, 0.5)])
        quaternion = g.mul(g.from_rotvec([math.pi, 0, 0]), g.from_rotvec(rng.normal(size=3) * [0.45, 0.45, 0.6]))
        views.append((k, marker.render(camera, [(texture, width, height, position, quaternion)], seed=100 + k)))
    calibrated = marker.calibrate_camera(views)
    assert calibrated.calibrated and calibrated.rms_px < 0.5
    assert calibrated.matrix[0, 0] == pytest.approx(camera.matrix[0, 0], rel=0.01)
    assert calibrated.matrix[1, 1] == pytest.approx(camera.matrix[1, 1], rel=0.01)
    marker.save_camera(calibrated, tmp_path / "camera.json")
    loaded = marker.load_camera(tmp_path / "camera.json")
    assert np.allclose(loaded.matrix, calibrated.matrix) and loaded.calibrated
    half = loaded.scaled_to((640, 360))
    assert half.matrix[0, 0] == pytest.approx(calibrated.matrix[0, 0] / 2)
    with pytest.raises(ValueError, match="at least 5"):
        marker.calibrate_camera(views[:3])


def test_video_file_round_trip(camera, tmp_path):
    frames, truth_p, _ = _scene(camera, count=8)
    path = tmp_path / "scene.avi"
    writer = cv2.VideoWriter(str(path), cv2.CAP_OPENCV_MJPEG, cv2.VideoWriter_fourcc(*"MJPG"), 30.0, SIZE)
    for _, image in frames:
        writer.write(cv2.cvtColor(image, cv2.COLOR_GRAY2BGR))
    writer.release()
    track = marker.track_video(path, camera)
    assert track.frames_total == 8 and len(track.times) == 8
    assert np.all(np.diff(track.times) > 0) and track.times[-1] - track.times[0] == pytest.approx(7 / 30.0, abs=0.01)
    assert np.abs(track.positions - truth_p).max() < 0.006  # MJPEG compression costs a little accuracy
