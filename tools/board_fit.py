"""Area and height budget for the three-board stack, read off the netlist.

Nothing about the design is typed here. Parts and connectors -- board, side,
footprint, height, whether that height was ever confirmed -- come from
`netlist.current()`; the cavity and the stack parameters come from
`board_params`, which also DERIVES the stack height. This file only adds the
area arithmetic and says PASS or FAIL.

    python3 -m tools.board_fit          # exit 1: a budget fails · 2: over the ESTIMATED cavity height
    python3 tools/board-fit.py          # the same

Four budgets, four plain answers:

  DENSITY   raw body area against the usable area of that side of the board.
  PACK      a naive shelf-pack of the same bodies with a courtyard round each,
            against the board's length. ⚠️ A heuristic in both directions: it
            packs stupidly, and it knows nothing of mounting holes, standoff
            columns or creepage slots. When it fits, that is weak evidence.
            When it does NOT fit, this tool has not shown the board can be
            built, and says so -- the number is not explained away. What
            overrules it is a placed outline, not an argument.
  HEIGHT    `board_params.stack_height`, gap by gap, against the height there.
  ROWS      each FACE's harness headers end to end -- one row per face (IO-6),
            so a terminal under a board is not summed into the row on top of it
            -- against the length of the board they stand on. The room in front
            of them, `board_params.FACE_ROOM`, is not a budget here: it is a
            term of the cavity this design REQUIRES, which the report states.

⚠️ M18 is MEASURED (2026-09-20), so the cavity is a fact and every budget here
is a verdict. What is still an allowance is the ENCLOSURE -- wall, floor and lid
-- which the report says on its first line for as long as that is true. It makes
the requirement provisional, not the verdict: see `board_params.envelope_is_binding`.

The CAVITY the design requires is reported beside the budgets, and it answers to
the same gate the height does: a MEASURED cavity it exceeds is a failure --
`board_params.cavity_problems`, which `problems()` includes.
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


def shelf_pack(rects, board_w: float | None = None):
    """Naive first-fit shelf pack. -> (length used, blocker refdes).

    Every body is ORIENTED first -- long side across the board, unless it is
    longer than the board is wide and has to lie lengthwise -- then the pack is
    ordered by the shelf depth that orientation gives, deepest first, and each
    body goes on the first shelf with room across for it.

    ⚠️ Ordering by the depth the orientation gives is the point of the sort.
    Ordering on the body's short side, as this did until 2026-09-20, puts a body
    that must lie lengthwise in the MIDDLE of the order: it then opens the
    deepest shelf of the whole pack after the bodies that could have stood
    beside it have been placed elsewhere. That is one board-wide connector
    wasting a shelf the length of itself. POWER top's three biggest bodies are
    two 55.88 mm harness terminals (J101, J405) and J202, the 58.42 mm
    inter-board PWR-OUT connector; on the 39 mm board of 2026-09-20 the old
    order reported 321.57 mm where these same bodies pack into 214.85 mm, and
    on the 48 mm board before that, 254.93 against 195.45.
    """
    width = bp.BOARD_W if board_w is None else board_w
    placed = []
    for ref, w, l in rects:
        across, along = max(w, l) + 2 * COURTYARD, min(w, l) + 2 * COURTYARD
        if across > width:
            across, along = along, across
        if across > width:
            return None, ref
        placed.append((across, along))
    placed.sort(key=lambda r: -r[1])
    shelves: list[list[float]] = []            # [width used, depth]
    for across, along in placed:
        for shelf in shelves:
            if shelf[0] + across <= width + 1e-9:
                shelf[0] += across
                break
        else:
            shelves.append([across, along])
    return sum(shelf[1] for shelf in shelves), ""


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
    side: str                  # the FACE of that board: one row per face (IO-6)
    headers: tuple[str, ...]
    length_mm: float           # the harness headers end to end, HEADER_GAP apart
    room_mm: float             # deepest mated plug's overhang + the wire's bend

    @property
    def face(self) -> str:
        return f"{self.board} {self.side}"


def edge_budget(d: Design, order=bp.STACK_ORDER) -> tuple[Edge, ...]:
    """Every FACE with harness headers: the row they take and the room to
    the wall their plugs need. An unfitted header still takes its row.

    One row per FACE, not per board (IO-6). A terminal hanging UNDER a board
    is a row of its own, beside the row standing on top of the same board:
    summed together they would report an edge twice as long as either row is,
    and a board would fail a length no row of it needs."""
    out = []
    for board in order:
        for side in SIDES:
            hs = [c for c in d.connectors if c.board == board
                  and c.side == side and c.leaves_box]
            if not hs:
                continue
            length = sum(c.footprint_mm[0] for c in hs) + HEADER_GAP * (len(hs) - 1)
            room = max((c.overhang_mm for c in hs if not c.dnp),
                       default=0.0) + bp.WIRE_BEND
            out.append(Edge(board, side, tuple(c.refdes for c in hs), length, room))
    return tuple(out)


def face_verdicts(d: Design) -> list[str]:
    """Each board's harness headers are one row on the connector face (IO-6):
    the row must fit the board's length."""
    return [f"row: {e.board}'s {len(e.headers)} harness headers take "
            f"{e.length_mm:.0f} mm of the face; the board is {bp.BOARD_L:.0f} mm long"
            for e in edge_budget(d) if e.length_mm > bp.BOARD_L]


def unseen(d: Design, order=bp.STACK_ORDER) -> list[str]:
    """Bodies the area budget cannot see: no footprint, but not negligible."""
    out = [f"{c.refdes} ({c.name}) on {c.board}" for c in d.connectors
           if c.board in order and not (c.footprint_mm[0] > 0 and c.footprint_mm[1] > 0)]
    out += [f"{p.refdes} ({p.mpn}, {p.height_mm} mm tall) on {p.board}" for p in d.parts
            if p.board in order and not (p.footprint_mm[0] > 0 and p.footprint_mm[1] > 0)
            and not p.height_mm < NEGLIGIBLE_BELOW_MM]
    return out


def problems(d: Design) -> list[str]:
    """Every budget failure. Empty means all four close."""
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
    # The plan axes of the cavity, now that the cavity is a FACT. Gated inside
    # `cavity_problems` on the same `envelope_is_binding()` the height answers
    # to; M18 landed on 2026-09-20, so this is a live gate and not a paragraph
    # addressed to the future. Empty only if a cavity figure goes back to being
    # an estimate -- and the report still states the overrun even then.
    errs += bp.cavity_problems(d)
    # Not gated on `envelope_is_binding`: a row longer than the board it stands
    # on is a failure of the design against its OWN envelope (IO-14), and
    # nothing M18 can measure makes it not one.
    errs += face_verdicts(d)
    return errs


def report(d: Design) -> str:
    out = []
    # ⚠️ The two flags say different things and the first line must not blur
    # them. An unmeasured cavity makes the VERDICT provisional -- nothing can
    # fail against a guess. An undecided enclosure makes the REQUIREMENT
    # provisional, and nothing else: the verdict still binds, because the design
    # is judged against its own allowances (`board_params.envelope_is_binding`).
    if not bp.CAVITY_MEASURED:
        out.append("⚠️ THE HEIGHT VERDICT IS PROVISIONAL -- M18 NOT MEASURED: the "
                   "cavity is an estimate, so an overrun is reported and not "
                   "failed. Area, pack and rows are not: they are measured "
                   "against the envelope the design itself requires (IO-14).")
    elif not bp.ENCLOSURE_DECIDED:
        out.append("⚠️ THE REQUIREMENT IS NOT FINAL -- enclosure not chosen: wall, "
                   "floor and lid are allowances, so the cavity figures below "
                   "move when the box's model lands. Every VERDICT here binds "
                   "regardless: M18 is measured (IO-14).")
    req_l, req_w, req_h = bp.cavity_required(d)
    out.append(f"board {bp.BOARD_W:.0f} x {bp.BOARD_L:.0f} = {bp.BOARD_AREA:.0f} mm² "
               f"({MOUNT_AREA:.0f} mm² of it under the four M3 corners)   "
               f"height available {bp.AVAIL_H:.1f} mm")
    out.append(f"CAVITY REQUIRED (IO-14)   {req_l:.1f} along x {req_w:.2f} across x "
               f"{req_h:.1f} tall -- the board, {bp.WALL:g} mm of wall, "
               f"{bp.SIDE_CLEARANCE:g} mm to drop in past the far side, "
               f"{bp.FACE_ROOM:.2f} mm in front of the connector face, "
               f"{bp.END_ALLOWANCE:g} mm at each end, floor and lid.")
    # ⚠️ Both halves of this branch on the SAME flag. The overrun sentence used
    # to be unconditional under a first line that said "NOT MEASURED", so
    # flipping CAVITY_MEASURED changed nothing a reader could see and the day
    # M18 landed the report would have called a measured box an estimate.
    # ⛔ There used to be a third branch here -- measured, enclosure undecided,
    # "not yet a failure". It is gone, deliberately: a measured cavity the
    # design does not fit is a failure whatever the box's model has yet to say
    # (`board_params.envelope_is_binding` argues it). The lever the undecided
    # allowances still offer is named in the problem text, not in a reprieve.
    cavity = (f"{bp.CAVITY_L:.0f} x {bp.CAVITY_W:.0f} x {bp.CAVITY_H:.0f} mm")
    over = [f"{axis} by {need - have:.1f} mm"
            for axis, need, have in bp.cavity_overruns(d)]
    if not bp.CAVITY_MEASURED:
        head, tail = f"⬜ NOT MEASURED -- M18's estimate is {cavity}", (
            "That is a finding for M18, not a failure of the design.")
    else:
        plan_over = [a for a, *_ in bp.cavity_overruns(d) if a != "tall"]
        head, tail = f"✅ MEASURED (M18) -- the cavity is {cavity}", (
            "The design DOES NOT FIT the cavity that was measured, and that is "
            "a FAILURE: " + ("see the plan axes below." if plan_over else
                             "it is the stack's height, and HEIGHT below "
                             "fails on it."))
    out.append(head + (f"; the requirement EXCEEDS it {', '.join(over)}. {tail}\n"
                       if over else "; the requirement fits inside it.\n"))

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

    out.append(f"\nROWS   one row per FACE (IO-6): its harness headers end to end, "
               f"{HEADER_GAP:g} mm apart, along a {bp.BOARD_L:.0f} mm board. The face "
               f"needs {bp.FACE_ROOM:.2f} mm in front of it (the deepest mated plug, "
               f"then a {bp.WIRE_BEND:g} mm wire bend), which is in the cavity above.")
    for e in edge_budget(d):
        fits = ("fits" if e.length_mm <= bp.BOARD_L else
                f"⛔ DOES NOT FIT ({e.length_mm - bp.BOARD_L:.0f} mm over)")
        out.append(f"  {e.board:7} {e.side:6} {e.length_mm:6.1f} mm of row, "
                   f"{e.room_mm:5.2f} mm in front   {fits:12} {' '.join(e.headers)}")

    errs = problems(d)
    out.append("")
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
    elif stack.envelope_verdicts:
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
    # 2 = over the ESTIMATED cavity's height: not a failure yet, and never a
    # pass. The plan budgets no longer land here -- since IO-14 they are
    # measured against the design's own envelope, so they fail outright.
    return 2 if bp.stack_height(d).envelope_verdicts else 0


if __name__ == "__main__":
    sys.exit(main())
