# Offline finite-load lifecycle — not hardware accepted

October 17, 2026. Scope authorised by the APS/sim2real owner through Chief:
implement and mock-test only what is independent of physical servo identification.

`sim/offline_load_lifecycle.py` is a pure, in-memory control-flow model. It is
not imported by the S3 firmware, flash/console tools, simulator entry points or
assembly guide. It has no device I/O, callbacks, clocks, channel maps, angles,
pulse values or default motion plan. It is not a runnable battery load test.

## What can be validated independently

- Preparation alone cannot start a run or expose an active phase.
- An explicit start with the current plan generation is required.
- Preparation tickets are in-memory and instance-specific; a recreated model
  cannot accept an old instance's ticket even if its counter starts at the same value.
- Only completion of the current opaque phase advances the finite plan.
- Per-phase and total virtual-time deadlines terminate the mock run. A completion
  at the deadline is too late; advancing phases cannot extend the total deadline.
- Abort prevents continuation. Reset drops preparation and invalidates old events;
  no automatic restart or persistence across a simulated power cycle exists.
  Abort does not need a functioning clock.
- Identical external events yield identical snapshots. Invalid/backward clock
  values and stale/out-of-order acknowledgements cannot advance a phase.

The caller supplies an immutable, finite tuple of unique phase identifiers and
positive integer time budgets. Test identifiers and times are synthetic fixtures,
not a proposed robot sequence, channel mapping or recommended hardware timing.
There is no serial/Web/BOOT command or firmware integration for this model.
Timeouts are checked on caller-supplied polling/completion events. There is no
background scheduler or independent real-time watchdog for a blocked host.

## What still depends on the instructor and hardware

The unanswered observation request remains: **Does the OLED show the paired-channel
table headed “CMD / outputs OFF”, and is the robot staying still?**

Physical identification/calibration must precede an approved motion plan. Motion
amplitudes, direction, timing, repetitions, power acceptance and the actual channel
map are deliberately not selected here. Future integration must use the existing
SafeAction gate and explicitly handle real outputs-off, watchdog and reset/power
behaviour. A mock abort cannot prove that physical outputs are off. Simulated
phase completion is not student observation or verification of movement.

No hardware commands, flashing, movement, load tests or supply changes are
authorised by this model. The 29–33 animation hold and body-preview gate remain.

## Validation

Run `python -m pytest -q tests/test_offline_load_lifecycle.py` in the repository's
Python environment. No new dependencies or build artifacts are required. Existing
PR CI collects this test on Linux and macOS; local execution on one OS is not
cross-platform acceptance. Current broad CI remains unchanged.

The lifecycle tests themselves are independent and use per-test in-memory state.
A single local pytest process is sufficient for this sub-second unit suite;
an independent static boundary check can run concurrently. No firmware build,
browser suite, hardware session or new orchestration machinery is needed here.
