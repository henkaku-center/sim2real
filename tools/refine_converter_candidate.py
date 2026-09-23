"""Apply measured heights to the local comparison, preserving imported sources.

Run in the existing GUI after preview_converter_candidate.py. Capacitors lose a
middle cylindrical band; diameters, tops, bases and leads retain source geometry.
These local STEP-derived features are not redistributed with the repository.
"""
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore


def main():
    path = Path(__file__).resolve().parents[1] / 'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'
    doc = next(d for d in App.listDocuments().values() if d.FileName == str(path))
    if doc.getObject('MeasuredCapacitor1'):
        raise RuntimeError('Height refinements already exist; preserve native edits.')
    module = doc.YAAJ_DCDC_StepDown_LM2596_cp
    capacitors = [o for o in module.Group if hasattr(o, 'Shape')
                  and not o.Shape.isNull()
                  and abs(o.Shape.BoundBox.ZMax - 14.3) < 1e-5]
    screws = [o for o in module.Group if hasattr(o, 'Shape')
              and not o.Shape.isNull()
              and abs(o.Shape.BoundBox.ZMax - 13.036) < 0.001]
    assert len(capacitors) == 2 and len(screws) == 1
    doc.openTransaction('Apply instructor converter height measurements')
    try:
        for i, source in enumerate(capacitors, 1):
            # Both cuts pass through the straight cylindrical body. Removing a
            # band preserves the end details and unmeasured lead protrusions.
            b = source.Shape.BoundBox
            removed = b.ZMax - 11.5
            lower = source.Shape.common(Part.makeBox(100, 100, 25,
                                                     App.Vector(-30, -50, -20)))
            upper = source.Shape.common(Part.makeBox(100, 100, 30,
                                                     App.Vector(-30, -50, 5 + removed)))
            upper.translate(App.Vector(0, 0, -removed))
            shape = lower.fuse(upper).removeSplitter()
            assert shape.isValid() and len(shape.Solids) == 1
            assert abs(shape.BoundBox.ZMax - 11.5) < 1e-6
            assert abs(shape.BoundBox.ZMin - b.ZMin) < 1e-6
            obj = doc.addObject('Part::Feature', f'MeasuredCapacitor{i}')
            module.addObject(obj)
            obj.Label = f'Capacitor {i} — top 11.5 mm from PCB underside'
            obj.Shape = shape
            obj.addProperty('App::PropertyLength', 'MeasuredTopHeight', 'Evidence')
            obj.MeasuredTopHeight = 11.5
            obj.setEditorMode('MeasuredTopHeight', 1)
            obj.addProperty('App::PropertyString', 'Modification', 'Evidence')
            obj.Modification = 'Instructor measurement; removed 2.8 mm mid-body band. Diameter, end details and leads remain unverified reference geometry.'
            # Transfer each face finish from the nearest corresponding original
            # surface, undoing the upper-piece translation for comparison.
            appearances = source.ViewObject.ShapeAppearance
            mapped = []
            for face in shape.Faces:
                probe = face.CenterOfMass
                if probe.z > 5:
                    probe.z += removed
                point = Part.Vertex(probe)
                index = min(range(len(source.Shape.Faces)),
                            key=lambda n: source.Shape.Faces[n].distToShape(point)[0])
                mapped.append(appearances[min(index, len(appearances)-1)])
            obj.ViewObject.ShapeAppearance = mapped
            source.ViewObject.Visibility = False

        source = screws[0]
        z0 = source.Shape.BoundBox.ZMin
        height = source.Shape.BoundBox.ZLength
        shape = source.Shape.common(Part.makeBox(100, 100, 30,
                                    App.Vector(-30, -50, z0 + height - 1)))
        shape.translate(App.Vector(0, 0, -(height - 1)))
        assert shape.isValid() and abs(shape.BoundBox.ZLength - 1) < 1e-6
        screw = doc.addObject('Part::Feature', 'MeasuredAdjustmentScrew')
        module.addObject(screw)
        screw.Label = 'Gold adjustment screw — 1 mm protrusion'
        screw.Shape = shape
        gold = source.ViewObject.ShapeAppearance[0]
        gold.DiffuseColor = (0.83, 0.64, 0.19)
        gold.SpecularColor = (0.95, 0.82, 0.45)
        gold.Shininess = 0.8
        screw.ViewObject.ShapeAppearance = [gold] * len(shape.Faces)
        screw.ViewObject.LineColor = (0.40, 0.29, 0.07)
        screw.addProperty('App::PropertyString', 'Evidence')
        screw.Evidence = 'Instructor: ~1 mm protrusion. Source blue body top retained at 11.516 mm; resulting screw top 12.516 mm is consistent with earlier approximate 13 mm, not an exact measurement.'
        source.ViewObject.Visibility = False
        doc.CandidateModule.Status = 'Locally adapted candidate: capacitor tops measured 11.5 mm; screw protrusion ~1 mm; blue-body height still reference-derived.'
        doc.Label = 'LM2596 comparison — measured capacitor heights'
        doc.recompute()
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.save()
    App.setActiveDocument(doc.Name)
    view = Gui.activeDocument().activeView()
    view.viewAxonometric()
    view.fitAll()
    image = Path(doc.FileName).parent / 'comparison-preview.png'
    QtCore.QTimer.singleShot(500, lambda: view.saveImage(str(image), 1600, 1200, 'White'))
    print('PASS: two capacitor tops 11.5 mm; screw protrusion 1 mm; imported originals hidden and preserved.')


main()
