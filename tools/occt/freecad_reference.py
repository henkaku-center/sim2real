"""FreeCAD reference for the Node/OCCT port: the variant geometry stage of
v3_assembly_cad.build() (widening, lengthening, transplanted bays) run with the
real functions on the normalized V3 references. Writes reference-variant-geometry.json.

PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib:. QT_QPA_PLATFORM=offscreen \
  /Applications/FreeCAD.app/Contents/Resources/bin/python tools/occt/freecad_reference.py
"""
import json
from pathlib import Path

from tools import v3_assembly_cad as cad

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('reference-variant-geometry.json')


def record(shape):
    b = shape.BoundBox
    return {'volume_mm3': shape.Volume, 'bounds_mm': [[b.XMin, b.YMin, b.ZMin], [b.XMax, b.YMax, b.ZMax]],
            'valid': shape.isValid(), 'closed': shape.isClosed(), 'solids': len(shape.Solids)}


def variant_stage(params):
    _, ref = cad.load_references()
    variant = params.get('variant') or {}
    h = variant.get('widen_mm', 0) / 2
    legs = variant.get('middle_legs')
    if h:
        for name in ['frame', 'bottom', 'head', 'lid']:
            ref[name] = cad.stretch_y(ref[name], variant['stretch_plane_y_mm'], variant['widen_mm'],
                                      refine=name in ('head', 'lid') and not legs)
    if legs:
        L = legs['lengthen_mm']
        for name in ['frame', 'bottom']:
            extended = cad.extend_x(ref[name], legs['body_plane_x_mm'], L)
            ref[name], _ = cad.transplant_bays(ref[name], extended, legs['bay_x_range_mm'], legs['bay_shift_mm'],
                                               legs['bay_y_limit_mm'] + h)
        for name in ['head', 'lid']:
            ref[name] = cad.extend_x(ref[name], legs['head_plane_x_mm'], L)
    return {name: record(ref[name]) for name in ['frame', 'bottom', 'head', 'lid']}


designs = {}
for design in ['internal-frame-s3', 'internal-frame-s3-two-eyes', 'internal-frame-s3-two-eyes-six-legs']:
    params = json.loads((ROOT / 'assets/printing' / design / 'params.json').read_text())
    print(design, flush=True)
    designs[design] = {'params': params.get('variant'), 'parts': variant_stage(params)}
OUT.write_text(json.dumps({'source': 'FreeCAD, tools/v3_assembly_cad.py variant stage',
                           'script_sha256': cad.sha(ROOT / 'tools/v3_assembly_cad.py'), 'designs': designs},
                          indent=2, sort_keys=True) + '\n')
print('wrote', OUT)
