# Tachikoma upper body: plan (2026-11-05)

Base (unchanged, already printed): V3 `internal-frame` + `bottom-cover` + the 8
legs from `Sesame Robot Build Guide/`. Only the upper body is new: it replaces
the V3 `head-cover` (shell) and `head-lid`. Drawing: `tachikoma-plan.png`. Kit = the course V3 frame/head kit (Nov 2026).

All numbers are from the kit's CAD (`assembly.json`, `head-cable-clearance.json`,
`tail-switch-check.json`), in body coordinates: **X+ front, Y+ left, Z up**,
with the frame top deck at Z ≈ 5 and the ground at Z ≈ −49 when standing.

## What it must fit (measured)

| Item | Value |
|---|---|
| Frame | X −43.5…43.7, Y ±46.6, Z −10.7…5.0 (87.2 × 93.2 mm) |
| V3 head footprint | X −43.5…43.7, Y ±29.3 (87.2 × 58.5), Z 5.0…50.2 |
| Head screws (attach) | 4 axes at (−37.5, ±26.5) and (40.1, ±27.4) |
| OLED window | X 36.4…39.9, Y ±11.3, Z 29.9…42.1 (front wall) |
| Ribbon notches | each side, centre X 0.4, 15.5 wide, Z 5…15, bottom-open |
| Battery wire | front-right notch 6 × 8 mm |
| USB access | rear, X −44.5…−30.9, Y −17.4…−5.4, Z 19.9…26.9 |
| Power switch | rear centre bore Ø5 at X −39.9, Z 37.6 (toggle sticks out ~10 mm) |
| Lid rail | lid X −38.3…34.0, Y ±26.2, Z 48.2…52.0, slides in from the rear |
| Legs (top parts + foot servos) | |Y| ≥ 31.6, **Z ≤ 22.1** in Rest and Stand |
| Feet | |Y| ≥ 49 (Stand) / ≥ 63 (Rest); raised feet in wave/dance stay out at |Y| ≳ 49 |

## Design

1. **Thorax shell (replaces `head-cover`)**, printed in one piece:
   - Lower band Z 5…25 is the V3 shell, unchanged: the 4 screw bosses, ribbon notches, battery notch, USB opening, switch-side rear wall. This is what guarantees the fit.
   - Above Z 25 the Tachikoma thorax: rounded, up to **88 × 80 mm** (Y ±40, overhanging the legs, which stay below Z 22, so ≥ 3 mm clearance), roof at Z ≈ 55.
   - The V3 lid rail is kept on the roof.
2. **Head pod (front, part of the thorax print)**:
   - X 44…60, 48 mm wide, Z 25…50, rounded nose.
   - An open, flared window (~30 × 18 mm) in front of the OLED, so the screen is the main "eye".
   - Two small printed lenses on the pod sides for the classic three-eye look.
3. **Abdomen pod (replaces `head-lid`)**:
   - The V3 lid's exact rail profile as its base, so it slides on and off like the lid (access to the electronics).
   - On top: a hollow ellipsoid ~**85 × 62 × 45 mm**, X −20…−105, Z 50…95, sitting high behind the thorax like the anime.
   - Its underside stays above Z 48 behind the body, clearing the switch (Z 37.6) and the USB (Z 20–27).
4. **Attach**:
   - Thorax: the same 4 screws as the V3 head.
   - Abdomen: the V3 lid rail, plus 2 optional 6 × 2 mm magnets if it slides out while walking.
   - Nothing new to drill in the frame.

## Size and weight

- Overall about 165 mm long (X −105…60), 80 mm wide at the body (legs wider), top ≈ 145 mm above the ground when standing.
- Target weight ≤ 60 g total (thorax ~35 g, abdomen ~20 g): PLA, 2–3 walls, 10–15 % infill, abdomen 1.2 mm hollow shell.
- The abdomen moves the centre of mass back about 5–8 mm, so check that walk still works. If it tips backwards, shorten the abdomen to X −90 or use the fabric version (thin printed ribs + stretch fabric, ~8 g).

## Build steps (next)

1. Generate the parts in CAD (Python `build123d`/OCP via `uv`; FreeCAD/Blender are not installed). Import `head-cover.step` and `head-lid.step`, keep the lower band and the rail, and add the thorax, head pod and abdomen.
2. Check numerically: closed solids, the 4 screw axes unchanged, OLED/USB/switch/notches open, no intersection with the electronics or the Rest/Stand leg bounds.
3. Export print STLs (thorax rim-down with tree supports; abdomen rail-down) and a slice check.
4. Print the abdomen first (cheap) to check rail fit, then the thorax.
5. Battery test: full demo loop + walk with the shell on; read `log` for brown-outs.

Being slightly larger is fine everywhere except two limits: thorax under Z 25 (must stay the V3 band) and the |Y| ≤ 40 overhang (raised feet).
