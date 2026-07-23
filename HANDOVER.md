# HANDOVER

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
