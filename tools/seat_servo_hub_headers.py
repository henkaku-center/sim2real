"""Seat the existing native header stack flush, preserving all other CAD edits.

Run in the existing FreeCAD GUI. Flush mating is instructor-confirmed; the
resulting board separation is derived from still-provisional housing dimensions.
"""
from pathlib import Path
import json
import FreeCAD as App
import FreeCADGui as Gui

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'


def world(obj):
    shape = obj.Shape.copy()
    shape.Placement = obj.getGlobalPlacement().multiply(obj.Placement.inverse()).multiply(shape.Placement)
    return shape


def main():
    doc = next(d for d in App.listDocuments().values() if d.FileName == str(FILE))
    p = doc.HubInstallation
    previous = p.PCBSeparation.Value
    doc.openTransaction('Seat male header spacers flush against female sockets')
    try:
        p.PCBSeparation = p.SocketHeight + p.OriginalSpacerHeight + p.DonorSpacerHeight
        if 'SeatingEvidence' not in p.PropertiesList:
            p.addProperty('App::PropertyString', 'SeatingEvidence', 'Header assumptions')
        p.SeatingEvidence = 'Instructor confirms plastic-to-plastic flush mating. Board separation derived from provisional socket/spacer dimensions; earlier physical estimate was approximately 14 mm.'
        doc.recompute()
        for col in ['A', 'X']:
            gap = min(world(doc.getObject(name+'_'+col)).BoundBox.ZMin for name in ['DonorSpacer', 'OriginalSpacer']) - world(doc.getObject('SocketHousing_'+col)).BoundBox.ZMax
            assert abs(gap) < 1e-7, gap
        clearance = world(doc.ServoHubCandidate).distToShape(world(doc.MeasuredAdjustmentScrew))[0]
        assert clearance > 0, 'Seated hub touches converter screw'
        for row in range(3, 9):
            for col in ['A', 'X']:
                pin = world(doc.getObject(f'HubMalePin_{col}{row}'))
                assert pin.common(world(doc.getObject(f'SocketTail_{col}{row}'))).Volume < 1e-7
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.save()
    report = {'previous_board_separation_mm': previous,
              'seated_board_separation_mm': p.PCBSeparation.Value,
              'plastic_mating_gap_mm': 0,
              'modeled_screw_clearance_mm': clearance,
              'evidence': p.SeatingEvidence}
    (ROOT/'assets/cad/reports/servo-hub-flush-seating.json').write_text(json.dumps(report, indent=2)+'\n')
    App.setActiveDocument(doc.Name)
    Gui.activeDocument().activeView().saveImage(str(FILE.parent/'hub-headers-flush-preview.png'),1600,1200,'White')
    print(f'PASS: flush seating; separation {p.PCBSeparation.Value:.3f} mm; screw clearance {clearance:.6f} mm; saved.')


main()
