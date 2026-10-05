# Sesame S3 — hardware state and recovery

## Offline firmware update — 2026-10-06

The owner reports the robot is now fully assembled, but neutral alignment and
travel are unsatisfactory; firmware has not changed since September22.
**Installed hardware state below is unchanged:** this session performed no flash
or physical test. A replacement single-image calibration/controller is now in
`firmware/sesame-s3/`. Start with [calibration](SESAME-S3-CALIBRATION.md),
[diagnosis](SESAME-S3-DIAGNOSIS.md), and the generated
[machine-readable APS handoff](sesame-s3-interface.json).

Key qualification: old150..512 ticks do omit~19.5% of the manifest's intended
pulse span, but ESP32Servo3.0.9 also caps upstream's requested2929µs at2500µs.
This is not proof of20% missing mechanical range relative to upstream hardware.
The replacement explicitly uses732..2929µs with a measured-clock setting,
horn-off centring and per-device travel limits. Physical map, horn offset,
oscillator frequency, Wi-Fi visibility and successful motions remain
**NEEDS-HARDWARE**. Target map is not preinstalled as measured calibration.

---

**Updated 2026-09-22**, following the 2026-09-21–22 session.
Instructor decision: this **S3 SuperMini + PCA9685 perfboard build is the APS-II course default**.
Course-facing record: `../aps/docs/planning/aps-ii/BUILD-STATE.md` (from this repo root).

Component identities, 2026-09-23 instructor confirmations, CAD-source research and
remaining assembly measurements: [Electronics CAD sources](ELECTRONICS-CAD-SOURCES.md).

## Start here next session

**Installed firmware is `servo-load-test`, not the full Sesame controller.** It boots with all
outputs off. A BOOT press/release commands all physical hub channels 0–7 to 90°, then 95°/90° three
times at one-second intervals, ending full-off at about seven seconds. A press during the test aborts.
The instructor confirmed completion on battery power. No current/rail/temperature measurements were
captured. This is a small-range simultaneous-motion test, not maximum load or gait acceptance.

The individual test moved servos, but **the physical joint order was wrong**. Resolve actual
channel/joint identities before calibrated poses, gaits, or connecting a policy. Preserve the existing
simulation manifest as its S2-era baseline until an explicit, hardware-verified S3 profile is ready;
do not reinterpret its `channel` fields as the new physical PCA9685 channels.

Detailed assembly materials and the circuit-board design are expected from the instructor on
**2026-09-23**. Exact as-built OE wiring and source-selection topology still need confirmation.

## Hardware identity and wiring

- ESP32-S3 QFN56 rev v0.2, MAC `d4:05:92:47:c8:b0`, 4 MB flash, 2 MB embedded PSRAM reported.
- USB VID:PID `303a:1001` (USB-Serial/JTAG); both ROM and diagnostic app used this identity.
  Descriptors alone do not prove which firmware mode is running.
- GPIO2 SDA / GPIO3 SCL; final repeated scans acknowledge OLED `0x3C`, hub `0x40`, and `0x70`.
- OLED rendering and frame updates were visibly confirmed; full firmware face/SSID also confirmed.
- Shared 3V3 logic VCC and GND; separate servo V+. GPIO18/OE is a firmware expectation, not
  a verified physical connection in this session. Diagnostics also write PCA9685 full-off registers.
- Battery labelled 7.4 V/1000 mAh; LM2596-style converter, 5 V output confirmed by instructor.
  No instrument reading was independently captured. Upstream target docs specify 5.2 V no-load;
  this session's setting was 5.0 V. Do not silently conflate them.
- Battery boot and human-triggered motion tests ran with USB disconnected. Shared USB/battery power
  isolation was not established; follow the final wiring design before changing that arrangement.

## Soldering fault evidence

Hub disconnected, OLED all-direct → pass. OLED VCC/GND via PCB → pass. Add PCB SDA → pass.
Add PCB SCL → fail. Restore direct SCL → pass. The reversible comparison isolated the PCB SCL
path/moved connection. Adding the hub then gave OLED-only responses. Further resoldering restored
both devices; five final scans consistently showed `0x3C`, `0x40`, `0x70` and the instructor reported
the hub power LED became bright and steady. Exact defective joint not independently established.

The earlier LED pulsation timing was uncertain (initially about 3 s, later irregular 5–8 s).
Do not claim proven phantom powering, a short, or synchronization with scans. The scanner runs
continuously; opening a serial capture only reads output. Drain buffered output before comparing
physical configurations. Selected captures: `reference/evidence/2026-09-22-sesame-s3/`.

## Firmware provenance and versions

Full firmware: `tim003/CIT_FC_Robotics@98d030a2d1e2e2e1f195669a9f87fcf9c5f1d465`,
`firmware/sesame-s3-pca9685`. Unmodified pinned headers (`face-bitmaps.h`, `movement-sequences.h`,
`captive-portal.h`) fetched from `dorianborian/sesame-robot@86d2bf8099754fd548c7cf98ee11fc9e9cdb5092`.

Core 3.3.11; esptool 5.3.1; Adafruit PWM 3.0.3, SSD1306 2.5.17, GFX 1.12.6, BusIO 1.17.4.
FQBN `esp32:esp32:esp32s3:CDCOnBoot=cdc`; default 4 MB layout, application at `0x10000`.
Full firmware clean build: 1,106,845 bytes / 84%; resulting app binary 1,106,992 bytes.
All completed uploads reported hash verification. Full firmware subtrim query returned eight zeros.

Full firmware was built without local OTA configuration. The face and scrolling Wi-Fi information
worked, but the advertised `Sesame-Controller` AP was absent in instructor/Artemis scans, including
on battery. HTTP controller and OTA were not tested. Antenna clearance is a hypothesis, not a diagnosis.

## Direct Artemis workflow — working path

Artemis is Linux, accessible through `ssh artemis`. In this session:

```text
/dev/ttyACM0
/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_D4:05:92:47:C8:B0-if00
~/sesame-bringup/2026-09-22/
```

Sources/builds there: `sesame-s3-pca9685/`, `common/`, `full-build/`, `oled-check.ino`,
`servo-button-test/`, `servo-button-build/`, `servo-load-test/`, `servo-load-build/`.
Full boot log: `full-boot.log`. The original I²C sketch/build was prepared on the Mac.

Build command (substitute the chosen sketch/build directory):

```sh
TMPDIR=/tmp arduino-cli compile --clean \
  --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc \
  --build-path "$HOME/sesame-bringup/2026-09-22/full-build" \
  "$HOME/sesame-bringup/2026-09-22/sesame-s3-pca9685"
```

With battery disconnected, direct USB flashing of the app at `0x10000` worked with esptool's default
reset and `--after hard-reset`. This app-only offset assumes the known installed partition/bootloader
layout; a blank/replacement board needs its complete generated `flash_args` images.

For serial capture, instantiate pyserial with `port=None`, set `dtr=False`, `rts=False`, then set
the port, open it, and set `dtr=True`. Captures showed `USB_UART_CHIP_RESET`; opening serial may reboot
this setup. Do not treat monitor attachment as passive during movement.

Mac compilation needed explicit PATH (`/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin`)
and writable TMPDIR/TMP/TEMP: initial failures were ctags temporary-file creation and missing python3
in the tool environment, not firmware errors. Both Mac and Artemis compiled diagnostics.

## Karasu findings — preserve, but direct USB was simpler

SSH: `u0_a424`, port 8022; this Mac's existing `~/.ssh/github` key was accepted. Local SSH aliases
`karasu-iii` and `karasu` were configured. No private key material is stored in this repository.

- Termux USB device path changes/reuses after reconnect/reset; always list afresh and reacquire access.
- Permission-request timeouts sometimes preceded a later direct `termux-usb DEVICE` result of
  `Permission granted.` Check that before repeatedly requesting permission.
- Killing the waiting API client on a short timeout can leave Android reporting `ResultReturner`
  `LocalSocket Connection refused`; this is not itself evidence of robot failure.
- Cold boot holding BOOT while connecting USB stabilized a repeatedly re-enumerating board.
- S3 serial endpoints: OUT `0x01`, IN `0x81`, interfaces 0/1; interrupt `0x82`.
  Interface 2 is separate. The old S2 bridge's `0x03`/`0x84` endpoints were wrong here.
- The retained S3 bridge uses 64-byte bulk writes **and reads**, with a 20 ms read timeout.
  A 4 KB read then succeeded, and a full 4 MB backup completed in 170 seconds.
- A terminated bridge could remain blocked in `accept()` and hold port 7777. Stop only the identified
  stale process and verify release before relaunching. Never attach a new device through a stale FD.
- Karasu flashed the I²C diagnostic successfully, but later attempts at OLED upload timed out on USB
  writes despite matching descriptors. Switching to Artemis resolved upload/capture immediately;
  the later Karasu failure's root cause remains unresolved.

## Backup and source preservation

Original pre-diagnostic full flash, on the Mac:

```text
~/Documents/Sesame-backups/2026-09-22-d4059247c8b0/original-flash.bin
size: 4194304
sha256: 0dc8e79f4bbd9837d8f17e9e6050eed696530921d1fd215ab24a59458215decc
```

The backup is not committed or published. Diagnostic snapshots and bridge source:
`firmware-tests/sesame-s3-bringup/`. These record the exact bounded, human-triggered bench tests;
they are not a general actuation interface or a validated SafeAction integration.

The same Mac backup directory now contains `session-images/` with the full controller and load-test
application binaries plus `full-boot.log`, copied from Artemis. SHA-256:

```text
servo-load-test.ino.bin
8f7a8c8d18316f4fb71fd5fa9bb96c5fb6ba46bad1341e79ba153df9e5f5314c
sesame-s3-pca9685.ino.bin
8851562708a257eebe1381ce31f3c167e6a27cb1adad1d681765c147b0ac808b
```

Archived individual/load diagnostic source hashes were compared with the built sources on Artemis
and matched. Binaries and raw flash backups are kept outside Git.

## Intended transfer, not a verified new physical map

The previous S2 robot used a PCA9685, with CH0–7 = R1,R2,L1,L2,R4,R3,L3,L4.
New firmware maps those logical indices to PCA channels `{4,5,0,1,7,6,2,3}`.
The instructor reported wrong physical order during the individual test; actual channel identities,
directions and calibration must be measured before updating the canonical manifest or accepting gaits.
