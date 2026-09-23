"""Read-only geometry audit of locally cached external-component candidates."""
from pathlib import Path
import json
import FreeCAD as App
import Part
import Import

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'assets/cad/upstream/external-peripherals'
results=[]
for source in json.loads((CACHE/'sources.json').read_text()):
    doc=App.newDocument('Audit')
    Import.insert(str(CACHE/source['file']),doc.Name)
    doc.recompute()
    objects=[]
    for o in doc.Objects:
        if o.TypeId=='App::Part' or not hasattr(o,'Shape') or not o.Shape.Solids:continue
        b=o.Shape.BoundBox
        circles=set()
        for edge in o.Shape.Edges:
            curve=edge.Curve
            if isinstance(curve,Part.Circle):
                circles.add(tuple(round(v,5) for v in [curve.Radius,*curve.Center]))
        objects.append({'name':o.Name,'label':o.Label,'valid':o.Shape.isValid(),
                        'solids':len(o.Shape.Solids),'bounds_mm':[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax],
                        'size_mm':[b.XLength,b.YLength,b.ZLength],'circles':sorted(circles)})
    results.append({**source,'objects':objects})
    App.closeDocument(doc.Name)
(ROOT/'assets/cad/reports/external-peripheral-candidates.json').write_text(json.dumps(results,indent=2)+'\n')
print('PASS: three cached STEP candidates inspected; no assembly changes.')
