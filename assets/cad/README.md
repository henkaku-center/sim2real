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

The native `.FCStd` documents in `work/` are versioned with **Git LFS**;
`work/sesame-isometric.png` and `work/circuitry-preview.png` are versioned with regular Git. Automatic `.FCBak`
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
be run from FreeCAD's Macro menu. The native documents and the small previews
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

## Standalone circuitry co-design

**Active editing document: `work/Sesame-S3-circuitry.FCStd`.** Instructor requested
on 2026-09-23 that circuitry be validated independently before redesigning the robot
body to fit the larger board. The older layout document remains an upstream reference.

Run `tools/open_circuitry.FCMacro` from FreeCAD's Macro menu, or launch it with:

```sh
open -n -a /Applications/FreeCAD.app --args "$PWD/tools/open_circuitry.FCMacro"
```

The macro creates the document only if it is missing; subsequent runs open the
saved document and preserve edits. Repeated `open -n` launches create additional
FreeCAD instances: prefer the Macro menu during an interactive co-design session.
A live same-session command bridge is a remaining workflow improvement.
During co-design, **reuse the existing FreeCAD window** (instructor requirement).
Run macros from its Macro menu or `runpy.run_path(...)` in its Python Console;
do not repeatedly launch `open -n`. macOS Accessibility access was granted on
2026-09-23. Console automation must explicitly focus the console and paste text:
simulated typing through the active input method corrupted Python and triggered
viewport shortcuts when focus was wrong. Verify console output after each command.

Initial contents:

- Native parametric `Carrier`, 70 × 50 mm outline confirmed by the instructor;
  1.6 mm thickness is listing-derived and explicitly unmeasured. Edit Length,
  Width and Height in its Data tab. Origin is the lower corner; X is the 70 mm edge,
  Y the 50 mm edge, Z upward. No hole offsets or mounting-hole locations are invented.
- Hidden `UnplacedReferences`: 2D PCA9685 and OLED PCB outlines from purchased
  listings. Their staging positions are not assembly coordinates; no unverified
  module heights are modeled.
- `PendingMeasurements`: converter outline conflict, S3 dimensions/socket height,
  and header/wire/solder geometry. These metadata objects have no invented solids.
- `ValidationScope`: circuitry-first workflow and evidence status.

Checks on FreeCAD 1.1.3/macOS: document save/reopen, valid carrier shape, dimensions
and volume, reference dimensions, hidden staging group, and a temporary 70 → 72 →
70 mm length edit with successful recomputation. The verification did not save
over the native file. The GUI preview was inspected. This is the carrier-level
starting point, not a completed model of the hand-soldered assembly.

### Carrier hole grid (2026-09-23)

`tools/add_carrier_grid.FCMacro` upgrades the existing open circuitry document
(or opens the saved document if necessary); it does not regenerate an existing
grid. The native document now has **432 signal bores plus four mounting bores**.
The original `Carrier` box is retained as the hidden editable Boolean base.

- `HoleGrid`: 24 columns A–X, 18 rows 1–18, pitch 2.54 mm. The instructor read
  **PY-5cmx7cm 2.54mm 22402A-18** from the physical board. In top view, A1 is
  upper left, X18 lower right. Edge annotations label columns and rows; individual
  hidden cutters are named `Hole_A1` through `Hole_X18` for programmatic placement.
- Signal diameter is **1.0 mm**, based on the instructor's visual estimate of the
  physical board on 2026-09-23 (not a precision measurement). It replaces the
  initial 0.9 mm placeholder. The exact Amazon listing
  (`https://www.amazon.co.jp/dp/B071JYD6QP`) contradicts itself: bullets say 0.9 mm,
  description says 1.0 mm.
- Grid offsets are centered assumptions: X=5.79 mm, Y=3.41 mm from board edges
  to outer hole centers. Remove the offset expressions to enter measured offsets.
- `MountingHoleParameters`: four corner holes, physically confirmed by instructor.
  Initial creation script used photo estimates of diameter 2.5 mm and symmetric
  edge-to-center offsets 2.0 mm. The native document now records the instructor's
  2026-09-23 physical estimates: **diameter about 2 mm; centers 2 mm from the short
  (50 mm) edges**, hence `Diameter=2`, `InsetX=2`. The long-edge center distance
  (`InsetY`) is **less than 2 mm**, exact value unresolved. Its existing 2 mm
  geometry remains an explicitly inaccurate placeholder awaiting a numeric value.
  Four-corner symmetry is still assumed. No verified drawing for the exact board
  marking was found. Native values override the one-time creation script defaults.
- `reports/carrier-hole-coordinates.csv` records the signal centers at this revision;
  it is an exported snapshot, not live-linked to subsequent native edits.
- Pads, plated barrels and silkscreen geometry remain unmodeled. Labels are native
  annotations, not engraved material. Use `Circuitry.Placement` to position/rotate
  the assembly; individual carrier rotation is not supported by the grid expressions.

The upgrade checks that the result is one valid solid and that removed volume
equals all 436 cylindrical through-bores. Top-view labels and holes were inspected
in the GUI preview. Dimensions marked provisional remain pending physical validation.
