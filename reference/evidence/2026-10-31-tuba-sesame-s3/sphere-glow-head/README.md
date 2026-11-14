# Sphere glow head (V3 kit, 2026-11-10)

Built from my sketch (`sketch.jpg`): a big half-sphere dome over the robot, with the
attachable bottom part kept **exactly** as the V3 head-cover, so it screws on the same way.

- **Below Z 24 mm: V3 shell unchanged.** This keeps the 4 head screws/bosses, the ribbon and battery notches, and the lower USB opening. The CAD difference is 0 mm³.
- **Above that:**
  - a flat floor ring (1.6 mm) and a thin dome (`1.2 mm` or `0.8 mm`)
  - semi-axes 52 × 46 × 46 mm, so it's nearly a sphere, slightly longer front-to-back to clear the OLED and switch
- **Openings:**
  - The V3 OLED front plate is kept, with a flared visor through the dome.
  - The switch bore and USB opening have tunnels through the dome.
- **No lid:** remove the 4 head screws to open.

Size: 104 × 92 × 65 mm (dome top 70 mm above the deck). About 43 g (1.2 mm) / 37 g (0.8 mm) solid PLA.

## Checks (`sphere-head-*-checks.json`, CAD only)

| Check | Result |
|---|---|
| V3 bottom part (below Z 23.4) unchanged | 0 mm³ |
| OLED window / USB / switch bore blocked | 0 mm³ |
| Overlap with frame / leg zone (Z ≤ 22.1) | 0 mm³ |
| Floor above the legs | 1.9 mm |
| Dome half-width vs frame (raised feet are outside the frame) | ±46.0 vs ±46.6 mm |
| V3 inside space lost | about 56 mm³, only in the two rear-top corners (lid-rail area, Z 37–50). Check nothing sits there. |
| Single closed solid, 0 non-manifold edges (after STL load) | yes (`edges.py`) |

## Print (Bambu)

- Use `sphere-head-1.2mm-print.stl` (or 0.8 mm), printed upright on its bottom rim.
- Use translucent/white PETG or PLA, with 3 walls (1.2 mm) or 2 walls (0.8 mm).
- Supports: tree, **on build plate only**. They hold the inner dome and the floor ring.
- The floor ring overhangs the V3 band by up to 22 mm, so the supports under it are required.

Derived from the Loftwork `printing_V3` kit (Jom Jetsada, Paul, contributors) and the
original Sesame by Dorian Todd (Apache-2.0).
