# Voice body handoff (2026-11-26)

Sesame can be moved by sound and voice through a coupled-oscillator (CPG)
body, live on the robot or on a simulated robot. Everything is reachable from
the robot's own page, `http://sesame-s3-8b2c.local`. This note covers what
exists, how to run it, what has been verified and what is still open. For the
mind itself (reflexes, designer, memory), see `reference/SESAME-MIND.md`. The
experiments behind the design are in `reference/SOUND-MOTION.md`.

## Why it is built this way

The question is whether frequency (sound) can be a source of autonomy,
emergence or cognitive-looking acts on an 8-axis quadruped, rather than only
a trigger for canned motions. A survey of LLM text-to-motion work (Alter3,
GenEM, SayTap, Language to Rewards, Humanoid-LLA, RLPF and others) settled
three choices:

- **The body is a dynamical system and language sets its parameters.** The
  LLM (for now a keyword table) chooses an intent, which sets the gait, tempo,
  amplitude and settle. It never emits per-tick angles.
- **Voice carries two meanings, routed separately.** Prosody (pitch relative
  to the speaker, rising or falling pitch, loudness, syllables) drives arousal
  directly in the body. Words arrive later, after speech recognition, and set
  the intent. Turning text itself into a waveform would carry no meaning.
- **Emergence is placed in transitions and timing, not in joint
  trajectories.** The oscillators can only settle into readable states (trot,
  sway, still), so a missed entrainment reads as hesitation, not writhing.

## What exists

| Piece | File | What it does |
|---|---|---|
| Sound experiment | `sim/sound_motion.py` | osc vs coupled CPG vs DEP on the same audio, metrics and side-by-side video |
| Voice experiment | `sim/voice_motion.py` | `ProsodyStream` (streaming F0, slope, loudness, onsets), `VoiceCpg` (prosody + words → CPG), scene scripts with macOS `say` or a synthetic voice |
| Live body | `tools/sesame_mind.py` `VoiceBody` | Microphone → prosody → 50 Hz CPG → `pose` at up to 20 Hz to the robot; chat or whisper words → intent (lasts 8 s) |
| Simulated robot | `sim/live_robot.py` `SimRobot` | MuJoCo stand-in for the S3 command interface (`arm run`, `pose`, `motion`, `off`, `stop`, `heartbeat`): 300 deg/s rate limit, soft limits, freezes after 0.5 s without commands, MJPEG view |
| Mind announcement | `tools/sesame_mind.py` `announce` + firmware `mind` command | The PC tells the robot its URL every 10 s; the robot saves it in NVS and the page adopts it |
| Robot page | `firmware/sesame-s3/web_ui.h` (branch `feat/s3-mind-chat`) | Mind panel: chat, "声で動く" (off / both / prosody only / words only), "仮想ロボット" with live sim view, 反芻, settings |

## Where things are

| | Branch (remote `fork` = memorist17/sim2real) | Head |
|---|---|---|
| PC side, sim, tests, docs | `feat/sesame-mind` | `5963612` (pushed) |
| Robot firmware | `feat/s3-mind-chat` (worktree `../sim2real-s3-mind-chat`) | `824666e` (pushed) |

`feat/s3-mind-chat` is the robot's build line (OE=GPIO18, manifest
`f7382b66d6f7a844`). **Never flash a main-based build on this robot**: its
saved calibration would be rejected.

## Device state (2026-11-26)

- Flashed `feat/s3-mind-chat` @824666e over USB. After boot: `saved=1`,
  manifest `f7382b66d6f7a844`, outputs OFF.
- `mind=http://10.248.198.140:8765` is saved in NVS and survived a USB reset.
- The robot joins the phone hotspot `kotaronowifi`. Its address that day was
  10.248.198.6 and the Mac's was .140; the subnet changes every session.
- The USB port name changes between sessions (`/dev/cu.usbmodem101`,
  `/dev/cu.usbmodem1101`). Look it up each time.

## Running

```sh
# With the robot: open http://sesame-s3-8b2c.local on the phone; the Mind URL fills in by itself
uv run --group radio --group dev python tools/sesame_mind.py --mic --mic-device :1 --serve 8765 --robot sesame-s3-8b2c.local

# Without the robot: open http://localhost:8765/ (the virtual robot appears there)
uv run --group radio --group dev python tools/sesame_mind.py --mic --mic-device :1 --serve 8765 --host sim

# Offline experiments and videos (out/ is gitignored)
uv run --group dev python -m sim.sound_motion --video
uv run --group dev python -m sim.voice_motion --video        # macOS say; --synth on any OS

uv run --group dev --group radio python -m pytest tests/test_sound_motion.py tests/test_voice_motion.py \
    tests/test_live_robot.py tests/test_sesame_mind.py
```

On this MacBook Air, avfoundation audio device `:0` is BlackHole and records
silence; `:1` is the built-in microphone. No whisper model is on disk, so
spoken words are not transcribed; type them into the chat instead
(落ち着いて, おいで, あそぼう).

## Verified

- **Simulation, sound:** the coupled CPG locks to 120 and 90 BPM (motion
  2.00 / 1.50 Hz, periodicity 0.93 / 0.82, spectral flatness 0.03). DEP is
  broadband (flatness about 0.35) and never settles. osc twitches.
- **Simulation, voice:** a shouted 落ち着いて！ settles 2.10 s after it is
  understood, with 2 rebounds; a quiet one settles in 0.62 s. A quiet おいで。
  walks at half the amplitude of the words-only run. This conflict is designed
  in (the channels act on different time scales), not emergent.
- **Live, dry and simulated:** a WAV stood in for the microphone, driving the
  virtual robot. Arousal rises on the excited voice and the gait switches
  sway → trot; about 18 poses per second are sent (the cap is 20).
- **Robot, no motion:** the firmware flashed, calibration was kept, the page
  served over Wi-Fi shows the new panel, and the announcement round trip
  works and persists in NVS.
- **Tests:** 7 sound, 7 voice, 6 simulated robot and 27 mind tests pass. The
  full suite has the same 25 failures and 9 errors as before; all of them come
  from Git LFS assets missing locally (git-lfs is not installed).

## Not verified

1. **The voice body has never moved the real robot.** Untested: 20 Hz `pose`
   over Wi-Fi next to the phone page's own polling, the firmware's 300 deg/s
   limit (fast trots will come out smaller), foot slip and battery sag.
2. Real voices in a real room. The tuning used `say` and synthetic voices.
3. The phone page in a real phone browser: auto-filled URL, sim view,
   virtual-robot switch.
4. An LLM in place of the keyword table.

## Open decisions for the user

- **API keys should stay on the PC.** The settings panel sends keys over plain
  HTTP, and with announcements any LAN device can pose as the mind. Proposed:
  remove the key fields from the page and use `ant auth login` (OAuth profile)
  or `ANTHROPIC_API_KEY` on the PC. `ClaudeBrain` currently rejects a missing
  key before the SDK can find a profile (`tools/sesame_mind.py`, "no Claude
  API key"); that check needs to go. Installing `ant` needs the user's OK.
- **Whisper model** (`ggml-small.bin`, about 466 MB) for spoken words: the
  download needs the user's OK.

## Remote operation (asked 2026-11-26, not built)

The mind URL is now persistent. "Move the robot from anywhere whenever it is
powered" needs two more things:

1. **A network the robot joins on its own.** The STA stores one network, the
   phone hotspot; with the hotspot off, the robot has only its own AP. A fixed
   home or lab Wi-Fi is needed (`wifi join` over USB). Remembering several
   networks would be a firmware change.
2. **A way in from outside.** The robot sits behind NAT and cannot be
   reached directly.

| Option | How | Needs | Fits "power only"? |
|---|---|---|---|
| A. PC relay over Tailscale | The mind proxies the robot (for example `/robot/*` → robot) and remote users reach the mind over the tailnet (Tailscale is installed on the Mac) or Funnel | A PC on the robot's LAN, always on; no firmware change | No: needs the PC |
| B. Robot dials out | The firmware keeps an outbound WebSocket/HTTPS connection to a relay (for example the user's WSL home server behind Tailscale Funnel); the relay forwards commands | Firmware change (TLS client, token), a relay service | **Yes** |

Whichever option is used, it first needs **authentication** (none exists
today) and a way to **see** the robot (there is no camera). The link-loss hold
(freeze after 500 ms, outputs OFF after 600 s held) is the only safeguard
against a dropped remote link. Suggested order: try A first (no firmware
change), then build B for real power-only operation.

## Next steps

1. With the battery in and the robot on the floor, choose "声で動く: 抑揚＋言葉"
   on the phone and talk to it. Watch the pose rate (`pose送信`) and errors in
   the status line, then compare with the virtual robot.
2. Keys stay on the PC (open decision above).
3. Whisper model, then spoken words.
4. Replace the keyword table with an LLM that picks among intents (and later
   tunes CPG parameters), using the reflex backends that already exist.
5. Remote operation, option A then B.

## Pitfalls

- Other sessions commit to `feat/sesame-mind` in parallel (for example the
  motion-space work). Stage only your own files.
- `curl` is not permitted in the agent environment; use Python `urllib` or
  `tools/sesame_remote.py`.
- `/tmp` is cleared between sessions; helper scripts there disappear.
- The MuJoCo meshes are LFS pointers, so rendering uses collision boxes, and
  MJCF-loading tests fail locally.
- An MJPEG viewer's first frame used to be stale (fixed: `SimRobot.frames()`
  yields only new frames). Keep that in mind when grabbing frames for checks.
- Audio arrives in 100 ms chunks. The body loop must stay paced on the wall
  clock (`VoiceBody._loop`); otherwise poses go out in bursts at about 5 per
  second.
