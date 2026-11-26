# Sesame mind — handoff (2026-11-13)

Chat, voice and radio drive the Sesame S3. A fast reflex picks a motion, an LLM
designs new motions as small specs, a spine streams them as `pose` frames, and
the robot remembers and ruminates. This is a working skeleton: the plumbing runs
and is tested; the intelligence has not yet been tried with real keys or servos.

```text
robot page (ESP32, http://sesame-s3-8b2c.local) ── Mind panel ──▶ PC: tools/sesame_mind.py --serve 8765
mic / radio / file / stdin ───────────────────────────────────────▶   ears → reflex → library → spine ──▶ robot /cmd
                                                                       "new" → designer → library
                                                                       memory.jsonl, idle → notes.md
```

## Where things are

| What | Branch (remote `fork`) | Path |
|---|---|---|
| PC mind, tests, this note | `feat/sesame-mind` (on `feat/radio-paranoia-agent`) | `tools/sesame_mind.py`, `tests/test_sesame_mind.py` |
| Robot firmware with Mind panel | `feat/s3-mind-chat` (on `feat/s3-power-stagger-oe18`) | `firmware/sesame-s3/web_ui.h`; local worktree `../sim2real-s3-mind-chat` |

`feat/s3-mind-chat` is a **robot-only build line** (OE=GPIO18, manifest id
`f7382b66d6f7a844`, which matches the saved calibration). Do not flash a
main-based build on this robot. To upstream the panel, port the `web_ui.h`
change onto a main-based branch.

## Current device state

- Flashed `feat/s3-mind-chat` @7f2841c on 2026-11-13 over USB. Boot after flash:
  `saved=1`, all joints verified, STA reconnected. The battery was not
  disconnected for this flash; outputs were OFF.
- The robot joins the phone hotspot `kotaronowifi` (`wifi join`, stored in NVS);
  the robot AP `Sesame-S3-8B2C` stays as fallback.
- The hotspot subnet changes between sessions (10.217.105.x, then 10.147.42.x);
  host parts stayed robot `.6`, Mac `.140`. mDNS `sesame-s3-8b2c.local`
  resolved from the Mac on 11-12 and failed once on 11-11. If an address times
  out, read the IP on the OLED (outputs OFF) or `wifi` over USB.
- USB-C powers logic only; servos need the battery (LM2596 → 5 V).

## Running

```sh
uv run --group radio python tools/sesame_mind.py --serve 8765          # configure from the robot page
uv run --group radio python tools/sesame_mind.py --text                # stdin chat, dry run
uv run --group radio python tools/sesame_mind.py --mic --whisper-model ggml-small.bin --serve 8765
```

On the robot page, enter `http://<PC LAN IP>:8765` in Mind (stored in the
phone's localStorage). Settings: reflex (keywords / Jev / LLM), LLM for the
reflex (Claude / local), designer (Claude / local / none), Claude models, Claude
and TypeSafe keys, Jev URL, local server URL and model, and "drive this robot"
(sends the robot's LAN IP to the PC, which then heartbeats, arms `run` and
stands). Settings persist in `.sesame-mind/config.json` (mode 600, gitignored);
keys are write-only. A missing key falls back to keywords with no designer and
shows the reason. A background server started by an agent stops after 2 h; run
it in a terminal for longer sessions.

Local LLMs: any OpenAI-compatible server. `llama-server` (llama.cpp 0.9.0) is
installed but there are no models on disk yet, e.g.
`llama-server -hf ggml-org/gemma-3-4b-it-GGUF` (port 8080, default local URL;
first run downloads a few GB). Ollama: `http://localhost:11434/v1`.

### Voice body (2026-11-19)

`sim/voice_motion.py` running live: the PC microphone's prosody (pitch
relative to the speaker, rising or falling pitch, loudness, syllables) drives
the CPG body, and words set its intent (`settle` / `approach` / `play`, from
the same keyword table as the simulator; an intent lasts 8 s). Pick
"声で動く" (both, prosody only, words only) in the robot page's Mind panel.
That also sets "drive this robot", so the PC arms `run` and streams `pose` at
20 Hz. The status line shows pitch, arousal, amplitude, gait, intent and the
number of frames sent. While the body is on, chat and whisper text go to the
body instead of the library motions.

```sh
uv run --group radio python tools/sesame_mind.py --mic --mic-device :1 --serve 8765    # prosody only; type words in the panel
uv run --group radio python tools/sesame_mind.py --mic --mic-device :1 --whisper-model ggml-small.bin --serve 8765
```

On the user's MacBook Air, avfoundation audio device `:0` is BlackHole (a
virtual device that records silence) and `:1` is the built-in microphone.
List devices with `ffmpeg -f avfoundation -list_devices true -i ""`.

The phone cannot be the microphone: the robot page is plain HTTP, and
browsers only allow `getUserMedia` on secure origins. `GET /body` returns
the body's state as JSON. Without `--whisper-model`, speech is not
transcribed; no whisper model is on disk yet.

The firmware with the "声で動く" panel (`feat/s3-mind-chat` @3fa6484) was
flashed on 2026-11-26. Calibration survived (`saved=1`, manifest
`f7382b66d6f7a844`), and the page served over Wi-Fi includes the panel. The
voice body has not yet driven the real robot.

### Everything on the robot page (2026-11-26)

`http://sesame-s3-8b2c.local` is the single control surface. Start the PC with
`--robot`; nobody has to type the PC address:

```sh
uv run --group radio --group dev python tools/sesame_mind.py --mic --mic-device :1 --serve 8765 --robot sesame-s3-8b2c.local
```

Every 10 s the PC checks the robot's `/status` and, if needed, sends
`mind http://<its LAN IP>:8765`. The firmware saves this in NVS (`sesame-net`
key `mind`) and reports it as `mind=` in `status`; the page adopts it as the
Mind URL. This covers hotspot address changes and robot reboots. The Mind
panel holds chat, "声で動く", the "仮想ロボット" switch (the PC drives
`--host sim`, and its live view appears on the page), 反芻 (ruminate) and the
settings. Like the rest of the mind link, it has no authentication: on an
untrusted network anyone could announce themselves as the mind, and keys typed
into the settings would go to them.

Flashed `feat/s3-mind-chat` @824666e on 2026-11-26. The robot learned
`mind=http://10.248.198.140:8765` from `--robot`, and it survived a reset.
Not yet checked in a phone browser.

### Without the robot: `--host sim` (2026-11-26)

`sim/live_robot.py` stands in for the S3's command interface. It accepts
`arm run`, `pose`, `motion`, `off`, `stop` and `heartbeat`, approaches targets
at the firmware's 300 deg/s run rate within the soft limits, and freezes when
commands stop for 0.5 s. It steps MuJoCo in real time, and the chat page
(`http://localhost:8765/`) shows it live (MJPEG at `/sim.mjpg`) next to the
"声で動く" selector and the body's status line.

```sh
uv run --group radio --group dev python tools/sesame_mind.py --mic --mic-device :1 --serve 8765 --host sim
```

The body loop ticks at 50 Hz on the wall clock and takes one prosody frame
per tick. Microphone chunks bring 5 frames at once, so before this the loop
moved in bursts and only about 5 poses per second went out. Measured with a
WAV standing in for the microphone: about 18 poses per second reach the
robot (the cap is 20).

## Design choices

- The LLM never emits per-tick angles. Specs are `osc` (per-joint sine around a
  manifest pose) or `keys` (keyframes), in internal degrees relative to `base`,
  clamped to manifest soft limits; firmware motions are library entries. A learned
  motion replays with no model call.
- Jev (TypeSafe System One) fits the reflex: Choice over library names plus
  `new`/`none`, Score for intensity, Noul for "addressed to the robot".
  It cannot design motions. No official on-device Jev exists; `local-jev`
  (third-party, wire-compatible) is the edge candidate, untested.
- Ears: a rising edge above `loud_rms` is an immediate `sound` moment (no
  model); speech is split on 600 ms silence for whisper instead of fixed 12 s chunks.
- One worker handles moments in order; a newer motion interrupts the playing one.
- Every remark gets a body answer (2026-11-26). The LLM reflex picks a stock or
  learned motion that expresses the words (stock motions now carry Japanese
  descriptions), and answers `new` when none fits, without being asked to make one;
  the designer then expresses the remark (寒いね → shiver_cold) and the library keeps
  it for instant replay. `none` is for noise and empty words (テスト). Measured
  with Claude: reflex 1.3–2.3 s (Haiku 5.5), design 3.3 s (Opus 5.5, low effort).
  A design never replaces an existing name (`dance` → `dance_2`).
  Later the same day, at the user's request, the LLM reflex stopped offering the
  stock motions at all (`LLMReflex(use_stock=False)`): it designs by default and
  replays a learned motion only when its meaning is nearly the same
  (おいしい！ → yummy_wiggle, 喉かわいたね → thirsty_sip, こんにちは → new).
  The rule reflex and Jev still see the stock motions.
- Thought log (2026-11-26): `http://<mind>:8765/thoughts` (linked from the chat
  page) shows each remark as a card: reflex (backend, time, choices offered,
  decision, intensity, tempo, why), designer (time, why) and the motion as small
  multiples (one row per axis/joint, its own unit and scale, key ends labelled
  with their ease, hover crosshair, table view). Reflex and designer now return a
  short `why`; `/trace` serves the entries with curves from `curve()`.
- Guest page (2026-11-26): with `--serve PORT` the mind also serves PORT+1 on
  localhost only (`--guest`), with just the thought log, `/trace` and `/say`
  (one message per 4 s, 200 characters). The same HTML (`tools/sesame_thoughts.html`,
  read per request, so design edits need only a reload) has a talk bar: the
  browser's speech recognition (ja-JP, "ずっと聞く" for a phone left by the robot)
  or typed text. Speech recognition needs HTTPS, so the page is published
  tailnet-only with `tailscale serve --bg --https=8443 --set-path /sesame
  http://127.0.0.1:8766` at `https://kotaromacbook-air.taile70e.ts.net:8443/sesame/`;
  the phone needs Tailscale. At the user's request the same page is also public on
  Funnel: `tailscale funnel --bg --set-path /sesame http://127.0.0.1:8766` →
  `https://kotaromacbook-air.taile70e.ts.net/sesame/` (any phone, any network; checked
  through the public ingress: page 200, /trace 200, /config 404). Public means the
  thought log, including admin chats, is readable by anyone with the URL, and the
  `--guest-daily` cap (300) bounds model spend. Undo: `tailscale funnel --https=443
  --set-path /sesame off`.
- Speed and dynamics (2026-11-26). `intensity` sizes a designed motion (0.3–1×);
  `tempo` (0.5–2, from the reflex: 速く, ゆっくり, キビキビ; the rule reflex knows
  速く/ゆっくり) rescales its time. Each key may carry `ease`: `linear`, `in`
  (wind-up), `out` (soft landing) or `inout`; the designer is told to shape
  dynamics with key lengths and eases. Firmware motions (dance, worm…) keep their
  own speed: tempo does not reach them, and the firmware's 300 deg/s limit caps
  every motion. Checked with Claude: 速く踊って → dance ×1.5, ゆっくり手を振って →
  wave ×0.5; "溜めて跳ねて、ふわっと着地" → 900 ms `in`, 150 ms `linear`, `out`, `inout`.
- The PC server answers the robot page cross-origin (`Access-Control-Allow-Origin: *`).
  No authentication: anyone on the LAN can chat, change settings or drive the
  robot. API keys no longer pass through the page (2026-11-26). Use a trusted network.

## Verified

- `tests/test_sesame_mind.py`: 18 tests (spec maths and clamping, library and
  memory persistence, rules/Jev/LLM reflex parsing, settings and key hiding,
  `/config` and CORS, ears segmentation, failure fallbacks). The full suite's
  failure set is unchanged (LFS-only MJCF assets missing locally).
- Firmware builds (83 % flash), `tests/test_s3_firmware.py` passes, page JS
  passes `node --check`, the flashed robot serves the new panel.
- Dry runs of the chat page and `/config` from the Mac.

## Not yet verified

1. Claude designing a motion (no `ANTHROPIC_API_KEY` in the agent shell).
2. Jev request/response field names: built from docs.typesafe.ai and guides as of
   2026-11; the parser tolerates renamed fields. Check with a real key.
3. Streaming `pose` frames on the real robot (needs the battery) and how 20 Hz
   frames interact with the firmware rate limit and Wi-Fi jitter (RSSI was -80 dBm).
4. The Mind panel in a real phone browser (no browser in the agent environment).
5. Any local model's quality as reflex or designer.

## Next steps

1. Enter a Claude key on the page, ask for a new motion in a dry run, inspect
   `.sesame-mind/library.json`, then switch "drive this robot" on with the battery.
2. Jev key: compare latency and choices against `llm:claude` on the same inputs
   (`memory.jsonl` logs `reflex_ms` and `by`).
3. Firmware spine: an `osc`/keyframe command expanded on the ESP32 at ≥ 50 Hz, so
   one line per motion crosses Wi-Fi.
4. Autonomy on link loss: store a few library specs and an idle routine
   (written by rumination) in NVS and play them instead of the current
   freeze-and-hold; include the tuck → stand recovery (no fall sensing).
5. Optional robot-mounted I2S mic (e.g. INMP441) for onset/loudness reflexes
   that work offline.
