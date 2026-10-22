// No device or electrical-accuracy claim: deterministic clock/parser/output tests.
#include <cassert>
#include <cmath>
#include <iostream>
#include "clock_measurement.h"
#include "safe_action.h"
using namespace sesame;
static void near(double actual,double expected,double tolerance=1e-6) {
  assert(std::abs(actual-expected)<=tolerance);
}
static void feed(ClockMeasurement& clock,uint32_t start=0,uint32_t period=20000) {
  const auto generation=clock.report().generation;
  for(unsigned i=0;i<101;i++)assert(clock.edge(generation,start+i*period)==(i==100));
}
int main() {
  CommandLine c;
  for(auto pair : {std::make_pair("clock measure",ClockCommand::Measure),
                  std::make_pair("clock status",ClockCommand::Status),
                  std::make_pair("clock abort",ClockCommand::Abort)}) {
    assert(c.parse(pair.first));assert(clockCommand(c)==pair.second);
  }
  for(const char* invalid:{"clock","clock measure 4","clock measure extra","clock abort now","clock nan","clock MEASURE"}) {
    assert(c.parse(invalid));assert(clockCommand(c)==ClockCommand::Invalid);
  }
  assert(c.parse("oscillator 25000000"));assert(clockCommand(c)==ClockCommand::None);
  ClockMeasurement clock;
  assert(clock.report().outcome==ClockOutcome::Idle && !clock.active());
  assert(clock.start(10,121));const auto first=clock.report().generation;
  assert(!clock.start(11,121));assert(clock.report().generation==first);
  clock.edge(first-1,100);assert(clock.report().edges==0);
  feed(clock);assert(clock.active());assert(clock.report().edges==101);
  assert(!clock.edge(first,3000000));assert(clock.report().edges==101); // bounded ISR work/data
  assert(clock.poll(2011));assert(clock.report().outcome==ClockOutcome::Complete);
  near(clock.report().observedHz(),50);near(clock.report().oscillatorHz(),24985600);
  near(clock.report().jitterPpm(),0);
  assert(!clock.poll(3000));clock.abort(ClockOutcome::Aborted); // terminal result persists
  assert(clock.report().outcome==ClockOutcome::Complete);
  assert(clock.start(20,121));assert(clock.report().generation!=first);
  clock.edge(first,20);assert(clock.report().edges==0);
  const auto second=clock.report().generation;
  // 25MHz / (4096*122), not coarse integer pulse counts in a one-second gate.
  for(unsigned i=0;i<101;i++)clock.edge(second,uint32_t(std::llround(i*19988.48)));
  assert(clock.poll(2021));near(clock.report().oscillatorHz(),25000000,1);
  assert(clock.report().outcome==ClockOutcome::Complete);
  assert(clock.start(0xfffffff0u,121));feed(clock,0xffff0000u);
  assert(clock.poll(uint32_t(0xfffffff0u+2001u)));near(clock.report().observedHz(),50);
  assert(clock.start(0xfffffff0u,121));
  assert(!clock.poll(uint32_t(0xfffffff0u+3999u)));
  assert(clock.poll(uint32_t(0xfffffff0u+4000u)));
  assert(clock.report().outcome==ClockOutcome::Timeout && clock.report().edges==0);
  // Completion cannot launder a deadline exceeded during a stalled main loop.
  assert(clock.start(0,121));feed(clock);assert(clock.poll(4000));
  assert(clock.report().outcome==ClockOutcome::Timeout);
  for(uint32_t period:{0u,500u,40000u,50000u}) {
    assert(clock.start(0,121));feed(clock,0,period);assert(clock.poll(3000));
    assert(clock.report().outcome==ClockOutcome::Quality);
  }
  assert(clock.start(0,121));
  for(unsigned i=0;i<101;i++)clock.edge(clock.report().generation,i*20000+(i>50?20000:0));
  assert(clock.poll(2500));assert(clock.report().outcome==ClockOutcome::Quality); // dropped edge
  assert(clock.start(0,121));
  for(unsigned i=0;i<101;i++)clock.edge(clock.report().generation,i*20000+(i%2?300:0));
  assert(clock.poll(2500));assert(clock.report().outcome==ClockOutcome::Quality); // excess jitter
  for(auto reason:{ClockOutcome::Aborted,ClockOutcome::Fault,ClockOutcome::Disconnected,
                   ClockOutcome::Watchdog,ClockOutcome::CommandError}) {
    assert(clock.start(0,121));clock.edge(clock.report().generation,100);
    clock.abort(reason);clock.edge(clock.report().generation,20100);
    assert(clock.report().outcome==reason && clock.report().edges==1 && !clock.active());
  }
  SafeAction gate;uint16_t wanted[16];
  assert(gate.arm(Mode::ClockMeasure,-1,0));
  assert(!gate.arm(Mode::Channel,0,0));assert(!gate.centre(0));
  for(int j=0;j<8;j++)assert(!gate.set(j,90,0));
  const auto calibration=gate.cal;
  gate.enabled=255; // defense in depth: corrupt/stale mask still cannot enable CH0..14
  assert(planOutputs(gate,121,wanted));
  for(int ch=0;ch<15;ch++)assert(wanted[ch]==4096);
  assert(wanted[15]==pulseTicks(1500,gate.cal.oscillator,121));
  assert(gate.step(500));assert(!gate.step(501));
  assert(planOutputs(gate,121,wanted));for(auto value:wanted)assert(value==4096);
  assert(gate.cal.oscillator==calibration.oscillator && gate.cal.verified==calibration.verified);
  assert(gate.arm(Mode::Channel,1,600));assert(gate.set(1,95,600));
  assert(planOutputs(gate,121,wanted));assert(wanted[1]!=4096 && wanted[15]==4096);
  gate.off();assert(planOutputs(gate,121,wanted));for(auto value:wanted)assert(value==4096);
  std::cout<<"Clock capture/parser/generation/deadline/quality/output exclusion tests passed\n";
}
