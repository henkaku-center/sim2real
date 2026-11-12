# Held body-v1 provenance

Updated November 12, 2026. The body-v1 report is held at `FAIL-DRAFT`. This page
records how its inputs are pinned. It is not approval to print, release the body
preview or move hardware.

## Current baseline: validator rerun of November 12, 2026

The instructor's decision of November 12 (DECISIONS.md D24) changed
`manifest/robot.yaml`: hip `limits_deg` became L1/R2 0–100 and R1/L2 80–180,
`mcu.board` became the course S3, and `8d75c0ea0b2c68e7` joined the readable
calibration identities. Joint limits are an effective input of the body job:
`tools/check_body.py::make_job` samples each joint across its manifest range.
This was therefore not a metadata refresh. The validator was run again.

The same day the manifest gained typed joint directions (`points_at_deg`,
`fitted_travel_deg`), a corrected convention comment and the course body in
`hardware_revision.printed_parts`. Those edits leave the body job numerically
the same. They are still manifest differences outside the tool's exact-delta
list, which is empty, so the validator ran a second time on the final manifest.
The baseline is that second run.

**Runs.** `uv run python tools/check_body.py`, the command in
`reference/BODY-CAD.md`, on macOS x86-64 with `/Applications/FreeCAD.app`:
FreeCAD 1.1.3 (build `145529fe`), OCCT 7.8.1, Python 3.11.14, motion checks with
python-fcl 0.7.0.11. This is the build recorded in the October report. Each run
exits with code 1, because the draft still fails acceptance.

| Run | Commit | Manifest SHA-256 | Wall time |
|---|---|---|---|
| First rerun (hip limits, board) | `cf8241d` | `3b38a3fe…` | 9 min 48 s |
| Second rerun (final manifest), the baseline | `828862d` | `a9ae157f…` | 9 min 4 s |

**Result.** `FAIL-DRAFT`, `geometry_pass: false`, `release_ready: false`. The two
reruns agree in every finding.

- Static results are unchanged from October: 6,732 body/component pairs with
  the same eight retained-interface findings, 36 body/body pairs without
  intersection, fastener alignment 12/12, wall findings on the retained frame
  and bottom cover.
- Sampled motion: 9,648 pairs and 38 findings, against 10,656 and 58 in October.
  Hips are sampled from −10° to +90° instead of −45° to +90°. All 8,784 rows
  present in both reports have the same status and distance. Of the 58 October
  findings, 26 belonged to poses that are no longer sampled (hips at −45° and
  −40°, and the coupled midpoint at 22.5°) and 32 remain. Six rows are new: the
  coupled midpoint is now 40°, inside the upper-leg contact with the retained
  frame already recorded for hips at +20° to +60°. All 38 are against the
  retained frame; none involves a new body part.
- Exports: in the baseline run every STEP, STL and 3MF file, the scene and the
  static findings are byte-identical to their October versions. Five generated
  files differ, all of them motion results: `report.json`, `rom-animation.json`,
  `index.html`, `rom-preview.gif` and `rom-sweep.png`. `v1/README.md` was edited
  by hand to state the result.
- The first rerun wrote eleven part files differently: the four riser STL/3MF
  pairs with the same vertices, area and volume in another triangle order, and
  the frame, bottom and assembled STEP files with the same solid, face, edge and
  vertex counts and bounds, volumes equal within 2e-9 mm³. The second run
  returned to the October bytes, so that was run-to-run variation of the
  exporter with the same geometry, not an effect of the manifest.

**How it is recorded.**

- Commit `828862d1442db375b68e6594a39d6773eac281d4` holds the validator's
  canonical report, without a revalidation record, next to the manifest it
  executed. `tools/revalidate_body_provenance.py` names that commit, the report
  digest, the digest of the preserved-file map and the eight consumer hashes,
  which are unchanged since October. Commit `cf8241d` holds the first rerun and
  stays in history as a superseded baseline.
- `ALLOWED_MANIFEST_CHANGES` is empty and the method is
  `executed-manifest-exact-v4`. The committed manifest is byte for byte the
  executed one and no difference is excepted. The five firmware-only deltas that
  method v3 excepted against the October run are part of the executed manifest
  now. A later manifest edit, firmware metadata included, fails verification
  until it is audited and listed as an exact delta, or the validator runs again.
- The committed report carries the `input_revalidation` record written by the
  tool's `--write`. Its `validator_executed: false` describes that write step,
  which runs no geometry. Removing the record reconstructs the baseline report
  byte for byte.
- `tests/test_body_provenance.py` keeps every rejection case. Cases that relied
  on the v3 delta list run against a fixture delta list, and the fields v3
  excepted are tested as effective inputs.

```sh
python tools/revalidate_body_provenance.py  # read-only verification
# With explicit provenance-repair authority, after an audited exact delta:
python tools/revalidate_body_provenance.py --write --baseline 828862d1442db375b68e6594a39d6773eac281d4
python -m pytest -q tests/test_body_provenance.py tests/test_body_cad.py
```

Verification needs no history. `--write` reads the baseline report from that
commit, so the commit stays reachable when this change is merged with a merge
commit, as earlier pull requests were.

In CI the body-CAD job takes the full FreeCAD route for this change and ends at
its fit-acceptance step, as every full run of the held draft has. That step
reports the draft's `FAIL-DRAFT`; it is a result, not a waived failure. On the
first rerun's commit both CI runners reproduced the committed numbers.

## Earlier baseline: October 5 run and its metadata refreshes

Kept as history. The method v3 exception list described here is no longer in
the tool; the rerun above replaced that baseline.

Updated October 25, 2026. This is **metadata revalidation, not a geometry-validator rerun**
and not approval to print, release the body preview or move hardware.

### Cause

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

The October 25 course OE correction changes only the firmware selector `oe`
from 18 to 7 and extends the exact saved-record compatibility list to
`[e669b916d178ac0a, bd7675604b98ae46]`. All eight pinned body consumers were
rechecked at `4cebb23`; none consumes those fields. No body parameter, joint,
pose, range, transform, source asset or geometry-consumer code changes with
this correction. The original report/execution identities are still the baseline.

The audit rechecked all eight original consumer hashes. `sim/manifest.py`
constructs joints and neutral from their unchanged fields (and exposes poses
through `pose_internal`). `tools/check_body.py::make_job` uses those joints,
signs, ranges and fixed geometry transforms to construct its ROM job; its only
use of the complete YAML file is its raw provenance hash. The pinned MJCF,
asset-preparation, CAD, detector, motion and renderer code does not consume the
allowed firmware metadata fields. None of that consumer code was changed
to obtain equivalence.

The original and current manifests also produce identical `make_job` numerical
payloads (four legs, 296 ROM samples) when raw provenance hashes are excluded
from that comparison. This is input/job equivalence, not a rerun of geometry
acceptance. In particular, a physical clock-measurement jumper is not newly
modeled or certified for body fit by this metadata repair.

### Proof and reader semantics

`tools/revalidate_body_provenance.py` now uses
`unused-s3-firmware-metadata-v3`: three exact additions (the existing Tim pulse
profile, GPIO4 input and two-ID compatibility list) and the exact status-label
and OE18→7 replacements against the original execution manifest. Its
`allowed_manifest_changes` records their paths, typed values and original label.
It does not ignore the whole hardware profile or permit arbitrary values even
within those five keys. It rejects missing keys, other GPIO values, widened
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
provenance allowlist plus the exact non-geometry OE firmware companion paths
audited in `4cebb23..1aea3c8`. No firmware/reference directory-wide exemption is
used. The companion list includes this change's generated contract, generator,
focused firmware tests and named documents; it does not admit new helper files,
body tests, assets or geometry consumers.

**Path eligibility alone never selects that route.** Before classification the
job provides pinned PyYAML, then verifies the checked-out proof, exact manifest
delta, original report reconstruction, all pinned consumer/source/export hashes
and held flags. The same proof/rejection tests run again as the metadata job's
required check on both OSes. The main CI job retains firmware tests/builds.
Missing dependencies or LFS data, malformed/stale proofs, altered geometry
inputs/consumers/assets, unknown paths or missing comparison refs retain the
existing full CAD path. Workflow changes alone cannot select the narrow path.
The matrix has two bounded jobs with separate runner filesystems.

This corrects OE PR #5's classification: run `40170704312` selected full CAD
merely because the manifest/proof repair accompanied firmware documents and
generated constants. Its known held FAIL-DRAFT results remain results, not
successes or waived failures. A successful metadata-only job means unchanged
audited body inputs and preserved failure evidence, **not successful body fit**.
Full detector and fit-acceptance steps are retained unchanged for genuine or
unclassified geometry changes; no `continue-on-error` or acceptance bypass is
introduced.

A future genuine body redesign/regeneration requires its own review and a new
execution/provenance contract; this held snapshot cannot silently certify it.
The hardware observation/mapping wait and assembly-animation/body-preview holds
remain separate from repairing repository provenance freshness.
