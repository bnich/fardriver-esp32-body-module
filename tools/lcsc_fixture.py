"""The LCSC and EasyEDA-library facts the tests check the design against,
kept in the repo so the checks run offline and never skip.

    python3 -m tools.lcsc_fixture        # refresh tests/fixtures/lcsc.json

For every LCSC code the design orders (netlist.lcsc_catalogue and
terminal_catalogue): the part number, maker and package LCSC gives it, and
the library symbol's pin numbers and names. tests/test_lcsc_records.py holds
the design to this file and, where the service is reachable, this file to the
live library, so a stale fixture fails too.
"""
import json
import re
import sys
from pathlib import Path

from . import netlist, padmap

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "lcsc.json"

#: An ordering suffix LCSC's part number carries and the netlist's does not --
#: tape-and-reel, lead finish, packing option. With the suffix removed the two
#: are the SAME part; anything else left over is ANOTHER part. Listed from the
#: makers' own numbering, never guessed from the string: Diodes' BSS127S-7
#: minus its `-7` is BSS127S, which is still not the Infineon BSS127 (H21).
MPN_SUFFIXES = (
    "-E3/57T",      # Vishay: SMCJ90A-E3/57T -- E3 lead finish, 57T reel
    "H6327XTSA2",   # Infineon: BSS127H6327XTSA2 -- H6327 package code, XTSA2 reel
    "TV7",          # Vishay: VY2472M49Y5US6TV7 -- kinked-lead tape
    "-7",           # Diodes: 3000-piece reel (named so the strip is stated, not a hole)
)

#: A maker as the netlist's tables write it -> the word LCSC's record uses,
#: where they are not the same word. Every entry says why it is one company.
MAKER_IS = {
    "CHEMI-CON": "NCC",         # Nippon Chemi-Con
    "HONGJIACHENG": "R+O",      # one LCSC brand: "hongjiacheng" in JLC's search,
                                # "R+O" in the LCSC detail; the datasheet file is
                                # hongjiacheng-SMF18A_C19077512.pdf
}

#: The netlist's package text -> the LCSC package strings that name the SAME
#: package, where LCSC spells it differently. Anything not here must match by
#: normalised equality, so a code that moves to another package fires until
#: someone states here that the two are one package.
PACKAGE_IS = {
    "SOT-23": ("SOT-23-3",),
    "SC-74": ("SC-74-6",),                          # onsemi's name for SOT-23-6 / TSOP-6
    "DO-214AB (SMC)": ("SMC(DO-214AB)", "SMC"),
    "DO-214AC (SMA)": ("SMA(DO-214AC)", "SMA"),
    "DO-214AA (SMB)": ("DO-214AA(SMB)", "SMB"),
    "TO-263AA (D2PAK)": ("TO-263AA", "TO-263"),
    "2220 C0G": ("2220",),
    "28-HTSSOP PowerPAD, 0.65 mm": ("HTSSOP-28-EP",),
    "8-HVSSOP PowerPAD": ("HVSSOP-8",),
    "WQFN-30 (RNP), 0.5 mm": ("WQFN-30-EP(4x6)",),
    "SMD, 6.9 × 6.5 mm": ("SMD,6.9x6.5mm",),
    "WROOM-1 / WROOM-1U SMD module": ("SMD,19.2x18mm",),
    # Loose through-hole parts, described by their body in the netlist:
    "radial can 18 × 25 mm, lying down": ("Through Hole,D18xL25mm",),
    "radial polymer 10 × 15 mm, lying down": ("Through Hole,D10xL15mm",),
    "radial disc, lying FLAT": ("Through Hole,P=7.5mm",),
    "5 × 20 fuse holder: two PCB clips": ("Through Hole",),
    "5 × 20 ceramic, in the holder FH201": ("D5.2xL20mm",),
}

#: A connector bought as a longer strip and CUT to the design's contact
#: count: the record's symbol has MORE pins than the connector, never fewer.
#: Every other connector's contact count equals its record's (M14).
CUT_TO_LENGTH = {
    "C2333": "a 2×40 strip cut to STACK's 2×29 (netlist._FAB_CONN J406)",
}


def service():
    """~/tools/lcsc-search's Service, or None when it is not on this machine."""
    try:
        sys.path.insert(0, str(Path.home() / "tools/lcsc-search"))
        from lcsc_search import Service
    except ImportError:
        return None
    return Service()


def codes() -> list[str]:
    d = netlist.checked()
    out = set(netlist.lcsc_catalogue()) | set(netlist.terminal_catalogue())
    out |= {x.lcsc for x in (*d.parts, *d.connectors) if x.lcsc}
    out |= {c.plug for c in d.connectors if c.plug}
    out |= {code for code in padmap.FOOTPRINT_FROM_MPN.values() if code}
    return sorted(out)


def record(svc, code: str) -> dict:
    from .footprint_lib import Library, allegro_safe
    part = svc.part(code)
    if part is None:
        raise LookupError(f"LCSC has no part {code}")
    pins = None
    dev = svc.footprint(code)
    if dev is not None and dev.get("symbol_uuid"):
        doc = svc.document(dev["symbol_uuid"])
        if doc is not None:
            pins = [list(p) for p in padmap.library_pins(doc["data"])]
    got = Library(svc).footprint(code)
    return {"mpn": part.mpn, "manufacturer": part.manufacturer,
            "package": part.package, "symbol_pins": pins,
            "footprint": allegro_safe(got[0]) if got else None}


def _norm(text: str) -> str:
    return "".join(text.upper().split())


def _bare(mpn: str) -> str:
    """The part number with ONE listed ordering suffix removed."""
    m = _norm(mpn)
    for suffix in MPN_SUFFIXES:
        s = _norm(suffix)
        if m.endswith(s) and len(m) > len(s):
            return m[:-len(s)]
    return m


def same_mpn(ours: str, theirs: str) -> bool:
    """Equal part numbers once a listed suffix is stripped from either. Never
    a substring test: `BSS127` ⊂ `BSS127S-7` is the swap CLAUDE.md forbids."""
    return _bare(ours) == _bare(theirs)


def _maker_words(text: str) -> set[str]:
    return {w for w in re.split(r"[\s(),/]+", text.upper()) if w}


def same_maker(ours: str, theirs: str) -> bool:
    """The netlist's maker word is one of the words in LCSC's manufacturer
    string (`MDD` in `MDD(Microdiode Semiconductor)`, `IXYS` in
    `Littelfuse/IXYS`), or `MAKER_IS` says which word it is."""
    word = ours.upper()
    return word in _maker_words(theirs) or MAKER_IS.get(word, "") in _maker_words(theirs)


def same_package(ours: str, theirs: str) -> bool:
    if _norm(ours) == _norm(theirs):
        return True
    return _norm(theirs) in {_norm(x) for x in PACKAGE_IS.get(ours, ())}


def table_parts(table: str, mpn: str) -> tuple[str | None, str | None]:
    """(maker word, part-number token) read out of a table string such as
    `"Vishay SMCJ90A-E3/57T"`, `"SMBJ18A (R+O)"` or `"Samsung CL21B105KBFNNNE,
    X7R"`: the token that IS `mpn` (suffix-stripped equality), and the first
    other token, its parentheses removed. (None, None) when no token is
    the part."""
    tokens = [t for t in re.split(r"[\s,]+", table) if t]
    hit = next((i for i, t in enumerate(tokens) if same_mpn(t, mpn)), None)
    if hit is None:
        return None, None
    rest = [t for i, t in enumerate(tokens) if i != hit]
    if not rest:
        return None, tokens[hit]
    maker = re.split(r"[()]", rest[0])
    return next((m for m in maker if m), None), tokens[hit]


def terminal_maker(pattern: str) -> str:
    """The maker of the terminal family a `terminal_catalogue` pattern names,
    read from its pitch: `EDGRM-3.81-0?8P` is a 3.81 mm part, Kangnex's."""
    m = re.search(r"-(\d+(?:\.\d+)?)-", pattern)
    if not m:
        raise ValueError(f"terminal pattern {pattern!r} states no pitch")
    return netlist._TB_FAMILY[float(m.group(1))]["maker"]


def check(d, fixture: dict, catalogue=None, terminals=None) -> list[str]:
    """Every problem between the design's LCSC codes and what LCSC says they
    are. Empty: each code is the part its table names -- maker, part number
    and package -- and that part is the one the rules checked.

    Part numbers compare by EQUALITY after `MPN_SUFFIXES`; a substring test
    let Diodes' BSS127S-7, TECH PUBLIC's TPSMS05T1G and MDD's SMCJ90A through
    as the parts they are named after (H21)."""
    catalogue = netlist.lcsc_catalogue() if catalogue is None else catalogue
    terminals = netlist.terminal_catalogue() if terminals is None else terminals
    errs = []
    used = {x.lcsc for x in (*d.parts, *d.connectors) if x.lcsc}
    used |= {c.plug for c in d.connectors if c.plug}
    for code in sorted(used | set(catalogue) | set(terminals)):
        if code not in fixture:
            errs.append(f"{code}: no record in {FIXTURE.name}; run "
                        f"`python3 -m tools.lcsc_fixture` and read what it says")
    for code, table in sorted(catalogue.items()):
        rec = fixture.get(code)
        if not rec:
            continue
        maker, _ = table_parts(table, rec["mpn"])
        if maker is None:
            errs.append(f"{code} is {rec['mpn']} ({rec['manufacturer']}), not the "
                        f"{table!r} its table orders")
        elif not same_maker(maker, rec["manufacturer"]):
            errs.append(f"{code} is {rec['mpn']} by {rec['manufacturer']!r}, not "
                        f"{maker}'s as its table {table!r} says -- a same-numbered "
                        f"part from another maker is another part")
    for code, pattern in sorted(terminals.items()):
        rec = fixture.get(code)
        if not rec:
            continue
        if not re.search(pattern, rec["mpn"]):
            errs.append(f"{code} is {rec['mpn']}, not a terminal of the family "
                        f"and size /{pattern}/")
        elif not same_maker(terminal_maker(pattern), rec["manufacturer"]):
            errs.append(f"{code} is {rec['mpn']} by {rec['manufacturer']!r}, not "
                        f"{terminal_maker(pattern)}'s, whose drawing the height "
                        f"model reads for that pitch")
    for x in (*d.parts, *d.connectors):
        if x.lcsc and x.lcsc not in catalogue and x.lcsc not in terminals:
            errs.append(f"{x.refdes}: {x.lcsc} is ordered from no table, so no "
                        f"maker part number was ever stated for it")
    for p in d.parts:
        rec = fixture.get(p.lcsc)
        if not rec:
            continue
        by_value = p.mpn.startswith(("R-", "C-")) or p.mpn == "NET-TIE"
        if not by_value and not same_mpn(p.mpn, rec["mpn"]):
            errs.append(f"{p.refdes}: the netlist checks {p.mpn} but {p.lcsc} is "
                        f"{rec['mpn']}")
        if not same_package(p.package, rec["package"]):
            errs.append(f"{p.refdes}: the netlist places a {p.package!r} but "
                        f"{p.lcsc} comes in {rec['package']!r}; if those are one "
                        f"package, say so in lcsc_fixture.PACKAGE_IS")
    for c in d.connectors:
        rec = fixture.get(c.lcsc)
        if not rec or rec["symbol_pins"] is None:
            continue
        n = len(rec["symbol_pins"])
        if c.lcsc in CUT_TO_LENGTH:
            if len(c.pins) > n:
                errs.append(f"{c.refdes}: {len(c.pins)} contacts cut from {c.lcsc}, "
                            f"whose strip has {n} ({CUT_TO_LENGTH[c.lcsc]})")
        elif len(c.pins) != n:
            errs.append(f"{c.refdes}: {len(c.pins)} contacts in the netlist, but "
                        f"{c.lcsc} ({rec['mpn']}) has {n}")
    return errs


def load() -> dict:
    return json.loads(FIXTURE.read_text())


def main() -> int:
    svc = service()
    if svc is None:
        print("~/tools/lcsc-search is not on this machine: nothing refreshed")
        return 1
    data = {code: record(svc, code) for code in codes()}
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {FIXTURE.relative_to(Path.cwd()) if FIXTURE.is_relative_to(Path.cwd()) else FIXTURE}: "
          f"{len(data)} codes")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except netlist.NotACircuit as e:
        print(e)
        sys.exit(1)
