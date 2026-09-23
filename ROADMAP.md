# APS-II Portable Robot Simulation Research and Roadmap

**Reviewed:** 2026-07-23 (cross-platform stress test applied — see "Cross-platform reality check")
**Status:** feasible as a staged research/teaching platform; infeasible if framed as writing and owning every engine

**Priorities (confirmed):** macOS + Linux compatibility for students, AI-agent-friendly toolchains, fast iteration, and CV-legible industry frameworks. A pure web-based stack is a long-term stretch achievement, not a milestone — it must never block educational outcomes or displace well-known sim2real tooling from student CVs.

## Recorded follow-up: interactive build instructions (2026-09-24)

Instructor-requested future work: stepwise assembly animations that students can
pause, rotate and inspect from different angles. **Implementation deferred.**
Capture ordered construction operations and semantic/native part bindings during
current CAD co-design; retain intermediate-state gaps and measurement evidence.
The converter pilot record is in [assets/cad/instructions/](assets/cad/instructions/README.md).
See decision D6. This is a later presentation layer over the as-built records,
not a new prerequisite for circuitry validation or enclosure redesign.

## Executive assessment

The realistic goal is to own the **robot definition, data, safety contract, task API, evaluation tests, browser experience, and backend adapters** while building on replaceable open-source engines. That gives APS-II meaningful control and portability without spending the course writing collision detection, GPU kernels, renderers, and training infrastructure.

A strong route is:

- **MuJoCo as the portable reference simulator** — the only physics core in this plan that is first-class on both macOS and Linux;
- **MuJoCo MJX or MuJoCo Warp for accelerated RL experiments on the Linux/NVIDIA workstation only** — all accelerated paths (MJX-GPU, Warp, Genesis, Isaac, Newton-GPU) are effectively NVIDIA/Linux paths today; the portable path is CPU MuJoCo everywhere plus accelerated backends on the workstation;
- **Isaac Sim/Isaac Lab as an optional NVIDIA high-fidelity and synthetic-data backend**;
- **Blender as the human-facing source for visual and collision assets**;
- **glTF/GLB for browser delivery, MJCF/URDF for robot dynamics, and OpenUSD for interchange with Omniverse**;
- **a Vite/TypeScript browser workbench using PlayCanvas/WebGPU**, with MuJoCo WASM or a WebSocket-connected native backend;
- **LeRobotDataset as the long-term real/sim episode format**; and
- **gsplat plus SuperSplat for reconstruction and browser-side Gaussian-splat work**.

Do not make Omniverse, CUDA, WebGPU, USD, or any one physics engine the canonical representation. Make each an adapter around a small APS-owned contract.

**Student-facing toolchain (all pip-installable on macOS and Linux, deterministic enough for agent-written tests, and CV-legible):** Python + MuJoCo + Gymnasium + Stable-Baselines3 (or MuJoCo Playground on the workstation) + LeRobot.

## Cross-platform reality check (macOS + Linux)

Verified against upstream docs and issue trackers:

| Component | macOS | Linux | Notes |
|---|---|---|---|
| MuJoCo (native, CPU) | ✅ first-class (`pip install mujoco`, `mjpython` viewer) | ✅ | Deterministic CPU stepping; identical results on student MacBooks and the workstation — the most agent-friendly engine here |
| MuJoCo WASM (`@mujoco/mujoco`) | ✅ CI-tested | ✅ | First-party DeepMind bindings under `mujoco/wasm/`; Windows is the experimental platform, not macOS |
| MJX (JAX) | ⚠️ CPU only — `jax-metal` is broken in practice (missing ops, `mhlo.reduce` legalization failures) | ✅ GPU (CUDA) | JAX-CPU works fine for tiny 8-DOF Sesame batches; do not let students burn a week on jax-metal |
| MuJoCo Warp | ❌ | ✅ CUDA-only, x86-64 | No macOS path at all |
| Genesis World | ❌ broken (OpenGL 4.1 cap vs. required 4.2, MPS float64 incompatibility, version churn) | ⚠️ NVIDIA | Instructor-only spike; exclude from anything students touch |
| Isaac Sim / Isaac Lab | ❌ never | ✅ Ubuntu 22.04/24.04, GLIBC ≥2.35, RTX GPU | Workstation-only elective; heavyweight, version-matched install is the most agent-hostile environment in the stack |
| Newton | ⚠️ CPU only | ✅ CUDA for everything interesting | Warp is a mandatory dependency; tiled sensors and MPM are NVIDIA-only |
| LeRobot | ✅ Apple Silicon supported (TorchCodec; Intel Mac falls back to pyav) | ✅ | Strongest CV pairing with MuJoCo |
| Wokwi (ESP32-S2 firmware sim) | ✅ browser + CLI | ✅ | Officially simulates ESP32-S2; Arduino/ESP-IDF, GDB, CI screenshot capture |

**Consequence:** batched GPU RL training is a workstation (or cheap cloud GPU) activity; students develop, evaluate, and replay everywhere on CPU MuJoCo. This platform gap is a teaching moment about hardware-dependent throughput, not a wall — design stages accordingly.

## Feasibility on the current workstation

The available machine is unusually suitable for the work:

- NVIDIA RTX 5000 Ada Laptop GPU, 16 GB VRAM, compute capability 8.9;
- Intel i9-13980HX, 32 logical CPUs;
- 188 GiB system RAM; and
- roughly 2.6 TB free local storage.

This is ample for Sesame-scale rigid-body simulation, parallel proprioceptive RL, Gaussian-splat training, Blender, and meaningful Isaac/Genesis experiments. Sixteen GB VRAM will still constrain large camera batches, high-resolution RTX synthetic data, and VLA fine-tuning. Those workloads should start with small images, few cameras, mixed precision, and modest models.

## Candidate stack

### MuJoCo: recommended reference core

MuJoCo is mature, Apache-2.0, actively maintained, and has C, Python, first-party JavaScript/WebAssembly support, MJX, and MuJoCo Warp paths. MuJoCo Playground adds Apache-2.0 GPU-accelerated robot-learning environments, sim-to-real examples, vision support, PPO/SAC-style workflows, and reproducible project tooling.

Why it fits APS:

- small enough to understand and run locally;
- deterministic CPU reference behavior is practical for tests;
- MJCF is expressive for actuators, limits, contacts, and sensors;
- browser/WASM makes a portable interactive version realistic;
- MJX or Warp provides batched training without changing the conceptual model; and
- its license and contribution process are clear.

Limitations: browser simulation is not the high-throughput RL path; photorealism and Gaussian splats need a separate renderer or backend; model conversion must be tested rather than assumed lossless.

### Genesis World: instructor-only tracked spike (demoted)

Genesis World 1.x is Apache-2.0 and exposes rigid/multi-physics simulation, sensors, parallel environments, multiple renderers, differentiability, URDF/MJCF/OBJ/GLB/USD ingestion, and a Python API. Its compiler advertises CUDA, AMD ROCm, Apple Metal, Vulkan, x86, and ARM64 backends. Its Nyx renderer includes a 3D Gaussian-splat path.

This is close to the long-term dream on paper, but it currently fails the cross-platform and stability test: Apple Silicon rendering is broken (macOS caps OpenGL at 4.1 while Genesis requires 4.2 — `glDrawElementsInstancedBaseInstance` symbol not found), MPS lacks float64, pip-vs-source version conflicts recur, and API churn breaks published examples. It is also the weakest CV item in the stack — impressive demos, thin industry adoption so far. Treat it as an **instructor-only spike on the Linux workstation, revisited each term**; exclude it from anything students touch. Validate contact behavior, reproducibility, installation, export, and sim-to-real on Sesame before any larger commitment.

### Isaac Sim and Isaac Lab: optional high-fidelity accelerator

Isaac Lab is an open robot-learning framework with mature GPU parallelism, cameras, depth, segmentation, IMU/contact sensors, domain randomization, and several RL libraries. Isaac Sim provides RTX rendering, OpenUSD workflows, synthetic data, and neural-volume/Gaussian-splat integration.

It is realistic on the current NVIDIA hardware and valuable for learning industry tooling — Isaac *is* the industry name in humanoid/manipulation job postings, so it has real CV value. But it has **zero macOS support** (Ubuntu 22.04/24.04 + Windows only, GLIBC ≥2.35, RTX required), and its heavyweight, version-matched, GUI-centric install makes it the most agent-hostile environment in the stack (slow startup, licensing prompts, poor fit for tight agent iteration loops). Frame it as a **workstation-only elective for CV value — never on the student critical path**. It should remain an adapter because Isaac Lab depends on version-matched Isaac Sim/Omniverse components with additional proprietary terms, and deployment is NVIDIA-centric. Use it to learn and produce data—not as the only place where the robot, task, or policy can exist.

### Newton: strategically interesting, not the first implementation

Newton is a Linux Foundation, Apache-2.0 GPU physics project initiated by Disney Research, Google DeepMind, and NVIDIA. It is based on Warp, integrates MuJoCo Warp, supports OpenUSD, differentiability, custom solvers, multiple viewers, and CPU/CUDA execution.

Its architecture points toward a less Omniverse-bound NVIDIA path, but it is still young and GPU acceleration is primarily CUDA. Track and test it after the MuJoCo vertical slice; do not place the first student deliverable on it.

### Browser workbench

The browser is Stage 1's **demo and inspection layer**, not a co-equal runtime. The first-party MuJoCo WASM bindings (`@mujoco/mujoco`, maintained by DeepMind in-tree, macOS CI-tested) make the pure-web dream far cheaper than originally assumed: a shared MJCF model runs natively and in-browser with no porting. Most of the web payoff therefore arrives *for free* by staying on MuJoCo — pure-web remains a stretch achievement with no milestone or exit criterion of its own, and it must never displace the CV-legible native toolchain. Use the browser for the human/agent feedback loop, not as the only compute runtime:

- Vite + TypeScript for immediate hot-module reload;
- PlayCanvas Engine for WebGPU/WebGL rendering, glTF, WebXR, and native Gaussian-splat support;
- SuperSplat as both a reference implementation and a usable MIT-licensed editor;
- first-party MuJoCo WASM (`@mujoco/mujoco`) in a Web Worker for portable small-scene physics; and
- WebSocket/WebRTC state streaming from Python for native CPU/GPU simulation and training.

This split preserves the excellent Chrome DevTools loop while allowing thousands of headless environments to train outside the browser. A scripted scenario runner can reload the app, apply controls, capture screenshots, inspect console/network errors, and record numerical assertions through Chrome DevTools Protocol.

WebGPU is highly valuable for rendering, splat interaction, lightweight inference, and teaching GPU concepts. Reimplementing mature batched robot physics and RL in WebGPU should not be an early objective.

### Blender and asset interoperability

Blender is the right owned authoring surface for mesh cleanup, origins, scales, materials, collision proxies, camera paths, and animations. Keep source `.blend` files plus generated artifacts.

No single exchange format covers everything:

- **MJCF**: canonical executable dynamics model for the MuJoCo reference;
- **URDF**: broad robotics interchange and a useful generated view;
- **GLB/glTF**: browser visual assets;
- **OpenUSD**: Omniverse/Isaac scene composition and larger workflows;
- **OBJ/STL**: manufacturing/import sources, not semantic robot definitions; and
- **PLY/SOG or standardized splat formats**: captured appearance only.

Store actuator order, physical pins, angle conventions, calibration, safe limits, and firmware command mapping in an APS-owned machine-readable manifest. Generate/check backend files from that manifest where practical.

### Firmware simulation: MuJoCo does not emulate the ESP32-S2

MuJoCo (native or WASM) simulates the robot *body* only — bodies, joints, contacts, and idealized actuators. It has no concept of a microcontroller, GPIO, PWM timers, serial parsing, or the firmware control loop. Simulating the S2 mini's Arduino/ESP-IDF code is a separate concern with its own well-supported tool:

- **Wokwi** officially simulates the ESP32-S2 (plus S3/C3/C6/etc.) in the browser and via a CLI, runs Arduino and ESP-IDF projects, and supports GDB debugging, virtual serial, Wi-Fi simulation, and screenshot capture for CI — an unusually agent-friendly loop for firmware logic tests.
- **Espressif QEMU** documents ESP32/C3/S3 targets; ESP32-S2 support is community-grade only. Prefer Wokwi for the S2 mini.

Recommended decomposition: MuJoCo tests what the servos do to the world; Wokwi tests that the firmware's command parser, PWM mapping, and watchdog behave; the seam is the **SafeAction command vocabulary**, tested independently on each side. Bridging Wokwi's virtual serial into MuJoCo WASM in a single browser tab is theoretically possible but is a research project, not a milestone. For sim-to-real fidelity, what matters (servo lag, deadband, backlash, latency) is best captured as *measured actuator models inside MJCF*, not by emulating the MCU cycle-by-cycle.

## Gaussian splats: useful but not a physical world model

Gaussian splats can provide compelling captured backgrounds and visual domain adaptation. They do not inherently provide reliable collision geometry, articulation, affordances, or object identity. Every splat environment used for simulation needs a separate mesh, heightfield, or primitive collision representation and explicit coordinate alignment.

Recommended open workflow:

1. capture calibrated images/video;
2. estimate camera poses and train with `gsplat`/Nerfstudio or a compatible local tool;
3. inspect, crop, and optimize with SuperSplat;
4. create simplified collision geometry in Blender;
5. render in PlayCanvas for the browser;
6. test Genesis Nyx or Isaac NuRec only as optional higher-fidelity adapters; and
7. record transforms and provenance so appearance and collision assets remain aligned.

`gsplat` and Nerfstudio are Apache-2.0; SuperSplat is MIT and specifically supports local hot-reload development. This is a much clearer contribution base than the current Sesame community simulator.

## RL and vision-action learning

### Proprioceptive locomotion RL: realistic soon

Sesame has only eight actuators and a small state/action space. Training stand, recover, turn, or locomotion policies in batched MuJoCo/Genesis environments is technically realistic on the current GPU.

The difficult part is not obtaining a reward curve; it is sim-to-real safety and fidelity:

- measured mass/inertia, servo speed, torque, backlash, deadband, and latency;
- foot friction and compliant contacts;
- voltage/current limitations;
- calibration variation;
- observation and command delay;
- action rate and joint limits; and
- robust fall/stop behavior.

Policies should output bounded pose targets or small deltas through a rate-limited safety layer. They should never receive unrestricted raw servo authority on the physical robot.

### Vision-action models: possible later, not the first milestone

LeRobot is Apache-2.0 and provides extensible robot interfaces, Parquet/video datasets, training/evaluation tools, imitation learning, RL, and VLA policies. Implementing a Sesame adapter and recording synchronized observations/actions would create durable value even before training a VLA.

The baseline Sesame currently has no camera and the ESP32 cannot host a useful vision policy. Initial inference would run on the workstation and send bounded commands over the network. A VLA is justified only after defining a visually observable task and collecting demonstrations. For this robot, compact behavior cloning or image-conditioned policies are educationally and scientifically cleaner than beginning with a foundation VLA.

Training a general VLA from scratch is not realistic for a small course. Fine-tuning a compact open model may become realistic after the dataset and safety path exist, but 16 GB VRAM will require careful model selection, quantization/adapters, and low-resolution inputs.

## APS-owned interfaces

A portable stack should define these engine-independent contracts first:

```text
RobotModel
  joint names/order, transforms, limits, actuators, sensors
  visual/collision asset references
  firmware pins, command mapping, calibration and revision

Environment
  reset(seed, parameters) -> observation
  step(safe_action) -> observation, reward, terminated, metrics
  snapshot/replay and deterministic test scenario

Observation
  timestamp, joint state, body pose, contacts, optional RGB/depth

SafeAction
  bounded target/delta, duration/rate, stop and watchdog semantics

Episode
  LeRobot-compatible video/images + tabular state/action metadata
```

Adapters can then implement MuJoCo, Genesis, Isaac, browser WASM, and the physical robot. Cross-backend tests should replay identical poses and compare transforms, contacts, and rendered calibration targets within declared tolerances.

## Educational value

### High value

- coordinate frames, transforms, units, calibration, and versioning;
- direct comparison of simulation assumptions with a hand-built robot;
- reward design, reward hacking, domain randomization, and sim-to-real gaps;
- safe action interfaces and watchdog design;
- open formats, reproducibility, profiling, and cross-backend tests;
- dataset design, bias, provenance, and evaluation; and
- agentic development where visual feedback is paired with numerical assertions.

### Medium value

- Gaussian-splat capture and alignment;
- synthetic camera data and visual randomization;
- Blender-to-simulator asset pipelines; and
- contributing focused improvements upstream.

### Low value at the beginning

- writing a new general physics engine;
- training a general-purpose VLA from scratch;
- replacing CUDA kernels with WebGPU before a task exists;
- building an Omniverse extension before a portable model passes; and
- photorealism without a measured learning/evaluation need.

## Realistic staged roadmap

### Stage 0 — contracts and reproducible seed project (1 week)

- Create a separate simulation repository rather than adding heavy dependencies to this static course site.
- Freeze the robot manifest, coordinate conventions, safe limits, and asset revisions.
- Build one command that launches a hot-reloading browser and a Python service.
- Add CDP smoke tests: load, no console errors, camera screenshot, eight-joint control, reset.
- Record environment/tool versions in a lockfile/container.

**Exit:** one deterministic pose appears consistently in Blender-exported GLB, MuJoCo, and the browser.

### Stage 1 — interactive Sesame digital twin (2–3 weeks)

- Build an MJCF model with separate visual and collision geometry.
- Add stock motion playback, joint sliders, serial/HTTP command vocabulary, plots, and replay.
- Run MuJoCo native and MuJoCo WASM from the same model/assets.
- Compare rest, stand, wave, and walk with the tethered prototype.

**Exit:** documented joint/pose agreement and known sim-to-real mismatches; no claim of predictive fidelity yet.

### Stage 2 — proprioceptive RL (2–4 weeks)

- Expose a Gymnasium-style environment; make **CPU MuJoCo + Stable-Baselines3 vectorized envs the student-facing default** — for an 8-actuator robot this trains stand/recover policies in minutes on any laptop.
- Add the vectorized MJX or MuJoCo Warp path as the "scaling" lesson on the Linux workstation (or a cheap cloud GPU); students on MacBooks cannot run this locally, and that is by design.
- Start with stand/recover, then turn or locomotion.
- Add domain randomization, policy checkpoints, deterministic evaluation, and videos.
- Deploy only through the bounded host-side safety interface.

**Exit (portable):** policy trains on any student laptop with CPU MuJoCo (small batch), beats a simple baseline in held-out simulation, and passes supervised low-power physical trials.
**Exit (scaling):** the same environment scales on the Linux workstation with MJX/Warp, with documented throughput comparison.

### Stage 3 — Blender and Gaussian-splat environment (2–4 weeks)

- Capture one room/object scene.
- Train and edit a splat; build aligned collision proxies in Blender.
- Load it in the browser and test Genesis or Isaac rendering as a comparison.
- Document scale, alignment, artifacts, and performance.

**Exit:** robot can be viewed and navigated consistently in captured appearance plus explicit collision geometry.

### Stage 4 — dataset and imitation learning (3–6 weeks)

- Implement a Sesame LeRobot adapter.
- Record synchronized state, commands, task labels, and external camera video.
- Train a small behavior-cloning/image-conditioned policy before any VLA.
- Establish offline metrics and guarded real-world evaluation.

**Exit:** reproducible dataset and a policy that improves on a non-visual or scripted baseline for one defined task.

### Stage 5 — optional VLA and multi-backend work (research track)

- Fine-tune a compact LeRobot-supported VLA only if task/data justify it.
- Compare MuJoCo, Genesis, and Isaac observations/policies.
- Explore Newton and WebGPU inference/compute selectively.
- Upstream generic fixes and adapters where licenses and maintainers support them.

## Immediate recommendation

Start with a two-day technical spike, not an Omniverse installation marathon:

1. model Sesame minimally in MJCF from the frozen dimensions;
2. run it in native MuJoCo and first-party MuJoCo WASM (`@mujoco/mujoco`) from the same MJCF;
3. create a Vite browser shell with hot reload and CDP screenshot/assertion scripts;
4. stream or share eight joint states and load a GLB visual model;
5. measure browser frame rate, native step rate, and coordinate agreement; and
6. separately run one stock Genesis rigid-body example to verify the GPU toolchain (instructor, Linux workstation only).

If that vertical slice feels as interactive as expected, it becomes the owned foundation. Isaac Lab can then be evaluated against the same robot/task contract rather than becoming the architecture by default.

## Primary upstream references

- MuJoCo: <https://github.com/google-deepmind/mujoco>
- MuJoCo Playground: <https://github.com/google-deepmind/mujoco_playground>
- Genesis World: <https://github.com/Genesis-Embodied-AI/genesis-world>
- Isaac Lab: <https://github.com/isaac-sim/IsaacLab>
- Newton: <https://github.com/newton-physics/newton>
- LeRobot: <https://github.com/huggingface/lerobot>
- Blender: <https://projects.blender.org/blender/blender>
- SuperSplat: <https://github.com/playcanvas/supersplat>
- PlayCanvas Engine: <https://github.com/playcanvas/engine>
- gsplat: <https://github.com/nerfstudio-project/gsplat>
- Nerfstudio: <https://github.com/nerfstudio-project/nerfstudio>
- glTF: <https://github.com/KhronosGroup/glTF>
- MuJoCo WASM (first-party): <https://github.com/google-deepmind/mujoco/tree/main/wasm>
- Wokwi (ESP32-S2 firmware simulation): <https://docs.wokwi.com/guides/esp32>
- Stable-Baselines3: <https://github.com/DLR-RM/stable-baselines3>
- Gymnasium: <https://github.com/Farama-Foundation/Gymnasium>
