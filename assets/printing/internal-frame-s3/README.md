# V3 frame, spacers and example head

This kit adapts the shared Loftwork `printing_V3` frame, bottom cover, head shell
and removable lid to the APS 70 × 50 × 1.6 mm carrier. It supersedes the earlier
v122-derived widened frame. All eight existing leg meshes remain unchanged.

The frame is approximately **87.177 × 93.230 × 15.700 mm**. Its native servo bays
retain their 27.8 mm mounting-hole pitch. The assembled shell and lid are about
**87.177 × 58.534 × 55 mm**. The head's upper section is raised 8 mm above a splice
at body Z=47.7 mm; the OLED aperture and lower mounting features are preserved.

The PCB is positioned 0.6 mm forward of V3's original PCB datum. The original
66 × 46 mm / Ø1.9 mm pilot pattern is replaced by the guide's 66 × 46.4 mm /
Ø1.3 mm pattern. Four separate 3 mm spacers and the proposed Ø1.6 × 8 mm
plastics-screw stack are retained. See `PCB-MOUNTING.md` for dimensions and limits.

Each side has one 8 mm-wide bottom-open ribbon notch, with 2 mm top corner radii,
aligned with the frame's midpoint outlet between front and rear hip servos.
The native front-right battery opening and centred underside cover fixings remain.
V3's bottom-cover STEP had one missing three-edge curved sliver; a 0.0784 mm²
patch closes that boundary without filling its screw openings.

## Files

- `internal-frame-print.stl`: PCB-side flat face at Z=0.
- `pcb-spacer.stl`: upright; print four copies.
- `head-cover-print.stl`: shell rim at Z=0.
- `head-lid-print.stl`: outer lid face down at Z=0.
- `bottom-cover.stl`: matching V3 bottom, in assembly coordinates.
- Each part also has an assembly-coordinate STL and editable STEP.
- `params.json`, `assembly.json`, `frame-datums.json` and
  `head-cable-clearance.json`: parameters, provenance and numerical check results.

Slicing receipts identify the exact checked meshes. With the Bambu Studio P1S
0.4 mm / Generic PLA profile, 0.2 mm layers, four walls and 25% infill, the frame
plus four spacers sliced without supports (about 1 h 34 min / 45.25 g). The shell
and lid sliced with supports (about 1 h 20 min / 42.27 g). The unsupported shell
trial reported floating regions; the supported trial did not. These are slicer
estimates, not physical print results. See `HEAD-COVER.md` for head-specific checks.

## Rebuild

For quick shell/lid edits, run **`python tools/preview_printing.py --show`**.
It rebuilds the native head construction and shows a STEP file in the installed
cadgen 0.8.4 viewer. Run it again after editing `params.json`; the same viewer
follows the file. `--params` accepts an experimental parameter file. On Linux,
run from a FreeCAD Python environment or set `FREECAD_PYTHON` and optionally
`FREECAD_LIB`; macOS also finds the standard FreeCAD app installation.

Preview files live in `tests/artifacts/head-preview/`. The preview checks valid
closed parts, the unchanged OLED aperture, shell/lid overlap and head-base height.
Its `preview.json` explicitly lists the assembly-wide checks not run. Unchanged
electronics/placement measurements are cached by source hashes and CAD versions;
edited head geometry is rebuilt each time. Preview never writes a release receipt
or overwrites the delivered kit. The full command below still runs every fit
check and produces the release STEP/STL files.

Use FreeCAD's Python to run `python -m tools.internal_frame_cad --include-bottom-cover`.
If mounting datums change, first run `--datums-only`, then regenerate ribbon/leg
samples with APS's `scripts/export_head_cable_clearance.mjs --frame frame-datums.json`.
The generator checks numeric datum agreement, all 710 electronics shapes,
separate spacers, matching cover/head fixing axes, unchanged servo bays, sampled
ribbon surfaces and Rest/Standing leg bounds. Run
`uv run python -m pytest tests/test_internal_frame.py -q` for artifact checks.

These are CAD and sampled-pose checks, not physical fit or full-motion validation.
Students may modify or replace the design, firmware and motion as they wish.

## Credit

V3 files shared by **Jom Jetsada / Loftwork team**; original Sesame by
**Dorian Todd and contributors** (`dorianborian/sesame-robot`, Apache-2.0).
Adaptation and public distribution of V3 derivatives were authorized by the
instructor on October 31, 2026. `reference-v3/source.json` pins source hashes,
normalization and repair details. Reference STEP exports have sanitized headers;
private original downloads are not included.
