# S3-measured PCA9685 clock — agent procedure

October 21, 2026. This is a bounded **non-motion** measurement feature in the
interactive `sesame-s3` controller, not the offline load-test lifecycle model.
It retains `tim-pca9685-150-512-v1`. No physical device IO, flashing or measurement
was performed while developing it. The actual jumper/device state is **unknown**,
not asserted absent. Once the fixture and device access are established, an
agent can run measure → explicit apply → remeasure without a handheld meter.
This is not a new universal human-supervision rule or approval form.

## Connection and the remaining pin-binding gap

- USB only, battery physically disconnected, **all servo plugs removed** during
  this clock step. CH0–14 remain full-off; only CH15 produces the reference.
- Female jumper: **CH15 PWM/SIGNAL → S3 GPIO4**, with existing common carrier
  GND. Never connect the middle V+ pin to the S3 input. PCA logic VCC must be
  3.3 V; the measurement code cannot detect an incorrect signal voltage.
- GPIO4 is newly reserved in `manifest/robot.yaml`. It is distinct from the
  controller's SDA2, SCL3, OE18, BOOT0 and native USB19/20 assignments. Firmware
  configures it as input with pulldown; it is never driven as an output.
- Hub reference CAD: CH15 is `cad.Part__Feature128.pin.2` and coincident copy
  `cad.Part__Feature144.pin.2`. The APS exporter explicitly assigns rows
  `.pin.0=GND`, `.pin.1=V+`, `.pin.2=PWM`, edge inward. The native numeric
  silkscreen marks that column 15.
- **Installed SuperMini carrier address / S3 header part remain unresolved.**
  `s3-installation.json` documents A11–I17 geometry, not an electronic pin map.
  Its imported `ESP32-S3_Zero.step` is reference geometry. The official Zero
  pinout has a 5V/GND/3V3/GP1…GP6 side and a TX/RX/GP13…GP7 side, which does not
  match the existing diagram's D17=GPIO2/E17=GPIO3 claim under the recorded CAD
  rotation. Do **not** extrapolate F17=GPIO4 from those two addresses. Establish
  the actual board's labelled GPIO4 and its carrier position from its specific
  pinout/photo before drawing the second endpoint as a verified native part.
  The generated interface intentionally uses `null` for both carrier fields.

There is no reason to invent a carrier address or flash a device merely to close
this documentation gap. Physical execution additionally requires the actual
USB endpoint/firmware identity and the existing OE/reset-disable wiring to be
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
preserved when adding the read-only input field; all pre-existing manifest bytes
still participate in the compatibility hash. The old external-meter `reference`
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

- [Waveshare Zero pinout](https://www.waveshare.com/wiki/ESP32-S3-Zero#Pinout)
  and its [labelled photograph](https://www.waveshare.com/w/upload/8/87/ESP32-S3-Zero-details-inter.jpg).
  Reference-board evidence only; not proof that the installed SuperMini shares it.
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
