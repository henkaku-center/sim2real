"""Content-addressed successful check results. Geometry, code and tolerances are inputs."""
import hashlib
import json
import os
from pathlib import Path
import time


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def shape_digest(shape):
    return hashlib.sha256(shape.exportBrepToString().encode()).hexdigest()


class CheckCache:
    def __init__(self,directory,context,fresh=False):
        self.directory=Path(directory);self.context=context;self.fresh=fresh;self.records=[]

    def run(self,name,inputs,check):
        key=digest({'name':name,'context':self.context,'inputs':inputs})
        path=self.directory/(key+'.json');started=time.perf_counter()
        if not self.fresh and path.exists():
            try:
                saved=json.loads(path.read_text())
                if saved['key']==key and saved['result_sha256']==digest(saved['result']):
                    self.records.append({'group':name,'key':key,'cache_hit':True})
                    return saved['result']
            except (ValueError,KeyError,TypeError):pass
        result=check()  # Exceptions never produce a cache entry.
        self.directory.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix(f'.{os.getpid()}.tmp')
        temporary.write_text(json.dumps({'key':key,'result':result,'result_sha256':digest(result),'seconds':time.perf_counter()-started},sort_keys=True,allow_nan=False)+'\n')
        temporary.replace(path)
        self.records.append({'group':name,'key':key,'cache_hit':False})
        return result


def check_electronics(solid,electronics):
    collisions=[];bb=solid.BoundBox
    for part,shape in electronics.items():
        if not bb.intersect(shape.BoundBox):continue
        hit=solid.common(shape);assert hit.isNull() or hit.isValid(),part
        assert hit.Volume>=-1e-6
        if hit.Volume>1e-4:collisions.append({'part':part,'volume_mm3':hit.Volume})
    assert not collisions,collisions
    return collisions


def check_servo_bays(original,frame):
    import FreeCAD as App
    import Part
    checks=[]
    for side in [-1,1]:
        boundary=31.8751;box=Part.makeBox(300,150-boundary,300,App.Vector(-150,boundary if side>0 else -150,-150))
        before=original.common(box);after=frame.common(box);assert before.isValid() and after.isValid()
        delta=abs(before.Volume-after.Volume);assert delta<1e-3
        deviation=0.;samples=0
        for a,b in [(before,after),(after,before)]:
            for face in a.Faces:
                points,_=face.tessellate(.3)
                for i in sorted({0,len(points)//2,len(points)-1}):
                    if points:deviation=max(deviation,Part.Vertex(points[i]).distToShape(b)[0]);samples+=1
        assert deviation<1e-4
        checks.append({'side':side,'translation_y_mm':0,'volume_difference_mm3':delta,'max_surface_deviation_mm':deviation,'surface_samples':samples,'source':'unchanged normalized V3 bay outside Y=±31.8751'})
    return checks


def check_ribbons(head,lid,cables,settings,mid,electronics):
    import FreeCAD as App
    import Part
    core_top=lid.BoundBox.ZMin-.3
    core=Part.makeBox(46,48,core_top-10,App.Vector(-20,-24,10));core_hits=[s.common(core) for s in [head,lid]]
    assert all(s.isNull() or s.isValid() for s in core_hits);core_clear=all(abs(s.Volume)<1e-6 for s in core_hits)
    print('V3: ribbon cavity certificate',core_clear,[s.Volume for s in core_hits],flush=True)
    entry=cables['assembly_datums']['head_cable_entry'];width=entry['width_mm']-.1
    portal=Part.makeBox(width,70,2,App.Vector(entry['centre_x_mm']-width/2,-35,entry['entry_z_mm']-1))
    portal_hits=[s.common(portal) for s in [head,lid]]
    assert all(s.isNull() or s.isValid() for s in portal_hits)
    portal_clear=all(abs(s.Volume)<1e-6 for s in portal_hits);portal_box=portal.BoundBox
    lower_cores=[Part.makeBox(17,52.6,18,App.Vector(-8,-26.3,10)),Part.makeBox(17,51.6,6,App.Vector(-8,-25.8,28)),
                 Part.makeBox(17,50.4,5,App.Vector(-8,-25.2,34)),Part.makeBox(17,49,4,App.Vector(-8,-24.5,39))]
    certified=[]
    for box in lower_cores:
        intersections=[s.common(box) for s in [head,lid]]
        assert all(s.isNull() or s.isValid() for s in intersections)
        if all(abs(s.Volume)<1e-6 for s in intersections):certified.append(box.BoundBox)
    hbox=head.BoundBox;lbox=lid.BoundBox;bad=[];queries=0
    for point in cables['surface_points_mm']:
        x,y,zz=point;v=App.Vector(*point)
        if not hbox.isInside(v) and not lbox.isInside(v):continue
        if core_clear and -20<=x<=26 and -24<=y<=24 and 10<=zz<=core_top:continue
        if portal_clear and portal_box.isInside(v):continue
        if any(box.isInside(v) for box in certified):continue
        queries+=1
        if hbox.isInside(v) and head.isInside(v,1e-6,False) or lbox.isInside(v) and lid.isInside(v,1e-6,False):bad.append(point)
        assert len(bad)<12,('ribbons in head',bad)
    assert not bad,('ribbons in head',len(bad),bad[:4])
    print('V3: ribbon/head samples classified',queries,flush=True)
    # Local broad phase for the now-internal risers, followed by native solids.
    import math
    members={}
    for name,shape in electronics.items():
        for i,solid in enumerate(shape.Solids or [shape]):members[(name,i)]=solid
    bins={};boxes={name:shape.BoundBox for name,shape in members.items()}
    for name,b in boxes.items():
        for x in range(math.floor(b.XMin/4),math.floor(b.XMax/4)+1):
            for y in range(math.floor(b.YMin/4),math.floor(b.YMax/4)+1):
                for z in range(math.floor(b.ZMin/4),math.floor(b.ZMax/4)+1):bins.setdefault((x,y,z),[]).append(name)
    hits=[];electronics_queries=0
    for point in cables['surface_points_mm']:
        vector=App.Vector(*point)
        for name in bins.get(tuple(math.floor(v/4) for v in point),[]):
            if not boxes[name].isInside(vector):continue
            electronics_queries+=1
            if members[name].isInside(vector,1e-6,False):hits.append({'part':name,'point':point})
            assert len(hits)<12,('ribbon surfaces in electronics',hits)
    assert not hits,('ribbon surfaces in electronics',len(hits),hits[:12])
    return {'classified':queries,'inside':0,'electronics_classified':electronics_queries,'electronics_inside':0}
