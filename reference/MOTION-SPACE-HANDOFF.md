# Motion-space handoff (2026-11-26)

Sesame's eight servos are re-expressed as eight named axes. The work comes in
four parts: a simulation-derived description of where the robot can stand and
walk, a text version of it for LLMs, Sesame Mind specs written in it, and an
interactive viewer for the talk. The viewer is served by the robot at
`http://sesame-s3-8b2c.local/space`. This note covers what exists, how to run
and change it, what has been verified and what is still open. The findings
and numbers themselves are in `reference/MOTION-SPACE.md`.

## Why it is built this way

- **Only about 10% of the 8-D joint box can stand.** If the joints are
  sampled uniformly, the robot mostly ends up with its centre of mass outside
  the paws, paddles too flat to carry the load, or same-side legs colliding.
  An LLM or a student designing in raw joint angles hits these all the time.
- **The axes are symmetric patterns, and the feet are solved, not chosen.**
  Hips are surge, spread, yaw and stride (all-legs, front/back, left/right
  and diagonal patterns of paw sweep). Height, pitch and roll are solved by
  foot inverse kinematics, so all four paws stay on the floor and the body
  cannot rock. Lift raises one diagonal and is only for gaits.
- **Feasibility is an explicit rule set, checked against MuJoCo.** The rules
  are joint limits, centre-of-mass margin of at least 10 mm, feet at least
  30°, floor clearance of at least 5 mm, and a same-side hip sum of at least
  −20°. A simpler inner budget sits inside them. `project()` shrinks any
  pose towards the centre until it passes, so wild input keeps its shape.
- **The same model runs in Python and in the browser.**
  `sim/motion_space.js` is a line-for-line port, and a node test pins it to
  Python. The viewer, the robot page and the presentation therefore show
  exactly what the planner enforces.

## What exists

| Piece | File | What it does |
|---|---|---|
| Model | `sim/motion_space.py` | `decode` (axes → joints, foot IK), `violations`, `project`, `within_budget`, `gait`, `describe` (LLM text), MuJoCo `Settler` (`holds`, `drive`), `report` |
| Numbers | `manifest/motion_space.yaml` | Centre, rules, single-axis ranges, tilt by height, budget, safe box, gait slopes |
| JS port | `sim/motion_space.js` | Same model plus map classification (`slice`) and an SVG scene renderer |
| Viewer source | `sim/motion_space_viewer.html` | Page template: 3-D view, map, sliders, gait buttons, six walkthroughs, LLM text, optional live robot |
| Viewer (generated) | `web/public/motion-space/index.html` | One self-contained file (~41 kB), no network; copy it anywhere |
| Robot page | `firmware/sesame-s3/space_ui.h` + `/space` route in `controller.cpp` (branch `feat/s3-mind-chat`) | The same page, gzipped in flash (15.6 kB), linked from the console |
| Mind specs | `tools/sesame_mind.py` | `axes` (periodic) and `axes_keys` (keyframe) specs; frames go through `project()`; designer prompt includes `describe()`; `GET /space` on the mind server returns the LLM text |
| Tests | `tests/test_motion_space.py`, `tests/test_motion_space_js.py`, `tests/test_sesame_mind.py` | IK against MuJoCo, hip-axis directions, no self-collision, YAML ranges, budget ⊂ feasible, 150 poses held, trot walks and turns, JS = Python, page freshness, spec round trips |

## Where things are

| | Branch (remote `fork` = memorist17/sim2real) | Head |
|---|---|---|
| Model, viewer, mind, tests, docs | `feat/sesame-mind` | `c6162cd` plus this note |
| Robot firmware | `feat/s3-mind-chat` (worktree `../sim2real-s3-mind-chat`) | `3de6e45` (= 824666e + `/space`) |

`feat/s3-mind-chat` is the robot's build line. **Never flash a main-based
build on this robot**: its saved calibration would be rejected.

## How to run and change it

```sh
uv run python -m sim.motion_space            # recompute the YAML's numbers in MuJoCo (~12 s)
uv run python -m sim.motion_space --text     # the LLM text
uv run python -m sim.motion_space --html     # rebuild web/public/motion-space/index.html
uv run python -m pytest -q tests/test_motion_space.py tests/test_motion_space_js.py tests/test_sesame_mind.py
```

After changing the model, the template or the YAML:

1. Rebuild the page (`--html`). The freshness test fails until you do.
2. Regenerate the robot's header from this checkout:
   `uv run python -m sim.motion_space --firmware-header ../sim2real-s3-mind-chat/firmware/sesame-s3/space_ui.h`.
3. In the worktree, run `python3 tools/sesame_s3.py build`, then
   `python3 tools/sesame_s3.py flash --port /dev/cu.usbmodemNNNN`. Look the
   port up each time; it changes between sessions.
4. Check `show` for `saved=1`, then fetch `/space`.

The viewer's walkthrough texts and colours are in the template's `STORIES`
and `CLS` tables. Numbers in the texts are read from the YAML, not typed in.

## Verified (2026-11-26)

- In simulation: 800/800 random feasible poses held as commanded. Every
  budget sample is feasible: 16 000 were checked during exploration and
  3000 are checked in the tests. A quarter-cycle stride/lift trot walks,
  and a spread/lift trot turns, with the slopes recorded in the YAML.
- The JS port agrees with Python on 303 poses (joints, rules, margins,
  projection, budget).
- Without a real browser: the page script was run against a stub DOM
  through every walkthrough, gait, slider, map click and projection
  toggle, with no runtime errors. Rendered snapshots were checked visually
  through Quick Look.
- On the robot: `3de6e45` was flashed over USB, and `saved=1` with
  manifest `f7382b66d6f7a844` was kept. Wi-Fi rejoined the hotspot. Fetched
  by IP, `/space` arrives in ~0.13 s with `Content-Encoding: gzip` and is
  byte-identical to the repository page.

## Not verified / open

- **No real-browser check yet.** Open `/space` (and the copied file) in
  Safari or Chrome at the projector's resolution, and click through the
  six walkthroughs.
- **"実機に送る" has never moved the robot.** It is shown only when the page
  comes from the robot. It sends `arm run`, then `pose` frames (at most
  10 Hz) and heartbeats; Freeze and OUTPUTS OFF are next to it. Try it
  first with the robot on the floor and someone at OUTPUTS OFF.
- **Nothing in the motion space has been measured on hardware.** The joint
  signs and soft limits are the manifest's assumptions. The geometry is the
  MJCF collision boxes, and masses, servo gain and torque are nominal. The
  next hardware checks are listed in `reference/MOTION-SPACE.md`.
- **Presentation hosting.** The talk is at
  `https://mini.taile70e.ts.net/presentation/1/`. Copy
  `web/public/motion-space/index.html` there, for example as
  `motion-space.html`, and link or iframe it. Do not iframe the robot's
  http page from the https deck: browsers block the mixed content.
- **Agent access to those URLs.** In auto mode, Claude's read-only GETs to
  `*.taile70e.ts.net` and the robot were refused as oversight-sensitive.
  Allowing them takes an `autoMode` entry in the user's own
  `~/.claude/settings.json`, which only the user can add.
