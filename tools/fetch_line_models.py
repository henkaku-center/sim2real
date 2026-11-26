"""Fetch the pinned third-party models of the line twin (manifest/line.yaml).

Each machine with a `commit` and a `fetch` entry is downloaded as that commit's
GitHub archive and only the listed paths are kept, under the ignored
assets/line/upstream/<dir>/. A `.commit` marker records what is cached.
Standard library and PyYAML only.

  uv run python tools/fetch_line_models.py                download what is missing
  uv run python tools/fetch_line_models.py --verify-only  check the cache, no network
"""

import argparse
import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "assets" / "line" / "upstream"


def fetch(machine: dict, target: Path) -> None:
    slug = machine["project"].removeprefix("https://github.com/").strip("/")
    url = f"https://codeload.github.com/{slug}/tar.gz/{machine['commit']}"
    with urllib.request.urlopen(url, timeout=300) as response:
        archive = tarfile.open(fileobj=io.BytesIO(response.read()), mode="r:gz")
    wanted = tuple(machine["fetch"]["paths"])
    staging = target.with_name(target.name + ".part")
    shutil.rmtree(staging, ignore_errors=True)
    for member in archive.getmembers():
        relative = member.name.split("/", 1)[1] if "/" in member.name else ""
        if not member.isfile() or not any(relative == w or relative.startswith(w + "/") for w in wanted):
            continue
        destination = (staging / relative).resolve()
        if not destination.is_relative_to(staging.resolve()):
            raise ValueError(f"path outside cache: {member.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.extractfile(member).read())
    (staging / ".commit").write_text(machine["commit"] + "\n")
    shutil.rmtree(target, ignore_errors=True)
    staging.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify-only", action="store_true", help="Check the cache without networking")
    args = parser.parse_args()
    line = yaml.safe_load((ROOT / "manifest" / "line.yaml").read_text())
    stale = False
    for name, machine in line["machines"].items():
        if "fetch" not in machine:
            continue
        target = CACHE / machine["fetch"]["dir"]
        marker = target / ".commit"
        current = marker.exists() and marker.read_text().strip() == machine["commit"]
        if current:
            state = "verified"
        elif args.verify_only:
            state, stale = "missing or at another commit", True
        else:
            fetch(machine, target)
            state = "downloaded"
        print(f"{name}: {state} ({machine['commit'][:12]})")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
