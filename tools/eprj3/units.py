"""mm <-> EasyEDA Pro native units.

⛔ SCHEMATIC AND PCB DOCUMENTS USE DIFFERENT UNITS, TEN TIMES APART.
That is not a typo in this file; it is a property of the format, and it is the
single easiest way to produce a project that opens cleanly and is silently
wrong by 10x.

  SCHEMATIC   1 unit = 0.01 inch = 0.254 mm
              Proven from the official example: pin rows sit 10 units apart
              (y = -45, -35, -25, -15) and schematic pin pitch is 0.1 inch.
              This matches `fmt2 general/conventions.md`.

  PCB         1 unit = 1 mil = 0.0254 mm
              Proven from the official example's board outline,
              ["R",0,940,1475,940,0,0] -> 1475 x 940 units:
                  at 1 mil    37.5 x 23.9 mm   <- a normal small PCB
                  at 0.01 in  374.7 x 238.8 mm <- larger than A4
              ⚠️ `conventions.md` says 0.01 inch for everything. For PCB
              documents it is wrong. The file wins over the prose.

There is deliberately NO unit-agnostic `mm_to_units()`. A caller that has not
decided which document it is emitting has not finished thinking, and a wrong
guess here is invisible: the board simply comes out the wrong size.

Geometry is carried in millimetres as float everywhere else in this project
and converted exactly once, here, at emit time.
"""

SCH_MM_PER_UNIT = 0.254     # 0.01 inch
PCB_MM_PER_UNIT = 0.0254    # 1 mil


def mm_to_sch(mm: float) -> float:
    """Millimetres -> schematic units (0.01 inch). No rounding."""
    return mm / SCH_MM_PER_UNIT


def sch_to_mm(units: float) -> float:
    return units * SCH_MM_PER_UNIT


def mm_to_pcb(mm: float) -> float:
    """Millimetres -> PCB units (mil). No rounding."""
    return mm / PCB_MM_PER_UNIT


def pcb_to_mm(units: float) -> float:
    return units * PCB_MM_PER_UNIT
