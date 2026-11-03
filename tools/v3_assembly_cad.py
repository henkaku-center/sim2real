"""Fit the authorized, normalized Loftwork V3 frame, shell and lid to APS."""
import hashlib
import json
import math
import time
from pathlib import Path
import FreeCAD as App
import Part
import MeshPart
from tools.body_cad import load_electronics,bounds,export_step,write_stl
from tools.cad_validation_cache import CheckCache,shape_digest,check_electronics,check_servo_bays,check_ribbons

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'assets/printing/internal-frame-s3/reference-v3'
V=App.Vector


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,data):Path(path).write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def translated(shape,offset):
    result=shape.copy();result.translate(V(*offset));return result


def cylinders(shape,radius,predicate=lambda f:True):
    groups={}
    for face in shape.Faces:
        c=face.Surface
        if not isinstance(c,Part.Cylinder) or abs(c.Axis.z)<.999 or abs(c.Radius-radius)>1e-5 or not predicate(face):continue
        key=(round(c.Center.x,6),round(c.Center.y,6),round(face.BoundBox.ZMin,6),round(face.BoundBox.ZMax,6))
        groups.setdefault(key,[]).append(face)
    return groups


def rounded_notches(shape,x,width,top):
    b=shape.BoundBox;r=2.;span=b.YLength+2;z=b.ZMin-1
    pieces=[Part.makeBox(width,span,top-r-z,V(x-width/2,b.YMin-1,z)),Part.makeBox(width-2*r,span,r,V(x-width/2+r,b.YMin-1,top-r))]
    pieces += [Part.makeCylinder(r,span,V(x+side*(width/2-r),b.YMin-1,top-r),V(0,1,0)) for side in [-1,1]]
    return shape.cut(pieces[0].multiFuse(pieces[1:]))


def windows(shape,width=(20,24)):
    found=[]
    for face in shape.Faces:
        c=face.Surface
        if not isinstance(c,Part.Plane) or c.Axis.x<.9 or not .1<c.Axis.z<.5:continue
        for wire in face.Wires:
            b=wire.BoundBox
            if width[0]<b.YLength<width[1] and 10<b.ZLength<15:
                found.append({'bounds_mm':bounds(wire),'centre_mm':list(b.Center),'normal':list(c.Axis),'width_mm':b.YLength,'height_mm':b.ZLength/c.Axis.x})
    return sorted(found,key=lambda w:w['centre_mm'][1])


def window(shape):
    found=windows(shape)
    if not found:raise AssertionError('V3 OLED aperture not found')
    return found[0]


def stretch_y(shape,plane,widen,refine=True):
    """Translate the two outer halves apart and bridge them with the exact
    section at each cut. Only valid where every face crossing the cut is
    prismatic along Y, so no hole, boss or curve changes shape."""
    for face in shape.Faces:
        s,b=face.Surface,face.BoundBox
        if b.YLength<1e-6 or not any(b.YMin<c<b.YMax for c in [-plane,plane]):continue
        prismatic=isinstance(s,Part.Plane) and abs(s.Axis.y)<1e-9 or isinstance(s,Part.Cylinder) and abs(abs(s.Axis.y)-1)<1e-9
        assert prismatic,('Stretch plane crosses a non-prismatic face',plane,b)
    half=widen/2;big=400
    pieces=[shape.common(Part.makeBox(big,2*plane,big,V(-big/2,-plane,-big/2)))]
    for side in [-1,1]:
        outer=shape.common(Part.makeBox(big,big,big,V(-big/2,plane if side>0 else -plane-big,-big/2)))
        pieces.append(translated(outer,[0,side*half,0]))
        section=Part.makeFace(shape.slice(V(0,1,0),side*plane),'Part::FaceMakerBullseye')
        bridge=section.extrude(V(0,half,0));bridge.translate(V(0,0 if side>0 else -half,0))
        pieces.append(bridge)
    result=pieces[0].multiFuse(pieces[1:])
    # Keep the seam faces when another cut follows: merged faces across a seam
    # make later slices and Booleans unreliable. The last operation refines.
    if refine:result=result.removeSplitter()
    result=Part.makeSolid(max(result.Shells,key=lambda shell:shell.Area)) if len(result.Solids)!=1 else result.Solids[0]
    area=sum(Part.makeFace(shape.slice(V(0,1,0),side*plane),'Part::FaceMakerBullseye').Area for side in [-1,1])
    assert result.isValid() and result.isClosed() and abs(result.Volume-shape.Volume-area*half)<1e-3*shape.Volume,(result.Volume,shape.Volume,area*half)
    assert abs(result.BoundBox.YLength-shape.BoundBox.YLength-widen)<1e-6
    return result


def extend_x(shape,plane,length):
    """Lengthen by moving everything ahead of one prismatic X cut forward and
    bridging the gap with that cut's exact section."""
    for face in shape.Faces:
        s,b=face.Surface,face.BoundBox
        if b.XLength<1e-6 or not b.XMin<plane<b.XMax:continue
        prismatic=isinstance(s,Part.Plane) and abs(s.Axis.x)<1e-9 or isinstance(s,Part.Cylinder) and abs(abs(s.Axis.x)-1)<1e-9
        assert prismatic,('Lengthening plane crosses a non-prismatic face',plane,b)
    big=600
    rear=shape.common(Part.makeBox(big,big,big,V(plane-big,-big/2,-big/2)))
    front=translated(shape.common(Part.makeBox(big,big,big,V(plane,-big/2,-big/2))),[length,0,0])
    section=Part.makeFace(shape.slice(V(1,0,0),plane),'Part::FaceMakerBullseye')
    bridge=section.extrude(V(length,0,0))
    result=rear.multiFuse([bridge,front]).removeSplitter()
    result=Part.makeSolid(max(result.Shells,key=lambda shell:shell.Area)) if len(result.Solids)!=1 else result.Solids[0]
    assert result.isValid() and result.isClosed() and abs(result.Volume-shape.Volume-section.Area*length)<1e-3*shape.Volume
    assert abs(result.BoundBox.XLength-shape.BoundBox.XLength-length)<1e-6
    return result


def transplant_bays(source,target,x_range,shift,y_limit):
    """Copy the outer bay band of an existing leg station into the bridge."""
    lo,hi=x_range;big=600
    keep=lambda shape,x0,x1,side:shape.common(Part.makeBox(x1-x0,big,big,V(x0,y_limit if side>0 else -y_limit-big,-big/2)))
    blocks=[translated(keep(source,lo,hi,side),[shift,0,0]) for side in [-1,1]]
    hole=Part.makeCompound([Part.makeBox(hi-lo,big,big,V(lo+shift,y_limit if side>0 else -y_limit-big,-big/2)) for side in [-1,1]])
    result=target.cut(hole).multiFuse(blocks).removeSplitter()
    assert result.isValid() and len(result.Solids)==1 and result.isClosed(),('Transplanted bays are not joined to the body',len(result.Solids))
    return result.Solids[0],blocks


def split_window(head,bar):
    """Close the centre of one widened aperture, leaving two equal eyes, using
    the wall's own section beside the opening."""
    (wide,)=windows(head,(40,400))
    lo,hi=wide['bounds_mm'];y=hi[1]+1.5
    section=Part.makeFace(head.slice(V(0,1,0),y),'Part::FaceMakerBullseye')
    section=section.common(Part.makeBox(30,30,hi[2]-lo[2]+3,V(lo[0]-6,y-15,lo[2]-1.5)))
    centre=wide['centre_mm'][1];fill=section.extrude(V(0,bar,0));fill.translate(V(0,centre-y-bar/2,0))
    head=head.fuse(fill).removeSplitter()
    assert head.isValid() and len(head.Solids)==1
    eyes=windows(head);assert len(eyes)==2,eyes
    assert abs(eyes[0]['centre_mm'][1]+eyes[1]['centre_mm'][1]-2*centre)<1e-6 and abs(eyes[0]['width_mm']-eyes[1]['width_mm'])<1e-6
    return head


def load_references(names=None):
    source=json.loads((REF/'source.json').read_text());ref={}
    for name,record in source['files'].items():
        if names is not None and name not in names:continue
        path=REF/(name+'.step');assert sha(path)==record['normalized_sha256'];ref[name]=Part.read(str(path))
        assert ref[name].isValid() and len(ref[name].Solids)==1 and ref[name].isClosed()
    return source,ref


def frame_layout(frame,deck,h=0):
    mounts={};hips={}
    case_axes=cylinders(frame,.95,lambda f:abs(f.Surface.Center.y)>30+h and f.BoundBox.ZMax>deck-1)
    for side,left in [('L',True),('R',False)]:
        holes=sorted({(x,y) for x,y,lo,hi in case_axes if (y>0)==left},reverse=True)
        pairs=[holes[i:i+2][::-1] for i in range(0,len(holes),2)];assert len(pairs) in (2,3) and all(len(p)==2 for p in pairs)
        # Front first, rear last; a middle pair (six legs) copies the front bay.
        names=[side+'1',side+'5',side+'2'] if len(pairs)==3 else [side+'1',side+'2']
        for name,pair in zip(names,pairs):
            front=name[1]!='2'
            centre=[sum(p[i] for p in pair)/2 for i in [0,1]];assert abs(pair[1][0]-pair[0][0]-27.8)<1e-4
            mounts[name]={'holes':pair,'caseCenter':centre};hips[name]=[centre[0]+(1 if front else -1)*5.375,centre[1]]
    slot_centres={(round(f.Surface.Center.x,6),round(f.Surface.Center.y,6)) for f in frame.Faces if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Axis.z)>.999 and abs(f.Surface.Radius-2.54)<1e-5 and abs(f.Surface.Center.x)<10 and abs(f.Surface.Center.y)>35+h}
    assert len(slot_centres)==4
    mid=sum(x for x,y in slot_centres)/4;half=abs(mounts['L1']['caseCenter'][1])-25.4
    channel={'midpoint_x_mm':mid,'side_offset_mm':half,'foot_lane_y_mm':half+15.4,'hip_lane_y_mm':half+17.0}
    return mounts,hips,channel


def fit_head(ref,settings,mid,usb,variant=None):
    """The same native head construction for interactive preview and full checks."""
    variant=variant or {};h=variant.get('widen_mm',0)/2;ahead=variant.get('middle_legs',{}).get('lengthen_mm',0)
    head=ref['head'].copy()
    if variant.get('eyes')==2:head=split_window(head,variant['eye_bar_mm'])
    eyes=windows(head);original_window=eyes[0];z=settings['height_splice_z_mm'];raise_mm=settings['raise_mm']
    entries=lower_entries(head,settings['cable_entry']['z_mm'])
    # Reconstruct the two unwanted upper side openings from an intact section
    # of the same tapered wall, including its native lid-seat profile.
    port_x=(-21.7575,-6.7575);port_floor=42.210127293763
    section=Part.makeFace(head.slice(V(1,0,0),mid),'Part::FaceMakerBullseye')
    section=section.common(Part.makeBox(300,300,80,V(-150,-150,port_floor-.1)))
    patch=section.extrude(V(port_x[1]-port_x[0]+.2,0,0));patch.translate(V(port_x[0]-.1-mid,0,0))
    head=head.fuse(patch)
    assert original_window['bounds_mm'][1][2]<z
    if raise_mm:
        low=head.common(Part.makeBox(300,300,z+150,V(-150,-150,-150)));high=head.common(Part.makeBox(300,300,150-z,V(-150,-150,z)))
        section=Part.makeFace(head.slice(V(0,0,1),z),'Part::FaceMakerBullseye')
        head=low.fuse(section.extrude(V(0,0,raise_mm))).fuse(translated(high,[0,0,raise_mm]))
    lid=translated(ref['lid'],[0,0,raise_mm]);roof=lid.BoundBox.ZMax
    # Remove the old bore faces and heal the tapered wall, then put the toggle at the
    # rear panel's horizontal centre. Retain the original height above the hub.
    bore_faces=[f for f in head.Faces if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Radius-2.5)<1e-6 and f.Surface.Axis.x<-.9]
    old_bores=[f.Surface for f in bore_faces]
    assert old_bores and all((b.Center-old_bores[0].Center).Length<1e-6 for b in old_bores)
    old=old_bores[0];cy=(head.BoundBox.YMin+head.BoundBox.YMax)/2
    recess=[f for f in head.Faces if isinstance(f.Surface,Part.Plane) and f.BoundBox.XMax<-30 and f.BoundBox.YMin>old.Center.y-2.71 and f.BoundBox.YMax<old.Center.y+2.71 and f.BoundBox.ZMin>old.Center.z-5 and f.BoundBox.ZMax<old.Center.z+5]
    assert len(recess)==5
    before_fill=head.Volume
    head=head.defeaturing(bore_faces+recess)
    assert before_fill+60<head.Volume<before_fill+70
    cz=old.Center.z
    cx=old.Center.x-old.Axis.z/old.Axis.x*(cz-old.Center.z)
    switch_centre=V(cx,cy,cz)
    head=head.cut(Part.makeCylinder(2.5,20,switch_centre-old.Axis*10,old.Axis))
    assert head.isValid() and len(head.Solids)==1
    ear_source=json.loads((REF.parent/'reference-ears/source.json').read_text());ears=[]
    for name,record in ear_source['files'].items():
        path=REF.parent/'reference-ears'/(name+'.step');assert sha(path)==record['sha256']
        ear=Part.read(str(path));base=ear_source['base_z_mm'];extension=settings['ear_extension_mm']
        section=Part.makeFace(ear.slice(V(0,0,1),base+.001),'Part::FaceMakerBullseye')
        ear=translated(ear,[0,0,extension]).fuse(section.extrude(V(0,0,extension)))
        ear.translate(V(settings['ear_forward_mm']+ahead,(settings['ear_spread_mm']+h)*(1 if name=='left' else -1),head.BoundBox.ZMax-1-base))
        assert ear.isValid() and len(ear.Solids)==1
        ears.append(ear)
    # Fixed front shoulders support the ears. A T-shaped removable lid covers
    # the rear roof and extends forward between them, as in the instructor sketch.
    split_x=min(e.BoundBox.XMin for e in ears)-.25
    tongue=min(abs(e.BoundBox.YMin if e.BoundBox.Center.y>0 else e.BoundBox.YMax) for e in ears)
    corners=Part.makeCompound([Part.makeBox(100,100,100,V(split_x,tongue if side>0 else -100-tongue,0)) for side in [-1,1]])
    shoulders=translated(lid.common(corners),[0,0,-.1])
    gap=settings['lid_clearance_mm']
    lid=lid.cut(Part.makeCompound([Part.makeBox(100,100,100,V(split_x-gap,tongue-gap if side>0 else -100-tongue+gap,0)) for side in [-1,1]]))
    # Preserve Jom/Paul's native V3 captive rail profile and mating clearance.
    # The flare beneath the shell overhang blocks vertical removal on purpose.
    # Only the T-shaped shoulder split above uses our separate plan clearance.
    head=head.multiFuse([shoulders,*ears])
    usb_y=(usb.YMin+usb.YMax)/2;usb_z=(usb.ZMin+usb.ZMax)/2
    usb_cut=Part.makeBox(usb.XMin-head.BoundBox.XMin+2,12,7,V(head.BoundBox.XMin-1,usb_y-6,usb_z-3.5));head=head.cut(usb_cut)
    power=settings['battery_entry'];w=power['width_mm'];r=power['corner_radius_mm']
    frame=ref['frame'];power_axes=cylinders(frame,1.,lambda f:f.Surface.Center.x>0 and f.Surface.Center.y<0 and abs(f.BoundBox.ZMax-frame.BoundBox.ZMax)<1e-5)
    assert len(power_axes)==2
    power_x=sum(x for x,y,lo,hi in power_axes)/2;bottom=head.BoundBox.ZMin-1;top=head.BoundBox.ZMin+power['height_mm']
    cuts=[Part.makeBox(w,40,top-r-bottom,V(power_x-w/2,-55-h,bottom)),Part.makeBox(w-2*r,40,r,V(power_x-w/2+r,-55-h,top-r))]
    cuts.extend(Part.makeCylinder(r,40,V(power_x+side*(w/2-r),-55-h,top-r),V(0,1,0)) for side in [-1,1])
    head=head.cut(cuts[0].multiFuse(cuts[1:]))
    battery_entry={'side':'right','centre_x_mm':power_x,'width_mm':w,'bottom_z_mm':bottom+1,'top_z_mm':top,'corner_radius_mm':r,'wire_z_mm':power['wire_z_mm'],'bottom_open':True,'aligned_to':'native front-right frame power channel'}
    opening=head.common(Part.makeLine(V(power_x,-40-h,power['wire_z_mm']),V(power_x,-20-h,power['wire_z_mm'])))
    opposite=head.common(Part.makeLine(V(power_x,20+h,power['wire_z_mm']),V(power_x,40+h,power['wire_z_mm'])))
    assert sum(e.Length for e in opening.Edges)<1e-6 and sum(e.Length for e in opposite.Edges)>1
    assert head.isValid() and len(head.Solids)==1
    refined=head.removeSplitter()
    unified=refined.isValid() and abs(refined.Volume-head.Volume)<1e-3
    if unified:head=refined
    # Grafting the hollow original ear profiles onto the fixed roof shoulders
    # encloses tiny internal pockets. Seal only those disconnected void shells;
    # the exterior, OLED opening and bottom-open cable entries remain unchanged.
    void_count=len(head.Shells)-1;before_volume=head.Volume
    head=Part.makeSolid(max(head.Shells,key=lambda shell:shell.Area))
    void_volume=head.Volume-before_volume
    assert 0<=void_volume<before_volume*.01,(void_volume,before_volume,len(head.Shells))
    for zz in [44.,46.]:
        samples=ref['head'].common(Part.makeLine(V(mid,-35-h,zz),V(mid,35+h,zz))).Edges
        assert len(samples)==2
        for edge in samples:
            point=V(sum(port_x)/2,edge.BoundBox.Center.y,zz)
            assert not ref['head'].isInside(point,1e-6,False) and head.isInside(point,1e-6,False)
    assert all(s.isValid() and len(s.Solids)==1 and s.isClosed() for s in [head,lid])
    fitted_eyes=windows(head);fitted_window=fitted_eyes[0];assert len(fitted_eyes)==len(eyes)
    for before,after in zip(eyes,fitted_eyes):
        assert max(abs(a-b) for p,q in zip(before['bounds_mm'],after['bounds_mm']) for a,b in zip(p,q))<1e-5
    head_lid_overlap=head.common(lid);assert head_lid_overlap.isNull() or head_lid_overlap.isValid();assert abs(head_lid_overlap.Volume)<1e-3
    capture=[]
    for lift in [.25,.5,1]:
        overlap=head.common(translated(lid,[0,0,lift]));assert overlap.isNull() or overlap.isValid()
        assert overlap.Volume>1,(lift,overlap.Volume)
        capture.append({'lift_mm':lift,'intersection_mm3':overlap.Volume})
    slide=[]
    travel=lid.BoundBox.XLength+14
    for i in range(41):
        offset=-travel*(1-i/40)
        overlap=head.common(translated(lid,[offset,0,0]));assert overlap.isNull() or overlap.isValid()
        assert abs(overlap.Volume)<1e-3,(offset,overlap.Volume)
        slide.append({'rear_offset_mm':offset,'z_offset_mm':0,'intersection_mm3':overlap.Volume})
    switch_holes=[f.Surface for f in head.Faces if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Radius-2.5)<1e-6 and f.Surface.Axis.x<-.9]
    assert len(switch_holes)==1
    switch_hole=switch_holes[0]
    assert (switch_hole.Center-switch_centre).cross(switch_hole.Axis).Length<1e-6
    old_fill=head.common(Part.makeLine(old.Center-old.Axis*5,old.Center+old.Axis*5))
    old_fill_mm=sum(e.Length for e in old_fill.Edges);assert 1.99<old_fill_mm<2.01
    new_open=head.common(Part.makeLine(switch_centre-old.Axis*5,switch_centre+old.Axis*5))
    assert sum(e.Length for e in new_open.Edges)<1e-6
    details={'display_windows':fitted_eyes,'cable_notches':entries,'battery_entry':battery_entry,'closed_upper_side_ports':2,'ear_source':ear_source,
              'switch_opening':{'centre_mm':list(switch_centre),'normal':list(switch_hole.Axis),'diameter_mm':5.,'source':'rear-panel horizontally centred tail switch; original height retained above servo hub; former bore closed',
                                'old_centre_mm':list(old.Center),'panel_centre_y_mm':cy,'height_retained':True,'old_bore_filled_mm':old_fill_mm,'old_recess_removed':True},
             'sealed_internal_voids':{'count':void_count,'volume_mm3':void_volume},'unified_external_faces':unified,
             'ear_bounds_mm':[bounds(e) for e in ears],'ear_height_above_roof_mm':max(e.BoundBox.ZMax for e in ears)-roof,
              'lid_capture_samples':capture,'lid_slide_samples':slide,'lid_plan':{'shape':'T-shaped rear roof with a front tongue between fixed ears','roof_z_mm':roof,
                          'mating_profile':'unchanged native V3 captive underhang','assembly_direction':'rear-to-front at fixed Z',
                         'tongue_half_width_mm':tongue-gap,'shoulder_start_x_mm':split_x,'clearance_mm':gap}}
    return head,lid,fitted_window,head_lid_overlap,usb_cut,details


def lower_entries(head,z):
    b=head.BoundBox;edges=head.common(Part.makeLine(V(-12,b.YMin+1,z),V(12,b.YMin+1,z))).Edges
    assert len(edges)==2
    edges=sorted(edges,key=lambda e:e.BoundBox.XMin);left=edges[0].BoundBox.XMax;right=edges[1].BoundBox.XMin
    candidates=[v.Point.z for f in head.Faces if isinstance(f.Surface,Part.Plane) and abs(f.Surface.Axis.y)>.999
                for v in f.Vertexes if abs(v.Point.x)<12 and v.Point.z<b.ZMin+12]
    return {'count':2,'bottom_open':True,'source':'unchanged native V3 lower entries','centre_x_mm':(left+right)/2,
            'width_mm':right-left,'bottom_z_mm':b.ZMin,'top_z_mm':max(candidates),'top_corner_radius_mm':1.6,
            'entry_z_mm':z,'side_y_mm':[b.YMin,b.YMax]}


def make_spacer(params):
    spacer=Part.makeCylinder(params['pcb_standoff_radius_mm'],params['pcb_standoff_height_mm']).cut(Part.makeCylinder(params['pcb_spacer_bore_mm']/2,params['pcb_standoff_height_mm']))
    assert spacer.isValid() and spacer.isClosed() and len(spacer.Solids)==1
    return spacer


def fit_frame(original,params,pcb_holes,skip_contained=False):
    frame=original.copy();deck=frame.BoundBox.ZMax
    old_holes=cylinders(frame,.95,lambda f:abs(f.BoundBox.ZMax-deck)<1e-5);assert len(old_holes)==4
    frame=frame.multiFuse([Part.makeCylinder(.95,hi-lo,V(x,y,lo)) for x,y,lo,hi in old_holes])
    depth=params['pcb_pilot_depth_mm']+params['pcb_pilot_floor_mm']
    bosses=[Part.makeCylinder(params['pcb_standoff_radius_mm'],depth,V(x,y,deck-depth)) for x,y,_ in pcb_holes]
    # In a widened frame the deck already surrounds each boss; fusing a fully
    # contained cylinder adds no material and can leave an invalid seam.
    if skip_contained:bosses=[b for b in bosses if abs(frame.common(b).Volume-b.Volume)>1e-6]
    if bosses:frame=frame.multiFuse(bosses)
    frame=frame.cut(Part.makeCompound([Part.makeCylinder(params['pcb_pilot_diameter_mm']/2,params['pcb_pilot_depth_mm'],V(x,y,deck-params['pcb_pilot_depth_mm'])) for x,y,_ in pcb_holes]))
    assert frame.isValid() and len(frame.Solids)==1 and abs(frame.BoundBox.ZMax-deck)<1e-6
    for x,y,_ in pcb_holes:
        assert not frame.isInside(V(x,y,deck-.1),1e-6,False)
        assert frame.isInside(V(x,y,deck-params['pcb_pilot_depth_mm']-params['pcb_pilot_floor_mm']/2),1e-6,False)
    return frame,old_holes


def preview_datums(out):
    """Cache only immutable input measurements, never fit-check results."""
    files=['assets/cad/Sesame-S3-Assembly.FCStd','assets/cad/instructions/assembly-cad-snapshot.json',
           'assets/printing/internal-frame-s3/reference-v3/frame.step','assets/printing/internal-frame-s3/reference-v3/source.json',
           'tools/body_cad.py','tools/v3_assembly_cad.py']
    key={'files':{name:sha(ROOT/name) for name in files},'freecad':App.Version(),'occt':Part.OCC_VERSION}
    path=out/'preview-inputs.json'
    if path.exists():
        try:
            cached=json.loads(path.read_text())
            if cached['key']==key:return cached['datums'],True
        except (ValueError,KeyError):pass
    _,ref=load_references({'frame'});deck=ref['frame'].BoundBox.ZMax
    _,_,channel=frame_layout(ref['frame'],deck)
    native,electronics,_,holes,_=load_electronics()
    data={'deck_z_mm':deck,'midpoint_x_mm':channel['midpoint_x_mm'],
          'pcb_half_size_mm':[native.Carrier.Length.Value/2,native.Carrier.Width.Value/2],
          'usb_native_bounds_mm':bounds(electronics['S3Source_Part__Feature022']),
          'pcb_native_holes_mm':holes}
    out.mkdir(parents=True,exist_ok=True);write(path,{'key':key,'datums':data})
    return data,False


def preview_head(params,out):
    return preview_part(params,out,'head')


def preview_part(params,out,kind='head'):
    """Fast native STEP preview, explicitly separate from a release receipt."""
    if out.resolve()==REF.parent.resolve() or (out/'assembly.json').exists():
        raise ValueError('Use a separate preview directory; this directory holds release artifacts')
    started=time.perf_counter()
    details={};cached=False
    if kind=='spacer':
        shape=make_spacer(params);shapes=[('pcb-spacer',shape)];checks=['closed valid spacer']
    else:
        datums,cached=preview_datums(out);deck=datums['deck_z_mm'];seat=deck+params['pcb_standoff_height_mm']
        cx,cy=datums['pcb_half_size_mm']
        if kind=='head':
            _,ref=load_references({'head','lid','frame'});lo,hi=datums['usb_native_bounds_mm']
            usb=App.BoundBox(cx-hi[0],cy-hi[1],lo[2]+seat,cx-lo[0],cy-lo[1],hi[2]+seat)
            head,lid,aperture,overlap,_,features=fit_head(ref,params['head_cover'],datums['midpoint_x_mm'],usb)
            assert head.BoundBox.ZMin>=deck-1e-6
            shapes=[('head-cover',head),('head-lid',lid)]
            details={'display_window':aperture,'lid_intersection_mm3':overlap.Volume,**features}
            checks=['closed valid shell/lid','unchanged OLED aperture','shell/lid overlap','head base above frame deck']
        elif kind=='frame':
            _,ref=load_references({'frame'});holes=[[cx-x,cy-y,seat] for x,y in datums['pcb_native_holes_mm']]
            frame,_=fit_frame(ref['frame'],params,holes)
            shapes=[('internal-frame',frame)]
            checks=['valid frame','flat deck','clear pilot axes','pilot floors']
        else:raise ValueError('Unknown preview part: '+kind)
    out.mkdir(parents=True,exist_ok=True)
    parts={};view_name=kind+'-preview'
    for name,shape in [*shapes,(view_name,Part.makeCompound([s for _,s in shapes]))]:
        path=out/(name+'.step');export_step(shape,path)
        parts[name]={'step_sha256':sha(path),'bounds_mm':bounds(shape),'volume_mm3':shape.Volume}
        if name==view_name:
            mesh=MeshPart.meshFromShape(Shape=shape,LinearDeflection=params['mesh_deflection_mm'],AngularDeflection=.2,Relative=False)
            # Touching shell/lid solids may share edges in this display mesh.
            # It is an assembly preview, not a single printable solid.
            if len(shapes)==1:assert mesh.isSolid()
            write_stl(out/(view_name+'.stl'),mesh)
            parts[name]['stl_sha256']=sha(out/(view_name+'.stl'))
    report={'schema':1,'mode':view_name,'parameters':params,'parts':parts,
            'checks':checks,
            'unchecked':['electronics intersections','spacer clearance','mounting axes','ribbon clearance','leg poses','slicing','physical fit'],
            'source_script_sha256':sha(__file__),'electronics_sha256':sha(ROOT/'assets/cad/Sesame-S3-Assembly.FCStd'),
            'reference_sha256':sha(REF/'source.json'),**details,
            'input_cache_hit':cached,'elapsed_seconds':time.perf_counter()-started}
    write(out/'preview.json',report)
    print(json.dumps({'mode':view_name,'seconds':report['elapsed_seconds'],'input_cache_hit':cached,'view_file':str(out/(view_name+'.step')),'full_assembly_checks':'not run'},indent=2),flush=True)
    return report


def build(params,out,include_cover=True,datums_only=False,fresh_checks=False,check_cache=None):
    source,ref=load_references()
    variant=params.get('variant');h=variant.get('widen_mm',0)/2 if variant else 0
    legs=(variant or {}).get('middle_legs');middle_blocks=[]
    if variant and h:
        print('V3: widening the reference frame, cover, shell and lid',flush=True)
        for name in ['frame','bottom','head','lid']:ref[name]=stretch_y(ref[name],variant['stretch_plane_y_mm'],variant['widen_mm'],refine=name in ('head','lid') and not legs)
    if legs:
        print('V3: lengthening and adding a middle leg station',flush=True)
        L=legs['lengthen_mm']
        for name in ['frame','bottom']:
            extended=extend_x(ref[name],legs['body_plane_x_mm'],L)
            ref[name],blocks=transplant_bays(ref[name],extended,legs['bay_x_range_mm'],legs['bay_shift_mm'],legs['bay_y_limit_mm']+h)
            if name=='frame':middle_blocks=blocks
        for name in ['head','lid']:ref[name]=extend_x(ref[name],legs['head_plane_x_mm'],L)
    frame=ref['frame'].copy();deck=frame.BoundBox.ZMax;seat=deck+params['pcb_standoff_height_mm']
    native,electronics,_,holes,hole_diameter=load_electronics()
    pcb_size=[native.Carrier.Length.Value,native.Carrier.Width.Value,native.Carrier.Shape.BoundBox.ZLength];cx,cy=pcb_size[0]/2,pcb_size[1]/2
    pcb_holes=[[cx-x,cy-y,seat] for x,y in holes]
    mounts,hips,channel=frame_layout(frame,deck,h);mid=channel['midpoint_x_mm']
    datums={'reference_family':'loftwork-printing-v3','reference_sha256':sha(REF/'source.json'),'parameters':params,'pcb_seat_z_mm':seat,'servo_flange_seat_z_mm':deck,
            'head_cable_entry':lower_entries(ref['head'],params['head_cover']['cable_entry']['z_mm']),
            'source_frame_bounds_mm':bounds(frame),'head_reference_bounds_mm':bounds(ref['head']),'parts':{'internal-frame':{'bounds_mm':bounds(frame)}},'servo_mounts':mounts,'hip_shaft_xy_mm':hips,'channel_layout':channel}
    out.mkdir(parents=True,exist_ok=True);write(out/'frame-datums.json',datums)
    if datums_only:return datums
    print('V3: fitting PCB pilots and separate spacers',flush=True)
    frame,old_holes=fit_frame(frame,params,pcb_holes,bool(variant))
    spacer=make_spacer(params)
    origins=[[x,y,deck] for x,y,_ in pcb_holes];spacers=[translated(spacer,p) for p in origins]
    lowest=min(s.BoundBox.ZMin for s in electronics.values());penetration=params['pcb_screw_length_mm']-pcb_size[2]-params['pcb_standoff_height_mm']
    assert 2*params['pcb_screw_diameter_mm']<=penetration<params['pcb_pilot_depth_mm']
    matrix=App.Matrix(-1,0,0,cx,0,-1,0,cy,0,0,1,seat,0,0,0,1)
    for s in electronics.values():s.transformShape(matrix)
    settings=params['head_cover'];z=settings['height_splice_z_mm'];raise_mm=settings['raise_mm']
    head,lid,fitted_window,head_lid_overlap,usb_cut,head_features=fit_head(ref,settings,mid,electronics['S3Source_Part__Feature022'].BoundBox,variant)
    assert head.BoundBox.ZMin>=frame.BoundBox.ZMax-1e-6
    print('V3: checking electronics, spacers, shell and lid',flush=True)
    cache=CheckCache(check_cache or ROOT/'tests/artifacts/printing-check-cache',
        {'checker':sha(ROOT/'tools/cad_validation_cache.py'),'loader':sha(ROOT/'tools/body_cad.py'),
         'freecad':App.Version(),'occt':Part.OCC_VERSION},fresh=fresh_checks)
    electronics_key={'source':sha(ROOT/'assets/cad/Sesame-S3-Assembly.FCStd'),
                     'snapshot':sha(ROOT/'assets/cad/instructions/assembly-cad-snapshot.json'),'placement':[cx,cy,seat]}
    # Native Boolean/classifier calls can populate a shape's internal caches.
    # Freeze identities before any optional check so a hit cannot change the
    # identity used by a later group.
    checked_solids=[('frame',frame),*[(f'spacer-{i}',s) for i,s in enumerate(spacers)],('head',head),('lid',lid)]
    geometry_keys={name:shape_digest(solid) for name,solid in checked_solids}
    reference_frame_key=shape_digest(ref['frame'])
    collisions=[]
    for name,solid in checked_solids:
        cache.run('electronics/'+name,{'solid':geometry_keys[name],'electronics':electronics_key},lambda:check_electronics(solid,electronics))
    assert not collisions,collisions
    spacer_gaps=[head.distToShape(s)[0] for s in spacers];assert min(spacer_gaps)>=.6,spacer_gaps
    bottom=ref['bottom'];overlap=frame.common(bottom);assert overlap.isNull() or overlap.isValid();assert abs(overlap.Volume)<.01,overlap.Volume
    frame_under=sorted({(x,y) for x,y,lo,hi in cylinders(frame,.95,lambda f:abs(f.Surface.Center.y)<.001 and f.BoundBox.ZMax<0)})
    cover_under=sorted({(round(f.Surface.Center.x,6),round(f.Surface.Center.y,6)) for f in bottom.Faces if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Axis.z)>.999 and abs(f.Surface.Center.y)<.001 and abs(f.BoundBox.ZMax-bottom.BoundBox.ZMax)<1e-4})
    assert len(frame_under)==len(cover_under)==2
    assert max(abs(a-b) for p,q in zip(frame_under,cover_under) for a,b in zip(p,q))<1e-3
    head_axes=sorted({(x,y) for x,y,lo,hi in cylinders(head,.95,lambda f:abs(f.BoundBox.ZMin-deck)<1e-4)})
    frame_head=sorted({(x,y) for x,y,lo,hi in cylinders(frame,1.15,lambda f:abs(f.BoundBox.ZMax-deck)<1e-4)})
    assert len(head_axes)==len(frame_head)==4 and max(abs(a-b) for p,q in zip(head_axes,frame_head) for a,b in zip(p,q))<1e-3
    # The V3 opening already lies at the robot's front-right. Its two R1
    # cylindrical corner faces are fillets, not extra screw holes.
    port_corners=cylinders(frame,1.,lambda f:f.Surface.Center.x>0 and f.Surface.Center.y<0 and abs(f.BoundBox.ZMax-deck)<1e-5)
    assert len(port_corners)==2
    port_x=sum(x for x,y,lo,hi in port_corners)/2
    assert not frame.isInside(V(port_x,-28-h,deck-.1),1e-6,False)
    for y in [14.7+h,31.3+h]:assert frame.isInside(V(port_x,y,-5),1e-6,False)
    for y in [-14.7-h,-31.3-h,-31.8-h]:assert not frame.isInside(V(port_x,y,-5),1e-6,False)
    channel_checks=[]
    # Unrefined widened solids give exact Boolean volumes, but point
    # classification is reliable only on the face-merged copy.
    probe=frame.removeSplitter() if variant else frame
    def sampled(x,sign,zz):
        # Widened solids carry bridge seams; classify points rather than
        # trusting how a Boolean splits section edges along them.
        inside=[probe.isInside(V(x,sign*(12+h+i*.05),zz),1e-6,False) for i in range(401)]
        runs=[];start=None
        for i,v in enumerate(inside+[False]):
            if v and start is None:start=i
            if not v and start is not None:runs.append([round(12+h+start*.05,2),round(12+h+(i-1)*.05,2)]);start=None
        return [r for r in runs if r[1]-r[0]>.2]  # Drop single-sample classifier noise on seam faces.
    for x in [-port_x,-20,-15]:
        for zz in [-5,-10]:
            if variant:
                sections=[sampled(x,sign,zz) for sign in [-1,1]];tolerance=.051
            else:
                sections=[];tolerance=1e-3
                for sign in [-1,1]:
                    es=frame.common(Part.makeLine(V(x,sign*12,zz),V(x,sign*32,zz))).Edges
                    sections.append(sorted([sorted([abs(e.BoundBox.YMin),abs(e.BoundBox.YMax)]) for e in es]))
            assert len(sections[0])==len(sections[1])
            assert all(abs(a-b)<tolerance for p,q in zip(*sections) for a,b in zip(p,q)),(x,zz,sections)
            channel_checks.append({'x_mm':x,'z_mm':zz,'left_right_intervals_mm':sections})
    # Protect the V3 servo bays; the PCB edits are strictly inboard of them.
    # A widened variant moves the bays outward with the walls; old PCB holes
    # are filled inside that band, so compare the bays beyond it (1 mm clear
    # of the widening seams, where Boolean clipping differs by tolerance).
    bay_boundary=31.8751+(h+1 if variant else 0)
    # Variant solids carry translation seams; OCC Booleans in the PCB fit can
    # shave up to ~0.15 mm at a seam-adjacent corner. Recorded, not hidden.
    bay_tolerance=.2 if variant else 1e-4
    bay_checks=cache.run('servo-bays',{'frame':geometry_keys['frame'],'reference':reference_frame_key,'boundary':bay_boundary,'tolerance':bay_tolerance},lambda:check_servo_bays(ref['frame'],frame,bay_boundary,bay_tolerance))
    cables_path=ROOT/'assets/printing/internal-frame-s3/head-cable-clearance.json';cables=json.loads(cables_path.read_text())
    if variant:cables=None
    def same(a,b):
        if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
        if isinstance(a,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
        if isinstance(a,(int,float)) and not isinstance(a,bool):return abs(a-b)<1e-5
        return a==b
    leg_checks=[];boxes=[bounds(head),bounds(lid)];limits=[[min(b[0][i] for b in boxes) for i in range(3)],[max(b[1][i] for b in boxes) for i in range(3)]]
    if cables:
        assert same(cables['assembly_datums'],datums),'Routing samples use different frame/PCB datums'
        assert cables['entry_min_gap_mm']>=.2
        print('V3: checking authored ribbon and leg clearance samples',flush=True)
        ribbon_check=cache.run('ribbons',{'head':geometry_keys['head'],'lid':geometry_keys['lid'],'routes':sha(cables_path),'settings':settings,'midpoint':mid,'electronics':electronics_key},lambda:check_ribbons(head,lid,cables,settings,mid,electronics))
        queries=ribbon_check['classified']
        for item in cables['leg_samples']:
            box=item['bounds_mm'];assert any(box[1][i]<limits[0][i] or box[0][i]>limits[1][i] for i in range(3)),(item['part'],item['pose'])
            leg_checks.append({'part':item['part'],'pose':item['pose'],'separated_from_head':True})
    else:
        # Authored ribbon routes and leg samples belong to the base datums.
        ribbon_check={'electronics_inside':None};queries=None
    parts={}
    def export(name,shape):
        assert shape.isValid() and len(shape.Solids)==1 and shape.isClosed(),name
        mesh=MeshPart.meshFromShape(Shape=shape,LinearDeflection=params['mesh_deflection_mm'],AngularDeflection=.2,Relative=False);assert mesh.isSolid(),name
        write_stl(out/(name+'.stl'),mesh);export_step(shape,out/(name+'.step'))
        parts[name]={'bounds_mm':bounds(shape),'volume_mm3':shape.Volume,'triangles':mesh.CountFacets,'stl_sha256':sha(out/(name+'.stl')),'step_sha256':sha(out/(name+'.step')),'valid_solid':True,'closed_mesh':True}
    for name,shape in [('internal-frame',frame),('pcb-spacer',spacer),('head-cover',head),('head-lid',lid),('bottom-cover',bottom)]:export(name,shape)
    parts['pcb-spacer'].update(quantity=4,assembly_origins_mm=origins,print_rotation_axis_angle=[1,0,0,0])
    for name,shape,angle in [('internal-frame',frame,180),('head-cover',head,0),('head-lid',lid,180)]:
        oriented=shape.copy()
        if angle:oriented.rotate(V(0,0,0),V(1,0,0),angle)
        oriented.translate(V(0,0,-oriented.BoundBox.ZMin))
        mesh=MeshPart.meshFromShape(Shape=oriented,LinearDeflection=params['mesh_deflection_mm'],AngularDeflection=.2,Relative=False);assert mesh.isSolid()
        filename=name+'-print.stl';write_stl(out/filename,mesh)
        parts[name].update(print_rotation_axis_angle=[1,0,0,angle],print_stl=filename,print_stl_sha256=sha(out/filename),print_bounds_mm=bounds(oriented))
    edges=frame.common(Part.makeLine(V(mid,-100,deck-.5),V(mid,100,deck-.5))).Edges
    support=max(e.BoundBox.YMax for e in edges)-min(e.BoundBox.YMin for e in edges)
    report={**datums,'schema_version':2,'units':'mm','coordinates':'X front/OLED, Y left, Z up; PCB USB toward rear','source':source,
            'validation_cache':cache.records,'validation_checker_sha256':sha(ROOT/'tools/cad_validation_cache.py'),
            'source_script_sha256':sha(__file__),'entry_script_sha256':sha(ROOT/'tools/internal_frame_cad.py'),'pcb_size_mm':pcb_size,'pcb_hole_diameter_mm':hole_diameter,'pcb_mount_holes_mm':pcb_holes,
            'pcb_side_margin_mm':(support-pcb_size[1])/2,'support_width_mm':support,'electronics_sha256':sha(ROOT/'assets/cad/Sesame-S3-Assembly.FCStd'),'electronics_shapes_checked':len(electronics),'electronics_intersections':collisions,'parts':parts,
            'pcb_hole_adjustment':{'source_axes':[[x,y] for x,y,lo,hi in old_holes],'destination_axes':[[x,y] for x,y,_ in pcb_holes],'source_diameter_mm':1.9,'pilot_diameter_mm':params['pcb_pilot_diameter_mm']},
            'bottom_cover_fasteners':{'frame':frame_under,'cover':cover_under,'matching_axes':True,'frame_intersection_mm3':overlap.Volume},'head_mount_axes_xy_mm':frame_head,'servo_bay_checks':bay_checks,
            'battery_wire_cutout':{'location':'front-right','centre_x_mm':port_x,'corner_radius_mm':1.,'source':'native V3 opening','other_channel_walls_intact':True,'new_cutout_wall_clear':True,'opposite_channel_section_checks':channel_checks},
            'pcb_fastening':{'board_thickness_mm':pcb_size[2],'spacer_height_mm':params['pcb_standoff_height_mm'],'screw_diameter_mm':params['pcb_screw_diameter_mm'],'screw_under_head_length_mm':params['pcb_screw_length_mm'],'nominal_frame_penetration_mm':penetration,'pilot_depth_mm':params['pcb_pilot_depth_mm'],'tip_clearance_mm':params['pcb_pilot_depth_mm']-penetration,'minimum_pilot_floor_mm':params['pcb_pilot_floor_mm'],'model_underside_projection_mm':-lowest,'model_deck_clearance_mm':params['pcb_standoff_height_mm']+lowest},
            'head_fit':{'source_object':'Loftwork V3 shell and removable lid','raise_mm':raise_mm,'height_splice_z_mm':z,'assembled_size_mm':[limits[1][i]-limits[0][i] for i in range(3)],'display_window':fitted_window,'display_window_unchanged':True,'spacer_clearances_mm':spacer_gaps,'electronics_intersections':collisions,'electronics_shapes_checked':len(electronics),'mount_axes_xy_mm':head_axes,'lid_intersection_mm3':head_lid_overlap.Volume,**head_features,**({'cable_surface_samples':len(cables['surface_points_mm']),'cable_samples_inside':0,'cable_samples_classified':queries,'cable_electronics_samples_inside':ribbon_check['electronics_inside'],'cable_entry_min_gap_mm':cables['entry_min_gap_mm'],'cable_reference_sha256':sha(cables_path)} if cables else {'cable_checks':'not run: authored ribbon routes are for the base frame'}),'leg_pose_checks':leg_checks,'usb_access_bounds_mm':bounds(usb_cut),'scope':'Final model fit and authored route samples; Rest/Standing leg bounds. No physical print or full-range motion test.'},
            'variant':variant,'unchanged_legs':{name:sha(ROOT/'assets/stl/upstream'/f'{name}-v117.stl') for name in ['L1','L2','L3','L4','R1','R2','R3','R4']},'fit_note':'V3-derived example; current PCB/spacer datums retained. CAD and sampled route checks are not physical fit evidence.'}
    write(out/'assembly.json',report);print(json.dumps({'parts':list(parts),'head_spacer_gaps_mm':spacer_gaps,'ribbon_queries':queries,'support_width_mm':support},indent=2),flush=True)
    return report
