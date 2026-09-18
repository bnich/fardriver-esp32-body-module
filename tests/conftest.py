import pytest


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
