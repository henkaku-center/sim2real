# Tim's S3 servo-debug reference

Imported with the instructor's explicit permission to republish/adapt, confirmed
October 11, 2026. Author/source: Tim, `tim003/CIT_FC_Robotics`, revision
`98d030a2d1e2e2e1f195669a9f87fcf9c5f1d465`. `SOURCE.json` records per-file hashes.
The source repository has no declared licence; this notice records the specific
permission rather than assigning a new licence to Tim's unchanged files.

These are unmodified reference files, preserving their relative includes. They
are **not the classroom flash target**. The test sketch automatically repeats
0/90/180-degree commands. It has no interactive serial command protocol, per-device
calibration store, slew limit or external command watchdog. MG90S positions shown
on the OLED are commanded angles, not sensor readings.

Our maintained controller is `firmware/sesame-s3/`. The comparison and proposed
bench adaptation are in `reference/SERVO-BENCH-PLAN.md`. Do not flash the reference
sketch merely because its filename contains “test”. The course needs an explicitly
selected production-compatible pulse profile and a verified wired power setup.

Reproduce the import with `python3 tools/import_tim_servo_reference.py` using
authorised GitHub access. The classroom workflow will use these local files and
our own agent instructions, without requiring students to access Tim's repository.
