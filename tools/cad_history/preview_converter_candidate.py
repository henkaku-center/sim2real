"""Compare the pinned YAAJ converter in the existing FreeCAD GUI.

Run with runpy.run_path from FreeCAD's Python console. The comparison document
is saved in the ignored upstream cache; the authoritative circuitry is untouched.
Imported STEP faces are reference geometry, not native parametric features.
"""
from pathlib import Path
import hashlib
import json
import urllib.request
import zipfile

import FreeCAD as App
import FreeCADGui as Gui
import ImportGui
import Part
from PySide import QtCore

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'assets/cad/upstream/lm2596-yaaj'
REVISION = '82e7b5806c70ca289d5c9fb9ed6e5a2209b806d2'
URL = ('https://raw.githubusercontent.com/yet-another-average-joe/'
       f'KiCad-Chinese_Modules/{REVISION}/DCDC_StepDown_LM2596/'
       'Packages3D/YAAJ_DCDC_StepDown_LM2596.zip')
SHA256 = 'd8a7836b10bd3a2ca68ff85d6a6060c038f0c991fc9c01d57ccc444d6c3428ee'
STEP = 'YAAJ_DCDC_StepDown_LM2596_cp.step'


def copy_carrier_finish(source, doc):
    """Copy all visible carrier finishes as geometry snapshots, in local axes."""
    rings = [o for o in source.Objects if o.Name.startswith(('Pad_Top_', 'Pad_Bottom_'))]
    capsules = [o for o in source.Objects if o.Name.startswith(('EdgePad_Top_', 'EdgePad_Bottom_'))]
    labels = list(source.SurfaceLabels.Group)
    assert (len(rings), len(capsules), len(labels)) == (864, 64, 42)
    for name, objects, style in [('CarrierRings', rings, source.PadRing.ViewObject),
                                 ('CarrierCapsules', capsules, source.PadRing.ViewObject),
                                 ('CarrierLettering', labels, labels[0].ViewObject)]:
        if doc.getObject(name):
            raise RuntimeError(f'{name} already exists; preserve comparison edits.')
        obj = doc.addObject('Part::Feature', name)
        obj.Label = f'{name} — {len(objects)} copied features'
        obj.Shape = Part.makeCompound([o.Shape.copy() for o in objects])
        obj.ViewObject.ShapeAppearance = style.ShapeAppearance
        obj.ViewObject.LineColor = style.LineColor
        obj.ViewObject.LineWidth = style.LineWidth
        obj.ViewObject.DisplayMode = style.DisplayMode
        if name == 'CarrierLettering':
            obj.ViewObject.LineColor = (0.65, 0.85, 0.55)
            obj.ViewObject.LineWidth = 1.0
            obj.ViewObject.DisplayMode = 'Wireframe'
        assert abs(obj.Shape.Volume - sum(o.Shape.Volume for o in objects)) < 1e-7
        obj.addProperty('App::PropertyString', 'Evidence')
        obj.Evidence = 'Geometry snapshot from authoritative circuitry; edit original native features there.'
    doc.recompute()
    print('PASS: copied 864 rings, 64 capsules and 42 outlined labels.')


def main():
    source_path = ROOT / 'assets/cad/work/Sesame-S3-circuitry.FCStd'
    source = next(d for d in App.listDocuments().values()
                  if d.FileName == str(source_path))
    if any(d.FileName == str(CACHE / 'LM2596-comparison.FCStd')
           or d.Name == 'LM2596_Comparison' for d in App.listDocuments().values()):
        raise RuntimeError('Comparison already open; preserve edits and inspect it.')
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / 'module.zip'
    if not archive.exists():
        archive.write_bytes(urllib.request.urlopen(URL, timeout=30).read())
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == SHA256
    with zipfile.ZipFile(archive) as z:
        (CACHE / STEP).write_bytes(z.read(STEP))

    doc = App.newDocument('LM2596_Comparison')
    doc.Label = 'LM2596 candidate — capacitor height NOT validated'
    ImportGui.insert(str(CACHE / STEP), doc.Name)
    imported = list(doc.Objects)
    roots = [o for o in imported if not o.InList]
    module = doc.addObject('App::Part', 'CandidateModule')
    module.Label = 'YAAJ reference — exact pin spacing; different capacitors?'
    for obj in roots:
        module.addObject(obj)
    for name, text in {
        'SourceURL': URL, 'Revision': REVISION,
        'Status': 'Candidate only. Trimmer top 13.036 mm; capacitors 14.3 mm above PCB underside.',
        'LicenseStatus': 'No license located in upstream tree or root README; local comparison only.',
        'Evidence': 'Pin locations and ~0.5 mm insulated separation from instructor; outline from candidate CAD.',
    }.items():
        module.addProperty('App::PropertyString', name, 'Evidence')
        setattr(module, name, text)
    settings = doc.addObject('App::FeaturePython', 'Installation')
    settings.addProperty('App::PropertyLength', 'InsulatedSeparation', 'Assembly')
    settings.InsulatedSeparation = 0.5

    holes = {o.Address: o for o in source.Objects
             if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
    anchor = holes['O17'].Placement.Base
    z = source.Carrier.Placement.Base.z + source.Carrier.Height.Value
    module.Placement = App.Placement(App.Vector(anchor.x, anchor.y, z + 0.5),
                                     App.Rotation(App.Vector(0, 0, 1), -90))
    module.setExpression('Placement.Base.z', f'{z} mm + Installation.InsulatedSeparation')
    board = doc.addObject('Part::Feature', 'PerfboardReference')
    board.Label = 'Perfboard — copied reference in assembly-local coordinates'
    board.Shape = source.PerforatedCarrier.Shape.copy()
    board.ViewObject.ShapeColor = source.PerforatedCarrier.ViewObject.ShapeColor
    copy_carrier_finish(source, doc)

    tape = doc.addObject('Part::Box', 'InsulationEnvelope')
    module.addObject(tape)
    tape.Label = '3 tape layers — 0.5 mm combined; coverage provisional'
    tape.Length, tape.Width = 43.6, 21.3
    tape.Placement.Base = App.Vector(-1.48, -19.54, -0.5)
    tape.setExpression('Height', 'Installation.InsulatedSeparation')
    tape.setExpression('Placement.Base.z', '-Installation.InsulatedSeparation')
    tape.ViewObject.ShapeColor = (0.08, 0.08, 0.08)
    tape.addProperty('App::PropertyString', 'Evidence')
    tape.Evidence = 'Full rectangular coverage is assumed; tape cutouts and actual coverage unmeasured.'

    report = {'revision': REVISION, 'archive_sha256': SHA256,
              'pcb_outline_mm': [43.6, 21.3], 'trimmer_top_mm': 13.036,
              'capacitor_top_mm': 14.3, 'pin_alignment': []}
    for terminal, address, x, y in [('IN+', 'O17', 0, 0),
                                   ('IN-', 'V17', 0, -17.78),
                                   ('OUT+', 'O1', 40.64, 0),
                                   ('OUT-', 'V1', 40.64, -17.78)]:
        pos = module.Placement.multVec(App.Vector(x, y, 0))
        target = holes[address].Placement.Base
        error = ((pos.x-target.x)**2 + (pos.y-target.y)**2)**0.5
        assert error < 1e-7, (terminal, error)
        report['pin_alignment'].append({'terminal': terminal, 'address': address,
                                        'xy_error_mm': error})
        label = doc.addObject('App::Annotation', 'Terminal_' + address)
        label.LabelText = [terminal + ' / ' + address]
        label.Position = App.Vector(pos.x, pos.y, z + 3)
        label.ViewObject.FontSize = 9
    doc.recompute()
    doc.saveAs(str(CACHE / 'LM2596-comparison.FCStd'))
    (CACHE / 'placement-check.json').write_text(json.dumps(report, indent=2)+'\n')
    App.setActiveDocument(doc.Name)
    view = Gui.activeDocument().activeView()
    view.viewAxonometric()
    view.fitAll()
    QtCore.QTimer.singleShot(500, lambda: view.saveImage(
        str(CACHE / 'comparison-preview.png'), 1600, 1200, 'White'))
    print('PASS: four terminal XY positions match; local comparison saved.')


if __name__ in ('__main__', '<run_path>'):
    main()
