"""Metadata proof/rejection tests. Fixtures are files, never regenerated CAD."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import revalidate_body_provenance as provenance


@pytest.fixture
def fixture_repo(tmp_path, monkeypatch):
    committed = json.loads((ROOT / provenance.REPORT).read_bytes())
    old_yaml = committed[provenance.PROOF]['original_manifest_yaml'].encode()
    frozen = b'synthetic frozen source, not a geometry model'
    exported = b'synthetic export, not a geometry model'
    files = {
        provenance.MANIFEST: old_yaml,
        'assets/body/params.json': provenance.encoded({'fixture': 'unchanged'}),
        'assets/body/frozen-inputs.json': provenance.encoded({'assets/stl/upstream/fixture.stl': provenance.sha(frozen)}),
        'assets/stl/upstream/fixture.stl': frozen,
        'assets/body/v1/fixture.stl': exported,
        'assets/body/v1/preview.png': b'synthetic preview file',
        'assets/body/v1/assembly.json': provenance.encoded({'export_hashes': {'fixture.stl': provenance.sha(exported)}}),
        **{path: (ROOT / path).read_bytes() for path in provenance.AUDITED_CONSUMERS},
    }
    report = {
        'status': 'FAIL-DRAFT', 'release_ready': False, 'geometry_pass': False,
        'parameters': {'fixture': 'unchanged'}, 'results': ['original synthetic finding'],
        'input_hashes': {path: provenance.sha(data) for path, data in files.items()
                         if path in provenance.AUDITED_CONSUMERS or path == provenance.MANIFEST},
        'source_hashes': {'fixture.stl': provenance.sha(frozen)},
    }
    files[provenance.REPORT] = provenance.encoded(report)
    # Synthetic baseline report only; consumer code pins remain the real audited pins.
    monkeypatch.setattr(provenance, 'AUDITED_REPORT_SHA256', provenance.sha(files[provenance.REPORT]))
    preserved = {path: provenance.sha(data) for path, data in files.items()
                 if path not in (provenance.REPORT, provenance.MANIFEST)}
    monkeypatch.setattr(provenance, 'AUDITED_PRESERVED_SHA256', provenance.sha(provenance.encoded(preserved)))
    baseline = provenance.AUDITED_REPORT_COMMIT

    def git_object(_root, *args):
        if args[:1] == ('rev-parse',):
            return (baseline + '\n').encode()
        if args[:1] == ('ls-tree',):
            return b'\0'.join(p.encode() for p in sorted(files) if p.startswith('assets/body/')) + b'\0'
        assert args[0] == 'show'
        revision, path = args[1].split(':', 1)
        assert revision == baseline
        data = files[path]
        if path.endswith('.stl'):
            # Exercise Git LFS pointer identity without needing a CAD kernel.
            return f'version https://git-lfs.github.com/spec/v1\noid sha256:{provenance.sha(data)}\nsize {len(data)}\n'.encode()
        return data

    monkeypatch.setattr(provenance, 'git', git_object)
    for path, data in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (tmp_path / provenance.MANIFEST).write_bytes((ROOT / provenance.MANIFEST).read_bytes())
    return tmp_path, baseline, files


def test_committed_revalidation_is_true_and_keeps_hold():
    proof = provenance.verify(ROOT)
    assert proof['original_commit'] == provenance.AUDITED_REPORT_COMMIT
    assert proof['validator_executed'] is False
    assert proof['method'] == 'unused-s3-firmware-metadata-v2'
    assert proof['allowed_manifest_changes'] == provenance.ALLOWED_MANIFEST_CHANGES
    assert proof['original_input_hashes'][provenance.MANIFEST] == '2912c38dd40bd622694a103be345d6c2a7374ef05b85a5a511314ff0ccc58bae'


def test_refresh_preserves_reconstructible_execution_and_is_idempotent(fixture_repo):
    root, baseline, files = fixture_repo
    original = json.loads(files[provenance.REPORT])
    updated = provenance.refresh(root, baseline)
    proof = provenance.verify(root)
    reconstructed = copy.deepcopy(updated)
    reconstructed.pop(provenance.PROOF)
    reconstructed['input_hashes'] = proof['original_input_hashes']
    assert reconstructed == original
    assert provenance.encoded(reconstructed) == files[provenance.REPORT]
    assert set(updated) - set(original) == {provenance.PROOF}
    assert all((root / path).read_bytes() == data for path, data in files.items()
               if path not in (provenance.REPORT, provenance.MANIFEST))
    first = (root / provenance.REPORT).read_bytes()
    provenance.refresh(root, baseline)
    assert (root / provenance.REPORT).read_bytes() == first


def test_exact_firmware_deltas_preserve_effective_body_identity(fixture_repo):
    root, baseline, files = fixture_repo
    old = files[provenance.MANIFEST]
    original = yaml.safe_load(old)
    revised = copy.deepcopy(original)
    hw = revised['hardware_profiles']['sesame_s3']
    for change in provenance.ALLOWED_MANIFEST_CHANGES:
        hw[change['path'][-1]] = copy.deepcopy(change['value'])
    expected = provenance.sha(provenance.encoded(original))
    assert provenance.effective_identity(old, yaml.safe_dump(revised)) == expected
    assert provenance.effective_identity(old, (ROOT / provenance.MANIFEST).read_bytes()) == expected
    provenance.refresh(root, baseline)
    assert provenance.verify(root)['effective_manifest_sha256'] == expected


@pytest.mark.parametrize('field,value', [
    ('clock_measure_gpio', 5), ('clock_measure_gpio', 4.0),
    ('clock_measure_gpio', True), ('clock_measure_gpio', '4'),
    ('calibration_compatible_manifest_ids', ['bd7675604b98ae46', '0000000000000000']),
    ('calibration_compatible_manifest_ids', 'bd7675604b98ae46'),
    ('calibration_compatible_manifest_ids', []),
    ('intended_channels_status', 'physically-verified'),
    ('pulse_profile', {'id': 'different-profile'}),
])
def test_changed_allowed_field_values_are_not_a_blanket_exception(fixture_repo, field, value):
    root, baseline, files = fixture_repo
    data = yaml.safe_load((root / provenance.MANIFEST).read_text())
    data['hardware_profiles']['sesame_s3'][field] = value
    (root / provenance.MANIFEST).write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='unaudited firmware metadata value'):
        provenance.refresh(root, baseline)
    assert (root / provenance.REPORT).read_bytes() == files[provenance.REPORT]


@pytest.mark.parametrize('field', ['clock_measure_gpio', 'calibration_compatible_manifest_ids',
                                 'intended_channels_status', 'pulse_profile'])
def test_missing_audited_field_is_rejected(fixture_repo, field):
    root, baseline, files = fixture_repo
    data = yaml.safe_load((root / provenance.MANIFEST).read_text())
    del data['hardware_profiles']['sesame_s3'][field]
    (root / provenance.MANIFEST).write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='unaudited firmware metadata value'):
        provenance.refresh(root, baseline)
    assert (root / provenance.REPORT).read_bytes() == files[provenance.REPORT]


@pytest.mark.parametrize('field', ['joint_limit', 'neutral', 'other_hardware_field', 'scalar_type',
                                 'recommended_channel_map', 'joint_overlay_limits', 'unknown_metadata'])
def test_effective_manifest_changes_rejected_before_write(fixture_repo, field):
    root, baseline, files = fixture_repo
    data = yaml.safe_load((root / provenance.MANIFEST).read_text())
    if field == 'joint_limit':
        data['joints'][0]['limits_deg'][0] += 1
    elif field == 'neutral':
        data['conventions']['firmware_neutral_deg'] += 1
    elif field == 'scalar_type':
        data['joints'][0]['sign'] = True  # Python True == 1 must not bypass the diff.
    elif field == 'recommended_channel_map':
        data['hardware_profiles']['sesame_s3']['intended_channels']['R1'] = 6
    elif field == 'joint_overlay_limits':
        data['hardware_profiles']['sesame_s3']['initial_limits_deg'] = [0, 180]
    elif field == 'unknown_metadata':
        data['hardware_profiles']['sesame_s3']['unknown_firmware_feature'] = True
    else:
        data['hardware_profiles']['sesame_s3']['sda'] += 1
    (root / provenance.MANIFEST).write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='effective inputs changed'):
        provenance.refresh(root, baseline)
    assert (root / provenance.REPORT).read_bytes() == files[provenance.REPORT]


@pytest.mark.parametrize('path', [
    'tools/check_body.py', 'sim/manifest.py', 'assets/body/params.json',
    'assets/body/frozen-inputs.json', 'assets/stl/upstream/fixture.stl',
    'assets/body/v1/fixture.stl', 'assets/body/v1/assembly.json',
])
def test_source_asset_or_export_changes_rejected_without_report_write(fixture_repo, path):
    root, baseline, files = fixture_repo
    (root / path).write_bytes(files[path] + b'\nchanged')
    with pytest.raises((ValueError, json.JSONDecodeError)):
        provenance.refresh(root, baseline)
    assert (root / provenance.REPORT).read_bytes() == files[provenance.REPORT]


@pytest.mark.parametrize('mutation', [
    'result', 'release', 'geometry', 'status', 'original_hash', 'original_commit',
    'original_manifest', 'original_inputs', 'executed_claim', 'coverage', 'missing_proof',
    'allowed_metadata', 'method',
])
def test_tampered_provenance_or_results_rejected(fixture_repo, mutation):
    root, baseline, _ = fixture_repo
    report = provenance.refresh(root, baseline)
    proof = report[provenance.PROOF]
    if mutation == 'result': report['results'] = ['changed finding']
    elif mutation == 'release': report['release_ready'] = True
    elif mutation == 'geometry': report['geometry_pass'] = True
    elif mutation == 'status': report['status'] = 'PASS'
    elif mutation == 'original_hash': proof['original_report_sha256'] = '0' * 64
    elif mutation == 'original_commit': proof['original_commit'] = '0' * 40
    elif mutation == 'original_manifest': proof['original_manifest_yaml'] += '\n# tampered'
    elif mutation == 'original_inputs': proof['original_input_hashes'][provenance.MANIFEST] = '0' * 64
    elif mutation == 'executed_claim': proof['validator_executed'] = True
    elif mutation == 'coverage': del proof['preserved_sha256']['sim/manifest.py']
    elif mutation == 'missing_proof': del report[provenance.PROOF]
    elif mutation == 'allowed_metadata': proof['allowed_manifest_changes'][1]['value'] = 5
    elif mutation == 'method': proof['method'] = 'unused-s3-pulse-profile-addition-v1'
    with pytest.raises(ValueError): provenance.verify(root, report)


def test_blind_hash_replacement_is_not_accepted(fixture_repo):
    root, baseline, files = fixture_repo
    report = json.loads(files[provenance.REPORT])
    report['input_hashes'][provenance.MANIFEST] = provenance.sha((root / provenance.MANIFEST).read_bytes())
    (root / provenance.REPORT).write_bytes(provenance.encoded(report))
    with pytest.raises(ValueError, match='missing/unknown revalidation'): provenance.verify(root)
    with pytest.raises(ValueError, match='unexplained report edits'): provenance.refresh(root, baseline)


@pytest.mark.parametrize('change', ['add', 'delete', 'export_and_hash'])
def test_inventory_and_joint_export_hash_tampering_rejected(fixture_repo, change):
    root, baseline, _ = fixture_repo
    provenance.refresh(root, baseline)
    exported = root / 'assets/body/v1/fixture.stl'
    if change == 'add': (root / 'assets/body/v1/extra.stl').write_text('extra')
    elif change == 'delete': exported.unlink()
    else:
        exported.write_text('changed')
        (root / 'assets/body/v1/assembly.json').write_bytes(provenance.encoded(
            {'export_hashes': {'fixture.stl': provenance.sha(exported.read_bytes())}}))
    with pytest.raises(ValueError): provenance.verify(root)


def test_changed_manifest_cannot_reuse_previous_proof(fixture_repo):
    root, baseline, _ = fixture_repo
    provenance.refresh(root, baseline)
    with (root / provenance.MANIFEST).open('a') as out: out.write('\n# later change\n')
    with pytest.raises(ValueError, match='current input changed'): provenance.verify(root)


def test_changed_image_and_forged_proof_hash_cannot_relabel_original_asset(fixture_repo):
    root, baseline, _ = fixture_repo
    report = provenance.refresh(root, baseline)
    image = 'assets/body/v1/preview.png'
    (root / image).write_bytes(b'replacement image')
    report[provenance.PROOF]['preserved_sha256'][image] = provenance.sha((root / image).read_bytes())
    with pytest.raises(ValueError, match='original preserved-file identities changed'):
        provenance.verify(root, report)


@pytest.mark.parametrize('extra', ['manifest/robot.yaml', 'tools/check_body.py',
                                  'assets/body/params.json', 'assets/body/v1/face-cover.stl',
                                  'tests/test_body_cad.py', 'unknown.py'])
def test_mixed_or_uncertain_changes_keep_full_cad_coverage(extra):
    assert not provenance.provenance_only({provenance.REPORT, extra})


def test_scoped_ci_route_requires_report_and_exact_allowlist():
    assert provenance.provenance_only(provenance.PROVENANCE_PATHS)
    assert provenance.provenance_only({provenance.REPORT})
    assert not provenance.provenance_only(set())
    assert not provenance.provenance_only({'.github/workflows/body-cad.yml'})
    result = subprocess.run([sys.executable, str(ROOT / 'tools/revalidate_body_provenance.py'),
                             '--classify', '--base-ref', 'unknown', '--head-ref', 'unknown'],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'provenance_only=false'


def test_workflow_scopes_only_provenance_without_dropping_validation():
    workflow = yaml.safe_load((ROOT / '.github/workflows/body-cad.yml').read_text())
    job = workflow['jobs']['geometry']
    assert job['strategy']['max-parallel'] == 2
    steps = {s.get('name', s.get('uses')): s for s in job['steps']}
    assert steps['actions/checkout@v4']['with']['fetch-depth'] == 0
    verify = steps['Verify metadata-only provenance and rejection controls']
    assert verify['if'] == "steps.scope.outputs.provenance_only == 'true'"
    assert 'tests/test_body_provenance.py' in verify['run']
    for name in ['mamba-org/setup-micromamba@v2', 'Configure separate FreeCAD runtime',
                 'Detector regression tests', 'Full body fit acceptance (draft failures remain failures)']:
        assert steps[name]['if'] == "steps.scope.outputs.provenance_only != 'true'"


@pytest.mark.parametrize('ref', ['', '0' * 40])
def test_missing_comparison_refs_retain_full_cad_route(ref):
    result = subprocess.run([sys.executable, str(ROOT / 'tools/revalidate_body_provenance.py'),
                             '--classify', '--base-ref', ref, '--head-ref', ref],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'provenance_only=false'
