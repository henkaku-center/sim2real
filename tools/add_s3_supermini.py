"""Install uploaded Zero geometry and editable detachable sockets at A11-I17.

Run once in the existing GUI. Source STEP geometry stays unscaled; material
changes are explicit approximations because the WROOM upload has no RGB styles.
"""
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'


def main():
    doc=next(d for d in App.listDocuments().values() if d.FileName==str(FILE))
    source=next(d for d in App.listDocuments().values() if d.FileName.endswith('/S3ZeroReference.FCStd'))
    carrier=next(d for d in App.listDocuments().values() if d.FileName.endswith('/work/Sesame-S3-circuitry.FCStd'))
    holes={o.Address:o.Placement.Base for o in carrier.Objects if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList}
    assert not doc.getObject('S3SuperMini'), 'Already installed; preserve native edits.'
    doc.openTransaction('Install socket-mounted S3 SuperMini at A11-I17')
    try:
        p=doc.addObject('App::FeaturePython','S3Installation')
        for name,value,note in [
            ('CarrierTopZ',1.6,'Existing carrier top.'),('SocketHeight',8.5,'Provisional Youmile-style female housing, not measured.'),
            ('SpacerHeight',2.5,'PENGLIN symmetric header reference: 15 - 2*6.25 mm.'),
            ('MaleMatingLength',6.25,'PENGLIN nominal exposed end; instructor confirms long centred S3 headers.'),('MaleSolderLength',6.25,'Equal exposed upper end, left untrimmed for expansion; instructor confirmed.'),
            ('PinWidth',.6,'Provisional square section fitting the source 0.9 mm bores.'),
            ('PCBThickness',1.62,'Uploaded Zero geometry bounding thickness includes pad surfaces.'),
            ('PCBTopLocalZ',.01,'Uploaded Zero top pad surface.'),
            ('PCBUndersideDepth',1.61,'Uploaded Zero bottom surface below local zero.'),
            ('SocketCavityDepth',7,'Provisional insertion cavity, following hub socket reference.'),
            ('SocketCavityWidth',1,'Simplified square cavity.'),('ContactOpening',.72,'Simplified sleeve opening, spring contact not recovered.'),
            ('TailProjection',1,'Illustrative underside tail projection.'),('SolderHeight',1,'Illustrative solder height.'),
            ('CenterX',(holes['A11'].x+holes['I17'].x)/2,'Center of instructor-specified footprint.'),
            ('CenterY',(holes['A11'].y+holes['I17'].y)/2,'Center of instructor-specified footprint.'),
        ]:
            p.addProperty('App::PropertyLength',name,'Dimensions',note);setattr(p,name,value)
        p.addProperty('App::PropertyString','Evidence','Evidence')
        p.Evidence='Instructor-selected uploaded ESP32-S3_Zero.step geometry; matches 18 x 23.5 mm PCB, 9 pins per row, 2.54 mm pitch, 15.24 mm row spacing. S3 spans A11-I17. USB toward A/outside edge inferred; stack heights provisional. WROOM upload has no COLOUR_RGB definitions; dark PCB/silver finish is an interpretation, not transferred source material.'
        moving=doc.addObject('App::Part','S3SuperMini');moving.Label='ESP32-S3 SuperMini — removable, A11-I17'
        moving.Placement.Rotation=App.Rotation(App.Vector(0,0,1),90)
        moving.setExpression('Placement.Base.x','S3Installation.CenterX')
        moving.setExpression('Placement.Base.y','S3Installation.CenterY')
        moving.setExpression('Placement.Base.z','S3Installation.CarrierTopZ + S3Installation.SocketHeight + S3Installation.SpacerHeight + S3Installation.PCBUndersideDepth')
        fixed=doc.addObject('App::Part','S3FemaleSockets');fixed.Label='Carrier-fixed S3 sockets — A11-I11 / A17-I17'
        visible,hidden=[],[]
        def new(kind,name,group):
            o=doc.addObject(kind,name);group.addObject(o);return o
        def expr(o,prop,value):o.setExpression(prop,value.replace('$','S3Installation.'))
        def box(name,group,x,y,z,l,w,h):
            o=new('Part::Box',name,group)
            for prop,value in [('Placement.Base.x',x),('Placement.Base.y',y),('Placement.Base.z',z),('Length',l),('Width',w),('Height',h)]:expr(o,prop,value)
            return o
        def finish(o,color,key):
            if color is not None:o.ViewObject.ShapeColor=color
            o.addProperty('App::PropertyString','InstructionId','Construction');o.InstructionId='s3.'+key
            visible.append(o);return o
        def cut(name,group,base,tools):
            if len(tools)>1:
                tool=new('Part::MultiFuse',name+'Tools',group);tool.Shapes=tools;hidden.extend(tools)
            else:tool=tools[0]
            o=new('Part::Cut',name,group);o.Base,o.Tool=base,tool;hidden.extend([base,tool]);return o
        # Retain imported component boundaries, source face assignments and identities.
        for original in source.Objects:
            if original.TypeId=='App::Part' or not hasattr(original,'Shape') or not original.Shape.Solids:continue
            o=new('PartDesign::Feature','S3Source_'+original.Name,moving)
            o.Shape=original.Shape.copy()
            materials=[]
            for material in original.ViewObject.ShapeAppearance:
                rgb=tuple(material.DiffuseColor)[:3]
                if abs(rgb[0]-.2196078)<.001 and abs(rgb[2]-.627451)<.001:
                    material.DiffuseColor=(.085,.09,.095)
                elif abs(rgb[0]-.9294118)<.001 and abs(rgb[1]-.8078431)<.001:
                    material.DiffuseColor=(.88,.66,.26)
                materials.append(material)
            o.ViewObject.ShapeAppearance=materials
            o.addProperty('App::PropertyString','SourceObject','Evidence');o.SourceObject=original.Name
            o.Label={'Part__Feature030':'S3 PCB and terminal pads','Part__Feature016':'S3 diagonal SoC','Part__Feature':'S3 red antenna','Part__Feature022':'S3 USB-C shell'}.get(original.Name,'S3 '+original.Label)
            finish(o,None,'component.'+original.Name)
        for row,lx in [(11,-7.62),(17,7.62)]:
            pins,cavities=[],[]
            for index,col in enumerate('ABCDEFGHI'):
                a=f'{col}{row}';ly=(index-4)*2.54;point=holes[a]
                pin=box('S3MalePin_'+a,moving,f'{lx} mm - $PinWidth/2',f'{ly} mm - $PinWidth/2',
                        '-$PCBUndersideDepth - $SpacerHeight - $MaleMatingLength','$PinWidth','$PinWidth',
                        '$MaleMatingLength + $SpacerHeight + $MaleSolderLength')
                pin.addProperty('App::PropertyString','Address','Construction');pin.Address=a
                pins.append(pin);finish(pin,(.76,.77,.79),'male_pin.'+a)
                cone=new('Part::Cone','S3TopSolderBlank_'+a,moving);cone.Radius1,cone.Radius2=.85,.43
                cone.Placement.Base=App.Vector(lx,ly,.01);expr(cone,'Height','$SolderHeight')
                finish(cut('S3TopSolder_'+a,moving,cone,[pin]),(.70,.72,.74),'top_solder.'+a)
                x=f'{point.x} mm';y=f'{point.y} mm'
                cavity=box('S3SocketCavity_'+a,fixed,x+' - $SocketCavityWidth/2',y+' - $SocketCavityWidth/2',
                           '$CarrierTopZ + $SocketHeight - $SocketCavityDepth','$SocketCavityWidth','$SocketCavityWidth','$SocketCavityDepth')
                cavities.append(cavity)
                sleeve=box('S3ContactBlank_'+a,fixed,x+' - $SocketCavityWidth/2',y+' - $SocketCavityWidth/2',
                           '$CarrierTopZ + $SocketHeight - $SocketCavityDepth','$SocketCavityWidth','$SocketCavityWidth','$SocketCavityDepth')
                bore=box('S3ContactBore_'+a,fixed,x+' - $ContactOpening/2',y+' - $ContactOpening/2',
                         '$CarrierTopZ + $SocketHeight - $SocketCavityDepth','$ContactOpening','$ContactOpening','$SocketCavityDepth')
                finish(cut('S3Contact_'+a,fixed,sleeve,[bore]),(.82,.69,.32),'socket_contact.'+a)
                tail=box('S3SocketTail_'+a,fixed,x+' - $PinWidth/2',y+' - $PinWidth/2','-$TailProjection',
                         '$PinWidth','$PinWidth','$TailProjection + $CarrierTopZ + $SocketHeight - $SocketCavityDepth')
                finish(tail,(.76,.77,.79),'socket_tail.'+a)
                cone=new('Part::Cone','S3BottomSolderBlank_'+a,fixed);cone.Radius1,cone.Radius2=.43,.85
                cone.Placement.Base=App.Vector(point.x,point.y,-1);expr(cone,'Height','$SolderHeight');expr(cone,'Placement.Base.z','-$SolderHeight')
                finish(cut('S3BottomSolder_'+a,fixed,cone,[tail]),(.70,.72,.74),'bottom_solder.'+a)
            blank=box('S3SpacerBlank_'+str(row),moving,f'{lx-1.27} mm','-11.43 mm','-$PCBUndersideDepth - $SpacerHeight','2.54 mm','22.86 mm','$SpacerHeight')
            finish(cut('S3Spacer_'+str(row),moving,blank,pins),(.08,.08,.09),'male_spacer.'+str(row))
            blank=box('S3SocketBlank_'+str(row),fixed,f'{holes["I"+str(row)].x-1.27} mm',f'{holes["A"+str(row)].y-1.27} mm',
                      '$CarrierTopZ','22.86 mm','2.54 mm','$SocketHeight')
            finish(cut('S3SocketHousing_'+str(row),fixed,blank,cavities),(.08,.08,.09),'socket_housing.'+str(row))
        service=doc.addObject('App::Part','S3ServiceEnvelopes')
        clearance=box('S3USBAccess',service,'$CenterX + 12.8 mm','$CenterY - 6 mm',
                      '$CarrierTopZ + $SocketHeight + $SpacerHeight','15 mm','12 mm','8 mm')
        clearance.Label='USB plug access — provisional 15 x 12 x 8 mm envelope'
        clearance.ViewObject.Transparency=85
        hidden.append(clearance);service.Visibility=False
        doc.recompute()
        for o in visible:assert not o.Shape.isNull() and o.Shape.isValid(),o.Name
        for o in hidden:o.ViewObject.Visibility=False
        for o in visible:o.ViewObject.Visibility=True
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction();raise
    doc.recompute();doc.save();App.setActiveDocument(doc.Name)
    view=Gui.activeDocument().activeView();camera=view.getCamera()
    view.viewAxonometric();view.fitAll();view.saveImage(str(FILE.parent/'s3-installed-preview.png'),1600,1200,'White');view.setCamera(camera)
    print(f'PASS: {len(visible)} S3 component/header/socket/solder objects saved.')


main()
