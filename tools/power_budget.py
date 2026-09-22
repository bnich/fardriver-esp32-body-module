"""The module's 12 V load, against the parts that carry it.

    python3 -m tools.power_budget

The base load is plan §3.2.3's measured-and-estimated 12 V budget; the aux
load is DERIVED from the netlist (every 12 V and 5 V aux channel at the
design's per-output current, plus the 5 V buck's own standing draw). Sized at
the 60.0 V LVC, never at full charge (plan §3.2.3): a converter is a
constant-power load, so its input current is highest when the pack is lowest.

⚠️ WHICH CASE THIS MODELS -- read this before quoting 8.47 A as "the worst
case", because it is not the ceiling:

  * `AUX_OUTPUT_A` is the NOMINAL per-channel load IO-2 asked for -- 1 A, all
    eight on together -- not what the limiters let through. `limit_case()`
    derives that second figure from the copper, and the report prints it on
    the LIMITED line: every channel held at the upper edge of its own
    current limit, about 11.4 A at 12 V. That is 91 % of the brick's 12.5 A,
    so the converter still carries it -- but it puts ~2.53 A into the choke
    (84 % of 3 A) and ~2.58 A through the tap fuse (86 % of 3 A), over the
    derates below. That is EIGHT SIMULTANEOUS OUTPUT FAULTS, and a fast-blow fuse
    opening on it is the fuse doing its job. It is derived here so nobody
    meets it as a surprise, and it is not what this check sizes the input path
    against.
    ⚠️ The base in that sum is still `BASE_12V_A`, the NOMINAL 2.62 A of
    lamps, fan and display: `U301` and `U302` have limits of their own
    (2.0 A and 1.0 A per channel), and the LIMITED figure does not include
    them. The true ceiling is higher again.
  * The 5 V buck is counted whether or not a channel is switched on. U305's
    EN is tied to its own PVIN (TI SNVSAH5A p.4, "Can be tied to PVIN"), so
    the 5 V aux rail is live whenever the 12 V rail is -- before the firmware
    boots, with the expander in reset, with every enable pulled low. Its
    standing draw therefore sits on the 12 V budget permanently, and it is
    the one term the SHED case below cannot drop.
  * `Result.shed_*` is the load with every aux channel RELEASED: what is left
    on the tap after the firmware sheds the outputs at key-off (IO-16), which
    is the load `tools/soft_start.py` charges Q101's key-off decay with. It is
    this sum minus `aux12_a` and `aux5_a` exactly -- so it follows the base,
    and it keeps `buck_standing_a`, which no firmware can release.
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
from .model import Design, Part, resistance

#: plan §3.2.3: one beam, DRL, brake, signals, fan, display, telltales.
BASE_12V_A = 2.62
#: IO-2: every aux output delivers 1 A. ⚠️ Nominal, not the limit -- see above.
AUX_OUTPUT_A = 1.0
V12, V5 = 12.0, 5.0
#: The 5 V aux buck (U305, an LM73605) converting V12 → 5 V. TI SNVSAH5A
#: (ti_lm73605.pdf) p.33 Fig. 33/34, V_OUT = 5 V at 500 kHz: 93-94 % at 4 A
#: from a 12 V input. Those curves are drawn for the LM73606 -- the datasheet
#: publishes no 5 V curve for the LM73605 itself, only 3.3 V (p.32) and 12 V
#: (p.34) -- so 90 % is the conservative figure this budget uses.
BUCK_EFF = 0.90
#: The 12 V brick. TDK-Lambda CN-B110 datasheet (tdk_cn-b_e.pdf) p.1 "Model
#: Selector": CN150B110-12 is 91.5 % at 100 % load and nominal input. This
#: design runs it near 70 % of rating, off nominal, so 90 % is conservative.
#: ⚠️ Named for the JOB, not the maker: the field below is `conv_in_a` and the
#: report says "converter input", for the same reason nothing here says L101.
CONV_EFF = 0.90
LVC_V = 60.0             # the pack's low-voltage cutoff (plan §3.2.3)
LOGIC_IN_W = 3.0         # the Cincon's input for the logic rail (plan §3.2.3)
#: The module's B+ tap fuse, off the board in the harness (IO-10): KLKD003,
#: 3 A fast-blow, 600 V DC / 50 kA DC (Littelfuse POWR-GARD rev 111618 p.1-2).
TAP_FUSE_A = 3.0
TAP_FUSE_MPN = "KLKD003"
#: A fast-blow fuse carries at most this share of its rating continuously.
#: ⚠️ This is Littelfuse's 25 °C continuous-duty CONVENTION, not a line in the
#: KLKD datasheet: littelfuse_klkd.pdf p.4 gives only a temperature-derating
#: curve ("Temperature of Air Immediately Surrounding Fuse"), which is flat
#: near room ambient and so says nothing about continuous duty at 25 °C. The
#: datasheet's own agency table (p.4) is the other half of the reason: a KLKD
#: is only required to hold 100 % of its rating to temperature stabilisation,
#: and must open within 60 minutes at 135 %.
FUSE_DERATE = 0.75
#: And a common-mode choke this share of its rated current. ⚠️ What the 0.80
#: assumes is AMBIENT: Würth's 3 A is a 70 °C figure (we7448023005.pdf p.1),
#: and this choke is not in 70 °C air. It is inside a sealed metal box with
#: the 12 V brick -- ~10 W of dissipation at this load -- bolted to the floor
#: below it, in a stack with no airflow, on a bike that is ridden in summer.
#: The 20 % is the allowance for the difference, and it is an estimate: ⬜ it
#: becomes a measurement when the box is instrumented (spec §8 note 3).
CHOKE_DERATE = 0.80
#: The converter gets no derate at all, and that is deliberate rather than
#: lax: the brick's 12.5 A is TDK's rating AT ITS OWN rated conditions
#: (tdk_cn-b_e.pdf p.1), with the baseplate cooling TDK specifies, so cutting
#: it here would be inventing a second, unsourced rating. The real limit on
#: this part is thermal and is ⬜ UNPROVEN: the owner's pending measurement of
#: the brick's dissipation and baseplate temperature at the 8.5 A load (spec
#: §8 note 3 / owner list item 4) is what will say whether 12.5 A is reachable
#: in this box. That measurement, not this number, is the gate that matters.
CONV_DERATE = 1.00
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

#: A programming resistor's own tolerance, in the direction that RAISES the
#: limit it sets. Every resistor in both limiter strings is a 1 % part.
R_TOL = 0.01


def _tps4h160_limit_a(r_ohm: float) -> float:
    """TPS4H160B, R_CL → the MOST one channel passes. TI SLVSCV8E p.29 eq. 10
    gives 0.8 V × 2500 / R_CL, and p.8 gives ±15 % over 0.5-7 A."""
    return 0.8 * 2500.0 / (r_ohm * (1 - R_TOL)) * 1.15


def _tps2553_limit_a(r_ohm: float) -> float:
    """TPS2553, R_ILIM → the MOST one channel passes. TI SLVS841F p.15 eq. 1,
    the I_OS(max) curve: 22980 / R_ILIM(kΩ)^0.94, in mA. The equations
    explicitly EXCLUDE the resistor's own tolerance, so it goes in here."""
    return 22980.0 / (r_ohm * (1 - R_TOL) / 1000.0) ** 0.94 / 1000.0


#: How a current-limited switch turns its programming resistor into a ceiling:
#: mpn prefix -> (the pin the resistor hangs on, the datasheet's equation).
#: ⚠️ Keyed by MPN and not by refdes on purpose. A refdes is a POSITION and
#: says nothing about the maths; the equation belongs to the PART, and its pin
#: name comes off the same datasheet page. A switch that is not in here is a
#: problem, never a skip -- see `limit_case`.
_LIMITERS = {
    "TPS4H160": ("CL", _tps4h160_limit_a),
    "TPS2553": ("ILIM", _tps2553_limit_a),
    "TPS2552": ("ILIM", _tps2553_limit_a),
}


def _conv_in_a(load_12v_a: float) -> float:
    """A 12 V load -> the brick's input current at the LVC.

    One home for the arithmetic: the nominal case, the LIMITED case and the
    SHED case are the same three multiplications over three different loads,
    and a second copy of them is a second place to fix an efficiency.
    """
    return load_12v_a * V12 / CONV_EFF / LVC_V


def _tap_a(conv_in_a: float) -> float:
    """The brick's input current -> the whole B+ tap at the LVC.

    Q101 sits upstream of BOTH converters, so the Cincon's logic rail is on
    the tap whatever the 12 V side is doing.
    """
    return conv_in_a + LOGIC_IN_W / LVC_V


@dataclass
class Limit:
    """What the limiters let through, as opposed to what the design asks for."""
    load_12v_a: float | None = None
    conv_in_a: float | None = None
    tap_a: float | None = None
    per_12v_a: float | None = None
    per_5v_a: float | None = None
    n12: int = 0
    n5: int = 0
    problems: list[str] = field(default_factory=list)


@dataclass
class Result:
    load_12v_a: float
    conv_in_a: float
    tap_a: float
    aux12_a: float = 0.0
    aux5_a: float = 0.0
    buck_standing_a: float = 0.0
    converter: Part | None = None
    conv_rated_a: float | None = None
    choke: Part | None = None
    choke_rated_a: float | None = None
    limit: Limit = field(default_factory=Limit)
    problems: list[str] = field(default_factory=list)

    @property
    def shed_load_12v_a(self) -> float:
        """The 12 V load left when the firmware releases every aux output.

        IO-16 (2026-09-20): `KEY_SENSE` going inactive makes the firmware drop
        all eight aux channels, so Q101's key-off decay carries THIS and not
        `load_12v_a`. It is the same sum minus exactly the terms that are
        released -- `aux12_a` and `aux5_a` -- so a change to the base moves it
        and nobody retypes anything.

        ⚠️ `buck_standing_a` STAYS IN, and that is the whole reason this is a
        property rather than `BASE_12V_A` read from somewhere. U305's EN is
        tied to its own PVIN (TI SNVSAH5A p.4), so the 5 V aux rail is live
        whenever the 12 V rail is: the firmware has no way to release it.
        Leaving it out would be a silent omission, not a conservatism.
        """
        return self.load_12v_a - self.aux12_a - self.aux5_a

    @property
    def shed_conv_in_a(self) -> float:
        """The 12 V brick's input current at the LVC with the outputs shed."""
        return _conv_in_a(self.shed_load_12v_a)

    @property
    def shed_tap_a(self) -> float:
        """The B+ tap current at the LVC with the outputs shed -- the load
        `tools/soft_start.py` holds Q101's key-off SOA margin to."""
        return _tap_a(self.shed_conv_in_a)


def _rated_a(value: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*A\b", value or "")
    return float(m.group(1)) if m else None


def _converters_12v(d: Design) -> tuple[Part, ...]:
    """Every brick that MAKES a 12 V rail: a CONVERTER with an OUTPUT pin on a
    12 V net. Input pins are skipped by EXACT name, so that a part fed from
    V12 cannot be mistaken for the part that makes it.

    ⚠️ The skip is a belt, not the braces. What actually keeps the 5 V aux
    buck (U305) out of this list is its `kind`: it is an "IC", not a
    "CONVERTER", so the loop never looks at it. Were it ever reclassified, the
    name filter would NOT save the answer -- U305's `SW` pin sits on
    `V5AUX_SW`, whose domain is "12V", and "SW" is not an input name. The exact
    match is here so that a legitimate output called `INH` or `VIN_SENSE` is
    not swallowed by a substring test either.
    """
    out = []
    for p in d.parts:
        if p.kind != "CONVERTER":
            continue
        for pin in p.pins:
            if pin.lower().lstrip("+-") in ("vin", "pvin", "in"):
                continue
            net = d.net_of(p.refdes, pin)
            if net is not None and net.domain == "12V":
                out.append(p)
                break
    return tuple(out)


def _input_chokes(d: Design, conv: Part) -> tuple[Part, ...]:
    """Every common-mode choke in THAT brick's input path: the ones sharing an
    84 V net with it.

    ⛔ Not "a net". U201 and BOTH chokes sit on GND, so a lookup over every
    shared net returns whichever comes first in the parts tuple, and would
    have graded the wrong part. It is the `domain == "84V"` filter that throws
    GND away: U201's nets are HV_C1_P, HV_C1_N, GND, V12 and BASEPLATE, of
    which only the first two are 84 V, and L102 is on HV_C2_P / HV_C2_N. U201
    is not on HV_SW at all -- that net is ahead of both chokes.
    """
    hv = {n.name for n in d.nets_of(conv.refdes) if n.domain == "84V"}
    on_hv = {r for n in d.nets if n.name in hv for r, _ in n.pins}
    return tuple(p for p in d.parts
                 if p.kind == "CMCHOKE" and p.refdes in on_hv)


def _converter_12v(d: Design) -> Part | None:
    """The first brick making the 12 V rail. `budget()` uses `_converters_12v`
    and reports a second one as a defect; this wrapper is for callers that
    want the part itself."""
    convs = _converters_12v(d)
    return convs[0] if convs else None


def _input_choke(d: Design, conv: Part) -> Part | None:
    """The first choke in `conv`'s input path -- see `_converter_12v`."""
    chokes = _input_chokes(d, conv)
    return chokes[0] if chokes else None


def _aux_nets(d: Design, rail: str) -> list[str]:
    """The aux channel nets of one rail, e.g. AUX12V_1 … AUX12V_10.
    ⚠️ `\\d+`, never `\\d`: a tenth channel is still a channel, and a regex
    that quietly stops counting at nine under-states the very load this
    module exists to derive."""
    return sorted(n.name for n in d.nets
                  if re.fullmatch(rf"AUX{rail}V_\d+", n.name))


def _channel_limit_a(d: Design, net_name: str) -> tuple[float | None, str]:
    """The ceiling of ONE aux channel, read off the copper: the switch driving
    that net, the resistor on its programming pin, and that part's own
    equation. Returns (amps, "") or (None, why not)."""
    parts = {p.refdes: p for p in d.parts}
    drivers = [parts[r] for r, _ in d.net(net_name).pins
               if r in parts and parts[r].kind == "IC"]
    if len(drivers) != 1:
        return None, (f"{net_name} is driven by {len(drivers)} switches "
                      f"({sorted(p.refdes for p in drivers)}): nothing here "
                      f"can say what its current limit is")
    sw = drivers[0]
    key = next((k for k in _LIMITERS if sw.mpn.startswith(k)), None)
    if key is None:
        return None, (f"{sw.refdes} ({sw.mpn}) drives {net_name} and no "
                      f"current-limit equation here belongs to it: add one "
                      f"from its datasheet rather than guessing the ceiling")
    pin, equation = _LIMITERS[key]
    prog = d.net_of(sw.refdes, pin)
    if prog is None:
        return None, f"{sw.refdes} has no net on its {pin} pin"
    rs = [parts[r] for r, _ in prog.pins
          if r in parts and parts[r].kind == "R" and r != sw.refdes]
    ohms = {r.refdes: resistance(r.value) for r in rs}
    # `if v` drops both None (no resistance in the value) and 0 Ω: a link on a
    # programming pin does not state a limit either, and dividing by it would
    # invent an infinite one.
    readable = {k: v for k, v in ohms.items() if v}
    if len(readable) != 1:
        return None, (f"{sw.refdes}'s {pin} pin ({prog.name}) carries "
                      f"{len(readable)} readable resistors {sorted(readable)}: "
                      f"its current limit is not derivable")
    return equation(next(iter(readable.values()))), ""


def limit_case(d: Design | None = None) -> Limit:
    """What the aux block passes with every limiter at its upper threshold --
    the case the docstring above warns about, DERIVED rather than typed.

    It is the only case that threatens the choke or the tap fuse, so a change
    to a programming resistor must move this number and not a paragraph of
    prose. Change U303's R_CL from 1k5 to 1k2 and the figure moves.

    ⚠️ The base is `BASE_12V_A`, which is nominal: U301's and U302's own
    limits are not in this sum. And the 5 V branch is not capped at U305's
    5 A output rating either, which would hold it a little below four times a
    channel's limit -- both omissions make this figure conservative in the
    direction of asking MORE of the input path, which is the safe direction
    for sizing a fuse.
    """
    d = d if d is not None else netlist.current()
    lim = Limit()
    per = {}
    for rail in ("12", "5"):
        nets = _aux_nets(d, rail)
        amps = set()
        for name in nets:
            a, problem = _channel_limit_a(d, name)
            if problem:
                lim.problems.append(problem)
            else:
                amps.add(round(a, 6))
        if len(amps) > 1:
            lim.problems.append(
                f"the {rail} V aux channels do not share one current limit "
                f"({sorted(amps)} A): this sum assumes they do")
        per[rail] = (len(nets), next(iter(amps)) if len(amps) == 1 else None)
    lim.n12, lim.per_12v_a = per["12"]
    lim.n5, lim.per_5v_a = per["5"]
    if lim.problems or lim.per_12v_a is None or lim.per_5v_a is None:
        return lim
    lim.load_12v_a = (BASE_12V_A + lim.n12 * lim.per_12v_a
                      + lim.n5 * lim.per_5v_a * V5 / BUCK_EFF / V12
                      + (BUCK_STANDING_A if lim.n5 else 0.0))
    lim.conv_in_a = _conv_in_a(lim.load_12v_a)
    lim.tap_a = _tap_a(lim.conv_in_a)
    return lim


def budget(d: Design | None = None) -> Result:
    d = d if d is not None else netlist.current()
    n12 = len(_aux_nets(d, "12"))
    n5 = len(_aux_nets(d, "5"))
    aux12 = n12 * AUX_OUTPUT_A
    aux5 = n5 * AUX_OUTPUT_A * V5 / BUCK_EFF / V12
    # The buck is a permanent load on V12 because its enable is its input: the
    # 5 V rail exists for those channels, so their presence is what says so.
    standing = BUCK_STANDING_A if n5 else 0.0
    load = BASE_12V_A + aux12 + aux5 + standing
    conv_in = _conv_in_a(load)
    tap = _tap_a(conv_in)
    r = Result(load, conv_in, tap, aux12_a=aux12, aux5_a=aux5,
               buck_standing_a=standing)

    convs = _converters_12v(d)
    conv = convs[0] if convs else None
    r.converter = conv
    if conv is None:
        r.problems.append("no converter makes the 12 V rail: nothing carries "
                          "this load, and nothing here can say what it is "
                          "rated for")
    else:
        if len(convs) > 1:
            r.problems.append(
                f"{len(convs)} converters put an output on a 12 V net "
                f"({', '.join(p.refdes for p in convs)}): this check sizes ONE "
                f"input path, and two bricks on one rail share the load in a "
                f"way nobody here has stated")
        r.conv_rated_a = _rated_a(conv.value)
        if r.conv_rated_a is None:
            r.problems.append(f"{conv.refdes} ({conv.mpn}) states no current "
                              f"rating in its value {conv.value!r}")
        elif load > r.conv_rated_a * CONV_DERATE:
            r.problems.append(f"{conv.refdes} ({conv.mpn}) is asked for "
                              f"{load:.2f} A where it makes {r.conv_rated_a:g} A")

    chokes = _input_chokes(d, conv) if conv else ()
    choke = chokes[0] if chokes else None
    r.choke = choke
    if choke is None:
        r.problems.append("no common-mode choke stands in the 12 V "
                          "converter's input path: nothing limits what the "
                          "brick's switching puts back on the pack wiring, "
                          "and nothing here is sized against this load")
    else:
        if len(chokes) > 1:
            r.problems.append(
                f"{len(chokes)} common-mode chokes sit on {conv.refdes}'s "
                f"84 V input ({', '.join(p.refdes for p in chokes)}): the "
                f"input current would split between them in a ratio nobody "
                f"here has stated, and only the first is graded below")
        r.choke_rated_a = _rated_a(choke.value)
        if r.choke_rated_a is None:
            r.problems.append(f"{choke.refdes} ({choke.mpn}) states no current "
                              f"rating in its value {choke.value!r}: it cannot "
                              f"be held to this load")
        elif conv_in > r.choke_rated_a * CHOKE_DERATE:
            r.problems.append(
                f"{choke.refdes} ({choke.mpn}, {choke.value}) carries "
                f"{conv_in:.2f} A at the {LVC_V:g} V LVC: over "
                f"{CHOKE_DERATE:.0%} of its {r.choke_rated_a:g} A rating")

    if tap > TAP_FUSE_A * FUSE_DERATE:
        r.problems.append(f"the {TAP_FUSE_A:g} A tap fuse ({TAP_FUSE_MPN}) "
                          f"carries {tap:.2f} A at the LVC: over "
                          f"{FUSE_DERATE:.0%} of its rating")

    # ⚠️ The LIMITED figures are EXPECTED to exceed the choke and fuse derates
    # -- that case is eight simultaneous output faults. What is not acceptable
    # is being unable to derive it at all, because then the docstring's warning
    # is prose again and nothing re-checks it.
    r.limit = limit_case(d)
    r.problems += [f"the limit case is not derivable: {p}"
                   for p in r.limit.problems]
    return r


def _margin(carried: float, rated: float | None, derate: float) -> str:
    if rated is None:
        return "no rating to measure against"
    return (f"{carried:.2f} A of {rated:g} A = {carried / rated:.0%} "
            f"(gate {derate:.0%}, {rated * derate - carried:+.2f} A of margin)")


def _render(r: Result) -> str:
    lines = [f"12 V nominal load {r.load_12v_a:.2f} A (IO-2: every aux channel "
             f"at {AUX_OUTPUT_A:g} A -- base {BASE_12V_A:.2f} + 12 V aux "
             f"{r.aux12_a:.2f} + 5 V aux {r.aux5_a:.2f} + buck standing "
             f"{r.buck_standing_a * 1000:.2f} mA) · converter input "
             f"{r.conv_in_a:.2f} A · tap {r.tap_a:.2f} A at {LVC_V:g} V"]
    if r.converter is not None:
        lines.append(f"  {r.converter.refdes} ({r.converter.mpn})  "
                     + _margin(r.load_12v_a, r.conv_rated_a, CONV_DERATE))
    if r.choke is not None:
        lines.append(f"  {r.choke.refdes} ({r.choke.mpn}, {r.choke.value})  "
                     + _margin(r.conv_in_a, r.choke_rated_a, CHOKE_DERATE))
    lines.append(f"  tap fuse ({TAP_FUSE_MPN}, harness)  "
                 + _margin(r.tap_a, TAP_FUSE_A, FUSE_DERATE))
    lim = r.limit
    if lim.load_12v_a is not None:
        choke = (f"{lim.conv_in_a / r.choke_rated_a:.0%} of the choke"
                 if r.choke_rated_a else "no choke rating to measure against")
        lines.append(
            f"LIMITED {lim.load_12v_a:.2f} A at 12 V -- every limiter at its "
            f"upper threshold ({lim.n12} × {lim.per_12v_a:.2f} A + {lim.n5} × "
            f"{lim.per_5v_a:.2f} A over the {BASE_12V_A:.2f} A nominal base) · "
            f"converter input {lim.conv_in_a:.2f} A ({choke}) · tap "
            f"{lim.tap_a:.2f} A ({lim.tap_a / TAP_FUSE_A:.0%} of the fuse). "
            f"{lim.n12 + lim.n5} simultaneous output faults: over the derates "
            f"by design, and NOT what the gates above size the input path "
            f"against")
    lines.append(
        f"SHED {r.shed_load_12v_a:.2f} A at 12 V -- every aux channel "
        f"RELEASED, which the firmware does on key-off (IO-16) · converter "
        f"input {r.shed_conv_in_a:.2f} A · tap {r.shed_tap_a:.2f} A at "
        f"{LVC_V:g} V, the load tools/soft_start.py holds Q101's key-off SOA "
        f"to. ⚠️ The {r.buck_standing_a * 1000:.2f} mA buck standing draw is "
        f"INSIDE it: U305's EN is tied to its own PVIN, so no firmware can "
        f"release the 5 V rail")
    lines += [f"  ⛔ {p}" for p in r.problems]
    lines.append("FAIL" if r.problems else "PASS")
    return "\n".join(lines)


def report(d: Design | None = None) -> str:
    return _render(budget(d))


def main() -> int:
    try:
        d = netlist.checked()
    except netlist.NotACircuit as e:
        print(f"⛔ REFUSED -- {e}")
        return 1
    r = budget(d)
    print(_render(r))
    return 1 if r.problems else 0


if __name__ == "__main__":
    sys.exit(main())
