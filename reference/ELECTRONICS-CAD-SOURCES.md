# Electronics CAD sources and S3 assembly preparation

Research date: **2026-09-23**. This is a source-selection and measurement record,
not a validated assembly model. Component geometry and the eventual assembly belong
in `sim2real`; purchase quantities/costs remain canonical in APS
`docs/ii/inventory/data.json`. Link purchases by ASIN, not just generic component name.

## S3, carrier connectors and underside wiring — 2026-09-24

- Auxiliary strips are **X14–X17** and instructor-corrected **M12–M15**.
  M12/M13/M14/M15 serve OLED **GND/black, VCC/red, SCL/green, SDA/blue**.
  X14/X15 are the two switch V+ connections; X16/X17 are battery V+/GND.
  These signal assignments are explicit instructor evidence and native CAD properties.
- Four insulated jumpers: red L4–L13 and B3–B9, blue K5–K18, green J6–J14.
  Native sketches/sweeps separate conductor and insulation; gauges/bends remain illustrative.
- Instructor supplied `ESP32-S3_Zero.step` and `ESP32-S3-WROOM-1.STEP`.
  Zero was selected for geometry: 31 valid solid component objects, an 18 × 23.5 mm
  board, nine holes per side at 2.54 mm pitch and 15.24 mm row separation.
  It fits **A11–I11 / A17–I17** without scaling. Original files remain local unchanged.
  USB faces outward toward A as a placement inference. The source's diagonal IC,
  two buttons and red antenna agree with the instructor's new component photo.
- WROOM STEP contains no `COLOUR_RGB` records; its default FreeCAD display is not
  a transferable material palette. The new photo supplies the finish evidence:
  black PCB, gold pads, silver USB shell, red antenna. Source component boundaries
  and face assignments are retained, with PCB/pad finish adjusted accordingly.
- S3 headers are explicitly **long, centred and untrimmed**, retained for top-side
  expansion. Use the purchased PENGLIN nominal 15 mm / 6.25 mm each exposed side /
  2.5 mm spacer reference; installed brand remains unconfirmed. No donor spacer is
  added to the S3. Current model gives 6.25 mm socket engagement and 4.63 mm above
  the source board's top pad surface. Pin width is provisionally 0.6 mm square to
  fit the source 0.9 mm bores. Female height 8.5 mm and cavity depth 7 mm remain
  unmeasured. Modeled PCB underside is Z=12.6 mm.
- The S3 and its male pins/spacers/top solder move together; female sockets and
  their tails/bottom solder stay on the carrier. A temporary 10 mm lift test was
  reverted without saving. Exact overlap checks include imported hub/converter
  leaves; soldered wire/tail intersections are recorded as intended joints.
- Sixteen underside bare-wire route segments are modeled in native primitives.
  Wire diameter 0.5 mm, center Z=-0.8 mm and solder shapes are illustrative.
  The instructor's top-view diagram resolves the three obscured photo junctions:
  X15–X16 battery-positive bridge, M15–M18 SDA link and B10–B11 ground bridge.
  C11 remains separate on OLED VCC. All thin-line routes and four thick jumpers
  are accounted for; segment boundaries do not establish actual cut lengths.
  Model topology is checked against eight distinct diagram nets; physical
  continuity has not been tested. Geometry is not a measurement of solder shape.
- Construction records: `assets/cad/instructions/s3-installation.json`,
  `carrier-connections.json`, and `underside-wiring.json`; saved-geometry results
  are in `assets/cad/reports/s3-installation-check.json` and
  `underside-wiring-check.json`. Native comparison and source uploads remain
  local-only pending source redistribution permission; snapshot/scripts/records
  are committed. Native identities survive the M-strip address correction.

## Recommended sources

1. **KiCad official 3D libraries** for individual connectors, headers, switches,
   and board-level packages. Prefer their STEP solids when constructing an assembly.
   The [library license](https://www.kicad.org/libraries/license/) is CC-BY-SA-4.0
   with an electronic-design exception; redistributed library collections still
   require the library license and attribution. Check the exact model's notices.
   [Packages](https://gitlab.com/kicad/libraries/kicad-packages3D).
   Important maintenance finding: the old
   [packages3D generator](https://gitlab.com/kicad/libraries/kicad-packages3D-generator)
   is archived. Its recommended footprint-generator URL now redirects to
   [KiCad Library Tools](https://gitlab.com/kicad/libraries/kicad-library-tools),
   which includes 3D generators. Use that current upstream when evaluating editable
   generation sources; generated-library and generator-code licenses are distinct.
2. **[Adafruit CAD Parts](https://github.com/adafruit/Adafruit_CAD_Parts)** for
   complete breakout-board and accessory models. Repository
   [LICENSE](https://github.com/adafruit/Adafruit_CAD_Parts/blob/main/LICENSE) is MIT;
   retain its notice when copying models. STEP, Fusion 360 and STL are available.
   Tree inspected at `6f52ee4d48df0e7118d2d82f485cb572051a24fe` includes:
   - `815 Servo Driver 16 Channel/815 Servo Driver 16 Channel.step`
   - `1143 Micro Servo - High Torque Metal Gear/1143 Micro Servo High Torque Metal Gear.step`
   - `3221 Toggle Switch/3221 Toggle Switch.step`
   These are **reference/adaptation candidates**, not confirmed matches for the
   KKHMF PCA9685, mixed MG90S purchases, or ALAMSCN switch. Compare outlines,
   mounting holes, shaft geometry and connectors before adoption.
3. **[FreeCAD community parts library](https://github.com/FreeCAD/FreeCAD-library)**
   for editable native models and STEP. Its README specifies CC-BY-3.0 with
   attribution to each model's author. Tree inspected at
   `be5e71491051cef75da46831b6fd77c6313cb497` includes
   `Electrical Parts/Servos/SG-90/` with separate horns and body, plus
   `Electronics Parts/Switch/Mini toggle switch 1P2T/`.
   Neither SG90 nor a three-terminal switch establishes a match to our purchases.
   Useful as editable references; record author and individual file provenance.
4. **[NopSCADlib](https://github.com/nophead/NopSCADlib)** for scripted mechanical
   assemblies, PCB/header primitives and cable-related geometry. README states
   GPLv3; inspected source headers specify GPLv3-or-later, with some separately
   licensed assets. Tree inspected at `c9baa0ed0faa23e849141c3d8c6728545d6af910`.
   `vitamins/pcbs.scad` includes MP1584EN and other buck converters, but an exact
   LM2596 purchase match was not established. `servo_motors.scad` describes
   industrial Lichuan servos, not MG90S. Do not mistake keyword hits for matching
   models. Treat this primarily as a parametric toolkit candidate.
5. **[SnapMagic/SnapEDA](https://www.snapeda.com/about/FAQ)** as a supplementary
   part-number search. Its FAQ includes 3D models under CC-BY-SA-4.0 with a design
   exception. Verify each downloaded asset's origin and terms; a STEP download
   does not necessarily include editable construction history. Prefer identified
   manufacturer part numbers over searches for generic clone-board names.

No verified, openly licensed model for the exact purchased **S3 SuperMini** was
established. Search surfaced a Cults3D STP/STL listing, but fetching it returned
403, preventing license/model verification. C3 SuperMini, S3 Zero and XIAO results
are not substitutes for this board. Similarly, public availability on a model
sharing site alone does not establish suitability for redistribution.

## Assembly-specific choices and evidence

Instructor confirmations on 2026-09-23:

| Part | Inventory ASIN | Build status |
|---|---|---|
| Carrier | B071JYD6QP | Installed 70 × 50 mm board; mistakenly purchased 60 × 80 mm B0CX1RGYFG excluded |
| Battery | B0F3JB59B6 | Confirmed installed purchase |
| LM2596 converter | B07NVSVW1N | Confirmed installed purchase |
| Toggle | B0G9M71BBS | Confirmed installed purchase |
| MG90S | B0B8V31SD4, B0FMXXYD3Y, B0GS1HT519 | Mixed purchased variants; shared position-servo family is a design requirement, dimensional interchangeability not verified |
| MG90D | B0FH1KZ64Y | Mistaken continuous-rotation purchase; excluded from leg build and compatibility target |

Other inventory-linked assembly components: S3 B0H9LLXWNH, PCA9685 B078YRJ8D7,
OLED B08CTZVVLS. Ownership of other inventory items does not establish installation.

The instructor-supplied [Builder Studio album](https://photos.app.goo.gl/ekx75uje2vnPG2wUA)
was reviewed as 25 images in downloaded album order. It supports an elevated
PCA9685 above the taped converter, modified header spacers/pins, a socketed S3
with USB facing the carrier edge, underside soldering, and external battery,
switch and OLED wiring. These are **photo observations**, not caliper measurements.
Exact wire gauges, header purchase matches and the OLED harness origin remain
unresolved from the photographs.

## Recovered dimensions: published, not measured

Exact Amazon Japan ASIN pages and their product images were inspected on
2026-09-23. Use `https://www.amazon.co.jp/dp/<ASIN>` to locate each source.

| Part | Published data | Remaining ambiguity |
|---|---|---|
| B071JYD6QP carrier | Title 50 × 70 mm; 1.6 mm thick; 2.54 mm pitch; 0.9 mm holes; 18 × 24 grid | Bullet text also says 60 × 80 mm. Instructor and album support 50 × 70 mm; edge offsets/mount holes still need measurement |
| B078YRJ8D7 PCA9685 | 61 × 25 mm | Thickness, hole coordinates, tallest components and installed socket height unknown |
| B08CTZVVLS OLED | 25.4 × 26.1 mm PCB; dimension image also marks 22 mm horizontal mounting span and 11 mm display height | Hole diameters/vertical spacing, glass offset, thickness and actual visible aperture need confirmation |
| B0F3JB59B6 battery | 51 × 28 × 14 mm; 47 g per pack; 7.4 V, 1000 mAh, 2S; listing calls connector JST | Connector series/pitch, cable length and installed envelope unknown |
| B07NVSVW1N converter | Product images conflict: 42 × 21 mm versus 45 × 20 mm | Measure the delivered PCB; do not silently select a generic LM2596 model |
| B0G9M71BBS toggle | Image labels 13 × 8 mm body footprint, 33 mm overall, 10 mm lever | Thread diameter, panel-hole size, nut envelope, usable panel thickness and lever sweep unknown |

Dimension-image identifiers: converter `61FCIdD5tlL` and `519Lg2LkglL`;
switch `61rIy15oUuL`; OLED `61KIviiTKFL` (Amazon image CDN).
No electrical load ratings are validated by these geometry observations.

## Installed converter observations (2026-09-24)

Instructor-reported physical observations for B07NVSVW1N:

- One blue screw-adjustable potentiometer. Initially reported as the tallest
  component; instructor subsequently clarified that the capacitors are very
  close in height. Subsequent measurement resolves the ordering: capacitor top
  **11.5 mm above converter PCB underside**, with the potentiometer tallest due
  to a gold adjustment screw protruding approximately **1 mm** above its blue body.
- Approximate height **13 mm**, from the underside of the converter's own PCB
  to the top of that potentiometer, including that PCB's thickness. This is a
  physical estimate, not a precision measurement. It excludes the perfboard,
  any gap beneath the converter PCB, and underside pin/solder protrusions.
- Perfboard connections: OUT− at **V1**, OUT+ at **O1**, IN− at **V17**,
  IN+ at **O17**. At the carrier's 2.54 mm pitch these imply a connection
  rectangle of **17.78 × 40.64 mm**; converter hole alignment still needs checking.
- Separation between the perfboard top surface and converter PCB underside is
  approximately **0.5 mm**, reported by the instructor. Three layers of electrical
  tape insulate the converter underside. Treat the 0.5 mm as the total installed
  separation including the tape, not an additional air gap; individual tape-layer
  thickness and coverage have not been measured.
- Derived approximate stack: converter underside **2.1 mm** above the perfboard
  underside (1.6 mm perfboard + 0.5 mm separation); potentiometer top **13.5 mm**
  above the perfboard top, or **15.1 mm** above its underside. These are nominal
  sums of physical estimates, not precision measurements or service clearances;
  the subsequent capacitor measurement supersedes the earlier height uncertainty.

Use these observations to assess candidate CAD geometry; an agreement in pin
spacing alone does not establish an exact purchased-variant match.

### YAAJ converter comparison (2026-09-24)

Downloaded the bare-module STEP from `yet-another-average-joe/KiCad-Chinese_Modules`
at revision `82e7b5806c70ca289d5c9fb9ed6e5a2209b806d2`, path
`DCDC_StepDown_LM2596/Packages3D/YAAJ_DCDC_StepDown_LM2596.zip`.
Archive SHA-256: `d8a7836b10bd3a2ca68ff85d6a6060c038f0c991fc9c01d57ccc444d6c3428ee`.
The root README lists the module but supplies no license; no license file was
located in the inspected repository tree. Keep imported geometry in the ignored
local cache while comparing, rather than redistributing it in the tracked CAD.

Direct FreeCAD 1.1.3 geometry audit (model dimensions, not physical measurements):

- Valid shape, 80 solids; PCB outline **43.6 × 21.3 mm**, nominal PCB thickness
  **1.6 mm** (pad surfaces extend 0.001 mm beyond each face).
- Four terminal centers form **40.64 × 17.78 mm**. A −90° Z rotation with source
  IN+ at O17 aligns all four terminals to the user-specified physical addresses;
  maximum computed XY error is below **0.0000001 mm**.
- Original adjustment-screw top: **13.036 mm** above nominal PCB underside;
  original capacitor tops: **14.3 mm**. These are the downloaded reference values,
  superseded in the local comparison by the measured-height adaptations below.
- Some component leads reach **0.85 mm below the converter PCB**. With 0.5 mm
  separation, their unmodified reference geometry reaches into the perfboard
  height range by 0.35 mm. Installed trimming/bending/solder is not yet modeled.

`tools/preview_converter_candidate.py` opens a separate comparison tab in the
existing GUI, aligned over a copied perforated-board reference, with editable
`Installation.InsulatedSeparation` and a provisional full-outline tape envelope.
It verifies the archive checksum and four terminal positions, and saves the
comparison, preview and alignment report under `assets/cad/upstream/lm2596-yaaj/`.
The comparison includes geometry snapshots of all **864 rings, 64 capsules and
42 outlined labels**, with silver capsules matching rings and light-green lettering.
Native circuitry remains the authoritative saved build; imported reference
geometry is kept in the local comparison document. The instructor gave positive
visual feedback, not complete dimensional validation; underside details remain open.
Save/reopen checks passed for shape validity and a temporary 0.5 → 0.7 mm gap
edit (not saved), including both module elevation and insulation thickness.
FreeCAD emitted `Invalid element name string id` on reopening the copied-board
comparison; no invalid object states or invalid shapes were found. This warning
has not been diagnosed and is not evidence of loss-free feature-history copying.

`tools/refine_converter_candidate.py` applies the instructor's subsequent height
measurements in that comparison tab while retaining hidden imported originals:

- Each capacitor is shortened by removing a **2.8 mm mid-body band** and joining
  the remaining halves. Diameter, top, base and lead geometry are retained;
  resulting top is **11.5 mm** above converter PCB underside. Other capacitor
  dimensions remain unverified reference values.
- Gold screw protrusion is reduced to **1 mm**, retaining its slotted top. The blue
  body remains the reference height: approximately **11.516 mm** above converter
  PCB underside. Thus screw top is approximately **12.516 mm**, consistent with
  the earlier rough 13 mm observation but not an independently measured blue-body
  height. The resulting installed screw top is approximately **14.616 mm** above
  the perfboard underside; retain uncertainty for enclosure fitting.
- All adjustment-screw faces use a gold-colored material, per instructor request.
- Adaptations are static STEP-derived shapes with evidence properties, not recovered
  original parametric feature history. Tape separation remains expression-driven.
The final comparison passed save/reopen geometry checks, including both 11.5 mm
capacitor tops, 1 mm screw protrusion, 864 rings, 64 capsules and lettering geometry.
The earlier element-name warning did not recur in that final headless check.

### Installed converter pins and underside solder (2026-09-24)

Instructor-described construction: four square male header pins were inserted
short end first from beneath the converter, with the plastic against its underside,
then soldered on top. The plastic was removed with pliers. Long ends were inserted
through the carrier, clipped flush beneath it, and the holes filled with solder.
There are **no retained plastic spacers** on these four pins.

Rechecked the downloaded album sequence: photo 03 shows spacer removal and bare
pins; photo 04 shows the central tape patch leaving terminal pads exposed; photo 05
shows top-side solder; photos 06–07 show underside clipping and the four finished
solder mounds. These support the construction but do not supply precise dimensions.
The instructor estimates underside solder across the carrier is **typically 1 mm**
high. This is **not a measured maximum** or an individual measurement of each joint.

`tools/add_converter_pins.py` adds four native editable square pins at O17, V17,
O1 and V1, plus converter-hole fill, top solder, carrier-hole fill and underside
solder for each. Their lower metal ends terminate at the carrier underside. The
underside solder extends **1 mm below that plane**, applying the typical estimate
uniformly. There is no modeled retained plastic. Further underside joints remain
to be modeled as the other components are added.

Native `Installation` properties expose provisional pin width **0.64 mm**, top
projection **0.3 mm**, top solder radius/height **0.9/0.4 mm**, and bottom solder
radius **0.95 mm**. These dimensions and the conical solder profiles are illustrative,
not measured. Thickness values remain the carrier's 1.6 mm nominal value and the
candidate converter's 1.6 mm. Tape coverage is now a central **37.6 × 20.3 mm**
rectangular approximation with exposed corner pads, based qualitatively on photo 04;
the three tape layers retain the instructor's combined approximate 0.5 mm separation.

Save/reopen checks verified all four pin centers against the authoritative carrier
addresses, flush lower pin ends, 1 mm solder projection, valid solder/pin shapes,
and no pin intersection with either board substrate or the tape. A temporary gap
change from 0.5 to 0.7 mm preserved the flush ends through expressions; that test
change was not saved. The working GUI comparison is saved with the 0.5 mm gap.

## Detachable servo hub — research and assembly evidence (2026-09-24)

Installed purchase: PCA9685 hub **B078YRJ8D7**, listing outline **61 × 25 mm**.
Instructor confirmed that the two six-pin mounting/interconnect strips use
**symmetric male headers with long metal ends on both sides**, not ordinary
short-tail headers. Each strip receives an additional plastic spacer harvested
from a donor header, alongside its original spacer. Dimensions of the symmetric
pins, individual spacers and female sockets are not yet measured.

Photos 08–10 show donor-spacer removal and the doubled spacer stack. Photo 11
shows the two modified male strips below the hub and solder on its top face.
Photos 12–13 show the female sockets being fitted; photo 15 shows the completed
stack above the converter. The instructor confirms that the **female sockets are
soldered to the carrier** and the hub remains **detachable**, elevated to clear
the converter's gold potentiometer screw. The photos retain the 16 three-pin
servo-output connectors. The desolder/replacement instruction is interpreted as
applying to the two end interconnect headers, not those output connectors.

Conditional preparation: if those end headers arrive already soldered, remove
them before installing the symmetric double-ended header arrangement. Their
actual as-delivered state is not established here. Preserve both possible starting
states in future instruction authoring.

Photo 14 is annotated **A → X** and **3 → 8**, suggesting six-pin sockets at
**A3–A8 and X3–X8**. This began as a photo interpretation; the instructor subsequently
confirmed those positions and the approximate height, as recorded below.
The actual minimum clearance from the gold screw remains unmeasured.
Clearance checks must include hub underside solder/tails, not only the PCB plane.

### CAD search results

- Instructor-proposed candidate: `https://grabcad.com/library/pca9685-8`.
  Direct page and `/files` retrieval expose only the JavaScript site shell;
  the browser tool reports no connected desktop browser, and direct retrieval of
  the page's application script returned HTTP 403. Search confirms the listing
  but does not expose usable geometry. Candidate appearance, dimensions, header
  spacing, author and license remain unverified. Obtain the downloadable STEP or
  native file before judging its suitability; no match is claimed from its name.

- Official Adafruit downloads page:
  `https://learn.adafruit.com/16-channel-pwm-servo-driver/downloads`
  links the manufacturer's STEP/Fusion assets in `adafruit/Adafruit_CAD_Parts`,
  directory `815 Servo Driver 16 Channel`. Existing pinned revision is
  `6f52ee4d48df0e7118d2d82f485cb572051a24fe` (MIT; provenance already in
  `assets/cad/sources.json`). Rechecked native `assets/cad/work/Adafruit-815.FCStd`
  headlessly: 100 shape objects; its valid single-solid `Board` object
  (`Part__Feature`) measures **62.23 × 25.4 × 1.57 mm**. This is a usable reference,
  not a verified model of B078YRJ8D7. No model was scaled or substituted.
- A search lead identifies Nelson Stoldt's *PCA9685 16 Channel 12 Bit Servo Driver
  (Generic & Adafruit)*, reportedly with FreeCAD and STEP variants. The expected
  primary GrabCAD page at
  `https://grabcad.com/library/pca9685-16-channel-12-bit-servo-driver-generic-adafruit-1`
  returned only the generic site shell through the fetch tool. File dimensions,
  source contents and license are **not verified**; no file adopted. Aggregator
  listings are discovery leads, not engineering evidence.
- Another generic model search lead is Printables model 341031, *PCA9685 16 Channel
  12 Bit Servo Driver*; direct retrieval returned HTTP 403. Not inspected/adopted.

The construction record is `assets/cad/instructions/servo-hub-installation.json`.
The subsequent placement confirmation and derived hub are described below;
detailed detachable header/socket geometry remains outstanding.

### Uploaded candidate inspection

Instructor supplied `pca9685.step` and `PCA9685.IGS` after proposing GrabCAD
`pca9685-8`. Both were imported in the existing GUI into separate local comparison
tabs, without changing the installed converter/carrier. Provenance, file SHA-256
values and measurements are in
`assets/cad/reports/servo-hub-uploaded-candidates.json`. Uploaded files and native
comparison saves remain in ignored `assets/cad/upstream/pca9685-uploaded/`.
`tools/preview_servo_hub_candidates.py` opens those cached inputs for comparison.

**STEP selected as the candidate by the instructor:** 321 valid solids, named
components, retained servo outputs and already-bare six-hole end rows. Its file
header identifies a 2023-05-13 FreeCAD export, not original parametric feature
history. The large `Platine` solid includes major components as well as the PCB;
do not treat its entire bounding box as PCB dimensions.

Direct face/edge inspection gives a **60 × 25 × 1.6 mm PCB**, with terminal-row
centers at **X=±28.73 mm** and six holes at **2.54 mm pitch** along each row.
Thus its row span is **57.46 mm**, **0.96 mm short** of the **58.42 mm** between
carrier columns A and X. This also differs from the purchase listing's 61 mm
board length. The carrier addresses were unconfirmed at that inspection stage;
the instructor subsequently confirmed them, as recorded below. No scaling,
hole relocation, or pin bending was applied to the uploaded baseline.
Recorded Z bounds extend approximately 1.463 mm below nominal PCB underside;
actual underside protrusions and installed clearance still need checking.

**IGES not selected:** SolidWorks 2015 export, 1,546 individual faces with no
solids or sewn shells on import. Its geometry validity result does not establish
a closed, watertight assembly. No repair was attempted. It is a distinct model,
not another encoding of the uploaded STEP.

### Confirmed hub placement update

Instructor confirmed female sockets at **A3–A8 and X3–X8**, and estimates
**14 mm from the carrier top to the hub PCB underside**, just clearing the gold
adjustment screw. With the nominal 1.6 mm carrier, the hub underside datum is
therefore **Z=15.6 mm** in carrier-local coordinates. This is an approximate
installed height, not a measured minimum clearance. Earlier photo-only placement
uncertainty is superseded; the uploaded STEP's 57.46 mm row span still conflicts
with the confirmed 58.42 mm socket span. Resolve that model discrepancy explicitly
before treating the hub as dimensionally fitted. Female socket body height,
male-pin engagement and individual spacer thicknesses remain unmeasured.

The instructor also reports that the **actual pins fit nicely**, with no noticed
alignment issue. That physical evidence takes precedence over the uploaded CAD's
narrower spacing; the discrepancy is not a diagnosed fault in the real build.

`tools/fit_servo_hub_reference.py` creates a separate derived reference, preserving
the uploaded source. It moves each end strip **0.48 mm outward** and bridges the
PCB substrate, bringing the row span to **58.42 mm** without scaling the central
components or the **2.54 mm** pitch. The resulting **60.96 × 25 mm** outline is an
inferred model correction, not a measurement. End mounting holes move with the
strips and remain unverified. A 0.035 mm surface-metal sliver crosses one split;
no projecting pins or component bodies cross the split planes. Decorative source
legends retain their original placements. The corrected body is a static derived
solid, not recovered native design history.

`tools/place_servo_hub_candidate.py` places that derived reference in the existing
local circuitry comparison at **Z=15.6 mm**, with all twelve terminal centers
aligned to **A3–A8/X3–X8**. The model's gold-screw-to-hub distance is approximately
**0.984 mm**, consistent with slight clearance but not an independent physical
clearance measurement. At this placement milestone, symmetric male headers,
two-spacer stacks, female sockets and hub solder were still pending; their
subsequent provisional geometry is recorded below.
Saved-document checks verified a valid corrected body, all twelve actual terminal
bores aligned to the carrier, the model screw clearance, and response to a temporary
14 → 14.5 mm height edit (not saved). The uploaded STEP's SHA-256 is unchanged.
The refreshed instruction snapshot includes 37 native bindings and the hub parameters.

### Detachable header geometry — 2026-09-24

`tools/add_servo_hub_headers.py` adds two six-position female sockets and two
hub-mounted symmetric male strips at A3–A8/X3–X8. The existing GUI document is
preserved; native Part primitives, cuts and expressions expose the dimensions in
`HubInstallation`. `HubMaleHeaders` belongs to the removable hub, while
`HubFemaleSockets` stays on the carrier. Original and donor plastic spacers are
separate native objects for future assembly instructions.

**Provisional visualization dimensions, not purchased-part specifications:**
8.5 mm female body, two 2.5 mm spacers, 0.64 mm square pins, and 6 mm equal exposed
pin lengths beyond the original spacer (14.5 mm total metal length). At the
confirmed approximate 14 mm separation, this leaves a 0.5 mm socket-to-donor gap
and 3 mm engagement. The untrimmed upper pins extend 4.4 mm above the hub PCB;
actual upper trimming remains unknown. The female cavities are 5 mm deep with
simplified hollow metal sleeves, not reconstructed spring contacts. Socket tails
extend a provisional 0.8 mm below the carrier. Twelve hub-top and twelve
carrier-underside solder fillets are illustrative; internal bore solder is omitted.

The saved-document check `tools/check_servo_hub_headers.py` verified all 66 finished
features, twelve terminal alignments, symmetry about the original spacers, 3 mm
engagement, and no male-pin volume overlap with the housing, spacers, sleeves or
tails. A temporary 10 mm hub lift clears the sockets and leaves their geometry
fixed; test edits are not saved. Results are in
`assets/cad/reports/servo-hub-headers-check.json`.
The instruction snapshot now contains 105 native bindings. A local native milestone
copy is retained as `LM2596-comparison-headers-2026-09-24.FCStd` alongside the active
comparison; both remain local-only with the imported candidate geometry.

### Flush seating correction and connector dimensions

The instructor subsequently confirmed that the male spacer stack touches the
female socket housing in the real assembly. `tools/seat_servo_hub_headers.py`
lowers the existing hub by 0.5 mm while preserving its native objects. The modeled
carrier-top-to-hub-underside separation is now **13.5 mm**, derived from the
provisional 8.5 + 2.5 + 2.5 mm plastic stack, consistent with the earlier approximate
14 mm physical estimate. Engagement becomes **3.5 mm**, the plastic mating gap
becomes zero, and the calculated screw clearance is approximately **0.484 mm**.
These remain model-derived values, not new physical measurements.

Manufacturer comparison (not identification of the purchased generic headers):
Samtec TSW/HTSW uses 2.54 mm pitch and approximately 2.54 mm insulator thickness
(for example its -07 length stack is 10.92 - 2.54 - 5.84 = 2.54 mm).
Samtec SSW/SSQ straight sockets have an **8.51 mm housing height**, but specify
**3.68–6.35 mm insertion depth** separately. Housing height is not usable insertion
depth. These drawings make the chosen 2.5 mm spacer and 8.5 mm socket exterior
plausible; they do not validate our assumed internal cavity or engagement for the
actual parts. In particular the modeled 3.5 mm engagement is not claimed to meet
the SSW specification, and the model is not being relabeled as a Samtec connector.

Primary references checked: Samtec `catalog_english/tsw_th.pdf` and
`catalog_english/ssw_th.pdf` on `suddendocs.samtec.com`.
Exact spacer thickness, socket cavity/contact geometry and male length remain
provisional pending identification or measurement of the installed parts.

### Purchased long headers, spacer orientation and underside solder correction

Purchase confirmations dated **2026-09-14** identify the actual symmetric long-pin
purchase as **PENGLIN B0FJ5NR96F**, not the earlier ordinary KKHMF strip. Both the
order title and the supplier's current listing specify **15 mm total metal length**
and **6.25 mm exposed on each side**, implying a **2.5 mm original spacer**.
The same day's **Youmile B0C13N6T48** order contains 30 male and 30 female strips
at 2.54 mm pitch. Its female socket housing height and internal cavity depth could
not be confirmed from the retrieved listing/size images, and its identity as the
installed female socket still needs instructor confirmation. These two purchases
were absent from the checked APS inventory rows; purchase evidence is recorded
here without duplicating private order/account details.

The instructor confirms the hub-top pins are **untrimmed** and protrude **about
2 mm above the PCB**. Reinspection of photos 10–12 indicates the donor spacer is
on the **PCB side**, leaving the original spacer on the **socket side**. The initial
model had these reversed. Correcting orientation and using the purchased 15 mm
pins gives **6.25 - 2.5 - 1.6 = 2.15 mm** upper protrusion, consistent with the
physical estimate without inventing a cutting step. This also changes modeled
socket engagement to **6.25 mm**; the simplified internal socket envelope is now
**7 mm deep**, explicitly provisional rather than a supplier-confirmed dimension.
The earlier 3/3.5 mm engagement and 5 mm cavity were initial modeling assumptions.

`tools/refine_purchased_hub_headers.py` updates the existing native objects and
reverses the twelve carrier-underside solder cones: **0.9 mm radius against the
board, tapering to 0.48 mm away from it**. Upper solder retains its correct direction.
Flush seating remains at 13.5 mm board separation with approximately 0.484 mm
modeled screw clearance. The photo-inferred donor placement, donor thickness and
socket internals remain distinguished from purchased nominal pin dimensions.

Sources and confidence are recorded in
`assets/cad/reports/purchased-hub-headers.json`, including supplier URLs. Exact
part-match evidence for the socket is still insufficient to claim its depth is
confirmed.

## Model construction plan

- Store a reusable family definition and per-ASIN overrides for position servos:
  body, mounting tabs/holes, shaft datum, spline/horn, lead exit, mass, torque,
  speed, operating voltage and calibrated motion limits. Unknown values stay
  unknown; an advertised overall height is not automatically a body height.
- Start with measured board outlines and attachment datums; reuse verified
  connector models. Represent solder, raised sockets, insulation and bent/trimmed
  pins as assembly-specific geometry rather than changing the purchased-board model.
- Keep native editable sources or parameter-generating code plus STEP for
  mechanical interchange. Generate visual GLB and simplified collision geometry
  from that source, with explicit mm-to-m conversion into simulation.
- Record source URL, revision, author/license, checksum, local modifications,
  dimensions/datum conventions and applicability to the ASIN for every adopted
  model. Distinguish `published`, `photo-observed`, `measured` and `assumed` fields.
- Define insertion/removal space and cable bend/service envelopes separately from
  solid geometry: USB plug, servo plugs, OLED cable, battery connector, toggle
  lever, trimmer access and socketed-board removal.
- Before enclosure fitting, obtain top/bottom views with scale and side-on stack
  measurements; prioritize converter outline, header heights, maximum underside
  protrusion, board offsets, OLED holes and switch mounting thread. Request close-ups
  for connector/header identity where needed. **NEEDS-HARDWARE**.

This research does not change calibrated joint mapping or the current simulator
manifest. [Upstream CAD downloads and import audit](../assets/cad/README.md) include
the Sesame assembly, three Adafruit comparison models and simulator-matched STLs.
FreeCAD import, shape-validity checks and a GUI preview are complete; physical fit
validation remains pending. See the [co-design workflow recommendation](CAD-CO-DESIGN.md).
