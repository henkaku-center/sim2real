# Sesame spoken-prompt demo

Software for the Loftwork/FabCafe **AI is not magic** exhibition: setup
**1 December 2026**, party **3 December 2026**, then a two-month installation.
No robot firmware changes. Hardware and the replacement speech path are not commissioned
by this change.

## Run the complete local demo

From the repository root, with `uv` and a C++17 compiler installed:

```sh
uv run --project tools/voice_demo --locked python -m tools.voice_demo.demo
```

This starts a loopback HTTP server with the deterministic fake provider, opens
a native-firmware pseudo-terminal, sends “move like a snake”, plays the custom
sequence through the normal serial relay, and asserts `mode=0 outputs=0` at the
end. All processes and the PTY are closed. It uses no microphone, robot, provider
key or external network. The first `uv` invocation may download locked packages.
Try `--text 'do a bow'` or `--text 'say hello to the audience'` too.

Python 3.11+ works, including Raspberry Pi OS Bookworm's Python 3.11 on arm64.
The small independent environment avoids installing MuJoCo/CAD dependencies on
the Pi or server. Base dependencies are **PySerial 3.5 and PyYAML 6.0.3**;
Deepgram transcription uses standard-library HTTP through Kotoleaf. GPIO
optionally adds **gpiod 2.3.0 on Linux only**. Versions/hashes are in `uv.lock`.
Development uses pytest 9.0.2. Native simulation needs `c++`; actual relay/server
deployment does not. The root repository pytest runner also discovers the tests.

```sh
uv run --project tools/voice_demo --locked python -m pytest tests/test_voice_demo.py tests/test_voice_providers.py -v
```

CI runs this minimal environment and the complete demo on Linux x86_64,
Linux arm64 and macOS, using Python 3.11. The simulator is a **serial behavioural
test double**, not a physics or MCU simulator; see [SIMULATOR.md](SIMULATOR.md).

## Three parts, separately

Run these from the repository root in separate terminals. Set the same random
`VOICE_DEVICE_TOKEN` in server and relay environments; use at least 16 ASCII
characters. Generate it locally with `python3 -c 'import secrets;
print(secrets.token_urlsafe(32))'`. Never commit a real token or provider key.

```sh
# 1. Server (explicitly fake, regardless of other environment keys)
VOICE_PROVIDER=fake uv run --project tools/voice_demo --locked python -m tools.voice_demo.server

# 2. Simulated USB robot: prints its /dev/pts/... or /dev/ttys... port
uv run --project tools/voice_demo --locked python -m tools.voice_demo.simulator

# 3. Relay: substitute the printed port
uv run --project tools/voice_demo --locked python -m tools.voice_demo.relay --port PORT
```

The development terminal accepts a text prompt followed by Enter. Local `1`
plays bow, `2` wave, `3` rest; `off` cancels; `quit` exits with outputs off.
`--text 'do a bow'` performs one request; `--local rest` plays without a server.
The complete demo deliberately forces fake mode, even if an API key is present.

### Push-to-talk and the USB microphone

On the Pi, install `alsa-utils`, select the USB microphone using `arecord -l`,
and use a stable ALSA device such as `plughw:CARD=Device,DEV=0`. Capture is mono
PCM16 at 16 kHz, at most 30 seconds / 960,000 PCM bytes, held only in memory.
Key down starts `arecord`, key up stops it and uploads a WAV. Key-repeat events
are ignored. A stuck button cannot record more than 30 seconds; release is still
required to submit. Microphone failure leaves local motion keys available.

```sh
uv run --project tools/voice_demo --locked python -m tools.voice_demo.relay \
  --port /dev/serial/by-id/YOUR-ROBOT \
  --input evdev --input-device /dev/input/by-id/YOUR-BUTTON-event-kbd \
  --ptt-code 57 --audio-device 'plughw:CARD=Device,DEV=0'
```

This reads press/release events from **only the specified Linux input devices**,
without a desktop or a global keyboard hook. `57` is Linux `KEY_SPACE`; use the
key code emitted by the button. Keys `1/2/3` and Escape on that selected device
work offline. For a one-button peripheral, add a keyboard using a second
`--input-device /dev/input/by-id/YOUR-KEYBOARD-event-kbd` argument. The environment
variable accepts comma-separated paths, so the same setup works under systemd.
Do not run two relay instances against one serial port.

GPIO option: install with `uv sync --project tools/voice_demo --locked --extra gpio`.
Add `--gpio-chip /dev/gpiochip0 --gpio-line 17` (replace chip/line with the actual
Pi's GPIO enumeration). The button connects that **Pi** GPIO to GND; the input
requests pull-up and 20 ms debounce, falling edge = press. Keep a selected USB
keyboard for offline keys. GPIO chip numbering and the physical button are
unverified on the installation Pi; this does not refer to the robot's GPIOs.

On macOS, install `ffmpeg` and grant its microphone access. `--audio-device :0`
selects AVFoundation audio device 0; list devices with
`ffmpeg -f avfoundation -list_devices true -i ''`. On macOS or desktop Linux,
`--input gui --ptt-key space` uses a focused Tk window for genuine key-down/up
input and local motion buttons. Python must include Tk (`python3-tk` on Debian;
a Tk-enabled Python on macOS). Losing focus discards the recording. Terminal
mode is text-only because terminals do not reliably report key releases.

## The contract and failure behaviour

`POST /prompt` accepts either `Content-Type: application/json` with
`{"text":"do a bow"}`, or a raw `audio/wav` body. Both require
`Authorization: Bearer <device-token>`. The response is exactly
`{transcript, plan, notes}`. `GET /health` also requires the token.
Bodies are limited to 1,000,000 bytes, text to 2,000 characters. HTTP errors are
401 (auth), 413 (size), 415 (format), 422 (invalid input/plan), 502 (provider),
503 (busy). The server bounds active connections and provider requests and does
not retain audio/transcripts or log headers. The Pi console shows transcript,
notes, step data and outcome, with terminal control characters escaped.

The default is **Claude planning + Deepgram through Kotoleaf**, not an implicit fake
fallback. Claude submits one `submit_plan` tool call using the plan schema below.
The server locally validates it; missing/invalid tool output gets one correction
attempt with the validator's reason. Two failures produce HTTP 422
`{error, notes}` and no plan. HTTP/provider errors get no automatic retry. The
relay displays refusal notes. Each provider call has a 30-second timeout; the
relay allows 100 seconds for transcription plus up to two planning attempts.
Offline keys continue to preempt a pending request.

Provider requests identify this application as `sesame-voice-demo/0.1.0` (Claude
and Deepgram HTTP User-Agent). HTTP errors preserve status; Claude also preserves
short numeric edge diagnostics such as `error code: 1010`, while suppressing
arbitrary provider text/JSON/HTML and credentials. Cloudflare can reject the
default Python urllib User-Agent before a request reaches the Worker.

Generate the JSON Schema directly from the current manifests/firmware:

```sh
uv run --project tools/voice_demo --locked python -m tools.voice_demo.plan
```

A plan is `{version: 1, contract: <source hash>, steps: [...]}`. Each step is:

| Type | Fields and meaning |
|---|---|
| `motion` | `name`: one finite stock sequence; wait for `OK MOTION complete` |
| `face` | `name`, `hold_ms`: named firmware face; no custom pixels |
| `pose` | `angles`: eight firmware degrees in manifest joint order; `duration_ms`: Pi interpolation time; `hold_ms`: hold after settling |
| `rest` | Play firmware `rest`, then wait for completion |

The validator rejects extra fields, unknown names, nonfinite/bool angles,
out-of-range poses, infeasible transition times, more than 32 steps, or an
estimated upper duration over 120 seconds including motion travel and holds.
`face_bitmap` is reserved for a future version and **rejected today with a
specific unsupported-firmware reason**. There is no raw-serial or code step.
Future support requires a new version/capability contract and playback adapter;
simply producing the new tag cannot reach serial.

Both server and Pi validate the entire plan. Sources are hashed, and stale
generated firmware/joint evidence prevents playback. Every custom and stock
target uses the same fitted-travel assessment as `tools/joints.py`, plus soft
limits. All 19 stock motions are read, but **walk and point are unavailable** in
this demo because their R2=100° target exceeds fitted travel 0..90°. No firmware
motion is rewritten. The remaining 17 are available; long walking/turning motions
can consume most of the two-minute budget. FACE_LIST entries without an actual
first bitmap (including the spelling `defualt`) are excluded, as in `setFace`.

The Pi opens serial through `tools/sesame_s3_console.open_device`: 115200 baud,
LF, maximum 159 bytes. It exports the device calibration read-only and rejects
a plan the device would clamp. Current firmware's `arm run` requires saved,
verified calibration; the relay reports refusal and never writes calibration.
Telemetry is **commanded position**, not physical feedback.

The local heartbeat thread uses the console's **100 ms heartbeat cadence**,
inside the firmware's **500 ms watchdog**. It runs separately from HTTP, audio
capture and playback waits. All custom interpolation/holds and stock completion
handling stay on the Pi. An absolute local lease additionally stops heartbeat
and sends `off` if playback exceeds its finite budget (plus 2 seconds for setup).
Completion, cancellation, invalid plans and serial errors send `off`; `stop`
alone would retain torque and is not the relay's release action. If serial is
lost, OFF cannot be acknowledged; heartbeat ceases and the MCU watchdog is the
remaining release mechanism. No interrupted plan resumes automatically.

New server requests are accepted only while idle and outputs are off. A missing,
slow or failed server therefore cannot keep outputs on. Offline keys work while
a request is outstanding; they invalidate the request, and its late response
cannot start motion or interrupt the new local action. Once a complete validated
plan is downloaded, playback needs no server connection. Escape cancels locally.

## Deploy the server on Cloud Run

The exhibition project `sesame-robots` sits under an organisation policy that
denies Compute Engine, so the server runs as a Cloud Run service, not a VM.
It was first deployed on **26 November 2026** in `asia-northeast1` and checked
with a typed prompt and with synthetic English and Japanese speech; see
[VALIDATION.md](VALIDATION.md).

One-time setup in the project: enable Cloud Run, Cloud Build, Artifact Registry,
Secret Manager; create the service accounts `voice-server`
(Secret Accessor on the three secrets) and `voice-build`
(Cloud Run Builder and Logs Writer; the project has no Compute Engine default
account for builds); and create the secrets `voice-device-token`,
`voice-claude-token` and `voice-stt-token` without a trailing newline. Then, from
a clean checkout of the revision to deploy:

```sh
GCP_PROJECT=sesame-robots VOICE_CLAUDE_BASE_URL=https://YOUR-WORKER-ORIGIN \
  tools/voice_demo/deploy/cloud-run.sh HEAD
```

The script stages only what the server reads (firmware, manifests, reference,
tools and the course body's leg-clearance evidence), builds
`deploy/Dockerfile`, and prints the service URL; set that URL as
`VOICE_SERVER_URL` on the Pi. Secrets are mounted from Secret Manager and never
pass through the script. The service scales to zero by default; set
`VOICE_MIN_INSTANCES=1` for the party so the first prompt does not wait for a
cold start.

The service URL is reachable from the Internet, because the organisation does
not allow public invoker bindings and the Pi has no Google identity: the
invoker check is disabled and **the device token is the only gate**. Every
route, including `/health`, answers 401 without it. Keep the token only in
Secret Manager and on the Pi, and rotate it by adding a secret version and
redeploying. The systemd unit in `deploy/` remains for running the server on a
private host instead.

### Configure Claude and Deepgram

Set these **only in the server's private environment file**:

```sh
VOICE_PROVIDER=claude
VOICE_CLAUDE_BASE_URL=https://YOUR-WORKER.YOUR-SUBDOMAIN.workers.dev
VOICE_CLAUDE_TOKEN=YOUR-WORKER-ACCESS-TOKEN
VOICE_PLAN_MODEL=claude-haiku-4-5
VOICE_STT_URL=https://kotoleaf.wandering-sky-fcce.workers.dev
VOICE_STT_TOKEN=YOUR-KOTOLEAF-ACCESS-TOKEN
```

Obtain the actual Worker URL from its deployment; the example is a placeholder.
`VOICE_CLAUDE_BASE_URL` is an HTTPS origin, optionally ending in `/v1`.
The token is the Worker's access token, **not** an Anthropic key. The request
uses only the supported non-streaming Messages subset and `x-api-key` auth.

To switch to an **Anthropic Console API key**, change
`VOICE_CLAUDE_BASE_URL=https://api.anthropic.com` and replace
`VOICE_CLAUDE_TOKEN` with that key; set `VOICE_PLAN_MODEL` to the desired available
model and restart the server. No code, relay or speech change is needed.
Application-specific variables avoid inheriting unrelated Anthropic auth settings.

For audio, `VOICE_STT_TOKEN` is required at server startup in real-provider mode.
`VOICE_STT_URL` must be an HTTPS origin and defaults to the Kotoleaf URL above.
The server POSTs WAV bytes to `/v1/listen?smart_format=true`, authenticated with
`Authorization: Token <token>`. Kotoleaf enforces Nova-3 English/Japanese
code-switching; the app sends no model or language parameters. Requests use a
30-second timeout, no redirects or environment proxies, and bounded responses.
Deepgram is the only speech adapter; `/health` reports `stt_provider: deepgram`.

Planners implement `generate(text) -> (plan, notes)`; speech adapters implement
`transcribe(wav_bytes) -> text`. The Pi never receives either provider's credentials.

The opt-in live text matrix uses configured Claude credentials and a simulated
robot; it consumes provider quota and stops immediately on HTTP/transport errors:

```sh
uv run --project tools/voice_demo --locked python -m tools.voice_demo.live_check --output /path/to/private-results.json
```

## Deploy the Pi relay

Use Raspberry Pi OS Bookworm or newer, 64-bit. Install `alsa-utils`, git, uv and
Tailscale; enroll the Pi in the same tailnet. Check out the **same revision** at
`/opt/sim2real` and create the minimal environment. Configure the
installation user's access to `dialout`, `audio`, `input` and, for GPIO, `gpio`.
The provided service uses the dedicated `sesame-voice` user; create it as above.

```sh
sudo usermod -aG dialout,audio,input sesame-voice
# If GPIO is used: sudo usermod -aG gpio sesame-voice
sudo install -d -m 750 /etc/sesame-voice
# Create /etc/sesame-voice/relay.env from deploy/relay.env.example;
# set stable USB paths, microphone, HTTPS server URL and matching device token.
# chmod 600 the environment file.
sudo install -m 644 tools/voice_demo/deploy/voice-relay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now voice-relay
journalctl -u voice-relay -f
```

The Pi unit does **not** wait for network-online; local keys remain useful during
a tailnet outage. A service restart returns to idle, outputs off, without
replaying anything. Disable the unit before using the serial console. Normal
service stop handles SIGTERM and sends `off`. Journal output includes spoken
transcripts; set the venue's local retention policy appropriately.

| Variable | Where | Default |
|---|---|---|
| `VOICE_DEVICE_TOKEN` | Both | Required for HTTP; local motions work without it |
| `VOICE_PROVIDER` | Server | `claude`; explicitly select `fake` for offline fixtures |
| `VOICE_CLAUDE_BASE_URL` | Server | `https://api.anthropic.com`; set Worker origin for gateway testing |
| `VOICE_CLAUDE_TOKEN` | Server | Required: Worker access token or Anthropic Console key |
| `VOICE_PLAN_MODEL` | Server | `claude-haiku-4-5` |
| `VOICE_STT_URL` | Server | `https://kotoleaf.wandering-sky-fcce.workers.dev` |
| `VOICE_STT_TOKEN` | Server | Required: Kotoleaf access token; fake mode needs none |
| `VOICE_SERVER_URL` | Pi | `http://127.0.0.1:8765` for development |
| `VOICE_SERIAL_PORT` | Pi | No inferred port |
| `VOICE_INPUT` | Pi | `terminal`; set `evdev` for headless Pi |
| `VOICE_INPUT_DEVICE` | Pi | Explicit Linux event device |
| `VOICE_PTT_CODE` / `VOICE_PTT_KEY` | Pi / desktop | `57` / `space` |
| `VOICE_AUDIO_DEVICE` | Relay | ALSA `default` / AVFoundation `:0` |
| `VOICE_GPIO_CHIP` / `VOICE_GPIO_LINE` | Pi | `/dev/gpiochip0` / unset |

## Still unverified on real hardware

- Pi 5 microphone recognition, ALSA device selection and noisy-room English/Japanese transcription.
- USB button press/release behaviour, GPIO pin/chip selection, Tk input and macOS microphone permissions.
- Real USB enumeration/reset timing, serial latency, installed firmware identity and saved calibration.
- Actual motion appearance, balance, contact/clearance, servo travel and OLED faces.
- Real watchdog/OE release under disconnect, process crash, I2C faults and Pi overload.
- Power delivery, grounding and USB/battery isolation. The reference notes say
  **never combine USB and battery**; this software does not establish a powered
  USB-connected full-robot installation arrangement. USB-only bench capacity is
  unmeasured. See `reference/SESAME-S3-CALIBRATION.md` and the generated interface's
  `power` section; do not infer an electrical design from this serial architecture.
- VM/Tailscale deployment, deployed Kotoleaf audio path, direct Anthropic Console-key
  access, load-dependent latency/cost, arbitrary-prompt semantic correctness,
  and unattended two-month endurance/restart behaviour. The test Worker text
  path and native PTY were exercised; see VALIDATION.md.

Give the guide [GUIDE.md](GUIDE.md). Test results and review scope are recorded in
[VALIDATION.md](VALIDATION.md).
