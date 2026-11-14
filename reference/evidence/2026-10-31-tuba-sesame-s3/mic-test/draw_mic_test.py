"""How to build the AE-MICAMP kit and wire it to the spare SuperMini for a laptop test."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle, FancyArrowPatch
fig, axes = plt.subplots(1, 4, figsize=(22, 7), dpi=110)
for ax in axes: ax.set_xlim(0, 20); ax.set_ylim(0, 20); ax.set_aspect("equal"); ax.axis("off")
def board(ax, x, y, w, h, c="#2e7d32"): ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.4", fc=c, ec="black", lw=1.5))
def txt(ax, x, y, s, **k): ax.text(x, y, s, ha="center", va="center", **k)

# 1 mic capsule
ax = axes[0]; ax.set_title("STEP 1  Mic capsule\nfrom the FRONT (plain side, 'AE-MICAMP' printed)", fontsize=12)
board(ax, 4, 6, 12, 8)
ax.add_patch(Circle((12, 10), 3, fc="#bdbdbd", ec="black", lw=2)); txt(ax, 12, 10, "capsule", fontsize=9)
for i, n in enumerate(["OUT", "GND", "VCC"]): ax.add_patch(Circle((5.5, 12.5 - i * 2.3), .55, fc="gold", ec="black")); ax.text(6.4, 12.5 - i * 2.3, n, color="white", va="center", fontsize=10, weight="bold")
txt(ax, 10, 3.8, "Push its 2 legs through the 'M1' holes\nand solder them on the BACK, then cut the extra.\nLeg joined to the metal case = (-),\nthe other leg into the hole marked '+'.\nSolder fast (2-3 s): heat kills the capsule.", fontsize=10)

# 2 wires straight into JP holes (header optional)
ax = axes[1]; ax.set_title("STEP 2  Three wires into JP1\n(label them with tape: 1, 2, 3)", fontsize=12)
board(ax, 3, 8, 9, 7)
labels = [("1  VCC", "#e53935"), ("2  GND", "#212121"), ("3  OUT", "#fbc02d")]
for i, (n, c) in enumerate(labels):
    y = 13.5 - i * 2.2
    ax.add_patch(Circle((10.6, y), .5, fc="gold", ec="black")); ax.text(9.6, y, n, color="white", ha="right", va="center", fontsize=10, weight="bold")
    ax.plot([10.6, 18.5], [y, y], color=c, lw=5)
txt(ax, 10, 4.3, "Easiest: solder each red wire straight into a JP1 hole.\n(Or solder the 3-pin header in, then the wires to it.)\nPin 1 is marked '1' next to JP on the board.\nAll your wires are red, so TAPE-LABEL them now:\n1 = VCC,  2 = GND,  3 = OUT", fontsize=10)

# 3 to spare SuperMini
ax = axes[2]; ax.set_title("STEP 3  Wires to the SPARE SuperMini\n(read the pin labels printed on its underside)", fontsize=12)
board(ax, 6, 3, 8, 13, "#1565c0")
ax.add_patch(Rectangle((8.5, 15.4), 3, 1.6, fc="silver", ec="black")); txt(ax, 10, 16.2, "USB-C", fontsize=9)
left = ["TX", "RX", "1", "2", "3", "4", "5", "6", "7"]; right = ["5V", "GND", "3V3", "13", "12", "11", "10", "9", "8"]
pin = {}
for i, (l, r) in enumerate(zip(left, right)):
    y = 14.2 - i * 1.35
    for x, n, ha in ((6.7, l, "left"), (13.3, r, "right")):
        hot = n in ("5", "GND", "3V3")
        ax.add_patch(Circle((x, y), .42, fc="#e53935" if hot else "gold", ec="black"))
        ax.text(x + (.7 if ha == "left" else -.7), y, n, color="white", ha=ha, va="center", fontsize=8, weight="bold")
        pin[n] = (x, y)
for (n, c, p) in [("1 VCC", "#e53935", "3V3"), ("2 GND", "#212121", "GND"), ("3 OUT", "#fbc02d", "5")]:
    x, y = pin[p]; xs = 19 if x > 10 else 1
    ax.plot([xs, x], [y, y], color=c, lw=4); ax.text(xs, y + .6, n, ha="center", fontsize=9, weight="bold")
txt(ax, 10, 1.2, "wire 1 VCC -> 3V3   wire 2 GND -> GND   wire 3 OUT -> 5\nWrap each wire end tightly round the pin and solder.\nNEVER 5V on VCC (pin order may differ: trust the labels).", fontsize=9.5)

# 4 USB to laptop
ax = axes[3]; ax.set_title("STEP 4  USB-C cable to the laptop", fontsize=12)
board(ax, 2, 8, 5, 6, "#1565c0"); txt(ax, 4.5, 11, "spare\nSuperMini", color="white", fontsize=10)
ax.add_patch(FancyBboxPatch((12, 6), 7, 9, boxstyle="round,pad=0.02,rounding_size=0.5", fc="#cfd8dc", ec="black")); txt(ax, 15.5, 10.5, "laptop", fontsize=12)
ax.plot([7, 12], [11, 11], color="black", lw=6); txt(ax, 9.5, 12, "USB-C data cable", fontsize=9)
txt(ax, 10, 3.5, "Plug the SuperMini's USB-C into the laptop\n(same cable you use for the robot).\nNo battery, no servos needed.\nThen tell Claude: I flash a mic test and you\nsee a live level bar + your words as text.", fontsize=10)
plt.tight_layout(); plt.savefig("mic-test-wiring.png", bbox_inches="tight")
