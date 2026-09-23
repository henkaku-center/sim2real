"""Read saved native assembly; test mating and removability without saving edits.

Run with freecadcmd. The PASS report is written only after every assertion succeeds.
"""
from pathlib import Path
import json
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'
REPORT = ROOT / 'assets/cad/reports/servo-hub-headers-check.json'


def world(obj):
    shape = obj.Shape.copy()
    shape.Placement = obj.getGlobalPlacement().multiply(obj.Placement.inverse()).multiply(shape.Placement)
    return shape


def main():
    doc = App.openDocument(str(FILE))
    carrier = App.openDocument(str(ROOT / 'assets/cad/work/Sesame-S3-circuitry.FCStd'))
    holes = {o.Address: o for o in carrier.Objects if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
    finished = [o for o in doc.Objects if 'InstructionId' in o.PropertiesList]
    assert len(finished) == 66
    for obj in finished:
        assert obj.Shape.isValid() and not obj.Shape.isNull(), obj.Name
    rows = []
    for col in ['A', 'X']:
        housing = world(doc.getObject('SocketHousing_'+col))
        original = world(doc.getObject('OriginalSpacer_'+col))
        donor = world(doc.getObject('DonorSpacer_'+col))
        assert abs(original.BoundBox.ZMin-housing.BoundBox.ZMax)<1e-7
        for row in range(3, 9):
            address = f'{col}{row}'
            pin = world(doc.getObject('HubMalePin_'+address))
            tail = world(doc.getObject('SocketTail_'+address))
            target = holes[address].Placement.Base
            for shape in [pin, tail]:
                assert abs(shape.BoundBox.Center.x-target.x)<1e-7
                assert abs(shape.BoundBox.Center.y-target.y)<1e-7
            assert abs(pin.BoundBox.Center.z-original.BoundBox.Center.z)<1e-7
            assert abs(pin.BoundBox.ZLength-15)<1e-7
            pcb_top = doc.ServoHubCandidate.Placement.Base.z + doc.HubInstallation.HubPCBThickness.Value
            assert abs(pin.BoundBox.ZMax-pcb_top-2.15)<1e-7
            cone = doc.getObject('SocketBottomSolder_'+address+'Blank')
            assert cone.Radius2.Value > cone.Radius1.Value
            assert abs(cone.Placement.Base.z+cone.Height.Value)<1e-7
            for solid in [housing, original, donor, world(doc.getObject('SocketContact_'+address)), tail]:
                assert pin.common(solid).Volume < 1e-7, address
            engagement = housing.BoundBox.ZMax-pin.BoundBox.ZMin
            assert abs(engagement-6.25)<1e-7
            rows.append({'address': address, 'engagement_mm': round(engagement, 6)})
    clearance = world(doc.ServoHubCandidate).distToShape(world(doc.MeasuredAdjustmentScrew))[0]
    assert abs(clearance-.4836487153819995)<1e-6
    # A temporary hub lift must translate male features and leave socket solids fixed.
    male = doc.HubMalePin_A3
    before_male = world(male).BoundBox.ZMin
    before_fixed = world(doc.HubFemaleSockets).BoundBox.ZMin
    original_height = doc.HubInstallation.PCBSeparation.Value
    doc.HubInstallation.PCBSeparation = original_height+10
    doc.recompute()
    assert abs(world(male).BoundBox.ZMin-before_male-10)<1e-7
    assert abs(world(doc.HubFemaleSockets).BoundBox.ZMin-before_fixed)<1e-7
    assert world(male).BoundBox.ZMin > world(doc.SocketHousing_A).BoundBox.ZMax
    doc.HubInstallation.PCBSeparation = original_height
    doc.recompute()
    for obj in finished:
        assert obj.Shape.isValid(), obj.Name
    report = {'status': 'PASS', 'finished_features': len(finished),
              'saved_document_reopened': True, 'terminals': rows,
              'symmetric_about_original_spacer': True,
              'purchased_male_pin_length_mm': 15,
              'modeled_upper_projection_mm': 2.15,
              'instructor_approximate_upper_projection_mm': 2,
              'underside_solder_widest_at_board': True,
              'plastic_mating_gap_mm': 0,
              'modeled_screw_clearance_mm': clearance,
              'male_housing_spacer_contact_tail_overlap_mm3': 0,
              'temporary_lift_mm': 10, 'carrier_sockets_stayed_fixed': True,
              'test_edits_saved': False,
              'limitations': 'Provisional dimensions; simplified contact sleeves, not spring/contact-force simulation; upper pins modeled untrimmed.'}
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print('PASS: 66 valid features; 12 aligned 15 mm symmetric pins; 2.15 mm upper projection; solder widest at board; flush seating, 6.25 mm engagement, 0.484 mm screw clearance; sockets fixed during 10 mm lift. No test edits saved.')


main()
