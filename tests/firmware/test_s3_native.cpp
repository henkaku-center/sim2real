#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include "safe_action.h"
#include "command_line.h"
#include "bench_display.h"
#include "../../reference/vendor/tim-servo-debug/firmware/common/sesame_servo_map.h"

using namespace sesame;
void near(float a, float b, float tolerance = .002f) { assert(fabsf(a-b) <= tolerance); }

int main() {
  near(angleUs(0), 732); near(angleUs(90), 1615.28); near(angleUs(180), 2498.56);
  for (int angle=0;angle<=180;++angle) {
    // Compare to Tim's actual pinned implementation, not a duplicated formula.
    assert(pulseTicks(angleUs(angle),25000000,121)==servoAngleToPulse(angle));
    near(angleUs(usAngle(angleUs(angle))),angleUs(angle));
  }
  for (uint32_t osc : {23000000,25000000,26000000,27000000}) {
    uint8_t p = uint8_t(lround(double(osc)/(50*4096))-1);
    double tick = (p+1)*1000000.0/osc;
    for (float us : {732.0f,1500.0f,1615.28f,2498.56f})
      near(pulseTicks(us,osc,p)*tick, us, tick/2+.001);
  }
  assert(pulseTicks(angleUs(180),25000000,121) == 512);
  for (int tenth=1;tenth<=1800;++tenth)
    assert(angleUs(tenth/10.0f)>=angleUs((tenth-1)/10.0f));
  char cell[12];
  formatBenchCell(cell,sizeof(cell),0,"--",false,NAN); assert(!strcmp(cell," 0 --:---"));
  formatBenchCell(cell,sizeof(cell),4,"R1",true,90); assert(!strcmp(cell,"*4 R1: 90"));
  for (int row=0;row<4;++row) { assert(benchChannel(row,0)==row); assert(benchChannel(row,1)==row+4); }
  Calibration cal;
  static_assert(sizeof(Calibration)==124, "Preserve compatible NVS record layout");
  assert(cal.valid() && !cal.complete());
  const int recommended[8]={4,5,0,1,7,6,2,3};
  for(int j=0;j<8;++j)assert(cal.channel[j]==recommended[j]);
  assert(cal.verified==0);
  char legacyId[17]="bd7675604b98ae46", currentId[17], invalidId[17]="0000000000000000";
  char benchId[17]="e669b916d178ac0a";
  static_assert(OE==7 && CLOCK_MEASURE_GPIO==4 && OE!=SDA && OE!=SCL, "Course pin contract");
  strcpy(currentId,MANIFEST_ID);
  assert(compatibleCalibrationManifest(legacyId));assert(compatibleCalibrationManifest(currentId));
  assert(compatibleCalibrationManifest(benchId));
  assert(!compatibleCalibrationManifest(invalidId));legacyId[16]='x';assert(!compatibleCalibrationManifest(legacyId));
  Calibration savedLegacy=cal;
  savedLegacy.channel[0]=-1;savedLegacy.oscillator=27000000;savedLegacy.trim[1]=2;
  assert(savedLegacy.valid());Calibration loaded=savedLegacy;
  assert(loaded.channel[0]==-1 && loaded.oscillator==27000000 && loaded.trim[1]==2);
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
  g.cal.channel[0]=-1;assert(!g.arm(Mode::Joint,0,0));g.cal.channel[0]=DEFAULT_CHANNELS[0];
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
  g.set(0,180,0); near(g.target[0],177); g.step(20); near(g.current[0],90+RUN_RATE*0.02f);
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
  assert(c.parse("arm bench 7") && c.is("arm",3) && c.integer(2,n) && n==7);
  assert(rawMode(c.words[1])==Mode::Bench);
  assert(rawMode("hornless")==Mode::Bench); // compatibility only, not classroom wording
  assert(rawMode("invalid")==Mode::Off);
  assert(c.parse("arm bench 7 extra") && !c.is("arm",3));
  // Full commanded range on every raw channel, without changing production
  // calibration limits, while preserving slew/watchdog and output exclusion.
  SafeAction bench;uint32_t now=0;uint16_t wanted[16];
  for(int channel=0;channel<8;++channel) {
    assert(bench.arm(Mode::Bench,channel,now));assert(bench.enabled==0);
    assert(!bench.set((channel+1)%8,0,now));
    for(float target:{0.0f,90.0f,180.0f,90.0f}) {
      assert(bench.set(channel,target,now));near(bench.target[channel],target);
      unsigned iterations=0;
      while(!bench.settled()) {
        const float prior=bench.current[channel];now+=20;bench.heartbeat(now);assert(bench.step(now));
        assert(fabsf(bench.current[channel]-prior)<=CAL_RATE*.02f+.001f);
        assert(planOutputs(bench,121,wanted));
        for(int output=0;output<16;++output)assert((wanted[output]!=4096)==(output==channel));
        assert(++iterations<1000);
      }
      near(bench.current[channel],target,.011f);
    }
    assert(bench.cal.low[channel]==fmaxf(SOFT_LOW[channel],INITIAL_LOW));
    bench.off();assert(planOutputs(bench,121,wanted));for(auto tick:wanted)assert(tick==4096);
  }
  assert(bench.arm(Mode::Bench,0,now));assert(bench.set(0,-100,now));near(bench.target[0],0);
  assert(bench.set(0,300,now));near(bench.target[0],180);
  assert(!bench.set(0,NAN,now));assert(!bench.step(now+WATCHDOG_MS+1));
  std::cout << "S3 native safety/mapping/parser/motion tests passed\n";
}
