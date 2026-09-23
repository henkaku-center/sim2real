"""Check saved native bare-wire geometry and photo-address endpoints."""
from pathlib import Path
import json
import FreeCAD as App
import Part

ROOT=Path(__file__).resolve().parents[1]
doc=App.openDocument(str(ROOT/'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'))
carrier=App.openDocument(str(ROOT/'assets/cad/work/Sesame-S3-circuitry.FCStd'))
holes={o.Address:o.Placement.Base for o in carrier.Objects if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
objects=[o for o in doc.Objects if 'InstructionId' in o.PropertiesList and o.InstructionId.startswith('underside.')]
wires=[o for o in objects if o.InstructionId.startswith('underside.wire.')]
assert len(wires)==16
for o in objects:assert o.Shape.isValid() and not o.Shape.isNull(),o.Name
for wire in wires:
    assert len(wire.Shape.Solids)==1,wire.Name
    assert wire.Shape.BoundBox.ZMax<0,wire.Name
    for address in wire.Addresses:
        p=holes[address];point=Part.Vertex(App.Vector(p.x,p.y,-.8))
        assert wire.Shape.isInside(point.Point,1e-7,True) or wire.Shape.distToShape(point)[0]<1e-7,(wire.Name,address)
contacts=[]
for i,a in enumerate(wires):
    for b in wires[i+1:]:
        if a.Shape.distToShape(b.Shape)[0]<1e-6:
            contacts.append([list(a.Addresses),list(b.Addresses)])
assert len(contacts)==4,contacts
routes=[list(o.Addresses) for o in wires]
routes += [list(o.Addresses) for o in doc.Objects if 'InstructionId' in o.PropertiesList and o.InstructionId.startswith('jumper.insulation.')]
expected_nets={
    'output_ground':['V1','A8','B11','M12'],
    'output_5V':['O1','A3','A11'],
    'logic_VCC':['A4','C11','M13'],
    'SCL':['A6','E17','M14'],
    'SDA':['A5','D17','M15'],
    'switched_input_positive':['X14','O17'],
    'battery_positive_to_switch':['X15','X16'],
    'battery_negative':['X17','V17'],
}
addresses=set(a for route in routes for a in route)|set(a for net in expected_nets.values() for a in net)
parent={a:a for a in addresses}
def root(a):
    while parent[a]!=a:a=parent[a]
    return a
def join(a,b):parent[root(a)]=root(b)
for route in routes:
    for a,b in zip(route,route[1:]):
        join(a,b)
        delta=holes[b]-holes[a]
        for address in addresses:
            offset=holes[address]-holes[a]
            if offset.cross(delta).Length<1e-7 and -1e-7<=offset.dot(delta)<=delta.dot(delta)+1e-7:
                join(a,address)
for name,net in expected_nets.items():assert len({root(a) for a in net})==1,(name,net)
assert len({root(net[0]) for net in expected_nets.values()})==len(expected_nets),'Unexpected diagram net merge'
report={'status':'PASS','wire_runs':16,'finished_features':len(objects),'all_endpoint_addresses_aligned':True,
        'all_wires_below_carrier':True,'bare_wire_contacts':contacts,
        'pending_confirmation':[],
        'diagram_cross_reference':'All thin-line routes and four thick jumper runs accounted for. B10-B11, M15-M18 and X15-X16 explicitly resolved by instructor top-view diagram.',
        'diagram_net_topology':expected_nets,'eight_distinct_diagram_nets':True,
        'electrical_validation':'Not performed; physical photo tracing only.'}
(ROOT/'assets/cad/reports/underside-wiring-check.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: 16 valid native bare-wire route segments; all endpoints aligned; four expected wire joins; diagram routes complete.')
