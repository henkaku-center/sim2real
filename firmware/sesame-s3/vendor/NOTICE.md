# Upstream assets

`face-bitmaps.h` is an unmodified Dorian Todd / Sesame Robot asset, Apache-2.0,
from the pinned September build input. See `provenance.json` for its commit and
SHA-256. The license is reproduced in `LICENSE`.

The controller implementation outside this directory is the APS S3 port. Its
stock poses and motion targets are generated from `manifest/robot.yaml` and
`manifest/motions.yaml`, whose original Sesame attribution is retained there.
Unlike upstream's blocking sequence execution, this controller waits for each
rate-limited target to settle before proceeding; motion timing is intentionally
slower for commissioning. Its command parser, web console, watchdog and NVS
overlay are new; it is not a drop-in Sesame Studio API implementation.
