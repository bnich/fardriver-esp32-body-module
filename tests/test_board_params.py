import pytest
from tools import board_params as bp


def test_cavity_is_the_owner_estimate_pending_m18():
    assert (bp.CAVITY_L, bp.CAVITY_W, bp.CAVITY_H) == (200.0, 50.0, 70.0)
    assert bp.CAVITY_MEASURED is False, "flip this only when M18 lands"


def test_board_envelope_is_derived_not_hardcoded():
    assert bp.BOARD_W == pytest.approx(bp.CAVITY_W - 2 * bp.WALL - 2.0)
    assert bp.BOARD_L == pytest.approx(bp.CAVITY_L - 2 * bp.WALL - 8.0)


def test_envelope_matches_the_design_record():
    # board-design-record.md section 0 states 42 x 186
    assert bp.BOARD_W == pytest.approx(42.0)
    assert bp.BOARD_L == pytest.approx(186.0)


def test_internal_stack_height():
    assert bp.AVAIL_H == pytest.approx(64.0)


def test_layer_ceilings_cover_all_four_boards():
    assert set(bp.LAYER_CEILING_MM) == {"HVIN", "CONV", "DRV", "BRAIN"}


def test_conv_ceiling_clears_the_y2_discs_not_just_the_brick():
    # The Y2 caps must sit AT the converter terminals (plan 9.5.2) and are
    # 14.0 mm -- taller than the 12.7 mm brick. The plate clears them; the
    # brick gets a spacer. Setting this back to 12.7 makes a required part
    # illegal on the board it is required to be on.
    assert bp.LAYER_CEILING_MM["CONV"] == pytest.approx(14.0)
    assert bp.LAYER_CEILING_MM["CONV"] > 12.7
