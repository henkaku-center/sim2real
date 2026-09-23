"""Apply instructor-confirmed centred S3 pins and photo-confirmed gold pads."""
from pathlib import Path
import FreeCAD as App

ROOT=Path(__file__).resolve().parents[1]
doc=next(d for d in App.listDocuments().values() if d.FileName.endswith('/LM2596-comparison.FCStd'))
doc.openTransaction('Confirm long centred S3 headers and gold pad finish')
try:
    p=doc.S3Installation
    p.MaleMatingLength=6.25
    p.MaleSolderLength=6.25
    p.Evidence += ' Instructor explicitly confirms long centred male headers, soldered with upper ends retained for expansion. PENGLIN B0FJ5NR96F nominal 15 mm metal length, 6.25 mm each side of a 2.5 mm spacer used as reference; installed brand unconfirmed. New S3 photo confirms black solder mask, gold terminal pads, silver USB shell and red antenna.'
    p.addProperty('App::PropertyString','HeaderEvidence','Evidence') if 'HeaderEvidence' not in p.PropertiesList else None
    p.HeaderEvidence='Long centred/untrimmed is instructor-confirmed. Nominal 15 mm and 6.25 mm exposed ends from purchased PENGLIN reference; modeled 0.6 mm square pin section provisional to fit uploaded 0.9 mm bores.'
    pcb=doc.S3Source_Part__Feature030
    materials=[]
    for material in pcb.ViewObject.ShapeAppearance:
        rgb=tuple(material.DiffuseColor)[:3]
        if all(abs(a-b)<.001 for a,b in zip(rgb,(.76,.77,.79))):material.DiffuseColor=(.88,.66,.26)
        materials.append(material)
    pcb.ViewObject.ShapeAppearance=materials
    doc.recompute()
    for o in doc.Objects:
        if o.Name.startswith('S3MalePin_'):
            assert abs(o.Height.Value-15)<1e-7
            assert o.Shape.isValid()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction();raise
doc.recompute();doc.save()
print('PASS: S3 uses 15 mm centred untrimmed pins; gold PCB pads match supplied photo.')
