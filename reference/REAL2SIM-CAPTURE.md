# Real-to-sim capture: one robot, one video, about ten minutes

**Nothing has been measured yet.** So far the tooling below has run on synthetic
data alone (`tests/test_real2sim_*.py`), and the servo values and masses in
`manifest/robot.yaml` are still unmeasured-nominal. The instructor requested
this page (2026-11-12) as the reference capture for the course robot; it is
optional and puts no conditions on what students do with their own robots or
firmware.

## Before the session

1. Print `reference/real2sim/marker-sheet.pdf` (two A4 pages) at **100 % / actual
   size**, not "fit to page". Check that the scale bar reads 100 mm and the head
   marker's black square 40 mm; reprint if not. Matte paper.
2. The recorder uses `arm run`, which the reference firmware accepts once its
   calibration is verified and saved (`reference/SESAME-S3-CALIBRATION.md`).
   Otherwise the recorder stops with the device's own refusal.

## Physical steps

1. **Weigh** on a kitchen scale (1 g): the complete robot with its battery. If
   it is easy, also the battery alone, one upper leg with its foot servo, one
   lower paddle and the head lid. Write the numbers into
   `reference/real2sim/measurements.yaml`.
2. **Stick the head marker.** Cut along the dashed line (52 × 60 mm) and tape it
   flat on the head lid, centred, with the FRONT arrow toward the face. Keep the
   white margin; no tape over the black square. With the robot lying flat, legs
   out, measure the height of the marker paper above the floor and write it into
   the same file (`marker.centre_height_above_floor_at_rest_mm`).
3. **Floor.** Hard, flat, plain surface. Optionally tape the 80 mm floor marker
   flat on it, 15–20 cm in front of the robot, fully in view.
4. **Camera.** A phone on a tripod or a stack of books, landscape, 40–60 cm from
   the robot, looking down at 30–45°, so the robot and the floor marker stay
   inside the frame with a hand's width to spare. 60 frames per second if the
   phone offers it (1080p), otherwise 30. Stabilisation off, no zoom, focus and
   exposure locked, even light without glare on the marker. Do not touch the
   camera between the two clips below.
5. **Calibration clip (20 s).** Tape page 2 (the checker board) to a book and
   move it slowly in front of the camera in the same video mode: near and far,
   tilted left, right, up and down, into the corners of the frame.
6. **Run.** Unplug USB and power the robot from its battery. Join its Wi-Fi
   access point from the laptop (`Sesame-S3-…`). Lay the robot flat on its belly
   facing away from the floor marker's side of the frame, start the video, then:

   ```sh
   uv run python tools/real2sim.py record sysid --http --out reference/evidence/real2sim/sysid-1.jsonl
   ```

   `sysid` is one 17 s take: rest, stand, half squat, body sway, body twist,
   rest. Keep filming until the robot is back at rest. A second take
   (`sysid-2`) and `walk` (about 85 s with the firmware's 60°/s ramp) are useful
   if there is time. The Wi-Fi console is the only command path with USB
   unplugged; if the laptop cannot reach `http://192.168.4.1`, stop there and
   report it, because the access point has not been verified on hardware.

## Afterwards: one command

```sh
uv run python tools/real2sim.py calibrate reference/evidence/real2sim/sysid-1.jsonl robot.mp4 \
    --board-video board.mp4 --out out/sysid-1
```

It calibrates the camera from the board clip, adds the head marker's track to
the log file, fits the simulation parameters and writes `out/sysid-1/report.html` (open it on a phone)
and `fit.json`. Commit the small `.jsonl` logs and `measurements.yaml`; videos
stay out of the repository unless they go through Git LFS.

## What to expect, honestly

- **Camera calibration.** The board clip gives focal length, image centre and
  lens distortion. Without it (`calibrate` without `--board-video`) the tool
  guesses a 65° field of view and says so in the log: expect the focal-length
  error, typically several percent, as a proportional error on motion toward or
  away from the camera, and one to two degrees of tilt. On synthetic frames a
  10 % focal error raised the error on 60 mm of relative motion from 1.2 mm to
  3.1 mm RMS. With calibration, synthetic pose recovery is within 1.5 mm across
  the image, 6 mm along the optical axis and 1.5°; real lenses, motion blur and
  rolling shutter will add to that and are not simulated.
- **What the torso can tell.** Height, roll and pitch are fitted. Forward and
  sideways position and yaw are shown but not fitted, because they accumulate
  foot slip. With the reference firmware's 60°/s ramp the servos never reach
  their speed or torque limit, so the report will mark those as not
  identifiable and leave them nominal; gain, friction and the time offset are
  what such a run can inform. A build without the ramp can inform more.
- **Frames.** The log stores the marker pose in the floor marker's frame (z up)
  when the floor marker is visible, otherwise in the camera frame; the fit only
  uses motion relative to the rest pose at the start of the run, so start the
  recorder with the robot lying still, flat on the floor.
- A command acknowledgement is not proof of motion. The recorder logs what was
  sent and what the device replied; the video is the measurement.

Try the whole chain without hardware:
`uv run python tools/real2sim.py demo --out /tmp/real2sim-demo`.
