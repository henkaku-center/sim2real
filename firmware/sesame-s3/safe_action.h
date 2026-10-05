// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cmath>
#include <cstdint>
#include <cstring>
#include "manifest_generated.h"

namespace sesame {
inline float clamp(float x, float lo, float hi) { return fminf(hi, fmaxf(lo, x)); }
inline float angleUs(float angle) { return PULSE_MIN + (PULSE_MAX - PULSE_MIN) * angle / 180.0f; }
inline float usAngle(float us) { return (us - PULSE_MIN) * 180.0f / (PULSE_MAX - PULSE_MIN); }
inline uint16_t pulseTicks(float us, uint32_t oscillator, uint8_t prescale) {
  return uint16_t(lround(double(us) * oscillator / (1000000.0 * (prescale + 1))));
}

struct Calibration {
  uint32_t version = 1;
  uint32_t oscillator = OSC_DEFAULT;
  int8_t channel[8] = {-1,-1,-1,-1,-1,-1,-1,-1};
  int8_t sign[8];
  float trim[8], low[8], high[8];
  uint8_t verified = 0;
  Calibration() {
    for (int j = 0; j < 8; ++j) {
      sign[j] = SIGNS[j]; trim[j] = TRIMS[j];
      low[j] = fmaxf(SOFT_LOW[j], INITIAL_LOW);
      high[j] = fminf(SOFT_HIGH[j], INITIAL_HIGH);
    }
  }
  bool valid() const {
    if (version != 1 || oscillator < 20000000 || oscillator > 30000000) return false;
    unsigned used = 0;
    for (int j = 0; j < 8; ++j) {
      if (channel[j] < -1 || channel[j] > 7 || (sign[j] != 1 && sign[j] != -1)) return false;
      if (channel[j] >= 0) {
        if (used & (1u << channel[j])) return false;
        used |= 1u << channel[j];
      } else if (verified & (1u << j)) return false;
      if (!std::isfinite(trim[j]) || fabsf(trim[j]) > TRIM_LIMIT ||
          !std::isfinite(low[j]) || !std::isfinite(high[j]) ||
          low[j] < SOFT_LOW[j] || high[j] > SOFT_HIGH[j] ||
          low[j] > NEUTRAL || high[j] < NEUTRAL || low[j] > high[j]) return false;
    }
    return true;
  }
  bool complete() const { return valid() && verified == 255; }
  float physical(int j, float firmware) const {
    return NEUTRAL + trim[j] + sign[j] * SIGNS[j] * (firmware - NEUTRAL);
  }
  float canonical(int j, float physicalAngle) const {
    return NEUTRAL + sign[j] * SIGNS[j] * (physicalAngle - NEUTRAL - trim[j]);
  }
  float bounded(int j, float firmware) const {
    // Intersect measured logical limits with post-trim electrical endpoints.
    float a = canonical(j, 0), b = canonical(j, 180);
    return clamp(firmware, fmaxf(low[j], fminf(a,b)), fminf(high[j], fmaxf(a,b)));
  }
};

enum class Mode { Off, Channel, Hornless, Joint, Assembly, Run, Reference };

// All PWM authority passes through this gate, including raw bench commands.
// First enable cannot be slew-limited from an unknown physical shaft position.
// It always starts at neutral; subsequent targets are slew-limited.
class SafeAction {
 public:
  Calibration cal;
  Mode mode = Mode::Off;
  int selected = -1;
  float current[8] = {}, target[8] = {};
  uint8_t enabled = 0;
  uint32_t lastHeartbeat = 0, lastStep = 0;
  bool timedOut = false;
  bool active() const { return mode != Mode::Off; }
  void off() { mode = Mode::Off; enabled = 0; selected = -1; }
  void heartbeat(uint32_t now) { if (active()) lastHeartbeat = now; }
  bool arm(Mode m, int index, uint32_t now) {
    if (active() || m == Mode::Off || !cal.valid()) return false;
    if (m == Mode::Run && !cal.complete()) return false;
    if ((m == Mode::Channel || m == Mode::Hornless || m == Mode::Joint) && (index < 0 || index > 7)) return false;
    if (m == Mode::Joint && cal.channel[index] < 0) return false;
    mode = m; selected = index; timedOut = false;
    lastHeartbeat = lastStep = now;
    for (int j = 0; j < 8; ++j) current[j] = target[j] = NEUTRAL;
    enabled = 0; // arm alone NEVER emits pulses
    return true;
  }
  bool set(int j, float degrees, uint32_t now) {
    if (!active() || !std::isfinite(degrees) || j < 0 || j > 7) return false;
    if (mode == Mode::Assembly || mode == Mode::Reference) return false;
    if (mode != Mode::Run && j != selected) return false;
    float bound;
    if (mode == Mode::Channel) bound = clamp(degrees, INITIAL_LOW, INITIAL_HIGH);
    else if (mode == Mode::Hornless) bound = clamp(degrees, 0, 180);
    else bound = cal.bounded(j, degrees);
    if (fabsf(bound - current[j]) > MAX_JUMP) { stop(now); return false; }
    target[j] = bound;
    enabled |= 1u << j;
    heartbeat(now);
    return true;
  }
  bool centre(uint32_t now) {
    if (mode != Mode::Assembly) return false;
    for (int j = 0; j < 8; ++j) current[j] = target[j] = NEUTRAL;
    enabled = 255; heartbeat(now); return true;
  }
  void stop(uint32_t now) {
    for (int j = 0; j < 8; ++j) target[j] = current[j];
    heartbeat(now);
  }
  bool step(uint32_t now) {
    if (!active()) return false;
    if (uint32_t(now - lastHeartbeat) > WATCHDOG_MS) {
      off(); timedOut = true; return false;
    }
    // Never turn a stalled loop into a large catch-up jump.
    uint32_t dt = now - lastStep; if (dt > 20) dt = 20;
    lastStep = now;
    float step = (mode == Mode::Run ? RUN_RATE : CAL_RATE) * dt / 1000.0f;
    for (int j = 0; j < 8; ++j) current[j] += clamp(target[j] - current[j], -step, step);
    return true;
  }
  bool settled() const {
    for (int j = 0; j < 8; ++j) if ((enabled & (1u << j)) && fabsf(target[j] - current[j]) > 0.01f) return false;
    return true;
  }
  int channel(int j) const { return mode == Mode::Run || mode == Mode::Joint ? cal.channel[j] : j; }
  float physical(int j) const {
    return mode == Mode::Run || mode == Mode::Joint ? cal.physical(j, current[j]) : current[j];
  }
};
} // namespace sesame
