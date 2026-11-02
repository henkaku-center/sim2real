"""Extract the original Sesame ear profiles from the pinned public v122 CAD."""
import hashlib
import json
import re
from pathlib import Path
import FreeCAD as App
import Import
import Part
import MeshPart
from tools.body_cad import export_step,bounds

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/printing/internal-frame-s3/reference-ears'


def main():
    entry=next(e for e in json.loads((ROOT/'assets/cad/sources.json').read_text())['files'] if e['source_path']=='hardware/cad/Sesame-ESP32-v122.step')
    path=ROOT/'assets/cad/upstream'/entry['path'];raw=path.read_bytes()
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==entry['git_blob_sha1']
    doc=App.newDocument('OriginalSesameEars');Import.insert(str(path),doc.Name)
    matrix=App.Matrix(-1,0,0,26,0,0,1,0,0,1,0,-17,0,0,0,1)
    frame=next(o.Shape.copy() for o in doc.Objects if o.Label=='Internal-Frame');frame.transformShape(matrix)
    obj=doc.getObject('Part__Feature491');head=obj.Shape.copy()
    head.Placement=obj.getGlobalPlacement().multiply(obj.Placement.inverse()).multiply(head.Placement)
    head.transformShape(matrix);head.translate(App.Vector(0,-frame.BoundBox.Center.y,0))
    roof=max(f.BoundBox.ZMin for f in head.Faces if isinstance(f.Surface,Part.Plane) and abs(f.Surface.Axis.z)>.999 and f.Area>1000)
    cut_z=roof+.0001
    ears=head.common(Part.makeBox(100,100,30,App.Vector(-50,-50,cut_z)))
    assert len(ears.Solids)==2
    OUT.mkdir(parents=True,exist_ok=True);records={}
    for ear in ears.Solids:
        name='left' if ear.CenterOfMass.y>0 else 'right'
        # Seal tiny enclosed roof voids inherited from the original CAD.
        ear=Part.makeSolid(max(ear.Shells,key=lambda s:s.Area))
        assert ear.isValid() and ear.isClosed()
        mesh=MeshPart.meshFromShape(Shape=ear,LinearDeflection=.08,AngularDeflection=.2,Relative=False);assert mesh.isSolid()
        output=OUT/(name+'.step');export_step(ear,output)
        text=output.read_text();text=re.sub(r'FILE_NAME\(.*?\);',"FILE_NAME('Sesame original ear','2026-01-01T00:00:00',(''),(''),'Open CASCADE','Normalized geometry','');",text,flags=re.S);output.write_text(text)
        records[name]={'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bounds_mm':bounds(ear)}
    report={'source_repository':'dorianborian/sesame-robot','source_path':entry['source_path'],'git_blob_sha1':entry['git_blob_sha1'],
            'source_object':'Part__Feature491 / COMPOUND001','credit':'Dorian Todd and contributors','license':'Apache-2.0',
            'base_z_mm':cut_z,'source_to_body_matrix':list(matrix.A),'centre_y_mm':frame.BoundBox.Center.y,'files':records}
    (OUT/'source.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
