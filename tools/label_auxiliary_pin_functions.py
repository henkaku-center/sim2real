"""Record instructor-confirmed OLED/power pin assignments on native objects."""
import FreeCAD as App

PINS={
    'M12':('OLED','GND','black'), 'M13':('OLED','VCC','red'),
    'M14':('OLED','SCL','green'), 'M15':('OLED','SDA','blue'),
    'X14':('Power','Switch V+ terminal 1',''), 'X15':('Power','Switch V+ terminal 2',''),
    'X16':('Power','Battery V+',''), 'X17':('Power','Battery GND',''),
}
doc=next(d for d in App.listDocuments().values() if d.FileName.endswith('/LM2596-comparison.FCStd'))
doc.openTransaction('Record instructor-confirmed OLED and switch/battery pinout')
try:
    for o in doc.Objects:
        if 'InstructionId' not in o.PropertiesList or not o.InstructionId.startswith('auxiliary.pin.'):continue
        purpose,signal,color=PINS[o.Address]
        for name,value in [('ConnectorPurpose',purpose),('Signal',signal),('CableColor',color),('PinoutEvidence','Instructor explicitly supplied low-to-high pin order, 2026-09-24')]:
            if name not in o.PropertiesList:o.addProperty('App::PropertyString',name,'Connection')
            setattr(o,name,value)
        o.Label=f'{o.Address} — {purpose}: {signal}'+(f' ({color})' if color else '')
    doc.recompute();doc.commitTransaction()
except Exception:
    doc.abortTransaction();raise
doc.save()
print('PASS: eight auxiliary pins labeled with instructor-confirmed functions.')
