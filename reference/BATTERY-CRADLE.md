# Battery cradle — a FreeCAD-free design loop

This is a new, standalone CAD prototype, **not a verified attachment to Sesame**.
It does not change the existing robot, power wiring, motion or physics model.
Nothing has been purchased, printed, loaded or fitted for this prototype.

## Agent entry — no UI required

Work in the builder's own checkout. Translate their prompt or annotated image
into explicit dimensions; label any assumptions. Use the existing CLI rather
than asking the builder to operate a configurator:

```sh
(cd tools/occt && npm ci)
printf '{"length":82,"width":51,"height":36}' | \
  node tools/occt/cradle-build.mjs ./out/cradle --receipt > ./cradle-receipt.json
```

Node 24 and the existing locked OCCT WASM dependency are sufficient; no FreeCAD,
browser, private server, model account or inference call is required. The output
directory receives `cradle.step`, `cradle.stl`, and `cradle.json` (parameters,
measured CAD dimensions, checks and timing). `--receipt` returns that metadata
and absolute file paths, not another copy of the STEP and base64 STL in the
agent's context. Omit it to retain the existing inline JSON/API response.

Inspect the receipt, render the exported geometry with an available renderer,
and revise from the builder's feedback. Show the final result and relevant issue
views rather than asking them to use sliders. This generator does not itself
render screenshots; state when that capability is unavailable. A new output
directory per iteration preserves earlier files. Checks are feedback, not student
approval gates or claims of printed fit. The existing robot/firmware is untouched.

## Optional existing viewer

The previously delivered viewer remains available for inspecting results; it is
not required by the agent workflow and is not being expanded:

```sh
node tools/cradle_server.mjs
```

The preview displays an STL of the same validated solid that the CLI exports.
It is not a drawing scaled to resemble CAD.

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

`tools/occt/cradle-parameters.mjs` owns defaults, validation limits and the nominal
existing-pack, Anker A1638 and G-FORCE GFG019 presets with their source URLs and
limitations. The browser, API and builder share it; the workbench shows the
dimensions and attribution. These are editable starting points, not battery
recommendations or measured fit. Changing an input still requires a successful
build before downloads are enabled; request tokens reject superseded responses.

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
