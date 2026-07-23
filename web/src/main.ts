// UI thread: PlayCanvas rendering + joint sliders. Physics lives in worker.ts.

import * as pc from "playcanvas";
import type { GeomMeta, JointInfo, WorkerRequest, WorkerResponse } from "./protocol";
import "./style.css";

// mjtGeom enum values we render (subset used by the placeholder model)
const GEOM_PLANE = 0;
const GEOM_SPHERE = 2;
const GEOM_CAPSULE = 3;
const GEOM_BOX = 6;
const GEOM_MESH = 7;
const COLLISION_GROUP = 3; // hidden, mirrors the native viewer default

const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });

const app = document.querySelector<HTMLDivElement>("#app")!;
app.innerHTML = `
  <main>
    <canvas id="view"></canvas>
    <aside id="panel">
      <h1>sesame sim</h1>
      <div id="status">loading MuJoCo WASM…</div>
      <div id="sliders"></div>
      <div id="buttons">
        <button id="reset">reset</button>
        <button id="rest">rest</button>
        <button id="stand">stand</button>
      </div>
      <h2>motions</h2>
      <div id="motions"></div>
      <h2>debug</h2>
      <label id="skeleton-toggle"><input type="checkbox" id="show-skeleton"> show skeleton</label>
      <div id="telemetry"></div>
    </aside>
  </main>`;

// ---------- PlayCanvas scene ----------
const canvas = document.querySelector<HTMLCanvasElement>("#view")!;
const pcApp = new pc.Application(canvas, {});
pcApp.setCanvasFillMode(pc.FILLMODE_NONE);
pcApp.setCanvasResolution(pc.RESOLUTION_AUTO);
function resize() {
  const rect = canvas.parentElement!.getBoundingClientRect();
  pcApp.resizeCanvas(rect.width - 320, rect.height);
}
window.addEventListener("resize", resize);
pcApp.start();

const camera = new pc.Entity("camera");
camera.addComponent("camera", { clearColor: new pc.Color(0.12, 0.12, 0.14) });
pcApp.root.addChild(camera);

// ---------- Orbit camera: left-drag rotate, right/shift-drag pan, wheel zoom
const orbit = {
  yawDeg: 38,
  pitchDeg: -28,
  dist: 0.55,
  target: new pc.Vec3(0, 0.03, 0),
};

function updateCamera() {
  const yaw = (orbit.yawDeg * Math.PI) / 180;
  const pitch = (orbit.pitchDeg * Math.PI) / 180;
  const cp = Math.cos(pitch);
  camera.setPosition(
    orbit.target.x + orbit.dist * cp * Math.sin(yaw),
    orbit.target.y - orbit.dist * Math.sin(pitch),
    orbit.target.z + orbit.dist * cp * Math.cos(yaw),
  );
  camera.lookAt(orbit.target);
}
updateCamera();

let dragButton = -1;
let lastX = 0;
let lastY = 0;
canvas.addEventListener("contextmenu", (e) => e.preventDefault());
canvas.addEventListener("pointerdown", (e) => {
  dragButton = e.button;
  lastX = e.clientX;
  lastY = e.clientY;
  try {
    canvas.setPointerCapture(e.pointerId);
  } catch {
    /* synthetic events (tests) have no active pointer */
  }
});
canvas.addEventListener("pointerup", (e) => {
  dragButton = -1;
  try {
    canvas.releasePointerCapture(e.pointerId);
  } catch {
    /* see above */
  }
});
canvas.addEventListener("pointermove", (e) => {
  if (dragButton < 0) return;
  const dx = e.clientX - lastX;
  const dy = e.clientY - lastY;
  lastX = e.clientX;
  lastY = e.clientY;
  if (dragButton === 0 && !e.shiftKey) {
    orbit.yawDeg -= dx * 0.4;
    orbit.pitchDeg = Math.max(-89, Math.min(89, orbit.pitchDeg - dy * 0.4));
  } else {
    // pan in the camera's screen plane
    const scale = orbit.dist * 0.002;
    const right = camera.right;
    const up = camera.up;
    orbit.target.x -= (right.x * dx - up.x * dy) * scale;
    orbit.target.y -= (right.y * dx - up.y * dy) * scale;
    orbit.target.z -= (right.z * dx - up.z * dy) * scale;
  }
  updateCamera();
});
canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    orbit.dist = Math.max(0.1, Math.min(3, orbit.dist * Math.pow(1.0015, e.deltaY)));
    updateCamera();
  },
  { passive: false },
);

// Test hook for camera QC (CDP)
declare global {
  interface Window {
    __view: { orbit: typeof orbit; cameraPos: () => number[] };
  }
}
window.__view = {
  orbit,
  cameraPos: () => {
    const p = camera.getPosition();
    return [p.x, p.y, p.z];
  },
};

const light = new pc.Entity("light");
light.addComponent("light", { type: "directional", intensity: 1.2, castShadows: false });
light.setEulerAngles(50, 30, 0);
pcApp.root.addChild(light);

// MuJoCo is z-up; PlayCanvas is y-up. Parent all geoms under a rotated root
// so MuJoCo coordinates can be used directly as local transforms.
const mjRoot = new pc.Entity("mujoco-root");
mjRoot.setEulerAngles(-90, 0, 0);
pcApp.root.addChild(mjRoot);

const geomEntities: pc.Entity[] = [];

// ---------- Skeleton (rig) visualization ----------
let siteNames: string[] = [];
let siteEntities: pc.Entity[] = [];
let latestSites: Float32Array | null = null;
let showSkeleton = false;
const BONE_CHAINS: string[][] = []; // filled once site names are known
const boneColor = new pc.Color(0.1, 1.0, 0.4);
const tmpA = new pc.Vec3();
const tmpB = new pc.Vec3();

function makeSiteEntities(names: string[]) {
  siteNames = names;
  const mat = new pc.StandardMaterial();
  mat.emissive = new pc.Color(0.1, 1.0, 0.4);
  mat.diffuse = new pc.Color(0, 0, 0);
  mat.update();
  for (const name of names) {
    const e = new pc.Entity(`site_${name}`);
    const mesh = pc.Mesh.fromGeometry(pcApp.graphicsDevice, new pc.SphereGeometry({ radius: 0.004 }));
    e.addComponent("render", { meshInstances: [new pc.MeshInstance(mesh, mat)] });
    e.enabled = false;
    mjRoot.addChild(e);
    siteEntities.push(e);
  }
  for (const leg of ["front_left", "front_right", "back_left", "back_right"]) {
    BONE_CHAINS.push(["torso_center", `${leg}_hip`, `${leg}_knee`, `${leg}_paw`]);
  }
  BONE_CHAINS.push(["face", "torso_center", "rear"]);
}

function sitePos(name: string, out: pc.Vec3): pc.Vec3 {
  const i = siteNames.indexOf(name);
  out.set(latestSites![3 * i], latestSites![3 * i + 1], latestSites![3 * i + 2]);
  return mjRoot.getWorldTransform().transformPoint(out, out);
}

// ---------- Live telemetry (from the skeleton stream) ----------
const PAWS = ["front_left_paw", "front_right_paw", "back_left_paw", "back_right_paw"];
const GROUND_EPS = 0.012; // paddle half-height + margin: below this = grounded
let telemetryEls: Record<string, HTMLElement> = {};

function buildTelemetry() {
  const el = document.querySelector<HTMLDivElement>("#telemetry")!;
  el.innerHTML =
    `<div class="trow" id="t-torso"></div><div class="trow" id="t-att"></div>` +
    PAWS.map((p) => `<div class="trow paw" id="t-${p}"></div>`).join("");
  telemetryEls = Object.fromEntries(
    ["t-torso", "t-att", ...PAWS.map((p) => `t-${p}`)].map((id) => [
      id,
      document.querySelector<HTMLElement>(`#${id}`)!,
    ]),
  );
}

function site3(name: string): [number, number, number] {
  const i = siteNames.indexOf(name);
  return [latestSites![3 * i], latestSites![3 * i + 1], latestSites![3 * i + 2]];
}

function updateTelemetry() {
  if (!latestSites || siteNames.length === 0) return;
  const [cx, cy, cz] = site3("torso_center");
  const face = site3("face");
  const rear = site3("rear");
  const pitch = face[2] - rear[2];
  const yawDeg = (Math.atan2(face[1] - rear[1], face[0] - rear[0]) * 180) / Math.PI;
  telemetryEls["t-torso"].textContent =
    `torso xyz ${cx.toFixed(3)} ${cy.toFixed(3)} ${cz.toFixed(3)}`;
  telemetryEls["t-att"].textContent =
    `yaw ${yawDeg.toFixed(0)}\u00b0  pitch(f-r) ${(pitch * 1000).toFixed(0)}mm`;
  for (const p of PAWS) {
    const z = site3(p)[2];
    const grounded = z < GROUND_EPS;
    const el = telemetryEls[`t-${p}`];
    el.textContent = `${p.replace("_paw", "").replaceAll("_", " ")} ${(z * 1000)
      .toFixed(0)
      .padStart(3)}mm ${grounded ? "\u25a0 ground" : "\u25a1 air"}`;
    el.classList.toggle("grounded", grounded);
  }
}

pcApp.on("update", () => {
  updateTelemetry();
  if (!showSkeleton || !latestSites) return;
  for (const chain of BONE_CHAINS) {
    for (let i = 0; i + 1 < chain.length; i++) {
      pcApp.drawLine(sitePos(chain[i], tmpA), sitePos(chain[i + 1], tmpB), boneColor, false);
    }
  }
});

function makeGeomEntity(meta: GeomMeta, index: number): pc.Entity {
  const e = new pc.Entity(`geom${index}`);
  const material = new pc.StandardMaterial();
  material.diffuse = new pc.Color(meta.rgba[0], meta.rgba[1], meta.rgba[2]);
  material.update();
  const shape = new pc.Entity("shape");
  let mesh: pc.Mesh | undefined;
  const device = pcApp.graphicsDevice;
  if (meta.group === COLLISION_GROUP) {
    e.addChild(shape);
    mjRoot.addChild(e);
    return e; // collision primitive: keep the entity for indexing, render nothing
  }
  if (meta.type === GEOM_MESH) {
    // counter-apply MuJoCo's internal mesh re-centering to the raw GLB
    const [qw, qx, qy, qz] = meta.meshQuat ?? [1, 0, 0, 0];
    const qInv = new pc.Quat(-qx, -qy, -qz, qw);
    const t = meta.meshPos ?? [0, 0, 0];
    const off = qInv.transformVector(new pc.Vec3(-t[0], -t[1], -t[2]));
    shape.setLocalRotation(qInv);
    shape.setLocalPosition(off);
    const base = meta.name.replace(/_visual$/, "");
    const asset = new pc.Asset(base, "container", { url: `/meshes/${base}.glb` });
    asset.on("load", () => {
      const inst = (asset.resource as pc.ContainerResource).instantiateRenderEntity();
      inst.findComponents("render").forEach((rc) => {
        (rc as pc.RenderComponent).meshInstances.forEach((mi) => (mi.material = material));
      });
      shape.addChild(inst);
    });
    pcApp.assets.add(asset);
    pcApp.assets.load(asset);
    e.addChild(shape);
    mjRoot.addChild(e);
    return e;
  }
  if (meta.type === GEOM_PLANE) {
    mesh = pc.Mesh.fromGeometry(device, new pc.PlaneGeometry({ halfExtents: new pc.Vec2(1, 1) }));
    shape.setLocalEulerAngles(90, 0, 0); // plane geometry is y-up; mujoco plane is z-up
  } else if (meta.type === GEOM_BOX) {
    mesh = pc.Mesh.fromGeometry(
      device,
      new pc.BoxGeometry({ halfExtents: new pc.Vec3(meta.size[0], meta.size[1], meta.size[2]) }),
    );
  } else if (meta.type === GEOM_CAPSULE) {
    // mujoco capsule: size = [radius, half-length], axis = local z
    mesh = pc.Mesh.fromGeometry(
      device,
      new pc.CapsuleGeometry({ radius: meta.size[0], height: 2 * meta.size[1] + 2 * meta.size[0] }),
    );
    shape.setLocalEulerAngles(90, 0, 0); // capsule geometry axis is y; mujoco axis is z
  } else if (meta.type === GEOM_SPHERE) {
    mesh = pc.Mesh.fromGeometry(device, new pc.SphereGeometry({ radius: meta.size[0] }));
  }
  if (mesh) {
    const mi = new pc.MeshInstance(mesh, material);
    shape.addComponent("render", { meshInstances: [mi] });
  }
  e.addChild(shape);
  mjRoot.addChild(e);
  return e;
}

const rotMat = new pc.Mat4();
const quat = new pc.Quat();
function applyFrame(xpos: Float32Array, xmat: Float32Array) {
  for (let g = 0; g < geomEntities.length; g++) {
    const e = geomEntities[g];
    e.setLocalPosition(xpos[3 * g], xpos[3 * g + 1], xpos[3 * g + 2]);
    const m = xmat.subarray(9 * g, 9 * g + 9);
    // column-major Mat4 from row-major 3x3
    rotMat.set([m[0], m[3], m[6], 0, m[1], m[4], m[7], 0, m[2], m[5], m[8], 0, 0, 0, 0, 1]);
    quat.setFromMat4(rotMat);
    e.setLocalRotation(quat);
  }
}

// ---------- Worker wiring + UI ----------
const statusEl = document.querySelector<HTMLDivElement>("#status")!;
const slidersEl = document.querySelector<HTMLDivElement>("#sliders")!;
let joints: JointInfo[] = [];
const sliderInputs: HTMLInputElement[] = [];

function send(msg: WorkerRequest) {
  worker.postMessage(msg);
}

function setSliders(values: number[]) {
  values.forEach((v, i) => {
    sliderInputs[i].value = `${v}`;
    sliderInputs[i].dispatchEvent(new Event("_display"));
  });
}

function commandPose(values: number[]) {
  send({ type: "ctrl", values });
  setSliders(values);
}

// Test hook for CDP smoke tests (tests/, Stage 0 task 6).
const errors: string[] = [];
const stateWaiters: ((s: Extract<WorkerResponse, { type: "state" }>) => void)[] = [];
let readyResolve: (() => void) | undefined;
const simHook = {
  ready: new Promise<void>((res) => (readyResolve = res)),
  errors,
  send,
  getState: () =>
    new Promise<Extract<WorkerResponse, { type: "state" }>>((res) => {
      stateWaiters.push(res);
      send({ type: "getState" });
    }),
};
declare global {
  interface Window {
    __sim: typeof simHook;
  }
}
window.__sim = simHook;

worker.onmessage = (ev: MessageEvent<WorkerResponse>) => {
  const msg = ev.data;
  if (msg.type === "ready") {
    joints = msg.joints;
    statusEl.textContent = `MuJoCo ${msg.mujocoVersion} · dt=${msg.timestep}s`;
    const motionsEl = document.querySelector<HTMLDivElement>("#motions")!;
    for (const name of msg.motions) {
      const b = document.createElement("button");
      b.textContent = name.replaceAll("_", " ");
      b.dataset.motion = name;
      b.addEventListener("click", () => send({ type: "motion", name }));
      motionsEl.append(b);
    }
    msg.geoms.forEach((meta, i) => geomEntities.push(makeGeomEntity(meta, i)));
    for (const j of joints) {
      const row = document.createElement("label");
      row.className = "slider-row";
      const name = document.createElement("span");
      name.textContent = `ch${j.channel} ${j.name}`;
      const input = document.createElement("input");
      input.type = "range";
      input.min = `${j.ctrlLo}`;
      input.max = `${j.ctrlHi}`;
      input.step = "0.01";
      input.value = "0";
      input.dataset.joint = j.name;
      const val = document.createElement("code");
      const display = () => (val.textContent = `${Number(input.value).toFixed(2)}`);
      display();
      input.addEventListener("input", () => {
        display();
        send({ type: "setCtrl", channel: j.channel, value: Number(input.value) });
      });
      input.addEventListener("_display", display);
      row.append(name, input, val);
      slidersEl.append(row);
      sliderInputs.push(input);
    }
    makeSiteEntities(msg.siteNames);
    buildTelemetry();
    resize();
    readyResolve?.();
  } else if (msg.type === "frame") {
    applyFrame(msg.xpos, msg.xmat);
    latestSites = msg.sites;
    for (let i = 0; i < siteEntities.length; i++) {
      siteEntities[i].setLocalPosition(msg.sites[3 * i], msg.sites[3 * i + 1], msg.sites[3 * i + 2]);
    }
  } else if (msg.type === "state") {
    stateWaiters.splice(0).forEach((w) => w(msg));
  } else if (msg.type === "error") {
    errors.push(msg.message);
    console.error("worker error:", msg.message);
  }
};

document.querySelector<HTMLInputElement>("#show-skeleton")!.addEventListener("change", (ev) => {
  showSkeleton = (ev.target as HTMLInputElement).checked;
  siteEntities.forEach((e) => (e.enabled = showSkeleton));
});

document.querySelector("#reset")!.addEventListener("click", () => {
  send({ type: "reset" });
  setSliders(new Array(8).fill(0));
});
document.querySelector("#rest")!.addEventListener("click", () => commandPose(new Array(8).fill(0)));
document.querySelector("#stand")!.addEventListener("click", () =>
  // Internal-radian stand pose: hips (ch0-3) +45° down, feet (ch4-7) +90°
  // down. Numerical agreement with manifest poses.stand is CDP-tested.
  commandPose([...Array(4).fill(Math.PI / 4), ...Array(4).fill(Math.PI / 2)]),
);

send({ type: "init" });
