# Sound-driven motion: osc vs coupled CPG vs DEP (simulation, 2026-11-13)

Question: can sound (onsets, tempo, loudness) drive Sesame's 8 joints into
motion that reads as behaviour (gait, stillness, entrainment, hesitation)
rather than writhing? `sim/sound_motion.py` runs three controllers on the
same audio in MuJoCo and scores each audio section numerically.

```sh
uv run --group dev python -m sim.sound_motion --video     # out/sound_motion/compare.mp4 (+ audio)
uv run --group dev python -m sim.sound_motion --wav x.wav --video
uv run --group dev python -m pytest tests/test_sound_motion.py
```

The model is `models/sesame.xml` without the LFS visual meshes (collision
boxes are rendered instead). Masses and servo gains are still the unmeasured
placeholders from `sim/build_mjcf.py`, so these are claims about the
controllers, not about the physical robot.

## Controllers

- **osc**: the current `tools/sesame_mind.py` spine. A loud onset starts a 2 s
  `osc` spec (shared 1.5 Hz, per-joint amplitude and phase) and a newer onset
  interrupts it. Phases are random per library entry (seeded): the worst case
  of an uncoordinated spec. An LLM-designed spec could be coordinated, but
  nothing listens back to the beat or the body.
- **cpg**: four leg oscillators coupled toward a symmetric gait (trot =
  diagonals together, sway = right side against left side). Each onset acts as
  a PLL step: the front-right phase error corrects phase (gain 0.5) and
  frequency (0.5 rad/s per rad). Stability needs `adapt · T < kick` for beat
  period T; larger gains run away. The onset rate (2.5 s low-pass) sets the
  amplitude and picks the gait (> 1.85/s trot, < 1.65/s sway).
- **dep**: simplified differential extrinsic plasticity (Der & Martius 2015).
  `C` tracks `dx_t dx_{t-1}^T`, `y = tanh(kappa C x + h)`, loudness raises
  kappa and onsets kick `h`. It reads measured joint angles, which the real
  robot does not have (the MG90S has no position output).

## Result (test signal, seed 0)

| section | metric | osc | cpg | dep |
|---|---|---|---|---|
| beat 120 (2.0 Hz) | periodic | 0.36 | **0.93** | 0.45 |
| | flatness (1 = noise) | 0.31 | **0.03** | 0.34 |
| | motion_hz | 2.00 | **2.00** | 1.75 |
| | beat_plv | 0.96* | 0.87 | 0.41 |
| beat 90 (1.5 Hz) | periodic | 0.36 | **0.82** | 0.53 |
| | motion_hz | 1.50 | **1.50** | 1.75 |
| irregular bursts | periodic | 0.26 | 0.44 | 0.49 |
| after the sound | still | 0.66 | 0.00 | 0.00 |
| | motion_hz | – | 1.83 (tempo memory) | 1.50 |

\* osc restarts its spec on every onset, so it is trivially phase-locked to the
onsets: the motion is a twitch that restarts on each beat, not entrainment.

No mode fell over (minimum torso cos(tilt) 1.00) and all three were still
before the sound started.

- **cpg** is the only mode that reads as a gait. It locks to 120 and 90 BPM,
  switches trot → sway when the tempo drops, loses periodicity on irregular
  bursts (0.44; hesitation), and after the sound keeps the learned tempo for a
  few seconds while the amplitude decays.
- **dep** is broadband at about 1.7 Hz whatever the beat (flatness about 0.35)
  and never returns to stillness: writhing, as expected without sensors.
- **osc** is uncoordinated twitching while sound continues, and goes still
  within 2 s once it stops.

`tests/test_sound_motion.py` pins these numbers: onsets, determinism, CPG
entrainment and gait switch, and DEP being broadband where CPG is tonal.

## Not verified

- No physical runs. Real MG90S lag, foot slip and Wi-Fi jitter on 50 Hz frames
  (see `reference/SESAME-MIND.md`) are untested.
- Only one synthetic signal and one seed have been scored. Real music
  (`--wav`) has not been checked.
- The parameters (coupling, PLL gains, thresholds) were tuned by hand on this
  signal.

# Voice: prosody to the body, words to the parameters (2026-11-13)

Turning text into a waveform would be an arbitrary code with no meaning for
the body. Voice carries two kinds of meaning, so `sim/voice_motion.py` routes
them separately into the same CPG body:

- **prosody** (pitch above a 220 Hz reference, rising or falling pitch,
  loudness, syllable onsets) drives arousal. Arousal sets amplitude, tempo
  and gait, and each syllable kicks the amplitude. Animals respond to these
  cues without words; for dogs, rising repeated notes excite and falling ones
  calm (McConnell 1990, from memory).
- **words** go through a keyword table that stands in for the LLM and maps
  the transcript to CPG parameters: `settle`, `approach` (trot) and `play`
  (faster trot). Words arrive 0.4 s after the utterance ends, as speech
  recognition would deliver them, so the body hears the tone before it
  understands the words.

```sh
uv run --group dev python -m sim.voice_motion --video   # macOS say -v Kyoko; out/voice_motion/compare.mp4
uv run --group dev python -m sim.voice_motion --synth   # synthetic voice, any OS (used by the tests)
```

The script says each line three times: excited おいで！, calm 落ち着いて。,
excited あそぼう！, excited 落ち着いて！, calm おいで。. The excited `say`
voice sits at about 370-420 Hz, the calm one at about 165 Hz.

| scene | metric | prosody | words | both |
|---|---|---|---|---|
| 落ち着いて。 (calm) | settle_s / rebounds | (barely moving) | 0.74 / 0 | **0.62 / 0** |
| 落ち着いて！ (excited) | settle_s / rebounds | never | 1.02 / 0 | **2.10 / 2** |
| おいで。 (calm) | amp_deg | 1.2 | 9.4 | **4.8** |
| おいで！ (excited) | amp_deg | 11.9 | 9.6 | **12.2** |

- In `both`, a shouted 落ち着いて！ is understood as `settle`, but the next
  excited syllables push the amplitude up again (two rebounds). The body
  stops about 1.5 s later than for the quiet version. Words alone settle
  either way, and prosody alone never settles.
- Words choose what to do and prosody scales how much: a quiet おいで。 walks
  at half the amplitude of the words-only run, and prosody alone barely moves
  for it.
- The conflict is designed in, not emergent. It comes from the two channels
  acting on different time scales: syllable kicks are immediate, while the
  settle command lags speech recognition and then acts on the amplitude.

`tests/test_voice_motion.py` pins these contrasts on the synthetic voice
(F0 tracking within 2 %, rising vs falling, settle and rebound ordering,
amplitude scaling).

Not verified: real human voices or microphone noise, an actual LLM in place
of the keyword table, and the real robot.
