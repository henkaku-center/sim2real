"""Check the delivered V3-derived kit and its native-CAD validation receipt."""
import hashlib
import json
import os
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('INTERNAL_FRAME_OUTPUT',ROOT/'assets/printing/internal-frame-s3'))
CANONICAL=ROOT/'assets/printing/internal-frame-s3'
def receipt():return json.loads((OUT/'assembly.json').read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_artifacts_match_the_validated_native_kit():
    r=receipt();assert r['reference_family']=='loftwork-printing-v3'
    assert r['source_script_sha256']==sha(ROOT/'tools/v3_assembly_cad.py')
    assert r['entry_script_sha256']==sha(ROOT/'tools/internal_frame_cad.py')
    assert r['validation_checker_sha256']==sha(ROOT/'tools/cad_validation_cache.py')
    assert len(r['validation_cache'])==9 and all(len(c['key'])==64 for c in r['validation_cache'])
    assert r['parameters']==json.loads((CANONICAL/'params.json').read_text())
    assert set(r['parts'])=={'internal-frame','bottom-cover','pcb-spacer','head-cover','head-lid'}
    for name,p in r['parts'].items():
        assert p['valid_solid'] and p['closed_mesh']
        for ext in ['stl','step']:assert sha(OUT/f'{name}.{ext}')==p[f'{ext}_sha256']
        raw=(OUT/f'{name}.stl').read_bytes();assert raw[80:84]==struct.pack('<I',p['triangles'])
        assert len(raw)==84+50*p['triangles']


def test_v3_reference_is_pinned_normalized_and_repaired_without_private_headers():
    r=receipt();source=r['source'];m=source['source_to_body_matrix']
    assert m[0]==m[5]==-1 and m[10]==1  # proper rotation, not a mirrored robot
    assert source['pcb_forward_adjustment_mm']==.6
    assert source['lid_seating_translation_z_mm']==-20
    for name,entry in source['files'].items():
        p=CANONICAL/'reference-v3'/f'{name}.step';assert sha(p)==entry['normalized_sha256']
        header=p.read_text().split('DATA;')[0]
        assert 'Sesame V3 reference' in header and '/Users/' not in header and 'C:\\' not in header
    assert source['files']['bottom']['repair']['free_edges']==3
    assert source['files']['bottom']['repair']['patch_area_mm2']<.1


def test_current_pcb_datums_and_screw_stack_are_retained():
    r=receipt();assert r['pcb_size_mm']==[70.,50.,1.6]
    assert len(r['pcb_mount_holes_mm'])==4
    assert {round(p[0],4) for p in r['pcb_mount_holes_mm']}=={-33,33}
    assert {round(p[1],4) for p in r['pcb_mount_holes_mm']}=={-23.2,23.2}
    assert r['pcb_hole_adjustment']['source_diameter_mm']==1.9
    assert r['pcb_hole_adjustment']['pilot_diameter_mm']==1.3
    assert len(r['pcb_hole_adjustment']['source_axes'])==4
    stack=r['pcb_fastening'];assert stack['spacer_height_mm']==3 and stack['screw_under_head_length_mm']==8
    assert abs(stack['nominal_frame_penetration_mm']-3.4)<1e-6
    assert abs(stack['tip_clearance_mm']-.8)<1e-6 and stack['minimum_pilot_floor_mm']==1.2
    assert abs(stack['model_deck_clearance_mm']-1.6)<1e-6


def test_frame_print_face_is_flat_and_spacers_are_separate():
    r=receipt();frame=r['parts']['internal-frame'];spacer=r['parts']['pcb-spacer']
    assert abs(frame['bounds_mm'][1][2]-r['servo_flange_seat_z_mm'])<1e-6
    assert spacer['quantity']==4 and len(spacer['assembly_origins_mm'])==4
    for origin,hole in zip(spacer['assembly_origins_mm'],r['pcb_mount_holes_mm']):
        assert origin[:2]==hole[:2] and abs(origin[2]+3-hole[2])<1e-6
    for name in ['internal-frame','head-cover','head-lid']:
        part=r['parts'][name]
        assert sha(OUT/part['print_stl'])==part['print_stl_sha256']
        raw=(OUT/part['print_stl']).read_bytes();vertices=[struct.unpack_from('<12fH',raw,84+i*50)[3:12] for i in range(struct.unpack_from('<I',raw,80)[0])]
        assert abs(min(z for p in vertices for z in p[2::3]))<1e-5


def test_servo_bays_and_leg_meshes_are_preserved():
    r=receipt();assert len(r['servo_mounts'])==4
    for m in r['servo_mounts'].values():assert abs(m['holes'][1][0]-m['holes'][0][0]-27.8)<1e-4
    for b in r['servo_bay_checks']:
        assert b['volume_difference_mm3']<1e-3 and b['max_surface_deviation_mm']<1e-4 and b['surface_samples']>100
    assert len(r['unchanged_legs'])==8
    for name,digest in r['unchanged_legs'].items():assert sha(ROOT/f'assets/stl/upstream/{name}-v117.stl')==digest


def test_fixings_and_battery_channel_remain_functional():
    r=receipt();bottom=r['bottom_cover_fasteners']
    assert bottom['matching_axes'] and abs(bottom['frame_intersection_mm3'])<.01
    assert len(bottom['frame'])==len(bottom['cover'])==2
    assert all(abs(p[1])<1e-3 for p in bottom['frame']+bottom['cover'])
    assert len(r['head_mount_axes_xy_mm'])==4
    port=r['battery_wire_cutout'];assert port['location']=='front-right' and port['corner_radius_mm']==1
    assert port['other_channel_walls_intact'] and port['new_cutout_wall_clear']


def test_head_lid_electronics_and_cable_entries_are_checked():
    r=receipt();h=r['head_fit']
    assert h['source_object']=='Loftwork V3 shell and removable lid'
    assert h['raise_mm']==0 and h['height_splice_z_mm']==47.7
    assert all(abs(a-b)<.001 for a,b in zip(h['assembled_size_mm'][:2],[87.17675,58.534]))
    assert h['assembled_size_mm'][2]<55 and len(h['ear_bounds_mm'])==2
    assert h['closed_upper_side_ports']==2 and h['ear_height_above_roof_mm']>5
    assert h['lid_plan']['shape'].startswith('T-shaped') and h['lid_plan']['clearance_mm']==.3
    assert len(h['lid_seating_samples'])==9 and all(abs(s['intersection_mm3'])<1e-3 for s in h['lid_seating_samples'])
    for name,entry in h['ear_source']['files'].items():assert sha(CANONICAL/'reference-ears'/f'{name}.step')==entry['sha256']
    assert h['display_window_unchanged'] and h['display_window']['width_mm']>20 and h['display_window']['height_mm']>11
    assert h['cable_notches']['bottom_open'] and h['cable_notches']['count']==2
    assert h['cable_notches']==r['head_cable_entry']
    assert 15<h['cable_notches']['width_mm']<16 and h['cable_notches']['top_z_mm']<15
    assert h['cable_electronics_samples_inside']==0
    assert min(h['spacer_clearances_mm'])>=.6 and abs(h['lid_intersection_mm3'])<1e-3
    assert r['electronics_shapes_checked']==710 and not r['electronics_intersections']
    assert h['cable_reference_sha256']==sha(CANONICAL/'head-cable-clearance.json')
    assert h['cable_entry_min_gap_mm']>=.2 and h['cable_samples_inside']==0
    assert len(h['leg_pose_checks'])==16 and all(x['separated_from_head'] for x in h['leg_pose_checks'])
