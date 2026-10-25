# Course SuperMini output enable: GPIO7 / I17

October 25, 2026. The instructor selected **exposed GPIO7** as the canonical
course controller's OE pin, replacing the previous GPIO18 expectation. This is
a pin-contract correction, not a new motion mode or a physical-validation claim.

## One connection contract

| Connection | Carrier location | Native exposed header part |
|---|---|---|
| S3 GPIO7 → hub OE | I17 → A7 | `s3.male_pin.I17` → `hub.male_pin.A7` |
| OE pull-up → 3V3 logic VCC | A7 → A4 | `hub.male_pin.A7` → `hub.male_pin.A4` |

A3 is servo **V+**, not the pull-up rail. The hub side header contract is
A3=V+, A4=VCC, A5=SDA, A6=SCL, A7=OE, A8=GND. The reference geometry has exposed
pin-top centres in assembly millimetres: I17 `[43.89,44.05,18.85]`, A7
`[64.21,18.65,18.85]`, A4 `[64.21,11.03,18.85]`. These are CAD illustration
anchors, not measured jumper lengths or solder locations.

The parent's October 22 observation of the actual-board photo established the
USB-facing-A row TX, RX, 1, 2, 3, 4, 5, 6, 7 at A17… I17. That locates GPIO7
at I17 and leaves GPIO4/F17 for the clock input. It is not inferred from the
Waveshare Zero pinout. Existing native geometry records `Address=I17`; the hub
OE and VCC native pins match the documented side-header order. No assets were
regenerated or repositioned for this correction.

## Pull-up evidence: driven HIGH is not reset HIGH

Instructor-supplied private course bench notes report GPIO7 wired to OE with
**4.7 kΩ to 3V3**, approximately **3.2 V while GPIO7 actively drove HIGH**, and
stopping following a hub fault. These are student-reported observations, not
independent measurements by this change's author. Raw logs, student code and
private identifiers are not published or executed here.

Do **not** turn 4.7 kΩ into a universal reset-safety recommendation:

- The official Adafruit reference schematic connects **R7=10 kΩ from OE to GND**.
  A clone's actual bias network must be identified, not assumed identical.
- NXP specifies OE HIGH at a minimum of **0.7×VDD**. With a 10 kΩ pull-down and
  4.7 kΩ pull-up, the unloaded divider is `10/(10+4.7)=0.6803` of VCC: about
  **2.24 V at 3.3 V**, below the **2.31 V** guaranteed-HIGH boundary even before
  tolerances/leakage. This is a calculation for that reference circuit, not a
  measurement of a student's module.
- A driven-HIGH 3.2 V reading therefore does not establish what happens when
  the MCU pin is high-impedance during reset. Nor does a GPIO `digitalRead`
  alone establish the PCA's input-level margin. No student diagnostic code
  that releases OE or changes its bias is imported by this update.

For the actual class build, with servo plugs disconnected and logic VCC present,
check **OE-to-GND during MCU reset/high-impedance**, against the actual VCC and
PCA input-high requirement, with margin. If the node cannot remain HIGH, identify
the on-module bias and correct the pull-up/bias design before relying on reset
disable. The supplied evidence does not establish a universal replacement
resistor or validated reset waveform. This is a concrete electrical check, not
a student form or an extra approval gate.

OE HIGH disables PWM output; it does **not** disconnect servo V+ or prove that
all power has been removed. Firmware still asserts OE before I²C clearing, keeps
the watchdog/fault latch/output exclusion, and starts outputs-off. Hardware
reset bias is needed before firmware is running and cannot be certified by
those software properties.

## Calibration compatibility and scope

The current manifest identity changes with the OE selection. Valid saved records
with identities **`e669b916d178ac0a`** or **`bd7675604b98ae46`** are explicitly
accepted with the same binary-layout, checksum and calibration-validity checks.
Loading preserves map/sign/trim/limits/oscillator/verification values and does
not write NVS. There is no automatic map normalization, including for measured
custom maps; an explicit later `save` updates the record identity.

The recommended fresh map, shared Tim pulse profile, rate-limited full-range
`arm bench CH` pointer procedure, watchdog and stop semantics are unchanged.
There is no new load test, retry/recovery policy, device operation or measured
reset result. Historical bring-up sketches and archived evidence retain their
original GPIO18 references as historical records, not current wiring instructions.

## Public electrical references

Retrieved October 25, 2026:

- [NXP PCA9685 datasheet](https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf),
  Rev. 4, April 16, 2015, Table 14 p.39 (OE input thresholds), and OE behavior.
  Download SHA-256: `237d47f339cac4c3a0d56a5f0b4d3c93df71e3eb43f36ac57ea4ff38e6b2e585`.
- [Adafruit reference schematic](https://github.com/adafruit/Adafruit-16-Channel-PWM-Servo-Driver-PCB/blob/4e16c274ac3c99000c944d206bc1d9f8d4e20856/Adafruit%20PCA9685.sch),
  pinned commit `4e16c274ac3c99000c944d206bc1d9f8d4e20856`: R7=10K, terminal1
  on OE and terminal2 on GND. Schematic SHA-256:
  `8a6f94ed1fcf0c04a0c9d92438739bf56cec6a5e4837be6d3c93ed8ff1a8ec90`.
- [Adafruit pin descriptions](https://learn.adafruit.com/16-channel-pwm-servo-driver/pinouts)
  distinguish logic VCC, servo V+ and the default OE pull-down.

The private notes and photo observations establish reported class-build choices;
these manufacturer references establish reference electrical requirements.
Neither is a new reset-time test of the actual assembled robot.
