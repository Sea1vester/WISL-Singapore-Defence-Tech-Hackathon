"""Regenerate the Hermes 900 STANAG and aunav ROS demo fixtures near Amesbury.

Run from the repo root:  python3 sdth-telemetry/scripts/generate_multivendor_fixtures.py
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "sdth-demo" / "fixtures"
LAT0, LON0 = 51.1789, -1.8262  # Stonehenge/Amesbury cache region
M_PER_DEG_LAT = 111_132.0

def ll(north_m, east_m):
    lat = LAT0 + north_m / M_PER_DEG_LAT
    lon = LON0 + east_m / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))
    return lat, lon

def fmt(v, nd=7):
    return f"{v:.{nd}f}".rstrip("0").rstrip(".") if "." in f"{v:.{nd}f}" else f"{v:.{nd}f}"

# ---------- Hermes 900 STANAG: perimeter circuit, GNSS degrades mid-flight ----------
# Route: takeoff -> rectangle NE(900,500) SE(-300,500) SW(-300,-400) NW(900,-400) -> home.
waypts = [(0, 0), (500, 900), (-300, 900), (-300, -400), (500, -400), (500, 0), (0, 0)]
ALT_CRUISE = 118.0
SEG_S = 75  # seconds per leg
lines = []
t0 = "2026-03-19T09:14"
elapsed = 0.0
idx = 0
def ts(sec):
    m = int(sec // 60); s = sec - m * 60
    return f"2026-03-19T09:{14 + m:02d}:{s:04.1f}Z"

for leg, ((n0, e0), (n1, e1)) in enumerate(zip(waypts, waypts[1:])):
    steps = int(SEG_S / 2)
    for i in range(steps):
        f = i / steps
        n = n0 + (n1 - n0) * f
        e = e0 + (e1 - e0) * f
        lat, lon = ll(n, e)
        t = elapsed + i * 2
        # climb on leg 0, descend on final approach leg
        if leg == 0:
            alt = 2 + ALT_CRUISE * min(1.0, t / 60)
        elif leg == len(waypts) - 2:
            alt = ALT_CRUISE * (1 - 0.4 * f)
        else:
            alt = ALT_CRUISE
        heading = (math.degrees(math.atan2(e1 - e0, n1 - n0)) + 360) % 360
        # GNSS degradation window: mid-flight, sats 15 -> 5 -> 14
        in_gap = 170 <= t <= 240
        sats = 5 if in_gap else (15 - idx % 2)
        warn = " warning=GNSS_DEGRADED" if in_gap else ""
        msg = "WARNING" if in_gap else "TELEMETRY"
        batt = 94 - t * 0.02
        roll = 2.5 * math.sin(t / 9)
        pitch = -1.4 + 0.8 * math.sin(t / 13)
        lines.append(
            f"<134>1 {ts(t)} hermes-fcs nav 4021 1001 - [SDTH@32473] {msg} "
            f"lat={lat:.7f} lon={lon:.7f} alt={alt:.1f} roll={roll:.1f} pitch={pitch:.1f} "
            f"heading={heading:.1f} battery_pct={batt:.1f} flight_mode=AUTO "
            f"gps_satellites={sats}{warn}"
        )
        idx += 1
    elapsed += SEG_S

(OUT / "hermes900_amesbury_perimeter.stanag").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("stanag lines:", len(lines))

# ---------- aunav.NEO ROS log: ground route check, clean ----------
# Route: figure sweep around muster point at (250, -150)
ros = []
t = 1_773_930_000.0  # ~2026-03-19
for i in range(96):
    a = i * 0.12
    n = -150 + 180 * math.sin(a)
    e = 250 + 260 * math.sin(a) * math.cos(a) * 2
    lat, lon = ll(n, e)
    head = (math.degrees(a) + 90) % 360
    batt = 88 - i * 0.08
    ros.append(
        f"[ROS_INFO] [{t:.3f}] /aunav/telemetry lat={lat:.7f} lon={lon:.7f} "
        f"alt=1.4 roll={1.1*math.sin(a):.1f} pitch={0.6*math.cos(a):.1f} "
        f"heading={head:.1f} speed_mps={2.1 + 0.4*math.sin(a*2):.2f} "
        f"battery_pct={batt:.1f} flight_mode=PATROL"
    )
    t += 3.0
(OUT / "aunav_neo_amesbury_patrol.ros").write_text("\n".join(ros) + "\n", encoding="utf-8")
print("ros lines:", len(ros))
