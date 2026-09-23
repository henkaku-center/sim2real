"""Create the independent circuitry document once; preserve subsequent GUI edits.

Run with FreeCADCmd or through open_circuitry.FCMacro. Native document properties
become authoritative after creation; this script is not a regeneration command.
"""

from pathlib import Path
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "assets" / "cad" / "work"
PATH = WORK / "Sesame-S3-circuitry.FCStd"


def annotate(obj, values):
    for name, value in values.items():
        obj.addProperty("App::PropertyString", name, "Evidence")
        setattr(obj, name, value)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    doc = next((d for d in App.listDocuments().values() if d.FileName == str(PATH)), None)
    created = doc is None and not PATH.exists()
    if doc is None and not created:
        doc = App.openDocument(str(PATH))
    if created:
        doc = App.newDocument("Sesame_S3_Circuitry")
        doc.Label = "Sesame S3 circuitry — validation in progress"
        assembly = doc.addObject("App::Part", "Circuitry")
        assembly.Label = "Circuit board assembly"
        carrier = doc.addObject("Part::Box", "Carrier")
        carrier.Label = "Carrier — 70 × 50 mm; thickness nominal"
        carrier.Length, carrier.Width, carrier.Height = 70, 50, 1.6
        annotate(carrier, {
            "ASIN": "B071JYD6QP",
            "OutlineEvidence": "70 x 50 mm confirmed by instructor, 2026-09-23",
            "ThicknessEvidence": "1.6 mm from listing; not measured on installed board",
            "HoleLayoutStatus": "18 x 24, 2.54 mm pitch per album/listing; edge offsets and mounting holes unmeasured, not yet modeled",
            "Datum": "Origin at PCB lower corner; X=70 mm edge, Y=50 mm edge, Z upward; top surface at Z=Height",
        })
        assembly.addObject(carrier)

        refs = doc.addObject("App::Part", "UnplacedReferences")
        refs.Label = "UNPLACED reference outlines — hidden initially"
        refs.Placement.Base = App.Vector(95, 0, 0)
        for name, label, length, width, y, asin in [
            ("PCA9685Footprint", "PCA9685 PCB outline — 61 × 25 mm", 61, 25, 0, "B078YRJ8D7"),
            ("OLEDFootprint", "OLED PCB outline — 25.4 × 26.1 mm", 25.4, 26.1, 35, "B08CTZVVLS"),
        ]:
            obj = doc.addObject("Part::Plane", name)
            obj.Label = label
            obj.Length, obj.Width = length, width
            obj.Placement.Base = App.Vector(0, y, 0)
            annotate(obj, {"ASIN": asin, "Evidence": "Exact purchased listing; not physically measured",
                           "Status": "2D outline only; thickness, headers, holes and assembly placement unknown",
                           "PlacementMeaning": "Reference display position only, not installed coordinates"})
            refs.addObject(obj)

        pending = doc.addObject("App::DocumentObjectGroup", "PendingMeasurements")
        pending.Label = "Unmodeled parts / measurements needed"
        for name, label, asin, status in [
            ("Converter", "LM2596 — outline and installed position needed", "B07NVSVW1N", "Listing images conflict: 42 x 21 mm versus 45 x 20 mm; height and position unmeasured"),
            ("Controller", "S3 SuperMini — dimensions and socket height needed", "B0H9LLXWNH", "No verified board drawing; USB envelope and pin rows need measurement"),
            ("HeadersWiring", "Headers, wires and solder — measurements needed", "Unresolved", "Model raised sockets, underside protrusions, cable exits and insertion space"),
        ]:
            obj = doc.addObject("App::FeaturePython", name)
            obj.Label = label
            annotate(obj, {"ASIN": asin, "Status": status})
            pending.addObject(obj)
        notes = doc.addObject("App::FeaturePython", "ValidationScope")
        notes.Label = "Scope — circuitry first, enclosure later"
        annotate(notes, {
            "Decision": "Instructor: validate standalone circuitry before redesigning robot body, 2026-09-23",
            "CurrentStage": "Carrier outline only; no assembled stack, installed placements or wire geometry claimed",
            "LaterScope": "Battery, toggle and OLED harness clearances; enclosure designed after physical validation",
            "Editing": "Edit native Carrier Length/Width/Height in the Data tab; creation script preserves saved document edits",
        })
        doc.recompute()

    App.setActiveDocument(doc.Name)
    if App.GuiUp:
        import FreeCADGui as Gui
        from PySide import QtCore
        if created:
            doc.Carrier.ViewObject.ShapeColor = (0.48, 0.29, 0.12)
            doc.Carrier.ViewObject.LineColor = (0.12, 0.08, 0.04)
            doc.UnplacedReferences.ViewObject.Visibility = False
            for obj in doc.Objects:
                if obj.TypeId in ("App::Origin", "App::Line", "App::Plane", "App::Point"):
                    obj.ViewObject.Visibility = False
        view = Gui.activeDocument().activeView()
        view.viewAxonometric()
        view.fitAll()

        def capture():
            view.viewAxonometric()
            view.fitAll()
            view.saveImage(str(WORK / "circuitry-preview.png"), 1200, 900, "White")
            (WORK / "circuitry-opened.txt").write_text("Standalone circuitry document opened.\n")

        QtCore.QTimer.singleShot(1200, capture)
    if created:
        doc.saveAs(str(PATH))
    print(f"Circuitry document: {PATH}; created={created}")


# FreeCADCmd loads Python entrypoints as modules.
main()
