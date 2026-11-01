import copy
import json
from pathlib import Path
import threading
from tools.cad_workbench import Workbench,key_for
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]


def test_head_edit_leaves_frame_and_spacer_keys_unchanged():
    params=json.loads((ROOT/'assets/printing/internal-frame-s3/params.json').read_text());changed=copy.deepcopy(params)
    changed['head_cover']['cable_notch_width_mm']+=1
    assert key_for('head',params,{})!=key_for('head',changed,{})
    assert all(key_for(k,params,{})==key_for(k,changed,{}) for k in ['frame','spacer'])
    assert key_for('frame',params,{'code':'v1'})!=key_for('frame',params,{'code':'v2'})


def test_watcher_debounces_bursts_and_recovers_invalid_json(tmp_path):
    params=tmp_path/'params.json';params.write_text('{}')
    wb=Workbench(tmp_path/'out',params,[],{},('head',));calls=[];called=threading.Event();errored=threading.Event()
    original_status=wb.status
    def status(**changes):
        original_status(**changes)
        if changes.get('state')=='error':errored.set()
    wb.status=status
    wb.inputs.files=[]
    def rebuild():
        value=json.loads(params.read_text());calls.append(value);called.set()
    wb.rebuild=rebuild
    thread=threading.Thread(target=lambda:wb.watch(.2));thread.start()
    try:
        assert called.wait(3);called.clear()
        for value in [1,2,3]:params.write_text(json.dumps({'value':value}))
        assert called.wait(3);assert calls==[{}, {'value':3}];called.clear()
        params.write_text('{');assert errored.wait(5)
        assert wb.state['state']=='error'
        params.write_text('{"value":4}');assert called.wait(3);assert calls[-1]=={'value':4}
    finally:wb.stop.set();thread.join(3)


def test_save_during_build_does_not_publish_stale_geometry_or_input_cache(tmp_path):
    params=tmp_path/'params.json';params.write_text('{}')
    wb=Workbench(tmp_path/'out',params,['python'],{},('head',))
    stage=wb.out/'.work/head';stage.mkdir(parents=True)
    (stage/'preview-inputs.json').write_text('{"stale":true}')
    wb.inputs.snapshot=lambda:({}, {'head':'new-key'})
    with patch('tools.cad_workbench.subprocess.run',return_value=SimpleNamespace(returncode=0)):
        assert not wb.build('head',{},'old-key')
    assert not wb.state['parts']
    assert not (stage/'preview-inputs.json').exists()
