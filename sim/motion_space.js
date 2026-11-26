// Sesame motion space in JavaScript: a line-for-line port of sim/motion_space.py
// (decode, rules, project, gait) plus an SVG scene, for the interactive viewer.
// DATA comes from `python -m sim.motion_space --html` (motion_space.yaml, the
// manifest and the MJCF dimensions); tests/test_motion_space_js.py checks the
// port against Python with node.
"use strict";
function makeSpace(D) {
  const RAD = Math.PI / 180, AX = D.axes, S = D.space, C = S.center, K = D.dims;
  const SX = D.sx, SY = D.sy, P = D.pattern, HP = D.hipPattern;
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const add = (...v) => v.reduce((s, p) => [s[0] + p[0], s[1] + p[1], s[2] + p[2]]);
  const mul = (k, p) => [k * p[0], k * p[1], k * p[2]];
  const apply = (R, p) => [dot(R[0], p), dot(R[1], p), dot(R[2], p)];
  const wrap = x => { const t = 2 * Math.PI; return ((x + Math.PI) % t + t) % t - Math.PI; };

  function full(z) {
    const o = {};
    for (const a of AX) o[a] = z && z[a] != null ? +z[a] : C[a];
    return o;
  }
  function rot(pitch, roll) {
    const a = -pitch * RAD, b = -roll * RAD, ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b);
    const ry = [[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]], rx = [[1, 0, 0], [0, cb, -sb], [0, sb, cb]];
    return ry.map(r => [0, 1, 2].map(c => r[0] * rx[0][c] + r[1] * rx[1][c] + r[2] * rx[2][c]));
  }
  function femur(i, hipDeg) {
    const h = hipDeg * RAD;
    return [[SX[i] * K.HIP_X, SY[i] * K.HIP_Y, K.LEG_PLANE_DZ], [SX[i] * Math.sin(h), SY[i] * Math.cos(h), 0]];
  }
  function hipAngles(z) {
    z = full(z);
    return [0, 1, 2, 3].map(i => S.hip_center_deg + SX[i] * Object.keys(HP).reduce((s, a) => s + z[a] * P[HP[a]][i], 0));
  }
  function footIK(i, hipDeg, R, height, lift) {
    const [hip, u] = femur(i, hipDeg), r3 = R[2], ru = dot(r3, u), rz = r3[2];
    const side = Math.abs(dot(r3, [-u[1], u[0], 0])) * K.FOOT_HALF[0];
    const c0 = height + dot(r3, add(hip, mul(K.UPPER_LEN, u))) - side;
    let best = null;
    for (const edge of [1, -1]) {
      const a = K.FOOT_LEN * ru + edge * K.FOOT_HALF[2] * rz, b = -K.FOOT_LEN * rz + edge * K.FOOT_HALF[2] * ru;
      const rho = Math.hypot(a, b), k = lift - c0;
      if (Math.abs(k) > rho) continue;
      const base = Math.atan2(b, a), spread = Math.acos(k / rho);
      for (let phi of [base - spread, base + spread]) {
        phi = wrap(phi);
        if (Math.abs(phi) <= Math.PI / 2 + 1e-9 && (best === null || phi < best)) best = phi;
      }
    }
    return best === null ? null : best / RAD;
  }
  function decode(z) {
    z = full(z);
    const hips = hipAngles(z), R = rot(z.pitch, z.roll), feet = [];
    for (let i = 0; i < 4; i++) {
      const raised = P.diag[i] * z.lift > 0;
      const f = footIK(i, hips[i], R, z.height / 1000, raised ? Math.abs(z.lift) / 1000 : 0);
      if (f === null) return null;
      feet.push(f);
    }
    const q = {};
    D.legHip.forEach((n, i) => { q[n] = hips[i]; });
    D.legFoot.forEach((n, i) => { q[n] = feet[i]; });
    return { q, hips, feet };
  }
  function firmware(q) {
    return D.joints.map(j => Math.min(Math.max(q[j.name] * j.sign + D.neutral, j.limits_deg[0]), j.limits_deg[1]));
  }
  function legFrames(i, hipDeg, footDeg) {
    const [hip, u] = femur(i, hipDeg), f = footDeg * RAD;
    const d = add(mul(Math.cos(f), u), [0, 0, -Math.sin(f)]), n = add(mul(Math.sin(f), u), [0, 0, Math.cos(f)]);
    const knee = add(hip, mul(K.UPPER_LEN, u));
    return { hip, u, v: [-u[1], u[0], 0], knee, d, n, tip: add(knee, mul(K.FOOT_LEN, d)) };
  }
  function paw(i, hipDeg, footDeg, R) {
    const L = legFrames(i, hipDeg, footDeg);
    let low = null;
    for (const e of [1, -1]) for (const w of [1, -1]) {
      const p = add(L.tip, mul(e * K.FOOT_HALF[2], L.n), mul(w * K.FOOT_HALF[0], L.v));
      if (low === null || apply(R, p)[2] < apply(R, low)[2]) low = p;
    }
    return low;
  }
  function com(hips, feet) {
    let total = [0, 0, 0], mass = K.TORSO_MASS;
    for (let i = 0; i < 4; i++) {
      const L = legFrames(i, hips[i], feet[i]);
      total = add(total, mul(K.UPPER_MASS, add(L.hip, mul(K.UPPER_LEN / 2, L.u))),
                  mul(K.FOOT_MASS, add(L.knee, mul(K.FOOT_LEN / 2, L.d))));
      mass += K.UPPER_MASS + K.FOOT_MASS;
    }
    return mul(1 / mass, total);
  }
  function hull(pts) {  // monotone chain, counter-clockwise
    const p = pts.map(q => [q[0], q[1]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lo = [], hi = [];
    for (const q of p) { while (lo.length > 1 && cross(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
    for (const q of p.reverse()) { while (hi.length > 1 && cross(hi[hi.length - 2], hi[hi.length - 1], q) <= 0) hi.pop(); hi.push(q); }
    return lo.slice(0, -1).concat(hi.slice(0, -1));
  }
  function margin(pts, c) {  // signed distance of c inside the hull (xy)
    const h = hull(pts);
    if (h.length < 3) return -Infinity;
    let m = Infinity;
    for (let k = 0; k < h.length; k++) {
      const a = h[k], b = h[(k + 1) % h.length], len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      m = Math.min(m, ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / len);
    }
    return m;
  }
  const TORSO_CORNERS = [];
  for (const a of [-1, 1]) for (const b of [-1, 1]) for (const c of [-1, 1])
    TORSO_CORNERS.push([a * K.TORSO_HALF[0], b * K.TORSO_HALF[1], c * K.TORSO_HALF[2]]);
  function lowestBody(hips, R, height) {
    const pts = TORSO_CORNERS.slice();
    for (let i = 0; i < 4; i++) {
      const [hip, u] = femur(i, hips[i]), v = [-u[1], u[0], 0];
      for (const s of [0, K.UPPER_LEN]) for (const a of [-1, 1]) for (const c of [-1, 1])
        pts.push(add(hip, mul(s, u), mul(a * K.UPPER_HALF[0], v), [0, 0, c * K.UPPER_HALF[2]]));
    }
    return height + Math.min(...pts.map(p => apply(R, p)[2]));
  }
  function measures(z) {
    z = Object.assign(full(z), { lift: 0 });
    const dq = decode(z);
    if (!dq) return null;
    const { hips, feet } = dq, R = rot(z.pitch, z.roll);
    const paws = [0, 1, 2, 3].map(i => apply(R, paw(i, hips[i], feet[i], R)));
    return {
      support_margin_mm: 1000 * margin(paws, apply(R, com(hips, feet))),
      clearance_mm: 1000 * lowestBody(hips, R, z.height / 1000),
      foot_min_deg: Math.min(...feet),
      hip_pair_sum_min_deg: Math.min(hips[0] + hips[2], hips[1] + hips[3]),
    };
  }
  const RULES = ["support_margin_mm", "clearance_mm", "foot_min_deg", "hip_pair_sum_min_deg"];
  function violations(z) {
    const zf = full(z), dq = decode(zf);
    if (!dq) return ["unreachable"];
    const out = [];
    for (const j of D.joints) {
      const v = dq.q[j.name];
      if (v < j.internal_deg[0] - 1e-6 || v > j.internal_deg[1] + 1e-6) out.push("limit " + j.name);
    }
    if (Math.abs(zf.lift) > S.rules.lift_max_mm) out.push("lift");
    const got = measures(zf);
    if (!got) return out.concat(["unreachable"]);
    for (const k of RULES) if (got[k] < S.rules[k]) out.push(k);
    return out;
  }
  const feasible = z => violations(z).length === 0;
  function project(z, steps = 20) {
    const zf = full(z);
    if (feasible(zf)) return zf;
    const at = s => { const o = {}; for (const a of AX) o[a] = C[a] + s * (zf[a] - C[a]); return o; };
    let lo = 0, hi = 1;
    for (let k = 0; k < steps; k++) { const mid = (lo + hi) / 2; if (feasible(at(mid))) lo = mid; else hi = mid; }
    return at(lo);
  }
  function tiltLimit(h) {
    const ks = Object.keys(S.tilt_by_height).map(Number).sort((a, b) => a - b), t = S.tilt_by_height;
    if (h <= ks[0]) return t[ks[0]];
    for (let k = 1; k < ks.length; k++) if (h <= ks[k])
      return t[ks[k - 1]] + (h - ks[k - 1]) / (ks[k] - ks[k - 1]) * (t[ks[k]] - t[ks[k - 1]]);
    return t[ks[ks.length - 1]];
  }
  function withinBudget(z) {
    const b = S.budget; z = full(z);
    return Object.keys(HP).reduce((s, a) => s + Math.abs(z[a]), 0) <= b.hip_l1_deg
      && b.height_mm[0] <= z.height && z.height <= b.height_mm[1]
      && Math.abs(z.pitch) + Math.abs(z.roll) <= b.tilt_l1_fraction * tiltLimit(z.height)
      && Math.abs(z.lift) <= b.lift_mm;
  }
  function gait(t, hz, stride, steer, lift, pose) {
    const s = Math.sin(2 * Math.PI * hz * t), c = Math.sin(2 * Math.PI * (hz * t + 0.25));
    return Object.assign(full(pose), { stride: stride * s, spread: steer * s, lift: lift * c });
  }

  // ---- scene: world-frame boxes (m), floor at z = 0
  function box(center, ax, half) {  // ax: three unit axes
    const out = [];
    for (const a of [-1, 1]) for (const b of [-1, 1]) for (const c of [-1, 1])
      out.push(add(center, mul(a * half[0], ax[0]), mul(b * half[1], ax[1]), mul(c * half[2], ax[2])));
    return out;  // index = (a>0)*4 + (b>0)*2 + (c>0)
  }
  function scene(z) {
    z = full(z);
    const dq = decode(z);
    if (!dq) return null;
    const R = rot(z.pitch, z.roll), h = z.height / 1000;
    const W = p => add(apply(R, p), [0, 0, h]);
    const ex = [1, 0, 0], ey = [0, 1, 0], ez = [0, 0, 1];
    const boxes = [
      { part: "torso", pts: box([0, 0, 0], [ex, ey, ez], K.TORSO_HALF).map(W) },
      { part: "face", pts: box([K.TORSO_HALF[0], 0, 0.004], [ex, ey, ez], [0.002, 0.016, 0.011]).map(W) },
    ];
    const paws = [];
    for (let i = 0; i < 4; i++) {
      const L = legFrames(i, dq.hips[i], dq.feet[i]);
      boxes.push({ part: "upper", leg: i, pts: box(add(L.hip, mul(K.UPPER_LEN / 2, L.u)), [L.v, L.u, ez], K.UPPER_HALF).map(W) });
      boxes.push({ part: "lower", leg: i, pts: box(add(L.knee, mul(K.FOOT_LEN / 2, L.d)), [L.v, L.d, L.n],
                                                   [K.FOOT_HALF[0], K.FOOT_HALF[1], K.FOOT_HALF[2]]).map(W) });
      paws.push(W(paw(i, dq.hips[i], dq.feet[i], R)));
    }
    return { boxes, paws, com: W(com(dq.hips, dq.feet)), q: dq.q };
  }
  // ---- map: why each pose in a 2-D slice stands or not
  const ORDER = ["unreachable", "limit", "hip_pair_sum_min_deg", "clearance_mm", "support_margin_mm", "foot_min_deg", "lift"];
  function classify(z) {
    const v = violations(z);
    if (!v.length) return withinBudget(z) ? "budget" : "feasible";
    return ORDER.find(k => v.some(x => x === k || x.startsWith(k + " "))) || v[0];
  }
  function slice(z, ax, ay, n, xr, yr) {
    const zf = full(z), cls = [];
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
      const p = Object.assign({}, zf);
      p[ax] = xr[0] + (c + 0.5) / n * (xr[1] - xr[0]);
      p[ay] = yr[1] - (r + 0.5) / n * (yr[1] - yr[0]);
      cls.push(classify(p));
    }
    return cls;
  }

  // ---- SVG: orthographic camera (yaw, elevation in degrees), painter's algorithm
  const FACES = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]];
  function svgScene(sc, cam, opt) {
    opt = opt || {};
    const t = cam.yaw * RAD, f = cam.elev * RAD, k = cam.scale;
    const ct = Math.cos(t), st = Math.sin(t), cf = Math.cos(f), sf = Math.sin(f);
    const depthDir = [st * cf, ct * cf, -sf], light = [-0.4, 0.5, -0.75];
    const pr = p => { const x1 = ct * p[0] - st * p[1], y1 = st * p[0] + ct * p[1];
      return [x1 * k, -(p[2] * cf + y1 * sf) * k, y1 * cf - p[2] * sf]; };
    const pt = p => { const s = pr(p); return s[0].toFixed(1) + "," + s[1].toFixed(1); };
    const out = [];
    // floor grid in its own frame: world = Rot(yaw) * (floor - offset), so a gait
    // visibly travels (opt.floor.a/b: robot position on the floor, yaw: its heading)
    const fl = opt.floor || { a: 0, b: 0, yaw: 0 }, g = 0.02, span = 0.16;
    const cy = Math.cos(-fl.yaw), sy = Math.sin(-fl.yaw);
    const ma = ((fl.a % g) + g) % g, mb = ((fl.b % g) + g) % g;
    const fw = (u, v) => { u -= ma; v -= mb; return [cy * u - sy * v, sy * u + cy * v, 0]; };
    let grid = "";
    for (let a = -span; a <= span + 1e-9; a += g) {
      grid += "M" + pt(fw(a + g, -span)) + "L" + pt(fw(a + g, span + g));
      grid += "M" + pt(fw(-span, a + g)) + "L" + pt(fw(span + g, a + g));
    }
    out.push('<path d="' + grid + '" class="grid"/>');
    out.push('<path d="M' + pt([0.09, 0, 0]) + "L" + pt([0.14, 0, 0]) + '" class="fwd" marker-end="url(#arrow)"/>');
    const down = sc.paws.filter(p => p[2] < 0.0015);
    if (down.length >= 3) out.push('<polygon points="' + hull(down).map(p => pt([p[0], p[1], 0])).join(" ") + '" class="support"/>');
    for (const p of sc.paws) out.push('<circle cx="' + pt([p[0], p[1], 0]).replace(",", '" cy="') + '" r="4" class="' + (p[2] < 0.0015 ? "paw" : "pawup") + '"/>');
    // boxes
    const faces = [];
    for (const b of sc.boxes) {
      const center = mul(1 / 8, add(...b.pts));
      for (const fi of FACES) {
        const ps = fi.map(i => b.pts[i]), fc = mul(1 / 4, add(...ps));
        const n = add(fc, mul(-1, center)), nl = Math.hypot(...n), nn = mul(1 / nl, n);
        if (dot(nn, depthDir) >= 0) continue;
        faces.push({ d: pr(fc)[2], ps, b, shade: 0.6 + 0.4 * Math.max(0, -dot(nn, light)) });
      }
    }
    faces.sort((a, b) => b.d - a.d);
    const col = opt.colors || {};
    for (const fc of faces) {
      const key = fc.b.part === "upper" || fc.b.part === "lower" ? "leg" + fc.b.leg : fc.b.part;
      const c = (col[key] || [200, 200, 200]).map(v => Math.round(v * fc.shade));
      out.push('<polygon points="' + fc.ps.map(pt).join(" ") + '" fill="rgb(' + c.join(",") + ')" class="face"/>');
    }
    // centre of mass and its shadow
    const cm = sc.com, ok = opt.comOk !== false;
    out.push('<path d="M' + pt(cm) + "L" + pt([cm[0], cm[1], 0]) + '" class="comline"/>');
    out.push('<circle cx="' + pt([cm[0], cm[1], 0]).replace(",", '" cy="') + '" r="5" class="' + (ok ? "com" : "combad") + '"/>');
    return out.join("");
  }
  return { full, decode, firmware, measures, violations, feasible, project, tiltLimit, withinBudget,
           gait, scene, hull, margin, RULES, classify, slice, svgScene };
}
if (typeof module !== "undefined") module.exports = { makeSpace };
