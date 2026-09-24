"""tools/layout_facts.py: the project reader and the derivations the export
states -- the frame, a part's envelope, the net classes and the rules that
assign them, the decouplers, the HV node voltages -- each proven on the real
design or a record stream built for the case.

What pcbl does with these facts once exported (placing, routing, checking) is
proven in pcb-layout-tools, not here.
"""
import json

import pytest

from tests.synthetic_project import MIL, design, ix  # noqa: F401  (fixtures)
from tools import board_params as bp, eprj2, layout_facts as facts, layout_rules
from tools.model import Net


# --- the frame and the envelope ----------------------------------------------------
def test_portrait_frame_is_a_rotation_and_round_trips():
    f = facts.Frame(242.0, 41.84, True)
    assert f.to_file(0, 0) == (0, 242.0)                 # u = 0 is the file's top
    assert f.to_file(242.0, 41.84) == (41.84, 0)
    assert f.to_board(*f.to_file(12.5, 7.25)) == pytest.approx((12.5, 7.25))
    assert f.file_angle(0) == 270 and f.board_angle(270) == 0
    # a proper rotation: the direction of +u in the file is -Y, of +v is +X
    assert f.dir_to_board(1, 0) == (0, 1) and f.dir_to_board(0, -1) == (1, 0)
    g = facts.Frame(242.0, 41.84, False)
    assert g.to_file(3, 4) == (3, 4) and g.file_angle(90) == 90


def test_envelope_unions_pads_outline_and_the_stated_body():
    recs = [({"type": "PAD"}, json.dumps({"num": "1", "centerX": -39.37, "centerY": 0,
                                         "defaultPad": {"width": 55.5, "height": 53.15}})),
            ({"type": "PAD"}, json.dumps({"num": "2", "centerX": 39.37, "centerY": 0,
                                         "defaultPad": {"width": 55.5, "height": 53.15}})),
            ({"type": "POLY"}, json.dumps({"layerId": 3, "path": [71.3, -35.6, "ARC", 90, 77.3, -29.6]}))]
    e = facts.envelope(recs, (2.0, 1.25))
    assert e.x1 == pytest.approx(77.3 / MIL, abs=0.01)         # the silk, wider than the body
    assert e.y0 == pytest.approx(-35.6 / MIL, abs=0.01)        # the arc's start, below the pads
    assert e.y1 == pytest.approx(53.15 / 2 / MIL, abs=0.01)    # the pads, above the body's 0.625
    assert len(e.pads) == 2 and e.pads[0][0] == "1"
    # no `hole` record: surface mount, and nothing of it reaches the far face
    assert e.pads[0][5] is False and not e.tht
    holed = [(h, json.dumps({**json.loads(p), "hole": {"width": 30, "height": 30}}))
             for h, p in recs if h["type"] == "PAD"]
    assert facts.envelope(holed, (2.0, 1.25)).tht
    # a brick drawn upright: the stated body is laid along the drawn long axis
    tall = [({"type": "PAD"}, json.dumps({"num": "a", "centerX": 0, "centerY": -900,
                                         "defaultPad": {"width": 60, "height": 60}})),
            ({"type": "PAD"}, json.dumps({"num": "b", "centerX": 0, "centerY": 900,
                                         "defaultPad": {"width": 60, "height": 60}}))]
    e = facts.envelope(tall, (50.8, 25.4))
    assert e.x1 - e.x0 == pytest.approx(25.4) and e.y1 - e.y0 == pytest.approx(50.8)


def test_power_classes_come_from_driver_pins_not_names(design):
    cls = facts.power_classes(design)
    assert cls["PWR12"] == {"V12"}
    assert "AUX5V_1" in cls["CH5"] and "TAIL_STOP" in cls["CH12"]
    assert "KEY_SENSE_PIN" in cls["SENSE"] and "TWAI_TX" not in cls["SENSE"]
    # a net NAMED like a 5 V channel, with no TPS2553 OUT pin on it, is not one
    fake = design.with_net(Net("AUX5V_9", (("R401", "1"), ("U402", "GPA0")), "3V3"))
    assert "AUX5V_9" not in facts.power_classes(fake)["CH5"]
    real_faults = [n.name for n in design.nets if n.name.startswith("AUX5V_") and "FAULT" in n.name]
    assert real_faults and not (set(real_faults) & cls["CH5"])


def test_decouplers_are_100nF_on_a_rail_and_ground(ix):
    dec = facts.decouplers(ix, "LOGIC")
    assert dec["C414"] == "V3P3"
    assert "C412" not in dec                          # 100 nF on EN + GND: not a rail
    assert "C437" not in dec                          # the ADC filter


def test_a_zero_size_hole_is_an_smd_pad_not_a_pin_through_the_board():
    """`U404`'s SOIC-8 in the owner's file: eight pads, each with
    `"hole":{"holeType":"ROUND","width":0,"height":0}` -- the converter's way
    of writing an SMD land. Counting it as through-hole made an SOIC a THT part
    (2026-09-22) and would forbid every part on the other face under it. A
    hole crosses the board only if it has a size; the same pad with a 0.6 mm
    hole does."""
    def pad(hole):
        return [({"type": "PAD", "id": "p"}, eprj2._compact({
            "layerId": 1, "num": "1", "centerX": 0, "centerY": 0, "hole": hole, "plated": True,
            "defaultPad": {"padType": "RECT", "width": 60.0, "height": 60.0}}))]
    smd = facts.envelope(pad({"holeType": "ROUND", "width": 0, "height": 0}), (2.0, 2.0))
    assert smd.pads[0][5] is False and not smd.tht
    none = facts.envelope(pad(None), (2.0, 2.0))
    assert none.pads[0][5] is False and not none.tht
    drilled = facts.envelope(pad({"holeType": "ROUND", "width": 23.622, "height": 23.622}), (2.0, 2.0))
    assert drilled.pads[0][5] is True and drilled.tht



# --- the net classes ---------------------------------------------------------------
def test_the_hv_clearance_is_the_repo_s_one_figure():
    """⛔ Not a second copy of 1.25: the class reads `layout_rules`, so the
    placement gap and the routing rule cannot drift apart."""
    assert facts.HV.clearance_mm == layout_rules.HV_CLEARANCE_MM


def test_pack_voltage_beats_rail(ix):
    """`HV_C1_P` and `HV_C2_HOLD` are in `rules.rails(d)` AND at 84 V. Reached
    by the RAIL row first they would be routed at 0.6 mm and 0.25 mm of
    clearance while sitting at pack voltage."""
    for net in ("HV_C1_P", "HV_C2_HOLD"):
        assert net in ix.rails
        assert facts.net_class(ix, "POWER", net) is facts.HV


def test_the_twelve_volt_bus_is_pwr12_only_where_the_current_is(ix):
    """R0 scopes PWR12 to "on OUTPUTS and POWER"; `carries_bus` derives it."""
    assert facts.carries_bus(ix, "POWER") and facts.carries_bus(ix, "OUTPUTS")
    assert not facts.carries_bus(ix, "LOGIC") and not facts.carries_bus(ix, "CTRL")
    assert facts.net_class(ix, "POWER", "V12") is facts.PWR12
    assert facts.net_class(ix, "OUTPUTS", "V12") is facts.PWR12
    assert facts.net_class(ix, "LOGIC", "V12") is facts.RAIL
    assert facts.net_class(ix, "CTRL", "V12") is facts.RAIL


def test_the_driver_line_is_on_outputs_and_nowhere_else(ix):
    assert facts.v12_line(ix, "OUTPUTS") == ("U301", "U302", "U303")
    for board in ("POWER", "LOGIC", "CTRL"):
        assert facts.v12_line(ix, board) == ()


def test_the_can_pair_comes_from_the_transceiver_s_pins(ix):
    """Derived from a part with pins named CANH/CANL, never from a net name."""
    assert facts.diff_nets(ix, "LOGIC") == {"CANH", "CANL"}
    assert facts.net_class(ix, "LOGIC", "CANH") is facts.DIFF


def test_the_pair_follows_the_pin_and_not_the_name(design):
    """⛔ The class is the transceiver's pins, not a net called CANH. Move the
    `CANH` pin onto a net with another name and the class moves with it; the
    net that keeps the name and loses the pin drops out."""
    d = design.replace_net("CANH", pins=tuple(
        p for p in design.net("CANH").pins if p[0] != "U404"))
    d = d.replace_net("CAN_RS", pins=design.net("CAN_RS").pins + (("U404", "CANH"),))
    ix2 = facts.Index(d)
    pair = facts.diff_nets(ix2, "LOGIC")
    assert "CAN_RS" in pair and "CANH" not in pair


def test_a_sense_net_is_not_a_rail(ix):
    for net in ("CS1", "KEY_SENSE_PIN", "V12_SENSE"):
        assert facts.net_class(ix, "LOGIC", net) in (facts.SENSE, facts.DEFAULT)
    assert facts.net_class(ix, "OUTPUTS", "CS1") is facts.SENSE


def test_every_hv_net_has_a_derived_voltage(ix, design):
    nodes = facts.hv_node_voltages(design)
    for board in bp.STACK_ORDER:
        assert set(ix.hv.get(board, ())) <= set(nodes), board
    assert set(nodes) == set(layout_rules.hv_nets(design, "POWER"))


def test_an_hv_net_with_no_derived_voltage_is_refused(monkeypatch, design):
    """⛔ A new 84 V net nothing derives must FAIL, never fall through to a
    relaxed figure by default."""
    from tools import soft_start
    real = soft_start.hv_node_ranges

    def short(d=None):
        out = dict(real(d))
        out.pop("HV_SW")
        return out
    monkeypatch.setattr(soft_start, "hv_node_ranges", short)
    monkeypatch.setattr(facts, "_HV_VOLTS", {})
    with pytest.raises(RuntimeError, match="HV_SW.*no derived node voltage"):
        facts.hv_node_voltages(design)
