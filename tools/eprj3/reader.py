"""Read a generated sheet back, the way the application would, and derive its nets.

This is the check that the emitted BYTES carry the design -- not what the
emitter meant to write. It knows nothing about `schematic.py`: it parses the
records with the grammar (spec §3.2), transforms every symbol pin by its
component's placement (spec §9, by trigonometry), unions `LINE` endpoints per
`lineGroup`, names each conductor from the net flags touching it (`Global Net
Name`) and from the wires' `NET` attributes, and merges conductors that share a
name.

It was calibrated before it was trusted: on the official example's sheet it
yields VCC = {R1.2, R2.2, C1.2, L1.2} and GND = {R1.1, R2.1, C1.1, L1.1}, and
on the spec's two-resistor example SIG1 = {R1.2, R2.1}. Those vendor files are
not in this repository; the negative controls in tests/test_schematic.py -- a
moved component and a renamed flag must each break the comparison -- keep it
honest here.

⚠️ What it models is the SPEC's reading of the application: that a net flag or
a `NET` name joins separate conductors is inferred, not demonstrated. The gauge
project (tools/gauge.py) is where the application itself answers.
"""
import collections
import json
import math
from dataclasses import dataclass, field

_DEC = json.JSONDecoder()


class ReadError(ValueError):
    """The bytes are not a sheet the reader can parse."""


def parse_records(text):
    """Grammar-exact, the way the application splits a file (spec §3.2):
    records on "|" + LF, then the header is decoded as ONE JSON value and must
    be followed immediately by "||".  Returns (header, payload, raw)."""
    out = []
    for raw in text.split("|\n"):
        head, end = _DEC.raw_decode(raw)
        rest = raw[end:]
        if not rest.startswith("||"):
            raise ReadError(f"no '||' after header: {raw[:80]!r}")
        payload = rest[2:]
        out.append((head, json.loads(payload) if payload else None, raw))
    return out


def reserialise(records):
    def compact(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return "|\n".join(compact(h) + "||" + ("" if p is None else compact(p))
                      for h, p, _ in records)


def documents(records):
    docs = []
    for head, payload, _ in records:
        if head["type"] == "DOCHEAD":
            docs.append({"docType": payload["docType"],
                         "uuid": payload["uuid"], "head": payload,
                         "records": []})
        else:
            if not docs:
                raise ReadError("a record before the first DOCHEAD")
            docs[-1]["records"].append((head, payload))
    return docs


def transform(px, py, cx, cy, rotation, mirror=False):
    """Spec §9 `place()`, by trigonometry: rotate, mirror, translate."""
    r = math.radians(rotation)
    c, s = math.cos(r), math.sin(r)
    x = px * c + py * s
    y = -px * s + py * c
    if mirror:
        x = -x
    return (round(cx + x, 6) + 0.0, round(cy + y, 6) + 0.0)


@dataclass
class Sheet:
    """What the reader sees in one sheet file."""
    symbols: dict            # uuid -> {"docType", "pins": [(x, y, number)]}
    devices: dict            # uuid -> attributes
    components: dict         # id -> payload
    attrs: dict              # parentId -> {key: payload}
    wires: set
    lines: list              # payloads
    page_meta: dict

    def attr(self, parent, key):
        a = self.attrs.get(parent, {}).get(key)
        return None if a is None else a["value"]

    def symbol_of(self, cid):
        symu = self.attr(cid, "Symbol")
        if symu is None:
            symu = self.devices.get(self.attr(cid, "Device"), {}).get("Symbol")
        return symu

    def global_net_name(self, cid):
        return (self.attr(cid, "Global Net Name")
                or self.devices.get(self.attr(cid, "Device"), {})
                .get("Global Net Name"))

    def anchors(self, cid):
        """[(point, pin number)] for one component, absolute."""
        c = self.components[cid]
        return [(transform(x, y, c["x"], c["y"], c["rotation"],
                           c.get("isMirror", False)), num)
                for x, y, num in self.symbols[self.symbol_of(cid)]["pins"]]

    def is_flag(self, cid):
        return self.symbols[self.symbol_of(cid)]["docType"] == 18


def read_sheet(text):
    docs = documents(parse_records(text))
    symbols, devices = {}, {}
    for d in docs:
        if d["docType"] == "SYMBOL":
            meta = next(p for h, p in d["records"] if h["type"] == "META")
            pins, numbers = {}, {}
            for h, p in d["records"]:
                if h["type"] == "PIN":
                    pins[h["id"]] = (p["x"], p["y"])
                elif (h["type"] == "ATTR" and p
                      and p.get("key") == "Pin Number"):
                    numbers[p["parentId"]] = p["value"]
            symbols[d["uuid"]] = {
                "docType": meta["docType"],
                "pins": [(x, y, numbers.get(pid))
                         for pid, (x, y) in pins.items()]}
        elif d["docType"] == "DEVICE":
            meta = next(p for h, p in d["records"] if h["type"] == "META")
            devices[d["uuid"]] = meta.get("attributes", {})
    pages = [d for d in docs if d["docType"] == "SCH_PAGE"]
    if len(pages) != 1:
        raise ReadError(f"expected one SCH_PAGE, found {[d['docType'] for d in docs]}")
    comps, attrs, wires, lines = {}, collections.defaultdict(dict), set(), []
    meta = None
    for h, p in pages[0]["records"]:
        if h["type"] == "META":
            meta = p
        elif h["type"] == "COMPONENT":
            comps[h["id"]] = p
        elif h["type"] == "WIRE":
            wires.add(h["id"])
        elif h["type"] == "LINE":
            lines.append(p)
        elif h["type"] == "ATTR" and p:
            attrs[p["parentId"]][p["key"]] = p
    return Sheet(symbols, devices, comps, dict(attrs), wires, lines, meta)


@dataclass
class Derived:
    nets: dict = field(default_factory=dict)      # name -> {(ref, pin)}
    unnamed: list = field(default_factory=list)   # member sets with no name
    conflicts: list = field(default_factory=list)  # (names, members)
    floating: set = field(default_factory=set)    # (ref, pin) on no wire
    dangling_flags: list = field(default_factory=list)


def derive_nets(text):
    """Nets from the geometry and the naming records -- in that order:
    `lineGroup` endpoint coincidence, then net-flag `Global Net Name`, then
    wire `NET` names; conductors sharing a name are one net."""
    sheet = read_sheet(text)
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    for ln in sheet.lines:
        w = ("W", ln["lineGroup"])
        union(("P",) + transform(ln["startX"], ln["startY"], 0, 0, 0), w)
        union(("P",) + transform(ln["endX"], ln["endY"], 0, 0, 0), w)

    members = collections.defaultdict(set)
    names = collections.defaultdict(set)
    out = Derived()
    for cid in sheet.components:
        if sheet.symbol_of(cid) not in sheet.symbols:
            raise ReadError(f"component {cid} names no embedded symbol")
        gnn = sheet.global_net_name(cid)
        ref = sheet.attr(cid, "Designator")
        for point, number in sheet.anchors(cid):
            key = ("P",) + point
            if gnn:
                if key in parent:
                    names[find(key)].add(gnn)
                else:
                    out.dangling_flags.append(gnn)
            elif key in parent:
                members[find(key)].add((ref, number))
            else:
                out.floating.add((ref, number))
    for wid in sheet.wires:
        value = sheet.attr(wid, "NET")
        if value:
            names[find(("W", wid))].add(value)

    nets = collections.defaultdict(set)
    for root, mem in members.items():
        n = names.get(root, set())
        if not n:
            out.unnamed.append(mem)
        elif len(n) > 1:
            out.conflicts.append((sorted(n), sorted(mem)))
        else:
            nets[next(iter(n))] |= mem
    out.nets = dict(nets)
    return out


def netlist_slice(design, board):
    """What the board's sheet must carry: each net's pins on this board."""
    refs = ({p.refdes for p in design.parts if p.board == board}
            | {c.refdes for c in design.connectors if c.board == board})
    out = {}
    for net in design.nets:
        pins = {(r, p) for r, p in net.pins if r in refs}
        if pins:
            out[net.name] = pins
    return out


def expected_floating(design, board):
    """Pins that must be on no wire: `nc` pins and unused cavities."""
    out = set()
    for p in design.parts:
        if p.board == board:
            out |= {(p.refdes, pin) for pin in p.nc}
    for c in design.connectors:
        if c.board == board:
            out |= {(c.refdes, cp.pin) for cp in c.pins if not cp.net}
    return out


def diff(derived, want):
    lines = []
    for name in sorted(set(derived) | set(want)):
        got, exp = derived.get(name, set()), want.get(name, set())
        if got != exp:
            lines.append(f"{name}: missing {sorted(exp - got)} "
                         f"extra {sorted(got - exp)}")
    return lines


def compare(text, design, board):
    """Every way the sheet `text` fails to carry `board`'s slice of `design`.

    Empty means the emitted bytes connect exactly the pins the netlist says,
    leave unconnected exactly the pins it leaves unconnected, and name no
    conductor ambiguously.
    """
    try:
        got = derive_nets(text)
    except (ReadError, KeyError, ValueError) as exc:
        return [f"{board}: the sheet does not read back: {exc}"]
    out = [f"{board}: {line}" for line in diff(got.nets, netlist_slice(design, board))]
    want_floating = expected_floating(design, board)
    for pin in sorted(got.floating - want_floating):
        out.append(f"{board}: {pin[0]}.{pin[1]} is on no wire but the netlist connects it")
    for pin in sorted(want_floating - got.floating):
        out.append(f"{board}: {pin[0]}.{pin[1]} is wired but the netlist leaves it open")
    for mem in got.unnamed:
        out.append(f"{board}: a conductor with no net name joins {sorted(mem)}")
    for names, mem in got.conflicts:
        out.append(f"{board}: one conductor carries several names {names}: {mem}")
    for name in got.dangling_flags:
        out.append(f"{board}: a net flag {name!r} touches no wire")
    return out
