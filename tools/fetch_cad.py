"""Fetch pinned upstream CAD assets without third-party Python dependencies."""

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
CAD = ROOT / "assets" / "cad"


def validate(data, entry):
    """Check bytes against the blob identity in the pinned upstream Git tree."""
    digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if len(data) != entry["bytes"] or digest != entry["git_blob_sha1"]:
        raise ValueError(f"Upstream content mismatch: {entry['path']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Check local files without networking")
    args = parser.parse_args()
    manifest = json.loads((CAD / "sources.json").read_text())
    cache = (CAD / "upstream").resolve()
    for entry in manifest["files"]:
        target = (cache / entry["path"]).resolve()
        if not target.is_relative_to(cache):
            raise ValueError(f"Path outside CAD cache: {entry['path']}")
        if target.exists():
            data = target.read_bytes()
            validate(data, entry)  # Preserve modified files rather than overwriting them.
            state = "verified"
        elif args.verify_only:
            raise FileNotFoundError(target)
        else:
            with urllib.request.urlopen(entry["url"], timeout=180) as response:
                data = response.read()
            validate(data, entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".part")
            temporary.write_bytes(data)
            temporary.replace(target)
            state = "downloaded"
        print(f"{state}: {entry['path']} ({len(data):,} bytes)")
    print(f"Verified {len(manifest['files'])} files from pinned upstream revisions.")


if __name__ == "__main__":
    main()
