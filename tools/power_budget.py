"""The module's worst-case power, against the parts that carry it.

    python3 -m tools.power_budget

The base load is plan §3.2.3's measured-and-estimated 12 V budget; the aux
load is DERIVED from the netlist (every 12 V and 5 V aux channel at the
design's per-output current, plus the 5 V buck's own standing draw). Sized at
the 60.0 V LVC, never at full charge (plan §3.2.3): a converter is a
constant-power load, so its input current is highest when the pack is lowest.

⚠️ WHICH CASE THIS MODELS -- read this before quoting 8.47 A as "the worst
case", because it is not the ceiling:

  * `AUX_OUTPUT_A` is the NOMINAL per-channel load IO-2 asked for -- 1 A, all
    eight on together -- not what the limiters let through. Each 12 V channel
    limits at 1.12-1.55 A (R_CL = 1.5 k, TI SLVSCV8E p.8's ±15 %) and each 5 V
    channel at 1.19-1.39 A (TI SLVS841F; U305's own 5 A output rating caps the
    5 V branch a little below four times that). Eight channels all held at
    their upper current limit is about 2.62 + 6.20 + 2.57 = 11.4 A at 12 V:
    91 % of the brick's 12.5 A, so the converter still carries it -- but
    2.53 A into the choke (84 % of 3 A) and 2.58 A through the tap fuse (86 %
    of 3 A), both over the derates below. That case is EIGHT SIMULTANEOUS
    OUTPUT FAULTS, and a fast-blow fuse opening on it is the fuse doing its
    job. It is recorded here so nobody meets it as a surprise, and it is not
    what this check sizes the input path against.
  * The 5 V buck is counted whether or not a channel is switched on. U305's
    EN is tied to its own PVIN (TI SNVSAH5A p.4, "Can be tied to PVIN"), so
    the 5 V aux rail is live whenever the 12 V rail is -- before the firmware
    boots, with the expander in reset, with every enable pulled low. Its
    standing draw therefore sits on the 12 V budget permanently.
  * The 12 V converter and its input choke are found through the COPPER,
    never by refdes: the brick whose output is a 12 V net, and the
    common-mode choke on that brick's 84 V input nets. A check that names
    L101 stops checking the day the part is renumbered. The tap fuse is the
    one number typed here, because it is in the HARNESS and not on any board
    the netlist describes (IO-10).
"""
import re
import sys
from dataclasses import dataclass, field

from . import netlist
from .model import Design, Part

#: plan §3.2.3: one beam, DRL, brake, signals, fan, display, telltales.
BASE_12V_A = 2.62
#: IO-2: every aux output delivers 1 A. ⚠️ Nominal, not the limit -- see above.
AUX_OUTPUT_A = 1.0
V12, V5 = 12.0, 5.0
BUCK_EFF = 0.90          # the 5 V aux buck, conservative at 20 W (Task 3 item 1's datasheet)
TDK_EFF = 0.90           # TDK CN150B110 at ~70 % load; 91.5 % is its full-load figure
LVC_V = 60.0             # the pack's low-voltage cutoff (plan §3.2.3)
LOGIC_IN_W = 3.0         # the Cincon's input for the logic rail (plan §3.2.3)
#: The module's B+ tap fuse, off the board in the harness (IO-10): KLKD003,
#: 3 A fast-blow, 600 V DC / 50 kA DC (Littelfuse POWR-GARD rev 111618 p.1-2).
TAP_FUSE_A = 3.0
TAP_FUSE_MPN = "KLKD003"
#: A fast-blow fuse carries at most this share of its rating continuously.
FUSE_DERATE = 0.75
#: And a common-mode choke this share of its 70 °C rated current: the rating is
#: a temperature-rise figure, and the stack gives it no airflow.
CHOKE_DERATE = 0.80
#: What the 5 V aux buck draws from V12 with every 5 V channel OFF, in A:
#:   IQ_SW    15 µA at V12          TI SNVSAH5A p.8, I_OUT = 0, RT open, and
#:                                  SYNC/MODE grounded = auto mode (p.4), so
#:                                  it is in PFM here, not switching flat out.
#:   FB       5.03 V / (12 k + 3 k) = 335 µA out of the 5 V rail (R377/R378),
#:            which the buck converts: ~155 µA at 12 V.
#: = 0.17 mA, booked at 0.25 mA -- the divider's 1.7 mW is converted at a
#: light-load efficiency well under BUCK_EFF, and a term this small does not
#: earn a second decimal. It is in the sum because a term nobody states is a
#: term nobody re-checks, not because it is large. The four TPS2553 switches
#: add nothing measurable: 0.1 µA each with the output off (TI SLVS841F p.6).
BUCK_STANDING_A = 0.00025


@dataclass
class Result:
    load_12v_a: float
    tdk_in_a: float
    tap_a: float
    aux12_a: float = 0.0
    aux5_a: float = 0.0
    buck_standing_a: float = 0.0
    converter: Part | None = None
    conv_rated_a: float | None = None
    choke: Part | None = None
    choke_rated_a: float | None = None
    problems: list = field(default_factory=list)


def _rated_a(value: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*A\b", value or "")
    return float(m.group(1)) if m else None


def _converter_12v(d: Design) -> Part | None:
    """The brick that MAKES the 12 V rail: a converter with an OUTPUT pin on a
    12 V net. ⛔ Input pins are skipped by name -- the 5 V aux buck's PVIN is
    on V12 too, and it is a load, not the source."""
    for p in d.parts:
        if p.kind != "CONVERTER":
            continue
        for pin in p.pins:
            if "in" in pin.lower():
                continue
            net = d.net_of(p.refdes, pin)
            if net is not None and net.domain == "12V":
                return p
    return None


def _input_choke(d: Design, conv: Part) -> Part | None:
    """The common-mode choke in THAT brick's input path: the one sharing an
    84 V net with it. ⛔ Not "a net" -- both chokes sit on HV_SW and on GND,
    so a lookup over every shared net returns whichever comes first in the
    parts tuple, and would have graded the wrong part."""
    hv = {n.name for n in d.nets_of(conv.refdes) if n.domain == "84V"}
    on_hv = {r for n in d.nets if n.name in hv for r, _ in n.pins}
    return next((p for p in d.parts
                 if p.kind == "CMCHOKE" and p.refdes in on_hv), None)


def budget(d: Design | None = None) -> Result:
    d = d if d is not None else netlist.current()
    n12 = sum(1 for n in d.nets if re.fullmatch(r"AUX12V_\d", n.name))
    n5 = sum(1 for n in d.nets if re.fullmatch(r"AUX5V_\d", n.name))
    aux12 = n12 * AUX_OUTPUT_A
    aux5 = n5 * AUX_OUTPUT_A * V5 / BUCK_EFF / V12
    # The buck is a permanent load on V12 because its enable is its input: the
    # 5 V rail exists for those channels, so their presence is what says so.
    standing = BUCK_STANDING_A if n5 else 0.0
    load = BASE_12V_A + aux12 + aux5 + standing
    tdk_in = load * V12 / TDK_EFF / LVC_V
    tap = tdk_in + LOGIC_IN_W / LVC_V
    r = Result(load, tdk_in, tap, aux12_a=aux12, aux5_a=aux5,
               buck_standing_a=standing)

    conv = _converter_12v(d)
    r.converter = conv
    if conv is None:
        r.problems.append("no converter makes the 12 V rail: nothing carries "
                          "this load, and nothing here can say what it is "
                          "rated for")
    else:
        r.conv_rated_a = _rated_a(conv.value)
        if r.conv_rated_a is None:
            r.problems.append(f"{conv.refdes} ({conv.mpn}) states no current "
                              f"rating in its value {conv.value!r}")
        elif load > r.conv_rated_a:
            r.problems.append(f"{conv.refdes} ({conv.mpn}) is asked for "
                              f"{load:.2f} A where it makes {r.conv_rated_a:g} A")

    choke = _input_choke(d, conv) if conv else None
    r.choke = choke
    if choke is None:
        r.problems.append("no common-mode choke stands in the 12 V "
                          "converter's input path: nothing limits what the "
                          "brick's switching puts back on the pack wiring, "
                          "and nothing here is sized against this load")
    else:
        r.choke_rated_a = _rated_a(choke.value)
        if r.choke_rated_a is None:
            r.problems.append(f"{choke.refdes} ({choke.mpn}) states no current "
                              f"rating in its value {choke.value!r}: it cannot "
                              f"be held to this load")
        elif tdk_in > r.choke_rated_a * CHOKE_DERATE:
            r.problems.append(
                f"{choke.refdes} ({choke.mpn}, {choke.value}) carries "
                f"{tdk_in:.2f} A at the {LVC_V:g} V LVC: over "
                f"{CHOKE_DERATE:.0%} of its {r.choke_rated_a:g} A rating")

    if tap > TAP_FUSE_A * FUSE_DERATE:
        r.problems.append(f"the {TAP_FUSE_A:g} A tap fuse ({TAP_FUSE_MPN}) "
                          f"carries {tap:.2f} A at the LVC: over "
                          f"{FUSE_DERATE:.0%} of its rating")
    return r


def _margin(carried: float, rated: float | None, derate: float) -> str:
    if not rated:
        return "no rating to measure against"
    return (f"{carried:.2f} A of {rated:g} A = {carried / rated:.0%} "
            f"(gate {derate:.0%}, {rated * derate - carried:+.2f} A of margin)")


def report(d: Design | None = None) -> str:
    r = budget(d)
    lines = [f"12 V worst case {r.load_12v_a:.2f} A "
             f"(base {BASE_12V_A:.2f} + 12 V aux {r.aux12_a:.2f} + 5 V aux "
             f"{r.aux5_a:.2f} + buck standing {r.buck_standing_a * 1000:.2f} mA) "
             f"· TDK input {r.tdk_in_a:.2f} A · tap {r.tap_a:.2f} A "
             f"at {LVC_V:g} V"]
    if r.converter is not None:
        lines.append(f"  {r.converter.refdes} ({r.converter.mpn})  "
                     + _margin(r.load_12v_a, r.conv_rated_a, 1.0))
    if r.choke is not None:
        lines.append(f"  {r.choke.refdes} ({r.choke.mpn}, {r.choke.value})  "
                     + _margin(r.tdk_in_a, r.choke_rated_a, CHOKE_DERATE))
    lines.append(f"  tap fuse ({TAP_FUSE_MPN}, harness)  "
                 + _margin(r.tap_a, TAP_FUSE_A, FUSE_DERATE))
    lines += [f"  ⛔ {p}" for p in r.problems]
    lines.append("FAIL" if r.problems else "PASS")
    return "\n".join(lines)


def main() -> int:
    text = report()
    print(text)
    return 1 if text.endswith("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
