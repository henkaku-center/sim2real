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


def window(shape):
    for face in shape.Faces:
        c=face.Surface
        if not isinstance(c,Part.Plane) or c.Axis.x<.9 or not .1<c.Axis.z<.5:continue
        for wire in face.Wires:
            b=wire.BoundBox
            if 20<b.YLength<24 and 10<b.ZLength<15:
                return {'bounds_mm':bounds(wire),'centre_mm':list(b.Center),'normal':list(c.Axis),'width_mm':b.YLength,'height_mm':b.ZLength/c.Axis.x}
    raise AssertionError('V3 OLED aperture not found')


def load_references(names=None):
    source=json.loads((REF/'source.json').read_text());ref={}
    for name,record in source['files'].items():
        if names is not None and name not in names:continue
        path=REF/(name+'.step');assert sha(path)==record['normalized_sha256'];ref[name]=Part.read(str(path))
        assert ref[name].isValid() and len(ref[name].Solids)==1 and ref[name].isClosed()
    return source,ref


def frame_layout(frame,deck):
    mounts={};hips={}
    case_axes=cylinders(frame,.95,lambda f:abs(f.Surface.Center.y)>30 and f.BoundBox.ZMax>deck-1)
    for name,front,left in [('L1',True,True),('L2',False,True),('R1',True,False),('R2',False,False)]:
        pair=sorted({(x,y) for x,y,lo,hi in case_axes if (x>0)==front and (y>0)==left});assert len(pair)==2
        centre=[sum(p[i] for p in pair)/2 for i in [0,1]];assert abs(pair[1][0]-pair[0][0]-27.8)<1e-4
        mounts[name]={'holes':pair,'caseCenter':centre};hips[name]=[centre[0]+(1 if front else -1)*5.375,centre[1]]
    slot_centres={(round(f.Surface.Center.x,6),round(f.Surface.Center.y,6)) for f in frame.Faces if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Axis.z)>.999 and abs(f.Surface.Radius-2.54)<1e-5 and abs(f.Surface.Center.x)<10 and abs(f.Surface.Center.y)>35}
    assert len(slot_centres)==4
    mid=sum(x for x,y in slot_centres)/4;half=abs(mounts['L1']['caseCenter'][1])-25.4
    channel={'midpoint_x_mm':mid,'side_offset_mm':half,'foot_lane_y_mm':half+15.4,'hip_lane_y_mm':half+17.0}
    return mounts,hips,channel


def fit_head(ref,settings,mid,usb):
    """The same native head construction for interactive preview and full checks."""
    head=ref['head'].copy();original_window=window(head);z=settings['height_splice_z_mm'];raise_mm=settings['raise_mm']
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
    ear_source=json.loads((REF.parent/'reference-ears/source.json').read_text());ears=[]
    for name,record in ear_source['files'].items():
        path=REF.parent/'reference-ears'/(name+'.step');assert sha(path)==record['sha256']
        ear=Part.read(str(path));base=ear_source['base_z_mm'];extension=settings['ear_extension_mm']
        section=Part.makeFace(ear.slice(V(0,0,1),base+.001),'Part::FaceMakerBullseye')
        ear=translated(ear,[0,0,extension]).fuse(section.extrude(V(0,0,extension)))
        ear.translate(V(settings['ear_forward_mm'],settings['ear_spread_mm']*(1 if name=='left' else -1),head.BoundBox.ZMax-1-base))
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
    # Replace V3's outward-flared (dovetail) lower skirt with a straight slip
    # skirt. Keep the upper seating flange, so the lid can lower past the rim.
    rim=ref['head'].BoundBox.ZMax+raise_mm
    skirt=Part.makeFace(lid.slice(V(0,0,1),rim-.01),'Part::FaceMakerBullseye').makeOffset2D(-gap,join=2)
    if not skirt.Faces:skirt=Part.makeFace(skirt.Wires,'Part::FaceMakerBullseye')
    skirt.translate(V(0,0,.01))
    keep=skirt.extrude(V(0,0,-10)).fuse(Part.makeBox(300,300,100,V(-150,-150,rim)))
    lid=lid.common(keep)
    head=head.multiFuse([shoulders,*ears])
    usb_y=(usb.YMin+usb.YMax)/2;usb_z=(usb.ZMin+usb.ZMax)/2
    usb_cut=Part.makeBox(usb.XMin-head.BoundBox.XMin+2,12,7,V(head.BoundBox.XMin-1,usb_y-6,usb_z-3.5));head=head.cut(usb_cut)
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
    assert 0<=void_volume<before_volume*.01
    for zz in [44.,46.]:
        samples=ref['head'].common(Part.makeLine(V(mid,-35,zz),V(mid,35,zz))).Edges
        assert len(samples)==2
        for edge in samples:
            point=V(sum(port_x)/2,edge.BoundBox.Center.y,zz)
            assert not ref['head'].isInside(point,1e-6,False) and head.isInside(point,1e-6,False)
    assert all(s.isValid() and len(s.Solids)==1 and s.isClosed() for s in [head,lid])
    fitted_window=window(head)
    assert max(abs(a-b) for p,q in zip(original_window['bounds_mm'],fitted_window['bounds_mm']) for a,b in zip(p,q))<1e-5
    head_lid_overlap=head.common(lid);assert head_lid_overlap.isNull() or head_lid_overlap.isValid();assert abs(head_lid_overlap.Volume)<1e-3
    seating=[]
    for lift in [0,.5,1,1.5,2,4,8,12,20]:
        overlap=head.common(translated(lid,[0,0,lift]));assert overlap.isNull() or overlap.isValid()
        assert abs(overlap.Volume)<1e-3,(lift,overlap.Volume)
        seating.append({'lift_mm':lift,'intersection_mm3':overlap.Volume})
    details={'cable_notches':entries,'closed_upper_side_ports':2,'ear_source':ear_source,
             'sealed_internal_voids':{'count':void_count,'volume_mm3':void_volume},'unified_external_faces':unified,
             'ear_bounds_mm':[bounds(e) for e in ears],'ear_height_above_roof_mm':max(e.BoundBox.ZMax for e in ears)-roof,
             'lid_seating_samples':seating,'lid_plan':{'shape':'T-shaped rear roof with a front tongue between fixed ears','roof_z_mm':roof,
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


def fit_frame(original,params,pcb_holes):
    frame=original.copy();deck=frame.BoundBox.ZMax
    old_holes=cylinders(frame,.95,lambda f:abs(f.BoundBox.ZMax-deck)<1e-5);assert len(old_holes)==4
    frame=frame.multiFuse([Part.makeCylinder(.95,hi-lo,V(x,y,lo)) for x,y,lo,hi in old_holes])
    depth=params['pcb_pilot_depth_mm']+params['pcb_pilot_floor_mm']
    frame=frame.multiFuse([Part.makeCylinder(params['pcb_standoff_radius_mm'],depth,V(x,y,deck-depth)) for x,y,_ in pcb_holes])
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
            _,ref=load_references({'head','lid'});lo,hi=datums['usb_native_bounds_mm']
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
    frame=ref['frame'].copy();deck=frame.BoundBox.ZMax;seat=deck+params['pcb_standoff_height_mm']
    native,electronics,_,holes,hole_diameter=load_electronics()
    pcb_size=[native.Carrier.Length.Value,native.Carrier.Width.Value,native.Carrier.Shape.BoundBox.ZLength];cx,cy=pcb_size[0]/2,pcb_size[1]/2
    pcb_holes=[[cx-x,cy-y,seat] for x,y in holes]
    mounts,hips,channel=frame_layout(frame,deck);mid=channel['midpoint_x_mm']
    datums={'reference_family':'loftwork-printing-v3','reference_sha256':sha(REF/'source.json'),'parameters':params,'pcb_seat_z_mm':seat,'servo_flange_seat_z_mm':deck,
            'head_cable_entry':lower_entries(ref['head'],params['head_cover']['cable_entry']['z_mm']),
            'source_frame_bounds_mm':bounds(frame),'head_reference_bounds_mm':bounds(ref['head']),'parts':{'internal-frame':{'bounds_mm':bounds(frame)}},'servo_mounts':mounts,'hip_shaft_xy_mm':hips,'channel_layout':channel}
    out.mkdir(parents=True,exist_ok=True);write(out/'frame-datums.json',datums)
    if datums_only:return datums
    print('V3: fitting PCB pilots and separate spacers',flush=True)
    frame,old_holes=fit_frame(frame,params,pcb_holes)
    spacer=make_spacer(params)
    origins=[[x,y,deck] for x,y,_ in pcb_holes];spacers=[translated(spacer,p) for p in origins]
    lowest=min(s.BoundBox.ZMin for s in electronics.values());penetration=params['pcb_screw_length_mm']-pcb_size[2]-params['pcb_standoff_height_mm']
    assert 2*params['pcb_screw_diameter_mm']<=penetration<params['pcb_pilot_depth_mm']
    matrix=App.Matrix(-1,0,0,cx,0,-1,0,cy,0,0,1,seat,0,0,0,1)
    for s in electronics.values():s.transformShape(matrix)
    settings=params['head_cover'];z=settings['height_splice_z_mm'];raise_mm=settings['raise_mm']
    head,lid,fitted_window,head_lid_overlap,usb_cut,head_features=fit_head(ref,settings,mid,electronics['S3Source_Part__Feature022'].BoundBox)
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
    assert not frame.isInside(V(port_x,-28,deck-.1),1e-6,False)
    for y in [14.7,31.3]:assert frame.isInside(V(port_x,y,-5),1e-6,False)
    for y in [-14.7,-31.3,-31.8]:assert not frame.isInside(V(port_x,y,-5),1e-6,False)
    channel_checks=[]
    for x in [-port_x,-20,-15]:
        for zz in [-5,-10]:
            sections=[]
            for sign in [-1,1]:
                es=frame.common(Part.makeLine(V(x,sign*12,zz),V(x,sign*32,zz))).Edges
                sections.append(sorted([sorted([abs(e.BoundBox.YMin),abs(e.BoundBox.YMax)]) for e in es]))
            assert len(sections[0])==len(sections[1])
            assert all(abs(a-b)<1e-3 for p,q in zip(*sections) for a,b in zip(p,q)),(x,zz,sections)
            channel_checks.append({'x_mm':x,'z_mm':zz,'left_right_intervals_mm':sections})
    # Protect the V3 servo bays; the PCB edits are strictly inboard of them.
    bay_checks=cache.run('servo-bays',{'frame':geometry_keys['frame'],'reference':reference_frame_key},lambda:check_servo_bays(ref['frame'],frame))
    cables_path=ROOT/'assets/printing/internal-frame-s3/head-cable-clearance.json';cables=json.loads(cables_path.read_text())
    def same(a,b):
        if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
        if isinstance(a,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
        if isinstance(a,(int,float)) and not isinstance(a,bool):return abs(a-b)<1e-5
        return a==b
    assert same(cables['assembly_datums'],datums),'Routing samples use different frame/PCB datums'
    assert cables['entry_min_gap_mm']>=.2
    print('V3: checking authored ribbon and leg clearance samples',flush=True)
    ribbon_check=cache.run('ribbons',{'head':geometry_keys['head'],'lid':geometry_keys['lid'],'routes':sha(cables_path),'settings':settings,'midpoint':mid,'electronics':electronics_key},lambda:check_ribbons(head,lid,cables,settings,mid,electronics))
    queries=ribbon_check['classified']
    leg_checks=[];boxes=[bounds(head),bounds(lid)];limits=[[min(b[0][i] for b in boxes) for i in range(3)],[max(b[1][i] for b in boxes) for i in range(3)]]
    for item in cables['leg_samples']:
        box=item['bounds_mm'];assert any(box[1][i]<limits[0][i] or box[0][i]>limits[1][i] for i in range(3)),(item['part'],item['pose'])
        leg_checks.append({'part':item['part'],'pose':item['pose'],'separated_from_head':True})
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
            'battery_wire_cutout':{'location':'front-right','corner_radius_mm':1.,'source':'native V3 opening','other_channel_walls_intact':True,'new_cutout_wall_clear':True,'opposite_channel_section_checks':channel_checks},
            'pcb_fastening':{'board_thickness_mm':pcb_size[2],'spacer_height_mm':params['pcb_standoff_height_mm'],'screw_diameter_mm':params['pcb_screw_diameter_mm'],'screw_under_head_length_mm':params['pcb_screw_length_mm'],'nominal_frame_penetration_mm':penetration,'pilot_depth_mm':params['pcb_pilot_depth_mm'],'tip_clearance_mm':params['pcb_pilot_depth_mm']-penetration,'minimum_pilot_floor_mm':params['pcb_pilot_floor_mm'],'model_underside_projection_mm':-lowest,'model_deck_clearance_mm':params['pcb_standoff_height_mm']+lowest},
            'head_fit':{'source_object':'Loftwork V3 shell and removable lid','raise_mm':raise_mm,'height_splice_z_mm':z,'assembled_size_mm':[limits[1][i]-limits[0][i] for i in range(3)],'display_window':fitted_window,'display_window_unchanged':True,'spacer_clearances_mm':spacer_gaps,'electronics_intersections':collisions,'electronics_shapes_checked':len(electronics),'mount_axes_xy_mm':head_axes,'lid_intersection_mm3':head_lid_overlap.Volume,**head_features,'cable_surface_samples':len(cables['surface_points_mm']),'cable_samples_inside':0,'cable_samples_classified':queries,'cable_electronics_samples_inside':ribbon_check['electronics_inside'],'cable_entry_min_gap_mm':cables['entry_min_gap_mm'],'cable_reference_sha256':sha(cables_path),'leg_pose_checks':leg_checks,'usb_access_bounds_mm':bounds(usb_cut),'scope':'Final model fit and authored route samples; Rest/Standing leg bounds. No physical print or full-range motion test.'},
            'unchanged_legs':{name:sha(ROOT/'assets/stl/upstream'/f'{name}-v117.stl') for name in ['L1','L2','L3','L4','R1','R2','R3','R4']},'fit_note':'V3-derived example; current PCB/spacer datums retained. CAD and sampled route checks are not physical fit evidence.'}
    write(out/'assembly.json',report);print(json.dumps({'parts':list(parts),'head_spacer_gaps_mm':spacer_gaps,'ribbon_queries':queries,'support_width_mm':support},indent=2),flush=True)
    return report
