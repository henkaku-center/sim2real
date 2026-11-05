# Re-apply this robot's calibration after a manifest change resets NVS.
# Fresh calibration 2026-10-29 (build 11+): default course map and signs.
# USB only, battery unplugged. Usage: apply_calibration.py PORT
import sys, time, serial

OSCILLATOR = 27815198
CAL = {"L1": (0, -1), "L2": (1, 1), "L3": (2, -1), "L4": (3, 1),     # name: (channel, sign)
       "R1": (4, 1), "R2": (5, -1), "R3": (6, 1), "R4": (7, -1)}
LIMITS = {"R1": "45 180", "L2": "45 180", "R2": "0 135", "L1": "0 135",  # hips: firmware soft range (walk needs it)
          "L3": "0 180", "R4": "0 180", "R3": "0 180", "L4": "0 180"}  # feet full range (stock wave/dance need it)

s = serial.Serial(sys.argv[1], 115200, timeout=0.3)
time.sleep(1.5); s.read(8000)
cmds = ["off", f"oscillator {OSCILLATOR}"]
for n, (ch, sg) in CAL.items():
    cmds += [f"map {n} {ch}", f"sign {n} {sg}", f"limits {n} {LIMITS[n]}"]
cmds += [f"verify {n}" for n in CAL] + ["save", "show"]
for c in cmds:
    s.write((c + "\n").encode()); time.sleep(0.3)
time.sleep(0.5); out = s.read(12000).decode(errors="replace"); s.close()
print("\n".join(l for l in out.splitlines() if l.startswith(("ERR", "OK SAVED", "manifest", "R", "L"))))
if "OK SAVED" not in out or "ERR" in out: sys.exit("calibration NOT saved")
