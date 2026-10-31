# Separate PCB spacers and fastening

## Purchased board

APS inventory identifies **Amazon Japan ASIN B071JYD6QP** as the installed
**50 × 70 mm double-sided carrier**. The September 23 product-source record lists
**1.6 mm thickness**, **2.54 mm pitch**, an **18 × 24 grid** and **0.9 mm signal
holes**. That last number is not the corner mounting-hole diameter. The listing
also contained conflicting 60 × 80 mm bullet text; the instructor confirmed the
50 × 70 mm board. The separate B0CX1RGYFG purchase was the wrong size.

The four corner holes are modeled as **2.0 mm diameter**, on **66 × 46.4 mm**
centres. They remain photo/record-derived datums, not a manufacturer's screw
specification. There is no verified included/recommended mounting screw for this
ASIN in our records. The current listing could not be independently rechecked in
this session. Product record: `reference/ELECTRONICS-CAD-SOURCES.md` and native
`MountingHoleParameters` in `assets/cad/Sesame-S3-Assembly.FCStd`.

## Proposed printed joint

Print **four identical loose spacers**, 3 mm high, 4.9 mm outside diameter and
1.9 mm clearance bore. Place them on the frame's four pilot holes, then lower
the board with its USB connector toward the rear.

| Stack / allowance | Nominal CAD value |
|---|---:|
| PCB thickness | 1.6 mm |
| Loose spacer height | 3.0 mm |
| Proposed pan-head plastics screw, under-head length | 8.0 mm |
| Screw major diameter | 1.6 mm |
| Penetration into frame: 8 − 1.6 − 3 | 3.4 mm |
| Frame pilot diameter / depth | 1.3 / 4.2 mm |
| Extra depth beneath screw tip | 0.8 mm |
| Material below blind pilot | 1.2 mm minimum |
| Lowest modeled underside pin projection | 1.4 mm |
| Modeled underside clearance: 3 − 1.4 | 1.6 mm |

The penetration is an axial stack calculation, not a tested thread pull-out
rating or the full-thread engagement after subtracting a particular screw tip.
The pilot diameter is provisional for the selected screw, polymer and printer.
Use a plastics-specific thread-forming screw; a metric M1.6 machine screw has a
different thread and should not be substituted into an untapped pilot by name.
The exact 8 mm screw SKU is not purchased or verified here.

The inventory's **M2×5** screws leave only 0.4 mm penetration with this stack and
are not the proposed PCB fixing. The recorded **M2.5×5** screws do not fit the
modeled 2 mm corner holes. Do not enlarge the PCB holes merely to use those screws.
Check the delivered corner-hole size before ordering the final fastener.

Use a flat-bearing pan head rather than a countersunk head on the flat PCB.
The spacer is unthreaded, so the screw clamps the board and spacer against the
frame. Tighten only enough to seat the stack without bowing the PCB or stripping
plastic. Check real underside solder/leads against the spacer height; the native
solder model is illustrative. A taller spacer needs a correspondingly longer
screw and a fresh depth check. Repeated disassembly favors a designed-in metal
insert or nut rather than repeatedly reforming plastic threads.

## Printing

`internal-frame-print.stl` puts the flat PCB-side face on the bed, with underside
features growing upward. The reinforcement for the pilot holes stays beneath
that face; no posts protrude above it. `pcb-spacer.stl` sits upright on Z=0;
print four copies. `internal-frame.stl` retains assembly coordinates for the
guide. No modeled M1.6 thread is expected to print accurately in these holes.

## Manufacturer guidance consulted — October 31, 2026

- TAKACHI, **EM series PCB mounting screws**:
  https://www.takachi-enclosure.com/products/EM
  Describes self-tappers for plastic-case PCB bosses, including diameter 1.6 mm.
  Its EM-1.6 is only 4 mm long; it is an example of the fastener type, not the
  selected part for this longer spacer stack.
- Formlabs, **3D Printing Threads and Adding Threaded Inserts**:
  https://formlabs.com/blog/adding-screw-threads-3d-printed-parts/
  Advises plastics-appropriate screws and manufacturer-specific boss dimensions;
  metal inserts/nuts better withstand repeated assembly. Its material-specific
  SLA/SLS guidance does not establish a validated FDM pilot diameter for this part.

CAD verifies all 710 native electronics shapes against the frame and all four
spacers, a flat print face, clear pilot axes and material below their blind ends.
Those checks are not physical fastening, solder-height or print tests.
