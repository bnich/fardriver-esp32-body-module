import os

import pytest

# The suite is hermetic: no library footprint is fetched.  Tests that bind
# footprints hand emit_board a FakeLibrary instead.
os.environ["REVV1_NO_LIBRARY"] = "1"


@pytest.fixture
def binding_envelope(monkeypatch):
    """The envelope as a FACT: cavity measured and enclosure chosen.

    While either is still an estimate, a stack that overruns is reported as
    provisional and cannot fail the design. Tests that prove an overrun FAILS
    must therefore say which world they are in.
    """
    from tools import board_params
    monkeypatch.setattr(board_params, "CAVITY_MEASURED", True)
    monkeypatch.setattr(board_params, "ENCLOSURE_DECIDED", True)


@pytest.fixture
def measured_cavity(monkeypatch):
    """`measured_cavity(along, across)` -- the cavity as M18 MEASURED it, with
    the enclosure chosen, so the envelope is a fact and a design that will not
    go in the box is a failure.

    ⛔ A FIXTURE. The real `CAVITY_MEASURED` is honestly False and stays False
    until the owner measures the bike; nothing in the suite flips it.

    ⚠️ The height is not settable here on purpose: `stack_height`'s `avail_mm`
    default binds AVAIL_H at import, so a CAVITY_H typed after import would not
    reach it. The height path has its own proof (`binding_envelope`); this one
    is for the two PLAN axes.
    """
    def measure(along: float, across: float):
        from tools import board_params
        monkeypatch.setattr(board_params, "CAVITY_L", along)
        monkeypatch.setattr(board_params, "CAVITY_W", across)
        monkeypatch.setattr(board_params, "CAVITY_MEASURED", True)
        monkeypatch.setattr(board_params, "ENCLOSURE_DECIDED", True)
    return measure
