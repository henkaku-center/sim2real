# Real-to-sim run logs

Run logs (`*.jsonl`, schema `sesame-run-log` v1) recorded against a physical
robot belong here; see `../../REAL2SIM-CAPTURE.md`. **There are none yet.**
`tools/check_design.py` reports "no measured run recorded" until a log with
`"evidence": "measured"` and a torso track is committed. Synthetic and dry-run
logs do not belong in this directory. Videos stay out of the repository unless
they go through Git LFS.
