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

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--params',type=Path,default=ROOT/'assets/printing/internal-frame-s3/params.json')
    parser.add_argument('--output',type=Path,default=ROOT/'tests/artifacts/head-preview')
    parser.add_argument('--show',action='store_true',help='Print a live cadgen viewer URL after building')
    args=parser.parse_args();params=args.params.resolve();out=args.output.resolve()
    mac=Path('/Applications/FreeCAD.app/Contents/Resources/bin/python')
    executable=os.environ.get('FREECAD_PYTHON')
    if not executable:
        executable=str(mac) if mac.exists() else sys.executable if importlib.util.find_spec('FreeCAD') else None
    if not executable:parser.error('Set FREECAD_PYTHON to the Python in your FreeCAD environment')
    env=os.environ.copy();env['QT_QPA_PLATFORM']='offscreen'
    lib=os.environ.get('FREECAD_LIB') or (str(mac.parent.parent/'lib') if executable==str(mac) else '')
    if lib:env['PYTHONPATH']=lib+os.pathsep+env.get('PYTHONPATH','')
    started=time.perf_counter()
    subprocess.run([executable,'-u','-m','tools.internal_frame_cad','--preview-head','--params',str(params),'--output',str(out)],cwd=ROOT,env=env,check=True)
    print(f'Preview command wall time: {time.perf_counter()-started:.2f}s',flush=True)
    if args.show:
        cadgen=shutil.which('cadgen') or str(Path.home()/'.local/bin/cadgen')
        subprocess.run([cadgen,'+0.8.4','viewer','--json',str(out/'head-preview.step')],check=True)


if __name__=='__main__':main()
