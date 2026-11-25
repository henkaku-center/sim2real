"""Finite spoken-prompt plans; all device authority stays on the relay."""
from pathlib import Path
import sys

# Existing tools are executable modules with sibling imports.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
