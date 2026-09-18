"""THE ENCODING BOUNDARY -- the one place a record or a separator is formatted.

EasyEDA Pro V3 documents (`.esch2`, `.epcb2`, `.ecfg`, ...) are text:

    file    := record ( "|" LF record )*
    record  := header_json "||" payload_json
    payload_json may be EMPTY

⛔ The separator sits BETWEEN records. There is none after the last record and
no trailing newline. `serialize_record` returns one record with no separator;
`join_records` is the only place the separator exists, so a caller cannot get
the grammar wrong by joining on its own.

How the editor reads it (EasyEDA Pro 2.2.45.4, paraphrased): it splits the text
on `"|" + LF`, splits each record at its FIRST `||`, JSON-parses the header and
dispatches on the header's named fields -- `type`, `id`, `ticket`. ⚠️ A record
it cannot parse is dropped SILENTLY: the file opens, and the geometry is simply
missing. Every guard below is therefore an error here rather than a quiet hole
there:

  * the header is a JSON OBJECT with a string `type` -- a header without one
    has nothing to dispatch on;
  * the header's JSON never contains `||` -- the editor would cut it there;
  * no NaN or Infinity -- Python writes them happily and `JSON.parse` rejects
    them, which would drop the whole record;
  * compact JSON, non-ASCII text unescaped, as the editor writes it. Compact
    JSON cannot contain a raw LF, so a record can never contain the separator.

An EMPTY payload is legal (the editor writes `header||` itself). It has to be
asked for explicitly by passing `None`: nothing defaults to it.

Verified by byte-exact round trip: splitting the editor's own documents on
`"|" + LF`, parsing both halves of every record and re-joining them reproduces
the original bytes.
"""
import json

#: Between two records. Never after the last one.
RECORD_SEPARATOR = "|\n"
#: Between a record's header and its payload. The editor cuts at the FIRST one.
HEADER_SEPARATOR = "||"


def _compact(obj) -> str:
    """Compact JSON as the editor writes it; raises ValueError on NaN/Infinity."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def serialize_record(header: dict, payload: dict | None) -> str:
    """One record, `header||payload`, with NO separator on either end.

    `payload=None` writes the empty payload (`header||`).
    """
    if not isinstance(header, dict) or not isinstance(header.get("type"), str):
        raise TypeError(
            "a record header is a JSON object with a string 'type'; the "
            f"editor silently drops anything else (got {header!r})")
    if payload is not None and not isinstance(payload, dict):
        raise TypeError(
            f"a record payload is a JSON object or None (got {payload!r})")
    head = _compact(header)
    if HEADER_SEPARATOR in head:
        raise ValueError(
            "a record header must not contain '||': the editor splits the "
            f"record at the first one and drops it ({head!r})")
    return head + HEADER_SEPARATOR + ("" if payload is None else _compact(payload))


def join_records(records) -> str:
    """A document body: records joined by `"|" + LF`, nothing after the last.

    Takes records as `serialize_record` returns them. Anything else -- a
    record with no `||`, or one that carries its own trailing `|` -- would
    be dropped by the editor without a word, so it is refused here.
    """
    records = list(records)
    for record in records:
        head, sep, payload = record.partition(HEADER_SEPARATOR)
        if not (sep and head.startswith("{") and head.endswith("}")
                and (payload == "" or payload.endswith("}"))
                and RECORD_SEPARATOR not in record):
            raise ValueError(
                "not a serialised record (expected 'header||payload' exactly "
                f"as serialize_record returns it): {record[:60]!r}")
    return RECORD_SEPARATOR.join(records)
