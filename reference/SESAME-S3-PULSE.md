# CH0 electrical loopback

Use CH0 **SIGNAL → GPIO4 (F17)**, with the CH0 servo unplugged and the
existing shared ground. PCA logic VCC is 3.3 V; never connect servo V+ to GPIO4.
USB-only fixture, battery disconnected. GPIO4 is an input with pulldown.

This extends the clock-capture branch to observe the actual CH0 waveform,
including falling edges. It does not substitute commanded-angle telemetry for
measurement. It uses the existing SafeAction channel mode and pulse profile;
calibration/NVS are unchanged. The legacy `clock measure` still uses CH15.

With a live USB heartbeat (at least every 200 ms):

```text
off
arm channel 0
us 1615.28
```

Wait for the target to settle (check `status`), then:

```text
pulse measure
pulse status
```

Poll status with heartbeats until that generation is terminal. A complete capture
contains 101 rising edges and 100 high pulses. Frequency and high times come from
GPIO4 ISR timestamps, not the commanded pulse. CH0 ON/OFF registers are read back
at capture start; they establish programmed values, not physical voltage levels.
The source channel is the declared jumper fixture, not auto-detected wiring.

Completion, 4-second timeout, USB disconnect, malformed/conflicting commands,
I2C fault, BOOT abort or heartbeat expiry switch outputs off. `off`, `stop`,
`pulse abort` and `clock abort` also stop capture. Do not change the target during
capture. Repeat from `arm channel 0` with `us 1566.48` for a second duty cycle.

Compare frequency, mean/min/max high time and register ticks between captures.
No edges is a diagnostic outcome, not proof of a broken servo or absent power:
check the actual jumper, OE, signal voltage and channel identity. Measurements
are relative to the ESP32 clock; ISR latency adds pulse-width uncertainty.
No oscillator or joint calibration is automatically saved.

For a control measurement, send `off`, then `pulse listen` with heartbeats and
poll `pulse status`. This leaves **all PCA outputs off** and reports channel=-1:
it observes GPIO4 without attributing any input activity to CH0. Pulses present
in this state require fixture/signal-path diagnosis before a servo trial.
