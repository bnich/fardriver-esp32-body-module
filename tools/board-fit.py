#!/usr/bin/env python3
"""Area and height budget for the ESP32 body module's 4-board stack.

Backs the computed figures in `docs/board-design-record.md` (§1, §3, §4).
Re-run it when M18 (the cavity) or M19 (part heights) land: edit the two
PARAMETERS blocks below, run, and update the record's tables from the output.

    python3 tools/board-fit.py

Nothing here is a routing multiplier. Footprints are datasheet envelopes and
the packing is a real shelf-pack, because a density fudge factor answered this
question wrongly once already.
"""

# ── PARAMETERS ── M18: the cavity ────────────────────────────────────────────
# ⚠️ The cavity lives in tools/board_params.py -- ONE home, imported by both
# this budget and the PCB outline emitter, so the number that proves the design
# fits and the number that gets manufactured cannot drift apart.
import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
from tools.board_params import (            # noqa: E402
    CAVITY_L, CAVITY_W, CAVITY_H, WALL, FLOOR, LID, CAVITY_MEASURED,
)

# ── PARAMETERS ── M19: heights not yet read off a datasheet ──────────────────
H_CHOKE = 18.0      # Wurth 7448022010 — ⬜ THE CRITICAL UNKNOWN (§4)
H_CONN_STD = 12.0   # right-angle connector, standard (JST XH class)
H_CONN_LOW = 6.0    # right-angle connector, low profile (JST PH class)
H_FUSEHOLDER = 12.0 # Schurter FAC 0031.3803 — ⬜

PCB, GAP, PLATE = 1.6, 1.0, 3.0     # PLATE = BD-9 alloy shield / heatspreader

from tools.board_params import BOARD_W, BOARD_L, AVAIL_H   # noqa: E402
AREA = BOARD_W * BOARD_L

# ── PARTS ── (ref, w, h, qty, clearance, height) ─────────────────────────────
L1 = [  # HVIN — 84 V entry, protection, start latch (D24)
    ("SMCJ90A DO-214AB",      8.0,  6.0,  1, 2.5,  2.6),
    ("CM choke 7448022010",  22.5, 20.5,  2, 1.5, H_CHOKE),
    ("Y2 VY2472M49Y5US6",    13.0,  7.0,  4, 2.5, 14.0),
    ("IXTP26P20P TO-220AB",  11.0, 16.0,  2, 2.5, 16.0),
    ("74HC14 DIP-14",        19.0,  8.0,  1, 1.0,  4.5),
    ("RC film 2.2uF",        13.0,  7.0,  1, 1.0,  9.0),
    ("BSS126 SOT-23",         3.0,  3.0,  2, 1.0,  1.2),
    ("passives 0805",         2.0,  1.5, 24, 0.6,  1.0),
    ("conn B+/B- (84V)",     20.0, 10.0,  1, 3.0, H_CONN_STD),
    ("conn KEY switch",      12.0, 10.0,  1, 3.0, H_CONN_LOW),
    ("conn KEY out (84V)",   10.0, 10.0,  1, 3.0, H_CONN_LOW),
    ("conn HV-LINK 5.08mm",  24.0,  8.0,  1, 2.5, H_CONN_LOW),
]
L2 = [  # CONV — both converters. BD-14: the two cans mount UNDERSIDE.
    ("TDK CN150B110-12/CO",  58.3, 37.2,  1, 2.0, 12.7),
    ("Cincon EC7BW-110S05",  50.8, 25.4,  1, 2.0, 10.2),
    ("EKXJ221 220u/220V",    25.0, 18.0,  2, 1.5, 18.0),   # underside — see BD14
    ("1N4007 DO-41",         10.0,  3.0,  1, 2.0,  3.0),
    ("FAC 0031.3803 + fuse", 30.0, 12.0,  1, 2.5, H_FUSEHOLDER),
    ("passives 0805",         2.0,  1.5,  8, 0.6,  1.0),
    ("conn HV-LINK 5.08mm",  24.0,  8.0,  1, 2.5, H_CONN_LOW),
    ("conn PWR-UP",          22.0,  8.0,  1, 1.0, H_CONN_LOW),
]
L3 = [  # DRV — 12 V drivers + brake circuit (D23)
    ("TPS4H160B HTSSOP-28",  12.0, 10.0,  2, 1.5,  1.2),
    ("20k pullup 0805",       2.0,  1.5,  6, 0.6,  1.0),
    ("AO3400A SOT-23",        3.0,  3.0,  4, 1.0,  1.2),
    ("AO3407A SOT-23 (Q1)",   3.0,  3.0,  1, 1.0,  1.2),
    ("1N4148 SOD-123",        4.0,  2.0,  6, 0.8,  1.1),
    ("passives 0805",         2.0,  1.5, 30, 0.6,  1.0),
    ("conn headlight (4)",   20.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn tail+rear (5)",   24.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn front turn (4)",  20.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn horn (2)",        11.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn fan+buzzer (4)",  20.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn brake levers (4)",20.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn PWR-UP",          22.0,  8.0,  1, 1.0, H_CONN_LOW),
    ("conn STACK 2x20",      28.0,  8.0,  1, 1.0, H_CONN_LOW),
]
L4 = [  # BRAIN — logic
    ("ESP32-S3-WROOM-1-N8",  25.5, 18.0,  1, 2.0,  3.1),
    ("MCP23017 SOIC-28",     18.0,  7.5,  2, 1.5,  2.7),
    ("SN65HVD230 SOIC-8",     5.0,  4.0,  1, 1.0,  1.8),
    ("PESD5V0S4UD SOT-457",   3.0,  3.0,  4, 1.0,  1.1),
    ("USB-C receptacle",      9.0,  7.5,  1, 2.0,  3.5),
    ("boost FET + pulldown",  3.0,  3.0,  1, 1.0,  1.2),
    ("class-A nets",          2.0,  1.5, 36, 0.6,  1.0),
    ("passives 0805",         2.0,  1.5, 24, 0.6,  1.0),
    ("conn left pod (8)",    30.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn right pod (5)",   24.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn FarDriver (6)",   26.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn display 9-pin",   32.0,  9.0,  1, 1.5, H_CONN_LOW),
    ("conn STACK 2x20",      28.0,  8.0,  1, 1.0, H_CONN_LOW),
]
BOARDS = [("L1", "HVIN", L1), ("L2", "CONV", L2), ("L3", "DRV", L3), ("L4", "BRAIN", L4)]

# BD-14: parts mounted on a board's underside do not add to its top-side height.
UNDERSIDE = {("L2", "EKXJ221 220u/220V")}


def raw_area(parts):
    return sum(w * h * q for _, w, h, q, _, _ in parts)


def shelf_pack(parts, board_w):
    """Greedy shelf pack, tallest shelf first. Returns length consumed."""
    rects = []
    for ref, w, h, qty, cl, _ in parts:
        for _ in range(qty):
            rects.append((max(w, h) + 2 * cl, min(w, h) + 2 * cl, ref))
    rects.sort(key=lambda r: -r[1])
    x = y = shelf = 0.0
    for w, h, ref in rects:
        if w > board_w:
            w, h = h, w
        if w > board_w:
            return None, f"{ref} exceeds a {board_w:.0f} mm board"
        if x + w > board_w:
            y, x, shelf = y + shelf, 0.0, 0.0
        x += w
        shelf = max(shelf, h)
    return y + shelf, None


def top_height(layer, parts):
    return max(h for ref, _, _, _, _, h in parts if (layer, ref) not in UNDERSIDE)


_prov = "measured" if CAVITY_MEASURED else "⚠️ ESTIMATE, NOT MEASURED (M18)"
print(f"M18 cavity      {CAVITY_L:.0f} x {CAVITY_W:.0f} x {CAVITY_H:.0f} mm   ({_prov})")
print(f"board envelope  {BOARD_W:.0f} x {BOARD_L:.0f} = {AREA:.0f} mm²"
      f"   internal height {AVAIL_H:.1f} mm\n")

print("AREA")
print(f"  {'':2} {'board':6} {'raw mm²':>9} {'density':>8}  {'shelf-packed':>13}")
total = 0.0
for tag, name, parts in BOARDS:
    ra = raw_area(parts)
    total += ra
    length, err = shelf_pack(parts, BOARD_W)
    packed = "BLOCKED" if err else f"{length:.0f} mm long"
    warn = "  ⚠️" if ra / AREA > 0.45 else ""
    print(f"  {tag:2} {name:6} {ra:9.0f} {100*ra/AREA:7.0f}%  {packed:>13}{warn}")
print(f"  {'':2} {'TOTAL':6} {total:9.0f} {100*total/(4*AREA):7.0f}%   across 4 boards\n")

print("HEIGHT  (BD-14 underside parts excluded from their layer's top side)")
z = FLOOR and 0.0
z = 3.0
print(f"  {z:5.1f}  standoff")
for i, (tag, name, parts) in enumerate(BOARDS):
    z += PCB
    th = top_height(tag, parts)
    tallest = max((p for p in parts if (tag, p[0]) not in UNDERSIDE), key=lambda p: p[5])
    print(f"  {z:5.1f}  {tag} {name} board top   ceiling {th:4.1f}  ({tallest[0]})")
    z += th + GAP
    if i == 1:
        z += PLATE + GAP
        print(f"  {z:5.1f}  alloy plate (BD-9)")
verdict = "✅ under" if z <= AVAIL_H else "⛔ OVER"
print(f"\n  {z:5.1f}  USED      {AVAIL_H:5.1f}  AVAILABLE      {verdict} by {abs(AVAIL_H-z):.1f} mm")
if z > AVAIL_H:
    print("\n  Levers, in the order §4 applies them:")
    print("    1. M19: confirm the CM choke height (assumed 18.0 here)")
    print("    2. BD-14: more parts to undersides")
    print("    3. BD-8: low-profile connectors on both logic layers")
    print("    4. BD-13 (the reserve): drop the isolated 5 V rail")
