"""Place the selected hub at the instructor-confirmed approximate height.

Run in the existing GUI with carrier, circuitry comparison and hub candidate open.
Uses the explicitly corrected 58.42 mm row-span reference; no scaling or bent-pin
geometry is introduced. Header/socket geometry is still pending.
"""
from pathlib import Path
import json
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

ROOT = Path(__file__).resolve().parents[1]


def main():
    def opened(relative):
        return next(d for d in App.listDocuments().values() if d.FileName == str(ROOT / relative))
    doc = opened('assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd')
    carrier = opened('assets/cad/work/Sesame-S3-circuitry.FCStd')
    source = opened('assets/cad/upstream/pca9685-uploaded/ServoHub_FittedReference.FCStd')
    if doc.getObject('ServoHubCandidate'):
        raise RuntimeError('Hub already placed; preserve native edits.')
    holes = {o.Address: o for o in carrier.Objects
             if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
    doc.openTransaction('Place span-corrected hub at confirmed approximate height')
    try:
        params = doc.addObject('App::FeaturePython', 'HubInstallation')
        params.Label = 'Hub placement — instructor estimates and unresolved fit'
        for name, value, text in [
            ('CarrierTopZ', doc.PerfboardReference.Shape.BoundBox.ZMax, 'Saved carrier top datum.'),
            ('PCBSeparation', 14, 'Instructor estimate: carrier TOP to hub PCB UNDERSIDE, just clearing gold screw.'),
            ('RequiredRowSpan', holes['A3'].Placement.Base.x - holes['X3'].Placement.Base.x, 'Confirmed carrier columns A and X.'),
            ('CandidateRowSpan', 58.42, 'Derived reference corrected from uploaded 57.46 mm span to confirmed sockets.'),
        ]:
            params.addProperty('App::PropertyLength', name, 'Placement evidence', text)
            setattr(params, name, value)
        params.addProperty('App::PropertyString', 'SocketAddresses', 'Placement evidence')
        params.SocketAddresses = 'A3-A8 and X3-X8; instructor confirmed'
        hub = doc.addObject('App::Part', 'ServoHubCandidate')
        hub.Label = 'Servo hub — 14 mm elevation; corrected socket span'
        imported = doc.copyObject(source.getObject('PCA9685'), True)
        hub.addObject(imported)
        hub.Placement.Base.x = (holes['A3'].Placement.Base.x + holes['X3'].Placement.Base.x) / 2
        hub.Placement.Base.y = (holes['A3'].Placement.Base.y + holes['A8'].Placement.Base.y) / 2
        hub.setExpression('Placement.Base.z', 'HubInstallation.CarrierTopZ + HubInstallation.PCBSeparation')
        hub.addProperty('App::PropertyString', 'FitStatus', 'Evidence')
        hub.FitStatus = 'Derived reference: source end rows moved outward 0.48 mm each to confirmed A-X socket span. PCB outline 60.96 mm inferred, not measured. No connecting headers modeled yet.'
        hub.addProperty('App::PropertyString', 'ASIN', 'Evidence')
        hub.ASIN = 'B078YRJ8D7'
        doc.recompute()
        assert abs(hub.Placement.Base.z - 15.6) < 1e-7
        mismatches = []
        for column, x in [('A', 29.21), ('X', -29.21)]:
            for row, y in zip(range(3, 9), [-6.35, -3.81, -1.27, 1.27, 3.81, 6.35]):
                point = hub.Placement.multVec(App.Vector(x, y, 0))
                target = holes[f'{column}{row}'].Placement.Base
                assert abs(point.y - target.y) < 1e-7
                assert abs(point.x - target.x) < 1e-7
                mismatches.append({'address': f'{column}{row}', 'x_error_mm': point.x-target.x, 'y_error_mm': point.y-target.y})
        # Convert the screw's local shape to document coordinates before measuring.
        screw = doc.MeasuredAdjustmentScrew
        screw_shape = screw.Shape.copy()
        parent_pose = screw.getGlobalPlacement().multiply(screw.Placement.inverse())
        screw_shape.Placement = parent_pose.multiply(screw_shape.Placement)
        distance = hub.Shape.distToShape(screw_shape)[0]
        report = {'source': 'Socket-span-corrected reference placed in local comparison',
                  'carrier_top_to_hub_underside_mm': 14,
                  'hub_underside_z_mm': hub.Placement.Base.z,
                  'screw_to_candidate_distance_mm': distance,
                  'clearance_status': 'Model-only value; physical minimum unmeasured and source dimensions provisional',
                  'terminal_mismatches': mismatches}
        (Path(doc.FileName).parent / 'hub-placement-check.json').write_text(json.dumps(report, indent=2)+'\n')
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.save()
    App.setActiveDocument(doc.Name)
    view = Gui.activeDocument().activeView()
    view.viewAxonometric()
    view.fitAll()
    QtCore.QTimer.singleShot(500, lambda: view.saveImage(str(Path(doc.FileName).parent / 'comparison-preview.png'), 1600, 1200, 'White'))
    print(f'PASS: hub placed at Z=15.6 mm; all twelve terminal centers aligned; model screw distance {distance:.4f} mm.')


main()
