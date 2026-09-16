"""Executable constraints. Each one names the decision it protects.

The project's rule is that a constraint belongs in an assertion, not a comment
-- and that an assertion which never fires is not a test. Every rule here has
a deliberately-broken fixture in tests/test_rules.py proving it FAILS, beside
the real design proving it PASSES.

An error string always starts with the rule ID so a failure points at the
decision it violates rather than at a line number.
"""
from .board_params import LAYER_CEILING_MM
from .model import Design

# ESP32-S3 silicon facts (plan.md 3.1.2), not preferences.
ADC1_GPIOS = {f"GPIO{n}" for n in range(1, 11)}
STRAPPING_GPIOS = {"GPIO0", "GPIO3", "GPIO45", "GPIO46"}
USB_GPIOS = {"GPIO19", "GPIO20"}
BOOT_LOG_GPIO = "GPIO43"
NONEXISTENT_GPIOS = {f"GPIO{n}" for n in range(22, 26)}
FLASH_GPIOS = {f"GPIO{n}" for n in range(26, 33)}

#: Nets that must be read by ADC1 because ADC2 dies when WiFi is on.
#: ⚠️ Both the plan's IN-nn labels AND the netlist's own net names are listed.
#: The rule previously carried only the IN-nn names, which appear nowhere in
#: netlist.py, so it silently covered nothing -- an assertion that cannot fire
#: is not a test.
ANALOG_NETS = {
    "CS1", "CS2",
    "IN-12", "KEY_SENSE",      # same signal, two vocabularies
    "IN-15", "V12_SENSE",
    "IN-16", "AMBIENT",
}

LOW_VOLTAGE_BOARDS = {"DRV", "BRAIN"}
HIGH_DOMAINS = {"84V"}

TVS_MPNS = {"PESD5V0S4UD", "SMCJ90A"}
BIAS_VALUES = {"10k", "100k", "20k"}


def bd2_voltage_domain_containment(d: Design) -> list[str]:
    """BD-2: 84 V never reaches the logic boards."""
    errs = []
    for net in d.nets:
        if net.domain not in HIGH_DOMAINS:
            continue
        for refdes, _pin in net.pins:
            try:
                board = d.board_of(refdes)
            except KeyError:
                continue
            if board in LOW_VOLTAGE_BOARDS:
                errs.append(
                    f"BD-2: net {net.name!r} is {net.domain} but reaches "
                    f"{refdes} on {board}. 84 V stays on HVIN/CONV.")
    return errs


def bd4_hv_link_creepage(d: Design) -> list[str]:
    """BD-4: the 84 V inter-board header skips alternate pins."""
    errs = []
    for c in d.connectors:
        if c.interface == "HV-LINK" and c.pitch_mm < 5.08:
            errs.append(
                f"BD-4: {c.refdes} carries 84 V at {c.pitch_mm} mm pitch. "
                f"Skip alternate pins for 5.08 -- 2.54 leaves ~0.7 mm "
                f"pad-edge to pad-edge against IPC-2221's 0.6 mm.")
    return errs


def adc1_only(d: Design) -> list[str]:
    """ADC2 is unusable while WiFi is on, so analog must land on GPIO1-10."""
    errs = []
    for net in d.nets:
        if net.name in ANALOG_NETS and net.gpio and net.gpio not in ADC1_GPIOS:
            errs.append(
                f"ADC1: analog net {net.name!r} is on {net.gpio}. "
                f"ADC2 dies with WiFi -- use GPIO1-10.")
    return errs


def strapping_pins(d: Design) -> list[str]:
    """No wire that leaves the box may land on a strapping pin."""
    errs = []
    for net in d.nets:
        if not net.gpio:
            continue
        if net.leaves_box and net.gpio in STRAPPING_GPIOS:
            errs.append(
                f"strapping: net {net.name!r} leaves the box on {net.gpio}. "
                f"A rider holding a lever at key-on would put the module in "
                f"download mode -- no lights, on the road.")
        if net.gpio in NONEXISTENT_GPIOS:
            errs.append(f"strapping: {net.name!r} uses {net.gpio}, which does "
                        f"not exist on the S3.")
        if net.gpio in FLASH_GPIOS:
            errs.append(f"strapping: {net.name!r} uses {net.gpio}, which is "
                        f"in-package flash.")
        if net.gpio in USB_GPIOS and not net.name.startswith("USB_"):
            # GPIO19/20 ARE native USB D-/D+. The USB nets are entitled to
            # them; anything else on them is the error.
            errs.append(f"strapping: {net.name!r} uses {net.gpio}, reserved "
                        f"for native USB.")
    return errs


def gpio43_never_a_driver(d: Design) -> list[str]:
    """GPIO43 emits the ROM boot log at every reset."""
    return [
        f"GPIO43: net {net.name!r} drives from {BOOT_LOG_GPIO}, which emits "
        f"the ROM boot log at 115200 on every reset."
        for net in d.nets if net.gpio == BOOT_LOG_GPIO
    ]


def gate_bias_off(d: Design) -> list[str]:
    """D14: every output gate biases OFF, so a hung module drives no lamp."""
    errs = []
    for net in d.nets:
        if not net.name.endswith("_GATE"):
            continue
        has_bias = any(
            d.part(r).value in BIAS_VALUES
            for r, _ in net.pins if _safe_has(d, r))
        if not has_bias:
            errs.append(
                f"gate bias: {net.name!r} has no bias-OFF resistor. Every "
                f"gate biases OFF (D14) or a hung module can drive a lamp.")
    return errs


def tvs_on_box_leaving_nets(d: Design) -> list[str]:
    """Every wire leaving the box gets its TVS on-board at the connector."""
    tvs_nets = {
        net.name for net in d.nets
        for r, _ in net.pins
        if _safe_has(d, r) and d.part(r).mpn in TVS_MPNS
    }
    return [
        f"TVS: net {net.name!r} leaves the box with no TVS at its connector."
        for net in d.nets if net.leaves_box and net.name not in tvs_nets
    ]


def layer_height_ceilings(d: Design) -> list[str]:
    """Section 4: height is a design rule here, not an outcome."""
    errs = []
    for p in d.parts:
        if p.side != "top":
            continue          # BD-14: underside parts hang into the layer below
        ceiling = LAYER_CEILING_MM.get(p.board)
        if ceiling is not None and p.height_mm > ceiling:
            errs.append(
                f"height: {p.refdes} ({p.mpn}) is {p.height_mm} mm on "
                f"{p.board}, ceiling {ceiling} mm. One tall substitution "
                f"breaks the enclosure.")
    return errs


#: Working voltage of each domain, for protection-part selection.
DOMAIN_VOLTS = {"84V": 84.0, "12V": 12.0, "5V": 5.0, "3V3": 3.3}


def tvs_standoff_covers_its_net(d: Design) -> list[str]:
    """A TVS must STAND OFF the net's working voltage, not clamp below it.

    `PESD5V0S4UD` has V_RWM = 5 V. Put it across a 12 V lamp feed and it
    conducts continuously -- a dead short on the channel it was meant to
    protect. The part is correct on 3.3 V logic and wrong on 12 V, and nothing
    about the schematic looks different.

    Guarding the class here rather than at each call site, so the next 12 V
    channel added cannot reintroduce it.
    """
    errs = []
    for net in d.nets:
        volts = DOMAIN_VOLTS.get(net.domain)
        if volts is None:
            continue
        for refdes, _pin in net.pins:
            if not _safe_has(d, refdes):
                continue
            part = d.part(refdes)
            if part.mpn not in TVS_MPNS:
                continue
            if part.vds_max is not None and part.vds_max < volts:
                errs.append(
                    f"TVS standoff: {part.refdes} ({part.mpn}) stands off "
                    f"{part.vds_max} V on net {net.name!r}, which works at "
                    f"{volts} V. It will conduct continuously -- a short, not "
                    f"protection.")
    return errs


def _safe_has(d: Design, refdes: str) -> bool:
    try:
        d.part(refdes)
        return True
    except KeyError:
        return False


ALL_RULES = (
    bd2_voltage_domain_containment,
    bd4_hv_link_creepage,
    adc1_only,
    strapping_pins,
    gpio43_never_a_driver,
    gate_bias_off,
    tvs_on_box_leaving_nets,
    tvs_standoff_covers_its_net,
    layer_height_ceilings,
)


def check_all(design: Design) -> list[str]:
    """Run every rule. Empty list means the design satisfies its own spec."""
    errs: list[str] = []
    for rule in ALL_RULES:
        errs.extend(rule(design))
    return errs
