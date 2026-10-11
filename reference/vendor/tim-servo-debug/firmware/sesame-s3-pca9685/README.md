# sesame-s3-pca9685

Our fork of upstream's `sesame-firmware-main.ino`, retargeted to the
**ESP32-S3 Super Mini + PCA9685**.

Wiring is specified in [`docs/wiring/netlist.md`](../../docs/wiring/netlist.md),
which is the source of truth. This sketch implements that netlist and nothing
else — if the two disagree, the netlist wins.

## What changed vs upstream

Branch point: [`dorianborian/sesame-robot`](https://github.com/dorianborian/sesame-robot)
@ `86d2bf8`. The diff is deliberately tiny — the substantive edits below are
exactly the blast radius predicted in
[`docs/upstream/divergence.md`](../../docs/upstream/divergence.md):

| Upstream | Change |
|---|---|
| `#include <ESP32Servo.h>` | → `Adafruit_PWMServoDriver.h` |
| `I2C_SDA 33` / `I2C_SCL 35` | → GPIO2 / GPIO3 |
| `Servo servos[8]` + `servoPins[8]` + 8×`attach()` | Removed. One PCA9685 object |
| `ESP32PWM::allocateTimer()` ×4 | Removed. The MCU no longer generates servo PWM |
| `setServoAngle()` | Rewritten onto `pwm.setPWM(channel, 0, pulse)` |
| — | **Added:** shared `firmware/common/sesame_servo_map.h`; `setServoAngle()` translates upstream logical indices through `LOGICAL_TO_PCA_CHANNEL` before writing PCA9685 outputs |
| — | **Added:** PCA9685 `OE` on GPIO18, held HIGH through boot and released only after a successful `0x40` probe, 50 Hz setup, and all 16 outputs being set full-off |

Everything else — the face engine, `movement-sequences.h`, the JSON API, the
captive portal, Sesame Studio compatibility — is byte-identical to upstream.
Portability is preserved by applying an explicit channel translation at the
hardware boundary, not by assuming physical channel `n` equals logical index `n`.

## Logical-to-physical channel translation

Physical PCA9685 channel order does not match upstream logical index order.
The firmware translates at the hardware boundary using
[`LOGICAL_TO_PCA_CHANNEL`](../common/sesame_servo_map.h), defined in
`firmware/common/sesame_servo_map.h`:

```c++
constexpr uint8_t LOGICAL_TO_PCA_CHANNEL[SERVO_COUNT] = {4, 5, 0, 1, 7, 6, 2, 3};
```

| Logical index | Upstream name | PCA9685 ch | Physical joint |
|---|---|---|---|
| 0 | R1 | ch4 | URF — Upper Right Front |
| 1 | R2 | ch5 | URB — Upper Right Back |
| 2 | L1 | ch0 | ULF — Upper Left Front |
| 3 | L2 | ch1 | ULB — Upper Left Back |
| 4 | R4 | ch7 | LRB — Lower Right Back |
| 5 | R3 | ch6 | LRF — Lower Right Front |
| 6 | L3 | ch2 | LLF — Lower Left Front |
| 7 | L4 | ch3 | LLB — Lower Left Back |

Subtrim values are indexed by **logical** index (upstream convention), not by
physical PCA9685 channel. Any per-servo trim array must follow the same
logical ordering.

## Pulse geometry — read before changing `SERVOMAX`

Upstream calls `attach(servoPins[i], 732, 2929)`. Those are **microseconds**,
and ESP32Servo **silently clamps** the top end:

```c
// ESP32Servo.h
#define MIN_PULSE_WIDTH   500
#define MAX_PULSE_WIDTH  2500
// ESP32Servo.cpp — attach()
if (max > MAX_PULSE_WIDTH) max = MAX_PULSE_WIDTH;
```

So upstream's real sweep is **732 – 2500 µs**. The `2929` never reached a servo.

The PCA9685 is 12-bit — 4096 steps per period (NXP PCA9685 datasheet).
`setPWMFreq(50)` programs prescale 121 → 50.03 Hz → 19988 µs period →
**4.88 µs per count**, giving `SERVOMIN 150` (732 µs) and `SERVOMAX 512`
(2500 µs).

Measured fidelity against upstream across all 181 integer angles: **worst
deviation 6.1 µs = 0.62° of travel**, which is under a third of one step of
upstream's own 10-bit LEDC timer (~19.5 µs). The port is finer than the
original.

> **`SERVOMAX 600` is a trap.** 600 counts = 2928 µs — the value upstream
> *asked* for and never got, and the value the initial 3-servo bench sketch
> used. It sweeps **17.1% further** at the top end than any existing animation
> was authored for. Raise it only after a loaded, one-leg-at-a-time bench test.

## Dependencies

Verified against these exact versions:

| Requirement | Version used |
|---|---|
| ESP32 Arduino core | 3.3.11 |
| Adafruit PWM Servo Driver Library | 3.0.3 |
| Adafruit SSD1306 + Adafruit GFX + Adafruit BusIO | installed |

`ESP32Servo` is **no longer needed** and should not be installed for this
sketch.

### Upstream headers (not vendored)

Three unmodified upstream headers must sit **in this folder, next to the
`.ino`** — an Arduino sketch folder is the compilation unit, so the compiler
looks nowhere else.

They are not committed — `firmware/` holds our modified files only, and
re-committing 297 KB of unchanged upstream bitmaps would just create a silent
fork. All three are listed in `.gitignore`, so a plain `git add firmware/` will
not pick them up by accident. Fetch them with:

```sh
cd firmware/sesame-s3-pca9685
U=https://raw.githubusercontent.com/dorianborian/sesame-robot/86d2bf8099754fd548c7cf98ee11fc9e9cdb5092/firmware
curl -sfLO $U/face-bitmaps.h
curl -sfLO $U/movement-sequences.h
curl -sfLO $U/captive-portal.h
```

The unmodified upstream sketch is excluded on the same grounds. Fetch it into
`firmware/` when you want a baseline to diff this port against:

```sh
curl -sfL $U/sesame-firmware-main.ino \
  -o "firmware/original sesame-firmware-main.ino"
```

The delta it would show is described in
[`docs/upstream/divergence.md`](../../docs/upstream/divergence.md).

## Build

For a complete clean-machine and replacement-board procedure, follow
[`docs/firmware-installation.md`](../../docs/firmware-installation.md). The
commands below are the concise reference for an already prepared workstation.

```sh
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc \
  -u -p /dev/cu.usbmodem* firmware/sesame-s3-pca9685
```

**`CDCOnBoot=cdc` is not optional.** The ESP32-S3 Super Mini has native USB and
no UART bridge. The core defaults this to *Disabled*, which sends `Serial`
output to UART0 on GPIO43/44 instead of the USB port — so the serial monitor
stays completely blank and every diagnostic in this sketch is invisible. In the
Arduino IDE the same setting is **Tools → USB CDC On Boot → Enabled**.

With no local OTA configuration the sketch does not even include ArduinoOTA,
so the OTA-disabled image carries none of its flash or RAM cost; the OTA-only
constants, globals, and callbacks are compiled out with it.

Last verified `--clean` results: **1,106,877 bytes (84%)** with OTA disabled
(no local config) and **1,128,161 bytes (86%)** with OTA configured. Both use
the default 1,310,720-byte app slot. That is tight on the default partition
scheme — if you add code and it overflows, switch to a partition scheme with a
larger app slot rather than deleting faces.

> **Always verify with `--clean`.** `arduino-cli` caches aggressively and will
> happily report a successful size for a *previous* build while the current
> source does not compile at all. A stale cache already produced one false
> "verified" result on this sketch.

## Wi-Fi firmware updates

A clean checkout has **no Wi-Fi update support at all**: with no local
configuration present the sketch is compiled without ArduinoOTA, uses hostname
`sesame-robot`, and creates the default `Sesame-Controller` AP. Before the first
Wi-Fi update, each new ESP32 must therefore receive one USB flash with its
private robot configuration present. From the repository root, run:

```sh
./scripts/configure-ota.sh
```

This prompts for the robot's device-wide hostname, AP SSID/password, and OTA
password. It does not change saved station-mode Wi-Fi credentials. The
generated `firmware/sesame-s3-pca9685/ota-local-config.h` is gitignored,
written mode `0600`, and contains the plaintext AP password plus an
authentication-equivalent OTA password verifier. Keep it private and maintain a
secure local backup if USB recovery after credential loss would be difficult.

What the script accepts, before you run it:

- **Hostname** — 1–32 lowercase letters, digits, or internal hyphens; no
  leading or trailing hyphen.
- **Robot AP SSID** — 1–32 bytes of printable ASCII.
- **Robot AP password** — 8–63 bytes of printable ASCII, entered twice without
  echo.
- **OTA password** — at least 8 bytes, entered twice without echo (8 bytes is
  8 characters of ASCII; non-ASCII input is rejected for AP fields).
- Any rejected value leaves the existing local configuration untouched.
- **`ota-upload.sh` requires that header.** It refuses to run without it,
  because the local configuration supplies both the default target hostname and
  the verifier the robot authenticates against.

If the header predates per-robot AP configuration and lacks
`SESAME_AP_SSID`/`SESAME_AP_PASSWORD`, rerun `configure-ota.sh` before flashing.
The sketch deliberately stops compilation with `#error` until the incomplete
header is regenerated, rather than silently using the public AP defaults.

With the robot connected over USB, install that configured firmware once:

```sh
arduino-cli compile --clean \
  --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc \
  -u -p /dev/cu.usbmodem* firmware/sesame-s3-pca9685
```

The current robot received this one-time configured USB installation on
2026-09-16. A clean checkout still requires the same step for each new robot
before its first Wi-Fi update.

For every later Wi-Fi update:

1. Raise or securely support the robot; OTA deliberately makes all servos limp.
2. Power the robot normally and stop any movement.
3. Connect the computer to the configured robot AP (default:
   `Sesame-Controller`) or to the same LAN as the robot.
4. Confirm `http://<current-hostname>.local` opens in a browser.
5. From the repository root, run `./scripts/ota-upload.sh`.
6. Enter the current hostname/IP and OTA password when prompted. When given a
   hostname, the script resolves it to IPv4 before invoking Arduino CLI because
   Arduino CLI keys the discovered network port by its numeric address on
   macOS. A literal IPv4 address is used unchanged. If automatic resolution
   fails, rerun the script and enter the network-port IP shown by
   `arduino-cli board list`.
7. Observe the OLED firmware-update message and do not power off the robot.
8. Wait for image validation and reboot, then reconnect at the configured
   hostname — keeping the robot supported until it is back (see the note
   below).
9. If the update fails **after it has started** (OLED: `Update failed` /
   `Servos disabled` / `Reboot robot`), reboot the robot manually: only a
   started update disables the servo outputs, and they stay disabled — with
   that warning latched on the OLED — until reboot. A failure *before* the
   transfer starts, such as a rejected password, disables nothing and leaves
   the robot running and commandable.
10. Use USB recovery if the old image cannot boot or join Wi-Fi.

The uploader does not automatically retry an interrupted transfer. Restore a
stable connection and run it again deliberately rather than risking two
competing update attempts.

The first live OTA acceptance completed on 2026-09-16: the transfer reached
100%, the ESP32 rebooted, and the robot AP/controller returned. That accepted
run used the literal network-port IP `192.168.4.1`; it proves the upload and
reboot path, not automatic hostname resolution. Hostname-to-IPv4 resolution is
covered by the host regression test and still needs confirmation on the next
live robot upload. ESP32 core 3.3.11 printed `Unexpected response: 864` after
completion but exited successfully; the observed reboot and restored controller
confirmed that image.

> **Keep the robot supported through the OTA reboot.** PCA9685 register
> retention and `OE` state across a warm restart are not guaranteed to be
> identical to a cold boot, so a brief servo transient between reset and the
> new firmware driving `OE` HIGH cannot be ruled out from the source alone.
> This has not been observed on hardware; it is an explicit item to watch
> during hardware acceptance, not a claim that it happens.

Changing the configured hostname takes effect after reboot and changes HTTP
mDNS, the station DHCP hostname, the status API, OLED/serial announcements, and
OTA discovery. The upload script clean-builds the image and refuses any binary
larger than the default OTA slot limit of **1,310,720 bytes**.

The password is read without terminal echo and is not written to the build, but
`ota-upload.sh` must pass it to `arduino-cli` as a process argument. It can
therefore be visible briefly to other sufficiently privileged local processes
during the upload. Run updates only on a trusted computer.

## Before first power-up

Full checklist is in [`docs/wiring/README.md`](../../docs/wiring/README.md).
The three that destroy hardware:

1. **PCA9685 `VCC` is 3V3, `V+` is the 5 V rail.** They are different supplies
   on the same board. 5 V into `VCC` destroys it.
2. **Set the LM2596S to 5.2 V no-load *before* connecting anything.**
3. **Servo current must not flow through the ESP32** — servo power comes off
   the PCA9685's own 3-pin headers.

On boot the sketch drives `OE` HIGH (outputs disabled) before touching I2C.
After a successful `0x40` probe, the PWM frequency is programmed and all
sixteen PCA9685 channels are set to full-off before `OE` is released LOW, so no
stale PWM state survives a warm restart. Servos stay limp until the first
command, same as upstream.

If the PCA9685 does not answer at its I2C address, the serial log says so at
115200 baud rather than failing silently (fail-closed probe).

One more that destroys nothing but costs a day: **seat the board so its
antenna end overhangs the breadboard**, clear of the metal strips — see
[`docs/wiring/antenna.md`](../../docs/wiring/antenna.md).

## Known trap: a missing OLED kills the Wi-Fi AP

Inherited from upstream, unchanged:

```c
if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
  Serial.println(F("SSD1306 allocation failed."));
  while (1);            // halts here
}
```

This runs **before** `WiFi.softAP()`. If the SSD1306 does not answer at `0x3C`,
the board stops dead and the configured robot AP never appears — which looks
like a Wi-Fi fault but is an I2C fault.

First checkpoint on boot: the OLED should display `Setting up WiFi...`. If it
does, I2C is fine and the halt is not your problem.

To find out what is actually on the bus, run
[`firmware/test/i2c-scan`](../test/i2c-scan/i2c-scan.ino). Some SSD1306 modules
are strapped to `0x3D` rather than `0x3C`.

## Known trap: a breadboard kills the Wi-Fi radio

The Super Mini's antenna is printed on one end of its own PCB. Seated
centrally in a breadboard, that antenna sits over the metal contact strips,
which detune and absorb it. The board still *hears* nearby networks, but
nothing can reach it: the configured robot AP reports a successful start and
stays invisible to every client.

**Seat the board with its antenna end overhanging the breadboard.** The full
account, including the measurements and the PCB keep-out rules, is in
[`docs/wiring/antenna.md`](../../docs/wiring/antenna.md).

This is not a firmware fault and no code change fixes it. If the network does
not appear, check the board's physical placement before reading a single line
of this sketch.

## Not implemented

**UWB runtime and pin assignments are absent from this sketch.** It contains
only a comment recording that UWB is deliberately absent. The SPI-based raw
UWB radio header remains reserved and unpopulated in the netlist (rows 27–34),
but this firmware does not configure it. Stage 2 owns future UWB integration;
the selected route is Makerfabs ESP32 UWB DW3000 over UART, not SPI.

`RSTn` (GPIO21) is **open-drain**: pull low to reset, release to high-Z, never
drive high. See [`docs/wiring/expansion.md`](../../docs/wiring/expansion.md)
before fitting a module.

## Staged acceptance sequence

After a complete assembly, verify movement in this order:

1. **Rest** — all eight logical servos are commanded to 90°; inspect every
   joint before continuing.
2. **Stand** — expect logical angles R1=135°, R2=45°, L1=45°, L2=135°,
   R4=0°, R3=180°, L3=0°, and L4=180°; verify the stance without binding.
3. **Wave** — one front leg cycles; verify range of motion.
4. **Walk (raised)** — full gait cycle with robot lifted clear of the floor;
   verify all eight servos move in the correct sequence.
5. **Stop** — return to Stand; power down.

Do not run Walk on a surface until all servos pass the raised-walk test.
Complete production animation and loaded floor operation remain Stage 1
pending items.
