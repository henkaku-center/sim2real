// Sesame S3 bring-up: scan only, no servo PWM commands.
#include <Wire.h>

constexpr int SDA_PIN = 2;
constexpr int SCL_PIN = 3;
constexpr int OE_PIN = 18;

void setup() {
  // Disable PCA9685 outputs if OE is connected as in the production netlist.
  digitalWrite(OE_PIN, HIGH);
  pinMode(OE_PIN, OUTPUT);
  Serial.begin(115200);
  delay(2000);
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  Wire.setTimeOut(50);
}

void loop() {
  Serial.println("Sesame diagnostic: SDA=2 SCL=3; GPIO18/OE held HIGH");
  int found = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    uint8_t result = Wire.endTransmission();
    if (result == 0) {
      Serial.printf("  ACK at 0x%02X", address);
      if (address == 0x3C || address == 0x3D) Serial.print(" (expected OLED address)");
      if (address == 0x40) Serial.print(" (expected PCA9685 address)");
      if (address == 0x70) Serial.print(" (possible PCA9685 all-call address)");
      Serial.println();
      ++found;
    } else if (result != 2) {
      Serial.printf("  I2C error %u at 0x%02X\n", result, address);
    }
  }
  Serial.printf("Scan complete: %d responding address(es)\n\n", found);
  delay(3000);
}
