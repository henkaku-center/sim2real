# Sesame motion space — November 13, 2026

Simulation-derived. Numbers live in `manifest/motion_space.yaml`; the code is
`sim/motion_space.py`; `uv run python -m sim.motion_space` recomputes them and
`tests/test_motion_space.py` checks them against MuJoCo. Nothing here has been
measured on a physical robot. It inherits the assumed joint signs and soft
limits of `manifest/robot.yaml`, the box collision geometry and estimated
masses of `models/sesame.xml`, and the placeholder servo gain (0.6 N·m/rad)
and stall torque (0.176 N·m).

## Why eight servos are not eight free axes

The hips sweep the legs horizontally and the feet pitch the paddles, so a
pose stands only if all of the following hold. These were found by sampling
the 8-D joint box and letting MuJoCo settle each pose:

- **Uniform joint sampling mostly fails.** Only about 10% of uniformly random
  joint vectors stand: the torso lands on the floor or the robot tips.
- **Paws on one side of the centre of mass tip it over.** For example, all
  four paws swept forward. Rule: centre of mass ≥ 10 mm inside the paw
  polygon.
- **Uneven paw heights rock the body onto three legs.** Fix: the foot angles
  are not free axes. Inverse kinematics solves them so that every paw touches
  the floor for a commanded height, pitch and roll.
- **Flat paddles (foot < 30°) overload the foot servos.** The body sags, and
  with asymmetric hips it creeps several mm/s while "standing still". Rule:
  every supporting foot ≥ 30°.
- **Same-side legs collide** when the front and back hips both sweep inward.
  The front+back hip sum must be ≥ about −25°. Rule: ≥ −20°. Left/right legs
  and single legs never self-collide inside the soft limits.
- **The torso and femurs must clear the floor.** Rule: ≥ 5 mm.
- **Reach is short.** The paw is at most ~49.5 mm below the hip plane. This,
  rather than torque, is what limits pitch and roll.

## The axes

Hip axes are symmetric patterns of paw forward sweep, in degrees around the
`stand` X-stance (all hips 45°). Feet are solved from body attitude.

| axis | meaning | alone, from centre |
|---|---|---|
| surge | all paws forward (body shifts back) | ±45° |
| spread | front paws forward, back paws back | −55…+45° |
| yaw | right paws forward, left back (twists body on its paws) | ±45° |
| stride | FR/BL forward, FL/BR back (the trot stroke) | ±45° |
| height | torso centre above floor | 34…49.5 mm (centre 42) |
| pitch | nose up | ±6.25° at 42 mm |
| roll | right side up | ±6.25° at 42 mm |
| lift | raise FR/BL (+) or FL/BR (−) paws | ±15 mm (gait only) |

The axes share servos, so combinations are narrower than each axis alone.
Rather than an axis-aligned box, the feasible set has a simple inner
**budget**. Every pose inside it passes all rules; 3000 random samples are
checked in the tests, and 16 000 were checked during exploration:

- `|surge| + |spread| + |yaw| + |stride| ≤ 45°`. Each hip servo sees the
  signed sum of the four patterns.
- `36 ≤ height ≤ 48 mm` and `|pitch| + |roll| ≤ 0.75 × tilt_by_height(height)`.
  Tilt room peaks at ~6.5° near 42–44 mm and vanishes at 34 mm and 49.5 mm.
- `|lift| ≤ 12 mm`.

`project(z)` handles anything outside the budget. It scales the pose's offset
from the centre until every rule holds, so a too-wild motion keeps its shape
and gets smaller. In MuJoCo, 800/800 random feasible poses (seed 0) held as
commanded: attitude within 4°, height within 6 mm, no body contact, drift
< 2 mm, peak servo load < 50% stall.

Not certified: at a lower height with symmetric hips, steeper tilts hold in
simulation (38 mm, pitch 12°, foot 13°). With asymmetric hips those flat
paddles creep, so the rule excludes them.

## Gaits

A diagonal trot is two axes: `stride` (or `spread`) oscillates at `hz`, and
`lift` leads it by a quarter cycle (`sim.motion_space.gait`). It is driven
like the host spine: 20 Hz `pose` frames, 300°/s slew as in the S3 firmware
`RUN_RATE`. Lift is 10 mm.

| hz | forward mm/s, stride 5/10/20/30° | turn °/s, steer 5/10/20/30° |
|---|---|---|
| 0.5 | 6 / 14 / 27 / 39 | 6 / 12 / 25 / 38 |
| 1 | 12 / 26 / 51 / 79 | 12 / 25 / 50 / 75 |
| 2 | 41 / 74 / 135 / 150 | 24 / 48 / 97 / 149 |
| 3 | 46 / 96 / 137 / 77 | 31 / 69 / 145 / 142 |

- Forward ≈ 2.6 × stride × hz mm/s and turn ≈ 2.4 × steer × hz °/s.
  Both hold until the hip slew demand `2π·hz·(|stride|+|steer|)` passes
  300°/s; past that, speed drops.
- Negative stride walks backward. Negative steer turns right. Mixing stride
  and steer walks an arc: stride 20 with steer 10 at 2 Hz gives 122 mm/s
  at 44°/s.
- Turning comes from `spread`, not `yaw`. In a trot the two diagonals must
  sweep in opposite yaw senses, which is the front/back pattern. Oscillating
  `yaw` itself turns only 1–3°/s.
- Lift below ~4 mm scuffs. Lift 0 does not move at all.
- For comparison, the stock firmware `walk` makes 54 mm/s in the same
  simulation.

Simulated floor friction is 0.9 and the servos are idealised. Treat the
speeds as relative, not as predictions for a real table.

## Next hardware checks

Record the results in `DECISIONS.md` when measured:

1. Command the centre (`firmware_pose({})`, firmware
   `135 45 45 135 ~45 ~135 ~45 ~135`) and the budget corners. Watch for
   sag, creep and leg collisions.
2. Run `gait(t, 1, stride=10, lift=10)` slowly, and compare its direction
   with the sign conventions.
3. Measure the real hip-pair collision angle and the foot angle below which
   the robot sags. Then update `rules` and rerun the report.
