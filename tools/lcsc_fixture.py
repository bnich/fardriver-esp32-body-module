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
import sys
from pathlib import Path

from . import netlist, padmap

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "lcsc.json"


def service():
    """~/tools/lcsc-search's Service, or None when it is not on this machine."""
    try:
        sys.path.insert(0, str(Path.home() / "tools/lcsc-search"))
        from lcsc_search import Service
    except ImportError:
        return None
    return Service()


def codes() -> list[str]:
    d = netlist.current()
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


def check(d, fixture: dict, catalogue=None, terminals=None) -> list[str]:
    """Every problem between the design's LCSC codes and what LCSC says they
    are. Empty: each code is the part its table names, and that part is the
    one the rules checked."""
    import re
    catalogue = netlist.lcsc_catalogue() if catalogue is None else catalogue
    terminals = netlist.terminal_catalogue() if terminals is None else terminals
    errs = []
    used = {x.lcsc for x in (*d.parts, *d.connectors) if x.lcsc}
    used |= {c.plug for c in d.connectors if c.plug}
    for code in sorted(used | set(catalogue) | set(terminals)):
        if code not in fixture:
            errs.append(f"{code}: no record in {FIXTURE.name}; run "
                        f"`python3 -m tools.lcsc_fixture` and read what it says")
    for code, maker in sorted(catalogue.items()):
        rec = fixture.get(code)
        if rec and _norm(rec["mpn"]) not in _norm(maker):
            errs.append(f"{code} is {rec['mpn']} ({rec['manufacturer']}), not the "
                        f"{maker!r} its table orders")
    for code, pattern in sorted(terminals.items()):
        rec = fixture.get(code)
        if rec and not re.search(pattern, rec["mpn"]):
            errs.append(f"{code} is {rec['mpn']}, not a terminal of the family "
                        f"and size /{pattern}/")
    for x in (*d.parts, *d.connectors):
        if x.lcsc and x.lcsc not in catalogue and x.lcsc not in terminals:
            errs.append(f"{x.refdes}: {x.lcsc} is ordered from no table, so no "
                        f"maker part number was ever stated for it")
    for p in d.parts:
        rec = fixture.get(p.lcsc)
        if rec and not p.mpn.startswith(("R-", "C-")) and p.mpn != "NET-TIE" \
                and _norm(p.mpn) not in _norm(rec["mpn"]):
            errs.append(f"{p.refdes}: the netlist checks {p.mpn} but {p.lcsc} is "
                        f"{rec['mpn']}")
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
    sys.exit(main())
