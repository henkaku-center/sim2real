// Stock motion expansion — mirror of sim/motions.py (keep semantics in sync):
// - flatten nested steps into merged, time-ordered events
// - event applies before step_index = round(time_ms / 1000 / timestep)

import { load as parseYaml } from "js-yaml";
import robotYamlRaw from "../../manifest/robot.yaml?raw";
import motionsYamlRaw from "../../manifest/motions.yaml?raw";

interface RobotManifest {
  conventions: { firmware_neutral_deg: number };
  joints: { name: string; channel: number; sign: number }[];
  poses: Record<string, Record<string, number>>;
}

type Step =
  | { pose: string }
  | { set: Record<string, number> }
  | { wait: number }
  | { repeat: { count: number; steps: Step[] } };

interface MotionsDoc {
  motions: Record<string, Step[]>;
}

export const robot = parseYaml(robotYamlRaw) as RobotManifest;
export const motionsDoc = parseYaml(motionsYamlRaw) as MotionsDoc;

export const motionNames = Object.keys(motionsDoc.motions);

const byName = new Map(robot.joints.map((j) => [j.name, j]));
const neutral = robot.conventions.firmware_neutral_deg;

export function toInternal(jointName: string, firmwareDeg: number): number {
  const j = byName.get(jointName)!;
  return ((firmwareDeg - neutral) * Math.PI / 180) * j.sign;
}

export interface Event {
  timeMs: number;
  targetsDeg: Record<string, number>;
}

export function flatten(steps: Step[]): Event[] {
  const events = new Map<number, Record<string, number>>();
  let t = 0;
  const apply = (targets: Record<string, number>) => {
    const existing = events.get(t) ?? {};
    events.set(t, { ...existing, ...targets });
  };
  const walk = (steps: Step[]) => {
    for (const step of steps) {
      if ("pose" in step) apply(robot.poses[step.pose]);
      else if ("set" in step) apply(step.set);
      else if ("wait" in step) t += step.wait;
      else if ("repeat" in step) {
        for (let i = 0; i < step.repeat.count; i++) walk(step.repeat.steps);
      }
    }
  };
  walk(steps);
  return [...events.entries()]
    .sort(([a], [b]) => a - b)
    .map(([timeMs, targetsDeg]) => ({ timeMs, targetsDeg }));
}

export interface ScheduleEntry {
  stepIndex: number;
  channel: number;
  value: number; // internal radians
}

export function ctrlSchedule(motionName: string, timestep: number): ScheduleEntry[] {
  const out: ScheduleEntry[] = [];
  for (const ev of flatten(motionsDoc.motions[motionName])) {
    const stepIndex = Math.round(ev.timeMs / 1000 / timestep);
    for (const [name, deg] of Object.entries(ev.targetsDeg)) {
      out.push({ stepIndex, channel: byName.get(name)!.channel, value: toInternal(name, deg) });
    }
  }
  return out;
}
