# Firmware → PWM → horns → robot: simulation plan

Research checked October 11, 2026. **Architecture proposal, not an implemented
firmware emulator or hardware validation.** The immediate class requirement is
bench commissioning before attaching legs; antenna design is a later extension.

## Recommended first slice

Build an **agent-launched localhost bench**, using the APS guide's typography,
colours and existing component assets. Default to simulation. Keep its hardware
transport explicit and separate; opening a page must never arm a real robot.

```text
agent / student commands
          ↓
shared firmware command + calibration logic
          ↓
timestamped PCA9685 / OE events
          ↓
PWM decoder → servo model → shaft / horn transforms
                              ↓ later
                    articulated MuJoCo robot
```

This is software-in-the-loop if the controller logic is compiled natively. Do not
call it ESP32 instruction emulation. Start with the native-testable code already
in `firmware/sesame-s3/safe_action.h` and `command_line.h`; separate Arduino I/O,
time, storage and PWM writes from the command dispatcher in `controller.cpp`.
Run the same logic on S3 and host; avoid a second hand-written JavaScript controller
which merely looks similar. The browser displays traces/state over a local API.

Keep the final API/launcher command unspecified until the implementation exists.
Use the existing Python/uv + browser toolchain, localhost binding, isolated output
directories and explicit transport ownership. Reuse APS theme tokens; preserve
electrical colours and label simulated positions as simulated.

### Observable contract

Each record should carry simulation timestamp, sequence number, firmware/profile
revision, origin (simulated/hardware), physical PCA channel, joint name if mapped,
commanded angle, target microseconds, prescale, on/off counts, OE/full-off state,
watchdog/stop state and calibration fingerprint. Keep measured shaft angle separate
and nullable: an MG90S command/display is not encoder feedback.

Model the PCA's register state: MODE1 sleep/restart/auto-increment, prescaler,
per-channel ON/OFF counts and full-on/full-off, and OE. For ordinary PWM,
period = 4096 × (prescale + 1) / oscillator_hz, and high time follows the modular
ON/OFF difference. Full-off and OE must override it; zero duty is not “zero degrees”.
Record nominal oscillator assumptions separately from measured calibration.

### Servo and mechanical layers

1. Eight bench shafts/horns, with joint/channel labels and actual commanded pulses.
   First use a documented ideal position model, then add measured speed, lag,
   deadband, backlash and torque limits. Outputs-off should not imply a shaft
   instantly returns to neutral; include passive behaviour when dynamics is added.
2. Couple to MuJoCo hinge actuators with bounded torques and calibrated target
   conversion. Do not teleport joint positions or prescribe body motion.
3. Add leg masses/inertias, calibrated joint axes/limits, friction and floor contacts.
   Let ground-reaction forces produce body motion. Replace the historical S2-era
   model mapping only through the owned manifest and verified S3 calibration.

[MuJoCo's actuation and dynamics documentation](https://mujoco.readthedocs.io/en/stable/computation/index.html#actuation-model)
provides the joint/actuator/constraint machinery. It does not emulate ESP32 firmware
or the PCA's I²C registers. Model fidelity and usable parameter values still need
physical identification; a plausible animation does not validate a gait.

## Running the actual ESP32 binary

### Wokwi — viable peripheral-level validation lane

[Official ESP32 support](https://docs.wokwi.com/guides/esp32) includes S3, I²C and
USB CDC. [Supported hardware](https://docs.wokwi.com/getting-started/supported-hardware)
lists SSD1306 and a servo but does not list PCA9685 as a built-in component.
Use its [custom-chip API](https://docs.wokwi.com/chips-api/getting-started) for a
verified PCA model; then export pulse traces for the same servo/physics adapter.

An existing [community PCA9685 model](https://github.com/bonnyr/wokwi-pca9685-custom-chip)
is a research starting point, not an accepted dependency. Its README explicitly
marks **OE unused** and MODE2 writes unimplemented. Consequently it cannot validate
our OE shutdown behaviour without extension and tests. Check licensing and pin a
revision before any reuse. Investigate the automation/trace transport and current
service terms before making it a required student dependency.

Wokwi's [Wi-Fi simulation](https://docs.wokwi.com/guides/esp32-wifi) exercises network
traffic and protocols. It does not establish antenna gain, matching or link
performance around our metal, battery and enclosure. Its public gateway monitors
traffic; use synthetic credentials/data. A localhost page around the simulator
does not, by itself, make every simulator dependency local/offline.

### Espressif QEMU — native alternative to investigate

[Espressif documents S3 emulation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/tools/qemu.html)
and prebuilt Linux/macOS binaries. The [S3 QEMU README](https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/esp32s3/README.md)
describes flash images, UART, GDB and virtual networking. CPU support alone is not
proof that this Arduino image, native USB behaviour, PCA9685 and OLED work unchanged.
Audit the required peripheral path and run a pinned minimal test image before
selecting it. It is a separate fidelity lane, not a replacement for the initial
shared-logic bench. No QEMU/Wokwi compatibility test was run in this research.

## Maxwell / antenna extension

[openEMS](https://docs.openems.de/en/latest/intro.html) is an EC-FDTD full-wave
Maxwell solver with Python interfaces, material definitions, field dumps and
near-to-far-field transformations. It is a suitable **candidate** for offline
antenna/placement studies, separate from the real-time mechanical timestep.

An RF model needs the antenna conductor/feed, matching network or port model,
PCB dielectric stack-up and losses, ground plane, nearby batteries/wires/metal,
enclosure materials and boundary conditions. Our decorative component meshes
do not supply those facts. Plan to compare S11, efficiency and radiation patterns,
then validate with RF measurements and repeatable real packet/RSSI tests. No
claim of “good Wi-Fi” follows from field plots or S11 alone.

Keep a shared coordinate frame and versioned geometry/material export. Let the
offline solver produce field datasets and reduced models (for example loss or
antenna-pattern tables) that a networking scenario can consume. Full board/device
EM, power electronics and robot contacts have very different time scales; do not
attempt one giant real-time solver for all of them.

For power-rail sag, reverse polarity or regulator behaviour, a separate lumped
circuit/SPICE model is a more targeted future investigation than full-wave EM.
It will need component models and measured supply/load data.

**Deployment caution from the project, not a guessed install recipe:** openEMS's
[package instructions](https://docs.openems.de/en/latest/install/package.html)
currently say its former macOS Homebrew formula is broken/unmaintained and manual
installation is required. Keep it off the classroom critical path; prototype on
the instructor workstation, and verify both OS paths before student adoption.

## Exit criteria and bounded parallel work

- Firmware branch: compare a fixed command sequence against native shared-logic
  traces; test rejected commands, channel isolation, stop/off and lost heartbeat.
- Peripheral branch: verify prescale/tick timing, OE, reset and I²C fault behaviour
  against datasheet expectations and measured hardware traces.
- Viewer branch: test eight separate horn transforms, correct labels, no hidden
  geometry/cables, theme parity, and simulated-vs-measured indicators.
- Physics branch: deterministic numerical tests for torque limits, joint signs,
  contact forces and body motion; require measured-data comparison before claiming
  realistic sim-to-real behaviour.
- RF branch: mesh convergence and measurement comparison, independently of the
  calibration milestone.

Build shared firmware artifacts once. These readers/tests can run independently
with a bounded budget (initially two CPU jobs), separate ports/output folders and
fixed seeds. Real hardware tests remain serial per device because serial-port
ownership and physical observations are shared. Do not rebuild a common binary
while another test is consuming it. No new CI pipeline was introduced by this plan.
