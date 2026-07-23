"""Determinism and reference-trajectory checks for models/sesame.xml.

Two levels:
1. Bit-identical repeatability on the same machine/build (hard requirement).
2. Agreement with a committed reference trajectory within a declared
   tolerance (cross-platform: macOS/Linux builds may differ in low-order
   bits, and 2 s of contact dynamics amplifies them).
"""

import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from sim.build_mjcf import MODEL_PATH
from sim.manifest import load_manifest

REFERENCE_PATH = Path(__file__).parent / "data" / "stand_1000_qpos.json"
STEPS = 1000
CROSS_PLATFORM_ATOL = 1e-3  # declared tolerance vs committed Linux reference


def load_model() -> mujoco.MjModel:
    return mujoco.MjModel.from_xml_path(str(MODEL_PATH))


def run_stand(steps: int = STEPS) -> np.ndarray:
    model = load_model()
    data = mujoco.MjData(model)
    manifest = load_manifest()
    stand = manifest.pose_internal("stand")
    data.ctrl[:] = [stand[j.name] for j in manifest.joints]
    for _ in range(steps):
        mujoco.mj_step(model, data)
    return data.qpos.copy()


@pytest.fixture(scope="module")
def final_qpos():
    return run_stand()


def test_bit_identical_repeatability(final_qpos):
    assert np.array_equal(final_qpos, run_stand()), (
        "same machine, same build: runs must be bit-identical"
    )


def test_matches_committed_reference(final_qpos):
    ref = json.loads(REFERENCE_PATH.read_text())
    assert ref["steps"] == STEPS
    np.testing.assert_allclose(
        final_qpos, np.array(ref["qpos"]), atol=CROSS_PLATFORM_ATOL,
        err_msg="drifted from committed reference (see tests/data/); "
        "if the model intentionally changed, regenerate the reference",
    )


def test_stand_command_raises_torso(final_qpos):
    spawn_z = 0.05  # keyframe height from sim/build_mjcf.py
    assert final_qpos[2] > spawn_z + 0.01, "standing should lift the torso"
    assert np.all(np.isfinite(final_qpos))


def test_final_pose_is_left_right_symmetric(final_qpos):
    # Mirroring is encoded in the manifest signs, so mirrored joints share the
    # same internal target and should settle near the same internal angle.
    model = load_model()

    def q(name: str) -> float:
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        return final_qpos[model.jnt_qposadr[jid]]

    for right, left in (("R1", "L1"), ("R2", "L2"), ("R3", "L3"), ("R4", "L4")):
        assert q(right) == pytest.approx(q(left), abs=0.1), (
            f"{right}/{left}: mirrored joints should settle at similar internal angles"
        )
    # Diagonal symmetry of the placeholder model is exact: R1<->L2, R2<->L1.
    assert q("R1") == pytest.approx(-q("L2"), abs=1e-6)
    assert q("R2") == pytest.approx(-q("L1"), abs=1e-6)
