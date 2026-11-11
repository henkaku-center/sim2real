#!/usr/bin/env python3
"""One read-only check for coupled design consumers; JSON evidence, no completion fiction."""
import json
from pathlib import Path
import subprocess
import sys
import circuit
import leg_clearance
import rule_drift

ROOT=Path(__file__).resolve().parents[1]
LEG_DESIGNS=('internal-frame-s3','internal-frame-s3-two-eyes')


def leg_clearance_report(root=ROOT):
    """Committed leg-clearance evidence per design: hash freshness, digest and manifest comparison."""
    robot,motions=leg_clearance.load_manifests(root)
    designs={}
    for name in LEG_DESIGNS:
        directory=Path(root)/leg_clearance.PRINTING/name
        status=leg_clearance.verify(directory,root)
        entry={'evidence':f'{leg_clearance.PRINTING}/{name}/{leg_clearance.EVIDENCE}','state':'cad-derived' if status['fresh'] else 'stale','stale':status['stale']}
        if status['fresh']:
            evidence=json.loads((directory/leg_clearance.EVIDENCE).read_text())
            entry.update(leg_clearance.summary(evidence),manifest=leg_clearance.compare(evidence,robot,motions))
        designs[name]=entry
    return {'ok':all(d['state']=='cad-derived' for d in designs.values()),'designs':designs}


def main():
    checks=[]
    try:
        checks.append({'name':'live-routing-cad-export','ok':True,'result':circuit.check(ROOT)})
    except (ValueError,OSError,KeyError) as error:
        checks.append({'name':'live-routing-cad-export','ok':False,'error':str(error)})
    suites=[('firmware-and-circuit', [sys.executable,'-m','pytest','-q','tests/test_s3_firmware.py','tests/test_s3_clock.py','tests/test_course_circuit.py','tests/test_rule_drift.py']),
            ('two-eye-artifact-constraints',[sys.executable,'-m','pytest','-q','tests/test_two_eye_variant.py']),
            ('graph-to-scene-adapter',['node','--test','tests/circuit-view.test.mjs'])]
    for name,command in suites:
        try:
            result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=120)
            checks.append({'name':name,'ok':result.returncode==0,'output':result.stdout+result.stderr})
        except (OSError,subprocess.TimeoutExpired) as error:
            checks.append({'name':name,'ok':False,'error':str(error)})
    try:
        legs=leg_clearance_report()
    except (ValueError,OSError,KeyError) as error:
        legs={'ok':False,'designs':{},'error':str(error)}
    checks.append({'name':'leg-clearance-evidence','ok':legs['ok'],
                   'result':{name:{'state':d['state'],'stale':d['stale']} for name,d in legs['designs'].items()},
                   **({'error':legs['error']} if 'error' in legs else {})})
    variant_path='assets/printing/internal-frame-s3-two-eyes/assembly.json'
    variant=json.loads((ROOT/variant_path).read_text())
    geometry=next(c['ok'] for c in checks if c['name']=='two-eye-artifact-constraints')
    trace=[
        {'stage':'CAD mutation and printable exports','state':'working' if geometry else 'unverified',
         'evidence':variant_path,'scope':'Current source/artifact hashes, recorded solids, dimensions and clearances; not a new native CAD regeneration or physical fit test.'},
        {'stage':'Second-display electronics','state':'planned','evidence':variant['variant']['electronics'],
         'scope':'Variant design intent. No claim that the extra header, device address or second-display firmware was implemented or physically checked.'},
        {'stage':'Cable and leg clearances','state':'partial',
         'cables':{'state':'unverified','evidence':variant['head_fit']['cable_checks']},
         'legs':{'state':'cad-derived' if legs['ok'] else 'stale','designs':legs['designs'],
                 'scope':leg_clearance.SCOPE+' Stale evidence fails this check; rerun tools/leg_clearance.py <design> --write.'}},
        {'stage':'Mutated dynamics and mass/stability validation','state':'unverified',
         'scope':'This check does not establish a dynamics model and acceptance run for the changed robot. Geometry/rendering is not such evidence.'},
        {'stage':'Human review and iteration','state':'manual','scope':'Part of the intended workflow, not an asserted completed acceptance.'},
        {'stage':'Fabricated and assembled variant','state':'unverified','scope':'Exported printable files do not establish printing, ordering, assembly or physical performance.'},
    ]
    ok=all(c['ok'] for c in checks)
    print(json.dumps({'ok':ok,'checks':checks,'mutation_example':'two-eyes','trace':trace,
                      'rule_drift':rule_drift.scan(),
                      'end_to_end_coverage':'Not established by these checks',
                      'scope':'Dependency checks and current evidence limits; not a manufacturing or student-approval gate.'},indent=2))
    return 0 if ok else 1


if __name__=='__main__':sys.exit(main())
