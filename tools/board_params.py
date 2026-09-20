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
the cavity that implies, as a REQUIREMENT on the enclosure (`CAVITY_REQUIRED_*`).

⚠️ M18 LANDED (owner, 2026-09-20): the cavity is MEASURED at 260 x 70 x 100 mm.
Two things follow, and both are load-bearing:
  * The comparison is now a VERDICT. `cavity_problems` FAILS the design on any
    plan axis the measured cavity cannot hold, and `stack_height` fails it on
    the height. It is no longer a paragraph addressed to a future measurement.
  * WHICH AXIS IS SCARCE FLIPPED. Length has room and width does not, so the
    envelope search below spends length and protects width -- the opposite of
    what it did against the estimate. ⛔ Read the search at `BOARD_W` before
    changing either number.

⚠️ WHAT IS STILL PROVISIONAL, and what is not:
  * The enclosure is an all-metal CNC box whose model does not exist yet: WALL,
    FLOOR and LID are ALLOWANCES the model's thicknesses will replace. That is
    all `ENCLOSURE_DECIDED` claims, and it is why the REQUIREMENT is not final
    -- a thinner wall hands width back, a thicker one spends it.
  * ⛔ It is NOT a reason to withhold a verdict, and it no longer does:
    `envelope_is_binding()` answers to the MEASUREMENT alone. The reasoning is
    written out there; the short version is that the cavity is the fact this
    design cannot change, while the allowances are the design's own numbers,
    and a design is always judged against its own numbers.
  * The plan budgets are not provisional either. Area, pack and rows answer to
    BOARD_W x BOARD_L, which is the design's own requirement.
When the enclosure lands: edit the allowances, flip `ENCLOSURE_DECIDED`, run
`python3 -m tools.board_fit`, and re-run the envelope search if a wall moved.
"""
import math
import re
from dataclasses import dataclass

from .model import Connector, Design, Part

# --- M18: the cavity, as MEASURED -------------------------------------------
#: ✅ MEASURED (M18, owner, 2026-09-20): the old-controller cavity under the
#: battery compartment, where the stack lives. Since IO-14 these three size
#: NOTHING -- the envelope below is the design's own requirement and
#: CAVITY_REQUIRED_* says what the enclosure has to be. What they are is the
#: FACT that requirement is judged against, and the caps the envelope search
#: works within.
CAVITY_L = 260.0   # mm, along the bike
CAVITY_W = 70.0    # mm, across -- ⚠️ the scarce axis: 4.35 mm spare today
CAVITY_H = 100.0   # mm, floor to the underside of the battery tray
CAVITY_MEASURED = True    # ✅ M18, measured by the owner 2026-09-20

# --- enclosure: PROVISIONAL allowances -------------------------------------
# What the enclosure takes out of the cavity on each face. The enclosure is an
# all-metal CNC box (owner, 2026-09-18); these are allowances until its model
# sets the real wall, floor and lid thicknesses. CAVITY_REQUIRED_* and AVAIL_H
# inherit them, which is why the requirement is not yet FINAL.
# ENCLOSURE_DECIDED means "the model has set these", not "the material is known".
# ⛔ It does NOT gate the fit verdict -- see `envelope_is_binding`. A design that
# does not fit the measured cavity WITH these allowances fails today; what the
# model can still change is the requirement, not whether it is checked.
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
#: two are the envelope the search below picked: the design as it stands closes
#: every budget in `board_fit` on them with at least 10 % of margin, and the
#: cavity they require fits inside the one M18 measured.
#:
#: ⚠️ THE RULE IS: FIT THE MEASURED CAVITY, THEN TAKE THE NARROWEST BOARD THAT
#: STILL CLEARS EVERY BUDGET BY 10 %, SPENDING THE ABUNDANT LENGTH RATHER THAN
#: THE SCARCE WIDTH.
#: ⛔ It used to be the opposite -- least LENGTH first, then least width -- and
#: M18 inverted the reason, not just the numbers. That order was chosen while
#: the cavity was a 200 x 50 ESTIMATE the design already overran by 33.0 mm
#: along and 24.7 mm across: buying length to save width would have made the
#: worse of the two problems worse. The MEASUREMENT is 260 x 70. Length now has
#: 27.0 mm of slack and WIDTH is the axis that runs out first, so length is the
#: axis to spend and width the one to protect. ⛔ Do not restore the old order,
#: and do not re-derive it from the old reason: it is written down here so
#: nobody has to.
#:
#: The search, against the netlist and the cavity of 2026-09-20:
#:
#:   THE CAPS come straight off the measurement. Across, the box takes 2 x WALL,
#:   the far side needs SIDE_CLEARANCE to drop the board in past, and the
#:   connector face needs FACE_ROOM in front of it:
#:       70.0 - 2 x 3.0 - 1.0 - 19.65 = 43.35 mm of board.
#:   Along, 2 x WALL and END_ALLOWANCE at each end:
#:       260.0 - 2 x 3.0 - 2 x 4.0 = 246.0 mm of board.
#:
#:   WIDTH is searched first and taken as narrow as the caps allow. 39.0 mm is
#:   the NARROWEST width that closes at ANY length <= 246.0, and the PACK is
#:   what binds: at 39.0 the worst face (POWER top) packs into 214.85 mm and so
#:   needs L >= 214.85 / 0.90 = 238.72, inside the cap; at 38.9 the same face
#:   packs into 239.25 mm, needing L >= 265.8, outside it. The 24.4 mm step is
#:   C203-C206, four 12.5 x 18.5 Y-caps: 18.5 + 2 x COURTYARD = 19.50 across
#:   each, and 19.50 + 19.50 = 39.00 exactly, so they pair two to a shelf at
#:   39.0 and each take a 13.5 mm shelf of their own a tenth below it.
#:   ⚠️ 39.0 therefore sits ON that step rather than above it -- the pack reads
#:   214.85 for every width from 39.0 to 41.0 and jumps below it. The step-up
#:   this envelope buys is spent on LENGTH instead, the axis with room to spend.
#:
#:   LENGTH is then the least that clears all three budgets by 10 %. The pack
#:   wants 238.72. The longest row wants less: the harness headers of one face
#:   stand end to end along the board and that sum is arithmetic, not a
#:   heuristic -- POWER top is longest at 197.04 mm, so 197.04 / 0.90 = 218.93.
#:   Density is satisfied at any length in range (it wants only W >= 38.3 here).
#:   238.72 -> 239.0.
#:
#:   WHAT IT COSTS AND BUYS: 39.0 x 239.0 = 9321 mm², three boards 280 cm². The
#:   cavity it requires is 253.00 along (7.00 mm spare) x 65.65 across (4.35 mm
#:   spare). Margins: row 17.6 %, pack 10.1 %, density 11.7 %. The row's 41.96 mm
#:   of slack also covers the four M3 corners it may not run into -- at each END
#:   of the row two corners take 2 x M3_INSET_MM of length between them, 2 x 2 x
#:   3.5 = 14.0 mm in all -- which the row check does not model.
#:
#: ⛔ Re-run the search when a body or a terminal changes; do not nudge these to
#: make a budget close. `python3 -m tools.board_fit` prints every margin, and
#: `tests/test_board_params.py` holds the row, the pack and the density to the
#: 10 % this search bought.
BOARD_W = 39.0
BOARD_L = 239.0
BOARD_AREA = BOARD_W * BOARD_L

#: Internal height the stack may use. Cut from a MEASUREMENT since M18:
#: 100.0 - 3.0 - 3.0 = 94.0 mm, against a derived stack of 62.4. ⚠️ It was 64.0
#: against the old estimate, where the same stack sat 1.6 mm inside its limit;
#: nothing about this budget is tight any more. ⛔ It is still read against two
#: ALLOWANCES, so the enclosure's model moves it.
AVAIL_H = CAVITY_H - FLOOR - LID

# --- the cavity that envelope REQUIRES ---------------------------------------
#: These are not observations of the bike: they are what the enclosure has to be
#: for the design above to go in it (IO-14). Across, the box wall, the drop-in
#: clearance on the far side and the plug-and-bend room in front of the
#: connector face; along, the wall and the drop-in clearance at each end; tall,
#: the DERIVED stack plus the floor and the lid (`cavity_required`, because the
#: stack is a property of the design).
#: ⚠️ They are CHECKED, not merely stated: M18 is measured, so `cavity_problems`
#: FAILS the design on either plan axis the cavity cannot hold. Today they fit
#: -- 253.00 of 260.0 along, 65.65 of 70.0 across -- with 7.00 and 4.35 mm to
#: spare. ⬜ Still not FINAL: WALL is an allowance, so both figures move when the
#: enclosure's model lands. `tests/test_board_params.py` pins all three against
#: drift, because nothing else bounds what the design may ask of the enclosure.
CAVITY_REQUIRED_W = BOARD_W + 2 * WALL + SIDE_CLEARANCE + FACE_ROOM   # 65.65
CAVITY_REQUIRED_L = BOARD_L + 2 * WALL + 2 * END_ALLOWANCE            # 253.0

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
    #: The stack-versus-envelope verdict while the CAVITY is not a fact -- an
    #: overrun reported loudly, never silently, but unable to FAIL a design
    #: against a number nobody has measured. ⚠️ Empty since M18 (2026-09-20):
    #: with the cavity measured an overrun lands in `problems` instead. The
    #: machinery stays because `CAVITY_MEASURED` is what it answers to, and a
    #: guard that cannot fire today is still the guard for the day a cavity
    #: figure goes back to being a guess.
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
                verdict + " against the ESTIMATED envelope (the cavity is not "
                "measured). Binding the moment it is")

    unconfirmed = unconfirmed_heights(d, order)
    setters = {r for g in gaps for r in g.set_by}
    load_bearing = tuple(r for r, *_ in unconfirmed if r in setters)
    return Stack(gaps, total, avail_mm, tuple(problems), tuple(notes),
                 unconfirmed, load_bearing, tuple(envelope_verdicts))


def cavity_required(d: Design, order=STACK_ORDER) -> tuple[float, float, float]:
    """(along, across, tall) the enclosure has to give this design, in mm.

    A REQUIREMENT, not a measurement (IO-14): the plan dimensions come from the
    typed envelope, the height from the stack this design derives. M18 measured
    the cavity these are judged against; `cavity_overruns` does the comparing
    and `cavity_problems` decides whether it is a failure.
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
    """The PLAN axes against the cavity, now that the cavity is a FACT.

    Gated exactly as the height overrun is (`envelope_is_binding`), which since
    M18 means gated on the MEASUREMENT alone. Without the gate this would have
    failed the design against a guess; without the check it would pass a design
    too wide for a box somebody has actually measured.

    ⚠️ The TALL axis is deliberately not here. `stack_height` already fails on
    it through the same gate (AVAIL_H is CAVITY_H less the floor and the lid),
    and one overrun reported twice reads as two faults.
    """
    if not envelope_is_binding():
        return []
    # ⚠️ The lever named depends on ENCLOSURE_DECIDED, because it is the honest
    # one: while WALL is still an allowance, a thinner wall really can close a
    # small overrun, and a reader who is not told that will redesign a board
    # instead. Once the model sets the wall, that lever is gone.
    lever = ("a smaller design or a bigger box" if ENCLOSURE_DECIDED else
             "a smaller design, a thinner wall allowance or a bigger box")
    return [f"cavity {axis}: the design requires {need:.2f} mm but the measured "
            f"cavity gives {have:.2f} mm -- OVER by {need - have:.2f} mm. The "
            f"board, its walls and its clearances do not go in the box that was "
            f"measured (M18); only {lever} closes this"
            for axis, need, have in cavity_overruns(d, order) if axis != "tall"]


def envelope_is_binding() -> bool:
    """True once the CAVITY is a measurement rather than a guess.

    ⚠️ THE DECISION, 2026-09-20, and the reason, because the alternative is
    defensible and somebody will ask: a measured cavity the design does not fit
    FAILS even while `ENCLOSURE_DECIDED` is False. This used to require both
    flags.

    The two flags are not the same kind of thing.
      * `CAVITY_MEASURED` is about the BIKE. Nothing in this design can move
        260 x 70 x 100, and a design that does not go in it is broken now.
      * `ENCLOSURE_DECIDED` is about the DESIGN'S OWN allowances -- WALL, FLOOR,
        LID. A design is always judged against its own numbers; if those numbers
        later change, the requirement re-derives and this gate re-answers.
    Waiting for the box to be modelled would mean holding a known failure open
    across every hour of work that gets built on the design meanwhile, to buy
    one thing: the chance that a thinner wall rescues it. That is the wrong
    trade -- and the chance is not lost, because the failure message says so and
    the requirement recomputes the moment an allowance moves.

    ⛔ Do not re-add `ENCLOSURE_DECIDED` here. It still has its own job: it says
    the requirement is not FINAL, which is why `Stack.provisional` reads it, why
    the report carries the allowance caveat on its first line, and why the
    failure text names the wall as a lever.

    Read at call time, not import time, so flipping the flag takes effect
    everywhere at once -- and so a test can prove the overrun becomes an error.
    """
    return bool(CAVITY_MEASURED)


def stack_provisional(d: Design) -> list[str]:
    """The envelope verdict while the envelope is still an estimate."""
    return list(stack_height(d).envelope_verdicts)


def stack_problems(d: Design) -> list[str]:
    """`stack_height(d).problems` in the shape a rule returns."""
    return list(stack_height(d).problems)
