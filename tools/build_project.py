#!/usr/bin/env python3
"""Generate the EasyEDA Pro project for the three-board set.

    python3 tools/build_project.py [--out DIR] [--keep-saved-layout]
                                                        (default: build-eprj3/)

Writes `<out>/revv1-module/`, an `.eprj3` folder project with one board per
`board_params.STACK_ORDER` layer -- POWER, OUTPUTS, LOGIC -- each with:

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
A failure exits `EXIT_REFUSED` (1) naming every problem, and renames the
previous build's artefacts under `--out` to `<name>.stale`, so the project
left in the directory can never be mistaken for one built from the current
netlist: a project that looks finished and carries the wrong nets is worse
than no project.

The exit code is a COMPLETENESS gate, not only a refusal:
  0                  every placed item carries a footprint and the .eprj2 the
                     editor opens was written -- or, with `--keep-saved-layout`,
                     the one there is the owner's saved layout and was left
                     untouched;
  EXIT_REFUSED   (1) a gate failed; nothing new was written; the previous
                     build is renamed .stale;
  EXIT_INCOMPLETE (2) the project was written but cannot yet be laid out: a
                     placed item has no footprint (the editor refuses a
                     netlist export while one is missing), or no .eprj2 was
                     written (no `cryptography`, or no editor template). The
                     summary names each one. Everything that COULD be
                     written is on disk, so the folder can still be read.

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
import re
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
#: Where EasyEDA Pro keeps its projects, and the ONE place an .eprj2 of this
#: design lives (owner, 2026-09-22: "all easyeda files should be in
#: ~/Documents/EasyEDA-Pro/projects"). The build writes the generated .eprj2
#: there -- unless one is already there that the editor has SAVED, which is the
#: owner's layout and must never be overwritten by a generated one.
EDITOR_PROJECTS = Path.home() / "Documents" / "EasyEDA-Pro" / "projects"

#: A gate refused the netlist: nothing new on disk, the old build marked stale.
EXIT_REFUSED = 1
#: Written, but not a project the editor can lay out yet -- an item without a
#: footprint, or no .eprj2.  Distinct from EXIT_REFUSED so a caller can tell
#: "the netlist is wrong" from "this machine lacks a library or a template".
EXIT_INCOMPLETE = 2
#: What a refused build renames the previous build's artefacts with.
STALE_SUFFIX = ".stale"

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


def artefacts(out, name=PROJECT_NAME):
    """Every path a build of `name` writes under `out`, whether or not it is
    there: the folder, its zip, the .eprj2 and the layout rules.  A folder of
    that name that is NOT a generated project is not in the list -- the build
    never touches one (see `write`)."""
    out = Path(out)
    paths = [out / f"{name}.eprj2", out / f"{name}.zip", out / "layout-rules.txt"]
    root = out / name
    if not root.is_dir() or (root / f"{name}.eprj3").is_file():
        paths.append(root)
    return paths


def _remove(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def mark_stale(out, name=PROJECT_NAME):
    """Rename the previous build's artefacts under `out` to `<path>.stale`, so
    a REFUSED build leaves nothing that opens as the current project.  A
    `.stale` from an earlier refusal is replaced.  Returns the new paths.

    The .eprj2 in the editor's folder is marked too -- but ONLY if it is a
    generated one.  A project the editor has saved is the owner's layout: a
    refused netlist is no reason to touch it, and the build never does."""
    renamed = []
    editor = EDITOR_PROJECTS / f"{name}.eprj2"
    candidates = list(artefacts(out, name))
    if editor.exists() and _is_generated(editor):
        candidates.append(editor)
    for path in candidates:
        if not path.exists():
            continue
        stale = path.with_name(path.name + STALE_SUFFIX)
        _remove(stale)
        path.rename(stale)
        renamed.append(stale)
    return renamed


def clear_stale(out, name=PROJECT_NAME):
    """A build that writes removes the `.stale` copies a refusal left: the
    directory holds either the current build or the marked remains of the
    last one, never both.  The editor folder's `.stale` goes the same way."""
    for path in list(artefacts(out, name)) + [EDITOR_PROJECTS / f"{name}.eprj2"]:
        _remove(path.with_name(path.name + STALE_SUFFIX))


def write(project, out):
    """Write the project folder and its zip under `out`; return both paths.

    A previous build of the same project is replaced, so a file the generator
    no longer writes cannot survive into the new one, and the `.stale` remains
    of a refused build are removed.  A folder of that name that is NOT a
    generated project is left alone and refused.
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
    clear_stale(out, project.name)
    root = project.write(out)
    zip_path = write_zip(root, out / f"{project.name}.zip", project.epoch_ms)
    return root, zip_path


def write_eprj2(root, template):
    """Wrap the written folder as `<name>.eprj2` beside it: the file EasyEDA
    Pro 3.2.149 opens.  Returns (path, None), or (None, why it was not written).

    The folder is still the design when this cannot be written, so it is not
    a REFUSED build -- but the owner cannot open the result, so `main` exits
    `EXIT_INCOMPLETE` and the summary says why, every run.
    """
    root = Path(root)
    template = template or eprj2.find_template()
    if template is None:
        return None, ("no template: open any project in EasyEDA Pro once so it "
                      "saves an .eprj2, or pass --template")
    target = EDITOR_PROJECTS / f"{root.name}.eprj2"
    if target.exists() and not _is_generated(target):
        return None, (f"{target} is the owner's SAVED layout, not a generated "
                      f"project -- refusing to overwrite it. Layout absorbs a "
                      f"netlist change through Import Changes (layout/README.md), "
                      f"never by regenerating over it. --keep-saved-layout leaves it "
                      f"and counts it as the project to open")
    try:
        EDITOR_PROJECTS.mkdir(parents=True, exist_ok=True)
        return eprj2.convert(root, target, template), None
    except (RuntimeError, ValueError) as exc:
        return None, str(exc)


#: The build stamps every document it writes with this fixed timestamp
#: (`eprj2._head` / `from_eprj3`), so a project the editor has saved carries a
#: real one instead. That is how a generated .eprj2 is told from a laid-out one.
GENERATED_STAMP = "1788000000000"


def saved_layout(name=PROJECT_NAME):
    """The editor folder's `<name>.eprj2` if it is the owner's SAVED layout,
    else None.  `--keep-saved-layout` counts that file as the project to open:
    it was written from this netlist and laid out since, and a netlist change
    reaches it through Import Changes (layout/README.md), never through a
    regenerated file."""
    path = EDITOR_PROJECTS / f"{name}.eprj2"
    return path if path.exists() and not _is_generated(path) else None


def _is_generated(path) -> bool:
    """True if `path` is a build output (fixed stamp on its DOCHEADs), False if
    the editor has saved it since -- which means it holds the owner's work."""
    try:
        d = eprj2.read(path)
    except Exception:
        return False                # unreadable: treat as precious
    heads = re.findall(r'"updateTime":(\d+)', d["text"][:200000])
    return bool(heads) and all(h == GENERATED_STAMP for h in heads)


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
                             "through ~/tools/lcsc-search when it is here); "
                             f"the build then exits {EXIT_INCOMPLETE}, INCOMPLETE")
    parser.add_argument("--keep-saved-layout", action="store_true",
                        help="when the editor folder's .eprj2 is the owner's SAVED "
                             "layout, leave it untouched and exit 0 rather than "
                             f"{EXIT_INCOMPLETE}: the saved layout is the project to "
                             "open.  It never overwrites it; tools/gate.sh passes it")
    parser.add_argument("--template",
                        help="an .eprj2 EasyEDA Pro saved, for the .eprj2 "
                             "output (default: found in the editor's folders)")
    args = parser.parse_args(argv)

    design = netlist.current()
    problems = gate(design)
    if problems:
        return refuse(f"{len(problems)} problem(s)", problems, args.out)

    library = None if args.no_footprints else footprint_lib.open_library()
    project, sheets = build(design, library=library)
    problems = read_back(project, design)
    if problems:
        return refuse(f"the emitted sheets do not carry the netlist -- "
                      f"{len(problems)} problem(s)",
                      [f"read-back: {p}" for p in problems], args.out)
    root, zip_path = write(project, args.out)
    print(summary(project, sheets, root, zip_path))
    eprj2_path, why = write_eprj2(root, args.template)
    kept = saved_layout(root.name) if eprj2_path is None and args.keep_saved_layout else None
    if kept is not None:
        print(f"  the owner's saved layout is the project to open, left untouched "
              f"(--keep-saved-layout): {kept}")
    else:
        print(eprj2_line(eprj2_path, why))
    # The HV clearance the PCB documents cannot carry: set it up before routing.
    rules_path = Path(args.out) / "layout-rules.txt"
    rules_path.write_text(layout_rules.text(design) + "\n", encoding="utf-8")
    print(f"  layout rules to set up in the editor before routing: {rules_path}")

    unbound = [r for s in sheets for r in s.footprints_unbound]
    return incomplete(unbound, eprj2_path is not None or kept is not None)


def refuse(headline, problems, out):
    """Say why nothing new was written, mark the previous build stale, and
    return `EXIT_REFUSED`."""
    print(f"REFUSED: {headline}; nothing was written.", file=sys.stderr)
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    stale = mark_stale(out)
    if stale:
        print(f"  the previous build in {out} is renamed {STALE_SUFFIX}, so it "
              f"cannot be opened as current: "
              + " ".join(p.name for p in stale), file=sys.stderr)
    return EXIT_REFUSED


def incomplete(unbound, eprj2_written):
    """0 when the written project is one the editor can lay out; else
    `EXIT_INCOMPLETE`, saying on stderr what is missing.  The summary above
    has already named each unbound item."""
    missing = []
    if unbound:
        missing.append(f"{len(unbound)} placed item(s) carry no footprint "
                       f"(named above); the editor refuses a netlist export "
                       f"until every one has one")
    if not eprj2_written:
        missing.append("no .eprj2 was written, and EasyEDA Pro 3.2.149 opens "
                       "nothing else")
    if not missing:
        return 0
    print(f"INCOMPLETE: the project is written but is not one to lay out yet "
          f"-- {'; '.join(missing)}.", file=sys.stderr)
    return EXIT_INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
