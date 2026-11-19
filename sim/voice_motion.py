"""Voice-driven motion: how it is said moves the body, what is said sets its parameters.

The same coupled-oscillator body (sim/sound_motion.py CpgController) is driven
three ways from one recording:

    prosody  only how it is said. Pitch above the speaker's reference, rising
             pitch, loudness and syllable onsets raise arousal; low or falling
             pitch lets it decay. Arousal sets amplitude, tempo and gait, and
             each syllable kicks the amplitude (animals respond to these cues
             without words: rising repeated notes excite, falling ones calm).
    words    only what is said. A keyword table stands in for the LLM and maps
             the transcript to CPG parameters (gait, amplitude, tempo, settle).
             Words arrive WORD_LATENCY_S after the utterance ends, as speech
             recognition would deliver them.
    both     words choose what (gait, tempo, settle), prosody scales how much;
             syllable kicks still reach the body while a settle command holds
             it down, so "calm down!" shouted reads differently from
             "calm down." said quietly.

Per scene metrics: amp_deg (RMS joint deviation from stand), travel_m,
settle_s (time from the scene's first understood words until the body stays
still for 0.5 s; nan if it does not within the scene), rebounds (times the
commanded amplitude climbs again by > 0.1 within 0.2 s after those words),
arousal (peak).

    uv run --group dev python -m sim.voice_motion --video     # macOS `say` voices
    uv run --group dev python -m sim.voice_motion --synth     # synthetic voice, any OS
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from sim.manifest import Manifest, load_manifest
from sim.sound_motion import (
    FRAME_HZ,
    SR,
    CpgController,
    Renderer,
    Sim,
    load_wav,
    physics_model,
)

OUT_DIR = Path(__file__).parent.parent / "out" / "voice_motion"
MODES = ("prosody", "words", "both")
WORD_LATENCY_S = 0.4
INTENT_S = 8.0  # an understood command fades after this long
F0_RANGE = (75.0, 500.0)


# ---------------------------------------------------------------- intents (the LLM's interface)


@dataclass(frozen=True)
class Intent:
    name: str
    gait: str  # "trot" | "sway"
    amp: float  # amplitude 0..1
    hz: float  # stepping frequency
    settle: float = 0.0  # 1 = hold the body down


INTENTS = {
    "settle": Intent("settle", "sway", 0.0, 1.2, settle=1.0),
    "approach": Intent("approach", "trot", 0.6, 1.6),
    "play": Intent("play", "trot", 0.9, 2.2),
}
KEYWORDS = {  # stand-in for the LLM: transcript -> intent
    "落ち着いて": "settle", "おすわり": "settle", "とまって": "settle", "calm down": "settle",
    "おいで": "approach", "come here": "approach",
    "あそぼう": "play", "おどって": "play", "let's play": "play",
}


def understand(text: str) -> Intent | None:
    return next((INTENTS[v] for k, v in KEYWORDS.items() if k in text.lower()), None)


# ---------------------------------------------------------------- prosody


@dataclass
class Prosody:
    env: np.ndarray  # loudness 0..1 per frame
    onset: np.ndarray  # syllable onset strength per frame
    f0: np.ndarray  # Hz, nan when unvoiced
    pitch_st: np.ndarray  # semitones above the reference f0, nan when unvoiced
    slope: np.ndarray  # semitones per second over the last 0.2 s, 0 when unknown


class ProsodyStream:
    """Prosody frames (FRAME_HZ) from audio fed in chunks of any size.

    The same code serves the simulator (one chunk) and the live microphone.
    Each frame is emitted one frame late: onsets and the 3-frame pitch median
    look one frame ahead. Loudness is relative to a slowly decaying running
    peak. With f0_ref=None the pitch reference follows the speaker (a slow
    average of voiced pitch), so "high" means high for this voice.
    """

    HOP, WIN = SR // FRAME_HZ, 640
    FLOOR = 0.03  # running-peak floor (RMS) so room noise does not read as loud

    def __init__(self, f0_ref: float | None = 220.0, refractory_s: float = 0.12):
        self.fixed_ref = f0_ref
        self.ref_st = 12 * math.log2(f0_ref or 200.0)  # reference pitch in semitones re 1 Hz
        self.refractory = refractory_s * FRAME_HZ
        self.buf = np.zeros(0, dtype=np.float32)
        self.j = 0  # next frame to compute
        self.peak = self.FLOOR
        self.prev_loud = None
        self.last_onset = -1e9
        self.raw: list = []  # (rms, flux, raw f0) of the last frames computed
        self.st_hist: list[float] = []
        self.window = np.hanning(self.WIN)
        self.lags = (int(SR / F0_RANGE[1]), int(SR / F0_RANGE[0]))

    @property
    def f0_ref(self) -> float:
        return 2 ** (self.ref_st / 12)

    def _raw_f0(self, seg: np.ndarray) -> float:
        if len(seg) < self.WIN or np.sqrt((seg**2).mean()) < 0.005:
            return math.nan
        w = (seg - seg.mean()) * self.window
        ac = np.correlate(w, w, "full")[self.WIN - 1:]
        ac = ac / (ac[0] + 1e-12)
        lo, hi = self.lags
        lag = lo + int(ac[lo:hi].argmax())
        return SR / lag if ac[lag] > 0.45 else math.nan

    def feed(self, audio: np.ndarray, final: bool = False) -> list[tuple[float, float, float, float, float]]:
        """Append samples; returns finished frames (env, onset, f0, pitch_st, slope)."""
        self.buf = np.concatenate([self.buf, np.asarray(audio, dtype=np.float32)])
        out = []
        while len(self.buf) >= self.WIN or (final and len(self.buf) >= self.HOP):
            hop = self.buf[: self.HOP].astype(np.float64)
            rms = float(np.sqrt((hop**2).mean()))
            loud = math.log(rms + 1e-4)
            flux = 0.0 if self.prev_loud is None else max(loud - self.prev_loud, 0.0)
            self.prev_loud = loud
            self.raw.append((rms, flux, self._raw_f0(self.buf[: self.WIN])))
            self.buf = self.buf[self.HOP:]
            self.j += 1
            if len(self.raw) >= 2:
                out.append(self._emit(len(self.raw) - 2))
            self.raw = self.raw[-3:]
        if final and self.raw:
            self.raw.append((0.0, 0.0, math.nan))
            out.append(self._emit(len(self.raw) - 2))
            self.raw = []
        return out

    def _emit(self, i: int):
        rms, flux, f0 = self.raw[i]
        nxt = self.raw[i + 1]
        prv = self.raw[i - 1] if i > 0 else (0.0, 0.0, math.nan)
        k = self.j - (len(self.raw) - i)  # frame index being emitted
        self.peak = max(self.FLOOR, self.peak * math.exp(-1 / (30 * FRAME_HZ)), rms)
        env = min(1.0, rms / self.peak)
        onset = 0.0
        if flux > 1.0 and env > 0.1 and flux >= nxt[1] and k - self.last_onset >= self.refractory:
            onset, self.last_onset = env, k
        if math.isfinite(f0):  # 3-frame median removes isolated octave jumps
            f0 = float(np.median([x if math.isfinite(x) else f0 for x in (prv[2], f0, nxt[2])]))
            st_abs = 12 * math.log2(f0)
            if self.fixed_ref is None:  # ~20 s of voiced speech to follow a new speaker
                self.ref_st += (st_abs - self.ref_st) / (20 * FRAME_HZ)
            st = st_abs - self.ref_st
        else:
            st = math.nan
        self.st_hist = (self.st_hist + [st])[-int(0.2 * FRAME_HZ) - 1:]
        y = np.array(self.st_hist)
        ok = np.isfinite(y)
        slope = float(np.polyfit(np.flatnonzero(ok) / FRAME_HZ, y[ok], 1)[0]) if ok.sum() >= 5 else 0.0
        return env, onset, f0, st, slope


def prosody(audio: np.ndarray, f0_ref: float | None = 220.0) -> Prosody:
    """Batch prosody: the live ProsodyStream run over a whole recording."""
    frames = ProsodyStream(f0_ref).feed(audio, final=True)
    env, onset, f0, st, slope = (np.array(c) for c in zip(*frames))
    return Prosody(env, onset, f0, st, slope)


def f0_track(audio: np.ndarray) -> np.ndarray:
    """Pitch per frame (Hz, nan when quiet or aperiodic)."""
    return prosody(audio).f0


# ---------------------------------------------------------------- scenes


@dataclass
class Utterance:
    start: float
    end: float
    text: str
    style: str  # "calm" | "excited"


@dataclass
class Scene:
    start: float
    end: float
    label: str


SCRIPT = (  # (label, text, style); each line is said REPEATS times
    ("come, excited", "おいで！", "excited"),
    ("calm down, calm", "落ち着いて。", "calm"),
    ("play, excited", "あそぼう！", "excited"),
    ("calm down, excited", "落ち着いて！", "excited"),
    ("come, calm", "おいで。", "calm"),
)
LEAD_S, SCENE_S, REPEATS, REPEAT_GAP_S = 2.0, 6.0, 3, 0.35


def _say(text: str, style: str, tmp: Path) -> np.ndarray:
    """macOS text-to-speech: calm = slow and low, excited = fast, high and louder."""
    rate, pitch, gain = (120, "-4", 1.0) if style == "calm" else (260, "+14", 1.8)
    aiff, wav = tmp / "u.aiff", tmp / "u.wav"
    subprocess.run(["say", "-v", "Kyoko", "-r", str(rate), "-o", str(aiff), f"[[pbas {pitch}]]{text}"], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(aiff), "-ac", "1", "-ar", str(SR),
                    "-c:a", "pcm_s16le", str(wav)], check=True)
    return np.clip(load_wav(wav) * gain, -1, 1)


def synth_utterance(style: str, seed: int = 0) -> np.ndarray:
    """A voice-like harmonic tone: calm = 3 slow syllables falling 200 -> 165 Hz,
    excited = 3 quick syllables rising 330 -> 430 Hz and louder."""
    rng = np.random.default_rng(seed)
    syl, gap, f_a, f_b, amp = (0.24, 0.08, 200, 165, 0.25) if style == "calm" else (0.13, 0.05, 330, 430, 0.6)
    n_syl = int(syl * SR)
    t = np.arange(3 * int((syl + gap) * SR)) / SR
    f = np.geomspace(f_a, f_b, len(t))
    phase = 2 * math.pi * np.cumsum(f) / SR
    tone = sum(np.sin(h * phase) / h for h in range(1, 7))
    env = np.zeros(len(t))
    for i in range(3):
        a = i * int((syl + gap) * SR)
        env[a: a + n_syl] = np.hanning(n_syl)
    return (amp * tone * env / 1.6 + 0.002 * rng.standard_normal(len(t))).astype(np.float32)


def build_scene(synth: bool = False, seed: int = 0) -> tuple[np.ndarray, list[Utterance], list[Scene]]:
    """Audio for SCRIPT plus utterance and scene timing."""
    total = LEAD_S + SCENE_S * len(SCRIPT)
    audio = 0.002 * np.random.default_rng(seed).standard_normal(int(total * SR))
    utts, scenes = [], []
    with tempfile.TemporaryDirectory() as d:
        for i, (label, text, style) in enumerate(SCRIPT):
            start = LEAD_S + i * SCENE_S
            scenes.append(Scene(start, start + SCENE_S, label))
            clip = synth_utterance(style, seed + i) if synth else _say(text, style, Path(d))
            at = start
            for _ in range(REPEATS):
                a = int(at * SR)
                audio[a: a + len(clip)] += clip
                utts.append(Utterance(at, at + len(clip) / SR, text, style))
                at += len(clip) / SR + REPEAT_GAP_S
    return audio.astype(np.float32), utts, scenes


# ---------------------------------------------------------------- controller


class VoiceCpg(CpgController):
    """The CPG body with a prosody channel, a words channel, or both.

    Live use calls hear_words() when speech is transcribed and step() once per
    prosody frame. The simulator calls the controller with precomputed prosody
    and utterance timing (pros, utts).
    """

    def __init__(self, m: Manifest, mode: str = "both", seed: int = 0,
                 pros: Prosody | None = None, utts: list[Utterance] = (), intent_s: float = INTENT_S):
        super().__init__(m, seed)
        self.mode, self.p, self.intent_s = mode, pros, intent_s
        self.hear = mode in ("prosody", "both")
        self.read = mode in ("words", "both")
        self.events = {round((u.end + WORD_LATENCY_S) * FRAME_HZ): u.text for u in utts}
        self.intent: Intent | None = None
        self.intent_left = 0  # frames until the intent expires
        self.arousal = 0.0
        self.hz = 1.2
        self.log = []  # (arousal, r, gait, intent) per frame
        self.keep_log = None  # frames to keep; live runs set a bound

    def hear_words(self, text: str) -> Intent | None:
        """Words understood: a known intent replaces the current one for intent_s."""
        it = understand(text) if self.read else None
        if it:
            self.intent, self.intent_left = it, int(self.intent_s * FRAME_HZ)
        return it

    def __call__(self, k, env, onset, q):
        if k in self.events:
            self.hear_words(self.events[k])
        return self.step(env, onset, self.p.pitch_st[k], self.p.slope[k])

    def step(self, env: float, onset: float, pitch_st: float, slope: float) -> np.ndarray:
        """One prosody frame in, joint targets (internal radians, manifest order) out."""
        dt = 1 / FRAME_HZ
        if self.intent_left > 0:
            self.intent_left -= 1
            if self.intent_left == 0:
                self.intent = None
        if self.hear:
            drive = -1.0 / 2.0 * self.arousal  # decays with a 2 s time constant
            if np.isfinite(pitch_st):
                drive += 0.9 * (pitch_st / 6 + float(np.clip(slope / 30, -1, 1)) + env)
            self.arousal = float(np.clip(self.arousal + dt * drive, 0.0, 1.5))
        a = min(self.arousal, 1.0)
        it = self.intent
        if it is None:
            target = a
        elif self.hear:
            target = it.amp * (0.5 + a) - 1.2 * it.settle
        else:
            target = it.amp
        self.r += dt / 0.4 * (float(np.clip(target, 0, 1)) - self.r)
        if self.hear and onset > 0:  # each syllable reaches the body
            self.r = min(1.0, self.r + 0.3 * a)
        if it is not None:
            self.gait = it.gait
            self.hz = it.hz * (0.85 + 0.3 * a) if self.hear else it.hz
        else:
            self.gait = "trot" if a > 0.6 else "sway" if a < 0.45 else self.gait
            self.hz = 1.2 + 0.8 * a
        self.omega += dt / 0.5 * (2 * math.pi * self.hz - self.omega)
        self.advance(dt)
        self.phi %= 2 * math.pi
        self.log.append((self.arousal, self.r, self.gait, it.name if it else "-"))
        if self.keep_log and len(self.log) > 2 * self.keep_log:
            del self.log[:-self.keep_log]
        return self.pose()


# ---------------------------------------------------------------- metrics


def scene_metrics(run, base: np.ndarray, utts: list[Utterance], scenes: list[Scene]) -> dict:
    moving = np.abs(run.qvel).max(axis=1) > 0.3
    # smooth over 0.1 s so a single zero crossing of velocity is not "still"
    w = int(0.1 * FRAME_HZ)
    moving = np.convolve(moving, np.ones(w), "same") > 0
    out = {}
    for s in scenes:
        a, b = int(s.start * FRAME_HZ), int(s.end * FRAME_HZ)
        first = min(round((u.end + WORD_LATENCY_S) * FRAME_HZ) for u in utts if s.start <= u.start < s.end)
        hold = int(0.5 * FRAME_HZ)
        settle = float("nan")
        for i in range(first, b - hold):
            if not moving[i: i + hold].any():
                settle = (i - first) / FRAME_HZ
                break
        r = np.array([lg[1] for lg in run.log[first:b]])
        lag = int(0.2 * FRAME_HZ)
        rises = (r[lag:] - r[:-lag]) > 0.1
        out[s.label] = {
            "amp_deg": float(np.degrees(np.sqrt(((run.q[a:b] - base) ** 2).mean()))),
            "travel_m": float(np.linalg.norm(run.torso[b - 1, :2] - run.torso[a, :2])),
            "settle_s": settle,
            "rebounds": int((np.diff(rises.astype(int)) == 1).sum() + rises[:1].sum()),
            "arousal": float(max(lg[0] for lg in run.log[a:b])),
        }
    return out


def simulate(audio, utts, scenes, modes=MODES, seed: int = 0, video: Path | None = None):
    m = load_manifest()
    pros = prosody(audio)
    model = physics_model()
    sims = [Sim(mode, m, seed, model, VoiceCpg(m, mode, seed, pros, utts)) for mode in modes]
    render = None
    if video:
        def caption(t):
            said = next((f"「{u.text}」({u.style})" for u in utts if u.start <= t < u.end), "")
            heard = next((u.text for u in reversed(utts) if u.end + WORD_LATENCY_S <= t), "")
            return f"voice: {said or '-'}   words understood: {heard or '-'}"

        def pane_text(sim, k):
            arousal, r, gait, intent = sim.ctl.log[k]
            return f"arousal {arousal:.2f}  amp {r:.2f}  {gait}  intent {intent}"

        render = Renderer(model, sims, caption, pros.onset, video, audio, size=(400, 300), pane_text=pane_text)
    for k in range(len(pros.env)):
        for sim in sims:
            sim.step(k, float(pros.env[k]), float(pros.onset[k]))
        if render and k % 2 == 0:
            render.frame(k)
    if render:
        render.close()
    runs = [sim.result() for sim in sims]
    base = sims[0].ctl.base
    return pros, runs, {r.mode: scene_metrics(r, base, utts, scenes) for r in runs}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--synth", action="store_true", help="synthetic voice instead of macOS `say`")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    synth = args.synth or shutil.which("say") is None
    audio, utts, scenes = build_scene(synth, args.seed)
    pros, runs, table = simulate(audio, utts, scenes, seed=args.seed,
                                 video=args.out / "compare.mp4" if args.video else None)
    voiced = np.isfinite(pros.f0)
    print(f"voice: {'synthetic' if synth else 'say -v Kyoko'}   voiced frames {voiced.sum()}")
    for u in utts[::REPEATS]:
        a, b = int(u.start * FRAME_HZ), int(u.end * FRAME_HZ)
        f = pros.f0[a:b]
        print(f"  {u.text:<8} {u.style:<8} f0 median {np.nanmedian(f):5.0f} Hz  slope {np.mean(pros.slope[a:b]):+6.1f} st/s")
    keys = ("amp_deg", "travel_m", "settle_s", "rebounds", "arousal")
    for s in scenes:
        print(f"\n[{s.label}] {s.start:g}-{s.end:g} s")
        print("mode     " + "".join(f"{k:>15}" for k in keys))
        for mode, per in table.items():
            print(f"{mode:<9}" + "".join(f"{per[s.label][k]:>15.2f}" for k in keys))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "metrics.json").write_text(json.dumps(table, indent=2, ensure_ascii=False))
    if args.video:
        print(f"\nvideo: {args.out / 'compare.mp4'}")


if __name__ == "__main__":
    main()
