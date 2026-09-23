"""Correct existing native header orientation, purchased length and underside solder.

Preserves native identities. Run in the existing GUI after flush seating.
"""
from pathlib import Path
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT/'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'


def main():
    doc = next(d for d in App.listDocuments().values() if d.FileName == str(FILE))
    p = doc.HubInstallation
    doc.openTransaction('Correct purchased symmetric headers and solder orientation')
    try:
        p.SymmetricExposedLength = 6.25
        p.OriginalSpacerHeight = 2.5
        p.SocketCavityDepth = 7
        if 'MeasuredUpperProtrusion' not in p.PropertiesList:
            p.addProperty('App::PropertyLength', 'MeasuredUpperProtrusion', 'Header evidence', 'Instructor measured ABOUT 2 mm above PCB; pins were not trimmed.')
        p.MeasuredUpperProtrusion = 2
        if 'PurchasedHeaderEvidence' not in p.PropertiesList:
            p.addProperty('App::PropertyString', 'PurchasedHeaderEvidence', 'Header evidence')
        p.PurchasedHeaderEvidence = 'PENGLIN B0FJ5NR96F, order 2026-09-14 and supplier listing: 15 mm total, 6.25 mm each side, implying 2.5 mm original spacer. Photos 10-12 indicate donor spacer on PCB side. Calculated upper projection 2.15 mm agrees with instructor about 2 mm, untrimmed. Female Youmile B0C13N6T48 purchased same day, installed identity not yet confirmed; 8.5 mm body and 7 mm cavity remain provisional.'
        p.Label = 'Hub installation — purchased dimensions and physical evidence'
        doc.ServoHubCandidate.Label = 'Servo hub — flush-seated detachable headers'
        doc.ServoHubCandidate.FitStatus = 'All twelve corrected hub bores aligned to A3-A8/X3-X8; flush spacer/socket mating. 13.5 mm modeled separation; 15 mm untrimmed symmetric pins; 2.15 mm upper protrusion. Socket internals remain provisional.'
        for col in ['A', 'X']:
            doc.getObject('OriginalSpacerBlank_'+col).setExpression('Placement.Base.z', '-HubInstallation.DonorSpacerHeight - HubInstallation.OriginalSpacerHeight')
            doc.getObject('DonorSpacerBlank_'+col).setExpression('Placement.Base.z', '-HubInstallation.DonorSpacerHeight')
            for row in range(3,9):
                pin = doc.getObject(f'HubMalePin_{col}{row}')
                pin.setExpression('Placement.Base.z', '-HubInstallation.DonorSpacerHeight - HubInstallation.OriginalSpacerHeight - HubInstallation.SymmetricExposedLength')
                cone = doc.getObject(f'SocketBottomSolder_{col}{row}Blank')
                cone.Radius1, cone.Radius2 = .48, .9
        doc.recompute()
        for obj in doc.Objects:
            if 'InstructionId' in obj.PropertiesList:
                assert obj.Shape.isValid(), obj.Name
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.save()
    print('PASS: 15 mm purchased pins, donor spacers on PCB side, 2.15 mm untrimmed projection; underside solder broad against board; saved.')


main()
