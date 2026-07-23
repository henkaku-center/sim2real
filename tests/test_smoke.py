"""Environment smoke test: MuJoCo installs and steps deterministically on this OS.

This is intentionally minimal — real determinism assertions against
models/sesame.xml arrive with Stage 0 task 3 (tests/test_determinism.py).
"""

import mujoco
import numpy as np

_PENDULUM_XML = """
<mujoco>
  <option timestep="0.002"/>
  <worldbody>
    <body pos="0 0 1">
      <joint name="hinge" type="hinge" axis="0 1 0"/>
      <geom type="capsule" fromto="0 0 0 0 0 -0.3" size="0.02" mass="0.1"/>
    </body>
  </worldbody>
</mujoco>
"""


def test_mujoco_steps_deterministically():
    def run() -> np.ndarray:
        model = mujoco.MjModel.from_xml_string(_PENDULUM_XML)
        data = mujoco.MjData(model)
        data.qpos[0] = 0.5  # start off-equilibrium so dynamics are non-trivial
        for _ in range(1000):
            mujoco.mj_step(model, data)
        return data.qpos.copy()

    a, b = run(), run()
    assert np.array_equal(a, b), "identical runs must be bit-identical"
    assert np.all(np.isfinite(a))
    assert a[0] != 0.5, "pendulum should have moved"
