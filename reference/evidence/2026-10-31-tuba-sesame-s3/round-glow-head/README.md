# Rounded glow head (V3 kit, 2026-11-10)

A rounder, thin-walled replacement for the V3 `head-cover` + `head-lid`, made for a
glowing shell (LEDs inside, copper-tape touch pad). It fits the printed V3
`internal-frame` + `bottom-cover` + legs without changes.

- **Below Z 16 mm** the V3 shell is kept exactly: the 4 head screws/bosses, both
  ribbon notches, and the battery notch.
- **Above Z 16 mm** a rounded dome (hull of 4 Ø36 mm corner spheres and the V3
  footprint) with a thin wall: `1.2 mm` (sturdier) or `0.8 mm` (more glow).
- The V3 front plate around the OLED is kept, with a flared visor window through the dome.
- USB (rear) and the centred tail switch keep their V3 walls, with tunnels through the dome.
- There's no lid: to open it, remove the 4 head screws.

Size: 95 × 70 × 53 mm (V3: 87 × 59 × 54 with ears). About 34 g (1.2 mm) / 27 g (0.8 mm) solid PLA.

## Checks (`round-head-*-checks.json`, CAD only, not a physical fit test)

| Check | Result |
|---|---|
| V3 band below Z 15.4 unchanged | 0 mm³ difference |
| V3 shell volume outside the new dome | 0 mm³ (all old inside space kept) |
| Material added inside the V3 interior | ≈0 (only fills outside pockets of the old wall) |
| OLED window / USB / switch bore blocked | 0 mm³ |
| Overlap with internal frame | 0 mm³ |
| Leg zone (abs(Y) ≥ 31.6, Z ≤ 22.1) | 0 mm³ |
| Single closed solid | yes (1 part) |

## Print (Bambu)

- Use `round-head-1.2mm-print.stl` or `round-head-0.8mm-print.stl`, printed upright on the flat bottom rim.
- Use translucent/white PETG or PLA. For 1.2 mm walls use 3 walls of 0.4 mm; for 0.8 mm use 2 walls. Set infill to 100 % (the walls are solid anyway).
- Supports: tree, **on build plate only**. They hold up the inner roof from below through the open bottom, so the outside stays smooth.
- Print a 1.2 mm first; 0.8 mm glows more but is fragile around the screws.

Regenerate:

```
uv run --no-project --python 3.12 --with trimesh --with manifold3d --with numpy python -I round_head.py "<kit folder>" <out dir> 1.2
```

Derived from the Loftwork `printing_V3` kit (Jom Jetsada, Paul, contributors) and the
original Sesame by Dorian Todd (Apache-2.0).
