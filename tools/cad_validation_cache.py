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


def check_ribbons(head,lid,cables,settings,mid):
    import FreeCAD as App
    import Part
    core=Part.makeBox(60,50,45,App.Vector(-30,-25,10));core_hits=[s.common(core) for s in [head,lid]]
    assert all(s.isNull() or s.isValid() for s in core_hits);core_clear=all(abs(s.Volume)<1e-6 for s in core_hits)
    hbox=head.BoundBox;lbox=lid.BoundBox;bad=[];queries=0
    for point in cables['surface_points_mm']:
        x,y,zz=point;v=App.Vector(*point)
        if not hbox.isInside(v) and not lbox.isInside(v):continue
        if core_clear and -30<=x<=30 and -25<=y<=25 and 10<=zz<=55:continue
        dx=abs(x-mid);half=settings['cable_notch_width_mm']/2;top=settings['cable_notch_top_z_mm']
        if zz<lbox.ZMin and (dx<=half and zz<=top-2 or dx<=half-2 and zz<=top or (dx-half+2)**2+(zz-top+2)**2<=4):continue
        queries+=1
        if hbox.isInside(v) and head.isInside(v,1e-6,False) or lbox.isInside(v) and lid.isInside(v,1e-6,False):bad.append(point)
    assert not bad,('ribbons in head',len(bad),bad[:4])
    return {'classified':queries,'inside':0}
