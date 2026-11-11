"""Headless step-rate benchmark for a named model (default: the course twin).

Usage: uv run python sim/bench.py [--design NAME] [--steps N] [--repeats R]

NAME is a printing design from manifest/twin.yaml, or upstream-v117 for the
upstream-body baseline (models/sesame.xml). Prints steps/second and real-time
factor. Runs single-threaded on one core.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

import mujoco

from sim.manifest import load_manifest
from sim.twin import model_path


def bench(steps: int, design: str | None = None) -> float:
    model = mujoco.MjModel.from_xml_path(str(model_path(design)))
    data = mujoco.MjData(model)
    manifest = load_manifest()
    stand = manifest.pose_internal("stand")
    data.ctrl[:] = [stand[j.name] for j in manifest.joints]
    mujoco.mj_step(model, data)  # warm-up (allocations, first contact)
    t0 = time.perf_counter()
    for _ in range(steps):
        mujoco.mj_step(model, data)
    return steps / (time.perf_counter() - t0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", help="model name (default: the course twin)")
    parser.add_argument("--steps", type=int, default=50_000)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    path = model_path(args.design)
    timestep = mujoco.MjModel.from_xml_path(str(path)).opt.timestep
    rates = [bench(args.steps, args.design) for _ in range(args.repeats)]
    best = max(rates)
    print(f"model: {path.name}  timestep: {timestep} s  steps: {args.steps}")
    for i, r in enumerate(rates):
        print(f"  run {i}: {r:,.0f} steps/s")
    print(f"best: {best:,.0f} steps/s  ({best * timestep:,.0f}x real time)")


if __name__ == "__main__":
    main()
