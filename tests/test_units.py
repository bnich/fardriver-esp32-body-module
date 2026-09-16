import pytest
from tools.eprj3.units import mm_to_units, units_to_mm


def test_one_inch_is_one_hundred_units():
    # fmt2 general/conventions.md: the unit is 0.01 inch
    assert mm_to_units(25.4) == pytest.approx(100.0)


def test_board_width_42mm():
    assert mm_to_units(42.0) == pytest.approx(165.354, abs=0.001)


def test_board_length_186mm():
    assert mm_to_units(186.0) == pytest.approx(732.283, abs=0.001)


@pytest.mark.parametrize("mm", [0.0, 0.1, 1.6, 25.4, 42.0, 186.0, 200.0])
def test_round_trip(mm):
    assert units_to_mm(mm_to_units(mm)) == pytest.approx(mm, abs=1e-6)


def test_zero():
    assert mm_to_units(0) == 0
