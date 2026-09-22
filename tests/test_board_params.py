"""The stack's geometry is DERIVED from the design, and these tests prove it by
building small designs whose answer can be worked out by hand.

Every expectation below is arithmetic on the fixture's own heights plus the
stated parameters (PCB 1.6, clearance 1.0, trimmed tails 1.5, floor liner 0.5,
thermal pad 0.5 under the brick, floor boss 3.0). None of them re-implements
`layer_gaps`; each states the number a person would get.
"""
import math
from dataclasses import replace

import pytest

from tools import board_params as bp
from tools.model import ConnPin, Connector, Design, Part, Standoff


def part(ref, board, height, *, side="top", confirmed=True, package="0805",
         mpn="X", dnp=False):
    """A BODY with a height and a footprint: kind MECH, because the height
    model reads neither kind nor value, and a resistor with no value is what
    the model refuses (M11)."""
    return Part(ref, mpn, package, board, "MECH", ("1", "2"), height, confirmed,
                (2.0, 1.25), side=side, dnp=dnp)


def conn(ref, board, height, *, confirmed=True, interface=None):
    return Connector(ref, board, ref, (ConnPin("1", ""),), height, confirmed,
                     (10.0, 5.0), leaves_box=interface is None,
                     interface=interface)


def three_boards(power_top=14.0):
    """POWER: one tall THT part on top, the brick UNDER the board on its floor
    seat. OUTPUTS, LOGIC: a 7.0 connector each."""
    return Design(
        parts=(part("L101", "POWER", power_top, package="THT"),
               part("U201", "POWER", 12.7, package="brick", side="bottom"),
               part("U401", "LOGIC", 3.1, package="module")),
        connectors=(conn("J301", "OUTPUTS", 7.0), conn("J401", "LOGIC", 7.0)))


def gap(stack, below, above):
    return next(g for g in stack.gaps if (g.below, g.above) == (below, above))


# --- parameters ----------------------------------------------------------------
def test_the_envelope_the_pcb_outline_is_cut_to():
    # IO-14: the board is the DESIGN's requirement, not a slice of the cavity,
    # so these two are typed. 41.84 x 242 = 10125.28 mm². The PCB emitter draws
    # BOARD_W x BOARD_L, so a change here is a change to a manufactured outline
    # and must be meant -- and it must come from re-running the search in the
    # file's comment, never from nudging a budget closed.
    # ⚠️ The WIDTH is not the search's own answer: the search returns 40.84 and
    # 40.84 sits ON a 6.90 mm pack cliff, so the board stands 1.0 mm clear of
    # it. That is a CHECKED property, below.
    assert (bp.BOARD_W, bp.BOARD_L) == (41.84, 242.0)
    assert bp.BOARD_AREA == pytest.approx(41.84 * 242.0) == pytest.approx(10125.28)
    # Height is cut from the MEASURED cavity: 100 - 3 floor - 3 lid = 94.
    assert bp.AVAIL_H == 100.0 - 3.0 - 3.0 == 94.0


# --- the 10 % the envelope search bought ------------------------------------
# ⚠️ These three are DESIGN-MARGIN tests and they are not board_fit's gates.
# board_fit asks whether the board can be built at all -- a row or a pack over
# 100 % of BOARD_L, a face over DENSITY_LIMIT. These ask the different question
# IO-14 answered: is the 10 % of headroom the envelope search paid for still
# there? Every one of them would pass at 100 %, which is exactly why they exist:
# without them the margin can erode to zero with every gate green and the
# envelope quietly stops being the one IO-14 chose.
# ⛔ Do not "simplify" one of these into board_fit's limit. A tripwire set at the
# limit it is guarding is not a tripwire.
#: IO-24 (amended 2026-09-21): the 12 V row, OUTPUTS top, is the ONE stated
#: exception to the 90 % row margin, and only as far as it stands. The row is
#: arithmetic (tools.netlist._tb: N x 3.81 + 10.48 per 3.81 mm Kangnex header,
#: HEADER_GAP between neighbours), so the exception is the row's own figure,
#: not a rounder fraction -- 0.91 x 242.0 = 220.22 would not even hold it.
TWELVE_V_ROW_MM = 220.28


def test_the_board_length_holds_the_longest_row_with_room_to_spare():
    """The row is arithmetic, not a heuristic, so it is one of the two things
    BOARD_L answers to. Every row is held to 0.90 x 242.0 = 217.80 mm except
    the 12 V row, which is held to TWELVE_V_ROW_MM, where it stands.

    THE EXCEPTION (IO-24, amended 2026-09-21). J301, J303 and J305 were three
    3.81 x 4 terminals with three polarity conventions, and a swapped plug
    drove a load reversed or held a lamp common at +12 V. The fix is a unique
    size for each, and the family is saturated: every size 2-9 at 3.81 mm is a
    terminal in one of the two rows and the 11-way header is stock 0, so J303
    took 10 ways and J305 twelve. The 12 V row, by hand, header by header:
      J301  4 x 3.81 + 10.48 =  25.72
      J302  5 x 3.81 + 10.48 =  29.53
      J303 10 x 3.81 + 10.48 =  48.58
      J304  2 x 3.81 + 10.48 =  18.10
      J305 12 x 3.81 + 10.48 =  56.20
      J313  7 x 3.81 + 10.48 =  37.15   bodies 215.28
      five HEADER_GAPs of 1.0            +  5.00 = 220.28 mm
    220.28 / 242.0 = 91.0 %, 2.48 mm past the 90 % line. The margin exists to
    absorb connector growth, and closing a real polarity hazard is what it is
    for; the owner accepted this row on 2026-09-21. It is an exception, not a
    loosening: the other rows keep 0.90, the pack and density tripwires below
    are untouched, and the row is pinned where it stands, so the NEXT thing to
    lengthen it -- a seventh header (18.10 + 1.0 mm at the least) or one more
    position (3.81 mm) -- fails here and is a new decision. What a real defect
    scores: a row over the board itself is 242.0 mm, 100 %, and board_fit
    fails it; this test fires 21.72 mm before that.

    The other rows: POWER top's five headers are 55.88 + 25.4 + 35.56 + 20.32 +
    55.88 = 193.04 of body and four 1 mm gaps = 197.04 mm, 81.4 %, clearing
    217.80 by 20.76 mm; LOGIC top 185.94, OUTPUTS bottom 38.40. The 12 V row
    clears the board by 21.72 mm, 14.0 mm of which the four M3 corners take: at
    each END of the row two corners take 2 x 3.5 mm of length between them, so
    2 x 2 x 3.5 = 14.0 mm in all, and 7.72 mm is left.

    ⚠️ No row sets the length. The 12 V row would want 220.28 / 0.90 = 244.76
    and does not get it; the PACK wanted 239.49, and 242.0 was taken to keep the
    pack tripwire off a hair trigger.
    Protects: that every row but the one excepted keeps its margin while the
    length is being set by something else, and that the exception stays the
    size it was accepted at."""
    from tools import board_fit as bf, netlist
    rows = {(e.board, e.side): e.length_mm for e in bf.edge_budget(netlist.current())}
    twelve_v = rows.pop(("OUTPUTS", "top"))
    assert twelve_v == pytest.approx(TWELVE_V_ROW_MM, abs=0.01)   # the exception, where it stands
    assert twelve_v / bp.BOARD_L == pytest.approx(0.910, abs=0.0005)
    assert twelve_v - 0.90 * bp.BOARD_L == pytest.approx(2.48, abs=0.01)
    for face, length in rows.items():
        assert length <= 0.90 * bp.BOARD_L, face                     # the tripwire, every other row
    assert max(rows.values()) == pytest.approx(197.04)              # POWER top, unchanged
    assert bp.BOARD_L - twelve_v > 4 * bf.M3_INSET_MM


def test_the_worst_pack_keeps_the_10_percent_the_envelope_was_chosen_for():
    """The pack is what BOARD_L was set by. POWER top binds: 215.54 mm against
    0.90 x 242.0 = 217.80, so 2.26 mm of slack.

    ⚠️ THIS TRIPWIRE WAS A STRICT XFAIL for the length of IO-20's parts task:
    the cabled crossings put a 38.08 x 8.4 box header and a 19.74 x 8.5 keyed
    power header on POWER top in place of a 58.42 x 2.54 bus, the binding pack
    went 214.85 -> 225.13 mm against the 216.90 the 40 x 241 envelope bought,
    and the design still BUILT. Re-running the search is what brought it back:
    41.84 x 242.0, derived in `board_params`. ⛔ The marker is gone, not
    loosened -- the figures below are the new envelope's, hand-computed.

    240.0 would have done for the pack -- the next whole millimetre above
    215.54 / 0.90 = 239.49 -- and it leaves 0.46 mm here; 241.0 leaves 1.36.
    A tripwire with well under a millimetre of slack fires on almost any
    change, which is noise and not signal, and 2.0 mm is what the same choice
    bought on 2026-09-20. Length is the abundant axis (4.00 mm of cavity spare
    even at 242.0). ⛔ What a body that grows must NOT be answered by is a wider
    board: the pack cliff is at 40.84 mm and the board stands 1.00 mm above it,
    with only 1.51 mm of cavity width left (see the cliff tests below).

    Protects: that margin. board_fit only fails a pack at 242 mm, so without
    this a body could grow 26 mm and nothing would say the envelope had stopped
    being the one the search chose -- which is exactly what it said in IO-20."""
    from tools import board_fit as bf, netlist
    worst = max(bf.area_budget(netlist.current()),
                key=lambda s: -1.0 if s.pack_mm is None else s.pack_mm)
    assert (worst.board, worst.side) == ("POWER", "top")
    assert worst.pack_mm == pytest.approx(215.54, abs=0.01)     # where it stands
    assert worst.pack_mm <= 0.90 * bp.BOARD_L          # the tripwire
    assert 0.90 * bp.BOARD_L - worst.pack_mm == pytest.approx(2.26, abs=0.01)


def test_the_worst_density_keeps_the_10_percent_the_envelope_was_chosen_for():
    """The same search held every face to 0.90 x DENSITY_LIMIT = 0.675. POWER
    top binds again: 6243.18 mm² of bodies in 41.84 x 242.0 - 196 = 9929.28 mm²
    of usable side = 0.6288, which clears 0.675 by 0.0462 -- 16.2 % of headroom
    against the 0.75 board_fit fails at. ⚠️ It was 0.6611 on the 40 x 241 board
    IO-20's cabled crossings left behind, 0.0139 inside the tripwire; the wider
    envelope is what bought it back.

    Protects: the headroom routing, courtyards and creepage come out of. Density
    is not what set the envelope (at 41.84 mm it wanted only L >= 225.74), so it
    has more slack than the pack -- but board_fit does not fail a face until
    0.75, and a face drifting from 0.629 to 0.749 is a board nobody can lay
    out, silently."""
    from tools import board_fit as bf, netlist
    worst = max(bf.area_budget(netlist.current()), key=lambda s: s.density)
    assert (worst.board, worst.side) == ("POWER", "top")
    assert worst.density <= 0.90 * bf.DENSITY_LIMIT    # the tripwire
    assert worst.density == pytest.approx(0.6288, abs=0.0005)   # where it stands


# --- the pack CLIFF: derived from the packer, not typed ----------------------
# ⚠️ The shelf pack is not smooth in the board's WIDTH. It steps, because a body
# either fits beside another across the board or it does not, and at the width
# where two bodies start pairing a whole shelf disappears at once. Today's step
# is 6.90 mm tall and sits at 40.84 mm, and the 41.84 mm board stands 1.00 mm
# above it. What follows DERIVES where it is from the packer; nothing here is
# allowed to type a width as the answer, which is why the step moving is
# something these tests report rather than something they break on.
#
# The caps are the measured cavity's, exactly as `board_params`' envelope search
# takes them: along, the box wall and the drop-in clearance at each end; across,
# the wall, the far-side drop-in and the room in front of the connector face.
def _cavity_board_caps():
    """(longest, widest) board the MEASURED cavity can carry, in mm."""
    return (bp.CAVITY_L - 2 * bp.WALL - 2 * bp.END_ALLOWANCE,          # 246.00
            bp.CAVITY_W - 2 * bp.WALL - bp.SIDE_CLEARANCE - bp.FACE_ROOM)  # 43.35


def _worst_pack(d, width):
    """(mm, face) of the binding face's shelf-pack on a board `width` wide.

    Straight out of `board_fit.shelf_pack`, at a width that is an ARGUMENT and
    not `BOARD_W`, which is the whole point: it lets the step be found. A face
    that cannot place a body at all is infinitely long, which is the honest
    reading -- there is no length of board that carries it.
    """
    from tools import board_fit as bf
    worst, face = 0.0, "-"
    for board in bp.STACK_ORDER:
        for side in bf.SIDES:
            rects = bf.bodies(d, board, side)
            if not rects:
                continue
            mm, blocked = bf.shelf_pack(rects, width)
            if mm is None:
                return math.inf, f"{board} {side} ({blocked} does not fit)"
            if mm > worst:
                worst, face = mm, f"{board} {side}"
    return worst, face


def pack_cliff(d, tol=1e-7):
    """Where the pack steps, found by bisection on the board's WIDTH.

    -> (edge_mm, face, below_mm, above_mm): the narrowest width whose pack a
    board the cavity allows can carry, the face that binds there, and the pack
    just below that width and at it.

    A width is CARRYABLE when the binding face packs into 0.90 x the longest
    board the cavity allows -- 0.90 x 246.0 = 221.40 mm. The 0.90 is the same
    design margin the envelope search bought and the three tripwires above hold;
    without it the question is meaningless, because a pack at 99 % of the board
    is not an envelope anybody would choose.

    So the edge is the boundary between "no length the measured cavity allows
    absorbs this pack" and "one does", and the step across it is the fall that
    boundary exists for.
    """
    lo, hi = 20.0, _cavity_board_caps()[1]
    assert _worst_pack(d, lo)[0] > 0.90 * _cavity_board_caps()[0], (
        f"⛔ THE SEARCH HAS NO BRACKET: a {lo} mm board already packs into a "
        f"length the cavity carries, so the step this guard exists for is not "
        f"between {lo} and {hi} mm. Widen the search or re-run the envelope one.")
    assert _worst_pack(d, hi)[0] <= 0.90 * _cavity_board_caps()[0], (
        f"⛔ NO BOARD THE MEASURED CAVITY ALLOWS CLOSES THE PACK: at the widest "
        f"it permits ({hi:.2f} mm) the binding face still packs into "
        f"{_worst_pack(d, hi)[0]:.2f} mm, which needs more than the "
        f"{_cavity_board_caps()[0]:.1f} mm of length the cavity permits. This is "
        f"not a clearance problem -- the design no longer fits the box.")
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if _worst_pack(d, mid)[0] <= 0.90 * _cavity_board_caps()[0]:
            hi = mid
        else:
            lo = mid
    above, face = _worst_pack(d, hi)
    return round(hi, 4), face, _worst_pack(d, lo)[0], above


def cliff_problems(d) -> list[str]:
    """The cliff guard, as a list so a mutation can read it instead of dying.

    Two levels, because they are two different failures:
      ABOVE THE BOARD  the step has climbed past BOARD_W. The boards have to be
                       re-shaped -- this is not a margin, it is the envelope.
      CLEARANCE        the step is at or below BOARD_W but nearer than the
                       1.0 mm the owner bought. The design still builds; what is
                       gone is the standoff, and that is a decision to take
                       deliberately rather than discover.
    """
    edge, face, below, above = pack_cliff(d)
    # An infinite figure below the step is not a long pack: it is a body that
    # cannot be placed at all on a board that narrow, which is a wall and not a
    # step. Say that, rather than printing "inf mm".
    fall = (f"falls {below - above:.2f} mm across that step"
            if math.isfinite(below) else
            "cannot be placed at all below it -- a body fits in neither "
            "orientation, so the step has no far side")
    if edge > bp.BOARD_W + 1e-9:
        need = (f"packs into {below:.2f} mm, needing a {below / 0.90:.2f} mm "
                f"board against the {_cavity_board_caps()[0]:.2f} mm the cavity "
                f"allows" if math.isfinite(below) else
                "cannot be placed at all -- a body fits in neither orientation")
        return [f"cliff above the board: the pack steps at {edge:.2f} mm of "
                f"width and BOARD_W is {bp.BOARD_W:.2f}. Below the step {face} "
                f"{need}. Re-run the envelope search"]
    if bp.BOARD_W - edge < 1.0 - 1e-9:
        return [f"cliff clearance: the pack steps at {edge:.2f} mm of width and "
                f"BOARD_W is {bp.BOARD_W:.2f} -- {bp.BOARD_W - edge:.2f} mm "
                f"above it, against the 1.00 mm the owner bought on 2026-09-20. "
                f"{face} {fall}"]
    return []


def test_the_pack_cliff_is_derived_from_the_packer():
    """⭐ THE CLIFF, as a CHECKED property rather than a paragraph.

    WHAT IT PROTECTS. `board_fit`'s shelf pack steps in the board's width,
    because a body either fits beside another across the board or it does not.
    ⚠️ WHICH TWO BODIES MAKE THE STEP IS NOT A CONSTANT. It was the Y-caps:
    C203-C206 are 12.5 x 18.5, so 18.5 + 2 x COURTYARD = 19.50 across each and
    two paired at 39.00 EXACTLY. Since IO-20 it is C207, the 19.1 mm polymer
    bulk cap at 20.10 across, pairing with J202, the keyed power header at
    19.74 + 2 x COURTYARD = 20.74 -- and 20.10 + 20.74 = 40.84. Below that
    width they take a shelf each and POWER top packs into 225.13 mm; at it they
    share one and the same face packs into 218.23 mm, a 6.90 mm step.

    ⛔ Nothing here types a width as the answer. `pack_cliff` bisects on the
    width and asks the packer, so the guard finds the step wherever the
    geometry puts it -- which is how it found this one after the two bodies
    that made the old one stopped being the binding pair. The mutation tests
    below move it deliberately, from both bodies and from the courtyard."""
    from tools import netlist
    edge, face, below, above = pack_cliff(netlist.current())
    assert face == "POWER top"
    assert edge == pytest.approx(40.84, abs=0.01)          # where the step IS
    assert (below, above) == (pytest.approx(225.13), pytest.approx(218.23))
    assert below - above == pytest.approx(6.90, abs=0.01)   # ...and how tall
    # ...and no length the cavity allows absorbs the pack below it:
    assert below / 0.90 > _cavity_board_caps()[0]


def test_the_board_stands_clear_of_the_cliff():
    """⚠️ WHY A BOARD MUST NOT SIT ON THE STEP. A board on the edge is one where
    any growth in a body, or in COURTYARD, re-shapes BOTH plan axes -- the width
    walks up and the length follows the pack. The clearance is 1.0 mm and it has
    no slack of its own by construction: it IS the purchase, not a percentage of
    it. Spending any of it is meant to be a decision, which is what this says.

    ⚠️ THIS WAS A STRICT XFAIL for the length of IO-20's parts task: the step
    moved from 39.00 mm (two Y-caps pairing) to 40.84 (C207 pairing with the new
    J202), 0.84 mm ABOVE the 40.0 mm board, so the board was on the wrong side
    of it. The envelope search is what answered it -- 41.84 is 40.84 + the
    millimetre, exactly as 40.0 was 39.00 + it -- and the marker is gone rather
    than loosened."""
    from tools import netlist
    edge, _face, _below, _above = pack_cliff(netlist.current())
    assert bp.BOARD_W - edge == pytest.approx(1.0, abs=1e-9), \
        f"the step is at {edge:.2f} mm"
    assert cliff_problems(netlist.current()) == []


def test_the_guard_reports_a_board_below_the_cliff(board_width):
    """⚠️ THE MUTATION, direction one: the board's own width, which the guard
    must answer to, in both of the shapes a too-narrow board takes. Every
    board_fit gate is green at 40.0 mm AND at 41.0 -- that is exactly why this
    guard has to exist -- while one is below the step and the other 0.16 mm
    above it, so the guard is the only thing that says the envelope needs
    re-running and by how much.

    ⚠️ 40.0 x 241.0 is not a hypothetical width: it is the envelope IO-20's
    cabled crossings were left standing on, and this is the message that said
    so."""
    from tools import board_fit as bf, netlist
    d = netlist.current()
    assert bf.problems(d) == []                          # 41.84 mm: it builds
    assert cliff_problems(d) == []                       # ...and it is clear
    board_width(40.0)
    assert bf.problems(d) == []                          # 40.0 mm: it still builds
    (at_40,) = cliff_problems(d)
    assert at_40.startswith("cliff above the board:")
    assert "steps at 40.84 mm" in at_40 and "BOARD_W is 40.00" in at_40
    assert "packs into 225.13 mm" in at_40 and "Re-run the envelope search" in at_40
    board_width(41.0)
    assert bf.problems(d) == []                          # ...and it still builds
    (at_41,) = cliff_problems(d)
    assert at_41.startswith("cliff clearance:")          # above it, but not by 1 mm
    assert "steps at 40.84 mm" in at_41 and "BOARD_W is 41.00" in at_41
    assert "0.16 mm above it" in at_41


def test_the_cliff_follows_the_bodies_that_make_it(grown_y_caps, grown_body):
    """⚠️ THE MUTATION, direction two, and the one that proves the step is
    DERIVED: move the bodies that pair at it and the step has to move with
    them. ⭐ TWO DIFFERENT PAIRS, deliberately — the binding pair changed once
    already (IO-20), and a mutation aimed only at the Y-caps would have gone on
    "proving" the guard while it had stopped answering to them.

      C207 +0.50  20.10 -> 20.60 across, pairing with J202's 20.74 at 41.34.
                  Still below the board, but only 0.50 mm below: a CLEARANCE
                  problem, the mildest of the guard's three answers.
      C207 -1.00  19.10 across, pairing at 39.84 -- 2.00 mm clear, and the
                  guard goes SILENT. The one mutation here that proves the
                  guard can be satisfied as well as fail.
      Y-caps +1.5 21.00 mm across each, pairing at 42.00, ABOVE the board and
                  displacing the pair that makes today's step. This is not a
                  clearance: the boards have to be re-shaped, and the guard says
                  so in different words."""
    near = grown_body("C207", 0.5)
    assert pack_cliff(near)[0] == pytest.approx(41.34, abs=0.01)
    (tight,) = cliff_problems(near)
    assert tight.startswith("cliff clearance:")
    assert "steps at 41.34 mm" in tight and "0.50 mm above it" in tight

    clear = grown_body("C207", -1.0)
    assert pack_cliff(clear)[0] == pytest.approx(39.84, abs=0.01)
    assert cliff_problems(clear) == []                   # 2.00 mm clear

    over = grown_y_caps(1.5)
    assert pack_cliff(over)[0] == pytest.approx(42.00, abs=0.01)
    (past,) = cliff_problems(over)
    assert past.startswith("cliff above the board:")
    assert "steps at 42.00 mm" in past and "BOARD_W is 41.84" in past
    assert "packs into 228.53 mm" in past               # ...and what that costs
    assert "Re-run the envelope search" in past


def test_the_courtyard_is_in_the_same_sum_and_moves_the_cliff_too(monkeypatch):
    """The step is (19.10 + 19.74) + 4 x COURTYARD -- two bodies, two
    courtyards each -- so the courtyard is as load-bearing as either body is,
    and it grows EVERY body, not two.
    ⛔ COURTYARD is not a dial (it is IPC-7351's most generous excess); this
    mutates it only to show the guard answers to it, and it reaches all three
    of the guard's answers on its own. While that pair still binds, each
    0.05 mm moves the step 0.20 mm: 0.45 puts it at 40.64 (1.20 mm clear, and
    SILENT) and 0.55 at 41.04 (0.80 mm, a CLEARANCE problem). ⚠️ By 0.65 the sum
    no longer predicts it -- 42.60, not 41.44 -- because every other body has
    grown too and a different pair binds; the guard still finds it, ABOVE the
    board, which is the point of deriving rather than typing. ⚠️ At 0.70 there
    is no step left to find -- the widest board the measured cavity allows no
    longer closes the pack -- and `pack_cliff` says THAT instead of returning a
    number, which is the answer that matters."""
    from tools import board_fit as bf, netlist
    d = netlist.current()
    monkeypatch.setattr(bf, "COURTYARD", 0.45)
    assert pack_cliff(d)[0] == pytest.approx(40.64, abs=0.01)
    assert cliff_problems(d) == []                       # 1.20 mm clear
    monkeypatch.setattr(bf, "COURTYARD", 0.55)
    assert pack_cliff(d)[0] == pytest.approx(41.04, abs=0.01)
    assert cliff_problems(d)[0].startswith("cliff clearance:")
    monkeypatch.setattr(bf, "COURTYARD", 0.65)
    assert pack_cliff(d)[0] == pytest.approx(42.60, abs=0.01)
    assert cliff_problems(d)[0].startswith("cliff above the board:")
    monkeypatch.setattr(bf, "COURTYARD", 0.70)
    with pytest.raises(AssertionError, match="no longer fits the box"):
        pack_cliff(d)


def test_the_cavity_the_envelope_requires_is_stated_against_m18():
    """A requirement on the enclosure, not a measurement of the bike.
    Across: 41.84 board + 2 x 3 wall + 1 drop-in on the far side + 19.65 in
    front of the connector face = 68.49. Along: 242 + 2 x 3 + 2 x 4 = 256.0.
    Tall: the DERIVED stack + 3 floor + 3 lid."""
    assert bp.CAVITY_REQUIRED_W == pytest.approx(68.49)
    assert bp.CAVITY_REQUIRED_L == pytest.approx(256.0)
    d = three_boards()                                   # 52.0 mm of stack
    assert bp.cavity_required(d) == pytest.approx((256.0, 68.49, 52.0 + 6.0))
    # ...and it goes inside the cavity M18 measured, with the spare stated:
    # 260.0 - 256.0 = 4.00 mm along, 70.0 - 68.49 = 1.51 mm across.
    assert bp.CAVITY_L - bp.CAVITY_REQUIRED_L == pytest.approx(4.00)
    assert bp.CAVITY_W - bp.CAVITY_REQUIRED_W == pytest.approx(1.51)


def test_the_required_cavity_cannot_grow_without_someone_typing_the_new_number():
    """⚠️ A DRIFT TRIPWIRE on the real netlist, not a derivation.

    CAVITY_REQUIRED_* is an OUTPUT and nothing bounds it from below. Since M18
    `cavity_problems` does bound it from above -- a requirement past 260.0 or
    70.0 now FAILS -- but the whole distance to that bound is only 4.00 mm along
    and 1.51 mm across, and every millimetre of it can be spent with every gate
    green. A body or a terminal that walks the width from 68.49 to 69.9 leaves
    the design fitting by 0.1 mm and nobody told. The per-wall plug-room verdict
    that used to push back was removed with IO-6's connector face.

    Protects: the spare the envelope search bought against the measured cavity.
    These are today's figures on today's netlist; a terminal, a body height, the
    wall or a clearance that moves one of them fails here, so whoever moved it
    has to look at the new number and type it in.

    THE ARITHMETIC, by hand:
      along   242.0 board + 2 x 3.0 wall + 2 x 4.0 end allowance   = 256.00
      across  41.84 board + 2 x 3.0 wall + 1.0 drop-in + 19.65 face =  68.49
      tall    the DERIVED stack + 3.0 floor + 3.0 lid, and the stack is
              13.20 FLOOR->POWER (U201's 12.7 brick on its 0.5 pad)
            + 30.00 POWER->OUTPUTS (the Shuntian M3X30 standoff, which SETS it)
            + 11.04 OUTPUTS->LOGIC (J308+J406, the STACK pair that stops)
            +  8.25 LOGIC->LID (J410's 7.25 + 1.0 clearance)
            +  3 x 1.6 of PCB                                     =  67.29
              so 67.29 + 6.0                                      =  73.29

    ⚠️ The TALL figure is asserted beside the plan axes because it must NOT move
    WITH them: the stack is derived from heights alone. It was 68.39 at 48 x 219,
    at 39 x 239 and at 40 x 241 -- three envelopes, one height. What moved it to
    73.29 is the standoff term, which took POWER->OUTPUTS from the 25.10 the
    obstructions needed to the 30.0 the M3x30 posts give: +4.90, and the plan
    axes did not move a micron for it."""
    from tools import netlist
    along, across, tall = bp.cavity_required(netlist.current())
    assert (along, across) == pytest.approx((256.0, 68.49))
    assert tall == pytest.approx(73.29, abs=0.01)
    # ...and the measurement they are judged against, so a drift in EITHER bites.
    assert (bp.CAVITY_L, bp.CAVITY_W, bp.CAVITY_H) == (260.0, 70.0, 100.0)
    assert bp.cavity_overruns(netlist.current()) == ()      # it fits, on all three


def test_the_tall_requirement_does_not_answer_to_the_board_s_width_or_length(
        monkeypatch):
    """Shown, not assumed. Reshaping the board from 48 x 219 to 40 x 241 moved
    both plan axes and must have moved the height by nothing at all: the stack
    is a sum of part heights, clearances and PCB, and no term of it is a plan
    dimension. Put the old envelope back and the tall figure is the same."""
    from tools import netlist
    d = netlist.current()
    tall_now = bp.cavity_required(d)[2]
    monkeypatch.setattr(bp, "BOARD_W", 48.0)
    monkeypatch.setattr(bp, "BOARD_L", 219.0)
    monkeypatch.setattr(bp, "BOARD_AREA", 48.0 * 219.0)
    assert bp.cavity_required(d)[2] == pytest.approx(tall_now)
    assert bp.stack_height(d).total_mm == pytest.approx(tall_now - bp.FLOOR - bp.LID)


# --- the cavity requirement is CHECKED, now that the cavity is a fact --------
def test_the_measured_cavity_holds_the_design_and_the_gate_is_armed():
    """The real flags. M18 measured 260 x 70 x 100 and the design asks for
    255.0 x 66.65 x 68.4, so there is no verdict to give -- and, unlike before
    M18, the empty list means it FITS and not that nothing was gating it."""
    from tools import netlist
    assert bp.envelope_is_binding()
    assert bp.cavity_overruns(netlist.current()) == ()
    assert bp.cavity_problems(netlist.current()) == []


def test_the_gate_answers_to_the_measurement_not_to_the_enclosure():
    """⚠️ THE DECISION of 2026-09-20, asserted and not merely commented: a
    MEASURED cavity binds while the enclosure is still undecided. Both flags are
    read as they really are, and `envelope_is_binding` must follow only the
    first. ⛔ If someone re-adds ENCLOSURE_DECIDED to that gate, this fails and
    the reasoning is in `board_params.envelope_is_binding`."""
    assert (bp.CAVITY_MEASURED, bp.ENCLOSURE_DECIDED) == (True, False)
    assert bp.envelope_is_binding()


def test_a_board_too_wide_for_the_measured_cavity_fails(wider_board):
    """⚠️ THE MUTATION that makes the gate a check rather than a claim. Today's
    40.0 mm board asks 66.65 mm of the 70.0 M18 measured and passes; a 45.0 mm
    board asks 71.65 mm and does not go in the box. The flags are the real ones
    -- the enclosure is STILL UNDECIDED -- so this is exactly the case the
    decision is about, and the failure names the wall allowance as the lever
    that has not been spent yet."""
    from tools import netlist
    d = netlist.current()
    assert bp.cavity_problems(d) == []                   # 40.0 mm: it fits
    wider_board(45.0)
    (across,) = bp.cavity_problems(d)
    assert across.startswith("cavity across:")
    assert "requires 71.65 mm" in across and "gives 70.00 mm" in across
    assert "OVER by 1.65 mm" in across
    assert "thinner wall allowance" in across            # the lever still open


def test_a_measured_cavity_that_cannot_hold_the_design_is_a_failure(measured_cavity):
    """256.0 x 68.49 required; a 250 x 61 box holds neither axis, and each
    problem names its axis and the overrun."""
    d = three_boards()
    measured_cavity(250.0, 61.0)
    along, across = bp.cavity_problems(d)
    assert along.startswith("cavity along:") and "OVER by 6.00 mm" in along
    assert across.startswith("cavity across:") and "OVER by 7.49 mm" in across
    assert "measured cavity gives 250.00 mm" in along


def test_a_measured_cavity_that_holds_the_design_is_no_verdict_at_all(measured_cavity):
    measured_cavity(270.0, 80.0)
    assert bp.cavity_problems(three_boards()) == []
    assert bp.cavity_overruns(three_boards()) == ()


def test_the_tall_axis_is_left_to_the_stack_so_one_overrun_is_not_two_faults():
    """`three_boards(60.0)` is 98.0 mm of stack, 104.0 mm of cavity against the
    100 mm M18 measured: `cavity_overruns` sees it on the tall axis, and it is
    `stack_height` that fails on it. `cavity_problems` must not say it again.
    The plan axes are the real ones here and they fit, so the tall axis is the
    only thing that can speak."""
    d = three_boards(60.0)
    assert [axis for axis, *_ in bp.cavity_overruns(d)] == ["tall"]
    assert bp.cavity_problems(d) == []
    assert any("OVER by 4.0" in p for p in bp.stack_height(d).problems)


def test_rules_fails_on_a_cavity_the_measured_box_cannot_hold(measured_cavity):
    from tools import rules
    d = three_boards()
    assert not any(e.startswith("HT-CAVITY") for e in rules.check_all(d))
    measured_cavity(250.0, 61.0)
    cavity = [e for e in rules.check_all(d) if e.startswith("HT-CAVITY: ")]
    assert len(cavity) == 2 and "cavity along" in cavity[0]


def test_the_cavity_is_measured_and_the_enclosure_is_not():
    assert bp.CAVITY_MEASURED is True, "M18: measured by the owner, 2026-09-20"
    assert bp.ENCLOSURE_DECIDED is False, "flip only when the enclosure is chosen"
    # The stack still calls itself provisional -- on the ALLOWANCES now, not on
    # the cavity -- even when every height is confirmed:
    stack = bp.stack_height(three_boards())
    assert stack.load_bearing == () and stack.provisional


def test_no_ceiling_is_typed_anywhere():
    assert not hasattr(bp, "LAYER_CEILING_MM")
    assert not any("CEILING" in name for name in dir(bp))


# --- the derivation, by hand -------------------------------------------------------
def test_three_board_stack_by_hand():
    stack = bp.stack_height(three_boards())
    # FLOOR->POWER    the brick's seat, 0.5 pad + 12.7, over both the
    #                 0.5 liner + 1.5 tails + 1.0 path and the 3.0 boss = 13.2
    # POWER->OUTPUTS  14.0 + 1.0 + 1.5 tails under OUTPUTS             = 16.5
    # OUTPUTS->LOGIC   7.0 + 1.0 + 1.5                                 =  9.5
    # LOGIC->LID       7.0 + 1.0                                       =  8.0
    assert [g.gap_mm for g in stack.gaps] == pytest.approx([13.2, 16.5, 9.5, 8.0])
    assert stack.total_mm == pytest.approx(47.2 + 3 * 1.6)           # 52.0
    assert stack.margin_mm == pytest.approx(42.0)                    # 94.0 - 52.0
    assert stack.ok


def test_a_height_changed_in_the_design_moves_the_stack_by_that_much():
    low, high = bp.stack_height(three_boards(14.0)), bp.stack_height(three_boards(22.0))
    assert high.total_mm - low.total_mm == pytest.approx(8.0)
    assert gap(high, "POWER", "OUTPUTS").top_ref == "L101"


def test_an_over_height_stack_fails_and_says_by_how_much():
    stack = bp.stack_height(three_boards(60.0))         # 52.0 + 46.0 = 98.0 of 94
    assert not stack.ok
    assert any("OVER by 4.0" in p for p in stack.problems)
    assert bp.stack_problems(three_boards(60.0)) == list(stack.problems)


def test_connectors_count_as_tall_things():
    # Connector heights carry most of the stack's margin, so they have to count.
    d = three_boards()
    taller = d.replace_connector("J401", height_mm=12.0)
    assert bp.stack_height(taller).total_mm - bp.stack_height(d).total_mm == \
        pytest.approx(5.0)
    assert gap(bp.stack_height(taller), "LOGIC", "LID").top_ref == "J401"


def test_solder_tails_are_charged_only_under_through_hole_boards():
    smd = Design(parts=(part("R1", "POWER", 1.0), part("R2", "OUTPUTS", 1.0)))
    tht = smd.replace_part("R2", package="DIP-14")
    order = ("POWER", "OUTPUTS")
    assert gap(bp.stack_height(smd, order), "POWER", "OUTPUTS").gap_mm == pytest.approx(2.0)
    assert gap(bp.stack_height(tht, order), "POWER", "OUTPUTS").gap_mm == pytest.approx(3.5)
    assert gap(bp.stack_height(tht, order), "POWER", "OUTPUTS").hang_ref == "solder tails"


def test_tails_under_the_upper_board_are_charged_to_the_gap():
    # Tails budgeted at 0 land on whatever stands below: every OUTPUTS harness
    # pin on the choke under it. 16.5 - 14.0 = the clearance plus the tails.
    g = gap(bp.stack_height(three_boards()), "POWER", "OUTPUTS")
    assert g.gap_mm - 14.0 == pytest.approx(1.0 + 1.5)


# --- bottom-side parts (BD-14) -----------------------------------------------------
def test_a_bottom_side_part_shares_the_gap_and_gets_a_keep_out():
    d = three_boards(22.0).with_part(part("C201", "OUTPUTS", 18.0, side="bottom"))
    stack = bp.stack_height(d)
    g = gap(stack, "POWER", "OUTPUTS")
    assert g.gap_mm == pytest.approx(24.5)          # still set by L101, not 22 + 18
    note = next(n for n in stack.notes if n.startswith("keep-out: C201"))
    assert "5.5 mm" in note and "L101" in note      # 24.5 - 18.0 - 1.0


def test_a_bottom_side_part_deeper_than_everything_else_sets_the_gap():
    d = three_boards(14.0).with_part(part("C201", "OUTPUTS", 18.0, side="bottom"))
    g = gap(bp.stack_height(d), "POWER", "OUTPUTS")
    assert (g.gap_mm, g.hang_ref) == (pytest.approx(19.0), "C201")   # 18.0 + 1.0


def test_a_bottom_side_part_on_the_bottom_board_lifts_it_off_the_floor():
    # With no brick to seat on, the liner path sets it: 0.5 + 9.0 + 1.0 = 10.5.
    d = three_boards().without_part("U201") \
        .with_part(part("C101", "POWER", 9.0, side="bottom"))
    assert gap(bp.stack_height(d), "FLOOR", "POWER").gap_mm == pytest.approx(10.5)
    # With the brick there, 10.5 hides under its 13.2 seat and changes nothing.
    seated = three_boards().with_part(part("C101", "POWER", 9.0, side="bottom"))
    assert gap(bp.stack_height(seated), "FLOOR", "POWER").gap_mm == pytest.approx(13.2)
    assert bp.stack_height(seated).ok


# --- leads and the floor liner (MX-7, HV-1) ----------------------------------------
def test_pins_too_stiff_to_trim_are_charged_at_the_drawing_length():
    """The brick's pins are 5 ± 0.5: 5.5 - 1.6 = 3.9 mm of pin standing THROUGH
    POWER, where a trimmed lead would leave 1.5. With a 2.0 mm choke over it the
    pins are the tallest thing in the gap: 3.9 + 1.0 + 1.5 tails = 6.4."""
    d = three_boards(2.0).replace_part("U201", lead_mm=5.5)
    g = gap(bp.stack_height(d), "POWER", "OUTPUTS")
    assert (g.top_mm, g.top_ref) == (pytest.approx(3.9), "U201 pins")
    assert g.gap_mm == pytest.approx(3.9 + 1.0 + 1.5)


def test_a_connector_under_its_board_sends_its_pins_up_through_it():
    """An upper inter-board half's pins come out on top of its board."""
    d = three_boards()
    d = replace(d, connectors=d.connectors + (replace(
        conn("J311", "OUTPUTS", 2.5), side="bottom", lead_mm=6.1, leaves_box=False),))
    g = gap(bp.stack_height(d), "OUTPUTS", "LOGIC")
    assert (g.top_mm, g.top_ref) == (pytest.approx(7.0), "J301")   # 4.5 pins < 7.0
    tall = d.replace_connector("J311", lead_mm=10.6)                 # 9.0 up
    assert gap(bp.stack_height(tall), "OUTPUTS", "LOGIC").top_ref == "J311 pins"


def test_84v_pins_stand_off_an_insulated_floor():
    """POWER's pins face the grounded metal floor through the liner. Taken with
    no brick on the board, so the liner path is what sets the gap."""
    d = three_boards().without_part("U201").replace_part("L101", lead_mm=6.0)  # 4.4 down
    assert gap(bp.stack_height(d), "FLOOR", "POWER").gap_mm == pytest.approx(
        bp.FLOOR_LINER_T + 4.4 + 1.0)
    assert bp.FLOOR_LINER_T > 0


# --- the brick's floor seat --------------------------------------------------------
def test_the_floor_seat_sets_the_bottom_board_and_says_so():
    """0.5 pad + 12.7 brick = 13.2, against 0.5 liner + 1.5 tails + 1.0 = 3.0."""
    g = gap(bp.stack_height(three_boards()), "FLOOR", "POWER")
    assert (g.seat_mm, g.seat_ref) == (pytest.approx(13.2), "U201")
    assert g.seat_sets_gap and g.gap_mm == pytest.approx(13.2)
    assert "U201" in bp.stack_height(three_boards()).gaps[0].set_by


def test_nothing_beside_the_brick_may_hang_deeper_than_its_seat():
    """The baseplate reaches the floor only at 13.2 mm. Beside it a part has the
    0.5 liner under it and 1.0 of clearance over it, so 11.7 is the deepest that
    still fits (0.5 + 11.7 + 1.0 = 13.2); a 13.0 mm part is deeper than the
    brick itself and holds it off its heatsink."""
    ok = three_boards().with_part(part("U202", "POWER", 11.7, side="bottom"))
    bad = three_boards().with_part(part("U202", "POWER", 13.0, side="bottom"))
    assert bp.stack_height(ok).ok
    assert gap(bp.stack_height(ok), "FLOOR", "POWER").gap_mm == pytest.approx(13.2)
    problems = bp.stack_height(bad).problems
    assert any("U201" in p and "U202" in p and "bolt to the floor" in p
               for p in problems)
    assert not bp.stack_height(bad).ok


def test_the_seat_has_to_be_on_the_bottom_board_underside():
    """Flipped to POWER's top the stack still derives, and comes out 1.2 mm
    SHORTER (the 13.2 mm seat gap collapses to the 3.0 mm boss, and 12.7 mm of
    brick moves into a gap the 14.0 mm choke already sets) -- an arrangement
    that reads as an improvement while the brick has nothing to cool it."""
    flipped = three_boards().replace_part("U201", side="top")
    assert bp.stack_height(flipped).total_mm < bp.stack_height(three_boards()).total_mm
    assert any(p.startswith("seat: U201 sits on POWER top") and "heatsink" in p
               for p in bp.stack_height(flipped).problems)
    # ...and a design that does not carry the part says nothing either way.
    assert bp.stack_height(three_boards().without_part("U201")).ok


def test_a_stiff_lead_beside_the_brick_lifts_it_off_the_floor_too():
    """A tail stands on the liner like a part does: a 15 mm lead leaves
    15.0 - 1.6 = 13.4 mm through the board, and 0.5 + 13.4 + 1.0 > 13.2."""
    stiff = three_boards().replace_part("L101", lead_mm=15.0)
    assert any("L101 pins" in p and "bolt to the floor" in p
               for p in bp.stack_height(stiff).problems)


# --- inter-board connectors --------------------------------------------------------
def with_connectors(design, *more):
    return replace(design, connectors=design.connectors + more)


def linked(lower_h, upper_h, confirmed):
    """`three_boards` with a 5.0 mm OUTPUTS connector and a STACK pair OUTPUTS<->LOGIC."""
    return with_connectors(
        three_boards().replace_connector("J301", height_mm=5.0),
        conn("J308", "OUTPUTS", lower_h, confirmed=confirmed, interface="STACK"),
        conn("J406", "LOGIC", upper_h, confirmed=confirmed, interface="STACK"))


def test_an_unconfirmed_connector_pair_only_widens_the_gap():
    # OUTPUTS->LOGIC parts need 5.0 + 1.0 + 1.5 = 7.5
    short = bp.stack_height(linked(3.0, 2.5, confirmed=False))     # mates at 5.5
    tall = bp.stack_height(linked(8.5, 2.54, confirmed=False))     # mates at 11.04
    assert gap(short, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(7.5)
    assert gap(tall, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(11.04)
    # Too short to reach: said so, and it is the PARTS that set the gap.
    assert any("J308+J406 mates at 5.5 mm (unconfirmed) and the gap is 7.5 mm" in n
               for n in short.notes)
    assert not {"J308", "J406"} & set(short.load_bearing)
    # Tall enough to push the boards apart: now the guess is load-bearing.
    assert {"J308", "J406"} <= set(tall.load_bearing)
    assert short.ok and tall.ok


def test_two_unconfirmed_pairs_across_one_gap_are_told_to_agree():
    d = with_connectors(
        linked(3.0, 2.5, confirmed=False),                       # STACK at 5.5
        conn("J307", "OUTPUTS", 8.5, confirmed=False, interface="PWR-LOGIC"),
        conn("J407", "LOGIC", 2.5, confirmed=False, interface="PWR-LOGIC"))  # 11.0
    stack = bp.stack_height(d)
    assert gap(stack, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(11.0)
    assert any("J308+J406 mates at 5.5 mm" in n and "gap is 11.0 mm" in n
               for n in stack.notes)
    assert set(stack.load_bearing) == {"J307", "J407"}


def test_a_confirmed_connector_pair_is_the_gap_and_the_parts_must_fit_it():
    fits = bp.stack_height(linked(8.5, 2.54, confirmed=True))
    assert gap(fits, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(11.04) and fits.ok
    tight = bp.stack_height(linked(3.0, 2.5, confirmed=True))      # 5.5 < 7.5
    assert any("J301 stands 5.0 mm on OUTPUTS" in p for p in tight.problems)


def test_a_bottom_side_part_taller_than_the_gap_below_it_fails():
    d = linked(8.5, 2.54, confirmed=True).with_part(
        part("C450", "LOGIC", 12.0, side="bottom"))                # 12 + 1 > 11.04
    problems = bp.stack_height(d).problems
    assert any("C450 hangs 12.0 mm under LOGIC" in p for p in problems)


def test_two_chosen_pairs_cannot_disagree_about_one_gap():
    d = with_connectors(
        linked(8.5, 2.54, confirmed=True),
        conn("J307", "OUTPUTS", 6.0, interface="PWR-LOGIC"),
        conn("J407", "LOGIC", 2.0, interface="PWR-LOGIC"))
    assert any("cannot be two heights" in p for p in bp.stack_height(d).problems)


def test_the_middle_connector_of_a_three_board_bus_is_counted_once():
    # A MATED bus over POWER -> OUTPUTS -> LOGIC. J307 is ONE body on OUTPUTS.
    # Summing it into the gap below as well would invent a 17 mm "mated height"
    # out of two sockets that do not mate with each other.
    d = with_connectors(
        three_boards(),
        conn("J202", "POWER", 8.5, confirmed=False, interface="PWR-LOGIC"),
        conn("J307", "OUTPUTS", 8.5, confirmed=False, interface="PWR-LOGIC"),
        conn("J407", "LOGIC", 2.5, confirmed=False, interface="PWR-LOGIC"))
    stack = bp.stack_height(d)
    assert gap(stack, "POWER", "OUTPUTS").pairs == ()
    assert [p.refs for p in gap(stack, "OUTPUTS", "LOGIC").pairs] == ["J307+J407"]
    assert gap(stack, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(11.0)
    assert any(n.startswith("J307 (PWR-LOGIC) is the middle") for n in stack.notes)


def test_a_cabled_crossing_is_not_a_pair_and_its_halves_are_ordinary_bodies():
    """⭐ THE DIFFERENCE IO-20 MADE, as a checked property. The same two
    connectors, the same heights, the same boards -- declared a mated PAIR they
    are one 11.0 mm assembly that IS the gap and stands in nothing; declared a
    CABLE (model.CROSSING) they are two bodies, each cleared by CLEARANCE in
    the gap above its own face.

    ⛔ WHAT THE OLD MODEL HID. The lower half here stands 8.5 mm on OUTPUTS,
    under a gap the parts only need 7.5 mm of: as a pair it was exempt from
    being a thing standing in a gap at all, so the collision did not exist. It
    is the same exemption that had J311's 10.9 mm posts sitting 0.14 mm under
    LOGIC on the real netlist without a word from any gate."""
    cabled = with_connectors(
        three_boards().replace_connector("J301", height_mm=5.0),
        conn("J311", "OUTPUTS", 8.5, interface="PWR-OUT"),
        conn("J407", "LOGIC", 2.5, interface="PWR-OUT"))
    stack = bp.stack_height(cabled)
    assert gap(stack, "OUTPUTS", "LOGIC").pairs == ()           # no pair at all
    assert not any("mates at" in n for n in stack.notes)        # ...so no note
    # 8.5 standing on OUTPUTS + 1.0 clearance + 1.5 tails under LOGIC:
    assert gap(stack, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(11.0)
    assert gap(stack, "OUTPUTS", "LOGIC").top_ref == "J311"
    # ...and the mated pair of the same two bodies is the other answer entirely.
    paired = bp.stack_height(linked(8.5, 2.5, confirmed=True))
    assert [p.refs for p in gap(paired, "OUTPUTS", "LOGIC").pairs] == ["J308+J406"]
    assert gap(paired, "OUTPUTS", "LOGIC").top_ref == "J301"    # 5.0, not 8.5


# --- standoffs: the third kind of term ---------------------------------------
# ⭐ A part STANDS IN a gap and is cleared by CLEARANCE. A mated pair's bodies
# ARE the gap. A STANDOFF DEFINES one: the boards sit exactly where the pillar
# puts them, and nothing is added to it. Before IO-20's Task 4 `board_params`
# had only the first two, so `netlist.STANDOFFS` could not be read at all --
# entered as parts the 30.0 mm posts would have derived a 31.0 mm gap, and the
# 11.0 mm nylon one a 12.0 mm gap under an 11.04 mm connector stop.
def standoff(name="M3X30", h=20.0, between=("POWER", "OUTPUTS"),
             seating="sets", qty=4):
    return Standoff(name, "C0", qty, h, between, seating, "a test fixture")


def with_standoffs(design, *more):
    return replace(design, standoffs=design.standoffs + more)


def restand(design, name, **changes):
    """The real design with one of its standoffs altered -- the mutation
    fixture for everything below that runs on `netlist.current()`."""
    return replace(design, standoffs=tuple(
        replace(s, **changes) if s.name == name else s for s in design.standoffs))


def test_a_standoff_defines_the_gap_and_the_parts_do_not():
    """three_boards' POWER->OUTPUTS parts need 14.0 + 1.0 + 1.5 = 16.5 mm and
    would set the gap themselves. A 20.0 mm pillar across it takes over: the
    gap IS 20.0 -- not 16.5, and not 21.0 -- and the stack grows by the 3.5 mm
    difference, 52.0 -> 55.5."""
    plain = bp.stack_height(three_boards())
    posted = bp.stack_height(with_standoffs(three_boards(), standoff(h=20.0)))
    g = gap(posted, "POWER", "OUTPUTS")
    assert (g.need_mm, g.gap_mm) == (pytest.approx(16.5), pytest.approx(20.0))
    assert g.standoff_sets_gap and g.set_by == ("M3X30",)
    assert posted.total_mm - plain.total_mm == pytest.approx(3.5)
    assert posted.ok


def test_a_standoff_shorter_than_what_it_stands_beside_crushes_it():
    """⚠️ THE MUTATION the check was written for, on the fixture and then on the
    real design. A pillar does not compress: shorter than the tallest thing
    between the boards, it is the screws that take up the difference, through
    that part.

    ⛔ Nothing else catches this. `need` stops setting the gap the moment a
    standoff does, so without this check the 16.5 mm the parts want is simply
    absorbed and the tool reports a 15.0 mm gap and a PASS."""
    short = with_standoffs(three_boards(), standoff(h=15.0))
    (crushed,) = [p for p in bp.stack_height(short).problems if p.startswith("gap ")]
    assert "the M3X30 standoff holds the boards 15.00 mm apart" in crushed
    assert "the parts need 16.50 mm" in crushed
    assert "L101 stands 14.0 mm on POWER" in crushed        # ...and names it
    assert "crushes that part when the screws pull up" in crushed
    assert not bp.stack_height(short).ok
    # ...and on the real netlist, where L102 is the 22.0 mm choke on POWER's top
    # that the 30.0 mm brass post has to clear. 20.0 mm of post does not.
    from tools import netlist
    d = netlist.current()
    assert bp.stack_height(d).ok                            # 30.0 mm: it clears
    (real,) = [p for p in bp.stack_height(
        restand(d, "Shuntian M3X30", height_mm=20.0)).problems if p.startswith("gap ")]
    assert "the Shuntian M3X30 standoff holds the boards 20.00 mm apart" in real
    assert "the parts need 25.10 mm" in real
    assert "L102 stands 22.0 mm on POWER" in real


def test_a_gap_setting_standoff_and_a_chosen_pair_cannot_both_be_right():
    """A connector that has to mate across the same gap is the other way a
    pillar can be wrong: 13.0 mm of post under an 11.04 mm pair pulls the
    halves apart, and 9.0 mm would drive them together. Either way one gap has
    been given two lengths, and neither number is the one that was built."""
    for h in (13.0, 9.0):
        d = with_standoffs(linked(8.5, 2.54, confirmed=True),
                           standoff(h=h, between=("OUTPUTS", "LOGIC")))
        (clash,) = [p for p in bp.stack_height(d).problems
                    if "cannot be two lengths" in p]
        assert f"standoff holds the boards {h:.2f} mm apart" in clash
        assert "J308+J406 mates at 11.04 mm" in clash
    # ...and a pillar cut to the pair's own height is no verdict at all.
    agrees = with_standoffs(linked(8.5, 2.54, confirmed=True),
                            standoff(h=11.04, between=("OUTPUTS", "LOGIC")))
    assert bp.stack_height(agrees).ok


def test_a_short_standoff_is_deliberately_short_and_says_so():
    """⭐ THE NYLON TP-11, modelled as what it is. 11.0 specified against the
    11.04 mm stop J308+J406 sets: it is SHORT, with NO shim, and the
    CONNECTORS keep setting the gap. It defines nothing, so the gap is the
    pair's -- and the report says which of the two is in charge, and states
    the window the delivered pieces are selected into: 11.04 - SAME_LENGTH_MM
    = 10.94 up to the 11.04 stop, by hand."""
    from tools import netlist
    d = netlist.current()
    assert not any(s.seating == "shim" for s in d.standoffs), "no shim is booked"
    stack = bp.stack_height(d)
    g = gap(stack, "OUTPUTS", "LOGIC")
    assert g.standoff.name == "HIWA TP-11" and not g.standoff_sets_gap
    assert g.gap_mm == pytest.approx(11.04)                 # the pair's, not 11.0
    note = next(n for n in stack.notes if "HIWA TP-11" in n)
    assert "specified 11.00 mm under the 11.04 mm J307+J407 and J308+J406 set" in note
    assert "deliberately SHORT, so the pairs keep setting it, with NO shim" in note
    assert "MEASURE between 10.94 and 11.04 mm" in note
    assert stack.ok
    # ...and the standoff's own source states the same window and the count
    # ordered for it, so the order list and the stack say one thing.
    assert "between 10.94 and 11.04 mm" in g.standoff.source
    assert g.standoff.qty > 4 and "TWENTY are ordered for the FOUR" in g.standoff.source


def test_a_short_standoff_longer_than_the_gap_un_seats_the_connectors():
    """⚠️ THE MUTATION in the long direction. The TP-11's ±0.5 mm is the whole
    problem: at 11.5 it holds the boards 0.46 mm past the 11.04 mm the
    connectors stop at, and that 0.46 comes straight off their 6.0 mm of
    engagement. Nothing rescues a piece that measures long, which is why every
    delivered piece is measured and the long ones rejected before fitting."""
    from tools import netlist
    d = restand(netlist.current(), "HIWA TP-11", height_mm=11.5)
    (over,) = [p for p in bp.stack_height(d).problems if "HIWA TP-11" in p]
    assert "is 11.50 mm against a 11.04 mm gap" in over
    assert "un-seats them by 0.46 mm of their engagement" in over
    assert not bp.stack_height(d).ok


def test_a_shim_thicker_than_the_shortfall_holds_the_boards_apart():
    """⚠️ THE MUTATION the shim bound was written for (audit C1/H13). The
    HIWA PN-3 (C115937) is a 2.4 mm-thick M3 NUT -- 0.5 is its thread pitch --
    and it was booked as a 0.5 mm shim. Either figure fails here, because ALL a
    shim may take up is the 0.04 mm the TP-11 is short of the 11.04 mm stop:
    at 2.4 it holds the boards 2.36 mm apart, at 0.5 still 0.46 mm, and both
    un-seat the pairs the standoff exists to leave in charge. A check that
    only asked whether A shim existed passed both."""
    from tools import netlist
    d = netlist.current()
    for thick, lift in ((2.4, "2.36"), (0.5, "0.46")):
        nut = Standoff("HIWA PN-3", "C115937", 8, thick, (), "shim", "a nut")
        stack = bp.stack_height(replace(d, standoffs=d.standoffs + (nut,)))
        (over,) = [p for p in stack.problems if "PN-3" in p]
        assert f"the HIWA PN-3 shim is {thick:.2f} mm" in over
        assert "may take up at most the 0.04 mm" in over
        assert f"holds the boards {lift} mm apart" in over
        assert "un-seats J307+J407 and J308+J406" in over
        assert not stack.ok
    # Control: a shim that fits the shortfall is no verdict, and the selection
    # window moves down by what it takes up.
    fits = Standoff("washer", "C0", 4, 0.04, (), "shim", "fits")
    stack = bp.stack_height(replace(d, standoffs=d.standoffs + (fits,)))
    assert stack.ok
    note = next(n for n in stack.notes if "HIWA TP-11" in n)
    assert "shimmed by 0.04 mm" in note and "between 10.90 and 11.00 mm" in note


def test_a_short_standoff_needs_a_chosen_pair_to_be_short_of():
    """"Short" is short OF something: a connector pair whose drawing sets the
    gap. On a gap with no chosen pair the parts set the spacing, and a pillar
    specified under it is what the screws pull the boards down onto. The old
    check accepted "shimmed" anywhere."""
    d = with_standoffs(three_boards(),
                       standoff(name="TP-11", h=11.0, between=("OUTPUTS", "LOGIC"),
                                seating="shimmed"))
    assert gap(bp.stack_height(d), "OUTPUTS", "LOGIC").chosen == ()
    (loose,) = [p for p in bp.stack_height(d).problems if "TP-11" in p]
    assert "specified SHORT (11.00 mm) of a spacing NOTHING sets" in loose
    assert "this gap has no chosen pair" in loose
    assert not bp.stack_height(d).ok
    # ...an UNCONFIRMED pair is not a chosen one either: nothing sets the gap yet.
    d = with_standoffs(linked(8.5, 2.54, confirmed=False),
                       standoff(name="TP-11", h=11.0, between=("OUTPUTS", "LOGIC"),
                                seating="shimmed"))
    assert any("NOTHING sets" in p for p in bp.stack_height(d).problems)
    # ...and with the pair confirmed the same pillar is exactly right.
    d = with_standoffs(linked(8.5, 2.54, confirmed=True),
                       standoff(name="TP-11", h=11.0, between=("OUTPUTS", "LOGIC"),
                                seating="shimmed"))
    assert bp.stack_height(d).ok


def test_a_standoff_that_names_no_gap_of_the_stack_defines_nothing():
    """Structure, checked before any height is derived from it. A pillar
    between POWER and LOGIC is not a gap of this stack; a washer that claims
    two decks is not a pillar at all. Either one silently leaves the gap it was
    meant for derived from whatever else happens to be in it."""
    skipping = with_standoffs(three_boards(),
                              standoff(h=20.0, between=("POWER", "LOGIC")))
    (wrong,) = bp.standoff_problems(skipping)
    assert "stands between ('POWER', 'LOGIC')" in wrong
    assert "not neighbouring decks" in wrong
    assert gap(bp.stack_height(skipping), "POWER", "OUTPUTS").standoff is None
    washer = with_standoffs(three_boards(),
                            standoff(name="PN-3", h=0.5, seating="shim"))
    (misplaced,) = bp.standoff_problems(washer)
    assert "shim names ('POWER', 'OUTPUTS')" in misplaced
    # ...and the real table says neither of those things.
    from tools import netlist
    assert bp.standoff_problems(netlist.current()) == []


def test_one_gap_cannot_be_given_two_standoffs():
    """The taller would silently win, and a gap built to a length nobody chose
    is exactly the failure the whole term exists to stop."""
    d = with_standoffs(three_boards(), standoff(h=20.0),
                       standoff(name="M3X25", h=25.0))
    (twice,) = bp.standoff_problems(d)
    assert "the M3X30 and the M3X25 both stand between POWER and OUTPUTS" in twice
    assert not bp.stack_height(d).ok


def test_the_real_power_to_outputs_gap_is_the_brass_post():
    """⭐ The whole point of IO-20's Task 4, on the real netlist: no connector
    spans POWER -> OUTPUTS any more, so the M3x30 posts set it. 30.0 mm, over a
    25.10 mm the obstructions need, and `set_by` names the post rather than a
    part -- which is what `board_fit`'s HEIGHT block prints."""
    from tools import netlist
    g = gap(bp.stack_height(netlist.current()), "POWER", "OUTPUTS")
    assert g.pairs == ()                                    # the cables are gone
    assert g.standoff.name == "Shuntian M3X30" and g.standoff_sets_gap
    assert (g.gap_mm, g.need_mm) == (pytest.approx(30.0), pytest.approx(25.10))
    assert g.set_by == ("Shuntian M3X30",)


# --- heights nobody has read --------------------------------------------------------
def test_every_unconfirmed_height_is_listed_and_the_load_bearing_ones_named():
    d = three_boards().replace_part("L101", height_confirmed=False) \
        .with_part(part("R101", "POWER", 0.6, confirmed=False))
    stack = bp.stack_height(d)
    assert [r[0] for r in stack.unconfirmed] == ["L101", "R101"]
    assert stack.load_bearing == ("L101",)
    assert stack.ok and stack.provisional        # reported, not failed


@pytest.mark.parametrize("bad", [math.nan, -1.0, None])
def test_an_unknown_height_is_a_failure_not_a_short_part(bad):
    """The model refuses it at construction (tests/test_model.py), so the
    stack is never derived from a design carrying one."""
    with pytest.raises(ValueError, match="L101: height_mm="):
        three_boards().replace_part("L101", height_mm=bad)


def test_a_dnp_part_still_needs_its_room():
    d = three_boards().with_part(part("D406", "OUTPUTS", 9.0, dnp=True))
    assert gap(bp.stack_height(d), "OUTPUTS", "LOGIC").top_ref == "D406"


# --- the connector face (IO-6) ------------------------------------------------
def test_the_face_room_is_the_deepest_plug_and_its_bend():
    from tools import netlist
    d = netlist.current()
    deepest = max(c.overhang_mm for c in d.connectors if c.leaves_box and not c.dnp)
    assert bp.face_room(d) == pytest.approx(deepest + bp.WIRE_BEND)


def test_the_typed_face_room_matches_the_netlist():
    """FACE_ROOM is typed once so the outline and the budgets can use it as a
    constant; this is what keeps it honest. Today the deepest fitted plug is
    J101's Kefa 7.62, 9.65 mm past its header: 9.65 + 10.0 bend = 19.65."""
    from tools import netlist
    assert bp.FACE_ROOM == pytest.approx(19.65)
    assert bp.FACE_ROOM == pytest.approx(bp.face_room(netlist.current()))


def test_an_unfitted_plug_does_not_set_the_face_room():
    """A DNP terminal is laid out but nothing is plugged into it, so no plug of
    its stands in front of the face. J405 is parked and DNP: a 40 mm overhang on
    it must not move the answer; on a fitted one it would."""
    from tools import netlist
    d = netlist.current()
    assert bp.face_room(d.replace_connector("J405", overhang_mm=40.0)) \
        == pytest.approx(bp.FACE_ROOM)
    assert bp.face_room(d.replace_connector("J101", overhang_mm=40.0)) \
        == pytest.approx(50.0)


def test_a_harness_header_hanging_under_outputs_sets_the_gap_below_it():
    from tools import netlist
    d = netlist.current()
    tall = d.replace_connector("J314", height_mm=20.0, height_confirmed=True)
    gap = next(g for g in bp.layer_gaps(tall) if (g.below, g.above) == ("POWER", "OUTPUTS"))
    assert gap.hang_mm >= 20.0 and gap.gap_mm >= 20.0 + bp.CLEARANCE


def test_a_connector_under_a_board_gets_a_keep_out_like_a_part():
    """BD-14 on connectors, not just parts. J311 hangs 10.9 mm under OUTPUTS
    into the POWER->OUTPUTS gap, which the M3x30 standoffs set to 30.0 mm. So
    30.0 - 10.9 - 1.0 = 18.1 mm is the tallest thing that may stand under it,
    and the 22.0 mm chokes do not qualify. J312's 8.6 mm leaves 20.4, which
    they still do not.

    ⚠️ J314 no longer earns one, and the arithmetic is the reason rather than a
    change of heart: 30.0 - 7.0 - 1.0 = 22.0, and L101/L102 are 22.0 exactly,
    so the terminal and the chokes clear each other by precisely CLEARANCE.
    That note existed against the 25.1 mm gap the obstructions used to set; the
    standoff bought the 4.9 mm that retired it."""
    from tools import netlist
    stack = bp.stack_height(netlist.current())
    note = next(n for n in stack.notes if n.startswith("keep-out: J311"))
    assert "hangs 10.9 mm under OUTPUTS" in note
    assert "taller than 18.1 mm" in note and "L101" in note and "L102" in note
    assert any(n.startswith("keep-out: J312") and "taller than 20.4 mm" in n
               for n in stack.notes)
    assert not any(n.startswith("keep-out: J314") for n in stack.notes)


def test_only_a_mated_halfs_keep_out_is_a_note_about_nothing():
    """⭐ The exemption is for a MATED pair alone, and the two kinds are on the
    real netlist to tell apart. Each half of a pair faces its own other half by
    construction and their mated height IS the gap, so J406 and J407 hanging
    under LOGIC would be two notes about nothing. A CABLED half faces no mate:
    it is a body hanging into a gap like any other, it can sit over a choke,
    and it gets the note -- which is what J311 and J312 above are."""
    from tools import netlist
    stack = bp.stack_height(netlist.current())
    assert not [n for n in stack.notes
                if any(n.startswith(f"keep-out: {r}") for r in ("J406", "J407"))]
    assert [n for n in stack.notes
            if any(n.startswith(f"keep-out: {r}") for r in ("J311", "J312"))]


# --- the envelope verdict is provisional only while the CAVITY is a guess ----
# ⚠️ Built on `three_boards(60.0)`, NOT on the real netlist. These three used to
# derive their overrun from `netlist.current()` and skip when it fitted, so the
# wording of the verdict went untested exactly when the design was healthy.
# 52.0 mm of stack with the 14.0 mm choke, so 60.0 makes it 98.0 against the
# 94.0 the measured cavity leaves: OVER by 4.0 either way.
def test_an_overrun_of_the_measured_envelope_is_a_failure():
    """The real flags. M18 is measured, so this is a verdict and not a note --
    and the enclosure being undecided does not soften it."""
    assert bp.envelope_is_binding()
    tall = bp.stack_height(three_boards(60.0))
    assert any("OVER by 4.0" in p for p in tall.problems)
    assert not tall.envelope_verdicts
    assert not tall.ok


def test_the_same_overrun_could_not_fail_a_cavity_nobody_had_measured(
        unmeasured_cavity):
    """The world before M18, which is the only thing `envelope_verdicts` is for:
    an overrun reported loudly and unable to fail the design."""
    assert not bp.envelope_is_binding()
    tall = bp.stack_height(three_boards(60.0))
    assert tall.envelope_verdicts, "an overrun must never vanish silently"
    assert "OVER by 4.0" in tall.envelope_verdicts[0]
    assert "ESTIMATED envelope" in tall.envelope_verdicts[0]
    assert not any("OVER by" in p for p in tall.problems)
    assert tall.ok                       # reported loudly, and not a failure


def test_rules_relay_the_provisional_verdict_as_a_warning(unmeasured_cavity):
    from tools import rules
    d = three_boards(60.0)
    assert bp.stack_height(d).envelope_verdicts
    assert any(w.startswith("HT-STACK-PROVISIONAL") and "OVER by 4.0" in w
               for w in rules.warnings(d))
    assert not any(e.startswith("HT-STACK") for e in rules.check_all(d))


def test_rules_fail_on_that_same_overrun_now_the_cavity_is_measured():
    """...and the other side of it: with the real flags the warning becomes an
    error, so a stack too tall for the measured box cannot ride out as a note."""
    from tools import rules
    d = three_boards(60.0)
    assert not bp.stack_height(d).envelope_verdicts
    assert not any(w.startswith("HT-STACK-PROVISIONAL") for w in rules.warnings(d))
    assert any(e.startswith("HT-STACK") and "OVER by 4.0" in e
               for e in rules.check_all(d))
