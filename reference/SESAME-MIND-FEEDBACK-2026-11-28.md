# Sesame mind — feedback from the exhibition table (2026-11-28)

Notes for Kotaro from Grisha, written up by Grisha's agent after a morning of
using the mind on `sesame-s3-8b2c` through the Pi (`sesame-relay`). These are
suggestions, not requests: the design is yours. Nothing in `tools/` is changed
by this note.

## What we saw

Grisha said "Please do a bow." The ear heard it correctly (1.2 s), the reflex
chose `polite_bow_please` (3.3 s) and the robot played it. It did not look like
the stock `bow`, and Grisha asked why.

Reading the code, this is the design working as intended:

- `LLMReflex` leaves firmware motions out of its menu unless `use_stock`, and
  `REFLEX_SYSTEM` makes `new` the default. A spoken "bow" can never reach the
  stock bow; only the pads can.
- `polite_bow_please` is `pitch -5`, `height -5`, `surge 8`, hold, return. The
  motion space caps pitch at ±6.25°, so the best bow it can express is a small
  nod. The stock bow (`manifest/motions.yaml`) sets the hips to their ends and
  folds the front feet (`L1: 0, R1: 180, L3: 0, R3: 180 …`, then
  `L3: 90, R3: 90`), which the eight axes cannot describe.
- Of the 42 learned motions in the library that morning, 41 were `axes` or
  `axes_keys` (17 and 24) and one was `osc`. None used `keys`.

Grisha likes the split between reflex and new motion. His impression of the
designed motions so far is that they are mostly gentle sways and wiggles, and
that the designer does not really know what a motion will look like.

## Suggestions

1. **Few-shot the designer with the stock motions.** `motions.yaml` already
   holds 19 human-made motions with clear silhouettes. Showing a few of them to
   the designer as `keys` specs (bow, wave, pushup, cute, shrug), each with its
   `BUILTIN_ABOUT` line, would show it what a readable gesture looks like and
   how far the joints can really go. Today `DESIGN_SYSTEM` says to use
   `osc`/`keys` only when necessary, and the library shows it almost never does.
2. **Is the simplified space too limiting?** It keeps the robot upright, which
   matters on a table in a cafe. But a bow, a wave, a point or a pushup all need
   the body to leave that envelope on purpose. Possible middle ground: keep the
   axes for whole-body mood, and let the designer add joint keys for one or two
   limbs on top, with the same clamps the firmware already applies.
3. **Let the reflex use a stock motion when the request names it.** "Bow",
   "wave", "dance" asked for directly could map to the stock motion (the
   `use_stock` switch exists), while anything else still invents. That also
   skips the design step for the commonest requests.
4. **Rehearse in the twin, but not in the visitor's wait.** Running a candidate
   on `--host sim` before the real robot would tell the designer whether the
   body actually moved, tipped or barely changed, and it could revise once.
   That costs time, so it may fit better in the idle time the mind already uses
   to ruminate: play the first design at once, rehearse and improve it
   afterwards, and store the better version for next time.
5. **Make "thinking" visible for the whole wait.** `handle()` already cues the
   `thinking` face when text arrives, which is the right idea. Two things
   weaken it for an audience: the wait is 3–5 s (reflex) and longer when a new
   motion is designed, and the firmware draws a status strip over the top of
   the face. Worth checking on the real display that the thinking face stays
   until the motion starts. After a stock motion the firmware leaves that
   motion's face up (the bow face read as "sad" to Grisha); returning to `idle`
   afterwards would help.

## Things changed on the Pi and robot you should know about

All at Grisha's request, on 27–28 November. Each is reversible.

- **Speech-to-text now goes to Deepgram.** `/usr/local/bin/whisper-cli` is a
  small stand-in (`/usr/local/bin/sesame-stt`) that takes the same arguments,
  sends the WAV to the exhibition's voice server and prints the transcript. If
  that fails it runs your real binary, kept as `/usr/local/bin/whisper-cli.real`.
  Your code and services were not edited or restarted. Effects: English is now
  recognised (your `-l ja` no longer applies on the cloud path), and your
  whisper flags and prompt only apply on the fallback. The ear's log line still
  says "whisper N s". Undo:
  `sudo mv /usr/local/bin/whisper-cli.real /usr/local/bin/whisper-cli`.
- **Solo play is off** (`alone: false` through `POST /config`). Grisha wants the
  robot to move only when spoken to.
- **Power.** The robot runs from a bench adapter on the battery input. We saw a
  real brownout reset during solo play at 7.34 V (uptime went 10 s → 3 s during
  a `wave`, `reset=brownout`). Grisha raised the adapter to 9 V; 100 s of
  back-to-back motions at ×1.5 then ran with no reset. Note that the mind prints
  "(robot was reset; arming again)" whenever it finds the robot off, including
  after an `off` command, so those lines over-count resets.
- **The Pi moved to the Henkaku Center tailnet** and is now `sesame-relay`. SSH
  as `sesame` works for tailnet members with the shared password; Raspberry Pi
  Connect is also set up for remote desktop.

— mochi-the-kitty · anthropic/claude-fable-5-2 · ses_f2bf92614ffes1a409FbNU9Rmj
