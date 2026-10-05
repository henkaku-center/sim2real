#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include "safe_action.h"
#include "command_line.h"

using namespace sesame;
void near(float a, float b, float tolerance = .002f) { assert(fabsf(a-b) <= tolerance); }

int main() {
  near(angleUs(0), 732); near(angleUs(90), 1830.5); near(angleUs(180), 2929);
  for (uint32_t osc : {23000000,25000000,26000000,27000000}) {
    uint8_t p = uint8_t(lround(double(osc)/(50*4096))-1);
    double tick = (p+1)*1000000.0/osc;
    for (float us : {732.0f,1500.0f,1830.5f,2929.0f})
      near(pulseTicks(us,osc,p)*tick, us, tick/2+.001);
  }
  assert(pulseTicks(2929,25000000,121) == 600); // regression: old cap was 512
  Calibration cal;
  assert(cal.valid() && !cal.complete());
  for (int j=0;j<8;++j) {
    cal.channel[j]=j; cal.low[j]=SOFT_LOW[j]; cal.high[j]=SOFT_HIGH[j];
    near(cal.physical(j,45),45); // upstream absolute angles are NOT signed twice
    near(cal.canonical(j,135),135);
    cal.sign[j] *= -1;
    near(cal.physical(j,45),135);
    near(cal.canonical(j,135),45);
    cal.sign[j] *= -1;
  }
  cal.verified=255; assert(cal.complete());
  cal.channel[1]=0; assert(!cal.valid()); cal.channel[1]=1;
  cal.trim[0]=NAN; assert(!cal.valid()); cal.trim[0]=3;
  near(cal.bounded(0,180),177); near(cal.physical(0,cal.bounded(0,180)),180);
  cal.trim[1]=-3; near(cal.bounded(1,0),3);
  cal.low[0]=44; assert(!cal.valid()); cal.low[0]=45;
  cal.oscillator=0; assert(!cal.valid()); cal.oscillator=25000000;
  cal.high[0]=INFINITY; assert(!cal.valid()); cal.high[0]=180;
  SafeAction g;
  assert(!g.active() && !g.enabled);
  assert(!g.set(0,90,0));
  assert(!g.arm(Mode::Run,-1,0));
  assert(!g.arm(Mode::Joint,0,0));
  assert(!g.arm(Mode::Channel,8,0));
  assert(g.arm(Mode::Channel,3,0) && g.enabled==0);
  assert(!g.set(2,95,0)); assert(!g.set(3,NAN,0));
  assert(g.set(3,180,0)); near(g.target[3],95); assert(g.enabled==(1<<3));
  g.step(20); near(g.current[3],90.3);
  g.stop(20); g.step(40); near(g.current[3],90.3); near(g.target[3],90.3);
  assert(g.step(520)); assert(!g.step(521)); assert(!g.active() && !g.enabled && g.timedOut);
  g.heartbeat(600); assert(!g.active()); // stale host cannot revive watchdog
  assert(g.arm(Mode::Hornless,0,1000)); assert(!g.arm(Mode::Hornless,1,1000));
  assert(g.set(0,0,1000)); g.step(1020); near(g.current[0],89.7);
  // A queued internal motion cannot keep itself alive by consuming waypoints.
  g.set(0,180,g.lastHeartbeat);
  assert(!g.step(1501));
  assert(g.arm(Mode::Assembly,-1,2000) && !g.enabled);
  assert(!g.set(0,180,2000)); assert(g.centre(2000));
  for (int j=0;j<8;++j) { near(g.physical(j),90); assert(g.channel(j)==j); }
  assert(g.enabled==255); g.off();
  // Wrap-safe monotonic watchdog and no catch-up leap after a scheduler stall.
  assert(g.arm(Mode::Hornless,0,0xffffff00)); g.set(0,180,0xffffff00);
  assert(g.step(0x00000010)); near(g.current[0],90.3);
  assert(!g.step(0x00000100));
  g.cal=cal; assert(g.arm(Mode::Run,-1,0));
  g.set(0,180,0); near(g.target[0],177); g.step(20); near(g.current[0],91.2);
  assert(!g.set(8,90,20)); g.off();
  // All stock motion targets must stay within the manifest's soft envelope.
  unsigned count=0;
  for (const auto& m : MOTIONS) {
    assert(m.count>0); ++count;
    for (unsigned s=0;s<m.count;++s) for (int j=0;j<8;++j) {
      int angle=m.steps[s].degrees[j];
      assert(angle == -1 || (angle>=SOFT_LOW[j] && angle<=SOFT_HIGH[j]));
    }
  }
  assert(count==19);
  CommandLine c; float f; int n;
  assert(c.parse("arm joint R1") && c.is("arm",3));
  for (const char* text : {"angle nan","angle inf","angle 90junk","angle 1e100"}) {
    assert(c.parse(text)); assert(!c.number(1,f));
  }
  assert(c.parse("map R1 1.5")); assert(!c.integer(2,n));
  assert(c.parse("angle 90 trailing") && !c.is("angle",2));
  char longline[170]; memset(longline,'x',169); longline[169]=0; assert(!c.parse(longline));
  assert(!c.parse("1 2 3 4 5 6 7 8 9 10 11 12 13"));
  std::cout << "S3 native safety/mapping/parser/motion tests passed\n";
}
