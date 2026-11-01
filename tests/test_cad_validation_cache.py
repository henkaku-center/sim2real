"""Cache invalidation and failure semantics independent of the native CAD runtime."""
import json
from tools.cad_validation_cache import CheckCache


def test_successful_groups_only_reuse_matching_inputs_and_checker(tmp_path):
    calls=[]
    def check():calls.append(1);return {'clearance':.8}
    cache=CheckCache(tmp_path,{'checker':'v1','kernel':'7.9'})
    assert cache.run('frame',{'brep':'frame-a','tolerance':1e-5},check)=={'clearance':.8}
    cache.run('frame',{'brep':'frame-a','tolerance':1e-5},check)
    assert len(calls)==1 and cache.records[-1]['cache_hit']
    cache.run('frame',{'brep':'frame-b','tolerance':1e-5},check)
    cache.run('frame',{'brep':'frame-b','tolerance':1e-4},check)
    CheckCache(tmp_path,{'checker':'v2','kernel':'7.9'}).run('frame',{'brep':'frame-a','tolerance':1e-5},check)
    assert len(calls)==4
    CheckCache(tmp_path,{'checker':'v1','kernel':'7.9'},fresh=True).run('frame',{'brep':'frame-a','tolerance':1e-5},check)
    assert len(calls)==5


def test_failure_is_never_cached_and_corrupt_result_is_rechecked(tmp_path):
    cache=CheckCache(tmp_path,{})
    def fail():raise AssertionError('collision')
    import pytest
    with pytest.raises(AssertionError):cache.run('head',{},fail)
    assert not list(tmp_path.iterdir())
    cache.run('head',{},lambda:[])
    file=next(tmp_path.iterdir());saved=json.loads(file.read_text());saved['result']=['corrupt'];file.write_text(json.dumps(saved))
    assert cache.run('head',{},lambda:['rechecked'])==['rechecked']
    assert not cache.records[-1]['cache_hit']
