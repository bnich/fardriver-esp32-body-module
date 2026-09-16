"""ESP32-S3 pin pool and the BRAIN board's demand against it.

BD-5 resolved D16 to full-native lighting on the strength of "21 signals cost
nothing" across the DRV<->BRAIN stack connector. That is true of the CONNECTOR
and says nothing about the BOARD: totalling every signal that needs a GPIO puts
demand at exactly the size of the pool, with one of those pins being GPIO43,
which emits the ROM boot log and can never be a driver.

So full-native is reachable but has NO margin. This module makes that
checkable instead of leaving it as a sentence nobody re-derives.

plan.md 3.1.2 (silicon) and 9.8.1 (what a custom board recovers).
"""

# --- silicon facts ---------------------------------------------------------
EXISTS = set(range(0, 22)) | set(range(26, 49))   # GPIO22-25 do not exist
FLASH = set(range(26, 33))                        # in-package SPI flash
USB = {19, 20}                                    # native USB D-/D+
STRAPPING = {0, 3, 45, 46}                        # no wire may leave the box
BOOT_LOG = 43                                     # U0TXD, ROM log every reset
ADC1 = set(range(1, 11))                          # ADC2 dies with WiFi

#: Usable on a custom board with a bare WROOM-1-N8 (no DevKit artefacts).
POOL = EXISTS - FLASH - USB - STRAPPING

#: Of the pool, the pins that may drive a load.
DRIVER_POOL = POOL - {BOOT_LOG}

#: Available for analog, which must be ADC1.
ADC1_POOL = ADC1 & POOL

#: (label, count, kind) -- every signal needing a GPIO on BRAIN under BD-5.
DEMAND = (
    ("lighting channels -> TPS4H160B IN", 6, "driver"),
    ("DIAG_EN, SEL1, SEL2",               3, "driver"),
    ("CS1, CS2",                          2, "adc1"),
    ("FAULT1, FAULT2",                    2, "input"),
    ("horn, fan (PWM), buzzer (PWM)",     3, "driver"),
    ("boost",                             1, "driver"),
    ("IN-05/06 brake, native <10 ms",     2, "input"),
    ("I2C SDA, SCL",                      2, "bidir"),
    ("MCP23017 INT",                      1, "input"),
    ("UART1 TX/RX, UART2 RX",             3, "bidir"),
    ("TWAI TX/RX",                        2, "bidir"),
    ("IN-12 KEY sense",                   1, "adc1"),
    ("IN-15 12 V rail sense",             1, "adc1"),
    ("IN-16 ambient (optional)",          1, "adc1"),
    ("RUN sense, START sense",            2, "input"),
)

TOTAL = sum(n for _, n, _ in DEMAND)
DRIVERS = sum(n for _, n, k in DEMAND if k == "driver")
ANALOG = sum(n for _, n, k in DEMAND if k == "adc1")
SPARE = len(POOL) - TOTAL


def report() -> list[str]:
    """Problems with the budget. Empty list means it closes."""
    errs = []
    if TOTAL > len(POOL):
        errs.append(f"GPIO budget: demand {TOTAL} exceeds pool {len(POOL)}")
    if DRIVERS > len(DRIVER_POOL):
        errs.append(f"GPIO budget: {DRIVERS} drivers exceed the "
                    f"{len(DRIVER_POOL)} non-GPIO43 pins")
    if ANALOG > len(ADC1_POOL):
        errs.append(f"GPIO budget: {ANALOG} analog signals exceed ADC1's "
                    f"{len(ADC1_POOL)} usable pins (ADC2 dies with WiFi)")
    return errs
