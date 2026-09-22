"""Reading EasyEDA's exported netlist (.tel) and comparing it with ours.

The fixture copies the export's quirks from real files: CRLF, a trailing ','
that continues a line, a lone ',' line between records, and a quoted value
with a comma of its own.
"""
from collections import defaultdict

from tools import lcsc_fixture, netlist, tel_check
from tools.eprj3.schematic import board_refs, converted_to_pcb, landed_pins
from tools.model import Design, Net, Part

TEL = ("$PACKAGES\r\n"
       "c0805 ! c0805 ! '100nF 50V' ; C1 \r\n"
       "cap-th_bd8 ! cap-th_bd8 ! '680uF 25V polymer, 20 mΩ' ; ,\r\n"
       "        C2 C3 \r\n"
       ",\r\n"
       "        MODULE_X ! MODULE_X ! '43-160 V → 5 V' ,\r\n"
       "        ; U1 \r\n"
       "fuse-th ! fuse-th !  ; FH1 FH2 \r\n"
       "$NETS\r\n"
       "'GND' ; C1.2 C2.- ,\r\n"
       "        C3.- U1.-Vin \r\n"
       "'V5' ; C1.1 C2.+ C3.+ U1.+Vout \r\n"
       "'HOLD_IN' ; FH1.1 \r\n"
       "'HOLD' ; FH2.1 \r\n"
       "$A_PROPERTIES\r\n"
       "$END\r\n")

#: What the library says each toy part's footprint is -- every part on the
#: PCB needs one, or the comparison cannot say "identical".
FIXTURE = {"C1L": {"footprint": "c0805"}, "C2L": {"footprint": "cap-th_bd8"},
           "C3L": {"footprint": "cap-th_bd8"}, "U1L": {"footprint": "MODULE_X"},
           "FH1L": {"footprint": "fuse-th"}, "FH2L": {"footprint": "fuse-th"}}


def design(extra_nets=()):
    parts = (Part("C1", "c", "0805", "POWER", "C", ("1", "2"), 1, v_max=50, lcsc="C1L"),
             Part("C2", "c", "r", "POWER", "C", ("+", "-"), 1, v_max=25, lcsc="C2L"),
             Part("C3", "c", "r", "POWER", "C", ("+", "-"), 1, v_max=25, lcsc="C3L"),
             Part("U1", "m", "m", "POWER", "CONVERTER", ("-Vin", "+Vout"), 1, lcsc="U1L"),
             Part("FH1", "clip", "clip", "POWER", "FUSECLIP", ("1",), 1, lcsc="FH1L"),
             Part("FH2", "clip", "clip", "POWER", "FUSECLIP", ("1",), 1, lcsc="FH2L"),
             Part("F1", "fuse", "5x20", "POWER", "FUSE", ("1", "2"), 1, v_max=300))
    nets = (Net("GND", (("C1", "2"), ("C2", "-"), ("C3", "-"), ("U1", "-Vin")), "GND"),
            Net("V5", (("C1", "1"), ("C2", "+"), ("C3", "+"), ("U1", "+Vout")), "5V"),
            Net("HOLD_IN", (("FH1", "1"), ("F1", "1")), "84V"),
            Net("HOLD", (("FH2", "1"), ("F1", "2")), "84V")) + tuple(extra_nets)
    return Design(parts=parts, nets=nets)


def test_the_parser_reads_every_record_through_the_continuations():
    t = tel_check.parse(TEL)
    assert t.packages == {"C1": "c0805", "C2": "cap-th_bd8", "C3": "cap-th_bd8",
                          "U1": "MODULE_X", "FH1": "fuse-th", "FH2": "fuse-th"}
    assert t.nets["GND"] == {("C1", "2"), ("C2", "-"), ("C3", "-"), ("U1", "-Vin")}
    assert set(t.nets) == {"GND", "V5", "HOLD_IN", "HOLD"}


def test_a_matching_export_passes_with_the_fuse_expected_absent():
    """F1 is not converted to PCB: the export leaves it out, and its two nets
    stay split, as the copper will be."""
    r = tel_check.compare(design(), "POWER", tel_check.parse(TEL), FIXTURE)
    assert r.ok, r.problems
    assert r.left_off == ["F1"]
    assert (r.nets, r.pins, r.footprints) == (4, 10, 6)


def test_a_pin_on_the_wrong_net_is_reported():
    bad = TEL.replace("'V5' ; C1.1 C2.+", "'V5' ; C1.2 C2.+")
    r = tel_check.compare(design(), "POWER", tel_check.parse(bad), FIXTURE)
    assert not r.ok
    assert any("V5" in p for p in r.problems) and any("GND" in p for p in r.problems)


def test_a_missing_net_and_a_part_that_should_be_off_the_pcb_are_reported():
    with_fuse = TEL.replace("'HOLD' ; FH2.1", "'HOLD' ; FH2.1 F1.2")
    r = tel_check.compare(design(), "POWER", tel_check.parse(with_fuse), FIXTURE)
    assert not r.ok and any("F1" in p for p in r.problems)
    r = tel_check.compare(design((Net("SPARE", (("U1", "x"),), "SIGNAL"),)), "POWER",
                          tel_check.parse(TEL), FIXTURE)
    assert not r.ok and any("SPARE" in p for p in r.problems)


def test_a_wrong_footprint_is_reported_even_when_every_net_matches():
    """Pads carry pin names, so a wrong land pattern with the right names
    passes the nets (review CK-11). C1's footprint is compared too."""
    assert tel_check.compare(design(), "POWER", tel_check.parse(TEL), FIXTURE).ok
    wrong = TEL.replace("c0805 ! c0805 ! '100nF 50V' ; C1", "r0402 ! r0402 ! '100nF 50V' ; C1")
    r = tel_check.compare(design(), "POWER", tel_check.parse(wrong), FIXTURE)
    assert any("C1 has footprint r0402, the generator bound c0805" in p for p in r.problems)


def test_a_footprint_that_cannot_be_checked_is_a_problem_not_a_skip():
    """A `footprint: null` record used to drop the comparison and leave the
    verdict "identical" (H14). The export is right in every other way."""
    nulled = {**FIXTURE, "C1L": {"footprint": None}}
    r = tel_check.compare(design(), "POWER", tel_check.parse(TEL), nulled)
    assert not r.ok
    assert r.problems == ["footprint of C1 could not be checked: no footprint on record "
                          "for it (tests/fixtures/lcsc.json)"]
    assert r.footprints == 5
    # ...and a part the fixture has never heard of is the same problem:
    r = tel_check.compare(design(), "POWER", tel_check.parse(TEL),
                          {k: v for k, v in FIXTURE.items() if k != "U1L"})
    assert r.problems == ["footprint of U1 could not be checked: no footprint on record "
                          "for it (tests/fixtures/lcsc.json)"]


def test_the_fuse_left_off_the_pcb_is_not_asked_for_a_footprint():
    """F1 is never converted to PCB, so its footprint is legitimately unknown."""
    r = tel_check.compare(design(), "POWER", tel_check.parse(TEL), FIXTURE)
    assert r.ok and "F1" not in " ".join(r.problems)


# -- the real design -----------------------------------------------------------

def _export(design, board, fixture):
    """A .tel export of `board` exactly as the generator's netlist stands: the
    editor's own reading of a project built from this design."""
    refs = board_refs(design, board)
    off = {p.refdes for p in design.parts if p.refdes in refs and not converted_to_pcb(p)}
    nets = defaultdict(set)
    for (ref, pin), net in landed_pins(design).items():
        if ref in refs and ref not in off:
            nets[net].add((ref, pin))
    fps = tel_check.expected_footprints(design, board, fixture)
    packages = {r: fp for r, fp in fps.items() if r not in off}
    assert None not in packages.values(), "the real design has a footprint for every part"
    return packages, dict(nets)


def _tel_text(packages, nets):
    by_fp = defaultdict(list)
    for ref, fp in sorted(packages.items()):
        by_fp[fp].append(ref)
    lines = ["$PACKAGES"]
    lines += [f"{fp} ! {fp} !  ; {' '.join(refs)}" for fp, refs in sorted(by_fp.items())]
    lines.append("$NETS")
    lines += [f"'{name}' ; {' '.join(f'{r}.{p}' for r, p in sorted(pins))}"
              for name, pins in sorted(nets.items())]
    lines += ["$A_PROPERTIES", "$END", ""]
    return "\r\n".join(lines)


def test_a_true_export_of_every_board_is_identical_with_every_footprint_compared():
    """⚠️ Every board in the ORDER, read off `board_params` rather than typed:
    CTRL joined it at IO-26 and a typed triple would have left the newest board
    -- the one nothing has ever been exported from -- out of the one check that
    proves an export matches the netlist.

    ⚠️ The floor is per-board and it is 20, not 50: POWER shed the controller
    row to CTRL and carries 39 placed items now, and CTRL itself 22. What the
    floor is for is catching an export that came back nearly empty, and any
    number under the smallest real board does that."""
    from tools import board_params as bp
    d = netlist.current()
    fx = lcsc_fixture.load()
    assert bp.STACK_ORDER == ("POWER", "OUTPUTS", "LOGIC", "CTRL")
    for board in bp.STACK_ORDER:
        packages, nets = _export(d, board, fx)
        r = tel_check.compare(d, board, tel_check.Tel(packages, nets), fx)
        assert r.ok, (board, r.problems[:5])
        assert r.footprints == len(packages) > 20, board


def test_seventeen_smf18a_on_the_wrong_land_fail_even_with_their_record_nulled(tmp_path, capsys):
    """H14's reproduction: null the SMF18A's footprint record and export
    OUTPUTS with every one of them on the SOD-123 land instead of SOD-123FL.
    Before 2026-09-21: "identical", exit 0."""
    d = netlist.current()
    fx = lcsc_fixture.load()
    smf = sorted(p.refdes for p in d.parts if p.mpn == "SMF18A" and p.board == "OUTPUTS")
    assert len(smf) == 17 and all(d.part(r).lcsc == "C19077512" for r in smf)
    packages, nets = _export(d, "OUTPUTS", fx)
    wrong = {**packages, **{r: "sod-123_l2_7-w1_6-ls3_7-rd" for r in smf}}
    nulled = {**fx, "C19077512": {**fx["C19077512"], "footprint": None}}

    r = tel_check.compare(d, "OUTPUTS", tel_check.Tel(wrong, nets), nulled)
    assert not r.ok and len(r.problems) == 17
    assert all(p == f"footprint of {ref} could not be checked: no footprint on record "
                    f"for it (tests/fixtures/lcsc.json)" for p, ref in zip(r.problems, smf))
    # With the record intact the same export names the wrong land itself:
    r = tel_check.compare(d, "OUTPUTS", tel_check.Tel(wrong, nets), fx)
    assert len(r.problems) == 17 and all("the generator bound sod-123fl" in p for p in r.problems)

    # And through main(): the wrong-land export exits 1 and never says identical.
    path = tmp_path / "Netlist_OUTPUTS.tel"
    path.write_text(_tel_text(wrong, nets), encoding="utf-8")
    assert tel_check.main(["OUTPUTS", str(path)]) == 1
    out = capsys.readouterr().out
    assert "identical" not in out and "17 problem(s)" in out
    path.write_text(_tel_text(packages, nets), encoding="utf-8")
    assert tel_check.main(["OUTPUTS", str(path)]) == 0
    out = capsys.readouterr().out
    assert f"identical to the generator's netlist, every one of {len(packages)} footprints compared" in out
