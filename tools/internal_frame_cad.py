"""Widen the exact v122 STEP Internal-Frame for the 70 x 50 mm APS PCB.

Run with the FreeCAD Python used by tools/check_body.py. Source geometry is
translated in two rigid halves; no scaling of servo pockets, fasteners or legs.
The splice avoids the centre-line cover bores. Bottom cover is derived afterward
with the same splice and width, preserving its mating fastener coordinates.
"""
import argparse
import hashlib
import json
import math
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'assets/printing/internal-frame-s3'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(params, out, include_cover=False, datums_only=False):
    if params.get('source_family')=='loftwork-printing-v3':
        from tools.v3_assembly_cad import build as build_v3
        return build_v3(params,out,include_cover,datums_only)
    import FreeCAD as App
    import Import
    import MeshPart
    import Part
    from tools.body_cad import load_electronics, bounds, export_step, write_stl

    entries = json.loads((ROOT/'assets/cad/sources.json').read_text())['files']
    entry = next(e for e in entries if e['source_path']=='hardware/cad/Sesame-ESP32-v122.step')
    source = ROOT/'assets/cad/upstream'/entry['path']
    raw = source.read_bytes() if source.exists() else urllib.request.urlopen(entry['url'],timeout=180).read()
    assert len(raw)==entry['bytes']
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==entry['git_blob_sha1']
    if not source.exists():source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(raw)
    upstream = App.newDocument('InternalFrameSource')
    Import.insert(str(source), upstream.Name)
    body_basis = App.Matrix(-1,0,0,26, 0,0,1,0, 0,1,0,-17, 0,0,0,1)
    original = next(o.Shape.copy() for o in upstream.Objects if o.Label=='Internal-Frame')
    original.transformShape(body_basis)
    centre_y = (original.BoundBox.YMin+original.BoundBox.YMax)/2
    original.translate(App.Vector(0,-centre_y,0))
    width = float(params['widening_mm'])
    seam = float(params['splice_y_mm'])
    assert width>0 and 1<seam<3.7, 'Keep the splice clear of the original round cover bores'

    def shifted(shape, dy):
        result=shape.copy();result.translate(App.Vector(0,dy,0));return result

    def widen(shape):
        low=shape.common(Part.makeBox(300,150+seam,300,App.Vector(-150,-150,-150)))
        high=shape.common(Part.makeBox(300,150-seam,300,App.Vector(-150,seam,-150)))
        section=Part.makeFace(shape.slice(App.Vector(0,1,0),seam),'Part::FaceMakerBullseye')
        bridge=shifted(section.extrude(App.Vector(0,width,0)),-width/2)
        result=shifted(low,-width/2).fuse(bridge).fuse(shifted(high,width/2))
        # OCC's edge unifier fails on these valid imported fillets. Retain their
        # exact faces rather than healing/scaling the part or accepting bad solids.
        assert result.isValid() and len(result.Solids)==1
        return result

    def support_width(shape):
        edges=shape.common(Part.makeLine(App.Vector(0,-100,4),App.Vector(0,100,4))).Edges
        return max(e.BoundBox.YMax for e in edges)-min(e.BoundBox.YMin for e in edges)

    def widen_with_centered_fasteners(shape,kind):
        # The original centre bores fall wholly in the negative splice half.
        # Remove them before widening, then recut their exact axial profiles at
        # Y=0. Moving only the top opening would leave displaced screw-head wells.
        radius=.72328 if kind=='frame' else 1.15
        axes=sorted({(round(f.Surface.Center.x,8),round(f.Surface.Center.y,8)) for f in shape.Faces
                     if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Axis.z)>.999
                     and abs(f.Surface.Center.y)<1e-5 and abs(f.Surface.Radius-radius)<1e-5})
        assert len(axes)==2,(kind,axes)
        def axis_match(point):return any(math.hypot(point.x-x,point.y-y)<1e-5 for x,y in axes)
        profiles={axis:[] for axis in axes}
        for face in shape.Faces:
            surface=face.Surface
            if not isinstance(surface,(Part.Cylinder,Part.Cone)) or abs(surface.Axis.z)<.999 or not axis_match(surface.Center):continue
            axis=min(axes,key=lambda p:math.hypot(surface.Center.x-p[0],surface.Center.y-p[1]))
            lo,hi=face.BoundBox.ZMin,face.BoundBox.ZMax
            radii=[surface.Radius]*2
            if isinstance(surface,Part.Cone):
                radii=[surface.Radius+(z-surface.Center.z)*math.tan(surface.SemiAngle)/surface.Axis.z for z in [lo,hi]]
            profiles[axis].append({'z_mm':[lo,hi],'radii_mm':radii})
        blank=shape.copy()
        for _ in range(3):
            faces=[]
            for f in blank.Faces:
                surface=f.Surface
                if isinstance(surface,(Part.Cylinder,Part.Cone)) and abs(surface.Axis.z)>.999 and axis_match(surface.Center):faces.append(f)
                elif isinstance(surface,Part.Plane) and abs(surface.Axis.z)>.999 and axis_match(f.CenterOfMass) and len(f.Wires)==1 and len(f.Edges)==1 and f.BoundBox.XLength<9 and f.BoundBox.YLength<9:faces.append(f)
            if not faces:break
            previous_volume=blank.Volume;blank=blank.defeaturing(faces)
            assert blank.isValid() and len(blank.Solids)==1 and blank.Volume>previous_volume+1e-4,(kind,'hole closure failed')
        else:raise AssertionError((kind,'hole surfaces remain'))
        result=widen(blank);records=[]
        for (x,y),profile in profiles.items():
            tools=[]
            for segment in profile:
                lo,hi=segment['z_mm'];r0,r1=segment['radii_mm']
                tools.append(Part.makeCylinder(r0,hi-lo,App.Vector(x,0,lo)) if abs(r0-r1)<1e-7 else Part.makeCone(r0,r1,hi-lo,App.Vector(x,0,lo)))
            result=result.cut(Part.makeCompound(tools))
            assert result.isValid() and len(result.Solids)==1
            lo=min(s['z_mm'][0] for s in profile);hi=max(s['z_mm'][1] for s in profile)
            old_y=y+(-width/2 if y<seam else width/2)
            for z in [lo+.1,(lo+hi)/2,hi-.1]:
                assert result.isInside(App.Vector(x,old_y,z),1e-6,False),(kind,'old hole not closed')
                assert not result.isInside(App.Vector(x,0,z),1e-6,False),(kind,'new axis blocked')
            records.append({'x_mm':x,'y_mm':0,'previous_widened_y_mm':old_y,'profile':profile,'old_hole_closed':True,'new_axis_clear':True})
        return result,records

    frame,frame_fasteners=widen_with_centered_fasteners(original,'frame')
    port=None
    if params.get('battery_wire_cutout')=='front-right':
        # Recover the original 3D opening, not an extrusion of its roof outline.
        # Restore the entire old channel from the intact opposite-hand geometry.
        corners=[f for f in frame.Faces if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Radius-.635)<1e-5 and abs(f.Surface.Axis.z)>.999 and f.Surface.Center.x<-15 and f.Surface.Center.y>0]
        assert len(corners)==2
        radius=corners[0].Surface.Radius
        x0=min(f.Surface.Center.x for f in corners)-radius;x1=max(f.Surface.Center.x for f in corners)+radius
        y0=corners[0].Surface.Center.y-radius;y1=support_width(frame)/2
        top=frame.BoundBox.ZMax;bottom=max(f.BoundBox.ZMin for f in corners);probe=top-.05
        rectangle=Part.makePlane(x1-x0,y1-y0,App.Vector(x0,y0,probe))
        profile=rectangle.cut(frame)
        assert profile.isValid() and len(profile.Faces)==1 and 40<profile.Area<60
        pivot=App.Vector((frame.BoundBox.XMin+frame.BoundBox.XMax)/2,0,0)
        moved_profile=profile.copy();moved_profile.rotate(pivot,App.Vector(0,0,1),180)
        z0=frame.BoundBox.ZMin-1;height=frame.BoundBox.ZLength+2;outer_y=width/2+20
        opening_box=Part.makeBox(x1-x0,outer_y-y0,height,App.Vector(x0,y0,z0))
        cutter=opening_box.cut(frame)
        assert cutter.isValid() and len(cutter.Solids)==1
        repair_x=frame.BoundBox.XMin-1
        repair_outer_y=width/2+19.3  # stop at the native servo-pocket inner face
        repair_box=Part.makeBox(x1+1.5-repair_x,repair_outer_y-y0+2.5,height,App.Vector(repair_x,y0-2.5,z0))
        reference=frame.mirror(App.Vector(0,0,0),App.Vector(0,1,0)).common(repair_box)
        assert reference.isValid()
        frame=frame.cut(repair_box).fuse(reference)
        cutter.rotate(pivot,App.Vector(0,0,1),180)
        frame=frame.cut(cutter)
        assert frame.isValid() and len(frame.Solids)==1
        old_point=App.Vector((x0+x1)/2,(y0+y1)/2,top-.1)
        new_point=App.Vector(2*pivot.x-old_point.x,-old_point.y,old_point.z)
        assert frame.isInside(old_point,1e-6,False) and not frame.isInside(new_point,1e-6,False)
        assert new_point.x>0 and new_point.y<0
        channel_samples=[]
        for x in [-34,x0+2,(x0+x1)/2,x1-.5]:
            for z in [frame.BoundBox.ZMin+.5,-5,0,top-.1]:
                intervals=[]
                for side in [1,-1]:
                    edges=frame.common(Part.makeLine(App.Vector(x,side*(y0-2.5),z),App.Vector(x,side*repair_outer_y,z))).Edges
                    intervals.append(sorted([sorted([abs(e.BoundBox.YMin),abs(e.BoundBox.YMax)]) for e in edges]))
                assert len(intervals[0])==len(intervals[1]),(x,z,intervals)
                assert all(abs(a-b)<1e-5 for aa,bb in zip(*intervals) for a,b in zip(aa,bb)),(x,z,intervals)
                channel_samples.append({'x_mm':x,'z_mm':z,'material_y_intervals_mm':intervals[0]})
        for z in [frame.BoundBox.ZMin+.5,-5,0,top-.1]:
            for y in [y0+.2,(y0+outer_y)/2,width/2+19.26]:
                assert not frame.isInside(App.Vector(new_point.x,-y,z),1e-6,False),('battery opening blocked',y,z)
        port={'location':'front-right','old_location':'back-left','profile_area_mm2':profile.Area,'profile_bounds_mm':bounds(moved_profile),'original_profile_bounds_mm':bounds(profile),'corner_radius_mm':radius,'roof_depth_mm':top-bottom,'rotation_about_frame_center_deg':180,'old_opening_closed':True,'new_opening_clear':True,
              'method':'Opposite-hand channel restoration and rotated original 3D opening, including rounded wall ends',
              'old_channel_matches_opposite':True,'channel_section_checks':channel_samples,'new_cutout_wall_clear':True,'opening_tool_bounds_mm':bounds(cutter)}
    # Close only the approved top-side openings, before adding the PCB pilot
    # reinforcement. Full circular bore faces give exact plugs without growing
    # a broad cylinder into adjacent channels or retaining crescent openings.
    removed_holes=[];plugs=[];retained_holes=[]
    for face in frame.Faces:
        c=face.Surface
        if not isinstance(c,Part.Cylinder) or abs(c.Axis.z)<.999 or abs(face.BoundBox.ZMax-original.BoundBox.ZMax)>1e-5:continue
        x,y=c.Center.x,c.Center.y;reason=None
        if abs(c.Radius-.875)<1e-5:
            if x>0 or abs(x+7.78853)<1e-4:reason='unused electronics mounting hole'
            elif x<-35 and y>0:reason='unintended mirrored rear hole'
            elif x<-35:retained_holes.append({'x_mm':x,'y_mm':y,'diameter_mm':2*c.Radius,'reason':'unresolved original rear hole'})
        elif abs(c.Radius-1.15)<1e-5:
            if x>30:reason='obsolete front head opening causing PCB reinforcement crescent'
            elif x<-35:retained_holes.append({'x_mm':x,'y_mm':y,'diameter_mm':2*c.Radius,'reason':'original rear head fixing'})
        if reason:
            lo,hi=face.BoundBox.ZMin,face.BoundBox.ZMax
            assert not frame.isInside(App.Vector(x,y,(lo+hi)/2),1e-6,False),'Expected an empty bore, including mirrored faces'
            assert abs(face.Area-2*math.pi*c.Radius*(hi-lo))<1e-4,'Expected a complete bore before reinforcement'
            plugs.append(Part.makeCylinder(c.Radius,hi-lo,App.Vector(x,y,lo)))
            removed_holes.append({'x_mm':x,'y_mm':y,'diameter_mm':2*c.Radius,'filled_z_mm':[lo,hi],'reason':reason})
    assert len(removed_holes)==7 and len(retained_holes)==4,(removed_holes,retained_holes)
    before=frame.Volume;frame=frame.multiFuse(plugs)
    assert frame.isValid() and len(frame.Solids)==1
    assert abs(frame.Volume-before-sum(p.Volume for p in plugs))<1e-3
    native, electronics, _, holes, hole_diameter=load_electronics()
    pcb_size=[native.Carrier.Length.Value,native.Carrier.Width.Value,native.Carrier.Shape.BoundBox.ZLength]
    cx,cy=pcb_size[0]/2,pcb_size[1]/2
    deck=original.BoundBox.ZMax
    seat=deck+params['pcb_standoff_height_mm']
    hole_centres=[[cx-x,cy-y,seat] for x,y in holes]
    # Reinforcement stays below the flat print face. The four spacers are loose
    # parts, with clearance bores; only the frame has screw-forming pilot holes.
    boss_depth=params['pcb_pilot_depth_mm']+params['pcb_pilot_floor_mm']
    posts=[Part.makeCylinder(params['pcb_standoff_radius_mm'],boss_depth,App.Vector(x,y,deck-boss_depth)) for x,y,_ in hole_centres]
    frame=frame.multiFuse(posts)
    pilots=[Part.makeCylinder(params['pcb_pilot_diameter_mm']/2,params['pcb_pilot_depth_mm'],App.Vector(x,y,deck-params['pcb_pilot_depth_mm'])) for x,y,_ in hole_centres]
    frame=frame.cut(Part.makeCompound(pilots))
    assert frame.isValid() and len(frame.Solids)==1
    assert abs(frame.BoundBox.ZMax-deck)<1e-6,'No integral spacer may rise above the flat bed face'
    for record in removed_holes:
        lo,hi=record['filled_z_mm']
        for z in [lo+.05,(lo+hi)/2,hi-.05]:
            assert frame.isInside(App.Vector(record['x_mm'],record['y_mm'],z),1e-6,False),record
    for record in retained_holes:
        assert not frame.isInside(App.Vector(record['x_mm'],record['y_mm'],deck-.1),1e-6,False),record
    for x,y,_ in hole_centres:
        assert not frame.isInside(App.Vector(x,y,deck-params['pcb_pilot_depth_mm']+.1),1e-6,False)
        assert frame.isInside(App.Vector(x,y,deck-params['pcb_pilot_depth_mm']-params['pcb_pilot_floor_mm']/2),1e-6,False)
    spacer=Part.makeCylinder(params['pcb_standoff_radius_mm'],params['pcb_standoff_height_mm'])
    spacer=spacer.cut(Part.makeCylinder(params['pcb_spacer_bore_mm']/2,params['pcb_standoff_height_mm']))
    spacer_origins=[[x,y,deck] for x,y,_ in hole_centres]
    placed_spacers=[]
    for origin in spacer_origins:
        placed=spacer.copy();placed.translate(App.Vector(*origin));placed_spacers.append(placed)
        assert placed.common(frame).Volume<1e-5
    lowest=min(s.BoundBox.ZMin for s in electronics.values())
    penetration=params['pcb_screw_length_mm']-pcb_size[2]-params['pcb_standoff_height_mm']
    assert params['pcb_spacer_bore_mm']>params['pcb_screw_diameter_mm']
    assert hole_diameter>params['pcb_screw_diameter_mm']
    assert 2*params['pcb_screw_diameter_mm']<=penetration<params['pcb_pilot_depth_mm']
    assert params['pcb_standoff_height_mm']+lowest>=1.0

    # Compare the complete electronics BReps, not just a PCB rectangle. The 180°
    # yaw keeps USB at the rear in the guide's established robot orientation.
    pcb_matrix=App.Matrix(-1,0,0,cx, 0,-1,0,cy, 0,0,1,seat, 0,0,0,1)
    collisions=[]
    for name,part in electronics.items():
        part.transformShape(pcb_matrix)
        for item,solid in [('frame',frame),*[(f'spacer-{i+1}',s) for i,s in enumerate(placed_spacers)]]:
            if not part.BoundBox.intersect(solid.BoundBox):continue
            intersection=part.common(solid)
            assert intersection.isNull() or intersection.isValid(),name
            volume=intersection.Volume
            assert volume>=-1e-6,(name,volume)
            if volume>1e-4:collisions.append({'part':name,'against':item,'intersection_mm3':volume})
    assert not collisions, collisions

    # Reserve the two straight side-wall strips alongside the PCB for the next
    # head-shell revision. This checks a design envelope, not a fitted head.
    support=support_width(frame)
    side_margin=(support-pcb_size[1])/2
    wall=float(params['head_wall_mm']);clearance=float(params['head_side_clearance_mm'])
    assert wall>0 and clearance>0 and side_margin>=wall+2*clearance
    height=max(p.BoundBox.ZMax for p in electronics.values())-seat
    wall_shapes=[Part.makeBox(pcb_size[0],wall,height,App.Vector(-cx,y,seat))
                 for y in [cy+clearance,-cy-clearance-wall]]
    wall_collisions=[]
    for name,part in electronics.items():
        for side,shape in zip(['left','right'],wall_shapes):
            if not part.BoundBox.intersect(shape.BoundBox):continue
            overlap=part.common(shape)
            assert overlap.isNull() or overlap.isValid(),name
            assert overlap.Volume>=-1e-6,(name,overlap.Volume)
            if overlap.Volume>1e-4:wall_collisions.append({'part':name,'side':side,'intersection_mm3':overlap.Volume})
    assert not wall_collisions,wall_collisions
    head_allowance={'wall_mm':wall,'pcb_gap_mm':clearance,'outer_gap_mm':side_margin-wall-clearance,
                    'side_wall_bounds_mm':[bounds(s) for s in wall_shapes],
                    'electronics_shapes_checked':len(electronics),'electronics_intersections':wall_collisions,
                    'status':'Reserved side-wall envelopes only; head shape, height, retention and OLED window fitting follow separately.'}

    # Protect each complete servo bay outside the original central support.
    # Mounting holes and pocket shapes must be rigid translations of the source.
    bay_checks=[]
    for sign in [-1,1]:
        # Native servo-pocket inner faces are Y=±19.3. The old support-edge
        # boundary also included 0.08 mm of channel wall, now deliberately fixed.
        boundary=19.3+1e-4
        assert any(abs(f.BoundBox.YLength)<1e-6 and abs(abs(f.CenterOfMass.y)-19.3)<1e-5 for f in original.Faces)
        cut=Part.makeBox(300,150-boundary,300,App.Vector(-150,boundary if sign>0 else -150,-150))
        expected=shifted(original.common(cut),sign*width/2)
        actual=frame.common(shifted(cut,sign*width/2))
        # OCCT returns invalid negative-volume intersections when subtracting
        # these coincident imported bays. Check valid solids, volume and mutual
        # surface distances instead; never accept that invalid Boolean result.
        assert expected.isValid() and actual.isValid()
        volume_difference=abs(expected.Volume-actual.Volume)
        samples=0;deviation=0.0
        for source_bay,target_bay in [(expected,actual),(actual,expected)]:
            for face in source_bay.Faces:
                points,_=face.tessellate(.3)
                for index in sorted({0,len(points)//2,len(points)-1}):
                    if index<0 or not points:continue
                    deviation=max(deviation,Part.Vertex(points[index]).distToShape(target_bay)[0]);samples+=1
        assert volume_difference<1e-3 and deviation<1e-4,(sign,volume_difference,deviation)
        bay_checks.append({'side':sign,'translation_y_mm':sign*width/2,'protected_source_y_min_abs_mm':boundary,'volume_difference_mm3':volume_difference,'max_surface_deviation_mm':deviation,'surface_samples':samples})

    out.mkdir(parents=True,exist_ok=True)
    parts={}
    def export(name, shape):
        assert shape.isValid() and len(shape.Solids)==1
        mesh=MeshPart.meshFromShape(Shape=shape,LinearDeflection=params['mesh_deflection_mm'],AngularDeflection=.2,Relative=False)
        assert mesh.isSolid(),name
        write_stl(out/(name+'.stl'),mesh);export_step(shape,out/(name+'.step'))
        parts[name]={'bounds_mm':bounds(shape),'volume_mm3':shape.Volume,'triangles':mesh.CountFacets,
                     'stl_sha256':sha(out/(name+'.stl')),'step_sha256':sha(out/(name+'.step')),'valid_solid':True,'closed_mesh':True}

    # Frame validation and export complete before touching the dependent cover.
    export('internal-frame',frame)
    export('pcb-spacer',spacer)
    parts['pcb-spacer']['quantity']=4
    parts['pcb-spacer']['assembly_origins_mm']=spacer_origins
    parts['pcb-spacer']['print_rotation_axis_angle']=[1,0,0,0]
    parts['internal-frame']['print_rotation_axis_angle']=[1,0,0,180]
    print_frame=frame.copy();print_frame.rotate(App.Vector(0,0,0),App.Vector(1,0,0),180)
    print_frame.translate(App.Vector(0,0,-print_frame.BoundBox.ZMin))
    print_mesh=MeshPart.meshFromShape(Shape=print_frame,LinearDeflection=params['mesh_deflection_mm'],AngularDeflection=.2,Relative=False)
    assert print_mesh.isSolid() and abs(print_frame.BoundBox.ZMin)<1e-6
    write_stl(out/'internal-frame-print.stl',print_mesh)
    parts['internal-frame']['print_stl']='internal-frame-print.stl'
    parts['internal-frame']['print_stl_sha256']=sha(out/'internal-frame-print.stl')
    parts['internal-frame']['print_bounds_mm']=bounds(print_frame)
    cover_fasteners=[]
    if include_cover:
        bottom=next(o.Shape.copy() for o in upstream.Objects if o.Label=='Bottom-Cover')
        bottom.transformShape(body_basis);bottom.translate(App.Vector(0,-centre_y,0))
        cover,cover_fasteners=widen_with_centered_fasteners(bottom,'cover')
        assert [(p['x_mm'],p['y_mm']) for p in frame_fasteners]==[(p['x_mm'],p['y_mm']) for p in cover_fasteners]
        original_overlap=original.common(bottom).Volume
        intersection=frame.common(cover)
        assert intersection.isNull() or intersection.isValid()
        revised_overlap=intersection.Volume
        assert -1e-6<=revised_overlap<1e-3,(original_overlap,revised_overlap)
        export('bottom-cover',cover)
        parts['bottom-cover']['frame_intersection_mm3']=revised_overlap
        parts['bottom-cover']['original_frame_intersection_mm3']=original_overlap

    hips={}
    nominal=json.loads((ROOT/'assets/body/params.json').read_text())['servo']['hip_shaft_xy_mm']
    for name,key in [('L1','front_left'),('L2','back_left'),('R1','front_right'),('R2','back_right')]:
        x,y=nominal[key];y-=centre_y;y+=(1 if y>seam else -1)*width/2
        hips[name]=[x,y]
    support=support_width(frame)
    assert support>=pcb_size[1]+2, support
    report={
        'schema_version':1,'units':'mm','coordinates':'X front, Y left, Z up; frame centred laterally; PCB USB rear',
        'source':{'repository':'dorianborian/sesame-robot','revision':entry['revision'],'path':entry['source_path'],'sha256':sha(source),'frame_stl_sha256':sha(ROOT/'assets/stl/upstream/Internal-Frame-v121.stl')},
        'parameters':params,'source_frame_bounds_mm':bounds(original),'pcb_size_mm':pcb_size,
        'source_support_width_mm':support_width(original),'support_width_mm':support,
        'pcb_side_margin_mm':(support-pcb_size[1])/2,
        'head_wall_allowance':head_allowance,
        'battery_wire_cutout':port,
        'top_hole_cleanup':{'filled':removed_holes,'retained':retained_holes,'note':'Seven approved top openings closed; original lower head-access recesses remain. PCB pilots are drilled afterward.'},
        'bottom_cover_fasteners':{'frame':frame_fasteners,'cover':cover_fasteners,'note':'Both axes centred at Y=0; original bore, entry chamfer and screw-head recess profiles retained.'},
        'pcb_mount_holes_mm':hole_centres,'pcb_hole_diameter_mm':hole_diameter,'pcb_seat_z_mm':seat,
        'pcb_fastening':{'board_thickness_mm':pcb_size[2],'spacer_height_mm':params['pcb_standoff_height_mm'],
                         'screw_diameter_mm':params['pcb_screw_diameter_mm'],'screw_under_head_length_mm':params['pcb_screw_length_mm'],
                         'nominal_frame_penetration_mm':penetration,'pilot_depth_mm':params['pcb_pilot_depth_mm'],
                         'tip_clearance_mm':params['pcb_pilot_depth_mm']-penetration,'minimum_pilot_floor_mm':params['pcb_pilot_floor_mm'],
                         'model_underside_projection_mm':-lowest,'model_deck_clearance_mm':params['pcb_standoff_height_mm']+lowest,
                         'type':'Pan-head plastics thread-forming screw, not an interchangeable metric machine screw',
                         'status':'Proposed stack; corner holes are model datums, exact screw and printed pilot fit need checking; solder envelope is illustrative'},
        'servo_flange_seat_z_mm':original.BoundBox.ZMax,'hip_shaft_xy_mm':hips,
        'electronics_sha256':sha(ROOT/'assets/cad/Sesame-S3-Assembly.FCStd'),
        'source_script_sha256':sha(__file__),'parts':parts,'servo_bay_checks':bay_checks,
        'electronics_intersections':collisions,'electronics_shapes_checked':len(electronics),
        'unchanged_legs':{name:sha(ROOT/'assets/stl/upstream'/f'{name}-v117.stl') for name in ['L1','L2','L3','L4','R1','R2','R3','R4']},
        'fit_note':'CAD geometry check, not a physical print test. PCB hole datums retain the recorded instructor estimates. Servo mounting features are preserved from the linked frame.'
    }
    (out/'assembly.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'parts':list(parts),'frame_size_mm':[frame.BoundBox.XLength,frame.BoundBox.YLength,frame.BoundBox.ZLength],'pcb_size_mm':pcb_size,'electronics_shapes_checked':len(electronics),'collisions':collisions,'servo_bays':bay_checks},indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--params',type=Path,default=OUTPUT/'params.json')
    p.add_argument('--output',type=Path)
    p.add_argument('--include-bottom-cover',action='store_true')
    p.add_argument('--datums-only',action='store_true',help='Export the V3 route/placement datums before generating clearance samples')
    p.add_argument('--preview-head',action='store_true',help='Fast V3 shell/lid STEP preview; skip full assembly checks and release exports')
    args=p.parse_args();params=json.loads(args.params.read_text())
    if args.preview_head:
        if args.datums_only or params.get('source_family')!='loftwork-printing-v3':p.error('--preview-head requires V3 parameters and cannot be combined with --datums-only')
        from tools.v3_assembly_cad import preview_head
        preview_head(params,args.output or ROOT/'tests/artifacts/head-preview')
    else:build(params,args.output or OUTPUT,args.include_bottom_cover,args.datums_only)


if __name__=='__main__':main()
