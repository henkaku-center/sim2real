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
- New PCB supports: 4 mm above the frame deck, with the recorded **66 × 46.4 mm**
  mounting-hole spacing. The 1.4 mm pilot holes are intended for M1.6 screws through
  the PCB's approximately 2 mm holes; dimensions are editable in `params.json`.
- USB remains at the robot's rear. The frame is in millimetres, X front / Y left /
  Z up. Let the slicer place its underside on the bed.
- The battery-wire opening is now at the robot's **front-right**. Its original
  back-left top opening is filled. The same measured notch profile is rotated
  180° around the frame centre, retaining its dimensions and edge offsets.

`internal-frame.step` is the editable CAD solid; `internal-frame.stl` is its print
mesh. The matching `bottom-cover.step` / `.stl` are widened only after the frame
has been built and checked, using the same splice and lateral translations.
The old-width bottom cover will not match this wider frame.

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
