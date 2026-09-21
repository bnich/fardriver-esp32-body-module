import os

import pytest

# The suite is hermetic: no library footprint is fetched.  Tests that bind
# footprints hand emit_board a FakeLibrary instead.
os.environ["REVV1_NO_LIBRARY"] = "1"


@pytest.fixture
def binding_envelope(monkeypatch):
    """The envelope as a settled FACT: cavity measured AND enclosure chosen.

    ⚠️ Since M18 (2026-09-20) the gate answers to `CAVITY_MEASURED` alone, which
    is really True, so this fixture no longer decides whether an overrun fails.
    What it still does is put the test in the world where the REQUIREMENT is
    final too, so no allowance caveat colours the wording it reads.
    """
    from tools import board_params
    monkeypatch.setattr(board_params, "CAVITY_MEASURED", True)
    monkeypatch.setattr(board_params, "ENCLOSURE_DECIDED", True)


@pytest.fixture
def unmeasured_cavity(monkeypatch):
    """The world BEFORE M18: the cavity is a guess, so an overrun is reported
    and cannot fail the design.

    ⛔ A FIXTURE, and the only way that path is now reachable: the real
    `CAVITY_MEASURED` is True. The machinery it exercises is the guard for a
    cavity figure that goes back to being an estimate, and the regression test
    for a tool that once printed an overrun and then "✅ PASS".
    """
    from tools import board_params
    monkeypatch.setattr(board_params, "CAVITY_MEASURED", False)


@pytest.fixture
def measured_cavity(monkeypatch):
    """`measured_cavity(along, across)` -- a cavity OTHER than the one M18
    measured, so a test can drive a design that will not go in the box.

    ⛔ A FIXTURE for the two PLAN axes. The real `CAVITY_L` / `CAVITY_W` are
    260.0 / 70.0, measured by the owner on 2026-09-20, and the real design fits
    inside them; a test that needs a failure has to supply a box that cannot
    hold it.

    It leaves `ENCLOSURE_DECIDED` alone -- False, as it really is -- because the
    verdict does not depend on it (`board_params.envelope_is_binding`), and a
    fixture that flipped it would hide exactly that.

    ⚠️ The height is not settable here on purpose: `stack_height`'s `avail_mm`
    default binds AVAIL_H at import, so a CAVITY_H typed after import would not
    reach it. The height path has its own proof; this one is for the plan axes.
    """
    def measure(along: float, across: float):
        from tools import board_params
        monkeypatch.setattr(board_params, "CAVITY_L", along)
        monkeypatch.setattr(board_params, "CAVITY_W", across)
        monkeypatch.setattr(board_params, "CAVITY_MEASURED", True)
    return measure


@pytest.fixture
def board_width(monkeypatch):
    """`board_width(mm)` -- the design on a board of some other width, with
    `BOARD_AREA` and `CAVITY_REQUIRED_W` moved with it as the module's own
    arithmetic would.

    ⛔ A MUTATION FIXTURE, and the only way to a width other than the 41.84 the
    envelope search chose. It drives two different proofs: a board too WIDE for
    the measured cavity must fail `cavity_problems`, and a board back on the
    40.0 the cabled crossings were left standing on must fail the pack-cliff
    guard -- below the step at 40.0, and above it but inside the millimetre at
    41.0. The real flags (cavity measured, enclosure still undecided) are left
    untouched in all of them.
    """
    def set_width(mm: float):
        from tools import board_params as bp
        monkeypatch.setattr(bp, "BOARD_W", mm)
        monkeypatch.setattr(bp, "BOARD_AREA", mm * bp.BOARD_L)
        monkeypatch.setattr(bp, "CAVITY_REQUIRED_W",
                            mm + 2 * bp.WALL + bp.SIDE_CLEARANCE + bp.FACE_ROOM)
    return set_width


@pytest.fixture
def wider_board(board_width):
    """`wider_board(mm)` -- `board_width` under the name the cavity-gate tests
    read by, where the mutation is always a board too wide for the box."""
    return board_width


@pytest.fixture
def grown_y_caps():
    """`grown_y_caps(mm)` -- the real netlist with `mm` added to the 18.5 mm
    side of C203-C206, the four Y-caps whose paired courtyards MADE the pack
    cliff until IO-20 (18.5 + 2 x COURTYARD = 19.50 across each, and two to a
    shelf was the 39.00 mm step; C207 and J202 pair at 40.84 now).

    ⛔ A MUTATION FIXTURE. It exists to prove the cliff guard is derived from
    the packer and not from a typed width: grow these four past the binding
    pair and the derived step has to move with them. Negative `mm` shrinks them.
    ⚠️ All four, not one: the step is a PAIR of caps sharing a shelf, so one
    grown cap can still pair with an ungrown one and the step moves by half as
    much (18.5 + 0.5 on one cap alone puts it at 39.50, not 40.00).
    """
    def grow(mm: float):
        from tools import netlist
        d = netlist.current()
        for ref in ("C203", "C204", "C205", "C206"):
            w, l = next(p.footprint_mm for p in d.parts if p.refdes == ref)
            d = d.replace_part(ref, footprint_mm=(w, l + mm))
        return d
    return grow


@pytest.fixture
def grown_body():
    """`grown_body(refdes, mm)` -- the real netlist with `mm` added to the
    LONGER side of one body, whichever one the cliff currently answers to.

    ⛔ A MUTATION FIXTURE, and deliberately not tied to a refdes: the pair that
    makes the pack cliff changed with IO-20, and a fixture that names only
    yesterday's pair lets a mutation go on passing while it has stopped moving
    the thing it claims to move.
    """
    def grow(refdes: str, mm: float):
        from tools import netlist
        d = netlist.current()
        w, l = next(p.footprint_mm for p in d.parts if p.refdes == refdes)
        long_side, short = max(w, l), min(w, l)
        return d.replace_part(refdes, footprint_mm=(short, long_side + mm))
    return grow
