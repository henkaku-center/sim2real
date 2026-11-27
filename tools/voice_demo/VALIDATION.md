# Validation and self-review

## Deepgram / Kotoleaf replacement — 27 November 2026

The production speech adapter now uses Deepgram through Kotoleaf exclusively.
Offline tests cover exact URL, WAV body, authorization and User-Agent, unchanged
English/Japanese transcripts, empty speech, HTTP 401/429/500, malformed/oversized
responses, HTTPS validation, missing tokens, redirects, disabled proxies and
secret-free errors. `/health` reports `stt_provider: deepgram`.

- uv **0.12.19** regenerated the demo lockfile, removing Google-only packages
  while retaining the base dependency versions.
- Python **3.11.16**, macOS Intel: focused voice suite **93 passed, 1 skipped**
  (Linux-only GPIO), 14.19 seconds.
- Python **3.12.13**: full root suite **549 passed, 17 skipped, 1 expected
  failure**, 164.69 seconds. Existing hardware/browser/environment skips remain.
- Complete fake HTTP → relay → native firmware PTY demo passed, asserting
  `mode=0 outputs=0`; shell syntax and `git diff --check` passed.
- Self-review checked the single production factory, startup failure without a
  token, bounded private errors, HTTP status, proxy/redirect refusal, secret
  mapping and removal of Google-specific runtime/configuration/dependencies.
  CI runs the voice suite on Linux x86_64, Linux arm64 and macOS.

The live deployed check will follow the owner's deployment from main. No live
provider requests, deployment, cloud resources or credentials were used here.
The comparison reported by the owner on 27 November is recorded in DECISION.md;
it is separate from this offline adapter validation.

The following sections preserve historical results for the superseded adapters.

## Claude / Google migration — 25 November 2026 (historical)

- `uv run --project tools/voice_demo --locked --extra google --python 3.11 python -m pytest tests/test_voice_demo.py tests/test_voice_providers.py -q`:
  **71 passed, 1 skipped**, 11.42 seconds, macOS Intel / Python 3.11.16. The skip
  is Linux-only GPIO. The Google SDK installed successfully on this Mac.
- `uv run --locked pytest -q`: **502 passed, 19 skipped, 1 expected failure**,
  124.49 seconds, Python 3.12.13. The root environment has no Google extra, so
  five Google-specific cases skip there and pass in the dedicated voice run
  above. This full run preceded the final User-Agent/edge-diagnostic changes;
  the focused run covers those changes. Remaining skips
  reflect existing environment/hardware/browser coverage limits.
- Fake HTTP → relay → native C++ firmware PTY demo: completed the custom snake
  sequence, asserted `mode=0 outputs=0`, and closed all owned resources.
- Mocked Claude HTTP covers exact Worker/Anthropic request fields and headers,
  tool input, no-tool recovery, invalid timing then correction, two failed
  attempts, wrong/multiple tools, truncated responses, bad JSON/oversized bodies,
  redirects, timeouts, and Worker HTTP 400/401/403/429/500/502 without retry or
   arbitrary error-body disclosure. Tests assert the application User-Agent on
   first and correction requests and numeric-only edge diagnostics (including
   rejecting private-text suffixes, JSON and oversized bodies). Refusal notes
   survive the server/relay HTTP boundary.
- Google tests exercise real V2 protobuf requests with a mocked `SpeechClient`:
  matching region/recognizer, two-language or `auto` config, WAV auto-decoding,
  ADC default construction without credentials passed, 30-second/no-retry RPC,
  client closure, empty recognition, ADC/API errors, and pre-ADC audio rejection.
  Separate-adapter integration passes Japanese transcription to the planner.
- Self-review checked credentials stay out of prompts/logs, unsupported Worker
  fields are absent, no response can reach playback without full validation,
  no implicit fake fallback exists, and Pi-local cancellation remains separate
  from the longer provider wait. HTTP status and exact short numeric edge codes
  are preserved; arbitrary error bodies remain suppressed.
- CI's existing three-platform voice job now installs the Google extra and runs
  both voice test modules on Linux x86_64, Linux arm64 and macOS (Python 3.11).

### Live Worker checks

At **2026-11-25 06:36:49 UTC**, ran the application server, normal HTTP client and
task-owned native PTY using the new Claude adapter. The exact test endpoint was
recovered from its **Wrangler deployment log**, not guessed. `wrangler whoami`
confirmed the configured account, and `wrangler versions view` confirmed the
deployed default `claude-haiku-4-5`. The Worker was not changed or redeployed.
Its access token was read directly into the command environment from the
authorized private file, without copying it into this repository or output.

The first attempt returned **HTTP 403 in 0.088 seconds**, and live testing stopped
as instructed. The gateway owner then isolated Cloudflare edge code **1010** to
the default `Python-urllib/3.x` User-Agent, confirming that an application
User-Agent reached the unchanged Worker successfully, and explicitly requested
a rerun. Added `sesame-voice-demo/0.1.0` and narrowly filtered numeric diagnostics.

At **06:49:06 UTC**, the ten-prompt matrix completed on source revision
`104a928cc12225a72533a847f41b6586c24c9775` (clean tree at launch). The API returned
model snapshot **`claude-haiku-4-5-20251001`**. Latencies below are client-to-server
plan/refusal time, including correction attempts but excluding simulated playback.
Every returned plan was played through the normal relay on the native firmware
PTY, with numerical `mode=0 outputs=0` assertions after playback.

| Prompt | Plan summary / result | Latency | Simulator | Sensible? |
|---|---|---|---|---|
| do a bow | Stock `bow` | 2.350 s | Completed, off | Yes |
| say hello to the audience | `happy` face (1.5 s), `wave` | 2.732 s | Completed, off | Yes; a visual greeting, no speech |
| おじぎして | Stock `bow` | 2.580 s | Completed, off | Yes |
| みんなに挨拶して | `happy` face (1 s), `wave` | 2.766 s | Completed, off | Yes |
| dance | Stock `dance` | 2.463 s | Completed, off | Yes |
| 泳いで | Stock `swim` | 2.284 s | Completed, off | Yes |
| look cute | Stock `cute` | 2.353 s | Completed, off | Yes |
| move like a snake | Rest, four custom hip poses, rest; corrected once | 7.354 s | Completed, off | Limited: rhythmic splay/retract, not a travelling snake wave |
| change your face to one eyeball | Incorrectly substituted `surprised` face (2 s) | 2.673 s | Completed, off | **No**; schema-valid but semantically wrong; fixed/retested below |
| blorpt zibble flarn 987 | Refusal after two no-tool responses | 4.483 s | No plan, no playback | Yes |

The snake's initial R1=45° target violated fitted travel. Local validation caught
it, sent the joint-specific reason back, and accepted the corrected second
candidate. The four resulting hip targets alternate `[150,30,30,150]` and
`[110,70,70,110]`; ankle targets remain 90°, each transition is 1.2 s plus a
0.3 s hold. This demonstrates custom validated motion and correction, not a
learned snake gait or physical balance.

**Typical stock response: 2.46 s median (2.28–2.77 s).** The full ten-prompt
median was 2.63 s. The custom request took 7.35 s with correction; the nonsense
refusal took 4.48 s. The matrix used 12 model requests, 84,286 reported input
tokens and 2,526 output tokens, with no reported cache hits. These counts include
the gateway envelope and retry overhead, not a billing measurement.

### Semantic failure fixed and checked again

Validation of geometry/schema cannot establish correspondence to user intent.
Haiku originally claimed the `surprised` bitmap was a single eyeball despite the
general instruction against substitutions. Strengthened the capability prompt:
stock faces are immutable, eye count/shape/layout cannot be edited by this demo,
and `surprised` is not a one-eye asset. No keyword filter or hard-coded refusal
was added to the application.

At **06:52:38 UTC**, reran the unsupported request in English and Japanese plus a
supported face request, using the same Haiku model and the updated local prompt:

| Prompt | Result | Latency | Simulator | Sensible? |
|---|---|---|---|---|
| change your face to one eyeball | Correct refusal with fixed-bitmap explanation | 5.863 s | No plan, no playback | Yes |
| ひとつ目の顔にして | Correct refusal with fixed-bitmap explanation | 6.268 s | No plan, no playback | Yes |
| show a surprised face | `surprised`, hold 2 s | 2.458 s | Completed, off | Yes |

Both refusals used the required second attempt; the supported expression used
one. These checks used five requests, 35,379 input tokens and 922 output tokens.
No alternate model was needed after the capability clarification. Retest
success is evidence for these examples, not a guarantee of future semantic
correctness. The original ten prompts were not all repeated after that prompt
clarification. Full plans, notes, per-attempt times and usage are in
`live_results.json` and `live_face_recheck.json`. The latter records its dirty
tree because the capability-prompt change was uncommitted at launch. The
`live_check.py` entry point reproduces the matrix; it stores no credentials.

### Still unverified

Direct Anthropic Console-key authentication; generalization beyond these text
examples, repeatability under load and semantic correctness of arbitrary custom
requests; Google ADC/IAM/API enablement on the planned VM; live English/Japanese
audio, silence/noise behavior and recognition latency/cost. No robot, microphone, Pi,
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

### Cloud Run deployment check — 26 November 2026

Service `sesame-voice`, project `sesame-robots`, region `asia-northeast1`,
Claude through the test Worker (`claude-haiku-4-5`), Google Speech-to-Text
`chirp_3` in `us` with `en-US,ja-JP`. Requests came from a development Mac over
the public service URL with the device token.

| Input | Transcript | Plan | Total time |
|---|---|---|---:|
| no token, `GET /health` | — | HTTP 401 | — |
| typed "do a bow" | do a bow | motion `bow` | 2.80 s |
| synthetic speech, English "Do a bow" | Do a bow. | motion `bow` | 5.16 s |
| synthetic speech, Japanese 「みんなに挨拶して」 | みんな に 挨拶 し て 。 | motion `wave` | 4.22 s |

The audio was generated with macOS text-to-speech (16 kHz mono WAV), so this
shows the deployed speech and planning path works end to end; it says nothing
about a real voice, the exhibition microphone or cafe noise. Plans were not
played on a robot or the simulator in this check.
