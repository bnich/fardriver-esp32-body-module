"""Physical envelope for the three-board stack -- THE single home for it.

Two kinds of thing live here and they are kept apart on purpose:

  PARAMETERS  the cavity, the enclosure allowances, PCB thickness, clearances.
              Typed here, once. The PCB outline emitter and `board_fit` both
              import them, so the outline that is manufactured cannot drift
              from the budget that says it fits.

  GEOMETRY    how tall the stack is. ⛔ Never typed. `layer_gaps(design)` and
              `stack_height(design)` DERIVE it from the netlist's own parts and
              connectors, so a height changed in the netlist moves the stack
              the same day, and a ceiling nobody re-derived cannot exist.

⚠️ BOTH BUDGETS ARE PROVISIONAL, twice over:
  * M18 is not measured. The cavity is the owner's estimate. Width is the
    sensitive axis: roughly 25-30 mm of usable board length per 10 mm of width.
  * The enclosure is an all-metal CNC box, but its model does not exist yet:
    wall, floor and lid are ALLOWANCES that the model's thicknesses replace.
When either lands: edit the block, flip the flag, run `python3 -m tools.board_fit`.
"""
import math
import re
from dataclasses import dataclass

from .model import Connector, Design, Part

# --- M18: the cavity -------------------------------------------------------
CAVITY_L = 200.0   # mm, along the bike
CAVITY_W = 50.0    # mm, across -- ⚠️ the sensitive axis
CAVITY_H = 70.0    # mm, floor to the underside of the battery tray
CAVITY_MEASURED = False   # ⛔ still an estimate; flip when M18 lands

# --- enclosure: PROVISIONAL allowances -------------------------------------
# What the enclosure takes out of the cavity on each face. The enclosure is an
# all-metal CNC box (owner, 2026-09-18); these are allowances until its model
# sets the real wall, floor and lid thicknesses. Every figure derived below
# inherits them, which is why both budgets report themselves as provisional.
# ENCLOSURE_DECIDED means "the model has set these", not "the material is known".
ENCLOSURE_DECIDED = False
WALL = 3.0
FLOOR = 3.0
LID = 3.0

# --- derived board envelope ------------------------------------------------
SIDE_CLEARANCE = 1.0   # per side: the board must drop in past the walls
END_ALLOWANCE = 4.0    # per end: glands and the connector shells facing them
BOARD_W = CAVITY_W - 2 * WALL - 2 * SIDE_CLEARANCE
BOARD_L = CAVITY_L - 2 * WALL - 2 * END_ALLOWANCE
BOARD_AREA = BOARD_W * BOARD_L

AVAIL_H = CAVITY_H - FLOOR - LID        # internal height the stack may use

# --- stack parameters --------------------------------------------------------
#: Bottom to top.  BD-2: voltage decreases with height, 84 V at the floor.
STACK_ORDER = ("POWER", "OUTPUTS", "LOGIC")

PCB_T = 1.6
#: Air between the tallest thing in a gap and whatever faces it, so that
#: tolerance and vibration never make them touch. ⚠️ Mechanical only -- it is
#: not a creepage or insulation figure.
CLEARANCE = 1.0
#: How far a TRIMMED through-hole lead stands out of the far side of its board
#: (IPC-A-610 allows 1.5 mm): the default for a part with long leads, which
#: the build trims. A part whose pins are too short or stiff to trim states
#: its drawing's `lead_mm`, and its tail is that less the PCB. Left out, tails
#: touch the floor liner or the part below.
TAIL = 1.5
#: Least space under the bottom board. The derivation never goes below
#: liner + tails + clearance; this is the enclosure's boss height. PROVISIONAL.
FLOOR_STANDOFF_MIN = 3.0
#: An insulating sheet on the metal floor under POWER, whose underside carries
#: 84 V copper -- both converters' input pins, and the trimmed tails of J101 and
#: the chokes. The box is bonded to ground, so without it one bent tail, a stray
#: strand or a flexed board is a pack short. A 0.43 mm polypropylene sheet
#: (Formex GK-17 class) is the kind meant. ⚠️ It is CUT AWAY under `FLOOR_SEAT`,
#: where the baseplate has to reach the floor. PROVISIONAL: chosen with the
#: enclosure.
FLOOR_LINER_T = 0.5
#: The part that seats the bottom board on the floor: the 12 V brick is
#: conduction-cooled, and its baseplate bolts to the box floor through a thermal
#: pad, which is the heatsink (owner, 2026-09-19 -- there is no alloy plate in
#: the stack). Its seat sets how high the bottom board sits, so nothing else on
#: that face may hang deeper than it does; `stack_height` fails the design when
#: something does.
FLOOR_SEAT = "U201"
#: Thermal interface material between that baseplate and the floor. PROVISIONAL:
#: chosen with the enclosure.
THERMAL_PAD_T = 0.5

# --- harness plugs at the walls (MX-3) ---------------------------------------
#: A harness wire leaves straight out of the back of its screw plug and has to
#: turn along the wall. ~3x the OD of a 1.5 mm² wire; tighter fatigues the
#: conductor where the plug clamps it. PROVISIONAL, with the cable exit (M18).
WIRE_BEND = 10.0

FLOOR_NAME, LID_NAME = "FLOOR", "LID"

#: Packages whose leads pass through the board. A connector is always taken
#: as through-hole: the conservative reading, and the usual one here.
_THROUGH_HOLE = re.compile(
    r"(?i)(\bTHT\b|\bTH\b|through|\bDIP\b|DIP-|TO-220|TO-247|TO-92|DO-41|DO-15|"
    r"DO-201|radial|axial|\bdisc\b|brick)")


def is_through_hole(package: str) -> bool:
    return bool(_THROUGH_HOLE.search(package))


def tail_mm(x) -> float:
    """How far a through-hole item's leads stand out of the far side of its
    board: its drawing's pins less the PCB, or TAIL where the build trims them.
    A connector is always through-hole."""
    if isinstance(x, Part) and not is_through_hole(x.package):
        return 0.0
    lead = getattr(x, "lead_mm", None)
    return TAIL if lead is None else max(0.0, lead - PCB_T)


def _tails(d: Design, board: str, side: str) -> tuple[float, str]:
    """(mm, what) of the longest tails pointing out of `board`'s other face
    from items mounted on `side`."""
    items = [x for x in (*d.parts, *d.connectors)
             if x.board == board and getattr(x, "side", "top") == side]
    best = max(((tail_mm(x), x) for x in items), default=(0.0, None),
               key=lambda t: t[0])
    mm, x = best
    if not mm:
        return 0.0, "-"
    return mm, ("solder tails" if getattr(x, "lead_mm", None) is None
                else f"{x.refdes} pins")


@dataclass(frozen=True)
class Pair:
    """The two halves of one inter-board connector, across one gap."""
    lower: str
    upper: str
    mated_mm: float            # body on body: the board spacing this pair gives
    confirmed: bool            # BOTH heights read off a drawing: the part is chosen

    @property
    def refs(self) -> str:
        return f"{self.lower}+{self.upper}"


@dataclass(frozen=True)
class Gap:
    """The space between two decks of the stack, and why it is that big."""
    below: str                 # a board, or FLOOR
    above: str                 # a board, or LID
    top_mm: float              # tallest thing standing on `below`
    top_ref: str
    #: Deepest thing under `above`: a part, or solder tails. On the FLOOR gap
    #: the floor seat is left out of it and counted in `seat_mm` instead, so the
    #: two terms of that gap can be read apart.
    hang_mm: float
    hang_ref: str
    #: FLOOR gap only: the thermal pad plus `FLOOR_SEAT`'s own height, which is
    #: how high its baseplate holds the board off the floor. 0 in every other
    #: gap, and 0 when the seat part is not mounted on that face.
    seat_mm: float
    seat_ref: str
    need_mm: float             # what the parts require
    pairs: tuple[Pair, ...]    # inter-board connectors crossing this gap
    gap_mm: float              # the spacing the stack is built with

    @property
    def seat_sets_gap(self) -> bool:
        """The floor seat, not the parts that hang beside it, sets this gap."""
        return bool(self.seat_mm) and self.seat_mm >= self.need_mm - 1e-9

    @property
    def chosen(self) -> tuple[Pair, ...]:
        return tuple(p for p in self.pairs if p.confirmed)

    @property
    def mated_mm(self) -> float:
        """Spacing the connectors give: the chosen pair's, else the tallest. 0 = none."""
        return max((p.mated_mm for p in self.chosen or self.pairs), default=0.0)

    @property
    def mated_refs(self) -> tuple[str, ...]:
        return tuple(r for p in self.chosen or self.pairs for r in (p.lower, p.upper))

    @property
    def mated_confirmed(self) -> bool:
        return bool(self.chosen)

    @property
    def set_by(self) -> tuple[str, ...]:
        """Refdes whose heights this gap's size actually rests on."""
        pairs = self.chosen or tuple(
            p for p in self.pairs if p.mated_mm >= self.gap_mm - 1e-9)
        refs = [r for p in pairs for r in (p.lower, p.upper)]
        if not self.chosen and self.need_mm >= self.gap_mm - 1e-9:
            refs += [self.top_ref, self.hang_ref]
            if self.seat_sets_gap:
                refs.append(self.seat_ref)
        return tuple(refs)


@dataclass(frozen=True)
class Stack:
    gaps: tuple[Gap, ...]
    total_mm: float
    avail_mm: float
    #: Anything that makes the answer NO, or makes it impossible to give.
    problems: tuple[str, ...]
    #: Placement constraints and connector choices the numbers imply.
    notes: tuple[str, ...]
    #: (refdes, board, what, height) for every height nobody has read off a
    #: drawing. `load_bearing` is the subset that sets a gap.
    unconfirmed: tuple[tuple[str, str, str, float], ...]
    load_bearing: tuple[str, ...]
    #: The stack-versus-envelope verdict while the envelope itself is not a
    #: fact (cavity unmeasured or enclosure undecided). Reported loudly, never
    #: silently -- but it cannot FAIL a design against a number nobody has
    #: measured. The moment both flags are true it lands in `problems` instead.
    envelope_verdicts: tuple[str, ...] = ()

    @property
    def margin_mm(self) -> float:
        return self.avail_mm - self.total_mm

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def provisional(self) -> bool:
        return bool(self.load_bearing) or not CAVITY_MEASURED or not ENCLOSURE_DECIDED


def _bad_height(h) -> bool:
    return h is None or isinstance(h, bool) or math.isnan(h) or h < 0.0


def _tallest(items):
    """(height, refdes) of the tallest of [(height, refdes)], or (0, '-')."""
    return max(items, default=(0.0, "-"))


def _halves(d: Design, board: str) -> dict:
    found = {}
    for c in d.connectors:
        if c.interface and c.board == board:
            found.setdefault(c.interface, c)
    return found


def _pairs(d: Design, below: str, above: str, order=STACK_ORDER):
    """Inter-board connector pairs bridging two adjacent boards, one per interface.

    A connector has one body. On the middle board of a three-board bus that
    body stands on top and mates UPWARD; how the bus gets down to the board
    beneath is a second part the design has to carry, so no pair is invented
    for that crossing (`_through` reports it).
    """
    lower, upper = _halves(d, below), _halves(d, above)
    return [(lower[i], upper[i]) for i in sorted(lower.keys() & upper.keys())
            if upper[i].refdes not in {c.refdes for c in _through(d, order)}]


def _through(d: Design, order=STACK_ORDER):
    """Connectors that sit between two other halves of their own interface."""
    out = []
    for lo, mid, up in zip(order, order[1:], order[2:]):
        a, b, c = _halves(d, lo), _halves(d, mid), _halves(d, up)
        out += [b[i] for i in sorted(a.keys() & b.keys() & c.keys())]
    return out


def layer_gaps(d: Design, order=STACK_ORDER) -> tuple[Gap, ...]:
    """Every gap of the stack, bottom to top: FLOOR->first board ... last board->LID.

    For the gap between a lower deck and an upper one:

      need  = the larger of
                tallest top-side thing below + CLEARANCE + solder tails above
                deepest bottom-side part above + CLEARANCE

              On the FLOOR gap it is instead the larger of
                THERMAL_PAD_T + FLOOR_SEAT's height  (the baseplate on the floor)
                FLOOR_LINER_T + the deepest OTHER underside item + CLEARANCE
              never below FLOOR_STANDOFF_MIN. `seat_sets_gap` says which won.

      mated = the two halves of an inter-board connector, body on body
              (`height_mm` of the lower half + `height_mm` of the upper). That
              IS the board spacing once the connector is chosen.

      gap   = mated, when both halves' heights are confirmed (the connector is
              chosen and it sets the spacing -- `stack_height` fails the design
              if the parts need more); otherwise the larger of need and the
              tallest pair, because the boards cannot sit closer than the
              tallest connector specified between them.

    A bottom-side part and a tall part beneath it share a gap by standing
    side by side (BD-14): one deliberate placement, and `stack_height` states
    the keep-out it costs. Solder tails get no such credit -- they are
    wherever a through-hole part is -- so they ADD to what stands below.

    A DNP part counts: its footprint can be populated, so its part must fit.
    """
    decks = (FLOOR_NAME,) + tuple(order) + (LID_NAME,)
    paired = {c.refdes for lo, up in zip(order, order[1:])
              for pair in _pairs(d, lo, up, order) for c in pair}
    gaps = []
    for below, above in zip(decks, decks[1:]):
        tops = [(p.height_mm, p.refdes) for p in d.parts
                if p.board == below and p.side == "top" and not _bad_height(p.height_mm)]
        tops += [(c.height_mm, c.refdes) for c in d.connectors
                 if c.board == below and c.side == "top" and c.refdes not in paired
                 and not _bad_height(c.height_mm)]
        if below in order:                   # pins of parts mounted underneath
            up_tails, up_ref = _tails(d, below, "bottom")
            if up_tails:
                tops.append((up_tails, up_ref))
        top_mm, top_ref = _tallest(tops)

        hangs = [(p.height_mm, p.refdes) for p in d.parts
                 if p.board == above and p.side == "bottom"
                 and not _bad_height(p.height_mm)]
        hangs += [(c.height_mm, c.refdes) for c in d.connectors
                  if c.board == above and c.side == "bottom" and c.refdes not in paired
                  and not _bad_height(c.height_mm)]
        tails, tails_ref = _tails(d, above, "top") if above in order else (0.0, "-")
        part_mm, part_ref = _tallest(hangs)
        hang_mm, hang_ref = (part_mm, part_ref) if part_mm >= tails else (tails, tails_ref)
        if hang_mm == 0.0:
            hang_ref = "-"

        seat_mm, seat_ref = 0.0, "-"
        if below == FLOOR_NAME:
            # The seat bolts to the floor; everything else on that face clears
            # the liner. They are separate terms, and the taller one wins.
            seat_h = [h for h, r in hangs if r == FLOOR_SEAT]
            if seat_h:
                seat_mm, seat_ref = THERMAL_PAD_T + max(seat_h), FLOOR_SEAT
                beside = [(h, r) for h, r in hangs if r != FLOOR_SEAT]
                if tails:
                    beside.append((tails, tails_ref))
                hang_mm, hang_ref = _tallest(beside)
                if hang_mm == 0.0:
                    hang_ref = "-"
            need = max(FLOOR_STANDOFF_MIN, seat_mm,
                       FLOOR_LINER_T + hang_mm + CLEARANCE)
        elif above == LID_NAME:
            need = top_mm + CLEARANCE
        else:
            need = max(top_mm + CLEARANCE + tails, part_mm + CLEARANCE)

        pairs = tuple(
            Pair(lo.refdes, up.refdes, lo.height_mm + up.height_mm,
                 lo.height_confirmed and up.height_confirmed)
            for lo, up in (_pairs(d, below, above, order)
                           if below in order and above in order else [])
            if not _bad_height(lo.height_mm) and not _bad_height(up.height_mm))
        chosen = [p.mated_mm for p in pairs if p.confirmed]
        gap_mm = max(chosen) if chosen else max(
            [need] + [p.mated_mm for p in pairs])
        gaps.append(Gap(below, above, top_mm, top_ref, hang_mm, hang_ref,
                        seat_mm, seat_ref, need, pairs, gap_mm))
    return tuple(gaps)


def unconfirmed_heights(d: Design, order=STACK_ORDER):
    """(refdes, board, what, height) for every height not read off a drawing."""
    rows = [(p.refdes, p.board, p.mpn, p.height_mm)
            for p in d.parts if p.board in order and not p.height_confirmed]
    rows += [(c.refdes, c.board, c.name, c.height_mm)
             for c in d.connectors if c.board in order and not c.height_confirmed]
    return tuple(sorted(rows, key=lambda r: (order.index(r[1]), r[0])))


def stack_height(d: Design, order=STACK_ORDER, avail_mm: float = AVAIL_H) -> Stack:
    """The derived stack against the height available. See `layer_gaps`."""
    problems, notes = [], []
    items: list[Part | Connector] = [*d.parts, *d.connectors]
    for x in items:
        if x.board in order and _bad_height(x.height_mm):
            problems.append(
                f"height: {x.refdes} on {x.board} has no usable height "
                f"({x.height_mm!r}) -- the stack cannot be derived around a part "
                f"of unknown size, so this is a failure, not a pass")

    gaps = layer_gaps(d, order)
    by_ref = {x.refdes: x for x in items}
    for c in _through(d, order):
        notes.append(
            f"{c.refdes} ({c.interface}) is the middle of a three-board bus: its one "
            f"body is counted standing on {c.board}, mating upward. What carries "
            f"{c.interface} down to the board beneath {c.board} is not in the "
            f"netlist, so that crossing has no mated height here")
    for g in gaps:
        where = f"{g.below}->{g.above}"
        if g.chosen and g.need_mm > g.gap_mm + 1e-9:
            culprit = (f"{g.hang_ref} hangs {g.hang_mm:.1f} mm under {g.above}"
                       if g.hang_mm + CLEARANCE > g.gap_mm else
                       f"{g.top_ref} stands {g.top_mm:.1f} mm on {g.below}")
            problems.append(
                f"gap {where}: the parts need {g.need_mm:.1f} mm but the chosen "
                f"connector pair {g.chosen[0].refs} sets the boards "
                f"{g.gap_mm:.1f} mm apart -- {culprit}")
        for pair in g.pairs:
            if abs(pair.mated_mm - g.gap_mm) <= 0.1:
                continue
            if pair.confirmed:
                problems.append(
                    f"gap {where}: the chosen pair {pair.refs} mates at "
                    f"{pair.mated_mm:.1f} mm but the gap is {g.gap_mm:.1f} mm -- "
                    f"one gap cannot be two heights")
            else:
                notes.append(
                    f"gap {where}: {pair.refs} mates at {pair.mated_mm:.1f} mm "
                    f"(unconfirmed) and the gap is {g.gap_mm:.1f} mm -- the pair has "
                    f"to be a type that mates at the gap, and once it is chosen its "
                    f"drawing sets the gap")
        # The baseplate reaches the floor only while nothing beside it hangs
        # deeper. Anything that does lifts the brick off its heatsink, so the
        # gap silently growing to fit it is exactly the failure to catch.
        seat = by_ref.get(FLOOR_SEAT)
        if g.seat_mm and seat is not None and not _bad_height(seat.height_mm):
            # Parts AND the tails of what is soldered on top: both stand on the
            # liner, and either one deeper than the seat lifts the baseplate.
            beside = [(x.height_mm, x.refdes) for x in items
                      if x.board == g.above and x.refdes != FLOOR_SEAT
                      and getattr(x, "side", "top") == "bottom"
                      and not _bad_height(x.height_mm)]
            tail_mm_, tail_ref = _tails(d, g.above, "top")
            if tail_mm_:
                beside.append((tail_mm_, tail_ref))
            for mm, ref in sorted(beside, reverse=True):
                if FLOOR_LINER_T + mm + CLEARANCE > g.seat_mm + 1e-9:
                    problems.append(
                        f"gap {where}: {FLOOR_SEAT} ({seat.height_mm:.1f} mm) cannot "
                        f"bolt to the floor through its {THERMAL_PAD_T:.1f} mm pad "
                        f"-- {ref} hangs {mm:.1f} mm beside it and needs the "
                        f"{FLOOR_LINER_T:.1f} mm liner and {CLEARANCE:.1f} mm "
                        f"under it")
        # BD-14: what hangs from above and what stands below must not overlap
        # in plan wherever together they are taller than the gap.
        if g.below in order and g.above in order:
            for p in d.parts:
                if p.board != g.above or p.side != "bottom" or _bad_height(p.height_mm):
                    continue
                room = g.gap_mm - p.height_mm - CLEARANCE
                blockers = sorted(
                    x.refdes for x in items
                    if x.board == g.below and getattr(x, "side", "top") == "top"
                    and not _bad_height(x.height_mm) and x.height_mm > room)
                if blockers:
                    notes.append(
                        f"keep-out: {p.refdes} hangs {p.height_mm:.1f} mm under "
                        f"{g.above}; nothing on {g.below} taller than {room:.1f} mm "
                        f"may sit beneath it ({', '.join(blockers)})")

    total = sum(g.gap_mm for g in gaps) + PCB_T * len(order)
    envelope_verdicts: list[str] = []
    if total > avail_mm + 1e-9:
        verdict = (f"stack: {total:.1f} mm derived, {avail_mm:.1f} mm available -- "
                   f"OVER by {total - avail_mm:.1f} mm")
        if envelope_is_binding():
            problems.append(verdict)
        else:
            envelope_verdicts.append(
                verdict + " against the ESTIMATED envelope (M18 unmeasured and/or "
                "enclosure undecided). Binding the moment both are settled")

    unconfirmed = unconfirmed_heights(d, order)
    setters = {r for g in gaps for r in g.set_by}
    load_bearing = tuple(r for r, *_ in unconfirmed if r in setters)
    return Stack(gaps, total, avail_mm, tuple(problems), tuple(notes),
                 unconfirmed, load_bearing, tuple(envelope_verdicts))


def envelope_is_binding() -> bool:
    """True once the envelope is a FACT: cavity measured AND enclosure chosen.

    Read at call time, not import time, so flipping either flag takes effect
    everywhere at once -- and so a test can prove the overrun becomes an error.
    """
    return bool(CAVITY_MEASURED and ENCLOSURE_DECIDED)


def stack_provisional(d: Design) -> list[str]:
    """The envelope verdict while the envelope is still an estimate."""
    return list(stack_height(d).envelope_verdicts)


def stack_problems(d: Design) -> list[str]:
    """`stack_height(d).problems` in the shape a rule returns."""
    return list(stack_height(d).problems)
