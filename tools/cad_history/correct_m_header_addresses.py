"""Move the existing M strip to confirmed M12-M15 without replacing objects."""
from pathlib import Path
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[2]
doc = next(d for d in App.listDocuments().values() if d.FileName == str(ROOT/'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'))
carrier = next(d for d in App.listDocuments().values() if d.FileName == str(ROOT/'assets/cad/work/Sesame-S3-circuitry.FCStd'))
holes = {o.Address:o.Placement.Base for o in carrier.Objects if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
pins = [o for o in doc.Objects if 'InstructionId' in o.PropertiesList and o.InstructionId.startswith('auxiliary.pin.M')]
assert sorted(o.Address for o in pins) == ['M13','M14','M15','M16'], 'Correction already applied or strip changed; inspect native CAD.'
doc.openTransaction('Correct instructor-confirmed header addresses to M12-M15')
try:
    for pin in pins:
        old = pin.Address
        new = 'M'+str(int(old[1:])-1)
        pin.setExpression('Placement.Base.y',f'{holes[new].y} mm - CarrierConnections.PinWidth/2')
        pin.Address = new
        pin.InstructionId = 'auxiliary.pin.'+new
        pin.Label = 'Auxiliary pin '+new
        solder = doc.getObject('AuxSolder_'+old)
        solder.Base.Placement.Base.y = holes[new].y
        solder.InstructionId = 'aux.solder.'+new
        solder.Label = 'Auxiliary solder '+new
    doc.AuxSpacerBlank_M.Placement.Base.y = holes['M12'].y-1.27
    doc.AuxiliaryHeaders.Label = 'Two 4-pin short-tail headers — X14-X17 / M12-M15'
    doc.CarrierConnections.Evidence = 'Instructor confirmed X14-X17 and corrected second strip to M12-M15. Red L4-L13/B3-B9, blue K5-K18, green J6-J14. Short-tail header dimensions provisional.'
    doc.recompute()
    for pin in pins:
        assert abs(pin.Shape.BoundBox.Center.y-holes[pin.Address].y)<1e-7
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise
doc.recompute()
doc.save()
print('PASS: existing M strip moved to confirmed M12-M15; native identities retained.')
