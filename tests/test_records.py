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


def test_refuses_to_emit_before_the_gauge_settles_the_encoding():
    # The whole point of Task 1: guessing silently is the expensive failure.
    with pytest.raises(EncodingNotSettled):
        serialize_record(["DOCTYPE", "SCH", "1.0"])


def test_rejects_unknown_encoding():
    with pytest.raises(ValueError):
        serialize_record(["X"], encoding="klingon")


def test_object_encoding_defaults_payload_to_empty_object():
    assert serialize_record({"type": "META"}, encoding=OBJECT) == '{"type":"META"}||{}|'


def test_unicode_is_not_escaped():
    # the real example files carry CJK text unescaped
    out = serialize_record(["TEXT", "原理图"], encoding=ARRAY)
    assert "原理图" in out
