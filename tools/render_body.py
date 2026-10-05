"""Deterministic CPU orthographic review renders (Pillow, no GUI/GPU/display)."""
import json
import gzip
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def render(scene, path, title, direction=(1.5,-2,1.4), exploded=False, cutaway=False):
    look = np.array(direction,dtype=float)
    look /= np.linalg.norm(look)
    right = np.cross([0,0,1],look)
    if np.linalg.norm(right)<.01:
        right = np.array([1.,0,0])
    right /= np.linalg.norm(right)
    up = np.cross(look,right)
    basis = np.array([right,up,look])
    objects = []
    for item in scene:
        if item['kind'] in ['service','wire','reference']:
            continue
        if cutaway and item['id'] in ['body.face-cover']:
            continue
        points = np.array(item['vertices'],dtype=float)
        if not len(points):
            continue
        if exploded:
            if item['id']=='body.face-cover' or item['kind'] in ['oled','switch']:
                points += [0,0,75]
            elif item['kind']=='electronics':
                points += [0,0,40]
            elif item['id']=='body.battery-drawer' or item['id'].startswith('battery'):
                points += [75,0,0]
        objects.append((points@basis.T,np.array(item['faces']),item['color']))
    all_pts = np.vstack([o[0] for o in objects])
    lo,hi = all_pts.min(0),all_pts.max(0)
    width,height = 1280,1000
    scale = min((width-180)/(hi[0]-lo[0]),(height-200)/(hi[1]-lo[1]))
    triangles = []
    for points,faces,color in objects:
        tri = points[faces]
        n = np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        norms = np.linalg.norm(n,axis=1)
        keep = (norms>1e-9) & (n[:,2]>0)  # closed solid back-face culling
        tri,n,norms = tri[keep],n[keep],norms[keep]
        n /= norms[:,None]
        shade = .55+.45*np.maximum(0,n@np.array([-.25,.4,.88]))
        rgb = np.clip(np.asarray(color[:3])[None,:]*shade[:,None]*255,0,255).astype(int)
        xy = np.stack(((tri[:,:,0]-(lo[0]+hi[0])/2)*scale+width/2,
                      -(tri[:,:,1]-(lo[1]+hi[1])/2)*scale+height/2+20),axis=2)
        triangles.extend(zip(tri[:,:,2],xy,rgb))
    pixels = np.full((height,width,3),[239,242,245],dtype=np.uint8)
    depth = np.full((height,width),-np.inf,dtype=np.float32)
    # Real z-buffer: sorting triangles by mean depth breaks broad planar faces,
    # producing misleading stripes/occlusion in CAD exploded views.
    for zz,points,color in triangles:
        low = np.maximum(np.floor(points.min(axis=0)).astype(int),[0,0])
        high = np.minimum(np.ceil(points.max(axis=0)).astype(int),[width-1,height-1])
        if np.any(high<low):
            continue
        a,b,c=points
        denom=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(denom)<1e-9:
            continue
        xx,yy=np.meshgrid(np.arange(low[0],high[0]+1)+.5,np.arange(low[1],high[1]+1)+.5)
        u=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/denom
        v=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/denom
        ww=1-u-v
        z=u*zz[0]+v*zz[1]+ww*zz[2]
        region=depth[low[1]:high[1]+1,low[0]:high[0]+1]
        mask=(u>=-1e-6)&(v>=-1e-6)&(ww>=-1e-6)&(z>region)
        region[mask]=z[mask]
        pixels[low[1]:high[1]+1,low[0]:high[0]+1][mask]=color
    image=Image.fromarray(pixels)
    draw=ImageDraw.Draw(image)
    draw.text((35,25),title,fill='#142b3d',font_size=27)
    draw.text((35,65),'S3 body v1 - DRAFT / NEEDS-HARDWARE - mm - see report.json',fill='#934500',font_size=19)
    draw.text((35,height-43),'Cream: face cover  |  Blue: carrier tray  |  Gold: battery drawer / risers  |  Red: frozen legs',fill='#344858',font_size=16)
    draw.text((35,height-23),'Black blocks: nominal servo envelopes; purchased-variant fit remains unverified.',fill='#344858',font_size=14)
    image.save(path)


def render_review(out,report):
    out = Path(out)
    scene = json.loads(gzip.decompress((out/'scene.json.gz').read_bytes()))
    images = [
        ('assembled.png','Assembled preview',(1.5,-2,1.4),False,False),
        ('front.png','Face / battery drawer / USB access',(1,0,.15),False,False),
        ('rear.png','Rear switch access',(-1,.2,.25),False,False),
        ('top-open.png','Cover removed: exact native electronics',(.2,-.3,1),False,True),
        ('exploded.png','Exploded assembly',(1.5,-2,1.4),True,False),
    ]
    for filename,title,direction,exploded,cutaway in images:
        render(scene,out/filename,title,direction,exploded,cutaway)
    # A contact sheet animates representative single-joint positions using the
    # same frozen templates and canonical axes as the numerical sweep.
    animation = json.loads((out/'rom-animation.json').read_text())
    if animation['kinematics']:
        leg = animation['kinematics'][0]
        frames=[]
        import trimesh
        for q in np.linspace(*leg['soft_ranges_internal_deg'][0],7):
            modified=[]
            transform = trimesh.transformations.rotation_matrix(np.radians(q),leg['hip_axis'],leg['hip_center_mm'])
            for item in scene:
                if item['kind'] not in ['body','leg','servo','horn','oled']:
                    continue  # sealed internal electronics add no motion-review information
                row=dict(item)
                if item['id'].startswith('leg.'+leg['name']+'.'):
                    row['vertices']=trimesh.transform_points(np.asarray(item['vertices']),transform).tolist()
                modified.append(row)
            dest=out/'rom-current.png'
            render(modified,dest,f"ROM {leg['hip_joint']} = {q:.1f} deg",(1.5,-2,1.4))
            frames.append(Image.open(dest).copy().resize((640,500)))
        frames[0].save(out/'rom-preview.gif',save_all=True,append_images=frames[1:],duration=220,loop=0)
        sheet=Image.new('RGB',(640*4,500*2),'white')
        for i,frame in enumerate(frames):
            sheet.paste(frame,((i%4)*640,(i//4)*500))
        sheet.save(out/'rom-sweep.png')
        (out/'rom-current.png').unlink()
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Sesame body v1 review</title>
<style>body{font:16px system-ui;margin:2em;background:#eff2f5}img{max-width:95%;display:block}pre{white-space:pre-wrap}h1{color:#934500}</style>
<h1>DRAFT: '''+report['status']+'''</h1><p>Not print-approved. Read <a href="report.json">the numerical report</a> and <a href="assembly.json">assembly bindings</a>.</p><pre>'''+json.dumps(report['summary'],indent=2)+'''</pre>'''
    for filename,title,*_ in images:
        html+=f'<h2>{title}</h2><img src="{filename}" alt="{title}">'
    html+='<h2>Representative hip sweep (all joints checked numerically)</h2><img src="rom-preview.gif" alt="Sampled leg sweep">'
    (out/'index.html').write_text(html+'\n')
