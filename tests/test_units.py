"""Units are the highest-consequence, lowest-visibility thing in the emitter.

Schematic and PCB documents differ by 10x, so both directions of both
conversions are pinned against figures read out of the official example files.
"""
import pytest
from tools.eprj3.units import (
    mm_to_sch, sch_to_mm, mm_to_pcb, pcb_to_mm,
    SCH_MM_PER_UNIT, PCB_MM_PER_UNIT,
)


def test_the_two_units_differ_by_exactly_ten():
    assert SCH_MM_PER_UNIT / PCB_MM_PER_UNIT == pytest.approx(10.0)


# --- schematic: 1 unit = 0.01 inch -----------------------------------------
def test_schematic_pin_pitch_is_ten_units():
    # official example: pin rows at y = -45,-35,-25,-15 -> 10 units apart,
    # and schematic pin pitch is 0.1 inch = 2.54 mm
    assert sch_to_mm(10) == pytest.approx(2.54)


def test_one_inch_is_one_hundred_schematic_units():
    assert mm_to_sch(25.4) == pytest.approx(100.0)


# --- PCB: 1 unit = 1 mil ----------------------------------------------------
def test_example_board_outline_is_a_sane_size():
    # official example outline ["R",0,940,1475,940,0,0]
    assert pcb_to_mm(1475) == pytest.approx(37.465, abs=0.001)
    assert pcb_to_mm(940) == pytest.approx(23.876, abs=0.001)


def test_one_inch_is_one_thousand_pcb_units():
    assert mm_to_pcb(25.4) == pytest.approx(1000.0)


def test_our_board_envelope_in_pcb_units():
    # The figures the outline emitter cuts: board_params' 41.84 x 242 mm
    # envelope (tests/test_pcb.py is what holds the emitter to BOARD_W /
    # BOARD_L). The expected units are hand-computed at 1 unit = 1 mil --
    # 41.84 / 0.0254 = 1647.244, 242 / 0.0254 = 9527.559 -- so they pin the
    # CONVERSION rather than restate it. The assertion above them is what keeps
    # this comment true: it read "42 x 186" for a while after the envelope
    # moved, and "40 x 241" until the cabled crossings re-ran the search.
    from tools.board_params import BOARD_L, BOARD_W
    assert (BOARD_W, BOARD_L) == (41.84, 242.0)
    assert mm_to_pcb(41.84) == pytest.approx(1647.244, abs=0.001)
    assert mm_to_pcb(242.0) == pytest.approx(9527.559, abs=0.001)


def test_jlc_rule_numbers_read_as_round_mm_in_mil():
    # 11.811 / 196.8504 / 236.2205 appear in the example's rules
    for units, mm in ((11.811, 0.3), (196.8504, 5.0), (236.2205, 6.0)):
        assert pcb_to_mm(units) == pytest.approx(mm, abs=0.001)


# --- round trips ------------------------------------------------------------
@pytest.mark.parametrize("mm", [0.0, 0.1, 1.6, 25.4, 41.84, 242.0, 200.0])
def test_sch_round_trip(mm):
    assert sch_to_mm(mm_to_sch(mm)) == pytest.approx(mm, abs=1e-6)


@pytest.mark.parametrize("mm", [0.0, 0.1, 1.6, 25.4, 41.84, 242.0, 200.0])
def test_pcb_round_trip(mm):
    assert pcb_to_mm(mm_to_pcb(mm)) == pytest.approx(mm, abs=1e-6)


def test_there_is_no_unit_agnostic_conversion():
    # A caller that has not decided which document it is emitting has not
    # finished thinking, and the failure is invisible.
    import tools.eprj3.units as u
    assert not hasattr(u, "mm_to_units")
    assert not hasattr(u, "units_to_mm")
