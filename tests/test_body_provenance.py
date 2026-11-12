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

# The current baseline (validator rerun of 2026-11-12) excepts no manifest
# difference. These fixture deltas keep the exact-delta mechanism under test
# without claiming that the real manifest carries any.
FIXTURE_CHANGES = [
    {'operation': 'add', 'path': ['hardware_profiles', 'sesame_s3', 'fixture_profile'],
     'value': {'id': 'fixture-profile-v1', 'ticks': [150, 512]}},
    {'operation': 'add', 'path': ['hardware_profiles', 'sesame_s3', 'fixture_gpio'], 'value': 4},
    {'operation': 'replace', 'path': ['hardware_profiles', 'sesame_s3', 'oe'],
     'original_value': 7, 'value': 8},
]


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


@pytest.fixture
def delta_repo(fixture_repo, monkeypatch):
    """The same repository with an audited delta list and a manifest that carries exactly those deltas."""
    root, baseline, files = fixture_repo
    monkeypatch.setattr(provenance, 'ALLOWED_MANIFEST_CHANGES', copy.deepcopy(FIXTURE_CHANGES))
    data = yaml.safe_load(files[provenance.MANIFEST])
    for change in FIXTURE_CHANGES:
        data['hardware_profiles']['sesame_s3'][change['path'][-1]] = copy.deepcopy(change['value'])
    (root / provenance.MANIFEST).write_text(yaml.safe_dump(data))
    return root, baseline, files


def test_committed_revalidation_is_true_and_keeps_hold():
    proof = provenance.verify(ROOT)
    assert proof['original_commit'] == provenance.AUDITED_REPORT_COMMIT == 'cf8241dcb69a0d37157745bba544677680d592ae'
    assert proof['validator_executed'] is False
    assert proof['method'] == 'executed-manifest-exact-v4'
    # The validator ran with the manifest as it is: nothing is excepted.
    assert proof['allowed_manifest_changes'] == provenance.ALLOWED_MANIFEST_CHANGES == []
    assert proof['original_manifest_yaml'].encode() == (ROOT / provenance.MANIFEST).read_bytes()
    assert proof['original_input_hashes'][provenance.MANIFEST] == '3b38a3fef45c53b7a4c918d1973a213bb3fec4291fd253d0b0807b7958326728'
    report = json.loads((ROOT / provenance.REPORT).read_bytes())
    assert report['status'] == 'FAIL-DRAFT' and not report['release_ready'] and not report['geometry_pass']
    # The rerun sampled the course hip range: -10 to +90 degrees.
    assert sorted({row['hip_deg'] for row in report['rom'] if row['mode'] == 'hip'})[::20] == [-10.0, 90.0]
    assert (report['summary']['rom_pairs'], report['summary']['rom_failures']) == (9648, 38)
    assert report['summary']['new_body_rom_failures'] == 0 and report['summary']['static_failures'] == 8


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


def test_current_baseline_excepts_no_manifest_difference(fixture_repo):
    root, baseline, files = fixture_repo
    old = files[provenance.MANIFEST]
    assert provenance.ALLOWED_MANIFEST_CHANGES == [] and old == (ROOT / provenance.MANIFEST).read_bytes()
    expected = provenance.sha(provenance.encoded(yaml.safe_load(old)))
    assert provenance.effective_identity(old, (ROOT / provenance.MANIFEST).read_bytes()) == expected
    provenance.refresh(root, baseline)
    assert provenance.verify(root)['effective_manifest_sha256'] == expected


def test_exact_audited_deltas_preserve_effective_body_identity(delta_repo):
    root, baseline, files = delta_repo
    old = files[provenance.MANIFEST]
    expected = provenance.sha(provenance.encoded(yaml.safe_load(old)))
    assert provenance.effective_identity(old, (root / provenance.MANIFEST).read_bytes()) == expected
    # The executed manifest itself no longer matches once deltas are declared.
    with pytest.raises(ValueError, match='unaudited firmware metadata value'):
        provenance.effective_identity(old, old)
    provenance.refresh(root, baseline)
    proof = provenance.verify(root)
    assert proof['effective_manifest_sha256'] == expected and proof['allowed_manifest_changes'] == FIXTURE_CHANGES


@pytest.mark.parametrize('field,value', [
    ('clock_measure_gpio', 5), ('clock_measure_gpio', 4.0),
    ('clock_measure_gpio', True), ('clock_measure_gpio', '4'),
    ('oe', 18), ('oe', 8), ('oe', 7.0), ('oe', True), ('oe', '7'),
    ('calibration_compatible_manifest_ids', ['e669b916d178ac0a']),
    ('calibration_compatible_manifest_ids', ['bd7675604b98ae46']),
    ('calibration_compatible_manifest_ids', ['e669b916d178ac0a', 'bd7675604b98ae46', '0000000000000000']),
    ('calibration_compatible_manifest_ids', ['bd7675604b98ae46', '0000000000000000']),
    ('calibration_compatible_manifest_ids', 'bd7675604b98ae46'),
    ('calibration_compatible_manifest_ids', []),
    ('calibration_compatible_manifest_ids', ['e669b916d178ac0a', 'bd7675604b98ae46']),
    ('calibration_compatible_manifest_ids', ['e669b916d178ac0a', 'bd7675604b98ae46', '8d75c0ea0b2c68e7', '0000000000000000']),
    ('intended_channels_status', 'physically-verified'),
    ('pulse_profile', {'id': 'different-profile'}),
])
def test_firmware_fields_excepted_before_the_rerun_are_effective_inputs_now(fixture_repo, field, value):
    """The October baseline excepted these fields; the rerun baseline excepts none."""
    root, baseline, files = fixture_repo
    data = yaml.safe_load((root / provenance.MANIFEST).read_text())
    assert provenance.encoded(data['hardware_profiles']['sesame_s3'][field]) != provenance.encoded(value)
    data['hardware_profiles']['sesame_s3'][field] = value
    (root / provenance.MANIFEST).write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='effective inputs changed'):
        provenance.refresh(root, baseline)
    assert (root / provenance.REPORT).read_bytes() == files[provenance.REPORT]


@pytest.mark.parametrize('field', ['clock_measure_gpio', 'calibration_compatible_manifest_ids',
                                 'intended_channels_status', 'pulse_profile', 'oe'])
def test_missing_firmware_field_is_rejected(fixture_repo, field):
    root, baseline, files = fixture_repo
    data = yaml.safe_load((root / provenance.MANIFEST).read_text())
    del data['hardware_profiles']['sesame_s3'][field]
    (root / provenance.MANIFEST).write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='effective inputs changed'):
        provenance.refresh(root, baseline)
    assert (root / provenance.REPORT).read_bytes() == files[provenance.REPORT]


@pytest.mark.parametrize('field,value', [
    ('fixture_gpio', 5), ('fixture_gpio', 4.0), ('fixture_gpio', True), ('fixture_gpio', '4'),
    ('oe', 7), ('oe', 9), ('oe', 8.0), ('oe', True), ('oe', '8'),
    ('fixture_profile', {'id': 'different-profile'}),
    ('fixture_profile', {'id': 'fixture-profile-v1', 'ticks': [150, 512], 'extra': 1}),
])
def test_changed_audited_delta_values_are_not_a_blanket_exception(delta_repo, field, value):
    root, baseline, files = delta_repo
    data = yaml.safe_load((root / provenance.MANIFEST).read_text())
    data['hardware_profiles']['sesame_s3'][field] = value
    (root / provenance.MANIFEST).write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='unaudited firmware metadata value'):
        provenance.refresh(root, baseline)
    assert (root / provenance.REPORT).read_bytes() == files[provenance.REPORT]


@pytest.mark.parametrize('field', ['fixture_gpio', 'fixture_profile', 'oe'])
def test_missing_audited_delta_field_is_rejected(delta_repo, field):
    root, baseline, files = delta_repo
    data = yaml.safe_load((root / provenance.MANIFEST).read_text())
    del data['hardware_profiles']['sesame_s3'][field]
    (root / provenance.MANIFEST).write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='unaudited firmware metadata value'):
        provenance.refresh(root, baseline)
    assert (root / provenance.REPORT).read_bytes() == files[provenance.REPORT]


def test_audited_deltas_do_not_admit_other_manifest_changes(delta_repo):
    root, baseline, files = delta_repo
    data = yaml.safe_load((root / provenance.MANIFEST).read_text())
    data['joints'][0]['limits_deg'][0] += 1
    (root / provenance.MANIFEST).write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='effective inputs changed outside the exact allowed firmware deltas'):
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
    elif mutation == 'allowed_metadata': proof['allowed_manifest_changes'].append(copy.deepcopy(FIXTURE_CHANGES[2]))
    elif mutation == 'method': proof['method'] = 'unused-s3-pulse-profile-addition-v1'
    with pytest.raises(ValueError): provenance.verify(root, report)


def test_blind_hash_replacement_is_not_accepted(delta_repo):
    # A manifest that differs from the executed one, even by audited deltas only,
    # cannot be blessed by writing its hash into the report.
    root, baseline, files = delta_repo
    assert (root / provenance.MANIFEST).read_bytes() != files[provenance.MANIFEST]
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


@pytest.mark.parametrize('extra', ['firmware/sesame-s3/controller.cpp', 'tools/check_body.py',
                                  'assets/body/params.json', 'assets/body/v1/face-cover.stl',
                                  'tests/test_body_cad.py', 'unknown.py'])
def test_mixed_or_uncertain_changes_keep_full_cad_coverage(extra):
    assert not provenance.provenance_only({provenance.REPORT, extra})


def test_audited_mixed_oe_companions_require_verified_body_proof(fixture_repo):
    root, baseline, _ = fixture_repo
    paths = provenance.PROVENANCE_PATHS | provenance.FIRMWARE_COMPANION_PATHS
    assert not provenance.provenance_only(paths, root)  # no wrapper yet
    provenance.refresh(root, baseline)
    scoped, reason = provenance.classify_body_scope(paths, root)
    assert scoped and reason == 'verified-unchanged-body-inputs-with-audited-companions'
    assert provenance.provenance_only({provenance.REPORT, provenance.MANIFEST,
                                      'firmware/sesame-s3/manifest_generated.h'}, root)
    assert not provenance.provenance_only(paths - {provenance.REPORT}, root)


@pytest.mark.parametrize('mutation', ['manifest', 'consumer', 'asset', 'release',
                                     'missing_proof', 'unhydrated_asset', 'malformed_manifest'])
def test_mixed_path_allowlist_cannot_bypass_current_proof(fixture_repo, mutation):
    root, baseline, _ = fixture_repo
    report = provenance.refresh(root, baseline)
    paths = {provenance.REPORT, provenance.MANIFEST, 'tools/generate_s3_firmware.py'}
    assert provenance.provenance_only(paths, root)
    if mutation == 'manifest':
        path = root / provenance.MANIFEST
        data = yaml.safe_load(path.read_text())
        data['hardware_profiles']['sesame_s3']['oe'] = 8
        path.write_text(yaml.safe_dump(data))
        # Even a forged current raw hash must not bypass exact input equivalence.
        report['input_hashes'][provenance.MANIFEST] = provenance.sha(path.read_bytes())
    elif mutation == 'consumer':
        with (root / 'tools/check_body.py').open('a') as out: out.write('\n# changed\n')
    elif mutation == 'asset':
        (root / 'assets/body/v1/preview.png').write_bytes(b'changed')
    elif mutation == 'release': report['release_ready'] = True
    elif mutation == 'missing_proof': del report[provenance.PROOF]
    elif mutation == 'unhydrated_asset':
        (root / 'assets/stl/upstream/fixture.stl').write_bytes(b'version https://git-lfs.github.com/spec/v1\n')
    else: (root / provenance.MANIFEST).write_text('invalid: [yaml')
    (root / provenance.REPORT).write_bytes(provenance.encoded(report))
    scoped, reason = provenance.classify_body_scope(paths, root)
    assert not scoped and reason.startswith('proof-not-established-')


def test_exact_oe_pr_paths_are_candidates_without_broad_directory_exemptions():
    # Exact files in 4cebb23..1aea3c8; no Git-history dependency on shallow CI.
    paths = {
        'DECISIONS.md', 'HANDOVER.md', provenance.REPORT, 'firmware/README.md',
        'firmware/sesame-s3/manifest_generated.h', provenance.MANIFEST,
        'reference/BODY-PROVENANCE.md', 'reference/SESAME-S3-BUILD-STATE.md',
        'reference/SESAME-S3-CALIBRATION.md', 'reference/SESAME-S3-CLOCK.md',
        'reference/SESAME-S3-OE.md', 'reference/evidence/2026-10-25-s3-oe-software.json',
        'reference/sesame-s3-interface.json', 'tests/firmware/test_s3_native.cpp',
        'tests/test_body_provenance.py', 'tests/test_s3_clock.py',
        'tools/generate_s3_firmware.py', 'tools/revalidate_body_provenance.py',
    }
    assert provenance.provenance_only(paths)
    for extra in ('assets/body/params.json', 'sim/manifest.py', 'new-file.md',
                  'firmware/sesame-s3/new-helper.h', 'reference/evidence/new.json'):
        assert not provenance.provenance_only(paths | {extra})


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
    names = [s.get('name', s.get('uses')) for s in job['steps']]
    assert names.index('astral-sh/setup-uv@v5') < names.index('Classify provenance-only repair')
    assert '--with pyyaml==6.0.3' in steps['Classify provenance-only repair']['run']
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
