#!/usr/bin/env python3
"""Sesame mind (skeleton): sound and chat in, new motions out, with memory.

    ears ──┬─ body: loudness / onset (no model, ms) ────────────┐
           └─ whisper: utterance text ──┐                       ▼
    chat page / stdin ──────────────────┴─▶ reflex ─▶ library ─▶ spine ─▶ robot
                                             │ "new"     ▲
                                             ▼           │
                                         designer (LLM) ┘
    memory.jsonl ◀─ every moment;   idle ─▶ ruminate (LLM) ─▶ notes.md

The reflex picks a library entry, an intensity and whether the speech was
addressed to the robot: `rules` (offline keywords), `jev` (TypeSafe System One;
point the Jev URL at a local-jev server for the edge) or `llm` (Claude or a
local model). The designer (Claude or a local model) only runs for new motions;
it writes a small spec that the spine expands into `pose` frames, so a learned
motion replays without any model. Local models are any OpenAI-compatible server
on this computer, e.g. `llama-server -hf ggml-org/gemma-3-4b-it-GGUF` (port 8080)
or Ollama (http://localhost:11434/v1).

Settings (backends, models, API keys, which robot to drive) live in
.sesame-mind/config.json and can be changed while running: GET/POST /config,
used by the Mind panel on the robot's own page. Keys are never sent back.

Specs move the eight motion-space axes (sim/motion_space.py: surge, spread,
yaw, stride, height, pitch, roll, lift) as offsets from its centre, or joints
in internal degrees relative to a manifest pose (`base`):

    {"kind": "axes", "hz": 2, "seconds": 4,
     "axes": [{"axis": "stride", "amp": 15, "offset": 0, "phase": 0},
              {"axis": "lift", "amp": 10, "offset": 0, "phase": 0.25}]}       # trot forward
    {"kind": "axes_keys", "keys": [{"ms": 600, "axes": [{"axis": "height", "value": -6}]}]}
    {"kind": "osc", "base": "stand", "hz": 1.5, "seconds": 4,
     "joints": [{"joint": "R1", "amp": 20, "offset": 0, "phase": 0.25}, ...]}
    {"kind": "keys", "base": "stand", "keys": [{"ms": 400, "angles": [{"joint": "L1", "deg": 30}]}]}
    {"kind": "firmware", "name": "wave"}

Axis frames are projected into the motion space (shrunk towards its centre
until Sesame can stand in them); joint frames are clamped to the manifest soft
limits. The firmware applies its own clamps and rate limit on top. Without
--host nothing moves (dry run). `uv run python -m sim.motion_space --text`
prints the motion space as the text the designer reads.

    uv run --group radio python tools/sesame_mind.py --text
    uv run --group radio python tools/sesame_mind.py --serve 8765 --robot sesame-s3-8b2c.local  # then use the robot page
    uv run --group radio python tools/sesame_mind.py --mic --whisper-model ggml-small.bin \\
        --serve 8765 --reflex jev --host sesame-s3-8b2c.local
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from radio_paranoia import RATE, offer, rms, source_command, transcribe  # noqa: E402
from sesame_remote import Robot, run_lines, start_heartbeat  # noqa: E402
from sim.manifest import load_manifest  # noqa: E402
from sim.voice_motion import FRAME_HZ as BODY_HZ, ProsodyStream, VoiceCpg  # noqa: E402
from sim.motion_space import AXES, describe, firmware_pose, load_space, project  # noqa: E402

FRAME_HZ = 20  # pose frames per second over Wi-Fi
INTENSITY = ("still", "gentle", "lively", "wild")
NEW, NONE = "new", "none"
BODY_MODES = ("off", "both", "prosody", "words")  # voice body (sim/voice_motion.py)
PERIODIC, KEYED = ("osc", "axes"), ("keys", "axes_keys")


# ---------------------------------------------------------------- moments


@dataclass(frozen=True)
class Moment:
    """One thing the robot noticed. Text may be empty (a bare sound)."""
    source: str  # chat | voice | radio | sound
    text: str = ""
    loudness: float = 0.0  # int16 RMS
    onset: bool = False  # sudden jump in loudness


@dataclass(frozen=True)
class Decision:
    action: str  # library name, NEW or NONE
    intensity: float = 0.5  # 0..1, the size of the motion
    addressed: float | None = None  # probability the speech was meant for the robot
    confidence: float | None = None
    by: str = ""
    tempo: float = 1.0  # speed factor for designed motions (0.5 = half speed, 2 = twice)


# ---------------------------------------------------------------- specs

# How a key's transition moves in time: in = slow start (wind-up), out = soft landing,
# inout = both. A key's ms sets how long; the ease sets where in that time the motion happens.
EASE = {"linear": lambda u: u, "in": lambda u: u * u, "out": lambda u: 1 - (1 - u) ** 2,
        "inout": lambda u: u * u * (3 - 2 * u)}
TEMPO = (0.5, 2.0)


def angles(manifest, spec, t, scale=1.0):
    """Offsets at time t (s): joint degrees from the base pose, or axis values from
    the motion-space centre for the `axes` kinds."""
    if spec["kind"] in PERIODIC:
        name, items = ("joint", spec["joints"]) if spec["kind"] == "osc" else ("axis", spec["axes"])
        return {j[name]: scale * (j.get("offset", 0.0)
                                  + j["amp"] * math.sin(2 * math.pi * (spec["hz"] * t + j.get("phase", 0.0))))
                for j in items}
    keys, start = spec["keys"], 0.0
    prev = {}
    for key in keys:
        target = ({a["joint"]: a["deg"] for a in key["angles"]} if spec["kind"] == "keys"
                  else {a["axis"]: a["value"] for a in key["axes"]})
        end = start + key["ms"] / 1000
        if t < end:
            u = EASE[key.get("ease", "linear")]((t - start) / (end - start) if end > start else 1.0)
            names = set(prev) | set(target)
            return {n: scale * (prev.get(n, 0.0) + u * (target.get(n, 0.0) - prev.get(n, 0.0))) for n in names}
        prev, start = target, end
    return {n: scale * d for n, d in prev.items()}


def duration(spec):
    if spec["kind"] in PERIODIC:
        return float(spec["seconds"])
    return sum(k["ms"] for k in spec["keys"]) / 1000


def frames(manifest, spec, hz=FRAME_HZ, intensity=0.5, tempo=1.0):
    """`pose` angles (firmware degrees, canonical order, soft-limit clamped) per frame.
    intensity sizes the motion; tempo plays it faster (>1) or slower (<1)."""
    base = manifest.pose_internal(spec.get("base", "stand"))
    center = load_space()["center"]
    scale = 0.3 + 0.7 * intensity
    tempo = min(max(tempo, TEMPO[0]), TEMPO[1])
    for i in range(int(duration(spec) / tempo * hz) + 1):
        delta = angles(manifest, spec, i * tempo / hz, scale)
        if spec["kind"] in ("axes", "axes_keys"):
            z = project({a: center[a] + delta.get(a, 0.0) for a in AXES}, manifest)
            degs = firmware_pose(z, manifest)
        else:
            degs = [manifest.to_firmware(j, base[j.name] + math.radians(delta.get(j.name, 0.0)))
                    for j in manifest.joints]
        yield [round(min(max(d, j.limits_deg[0]), j.limits_deg[1]), 1) for d, j in zip(degs, manifest.joints)]


def validate(manifest, spec):
    """Raise ValueError for specs the spine cannot play."""
    names = {j.name for j in manifest.joints}
    kind = spec.get("kind")
    if kind == "firmware":
        return
    if spec.get("base", "stand") not in manifest.raw["poses"]:
        raise ValueError(f"unknown base pose {spec.get('base')}")
    used = ([j["joint"] for j in spec["joints"]] if kind == "osc" else
            [a["joint"] for k in spec["keys"] for a in k["angles"]] if kind == "keys" else
            [a["axis"] for a in spec["axes"]] if kind == "axes" else
            [a["axis"] for k in spec["keys"] for a in k["axes"]] if kind == "axes_keys" else None)
    if used is None:
        raise ValueError(f"unknown spec kind {kind}")
    if unknown := set(used) - (names if kind in ("osc", "keys") else set(AXES)):
        raise ValueError(f"unknown {'joints' if kind in ('osc', 'keys') else 'axes'} {sorted(unknown)}")
    if kind in ("keys", "axes_keys") and (bad := {k.get("ease", "linear") for k in spec["keys"]} - set(EASE)):
        raise ValueError(f"unknown ease {sorted(bad)}")
    if not 0 < duration(spec) <= 30:
        raise ValueError("duration must be in (0, 30] s")


# ---------------------------------------------------------------- library and memory


def firmware_motions():
    return list(yaml.safe_load((ROOT / "manifest/motions.yaml").read_text())["motions"])


class Library:
    """Named motions: firmware built-ins plus designed specs (JSON on disk)."""

    def __init__(self, path=None):
        self.path = path
        self.items = {m: {"about": f"built-in {m}", "spec": {"kind": "firmware", "name": m}}
                      for m in firmware_motions()}
        if path and path.exists():
            self.items.update(json.loads(path.read_text()))

    def names(self):
        return list(self.items)

    def menu(self):
        return {n: v["about"] for n, v in self.items.items()}

    def add(self, name, about, spec):
        self.items[name] = {"about": about, "spec": spec}
        if self.path:
            learned = {n: v for n, v in self.items.items() if v["spec"]["kind"] != "firmware"}
            self.path.write_text(json.dumps(learned, ensure_ascii=False, indent=1))


class Memory:
    """Append-only JSONL of moments and what the robot did; notes.md is the rumination."""

    def __init__(self, folder=None):
        self.folder = folder
        self.lines = []
        if folder:
            folder.mkdir(parents=True, exist_ok=True)
            log = folder / "memory.jsonl"
            if log.exists():
                self.lines = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]

    def add(self, entry):
        self.lines.append(entry)
        if self.folder:
            with (self.folder / "memory.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def recent(self, n=20):
        return self.lines[-n:]

    @property
    def notes(self):
        p = self.folder / "notes.md" if self.folder else None
        return p.read_text() if p and p.exists() else ""

    @notes.setter
    def notes(self, text):
        if self.folder:
            (self.folder / "notes.md").write_text(text)


# ---------------------------------------------------------------- reflexes


def spoken_tempo(text):
    """Offline speed words: 速く → 1.5, ゆっくり → 0.6, otherwise 1."""
    if any(w in text for w in ("速く", "早く", "はやく", "素早く", "fast", "quick")):
        return 1.5
    if any(w in text for w in ("ゆっくり", "そっと", "slow")):
        return 0.6
    return 1.0


class RuleReflex:
    """Offline fallback: library names in the text, 作って/new for a new motion, onsets startle."""
    by = "rules"

    def decide(self, moment, library, notes=""):
        text = moment.text.lower()
        if moment.source == "chat" and any(w in text for w in ("作って", "つくって", "new ")):
            return Decision(NEW, 0.6, 1.0, by=self.by, tempo=spoken_tempo(text))
        for name in sorted(library.names(), key=len, reverse=True):
            if name in text:
                return Decision(name, 0.6, 1.0, by=self.by, tempo=spoken_tempo(text))
        if moment.onset:
            return Decision("shake", min(1.0, moment.loudness / 8000), by=self.by)
        return Decision(NONE, 0.0, by=self.by)


def jev_request(moment, library, notes, model="jev-latest"):
    """System One request. Field names follow docs.typesafe.ai as of 2026-11; verify with a key."""
    state = {"heard": moment.text, "source": moment.source, "loudness": round(moment.loudness),
             "sudden_sound": moment.onset, "motions": library.menu(), "notes": notes[-1500:]}
    return {
        "model": model,
        "state": json.dumps(state, ensure_ascii=False),
        "questions": {
            "action": {"type": "choice",
                       "question": "Which motion should the robot do now? 'new' = invent one, 'none' = keep still",
                       "options": library.names() + [NEW, NONE]},
            "intensity": {"type": "score", "question": "How energetically should it move?",
                          "criteria": list(INTENSITY)},
            "addressed": {"type": "noul", "question": "Is the speech addressed to the robot itself?"},
        },
    }


def _first(d, *keys):
    return next((d[k] for k in keys if isinstance(d, dict) and k in d), None)


def jev_decision(reply, options):
    """Tolerant parse: the SDK is young and minor versions have renamed fields."""
    answers = _first(reply, "answers", "results") or reply
    action = _first(answers.get("action", {}), "answer", "selected", "option", "value")
    score = _first(answers.get("intensity", {}), "score", "value", "answer")
    yes = _first(answers.get("addressed", {}), "probability", "value", "answer")
    conf = _first(answers.get("action", {}), "confidence")
    return Decision(action if action in options else NONE,
                    min(1.0, max(0.0, float(score) / (len(INTENSITY) - 1))) if score is not None else 0.5,
                    float(yes) if isinstance(yes, (int, float)) else None,
                    float(conf) if isinstance(conf, (int, float)) else None, by="jev")


class JevReflex:
    by = "jev"

    def __init__(self, url, key=None, model="jev-latest", timeout=2.0, post=None):
        self.url, self.key, self.model, self.timeout = url, key, model, timeout
        self.post = post or self._post

    def _post(self, body):
        req = urllib.request.Request(self.url, json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.key}"} if self.key else {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def decide(self, moment, library, notes=""):
        body = jev_request(moment, library, notes, self.model)
        return jev_decision(self.post(body), body["questions"]["action"]["options"])


# ---------------------------------------------------------------- designer (Claude)


DESIGN_SYSTEM = """\
あなたは四足歩行ロボット「セサミ」（8軸サーボ、各脚に hip と foot）の振付師です。
聞こえた言葉や指示から、新しい動きを一つ小さな設計図として作ってください。
なるべく下の動作空間の8軸で書いてください（転ばない範囲に自動で収まります）。
- axes: 軸の周期運動。hz は 0.2〜3、seconds は 1〜10、各軸の amp（振幅）、offset（中心からのずれ）、phase（0〜1周期）
- axes_keys: 軸のキーポーズの列。各キーの ms は 100〜2000、合計10秒以内、value は中心からの差分
- 各キーの ease でそのキーへの移り方を決めます: linear（等速）、in（ゆっくり出て速く着く＝溜め）、
  out（速く出てふわっと止まる）、inout（両端がなめらか）。緩急は ms の長短と ease で付けてください
  （例: 長い in で溜めて、短い linear で弾く、out で余韻）。
関節を直接動かす必要があるとき（片足を上げて振るなど）だけ osc / keys を使います。
角度は基準姿勢（base）からの差分で、内部座標の度数です（0 = 基準のまま）。
- osc: 関節の周期運動（joints）。keys: 関節のキーポーズの列（angles）
実際の動きは指定の 0.3〜1 倍（声の勢いで変わる）です。使わない種類の欄は空配列か0にしてください。
name は英小文字とアンダースコア、about は日本語で20字以内。

""" + describe()

RUMINATE_SYSTEM = """\
あなたはロボット「セサミ」の記憶です。最近の出来事と以前のメモを読み返し、
セサミの性格、好きな動き、よく聞く言葉、ひとりのときにやりたいことを、
箇条書き15行以内の新しいメモに書き直してください。古いメモの大事な点は残してください。
"""


def design_schema(manifest):
    joint = {"type": "string", "enum": [j.name for j in manifest.joints]}
    axis = {"type": "string", "enum": list(AXES)}
    num = {"type": "number"}

    def obj(props):
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}

    return obj({
        "name": {"type": "string"},
        "about": {"type": "string"},
        "kind": {"type": "string", "enum": ["axes", "axes_keys", "osc", "keys"]},
        "base": {"type": "string", "enum": list(manifest.raw["poses"])},
        "hz": num, "seconds": num,
        "axes": {"type": "array", "items": obj({"axis": axis, "amp": num, "offset": num, "phase": num})},
        "joints": {"type": "array", "items": obj({"joint": joint, "amp": num, "offset": num, "phase": num})},
        "keys": {"type": "array", "items": obj({
            "ms": num,
            "ease": {"type": "string", "enum": list(EASE)},
            "axes": {"type": "array", "items": obj({"axis": axis, "value": num})},
            "angles": {"type": "array", "items": obj({"joint": joint, "deg": num})},
        })},
    })


def spec_of(design):
    """Designer output -> (name, about, spec); the unused kind's fields are dropped."""
    kind = design["kind"]
    if kind in PERIODIC:
        spec = {k: design[k] for k in ("kind", "base", "hz", "seconds", "joints" if kind == "osc" else "axes")}
    else:
        field = "angles" if kind == "keys" else "axes"
        spec = {"kind": kind, "base": design["base"],
                "keys": [{"ms": k["ms"], **({"ease": k["ease"]} if k.get("ease", "linear") != "linear" else {}),
                          field: k.get(field, [])} for k in design["keys"]]}
    if kind.startswith("axes"):
        del spec["base"]
    return design["name"], design["about"], spec


class ClaudeBrain:
    by = "claude"

    def __init__(self, key=None, model="claude-opus-5-5", effort="low"):
        try:
            import anthropic
        except ImportError:
            raise ValueError("the `anthropic` package is missing (uv run --group radio ...)")
        if not (key or claude_auth()):
            raise ValueError("no Claude credentials on the PC: run `ant auth login` or set ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        self.model, self.effort = model, effort

    def ask(self, system, user, schema=None):
        fmt = {"format": {"type": "json_schema", "schema": schema}} if schema else {}
        r = self.client.beta.messages.create(
            model=self.model, max_tokens=4000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=system, output_config={"effort": self.effort, **fmt},
            messages=[{"role": "user", "content": user}])
        if r.stop_reason != "end_turn":
            raise RuntimeError(f"stop_reason={r.stop_reason}")
        return next(b.text for b in r.content if b.type == "text")


def _http_json(url, body=None, timeout=60.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def local_models(url, timeout=1.0):
    """Model ids served at an OpenAI-compatible URL; [] when nothing answers."""
    try:
        return [m["id"] for m in _http_json(url.rstrip("/") + "/models", timeout=timeout)["data"]]
    except (OSError, ValueError, KeyError, TypeError):
        return []


class LocalBrain:
    """OpenAI-compatible server on this computer: llama.cpp `llama-server`, Ollama (/v1), LM Studio, MLX."""
    by = "local"

    def __init__(self, url, model="", timeout=60.0, post=None):
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout
        self.post = post or (lambda body: _http_json(self.url + "/chat/completions", body, self.timeout))

    def ask(self, system, user, schema=None):
        body = {"model": self.model, "temperature": 0.7,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "answer", "strict": True, "schema": schema}}
        text = self.post(body)["choices"][0]["message"]["content"]
        if schema and not text.lstrip().startswith("{"):  # small models sometimes wrap JSON in prose
            text = text[text.index("{"): text.rindex("}") + 1]
        return text


class Designer:
    """New motions and rumination from any brain."""

    def __init__(self, brain, manifest):
        self.brain, self.schema = brain, design_schema(manifest)
        self.by = brain.by

    def design(self, moment, library, notes=""):
        user = (f"メモ:\n{notes or '（まだない）'}\n\n既にある動き: {', '.join(library.names())}\n\n"
                f"聞こえたこと（{moment.source}）:「{moment.text}」")
        return spec_of(json.loads(self.brain.ask(DESIGN_SYSTEM, user, self.schema)))

    def ruminate(self, recent, notes=""):
        events = "\n".join(json.dumps(e, ensure_ascii=False) for e in recent)
        return self.brain.ask(RUMINATE_SYSTEM, f"以前のメモ:\n{notes or '（まだない）'}\n\n最近の出来事:\n{events}")


REFLEX_SYSTEM = """\
あなたはロボット「セサミ」の反射です。聞こえたことに対して、今やる動きを一つ選んでください。
new = 新しい動きを作る（「〜みたいな動きを作って」など）、none = 何もしない。
チャットはセサミへの話しかけです。動きや様子や気持ちを頼まれたら、名前が一致しなくても
いちばん近い動きを選んでください（例: 悶えて → worm か freaky、喜んで → dance）。
none は、頼みではない独り言のときと、どの動きも合わないときだけです。
intensity は 0〜1 の動きの大きさ、tempo は速さの倍率 0.5〜2（1 = ふつう。「速く」「ゆっくり」
「のんびり」「キビキビ」などに合わせる）、addressed はセサミ自身に話しかけられた確率（0〜1）。
"""


class LLMReflex:
    def __init__(self, brain):
        self.brain, self.by = brain, f"llm:{brain.by}"

    def decide(self, moment, library, notes=""):
        options = library.names() + [NEW, NONE]
        schema = {"type": "object", "additionalProperties": False,
                  "required": ["action", "intensity", "tempo", "addressed"],
                  "properties": {"action": {"type": "string", "enum": options}, "intensity": {"type": "number"},
                                 "tempo": {"type": "number"}, "addressed": {"type": "number"}}}
        user = (f"動き: {json.dumps(library.menu(), ensure_ascii=False)}\nメモ: {notes[-800:]}\n"
                f"聞こえたこと（{moment.source}, 音量 {moment.loudness:.0f}{', 急な音' if moment.onset else ''}）:"
                f"「{moment.text}」")
        d = json.loads(self.brain.ask(REFLEX_SYSTEM, user, schema))
        return Decision(d["action"] if d["action"] in options else NONE,
                        min(1.0, max(0.0, float(d["intensity"]))), float(d["addressed"]), by=self.by,
                        tempo=min(max(float(d.get("tempo", 1.0)), TEMPO[0]), TEMPO[1]))


# ---------------------------------------------------------------- settings


JEV_CLOUD = "https://api.typesafe.ai/v1/systemone"
CLAUDE_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
DEFAULTS = {
    "reflex": "rules",  # rules | jev | llm
    "reflex_brain": "claude",  # claude | local (for reflex=llm)
    "designer": "claude",  # claude | local | none
    "claude_model": "claude-opus-5-5",
    "claude_reflex_model": "claude-haiku-5-5",
    "jev_url": JEV_CLOUD,
    "jev_model": "jev-latest",
    "local_url": "http://localhost:8080/v1",  # llama-server; Ollama: http://localhost:11434/v1
    "local_model": "",
    "host": "",  # robot address; empty = dry run
    "live": False,
    "body": "off",  # voice body: off | both | prosody | words
}


def claude_auth():
    """Where the Anthropic SDK will find credentials on this PC: "key", "profile" or ""."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "key"
    folder = Path(os.environ.get("ANTHROPIC_CONFIG_DIR") or Path.home() / ".config" / "anthropic") / "credentials"
    return "profile" if os.environ.get("ANTHROPIC_PROFILE") or any(folder.glob("*.json")) else ""

CHOICES = {"reflex": ("rules", "jev", "llm"), "reflex_brain": ("claude", "local"),
           "designer": ("claude", "local", "none"), "claude_model": CLAUDE_MODELS,
           "claude_reflex_model": CLAUDE_MODELS, "body": BODY_MODES}


class Settings:
    """config.json in the state folder (mode 600). API keys never pass through here: the page talks
    plain HTTP and anyone on the LAN can reach it, so keys stay in the PC's environment or `ant` profile."""

    def __init__(self, folder=None):
        self.path = folder / "config.json" if folder else None
        self.values = dict(DEFAULTS)
        if self.path and self.path.exists():
            self.values.update(json.loads(self.path.read_text()))

    def update(self, changes):
        for k, v in changes.items():
            if k in DEFAULTS:
                if k in CHOICES and v not in CHOICES[k]:
                    raise ValueError(f"{k} must be one of {', '.join(CHOICES[k])}")
                self.values[k] = bool(v) if k == "live" else str(v).strip()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.values, indent=1))
            self.path.chmod(0o600)

    def public(self):
        out = {k: v for k, v in self.values.items() if k in DEFAULTS}
        out.update(claude_auth=claude_auth(), typesafe_key_set=bool(os.environ.get("TYPESAFE_API_KEY")))
        out["choices"] = CHOICES
        return out


def brain_of(settings, which, claude_model):
    v = settings.values
    if which == "local":
        return LocalBrain(v["local_url"], v["local_model"])
    return ClaudeBrain(None, claude_model)


def build(settings, manifest):
    """(reflex, designer) for the current settings; ValueError explains what is missing."""
    v = settings.values
    if v["reflex"] == "jev":
        reflex = JevReflex(v["jev_url"], os.environ.get("TYPESAFE_API_KEY"), v["jev_model"])
    elif v["reflex"] == "llm":
        reflex = LLMReflex(brain_of(settings, v["reflex_brain"], v["claude_reflex_model"]))
    else:
        reflex = RuleReflex()
    designer = None if v["designer"] == "none" else Designer(brain_of(settings, v["designer"], v["claude_model"]),
                                                             manifest)
    return reflex, designer


# ---------------------------------------------------------------- spine


class Spine:
    """Plays one library entry at a time; a newer play() interrupts the current one."""

    def __init__(self, manifest, robot=None, hz=FRAME_HZ, sleep=time.sleep):
        self.manifest, self.robot, self.hz, self.sleep = manifest, robot, hz, sleep
        self.cancel = threading.Event()
        self.thread = None

    def start(self, entry, intensity=0.5, tempo=1.0):
        """Interrupt the current motion and play this one in the background."""
        self.cancel.set()
        if self.thread:
            self.thread.join()
        self.cancel = threading.Event()
        self.thread = threading.Thread(target=self._play_logged, args=(entry, intensity, tempo), daemon=True)
        self.thread.start()

    def _play_logged(self, entry, intensity, tempo=1.0):
        try:
            self.play(entry, intensity, tempo)
        except OSError as e:
            print(f"  (spine) no link: {e}", file=sys.stderr)

    def play(self, entry, intensity=0.5, tempo=1.0):
        """Firmware motions keep their own speed; tempo applies to designed ones."""
        spec = entry["spec"]
        if spec["kind"] == "firmware":
            lines = [f"motion {spec['name']}"]
            if self.robot is None:
                print("  (dry) " + lines[0], flush=True)
                return 0
            return run_lines(self.robot, lines)
        poses = list(frames(self.manifest, spec, self.hz, intensity, tempo))
        if self.robot is None:
            print(f"  (dry) {len(poses)} frames @ {self.hz} Hz, first: pose {' '.join(map(str, poses[0]))}", flush=True)
            return 0
        t0 = time.monotonic()
        for i, p in enumerate(poses):
            if self.cancel.is_set():
                return 0
            ok, text = self.robot.command("pose " + " ".join(f"{x:g}" for x in p))
            if not ok:
                print(f"  (spine) {text}", file=sys.stderr)
                return 1
            self.sleep(max(0.0, t0 + (i + 1) / self.hz - time.monotonic()))
        return 0


# ---------------------------------------------------------------- simulated robot


_SIM = []


def sim_robot():
    """The one MuJoCo stand-in (sim/live_robot.py) behind --host sim, started on first use."""
    if not _SIM:
        from sim.live_robot import SimRobot
        _SIM.append(SimRobot().start())
    return _SIM[0]


# ---------------------------------------------------------------- voice body


class VoiceBody:
    """sim/voice_motion live: how it is said moves the body, what is said sets its parameters.

    Microphone chunks become prosody frames; a BODY_HZ loop steps the CPG with
    them (or with silence when no microphone feeds it) and a sender streams the
    newest targets as `pose` at FRAME_HZ. While the body is on, words from chat
    or whisper go to the body instead of the reflex and library motions.
    """

    SILENCE = (0.0, 0.0, math.nan, math.nan, 0.0)

    def __init__(self, manifest, spine, hz=FRAME_HZ):
        self.manifest, self.spine, self.hz = manifest, spine, hz
        self.mode, self.cpg = "off", None
        self.lock = threading.Lock()
        self.frames = queue.Queue(maxsize=BODY_HZ // 2)  # newest 0.5 s of prosody
        self.stream = ProsodyStream(f0_ref=None)  # pitch reference follows the speaker
        self.mic_at = -1e9  # monotonic time of the last microphone chunk
        self.last, self.f0 = self.SILENCE, math.nan  # newest frame, last voiced pitch
        self.heard, self.error, self.sent, self.steps = "", "", 0, 0
        self.target, self.fresh = None, threading.Event()
        self.started = False

    @property
    def robot(self):
        return getattr(self.spine, "robot", None)

    def set_mode(self, mode):
        if mode == self.mode:
            return
        with self.lock:
            self.mode = mode
            self.cpg = None if mode == "off" else VoiceCpg(self.manifest, mode)
            if self.cpg:
                self.cpg.keep_log = BODY_HZ * 10
        if mode == "off":
            if self.robot:
                threading.Thread(target=self._command, args=("motion stand",), daemon=True).start()
        elif not self.started:
            self.started = True
            threading.Thread(target=self._loop, daemon=True).start()
            threading.Thread(target=self._send, daemon=True).start()

    def feed(self, pcm):
        """int16 microphone bytes from the ears."""
        if self.mode == "off":
            return
        self.mic_at = time.monotonic()
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        for frame in self.stream.feed(audio):
            offer(self.frames, frame)

    def hear_words(self, text):
        self.heard = text
        with self.lock:
            it = self.cpg.hear_words(text) if self.cpg else None
        return it.name if it else "-"

    def step(self, frame):
        with self.lock:
            if self.cpg is None:
                return None
            self.last = frame
            if math.isfinite(frame[2]):
                self.f0 = frame[2]
            self.target = self.cpg.step(*frame[:2], *frame[3:])
            self.steps += 1
        self.fresh.set()
        return self.target

    def _loop(self):
        """BODY_HZ ticks on the wall clock. Microphone chunks bring 5 frames at once, so
        each tick takes one, waits briefly for the next chunk when the queue is empty,
        and drops the oldest frames when more than a chunk has piled up (latency)."""
        period, next_t = 1 / BODY_HZ, time.monotonic()
        while True:
            if self.mode == "off":
                time.sleep(0.1)
                next_t = time.monotonic()
                continue
            frame = self.SILENCE
            if time.monotonic() - self.mic_at < 0.5:
                while self.frames.qsize() > 6:
                    self.frames.get_nowait()
                try:
                    frame = self.frames.get(timeout=1.5 * period)
                except queue.Empty:
                    pass
            self.step(frame)
            next_t += period
            now = time.monotonic()
            if next_t < now - 0.1:  # fell behind: do not try to catch up
                next_t = now
            time.sleep(max(0.0, next_t - now))

    def pose(self, target):
        return [round(min(max(self.manifest.to_firmware(j, q), j.limits_deg[0]), j.limits_deg[1]), 1)
                for q, j in zip(target, self.manifest.joints)]

    def _command(self, text):
        try:
            ok, reply = self.robot.command(text)
        except (OSError, AttributeError) as e:
            self.error = f"robot not reachable: {e}"
            return False
        if not ok:
            self.error = reply.strip()
        return ok

    def _send(self):
        last, t_last = None, 0.0
        while True:
            self.fresh.wait()
            self.fresh.clear()
            if self.mode == "off" or self.robot is None or self.target is None:
                continue
            time.sleep(max(0.0, t_last + 1 / self.hz - time.monotonic()))
            degs = self.pose(self.target)
            if last and max(abs(a - b) for a, b in zip(degs, last)) < 0.5:
                continue  # standing still: nothing new to say
            t_last = time.monotonic()
            if self._command("pose " + " ".join(f"{d:g}" for d in degs)):
                last, self.error = degs, ""
                self.sent += 1
            elif "arm run" in self.error:
                self._command("arm run")
            else:
                time.sleep(1.0)

    def state(self):
        env = self.last[0]
        with self.lock:
            cpg = self.cpg
            arousal, amp, gait, intent = cpg.log[-1] if cpg and cpg.log else (0.0, 0.0, "-", "-")
            hz = cpg.hz if cpg else 0.0
        robot = self.robot
        return {"mode": self.mode, "arousal": round(arousal, 2), "amp": round(amp, 2), "gait": gait,
                "intent": intent, "hz": round(hz, 2), "f0": None if math.isnan(self.f0) else round(self.f0),
                "f0_ref": round(self.stream.f0_ref), "loud": round(env, 2), "heard": self.heard,
                "mic": time.monotonic() - self.mic_at < 1.0, "robot": robot.base if robot else "",
                "steps": self.steps, "sent": self.sent, "error": self.error}


# ---------------------------------------------------------------- mind


class Mind:
    def __init__(self, reflex, library, memory, spine, designer=None, clock=time.time):
        self.reflex, self.library, self.memory, self.spine = reflex, library, memory, spine
        self.designer, self.clock = designer, clock
        self.settings, self.link, self.error = None, None, ""
        self.body = VoiceBody(spine.manifest, spine)

    def handle(self, moment):
        if self.body.mode != "off":
            return self.handle_body(moment)
        t0 = time.monotonic()
        try:
            decision = self.reflex.decide(moment, self.library, self.memory.notes)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            print(f"(reflex {self.reflex.by}) {e}; falling back to rules", file=sys.stderr)
            decision = RuleReflex().decide(moment, self.library)
        reflex_ms = (time.monotonic() - t0) * 1000
        action, note = decision.action, ""
        if action == NEW:
            action, note = self.invent(moment)
        entry = {"t": self.clock(), **asdict(moment), **asdict(decision), "did": action,
                 "reflex_ms": round(reflex_ms), "note": note}
        self.memory.add(entry)
        speed = f" ×{decision.tempo:g}" if decision.tempo != 1 else ""
        print(f"🧠 {moment.source}「{moment.text}」→ {action}{speed} ({decision.by}, {reflex_ms:.0f} ms)"
              f"{note and ' ' + note}", flush=True)
        if action != NONE:
            self.spine.start(self.library.items[action], decision.intensity, decision.tempo)
        return entry

    def handle_body(self, moment):
        """Body mode: words set the CPG's intent; sounds are already in the prosody."""
        if not moment.text:
            return None
        did = "body:" + self.body.hear_words(moment.text)
        entry = {"t": self.clock(), **asdict(moment), "action": did, "intensity": 0.0, "addressed": 1.0,
                 "by": f"body:{self.body.mode}", "did": did, "reflex_ms": 0, "note": ""}
        self.memory.add(entry)
        print(f"🫀 {moment.source}「{moment.text}」→ {did}", flush=True)
        return entry

    def invent(self, moment):
        if self.designer is None:
            return NONE, "no designer"
        try:
            name, about, spec = self.designer.design(moment, self.library, self.memory.notes)
            validate(self.spine.manifest, spec)
        except Exception as e:  # a bad design must not stop the robot listening
            return NONE, f"design failed: {e}"
        self.library.add(name, about, spec)
        return name, f"new motion {name}: {about}"

    def configure(self, settings):
        """Apply settings now; on error keep what works (rules, no designer) and report it."""
        self.settings, self.error = settings, ""
        try:
            self.reflex, self.designer = build(settings, self.spine.manifest)
        except ValueError as e:
            self.reflex, self.designer, self.error = RuleReflex(), None, str(e)
        v = settings.values
        self.body.set_mode(v.get("body", "off"))
        host = v["host"] if v["live"] and v["host"] else None
        if host != getattr(self.spine.robot, "host", None):
            if self.link:
                self.link.set()
                self.link = None
            self.spine.robot = (sim_robot() if host == "sim" else Robot(host)) if host else None
            if self.spine.robot:
                self.spine.robot.host = host
                self.link = start_heartbeat(self.spine.robot)
                threading.Thread(target=self._wake, args=(self.spine.robot,), daemon=True).start()
        return self.status()

    def _wake(self, robot):
        try:
            run_lines(robot, ["?arm run", "motion stand"])
        except OSError as e:
            self.error = f"robot {robot.base} not reachable: {e}"

    def status(self):
        robot = self.spine.robot
        return {"reflex": self.reflex.by, "designer": self.designer.by if self.designer else "none",
                "robot": robot.base if robot else "", "body": self.body.mode, "error": self.error}

    def ruminate(self):
        if self.designer and self.memory.recent():
            try:
                self.memory.notes = self.designer.ruminate(self.memory.recent(50), self.memory.notes)
            except Exception as e:  # an outage must not stop the robot listening
                print(f"(ruminate) {e}", file=sys.stderr)
                return
            print(f"💭 ruminated ({len(self.memory.notes.splitlines())} lines of notes)", flush=True)


# ---------------------------------------------------------------- ears


def utterances(stream, frame_ms=100, silence_rms=300.0, loud_rms=3000.0, end_ms=600, max_s=8.0):
    """Yield ("sound", loudness) when it gets loud and ("speech", pcm) per stretch above silence."""
    frame = int(RATE * frame_ms / 1000) * 2
    prev, buf, quiet = 0.0, bytearray(), 0
    while data := stream.read(frame):
        level = rms(data)
        if level >= loud_rms > prev:  # rising edge only: one startle per bang
            yield "sound", level
        prev = level
        if level >= silence_rms:
            buf += data
            quiet = 0
        elif buf:
            buf += data
            quiet += frame_ms
        if buf and (quiet >= end_ms or len(buf) >= max_s * RATE * 2):
            yield "speech", bytes(buf)
            buf, quiet = bytearray(), 0


class Tap:
    """A stream that hands every chunk it reads to a listener (the voice body)."""

    def __init__(self, stream, listener, open_while=None):
        self.stream, self.listener, self.open_while = stream, listener, open_while

    def read(self, n):
        if self.open_while and not self.open_while():
            return b""  # reads as the end of the stream
        data = self.stream.read(n)
        if data:
            self.listener(data)
        return data


def hear(args, moments, body=None, poll_s=0.2):
    """Audio ears -> moments; the newest win (offer drops the oldest). Without a
    whisper model only the body hears (prosody), nothing is transcribed. With
    --mic-on-demand the microphone is open only while the voice body is on."""
    source = "radio" if args.sdr is not None else "voice"
    on_demand = bool(getattr(args, "mic_on_demand", False) and body)
    listening = (lambda: body.mode != "off") if on_demand else None
    while True:
        while on_demand and not listening():
            time.sleep(poll_s)
        proc = subprocess.Popen(source_command(args), stdout=subprocess.PIPE)
        stream = Tap(proc.stdout, body.feed, listening) if body else proc.stdout
        try:
            for kind, value in utterances(stream, silence_rms=args.silence_rms):
                if kind == "sound":
                    offer(moments, Moment("sound", loudness=value, onset=True))
                elif args.whisper_model and (text := transcribe(value, args.whisper_cmd, args.whisper_model,
                                                                  args.language)):
                    offer(moments, Moment(source, text, loudness=rms(value)))
        finally:
            proc.terminate()
            proc.wait()
        if not on_demand:
            return
        time.sleep(poll_s)  # also paces restarts if the microphone fails


# ---------------------------------------------------------------- chat page


class Console:
    """Tees stdout/stderr and keeps the newest lines, so the pages can show what
    the mind printed (commands sent, robot replies, errors) without a terminal."""

    def __init__(self, keep=200):
        self.lines, self.lock = collections.deque(maxlen=keep), threading.Lock()

    def tee(self, stream):
        console, partial = self, []

        class Tee:
            def write(self, text):
                stream.write(text)
                with console.lock:
                    *done, rest = ("".join(partial) + text).split("\n")
                    partial[:] = [rest]
                    console.lines.extend((round(time.time(), 1), line) for line in done if line.strip())
                return len(text)

            def __getattr__(self, name):
                return getattr(stream, name)

        return Tee()

    def recent(self, n=60):
        with self.lock:
            return list(self.lines)[-n:]


CONSOLE = Console()



PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>Sesame mind</title><style>body{font:16px system-ui;margin:12px;max-width:640px}
#log,#bst,#con{white-space:pre-wrap;font:13px ui-monospace,monospace}#con{color:#555}form{display:flex;gap:6px}input{flex:1;font:16px system-ui}
img{width:100%;display:none;margin:6px 0}</style><h3>Sesame mind</h3>
<form id=f><input id=t placeholder="話しかける / ○○みたいな動きを作って" autofocus><button>送る</button></form>
<p><select id=body><option value=off>声で動く: オフ<option value=both>声で動く: 抑揚＋言葉<option value=prosody>声で動く: 抑揚だけ
<option value=words>声で動く: 言葉だけ</select> <button id=r>反芻</button></p><div id=bst></div><img id=sim alt="sim">
<div id=log></div><details open><summary>ログ（PC）</summary><div id=con></div></details><script>
body.onchange=()=>fetch('config',{method:'POST',body:JSON.stringify({body:body.value})});
setInterval(async()=>{const b=await (await fetch('body')).json();if(document.activeElement!==body)body.value=b.mode;
if(b.robot==='sim'&&!sim.src){sim.src='sim.mjpg';sim.style.display='block'}
bst.textContent=(b.mode==='off'?'':`声 ${b.f0??'-'} Hz (基準 ${b.f0_ref}) 音量 ${b.loud} | 覚醒 ${b.arousal} 振幅 ${b.amp} ${b.gait} ${b.hz} Hz\\n`+
`意図 ${b.intent} 「${b.heard}」 | ${b.mic?'マイク受信中':'マイクなし（--mic）'} | pose ${b.sent}`)+
`\\nrobot: ${b.robot||'なし（試し）'}`+(b.error?'\\nERR '+b.error:'')},500);
const show=async()=>{const l=await (await fetch('log')).json();log.textContent=l.reverse().map(e=>
`${new Date(e.t*1000).toLocaleTimeString()} ${e.source}「${e.text}」→ ${e.did} (${e.by} ${e.reflex_ms}ms) ${e.note}`).join('\\n')};
f.onsubmit=async e=>{e.preventDefault();const s=t.value;t.value='';
await fetch('say',{method:'POST',body:s});show()};r.onclick=()=>fetch('ruminate',{method:'POST'});
setInterval(show,1000);show();
setInterval(async()=>{const l=await (await fetch('console')).json();
con.textContent=l.reverse().map(([t,s])=>new Date(t*1000).toLocaleTimeString()+' '+s).join('\\n')},1000)</script>"""


def config_view(mind):
    view = mind.settings.public()
    view["local_models"] = local_models(view["local_url"])
    view["status"] = mind.status()
    return view


def serve(port, mind, moments):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body, kind="application/json"):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            # the robot's own page (another origin) posts chat here; plain-text POSTs need no preflight
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                return self.reply(200, PAGE, "text/html")
            if self.path == "/log":
                return self.reply(200, json.dumps(mind.memory.recent(40), ensure_ascii=False))
            if self.path == "/console":
                return self.reply(200, json.dumps(CONSOLE.recent(), ensure_ascii=False))
            if self.path == "/config":
                return self.reply(200, json.dumps(config_view(mind), ensure_ascii=False))
            if self.path == "/space":  # the motion space as text, for any LLM
                return self.reply(200, describe(), "text/plain")
            if self.path == "/body":
                return self.reply(200, json.dumps(mind.body.state(), ensure_ascii=False))
            if self.path == "/sim.mjpg" and getattr(mind.spine.robot, "host", "") == "sim":
                return self.stream_sim(mind.spine.robot)
            self.reply(404, "{}")

        def stream_sim(self, robot):
            """MJPEG of the simulated robot until the browser goes away."""
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                for frame in robot.frames():
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
            except OSError:
                pass

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
            if self.path == "/say" and body.strip():
                offer(moments, Moment("chat", body.strip()))
            elif self.path == "/ruminate":
                threading.Thread(target=mind.ruminate, daemon=True).start()
            elif self.path == "/config":
                try:
                    mind.settings.update(json.loads(body or "{}"))
                except ValueError as e:  # bad JSON or choice: nothing applied
                    return self.reply(400, json.dumps({**config_view(mind), "error": str(e)}, ensure_ascii=False))
                mind.configure(mind.settings)
                return self.reply(200, json.dumps(config_view(mind), ensure_ascii=False))
            self.reply(202, "{}")

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"chat page: http://{os.uname().nodename}:{port}/ (or this computer's LAN IP)", flush=True)
    return server


def lan_url(robot_host, port):
    """This computer's URL as seen from the robot's network (the interface that routes to it)."""
    host = robot_host.split("://")[-1].split("/")[0]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((socket.gethostbyname(host), 80))  # UDP connect sends nothing
        return f"http://{s.getsockname()[0]}:{port}"


def announce(mind, robots, port, every=10.0, stop=None, robot_of=Robot):
    """Tell each robot where this mind is (`mind URL`, saved on the robot) so its page
    fills in the Mind URL by itself; again when it forgets, reboots or our address changes."""
    stop = stop or threading.Event()
    while True:
        v = mind.settings.values if mind.settings else {}
        targets = set(robots) | ({v["host"]} if v.get("live") and v.get("host") not in ("", "sim") else set())
        for host in sorted(targets):
            try:
                url = lan_url(host, port)
                robot = robot_of(host)
                if f" mind={url}" not in robot.get("/status")[1]:
                    ok, text = robot.command(f"mind {url}")
                    print(f"📣 {host}: {text.strip() if ok else 'ERR ' + text.strip()}", flush=True)
            except OSError:
                pass  # robot off or out of reach: try again later
        if stop.wait(every):
            return


def think(mind, moments, idle_s=None):
    """Single worker: moments in arrival order; ruminate after idle_s without any."""
    while True:
        try:
            moment = moments.get(timeout=idle_s)
        except queue.Empty:
            mind.ruminate()
            continue
        if moment is None:
            return
        mind.handle(moment)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--sdr", type=float, metavar="MHZ", help="wide FM frequency for rtl_fm (Japan: 76-95)")
    src.add_argument("--mic", action="store_true", help="microphone through ffmpeg")
    src.add_argument("--file", help="audio file played in real time")
    src.add_argument("--text", action="store_true", help="chat lines on stdin")
    p.add_argument("--serve", type=int, metavar="PORT", help="chat page for phone/PC on this port")
    p.add_argument("--gain", type=float, help="rtl_fm tuner gain in dB (default: auto)")
    p.add_argument("--mic-device", help="ffmpeg input (macOS ':0' or ':<name>', Linux pulse 'default')")
    p.add_argument("--mic-on-demand", action="store_true",
                   help="open the microphone only while the voice body is on (for an always-running mind)")
    p.add_argument("--whisper-cmd", default="whisper-cli")
    p.add_argument("--whisper-model", help="ggml model for whisper.cpp, e.g. ggml-small.bin")
    p.add_argument("--language", default="ja")
    p.add_argument("--silence-rms", type=float, default=300.0, help="speech threshold (int16 RMS)")
    p.add_argument("--reflex", choices=CHOICES["reflex"], help="saved setting otherwise (default rules)")
    p.add_argument("--designer", choices=CHOICES["designer"], help="saved setting otherwise (default claude)")
    p.add_argument("--jev-url", help=f"System One endpoint, default {JEV_CLOUD}; a local-jev server for the edge")
    p.add_argument("--local-url", help="OpenAI-compatible local LLM server, default http://localhost:8080/v1")
    p.add_argument("--local-model")
    p.add_argument("--ruminate-s", type=float, default=300.0, help="ruminate after this long without input")
    p.add_argument("--state", type=Path, default=ROOT / ".sesame-mind",
                   help="library.json, memory.jsonl, notes.md, config.json")
    p.add_argument("--robot", action="append", default=[], metavar="HOST",
                   help="tell this robot (e.g. sesame-s3-8b2c.local) where the mind is, so its page finds it")
    p.add_argument("--host", help="drive this robot now (saved setting otherwise; settings page can switch); "
                   "'sim' drives a MuJoCo stand-in shown on the chat page (needs --group dev)")
    args = p.parse_args(argv)
    sys.stdout, sys.stderr = CONSOLE.tee(sys.stdout), CONSOLE.tee(sys.stderr)
    audio = args.sdr is not None or args.mic or args.file
    if not (audio or args.text or args.serve):
        p.error("give an ear (--sdr/--mic/--file/--text) and/or --serve")
    if audio and not args.whisper_model:
        print("no --whisper-model: speech is not transcribed; the voice body still hears prosody", flush=True)

    settings = Settings(args.state)
    flags = {"reflex": args.reflex, "designer": args.designer, "jev_url": args.jev_url,
             "local_url": args.local_url, "local_model": args.local_model, "host": args.host}
    settings.update({k: v for k, v in flags.items() if v is not None} | ({"live": True} if args.host else {}))
    manifest = load_manifest()
    mind = Mind(RuleReflex(), Library(args.state / "library.json"), Memory(args.state), Spine(manifest))
    status = mind.configure(settings)
    print(f"mind: reflex {status['reflex']}, designer {status['designer']}, robot {status['robot'] or 'dry run'}"
          + (f"\n  ({status['error']})" if status["error"] else ""), flush=True)
    moments = queue.Queue(maxsize=4)

    def stopped(*_):
        raise KeyboardInterrupt  # launchd stops with SIGTERM: release the robot the same way

    signal.signal(signal.SIGTERM, stopped)
    try:
        if args.serve:
            serve(args.serve, mind, moments)
            threading.Thread(target=announce, args=(mind, args.robot, args.serve), daemon=True).start()
        if audio:
            threading.Thread(target=hear, args=(args, moments, mind.body), daemon=True).start()
        if args.text:
            def typed():
                for line in sys.stdin:
                    if line.strip():
                        offer(moments, Moment("chat", line.strip()))
                if not (audio or args.serve):
                    offer(moments, None)
            threading.Thread(target=typed, daemon=True).start()
        think(mind, moments, args.ruminate_s)
    except KeyboardInterrupt:
        if mind.spine.robot:
            print("> off (interrupted)", flush=True)
            mind.spine.robot.command("off")
        return 130
    finally:
        if mind.link:
            mind.link.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
