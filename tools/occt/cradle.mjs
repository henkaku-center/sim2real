// Original parametric cradle; uses the existing licensed OCCT WASM kernel.
// No FreeCAD, jig code, generated imagery, physics or real fit claims.
import * as k from './kernel.mjs';

import {parameters} from './cradle-parameters.mjs';
export {DEFAULTS,PRESETS,parameters} from './cradle-parameters.mjs';

export async function buildCradle(input={}) {
  const p=parameters(input), oc=await k.initKernel();
  const started=performance.now();
  const length=p.length+2*p.clearance, inside=p.width+2*p.clearance, width=inside+2*p.wall;
  const plate=k.box(-length/2,-width/2,0,length,width,p.base);
  const rails=[-1,1].map(s=>k.box(-length/2,s>0?inside/2:-width/2,p.base,length,p.wall,p.railHeight));
  const centres=[]; const ears=[];
  for (const x of [-1,1]) for (const y of [-1,1]) {
    const cx=x*(length/2-10),cy=y*(width/2+4);
    centres.push([cx,cy]);
    ears.push(k.box(cx-6,y>0?width/2-2:-width/2-8,0,12,10,p.base));
  }
  let shape=k.fuseAll([plate,...rails,...ears]);
  const cylinder=(x,y,z,r,h)=>k.translated(new oc.BRepPrimAPI_MakeCylinder(r,h).Shape(),[x,y,z]);
  for (const [x,y] of centres) shape=k.cut(shape,cylinder(x,y,-1,1.7,p.base+2));
  const slots=[];
  for (const x of [-length/4,length/4]) {
    // Recess for webbing below the tray: supports can sit flat without trapping
    // a strap. The remaining floor thickness is base - 1 mm.
    shape=k.cut(shape,k.box(x-(p.strapWidth+0.6)/2,-width/2,-0.1,p.strapWidth+0.6,width,1.1));
    for (const y of [-1,1]) {
      const slot=k.box(x-(p.strapWidth+0.6)/2,y>0?inside/2-3:-inside/2+1,-1,p.strapWidth+0.6,2,p.base+2);
      slots.push(slot);shape=k.cut(shape,slot);
    }
  }
  shape=k.refine(shape);
  const valid=k.isValid(shape),solid_count=k.explore(shape,'SOLID').length;
  if (!valid || solid_count!==1) throw Error('Cradle must remain one valid solid');
  const battery=k.box(-p.length/2,-p.width/2,p.base,p.length,p.width,p.height);
  const overlap=Math.abs(k.volume(k.common(shape,battery)));
  if (overlap>1e-5) throw Error('Battery envelope intersects the cradle');
  for (const [x,y] of centres)
    if (Math.abs(k.volume(k.common(shape,cylinder(x,y,0,1.69,p.base))))>1e-5) throw Error('Mounting hole is blocked');
  for (const slot of slots)
    if (Math.abs(k.volume(k.common(shape,slot)))>1e-5) throw Error('Strap slot is blocked');
  const [lo,hi]=k.bounds(shape), outer=hi.map((v,i)=>v-lo[i]);
  const expected=[length,width+16,p.base+p.railHeight];
  if (outer.some((v,i)=>Math.abs(v-expected[i])>0.001)) throw Error('Outer envelope does not match the requested design');
  const mid=k.section(shape,2,p.base+p.railHeight/2);
  if (Math.abs(k.area(mid)-2*length*p.wall)>0.001) throw Error('Rail section does not preserve the requested wall thickness');
  return {shape,params:p,report:{status:'cad-only-unprinted',outer_mm:outer.map(v=>+v.toFixed(3)),volume_mm3:k.volume(shape),
    battery_overlap_mm3:overlap,valid,solid_count,build_ms:performance.now()-started,
    mount_centres_mm:centres,mount_hole_diameter_mm:3.4,strap_slot_width_mm:p.strapWidth+0.6,
    strap_slot_thickness_mm:2,strap_recess_depth_mm:1,floor_remaining_mm:p.base-1,
    mounting_scope:'Four external M3 clearance ears; no robot attachment, load or retention test. Two straps required; ends open.',
    units:'mm',kernel:'replicad-opencascadejs 1.2.1 / OCCT WASM'}};
}

export async function exportsFor(shape) {
  const oc=await k.initKernel();
  const step=k.writeStep(shape);
  // Explicit fine tessellation; export exactly the validated solid, not a
  // separate visual approximation. Each API build runs in its own process.
  const mesh=new oc.BRepMesh_IncrementalMesh(shape,0.08,false,0.3,false);
  mesh.Perform(new oc.Message_ProgressRange());
  const file='/cradle.stl',writer=new oc.StlAPI_Writer();
  if (!writer.Write(shape,file,new oc.Message_ProgressRange())) throw Error('STL export failed');
  const stl=oc.FS.readFile(file);oc.FS.unlink(file);
  if (!step.includes('ISO-10303-21') || !stl.length) throw Error('Empty CAD export');
  return {step,stl};
}
