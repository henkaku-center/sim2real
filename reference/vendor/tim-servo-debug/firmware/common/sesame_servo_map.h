#ifndef SESAME_SERVO_MAP_H
#define SESAME_SERVO_MAP_H

#include <stdint.h>

constexpr uint8_t SERVO_COUNT = 8;
constexpr uint8_t PCA9685_OUTPUT_COUNT = 16;
constexpr uint8_t INVALID_PCA9685_CHANNEL = 0xFF;
constexpr uint16_t SERVO_MIN_PULSE = 150;
constexpr uint16_t SERVO_MAX_PULSE = 512;
constexpr uint8_t SERVO_FREQUENCY_HZ = 50;
constexpr uint8_t PCA9685_OUTPUT_ENABLE_PIN = 18;

struct ServoDefinition {
  uint8_t channel;
  const char* abbreviation;
  uint8_t logicalIndex;
  const char* logicalName;
};

constexpr ServoDefinition SERVO_MAP[SERVO_COUNT] = {
    {0, "ULF", 2, "L1"}, {1, "ULB", 3, "L2"},
    {2, "LLF", 6, "L3"}, {3, "LLB", 7, "L4"},
    {4, "URF", 0, "R1"}, {5, "URB", 1, "R2"},
    {6, "LRF", 5, "R3"}, {7, "LRB", 4, "R4"},
};

constexpr uint8_t LOGICAL_TO_PCA_CHANNEL[SERVO_COUNT] = {4, 5, 0, 1, 7, 6, 2, 3};

constexpr uint8_t pcaChannelForLogicalServo(uint8_t logicalIndex) {
  return logicalIndex < SERVO_COUNT
             ? LOGICAL_TO_PCA_CHANNEL[logicalIndex]
             : INVALID_PCA9685_CHANNEL;
}

struct TranslatedServoCommand {
  bool valid;
  uint8_t pcaChannel;
  uint8_t adjustedAngle;
};

constexpr TranslatedServoCommand translateServoCommand(
    uint8_t logicalIndex, int angle, const int8_t trims[SERVO_COUNT]) {
  if (logicalIndex >= SERVO_COUNT) {
    return {false, INVALID_PCA9685_CHANNEL, 0};
  }
  int adjusted = angle + trims[logicalIndex];
  adjusted = adjusted < 0 ? 0 : adjusted;
  adjusted = adjusted > 180 ? 180 : adjusted;
  return {true, pcaChannelForLogicalServo(logicalIndex),
          static_cast<uint8_t>(adjusted)};
}

constexpr uint16_t servoAngleToPulse(uint8_t angle) {
  return angle >= 180
             ? SERVO_MAX_PULSE
             : SERVO_MIN_PULSE +
                   ((SERVO_MAX_PULSE - SERVO_MIN_PULSE) * angle) / 180;
}

template <typename OutputEnable>
void holdServoOutputsDisabled(OutputEnable& outputEnable) {
  outputEnable.configureOutput(PCA9685_OUTPUT_ENABLE_PIN);
  outputEnable.disable(PCA9685_OUTPUT_ENABLE_PIN);
}

// Decides whether an ArduinoOTA error callback must disable the servo
// outputs. ArduinoOTA reports authentication failures through onError()
// *before* onStart() ever runs, so an unauthenticated peer must never be able
// to limp the robot remotely: only an error raised after the update actually
// started (outputs already disabled) keeps them disabled until reboot.
// Pure and host-testable -- no hardware state is touched here.
constexpr bool otaErrorRequiresServoDisable(bool otaUpdateStarted) {
  return otaUpdateStarted;
}

template <typename OutputEnable>
void prepareServoOutputsForFirmwareUpdate(OutputEnable& outputEnable,
                                          bool& servoOutputsReady) {
  holdServoOutputsDisabled(outputEnable);
  servoOutputsReady = false;
}

template <typename PwmDriver, typename OutputEnable>
bool enableClearedPcaOutputs(PwmDriver& pwm, OutputEnable& outputEnable,
                             bool pcaReady) {
  if (!pcaReady) return false;
  for (uint8_t channel = 0; channel < PCA9685_OUTPUT_COUNT; ++channel) {
    pwm.setPWM(channel, 0, 4096);
  }
  outputEnable.enable(PCA9685_OUTPUT_ENABLE_PIN);
  return true;
}

#endif
