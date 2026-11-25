// SPDX-License-Identifier: Apache-2.0
// Host-only serial seam. Reuses firmware parser/gate/tables, no MCU emulation.
#include "safe_action.h"
#include "command_line.h"
#include <chrono>
#include <cstdio>
#include <poll.h>
#include <string>
#include <unistd.h>
#include <vector>

using namespace sesame;
namespace {
SafeAction gate;
const Motion* motion = nullptr;
unsigned motionIndex = 0;
uint32_t waitStarted = 0;
bool waiting = false, saved = true;
std::vector<std::string> faces;
const auto epoch = std::chrono::steady_clock::now();
uint32_t nowMs() {
  return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - epoch).count();
}
void cancelQueue() { motion = nullptr; waiting = false; }
void off(const char* reason) {
  gate.off(); cancelQueue(); printf("OFF %s\n", reason);
}
int jointIndex(const char* name) {
  for (int j=0; j<8; ++j) if (!strcmp(name, NAMES[j])) return j;
  return -1;
}
void service() {
  uint32_t now = nowMs();
  bool active = gate.active();
  if (!gate.step(now)) {
    if (active) off("watchdog >500ms");
    return;
  }
  // controller.cpp motionService, including settle-before-wait semantics.
  if (!motion || !gate.settled()) return;
  if (waiting) {
    if (now - waitStarted < motion->steps[motionIndex-1].waitMs) return;
    waiting = false;
  }
  if (motionIndex == motion->count) {
    puts("OK MOTION complete"); motion = nullptr; return;
  }
  const MotionStep& step = motion->steps[motionIndex++];
  for (int j=0; j<8; ++j) if (step.degrees[j] >= 0) {
    gate.set(j, step.degrees[j], gate.lastHeartbeat);
    if (fabsf(gate.target[j] - step.degrees[j]) > .01f)
      printf("CLAMP %s requested=%d bounded=%.2f\n", NAMES[j], step.degrees[j], gate.target[j]);
  }
  if (step.waitMs) { waiting = true; waitStarted = now; }
}
void status() {
  printf("mode=%d outputs=%u hub=1 fault=0 owner=%d motion=%s profile=%s\n",
         int(gate.mode), gate.enabled, gate.active() ? 1 : 0, motion ? motion->name : "none", PULSE_PROFILE_ID);
  for (int j=0; j<8; ++j) if (gate.enabled & (1u<<j))
    printf("CH%d current=%.2f target=%.2f physical=%.2f us=%.2f\n",
           gate.channel(j), gate.current[j], gate.target[j], gate.physical(j), angleUs(gate.physical(j)));
  puts(""); // controller status() includes a trailing LF before Serial.println
}
void exportCalibration() {
  printf("{\"version\":1,\"manifest_id\":\"%s\",\"oscillator_hz\":%u,\"joints\":[", MANIFEST_ID, gate.cal.oscillator);
  for (int j=0; j<8; ++j) {
    if (j) printf(",");
    printf("{\"name\":\"%s\",\"channel\":%d,\"sign\":%d,\"trim_deg\":%.4f,\"limits_deg\":[%.4f,%.4f],\"verified\":%s}",
           NAMES[j], gate.cal.channel[j], gate.cal.sign[j], gate.cal.trim[j], gate.cal.low[j], gate.cal.high[j],
           gate.cal.verified & (1u<<j) ? "true" : "false");
  }
  puts("]}");
}
std::string command(const char* line) {
  CommandLine c;
  if (!c.parse(line)) return "ERR malformed/too long";
  uint32_t now = nowMs();
  if (c.is("status",1)) { status(); return ""; }
  if (c.is("export",1)) { exportCalibration(); return ""; }
  if (c.is("off",1)) { off("command"); return "OK OFF"; }
  if (c.is("stop",1)) { cancelQueue(); gate.stop(now); return "OK STOP frozen; off releases torque"; }
  if (c.is("heartbeat",1)) { gate.heartbeat(now); return ""; }
  if (c.is("face",2)) {
    for (auto& face : faces) if (face == c.words[1]) return "OK FACE";
    return "ERR face name";
  }
  if (c.is("arm",2) || c.is("arm",3)) {
    if (gate.active()) return "ERR hub fault or already armed; off first";
    Mode mode=Mode::Off; int selected=-1;
    if (c.count==2 && !strcmp(c.words[1],"run") && saved) mode=Mode::Run;
    if (c.count==2 && !strcmp(c.words[1],"assembly")) mode=Mode::Assembly;
    if (c.count==3 && !strcmp(c.words[1],"joint")) { mode=Mode::Joint; selected=jointIndex(c.words[2]); }
    if (c.count==3 && c.integer(2,selected)) mode=rawMode(c.words[1]);
    if (!gate.arm(mode,selected,now)) return "ERR arm: select valid channel/joint; run needs all verified+saved";
    cancelQueue(); return "OK ARMED outputs OFF until target";
  }
  if (c.is("centre",1) || c.is("center",1)) {
    if (!gate.centre(now)) return "ERR arm assembly first";
    char out[100]; snprintf(out,sizeof(out),"OK CENTRE CH0..7 raw=90 us=%.2f",angleUs(NEUTRAL)); return out;
  }
  if (c.is("angle",2)) {
    float value;
    if (!c.number(1,value) || gate.selected<0) return "ERR select one channel/joint";
    cancelQueue();
    if (!gate.set(gate.selected,value,now)) return "ERR target";
    char out[100]; snprintf(out,sizeof(out),"OK TARGET %.2f%s",gate.target[gate.selected],
        fabsf(value-gate.target[gate.selected])>.01f ? " CLAMPED" : ""); return out;
  }
  if (c.is("motion",2) || c.is("run",2) || c.is("rest",1)) {
    if (gate.mode!=Mode::Run) return "ERR arm run first (verified+saved calibration)";
    const char* name=c.count==1 ? "rest" : c.words[1];
    if (!strcmp(name,"forward")) name="walk";
    if (!strcmp(name,"backward")) name="walk_backward";
    if (!strcmp(name,"left")) name="turn_left";
    if (!strcmp(name,"right")) name="turn_right";
    for (const auto& m:MOTIONS) if (!strcmp(name,m.name)) {
      cancelQueue(); motion=&m; motionIndex=0; gate.heartbeat(now);
      return std::string("OK MOTION ")+name;
    }
    return "ERR unknown motion";
  }
  if (c.is("servo",3) || c.is("pose",9)) {
    if (gate.mode!=Mode::Run) return "ERR arm run first";
    float values[8], value=0; int j=-1;
    if (c.count==3) {
      j=jointIndex(c.words[1]);
      if (j<0 || !c.number(2,value)) return "ERR servo NAME DEG";
    } else for (int k=0;k<8;++k) if (!c.number(k+1,values[k])) return "ERR pose numbers";
    cancelQueue();
    if (j>=0) gate.set(j,value,now);
    else for (int k=0;k<8;++k) gate.set(k,values[k],now);
    return "OK TARGETS (soft/measured/electrical clamps applied)";
  }
  return gate.active() ? "ERR unknown command or requires OFF" : "ERR syntax; help";
}
}
int main(int argc,char** argv) {
  setvbuf(stdout,nullptr,_IONBF,0);
  bool narrow=false;
  for(int a=1;a<argc;++a) {
    if (!strcmp(argv[a],"--fresh")) saved=false;
    else if (!strcmp(argv[a],"--narrow")) narrow=true;
    else faces.emplace_back(argv[a]);
  }
  // Explicit simulated saved reference calibration, never written to a robot.
  gate.cal.verified=saved ? 255 : 0;
  if (!narrow && saved) for(int j=0;j<8;++j) { gate.cal.low[j]=SOFT_LOW[j]; gate.cal.high[j]=SOFT_HIGH[j]; }
  off("boot");
  puts("READY Sesame S3 calibration+controller; outputs OFF; help");
  std::string line; bool overflow=false;
  while(true) {
    service();
    pollfd input{STDIN_FILENO,POLLIN,0};
    int result=poll(&input,1,1);
    if (result<0) return 0;
    if (!(input.revents&POLLIN)) continue;
    char bytes[192]; ssize_t count=read(STDIN_FILENO,bytes,sizeof(bytes));
    if(count<=0) return 0;
    for(ssize_t i=0;i<count;++i) {
      char ch=bytes[i];
      if(ch=='\r' || ch=='\n') {
        if(overflow) puts("ERR line too long (discarded)");
        else if(!line.empty()) { auto reply=command(line.c_str()); if(!reply.empty()) puts(reply.c_str()); }
        line.clear(); overflow=false;
      } else if(line.size()<159 && !overflow) line+=ch;
      else overflow=true;
    }
  }
}
