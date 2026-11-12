"""Native numerical safety tests; no ESP32, servo or RF result is implied."""
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
# Identities whose saved records stay readable, oldest first. The last one was
# in force until the course hip limits replaced the Sesame Studio values.
READABLE_IDS = ["e669b916d178ac0a", "bd7675604b98ae46", "8d75c0ea0b2c68e7"]


def compile_native(tmp_path, source, name):
    binary = tmp_path / name
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    "-I", str(ROOT / "firmware/sesame-s3"),
                    str(ROOT / "tests/firmware" / source), "-o", str(binary)], check=True)
    return binary


def test_generated_contract_is_current():
    subprocess.run([sys.executable, "tools/generate_s3_firmware.py", "--check"], cwd=ROOT, check=True)


def test_native_safeaction(tmp_path):
    subprocess.run([str(compile_native(tmp_path, "test_s3_native.cpp", "s3-test"))], check=True)


def nvs_record(manifest_id, *, magic=0x53334331, low=None, padding=0, break_checksum=False):
    """One saved record as the earlier firmware wrote it: packed here, not by the firmware header.

    Little-endian `magic, manifest[17], pad[3] | version, oscillator, channel[8],
    sign[8], trim[8], low[8], high[8], verified, pad[3] | checksum`, 152 bytes,
    FNV-1a over the first 148. Hip limits are the widest the earlier manifests
    allowed (R1/L2 45..180, R2/L1 0..135); order R1 R2 L1 L2 R4 R3 L3 L4.
    """
    signs = [joint["sign"] for joint in yaml.safe_load((ROOT / "manifest/robot.yaml").read_text())["joints"]]
    body = struct.pack("<I17s3x", magic, manifest_id.encode()) + struct.pack(
        "<II8b8b8f8f8fB3B", 1, 26123456, *[7, 6, 5, 4, 3, 2, 1, 0], *signs,
        *[1.5, -2.0, 0.25, 3.0, 0.0, -0.5, 4.0, -4.0],
        *(low or [45, 0, 0, 45, 10, 0, 0, 0]), *[180, 135, 135, 180, 170, 180, 180, 180], 255, *[padding] * 3)
    assert len(body) == 148
    checksum = 2166136261
    for byte in body:
        checksum = ((checksum ^ byte) * 16777619) & 0xFFFFFFFF
    return body + struct.pack("<I", checksum ^ (1 if break_checksum else 0))


def test_saved_calibration_loads_unchanged_when_stored_limits_exceed_soft_limits(tmp_path):
    header = (ROOT / "firmware/sesame-s3/manifest_generated.h").read_text()
    current = re.search(r'MANIFEST_ID\[\] = "([0-9a-f]{16})"', header)[1]
    listed = re.findall(r'"([0-9a-f]{16})"', re.search(r'COMPATIBLE_MANIFEST_IDS\[\] = \{(.*)\}', header)[1])
    assert listed == READABLE_IDS and current not in listed
    # The premise of this test: today's soft limits are narrower than the stored ones.
    low = [int(v) for v in re.search(r'SOFT_LOW\[\] = \{(.*)\}', header)[1].split(",")]
    high = [int(v) for v in re.search(r'SOFT_HIGH\[\] = \{(.*)\}', header)[1].split(",")]
    assert (low, high) == ([80, 0, 0, 80, 0, 0, 0, 0], [180, 100, 100, 180, 180, 180, 180, 180])
    records = {f"accept-{identity}.bin": nvs_record(identity) for identity in listed + [current]}
    records["accept-nonzero-padding.bin"] = nvs_record(listed[-1], padding=0xAA)
    records["reject-unknown-identity.bin"] = nvs_record("0000000000000000")
    records["reject-checksum.bin"] = nvs_record(listed[-1], break_checksum=True)
    records["reject-magic.bin"] = nvs_record(listed[-1], magic=0x53334332)
    records["reject-below-servo-range.bin"] = nvs_record(listed[-1], low=[-1, 0, 0, 45, 10, 0, 0, 0])
    records["reject-excludes-neutral.bin"] = nvs_record(listed[-1], low=[91, 0, 0, 45, 10, 0, 0, 0])
    paths = []
    for name, data in records.items():
        assert len(data) == 152
        (tmp_path / name).write_bytes(data)
        paths.append(str(tmp_path / name))
    binary = compile_native(tmp_path, "test_s3_saved_calibration.cpp", "s3-saved-calibration-test")
    result = subprocess.run([str(binary), *paths], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "S3 saved-calibration tests passed: 5 loaded as stored, 5 refused"


def test_interface_states_what_happens_to_stored_limits():
    interface = json.loads((ROOT / "reference/sesame-s3-interface.json").read_text())
    compatibility = interface["calibration_compatibility"]
    assert compatibility["read_manifest_ids"] == READABLE_IDS
    assert "neither clamped nor rewritten" in compatibility["stored_limits"]
    hips = {joint["name"]: joint for joint in interface["joint_map"] if joint["role"] == "hip"}
    assert {name: joint["soft_firmware_deg"] for name, joint in hips.items()} == {
        "R1": [80, 180], "R2": [0, 100], "L1": [0, 100], "L2": [80, 180]}
    assert all(joint["soft_internal_deg"] == [-10, 90] for joint in hips.values())
