# Faster V3 head iteration

Use `python tools/preview_printing.py --show` from the repository. It builds the
shell/lid through the same native FreeCAD construction as the complete kit,
then gives a cadgen 0.8.4 viewer URL. Edit the head parameters and rerun the
command; that file's viewer follows subsequent writes. `--params path.json`
allows an experimental copy, and `--output directory` separates variants.

The first run extracts source placement measurements. Later runs reuse them
while the electronics FCStd, snapshot, frame STEP, source receipt, loader code
and CAD versions match. Head geometry is rebuilt on every invocation. This avoids
opening the full electronics document and copying its 710 shapes for each edit.

## What the two paths do

| Path | Checks and output |
|---|---|
| Preview | Valid closed shell/lid, unchanged OLED aperture, shell/lid intersection and base height; STEP files plus `preview.json` under `tests/artifacts/head-preview/` |
| Full build | Electronics/spacers, mounting axes, servo bay preservation, ribbon samples, leg bounds, complete STEP/STL kit and `assembly.json` |

The preview receipt lists the checks not run. Preview cannot target the canonical
kit directory or any directory holding a release receipt. To regenerate the full
kit, use FreeCAD Python: `python -m tools.internal_frame_cad --include-bottom-cover`.
The browser-guide importer still consumes a committed full-build receipt.

On macOS the wrapper finds `/Applications/FreeCAD.app`. On Linux use a FreeCAD
Python environment, or set `FREECAD_PYTHON` (and `FREECAD_LIB` if needed).
`--show` uses the separately installed `cadgen +0.8.4`; the preview itself needs
only the existing FreeCAD environment. Upstream cadgen is unmodified.

## Measurements — November 1, 2026

Local Intel Mac, single-run observations, not a cross-machine benchmark:

- Profiled full V3 build: 195.94 s, including 112.72 s in native point-in-solid
  queries, 37.79 s in Boolean intersections and 17.41 s in distance queries.
- Initial uncached preview: about 10–12.5 s, dominated by source/electronics input.
- Warm-input preview with a real notch-width change: 1.75 s for geometry and
  export; restoring the original width: 1.80 s. These exclude interpreter startup
  and viewer redraw. The wrapper separately prints command wall time.
- A fresh CLI process using the cached inputs completed in **3.03 s wall time**,
  including interpreter startup (1.81 s inside preview construction/export).

This speeds up the edit/review loop by doing less work, not by claiming that the
full fit checks became faster. Native tests compare preview geometry with the
delivered STEP, exercise an 8→10→8 mm notch edit, verify exact restoration of the
preview outputs, and confirm an electronics-source change invalidates the cache.
The full build still checks all 710 electronics shapes and the authored ribbon
samples. CAD and sampled-pose checks do not establish physical print fit.
