"""Run once in the existing GUI; native primitives/expressions remain editable.

Dimensions below are provisional visualization choices, not purchased-part specs.
Original spacers center symmetric, untrimmed pins; donor spacers sit below them.
"""
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd'


def main():
    doc = next(d for d in App.listDocuments().values() if d.FileName == str(FILE))
    if doc.getObject('HubMaleHeaders'):
        raise RuntimeError('Headers already exist; preserve native edits.')
    doc.openTransaction('Add detachable hub headers, doubled spacers and sockets')
    try:
        p = doc.HubInstallation
        for name, value, note in [
            ('HeaderPitch', 2.54, 'Pitch retained from reference and carrier.'),
            ('HeaderPinWidth', .64, 'Provisional square pin width.'),
            ('OriginalSpacerHeight', 2.5, 'Provisional original plastic thickness.'),
            ('DonorSpacerHeight', 2.5, 'Provisional added plastic thickness.'),
            ('SymmetricExposedLength', 6, 'Provisional equal metal length beyond each side of ORIGINAL spacer; no upper trimming assumed.'),
            ('SocketHeight', 8.5, 'Provisional female housing height.'),
            ('SocketWidth', 2.54, 'Provisional housing/strip width.'),
            ('SocketCavityWidth', 1, 'Illustrative square housing cavity.'),
            ('SocketCavityDepth', 5, 'Illustrative blind cavity depth.'),
            ('ContactOpening', .72, 'Simplified receptacle opening; spring geometry not reconstructed.'),
            ('SocketTailProjection', .8, 'Provisional tail below carrier; trimming unconfirmed.'),
            ('HubPCBThickness', 1.6, 'Reference PCB thickness.'),
            ('HeaderSolderHeight', .5, 'Illustrative top solder height.'),
            ('SocketSolderHeight', 1, 'Illustrative carrier underside solder, not measured per joint.'),
        ]:
            p.addProperty('App::PropertyLength', name, 'Header assumptions', note)
            setattr(p, name, value)
        moving = doc.addObject('App::Part', 'HubMaleHeaders')
        moving.Label = 'Removable hub headers — symmetric pins and doubled spacers'
        doc.ServoHubCandidate.addObject(moving)
        fixed = doc.addObject('App::Part', 'HubFemaleSockets')
        fixed.Label = 'Carrier-fixed female sockets and solder'
        visible, hidden = [], []
        def new(kind, name, group):
            o = doc.addObject(kind, name)
            group.addObject(o)
            return o
        def expr(o, prop, value):
            o.setExpression(prop, value.replace('$', 'HubInstallation.'))
        def box(name, group, x, y, z, length, width, height):
            o = new('Part::Box', name, group)
            for prop, value in [('Placement.Base.x', x), ('Placement.Base.y', y),
                                ('Placement.Base.z', z), ('Length', length),
                                ('Width', width), ('Height', height)]:
                expr(o, prop, value)
            return o
        def finish(o, color, semantic):
            o.ViewObject.ShapeColor = color
            o.addProperty('App::PropertyString', 'InstructionId', 'Construction')
            o.InstructionId = semantic
            visible.append(o)
            return o
        def cut(name, group, base, tools):
            if len(tools) > 1:
                tool = new('Part::MultiFuse', name+'Tools', group)
                tool.Shapes = tools
                hidden.extend(tools)
            else:
                tool = tools[0]
            result = new('Part::Cut', name, group)
            result.Base, result.Tool = base, tool
            hidden.extend([base, tool])
            return result
        def solder(name, group, x, y, z, height, pin):
            cone = new('Part::Cone', name+'Blank', group)
            cone.Radius1, cone.Radius2 = .9, .48
            for prop, value in [('Placement.Base.x', x), ('Placement.Base.y', y),
                                ('Placement.Base.z', z), ('Height', height)]:
                expr(cone, prop, value)
            result = cut(name, group, cone, [pin])
            # The pin is also a finished visible object.
            return finish(result, (.70,.72,.74), name)
        for col, sign in [('A', 1), ('X', -1)]:
            x = f'{sign} * $RequiredRowSpan / 2'
            gx = f'{doc.ServoHubCandidate.Placement.Base.x} mm + ({x})'
            gy = f'{doc.ServoHubCandidate.Placement.Base.y} mm'
            pins, cavities = [], []
            for i, row in enumerate(range(3, 9)):
                a = f'{col}{row}'
                y = f'{i-2.5} * $HeaderPitch'
                wy = f'{gy} + ({y})'
                pin = box('HubMalePin_'+a, moving,
                          x+' - $HeaderPinWidth/2', y+' - $HeaderPinWidth/2',
                          '-$OriginalSpacerHeight - $SymmetricExposedLength',
                          '$HeaderPinWidth', '$HeaderPinWidth',
                          '$OriginalSpacerHeight + 2*$SymmetricExposedLength')
                pins.append(pin)
                finish(pin, (.82,.69,.32), 'hub.male_pin.'+a)
                solder('HubHeaderSolder_'+a, moving, x, y, '$HubPCBThickness', '$HeaderSolderHeight', pin)
                cavity = box('SocketCavity_'+a, fixed,
                             gx+' - $SocketCavityWidth/2', wy+' - $SocketCavityWidth/2',
                             '$CarrierTopZ + $SocketHeight - $SocketCavityDepth',
                             '$SocketCavityWidth', '$SocketCavityWidth', '$SocketCavityDepth')
                cavities.append(cavity)
                sleeve = box('SocketContactBlank_'+a, fixed,
                             gx+' - $SocketCavityWidth/2', wy+' - $SocketCavityWidth/2',
                             '$CarrierTopZ + $SocketHeight - $SocketCavityDepth',
                             '$SocketCavityWidth', '$SocketCavityWidth', '$SocketCavityDepth')
                bore = box('SocketContactBore_'+a, fixed,
                           gx+' - $ContactOpening/2', wy+' - $ContactOpening/2',
                           '$CarrierTopZ + $SocketHeight - $SocketCavityDepth',
                           '$ContactOpening', '$ContactOpening', '$SocketCavityDepth')
                finish(cut('SocketContact_'+a, fixed, sleeve, [bore]), (.82,.69,.32), 'hub.socket_contact.'+a)
                tail = box('SocketTail_'+a, fixed,
                           gx+' - $HeaderPinWidth/2', wy+' - $HeaderPinWidth/2',
                           '-$SocketTailProjection', '$HeaderPinWidth', '$HeaderPinWidth',
                           '$SocketTailProjection + $CarrierTopZ + $SocketHeight - $SocketCavityDepth')
                finish(tail, (.76,.77,.79), 'hub.socket_tail.'+a)
                solder('SocketBottomSolder_'+a, fixed, gx, wy,
                       '-$SocketSolderHeight', '$SocketSolderHeight', tail)
            for name, z, height in [
                ('OriginalSpacer', '-$OriginalSpacerHeight', '$OriginalSpacerHeight'),
                ('DonorSpacer', '-$OriginalSpacerHeight - $DonorSpacerHeight', '$DonorSpacerHeight')]:
                blank = box(name+'Blank_'+col, moving, x+' - $SocketWidth/2',
                            '-3*$HeaderPitch', z, '$SocketWidth', '6*$HeaderPitch', height)
                finish(cut(name+'_'+col, moving, blank, pins), (.10,.10,.11), 'hub.'+name+'.'+col)
            blank = box('SocketHousingBlank_'+col, fixed, gx+' - $SocketWidth/2',
                        gy+' - 3*$HeaderPitch', '$CarrierTopZ',
                        '$SocketWidth', '6*$HeaderPitch', '$SocketHeight')
            finish(cut('SocketHousing_'+col, fixed, blank, cavities), (.08,.08,.09), 'hub.socket_housing.'+col)
        doc.recompute()
        for o in visible:
            assert not o.Shape.isNull() and o.Shape.isValid(), o.Name
        for o in hidden:
            o.ViewObject.Visibility = False
        for o in visible:
            o.ViewObject.Visibility = True
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.recompute()
    doc.save()
    App.setActiveDocument(doc.Name)
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    Gui.activeDocument().activeView().saveImage(str(FILE.parent/'hub-headers-preview.png'),1600,1200,'White')
    print(f'PASS: {len(visible)} finished header/socket features; saved native assembly.')


main()
