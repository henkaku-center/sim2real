# Electronics CAD sources and S3 assembly preparation

Research date: **2026-09-23**. This is a source-selection and measurement record,
not a validated assembly model. Component geometry and the eventual assembly belong
in `sim2real`; purchase quantities/costs remain canonical in APS
`docs/ii/inventory/data.json`. Link purchases by ASIN, not just generic component name.

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
manifest. No third-party CAD assets have yet been imported or fit-validated.
