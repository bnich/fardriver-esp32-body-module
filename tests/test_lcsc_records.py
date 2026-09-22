"""The part JLC places is the part the rules checked (review CK-5).

Rules read the netlist MPN; JLC places the LCSC code. A code changed in a
table -- to the 65 °C ESP32-S3-WROOM-1U-N8R8, whose PSRAM takes IO35-37, or
to the Diodes BSS127S-7, whose threshold sits above D13_EN -- passes every
rule. tests/fixtures/lcsc.json records what LCSC says each code is; it is
checked here offline, and against the live library where it can be reached.

The clone records below are REAL `record()` outputs (LCSC detail, 2026-09-21),
so each test swaps in what LCSC would actually say, not a caricature.
"""
import os

import pytest

from tools import lcsc_fixture, netlist
from tools.model import ConnPin

# Diodes' BSS127S-7: V_GS(th) 4.5 V max, the part CLAUDE.md forbids by name.
BSS127S_7 = {"mpn": "BSS127S-7", "manufacturer": "DIODES", "package": "SOT-23",
             "symbol_pins": None, "footprint": None}
# TECH PUBLIC's TPSMS05T1G: ONE channel, clamping at 14 V, in SOT-23-6 -- named
# after the six-channel 9.8 V onsemi array it would replace on every 3.3 V line.
TPSMS05T1G = {"mpn": "TPSMS05T1G", "manufacturer": "TECH PUBLIC", "package": "SOT-23-6",
              "symbol_pins": None, "footprint": None}
# MDD's SMCJ90A: the same number as Vishay's, from another maker.
MDD_SMCJ90A = {"mpn": "SMCJ90A", "manufacturer": "MDD(Microdiode Semiconductor)",
               "package": "SMC", "symbol_pins": None, "footprint": None}


@pytest.fixture(scope="module")
def fixture():
    return lcsc_fixture.load()


def _swapped(d, mpn: str, code: str, table: str):
    """The design with every `mpn` part ordered as `code`, and the catalogue
    honestly re-tabled to say what `code` is -- the edit a person would make."""
    cat = dict(netlist.lcsc_catalogue())
    old = next(p.lcsc for p in d.parts if p.mpn == mpn)
    cat.pop(old)
    cat[code] = table
    bad = d
    for p in d.parts:
        if p.mpn == mpn:
            bad = bad.replace_part(p.refdes, lcsc=code)
    return bad, cat


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
    """The swap made HONESTLY -- the table re-typed to `Diodes BSS127S-7` --
    while the netlist still checks `BSS127`. Until 2026-09-21 a substring
    test (`BSS127` ⊂ `BSS127S-7`) let it through the gate test above (H21)."""
    d = netlist.current()
    q = next(p for p in d.parts if p.mpn == "BSS127")
    bad, cat = _swapped(d, "BSS127", "C154890", "Diodes BSS127S-7")
    errs = lcsc_fixture.check(bad, {**fixture, "C154890": BSS127S_7}, catalogue=cat)
    assert f"{q.refdes}: the netlist checks BSS127 but C154890 is BSS127S-7" in errs
    # Ordered without a table entry at all:
    errs = lcsc_fixture.check(d.replace_part(q.refdes, lcsc="C154890"),
                              {**fixture, "C154890": BSS127S_7})
    assert any(f"{q.refdes}: C154890 is ordered from no table" in e for e in errs)


def test_a_single_channel_clone_named_after_the_sms05t1g_is_caught(fixture):
    d = netlist.current()
    bad, cat = _swapped(d, "SMS05T1G", "C708742", "TECH PUBLIC TPSMS05T1G")
    errs = lcsc_fixture.check(bad, {**fixture, "C708742": TPSMS05T1G}, catalogue=cat)
    arrays = [p.refdes for p in d.parts if p.mpn == "SMS05T1G"]
    assert len(arrays) >= 10
    for ref in arrays:
        assert f"{ref}: the netlist checks SMS05T1G but C708742 is TPSMS05T1G" in errs
        assert any(e.startswith(f"{ref}: the netlist places a 'SC-74' but C708742 comes "
                                f"in 'SOT-23-6'") for e in errs)


def test_another_makers_smcj90a_is_caught_by_maker(fixture):
    """Same number, same package, another maker, table string left saying
    Vishay: only the maker word tells them apart."""
    d = netlist.current()
    bad, cat = _swapped(d, "SMCJ90A", "C2994079", "Vishay SMCJ90A-E3/57T")
    errs = lcsc_fixture.check(bad, {**fixture, "C2994079": MDD_SMCJ90A}, catalogue=cat)
    assert errs == ["C2994079 is SMCJ90A by 'MDD(Microdiode Semiconductor)', not "
                    "Vishay's as its table 'Vishay SMCJ90A-E3/57T' says -- a "
                    "same-numbered part from another maker is another part"]


def test_a_terminal_from_another_maker_is_caught(fixture):
    """The 3.81 mm family is Kangnex's, whose drawing the height model reads;
    a same-numbered 15EDG header from another maker passes the pattern."""
    rec = {**fixture["C133147"], "manufacturer": "Cixi Kefa Elec"}
    errs = lcsc_fixture.check(netlist.current(), {**fixture, "C133147": rec})
    assert errs == ["C133147 is WJ15EDGRM-3.81-02P-14-00A by 'Cixi Kefa Elec', not "
                    "Kangnex's, whose drawing the height model reads for that pitch"]


def test_a_tenth_contact_on_the_nine_way_pwr_logic_is_caught(fixture):
    """M14: a connector's contact count is held to its part's symbol."""
    d = netlist.current()
    j = d.connector("J307")
    bad = d.replace_connector("J307", pins=j.pins + (ConnPin("10", "GND"),))
    errs = lcsc_fixture.check(bad, fixture)
    assert errs == ["J307: 10 contacts in the netlist, but C22373895 "
                    "(HC-PM254-8.5H-1x9PZ) has 9"]


def test_the_cut_strip_may_be_longer_than_stack_but_not_shorter(fixture):
    d = netlist.current()
    j = d.connector("J406")
    assert j.lcsc in lcsc_fixture.CUT_TO_LENGTH
    assert len(fixture[j.lcsc]["symbol_pins"]) == 80 > len(j.pins) == 58
    too_many = d.replace_connector("J406", pins=j.pins + tuple(
        ConnPin(str(n), "GND") for n in range(59, 82)))
    errs = lcsc_fixture.check(too_many, fixture)
    assert errs == ["J406: 81 contacts cut from C2333, whose strip has 80 (a 2×40 "
                    "strip cut to STACK's 2×29 (netlist._FAB_CONN J406))"]


@pytest.mark.parametrize("ours, theirs, same", [
    ("BSS127", "BSS127H6327XTSA2", True),       # Infineon's reel suffix
    ("BSS127", "BSS127S-7", False),             # Diodes' part, `-7` stripped or not
    ("BSS127S", "BSS127S-7", True),
    ("SMCJ90A", "SMCJ90A-E3/57T", True),
    ("SMCJ90A", "SMCJ90A", True),
    ("SMS05T1G", "TPSMS05T1G", False),          # a prefix on the front
    ("SMS05T1G", "SMS05T1GX", False),           # an unlisted suffix
    ("VY2472M49Y5US6", "VY2472M49Y5US6TV7", True),
    ("SMF6.0A", "SMF6.0CA", False),             # the bidirectional grade
    ("TLV76733DGNR", "TLV76701DGNR", False),
])
def test_part_numbers_compare_by_equality_after_a_listed_suffix(ours, theirs, same):
    assert lcsc_fixture.same_mpn(ours, theirs) is same


@pytest.mark.parametrize("ours, theirs, same", [
    ("Vishay", "VISHAY", True),
    ("MDD", "MDD(Microdiode Semiconductor)", True),
    ("IXYS", "Littelfuse/IXYS", True),
    ("Samsung", "Samsung Electro-Mechanics", True),
    ("Chemi-Con", "NCC", True),
    ("hongjiacheng", "R+O", True),
    ("Kangnex", "KANGNEX", True),
    ("Kefa", "Cixi Kefa Elec", True),
    ("Vishay", "MDD(Microdiode Semiconductor)", False),
    ("onsemi", "TECH PUBLIC", False),
    ("Infineon", "DIODES", False),
    ("TI", "TITAN", False),                     # a word, not a substring
    ("Kangnex", "Cixi Kefa Elec", False),
])
def test_makers_compare_by_word(ours, theirs, same):
    assert lcsc_fixture.same_maker(ours, theirs) is same


@pytest.mark.parametrize("ours, theirs, same", [
    ("SOT-23", "SOT-23", True),
    ("SOT-23", "SOT-23-3", True),
    ("SOT-23", "SOT-23-6", False),
    ("SC-74", "SC-74-6", True),
    ("SC-74", "SOT-23-6", False),
    ("DO-214AB (SMC)", "SMC(DO-214AB)", True),
    ("DO-214AB (SMC)", "SMB(DO-214AA)", False),
    ("0805", "0805", True),
    ("0805", "0603", False),
    ("SOD-123FL", "SOD-123", False),            # the two lands tel_check tells apart
])
def test_packages_compare_by_stated_alias_or_equality(ours, theirs, same):
    assert lcsc_fixture.same_package(ours, theirs) is same


@pytest.mark.parametrize("table, mpn, maker", [
    ("Infineon BSS127H6327XTSA2", "BSS127H6327XTSA2", "Infineon"),
    ("Vishay SMCJ90A-E3/57T", "SMCJ90A", "Vishay"),
    ("SMBJ18A (R+O)", "SMBJ18A", "R+O"),
    ("Samsung CL21B105KBFNNNE, X7R", "CL21B105KBFNNNE", "Samsung"),
    ("BOOMELE(Boom Precision Elec) 2.54-2*40P", "2.54-2*40P", "BOOMELE"),
    ("Hong Cheng HC-PM254-8.5H-1x9PZ", "HC-PM254-8.5H-1x9PZ", "Hong"),
    ("JST B4P(5-3)-VH(LF)(SN)", "B4P(5-3)-VH(LF)(SN)", "JST"),
    ("Diodes BSS127S-7", "BSS127H6327XTSA2", None),   # the table names another part
])
def test_the_maker_word_is_read_out_of_the_table_string(table, mpn, maker):
    assert lcsc_fixture.table_parts(table, mpn)[0] == maker


def test_every_table_string_parses_against_its_record(fixture):
    """Every catalogue string yields a maker word: the parser covers the
    tables' spellings, so a silent None cannot pass as a match."""
    for code, table in netlist.lcsc_catalogue().items():
        maker, token = lcsc_fixture.table_parts(table, fixture[code]["mpn"])
        assert maker and token, (code, table)


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
