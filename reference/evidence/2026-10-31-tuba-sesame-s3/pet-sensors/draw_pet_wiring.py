"""Where the touch pad and the M5Stack ToF unit connect (run: python draw_pet_wiring.py)."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle
fig, axes = plt.subplots(1, 2, figsize=(16, 7), dpi=120)
for ax in axes: ax.set_xlim(0, 20); ax.set_ylim(0, 14); ax.set_aspect("equal"); ax.axis("off")
def board(ax, x, y, w, h, c, t):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.3", fc=c, ec="black", lw=1.5))
    ax.text(x + w / 2, y + h + 0.4, t, ha="center", fontsize=11, weight="bold")

# 1: touch pad -> GPIO6 on the SuperMini pin row
ax = axes[0]
ax.set_title("1. TOUCH PAD -> pin 6 of the ESP32-S3 SuperMini\nfind the pin row that already has the SDA, SCL and OE wires", fontsize=11)
board(ax, 2, 3, 16, 3.2, "#1565c0", "SuperMini: pin row  TX  RX  1  2  3  4  5  6  7")
row = ["TX", "RX", "1", "2", "3", "4", "5", "6", "7"]
used = {"2": "SDA wire", "3": "SCL wire", "4": "clock", "7": "OE wire"}
for i, n in enumerate(row):
    x = 3 + i * 1.75
    c = "#e53935" if n == "6" else ("#9e9e9e" if n in used else "gold")
    ax.add_patch(Circle((x, 4.6), 0.45, fc=c, ec="black"))
    ax.text(x, 3.6, n, ha="center", color="white", fontsize=11, weight="bold")
    if n in used: ax.text(x, 6.9, used[n], ha="center", fontsize=8, rotation=45)
ax.add_patch(Circle((15.25, 11), 1.6, fc="#cfd8dc", ec="#607d8b", lw=2)); ax.text(15.25, 11, "metal\ndisc", ha="center", va="center", fontsize=9)
ax.plot([15.25, 15.25, 15.25], [9.4, 6.0, 5.05], color="#e53935", lw=4)
ax.text(10, 12.6, "pin 6 = the free pin right next to the OE wire (pin 7)", ha="center", fontsize=10, weight="bold", color="#c62828")
ax.text(10, 1.2, "1 wire: metal disc (or copper tape) -> pin 6. Solder, or twist + tape very firmly.\nStick the disc inside the top of the dome. Nothing else to connect.", ha="center", fontsize=10)

# 2: ToF unit -> free end of the hub's 6-pin header
ax = axes[1]
ax.set_title("2. M5STACK ToF -> free 6-pin header at the other end of the servo hub (PCA9685)\nuse your Grove-to-Dupont cable; follow the LABELS, not the wire colours", fontsize=11)
board(ax, 1, 3, 7, 7.5, "#1e88e5", "servo hub (PCA9685)\nfree end header")
hub = ["GND", "OE", "SCL", "SDA", "VCC", "V+"]
for i, n in enumerate(hub):
    y = 9.5 - i * 1.2
    c = "#9e9e9e" if n in ("OE", "V+") else "gold"
    ax.add_patch(Circle((7.3, y), 0.38, fc=c, ec="black")); ax.text(6.6, y, n, ha="right", va="center", color="white", fontsize=10, weight="bold")
board(ax, 13, 4.5, 5, 5, "#eeeeee", "M5Stack Unit ToF")
tof = {"GND": 9.0, "5V": 7.8, "SDA": 6.6, "SCL": 5.4}
for n, y in tof.items():
    ax.add_patch(Circle((13.3, y), 0.38, fc="gold", ec="black")); ax.text(14.0, y, n, va="center", fontsize=10, weight="bold")
links = [("GND", "GND", "black"), ("VCC", "5V", "red"), ("SDA", "SDA", "#fbc02d"), ("SCL", "SCL", "#90a4ae")]
for h, t, c in links:
    y1 = 9.5 - hub.index(h) * 1.2; y2 = tof[t]
    ax.plot([7.7, 10.5, 10.5, 12.9], [y1, y1, y2, y2], color=c, lw=4)
ax.text(10, 1.0, "hub GND -> ToF GND,  hub VCC (3.3 V) -> ToF 5V pin,  hub SDA -> SDA,  hub SCL -> SCL\n"
        "(VCC, not V+: keeps the I2C lines at 3.3 V). Mount the ToF lens facing the floor, >= 3 cm above it.",
        ha="center", fontsize=9.5)
plt.tight_layout(); plt.savefig("pet-wiring.png", bbox_inches="tight")
