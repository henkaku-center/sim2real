"""Check the shipped frame/PCB geometry receipt without requiring FreeCAD in CI."""
import hashlib
import json
import os
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('INTERNAL_FRAME_OUTPUT',ROOT/'assets/printing/internal-frame-s3'))


def test_frame_artifacts_and_dimensions():
    report=json.loads((OUT/'assembly.json').read_text())
    assert report['source_script_sha256']==hashlib.sha256((ROOT/'tools/internal_frame_cad.py').read_bytes()).hexdigest()
    assert report['parameters']==json.loads((ROOT/'assets/printing/internal-frame-s3/params.json').read_text())
    assert report['pcb_size_mm']==[70.0,50.0,1.6]
    assert abs(report['support_width_mm']-report['source_support_width_mm']-18)<1e-5
    assert abs(report['support_width_mm']-56.44)<.001  # displayed nominal dimensions
    assert abs(report['pcb_side_margin_mm']-3.22)<.001
    old=report['source_frame_bounds_mm'];new=report['parts']['internal-frame']['bounds_mm']
    assert abs((new[1][1]-new[0][1])-(old[1][1]-old[0][1])-18)<1e-6
    for name,part in report['parts'].items():
        assert part['valid_solid'] and part['closed_mesh']
        for ext in ['stl','step']:
            assert hashlib.sha256((OUT/f'{name}.{ext}').read_bytes()).hexdigest()==part[f'{ext}_sha256']
        raw=(OUT/f'{name}.stl').read_bytes()
        assert struct.unpack_from('<I',raw,80)[0]==part['triangles']
        assert len(raw)==84+50*part['triangles']


def test_fit_and_existing_leg_interfaces():
    report=json.loads((OUT/'assembly.json').read_text())
    assert report['electronics_sha256']==hashlib.sha256((ROOT/'assets/cad/Sesame-S3-Assembly.FCStd').read_bytes()).hexdigest()
    assert report['electronics_shapes_checked']>600 and not report['electronics_intersections']
    for bay in report['servo_bay_checks']:
        assert abs(bay['translation_y_mm'])==9
        assert bay['surface_samples']>100
        assert bay['volume_difference_mm3']<1e-3
        assert bay['max_surface_deviation_mm']<1e-4
    assert len(report['unchanged_legs'])==8
    for name,digest in report['unchanged_legs'].items():
        assert hashlib.sha256((ROOT/f'assets/stl/upstream/{name}-v117.stl').read_bytes()).hexdigest()==digest
    holes=report['pcb_mount_holes_mm']
    assert len(holes)==4
    assert {round(p[0],4) for p in holes}=={-33,33}
    assert {round(p[1],4) for p in holes}=={-23.2,23.2}
    assert report['parts']['bottom-cover']['frame_intersection_mm3']<1e-3


def test_head_side_wall_space_is_reserved_clear_of_electronics():
    report=json.loads((OUT/'assembly.json').read_text());allowance=report['head_wall_allowance']
    assert allowance['wall_mm']==2 and allowance['pcb_gap_mm']==.6
    assert allowance['outer_gap_mm']>=.6
    assert not allowance['electronics_intersections'] and allowance['electronics_shapes_checked']==710
    left,right=allowance['side_wall_bounds_mm']
    assert abs(left[0][1]-25.6)<1e-6 and abs(left[1][1]-27.6)<1e-6
    assert abs(right[0][1]+27.6)<1e-6 and abs(right[1][1]+25.6)<1e-6
    assert left[0][0]==right[0][0]==-35 and left[1][0]==right[1][0]==35
    assert left[0][2]==right[0][2]==report['pcb_seat_z_mm']
    assert left[1][2]>left[0][2] and right[1][2]>right[0][2]


def test_bottom_cover_fasteners_are_centred_with_matching_axes():
    report=json.loads((OUT/'assembly.json').read_text());fixings=report['bottom_cover_fasteners']
    frame,cover=fixings['frame'],fixings['cover']
    assert len(frame)==len(cover)==2
    assert [(p['x_mm'],p['y_mm']) for p in frame]==[(p['x_mm'],p['y_mm']) for p in cover]
    for kind,records in [('frame',frame),('cover',cover)]:
        for p in records:
            assert p['y_mm']==0 and p['previous_widened_y_mm']==-9
            assert p['old_hole_closed'] and p['new_axis_clear']
            assert len(p['profile'])==(2 if kind=='frame' else 4)
            radii=[r for s in p['profile'] for r in s['radii_mm']]
            assert abs(min(radii)-(.72328 if kind=='frame' else 1.15))<1e-5
            assert abs(max(radii)-(1.48528 if kind=='frame' else 3.99796))<1e-5


def test_battery_wire_cutout_moves_without_changing_its_profile():
    report=json.loads((OUT/'assembly.json').read_text());port=report['battery_wire_cutout']
    assert port['location']=='front-right' and port['old_location']=='back-left'
    assert port['old_opening_closed'] and port['new_opening_clear']
    old=port['original_profile_bounds_mm'];new=port['profile_bounds_mm'];frame=report['source_frame_bounds_mm']
    assert old[1][0]<0 and old[0][1]>0 and new[0][0]>0 and new[1][1]<0
    for axis in [0,1]:assert abs((old[1][axis]-old[0][axis])-(new[1][axis]-new[0][axis]))<1e-6
    assert abs((old[0][0]+old[1][0]+new[0][0]+new[1][0])/2-(frame[0][0]+frame[1][0]))<1e-6
    assert abs(old[0][1]+old[1][1]+new[0][1]+new[1][1])<1e-6
