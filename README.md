# sim2real

Design-to-fabrication sim-to-real work for ChibaTech APS-II, using **Sesame** as
the reference robot. The current scope and instructor intent live in
[Project goal](AGENTS.md#project-goal), not in a fixed hardware/task checklist.

The project owns the **robot definition, safety contract, task API, evaluation tests, browser experience, and backend adapters** while building on replaceable open-source engines — primarily **MuJoCo** as the cross-platform reference simulator.

## Status

Run `uv run python tools/check_design.py` for the current checked dependencies
and the two-eye mutation trace. A successful geometry/export check is not
end-to-end simulation, firmware or physical acceptance. [ROADMAP.md](ROADMAP.md)
retains the earlier research history; it is not a live completion dashboard.

### Quick start

```bash
uv sync                      # Python env (locked)
uv run pytest                # full test suite
uv run python sim/view.py    # native viewer (macOS: uv run mjpython sim/view.py)
uv run python sim/bench.py   # physics step-rate benchmark
uv run python -m sim.twin --check   # generated twins and dynamics records are current
cd web && npm ci && npm run dev   # browser sim at http://localhost:5173
```

## Documents

### Electronics CAD

Open **[`assets/cad/Sesame-S3-Assembly.FCStd`](assets/cad/Sesame-S3-Assembly.FCStd)**
with FreeCAD 1.1.3 or newer, after `git lfs pull`. This is the complete electronics
assembly, including its editable carrier. `tools/open_cad.FCMacro` opens the same
file. See [CAD workflow](assets/cad/README.md) and
[animated-instruction records](assets/cad/instructions/README.md).

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
- **Replaceable tools.** MuJoCo, Gymnasium, Stable-Baselines3 and LeRobot are reference choices, not boundaries on the designs or workflows students can explore.
- **Adapters around an owned contract.** No engine (MuJoCo, Genesis, Isaac, Newton) or format (MJCF, URDF, USD) is the canonical representation. The APS-owned robot manifest and interfaces are.

## Planned layout

```
manifest/robot.yaml     # APS-owned contract: joints, pins, limits, calibration (frozen first)
manifest/twin.yaml      # twin inputs: default hardware and design, mass table, nominal actuator/contact values
models/<design>.xml     # generated MJCF per printing design; default internal-frame-s3 (sim/twin.py)
assets/printing/<design>/dynamics.json   # the same twin as a typed record for consumers without MuJoCo
models/sesame.xml       # upstream narrow-body baseline, named upstream-v117; the browser still loads this one
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

## License

Apache-2.0 — see [LICENSE](LICENSE). Third-party assets keep their own notices in
`assets/cad/licenses/`, `assets/cad/upstream/` and `assets/cad/fonts/`.
