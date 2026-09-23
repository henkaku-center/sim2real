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
The 22-file download is **79,565,300 bytes** including licenses, the upstream
CAD README and 11 comparison STLs. `upstream/` is a gitignored, reproducible local cache. Keep original
downloads intact and make working designs elsewhere.

The five native `.FCStd` documents in `work/` are versioned with **Git LFS**;
`work/sesame-isometric.png` is versioned with regular Git. Automatic `.FCBak`
backups, full local audit output and runtime markers remain ignored. After cloning:

```sh
git lfs install
git lfs pull --include="assets/cad/work/*.FCStd" --exclude=""
```

This retrieves the committed CAD documents without requiring a fresh STEP import.
Save and commit subsequent working-document edits normally; the `.gitattributes`
rule stores their binary contents in LFS. Original STEP/Fusion downloads remain
available through the pinned downloader. Third-party notices for the imported
documents are retained in `licenses/sesame-Apache-2.0.txt` and `licenses/adafruit-MIT.txt`.

Git LFS 3.8.0 was installed locally from the official macOS Intel release on
2026-09-23, with its release-asset SHA-256 verified, and Git LFS hooks initialized.

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

## FreeCAD import and inspection

FreeCAD **1.1.3**, revision `145529fe741292ff0b3977a01195bf0247425794`, was installed
by the instructor and exercised on macOS on 2026-09-23. From the repository root:

```sh
/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd tools/inspect_cad.py
open -n -a /Applications/FreeCAD.app --args "$PWD/tools/open_cad.FCMacro"
```

The importer creates missing native documents in `work/` on first run, including
`Sesame-S3-layout-start.FCStd`. Later runs audit existing reference documents and
preserve the working document. The viewer macro opens the working document,
enables model visibility, hides datum axes/planes and captures a viewport image.
It does not save over an existing GUI document; save interactively to retain view
changes. Avoid repeatedly launching new application instances; the macro can also
be run from FreeCAD's Macro menu. The five native documents and the small preview
are committed; they are an initial reference workspace, not a fitted S3 assembly.

### Results

| Source | Part features | Invalid leaf shapes | Notes |
|---|---:|---:|---|
| Sesame assembly | 492 | 1 | Old KCD1-B2 rocker; its parent and assembly also report invalid |
| Adafruit micro-servo | 6 | 0 | Candidate model only |
| Adafruit toggle | 10 | 3 | Three solids fail validity; aggregate also reports invalid |
| Adafruit PCA9685 | 100 | 0 | Candidate model only |

The full document counts additionally include containers and generated coordinate
systems. Do not sum nested object volumes. The report distinguishes object-local
bounds from placements; it does not claim each bounding box is an assembly-global
envelope. FreeCAD sanitized malformed control characters in some imported servo
labels while saving; original STEP files remain intact.

Frame, bottom cover and all eight leg-part shapes pass `isValid()`. STEP-versus-STL
volume differences are below 0.09% (frame −0.085%, bottom cover −0.056%, legs
+0.007% to +0.014%). This supports similarity, not geometric identity or fit:
surface registration and mounting-datum comparisons are still needed.

The simulator STL checkout contained Git LFS pointers. Matching upstream files
were downloaded into the CAD cache; all 11 SHA-256 hashes match the simulator's
pointer identities. Empty meshes and hash mismatches are rejected by the inspector.

Evidence: [compact audit](reports/freecad-import.json); complete hierarchy in local
`work/freecad-import-full.json`; GUI viewport in local `work/sesame-isometric.png`.
The assembly was visibly rendered in FreeCAD. No invalid geometry was silently
repaired, and no physical fit or joint calibration was inferred from these checks.
