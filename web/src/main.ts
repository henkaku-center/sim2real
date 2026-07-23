// UI thread: PlayCanvas rendering + joint sliders. Physics lives in worker.ts.

import * as pc from "playcanvas";
import type { GeomMeta, JointInfo, WorkerRequest, WorkerResponse } from "./protocol";
import "./style.css";

// mjtGeom enum values we render (subset used by the placeholder model)
const GEOM_PLANE = 0;
const GEOM_SPHERE = 2;
const GEOM_CAPSULE = 3;
const GEOM_BOX = 6;

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
camera.setPosition(0.35, 0.25, 0.45);
camera.lookAt(0, 0.03, 0);
pcApp.root.addChild(camera);

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

function makeGeomEntity(meta: GeomMeta, index: number): pc.Entity {
  const e = new pc.Entity(`geom${index}`);
  const material = new pc.StandardMaterial();
  material.diffuse = new pc.Color(meta.rgba[0], meta.rgba[1], meta.rgba[2]);
  material.update();
  const shape = new pc.Entity("shape");
  let mesh: pc.Mesh | undefined;
  const device = pcApp.graphicsDevice;
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
const stateWaiters: ((s: { qpos: number[]; ctrl: number[]; time: number }) => void)[] = [];
let readyResolve: (() => void) | undefined;
const simHook = {
  ready: new Promise<void>((res) => (readyResolve = res)),
  errors,
  send,
  getState: () =>
    new Promise<{ qpos: number[]; ctrl: number[]; time: number }>((res) => {
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
    resize();
    readyResolve?.();
  } else if (msg.type === "frame") {
    applyFrame(msg.xpos, msg.xmat);
  } else if (msg.type === "state") {
    stateWaiters.splice(0).forEach((w) => w({ qpos: msg.qpos, ctrl: msg.ctrl, time: msg.time }));
  } else if (msg.type === "error") {
    errors.push(msg.message);
    console.error("worker error:", msg.message);
  }
};

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
