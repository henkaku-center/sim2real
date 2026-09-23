"""Read the open, saved CAD documents into an animation-authoring snapshot.

Run in the existing FreeCAD GUI after saving both documents. Does not modify CAD.
Native objects remain authoritative; this is a snapshot, never a regeneration input.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/cad/instructions/converter-cad-snapshot.json'
PATHS = {
    'carrier': 'assets/cad/work/Sesame-S3-circuitry.FCStd',
    'comparison': 'assets/cad/upstream/lm2596-yaaj/LM2596-comparison.FCStd',
}


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
    docs = {key: next(d for d in App.listDocuments().values()
                      if d.FileName == str(ROOT / path)) for key, path in PATHS.items()}
    for doc in docs.values():
        if doc.isTouched():
            raise RuntimeError(f'Recompute and save {doc.Label} before exporting.')
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
        imported = next(o for o in hub.Group if o.TypeId == 'App::Part')
        body = next(o for o in docs['comparison'].Objects if o.Label == 'Platine')
        bindings.extend([('servo_hub', 'comparison', hub.Name),
                         ('servo_hub.reference', 'comparison', imported.Name),
                         ('servo_hub.body', 'comparison', body.Name)])
    records = []
    for semantic, document, name in bindings:
        obj = docs[document].getObject(name)
        assert obj is not None, name
        record = {'id': semantic, 'document': document, 'native_object': name,
                  'label': obj.Label, 'type': obj.TypeId,
                  'cad_dependents': [o.Name for o in obj.InList],
                  'appearance': appearance(obj.ViewObject)}
        if hasattr(obj, 'Placement'):
            record['local_pose'] = pose(obj.Placement)
            record['global_pose'] = pose(obj.getGlobalPlacement())
        parent = obj.getParentGeoFeatureGroup()
        record['parent_coordinate_group'] = parent.Name if parent else None
        if hasattr(obj, 'Group'):
            record['members'] = [o.Name for o in obj.Group]
        if hasattr(obj, 'Shape') and obj.TypeId != 'App::Part':
            record['solid_count'] = len(obj.Shape.Solids)
        record['expressions'] = [[path, expression] for path, expression in obj.ExpressionEngine]
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
        'schema_version': 1,
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'source': 'Read-only live GUI snapshot; caller must save documents before export.',
        'units': {'length': 'mm', 'rotation': 'quaternion_xyzw'},
        'freecad_version': list(App.Version()),
        'authority': 'Native CAD is authoritative. Saved-file hashes identify disk artifacts, not a substitute for saving live edits.',
        'documents': {key: {'path': path, 'saved_file_sha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                            'distribution': 'Git LFS' if key == 'carrier' else 'local_only_ignored_candidate'}
                      for key, path in PATHS.items()},
        'placement_note': 'Transforms act on native object-local geometry. Shape data can already contain nonzero vertex coordinates; do not recenter exported meshes without updating transforms.',
        'parameters': parameters,
        'hub_parameters': hub_parameters,
        'objects': records,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(f'PASS: {len(records)} native bindings and {len(parameters)} parameters exported; CAD untouched.')


main()
