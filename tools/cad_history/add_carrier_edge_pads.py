"""Add native linked capsule pads along both short edges, in the existing GUI."""
from pathlib import Path
import math
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / 'assets/cad/work/Sesame-S3-circuitry.FCStd'


def main():
    doc = next((d for d in App.listDocuments().values() if d.FileName == str(FILE)), None)
    if doc is None:
        doc = App.openDocument(str(FILE))
    if doc.getObject('EdgePads'):
        print('Edge pads already exist; preserving native edits.')
        return
    doc.openTransaction('Add sixteen capsule pads along each short edge')
    try:
        params = doc.addObject('App::FeaturePython', 'EdgePadParameters')
        params.Label = 'Edge pads — 3 × 2 mm; edge inset provisional'
        for name, value in [('Length', 3.0), ('Width', 2.0), ('EdgeInset', 2.0)]:
            params.addProperty('App::PropertyLength', name, 'Pads')
            setattr(params, name, value)
        params.setExpression('Width', 'HoleGrid.HoleDiameter + 2 * PadParameters.RadialWidth')
        params.addProperty('App::PropertyString', 'Evidence', 'Evidence')
        params.Evidence = 'Instructor, 2026-09-23: sixteen metal pills per short edge, about 3 mm long and 2 mm wide; clarified end curvature matches the outer edge of the silver pinhole ring. Width expression follows ring outer diameter, giving end radius=1 mm initially. Photo-01 supports row 2-17 alignment and long axis across the margin. Centers assumed 2 mm from short edges, NOT measured. Repeated on both faces following double-sided board reference. Height follows visualization-only PadParameters.DisplayThickness; electrical purpose not verified.'
        doc.Circuitry.addObject(params)
        templates = doc.addObject('App::DocumentObjectGroup', 'EdgePadTemplates')
        templates.Label = 'Hidden native capsule template'
        middle = doc.addObject('Part::Box', 'EdgePadMiddle')
        middle.setExpression('Length', 'EdgePadParameters.Length - EdgePadParameters.Width')
        middle.setExpression('Width', 'EdgePadParameters.Width')
        middle.setExpression('Height', 'PadParameters.DisplayThickness')
        middle.setExpression('Placement.Base.x', '-(EdgePadParameters.Length - EdgePadParameters.Width) / 2')
        middle.setExpression('Placement.Base.y', '-EdgePadParameters.Width / 2')
        ends = []
        for name, sign in [('Left', '-'), ('Right', '')]:
            end = doc.addObject('Part::Cylinder', 'EdgePadEnd' + name)
            end.setExpression('Radius', 'EdgePadParameters.Width / 2')
            end.setExpression('Height', 'PadParameters.DisplayThickness')
            end.setExpression('Placement.Base.x', sign + '(EdgePadParameters.Length - EdgePadParameters.Width) / 2')
            ends.append(end)
        capsule = doc.addObject('Part::MultiFuse', 'EdgePadCapsule')
        capsule.Label = 'Parametric 3 × 2 mm capsule — shared by 64 pads'
        capsule.Shapes = [middle] + ends
        capsule.Refine = True
        templates.Group = [middle] + ends + [capsule]
        pads = doc.addObject('App::DocumentObjectGroup', 'EdgePads')
        pads.Label = 'Edge pads — 16 per short edge, both faces'
        doc.Circuitry.addObject(pads)
        for face in ('Top', 'Bottom'):
            for side in ('Left', 'Right'):
                group = doc.addObject('App::DocumentObjectGroup', f'EdgePads{face}{side}')
                group.Label = f'{face} {side.lower()} — rows 2–17'
                pads.addObject(group)
                for row in range(2, 18):
                    link = doc.addObject('App::Link', f'EdgePad_{face}_{side}_{row}')
                    link.setLink(capsule)
                    link.Label = f'{face} {side.lower()} edge pad — row {row}'
                    x = 'EdgePadParameters.EdgeInset' if side == 'Left' else 'Carrier.Length - EdgePadParameters.EdgeInset'
                    link.setExpression('LinkPlacement.Base.x', 'Carrier.Placement.Base.x + ' + x)
                    link.setExpression('LinkPlacement.Base.y', f'Hole_A{row}.Placement.Base.y')
                    z = 'Carrier.Height' if face == 'Top' else '-PadParameters.DisplayThickness'
                    link.setExpression('LinkPlacement.Base.z', 'Carrier.Placement.Base.z + ' + z)
                    group.addObject(link)
        doc.recompute()
        assert capsule.Shape.isValid() and len(capsule.Shape.Solids) == 1
        area = (params.Length.Value - params.Width.Value) * params.Width.Value + math.pi * (params.Width.Value / 2)**2
        assert abs(capsule.Shape.Volume - area * doc.PadParameters.DisplayThickness.Value) < 1e-8
        assert abs(capsule.Shape.BoundBox.XLength - 3) < 1e-8
        assert abs(capsule.Shape.BoundBox.YLength - 2) < 1e-8
        for group in pads.Group:
            assert len(group.Group) == 16
            for link in group.Group:
                assert link.Shape.isValid()
        doc.ValidationScope.CurrentStage = 'Carrier with signal holes, mounting holes, annular pads and edge capsule pads; offsets and metal height partly provisional, installed components pending.'
        if App.GuiUp:
            import FreeCADGui as Gui
            # MultiFuse inherits per-face appearance from its source solids
            # on recompute; styling only the result is not persistent.
            finish = doc.PadRing.ViewObject
            for obj in [middle] + ends + [capsule]:
                obj.ViewObject.ShapeAppearance = finish.ShapeAppearance
                obj.ViewObject.LineMaterial = finish.LineMaterial
                obj.ViewObject.LineWidth = finish.LineWidth
                obj.ViewObject.DisplayMode = finish.DisplayMode
                obj.ViewObject.Lighting = finish.Lighting
            for obj in [middle] + ends + [capsule, templates]:
                obj.ViewObject.hide()
            for group in pads.Group:
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
            print('PASS: 64 native capsule pads, sixteen per edge per face; 3x2 mm outline and volume checked; existing document saved.')
        QtCore.QTimer.singleShot(500, capture)


main()
