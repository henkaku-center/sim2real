"""Add native, addressable perfboard bores and coordinate annotations once.

Open with FreeCADCmd or add_carrier_grid.FCMacro. Saved native objects and
expressions remain editable without this module after the upgrade.
"""
from pathlib import Path
import csv
import math
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "assets" / "cad" / "work"
FILE = WORK / "Sesame-S3-circuitry.FCStd"


def add_grid(doc):
    if doc.getObject("PerforatedCarrier"):
        return False
    board = doc.Carrier
    doc.openTransaction("Add 24 by 18 carrier hole grid")
    try:
        params = doc.addObject("App::FeaturePython", "HoleGrid")
        params.Label = "Hole grid — 24 × 18; offsets provisional"
        for name, value in [("Columns", 24), ("Rows", 18)]:
            params.addProperty("App::PropertyInteger", name, "Grid")
            setattr(params, name, value)
            params.setEditorMode(name, 1)  # Topology is fixed; dimensions remain editable.
        for name, value in [("Pitch", 2.54), ("HoleDiameter", 0.9), ("OffsetX", 5.79), ("OffsetY", 3.41)]:
            params.addProperty("App::PropertyLength", name, "Grid")
            setattr(params, name, value)
        params.setExpression("OffsetX", "(Carrier.Length - 23 * Pitch) / 2")
        params.setExpression("OffsetY", "(Carrier.Width - 17 * Pitch) / 2")
        for name, text in {
            "Source": "Amazon.co.jp B071JYD6QP: 18x24, 2.54 mm pitch; 0.9 mm signal diameter provisional (listing also says 1.0 mm). Assembly photo 01 confirms grid count.",
            "BoardMarking": "PY-5cmx7cm 2.54mm 22402A-18 — transcribed by instructor, 2026-09-23",
            "OffsetEvidence": "Centered grid assumption, NOT a measured edge offset. Remove OffsetX/OffsetY expressions to enter measurements.",
            "Coordinates": "Top view: A-X left to right; 1-18 top to bottom. A1 is upper left; A18 lower left. Labels follow the supplied photo orientation.",
            "MountingHoles": "Four corner holes confirmed by instructor and photo; modeled with explicitly provisional photo estimates",
        }.items():
            params.addProperty("App::PropertyString", name, "Evidence")
            setattr(params, name, text)
        doc.Circuitry.addObject(params)
        tools = []
        for col in range(24):
            for row in range(18):
                address = f"{chr(65 + col)}{row + 1}"
                hole = doc.addObject("Part::Cylinder", "Hole_" + address)
                hole.Label = address
                hole.setExpression("Radius", "HoleGrid.HoleDiameter / 2")
                hole.setExpression("Height", "Carrier.Height + 2 mm")
                hole.setExpression("Placement.Base.x", f"Carrier.Placement.Base.x + HoleGrid.OffsetX + {col} * HoleGrid.Pitch")
                hole.setExpression("Placement.Base.y", f"Carrier.Placement.Base.y + Carrier.Width - HoleGrid.OffsetY - {row} * HoleGrid.Pitch")
                hole.setExpression("Placement.Base.z", "Carrier.Placement.Base.z - 1 mm")
                tools.append(hole)
        mounts = doc.addObject("App::FeaturePython", "MountingHoleParameters")
        mounts.Label = "4 mounting holes — PHOTO ESTIMATES, measure before fitting"
        for name, value in [("Diameter", 2.5), ("InsetX", 2.0), ("InsetY", 2.0)]:
            mounts.addProperty("App::PropertyLength", name, "Provisional dimensions")
            setattr(mounts, name, value)
        mounts.addProperty("App::PropertyString", "Evidence", "Evidence")
        mounts.Evidence = "Count=4 physically confirmed. Diameter ~2.5 mm and edge-to-center insets ~2 mm estimated visually from photo-01 against nominal 70x50 mm outline; symmetry assumed. NOT measured or manufacturer-specified."
        doc.Circuitry.addObject(mounts)
        for name, x, y in [
            ("TL", "MountingHoleParameters.InsetX", "Carrier.Width - MountingHoleParameters.InsetY"),
            ("TR", "Carrier.Length - MountingHoleParameters.InsetX", "Carrier.Width - MountingHoleParameters.InsetY"),
            ("BL", "MountingHoleParameters.InsetX", "MountingHoleParameters.InsetY"),
            ("BR", "Carrier.Length - MountingHoleParameters.InsetX", "MountingHoleParameters.InsetY"),
        ]:
            hole = doc.addObject("Part::Cylinder", "Mount_" + name)
            hole.Label = "Mount " + name + " — provisional"
            hole.setExpression("Radius", "MountingHoleParameters.Diameter / 2")
            hole.setExpression("Height", "Carrier.Height + 2 mm")
            hole.setExpression("Placement.Base.x", "Carrier.Placement.Base.x + " + x)
            hole.setExpression("Placement.Base.y", "Carrier.Placement.Base.y + " + y)
            hole.setExpression("Placement.Base.z", "Carrier.Placement.Base.z - 1 mm")
            tools.append(hole)
        compound = doc.addObject("Part::Compound", "HoleTools")
        compound.Label = "432 signal + 4 mounting hole tools"
        compound.Links = tools
        result = doc.addObject("Part::Cut", "PerforatedCarrier")
        result.Label = "Carrier — 432 signal + 4 provisional mounting holes"
        result.Base, result.Tool = board, compound
        doc.Circuitry.addObject(result)
        labels = doc.addObject("App::DocumentObjectGroup", "GridLabels")
        labels.Label = "Hole coordinates — A–X / 1–18"
        doc.Circuitry.addObject(labels)
        for col in range(24):
            char = chr(65 + col)
            label = doc.addObject("App::Annotation", "Column_" + char)
            label.LabelText = [char]
            label.setExpression("Position.x", f"Hole_{char}18.Placement.Base.x")
            label.setExpression("Position.y", "Carrier.Placement.Base.y - 2 mm")
            label.setExpression("Position.z", "Carrier.Placement.Base.z + Carrier.Height + 0.1 mm")
            labels.addObject(label)
        for row in range(18):
            label = doc.addObject("App::Annotation", f"Row_{row+1}")
            label.LabelText = [str(row + 1)]
            label.setExpression("Position.x", "Carrier.Placement.Base.x - 3 mm")
            label.setExpression("Position.y", f"Hole_A{row+1}.Placement.Base.y")
            label.setExpression("Position.z", "Carrier.Placement.Base.z + Carrier.Height + 0.1 mm")
            labels.addObject(label)
        doc.Carrier.HoleLayoutStatus = "432 signal bores + 4 corner mounting holes; signal edge offsets and mounting dimensions provisional"
        doc.ValidationScope.CurrentStage = "Carrier with 24x18 coordinate grid and four provisional corner holes; measurements and installed components pending"
        doc.recompute()
        expected = board.Shape.Volume - 432 * math.pi * (params.HoleDiameter.Value / 2) ** 2 * board.Height.Value
        expected -= 4 * math.pi * (mounts.Diameter.Value / 2) ** 2 * board.Height.Value
        assert result.Shape.isValid() and len(result.Shape.Solids) == 1
        assert abs(result.Shape.Volume - expected) < 1e-5
        doc.commitTransaction()
        return True
    except Exception:
        doc.abortTransaction()
        raise


def main():
    doc = next((d for d in App.listDocuments().values() if d.FileName == str(FILE)), None)
    if doc is None:
        doc = App.openDocument(str(FILE))
    changed = add_grid(doc)
    App.setActiveDocument(doc.Name)
    reports = ROOT / "assets" / "cad" / "reports"
    with (reports / "carrier-hole-coordinates.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["address", "x_mm", "y_mm", "pcb_top_z_mm", "diameter_mm", "offset_status"])
        for col in range(24):
            for row in range(18):
                name = f"{chr(65+col)}{row+1}"
                pos = doc.getObject("Hole_" + name).Placement.Base
                writer.writerow([name, round(pos.x, 6), round(pos.y, 6), doc.Carrier.Placement.Base.z + doc.Carrier.Height.Value,
                                 doc.HoleGrid.HoleDiameter.Value, "centered assumption; not measured"])
    if App.GuiUp:
        import FreeCADGui as Gui
        from PySide import QtCore
        doc.Carrier.ViewObject.hide()
        doc.HoleTools.ViewObject.hide()
        for obj in doc.HoleTools.Links:
            obj.ViewObject.hide()
        doc.PerforatedCarrier.ViewObject.ShapeColor = (0.08, 0.42, 0.24)
        doc.PerforatedCarrier.ViewObject.show()
        for label in doc.GridLabels.Group:
            label.ViewObject.FontSize = 12
            label.ViewObject.TextColor = (0.08, 0.08, 0.08)
            label.ViewObject.show()
        Gui.activeDocument().activeView().viewTop()
        Gui.activeDocument().activeView().fitAll()
        def capture():
            view = Gui.activeDocument().activeView()
            view.viewTop()
            view.fitAll()
            view.saveImage(str(WORK / "circuitry-preview.png"), 1600, 1200, "White")
            (WORK / "grid-opened.txt").write_text("432 signal + 4 provisional mounting holes displayed with coordinate labels.\n")
        QtCore.QTimer.singleShot(1200, capture)
    if changed:
        doc.save()
    print(f"432 addressable bores, 42 axis labels. Updated={changed}; {FILE}")


main()
