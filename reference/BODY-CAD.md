# Agent-editable Sesame S3 body

**v1 is a clearance-first engineering draft, not a print-approved robot.**
The native S3 circuitry is authoritative; the body is generated from text.
Read [`assets/body/v1/report.json`](../assets/body/v1/report.json) before using a
render or STL. Measurement assumptions do not disappear when numerical tests pass.

## Pipeline choice

Use **scripted FreeCAD `Part` / OpenCascade**, with JSON parameters and a separate
uv-locked Python runner. Motion queries use FCL triangle BVHs plus containment
checks; static nearby body/component pairs use OCC solid distance/intersection.
`tools/body_cad.py` is the body design source;
`assets/body/params.json` is its editable parameter set. No mouse operations,
GUI document state, Python proxies stored inside FCStd, network downloads, or
hand edits to generated triangles are needed to regenerate a body.

| Candidate | Assessment for this repository |
|---|---|
| FreeCAD scripted — selected | Reads the authoritative native assembly and its placements without a second CAD runtime. Existing saved-model checks already use it. `Part` booleans/distance give solid interference checks; STEP/STL exports are native. Human inspection can still use FreeCAD. |
| CadQuery | Good code-first OpenCascade alternative with macOS/Linux installation and STEP import/export. Adds an OCP environment plus a FreeCAD export boundary; it does not make the native circuitry's construction history editable. |
| build123d | Good Python/OpenCascade alternative, especially explicit algebraic part composition. Same extra native-export boundary here. No body requirement justifies maintaining both kernels in v1. |

Upstream technical references inspected: FreeCAD's official **Features** and Python
scripting documentation; CadQuery **Installing CadQuery**; build123d **Installation**.
All three are viable; this is a repository-integration choice, not a claim that
FreeCAD is universally better for agent CAD.

### Authority and reproducibility

- **Electronics:** `assets/cad/Sesame-S3-Assembly.FCStd`, read-only. Effective leaf
  visibility and semantic/native IDs come from `assembly-cad-snapshot.json`.
  The exporter rejects a stale snapshot; containers are not double-counted.
- **Body:** JSON parameters + Python operations. Deterministic operation order,
  tessellation tolerances, fixed ZIP timestamps and normalized STEP timestamps.
- **Interfaces:** frozen upstream frame, bottom cover, eight leg meshes and leg
  print plate have SHA-256 identities in `assets/body/frozen-inputs.json`.
  A body edit may not resize servo pockets or move leg mounts. V1 retains the
  entire original frame and bottom, including the old unused electronics features.
- **Units:** generated STEP/STL are assembly-coordinate **millimetres**,
  x-forward/y-left/z-up about the existing simulator torso origin. The upstream
  mapping is `(x,y,z) = (26-upstream.x, upstream.z, upstream.y-17)`.
  Multiply by `0.001` to render in a metre-based viewer. Individual 3MF files
  contain their documented **print orientation**, translated onto the bed.
- **Kernel versions:** local FreeCAD **1.1.3**, Python **3.11.14**, OCCT **7.8.1**.
  Conda-forge offers FreeCAD 1.1.3 for Linux x86-64/aarch64 and macOS Intel/ARM;
  its current builds use OCCT 7.9.3. Cross-kernel triangulation/STEP bytes may
  differ. Numerical geometry tolerances, not cross-platform byte equality, are
  the contract; the report records the runtime. Linux parity requires CI evidence.
- `uv.lock` pins numpy, trimesh, scipy, rtree, Pillow and pytest. The body checker
  adds **python-fcl 0.7.0.11** (FCL 0.7) to the dev dependency group. PyPI publishes
  CPython 3.12 wheels for macOS Intel/ARM and Linux x86-64/aarch64; the Intel Mac
  wheel was installed and exercised here. This is not a core simulation dependency.

## V1 construction

The original frame and leg templates are unchanged. Four risers use the old PCB
attachment bores, whose centers were fitted to the STL's 24-vertex bore rings.
A raised carrier tray provides four standoffs aligned to the **native carrier's
four corner bores**, an under-carrier battery drawer, and servo-wire channels.
The front risers have low attachment feet and inset tall columns: straight
columns at the old front PCB bores were caught by the hip sweep. Short M1.6
screws attach those feet before the tray is installed. Countersunk tray screws
remain flush below the battery drawer (front M2.5; rear long M1.6, lengths to
verify). The frame bores and servo pockets themselves are unchanged.
The drawer retains the battery with a removable hook-and-loop strap and a
screw-retained front flange. Remove the flange screws, disconnect the battery,
and pull the drawer in +X; the circuit need not be removed.

The face cover includes OLED edge rails, a window, a rear toggle hole and a
USB-C service opening located from the actual native S3 shell. The OLED slides
into its rails from the underside; a removable tape stop retains the open end.
The switch uses its own threaded bushing and nut. Four long cover screws enter
tray bosses outside the electronics outline. Fastener engagement, structural
stiffness, purchased servo variants and harness routing await hardware review.
The eight servo channels are open at the tray/cover seam, so wires can be laid
in before closing; bulky servo plugs need not be threaded through small holes.

The tall riser layout is intentional for this first collision-screening draft:
it retains the complete fixed leg interface while placing the larger electronics
and battery above the leg workspace. It raises center of mass considerably.
A shorter body should be a subsequent parameter/design iteration informed by
the report, not an unverified reduction of leg travel or pocket dimensions.

### How an agent changes the body

1. **Edit params.** Change `assets/body/params.json`; keep evidence/status fields
   beside assumptions. For a new construction feature edit `tools/body_cad.py`.
   Never save over the native electronics or modify the frozen templates.
2. **Run checks.** From the repo root:

   ```sh
   uv sync --locked
   git lfs pull --include='assets/cad/Sesame-S3-Assembly.FCStd,assets/stl/upstream/*,assets/print/sesame-legs-set.3mf'
   uv run python tools/check_body.py
   uv run pytest tests/test_body_cad.py -q
   # Full acceptance test; deliberately fails if the draft still has fit defects:
   BODY_CAD_ACCEPTANCE=1 uv run pytest tests/test_body_cad.py -q
   ```

   On macOS the runner finds `/Applications/FreeCAD.app/.../bin/python` and sets
   the supplied library path automatically. On Linux, or a different install:

   ```sh
   export FREECAD_PYTHON=/path/to/freecad-environment/bin/python
   # Only if FreeCAD modules are outside that interpreter's default search path:
   export FREECAD_LIB=/path/to/freecad-environment/lib
   uv run python tools/check_body.py
   ```

   `--params FILE --output DIRECTORY` supports experiments without replacing v1.
   `--skip-rom` is a diagnostic shortcut and can never produce an accepting report.
   `--require-release` additionally rejects outstanding hardware measurements.
   Do not treat an exit code of 1 as an exporter failure: read the JSON findings.

3. **Read the report.** Start with `status`, `summary`, then failing pair rows.
   `distance_lower_bound_mm` is conservative AABB separation; nearby pairs use
   exact OCC `distToShape`/`common`. `intersection_mm3` above the configured
   threshold is a failure even for a named intended contact. Face contact is
   permitted only for recorded mating pairs, never as a blanket collision waiver.
4. **Inspect renders.** Open `assets/body/v1/index.html`, `assembled.png`,
   `top-open.png`, `front.png`, `rear.png`, `exploded.png`, and `rom-sweep.png`.
   Colors and IDs distinguish new body, native electronics and reference envelopes.
5. **Iterate.** Repair collisions before shortening the risers or reducing wall
   thickness. Update assumptions after measurement. Rebuild exports and rerun
   checks; commit source, exported geometry, report and handoff together.

### What the checks do — and do not prove

- Every body part against every native visible electronics leaf, battery, switch,
  OLED, eight servo-case proxies, eight horns and swept external wire envelopes.
  Body/body interference is checked too. The native source's internal soldered
  joints are not reinterpreted as enclosure collisions.
- Minimum-clearance thresholds, with deliberate surface contacts recorded.
- Single valid solid per printed part; mesh closure and winding; sampled wall
  thickness using inward face-centroid rays. The latter is **not a proof of the
  global minimum thickness**: small slivers/edge features can be missed. Sampling
  coverage and thin locations are included. Frozen upstream thin features are
  reported, not silently excused or thickened.
- Overhang area after the declared print orientation; build-volume fit for a
  256 × 256 × 256 mm P1S. Downward bridge surfaces are conservatively reported.
  **This is not a slicer**: supports, bridging, bed contact, layer adhesion and
  print quality require Bambu Studio inspection. Prefer supports only on the
  face cover; the report reveals where that target is not yet met.
- Each joint across the manifest soft range at ≤5° increments with the other
  joint at rest, plus coupled endpoint/midpoint poses. Both links move with the
  hip; the lower link also rotates at the foot. The exact printed leg meshes are
  checked against each body part using FCL mesh BVHs plus containment queries.
  The 0.1 mm body tessellation allowance is added to the clearance threshold.
  Foot-servo and horn proxies move with their links too. This is a **sampled sweep**, not a continuous
  collision proof or exhaustive two-joint configuration-space search.
- Carrier screws are intersected with actual native carrier material; pilot
  holes and support seating are tested geometrically. Frame anchors are checked
  against the original bores. Strength/thread pull-out is not inferred.
- The report preserves uncertainty: servo/horn stand-ins are screening volumes,
  not validated purchased MG90S variants. Wire-route endpoints/bends, peripheral
  envelopes and legacy kinematic registration require physical confirmation.

## To measure tomorrow — 2026-10-07

No owner input is needed to generate v1 tonight. These are the measurements that
turn the evidence-based draft into a physical-fit decision. **Power off and
disconnect the battery before taking mechanical measurements.**

| Item / parameter | Value used tonight and evidence | Exactly what to measure | Tool |
|---|---|---|---|
| Battery `battery.size_mm` | **51 × 28 × 14 mm**, B0F3JB59B6 listing recorded in `ELECTRONICS-CAD-SOURCES.md` | Maximum length, width, thickness including wrap; use light contact, do not squeeze the pack | Ruler; calipers with light contact if safe |
| Battery exit and connector | Assumed **12 × 8 × 5 mm** connector; 1 mm pack padding | Which pack face the leads exit; exit center from two adjacent edges; connector body's three maximum dimensions | Ruler for exit offsets; calipers for disconnected plastic connector |
| Battery service slack | Proposed route only | Free lead length from pack to connector; distance needed to pull drawer out far enough to unplug, with relaxed cable bend | Ruler |
| Toggle body `switch.body_size_mm` | **13 × 8 mm** listing footprint; **10 mm** rear depth assumed; listing gives 33 mm overall / 10 mm lever | Plastic body L/W; distance from panel seating face to deepest terminal, including solder/insulation | Calipers |
| Toggle bushing and hole | **6 mm** thread, **6.8 mm** hole assumed | Thread major diameter; usable threaded length after nut/washer; nut across flats/corners; washer OD | Calipers |
| Toggle lever envelope | **10 mm** lever from listing; provisional sweep sphere | Lever length from pivot and maximum lateral excursion in both positions; lever clearance from surrounding surface | Ruler, calipers for lever length |
| OLED board | **25.4 × 26.1 mm** listing XY; **1.6 mm** thickness assumed | PCB width/height/thickness and maximum rear component/solder/header depth | Calipers |
| OLED face | **23 × 12 mm** window, **2 mm** glass depth assumed; listing marks 11 mm display height | Glass outer dimensions, visible active area, active-area offsets from PCB edges, glass height above PCB | Calipers; ruler for active-area offsets without touching glass |
| OLED cable/retention | Rails and tape stop, 5 mm rear envelope assumed | Header orientation, plug depth/width, cable exit side, unobstructed PCB edge available for rails | Calipers |
| S3 USB plug | Native shell datum; **12 × 7 × 35 mm** insertion envelope assumed | Actual flashing cable plug width/height; rigid length from metal tip to flexible strain relief; test straight insertion line | Calipers for plug; ruler for service length |
| Carrier holes | Native **2 mm** diameter, **2 mm X / 1.8 mm Y** insets, instructor estimates | Hole diameter; hole-center spacing along both edges; underside solder maximum below PCB; maximum installed top height | Calipers, derive center spacing from outside-to-outside minus hole diameter |
| MG90S family and horns | Nominal screening envelopes, not purchase-variant certification | Case L/W/H; mounting-tab span and hole centers; shaft center to case edges; horn radius/thickness; full lead-exit envelope for each installed brand | Calipers |
| Servo wiring | **2 mm** bundle radius, **0.8 mm** channel allowance assumed | 3-wire bundle diameter, plug maximum width/height, free lead length, relaxed bend radius, exit side at each servo | Calipers for cross sections; ruler for lead/bends |
| Frame anchors/fasteners | Old PCB bore centers fitted to upstream STL, nominal 1.75 mm bores; inset front columns with separate M2.5 top screws | Available bore depth, short M1.6 foot-screw engagement, M2.5 top engagement, long rear M1.6 length, countersunk head diameter/height; tray/riser compression and rocking after assembly | Calipers; ruler for long fastener length |
| Leg registration | Existing sim datum/signs, not new physical calibration | With horns centered by the existing supervised workflow, compare hip centers and neutral leg position to the mesh preview; measure center spans and frame offset | Ruler (calipers for accessible shaft centers) |

Inventory is a research source, not a runtime dependency. No private order/account
details are copied into this public body handoff.

## APS guide handoff: “place circuit in body”

The body guide must read `assets/body/v1/assembly.json` and
`assets/body/v1/report.json`, not infer fit from a thumbnail. Export paths:

- `assets/body/v1/interface-frame.{step,stl,3mf}`
- `assets/body/v1/bottom-cover.{step,stl,3mf}`
- `assets/body/v1/riser-{1,2,3,4}.{step,stl,3mf}`
- `assets/body/v1/carrier-tray.{step,stl,3mf}`
- `assets/body/v1/battery-drawer.{step,stl,3mf}`
- `assets/body/v1/face-cover.{step,stl,3mf}`
- `assets/body/v1/electronics-reference.step` — native carrier coordinates
- `assets/body/v1/assembled-preview.step` — assembled millimetre coordinates

All part STEP/STLs already share the torso frame. The JSON gives the native
electronics translation/quaternion, stable `body.*` IDs, native electronics
bindings, fastener datums, wire polylines and six ordered installation steps.
Use the same native assembly meshes already exported by the APS guide, apply
the recorded electronics transform, then animate downward placement onto the
standoffs. The exploded review lifts the cover/electronics and pulls the drawer
outward; it is not a change to assembly coordinates. Keep optional guide section
**C hidden until geometry and physical fit are accepted**, as coordinated with
the guide agent. Preliminary renders may be shown as explicitly labeled design
review, not student assembly instructions.

## MuJoCo follow-up

Do not hand-edit generated `models/sesame.xml`. This tall draft materially changes
torso mass distribution, inertia, ground collision geometry and stability. A
mesh-only swap plus guessed scalar mass would hide those changes. After fit:

1. Weigh each new print and the complete torso; record battery/electronics masses.
2. Use generated mm-to-m meshes and volume/infill-informed mass estimates only
   as explicit placeholders, then replace them with measured mass/COM/inertia.
3. Update `sim/build_mjcf.py` and the asset generation path, preserving manifest
   joints/signs/ranges and the fixed leg datums.
4. Regenerate MJCF/browser assets and rerun deterministic, behavior and browser
   tests. Check COM/stability before any physical gait trial.
