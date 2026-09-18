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


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("build")
    assert build_project.main(["--out", str(out)]) == 0
    return out


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


# --- the gate ---------------------------------------------------------------
def test_refuses_an_integrity_failure(monkeypatch, tmp_path, capsys):
    broken = DESIGN.without_pin("R110", "1")      # a floating leg
    monkeypatch.setattr(netlist, "current", lambda: broken)
    assert build_project.main(["--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "REFUSED" in err and "integrity: floating: R110.1" in err
    assert list(tmp_path.iterdir()) == []         # nothing written


def test_refuses_a_rule_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rules, "check_all",
                        lambda d: ["D99: a deliberately failing rule"])
    assert build_project.main(["--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "rules: D99: a deliberately failing rule" in err
    assert list(tmp_path.iterdir()) == []


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
    assert build_project.main(["--out", str(tmp_path)]) == 0
    assert tree(tmp_path) == tree(built)


def test_a_rebuild_replaces_stale_files(tmp_path):
    assert build_project.main(["--out", str(tmp_path)]) == 0
    stale = tmp_path / NAME / "sch" / "HVIN" / "P9.esch2"
    stale.write_text("left over", encoding="utf-8")
    assert build_project.main(["--out", str(tmp_path)]) == 0
    assert not stale.exists()


def test_refuses_to_clobber_a_folder_it_did_not_write(tmp_path):
    (tmp_path / NAME).mkdir()
    (tmp_path / NAME / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_project.main(["--out", str(tmp_path)])
    assert (tmp_path / NAME / "notes.txt").read_text() == "mine"


# --- the summary ------------------------------------------------------------
def test_summary_names_every_board_and_warns(tmp_path, capsys):
    assert build_project.main(["--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    for board in STACK_ORDER:
        assert f"\n  {board}" in out
    assert build_project.ACCEPTANCE_WARNING in out
    assert "gauge" in out


def test_default_naming_is_both():
    assert schematic.NAMING == "both"


# --- gate 3: the build reads back what it is about to write ---------------------
bp = build_project


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
        if board == "DRV":
            sheet.page_records = _rename_one_ground_flag(sheet.page_records)
        return out

    monkeypatch.setattr(bp.schematic, "emit_board", corrupt)
    code = bp.main(["--out", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 1
    assert "read-back" in err and "DRV" in err
    assert not any(tmp_path.iterdir()), "nothing may be written when read-back fails"
