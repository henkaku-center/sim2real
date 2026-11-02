# Low-roof head, fixed ears and removable lid

The November 2 instructor correction keeps the native V3 lower cable entries,
closes both unwanted upper side openings, and removes the added tall side slots.
The V3 main roof is no longer raised 8 mm. The original Sesame ear profiles are
restored at the front corners, attached to the shell on fixed shoulders.

The removable lid covers the rear roof and extends forward as a central tongue
between the ears. This gives access behind the display while the ears remain
part of the shell. Its upper seating flange remains; the inherited flared skirt
is replaced by a straight slip-fit skirt so the lid can lower past the rim.
The skirt and new shoulder/tongue seams have a provisional 0.3 mm CAD clearance.
Nine sampled lid heights are checked for shell/ear intersections. Physical print
fit and retention are unverified.

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
STEP files for editing. `head-slice-check.json` identifies the exact sliced files
and settings; slicer estimates are not physical print results.

Credit: Jom Jetsada / Loftwork V3 contributors; original Sesame by Dorian Todd
and contributors (Apache-2.0). Students may freely modify or replace this example.
