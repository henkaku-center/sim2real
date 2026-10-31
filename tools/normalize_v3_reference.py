"""Re-export the supplied V3 geometry without private STEP headers/paths."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import FreeCAD as App
import Part
import MeshPart
from tools.body_cad import export_step,bounds

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/printing/internal-frame-s3/reference-v3'
NAMES={'frame':'internal-frame_v3.stp','bottom':'bottom-cover_v3.stp','head':'top-cover-shell_v3.stp','lid':'top-cover-lid_v3.stp'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,required=True);args=parser.parse_args()
    raw={k:Part.read(str(args.input/name)) for k,name in NAMES.items()}
    frame=raw['frame'];deck=frame.BoundBox.ZMax
    axes=sorted({(round(f.Surface.Center.x,8),round(f.Surface.Center.y,8)) for f in frame.Faces
                 if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Axis.z)>.999 and abs(f.Surface.Radius-.95)<1e-5 and abs(f.BoundBox.ZMax-deck)<1e-5})
    assert len(axes)==4
    # Keep the current carrier and spacer dimensions. A 0.6 mm forward PCB
    # adjustment balances clearance to V3's front/rear head mounting bosses.
    cx=sum(p[0] for p in axes)/4-.6;cy=(frame.BoundBox.YMin+frame.BoundBox.YMax)/2
    matrix=App.Matrix(-1,0,0,cx,0,-1,0,cy,0,0,1,4.967756901865165-deck,0,0,0,1)
    report={'family':'Loftwork printing_V3','shared_date':'2026-09-17','credit':'V3 files shared by Jom Jetsada / Loftwork team; original Sesame by Dorian Todd and contributors.',
            'upstream':'dorianborian/sesame-robot','upstream_license':'Apache-2.0','publication':'Adapted V3 geometry authorized by the instructor on 2026-10-31.',
            'source_to_body_matrix':list(matrix.A),'pcb_forward_adjustment_mm':.6,'lid_seating_translation_z_mm':-20,
            'normalizer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'files':{}}
    OUT.mkdir(parents=True,exist_ok=True)
    for key,shape in raw.items():
        repaired=None
        if key=='bottom':
            # The supplied STEP has one missing curved sliver, bounded by three
            # free edges. Fill that boundary, not the intended screw openings.
            free=[e for e in shape.Edges if sum(any(e.isSame(a) for a in f.Edges) for f in shape.Faces)==1]
            assert len(free)==3
            patch=Part.makeFilledFace(free);assert patch.Area<.1
            shell=Part.makeShell([*shape.Faces,patch]);shell.sewShape();shape=Part.makeSolid(shell)
            repaired={'free_edges':3,'patch_area_mm2':patch.Area}
        assert shape.isValid() and len(shape.Solids)==1 and shape.isClosed(),key
        shape.transformShape(matrix)
        if key=='lid':shape.translate(App.Vector(0,0,-20))
        output=OUT/(key+'.step');export_step(shape,output)
        text=output.read_text();text=re.sub(r'FILE_NAME\(.*?\);',"FILE_NAME('Sesame V3 reference','2026-01-01T00:00:00',(''),(''),'Open CASCADE','Normalized geometry','');",text,flags=re.S);output.write_text(text)
        reopened=Part.read(str(output));assert reopened.isValid() and len(reopened.Solids)==1
        mesh=MeshPart.meshFromShape(Shape=reopened,LinearDeflection=.08,AngularDeflection=.2,Relative=False)
        print(key,'solid',reopened.isValid(),'mesh closed',mesh.isSolid(),'triangles',mesh.CountFacets,flush=True)
        report['files'][key]={'original_filename':NAMES[key],'original_sha256':hashlib.sha256((args.input/NAMES[key]).read_bytes()).hexdigest(),
                              'normalized_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bounds_mm':bounds(reopened),'repair':repaired}
    (OUT/'source.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
