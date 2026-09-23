"""Import pinned STEP models with FreeCADCmd and prepare a local working document.

Run with FreeCAD's bundled interpreter, not system Python. Existing working CAD
documents are never overwritten. Reports describe imported geometry, not measured
hardware. See assets/cad/README.md for the invocation.
"""

import hashlib
import json
from pathlib import Path
import sys

import FreeCAD as App
import Import
import Mesh
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from fetch_cad import validate

CAD = ROOT / "assets" / "cad"
WORK = CAD / "work"
REPORTS = CAD / "reports"


def bounds(shape):
    box = shape.BoundBox
    return {
        "min_mm": [round(box.XMin, 6), round(box.YMin, 6), round(box.ZMin, 6)],
        "max_mm": [round(box.XMax, 6), round(box.YMax, 6), round(box.ZMax, 6)],
        "size_mm": [round(box.XLength, 6), round(box.YLength, 6), round(box.ZLength, 6)],
    }


def inspect(doc):
    objects = []
    for obj in doc.Objects:
        entry = {
            "name": obj.Name, "label": obj.Label, "type": obj.TypeId,
            "dependencies": [child.Name for child in obj.OutList],
        }
        if hasattr(obj, "Placement"):
            p = obj.getGlobalPlacement()
            entry["global_placement"] = {
                "translation_mm": list(p.Base), "quaternion_xyzw": list(p.Rotation.Q),
            }
        if obj.TypeId in ("Part::Feature", "App::Part", "App::Link") and hasattr(obj, "Shape") and not obj.Shape.isNull():
            shape = obj.Shape.copy()
            entry.update({
                "valid": shape.isValid(), "solids": len(shape.Solids),
                "faces": len(shape.Faces), "volume_mm3": round(shape.Volume, 6),
                "shape_bounds": bounds(shape),
            })
            # Shape already includes the object's own placement; remove it for
            # an object-coordinate envelope. Parent transforms are not included.
            shape.Placement = App.Placement()
            entry["object_bounds"] = bounds(shape)
        objects.append(entry)
    return {
        "object_count": len(objects),
        "shape_object_count": sum("valid" in entry for entry in objects),
        "invalid_shape_objects": [entry["name"] for entry in objects if entry.get("valid") is False],
        "objects": objects,
    }


def main():
    manifest = json.loads((CAD / "sources.json").read_text())
    steps = [entry for entry in manifest["files"] if entry["path"].endswith(".step")]
    names = {entry["path"]: ("Sesame-upstream" if entry["path"].startswith("sesame/")
             else "Adafruit-" + Path(entry["path"]).parent.name.split()[0]) for entry in steps}
    working_path = WORK / "Sesame-S3-layout-start.FCStd"
    for entry in steps:
        validate((CAD / "upstream" / entry["path"]).read_bytes(), entry)
    WORK.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    report = {
        "freecad_version": App.Version(), "occt_version": Part.OCC_VERSION,
        "units": {"length": "mm", "volume": "mm^3"},
        "scope": "Imported STEP geometry; not hardware fit verification. Containers and links may duplicate geometry; do not sum object volumes.",
        "sources": [], "existing_stl_meshes": [],
    }
    for entry in steps:
        name = names[entry["path"]]
        native_path = WORK / (name + ".FCStd")
        if native_path.exists():
            doc = App.openDocument(str(native_path))
        else:
            doc = App.newDocument(name.replace("-", "_"))
            Import.insert(str(CAD / "upstream" / entry["path"]), doc.Name)
        doc.recompute()
        result = inspect(doc)
        if not result["shape_object_count"]:
            raise ValueError(f"STEP import has no shape objects: {entry['path']}")
        result.update({"source_path": entry["path"], "revision": entry["revision"],
                       "git_blob_sha1": entry["git_blob_sha1"]})
        report["sources"].append(result)
        if not native_path.exists():
            doc.saveAs(str(native_path))
        result["native_file_sha256"] = hashlib.sha256(native_path.read_bytes()).hexdigest()
        if name == "Sesame-upstream" and not working_path.exists():
            doc.Label = "Sesame S3 layout — upstream reference, fit pending"
            baseline = doc.addObject("App::DocumentObjectGroup", "UpstreamBaseline")
            baseline.Label = "Upstream geometry — S2 / SG90 reference"
            roots = [obj for obj in doc.RootObjects if obj != baseline]
            baseline.Group = roots
            components = doc.addObject("App::DocumentObjectGroup", "S3Components")
            components.Label = "S3 components — placement pending"
            notes = doc.addObject("App::FeaturePython", "BuildMetadata")
            for key, value in {
                "UpstreamRevision": entry["revision"],
                "Status": "Reference assembly only; S3 component fit and physical measurements pending",
                "CarrierASIN": "B071JYD6QP",
                "CarrierNominalSize": "70 x 50 mm; 1.6 mm listing thickness, not measured",
                "ServoScope": "Fixed-angle MG90S variants; excludes B0FH1KZ64Y continuous rotation",
            }.items():
                notes.addProperty("App::PropertyString", key, "Provenance")
                setattr(notes, key, value)
            doc.recompute()
            doc.saveAs(str(working_path))
        App.closeDocument(doc.Name)

    for path in sorted((ROOT / "assets" / "stl" / "upstream").glob("*.stl")):
        original = path.read_bytes()
        expected = hashlib.sha256(original).hexdigest()
        mesh_path = path
        if original.startswith(b"version https://git-lfs.github.com/spec/v1"):
            expected = next(line.split(":", 1)[1] for line in original.decode().splitlines() if line.startswith("oid sha256:"))
            match = next(e for e in manifest["files"] if Path(e["path"]).name == path.name)
            mesh_path = CAD / "upstream" / match["path"]
            validate(mesh_path.read_bytes(), match)
        actual = hashlib.sha256(mesh_path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Mesh differs from simulator asset: {path.name}")
        mesh = Mesh.Mesh(str(mesh_path))
        if mesh.CountFacets == 0:
            raise ValueError(f"Empty mesh: {mesh_path}")
        report["existing_stl_meshes"].append({
            "path": str(path.relative_to(ROOT)),
            "sha256": actual,
            "matches_simulator_asset": True,
            "closed": mesh.isSolid(), "facets": mesh.CountFacets,
            "volume_mm3": round(mesh.Volume, 6), "bounds": bounds(mesh),
        })
    (WORK / "freecad-import-full.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    for result in report["sources"]:
        result["objects"] = [o for o in result["objects"] if o.get("valid") is False
                             or ("valid" in o and any(word in o["label"].lower()
                                 for word in ("internal-frame", "bottom-cover", "femur", "foot-joint")))]
    report["detail"] = "Selected frame/leg and invalid objects; complete hierarchy is in the local work/freecad-import-full.json."
    (REPORTS / "freecad-import.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    for result in report["sources"]:
        print(f"{result['source_path']}: {result['object_count']} objects, "
              f"{result['shape_object_count']} shapes, {len(result['invalid_shape_objects'])} invalid")
    print(f"Working document available (existing edits preserved): {working_path}")


# FreeCADCmd loads .py entrypoints as modules rather than setting __name__ to
# "__main__". This file is an executable FreeCAD script, not a library module.
main()
