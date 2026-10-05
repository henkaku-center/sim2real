# Sesame S3 range, neutral and Wi-Fi diagnosis

**2026-10-06. Offline source investigation; NEEDS-HARDWARE.** Owner reports a
fully assembled robot with misalignment/restricted movement, firmware unchanged
since September22. The installed image remains the old `servo-load-test` until
the owner flashes the new image. No hardware was connected, commanded or flashed
during this work. Reading archived sources/logs on Artemis is not a robot test.

## Findings: distinguish intended range from effective upstream output

| Item | Source-confirmed finding | What still needs measurement |
|---|---|---|
| Pulse range | Bring-up/full S3 use150..512 PCA ticks, not manifest732..2929µs | Actual physical shaft travel per servo |
| Upstream library | `attach(pin,732,2929)` is **clamped to732..2500** by ESP32Servo3.0.9 | Which library/version built any older physical S2 firmware |
| Clock | Existing sketches assume25MHz; no measurement/compensation recorded | Actual PCA oscillator/frequency and pulse high time |
| Horn index | Old “90°” is~1615µs; new manifest centre is1830.5µs | Whether horns were mounted at that old centre, spline offset per joint |
| Channel map | Intended map differs from logical order; owner reported wrong movement order | The actual as-wired map, all eight directions and trims |
| Wi-Fi now | Installed load test contains **no Wi-Fi code** | Visibility after new controller flash |
| Wi-Fi September22 | Full source ignored `softAP()` return; log's “AP Created” did not check success | RF/antenna, board power and AP behaviour on this unit |

### Exact pulse calculation

Old code: `ticks = 150 + floor(362 * degrees / 180)` and `setPWMFreq(50)`.
At an ideal50Hz period its endpoints are732.42 and2500µs. More precisely,
Adafruit3.0.3 selects **prescale121** for25MHz; each tick is4.88µs:

| Requested angle | Old ticks | Old high time (25MHz actual) | Manifest intended high time |
|---|---:|---:|---:|
| 0° |150|732.00µs|732.00µs|
| 90° |331|1615.28µs|1830.50µs|
| 180° |512|2498.56µs|2929.00µs|

Relative to the *manifest's intended pulse span*, the upper range is short by
about19.5%; old90° corresponds to about72.37° on that intended linear scale.
This is an electrical mapping comparison, **not a measurement that every MG90S
is mechanically missing20% of travel**. The full S3 source deliberately chose
512 ticks to match ESP32Servo's effective2500µs cap. Thus “we accidentally
removed20% relative to upstream physical motion” is not established. The new
code implements the user's requested manifest range, which **widens** the old
electrical range and requires disengaged-horn calibration and measured limits.
2929µs may reach beyond a particular servo's useful/mechanical endpoint.

### Clock error is independent of pulse-range selection

PCA period = `4096 × (prescale+1) / actual_oscillator_hz`;
high time = `ticks × (prescale+1) / actual_oscillator_hz`.
With old prescale121 unchanged:

| Actual oscillator (examples, unmeasured) | Frame frequency | Old0°/90°/180° high times |
|---|---:|---|
|25MHz|50.0288Hz|732.00 /1615.28 /2498.56µs|
|26MHz|52.0300Hz|703.85 /1553.15 /2402.46µs|
|27MHz|54.0311Hz|677.78 /1495.63 /2313.48µs|

Adafruit's own3.0.3 example describes roughly23–27MHz variation and illustrates
`setOscillatorFrequency(27000000)`. This supports measuring each board; it does
not prove this clone is26–27MHz. Changing only the library oscillator variable
while continuing to use fixed150..512 ticks does **not** implement the intended
microsecond range. New firmware sets oscillator before50Hz, reads/checks the
actual prescaler and uses rounded microsecond-to-tick math. Resolution remains
about4.9µs at50Hz; rounding error is at most half a tick, plus the uncertainty
in the owner's oscillator measurement. It is not a1µs-resolution DAC.

### Neutral, signs, trim and physical channel order

Both upstream Rest and the manifest use all90°. Stand is, in canonical order
R1,R2,L1,L2,R4,R3,L3,L4: **135,45,45,135,0,180,0,180**. Do not use Stand
to mean “all centred”. Upstream build instructions fit joints while standing;
our horn-mount procedure instead uses Rest/90° as explicitly requested.

Upstream sends *absolute servo degrees*, with `clamp(angle+servoSubtrim,0,180)`;
it has no separate per-joint sign transformation. Its trims start at zero;
`subtrim save` prints a C array rather than persisting NVS. The September full
firmware query returned eight zeros, and the diagnostics use no trims at all.

Manifest internal angle is `(firmware_angle-90) × manifest_sign`. Signs are
**+1 R1/L2/R3/L4**, **−1 R2/L1/R4/L3**; these are mounting conventions, not
eight calibration measurements. The new physical mapping is:

```text
electrical_angle = 90 + trim + physical_sign * manifest_sign * (firmware_angle - 90)
```

Matching default signs cancel for upstream absolute-angle commands; they are
not applied twice. Trims are added in physical servo degrees. The gate
intersects measured logical bounds, manifest bounds and post-trim electrical
0..180°. Endpoint clipping is reported, not compensated by overdriving pulses.

The **sole machine-readable guide handoff** is
[`sesame-s3-interface.json`](sesame-s3-interface.json), generated from canonical
manifests alongside the firmware. It includes logical order, target PCA channels,
null hardware-verified channels, per-joint soft ranges, command catalog and
the export/NVS calibration schema. Target-only map in canonical order:
**4,5,0,1,7,6,2,3**. No target is preinstalled as a measured map: all new NVS
channel defaults are−1. The simulator's S2 GPIO fields remain unchanged.

A horn installed one or more spline teeth off produces a persistent angular
offset and can make linkage contact restrict otherwise usable servo travel.
Re-index it mechanically before applying small trims. Spline tooth count and
the actual offsets on this mixed-servo build are unknown; no specific degree
per tooth or measured horn error is asserted. Wrong channel order is established
by the owner's September report, but the correct wiring cannot be inferred
from code. Oscillator drift, horn indexing and mechanical limits remain candidate
contributors until the owner performs the procedure.

## Full controller and invisible-AP investigation

The new single image includes all19 manifest motions and pinned upstream face
bitmaps. Motions execute as a nonblocking state machine through the same gate
as calibration. USB and web share NVS and command semantics. Raw benchmark
motion cannot bypass the rate, pulse, channel, watchdog or stop gates.

**Immediate AP explanation:** the currently installed load test never starts
Wi-Fi. For the earlier full image, source and `full-boot.log` show only a claimed
IP, not a checked `softAP` return or a radio scan. AP-only mode was already
intended, so STA channel migration is not a proven historical cause. There is
no evidence of a hardware antenna failure or insufficient TX power yet.

The port makes this diagnosable:

- Explicit AP-only, station credentials not reused, visible SSID
  `Sesame-S3-XXXX`, fixed channel1, password `sesame123`, IP192.168.4.1.
- Country set using `esp_wifi_set_country_code`, defaultJP for the course;
  `wifi US 1 8.5` selects US for a bench there. Channels limited to1–11.
- Requested8.5dBm as a conservative starting point, sleep disabled, all setup
  return values logged. `wifi` prints actual channel/hidden/country/TX setting,
  clients and get-API errors. Requested and actual power can differ due to
  the driver's discrete supported settings; readback is configuration, not
  radiated-power measurement.
- With servo V+ off over USB, compare `wifi JP 6 8.5`, then channel11; compare
 2/8.5/13dBm **one variable at a time**.19.5 is available as a comparison, not
  the first proposed remedy. Use the country where the test is actually run.
- Scan on a2.4GHz-capable phone/computer at0.5–1m. Record SSID/channel/RSSI,
  boot/reset messages and supply state; test bare-board antenna clearance away
  from battery, converter, metal, servo wiring and enclosure. A SuperMini's
  antenna implementation varies by board; inspect this board's actual antenna
  and any RF-selection components before assuming it has an external-antenna
  connector. Do not prescribe antenna solder modifications from a photo.

**Proposed fix order:** restore an actual AP-capable image, inspect checked
startup results, use explicit channel/country/moderate TX power, then isolate
placement and supply effects. If it remains invisible with correct API results
on two receivers and servo power disconnected, compare the same image on a
known-good S3 board. That discriminates assembly/board RF from software without
guessing at antenna or oscillator faults. Hardware Wi-Fi acceptance remains open.

## Sources and reproducibility

- Local upstream `../sesame-robot` at `c458a9ed2749ac675f7ddfdbb8705180a1ba3211`:
  `firmware/sesame-firmware-main.ino` attach/setServoAngle/subtrim code,
  `movement-sequences.h` Rest/Stand and the angle guide.
- Preserved full S3 build on Artemis, source
  [`tim003/CIT_FC_Robotics@98d030a`](https://github.com/tim003/CIT_FC_Robotics/blob/98d030a2d1e2e2e1f195669a9f87fcf9c5f1d465/firmware/sesame-s3-pca9685/sesame-s3-pca9685.ino):
  explicit explanation of ESP32Servo's clamp; `firmware/common/sesame_servo_map.h`
  constants150/512 and target map. Its archived boot log is the prior state
  record's `full-boot.log`.
- Installed ESP32Servo**3.0.9**, `src/ESP32Servo.h:MAX_PULSE_WIDTH=2500`,
  `src/ESP32Servo.cpp:attach` clamps max; matches the
  [library's documented attach contract](https://github.com/madhephaestus/ESP32Servo).
- [Adafruit driver3.0.3](https://github.com/adafruit/Adafruit-PWM-Servo-Driver-Library/blob/3.0.3/Adafruit_PWMServoDriver.cpp):
  oscillator/prescale/tick math; its `examples/servo/servo.ino` describes measuring
  oscillator variation. Local installed source was inspected, not just examples.
- [Espressif S3 Wi-Fi API](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/network/esp_wifi.html):
  AP/STA channel interaction, country-code validation, TX power readback.
  The actual port compiles against pinned Arduino core3.3.11's headers.
- Faces vendored from upstream `86d2bf8099754fd548c7cf98ee11fc9e9cdb5092`:
  archive bytes matched GitHub's pinned contents API SHA-256
  `722692894402d9eccf5c022ed7b4eb090c2de6b171b7872cedce55609dac1f06`.

### Offline validation

Native C++ tests exercise actual firmware gate/parser code under AddressSanitizer
and UndefinedBehaviorSanitizer: pulse endpoints at23/25/26/27MHz, half-tick
rounding, sign reversal, post-trim endpoint clipping, duplicate maps, corrupt
values, off/arm/centre, one-channel isolation, rate caps, watchdog wraparound,
stale heartbeat, stop, non-self-feeding sequences, invalid numbers/overlong lines,
and all19 stock-motion soft bounds. **23 macOS pytest tests passed**, including
existing manifest/SafeAction tests. The same native sanitizer executable passed
on Linux. Clean Arduino builds passed on **macOS15.7.9 x86-64** and **Linux
x86-64 (Artemis)**: 1,019,565 and 1,019,533 sketch bytes respectively (77% of the
1,310,720-byte slot), both48,128 bytes global RAM. No compile warnings were emitted.
[Permanent validation evidence](evidence/2026-10-06-sesame-s3/offline-validation.json)
records source/binary hashes, commands and the exact boundary of these results.
The toolchain/source inputs are pinned; byte-identical binaries across build
paths/timestamps are not claimed. No hardware result is inferred from compilation.

## Owner session — 30–60 minutes, stop at the first failed prerequisite

1. **0–10min:** battery/servo V+ disconnected, horns disengaged, inspect OE
   and power isolation; flash `python3 tools/sesame_s3.py flash --port PORT`.
   Open console; `status` → `mode=0 outputs=0 hub=1 fault=0`. `face happy`
   → `OK FACE`; `wifi` should show `ok=1`, channel1, hidden0, get_errors0,0,0.
   Scan for `Sesame-S3-XXXX`; no RF result is pre-assumed.
2. **10–20min:** all servos unplugged, USB-only. `:live`, `reference`, `show`.
   Measure CH15 frame frequency; compute `f ×4096×(P+1)`. `off`,
   `oscillator <measured-Hz>`, `save` → `OK SAVED NVS`; repeat reference and
   verify~50Hz/1500µs. No meter? Mark clock unmeasured and defer certification.
3. **20–30min:** power off, connect eight servo leads CH0–7, unplug USB,
   battery-only boot. BOOT press/release → `Centre …s`, raw90° for30s.
   Seat horns at Rest orientation; power off to fasten. Repeat centring if needed.
4. **30–45min:** using battery Wi-Fi or verified isolated USB, enable heartbeat;
   `arm channel 0`, `angle 90`, `jog 5`, `status`, `off` → one servo moves.
   Repeat0–7; `map NAME CH` from observation. `arm joint NAME`, `angle 90`,
   `q 5`, `q 0`, `off`; adjust `sign`, small `trim` and staged `limits` while off.
   Eight careful endpoint checks may need a second session: do not rush to stand.
5. **45–55min:** `off`, `verify NAME` for each actually checked joint, `save`,
   `show`, `export`. Retain JSON and measured frequency/robot identity. Power-cycle;
   `show` must retain values and outputs remain off. In a supported single-joint
   test, `:pause` → `OFF watchdog >500ms`; subsequent heartbeat must not resume.
6. **55–60min, only if ready:** `:live`, `arm run`, `motion rest`, then one
   supported `motion stand`/`motion wave`/`motion dance` at a time. Expect
   `OK MOTION NAME` then `OK MOTION complete`; inspect any `CLAMP` report.
   `stop` → `OK STOP frozen…`; **BOOT press or `off` releases all outputs**.

**Abort:** unexpected joint/direction, linkage contact, sustained buzz/stall,
hot servo/regulator, reset/brownout, lost heartbeat, I²C fault or unverified
USB/battery isolation. Support the body, press BOOT/`off`, then disconnect
servo power if needed. Do not keep retrying a stalled endpoint. A wrong map or
unknown horn index is corrected before any multi-joint pose. First acquisition
of neutral is open-loop and can jump; disengage horns for that first test.
