# Sesame firmware state and APS deltas

Date: 2026-08-14

Related upstream activity:

- Sesame firmware PR for USB Serial face commands: <https://github.com/dorianborian/sesame-robot/pull/76>
- pySerial PR to keep `list_ports` importable on Android/Termux: <https://github.com/pyserial/pyserial/pull/873>
- esptool Android/Termux findings added to existing issue: <https://github.com/espressif/esptool/issues/665#issuecomment-5290556615>

This note records the firmware/hardware state observed during phone-to-Sesame tests with Karasu III (Android/Termux) and the APS-local firmware changes we intend to carry. Do not treat the upstream clone as the working source of truth; upstream `dorianborian/sesame-robot` remains a reference only.

## Observed hardware / transport state

- Robot enumerates over Karasu USB OTG through Termux as `/dev/bus/usb/001/002`.
- USB descriptor observed from Android raw USB access:
  - VID:PID `303a:80c2`
  - class `ef`, subclass `02`, protocol `01`
  - CDC ACM-style interfaces:
    - interface 0: comms, interrupt IN `0x85`
    - interface 1: data, bulk OUT `0x03`, bulk IN `0x84`
- Termux can open the raw USB device after `termux-usb -r /dev/bus/usb/001/002` permission grant.
- Stock Android/Termux does not expose `/dev/ttyACM*` or `/dev/ttyUSB*`; pyserial/esptool therefore do not work out of the box.
- A small raw CDC test program on Karasu can send serial bytes to the running firmware.
- Serial command `subtrim`/`st` replies successfully, confirming app-firmware USB serial communication.

## Current upstream firmware behavior relevant to faces

Reference: `dorianborian/sesame-robot@main`, `firmware/sesame-firmware-main.ino`.

- USB Serial CLI supports motion/debug commands, e.g.:
  - `run walk`, `rn wf`
  - `run rest`, `rn rs`
  - `run stand`, `rn st`
  - `subtrim`, `st`
  - `<motor> <angle>`, `all <angle>`
- USB Serial CLI does **not** currently support face-only commands.
- Face-only commands are supported over HTTP:
  - `POST /api/command` with body `{"face":"happy"}`
- Karasu successfully connected to Sesame AP `Sesame-Controller` and the web controller changed OLED faces.
- Servo movement did not occur during web-button tests because the servo rail/hub was not externally powered. This is expected and should not be debugged as a firmware issue until servo power is attached.

## APS-local modifications / intended deltas

Known APS work and decisions to preserve locally:

1. Servo direction/polarity changes were made during assembly bring-up.
2. Those direction changes appear to have reduced usable range of motion in some joints.
3. Planned mechanical correction: unscrew legs and reattach them in the correct orientation before relying on firmware-side reversals.
4. Proposed firmware delta: add USB Serial face-only commands for phone-over-USB control, without requiring Wi-Fi:

```cpp
else if (strncmp(command_buffer, "face ", 5) == 0 || strncmp(command_buffer, "fc ", 3) == 0) {
  const char* faceName = (command_buffer[1] == 'c') ? command_buffer + 3 : command_buffer + 5;
  if (strlen(faceName) > 0) {
    currentCommand = "";
    setFace(String(faceName));
    Serial.print("Face set to ");
    Serial.println(faceName);
  } else {
    Serial.println("Usage: face <name>");
  }
}
```

Example intended commands after flashing this delta:

```text
face happy
face surprised
face sleepy
fc happy
```

## Firmware flashing from Karasu

Goal: phone sends firmware updates directly to Sesame over USB OTG.

Status: partially implemented as an experimental RFC2217 bridge in `tools/karasu-usb-bridge/`.

Blockers:

- Android grants raw USB device access through `termux-usb`, not a POSIX serial tty.
- Stock `esptool.py` expects pyserial over `/dev/ttyACM*`/`/dev/ttyUSB*` and cannot directly use the Termux USB file descriptor.
- The experimental bridge solves the serial transport by exposing Karasu's raw USB CDC device as RFC2217 TCP serial, but bootloader entry remains unresolved.
- ESP32-S2/S3 native USB CDC DTR/RTS are virtual line states. They do not guarantee hardware EN/GPIO0 boot mode entry unless the board/firmware maps them accordingly.
- USB reset/reboot re-enumerates the Android device path (`/dev/bus/usb/001/00N`), invalidating the old `termux-usb` file descriptor. Android permission may need to be granted again unless the OS offers and honors an always-allow choice.
- A fully reliable phone flasher likely requires one of:
  1. manual BOOT/GPIO0 + RESET during the bridge session,
  2. firmware-assisted reboot-to-bootloader command or 1200-bps touch support,
  3. bridge auto-reopen after re-enumeration plus persistent Android USB permission,
  4. root/kernel support exposing a real tty device, or
  5. adding OTA/web firmware update support to Sesame and using Wi-Fi instead of USB for firmware updates.

Near-term recommendation:

- Use Karasu for HTTP face/control tests now.
- Add the serial `face` command in APS-local firmware, flash once from laptop, then use Karasu USB serial for face-only commands.
- Treat phone-based flashing as the next transport project.

Preferred flashing architecture:

1. Calcifer/Artemis performs complex development work: Arduino build, dependency management, tests, artifact storage.
2. Karasu stays on normal Wi-Fi/cellular/Tailscale for internet reachability while physically connected to Sesame over USB OTG.
3. Karasu runs a small USB CDC ACM bridge that maps the Termux-granted raw USB file descriptor to a serial protocol usable by the host.
4. Calcifer runs `esptool` against Karasu over the network, ideally through pySerial's existing `rfc2217://` support so DTR/RTS/baud-rate control can be forwarded to USB CDC control requests.

This keeps the phone as the carried field device and USB bridge, without forcing all firmware builds to happen on Android.

## Latest bridge test result (2026-08-14)

With Sesame manually placed into ROM bootloader mode (hold BOOT/GPIO0, tap RESET, release BOOT), Karasu re-enumerated the device as the ROM bootloader:

```text
VID:PID 303a:0002
Chip detected by esptool: ESP32-S2 / ESP32-S2FNR2
MAC observed: 48:27:e2:59:51:3c
```

`esptool` can now sync through the Karasu RFC2217 bridge and read registers. This proves the calcifer → Tailscale → Karasu → USB OTG → Sesame bootloader path.

Remaining issue: uploading the esptool flasher stub currently fails with a ROM response checksum error during `MEM_DATA`. This likely points to a bridge robustness issue for large binary writes / escaping / chunking rather than basic connectivity. Next tests should focus on:

- using `--no-stub` write/read operations,
- smaller USB bulk OUT chunk sizes,
- stricter RFC2217/telnet escaping tests with binary payloads containing `0xff`,
- direct socket transport once the board is already in bootloader mode,
- automatic bridge restart after `/dev/bus/usb` re-enumeration.
