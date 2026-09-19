"""Which footprint pad each netlist pin lands on.

The symbol's pins carry the netlist's names (A/K, G/D/S, VS, GPA0); a footprint's
pads carry numbers.  EasyEDA joins them by matching the two, so each footprint's
pads are renamed to the pins they carry.  A wrong entry here wires a transistor
backwards on a board that passes every other check, so the tables are typed
from the datasheets and checked two ways: they must cover every pin of every
fitted item, and -- where this machine can reach EasyEDA's library -- they must
agree with the library symbol's own pin numbers and names.
"""
import json
import os
from pathlib import Path

import pytest

from tools import netlist, padmap


@pytest.fixture(scope="module")
def d():
    return netlist.current()


def _fitted(d):
    return [p for p in d.parts if not p.dnp] + list(d.connectors)


def test_every_fitted_item_with_a_footprint_has_a_map_covering_every_pin(d):
    for x in _fitted(d):
        m = padmap.pad_map(x)
        pins = set(padmap.pins_of(x))
        landed = {pin for pin in m.values() if pin is not None}
        assert pins <= landed, f"{x.refdes}: pins with no pad: {sorted(pins - landed)}"
        extra = landed - pins - set(getattr(x, "nc", ()))
        assert not extra, f"{x.refdes}: pads name pins it does not have: {sorted(extra)}"


@pytest.mark.parametrize("mpn,pad,pin", [
    ("AO3400A", "1", "G"), ("AO3400A", "2", "S"), ("AO3400A", "3", "D"),
    ("BSS127", "3", "D"), ("IXTA26P20P-TRL", "2", "D"), ("IXTA26P20P-TRL", "3", "S"),
    ("SS14", "1", "K"), ("SMCJ90A", "2", "A"),
])
def test_the_pins_a_reversal_would_hurt(d, mpn, pad, pin):
    part = next(p for p in d.parts if p.mpn == mpn)
    assert padmap.pad_map(part)[pad] == pin


def test_the_wroom_matches_the_pads_its_source_cites(d):
    """netlist.py U401: GND = pads 1 and 40, EPAD = 41, IO43 = 37, IO44 = 36."""
    m = padmap.pad_map(d.part("U401"))
    assert (m["1"], m["40"], m["41"], m["37"], m["36"]) == ("GND", "GND", "EPAD", "IO43", "IO44")


def test_every_exposed_pad_is_on_ground(d):
    """The library check accepts a library 'GND' for our EPAD/PAD; that is
    only sound while every exposed pad really is on GND."""
    for p in d.parts:
        for pin in ("EPAD", "PAD"):
            if pin in p.pins:
                net = d.net_of(p.refdes, pin)
                assert net is not None and net.name == "GND", f"{p.refdes}.{pin} is on {net}"


def test_the_tlv767_matches_its_source(d):
    """netlist.py U405: OUT 1, SNS 2, NC 3 and 7, GND 4 and 6, EN 5, IN 8, pad."""
    m = padmap.pad_map(d.part("U405"))
    assert [m[str(n)] for n in range(1, 10)] == ["OUT", "SNS", "NC", "GND", "EN", "GND", "NC", "IN", "PAD"]


# --- the independent check: EasyEDA's library symbol --------------------------------
def _library():
    try:
        import sys
        sys.path.insert(0, str(Path.home() / "tools/lcsc-search"))
        from lcsc_search import Service
    except ImportError:
        pytest.skip("~/tools/lcsc-search is not on this machine")
    if os.environ.get("PADMAP_OFFLINE"):
        pytest.skip("PADMAP_OFFLINE set")
    return Service()


def test_every_map_agrees_with_the_library_symbol(d):
    """For each LCSC part, the library symbol's NUMBER -> NAME must agree with
    our table wherever the library names a pin (an unnamed or purely numeric
    library pin carries no information to check)."""
    svc = _library()
    checked = 0
    # Unfitted parts too: their footprint is on the board, waiting to be fitted.
    for x in list(d.parts) + list(d.connectors):
        code = padmap.footprint_source(x)
        if not code:
            continue
        dev = svc.footprint(code)
        if dev is None or not dev.get("symbol_uuid"):
            continue
        doc = svc.document(dev["symbol_uuid"])
        if doc is None:
            continue
        lib = padmap.library_pins(doc["data"])
        m = padmap.pad_map(x)
        for num, name in lib:
            if num not in m or m[num] is None:
                continue
            assert padmap.names_agree(m[num], name, x), (
                f"{x.refdes} ({code}) pad {num}: our {m[num]!r}, library {name!r}")
        checked += 1
    assert checked > 30
