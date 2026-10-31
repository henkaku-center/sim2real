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
    assert original_window['bounds_mm'][1][2]<z
    low=head.common(Part.makeBox(300,300,z+150,V(-150,-150,-150)));high=head.common(Part.makeBox(300,300,150-z,V(-150,-150,z)))
    section=Part.makeFace(head.slice(V(0,0,1),z),'Part::FaceMakerBullseye')
    head=low.fuse(section.extrude(V(0,0,raise_mm))).fuse(translated(high,[0,0,raise_mm]));lid=translated(ref['lid'],[0,0,raise_mm])
    head=rounded_notches(head,mid,settings['cable_notch_width_mm'],settings['cable_notch_top_z_mm'])
    usb_y=(usb.YMin+usb.YMax)/2;usb_z=(usb.ZMin+usb.ZMax)/2
    usb_cut=Part.makeBox(usb.XMin-head.BoundBox.XMin+2,12,7,V(head.BoundBox.XMin-1,usb_y-6,usb_z-3.5));head=head.cut(usb_cut)
    assert all(s.isValid() and len(s.Solids)==1 and s.isClosed() for s in [head,lid])
    fitted_window=window(head)
    assert max(abs(a-b) for p,q in zip(original_window['bounds_mm'],fitted_window['bounds_mm']) for a,b in zip(p,q))<1e-5
    head_lid_overlap=head.common(lid);assert head_lid_overlap.isNull() or head_lid_overlap.isValid();assert abs(head_lid_overlap.Volume)<1e-3
    return head,lid,fitted_window,head_lid_overlap,usb_cut


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
    native,electronics,_,_,_=load_electronics()
    data={'deck_z_mm':deck,'midpoint_x_mm':channel['midpoint_x_mm'],
          'pcb_half_size_mm':[native.Carrier.Length.Value/2,native.Carrier.Width.Value/2],
          'usb_native_bounds_mm':bounds(electronics['S3Source_Part__Feature022'])}
    out.mkdir(parents=True,exist_ok=True);write(path,{'key':key,'datums':data})
    return data,False


def preview_head(params,out):
    """Fast native STEP preview, explicitly separate from a release receipt."""
    if out.resolve()==REF.parent.resolve() or (out/'assembly.json').exists():
        raise ValueError('Use a separate preview directory; this directory holds release artifacts')
    started=time.perf_counter()
    datums,cached=preview_datums(out)
    _,ref=load_references({'head','lid'})
    deck=datums['deck_z_mm'];seat=deck+params['pcb_standoff_height_mm']
    cx,cy=datums['pcb_half_size_mm'];lo,hi=datums['usb_native_bounds_mm']
    usb=App.BoundBox(cx-hi[0],cy-hi[1],lo[2]+seat,cx-lo[0],cy-lo[1],hi[2]+seat)
    head,lid,aperture,overlap,_=fit_head(ref,params['head_cover'],datums['midpoint_x_mm'],usb)
    assert head.BoundBox.ZMin>=deck-1e-6
    out.mkdir(parents=True,exist_ok=True)
    parts={}
    for name,shape in [('head-cover',head),('head-lid',lid),('head-preview',Part.makeCompound([head,lid]))]:
        path=out/(name+'.step');export_step(shape,path)
        parts[name]={'step_sha256':sha(path),'bounds_mm':bounds(shape),'volume_mm3':shape.Volume}
    report={'schema':1,'mode':'head-preview','parameters':params,'parts':parts,
            'checks':['closed valid shell/lid','unchanged OLED aperture','shell/lid overlap','head base above frame deck'],
            'unchecked':['electronics intersections','spacer clearance','mounting axes','ribbon clearance','leg poses','slicing','physical fit'],
            'source_script_sha256':sha(__file__),'electronics_sha256':sha(ROOT/'assets/cad/Sesame-S3-Assembly.FCStd'),
            'reference_sha256':sha(REF/'source.json'),'display_window':aperture,'lid_intersection_mm3':overlap.Volume,
            'input_cache_hit':cached,'elapsed_seconds':time.perf_counter()-started}
    write(out/'preview.json',report)
    print(json.dumps({'mode':'head-preview','seconds':report['elapsed_seconds'],'input_cache_hit':cached,'view_file':str(out/'head-preview.step'),'full_assembly_checks':'not run'},indent=2),flush=True)
    return report


def build(params,out,include_cover=True,datums_only=False):
    source,ref=load_references()
    frame=ref['frame'].copy();deck=frame.BoundBox.ZMax;seat=deck+params['pcb_standoff_height_mm']
    native,electronics,_,holes,hole_diameter=load_electronics()
    pcb_size=[native.Carrier.Length.Value,native.Carrier.Width.Value,native.Carrier.Shape.BoundBox.ZLength];cx,cy=pcb_size[0]/2,pcb_size[1]/2
    pcb_holes=[[cx-x,cy-y,seat] for x,y in holes]
    mounts,hips,channel=frame_layout(frame,deck);mid=channel['midpoint_x_mm']
    datums={'reference_family':'loftwork-printing-v3','reference_sha256':sha(REF/'source.json'),'parameters':params,'pcb_seat_z_mm':seat,'servo_flange_seat_z_mm':deck,
            'source_frame_bounds_mm':bounds(frame),'head_reference_bounds_mm':bounds(ref['head']),'parts':{'internal-frame':{'bounds_mm':bounds(frame)}},'servo_mounts':mounts,'hip_shaft_xy_mm':hips,'channel_layout':channel}
    out.mkdir(parents=True,exist_ok=True);write(out/'frame-datums.json',datums)
    if datums_only:return datums
    print('V3: fitting PCB pilots and separate spacers',flush=True)
    old_holes=cylinders(frame,.95,lambda f:abs(f.BoundBox.ZMax-deck)<1e-5);assert len(old_holes)==4
    fills=[Part.makeCylinder(.95,hi-lo,V(x,y,lo)) for x,y,lo,hi in old_holes]
    frame=frame.multiFuse(fills)
    depth=params['pcb_pilot_depth_mm']+params['pcb_pilot_floor_mm']
    reinforcement=[Part.makeCylinder(params['pcb_standoff_radius_mm'],depth,V(x,y,deck-depth)) for x,y,_ in pcb_holes]
    frame=frame.multiFuse(reinforcement)
    frame=frame.cut(Part.makeCompound([Part.makeCylinder(params['pcb_pilot_diameter_mm']/2,params['pcb_pilot_depth_mm'],V(x,y,deck-params['pcb_pilot_depth_mm'])) for x,y,_ in pcb_holes]))
    assert frame.isValid() and len(frame.Solids)==1 and abs(frame.BoundBox.ZMax-deck)<1e-6
    for x,y,_ in pcb_holes:
        assert not frame.isInside(V(x,y,deck-.1),1e-6,False)
        assert frame.isInside(V(x,y,deck-params['pcb_pilot_depth_mm']-params['pcb_pilot_floor_mm']/2),1e-6,False)
    spacer=Part.makeCylinder(params['pcb_standoff_radius_mm'],params['pcb_standoff_height_mm']).cut(Part.makeCylinder(params['pcb_spacer_bore_mm']/2,params['pcb_standoff_height_mm']))
    origins=[[x,y,deck] for x,y,_ in pcb_holes];spacers=[translated(spacer,p) for p in origins]
    lowest=min(s.BoundBox.ZMin for s in electronics.values());penetration=params['pcb_screw_length_mm']-pcb_size[2]-params['pcb_standoff_height_mm']
    assert 2*params['pcb_screw_diameter_mm']<=penetration<params['pcb_pilot_depth_mm']
    matrix=App.Matrix(-1,0,0,cx,0,-1,0,cy,0,0,1,seat,0,0,0,1)
    for s in electronics.values():s.transformShape(matrix)
    settings=params['head_cover'];z=settings['height_splice_z_mm'];raise_mm=settings['raise_mm']
    head,lid,fitted_window,head_lid_overlap,usb_cut=fit_head(ref,settings,mid,electronics['S3Source_Part__Feature022'].BoundBox)
    assert head.BoundBox.ZMin>=frame.BoundBox.ZMax-1e-6
    print('V3: checking electronics, spacers, shell and lid',flush=True)
    collisions=[]
    for name,solid in [('frame',frame),*[(f'spacer-{i}',s) for i,s in enumerate(spacers)],('head',head),('lid',lid)]:
        bb=solid.BoundBox
        for part,shape in electronics.items():
            if not bb.intersect(shape.BoundBox):continue
            hit=solid.common(shape);assert hit.isNull() or hit.isValid(),(name,part)
            assert hit.Volume>=-1e-6
            if hit.Volume>1e-4:collisions.append({'solid':name,'part':part,'volume_mm3':hit.Volume})
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
    bay_checks=[]
    for side in [-1,1]:
        boundary=31.8751;box=Part.makeBox(300,150-boundary,300,V(-150,boundary if side>0 else -150,-150))
        before=ref['frame'].common(box);after=frame.common(box);assert before.isValid() and after.isValid()
        delta=abs(before.Volume-after.Volume);assert delta<1e-3
        deviation=0.;samples=0
        for a,b in [(before,after),(after,before)]:
            for face in a.Faces:
                points,_=face.tessellate(.3)
                for i in sorted({0,len(points)//2,len(points)-1}):
                    if points:deviation=max(deviation,Part.Vertex(points[i]).distToShape(b)[0]);samples+=1
        assert deviation<1e-4
        bay_checks.append({'side':side,'translation_y_mm':0,'volume_difference_mm3':delta,'max_surface_deviation_mm':deviation,'surface_samples':samples,'source':'unchanged normalized V3 bay outside Y=±31.8751'})
    cables_path=ROOT/'assets/printing/internal-frame-s3/head-cable-clearance.json';cables=json.loads(cables_path.read_text())
    def same(a,b):
        if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
        if isinstance(a,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
        if isinstance(a,(int,float)) and not isinstance(a,bool):return abs(a-b)<1e-5
        return a==b
    assert same(cables['assembly_datums'],datums),'Routing samples use different frame/PCB datums'
    assert cables['entry_min_gap_mm']>=.2
    print('V3: checking authored ribbon and leg clearance samples',flush=True)
    core=Part.makeBox(60,50,45,V(-30,-25,10));core_hits=[s.common(core) for s in [head,lid]]
    assert all(s.isNull() or s.isValid() for s in core_hits);core_clear=all(abs(s.Volume)<1e-6 for s in core_hits)
    hbox=head.BoundBox;lbox=lid.BoundBox;bad=[];queries=0
    for point in cables['surface_points_mm']:
        x,y,zz=point
        v=V(*point)
        if not hbox.isInside(v) and not lbox.isInside(v):continue
        if core_clear and -30<=x<=30 and -25<=y<=25 and 10<=zz<=55:continue
        dx=abs(x-mid);half=settings['cable_notch_width_mm']/2;top=settings['cable_notch_top_z_mm']
        if zz<lbox.ZMin and (dx<=half and zz<=top-2 or dx<=half-2 and zz<=top or (dx-half+2)**2+(zz-top+2)**2<=4):continue
        queries+=1
        if hbox.isInside(v) and head.isInside(v,1e-6,False) or lbox.isInside(v) and lid.isInside(v,1e-6,False):bad.append(point)
    assert not bad,('ribbons in head',len(bad),bad[:4])
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
            'source_script_sha256':sha(__file__),'entry_script_sha256':sha(ROOT/'tools/internal_frame_cad.py'),'pcb_size_mm':pcb_size,'pcb_hole_diameter_mm':hole_diameter,'pcb_mount_holes_mm':pcb_holes,
            'pcb_side_margin_mm':(support-pcb_size[1])/2,'support_width_mm':support,'electronics_sha256':sha(ROOT/'assets/cad/Sesame-S3-Assembly.FCStd'),'electronics_shapes_checked':len(electronics),'electronics_intersections':collisions,'parts':parts,
            'pcb_hole_adjustment':{'source_axes':[[x,y] for x,y,lo,hi in old_holes],'destination_axes':[[x,y] for x,y,_ in pcb_holes],'source_diameter_mm':1.9,'pilot_diameter_mm':params['pcb_pilot_diameter_mm']},
            'bottom_cover_fasteners':{'frame':frame_under,'cover':cover_under,'matching_axes':True,'frame_intersection_mm3':overlap.Volume},'head_mount_axes_xy_mm':frame_head,'servo_bay_checks':bay_checks,
            'battery_wire_cutout':{'location':'front-right','corner_radius_mm':1.,'source':'native V3 opening','other_channel_walls_intact':True,'new_cutout_wall_clear':True,'opposite_channel_section_checks':channel_checks},
            'pcb_fastening':{'board_thickness_mm':pcb_size[2],'spacer_height_mm':params['pcb_standoff_height_mm'],'screw_diameter_mm':params['pcb_screw_diameter_mm'],'screw_under_head_length_mm':params['pcb_screw_length_mm'],'nominal_frame_penetration_mm':penetration,'pilot_depth_mm':params['pcb_pilot_depth_mm'],'tip_clearance_mm':params['pcb_pilot_depth_mm']-penetration,'minimum_pilot_floor_mm':params['pcb_pilot_floor_mm'],'model_underside_projection_mm':-lowest,'model_deck_clearance_mm':params['pcb_standoff_height_mm']+lowest},
            'head_fit':{'source_object':'Loftwork V3 shell and removable lid','raise_mm':raise_mm,'height_splice_z_mm':z,'assembled_size_mm':[limits[1][i]-limits[0][i] for i in range(3)],'display_window':fitted_window,'display_window_unchanged':True,'spacer_clearances_mm':spacer_gaps,'electronics_intersections':collisions,'electronics_shapes_checked':len(electronics),'mount_axes_xy_mm':head_axes,'lid_intersection_mm3':head_lid_overlap.Volume,'cable_notches':{'count':2,'bottom_open':True,'centre_x_mm':mid,'width_mm':settings['cable_notch_width_mm'],'top_z_mm':settings['cable_notch_top_z_mm'],'top_corner_radius_mm':2},'cable_surface_samples':len(cables['surface_points_mm']),'cable_samples_inside':0,'cable_samples_classified':queries,'cable_entry_min_gap_mm':cables['entry_min_gap_mm'],'cable_reference_sha256':sha(cables_path),'leg_pose_checks':leg_checks,'usb_access_bounds_mm':bounds(usb_cut),'scope':'Final model fit and authored route samples; Rest/Standing leg bounds. No physical print or full-range motion test.'},
            'unchanged_legs':{name:sha(ROOT/'assets/stl/upstream'/f'{name}-v117.stl') for name in ['L1','L2','L3','L4','R1','R2','R3','R4']},'fit_note':'V3-derived example; current PCB/spacer datums retained. CAD and sampled route checks are not physical fit evidence.'}
    write(out/'assembly.json',report);print(json.dumps({'parts':list(parts),'head_spacer_gaps_mm':spacer_gaps,'ribbon_queries':queries,'support_width_mm':support},indent=2),flush=True)
    return report
