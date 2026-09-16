import pytest
from tools.eprj3.records import serialize_record, ARRAY, OBJECT, EncodingNotSettled


def test_array_encoding_is_one_json_array_per_line():
    out = serialize_record(["DOCTYPE", "SCH", "1.0"], encoding=ARRAY)
    assert out == '["DOCTYPE","SCH","1.0"]'
    assert "\n" not in out


def test_object_encoding_uses_double_pipe_and_trailing_pipe():
    out = serialize_record({"type": "DOCHEAD"}, encoding=OBJECT,
                           payload={"docType": "SCH"})
    assert out == '{"type":"DOCHEAD"}||{"docType":"SCH"}|'


def test_no_whitespace_in_emitted_json():
    out = serialize_record(["HEAD", {"editorVersion": "4.7.8", "importFlag": 0}],
                           encoding=ARRAY)
    assert ", " not in out
    assert '": ' not in out


def test_encoding_is_settled_to_v3_objects():
    # Settled from the installed editor's own parser: it JSON.parses the
    # header and reads o.type / o.id / o.ticket -- named fields on an OBJECT.
    # A V2 array has no .type and is silently dropped.
    from tools.eprj3 import records
    assert records.ENCODING == OBJECT


def test_default_encoding_now_emits_without_raising():
    out = serialize_record({"type": "DOCHEAD"}, payload={"docType": "SCH"})
    assert out == '{"type":"DOCHEAD"}||{"docType":"SCH"}|'


def test_the_guard_still_exists_for_an_unset_encoding():
    # the refusal must survive: temporarily clear it and confirm it bites
    from tools.eprj3 import records
    saved = records.ENCODING
    records.ENCODING = None
    try:
        with pytest.raises(EncodingNotSettled):
            serialize_record({"type": "X"})
    finally:
        records.ENCODING = saved


def test_rejects_unknown_encoding():
    with pytest.raises(ValueError):
        serialize_record(["X"], encoding="klingon")


def test_object_encoding_defaults_payload_to_empty_object():
    assert serialize_record({"type": "META"}, encoding=OBJECT) == '{"type":"META"}||{}|'


def test_unicode_is_not_escaped():
    # the real example files carry CJK text unescaped
    out = serialize_record(["TEXT", "原理图"], encoding=ARRAY)
    assert "原理图" in out
