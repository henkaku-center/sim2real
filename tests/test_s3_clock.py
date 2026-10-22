"""Focused native timing tests; no hardware IO and no offline-load lifecycle suite."""
from pathlib import Path
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_native_clock_measurement(tmp_path):
    binary = tmp_path / "s3-clock-test"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    "-I", str(ROOT / "firmware/sesame-s3"),
                    str(ROOT / "tests/firmware/test_s3_clock.cpp"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_read_only_feature_preserves_calibration_identity_and_photo_binding():
    header = (ROOT / "firmware/sesame-s3/manifest_generated.h").read_text()
    # Compatibility identity before this read-only feature. Changing motion or
    # pulse semantics requires an intentional test/compatibility review.
    assert re.search(r'MANIFEST_ID\[\] = "bd7675604b98ae46"', header)
    interface = json.loads((ROOT / "reference/sesame-s3-interface.json").read_text())
    clock = interface['clock_measurement']
    assert clock['input_gpio'] == 4 and clock['pca_channel'] == 15
    assert clock['carrier_address'] == 'F17' and clock['s3_header_part'] == 's3.male_pin.F17'
    provenance = clock['pin_binding_provenance']
    assert provenance['kind'] == 'parent-observed-user-reference-photo'
    assert provenance['observed_on'] == '2026-10-22'
    assert provenance['image_sha256'] is None
    assert provenance['far_to_usb_labels'] == ['7', '6', '5', '4', '3', '2', '1', 'RX', 'TX']
    assert provenance['installed_row_usb_to_far']['F17'] == 'GPIO4'
    assert clock['pca_actual_photo_native_part'] is None
    assert clock['pca_signal_parts_scope'].startswith('reference-CAD-only:')
    assert clock['pca_signal_parts'] == ['cad.Part__Feature128.pin.2', 'cad.Part__Feature144.pin.2']
    assert clock['target_edges'] == 101 and clock['timeout_ms'] == 4000
    assert clock['watchdog_ms'] == 500
    assert interface['pulse']['profile_id'] == 'tim-pca9685-150-512-v1'
    assert {'clock measure', 'clock status', 'clock abort'} <= {
        command['syntax'] for command in interface['commands']}
