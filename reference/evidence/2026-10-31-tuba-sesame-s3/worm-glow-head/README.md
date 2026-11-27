# Worm glow head (V3 kit, 2026-11-14)

A caterpillar-style shell for the robot, with the same attachable bottom as the sphere head.
The bottom part is kept **exactly** as the V3 head-cover, so it screws on the same way.

- **Below Z 24 mm: V3 shell unchanged.** This keeps the 4 head screws/bosses, the ribbon and battery notches, and the lower USB opening. The CAD difference is 0 mm³.
- **Above that:**
  - a flat floor ring (1.6 mm)
  - a long thin half-ellipsoid body, 64 × 41 × 46 mm semi-axes
  - 5 hollow ribs (worm segments), 4 mm proud
  - a smooth face segment at the front around the OLED
  - two antennae (Ø 3 mm stalks, Ø 6 mm balls)
- **Openings:** the V3 OLED front plate is kept, with a visor through the face. The switch bore and USB opening have tunnels through the wall.
- **No lid:** remove the 4 head screws to open.
- **Glow:** the ribs are hollow at the same wall thickness, so the whole shell glows evenly.

Size: 128 × 90 × 69 mm (antenna tips 74 mm above the deck). About 59 g (1.2 mm) solid PLA, less with normal infill.

## Checks (`worm-head-*-checks.json`, CAD only)

| Check | Result |
|---|---|
| V3 bottom part (below Z 23.4) unchanged | 0 mm³ |
| OLED window / USB / switch bore blocked | 0 mm³ |
| Overlap with frame / leg zone (Z ≤ 22.1) | 0 mm³ |
| Half-width (raised feet start at ±49) | ±44.8 mm |
| V3 inside space lost | about 67 mm³, in the rear-top lid-rail corners (same area as the sphere head) |
| Single closed solid, 0 non-manifold edges (after STL load) | yes (`edges.py`) |

## Print (Bambu P1S)

- Use `worm-head-1.2mm-print.stl` (or 0.8 mm for more glow), printed upright on its bottom rim.
- Material: PLA Matte or PLA Basic. Use 3 walls (1.2 mm) or 2 walls (0.8 mm).
- Supports: tree, **on build plate only**. They hold the inner roof, the floor ring and the rib undersides. Snap them out through the bottom.

Rebuild: `python worm_head.py <kit> <out> 1.2` (manifold3d + trimesh), then preview with `render_worm.py`.

Derived from the Loftwork `printing_V3` kit (Jom Jetsada, Paul, contributors) and the
original Sesame by Dorian Todd (Apache-2.0).
