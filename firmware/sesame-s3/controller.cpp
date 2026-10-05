// SPDX-License-Identifier: Apache-2.0
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <esp_wifi.h>
#include <sys/socket.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_SSD1306.h>
#include "safe_action.h"
#include "command_line.h"
#include "vendor/face-bitmaps.h"
#include "web_ui.h"

using namespace sesame;
namespace {
SafeAction gate;
Adafruit_PWMServoDriver pwm(PCA_ADDRESS);
Adafruit_SSD1306 display(128, 64, &Wire, -1, 100000, 100000);
Preferences prefs;
NetworkServer http(80);
NetworkClient client;
DNSServer dns;
bool ready = false, screen = false, nvs = false, saved = false;
bool apOK = false, fault = false;
uint8_t prescale = 0;
uint16_t lastTicks[16];
uint32_t lastPWM = 0, buttonStart = 0;
enum Owner { NONE, USB, WEB, BUTTON } owner = NONE;
String ssid, country = "JP";
int wifiChannel = 1;
float wifiPower = 8.5;
const Motion* motion = nullptr;
unsigned motionIndex = 0;
uint32_t waitStarted = 0;
bool waiting = false;
bool sweeping = false;
float sweepLow = 0, sweepHigh = 0;
unsigned sweepStage = 0;

struct Face { const char* name; const unsigned char* frames[6]; };
const Face faces[] = {
#define X(n) {#n, {epd_bitmap_##n, epd_bitmap_##n##_1, epd_bitmap_##n##_2, epd_bitmap_##n##_3, epd_bitmap_##n##_4, epd_bitmap_##n##_5}},
  FACE_LIST
#undef X
};
const Face* face = nullptr;
unsigned faceFrame = 0;
uint32_t lastFace = 0;

int jointIndex(const char* name) {
  for (int j = 0; j < 8; ++j) if (!strcmp(name, NAMES[j])) return j;
  return -1;
}
void setFace(const char* name) {
  for (const auto& f : faces) if (!strcmp(f.name, name) && f.frames[0]) {
    face = &f; faceFrame = 0; lastFace = 0; return;
  }
}
void cancelQueue() { motion = nullptr; sweeping = false; waiting = false; }
bool clearPWM() {
  digitalWrite(OE, HIGH);
  bool ok = true;
  if (ready) for (int ch = 0; ch < 16; ++ch) {
    if (pwm.setPWM(ch, 0, 4096)) { ok = false; break; }
  }
  for (auto& v : lastTicks) v = 4096;
  return ok;
}
void outputsOff(const char* reason) {
  gate.off(); cancelQueue(); owner = NONE;
  if (!clearPWM()) { ready = false; fault = true; }
  Serial.printf("OFF %s%s\n", reason, fault ? " I2C_FAULT: power off, reboot after repair" : "");
}
bool readRegister(uint8_t reg, uint8_t& value) {
  Wire.beginTransmission(PCA_ADDRESS); Wire.write(reg);
  if (Wire.endTransmission(false) || Wire.requestFrom(uint8_t(PCA_ADDRESS), uint8_t(1)) != 1) return false;
  value = Wire.read(); return true;
}
bool configurePWM() {
  if (!ready || !clearPWM()) return false;
  pwm.setOscillatorFrequency(gate.cal.oscillator);
  pwm.setPWMFreq(PWM_HZ);
  if (!readRegister(0xfe, prescale)) return false;
  const int expected = int(lround(double(gate.cal.oscillator) / (4096 * PWM_HZ))) - 1;
  return prescale == expected && clearPWM();
}

struct Record { uint32_t magic; char manifest[17]; Calibration cal; uint32_t checksum; };
uint32_t checksum(const Record& record) {
  const auto* bytes = reinterpret_cast<const uint8_t*>(&record);
  uint32_t h = 2166136261u;
  for (size_t i = 0; i < offsetof(Record, checksum); ++i) h = (h ^ bytes[i]) * 16777619u;
  return h;
}
bool saveCalibration() {
  if (!nvs || !gate.cal.valid()) return false;
  Record r;
  memset(&r, 0, sizeof(r));
  r.magic = 0x53334331; strcpy(r.manifest, MANIFEST_ID); r.cal = gate.cal;
  r.checksum = checksum(r);
  return prefs.putBytes("record", &r, sizeof(r)) == sizeof(r);
}
void loadCalibration() {
  nvs = prefs.begin("sesame-s3", false);
  Record r;
  if (nvs && prefs.getBytesLength("record") == sizeof(r) &&
      prefs.getBytes("record", &r, sizeof(r)) == sizeof(r) && r.magic == 0x53334331 &&
      !memcmp(r.manifest, MANIFEST_ID, sizeof(r.manifest)) && r.checksum == checksum(r) && r.cal.valid()) {
    gate.cal = r.cal; saved = true;
    Serial.println("CAL loaded NVS");
  } else Serial.println("CAL defaults: map UNASSIGNED, limits 85..95; show/help");
}
String showCalibration() {
  String out = "manifest=" + String(MANIFEST_ID) + " saved=" + String(saved) +
    " oscillator_hz=" + String(gate.cal.oscillator) + " prescale=" + String(prescale) +
    " expected_pwm_hz=" + String(double(gate.cal.oscillator) / (4096.0 * (prescale + 1)), 4) + "\n";
  for (int j = 0; j < 8; ++j) {
    out += String(NAMES[j]) + " channel=" + String(gate.cal.channel[j]) + " sign=" + String(gate.cal.sign[j]) +
      " trim=" + String(gate.cal.trim[j], 2) + " limits=" + String(gate.cal.low[j], 2) + "," +
      String(gate.cal.high[j], 2) + " verified=" + String(bool(gate.cal.verified & (1u << j))) + "\n";
  }
  return out;
}
String exportCalibration() {
  String out = "{\"version\":1,\"manifest_id\":\"" + String(MANIFEST_ID) +
    "\",\"oscillator_hz\":" + String(gate.cal.oscillator) + ",\"joints\":[";
  for (int j = 0; j < 8; ++j) {
    if (j) out += ",";
    out += "{\"name\":\"" + String(NAMES[j]) + "\",\"channel\":" + String(gate.cal.channel[j]) +
      ",\"sign\":" + String(gate.cal.sign[j]) + ",\"trim_deg\":" + String(gate.cal.trim[j], 4) +
      ",\"limits_deg\":[" + String(gate.cal.low[j], 4) + "," + String(gate.cal.high[j], 4) +
      "],\"verified\":" + String(gate.cal.verified & (1u << j) ? "true" : "false") + "}";
  }
  return out + "]}";
}
String status() {
  String out = "mode=" + String(int(gate.mode)) + " outputs=" + String(gate.enabled) +
    " hub=" + String(ready) + " fault=" + String(fault) + " owner=" + String(int(owner)) +
    " motion=" + String(motion ? motion->name : "none") + "\n";
  for (int j = 0; j < 8; ++j) if (gate.enabled & (1u << j)) {
    out += "CH" + String(gate.channel(j)) + " current=" + String(gate.current[j], 2) +
      " target=" + String(gate.target[j], 2) + " physical=" + String(gate.physical(j), 2) +
      " us=" + String(angleUs(gate.physical(j)), 2) + "\n";
  }
  return out;
}
String wifiStatus() {
  wifi_config_t config = {}; wifi_country_t cc = {}; int8_t tx = 0;
  esp_err_t a = esp_wifi_get_config(WIFI_IF_AP, &config);
  esp_err_t b = esp_wifi_get_country(&cc);
  esp_err_t c = esp_wifi_get_max_tx_power(&tx);
  char countryText[4] = {cc.cc[0], cc.cc[1], cc.cc[2], 0};
  return "AP ok=" + String(apOK) + " ssid=" + ssid + " ip=" + WiFi.softAPIP().toString() +
    " channel=" + String(config.ap.channel) + " hidden=" + String(config.ap.ssid_hidden) +
    " country=" + String(countryText) + " tx_dbm=" + String(tx / 4.0, 2) +
    " clients=" + String(WiFi.softAPgetStationNum()) + " get_errors=" +
    String(int(a)) + "," + String(int(b)) + "," + String(int(c));
}
void startWifi() {
  // Explicit AP-only mode: no saved STA credentials or channel migration.
  WiFi.persistent(false);
  bool modeOK = WiFi.mode(WIFI_AP);
  esp_err_t cc = esp_wifi_set_country_code(country.c_str(), false);
  bool sleepOK = WiFi.setSleep(false);
  bool ipOK = WiFi.softAPConfig(IPAddress(192,168,4,1), IPAddress(192,168,4,1), IPAddress(255,255,255,0));
  bool started = WiFi.softAP(ssid.c_str(), "sesame123", wifiChannel, 0, 2);
  wifi_power_t power = wifiPower == 2 ? WIFI_POWER_2dBm : wifiPower == 13 ? WIFI_POWER_13dBm :
    wifiPower == 19.5 ? WIFI_POWER_19_5dBm : WIFI_POWER_8_5dBm;
  bool txOK = WiFi.setTxPower(power);
  apOK = modeOK && cc == ESP_OK && ipOK && started && txOK;
  Serial.printf("WIFI mode=%d country_err=%d sleep=%d ip=%d softAP=%d tx=%d\n", modeOK, int(cc), sleepOK, ipOK, started, txOK);
  Serial.println(wifiStatus());
  dns.stop();
  if (started) { dns.start(53, "*", WiFi.softAPIP()); http.begin(); }
}

const char* HELP =
  "help | show | export | status | wifi | face NAME | off | stop | heartbeat\n"
  "arm channel CH | arm hornless CH | arm joint NAME | arm assembly | arm run\n"
  "angle DEG | us MICROSECONDS | q INTERNAL_DEG | jog DELTA_DEG | sweep LOW HIGH\n"
  "centre (assembly, raw CH0..7=90; ignores trims)\n"
  "OFF only: map NAME CH | unmap NAME | sign NAME -1|1 | trim NAME DEG\n"
  "OFF only: limits NAME LOW HIGH | verify NAME | oscillator HZ | save\n"
  "reference (OFF, no servos: CH15=1500us) | motion NAME | run NAME\n"
  "servo NAME DEG | pose D0 D1 D2 D3 D4 D5 D6 D7 | rest\n"
  "OFF only: wifi JP|US|GB|DE|FR CHANNEL(1..11) TX_DBM(2|8.5|13|19.5)\n"
  "Every active serial/web session needs heartbeat <500ms; use class console.\n"
  "BOOT release while OFF: 30s assembly centre; BOOT press while active: OFF.";

String command(const char* text, Owner source) {
  CommandLine c; float value = 0, second = 0; int number = 0;
  if (!c.parse(text)) return "ERR malformed/too long";
  const uint32_t now = millis();
  if (c.is("help", 1)) return HELP;
  if (c.is("status", 1)) return status();
  if (c.is("show", 1) || c.is("subtrim", 1)) return showCalibration();
  if (c.is("export", 1)) return exportCalibration();
  if (c.is("wifi", 1)) return wifiStatus();
  if (c.is("off", 1)) { outputsOff("command"); return "OK OFF"; }
  if (c.is("stop", 1)) { cancelQueue(); gate.stop(now); return "OK STOP frozen; off releases torque"; }
  if (gate.active() && owner != source) return "ERR owned by another transport; off first";
  if (c.is("heartbeat", 1)) { gate.heartbeat(now); return ""; }
  if (c.is("face", 2)) { setFace(c.words[1]); return face && !strcmp(face->name, c.words[1]) ? "OK FACE" : "ERR face name"; }
  if (c.is("arm", 2) || c.is("arm", 3)) {
    if (!ready || fault || gate.active()) return "ERR hub fault or already armed; off first";
    Mode mode = Mode::Off; int selected = -1;
    if (c.count == 2 && !strcmp(c.words[1], "assembly")) mode = Mode::Assembly;
    if (c.count == 2 && !strcmp(c.words[1], "run") && saved) mode = Mode::Run;
    if (c.count == 3 && !strcmp(c.words[1], "joint")) { mode = Mode::Joint; selected = jointIndex(c.words[2]); }
    if (c.count == 3 && c.integer(2, selected)) {
      if (!strcmp(c.words[1], "channel")) mode = Mode::Channel;
      if (!strcmp(c.words[1], "hornless")) mode = Mode::Hornless;
    }
    if (!gate.arm(mode, selected, now)) return "ERR arm: select valid channel/joint; run needs all verified+saved";
    owner = source; cancelQueue();
    return "OK ARMED outputs OFF until target";
  }
  if (c.is("reference", 1)) {
    if (!ready || fault || !gate.arm(Mode::Reference, -1, now)) return "ERR off first / hub fault";
    owner = source; return "OK REFERENCE CH15 requested_us=1500 ticks=" +
      String(pulseTicks(1500, gate.cal.oscillator, prescale)) + " prescale=" + String(prescale) + "; no servos on CH15";
  }
  if (c.is("centre", 1) || c.is("center", 1)) {
    return gate.centre(now) ? "OK CENTRE CH0..7 raw=90 us=1830.50" : "ERR arm assembly first";
  }
  if (c.is("angle", 2) || c.is("us", 2) || c.is("jog", 2) || c.is("q", 2)) {
    if (!c.number(1, value) || gate.selected < 0) return "ERR select one channel/joint";
    int j = gate.selected;
    if (c.is("us", 2)) {
      if (value < PULSE_MIN || value > PULSE_MAX) return "ERR pulse range 732..2929";
      value = usAngle(value);
      if (gate.mode == Mode::Joint) value = gate.cal.canonical(j, value);
    } else if (c.is("jog", 2)) value += gate.current[j];
    else if (c.is("q", 2)) {
      if (gate.mode != Mode::Joint) return "ERR q requires joint mode";
      value = NEUTRAL + SIGNS[j] * value;
    }
    cancelQueue();
    if (!gate.set(j, value, now)) return "ERR target";
    return "OK TARGET " + String(gate.target[j], 2) + (fabsf(value - gate.target[j]) > .01f ? " CLAMPED" : "");
  }
  if (c.is("sweep", 3)) {
    if (gate.selected < 0 || !c.number(1, value) || !c.number(2, second) || value >= second) return "ERR sweep LOW HIGH";
    // One low -> high -> neutral pass, still bounded and watchdog-controlled.
    if (!gate.set(gate.selected, value, now)) return "ERR sweep mode";
    cancelQueue(); sweepLow = gate.target[gate.selected];
    if (!gate.set(gate.selected, second, now)) return "ERR sweep target";
    sweepHigh = gate.target[gate.selected];
    gate.set(gate.selected, sweepLow, now); sweeping = true; sweepStage = 0;
    return "OK SWEEP " + String(sweepLow, 2) + ".." + String(sweepHigh, 2);
  }
  if (c.is("motion", 2) || c.is("run", 2) || c.is("rest", 1)) {
    if (gate.mode != Mode::Run) return "ERR arm run first (verified+saved calibration)";
    const char* name = c.count == 1 ? "rest" : c.words[1];
    if (!strcmp(name, "forward")) name = "walk";
    if (!strcmp(name, "backward")) name = "walk_backward";
    if (!strcmp(name, "left")) name = "turn_left";
    if (!strcmp(name, "right")) name = "turn_right";
    for (const auto& m : MOTIONS) if (!strcmp(name, m.name)) {
      cancelQueue(); motion = &m; motionIndex = 0; gate.heartbeat(now);
      setFace(strstr(name, "walk") || strstr(name, "turn") ? "walk" : name);
      return "OK MOTION " + String(name);
    }
    return "ERR unknown motion";
  }
  if (c.is("servo", 3) || c.is("pose", 9)) {
    if (gate.mode != Mode::Run) return "ERR arm run first";
    float values[8]; int j = -1;
    if (c.count == 3) {
      j = jointIndex(c.words[1]);
      if (j < 0 || !c.number(2, value)) return "ERR servo NAME DEG";
    } else for (int k = 0; k < 8; ++k) if (!c.number(k+1, values[k])) return "ERR pose numbers";
    cancelQueue();
    if (j >= 0) gate.set(j, value, now);
    else for (int k = 0; k < 8; ++k) gate.set(k, values[k], now);
    return "OK TARGETS (soft/measured/electrical clamps applied)";
  }
  if (gate.active()) return "ERR unknown command or requires OFF";
  Calibration next = gate.cal;
  int j = c.count > 1 ? jointIndex(c.words[1]) : -1;
  if (c.is("save", 1)) {
    saved = saveCalibration(); return saved ? "OK SAVED NVS" : "ERR NVS save";
  }
  if (c.is("map", 3) && j >= 0 && c.integer(2, number) && number >= 0 && number <= 7) {
    next.channel[j] = number; next.verified &= ~(1u << j);
  } else if (c.is("unmap", 2) && j >= 0) {
    next.channel[j] = -1; next.verified &= ~(1u << j);
  } else if (c.is("sign", 3) && j >= 0 && c.integer(2, number) && (number == 1 || number == -1)) {
    next.sign[j] = number; next.verified &= ~(1u << j);
  } else if (c.is("trim", 3) && j >= 0 && c.number(2, value)) {
    next.trim[j] = value; next.verified &= ~(1u << j);
  } else if (c.is("limits", 4) && j >= 0 && c.number(2, value) && c.number(3, second)) {
    next.low[j] = value; next.high[j] = second; next.verified &= ~(1u << j);
  } else if (c.is("verify", 2) && j >= 0 && next.channel[j] >= 0) {
    next.verified |= 1u << j;
  } else if (c.is("oscillator", 2) && c.integer(1, number) && number >= 20000000 && number <= 30000000) {
    next.oscillator = number; next.verified = 0;
  } else if (c.is("wifi", 4) && c.integer(2, number) && c.number(3, value) && number >= 1 && number <= 11 &&
             (value == 2 || value == 8.5 || value == 13 || value == 19.5) &&
             (!strcmp(c.words[1], "JP") || !strcmp(c.words[1], "US") || !strcmp(c.words[1], "GB") ||
              !strcmp(c.words[1], "DE") || !strcmp(c.words[1], "FR"))) {
    if (source != USB) return "ERR change Wi-Fi via USB with servo power off";
    country = c.words[1]; wifiChannel = number; wifiPower = value;
    startWifi(); return wifiStatus();
  } else return "ERR syntax; help";
  if (!next.valid()) return "ERR calibration bounds or duplicate channel; unmap first";
  bool clockChanged = next.oscillator != gate.cal.oscillator;
  gate.cal = next; saved = false;
  if (clockChanged && !configurePWM()) { fault = true; outputsOff("clock I2C fault"); return "ERR oscillator write"; }
  return "OK CAL changed; verify after test, then save";
}

void serialService() {
  static char line[160]; static unsigned count = 0; static bool overflow = false;
  static String replies;
  for (unsigned budget = 0; budget < 192 && Serial.available(); ++budget) {
    char ch = Serial.read();
    if (ch == '\r' || ch == '\n') {
      if (overflow) Serial.println("ERR line too long (discarded)");
      else if (count) {
        line[count] = 0; String out = command(line, USB);
        if (out.length()) {
          if (replies.length() + out.length() > 8192) replies = "ERR output queue overflow; repeat show/export\n";
          else replies += out + "\n";
        }
      }
      count = 0; overflow = false;
    } else if (count < sizeof(line)-1 && !overflow) line[count++] = ch;
    else overflow = true;
  }
  size_t bytes = replies.length();
  if (bytes > 64) bytes = 64;
  if (bytes && Serial.availableForWrite() >= int(bytes)) {
    size_t written = Serial.write(reinterpret_cast<const uint8_t*>(replies.c_str()), bytes);
    replies.remove(0, written);
  }
}

// Nonblocking bounded HTTP reader: a partial/slow client cannot stall watchdog
// service inside WebServer::handleClient(). No OTA or blocking motion loops.
String request;
String response;
size_t responseSent = 0;
uint32_t requestStarted = 0;
String urlDecode(const String& text) {
  String out;
  for (unsigned i = 0; i < text.length(); ++i) {
    char ch = text[i];
    if (ch == '+') out += ' ';
    else if (ch == '%' && i + 2 < text.length()) {
      char hex[] = {text[i+1], text[i+2], 0}; char* end;
      long v = strtol(hex, &end, 16);
      if (*end || v < 32 || v > 126) return "";
      out += char(v); i += 2;
    } else out += ch;
  }
  return out;
}
void httpService() {
  if (!client) {
    client = http.accept();
    if (!client) return;
    client.setTimeout(1); request = ""; response = ""; responseSent = 0; requestStarted = millis();
  }
  if (millis() - requestStarted > 250 || request.length() > 1024) { client.stop(); return; }
  if (response.length()) {
    size_t remaining = response.length() - responseSent;
    int sent = ::send(client.fd(), response.c_str() + responseSent, remaining > 512 ? 512 : remaining, MSG_DONTWAIT);
    if (sent > 0) responseSent += sent;
    else if (sent < 0 && errno != EAGAIN && errno != EWOULDBLOCK) { client.stop(); return; }
    if (responseSent == response.length()) client.stop();
    return;
  }
  for (unsigned budget = 0; budget < 192 && client.available(); ++budget) request += char(client.read());
  if (!request.endsWith("\r\n\r\n")) return;
  int space = request.indexOf(' ', 4);
  String path = request.substring(4, space);
  String body, type = "text/plain"; int code = 200;
  if (!request.startsWith("GET ") || space < 0) { code = 400; body = "ERR HTTP"; }
  else if (path == "/status") body = status() + wifiStatus();
  else if (path.startsWith("/cmd?c=")) {
    String text = urlDecode(path.substring(7));
    body = command(text.c_str(), WEB);
    if (body.startsWith("ERR")) code = 400;
  } else { type = "text/html"; body = WEB_UI; }
  // Stream response with MSG_DONTWAIT on subsequent iterations. Arduino's
  // NetworkClient::write retries with blocking select; do not use it here.
  response = "HTTP/1.1 " + String(code) + (code == 200 ? " OK" : " Bad Request") +
    "\r\nContent-Type: " + type + "\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: " + String(body.length()) + "\r\n\r\n" + body;
}

void buttonService() {
  static bool initialized = false, raw = false, stable = false, seenRelease = false, pending = false;
  static uint32_t changed = 0;
  bool pressed = digitalRead(0) == LOW;
  if (!initialized) { raw = stable = pressed; initialized = true; seenRelease = !pressed; }
  if (pressed != raw) { raw = pressed; changed = millis(); }
  if (millis() - changed >= 40 && stable != raw) {
    stable = raw;
    if (stable) {
      if (gate.active()) { outputsOff("BOOT abort"); pending = false; }
      else pending = seenRelease;
    } else {
      seenRelease = true;
      if (pending && ready && !fault && gate.arm(Mode::Assembly, -1, millis())) {
        gate.centre(millis()); owner = BUTTON; buttonStart = millis();
        Serial.println("OK CENTRE button CH0..7 raw=90 us=1830.50 lease=30000ms");
      }
      pending = false;
    }
  }
  if (owner == BUTTON) {
    if (millis() - buttonStart >= 30000) outputsOff("assembly 30s complete");
    else gate.heartbeat(millis()); // finite, local human-triggered action only
  }
}
void motionService() {
  if (sweeping && gate.settled()) {
    if (sweepStage == 0) gate.set(gate.selected, sweepHigh, gate.lastHeartbeat);
    else if (sweepStage == 1) gate.set(gate.selected, NEUTRAL, gate.lastHeartbeat);
    else { sweeping = false; Serial.println("OK SWEEP complete"); }
    ++sweepStage;
  }
  if (!motion || !gate.settled()) return;
  if (waiting) {
    if (millis() - waitStarted < motion->steps[motionIndex-1].waitMs) return;
    waiting = false;
  }
  if (motionIndex == motion->count) { Serial.println("OK MOTION complete"); motion = nullptr; return; }
  const MotionStep& step = motion->steps[motionIndex++];
  for (int j = 0; j < 8; ++j) if (step.degrees[j] >= 0) {
    gate.set(j, step.degrees[j], gate.lastHeartbeat);
    if (fabsf(gate.target[j] - step.degrees[j]) > .01f)
      Serial.printf("CLAMP %s requested=%d bounded=%.2f\n", NAMES[j], step.degrees[j], gate.target[j]);
  }
  if (step.waitMs) { waiting = true; waitStarted = millis(); }
}
void outputService() {
  uint32_t now = millis();
  bool wasActive = gate.active();
  if (!gate.step(now)) {
    if (wasActive) outputsOff("watchdog >500ms");
    return;
  }
  motionService();
  if (now - lastPWM < 20) return;
  lastPWM = now;
  uint16_t wanted[16]; for (auto& v : wanted) v = 4096;
  for (int j = 0; j < 8; ++j) if (gate.enabled & (1u << j)) {
    int ch = gate.channel(j);
    if (ch < 0 || ch > 7) { outputsOff("invalid map"); return; }
    wanted[ch] = pulseTicks(angleUs(clamp(gate.physical(j), 0, 180)), gate.cal.oscillator, prescale);
  }
  if (gate.mode == Mode::Reference) wanted[15] = pulseTicks(1500, gate.cal.oscillator, prescale);
  bool any = false;
  for (int ch = 0; ch < 16; ++ch) {
    if (wanted[ch] != 4096) any = true;
    if (lastTicks[ch] != wanted[ch]) {
      if (pwm.setPWM(ch, 0, wanted[ch])) { fault = true; outputsOff("I2C write fault"); return; }
      lastTicks[ch] = wanted[ch];
    }
  }
  // Check hub even when holding a stationary target; lost I2C latches off.
  uint8_t livePrescale;
  if (!readRegister(0xfe, livePrescale) || livePrescale != prescale) {
    fault = true; outputsOff("I2C/prescale fault"); return;
  }
  digitalWrite(OE, any ? LOW : HIGH);
}
void faceService() {
  if (!screen || !face || millis() - lastFace < 250) return;
  lastFace = millis();
  display.clearDisplay();
  display.drawBitmap(0, 0, face->frames[faceFrame], 128, 64, SSD1306_WHITE);
  display.fillRect(0, 0, 128, 10, SSD1306_BLACK);
  display.setCursor(0,0); display.setTextSize(1); display.setTextColor(SSD1306_WHITE);
  if (owner == BUTTON) display.printf("Centre %lus", (unsigned long)((30000 - (millis() - buttonStart))/1000));
  else if (gate.active()) display.print("ACTIVE / BOOT: OFF");
  else display.print(apOK ? ssid : "AP FAILED / USB help");
  display.display();
  if (faceFrame < 5 && face->frames[faceFrame+1]) ++faceFrame; else faceFrame = 0;
}
} // namespace

void setup() {
  digitalWrite(OE, HIGH); pinMode(OE, OUTPUT); pinMode(0, INPUT_PULLUP);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0); // an absent USB host must not block the watchdog
  Wire.begin(sesame::SDA, sesame::SCL); Wire.setClock(100000); Wire.setTimeOut(5);
  loadCalibration();
  ready = pwm.begin();
  if (ready && !configurePWM()) { ready = false; fault = true; }
  outputsOff("boot");
  Wire.beginTransmission(OLED_ADDRESS);
  if (!Wire.endTransmission()) screen = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS, false, false);
  setFace("rest");
  uint64_t mac = ESP.getEfuseMac();
  char name[32]; snprintf(name, sizeof(name), "Sesame-S3-%02X%02X", unsigned((mac >> 32)&255), unsigned((mac >> 40)&255)); ssid = name;
  startWifi();
  Serial.println("READY Sesame S3 calibration+controller; outputs OFF; help");
}
void loop() {
  outputService(); buttonService(); serialService(); outputService();
  httpService(); outputService();
  dns.processNextRequest(); faceService(); outputService();
  delay(1);
}
