#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_GFX.h>

#include "robotics_esp32s3_servo_map.h"

// ESP32-S3 Super Mini I2C bus.
#define SDA_PIN 2
#define SCL_PIN 3

#define PCA9685_I2C_ADDR 0x40
#define OLED_I2C_ADDR 0x3C
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1

constexpr uint16_t ANGLE_HOLD_MS = 1000;
constexpr uint16_t RETURN_HOLD_MS = 500;
constexpr uint16_t BETWEEN_SERVOS_MS = 500;

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(PCA9685_I2C_ADDR);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

struct ServoOutputEnable {
  void configureOutput(uint8_t pin) { pinMode(pin, OUTPUT); }
  void disable(uint8_t pin) { digitalWrite(pin, HIGH); }
  void enable(uint8_t pin) { digitalWrite(pin, LOW); }
};

ServoOutputEnable servoOutputEnable;

// -1 means the channel has not yet received a position command. These are
// commanded positions only; the MG90S servos provide no angle feedback.
int16_t commandedAngles[SERVO_COUNT] = {-1, -1, -1, -1, -1, -1, -1, -1};
int8_t activeServoIndex = -1;

void updateDisplay() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Commanded angles");

  for (uint8_t row = 0; row < DISPLAY_ROW_COUNT; ++row) {
    for (uint8_t column = 0; column < 2; ++column) {
      const uint8_t servoIndex = DISPLAY_PAIRS[row][column];
      char cell[SERVO_CELL_BUFFER_SIZE];
      formatServoCell(cell, sizeof(cell), SERVO_MAP[servoIndex],
                      commandedAngles[servoIndex],
                      activeServoIndex == static_cast<int8_t>(servoIndex));
      display.setCursor(column * 64, 16 + row * 12);
      display.print(cell);
    }
  }

  display.display();
}

void commandServo(uint8_t servoIndex, uint8_t angle) {
  const ServoDefinition& servo = SERVO_MAP[servoIndex];
  activeServoIndex = servoIndex;
  commandedAngles[servoIndex] = angle;
  pwm.setPWM(servo.channel, 0, servoAngleToPulse(angle));
  updateDisplay();

  Serial.printf("PCA9685 pin %u (%s): %u degrees\n", servo.channel,
                servo.abbreviation, angle);
}

void releaseServo(uint8_t servoIndex) {
  const ServoDefinition& servo = SERVO_MAP[servoIndex];
  pwm.setPin(servo.channel, 0);
  activeServoIndex = -1;
  updateDisplay();

  Serial.printf("PCA9685 pin %u (%s): released at last command %d degrees\n",
                servo.channel, servo.abbreviation,
                commandedAngles[servoIndex]);
}

void setup() {
  Serial.begin(115200);

  // OE is active-low. Disable every PCA9685 output before touching the bus so
  // retained register values cannot twitch a servo during initialization.
  holdServoOutputsDisabled(servoOutputEnable);

  Wire.begin(SDA_PIN, SCL_PIN);

  pwm.begin();
  pwm.setPWMFreq(SERVO_FREQUENCY_HZ);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
    Serial.println(F("OLED initialization failed"));
    while (true) {
      delay(1000);
    }
  }

  updateDisplay();

  // Clear all sixteen PCA9685 channels to full-off before lowering OE.
  enableClearedPcaOutputs(pwm, servoOutputEnable, true);
  delay(1000);
}

void loop() {
  for (uint8_t servoIndex = 0; servoIndex < SERVO_COUNT; ++servoIndex) {
    for (uint8_t angleIndex = 0; angleIndex < TEST_ANGLE_COUNT; ++angleIndex) {
      commandServo(servoIndex, TEST_ANGLES[angleIndex]);
      delay(ANGLE_HOLD_MS);
    }

    // Return to center before removing PWM so the linkage is not released at
    // an endpoint. The OLED retains this last commanded angle after release.
    commandServo(servoIndex, RETURN_ANGLE);
    delay(RETURN_HOLD_MS);
    releaseServo(servoIndex);
    delay(BETWEEN_SERVOS_MS);
  }
}
