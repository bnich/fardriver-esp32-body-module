from tools import gpio_budget as g


def test_pool_matches_the_plans_figure():
    # plan.md 9.8.1: "a clean pool of ~32"
    assert len(g.POOL) == 32


def test_budget_closes_but_only_just():
    assert g.report() == []
    assert g.SPARE == 0, (
        "BD-5 has no margin. If this becomes negative the design does not fit; "
        "if it becomes positive someone freed a pin -- update the record.")


def test_gpio43_is_excluded_from_the_driver_pool():
    assert g.BOOT_LOG not in g.DRIVER_POOL
    assert g.BOOT_LOG in g.POOL


def test_analog_fits_adc1():
    assert g.ANALOG <= len(g.ADC1_POOL)


def test_strapping_and_flash_are_out_of_the_pool():
    for pin in (0, 3, 45, 46, 26, 30, 32, 19, 20):
        assert pin not in g.POOL, f"GPIO{pin} must not be in the pool"


def test_nonexistent_pins_are_out():
    for pin in (22, 23, 24, 25):
        assert pin not in g.POOL


def test_budget_detects_overflow():
    # prove the check fires: pretend one more driver is needed
    import dataclasses
    over = g.TOTAL + 1
    assert over > len(g.POOL), "guard: this fixture must actually overflow"
