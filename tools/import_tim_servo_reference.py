#!/usr/bin/env python3
"""Import the instructor-authorised, pinned Tim servo reference (not a flasher).

Uses the existing authenticated GitHub CLI. Never imports local OTA credentials.
Four independent reads share a maximum of four workers; files are written only
after every fetch succeeds. Retains the original relative include layout.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'reference/vendor/tim-servo-debug'
REPO = 'tim003/CIT_FC_Robotics'
REVISION = '98d030a2d1e2e2e1f195669a9f87fcf9c5f1d465'
FILES = (
    'firmware/test/robotics_esp32s3/robotics_esp32s3.ino',
    'firmware/test/robotics_esp32s3/robotics_esp32s3_servo_map.h',
    'firmware/common/sesame_servo_map.h',
    'firmware/sesame-s3-pca9685/README.md',
)


def fetch(path):
    record = json.loads(subprocess.check_output(
        ['gh', 'api', f'repos/{REPO}/contents/{path}?ref={REVISION}'], timeout=45))
    if record.get('encoding') != 'base64' or record.get('type') != 'file':
        raise ValueError(f'Unexpected GitHub content for {path}')
    data = base64.b64decode(record['content'])
    blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    if blob != record['sha']:
        raise ValueError(f'Git blob mismatch: {path}')
    return path, data, {'git_blob': blob, 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    with ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(fetch, FILES))
    for path, data, _ in fetched:
        target = DEST / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    source = {
        'repository': REPO, 'revision': REVISION, 'imported_on': '2026-10-11',
        'permission': 'Instructor confirmed permission to republish/adapt on 2026-10-11',
        'upstream_license': 'No repository licence declared; retain permission/provenance notice',
        'purpose': 'Unmodified reference, not the approved classroom flashing target',
        'files': {path: digest for path, _, digest in fetched},
    }
    (DEST / 'SOURCE.json').write_text(json.dumps(source, indent=2) + '\n')
    print(f'Imported {len(fetched)} pinned reference files into {DEST}')


if __name__ == '__main__':
    main()
