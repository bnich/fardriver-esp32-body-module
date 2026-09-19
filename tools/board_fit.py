"""Area and height budget for the three-board stack, read off the netlist.

Nothing about the design is typed here. Parts and connectors -- board, side,
footprint, height, whether that height was ever confirmed -- come from
`netlist.current()`; the cavity and the stack parameters come from
`board_params`, which also DERIVES the stack height. This file only adds the
area arithmetic and says PASS or FAIL.

    python3 -m tools.board_fit          # exit 1: a budget fails · 2: over the ESTIMATED envelope
    python3 tools/board-fit.py          # the same

Three budgets, three plain answers:

  DENSITY   raw body area against the usable area of that side of the board.
  PACK      a naive shelf-pack of the same bodies with a courtyard round each,
            against the board's length. ⚠️ A heuristic in both directions: it
            packs stupidly, and it knows nothing of mounting holes, standoff
            columns or creepage slots. When it fits, that is weak evidence.
            When it does NOT fit, this tool has not shown the board can be
            built, and says so -- the number is not explained away. What
            overrules it is a placed outline, not an argument.
  HEIGHT    `board_params.stack_height`, gap by gap, against the height there.
  PLUGS     each board's harness headers end to end, against the edges of the
            envelope whose wall is far enough away for a mated plug and the
            bend of the wire leaving straight out of its back.

⚠️ Both are provisional until M18 is measured and the enclosure is chosen;
the report says so on its first line for as long as that is true.
"""
import sys
from dataclasses import dataclass

from . import board_params as bp
from .eprj3.pcb import M3_INSET_MM
from .model import Design

#: FAIL above this share of a side's usable area, bodies only. POWER's two faces
#: run about 0.45-0.55 -- both converter bricks underneath, the chokes and the
#: cans on top -- and placing that by hand already leaves little over; routing,
#: courtyards and creepage have to come out of what is left, so a side past 0.75
#: has no layout. A sparse logic board scores 0.2-0.4.
DENSITY_LIMIT = 0.75
#: Per side of every body in the pack: 1.0 mm body to body. IPC-7351's most
#: generous courtyard excess, and clear of the 0.6 mm IPC-2221 spacing BD-4
#: holds 84 V to.
COURTYARD = 0.5
#: Each M3 corner costs a square two insets on a side (pcb.py places the hole).
MOUNT_AREA = 4 * (2 * M3_INSET_MM) ** 2
#: A body this tall or taller with no footprint is a hole in the area budget,
#: not a negligible passive. Connectors always have a body.
NEGLIGIBLE_BELOW_MM = 2.0

SIDES = ("top", "bottom")
#: Between two harness headers on one edge: their flange screws and a finger.
HEADER_GAP = 1.0


@dataclass(frozen=True)
class Side:
    board: str
    side: str
    count: int                 # bodies with a footprint
    raw_mm2: float
    pack_mm: float | None      # None: some body fits the board in no orientation
    blocked_by: str = ""

    @property
    def density(self) -> float:
        return self.raw_mm2 / (bp.BOARD_AREA - MOUNT_AREA)

    @property
    def density_ok(self) -> bool:
        return self.density <= DENSITY_LIMIT

    @property
    def pack_ok(self) -> bool:
        return self.pack_mm is not None and self.pack_mm <= bp.BOARD_L


def bodies(d: Design, board: str, side: str):
    """[(refdes, w, l)] of everything with a footprint on that side."""
    out = [(p.refdes, *p.footprint_mm) for p in d.parts
           if p.board == board and p.side == side]
    out += [(c.refdes, *c.footprint_mm) for c in d.connectors
            if c.board == board and c.side == side]
    return [(r, w, l) for r, w, l in out if w > 0 and l > 0]


def shelf_pack(rects, board_w: float = bp.BOARD_W):
    """Greedy shelf pack, deepest shelf first. -> (length used, blocker refdes)."""
    grown = sorted(((max(w, l) + 2 * COURTYARD, min(w, l) + 2 * COURTYARD, ref)
                    for ref, w, l in rects), key=lambda r: -r[1])
    x = y = shelf = 0.0
    for across, along, ref in grown:
        if across > board_w:
            across, along = along, across
        if across > board_w:
            return None, ref
        if x + across > board_w:
            y, x, shelf = y + shelf, 0.0, 0.0
        x += across
        shelf = max(shelf, along)
    return y + shelf, ""


def area_budget(d: Design, order=bp.STACK_ORDER) -> tuple[Side, ...]:
    rows = []
    for board in order:
        for side in SIDES:
            rects = bodies(d, board, side)
            if side == "bottom" and not rects:
                continue
            length, blocker = shelf_pack(rects)
            rows.append(Side(board, side, len(rects),
                             sum(w * l for _, w, l in rects), length, blocker))
    return tuple(rows)


@dataclass(frozen=True)
class Edge:
    board: str
    headers: tuple[str, ...]
    length_mm: float           # the harness headers end to end, HEADER_GAP apart
    room_mm: float             # deepest mated plug's overhang + the wire's bend


def edge_budget(d: Design, order=bp.STACK_ORDER) -> tuple[Edge, ...]:
    """Every board with harness headers: the edge they take and the room to
    the wall their plugs need. An unfitted header still takes its edge."""
    out = []
    for board in order:
        hs = [c for c in d.connectors if c.board == board and c.leaves_box]
        if not hs:
            continue
        length = sum(c.footprint_mm[0] for c in hs) + HEADER_GAP * (len(hs) - 1)
        room = max((c.overhang_mm for c in hs if not c.dnp), default=0.0) + bp.WIRE_BEND
        out.append(Edge(board, tuple(c.refdes for c in hs), length, room))
    return tuple(out)


def edge_verdicts(d: Design) -> list[str]:
    """A board whose plugs no wall of the envelope has room for. The walls'
    allowances are provisional (M18, the enclosure), so this is a verdict
    against an estimate until `envelope_is_binding()`."""
    out = []
    for e in edge_budget(d):
        ends = 2 * bp.BOARD_W if bp.END_ALLOWANCE >= e.room_mm else 0.0
        sides = 2 * bp.BOARD_L if bp.SIDE_CLEARANCE >= e.room_mm else 0.0
        if e.length_mm <= ends + sides:
            continue
        out.append(
            f"plugs: {e.board}'s {len(e.headers)} harness headers take "
            f"{e.length_mm:.0f} mm of edge and need {e.room_mm:.1f} mm to the wall "
            f"(the mated plug, then the wire's bend); the envelope leaves "
            f"{bp.END_ALLOWANCE:g} mm at each end ({2 * bp.BOARD_W:.0f} mm of edge) "
            f"and {bp.SIDE_CLEARANCE:g} mm at each side ({2 * bp.BOARD_L:.0f} mm)")
    return out


def unseen(d: Design, order=bp.STACK_ORDER) -> list[str]:
    """Bodies the area budget cannot see: no footprint, but not negligible."""
    out = [f"{c.refdes} ({c.name}) on {c.board}" for c in d.connectors
           if c.board in order and not (c.footprint_mm[0] > 0 and c.footprint_mm[1] > 0)]
    out += [f"{p.refdes} ({p.mpn}, {p.height_mm} mm tall) on {p.board}" for p in d.parts
            if p.board in order and not (p.footprint_mm[0] > 0 and p.footprint_mm[1] > 0)
            and not p.height_mm < NEGLIGIBLE_BELOW_MM]
    return out


def problems(d: Design) -> list[str]:
    """Every budget failure. Empty means all three close."""
    errs = []
    for s in area_budget(d):
        where = f"{s.board} {s.side}"
        if not s.density_ok:
            errs.append(f"density: {where} is {s.density:.0%} bodies, limit "
                        f"{DENSITY_LIMIT:.0%} -- no room left to lay it out")
        if s.pack_mm is None:
            errs.append(f"pack: {where}: {s.blocked_by} fits a {bp.BOARD_W:.0f} mm "
                        f"board in neither orientation")
        elif not s.pack_ok:
            errs.append(f"pack: {where} DOES NOT FIT -- the naive pack needs "
                        f"{s.pack_mm:.0f} mm of a {bp.BOARD_L:.0f} mm board, "
                        f"{s.pack_mm - bp.BOARD_L:.0f} mm over. Not shown to be "
                        f"buildable; only a placed outline can overrule this")
    errs += [f"area: {what} has no footprint -- the area budget cannot see it"
             for what in unseen(d)]
    errs += bp.stack_height(d).problems
    if bp.envelope_is_binding():
        errs += edge_verdicts(d)
    return errs


def report(d: Design) -> str:
    out = []
    caveats = [] if bp.CAVITY_MEASURED else ["M18 NOT MEASURED: the cavity is an estimate"]
    if not bp.ENCLOSURE_DECIDED:
        caveats.append("enclosure not chosen: wall, floor and lid are allowances")
    if caveats:
        out.append("⚠️ PROVISIONAL -- " + "; ".join(caveats) + ".")
    out.append(f"cavity {bp.CAVITY_L:.0f} x {bp.CAVITY_W:.0f} x {bp.CAVITY_H:.0f} mm   "
               f"board {bp.BOARD_W:.0f} x {bp.BOARD_L:.0f} = {bp.BOARD_AREA:.0f} mm² "
               f"({MOUNT_AREA:.0f} mm² of it under the four M3 corners)   "
               f"height {bp.AVAIL_H:.1f} mm\n")

    out.append(f"AREA   density = bodies / usable side, FAIL above {DENSITY_LIMIT:.0%}.   "
               f"pack = naive shelf-pack, {COURTYARD} mm courtyard, FAIL when longer "
               f"than the board.")
    out.append(f"  {'board':6} {'side':6} {'bodies':>6} {'raw mm²':>8} {'density':>8}      "
               f"{'pack':>7}  of {bp.BOARD_L:.0f} mm")
    for s in area_budget(d):
        dens = "ok" if s.density_ok else "⛔ FAIL"
        if s.pack_mm is None:
            pack = f"   ⛔ {s.blocked_by} fits in neither orientation"
        else:
            pack = f"{s.pack_mm:5.0f} mm  " + (
                "fits" if s.pack_ok else
                f"⛔ DOES NOT FIT ({s.pack_mm - bp.BOARD_L:.0f} mm over)")
        out.append(f"  {s.board:6} {s.side:6} {s.count:6d} {s.raw_mm2:8.0f} "
                   f"{s.density:7.0%} {dens:4} {pack}")
    small = sum(1 for p in d.parts if p.footprint_mm[0] <= 0 or p.footprint_mm[1] <= 0)
    if small:
        out.append(f"  {small} part(s) carry no footprint and are not in the area figures.")

    stack = bp.stack_height(d)
    seated = next((g for g in stack.gaps
                   if g.below == bp.FLOOR_NAME and g.seat_mm), None)
    head = (f"\nHEIGHT   derived: PCB {bp.PCB_T}, clearance {bp.CLEARANCE}, "
            f"solder tails {bp.TAIL}, ")
    out.append(head + (
        f"{seated.seat_ref} bolted to the floor on a {bp.THERMAL_PAD_T} mm pad "
        f"(liner {bp.FLOOR_LINER_T} elsewhere)" if seated else
        f"floor liner {bp.FLOOR_LINER_T}, nothing on the floor seat"))
    z = 0.0
    for g in stack.gaps:
        why = [f"{g.top_ref} {g.top_mm:.1f} up" if g.top_mm else "",
               f"{g.hang_ref} {g.hang_mm:.1f} down" if g.hang_mm else "",
               (f"{g.seat_ref} seats on the floor at {g.seat_mm:.1f}"
                + (", which sets it" if g.seat_sets_gap else "")) if g.seat_mm else "",
               *(f"{pr.refs} mates at {pr.mated_mm:.1f}"
                 + ("" if pr.confirmed else " (unconfirmed)") for pr in g.pairs)]
        out.append(f"  {z:6.1f}  gap {g.below:>5} -> {g.above:<5} {g.gap_mm:5.1f}   "
                   + ", ".join(w for w in why if w))
        z += g.gap_mm
        if g.above in bp.STACK_ORDER:
            z += bp.PCB_T
    verdict = "under" if stack.margin_mm >= 0 else "⛔ OVER"
    out.append(f"  {stack.total_mm:6.1f}  USED of {stack.avail_mm:.1f} mm -- "
               f"{verdict} by {abs(stack.margin_mm):.1f} mm")
    for n in stack.notes:
        out.append(f"  ⚠️ {n}")

    if stack.unconfirmed:
        out.append(f"\nUNCONFIRMED HEIGHTS   {len(stack.unconfirmed)} not read off a "
                   f"manufacturer's drawing -- every one is below.   "
                   f"⭐ = a gap above rests on it")
        groups: dict[tuple, list[str]] = {}
        for ref, board, what, h in stack.unconfirmed:
            key = (ref in stack.load_bearing, board, h, what[:48],
                   ref if ref in stack.load_bearing else "")
            groups.setdefault(key, []).append(ref)
        for (starred, board, h, what, _), refs in sorted(
                groups.items(), key=lambda kv: (not kv[0][0],
                                                bp.STACK_ORDER.index(kv[0][1]),
                                                -kv[0][2], kv[1][0])):
            out.append(f"  {'⭐' if starred else '  '} {board:6} {h:5.1f} mm  "
                       f"{what}: {' '.join(refs)}")

    out.append(f"\nPLUGS   harness headers end to end, {HEADER_GAP:g} mm apart; room = "
               f"the deepest mated plug + a {bp.WIRE_BEND:g} mm wire bend")
    for e in edge_budget(d):
        out.append(f"  {e.board:6} {e.length_mm:5.0f} mm of edge, {e.room_mm:4.1f} mm to "
                   f"the wall   {' '.join(e.headers)}")
    edges = [] if bp.envelope_is_binding() else edge_verdicts(d)

    errs = problems(d)
    out.append("")
    for verdict in edges:
        out.append(f"⚠️  PROVISIONAL -- {verdict}. Binding the moment M18 and the "
                   f"enclosure are settled")
    for verdict in stack.envelope_verdicts:
        out.append(f"⚠️  PROVISIONAL -- {verdict}")
        if stack.total_mm > bp.CAVITY_H:
            out.append(
                f"    ⛔ {stack.total_mm:.1f} mm exceeds even the RAW cavity estimate "
                f"({bp.CAVITY_H:.0f} mm) -- no choice of enclosure can absorb it. "
                f"Only a taller measured cavity (M18) or a shorter stack can.")
    if errs:
        out.append(f"⛔ FAIL -- {len(errs)} problem(s)")
        out += [f"  - {e}" for e in errs]
    elif stack.envelope_verdicts or edges:
        out.append("⚠️  NOT A PASS -- the design overruns the ESTIMATED envelope. It is "
                   "not a failure only because the envelope is not yet a fact.")
    else:
        out.append("✅ PASS" + (f" -- provisional: {len(stack.load_bearing)} unconfirmed "
                                f"height(s) set gaps" if stack.load_bearing else ""))
    return "\n".join(out)


def main(argv=None, d: Design | None = None) -> int:
    if d is None:
        from . import netlist
        d = netlist.current()
    print(report(d))
    if problems(d):
        return 1
    # 2 = over the ESTIMATED envelope: not a failure yet, and never a pass.
    return 2 if bp.stack_height(d).envelope_verdicts or edge_verdicts(d) else 0


if __name__ == "__main__":
    sys.exit(main())
