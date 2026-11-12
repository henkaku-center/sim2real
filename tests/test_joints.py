"""tools/joints.py: ask what a joint does before commanding it, check targets before sending.

Run as a student or assistant would: a plain interpreter without site-packages.
The cases are the ones from 12 November 2026: a rear hip turned toward the
front, a hip driven to 180, and symmetric sweeps about 90 on fitted hips.
Nothing here opens a device.
"""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_design  # noqa: E402
import joints  # noqa: E402
import leg_clearance as lc  # noqa: E402

DESIGN = "internal-frame-s3"
HIPS = {"L1": [0, 90], "R1": [90, 180], "L2": [90, 180], "R2": [0, 90]}


def run(*args, root=None):
    """The command line, standard library only (-S: no site-packages)."""
    command = [sys.executable, "-S", str(ROOT / "tools/joints.py")]
    if root is not None:
        command += ["--root", str(root)]
    return subprocess.run(command + [str(a) for a in args], capture_output=True, text=True, cwd=ROOT)


def query(name):
    result = run("query", name)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def manifest():
    return yaml.safe_load((ROOT / "manifest/robot.yaml").read_text())


# ------------------------------------------------------------------- query

def test_query_l2_says_where_it_points_how_far_it_travels_and_what_stops_it():
    answer = query("L2")
    assert answer["where"] == {"leg": "back_left", "role": "hip", "words": "rear-left hip"}
    assert answer["rest_deg"] == 90
    assert answer["points_at_deg"] == {"0": "forward", "90": "out_left", "180": "back"}
    assert answer["in_words"] == {"0": "leg forward", "90": "leg straight out to the left", "180": "leg backward"}
    assert answer["fitted_travel_deg"] == [90, 180] and "One way only" in answer["fitted_travel_words"]
    assert answer["soft_limits_deg"] == [80, 180] and answer["sign"] == 1
    assert answer["hub_channel"] == {"default": 1, "status": "recommended-default-not-physically-verified",
                                     "hardware_verified": None}
    beyond = answer["beyond_fitted_travel"]
    assert beyond["side"] == "below 90°" and beyond["direction"] == "forward, toward the middle of the body"
    assert beyond["cad_first_contact"]["partner"] == "head-cover"
    assert beyond["cad_first_contact"]["degrees_past_rest"] == pytest.approx(13.0, abs=0.3)
    assert beyond["cad_first_contact"]["servo_deg"] == pytest.approx(77.0, abs=0.3)
    assert beyond["status"].startswith("CAD-derived") and "not measured" in beyond["status"]
    # What happened: L2 turned forward into the L1 leg. That contact is not in the CAD sweep.
    assert beyond["neighbouring_leg"] == "L1" and "not modelled" in beyond["leg_to_leg"]
    evidence = answer["evidence"]
    assert "2026-11-12" in evidence["directions"]["source"] and "instructor" in evidence["directions"]["kind"]
    assert evidence["contact"]["kind"] == "CAD-derived, not physical" and evidence["contact"]["design"] == DESIGN
    assert evidence["measured_on_your_robot"] == "nothing"
    assert evidence["limits_sign_channel"]["manifest_id"] == "fe108150ee38fa10"
    for phrase in ("one observed movement", "wiring, signs or horn positions", "never opens", "Bench mode accepts any angle"):
        assert phrase in answer["scope"], phrase


def test_query_all_matches_the_manifest_joint_by_joint(manifest):
    answer = query("all")
    names = [joint["name"] for joint in manifest["joints"]]
    assert list(answer["joints"]) == names == answer["pose_order"] == ["R1", "R2", "L1", "L2", "R4", "R3", "L3", "L4"]
    channels = manifest["hardware_profiles"]["sesame_s3"]["intended_channels"]
    for joint in manifest["joints"]:
        entry = answer["joints"][joint["name"]]
        assert entry["where"]["leg"] == joint["leg"] and entry["where"]["role"] == joint["role"]
        assert entry["points_at_deg"] == {str(deg): joint["points_at_deg"][deg] for deg in (0, 90, 180)}
        assert entry["fitted_travel_deg"] == joint["fitted_travel_deg"]
        assert entry["soft_limits_deg"] == joint["limits_deg"] and entry["sign"] == joint["sign"]
        assert entry["hub_channel"]["default"] == channels[joint["name"]]
        assert entry["hub_channel"]["hardware_verified"] is None
    hips = {name: entry for name, entry in answer["joints"].items() if entry["where"]["role"] == "hip"}
    assert {name: entry["fitted_travel_deg"] for name, entry in hips.items()} == HIPS
    assert {name: entry["where"]["words"] for name, entry in hips.items()} == {
        "L1": "front-left hip", "R1": "front-right hip", "L2": "rear-left hip", "R2": "rear-right hip"}
    for name, entry in hips.items():
        # Beyond the travel every hip turns toward the middle and meets the head cover first, in CAD.
        assert entry["beyond_fitted_travel"]["direction"].endswith("toward the middle of the body")
        assert entry["beyond_fitted_travel"]["cad_first_contact"]["partner"] == "head-cover"
        assert entry["beyond_fitted_travel"]["neighbouring_leg"] == {"L1": "L2", "L2": "L1", "R1": "R2", "R2": "R1"}[name]
    # Front hips: the shallow frame band inside the travel is reported, not hidden.
    for name in ("L1", "R1"):
        (band,) = hips[name]["within_fitted_travel"]["cad_overlap_bands"]
        assert band["partner"] == "internal-frame" and band["max_overlap_mm"] < 0.5
    for name in ("L2", "R2"):
        assert hips[name]["within_fitted_travel"]["cad_overlap_bands"] == []
    for name in ("L3", "R3", "L4", "R4"):
        entry = answer["joints"][name]
        assert entry["fitted_travel_deg"] == [0, 180] and entry["within_fitted_travel"]["cad_contact_free"] is True
    assert answer["joints"]["L3"]["in_words"]["0"].startswith("foot down")
    assert answer["joints"]["R3"]["in_words"]["0"] == "foot up"


def test_unknown_joint_is_an_error_not_a_guess():
    result = run("query", "L9")
    assert result.returncode == 2 and "Unknown joint" in json.loads(result.stderr)["error"] and result.stdout == ""


# ------------------------------------------------------------------- check

@pytest.mark.parametrize("args,phrases", [
    (["L2", 0], ["L2 0° turns the rear-left leg forward, toward the middle of the body; fitted travel is 90–180°",
                 "head cover", "toward the L1 leg"]),
    (["R2", 180], ["R2 180° turns the rear-right leg forward, toward the middle of the body; fitted travel is 0–90°",
                   "Contact between two legs is not modelled"]),
])
def test_todays_two_commands_are_refused(args, phrases):
    result = run("check", *args)
    assert result.returncode == 1
    assert result.stdout.startswith("NOT OK: ") and "nothing was sent" in result.stdout
    for phrase in phrases:
        assert phrase in result.stdout, phrase


@pytest.mark.parametrize("args", [
    ["L1", 90, 0, 90], ["R1", 90, 180, 90], ["L2", 90, 180, 90], ["R2", 90, 0, 90],
    # Standing, by name and in the firmware's `pose` order R1 R2 L1 L2 R4 R3 L3 L4.
    ["L1", 45, "R2", 45, "R1", 135, "L2", 135, "L3", 0, "R4", 0, "L4", 180, "R3", 180],
    ["pose", 135, 45, 45, 135, 0, 180, 0, 180],
    ["pose", 90, 90, 90, 90, 90, 90, 90, 90],
])
def test_fitted_travel_and_standing_pass(args):
    result = run("check", *args)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("OK: ") and len(result.stdout.strip().splitlines()) == 1
    assert "legs fitted" in result.stdout and "nothing was sent" in result.stdout


def test_standing_pose_in_the_manifest_is_what_the_check_was_given(manifest):
    stand = manifest["poses"]["stand"]
    assert [stand[name] for name in ("R1", "R2", "L1", "L2", "R4", "R3", "L3", "L4")] == [135, 45, 45, 135, 0, 180, 0, 180]


@pytest.mark.parametrize("name", sorted(HIPS))
@pytest.mark.parametrize("sweep", [(45, 135), (65, 115), (80, 100), (0, 180)])
def test_symmetric_sweeps_about_rest_fail_on_a_fitted_hip_and_pass_on_bare_horns(name, sweep):
    fitted = run("check", name, *sweep)
    assert fitted.returncode == 1
    low, high = HIPS[name]
    wrong = sweep[0] if low == 90 else sweep[1]                 # the half on the middle side of Rest
    assert f"NOT OK: {name} {wrong}° turns" in fitted.stdout and f"fitted travel is {low}–{high}°" in fitted.stdout
    assert fitted.stdout.count("NOT OK") == 1                   # the half on the fitted side is fine
    bare = run("check", "--bare-horns", name, *sweep)
    assert bare.returncode == 0
    assert "bare horns, legs off: the full 0–180° is allowed" in bare.stdout and bare.stdout.startswith("OK: ")


def test_the_ten_degrees_stock_walk_uses_are_reported_as_outside_the_travel():
    result = run("check", "R2", 100)
    assert result.returncode == 1 and "stops 3° short" in result.stdout
    assert "inside the soft limits 0–100° only because stock walk and point go there" in result.stdout


def test_feet_take_the_whole_range_and_nothing_takes_more():
    assert run("check", "L3", 0, 180, "R4", 0, 180).returncode == 0
    for flag in ([], ["--bare-horns"]):
        result = run("check", *flag, "L3", 181)
        assert result.returncode == 1 and "outside the servo's 0–180° range" in result.stdout


@pytest.mark.parametrize("args", [["Q9", 10], [90], ["L2"], ["pose", 90, 90], ["L2", "ninety"], ["L2", "nan"], ["L1", 10, "L2"]])
def test_malformed_requests_cannot_be_answered(args):
    result = run("check", *args)
    assert result.returncode == 2 and "error" in json.loads(result.stderr) and result.stdout == ""


def test_the_tool_imports_nothing_outside_the_standard_library():
    probe = ("import sys; sys.path.insert(0, 'tools'); import joints; "
             "bad = [m for m in ('yaml', 'numpy', 'trimesh', 'fcl', 'mujoco') if m in sys.modules]; print(bad)")
    result = subprocess.run([sys.executable, "-S", "-c", probe], capture_output=True, text=True, cwd=ROOT, check=True)
    assert result.stdout.strip() == "[]"
    # It reads committed files and prints; no device, network or process module is imported.
    tree = ast.parse((ROOT / "tools/joints.py").read_text())
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported == {"argparse", "hashlib", "json", "pathlib", "sys", "leg_clearance"}


# ------------------------------------------------------- current or no answer

def test_interface_names_the_manifest_bytes_it_was_generated_from():
    interface = json.loads((ROOT / joints.INTERFACE).read_text())
    for name, digest in interface["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert set(interface["source_sha256"]) == {"manifest/robot.yaml", "manifest/safeaction.yaml", "manifest/motions.yaml"}
    header = (ROOT / "firmware/sesame-s3/manifest_generated.h").read_text()
    assert f'MANIFEST_ID[] = "{interface["manifest_id"]}"' in header
    assert "tools/joints.py query" in interface["joint_directions"]["ask"]


@pytest.fixture
def copy_repo(tmp_path):
    """Just the committed data the tool reads; the tool itself runs from this checkout."""
    for name in [joints.INTERFACE, "manifest/robot.yaml", "manifest/safeaction.yaml", "manifest/motions.yaml"]:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, tmp_path / name)
    design = tmp_path / lc.PRINTING / DESIGN
    design.mkdir(parents=True)
    for name in ["assembly.json", lc.EVIDENCE] + [f"{part}.stl" for part in lc.BODY_PARTS]:
        shutil.copy(ROOT / lc.PRINTING / DESIGN / name, design / name)
    shutil.copytree(ROOT / lc.LEGS, tmp_path / lc.LEGS)
    return tmp_path


def refused(root, needle):
    for command in (["query", "L2"], ["check", "L2", 90, 180, 90]):
        result = run(*command, root=root)
        assert result.returncode == 2 and result.stdout == "", command
        assert needle in json.loads(result.stderr)["error"], result.stderr
    return True


def test_copy_answers_like_the_checkout(copy_repo):
    assert json.loads(run("query", "all", root=copy_repo).stdout) == query("all")
    assert run("check", "L2", 0, root=copy_repo).returncode == 1


def test_manifest_edit_makes_the_interface_stale(copy_repo):
    with (copy_repo / "manifest/robot.yaml").open("a") as out:
        out.write("\n# a later edit\n")
    assert refused(copy_repo, "Stale firmware interface: manifest/robot.yaml changed")


def test_interface_without_source_hashes_or_missing_is_refused(copy_repo):
    path = copy_repo / joints.INTERFACE
    data = json.loads(path.read_text())
    del data["source_sha256"]
    path.write_text(json.dumps(data))
    assert refused(copy_repo, "records no manifest hashes")
    path.unlink()
    assert refused(copy_repo, "Cannot read reference/sesame-s3-interface.json")


def test_changed_or_missing_leg_clearance_evidence_is_refused(copy_repo):
    design = copy_repo / lc.PRINTING / DESIGN
    stl = design / "head-cover.stl"
    original = stl.read_bytes()
    stl.write_bytes(original + b"\0")
    assert refused(copy_repo, "Stale leg-clearance evidence for internal-frame-s3: head-cover.stl changed")
    stl.write_bytes(original)
    assert run("query", "L2", root=copy_repo).returncode == 0
    (design / lc.EVIDENCE).unlink()
    assert refused(copy_repo, "Stale leg-clearance evidence")


def test_git_lfs_pointers_are_checked_by_the_hash_they_name(copy_repo):
    """A checkout without the large files still proves the evidence current, or stale."""
    design = copy_repo / lc.PRINTING / DESIGN
    stl = design / "internal-frame.stl"
    digest = hashlib.sha256(stl.read_bytes()).hexdigest()
    pointer = "version https://git-lfs.github.com/spec/v1\noid sha256:{}\nsize {}\n"
    stl.write_text(pointer.format(digest, 1017484))
    assert run("check", "L2", 90, 180, root=copy_repo).returncode == 0
    stl.write_text(pointer.format("0" * 64, 1017484))
    assert refused(copy_repo, "internal-frame.stl changed")


def test_directions_that_contradict_the_cad_free_side_are_refused(copy_repo):
    """Regenerated-looking data that disagrees with itself is not answered either."""
    path = copy_repo / joints.INTERFACE
    data = json.loads(path.read_text())
    next(j for j in data["joint_map"] if j["name"] == "L2")["fitted_travel_firmware_deg"] = [0, 90]
    path.write_text(json.dumps(data))
    assert refused(copy_repo, "L2: manifest directions and leg-clearance evidence disagree")


@pytest.mark.parametrize("current", [True, False])
def test_check_design_fails_when_the_joint_query_cannot_answer(monkeypatch, capsys, current):
    stub = SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
                           TimeoutExpired=check_design.subprocess.TimeoutExpired)
    monkeypatch.setattr(check_design, "subprocess", stub)
    if not current:
        def stale(root=ROOT, design=joints.COURSE_BODY):
            raise joints.CannotAnswer("Stale firmware interface: manifest/robot.yaml changed")
        monkeypatch.setattr(joints, "load", stale)
    code = check_design.main()
    output = json.loads(capsys.readouterr().out)
    check = next(c for c in output["checks"] if c["name"] == "joint-query-data")
    assert (code, output["ok"], check["ok"]) == ((0, True, True) if current else (1, False, False))
    if current:
        assert check["result"] == {"ask": "python3 tools/joints.py query NAME | check NAME DEG ...",
                                   "manifest_id": "fe108150ee38fa10", "contact_design": DESIGN}
    else:
        assert "Stale firmware interface" in check["error"]
