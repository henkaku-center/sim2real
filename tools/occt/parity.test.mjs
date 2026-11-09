// Parity: the Node/OCCT variant stage against FreeCAD running v3_assembly_cad on the
// same normalized V3 references (reference-variant-geometry.json, freecad_reference.py).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as k from './kernel.mjs';
import { variantStage, extendX, assertConserved } from './variants.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const REF = ROOT + 'assets/printing/internal-frame-s3/reference-v3/';
const expected = JSON.parse(readFileSync(new URL('./reference-variant-geometry.json', import.meta.url)));
await k.initKernel();
const references = Object.fromEntries(['frame', 'bottom', 'head', 'lid'].map(name => [name, k.readStep(REF + name + '.step')]));

for (const [design, { params, parts }] of Object.entries(expected.designs)) {
  test(`${design}: Node/OCCT matches FreeCAD`, () => {
    const out = variantStage(references, params);
    for (const [name, want] of Object.entries(parts)) {
      const shape = out[name], v = k.volume(shape), [lo, hi] = k.bounds(shape);
      assert.ok(Math.abs(v - want.volume_mm3) <= 1e-5 * want.volume_mm3, `${name} volume ${v} vs FreeCAD ${want.volume_mm3}`);
      for (let i = 0; i < 3; i++) {
        assert.ok(Math.abs(lo[i] - want.bounds_mm[0][i]) < 1e-3 && Math.abs(hi[i] - want.bounds_mm[1][i]) < 1e-3,
          `${name} bounds ${JSON.stringify([lo, hi])} vs ${JSON.stringify(want.bounds_mm)}`);
      }
      assert.equal(k.isValid(shape), want.valid, `${name} validity`);
      assert.equal(k.explore(shape, 'SOLID').length, want.solids, `${name} solids`);
    }
  });
}

test('a lengthening cut through a non-prismatic face is refused', () => {
  assert.throws(() => extendX(references.frame, 30.5, 10), /non-prismatic|Volume not conserved|Invalid/);
});

test('a valid result that lost material is rejected by the volume check', () => {
  // A valid solid is not enough: lengthening must add exactly section area × length.
  const section = k.section(references.bottom, 0, -3.5), added = k.area(section) * 52;
  const missing = k.translated(references.bottom, [0, 0, 0]);
  assert.throws(() => assertConserved(missing, references.bottom, added, 0, 0), /Volume not conserved/);
});
