"""Executable constraints -- each one checks the JOB, not the label.

A rule here never asks "is there a part with the right name on a net with the
right name". It asks the question the decision was taken to answer: is V_GS
zero with the driver dead, can current actually reach ground through this
clamp, can a rider's lever reach a strapping pin, does this part survive the
voltage across it. Everything that can be derived from connectivity IS derived:

  * "leaves the box" comes from the connectors, and for an MCU-side net from a
    walk through its series parts back to a box-leaving connector;
  * a FET's gate, source and drain are its `G`, `S`, `D` pins, so OFF is
    "a fitted resistor joins the gate net to the source net" for both polarities;
  * a net's voltage is the HIGHER of its declared domain and whatever pulls it
    up through resistors and forward diodes with no path to ground -- so a node
    typed `3V3` is still seen at the 12 V a pull-up resistor holds it at;
  * a GPIO is the `IOn` pin the net lands on, cross-checked against its tag.

Two kinds of walk, and the difference is deliberate:
  HAZARD walks (84 V containment, strapping, GPIO43, pull-up voltage) count a
  DNP part -- the footprint exists and can be populated.
  FUNCTION walks (bias, turn-on path, protection, ground joins) count only
  FITTED parts -- a job is not done by a part that is not there.

Every error string starts with a stable rule ID, then a colon:

  BD-2  BD-4
  GPIO-TAG  GPIO-DUP  GPIO-PAD  GPIO-43  GPIO-ADC1  GPIO-STRAP
  GPIO-RESET-PULL
  D14  TURN-ON  GATE-VGS
  VR-RATED  VR-DOMAIN  VR-UNDER  VR-STANDOFF  VR-DATASHEET
  LV-LOGIC  PROT  GND-ISLAND  MCP-OUT7  POL
  HT-NUM  HT-STACK  HT-GEOM  D10  SUPPLY  GND-PIN  BUS-ORDER  VR-CLAMP
  VR-POWER  PULL-DIR

`check_all(design)` returns the errors; `warnings(design)` returns what a human
must look at but a gate must not fail on (HT-W*, BOX-W*).

Silicon facts are read from tools/gpio_budget.py and the stack's geometry is
DERIVED by tools/board_params.py from the design's own heights; neither is
restated here, so neither can drift.

tests/test_rules.py proves every rule FIRES on the defect it names and stays
quiet on a real circuit; tests/test_design_clean.py holds the real netlist to
all of them.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict, deque

from . import board_params as _bp
from .model import (DOMAIN_VOLTS, Connector, Design, Part, is_cabled,
                    resistance)

try:                                    # silicon facts have ONE home when it exists
    from . import gpio_budget as _gb
except ImportError:                     # pragma: no cover - stdlib-only fallback
    _gb = None


# ── ESP32-S3 / WROOM-1 facts (plan 3.1.2) ────────────────────────────────────
def _silicon(name: str, local) -> frozenset[int]:
    got = getattr(_gb, name, None) if _gb is not None else None
    return frozenset(local if got is None else got)


GPIO_EXISTS = _silicon("EXISTS", set(range(0, 22)) | set(range(26, 49)))
GPIO_FLASH = _silicon("FLASH", range(26, 33))        # in-package SPI flash
GPIO_STRAPPING = _silicon("STRAPPING", {0, 3, 45, 46})
GPIO_ADC1 = _silicon("ADC1", range(1, 11))           # ADC2 dies with WiFi
GPIO_RESET_PULL_UP = _silicon("RESET_PULL_UP", {0, 20, 39, 43, 44})
GPIO_BOOT_LOG: int = getattr(_gb, "BOOT_LOG", 43) if _gb is not None else 43

#: The WROOM-1 module has no pad for these two (FIX-SPEC 3.4).
WROOM1_NOT_BROUGHT_OUT = _silicon("NOT_BROUGHT_OUT", {33, 34})

#: GPIOs a net may land on: silicon, minus flash, minus the missing pads.
MODULE_GPIOS = GPIO_EXISTS - GPIO_FLASH - WROOM1_NOT_BROUGHT_OUT

#: WROOM-1 pad names that are GPIOs under another name.
MCU_PIN_ALIASES = {"TXD0": 43, "U0TXD": 43, "RXD0": 44, "U0RXD": 44}

#: Nets read by the ADC. ADC2 is dead while WiFi is on, so these need GPIO1-10.
#: A net that walks to a driver's `CS` pin is analog whatever it is called.
ANALOG_NETS = frozenset(getattr(
    _gb, "ANALOG_NETS", {"CS1", "CS2", "KEY_SENSE", "V12_SENSE", "AMBIENT"}))

#: Absolute maximum on an ESP32-S3 pin (audit C-H5). Protects the MCU from any
#: net that is, or is pulled to, 5 V / 12 V / 84 V.
LOGIC_PIN_V_MAX = 3.6
#: An MCP23017 pin may sit this far above its own VDD (DS20001952).
MCP_PIN_OVER_VDD = 0.6

# ── board facts ──────────────────────────────────────────────────────────────
#: BD-2: 84 V stays on POWER. The TPS4H160B on OUTPUTS is a 40 V part.
LOW_VOLTAGE_BOARDS = frozenset({"OUTPUTS", "LOGIC"})
#: BD-4: 2.54 mm leaves ~0.7 mm pad edge to pad edge against IPC-2221's 0.6 mm.
HV_MIN_PITCH_MM = 5.08
#: A P-FET whose source sits at or above this cannot be driven from a logic
#: pin, so its turn-on path has to exist in copper.
HIGH_SIDE_VOLTS = 12.0

#: board_params DERIVES every gap from the design's own part and connector
#: heights; there is no typed ceiling to compare against. Only its two
#: outward-facing calls are used, never the shape of its gap records.
_stack_problems = getattr(_bp, "stack_problems", None)
_stack_height = getattr(_bp, "stack_height", None)
#: The plan axes of the cavity the design requires. Empty while M18 is an
#: estimate; a failure the moment the cavity is measured and the enclosure is
#: chosen. Relayed here so the rules gate and board_fit give the same answer.
_cavity_problems = getattr(_bp, "cavity_problems", None)
#: An unconfirmed height this close to setting its gap is reported, not trusted.
UNCONFIRMED_MARGIN_MM = 2.0

# ── part facts ───────────────────────────────────────────────────────────────
FETS = ("NFET", "PFET")
#: Kinds that must carry a voltage rating (model.Part.v_max).
RATED_KINDS = ("C", "D", "ZENER", "TVS", "NFET", "PFET", "R")


def _is_link(p: Part) -> bool:
    """A 0 R link or a copper net-tie: a conductor, with no voltage across it."""
    return p.kind == "R" and (p.mpn == "NET-TIE" or p.value.strip().upper() in ("0R", "0"))


def _kind(p: Part) -> str:
    """The kind a walk sees. A 0 R link, a net-tie and any MECH part landed on
    two nets (a jumper, a standoff bonding two planes) are one thing: LINK, a
    plain conductor. Everything else is its own kind."""
    if _is_link(p) or (p.kind == "MECH" and len(p.pins) >= 2):
        return "LINK"
    return p.kind


#: Diode-like kinds: each conducts forward, anode to cathode, whatever it is
#: sold as -- a TVS or zener is a diode first.
_DIODES = ("D", "ZENER", "TVS")
#: What a DC path may pass through both ways. A fuse holder is not one: its two
#: clips meet only through the fuse it holds, and the fuse is the FUSE part.
_SERIES = ("R", "L", "FUSE", "LINK")
_HAZARD_PATH = _SERIES + _DIODES + ("CMCHOKE",) + FETS
#: Low-impedance joins: what can carry pack voltage somewhere. Not resistors
#: (the dividers), but a link is a wire whatever its package.
_HV_JOIN = ("L", "FUSE", "LINK", "CMCHOKE") + _DIODES + FETS
#: What makes two ground-typed nets one ground: copper, not a resistor. A
#: clamp returned through 10 k is not grounded.
_GROUND_JOIN = ("LINK", "L", "FUSE", "CMCHOKE")

#: Multi-pin protection parts whose pins are named by role, not A/K or the
#: SMS arrays' A2/K1: MPN prefix -> (diodes as (anode pin, cathode pin), pins
#: joined inside), typed from the part's datasheet.  None on the board today.
_TVS_TOPOLOGY: dict[str, tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]] = {}


def _diodes(p: Part) -> tuple[list[tuple[str, str]], list[tuple[str, str]]] | None:
    """(forward diodes as (anode, cathode), pins joined inside) of a diode-like
    part, from its pin ROLES; None when the pins carry no roles."""
    pins = set(p.pins)
    if pins == {"A", "K"}:
        return [("A", "K")], []
    for prefix, (diodes, joined) in _TVS_TOPOLOGY.items():
        if p.mpn.upper().startswith(prefix):
            return list(diodes), list(joined)
    anodes = [x for x in p.pins if re.fullmatch(r"A\d+", x)]
    cathodes = [x for x in p.pins if re.fullmatch(r"K\d+", x)]
    if anodes and cathodes and len(anodes) + len(cathodes) == len(p.pins):
        return [(a, k) for a in anodes for k in cathodes], []   # an SMS-style array
    return None

#: Ratings READ FROM DATASHEETS, keyed by MPN prefix. A hand-typed `v_max`
#: above its line here is a typo or a wish. (prefix, volts, source)
DATASHEET_V_MAX: tuple[tuple[str, float, str], ...] = (
    ("PESD5V0S4UD", 5.0, "Nexperia PESD5V0S4UD, V_RWM"),
    ("SMS05T1G", 5.0, "onsemi SMS05T1/D rev 10, V_RWM"),
    ("SMS15T1G", 15.0, "onsemi SMS05T1/D rev 10, V_RWM"),
    ("SMCJ90A", 90.0, "Littelfuse SMCJ series, V_R; plan 3.2.1"),
    ("SMBJ15A", 15.0, "Littelfuse SMBJ series: the part number carries V_R"),
    ("AO3400A", 30.0, "AOS AO3400A, V_DS"),
    ("AO3407A", 30.0, "AOS AO3407A, V_DS"),
    ("IXTP26P20P", 200.0, "IXYS DS99913D, V_DSS"),
    ("IXTA26P20P", 200.0, "IXYS DS99913D, V_DSS"),
    ("BSS127", 600.0, "Infineon BSS127 rev 2.x, V_DS"),
    ("1N4148", 100.0, "V_RRM"),
    ("1N4007", 1000.0, "V_RRM"),
    ("M7", 1000.0, "the SMA 1N4007: V_RRM"),
    ("SMBJ18A", 18.0, "the part number carries V_R"),
    ("BZT52B10", 10.0, "V_Z nominal"),
    ("BZT52B15", 15.0, "V_Z nominal"),
    ("SS14", 40.0, "V_RRM"),
    ("TPS4H160", 40.0, "TI SLVSCV8E, operating V_VS; abs max 48 V"),
    ("SMF6.0A", 6.0, "SMF series rev 2.2: the part number carries V_RWM"),
    ("LM73605", 36.0, "TI SNVSAH5A, recommended operating PVIN; abs max 42 V"),
    ("TPS2553", 6.5, "TI SLVS841F, recommended operating V_IN; abs max 7 V"),
)

#: Every TVS's clamping voltage READ FROM ITS DATASHEET, with the pulse current
#: the figure holds at: (prefix, volts, "file p.N"). VR-CLAMP holds every part
#: behind a TVS to its typed `v_clamp`; until 2026-09-21 nothing held that
#: figure to anything, and a flattering clamp passed an overdriven victim (H19).
#: A TVS in the design with no line here FAILS -- an unverified clamp is an
#: unchecked one. Files are in ../fardriver-nd72450-reference/reference/.
DATASHEET_V_CLAMP: tuple[tuple[str, float, str], ...] = (
    ("SMS05T1G", 9.8, "onsemi SMS05T1/D rev 10 (tvs_onsemi_sms05t1-d.pdf) p.2: V_C 9.8 V @ I_PP 5 A"),
    ("SMS15T1G", 29.0, "onsemi SMS05T1/D rev 10 (tvs_onsemi_sms05t1-d.pdf) p.2: V_C 29.0 V @ I_PP 12 A"),
    ("SMCJ90A", 146.0, "Vishay doc 88394 rev 20-Jul-2020 (vishay_smcj_88394_C1976063.pdf) p.2: "
                       "V_C 146 V @ I_PP 10.3 A"),
    ("SMBJ18A", 29.2, "SMBJ series (smbj_series_C7420377.pdf) p.2: V_C 29.2 V @ I_PP 20.55 A"),
    ("SMBJ15A", 24.4, "SMBJ series (smbj_series_C7420377.pdf) p.2: V_C 24.4 V @ I_PP 24.59 A"),
    ("SMF18A", 29.2, "SMF series rev 2.2 (smf_series_C19077499.pdf) p.2: V_C 29.2 V @ I_PP 6.8 A"),
    ("SMF6.0A", 10.3, "SMF series rev 2.2 (smf_series_C19077499.pdf) p.2: V_C 10.3 V @ I_PP 19.4 A"),
    ("PESD5V0S4UD", 13.0, "Nexperia PESD5V0S4UD (nexperia_pesd5v0s4ud.pdf) p.4: V_CL 13 V @ I_PP 20 A"),
)


# ── the index: everything a rule needs, derived once ─────────────────────────
class _Ix:
    def __init__(self, d: Design):
        self.d = d
        self.parts: dict[str, Part] = {}
        for p in d.parts:
            self.parts.setdefault(p.refdes, p)
        self.conns: dict[str, Connector] = {}
        for c in d.connectors:
            self.conns.setdefault(c.refdes, c)
        self.nets = {}
        for n in d.nets:
            self.nets.setdefault(n.name, n)

        #: (refdes, pin) -> every net it is on. integrity.py owns "more than
        #: one is a short"; a rule must still see all of them.
        self.pin_nets: dict[tuple[str, str], list[str]] = defaultdict(list)
        #: refdes -> pins that are actually netted, declared or not
        self.landed: dict[str, list[str]] = defaultdict(list)
        #: net -> connectors it lands on, by its own pins OR the connector table
        self.net_conns: dict[str, set[str]] = defaultdict(set)
        for n in d.nets:
            for ref, pin in n.pins:
                self.pin_nets[(ref, pin)].append(n.name)
                if pin not in self.landed[ref]:
                    self.landed[ref].append(pin)
                if ref in self.conns:
                    self.net_conns[n.name].add(ref)
        for c in d.connectors:
            for cp in c.pins:
                if cp.net:
                    self.net_conns[cp.net].add(c.refdes)

        #: net -> [(other net, part, flow, pin here, pin there)]
        #: flow: "both" | "out" (current may only leave this net) | "in"
        self.adj: dict[str, list[tuple[str, Part, str, str, str]]] = defaultdict(list)
        for p in self.parts.values():
            for a, b, polar in self._pairs(p):
                for na in self.pin_nets.get((p.refdes, a), ()):
                    for nb in self.pin_nets.get((p.refdes, b), ()):
                        if na == nb:
                            continue
                        self.adj[na].append((nb, p, "out" if polar else "both", a, b))
                        self.adj[nb].append((na, p, "in" if polar else "both", b, a))

        self._stiff: dict[str, bool] = {}
        self._pull: dict[str, tuple[float, str, list[str]] | None] = {}
        self._divided: dict[str, tuple[float, list[str]] | None] = {}
        self.grounded = self._ground_component()

    # -- what conducts DC between which pins ----------------------------------
    @staticmethod
    def _pairs(p: Part) -> list[tuple[str, str, bool]]:
        pins = set(p.pins)
        kind = _kind(p)
        if kind == "LINK":
            ps = list(p.pins)
            return [(a, b, False) for i, a in enumerate(ps) for b in ps[i + 1:]]
        if kind in _SERIES and len(p.pins) == 2:
            return [(p.pins[0], p.pins[1], False)]
        if kind in _DIODES:
            roles = _diodes(p)
            if roles is None:                       # no roles: POL fires; assume
                ps = list(p.pins)                   # it conducts every way
                return [(a, b, False) for i, a in enumerate(ps) for b in ps[i + 1:]]
            diodes, joined = roles
            return ([(a, k, True) for a, k in diodes]      # current flows A -> K
                    + [(a, b, False) for a, b in joined])
        if p.kind == "CMCHOKE":
            if {"1", "2", "3", "4"} <= pins:        # windings 1-4 and 2-3
                return [("1", "4", False), ("2", "3", False)]
            ps = list(p.pins)                       # unknown pairing: assume all
            return [(a, b, False) for i, a in enumerate(ps) for b in ps[i + 1:]]
        if p.kind in FETS and {"D", "S"} <= pins:
            return [("D", "S", False)]              # the channel
        return []

    # -- nets -----------------------------------------------------------------
    def pins_of(self, p: Part) -> tuple[str, ...]:
        """Declared pins, plus any pin that is netted without being declared.
        integrity.py reports the second kind; a rule must still look at it."""
        return p.pins + tuple(q for q in self.landed.get(p.refdes, ())
                              if q not in p.pins)

    def nets_of_pin(self, refdes: str, pin: str) -> list[str]:
        return self.pin_nets.get((refdes, pin), [])

    def is_gnd(self, name: str) -> bool:
        n = self.nets.get(name)
        return n is not None and n.domain == "GND"

    def leaves_box_directly(self, name: str) -> list[str]:
        return sorted(c for c in self.net_conns.get(name, ())
                      if c in self.conns and self.conns[c].leaves_box)

    def is_stiff(self, name: str) -> bool:
        """A supply or return: low impedance, so a walk never passes THROUGH it.

        Derived, not typed: ground; anything a CONVERTER drives or is fed by;
        anything with bulk + bypass (two or more fitted capacitors to ground).
        A signal net has at most its one filter capacitor.
        """
        if name not in self._stiff:
            self._stiff[name] = self._compute_stiff(name)
        return self._stiff[name]

    def _compute_stiff(self, name: str) -> bool:
        net = self.nets.get(name)
        if net is None:
            return False
        if net.domain == "GND":
            return True
        caps = 0
        for ref, pin in net.pins:
            p = self.parts.get(ref)
            if p is None:
                continue
            if p.kind == "CONVERTER":
                return True
            if p.kind == "C" and not p.dnp and len(p.pins) == 2:
                other = p.pins[1] if pin == p.pins[0] else p.pins[0]
                if any(self.is_gnd(n) for n in self.nets_of_pin(ref, other)):
                    caps += 1
        return caps >= 2

    def is_loaded(self, name: str) -> bool:
        """A fitted R or L ties the net straight to ground: a divider tap or a
        pulled-down node. Its voltage is a ratio nobody here can compute."""
        return any(p.kind in ("R", "L") and not p.dnp and self.is_gnd(other)
                   for other, p, _f, _a, _b in self.adj.get(name, ()))

    def walk(self, start: str, kinds, *, fitted_only: bool, flows=("both", "out", "in"),
             enter=None, through=None) -> dict[str, list[str]]:
        """Nets DC-reachable from `start`, each with the refdes path to it.

        `enter(net)` False: the net is not reachable at all.
        `through(net)` False: the net is reached, but the walk stops there.
        """
        seen: dict[str, list[str]] = {start: []}
        queue = deque([start])
        while queue:
            x = queue.popleft()
            if x != start and through is not None and not through(x):
                continue
            for other, p, flow, _a, _b in self.adj.get(x, ()):
                if (_kind(p) not in kinds or (fitted_only and p.dnp)
                        or flow not in flows or other in seen
                        or (enter is not None and not enter(other))):
                    continue
                seen[other] = seen[x] + [p.refdes]
                queue.append(other)
        return seen

    def signal_reach(self, start: str) -> dict[str, list[str]]:
        """HAZARD walk from a signal net: through any series part, fitted or
        not, never through a supply or ground."""
        return self.walk(start, _HAZARD_PATH, fitted_only=False,
                         through=lambda n: not self.is_stiff(n))

    # -- voltage --------------------------------------------------------------
    def declared(self, name: str) -> float | None:
        n = self.nets.get(name)
        return None if n is None else DOMAIN_VOLTS.get(n.domain)

    def pulled_up(self, name: str) -> tuple[float, str, list[str]] | None:
        """(volts, from net, via) if something holds this net UP with nothing
        holding it down -- e.g. a driver output at 12 V through its open-load
        pull-up, or a contact at 3.3 V through its class-A pull-up."""
        if name not in self._pull:
            self._pull[name] = self._compute_pull(name)
        return self._pull[name]

    def _compute_pull(self, name: str):
        if self.is_stiff(name) or self.is_loaded(name):
            return None
        reach = self.walk(
            name, _SERIES + _DIODES, fitted_only=False, flows=("both", "in"),
            enter=lambda n: not self.is_gnd(n),
            through=lambda n: not self.is_stiff(n) and not self.is_loaded(n))
        best = None
        for other, via in reach.items():
            if other == name:
                continue
            if self.is_loaded(other) and not self.is_stiff(other):
                continue      # a tap or sensed node: its label is a ceiling
                              # for rating parts, not a level it holds others at
            v = self.declared(other)
            if v is not None and (best is None or v > best[0]):
                best = (v, other, via)
        return best

    # -- the resistor network: a divider's real voltage ------------------------
    def is_source(self, name: str) -> bool:
        """A net whose voltage something outside the resistor network sets: a
        supply or return, or a wire from outside the box at its stated level."""
        return self.is_stiff(name) or bool(self.leaves_box_directly(name))

    def divided(self, name: str) -> tuple[float, list[str]] | None:
        """(volts, sources) of a node held by fitted resistors between sources:
        the solved network, not its label. Every other connection is taken as
        high-impedance -- an MCU pin, an IC input, a pin in its reset state --
        which is the case in which a tap sits highest. None when no source
        above ground reaches it through resistors."""
        if name not in self._divided:
            self._solve_from(name)
        return self._divided.get(name)

    def _resistors(self, name: str):
        """(other net, ohms, refdes) for each fitted resistor on `name`."""
        for other, p, _f, _a, _b in self.adj.get(name, ()):
            if p.kind != "R" or p.dnp:
                continue
            ohms = 1e-3 if _is_link(p) else resistance(p.value)
            if ohms is not None:
                yield other, ohms, p.refdes

    def _solve_from(self, name: str) -> None:
        if self.is_source(name):
            self._divided[name] = None
            return
        nodes, seen, queue, edges = [], {name}, deque([name]), []
        while queue:
            x = queue.popleft()
            nodes.append(x)
            for other, ohms, ref in self._resistors(x):
                edges.append((x, other, ohms, ref))
                if other not in seen:
                    seen.add(other)
                    if not self.is_source(other):
                        queue.append(other)
        sources = {n: (self.declared(n) or 0.0) for n in seen if self.is_source(n)}
        if not any(v > 0 for v in sources.values()):
            for n in nodes:
                self._divided[n] = None
            return
        idx = {n: i for i, n in enumerate(nodes)}
        size = len(nodes)
        g = [[0.0] * (size + 1) for _ in range(size)]
        for a, b, ohms, _ref in edges:
            c = 1.0 / ohms
            i = idx[a]
            g[i][i] += c
            if b in idx:
                g[i][idx[b]] -= c
            else:
                g[i][size] += c * sources[b]
        for i in range(size):                  # an isolated island: tie it down
            if g[i][i] == 0.0:
                g[i][i] = 1.0
        for col in range(size):                # Gauss-Jordan, partial pivoting
            piv = max(range(col, size), key=lambda r: abs(g[r][col]))
            g[col], g[piv] = g[piv], g[col]
            if abs(g[col][col]) < 1e-18:
                continue
            for r in range(size):
                if r != col and g[r][col]:
                    f = g[r][col] / g[col][col]
                    for k in range(col, size + 1):
                        g[r][k] -= f * g[col][k]
        up = sorted(n for n, v in sources.items() if v > 0)
        for n, i in idx.items():
            v = g[i][size] / g[i][i] if g[i][i] else None
            self._divided[n] = None if v is None else (round(v, 3), up)

    def volts(self, name: str) -> tuple[float | None, str]:
        """The voltage a part on this net must survive, and why if it is not
        simply the label: held up with no path to ground, or a divider whose
        resistor values put it above its label."""
        dec, pull = self.declared(name), self.pulled_up(name)
        label = self.nets[name].domain if name in self.nets else "?"
        best, why = dec, ""
        if pull is not None and (best is None or pull[0] > best):
            best, why = pull[0], (f" (typed {label}, but held at {pull[1]!r} = "
                                  f"{pull[0]:g} V through {'+'.join(pull[2])} "
                                  f"with no path to ground)")
        div = self.divided(name)
        if div is not None and (best is None or div[0] > best + 0.05):
            best, why = div[0], (f" (typed {label}, but its resistors put it at "
                                 f"{div[0]:g} V from {', '.join(div[1])})")
        return best, why

    # -- ground ---------------------------------------------------------------
    def _ground_component(self) -> set[str]:
        gnd = [n for n in self.d.nets if n.domain == "GND"]
        if not gnd:
            return set()
        principal = max(gnd, key=lambda n: len(n.pins)).name
        return set(self.walk(principal, _GROUND_JOIN, fitted_only=True,
                             enter=self.is_gnd))

    # -- MCU ------------------------------------------------------------------
    def mcus(self) -> list[Part]:
        return [p for p in self.parts.values() if "ESP32" in p.mpn.upper()]

    def fets(self) -> list[Part]:
        return [p for p in self.parts.values() if p.kind in FETS]


_INDEX_CACHE: dict[int, tuple[Design, _Ix]] = {}


def _index(d: Design) -> _Ix:
    """One index per design object, shared by every rule in a `check_all`.
    Keyed on identity and holding the design, so an id is never reused while
    its entry lives, and nothing about the design needs to be hashable."""
    hit = _INDEX_CACHE.get(id(d))
    if hit is not None and hit[0] is d:
        return hit[1]
    if len(_INDEX_CACHE) >= 8:
        _INDEX_CACHE.clear()
    ix = _Ix(d)
    _INDEX_CACHE[id(d)] = (d, ix)
    return ix


def _pin_gpio(pin: str) -> int | None:
    if pin in MCU_PIN_ALIASES:
        return MCU_PIN_ALIASES[pin]
    m = re.fullmatch(r"(?:IO|GPIO)(\d+)", pin)
    return int(m.group(1)) if m else None


def _tag_gpio(tag: str | None) -> int | None:
    m = re.fullmatch(r"GPIO(\d+)", tag or "")
    return int(m.group(1)) if m else None


def _net_gpios(ix: _Ix) -> dict[str, set[int]]:
    """net -> every GPIO it touches, from the MCU PINS and from its tag. Both,
    so that neither a missing tag nor a lying one hides a net from a pin rule."""
    mcu = {p.refdes for p in ix.mcus()}
    out: dict[str, set[int]] = {}
    for n in ix.d.nets:
        gs = {g for ref, pin in n.pins if ref in mcu
              for g in (_pin_gpio(pin),) if g is not None}
        tag = _tag_gpio(n.gpio)
        if tag is not None:
            gs.add(tag)
        if gs:
            out[n.name] = gs
    return out


def _via(path: list[str]) -> str:
    return " -> ".join(path) if path else "directly"


# ── BD-2 / BD-4: where 84 V is allowed to be ─────────────────────────────────
def _hv_nets(ix: _Ix) -> tuple[dict[str, list[str]], list[str]]:
    """Every net that can sit at pack voltage: typed 84V, or DC-joined to one
    through a FET channel, inductor, fuse, diode or choke winding."""
    errs: list[str] = []
    hv: dict[str, list[str]] = {}
    for n in ix.d.nets:
        if n.domain != "84V":
            continue
        for other, path in ix.walk(n.name, _HV_JOIN, fitted_only=False,
                                   enter=lambda x: not ix.is_gnd(x)).items():
            if other not in hv:
                hv[other] = path
                dom = ix.nets[other].domain
                if dom != "84V":
                    errs.append(
                        f"BD-2: net {other!r} is typed {dom} but is DC-joined "
                        f"to the 84 V net {n.name!r} through {_via(path)}. It "
                        f"carries pack voltage whatever its label says.")
    return hv, errs


def bd2_voltage_domain_containment(d: Design) -> list[str]:
    """BD-2: 84 V never reaches OUTPUTS or LOGIC -- parts OR connectors."""
    ix = _index(d)
    hv, errs = _hv_nets(ix)
    for name in hv:
        net = ix.nets[name]
        refs = [r for r, _ in net.pins]
        refs += [c.refdes for c in d.connectors
                 if any(cp.net == name for cp in c.pins)]
        for ref in dict.fromkeys(refs):
            if ref in ix.parts:
                board = ix.parts[ref].board
            elif ref in ix.conns:
                board = ix.conns[ref].board
            else:
                errs.append(f"BD-2: 84 V net {name!r} lands on {ref}, which is "
                            f"neither a part nor a connector, so nothing proves "
                            f"it is not on a logic board.")
                continue
            if board in LOW_VOLTAGE_BOARDS:
                errs.append(f"BD-2: 84 V net {name!r} reaches {ref} on {board}. "
                            f"Pack voltage stays on POWER.")
    return errs


#: The key-switch output as it enters the box. D10: the module only ever
#: LISTENS to this wire -- it never sources it and never switches it.
KEY_NETS = ("KSW",)


def d10_key_wire_is_only_listened_to(d: Design) -> list[str]:
    """D10: nothing in the module can source, hold up or switch the KEY wire.

    The key switch feeds the FarDriver KEY directly; the module takes a tap.
    The only parts that belong on that tap are its connector, its TVS to
    ground, and high-value resistors (the enable divider, the sense divider).
    Any LOW-IMPEDANCE joint -- a diode, a FET channel, an inductor, a fuse --
    is a path by which the module could back-feed KEY and hold the controller
    on with the key out. A diode from the module's own switched rail onto this
    net latches the module AND the controller, and every other rule is blind
    to it. DNP parts count: a hazard does not need to be fitted to be drawn.
    """
    ix = _index(d)
    errs = []
    for name in KEY_NETS:
        if name not in ix.nets:
            continue
        for other, path in ix.walk(name, _HV_JOIN, fitted_only=False,
                                   enter=lambda n: not ix.is_gnd(n)).items():
            if other != name:
                errs.append(
                    f"D10: the key wire {name!r} is joined to {other!r} through "
                    f"{_via(path)} -- a low-impedance path. The module may only "
                    f"LISTEN to KEY (resistors, its TVS, its connector); this "
                    f"lets it back-feed the FarDriver KEY.")
    return errs


#: MPN prefix -> {supply pin: domains it may sit on}. Each entry is the part's
#: own supply range intersected with what its I/O must talk to. A part missing
#: from this table is REPORTED, never assumed fine -- this rule exists because
#: `U404.VCC` on the 5 V rail passed every other check.
SUPPLY_PINS = {
    "ESP32-S3-WROOM-1": {"3V3": {"3V3"}},              # 3.0-3.6 V
    "SN65HVD230": {"VCC": {"3V3"}},                     # 3.0-3.6 V, abs max 4 V
    "MCP23017": {"VDD": {"3V3"}},                       # 1.8-5.5 V, but its I/O meets 3.3 V pins
    "TPS4H160": {"VS": {"12V"}},                        # 4-40 V: the 12 V rail ONLY, never 84 V
    "TLV767": {"IN": {"5V", "12V"}},                    # 2.5-16 V in (12 V is legal; its heat is board_fit's problem)
    "LM73605": {"PVIN": {"12V"}},                       # 3.5-36 V in, 42 V abs: the 12 V rail, never 84 V
    # 2.5-6.5 V in, 7 V abs. ⛔ `OUT` is deliberately absent: it would make
    # VR-CLAMP judge the 5 V clamp against a 7 V limit that IO-12 decided not
    # to protect. What is and is not protected is stated once, on the clamp
    # itself (netlist._tvs6); the risk is recorded, not checked.
    "TPS2553": {"IN": {"5V"}},
    "TLV803S": {"VDD": {"3V3"}},                        # its 2.93 V threshold watches the 3.3 V rail
    "CN150B110": {"+Vin": {"84V"}},
    "EC7BW": {"+Vin": {"84V"}},
}
_SUPPLY_KINDS = ("IC", "MODULE", "CONVERTER")


def supply_pins(d: Design) -> list[str]:
    """Every IC's supply pin sits on a rail that part tolerates."""
    ix = _index(d)
    errs = []
    for p in d.parts:
        if p.kind not in _SUPPLY_KINDS:
            continue
        table = next((v for k, v in SUPPLY_PINS.items() if p.mpn.startswith(k)), None)
        if table is None:
            errs.append(f"SUPPLY: {p.refdes} ({p.mpn}) has no entry in "
                        f"rules.SUPPLY_PINS, so nothing checks what rail feeds it")
            continue
        for pin, allowed in table.items():
            if pin not in p.pins:
                errs.append(f"SUPPLY: {p.refdes} ({p.mpn}) declares no {pin!r} pin")
                continue
            nets = ix.pin_nets.get((p.refdes, pin), ())
            for name in nets:
                dom = ix.nets[name].domain if name in ix.nets else "?"
                if dom not in allowed:
                    errs.append(f"SUPPLY: {p.refdes}.{pin} ({p.mpn}) is on {name!r} "
                                f"({dom}); it may only sit on {sorted(allowed)}")
    return errs


#: MPN prefix -> the pins that are the part's RETURN, from its datasheet.
#: Separate from SUPPLY_PINS on purpose: ⛔ a ground listed there would land
#: in `rails()`, which would make GND a supply rail and fail BUS-ORDER on
#: every signal that faces a ground across STACK and CTRL.
#: ⚠️ A converter's INPUT return is NOT here: both bricks' `-Vin` joins ground
#: only through its choke's second winding, and is 84 V-section copper.
GROUND_PINS = {
    "ESP32-S3-WROOM-1": {"GND", "EPAD"},
    "SN65HVD230": {"GND"},
    "MCP23017": {"VSS"},
    "TPS4H160": {"GND", "PAD"},          # PAD: SLVSCV8E p.31, to the GND copper
    "TLV767": {"GND", "PAD"},
    "TLV803S": {"GND"},
    "TPS2553": {"GND"},
    # SNVSAH5A p.4: AGND is the reference for every parameter, PGND the LS
    # FET's source, DAP (our PAD) the heat path -- all three to system ground.
    # Splitting them is the point of this part's layout, and nothing but this
    # rule says where they go: a PGND landed on the 5 V rail it makes passed
    # integrity, every test and every other rule (review 2026-09-20).
    "LM73605": {"AGND", "PGND", "PAD"},
    "CN150B110": {"-V", "-S"},           # output return, and its sense leg
    "EC7BW": {"-Vout"},
}


def ground_pins(d: Design) -> list[str]:
    """Every IC's, module's and converter's RETURN pin is on the ground net.

    Not "on a net called GND" and not "on a GND-typed net": on a net JOINED to
    ground by copper, which is what `is_stiff`'s ground component means. A
    ground-typed island that reaches ground through nothing is GND-ISLAND's
    error, and a return pin sitting on it is this one's."""
    ix = _index(d)
    errs = []
    for p in d.parts:
        if p.kind not in _SUPPLY_KINDS:
            continue
        pins = next((v for k, v in GROUND_PINS.items() if p.mpn.startswith(k)), None)
        if pins is None:
            errs.append(f"GND-PIN: {p.refdes} ({p.mpn}) has no entry in "
                        f"rules.GROUND_PINS, so nothing checks where its "
                        f"return goes")
            continue
        for pin in sorted(pins):
            if pin not in p.pins:
                errs.append(f"GND-PIN: {p.refdes} ({p.mpn}) declares no {pin!r} pin")
                continue
            for name in ix.nets_of_pin(p.refdes, pin):
                if name not in ix.grounded:
                    dom = ix.nets[name].domain if name in ix.nets else "?"
                    errs.append(
                        f"GND-PIN: {p.refdes}.{pin} ({p.mpn}) is on {name!r} "
                        f"({dom}), which is not joined to the ground net. A "
                        f"return pin on anything else is a part referenced to "
                        f"the wrong node, whatever else passes.")
    return errs


def bd4_hv_creepage(d: Design) -> list[str]:
    """BD-4: every connector carrying pack voltage, whatever it is labelled."""
    ix = _index(d)
    hv, _ = _hv_nets(ix)
    errs = []
    for c in d.connectors:
        carried = sorted(n for n in hv if c.refdes in ix.net_conns.get(n, ()))
        if not carried:
            continue
        if not (c.pitch_mm >= HV_MIN_PITCH_MM):          # NaN fails too
            errs.append(
                f"BD-4: {c.refdes} carries 84 V ({', '.join(carried)}) "
                f"at {c.pitch_mm} mm pitch; it needs >= {HV_MIN_PITCH_MM} mm.")
    return errs


# ── GPIO rules: read the PIN, cross-check the tag ────────────────────────────
def gpio_rules(d: Design) -> list[str]:
    ix = _index(d)
    errs: list[str] = []
    mcu = {p.refdes for p in ix.mcus()}
    gpios = _net_gpios(ix)

    for n in d.nets:
        pin_gs = sorted({g for ref, pin in n.pins if ref in mcu
                         for g in (_pin_gpio(pin),) if g is not None})
        tag = _tag_gpio(n.gpio)
        if n.gpio and tag is None:
            errs.append(f"GPIO-TAG: net {n.name!r} carries the tag {n.gpio!r}, "
                        f"which is not of the form GPIOn.")
        elif tag is not None and tag not in pin_gs:
            errs.append(f"GPIO-TAG: net {n.name!r} is tagged GPIO{tag} but lands "
                        f"on MCU GPIOs {pin_gs or 'NONE'}.")
        elif pin_gs and tag is None:
            errs.append(f"GPIO-TAG: net {n.name!r} lands on MCU GPIO{pin_gs[0]} "
                        f"with no gpio tag.")

    used = Counter(g for gs in gpios.values() for g in gs)
    for g, count in sorted(used.items()):
        if count > 1:
            on = sorted(name for name, gs in gpios.items() if g in gs)
            errs.append(f"GPIO-DUP: GPIO{g} is used by {count} nets: {on}.")

    for name, gs in sorted(gpios.items()):
        reach = None
        for g in sorted(gs):
            if g not in MODULE_GPIOS:
                why = ("is the in-package flash" if g in GPIO_FLASH else
                       "has no pad on the WROOM-1" if g in WROOM1_NOT_BROUGHT_OUT
                       else "does not exist on the S3")
                errs.append(f"GPIO-PAD: net {name!r} uses GPIO{g}, which {why}.")
            if g == GPIO_BOOT_LOG or g in GPIO_STRAPPING:
                reach = reach if reach is not None else ix.signal_reach(name)
            if g == GPIO_BOOT_LOG:
                errs.extend(
                    f"GPIO-43: net {name!r} is on GPIO{g}, which emits the ROM "
                    f"boot log at every reset, and reaches {load} {_via(path)}. "
                    f"Never a driver."
                    for load, path in _loads(ix, reach, mcu))
            if g in GPIO_STRAPPING:
                errs.extend(
                    f"GPIO-STRAP: net {name!r} is on strapping GPIO{g} and "
                    f"reaches {load} {_via(path)}. That input's bias network "
                    f"sets the boot strap; strapping pins are outside the pool."
                    for load, path in _loads(ix, reach, mcu))
                for other, path in reach.items():
                    if ix.is_stiff(other):
                        continue
                    for conn in sorted(ix.net_conns.get(other, ())):
                        c = ix.conns.get(conn)
                        if c is None or not (c.leaves_box or c.interface):
                            continue            # the internal service pads
                        where = ("leaves the box" if c.leaves_box else
                                 f"crosses {c.interface} to another board")
                        errs.append(
                            f"GPIO-STRAP: net {name!r} is on strapping GPIO{g} "
                            f"and reaches {conn} ({c.name}), which {where}, "
                            f"{_via(path)}. Whatever holds that wire at key-on "
                            f"picks the boot mode.")

        for g in sorted(gs & GPIO_RESET_PULL_UP):
            errs.extend(
                f"GPIO-RESET-PULL: net {name!r} is on GPIO{g}, which comes out "
                f"of reset pulled UP, and reaches the enable {load} {_via(path)}: "
                f"the load is ON from reset until firmware runs, and stays on "
                f"if it hangs. Every driver biases OFF (D14)."
                for load, path in _loads(ix, ix.signal_reach(name), mcu)
                if _active_high_enable(ix, load))

    errs.extend(_adc1(ix, gpios))
    return errs


def _active_high_enable(ix: _Ix, load: str) -> bool:
    """An input that switches a load ON when pulled high: an N-FET gate, or an
    IC's IN/EN pin (a TPS4H160 channel input)."""
    ref, _, pin = load.partition(".")
    p = ix.parts[ref]
    return (p.kind == "NFET" and pin == "G") or (
        p.kind == "IC" and re.fullmatch(r"(IN\d*|EN)", pin) is not None)


def _loads(ix: _Ix, reach, mcu) -> list[tuple[str, list[str]]]:
    """FET gates and IC pins a signal net reaches: the things it DRIVES."""
    out = []
    for other, path in reach.items():
        if ix.is_stiff(other):
            continue
        for ref, pin in ix.nets[other].pins:
            p = ix.parts.get(ref)
            if p is None or ref in mcu:
                continue
            if (p.kind in FETS and pin == "G") or p.kind == "IC":
                out.append((f"{ref}.{pin}", path))
    return out


def _adc1(ix: _Ix, gpios: dict[str, set[int]]) -> list[str]:
    errs = []
    analog: dict[str, str] = {n.name: "is an analog net"
                              for n in ix.d.nets if n.name in ANALOG_NETS}
    for name in gpios:                       # derived: walks to a driver's CS pin
        if name in analog:
            continue
        for other, path in ix.signal_reach(name).items():
            hit = [f"{ref}.CS" for ref, pin in ix.nets[other].pins
                   if pin == "CS" and ref in ix.parts and ix.parts[ref].kind == "IC"]
            if hit:
                analog[name] = f"reads the current-sense output {hit[0]} {_via(path)}"
                break
    for name, why in sorted(analog.items()):
        gs = gpios.get(name, set()) or {
            g for other in _one_resistor_away(ix, name) for g in gpios.get(other, ())}
        if not gs:
            errs.append(f"GPIO-ADC1: {name!r} {why} but lands on no MCU pin.")
        for g in sorted(gs - GPIO_ADC1):
            errs.append(f"GPIO-ADC1: {name!r} {why} but is on GPIO{g}. ADC2 "
                        f"dies with WiFi -- use GPIO1-10.")
    return errs


def _one_resistor_away(ix: _Ix, name: str) -> set[str]:
    """Nets joined to `name` by one fitted two-pin resistor: an ADC net may
    meet its pin through its series resistor."""
    out = set()
    for ref, pin in ix.nets[name].pins:
        p = ix.parts.get(ref)
        if p is not None and p.kind == "R" and not p.dnp and len(p.pins) == 2:
            other = p.pins[1] if pin == p.pins[0] else p.pins[0]
            out.update(ix.pin_nets.get((ref, other), ()))
    out.discard(name)
    return out


# ── BUS-ORDER: an inter-board power bus survives being mated wrong ───────────
#: Nets at ground potential: a converter's -Vin joins GND through its choke's
#: second winding only, so it is a return, not a rail.
_RETURN_NETS = frozenset({"GND", "HV_C1_N", "HV_C2_N"})


def rails(d: Design) -> frozenset[str]:
    """Every net that feeds a part's SUPPLY pin: the design's own statement of
    what a RAIL is, and the same table rule SUPPLY holds each of those pins to.

    ⛔ Not the domain. `CS1` is 3.3 V class and `TT_L` 12 V class, and neither
    carries anything: a sense node shorted to ground reads zero, a rail shorted
    to ground takes the board down with it."""
    ix = _index(d)
    out = set()
    for p in d.parts:
        for pin in _supply_pins(p):
            out.update(ix.nets_of_pin(p.refdes, pin))
    return frozenset(out)


def bus_order(d: Design) -> list[str]:
    """Every inter-board interface, against the ways a half can be mated wrong.

    ⭐ WHICH QUESTION IT ASKS DEPENDS ON THE CROSSING (model.CROSSING).

    A CABLE is asked for POSITIVE KEYING, and nothing else. Its plug is one
    moulded housing, so it cannot be seated a contact off; what it can be is
    offered to its header the other way round, by hand, every time the boards
    are serviced -- and a key makes that mechanically impossible where an
    ordering rule only makes it survivable.

    ⛔ A cable is NOT exempt, it is held to something stronger, because an
    unkeyed cable is strictly WORSE than a palindromic bus. A bus's two halves
    are soldered down facing each other at a fixed spacing and the palindrome
    lands every net on itself if one is reversed; a loom is a separate part
    that arrives in somebody's hand, and PWR-OUT's four different nets on four
    contacts admit no ordering that makes reversing it harmless -- reversed, a
    rail meets a sense node whatever order they sit in. The key is the only
    defence a cable has, and a cabled half that names none has none at all.

    A MATED PAIR is asked for the two orderings below. Reversed -- or, the same
    thing in copper, an upper half mirrored by being mounted under its board --
    contact i meets contact n+1-i. One contact off, contact i meets contact
    i+1. Neither may land a rail or a signal on a DIFFERENT one:

      opposite pairs  a power bus survives reversal by being a palindrome, so
                      every net lands on itself; a signal spine survives it by
                      facing every signal with a ground. ⛔ A RAIL opposite
                      anything but itself is a short across the interface, and
                      a ground opposite it does not excuse it -- that IS the
                      short. So a mismatched pair passes only when neither side
                      is a rail and one of them is a return. ⚠️ Where that line
                      sits: a SENSE line facing a ground reversed is a misread
                      and a loud one (firmware flags 'powered with KEY_SENSE
                      low'); a RAIL facing one is a short across the interface.
                      A power bus still earns its palindrome by having one --
                      every net lands on itself and neither case arises.
      adjacent pairs  two different nets may sit side by side only if one of
                      them is a return: a shift can short a rail, never feed
                      84 V or 12 V into a logic input. (A shift is a visibly
                      hanging contact and blows the module's fuse; a half
                      reversed seats fully and looks right, which is why the
                      opposite-pair test is the stricter of the two.)

    ⚠️ Both tests are read off the PIN TABLE, for EVERY interface. STACK was
    exempt BY NAME, on the argument that its alternating grounds make the
    palindrome unnecessary. True of its signals -- and it left the alternation
    itself unchecked, it fired on CTRL the day CTRL was added, which is built
    the same way contact for contact, and it hid a RAIL on the spine: V3P3 sat
    opposite a ground until the rail test above moved it to PWR-LOGIC, where a
    rail belongs."""
    errs = []
    seen = set()
    supply = rails(d)
    for c in d.connectors:
        if not c.interface or c.interface in seen:
            continue
        seen.add(c.interface)
        if is_cabled(c.interface):
            # BOTH halves, not the first: each end of a loom is presented to
            # its own header, and only the end that is keyed is safe.
            for half in d.connectors:
                if half.interface == c.interface and not half.keyed:
                    errs.append(
                        f"BUS-ORDER: {half.interface} ({half.refdes}) is a "
                        f"CABLE and names no keying, so nothing stops its plug "
                        f"going in the other way round. A cable is not exempt "
                        f"from this rule, it is held to more: a mated pair is "
                        f"soldered down facing its own half and survives being "
                        f"reversed by reading the same from both ends, while a "
                        f"loom is offered by hand at every service and no "
                        f"ordering of four different nets makes reversing it "
                        f"harmless. Name the feature from the maker's drawing "
                        f"in `Connector.keyed`, or the interface has nothing.")
            continue
        nets = [cp.net for cp in c.pins]
        n = len(nets)
        for i in range(n // 2):
            a, b = nets[i], nets[n - 1 - i]
            if a == b:
                continue
            shorted = sorted({a, b} & supply)
            if shorted or not ({a, b} & _RETURN_NETS):
                why = (f"{shorted[0]} is a supply rail, so a reversed or "
                       f"mirrored half SHORTS it to {(a if b == shorted[0] else b) or '-'}"
                       if shorted else
                       "neither is a return, so a reversed or mirrored half "
                       "lands one on the other")
                errs.append(f"BUS-ORDER: {c.interface} ({c.refdes}) reads "
                            f"{'/'.join(x or '-' for x in nets)}: not the same "
                            f"from both ends -- contacts {i + 1}/{n - i} carry "
                            f"{a or '-'} and {b or '-'}, and {why}")
                break
        for i, (a, b) in enumerate(zip(nets, nets[1:]), start=1):
            if a != b and not ({a, b} & _RETURN_NETS):
                errs.append(f"BUS-ORDER: {c.interface} ({c.refdes}) puts {a or '-'} "
                            f"beside {b or '-'} on contacts {i}/{i + 1}: mated one "
                            f"contact off, one lands on the other")
    return errs


# ── D14: every gate biases OFF, for the polarity the FET actually is ─────────
#: What an IC calls the pin that turns its output on, across the families this
#: board uses: `EN`, `ENABLE`, `SHDN`, `SHUTDOWN`, their inverted spellings
#: (`nEN`, `/EN`), and a qualified one (`DIAG_EN`). ⛔ Never just "EN": the
#: branch below matched that one string, so a part naming its enable anything
#: else walked straight past the rule that exists for it.
ENABLE_PIN = re.compile(r"(?i)[/n]?(?:EN|ENABLE|SHDN|SHUTDOWN|CE|ON)\d?"
                        r"|\w+_(?:EN|ENABLE|SHDN|CE|ON)")
#: Pins a part holds OFF ITSELF, by MPN prefix. ⛔ An entry here is a DATASHEET
#: STATEMENT, never a convenience: TI SLVSCV8E Table 5-1 (p.4-5) marks INx,
#: DIAG_EN, SEL, SEH and THER "internal pulldown", and §6.5 (p.8) gives the
#: resistor -- R(logic,pd) 100/175/250 kΩ on INx, SEL, SEH and THER,
#: 200/275/350 kΩ on DIAG_EN. That silicon is what holds every lamp and every
#: 12 V aux channel off through boot and for as long as nothing drives the
#: pin, so demanding copper as well would be demanding a part the design does
#: not need.
INTERNAL_PULLDOWN = {
    "TPS4H160": frozenset({"IN1", "IN2", "IN3", "IN4", "DIAG_EN",
                           "SEL", "SEH", "THER"}),
}


#: |V_GS(th)| MINIMUM per FET, from its datasheet: the gate-source voltage at
#: which the most sensitive unit begins to conduct. D14 holds every gate's
#: RESTING voltage under it. (prefix, volts, source). ⛔ A FET whose gate rests
#: off its source with no line here is REFUSED, not passed at a guessed figure:
#: the AO3400A's 0.65 V is under any "safe universal" 1 V.
DATASHEET_VGS_TH_MIN: tuple[tuple[str, float, str], ...] = (
    ("AO3400A", 0.65, "AOS AO3400A rev 3 (aos_ao3400a_C20917.pdf) p.2: V_GS(th) 0.65 V min, "
                      "I_D 250 µA"),
    ("BSS127", 1.4, "Infineon BSS127 rev 2.01 (infineon_bss127_C152611.pdf) p.2: V_GS(th) "
                    "1.4 V min, I_D 8 µA"),
    ("IXTA26P20P", 2.0, "IXYS DS99913D (ixys_ds99913d.pdf) p.1: V_GS(th) -2.0 V min, I_D -250 µA"),
    ("IXTP26P20P", 2.0, "IXYS DS99913D (ixys_ds99913d.pdf) p.1: V_GS(th) -2.0 V min, I_D -250 µA"),
)
#: V_IL -- the most an active-high enable may rest at and still read LOW --
#: per part, from its datasheet. (prefix, volts, source). A part with no line
#: is held to V_IL_DEFAULT.
DATASHEET_V_IL: tuple[tuple[str, float, str], ...] = (
    ("TPS2553", 0.66, "TI SLVS841F (ti_tps2553.pdf) p.6 §7.3: V_IL 0.66 V max on EN"),
    ("TPS4H160", 0.8, "TI SLVSCV8E (ti_tps4h160.pdf) p.8: V_IL 0.8 V max"),
    ("LM73605", 0.3, "TI SNVSAH5A (ti_lm73605.pdf) p.6: V_EN_VCC_L 0.3 V, EN falling"),
)
#: The TTL/CMOS convention, for a part with no line above. ⚠️ Not universal:
#: the TPS2553's own figure is 0.66 V, which is why the table exists.
V_IL_DEFAULT = 0.8
#: A gate or enable within this of its OFF level rests OFF; the solver rounds.
_REST_TOL_V = 0.05
#: ICs whose ENABLE may sit on a rail: a REGULATOR making a rail the design
#: needs the moment its input appears. Its being always on is the point; what
#: the firmware sheds are the loads behind it. Any other IC's enable on a rail
#: -- a LOAD SWITCH in particular -- is a channel the key-off shed (IO-16)
#: can never release, and fails D14. mpn prefix -> why, from the netlist's
#: own source for the part.
ALWAYS_ON_ENABLE = {
    "LM73605": "the 5 V aux buck: EN straight to V12 is TI's own connection "
               "(SNVSAH5A p.4 'Can be tied to PVIN'); the four TPS2553 behind it "
               "are what the firmware sheds",
    "TLV767": "the 3.3 V LDO: EN to IN ('can be connected to the input pin', "
              "SLVSE84D) brings the logic rail up with the 5 V -- the S3 cannot "
              "enable its own supply",
}


def _resting(ix: _Ix, net: str, reference: str | None = None) -> tuple[float, list[str]]:
    """The voltage `net` rests at with every command at rest: its fitted
    resistor network solved with every STIFF net at its declared voltage,
    `reference` (a FET's own source net, whatever its stiffness) at its
    declared voltage, and every other source -- a wire from outside the box,
    the key tap -- HIGH-IMPEDANCE, as an open switch leaves it. Every pin that
    is not a resistor (an MCU output in reset, a FET channel off) is open.
    Returns (volts, the fixed nets above 0 V it is solved against)."""
    held = lambda n: ix.is_stiff(n) or n == reference
    if held(net):
        return ix.declared(net) or 0.0, [net]
    nodes, seen, queue, edges = [], {net}, deque([net]), []
    while queue:
        x = queue.popleft()
        nodes.append(x)
        for other, ohms, _ref in ix._resistors(x):
            edges.append((x, other, max(ohms, 1e-3)))
            if other not in seen:
                seen.add(other)
                if not held(other):
                    queue.append(other)
    fixed = {n: (ix.declared(n) or 0.0) for n in seen if held(n)}
    if not fixed:
        return 0.0, []
    v = _solve(ix, nodes, edges, fixed)
    return round(v.get(net, 0.0), 3), sorted(n for n, val in fixed.items() if val > 0)


def _datasheet(table, mpn: str):
    return next(((v, src) for prefix, v, src in table if mpn.upper().startswith(prefix)), None)


def d14_gate_bias(d: Design) -> list[str]:
    """Every FET gate and every IC enable RESTS OFF: not merely "a bias
    resistor exists", but V_GS solved at rest is under the part's V_GS(th)
    minimum, and an enable's resting voltage is under its V_IL.

    Until 2026-09-21 this asked only whether a pull-down existed (H4). A 1 kΩ
    pull-up beside the fitted 10 kΩ pull-down passed, with the horn FET hard
    ON; a 1 kΩ pull-up on a TPS2553 enable passed, with 5 V aux 1 on from
    power-up and un-sheddable through Q101's decay (IO-16); a 499 kΩ from
    Q101's gate to ground passed, with the 84 V P-FET at V_GS = -14 V key-OFF.
    `_resting` solves what `ix.divided` solves, but against the rails only:
    a wire from outside the box (KSW) is a command, and at rest it is open."""
    ix = _index(d)
    errs = []
    for q in ix.fets():
        missing = [x for x in ("G", "S", "D") if x not in q.pins]
        if missing:
            errs.append(f"D14: {q.refdes} ({q.mpn}) declares no {missing} pin, "
                        f"so OFF cannot be defined for it. Name FET pins G, S, D.")
            continue
        gate, source = ix.nets_of_pin(q.refdes, "G"), ix.nets_of_pin(q.refdes, "S")
        if not gate or not source:
            errs.append(f"D14: {q.refdes} ({q.mpn}) has its "
                        f"{'gate' if not gate else 'source'} on no net.")
            continue
        if set(gate) & set(source):
            continue                                  # V_GS is zero in copper
        if not any(_joins(ix, r, gate, source) for r in ix.parts.values()
                   if r.kind == "R" and not r.dnp):
            errs.append(
                f"D14: {q.refdes} ({q.kind} {q.mpn}) has no fitted resistor "
                f"from its gate net {gate[0]!r} to its SOURCE net {source[0]!r}. "
                f"OFF means V_GS = 0; a resistor to any other rail biases it ON "
                f"or nowhere.")
            continue
        if q.dnp:
            continue
        vg, held = _resting(ix, gate[0], reference=source[0])
        vs, _ = _resting(ix, source[0], reference=source[0])
        toward_on = (vg - vs) if q.kind == "NFET" else (vs - vg)
        if toward_on <= _REST_TOL_V:
            continue
        line = _datasheet(DATASHEET_VGS_TH_MIN, q.mpn)
        where = (f"rests at {vg:g} V against its source {source[0]!r} at {vs:g} V "
                 f"(V_GS {'+' if q.kind == 'NFET' else '-'}{toward_on:g} V, held by "
                 f"{', '.join(held) or 'nothing'})")
        if line is None:
            errs.append(f"D14: {q.refdes} ({q.kind} {q.mpn}) gate {gate[0]!r} {where}, "
                        f"and DATASHEET_VGS_TH_MIN has no line for it: an unstated "
                        f"threshold is an unchecked gate.")
        elif toward_on > line[0]:
            errs.append(f"D14: {q.refdes} ({q.kind} {q.mpn}) gate {gate[0]!r} {where}: "
                        f"above its V_GS(th) minimum {line[0]:g} V ({line[1]}), so it "
                        f"rests ON with no firmware running.")
    # An IC's ENABLE is a gate by another name: high-Z on it is a load whose
    # state nobody chose. The rule checked FET gates only until the aux block
    # put four load switches on expander bits that come out of reset as
    # inputs (IO-1) -- exactly the window D14 exists for.
    #
    # ⚠️ Two limits this branch does NOT close, stated so neither is mistaken
    # for covered:
    #   * It is POLARITY-BLIND. It reads a resistor to ground as "biased off",
    #     which is true of an active-high enable and FALSE of an active-low
    #     one (`SHDN`, `/EN`): that part is biased ON by the same copper and
    #     passes here. What states the polarity is the part's own `source`,
    #     and choosing the active-high member of a family is a design decision
    #     (the TPS2553, ⛔ never the TPS2552).
    #   * `kind != "IC"` is LOAD-BEARING, not tidiness. It keeps `U401.EN` out:
    #     the S3's CHIP_PU is a reset input that must be pulled UP through its
    #     RC, not an output enable, and this rule would demand the opposite of
    #     what Espressif's design guide asks. `test_the_module_has_its_reset_rc`
    #     is what guards that pin.
    # A pin tied straight to a rail is a deliberate always-on (U405's EN on V5,
    # U305's on V12), not a floating enable, so a stiff net is skipped -- and a
    # pin its own silicon holds off needs no copper (INTERNAL_PULLDOWN).
    for p in ix.parts.values():
        if p.kind != "IC" or p.dnp:
            continue
        internal = next((v for k, v in INTERNAL_PULLDOWN.items()
                         if p.mpn.startswith(k)), frozenset())
        always_on = next((why for k, why in ALWAYS_ON_ENABLE.items()
                          if p.mpn.startswith(k)), None)
        v_il = _datasheet(DATASHEET_V_IL, p.mpn)
        limit, src = v_il if v_il else (V_IL_DEFAULT, "V_IL_DEFAULT, the TTL/CMOS convention")
        for pin in ix.pins_of(p):
            if not ENABLE_PIN.fullmatch(pin) or pin in internal:
                continue
            for net in ix.nets_of_pin(p.refdes, pin):
                if ix.is_stiff(net):
                    if always_on is None:
                        errs.append(
                            f"D14: {p.refdes} ({p.mpn}) {pin} is tied to the rail "
                            f"{net!r} ({ix.declared(net) or 0:g} V): enabled for as "
                            f"long as the rail is up, which the key-off shed "
                            f"(IO-16) can never release. Only a rail REGULATOR's "
                            f"enable may sit on a rail (ALWAYS_ON_ENABLE); a load "
                            f"switch's is a channel no firmware controls.")
                    continue
                if not any(_joins(ix, r, [net], ["GND"]) for r in ix.parts.values()
                           if r.kind == "R" and not r.dnp):
                    errs.append(f"D14: {p.refdes} ({p.mpn}) {pin} on {net!r} "
                                f"has no fitted resistor to GND. Every enable "
                                f"biases OFF from reset (D14).")
                    continue
                v, held = _resting(ix, net)
                if v > limit + _REST_TOL_V:
                    errs.append(
                        f"D14: {p.refdes} ({p.mpn}) {pin} on {net!r} rests at {v:g} V, "
                        f"held by {', '.join(held)}: above V_IL {limit:g} V ({src}), "
                        f"so it is ENABLED from power-up with no firmware, and "
                        f"nothing the firmware does can shed it (IO-16).")
    return errs


def _joins(ix: _Ix, r: Part, a: list[str], b: list[str]) -> bool:
    if len(r.pins) != 2:
        return False
    n0, n1 = (set(ix.nets_of_pin(r.refdes, pin)) for pin in r.pins)
    return bool((n0 & set(a) and n1 & set(b)) or (n0 & set(b) and n1 & set(a)))


# ── TURN-ON: can the switch be commanded on at all? ──────────────────────────
def turn_on_path(d: Design) -> list[str]:
    ix = _index(d)
    errs = []
    for q in ix.fets():
        if q.dnp or not {"G", "S"} <= set(q.pins):
            continue
        gate, source = ix.nets_of_pin(q.refdes, "G"), ix.nets_of_pin(q.refdes, "S")
        if not gate or not source:
            continue                                  # integrity reports these
        if set(gate) & set(source):
            errs.append(f"TURN-ON: {q.refdes} ({q.mpn}) has its gate on its own "
                        f"source net {sorted(set(gate) & set(source))[0]!r}: "
                        f"V_GS is always 0, so it can never turn on.")
            continue
        vs = max((ix.volts(s)[0] or 0.0) for s in source)
        if q.kind == "PFET" and vs >= HIGH_SIDE_VOLTS:
            if not any(_pulls_low(ix, g, set(source)) for g in gate):
                errs.append(
                    f"TURN-ON: {q.refdes} ({q.mpn}) is a high-side P-FET on "
                    f"{source[0]!r} but nothing can pull its gate {gate[0]!r} "
                    f"below its source: no fitted path to ground through "
                    f"resistors and one N-FET, and no steering diode to a "
                    f"contact that leaves the box. It can never turn on.")
        elif not any(_has_driver(ix, g, set(source)) for g in gate):
            errs.append(
                f"TURN-ON: {q.refdes} ({q.mpn}) gate {gate[0]!r} is commanded "
                f"by nothing -- no IC pin, connector or rail reaches it through "
                f"fitted series parts. It can never turn on.")
    return errs


def _pulls_low(ix: _Ix, gate: str, source: set[str]) -> bool:
    """Gate -> ground through fitted resistors, forward diodes and at most one
    N-FET channel. A net that leaves the box is set by the outside world, so
    the path may END there (behind a diode that can only sink) but never pass
    through it; nor through a supply, nor through the FET's own source."""
    seen = set()
    queue = deque([(gate, False, False)])
    while queue:
        state = queue.popleft()
        if state in seen:
            continue
        seen.add(state)
        net, used_fet, via_diode = state
        if net in ix.grounded:
            return True
        outside = bool(ix.leaves_box_directly(net))
        if outside and via_diode:
            return True
        if outside or net in source or (net != gate and ix.is_stiff(net)):
            continue
        for other, p, flow, here, _there in ix.adj.get(net, ()):
            if p.dnp:
                continue
            if _kind(p) in _SERIES:
                queue.append((other, used_fet, via_diode))
            elif p.kind == "D" and flow == "out":
                queue.append((other, used_fet, True))
            elif p.kind == "NFET" and here == "D" and not used_fet:
                queue.append((other, True, via_diode))
    return False


def _has_driver(ix: _Ix, gate: str, source: set[str]) -> bool:
    reach = ix.walk(gate, _SERIES + ("D",), fitted_only=True,
                    enter=lambda n: n not in source,
                    through=lambda n: not ix.is_stiff(n))
    for net in reach:
        if ix.is_gnd(net):
            continue
        if net != gate and ix.is_stiff(net):
            return True                               # tied to a rail
        if ix.net_conns.get(net):
            return True
        if any(ref in ix.parts and ix.parts[ref].kind in ("IC", "MODULE", "CONVERTER")
               for ref, _ in ix.nets[net].pins):
            return True
    return False


# ── GATE-VGS: a commanded gate must REACH the V_GS its part is specified at ───
#: |V_GS| each FET's on-state is specified at, from its datasheet. Beside
#: DATASHEET_V_MAX, and read the same way: (mpn prefix, volts, where it says so).
#: An entry is required for any FET a logic pin commands through a divider --
#: no figure means no check, so a missing one is an error, not a pass.
#: ⭐ Found by review 2026-09-19: R114 = 100k puts 0.30 V on Q106's gate, and the
#: motor cut simply never works. Integrity passes, D14 passes (the bias-OFF is
#: there), TURN-ON passes (a pin does reach the gate), VR-* pass, and all 1233
#: tests pass. The topology is right; only the RATIO is wrong, and nothing was
#: looking at the ratio.
DATASHEET_VGS_SPEC: tuple[tuple[str, float, str], ...] = (
    ("AO3400A", 2.5, "AOS AO3400A: R_DS(on) 48 mΩ max is specified at "
                     "V_GS = 2.5 V, the lowest gate drive the part is "
                     "characterised at"),
)

#: A source declared within this of 0 V counts as sitting at GROUND potential.
_AT_RAIL_V = 0.2


def gate_drive_level(d: Design) -> list[str]:
    """Can the command actually switch the FET?

    D14 asks whether the gate rests OFF. TURN-ON asks whether anything can
    reach it. Neither reads the DIVIDER the series resistor and the bias
    resistor form, so a series resistor of the wrong decade leaves a switch
    that is wired correctly, biased correctly, commanded by the right pin, and
    does not switch.

    |V_GS| at the divider is |V_source - V_on| × R_bias / (R_series + R_bias),
    where V_on is the level the driver asserts to turn this FET on: its own
    rail for a low-side N-FET, 0 V for a P-FET resting at its source. The BIAS
    is taken worst case (the smallest of them, which loses the most drive); the
    SERIES is the lightest resistive path to a logic pin, because that is the
    path the copper drives through -- two pins on one gate and the stronger wins.

    ⛔ The rule REFUSES the cases it cannot compute rather than passing them: a
    source that is not at ground potential, a swing it cannot read, or an mpn
    with no stated V_GS. (A P-FET whose source is above 3.3 V and whose gate a
    logic pin pulls down is LV-LOGIC's error, not this one: that pin sees the
    rail.)
    """
    ix = _index(d)
    errs = []
    for q in ix.fets():
        if q.dnp or not {"G", "S"} <= set(q.pins):
            continue
        gate, source = ix.nets_of_pin(q.refdes, "G"), ix.nets_of_pin(q.refdes, "S")
        if not gate or not source or set(gate) & set(source):
            continue                            # integrity / D14 / TURN-ON own these
        g, s = gate[0], source[0]
        drive = _logic_drive(ix, g, set(source))
        if drive is None:
            continue                            # no logic pin commands this gate
        series, driver = drive
        biases = [r for r in ix.parts.values()
                  if r.kind == "R" and not r.dnp and _joins(ix, r, gate, source)]
        ohms = [x for x in (resistance(r.value) for r in biases) if x is not None]
        if not ohms:
            continue                            # D14 reports a missing bias-OFF
        # ⚠️ 0 Ω is a real value here, not "absent": a 0 Ω link or NET-TIE from
        # gate to source passes D14 (a resistor IS there) and TURN-ON (a pin does
        # reach the gate) while holding V_GS at zero for ever.
        bias = min(ohms)
        v_src, v_rail = ix.declared(s), ix.declared(driver)
        v_on = 0.0 if q.kind == "PFET" else v_rail
        if v_src is None or v_on is None:
            mute = f"source {s!r}" if v_src is None else f"driver {driver!r}"
            errs.append(f"GATE-VGS: {q.refdes} ({q.kind} {q.mpn}) is commanded "
                        f"from {driver!r} through {series:g} Ω, and the swing "
                        f"across its gate divider cannot be read: {mute} "
                        f"declares no voltage. An unknown swing is an unchecked "
                        f"gate.")
            continue
        if q.kind != "PFET" and v_src > _AT_RAIL_V:
            errs.append(f"GATE-VGS: {q.refdes} ({q.kind} {q.mpn}) is a HIGH-SIDE "
                        f"N-FET -- its source {s!r} sits at {v_src:g} V, so its "
                        f"gate must be driven ABOVE that and the {v_rail:g} V "
                        f"logic pin on {driver!r} cannot. This rule computes "
                        f"|V_GS| only for a source at ground potential; a "
                        f"bootstrap or charge pump needs a check of its own.")
            continue
        spec = next((v for pre, v, why in DATASHEET_VGS_SPEC
                     if q.mpn.upper().startswith(pre)), None)
        why = next((why for pre, _v, why in DATASHEET_VGS_SPEC
                    if q.mpn.upper().startswith(pre)), "")
        if spec is None:
            errs.append(f"GATE-VGS: {q.refdes} ({q.kind} {q.mpn}) has its gate "
                        f"{g!r} commanded through a divider, and "
                        f"DATASHEET_VGS_SPEC states no V_GS its on-state is "
                        f"specified at. Read it off the datasheet and add it "
                        f"there; without it the divider is unchecked.")
            continue
        swing = abs(v_src - v_on)
        vgs = swing * bias / (series + bias) if series + bias > 0 else 0.0
        if vgs + 1e-9 < spec:
            errs.append(f"GATE-VGS: {q.refdes} ({q.kind} {q.mpn}) is commanded "
                        f"from {driver!r} through {series:g} Ω against a "
                        f"{bias:g} Ω bias, so its gate reaches only {vgs:.3g} V "
                        f"of a {swing:g} V swing. Its on-state is specified at "
                        f"|V_GS| = {spec:g} V ({why}). Below that the part "
                        f"switches somewhere on its transfer curve, where "
                        f"R_DS(on) is not specified at all.")
    return errs


def _logic_pin_net(ix: _Ix, name: str) -> bool:
    """A net a logic pin drives: it carries a gpio tag, or an MCU or expander
    pin lands on it."""
    if ix.nets[name].gpio:
        return True
    return any(ref in ix.parts
               and ("ESP32" in ix.parts[ref].mpn.upper()
                    or ix.parts[ref].mpn.upper().startswith("MCP23017"))
               for ref, _ in ix.nets[name].pins)


def _logic_drive(ix: _Ix, gate: str, source: set[str]) -> tuple[float, str] | None:
    """(series ohms, the net the logic pin drives) for the LIGHTEST resistive
    path from `gate` to a net a logic pin drives, or None if none does. Two
    pins on one gate means the stronger one wins, which is what the copper
    does.

    ⛔ Two kinds of net are never entered, and both matter:
      * a RAIL -- the bias resistor ends on one, and every rail meets an MCU
        supply pin, so entering one would find a 'driver' through the very
        resistor that holds the gate OFF;
      * a net that LEAVES THE BOX -- the outside world sets it, so a logic pin
        on the far side is not driving this gate through it. Without this, Q105's
        84 V level-shifter gate walks out through KSW and back in through the
        key-sense divider and reports KEY_SENSE_PIN, an ADC input 1.33 MΩ away,
        as its driver."""
    import heapq
    best: dict[str, float] = {gate: 0.0}
    heap = [(0.0, gate)]
    while heap:
        ohms, net = heapq.heappop(heap)
        if ohms > best.get(net, math.inf):
            continue
        if _logic_pin_net(ix, net):
            return (ohms, net)
        for other, part, _f, _a, _b in ix.adj.get(net, ()):
            if (part.dnp or part.kind != "R" or len(part.pins) != 2
                    or other in source or ix.is_stiff(other)
                    or ix.leaves_box_directly(other)):
                continue
            step = resistance(part.value)
            if step is None:
                continue
            total = ohms + step
            if total < best.get(other, math.inf):
                best[other] = total
                heapq.heappush(heap, (total, other))
    return None


# ── VR: check the voltage line on EVERY part ─────────────────────────────────
def voltage_ratings(d: Design) -> list[str]:
    ix = _index(d)
    errs = []
    gate_clamps = _gate_source_pairs(ix)
    for p in d.parts:
        required = p.kind in RATED_KINDS and not _is_link(p)
        if p.v_max is None:
            if required:
                errs.append(f"VR-RATED: {p.refdes} ({p.kind} {p.mpn}) carries no "
                            f"v_max. An unrated part is an unchecked part.")
            continue
        if not (math.isfinite(p.v_max) and p.v_max > 0):
            errs.append(f"VR-RATED: {p.refdes} ({p.mpn}) has v_max={p.v_max}.")
            continue
        for prefix, limit, src in DATASHEET_V_MAX:
            if p.mpn.upper().startswith(prefix) and p.v_max > limit:
                errs.append(f"VR-DATASHEET: {p.refdes} ({p.mpn}) is typed "
                            f"v_max={p.v_max:g} V; the datasheet says {limit:g} V "
                            f"({src}).")
        if p.kind == "TVS" and not p.dnp and p.v_clamp is not None:
            line = next(((v, src) for prefix, v, src in DATASHEET_V_CLAMP
                         if p.mpn.upper().startswith(prefix)), None)
            if line is None:
                errs.append(f"VR-DATASHEET: {p.refdes} ({p.mpn}) is typed "
                            f"v_clamp={p.v_clamp:g} V, and DATASHEET_V_CLAMP has no "
                            f"line for it: an unverified clamp is an unchecked one. "
                            f"Read V_C from its datasheet and add the line.")
            elif abs(p.v_clamp - line[0]) > 0.05:
                errs.append(f"VR-DATASHEET: {p.refdes} ({p.mpn}) is typed "
                            f"v_clamp={p.v_clamp:g} V; the datasheet says "
                            f"{line[0]:g} V ({line[1]}).")

        all_pins = ix.pins_of(p)
        pins = (tuple(x for x in ("D", "S") if x in all_pins)
                if p.kind in FETS else all_pins)
        seen_nets: dict[str, tuple[float | None, str]] = {}
        for pin in pins:
            for name in ix.nets_of_pin(p.refdes, pin):
                if not ix.is_gnd(name):
                    seen_nets[name] = ix.volts(name)
        for name in seen_nets:
            if required and ix.declared(name) is None:
                errs.append(
                    f"VR-DOMAIN: {p.refdes} ({p.mpn}, {p.v_max:g} V) is on net "
                    f"{name!r}, whose voltage is not declared "
                    f"(domain {ix.nets[name].domain}). Nothing can say whether "
                    f"the part survives it.")
        known = {n: vw for n, vw in seen_nets.items() if vw[0] is not None}
        if not known:
            continue

        if p.kind == "TVS":
            for name, (v, why) in known.items():
                if v > p.v_max:
                    errs.append(
                        f"VR-STANDOFF: {p.refdes} ({p.mpn}) stands off "
                        f"{p.v_max:g} V on net {name!r}, which works at {v:g} V"
                        f"{why}. It conducts continuously -- a load, not "
                        f"protection.")
            continue

        worst = max(known, key=lambda n: known[n][0])
        across, why = known[worst]
        nets = frozenset(n for pin in all_pins for n in ix.nets_of_pin(p.refdes, pin))
        if p.kind == "ZENER" and nets in gate_clamps:
            continue                  # a gate clamp's job IS to conduct at V_Z
        clamp = min((z.v_max for z in d.parts
                     if z.kind == "ZENER" and not z.dnp and z is not p
                     and z.v_max is not None
                     and frozenset(n for pin in ix.pins_of(z)
                                   for n in ix.nets_of_pin(z.refdes, pin)) == nets),
                    default=None)
        if clamp is not None and len(nets) == 2:
            across = min(across, clamp)
        if across > p.v_max:
            errs.append(
                f"VR-UNDER: {p.refdes} ({p.kind} {p.mpn}) is rated "
                f"{p.v_max:g} V and sees up to {across:g} V "
                f"(net {worst!r}{why}).")
    return errs


def _gate_source_pairs(ix: _Ix) -> set[frozenset[str]]:
    pairs = set()
    for q in ix.fets():
        for g in ix.nets_of_pin(q.refdes, "G"):
            for s in ix.nets_of_pin(q.refdes, "S"):
                pairs.add(frozenset((g, s)))
    return pairs


# ── LV-LOGIC: nothing above 3.3 V on a 3.3 V pin ─────────────────────────────
def logic_pin_levels(d: Design) -> list[str]:
    ix = _index(d)
    errs = []
    for p in ix.parts.values():
        if "ESP32" in p.mpn.upper():
            limit = LOGIC_PIN_V_MAX
        elif p.mpn.upper().startswith("MCP23017"):
            vdd = [ix.volts(n)[0] for n in ix.nets_of_pin(p.refdes, "VDD")]
            vdd = [v for v in vdd if v is not None]
            limit = (max(vdd) + MCP_PIN_OVER_VDD) if vdd else LOGIC_PIN_V_MAX
        else:
            continue
        for pin in ix.pins_of(p):
            for name in ix.nets_of_pin(p.refdes, pin):
                v, why = ix.volts(name)
                if v is not None and v > limit:
                    errs.append(
                        f"LV-LOGIC: {p.refdes}.{pin} ({p.mpn}) is on net "
                        f"{name!r} at {v:g} V{why}; the pin survives "
                        f"{limit:g} V. Divide it down (plan 4, class B).")
    return errs


# ── PROT: a clamp that is fitted, at the connector, and returns to ground ────
def protection(d: Design) -> list[str]:
    ix = _index(d)
    errs = []
    for c in d.connectors:
        if not c.leaves_box:
            continue
        names = {cp.net for cp in c.pins if cp.net}
        names |= {n for n, conns in ix.net_conns.items() if c.refdes in conns}
        for name in sorted(names):
            net = ix.nets.get(name)
            if net is None:
                errs.append(f"PROT: {c.refdes} names net {name!r}, which does "
                            f"not exist, so its protection cannot be checked.")
                continue
            if net.domain == "GND":
                continue
            if _resistive_input(ix, net):
                continue
            why_not = []
            ok = False
            for ref, pin in net.pins:
                t = ix.parts.get(ref)
                if t is None or t.kind != "TVS":
                    continue
                problems = []
                # A parked terminal's clamp may be left off only with its
                # header: the label alone leaves a live header unguarded.
                if t.dnp and not (c.parked and c.dnp):
                    problems.append("is DNP")
                if t.board != c.board:
                    problems.append(f"is on {t.board}, not {c.board}")
                returns = [q for q in ix.pins_of(t) if q != pin
                           and any(n in ix.grounded
                                   for n in ix.nets_of_pin(t.refdes, q))]
                if not returns:
                    problems.append("has no other terminal on ground")
                if problems:
                    why_not.append(f"{t.refdes} {' and '.join(problems)}")
                else:
                    ok = True
            if not ok:
                errs.append(
                    f"PROT: net {name!r} leaves the box on {c.refdes} "
                    f"({c.name}, {c.board}) with no working clamp: "
                    f"{'; '.join(why_not) or 'no TVS on the net at all'}.")
    return errs


#: A wire whose every on-board part is a fitted resistor at least this large
#: needs no clamp: it can push only microamps into the board, and a TVS on it
#: would add the one part that can fail SHORT -- on KSW that blows the key fuse
#: and cuts the controller's KEY (review HV-2 / FM-5).
HI_Z_INPUT_OHMS = 100e3


def _resistive_input(ix: _Ix, net) -> bool:
    from .model import resistance
    parts = [ix.parts.get(ref) for ref, _ in net.pins if ref not in ix.conns]
    return bool(parts) and all(
        p is not None and p.kind == "R" and not p.dnp
        and (resistance(p.value) or 0) >= HI_Z_INPUT_OHMS for p in parts)


# ── GND-ISLAND: a ground that is not joined to ground ────────────────────────
def ground_islands(d: Design) -> list[str]:
    ix = _index(d)
    return [
        f"GND-ISLAND: net {n.name!r} is typed GND but no fitted resistor, "
        f"inductor, fuse or choke winding joins it to the ground net. Every "
        f"return landed on it goes nowhere."
        for n in d.nets if n.domain == "GND" and n.name not in ix.grounded]


# ── MCP-OUT7: GPA7 / GPB7 are output-only ────────────────────────────────────
def mcp23017_bit7(d: Design) -> list[str]:
    ix = _index(d)
    errs = []
    for p in ix.parts.values():
        if not p.mpn.upper().startswith("MCP23017"):
            continue
        for pin in ("GPA7", "GPB7"):
            for name in ix.nets_of_pin(p.refdes, pin):
                errs.append(
                    f"MCP-OUT7: net {name!r} lands on {p.refdes}.{pin}, which "
                    f"is output-only (DS20001952 rev D). Leave both bit 7s in "
                    f"`nc`.")
    return errs


# ── POL: a diode whose direction nobody wrote down ───────────────────────────
def polarity(d: Design) -> list[str]:
    """Every diode-like part names its pins by role, and each diode inside it
    points the way a clamp must: cathode on the net at the higher level. A
    multi-pin array numbered 1-6 cannot be checked at all, and a swapped pair
    of its pins (an array's anode and a line) shorts a rail."""
    ix = _index(d)
    errs = []
    for p in d.parts:
        if p.kind not in _DIODES:
            continue
        bidirectional = p.kind == "TVS" and p.mpn.upper().rstrip("-0123456789").endswith("CA")
        roles = _diodes(p)
        if roles is None:
            if not bidirectional:
                errs.append(f"POL: {p.refdes} ({p.kind} {p.mpn}) names its pins "
                            f"{p.pins}. Name them by role (A/K, or the part's own "
                            f"in rules._TVS_TOPOLOGY), or its direction is "
                            f"undefined and no path through it can be checked.")
            continue
        for a, k in roles[0]:
            for na in ix.nets_of_pin(p.refdes, a):
                for nk in ix.nets_of_pin(p.refdes, k):
                    va, vk = ix.declared(na), ix.declared(nk)
                    if va is not None and vk is not None and vk < va:
                        errs.append(
                            f"POL: {p.refdes} ({p.mpn}) has its {a}->{k} diode "
                            f"from {na!r} ({va:g} V) to {nk!r} ({vk:g} V): "
                            f"forward-biased, it shorts {na!r} instead of "
                            f"clamping {nk!r}.")
    return errs


# ── VR-CLAMP: what a TVS lets through must be survivable behind it ──────────
#: Microchip DS20001952D p.3: MCP23017 input clamp current, I_IK, +/-20 mA.
MCP_CLAMP_MA = 20.0
#: What a transient on a clamped net passes on: copper, and diodes forward.
_CLAMP_JOIN = ("L", "FUSE", "LINK", "CMCHOKE")


def _returns(ix: _Ix) -> set[str]:
    """Nets at ground potential: ground, and anything joined to it only
    through copper or a choke winding (a converter's -Vin)."""
    out = set()
    for n in ix.d.nets:
        if n.domain == "GND":
            out |= set(ix.walk(n.name, _CLAMP_JOIN, fitted_only=True))
    return out


def clamp_ratings(d: Design) -> list[str]:
    """A TVS conducts at its clamping voltage, not its stand-off: every part it
    protects must survive THAT (HV-3: the 84 V clamp is 146 V, against 160 V
    converters and a 200 V FET). Rated to ground and checked here: converters'
    and ICs' supply pins, FETs across their channel, capacitors to a return.
    An expander pin behind a series resistor must take the clamp's current
    into its protection diodes (I_IK)."""
    ix = _index(d)
    errs = []
    returns = _returns(ix)
    for t in ix.parts.values():
        if t.kind != "TVS" or t.dnp:
            continue
        if t.v_clamp is None:
            errs.append(f"VR-CLAMP: {t.refdes} ({t.mpn}) states no clamping "
                        f"voltage, so nothing behind it can be checked.")
            continue
        roles = _diodes(t)
        if roles is None:
            continue
        for a, k in roles[0]:
            if not any(n in returns for n in ix.nets_of_pin(t.refdes, a)):
                continue
            for guarded in ix.nets_of_pin(t.refdes, k):
                if guarded in returns:
                    continue
                errs += _clamp_victims(ix, t, guarded, returns)
    return sorted(set(errs))


def _clamped(ix: _Ix, name: str) -> bool:
    """A net with a fitted clamp of its own, which governs it."""
    return any(p.kind == "TVS" and not p.dnp for p in
               (ix.parts.get(ref) for ref, _ in ix.nets[name].pins) if p is not None)


def _clamp_victims(ix: _Ix, t: Part, guarded: str, returns: set[str]) -> list[str]:
    """The pulse spreads over copper and forward diodes, and through a switch
    that may be on -- but not into a net with a clamp of its own, which then
    holds it (a lamp output's pulse does not set the 12 V rail's level)."""
    v = t.v_clamp
    enter = lambda n: n not in returns and (n == guarded or not _clamped(ix, n))
    on = ix.walk(guarded, _CLAMP_JOIN + _DIODES + FETS, fitted_only=True,
                 flows=("both", "out"), enter=enter)
    off = ix.walk(guarded, _CLAMP_JOIN + _DIODES, fitted_only=True,
                  flows=("both", "out"), enter=enter)
    errs = []
    head = f"VR-CLAMP: {t.refdes} ({t.mpn}) clamps {guarded!r} at {v:g} V"
    for p in ix.parts.values():
        if p is t or p.dnp or p.v_max is None:
            continue
        nets = {pin: ix.nets_of_pin(p.refdes, pin) for pin in ix.pins_of(p)}
        hit = lambda pin, region: any(n in region for n in nets.get(pin, ()))
        if p.kind == "CONVERTER" and hit("+Vin", on):
            why = "at its +Vin"
        elif p.kind == "IC" and any(hit(pin, on) for pin in _supply_pins(p)):
            why = "at its supply pin"
        elif p.kind in FETS and hit("D", off) != hit("S", off):
            why = "across its channel, switched off"
        elif p.kind == "C" and len(p.pins) == 2 and (
                (hit(p.pins[0], on) and any(n in returns for n in nets[p.pins[1]]))
                or (hit(p.pins[1], on) and any(n in returns for n in nets[p.pins[0]]))):
            why = "to a return"
        else:
            continue
        if p.v_max < v:
            errs.append(f"{head}; {p.refdes} ({p.mpn}) is rated {p.v_max:g} V "
                        f"{why}. Choose a clamp under the part, or a part over "
                        f"the clamp.")
    for q in ix.parts.values():
        if not q.mpn.upper().startswith("MCP23017"):
            continue
        vdd = max((ix.volts(n)[0] or 0.0 for n in ix.nets_of_pin(q.refdes, "VDD")),
                  default=3.3)
        for pin in ix.pins_of(q):
            for n in ix.nets_of_pin(q.refdes, pin):
                for other, ohms, ref in ix._resistors(n):
                    if other != guarded or ohms <= 0:
                        continue
                    ma = (v - (vdd + MCP_PIN_OVER_VDD)) / ohms * 1e3
                    if ma > MCP_CLAMP_MA:
                        errs.append(f"{head}; through {ref} ({ohms:g} Ω) that "
                                    f"drives {ma:.1f} mA into {q.refdes}.{pin}, "
                                    f"whose clamp diodes take {MCP_CLAMP_MA:g} mA "
                                    f"(I_IK).")
    return errs


def _supply_pins(p: Part) -> tuple[str, ...]:
    table = next((v for k, v in SUPPLY_PINS.items() if p.mpn.startswith(k)), None)
    return tuple(table) if table else ()


# ── VR-POWER: what a resistor dissipates at its worst ──────────────────────
#: Rated power by package, the chip-resistor standard: 0402 1/16 W, 0603
#: 1/10 W, 0805 1/8 W, 1206 1/4 W. UNI-ROYAL's part-number power code says so
#: for the parts _R_LCSC buys (uniroyal_0805W8.pdf p.2 §2.2: WG = 1/16 W,
#: WA = 1/10 W, W8 = 1/8 W, W4 = 1/4 W -- 0603WA…, 0805W8…, 1206W4…). ⛔ Pinned
#: by value in tests/test_rules.py: this table ×10 once passed every test, and
#: the design runs at 58-73 % of these figures (H18).
R_POWER_W = {"0402": 1 / 16, "0603": 1 / 10, "0805": 1 / 8, "1206": 1 / 4}
#: The most a logic pin drives into a resistor: Espressif ESP32-S3 datasheet
#: v2.2 p.65 Table 5-4, I_OH 40 mA at PAD_DRIVER 3 (I_OL 28 mA); Microchip
#: DS20001952D p.3, 25 mA sourced or sunk by any MCP23017 pin.
PIN_DRIVE_A = {"ESP32": 0.040, "MCP23017": 0.025}


def _pin_drive(ix: _Ix, name: str) -> float | None:
    """The drive limit of the logic pins on `name`, or None if none."""
    out = [a for ref, _ in ix.nets[name].pins if ref in ix.parts
           for key, a in PIN_DRIVE_A.items() if key in ix.parts[ref].mpn.upper()]
    return max(out) if out else None


def _hard(ix: _Ix, name: str) -> bool:
    """A net something other than a resistor can drive or ground: a supply, a
    wire, a pin of a chip or module, a FET channel, a diode. A net held only by
    resistors, gates, capacitors and clamps follows its resistors."""
    if ix.is_source(name) or ix.net_conns.get(name):
        return True
    for ref, pin in ix.nets[name].pins:
        p = ix.parts.get(ref)
        if p is None:
            continue
        if p.kind in ("IC", "MODULE", "CONVERTER") or p.kind == "D":
            return True
        if p.kind in FETS and pin in ("D", "S"):
            return True
    return False


def _solve(ix: _Ix, nodes: list[str], edges, fixed: dict[str, float]) -> dict[str, float]:
    """Node voltages of a resistor network with `fixed` nets held."""
    free = [n for n in nodes if n not in fixed]
    idx = {n: i for i, n in enumerate(free)}
    size = len(free)
    g = [[0.0] * (size + 1) for _ in range(size)]
    for a, b, ohms in edges:
        c = 1.0 / ohms
        for x, y in ((a, b), (b, a)):
            if x not in idx:
                continue
            i = idx[x]
            g[i][i] += c
            if y in idx:
                g[i][idx[y]] -= c
            else:
                g[i][size] += c * fixed[y]
    for i in range(size):
        if g[i][i] == 0.0:
            g[i][i] = 1.0
    for col in range(size):
        piv = max(range(col, size), key=lambda r: abs(g[r][col]))
        g[col], g[piv] = g[piv], g[col]
        if abs(g[col][col]) < 1e-18:
            continue
        for r in range(size):
            if r != col and g[r][col]:
                f = g[r][col] / g[col][col]
                for k in range(col, size + 1):
                    g[r][k] -= f * g[col][k]
    out = dict(fixed)
    out.update({n: g[i][size] / g[i][i] for n, i in idx.items()})
    return out


def _worst_across(ix: _Ix, r: Part) -> float:
    """The most voltage `r` can see: its network solved with every driven net
    high, then every driven net low (supplies hold their level either way), and
    -- when both its ends are driven -- one high and the other low."""
    a, b = (ix.nets_of_pin(r.refdes, pin)[0] if ix.nets_of_pin(r.refdes, pin) else None
            for pin in r.pins[:2])
    if a is None or b is None:
        return 0.0
    vmax = lambda n: ix.volts(n)[0] or 0.0
    floor = lambda n: (ix.declared(n) or 0.0) if ix.is_stiff(n) else 0.0
    if _hard(ix, a) and _hard(ix, b):
        return max(abs(vmax(a) - floor(b)), abs(vmax(b) - floor(a)))
    nodes, seen, queue, edges = [], {a, b}, deque([a, b]), []
    while queue:
        x = queue.popleft()
        nodes.append(x)
        if _hard(ix, x):
            continue
        for other, ohms, _ref in ix._resistors(x):
            edges.append((x, other, max(ohms, 1e-3)))
            if other not in seen:
                seen.add(other)
                queue.append(other)
    ohms_r = resistance(r.value) or 1e-3
    edges.append((a, b, max(ohms_r, 1e-3)))
    worst = 0.0
    for high in (True, False):
        fixed = {n: (vmax(n) if (high or ix.is_stiff(n)) else floor(n))
                 for n in nodes if _hard(ix, n)}
        if not fixed:
            continue
        v = _solve(ix, nodes, edges, fixed)
        worst = max(worst, abs(v.get(a, 0.0) - v.get(b, 0.0)))
    return worst


def resistor_power(d: Design) -> list[str]:
    """V²/R at the worst voltage a resistor can see, against its package."""
    ix = _index(d)
    errs = []
    for r in ix.parts.values():
        if r.kind != "R" or r.dnp or _is_link(r) or len(r.pins) != 2:
            continue
        ohms, rated = resistance(r.value), R_POWER_W.get(r.package)
        if not ohms or rated is None:
            continue
        v = _worst_across(ix, r)
        watts = v * v / ohms
        # A logic pin is a current-limited driver, not a supply: what it can
        # push through a resistor to anything but a rail is its drive limit.
        ends = [ix.nets_of_pin(r.refdes, pin) for pin in r.pins]
        if not all(ends):
            continue                          # integrity reports an unlanded pin
        a, b = ends[0][0], ends[1][0]
        for pin_net, far in ((a, b), (b, a)):
            amps = _pin_drive(ix, pin_net)
            if amps is not None and not ix.is_stiff(far):
                watts = min(watts, amps * amps * ohms)
        if watts > rated:
            errs.append(f"VR-POWER: {r.refdes} ({r.value}, {r.package}) can see "
                        f"{v:.3g} V and dissipate {watts:.3g} W; its package is "
                        f"rated {rated:g} W.")
    return errs


# ── PULL-DIR: a switch that closes to ground needs a pull-UP ─────────────────
def pull_direction(d: Design) -> list[str]:
    """A wire that meets a logic input through its series resistor carries a
    contact to ground (plan §4 class A). Pulled only DOWN, it reads 'closed'
    whether the contact is open or not."""
    ix = _index(d)
    logic = {n for p in ix.parts.values()
             if "ESP32" in p.mpn.upper() or p.mpn.upper().startswith("MCP23017")
             for pin in ix.pins_of(p) for n in ix.nets_of_pin(p.refdes, pin)
             if not ix.is_stiff(n)}
    errs = []
    for c in d.connectors:
        if c.interface:
            continue
        for name in sorted({cp.net for cp in c.pins if cp.net}):
            if name not in ix.nets or ix.is_stiff(name):
                continue
            ends = list(ix._resistors(name))
            if not any(o in logic for o, _ohms, _ref in ends):
                continue
            ups = [ref for o, _ohms, ref in ends if ix.is_source(o) and (ix.declared(o) or 0) > 0]
            downs = [ref for o, _ohms, ref in ends if o in ix.nets and ix.is_gnd(o)]
            if downs and not ups:
                errs.append(f"PULL-DIR: {name!r} on {c.refdes} feeds a logic input "
                            f"but is pulled DOWN by {', '.join(downs)} and up by "
                            f"nothing: a contact to ground can never be read.")
    return errs


# ── HT: every body in the stack, against a stack derived from those bodies ───
def _bodies(d: Design):
    """Every body in the stack. The last field is "half of a MATED pair", and
    ⛔ it is not "has an interface": a CABLED crossing's half mates with nothing
    across the gap, so its height sets no board spacing and it stands in the gap
    above its face like any other body (`board_params._pairs`). Reading it the
    old way told the owner that J202, J105, J311 and J312 each set a spacing,
    four times, about four connectors joined by looms."""
    for p in d.parts:
        yield p.refdes, p.mpn, p.board, p.side, p.height_mm, p.height_confirmed, False
    for c in d.connectors:
        yield (c.refdes, c.name, c.board, c.side, c.height_mm, c.height_confirmed,
               c.interface is not None and not is_cabled(c.interface))


def _is_height(h) -> bool:
    return isinstance(h, (int, float)) and not isinstance(h, bool) \
        and math.isfinite(h) and h >= 0


def heights(d: Design) -> list[str]:
    """Parts AND connectors, top side and bottom. board_params derives each
    gap from the tallest thing standing in it, the deepest thing hanging into
    it, solder tails, the brick's floor seat and the mated inter-board pairs -- so a
    tall connector, a 40 mm `side="bottom"` part and a NaN all land here.

    The cavity the envelope REQUIRES is relayed too, on the plan axes: while
    M18 is an estimate `cavity_problems` is empty, and once the cavity is
    measured and the enclosure chosen a design that will not go in the box
    fails this gate exactly as an over-tall stack does."""
    errs = [f"HT-NUM: {ref} ({what}) has height {h!r}. An unknown height is an "
            f"unchecked height."
            for ref, what, _b, _s, h, _c, _i in _bodies(d) if not _is_height(h)]
    if _stack_problems is None:
        errs.append("HT-GEOM: tools/board_params.py offers no stack_problems(design), "
                    "so no height in this design has been checked against the "
                    "enclosure.")
        return errs
    errs.extend(f"HT-STACK: {p}" for p in _stack_problems(d))
    if _cavity_problems is not None:
        errs.extend(f"HT-CAVITY: {p}" for p in _cavity_problems(d))
    return errs


ALL_RULES = (
    bd2_voltage_domain_containment,
    d10_key_wire_is_only_listened_to,
    supply_pins,
    ground_pins,
    bd4_hv_creepage,
    gpio_rules,
    d14_gate_bias,
    turn_on_path,
    gate_drive_level,
    voltage_ratings,
    logic_pin_levels,
    protection,
    ground_islands,
    mcp23017_bit7,
    polarity,
    heights,
    bus_order,
    clamp_ratings,
    resistor_power,
    pull_direction,
)


def check_all(design: Design) -> list[str]:
    """Run every rule. Empty list means the design does its job."""
    errs: list[str] = []
    for rule in ALL_RULES:
        errs.extend(rule(design))
    return errs


def _near_limit(d: Design) -> dict[str, str]:
    """refdes -> why its unconfirmed height matters. A body's ceiling is
    whatever is tallest among the bodies that share its face of its board: the
    gap there is measured against that one, and anything within
    UNCONFIRMED_MARGIN_MM of it would be if its real height came in over. The
    half of a MATED pair sets the board spacing outright.

    ⚠️ "measured against", not "sets": since a STANDOFF can define a gap
    (`board_params.Gap.standoff`), the tallest body in one is often not what
    puts the boards where they are -- it is what the gap has to clear, and an
    unconfirmed height for it is just as load-bearing either way."""
    tallest: dict[tuple[str, str], tuple[float, str]] = {}
    for ref, _w, board, side, h, _c, paired in _bodies(d):
        if not paired and _is_height(h) and h > tallest.get((board, side), (-1.0, ""))[0]:
            tallest[(board, side)] = (h, ref)
    out = {}
    for ref, _w, board, side, h, confirmed, paired in _bodies(d):
        if confirmed or not _is_height(h):
            continue
        if paired:
            out[ref] = "its mated height sets the spacing between two boards"
            continue
        top, top_ref = tallest[(board, side)]
        if top_ref == ref:
            out[ref] = (f"the tallest body on the {side} of {board}, so that "
                        f"gap is measured against it")
        elif top - h <= UNCONFIRMED_MARGIN_MM:
            out[ref] = (f"within {UNCONFIRMED_MARGIN_MM:g} mm of the tallest body "
                        f"on the {side} of {board} ({top_ref}, {top:g} mm), which "
                        f"that gap is measured against")
    return out


def warnings(design: Design) -> list[str]:
    """What a human must look at, and a gate must not fail on."""
    out: list[str] = []
    if not getattr(_bp, "CAVITY_MEASURED", True):
        out.append("HT-W0: the cavity is an estimate (M18 is not measured); "
                   "every height verdict here is provisional.")
    if not getattr(_bp, "ENCLOSURE_DECIDED", True):
        out.append("HT-W0: the enclosure is not chosen; wall, floor and lid are "
                   "allowances, so the height available is provisional.")
    why = _near_limit(design)
    stack = _stack_height(design) if _stack_height is not None else None
    for verdict in getattr(stack, "envelope_verdicts", ()) or ():
        out.append(f"HT-STACK-PROVISIONAL: {verdict}")
    for ref in getattr(stack, "load_bearing", ()):
        why.setdefault(ref, "board_params finds that it sets a gap of the stack")
    heights_of = {ref: (what, h) for ref, what, _b, _s, h, _c, _i in _bodies(design)}
    for ref, reason in why.items():
        what, h = heights_of.get(ref, ("?", float("nan")))
        out.append(f"HT-W1: {ref} ({what}) is {h:g} mm, UNCONFIRMED, and {reason}. "
                   f"Read it off the manufacturer's drawing.")
    out.extend(f"HT-W2: {note}" for note in getattr(stack, "notes", ()))
    for c in design.connectors:
        if not c.leaves_box and c.interface is None:
            out.append(f"BOX-W1: {c.refdes} ({c.name}) is declared internal but "
                       f"mates with no inter-board interface. If a wire on it "
                       f"ever leaves the enclosure, every net on it needs a "
                       f"clamp and PROT is not checking them.")
    return out


if __name__ == "__main__":
    import sys
    from . import netlist
    design = netlist.current()
    problems = check_all(design)
    for e in problems:
        print(e)
    notes = warnings(design)
    for w in notes:
        print("warning:", w)
    print(f"\n{len(problems)} rule violation(s), {len(notes)} warning(s)")
    sys.exit(1 if problems else 0)
