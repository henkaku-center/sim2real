# CAD starting assets

Downloaded and inspected **2026-09-23**. See
[CAD workflow recommendation](../../reference/CAD-CO-DESIGN.md) and
[component/CAD source research](../../reference/ELECTRONICS-CAD-SOURCES.md).

## Fetch / verify

From the repository root, using Python 3.9 or newer (standard library only):

```sh
python3 tools/fetch_cad.py
python3 tools/fetch_cad.py --verify-only
```

`sources.json` pins upstream commit, URL, byte count, Git blob hash and declared
repository license for every file. The downloader verifies those bytes before
saving. Existing modified files cause an error instead of being overwritten.
The 11-file download is **77,010,776 bytes** including licenses and the upstream
CAD README. `upstream/` is a gitignored, reproducible local cache. Keep original
downloads intact and make working designs elsewhere. Git LFS was unavailable on
the research machine; large downloaded assets are not committed as raw blobs.
Authored native CAD files should follow the repository's Git LFS policy.

## Sesame baseline

Upstream: `dorianborian/sesame-robot` at
`d106cbc8e158c982f408db421134f23273c5f51f`.

| Local path below `upstream/sesame/` | Purpose |
|---|---|
| `hardware/cad/Sesame-ESP32-v122.step` | Solid/assembly interchange starting point for FreeCAD |
| `hardware/cad/Sesame-ESP32-v122.f3z` | Original Fusion assembly archive, retained for source fidelity |
| `hardware/cad/README.md` | Upstream instructions and caveats |
| `LICENSE` | Upstream Apache-2.0 license |

**Initial file inspection, not CAD-kernel validation:**

- STEP start/end markers are present; 106 `PRODUCT` entries were found. These
  are product records, not a count of distinct physical parts or valid solids.
- Both filenames say **v122**; the STEP root label is **Sesame-ESP32 v123** and
  the Fusion archive's `DesignDescription.json` also reports version **123**.
  Preserve this discrepancy; use the pinned commit and file hashes for identity.
- Labels include SG90 Tower Pro servos, a 0.96-inch OLED, leg joints, Internal-Frame,
  Bottom-Cover, an S2 Mini board, KCD1-B2 rocker switch, an Ovonic 3S battery and
  a 14500 7.4 V/800 mAh battery. Labels alone do not establish which bodies are
  active/visible in the assembly or that any are identical to purchased hardware.
- The `.f3z` contains 21 members, including its manifest and design description;
  its ZIP CRC check passed. Some referenced components were imported from STEP
  upstream, so even the Fusion archive need not contain editable source sketches
  for every component.
- Frame/leg equivalence to the simulator's v117/v121 STLs remains unverified.
  Do not replace simulator geometry based on the assembly filename.

The file is an **older upstream robot reference**, not an as-built S3 electronics
assembly. Replace or verify the servo/electronics geometry against our component
record before designing fit-critical features.

## Adafruit comparison models

Upstream: `adafruit/Adafruit_CAD_Parts` at
`6f52ee4d48df0e7118d2d82f485cb572051a24fe`, MIT license, included as
`upstream/adafruit/LICENSE`.

Downloaded `.step` and native `.f3d` for each:

- `1143 Micro Servo - High Torque Metal Gear/1143 Micro Servo High Torque Metal Gear`
- `815 Servo Driver 16 Channel/815 Servo Driver 16 Channel`
- `3221 Toggle Switch/3221 Toggle Switch`

All three STEP files have start/end markers; all three native archives passed ZIP
CRC checks. The micro-servo STEP has separate body and spline product records.
They are comparison candidates, not certified substitutes for RCmall/other MG90S,
KKHMF PCA9685 or ALAMSCN toggle purchases. Matching mounting datums, shaft geometry,
connectors and assembled height is still required.

FreeCAD was not found on PATH or in standard application locations during this
session. No GUI import, topology validation, assembly placement or dimensional
comparison has yet been performed. File integrity checks do not establish fit.
