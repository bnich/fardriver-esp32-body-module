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
def wider_board(monkeypatch):
    """`wider_board(mm)` -- the design on a board too wide for the measured
    cavity, `CAVITY_REQUIRED_W` moved with it as the module's own arithmetic
    would.

    ⛔ A MUTATION FIXTURE. It exists to prove the cavity gate bites: 39.0 mm
    passes and a board a few millimetres wider must not, with the real flags
    (cavity measured, enclosure still undecided) untouched.
    """
    def widen(mm: float):
        from tools import board_params as bp
        monkeypatch.setattr(bp, "BOARD_W", mm)
        monkeypatch.setattr(bp, "BOARD_AREA", mm * bp.BOARD_L)
        monkeypatch.setattr(bp, "CAVITY_REQUIRED_W",
                            mm + 2 * bp.WALL + bp.SIDE_CLEARANCE + bp.FACE_ROOM)
    return widen
