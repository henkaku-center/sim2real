# Centipede, 2 segments / 4 legs (V3 kit, 2026-11-14)

A test version of the centipede body. It has two hinged segments with 2 legs each, so the 4 legs I already have can test it.
Each segment has a detachable round glow cap. Take the cap off to reach the head screws, the PCB or the battery.

| | Segment 1 (front) | Segment 2 (rear) |
|---|---|---|
| Legs | L1, R1 (V3 front bays, unchanged) | L2, R2 (V3 rear bays, unchanged) |
| Inside | battery (native V3 battery bay), switch, OLED | PCB on the 4 V3 spacers, USB at the rear |
| Front/rear wall | switch hole Ø 6.5 mm in the front wall (2 mm flat) | V3 USB opening, cut through the cap too |
| Hinge part | tongue (rear) | fork, 2 tabs (front) |

The same servo channels are used, so the firmware is unchanged.

## Parts

- **Frame:** the V3 internal frame with one pair of servo bays removed and a hinge half added. The kept bays and the PCB/battery mounts are unchanged (0 mm³).
- **Base:** the V3 head-cover band below Z 19. It uses the same 4 head screws into the frame and has 2 M2 bosses for the cap. There is a 12 × 8 mm wire slot at the hinge end.
- **Cap:** a round dome with a 1.2 mm wall that rests on the band top (a 194 mm² ledge). Its 3.8 mm skirt goes over the band, and it's held by 2 × M2×5 screws at the ends.
- **Hinge:** an M3×20 pivot bolt with a nyloc nut. A second M3×20 **lock bolt** 7 mm beside it makes the body rigid. **Keep the lock bolt in for walking tests**; take it out to let the body bend (±35° with no collisions in CAD).
- **Bottom cover:** the unchanged V3 `bottom-cover.stl`, one per segment.

## Checks (`centipede-checks.json`, CAD only, 3 passes)

| Check | Result |
|---|---|
| Kept servo bays / band below Z 14 unchanged | 0 / 0 mm³ |
| Pivot holes aligned; hinge parts touching at rest | 0 mm offset / 0 mm³ |
| Collisions while bending −35…+35° | 0 mm³ |
| PCB space: board + 20 mm everywhere, + 30 mm in the middle (like V3) | 0 mm³ blocked |
| Battery bay / USB opening blocked | 0 / 0 mm³ |
| Switch: wall at the hole | 2.0 mm, flat ±6 mm |
| Switch: 13 × 8 × 16 mm body space, nut zone | 0 / 0 mm³ blocked |
| Width (raised feet start at ±49) | ±30.7 mm caps, ±46.6 mm frames (same as V3) |
| Every print STL: 1 solid, 0 non-manifold edges | yes |

### Balance (estimated)

- **Mass:** about 352 g in total, nearly the same in each segment. The battery is in segment 1 and the PCB in segment 2, so the balance point sits 1.3 mm from the middle of the 4 feet.
- **Standing on 4 feet:** the balance point is at least 50 mm inside the support area, so it's very stable.
- **One foot lifted:** the balance point sits almost exactly on the diagonal (0.8 mm). This is the same as the current Sesame and any 4-legged robot. The walk relies on quick steps, so keep the lock bolt in.
- **3-segment, 6-leg version:** this fixes it, because 3 feet always stay down.

## Print (Bambu P1S, PLA)

| File | Count | Orientation | Supports |
|---|---|---|---|
| `seg1-frame-print.stl`, `seg2-frame-print.stl` | 1 each | as given (PCB face down, like V3) | tree, build plate only (under the hinge parts) |
| `seg1-base-print.stl`, `seg2-base-print.stl` | 1 each | rim down | tree, build plate only (small) |
| `seg1-cap-print.stl`, `seg2-cap-print.stl` | 1 each | skirt down | tree, build plate only (inside the dome; snap out) |
| V3 `bottom-cover.stl` | 1 more (I have 1) | flat | none |

- **Frames:** 0.2 mm layers, 4 walls, 25 % infill, like V3.
- **Caps:** 2 walls for the glow.

**Hardware:**
- 2 × M3×20 bolts + 2 × M3 nyloc nuts
- 4 × M2×5 screws (caps)
- the usual V3 screws × 2 (head, cover, PCB)

The front servo leads now run about 15 cm further to the PCB. If a lead is short, use a servo extension.

Rebuild:
- `python centipede.py <kit> <out>`
- `render_centipede.py` for the preview
- `print_check.py <out> <kit>` for overhangs

Derived from the Loftwork `printing_V3` kit (Jom Jetsada, Paul, contributors) and the original Sesame by Dorian Todd (Apache-2.0).
