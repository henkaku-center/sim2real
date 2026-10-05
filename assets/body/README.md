# S3 body — parametric design and generated v1

**Start with [`reference/BODY-CAD.md`](../../reference/BODY-CAD.md).**

- `params.json`: dimensions, clearances, print/check settings and evidence labels.
- `frozen-inputs.json`: upstream frame/cover/leg and leg-print-set identities.
- `v1/`: generated per-part STEP/STL/3MF, native electronics STEP reference,
  assembled STEP preview, assembly bindings, machine-readable collision report,
  and several PNG views plus an exploded view and leg-sweep preview.

Regenerate with `uv run python tools/check_body.py`. A nonzero status means read
the report and iterate; exporting a file is not fit acceptance. The current v1
is **DRAFT / NEEDS-HARDWARE**, with explicit assumptions and a measurement table.
The workflow never changes the authoritative FCStd or the fixed leg templates.

STL/STEP: millimetres in the existing torso-local x-forward/y-left/z-up frame.
3MF: individual parts in their documented print orientation, on the print bed;
these are generic geometry packages, **not pre-sliced Bambu machine profiles**.
See `v1/assembly.json` for transforms, part IDs and ordered guide steps.

License: repository Apache-2.0; frozen Sesame reference shapes retain upstream
Apache-2.0 provenance (`assets/cad/licenses/sesame-Apache-2.0.txt`). Imported native
electronics redistribution is cleared by DECISIONS.md D8. No external publication
is part of this workflow.
