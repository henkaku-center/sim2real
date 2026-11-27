#!/usr/bin/env python3
"""Keep sesame mind running on this Mac or Linux box, so the robot's page always finds it.

launchd (macOS) or a systemd user unit (Linux, e.g. a Raspberry Pi) starts the mind
at login/boot and restarts it if it dies. The mind tells the
robot its URL every 10 s, so turning the robot on (or opening its page) is all
it takes. The microphone opens only while 声で動く is on.

    python3 tools/sesame_mind_agent.py install     # once; survives reboots
    python3 tools/sesame_mind_agent.py restart     # after pulling new code or signing in with `ant auth login`
    python3 tools/sesame_mind_agent.py status | log | uninstall

The agent runs whatever is checked out in this working tree. Claude credentials
come from `ant auth login` (launchd does not see shell exports); on Linux the unit
also reads `ANTHROPIC_API_KEY=...` from `.sesame-mind/env` if that file exists.

On Linux run `sudo loginctl enable-linger $USER` once so the unit starts at boot
without anyone logging in. Pick the microphone with `--mic alsa:plughw:CARD=X,DEV=0`
(`arecord -l` lists cards) when there is no PulseAudio/PipeWire.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

LABEL = "com.sesame.mind"
ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".sesame-mind"
LOG = STATE / "mind.log"
TARGET = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
DOMAIN = f"gui/{os.getuid()}"
UNIT = "sesame-mind.service"
UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / UNIT
MAC_MIC, LINUX_MIC = ":MacBook Airのマイク", "pulse:default"


def command(robot, mic, port, whisper, groups=("radio", "dev")):
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    args = [uv, "run", "--project", str(ROOT), *[x for g in groups for x in ("--group", g)], "python",
            str(ROOT / "tools" / "sesame_mind.py"), "--mic", "--mic-on-demand", "--mic-device", mic,
            "--serve", str(port), "--robot", robot]
    if whisper and Path(whisper).expanduser().exists():
        args += ["--whisper-model", str(Path(whisper).expanduser())]
    path = os.pathsep.join([str(Path(uv).parent), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"])
    return args, path


def plist(robot, mic, port, whisper):
    args, path = command(robot, mic, port, whisper)
    return {"Label": LABEL, "ProgramArguments": args, "WorkingDirectory": str(ROOT),
            "EnvironmentVariables": {"PATH": path, "PYTHONUNBUFFERED": "1"},
            "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10,
            "StandardOutPath": str(LOG), "StandardErrorPath": str(LOG)}


def unit(robot, mic, port, whisper):
    """systemd user unit; only the radio group, so a Pi needs no CAD/test wheels."""
    args, path = command(robot, mic, port, whisper, groups=("radio",))
    # systemd expands % specifiers and $VARs in ExecStart; double them, then quote words
    quoted = " ".join(shlex.quote(x.replace("%", "%%").replace("$", "$$")) for x in args)
    return f"""[Unit]
Description=Sesame mind (tools/sesame_mind.py)
Wants=network-online.target
After=network-online.target sound.target

[Service]
WorkingDirectory={ROOT}
Environment=PATH={path}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-{STATE / "env"}
ExecStart={quoted}
StandardOutput=append:{LOG}
StandardError=append:{LOG}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""


def systemctl(*args, check=False):
    r = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"systemctl --user {' '.join(args)} failed ({r.returncode}): {(r.stderr or r.stdout).strip()}")
    return r


def linux(a):
    if a.command in ("install", "plist"):
        text = unit(a.robot, a.mic or LINUX_MIC, a.port, a.whisper_model)
        if a.command == "plist":
            sys.stdout.write(text)
            return 0
        STATE.mkdir(exist_ok=True)
        UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        UNIT_PATH.write_text(text)
        systemctl("daemon-reload", check=True)
        systemctl("enable", UNIT, check=True)
        systemctl("restart", UNIT, check=True)
        print(f"installed {UNIT_PATH}\nlog: {LOG}\nfor start at boot: sudo loginctl enable-linger {os.environ.get('USER', '$USER')}")
    elif a.command == "uninstall":
        systemctl("disable", "--now", UNIT)
        UNIT_PATH.unlink(missing_ok=True)
        systemctl("daemon-reload")
        print("uninstalled")
    elif a.command == "restart":
        systemctl("restart", UNIT, check=True)
        print("restarted")
    elif a.command == "status":
        r = systemctl("show", UNIT, "-p", "ActiveState", "-p", "SubState", "-p", "MainPID", "-p", "NRestarts")
        print(r.stdout.strip() if UNIT_PATH.exists() else "not installed")
    else:
        os.execvp("tail", ["tail", "-n", "40", "-f", str(LOG)])
    return 0


def launchctl(*args, check=False):
    r = subprocess.run(["launchctl", *args], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"launchctl {' '.join(args)} failed ({r.returncode}): {(r.stderr or r.stdout).strip()}")
    return r


def unload(timeout_s=15.0):
    """bootout returns before the old mind has exited; bootstrap fails (5) until it has."""
    launchctl("bootout", f"{DOMAIN}/{LABEL}")
    deadline = time.monotonic() + timeout_s
    while launchctl("print", f"{DOMAIN}/{LABEL}").returncode == 0:
        if time.monotonic() > deadline:
            raise SystemExit(f"{LABEL} is still running; try again in a moment")
        time.sleep(0.3)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("install", "uninstall", "restart", "status", "log", "plist"))
    p.add_argument("--robot", default="sesame-s3-8b2c.local")
    p.add_argument("--mic", help=f"ffmpeg input: macOS avfoundation (default {MAC_MIC!r}); "
                   f"Linux pulse:NAME or alsa:DEVICE (default {LINUX_MIC!r})")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--whisper-model", default="~/models/whisper/ggml-small.bin", help="used if the file exists")
    a = p.parse_args(argv)
    if sys.platform.startswith("linux"):
        return linux(a)
    if a.command in ("install", "plist"):
        data = plistlib.dumps(plist(a.robot, a.mic or MAC_MIC, a.port, a.whisper_model))
        if a.command == "plist":
            sys.stdout.write(data.decode())
            return 0
        STATE.mkdir(exist_ok=True)
        unload()  # replace an older copy
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_bytes(data)
        launchctl("bootstrap", DOMAIN, str(TARGET), check=True)
        print(f"installed {TARGET}\nlog: {LOG}")
    elif a.command == "uninstall":
        unload()
        TARGET.unlink(missing_ok=True)
        print("uninstalled")
    elif a.command == "restart":
        launchctl("kickstart", "-k", f"{DOMAIN}/{LABEL}", check=True)
        print("restarted")
    elif a.command == "status":
        r = launchctl("print", f"{DOMAIN}/{LABEL}")
        lines = [s.strip() for s in r.stdout.splitlines() if s.strip().startswith(("state =", "pid =", "last exit"))]
        print("\n".join(lines) if r.returncode == 0 else "not installed")
    else:
        os.execvp("tail", ["tail", "-n", "40", "-f", str(LOG)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
