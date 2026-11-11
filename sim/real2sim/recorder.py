"""Play a pose/motion sequence through the firmware console and log the run.

The recorder speaks the reference firmware's text commands (``export``,
``arm run``, ``pose D0..D7``, ``heartbeat``, ``status``, ``off`` — see
firmware/sesame-s3/controller.cpp) over one of three transports:

- ``LineTransport``: a serial device opened by tools/sesame_s3_console.py
- ``HttpTransport``: the firmware's Wi-Fi console (``/cmd?c=``), for runs on
  battery power with USB unplugged
- ``SimulatedFirmware``: a host-side stand-in, for dry runs and tests

It does not flash, does not change firmware, and never retries a refused
command. A command acknowledgement is not physical confirmation: the log
records what was sent and what the device answered, nothing more.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from sim.manifest import Manifest, load_manifest
from sim.motions import Event, flatten, load_motions
from sim.real2sim import runlog

SEQUENCES_PATH = Path(__file__).parent / "sequences.yaml"
PREAMBLE_REST_S = 2.0  # every run starts with "rest, hold": the alignment window
MAX_LINE_BYTES = 159  # firmware CommandLine buffer is 160 including the terminator


class RecorderError(RuntimeError):
    """The device refused or dropped the run. Outputs are commanded off; no log is written."""


# ---- sequences -------------------------------------------------------------


def sequence_names(manifest: Manifest | None = None) -> list[str]:
    manifest = manifest or load_manifest()
    own = yaml.safe_load(SEQUENCES_PATH.read_text())["sequences"]
    return sorted({*own, *load_motions()["motions"], *manifest.raw["poses"]})


def sequence_events(name: str, manifest: Manifest | None = None) -> list[Event]:
    """Named sequence -> merged events, preceded by the rest preamble.

    Looks in sequences.yaml first, then the stock motions, then named poses.
    """
    manifest = manifest or load_manifest()
    poses = manifest.raw["poses"]
    own = yaml.safe_load(SEQUENCES_PATH.read_text())["sequences"]
    motions = load_motions()["motions"]
    if name in own:
        steps = own[name]
    elif name in motions:
        steps = motions[name]
    elif name in poses:
        steps = [{"pose": name}, {"wait": 1000}]
    else:
        raise KeyError(f"unknown sequence {name!r}; choose from {', '.join(sequence_names(manifest))}")
    preamble = [{"pose": "rest"}, {"wait": PREAMBLE_REST_S * 1000.0}]
    return flatten(preamble + list(steps), poses)


def firmware_timing(events: list[Event], rate_deg_s: float | None, neutral_deg: float = 90.0) -> list[Event]:
    """Delay each event until the previous move has finished ramping.

    Mirrors the reference firmware's own ``motion`` playback, which waits for
    the slew-limited outputs to settle before it starts counting a step's
    wait. Without a ramp (``rate_deg_s`` None) the timing is unchanged.
    """
    if not rate_deg_s:
        return list(events)
    current: dict[str, float] = {}
    out, shift, travel_ms = [], 0.0, 0.0
    for event in events:
        shift += travel_ms  # the previous move must finish before this event's clock runs on
        out.append(Event(event.time_ms + shift, dict(event.targets_deg)))
        travel = max(abs(deg - current.get(name, neutral_deg)) for name, deg in event.targets_deg.items())
        current.update(event.targets_deg)
        travel_ms = travel / rate_deg_s * 1000.0
    if out and travel_ms:  # let the last move complete inside the log
        out.append(Event(out[-1].time_ms + travel_ms, {}))
    return out


# ---- transports ------------------------------------------------------------


class LineTransport:
    """Line protocol over a pyserial-like device (write/read/close)."""

    evidence = "measured"

    def __init__(self, device, name: str = "serial"):
        self.device, self.name, self._buffer = device, name, b""

    def write(self, text: str) -> None:
        data = text.encode()
        if len(data) > MAX_LINE_BYTES:
            raise RecorderError(f"command exceeds the firmware line length: {text[:40]}…")
        self.device.write(data + b"\n")

    def read_lines(self) -> list[str]:
        self._buffer += self.device.read(4096)
        lines = []
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            lines.append(line.decode(errors="replace").rstrip("\r"))
        if len(self._buffer) > 8192:
            self._buffer = b""  # bound garbage from a wrong baud rate or firmware
        return [line for line in lines if line]

    def close(self) -> None:
        self.device.close()


class HttpTransport:
    """The firmware's AP console: GET http://<host>/cmd?c=<command>."""

    evidence = "measured"

    def __init__(self, host: str = "192.168.4.1", timeout_s: float = 0.35):
        self.name, self.host, self.timeout_s, self._lines = "http", host, timeout_s, []

    def write(self, text: str) -> None:
        url = f"http://{self.host}/cmd?c={urllib.parse.quote(text)}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_s) as response:
                body = response.read().decode(errors="replace")
        except urllib.error.HTTPError as error:  # firmware answers ERR with HTTP 400
            body = error.read().decode(errors="replace")
        except OSError as error:
            raise RecorderError(f"no answer from http://{self.host} ({error}); outputs time out after 500 ms") from error
        self._lines += [line for line in body.splitlines() if line]

    def read_lines(self) -> list[str]:
        lines, self._lines = self._lines, []
        return lines

    def close(self) -> None:
        pass


class SimulatedFirmware:
    """Stand-in for firmware/sesame-s3 covering the commands the recorder uses.

    Same replies, ramp (``controller_rate_deg_s``), clamps and 500 ms
    watchdog as the reference controller. It drives no hardware: logs made
    with it are labelled ``dry-run``.
    """

    evidence = "dry-run"
    name = "sim"

    def __init__(self, manifest: Manifest | None = None, clock=time.monotonic,
                 calibrated: bool = True, limits_deg: dict[str, tuple[float, float]] | None = None):
        self.manifest = manifest or load_manifest()
        self.clock = clock
        hw = self.manifest.raw["hardware_profiles"]["sesame_s3"]
        self.rate = float(hw["controller_rate_deg_s"])
        self.watchdog_s = 0.5
        self.calibrated = calibrated
        self.channels = hw["intended_channels"]
        self.limits = {j.name: tuple(j.limits_deg) for j in self.manifest.joints}
        self.limits.update(limits_deg or {})
        neutral = self.manifest.neutral_deg
        self.current = {j.name: neutral for j in self.manifest.joints}
        self.target = dict(self.current)
        self.enabled: set[str] = set()
        self.armed = False
        self.last_heartbeat = self.last_step = clock()
        self._lines: list[str] = []

    def _advance(self) -> None:
        now = self.clock()
        if self.armed and now - self.last_heartbeat > self.watchdog_s:
            self._off()
            self._lines.append("OFF watchdog >500ms")
        if self.armed:
            step = self.rate * (now - self.last_step)
            for name in self.current:
                delta = self.target[name] - self.current[name]
                self.current[name] += min(max(delta, -step), step)
        self.last_step = now

    def _off(self) -> None:
        self.armed = False
        self.enabled.clear()

    def write(self, text: str) -> None:
        self._advance()
        reply = self._dispatch(text.split())
        if reply:
            self._lines += reply.splitlines()

    def _dispatch(self, words: list[str]) -> str:
        if not words:
            return "ERR malformed/too long"
        now, names = self.clock(), [j.name for j in self.manifest.joints]
        if words == ["off"]:
            self._off()
            return "OFF command\nOK OFF"
        if words == ["heartbeat"]:
            if self.armed:
                self.last_heartbeat = now
            return ""
        if words == ["export"]:
            joints = [{"name": n, "channel": self.channels[n], "sign": 1, "trim_deg": 0.0,
                       "limits_deg": list(self.limits[n]), "verified": self.calibrated} for n in names]
            return json.dumps({"version": 1, "manifest_id": "simulated", "oscillator_hz": 25000000,
                               "joints": joints}, separators=(",", ":"))
        if words == ["status"]:
            lines = [f"mode={5 if self.armed else 0} outputs={len(self.enabled)} hub=1 fault=0 "
                     f"owner={1 if self.armed else 0} motion=none profile=simulated"]
            lines += [f"CH{self.channels[n]} current={self.current[n]:.2f} target={self.target[n]:.2f}"
                      for n in names if n in self.enabled]
            return "\n".join(lines)
        if words == ["arm", "run"]:
            if self.armed:
                return "ERR hub fault or already armed; off first"
            if not self.calibrated:
                return "ERR arm: select valid channel/joint; run needs all verified+saved"
            self.armed, self.last_heartbeat = True, now
            neutral = self.manifest.neutral_deg
            self.current = {n: neutral for n in names}
            self.target = dict(self.current)
            return "OK ARMED outputs OFF until target"
        if words[0] == "pose" and len(words) == 9:
            if not self.armed:
                return "ERR arm run first"
            try:
                values = [float(w) for w in words[1:]]
            except ValueError:
                return "ERR pose numbers"
            for name, value in zip(names, values):
                low, high = self.limits[name]
                self.target[name] = min(max(value, low), high)
            self.enabled.update(names)
            self.last_heartbeat = now
            return "OK TARGETS (soft/measured/electrical clamps applied)"
        return "ERR unknown command or requires OFF" if self.armed else "ERR syntax; help"

    def read_lines(self) -> list[str]:
        self._advance()
        lines, self._lines = self._lines, []
        return lines

    def close(self) -> None:
        pass


class FakeClock:
    """Deterministic clock for instant dry runs: sleeping advances time."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(seconds, 0.0)


# ---- the recorder ----------------------------------------------------------


def _format_degrees(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _export_limits(lines: list[str]) -> dict[str, tuple[float, float]]:
    for line in lines:
        if line.startswith('{"version"'):
            try:
                return {j["name"]: (float(j["limits_deg"][0]), float(j["limits_deg"][1]))
                        for j in json.loads(line)["joints"]}
            except (ValueError, KeyError, TypeError, IndexError):
                return {}
    return {}


def record(transport, sequence: str, *, manifest: Manifest | None = None,
           slew_rate_deg_s: float | None | str = "manifest", settle: bool = True,
           clock=time.monotonic, sleep=time.sleep, heartbeat_s: float = 0.1,
           status_s: float = 0.5, tail_s: float = 1.0, note: str = "") -> tuple[dict, list[dict]]:
    """Run ``sequence`` and return (header, records) of a valid run log.

    ``slew_rate_deg_s`` is the ramp the command interface applies to targets:
    the manifest's ``controller_rate_deg_s`` by default, ``None`` for a build
    that jumps straight to the target. The fit reproduces this ramp, so it
    must describe the firmware that was actually running.
    """
    manifest = manifest or load_manifest()
    names = [j.name for j in manifest.joints]
    if slew_rate_deg_s == "manifest":
        slew_rate_deg_s = float(manifest.raw["hardware_profiles"]["sesame_s3"]["controller_rate_deg_s"])
    events = sequence_events(sequence, manifest)
    if settle:
        events = firmware_timing(events, slew_rate_deg_s, manifest.neutral_deg)

    start = clock()
    records: list[dict] = []
    replies: list[str] = []
    state = {"heartbeat": -1e9, "status": 0.0, "heartbeats": 0, "armed": False}

    def now() -> float:
        return round(clock() - start, 6)

    def pump() -> list[str]:
        lines = transport.read_lines()
        for line in lines:
            records.append({"type": "reply", "t": now(), "clock": "host", "text": line})
        replies.extend(lines)
        if state["armed"] and any(line.startswith("OFF") for line in lines):
            raise RecorderError(f"device released the outputs mid-run: {lines}")
        return lines

    def send(text: str, **extra) -> None:
        records.append({"type": "command", "t": now(), "clock": "host", "text": text, **extra})
        transport.write(text)

    def wait_until(deadline: float, until=None) -> bool:
        while True:
            lines = pump()
            if until and any(until(line) for line in lines):
                return True
            t = now()
            if t >= deadline:
                return False
            if state["armed"] and t - state["heartbeat"] >= heartbeat_s:
                transport.write("heartbeat")  # counted, not logged line by line
                state["heartbeat"], state["heartbeats"] = t, state["heartbeats"] + 1
            if state["armed"] and status_s and t - state["status"] >= status_s:
                send("status")
                state["status"] = t
            sleep(min(0.005, max(deadline - t, 1e-4)))  # always advance, even on float dust

    clamped: dict[str, list[float]] = {}
    try:
        send("export")
        wait_until(now() + 0.3)
        limits = _export_limits(replies)
        send("arm run")
        if not wait_until(now() + 1.0, until=lambda line: line.startswith(("OK ARMED", "ERR"))) \
                or not any(line.startswith("OK ARMED") for line in replies):
            refusal = next((line for line in reversed(replies) if line.startswith("ERR")), "no reply to 'arm run'")
            raise RecorderError(f"device did not arm: {refusal}")
        state["armed"] = True
        sequence_start = now()
        pose = {name: manifest.neutral_deg for name in names}
        for event in events:
            wait_until(sequence_start + event.time_ms / 1000.0)
            if not event.targets_deg:
                continue
            requested = {name: float(deg) for name, deg in event.targets_deg.items()}
            for name, deg in requested.items():
                low, high = limits.get(name, (0.0, 180.0))
                pose[name] = min(max(deg, low), high)
                if pose[name] != deg:
                    clamped[name] = [deg, pose[name]]
            # The log holds the EFFECTIVE targets (after the device's exported limits).
            send("pose " + " ".join(_format_degrees(pose[name]) for name in names), targets_deg=dict(pose))
        wait_until(sequence_start + events[-1].time_ms / 1000.0 + tail_s)
    finally:
        state["armed"] = False
        try:
            send("off")
            wait_until(now() + 0.2)
        except RecorderError:
            pass

    errors = [line for line in replies if line.startswith("ERR")]
    header = runlog.make_header(
        evidence=transport.evidence,
        joints=names,
        command_interface={
            "transport": transport.name,
            "firmware": "firmware/sesame-s3 text console",
            "mode": "run",
            "slew_rate_deg_s": slew_rate_deg_s,
            "firmware_like_timing": bool(settle and slew_rate_deg_s),
        },
        sequence={"name": sequence, "preamble_rest_s": PREAMBLE_REST_S,
                  "start_host_s": sequence_start, "duration_s": round(events[-1].time_ms / 1000.0 + tail_s, 6)},
        recorder={"heartbeats_sent": state["heartbeats"], "heartbeat_period_s": heartbeat_s,
                  "device_errors": errors, "clamped_deg": clamped,
                  "acknowledgement_is_not_physical_confirmation": True},
        created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        note=note,
    )
    return header, records


def dry_run(sequence: str, **kwargs) -> tuple[dict, list[dict]]:
    """Instant, deterministic recording against the simulated firmware."""
    clock = FakeClock()
    firmware = SimulatedFirmware(kwargs.get("manifest"), clock=clock)
    kwargs.setdefault("slew_rate_deg_s", firmware.rate)
    return record(firmware, sequence, clock=clock, sleep=clock.sleep, **kwargs)
