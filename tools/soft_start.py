#!/usr/bin/env python3
"""D13 soft start -- what the gate network around Q101 actually does.

Q101 (`IXTA26P20P`, P-channel, high side) connects the pack to the module's
440 µF of bulk capacitance. The inrush energy has to go somewhere and the soft
start deliberately puts it in the MOSFET, so the MOSFET lives or dies on its
safe operating area (SOA), and the ramp time is what buys the margin.

The circuit (HVIN, refdes as netlisted):

    HV_BPLUS ──┬─────────┬─────────┬──────── Q101.S
             R110      D102      C107
             100 k     15 V      4.7 µF
               └────┬────┴─────────┘
                D13_GATE ─── Q101.G
                    │   └── C105 68 nF ───── HV_SW (Q101.D) ── 440 µF + load
                  R101A+R101B  540 k  (2 × 270 k)
                    │
                  D13_PD ── Q105 BSS127 ── GND        (Q105 is ON only with
                                                       the key on: D13_EN)

Three currents meet at the gate while the drain slews (the Miller plateau):

    I(C105) = I(R101) − I(R110) = (V_pack − V_pl)/R_PD − V_pl/R_GS

⚠️ R110 OPPOSES the pull-down: its current is subtracted, never the one that
charges C105. With R_PD absent the gate has no path off the source at all and
the FET never turns on. Both are pinned in tests/test_soft_start.py.

C107 does not set the ramp. It is there for the XT90-S plug-in with the key
OFF: a fast source edge is coupled into the gate by C105, and C107 divides it
down to C105/(C105 + C107) of the step -- under the FET's threshold.

This is a lumped model, not SPICE: square-law FET, ideal zener, ideal
capacitors (C105 is specified C0G/film so it does not lose capacitance under
bias). It needs nothing but the standard library.

    python3 tools/soft_start.py          # report; exit 1 on any FAIL

The run reads the gate network OFF THE NETLIST (`circuit_from`), by following
the copper round Q101 -- so a resistor changed there is simulated here, and a
pull-down path that does not exist there is reported as one. `SPEC` below is
the specified circuit, used when no netlist can be read, and the run says
which it used and where the two differ.
"""
import math
import pathlib
import re
import sys
from dataclasses import dataclass, fields, replace

# ── Q101 IXTA26P20P -- IXYS DS99913D (01/13): the IXTP's die in TO-263 ─────
VTH_MIN, VTH_MAX = 2.0, 4.0      # |V_GS(th)| at 250 µA, p.1
VTH_NOM = 3.0                    # midpoint; the sheet gives no typical
GFS_MIN_S, GFS_TYP_S = 10.0, 17.0   # at I_D = 13 A, p.2
GFS_TEST_A = 13.0
C_ISS, C_RSS = 2740e-12, 100e-12    # p.2, at V_DS = 25 V
VGS_ABS_MAX = 20.0               # V_GSS, p.1 -> D102 must clamp inside it
#: SOA read off DS99913D Fig. 14 (T_C = 70 °C) at V_DS = 84 V, ±10 % by eye:
#: (pulse width s, allowed power W). DC is the last row.
SOA_84V_TC70 = ((0.010, 460.0), (0.100, 254.0))
SOA_DC_84V_TC70 = 191.0
#: Margin applied to every SOA figure. (150 − 60)/(150 − 25) = 0.72 is the
#: derate for a 60 °C case against a 25 °C plot; Fig. 14 is already drawn at
#: 70 °C, so here it is pure margin -- kept because the figures were read by
#: eye off a log plot and the enclosure's temperature is not yet known.
SOA_DERATE = 0.72


def k_from_gfs(gfs_s: float, at_amps: float = GFS_TEST_A) -> float:
    """Square-law constant K (A/V²) from a transconductance at a current.

    I = K·V_ov² gives g_fs = 2·sqrt(K·I), so K = g_fs² / (4·I).
    """
    return gfs_s * gfs_s / (4.0 * at_amps)


# ── the load Q101 has to charge ────────────────────────────────────────────
V_PACK_FULL = 84.0     # worst case for stored energy and for V_DS
V_LVC = 60.0           # low-voltage cutoff: least gate drive, slowest ramp
C_LOAD = 440e-6        # C201 + C202, 220 µF each
I_LOAD_MAX = 0.62      # measured module draw at the 60 V cutoff
P_LOAD = I_LOAD_MAX * V_LVC    # the converters are constant-power above it
#: SMCJ90A maximum clamping voltage at I_PP (Littelfuse SMCJ series table).
#: The most the source node can reach while D101 stands.
V_TVS_CLAMP = 146.0

# ── Q105's gate (D13_EN): KSW -> R112A+R112B -> D13_EN -> R113 -> GND ─────
R_EN_TOP, R_EN_BOTTOM = 998e3, 100e3     # 2 x 499 k over 100 k: 7.6 V at 84 V
C_EN = 100e-9                            # C108: rides out key-contact bounce
V_EN_CLAMP = 10.0                        # D106
Q105_VTH_MAX = 2.6                       # BSS127 V_GS(th) 1.4-2.6 V: the late one

#: The ramp asked for is ~50 ms. The band is held at full charge with a
#: mid-threshold FET; the corners are reported beside it. Slower costs the FET
#: less power, not more, so a slow corner is not a failure -- the SOA check is.
RAMP_TARGET_S = (0.040, 0.070)


@dataclass(frozen=True)
class Circuit:
    """The gate network. `r_pd=None` means no pull-down path exists."""
    r_gs: float = 100e3            # R110, gate-source
    r_pd: float | None = 540e3     # R101A + R101B = 2 × 270 k, gate to ground via Q105
    c_gd: float = 68e-9            # C105, gate-drain (the Miller capacitor)
    c_gs: float = 4.7e-6           # C107, gate-source
    v_zener: float = 15.0          # D102


@dataclass(frozen=True)
class Fet:
    v_th: float = VTH_NOM
    k: float = k_from_gfs(GFS_TYP_S)

    def current(self, v_sg: float, v_sd: float) -> float:
        v_ov = v_sg - self.v_th
        if v_ov <= 0.0 or v_sd <= 0.0:
            return 0.0
        if v_sd < v_ov:
            return self.k * (2.0 * v_ov * v_sd - v_sd * v_sd)
        return self.k * v_ov * v_ov


SPEC = Circuit()
NOMINAL = Fet()
#: Fastest ramp = most power: lowest threshold, most gain.
FAST = Fet(v_th=VTH_MIN, k=k_from_gfs(GFS_TYP_S))
#: Slowest ramp, latest turn-on: highest threshold, least gain.
SLOW = Fet(v_th=VTH_MAX, k=k_from_gfs(GFS_MIN_S))


_R_VALUE = re.compile(r"^(\d+(?:\.\d+)?)([RkM])(\d*)")      # 270k  1k00  5k1  0R
_C_VALUE = re.compile(r"^(\d+(?:\.\d+)?)\s*([pnuµ])F")        # 68nF  4.7uF
_V_VALUE = re.compile(r"^(\d+(?:\.\d+)?)\s*V")                # 15V
_MULT = {"R": 1.0, "k": 1e3, "M": 1e6, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6}


def _value(part) -> float:
    """A netlist part's `value` string in ohms, farads or volts."""
    kind_re = {"R": _R_VALUE, "C": _C_VALUE, "ZENER": _V_VALUE}[part.kind]
    m = kind_re.match(part.value.strip())
    if not m:
        raise ValueError(f"{part.refdes}: cannot read a value out of {part.value!r}")
    if part.kind == "R":
        return float(f"{m.group(1)}.{m.group(3) or 0}" if m.group(3)
                     else m.group(1)) * _MULT[m.group(2)]
    return float(m.group(1)) * (_MULT[m.group(2)] if part.kind == "C" else 1.0)


def circuit_from(d, switch: str = "Q101") -> Circuit:
    """The gate network as the netlist has it, read by following the copper.

    Nothing is looked up by refdes except the switch itself: R_GS, C_GS and
    the zener are whatever fitted two-pin parts join gate to source; C_GD joins
    gate to drain; R_PD is the chain of series resistors from the gate to the
    drain of an N-FET whose source is on a ground net. No such chain -> None,
    which is a switch that can never turn on.
    """
    gate, source, drain = (d.net_of(switch, pin) for pin in ("G", "S", "D"))
    if None in (gate, source, drain):
        raise ValueError(f"{switch} has a pin on no net")
    parts = {p.refdes: p for p in d.parts if not p.dnp and len(p.pins) == 2}

    def far_end(ref, near):
        nets = [n for n in d.nets_of(ref) if n.name != near.name]
        return nets[0] if len(nets) == 1 else None

    def between(a, b, kind):
        return [parts[r] for r, _ in a.pins if r in parts and parts[r].kind == kind
                and (far_end(r, a) or a).name == b.name]

    def grounded_switch(net) -> bool:
        for ref, pin in net.pins:
            if pin == "D" and d.has(ref) and d.part(ref).kind == "NFET":
                low = d.net_of(ref, "S")
                if low is not None and low.domain == "GND":
                    return True
        return False

    def pull_down(net, seen):
        if grounded_switch(net):
            return 0.0
        for ref, _ in net.pins:
            if ref in parts and parts[ref].kind == "R" and ref not in seen:
                nxt = far_end(ref, net)
                if nxt is None or nxt.name in (source.name, drain.name):
                    continue
                rest = pull_down(nxt, seen | {ref})
                if rest is not None:
                    return _value(parts[ref]) + rest
        return None

    r_gs = between(gate, source, "R")
    zener = between(gate, source, "ZENER")
    if not r_gs or not zener:
        raise ValueError(f"{switch}: no gate-source resistor or no gate zener -- "
                         f"the gate is not biased OFF or not clamped")
    return Circuit(
        r_gs=1.0 / sum(1.0 / _value(p) for p in r_gs),
        r_pd=pull_down(gate, frozenset()),
        c_gd=sum(_value(p) for p in between(gate, drain, "C")),
        c_gs=sum(_value(p) for p in between(gate, source, "C")),
        v_zener=min(_value(p) for p in zener))


def differences(a: Circuit, b: Circuit, rel: float = 1e-9) -> list[str]:
    """Which elements of two circuits differ, as readable text."""
    out = []
    for f in fields(Circuit):
        x, y = getattr(a, f.name), getattr(b, f.name)
        if (x is None) != (y is None) or (
                x is not None and not math.isclose(x, y, rel_tol=rel, abs_tol=1e-15)):
            out.append(f"{f.name}: {x if x is None else format(x, 'g')} vs "
                       f"{y if y is None else format(y, 'g')}")
    return out


def load_current(v_d: float) -> float:
    """Converter draw at an input voltage of `v_d`.

    Constant power above the cutoff voltage, capped at the measured 0.62 A
    below it. ⚠️ Deliberately pessimistic: the real converters sit in
    under-voltage lock-out for the first part of the ramp and draw nothing.
    """
    if v_d <= 0.0:
        return 0.0
    if v_d < 1.0:
        return I_LOAD_MAX * v_d          # no draw from a node that is at 0 V
    return min(I_LOAD_MAX, P_LOAD / v_d)


def soa_limit_w(pulse_s: float) -> float:
    """Derated power Q101 may dissipate for an equal-energy square pulse.

    Log-log between the 10 ms and 100 ms lines. Shorter than 10 ms is held at
    the 10 ms figure and longer than 100 ms at the DC figure -- both choices
    understate what the part can take. The lines are read at V_DS = 84 V;
    at a lower pack voltage the true limit is no lower.
    """
    (t0, p0), (t1, p1) = SOA_84V_TC70
    if pulse_s <= t0:
        raw = p0
    elif pulse_s <= t1:
        f = math.log(pulse_s / t0) / math.log(t1 / t0)
        raw = math.exp(math.log(p0) + f * math.log(p1 / p0))
    else:
        raw = SOA_DC_84V_TC70
    return raw * SOA_DERATE


def static_v_sg(v_pack: float, c: Circuit = SPEC) -> float:
    """Gate drive once everything has settled, key on."""
    if c.r_pd is None:
        return 0.0
    return min(c.v_zener, v_pack * c.r_gs / (c.r_gs + c.r_pd))


#: (top ohms, bottom ohms, farads) of the divider on the level shifter's gate.
SPEC_ENABLE = (R_EN_TOP, R_EN_BOTTOM, C_EN)


def enable_from(d, switch: str = "Q101", key_net: str = "KSW"):
    """The level shifter's gate divider as netlisted: (top, bottom, cap).

    Follows the copper from the grounded N-FET under `switch`'s pull-down: the
    resistor(s) from its gate to GND are the bottom, the series chain from its
    gate to the key wire is the top, the capacitor(s) from its gate to GND the
    filter. Raises if the shifter's gate has no divider -- a gate nobody drives.
    """
    parts = {p.refdes: p for p in d.parts if not p.dnp and len(p.pins) == 2}
    shifter = None
    for p in d.parts:
        if p.kind == "NFET" and not p.dnp:
            low, dr = d.net_of(p.refdes, "S"), d.net_of(p.refdes, "D")
            if low is not None and low.domain == "GND" and dr is not None \
                    and d.net_of(switch, "G") is not None:
                shifter = p
                break
    if shifter is None:
        raise ValueError("no grounded N-FET level shifter found")
    gate = d.net_of(shifter.refdes, "G")
    if gate is None:
        raise ValueError(f"{shifter.refdes} has no gate net")

    def far(ref, near):
        nets = [n for n in d.nets_of(ref) if n.name != near.name]
        return nets[0] if len(nets) == 1 else None

    bottom = [parts[r] for r, _ in gate.pins if r in parts and parts[r].kind == "R"
              and (far(r, gate) is not None and far(r, gate).domain == "GND")]
    caps = [parts[r] for r, _ in gate.pins if r in parts and parts[r].kind == "C"
            and (far(r, gate) is not None and far(r, gate).domain == "GND")]

    def chain(net, seen):
        if net.name == key_net:
            return 0.0
        for r, _ in net.pins:
            if r in parts and parts[r].kind == "R" and r not in seen:
                nxt = far(r, net)
                if nxt is None or nxt.domain == "GND":
                    continue
                rest = chain(nxt, seen | {r})
                if rest is not None:
                    return _value(parts[r]) + rest
        return None

    top = chain(gate, frozenset())
    if not bottom or top is None:
        raise ValueError(f"{shifter.refdes}: its gate has no divider from "
                         f"{key_net} -- nothing drives the level shifter")
    return (top, 1.0 / sum(1.0 / _value(p) for p in bottom),
            sum(_value(p) for p in caps))


def enable_level_v(v_pack: float, en=SPEC_ENABLE) -> float:
    top, bottom, _c = en
    return min(V_EN_CLAMP, v_pack * bottom / (top + bottom))


def enable_delay_s(v_pack: float, en=SPEC_ENABLE) -> float:
    """Key on -> Q105 conducting: D13_EN's RC up to the BSS127's worst threshold."""
    top, bottom, c_en = en
    v_final = enable_level_v(v_pack, en)
    if v_final <= Q105_VTH_MAX:
        return math.inf
    tau = (top * bottom / (top + bottom)) * c_en
    return -tau * math.log(1.0 - Q105_VTH_MAX / v_final)


def miller_estimate_s(v_pack: float, c: Circuit = SPEC, fet: Fet = NOMINAL,
                      ramp_guess_s: float = 0.05) -> float:
    """Closed-form ramp from KCL at the gate. An independent check on the ODE.

    Valid when the gate sits still during the ramp, i.e. WITHOUT a large
    gate-source capacitor; with C107 fitted the ramp starts softer and the
    ODE is the answer.
    """
    if c.r_pd is None:
        return math.inf
    t = ramp_guess_s
    for _ in range(50):                 # the plateau depends on the current,
        i_d = C_LOAD * v_pack / t + load_current(v_pack / 2)   # which depends on t
        v_pl = fet.v_th + math.sqrt(i_d / fet.k)
        i_m = (v_pack - v_pl) / c.r_pd - v_pl / c.r_gs
        if i_m <= 0.0:
            return math.inf
        t = (c.c_gd + C_RSS) * v_pack / i_m
    return t


@dataclass(frozen=True)
class KeyOn:
    """One key-on event at one pack voltage."""
    v_pack: float
    turns_on: bool
    why_not: str = ""
    enable_delay_s: float = 0.0       # key -> Q105 on
    gate_delay_s: float = 0.0         # Q105 on -> Q101 at threshold
    ramp_s: float = math.inf          # HV_SW 10 %->90 %, /0.8 (full-swing equivalent)
    i_peak_a: float = 0.0
    p_peak_w: float = 0.0
    energy_j: float = 0.0             # dissipated in Q101 over the event
    v_sg_on: float = 0.0              # settled gate drive

    @property
    def turn_on_delay_s(self) -> float:
        return self.enable_delay_s + self.gate_delay_s

    @property
    def pulse_s(self) -> float:
        """Width of the square pulse at P_peak that carries the same energy."""
        return self.energy_j / self.p_peak_w if self.p_peak_w else 0.0

    @property
    def soa_limit_w(self) -> float:
        return soa_limit_w(self.pulse_s)

    @property
    def soa_ok(self) -> bool:
        return self.turns_on and self.p_peak_w <= self.soa_limit_w


def _step(c: Circuit, fet: Fet, pulled_down: bool, v_s: float, dv_s: float,
          v_g: float, v_d: float, dt: float):
    """Advance gate and drain by `dt`. Returns (v_g, v_d, i_fet, p_fet).

    The drain uses an exponential step on the FET's secant conductance, so the
    last part of the ramp (a few milliohms into 440 µF) is stable at any `dt`.
    The source may move by `dv_s` within the step: charge is conserved across
    C105 and C107 exactly, so an ideal edge needs no tiny time step.
    """
    c_gs, c_gd = c.c_gs + (C_ISS - C_RSS), c.c_gd + C_RSS
    v_sd = v_s - v_d
    i_f = fet.current(v_s - v_g, v_sd)
    i_l = load_current(v_d)
    if i_f > 0.0:
        g = i_f / v_sd
        v_inf = v_s - i_l / g
        v_d_new = v_inf + (v_d - v_inf) * math.exp(-g * dt / C_LOAD)
    else:
        v_d_new = v_d - i_l * dt / C_LOAD
    v_d_new = max(v_d_new, 0.0)
    i_g = (v_s - v_g) / c.r_gs
    if pulled_down:
        i_g -= v_g / c.r_pd
    v_s_new = v_s + dv_s
    v_g_new = v_g + (i_g * dt + c_gs * dv_s + c_gd * (v_d_new - v_d)) / (c_gs + c_gd)
    v_g_new = max(v_g_new, v_s_new - c.v_zener)      # D102 in breakdown
    v_g_new = min(v_g_new, v_s_new + 0.7)            # D102 forward
    return v_g_new, v_d_new, i_f, i_f * v_sd


def simulate_key_on(v_pack: float = V_PACK_FULL, c: Circuit = SPEC,
                    fet: Fet = NOMINAL, dt: float = 10e-6,
                    give_up_s: float = 3.0) -> KeyOn:
    """Key on with the pack already connected and HV_SW discharged.

    Fixed-step integration. At the 10 µs default the ramp and the peak power
    move by under 0.1 % when the step is halved, and the result matches an
    adaptive stiff solver run on the same equations to four figures.

    Wiring and fuse resistance are left out: they sit upstream of Q101's
    source AND of the gate network's reference, so they do not degenerate the
    FET, and leaving them out puts every watt in the FET.
    """
    if c.r_pd is None:
        return KeyOn(v_pack, False,
                     "never turns on: no pull-down path, R110 holds V_GS at 0")
    v_on = static_v_sg(v_pack, c)
    if v_on <= fet.v_th:
        return KeyOn(v_pack, False,
                     f"never turns on: the divider settles at V_GS = -{v_on:.2f} V, "
                     f"short of the {fet.v_th:.1f} V threshold", v_sg_on=v_on)
    t_enable = enable_delay_s(v_pack)
    if math.isinf(t_enable):
        return KeyOn(v_pack, False, "never turns on: D13_EN stays under Q105's threshold")
    # Below threshold nothing conducts and HV_SW sits at 0 V, so the gate is a
    # plain RC toward the divider voltage: no need to integrate it.
    c_tot = c.c_gs + c.c_gd + C_ISS
    tau = (c.r_gs * c.r_pd / (c.r_gs + c.r_pd)) * c_tot
    v_aim = v_pack * c.r_gs / (c.r_gs + c.r_pd)
    t_gate = -tau * math.log(1.0 - fet.v_th / v_aim)

    v_g, v_d, t = v_pack - fet.v_th, 0.0, 0.0
    t10 = t90 = None
    i_peak = p_peak = energy = 0.0
    while t < give_up_s:
        v_g, v_d, i_f, p_f = _step(c, fet, True, v_pack, 0.0, v_g, v_d, dt)
        t += dt
        energy += p_f * dt
        i_peak, p_peak = max(i_peak, i_f), max(p_peak, p_f)
        if t10 is None and v_d >= 0.1 * v_pack:
            t10 = t
        if t90 is None and v_d >= 0.9 * v_pack:
            t90 = t
        if v_pack - v_d < 0.05:
            break
    if t90 is None:
        return KeyOn(v_pack, False,
                     f"HV_SW has not reached 90 % within {give_up_s:.0f} s of Q101's threshold",
                     t_enable, t_gate, v_sg_on=v_on)
    return KeyOn(v_pack, True, "", t_enable, t_gate, (t90 - t10) / 0.8,
                 i_peak, p_peak, energy, v_on)


@dataclass(frozen=True)
class PlugIn:
    """The pack being connected with the key OFF (Q105 off: no pull-down)."""
    v_step: float
    v_sg_peak: float
    hv_sw_peak: float          # how far the module's bulk caps got charged
    limit: float = VTH_MIN

    @property
    def ok(self) -> bool:
        return self.v_sg_peak < self.limit


def plug_in(v_step: float = V_PACK_FULL, c: Circuit = SPEC,
            fet: Fet = FAST, dt: float = 1e-6, watch_s: float = 0.02) -> PlugIn:
    """Source steps 0 -> `v_step` in ONE step with the key off.

    An ideal edge is the worst case: any slower one gives R110 time to bleed
    the gate. The XT90-S pre-charge contact only makes it gentler.
    """
    v_g, v_d = 0.0, 0.0
    v_g, v_d, _, _ = _step(c, fet, False, 0.0, v_step, v_g, v_d, dt)
    v_sg_peak, hv_sw_peak, t = v_step - v_g, v_d, 0.0
    while t < watch_s:
        v_g, v_d, _, _ = _step(c, fet, False, v_step, 0.0, v_g, v_d, dt)
        t += dt
        v_sg_peak, hv_sw_peak = max(v_sg_peak, v_step - v_g), max(hv_sw_peak, v_d)
    return PlugIn(v_step, v_sg_peak, hv_sw_peak)


def key_off_delay_s(v_pack: float = V_PACK_FULL, c: Circuit = SPEC,
                    fet: Fet = FAST) -> float:
    """Key off -> Q101 starting to pinch off: C107 discharging through R110.
    Longest for the lowest-threshold FET, which is the default.

    The price of C107. HV_SW then ramps DOWN at about V_pl/(R_GS·C105), with
    Q101 carrying only the load, so it can never dissipate more than
    I_load × V_pack on the way.
    """
    v_pl = fet.v_th + math.sqrt(I_LOAD_MAX / fet.k)
    v_on = static_v_sg(v_pack, c)
    if v_on <= v_pl:
        return 0.0
    return c.r_gs * (c.c_gs + c.c_gd + C_ISS) * math.log(v_on / v_pl)


def solve_r_pd(target_ramp_s: float, v_pack: float = V_PACK_FULL,
               c: Circuit = SPEC, fet: Fet = NOMINAL) -> float:
    """The pull-down resistance that gives `target_ramp_s`, everything else as `c`.

    Bisection on the simulated ramp, which rises monotonically with R_PD.
    Raises ValueError when no value can: above R_GS·(V/V_th − 1) the divider
    never reaches threshold.
    """
    def ramp(r_pd, dt=20e-6):          # coarse while searching, checked below
        return simulate_key_on(v_pack, replace(c, r_pd=r_pd), fet, dt).ramp_s

    lo, hi = 1e3, 0.98 * c.r_gs * (v_pack / fet.v_th - 1.0)
    if not ramp(lo) <= target_ramp_s <= ramp(hi):
        raise ValueError(
            f"no R_PD between {lo/1e3:.0f} k and {hi/1e3:.0f} k gives a "
            f"{target_ramp_s*1e3:.0f} ms ramp at {v_pack:.0f} V")
    for _ in range(40):
        mid = math.sqrt(lo * hi)
        if ramp(mid) < target_ramp_s:
            lo = mid
        else:
            hi = mid
        if hi / lo < 1.002:
            break
    r_pd = math.sqrt(lo * hi)
    # The bisection also converges on the edge where the FET stops turning on
    # at all (ramp = inf). That is not an answer.
    if not math.isclose(ramp(r_pd, 10e-6), target_ramp_s, rel_tol=0.02):
        raise ValueError(
            f"no R_PD gives a {target_ramp_s*1e3:.0f} ms ramp at {v_pack:.0f} V: "
            f"by {r_pd/1e3:.0f} k the FET no longer turns on")
    return r_pd


#: The converters run down to 43 V. The level shifter must still be hard on
#: there, or the module browns out before the pack reaches its cutoff.
V_CONVERTER_MIN = 43.0


def assess(c: Circuit = SPEC, en=SPEC_ENABLE) -> list[str]:
    """Every way `c` (and the level shifter's gate divider `en`) fails."""
    fails = []
    for v in (V_CONVERTER_MIN, V_LVC):
        level = enable_level_v(v, en)
        if level <= Q105_VTH_MAX:
            fails.append(
                f"level shifter: D13_EN is only {level:.2f} V at a {v:.0f} V pack, "
                f"not above the BSS127's {Q105_VTH_MAX} V worst-case threshold -- "
                f"Q105 may not turn on, so Q101 never does")
    for v in (V_PACK_FULL, V_LVC):
        for name, fet in (("fast", FAST), ("nominal", NOMINAL), ("slow", SLOW)):
            r = simulate_key_on(v, c, fet)
            tag = f"{v:.0f} V, {name} FET (V_th {fet.v_th:.1f} V)"
            if not r.turns_on:
                fails.append(f"{tag}: {r.why_not}")
                continue
            if not r.soa_ok:
                fails.append(
                    f"{tag}: over the SOA target -- {r.p_peak_w:.0f} W peak as a "
                    f"{r.pulse_s*1e3:.1f} ms pulse, {r.soa_limit_w:.0f} W allowed "
                    f"(x{SOA_DERATE} derate)")
            # (the settled V_GS is already clamped by the zener, so comparing IT
            # with the rating could never fire -- the clamp itself is checked
            # once, below)
    if c.v_zener >= VGS_ABS_MAX:
        fails.append(f"D102 clamps at {c.v_zener:.0f} V, which is not inside the "
                     f"{VGS_ABS_MAX:.0f} V gate rating it exists to protect")
    nominal = simulate_key_on(V_PACK_FULL, c, NOMINAL)
    if nominal.turns_on and not RAMP_TARGET_S[0] <= nominal.ramp_s <= RAMP_TARGET_S[1]:
        fails.append(
            f"ramp {nominal.ramp_s*1e3:.1f} ms at {V_PACK_FULL:.0f} V is outside the "
            f"{RAMP_TARGET_S[0]*1e3:.0f}-{RAMP_TARGET_S[1]*1e3:.0f} ms target")
    p = plug_in(V_PACK_FULL, c)
    if not p.ok:
        fails.append(
            f"key-OFF plug-in: an {p.v_step:.0f} V step drives V_GS to "
            f"-{p.v_sg_peak:.2f} V, past the {p.limit:.1f} V minimum threshold -- "
            f"Q101 conducts with the key off (HV_SW reaches {p.hv_sw_peak:.1f} V)")
    return fails


def _netlisted() -> tuple[Circuit | None, str]:
    """(the netlist's gate network, "") or (None, why it could not be read)."""
    root = str(pathlib.Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from tools import netlist
        d = netlist.current()
        return (circuit_from(d), enable_from(d)), ""
    except Exception as exc:              # any failure is reported, never hidden
        return None, f"{type(exc).__name__}: {exc}"


def main(argv=None, c: Circuit | None = None) -> int:
    print("D13 SOFT START -- Q101 IXTA26P20P into "
          f"{C_LOAD*1e6:.0f} µF + {I_LOAD_MAX} A (constant power above {V_LVC:.0f} V)")
    en = SPEC_ENABLE
    if c is None:
        if argv and "--spec" in argv:
            c = SPEC
            print("  circuit: the SPECIFIED values (--spec). This says nothing about "
                  "the netlist.")
        else:
            read, why_not = _netlisted()
            if read is None:
                # A tool that cannot read the design must not report on it. Falling
                # back to the specified values here once printed PASS for a netlist
                # whose gate-source resistor had been deleted.
                print(f"⛔ FAIL -- the D13 gate network could not be read off the "
                      f"netlist: {why_not}\n   (use --spec to simulate the specified "
                      f"values instead)")
                return 1
            c, en = read
            print("  circuit: read off tools/netlist.py")
            for diff in differences(c, SPEC):
                print(f"  ⚠️ netlist vs specified -- {diff}")
            print(f"  level shifter gate: {en[0]/1e3:.0f} k over {en[1]/1e3:.0f} k, "
                  f"{en[2]*1e9:.0f} nF -> {enable_level_v(V_PACK_FULL, en):.1f} V at "
                  f"{V_PACK_FULL:.0f} V, {enable_level_v(V_CONVERTER_MIN, en):.1f} V at "
                  f"{V_CONVERTER_MIN:.0f} V (BSS127 V_th ≤ {Q105_VTH_MAX} V)")
    r_pd = "ABSENT" if c.r_pd is None else f"{c.r_pd/1e3:.0f} k"
    print(f"  R110 {c.r_gs/1e3:.0f} k   R101 {r_pd}   C105 {c.c_gd*1e9:.0f} nF"
          f"   C107 {c.c_gs*1e6:.1f} µF   D102 {c.v_zener:.0f} V\n")
    print("KEY ON")
    print(f"  {'pack':>5} {'FET':8} {'V_th':>5} {'delay':>8} {'ramp':>8} {'I pk':>6} "
          f"{'P pk':>6} {'E':>6} {'pulse':>7} {'SOA':>6}  {'V_GS on':>7}")
    for v in (V_PACK_FULL, V_LVC):
        for name, fet in (("fast", FAST), ("nominal", NOMINAL), ("slow", SLOW)):
            r = simulate_key_on(v, c, fet)
            if not r.turns_on:
                print(f"  {v:4.0f}V {name:8} {fet.v_th:5.1f}  ⛔ {r.why_not}")
                continue
            print(f"  {v:4.0f}V {name:8} {fet.v_th:5.1f} {r.turn_on_delay_s*1e3:6.0f}ms "
                  f"{r.ramp_s*1e3:6.1f}ms {r.i_peak_a:5.2f}A {r.p_peak_w:5.0f}W "
                  f"{r.energy_j:5.2f}J {r.pulse_s*1e3:5.1f}ms {r.soa_limit_w:5.0f}W"
                  f"  {-r.v_sg_on:6.1f}V  {'ok' if r.soa_ok else '⛔ OVER'}")
    print(f"  SOA = DS99913D Fig. 14 (T_C 70 °C, V_DS 84 V) x{SOA_DERATE}, at the "
          "equal-energy pulse width.")
    print(f"  ½CV² at {V_PACK_FULL:.0f} V is {0.5*C_LOAD*V_PACK_FULL**2:.2f} J; "
          "Q101 absorbs that plus the load's share.\n")

    print("KEY OFF, PACK PLUGGED IN (XT90-S)")
    p = plug_in(V_PACK_FULL, c)
    print(f"  {p.v_step:.0f} V ideal step   V_GS peaks at -{p.v_sg_peak:.2f} V   "
          f"(must stay under {p.limit:.1f} V, the minimum threshold)   "
          f"{'ok' if p.ok else '⛔ Q101 CONDUCTS'}")
    if p.ok:
        at_clamp = V_TVS_CLAMP * p.v_sg_peak / p.v_step
        leak = FAST.current(at_clamp, V_TVS_CLAMP)
        print(f"  ⚠️ bound, not an expectation: a plug-in that rings HV_BPLUS up to D101's "
              f"{V_TVS_CLAMP:.0f} V clamp\n     puts V_GS at -{at_clamp:.2f} V -> "
              f"{leak*1e3:.0f} mA through a minimum-threshold Q101 while the clamp lasts.")
    print("  ✔ Scope HV_SW and HV_BPLUS during a key-off plug-in.\n")

    print("KEY OFF")
    for v in (V_PACK_FULL, V_LVC):
        print(f"  {v:.0f} V: Q101 holds on for up to {key_off_delay_s(v, c)*1e3:.0f} ms "
              f"(C107 through R110), then carries at most "
              f"{I_LOAD_MAX*v:.0f} W on the way down -- "
              f"{'under' if I_LOAD_MAX*v <= SOA_DC_84V_TC70*SOA_DERATE else '⛔ OVER'} the "
              f"derated DC line, {SOA_DC_84V_TC70*SOA_DERATE:.0f} W.")
    print()

    print("R_PD FOR A TARGET RAMP (84 V, nominal FET)")
    for ms in (40, 50, 60, 70):
        print(f"  {ms} ms -> {solve_r_pd(ms/1e3, c=c)/1e3:5.0f} k")
    print()

    fails = assess(c, en)
    if fails:
        print("⛔ FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("✅ PASS -- turns on at every corner, inside the SOA target, ramp on "
          "target, and stays off when plugged in with the key off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
