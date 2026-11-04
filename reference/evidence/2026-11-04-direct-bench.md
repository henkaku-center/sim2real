# Direct bench response — November 4, 2026

The instructor reported slow movement on a student's USB-connected S3. Serial
status showed roughly 10 commanded degrees per second in bench mode. Current
source used CAL_RATE=15 and capped elapsed step time at 20 ms, so loop stalls
could further reduce wall-clock speed. Exact loop-stall attribution was not
measured; neither servo failure nor electrical waveform quality was inferred
from a command acknowledgement.

Changed only bench-mode interpolation: each enabled channel's commanded output
now takes its target on the next service step. Channel/joint/run rates, watchdog,
off semantics, output exclusion, pulse conversion and calibration format remain.

Validation:

- Native firmware and clock tests: 4 passed on macOS; 4 passed on Artemis/Linux.
- Clean pinned Arduino build: 1,027,865 bytes program, 48,800 bytes globals.
- App SHA-256: `b44fa6701b67fa15513f50d5bff70dc65dd41b3156efe26ec00d5d5910bde653`.
- Arduino upload completed with written-data hash verification.
- Existing NVS reloaded: oscillator 28,441,028 Hz, prescale 138, saved=1.
  Earlier physical GPIO4 edge capture measured corrected PWM at 49.969693 Hz.
- CH1 targets 45, 135, 90 each appeared as matching current/target at the first
  status request, sent about 250 ms after the target. Two seconds between targets.
- Final status: outputs=0, hub=1, fault=0.
- Instructor's observation after this test: “oh finally that was speedy.” This
  confirms visibly faster response, not a measured shaft angle or rated speed.

Private partition-table/NVS backups, build report, upload log and serial capture
remain on Artemis under `~/sesame-bringup/2026-11-04-direct-bench/`. Full-flash
backup attempts stopped during transfer; no complete firmware rollback image
was obtained. Calibration-partition backup succeeded and was not published.
