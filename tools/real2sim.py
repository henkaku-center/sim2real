#!/usr/bin/env python3
"""Real-to-sim calibration: marker sheet, recorder, tracker, fit and report.

Optional reference tooling; nothing here flashes or changes firmware.

  uv run python tools/real2sim.py sheet                        # printable marker sheet
  uv run python tools/real2sim.py record sysid --http --out run.jsonl
  uv run python tools/real2sim.py calibrate run.jsonl robot.mp4 --board-video board.mp4 --out out/
  uv run python tools/real2sim.py demo --out /tmp/real2sim     # synthetic end-to-end example

See reference/REAL2SIM-CAPTURE.md for the physical steps.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.real2sim import fit as fitting  # noqa: E402
from sim.real2sim import marker, pipeline, recorder, runlog  # noqa: E402


def cmd_sheet(args):
    pages = marker.sheet_pages()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(marker.sheet_pdf(pages))
    print(f"wrote {out} (2 pages, A4; print at 100 %)")
    if args.svg:
        for number, page in enumerate(pages, 1):
            path = out.with_name(f"{out.stem}-{number}.svg")
            path.write_text(marker.sheet_svg(page))
            print(f"wrote {path}")


def cmd_record(args):
    slew = None if args.no_ramp else (args.slew_rate if args.slew_rate else "manifest")
    if args.port:
        import time

        import sesame_s3_console  # the class console's serial open; never reconnects
        transport = recorder.LineTransport(sesame_s3_console.open_device(args.port))
        print("USB serial: follow the documented power isolation for this robot. Waiting for the board to boot…")
        time.sleep(2.5)  # opening USB may reset the board
        for line in transport.read_lines():
            print("  " + line)
    elif args.http:
        transport = recorder.HttpTransport(args.http)
    else:
        print("DRY RUN against the simulated firmware: no robot is commanded; the log is labelled dry-run.")
        if args.fast:
            header, records = recorder.dry_run(args.sequence, slew_rate_deg_s=slew, settle=not args.raw_timing)
            runlog.write(args.out, header, records)
            print(f"wrote {args.out}: {len(records)} records, {header['sequence']['duration_s']:.1f} s")
            return
        transport = recorder.SimulatedFirmware()
    try:
        header, records = recorder.record(transport, args.sequence, slew_rate_deg_s=slew,
                                          settle=not args.raw_timing, note=args.note)
    except recorder.RecorderError as error:
        raise SystemExit(f"recording stopped: {error}")
    finally:
        transport.close()
    runlog.write(args.out, header, records)
    info = header["recorder"]
    print(f"wrote {args.out}: {len(records)} records, evidence={header['evidence']}")
    if info["device_errors"]:
        print("device reported errors:", *info["device_errors"], sep="\n  ")
    if info["clamped_deg"]:
        print("targets clamped to the device's exported limits (requested -> effective):", info["clamped_deg"])
    print("An acknowledgement is not physical confirmation; check the video.")


def _camera(args):
    if getattr(args, "camera", None):
        return marker.load_camera(args.camera)
    if getattr(args, "board_video", None):
        camera = marker.calibrate_camera(marker.video_frames(args.board_video, every=5))
        print(f"camera calibrated from {args.board_video}: reprojection RMS {camera.rms_px:.2f} px")
        return camera
    print("WARNING: no camera calibration given; using a guessed field of view. "
          "Expect several percent error on distances and a few degrees on tilt.")
    return None


def cmd_calibrate_camera(args):
    camera = marker.calibrate_camera(marker.video_frames(args.video, every=args.every))
    marker.save_camera(camera, args.out)
    print(f"wrote {args.out}: fx={camera.matrix[0, 0]:.1f} fy={camera.matrix[1, 1]:.1f} "
          f"reprojection RMS {camera.rms_px:.2f} px ({camera.source})")


def _track(args, out):
    model = pipeline.load_model(args.model)
    track = marker.track_video(args.video, _camera(args))
    origin, source = pipeline.marker_origin(model, pipeline.load_measurements(args.measurements))
    path = pipeline.add_track(args.log, track, origin, source, out)
    print(f"wrote {path}: frame={track.frame}; " + "; ".join(track.notes))
    return path


def cmd_track(args):
    _track(args, args.out or args.log)


def _fit(paths, args):
    logs = {Path(p).stem: runlog.load(p) for p in paths}
    result, report_path = pipeline.fit_and_report(
        logs, args.out, model=pipeline.load_model(args.model), params=args.params.split(","),
        measurements=pipeline.load_measurements(args.measurements))
    print(pipeline.summary(result))
    print(f"report: {report_path}")


def cmd_fit(args):
    _fit(args.logs, args)


def cmd_calibrate(args):
    _fit([_track(args, args.log)], args)  # the marker track is added to the log in place


def cmd_validate(args):
    for path in args.logs:
        log = runlog.load(path)
        print(f"{path}: valid, evidence={log.evidence}, {len(log.commands)} commands, "
              f"{len(log.replies)} replies, {len(log.pose_t)} torso poses, {len(log.imu_t)} IMU samples")


def cmd_demo(args):
    for label, (result, report_path) in pipeline.demo(args.out, video=not args.no_video).items():
        print(f"\n== {label} ==")
        print(pipeline.summary(result))
        print(f"report: {report_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--model", default=str(pipeline.MODEL_PATH), help="compiled from this MJCF")
        p.add_argument("--measurements", default=str(pipeline.MEASUREMENTS_PATH))

    def fit_options(p):
        p.add_argument("--params", default=",".join(fitting.DEFAULT_PARAMS),
                       help=f"comma-separated subset of: {', '.join(fitting.PARAMS)}")
        p.add_argument("--out", required=True, help="directory for fit.json and report.html")

    p = sub.add_parser("sheet", help="write the printable marker sheet (PDF)")
    p.add_argument("--out", default=str(pipeline.SHEET_PATH))
    p.add_argument("--svg", action="store_true", help="also write one SVG per page")
    p.set_defaults(run=cmd_sheet)

    p = sub.add_parser("record", help="play a sequence and write the run log")
    p.add_argument("sequence", help="one of: " + ", ".join(recorder.sequence_names()))
    p.add_argument("--out", required=True)
    p.add_argument("--port", help="USB serial port (uses tools/sesame_s3_console.py)")
    p.add_argument("--http", nargs="?", const="192.168.4.1", help="robot Wi-Fi console address (battery runs)")
    p.add_argument("--fast", action="store_true", help="dry run without waiting in real time")
    p.add_argument("--no-ramp", action="store_true", help="the running firmware does not ramp targets")
    p.add_argument("--slew-rate", type=float, help="firmware ramp in deg/s if not the manifest value")
    p.add_argument("--raw-timing", action="store_true", help="do not wait for each ramp to finish")
    p.add_argument("--note", default="")
    p.set_defaults(run=cmd_record)

    p = sub.add_parser("calibrate-camera", help="camera intrinsics from a video of the ChArUco board")
    p.add_argument("video")
    p.add_argument("--out", required=True)
    p.add_argument("--every", type=int, default=5, help="use every Nth frame")
    p.set_defaults(run=cmd_calibrate_camera)

    p = sub.add_parser("track", help="add the marker's torso pose track from a video to a run log")
    p.add_argument("log")
    p.add_argument("video")
    p.add_argument("--camera", help="camera JSON from calibrate-camera")
    p.add_argument("--out", help="write a new log instead of updating in place")
    common(p)
    p.set_defaults(run=cmd_track)

    p = sub.add_parser("fit", help="fit parameters to tracked logs and write the report")
    p.add_argument("logs", nargs="+")
    fit_options(p)
    common(p)
    p.set_defaults(run=cmd_fit)

    p = sub.add_parser("calibrate", help="after a capture: track the video, fit, write the report")
    p.add_argument("log")
    p.add_argument("video")
    p.add_argument("--board-video", help="video of the ChArUco board, same camera mode")
    p.add_argument("--camera", help="camera JSON from an earlier calibrate-camera")
    fit_options(p)
    common(p)
    p.set_defaults(run=cmd_calibrate)

    p = sub.add_parser("validate", help="check run logs against the schema")
    p.add_argument("logs", nargs="+")
    p.set_defaults(run=cmd_validate)

    p = sub.add_parser("demo", help="synthetic end-to-end example (pipeline validation only)")
    p.add_argument("--out", required=True)
    p.add_argument("--no-video", action="store_true", help="skip the rendered marker video")
    p.set_defaults(run=cmd_demo)

    args = parser.parse_args()
    try:
        args.run(args)
    except (runlog.RunLogError, ValueError, KeyError) as error:
        raise SystemExit(f"error: {error}")


if __name__ == "__main__":
    main()
