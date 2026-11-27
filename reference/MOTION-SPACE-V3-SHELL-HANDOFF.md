# Motion space on the V3 body with the shell: handoff (2026-11-27)

The user asked for three things on 2026-11-26:

1. Put the motion-space work (`reference/MOTION-SPACE-HANDOFF.md`) into the
   APS mid-term deck. **Done and checked in a browser.**
2. Make the motion-space visuals (the viewer's 3-D robot and the slide-8
   video) show the robot as printed: the v3headarms dome and head arms
   (`bambu/stl/v3headarms/`). **Not started.**
3. Recompute the motion space with the shell on. **Not started.** One
   finding changes the scope: the motion space models a different body from
   the one the shell fits. The details are below.

Items 2 and 3 are one job. The recomputed model supplies both the numbers
and the geometry the visuals draw.

## 1. Deck (done)

`https://mini.taile70e.ts.net/presentation/1/` serves
`mini:~/dev/presentation/proto-kotaro/docs/presentations/4/` through the
symlink `~/dev/presentation/site/1`. The deck is "Building Sesame", APS
mid-term. The edits were made in place on mini.

- Slide 8 (`#s7`): the Motion space bullets, the footnote and the speaker
  notes now follow the current model. They cover the ~10% of random servo
  poses that stand, the four hip sweep patterns, the solved feet and
  shrinking towards the centre. The footnote says the robot serves the
  viewer but has not moved.
- Slide 9 (`#s8`): the Motion space box text.
- Slide 10 (`#s9`): one added sentence about moving the robot from the
  viewer.
- New appendix slide A5 (`#a5`): the viewer
  (`docs/presentations/4/motion-space.html`) in an iframe. The viewer is
  laid out at a virtual height of at least 800 px and scaled down to fit
  (the `.msvw` ResizeObserver), so the layout is the same at every
  projector resolution. Arrow keys still move the deck after a click
  inside the viewer, except on its inputs.
- The lead text says 5 appendix slides.

Checked with Vivaldi (Chromium 156) through Playwright at 1920×1080,
1440×900 and 1280×720:

- no slide overflows;
- the A5 iframe renders all 8 sliders and the 6 walkthroughs, with no
  console or page errors;
- the deck's keys work after clicking into the viewer, and the slider
  keys stay inside it.

Two bugs were found and fixed along the way. `loading="lazy"` left the
iframe blank in presentation mode. The unscaled iframe cut off sliders.

State and caveats:

- **Nothing is committed on mini.** That clone was already 5 commits ahead
  of `origin/main` with uncommitted deck edits before this work. Commit or
  push only when the user asks. The pre-edit backup is
  `mini:/tmp/deck4-index.backup-202611261636.html`, which is lost on
  reboot. The final `index.html` has md5
  `30eb8efe84d5ca02a07b93d47fb72132`.
- `~/dev/proto-kotaro` on the MacBook is a different, diverged clone of the
  same repository. Do not edit the deck there.
- The deck's `motion-space.html` is the **old Japanese-only viewer from
  `c6162cd`**. The bilingual viewer landed later in `a6587aa`. Re-copy
  `web/public/motion-space/index.html` when the model changes, or now.
- Browsers that already loaded the deck may hold a cached `index.html`.
  Reload it.

How to repeat the browser check (scripts were in `/tmp/deckcheck/`, which
may be gone):

- Playwright's own `launch()` and `launch_persistent_context()` hang with
  Vivaldi 8.3. Both hang on the first page, headless or not.
- What works: start Vivaldi yourself as a background command with
  `--headless=new --remote-debugging-port=9333
  --user-data-dir=/tmp/<fresh>`, then call `connect_over_cdp`. Use
  `contexts[0].pages[0]`, `goto(..., wait_until="commit")` (the deck's
  videos delay DOMContentLoaded) and a `?nc=` query to avoid the cache.
- Background commands stop after 30 minutes by default, which kills the
  browser mid-run. Pass a longer timeout.
- Auto mode refused `curl` to the tailnet URL and to the local CDP port.
  The Python Playwright route was allowed.
- Never point a test at the user's real Vivaldi profile.

## 2. Finding: the motion space models the wrong body

`sim/motion_space.py` takes every dimension and mass from
`sim/build_mjcf.py`, which is the upstream/S2-era baseline that
`manifest/robot.yaml` still declares. The shell, and the robot the user
built, use the **Loftwork V3 frame kit** (`reference/frame-and-cover_261105`).
That is the body in `bambu/scripts/sesame_model.py` with
`params-v3headarms.json`.

The numbers below come from `SesameModel` in the stand pose (hip 45,
knee 90). The bambu frame is x forward, y left, z up, with z = 0 at the
bottom of the torso.

| | motion space (MJCF) | V3 body (bambu) |
|---|---|---|
| Hip axes x, y (mm) | ±24.5, ±23.0 | +28.2 / −28.6, ±38.0 |
| Hip→knee along the femur | 36.9 | 36.8, plus a ~7.9 mm sideways knee offset that the MJCF ignores |
| Knee→paw | 47.0 | 47 (knee z 16.4 → tip z −30.5) |
| Knee axis above torso bottom | 16.3 (−1.8 from a 36.2 mm box's centre) | 16.4 |
| Torso mass | 190 g, CoM at the box centre | 259.2 g @ (1.0, 0.1, 21.0); includes the hip servos, battery 47 g, electronics 42 g, head-mount |
| Femur and foot servo, per leg | 19 g | 18.4 g @ about (±51.5, ±57.9, 17.1) |
| Foot paddle, per leg | 5 g | 4.8 to 5.1 g |
| Body total | 286 g | 352.7 g @ (0.66, 0.08, 19.02) |
| Shell dome | — | 109.0 g @ (0.60, 0.10, 80.59); bbox x −93.4…94.6, y −93.9…94.1, z 34.5…160.7 |
| Head arms | — | 17.1 g @ (0.57, 0.00, 44.27) |
| Robot with shell | — | 478.7 g |

- The legs themselves match. The "17 mm drop" between bambu's hip and knee
  points is not real: the hip point is an arbitrary point on the vertical
  hip axis.
- The real differences are three:
  - the hips are 15 mm wider apart sideways and 4 mm further apart front
    to back;
  - the torso is 69 g heavier;
  - the shell and arms add 126 g, with their CoM about 60 mm above the
    torso bottom.
- With the shell, the robot is +67% heavier than the motion space assumes.
  That raises foot-servo load (the `load < 0.5` stall rule), sag and
  tipping when tilted. Expect `foot_min_deg`, the tilt table, the budget
  and the gait slopes to move.
- The wider hips change `hip_pair_sum_min_deg`, the same-side leg
  collision threshold, and the support polygon.
- Every mass is still the bambu estimate. Nothing has been weighed:
  `mass_model.status` is "provisional-nominal".
- Simply adding the shell's mass to the S2 body would draw the V3 shell on
  a body it does not fit, and would still be off by 67 g. Do not do that
  silently.

## 3. Proposed plan for items 2 and 3

This is not started. Decide step 0 with the user first.

0. **Where the V3 body description lives.** AGENTS.md says the manifest is
   canonical for geometry. `robot.yaml` keeps the S2 baseline "until the
   new physical joint mapping is verified", and changing it moves every
   simulator. The proposed option is a motion-space body variant:
   - generate it from bambu, e.g. `manifest/motion_space_body.yaml` written
     by a new `sim/motion_space_body.py --from-bambu params-v3headarms.json`;
   - include hips, knee z, segment lengths, torso box, group masses and
     CoMs, and the shell parts with their inertia;
   - leave `robot.yaml` and `models/sesame.xml` untouched;
   - record the choice in `DECISIONS.md`.
1. **`sim/motion_space.py`.** Load the dimensions from the body file
   instead of `sim.build_mjcf`, keeping the same names. Then:
   - `_com()` gains the torso CoM offset and the shell parts.
   - `_lowest_body_point()` uses the V3 torso box. Use the frame and
     covers' extent, not the head-mount's 76.7 mm top. Measure it from the
     kit STLs.
   - `physics_model()` builds the MJCF with the V3 dimensions. Either give
     `build_mjcf.build_xml` a dims argument or edit the `MjSpec`. Attach the
     torso load, dome and arms as welded child bodies with explicit inertia,
     computed from the meshes with trimesh.
   - The dome cannot reach the floor in standing poses: its rim is 34.5 mm
     above the torso bottom. Bambu's fit check reports 6.0 mm minimum leg
     clearance over the walking range. Assert both in a test rather than
     making the dome collide (a mesh hull would swallow the legs).
2. **`sim/motion_space.js`.** Port the `_com` change and the new dims
   (`viewer_data()` already passes `dims`). Add the shell to `scene()` as
   torso-fixed triangles.
   - Decimate the dome from 21 768 faces to about 1 to 2k, keeping the
     lattice readable. Decimate the head-mount and arms too.
   - Watch the page size: the robot serves it gzipped from flash (15.6 kB
     before this change).
   - `tests/test_motion_space_js.py` must still match Python on the 303
     poses.
3. **Recompute.** Re-derive the rules, not only the ranges.
   - `report()` only re-checks ranges, safe-box corners, held poses and
     gait speeds.
   - The rule thresholds and `tilt_by_height` were fitted by exploration
     on 2026-11-13, and that script is not in the repository. Rebuild the
     sweeps.
   - Update `manifest/motion_space.yaml`, `reference/MOTION-SPACE.md`, the
     numbers in the viewer's walkthrough texts (they are read from the
     YAML) and `describe()`.
   - Expect to update `tests/test_motion_space.py` and the Sesame Mind
     tests.
4. **Video.** The slide-8 `img/motion_space.mp4` ("N/10 axis", "MuJoCo ·
   8 axes instead of 8 servos · 300 deg/s slew") was not made by any
   script in this repository. Write one, e.g. `--video` in
   `sim/motion_space.py`:
   - render the sweep with the V3 meshes and the shell, as
     `bambu/scripts/render.py` and `sim_check.articulated_model` already
     load them;
   - output into `out/`, which is gitignored;
   - copy the result into the deck's `img/`.
5. **Deck.** Re-copy the viewer, swap the video and poster, and re-check
   every number in the text against the new YAML: 10%, 800/800 and the
   rule values on slide 8 and A5.
6. **Robot.** Regenerate `space_ui.h` into the `feat/s3-mind-chat`
   worktree, then build and flash over USB. Only flash that branch, never a
   main-based build. Check `saved=1` afterwards.
7. **Behaviour change.** `tools/sesame_mind.py` runs every designed frame
   through `project()` and puts `describe()` in the designer prompt. The
   recomputed space changes what the real robot does. Say so in the commit
   and the handoff.

## Working-tree cautions (2026-11-27)

- Another session left uncommitted bambu changes:
  - `params-v3headarms.json`: rim band t 2.6 → 4.0 mm, `z_top` 56;
  - the v3headarms STL, STEP and 3MF files;
  - the previews;
  - `build/v3headarms/report.json`, regenerated 19:42 on 2026-11-26.
- The masses above come from that working tree: dome 109.0 g. Record which
  bambu revision any derived body file came from, and do not commit
  another session's bambu changes.
- `tools/sesame_mind.py` and `tests/test_sesame_mind.py` also have
  uncommitted changes from other work.
