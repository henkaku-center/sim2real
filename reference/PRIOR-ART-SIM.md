# Sesame Browser Simulator Findings

**Reviewed:** 2026-07-23
**Upstream:** <https://github.com/one-for-all/sesame-robot-sim> at `6c78ef5`
**Hosted application:** <https://sesame-sim.aperobotics.io/>
**Status:** promising teaching and motion-development tool; not yet a reproducible local dependency or exact digital twin of the APS-II prototype

## What it is

The simulator is more substantial than a pose visualizer. It runs a compiled ESP32 firmware image against an ESP32 emulator, converts the emulated PWM outputs into MG90S servo behavior, and drives a contact-enabled rigid-body model of Sesame. Its browser interface includes a Monaco code editor, project files, remote Arduino compilation, serial input/output, stock motion buttons, and a Three.js view.

Main stack:

- Rust 2024 compiled to WebAssembly;
- the author's `gorilla-physics` Rust rigid-body engine;
- a non-public/local-path `esp32rs` ESP32 emulator and MG90S model;
- URDF plus OBJ meshes for robot geometry;
- TypeScript, Three.js, Monaco Editor, and shared `chimpanzee-ui` components;
- Rspack and `wasm-pack` for the web build;
- Arduino CLI for firmware builds; and
- a Google Cloud Run compile service used by the browser editor.

The repository is active but small: 65 commits from one contributor between March and July 2026, with no releases, issues, or pull requests at review time.

## Local-use result

Cloning the repository is worthwhile for inspection and preservation. The checked-in `docs/` build can be served locally with a static HTTP server and successfully loads the robot, editor, serial UI, and 19 motion buttons. On the review machine it ran at about 0.29 real-time speed, so classroom-machine performance must be measured rather than assumed.

A complete source build is **not reproducible from the public repository alone**:

- Rust dependency `../esp32rs/` is not public or included;
- JavaScript dependency `../../chimpanzee-ui` is not public or included;
- public `gorilla-physics` is expected as an unpinned sibling checkout;
- no setup README, submodules, container, CI workflow, or tool-version manifest is provided;
- the compile service source is not linked; and
- neither the simulator nor `gorilla-physics` declares a software license.

The checked-in static build is only partly offline. Simulation and the bundled default firmware work locally, but compiling edited code sends the sketch and header ZIP to the maintainer's Cloud Run service. That service permits the production web origin but rejected the local test origin through CORS. Student code therefore leaves the browser when Compile is pressed, and local development needs either an allowed origin, a proxy, or a self-hosted compiler.

## Fidelity limits relevant to APS-II

The current simulator is not configured for the hand-wired LOLIN S2 Mini baseline:

- its firmware and emulator use the distro-board pins `{15, 2, 23, 19, 4, 16, 17, 18}`;
- the APS-II S2 baseline uses `{1, 2, 4, 6, 8, 10, 13, 14}`;
- `build-sesame.sh` targets generic classic ESP32 firmware, not ESP32-S2;
- the simulator firmware omits the stock OLED and Wi-Fi paths;
- its own README marks OLED and Wi-Fi unsupported;
- servo torque is deliberately multiplied by `0.5` with a TODO questioning the torque constant; and
- the URDF/mesh files are not labelled with the frozen v117/v121 printed-part revisions.

Movement sequences currently match the simulator's bundled firmware model, but a successful simulation does not prove S2 compilation, physical pin mapping, power integrity, enclosure fit, calibration, collision clearance, or safe real-servo limits.

## Recommendation

Use the hosted simulator now as a **simulator-first motion sandbox**, especially for reading movement sequences, using serial commands, and observing stock motions. Do not copy its complete firmware directly to the APS-II S2 prototype or make it an offline classroom prerequisite yet.

Before investing in a fork, contact the maintainer and ask for:

1. an explicit open-source license;
2. public or replaceable `esp32rs` and `chimpanzee-ui` dependencies;
3. the compile-service source or a documented local compiler path;
4. accepted contribution workflow and preferred issue list; and
5. confirmation of the modeled Sesame mechanical and controller revisions.

## Useful improvement candidates

Good first upstream contributions, after licensing and build access are resolved:

1. Root README with architecture, prerequisites, exact versions, and one-command local startup.
2. Pin/controller profiles for hand-wired S2 Mini versus distro-board hardware, with a visible active-profile warning.
3. Export of `movement-sequences.h` independently from the emulator-specific firmware.
4. Local persistence, import/export, and recovery of edited projects.
5. Joint-limit and body-collision warnings before a motion is exported.
6. Calibration/subtrim import and a side-by-side commanded-versus-simulated angle plot.
7. Reproducible compiler container or documented local Arduino CLI service.
8. Automated smoke tests for boot, serial commands, all eight PWM channels, and stock motions.
9. A lightweight lesson mode that hides infrastructure code and exposes only poses/sequences.
10. Optional run metrics such as falls, travel distance, peak joint speed/torque proxy, and real-time ratio.

Avoid beginning with reinforcement learning, Wi-Fi emulation, or a major physics rewrite. The highest-value work for APS-II is reproducibility, S2/profile clarity, safe motion authoring, and reliable export to the physical build.

## Evaluation gate

Before adopting it formally in the course:

- run the hosted version on each expected student machine/browser;
- complete a small pose edit and serial-command exercise;
- verify exported movement data against the pinned physical firmware;
- compare at least rest, stand, wave, and walk against the tethered prototype;
- document mismatches in angle, timing, collision, and stability; and
- decide whether hosted/cloud compilation and its data handling are acceptable for student work.
