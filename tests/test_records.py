"""The record grammar, checked by reading back what was written.

    file    := record ( "|" LF record )*
    record  := header_json "||" payload_json        (payload may be EMPTY)

⛔ The editor drops a record it cannot parse and says nothing, so "the string
looks right" is not a test. `reference_parse` below is written from the grammar
alone -- it shares no code with `records.py` -- and behaves as the editor does:
split on `"|" + LF`, cut each record at its FIRST `||`, strict-JSON-parse both
halves, and DROP whatever fails. A document passes when everything that went in
comes back out and nothing was dropped.
"""
import json

import pytest

from tools.eprj3.records import join_records, serialize_record


def _strict(constant):
    raise ValueError(f"JSON.parse rejects {constant}")


def reference_parse(text):
    """-> (parsed [(header, payload-or-None)], dropped [raw record])."""
    parsed, dropped = [], []
    if text == "":
        return parsed, dropped
    for raw in text.split("|\n"):
        head, _, payload = raw.partition("||")
        try:
            header = json.loads(head, parse_constant=_strict)
            if not isinstance(header, dict) or "type" not in header:
                raise ValueError("nothing to dispatch on")
            body = (None if payload == ""
                    else json.loads(payload, parse_constant=_strict))
        except ValueError:
            dropped.append(raw)
            continue
        parsed.append((header, body))
    return parsed, dropped


#: Every shape the emitter may be asked for: no ticket, an empty payload in
#: the MIDDLE and at the END, non-ASCII text, and payload text carrying both
#: separators (legal: the editor cuts at the FIRST `||`, and JSON escapes LF).
RECORDS = [
    ({"type": "DOCHEAD"}, {"docType": "SCH", "user": {}}),
    ({"type": "META", "ticket": 1, "id": "META"}, {"title": "原理图 Ω µF"}),
    ({"type": "ATTR", "ticket": 2, "id": "e1"}, None),
    ({"type": "TEXT", "ticket": 3, "id": "e2"},
     {"text": "a||b|\nc", "nested": {"x": [1, 2.5, None, True]}}),
    ({"type": "ATTR", "ticket": 4, "id": "e3"}, {"key": "NET", "value": "BL"}),
    ({"type": "ATTR", "ticket": 5, "id": "e4"}, None),
]


# --- one record -------------------------------------------------------------
def test_a_record_is_header_double_pipe_payload_and_nothing_else():
    out = serialize_record({"type": "DOCHEAD"}, {"docType": "SCH"})
    assert out == '{"type":"DOCHEAD"}||{"docType":"SCH"}'


def test_an_empty_payload_is_written_as_nothing_after_the_double_pipe():
    assert serialize_record({"type": "ATTR", "id": "x"}, None) == \
        '{"type":"ATTR","id":"x"}||'


def test_an_empty_object_payload_is_not_the_empty_payload():
    assert serialize_record({"type": "META"}, {}) == '{"type":"META"}||{}'


def test_the_payload_has_no_default():
    # An empty payload is most likely a deletion tombstone in the editor's own
    # files, so it must be asked for, never fallen into.
    with pytest.raises(TypeError):
        serialize_record({"type": "META"})


def test_json_is_compact():
    out = serialize_record({"type": "HEAD", "ticket": 1},
                           {"editorVersion": "4.7.8", "importFlag": 0})
    assert ", " not in out
    assert '": ' not in out


def test_non_ascii_text_is_written_unescaped():
    out = serialize_record({"type": "TEXT"}, {"text": "原理图"})
    assert "原理图" in out
    assert "\\u" not in out


# --- what the editor would drop in silence is refused out loud ---------------
def test_a_header_containing_the_double_pipe_is_refused():
    with pytest.raises(ValueError, match=r"\|\|"):
        serialize_record({"type": "ATTR", "id": "a||b"}, {"v": 1})


def test_the_double_pipe_guard_is_not_vacuous():
    # The same id, unguarded, really is cut in the wrong place and dropped.
    raw = '{"type":"ATTR","id":"a||b"}||{"v":1}'
    parsed, dropped = reference_parse(raw)
    assert parsed == [] and dropped == [raw]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nan_and_infinity_are_refused_in_either_half(bad):
    with pytest.raises(ValueError):
        serialize_record({"type": "COMPONENT"}, {"height": bad})
    with pytest.raises(ValueError):
        serialize_record({"type": "COMPONENT", "ticket": bad}, {})


@pytest.mark.parametrize("header", [
    ["DOCTYPE", "SCH", "1.0"],      # a V2 array record: no `.type` to read
    {"ticket": 1, "id": "e1"},      # an object, but nothing to dispatch on
    {"type": 7},
    "DOCHEAD",
    None,
])
def test_a_header_the_editor_cannot_dispatch_on_is_refused(header):
    with pytest.raises(TypeError):
        serialize_record(header, {})


@pytest.mark.parametrize("payload", [["a"], "text", 3, ""])
def test_a_payload_is_an_object_or_none(payload):
    with pytest.raises(TypeError):
        serialize_record({"type": "META"}, payload)


# --- the document -----------------------------------------------------------
def test_the_separator_sits_between_records_only():
    text = join_records([serialize_record(h, p) for h, p in RECORDS[:2]])
    assert text == ('{"type":"DOCHEAD"}||{"docType":"SCH","user":{}}|\n'
                    '{"type":"META","ticket":1,"id":"META"}||'
                    '{"title":"原理图 Ω µF"}')
    assert not text.endswith("\n")


def test_joining_nothing_is_the_empty_document():
    assert join_records([]) == ""


def test_a_single_record_carries_no_separator():
    one = serialize_record({"type": "DOCHEAD"}, {"docType": "PCB"})
    assert join_records([one]) == one


@pytest.mark.parametrize("stale", [
    '{"type":"META"}||{}|',          # a record carrying its own separator
    '{"type":"META"}',               # no `||` at all
    '["META",{}]',                   # a V2 array line
    '{"type":"A"}||{}|\n{"type":"B"}||{}',   # two records passed as one
])
def test_join_refuses_anything_serialize_record_would_not_return(stale):
    with pytest.raises(ValueError):
        join_records([serialize_record({"type": "DOCHEAD"}, {}), stale])


def test_round_trip_every_record_comes_back_and_none_is_dropped():
    text = join_records(serialize_record(h, p) for h, p in RECORDS)
    parsed, dropped = reference_parse(text)
    assert dropped == []
    assert parsed == RECORDS


@pytest.mark.parametrize("n", range(1, len(RECORDS) + 1))
def test_round_trip_holds_whichever_record_is_last(n):
    # The last record is the one a misplaced separator destroys, and an empty
    # payload in last position ends the file on `||` -- both are exercised.
    parsed, dropped = reference_parse(
        join_records(serialize_record(h, p) for h, p in RECORDS[:n]))
    assert (parsed, dropped) == (RECORDS[:n], [])


def test_the_reference_parser_does_catch_a_trailing_separator():
    # CONTROL. A document whose every record ends in `|`, joined on LF, is
    # what a separator placed INSIDE the record produces. The reference parser
    # must lose the last record, or the two round-trip tests above prove
    # nothing.
    wrong = "\n".join(serialize_record(h, p) + "|" for h, p in RECORDS[:2])
    parsed, dropped = reference_parse(wrong)
    assert [h["type"] for h, _ in parsed] == ["DOCHEAD"]
    assert len(dropped) == 1 and dropped[0].startswith('{"type":"META"')
