/// <reference lib="webworker" />
// MuJoCo WASM simulation worker. Physics runs here; the UI thread only renders.

import MainModuleFactory, { type MainModule, type MjModel, type MjData } from "@mujoco/mujoco";
import modelXml from "../../models/sesame.xml?raw";
import { ctrlSchedule, motionNames, type ScheduleEntry } from "./motions";
import type { WorkerRequest, WorkerResponse } from "./protocol";

const STEP_MS = 20; // wall-clock cadence of the free-running loop
const DEFAULT_SETTLE_STEPS = 500; // matches sim/motions.py play_native

let mj: MainModule;
let model: MjModel;
let data: MjData;
let running = false;
let globalStep = 0;
// Pending motion schedule in absolute step indices (live-loop playback).
let pending: { entry: ScheduleEntry; atStep: number }[] = [];

function applyPendingBefore(step: number) {
  while (pending.length > 0 && pending[0].atStep <= step) {
    const { entry } = pending.shift()!;
    setScalar(data.ctrl, entry.channel, entry.value);
  }
}

function doStep() {
  applyPendingBefore(globalStep);
  mj.mj_step(model, data);
  globalStep++;
}

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
  const skeleton: Record<string, [number, number, number]> = {};
  const xpos = asNumbers(data.site_xpos, model.nsite * 3);
  for (let i = 0; i < model.nsite; i++) {
    const name = mj.mj_id2name(model, mj.mjtObj.mjOBJ_SITE.value, i);
    skeleton[name] = [xpos[3 * i], xpos[3 * i + 1], xpos[3 * i + 2]];
  }
  return {
    type: "state",
    qpos: asNumbers(data.qpos, model.nq),
    ctrl: asNumbers(data.ctrl, model.nu),
    time: data.time as number,
    skeleton,
  };
}

function frameMessage(): { msg: WorkerResponse; transfer: Transferable[] } {
  const n = model.ngeom;
  const xpos = new Float32Array(asNumbers(data.geom_xpos, n * 3));
  const xmat = new Float32Array(asNumbers(data.geom_xmat, n * 9));
  const sites = new Float32Array(asNumbers(data.site_xpos, model.nsite * 3));
  return {
    msg: { type: "frame", xpos, xmat, sites, time: data.time as number },
    transfer: [xpos.buffer, xmat.buffer, sites.buffer],
  };
}

function stepLoop() {
  if (!running) return;
  const stepsPerTick = Math.round(STEP_MS / 1000 / model.opt.timestep);
  for (let i = 0; i < stepsPerTick; i++) doStep();
  const { msg, transfer } = frameMessage();
  post(msg, transfer);
}

// Mesh files referenced by the MJCF, served by Vite and mounted into the
// MuJoCo virtual filesystem before model compilation.
const stlUrls = import.meta.glob("../../assets/mesh/*.stl", {
  query: "?url",
  import: "default",
  eager: true,
}) as Record<string, string>;

async function init() {
  mj = await MainModuleFactory();
  const vfs = new mj.MjVFS();
  await Promise.all(
    Object.entries(stlUrls).map(async ([path, url]) => {
      const buf = new Uint8Array(await (await fetch(url)).arrayBuffer());
      const base = path.split("/").pop()!;
      // the compiler resolves meshdir-relative paths; register both forms
      vfs.addBuffer(`../assets/mesh/${base}`, buf);
      vfs.addBuffer(base, buf);
    }),
  );
  model = mj.MjModel.from_xml_string(modelXml, vfs);
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
  const ggroup = asNumbers(model.geom_group, model.ngeom);
  const gsize = asNumbers(model.geom_size, model.ngeom * 3);
  const grgba = asNumbers(model.geom_rgba, model.ngeom * 4);
  const gdata = asNumbers(model.geom_dataid, model.ngeom);
  const meshPos = asNumbers(model.mesh_pos, model.nmesh * 3);
  const meshQuat = asNumbers(model.mesh_quat, model.nmesh * 4);
  const MESH_TYPE = 7; // mjGEOM_MESH
  for (let g = 0; g < model.ngeom; g++) {
    const meta: import("./protocol").GeomMeta = {
      name: mj.mj_id2name(model, mj.mjtObj.mjOBJ_GEOM.value, g) ?? `geom${g}`,
      type: gtype[g],
      group: ggroup[g],
      size: gsize.slice(3 * g, 3 * g + 3) as [number, number, number],
      rgba: grgba.slice(4 * g, 4 * g + 4) as [number, number, number, number],
    };
    if (gtype[g] === MESH_TYPE && gdata[g] >= 0) {
      const m = gdata[g];
      meta.meshPos = meshPos.slice(3 * m, 3 * m + 3) as [number, number, number];
      meta.meshQuat = meshQuat.slice(4 * m, 4 * m + 4) as [number, number, number, number];
    }
    geoms.push(meta);
  }
  const siteNames = [];
  for (let i = 0; i < model.nsite; i++) {
    siteNames.push(mj.mj_id2name(model, mj.mjtObj.mjOBJ_SITE.value, i));
  }
  post({
    type: "ready",
    joints,
    geoms,
    motions: motionNames,
    siteNames,
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
        pending = [];
        globalStep = 0;
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
        for (let i = 0; i < req.steps; i++) doStep();
        const { msg, transfer } = frameMessage();
        post(msg, transfer);
        post(stateMessage());
        running = wasRunning;
        break;
      }
      case "motion": {
        // Live playback: schedule relative to the current step.
        const base = globalStep;
        pending = ctrlSchedule(req.name, model.opt.timestep).map((entry) => ({
          entry,
          atStep: base + entry.stepIndex,
        }));
        break;
      }
      case "runMotion": {
        // Deterministic playback mirroring sim/motions.py play_native.
        const wasRunning = running;
        running = false;
        const schedule = ctrlSchedule(req.name, model.opt.timestep);
        const settle = req.settleSteps ?? DEFAULT_SETTLE_STEPS;
        const last = schedule.length > 0 ? schedule[schedule.length - 1].stepIndex : 0;
        let i = 0;
        for (let step = 0; step < last + settle; step++) {
          while (i < schedule.length && schedule[i].stepIndex <= step) {
            setScalar(data.ctrl, schedule[i].channel, schedule[i].value);
            i++;
          }
          mj.mj_step(model, data);
          globalStep++;
        }
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
