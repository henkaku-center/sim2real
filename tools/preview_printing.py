"""Build a fast head preview; optionally show it in the installed cadgen viewer.

Run: python tools/preview_printing.py --show
The viewer follows subsequent rebuilds of the same STEP file.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--params',type=Path,default=ROOT/'assets/printing/internal-frame-s3/params.json')
    parser.add_argument('--output',type=Path,default=ROOT/'tests/artifacts/head-preview')
    parser.add_argument('--show',action='store_true',help='Print a live cadgen viewer URL after building')
    parser.add_argument('--part',choices=['head','frame','spacer','all'],default='head')
    parser.add_argument('--watch',action='store_true',help='Debounce saves and rebuild changed parts')
    parser.add_argument('--serve',type=int,metavar='PORT',help='Serve a before/after workbench on a local port; implies --watch')
    args=parser.parse_args();params=args.params.resolve();out=args.output.resolve()
    mac=Path('/Applications/FreeCAD.app/Contents/Resources/bin/python')
    executable=os.environ.get('FREECAD_PYTHON')
    if not executable:
        executable=str(mac) if mac.exists() else sys.executable if importlib.util.find_spec('FreeCAD') else None
    if not executable:parser.error('Set FREECAD_PYTHON to the Python in your FreeCAD environment')
    env=os.environ.copy();env['QT_QPA_PLATFORM']='offscreen'
    lib=os.environ.get('FREECAD_LIB') or (str(mac.parent.parent/'lib') if executable==str(mac) else '')
    if lib:env['PYTHONPATH']=lib+os.pathsep+env.get('PYTHONPATH','')
    command=[executable,'-u','-m','tools.internal_frame_cad']
    if args.watch or args.serve:
        from tools.cad_workbench import Workbench,server_for,KINDS
        workbench=Workbench(out,params,command,env,KINDS if args.part=='all' else (args.part,))
        server=server_for(workbench,args.serve) if args.serve else None
        if server:threading.Thread(target=server.serve_forever,daemon=True).start()
        print(f'Watching {params}; comparison server port: {args.serve or "off"}',flush=True)
        try:workbench.watch()
        except KeyboardInterrupt:workbench.stop.set()
        finally:
            if server:server.shutdown();server.server_close()
        return
    started=time.perf_counter()
    for kind in (('head','frame','spacer') if args.part=='all' else (args.part,)):
        subprocess.run([*command,'--preview',kind,'--params',str(params),'--output',str(out/kind if args.part=='all' else out)],cwd=ROOT,env=env,check=True)
    print(f'Preview command wall time: {time.perf_counter()-started:.2f}s',flush=True)
    if args.show:
        cadgen=shutil.which('cadgen') or str(Path.home()/'.local/bin/cadgen')
        files=[out/k/(k+'-preview.step') for k in ('head','frame','spacer')] if args.part=='all' else [out/(args.part+'-preview.step')]
        subprocess.run([cadgen,'+0.8.4','viewer','--json',*[str(p) for p in files]],check=True)


if __name__=='__main__':main()
