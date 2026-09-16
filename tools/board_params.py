"""Physical envelope for the four-board stack -- THE single home for it.

`board-fit.py` and the PCB outline emitter both import from here, so the
geometry cannot drift between the budget that proves it fits and the outline
that gets manufactured.

⚠️ M18 IS NOT MEASURED.  The cavity below is the owner's estimate of
2026-09-15, offered from a menu.  Width is the sensitive axis: roughly 25-30 mm
of usable board length per 10 mm of width gained.  When M18 lands, edit the
cavity block, flip CAVITY_MEASURED, and re-run tools/board-fit.py.

📄 docs/board-design-record.md sections 0 and 4.
"""

# --- M18: the cavity -------------------------------------------------------
CAVITY_L = 200.0   # mm, along the bike
CAVITY_W = 50.0    # mm, across -- ⚠️ the sensitive axis
CAVITY_H = 70.0    # mm, floor to the underside of the battery tray
CAVITY_MEASURED = False   # ⛔ still an estimate; flip when M18 lands

# --- enclosure -------------------------------------------------------------
WALL = 3.0     # printed ASA; thinner wicks water along the layer lines
FLOOR = 3.0
LID = 3.0

# --- derived board envelope ------------------------------------------------
# 1 mm of clearance per side for the board itself, 4 mm per end for glands
# and the connector shells that face the walls (BD-8).
BOARD_W = CAVITY_W - 2 * WALL - 2.0     # 42.0 mm
BOARD_L = CAVITY_L - 2 * WALL - 8.0     # 186.0 mm
BOARD_AREA = BOARD_W * BOARD_L

AVAIL_H = CAVITY_H - FLOOR - LID        # 64.0 mm of internal stack

# --- stack ------------------------------------------------------------------
PCB_T = 1.6
GAP = 1.0      # clearance from a layer's tallest part to the next board
PLATE_T = 3.0  # BD-9: alloy heatspreader / EMC barrier between CONV and DRV

#: Bottom to top.  BD-2: voltage decreases with height, 84 V at the floor.
STACK_ORDER = ("HVIN", "CONV", "DRV", "BRAIN")

#: What each layer's tallest part may be, above its own board.
#: These are design RULES, not outcomes -- one tall substitution breaks the
#: enclosure, so tools/rules.py asserts them.
LAYER_CEILING_MM = {
    "HVIN": 18.0,   # IXTP26P20P TO-220 upright floors this at 16.0
    "CONV": 14.0,   # the Y2 discs, which must sit AT the converter terminals
                    # (plan 9.5.2) and are 1.3 mm taller than the 12.7 mm
                    # brick -- so BD-9's plate clears them and the brick takes
                    # a 1.3 mm alloy spacer up to it. Electrolytics go
                    # UNDERSIDE (BD-14) and do not count here.
    "DRV": 6.0,     # right-angle low-profile connectors
    "BRAIN": 6.0,   # right-angle low-profile connectors
}
