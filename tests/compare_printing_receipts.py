"""Require a cached build to reproduce a fresh build's complete numerical receipt."""
import json
from pathlib import Path
import sys


def compare(fresh,cached):
    a=json.loads((Path(fresh)/'assembly.json').read_text());b=json.loads((Path(cached)/'assembly.json').read_text())
    first=a.pop('validation_cache');second=b.pop('validation_cache')
    assert len(first)==len(second)==9
    assert not any(r['cache_hit'] for r in first),first
    assert all(r['cache_hit'] for r in second),second
    assert a==b,[key for key in a if a[key]!=b.get(key)]
    print('Fresh/cached receipts equal; all nine groups reused')


if __name__=='__main__':compare(*sys.argv[1:])
