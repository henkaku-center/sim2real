# V3 example head: shell and removable lid

The shared Loftwork V3 shell/lid is the starting geometry. A proper 180° Z
rotation places its OLED face toward body +X, with Y left and Z up. The supplied
lid is seated 20 mm below its stored exploded position. The upper shell and lid
are raised 8 mm, splicing above the OLED aperture at body Z=47.7 mm.

Two bottom-open side notches are centred at X≈−0.225717 mm between the front and
rear hip servos. Each is 8 mm wide, ends at Z=55 mm and has R2 top corners.
Ribbons rise from the midpoint channels, pass inward through the notch, then fan
out to the hub. Entry levels are staggered by 1.8 mm. The route is an authored
illustration, not a live contact solver.

The native OLED aperture and mounting features remain. No purchased OLED model
is fitted in this head: actual display retention and pin clearance are unverified.
An additional rear USB access cut follows the modeled S3 connector.

## Recorded checks

`assembly.json` identifies the exact source and output meshes. The generator
checks valid closed solids/meshes, zero shell/lid intersection, matching four
head fixing axes, all 710 native electronics shapes and four separate spacers.
Head-to-spacer gaps are approximately 0.973, 0.965, 0.773 and 0.766 mm.
The current route receipt contains 57,012 ribbon surface samples and 16 leg
bounds at Rest/Standing. Those samples clear the fitted head; this does not
establish clearance for every continuous motion or physically bent ribbon.

Print `head-cover-print.stl` and `head-lid-print.stl` separately. Editable
`head-cover.step` and `head-lid.step` retain assembly coordinates. Slicing results
are recorded separately from CAD checks. No physical print/fit result is claimed.

The November 1 Bambu Studio trial uses supports for the shell/lid plate. An
unsupported trial reported floating regions; enabling supports removed that
warning. `head-slice-check.json` records the exact mesh hashes and estimates.

Change the shape, expression, cable routing or mounting to suit your own robot.
Credit: Jom Jetsada / Loftwork V3 contributors; original Sesame by Dorian Todd
and contributors. See `README.md` and `reference-v3/source.json` for provenance.
