// Prompted design variants on the V3 references: widen across Y, lengthen along X,
// transplant a servo bay band. Ports of v3_assembly_cad.stretch_y / extend_x /
// transplant_bays with the same prismatic-cut and volume-conservation checks.
import * as k from './kernel.mjs';

function assertPrismatic(shape, axis, planes) {
  for (const face of k.explore(shape, 'FACE')) {
    const [lo, hi] = k.bounds(face);
    if (hi[axis] - lo[axis] < 1e-6 || !planes.some(c => lo[axis] < c && c < hi[axis])) continue;
    const s = k.surface(face);
    const ok = s.kind === 'plane' && Math.abs(s.axis[axis]) < 1e-9 || s.kind === 'cylinder' && Math.abs(Math.abs(s.axis[axis]) - 1) < 1e-9;
    if (!ok) throw Error(`Cut plane crosses a non-prismatic face (axis ${axis}, planes ${planes})`);
  }
}

// Volume must grow by exactly the bridged section(s); a valid but wrong result is rejected.
export function assertConserved(result, shape, added, axis, length) {
  const dv = k.volume(result) - k.volume(shape) - added;
  if (!k.isValid(result)) throw Error('Invalid result solid');
  if (Math.abs(dv) >= 1e-3 * k.volume(shape)) throw Error(`Volume not conserved: off by ${dv.toFixed(3)} mm³`);
  const [a0, a1] = k.bounds(shape), [b0, b1] = k.bounds(result);
  if (Math.abs((b1[axis] - b0[axis]) - (a1[axis] - a0[axis]) - length) > 1e-6) throw Error('Extent did not grow by the requested length');
}

export function stretchY(shape, plane, widen, refine = true) {
  assertPrismatic(shape, 1, [-plane, plane]);
  const half = widen / 2, big = 400;
  const pieces = [k.common(shape, k.box(-big / 2, -plane, -big / 2, big, 2 * plane, big))];
  let added = 0;
  for (const side of [-1, 1]) {
    const outer = k.common(shape, k.box(-big / 2, side > 0 ? plane : -plane - big, -big / 2, big, big, big));
    pieces.push(k.translated(outer, [0, side * half, 0]));
    const section = k.section(shape, 1, side * plane);
    added += k.area(section) * half;
    pieces.push(k.translated(k.prism(section, [0, half, 0]), [0, side > 0 ? 0 : -half, 0]));
  }
  let result = k.fuseAll(pieces);
  // Keep seam faces when another cut follows; the last operation refines.
  if (refine) result = k.refine(result);
  result = k.singleSolid(result);
  assertConserved(result, shape, added, 1, widen);
  return result;
}

export function extendX(shape, plane, length) {
  assertPrismatic(shape, 0, [plane]);
  const big = 600;
  const rear = k.common(shape, k.box(plane - big, -big / 2, -big / 2, big, big, big));
  const front = k.translated(k.common(shape, k.box(plane, -big / 2, -big / 2, big, big, big)), [length, 0, 0]);
  const section = k.section(shape, 0, plane);
  const result = k.singleSolid(k.refine(k.fuseAll([rear, k.prism(section, [length, 0, 0]), front])));
  assertConserved(result, shape, k.area(section) * length, 0, length);
  return result;
}

export function transplantBays(source, target, [lo, hi], shift, yLimit) {
  const big = 600;
  const band = (x0, x1, side) => k.box(x0, side > 0 ? yLimit : -yLimit - big, -big / 2, x1 - x0, big, big);
  const blocks = [-1, 1].map(side => k.translated(k.common(source, band(lo, hi, side)), [shift, 0, 0]));
  let result = target;
  for (const side of [-1, 1]) result = k.cut(result, band(lo + shift, hi + shift, side));
  result = k.refine(k.fuseAll([result, ...blocks]));
  const solids = k.explore(result, 'SOLID');
  if (solids.length !== 1) throw Error(`Transplanted bays are not joined to the body (${solids.length} solids)`);
  const shape = k.singleSolid(result);
  if (!k.isValid(shape)) throw Error('Transplanted frame is not a valid solid');
  return { shape, blocks };
}

// The variant stage of v3_assembly_cad.build(), on loaded references {frame, bottom, head, lid}.
export function variantStage(ref, variant) {
  ref = { ...ref };
  const h = (variant?.widen_mm ?? 0) / 2, legs = variant?.middle_legs;
  if (h) for (const name of ['frame', 'bottom', 'head', 'lid'])
    ref[name] = stretchY(ref[name], variant.stretch_plane_y_mm, variant.widen_mm, ['head', 'lid'].includes(name) && !legs);
  if (legs) {
    for (const name of ['frame', 'bottom']) {
      const extended = extendX(ref[name], legs.body_plane_x_mm, legs.lengthen_mm);
      ref[name] = transplantBays(ref[name], extended, legs.bay_x_range_mm, legs.bay_shift_mm, legs.bay_y_limit_mm + h).shape;
    }
    for (const name of ['head', 'lid']) ref[name] = extendX(ref[name], legs.head_plane_x_mm, legs.lengthen_mm);
  }
  return ref;
}
