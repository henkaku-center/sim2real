# Low-roof head, fixed ears and removable lid

The November 2 instructor correction keeps the native V3 lower cable entries,
closes both unwanted upper side openings, and removes the added tall side slots.
The V3 main roof is no longer raised 8 mm. The original Sesame ear profiles are
restored at the front corners, attached to the shell on fixed shoulders.

The removable lid covers the rear roof and extends forward as a central tongue
between the ears. This gives access behind the display while the ears remain
part of the shell. Jom and Paul's original V3 flared underhang and matching shell
overhang are retained: rear entry, horizontal travel at fixed height, no vertical
seating. The earlier straight-skirt modification was incorrect and is removed.
The native rail clearance is unchanged; the 0.3 mm parameter applies only to the
new shoulder/tongue seams. Forty-one sampled slide positions clear the shell and
ears, while lifts of 0.25, 0.5 and 1 mm deliberately intersect the capture lip.
These establish the intended CAD assembly path, not printed friction or retention.

Keep the original joint as the baseline. If printer/material variation needs
adjustment, first print a representative rail section in the same orientation
and settings. Check hand-sliding effort and retention before altering the fit;
keep seams and first-layer expansion off the mating faces where practical.

## Cable path

Four ribbons enter side-by-side through each existing bottom-open notch, at
body Z=11.2 mm. Their centres are spaced 3.8 mm in X. The native opening is about
15.48 mm wide at that height and ends at Z≈14.97 mm. Each ribbon then rises
inside the shell and fans toward its existing header. Two alternating upper
levels keep this illustration below the lower lid. These are authored paths,
not a live contact solver or measured cut lengths.

The native OLED aperture and lower mounting features remain unchanged. The
purchased OLED is not fitted in this head model; retention and pin clearance
still need an actual assembly check. Rear USB access remains available.

The November 3 update moves the 5 mm toggle-switch bore to the horizontal centre
of the rear panel, making the outward toggle a small tail. Its original height
is retained: lowering to the panel's vertical midpoint intersects the servo hub
and nearby headers and blocks the cable approach. The former bore is filled over its
measured wall thickness. `assembly.json` records the new centre and verifies
that the old bore is closed and the new one is open. The guide places its existing
switch model and terminal wires from this same bore datum.

The old switch's rectangular internal recess is also removed; the healed rear
wall is 2 mm thick at the former bore. A separate 6 mm wide, 8 mm high bottom-open
notch on the right aligns with the native front-right frame power channel for
the battery leads. The two midpoint servo-ribbon openings remain separate.
`params.json` records the reference battery's underside placement, front/right
lead orientation and slight insertion roll; APS checks the pack and lead route
against the delivered solids.

## Sources and checks

The shell/lid starts from the shared Loftwork `printing_V3` kit. Ear surfaces are
extracted from the pinned original `Sesame-ESP32-v122.step`, without mirroring or
scaling their rounded caps. `reference-ears/source.json` records the source,
coordinate transform, cut plane and normalized STEP hashes. Editable dimensions
in `params.json` control ear placement, extension and the lid seam.

`assembly.json` records the native solids, all 710 electronics shapes, spacer
clearances, mounting axes, shell/lid overlap, sampled ribbon surfaces, and
Rest/Standing leg bounds. The internal ribbon samples are also checked against
the native electronics. These checks do not establish physical print fit,
display retention or clearance throughout every possible motion.

Print `head-cover-print.stl` and `head-lid-print.stl` separately. Use the matching
STEP files for editing. `head-slice-check.json` retains the November 2 slicing
of the earlier shell, identified by exact hashes; the centred-tail revision has
native solid/mesh checks but has not been re-sliced or physically printed.

Credit: Jom Jetsada, Paul and Loftwork V3 contributors; original Sesame by Dorian Todd
and contributors (Apache-2.0). Students may freely modify or replace this example.
