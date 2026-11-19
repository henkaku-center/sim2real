# Wave reliability investigation — 16 November 2026

**Not accepted for deployment.** The revised command is a candidate, not a
physically validated fix. PR 81 in APS remains held. A green unit-test suite
does not override the separate, currently failing numerical acceptance gate.

## What the instructor observed

Grisha observed the built robot tipping forward and suggested moving a rear leg
before lifting the front-left leg. This is a qualitative physical observation.
It does not identify the centre of mass, exact contacts or installed command.
It is used to expose a failure case, not as independent validation of our fix.

## Candidate command

Stand; wait 200 ms; command R4=80°, L2=90°, R1=180°; wait 300 ms;
lift L3 to 180°; then wave L3 between 180° and 100° and return to standing.
Compared with the old command, the rear-right foot folds first and the
front-right hip moves forward rather than toward 100°. The hip change is an
additional simulated adjustment, not something the instructor reported testing.

The 54-case development grid moves the whole-robot centre of mass ±15 mm
fore/aft and ±8 mm laterally, switches collision boxes to convex mesh hulls,
and varies gain/friction in three paired settings. These are deliberately broad
engineering stress settings, not measured confidence intervals. They do not
cover every combination, servo speed, delay, backlash, cable force or build.
The candidate was selected using this grid; its results are not a held-out test.

The earlier score used only final posture and majority-time foot contact. It
could pass a robot that tipped and later recovered. The new diagnostics record
transient tilt, wave-phase foot contact, torso/floor contact, maximum penetration,
nonfinite states and solver warnings. Contact currently means the lower-leg
collision geometry touching the floor, not a measured load-bearing paw force.

## Blocking numerical result

At the two-eye design's rear/right centre-of-mass corner, with low gain/friction,
the same proposed wave gives these maximum floor penetrations:

| Timestep | Penetration |
|---|---:|
| 2 ms | 13.438 mm |
| 1 ms | 3.918 mm |
| 0.5 ms | 1.923 mm |

All three runs finish upright. They cannot be called equivalent or trusted for
contact prediction. The nominal base also penetrates 4.621 / 2.996 / 2.780 mm.
No physical measurement supports treating a rigid tabletop as this compliant.

Run the independent gate (expected **exit 1**, not a passing release check):

```sh
uv run python -m sim.robustness --check-wave
uv run python -m sim.robustness --check-wave --design internal-frame-s3-two-eyes
```

The full versioned results live in `reference/evidence/2026-11-16-wave/`.
Screening tolerances are explicitly engineering choices: ≤1 mm penetration,
≤20° wave-phase tilt, ≤1% waving-leg contact after the lift transition, no body
contact or solver warning; successive timestep results must agree within 1°
tilt, 0.25 mm penetration and 0.02 contact fraction. These are not product specs.
Do not widen them simply to accept the current solver.

## Why the probe changed

- After changing body centres of mass, call `mj_setConst` and reset before
  replay. Refresh kinematics/contacts after integration before sampling them.
- MuJoCo's default `solref` time constant is 20 ms: smaller values stiffen
  contact. A positive time constant should be at least twice the timestep.
- A diagnostic 4 ms contact time constant reduced nominal penetration, but
  2 ms and 0.5 ms simulations still differed (1.428 vs 0.641 mm). It was **not**
  promoted into the model or used to claim a fix. A contact-model investigation
  and independent hold-out cases are needed before merging the command.

Primary references, consulted 16 November 2026:

- https://mujoco.readthedocs.io/en/stable/modeling.html#solver-parameters
- https://mujoco.readthedocs.io/en/stable/programming/simulation.html#model-changes

## Release boundaries

No hardware was commanded or flashed. No motion, generated firmware or changed
physics has been deployed from this branch. The candidate firmware identity is
`eb2915398f599160`; the previous `fe108150ee38fa10` remains readable, preserving
saved calibration. The body-v1 provenance exception covers precisely that
additional readable identity; it does not relabel historical CAD as rerun.

Do not merge APS PR 81 on the strength of mass agreement or final posture alone.
Its browser contact model, transient behaviour and runtime cost still need
separate checks. Cable simulation follows after these findings are addressed.
