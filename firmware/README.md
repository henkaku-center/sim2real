# Sesame S3 class firmware

One image in `sesame-s3/` contains calibration, the bounded controller, stock
OLED faces, nineteen manifest motions and an AP/web command console. A normal
firmware directory is appropriate because this replaces the temporary bench
image and remains installed for class. `firmware-tests/sesame-s3-bringup/`
remains an immutable record of what was actually tested in September.

Start with [student calibration](../reference/SESAME-S3-CALIBRATION.md).
For guide/tool integrations import **`reference/sesame-s3-interface.json`**:
channel map/status, commands, calibration JSON schema and power sequencing are
in that one generated handoff. Runtime `export` produces a matching device record.

## Reproducible build and flash

Requirements on macOS/Linux: Python 3, `uv`, and **arduino-cli 1.5.1** on PATH.
The [official release](https://github.com/arduino/arduino-cli/releases/tag/v1.5.1)
provides macOS x86-64/ARM64 and Linux x86-64/ARM64 archives plus checksums.
Install the matching archive and verify against `1.5.1-checksums.txt` rather
than taking an unpinned package-manager upgrade. Python dependencies needed by
the helper are installed by `uv` at the versions in `toolchain.json`.

From the repository root:

```sh
python3 tools/sesame_s3.py setup     # once: install exact core/libraries
python3 tools/sesame_s3.py build     # offline after tools/deps are cached
python3 tools/sesame_s3.py ports     # identify board; does not flash
```

**One flash command**, battery disconnected, servo V+ off, USB only:

```sh
python3 tools/sesame_s3.py flash --port /dev/ttyACM0
```

Use `/dev/cu.usbmodem…` on macOS. The script refuses a missing port or mismatched
toolchain, builds cleanly, verifies generated data and asset hashes, then uses
Arduino's complete bootloader/partition/application upload recipe. It does not
erase NVS (`EraseFlash=none`) or hard-code an app-only offset. For a board stuck
in its old firmware, hold BOOT, tap RESET, release BOOT, then identify the ROM
USB port again. Release BOOT after flashing before using the assembly button.

```sh
python3 tools/sesame_s3.py console --port /dev/ttyACM0
```

Console local commands: `:live` sends heartbeats every100ms; `:pause` deliberately
tests watchdog loss; `:quit` sends `off` and closes. It never auto-arms or
reconnects. A terminal opened by another monitor cannot also own this port.
Normal firmware command vocabulary is listed by `help` and the JSON handoff.

Pinned: ESP32 core **3.3.11** (includes its esptool/compiler dependencies),
PCA driver **3.0.3**, SSD1306 **2.5.17**, GFX **1.12.6**, BusIO **1.17.4**.
FQBN is pinned in `toolchain.json`: generic S3, USB CDC on boot, 4 MB flash,
default partitions, PSRAM disabled. No PSRAM dependency or board-specific
variant is required. I²C pins are explicitly2/3, not generic S3 defaults8/9.
Build artifacts/hashes go to ignored `firmware/.build/sesame-s3/`.

## Implementation and compatibility

- `safe_action.h`: native-testable finite/range checks, rate limit, watchdog,
  physical-sign/trim conversion, post-trim clipping and calibrated tick math.
- `controller.cpp`: PCA/OLED, checked NVS record, serial parser, finite motion
  playback, BOOT finite centre, AP diagnostics and nonblocking HTTP I/O.
- `manifest_generated.h`: generated constants/poses/motions, never hand-edited.
- `vendor/`: byte-identical pinned Sesame face assets, license and SHA-256.
- `tools/generate_s3_firmware.py`: generates firmware and guide handoff together.

```sh
uv run --frozen python tools/generate_s3_firmware.py
uv run --frozen pytest -q tests/test_s3_firmware.py tests/test_manifest.py tests/test_safeaction.py
```

This is a controller port of the upstream faces/pose vocabulary, not byte-for-byte
Sesame Studio HTTP compatibility. It supports all nineteen motions in
`manifest/motions.yaml`; `run NAME` aliases `motion NAME`, and forward/backward/
left/right alias walk/walk_backward/turn_left/turn_right. Each stock sequence
runs once and waits for bounded targets to settle before the next step. Timings
are intentionally slower than upstream's instantaneous writes. No OTA or STA
provisioning is part of this commissioning image. Normal AP mode is sufficient
for the phone controller; the device provides DNS redirection plus an explicit
`192.168.4.1` fallback, since captive portal auto-open is client-dependent.

Calibration sessions move one servo at a time, except explicitly requested raw
assembly centre. Default discovery travel85–95°, calibration15°/s and
controller60°/s are conservative caps below the general SafeAction maximum.
Stock commands and microsecond commands pass the same gate. `stop` freezes;
`off` cancels and releases. No external heartbeat for500ms disables outputs
and cancels queues; internal sequence steps do **not** feed that watchdog.
The S3 profile selects outputs-off instead of the simulator's rest failsafe
because an unverified channel map must not execute a multi-joint pose.

Arming never enables outputs; the first actual target starts from neutral.
There is no shaft feedback: the first move after release/reset cannot be
slew-limited from an unknown real position. Support/unload the robot. OE must
be connected and pulled high during reset to cover MCU resets/I²C failures;
software full-off alone cannot protect a still-powered PCA if the bus is lost.
`status` reports commanded/interpolated angles, not measured encoder positions.

The NVS record is versioned, checksummed and tied to the generated manifest
fingerprint. An invalid, incompatible or missing record falls back to
unassigned channels and narrow travel. `map` rejects duplicates; all changes
require outputs-off and clear verification as appropriate. Ordinary reflashes
with the same manifest preserve saved calibration. A changed manifest invalidates
the old record rather than silently reinterpreting it: retain `export` output
and re-enter/reverify the device's values. Calibration is device-specific;
do not copy one robot's trims/clock into every class build.

### Validation boundary

See [diagnosis and validation](../reference/SESAME-S3-DIAGNOSIS.md). Compile and
native tests do not establish RF visibility, servo travel, horn orientation,
power isolation or successful motion on hardware. Those remain NEEDS-HARDWARE.
