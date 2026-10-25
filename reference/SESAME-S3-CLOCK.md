# S3-measured PCA9685 clock — agent procedure

October 21, 2026. This is a bounded **non-motion** measurement feature in the
interactive `sesame-s3` controller, not the offline load-test lifecycle model.
It retains `tim-pca9685-150-512-v1`. No physical device IO, flashing or measurement
was performed while developing it. The actual jumper/device state is **unknown**,
not asserted absent. Once the fixture and device access are established, an
agent can run measure → explicit apply → remeasure without a handheld meter.
This is not a new universal human-supervision rule or approval form.

## Connection and photo-located S3 input

- USB only, battery physically disconnected, **all servo plugs removed** during
  this clock step. CH0–14 remain full-off; only CH15 produces the reference.
- Female jumper: **CH15 PWM/SIGNAL → S3 GPIO4**, with existing common carrier
  GND. Never connect the middle V+ pin to the S3 input. PCA logic VCC must be
  3.3 V; the measurement code cannot detect an incorrect signal voltage.
- GPIO4 is newly reserved in `manifest/robot.yaml`. It is distinct from the
  controller's SDA2, SCL3, OE7, BOOT0 and native USB19/20 assignments. Firmware
  configures it as input with pulldown; it is never driven as an output.
- Hub **reference CAD only**: CH15 is `cad.Part__Feature128.pin.2` and coincident copy
  `cad.Part__Feature144.pin.2`. The APS exporter explicitly assigns rows
  `.pin.0=GND`, `.pin.1=V+`, `.pin.2=PWM`, edge inward. The native numeric
  silkscreen glyphs `cad.Part__Feature245` / `246` spell 15 at x≈58.47, near the
  USB-facing A end. CH0 is column115 at x≈11.68, the opposite end. This native
  ordering **conflicts** with the new photo's far-end “Try first CH15” annotation.
  The parent could not fully read the actual printed hub number, so an as-built
  hub-to-native-part mapping is not established. Keep those IDs reference-only.
  Use the actual printed **15** and **SIGNAL/PWM** row; do not adopt the photo's
  suggestion to try the opposite end if no signal is detected.
- **GPIO4 is now photo-located at F17: `s3.male_pin.F17`.** On October 22 the
  user supplied an annotated actual-board photograph in the canonical APS guide
  conversation. The parent directly observed the right-side labels, far end
  toward USB: **7, 6, 5, 4, 3, 2, 1, RX, TX**, with 4 explicitly circled.
  Combined with the documented USB-facing-A installation, the row is
  A17=TX, B17=RX, C17=GPIO1, D17=GPIO2, E17=GPIO3, **F17=GPIO4**,
  G17=GPIO5, H17=GPIO6, I17=GPIO7. The native male pin carries `Address=F17`.
  This supersedes the earlier unresolved binding: it is not an inference from
  GPIO2/3 adjacency or from the Waveshare Zero reference model.
  The child did not receive the attachment as a local file and records no image
  hash. This is parent-observed user-photo provenance, not direct child image
  inspection or a physical continuity/voltage measurement.

The photo does not show the measurement jumper installed; its current state
remains unknown. Physical execution additionally requires the actual
USB endpoint/firmware identity and the [GPIO7 OE/reset-disable wiring](SESAME-S3-OE.md) to be
established. None is checked by the offline tests.

## Commands and automation

Using the class console (or an agent that sends `heartbeat` every 200 ms):

```text
off
show
:live
clock measure
clock status
```

`:live` belongs to the host console, not firmware. Keep heartbeats running while
polling `clock status` every ~200 ms. Start is USB-only and requires OFF. Read-only
status is available on either transport. An accepted start returns its generation
ID; accept a result only for that generation and `quality=complete`.

The capture averages **100 periods from 101 rising edges**, usually about two
seconds. It has a 4000 ms deadline and retains the existing 500 ms heartbeat
watchdog. No edge-count-per-one-second quantization is used. `clock status` gives
generation, quality, GPIO, prescale, edge count, observed Hz, oscillator estimate,
minimum/maximum periods, jitter ppm, timeout flag and `applied=0`.

After a complete result, outputs are already OFF. To apply a new estimate:

```text
oscillator HZ
save
clock measure
clock status
show
off
```

Replace `HZ` with the rounded estimate from that completed measurement, never a
nominal/example value. The agent may perform this explicit correction and second
measurement automatically within the clock-calibration task. Compare the new
frequency to `oscillator_hz / (4096 * (prescale + 1))` from the updated `show`;
prescaler quantization means it need not be exactly 50.000 Hz. Require repeatable
complete captures, rather than treating one plausible number as proof of wiring.

Measurement **never writes NVS, changes oscillator calibration or clears joint
verification**. The existing `oscillator HZ` operation clears all verification;
`save` persists only on explicit command. The legacy calibration manifest ID is
preserved when adding the read-only input field. The later recommended-default
policy produces a new current identity but explicitly accepts the prior
same-layout `bd7675604b98ae46` records without changing their values or writing
NVS. See [map normalization and the full pointer sequence](SESAME-S3-CALIBRATION.md).
The October 25 OE pin correction additionally accepts `e669b916d178ac0a` records;
neither update automatically normalizes a saved measured/custom channel map.
The old external-meter `reference`
command remains available as an independent comparison method.

`off`, `stop`, `clock abort`, BOOT abort, malformed/conflicting commands,
disconnect, watchdog, deadline and I2C/prescale faults terminate capture and
assert OE before clearing all channels. Completed/rejected results remain
readable until another measurement starts. A new generation rejects stale ISR
callbacks. Rejected quality, timeout or fault results must not be applied.

## Accuracy and source evidence

`observed_hz = (edges - 1) × 1e6 / (last_edge_us - first_edge_us)`;
`oscillator_estimate_hz = observed_hz × 4096 × (prescale + 1)`.
ISR timestamps use S3 `esp_timer_get_time()`, with microsecond resolution. This
compares the PCA oscillator to the **S3 clock**, not a calibrated laboratory
frequency standard. GPIO interrupt latency, missed/noisy edges and S3 oscillator
error still matter. Averaging reduces endpoint quantization; it does not prove
absolute accuracy or make every multimeter less reliable.

Algorithmic quality rejection: each observed period must be 10000–40000 µs,
peak-to-peak jitter at most 2% of the mean period, and estimated oscillator
20–30 MHz. These are detection bounds, **not an accuracy specification**.

Primary sources consulted October 21, 2026:

- October 22 user-supplied actual-board photo, observed by the parent session as
  described above. This resolves the S3 GPIO4/F17 location; no local image hash
  is available. It does not resolve the hub annotation/reference-CAD conflict.
- [Waveshare Zero pinout](https://www.waveshare.com/wiki/ESP32-S3-Zero#Pinout)
  and its [labelled photograph](https://www.waveshare.com/w/upload/8/87/ESP32-S3-Zero-details-inter.jpg).
  Reference-board evidence only; not the source of the now-established F17 binding.
- [Espressif ESP Timer](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/esp_timer.html#obtaining-current-time)
  documents ISR use of the microsecond time source. The installed pinned Arduino
  core 3.3.11 `esp32-hal-misc.c` also implements `micros()` with that function;
  `esp32-hal-gpio.c` provides `attachInterruptArg`/`detachInterrupt`.
- [Adafruit PCA9685 pinouts](https://learn.adafruit.com/16-channel-pwm-servo-driver/pinouts)
  distinguishes output logic VCC from servo V+ and describes OE. Do not infer a
  particular clone's resistor values or wiring from the reference board.
- Local native geometry and footprint:
  `assets/cad/instructions/s3-installation.json`,
  `tools/cad_history/add_s3_supermini.py`; APS
  `scripts/export_sesame_build.py::split_servo_pins` and
  `docs/ii/sesame-build/assets/assembly.json`.

Software checks: `tests/test_s3_clock.py`, affected native SafeAction/parser tests
in `tests/test_s3_firmware.py`, generated-interface reproducibility, and the
pinned Arduino build. They do not establish physical GPIO routing, jumper state,
electrical levels, oscillator accuracy or RF behaviour.
