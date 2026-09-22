#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

constexpr uint8_t OE_PIN = 18;
Adafruit_PWMServoDriver pwm(0x40);
Adafruit_SSD1306 display(128, 64, &Wire, -1, 100000, 100000);
bool ready = false, screen = false, active = false;
bool rawPressed = false, stablePressed = false, armed = false;
unsigned long changedAt = 0, startedAt = 0;
uint8_t stage = 0;

bool ack(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void outputsOff() {
  digitalWrite(OE_PIN, HIGH);
  for (uint8_t ch = 0; ch < 16; ++ch) pwm.setPWM(ch, 0, 4096);
  active = false;
}

void show(const char *message) {
  Serial.println(message);
  if (!screen) return;
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Sesame LOAD TEST");
  display.println("All hub CH0-7");
  display.println("90-95-90 x3");
  display.println(message);
  display.println("Battery only to move");
  display.println("BOOT: start / abort");
  display.display();
}

bool allAngle(uint8_t degrees) {
  uint16_t pulse = 150 + (362UL * degrees) / 180;
  for (uint8_t ch = 0; ch < 8; ++ch) {
    if (pwm.setPWM(ch, 0, pulse) != 0) {
      outputsOff();
      ready = false;
      show("I2C fault: power OFF");
      return false;
    }
  }
  return true;
}

void setup() {
  digitalWrite(OE_PIN, HIGH);
  pinMode(OE_PIN, OUTPUT);
  pinMode(BOOT_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  Wire.begin(2, 3);
  Wire.setClock(100000);
  Wire.setTimeOut(50);
  if (ack(0x3C)) screen = display.begin(SSD1306_SWITCHCAPVCC, 0x3C, false, false);
  if (ack(0x40)) {
    pwm.begin();
    pwm.setPWMFreq(50);
    outputsOff();
    ready = true;
  }
  rawPressed = stablePressed = digitalRead(BOOT_PIN) == LOW;
  changedAt = millis();
  show(ready ? "Idle: outputs OFF" : "Hub missing: STOP");
}

void loop() {
  unsigned long now = millis();
  bool pressed = digitalRead(BOOT_PIN) == LOW;
  if (pressed != rawPressed) {
    rawPressed = pressed;
    changedAt = now;
  }
  if (now - changedAt >= 40 && stablePressed != rawPressed) {
    stablePressed = rawPressed;
    if (stablePressed && ready) {
      if (active) {
        outputsOff();
        armed = false;
        show("Aborted: outputs OFF");
      } else {
        armed = true;
      }
    } else if (!stablePressed && armed && ready) {
      armed = false;
      if (allAngle(90)) {
        digitalWrite(OE_PIN, LOW);
        active = true;
        stage = 0;
        startedAt = millis();
        show("Running: all 90 deg");
      }
    }
  }
  if (active) {
    unsigned long elapsed = millis() - startedAt;
    if (elapsed >= 7000) {
      outputsOff();
      show("Done: outputs OFF");
    } else {
      uint8_t nextStage = elapsed / 1000;
      if (nextStage != stage) {
        stage = nextStage;
        uint8_t degrees = (stage % 2) ? 95 : 90;
        if (allAngle(degrees)) show(degrees == 95 ? "Running: all 95 deg" : "Running: all 90 deg");
      }
    }
  }
  delay(1);
}
