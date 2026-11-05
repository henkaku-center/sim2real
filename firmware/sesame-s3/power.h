// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdint.h>

namespace sesame {
// A servo's first pulse starts a full-speed move with a stall-current surge.
// Eight at once can sag a tired battery far enough to reset the MCU (brownout),
// which also drops the Wi-Fi AP. Stagger lets at most one channel go from
// full-off to pulsing per interval; pulsing channels and turn-offs pass through.
constexpr uint32_t STAGGER_DEFAULT_MS = 60; // effectively rounded up to the 20 ms PWM loop
constexpr uint32_t STAGGER_MAX_MS = 500;
struct EnergiseStagger {
  uint32_t lastStart = 0;
  bool started = false;
  // wanted/current: PCA ticks, 4096 = full off. Holds back newly energised
  // channels in wanted[]. Returns true while some channel is still waiting.
  bool apply(uint16_t (&wanted)[16], const uint16_t (&current)[16], uint32_t now, uint32_t intervalMs) {
    bool waiting = false;
    for (int ch = 0; ch < 16; ++ch) {
      if (current[ch] != 4096 || wanted[ch] == 4096 || !intervalMs) continue;
      if (!started || now - lastStart >= intervalMs) { started = true; lastStart = now; continue; }
      wanted[ch] = 4096; waiting = true;
    }
    return waiting;
  }
};

// Optional battery sense: 2S LiPo -> resistor divider -> ADC1 pin. Disabled
// (gpio -1) unless the owner fits a divider and configures it.
constexpr float BATTERY_LOW_DEFAULT_V = 6.8f; // ~3.4 V/cell for 2S under load
inline bool batteryPinAllowed(int gpio, int clockGpio, int sda, int scl, int oe) {
  // ESP32-S3 ADC1 is GPIO1..10 and keeps working while Wi-Fi is on (ADC2 does not).
  return gpio >= 1 && gpio <= 10 && gpio != clockGpio && gpio != sda && gpio != scl && gpio != oe;
}
struct BatteryMonitor {
  float volts = 0, minimum = 0;
  bool valid = false;
  // EMA for display; minimum tracks the deepest raw sag since reset().
  void sample(uint32_t pinMilliVolts, float ratio) {
    const float v = pinMilliVolts * ratio / 1000.0f;
    volts = valid ? volts + 0.1f * (v - volts) : v;
    if (!valid || v < minimum) minimum = v;
    valid = true;
  }
  void reset() { minimum = volts; }
  bool low(float threshold) const { return valid && volts < threshold; }
};
} // namespace sesame
