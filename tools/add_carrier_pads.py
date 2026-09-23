"""Add linked, native annular pads to the open circuitry document once.

Run with runpy.run_path() in the existing FreeCAD GUI's Python console.
The ring and links stay editable without a Python proxy after saving.
"""
from pathlib import Path
import math
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'assets/cad/work/Sesame-S3-circuitry.FCStd'


def main():
    doc = next((d for d in App.listDocuments().values() if d.FileName == str(FILE)), None)
    if doc is None:
        doc = App.openDocument(str(FILE))
    if doc.getObject('ConductivePads'):
        print('Pads already exist; preserving native edits.')
        return
    doc.openTransaction('Add 0.5 mm radial-width conductive pads')
    try:
        params = doc.addObject('App::FeaturePython', 'PadParameters')
        params.Label = 'Pads — 0.5 mm radial width; layer height illustrative'
        for name, value in [('RadialWidth', 0.5), ('DisplayThickness', 0.01)]:
            params.addProperty('App::PropertyLength', name, 'Pads')
            setattr(params, name, value)
        params.addProperty('App::PropertyString', 'Evidence', 'Evidence')
        params.Evidence = 'Instructor requested 0.5 mm thick rings, interpreted as radial width (2026-09-23). At 1 mm hole diameter, outer diameter=2 mm. Both faces follow board photo. 0.01 mm axial height is visualization-only, NOT measured metal thickness; pad shape/diameter not independently measured. No plated hole barrels or side-edge pads modeled.'
        doc.Circuitry.addObject(params)
        templates = doc.addObject('App::DocumentObjectGroup', 'PadTemplates')
        templates.Label = 'Hidden native ring template'
        # Keep shared source geometry at document scope; App::Link instances
        # carry its geometry into Circuitry without group-scope conflicts.
        outer = doc.addObject('Part::Cylinder', 'PadOuter')
        outer.setExpression('Radius', 'HoleGrid.HoleDiameter / 2 + PadParameters.RadialWidth')
        outer.setExpression('Height', 'PadParameters.DisplayThickness')
        inner = doc.addObject('Part::Cylinder', 'PadInner')
        inner.setExpression('Radius', 'HoleGrid.HoleDiameter / 2')
        inner.setExpression('Height', 'PadParameters.DisplayThickness + 2 mm')
        inner.Placement.Base.z = -1
        ring = doc.addObject('Part::Cut', 'PadRing')
        ring.Label = 'Parametric annulus — shared by 864 pads'
        ring.Base, ring.Tool = outer, inner
        templates.Group = [outer, inner, ring]
        pads = doc.addObject('App::DocumentObjectGroup', 'ConductivePads')
        pads.Label = 'Conductive pads — 432 per face'
        doc.Circuitry.addObject(pads)
        for face in ('Top', 'Bottom'):
            group = doc.addObject('App::DocumentObjectGroup', face + 'Pads')
            group.Label = face + ' pads — A1 to X18'
            pads.addObject(group)
            for col in range(24):
                for row in range(18):
                    address = f'{chr(65+col)}{row+1}'
                    link = doc.addObject('App::Link', f'Pad_{face}_{address}')
                    link.setLink(ring)
                    link.Label = f'{face} pad {address}'
                    link.setExpression('LinkPlacement.Base.x', f'Hole_{address}.Placement.Base.x')
                    link.setExpression('LinkPlacement.Base.y', f'Hole_{address}.Placement.Base.y')
                    z = 'Carrier.Placement.Base.z + Carrier.Height' if face == 'Top' else 'Carrier.Placement.Base.z - PadParameters.DisplayThickness'
                    link.setExpression('LinkPlacement.Base.z', z)
                    group.addObject(link)
        doc.recompute()
        assert ring.Shape.isValid() and len(ring.Shape.Solids) == 1
        r = doc.HoleGrid.HoleDiameter.Value / 2
        expected = math.pi * ((r + params.RadialWidth.Value)**2 - r**2) * params.DisplayThickness.Value
        assert abs(ring.Shape.Volume - expected) < 1e-8
        for group in (doc.TopPads, doc.BottomPads):
            assert len(group.Group) == 432
            for link in group.Group:
                assert link.Shape.isValid()
                assert abs(link.Shape.Volume - expected) < 1e-8
        doc.ValidationScope.CurrentStage = 'Carrier: 432 signal holes, four estimated mounting holes, 864 conductive pads. Grid offsets and metal height provisional; installed components pending.'
        if App.GuiUp:
            import FreeCADGui as Gui
            ring.ViewObject.ShapeColor = (0.78, 0.80, 0.82)
            ring.ViewObject.LineColor = (0.40, 0.42, 0.44)
            for obj in (outer, inner, ring, templates):
                obj.ViewObject.hide()
            for group in (doc.TopPads, doc.BottomPads):
                for link in group.Group:
                    link.ViewObject.show()
            Gui.Selection.clearSelection()
        doc.recompute()
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.save()
    if App.GuiUp:
        from PySide import QtCore
        def capture():
            Gui.activeDocument().activeView().saveImage(str(FILE.parent / 'circuitry-preview.png'), 1600, 1200, 'White')
            print('PASS: 864 native linked pads; valid rings and volumes verified; existing document saved and preview captured.')
        QtCore.QTimer.singleShot(500, capture)


main()
