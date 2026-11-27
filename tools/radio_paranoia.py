#!/usr/bin/env python3
"""Tinfoil-hat Sesame: radio speech becomes paranoid beliefs, beliefs become motions.

    radio ──▶ whisper ──▶ Claude (paranoid inner voice) ──▶ macro ──▶ sesame_remote

The code owns the madness curve: a suspicion level in [0, 1] decays each chunk
and rises by the model's `suspicion_delta`. Its phase (calm → suspicious →
convinced → frenzy) restricts which motions and faces the model may pick. A
frenzy is a fit: the motion runs, then the robot always tucks and stands, with
no fall detection. The v3 dome is monostable in the tuck pose (`bambu/`), so it
rolls back onto its belly from any orientation. Afterwards suspicion relapses to
RELAPSE, not zero.

Ears (each must write 16 kHz mono s16le to stdout):

    --sdr 80.0     rtl_fm wide FM on 80.0 MHz (RTL-SDR dongle + `rtl_fm`)
    --mic          default microphone through ffmpeg (a real radio next to it)
    --file x.mp3   a recording, played in real time through ffmpeg
    --text         type transcripts on stdin (no audio, no whisper)

Audio ears need whisper.cpp (`brew install whisper-cpp`) and a ggml model, e.g.
https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin; the
SDR ear needs `rtl_fm` (`brew install librtlsdr`). Claude credentials come from
ANTHROPIC_API_KEY. Without --host nothing moves: beliefs and macro lines are
printed (dry run).

    uv run --group radio python tools/radio_paranoia.py --text
    uv run --group radio python tools/radio_paranoia.py --sdr 80.0 --whisper-model ggml-small.bin
    uv run --group radio python tools/radio_paranoia.py --mic --whisper-model ggml-small.bin \\
        --host sesame-s3-xxxx.local --log paranoia.jsonl
"""
from __future__ import annotations

import argparse
import array
import json
import math
import queue
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from sesame_remote import Robot, run_lines, start_heartbeat  # noqa: E402
from sim.manifest import load_manifest  # noqa: E402

RATE = 16000
DECAY = 0.92  # per heard chunk
RELAPSE = 0.4  # suspicion right after a fit: "it is still talking to me"
DELTA = (-0.2, 0.4)
EVIDENCE = 6  # interpretations remembered on the evidence board


@dataclass(frozen=True)
class Phase:
    name: str
    floor: float
    motions: tuple[str, ...]
    faces: tuple[str, ...]


PHASES = (
    Phase("calm", 0.0, ("stand", "wave", "cute", "bow", "rest"), ("idle", "happy", "idle_blink", "sleepy")),
    Phase("suspicious", 0.25, ("turn_left", "turn_right", "walk_backward", "shrug", "point"),
          ("thinking", "confused", "talk_thinking", "surprised")),
    Phase("convinced", 0.5, ("point", "pushup", "crab", "walk", "shake"),
          ("angry", "talk_angry", "excited", "talk_excited")),
    Phase("frenzy", 0.8, ("freaky", "worm", "dance", "swim", "shake"),
          ("freaky", "talk_surprised", "angry", "dead")),
)
MOTIONS = sorted({m for p in PHASES for m in p.motions})
FACES = sorted({f for p in PHASES for f in p.faces})


def phase_of(level):
    return [p for p in PHASES if level >= p.floor][-1]


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class Step:
    phase: str
    level: float
    motion: str
    face: str
    fit: bool
    mutter: str


@dataclass
class Mind:
    level: float = 0.0
    fits: int = 0
    evidence: list[str] = field(default_factory=list)
    just_recovered: bool = False

    def update(self, decision):
        delta = clamp(float(decision["suspicion_delta"]), *DELTA)
        self.level = clamp(self.level * DECAY + delta, 0.0, 1.0)
        phase = phase_of(self.level)
        motion = decision["motion"] if decision["motion"] in phase.motions else phase.motions[0]
        face = decision["face"] if decision["face"] in phase.faces else phase.faces[0]
        self.evidence = (self.evidence + [decision["interpretation"]])[-EVIDENCE:]
        fit = phase.name == "frenzy"
        step = Step(phase.name, self.level, motion, face, fit, decision["mutter"])
        self.just_recovered = fit
        if fit:
            self.fits += 1
            self.level = RELAPSE
        return step


SYSTEM = f"""\
あなたは四足歩行ロボット「セサミ」の頭の中の声です。セサミは甲羅のようなドーム、
つまりアルミホイルの帽子をかぶっています。それでも、ラジオが自分だけに暗号を送ってくると信じています。
ラジオの断片を一つ聞くたびに、それが自分にとって何を意味するのかを解釈してください。

キャラクター:
- 天気、数字、周波数、時報、CMのジングル、言い間違いなど、どうでもいい細部に「意味」を見つける。
- 前の証拠とつなげて、勝手な物語をどんどん育てる。ただし、証拠が途切れると少し落ち着く。
- 甲羅のおかげで、転んでも必ず起き上がる。発作のあとは「帽子が守ってくれた」と思っている。
- これはコメディの登場人物です。実在の人物や団体、民族、宗教を黒幕として名指ししないでください。
  陰謀論を事実として述べることもしないでください。黒幕は「周波数」「天気図」「時報の人」のような、
  滑稽で無害なものにしてください。

出力:
- interpretation: その断片を、自分あての暗号としてどう読んだか（日本語で1〜2文）
- mutter: 体が動くときの独り言（日本語で20字以内）
- suspicion_delta: 疑いがどれだけ増えるか。-0.2から0.4の間。普通の内容なら小さい値か負の値、
  「自分あて」に聞こえるほど大きい値
- motion / face: 疑いが更新された後の段階に合うものを、次の表から選ぶ（段階は現在の疑い度×{DECAY}＋deltaで決まる）
""" + "\n".join(
    f"  - {p.name}（疑い度 {p.floor} 以上）: motion {', '.join(p.motions)} / face {', '.join(p.faces)}"
    for p in PHASES
)

SCHEMA = {
    "type": "object",
    "properties": {
        "interpretation": {"type": "string"},
        "mutter": {"type": "string"},
        "suspicion_delta": {"type": "number"},
        "motion": {"type": "string", "enum": MOTIONS},
        "face": {"type": "string", "enum": FACES},
    },
    "required": ["interpretation", "mutter", "suspicion_delta", "motion", "face"],
    "additionalProperties": False,
}


def prompt(mind, transcript):
    board = "\n".join(f"- {e}" for e in mind.evidence) or "（まだない）"
    note = "\nさっき発作を起こして転んだが、甲羅のおかげで起き上がったところ。" if mind.just_recovered else ""
    return (f"現在の疑い度: {mind.level:.2f}（{phase_of(mind.level).name}）。これまでの発作: {mind.fits}回。{note}\n"
            f"証拠ボード:\n{board}\n\nラジオの新しい断片:\n「{transcript}」")


class ClaudeBrain:
    def __init__(self, model="claude-opus-5-5", effort="low"):
        try:
            import anthropic
        except ImportError:
            sys.exit("radio_paranoia: the `anthropic` package is required (uv run --group radio ...)")
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def think(self, mind, transcript):
        a = self.anthropic
        try:
            r = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=SYSTEM,
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": prompt(mind, transcript)}],
            )
        except a.RateLimitError:
            print("(brain) rate limited; skipping this chunk", file=sys.stderr)
            return None
        except a.APIStatusError as e:
            if e.status_code < 500:
                raise
            print(f"(brain) server error {e.status_code}; skipping this chunk", file=sys.stderr)
            return None
        except a.APIConnectionError as e:
            print(f"(brain) no connection: {e}", file=sys.stderr)
            return None
        if r.stop_reason != "end_turn":
            print(f"(brain) stop_reason={r.stop_reason}; skipping this chunk", file=sys.stderr)
            return None
        return json.loads(next(b.text for b in r.content if b.type == "text"))


def tuck_command(manifest, hip_deg=90.0, foot_deg=-90.0):
    """`pose` in canonical joint order for the internal tuck pose (q_hip, q_foot)."""
    q = {"hip": math.radians(hip_deg), "foot": math.radians(foot_deg)}
    return "pose " + " ".join(f"{manifest.to_firmware(j, q[j.role]):g}" for j in manifest.joints)


class Body:
    def __init__(self, robot=None, tuck="pose 90 90 90 90 90 90 90 90", tuck_ms=3000, motion_timeout=75.0):
        self.robot = robot
        self.recovery = [tuck, f"wait {tuck_ms}", "motion stand", "face confused"]
        self.motion_timeout = motion_timeout

    def lines(self, step):
        return [f"motion {step.motion}", f"face {step.face}"] + (self.recovery if step.fit else [])

    def act(self, step):
        lines = self.lines(step)
        if self.robot is None:
            print("  (dry) " + "; ".join(lines), flush=True)
            return 0
        return run_lines(self.robot, lines, self.motion_timeout)


def source_command(args, platform=sys.platform):
    pcm = ["-ac", "1", "-ar", str(RATE), "-f", "s16le", "-loglevel", "error", "-"]
    if args.sdr is not None:
        gain = ["-g", str(args.gain)] if args.gain is not None else []
        # -r after -M: wbfm presets a 32 kHz output that -r then overrides
        return ["rtl_fm", "-f", f"{args.sdr}M", "-M", "wbfm", "-r", str(RATE), *gain, "-"]
    if args.mic:
        fmt, dev = ("avfoundation", ":0") if platform == "darwin" else ("pulse", "default")
        dev = args.mic_device or dev
        if platform != "darwin" and dev.split(":", 1)[0] in ("alsa", "pulse") and ":" in dev:
            fmt, dev = dev.split(":", 1)  # e.g. alsa:plughw:CARD=Device,DEV=0 for a USB mic without PulseAudio
        return ["ffmpeg", "-f", fmt, "-i", dev, *pcm]
    return ["ffmpeg", "-re", "-i", args.file, *pcm]


def rms(pcm):
    samples = array.array("h", pcm[: len(pcm) // 2 * 2])
    return math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0


def offer(chunks, item):
    """Put without blocking, dropping the oldest item when full."""
    while True:
        try:
            return chunks.put_nowait(item)
        except queue.Full:
            try:
                chunks.get_nowait()
            except queue.Empty:
                pass


def ear(stream, chunk_bytes, chunks):
    """Keep only the newest chunks: the radio does not wait for the brain."""
    while data := stream.read(chunk_bytes):
        offer(chunks, data)
    offer(chunks, None)


def transcribe(pcm, whisper_cmd, model, language, extra=()):
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        with wave.open(f.name, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm)
        out = subprocess.run([whisper_cmd, "-m", model, "-f", f.name, "-l", language, "-nt", "-np", *extra],
                             capture_output=True, text=True, timeout=120)
    if out.returncode:
        print(f"(ear) {whisper_cmd} failed: {out.stderr.strip()[-300:]}", file=sys.stderr)
        return ""
    return " ".join(out.stdout.split())


def transcripts(args):
    if args.text:
        for line in sys.stdin:
            if line.strip():
                yield line.strip()
        return
    proc = subprocess.Popen(source_command(args), stdout=subprocess.PIPE)
    chunks = queue.Queue(maxsize=2)
    threading.Thread(target=ear, args=(proc.stdout, int(args.chunk_s * RATE) * 2, chunks), daemon=True).start()
    try:
        while (pcm := chunks.get()) is not None:
            if rms(pcm) < args.silence_rms:
                continue
            if text := transcribe(pcm, args.whisper_cmd, args.whisper_model, args.language):
                yield text
    finally:
        proc.terminate()


def run(heard, brain, mind, body, log=None, clock=time.time):
    for transcript in heard:
        print(f"\n📻 {transcript}", flush=True)
        decision = brain.think(mind, transcript)
        if decision is None:
            continue
        step = mind.update(decision)
        print(f"🧠 {decision['interpretation']}\n"
              f"   suspicion {step.level:.2f} {step.phase}{' — FIT' if step.fit else ''}: 「{step.mutter}」", flush=True)
        try:
            if body.act(step):
                print("  (body) macro stopped at an ERR", file=sys.stderr)
        except OSError as e:
            print(f"  (body) ……電波が届かない。帽子が効いている。({e})", file=sys.stderr)
        if log:
            log.write(json.dumps({"t": clock(), "transcript": transcript, **decision, "level": step.level,
                                  "phase": step.phase, "motion": step.motion, "face": step.face,
                                  "fit": step.fit}, ensure_ascii=False) + "\n")
            log.flush()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--sdr", type=float, metavar="MHZ", help="wide FM frequency for rtl_fm (Japan: 76-95)")
    src.add_argument("--mic", action="store_true", help="listen to a real radio through the microphone")
    src.add_argument("--file", help="audio file played in real time")
    src.add_argument("--text", action="store_true", help="read transcripts from stdin")
    p.add_argument("--gain", type=float, help="rtl_fm tuner gain in dB (default: auto)")
    p.add_argument("--mic-device", help="ffmpeg input (macOS ':0', Linux pulse 'default')")
    p.add_argument("--whisper-cmd", default="whisper-cli")
    p.add_argument("--whisper-model", help="ggml model for whisper.cpp, e.g. ggml-small.bin")
    p.add_argument("--language", default="ja")
    p.add_argument("--chunk-s", type=float, default=12.0)
    p.add_argument("--silence-rms", type=float, default=300.0, help="skip quieter chunks (int16 RMS)")
    p.add_argument("--model", default="claude-opus-5-5")
    p.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--host", help="robot address; omit for a dry run")
    p.add_argument("--tuck", type=float, nargs=2, default=(90.0, -90.0), metavar=("HIP", "FOOT"),
                   help="internal tuck angles in degrees (bambu turtle-shell default 90 -90)")
    p.add_argument("--tuck-ms", type=int, default=3000, help="time lying tucked before standing")
    p.add_argument("--log", type=Path, help="append one JSON line per thought")
    args = p.parse_args(argv)
    if not args.text and not args.whisper_model:
        p.error("audio ears need --whisper-model")

    robot = Robot(args.host) if args.host else None
    body = Body(robot, tuck_command(load_manifest(), *args.tuck), args.tuck_ms)
    brain = ClaudeBrain(args.model, args.effort)
    done = start_heartbeat(robot) if robot else None
    log = args.log.open("a", encoding="utf-8") if args.log else None
    try:
        if robot and run_lines(robot, ["?arm run", "motion stand"]):
            return 1
        run(transcripts(args), brain, Mind(), body, log)
    except KeyboardInterrupt:
        if robot:
            print("> off (interrupted)", flush=True)
            robot.command("off")
        return 130
    finally:
        if done:
            done.set()
        if log:
            log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
