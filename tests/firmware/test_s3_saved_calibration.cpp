// Saved calibration across a manifest whose soft limits became narrower.
// tests/test_s3_firmware.py builds every record byte by byte, independently of
// this header, in the layout and checksum the earlier firmware wrote to NVS.
// Files named accept-* load exactly as stored; files named reject-* do not load.
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <iostream>
#include "safe_action.h"

using namespace sesame;

static_assert(sizeof(Calibration)==124 && sizeof(Record)==152, "Stored NVS record size");
static_assert(offsetof(Record,manifest)==4 && offsetof(Record,cal)==24 && offsetof(Record,checksum)==148, "Stored NVS record layout");
static_assert(offsetof(Calibration,oscillator)==4 && offsetof(Calibration,channel)==8 && offsetof(Calibration,sign)==16 &&
              offsetof(Calibration,trim)==24 && offsetof(Calibration,low)==56 && offsetof(Calibration,high)==88 &&
              offsetof(Calibration,verified)==120, "Stored calibration layout");

// What the Python side stored, in manifest joint order R1 R2 L1 L2 R4 R3 L3 L4:
// the widest hip limits the earlier manifests allowed, and one narrowed foot.
const int8_t CHANNEL[8]={7,6,5,4,3,2,1,0};
const float TRIM[8]={1.5f,-2.0f,0.25f,3.0f,0.0f,-0.5f,4.0f,-4.0f};
const float LOW[8]={45,0,0,45,10,0,0,0};
const float HIGH[8]={180,135,135,180,170,180,180,180};
const uint32_t OSCILLATOR=26123456;
const size_t STORED=offsetof(Calibration,verified)+1; // every stored field; trailing padding excluded

int main(int argc, char** argv) {
  int accepted=0, rejected=0;
  for (int i=1;i<argc;++i) {
    unsigned char raw[sizeof(Record)];
    FILE* file=fopen(argv[i],"rb"); assert(file);
    assert(fread(raw,1,sizeof(raw),file)==sizeof(raw) && fgetc(file)==EOF); fclose(file);
    Record r; memcpy(static_cast<void*>(&r),raw,sizeof(r));
    const char* name=strrchr(argv[i],'/'); name=name?name+1:argv[i];
    if (!strncmp(name,"reject-",7)) { assert(!acceptRecord(r)); ++rejected; continue; }
    assert(!strncmp(name,"accept-",7));
    // Loading is acceptance followed by a plain copy, as in loadCalibration().
    assert(acceptRecord(r));
    SafeAction gate; gate.cal=r.cal;
    assert(!memcmp(&gate.cal,raw+offsetof(Record,cal),STORED)); // byte for byte as saved
    assert(gate.cal.version==1 && gate.cal.oscillator==OSCILLATOR && gate.cal.verified==255);
    for (int j=0;j<8;++j) {
      assert(gate.cal.channel[j]==CHANNEL[j] && gate.cal.sign[j]==SIGNS[j] && gate.cal.trim[j]==TRIM[j]);
      assert(gate.cal.low[j]==LOW[j] && gate.cal.high[j]==HIGH[j]);
      // Premise: each stored hip limit is wider than today's soft range.
      assert(gate.cal.beyondSoft(j)==(j<4));
    }
    assert(LOW[0]<SOFT_LOW[0] && HIGH[1]>SOFT_HIGH[1] && HIGH[2]>SOFT_HIGH[2] && LOW[3]<SOFT_LOW[3]);
    // The record is usable as it stands and its own limits bound commands.
    assert(gate.cal.valid() && gate.cal.complete());
    assert(gate.cal.bounded(0,45)==45 && gate.cal.bounded(0,30)==45);     // R1 stored low
    assert(gate.cal.bounded(2,135)==135 && gate.cal.bounded(2,150)==135); // L1 stored high
    assert(gate.cal.bounded(4,0)==10);                                    // R4 narrowed foot kept
    assert(gate.arm(Mode::Run,-1,0));
    assert(gate.set(0,45,0) && gate.target[0]==45 && gate.set(1,135,0) && gate.target[1]==135);
    gate.off();
    // An explicit save keeps the stored values under the current identity.
    Record again; fillRecord(again,gate.cal);
    assert(!strcmp(again.manifest,MANIFEST_ID) && acceptRecord(again));
    assert(!memcmp(&again.cal,raw+offsetof(Record,cal),STORED));
    // A new `limits` edit stays inside the soft range; a refused edit changes nothing.
    Calibration next=gate.cal;
    assert(!next.setLimits(0,45,180) && !next.setLimits(1,0,135));
    assert(!memcmp(&next,&gate.cal,STORED));
    assert(next.setLimits(0,float(SOFT_LOW[0]),float(SOFT_HIGH[0])) && next.valid());
    assert(!next.beyondSoft(0) && next.beyondSoft(1) && next.verified==254);
    ++accepted;
  }
  // Fresh defaults start inside the soft range and save under the current identity.
  const Calibration fresh;
  for (int j=0;j<8;++j) assert(!fresh.beyondSoft(j));
  Record first; fillRecord(first,fresh);
  assert(acceptRecord(first) && !memcmp(&first.cal,&fresh,STORED));
  std::cout << "S3 saved-calibration tests passed: " << accepted << " loaded as stored, " << rejected << " refused\n";
  return 0;
}
