"""Shared location and opening rules for the authoritative electronics CAD."""
from pathlib import Path
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
CAD = ROOT / 'assets/cad'
ASSEMBLY = CAD / 'Sesame-S3-Assembly.FCStd'


def open_assembly():
    if tuple(int(v) for v in App.Version()[:2]) < (1, 1):
        raise RuntimeError('Open the assembly with FreeCAD 1.1.3 or newer; older versions lose native appearances.')
    if not ASSEMBLY.exists():
        raise FileNotFoundError(f'{ASSEMBLY}\nRetrieve the assembly with git lfs pull; do not generate a carrier-only replacement.')
    with ASSEMBLY.open('rb') as stream:
        if stream.read(80).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise RuntimeError('The assembly is an LFS pointer. Run git lfs pull first.')
    doc = next((d for d in App.listDocuments().values() if Path(d.FileName) == ASSEMBLY), None)
    if doc is None:
        doc = App.openDocument(str(ASSEMBLY))
    App.setActiveDocument(doc.Name)
    return doc
