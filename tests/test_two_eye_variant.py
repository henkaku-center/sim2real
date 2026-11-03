"""The two-eye design variant: a real widened kit generated from the V3 source."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'assets/printing/internal-frame-s3'
OUT=ROOT/'assets/printing/internal-frame-s3-two-eyes'
def load(path):return json.loads((path/'assembly.json').read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_variant_is_generated_by_the_current_script_from_base_parameters():
    v=load(OUT);params=json.loads((OUT/'params.json').read_text())
    assert v['source_script_sha256']==sha(ROOT/'tools/v3_assembly_cad.py')
    base=json.loads((BASE/'params.json').read_text());variant=params.pop('variant')
    assert params==base and v['variant']==variant and variant['id']=='two-eyes'
    for name,part in v['parts'].items():
        assert part['valid_solid'] and part['closed_mesh']
        for ext in ['stl','step']:assert sha(OUT/f'{name}.{ext}')==part[f'{ext}_sha256']


def test_body_widens_by_exactly_the_requested_width_without_rescaling_features():
    b,v=load(BASE),load(OUT);widen=v['variant']['widen_mm']
    for name in ['internal-frame','bottom-cover','head-cover','head-lid']:
        lo,hi=b['parts'][name]['bounds_mm'];vlo,vhi=v['parts'][name]['bounds_mm']
        assert abs((vhi[1]-vlo[1])-(hi[1]-lo[1])-widen)<1e-4,name
        for k in [0,2]:assert abs(vlo[k]-lo[k])<1e-4 and abs(vhi[k]-hi[k])<1e-4,name
    assert v['pcb_mount_holes_mm']==b['pcb_mount_holes_mm'] and v['pcb_size_mm']==b['pcb_size_mm']
    assert v['bottom_cover_fasteners']==b['bottom_cover_fasteners']
    for (x,y),(bx,by) in zip(v['head_mount_axes_xy_mm'],b['head_mount_axes_xy_mm']):
        assert abs(x-bx)<1e-4 and abs(abs(y)-abs(by)-widen/2)<1e-4
    for leg,mount in v['servo_mounts'].items():
        base=b['servo_mounts'][leg]['caseCenter']
        assert abs(mount['caseCenter'][0]-base[0])<1e-4 and abs(abs(mount['caseCenter'][1])-abs(base[1])-widen/2)<1e-4


def test_one_aperture_becomes_two_equal_symmetric_eyes():
    b,v=load(BASE),load(OUT)
    (one,)=b['head_fit']['display_windows'];eyes=v['head_fit']['display_windows']
    assert len(eyes)==2
    for eye in eyes:
        assert abs(eye['height_mm']-one['height_mm'])<1e-4 and abs(eye['centre_mm'][2]-one['centre_mm'][2])<1e-4
        assert eye['width_mm']>one['width_mm']-.3
    centre=one['centre_mm'][1]
    assert abs(eyes[0]['centre_mm'][1]+eyes[1]['centre_mm'][1]-2*centre)<1e-6
    # A 27.3 mm wide OLED module fits behind each eye without overlapping.
    assert eyes[1]['centre_mm'][1]-eyes[0]['centre_mm'][1]>27.3
    assert v['head_fit']['electronics_intersections']==[] and min(v['head_fit']['spacer_clearances_mm'])>=.6
    assert v['head_fit']['switch_opening']['old_recess_removed']


def test_variant_records_what_was_and_was_not_checked():
    v=load(OUT)
    assert v['head_fit']['cable_checks'].startswith('not run')
    e=v['variant']['electronics']
    assert e['second_display_i2c_address']=='0x3D' and e['new_s3_pins']==0
