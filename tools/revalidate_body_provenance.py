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
METHOD = 'executed-manifest-exact-v4'
# Baseline: the second validator rerun of 2026-11-12 (commit below), executed
# with the manifest as committed there: course hip limits, S3 board name, three
# readable calibration identities, typed joint directions and the course body
# in hardware_revision (DECISIONS.md D24). No difference from that manifest is
# excepted. The list is empty, so any later manifest edit, firmware
# metadata included, is an effective input change until it is audited and
# listed here as an exact delta under hardware_profiles.sesame_s3: `add` with
# its value, or `replace` with the original and the new value. Typed canonical
# JSON comparisons reject bool/int/float substitutions and additional fields.
# The five firmware-only deltas excepted against the October baseline (b38d4b3,
# method v3) are part of the executed manifest now.
ALLOWED_MANIFEST_CHANGES = []
AUDITED_REPORT_COMMIT = '828862d1442db375b68e6594a39d6773eac281d4'
AUDITED_REPORT_SHA256 = '6140419622fce237df203555dd1bc2daf00d22e77e857a43dd419310358e60b7'
AUDITED_PRESERVED_SHA256 = 'f7b11526aaa98c2831f6328bbc32213f6d1dcfb526edb703d64af9b205495591'
# The consumers that executed at the baseline, byte for byte; unchanged since
# b38d4b3. make_job consumes joints and neutral through sim/manifest.py.
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
# Exact non-geometry companions audited in 4cebb23..1aea3c8 for the course OE
# correction. No directory/glob exemption: new firmware, geometry, consumer or
# asset paths require review. Main CI still tests/builds the firmware changes.
FIRMWARE_COMPANION_PATHS = {
    MANIFEST, 'DECISIONS.md', 'HANDOVER.md', 'firmware/README.md',
    'firmware/sesame-s3/manifest_generated.h',
    'reference/SESAME-S3-BUILD-STATE.md', 'reference/SESAME-S3-CALIBRATION.md',
    'reference/SESAME-S3-CLOCK.md', 'reference/SESAME-S3-OE.md',
    'reference/sesame-s3-interface.json',
    'reference/evidence/2026-10-25-s3-oe-software.json',
    'tests/firmware/test_s3_native.cpp', 'tests/test_s3_clock.py',
    'tools/generate_s3_firmware.py',
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


def classify_body_scope(paths, root=ROOT):
    paths = set(paths)
    if REPORT not in paths:
        return False, 'no-provenance-report-change'
    if not paths <= PROVENANCE_PATHS | FIRMWARE_COMPANION_PATHS:
        return False, 'unknown-or-geometry-path'
    try:
        # A path list is only a candidate. Verify the checked-out report and
        # exact manifest equivalence, original execution reconstruction, pinned
        # consumer/source/export hashes and holds before skipping geometry work.
        verify(root)
    except Exception as error:
        # Missing dependencies/LFS inputs, malformed or stale proof, changed
        # consumers/assets and unknown failures all retain the full CAD route.
        return False, 'proof-not-established-' + type(error).__name__
    return True, 'verified-unchanged-body-inputs-with-audited-companions'


def provenance_only(paths, root=ROOT):
    return classify_body_scope(paths, root)[0]


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
            scoped, reason = classify_body_scope(filter(None, paths))
        except (subprocess.CalledProcessError, TypeError, ValueError):
            scoped = False  # Missing/unknown comparison retains full CAD coverage.
            reason = 'missing-or-invalid-comparison'
        import sys
        print('body scope: ' + reason, file=sys.stderr)
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
