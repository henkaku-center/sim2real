"""Native numerical safety tests; no ESP32, servo or RF result is implied."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_generated_contract_is_current():
    subprocess.run(["python", "tools/generate_s3_firmware.py", "--check"], cwd=ROOT, check=True)


def test_native_safeaction(tmp_path):
    binary = tmp_path / "s3-test"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    "-I", str(ROOT / "firmware/sesame-s3"),
                    str(ROOT / "tests/firmware/test_s3_native.cpp"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
