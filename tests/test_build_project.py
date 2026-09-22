"""`tools/build_project.py`: gated, complete, deterministic.

A project generated from a netlist that is not a circuit would look finished
and be wrong, so the gate is tested with a design broken each way it can be:
structurally (integrity) and by rule.  The output is then checked as files on
disk -- the same bytes the owner will open -- not as objects in memory.
"""
import json
import zipfile
from pathlib import Path

import pytest

from tools import build_project, netlist, rules
from tools.board_params import STACK_ORDER
from tools.eprj3 import schematic
from tests.test_schematic import (derive_nets, documents, netlist_slice,
                                  parse_records, read_sheet, reserialise)

DESIGN = netlist.current()
NAME = build_project.PROJECT_NAME
bp = build_project

#: What `main()` returns in THIS suite.  `conftest.py` sets REVV1_NO_LIBRARY, so
#: no library footprint is bound and every build here is INCOMPLETE by its own
#: account (see `test_no_library_is_incomplete_and_names_the_unbound`).  Every
#: project file is still written, which is what the tests below read.  0 would
#: mean a library was reached, and the suite would no longer be hermetic.
HERMETIC = bp.EXIT_INCOMPLETE


def run(out, *extra):
    """A build into `out`, asserting the hermetic exit code; returns `out`."""
    code = bp.main(["--out", str(out), *extra])
    assert code == HERMETIC, code
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return run(tmp_path_factory.mktemp("build"))


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


# --- the gate ---------------------------------------------------------------
def test_refuses_an_integrity_failure(monkeypatch, tmp_path, capsys):
    broken = DESIGN.without_pin("R110", "1")      # a floating leg
    monkeypatch.setattr(netlist, "current", lambda: broken)
    assert build_project.main(["--out", str(tmp_path)]) == bp.EXIT_REFUSED
    err = capsys.readouterr().err
    assert "REFUSED" in err and "integrity: floating: R110.1" in err
    assert list(tmp_path.iterdir()) == []         # nothing written


def test_refuses_a_rule_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rules, "check_all",
                        lambda d: ["D99: a deliberately failing rule"])
    assert build_project.main(["--out", str(tmp_path)]) == bp.EXIT_REFUSED
    err = capsys.readouterr().err
    assert "rules: D99: a deliberately failing rule" in err
    assert list(tmp_path.iterdir()) == []


# --- a refused build marks the previous one stale (M17) -------------------------
def _refuse_next_build(monkeypatch):
    monkeypatch.setattr(rules, "check_all",
                        lambda d: ["D99: a deliberately failing rule"])


def _names(out):
    return sorted(p.name for p in Path(out).iterdir())


def test_a_refused_build_renames_the_previous_project_stale(tmp_path, monkeypatch, capsys):
    """A good build, then a refusal into the same directory: the old .eprj2
    must not be there to open as current.  Every artefact is renamed, not only
    the .eprj2 -- the folder and zip are its sources and the layout rules its
    derivation, and any of them read as 'the current build' otherwise.

    The .eprj2 lives in the EDITOR's folder (2026-09-22), not under --out, so
    it is checked there; the folder, zip and rules under --out as before."""
    run(tmp_path)
    editor = bp.EDITOR_PROJECTS / f"{NAME}.eprj2"
    before = _names(tmp_path)
    assert NAME in before and "layout-rules.txt" in before and f"{NAME}.zip" in before
    assert editor.is_file() and bp._is_generated(editor)
    _refuse_next_build(monkeypatch)
    assert bp.main(["--out", str(tmp_path)]) == bp.EXIT_REFUSED
    after = _names(tmp_path)
    assert after == sorted(n + bp.STALE_SUFFIX for n in before)
    assert not editor.exists(), "a GENERATED .eprj2 in the editor folder is renamed stale too"
    assert editor.with_name(editor.name + bp.STALE_SUFFIX).is_file()
    assert (tmp_path / f"{NAME}{bp.STALE_SUFFIX}" / f"{NAME}.eprj3").is_file()
    err = capsys.readouterr().err
    assert f"renamed {bp.STALE_SUFFIX}" in err and f"{NAME}.eprj2" in err


def test_a_refused_build_leaves_a_saved_layout_alone(tmp_path, monkeypatch, capsys):
    """The one case that matters most: the editor folder holds the owner's
    SAVED layout (real timestamps, not the build's fixed one). A refused
    netlist is no reason to touch it. Nothing renames it, nothing overwrites
    it, and the summary says why the .eprj2 was not written."""
    run(tmp_path)
    editor = bp.EDITOR_PROJECTS / f"{NAME}.eprj2"
    # make it look saved: the editor re-stamps documents with the wall clock
    monkeypatch.setattr(bp, "_is_generated", lambda path: False)
    marker = editor.read_bytes()
    _refuse_next_build(monkeypatch)
    assert bp.main(["--out", str(tmp_path)]) == bp.EXIT_REFUSED
    assert editor.is_file() and editor.read_bytes() == marker, "the saved layout is untouched"
    assert not editor.with_name(editor.name + bp.STALE_SUFFIX).exists()


def test_a_second_refusal_has_nothing_left_to_rename(tmp_path, monkeypatch):
    run(tmp_path)
    _refuse_next_build(monkeypatch)
    assert bp.main(["--out", str(tmp_path)]) == bp.EXIT_REFUSED
    stale = _names(tmp_path)
    assert bp.main(["--out", str(tmp_path)]) == bp.EXIT_REFUSED
    assert _names(tmp_path) == stale


def test_mark_stale_replaces_an_earlier_stale_copy(tmp_path):
    """`main` never leaves a current build beside a .stale one, so this is
    the helper's own contract: the newer artefact wins the .stale name."""
    (tmp_path / f"{NAME}.eprj2").write_bytes(b"newer")
    (tmp_path / f"{NAME}.eprj2{bp.STALE_SUFFIX}").write_bytes(b"older")
    (tmp_path / NAME).mkdir()
    (tmp_path / NAME / f"{NAME}.eprj3").write_text("{}")
    (tmp_path / f"{NAME}{bp.STALE_SUFFIX}").mkdir()
    (tmp_path / f"{NAME}{bp.STALE_SUFFIX}" / "old.txt").write_text("older")
    renamed = bp.mark_stale(tmp_path)
    assert sorted(p.name for p in renamed) == sorted(
        [f"{NAME}.eprj2{bp.STALE_SUFFIX}", f"{NAME}{bp.STALE_SUFFIX}"])
    assert (tmp_path / f"{NAME}.eprj2{bp.STALE_SUFFIX}").read_bytes() == b"newer"
    assert (tmp_path / f"{NAME}{bp.STALE_SUFFIX}" / f"{NAME}.eprj3").is_file()
    assert not (tmp_path / f"{NAME}{bp.STALE_SUFFIX}" / "old.txt").exists()
    assert not (tmp_path / f"{NAME}.eprj2").exists() and not (tmp_path / NAME).exists()


def test_a_build_that_writes_removes_the_stale_remains(tmp_path, monkeypatch):
    """After a refusal, the next build that writes leaves the directory
    holding the current build alone -- current or marked, never both."""
    run(tmp_path)
    with monkeypatch.context() as m:
        _refuse_next_build(m)
        assert bp.main(["--out", str(tmp_path)]) == bp.EXIT_REFUSED
    assert any(n.endswith(bp.STALE_SUFFIX) for n in _names(tmp_path))
    run(tmp_path)
    assert not any(n.endswith(bp.STALE_SUFFIX) for n in _names(tmp_path))
    assert (tmp_path / f"{NAME}.zip").is_file()


def test_a_refusal_leaves_a_folder_it_did_not_write_alone(tmp_path, monkeypatch):
    (tmp_path / NAME).mkdir()
    (tmp_path / NAME / "notes.txt").write_text("mine", encoding="utf-8")
    _refuse_next_build(monkeypatch)
    assert bp.main(["--out", str(tmp_path)]) == bp.EXIT_REFUSED
    assert (tmp_path / NAME / "notes.txt").read_text() == "mine"
    assert _names(tmp_path) == [NAME]


def test_a_refusal_into_a_directory_that_does_not_exist_creates_nothing(tmp_path, monkeypatch):
    _refuse_next_build(monkeypatch)
    out = tmp_path / "never"
    assert bp.main(["--out", str(out)]) == bp.EXIT_REFUSED
    assert not out.exists()


# --- the exit code is a completeness gate (M17) ------------------------------------
def _every_item_bound(monkeypatch):
    """The real build, with every unbound item reported as bound: the suite
    cannot reach a library, so the binding is taken as reported and the exit
    code's own logic is what is under test."""
    real = bp.build

    def all_bound(design, **kw):
        project, sheets = real(design, **kw)
        for s in sheets:
            s.footprints_bound += s.footprints_unbound
            s.footprints_unbound.clear()
        return project, sheets

    monkeypatch.setattr(bp, "build", all_bound)


def test_no_library_is_incomplete_and_names_the_unbound(tmp_path, capsys):
    """The suite's own state: REVV1_NO_LIBRARY, so every LCSC-coded item is
    unbound.  That build is INCOMPLETE -- written, named, exit 2, never 0."""
    assert bp.main(["--out", str(tmp_path)]) == bp.EXIT_INCOMPLETE
    out, err = capsys.readouterr()
    assert "INCOMPLETE" in err and "carry no footprint" in err
    q301 = next(p for p in DESIGN.parts if p.refdes == "Q301")
    assert q301.lcsc, "Q301 is an LCSC-coded part, so it is unbound here"
    assert "Q301" in out.split("footprints:")[1].split("\n")[0]
    assert (tmp_path / NAME / f"{NAME}.eprj3").is_file(), "still written"


def test_a_complete_build_exits_zero(tmp_path, monkeypatch, capsys):
    """Every item bound and the .eprj2 written: 0.  The suite cannot reach a
    library, so the binding is taken as reported; the .eprj2 step is
    stubbed so the exit code does not hang on this machine's editor."""
    _every_item_bound(monkeypatch)
    monkeypatch.setattr(bp, "write_eprj2",
                        lambda root, template: (tmp_path / f"{NAME}.eprj2", None))
    assert bp.main(["--out", str(tmp_path)]) == 0
    out, err = capsys.readouterr()
    assert "INCOMPLETE" not in err and "0 do not" in out


def test_no_eprj2_alone_is_incomplete(tmp_path, monkeypatch, capsys):
    _every_item_bound(monkeypatch)
    monkeypatch.setattr(bp, "write_eprj2", lambda root, template: (None, "no template"))
    assert bp.main(["--out", str(tmp_path)]) == bp.EXIT_INCOMPLETE
    out, err = capsys.readouterr()
    assert "no .eprj2 was written" in err and "carry no footprint" not in err
    assert "NO .eprj2 WRITTEN" in out
    assert (tmp_path / f"{NAME}.zip").is_file(), "the folder and zip are still written"


def test_the_exit_codes_are_distinct_and_non_zero():
    assert bp.EXIT_REFUSED != bp.EXIT_INCOMPLETE
    assert bp.EXIT_REFUSED and bp.EXIT_INCOMPLETE


def test_incomplete_names_each_missing_thing():
    assert bp.incomplete([], True) == 0
    assert bp.incomplete(["D308"], True) == bp.EXIT_INCOMPLETE
    assert bp.incomplete([], False) == bp.EXIT_INCOMPLETE
    assert bp.incomplete(["D308"], False) == bp.EXIT_INCOMPLETE


def test_the_real_design_passes_the_gate():
    assert build_project.gate(DESIGN) == []


# --- the tree ---------------------------------------------------------------
def test_tree_is_one_board_per_stack_layer(built):
    files = sorted(tree(built / NAME))
    expected = [f"{NAME}.eprj3"]
    for b in STACK_ORDER:
        expected += [f"pcb/{b}.epcb2", f"sch/{b}/{b}.ecfg", f"sch/{b}/P1.esch2"]
    assert files == sorted(expected)


def test_index_binds_every_sheet_schematic_and_pcb(built):
    root = built / NAME
    index = json.loads((root / f"{NAME}.eprj3").read_text(encoding="utf-8"))
    profile = index["profile"]
    assert [b["title"] for b in sorted(profile["boards"].values(),
                                       key=lambda b: b["zIndex"])] \
        == list(STACK_ORDER)
    for key, sheet in profile["sheets"].items():
        schem = profile["schematics"][sheet["schematic_uuid"]]
        text = (root / "sch" / schem["name"] / f"{sheet['title']}.esch2") \
            .read_text(encoding="utf-8")
        page = documents(parse_records(text))[-1]
        assert page["docType"] == "SCH_PAGE" and page["uuid"] == key
        meta = page["records"][0][1]
        assert meta["schematic"] == sheet["schematic_uuid"]
        assert meta["title"] == sheet["title"]
    for pcb in profile["pcbs"].values():
        assert pcb["board"] in profile["boards"]


@pytest.mark.parametrize("board", STACK_ORDER)
def test_each_boards_sheet_carries_exactly_its_nets(built, board):
    text = (built / NAME / "sch" / board / "P1.esch2").read_text(
        encoding="utf-8")
    derived = derive_nets(text)
    assert derived.conflicts == [] and derived.unnamed == []
    assert derived.nets == netlist_slice(DESIGN, board)


def test_every_document_on_disk_round_trips(built):
    for rel, data in tree(built / NAME).items():
        if rel.endswith(".eprj3"):
            continue
        text = data.decode("utf-8")
        assert reserialise(parse_records(text)) == text, rel


def test_unique_ids_are_unique_across_the_whole_project(built):
    seen = {}
    for board in STACK_ORDER:
        sheet = read_sheet((built / NAME / "sch" / board / "P1.esch2")
                           .read_text(encoding="utf-8"))
        for cid in sheet.components:
            uid = sheet.attr(cid, "Unique ID")
            if uid is None:
                continue                          # net flags carry none
            ref = sheet.attr(cid, "Designator")
            assert uid not in seen, (uid, ref, seen.get(uid))
            seen[uid] = ref
    assert len(seen) == len(DESIGN.parts) + len(DESIGN.connectors)


def test_no_two_sheets_share_a_library_uuid(built):
    owners = {}
    for board in STACK_ORDER:
        text = (built / NAME / "sch" / board / "P1.esch2").read_text(
            encoding="utf-8")
        for d in documents(parse_records(text)):
            if d["docType"] in ("SYMBOL", "DEVICE"):
                assert d["uuid"] not in owners, (d["uuid"], board)
                owners[d["uuid"]] = board


def test_pcb_is_the_pcb_module_output(built):
    project, _ = build_project.build(DESIGN)
    for board in project.boards:
        on_disk = (built / NAME / "pcb" / f"{board.pcb.title}.epcb2") \
            .read_text(encoding="utf-8")
        assert on_disk == board.pcb.document()


def test_every_pcb_in_the_project_is_four_layer(built):
    """Owner, 2026-09-18: all PCBs are 4-layer."""
    for board in STACK_ORDER:
        text = (built / NAME / "pcb" / f"{board}.epcb2").read_text(encoding="utf-8")
        copper = set()
        for line in text.split("|\n"):
            head, _, body = line.partition("||")
            if json.loads(head)["type"] == "LAYER":
                b = json.loads(body)
                if b["use"] and b["layerType"] in ("TOP", "BOTTOM", "SIGNAL", "PLANE"):
                    copper.add(b["layerId"])
        assert copper == {1, 2, 15, 16}, board


# --- the zip ----------------------------------------------------------------
def test_zip_holds_the_folder_itself(built):
    with zipfile.ZipFile(built / f"{NAME}.zip") as zf:
        names = zf.namelist()
        assert f"{NAME}/{NAME}.eprj3" in names
        assert all(n.startswith(f"{NAME}/") for n in names)
        files = {n[len(NAME) + 1:]: zf.read(n) for n in names
                 if not n.endswith("/")}
    assert files == tree(built / NAME)


# --- determinism ------------------------------------------------------------
def test_two_runs_are_byte_identical(built, tmp_path):
    run(tmp_path)
    assert tree(tmp_path) == tree(built)


def test_a_rebuild_replaces_stale_files(tmp_path):
    run(tmp_path)
    stale = tmp_path / NAME / "sch" / "POWER" / "P9.esch2"
    stale.write_text("left over", encoding="utf-8")
    run(tmp_path)
    assert not stale.exists()


def test_refuses_to_clobber_a_folder_it_did_not_write(tmp_path):
    (tmp_path / NAME).mkdir()
    (tmp_path / NAME / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_project.main(["--out", str(tmp_path)])
    assert (tmp_path / NAME / "notes.txt").read_text() == "mine"


# --- the summary ------------------------------------------------------------
def test_summary_names_every_board_and_warns(tmp_path, capsys):
    run(tmp_path)
    out = capsys.readouterr().out
    for board in STACK_ORDER:
        assert f"\n  {board}" in out
    assert build_project.ACCEPTANCE_WARNING in out
    assert "gauge" in out


def test_default_naming_is_both():
    assert schematic.NAMING == "both"


# --- gate 3: the build reads back what it is about to write ---------------------
def test_the_real_build_reads_back_clean():
    project, _sheets = bp.build(netlist.current())
    assert bp.read_back(project, netlist.current()) == []


def _rename_one_ground_flag(records):
    """Corrupt ONE net flag's Global Net Name: GND -> GNDX. The netlist and the
    rules are untouched, so only reading the bytes back can catch it."""
    out, done = [], False
    for rec in records:
        head, sep, payload = rec.partition("||")
        if not done and payload:
            body = json.loads(payload)
            if body.get("key") == "Global Net Name" and body.get("value") == "GND":
                body["value"] = "GNDX"
                rec = head + sep + json.dumps(body, ensure_ascii=False,
                                              separators=(",", ":"))
                done = True
        out.append(rec)
    assert done, "fixture found no GND flag to corrupt"
    return tuple(out)


def test_the_build_refuses_sheets_that_do_not_carry_the_netlist(tmp_path, monkeypatch, capsys):
    real = bp.schematic.emit_board

    def corrupt(design, board, sheet, **kw):
        out = real(design, board, sheet, **kw)
        if board == "OUTPUTS":
            sheet.page_records = _rename_one_ground_flag(sheet.page_records)
        return out

    monkeypatch.setattr(bp.schematic, "emit_board", corrupt)
    code = bp.main(["--out", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == bp.EXIT_REFUSED
    assert "read-back" in err and "OUTPUTS" in err
    assert not any(tmp_path.iterdir()), "nothing may be written when read-back fails"


# --- the .eprj2 lives in the editor's folder, and a SAVED one is never overwritten -----------
# Owner, 2026-09-22: "all easyeda files should be in ~/Documents/EasyEDA-Pro/projects". The
# build writes its generated .eprj2 there. But once the owner has imported, placed and SAVED,
# that same path holds the layout -- and a generated project written over it would erase every
# placement. The build tells the two apart by the fixed updateTime the emitter stamps on every
# document (eprj2._head): a saved project carries the editor's real clock instead.

def _fake_eprj2(tmp_path, monkeypatch, stamps):
    """A stand-in .eprj2 whose DOCHEADs carry `stamps`, read through a patched eprj2.read."""
    target = tmp_path / "projects" / "revv1-module.eprj2"
    target.parent.mkdir()
    target.write_bytes(b"x")
    text = "".join(f'{{"type":"DOCHEAD"}}||{{"docType":"PCB","updateTime":{s}}}\n' for s in stamps)
    monkeypatch.setattr(build_project.eprj2, "read", lambda p: {"text": text})
    monkeypatch.setattr(build_project, "EDITOR_PROJECTS", target.parent)
    return target


def test_a_generated_eprj2_in_the_editor_folder_is_replaceable(tmp_path, monkeypatch):
    """Every DOCHEAD carries the build's fixed stamp: this is a build output."""
    t = _fake_eprj2(tmp_path, monkeypatch, [build_project.GENERATED_STAMP] * 3)
    assert build_project._is_generated(t)


def test_a_saved_eprj2_in_the_editor_folder_is_precious(tmp_path, monkeypatch):
    """One document the editor has re-stamped is enough: the file holds the owner's work."""
    t = _fake_eprj2(tmp_path, monkeypatch,
                    [build_project.GENERATED_STAMP, "1790100000000", build_project.GENERATED_STAMP])
    assert not build_project._is_generated(t)


def test_an_unreadable_eprj2_is_treated_as_precious(tmp_path, monkeypatch):
    """If the build cannot read it, it must not assume it may overwrite it."""
    t = _fake_eprj2(tmp_path, monkeypatch, [build_project.GENERATED_STAMP])
    monkeypatch.setattr(build_project.eprj2, "read", lambda p: (_ for _ in ()).throw(RuntimeError("no keys")))
    assert not build_project._is_generated(t)


def test_write_eprj2_refuses_to_overwrite_a_saved_layout(tmp_path, monkeypatch):
    """The whole point: a saved project in the editor folder stops the build cold, with the
    reason and the way forward (Import Changes, not regeneration) in the message."""
    t = _fake_eprj2(tmp_path, monkeypatch, ["1790100000000"])
    monkeypatch.setattr(build_project.eprj2, "convert",
                        lambda *a, **k: pytest.fail("convert must not be reached"))
    root = tmp_path / "revv1-module"; root.mkdir()
    path, why = build_project.write_eprj2(root, template=tmp_path / "t.eprj2")
    assert path is None
    assert "SAVED layout" in why and "refusing to overwrite" in why
    assert "Import Changes" in why


def test_write_eprj2_replaces_a_generated_project(tmp_path, monkeypatch):
    """And the mirror: a generated one is replaced, and convert IS reached with the editor path."""
    t = _fake_eprj2(tmp_path, monkeypatch, [build_project.GENERATED_STAMP] * 2)
    seen = {}
    monkeypatch.setattr(build_project.eprj2, "convert",
                        lambda root, out, tpl: seen.setdefault("out", out) or out)
    root = tmp_path / "revv1-module"; root.mkdir()
    path, why = build_project.write_eprj2(root, template=tmp_path / "t.eprj2")
    assert why is None and seen["out"] == t
