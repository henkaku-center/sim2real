# Human / agent mechanical CAD co-design

**Current opening workflow (2026-09-24):** use `tools/open_cad.FCMacro` or open
[`assets/cad/Sesame-S3-Assembly.FCStd`](../assets/cad/Sesame-S3-Assembly.FCStd)
in FreeCAD 1.1.3+. The complete electronics and editable carrier now share one
document. See [CAD layout and instruction-authoring workflow](../assets/cad/README.md).

Research and recommendation: **2026-09-23**. Software selection below is a proposal,
not an instructor-approved replacement of the existing simulation asset pipeline.

## Recommendation

**2026-09-24 follow-up:** preserve stepwise assembly information for future animated,
freely rotatable APS-II student instructions. This is a data-recording decision;
viewer/animation implementation is deferred. The [authoring records](../assets/cad/instructions/README.md)
retain ordered actions, semantic identities, native bindings, before/after states,
evidence and missing intermediate geometry. Keep these distinct from finished-part
geometry and update snapshots after saving native edits.

Use **FreeCAD as the main interactive mechanical design environment**, with its
Python API/macros for agent-driven operations on the same document. Add an MCP
bridge when live document inspection and GUI feedback are needed. Start with the
downloaded Sesame STEP assembly; retain the original Fusion archive.

This recommendation prioritizes a human's ability to edit sketches, dimensions,
features and assembly relationships while an agent inspects and changes the same
objects programmatically. It avoids making Python source editing the only way a
human can change a design. FreeCAD has a learning curve; this is a workflow-fit
recommendation, not a claim that its UX is more polished than every commercial CAD
application.

## Comparison

| Tool | Human workflow | Agent workflow | Role here |
|---|---|---|---|
| FreeCAD | Sketches, feature tree, constraints, property editor, assembly workbench | Python console, macros, document objects; community MCP bridges | Recommended shared mechanical design environment |
| build123d | Python editor with interactive geometry viewer; documented VS Code/browser viewers | Python B-rep modeling, parameterized construction, STEP interchange | Good candidate for code-owned component families and batch variants |
| CadQuery | Code-first modeling with separate GUI/viewer options | Python/OpenCascade, STEP import/export, script-based generation | Strong alternative for component generators; useful existing electronics ecosystem |
| OpenSCAD | Script editor, preview, parameterized CSG construction | Text source and command-line generation | Useful for simple fixtures; less aligned with this STEP-based assembly and direct GUI editing goal |

Keep Blender's existing role in visual/simulation asset preparation. A CAD workflow
should export geometry for that pipeline rather than replace dynamics or visual
asset conventions. Fusion source files are valuable upstream references, but Fusion
is not the proposed open-source authoring environment.

## The crucial interchange boundary

STEP is a solid-geometry/assembly interchange format in this workflow, **not a
round-trip transport for Fusion's or FreeCAD's feature history**. Imported solids
can be measured and used as the base for new features, but import does not recreate
the original driving sketches and constraints. Likewise, a build123d/CadQuery STEP
export does not become its Python construction history inside FreeCAD.

Use one clear source of truth per component:

- **Human/agent shared FreeCAD parts:** native document objects, constrained sketches
  and named properties are authoritative. Python macros incrementally edit them;
  agents first read the current state so human edits survive. Export parameter and
  geometry summaries for review; do not silently regenerate the document from an
  older script or a conflicting JSON copy. Track native documents through Git LFS.
- **Code-generated library parts:** Python plus parameter data is authoritative.
  FreeCAD consumes their generated solids; changes to the family go back to its
  source parameters/code. Do not imply arbitrary GUI edits propagate back to Python.
- **Imported purchased/upstream parts:** immutable pinned baseline plus a documented
  derived model. Reconstruct important features only where dimensions must change.

For our robot, expose practical names such as `CarrierWidth`, `CarrierLength`,
`PCAStackHeight`, `USBPlugClearance` and `BatteryCableExit`. Record units, tolerance,
source and measurement status. Unknown stack heights remain unresolved parameters,
not invisible nominal assumptions. The scene should distinguish solid geometry,
motion envelopes, cable routes and insertion/removal space.

## Agent interface

FreeCAD's Python object API is the modeling interface; **MCP is a transport layer**
that can let an agent query/edit the live application and obtain feedback.
Community implementation evaluated at README level:
[neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp).
It documents an addon inside FreeCAD plus a separate MCP server, document inspection,
Python execution and screenshots. It is not a FreeCAD-core protocol, and was not
installed or tested here. Its installation and macOS/Linux behavior must be checked
before adopting it for course use.

Proposed edit loop:

1. Inspect document objects, parameters, placement and the user's current selection.
2. Apply a small named change through native features/properties in an undoable
   document transaction; preserve manually authored objects.
3. Recompute, check shape validity, measure bounds and inspect relevant clearances.
4. Review a viewport image and numerical report together. For moving parts, check
   the required range of configurations rather than one static pose.
5. Save the native design and commit the script/parameter changes and asset revision.

Plain Python macros are enough to start; an MCP integration need not block initial
model inspection. Neither a successful tool call nor a convincing rendered image
alone proves dimensions, assembly constraints or mechanical clearance are correct.

## Immediate starting point

[Downloaded assets and integrity checks](../assets/cad/README.md): original Sesame
STEP/Fusion assembly and three Adafruit reference components, with pinned retrieval
manifest. Next CAD session should import the STEP into FreeCAD, inspect the actual
assembly hierarchy and transforms, compare frame/leg geometry to the existing
simulator, and replace old S2/SG90/power geometry with verified S3-build components.

The existing joint/calibration manifest remains canonical for simulation; no new
physical calibration or component fit is implied by downloading a CAD assembly.

## Primary sources reviewed

### Follow-up: fengyuGbt/freecad-ai

Reviewed README, repository tree, `modeling.py` and `agent.py` at commit
`944fc5279d7077af6206f0b64df4be75640e98c5` on 2026-09-23:
[repository](https://github.com/fengyuGbt/freecad-ai).

Useful patterns: named modeling operations, object references by name, numeric
argument handling, and feedback containing volume/bounds after a geometry operation.
Its semantic-tool examples support keeping complex geometric construction inside
ordinary code rather than requiring an LLM to invent long coordinate arrays.

It is a headless Python modeling/agent-loop project, not the live GUI MCP bridge
we discussed. README's verified environment is Windows FreeCAD 1.0.2; that is not
evidence of a tested macOS course workflow. Sketch/constraint repair and assembly
integration are listed as roadmap work. Its fillet/chamfer helpers explicitly
return non-parametric `Part::Feature` objects, so they are not a solution for
preserving interactive feature history throughout a model.

The cut-quality heuristic flags removal of less than 90% of the cutting tool's
volume; this can flag legitimate through-cuts whose tools extend beyond a part.
Use design-specific geometric assertions rather than adopting that heuristic as
a general correctness test. The reviewed source also resolves every matching
string argument as an object, not only object-reference parameters; a name
argument can therefore be misinterpreted. These are source-review observations,
not results of executing the package.

README says **license TBD** and the inspected tree has no LICENSE. Recommendation:
treat it as a useful research reference, not a dependency to vendor into this repo.
No package installation, code copying or external LLM calls were made. Our import
and audit scripts use FreeCAD's own API directly.

### Local implementation status

The installed FreeCAD 1.1.3 imported all four STEP models, saved native documents,
reopened them for inspection and displayed the Sesame working assembly in the GUI.
See [import results](../assets/cad/README.md#freecad-import-and-inspection).
The working file retains upstream geometry and an empty S3-component group with
build provenance; it does not yet position measured electronics. Python-driven
document access is proven locally; a live MCP bridge remains uninstalled.

- [FreeCAD features](https://www.freecad.org/features.php): native parametric properties,
  Python API, built-in assembly workbench, sketches and STEP support.
- [CadQuery introduction](https://cadquery.readthedocs.io/en/latest/intro.html): Python
  modeling, OpenCascade/OCP, separate GUIs and STEP import/export.
- [build123d documentation](https://build123d.readthedocs.io/en/latest/): Python B-rep
  modeling; [external tools](https://build123d.readthedocs.io/en/latest/external.html)
  documents VS Code and browser viewers.
- [OpenSCAD about](https://openscad.org/about.html): code-first CSG/extrusion workflow.
- [FreeCAD MCP](https://github.com/neka-nat/freecad-mcp): third-party live-app bridge.
- Original Sesame CAD README and native/STEP metadata are retained with the downloads.
