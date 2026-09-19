"""The part JLC places is the part the rules checked (review CK-5).

Rules read the netlist MPN; JLC places the LCSC code. A code changed in a
table -- to the 65 °C ESP32-S3-WROOM-1U-N8R8, whose PSRAM takes IO35-37, or
to the Diodes BSS127S-7, whose threshold sits above D13_EN -- passes every
rule. tests/fixtures/lcsc.json records what LCSC says each code is; it is
checked here offline, and against the live library where it can be reached.
"""
import os

import pytest

from tools import lcsc_fixture, netlist


@pytest.fixture(scope="module")
def fixture():
    return lcsc_fixture.load()


def test_every_code_is_the_part_its_table_names_and_the_rules_checked(fixture):
    assert lcsc_fixture.check(netlist.current(), fixture) == []


def test_a_code_swapped_for_the_65_c_esp32_is_caught(fixture):
    rec = {"C2980300": {"mpn": "ESP32-S3-WROOM-1U-N8R8", "manufacturer": "Espressif",
                        "package": "SMD", "symbol_pins": None}}
    errs = lcsc_fixture.check(netlist.current(), {**fixture, **rec},
                              catalogue={"C2980300": "Espressif ESP32-S3-WROOM-1U-N8"},
                              terminals={})
    assert any("C2980300 is ESP32-S3-WROOM-1U-N8R8" in e for e in errs)


def test_a_code_swapped_for_the_forbidden_bss127s_is_caught(fixture):
    d = netlist.current()
    q = next(p for p in d.parts if p.mpn == "BSS127")
    bad = d.replace_part(q.refdes, lcsc="C154890")
    rec = {"C154890": {"mpn": "BSS127S-7", "manufacturer": "DIODES",
                       "package": "SOT-23", "symbol_pins": None}}
    errs = lcsc_fixture.check(bad, {**fixture, **rec})
    assert any(f"{q.refdes}: C154890 is ordered from no table" in e for e in errs)
    # ...and changed in the table itself, the record contradicts the table:
    errs = lcsc_fixture.check(d, {**fixture, **rec}, terminals={},
                              catalogue={"C154890": "Infineon BSS127H6327XTSA2"})
    assert any("C154890 is BSS127S-7" in e for e in errs)


def test_an_unrecorded_code_is_not_waved_through(fixture):
    d = netlist.current()
    bad = d.replace_part("R401", lcsc="C99999999")
    assert any("C99999999: no record" in e for e in lcsc_fixture.check(bad, fixture))


def test_the_fixture_is_what_the_library_says_today(fixture):
    """A fixture nobody refreshes would pin a stale answer."""
    if os.environ.get("PADMAP_OFFLINE"):
        pytest.skip("PADMAP_OFFLINE set")
    svc = lcsc_fixture.service()
    if svc is None:
        pytest.skip("~/tools/lcsc-search is not on this machine")
    for code, rec in fixture.items():
        live = lcsc_fixture.record(svc, code)
        assert (live["mpn"], live["symbol_pins"]) == (rec["mpn"], rec["symbol_pins"]), code
