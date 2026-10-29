"""Widen the exact v122 STEP Internal-Frame for the 70 x 50 mm APS PCB.

Run with the FreeCAD Python used by tools/check_body.py. Source geometry is
translated in two rigid halves; no scaling of servo pockets, fasteners or legs.
The splice avoids the centre-line cover bores. Bottom cover is derived afterward
with the same splice and width, preserving its mating fastener coordinates.
"""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'assets/printing/internal-frame-s3'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(params, out, include_cover=False):
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

    frame=widen(original)
    port=None
    if params.get('battery_wire_cutout')=='front-right':
        # Recover the exact open-notch profile from the top deck, including its
        # corner radii. Move only that opening, not the frame or mounting holes.
        corners=[f for f in frame.Faces if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Radius-.635)<1e-5 and abs(f.Surface.Axis.z)>.999 and f.Surface.Center.x<-15 and f.Surface.Center.y>0]
        assert len(corners)==2
        radius=corners[0].Surface.Radius
        x0=min(f.Surface.Center.x for f in corners)-radius;x1=max(f.Surface.Center.x for f in corners)+radius
        y0=corners[0].Surface.Center.y-radius;y1=support_width(frame)/2
        top=frame.BoundBox.ZMax;bottom=max(f.BoundBox.ZMin for f in corners);probe=top-.05
        rectangle=Part.makePlane(x1-x0,y1-y0,App.Vector(x0,y0,probe))
        profile=rectangle.cut(frame)
        assert profile.isValid() and len(profile.Faces)==1 and 40<profile.Area<60
        fill=profile.copy();fill.translate(App.Vector(0,0,bottom-probe));fill=fill.extrude(App.Vector(0,0,top-bottom))
        pivot=App.Vector((frame.BoundBox.XMin+frame.BoundBox.XMax)/2,0,0)
        moved_profile=profile.copy();moved_profile.rotate(pivot,App.Vector(0,0,1),180)
        cutter=moved_profile.copy();cutter.translate(App.Vector(0,0,frame.BoundBox.ZMin-1-probe));cutter=cutter.extrude(App.Vector(0,0,frame.BoundBox.ZLength+2))
        frame=frame.fuse(fill).cut(cutter)
        assert frame.isValid() and len(frame.Solids)==1
        old_point=App.Vector((x0+x1)/2,(y0+y1)/2,top-.1)
        new_point=App.Vector(2*pivot.x-old_point.x,-old_point.y,old_point.z)
        assert frame.isInside(old_point,1e-6,False) and not frame.isInside(new_point,1e-6,False)
        assert new_point.x>0 and new_point.y<0
        port={'location':'front-right','old_location':'back-left','profile_area_mm2':profile.Area,'profile_bounds_mm':bounds(moved_profile),'original_profile_bounds_mm':bounds(profile),'corner_radius_mm':radius,'roof_depth_mm':top-bottom,'rotation_about_frame_center_deg':180,'old_opening_closed':True,'new_opening_clear':True}
    native, electronics, _, holes, hole_diameter=load_electronics()
    pcb_size=[native.Carrier.Length.Value,native.Carrier.Width.Value,native.Carrier.Shape.BoundBox.ZLength]
    cx,cy=pcb_size[0]/2,pcb_size[1]/2
    seat=original.BoundBox.ZMax+params['pcb_standoff_height_mm']
    hole_centres=[[cx-x,cy-y,seat] for x,y in holes]
    posts=[Part.makeCylinder(params['pcb_standoff_radius_mm'],seat,App.Vector(x,y,0)) for x,y,_ in hole_centres]
    frame=frame.multiFuse(posts)
    pilots=[Part.makeCylinder(params['pcb_pilot_diameter_mm']/2,params['pcb_pilot_depth_mm'],App.Vector(x,y,seat-params['pcb_pilot_depth_mm'])) for x,y,_ in hole_centres]
    frame=frame.cut(Part.makeCompound(pilots))
    assert frame.isValid() and len(frame.Solids)==1

    # Compare the complete electronics BReps, not just a PCB rectangle. The 180°
    # yaw keeps USB at the rear in the guide's established robot orientation.
    pcb_matrix=App.Matrix(-1,0,0,cx, 0,-1,0,cy, 0,0,1,seat, 0,0,0,1)
    collisions=[]
    for name,part in electronics.items():
        part.transformShape(pcb_matrix)
        if part.BoundBox.intersect(frame.BoundBox):
            intersection=part.common(frame)
            assert intersection.isNull() or intersection.isValid(),name
            volume=intersection.Volume
            assert volume>=-1e-6,(name,volume)
            if volume>1e-4:collisions.append({'part':name,'intersection_mm3':volume})
    assert not collisions, collisions

    # Protect each complete servo bay outside the original central support.
    # Mounting holes and pocket shapes must be rigid translations of the source.
    bay_checks=[]
    for sign in [-1,1]:
        boundary=support_width(original)/2+1e-4
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
        bay_checks.append({'side':sign,'translation_y_mm':sign*width/2,'volume_difference_mm3':volume_difference,'max_surface_deviation_mm':deviation,'surface_samples':samples})

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
    if include_cover:
        bottom=next(o.Shape.copy() for o in upstream.Objects if o.Label=='Bottom-Cover')
        bottom.transformShape(body_basis);bottom.translate(App.Vector(0,-centre_y,0))
        cover=widen(bottom)
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
        'battery_wire_cutout':port,
        'pcb_mount_holes_mm':hole_centres,'pcb_hole_diameter_mm':hole_diameter,'pcb_seat_z_mm':seat,
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
    p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--include-bottom-cover',action='store_true')
    args=p.parse_args();build(json.loads(args.params.read_text()),args.output,args.include_bottom_cover)


if __name__=='__main__':main()
