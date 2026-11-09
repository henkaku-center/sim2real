# FreeCAD-free CAD kernel (OpenCascade WebAssembly)

`kernel.mjs` wraps the OpenCascade calls the printing pipeline uses, through
[`replicad-opencascadejs`](https://www.npmjs.com/package/replicad-opencascadejs)
(OCCT built to WebAssembly, LGPL-2.1). It runs in Node or a browser; no FreeCAD install.

```sh
cd tools/occt && npm ci && npm test   # parity with FreeCAD on base, two-eye and six-leg designs
```

## Status: phase 1 of the port

- **Ported:** the variant stage of `tools/v3_assembly_cad.py` (`stretch_y`, `extend_x`,
  `transplant_bays`) with the same prismatic-cut and volume-conservation checks, in `variants.mjs`.
- **Parity:** `parity.test.mjs` compares each part's volume (1e-5 relative), bounds (1 µm), validity and solid count
  with `reference-variant-geometry.json`, written by FreeCAD running the real functions
  (`freecad_reference.py`). Regenerate it whenever `v3_assembly_cad.py`'s variant code changes.
- **Kernel difference handled:** this OCCT build can leave zero-volume internal sheets at translation seams inside an
  otherwise correct solid; FreeCAD's OCCT 7.8.1 removes them. `singleSolid()` keeps only enclosing shells. The volume
  check still rejects valid results that lost material.

## Remaining phases

1. Feature finding (`cylinders`, `frame_layout`, `windows`, `lower_entries`): needs per-face surface data
   (cylinder centre and radius), already reachable through `BRepAdaptor_Surface`.
2. `fit_frame` and `fit_head` (PCB holes, spacers, head fit, display windows) and the validation checks. The pipeline
   uses point-in-solid tests (`isInside`), which this npm build does not bind (`BRepClass3d_SolidClassifier`), nor
   `ShapeFix_Shape`. Options: a custom opencascade.js build listing exactly these classes, or ray/distance tests.
3. Outputs (STEP, STL, `assembly.json`) compared with the committed FreeCAD outputs, then switch CI and retire FreeCAD.
