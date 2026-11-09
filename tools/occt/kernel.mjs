// Minimal OpenCascade kernel for the CAD pipeline, without FreeCAD.
// replicad-opencascadejs (OCCT built to WebAssembly, LGPL-2.1) in Node or a browser.
// Each helper mirrors the FreeCAD Part call it replaces; units are millimetres.
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let oc = null;

export async function initKernel() {
  if (oc) return oc;
  // OCCT_WASM_JS may point at another replicad_single.js build (with its .wasm beside it).
  const entry = process.env.OCCT_WASM_JS || require.resolve('replicad-opencascadejs');
  const { default: init } = await import(entry.replace(/\.cjs$/, '.js'));
  oc = await init({ wasmBinary: readFileSync(entry.replace(/\.c?js$/, '.wasm')), print: () => {}, printErr: () => {} });
  return oc;
}
const K = () => { if (!oc) throw Error('Call initKernel() first'); return oc; };
const progress = () => new (K().Message_ProgressRange)();
const pnt = (x, y, z) => new (K().gp_Pnt)(x, y, z);
const vec = ([x, y, z]) => new (K().gp_Vec)(x, y, z);

export function readStep(path) {
  const o = K(), name = `/in_${Math.random().toString(36).slice(2)}.step`;
  o.FS.writeFile(name, readFileSync(path));
  const reader = new o.STEPControl_Reader();
  if (reader.ReadFile(name) !== o.IFSelect_ReturnStatus.IFSelect_RetDone) throw Error('STEP read failed: ' + path);
  reader.TransferRoots(progress());
  const shape = reader.OneShape();
  o.FS.unlink(name);
  return shape;
}

export function writeStep(shape) {
  const o = K(), name = `/out_${Math.random().toString(36).slice(2)}.step`, writer = new o.STEPControl_Writer();
  writer.Transfer(shape, o.STEPControl_StepModelType.STEPControl_AsIs, true, progress());
  writer.Write(name);
  const text = o.FS.readFile(name, { encoding: 'utf8' });
  o.FS.unlink(name);
  return text;
}

export const box = (x, y, z, dx, dy, dz) => new (K().BRepPrimAPI_MakeBox)(pnt(x, y, z), dx, dy, dz).Shape();

function boolean(Op, a, b) {
  const op = new Op(a, b, progress());
  op.Build(progress());
  if (!op.IsDone()) throw Error('Boolean failed');
  return op.Shape();
}
export const common = (a, b) => boolean(K().BRepAlgoAPI_Common, a, b);
export const cut = (a, b) => boolean(K().BRepAlgoAPI_Cut, a, b);
export const fuse = (a, b) => boolean(K().BRepAlgoAPI_Fuse, a, b);
// FreeCAD multiFuse fuses all arguments in one operation; sequential fuses give the
// same solid here (checked by volume, validity and solid count in the tests).
export const fuseAll = shapes => shapes.slice(1).reduce((acc, s) => fuse(acc, s), shapes[0]);

export function translated(shape, offset) {
  const t = new (K().gp_Trsf)();
  t.SetTranslation(vec(offset));
  return new (K().BRepBuilderAPI_Transform)(shape, t, true, false).Shape();
}

// The planar cross-section of a solid as faces (holes kept): FreeCAD's
// makeFace(shape.slice(axis, value), FaceMakerBullseye).
export function section(shape, axis, value) {
  const o = K(), origin = [0, 0, 0], normal = [0, 0, 0];
  origin[axis] = value; normal[axis] = 1;
  const plane = new o.gp_Pln(pnt(...origin), new o.gp_Dir(...normal));
  return common(shape, new o.BRepBuilderAPI_MakeFace(plane, -1000, 1000, -1000, 1000).Face());
}

export const prism = (shape, direction) => new (K().BRepPrimAPI_MakePrism)(shape, vec(direction), false, true).Shape();

// FreeCAD removeSplitter(): merge coplanar/cocylindrical faces across seams.
export function refine(shape) {
  const u = new (K().ShapeUpgrade_UnifySameDomain)(shape, true, true, false);
  u.Build();
  return u.Shape();
}

export function volume(shape) {
  const g = new (K().GProp_GProps)();
  K().BRepGProp.VolumeProperties(shape, g, false, false, false);
  return g.Mass();
}
export function area(shape) {
  const g = new (K().GProp_GProps)();
  K().BRepGProp.SurfaceProperties(shape, g, false, false);
  return g.Mass();
}
export function bounds(shape) {
  const o = K(), b = new o.Bnd_Box();
  // FreeCAD's Shape.BoundBox: BRepBndLib::Add with triangulation, zero gap (looser than optimal on splines).
  o.BRepBndLib.Add(shape, b, true);
  b.SetGap(0);
  const lo = b.CornerMin(), hi = b.CornerMax();
  return [[lo.X(), lo.Y(), lo.Z()], [hi.X(), hi.Y(), hi.Z()]];
}
export const isValid = shape => new (K().BRepCheck_Analyzer)(shape, true, false).IsValid();

export function explore(shape, kind) {
  const o = K(), out = [];
  const e = new o.TopExp_Explorer(shape, o.TopAbs_ShapeEnum['TopAbs_' + kind], o.TopAbs_ShapeEnum.TopAbs_SHAPE);
  for (; e.More(); e.Next()) out.push(o.TopoDS[kind === 'SOLID' ? 'Solid' : kind === 'SHELL' ? 'Shell' : kind === 'FACE' ? 'Face' : 'Edge'](e.Current()));
  return out;
}

// FreeCAD: makeSolid(largest shell) when a fuse does not yield exactly one solid.
export function singleSolid(shape) {
  const solids = explore(shape, 'SOLID');
  const shells = explore(shape, 'SHELL');
  if (solids.length === 1 && shells.length === 1) return solids[0];
  // This OCCT build can leave zero-volume internal sheets at translation seams
  // inside one solid (FreeCAD/OCCT 7.8 removes them); keep only enclosing shells.
  if (solids.length === 1) {
    const enclosing = shells.filter(sh => Math.abs(volume(new (K().BRepBuilderAPI_MakeSolid)(sh).Solid())) > 1e-6);
    if (enclosing.length !== 1) return solids[0];
    return new (K().BRepBuilderAPI_MakeSolid)(enclosing[0]).Solid();
  }
  const largest = shells.reduce((a, b) => (area(a) >= area(b) ? a : b));
  return new (K().BRepBuilderAPI_MakeSolid)(largest).Solid();
}

// Surface kind and axis of a face, for the prismatic-cut checks.
export function surface(face) {
  const o = K(), s = new o.BRepAdaptor_Surface(face, true), t = s.GetType(), T = o.GeomAbs_SurfaceType;
  const dir = d => [d.X(), d.Y(), d.Z()];
  if (t === T.GeomAbs_Plane) return { kind: 'plane', axis: dir(s.Plane().Axis().Direction()) };
  if (t === T.GeomAbs_Cylinder) return { kind: 'cylinder', axis: dir(s.Cylinder().Axis().Direction()) };
  return { kind: 'other' };
}
