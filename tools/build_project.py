#!/usr/bin/env python3
"""Generate the EasyEDA Pro project for the four-board set.

    python3 tools/build_project.py [--out DIR]          (default: build-eprj3/)

Writes `<out>/revv1-module/`, an `.eprj3` folder project with one board per
`board_params.STACK_ORDER` layer -- HVIN, CONV, DRV, BRAIN -- each with:

  * its schematic: one sheet holding every part and connector of that board,
    every connected pin wired to its net (stub + net flag + wire name, see
    `eprj3/schematic.py`);
  * its PCB: the outline, the four mounting holes and the design rules from
    `eprj3/pcb.py`.

and `<out>/revv1-module.eprj2`, the single-file project EasyEDA Pro 3.2.149
opens (it does not open `.eprj3`), plus `<out>/revv1-module.zip` of the folder
and `<out>/layout-rules.txt`: the HV net class to set up in the editor before
routing (`layout_rules.py`).

⛔ GATED, three times, and nothing is written unless all three are empty:
  1. `integrity.check` -- is the netlist a circuit at all;
  2. `rules.check_all` -- does it obey its safety and pin rules;
  3. `eprj3.reader.compare` -- read back every sheet about to be written and
     derive its nets from the BYTES, then compare them pin by pin with the
     netlist. This is the emitter checking its own output on every run, not
     only in the test suite.
A failure exits non-zero naming every problem: a project that looks finished
and carries the wrong nets is worse than no project.

Output is DETERMINISTIC: every uuid and record id is derived, every timestamp
is `project.DEFAULT_EPOCH_MS`, and the zip carries fixed dates.  Two runs are
byte-identical, which is the only cheap way to tell a regenerated project from
a changed one.

Every record round-trips the grammar byte-exactly, and the tests re-derive
every board's nets from the emitted geometry and naming records and compare
them, net by net and pin by pin, with `netlist.current()`.  EasyEDA Pro joins
the nets as generated: a board's netlist exported from the editor is proven
against the netlist with `tools/tel_check.py`, nets and footprints.  A proof
holds only for the netlist it was taken from.

Every placed item is bound to a footprint: EasyEDA's library footprint for its
LCSC part (through ~/tools/lcsc-search), or one generated here
(`footprint_lib.generated`).  The build names any item still without one.
"""
import argparse
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import eprj2, footprint_lib, integrity, layout_rules, netlist, rules  # noqa: E402
from tools.board_params import STACK_ORDER  # noqa: E402
from tools.eprj3 import reader, schematic  # noqa: E402
from tools.eprj3.project import DEFAULT_EPOCH_MS, Project  # noqa: E402

PROJECT_NAME = "revv1-module"
DEFAULT_OUT = "build-eprj3"

#: The line every summary ends with.  Stated plainly, every run.
ACCEPTANCE_WARNING = (
    "Nets: EasyEDA Pro 3.2.149 joins them as generated (the gauge, 2026-09-18). "
    "It does not open .eprj3: open the project as .eprj2. Footprints come from "
    "EasyEDA's library; the editor refuses a netlist export while any part "
    "lacks one (listed above).")


def gate(design):
    """Every reason not to emit, as readable lines.  Empty means go."""
    problems = [f"integrity: {e}" for e in integrity.check(design)]
    problems += [f"rules: {e}" for e in rules.check_all(design)]
    return problems


def read_back(project, design):
    """Gate 3: every board's sheet, as it will be written, against the netlist."""
    problems = []
    for board in project.boards:
        for sheet in board.schematic.sheets:
            problems += reader.compare(sheet.document(), design, board.title)
    return problems


def build(design, *, naming=None, epoch_ms=DEFAULT_EPOCH_MS, library=None):
    """The project, in memory.  Returns (project, [BoardSheet, ...]).  With a
    `library` (tools/footprint_lib.py), each device carries its footprint."""
    project = Project.for_stack(PROJECT_NAME, epoch_ms=epoch_ms)
    unique_ids = schematic.project_unique_ids(design, STACK_ORDER)
    sheets = []
    for board in project.boards:
        sheet = board.schematic.sheets[0]
        sheets.append(schematic.emit_board(design, board.title, sheet,
                                           naming=naming,
                                           unique_ids=unique_ids,
                                           library=library))
    return project, sheets


def write_zip(folder, zip_path, epoch_ms=DEFAULT_EPOCH_MS):
    """Zip `folder` ITSELF, so the archive holds `<name>/<name>.eprj3`.

    Deterministic: entries sorted, a fixed date on every entry, fixed modes,
    one compression level.  Directory entries are included -- an importer
    that expects them finds them, and one that does not ignores them.
    """
    folder = Path(folder)
    stamp = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    date_time = stamp.timetuple()[:6]
    paths = sorted(folder.rglob("*"))
    with zipfile.ZipFile(zip_path, "w") as zf:
        top = zipfile.ZipInfo(folder.name + "/", date_time)
        top.external_attr = (0o40755 << 16) | 0x10
        zf.writestr(top, b"")
        for path in paths:
            name = f"{folder.name}/{path.relative_to(folder).as_posix()}"
            if path.is_dir():
                info = zipfile.ZipInfo(name + "/", date_time)
                info.external_attr = (0o40755 << 16) | 0x10
                zf.writestr(info, b"")
            else:
                info = zipfile.ZipInfo(name, date_time)
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, path.read_bytes(),
                            compress_type=zipfile.ZIP_DEFLATED,
                            compresslevel=9)
    return Path(zip_path)


def write(project, out):
    """Write the project folder and its zip under `out`; return both paths.

    A previous build of the same project is replaced, so a file the generator
    no longer writes cannot survive into the new one.  A folder of that name
    that is NOT a generated project is left alone and refused.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    root = out / project.name
    if root.exists():
        if not (root / f"{project.name}.eprj3").is_file():
            raise FileExistsError(
                f"{root} exists and is not a generated project; not "
                f"overwriting it")
        shutil.rmtree(root)
    root = project.write(out)
    zip_path = write_zip(root, out / f"{project.name}.zip", project.epoch_ms)
    return root, zip_path


def write_eprj2(root, template):
    """Wrap the written folder as `<name>.eprj2` beside it: the file EasyEDA
    Pro 3.2.149 opens.  Returns (path, None), or (None, why it was not written).

    Not writing it is not a failed build -- the folder is still the design --
    but the summary says so loudly, every run.
    """
    root = Path(root)
    template = template or eprj2.find_template()
    if template is None:
        return None, ("no template: open any project in EasyEDA Pro once so it "
                      "saves an .eprj2, or pass --template")
    try:
        return eprj2.convert(root, root.parent / f"{root.name}.eprj2",
                             template), None
    except (RuntimeError, ValueError) as exc:
        return None, str(exc)


def eprj2_line(path, why):
    if path is not None:
        return f"  open in EasyEDA Pro: {path}"
    return f"  ⚠️ NO .eprj2 WRITTEN, and EasyEDA Pro 3.2.149 cannot open the folder: {why}"


def summary(project, sheets, root, zip_path):
    lines = [f"{project.name}: {len(sheets)} boards -> {root}"]
    lines.append(f"  {'board':6} {'parts':>5} {'conns':>5} {'nets':>5} "
                 f"{'schematic':>12} {'pcb':>10}")
    for board, bs in zip(project.boards, sheets):
        sheet = board.schematic.sheets[0]
        sch = root / "sch" / board.schematic.name / f"{sheet.title}.esch2"
        pcb = root / "pcb" / f"{board.pcb.title}.epcb2"
        lines.append(
            f"  {bs.board:6} {bs.part_count:5d} {bs.connector_count:5d} "
            f"{len(bs.net_names):5d} {sch.stat().st_size:10d} B "
            f"{pcb.stat().st_size:8d} B")
    lines.append(f"  naming: {sheets[0].naming}   zip: {zip_path} "
                 f"({zip_path.stat().st_size} B)")
    bound = [r for s in sheets for r in s.footprints_bound]
    unbound = [r for s in sheets for r in s.footprints_unbound]
    lines.append(f"  footprints: {len(bound)} placed items carry one; "
                 f"{len(unbound)} do not" + (f": {' '.join(unbound)}" if unbound else ""))
    lines.append(ACCEPTANCE_WARNING)
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate the EasyEDA Pro project for the board set.")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help=f"output directory (default: {DEFAULT_OUT}/)")
    parser.add_argument("--no-footprints", action="store_true",
                        help="bind no library footprint (default: bind them "
                             "through ~/tools/lcsc-search when it is here)")
    parser.add_argument("--template",
                        help="an .eprj2 EasyEDA Pro saved, for the .eprj2 "
                             "output (default: found in the editor's folders)")
    args = parser.parse_args(argv)

    design = netlist.current()
    problems = gate(design)
    if problems:
        print(f"REFUSED: {len(problems)} problem(s); nothing was written.",
              file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1

    library = None if args.no_footprints else footprint_lib.open_library()
    project, sheets = build(design, library=library)
    problems = read_back(project, design)
    if problems:
        print(f"REFUSED: the emitted sheets do not carry the netlist -- "
              f"{len(problems)} problem(s); nothing was written.", file=sys.stderr)
        for p in problems:
            print(f"  read-back: {p}", file=sys.stderr)
        return 1
    root, zip_path = write(project, args.out)
    print(summary(project, sheets, root, zip_path))
    print(eprj2_line(*write_eprj2(root, args.template)))
    # The HV clearance the PCB documents cannot carry: set it up before routing.
    rules_path = Path(args.out) / "layout-rules.txt"
    rules_path.write_text(layout_rules.text(design) + "\n", encoding="utf-8")
    print(f"  layout rules to set up in the editor before routing: {rules_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
