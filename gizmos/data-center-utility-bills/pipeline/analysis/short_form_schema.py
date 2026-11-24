#!/usr/bin/env python3
"""Stage 1 of the Short Form access request: the hash check and the schema and description read, nothing else.

Authorized by Joe on 2026-11-19 (ledger entry D-111), in his words: "authorize stage 1 only of
`docs/gate1/short-form-access-request-2026-11-19.md`, for `data/raw/pudl/core_eia861__yearly_short_form.parquet`: the
specified hash check and schema/description read, with no rows, column statistics or distinct values. Bring back the
exact stage 2 request. Neither stage 2 nor the proposed exclusion rule is authorized yet."

What this module opens, and nothing else:
  1. data/frozen/fetch_manifest_eia861.json, for the file's recorded SHA-256 (a permitted frozen file);
  2. the one file SHORT_FORM_TABLE, first as bytes for its SHA-256, and then, only if the hash equals the manifest's,
     its parquet footer through DuckDB's two table functions parquet_schema and parquet_kv_metadata, each by the fixed
     query held below as a constant.
Reads NO row, NO row count, NO row-group or column statistic, NO distinct value, NO price, NO revenue and NO bill. It
never calls DuckDB's footer-statistics function (the one named parquet_metadata, which carries column statistics) and
never opens the file with pyarrow's parquet reader. There is no code path here that reads a row.

Why DuckDB for the file (the agent's choice). pyarrow 19 refused the operational table from the same fetch with
"Repetition level histogram size mismatch" (reconciliation_inputs.read_short_form, found 2026-11-19), which is an error
in parsing that file's footer, so pyarrow's footer reader may refuse this one too; the request names DuckDB's two
schema functions; and each of them returns only what it is named for, so the query itself cannot return a statistic.
pyarrow is used only to decode, in memory, the bytes of the ARROW:schema key that parquet_kv_metadata has already
returned (pyarrow.ipc.read_schema on that buffer). That decode opens no file. It is how the per-column description text
(Arrow field metadata) is reached; the raw blob is never written out.

The redaction rule (the agent's reading of "no rows, column statistics or distinct values"). Description text is
returned as found, except:
  R1  in any JSON object with "kind": "range" (pandas' RangeIndex descriptor), the keys start, stop and step are
      removed, since stop minus start is the row count;
  R2  any key whose name says it is a row count or a column statistic (min, max, mean, null count, distinct count,
      num_rows, num_categories and the like, by the name's tokens) is removed with its value;
  R3  the raw ARROW:schema blob is withheld (binary); only its presence is recorded, and its decoded field metadata and
      schema-level metadata go through R1, R2, R4 and R5 like any other description text;
  R4  anything that looks like data values is withheld: a key whose name says it holds values, examples, samples,
      categories, levels or an enumeration; a JSON list of scalars that are not all column names of this file; a JSON
      object whose keys are all column names of this file (an example row);
  R5  a JSON number under a key not known to be schema (only precision and scale are) is withheld, since an unnamed
      number could be a count; a key whose value is not UTF-8 text is withheld as binary.
Each removal or withholding is recorded by key and path with the kind of thing it was, never with its value. For a
dictionary-encoded column the Arrow index width is withheld as well (it bounds the number of categories); the value
type is kept.

main() writes data/frozen/short_form_table_schema.json. Written 2026-11-19, session 23, job 2. The plan is a DRAFT and
is not frozen; this file is provisional and is not a ruling on any exclusion rule.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ---- the one file, and the record of its fetch ----------------------------------------------------------------------
SHORT_FORM_TABLE = ROOT / "data" / "raw" / "pudl" / "core_eia861__yearly_short_form.parquet"
MANIFEST = ROOT / "data" / "frozen" / "fetch_manifest_eia861.json"
MANIFEST_PATH_KEY = "data/raw/pudl/core_eia861__yearly_short_form.parquet"       # the entry's `path` in the manifest
EXPECTED_SHA256 = "a6a200ced70dffa2ea93e06e476fd43055ff4fa7289cffa881aa417d72c12e1c"  # as the request and D-111 quote it
OUT_SCHEMA = ROOT / "data" / "frozen" / "short_form_table_schema.json"

# ---- the only two queries run against the file (fixed; the path is a bound parameter) --------------------------------
SCHEMA_QUERY = ("SELECT name, type, type_length, repetition_type, num_children, converted_type, scale, precision, "
                "field_id, logical_type, duckdb_type, column_id FROM parquet_schema(?)")
KV_QUERY = "SELECT key, value FROM parquet_kv_metadata(?)"
SCHEMA_FIELDS = ("name", "type", "type_length", "repetition_type", "num_children", "converted_type", "scale",
                 "precision", "field_id", "logical_type", "duckdb_type", "column_id")

ARROW_SCHEMA_KEY = "ARROW:schema"

# ---- the redaction rule's word lists (the agent's reading) ------------------------------------------------------------
STAT_TOKENS = frozenset({
    "min", "max", "minimum", "maximum", "mean", "median", "avg", "average", "sum", "std", "stddev", "variance", "var",
    "count", "counts", "nulls", "null", "nullcount", "distinct", "unique", "nunique", "cardinality", "statistics",
    "stats", "stat", "histogram", "quantile", "quantiles", "percentile", "percentiles", "rows", "row", "nrows",
    "numrows", "rowcount", "num", "n", "total", "length", "len",
})
VALUE_TOKENS = frozenset({
    "value", "values", "example", "examples", "sample", "samples", "categories", "category", "levels", "enum", "enums",
    "domain", "head", "tail", "preview",
})
NUMERIC_SCHEMA_KEYS = frozenset({"precision", "scale"})
RANGE_BOUNDS = ("start", "stop", "step")

REDACTION_RULE = (
    "The agent's reading of 'no rows, column statistics or distinct values'. Description text is returned as found "
    "except: R1, in any JSON object with kind 'range' (pandas' RangeIndex descriptor) the keys start, stop and step are "
    "removed; R2, any key whose name says it is a row count or a column statistic is removed with its value; R3, the "
    "raw ARROW:schema blob is withheld and only its presence recorded, its decoded metadata going through the other "
    "rules; R4, anything that looks like data values (a key named for values, examples, samples, categories, levels or "
    "an enumeration; a list of scalars not all column names; an object whose keys are all column names) is withheld; "
    "R5, a number under a key not known to be schema (only precision and scale are) is withheld, and a value that is "
    "not UTF-8 text is withheld as binary. For a dictionary-encoded column the Arrow index width is withheld. Every "
    "removal is named by key and path and kind, never by value.")

WHAT_THIS_DOES_NOT_HOLD = [
    "no row of the table",
    "no row count; the footer's row count was not read into anything printed or stored",
    "no row-group or column statistic (minimum, maximum, null count, distinct count)",
    "no distinct value of any column",
    "no other file under data/raw (nothing there was listed, globbed, stat'ed or opened but this one file)",
    "no price, revenue or bill value",
]


class Stage1Refused(PermissionError):
    """Raised when the reader is asked for anything but the one authorized file."""


# =================================================================================================================
# The guard, the manifest and the hash
# =================================================================================================================
def _check_path(path) -> Path:
    """Refuse, in words, any path but the module constant SHORT_FORM_TABLE (compared as absolute paths)."""
    p = Path(os.path.abspath(path))
    allowed = Path(os.path.abspath(SHORT_FORM_TABLE))
    if p != allowed:
        raise Stage1Refused(f"stage 1 reads only {allowed}; {p} is not that file and is refused")
    return p


def expected_sha256_from_manifest(manifest=None) -> str:
    """The SHA-256 the fetch manifest records for MANIFEST_PATH_KEY. Stops if there is not exactly one entry."""
    manifest = MANIFEST if manifest is None else manifest
    with open(manifest, encoding="utf-8") as f:
        m = json.load(f)
    entries = [e for e in m.get("files", []) if e.get("path") == MANIFEST_PATH_KEY]
    if len(entries) != 1:
        raise ValueError(f"the manifest has {len(entries)} entries for {MANIFEST_PATH_KEY}; exactly one is needed")
    return str(entries[0]["sha256"])


def sha256_of(path) -> str:
    """SHA-256 of the authorized file's bytes. The bytes go to the hash and nowhere else."""
    p = _check_path(path)
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_check(path=None) -> dict:
    """Compare the file's SHA-256 with the manifest's and with the value the request quotes."""
    path = SHORT_FORM_TABLE if path is None else path
    _check_path(path)
    from_manifest = expected_sha256_from_manifest()
    found = sha256_of(path)
    return {
        "expected_from_manifest": from_manifest,
        "expected_as_quoted_in_request_and_D-111": EXPECTED_SHA256,
        "manifest_and_request_agree": from_manifest == EXPECTED_SHA256,
        "found": found,
        "equal": found == from_manifest == EXPECTED_SHA256,
    }


# =================================================================================================================
# The footer read (the only code that touches the file's structure)
# =================================================================================================================
def _read_footer_schema(path) -> tuple[list[dict], list[tuple[str, bytes]]]:
    """Run SCHEMA_QUERY and KV_QUERY, and nothing else, on the authorized file. Returns the schema elements in file
    order and the key-value pairs as raw (key, bytes). Neither query returns a row of the table or a statistic. The
    caller redacts; this function's return is never printed or stored as it is."""
    p = _check_path(path)
    import duckdb
    con = duckdb.connect(":memory:")
    try:
        schema_rows = con.execute(SCHEMA_QUERY, [str(p)]).fetchall()
        kv_rows = con.execute(KV_QUERY, [str(p)]).fetchall()
    finally:
        con.close()
    schema = [dict(zip(SCHEMA_FIELDS, r)) for r in schema_rows]
    kv = []
    for k, v in kv_rows:
        key = k.decode("utf-8", errors="replace") if isinstance(k, (bytes, bytearray)) else str(k)
        val = bytes(v) if isinstance(v, (bytes, bytearray, memoryview)) else str(v).encode("utf-8")
        kv.append((key, val))
    return schema, kv


# =================================================================================================================
# Redaction (pure functions)
# =================================================================================================================
def name_tokens(name: str) -> list[str]:
    """Split a key name into lower-case tokens at non-alphanumerics and at lower-to-upper case changes."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
    return [t for t in re.split(r"[^0-9A-Za-z]+", s.lower()) if t]


def says_statistic(name: str) -> bool:
    toks = name_tokens(name)
    joined = "".join(toks)
    return bool(set(toks) & STAT_TOKENS) or joined in {"numrows", "rowcount", "nullcount", "distinctcount",
                                                       "numcategories", "numvalues", "valuecount"}


def says_values(name: str) -> bool:
    return bool(set(name_tokens(name)) & VALUE_TOKENS)


def _is_scalar(x) -> bool:
    return x is None or isinstance(x, (str, int, float, bool))


def _clean_json(obj, path: str, columns: frozenset, log: list, key: str | None = None):
    """Walk a decoded JSON value and return it with R1, R2, R4 and R5 applied. Removed parts are logged by path and
    kind. Returns the module's _WITHHELD marker when the whole value is withheld."""
    if isinstance(obj, dict):
        out = {}
        is_range = obj.get("kind") == "range"
        if obj and all(isinstance(k, str) and k in columns for k in obj):
            log.append({"path": path, "rule": "R4", "kind": "an object whose keys are all column names of this file "
                        "(looks like an example row); withheld"})
            return _WITHHELD
        for k, v in obj.items():
            kp = f"{path}.{k}"
            if is_range and k in RANGE_BOUNDS:
                log.append({"path": kp, "rule": "R1", "kind": f"RangeIndex descriptor's {k}; removed"})
                continue
            if says_statistic(k):
                log.append({"path": kp, "rule": "R2", "kind": "a key whose name says it is a row count or a column "
                            "statistic; removed with its value"})
                continue
            if says_values(k):
                log.append({"path": kp, "rule": "R4", "kind": "a key whose name says it holds data values, examples "
                            "or categories; removed with its value"})
                continue
            cleaned = _clean_json(v, kp, columns, log, key=k)
            if cleaned is _WITHHELD:
                continue
            out[k] = cleaned
        return out
    if isinstance(obj, list):
        if all(_is_scalar(x) for x in obj):
            if all(isinstance(x, str) and x in columns for x in obj):
                return list(obj)
            log.append({"path": path, "rule": "R4", "kind": "a list of scalars not all of which are column names of "
                        "this file (possibly data values); withheld"})
            return _WITHHELD
        out = []
        for i, x in enumerate(obj):
            cleaned = _clean_json(x, f"{path}[{i}]", columns, log, key=key)
            if cleaned is not _WITHHELD:
                out.append(cleaned)
        return out
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float)):
        if key in NUMERIC_SCHEMA_KEYS:
            return obj
        log.append({"path": path, "rule": "R5", "kind": "a number under a key not known to be schema; withheld"})
        return _WITHHELD
    log.append({"path": path, "rule": "R5", "kind": f"a value of type {type(obj).__name__}; withheld"})
    return _WITHHELD


class _Withheld:
    def __repr__(self):
        return "<withheld>"


_WITHHELD = _Withheld()


def redact_value(key: str, raw: bytes, columns: frozenset, where: str) -> dict:
    """Apply the rule to one key-value pair. Returns {key, treatment, redactions, value?}. treatment is one of
    'returned whole', 'returned with redactions', 'withheld'."""
    log: list = []
    path = f"{where}[{key!r}]"
    if key == ARROW_SCHEMA_KEY:
        return {"key": key, "treatment": "withheld", "redactions": [{"path": path, "rule": "R3", "kind": "the raw "
                "Arrow schema blob (binary, base64); present, withheld; its decoded metadata is reported separately "
                "under the same rule"}]}
    if says_statistic(key):
        return {"key": key, "treatment": "withheld", "redactions": [{"path": path, "rule": "R2", "kind": "a key whose "
                "name says it is a row count or a column statistic"}]}
    if says_values(key):
        return {"key": key, "treatment": "withheld", "redactions": [{"path": path, "rule": "R4", "kind": "a key whose "
                "name says it holds data values, examples or categories"}]}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"key": key, "treatment": "withheld", "redactions": [{"path": path, "rule": "R5", "kind": "a value that "
                "is not UTF-8 text (binary)"}]}
    try:
        decoded = json.loads(text)
        is_json = True
    except (ValueError, TypeError):
        is_json = False
    if not is_json:
        return {"key": key, "treatment": "returned whole", "redactions": [], "value_format": "text", "value": text}
    cleaned = _clean_json(decoded, path, columns, log, key=key)
    if cleaned is _WITHHELD:
        return {"key": key, "treatment": "withheld", "redactions": log}
    return {"key": key, "treatment": "returned with redactions" if log else "returned whole", "redactions": log,
            "value_format": "JSON, parsed (whitespace not kept)", "value": cleaned}


def decode_arrow_schema(blob: bytes, columns: frozenset) -> dict:
    """Decode the ARROW:schema bytes in memory (no file is opened) and return each field's Arrow type and its field
    metadata, and the schema-level metadata, all through the rule. A decode failure is reported, not worked around."""
    try:
        import pyarrow as pa
        buf = base64.b64decode(blob)
        sch = pa.ipc.read_schema(pa.py_buffer(buf))
    except Exception as e:  # reported, not hidden
        return {"decoded": False, "error": f"{type(e).__name__}: {e}"}
    fields = []
    for i, f in enumerate(sch):
        t = f.type
        entry: dict = {"position": i + 1, "name": f.name, "nullable": bool(f.nullable)}
        if pa.types.is_dictionary(t):
            entry["arrow_type"] = f"dictionary<values={t.value_type}>"
            entry["type_redactions"] = [{"rule": "R4", "kind": "dictionary index width withheld (it bounds the number "
                                         "of categories)"}]
        else:
            entry["arrow_type"] = str(t)
        md = f.metadata or {}
        entry["field_metadata"] = [redact_value(k.decode("utf-8", errors="replace"), v, columns,
                                                f"field {f.name!r} metadata") for k, v in md.items()]
        fields.append(entry)
    smd = sch.metadata or {}
    schema_level = [redact_value(k.decode("utf-8", errors="replace"), v, columns, "decoded Arrow schema metadata")
                    for k, v in smd.items()]
    return {"decoded": True, "fields": fields, "schema_level_metadata": schema_level}


def describe(schema: list[dict], kv: list[tuple[str, bytes]]) -> dict:
    """Turn the footer read into the reportable record: schema elements in file order, and the description text with
    the rule applied. Pure; takes what _read_footer_schema returned."""
    root = schema[0] if schema else {}
    leaves = schema[1:]
    columns = frozenset(str(r["name"]) for r in leaves)
    cols_out = []
    for i, r in enumerate(leaves):
        cols_out.append({"position": i + 1, "name": r["name"], "physical_type": r["type"],
                         "logical_type": r["logical_type"], "converted_type": r["converted_type"],
                         "repetition_type": r["repetition_type"], "duckdb_type": r["duckdb_type"],
                         "type_length": r["type_length"], "scale": r["scale"], "precision": r["precision"],
                         "field_id": r["field_id"], "num_children": r["num_children"]})
    nested = [c["name"] for c in cols_out if c["num_children"]]
    kv_out = [redact_value(k, v, columns, "key-value metadata") for k, v in kv]
    arrow = None
    for k, v in kv:
        if k == ARROW_SCHEMA_KEY:
            arrow = decode_arrow_schema(v, columns)
    return {
        "parquet_schema": {
            "root": {"name": root.get("name"), "num_children": root.get("num_children")},
            "columns_in_file_order": cols_out,
            "nested_elements": nested,
        },
        "key_value_metadata": {
            "keys_found_in_file_order": [k for k, _ in kv],
            "per_key": kv_out,
        },
        "arrow_schema_decoded_from_ARROW_schema_key": arrow if arrow is not None else {"present": False},
    }


# =================================================================================================================
# The public entry point
# =================================================================================================================
def run_stage1(path=None) -> dict:
    """Guard the path, check the hash, and only if it matches read the footer schema and description. A mismatch
    stops here and the footer is not read."""
    path = SHORT_FORM_TABLE if path is None else path
    _check_path(path)
    hc = hash_check(path)
    if not hc["equal"]:
        return {"hash_check": hc, "stopped": "the hash does not match; stage 1 stopped and nothing else was read"}
    schema, kv = _read_footer_schema(path)
    out = {"hash_check": hc}
    out.update(describe(schema, kv))
    return out


def tool_versions() -> dict:
    import duckdb
    import pyarrow
    return {
        "file_read_by": f"duckdb {duckdb.__version__}: parquet_schema() and parquet_kv_metadata() only, by the "
                        "fixed queries SCHEMA_QUERY and KV_QUERY in pipeline/analysis/short_form_schema.py",
        "decode_of_ARROW_schema_bytes_by": f"pyarrow {pyarrow.__version__}: pyarrow.ipc.read_schema on the key's "
                                           "bytes in memory; no file opened by pyarrow",
        "hash_by": "hashlib.sha256 over the file's bytes",
        "why_duckdb": "pyarrow 19 refused the operational table from the same fetch while parsing its footer "
                      "('Repetition level histogram size mismatch'); the request names DuckDB's two schema functions; "
                      "each returns only what it is named for, so neither query can return a statistic (the agent's "
                      "choice)",
    }


def build_record(result: dict) -> dict:
    rec = {
        "what_this_is": (
            "Stage 1 of docs/gate1/short-form-access-request-2026-11-19.md, authorized by Joe on 2026-11-19 (D-111): "
            "the hash check and the schema and description read of data/raw/pudl/core_eia861__yearly_short_form.parquet, "
            "with no rows, column statistics or distinct values. Schema and description only. Provisional: the plan is "
            "a DRAFT and is not frozen. Not a ruling on any exclusion rule; stage 2 and the exclusion rule are not "
            "authorized. Written by pipeline/analysis/short_form_schema.py main(), session 23, job 2."),
        "file": MANIFEST_PATH_KEY,
        "tools": tool_versions(),
        "redaction_rule": REDACTION_RULE,
        "row_count": "not read; Joe's words do not name it and stage 2's column list does not need it (the session's "
                     "reading, his to strike, HANDOVER_session23_2026-11-19.md job 2)",
    }
    rec.update(result)
    rec["what_this_does_not_hold"] = WHAT_THIS_DOES_NOT_HOLD
    return rec


def main() -> int:
    result = run_stage1()
    rec = build_record(result)
    OUT_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_SCHEMA.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, OUT_SCHEMA)
    hc = rec["hash_check"]
    print(f"hash equal: {hc['equal']}")
    if not hc["equal"]:
        print("stage 1 stopped at the hash; nothing else read")
        return 1
    print(f"columns: {len(rec['parquet_schema']['columns_in_file_order'])}; "
          f"keys: {rec['key_value_metadata']['keys_found_in_file_order']}")
    print(f"wrote {OUT_SCHEMA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
