#!/usr/bin/env python3
"""Generate the firmware contract and nonblocking stock sequences from manifests."""
import argparse
import hashlib
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "firmware/sesame-s3/manifest_generated.h"
INTERFACE = ROOT / "reference/sesame-s3-interface.json"


def pulse_profile(hw):
    profile = hw['pulse_profile']
    assert profile['interpolation'] == 'floor-reference-ticks'
    low, high = profile['reference_ticks']
    assert 0 < low < high < 4096
    tick = 1e6 * (profile['reference_prescale'] + 1) / profile['reference_oscillator_hz']
    return profile, low, high, tick


def interface():
    robot = yaml.safe_load((ROOT / "manifest/robot.yaml").read_text())
    hw = robot["hardware_profiles"]["sesame_s3"]
    profile, tick_low, tick_high, tick_us = pulse_profile(hw)
    pulse_low, pulse_high = round(tick_low * tick_us, 6), round(tick_high * tick_us, 6)
    neutral_us = round((tick_low + (tick_high - tick_low) // 2) * tick_us, 6)
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
        ("bench", "any", "Show paired physical-channel commanded angles; no movement"),
        ("off", "any", "Cancel queues, assert OE, full-off all PCA outputs, disarm"),
        ("stop", "any", "Cancel queues, freeze targets; heartbeat still required"),
        ("heartbeat", "active-owner", "Renew 500ms watchdog; never arms or resumes"),
        ("arm channel CH", "off", "One physical CH0..7, discovery envelope 85..95"),
        ("arm hornless CH", "off", "One physical CH0..7, bounded 0..180, horns disengaged"),
        ("arm joint NAME", "off", "One mapped logical joint, measured/soft/electrical limits"),
        ("arm assembly", "off", "Prepare raw neutral on physical CH0..7; no pulses yet"),
        ("arm run", "off", "Require eight verified joints and saved NVS record; no pulses yet"),
        ("centre", "assembly", f"Raw 90 degrees /{neutral_us}us on CH0..7, ignore trims"),
        ("angle DEG", "single-channel-or-joint", "Absolute firmware angle; physical in raw modes"),
        ("us MICROSECONDS", "single-channel-or-joint", f"{pulse_low}..{pulse_high}, quantized through the same limits/rate gate"),
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
        ("clock measure", "off-usb-only", f"Bounded CH15 rising-edge timing on GPIO{hw['clock_measure_gpio']}; all servos unplugged; heartbeat required; no calibration write"),
        ("clock status", "any", "Read generation, quality, edges, observed Hz and oscillator estimate; MCU-relative, not a lab standard"),
        ("clock abort", "any", "Abort clock capture and turn all outputs off"),
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
        "pulse": {"profile_id": profile['id'], "reference_ticks": [tick_low, tick_high],
                   "reference_tick_us": tick_us, "interpolation": profile['interpolation'],
                   "range_us": [pulse_low, pulse_high], "angle_deg": [0, 180], "neutral_deg": 90,
                   "neutral_us": neutral_us, "pwm_hz": 50, "oscillator_default_hz": hw["oscillator_hz"],
                  "oscillator_status": "nominal-unmeasured", "ticks_formula": "round(us * oscillator_hz / (1000000 * (prescale+1)))"},
        "button": {"pin": 0, "off_press_release": "raw CH0..7 neutral for30s", "active_press": "off", "held_at_boot": "must release before new press"},
        "clock_measurement": {
            "input_gpio": hw["clock_measure_gpio"], "pca_channel": 15,
            "pca_signal_parts": ["cad.Part__Feature128.pin.2", "cad.Part__Feature144.pin.2"],
            "carrier_address": None, "s3_header_part": None,
            "pin_binding_status": "NEEDS-HARDWARE: installed SuperMini pinout not established by Zero reference CAD; do not infer F17=GPIO4",
            "power": "USB only; battery physically unplugged; all servo plugs removed; CH15 SIGNAL (not V+) to labelled GPIO4 input; common carrier GND; logic VCC 3.3V only",
            "target_edges": 101, "timeout_ms": 4000, "watchdog_ms": safe["watchdog"]["timeout_ms"],
            "clock_reference": "S3 esp_timer microseconds; average 100 periods; not traceable lab-standard frequency",
            "quality": "periods 10000..40000us, peak-to-peak jitter <=2% of mean, estimated oscillator 20..30MHz; algorithmic rejection limits, not measured accuracy",
            "oscillator_formula": "observed_hz * 4096 * (prescale + 1)",
            "apply": "Explicit oscillator HZ then save while OFF; measurement never changes calibration or verification",
        },
        "power": {"flash": "battery physically disconnected; USB only; servo leads may remain connected; outputs OFF at boot",
                  "button_assembly": "unplug USB, then power from battery alone",
                   "serial_motion": "USB only, battery disconnected; one small single-channel trial at a time; off between channels; stop on reset/sag/abnormal behaviour; USB capacity unverified",
                   "unverified_isolation": "never combine USB and battery; unplug USB before battery-only load testing; no external supply or Wi-Fi requirement",
                   "battery_load_test": "current BOOT routine is a static centre hold; finite repeated-motion load routine pending implementation/validation"},
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
    # Preserve the pre-existing NVS calibration identity: adding/changing this
    # read-only input does not change pulse conversion, joint mapping or limits.
    # All other original manifest bytes still participate in the legacy hash.
    robot_bytes, removed = re.subn(rb'^    clock_measure_gpio: [0-9]+[^\n]*\n', b'', paths[0].read_bytes(), flags=re.M)
    assert removed == 1, 'Expected one read-only timing-input field'
    fingerprint = hashlib.sha256(robot_bytes + b"".join(p.read_bytes() for p in paths[1:])).hexdigest()[:16]
    joints = robot["joints"]
    hw = robot["hardware_profiles"]["sesame_s3"]
    profile, tick_low, tick_high, tick_us = pulse_profile(hw)
    assert [j["channel"] for j in joints] == list(range(8))
    assert hw["controller_rate_deg_s"] <= safe["limits"]["max_rate_deg_s"]
    assert hw["watchdog_failsafe"] == "outputs_off"
    names = [j["name"] for j in joints]
    lines = ["// Generated by tools/generate_s3_firmware.py; do not edit.",
             "#pragma once", "#include <stdint.h>", "namespace sesame {",
             f'constexpr char MANIFEST_ID[] = "{fingerprint}";',
             f'constexpr char PULSE_PROFILE_ID[] = "{profile["id"]}";']
    values = {
        "NEUTRAL": robot["conventions"]["firmware_neutral_deg"],
        "PULSE_MIN": round(tick_low * tick_us, 6),
        "PULSE_MAX": round(tick_high * tick_us, 6),
        "REFERENCE_TICK_US": tick_us,
        "REFERENCE_TICK_MIN": tick_low,
        "REFERENCE_TICK_MAX": tick_high,
        "PWM_HZ": robot["servo_bus"]["pwm_hz"],
        "WATCHDOG_MS": safe["watchdog"]["timeout_ms"],
        "MAX_JUMP": safe["limits"]["max_jump_deg"],
        "CAL_RATE": hw["calibration_rate_deg_s"],
        "RUN_RATE": hw["controller_rate_deg_s"],
        "TRIM_LIMIT": hw["trim_limit_deg"],
        "INITIAL_LOW": hw["initial_limits_deg"][0],
        "INITIAL_HIGH": hw["initial_limits_deg"][1],
        "OSC_DEFAULT": hw["oscillator_hz"],
        "CLOCK_MEASURE_GPIO": hw["clock_measure_gpio"],
        **{key.upper(): hw[key] for key in ("sda", "scl", "oe", "pca_address", "oled_address")},
    }
    for name, value in values.items():
        kind = 'float' if isinstance(value, float) else 'uint32_t'
        lines.append(f"constexpr {kind} {name} = {value};")
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
