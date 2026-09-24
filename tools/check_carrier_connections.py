"""Validate saved carrier headers and editable jumper sweeps; no saved edits."""
from pathlib import Path
import json
import FreeCAD as App
import Part

ROOT=Path(__file__).resolve().parents[1]
doc=App.openDocument(str(ROOT/'assets/cad/Sesame-S3-Assembly.FCStd'))
carrier=doc
holes={o.Address:o.Placement.Base for o in carrier.Objects if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
features=[o for o in doc.Objects if 'InstructionId' in o.PropertiesList and o.InstructionId.startswith(('auxiliary.','aux.','jumper.'))]
assert len(features)==34
for o in features:assert o.Shape.isValid() and not o.Shape.isNull(),o.Name
pins={o.Address:o for o in features if o.InstructionId.startswith('auxiliary.pin.')}
for col,rows in [('X',range(14,18)),('M',range(12,16))]:
 for row in rows:
  a=f'{col}{row}';b=pins[a].Shape.BoundBox;p=holes[a]
  assert abs(b.Center.x-p.x)<1e-7 and abs(b.Center.y-p.y)<1e-7
  assert abs(b.ZMin+1.4)<1e-7
  assert pins[a].Shape.common(doc.getObject('AuxSpacer_'+col).Shape).Volume<1e-7
wires=[]
for name,a,b in [('Red_L','L4','L13'),('Red_B','B3','B9'),('Blue_K','K5','K18'),('Green_J','J6','J14')]:
 core=doc.getObject('JumperCore_'+name);sleeve=doc.getObject('JumperSleeve_'+name)
 for address in [a,b]:
  p=holes[address];tip=Part.Vertex(App.Vector(p.x,p.y,-.7))
  assert core.Shape.distToShape(tip)[0]<1e-7
 assert core.Shape.common(sleeve.Shape).Volume<1e-7
 assert sleeve.Shape.BoundBox.ZMin>1.6
 wires.append({'name':name,'addresses':[a,b],'span_mm':(holes[a]-holes[b]).Length})
for i,a in enumerate(features):
 if not a.InstructionId.startswith(('auxiliary.','jumper.core.','jumper.insulation.')):continue
 for b in features[i+1:]:
  if not b.InstructionId.startswith(('auxiliary.','jumper.core.','jumper.insulation.')):continue
  assert a.Shape.common(b.Shape).Volume<1e-6,(a.Name,b.Name)
report={'status':'PASS','finished_features':34,'headers':[['X'+str(i) for i in range(14,18)],['M'+str(i) for i in range(12,16)]],
        'M_header_evidence':'Instructor explicitly corrected the four-pin strip to M12-M15',
        'jumpers':wires,'native_sweeps_valid':True,'wire_cores_do_not_overlap_insulation':True,'new_header_wire_pair_intersections_mm3':0}
(ROOT/'assets/cad/reports/carrier-connections-check.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: eight header pins, four endpoint-aligned insulated sweeps, valid solids and no unintended pair intersections.')
