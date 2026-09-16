"""Every rule gets a PASS case and a FAIL case.

An assertion that never fires is not a test -- so each rule below is proven
against geometry/wiring that deliberately violates it.
"""
import pytest
from tools import rules
from tools.model import Part, Net, Connector, ConnPin, Design

# --- a minimal design that satisfies every rule ----------------------------
GOOD = Design(
    parts=(
        Part("U1", "ESP32-S3-WROOM-1-N8", "MOD", "BRAIN", 3.1),
        Part("Q1", "AO3400A", "SOT-23", "DRV", 1.2, vds_max=30),
        Part("R1", "10k", "0805", "DRV", 1.0, value="10k"),          # gate bias
        Part("D1", "PESD5V0S4UD", "SOT-457", "BRAIN", 1.1),          # TVS
        Part("Q3", "IXTP26P20P", "TO-220AB", "HVIN", 16.0, vds_max=200),
        Part("C1", "EKXJ221ELL221MM25S", "RAD", "CONV", 18.0, side="bottom"),
        Part("U9", "CN150B110-12/CO", "BRICK", "CONV", 12.7),
    ),
    nets=(
        Net("HORN_GATE", (("U1", "8"), ("Q1", "1"), ("R1", "1")),
            domain="SIGNAL", gpio="GPIO8"),
        Net("IN-12", (("U1", "1"), ("Q3", "2")), domain="SIGNAL",
            gpio="GPIO1", interface="PWR-UP"),
        Net("HORN_OUT", (("Q1", "2"), ("D1", "1")), domain="12V",
            leaves_box=True),
        Net("VBAT84", (("Q3", "1"), ("U9", "1")), domain="84V"),
    ),
    connectors=(
        Connector("J_HVLINK", "HVIN", "HV-LINK",
                  (ConnPin(1, "VBAT84"),), leaves_box=False,
                  pitch_mm=5.08, interface="HV-LINK"),
        Connector("J_HORN", "DRV", "Horn", (ConnPin(1, "HORN_OUT", "blue"),)),
    ),
)


def test_the_good_design_passes_everything():
    assert rules.check_all(GOOD) == []


# --- BD-2: voltage domain containment --------------------------------------
def test_bd2_fires_when_84v_reaches_brain():
    bad = GOOD.with_net(Net("STRAY84", (("U1", "9"), ("Q3", "3")), domain="84V"))
    assert any("BD-2" in e for e in rules.check_all(bad))

def test_bd2_quiet_on_good():
    assert [e for e in rules.check_all(GOOD) if "BD-2" in e] == []


# --- BD-4: HV-LINK creepage -------------------------------------------------
def test_bd4_fires_on_254_pitch_hv_link():
    from dataclasses import replace
    bad = replace(GOOD, connectors=tuple(
        replace(c, pitch_mm=2.54) if c.interface == "HV-LINK" else c
        for c in GOOD.connectors))
    assert any("BD-4" in e for e in rules.check_all(bad))

def test_bd4_quiet_on_good():
    assert [e for e in rules.check_all(GOOD) if "BD-4" in e] == []


# --- ADC1 -------------------------------------------------------------------
def test_adc1_fires_when_analog_lands_on_gpio11():
    bad = GOOD.with_gpio("IN-12", "GPIO11")
    assert any("ADC1" in e for e in rules.check_all(bad))

def test_adc1_quiet_on_good():
    assert [e for e in rules.check_all(GOOD) if "ADC1" in e] == []


# --- strapping pins ---------------------------------------------------------
def test_strapping_fires_when_a_box_leaving_net_uses_gpio0():
    bad = GOOD.with_gpio("HORN_OUT", "GPIO0")
    assert any("strapping" in e.lower() for e in rules.check_all(bad))

def test_strapping_quiet_on_good():
    assert [e for e in rules.check_all(GOOD) if "strapping" in e.lower()] == []


# --- GPIO43 -----------------------------------------------------------------
def test_gpio43_fires_when_used_as_a_driver():
    bad = GOOD.with_gpio("HORN_GATE", "GPIO43")
    assert any("GPIO43" in e for e in rules.check_all(bad))

def test_gpio43_quiet_on_good():
    assert [e for e in rules.check_all(GOOD) if "GPIO43" in e] == []


# --- gate bias --------------------------------------------------------------
def test_gate_bias_fires_when_the_pulldown_is_deleted():
    bad = GOOD.without_part("R1")
    assert any("gate bias" in e.lower() for e in rules.check_all(bad))

def test_gate_bias_quiet_on_good():
    assert [e for e in rules.check_all(GOOD) if "gate bias" in e.lower()] == []


# --- TVS on box-leaving nets ------------------------------------------------
def test_tvs_fires_when_removed_from_a_box_leaving_net():
    bad = GOOD.without_part("D1")
    assert any("TVS" in e for e in rules.check_all(bad))

def test_tvs_quiet_on_good():
    assert [e for e in rules.check_all(GOOD) if "TVS" in e] == []


# --- height ceilings --------------------------------------------------------
def test_height_fires_on_a_tall_topside_part_on_conv():
    from dataclasses import replace
    bad = replace(GOOD, parts=tuple(
        replace(p, height_mm=25.0, side="top") if p.refdes == "C1" else p
        for p in GOOD.parts))
    assert any("height" in e.lower() for e in rules.check_all(bad))

def test_height_ignores_bottom_side_parts():
    # BD-14: the electrolytics hang into the layer below, so they do not
    # count against CONV's 12.7 mm top-side ceiling
    assert [e for e in rules.check_all(GOOD) if "height" in e.lower()] == []


# --- TVS standoff vs the net it protects ------------------------------------
def test_tvs_standoff_fires_on_a_5v_array_across_a_12v_feed():
    """PESD5V0S4UD is V_RWM 5 V. On a 12 V lamp feed it conducts
    continuously -- a short across the channel it was meant to protect, and
    nothing about the schematic looks different."""
    from dataclasses import replace
    bad = replace(GOOD, parts=tuple(
        replace(p, vds_max=5.0) if p.refdes == "D1" else p for p in GOOD.parts))
    errs = rules.check_all(bad)
    assert any("TVS standoff" in e for e in errs), errs


def test_tvs_standoff_quiet_when_the_part_stands_off_the_rail():
    from dataclasses import replace
    ok = replace(GOOD, parts=tuple(
        replace(p, vds_max=24.0) if p.refdes == "D1" else p for p in GOOD.parts))
    assert [e for e in rules.check_all(ok) if "TVS standoff" in e] == []


def test_analog_rule_covers_the_netlists_own_names_not_just_the_plans():
    # The rule carried only IN-12/IN-15/IN-16, which appear nowhere in
    # netlist.py -- so it silently covered nothing.
    for name in ("KEY_SENSE", "V12_SENSE", "AMBIENT"):
        assert name in rules.ANALOG_NETS, f"{name} not policed by the ADC1 rule"


def test_usb_nets_are_entitled_to_gpio19_20():
    from tools.model import Net
    d = GOOD.with_net(Net("USB_DP", (("U1", "20"), ("D1", "2")), gpio="GPIO20"))
    assert [e for e in rules.check_all(d) if "reserved for native USB" in e] == []


def test_a_non_usb_net_on_gpio20_still_fires():
    from tools.model import Net
    d = GOOD.with_net(Net("HORN2", (("U1", "20"), ("Q1", "3")), gpio="GPIO20"))
    assert any("reserved for native USB" in e for e in rules.check_all(d))
