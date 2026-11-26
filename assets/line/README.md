# Line twin

A digital twin of the stations around the robot: a tabletop assembly line on which
open-source machines print, kit, solder and assemble a Sesame. It follows the
project goal of rehearsing a build before hardware moves. Started on 26 November
2026 alongside the "Sesame makes Sesame" concept trailer in the `aps` repository
(`trailer/`), whose keyframes inspired the first layout.

- `manifest/line.yaml` is the description: table, machines with pinned sources and
  licences, placed instances, fixtures, named targets, the ordered steps and one
  scripted rehearsal.
- `sim/line.py` composes it into one MuJoCo model and writes the reach evidence.
- `tools/fetch_line_models.py` downloads the pinned third-party models into the
  ignored `upstream/` folder (about 40 MB).
- `<layout>/reach.json` is the committed evidence for a layout. Only the current
  layout's record is checked for staleness; earlier ones are kept for comparison.
- `manifest/line_previs.yaml` and `sim/line_previs.py` play the trailer's twelve
  shots inside the twin and cut them into one video.

```bash
uv run python tools/fetch_line_models.py     # once
uv run python -m sim.line --summary          # findings
uv run python -m sim.line                    # regenerate reach.json
uv run python -m sim.line --check            # fail when reach.json is stale
uv run python -m sim.line --render out/      # stills, rehearsal video, index.html
uv run python -m sim.line_previs --summary   # shots, length, worst arm waypoint error
uv run python -m sim.line_previs --render out/   # previs.mp4 and previs.html (needs ffmpeg)
uv run pytest tests/test_line.py
```

## What it does and does not claim

It checks geometry only: whether fixtures and placeholder machines fit on the table,
and whether each gripper point can reach each target its steps name, using
position-only inverse kinematics inside the published joint limits. The rehearsal is
scripted joint motion with the item following the gripper.

It does not model grasping, soldering, printing, tool orientation, collisions or
cycle time. The printers are placeholder boxes with assumed dimensions. Nothing was
measured on hardware, and the record was generated on macOS only. The `evidence`
label on each step describes current practice in the world, taken from the trailer
research notes, not a result of this model.

## Layout `tabletop-v0`

The first layout copies the trailer picture: three printers in a row, one SO-101 in
front of them, one SO-101 for kitting, and a two-armed OpenArm on its pedestal
standing on the table. The twin finds that 6 of 14 gripper targets are reachable:

- One SO-101 in front of the middle printer reaches that bed but is about 135 mm
  short of each neighbouring bed.
- The kitting arm is 55 mm short of the printed-parts tray.
- With its pedestal on the table, neither OpenArm gripper reaches the jig (about
  320 mm short) or the pallet. In a separate sample of 20,000 random joint
  configurations the control points never came lower than about 0.26 m above the
  pedestal base; that sample is not part of the committed record.

These are properties of this layout, not of the machines. They are recorded so the
next layout can be compared against them.

## Layout `tabletop-v1`

The second layout answers each finding, and all 14 gripper targets are reachable:

- The printers eject finished parts onto an outfeed tray at their front, which is
  the common hobby practice, so one SO-101 serves all three.
- The trays and the kitting arm are pulled together.
- The OpenArm pedestal stands on a low stand behind the table, 0.45 m below the
  table top.
- No single pallet position was inside both the kitting arm's and the OpenArm's
  reach, so a short belt carries the pallet between them. The belt is a concept
  fixture; nothing about it is modelled beyond its footprint.

Collisions are still unchecked: an arm can pass through a printer frame or another
machine in this model without any warning.

## Pre-visualisation

`manifest/line_previs.yaml` restates the trailer storyboard (twelve shots, 59
seconds; `trailer/storyboard.js` in the `aps` repository) as cameras and events in
this layout. Arms move through inverse-kinematics waypoints, loose objects, hands,
screens and print heads are boxes on written paths, and the Sesame plays its stock
walk as joint angles while sliding along a path. It is an animatic for staging,
reach and timing. It is not evidence that any step works, and the rendered video is
not committed.
