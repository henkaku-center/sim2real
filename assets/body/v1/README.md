# Sesame S3 body v1 — exported engineering draft

**Read `report.json` before printing or enabling APS guide step C.**
This folder contains generated review/fit assets, not physical-fit certification.
The editable source is `../params.json` plus `../../../tools/body_cad.py`.
Workflow and the exact **measure-tomorrow (calipers/ruler)** checklist:
[`reference/BODY-CAD.md`](../../../reference/BODY-CAD.md).

## Export paths for the APS guide

Prefix every filename below with **`assets/body/v1/`** in the sim2real repository.

| Stable ID | STEP | STL | Print-oriented 3MF | Installation |
|---|---|---|---|---|
| `body.interface-frame` | `interface-frame.step` | `interface-frame.stl` | `interface-frame.3mf` | Reuse unchanged upstream frame / servo pockets |
| `body.bottom-cover` | `bottom-cover.step` | `bottom-cover.stl` | `bottom-cover.3mf` | Reuse unchanged upstream bottom |
| `body.riser-1` | `riser-1.step` | `riser-1.stl` | `riser-1.3mf` | Front foot and inward-offset column |
| `body.riser-2` | `riser-2.step` | `riser-2.stl` | `riser-2.3mf` | Front foot and inward-offset column |
| `body.riser-3` | `riser-3.step` | `riser-3.stl` | `riser-3.3mf` | Rear straight spacer |
| `body.riser-4` | `riser-4.step` | `riser-4.stl` | `riser-4.3mf` | Rear straight spacer |
| `body.carrier-tray` | `carrier-tray.step` | `carrier-tray.stl` | `carrier-tray.3mf` | Battery rails, carrier standoffs and cable channels |
| `body.battery-drawer` | `battery-drawer.step` | `battery-drawer.stl` | `battery-drawer.3mf` | Strap pack into drawer; insert along −X; secure flange |
| `body.face-cover` | `face-cover.step` | `face-cover.stl` | `face-cover.3mf` | Slide OLED into rails, fit rear switch, connect harnesses and close |

- **`assembly.json`**: stable IDs, native object bindings, source/export hashes,
  assembly/print transforms, carrier/frame/deck fastener datums, wire routes and
  ordered installation steps. This is the guide agent's placement contract.
- **`report.json`**: all static body/component pairs, body/body pairs, alignment,
  sampled full-soft-range leg/proxy motion, wall and printability findings.
  `geometry_pass` covers everything; `new_body_geometry_pass` distinguishes the
  new parts from unresolved frozen-interface findings. Neither replaces hardware
  confirmation. `release_ready` remains false while measurements are outstanding.
- **`electronics-reference.step`**: exact visible native electronics leaves,
  **native carrier coordinates**; original FCStd/history remains authoritative.
- **`assembled-preview.step`**: body and electronics in assembled torso coordinates.
  PNG/animation previews additionally show the unchanged leg templates.
- **`scene.json.gz`**: tessellated review geometry, including original leg meshes,
  explicit screening envelopes and a hidden legacy-top-cover reference.
- **`index.html`**: assembled, front, rear, cover-off and exploded PNGs; representative
  hip GIF/contact sheet. All joint sweeps are numeric in `report.json` and
  `rom-animation.json`, not just the representative animation.

## Placement contract

STEP/STL units are **millimetres**, in the existing torso-local frame:
**X forward, Y left, Z up**. They are already assembled; do not center individual
STLs independently. Convert coordinates by `0.001` for a metre-based viewer.

The exact circuit uses its original orientation and translation
**`[-35, -25, 79]` mm**. Read this from `assembly.json` on subsequent revisions;
do not hard-code it in the guide. The carrier's board underside lands on the four
tray standoffs. The installation animation lowers the circuit along −Z.
3MF files contain **print**, not assembly, transforms and no Bambu machine profile.

The battery drawer comes out in +X after unplugging the battery and releasing
its two front screws. The cover lifts in +Z. Its OLED/switch move with it; allow
real harness service slack. USB approaches the S3 through the +X access opening.

## Review before physical use

### Recorded v1 check result (2026-10-06)

| Check | Result |
|---|---|
| Static body/component pairs | **6,732 checked**; zero new-part failures; eight retained-interface/proxy fit findings |
| Body/body intersections | **Zero** |
| Sampled motion pairs | **10,656 checked**; zero new-part failures; 58 findings against the retained frame |
| Carrier, frame and deck fastener alignment | **12/12 pass** |
| Printable part topology | **9 valid single solids; all 9 exported meshes watertight** |
| New-part wall screen | **All pass sampled 1.2 mm minimum**; smallest sampled new feature ≈1.203 mm |
| Frozen frame/bottom wall screen | Thin-feature samples flagged; original geometry preserved |
| Individual part build-volume fit | **9/9 fit 256 × 256 × 256 mm** |
| Overall release gate | **`FAIL-DRAFT` / `release_ready: false`**; physical measurement and retained-interface reconciliation remain |

The validator intentionally exits nonzero for the overall draft. Do not read
passing software regression tests or `new_body_geometry_pass` as whole-robot
approval. Overhang values are conservative surface-area screens (including
possible bridges and threshold-angle faces), not slicer support instructions.
Local runtime: FreeCAD 1.1.3 / OCCT 7.8.1 and python-fcl 0.7.0.11; macOS tested,
Linux/macOS ARM CI is configured but requires its own run evidence.

- Nominal MG90S/horn proxies are **not** measured purchased variants. The old
  upstream CAD and simulator/template hip registrations differ; retained frame
  and bottom findings must be reconciled physically rather than hidden.
- The original frame/bottom have thin features detected by the conservative
  sampling screen. Their geometry is preserved, not automatically repaired.
- The new elevated body substantially raises center of mass. MuJoCo torso mesh,
  mass, inertia and stability updates remain a documented follow-up.
- Use the 3MF orientations as a starting point. Review small bridges and overhangs
  in Bambu Studio; cover supports may be needed. No slicing/print trial occurred.
- Keep APS's optional **“place circuit in body” C step hidden** until the report
  and a human-supervised fit check are accepted. These files can already be used
  for a clearly labeled design-review preview.
