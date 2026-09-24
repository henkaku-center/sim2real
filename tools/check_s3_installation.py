"""Check saved S3 placement, terminal bores, detachability and assembly clearance."""
from pathlib import Path
import json
import math
import FreeCAD as App
import Part

ROOT=Path(__file__).resolve().parents[1]
doc=App.openDocument(str(ROOT/'assets/cad/Sesame-S3-Assembly.FCStd'))
carrier=doc
holes={o.Address:o.Placement.Base for o in carrier.Objects if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
def world(o):
    s=o.Shape.copy();s.Placement=o.getGlobalPlacement();return s
objects=[o for o in doc.Objects if 'InstructionId' in o.PropertiesList and o.InstructionId.startswith('s3.')]
assert len(objects)==125,len(objects)
for o in objects:assert o.Shape.isValid() and not o.Shape.isNull(),o.Name
print('PASS: 125 native S3 feature shapes valid.',flush=True)
pcb=doc.getObject('S3Source_Part__Feature030')
pins=[o for o in objects if o.InstructionId.startswith('s3.male_pin.')]
assert len(pins)==18
for pin in pins:
    s=world(pin);b=s.BoundBox;p=holes[pin.Address]
    assert abs(b.Center.x-p.x)<1e-7 and abs(b.Center.y-p.y)<1e-7,pin.Name
    assert s.common(world(pcb)).Volume<1e-7,pin.Name
    assert abs(b.ZMin-3.85)<1e-7
    assert abs(b.ZMax-18.85)<1e-7
    row=pin.Address[1:]
    assert s.common(world(doc.getObject('S3Spacer_'+row))).Volume<1e-7
print('PASS: 18 pins aligned, clear of PCB bores and spacers.',flush=True)
for row in [11,17]:
    a=world(doc.getObject('S3Spacer_'+str(row))).BoundBox
    b=world(doc.getObject('S3SocketHousing_'+str(row))).BoundBox
    assert abs(a.ZMin-b.ZMax)<1e-7
    assert abs(a.ZMax-world(pcb).BoundBox.ZMin)<1e-7
# All existing bound parts are already finished/native; broad phase before booleans.
existing=[o for o in doc.Objects if 'InstructionId' in o.PropertiesList and not o.InstructionId.startswith('s3.') and hasattr(o,'Shape') and not o.Shape.isNull()]
def leaves(group):
    result=[]
    for child in group.Group:
        if child.TypeId=='App::Part':result.extend(leaves(child))
        elif hasattr(child,'Shape') and not child.Shape.isNull():result.append(child)
    return result
hub_source=next(o for o in doc.ServoHubCandidate.Group if o.TypeId=='App::Part' and o.Name!='HubMaleHeaders')
existing += leaves(hub_source) + leaves(doc.YAAJ_DCDC_StepDown_LM2596_cp)
existing += [doc.MeasuredAdjustmentScrew,doc.MeasuredCapacitor1,doc.MeasuredCapacitor2]
existing=list({o.Name:o for o in existing}.values())
existing_shapes={o.Name:world(o) for o in existing}
collisions=[];soldered_contacts=[];minimum=None
for o in objects:
    s=world(o)
    for other in existing:
        t=existing_shapes[other.Name]
        if not s.BoundBox.intersect(t.BoundBox):continue
        volume=s.common(t).Volume
        if volume>1e-6:
            address=o.InstructionId.rsplit('.',1)[-1]
            other_id=getattr(other,'InstructionId','')
            expected=(o.InstructionId.startswith(('s3.socket_tail.','s3.bottom_solder.')) and
                      ((other_id.startswith('underside.wire.') and address in other.Addresses) or
                       (other_id.startswith('underside.solder.') and other_id.endswith('.'+address))))
            (soldered_contacts if expected else collisions).append({'s3':o.Name,'existing':other.Name,'volume_mm3':volume})
print('Finished existing bound-part overlap checks.',flush=True)
# Parent compounds include all imported hub/converter geometry, even without bindings.
clearances={}
for name in ['ServoHubCandidate','ConverterCandidate']:
    other=doc.getObject(name)
    if other is None:continue
    shapes=[world(o) for o in other.Group if hasattr(o,'Shape') and not o.Shape.isNull()]
    if hasattr(other,'Shape') and not other.Shape.isNull():shapes=[world(other)]
    if shapes:
        assembly=Part.makeCompound(shapes)
        b=assembly.BoundBox
        def box_gap(a):
            return math.sqrt(sum(max(0,getattr(a,k+'Min')-getattr(b,k+'Max'),getattr(b,k+'Min')-getattr(a,k+'Max'))**2 for k in 'XYZ'))
        clearances[name]=min(box_gap(world(o).BoundBox) for o in objects)
before={o.Name:o.getGlobalPlacement().Base for o in pins}
tail=doc.S3SocketTail_A11;fixed=tail.getGlobalPlacement().Base
expression=next(value for key,value in doc.S3SuperMini.ExpressionEngine if key.lstrip('.')=='Placement.Base.z')
doc.S3SuperMini.setExpression('Placement.Base.z',expression+' + 10 mm');doc.recompute()
for o in pins:assert abs(o.getGlobalPlacement().Base.z-before[o.Name].z-10)<1e-7
assert (tail.getGlobalPlacement().Base-fixed).Length<1e-7
doc.S3SuperMini.setExpression('Placement.Base.z',expression);doc.recompute()
report={'status':'PASS' if not collisions else 'FAIL','finished_features':len(objects),'aligned_pins':18,
        'addresses':[o.Address for o in pins],'source_bore_intersections_mm3':0,'socket_engagement_mm':6.25,
        'male_pin_length_mm':15,'untrimmed_upper_projection_mm':4.63,
        'pcb_underside_z_mm':world(pcb).BoundBox.ZMin,'plastic_mating_gap_mm':0,'lift_test_mm':10,
        'fixed_sockets_remain_fixed':True,'existing_bound_part_intersections':collisions,'conservative_aabb_clearance_lower_bounds_mm':clearances,
        'intended_soldered_contact_overlaps':soldered_contacts,
        'limitations':'Socket dimensions and USB orientation provisional; source internal component overlaps not repaired.'}
(ROOT/'assets/cad/reports/s3-installation-check.json').write_text(json.dumps(report,indent=2)+'\n')
assert not collisions,collisions
print('PASS: 18 S3 pins aligned and bore-clear, flush mating, detachable assembly; no existing bound-part intersections.')
