#ifndef ROBOTICS_ESP32S3_SERVO_MAP_H
#define ROBOTICS_ESP32S3_SERVO_MAP_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "../../common/sesame_servo_map.h"

constexpr uint8_t DISPLAY_ROW_COUNT = 4;
constexpr size_t SERVO_CELL_BUFFER_SIZE = 11;

// Pair corresponding left/right joints on each OLED row.
constexpr uint8_t DISPLAY_PAIRS[DISPLAY_ROW_COUNT][2] = {
    {0, 4},
    {1, 5},
    {2, 6},
    {3, 7},
};

constexpr uint8_t TEST_ANGLE_COUNT = 3;
constexpr uint8_t TEST_ANGLES[TEST_ANGLE_COUNT] = {0, 90, 180};
constexpr uint8_t RETURN_ANGLE = 90;

// Formats one ten-character OLED cell, for example "*0 ULF: 90".
// Angles are commanded positions; this system has no servo feedback.
inline void formatServoCell(char* output, size_t outputSize,
                            const ServoDefinition& servo, int16_t angle,
                            bool active) {
  const char marker = active ? '*' : ' ';
  if (angle < 0) {
    snprintf(output, outputSize, "%c%u %s:---", marker, servo.channel,
             servo.abbreviation);
    return;
  }

  const int16_t displayAngle = angle > 180 ? 180 : angle;
  snprintf(output, outputSize, "%c%u %s:%3d", marker, servo.channel,
           servo.abbreviation, static_cast<int>(displayAngle));
}

#endif
