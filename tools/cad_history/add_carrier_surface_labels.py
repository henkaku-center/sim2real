"""Add editable surface markings and reconcile physical hole addresses.

Execute with runpy.run_path() in the existing FreeCAD Python console.
Stable internal object names are retained so existing expressions keep working.
"""
from pathlib import Path
import csv
import FreeCAD as App
from draftmake.make_shapestring import make_shapestring

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / 'assets/cad/work/Sesame-S3-circuitry.FCStd'
FONT = './../fonts/SourceCodePro-Regular.ttf'


def main():
    doc = next((d for d in App.listDocuments().values() if d.FileName == str(FILE)), None)
    if doc is None:
        doc = App.openDocument(str(FILE))
    if doc.getObject('SurfaceLabels'):
        print('Surface labels already exist; preserving edits.')
        return
    App.setActiveDocument(doc.Name)
    doc.openTransaction('Add physical surface coordinates')
    try:
        params = doc.addObject('App::FeaturePython', 'SurfaceLabelParameters')
        params.Label = 'Surface labels — A–X right to left; 01–18 bottom to top'
        for name, value in [('LetterHeight', 1.1), ('NumberHeight', 0.6),
                            ('TopInset', 1.2), ('DisplayLift', 0.012)]:
            params.addProperty('App::PropertyLength', name, 'Lettering')
            setattr(params, name, value)
        params.addProperty('App::PropertyString', 'Evidence', 'Evidence')
        params.Evidence = 'Instructor 2026-09-23: top long edge A-X right to left, no skipped letters; right short edge 01-18 bottom to top, numerals rotated counterclockwise 90 degrees in top view. All labels thin light-green outlines. Top-face markings only; underside orientation not confirmed. Font and text dimensions illustrative; visualization-only lift above board.'
        doc.Circuitry.addObject(params)
        labels = doc.addObject('App::DocumentObjectGroup', 'SurfaceLabels')
        labels.Label = 'Light-green outline lettering — physical board coordinates'
        doc.Circuitry.addObject(labels)
        def text(value, size_expression, x_expression, y_expression):
            obj = make_shapestring(value, FONT, Size=1)
            obj.Label = 'Surface ' + value
            obj.Justification = 'Middle-Center'
            obj.JustificationReference = 'Shape Height'
            obj.MakeFace = False
            obj.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), 90 if value.isdigit() else 0)
            obj.setExpression('Size', size_expression)
            obj.setExpression('Placement.Base.x', x_expression)
            obj.setExpression('Placement.Base.y', y_expression)
            obj.setExpression('Placement.Base.z', 'Carrier.Placement.Base.z + Carrier.Height + SurfaceLabelParameters.DisplayLift')
            labels.addObject(obj)
            if App.GuiUp:
                obj.ViewObject.ShapeColor = (0.65, 0.85, 0.55)
                obj.ViewObject.LineColor = (0.65, 0.85, 0.55)
                obj.ViewObject.LineWidth = 1.0
                obj.ViewObject.DisplayMode = 'Wireframe'
            return obj
        for index in range(24):
            physical = chr(65 + index)
            legacy = chr(88 - index)
            text(physical, 'SurfaceLabelParameters.LetterHeight',
                 f'Hole_{legacy}1.Placement.Base.x',
                 'Carrier.Placement.Base.y + Carrier.Width - SurfaceLabelParameters.TopInset')
        # Center the numbers in the gap between the right signal rings and pills.
        number_x = '(Hole_X1.Placement.Base.x + HoleGrid.HoleDiameter / 2 + PadParameters.RadialWidth + Carrier.Placement.Base.x + Carrier.Length - EdgePadParameters.EdgeInset - EdgePadParameters.Length / 2) / 2'
        for number in range(1, 19):
            text(f'{number:02d}', 'SurfaceLabelParameters.NumberHeight', number_x,
                 f'Hole_X{19-number}.Placement.Base.y')
        for col in range(24):
            for row in range(1, 19):
                legacy = f'{chr(65+col)}{row}'
                physical = f'{chr(88-col)}{19-row}'
                hole = doc.getObject('Hole_' + legacy)
                hole.addProperty('App::PropertyString', 'Address', 'Coordinates')
                hole.Address = physical
                hole.Label = physical
                for face in ('Top', 'Bottom'):
                    pad = doc.getObject(f'Pad_{face}_{legacy}')
                    pad.addProperty('App::PropertyString', 'Address', 'Coordinates')
                    pad.Address = physical
                    pad.Label = f'{face} pad {physical}'
        for face in ('Top', 'Bottom'):
            for side in ('Left', 'Right'):
                for row in range(2, 18):
                    doc.getObject(f'EdgePad_{face}_{side}_{row}').Label = f'{face} {side.lower()} edge pad — row {19-row:02d}'
        doc.HoleGrid.Coordinates = 'Physical top view: top edge A-X right to left; right edge 01-18 bottom to top. A1=bottom right; X18=top left. Hole.Address and Label are physical coordinates. Internal object Names retain legacy opposite orientation to preserve expressions; never infer physical address from Name.'
        doc.GridLabels.Label = 'Legacy external coordinate annotations — hidden'
        if App.GuiUp:
            for obj in [doc.GridLabels] + doc.GridLabels.Group:
                obj.ViewObject.hide()
            import FreeCADGui as Gui
            Gui.Selection.clearSelection()
        doc.recompute()
        assert len(labels.Group) == 42
        for obj in labels.Group:
            assert not obj.Shape.isNull() and obj.Shape.isValid(), obj.Label
            b = obj.Shape.BoundBox
            base = doc.Carrier.Placement.Base
            assert b.XMin > base.x and b.XMax < base.x + doc.Carrier.Length.Value, obj.Label
            assert b.YMin > base.y and b.YMax < base.y + doc.Carrier.Width.Value, obj.Label
        assert doc.Hole_X18.Address == 'A1' and doc.Hole_A1.Address == 'X18'
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.save()
    holes = sorted((o for o in doc.HoleTools.Links if hasattr(o, 'Address')),
                   key=lambda o: (o.Address[0], int(o.Address[1:])))
    with (ROOT / 'assets/cad/reports/carrier-hole-coordinates.csv').open('w', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['address', 'x_mm', 'y_mm', 'pcb_top_z_mm', 'diameter_mm', 'offset_status', 'native_object'])
        for hole in holes:
            p = hole.Placement.Base
            writer.writerow([hole.Address, round(p.x, 6), round(p.y, 6), doc.Carrier.Placement.Base.z + doc.Carrier.Height.Value,
                             doc.HoleGrid.HoleDiameter.Value, 'centered assumption; not measured', hole.Name])
    if App.GuiUp:
        from PySide import QtCore
        def capture():
            view = Gui.activeDocument().activeView()
            camera = view.getCamera()
            try:
                view.viewTop()
                view.fitAll()
                view.saveImage(str(FILE.parent / 'circuitry-preview.png'), 1600, 1200, 'White')
            finally:
                view.setCamera(camera)
            print('PASS: 42 surface labels; physical addresses and CSV updated; saved existing document. Camera restored.')
        QtCore.QTimer.singleShot(500, capture)


main()
