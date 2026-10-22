# CH0 loopback — October 22, 2026

User reported no servo movement and connected the requested CH0 SIGNAL → S3
GPIO4 jumper, USB attached. This session did not visually verify either endpoint
or measure voltage. Device USB/MAC: `90:da:72:73:8a:c8`.

## Firmware and validation

Built from `b8f077a` plus this branch's CH0 waveform/passive-capture extension.
Final app SHA-256:
`ae9c6a318e51c1e6e8b86774e0d213709c6165568790469c5615dad47610b55b`.
Pinned Arduino 1.5.1, ESP32 3.3.11, two compile jobs; native tests ran
independently with one compiler process. Final clean build: setup 2.012 s,
execution 103.790 s, total 105.803 s, no queue. Native timing/SafeAction and
generated-contract checks passed. macOS and final-head CI were not run here.

Uploaded the complete generated bootloader/partition/app recipe; all writes
reported hash verification. NVS `export` matched the pre-flash record exactly.
Manifest `bd7675604b98ae46`, oscillator 24985600 Hz, prescale 121, all joints
unmapped/unverified, all trims zero, limits 85–95°. No calibration was changed.

## Electrical observations

The earlier angle commands had only parser/target telemetry. This build reads
back PCA CH0 registers and timestamps GPIO4 CHANGE interrupts.

| Trial | CH0 ON / OFF registers | Observed result |
|---|---|---|
| Outputs-off control 1 | 0 / 4096 (full-off) | 0 edges over 4 s, timeout |
| Outputs-off control 2 | 0 / 4096 (full-off) | 0 edges over 4 s, timeout |
| Requested 1615.28 µs | 0 / 331 | 101 rising edges, 96 paired highs; mean high 5.219 µs, min 4, max 27; quality rejected |
| Requested 1566.48 µs | 0 / 321 | 101 rising edges, 98 paired highs; mean high 5.980 µs, min 5, max 6; quality rejected |

Both active captures were malformed; their computed mean frequency and
oscillator estimate are **not accepted measurements** and must not be saved.
The first active capture contained periods 3–97 µs; the second 3–20 µs.
An earlier capture on the initial extension build also had 4–5 µs highs and
was rejected. No valid ~50 Hz / ~1.6 ms servo waveform was established.

These observations do not establish a defective servo, PCA or wiring fault.
Short pulses resemble a bus-rate signal, but the passive controls were quiet;
signal identity, physical fixture and ISR capture integrity still need checking.
Next: obtain a clear view of both jumper endpoints, then discriminate the signal
path/capture with a known reference or independent instrument. Do not label the
software's requested width as a physically verified pulse.

All captures ended outputs-off; final status `mode=0 outputs=0 hub=1 fault=0`.
Logs and final build report accompany this note. No gait or all-servo motion ran.

## Subsequent instructor measurements

The instructor confirmed correct jumper placement, then reported **3.3 V on
A-side VCC** and only **30–40 mV on V+**, measured relative to GND both at the
side header and around the servo headers. These are human meter observations,
not telemetry inferred from the firmware. They establish an effectively
unpowered servo rail at the measured points and explain no servo movement.
They do not explain or validate the rejected GPIO waveform captures.

The next diagnostic is the S3 pin labelled 5V relative to the same hub GND.
The recorded carrier connects S3 socket A11 to converter O1 and hub socket A3
on the `output_5V` net; that model is not proof of actual continuity or of the
S3 module exposing USB power on its 5V pin. Keep the existing USB-only power
condition while locating where the 5V rail is absent.

An independent RMT diagnostic was started but paused before build/flash once
the missing V+ measurement arrived. The installed image remains the one hashed
above; no further firmware update or calibration write was performed.
