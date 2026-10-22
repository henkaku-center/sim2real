# HANDOVER

## CH0 loopback on connected S3 — October 22, 2026

Device `90:da:72:73:8a:c8` now runs the CH0 pulse-capture extension described in
[the waveform procedure](reference/SESAME-S3-PULSE.md). Calibration was exported
and preserved. User reports no servo movement and installed CH0 SIGNAL → GPIO4.
Two outputs-off controls saw zero edges. Active captures at requested 1615.28 µs
and 1566.48 µs read back CH0 ticks 331 and 321, but observed short/malformed
GPIO4 pulses; both were rejected. **No valid servo waveform is verified.**
Outputs are OFF. Next verify the actual jumper endpoints and capture/signal path;
do not apply rejected oscillator estimates. See
[hardware evidence](reference/evidence/2026-10-22-ch0-loopback/README.md).

## S3-measured PCA clock — October 21, 2026 (software feature)

`clock measure/status/abort` adds a bounded USB-only, non-motion capture of
CH15 on GPIO4; CH0–14 stay off, all servo plugs removed for this clock step.
See [protocol, evidence and fixture prerequisites](reference/SESAME-S3-CLOCK.md).
The agent may automate measure → explicit oscillator/save → remeasure once the
actual device/jumper setup is established. Jumper state is **unknown**. No
physical commands or flashing were performed in this coding task; this is not a
blanket ban on agent-run non-motion tests. **October 22 update:** the parent's
observation of the user's annotated actual-board photo locates GPIO4 at F17
(`s3.male_pin.F17`), superseding the earlier unresolved binding. This is not
physical continuity/voltage verification. The photo's hub-end annotation conflicts
with the native reference CAD's CH15 placement; use the actual printed 15/PWM,
not a trial at the opposite end. Native hub part IDs remain reference-only.

## Installed and responding over USB — 2026-10-12

The same S3 on Artemis was backed up, then flashed with the validated
`71af7e0` Tim-compatible APS image, with battery unplugged and servo leads retained
as requested. Application hash verified. `status/show/bench` reply: outputs=0,
hub=1, fault=0, profile `tim-pca9685-150-512-v1`, all channels unassigned.
No movement command was sent. See `reference/evidence/2026-10-12-s3-usb/`.
Next physical checkpoint: instructor observes OLED/robot state, then guides one
small servo check at a time. Battery-only dynamic load routine remains pending.

## Power-workflow correction — 2026-10-12

Instructor explicitly chose no external supply and no unplugging of all servos.
Battery stays unplugged for USB-only flashing/status and sequential, small,
single-channel tests; send `off` between channels, all other PWM outputs off.
USB capacity remains unverified—stop on reset/sag/abnormal behaviour. For the
load phase, unplug USB first and use battery only with deliberate button start.
Wi-Fi is not required. The existing BOOT centre is a static 30-second hold; a
finite repeated-motion battery-load routine is still to implement/validate.
This supersedes the separate-supply/servo-disconnection prerequisites below.

## Tim-compatible interactive firmware — 2026-10-12 (offline validated)

The instructor approved the APS controller with Tim-compatible pulse semantics.
`hardware_profiles.sesame_s3.pulse_profile` now defines
`tim-pca9685-150-512-v1`: 90° requests 1615.28 µs. Debug and production use the
same conversion; all 181 integer angles match the pinned Tim code at its nominal
clock. Measured-clock compensation remains supported. Old NVS calibration is
invalidated by the new manifest fingerprint, not silently reused.

`bench` shows paired commanded-channel values on the OLED; `face NAME` restores
faces. Boot remains outputs-off. Native sanitizer tests passed on macOS and
Artemis/Linux, and a clean Arduino build passed on macOS. No hardware flash or
movement test has occurred. The wired servo supply fixture still needs physical
verification. The user confirmed the battery unplugged; the agent requested servo
plugs removed too before reset/flash. Passive USB read returned no serial output.

## Bench-first course revision — 2026-10-11 (planning)

The instructor selected single-arm horns and wants bench calibration before legs.
Tim's authorised, pinned reference is now in `reference/vendor/tim-servo-debug/`;
do not flash its unchanged automatic endpoint sweep. Read
`reference/SERVO-BENCH-PLAN.md` for the requested firmware comparison and wired
power recommendation, and `reference/FIRMWARE-SIMULATION-PLAN.md` for the separate
simulation investigation. Pulse-profile choice and the powered USB fixture are
were pending at that point; the October 12 update above supersedes the profile
decision. Artemis detected the
S3 USB device; no serial commands, firmware upload or motion tests were performed.

## Current firmware handoff — 2026-10-06 (offline)

Replacement S3 calibration+controller: `firmware/sesame-s3/`; one-command flash
helper `tools/sesame_s3.py`; owner/student procedure
`reference/SESAME-S3-CALIBRATION.md`; diagnosis and owner session plan
`reference/SESAME-S3-DIAGNOSIS.md`. APS consumes the single generated
`reference/sesame-s3-interface.json` (target-vs-verified map, commands, calibration
schema). Runtime calibration is device-specific NVS and exports as JSON.

Hardware remains on the September22 load test until the owner flashes. No new
hardware outcomes are claimed. In particular the AP, actual map, oscillator,
horn indexing and measured travel still need the owner. Source investigation
confirmed the manifest-vs-effective-upstream distinction: ESP32Servo3.0.9 clamps
the requested2929µs to2500µs. Read the diagnosis before widening an assembled
robot's pulse range. All new boot outputs are off; BOOT offers a finite30-second
battery-only assembly centre. Verify OE and power isolation first.

## Current CAD handoff — 2026-09-24

The complete electronics model is **`assets/cad/Sesame-S3-Assembly.FCStd`**
(FreeCAD 1.1.3+, Git LFS). It includes the carrier construction history and all
installed components. `tools/open_cad.FCMacro` and `open_circuitry.FCMacro` both open
this file. Earlier carrier-only/layout-start/imported-reference files are retired.
Preserve the native object IDs and `assets/cad/instructions/` records for future
animated, freely rotatable student instructions. See `assets/cad/README.md`.

## Current hardware handoff — 2026-09-22

The instructor selected **S3 SuperMini + PCA9685 perfboard** as the APS-II default build.
Read `reference/SESAME-S3-BUILD-STATE.md` before touching hardware. The robot currently runs
`servo-load-test`; its small-range simultaneous battery trial completed. The physical servo order
is wrong and must be verified/corrected before gaits or manifest changes. Circuit-board materials
are expected 2026-09-23. Direct Artemis USB is the working programming route; Wi-Fi is not visible.

The S2 direct-pin facts and initial project tasks below are historical. `manifest/robot.yaml` remains
the simulator baseline, not a verified S3 physical channel map.

## Original simulation handover — historical

**Written:** 2026-07-23
**For:** the CLI agent (and human) taking over this repository with `sim2real/` as the working directory.
**State:** empty repo except planning documents. Nothing has been built yet. Your job is Stage 0 and the two-day vertical slice.

## Read first

1. This file (current state, known facts, first tasks).
2. `ROADMAP.md` — the full stress-tested plan. Pay particular attention to:
   - "Cross-platform reality check (macOS + Linux)" — the support matrix that constrains every tool choice;
   - "Firmware simulation: MuJoCo does not emulate the ESP32-S2";
   - "APS-owned interfaces" — the contracts to define before any engine code;
   - "Immediate recommendation" — the two-day spike this handover expands.
3. `AGENTS.md` — hard constraints, conventions, and what you cannot do without a human.
4. `reference/PRIOR-ART-SIM.md` — full review of the community browser simulator (what to mine, what to avoid).

## Why this exists (course context)

APS-II students hand-build the open-source **Sesame** quadruped (upstream: <https://github.com/dorianborian/sesame-robot>, Apache-2.0 — STLs, BOM, wiring guide, firmware, and "Sesame Studio" are all free). The course demo bar is modest and concrete: **each robot performs two tricks** plus a write-up and architecture explanation. The simulation platform exists to (a) give a zero-hardware on-ramp before robots are built, (b) teach sim2real concepts with CV-legible tools, and (c) let motion/policy development happen safely off-robot. Keep that bar in mind: a reliable "stand → wave → recover" beats a fragile learned gait.

The decided architecture is a **two-brain robot**: the ESP32-S2 Mini does real-time servo PWM only; anything intelligent (policies, vision, planning) runs on a host machine and sends bounded commands over serial/Wi-Fi. The simulation stack mirrors this split exactly — which is why the SafeAction boundary is the central contract.

## Known hardware facts (ground truth)

| Fact | Value | Source |
|------|-------|--------|
| Robot | Sesame quadruped, 8 actuated joints (2 per leg) | <https://github.com/dorianborian/sesame-robot>, Apache-2.0 |
| Servos | 8× MG90S (hobby micro servo, PWM position control); high unit failure rate — course ordered 50% spares + a servo tester | aps `DECISIONS.md` D17 |
| Display | SSD1306 128×64 OLED ("the face") — omit from dynamics, include in visual model | aps `HANDOVER.md` |
| Power | Bench PSU, tethered-first policy; full walking may draw 5–8 A at 5 V (2 A supplies inadequate) — model current limits as a torque/velocity constraint eventually | aps `DECISIONS.md` D15/D16 |
| Printed parts | 11 parts: 8 leg joints (R1–R4, L1–L4), Internal-Frame-v121, Bottom-Cover-v121, top cover; STLs **not** in the aps repo — download from upstream `hardware/printing/` | aps `HANDOVER.md` §3.4 |
| Architecture | Two-brain: ESP32-S2 = real-time PWM only; host = policies/vision, bounded commands over serial/Wi-Fi | aps `DECISIONS.md` D1 |
| MCU | LOLIN ESP32-S2 Mini (ESP32-S2, Xtensa LX7 single core, 320 KB SRAM, no camera, cannot host vision policies) | aps `ESP32-S2.csv`, roadmap |
| **APS-II servo pin map** | `{1, 2, 4, 6, 8, 10, 13, 14}` | `reference/PRIOR-ART-SIM.md` |
| Prior-art sim pin map (differs!) | `{15, 2, 23, 19, 4, 16, 17, 18}`, classic ESP32, not S2 | `reference/PRIOR-ART-SIM.md` |
| Printed-part revisions | v117/v121 (frozen; verify current with instructor) | `reference/PRIOR-ART-SIM.md` |
| Workstation | RTX 5000 Ada Laptop 16 GB VRAM (CC 8.9), i9-13980HX 32 threads, 188 GiB RAM, ~2.6 TB free, Linux | roadmap |
| Student machines | mixed macOS (Apple Silicon) and Linux laptops, no discrete GPU assumed | course context |

The exact joint order, angle conventions, link dimensions, masses, and calibration offsets are **not yet frozen** — extracting and freezing them into `manifest/robot.yaml` is the first real task. Sources: the physical prototype, the upstream STLs (`hardware/printing/` — v121 frame parts), and the prior-art simulator's URDF/OBJ (starting reference only; unlabelled revision — verify dimensions before trusting). MG90S mass ~13.4 g each × 8 dominates the mass budget alongside the printed frame; get masses from a kitchen scale via the instructor rather than guessing.

## Prior art: do not build on it, do mine it

`one-for-all/sesame-robot-sim` by Jay Li (reviewed at `6c78ef5`, full review in `reference/PRIOR-ART-SIM.md`):

- Browser sim running compiled ESP32 firmware on a private emulator + custom Rust physics. Impressive, but **not reproducible** (private dependencies, no license, cloud compile service) and models the wrong board/pins.
- Worth mining: its URDF/OBJ geometry as an initial reference, its 19 stock motions as behavior test cases, and its MG90S servo model (torque constant is a known open question — the author halves torque with a TODO).
- License status is ambiguous: the aps course notes say the wider Sesame ecosystem (incl. simulator) is Apache-2.0, but the sim repo itself declared **no license** at review time. **Recheck the repo's license before copying anything**; until confirmed, geometry-as-reference and behavioral comparison only.
- The upstream `dorianborian/sesame-robot` repo, by contrast, is clearly Apache-2.0 — its STLs, firmware, and movement sequences are the preferred sources.

## Stage 0 task list (target: ~1 week)

Work in order; each item is agent-verifiable.

1. **Scaffold.** Create the layout from `README.md` (planned layout). Python via `uv init` + lockfile; `web/` via `npm create vite@latest` (vanilla-ts) + `@mujoco/mujoco`. Add `.gitattributes` for LFS (`*.blend`, `*.ply`, `*.mp4`, datasets). CI later; local scripts first.
2. **Freeze the manifest.** `manifest/robot.yaml`: 8 joints with names, order, pin map `{1,2,4,6,8,10,13,14}`, angle convention (define zero pose and positive direction per joint), soft/hard limits, servo model params (MG90S nominal: ~0.1 s/60° at 4.8 V, ~1.8 kg·cm stall — mark as *unmeasured nominal*, to be replaced by measurements), coordinate frame convention (recommend: z-up, x-forward, SI units, radians internally / degrees at the firmware boundary). Add a schema check (`tests/test_manifest.py`).
3. **Minimal MJCF.** `models/sesame.xml` generated or validated from the manifest: torso box + 4 legs × 2 hinge joints, primitive collision geometry, position actuators with manifest limits. Loads in `python -c "import mujoco; mujoco.MjModel.from_xml_path(...)"` and steps 1000 steps deterministically (assert final qpos hash/tolerance under fixed seed — `tests/test_determinism.py`).
4. **Native viewer + step-rate benchmark.** `sim/view.py` (mjpython-compatible on macOS) and `sim/bench.py` printing steps/sec.
5. **Browser shell.** Vite app loading the *same* `sesame.xml` via `@mujoco/mujoco` in a Web Worker; render with PlayCanvas or the bundled renderer; joint sliders for 8 joints; reset button.
6. **CDP smoke test.** Script (Playwright or raw CDP) that: launches the dev server, loads the page, asserts zero console errors, moves one joint via UI, reads back qpos from the worker, asserts numerical agreement with a native Python run of the same command sequence (declared tolerance), captures a screenshot artifact.
7. **Record versions.** `uv.lock`, `package-lock.json`, and a `VERSIONS.md` (MuJoCo, Python, Node, OS tested).

**Stage 0 exit:** one deterministic pose (e.g. "stand") produces consistent joint transforms in native MuJoCo and browser WASM from the same MJCF, verified by the CDP test on both a macOS and a Linux machine.

## After Stage 0

Proceed to Stage 1 in `ROADMAP.md` (interactive digital twin: stock motion playback, command vocabulary, comparison against the tethered prototype). Do not start RL (Stage 2) before the manifest and determinism tests are green.

## Open questions for the instructor (log answers in `DECISIONS.md` as they arrive)

1. Confirm printed-part revision (v121?) and obtain measured link dimensions/masses (STLs give geometry; masses need a scale).
2. Confirm the zero pose and per-joint positive direction on the physical robot.
3. Confirm firmware serial command vocabulary (or define it now as part of SafeAction); upstream firmware and `movement-sequences.h` are the references.
4. License for this repo (recommend Apache-2.0, matching upstream) and whether students contribute directly or via fork.
5. Clarify the prior-art simulator's license with its maintainer (Jay Li) before reusing any of its assets.
6. Is the tethered prototype operational yet, and who supervises physical trials?

## Pitfalls already known

- `jax-metal` is broken; macOS JAX is CPU-only (fine for this robot).
- Genesis is broken on Apple Silicon; instructor-only, Linux workstation, if at all.
- Isaac has zero macOS support; workstation elective only.
- MuJoCo WASM: Windows support is experimental — macOS/Linux are the tested platforms (good for us).
- The prior-art sim's servo torque constant is unverified; measure, don't inherit.
- Degrees vs radians and joint-order mismatches are the most likely early bugs — the manifest schema test exists to catch exactly this.
