"""Pi-local playback and heartbeat. This module has no network imports."""
import json
import math
import re
import threading
import time

from .plan import require
from sesame_s3_console import HEARTBEAT_INTERVAL_SECONDS, open_device


class PlaybackError(RuntimeError):
    pass


class Cancelled(PlaybackError):
    pass


class SerialLink:
    """One response reader, a separately scheduled heartbeat, serialized writes."""
    def __init__(self, port, *, log=print):
        self.device = open_device(port)
        self.log = log
        self.buffer = b""
        self.write_lock = threading.Lock()
        self.finish = threading.Event()
        self.live_until = 0
        self.failure = None
        self.thread = threading.Thread(target=self._heartbeat, name="local-heartbeat", daemon=True)
        self.thread.start()

    def write(self, command):
        data = command.encode("ascii")
        if not data or len(data) > 159 or b"\n" in data or b"\r" in data:
            raise PlaybackError("invalid serial line (maximum 159 bytes, one command)")
        with self.write_lock:
            self.device.write(data + b"\n")

    def _heartbeat(self):
        while not self.finish.wait(HEARTBEAT_INTERVAL_SECONDS):
            try:
                with self.write_lock:
                    if self.live_until:
                        if time.monotonic() >= self.live_until:
                            self.live_until = 0
                            self.failure = PlaybackError("local playback lease expired")
                            self.device.write(b"off\n")
                        else:
                            self.device.write(b"heartbeat\n")
            except OSError:
                self.live_until = 0
                self.failure = PlaybackError("serial heartbeat failed; firmware watchdog must release outputs")
                return

    def begin_lease(self, seconds):
        if self.failure:
            raise self.failure
        with self.write_lock:
            self.live_until = time.monotonic() + seconds

    def line(self, deadline, cancel=None, *, tolerate_off=False):
        while time.monotonic() < deadline:
            if cancel and cancel.is_set():
                raise Cancelled("cancelled locally")
            if self.failure and not tolerate_off:
                raise self.failure
            if b"\n" not in self.buffer:
                self.buffer += self.device.read(4096)
                if len(self.buffer) > 16384:
                    raise PlaybackError("serial response buffer overflow")
            if b"\n" in self.buffer:
                data, self.buffer = self.buffer.split(b"\n", 1)
                line = data.decode("ascii", errors="replace").strip()
                if not line:
                    continue
                if not tolerate_off and line.startswith(("ERR", "CLAMP", "OFF", "READY")):
                    raise PlaybackError("robot: " + line)
                return line
            time.sleep(.002)
        raise TimeoutError("serial response deadline exceeded")

    def expect(self, expected, deadline, cancel=None, *, tolerate_off=False):
        while True:
            line = self.line(deadline, cancel, tolerate_off=tolerate_off)
            if line.startswith(expected):
                return line
            if line.startswith("ERR"):
                raise PlaybackError("robot: " + line)

    def command(self, command, expected, cancel=None, timeout=.7):
        self.write(command)
        return self.expect(expected, time.monotonic() + timeout, cancel)

    def off(self):
        with self.write_lock:
            self.live_until = 0
            self.device.write(b"off\n")
        self.expect("OK OFF", time.monotonic() + .7, tolerate_off=True)

    def status(self, cancel=None):
        header = self.command("status", "mode=", cancel)
        fields = dict(item.split("=", 1) for item in header.split())
        rows = {}
        deadline = time.monotonic() + .7
        for _ in range(int(fields["outputs"]).bit_count()):
            line = self.line(deadline, cancel)
            match = re.fullmatch(r"CH(\d+) current=([-\d.]+) target=([-\d.]+) physical=([-\d.]+) us=([-\d.]+)", line)
            if not match:
                raise PlaybackError("invalid robot status row")
            rows[int(match[1])] = (float(match[2]), float(match[3]))
        return fields, rows

    def close(self):
        try:
            self.off()
        except (OSError, TimeoutError, PlaybackError):
            self.log("OFF could not be acknowledged; no more heartbeats; firmware watchdog releases outputs.")
        finally:
            self.finish.set()
            self.thread.join(timeout=1)
            self.device.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Player:
    def __init__(self, link, catalog, *, log=print):
        self.link, self.catalog, self.log = link, catalog, log
        self.lock = threading.Lock()

    def preflight(self, plan, cancel):
        """Check the device's actual saved overlay without changing it."""
        raw = self.link.command("export", "{", cancel)
        try:
            calibration = json.loads(raw)
            require(calibration["manifest_id"] == self.catalog.interface["manifest_id"], "device manifest differs from demo checkout")
            entries = calibration["joints"]
            require([e["name"] for e in entries] == self.catalog.order, "device joint order differs")
            channels = [e["channel"] for e in entries]
            require(sorted(channels) == list(range(8)), "device calibration needs eight unique channels")
            for e in entries:
                require(e["verified"] is True, "device reports unverified calibration; arm run cannot play it")
                require(e["sign"] in (-1, 1) and type(e["trim_deg"]) in (int, float) and
                        math.isfinite(e["trim_deg"]) and abs(e["trim_deg"]) <= 15, "invalid device calibration")
                require(len(e["limits_deg"]) == 2 and 0 <= e["limits_deg"][0] <= 90 <= e["limits_deg"][1] <= 180,
                        "invalid device limits")
            by_name = {e["name"]: e for e in entries}
            targets = [dict(zip(self.catalog.order, self.catalog.rest))]
            for step in plan["steps"]:
                if step["type"] == "pose":
                    targets.append(dict(zip(self.catalog.order, step["angles"])))
                elif step["type"] in ("motion", "rest"):
                    targets.extend(t for t, _ in self.catalog.expand(step.get("name", "rest")))
            for target in targets:
                for name, angle in target.items():
                    e = by_name[name]
                    physical = 90 + e["trim_deg"] + e["sign"] * self.catalog.entries[name]["sign"] * (angle - 90)
                    require(e["limits_deg"][0] <= angle <= e["limits_deg"][1] and 0 <= physical <= 180,
                            f"device would clamp {name} {angle}; its saved calibration differs; nothing played")
            return channels
        except (ValueError, KeyError, TypeError) as exc:
            raise PlaybackError("calibration: " + str(exc)) from exc

    def settled(self, target, channels, deadline, cancel):
        while time.monotonic() < deadline:
            status, rows = self.link.status(cancel)
            if status["mode"] != "5" or status["fault"] != "0" or status["hub"] != "1":
                raise PlaybackError("robot left healthy run mode")
            if len(rows) != 8:
                raise PlaybackError("robot did not enable all pose channels")
            for channel, angle in zip(channels, target):
                if channel not in rows or abs(rows[channel][1] - angle) > .02:
                    raise PlaybackError("robot target mismatch/clamp")
            if all(abs(current - goal) <= .02 for current, goal in rows.values()):
                return
            if cancel.wait(.02):
                raise Cancelled("cancelled locally")
        raise TimeoutError("pose did not settle before its local deadline")

    def hold(self, seconds, cancel):
        end = time.monotonic() + seconds
        # Read unsolicited OFF/ERR/CLAMP throughout a hold, not just at the end.
        while time.monotonic() < end:
            try:
                self.link.line(min(end, time.monotonic() + .05), cancel)
            except TimeoutError:
                pass

    def play(self, plan, cancel=None):
        cancel = cancel or threading.Event()
        with self.lock:
            try:
                self.link.off()
                budgets = self.catalog.validate(plan)  # distrust even authenticated server data
                if cancel.is_set():
                    raise Cancelled("cancelled locally")
                channels = self.preflight(plan, cancel)
                self.link.begin_lease(sum(budgets) / 1000 + 2)
                self.link.command("arm run", "OK ARMED", cancel)
                previous = list(self.catalog.rest)
                for step, budget in zip(plan["steps"], budgets):
                    self.log("PLAY " + json.dumps(step, ensure_ascii=False))
                    deadline = time.monotonic() + budget / 1000
                    kind = step["type"]
                    if kind in ("motion", "rest"):
                        name = step.get("name", "rest")
                        self.link.command("rest" if kind == "rest" else "motion " + name, "OK MOTION " + name, cancel)
                        self.link.expect("OK MOTION complete", deadline, cancel)
                        _, previous = self.catalog.motion_timing(name, previous)
                        self.settled(previous, channels, deadline + .1, cancel)
                    elif kind == "face":
                        self.link.command("face " + step["name"], "OK FACE", cancel)
                        self.hold(step["hold_ms"] / 1000, cancel)
                    else:
                        started = time.monotonic()
                        duration = step["duration_ms"] / 1000
                        while True:
                            fraction = min(1, (time.monotonic() - started) / duration)
                            angles = [round(a + fraction * (b-a), 3) for a, b in zip(previous, step["angles"])]
                            self.catalog.check_pose(angles)  # check every interpolated target before send
                            self.link.command("pose " + " ".join(f"{v:.3f}" for v in angles), "OK TARGETS", cancel)
                            if fraction == 1:
                                break
                            if time.monotonic() >= deadline:
                                raise TimeoutError("pose playback deadline exceeded")
                            self.hold(min(.05, max(0, duration - (time.monotonic() - started))), cancel)
                        previous = list(step["angles"])
                        self.settled(previous, channels, deadline - step["hold_ms"] / 1000, cancel)
                        self.hold(step["hold_ms"] / 1000, cancel)
                self.log("PLAY complete (commanded motion; no physical feedback)")
            finally:
                self.link.off()
                self.log("OUTPUTS OFF")
