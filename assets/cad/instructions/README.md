# Assembly records for future interactive instructions

Recorded 2026-09-24 for APS-II course dogfooding. The instructor wants students to
step through assembly and rotate the model to inspect each operation. These files
preserve the inputs.

**Viewer (2026-09-26):** the first interactive instructions are the APS page
`docs/ii/sesame-build/` (<https://aps.chibatech.dev/ii/sesame-build/>).
`../aps/scripts/export_sesame_build.py` reads the assembly and snapshot read-only and
writes meshes there, with the exact geometry of every visible part (D8).
The step sequence lives in that page's `js/steps.js`.

**Native model:** `../Sesame-S3-Assembly.FCStd` — one complete, self-contained
electronics assembly. The carrier's editable construction history is embedded
under the hidden `CarrierDesign` group. There is no second carrier/comparison file
to open or synchronize.

## Records and ownership

- [`converter-installation.json`](converter-installation.json): ordered physical
  operations, stable semantic part IDs, before/after states, inspection viewpoints,
  evidence and missing intermediate geometry. This is an authoring record, not an
  executable animation format or a complete electrical build guide.
- [`assembly-cad-snapshot.json`](assembly-cad-snapshot.json): read-only snapshot
  of the current native object bindings, transforms, dimensions, visibility and
  materials. Native GUI edits remain authoritative; refresh the snapshot after
  saving changes. It must never be used to overwrite the CAD automatically.
  Schema version 2 binds all records to the single `assembly` document; previous
  semantic IDs are unchanged, and additional `cad.<NativeName>` IDs cover the
  complete native hierarchy and hidden construction history.
- [`servo-hub-installation.json`](servo-hub-installation.json): detachable hub
  construction, symmetric long-on-both-sides male headers, added spacers and
  carrier-mounted female sockets. The hub reference is placed at confirmed socket
  addresses and flush-seated at a modeled 13.5 mm elevation (physical estimate
  approximately 14 mm); the detailed header/socket parts
  combine purchased male-pin dimensions with provisional socket geometry.
  Untrimmed upper ends project a modeled 2.15 mm, matching the instructor's
  approximately 2 mm measurement. The snapshot includes individual pins,
  original/donor spacers, female sockets, contacts, tails and solder.
- [`../../../reference/ELECTRONICS-CAD-SOURCES.md`](../../../reference/ELECTRONICS-CAD-SOURCES.md):
  dimensional evidence, model modifications and unresolved details.

In FreeCAD's **existing** Python console, after saving the assembly:

```python
import runpy
runpy.run_path('/path/to/sim2real/tools/export_instruction_snapshot.py')
```

The exporter refuses pending recomputations; save the document first, including
appearance-only edits. Commit the refreshed JSON together with related native
edits/scripts. Saved-file SHA-256 values identify the local disk artifacts; they
do not prove that live unsaved edits have been saved. The exporter only reads the
open document and writes the snapshot. It also supports headless execution using
FreeCAD GUI services under Xvfb; no mouse/keyboard automation is needed.

## Recorded physical sequence

1. Insert four male header pins **short end first from below the converter**,
   seating the black plastic against its underside.
2. Solder the short ends on the converter's top face.
3. Remove all four plastic spacers with pliers, leaving the metal pins in place.
4. Insulate the converter's underside with **three overlapping tape layers**,
   leaving the four corner terminal pads exposed.
5. Seat the converter's long pin ends in the carrier: **OUT− V1, OUT+ O1,
   IN− V17, IN+ O17**. Installed separation is approximately **0.5 mm**, including
   the tape, not an additional air gap.
6. Clip the long ends **flush with the carrier underside**.
7. Solder/fill those four carrier holes. The finished metal pins remain flush,
   while the solder mounds extend below them. Typical underside solder height is
   approximately **1 mm**, not a verified maximum for all joints.

Album photos 03–07 and the instructor's construction description support this
sequence. The record includes SHA-256 identities of those five downloaded images;
the images themselves remain in the local cache and album, not this repository.
Archive the authorized instructional images before relying on them as future
course illustrations. The three tape-layer operations are separate in the structured record
so they can be illustrated later; their individual footprints and thicknesses
have not been measured. Do not divide the 0.5 mm installed separation into three
claimed tape thicknesses.

## Preserve these distinctions when animating later

| Information | How it is retained |
|---|---|
| Physical part identity | Stable semantic IDs, ASINs where known, per-pin terminal and carrier address |
| CAD identity | Document path plus exact native object name; display labels are not identifiers |
| Placement | Parent relationships, local/global position and quaternion, units and datum conventions |
| Assembly order | Stable step IDs, dependencies and explicit state changes |
| Non-rigid operations | Clipping, solder addition and spacer removal are state/geometry changes, not just translation |
| Evidence | Instructor report vs. measured estimate vs. photo observation vs. reference CAD vs. assumption |
| Appearance | Separate materials/visibility for pins, solder, insulation, screw and carrier details |
| Student inspection | Suggested top/underside/side targets; orbit remains available rather than locking the camera |
| Uncertainty | Unmeasured values stay explicit; typical heights do not become guaranteed clearance limits |

**Do not flatten the assembly into one mesh.** Keep pin, solder, tape and component
IDs available for selection and highlighting. Preserve relative transforms and
record the conversion from CAD millimetres/Z-up to any future viewer's coordinates.
Export only records with `export_visible_geometry=true`: imported originals hidden after
height adaptation and Boolean source/cutter objects must not appear twice.
`effective_visible` includes container visibility, so the entire hidden carrier
history stays out of the rendered assembled result. `App::Link` records retain
their linked-object identities. Mesh individual visible objects, not their parent
containers as well. This keeps material/part selection and future exploded views
available without double-rendering geometry.

Record an explicit starting state for every step, so scrubbing or jumping backward
restores the correct assembly rather than trying to physically undo a solder joint.
Camera suggestions are presentation metadata, never changes to assembly datums.
No animation duration, exact tool trajectory, exploded offset or orbit limit has
been prescribed yet.

## Geometry still needed for intermediate steps

The current model represents the **finished installation**, not all construction
stages. Keep placeholders for:

- Uncut header pins and their original long/short lengths.
- Four removable plastic spacers and their dimensions.
- Cut-off pin scraps and optional plier/cutter/soldering-iron illustrations.
- Three separate tape patches, their overlaps and installation order/footprints.
- Unsoldered and partially soldered states, using staged visibility/geometry rather
  than showing the completed solder at every step.

Do not silently invent these as measured assets. Their absence does not prevent
recording the sequence or inspecting the finished assembly today.

## Reproducibility and future publication

The complete assembly and embedded carrier history are now stored together in
`assets/cad/Sesame-S3-Assembly.FCStd` through Git LFS. The old source-document
hashes survive in the native `AssemblyMetadata` object and snapshot. The native
model contains the imported component geometry, not external file links.

Redistribution of the imported converter and uploaded hub/S3 geometry was confirmed
by the instructor on 2026-09-26 (DECISIONS.md D8).

Reconstruction scripts, in order, are `preview_converter_candidate.py`,
`refine_converter_candidate.py`, and `add_converter_pins.py` under `tools/cad_history/`.
They are one-time construction aids; they do not reproduce arbitrary later GUI
edits. The native saved document plus refreshed snapshot are the current record.
