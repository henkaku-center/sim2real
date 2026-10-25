#!/usr/bin/env python3
"""Audited metadata refresh for exact unused firmware-field deltas; no CAD runs.

Original execution inputs/results remain reconstructible and hash-verified.
Default invocation verifies; --write requires an explicit original git revision.
The exception is valid only for the audited consumers below, not future code.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]
REPORT = 'assets/body/v1/report.json'
MANIFEST = 'manifest/robot.yaml'
PROOF = 'input_revalidation'
METHOD = 'unused-s3-firmware-metadata-v3'
# Exact reviewed deltas from the original execution manifest, not a blanket
# exclusion of hardware_profiles. Typed canonical JSON comparisons also reject
# bool/int/float substitutions, additional fields and broader compatibility IDs.
ALLOWED_MANIFEST_CHANGES = [
    {'operation': 'add', 'path': ['hardware_profiles', 'sesame_s3', 'pulse_profile'],
     'value': {'id': 'tim-pca9685-150-512-v1', 'reference_oscillator_hz': 25000000,
               'reference_prescale': 121, 'reference_ticks': [150, 512],
               'interpolation': 'floor-reference-ticks'}},
    {'operation': 'add', 'path': ['hardware_profiles', 'sesame_s3', 'clock_measure_gpio'],
     'value': 4},
    {'operation': 'add', 'path': ['hardware_profiles', 'sesame_s3', 'calibration_compatible_manifest_ids'],
     'value': ['e669b916d178ac0a', 'bd7675604b98ae46']},
    {'operation': 'replace', 'path': ['hardware_profiles', 'sesame_s3', 'intended_channels_status'],
     'original_value': 'unverified-do-not-use-as-default',
     'value': 'recommended-default-not-physically-verified'},
    {'operation': 'replace', 'path': ['hardware_profiles', 'sesame_s3', 'oe'],
     'original_value': 18, 'value': 7},
]
AUDITED_REPORT_COMMIT = 'b38d4b3d249f9c09171277f01ba4b387f7660578'
AUDITED_REPORT_SHA256 = 'b5b4e730806144de953699aa48299bf74d62928f0a6f22dc67c2ea7adfcd9a68'
AUDITED_PRESERVED_SHA256 = '4a1707a9e731533c736e70fec4f5e62ca43a73772af565ac5ff30401f0c9fc47'
# Audited at b38d4b3 and rechecked at 4cebb23: make_job consumes joints/neutral;
# these unchanged consumers do not use the five firmware-only fields above.
AUDITED_CONSUMERS = {
    'sim/build_mjcf.py': 'c3d5cb2a6519dd7e0111e48fd98a7856eab099677435a23b2e226377aea98343',
    'sim/prepare_assets.py': '459d6b558e8a89355cf235b029b51ae8bd64f9b8c79fc3b79588c4d98fc446ac',
    'tools/body_cad.py': 'c0b5869f482100bd324b01ee9ba3d03ae707044d83335dcb4dc736565b13bab1',
    'tools/body_checks.py': '5d6e575fea7a0af2eccd11d9b0e7c59aa8254479f5fbc612578e0aca89cb0b1b',
    'tools/body_motion.py': '714687c1122a3fa8bda4d43869404a905ae0f113322619da8565683e4389524d',
    'tools/check_body.py': 'eb5aa68103cc4037c14353892fce2052fa4f9d1a42fd75e96b8ff2f90d1ed482',
    'tools/render_body.py': '6e6f839edb21e8e3089d28411cc17ceb97fd0ef684d5aa2f175f68048fc68834',
    'sim/manifest.py': 'a747eb1e2fac3939e616cf07c5d4a4dd5ee6d826efbe12418a3dc2421d5b2f42',
}
PROVENANCE_PATHS = {
    REPORT, 'tools/revalidate_body_provenance.py', 'tests/test_body_provenance.py',
    'reference/BODY-PROVENANCE.md', '.github/workflows/body-cad.yml',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def local(root, name):
    path = Path(name)
    require(not path.is_absolute() and '..' not in path.parts, 'unsafe input path')
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root.resolve()), 'input escapes repository')
    return resolved


def body_files(root):
    return sorted(str(p.relative_to(root)) for p in (root / 'assets/body').rglob('*') if p.is_file())


def effective_identity(original, current):
    import yaml  # Classification needs only stdlib; verification uses pinned PyYAML.
    old, new = yaml.safe_load(original), yaml.safe_load(current)
    old_hw = old['hardware_profiles']['sesame_s3']
    new_hw = new['hardware_profiles']['sesame_s3']
    for change in ALLOWED_MANIFEST_CHANGES:
        key = change['path'][-1]
        require(key in new_hw and encoded(new_hw[key]) == encoded(change['value']),
                f'effective inputs changed: unaudited firmware metadata value: {key}')
        if change['operation'] == 'add':
            require(key not in old_hw, f'not an addition to the audited baseline: {key}')
            del new_hw[key]
        else:
            require(key in old_hw and encoded(old_hw[key]) == encoded(change['original_value']),
                    f'unaudited original metadata value: {key}')
            new_hw[key] = copy.deepcopy(old_hw[key])
    require(encoded(old) == encoded(new), 'effective inputs changed outside the exact allowed firmware deltas')
    return sha(encoded(old))


def source_paths(report):
    paths = {}
    aliases = {'assembly': 'assets/cad/Sesame-S3-Assembly.FCStd',
               'snapshot': 'assets/cad/instructions/assembly-cad-snapshot.json'}
    for name, digest in report['source_hashes'].items():
        if name in aliases:
            path = aliases[name]
        else:
            require(Path(name).name == name and name.endswith('.stl'), 'unknown geometry source')
            path = 'assets/stl/upstream/' + name
        paths[path] = digest
    return paths


def verify(root, report=None):
    report = json.loads(local(root, REPORT).read_bytes()) if report is None else report
    require(report['status'] == 'FAIL-DRAFT' and report['release_ready'] is False
            and report['geometry_pass'] is False, 'held acceptance flags changed')
    proof = report.get(PROOF)
    require(isinstance(proof, dict) and proof.get('method') == METHOD, 'missing/unknown revalidation')
    require(proof['original_commit'] == AUDITED_REPORT_COMMIT and
            proof['original_report_sha256'] == AUDITED_REPORT_SHA256, 'unaudited original report')
    require(proof['validator_executed'] is False and
            encoded(proof.get('allowed_manifest_changes')) == encoded(ALLOWED_MANIFEST_CHANGES),
            'invalid revalidation claim')
    require(proof['verifier_sha256'] == sha(Path(__file__).read_bytes()), 'revalidation tool changed')
    require(sha(encoded(proof['preserved_sha256'])) == AUDITED_PRESERVED_SHA256,
            'original preserved-file identities changed')
    original = copy.deepcopy(report)
    original.pop(PROOF)
    original['input_hashes'] = proof['original_input_hashes']
    require(sha(encoded(original)) == proof['original_report_sha256'], 'original execution/results changed')
    old_yaml = proof['original_manifest_yaml'].encode()
    require(sha(old_yaml) == original['input_hashes'][MANIFEST], 'original manifest proof changed')
    require(effective_identity(old_yaml, local(root, MANIFEST).read_bytes())
            == proof['effective_manifest_sha256'], 'effective identity mismatch')
    require(set(report['input_hashes']) == set(original['input_hashes']), 'input list changed')
    for path, digest in report['input_hashes'].items():
        require(sha(local(root, path).read_bytes()) == digest, f'current input changed: {path}')
        if path != MANIFEST:
            require(digest == original['input_hashes'][path], f'executed input changed: {path}')
    require(body_files(root) == proof['body_files'], 'body file inventory changed')
    frozen = json.loads(local(root, 'assets/body/frozen-inputs.json').read_bytes())
    sources = source_paths(report)
    required = ((set(proof['body_files']) | set(report['input_hashes']) | set(frozen)
                 | set(sources) | set(AUDITED_CONSUMERS)) - {REPORT, MANIFEST})
    require(set(proof['preserved_sha256']) == required, 'preserved-file coverage changed')
    for path, digest in proof['preserved_sha256'].items():
        require(sha(local(root, path).read_bytes()) == digest, f'preserved file changed: {path}')
    for expected in (AUDITED_CONSUMERS, frozen, sources):
        for path, digest in expected.items():
            require(proof['preserved_sha256'].get(path) == digest, f'unaudited source: {path}')
    # Keep the existing readers' raw hash semantics; no exception in the freshness test.
    assembly = json.loads(local(root, 'assets/body/v1/assembly.json').read_bytes())
    for name, digest in assembly['export_hashes'].items():
        require(sha(local(root, 'assets/body/v1/' + name).read_bytes()) == digest, f'export changed: {name}')
    require(report['parameters'] == json.loads(local(root, 'assets/body/params.json').read_bytes()), 'parameters changed')
    return proof


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def git_digest(root, revision, path):
    data = git(root, 'show', f'{revision}:{path}')
    if data.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
        match = re.search(rb'^oid sha256:([0-9a-f]{64})$', data, re.M)
        require(match is not None, 'invalid LFS pointer')
        return match[1].decode()
    return sha(data)


def refresh(root, baseline):
    baseline = git(root, 'rev-parse', '--verify', baseline + '^{commit}').decode().strip()
    raw = git(root, 'show', f'{baseline}:{REPORT}')
    require(baseline == AUDITED_REPORT_COMMIT and sha(raw) == AUDITED_REPORT_SHA256, 'unaudited baseline')
    original = json.loads(raw)
    require(PROOF not in original and encoded(original) == raw, 'baseline must be original canonical execution report')
    current = json.loads(local(root, REPORT).read_bytes())
    if PROOF not in current:
        require(encoded(current) == encoded(original), 'unexplained report edits before revalidation')
    else:
        restored = copy.deepcopy(current)
        restored.pop(PROOF)
        restored['input_hashes'] = original['input_hashes']
        require(encoded(restored) == encoded(original), 'execution/results changed before refresh')
    old_yaml = git(root, 'show', f'{baseline}:{MANIFEST}')
    require(sha(old_yaml) == original['input_hashes'][MANIFEST], 'baseline manifest was not executed')
    identity = effective_identity(old_yaml, local(root, MANIFEST).read_bytes())
    inventory = sorted(p.decode() for p in git(root, 'ls-tree', '-r', '-z', '--name-only', baseline, '--', 'assets/body').split(b'\0') if p)
    require(inventory == body_files(root), 'body files differ from original execution')
    frozen = json.loads(git(root, 'show', f'{baseline}:assets/body/frozen-inputs.json'))
    sources = source_paths(original)
    paths = ((set(inventory) | set(original['input_hashes']) | set(AUDITED_CONSUMERS)
              | set(frozen) | set(sources)) - {REPORT, MANIFEST})
    preserved = {path: git_digest(root, baseline, path) for path in sorted(paths)}
    result = copy.deepcopy(original)
    result['input_hashes'][MANIFEST] = sha(local(root, MANIFEST).read_bytes())
    result[PROOF] = {
        'method': METHOD, 'validator_executed': False,
        'allowed_manifest_changes': copy.deepcopy(ALLOWED_MANIFEST_CHANGES),
        'original_commit': baseline, 'original_report_sha256': sha(raw),
        'original_input_hashes': original['input_hashes'],
        'original_manifest_yaml': old_yaml.decode(), 'effective_manifest_sha256': identity,
        'preserved_sha256': preserved, 'body_files': inventory,
        'verifier_sha256': sha(Path(__file__).read_bytes()),
    }
    verify(root, result)  # Verify everything before replacing this one file.
    path = local(root, REPORT)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(encoded(result))
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return result


def provenance_only(paths):
    paths = set(paths)
    return REPORT in paths and paths <= PROVENANCE_PATHS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--baseline')
    parser.add_argument('--classify', action='store_true')
    parser.add_argument('--base-ref')
    parser.add_argument('--head-ref')
    args = parser.parse_args()
    if args.classify:
        try:
            require(all(re.fullmatch(r'[0-9a-f]{40}', value or '') for value in
                        (args.base_ref, args.head_ref)), 'scope needs full commit hashes')
            paths = git(ROOT, 'diff', '--name-only', '-z', args.base_ref, args.head_ref, '--').decode().split('\0')
            scoped = provenance_only(filter(None, paths))
        except (subprocess.CalledProcessError, TypeError, ValueError):
            scoped = False  # Missing/unknown comparison retains full CAD coverage.
        print('provenance_only=' + str(scoped).lower())
    elif args.write:
        if not args.baseline:
            parser.error('--write requires the original --baseline revision')
        refresh(ROOT, args.baseline)
        print('Revalidated metadata only; original execution preserved; FAIL-DRAFT retained')
    else:
        verify(ROOT)
        print('PASS: audited provenance, unchanged effective inputs/assets, held release flags')


if __name__ == '__main__':
    main()
