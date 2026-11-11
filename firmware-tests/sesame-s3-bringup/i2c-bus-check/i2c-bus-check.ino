// Address probes only. Does not assume an external OE wire or command servo PWM.
// Begin with controller outputs off; this sketch does not clear retained PCA state.
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(1500);
  Wire.begin(2, 3);
  Wire.setClock(100000);
  Wire.setTimeOut(50);
}

void loop() {
  static unsigned pass = 0;
  Serial.printf("I2C pass=%u SDA=GPIO2:%d SCL=GPIO3:%d (digital levels, not volts)\n",
                ++pass, digitalRead(2), digitalRead(3));
  unsigned found = 0, nack = 0, errors = 0;
  for (uint8_t address = 8; address < 120; ++address) {
    Wire.beginTransmission(address);
    const uint8_t result = Wire.endTransmission();
    if (result == 0) {
      Serial.printf("ACK 0x%02X\n", address);
      ++found;
    } else if (result == 2) {
      ++nack;
    } else {
      Serial.printf("ERROR address=0x%02X code=%u\n", address, result);
      ++errors;
    }
  }
  Serial.printf("SCAN_DONE pass=%u ack=%u nack=%u errors=%u\n", pass, found, nack, errors);
  delay(2000);
}
