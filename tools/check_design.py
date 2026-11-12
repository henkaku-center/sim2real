#!/usr/bin/env python3
"""One read-only check for coupled design consumers; JSON evidence, no completion fiction."""
import json
from pathlib import Path
import subprocess
import sys
import circuit
import joints
import leg_clearance
import real2sim_status
import rule_drift

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sim import twin, twin_evidence
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
    # A committed dynamics record, generated MJCF or variant evidence that no
    # longer follows from its inputs is a failure, not a warning.
    for name,stale in [('dynamics-twin-records',twin.check_all),('dynamics-variant-evidence',twin_evidence.check_all)]:
        try:
            problems=stale()
            checks.append({'name':name,'ok':not problems,**({'error':'; '.join(problems)} if problems else {'result':'current'})})
        except (ValueError,OSError,KeyError) as error:
            checks.append({'name':name,'ok':False,'error':str(error)})
    suites=[('firmware-and-circuit', [sys.executable,'-m','pytest','-q','tests/test_s3_firmware.py','tests/test_s3_clock.py','tests/test_course_circuit.py','tests/test_rule_drift.py']),
            ('two-eye-artifact-constraints',[sys.executable,'-m','pytest','-q','tests/test_two_eye_variant.py']),
            ('dynamics-twin-numbers',[sys.executable,'-m','pytest','-q','tests/test_twin.py']),
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
    # tools/joints.py answers only from current data; an assistant asks it before commanding a joint.
    try:
        interface,course=joints.load(ROOT)
        checks.append({'name':'joint-query-data','ok':True,'result':{'ask':'python3 tools/joints.py query NAME | check NAME DEG ...',
                       'manifest_id':interface['manifest_id'],'contact_design':course['design']}})
    except joints.CannotAnswer as error:
        checks.append({'name':'joint-query-data','ok':False,'error':str(error)})
    variant_path='assets/printing/internal-frame-s3-two-eyes/assembly.json'
    variant=json.loads((ROOT/variant_path).read_text())
    geometry=next(c['ok'] for c in checks if c['name']=='two-eye-artifact-constraints')
    dynamics=all(c['ok'] for c in checks if c['name'].startswith('dynamics-'))
    evidence_path=twin_evidence.evidence_path('internal-frame-s3-two-eyes')
    simulated=json.loads(evidence_path.read_text()) if evidence_path.exists() else None
    trace=[
        {'stage':'CAD mutation and printable exports','state':'working' if geometry else 'unverified',
         'evidence':variant_path,'scope':'Current source/artifact hashes, recorded solids, dimensions and clearances; not a new native CAD regeneration or physical fit test.'},
        {'stage':'Second-display electronics','state':'planned','evidence':variant['variant']['electronics'],
         'scope':'Variant design intent. No claim that the extra header, device address or second-display firmware was implemented or physically checked.'},
        {'stage':'Cable and leg clearances','state':'partial',
         'cables':{'state':'unverified','evidence':variant['head_fit']['cable_checks']},
         'legs':{'state':'cad-derived' if legs['ok'] else 'stale','designs':legs['designs'],
                 'scope':leg_clearance.SCOPE+' Stale evidence fails this check; rerun tools/leg_clearance.py <design> --write.'}},
        {'stage':'Mutated dynamics and mass/stability','state':twin_evidence.STATUS if dynamics and simulated else 'stale',
         'evidence':str(evidence_path.relative_to(ROOT)),
         'simulated':None if simulated is None else {'summary':twin_evidence.summary(simulated),'mass':simulated['mass']['change'],
             'standing_margin_mm':{k:simulated['standing'][k]['margin_mm'] for k in (simulated['base'],simulated['variant'])},
             'standing_margin_under_mass_uncertainty_mm':{k:simulated['mass_uncertainty'][k]['margin_mm'] for k in (simulated['base'],simulated['variant'])}},
         'scope':twin_evidence.SCOPE+' A stale state means the committed records no longer follow from their inputs.'},
        real2sim_status.stage(ROOT),
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
