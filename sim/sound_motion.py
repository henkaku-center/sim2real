"""Sound-driven motion: three controllers, one sound, side by side in MuJoCo.

The question is whether sound can drive Sesame into motion that reads as
behaviour (gaits, stillness, entrainment, hesitation) rather than writhing.
All three controllers emit 50 Hz servo frames from the same audio features:

    osc  the current sesame_mind spine: a loud onset starts a 2 s `osc` spec
         (shared hz, per-joint amplitude and phase), intensity from loudness.
         Phases here are random per library entry (seeded), the worst case of
         an uncoordinated spec; nothing listens back to the body or the beat.
    cpg  four coupled leg oscillators. Coupling pulls the legs into a
         symmetric gait (trot or side-to-side sway), onsets reset the phase
         and adapt the frequency (entrainment with a tempo memory), and the
         onset rate sets the amplitude, so silence decays to standing still.
    dep  differential extrinsic plasticity (Der & Martius 2015, simplified):
         joint-velocity correlations rewrite a linear controller, sound raises
         its gain and kicks it. Uses measured joint angles, which the real
         robot does not have.

Metrics per audio section (all numeric, fixed seed, deterministic):

    still       fraction of frames with every joint slower than 0.3 rad/s
    periodic    mean autocorrelation peak of joint angles at lags 0.25-2 s
    flatness    spectral flatness of joint velocities (1 = noise, "writhing")
    motion_hz   dominant joint-motion frequency
    beat_plv    phase locking of the motion to the onsets (1 = locked)
    contact_per autocorrelation peak of the paw contact pattern
    travel_m    torso displacement in the floor plane
    upright     minimum cos(tilt) of the torso (< 0.3 means it fell over)

    uv run --group dev python -m sim.sound_motion                  # metrics table
    uv run --group dev python -m sim.sound_motion --video          # + out/sound_motion/compare.mp4
    uv run --group dev python -m sim.sound_motion --wav song.wav --video
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from sim.build_mjcf import MODEL_PATH
from sim.manifest import Manifest, load_manifest

FRAME_HZ = 50  # servo frame rate (PCA9685 at 50 Hz)
SR = 16000
SETTLE_S = 1.5  # stand up before the audio starts
OUT_DIR = Path(__file__).parent.parent / "out" / "sound_motion"
MODES = ("osc", "cpg", "dep")

# Leg layout: forward sweep sign of the hip (+ outward = front legs forward).
LEGS = (  # (leg, hip, foot, forward_sign)
    ("front_right", "R1", "R3", 1.0),
    ("front_left", "L1", "L3", 1.0),
    ("back_right", "R2", "R4", -1.0),
    ("back_left", "L2", "L4", -1.0),
)
GAITS = {  # leg phase offsets (rad) in LEGS order
    "trot": np.array([0.0, math.pi, math.pi, 0.0]),  # diagonals together
    "sway": np.array([0.0, math.pi, 0.0, math.pi]),  # right side vs left side
}


# ---------------------------------------------------------------- audio


@dataclass
class Section:
    start: float
    end: float
    label: str
    bpm: float | None = None


def test_signal(seed: int = 0) -> tuple[np.ndarray, list[Section]]:
    """Silence, 120 BPM clicks, 90 BPM clicks, irregular bursts, silence."""
    rng = np.random.default_rng(seed)
    sections = [
        Section(0, 4, "silence"),
        Section(4, 12, "beat 120", 120.0),
        Section(12, 20, "beat 90", 90.0),
        Section(20, 26, "irregular"),
        Section(26, 32, "after"),
    ]
    audio = 0.002 * rng.standard_normal(int(sections[-1].end * SR))
    t = np.arange(int(0.06 * SR)) / SR
    click = np.sin(2 * math.pi * 880 * t) * np.exp(-t / 0.012)
    burst = rng.standard_normal(len(t)) * np.exp(-t / 0.02)

    def put(at: float, sound: np.ndarray, gain: float) -> None:
        i = int(at * SR)
        n = min(len(sound), len(audio) - i)
        audio[i:i + n] += gain * sound[:n]

    for s in sections:
        if s.bpm:
            for at in np.arange(s.start, s.end, 60.0 / s.bpm):
                put(at, click, 0.6)
        elif s.label == "irregular":
            at = s.start
            while True:
                at += rng.exponential(0.45) + 0.12
                if at >= s.end:
                    break
                put(at, burst, rng.uniform(0.2, 0.6))
    return audio.astype(np.float32), sections


def load_wav(path: Path) -> np.ndarray:
    """Mono float audio resampled to SR (16-bit PCM WAV)."""
    with wave.open(str(path)) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        if w.getsampwidth() != 2:
            raise ValueError("expected 16-bit PCM WAV")
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        x = np.interp(np.arange(0, len(x) / sr, 1 / SR), np.arange(len(x)) / sr, x)
    return x.astype(np.float32)


def write_wav(path: Path, audio: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


@dataclass
class Features:
    env: np.ndarray  # loudness per frame, 0..1
    onset: np.ndarray  # onset strength per frame, 0 where there is none

    @property
    def onset_times(self) -> np.ndarray:
        return np.flatnonzero(self.onset) / FRAME_HZ


def features(audio: np.ndarray, refractory_s: float = 0.15) -> Features:
    """Frame-rate loudness and onsets (positive log-energy flux peaks)."""
    hop = SR // FRAME_HZ
    n = len(audio) // hop
    frames = audio[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    ref = max(np.percentile(rms, 99), 1e-6)
    env = np.clip(rms / ref, 0, 1)
    loud = np.log(rms + 1e-4)
    flux = np.maximum(np.diff(loud, prepend=loud[0]), 0)
    onset = np.zeros(n)
    last = -1e9
    for i in range(1, n - 1):
        if flux[i] > 1.0 and env[i] > 0.1 and flux[i] >= flux[i + 1] and i - last >= refractory_s * FRAME_HZ:
            onset[i] = env[i]
            last = i
    return Features(env, onset)


# ---------------------------------------------------------------- controllers


class Controller:
    """Maps one frame of audio features (+ measured joints) to joint targets."""

    def __init__(self, m: Manifest, seed: int = 0):
        self.m = m
        self.rng = np.random.default_rng(seed)
        self.idx = {j.name: i for i, j in enumerate(m.joints)}
        stand = m.pose_internal("stand")
        self.base = np.array([stand[j.name] for j in m.joints])
        rng = [m.internal_range(j) for j in m.joints]
        self.lo = np.array([r[0] for r in rng])
        self.hi = np.array([r[1] for r in rng])

    def __call__(self, k: int, env: float, onset: float, q: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def clamp(self, q: np.ndarray) -> np.ndarray:
        return np.clip(q, self.lo, self.hi)


class OscController(Controller):
    """Onset-triggered osc specs, as the sesame_mind spine plays them."""

    def __init__(self, m: Manifest, seed: int = 0, library: int = 3, hz: float = 1.5, seconds: float = 2.0):
        super().__init__(m, seed)
        self.hz, self.seconds = hz, seconds
        self.library = [
            (self.rng.uniform(10, 30, 8), self.rng.uniform(0, 1, 8)) for _ in range(library)
        ]
        self.playing: tuple[int, int, float] | None = None  # (spec, start frame, scale)

    def __call__(self, k, env, onset, q):
        if onset > 0:  # a newer moment interrupts the playing motion
            spec = int(self.rng.integers(len(self.library)))
            self.playing = (spec, k, 0.3 + 0.7 * onset)
        out = self.base.copy()
        if self.playing:
            spec, start, scale = self.playing
            t = (k - start) / FRAME_HZ
            if t > self.seconds:
                self.playing = None
            else:
                amp, phase = self.library[spec]
                out += scale * np.radians(amp * np.sin(2 * math.pi * (self.hz * t + phase)))
        return self.clamp(out)


class CpgController(Controller):
    """Coupled leg oscillators entrained by onsets, amplitude from onset rate."""

    def __init__(self, m: Manifest, seed: int = 0, hz: float = 1.6, coupling: float = 6.0,
                 kick: float = 0.5, adapt: float = 0.5, hip_deg: float = 22.0, foot_deg: float = 40.0):
        super().__init__(m, seed)
        self.omega = 2 * math.pi * hz
        self.coupling, self.kick, self.adapt = coupling, kick, adapt
        self.hip, self.foot = math.radians(hip_deg), math.radians(foot_deg)
        self.phi = self.rng.uniform(0, 2 * math.pi, 4)
        self.r = 0.0  # amplitude 0..1
        self.rate = 0.0  # low-passed onsets per second
        self.gait = "sway"
        self.log: list[tuple[float, float, str]] = []  # (omega_hz, r, gait)

    def __call__(self, k, env, onset, q):
        dt = 1 / FRAME_HZ
        self.rate += dt / 2.5 * (FRAME_HZ * (onset > 0) - self.rate)
        if self.rate > 1.85:
            self.gait = "trot"
        elif self.rate < 1.65:
            self.gait = "sway"
        target_r = min(1.0, self.rate / 1.5)
        self.r += dt / 0.6 * (target_r - self.r)
        rel = self.advance(dt)
        if onset > 0:  # a PLL: the phase error at the beat corrects phase and frequency
            lead = (rel[0] + math.pi) % (2 * math.pi) - math.pi  # front right: offset 0 in every gait
            self.phi -= self.kick * lead
            self.omega -= self.adapt * lead
            self.omega = float(np.clip(self.omega, 2 * math.pi * 0.7, 2 * math.pi * 3.0))
        self.phi %= 2 * math.pi
        self.log.append((self.omega / (2 * math.pi), self.r, self.gait))
        return self.pose()

    def advance(self, dt: float) -> np.ndarray:
        """Step the coupled phases toward the current gait; returns phases relative to it."""
        rel = self.phi - GAITS[self.gait]
        dphi = self.omega + self.coupling * np.sin(rel[None, :] - rel[:, None]).mean(axis=1)
        self.phi = self.phi + dt * dphi
        return rel

    def pose(self) -> np.ndarray:
        """Joint targets: hips sweep with cos(phase), paws lift while sin(phase) > 0."""
        out = self.base.copy()
        for i, (_, hip, foot, fwd) in enumerate(LEGS):
            out[self.idx[hip]] -= self.r * self.hip * fwd * math.cos(self.phi[i])
            out[self.idx[foot]] -= self.r * self.foot * max(0.0, math.sin(self.phi[i]))
        return self.clamp(out)


class DepController(Controller):
    """Simplified DEP: C <- normalised <dx_t dx_{t-1}^T>, y = tanh(kappa C x + h)."""

    def __init__(self, m: Manifest, seed: int = 0, kappa_base: float = 0.6, kappa_sound: float = 2.0,
                 tau: float = 0.5, hip_deg: float = 30.0, foot_deg: float = 45.0):
        super().__init__(m, seed)
        self.kappa_base, self.kappa_sound, self.tau = kappa_base, kappa_sound, tau
        self.scale = np.array([math.radians(hip_deg if j.role == "hip" else foot_deg) for j in m.joints])
        self.C = np.eye(8) + 0.05 * self.rng.standard_normal((8, 8))
        self.x_prev = np.zeros(8)
        self.dx_prev = np.zeros(8)
        self.arousal = 0.0

    def __call__(self, k, env, onset, q):
        dt = 1 / FRAME_HZ
        self.arousal += dt / 1.0 * (env - self.arousal)
        x = (q - self.base) / self.scale
        dx = x - self.x_prev
        self.C += dt / self.tau * (-self.C + np.outer(dx, self.dx_prev) * FRAME_HZ**2)
        self.x_prev, self.dx_prev = x, dx
        norm = np.linalg.norm(self.C) + 1e-6
        kappa = self.kappa_base + self.kappa_sound * self.arousal
        h = onset * 0.8 * self.rng.standard_normal(8)
        y = np.tanh(kappa * (self.C / norm * math.sqrt(8)) @ x + h)
        return self.clamp(self.base + y * self.scale)


CONTROLLERS = {"osc": OscController, "cpg": CpgController, "dep": DepController}


# ---------------------------------------------------------------- simulation


def physics_model():
    """models/sesame.xml without the LFS visual meshes, on a checker floor."""
    import mujoco

    spec = mujoco.MjSpec.from_file(str(MODEL_PATH))
    for g in list(spec.geoms):
        if g.type == mujoco.mjtGeom.mjGEOM_MESH:
            spec.delete(g)
    for mesh in list(spec.meshes):
        spec.delete(mesh)
    spec.add_texture(name="grid", type=mujoco.mjtTexture.mjTEXTURE_2D,
                     builtin=mujoco.mjtBuiltin.mjBUILTIN_CHECKER,
                     rgb1=[0.82, 0.82, 0.82], rgb2=[0.72, 0.72, 0.72], width=256, height=256)
    mat = spec.add_material(name="grid", texrepeat=[40, 40])
    mat.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = "grid"
    floor = next(g for g in spec.geoms if g.name == "floor")
    floor.material = "grid"
    floor.rgba = [1, 1, 1, 1]
    return spec.compile()


@dataclass
class Run:
    mode: str
    q: np.ndarray  # measured joints per frame, manifest order
    qvel: np.ndarray
    target: np.ndarray
    torso: np.ndarray  # xyz per frame
    upright: np.ndarray  # cos(tilt) per frame
    contact: np.ndarray  # paw on floor per frame, LEGS order
    log: list = field(default_factory=list)


class Sim:
    """One MuJoCo world driven by one controller at FRAME_HZ."""

    def __init__(self, mode: str, m: Manifest, seed: int = 0, model=None, ctl: Controller | None = None):
        import mujoco

        self.mj = mujoco
        self.mode = mode
        self.model = model or physics_model()
        self.data = mujoco.MjData(self.model)
        self.ctl = ctl or CONTROLLERS[mode](m, seed)
        jnt = self.model.actuator_trnid[:, 0]
        self.qadr = self.model.jnt_qposadr[jnt]
        self.vadr = self.model.jnt_dofadr[jnt]
        self.substeps = round(1 / FRAME_HZ / self.model.opt.timestep)
        name = lambda n: mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, n)  # noqa: E731
        self.floor = name("floor")
        self.paws = [name(f"{leg}_lower_geom") for leg, *_ in LEGS]
        self.data.ctrl[:] = self.ctl.base
        for _ in range(int(SETTLE_S / self.model.opt.timestep)):
            mujoco.mj_step(self.model, self.data)
        self.rec: dict[str, list] = {k: [] for k in ("q", "qvel", "target", "torso", "upright", "contact")}

    def step(self, k: int, env: float, onset: float) -> None:
        d = self.data
        q = d.qpos[self.qadr].copy()
        target = self.ctl(k, env, onset, q)
        d.ctrl[:] = target
        for _ in range(self.substeps):
            self.mj.mj_step(self.model, d)
        touching = set()
        for c in d.contact[: d.ncon]:
            if self.floor in (c.geom1, c.geom2):
                touching.add(c.geom1 + c.geom2 - self.floor)
        w, x, y, _ = d.qpos[3:7]
        self.rec["q"].append(d.qpos[self.qadr].copy())
        self.rec["qvel"].append(d.qvel[self.vadr].copy())
        self.rec["target"].append(target)
        self.rec["torso"].append(d.qpos[:3].copy())
        self.rec["upright"].append(1 - 2 * (x * x + y * y))
        self.rec["contact"].append([p in touching for p in self.paws])

    def result(self) -> Run:
        r = {k: np.array(v, dtype=float) for k, v in self.rec.items()}
        return Run(self.mode, log=getattr(self.ctl, "log", []), **r)


# ---------------------------------------------------------------- metrics


def _autocorr_peak(x: np.ndarray, lo_s: float = 0.25, hi_s: float = 2.0) -> float:
    """Max normalised autocorrelation over lags lo..hi; 0 for a still signal."""
    x = x - x.mean()
    if len(x) < hi_s * FRAME_HZ * 2 or x.std() < math.radians(2):
        return 0.0
    full = np.correlate(x, x, "full")[len(x) - 1:]
    full = full / full[0]
    return float(full[int(lo_s * FRAME_HZ): int(hi_s * FRAME_HZ)].max())


def _flatness(v: np.ndarray) -> float:
    """Spectral flatness of a velocity signal over 0.2..10 Hz."""
    if v.std() < 0.05:
        return float("nan")
    p = np.abs(np.fft.rfft((v - v.mean()) * np.hanning(len(v)))) ** 2
    f = np.fft.rfftfreq(len(v), 1 / FRAME_HZ)
    p = p[(f >= 0.2) & (f <= 10)] + 1e-12
    return float(np.exp(np.log(p).mean()) / p.mean())


def _mean_finite(xs: list[float]) -> float:
    xs = [x for x in xs if np.isfinite(x)]
    return float(np.mean(xs)) if xs else float("nan")


def _dominant_hz(x: np.ndarray) -> float:
    p = np.abs(np.fft.rfft((x - x.mean()) * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / FRAME_HZ)
    band = (f >= 0.3) & (f <= 5)
    return float(f[band][p[band].argmax()])


def _plv(x: np.ndarray, onsets: np.ndarray) -> float:
    """Phase locking of signal x (band-passed at its dominant hz) to onset frames."""
    if len(onsets) < 4 or x.std() < math.radians(2):
        return 0.0
    f0 = _dominant_hz(x)
    spec = np.fft.fft(x - x.mean())
    f = np.fft.fftfreq(len(x), 1 / FRAME_HZ)
    spec[(f <= 0) | (np.abs(f - f0) > 0.4)] = 0  # analytic signal, narrow band
    phase = np.angle(np.fft.ifft(2 * spec))
    return float(abs(np.exp(1j * phase[onsets]).mean()))


def metrics(run: Run, feats: Features, sections: list[Section]) -> dict[str, dict[str, float]]:
    out = {}
    for s in sections:
        a, b = int(s.start * FRAME_HZ), min(int(s.end * FRAME_HZ), len(run.q))
        q, v, c = run.q[a:b], run.qvel[a:b], run.contact[a:b]
        pc = q - q.mean(axis=0)
        main = pc @ np.linalg.svd(pc, full_matrices=False)[2][0] if pc.std() > 1e-9 else pc[:, 0]
        onsets = np.flatnonzero(feats.onset[a:b])
        out[s.label] = {
            "still": float((np.abs(v).max(axis=1) < 0.3).mean()),
            "periodic": float(np.mean([_autocorr_peak(q[:, j]) for j in range(8)])),
            "flatness": _mean_finite([_flatness(v[:, j]) for j in range(8)]),
            "motion_hz": _dominant_hz(main) if main.std() > math.radians(2) else 0.0,
            "beat_plv": _plv(main, onsets),
            "contact_per": float(np.mean([_autocorr_peak(c[:, i] * 1.0 * math.radians(90)) for i in range(4)])),
            "travel_m": float(np.linalg.norm(run.torso[b - 1, :2] - run.torso[a, :2])),
            "upright": float(run.upright[a:b].min()),
        }
    return out


def simulate(audio: np.ndarray, sections: list[Section], modes=MODES, seed: int = 0,
             video: Path | None = None, size=(360, 270), fps: int = 25):
    """Run every mode on the same audio; optionally render them side by side."""
    m = load_manifest()
    feats = features(audio)
    model = physics_model()
    sims = [Sim(mode, m, seed, model) for mode in modes]
    caption = lambda t: next((s.label for s in sections if s.start <= t < s.end), "")  # noqa: E731
    render = Renderer(model, sims, caption, feats.onset, video, audio, size, fps) if video else None
    for k in range(len(feats.env)):
        for sim in sims:
            sim.step(k, float(feats.env[k]), float(feats.onset[k]))
        if render and k % (FRAME_HZ // fps) == 0:
            render.frame(k)
    if render:
        render.close()
    runs = [sim.result() for sim in sims]
    return feats, runs, {r.mode: metrics(r, feats, sections) for r in runs}


# ---------------------------------------------------------------- video


CAPTION_FONTS = (  # first that exists; Japanese captions need a CJK font
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


class Renderer:
    """Side-by-side panes (one per sim) piped to ffmpeg with the audio track."""

    def __init__(self, model, sims, caption, onset: np.ndarray, path: Path, audio: np.ndarray,
                 size=(360, 270), fps: int = 25, pane_text=None):
        import mujoco

        self.mj, self.sims, self.caption, self.onset, self.size = mujoco, sims, caption, onset, size
        self.pane_text = pane_text  # optional (sim, frame) -> str under each pane's label
        self.r = mujoco.Renderer(model, size[1], size[0])
        self.opt = mujoco.MjvOption()
        self.opt.geomgroup[3] = 1  # collision boxes stand in for the LFS meshes
        self.cam = mujoco.MjvCamera()
        self.cam.distance, self.cam.azimuth, self.cam.elevation = 0.42, 135, -22
        self.flash = 0
        from PIL import ImageFont

        font = next((f for f in CAPTION_FONTS if Path(f).exists()), None)
        self.font = ImageFont.truetype(font, 16) if font else ImageFont.load_default(size=16)
        path.parent.mkdir(parents=True, exist_ok=True)
        wav = path.with_suffix(".wav")
        write_wav(wav, audio)
        w, h = size[0] * len(sims), size[1] + 28
        self.ff = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-i", str(wav),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
            stdin=subprocess.PIPE)

    def frame(self, k: int) -> None:
        from PIL import Image, ImageDraw

        t = k / FRAME_HZ
        if self.onset[max(0, k - 1): k + 1].any():
            self.flash = 3
        label = self.caption(t)
        panes = []
        for sim in self.sims:
            self.cam.lookat[:] = sim.data.qpos[:3]
            self.cam.lookat[2] = 0.03
            self.r.update_scene(sim.data, self.cam, self.opt)
            img = Image.fromarray(self.r.render())
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, 0, 16 + 10 * len(sim.mode), 26), fill=(250, 250, 250))
            draw.text((8, 4), sim.mode, fill=(0, 0, 0), font=self.font)
            if self.pane_text:
                draw.text((8, self.size[1] - 24), self.pane_text(sim, k), fill=(20, 20, 20), font=self.font)
            panes.append(img)
        w, h = self.size
        canvas = Image.new("RGB", (w * len(panes), h + 28), (250, 250, 250))
        for i, img in enumerate(panes):
            canvas.paste(img, (i * w, 28))
        draw = ImageDraw.Draw(canvas)
        draw.text((8, 5), f"t={t:5.1f}s  {label}", fill=(0, 0, 0), font=self.font)
        if self.flash:
            draw.ellipse((w * len(panes) - 26, 6, w * len(panes) - 10, 22), fill=(220, 40, 40))
            self.flash -= 1
        self.ff.stdin.write(canvas.tobytes())

    def close(self) -> None:
        self.ff.stdin.close()
        self.ff.wait()
        self.r.close()


# ---------------------------------------------------------------- CLI


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wav", type=Path, help="16-bit PCM WAV instead of the built-in test signal")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--video", action="store_true", help=f"write {OUT_DIR.name}/compare.mp4")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if args.wav:
        audio = load_wav(args.wav)
        sections = [Section(0, len(audio) / SR, args.wav.stem)]
    else:
        audio, sections = test_signal(args.seed)
    feats, runs, table = simulate(audio, sections, seed=args.seed,
                                  video=args.out / "compare.mp4" if args.video else None)
    keys = ("still", "periodic", "flatness", "motion_hz", "beat_plv", "contact_per", "travel_m", "upright")
    print(f"onsets: {len(feats.onset_times)}   seed {args.seed}")
    for s in sections:
        print(f"\n[{s.label}] {s.start:g}-{s.end:g} s" + (f"  beat {s.bpm / 60:.2f} Hz" if s.bpm else ""))
        print("mode  " + "".join(f"{k:>12}" for k in keys))
        for mode, per in table.items():
            print(f"{mode:<6}" + "".join(f"{per[s.label][k]:>12.2f}" for k in keys))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "metrics.json").write_text(json.dumps(table, indent=2))
    if args.video:
        print(f"\nvideo: {args.out / 'compare.mp4'}")


if __name__ == "__main__":
    main()
