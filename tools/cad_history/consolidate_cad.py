"""One-time consolidation of the saved carrier and assembled electronics.

Run in FreeCAD 1.1.3 with GUI services (Xvfb is sufficient). Source documents
are read-only. Native names, expressions and assembly placements are retained.
"""
from pathlib import Path
import hashlib
import json
import FreeCAD as App
import FreeCADGui as Gui

ROOT = Path(__file__).resolve().parents[2]
CAD = ROOT / 'assets/cad'
ASSEMBLY = CAD / 'Sesame-S3-Assembly.FCStd'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if ASSEMBLY.exists():
        raise RuntimeError('Assembly already exists; preserve native edits.')
    source = CAD / 'upstream/lm2596-yaaj/LM2596-comparison.FCStd'
    carrier = CAD / 'work/Sesame-S3-circuitry.FCStd'
    hashes = {str(p.relative_to(ROOT)): sha256(p) for p in (source, carrier)}
    doc = App.openDocument(str(source))
    original_objects = list(doc.Objects)
    original_roots = list(doc.RootObjects)
    visibility = {o.Name: o.ViewObject.Visibility for o in original_objects}
    placements = {o.Name: o.getGlobalPlacement() for o in original_objects if hasattr(o, 'Placement')}
    expressions = {o.Name: list(o.ExpressionEngine) for o in original_objects}
    ids = {o.Name: o.InstructionId for o in original_objects if 'InstructionId' in o.PropertiesList}
    carrier_doc = App.openDocument(str(carrier))
    doc.copyObject(carrier_doc.Objects, recursive=True, return_all=True)
    imported = [o for o in doc.Objects if o not in original_objects]
    imported_roots = [o for o in doc.RootObjects if o not in original_roots]
    assert len(imported) == 1500, len(imported)
    assert len(ids) == 284, len(ids)

    assembly = doc.addObject('App::Part', 'AssembledElectronics')
    assembly.Label = 'ASSEMBLED ELECTRONICS — open this group'
    assembly.Group = original_roots
    design = doc.addObject('App::Part', 'CarrierDesign')
    design.Label = 'Carrier construction history — hidden, editable'
    design.Group = imported_roots
    for obj in imported:
        if 'FontFile' in obj.PropertiesList:
            obj.FontFile = str(CAD / 'fonts/SourceCodePro-Regular.ttf')
    design.Visibility = False
    for name, visible in visibility.items():
        doc.getObject(name).ViewObject.Visibility = visible

    for name, label in {
        'CandidateModule': 'LM2596 converter — installed and height-adjusted',
        'PerfboardReference': 'Carrier PCB — installed display geometry',
        'ServoHubCandidate': 'PCA9685 servo hub — removable assembly',
        'S3SuperMini': 'ESP32-S3 SuperMini — removable assembly',
        'HubFemaleSockets': 'Carrier-fixed servo hub sockets and solder',
        'S3FemaleSockets': 'Carrier-fixed S3 sockets and solder',
        'AuxiliaryHeaders': 'OLED and power headers',
        'CarrierJumpers': 'Four insulated jumpers',
        'CarrierUndersideWires': 'Underside wiring and solder',
    }.items():
        doc.getObject(name).Label = label
    doc.Circuitry.Label = 'Editable carrier, grid, pads and lettering'
    doc.PendingMeasurements.Label = 'Historical carrier-stage notes — superseded by assembly records'
    doc.ValidationScope.CurrentStage = 'Complete installed electronics; native carrier construction retained in CarrierDesign.'
    doc.PerfboardReference.addProperty('App::PropertyString', 'EditableSource', 'Authoring')
    doc.PerfboardReference.EditableSource = 'PerforatedCarrier'
    doc.PerfboardReference.addProperty('App::PropertyString', 'DisplayGeometryNote', 'Authoring')
    doc.PerfboardReference.DisplayGeometryNote = 'Installed geometry snapshot, preserved from the verified assembly. CarrierDesign retains the editable native source; refresh display geometry after dimensional edits.'

    metadata = doc.addObject('App::FeaturePython', 'AssemblyMetadata')
    metadata.Label = 'Provenance and animated-instruction metadata'
    values = {
        'ModelId': 'sesame-s3.assembled-electronics',
        'Role': 'Authoritative assembled electronics document; not the complete robot enclosure.',
        'UnitsAndFrame': 'Millimetres, right-handed Z-up; origin at carrier underside; X along 70 mm edge.',
        'SourceDocuments': json.dumps(hashes, sort_keys=True),
        'InstructionSnapshot': 'instructions/assembly-cad-snapshot.json',
        'AuthoringGuide': 'instructions/README.md',
        'IdentityPolicy': 'Native object Names and InstructionId values are stable; display Labels are not identifiers.',
        'GeometryPolicy': 'Keep individual components, pins, sockets, solder and insulation; do not flatten into a mesh.',
        'SourcePermissions': 'Imported converter and uploaded hub/S3 source permissions remain unresolved; source provenance and limitations are retained in instruction records.',
        'ConsolidatedOn': '2026-09-24',
    }
    for key, value in values.items():
        metadata.addProperty('App::PropertyString', key, 'Assembly')
        setattr(metadata, key, value)
    metadata.addProperty('App::PropertyStringList', 'InstructionRecords', 'Assembly')
    metadata.InstructionRecords = [str(p.relative_to(CAD)) for p in sorted((CAD / 'instructions').glob('*.json')) if not p.name.endswith('snapshot.json')]
    doc.Label = 'Sesame S3 — assembled electronics'
    doc.recompute()
    # Grouping must not move or rebuild any installed component.
    for name, placement in placements.items():
        current = doc.getObject(name).getGlobalPlacement()
        assert (current.Base - placement.Base).Length < 1e-7, name
        assert current.Rotation.isSame(placement.Rotation, 1e-7), name
    for name, value in ids.items():
        assert doc.getObject(name).InstructionId == value, name
    for name, value in expressions.items():
        assert list(doc.getObject(name).ExpressionEngine) == value, name
    holes = [o for o in imported if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList]
    assert len(holes) == len({o.Address for o in holes}) == 432
    for obj in original_objects:
        if obj.Name in ids:
            assert not obj.Shape.isNull() and obj.Shape.isValid(), obj.Name
    App.setActiveDocument(doc.Name)
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    doc.saveAs(str(ASSEMBLY))
    for path, expected in hashes.items():
        assert sha256(ROOT / path) == expected, path
    print(f'PASS: {len(doc.Objects)} native objects consolidated; 284 instruction IDs and 432 carrier addresses preserved.', flush=True)
    return doc


if __name__ in ('__main__', '<run_path>'):
    main()
