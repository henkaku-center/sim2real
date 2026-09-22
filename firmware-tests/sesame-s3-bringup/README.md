# S3 bring-up evidence — 2026-09-22

Exact diagnostic source snapshots used during the human-supervised APS-II course-build session.
These are bounded bench diagnostics, not the production controller or a general SafeAction interface.
Hardware state and restore information: [`reference/SESAME-S3-BUILD-STATE.md`](../../reference/SESAME-S3-BUILD-STATE.md).

| Sketch | Behavior / observed result |
|---|---|
| `i2c-scan` | GPIO2/3 scan, OE HIGH; repaired bus responded at 0x3C/0x40/0x70 |
| `oled-check` | Full-off PCA outputs; OLED message/frame counter visibly confirmed |
| `servo-button-test` | One BOOT release starts one selected channel at 90→95→90; outputs off at completion; next press aborts; instructor reported wrong joint order |
| `servo-load-test` | **Currently installed**; BOOT release starts all CH0–7 at 90°, three synchronized 95°/90° cycles, full-off after ~7 s; press aborts; instructor reported battery test completion |

The first move to 90° is an absolute target, not a measured five-degree change from the initial pose.
The load sequence is three small-range cycles, not a stall/max-current/sustained gait test. Physical
load, peak current and rail sag were not instrumented. Do not use these snapshots as evidence that
all new-board joints match the production mapping or that model-driven control is accepted.

Motion diagnostics are manually triggered only after USB is disconnected and the battery powers
the supported robot. They start with outputs off and write full-off registers as well as asserting
GPIO18/OE, whose physical wiring was not established. Button abort cannot replace physical power-off
if software/I²C fails. No standalone SafeAction integration was implemented in these snapshots.

All four sketches were compiled with `esp32:esp32:esp32s3:CDCOnBoot=cdc`, ESP32 Arduino core 3.3.11.
Adafruit libraries: PWM Servo Driver 3.0.3, SSD1306 2.5.17, GFX 1.12.6, BusIO 1.17.4.
Artemis has the built binaries under `~/sesame-bringup/2026-09-22/`.

`sesame-s3-cdc-bridge.c` is the session's derivative of `tools/karasu-usb-bridge/cdc_tcp_bridge.c`:
S3 endpoints 0x01/0x81, 64-byte bulk transfers and 20 ms read timeout. It completed a full flash backup
and initial diagnostic flash, but later write timeouts remain unresolved. Direct Artemis USB was
the successful final programming route. This snapshot is not a generic cross-device bridge.
