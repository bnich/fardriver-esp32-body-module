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

⚠️ IO-14 INVERTED THE WIDTH DERIVATION. The boards used to be cut out of the
cavity estimate. They are now sized to the DESIGN -- owner, 2026-09-19: "we have
the ability to increase the board size if we need to" -- and this file states
the cavity that implies, as a REQUIREMENT on the enclosure. `CAVITY_*` is still
here, still the owner's unmeasured estimate, and no longer an input to anything:
M18 confirms the requirement or forces a rethink, instead of the design failing
against a guess.

⚠️ WHAT IS STILL PROVISIONAL, and what is not:
  * The HEIGHT verdict is. It is the one budget still read against the cavity
    ESTIMATE (AVAIL_H), so an overrun is reported loudly and cannot fail the
    design until `envelope_is_binding()`.
  * The plan budgets are not. Area, pack and rows answer to BOARD_W x BOARD_L,
    which is the design's own requirement -- a fact about the design.
  * ⬜ CAVITY_REQUIRED_* is neither: it is a requirement M18 has yet to confirm.
  * The enclosure is an all-metal CNC box, but its model does not exist yet:
    wall, floor and lid are ALLOWANCES that the model's thicknesses replace.
When either lands: edit the block, flip the flag, run `python3 -m tools.board_fit`.
⚠️ Flipping both flags ARMS the comparison: `cavity_problems` then fails the
design on any plan axis the measured cavity cannot hold, and `stack_height`
fails it on the height, so the report stops being a paragraph and becomes a
verdict. That is the point of the flags -- see `envelope_is_binding`.
"""
import math
import re
from dataclasses import dataclass

from .model import Connector, Design, Part

# --- M18: the cavity, as ESTIMATED -----------------------------------------
#: ⬜ The owner's estimate of the space under the seat. Since IO-14 it sizes
#: NOTHING: the envelope below is the design's own requirement, and
#: CAVITY_REQUIRED_* says what the enclosure has to be. These three are what M18
#: will replace, and what the requirement is reported against.
CAVITY_L = 200.0   # mm, along the bike
CAVITY_W = 50.0    # mm, across -- ⚠️ the sensitive axis
CAVITY_H = 70.0    # mm, floor to the underside of the battery tray
CAVITY_MEASURED = False   # ⛔ still an estimate; flip when M18 lands

# --- enclosure: PROVISIONAL allowances -------------------------------------
# What the enclosure takes out of the cavity on each face. The enclosure is an
# all-metal CNC box (owner, 2026-09-18); these are allowances until its model
# sets the real wall, floor and lid thicknesses. CAVITY_REQUIRED_* and AVAIL_H
# inherit them, which is why both report themselves as provisional.
# ENCLOSURE_DECIDED means "the model has set these", not "the material is known".
ENCLOSURE_DECIDED = False
WALL = 3.0
FLOOR = 3.0
LID = 3.0

# --- harness plugs at the connector face (MX-3, IO-6) ------------------------
#: A harness wire leaves straight out of the back of its screw plug and has to
#: turn along the wall. ~3x the OD of a 1.5 mm² wire; tighter fatigues the
#: conductor where the plug clamps it. PROVISIONAL, with the cable exit (M18).
WIRE_BEND = 10.0

#: The connector face (IO-6): every harness plug is on one long side, and the
#: deepest mated plug stands this far past its header before its wire bends.
#: Typed so the outline and the budgets can use it as a constant; a test holds
#: it equal to `face_room(netlist.current())`, so a terminal changed in the
#: netlist without this number moving is a failure, not a silent drift.
#: Today: J101's Kefa 7.62 plug, 9.65 mm past its header, then the bend.
FACE_ROOM = 19.65


def face_room(d: Design) -> float:
    """The deepest fitted plug's overhang past its header, then the wire's bend."""
    return max((c.overhang_mm for c in d.connectors if c.leaves_box and not c.dnp),
               default=0.0) + WIRE_BEND


# --- the board envelope: THE DESIGN'S REQUIREMENT (IO-14) --------------------
#: Around the board inside the box. The connector face is the long side the
#: harness plugs stand on and gives its room to them (FACE_ROOM); this is the
#: far side: the board must drop in past the wall.
SIDE_CLEARANCE = 1.0
#: Per end: the board has to drop in past the end walls, and no plug faces them
#: (IO-6 puts every harness plug on one long side).
END_ALLOWANCE = 4.0

#: ⚠️ TYPED, NOT DERIVED FROM THE CAVITY -- that is what IO-14 changed. These
#: two are the smallest envelope on which the design as it stands closes every
#: budget in `board_fit` with at least 10 % of margin, found by searching W and
#: L rather than by picking a round number. The search, against the netlist of
#: 2026-09-20:
#:
#:   LENGTH is set by the longest row, and nothing else can set it: the harness
#:   headers of one face stand end to end along the board, and that sum is
#:   arithmetic, not a heuristic. POWER top is the longest at 197.04 mm, so
#:   197.04 / 0.90 = 218.93 -> 219.0. No width buys length back. The 21.96 mm
#:   of margin is not a round number either: 14.0 mm of it is spoken for by
#:   the four M3 corners the row may not run into -- at each END of the row two
#:   corners take 2 x M3_INSET_MM of length between them, so 2 x 2 x 3.5 =
#:   14.0 mm in total -- which the row check does not model.
#:
#:   WIDTH is then the smallest at which every face's shelf pack fits 0.90 x
#:   BOARD_L and every face's body density clears 0.90 x DENSITY_LIMIT. Density
#:   wants W >= 41.8 (POWER top's 6046 mm² of bodies); the pack is what binds,
#:   and it clears 197.1 mm first at W = 47.8. Stepped up to 48.0 so the number
#:   does not sit on the first 0.1 mm of a step in a heuristic's staircase.
#:
#: ⚠️ "SMALLEST" IS LEXICOGRAPHIC -- least LENGTH first, then least width -- and
#: NOT least area. Over L in [219, 260] the minimum-AREA envelope is 39.0 x
#: 239.0 = 9321 mm², against the 47.8 x 219 = 10468 mm² taken here: 20 mm of
#: extra length buys 8.8 mm of width back. Length is the axis to protect. The
#: cavity this design requires is already 33.0 mm LONGER than M18's estimate and
#: 24.7 mm wider, so spending length to save width makes the harder of the two
#: M18 problems worse, on the one axis nothing else can shorten (the row sets
#: it). ⛔ Do not "optimise" this to the area minimum.
#:
#: ⛔ Re-run the search when a body or a terminal changes; do not nudge these to
#: make a budget close. `python3 -m tools.board_fit` prints every margin, and
#: `tests/test_board_params.py` holds the row, the pack and the density to the
#: 10 % this search bought.
BOARD_W = 48.0
BOARD_L = 219.0
BOARD_AREA = BOARD_W * BOARD_L

AVAIL_H = CAVITY_H - FLOOR - LID        # internal height the stack may use

# --- the cavity that envelope REQUIRES ---------------------------------------
#: ⬜ UNCONFIRMED UNTIL M18. These are not observations of the bike: they are
#: what the enclosure has to be for the design above to go in it, and the
#: measurement will confirm them or force a rethink (IO-14). Across, the box
#: wall, the drop-in clearance on the far side and the plug-and-bend room in
#: front of the connector face; along, the wall and the drop-in clearance at
#: each end; tall, the DERIVED stack plus the floor and the lid
#: (`cavity_required`, because the stack is a property of the design).
#: ⚠️ These are CHECKED, not merely stated: `cavity_problems` fails the design on
#: the plan axes the moment `envelope_is_binding()` -- so a measured cavity that
#: cannot hold the design is a FAILURE, not a paragraph in a report.
#: `tests/test_board_params.py` pins all three against drift.
CAVITY_REQUIRED_W = BOARD_W + 2 * WALL + SIDE_CLEARANCE + FACE_ROOM   # 74.65
CAVITY_REQUIRED_L = BOARD_L + 2 * WALL + 2 * END_ALLOWANCE            # 233.0

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
#: (Formex GK-17 class) is the kind meant. PROVISIONAL: chosen with the
#: enclosure.
#: ⚠️ It is CUT AWAY over `FLOOR_SEAT`'s footprint, where the baseplate has to
#: reach the floor -- and that is where U201's own pads sit, `+Vin` among them.
#: ⬜ OPEN: what holds those pads off the brick's case, which is metal and at
#: FG, is the case-to-board standoff when the pins are seated. TDK's outline
#: CA952-02-01A does not fix it (note F gives the pin length only), and the
#: height model here takes the conservative reading that the case seats flush.
#: Settle it from TDK's mounting guidance or the brick in hand BEFORE the
#: enclosure floor is cut. Everything the liner protects is outside this
#: footprint; nothing here says the cut-out itself is safe.
FLOOR_LINER_T = 0.5
#: The part that seats the bottom board on the floor: the 12 V brick is
#: conduction-cooled, and its baseplate bolts to the box floor through a thermal
#: pad, which is the heatsink (BD-27; BD-9's alloy plate is WITHDRAWN, there is
#: none in the stack). Its seat sets how high the bottom board sits, so nothing
#: else on that face may hang deeper than it does, and it has to BE on that
#: face; `stack_height` fails the design on either.
FLOOR_SEAT = "U201"
#: Thermal interface material between that baseplate and the floor. Two things
#: ride on it: it is a term in the stack height (the board sits this much higher
#: than the brick is tall), and its conductivity sets how far the brick's case
#: runs above the floor -- a thicker or poorer pad spends both. PROVISIONAL:
#: chosen with the enclosure.
THERMAL_PAD_T = 0.5

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


def _paired(d: Design, order=STACK_ORDER) -> set[str]:
    """Refdes of every inter-board half that mates with a half on a neighbour.

    These two are a pair: their mated height IS the gap, so neither is a thing
    standing in it or hanging into it, and neither needs a keep-out under it.
    """
    return {c.refdes for lo, up in zip(order, order[1:])
            for pair in _pairs(d, lo, up, order) for c in pair}


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
    paired = _paired(d, order)
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
    paired = _paired(d, order)
    by_ref = {x.refdes: x for x in items}

    # The seat has to BE on the bottom board's underside. Flipped to the top,
    # or moved up a board, every gap still derives and the stack comes out
    # SHORTER -- the one arrangement that reads as an improvement while the
    # brick has nothing to cool it. A design that does not carry the part at
    # all (a fixture) says nothing either way, so the check needs it present.
    seat_part = by_ref.get(FLOOR_SEAT)
    if seat_part is not None:
        seat_side = getattr(seat_part, "side", "top")
        if (seat_part.board, seat_side) != (order[0], "bottom"):
            problems.append(
                f"seat: {FLOOR_SEAT} sits on {seat_part.board} {seat_side}, not "
                f"under {order[0]} -- its baseplate bolted to the box floor "
                f"through the thermal pad is the stack's ONLY heatsink (IO-11, "
                f"BD-27), and the FLOOR gap is derived from that seat")
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
        # in plan wherever together they are taller than the gap. A harness
        # terminal under a board hangs into the gap exactly as a part does --
        # J314 hangs under OUTPUTS into the gap POWER's chokes stand in -- so
        # connectors are iterated too. The inter-board halves are skipped:
        # their mated height IS the gap, and each one faces its own other half
        # by construction, so a keep-out under it would be four notes about
        # nothing.
        if g.below in order and g.above in order:
            for p in (*d.parts, *d.connectors):
                if (p.board != g.above or getattr(p, "side", "top") != "bottom"
                        or _bad_height(p.height_mm) or p.refdes in paired):
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


def cavity_required(d: Design, order=STACK_ORDER) -> tuple[float, float, float]:
    """(along, across, tall) the enclosure has to give this design, in mm.

    ⬜ A REQUIREMENT, not a measurement (IO-14): the plan dimensions come from
    the typed envelope, the height from the stack this design derives. M18
    confirms these or forces a rethink.
    """
    return (CAVITY_REQUIRED_L, CAVITY_REQUIRED_W,
            stack_height(d, order).total_mm + FLOOR + LID)


def cavity_overruns(d: Design, order=STACK_ORDER) -> tuple[tuple[str, float, float], ...]:
    """(axis, required, available) for every axis the cavity does not hold.

    All three axes, whatever the flags say: this is arithmetic, and the report
    states it while the cavity is an estimate as readily as when it is a
    measurement. What the flags gate is whether it FAILS -- `cavity_problems`.
    One home for the comparison, so the report and the gate cannot disagree
    about whether the design fits.
    """
    req_l, req_w, req_h = cavity_required(d, order)
    return tuple((axis, need, have) for axis, need, have in
                 (("along", req_l, CAVITY_L),
                  ("across", req_w, CAVITY_W),
                  ("tall", req_h, CAVITY_H)) if need > have + 1e-9)


def cavity_problems(d: Design, order=STACK_ORDER) -> list[str]:
    """The PLAN axes against the cavity, once the envelope is a FACT.

    Gated exactly as the height overrun is (`envelope_is_binding`): while M18
    is an estimate a requirement that exceeds it is a finding for M18, and the
    day the owner measures the cavity and flips the flag it is a design that
    does not fit the box. Without the gate it would fail the design against a
    guess; without the check it would pass a design 33 mm too long for a box
    somebody has actually measured.

    ⚠️ The TALL axis is deliberately not here. `stack_height` already fails on
    it through the same gate (AVAIL_H is CAVITY_H less the floor and the lid),
    and one overrun reported twice reads as two faults.
    """
    if not envelope_is_binding():
        return []
    return [f"cavity {axis}: the design requires {need:.2f} mm but the measured "
            f"cavity gives {have:.2f} mm -- OVER by {need - have:.2f} mm. The "
            f"board, its walls and its clearances do not go in the box that was "
            f"measured (M18); only a smaller design or a bigger box closes this"
            for axis, need, have in cavity_overruns(d, order) if axis != "tall"]


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
