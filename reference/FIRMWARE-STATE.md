# Sesame firmware state and APS deltas

Date: 2026-08-14

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

Status: possible in principle, not yet implemented.

Blockers:

- Android grants raw USB device access through `termux-usb`, not a POSIX serial tty.
- Stock `esptool.py` expects pyserial over `/dev/ttyACM*`/`/dev/ttyUSB*` and cannot directly use the Termux USB file descriptor.
- A working phone flasher likely requires one of:
  1. a pyserial backend adapted to Android raw USB / `termux-usb`,
  2. a USB-serial-to-TCP bridge app plus `socat`/pty and esptool,
  3. root/kernel support exposing a real tty device, or
  4. adding OTA/web firmware update support to Sesame and using Wi-Fi instead of USB for firmware updates.

Near-term recommendation:

- Use calcifer or Artemis for flashing until the APS firmware state is captured cleanly.
- Use Karasu for HTTP face/control tests now.
- Add the serial `face` command in APS-local firmware, flash once from laptop, then use Karasu USB serial for face-only commands.
- Investigate phone-based flashing separately as a transport project, not as part of the first OLED command success test.
