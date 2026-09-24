"""Validate the saved assembly, stable authoring bindings and step dependencies.

Run with FreeCAD's Python interpreter; GUI services additionally check materials
and saved visibility. This script never saves or changes the native document.
"""
from pathlib import Path
import hashlib
import json
import sys
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from cad_document import ASSEMBLY, open_assembly


def main():
    before = hashlib.sha256(ASSEMBLY.read_bytes()).hexdigest()
    doc = open_assembly()
    records = ROOT / 'assets/cad/instructions'
    snapshot = json.loads((records / 'assembly-cad-snapshot.json').read_text())
    assert snapshot['schema_version'] == 2
    assert set(snapshot['documents']) == {'assembly'}
    assert snapshot['documents']['assembly']['saved_file_sha256'] == before
    assert doc.AssembledElectronics and doc.CarrierDesign and doc.AssemblyMetadata
    assert doc.PerforatedCarrier.getParentGeoFeatureGroup() == doc.Circuitry
    assert doc.Circuitry.getParentGeoFeatureGroup() == doc.CarrierDesign
    holes = [o for o in doc.Objects if o.Name.startswith('Hole_') and 'Address' in o.PropertiesList]
    assert len(holes) == len({o.Address for o in holes}) == 432
    parts = [o for o in doc.Objects if 'InstructionId' in o.PropertiesList]
    assert len(parts) == len({o.InstructionId for o in parts}) == 284
    for obj in parts:
        assert not obj.Shape.isNull() and obj.Shape.isValid(), obj.Name
    assert abs(doc.PerforatedCarrier.Shape.Volume - doc.PerfboardReference.Shape.Volume) < 1e-6
    for obj in doc.Objects:
        for prop in obj.PropertiesList:
            if 'XLink' in obj.getTypeIdOfProperty(prop):
                pending = [getattr(obj, prop)]
                while pending:
                    target = pending.pop()
                    if isinstance(target, (list, tuple)):
                        pending.extend(target)
                    elif hasattr(target, 'Document'):
                        assert target.Document == doc, (obj.Name, prop)

    assert len({r['id'] for r in snapshot['objects']}) == len(snapshot['objects'])
    assert {r['native_object'] for r in snapshot['objects']} == {o.Name for o in doc.Objects}
    rendered = set()
    for record in snapshot['objects']:
        assert record['document'] == 'assembly'
        obj = doc.getObject(record['native_object'])
        assert obj.TypeId == record['type'], obj.Name
        if 'global_pose' in record:
            placement = obj.getGlobalPlacement() if hasattr(obj, 'getGlobalPlacement') else obj.Placement
            assert (placement.Base - App.Vector(*record['global_pose']['translation_mm'])).Length < 1e-7, obj.Name
            q = record['global_pose']['quaternion_xyzw']
            assert placement.Rotation.isSame(App.Rotation(*q), 1e-7), obj.Name
        assert [list(value) for value in obj.ExpressionEngine] == record['expressions'], obj.Name
        if record['export_visible_geometry']:
            assert obj.Name not in rendered, obj.Name
            rendered.add(obj.Name)
        if App.GuiUp:
            from export_instruction_snapshot import effective_visibility
            assert record['effective_visible'] == effective_visibility(obj), obj.Name
            style = record['appearance']
            assert obj.ViewObject.Visibility == style['visible'], obj.Name
            if style.get('materials'):
                materials = obj.ViewObject.ShapeAppearance
                assignment = style['material_assignment']
                if assignment == 'uniform':
                    assignment = [0] * len(materials)
                assert len(assignment) == len(materials), obj.Name
                for material, index in zip(materials, assignment):
                    target = style['materials'][index]['DiffuseColor']
                    assert max(abs(a-b) for a,b in zip(material.DiffuseColor,target)) < 1e-6, obj.Name
    assert {'PerfboardReference', 'CarrierRings', 'CarrierCapsules'} <= rendered
    assert 'PerforatedCarrier' not in rendered  # Hidden native history must not double-render.
    assert any(n.startswith('S3Source_') for n in rendered)
    assert 'MeasuredCapacitor1' in rendered and 'MeasuredCapacitor2' in rendered

    step_count = 0
    for path in records.glob('*.json'):
        if path.name.endswith('snapshot.json'):
            continue
        record = json.loads(path.read_text())
        if 'cad_snapshot' in record:
            assert record['cad_snapshot'] == 'assembly-cad-snapshot.json', path.name
        steps = record.get('steps', [])
        by_id = {step['id']: step for step in steps}
        assert len(by_id) == len(steps), path.name
        done, active = set(), set()
        def visit(name):
            assert name in by_id, (path.name, name)
            assert name not in active, (path.name, 'cyclic step dependency', name)
            if name in done:
                return
            active.add(name)
            for dep in by_id[name].get('depends_on', []):
                visit(dep)
            active.remove(name)
            done.add(name)
        for name in by_id:
            visit(name)
        step_count += len(steps)
    assert hashlib.sha256(ASSEMBLY.read_bytes()).hexdigest() == before
    result = {'status': 'PASS', 'document': str(ASSEMBLY.relative_to(ROOT)),
              'sha256': before, 'native_objects': len(doc.Objects),
              'instruction_parts': len(parts), 'carrier_addresses': len(holes),
              'snapshot_bindings': len(snapshot['objects']),
              'visible_export_objects': len(rendered), 'instruction_steps': step_count,
              'external_document_links': 0, 'native_file_unchanged': True,
              'freecad_version': list(App.Version())}
    (ROOT / 'assets/cad/reports/assembly-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: ' + json.dumps(result), flush=True)


# FreeCADCmd also loads command-line scripts as modules.
main()
