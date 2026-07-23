/// <reference lib="webworker" />
// MuJoCo WASM simulation worker. Physics runs here; the UI thread only renders.

import MainModuleFactory, { type MainModule, type MjModel, type MjData } from "@mujoco/mujoco";
import modelXml from "../../models/sesame.xml?raw";
import type { WorkerRequest, WorkerResponse } from "./protocol";

const STEP_MS = 20; // wall-clock cadence of the free-running loop

let mj: MainModule;
let model: MjModel;
let data: MjData;
let running = false;

function post(msg: WorkerResponse, transfer: Transferable[] = []) {
  (self as unknown as DedicatedWorkerGlobalScope).postMessage(msg, transfer);
}

// Embind exposes numeric arrays either as heap views (typed arrays) or as
// vector handles with get/size — normalize to a plain JS number array.
function asNumbers(x: unknown, n?: number): number[] {
  if (ArrayBuffer.isView(x)) {
    const arr = Array.from(x as Float64Array);
    return n === undefined ? arr : arr.slice(0, n);
  }
  const vec = x as { size(): number; get(i: number): number | undefined };
  const len = n ?? vec.size();
  const out: number[] = [];
  for (let i = 0; i < len; i++) out.push(vec.get(i) ?? NaN);
  return out;
}

function setScalar(x: unknown, i: number, value: number) {
  if (ArrayBuffer.isView(x)) {
    (x as Float64Array)[i] = value;
  } else {
    (x as { set(i: number, v: number): boolean }).set(i, value);
  }
}

function stateMessage(): WorkerResponse {
  return {
    type: "state",
    qpos: asNumbers(data.qpos, model.nq),
    ctrl: asNumbers(data.ctrl, model.nu),
    time: data.time as number,
  };
}

function frameMessage(): { msg: WorkerResponse; transfer: Transferable[] } {
  const n = model.ngeom;
  const xpos = new Float32Array(asNumbers(data.geom_xpos, n * 3));
  const xmat = new Float32Array(asNumbers(data.geom_xmat, n * 9));
  return {
    msg: { type: "frame", xpos, xmat, time: data.time as number },
    transfer: [xpos.buffer, xmat.buffer],
  };
}

function stepLoop() {
  if (!running) return;
  const stepsPerTick = Math.round(STEP_MS / 1000 / model.opt.timestep);
  for (let i = 0; i < stepsPerTick; i++) mj.mj_step(model, data);
  const { msg, transfer } = frameMessage();
  post(msg, transfer);
}

async function init() {
  mj = await MainModuleFactory();
  model = mj.MjModel.from_xml_string(modelXml);
  data = new mj.MjData(model);
  mj.mj_forward(model, data);

  const joints = [];
  const ctrlrange = asNumbers(model.actuator_ctrlrange, model.nu * 2);
  for (let i = 0; i < model.nu; i++) {
    joints.push({
      name: mj.mj_id2name(model, mj.mjtObj.mjOBJ_ACTUATOR.value, i),
      channel: i,
      ctrlLo: ctrlrange[2 * i],
      ctrlHi: ctrlrange[2 * i + 1],
    });
  }
  const geoms = [];
  const gtype = asNumbers(model.geom_type, model.ngeom);
  const gsize = asNumbers(model.geom_size, model.ngeom * 3);
  const grgba = asNumbers(model.geom_rgba, model.ngeom * 4);
  for (let g = 0; g < model.ngeom; g++) {
    geoms.push({
      type: gtype[g],
      size: gsize.slice(3 * g, 3 * g + 3) as [number, number, number],
      rgba: grgba.slice(4 * g, 4 * g + 4) as [number, number, number, number],
    });
  }
  post({
    type: "ready",
    joints,
    geoms,
    timestep: model.opt.timestep as number,
    mujocoVersion: mj.mj_versionString(),
  });
  const { msg, transfer } = frameMessage();
  post(msg, transfer);
  running = true;
  setInterval(stepLoop, STEP_MS);
}

self.onmessage = async (ev: MessageEvent<WorkerRequest>) => {
  const req = ev.data;
  try {
    switch (req.type) {
      case "init":
        await init();
        break;
      case "setCtrl":
        setScalar(data.ctrl, req.channel, req.value);
        break;
      case "ctrl":
        req.values.forEach((v, i) => setScalar(data.ctrl, i, v));
        break;
      case "reset":
        mj.mj_resetData(model, data);
        for (let i = 0; i < model.nu; i++) setScalar(data.ctrl, i, 0);
        mj.mj_forward(model, data);
        {
          const { msg, transfer } = frameMessage();
          post(msg, transfer);
        }
        break;
      case "pause":
        running = false;
        break;
      case "resume":
        running = true;
        break;
      case "run": {
        const wasRunning = running;
        running = false;
        for (let i = 0; i < req.steps; i++) mj.mj_step(model, data);
        const { msg, transfer } = frameMessage();
        post(msg, transfer);
        post(stateMessage());
        running = wasRunning;
        break;
      }
      case "getState":
        post(stateMessage());
        break;
    }
  } catch (e) {
    post({ type: "error", message: `${e}` });
  }
};

export {}; // module worker
