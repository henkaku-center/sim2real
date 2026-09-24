"""Add native pins and illustrative solder to the saved converter comparison.

Run in the existing GUI. Installation properties are authoritative thereafter.
Only the physical construction and flush cut ends are confirmed; pin cross-section,
top projection and solder profiles are explicitly provisional visualization values.
"""
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / 'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'


def main():
    doc = next(d for d in App.listDocuments().values() if d.FileName == str(FILE))
    if doc.getObject('ConverterPins'):
        raise RuntimeError('Pins already exist; preserve native edits.')
    doc.openTransaction('Add clipped square converter pins and solder')
    try:
        settings = doc.Installation
        for name, value, explanation in [
            ('PinWidth', 0.64, 'Illustrative square width; not physically measured.'),
            ('PinTopProjection', 0.3, 'Illustrative short end within top solder mound; not measured.'),
            ('CarrierThickness', 1.6, 'Existing carrier thickness from purchased listing.'),
            ('ConverterThickness', 1.6, 'Candidate CAD nominal thickness; not measured.'),
            ('CarrierBoreRadius', 0.5, 'Existing carrier 1 mm bore model.'),
            ('ConverterBoreRadius', 0.499, 'Imported terminal hole radius from geometry audit.'),
            ('TopSolderRadius', 0.9, 'Illustrative solder fillet radius; not measured.'),
            ('TopSolderHeight', 0.4, 'Illustrative solder fillet height; not measured.'),
            ('BottomSolderProjection', 1.0, 'Instructor: underside solder typically ~1 mm. Applied uniformly to these four joints; not individually measured or a maximum.'),
            ('BottomSolderRadius', 0.95, 'Photo 07 shows solder covering pads; radius illustrative, not measured.'),
        ]:
            settings.addProperty('App::PropertyLength', name, 'Pin and solder assumptions', explanation)
            setattr(settings, name, value)
        group = doc.addObject('App::DocumentObjectGroup', 'ConverterPins')
        group.Label = '4 clipped square pins — plastic removed; solder illustrative'
        doc.CandidateModule.addObject(group)
        pins, finished, tools = [], [], []

        def add(kind, name):
            obj = doc.addObject(kind, name)
            group.addObject(obj)
            return obj

        def solder_fill(name, x, y, radius, z, height, pin):
            cylinder = add('Part::Cylinder', name + 'Blank')
            cylinder.setExpression('Radius', radius)
            cylinder.setExpression('Height', height)
            cylinder.Placement.Base.x, cylinder.Placement.Base.y = x, y
            cylinder.setExpression('Placement.Base.z', z)
            cut = add('Part::Cut', name)
            cut.Base, cut.Tool = cylinder, pin
            tools.append(cylinder)
            finished.append(cut)
            return cut

        for terminal, address, x, y in [('IN+', 'O17', 0, 0),
                                       ('IN-', 'V17', 0, -17.78),
                                       ('OUT+', 'O1', 40.64, 0),
                                       ('OUT-', 'V1', 40.64, -17.78)]:
            pin = add('Part::Box', 'ConverterPin_' + address)
            pin.Label = f'{terminal} → {address} — square pin, clipped flush'
            pin.setExpression('Length', 'Installation.PinWidth')
            pin.setExpression('Width', 'Installation.PinWidth')
            pin.setExpression('Height', 'Installation.CarrierThickness + Installation.InsulatedSeparation + Installation.ConverterThickness + Installation.PinTopProjection')
            pin.setExpression('Placement.Base.x', f'{x} mm - Installation.PinWidth / 2')
            pin.setExpression('Placement.Base.y', f'{y} mm - Installation.PinWidth / 2')
            pin.setExpression('Placement.Base.z', '-Installation.CarrierThickness - Installation.InsulatedSeparation')
            pin.addProperty('App::PropertyString', 'Address', 'Evidence')
            pin.Address = address
            pin.addProperty('App::PropertyString', 'Construction', 'Evidence')
            pin.Construction = 'Short end inserted from below converter and soldered on top; plastic flush to converter underside then removed; long end through carrier, clipped flush underneath and hole filled with solder. Width and top projection provisional.'
            pins.append(pin)
            solder_fill('ConverterHoleSolder_' + address, x, y,
                        'Installation.ConverterBoreRadius', '0 mm',
                        'Installation.ConverterThickness', pin)
            solder_fill('CarrierHoleSolder_' + address, x, y,
                        'Installation.CarrierBoreRadius',
                        '-Installation.CarrierThickness - Installation.InsulatedSeparation',
                        'Installation.CarrierThickness', pin)
            bottom = add('Part::Cone', 'BottomSolder_' + address)
            bottom.Label = f'{address} underside solder mound — photo-observed; size assumed'
            bottom.Placement.Base.x, bottom.Placement.Base.y = x, y
            bottom.setExpression('Placement.Base.z', '-Installation.CarrierThickness - Installation.InsulatedSeparation - Installation.BottomSolderProjection')
            bottom.setExpression('Radius1', 'Installation.BottomSolderRadius * 0.5')
            bottom.setExpression('Radius2', 'Installation.BottomSolderRadius')
            bottom.setExpression('Height', 'Installation.BottomSolderProjection')
            finished.append(bottom)
            fillet = add('Part::Cone', 'TopSolderBlank_' + address)
            fillet.Placement.Base.x, fillet.Placement.Base.y = x, y
            fillet.setExpression('Placement.Base.z', 'Installation.ConverterThickness')
            fillet.setExpression('Radius1', 'Installation.TopSolderRadius')
            fillet.setExpression('Radius2', 'Installation.PinWidth * 0.75')
            fillet.setExpression('Height', 'Installation.TopSolderHeight')
            cut = add('Part::Cut', 'TopSolder_' + address)
            cut.Base, cut.Tool = fillet, pin
            tools.append(fillet)
            finished.append(cut)

        # Photo 04 shows a central tape patch leaving terminal pads exposed.
        # Coverage offsets are illustrative rather than image measurements.
        tape = doc.InsulationEnvelope
        tape.Length, tape.Width = 37.6, 20.3
        tape.Placement.Base.x, tape.Placement.Base.y = 1.52, -19.04
        tape.Label = '3 tape layers — central patch; corner terminals exposed'
        tape.Evidence = 'Photo 04: central overlapping tape, terminals exposed. 37.6 x 20.3 mm rectangular coverage assumed; combined ~0.5 mm separation instructor estimate.'
        doc.recompute()
        for obj in pins + finished + [tape]:
            assert not obj.Shape.isNull() and obj.Shape.isValid(), obj.Name
        for pin in pins:
            assert abs(pin.Shape.BoundBox.ZMin + doc.CandidateModule.Placement.Base.z) < 1e-7
        for obj in pins:
            obj.ViewObject.ShapeColor = (0.76, 0.77, 0.79)
        for obj in finished:
            obj.ViewObject.ShapeColor = (0.70, 0.72, 0.74)
        tape.ViewObject.ShapeColor = (0.08, 0.08, 0.08)
        for obj in tools:
            obj.ViewObject.Visibility = False
        for obj in pins + finished + [tape]:
            obj.ViewObject.Visibility = True
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.save()
    App.setActiveDocument(doc.Name)
    def capture():
        view = Gui.activeDocument().activeView()
        camera = view.getCamera()
        try:
            view.viewAxonometric()
            view.fitAll()
            view.saveImage(str(FILE.parent / 'comparison-preview.png'), 1600, 1200, 'White')
        finally:
            view.setCamera(camera)
    QtCore.QTimer.singleShot(500, capture)
    print('PASS: four flush-cut square pins, 16 solder features and central tape patch; saved.')


main()
