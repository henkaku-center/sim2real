#!/usr/bin/env python3
"""Read-only advisory review of changed Markdown rules. Never rewrites or gates work."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
IMPERATIVE=re.compile(r'\b(must|mandatory|prerequisite)\b|^\s*(?:[-*]\s*)?(always|never|do not|only)\b|^\s*Before\b.+\b(ask|require|complete)\b',re.I)


def assess(text, context='', assignments=None):
    flags=[]
    if IMPERATIVE.search(text):
        if not re.search(r'(requested|confirmed|instructor intent|user instruction)',context,re.I):
            flags.append('request-origin-not-visible-in-nearby-text')
        if re.search(r'85\s*[–-]\s*95|5\s*(?:°|degree)|small.*(?:motion|step)|slow.*(?:motion|movement)|wiring.record|instructor.approval',text,re.I) or (re.search(r'^Before.+ask.+student',text,re.I) and re.search(r'wiring checks|evidence',context,re.I)):
            flags.append('possible-reference-workflow-promoted-to-restriction')
    if re.search(r'(?:goal|aim).*two tricks',text,re.I):
        flags.append('possible-reference-deliverable-as-project-ceiling')
    for role,pin in (assignments or {}).items():
        match=re.search(r'\b'+re.escape(role)+r'\s*[=:]\s*GPIO\s*(\d+)\b',text,re.I)
        if match and 's3.GPIO'+match[1]!=pin:
            flags.append(f'documented-{role}-assignment-differs-from-current-firmware:{pin}')
    return flags


def scan(repo=ROOT,since='HEAD~1',until=None):
    repo=Path(repo)
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True,stderr=subprocess.PIPE)
    range_args=[since]+([until] if until else [])
    try:
        revision=git('rev-parse',until or 'HEAD').strip()
        names=git('diff','--name-only','--diff-filter=AM','-z',*range_args,'--','*.md').split('\0')
    except subprocess.CalledProcessError:
        return {'advisory':True,'available':False,'findings':[],
                'reason':'Requested Git history unavailable; no alignment conclusion. Supply --since/--until from available history.'}
    assignments={};source_scope='not available for this repository'
    if repo.resolve()==ROOT.resolve():
        import circuit
        graph=circuit.build(repo)
        assignments={f['role']:f['pin'] for f in graph['firmware']}
        source_scope=graph['fingerprint']
    findings=[]
    for name in filter(None,names):
        content=git('show',f'{until}:{name}') if until else (repo/name).read_text()
        lines=content.splitlines();line=0
        for diff in git('diff','--no-ext-diff','--unified=0',*range_args,'--',name).splitlines():
            hunk=re.match(r'@@ .* \+(\d+)(?:,\d+)? @@',diff)
            if hunk:line=int(hunk[1]);continue
            if diff.startswith('+++') or diff.startswith('---'):continue
            if diff.startswith('+'):
                text=diff[1:];context='\n'.join(lines[max(0,line-5):line+4])
                flags=assess(text,context,assignments)
                if flags:
                    origin={'commit':None,'author':None,'date':None,'state':'uncommitted-or-unavailable'}
                    try:
                        blame=git('blame','--line-porcelain','-L',f'{line},{line}',*([until] if until else []),'--',name).splitlines()
                        sha=blame[0].split()[0]
                        if set(sha)!={'0'}:
                            author=next(x[7:] for x in blame if x.startswith('author '))
                            timestamp=int(next(x[12:] for x in blame if x.startswith('author-time ')))
                            origin={'commit':sha,'author':author,'date':datetime.fromtimestamp(timestamp,timezone.utc).isoformat(),'state':'committed'}
                    except (subprocess.CalledProcessError,StopIteration,ValueError):pass
                    findings.append({'path':name,'line':line,'text':text,'flags':flags,'origin':origin})
                line+=1
            elif diff.startswith(' '):line+=1
    return {'advisory':True,'repository':str(repo),'revision':revision,'since':since,'until':until,
            'current_firmware_evidence':source_scope,'findings':findings,
            'limits':'Heuristic leads for review, not semantic proof or an approval gate. No request link found does not mean a rule was unauthorized. Historical diffs are not current instructions. Nothing is rewritten.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=ROOT);p.add_argument('--since',default='HEAD~1');p.add_argument('--until')
    a=p.parse_args();print(json.dumps(scan(a.repo,a.since,a.until),ensure_ascii=False,indent=2))
