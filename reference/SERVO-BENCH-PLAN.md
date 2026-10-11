# Sesame bench commissioning — decisions and firmware comparison

October 11, 2026. Current APS-II course preparation. **Design review, not a
released replacement for the calibration procedure.** No firmware or pulse-profile
change has been made. The instructor asked to compare the options before choosing.

## Confirmed course direction

- Steps 29–33 should establish firmware behaviour and horn alignment before legs.
- Use the **single-arm horn**, lightly seated without its retaining screw. It is
  a visual pointer during unloaded tests, not a permanent attachment. Re-index
  only with power off; never turn a powered shaft by hand.
- Show all eight three-conductor leads (24 rendered conductors), not schematic
  stand-ins. Label each servo by intended joint and actual hub channel.
- Use a visually organised bench: four leg positions, each with upper/lower
  servos, labels readable in one view. Define left/right from the robot's view.
- The student asks their agent to load and guide the debug firmware, reports what
  physically moved, and iterates before fastening horns/attaching legs.
- The instructor authorised republication/adaptation of Tim's selected code.
  Pinned, byte-preserved inputs now live in `vendor/tim-servo-debug/`.
- Wi-Fi is not reliable enough to be the required class debugging path.

## Three things which must not be conflated

1. **Observed wire/channel identity.** A label or intended table is not a test.
2. **Firmware neutral.** A command called 90 degrees can mean different pulses.
3. **Mechanical alignment.** A single-arm pointer can be re-indexed on its spline
   without changing firmware; small trim corrects the residual after indexing.

## Firmware choices

| Property | Tim's diagnostic at 98d030a | Existing APS controller at 55eae6d |
|---|---|---|
| Behaviour | Repeating loop: each channel 0, 90, 180, return 90, release | Explicit serial/web commands; outputs off at boot |
| Agent interaction | Serial output only; no command parser | Commands, status, bounded moves, stop/off, external heartbeat |
| Motion timing | Blocking delays; target jumps | Nonblocking; bounded rate after initial neutral acquisition |
| Channel identity | Fixed intended mapping | Per-device mapping; starts unassigned |
| Calibration | No per-device save/export in test sketch | Oscillator, map, signs, trims, limits, verification; NVS + JSON |
| Display | Paired left/right commanded-angle table | Controller/calibration display and faces |
| Production relationship | Same 150–512-count mapping as Tim's full S3 controller | Same maintained image handles calibration and later motions |
| Initial range | Immediately requests endpoints | Narrow discovery range; expand deliberately after observation |

Tim's table display and physical-channel ordering are useful starting points.
For an agent-guided classroom session, retain our bounded command path rather than
flashing his unchanged automatic endpoint sweep.

### The neutral mismatch

At a **nominal actual oscillator of 25 MHz** and prescale 121, each PCA tick is
4.88 microseconds. Tim's integer interpolation gives 150/331/512 counts for
0/90/180 degrees, or **732.00 / 1615.28 / 2498.56 microseconds**. The APS manifest
requests **732 / 1830.5 / 2929 microseconds**, rounded to available PCA counts.
Neither table establishes physical travel or a universal MG90S mechanical centre.

Changing between them after fitting horns changes the meaning of 90 degrees.
See `SESAME-S3-DIAGNOSIS.md`; do not silently reinterpret saved calibration.

**Recommendation for decision:** use one maintained APS debug/production image,
with Tim's paired-channel diagnostic presentation. Choose its pulse profile before
horn calibration. If compatibility with Tim's existing production motions is the
priority, adopt a separately identified Tim-compatible profile in the canonical
manifest and generate both debug and production definitions from it. If retaining
the current APS profile, calibrate and remain on that profile; do not claim its
wider electrical range is automatically better or safe for every servo.

The choice is pending instructor review. Do not update `manifest/robot.yaml`, its
S3 profile, NVS fingerprint, interface JSON or the guide's firmware pin until chosen.

## Wired power recommendation

For bench debugging, prefer **USB-powered S3 logic plus separately supplied,
regulated 5 V servo V+**, sharing ground but not positive supplies. PCA logic VCC
remains 3.3 V. Servo current must not flow through the computer USB connection.
Use a current-limited bench supply for initial bring-up, starting with one servo;
determine the eight-servo supply budget from the actual units and tests.

Our carrier is not yet verified for this arrangement. The instruction records show
converter OUT+ routing into both the servo-power and S3-side wiring. Tim's netlist
instead describes an SPDT source selector; our build has a two-terminal toggle.
Do not copy his power schematic as an as-built description of this carrier.

Possible reversible bench fixture: lift the removable S3 out of the carrier and
connect only the required logic/power-reference signals via a verified harness,
leaving its USB/5 V rail disconnected from servo V+. Determine the actual 3V3,
GND, SDA, SCL and OE terminals and their reset behaviour on the real assembly
before turning this into student instructions. An interposer is another option.
This is a design candidate, not an accepted wiring recipe.

A generic USB isolator or a different USB cable alone is not evidence that two
positive power sources cannot meet. Confirm the schematic and unpowered continuity,
then test powered rails/current under supervision before publishing the fixture.

Reference: [Adafruit PCA9685 power guidance](https://learn.adafruit.com/16-channel-pwm-servo-driver/hooking-it-up)
separates logic VCC from servo V+ and documents servo-current demands. That guide's
5 V Arduino logic example does not change our S3's 3.3 V logic requirement.

## Proposed replacement sequence (29–33)

| Step | Visual | Student action |
|---|---|---|
| 29 | One enlarged servo; single-arm horn above spline; retaining screw set aside | Seat lightly. It is a movable reference pointer; do not screw it down. |
| 30 | All eight servos arranged in four leg pairs; all 24 conductors and plugs visible | Wire to hub, label joint + CH number, compare with intended map. |
| 31 | USB-to-computer and verified separate servo-power arrangement | Give the agent our `debug-firmware.md`; identify board, clean-build and flash with servo power off. |
| 32 | One channel highlighted; horn pointer and expected movement | Agent guides neutral, small +/- movement, return and off. Student identifies actual movement; correct mapping/indexing. |
| 33 | All eight labelled pointers at the chosen common reference | Repeat, save/export calibration and verify after restart. Fasten only after acceptance; leg attachment follows later. |

The eight leads must match the fixed rendering layout and selected channel map,
not end at arbitrary positions. Horn rotation must be a shaft-local rigid transform.
Do not depict arbitrary “correct” reference directions until the single-arm horn
dimensions and the leg-specific indexing reference are established.

## Hardware observation this session

Artemis enumerated USB `303a:1001`, `/dev/ttyACM0`, with stable by-id suffix
`D4:05:92:47:C8:B0`. This is a USB-detection result only. No serial command,
reset, flash or servo actuation was performed by this preparation work.
