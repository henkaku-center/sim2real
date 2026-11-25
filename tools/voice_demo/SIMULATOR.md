# Simulated robot: scope and derivation

`simulator.py` creates a POSIX PTY and a temporary native C++ executable. The
relay opens the PTY using the same PySerial function as USB. No simulator mode,
alternative command format or timing multiplier exists in the relay.

`robot_sim.cpp` directly includes the unchanged firmware `safe_action.h`,
`command_line.h` and generated `manifest_generated.h`. Thus these behaviours
execute the firmware's code: parsing/numeric rejection; mode IDs; arm without
pulses; calibrated/electrical clamps; 60°/s run slew; 15°/s joint slew; direct
bench targets; 20 ms maximum catch-up step; strict >500 ms watchdog; stopped
targets; and generated stock motion rows. Catalog startup verifies generated
tables against manifests and verifies the generated joint evidence's hashes.

The wrapper ports the relevant parts of `controller.cpp`:
- `serialService`: 159-byte lines, CR/LF terminators, overflow discard.
- `dispatchCommand`: `arm run/bench/channel/joint/assembly`, `angle`, `centre`,
  `servo`, `pose`, `motion`/`run`, aliases, `rest`, `face`, `heartbeat`, `stop`,
  `off`, `status`, `export`; exact reply strings for these commands.
- `motionService`: only advance after targets settle, honour wait rows, emit
  `CLAMP` and `OK MOTION complete`. Durations are not just sums of YAML waits:
  travel is rate limited too.
- `outputsOff`: cancel the queue, disarm, report OFF. `status` reports mode,
  enabled mask, USB owner and commanded positions; `export` reports the overlay.
- Face names come from FACE_LIST **and existing first-frame definitions**. The
  real controller ignores missing weak bitmaps; the simulator rejects them too.

By default the test device has a deliberately synthetic saved/verified reference
calibration with the manifest's soft ranges, signs and default channels. This
enables complete run-mode tests without modifying real NVS. `--fresh` uses the
firmware's unverified 85..95° defaults and refuses `arm run`; `--narrow` simulates
a saved but narrow calibration so the relay can prove it detects clamps before
playback. These are test fixtures, not a calibration recommendation or hardware
measurement.

## Omitted or not derivable from source alone

- No physical servos, contacts, balance, torque, load, power, PWM electrical
  accuracy, I2C faults, OE voltage, screen pixels or shaft-position feedback.
- No USB reset/re-enumeration/driver timing, transport contention, Web owner,
  captive portal, Wi-Fi, BOOT switch, NVS persistence or calibration editing.
- No clock-measurement, pulse/reference, sweep or diagnostic commands unused by
  this relay. They return ERR rather than pretend to work.
- The host poll loop is approximately 1 ms; it does not reproduce MCU task/ISR
  scheduling, Serial's 64-byte response chunks or hardware write backpressure.
  Kernel/host scheduling can stretch wall-clock execution. A delayed native
  loop still uses the firmware's 20 ms catch-up cap and real elapsed watchdog.
- Face commands are acknowledged, but bitmap animation and motion-selected face
  side effects are not rendered or physically verified.

The implemented command and motion semantics are source-derived. The omissions
above are explicit fidelity limits, not guessed hardware behaviour. This adds a
fast serial integration fixture alongside the repo's native/Wokwi/physics tools;
it does not replace MCU or real-robot validation.
