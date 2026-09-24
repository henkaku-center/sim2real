"""Add photo-addressed auxiliary headers and four insulated solid-wire jumpers.

Run once in the existing GUI. Native sketches/sweeps preserve editable wire paths.
M12-M15 is the instructor-confirmed correction to the original address wording.
"""
from pathlib import Path
import math
import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT/'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'


def main():
    doc = next(d for d in App.listDocuments().values() if d.FileName == str(FILE))
    carrier = next(d for d in App.listDocuments().values() if d.FileName == str(ROOT/'assets/cad/work/Sesame-S3-circuitry.FCStd'))
    holes = {o.Address: o.Placement.Base for o in carrier.Objects if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
    if doc.getObject('AuxiliaryHeaders'):
        raise RuntimeError('Auxiliary parts already exist; preserve native edits.')
    doc.openTransaction('Add two short-tail headers and four insulated jumpers')
    try:
        params = doc.addObject('App::FeaturePython','CarrierConnections')
        for name,value,note in [
            ('CarrierTopZ',1.6,'Existing carrier thickness.'),
            ('PinWidth',.64,'Provisional square section.'),
            ('SpacerHeight',2.5,'Provisional ordinary header spacer thickness.'),
            ('HeaderTopLength',6,'Provisional long mating end above spacer.'),
            ('HeaderTailLength',3,'Provisional short solder tail below spacer.'),
            ('SolderHeight',1,'Illustrative underside projection, not a measured maximum.'),
            ('WireCoreRadius',.25,'Illustrative solid conductor, gauge unverified.'),
            ('WireOuterRadius',.8,'Illustrative insulation outside radius.'),
            ('WireBendRadius',1.1,'Illustrative rounded bends, not photo measurement.'),
            ('WireCenterZ',3.15,'Illustrative horizontal centerline above carrier underside.'),
        ]:
            params.addProperty('App::PropertyLength',name,'Dimensions',note)
            setattr(params,name,value)
        params.addProperty('App::PropertyString','Evidence','Evidence')
        params.Evidence = 'Instructor confirmed X14-X17 and M12-M15. Red L4-L13/B3-B9, blue K5-K18, green J6-J14. Short-tail headers are ordinary purchased header style; dimensions provisional.'
        headers = doc.addObject('App::Part','AuxiliaryHeaders')
        headers.Label = 'Two 4-pin short-tail headers — X14-X17 / M12-M15'
        wires = doc.addObject('App::Part','CarrierJumpers')
        wires.Label = 'Four insulated jumper wires — physical addresses confirmed'
        finished, hidden = [], []
        def add(kind,name,group):
            o=doc.addObject(kind,name);group.addObject(o);return o
        def mark(o,semantic,color):
            o.addProperty('App::PropertyString','InstructionId','Construction');o.InstructionId=semantic
            o.ViewObject.ShapeColor=color;finished.append(o);return o
        def expr(o,prop,value):o.setExpression(prop,value.replace('$','CarrierConnections.'))
        def pin(address):
            point=holes[address]
            o=add('Part::Box','AuxPin_'+address,headers)
            expr(o,'Length','$PinWidth');expr(o,'Width','$PinWidth')
            expr(o,'Height','$HeaderTailLength + $SpacerHeight + $HeaderTopLength')
            expr(o,'Placement.Base.x',f'{point.x} mm - $PinWidth/2')
            expr(o,'Placement.Base.y',f'{point.y} mm - $PinWidth/2')
            expr(o,'Placement.Base.z','$CarrierTopZ - $HeaderTailLength')
            o.addProperty('App::PropertyString','Address','Construction');o.Address=address
            return mark(o,'auxiliary.pin.'+address,(.76,.77,.79))
        def solder(address,tool,group,prefix='Aux'):
            point=holes[address]
            cone=add('Part::Cone',prefix+'SolderBlank_'+address,group)
            cone.Radius1,cone.Radius2=.46,.9
            cone.Placement.Base=App.Vector(point.x,point.y,-1)
            expr(cone,'Height','$SolderHeight');expr(cone,'Placement.Base.z','-$SolderHeight')
            cut=add('Part::Cut',prefix+'Solder_'+address,group);cut.Base,cut.Tool=cone,tool
            hidden.append(cone);mark(cut,prefix.lower()+'.solder.'+address,(.70,.72,.74))
        for col,rows in [('X',range(14,18)),('M',range(12,16))]:
            pins=[pin(f'{col}{r}') for r in rows]
            blank=add('Part::Box','AuxSpacerBlank_'+col,headers)
            point=holes[f'{col}{rows.start}']
            blank.Length,blank.Width=2.54,4*2.54
            blank.Placement.Base=App.Vector(point.x-1.27,point.y-1.27,1.6)
            expr(blank,'Height','$SpacerHeight');expr(blank,'Placement.Base.z','$CarrierTopZ')
            tools=add('Part::MultiFuse','AuxSpacerTools_'+col,headers);tools.Shapes=pins
            spacer=add('Part::Cut','AuxSpacer_'+col,headers);spacer.Base,spacer.Tool=blank,tools
            hidden.extend([blank,tools]);mark(spacer,'auxiliary.spacer.'+col,(.09,.09,.10))
            for r,p in zip(rows,pins):solder(f'{col}{r}',p,headers)
        # Sketches lie in local YZ plane: sketch X is world Y, sketch Y is world Z.
        plane=App.Rotation(App.Vector(0,1,0),App.Vector(0,0,1),App.Vector(1,0,0),'ZXY')
        for name,a,b,color in [('Red_L','L4','L13',(.88,.035,.025)),
                                ('Red_B','B3','B9',(.88,.035,.025)),
                                ('Blue_K','K5','K18',(.025,.10,.65)),
                                ('Green_J','J6','J14',(.015,.55,.28))]:
            p0,p1=holes[a],holes[b]
            assert abs(p0.x-p1.x)<1e-7
            y0,y1=sorted([p0.y,p1.y]);z=params.WireCenterZ.Value;r=params.WireBendRadius.Value
            knee=z-r
            def vec(y,z):return App.Vector(y,z,0)
            curves=[Part.Arc(vec(y0,knee),vec(y0+r-r/math.sqrt(2),knee+r/math.sqrt(2)),vec(y0+r,z)),
                    Part.LineSegment(vec(y0+r,z),vec(y1-r,z)),
                    Part.Arc(vec(y1-r,z),vec(y1-r+r/math.sqrt(2),knee+r/math.sqrt(2)),vec(y1,knee))]
            for part,radius,core in [('Core',params.WireCoreRadius.Value,True),('Insulation',params.WireOuterRadius.Value,False)]:
                path=add('Sketcher::SketchObject','Jumper'+part+'Path_'+name,wires)
                path.Placement=App.Placement(App.Vector(p0.x,0,0),plane)
                edges=([Part.LineSegment(vec(y0,-.7),vec(y0,knee))]+curves+[Part.LineSegment(vec(y1,knee),vec(y1,-.7))]) if core else curves
                for edge in edges:path.addGeometry(edge,False)
                for i in range(len(edges)):path.addConstraint(Sketcher.Constraint('Block',i))
                profile=add('Sketcher::SketchObject','Jumper'+part+'Profile_'+name,wires)
                profile.Placement.Base=App.Vector(p0.x,y0,-.7 if core else knee)
                profile.addGeometry(Part.Circle(App.Vector(),App.Vector(0,0,1),radius),False)
                profile.addConstraint(Sketcher.Constraint('Diameter',0,2*radius))
                profile.setExpression('Constraints[0]','CarrierConnections.'+('WireCoreRadius' if core else 'WireOuterRadius')+' * 2')
                sweep=add('Part::Sweep','Jumper'+part+'_'+name,wires)
                sweep.Sections=[profile];sweep.Spine=(path,[]);sweep.Solid=True;sweep.Frenet=False
                hidden.extend([profile,path])
                if core:
                    core_obj=sweep;mark(sweep,'jumper.core.'+name,(.72,.39,.16))
                else:
                    insulation=add('Part::Cut','JumperSleeve_'+name,wires);insulation.Base,insulation.Tool=sweep,core_obj
                    hidden.append(sweep);mark(insulation,'jumper.insulation.'+name,color)
                    insulation.addProperty('App::PropertyStringList','Addresses','Construction');insulation.Addresses=[a,b]
                    insulation.addProperty('App::PropertyString','Evidence','Construction');insulation.Evidence='Endpoint addresses and color instructor-confirmed; diameter, bend profile and stripping length illustrative. Edit native path sketches for shape.'
            solder(a,core_obj,wires,'Jumper');solder(b,core_obj,wires,'Jumper')
        # User accepts inventory-linked female socket selection, not identification.
        doc.HubInstallation.PurchasedHeaderEvidence += ' Instructor subsequently selected an inventory/purchased socket reference: use Youmile B0C13N6T48; original installed origin unknown.'
        doc.recompute()
        for obj in finished:assert not obj.Shape.isNull() and obj.Shape.isValid(),obj.Name
        for obj in hidden:obj.ViewObject.Visibility=False
        for obj in finished:obj.ViewObject.Visibility=True
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction();raise
    doc.save()
    App.setActiveDocument(doc.Name)
    print(f'PASS: {len(finished)} new native header/wire/solder features; saved.')


main()
