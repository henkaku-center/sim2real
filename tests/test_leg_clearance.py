"""CAD-derived leg clearance: numbers with tolerances, determinism, stale evidence and consumers.

Every figure here comes from nominal CAD (upstream v117 leg prints against the
printed body parts). Nothing in this file is a physical measurement.
"""
import copy
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_design  # noqa: E402
import leg_clearance as lc  # noqa: E402

BASE = ROOT / 'assets/printing/internal-frame-s3'
EYES = ROOT / 'assets/printing/internal-frame-s3-two-eyes'
SIX = ROOT / 'assets/printing/internal-frame-s3-two-eyes-six-legs'
HIPS = ['L1', 'R1', 'L2', 'R2']
FRONT, REAR = ['L1', 'R1'], ['L2', 'R2']
# Servo degrees at 10 degrees toward the middle of the body.
TEN_TOWARD_MIDDLE = {'L1': 100, 'R2': 100, 'R1': 80, 'L2': 80}
STUDIO_LIMITS = {'L1': [0, 135], 'R2': [0, 135], 'R1': [45, 180], 'L2': [45, 180]}
PROPOSED_LIMITS = {'L1': [0, 100], 'R2': [0, 100], 'R1': [80, 180], 'L2': [80, 180]}


@pytest.fixture(scope='module')
def fresh():
    return lc.analyse(BASE)


@pytest.fixture(scope='module')
def committed():
    return {path.name: json.loads((path / lc.EVIDENCE).read_text()) for path in (BASE, EYES)}


@pytest.fixture(scope='module')
def manifests():
    return lc.load_manifests()


def close(a, b, tolerance):
    """Structural equality with an absolute tolerance on numbers."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k], tolerance) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return a == b
    return abs(a - b) <= tolerance


def test_rest_gap_is_the_head_cover_side_wall(fresh):
    for name in HIPS:
        rest = fresh['hips'][name]['rest']
        assert rest['servo_deg'] == 90 and rest['partner'] == 'head-cover'
        assert rest['gap_mm'] == pytest.approx(2.33, abs=0.05), name
        # The lid sits above and the bottom cover below the print's height range.
        assert set(fresh['hips'][name]['out_of_reach_vertical_gap_mm']) == {'head-lid', 'bottom-cover'}


def test_first_contact_toward_the_middle_is_the_head_cover_at_thirteen_degrees(fresh):
    for name in HIPS:
        hip = fresh['hips'][name]
        middle = hip['toward_middle']
        assert middle['partner'] == 'head-cover'
        assert middle['first_contact_deg'] == pytest.approx(13.0, abs=0.3), name
        assert middle['first_contact_servo_deg'] == pytest.approx(103 if name in ('L1', 'R2') else 77, abs=0.3)
        assert middle['first_contact_by_part_deg']['internal-frame'] == pytest.approx(27.0, abs=0.5)
        assert middle['min_gap_mm'] == 0.0 and middle['free_deg'] == middle['first_contact_deg']
        # Ten degrees toward the middle leaves about half a millimetre.
        gap, partner = lc._gap_at(hip, TEN_TOWARD_MIDDLE[name])
        assert partner == 'head-cover' and gap == pytest.approx(0.5, abs=0.05), name
        assert 6.5 < middle['gap_below_near_from_deg'] < 8.0


def test_head_cover_gap_is_constant_toward_the_end(fresh):
    for name in HIPS:
        hip = fresh['hips'][name]
        end = hip['toward_end']
        assert end['servo_direction'] != hip['toward_middle']['servo_direction']
        low, high = end['sampled_gap_range_by_part_mm']['head-cover']
        assert low == pytest.approx(hip['rest']['gap_mm'], abs=0.03) and high == pytest.approx(hip['rest']['gap_mm'], abs=0.03)
        # The whole 90 degrees, straight from the one-degree profile.
        profile = hip['gap_profile_mm']['head-cover']
        side = profile[:91] if end['servo_direction'] == 'decreasing' else profile[90:]
        assert len(side) == 91 and all(abs(gap - hip['rest']['gap_mm']) < 0.03 for gap in side), name


def test_front_hips_cross_a_shallow_frame_band_and_rear_hips_stay_free(fresh):
    expected = {'L1': [9.4, 21.0], 'R1': [159.0, 170.6]}
    for name in FRONT:
        hip = fresh['hips'][name]
        (band,) = [b for b in hip['contact_bands'] if b['transient']]
        assert band['partner'] == 'internal-frame'
        assert band['servo_deg'] == pytest.approx(expected[name], abs=0.5), name
        assert 0.2 < band['max_overlap_mm'] < 0.5
        end = hip['toward_end']
        assert end['partner'] == 'internal-frame' and end['first_contact_deg'] == pytest.approx(69.0, abs=0.5)
        # Past the band the print is free again up to the end of servo travel.
        travel_end = 0 if end['servo_direction'] == 'decreasing' else 180
        assert lc._classify_point(hip, travel_end, 1.0)['kind'] == 'near'
    for name in REAR:
        end = fresh['hips'][name]['toward_end']
        assert end['first_contact_deg'] is None and end['free_deg'] == 90
        assert end['min_gap_partner'] == 'internal-frame' and 0.15 < end['min_gap_mm'] < 0.35
        assert not any(b['transient'] for b in fresh['hips'][name]['contact_bands'])
    assert fresh['hips']['L1']['free_servo_deg'] == pytest.approx([21.0, 103.0], abs=0.5)
    assert fresh['hips']['R2']['free_servo_deg'] == pytest.approx([0.0, 103.0], abs=0.5)
    assert fresh['hips']['R1']['free_servo_deg'] == pytest.approx([77.0, 159.0], abs=0.5)
    assert fresh['hips']['L2']['free_servo_deg'] == pytest.approx([77.0, 180.0], abs=0.5)
    # The upstream stack height (prints 0.216 mm higher) changes no contact edge.
    assert fresh['datum_sensitivity']['same_contact_bands']
    assert fresh['datum_sensitivity']['max_contact_edge_shift_deg'] <= 0.05


def test_feet_and_neighbouring_legs_are_contact_free_on_the_grid(fresh):
    assert set(fresh['feet']) == {'L3', 'R3', 'L4', 'R4'}
    for name, foot in fresh['feet'].items():
        assert foot['free_servo_deg'] == [0.0, 180.0] and foot['body_contact_count'] == 0, name
        assert foot['own_hip_print_contact_bands_servo_deg'] == []
        assert foot['min_body_gap_mm'] > 5 and foot['own_hip_print_min_gap_mm'] > 2
        assert foot['grid']['poses'] >= 18 * 37
    assert len(fresh['neighbours']) == 2 and all(pair['min_gap_mm'] > 5 for pair in fresh['neighbours'])


def test_placement_reproduces_the_recorded_base_leg_samples():
    """Independent repo record: the base design's Rest and Standing leg samples (hips and feet)."""
    import numpy as np
    import trimesh
    assembly = json.loads((BASE / 'assembly.json').read_text())
    recorded = json.loads((BASE / 'head-cable-clearance.json').read_text())['leg_samples']
    meshes = {name: trimesh.load(ROOT / lc.LEGS / f'{name}-v117.stl', process=False, force='mesh')
              for hip, foot in lc.PRINTS.items() for name in (hip, foot)}
    legs = {hip: lc.Leg(hip, assembly, meshes) for hip in lc.PRINTS}
    poses = {'rest': {name: 90 for name in meshes},
             'standing': {'R1': 135, 'R2': 45, 'L1': 45, 'L2': 135, 'R4': 0, 'R3': 180, 'L3': 0, 'L4': 180}}
    assert len(recorded) == 16
    for sample in recorded:
        part, pose = sample['part'], poses[sample['pose']]
        leg = legs[part] if part in legs else next(leg for leg in legs.values() if leg.foot == part)
        transform = leg.transform(pose[leg.hip], None if part == leg.hip else pose[part])
        vertices = trimesh.transform_points(meshes[part].vertices, transform)
        assert np.abs(np.array([vertices.min(0), vertices.max(0)]) - np.array(sample['bounds_mm'])).max() < 1e-3, (part, sample['pose'])
    # The wide foot-servo side (13.95 mm from the hip axis against 6.37 mm) faces the middle at every corner.
    for hip, leg in legs.items():
        x = trimesh.transform_points(meshes[hip].vertices, leg.transform(90))[:, 0]
        toward_middle, toward_end = (leg.hx - x.min(), x.max() - leg.hx) if leg.hx > 0 else (x.max() - leg.hx, leg.hx - x.min())
        assert toward_middle == pytest.approx(13.95, abs=0.01) and toward_end == pytest.approx(6.37, abs=0.01), hip


def test_servo_convention_agrees_with_the_manifest(fresh, manifests):
    robot, _ = manifests
    joints = {joint['name']: joint for joint in robot['joints']}
    for name in HIPS:
        hip = fresh['hips'][name]
        assert hip['leg'] == joints[name]['leg'] and joints[name]['role'] == 'hip'
        # Manifest: internal q = (servo - 90) * sign, and q > 0 is the Standing (end) direction.
        assert hip['toward_end']['servo_direction'] == ('increasing' if joints[name]['sign'] > 0 else 'decreasing')
        stand = robot['poses']['stand'][name]
        assert (stand > 90) == (hip['toward_end']['servo_direction'] == 'increasing')
        assert hip['wide_side_faces'] == ('rear' if 'front' in hip['leg'] else 'front')
    for name, foot in fresh['feet'].items():
        assert foot['leg'] == joints[name]['leg'] and joints[name]['role'] == 'foot'


def test_committed_evidence_is_fresh_and_matches_a_new_run(fresh, committed):
    for path in (BASE, EYES):
        assert lc.verify(path) == {'fresh': True, 'stale': []}, path.name
    # Hash freshness pins inputs and checker; numbers also agree across platforms within rounding.
    assert close(committed[BASE.name], fresh, 0.02)
    assert committed[BASE.name]['scope'].startswith('CAD-derived, not physical')


def test_two_eye_variant_keeps_the_base_clearances(committed):
    base, eyes = committed[BASE.name], committed[EYES.name]
    assert eyes['design'] == EYES.name and eyes['inputs']['head-cover.stl'] != base['inputs']['head-cover.stl']
    for name in HIPS:
        a, b = base['hips'][name], eyes['hips'][name]
        # Walls and hip shafts both move out 15 mm, so the side clearance is unchanged.
        assert abs(b['hip_shaft_xy_mm'][1]) - abs(a['hip_shaft_xy_mm'][1]) == pytest.approx(15.0, abs=1e-6)
        assert b['rest']['gap_mm'] == pytest.approx(2.33, abs=0.05) and b['rest']['partner'] == 'head-cover'
        assert b['toward_middle']['first_contact_deg'] == pytest.approx(13.0, abs=0.3)
        assert b['toward_middle']['partner'] == 'head-cover'
        assert b['free_servo_deg'] == pytest.approx(a['free_servo_deg'], abs=0.2)
    assert all(foot['free_servo_deg'] == [0.0, 180.0] for foot in eyes['feet'].values())


def test_analysis_is_deterministic(fresh):
    assert lc.dumps(lc.analyse(BASE)) == lc.dumps(fresh)
    text = lc.dumps(fresh)
    assert json.loads(text) == fresh and text.endswith('}\n')


def test_middle_leg_stations_are_reported_as_not_run():
    with pytest.raises(ValueError, match='not supported'):
        lc.analyse(SIX)
    assert not lc.verify(SIX)['fresh']


@pytest.fixture
def copy_repo(tmp_path):
    """A hash-only copy: both designs' inputs and evidence, the leg prints and the manifests."""
    for design in (BASE, EYES):
        target = tmp_path / lc.PRINTING / design.name
        target.mkdir(parents=True)
        for name in ['assembly.json', lc.EVIDENCE] + [f'{part}.stl' for part in lc.BODY_PARTS]:
            shutil.copy(design / name, target / name)
    shutil.copytree(ROOT / lc.LEGS, tmp_path / lc.LEGS)
    shutil.copytree(ROOT / 'manifest', tmp_path / 'manifest')
    return tmp_path


def test_stale_evidence_is_detected(copy_repo):
    design = copy_repo / lc.PRINTING / BASE.name
    assert lc.verify(design, copy_repo)['fresh']

    def changed(path, edit):
        original = path.read_bytes()
        try:
            edit(path)
            return lc.verify(design, copy_repo)
        finally:
            path.write_bytes(original)

    append = lambda path: path.write_bytes(path.read_bytes() + b'\0')
    assert changed(design / 'head-cover.stl', append) == {'fresh': False, 'stale': ['head-cover.stl changed']}
    assert changed(copy_repo / lc.LEGS / 'L1-v117.stl', append)['stale'] == [f'{lc.LEGS}/L1-v117.stl changed']

    def edit_json(mutate):
        def edit(path):
            data = json.loads(path.read_text())
            mutate(data)
            path.write_text(json.dumps(data))
        return edit

    def move_hip(data):
        data['hip_shaft_xy_mm']['L1'][1] += 0.5
    assert changed(design / 'assembly.json', edit_json(move_hip))['stale'] == ['assembly.json datums changed']
    # Receipt fields this check does not consume leave the evidence current.
    assert changed(design / 'assembly.json', edit_json(lambda data: data.update(fit_note='edited')))['fresh']
    assert changed(design / lc.EVIDENCE, edit_json(lambda data: data.update(checker_sha256='0' * 64)))['stale'] == ['tools/leg_clearance.py changed']
    assert changed(design / lc.EVIDENCE, edit_json(lambda data: data['datums'].update(hip_axis_x_mm=2)))['stale'] == ['leg datums or settings changed']
    (design / lc.EVIDENCE).unlink()
    assert not lc.verify(design, copy_repo)['fresh']


def with_limits(robot, limits):
    revised = copy.deepcopy(robot)
    for joint in revised['joints']:
        if joint['name'] in limits:
            joint['limits_deg'] = limits[joint['name']]
    return revised


def test_sesame_studio_limits_exceed_the_free_range_toward_the_middle(fresh, manifests):
    robot, motions = manifests
    report = lc.compare(fresh, with_limits(robot, STUDIO_LIMITS), motions)
    assert set(report['limits_exceed_free_range']) == set(HIPS)
    rows = {row['joint']: row for row in report['limits']}
    for name in HIPS:
        (end,) = [e for e in rows[name]['ends'].values() if e['direction'] == 'toward_middle']
        assert end['kind'] == 'contact' and end['beyond_stop_deg'] == pytest.approx(32.0, abs=0.3), name
    for name in ('L3', 'R3', 'L4', 'R4'):
        assert rows[name]['exceeds'] is False and rows[name]['free_servo_deg'] == [0.0, 180.0]


def test_ten_degree_limit_stays_inside_but_within_a_millimetre(fresh, manifests):
    robot, motions = manifests
    report = lc.compare(fresh, with_limits(robot, PROPOSED_LIMITS), motions)
    rows = {row['joint']: row for row in report['limits']}
    for name in HIPS:
        (end,) = [e for e in rows[name]['ends'].values() if e['direction'] == 'toward_middle']
        assert end['kind'] == 'near' and end['partner'] == 'head-cover' and end['beyond_stop_deg'] == 0
        assert end['gap_mm'] == pytest.approx(0.5, abs=0.05)
        (other,) = [e for e in rows[name]['ends'].values() if e['direction'] == 'toward_end']
        assert other['beyond_stop_deg'] == 0 and other['kind'] in ('near', 'clear')
    # No limit lies past a stop. The front hips' limits still span the shallow
    # frame band, which has free travel on both sides and is reported as such.
    assert report['limits_exceed_free_range'] == []
    assert set(report['limits_cross_transient_bands']) == set(FRONT)
    for name in FRONT:
        (band,) = rows[name]['transient_bands_within_limits']
        assert band['partner'] == 'internal-frame' and band['max_overlap_mm'] < 0.5
        assert rows[name]['between_stops_servo_deg'] == pytest.approx([0.0, 103.0] if name == 'L1' else [77.0, 180.0], abs=0.5)
    for name in REAR:
        assert rows[name]['transient_bands_within_limits'] == []


def test_manifest_hip_limits_are_the_course_body_values(fresh, manifests):
    robot, motions = manifests
    assert {j['name']: j['limits_deg'] for j in robot['joints'] if j['role'] == 'hip'} == PROPOSED_LIMITS
    report = lc.compare(fresh, robot, motions)
    assert report['limits_exceed_free_range'] == []
    # Three degrees and half a millimetre short of first contact with the head cover.
    for name in HIPS:
        middle = fresh['hips'][name]['toward_middle']
        assert middle['first_contact_deg'] - 10 == pytest.approx(3.0, abs=0.1)


def test_stock_motions_that_swing_ten_degrees_toward_the_middle_are_flagged_close(fresh, manifests):
    robot, motions = manifests
    report = lc.compare(fresh, robot, motions)
    assert report['motions_checked'] == len(motions['motions']) == 19
    found = {(f['motion'], f['joint']): f for f in report['motions']}
    for motion in ('walk', 'point'):
        finding = found[(motion, 'R2')]
        assert finding['kind'] == 'near' and finding['partner'] == 'head-cover' and finding['servo_deg'] == 100
        assert finding['gap_mm'] == pytest.approx(0.5, abs=0.05)
    # No stock motion reaches the head cover; every contact finding is the shallow frame band.
    assert not [f for f in report['motions'] if f['partner'] == 'head-cover' and f['kind'] != 'near']
    crossing = [f for f in report['motions'] if f['kind'] == 'crosses-contact']
    assert crossing and all(f['partner'] == 'internal-frame' and f['joint'] in FRONT and f['max_overlap_mm'] < 0.5 for f in crossing)
    assert {'walk', 'walk_backward', 'pushup', 'bow'} <= {f['motion'] for f in crossing}
    assert not [f for f in report['motions'] if f['kind'] == 'contact']
    for motion in ('rest', 'stand', 'dance', 'swim', 'crab'):
        assert not [f for f in report['motions'] if f['motion'] == motion], motion


def test_check_design_reports_cad_derived_legs_and_fails_when_stale(copy_repo):
    report = check_design.leg_clearance_report()
    assert report['ok'] and set(report['designs']) == {BASE.name, EYES.name}
    for entry in report['designs'].values():
        assert entry['state'] == 'cad-derived' and entry['stale'] == []
        assert entry['hips']['L1']['toward_middle']['partner'] == 'head-cover'
        # The manifest's hip limits no longer reach a stop on either design.
        assert entry['manifest']['limits_exceed_free_range'] == []
        assert entry['manifest']['limits_cross_transient_bands'] == ['R1', 'L1']
    assert check_design.leg_clearance_report(copy_repo)['ok']
    stl = copy_repo / lc.PRINTING / EYES.name / 'internal-frame.stl'
    stl.write_bytes(stl.read_bytes() + b'\0')
    stale = check_design.leg_clearance_report(copy_repo)
    assert not stale['ok'] and stale['designs'][BASE.name]['state'] == 'cad-derived'
    entry = stale['designs'][EYES.name]
    assert entry['state'] == 'stale' and entry['stale'] == ['internal-frame.stl changed'] and 'hips' not in entry


@pytest.mark.parametrize('fresh_evidence', [True, False])
def test_check_design_stage_and_exit_code(monkeypatch, capsys, fresh_evidence):
    """The whole command, with its slow child test suites replaced by a passing stub."""
    stub = SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='', stderr=''),
                           TimeoutExpired=check_design.subprocess.TimeoutExpired)
    monkeypatch.setattr(check_design, 'subprocess', stub)
    if not fresh_evidence:
        real = lc.verify
        monkeypatch.setattr(lc, 'verify', lambda directory, root=ROOT: {'fresh': False, 'stale': ['head-cover.stl changed']}
                            if Path(directory).name == EYES.name else real(directory, root))
    code = check_design.main()
    output = json.loads(capsys.readouterr().out)
    check = next(c for c in output['checks'] if c['name'] == 'leg-clearance-evidence')
    stage = next(s for s in output['trace'] if s['stage'] == 'Cable and leg clearances')
    assert stage['state'] == 'partial'
    assert stage['cables'] == {'state': 'unverified', 'evidence': 'not run: authored ribbon routes are for the base frame'}
    assert stage['legs']['scope'].startswith('CAD-derived, not physical')
    assert (code, output['ok'], check['ok']) == ((0, True, True) if fresh_evidence else (1, False, False))
    assert stage['legs']['state'] == ('cad-derived' if fresh_evidence else 'stale')
    assert check['result'][EYES.name]['state'] == ('cad-derived' if fresh_evidence else 'stale')
