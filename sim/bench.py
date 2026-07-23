"""Headless step-rate benchmark for models/sesame.xml.

Usage: uv run python sim/bench.py [--steps N] [--repeats R]

Prints steps/second and real-time factor (model timestep 0.002 s => 500
steps/s is real time). Runs single-threaded on one core.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

import mujoco

from sim.build_mjcf import MODEL_PATH, TIMESTEP
from sim.manifest import load_manifest


def bench(steps: int) -> float:
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
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
    parser.add_argument("--steps", type=int, default=50_000)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    rates = [bench(args.steps) for _ in range(args.repeats)]
    best = max(rates)
    print(f"model: {MODEL_PATH.name}  timestep: {TIMESTEP} s  steps: {args.steps}")
    for i, r in enumerate(rates):
        print(f"  run {i}: {r:,.0f} steps/s")
    print(f"best: {best:,.0f} steps/s  ({best * TIMESTEP:,.0f}x real time)")


if __name__ == "__main__":
    main()
