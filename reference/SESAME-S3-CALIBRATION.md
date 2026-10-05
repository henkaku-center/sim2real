# Sesame S3: centre, mount horns, calibrate

**2026-10-06 — NEEDS-HARDWARE.** One image provides calibration, OLED faces,
stock motions and the Wi-Fi controller. Nothing here claims an observed result
on the assembled robot. [Diagnosis](SESAME-S3-DIAGNOSIS.md) ·
[Build/flash instructions](../firmware/README.md) ·
[Machine-readable guide handoff](sesame-s3-interface.json).

## 1. Power off, disengage horns, flash

1. Support the body with every foot clear. Disconnect battery and USB. Remove
   the horn screws and **lift the horns off the splines**; merely loosening a
   screw while the spline remains engaged does not free the linkage. Label the
   joints using the robot's own left/right. Never turn a powered shaft by hand.
2. Confirm **GPIO18 → PCA9685 OE**, with OE pulled high to **3.3 V** during reset,
   common GND, GPIO2 SDA, GPIO3 SCL, logic VCC=3.3 V and regulated servo V+=5 V.
   OE wiring/power-source isolation are still unverified on the original build.
   Leave servo V+ disconnected while checking/flash programming. Do not assume
   the USB port or its 5 V pin can power eight servos.
3. Battery disconnected, USB only: run the [one-time setup](../firmware/README.md),
   identify the USB port, then flash:

   ```sh
   python3 tools/sesame_s3.py flash --port /dev/ttyACM0
   python3 tools/sesame_s3.py console --port /dev/ttyACM0
   ```

   On macOS use the actual `/dev/cu.usbmodem…` port. Opening the console may
   reset the S3. Expect `READY Sesame S3 calibration+controller; outputs OFF; help`
   at boot, or type `status`: `mode=0 outputs=0 hub=1 fault=0 owner=0 motion=none`.

## 2. Calibrate the PWM clock first (servo V+ off)

Use the USB console with **all servos unplugged**, especially CH15:

```text
:live
reference
show
```

Expect `OK REFERENCE CH15 requested_us=1500 ticks=307 prescale=121` with the
25 MHz default. Probe **CH15 signal → meter/scope**, **GND → GND**, not V+.
Measure frequency `f` with a multimeter frequency mode (a DC-voltage reading
does not measure pulse width), or measure the high pulse with a scope/analyser.

- Frequency method: `oscillator_hz = round(f_hz × 4096 × (prescale + 1))`.
  Example **only if measured**: 54.03112 Hz with prescale 121 → 27,000,000 Hz.
- Pulse-width method: `oscillator_hz = round(ticks × (prescale + 1) × 1e6 / measured_high_us)`.
  Use the printed **ticks**, not an assumed exact 1500 µs; quantization matters.

Type `off`, then `oscillator HZ` with your computed integer, then `save`.
Expect `OK CAL changed; verify after test, then save`, `OK SAVED NVS`.
Run `:live`, `reference`, `show` again and remeasure. About 50 Hz and
1500 µs within one tick (about 4.9 µs), plus instrument uncertainty, is expected;
the integer prescaler need not give exactly 50.000 Hz. Type `off`.
Do not guess 27 MHz. If no instrument is available, retain the nominal default
and mark the clock **unmeasured**; do not call pulse accuracy hardware-verified.

## 3. Centre before fitting horns

Power everything off; connect the eight servos to CH0–7 with correct polarity.
**Unplug USB before connecting battery.** With the horns disengaged, power the
robot from battery alone. It starts outputs-off. Release BOOT if held, then
**press and release BOOT once**. All CH0–7 receive raw 90° = **1830.5 µs** for
30 seconds; the display says `Centre …s`. A further BOOT press aborts. This
works without Wi-Fi, a channel map or a USB connection. Repeat after timeout
as needed; no screws/connectors should be changed with power applied.

Seat the horn lightly at the **Rest/90° reference orientation**, using the
[upstream angle diagram](https://github.com/dorianborian/sesame-robot/blob/c458a9ed2749ac675f7ddfdbb8705180a1ba3211/docs/build-guide/assets/sesame-angle-guide.png).
Choose the nearest spline without forcing the shaft; power off before securing
the screw or fitting/rearranging linkage parts. If the shaft moved while off,
re-centre with the horn disengaged. Do not substitute a generic tester's
1500 µs centre or the old load-test's “90°”: those are different references.
This is the **Rest/assembly** pose, not the bent-leg Stand pose.

For a verified isolated USB bench setup, the equivalent commands are
`:live`, `arm assembly`, `centre`, then `off`. They report
`OK ARMED outputs OFF until target` and `OK CENTRE CH0..7 raw=90 us=1830.50`.
Assembly centring ignores trims, even if an old calibration is saved.

## 4. Identify the channels; test one joint at a time

Use battery-only Wi-Fi (join `Sesame-S3-XXXX`, password `sesame123`, open
`http://192.168.4.1`, tick **Keep heartbeat**) or an instructor-verified isolated
USB bench supply arrangement. **Do not plug ordinary USB into the live battery
assembly.** If Wi-Fi fails and isolation is unverified, stop after the BOOT
centre step; diagnosis can continue USB-only with servo V+ off.

In the USB console `:live` enables heartbeats. In the web console use the
checkbox instead; the other commands are identical. Starting with CH0:

```text
arm channel 0
angle 90
jog 5
status
off
```

Expect `OK ARMED…`, `OK TARGET 90.00`, `OK TARGET 95.00`. Only that servo
should move, at ≤15°/s after initial neutral acquisition. Note its actual
joint name. Repeat for CH1–7. Assign **your observed** names, e.g. `map R1 4`
**only if CH4 really moved the front-right hip**. `map` runs outputs-off;
`unmap NAME` frees a channel before a swap. Every channel must be unique.
The old target map is in the JSON handoff, explicitly **not hardware verified**.

## 5. Direction, trim, limits; save

For each mapped joint (R1 example), with the body supported:

```text
:live
arm joint R1
angle 90
q 5
q 0
off
```

`q` is internal joint degrees; `angle` is canonical firmware degrees. Default
signs are R1/R3/L2/L4 **+1**, R2/R4/L1/L3 **−1**. Compare movement with the
angle diagram, not the apparent screen-left direction. If physically reversed,
set `sign R1 -1` (example for R1 only), re-arm and repeat. The signs are absolute
physical signs, not another multiplier to apply to the upstream pose angles.

Correct large neutral errors by re-indexing the horn. For a small residual,
`trim R1 2` adds **2 physical servo degrees** (example, not a measured trim).
Re-arm, `angle 90`, and inspect. Trims are limited to ±15°.

Initially each joint is limited to 85–95°. With outputs off, widen its `limits`
in small stages, then re-arm and `jog 5`/`jog -5`, or `sweep 85 95` for one
low→high→neutral pass. Do not immediately command endpoints. Stop short of
binding/buzzing; record the usable range, which may be narrower than the
manifest. Manifest ceilings: R1/L2 **45–180°**, R2/L1 **0–135°**, feet
**0–180°**. These correspond to hips **q=[−45,+90]**, feet **q=[−90,+90]**.
For example, `limits R1 80 100` allows the next small inspection; it does not
certify that range. `us 1830.5` uses the same gate; it cannot bypass limits.
Post-trim electrical endpoints may further narrow the target (`CLAMPED`).

Once that joint's map, neutral, direction and chosen range are observed:

```text
off
verify R1
save
show
export
```

Repeat for all eight. `verify` records **your assertion**, not a sensor result.
`export` prints JSON matching the handoff's `calibration_schema`; save it with
robot identity, frequency measurement, photos and date. Power-cycle, then
`show` must reproduce the values with `saved=1`. Every boot remains outputs-off.
Only then use `:live`, `arm run`, `motion rest`; proceed to `motion stand`,
`motion wave`, `motion dance` individually if measured travel permits.
No reflash is needed. A `CLAMP` means choreography was limited; it is not a
successful full-range trick. **BOOT or `off` releases torque; support the robot.**
