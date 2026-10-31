# Student build log: Tuba's Sesame S3 (Oct 15–31, 2026)

A hand-built Sesame S3 (ESP32-S3 SuperMini + PCA9685, SSD1306 OLED, 8× MG90S,
LM2596 5 V from the battery), worked through the APS-II build guide. This
records what failed, what fixed it, and what I customized on my own robot.
The general fixes are proposed separately for the reference firmware; everything
here is my personal firmware and is shared for reference only.

- `tuba-firmware.patch`: my personal firmware changes (living face, battery demo,
  diagnostics, speed, rest pose), diffed against `a90dc60`.
- `apply_calibration.py`: re-applies my calibration (clock, map, signs, limits)
  after a manifest change resets the saved record.

## Timeline: failures → fixes

| # | Symptom | Root cause | Fix / result |
|---|---|---|---|
| 1 | OLED went black when a laptop joined the Wi-Fi | supply dip reset the SSD1306 | re-assert non-blanking OLED setup every 2 s |
| 2 | No Hz meter for the PWM clock | — | measure hub CH15 on GPIO4 with one jumper: 55.66 Hz → oscillator 27,815,198 Hz, rechecked 49.94 Hz |
| 3 | SuperMini has no GPIO18 | board pinout | OE on GPIO7 + 4.7 kΩ pull-up (now adopted upstream) |
| 4 | Hub fault at every power-on with 8 servos plugged in | servo inrush disturbs the first hub setup | boot no longer latches; retry every 1 s (`hubService`), `rehub`, `diag` |
| 5 | Feet stopped short, L3/R4 not touching the ground | I had added a 10° margin to the limits | full 0/180 for the feet, all 4 touch at Stand |
| 6 | Battery demo did nothing, face blank | hub VCC not connected: **1.4 V** back-fed via SDA/SCL, so no ACK and the OLED jammed SCL | `diag` (empty scan, SDA/SCL levels) + voltage check; re-made the VCC connection |
| 7 | S3 panic `StoreProhibited` on a broken bus | IDF `i2c_master` ISR after a 5 ms timeout (decoded with addr2line) | I²C timeout 50 ms |
| 8 | On battery: rest → stand → reboot loop | `log` showed `stand;boot r9` (brown-out) when 8 servos load at once | soft start + battery demo moves rest/stand one joint at a time |
| 9 | Demo started while USB was still connected | `Serial` is "port open", not "cable present" | `HWCDC::isPlugged()` for battery-vs-USB |
| 10 | Wave/dance/walk looked small | stock motions ask for angles outside my saved limits (CLAMP) | feet 0–180, hips widened to the firmware soft range |
| 11 | OLED drops off I²C after some flashes/handling | loose OLED connector | reseat; secure the connector |

## What worked (keep doing)

- `diag` before guessing: an I²C scan plus SDA/SCL levels told "wiring/power" apart from firmware every time.
- An NVS event `log` (boot reset reason + OFF reasons) is the only way to see what happened on battery.
- Measure VCC at the hub itself; continuity on SDA/SCL/GND alone missed the real fault.
- Never USB and battery at the same time; flash on USB only.
- Multi-servo motion on battery only; USB browns out.

## My customizations (all in `tuba-firmware.patch`)

- **Living face**: procedural OLED face (blinks, glances, moods, talking mouth); `face alive`, `mood`, `look`, `say`.
- **Battery auto demo**: about 5 s after a battery power-on it loops rest → stand → rest → stand → wave → dance → walk (10 cycles = 20 steps), 5 s apart. BOOT/`off` stops it; `demo on|off|status`.
- **Speed**: controller rate 60 → 240 °/s (4× faster); calibration rate 60 °/s.
- **Limits**: feet 0–180; hips R1/L2 45–180, R2/L1 0–135 (needed for walk).
- **Rest pose**: all joints 90° (L4 was briefly 75–80°, then back to 90°).
- **Diagnostics**: `diag`, `rehub`, `log [clear]`, `i2cswap` (scan with SDA/SCL swapped).

Calibration: oscillator 27,815,198 Hz; default course map and signs (CH0 L1 … CH7 R4).
Battery result (build 16): 4× faster full loop including walk runs without brown-outs.

## Next

A Tachikoma (Ghost in the Shell) shell over the step-34 frame: printed head/top,
light or fabric abdomen, magnet/clip adapter plate, weight under ~60 g.
