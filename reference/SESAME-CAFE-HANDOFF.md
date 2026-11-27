# Sesame at the café: guest page, pads and thought log (handoff, 2026-11-27)

This session turned the Sesame mind into something visitors can use without
help: a public page where anyone talks to the robot by voice or text, taps pads
to replay movements, and reads what the robot was thinking. It also made the
robot join the café Wi-Fi and the mind run on its own. The voice body and the
earlier mind work are in `reference/VOICE-BODY-HANDOFF.md` and
`reference/SESAME-MIND.md`; this note covers what was added on top.

## State at a glance (2026-11-27)

| | State |
|---|---|
| Public page | `https://kotaromacbook-air.taile70e.ts.net/sesame/` on the Tailscale Funnel of profile `gomakotaro17@gmail.com`. **Down right now**: the Mac's Tailscale was switched to the `wizard-of-oz@henkaku.center` profile, whose serve config is empty. `tailscale switch gomakotaro17@gmail.com` should bring it back (not done by the agent; the switch may be intentional). |
| Mind on the Mac | Running under launchd (`com.sesame.mind`), admin page `http://localhost:8765/`, guest port `127.0.0.1:8766`. Reflex: Claude Haiku 5.5; designer: Claude Opus 5.5 via the `ant auth login` profile. |
| Robot | `feat/s3-mind-chat` @95990da flashed (multi-network Wi-Fi). `fb9371f` (thought log embedded in the robot page) is built and pushed but **not flashed**. |
| Power | The battery is low or flat: the robot resets whenever the servos move, and the last check timed out. On USB alone the servos get no power. Charge the 7.4 V pack before the next demo. |
| Learned movements | 16 designs in `.sesame-mind/library.json` (gitignored). |

## Where things are

| Branch (remote `fork` = memorist17/sim2real) | Head | Contents |
|---|---|---|
| `feat/sesame-mind` | `6007f8b` | PC mind, guest page, launchd agent, tests, docs |
| `feat/s3-mind-chat` (worktree `../sim2real-s3-mind-chat`) | `fb9371f` | robot firmware |

| Piece | File |
|---|---|
| Guest page (talk, status, pads, thought log, ja/en) | `tools/sesame_thoughts.html`, read on every request |
| Guest server, pads, trace, status, rate limits | `tools/sesame_mind.py` (`serve_guest`, `Gate`, `motions`, `play_request`, `trace`, `curve`, `latest`) |
| launchd installer | `tools/sesame_mind_agent.py` |
| Wi-Fi list and quoted SSIDs | `firmware/sesame-s3/controller.cpp`, `command_line.h` (firmware branch) |

## What changed and why

**Credentials stay on the PC.** The robot page no longer sends API keys; the
mind takes `ANTHROPIC_API_KEY` or the `ant auth login` profile (`ant` 2.14.0 is
installed from `anthropics/tap/ant`) and reports which one as `claude_auth`.

**The mind runs by itself.** `python3 tools/sesame_mind_agent.py install`
registers a launchd agent (start at login, restart on exit). The microphone
opens only while 声で動く is on (`--mic-on-demand`). A SIGTERM sends `off` to the
robot. The agent runs whatever is checked out in this working tree.

**Every remark gets a body answer.** The LLM reflex no longer offers the stock
motions. It designs a new movement by default and replays a learned one only when
its meaning is nearly the same (おいしい！ → yummy_wiggle). Designed motions have
per-key eases (`in` wind-up, `out` settle, `inout`) and a spoken tempo (速く ×1.5,
ゆっくり ×0.5); intensity sets the size. Every designed motion ends with
`motion stand`. The reflex and designer return a short `why`, written in the
language they hear.

**Visitors get one page.** `tools/sesame_thoughts.html` is served at `/` on the
guest port and at `/thoughts` on the admin port:

- a large talk button using the browser's speech recognition (needs HTTPS; "ずっと
  聞く" keeps listening for a phone left by the robot) and a text box;
- a status line in large type: fine / waiting / battery may be low / can't reach
  the robot / can't reach the PC, from `GET /latest` (`robot` = the spine's last
  result);
- pads: learned movements (coloured, newest first) and the 19 stock ones,
  played at once with speed and size knobs (`POST /play`; no model call);
- the thought log as cards: what was heard, reflex choice and reason, the
  designer's reason, and the movement as small-multiple charts with eases marked;
- Japanese and English on one URL; the toggle is remembered per phone.

Guests can only reach `/`, `/thoughts`, `/trace`, `/latest`, `/motions`, `/say`,
`/play` and `/stand`. `/say` is limited to one message per 4 s, 200 characters
and 300 per day (`--guest-daily`); pads to one press per 0.4 s.

**The robot roams between networks.** `wifi join "FabCafe FreeWi-Fi"` (quotes
for spaces; open network) is saved next to `kotaronowifi`; up to five networks
are kept, and after 8 s without the current one the robot scans and joins the
strongest known one. The ESP32-S3 is 2.4 GHz only, so the café's 5 GHz SSID
cannot be used. At FabCafe the robot got 192.168.100.36 and the Mac .37.

**The mind copes with a sagging supply.** A robot that reset comes back
disarmed; the mind re-arms it once and retries. A second reset within 30 s means
the supply sags when the servos pull, so it stops re-arming and the page shows
"電池が少ないかも".

**Phones on mobile data keep up.** The page polls `/latest` (a few bytes) and
fetches the gzip'd log only when it changed: 195 kB → 26 kB, `/latest` in
0.15 s through the Funnel.

## Running

```sh
python3 tools/sesame_mind_agent.py install | restart | status | log | uninstall
# after code changes to tools/sesame_mind.py: restart. HTML edits: just reload the page.

tailscale funnel --bg --set-path /sesame http://127.0.0.1:8766   # publish (profile gomakotaro17)
tailscale funnel --https=443 --set-path /sesame off               # unpublish; leaves /mp3 /nuro /moba
```

The robot's own page stays the admin console (calibration, settings, voice
body). From a Mac use `http://sesame-s3-8b2c.local`; Android browsers cannot
resolve `.local`, so phones need the IP (shown on the mind page and the OLED).

## Verified

- 39 tests in `tests/test_sesame_mind.py` (guest routes and limits, pads,
  status, gzip, re-arming, eases and tempo, trace curves, settings without keys).
- The public URL through the Funnel's public ingress: page 200, `/trace` 200,
  `/config` 404 (2026-11-26, before the profile switch).
- Claude on real calls: 寒いね → a new `shiver_cold`; English remarks get English
  reasons; 溜めて跳ねて → 900 ms `in`, 150 ms `linear`, `out`, `inout`.
- Robot on FabCafe Wi-Fi, reachable by IP and `.local` from the Mac; calibration
  kept through two flashes (`saved=1`, manifest `f7382b66d6f7a844`).
- Page layout checked as rendered images (headless Chrome is not installed).

## Not verified

1. Speech recognition on a real phone. Vivaldi may not support it; use Chrome.
2. Any learned movement on the real robot: every attempt hit the low battery.
3. Roaming between the café Wi-Fi and the hotspot.
4. The redesigned page in a phone browser; the display font (Dela Gothic One)
   loads from Google Fonts and falls back to the system font.
5. `fb9371f` on the robot.

## Open items

- Charge the battery, then try pads and voice with the robot on the floor.
- Flash `fb9371f` (USB, battery switched off): `uv run python tools/sesame_s3.py --port /dev/cu.usbmodemXXXX flash` in the firmware worktree.
- Switch Tailscale back to `gomakotaro17@gmail.com` when the public page should
  be up, then make the QR code for `https://kotaromacbook-air.taile70e.ts.net/sesame/`.
- The whisper model at `~/models/whisper/ggml-small.bin` is incomplete
  (367 MB of about 488 MB); resume with `curl -L -C - -o …` and restart the agent.
  Until then whisper crashes on each utterance (harmless; the agent passes the
  model because the file exists).
- The library only grows. Consider pruning or merging near-duplicates.
- The reuse judgement is lenient (踊って → pirouette); tighten the prompt if
  visitors want more new movements.

## Henkaku tailnet access (2026-11-27)

The guest page is also published **on the Funnel of the Mac's
`wizard-of-oz@henkaku.center` profile** (public, by the user's choice on
2026-11-27; first it was tailnet-only `serve`):

```sh
tailscale funnel --bg --set-path /sesame http://127.0.0.1:8766  # https://kotaromacbook-air-1.tail08c5d0.ts.net/sesame/
tailscale funnel --https=443 --set-path /sesame off             # undo
```

Checked through the public ingress (103.84.155.217): page 200, `/latest` 200,
`/config` 404.
Each Tailscale profile keeps its own serve config, so switching back to
`gomakotaro17@gmail.com` brings the public Funnel back and this URL goes down.

Hosting the mind on the `sesame-relay` Pi (Raspberry Pi 5 on the same tailnet)
is possible but not done. The mind must reach the robot over HTTP and the robot
cannot join Tailscale, so the Pi has to be on the robot's Wi-Fi. At the check it
was on another network (`118.238.250.233`), and Tailscale SSH no longer
answered (`Permission denied (publickey,password)`, no SSH host keys advertised).

## The Pi as a remote ear (2026-11-27)

Decision: the mind and the robot stay on the Mac and `kotaronowifi`; the
`sesame-relay` Pi (Henkaku tailnet, at FabCafe on `FabCafeMTRL`) is only a
microphone. `tools/sesame_ear.py` cuts speech from its USB mic (JMTek, ALSA
`plughw:CARD=Device,DEV=0`), transcribes it with whisper.cpp on the Pi and posts
the text to the mind's admin `/say` at `http://100.112.210.74:8765` (the Mac's
tailnet IP; the Pi runs with `CorpDNS: false`, so MagicDNS names do not resolve).

With the PCsensor FootSwitch plugged in (`--pedal auto`, the default) the ear is
push-to-talk: hold the pedal, speak, release. All three of the pedal's input
devices count (keyboard, mouse, vendor), so its key mapping does not matter; the
ear grabs them so the key does not type into the console. Without a pedal it cuts
speech by loudness. Update the Pi with `git pull` and kill the ear process
(`systemctl` restarts it; `sudo systemctl restart sesame-ear` also works).

Measured from the Pi: the mind answers in 0.04 s; the mic idles at RMS ~200, so
the ear's threshold is 450. Not yet done (needs `sudo` and downloads on the Pi,
which the agent was not allowed to run): `cmake`, building `whisper-cli`, the
model `~/models/whisper/ggml-small-q5_1.bin`, installing the unit
(`python tools/sesame_ear.py --unit | sudo tee /etc/systemd/system/sesame-ear.service`),
and stopping the Pi's older `sesame-mind.service` (a second mind that cannot
reach the robot from FabCafeMTRL).

## Lag (2026-11-27)

Measured on the Pi 5 (small q5_1) and the Mac mind on the phone hotspot:

| Step | Before | After |
|---|---|---|
| whisper on the Pi | 9.7 s | ~1.5 s: greedy, no fallback, `-ac` cut to the clip (≥256; tighter repeats words), short prompt |
| reflex (Haiku 5.5) | 1.4–6 s | unchanged (network-bound) |
| new motion design | Opus 5–8 s, after the reflex | in parallel with the reflex; designer set to Sonnet 5.5 (4–8 s) on the settings page |

Feedback while waiting: pedal down → OLED `surprised`, pedal up → `thinking`
(through the mind's admin `POST /cue`), the mind shows `thinking` on every remark
and `idle` after a designed motion or none. Faces take 0.1–0.4 s and move no servo.

## Pitfalls

- The page is public: anyone with the URL can move the robot, and the thought
  log shows every remark, including ones typed on the admin page. Someone
  already asked for the owner's personal data; the robot only answers with its
  body and nothing private is served, but the text is visible to all.
- Other sessions commit to `feat/sesame-mind` (3D-print files under `bambu/`);
  stage only your own files, and pushes may upload their LFS objects.
- `uv run pytest … | tail -1 && git commit` commits even when tests fail; check
  the exit code of pytest itself.
- Funnel paths share one config with the user's other apps (`/mp3`, `/nuro`,
  `/moba`); add or remove only `/sesame`.
- `~/Library` is off limits to agents (CLAUDE.md); the user ran `install`.
- `curl` is not permitted for agents; downloads need the user.
