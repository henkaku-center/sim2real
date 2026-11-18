# Sesame S3 build — session log for review

**Student:** Tuba · **Course:** APS-II (Chiba Tech) · **Dates:** 2026-10-15 → 2026-10-31
**Guide:** <https://aps.chibatech.dev/ii/sesame-build/> (worked steps 28 → 34)
**Firmware:** since Oct 29: `henkaku-center/sim2real` @ `481630e` + upstream `a90dc60`, branch `tuba/fresh-face` (builds 9–16; diff `patches/fresh-face_on_481630e.diff`). Oct 15–22 work archived on `tuba/archive-2026-10-29` (builds 1–8). Version table: `BUILD-VERSIONS.md`.
**Assistant:** Claude Code (AI), driving the robot over the USB serial console; all physical work, measurements and observations by the student.
**Running detail:** `BUILD-NOTES.md` (step-by-step notes, extra steps with purpose and benefit, instructor questions).

## Files in this folder
| File | What it is |
|---|---|
| `SESSION-LOG.md` | This summary |
| `BUILD-NOTES.md` | Detailed build notes |
| `patches/` | Firmware diffs vs. the course revisions (see `BUILD-VERSIONS.md`) |
| `hz-check-jumper-photo.jpg` | Board photo marked for the PWM clock (Hz) self-measurement jumper: hub CH15 → S3 GPIO4 |
| `IMG_3268.jpeg` | Original board photo (carrier, hub, S3) |
| `IMG_3274.jpg` | Servo plugs + servos (found leg parts fitted before centring) |
| `IMG_3284.jpg`, `servo-map.png` | Plug numbering from the capacitor end + robot map used for labelling |
| `sesame-angle-guide.png` | Upstream Sesame Rest/Stand angle reference |
| `scripts/` | Serial scripts: `bench_channel.py` (one channel with error checks), `apply_calibration.py` (re-apply calibration) |
| `BUILD-VERSIONS.md` | Every firmware build 1–16: base, manifest ID, change, reason |
| `clock-jumper.jpg`, `i2c-wiring.jpg`, `voltage-check.jpg` | Annotated board photos: clock jumper, I²C beep test, 3.3 V / 5 V probe points |
| `calibration-export-2026-10-30.json` | Latest exported calibration (build 14) |

## Timeline

### 1. Setup and step 28 — power and face ✅
- Installed pinned toolchain (`arduino-cli 1.5.1`, checksum-verified; `uv`; ESP32 core 3.3.11 + pinned libraries via `tools/sesame_s3.py setup`). Board: ESP32-S3 on `/dev/cu.usbmodem1101`.
- Flashed with battery physically unplugged (USB only), every time.
- **Living face (extra):** procedural OLED face — random blinks, glances, smoothly blended moods, talking mouth; commands `face alive`, `mood`, `look`, `say`. Boots by default; `bench` keeps the course diagnostic view.
- Face went black when a laptop joined the robot's Wi-Fi → **self-healing display** (re-asserts OLED setup every 2 s). Confirmed fixed.
- Hub VCC measured **3.3 V** (student, multimeter).
- **PWM clock:** student's meter has no Hz mode → added a `freq` command so the S3 measures the hub's CH15 test pulse on GPIO4 via one jumper (`hz-check-jumper-photo.jpg`).
  - Before: **55.61 Hz**, pulse 1347 µs → hub oscillator **27,787,334 Hz** (≈11 % fast), saved.
  - After: **49.85 Hz**, pulse **1498.0 µs** (target 1500). New value needed a reboot to take effect.
- Battery test (USB unplugged): face appears ✅.

### 2. Hub reliability and OE
- Hub sometimes absent after flash/warm reset (fixed by USB replug); also two dropouts after handling (loose sockets).
- Added `scan` (I²C) and a **hub auto-retry** while outputs are OFF. One attempted fix (9-clock bus recovery) broke I²C — removed; a bug in the first retry version was found and fixed.
- **OE:** the S3 SuperMini has no GPIO18 pin → moved OE to **GPIO7** in `manifest/robot.yaml` (regenerated header; saved calibration reset and oscillator re-entered). Student wired hub OE → S3 pin 7 + 4.7 kΩ pull-up to VCC; **measured 3.2 V** on OE (outputs off) ✅.

### 3. Steps 29–30 — servos and centring ✅
- R1 single-servo test first (student's choice) ✅.
- All 8 on USB: repeated hub faults on CH0 and one USB brown-out (a servo kept buzzing — before OE was wired). Root causes found step by step:
  - leg parts already fitted to two servos (extra load);
  - CH0 plug badly seated/oriented — CH0 with nothing plugged passed; re-seated plug passed;
  - original L1 servo **grinding** (likely stripped gears) → replaced with a spare.
- Full 10–170° sweep, one at a time: **all 8 channels pass**; every sweep ends at 90° (centred). Battery BOOT centring countdown also ran.

### 4. Steps 31–32 — legs ✅
- Upper and lower legs fitted at the Rest angle, power off, no shaft moved (student).

### 5. Step 33 — identification and calibration ⏳
- Channel map confirmed position by position (plug 1 at the big-capacitor end): CH0 L1 · CH1 L2 · CH2 L3 · CH3 L4 · CH4 R1 · CH5 R2 · CH6 R3 · CH7 R4 — saved to NVS.
- Direction (sign) / trim / limits **paused**: legs are not on a body yet, so "toward Stand" can't be judged. Servos being labelled with stickers (L1, L2 done).
- Next: choose and print a body (dinosaur idea), then finish step 33 (`verify`, `save`, `export`).

### 6. Oct 22–23 — mounted legs, real map, power fixes, dances
- Servos mounted on a temporary foam body. **My stickers had front/back swapped** → remapped course names to real positions: L1=CH1, L2=CH0, L3=CH3, L4=CH2, R1=CH5, R2=CH4, R3=CH7, R4=CH6.
- Direction tests held **in the hand were unreliable**; tests **on the body with a pause-and-hold** (move toward Stand, hold 4–10 s) were much easier to judge. Later found the foot mapping still had swaps (a single raw-channel test showed CH3 = back-left foot) → final per-channel mapping still open.
- **USB can't power multi-servo motion:** 8 servos starting at once faulted the hub; a 4-hip dance browned out the ESP32 (`BOD`) after ~6 s. Everything with more than one servo must run on **battery** via the Wi-Fi web console.
- **Firmware power fixes:** soft start (servos enabled one at a time, 150 ms apart), hub-setup retry at power-on (servo inrush), I²C glitch tolerance (3 bad reads before cut-off) and screen at 100 kHz while servos move → on USB, arm + Rest + 10 s hold now works; on battery the robot moves.
- **Lower legs point straight down at Rest** (official: straight out) → stock Stand/Dance/Wave look wrong; added custom `hipdance` and `tubadance` motions + "My Dance"/"Hip Dance" web buttons.
- Web console gotchas: tick **Keep heartbeat** before **Arm**, keep the phone on the page (leaving it sends `off`), `ERR arm run first` = watchdog disarmed.
- Every manifest change (new motion, OE pin) resets saved calibration → `scripts/apply_calibration.py` re-applies it.
- **Not flashed yet:** `rehub` command (retry hub setup without power-cycling) is in the source/diff, but the upload was interrupted; the robot runs the previous build.

### 7. Oct 29 — fresh start on the latest course firmware (builds 9–11)
- Calibration was off, so I restarted from the course's `481630e` (`arm bench`, `clock measure`, OE on GPIO7 adopted upstream) plus only my living face (build 9). Old work archived.
- Clock re-measured with `clock measure` (CH15 → GPIO4 jumper): 55.66 Hz → oscillator **27,815,198 Hz**, recheck 49.94 Hz.
- **Build 10:** the hub faulted at every power-on with 8 servos plugged in (servo inrush). Boot no longer latches a fault: the hub is retried every 1 s, plus `diag` (I²C scan, hub registers, OE) and `rehub`.
- **Build 11:** calibration rate 15 → 60 °/s. All 8 joints calibrated with the **default course map and signs** (no flips needed), verified and saved.
- Rest (all 90°) and Stand confirmed. Feet at full 0/180, all 4 touch the ground (my earlier 10° margin made L3/R4 hang).

### 8. Oct 29–30 — battery auto demo and power debugging (builds 12–14)
- **Build 12:** on battery, about 5 s after power-on it loops rest → stand → rest → stand → wave → dance with no phone or commands. BOOT stops it.
- First battery run: nothing worked and the face was blank. **Build 13** added an NVS event `log` (boot reset reasons, OFF reasons) to read back over USB, plus soft start.
- Log + `diag`: brown-out (`r9`), then **no I²C devices at all**. Root cause after step-by-step checks (continuity, `i2cswap`, pin test, OLED unplugged): the **hub VCC was not connected** (measured **1.4 V**, back-fed through SDA/SCL). Re-made the connection and everything came back. The chips were fine.
- Firmware bugs found on the way: the demo started on USB once the serial port closed (`Serial` = port open) → `HWCDC::isPlugged()`. The S3 panicked on a broken bus (IDF I²C ISR, decoded with addr2line) → I²C timeout 50 ms.
- On battery: `stand;boot r9` loops (8 servos loading at once). **Build 14:** demo rest/stand move one joint at a time; demo keeps its own heartbeat.

### 9. Oct 30 — full movement, walk and speed (builds 14–16)
- Checked guide step 33 (now "Rotate and fit the foot servos") and upstream: my Rest/Stand angles match; upstream had no firmware change, merged anyway.
- Wave/dance looked small because the stock motions were **clamped by my saved limits** → feet 0–180, hips widened to the firmware soft range (R1/L2 45–180, R2/L1 0–135).
- **Build 15:** walk added after dance (stock gait, 10 cycles = 20 steps). L4 rest back to 90°.
- **Build 16:** controller rate 60 → **240 °/s** (4× faster). Battery test: **full loop incl. walk runs fine**.
- OLED connector comes loose after handling; reseating fixes it.

### 10. Oct 31 — shared upstream
- PR henkaku-center/sim2real#15: general fixes (hub retry, diag/rehub, soft start, I²C glitch tolerance, 50 ms timeout, NVS log).
- PR henkaku-center/sim2real#16: this build log + my personal firmware patch under `reference/evidence/`.

### Next
- Body: Tachikoma (Ghost in the Shell) shell over the step-34 wide frame. Printed head/top, light or fabric abdomen, magnet/clip adapter plate, under ~60 g. Bottom-Cover-wide printed.
- Still to check: LM2596 output at hub V+ (5 V) with the battery on.

## What the tutorial could add (my suggestions)
1. SuperMini has **no GPIO18** → document the OE pin choice (I used GPIO7 + 4.7 kΩ pull-up).
2. A **Hz-meter-free clock check** (`freq` on GPIO4 via one jumper) — my hub was 11 % fast.
3. **USB power limits**: single-servo tests only; anything more on battery.
4. **Soft start / startup retry** in firmware to survive servo inrush.
5. Check plug **seating/orientation** first when one channel faults instantly (my CH0), and a grinding servo = stripped gears (replace).
6. Do direction checks **on the body**, with a hold, not hand-held.
7. Count plugs from the **big capacitor** end (CH0) with a labelled photo (`servo-map.png`).
8. A `diag` + NVS `log` in the reference firmware: battery runs are otherwise invisible (PR #15).
9. Measure **hub VCC at the hub**: my "dead hub + blank face" was VCC disconnected (1.4 V back-fed), while SDA/SCL/GND continuity was fine.
10. Note that saved limits silently clamp the stock motions (wave/dance/walk need wider feet/hips).

## Safety practice followed
USB and battery never connected together · flashing/serial only with the battery unplugged · plugs changed only with power off · one servo moved at a time, small bounded motions at 15 °/s · stop on any fault/buzz (student unplugged USB when needed).

## Open questions for the instructor
1. Loose connectors (hub sockets earlier, OLED now): best way to secure them — hot glue, re-solder, or locking headers?
2. (Resolved: OE on GPIO7 adopted upstream.)
3. Self-measured clock (jumper + `freq`) instead of a Hz meter — acceptable?
4. New oscillator value only took effect after reboot — known behaviour?
5. Battery brown-outs at Stand (`r9`): is the LM2596 (3 A) expected to carry 8 MG90S standing/walking, or is a bigger regulator recommended?
6. OK to build a Tachikoma cosmetic shell on the step-34 wide frame? Any weight limit you recommend for walk?
7. Would you merge PR #15 (general fixes) into the reference firmware?
