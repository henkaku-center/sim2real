import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const $ = (id) => document.getElementById(id);
const form = $('parameters');
const keys = ['length', 'width', 'height', 'clearance', 'wall', 'base', 'railHeight', 'strapWidth'];
const defaults = { length: 51, width: 28, height: 14, clearance: .5, wall: 2, base: 2.4, railHeight: 6, strapWidth: 10 };
let revision = 0, requestToken = 0, dirty = true, built = null, controller = null;
let viewer = null;
const rawInputs = () => JSON.stringify(keys.map((key) => form.elements.namedItem(key).value));
function paramsFromInputs() {
  const params = {};
  for (const key of keys) {
    const input = form.elements.namedItem(key);
    if (!input.value.trim() || !Number.isFinite(input.valueAsNumber)) throw new Error(`Enter a number for ${key}.`);
    params[key] = input.valueAsNumber;
  }
  return params; // Geometric ranges and combinations are validated by the server.
}
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function downloadsEnabled(enabled) {
  $('download-step').disabled = !enabled;
  $('download-stl').disabled = !enabled;
}
function invalidate() {
  revision++;
  requestToken++;
  controller?.abort();
  dirty = true;
  downloadsEnabled(false);
  $('build').disabled = false;
  $('build').firstChild.textContent = 'Build cradle ';
  $('model-state').textContent = built ? 'Previous build · inputs changed' : 'Inputs not built';
  $('build-state').textContent = 'Inputs changed. Build again to update the model and downloads.';
  $('share-state').textContent = '';
}
function setInputs(params) {
  for (const key of keys) form.elements.namedItem(key).value = params[key] ?? defaults[key];
  invalidate();
}
form.addEventListener('input', () => { invalidate(); $('preset').value = ''; $('preset-note').textContent = 'Custom sizing. Measure your own battery, including any protrusions.'; });

// Binary STL headers can begin with “solid”; exact byte layout takes precedence.
function parseSTL(bytes) {
  let positions;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const count = bytes.length >= 84 ? view.getUint32(80, true) : 0;
  if (count > 0 && 84 + count * 50 === bytes.length) {
    positions = new Float32Array(count * 9);
    for (let triangle = 0; triangle < count; triangle++) {
      for (let axis = 0; axis < 9; axis++) positions[triangle * 9 + axis] = view.getFloat32(84 + triangle * 50 + 12 + axis * 4, true);
    }
  } else {
    const text = new TextDecoder().decode(bytes);
    if (!/^\s*solid\b/i.test(text) || !/endsolid\b/i.test(text)) throw new Error('The server returned an unreadable STL file.');
    const vertices = [];
    const number = '([+-]?(?:\\d+\\.?\\d*|\\.\\d+)(?:[eE][+-]?\\d+)?)';
    const pattern = new RegExp(`\\bvertex\\s+${number}\\s+${number}\\s+${number}`, 'gi');
    for (const match of text.matchAll(pattern)) vertices.push(Number(match[1]), Number(match[2]), Number(match[3]));
    if (!vertices.length || vertices.length % 9) throw new Error('The server returned incomplete STL triangles.');
    positions = new Float32Array(vertices);
  }
  if (!positions.every(Number.isFinite)) throw new Error('The STL contains non-finite coordinates.');
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function initViewer() {
  const host = $('viewport');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#eeece6');
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  host.appendChild(renderer.domElement);
  const camera = new THREE.PerspectiveCamera(35, 1, .1, 10000);
  camera.up.set(0, 0, 1);
  camera.position.set(85, -105, 100);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.target.set(0, 0, 8);
  controls.update();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8b8881, 2.4));
  const light = new THREE.DirectionalLight(0xffffff, 3);
  light.position.set(40, -65, 120);
  scene.add(light);
  const fill = new THREE.DirectionalLight(0xe2e8fa, 1.5);
  fill.position.set(-70, 50, 45);
  scene.add(fill);
  let model = null, envelope = null, bounds = null, userMoved = false;
  const render = () => renderer.render(scene, camera);
  controls.addEventListener('start', () => { userMoved = true; });
  controls.addEventListener('change', render);
  function fit(top = false) {
    if (!bounds) return;
    const sphere = bounds.getBoundingSphere(new THREE.Sphere());
    const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
    const angle = Math.min(halfFov, Math.atan(Math.tan(halfFov) * camera.aspect));
    const distance = sphere.radius / Math.sin(angle) * 1.22;
    const direction = top ? new THREE.Vector3(0, -.0001, 1) : new THREE.Vector3(1, -1.3, 1.15).normalize();
    camera.position.copy(sphere.center).addScaledVector(direction, distance);
    camera.near = Math.max(.01, sphere.radius / 1000);
    camera.far = Math.max(10000, distance * 20);
    camera.updateProjectionMatrix();
    controls.target.copy(sphere.center);
    controls.update();
    render();
  }
  function dispose(object) { if (object) { scene.remove(object); object.geometry.dispose(); object.material.dispose(); } }
  new ResizeObserver(() => {
    const width = host.clientWidth, height = host.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    if (!userMoved) fit();
    render();
  }).observe(host);
  $('fit').addEventListener('click', () => { userMoved = false; fit(); });
  $('top').addEventListener('click', () => { userMoved = true; fit(true); });
  $('battery-visible').addEventListener('change', () => { if (envelope) envelope.visible = $('battery-visible').checked; render(); });
  render();
  return {
    replace(geometry, params) {
      const nextModel = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0x293746, roughness: .58, metalness: .12 }));
      const nextEnvelope = new THREE.Mesh(new THREE.BoxGeometry(params.length, params.width, params.height), new THREE.MeshStandardMaterial({ color: 0xd79a40, transparent: true, opacity: .3, depthWrite: false, roughness: .6 }));
      nextEnvelope.position.z = params.base + params.height / 2;
      nextEnvelope.visible = $('battery-visible').checked;
      dispose(model); dispose(envelope);
      model = nextModel; envelope = nextEnvelope;
      scene.add(model, envelope);
      bounds = new THREE.Box3().setFromObject(model).union(new THREE.Box3().setFromObject(envelope));
      if (!userMoved) fit();
      render();
    },
  };
}

function revokeDownloads() {
  if (built) { URL.revokeObjectURL(built.stlURL); URL.revokeObjectURL(built.stepURL); }
}
const fmt = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  invalidate();
  error('');
  const token = ++requestToken, inputRevision = revision, snapshot = rawInputs();
  let geometry = null;
  try {
    const params = paramsFromInputs();
    if (!viewer) throw new Error('The 3D viewer is unavailable. Enable WebGL and reload to build.');
    controller = new AbortController();
    $('build').disabled = true;
    $('build').firstChild.textContent = 'Building… ';
    $('build-state').textContent = 'Building the solid model…';
    $('model-state').textContent = built ? 'Building · previous model shown' : 'Building…';
    const response = await fetch('api/build', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params), signal: controller.signal });
    const data = await response.json();
    if (token !== requestToken || revision !== inputRevision || snapshot !== rawInputs()) return;
    if (!response.ok || data.error) throw new Error(data.error || `Build failed (${response.status}).`);
    if (!data.params || keys.some((key) => !Number.isFinite(data.params[key]) || data.params[key] !== params[key])) throw new Error('The server returned different parameters. Build again.');
    if (!data.report || !data.report.valid || data.report.status !== 'cad-only-unprinted' || typeof data.step !== 'string' || !data.step.length) throw new Error('The server did not return a valid CAD prototype.');
    const bytes = Uint8Array.from(atob(data.stl_base64), (character) => character.charCodeAt(0));
    geometry = parseSTL(bytes);
    const report = data.report;
    const outer = report.outer_mm.map(fmt).join(' × ') + ' mm';
    const mounts = report.mount_centres_mm.map(([x, y]) => `(${fmt(x)}, ${fmt(y)})`).join(', ');
    viewer.replace(geometry, params);
    geometry = null; // Now owned by the viewer.
    revokeDownloads();
    built = { params, snapshot, stlURL: URL.createObjectURL(new Blob([bytes], { type: 'model/stl' })), stepURL: URL.createObjectURL(new Blob([data.step], { type: 'application/step' })) };
    dirty = false;
    downloadsEnabled(true);
    $('outer').textContent = outer;
    $('volume').textContent = `${fmt(report.volume_mm3)} mm³`;
    $('duration').textContent = `${fmt(report.build_ms / 1000)} s`;
    $('measurements').hidden = false;
    $('mount-pattern').textContent = `M3 holes: ${fmt(report.mount_hole_diameter_mm)} mm diameter. Centres (X, Y) in mm: ${mounts}. Pitch follows the cradle dimensions; it is not a verified robot mounting pattern.`;
    $('build-state').textContent = 'Model matches these inputs. STEP and STL are ready.';
    $('model-state').textContent = 'CAD prototype · current';
    writeHash(params);
  } catch (cause) {
    geometry?.dispose();
    if (token !== requestToken || cause.name === 'AbortError') return;
    dirty = true;
    downloadsEnabled(false);
    error(cause.message || 'Could not build the cradle. Please try again.');
    $('build-state').textContent = 'Build failed. Correct the inputs or try again. Downloads are disabled.';
    $('model-state').textContent = built ? 'Previous build · not current' : 'No model built';
  } finally {
    if (token === requestToken) { $('build').disabled = false; $('build').firstChild.textContent = 'Build cradle '; }
  }
});
for (const type of ['step', 'stl']) $('download-' + type).addEventListener('click', () => {
  if (dirty || !built || built.snapshot !== rawInputs()) { invalidate(); return; }
  const link = document.createElement('a');
  link.href = built[type + 'URL'];
  link.download = `battery-cradle-${built.params.length}x${built.params.width}x${built.params.height}mm.${type}`;
  document.body.appendChild(link); link.click(); link.remove();
});
window.addEventListener('pagehide', revokeDownloads);
window.addEventListener('pageshow', (event) => { if (event.persisted) invalidate(); });

function writeHash(params) {
  const url = new URL(location.href);
  url.hash = new URLSearchParams(keys.map((key) => [key, String(params[key])])).toString();
  history.replaceState(null, '', url);
}
function readHash() {
  const hash = new URLSearchParams(location.hash.slice(1));
  const params = { ...defaults };
  for (const key of keys) if (hash.has(key)) params[key] = hash.get(key);
  setInputs(params); // Invalid/empty hash values remain unbuildable, never silently accepted.
  $('preset').value = '';
  $('preset-note').textContent = location.hash ? 'Shared inputs loaded. Build to validate and preview them.' : 'Nominal original battery: 51 × 28 × 14 mm. Measure your own pack.';
}
window.addEventListener('hashchange', readHash);
$('share').addEventListener('click', async () => {
  try {
    const params = paramsFromInputs();
    writeHash(params);
    const url = location.href;
    if (navigator.share) { await navigator.share({ title: 'Battery cradle inputs', url }); $('share-state').textContent = 'Inputs shared; the recipient must build to validate them.'; }
    else if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(url); $('share-state').textContent = 'Link copied. Inputs still require a successful build to validate.'; }
    else $('share-state').textContent = 'Inputs saved in the address bar. Copy the page address to share.';
  } catch (cause) { if (cause.name !== 'AbortError') $('share-state').textContent = `Could not share: ${cause.message}. You can copy the page address after entering numeric inputs.`; }
});

async function loadPresets() {
  try {
    const response = await fetch('api/presets');
    if (!response.ok) throw new Error('Presets unavailable');
    const presets = await response.json();
    if (!Array.isArray(presets)) throw new Error('Invalid preset list');
    for (const [index, preset] of presets.entries()) {
      const option = document.createElement('option');
      option.value = String(index); option.textContent = preset.label;
      $('preset').appendChild(option);
    }
    $('preset').addEventListener('change', () => {
      if ($('preset').value === '') return;
      const preset = presets[Number($('preset').value)];
      setInputs(preset.params);
      $('preset-note').textContent = [preset.note, preset.source ? `Source: ${preset.source}` : ''].filter(Boolean).join(' ');
    });
  } catch { $('preset-note').textContent = 'Presets could not be loaded. You can still build using the dimensions below.'; }
}
readHash();
try { viewer = initViewer(); } catch (cause) { error(`3D viewer unavailable: ${cause.message}. Enable WebGL and reload.`); }
loadPresets();
if (viewer) form.requestSubmit();
