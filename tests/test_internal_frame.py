"""Check the shipped frame/PCB geometry receipt without requiring FreeCAD in CI."""
import hashlib
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/body/internal-frame-s3'


def test_frame_artifacts_and_dimensions():
    report=json.loads((OUT/'assembly.json').read_text())
    assert report['source_script_sha256']==hashlib.sha256((ROOT/'tools/internal_frame_cad.py').read_bytes()).hexdigest()
    assert report['parameters']==json.loads((OUT/'params.json').read_text())
    assert report['pcb_size_mm']==[70.0,50.0,1.6]
    assert abs(report['support_width_mm']-report['source_support_width_mm']-14)<1e-5
    assert abs(report['support_width_mm']-52.44)<.001  # displayed nominal dimensions
    assert abs(report['pcb_side_margin_mm']-1.22)<.001
    old=report['source_frame_bounds_mm'];new=report['parts']['internal-frame']['bounds_mm']
    assert abs((new[1][1]-new[0][1])-(old[1][1]-old[0][1])-14)<1e-6
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
        assert abs(bay['translation_y_mm'])==7
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
