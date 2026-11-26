#!/usr/bin/env python3
"""Run Sesame S3 commands over Wi-Fi, in order, with the phone-console macro rules.

Standard-library only. Each argument (or ';'-separated part) is one firmware
command. "?cmd" tolerates ERR, "wait MS" pauses, and motion/run/rest/sweep wait
for completion while heartbeats keep the link alive. On exit the robot is left
as the commands left it: it freezes and holds after 500 ms, OFF after 600 s.

    python3 tools/sesame_remote.py --host sesame-s3-8b2c.local "?arm run" "motion stand"
    python3 tools/sesame_remote.py --host 192.168.4.1 status
"""
import argparse
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

WAITS = re.compile(r"^(motion|run|rest|sweep)\b")


class Robot:
    def __init__(self, host, timeout=3.0, resolve=socket.gethostbyname):
        self.base = host if host.startswith("http") else f"http://{host}"
        self.timeout = timeout
        self.lock = threading.Lock()  # the firmware serves one client at a time
        self.name = urllib.parse.urlsplit(self.base).hostname or ""
        self.resolve, self.ip = resolve, None

    def _url(self, path):
        """macOS mDNS lookups of *.local fail now and then and cost time on every
        request, so the address is looked up once and again only after a failure."""
        if not self.name.endswith(".local"):
            return self.base + path
        if self.ip is None:
            self.ip = self.resolve(self.name)
        return self.base.replace(self.name, self.ip, 1) + path

    def get(self, path):
        with self.lock:
            for attempt in (0, 1):
                try:
                    with urllib.request.urlopen(self._url(path), timeout=self.timeout) as r:
                        return True, r.read().decode()
                except urllib.error.HTTPError as e:
                    return False, e.read().decode()
                except OSError:
                    if attempt or not self.name.endswith(".local"):
                        raise
                    self.ip = None  # the robot may have a new address: look it up again
                    time.sleep(0.3)

    def command(self, text):
        return self.get("/cmd?c=" + urllib.parse.quote(text))

    def busy(self):
        _, text = self.get("/status")
        return " motion=none " not in text or " sweep=1 " in text


def start_heartbeat(robot):
    """Heartbeat every 200 ms until the returned event is set."""
    done = threading.Event()

    def beat():
        while not done.wait(0.2):
            try:
                robot.command("heartbeat")
            except OSError:
                pass

    threading.Thread(target=beat, daemon=True).start()
    return done


def split_lines(*commands):
    return [p.strip() for arg in commands for p in re.split(r"[;\n]", arg) if p.strip()]


def run_lines(robot, lines, motion_timeout=75.0, sleep=time.sleep):
    """Run macro lines in order; 0 on success, 1 at the first untolerated ERR or timeout."""
    for line in lines:
        tolerate = line.startswith("?")
        line = line.lstrip("?").strip()
        if m := re.fullmatch(r"wait\s+(\d+)", line):
            sleep(int(m[1]) / 1000)
            continue
        ok, text = robot.command(line)
        print(f"> {line}\n{text}" if text else f"> {line}", flush=True)
        if not ok and not tolerate:
            return 1
        if ok and WAITS.match(line):
            deadline = time.monotonic() + motion_timeout
            sleep(0.25)
            while robot.busy():
                if time.monotonic() > deadline:
                    print("ERR motion timeout; sending stop", flush=True)
                    robot.command("stop")
                    return 1
                sleep(0.25)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True, help="robot address, e.g. sesame-s3-8b2c.local or 192.168.4.1")
    parser.add_argument("--motion-timeout", type=float, default=75.0)
    parser.add_argument("commands", nargs="+")
    args = parser.parse_args()
    robot = Robot(args.host)
    done = start_heartbeat(robot)
    try:
        return run_lines(robot, split_lines(*args.commands), args.motion_timeout)
    except KeyboardInterrupt:
        print("> off (interrupted)", flush=True)
        robot.command("off")
        return 130
    except OSError as e:
        print(f"ERR no reply from {robot.base}: {e}", file=sys.stderr)
        return 2
    finally:
        done.set()


if __name__ == "__main__":
    sys.exit(main())
