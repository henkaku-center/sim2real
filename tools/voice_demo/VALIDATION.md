# Validation and self-review — 25 November 2026

## Executed locally

- macOS Intel, Apple clang 17, uv 0.12.19.
- `uv run --project tools/voice_demo --locked python -m tools.voice_demo.demo`:
  complete fake HTTP → relay → native firmware PTY snake sequence; final
  `mode=0 outputs=0` asserted; processes/PTY closed.
- `uv run --project tools/voice_demo --locked --python 3.11 python -m pytest tests/test_voice_demo.py -q`:
  36 passed, 1 skipped in 11.37 seconds (Python 3.11.16). The macOS skip is the
  optional Linux-only GPIO settings test. Includes oversized numeric angles and
  separate button/keyboard event-stream coverage.
- `uv run --locked pytest -q`: 478 passed, 13 skipped, 1 expected failure in
  112.84 seconds (Python 3.12.13). This includes the initial 34 voice tests.
  Existing browser/CAD-environment skips remain skips, not hardware validation.
- C++ simulator compiled with `-Wall -Wextra -Werror` on each fixture launch.

CI additionally exercises the minimal Python 3.11 environment on Linux x86_64,
Linux arm64 and macOS, plus the repository's existing full checks. The PR checks
are the cross-platform evidence; local macOS execution alone is not.

## Self-review findings addressed

- Firmware `pose` has exactly eight numeric arguments, no duration. Relay
  interpolation is local; each interpolated target is checked before sending.
- Firmware `stop` retains torque. Completion/failure/cancellation use `off`.
- A stock-start ACK is not completion. The relay awaits the explicit complete
  message and checks commanded status; clamps and unexpected OFF abort playback.
- Heartbeat is independent of audio/HTTP/playback waits and shares the console's
  100 ms cadence. A separate finite lease covers a stuck playback worker.
- A late HTTP response could otherwise re-arm after a local key/stop. Request
  generations invalidate stale replies, with one network worker and one player.
- The device's saved calibration can be narrower than the manifest. Read-only
  `export` preflight checks targets against it before arm; no calibration writes.
- Real firmware's missing weak face definitions are excluded from FACE_LIST.
- Stock walk/point contain R2=100 outside fitted travel. They are explicitly
  rejected by this demo, not silently altered or physically certified.
- Unknown/extra fields, NaN/bool/overflowing angles, wrong-side hips, infeasible
  times, schema/firmware mismatch, overlong plans and bitmap steps are rejected.
- The PTY uses the actual firmware parser, rate/clamp/watchdog and generated
  motion tables. The port opener tolerates ENOTTY only for unavailable modem
  controls; other serial errors still propagate.
- Separate USB button/keyboard input devices are supported, preserving offline
  keys with a one-button PTT peripheral. Audio remains bounded and in memory.
- systemd uses a system-Python environment rather than a home-directory managed
  interpreter that `ProtectHome` would hide. No network-online dependency on Pi.

## Evidence limits

No real robot, microphone, USB button, GPIO, OLED, power supply, VM or live model
request was used. No firmware source/table or calibration data was changed.
The native PTY proves the implemented serial seam, not MCU scheduling or physical
motion. Complete unverified items are in README and simulator fidelity limits in
SIMULATOR.md. Provider endpoint/schema tests use fixtures, not paid API calls.
