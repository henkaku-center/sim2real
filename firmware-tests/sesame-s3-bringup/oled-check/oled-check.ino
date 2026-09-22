#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

Adafruit_SSD1306 display(128, 64, &Wire, -1, 100000, 100000);
bool displayReady = false;
unsigned long frame = 0;

bool responds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void setup() {
  digitalWrite(18, HIGH);
  pinMode(18, OUTPUT);
  Serial.begin(115200);
  delay(2000);
  Wire.begin(2, 3);
  Wire.setClock(100000);
  Wire.setTimeOut(50);
  // Full-off on every PCA9685 output; do not rely on OE being wired.
  if (responds(0x40)) {
    Wire.beginTransmission(0x40);
    Wire.write(0xFD); // ALL_LED_OFF_H
    Wire.write(0x10); // ALL_LED_OFF bit
    Serial.printf("PCA9685 full-off write status: %u\n", Wire.endTransmission());
  }
  if (responds(0x3C)) {
    displayReady = display.begin(SSD1306_SWITCHCAPVCC, 0x3C, false, false);
  }
  Serial.printf("OLED initialization: %s\n", displayReady ? "ready" : "failed");
}

void loop() {
  bool oled = responds(0x3C);
  bool hub = responds(0x40);
  Serial.printf("OLED=%s PCA9685=%s frame=%lu; servo outputs disabled\n",
                oled ? "ACK" : "missing", hub ? "ACK" : "missing", frame);
  if (displayReady && oled) {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.drawRect(0, 0, 128, 64, SSD1306_WHITE);
    display.setTextSize(2);
    display.setCursor(20, 6);
    display.print("Sesame");
    display.setTextSize(1);
    display.setCursor(8, 28);
    display.print(hub ? "I2C OK: OLED + HUB" : "OLED OK; HUB missing");
    display.setCursor(8, 41);
    display.print("Servo outputs OFF");
    display.setCursor(8, 52);
    display.print("Frame: ");
    display.print(frame);
    display.display();
  }
  ++frame;
  delay(1000);
}
