#!/usr/bin/env python3
"""Generate the firmware contract and nonblocking stock sequences from manifests."""
import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "firmware/sesame-s3/manifest_generated.h"
INTERFACE = ROOT / "reference/sesame-s3-interface.json"


def interface():
    robot = yaml.safe_load((ROOT / "manifest/robot.yaml").read_text())
    hw = robot["hardware_profiles"]["sesame_s3"]
    safe = yaml.safe_load((ROOT / "manifest/safeaction.yaml").read_text())
    # The published handoff is generated alongside the firmware constants.
    # This catalog documents the strict parser, not a second actuation path.
    commands = [
        ("help", "any", "List exact command grammar"),
        ("show", "any", "Export map/sign/trim/limits/verified flags and oscillator"),
        ("export", "any", "Print JSON matching calibration_schema; retain per-robot evidence"),
        ("status", "any", "Mode, owner, current/target/electrical pulse telemetry"),
        ("wifi", "any", "Actual AP configuration and API error codes"),
        ("face NAME", "any", "OLED face only"),
        ("off", "any", "Cancel queues, assert OE, full-off all PCA outputs, disarm"),
        ("stop", "any", "Cancel queues, freeze targets; heartbeat still required"),
        ("heartbeat", "active-owner", "Renew 500ms watchdog; never arms or resumes"),
        ("arm channel CH", "off", "One physical CH0..7, discovery envelope 85..95"),
        ("arm hornless CH", "off", "One physical CH0..7, bounded 0..180, horns disengaged"),
        ("arm joint NAME", "off", "One mapped logical joint, measured/soft/electrical limits"),
        ("arm assembly", "off", "Prepare raw neutral on physical CH0..7; no pulses yet"),
        ("arm run", "off", "Require eight verified joints and saved NVS record; no pulses yet"),
        ("centre", "assembly", "Raw 90 degrees /1830.5us on CH0..7, ignore trims"),
        ("angle DEG", "single-channel-or-joint", "Absolute firmware angle; physical in raw modes"),
        ("us MICROSECONDS", "single-channel-or-joint", "732..2929, converted through the same limits/rate gate"),
        ("q INTERNAL_DEG", "joint", "Internal signed joint angle; 0 is neutral"),
        ("jog DELTA_DEG", "single-channel-or-joint", "Add to current firmware angle"),
        ("sweep LOW HIGH", "single-channel-or-joint", "One low-high-neutral pass, 15deg/s; live watchdog"),
        ("map NAME CH", "off", "Assign one unique CH0..7; invalidates joint verification"),
        ("unmap NAME", "off", "Unassign joint before swapping channels"),
        ("sign NAME SIGN", "off", "Absolute physical sign +1/-1; invalidates verification"),
        ("trim NAME DEG", "off", "Physical-angle offset, -15..15; invalidates verification"),
        ("limits NAME LOW HIGH", "off", "Measured firmware envelope within manifest, including90"),
        ("verify NAME", "off", "Owner attests measured mapping/direction/limits; not auto-detection"),
        ("oscillator HZ", "off", "Measured20..30MHz; reapplies prescaler, clears ALL verification"),
        ("save", "off", "Persist one versioned/checksummed NVS calibration record"),
        ("reference", "off", "CH15=1500us, all servos disconnected; reports actual programmed ticks"),
        ("motion NAME", "run", "One finite stock sequence through SafeAction; same as run NAME"),
        ("servo NAME DEG", "run", "Bounded single-joint target"),
        ("pose D0 D1 D2 D3 D4 D5 D6 D7", "run", "Bounded targets in canonical logical order"),
        ("rest", "run", "Named rest motion; applies measured trims/signs"),
        ("wifi COUNTRY CHANNEL TX_DBM", "off-usb-only", "JP/US/GB/DE/FR;1..11;2/8.5/13/19.5; session-only"),
    ]
    joint_schema = {
        "type": "object", "additionalProperties": False,
        "required": ["name", "channel", "sign", "trim_deg", "limits_deg", "verified"],
        "properties": {
            "name": {"enum": [j["name"] for j in robot["joints"]]},
            "channel": {"type": "integer", "minimum": -1, "maximum": 7, "description": "-1=unassigned; nonnegative channels unique"},
            "sign": {"enum": [-1, 1]},
            "trim_deg": {"type": "number", "minimum": -hw["trim_limit_deg"], "maximum": hw["trim_limit_deg"]},
            "limits_deg": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 180}, "minItems": 2, "maxItems": 2},
            "verified": {"type": "boolean"},
        },
    }
    return {
        "schema_version": 1,
        "generated_by": "tools/generate_s3_firmware.py",
        "status": "NEEDS-HARDWARE; offline validation is recorded separately in the diagnosis",
        "procedure": "reference/SESAME-S3-CALIBRATION.md",
        "diagnosis": "reference/SESAME-S3-DIAGNOSIS.md",
        "firmware": "firmware/sesame-s3",
        "flash_command": "python3 tools/sesame_s3.py flash --port PORT",
        "console_command": "python3 tools/sesame_s3.py console --port PORT",
        "serial": {"baud": 115200, "line_ending": "LF", "maximum_line_bytes": 159,
                   "live_command": ":live", "pause_heartbeat_command": ":pause", "close_command": ":quit"},
        "joint_map": [{"name": j["name"], "logical_index": j["channel"], "leg": j["leg"], "role": j["role"],
                       "target_pca_channel": hw["intended_channels"][j["name"]],
                       "hardware_verified_pca_channel": None, "default_nvs_channel": -1,
                       "mapping_status": "target-only-unverified", "manifest_sign": j["sign"],
                       "soft_firmware_deg": j["limits_deg"],
                       "soft_internal_deg": sorted((v-90)*j["sign"] for v in j["limits_deg"])} for j in robot["joints"]],
        "pulse": {"range_us": robot["servo_bus"]["pulse_us"], "angle_deg": [0, 180], "neutral_deg": 90,
                  "neutral_us": 1830.5, "pwm_hz": 50, "oscillator_default_hz": hw["oscillator_hz"],
                  "oscillator_status": "nominal-unmeasured", "ticks_formula": "round(us * oscillator_hz / (1000000 * (prescale+1)))"},
        "button": {"pin": 0, "off_press_release": "raw CH0..7 neutral for30s", "active_press": "off", "held_at_boot": "must release before new press"},
        "power": {"flash": "battery disconnected; servo V+ off; USB only",
                  "button_assembly": "unplug USB, then power from battery alone",
                  "serial_motion": "instructor-verified isolated servo V+ with common ground, or verified data-only USB with no VBUS backfeed",
                  "unverified_isolation": "do not combine USB and battery; use battery-only button or Wi-Fi"},
        "safeaction": {"watchdog_ms": safe["watchdog"]["timeout_ms"], "failsafe": hw["watchdog_failsafe"],
                       "calibration_rate_deg_s": hw["calibration_rate_deg_s"], "controller_rate_deg_s": hw["controller_rate_deg_s"],
                       "start": "outputs-off, arm does not emit PWM", "first_enable": "unknown physical position; starts neutral, no feedback"},
        "ap": {"ssid": "Sesame-S3-<last-two-MAC-bytes>", "password": "sesame123", "ip": "192.168.4.1",
               "country": "JP", "channel": 1, "requested_tx_dbm": 8.5, "hardware_visibility": "unverified"},
        "commands": [{"syntax": a, "mode": b, "meaning": c} for a,b,c in commands],
        "calibration_schema": {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "SesameS3 NVS logical record v1",
            "type": "object", "additionalProperties": False,
            "required": ["version", "manifest_id", "oscillator_hz", "joints"],
            "properties": {"version": {"const": 1}, "manifest_id": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
                           "oscillator_hz": {"type": "integer", "minimum": 20000000, "maximum": 30000000},
                           "joints": {"type": "array", "items": joint_schema, "minItems": 8, "maxItems": 8}},
            "$comment": "Joint order must match joint_map; names/channels unique; limits subset of manifest and include90. NVS namespace sesame-s3, key record. Binary record adds magic and checksum; firmware validates all invariants."},
        "calibration_math": {"physical_angle": "90 + trim + physical_sign * manifest_sign * (firmware_angle - 90)",
                             "internal_angle": "manifest_sign * (firmware_angle - 90)",
                             "clamps": "intersect measured firmware limits, manifest soft limits, and post-trim physical0..180"},
    }


def render():
    paths = [ROOT / "manifest" / f for f in ("robot.yaml", "safeaction.yaml", "motions.yaml")]
    robot, safe, motions = [yaml.safe_load(p.read_text()) for p in paths]
    fingerprint = hashlib.sha256(b"".join(p.read_bytes() for p in paths)).hexdigest()[:16]
    joints = robot["joints"]
    hw = robot["hardware_profiles"]["sesame_s3"]
    assert [j["channel"] for j in joints] == list(range(8))
    assert hw["controller_rate_deg_s"] <= safe["limits"]["max_rate_deg_s"]
    assert hw["watchdog_failsafe"] == "outputs_off"
    names = [j["name"] for j in joints]
    lines = ["// Generated by tools/generate_s3_firmware.py; do not edit.",
             "#pragma once", "#include <stdint.h>", "namespace sesame {",
             f'constexpr char MANIFEST_ID[] = "{fingerprint}";']
    values = {
        "NEUTRAL": robot["conventions"]["firmware_neutral_deg"],
        "PULSE_MIN": robot["servo_bus"]["pulse_us"][0],
        "PULSE_MAX": robot["servo_bus"]["pulse_us"][1],
        "PWM_HZ": robot["servo_bus"]["pwm_hz"],
        "WATCHDOG_MS": safe["watchdog"]["timeout_ms"],
        "MAX_JUMP": safe["limits"]["max_jump_deg"],
        "CAL_RATE": hw["calibration_rate_deg_s"],
        "RUN_RATE": hw["controller_rate_deg_s"],
        "TRIM_LIMIT": hw["trim_limit_deg"],
        "INITIAL_LOW": hw["initial_limits_deg"][0],
        "INITIAL_HIGH": hw["initial_limits_deg"][1],
        "OSC_DEFAULT": hw["oscillator_hz"],
        **{key.upper(): hw[key] for key in ("sda", "scl", "oe", "pca_address", "oled_address")},
    }
    for name, value in values.items():
        lines.append(f"constexpr uint32_t {name} = {value};")
    lines.append('constexpr const char* NAMES[] = {' + ', '.join(f'"{n}"' for n in names) + '};')
    for name, values in {
        "SIGNS": [j["sign"] for j in joints],
        "SOFT_LOW": [j["limits_deg"][0] for j in joints],
        "SOFT_HIGH": [j["limits_deg"][1] for j in joints],
        "TRIMS": [robot["calibration"]["subtrim_deg"][n] for n in names],
    }.items():
        lines.append(f"constexpr int {name}[] = {{" + ", ".join(map(str, values)) + "};")
    lines += ["struct MotionStep { int16_t degrees[8]; uint16_t waitMs; };",
              "struct Motion { const char* name; const MotionStep* steps; uint16_t count; };"]

    def expand(steps):
        for step in steps:
            if "repeat" in step:
                for _ in range(step["repeat"]["count"]):
                    yield from expand(step["repeat"]["steps"])
            else:
                targets = robot["poses"][step["pose"]] if "pose" in step else step.get("set", {})
                yield [targets.get(n, -1) for n in names], step.get("wait", 0)

    for name, steps in motions["motions"].items():
        lines.append(f"constexpr MotionStep STEPS_{name}[] = {{")
        for angles, wait in expand(steps):
            lines.append("  {{" + ", ".join(map(str, angles)) + f"}}, {wait}" + "},")
        lines.append("};")
    lines.append("constexpr Motion MOTIONS[] = {")
    for name in motions["motions"]:
        lines.append(f'  {{"{name}", STEPS_{name}, sizeof(STEPS_{name}) / sizeof(MotionStep)}},')
    lines += ["};", "} // namespace sesame", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = {OUT: render(), INTERFACE: json.dumps(interface(), indent=2) + "\n"}
    if args.check:
        for path, content in outputs.items():
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Stale generated {path.name}; run tools/generate_s3_firmware.py")
    else:
        for path, content in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
