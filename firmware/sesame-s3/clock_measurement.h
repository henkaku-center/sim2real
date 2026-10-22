// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <cstring>
#include "command_line.h"

namespace sesame {
enum class ClockCommand { None, Measure, Status, Abort, Invalid };
inline ClockCommand clockCommand(const CommandLine& c) {
  if (!c.count || strcmp(c.words[0], "clock")) return ClockCommand::None;
  if (c.is("clock", 2)) {
    if (!strcmp(c.words[1], "measure")) return ClockCommand::Measure;
    if (!strcmp(c.words[1], "status")) return ClockCommand::Status;
    if (!strcmp(c.words[1], "abort")) return ClockCommand::Abort;
  }
  return ClockCommand::Invalid;
}
enum class ClockOutcome { Idle, Running, Complete, Quality, Timeout, Aborted,
                          Watchdog, Disconnected, Fault, CommandError };
inline const char* clockOutcomeName(ClockOutcome outcome) {
  switch(outcome) {
    case ClockOutcome::Idle: return "idle";
    case ClockOutcome::Running: return "running";
    case ClockOutcome::Complete: return "complete";
    case ClockOutcome::Quality: return "quality-rejected";
    case ClockOutcome::Timeout: return "timeout";
    case ClockOutcome::Aborted: return "aborted";
    case ClockOutcome::Watchdog: return "watchdog";
    case ClockOutcome::Disconnected: return "usb-disconnected";
    case ClockOutcome::Fault: return "fault";
    case ClockOutcome::CommandError: return "command-error";
  }
  return "invalid";
}
struct ClockReport {
  ClockOutcome outcome = ClockOutcome::Idle;
  uint32_t generation = 0, edges = 0, firstUs = 0, lastUs = 0;
  uint32_t minPeriodUs = UINT32_MAX, maxPeriodUs = 0;
  uint8_t prescale = 0;
  double observedHz() const {
    return edges > 1 && uint32_t(lastUs-firstUs) ?
      double(edges-1)*1000000.0/uint32_t(lastUs-firstUs) : 0;
  }
  double oscillatorHz() const { return observedHz()*4096.0*(prescale+1); }
  double jitterPpm() const {
    return edges > 1 && uint32_t(lastUs-firstUs) ?
      double(maxPeriodUs-minPeriodUs)*(edges-1)*1000000.0/uint32_t(lastUs-firstUs) : 0;
  }
};

// Protected by the caller's cross-core critical section. No allocation, blocking
// waits or floating arithmetic in edge(). A copied report is formatted outside
// the lock. Unsigned differences handle micros()/millis() rollover.
class ClockMeasurement {
 public:
  static constexpr uint32_t TARGET_EDGES = 101, TIMEOUT_MS = 4000;
  bool active() const { return data.outcome == ClockOutcome::Running; }
  bool start(uint32_t nowMs, uint8_t prescale) {
    if (active()) return false;
    uint32_t generation = data.generation+1;
    if (!generation) generation = 1;
    data = ClockReport{}; data.generation = generation; data.prescale = prescale;
    data.outcome = ClockOutcome::Running; startedMs = nowMs;
    return true;
  }
  bool edge(uint32_t generation, uint32_t nowUs) {
    if (!active() || generation != data.generation || data.edges >= TARGET_EDGES) return false;
    if (!data.edges) data.firstUs = nowUs;
    else {
      uint32_t period = nowUs-data.lastUs;
      if (period < data.minPeriodUs) data.minPeriodUs = period;
      if (period > data.maxPeriodUs) data.maxPeriodUs = period;
    }
    data.lastUs = nowUs; ++data.edges;
    return data.edges == TARGET_EDGES; // caller masks GPIO IRQ at this bound
  }
  bool poll(uint32_t nowMs) {
    if (!active()) return false;
    // Deadline wins over completion discovered after a stalled main loop.
    if (uint32_t(nowMs-startedMs) >= TIMEOUT_MS) { abort(ClockOutcome::Timeout); return true; }
    if (data.edges < TARGET_EDGES) return false;
    const double osc = data.oscillatorHz();
    data.outcome = data.minPeriodUs >= 10000 && data.maxPeriodUs <= 40000 &&
      data.jitterPpm() <= 20000 && osc >= 20000000 && osc <= 30000000 ?
      ClockOutcome::Complete : ClockOutcome::Quality;
    return true;
  }
  void abort(ClockOutcome outcome, bool force = false) {
    if (active() || force) data.outcome = outcome;
  }
  ClockReport report() const { return data; }
 private:
  ClockReport data;
  uint32_t startedMs = 0;
};
} // namespace sesame
