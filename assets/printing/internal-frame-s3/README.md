# Wider internal frame for the APS PCB

This changes the **Internal-Frame-v121** part in the supplied
`Sesame-ESP32-v122.step` assembly. The existing L1–L4 / R1–R4 leg STLs are unchanged.

- PCB: **70 × 50 × 1.6 mm**, read from the existing native electronics model.
- Widening: **18 mm total**, translating each side by **9 mm**. No scaling of
  servo pockets, screw holes or leg interfaces.
- Central support: **38.44 → 56.44 mm**, leaving **3.22 mm per side** of the PCB.
  This is 2 mm extra per side compared with the previous 14 mm widening.
- The side allowance reserves a **2 mm head wall**, **0.6 mm PCB clearance** and
  **0.62 mm outer clearance**. The two 70 mm-long wall envelopes are checked
  against the native electronics through their full height. These are space
  reservations; the next head revision must fit its complete shape, mounting,
  cable outlets and OLED window to this frame. The old head is not a fitted part.
- Four **separately printed 3 mm spacers**, with **66 × 46.4 mm** mounting-hole
  spacing. The spacers have 1.9 mm clearance bores; the frame has 1.3 mm pilots.
  Corner-hole diameter is approximately 2 mm in the model, not a verified product
  specification. Dimensions are editable in `params.json`.
- Proposed fastener: **Ø1.6 × 8 mm pan-head plastics thread-forming screw**.
  Stack: 1.6 mm PCB + 3 mm spacer + 3.4 mm nominal penetration. Frame pilots are
  4.2 mm deep with 0.8 mm tip clearance and 1.2 mm material beneath. The pilot
  diameter is a starting point for the selected screw and printed polymer, not
  a universal fit or a substitute for a screw manufacturer's specification.
- Modeled underside pins project 1.4 mm, leaving **1.6 mm deck clearance**.
  Actual solder blobs and untrimmed leads may differ; check the assembled board.
- USB remains at the robot's rear. The frame is in millimetres, X front / Y left /
  Z up. Let the slicer place its underside on the bed.
- The battery-wire opening is at the robot's **front-right**. The old back-left
  channel is rebuilt from the intact opposite-hand geometry, including both
  walls underneath. The complete original 3D opening is rotated 180° around the
  frame centre, retaining rounded wall ends and removing the former thin outer
  remnant. This supersedes the earlier roof-only fill and extruded outline cut.

`internal-frame.step` is the editable CAD solid; `internal-frame.stl` is its
assembly-coordinate mesh. The matching `bottom-cover.step` / `.stl` are widened only after the frame
has been built and checked, using the same splice and lateral translations.
The old-width bottom cover will not match this wider frame.

For printing, use **`internal-frame-print.stl`**: the flat PCB-side face is already
on Z=0, with the underside pointing up. This removes the integral posts that
prevented flat-bed placement. Print **four copies of `pcb-spacer.stl`** upright;
`pcb-spacer.step` is editable. The ordinary frame STL retains assembly coordinates
for the guide. Print orientation is a design choice, not a physical print result.

The frame plus four spacers were sliced in Bambu Studio 02.08.02.61 with the P1S
0.4 mm / Generic PLA profile, 0.2 mm layers, four walls and 25% infill. Slicing
completed with supports disabled and **zero support toolpaths**; normal bridge
paths remain. Estimated plate time: **1 h 25 min 26 s**, filament **39.09 g**.
See `slice-check.json` for model hashes. These are slicer estimates, not a print
test or instructions to send this printer-specific G-code to another machine.

See [PCB-MOUNTING.md](PCB-MOUNTING.md) for the purchased board, fastening stack,
manufacturer guidance and the remaining corner-hole/pilot-fit uncertainties.

Both underside cover screws are centred on **Y=0** (X ≈ −30.691 and +29.437 mm).
The earlier splice had carried them 9 mm to one side. The frame's blind pilot
holes and the cover's matching through-holes, countersinks and head wells now
share the centreline. Their original axial profiles are retained; the displaced
holes are closed.

The approved top-side cleanup closes four unused electronics holes, the
accidentally mirrored rear hole, and the two obsolete front head openings that
left crescents beside the PCB pilots. Their lower head-access recesses are
retained. The two rear head fixings and two unidentified original rear holes
remain open. The four current PCB pilots and eight servo fixings are preserved.

## Rebuild and checks

Run `python -m tools.internal_frame_cad --include-bottom-cover` with the FreeCAD
Python used by `tools/check_body.py`. The upstream STEP comes from the existing
`assets/cad/sources.json` cache (`tools/fetch_cad.py`). Adjust `params.json` to
experiment; the source script and exported STEP are yours to adapt.

`assembly.json` records source/output hashes, bounds, mount coordinates and the
check results. The build checks one valid solid and a closed print mesh, the
entire native electronics assembly for intersections, and preserved servo bays
with bidirectional BRep surface samples plus volume comparisons. Direct coincident
Boolean subtraction and edge-unification fail on the imported fillets in this
OCCT version; invalid Boolean results are not used as evidence of a fit.

These are CAD checks, not a claim that someone has printed or physically tested
the new frame. Hole datums retain the existing instructor's measurements/estimates.
Source robot geometry is Apache-2.0, credited to `dorianborian/sesame-robot`; see
the pinned source record and `assets/cad/upstream/sesame/LICENSE`.
