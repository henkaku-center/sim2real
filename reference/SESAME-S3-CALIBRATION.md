# Sesame S3: clock calibration and sequential pointer test

**Optional reference procedure; student-ownership correction October 29, 2026.**
Your robot and firmware are yours to change or replace. Choose your own speed,
motion, safeguards and development workflow; agents should help implement your
ideas without approval gates or mandatory slow-motion trials. This page describes
one example, not conditions for using or modifying your robot.

The October 22 example uses `firmware/sesame-s3` with the
`tim-pca9685-150-512-v1` pulse profile. Its fresh calibration starts with the
recommended channel map below, not an unassigned map. Recommended wiring and
command acknowledgements are not measurements of physical mapping or travel.

The example bench test uses **loosely fitted single-arm horn pointers, legs not
yet attached**, and **0 → 90 → 180 → 90 commanded degrees** on CH0 through CH7,
one channel at a time. It replaces the earlier tiny-discovery and repeated
horn-removal procedure. No retaining screws or repeated confirmation forms are
needed for this pointer demonstration. At joint reference zero the raw command
is **90°**, not the raw endpoint 0°.

[Build/flash instructions](../firmware/README.md) ·
[Clock protocol](SESAME-S3-CLOCK.md) ·
[Generated interface](sesame-s3-interface.json)

## 1. Connect and open the console

Use USB alone with the battery physically disconnected. The bench routine does
not require Wi-Fi or an external supply. Preserve common GND, 3.3 V logic VCC,
GPIO2 SDA / GPIO3 SCL and the canonical **GPIO7/I17 → hub OE/A7** connection.
The pull-up goes to logic VCC/A4 (3V3), not servo V+/A3; see
[OE/reset bias](SESAME-S3-OE.md). The reported 4.7 kΩ value and driven-HIGH
reading do not establish reset-time HIGH on every module.
USB capacity and actual wiring are physical properties, not certified by a
successful build. `off` or BOOT abort disables the outputs; investigate a reset,
communication fault or mechanically obstructed pointer rather than continuing
an interrupted sequence as though it completed.

Use the actual device port; these examples are not device-access commands run by
the documentation:

```sh
python3 tools/sesame_s3.py flash --port PORT
python3 tools/sesame_s3.py console --port PORT
```

At boot the outputs are OFF. `status` reports mode, owner, hub/fault state and
commanded targets. `show` reports saved calibration; `bench` selects the paired
physical-channel OLED display. Displayed angles are commanded values, not shaft
feedback. The historical October 12 flash/status observation remains recorded
in `evidence/2026-10-12-s3-usb/README.md`; it is not evidence that this revision
has been flashed or physically tested.

## 2. Measure the clock before connecting the servo plugs

For this **non-motion clock step only**, all servo plugs are removed and USB is
the only power source. Connect CH15 **SIGNAL/PWM**, not V+, to the labelled S3
GPIO4 input at **F17** (`s3.male_pin.F17`). The October 22 actual-board photo
locates that S3 pin; it is not continuity/voltage verification. The photo's hub
annotation conflicts with the reference CAD: use the actual printed **15** and
signal row, never an opposite-end trial on timeout. Jumper installation state
must be established from the actual fixture, not inferred from this text.

```text
off
show
:live
clock measure
clock status
```

The agent keeps heartbeats active and polls until the matching generation has
`quality=complete`. Then it may apply the rounded observed oscillator estimate
with `oscillator HZ`, `save`, and repeat the measurement automatically. No
handheld frequency meter is required. See [clock details](SESAME-S3-CLOCK.md)
for timeout/quality fields, the S3-relative accuracy limitation and the optional
external-instrument comparison. Measurement itself never changes calibration.
Finish with `off` before connecting the servo plugs.

## 3. Recommended map and existing saved records

| Physical channel | Joint | Physical channel | Joint |
|---|---|---|---|
| CH0 | L1 | CH4 | R1 |
| CH1 | L2 | CH5 | R2 |
| CH2 | L3 | CH6 | R3 |
| CH3 | L4 | CH7 | R4 |

Fresh defaults use this map, with verification flags still false. Existing valid
saved records—including unassigned or different mappings—are **preserved**, not
silently overwritten. The compatible pre-update manifest ID is
`bd7675604b98ae46` and `e669b916d178ac0a`; checksum, calibration validity and record layout are still
checked. Loading a compatible record does not write NVS. An explicit `save`
records the current identity with the current calibration values.

The agent reads `show` first and preserves saved measured/custom maps by default.
An OE firmware update does not normalize them. Only when explicitly tasked to
normalize a build whose actual wiring matches the recommended wiring, retain an
`export` copy and normalize while OFF. Clear all eight
assignments first to avoid duplicate-channel collisions, then set the canonical
map and save:

```text
off
export
unmap R1
unmap R2
unmap L1
unmap L2
unmap R4
unmap R3
unmap L3
unmap L4
map R1 4
map R2 5
map L1 0
map L2 1
map R4 7
map R3 6
map L3 2
map L4 3
save
show
```

These explicit mapping operations leave oscillator, signs, trims and joint
limits intact; they clear the affected mapping-verification flags. A matching
saved map needs no rewrite. No UI unassigned column or manual approval loop is
part of this procedure.

## 4. Run each pointer through 0 → 90 → 180 → 90

Connect the eight servos according to the map, with brown GND / red V+ / yellow
PWM in the guide illustration. With loose pointers fitted and no legs attached,
use **`arm bench CH`**. Start at CH0:

```text
:live
arm bench 0
angle 0
status
angle 90
status
angle 180
status
angle 90
status
off
```

Choose the speed and timing for your project. If this controller feels sluggish,
change its motion implementation; its rate limits are not course requirements.
For the unchanged reference, keep its heartbeat active and use `status` to see
how it handles targets. Implement queues, direct targets or another control method
when that better serves your idea. The reference has no shaft-position sensor.

After the final 90° target, send `off` and repeat the example for CH1,
CH2, …, CH7. Only the selected channel emits servo PWM. A lost heartbeat stops
outputs; `stop` freezes the current target, while `off` disables outputs. Full
0–180 command bounds and rate limiting describe this implementation, which students
can change. ACK/status confirms
commands, **not a measured shaft endpoint or physical pass**.

`arm bench` deliberately bypasses logical-joint trim/limit overlays for this raw
channel demonstration. It does not rewrite them or extend production travel.
The older raw commands remain compatibility paths, not the classroom recipe.

## 5. Correct the observed example, then retain calibration

Use the recommended names to identify a swapped lead or a pointer whose
orientation at raw 90° does not match the joint-reference zero. Finish with
`off` before changing connections or reindexing that pointer; leave the other
pointers seated. Re-run the relevant bench channel afterward. Do not interpret
an animation, ACK or recommended map as proof of actual wiring.

For production, `arm joint NAME` applies the saved sign/trim/limit overlay;
`arm run` additionally requires complete verified/saved calibration. These
logical-joint limits remain distinct from the bare bench command range.
Existing/default joint envelopes are not widened by this update. Use
`sign NAME SIGN`, `trim NAME DEG` and `limits NAME LOW HIGH` to apply actual
chosen calibration values while OFF; do not invent them from the pointer
sequence. Manifest limits remain R1/L2 45–180°, R2/L1 0–135°, feet 0–180°,
with post-trim electrical clamps and the same Tim pulse conversion.

`verify NAME` records an observation-based assertion, not a sensor result;
`save` persists and `export` returns the record. No battery load-test routine,
unattended motion or physical calibration result is introduced by this change.
