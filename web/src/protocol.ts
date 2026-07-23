// Message protocol between the UI thread and the MuJoCo worker.

export interface JointInfo {
  name: string;
  channel: number; // actuator index == firmware servo channel
  ctrlLo: number; // internal radians
  ctrlHi: number;
}

export interface GeomMeta {
  type: number; // mjtGeom enum value
  size: [number, number, number];
  rgba: [number, number, number, number];
}

export type WorkerRequest =
  | { type: "init" }
  | { type: "setCtrl"; channel: number; value: number }
  | { type: "ctrl"; values: number[] }
  | { type: "reset" }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "run"; steps: number } // deterministic stepping (pause first)
  | { type: "motion"; name: string } // schedule motion in the live loop
  | { type: "runMotion"; name: string; settleSteps?: number } // deterministic
  | { type: "getState" };

export type WorkerResponse =
  | {
      type: "ready";
      joints: JointInfo[];
      geoms: GeomMeta[];
      motions: string[];
      timestep: number;
      mujocoVersion: string;
    }
  | {
      type: "state";
      qpos: number[];
      ctrl: number[];
      time: number;
      // rig: world position of every named site (skeleton tracking points)
      skeleton: Record<string, [number, number, number]>;
    }
  | {
      type: "frame";
      // world transform per geom: 3 pos + 9 rotation-matrix floats
      xpos: Float32Array;
      xmat: Float32Array;
      time: number;
    }
  | { type: "error"; message: string };
