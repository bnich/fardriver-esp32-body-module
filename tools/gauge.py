#!/usr/bin/env python3
"""The gauge project: open this in EasyEDA Pro BEFORE trusting the full build.

    python3 tools/gauge.py [--out DIR]          (default: build-eprj3/)

Writes `<out>/gauge-revv1/`, `<out>/gauge-revv1.zip` and
`<out>/GAUGE-INSTRUCTIONS.md`: one board, one sheet, eight resistors R1-R8 in
four pairs.  Each pair is joined by a different mechanism, so one look at the
netlist says which mechanism EasyEDA Pro honours:

  1. GAUGE_GEOM  R1.2-R2.1  one WIRE whose LINE runs from anchor to anchor,
                            named by its NET attribute.  Geometric coincidence
                            is the exemplified mechanism: this is the CONTROL.
  2. GAUGE_WIRE  R3.2-R4.1  a separate stub on each pin, both NET=GAUGE_WIRE,
                            no flags, no shared geometry.
  3. GAUGE_FLAG  R5.2-R6.1  a separate stub on each pin, NET="" on both, each
                            ending on a net flag named GAUGE_FLAG.
  4. GAUGE_BOTH  R7.2-R8.1  stub + flag + wire name, all GAUGE_BOTH -- exactly
                            what `build_project.py` emits.

Experiments 2-4 call `schematic.connect`, the one function that connects a pin
in the production build, with naming "wire", "flag" and "both" respectively.
So each experiment IS the production output for that `schematic.NAMING`.

No free-text note is placed on the sheet: the spec documents no page-level
`TEXT` record, and an undocumented record is a guess.  The explanation lives in
GAUGE-INSTRUCTIONS.md beside the project instead.
"""
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.build_project import (DEFAULT_OUT, eprj2_line, write,  # noqa: E402
                                 write_eprj2)
from tools.eprj3 import footprints, placement, schematic  # noqa: E402
from tools.eprj3 import symbols as sym  # noqa: E402
from tools.eprj3.project import Project  # noqa: E402
from tools.model import Part  # noqa: E402

PROJECT_NAME = "gauge-revv1"
BOARD = "GAUGE"
INSTRUCTIONS = "GAUGE-INSTRUCTIONS.md"


@dataclass(frozen=True)
class Experiment:
    number: int
    net: str
    left: str           # its pin "2" is joined ...
    right: str          # ... to this one's pin "1"
    mechanism: str      # "geometry", or a schematic.NAMING value
    how: str


EXPERIMENTS = (
    Experiment(1, "GAUGE_GEOM", "R1", "R2", "geometry",
               "one wire drawn from R1.2 to R2.1, named by its NET attribute "
               "(the control: geometric coincidence is the proven mechanism)"),
    Experiment(2, "GAUGE_WIRE", "R3", "R4", "wire",
               "a separate stub on each pin, both wires NET = GAUGE_WIRE, no "
               "flags, nothing drawn between them"),
    Experiment(3, "GAUGE_FLAG", "R5", "R6", "flag",
               "a separate stub on each pin with an EMPTY NET name, each "
               "ending on a net flag named GAUGE_FLAG"),
    Experiment(4, "GAUGE_BOTH", "R7", "R8", "both",
               "stub + net flag + wire name, all GAUGE_BOTH -- exactly what "
               "the full build emits for every pin"),
)

#: Row pitch and the two resistor columns, in schematic units (0.01 inch).
#: The columns are 3 inches apart so a stub, its flag and its name text on one
#: resistor are nowhere near those of its partner: experiments 2-4 must share
#: NO geometry, or they would test coincidence instead of naming.
ROW_PITCH = 100
LEFT_X = 200
RIGHT_X = 500
TOP_Y = -500


def resistor(refdes):
    """A `Part` is what the symbol and device emitters take, and its `board`
    is a deck of the stack by type. The gauge's own board is `BOARD` above,
    on the project; nothing here reads the part's, so it borrows the bottom
    deck to construct."""
    return Part(refdes, "R-10k", "0805", "POWER", "R", ("1", "2"), 0.6,
                value="10k")


def build(epoch_ms=None):
    """The gauge project in memory.  Returns (project, page)."""
    kwargs = {} if epoch_ms is None else {"epoch_ms": epoch_ms}
    project = Project(PROJECT_NAME, **kwargs)
    project.add_board(BOARD)
    sheet = project.boards[0].schematic.sheets[0]
    page = schematic.Page(sheet.uuid, client=sheet.client,
                          epoch_ms=sheet.epoch_ms,
                          edit_version=sheet.edit_version)
    uid = 0
    for exp in EXPERIMENTS:
        y = TOP_Y + (exp.number - 1) * ROW_PITCH
        placed = {}
        for ref, x in ((exp.left, LEFT_X), (exp.right, RIGHT_X)):
            part = resistor(ref)
            item = placement.Item(ref, sym.for_part(part), {}, ref,
                                  schematic.part_name(part))
            uid += 1
            placed[ref] = schematic.place_part(page, item, x, y, f"gge{uid}",
                                               part=part)
        a = placed[exp.left].anchors["2"]
        b = placed[exp.right].anchors["1"]
        if exp.mechanism == "geometry":
            page.wire([(a[0], a[1], b[0], b[1])], role=("geometry", exp.net),
                      net=schematic.validate_net_name(exp.net),
                      label=((a[0] + b[0]) // 2, a[1] - 5, "CENTER_BOTTOM"),
                      show=True)
        else:
            outward_a = sym.for_part(resistor(exp.left)).pin("2").outward
            outward_b = sym.for_part(resistor(exp.right)).pin("1").outward
            schematic.connect(page, a, outward_a, exp.net,
                              role=(exp.left, "2"), naming=exp.mechanism)
            schematic.connect(page, b, outward_b, exp.net,
                              role=(exp.right, "1"), naming=exp.mechanism)
    # EasyEDA Pro will not export a netlist with any footprint missing, and the
    # netlist is how the gauge is read.  A generic 0805 outline: layout never
    # uses the gauge.
    r = resistor(EXPERIMENTS[0].left)
    item = placement.Item(r.refdes, sym.for_part(r), {}, r.refdes, schematic.part_name(r))
    page.bind_footprint(item.symbol, "R0805_GAUGE", footprints.two_pad(1.9, 1.0, 1.3),
                        device=schematic.device_for(item, part=r))
    sheet.library_records = page.library_records()
    sheet.page_records = page.page_records(first_ticket=2)
    return project, page


def instructions():
    rows = "\n".join(
        f"| {e.number} | `{e.net}` | {e.left}.2 and {e.right}.1 | {e.how} |"
        for e in EXPERIMENTS)
    return f"""# Gauge: does EasyEDA Pro take the generated nets?

`{PROJECT_NAME}` is a throwaway project: one board (`{BOARD}`), one sheet
(`P1`), eight 10k resistors in four pairs. Each pair is joined a different way.
For each pair, the question is whether EasyEDA Pro puts both resistors on
**one** net.

| # | Net | Pins | How the pins are joined |
|---|---|---|---|
{rows}

Experiment 1 is the control. It joins its pins by drawing a wire between
them, and that is the one mechanism the format documentation demonstrates. If
experiment 1 fails, the fault is not in the naming. Stop and report.

## Steps

1. EasyEDA Pro 3.2.149 opens neither the folder nor the zip: it opens `.eprj2`.
   Wrap `{PROJECT_NAME}/` as `{PROJECT_NAME}.eprj2`, open that file by its
   path (a file dropped into the projects folder is not listed until it has
   been opened), and copy any error or warning text exactly.
2. Open sheet `P1`. You should see four rows, each with two resistors:
   - row 1 has a wire between its resistors;
   - rows 2 to 4 have only short stubs, with a label or flag at the end of each.
3. Open the netlist. Use the net list in the design panel, or export a
   netlist and read the file.
4. For each of `GAUGE_GEOM`, `GAUGE_WIRE`, `GAUGE_FLAG` and `GAUGE_BOTH`:
   does the net exist, and does it list **both** of its resistor pins? If the
   pair is joined under a different name (for example `NET1`), write that
   name down.

## Report

- whether the project opened, and any error text;
- four yes/no answers, one per experiment, with any unexpected net name.

## What the answers mean

The full build connects every pin exactly as experiment 4 does. Which naming
records it writes is set by `NAMING` in `tools/eprj3/schematic.py`. After
changing it, run `python3 tools/build_project.py` again.

| Result | Meaning | Action |
|---|---|---|
| 4 joins | Stub + flag + wire name works | None. The full build is good as generated (`NAMING = "both"`) |
| 4 fails, 3 joins | Flags name nets, and the wire name gets in the way | Set `NAMING = "flag"` |
| 4 fails, 2 joins, 3 fails | Wire names name nets; flags do not | Set `NAMING = "wire"` |
| only 1 joins | Neither naming mechanism joins separate wires | The stub approach does not work. The emitter must draw real wires from pin to pin |
| 1 fails | The format itself is off | Stop and report. Naming is not the problem |
"""


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the EasyEDA Pro gauge project.")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help=f"output directory (default: {DEFAULT_OUT}/)")
    parser.add_argument("--template",
                        help="an .eprj2 EasyEDA Pro saved (default: found in "
                             "the editor's folders)")
    args = parser.parse_args(argv)
    project, _ = build()
    root, zip_path = write(project, args.out)
    notes = Path(args.out) / INSTRUCTIONS
    notes.write_text(instructions(), encoding="utf-8", newline="\n")
    sch = root / "sch" / BOARD / "P1.esch2"
    print(f"{project.name}: 1 board, 1 sheet, 8 resistors, "
          f"{len(EXPERIMENTS)} experiments -> {root}")
    for e in EXPERIMENTS:
        print(f"  {e.number}. {e.net:11} {e.left}.2-{e.right}.1  "
              f"{e.mechanism}")
    print(f"  sheet {sch.stat().st_size} B   zip {zip_path} "
          f"({zip_path.stat().st_size} B)")
    print(eprj2_line(*write_eprj2(root, args.template)))
    print(f"Open it in EasyEDA Pro and follow {notes}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
