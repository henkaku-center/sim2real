# Sesame spoken-prompt demo

Software for the Loftwork/FabCafe **AI is not magic** exhibition: setup
**1 December 2026**, party **3 December 2026**, then a two-month installation.
No robot firmware changes. Hardware and the Google Cloud VM are not commissioned
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
the Pi or VM. Runtime dependencies are **PySerial 3.5 and PyYAML 6.0.3**; GPIO
optionally adds **gpiod 2.3.0 on Linux only**. Versions/hashes are in `uv.lock`.
Development uses pytest 9.0.2. Native simulation needs `c++`; actual relay/server
deployment does not. The root repository pytest runner also discovers the tests.

```sh
uv run --project tools/voice_demo --locked python -m pytest tests/test_voice_demo.py -v
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

## Deploy the server on a Google Cloud VM

The VM has **not been provisioned**. No cloud resources or paid API requests were
created by these tests. On an authorized Debian VM, install git, Python/uv and
Tailscale, enroll it in the installation's tailnet, and restrict access to the
Pi/operator devices. Check out this tested revision at `/opt/sim2real`:

```sh
cd /opt/sim2real
uv sync --project tools/voice_demo --locked --no-dev --python /usr/bin/python3
sudo useradd --system --home /opt/sim2real --shell /usr/sbin/nologin sesame-voice
sudo install -d -m 750 /etc/sesame-voice
# Create /etc/sesame-voice/server.env from deploy/server.env.example;
# supply real values outside git, and chmod 600 the file.
sudo install -m 644 tools/voice_demo/deploy/voice-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now voice-server
sudo tailscale serve --bg http://127.0.0.1:8765
```

The service binds loopback only. Use the system Python (3.11 or newer), as shown, so it does not
depend on a managed interpreter under an operator's home directory hidden by
`ProtectHome=true`. Tailscale Serve supplies the tailnet HTTPS
address; set that address as `VOICE_SERVER_URL` on the Pi. Do not publish port
8765 to the Internet or use Tailscale Funnel. Verify authenticated `/health`
through the tailnet before changing `VOICE_PROVIDER=fake` to `openai`. The latter
uses `OPENAI_API_KEY` only from the server environment. See
[DECISION.md](DECISION.md) for the provider choice, sources and paid-test limits.

## Deploy the Pi relay

Use Raspberry Pi OS Bookworm or newer, 64-bit. Install `alsa-utils`, git, uv and
Tailscale; enroll the Pi in the same tailnet. Check out the **same revision** at
`/opt/sim2real` and create the minimal environment as above. Configure the
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
| `VOICE_PROVIDER` | Server | `openai` when `OPENAI_API_KEY` exists, otherwise `fake` |
| `OPENAI_API_KEY` | Server | None; never needed on Pi |
| `VOICE_STT_MODEL` | Server | `gpt-transcribe` |
| `VOICE_PLAN_MODEL` | Server | `gpt-6.1-terra` |
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
- VM/Tailscale deployment, real-provider credentials/model access, latency/cost,
  and unattended two-month endurance/restart behaviour.

Give the guide [GUIDE.md](GUIDE.md). Test results and review scope are recorded in
[VALIDATION.md](VALIDATION.md).
