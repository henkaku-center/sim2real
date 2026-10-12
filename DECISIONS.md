# DECISIONS LOG — sim2real

Append-only. Record every resolved question with date, decision, and rationale. Number entries `D1, D2, …`. Do not edit or delete past entries; supersede them with a new entry that references the old one.

Hardware-track decisions made before this repo existed live in the course repo (`henkaku-center/aps/DECISIONS.md`); the ones that bind this project are summarized in `HANDOVER.md` (two-brain architecture, LOLIN S2 Mini baseline, tethered-first power policy, 50% servo spares).

---

## D1. Repository scope and stack (2026-07-23)

**Decision:** Separate repo (`henkaku-center/sim2real`), not a subdirectory or submodule of the course site. MuJoCo as the cross-platform reference core; Gymnasium + Stable-Baselines3 student-facing; MJX/Warp workstation-only; LeRobot for datasets; first-party `@mujoco/mujoco` WASM + Vite for the browser; Wokwi for ESP32-S2 firmware logic tests.

**Rationale:** See `ROADMAP.md` ("Cross-platform reality check") — the course site is deliberately build-free and must stay so; submodules are agent- and student-hostile; MuJoCo is the only physics core first-class on both macOS and Linux; the accelerated paths are all NVIDIA/Linux.

## D2. Kinematic conventions verified against prior-art simulator (2026-07-23)

**Decision:** Freeze the STL-derived kinematics in `sim/build_mjcf.py`: hips rotate about a VERTICAL axis (horizontal leg sweep, X-stance at stand), feet pitch a 47 mm paddle about a horizontal axis; joint channel/pin/sign mapping per `manifest/robot.yaml` (point-symmetric servo mounting). Behavioral semantics are locked by `tests/test_behavior.py` telemetry assertions.

**Rationale:** Two convention bugs (vertical-swing hips; left/right sign grouping) survived all self-consistency tests and were caught only by human visual QC (wave paw grounding, stand asymmetry). Axis positions were then measured from the upstream v117 STLs (servo-horn circle fits: hip horn on femur top face at asm (x=1.5, z=±23), foot axis at (y=15.25, z=59.9)). The `dance` posture (sit-back, face up) was verified against the hosted prior-art simulator by the instructor on 2026-07-23; `bow`/`wave`/`turns` are consistent with the same mapping. Known open mismatch: `point` flips in sim (placeholder masses, xfail-documented); `walk` drifts laterally. Both await measured masses (NEEDS-HARDWARE).

## D3. S3 SuperMini + PCA9685 course hardware default (2026-09-22)

**Decision:** Instructor selected the new hand-soldered S3/PCA9685/OLED/battery assembly as the APS-II
default, superseding the S2 hardware baseline summarized in the original handover. Detailed board
materials are expected 2026-09-23. Course decision: APS D24.

**Evidence:** shared I²C after solder repair, visible OLED, full-firmware boot, individual servo motion,
and human-confirmed completion of a seven-second simultaneous eight-servo battery diagnostic.
This is not measured maximum-load acceptance. Physical joint order was reported wrong; Wi-Fi was
not visible. Current installed firmware is the temporary load diagnostic. Source/evidence and recovery:
`reference/SESAME-S3-BUILD-STATE.md`.

**Manifest boundary:** preserve D2's simulator conventions and current manifest pending measured S3
channel/joint/direction calibration. The new firmware's intended mapping is not yet verified on this
assembly. Do not pass raw new PCA channel numbers to the simulator's logical channel interface.

## D4. Assembly-model ownership and position-servo scope (2026-09-23)

**Decision:** Keep component geometry and the electronics assembly model in `sim2real`,
linked by ASIN to APS's canonical purchasing inventory. Instructor confirmed the
70 × 50 mm carrier B071JYD6QP and the battery/converter/toggle purchases recorded in
`reference/ELECTRONICS-CAD-SOURCES.md`. The 60 × 80 mm carrier is a mistaken purchase.

Support the mixed position-controlled MG90S purchases through a shared parametric
family with variant overrides and verified mounting geometry. The instructor excluded
continuous-rotation HiRCgo MG90D B0FH1KZ64Y as a mistaken purchase: leg joints require
fixed-angle positioning. This supersedes the earlier discussion's all-four-purchases
compatibility target. Procurement quantities and available working stock are distinct.

## D5. Validate standalone circuitry before enclosure redesign (2026-09-23)

**Decision:** Instructor knows the present circuit board will not fit the original
printed body. Build and physically validate a separate circuitry model first;
redesign the body after the instructor is confident in the circuitry's accuracy.
Do not use the old enclosure as a constraint on the as-built electronics model.

**Working artifact:** `assets/cad/work/Sesame-S3-circuitry.FCStd`, versioned through
Git LFS. Start from the confirmed 70 × 50 mm carrier outline; distinguish published
dimensions from measurements and leave unknown component placements unresolved.
Native document properties are authoritative after initial creation so human edits
survive subsequent agent sessions. The older full-robot CAD remains a reference.

## D6. Preserve assembly data for interactive student instructions (2026-09-24)

**Decision:** Instructor wants these as-built models and construction details to
support future animations and rotatable, stepwise student instructions. Record
the necessary information during co-design; defer animation/viewer implementation.

Maintain stable semantic part/step IDs, exact native CAD bindings, coordinate
frames and units, measured-versus-assumed dimensions, source evidence, ordered
before/after states, and suggested inspection views. Preserve removable and
consumed intermediates conceptually: plastic spacers, uncut pins, offcuts, tape
layers and solder additions. Explicitly identify intermediate geometry not yet
modeled. Do not flatten the assembly or imply the final model alone reproduces
its construction history.

**Initial records:** `assets/cad/instructions/README.md`,
`converter-installation.json`, and `converter-cad-snapshot.json` in that directory.
The snapshot is observational; native CAD remains authoritative as in D5. Preserve
the distinction between the versioned carrier and the local, ignored converter
comparison with unresolved upstream redistribution permission. This decision
does not change the simulator manifest, calibration or current course viewer.

## D7. One clearly named assembled electronics document (2026-09-24)

**Decision:** Instructor requested a clear final-model filename, removal of
unnecessary separate CAD files, and opening the full assembly by default while
preserving metadata for future animated (potentially WebGPU) instructions.

**Artifact:** `assets/cad/Sesame-S3-Assembly.FCStd` consolidates the completed
converter/hub/S3/wiring model and editable native carrier into one self-contained
document. Retire the carrier-only working file, layout-start and reproducible
native reference imports. Keep construction recipes as explicitly historical
sources, and retain source notices, hashes, evidence and authoring records.

The visible assembled result and hidden editable carrier history have distinct
groups. Stable native names, InstructionIds, placements, expressions and separate
pin/solder/insulation objects survive the consolidation. The snapshot is now
`assets/cad/instructions/assembly-cad-snapshot.json`, with one document binding
and explicit effective visibility for future renderer exports. Installation step
IDs, dependencies and state changes remain intact. No animation implementation,
new physical validation or resolution of third-party source permissions is implied.

## D8. Imported component geometry cleared for public release (2026-09-26)

**Decision:** The instructor confirmed that redistribution permission is fine for
all components in `assets/cad/Sesame-S3-Assembly.FCStd`, including the imported
LM2596 converter, uploaded PCA9685 servo-hub and ESP32-S3 models.

**Consequence:** The public APS build instructions
(<https://aps.chibatech.dev/ii/sesame-build/>) now show the exact assembly geometry
instead of box stand-ins. Earlier "permission unresolved" notes in D6, D7 and the
instruction records are superseded by this decision; their provenance and hash
evidence remain unchanged. No dimensional, electrical or manifest change is implied.

## D9. Repository licensed Apache-2.0 and made public (2026-10-04)

**Decision:** The instructor chose Apache-2.0 for this repository, matching the
upstream Sesame project, and approved making `henkaku-center/sim2real` public after
a history scan found no secrets (gitleaks, trufflehog) or personal data beyond
commit-author emails, which the instructor accepted.

**Consequence:** `LICENSE` added at the root. Third-party files keep their own
licenses (Sesame Apache-2.0, Adafruit MIT, Source Code Pro OFL); D8 covers the
imported component geometry.

## D10. Unified S3 calibration/controller and measured-device overlay (2026-10-06)

**Decision:** Deliver one maintained image in `firmware/sesame-s3/`, containing
calibration, upstream faces/manifest motions and an explicit AP. Preserve the
September diagnostics as evidence. Generate constants and the APS guide's sole
machine-readable handoff (`reference/sesame-s3-interface.json`: map/status,
commands, calibration schema) from the existing canonical manifests.

**Pulse-range qualification:** The owner requested manifest732–2929µs mapping.
Implement it with configured/measured PCA oscillator and rounded tick math,
but require horn-disengaged centring and per-device limits. Source investigation
established that ESP32Servo3.0.9 clamps upstream's `attach(...732,2929)` to2500µs;
the former S3 cap512ticks deliberately reproduced that effective limit. The
~19.5% electrical-span mismatch is not a measured20% loss of physical travel.
Horn offset, clock error and actual channel identity remain NEEDS-HARDWARE.

**Calibration:** A versioned/checksummed NVS record stores per-joint unique
channels, absolute physical signs, trims, measured limits, verification bits
and oscillator frequency. Export JSON for instructor review. No unverified
target map is auto-installed: default channels are unassigned. Simulator S2
GPIO/sign/angle facts remain intact; an additive S3 profile records only wiring
expectations and commissioning bounds. Updating the map/trim/sign/limits clears
the relevant verification; clock changes clear all verification.

**Bounded commissioning behaviour:** All command paths use the same SafeAction
gate, calibration15°/s and controller60°/s (below the existing300°/s maximum),
500ms external heartbeat, queue cancellation and post-trim electrical limits.
S3 watchdog failsafe is outputs-off, rather than trying a Rest motion through
an unknown map. `stop` freezes targets; `off` releases PWM. Outputs remain off
through boot/arm until an explicit target. BOOT offers a finite30s battery-only
raw90° assembly centre and active-press abort; this avoids requiring simultaneous
USB/battery power before isolation has been verified. Initial neutral acquisition
is open-loop and cannot assume a sensed shaft position. Verify OE/pull-up before
powered trials; software cannot guarantee shutdown through a failed I²C bus.

**Controller:** Preserve all19 canonical stock motions with nonblocking,
rate-limited execution and upstream face assets. Explicit visible AP-only,
channel1/countryJP/moderate8.5dBm request plus error/readback telemetry makes
the absent AP diagnosable. The old load test has no AP code; historical full
firmware visibility failure is unresolved. Do not label the antenna or TX power
as a proven cause. Class build/flash uses pinned arduino-cli/core/library versions;
no robot access or firmware upload occurred in this offline implementation.

## D11. Text-generated S3 body with immutable leg interfaces (2026-10-06)

**Decision:** Use scripted FreeCAD `Part` / OpenCascade for the agent-editable
body, with `assets/body/params.json` and `tools/body_cad.py` as its source. Read
the authoritative `Sesame-S3-Assembly.FCStd` without saving it; export native
electronics STEP plus semantic bindings for enclosure review. CadQuery and
build123d are viable alternatives, but would add another CAD runtime and an
interchange boundary without improving access to this native assembly.

**Interfaces:** Keep upstream leg templates and the leg print set unchanged,
with checked SHA-256 identities. V1 also retains the complete upstream frame
and bottom, using its old PCB attachment bores for a raised carrier tray. This
preserves servo pockets rather than approximating them with newly drawn boxes.
The taller layout prioritizes clearance and straightforward fabrication; it is
an engineering draft, not acceptance of its stability or physical fit.

**Validation:** Generate STEP/STL/3MF, a part/placement/assembly-order handoff,
machine-readable interference/clearance/alignment findings, sampled wall and
manifest-driven leg-motion checks, print-orientation/overhang reports, and CPU
review renders. Numerical failures remain failures; no guessed servo, wire or
peripheral dimensions are silently promoted to measured geometry. The upstream
CAD's hip-shaft registration differs from the existing simulator/template
registration and remains an explicit reconciliation item.

**Overnight scope:** The owner authorized evidence-based parameter assumptions
without waiting for hardware access. Battery 51 × 28 × 14 mm and toggle 13 ×
8 mm footprint come from the recorded exact-ASIN listings. Unknown thread,
connector, cable-exit, OLED, servo-variant and fastening dimensions stay flagged
with specific caliper/ruler instructions in `reference/BODY-CAD.md`.

**Handoff boundary:** APS's optional circuit-in-body step consumes
`assets/body/v1/assembly.json`, per-part exports and `report.json`; it remains
hidden until geometric and physical fit are accepted. Keep generated MuJoCo
torso meshes/mass/inertia as a follow-up: the raised assembly changes mass
distribution materially, so a cosmetic mesh swap or guessed scalar mass would
misrepresent the robot. No firmware, manifest calibration or actuation changes
are part of this body revision.

## D12. Bench-first horn calibration and Tim reference import (2026-10-11)

**Instructor direction:** Rework APS-II steps 29–33 around firmware verification
and eight-servo bench calibration before leg attachment. Use a loosely fitted
single-arm horn with no retaining screw; show all eight leads; label intended
joint and actual channel in an easily inspected bench arrangement. Students work
through an agent-facing `debug-firmware.md` and report physical observations.

**Source permission:** The instructor explicitly confirmed permission to
republish/adapt Tim's code. Preserve the selected test and common-header files
at `98d030a2d1e2e2e1f195669a9f87fcf9c5f1d465` under
`reference/vendor/tim-servo-debug/`, with byte hashes and a permission notice.
The unchanged automatic-sweep sketch is not the classroom flash target.

**Open decisions:** The instructor requested a comparison before choosing the
production pulse profile. D10 remains in force; neither neutral convention nor
saved calibration is changed by this import. Wired USB debugging is preferred
because Wi-Fi is not stable, but the USB/servo supply arrangement still needs
physical verification. `reference/SERVO-BENCH-PLAN.md` records the comparison and
proposed sequence. Firmware/rigid-body/RF simulation research is separate.

## D13. Tim-compatible APS commissioning/production profile (2026-10-12)

**Decision:** Following the comparison, the instructor approved the APS interactive
controller with Tim-compatible pulse semantics. Define the profile only in
`manifest/robot.yaml` → `hardware_profiles.sesame_s3.pulse_profile`. Preserve Tim's
floor-interpolated 150–512 reference counts at 25 MHz/prescale 121; convert these
reference pulses to counts using each device's nominal/measured oscillator. This
supersedes D10's S3 732–2929 µs range. The historical S2 simulation fields remain
unchanged and must not be mistaken for this S3 profile.

**Contract:** neutral 90° = 331 reference counts = 1615.28 µs. Calibration and
production share `angleUs`; fractional rate-limited targets use the same reference
count quantization. The new manifest fingerprint rejects old NVS calibration.
Keep the bounded gate, explicit arming, outputs-off boot and external watchdog.
The OLED bench view pairs raw channels 0/4, 1/5, 2/6, 3/7 and distinguishes
unassigned names and never-commanded positions; it does not infer shaft feedback.

**Validation:** 23 targeted pytest cases passed on macOS, including native C++
sanitizers and all 181 integer-angle comparisons to Tim's actual pinned code.
The same native sanitizer executable source passed on Artemis/Linux. A clean
macOS Arduino build used 1,021,269 bytes (77% of application space); no hardware
flash/actuation was performed. Local clean-build entry point took 2m22s, including
toolchain/source checks; native targeted tests took about 2.5s. These are local
measurements, not CI timings. Build uses two compiler jobs; an independent native
test uses one additional job, within the 12-logical-CPU/64-GiB host budget. Generated
artifacts are written once before parallel readers; hardware access stays serial.

**Physical boundary:** battery unplugged was confirmed. Wired servo supply/USB
isolation and servo disconnection before reset/flash are still to be verified.
No source-only result certifies the assembled robot's range, power or Wi-Fi.
