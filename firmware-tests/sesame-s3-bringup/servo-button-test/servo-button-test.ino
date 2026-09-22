#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

constexpr uint8_t OE_PIN = 18;
constexpr uint8_t CHANNELS[] = {4, 5, 0, 1, 7, 6, 2, 3};
const char *NAMES[] = {"R1 front-R upper", "R2 rear-R upper",
                       "L1 front-L upper", "L2 rear-L upper",
                       "R4 rear-R lower", "R3 front-R lower",
                       "L3 front-L lower", "L4 rear-L lower"};
Adafruit_PWMServoDriver pwm(0x40);
Adafruit_SSD1306 display(128, 64, &Wire, -1, 100000, 100000);
bool ready = false, screen = false, active = false;
bool rawPressed = false, stablePressed = false, armed = false;
unsigned long changedAt = 0, startedAt = 0;
uint8_t joint = 0, stage = 0;

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
  Serial.printf("%s | %s | CH%u\n", message, NAMES[joint], CHANNELS[joint]);
  if (!screen) return;
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Sesame servo test");
  display.println(NAMES[joint]);
  display.print("Hub CH"); display.println(CHANNELS[joint]);
  display.println(message);
  display.println("Battery only to move");
  display.println("BOOT: start / abort");
  display.display();
}

void angle(uint8_t degrees) {
  uint16_t pulse = 150 + (362UL * degrees) / 180;
  pwm.setPWM(CHANNELS[joint], 0, pulse);
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
  // A button held during startup must be released before a test can start.
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
      angle(90);
      digitalWrite(OE_PIN, LOW);
      active = true;
      stage = 0;
      startedAt = now;
      show("Testing 90-95-90");
    }
  }
  if (active) {
    unsigned long elapsed = now - startedAt;
    if (elapsed >= 2500) {
      outputsOff();
      joint = (joint + 1) % 8;
      show("Next: outputs OFF");
    } else if (elapsed >= 1800 && stage < 2) {
      angle(90);
      stage = 2;
    } else if (elapsed >= 1000 && stage < 1) {
      angle(95);
      stage = 1;
    }
  }
  delay(1);
}
