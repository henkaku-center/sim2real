"""Debounced preview builds and a read-only, phone-friendly comparison server."""
import hashlib
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parents[1]
WEB=Path(__file__).with_name('cad_workbench_web')
KINDS=('head','frame','spacer')


def atomic_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');temporary.replace(path)


def key_for(kind,params,source):
    names={'head':['head_cover','pcb_standoff_height_mm'],
           'frame':['pcb_pilot_depth_mm','pcb_pilot_floor_mm','pcb_pilot_diameter_mm','pcb_standoff_radius_mm'],
           'spacer':['pcb_standoff_radius_mm','pcb_standoff_height_mm','pcb_spacer_bore_mm']}[kind]
    value={'source':source,'params':{k:params[k] for k in [*names,'mesh_deflection_mm']}}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


class Inputs:
    def __init__(self,params):
        self.params=Path(params);self.memo={}
        self.files=[ROOT/name for name in ['tools/v3_assembly_cad.py','tools/body_cad.py','tools/internal_frame_cad.py',
            'tools/cad_validation_cache.py','assets/cad/Sesame-S3-Assembly.FCStd','assets/cad/instructions/assembly-cad-snapshot.json']]
        self.files+=list((ROOT/'assets/printing/internal-frame-s3/reference-v3').glob('*'))
        self.files+=list((ROOT/'assets/printing/internal-frame-s3/reference-ears').glob('*'))

    def fingerprint(self,path):
        stat=path.stat();stamp=(stat.st_mtime_ns,stat.st_size,stat.st_ino,stat.st_ctime_ns)
        if path not in self.memo or self.memo[path][0]!=stamp:
            self.memo[path]=(stamp,hashlib.sha256(path.read_bytes()).hexdigest())
        return self.memo[path][1]

    def signature(self):
        return tuple(self.fingerprint(p) for p in [self.params,*self.files] if p.is_file())

    def snapshot(self):
        params=json.loads(self.params.read_text())
        source={str(p.relative_to(ROOT)):self.fingerprint(p) for p in self.files if p.is_file()}
        return params,{k:key_for(k,params,source) for k in KINDS}


class Workbench:
    def __init__(self,out,params,command,env,kinds=KINDS):
        self.out=Path(out);self.inputs=Inputs(params);self.command=command;self.env=env;self.kinds=kinds
        self.lock=threading.Lock();self.stop=threading.Event();self.build_count=0;self.force_rebuild=True
        self.out.mkdir(parents=True,exist_ok=True)
        try:self.state=json.loads((self.out/'status.json').read_text())
        except (OSError,ValueError):self.state={'parts':{}}
        self.state.update(state='starting',message='Preparing previews',building=None)
        self.save()

    def save(self):
        self.state['updated_at']=time.time();atomic_json(self.out/'status.json',self.state)

    def status(self,**changes):
        with self.lock:self.state.update(changes);self.save()

    def build(self,kind,params,key):
        self.status(state='building',building=kind,message=f'Rebuilding {kind}…',error=None)
        stage=self.out/'.work'/kind;stage.mkdir(parents=True,exist_ok=True)
        atomic_json(stage/'params.json',params)
        started=time.perf_counter();self.build_count+=1
        result=subprocess.run([*self.command,'--preview',kind,'--params',str(stage/'params.json'),'--output',str(stage)],
                              cwd=ROOT,env=self.env,capture_output=True,text=True)
        elapsed=time.perf_counter()-started
        if result.returncode:
            self.status(state='error',building=None,message=f'{kind.capitalize()} build failed — showing last successful geometry',
                        error=(result.stderr or result.stdout)[-4000:],seconds=elapsed)
            return False
        # A save during a build supersedes that build. Never publish it as current.
        try:_,latest=self.inputs.snapshot()
        except (OSError,ValueError,KeyError):
            (stage/'preview-inputs.json').unlink(missing_ok=True)
            return False
        if latest[kind]!=key:
            # Source may have changed after the child imported its code. Its
            # input-cache receipt must not survive a superseded build either.
            (stage/'preview-inputs.json').unlink(missing_ok=True)
            return False
        receipt=json.loads((stage/'preview.json').read_text())
        relative=Path('builds')/str(time.time_ns())/kind;destination=self.out/relative
        destination.mkdir(parents=True)
        for path in stage.iterdir():
            if path.suffix in ('.step','.stl') or path.name=='preview.json':shutil.copy2(path,destination/path.name)
        current={'mesh':str(relative/(kind+'-preview.stl')),'step':str(relative/(kind+'-preview.step')),
                 'receipt':str(relative/'preview.json'),'built_at':time.time(),'seconds':elapsed,'input_key':key,
                 'parameters':params,'bounds_mm':receipt['parts'][kind+'-preview']['bounds_mm'],
                 'mesh_sha256':receipt['parts'][kind+'-preview']['stl_sha256']}
        with self.lock:
            old=self.state['parts'].get(kind,{})
            previous=old.get('previous') if old.get('current',{}).get('mesh_sha256')==current['mesh_sha256'] else old.get('current')
            self.state['parts'][kind]={'current':current,'previous':previous}
            self.state.update(state='ready',building=None,message=f'{kind.capitalize()} ready in {elapsed:.2f}s',error=None,seconds=elapsed)
            self.save()
        print(f'{kind}: published in {elapsed:.2f}s',flush=True)
        return True

    def rebuild(self):
        params,keys=self.inputs.snapshot()
        for kind in self.kinds:
            current=self.state['parts'].get(kind,{}).get('current',{})
            if self.force_rebuild or current.get('input_key')!=keys[kind] or not (self.out/current.get('mesh','missing')).is_file():
                if not self.build(kind,params,keys[kind]):return
        self.force_rebuild=False
        self.status(state='ready',building=None,message='Watching for edits',error=None)

    def watch(self,debounce=.6):
        observed=None;settled=None;changed_at=time.monotonic()
        while not self.stop.is_set():
            try:
                signature=self.inputs.signature()
                if signature!=observed:observed=signature;changed_at=time.monotonic()
                if signature!=settled and time.monotonic()-changed_at>=debounce:
                    settled=signature;self.rebuild()
            except Exception as exc:
                self.status(state='error',building=None,message='Build failed — showing last successful geometry',error=str(exc))
            self.stop.wait(.15)


def server_for(workbench,port):
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            name=unquote(urlsplit(self.path).path).lstrip('/') or 'index.html'
            if name=='status.json':
                with workbench.lock:data=json.dumps(workbench.state).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(data)));self.end_headers()
                if self.command!='HEAD':self.wfile.write(data)
                return
            root=workbench.out if name.startswith('builds/') else WEB
            path=(root/name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():self.send_error(404);return
            data=path.read_bytes();self.send_response(200)
            self.send_header('Content-Type',self.guess_type(str(path)))
            self.send_header('Cache-Control','no-store' if root==WEB else 'public, max-age=31536000, immutable')
            self.send_header('Content-Length',str(len(data)));self.end_headers()
            if self.command!='HEAD':self.wfile.write(data)
        do_HEAD=do_GET
        def log_message(self,*args):pass
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)
