# AGENTS.md

Guidance for AI coding agents (any harness — Claude Code, Codex, Gemini CLI, pi, etc.) working in this repository. Vendor-specific files (`CLAUDE.md`, `GEMINI.md`, …) should be symlinks to this file if a harness requires them.

## Project overview

Portable simulation and sim-to-real platform for the Sesame quadruped (8× MG90S servos, LOLIN ESP32-S2 Mini). MuJoCo is the cross-platform reference core; accelerated/vendor backends are adapters. Read `HANDOVER.md` first for current state and next tasks, and `ROADMAP.md` for the full plan and its rationale.

## APS-II dogfooding context

Everything in this repository that touches the Sesame robot, Karasu phone bridge, firmware flashing, SafeAction interface, simulator, calibration, hardware bring-up, or robot-control workflow is **current APS-II course dogfooding for the coming Fall course**, not speculative "next year" work. Treat findings as course-critical operational knowledge unless explicitly marked as long-term research.

When recording Sesame/Karasu/firmware discoveries:

- put durable technical state in this repo (`reference/`, `tools/`, `DECISIONS.md`, or the relevant source tree),
- cross-link APS-facing course notes in `../aps/` when useful,
- avoid filing active APS-II robot work under `next-year/` in the APS repo,
- keep the student-facing goal in mind: a reliable hand-built robot that performs two tricks and demonstrates the two-brain architecture.

## Hard constraints (do not violate)

1. **macOS + Linux parity for anything student-facing.** Before adding a dependency, verify it installs on both. CUDA-only paths (MuJoCo Warp, MJX-GPU, Isaac, Genesis, Newton-GPU) live behind optional extras and are workstation-only.
2. **Never give a policy or script unrestricted raw servo authority on the physical robot.** All real-world actuation goes through the bounded `SafeAction` layer (rate-limited pose targets/deltas, watchdog, stop semantics). This applies to test code too.
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

## What you cannot do (and who can)

- **You have no access to the physical robot.** All physical trials are human-supervised; your deliverable is the bounded command sequence + expected telemetry, never direct actuation. Flag `NEEDS-HARDWARE` in PRs/notes where a physical measurement is required.
- **You likely run on one OS.** Cross-platform claims (macOS + Linux) must be verified by CI or by asking the human to run the check on the other platform — do not mark them done from a single-OS run.
- **Decision authority** for hardware revisions, license, safety limits, and course scheduling rests with the instructor. Record every resolved question in `DECISIONS.md` with date and rationale; treat that file as append-only.

## Git conventions

- Do NOT include `Co-Authored-By` lines or any AI attribution in commit messages. Attribute commits to the configured git user.
- [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`. Subject ≤72 chars, imperative, no trailing period.
- `main` is the source of truth; short-lived branches named `<type>/<short-description>`; delete after merge.
