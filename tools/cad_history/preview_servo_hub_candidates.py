"""Inspect the two uploaded hub candidates in the existing FreeCAD GUI.

Inputs and native comparison documents remain in the ignored local cache.
These are standalone candidates, not installed/validated circuitry parts.
"""
from pathlib import Path
import json
import FreeCAD as App
import FreeCADGui as Gui
import ImportGui
from PySide import QtCore

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'assets/cad/upstream/pca9685-uploaded'


def main():
    candidates = [('pca9685.step', 'ServoHub_STEP'), ('PCA9685.IGS', 'ServoHub_IGES')]
    for filename, name in candidates:
        assert (CACHE / filename).exists(), filename
        if any(d.Name == name or d.FileName == str(CACHE / (name + '.FCStd'))
               for d in App.listDocuments().values()):
            raise RuntimeError(f'{name} already open; preserve native edits.')
    names = []
    for filename, name in candidates:
        doc = App.newDocument(name)
        doc.Label = name.replace('_', ' ') + ' — unverified candidate'
        ImportGui.insert(str(CACHE / filename), doc.Name)
        doc.recompute()
        report = []
        for obj in doc.Objects:
            if obj.TypeId.startswith('Part::') and hasattr(obj, 'Shape') and not obj.Shape.isNull():
                b = obj.Shape.BoundBox
                report.append({'name': obj.Name, 'label': obj.Label,
                               'bounds_mm': [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax],
                               'solids': len(obj.Shape.Solids), 'shells': len(obj.Shape.Shells),
                               'visible': obj.ViewObject.Visibility,
                               'parents': [o.Name for o in obj.InList]})
        (CACHE / (name + '-objects.json')).write_text(json.dumps(report, indent=2)+'\n')
        doc.saveAs(str(CACHE / (name + '.FCStd')))
        names.append(doc.Name)

    def capture():
        for name in names:
            App.setActiveDocument(name)
            view = Gui.activeDocument().activeView()
            view.viewAxonometric()
            view.fitAll()
            view.saveImage(str(CACHE / (name + '-preview.png')), 1600, 1200, 'White')
        App.setActiveDocument(names[0])
        print('PASS: both uploaded candidates imported and saved locally in existing GUI.')
    QtCore.QTimer.singleShot(500, capture)


main()
