"""Read the saved assembly into a renderer-independent authoring snapshot.

Run in FreeCAD's GUI services after saving the assembly (Xvfb is supported).
Native objects remain authoritative; this is a snapshot, never a regeneration input.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/cad/instructions/assembly-cad-snapshot.json'
sys.path.insert(0, str(ROOT / 'tools'))
from cad_document import ASSEMBLY, open_assembly


def effective_visibility(obj, seen=None):
    """Ignore Boolean dependencies; only container visibility is inherited."""
    seen = set() if seen is None else seen
    if obj.Name in seen:
        return True
    seen.add(obj.Name)
    if not obj.ViewObject.Visibility:
        return False
    parents = [p for p in obj.InList if 'Group' in p.PropertiesList and obj in p.Group]
    return all(effective_visibility(p, seen.copy()) for p in parents)


def pose(placement):
    return {'translation_mm': list(placement.Base),
            'quaternion_xyzw': list(placement.Rotation.Q)}


def appearance(view):
    result = {'visible': view.Visibility}
    for name in ['DisplayMode', 'LineWidth', 'LineColor']:
        if hasattr(view, name):
            result[name] = getattr(view, name)
    if hasattr(view, 'ShapeAppearance'):
        unique, indices = [], []
        for material in view.ShapeAppearance:
            value = {key: list(getattr(material, key)) for key in
                     ['DiffuseColor', 'AmbientColor', 'SpecularColor', 'EmissiveColor']}
            value.update(Shininess=material.Shininess, Transparency=material.Transparency)
            if value not in unique:
                unique.append(value)
            indices.append(unique.index(value))
        result['materials'] = unique
        result['material_assignment'] = ('uniform' if len(unique) == 1 else indices)
    return result


def main():
    assert App.GuiUp, 'Run in the existing GUI to capture current visual properties.'
    doc = open_assembly()
    if doc.isTouched():
        raise RuntimeError(f'Recompute and save {doc.Label} before exporting.')
    # Preserve every existing semantic ID while co-locating the two old roles.
    docs = {'carrier': doc, 'comparison': doc}
    bindings = [
        ('carrier', 'carrier', 'PerforatedCarrier'),
        ('carrier.display', 'comparison', 'PerfboardReference'),
        ('carrier.rings', 'comparison', 'CarrierRings'),
        ('carrier.capsules', 'comparison', 'CarrierCapsules'),
        ('carrier.lettering', 'comparison', 'CarrierLettering'),
        ('converter', 'comparison', 'CandidateModule'),
        ('converter.reference_group', 'comparison', 'YAAJ_DCDC_StepDown_LM2596_cp'),
        ('converter.pcb', 'comparison', 'Part__Feature'),
        ('converter.trimmer_body', 'comparison', 'Part__Feature002'),
        ('converter.adjustment_screw', 'comparison', 'MeasuredAdjustmentScrew'),
        ('converter.capacitor_1', 'comparison', 'MeasuredCapacitor1'),
        ('converter.capacitor_2', 'comparison', 'MeasuredCapacitor2'),
        ('tape', 'comparison', 'InsulationEnvelope'),
        ('pins', 'comparison', 'ConverterPins'),
    ]
    for address in ['O17', 'V17', 'O1', 'V1']:
        for semantic, prefix in [('pins', 'ConverterPin_'),
                                 ('top_solder', 'TopSolder_'),
                                 ('converter_hole_fill', 'ConverterHoleSolder_'),
                                 ('carrier_hole_fill', 'CarrierHoleSolder_'),
                                 ('bottom_solder', 'BottomSolder_')]:
            bindings.append((f'{semantic}.{address}', 'comparison', prefix + address))
    hub = docs['comparison'].getObject('ServoHubCandidate')
    if hub:
        imported = doc.getObject('PCA9685')
        body = doc.getObject('Part__Feature400')
        assert imported is not None and body is not None, 'Preserve the stable imported hub object identities.'
        bindings.extend([('servo_hub', 'comparison', hub.Name),
                         ('servo_hub.reference', 'comparison', imported.Name),
                         ('servo_hub.body', 'comparison', body.Name)])
    records = []
    for obj in docs['comparison'].Objects:
        if 'InstructionId' in obj.PropertiesList:
            bindings.append((obj.InstructionId, 'comparison', obj.Name))
    for name in ['HubMaleHeaders', 'HubFemaleSockets', 'AuxiliaryHeaders', 'CarrierJumpers', 'S3SuperMini', 'S3FemaleSockets', 'CarrierUndersideWires']:
        if docs['comparison'].getObject(name):
            bindings.append((name, 'comparison', name))
    bound_names = {name for _, _, name in bindings}
    # Imported components, hidden source geometry, carrier construction and
    # parameters also need stable identities for export and staged instruction work.
    for obj in doc.Objects:
        if obj.Name not in bound_names:
            bindings.append(('cad.' + obj.Name, 'comparison', obj.Name))
    for semantic, document, name in bindings:
        obj = docs[document].getObject(name)
        assert obj is not None, name
        record = {'id': semantic, 'document': 'assembly', 'native_object': name,
                  'label': obj.Label, 'type': obj.TypeId,
                  'cad_dependents': [o.Name for o in obj.InList],
                  'appearance': appearance(obj.ViewObject),
                  'effective_visible': effective_visibility(obj)}
        if hasattr(obj, 'Placement'):
            record['local_pose'] = pose(obj.Placement)
            record['global_pose'] = pose(obj.getGlobalPlacement() if hasattr(obj, 'getGlobalPlacement') else obj.Placement)
        parent = obj.getParentGeoFeatureGroup() if hasattr(obj, 'getParentGeoFeatureGroup') else None
        record['parent_coordinate_group'] = parent.Name if parent else None
        record['containers'] = [p.Name for p in obj.InList if 'Group' in p.PropertiesList and obj in p.Group]
        if hasattr(obj, 'Group'):
            record['members'] = [o.Name for o in obj.Group]
        if hasattr(obj, 'Shape') and obj.TypeId != 'App::Part':
            record['solid_count'] = len(obj.Shape.Solids)
            record['face_count'] = len(obj.Shape.Faces)
            record['export_visible_geometry'] = (effective_visibility(obj) and not obj.Shape.isNull()
                                                  and obj.TypeId not in ('App::Line', 'App::Plane', 'App::Point', 'App::Origin'))
        else:
            record['export_visible_geometry'] = False
        record['links'] = {prop: getattr(obj, prop).Name for prop in ['LinkedObject', 'Base', 'Tool']
                           if prop in obj.PropertiesList and hasattr(getattr(obj, prop), 'Name')}
        record['expressions'] = [[path, expression] for path, expression in obj.ExpressionEngine]
        record['construction_metadata'] = {name: getattr(obj, name) for name in
            ['Address', 'Addresses', 'ConnectorPurpose', 'Signal', 'CableColor', 'PinoutEvidence', 'SourceObject', 'Evidence']
            if name in obj.PropertiesList}
        records.append(record)
    parameters = {}
    settings = docs['comparison'].Installation
    for name in settings.PropertiesList:
        if settings.getTypeIdOfProperty(name) == 'App::PropertyLength':
            parameters[name] = {'value_mm': getattr(settings, name).Value,
                                'evidence': settings.getDocumentationOfProperty(name)}
    hub_parameters = {}
    hub_settings = docs['comparison'].getObject('HubInstallation')
    if hub_settings:
        for name in hub_settings.PropertiesList:
            if hub_settings.getTypeIdOfProperty(name) == 'App::PropertyLength':
                hub_parameters[name] = {'value_mm': getattr(hub_settings, name).Value,
                                        'evidence': hub_settings.getDocumentationOfProperty(name)}
    report = {
        'schema_version': 2,
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'source': 'Read-only native assembly snapshot; save the document before export.',
        'units': {'length': 'mm', 'rotation': 'quaternion_xyzw'},
        'freecad_version': list(App.Version()),
        'authority': 'Native CAD is authoritative. Saved-file hashes identify disk artifacts, not a substitute for saving live edits.',
        'documents': {'assembly': {'path': str(ASSEMBLY.relative_to(ROOT)),
                                  'saved_file_sha256': hashlib.sha256(ASSEMBLY.read_bytes()).hexdigest(),
                                  'storage': 'Git LFS'}},
        'previous_document_hashes': json.loads(doc.AssemblyMetadata.SourceDocuments),
        'source_permissions': doc.AssemblyMetadata.SourcePermissions,
        'viewer_contract': {
            'model_id': doc.AssemblyMetadata.ModelId,
            'coordinates': 'Right-handed CAD millimetres, Z-up; retain source geometry origins.',
            'binding_key': 'Stable id; native_object is the FreeCAD Name, not Label.',
            'render_selection': 'Export only export_visible_geometry=true objects; do not also mesh their parent containers.',
            'instancing': 'App::Link records retain linked-object identity; instance visible links even if their source is hidden.',
            'animation': 'Read initial states, dependencies and geometry/visibility changes from the installation records. Transform parent groups for detachable units.',
            'target_renderer': 'Renderer-independent; suitable as authoring input for a future WebGPU viewer.',
            'intermediate_geometry': 'Finished-state geometry only; missing uncut pins, tape layers and tool states remain explicit in the records.',
        },
        'placement_note': 'Transforms act on native object-local geometry. Shape data can already contain nonzero vertex coordinates; do not recenter exported meshes without updating transforms.',
        'parameters': parameters,
        'hub_parameters': hub_parameters,
        'additional_parameters': {
            group: {name: {'value_mm': getattr(obj, name).Value,
                           'evidence': obj.getDocumentationOfProperty(name)}
                    for name in obj.PropertiesList
                    if obj.getTypeIdOfProperty(name) == 'App::PropertyLength'}
            for group in ['CarrierConnections', 'S3Installation', 'UndersideWiring']
            if (obj := docs['comparison'].getObject(group)) is not None},
        'hub_evidence': {name: getattr(hub_settings, name) for name in
                         ['SeatingEvidence', 'PurchasedHeaderEvidence']
                         if hub_settings and name in hub_settings.PropertiesList},
        'objects': records,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(f'PASS: {len(records)} native bindings and {len(parameters)} parameters exported; CAD untouched.', flush=True)


if __name__ in ('__main__', '<run_path>'):
    main()
