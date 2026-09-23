"""Derive a hub reference matching the confirmed A-X socket span.

Preserve the uploaded source. Translate each end strip outward by 0.48 mm and
bridge the PCB; do not scale the IC, connectors or 2.54 mm pin pitch. The resulting
60.96 mm outline and moved mounting holes remain inferred, not measured hardware.
"""
from pathlib import Path
import json
import FreeCAD as App
import FreeCADGui as Gui
import Part

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'assets/cad/upstream/pca9685-uploaded'


def restored_finish(old_shape, old_materials, new_shape, shift):
    """Sample actual face triangles, not centroids that may lie off a surface."""
    materials = []
    old_faces = old_shape.Faces
    boxes = [face.BoundBox for face in old_faces]
    for face in new_shape.Faces:
        vertices, triangles = face.tessellate(0.05)
        assert triangles, 'Cannot sample face for appearance transfer'
        a, b, c = triangles[0]
        point = (vertices[a] + vertices[b] + vertices[c]) / 3
        if point.x > 25 + shift:
            point.x -= shift
        elif point.x < -25 - shift:
            point.x += shift
        elif point.x > 25:
            point.x = 24.999
        elif point.x < -25:
            point.x = -24.999
        candidates = [i for i, box in enumerate(boxes)
                      if box.XMin-.1 <= point.x <= box.XMax+.1
                      and box.YMin-.1 <= point.y <= box.YMax+.1
                      and box.ZMin-.1 <= point.z <= box.ZMax+.1]
        assert candidates, 'No source appearance near corrected face'
        vertex = Part.Vertex(point)
        index = min(candidates, key=lambda i: old_faces[i].distToShape(vertex)[0])
        materials.append(old_materials[min(index, len(old_materials)-1)])
    return materials


def main():
    source = next(d for d in App.listDocuments().values()
                  if d.FileName == str(CACHE / 'ServoHub_STEP.FCStd'))
    if any(d.FileName == str(CACHE / 'ServoHub_FittedReference.FCStd')
           or d.Name == 'ServoHub_FittedReference' for d in App.listDocuments().values()):
        raise RuntimeError('Derived hub already open; preserve edits.')
    original = next(o for o in source.Objects if o.Label == 'Platine')
    shape = original.Shape
    shift = (58.42 - 57.46) / 2
    for x in [-25, 25]:
        slab = Part.makeBox(.02, 40, 30, App.Vector(x-.01, -20, -5))
        section = shape.common(slab)
        # One split also crosses a 0.035 mm surface-metal sliver. No component
        # bodies or projecting pins may be cut by the correction planes.
        assert .8-1e-6 <= section.Volume < .804
        assert section.BoundBox.ZMin >= -1e-7 and section.BoundBox.ZMax < 1.64
    left = shape.common(Part.makeBox(15, 40, 30, App.Vector(-40, -20, -5)))
    center = shape.common(Part.makeBox(50, 40, 30, App.Vector(-25, -20, -5)))
    right = shape.common(Part.makeBox(15, 40, 30, App.Vector(25, -20, -5)))
    left.translate(App.Vector(-shift, 0, 0))
    right.translate(App.Vector(shift, 0, 0))
    bridges = [Part.makeBox(shift, 25, 1.6, App.Vector(x, -12.5, 0))
               for x in [-25-shift, 25]]
    result = center.multiFuse([left, right] + bridges).removeSplitter()
    assert result.isValid() and len(result.Solids) == 1
    assert abs(result.Volume-shape.Volume-2*shift*25*1.6) < 1e-5
    doc = App.newDocument('ServoHub_FittedReference')
    doc.Label = 'Servo hub — socket-span-corrected reference'
    root = doc.copyObject(source.getObject('PCA9685'), True)
    body = next(o for o in doc.Objects if o.Label == 'Platine')
    moved = []
    for obj in doc.Objects:
        if obj == body or not obj.TypeId.startswith('Part::') or not hasattr(obj, 'Shape') or obj.Shape.isNull():
            continue
        box = obj.Shape.BoundBox
        if box.XMin >= 25 or box.XMax <= -25:
            assert 'text' in obj.Label.lower(), 'Unexpected separate component at board end'
        # Retain decorative legends as complete words instead of shifting
        # selected glyphs within a word. Their exact print positions are unverified.
    materials = restored_finish(shape, original.ViewObject.ShapeAppearance, result, shift)
    body.Shape = result
    body.ViewObject.ShapeAppearance = materials
    root.addProperty('App::PropertyString', 'DimensionalEvidence', 'Evidence')
    root.DimensionalEvidence = 'Instructor: symmetric headers mate cleanly at carrier A3-A8/X3-X8. Row span corrected 57.46 to 58.42 mm; end strips moved 0.48 mm each. Outline 60.96 x 25 mm inferred; mounting-hole moves unverified. Uploaded source preserved. No uniform scaling.'
    doc.recompute()
    doc.saveAs(str(CACHE / 'ServoHub_FittedReference.FCStd'))
    report = {'source_file': 'pca9685.step', 'source_sha256': '729f86d58615fe78411c493129f28bddd675943c1f008a4d414bb4e2520f712a',
              'required_row_span_mm': 58.42, 'original_row_span_mm': 57.46,
              'end_shift_mm': shift, 'resulting_outline_mm': [60.96, 25],
              'outline_evidence': 'Inferred correction, not measured board outline',
              'added_pcb_volume_mm3': result.Volume-shape.Volume,
              'translated_edge_objects': moved, 'legends': 'Unchanged source placements', 'body_object': body.Name,
              'source_body_preserved': True}
    (CACHE / 'span-correction.json').write_text(json.dumps(report, indent=2)+'\n')
    App.setActiveDocument(doc.Name)
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    print('PASS: derived 58.42 mm socket span without scaling components or row pitch; source preserved.')


main()
