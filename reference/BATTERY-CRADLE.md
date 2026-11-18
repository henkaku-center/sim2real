# Battery cradle — a FreeCAD-free design loop

This is a new, standalone CAD prototype, **not a verified attachment to Sesame**.
It does not change the existing robot, power wiring, motion or physics model.
Nothing has been purchased, printed, loaded or fitted for this prototype.

## Use the workbench

```sh
cd tools/occt && npm ci && cd ../..
node tools/cradle_server.mjs
```

Node 24; the existing locked `replicad-opencascadejs` dependency. No FreeCAD,
new CAD runtime, model account or inference call is required. The browser sends
dimensions to a local Node process, which constructs the real solid using OCCT
WASM. The preview displays an STL of that solid; STEP and STL downloads come
from the same validated build. This is not a drawing scaled to resemble CAD.

Server defaults to loopback port 8862 (`PORT` overrides it). For phone access,
mount `/battery-cradle/` through Tailscale Serve, preserving existing routes:

```sh
tailscale serve status --json
tailscale serve --bg --https=443 --set-path=/battery-cradle http://127.0.0.1:8862
```

Use the host's HTTPS tailnet address with `/battery-cradle/`. The workbench has
no external CDN or analytics. The server serves only explicitly listed assets;
it does not expose the repository or accept arbitrary paths, scripts or commands.
One process-isolated build runs at a time, with bounded input/output and a 30 s
timeout. A disconnected client cancels its build. Kernel allocations are released
when that build process exits. Do not expose this local workbench to the public
internet without adding authentication and appropriate service controls.

Changing an input invalidates downloads immediately. A failed build retains the
last picture but cannot offer stale files as the new design. Share inputs records
parameters in the URL fragment; no private token is included.

## What it makes

An open-ended tray with two low rails, four external M3 clearance ears and slots
for **two separate retaining straps**. The underside has 1 mm recessed strap
channels. The minimum allowed base is 2.2 mm, leaving at least 1.2 mm over those
channels. The model is not a snap fit, and the straps are not modelled or supplied.
Slot width is strap width +0.6 mm; slot thickness is 2 mm; these are design
allowances, not measured printer clearances or qualified strap specifications.

Coordinates are millimetres, X along the battery, Y across it and Z up; tray bottom
is Z=0. Battery is a nominal rectangular envelope, seated at Z=base. Clearance
is **per side**. Rail height is above the base, not a parameter controlling battery
clamping force. Height changes the displayed battery and fit check, not a lid.

Mount-hole centres are printed in the disclosure and returned in the JSON report.
They are derived from cradle size, not copied from the robot frame. Robot coupling,
foot/ground clearance, cable routes, screw-head access, strap retention, insulation,
cooling and load strength remain unverified. Battery ports, leads, plugs, buttons
and terminals are not represented by the amber box. Do not infer charging or
electrical compatibility from a geometric envelope.

Presets are editable nominal starting points, not battery recommendations:

| Preset | Body envelope | Source |
|---|---|---|
| Existing battery | 51 × 28 × 14 mm | Amazon Japan B0F3JB59B6; also recorded in ELECTRONICS-CAD-SOURCES.md |
| Anker A1638 | 82 × 51 × 36 mm | https://www.ankerjapan.com/products/a1638 |
| G-FORCE GFG019 | 96 × 47 × 19 mm | https://www.gforce-hobby.jp/products/GFG019.html |

## Export without the browser

```sh
printf '{"length":82,"width":51,"height":36}' | \
  node tools/occt/cradle-build.mjs /path/to/output > /path/to/build-response.json
```

The output directory receives `cradle.step`, `cradle.stl`, and `cradle.json`
(parameters, measured CAD dimensions, checks and timing). stdout also supplies
the browser API response. File creation occurs only when an output directory is
passed; browser exports stay in the browser until downloaded.

## Verification and limits

```sh
(cd tools/occt && npm test)
# Use an existing Playwright Python environment with Chrome:
python tests/run_cradle_browser.py --url http://127.0.0.1:8862/ --output /path/to/screenshots
```

The Node suite checks all three presets and parameter boundaries: one valid solid,
actual envelope, rail cross-section, open screw/strap holes, zero overlap with
the nominal battery, and analytic volume conservation. Export tests re-import
STEP and check STL closed-manifold edge incidence/winding, volume and bounds.
Edit/revert is checked. The browser test checks real builds, both downloads,
invalid/stale-state protection and 390/1280 px layouts. These checks do not certify
material strength, printability on a particular printer or real hardware fit.

Local builds including kernel startup and exports took roughly 1–2 seconds in
initial checks on the host Mac. This is not a benchmark against a complete robot
build, a phone-side CAD timing, or a promise for every machine.

This implements a FreeCAD-free path for **this part**, not the retirement of
FreeCAD from the pre-existing electronics/full-kit pipeline. No jig code was
copied; the separately licensed kernel already used by this repo remains intact.
TRELLIS-generated cosmetic shells are a subsequent task; no GPU inference was run.
