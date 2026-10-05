#!/usr/bin/env python3
"""Pinned class build/flash entry point. Standard-library only; no automatic flash."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "firmware/toolchain.json").read_text())
BUILD = ROOT / "firmware/.build/sesame-s3"


def run(*args, capture=False):
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(filter(None, [env.get("PATH"), "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"]))
    # ctags on macOS requires an existing, writable TMPDIR. Honor the user's
    # directory (including OpenCode's private temp area); normalize trailing '/'.
    temp = tempfile.gettempdir() + os.sep
    env.update(TMPDIR=temp, TMP=temp, TEMP=temp)
    return subprocess.run(args, cwd=ROOT, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def cli(*args, capture=False):
    return run("arduino-cli", *args, capture=capture)


def check_cli():
    if not shutil.which("arduino-cli"):
        raise SystemExit("Install arduino-cli 1.5.1 for your OS/CPU; see firmware/README.md")
    info = json.loads(cli("version", "--format", "json", capture=True))
    if info["VersionString"] != LOCK["arduino_cli"]:
        raise SystemExit(f"Expected arduino-cli {LOCK['arduino_cli']}, found {info['VersionString']}")


def setup():
    cli("core", "update-index", "--additional-urls", LOCK["index_url"])
    cli("core", "install", LOCK["core"], "--additional-urls", LOCK["index_url"])
    for library, version in LOCK["libraries"].items():
        cli("lib", "install", "--no-deps", f"{library}@{version}")


def check_toolchain():
    data = json.loads(cli("core", "list", "--format", "json", capture=True))
    core_id, version = LOCK["core"].split("@")
    if not any(p["id"] == core_id and p["installed_version"] == version for p in data["platforms"]):
        raise SystemExit("Pinned ESP32 core missing; run setup")
    data = json.loads(cli("lib", "list", "--format", "json", capture=True))
    installed = {item["library"]["name"]: item["library"]["version"] for item in data["installed_libraries"]}
    for library, version in LOCK["libraries"].items():
        if installed.get(library) != version:
            raise SystemExit(f"Expected {library}@{version}; run setup")


def check_sources():
    record = json.loads((ROOT / "firmware/sesame-s3/vendor/provenance.json").read_text())
    for name, sha in record["sha256"].items():
        path = ROOT / "firmware/sesame-s3/vendor" / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise SystemExit(f"Vendored file hash mismatch: {name}")
    # Class firmware builds need only the pinned YAML reader, not the simulator.
    # Never silently regenerate canonical data while flashing a class robot.
    run("uv", "run", "--no-project", "--python", LOCK["host_python"], "--with",
        f"pyyaml=={LOCK['pyyaml']}", "python", "tools/generate_s3_firmware.py", "--check")


def build():
    check_toolchain(); check_sources()
    BUILD.mkdir(parents=True, exist_ok=True)
    cli("compile", "--clean", "--warnings", "all", "--fqbn", LOCK["fqbn"],
        "--build-path", str(BUILD), str(ROOT / "firmware/sesame-s3"))
    report = {"platform": platform.platform(), "toolchain": LOCK,
              "binaries_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in BUILD.glob("*.bin")}}
    (BUILD / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Build evidence: {BUILD / 'build-report.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "build", "flash", "console", "ports"])
    parser.add_argument("--port", help="Explicit USB port; never inferred for flashing")
    args = parser.parse_args()
    if args.action in ("flash", "console") and not args.port:
        parser.error("--port is required")
    if args.action == "console":
        run("uv", "run", "--no-project", "--python", LOCK["host_python"], "--with", f"pyserial=={LOCK['pyserial']}",
            "python", "tools/sesame_s3_console.py", "--port", args.port)
        return
    check_cli()
    if args.action == "setup": setup()
    elif args.action == "ports": cli("board", "list")
    else:
        build()
        if args.action == "flash":
            # Upload ALL generated flash images with the core's board recipe;
            # don't assume app-only 0x10000 or erase the NVS calibration sector.
            cli("upload", "--fqbn", LOCK["fqbn"], "--port", args.port,
                "--input-dir", str(BUILD), str(ROOT / "firmware/sesame-s3"))


if __name__ == "__main__":
    main()
