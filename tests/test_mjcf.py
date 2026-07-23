"""models/sesame.xml must stay in sync with the canonical manifest."""

import math

import mujoco
import pytest

from sim.build_mjcf import MODEL_PATH, build_xml
from sim.manifest import load_manifest


@pytest.fixture(scope="module")
def manifest():
    return load_manifest()


@pytest.fixture(scope="module")
def model():
    return mujoco.MjModel.from_xml_path(str(MODEL_PATH))


def test_committed_xml_matches_generator(manifest):
    assert MODEL_PATH.read_text() == build_xml(manifest), (
        "models/sesame.xml drifted from the manifest — "
        "regenerate with: uv run python -m sim.build_mjcf"
    )


def test_model_loads_with_expected_dofs(model):
    assert model.nu == 8, "8 position actuators"
    assert model.njnt == 9, "free root + 8 hinges"
    assert model.nq == 15  # 7 (free) + 8 hinges


def test_rig_sites_present(model):
    import mujoco as mj

    names = {
        mj.mj_id2name(model, mj.mjtObj.mjOBJ_SITE, i) for i in range(model.nsite)
    }
    legs = {"front_left", "front_right", "back_left", "back_right"}
    expected = {"torso_center", "face", "rear"} | {
        f"{leg}_{part}" for leg in legs for part in ("hip", "knee", "paw")
    }
    assert names == expected, "skeletal rig sites drifted"


def test_rig_forward_kinematics_at_rest(model):
    # At rest (q=0) the rig must match the STL-measured layout: paw tips
    # straight out sideways at hip height, wingspan = 2*(HIP_Y+UPPER+FOOT).
    import mujoco as mj

    from sim.build_mjcf import FOOT_LEN, HIP_X, HIP_Y, LEG_PLANE_DZ, SPAWN_Z, UPPER_LEN

    data = mj.MjData(model)
    mj.mj_forward(model, data)
    span = HIP_Y + UPPER_LEN + FOOT_LEN
    sid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, "front_left_paw")
    assert data.site_xpos[sid] == pytest.approx([HIP_X, span, SPAWN_Z + LEG_PLANE_DZ], abs=1e-9)
    sid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, "back_right_paw")
    assert data.site_xpos[sid] == pytest.approx([-HIP_X, -span, SPAWN_Z + LEG_PLANE_DZ], abs=1e-9)


def test_actuators_in_firmware_channel_order(model, manifest):
    names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
        for i in range(model.nu)
    ]
    assert names == [j.name for j in manifest.joints], (
        "actuator index must equal firmware servo channel"
    )


def test_ctrlranges_match_manifest_limits(model, manifest):
    for i, j in enumerate(manifest.joints):
        lo, hi = manifest.internal_range(j)
        assert model.actuator_ctrlrange[i][0] == pytest.approx(lo, abs=1e-5)
        assert model.actuator_ctrlrange[i][1] == pytest.approx(hi, abs=1e-5)


def test_angle_conversion_round_trip(manifest):
    for j in manifest.joints:
        for deg in (j.limits_deg[0], 90.0, j.limits_deg[1]):
            assert manifest.to_firmware(j, manifest.to_internal(j, deg)) == (
                pytest.approx(deg)
            )
        # Rest (90°) must be exactly q=0 for every joint.
        assert manifest.to_internal(j, 90.0) == 0.0


def test_stand_pose_is_left_right_mirror(manifest):
    stand = manifest.pose_internal("stand")
    for right, left in (("R1", "L1"), ("R2", "L2"), ("R3", "L3"), ("R4", "L4")):
        assert stand[right] == pytest.approx(stand[left]), (
            "internal angles must be mirror-symmetric in the stand pose"
        )
        assert abs(stand[right]) in (pytest.approx(math.pi / 4), pytest.approx(math.pi / 2))
