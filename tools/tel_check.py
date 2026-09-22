"""Compare EasyEDA's exported netlist (.tel) for one board with ours.

    python3 -m tools.tel_check BOARD ~/Downloads/Netlist_BOARD_<date>.tel

The export is the editor's own reading of the generated project, so every pin
it puts on a net is a pin the layout will route.  A part that is not converted
to PCB (the fuse) is left out of the export entirely, and its nets stay split,
as the copper will be.  Exits 0 when the two agree.
"""
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .eprj3.schematic import board_refs, converted_to_pcb, landed_pins

_PACKAGE = re.compile(r"(\S+) ! (\S+) ! ('[^']*'|[^;]*?)\s*;\s*(.*)")
_NET = re.compile(r"'?([^';]+?)'?\s*;\s*(.*)")


@dataclass
class Tel:
    packages: dict            # refdes -> footprint title
    nets: dict                # net name -> {(refdes, pin)}


@dataclass
class Result:
    problems: list
    left_off: list            # parts not converted to PCB, absent as they should be
    nets: int = 0
    pins: int = 0
    ok: bool = field(init=False)

    def __post_init__(self):
        self.ok = not self.problems


def _records(block):
    """Logical records: a trailing ',' continues a line; a lone ',' line sits
    between records and carries nothing."""
    out, buf = [], []
    for line in block.splitlines():
        s = line.strip()
        if not s or s == ",":
            continue
        more = s.endswith(",")
        buf.append(s[:-1].strip() if more else s)
        if not more:
            out.append(" ".join(buf))
            buf = []
    if buf:
        raise ValueError(f"record never ends: {' '.join(buf)!r}")
    return out


def parse(text):
    sections, name = defaultdict(list), None
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("$"):
            name = line.strip()
        elif name:
            sections[name].append(line)
    packages = {}
    for rec in _records("\n".join(sections["$PACKAGES"])):
        m = _PACKAGE.fullmatch(rec)
        if not m:
            raise ValueError(f"not a $PACKAGES record: {rec!r}")
        for ref in m.group(4).split():
            packages[ref] = m.group(1)
    nets = {}
    for rec in _records("\n".join(sections["$NETS"])):
        m = _NET.fullmatch(rec)
        if not m:
            raise ValueError(f"not a $NETS record: {rec!r}")
        nets[m.group(1)] = {tuple(p.rsplit(".", 1)) for p in m.group(2).split()}
    return Tel(packages, nets)


def expected_footprints(design, board, fixture=None):
    """refdes -> the footprint title the generator binds, as Allegro-safe as
    the export writes it: generated here, or the LCSC library's (from
    tests/fixtures/lcsc.json). None where it cannot be known offline."""
    from . import footprint_lib, lcsc_fixture, padmap
    if fixture is None:
        try:
            fixture = lcsc_fixture.load()
        except FileNotFoundError:
            fixture = {}
    out = {}
    refs = board_refs(design, board)
    for x in (*design.parts, *design.connectors):
        if x.refdes not in refs:
            continue
        code = padmap.footprint_source(x)
        if code is None:
            gen = footprint_lib.generated(x)
            out[x.refdes] = footprint_lib.allegro_safe(gen[0]) if gen else None
        else:
            out[x.refdes] = (fixture.get(code) or {}).get("footprint")
    return out


def compare(design, board, tel, fixture=None):
    refs = board_refs(design, board)
    off = sorted(p.refdes for p in design.parts
                 if p.refdes in refs and not converted_to_pcb(p))
    want = defaultdict(set)
    for (ref, pin), net in landed_pins(design).items():
        if ref in refs and ref not in off:
            want[net].add((ref, pin))
    problems = []
    for name in sorted(set(want) | set(tel.nets)):
        got, exp = tel.nets.get(name, set()), want.get(name, set())
        if got != exp:
            problems.append(f"net {name}: missing {sorted(exp - got)}, extra {sorted(got - exp)}")
    seen = defaultdict(list)
    for name, pins in tel.nets.items():
        for pin in pins:
            seen[pin].append(name)
    problems += [f"{'.'.join(pin)} is on {len(names)} nets: {', '.join(sorted(names))}"
                 for pin, names in sorted(seen.items()) if len(names) > 1]
    for ref in off:
        if ref in tel.packages or any(ref == r for r, _ in seen):
            problems.append(f"{ref} is not converted to PCB, but the export has it")
    problems += [f"{ref} is missing from $PACKAGES"
                 for ref in sorted(refs - set(off) - set(tel.packages))]
    problems += [f"{ref} is in $PACKAGES but not on {board}"
                 for ref in sorted(set(tel.packages) - refs)]
    # Pads carry pin names, so a wrong land pattern with the right pad names
    # would pass the nets: the footprint itself is compared too.
    for ref, want_fp in sorted(expected_footprints(design, board, fixture).items()):
        got_fp = tel.packages.get(ref)
        if got_fp is not None and want_fp is not None and got_fp != want_fp:
            problems.append(f"{ref} has footprint {got_fp}, the generator bound {want_fp}")
    return Result(problems, off, len(tel.nets), sum(map(len, tel.nets.values())))


def main(argv=None):
    from . import netlist
    board, path = (argv or sys.argv[1:])[:2]
    try:
        design = netlist.checked()
    except netlist.NotACircuit as e:
        print(f"⛔ REFUSED -- {e}")
        return 1
    r = compare(design, board, parse(Path(path).read_text(encoding="utf-8")))
    print(f"{board}: {r.nets} nets, {r.pins} pins in the export"
          + (f"; left off the PCB as intended: {' '.join(r.left_off)}" if r.left_off else ""))
    for p in r.problems:
        print(f"  ✗ {p}")
    print("  identical to the generator's netlist" if r.ok else f"  {len(r.problems)} problem(s)")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
