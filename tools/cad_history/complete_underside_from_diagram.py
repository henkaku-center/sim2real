# Historical construction recipe; open the current assembly with tools/open_cad.FCMacro.
"""Append the three links resolved by the instructor's top-view diagram."""
from pathlib import Path
import runpy

module=runpy.run_path(str(Path(__file__).with_name('add_carrier_underside_wires.py')),run_name='underside_helpers')
module['main']([['B10','B11'],['M15','M18'],['X15','X16']],continuation=True)
