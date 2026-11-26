"""sim/motion_space.js (the viewer's model) must agree with sim/motion_space.py."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from sim.manifest import load_manifest
from sim.motion_space import (
    AXES,
    VIEWER_PATH,
    decode,
    firmware_pose,
    load_space,
    measures,
    project,
    viewer_data,
    viewer_html,
    violations,
    within_budget,
)

M = load_manifest()
JS = Path(__file__).parent.parent / "sim" / "motion_space.js"
NODE = shutil.which("node")


def _samples(n=300, seed=5):
    space, rng = load_space(), np.random.default_rng(seed)
    lo = np.array([space["ranges"][a][0] for a in AXES], dtype=float) * 1.3
    hi = np.array([space["ranges"][a][1] for a in AXES], dtype=float) * 1.3
    lo[AXES.index("height")], hi[AXES.index("height")] = 28, 54
    return [dict(zip(AXES, rng.uniform(lo, hi))) for _ in range(n)] + [{}, {"lift": 10}, {"pitch": 6}]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_javascript_port_matches_python(tmp_path):
    zs = _samples()
    script = tmp_path / "run.js"
    script.write_text(f"""
const {{ makeSpace }} = require({json.dumps(str(JS))});
const S = makeSpace({json.dumps(viewer_data())});
const zs = {json.dumps(zs)};
console.log(JSON.stringify(zs.map(z => {{
  const d = S.decode(z);
  return {{ q: d && d.q, fw: d && S.firmware(d.q), v: S.violations(z), m: S.measures(z),
           p: S.project(z), b: S.withinBudget(z) }};
}})));
""")
    out = json.loads(subprocess.run([NODE, str(script)], capture_output=True, text=True, check=True).stdout)
    for z, js in zip(zs, out):
        q = decode(z)
        if q is None:
            assert js["q"] is None, z
            continue
        assert js["q"] == pytest.approx(q, abs=1e-6), z
        clamped = [min(max(f, j.limits_deg[0]), j.limits_deg[1]) for f, j in zip(firmware_pose(z), M.joints)]
        assert js["fw"] == pytest.approx(clamped, abs=1e-6), z  # the viewer sends clamped poses
        assert js["v"] == violations(z), z
        m = measures(z)
        if m is not None:
            assert {k: js["m"][k] for k in m} == pytest.approx({k: float(v) for k, v in m.items()}, abs=1e-6), z
        assert js["p"] == pytest.approx(project(z), abs=1e-6), z
        assert js["b"] == within_budget(z), z


def test_committed_viewer_is_fresh():
    assert VIEWER_PATH.read_text() == viewer_html(), (
        "web/public/motion-space/index.html is stale — rebuild with: uv run python -m sim.motion_space --html")
