# Centipede, 2 segments / 4 legs (V3 kit, 2026-11-14)

A test version of the centipede body. It has two hinged segments with 2 legs each, so the 4 legs I already have can test it.
Each segment has a detachable round glow cap. Take the cap off to reach the head screws, the PCB or the battery.

| | Segment 1 (front) | Segment 2 (rear) |
|---|---|---|
| Legs | L1, R1: V3 front bays, **moved to the segment centre** | L2, R2: V3 rear bays, **moved to the segment centre** |
| Inside | battery (native V3 battery bay), switch, OLED | PCB on the 4 V3 spacers, USB at the rear |
| Front/rear wall | switch hole Ø 6.5 mm in the front wall (2 mm flat) | V3 USB opening, cut through the cap too |
| Hinge part | tongue (rear) | fork, 2 tabs (front) |

The same servo channels are used, so the firmware is unchanged.

## Parts

- **Frame:** the V3 internal frame. One pair of servo bays is kept and moved so the hip shafts sit at the segment centre (X 0); the other pair is removed. A hinge half is added. The moved bays are identical to V3 (0 mm³ difference), and the PCB and battery mounts are unchanged.
- **Base:** the V3 head-cover shell below **Z 27**, 3 mm higher than the sphere head's Z 24. It uses the same 4 head screws into the frame and has 2 M2 bosses for the cap. There is a 12 × 8 mm wire slot at the hinge end.
  - The V3 USB opening (Z 19.9–26.9) is cut through the cap skirt too. On seg 1 it's a spare cable hole.
  - The base stops below the OLED window (Z 29.6), so there's no window to close.
- **Cap:** **the same dome as the sphere head** (52.5 × 46 × 46 mm, 1.2 mm wall) on a 1.6 mm flat floor ring.
  - The ring rests on the base top (335 mm² contact).
  - A 4 mm skirt goes over the base, held by 2 small pan-head screws at the ends.
  - The cap is 105 × 92 mm, and its top is 73 mm above the deck (the sphere head's was 70 mm).
- **Hinge:** a fork (2 tabs, seg 2) and a tongue (seg 1).
  - **Pivot:** your long countersunk self-tapping screw, with no nut. It goes through clearance holes (Ø 3.3) and a countersink in the top tab and tongue, then threads into a Ø 2.4 pilot in the bottom tab. An M3 bolt + nut also fits.
  - **Lock screw:** a second long screw 7 mm beside the pivot makes the body rigid. **Keep it in for walking tests**; take it out to let the body bend (±35° with no collisions in CAD).
- **Bottom cover:** `seg1-cover` / `seg2-cover`. This is the V3 cover with its bay tabs moved the same way. The old V3 cover no longer matches the moved bays.

## Checks (`centipede-checks.json`, CAD only, 3 passes)

| Check | Result |
|---|---|
| Moved servo bays vs V3 / band below Z 14 | 0 / 0 mm³ difference |
| Hip shafts at the segment centre | X 0.0 / 0.0 |
| Pivot holes aligned; hinge parts touching at rest | 0 mm offset / 0 mm³ |
| Collisions while bending −35…+35° | 0 mm³ |
| PCB space: board + 20 mm everywhere, + 30 mm in the middle (like V3) | 0 mm³ blocked |
| Cap vs base overlap | 0 mm³ |
| Cap half-width (raised feet start at ±49) | ±46.0 mm |
| Battery bay / USB opening blocked | 0 / 0 mm³ |
| Switch: wall at the hole | 2.0 mm, flat ±6 mm |
| Switch: 13 × 8 × 16 mm body space, nut zone | 0 / 0 mm³ blocked |
| Frame width | ±46.6 mm (same as V3) |
| Every print STL: 1 solid, 0 non-manifold edges | yes |

### Balance (estimated)

- **Mass:** about 362 g in total, nearly the same in each segment. The battery is in segment 1 and the PCB in segment 2, so the balance point sits 1.5 mm from the middle of the 4 feet.
- **Legs at the centres:** each segment's weight sits right over its own legs, so the hinge only keeps the segments level and doesn't carry them. The leg pairs are 112 mm apart (V3: 57 mm).
- **Standing on 4 feet:** the balance point is at least 50 mm inside the support area, so it's very stable.
- **One foot lifted:** the balance point sits on the diagonal (0.9 mm). This is the same as the current Sesame, so keep the lock screw in for walking. The 3-segment, 6-leg version fixes it.

## Print (Bambu P1S, PLA)

| File | Count | Orientation | Supports |
|---|---|---|---|
| `seg1-frame-print.stl`, `seg2-frame-print.stl` | 1 each | as given (PCB face down, like V3) | tree, build plate only (under the hinge parts) |
| `seg1-cover-print.stl`, `seg2-cover-print.stl` | 1 each | as given (like the V3 cover) | same as your V3 cover print |
| `seg1-base-print.stl`, `seg2-base-print.stl` | 1 each | rim down | tree, build plate only (small) |
| `seg1-cap-print.stl`, `seg2-cap-print.stl` | 1 each | skirt down | tree, build plate only: under the floor ring and inside the dome (like the sphere head) |

- **Frames and covers:** 0.2 mm layers, 4 walls, 25 % infill, like V3.
- **Caps:** 2 walls for the glow.

## Screws (from the screws I have, photo `body/IMG_3359.jpg`)

The photo has nothing to show scale, so these sizes are estimates. Check them with calipers or a ruler.

| Screw in the photo | Use | Count |
|---|---|---|
| Long silver countersunk self-tapper (~2.9 mm, longest) | hinge **pivot**, top down, threads into the bottom tab | 1 |
| Long black countersunk self-tapper | hinge **lock** screw | 1 |
| Small pan-head self-tappers (~M2, 5–8 mm) | caps (2 per cap, Ø 1.6 pilots) and PCB | 4 + the V3 count |
| Tiny pointed self-tappers | servo horns (as in the guide) | as needed |
| Silver countersunk machine screw (~M3 × 10) | spare; no nut on hand. Use it as the lock screw only with an M3 nut. | 0 |

- **Hinge screw length:** the stack is 15.7 mm, so any screw of 16 mm or more works. A longer tip just sticks out below the hinge, where nothing is in the way.
- **Pilot fit:** if a self-tapper spins loose in its pilot, add a drop of glue or use an M3 bolt and nut.
- **Servo leads:** the front leads now run about 15 cm further to the PCB. If one is short, use a servo extension.

Rebuild:
- `python centipede.py <kit> <out>`
- `render_centipede.py` for the preview
- `print_check.py <out> <kit>` for overhangs

Derived from the Loftwork `printing_V3` kit (Jom Jetsada, Paul, contributors) and the original Sesame by Dorian Todd (Apache-2.0).
