"""Reading EasyEDA's exported netlist (.tel) and comparing it with ours.

The fixture copies the export's quirks from real files: CRLF, a trailing ','
that continues a line, a lone ',' line between records, and a quoted value
with a comma of its own.
"""
from tools import tel_check
from tools.model import Design, Net, Part

TEL = ("$PACKAGES\r\n"
       "c0805 ! c0805 ! '100nF 50V' ; C1 \r\n"
       "cap-th_bd8 ! cap-th_bd8 ! '680uF 25V polymer, 20 mΩ' ; ,\r\n"
       "        C2 C3 \r\n"
       ",\r\n"
       "        MODULE_X ! MODULE_X ! '43-160 V → 5 V' ,\r\n"
       "        ; U1 \r\n"
       "fuse-th ! fuse-th !  ; FH1 FH2 \r\n"
       "$NETS\r\n"
       "'GND' ; C1.2 C2.- ,\r\n"
       "        C3.- U1.-Vin \r\n"
       "'V5' ; C1.1 C2.+ C3.+ U1.+Vout \r\n"
       "'HOLD_IN' ; FH1.1 \r\n"
       "'HOLD' ; FH2.1 \r\n"
       "$A_PROPERTIES\r\n"
       "$END\r\n")


def design(extra_nets=()):
    parts = (Part("C1", "c", "0805", "POWER", "C", ("1", "2"), 1, v_max=50),
             Part("C2", "c", "r", "POWER", "C", ("+", "-"), 1, v_max=25),
             Part("C3", "c", "r", "POWER", "C", ("+", "-"), 1, v_max=25),
             Part("U1", "m", "m", "POWER", "CONVERTER", ("-Vin", "+Vout"), 1),
             Part("FH1", "clip", "clip", "POWER", "FUSECLIP", ("1",), 1),
             Part("FH2", "clip", "clip", "POWER", "FUSECLIP", ("1",), 1),
             Part("F1", "fuse", "5x20", "POWER", "FUSE", ("1", "2"), 1, v_max=300))
    nets = (Net("GND", (("C1", "2"), ("C2", "-"), ("C3", "-"), ("U1", "-Vin")), "GND"),
            Net("V5", (("C1", "1"), ("C2", "+"), ("C3", "+"), ("U1", "+Vout")), "5V"),
            Net("HOLD_IN", (("FH1", "1"), ("F1", "1")), "84V"),
            Net("HOLD", (("FH2", "1"), ("F1", "2")), "84V")) + tuple(extra_nets)
    return Design(parts=parts, nets=nets)


def test_the_parser_reads_every_record_through_the_continuations():
    t = tel_check.parse(TEL)
    assert t.packages == {"C1": "c0805", "C2": "cap-th_bd8", "C3": "cap-th_bd8",
                          "U1": "MODULE_X", "FH1": "fuse-th", "FH2": "fuse-th"}
    assert t.nets["GND"] == {("C1", "2"), ("C2", "-"), ("C3", "-"), ("U1", "-Vin")}
    assert set(t.nets) == {"GND", "V5", "HOLD_IN", "HOLD"}


def test_a_matching_export_passes_with_the_fuse_expected_absent():
    """F1 is not converted to PCB: the export leaves it out, and its two nets
    stay split, as the copper will be."""
    r = tel_check.compare(design(), "POWER", tel_check.parse(TEL))
    assert r.ok, r.problems
    assert r.left_off == ["F1"]
    assert (r.nets, r.pins) == (4, 10)


def test_a_pin_on_the_wrong_net_is_reported():
    bad = TEL.replace("'V5' ; C1.1 C2.+", "'V5' ; C1.2 C2.+")
    r = tel_check.compare(design(), "POWER", tel_check.parse(bad))
    assert not r.ok
    assert any("V5" in p for p in r.problems) and any("GND" in p for p in r.problems)


def test_a_missing_net_and_a_part_that_should_be_off_the_pcb_are_reported():
    with_fuse = TEL.replace("'HOLD' ; FH2.1", "'HOLD' ; FH2.1 F1.2")
    r = tel_check.compare(design(), "POWER", tel_check.parse(with_fuse))
    assert not r.ok and any("F1" in p for p in r.problems)
    r = tel_check.compare(design((Net("SPARE", (("U1", "x"),), "SIGNAL"),)), "POWER",
                          tel_check.parse(TEL))
    assert not r.ok and any("SPARE" in p for p in r.problems)


def test_a_wrong_footprint_is_reported_even_when_every_net_matches():
    """Pads carry pin names, so a wrong land pattern with the right names
    passes the nets (review CK-11). C1's footprint is compared too."""
    d = design().replace_part("C1", lcsc="C49678")
    fixture = {"C49678": {"footprint": "c0805"}}
    assert tel_check.compare(d, "POWER", tel_check.parse(TEL), fixture).ok
    wrong = TEL.replace("c0805 ! c0805 ! '100nF 50V' ; C1", "r0402 ! r0402 ! '100nF 50V' ; C1")
    r = tel_check.compare(d, "POWER", tel_check.parse(wrong), fixture)
    assert any("C1 has footprint r0402, the generator bound c0805" in p for p in r.problems)
