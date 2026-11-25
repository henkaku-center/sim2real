# Validation and self-review — 25 November 2026

## Claude / Google migration

- `uv run --project tools/voice_demo --locked --extra google --python 3.11 python -m pytest tests/test_voice_demo.py tests/test_voice_providers.py -q`:
  **66 passed, 1 skipped**, 13.16 seconds, macOS Intel / Python 3.11.16. The skip
  is Linux-only GPIO. The Google SDK installed successfully on this Mac.
- `uv run --locked pytest -q`: **502 passed, 19 skipped, 1 expected failure**,
  124.49 seconds, Python 3.12.13. The root environment has no Google extra, so
  five Google-specific cases skip there and pass in the dedicated voice run
  above. This full run began before the final three defensive provider cases
  were added; the 66-pass focused run includes those cases. Remaining skips
  reflect existing environment/hardware/browser coverage limits.
- Fake HTTP → relay → native C++ firmware PTY demo: completed the custom snake
  sequence, asserted `mode=0 outputs=0`, and closed all owned resources.
- Mocked Claude HTTP covers exact Worker/Anthropic request fields and headers,
  tool input, no-tool recovery, invalid timing then correction, two failed
  attempts, wrong/multiple tools, truncated responses, bad JSON/oversized bodies,
  redirects, timeouts, and Worker HTTP 400/401/403/429/500/502 without retry or
  error-body disclosure. Refusal notes survive the server/relay HTTP boundary.
- Google tests exercise real V2 protobuf requests with a mocked `SpeechClient`:
  matching region/recognizer, two-language or `auto` config, WAV auto-decoding,
  ADC default construction without credentials passed, 30-second/no-retry RPC,
  client closure, empty recognition, ADC/API errors, and pre-ADC audio rejection.
  Separate-adapter integration passes Japanese transcription to the planner.
- Self-review checked credentials stay out of prompts/logs, unsupported Worker
  fields are absent, no response can reach playback without full validation,
  no implicit fake fallback exists, and Pi-local cancellation remains separate
  from the longer provider wait. HTTP status is preserved but opaque error
  bodies are intentionally discarded; this limits diagnosis of the live 403.
- CI's existing three-platform voice job now installs the Google extra and runs
  both voice test modules on Linux x86_64, Linux arm64 and macOS (Python 3.11).

### Live Worker check — stopped on first rejection

At **2026-11-25 06:36:49 UTC**, ran the application server, normal HTTP client and
task-owned native PTY using the new Claude adapter. The exact test endpoint was
recovered from its **Wrangler deployment log**, not guessed. `wrangler whoami`
confirmed the configured account, and `wrangler versions view` confirmed the
deployed default `claude-haiku-4-5`. The Worker was not changed or redeployed.
Its access token was read directly into the command environment from the
authorized private file, without copying it into this repository or output.

The first `POST /v1/messages` returned **HTTP 403**; the voice server returned
HTTP 502 with `Claude HTTP 403; check endpoint, credentials and model access`.
Elapsed client time was **0.088 seconds**. No Messages response, usage, tool
call or plan was received. We cannot determine whether the rejection came from
the gateway's authentication, Cloudflare filtering, or upstream access from
status alone. No further live requests or alternative models were tried, in
accordance with the instruction to stop on Worker rejection.

| Prompt | Plan summary / result | Latency | Simulator | Sensible? |
|---|---|---|---|---|
| do a bow | HTTP 403; no plan | 0.088 s | No playback | Not assessable |
| say hello to the audience | Not attempted after rejection | — | — | — |
| おじぎして | Not attempted after rejection | — | — | — |
| みんなに挨拶して | Not attempted after rejection | — | — | — |
| dance | Not attempted after rejection | — | — | — |
| 泳いで | Not attempted after rejection | — | — | — |
| look cute | Not attempted after rejection | — | — | — |
| move like a snake | Not attempted after rejection | — | — | — |
| change your face to one eyeball | Not attempted after rejection | — | — | — |
| blorpt zibble flarn 987 | Not attempted after rejection | — | — | — |

**Typical planning latency and live plan quality remain unknown.** The 88 ms is
rejection latency, not successful model latency. The machine-readable receipt is
`live_results.json`; its revision identifies the base commit, with this provider
implementation uncommitted during the live attempt. `live_check.py` reproduces
the ten-prompt matrix and plays each successful plan through the native PTY,
asserting outputs off. No successful live plan existed to play in this run.

### Still unverified

Working gateway authentication/model access; live Claude tool/schema behavior,
plan quality and typical latency; direct Anthropic Console-key authentication;
Google ADC/IAM/API enablement on the planned VM; live English/Japanese audio,
silence/noise behavior and recognition latency/cost. No robot, microphone, Pi,
VM, firmware or calibration was changed. Hardware appearance/balance and
installation commissioning remain outside the native serial simulator's evidence.

## Original PR #42 baseline (before the provider migration)

### Executed locally

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

### Self-review findings addressed

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

### Baseline evidence limits

No real robot, microphone, USB button, GPIO, OLED, power supply, VM or live model
request was used. No firmware source/table or calibration data was changed.
The native PTY proves the implemented serial seam, not MCU scheduling or physical
motion. Complete unverified items are in README and simulator fidelity limits in
SIMULATOR.md. Provider endpoint/schema tests use fixtures, not paid API calls.
