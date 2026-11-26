"""Turn a plain 3MF plate (make_plates.py) into a Bambu Studio project with print settings and per-object overrides.

    uv run python -I bambu/scripts/make_bambu_project.py SETTINGS.config PLAIN.3mf OUT.3mf [object:key=value ...]

SETTINGS.config is a Bambu Studio project_settings.config (bambu/slicer/).  Overrides become the object's own
settings, e.g. "shell-dome:enable_support=0".  Check the result headless with
    /Applications/BambuStudio.app/Contents/MacOS/BambuStudio --slice 0 --outputdir OUTDIR OUT.3mf
(exit 0 and no "gcode path conflicts" in the log).
"""
import re, sys, uuid, zipfile
import numpy as np

tpl, plain, out = sys.argv[1:4]
over = {}
for a in sys.argv[4:]:
    n, kv = a.split(":", 1); k, v = kv.split("=", 1); over.setdefault(n, {})[k] = v
s = zipfile.ZipFile(plain).read("3D/3dmodel.model").decode()
objs = []
for m in re.finditer(r'<object id="\d+" name="([^"]+)".*?<vertices>(.*?)</vertices><triangles>(.*?)</triangles>', s):
    v = np.array(re.findall(r'x="([^"]+)" y="([^"]+)" z="([^"]+)"', m.group(2)), float)
    f = re.findall(r'v1="(\d+)" v2="(\d+)" v3="(\d+)"', m.group(3))
    objs.append((m.group(1), v, f))
settings = open(tpl, 'rb').read()
NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"')
res, build, rels, cfg_obj, inst, asm = [], [], [], [], [], []
files = {}
for i, (name, v, f) in enumerate(objs):
    oid, cid = 2 * i + 2, 2 * i + 1
    c = (v.min(0) + v.max(0)) / 2
    loc = v - c
    vs = "".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in loc)
    ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{d}"/>' for a, b, d in f)
    path = f"3D/Objects/object_{cid}.model"
    files[path] = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>'
                   f'<metadata name="BambuStudio:3mfVersion">1</metadata><resources><object id="{cid}" p:UUID="{uuid.uuid4()}" type="model">'
                   f'<mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object></resources><build/></model>')
    tr = f"1 0 0 0 1 0 0 0 1 {c[0]:.5f} {c[1]:.5f} {c[2]:.5f}"
    res.append(f'<object id="{oid}" p:UUID="{uuid.uuid4()}" type="model"><components><component p:path="/{path}" objectid="{cid}" '
               f'p:UUID="{uuid.uuid4()}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/></components></object>')
    build.append(f'<item objectid="{oid}" p:UUID="{uuid.uuid4()}" transform="{tr}" printable="1"/>')
    rels.append(f'<Relationship Target="/{path}" Id="rel-{cid}" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>')
    extra = "".join(f'<metadata key="{k}" value="{val}"/>' for k, val in over.get(name, {}).items())
    cfg_obj.append(f'<object id="{oid}"><metadata key="name" value="{name}"/><metadata key="extruder" value="1"/>{extra}'
                   f'<part id="1" subtype="normal_part"><metadata key="name" value="{name}"/>'
                   f'<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/></part></object>')
    inst.append(f'<model_instance><metadata key="object_id" value="{oid}"/><metadata key="instance_id" value="0"/>'
                f'<metadata key="identify_id" value="{100 + i}"/></model_instance>')
    asm.append(f'<assemble_item object_id="{oid}" instance_id="0" transform="{tr}" offset="0 0 0" />')
files["3D/3dmodel.model"] = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>'
                             '<metadata name="Application">BambuStudio-02.08.02.61</metadata><metadata name="BambuStudio:3mfVersion">1</metadata>'
                             f'<resources>{"".join(res)}</resources><build>{"".join(build)}</build></model>')
files["3D/_rels/3dmodel.model.rels"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                        + "".join(rels) + "</Relationships>")
files["Metadata/model_settings.config"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>' + "".join(cfg_obj) +
                                           '<plate><metadata key="plater_id" value="1"/><metadata key="plater_name" value=""/>'
                                           '<metadata key="locked" value="false"/>' + "".join(inst) + '</plate><assemble>' + "".join(asm) + '</assemble></config>')
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/'
               'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
               'relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
               '<Default Extension="png" ContentType="image/png"/><Default Extension="gcode" ContentType="text/x.gcode"/></Types>')
    z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/'
               'package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel-1" '
               'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    z.writestr("Metadata/project_settings.config", settings)
    for n, d in files.items():
        z.writestr(n, d)
