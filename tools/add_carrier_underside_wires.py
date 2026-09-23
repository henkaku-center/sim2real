"""Add traceable bare-wire runs from instructor's underside photo.

Ambiguous solder bridges are deliberately recorded as unresolved; this is a
physical routing model, not a verified electrical netlist.
"""
from pathlib import Path
import json
import FreeCAD as App

ROOT=Path(__file__).resolve().parents[1]
ROUTES=[
    ['X17','V17'], ['X14','O14','O17'], ['V1','V10','B10'],
    ['M12','M10'], ['M14','J14','E14','E17'], ['O1','B1','B3','A3'],
    ['J6','A6'], ['K5','A5'], ['L4','A4'], ['D10','D8','A8'],
    ['A11','A9','B9'], ['M18','K18','D18','D17'], ['M13','C13','C11'],
]


def main(routes=ROUTES, continuation=False):
    doc=next(d for d in App.listDocuments().values() if d.FileName.endswith('/LM2596-comparison.FCStd'))
    carrier=next(d for d in App.listDocuments().values() if d.FileName.endswith('/work/Sesame-S3-circuitry.FCStd'))
    holes={o.Address:o.Placement.Base for o in carrier.Objects if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
    assert continuation or not doc.getObject('CarrierUndersideWires'),'Already modeled; preserve native edits.'
    if continuation:assert not doc.getObject('UnderWireSegment_14_0'),'Diagram additions already exist.'
    doc.openTransaction('Add photo-traced bare underside wires and solder')
    try:
        group=doc.CarrierUndersideWires if continuation else doc.addObject('App::Part','CarrierUndersideWires')
        group.Label='Bare underside wiring — ambiguous junctions pending confirmation'
        p=doc.UndersideWiring if continuation else doc.addObject('App::FeaturePython','UndersideWiring')
        if not continuation:
            p.addProperty('App::PropertyLength','WireRadius','Dimensions');p.WireRadius=.25
            p.addProperty('App::PropertyFloat','WireCenterZ','Dimensions');p.WireCenterZ=-.8
            p.addProperty('App::PropertyString','Evidence','Evidence')
        p.Evidence='Instructor underside photo, 2026-09-24: stripped single-core wires. Addresses traced from printed grid (X at photo top, A bottom, 18 left, 1 right). 0.5 mm diameter and Z=-0.8 mm illustrative. B10-B11 ground bridge, M18-M15 SDA branch and X15-X16 battery-positive bridge await confirmation; C11 is on separate OLED VCC route. No continuity claim.'
        visible,hidden=[],[]
        def new(kind,name):
            o=doc.addObject(kind,name);group.addObject(o);return o
        def finish(o,key):
            o.ViewObject.ShapeColor=(.73,.70,.65)
            o.addProperty('App::PropertyString','InstructionId','Construction');o.InstructionId='underside.'+key
            visible.append(o);return o
        for index,route in enumerate(routes,14 if continuation else 1):
            parts=[]
            points=[App.Vector(holes[a].x,holes[a].y,p.WireCenterZ) for a in route]
            for j,(a,b) in enumerate(zip(points,points[1:])):
                delta=b-a
                wire=new('Part::Cylinder',f'UnderWireSegment_{index}_{j}')
                wire.setExpression('Radius','UndersideWiring.WireRadius');wire.Height=delta.Length
                wire.Placement=App.Placement(a,App.Rotation(App.Vector(0,0,1),delta))
                wire.setExpression('Placement.Base.z','UndersideWiring.WireCenterZ')
                parts.append(wire)
            for j,point in enumerate(points[1:-1]):
                bend=new('Part::Sphere',f'UnderWireBend_{index}_{j}')
                bend.setExpression('Radius','UndersideWiring.WireRadius');bend.Placement.Base=point
                bend.setExpression('Placement.Base.z','UndersideWiring.WireCenterZ');parts.append(bend)
            if len(parts)>1:
                wire=new('Part::MultiFuse',f'UnderWire_{index}');wire.Shapes=parts;hidden.extend(parts)
            else:wire=parts[0]
            finish(wire,f'wire.{index}')
            wire.addProperty('App::PropertyStringList','Addresses','Construction');wire.Addresses=route
            wire.Label='Bare wire: '+' → '.join(route)
            for j,address in enumerate(route):
                cone=new('Part::Cone',f'UnderWireSolderBlank_{index}_{j}')
                cone.Radius1,cone.Radius2,cone.Height=.43,.85,1
                cone.Placement.Base=App.Vector(holes[address].x,holes[address].y,-1)
                solder=new('Part::Cut',f'UnderWireSolder_{index}_{j}');solder.Base,solder.Tool=cone,wire
                hidden.append(cone);finish(solder,f'solder.{index}.{address}')
        if continuation:
            group.Label='Bare underside wiring — cross-checked against instructor diagram'
            p.Evidence='Instructor underside photo and top-view wiring diagram, 2026-09-24. Diagram confirms B10-B11 ground, M15-M18 SDA and X15-X16 battery-positive links. C11 is separate OLED VCC. All illustrated routes accounted for; physical continuity remains untested. Wire diameter 0.5 mm and center Z=-0.8 mm illustrative. Native segment boundaries are modeling choices, not confirmed cut lengths.'
        doc.recompute()
        for o in visible:assert not o.Shape.isNull() and o.Shape.isValid(),o.Name
        for o in hidden:o.ViewObject.Visibility=False
        for o in visible:o.ViewObject.Visibility=True
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction();raise
    doc.recompute();doc.save()
    print(f'PASS: {len(routes)} underside route segments saved; diagram completion={continuation}.')


if __name__ == '__main__' or __name__ == '<run_path>':
    main()
