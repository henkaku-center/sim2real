# sim2real

Portable simulation and sim-to-real platform for the **Sesame** quadruped robot (8× MG90S servos, LOLIN ESP32-S2 Mini), built for the ChibaTech School of Design & Science course APS-II.

The project owns the **robot definition, safety contract, task API, evaluation tests, browser experience, and backend adapters** while building on replaceable open-source engines — primarily **MuJoCo** as the cross-platform reference simulator.

## Status

**Stage 0 complete.** The canonical manifest (`manifest/robot.yaml`), a manifest-generated MJCF, native viewer/benchmark, and a browser WASM shell all run from the same model, with native↔browser numerical parity CDP-tested on macOS + Linux in CI. Geometry is placeholder pending measured dimensions. Next: Stage 1 (stock motion playback, SafeAction command vocabulary) — see [ROADMAP.md](ROADMAP.md).

### Quick start

```bash
uv sync                      # Python env (locked)
uv run pytest                # full test suite
uv run python sim/view.py    # native viewer (macOS: uv run mjpython sim/view.py)
uv run python sim/bench.py   # physics step-rate benchmark
cd web && npm ci && npm run dev   # browser sim at http://localhost:5173
```

## Documents

| File | Purpose |
|------|---------|
| [HANDOVER.md](HANDOVER.md) | Entry point for the agent/developer taking over — known facts, first tasks, exit criteria |
| [ROADMAP.md](ROADMAP.md) | Full research review and staged roadmap (stress-tested against literature, 2026-07) |
| [AGENTS.md](AGENTS.md) | Conventions and guardrails for AI coding agents working in this repo (vendor-neutral) |
| [DECISIONS.md](DECISIONS.md) | Append-only log of resolved questions and their rationale |
| [reference/PRIOR-ART-SIM.md](reference/PRIOR-ART-SIM.md) | Full review of the community browser simulator (copied from the course repo) |

## Core principles

- **macOS + Linux first.** Every student-facing tool must `pip install` / `npm install` cleanly on both. GPU-accelerated training (MJX/Warp, CUDA) is a Linux-workstation activity; development and evaluation run anywhere on CPU MuJoCo.
- **AI-agent-friendly.** Deterministic CPU physics, headless test loops, numerical assertions, CDP-scripted browser checks. No GUI-only workflows on the critical path.
- **CV-legible frameworks.** MuJoCo, Gymnasium, Stable-Baselines3, LeRobot — tools students can name in interviews. Pure-web simulation is a stretch achievement, never a milestone.
- **Adapters around an owned contract.** No engine (MuJoCo, Genesis, Isaac, Newton) or format (MJCF, URDF, USD) is the canonical representation. The APS-owned robot manifest and interfaces are.

## Planned layout

```
manifest/robot.yaml     # APS-owned contract: joints, pins, limits, calibration (frozen first)
models/sesame.xml       # MJCF, visual + collision geometry separated
assets/                 # GLB exports, .blend sources
sim/                    # Python: mujoco native, Gymnasium env, later MJX
web/                    # Vite + TS + @mujoco/mujoco + PlayCanvas
firmware-tests/         # Wokwi project for the S2 Mini command parser
tests/                  # CDP smoke tests + cross-backend pose assertions
```

## Related repositories

- **Upstream robot (canonical hardware source):** <https://github.com/dorianborian/sesame-robot> — Apache-2.0; STLs, BOM, wiring guide, firmware, Sesame Studio
- Course site & teaching materials: `henkaku-center/aps` (hardware decisions log, inventory, course context)
- Prior-art community simulator: <https://github.com/one-for-all/sesame-robot-sim> (reviewed; not reproducible from public sources — see [reference/PRIOR-ART-SIM.md](reference/PRIOR-ART-SIM.md))
