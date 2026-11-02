# Faster V3 CAD iteration

## Live comparison workbench

```sh
python tools/preview_printing.py --part all --watch --serve 8852 \
  --params tests/artifacts/cad-workbench/params.json \
  --output tests/artifacts/cad-workbench
```

First copy `assets/printing/internal-frame-s3/params.json` to that working parameter
path. Edit that copy to experiment. Saves are debounced; one build runs at a time.
An edit that arrives during a build supersedes that result. A head-only parameter
change rebuilds the head, not the frame/spacer. Invalid or failed edits retain the
last successful geometry with a visible error. New successful geometry is published
atomically, with the previous distinct version retained.

The responsive page offers head/frame/spacer selection and After / Before / Overlay.
Camera position and target remain fixed between versions; Fit explicitly reframes.
Both STEP versions remain downloadable. Display STL assemblies are for comparison;
use the individual release parts for printing.

For phone access, expose the local port with Tailscale Serve on an unused path,
preserving all existing routes:

```sh
tailscale serve status --json
tailscale serve --bg --https=443 --set-path=/cad-review http://127.0.0.1:8852
```

Use the HTTPS tailnet hostname printed by Serve, with `/cad-review/`. Verify the
page, scripts, styles, vendor modules and model downloads at that URL. The viewer
has no CDN dependency: unmodified Three.js 0.180.0 and OrbitControls are vendored
with their MIT license and checksum receipt. The HTTP server exposes only its
viewer assets, status and published build files; it does not expose the repository.
Stop the watch process with Ctrl-C. Remove only this route with
`tailscale serve --https=443 --set-path=/cad-review off` when no longer needed.

## Individual previews

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

Use `--part frame` or `--part spacer` for those individual previews, or `--part all`
to build all three. Frame preview retains the pilot-axis/floor checks; spacer
preview checks a valid closed solid without loading the electronics.

The preview receipt lists the checks not run. Preview cannot target the canonical
kit directory or any directory holding a release receipt. To regenerate the full
kit, use FreeCAD Python: `python -m tools.internal_frame_cad --include-bottom-cover`.
The browser-guide importer still consumes a committed full-build receipt.

## Validation groups

Full local builds reuse successful electronics checks per solid, servo-bay checks,
and ribbon-surface checks. Each entry names its group and hashes the exact BRep
geometry, relevant inputs (electronics source/snapshot/placement or ribbon samples
and notch settings), checker/loader code and FreeCAD/OCCT versions. Failed checks
are never cached. Corrupt result receipts are recomputed. `assembly.json` records
which groups were reused and their content keys.

`--fresh-checks` forces every group to run and refreshes the cache. CI does this
before testing a cached rerun. `--check-cache PATH` selects an isolated cache;
the default is the ignored `tests/artifacts/printing-check-cache`. Cheap mounting,
spacer, source-datum and leg checks still run on every full build.

Geometry fingerprints are captured before optional native checks: Boolean and
classifier calls can populate internal shape caches, so hashing again after a
conditionally skipped check would make later cache keys depend on which checks
ran. The fresh-versus-cached integration test covers this ordering.

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
- With grouped validation caching, a later fresh/cached pair measured **243.65 s
  and 24.53 s**. All nine groups were reused; complete numerical receipts and
  STEP/STL hashes matched, apart from the explicit cache-hit records. These are
  local single-run observations under the workload at that time.

This speeds up the edit/review loop by doing less work, not by claiming that the
full fit checks became faster. Native tests compare preview geometry with the
delivered STEP, exercise an 8→10→8 mm notch edit, verify exact restoration of the
preview outputs, and confirm an electronics-source change invalidates the cache.

The November 2 head revision uses a native-height roof, fixed original-profile
ears and a T-shaped lid. The edit/revert regression now changes roof lift rather
than cutting a taller side slot; the lower cable openings stay native.
The full build still checks all 710 electronics shapes and the authored ribbon
samples. CAD and sampled-pose checks do not establish physical print fit.
