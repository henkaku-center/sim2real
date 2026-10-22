# Held body-v1 provenance refresh

Updated October 22, 2026. This is **metadata revalidation, not a geometry-validator rerun**
and not approval to print, release the body preview or move hardware.

## Cause

The body report was generated at `b38d4b3`. Commit `71af7e0`, owned by this
APS/sim2real instruction/firmware session, subsequently added only
`hardware_profiles.sesame_s3.pulse_profile` to `manifest/robot.yaml`. The report
hashed that entire file, although its audited body pipeline consumes unchanged
joint/neutral/geometry inputs and does not consume the added pulse profile.
PR #1's original CI run `39035777714` failed the freshness check on both OSes.
Those failures remain recorded; no check has been waived or suppressed.

The October 22 clock/bench firmware update merged as `1d796d6` added
`clock_measure_gpio: 4`, added
`calibration_compatible_manifest_ids: [bd7675604b98ae46]`, and changed only the
`intended_channels_status` label to `recommended-default-not-physically-verified`.
Its comment edits are also included in the current raw hash. The actual
`intended_channels` values and `initial_limits_deg` did **not** change; neither
did joint definitions, neutral, poses or geometry parameters. CI run
`39730152485` exposed the resulting stale raw hash and the old single-addition
proof's deliberate rejection on both OSes. This is a new dependency regression,
not a rerun or waiver of the earlier provenance work.

The audit rechecked all eight original consumer hashes. `sim/manifest.py`
constructs joints and neutral from their unchanged fields (and exposes poses
through `pose_internal`). `tools/check_body.py::make_job` uses those joints,
signs, ranges and fixed geometry transforms to construct its ROM job; its only
use of the complete YAML file is its raw provenance hash. The pinned MJCF,
asset-preparation, CAD, detector, motion and renderer code does not consume the
four allowed firmware metadata fields. None of that consumer code was changed
to obtain equivalence.

The original and current manifests also produce identical `make_job` numerical
payloads (four legs, 296 ROM samples) when raw provenance hashes are excluded
from that comparison. This is input/job equivalence, not a rerun of geometry
acceptance. In particular, a physical clock-measurement jumper is not newly
modeled or certified for body fit by this metadata repair.

## Proof and reader semantics

`tools/revalidate_body_provenance.py` now uses
`unused-s3-firmware-metadata-v2`: three exact additions (the existing Tim pulse
profile, GPIO4 input and single compatibility-ID list) and the one exact status
label replacement against the original execution manifest. Its
`allowed_manifest_changes` records their paths, typed values and original label.
It does not ignore the whole hardware profile or permit arbitrary values even
within those four keys. It rejects missing keys, other GPIO values, widened
compatibility lists, altered pulse profiles, claimed physical verification,
channel-map changes, logical-limit changes and unrecognized metadata.

The exception remains pinned to the specific original report and consumer-code
hashes. It rejects all other semantic
manifest changes, changed validator/manifest-reader code, body parameters,
frozen sources, geometry/export files, altered findings or changed release flags.

The refreshed `report.json.input_hashes` keeps the existing raw-byte freshness
semantics for current readers. The appended `input_revalidation` explicitly says
`validator_executed: false` and retains the original commit, report digest, original
input hashes and complete original manifest. Removing that record and restoring
its original input hashes reconstructs the original execution report byte-for-byte.
The proof binds every body file except the self-referential report, frozen inputs,
declared source assets, original generator inputs and the audited manifest reader.
The original `FAIL-DRAFT`, `geometry_pass: false`, `release_ready: false` and all
findings remain unchanged. No STL, STEP, mesh, picture or fit result is regenerated.

Verification works on a shallow checkout; the proof contains the original input
snapshot. Creating/recreating it requires the original git objects and hydrated
current LFS assets. The source commit, original report/consumer hashes and complete
original preserved-file digest map are pinned in the tool. Updating an asset and
its claimed proof hash together cannot relabel it as original. This is not a
generic way to bless arbitrary stale reports.

```sh
python tools/revalidate_body_provenance.py  # read-only verification
# Only with explicit provenance-repair authority:
python tools/revalidate_body_provenance.py --write --baseline b38d4b3d249f9c09171277f01ba4b387f7660578
python -m pytest -q tests/test_body_provenance.py
# Affected existing contracts only; no FreeCAD/export or full fit invocation:
python -m pytest -q tests/test_body_cad.py -k 'frozen_leg_and_servo_interfaces or committed_body_review_is_fresh_and_complete or rom_job_uses_manifest_ranges_and_moves_both_links'
```

## Scoped CI

The ordinary freshness test is unchanged. Normal Linux/macOS CI still runs it
and the new proof/rejection tests. The body-CAD job uses a metadata-only route
only when the change set contains the report and is wholly within the explicit
provenance helper/test/document/workflow allowlist. That route runs proof and
negative controls on both OSes, without invoking FreeCAD, FCL or rendering.
Mixed geometry/manifest changes, unknown paths or missing comparison refs retain
the existing full CAD path. Workflow changes alone cannot select the narrow path.
The matrix has two bounded jobs with separate runner filesystems.

A future genuine body redesign/regeneration requires its own review and a new
execution/provenance contract; this held snapshot cannot silently certify it.
The hardware observation/mapping wait and assembly-animation/body-preview holds
remain separate from repairing repository provenance freshness.
