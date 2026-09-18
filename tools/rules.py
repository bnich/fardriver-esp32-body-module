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
    up through resistors and forward diodes with no path to ground -- so a
    lever node typed `3V3` is still seen at the 12 V that R313 holds it at;
  * a GPIO is the `IOn` pin the net lands on, cross-checked against its tag.

Two kinds of walk, and the difference is deliberate:
  HAZARD walks (84 V containment, strapping, GPIO43, pull-up voltage) count a
  DNP part -- the footprint exists and can be populated.
  FUNCTION walks (bias, turn-on path, protection, ground joins) count only
  FITTED parts -- a job is not done by a part that is not there.

Every error string starts with a stable rule ID, then a colon:

  BD-2  BD-4
  GPIO-TAG  GPIO-DUP  GPIO-PAD  GPIO-USB  GPIO-43  GPIO-ADC1  GPIO-STRAP
  D14  TURN-ON
  VR-RATED  VR-DOMAIN  VR-UNDER  VR-STANDOFF  VR-DATASHEET
  LV-LOGIC  PROT  GND-ISLAND  MCP-OUT7  POL
  HT-NUM  HT-STACK  HT-GEOM  D10  SUPPLY

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
from .model import DOMAIN_VOLTS, Connector, Design, Part

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
GPIO_USB = _silicon("USB", {19, 20})                 # native USB D-/D+
GPIO_STRAPPING = _silicon("STRAPPING", {0, 3, 45, 46})
GPIO_ADC1 = _silicon("ADC1", range(1, 11))           # ADC2 dies with WiFi
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
#: BD-2: 84 V stays on HVIN/CONV. The TPS4H160B on DRV is a 40 V part.
LOW_VOLTAGE_BOARDS = frozenset({"DRV", "BRAIN"})
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
#: An unconfirmed height this close to setting its gap is reported, not trusted.
UNCONFIRMED_MARGIN_MM = 2.0

# ── part facts ───────────────────────────────────────────────────────────────
FETS = ("NFET", "PFET")
#: Kinds that must carry a voltage rating (model.Part.v_max).
RATED_KINDS = ("C", "D", "ZENER", "TVS", "NFET", "PFET")
#: What a DC path may pass through.
_SERIES = ("R", "L", "FUSE", "FUSECLIP")
_HAZARD_PATH = _SERIES + ("D", "CMCHOKE") + FETS
_HV_JOIN = ("L", "FUSE", "FUSECLIP", "D", "CMCHOKE") + FETS
_GROUND_JOIN = _SERIES + ("CMCHOKE",)

#: Ratings READ FROM DATASHEETS, keyed by MPN prefix. A hand-typed `v_max`
#: above its line here is a typo or a wish. (prefix, volts, source)
DATASHEET_V_MAX: tuple[tuple[str, float, str], ...] = (
    ("PESD5V0S4UD", 5.0, "Nexperia PESD5V0S4UD, V_RWM"),
    ("SMS15T1G", 15.0, "onsemi SMS05T1/D rev 10, V_RWM"),
    ("SMCJ90A", 90.0, "Littelfuse SMCJ series, V_R; plan 3.2.1"),
    ("SMBJ15A", 15.0, "Littelfuse SMBJ series: the part number carries V_R"),
    ("AO3400A", 30.0, "AOS AO3400A, V_DS"),
    ("AO3407A", 30.0, "AOS AO3407A, V_DS"),
    ("IXTP26P20P", 200.0, "IXYS DS99913D, V_DSS"),
    ("BSS127", 600.0, "Infineon BSS127 rev 2.x, V_DS"),
    ("1N4148", 100.0, "V_RRM"),
    ("1N4007", 1000.0, "V_RRM"),
    ("SS14", 40.0, "V_RRM"),
    ("TPS4H160", 40.0, "TI SLVSCV8E, operating V_VS; abs max 48 V"),
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
        self.grounded = self._ground_component()

    # -- what conducts DC between which pins ----------------------------------
    @staticmethod
    def _pairs(p: Part) -> list[tuple[str, str, bool]]:
        pins = set(p.pins)
        if p.kind in _SERIES and len(p.pins) == 2:
            return [(p.pins[0], p.pins[1], False)]
        if p.kind == "D" and len(p.pins) == 2:
            if pins == {"A", "K"}:
                return [("A", "K", True)]           # current flows A -> K only
            return [(p.pins[0], p.pins[1], False)]  # polarity unknown: POL fires
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
                if (p.kind not in kinds or (fitted_only and p.dnp)
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
        holding it down -- e.g. a lever node at 12 V through R313 and D303."""
        if name not in self._pull:
            self._pull[name] = self._compute_pull(name)
        return self._pull[name]

    def _compute_pull(self, name: str):
        if self.is_stiff(name) or self.is_loaded(name):
            return None
        reach = self.walk(
            name, _SERIES + ("D",), fitted_only=False, flows=("both", "in"),
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

    def volts(self, name: str) -> tuple[float | None, str]:
        """The voltage a part on this net must survive, and why if it is not
        simply the label."""
        dec, pull = self.declared(name), self.pulled_up(name)
        if pull is not None and (dec is None or pull[0] > dec):
            label = self.nets[name].domain if name in self.nets else "?"
            return pull[0], (f" (typed {label}, but held at {pull[1]!r} = "
                             f"{pull[0]:g} V through {'+'.join(pull[2])} with "
                             f"no path to ground)")
        return dec, ""

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
    """BD-2: 84 V never reaches DRV or BRAIN -- parts OR connectors."""
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
                            f"Pack voltage stays on HVIN/CONV.")
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
        for other, path in ix.walk(name, _HV_JOIN, fitted_only=False).items():
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


def bd4_hv_creepage(d: Design) -> list[str]:
    """BD-4: every connector carrying pack voltage, labelled HV-LINK or not."""
    ix = _index(d)
    hv, _ = _hv_nets(ix)
    errs = []
    for c in d.connectors:
        carried = sorted(n for n in hv if c.refdes in ix.net_conns.get(n, ()))
        if not carried and c.interface != "HV-LINK":
            continue
        if not (c.pitch_mm >= HV_MIN_PITCH_MM):          # NaN fails too
            errs.append(
                f"BD-4: {c.refdes} carries 84 V ({', '.join(carried) or 'HV-LINK'}) "
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
            if g in GPIO_USB and not name.startswith("USB_"):
                errs.append(f"GPIO-USB: net {name!r} uses GPIO{g}, which is "
                            f"native USB D-/D+ and the OTA fallback.")
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
                            continue            # the internal service header
                        where = ("leaves the box" if c.leaves_box else
                                 f"crosses {c.interface} to another board")
                        errs.append(
                            f"GPIO-STRAP: net {name!r} is on strapping GPIO{g} "
                            f"and reaches {conn} ({c.name}), which {where}, "
                            f"{_via(path)}. Whatever holds that wire at key-on "
                            f"picks the boot mode.")

    errs.extend(_adc1(ix, gpios))
    return errs


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
        gs = gpios.get(name, set())
        if not gs:
            errs.append(f"GPIO-ADC1: {name!r} {why} but lands on no MCU pin.")
        for g in sorted(gs - GPIO_ADC1):
            errs.append(f"GPIO-ADC1: {name!r} {why} but is on GPIO{g}. ADC2 "
                        f"dies with WiFi -- use GPIO1-10.")
    return errs


# ── D14: every gate biases OFF, for the polarity the FET actually is ─────────
def d14_gate_bias(d: Design) -> list[str]:
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
        if not gate or not source or set(gate) & set(source):
            continue                                  # D14 reports these
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
            if p.kind in _SERIES:
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


# ── VR: check the voltage line on EVERY part ─────────────────────────────────
def voltage_ratings(d: Design) -> list[str]:
    ix = _index(d)
    errs = []
    gate_clamps = _gate_source_pairs(ix)
    for p in d.parts:
        required = p.kind in RATED_KINDS
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
            why_not = []
            ok = False
            for ref, pin in net.pins:
                t = ix.parts.get(ref)
                if t is None or t.kind != "TVS":
                    continue
                problems = []
                if t.dnp and not c.parked:
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
    errs = []
    for p in d.parts:
        if len(p.pins) != 2 or set(p.pins) == {"A", "K"}:
            continue
        bidirectional = p.kind == "TVS" and p.mpn.upper().rstrip("-0123456789").endswith("CA")
        if p.kind in ("D", "ZENER") or (p.kind == "TVS" and not bidirectional):
            errs.append(f"POL: {p.refdes} ({p.kind} {p.mpn}) names its pins "
                        f"{p.pins}. Name them A and K, or its direction is "
                        f"undefined and no path through it can be checked.")
    return errs


# ── HT: every body in the stack, against a stack derived from those bodies ───
def _bodies(d: Design):
    for p in d.parts:
        yield p.refdes, p.mpn, p.board, p.side, p.height_mm, p.height_confirmed, False
    for c in d.connectors:
        yield (c.refdes, c.name, c.board, "top", c.height_mm, c.height_confirmed,
               c.interface is not None)


def _is_height(h) -> bool:
    return isinstance(h, (int, float)) and not isinstance(h, bool) \
        and math.isfinite(h) and h >= 0


def heights(d: Design) -> list[str]:
    """Parts AND connectors, top side and bottom. board_params derives each
    gap from the tallest thing standing in it, the deepest thing hanging into
    it, solder tails, BD-9's plate and the mated inter-board connectors -- so a
    tall connector, a 40 mm `side="bottom"` part and a NaN all land here."""
    errs = [f"HT-NUM: {ref} ({what}) has height {h!r}. An unknown height is an "
            f"unchecked height."
            for ref, what, _b, _s, h, _c, _i in _bodies(d) if not _is_height(h)]
    if _stack_problems is None:
        errs.append("HT-GEOM: tools/board_params.py offers no stack_problems(design), "
                    "so no height in this design has been checked against the "
                    "enclosure.")
        return errs
    errs.extend(f"HT-STACK: {p}" for p in _stack_problems(d))
    return errs


ALL_RULES = (
    bd2_voltage_domain_containment,
    d10_key_wire_is_only_listened_to,
    supply_pins,
    bd4_hv_creepage,
    gpio_rules,
    d14_gate_bias,
    turn_on_path,
    voltage_ratings,
    logic_pin_levels,
    protection,
    ground_islands,
    mcp23017_bit7,
    polarity,
    heights,
)


def check_all(design: Design) -> list[str]:
    """Run every rule. Empty list means the design does its job."""
    errs: list[str] = []
    for rule in ALL_RULES:
        errs.extend(rule(design))
    return errs


def _near_limit(d: Design) -> dict[str, str]:
    """refdes -> why its unconfirmed height matters. A body's ceiling is
    whatever is tallest among the bodies that share its face of its board: that
    one sets the gap, and anything within UNCONFIRMED_MARGIN_MM of it would if
    its real height came in over. Inter-board connectors set the board spacing
    outright."""
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
        if top - h <= UNCONFIRMED_MARGIN_MM:
            out[ref] = (f"within {UNCONFIRMED_MARGIN_MM:g} mm of the tallest body "
                        f"on the {side} of {board} ({top_ref}, {top:g} mm), which "
                        f"sets that gap")
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
