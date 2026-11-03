"""Native reference-switch clearance at the centred rear opening (FreeCAD Python)."""
import hashlib
import json
from pathlib import Path
import FreeCAD as App
import Part
from tools.body_cad import load_electronics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/printing/internal-frame-s3'


def main():
    report=json.loads((OUT/'assembly.json').read_text())
    opening=report['head_fit']['switch_opening'];nx,_,nz=opening['normal']
    old=opening['old_centre_mm'];seat=report['pcb_seat_z_mm']
    native,electronics,*_=load_electronics()
    matrix=App.Matrix(-1,0,0,native.Carrier.Length.Value/2,0,-1,0,native.Carrier.Width.Value/2,0,0,1,seat,0,0,0,1)
    for shape in electronics.values():shape.transformShape(matrix)
    source=ROOT/'assets/cad/upstream/adafruit/3221 Toggle Switch/3221 Toggle Switch.step'
    switch=Part.read(str(source))
    # Same two-lug reference geometry as the guide; omit its unused centre lug.
    switch=Part.makeCompound([s for s in switch.Solids if not(s.BoundBox.ZMax+14<5 and abs(s.BoundBox.Center.y)<1)])
    midpoint=(report['parts']['head-cover']['bounds_mm'][0][2]+report['head_fit']['lid_plan']['roof_z_mm'])/2
    results={}
    for name,z in [('rejected_vertical_midpoint',midpoint),('delivered',opening['centre_mm'][2])]:
        x=old[0]-nz/nx*(z-old[2]);y=opening['centre_mm'][1]
        shape=switch.copy()
        shape.transformShape(App.Matrix(0,-nz,nx,x-nx*3.25,1,0,0,y,0,nx,nz,z-nz*3.25,0,0,0,1))
        hits=[];near=[]
        for label,other in electronics.items():
            a,b=shape.BoundBox,other.BoundBox
            gap=sum(max(0,getattr(a,k+'Min')-getattr(b,k+'Max'),getattr(b,k+'Min')-getattr(a,k+'Max'))**2 for k in ['X','Y','Z'])**.5
            if gap>=8:continue
            distance=shape.distToShape(other)[0];near.append({'part':label,'distance_mm':distance})
            if distance<1e-6:
                overlap=shape.common(other).Volume
                if overlap>1e-5:hits.append({'part':label,'volume_mm3':overlap})
        results[name]={'centre_mm':[x,y,z],'intersections':hits,'nearest':sorted(near,key=lambda v:v['distance_mm'])[:10]}
    assert results['rejected_vertical_midpoint']['intersections']
    assert not results['delivered']['intersections']
    assert results['delivered']['nearest'][0]['distance_mm']>1
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result={'scope':'Native reference-switch versus all carrier electronics. Same two-lug stand-in as the guide; not measured purchased-part fit or physical cable reach.',
            'checker_sha256':sha(Path(__file__)),'assembly_sha256':sha(OUT/'assembly.json'),'switch_reference_sha256':sha(source),
            'electronics_sha256':report['electronics_sha256'],'results':results}
    (OUT/'tail-switch-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
