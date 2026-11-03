"""The six-leg prompt on top of two eyes: a lengthened kit with a middle station."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'assets/printing/internal-frame-s3'
EYES=ROOT/'assets/printing/internal-frame-s3-two-eyes'
OUT=ROOT/'assets/printing/internal-frame-s3-two-eyes-six-legs'
def load(path):return json.loads((path/'assembly.json').read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_generated_by_the_current_script_and_builds_on_the_two_eye_variant():
    v=load(OUT);params=json.loads((OUT/'params.json').read_text())
    assert v['source_script_sha256']==sha(ROOT/'tools/v3_assembly_cad.py')
    eyes=json.loads((EYES/'params.json').read_text())['variant']
    legs=params['variant'].pop('middle_legs')
    for key in ['widen_mm','stretch_plane_y_mm','eyes','eye_bar_mm','electronics']:assert params['variant'][key]==eyes[key]
    assert legs['servos_added']==4 and legs['hub_channels']==[8,9,10,11]
    for name,part in v['parts'].items():
        assert part['valid_solid'] and part['closed_mesh']
        for ext in ['stl','step']:assert sha(OUT/f'{name}.{ext}')==part[f'{ext}_sha256']


def test_body_lengthens_by_the_requested_length_and_keeps_the_pcb_datums():
    e,v=load(EYES),load(OUT);L=v['variant']['middle_legs']['lengthen_mm']
    for name in ['internal-frame','bottom-cover','head-cover','head-lid']:
        lo,hi=e['parts'][name]['bounds_mm'];vlo,vhi=v['parts'][name]['bounds_mm']
        assert abs((vhi[0]-vlo[0])-(hi[0]-lo[0])-L)<1e-4,name
        for k in [1,2]:assert abs(vlo[k]-lo[k])<1e-4 and abs(vhi[k]-hi[k])<1e-4,name
    assert v['pcb_mount_holes_mm']==e['pcb_mount_holes_mm'] and v['pcb_size_mm']==e['pcb_size_mm']
    assert v['electronics_intersections']==[] and min(v['head_fit']['spacer_clearances_mm'])>=.6
    assert len(v['head_fit']['display_windows'])==2


def test_three_evenly_spaced_leg_stations_with_identical_bays():
    v=load(OUT);m=v['servo_mounts']
    assert set(m)=={'L1','L2','L5','R1','R2','R5'}
    xs=[m[n]['caseCenter'][0] for n in ['L2','L5','L1']]
    assert abs((xs[1]-xs[0])-(xs[2]-xs[1]))<.05 and xs[1]-xs[0]>45
    for side in 'LR':
        front,middle=m[side+'1'],m[side+'5']
        assert abs(front['caseCenter'][1]-middle['caseCenter'][1])<1e-6
        assert abs((front['holes'][1][0]-front['holes'][0][0])-(middle['holes'][1][0]-middle['holes'][0][0]))<1e-6
    checks=v['servo_bay_checks']
    assert all(c['volume_difference_mm3']<1e-3 and c['max_surface_deviation_mm']<c['tolerance_mm']<=.2 for c in checks)


def test_head_and_frame_screw_axes_still_match():
    v=load(OUT)
    assert len(v['head_mount_axes_xy_mm'])==4 and v['head_fit']['electronics_intersections']==[]
    assert v['head_fit']['cable_checks'].startswith('not run')
