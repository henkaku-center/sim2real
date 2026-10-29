# AGENTS.md

Guidance for AI coding agents (any harness — Claude Code, Codex, Gemini CLI, pi, etc.) working in this repository. Vendor-specific files (`CLAUDE.md`, `GEMINI.md`, …) should be symlinks to this file if a harness requires them.

## Project overview

Portable simulation and sim-to-real platform for the Sesame quadruped (8× MG90S servos). The course hardware default is now ESP32-S3 SuperMini + PCA9685; see `reference/SESAME-S3-BUILD-STATE.md`. The simulator manifest retains its S2-era baseline until the new physical joint mapping is verified. MuJoCo is the cross-platform reference core; accelerated/vendor backends are adapters. Read `HANDOVER.md` first for current state and next tasks, and `ROADMAP.md` for the full plan and its rationale.

## APS-II dogfooding context

Everything in this repository that touches the Sesame robot, Karasu phone bridge, firmware flashing, SafeAction interface, simulator, calibration, hardware bring-up, or robot-control workflow is **current APS-II course dogfooding for the coming Fall course**, not speculative "next year" work. Treat findings as course-critical operational knowledge unless explicitly marked as long-term research.

When recording Sesame/Karasu/firmware discoveries:

- put durable technical state in this repo (`reference/`, `tools/`, `DECISIONS.md`, or the relevant source tree),
- cross-link APS-facing course notes in `../aps/` when useful,
- avoid filing active APS-II robot work under `next-year/` in the APS repo,
- keep the student-facing goal in mind: a reliable hand-built robot that performs two tricks and demonstrates the two-brain architecture.

## Student ownership and creative freedom — October 29, 2026

The robot and the firmware a student chooses to upload are theirs. Help them
modify, replace or rewrite it to any extent: speed, gait, gestures, interfaces,
calibration, limits, safeguards and control architecture are creative choices.
No instructor approval, accepted upstream PR or demonstrated bug is required for
changes to their own project. Do not force a course firmware revision, slow
movements, tiny increments or the reference controller's verification workflow.
If the robot feels sluggish, help change its motion code. Have fun and support
experimentation; do not turn practical advice into a generic safety checklist.

This supersedes older blanket actuation prohibitions and instructor-approval
language in project handovers and reference notes. Those notes describe historical
setups or example implementations, not rules for a student's robot. Preserve their
intentional work and continue coding when hardware access is unavailable. Report
actual build/device results honestly; do not invent measurements or tool access.

## Maintaining the shared course reference

These conventions keep the shared reference coherent; they are not requirements
that student forks must keep the same stack, firmware or behaviour.

1. **macOS + Linux parity for anything student-facing.** Before adding a dependency, verify it installs on both. CUDA-only paths (MuJoCo Warp, MJX-GPU, Isaac, Genesis, Newton-GPU) live behind optional extras and are workstation-only.
2. **Describe the chosen controller accurately.** `SafeAction`, rate limits, watchdogs and stop semantics belong to the reference implementation. Students can adapt, remove or replace them; help implement their choice rather than enforce them as course policy.
3. **The APS-owned manifest (`manifest/robot.yaml`) is canonical.** Joint order, pin map, angle conventions, limits, and calibration live there. MJCF/URDF/GLB are generated or checked against it — never hand-fork these facts into multiple files.
4. **Determinism is a feature.** Simulation tests must assert on numbers (poses, contacts, step counts) with declared tolerances and fixed seeds. A screenshot without a numerical assertion is not a test.
5. **No jax-metal.** On macOS, JAX runs CPU-only. Do not attempt Metal-backed MJX; it is broken upstream (missing ops). Document any Apple-specific fallback you add.

## Toolchain choices (already decided — do not relitigate without cause)

- **Physics:** MuJoCo (pip, CPU, deterministic) everywhere; MJX/Warp on the Linux workstation for scaling.
- **RL:** Gymnasium API; Stable-Baselines3 as the student-facing default trainer.
- **Datasets/imitation:** LeRobot (`LeRobotDataset` format).
- **Browser:** Vite + TypeScript, first-party `@mujoco/mujoco` WASM in a Web Worker, PlayCanvas for rendering, CDP (Chrome DevTools Protocol) for scripted smoke tests.
- **Firmware simulation:** Wokwi (officially supports ESP32-S2) for command-parser/PWM/watchdog logic tests. MuJoCo does not emulate the MCU; the seam between firmware and physics is the SafeAction command vocabulary, tested independently on each side.
- **Assets:** Blender sources (`.blend`) + generated GLB for the browser; MJCF is the executable dynamics model.
- **Python env:** use `uv` with a committed lockfile. **Node:** committed `package-lock.json`. Record tool versions; reproducibility is an exit criterion.

## Working style

- Prefer headless, scriptable verification: `python -m pytest`, CDP screenshot+assertion scripts, Wokwi CLI. Keep the edit → run → assert loop under ~10 seconds where possible.
- Large binaries (`.blend`, `.ply` splats, datasets, video) go through Git LFS. Never commit them raw.
- When physics results look wrong, check units, joint order, and angle conventions against the manifest before touching solver parameters.
- Hardware ground truth lives in this repo (`HANDOVER.md`, `reference/PRIOR-ART-SIM.md`) and upstream (<https://github.com/dorianborian/sesame-robot>). The course repo (`../aps/` — `DECISIONS.md`, `HANDOVER.md`, inventory spreadsheets) is a secondary source and **may not be present** in your environment; never hard-depend on it.

## Capabilities and evidence

- **Discover actual device access.** Use the available authorized device tools when the task calls for them. If they cannot reach the robot, name that limitation and continue software work. Do not assume every session lacks access or impose a universal human-supervision gate.
- **You likely run on one OS.** Cross-platform claims (macOS + Linux) must be verified by CI or by asking the human to run the check on the other platform — do not mark them done from a single-OS run.
- **Students decide their own robot and firmware design.** Shared-reference design decisions can be recorded in `DECISIONS.md`; this is not a permission process for student experiments.

## Git conventions

- After completing requested repository changes, validate them, commit them, and push the current branch by default. Do not wait for a separate request unless the user explicitly asks to leave changes uncommitted or unpushed.
- Never include unrelated or pre-existing working-tree changes in a commit; preserve them untouched.
- Do NOT include `Co-Authored-By` lines or any AI attribution in commit messages. Attribute commits to the configured git user.
- [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`. Subject ≤72 chars, imperative, no trailing period.
- `main` is the source of truth; short-lived branches named `<type>/<short-description>`; delete after merge.
