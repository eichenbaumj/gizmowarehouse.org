"""Tests on invented inputs for pipeline/analysis/short_form_schema.py (session 23, job 2; stage 1 of the Short Form
access request, authorized by Joe on 2026-11-19, D-111).

Nothing here reads data/. Every parquet file and manifest is invented in pytest's tmp_path. The tests reach the
invented file by monkeypatching the module constants SHORT_FORM_TABLE, MANIFEST, EXPECTED_SHA256 and OUT_SCHEMA; the
public entry point run_stage1 and the private reader _read_footer_schema both refuse any path but SHORT_FORM_TABLE.

The invented file carries a decoy revenue column holding a sentinel value, a pandas RangeIndex (so the `pandas` key
holds the row count as its stop), a categorical column (so the `pandas` key holds num_categories), per-field
description metadata, a field metadata key that names a statistic, and planted schema-level keys that carry a fake
statistic, a bare row count and a list of values. Tests whose name ends in `_can_fail` make a deliberate break in the
test process (a monkeypatched function or a planted source line) and show the same check then fails.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import short_form_schema as sfs  # noqa: E402

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")
pd = pytest.importorskip("pandas")
pytest.importorskip("duckdb")

N_ROWS = 3187                     # the invented row count; must appear nowhere in the output
SENTINEL = 987654.321             # the decoy revenue column's value; must appear nowhere in the output
SENTINEL_TEXT = "987654"
N_CATEGORIES = 7
CATEGORY_VALUES = [f"zqcat{i}" for i in range(N_CATEGORIES)]   # distinct values of a column; must not appear
PLANTED_VALUE_LIST = ["zzplantedvalueA", "zzplantedvalueB"]


def _invented_parquet(path: Path) -> None:
    df = pd.DataFrame({
        "utility_id_eia": [i % 50 + 1 for i in range(N_ROWS)],
        "report_date": pd.to_datetime(["2019-01-01"] * N_ROWS),
        "state": ["TX"] * N_ROWS,
        "sales_revenue": [SENTINEL] * N_ROWS,
        "entity_type": pd.Categorical([CATEGORY_VALUES[i % N_CATEGORIES] for i in range(N_ROWS)]),
    })
    t = pa.Table.from_pandas(df)                          # RangeIndex kept as metadata: start 0, stop N_ROWS, step 1
    s = t.schema
    s = s.set(s.get_field_index("utility_id_eia"),
              s.field("utility_id_eia").with_metadata({"description": "EIA utility identifier (invented text)"}))
    s = s.set(s.get_field_index("sales_revenue"),
              s.field("sales_revenue").with_metadata({"description": "Revenue in dollars (invented text)",
                                                      "max_value": str(SENTINEL)}))
    md = dict(s.metadata)
    md[b"description"] = b"Invented table: one row per utility, state and report year of a short filing."
    md[b"pudl_stats"] = json.dumps({"sales_revenue": {"max": SENTINEL, "null_count": 0},
                                    "note": "fake statistics"}).encode()
    md[b"row_count"] = str(N_ROWS).encode()
    md[b"provenance"] = json.dumps({"rows_seen": N_ROWS, "source": "invented",
                                    "allowed": PLANTED_VALUE_LIST}).encode()
    s = s.with_metadata(md)
    t = t.cast(s).replace_schema_metadata(md)
    pq.write_table(t, path)


def _manifest(path: Path, sha: str) -> None:
    path.write_text(json.dumps({"fetched_at": "2026-11-11T00:00:00+00:00", "files": [
        {"url": "invented", "ok": True, "path": "data/raw/pudl/other.parquet", "bytes": 1, "sha256": "0" * 64},
        {"url": "invented", "ok": True, "path": sfs.MANIFEST_PATH_KEY, "bytes": 1, "sha256": sha},
    ]}))


@pytest.fixture
def world(tmp_path, monkeypatch):
    f = tmp_path / "invented_short_form.parquet"
    _invented_parquet(f)
    sha = hashlib.sha256(f.read_bytes()).hexdigest()
    man = tmp_path / "manifest.json"
    _manifest(man, sha)
    monkeypatch.setattr(sfs, "SHORT_FORM_TABLE", f)
    monkeypatch.setattr(sfs, "MANIFEST", man)
    monkeypatch.setattr(sfs, "EXPECTED_SHA256", sha)
    monkeypatch.setattr(sfs, "OUT_SCHEMA", tmp_path / "out" / "short_form_table_schema.json")
    return {"file": f, "sha": sha, "manifest": man, "tmp": tmp_path}


def _leaks(text: str) -> list[str]:
    """Every barred thing found in serialized output."""
    found = []
    if re.search(rf"(?<![0-9A-Za-z]){N_ROWS}(?![0-9A-Za-z])", text):
        found.append("row count")
    if SENTINEL_TEXT in text:
        found.append("sentinel")
    for v in CATEGORY_VALUES + PLANTED_VALUE_LIST:
        if v in text:
            found.append(f"value {v}")
    if '"num_categories"' in text or '"stop"' in text:
        found.append("barred key")
    return found


# ---- the reader returns names, types and description text ---------------------------------------------------------
def test_returns_names_types_and_description(world):
    out = sfs.run_stage1()
    assert out["hash_check"]["equal"] is True
    cols = out["parquet_schema"]["columns_in_file_order"]
    assert [c["name"] for c in cols] == ["utility_id_eia", "report_date", "state", "sales_revenue", "entity_type"]
    assert [c["position"] for c in cols] == [1, 2, 3, 4, 5]
    assert cols[0]["physical_type"] == "INT64"
    assert cols[3]["physical_type"] == "DOUBLE"
    assert "StringType" in str(cols[2]["logical_type"])
    kv = {e["key"]: e for e in out["key_value_metadata"]["per_key"]}
    assert set(out["key_value_metadata"]["keys_found_in_file_order"]) == {
        "pandas", "description", "pudl_stats", "row_count", "provenance", "ARROW:schema"}
    assert kv["description"]["treatment"] == "returned whole"
    assert kv["description"]["value"].startswith("Invented table: one row per utility")
    arrow = out["arrow_schema_decoded_from_ARROW_schema_key"]
    assert arrow["decoded"] is True
    f = {x["name"]: x for x in arrow["fields"]}
    assert f["utility_id_eia"]["arrow_type"] == "int64"
    assert f["utility_id_eia"]["field_metadata"][0]["value"] == "EIA utility identifier (invented text)"
    rev = {m["key"]: m for m in f["sales_revenue"]["field_metadata"]}
    assert rev["description"]["value"] == "Revenue in dollars (invented text)"
    assert rev["max_value"]["treatment"] == "withheld"
    assert f["entity_type"]["arrow_type"] == "dictionary<values=string>"


def test_each_planted_key_is_treated_as_named(world):
    out = sfs.run_stage1()
    kv = {e["key"]: e for e in out["key_value_metadata"]["per_key"]}
    # R1: the RangeIndex bounds removed, the rest of the pandas key returned
    assert kv["pandas"]["treatment"] == "returned with redactions"
    rules = {(r["rule"], r["path"].split(".")[-1]) for r in kv["pandas"]["redactions"]}
    assert {("R1", "start"), ("R1", "stop"), ("R1", "step")} <= rules
    assert ("R2", "num_categories") in rules
    idx = kv["pandas"]["value"]["index_columns"][0]
    assert idx["kind"] == "range" and not {"start", "stop", "step"} & set(idx)
    # R2: a key named for a statistic or a row count is withheld whole
    assert kv["pudl_stats"]["treatment"] == "withheld" and kv["pudl_stats"]["redactions"][0]["rule"] == "R2"
    assert kv["row_count"]["treatment"] == "withheld"
    # R3: the raw blob withheld, its presence recorded
    assert kv["ARROW:schema"]["treatment"] == "withheld" and kv["ARROW:schema"]["redactions"][0]["rule"] == "R3"
    assert "value" not in kv["ARROW:schema"]
    # R2 and R4 inside a JSON key: rows_seen removed, the value list withheld, the source kept
    prov = kv["provenance"]
    assert prov["treatment"] == "returned with redactions"
    assert prov["value"] == {"source": "invented"}
    assert {r["rule"] for r in prov["redactions"]} == {"R2", "R4"}
    # the decoded Arrow schema-level metadata goes through the same rule
    smd = {e["key"]: e for e in out["arrow_schema_decoded_from_ARROW_schema_key"]["schema_level_metadata"]}
    assert smd["pandas"]["treatment"] == "returned with redactions"
    assert smd["row_count"]["treatment"] == "withheld"


def test_no_sentinel_row_count_or_value_anywhere_in_output(world):
    out = sfs.run_stage1()
    text = json.dumps(out)
    assert _leaks(text) == []
    sfs.main()
    written = sfs.OUT_SCHEMA.read_text()
    assert _leaks(written) == []
    rec = json.loads(written)
    assert rec["hash_check"]["equal"] is True
    assert "no row count" in " ".join(rec["what_this_does_not_hold"])
    assert "D-111" in rec["what_this_is"] and "not a ruling" in rec["what_this_is"].lower()


def test_no_leak_can_fail(world, monkeypatch):
    """Break: the JSON redaction is replaced by the identity in the test process. The row count, the sentinel and the
    category count then reach the output, so the leak check above would fail."""
    def identity(obj, path, columns, log, key=None):
        return obj
    monkeypatch.setattr(sfs, "_clean_json", identity)
    monkeypatch.setattr(sfs, "says_statistic", lambda name: False)
    monkeypatch.setattr(sfs, "says_values", lambda name: False)
    text = json.dumps(sfs.run_stage1())
    leaks = _leaks(text)
    assert "row count" in leaks and "sentinel" in leaks and "barred key" in leaks


def test_stdout_of_main_holds_nothing_barred(world, capsys):
    sfs.main()
    assert _leaks(capsys.readouterr().out) == []


# ---- the path guard ---------------------------------------------------------------------------------------------
def test_other_path_refused(world, tmp_path):
    other = tmp_path / "other.parquet"
    other.write_bytes(world["file"].read_bytes())
    for fn in (sfs.run_stage1, sfs.sha256_of, sfs._read_footer_schema, sfs.hash_check):
        with pytest.raises(sfs.Stage1Refused, match="is refused"):
            fn(other)


def test_default_constant_is_the_one_file():
    assert sfs.SHORT_FORM_TABLE == ROOT / "data" / "raw" / "pudl" / "core_eia861__yearly_short_form.parquet"
    assert sfs.MANIFEST_PATH_KEY == "data/raw/pudl/core_eia861__yearly_short_form.parquet"
    assert sfs.EXPECTED_SHA256 == "a6a200ced70dffa2ea93e06e476fd43055ff4fa7289cffa881aa417d72c12e1c"
    assert sfs.OUT_SCHEMA == ROOT / "data" / "frozen" / "short_form_table_schema.json"


def test_path_guard_can_fail(world, tmp_path, monkeypatch):
    """Break: the guard is replaced by one that passes everything; the other path is then not refused."""
    other = tmp_path / "other.parquet"
    other.write_bytes(world["file"].read_bytes())
    monkeypatch.setattr(sfs, "_check_path", lambda p: Path(p))
    sfs.sha256_of(other)          # no refusal: the test above would fail under this break


# ---- the hash stops the read ------------------------------------------------------------------------------------
def test_hash_mismatch_stops_before_schema_read(world, monkeypatch):
    calls = []
    monkeypatch.setattr(sfs, "_read_footer_schema", lambda p: calls.append(p) or ([], []))
    _manifest(world["manifest"], "f" * 64)
    monkeypatch.setattr(sfs, "EXPECTED_SHA256", "f" * 64)
    out = sfs.run_stage1()
    assert out["hash_check"]["equal"] is False
    assert "stopped" in out and calls == []
    assert set(out) == {"hash_check", "stopped"}
    assert sfs.main() == 1
    rec = json.loads(sfs.OUT_SCHEMA.read_text())
    assert "parquet_schema" not in rec and rec["hash_check"]["found"] == world["sha"]


def test_manifest_and_request_disagreeing_also_stops(world, monkeypatch):
    calls = []
    monkeypatch.setattr(sfs, "_read_footer_schema", lambda p: calls.append(p) or ([], []))
    monkeypatch.setattr(sfs, "EXPECTED_SHA256", "e" * 64)     # the file matches the manifest but not the request
    out = sfs.run_stage1()
    assert out["hash_check"]["manifest_and_request_agree"] is False and out["hash_check"]["equal"] is False
    assert calls == []


def test_hash_stop_can_fail(world, monkeypatch):
    """Break: hash_check is made to say equal whatever the hash; the schema function is then called on a mismatch."""
    calls = []
    monkeypatch.setattr(sfs, "_read_footer_schema", lambda p: calls.append(p) or ([], []))
    _manifest(world["manifest"], "f" * 64)
    real = sfs.hash_check
    monkeypatch.setattr(sfs, "hash_check", lambda p=None: {**real(p), "equal": True})
    sfs.run_stage1()
    assert calls != []            # the stop test above would fail under this break


def test_manifest_needs_exactly_one_entry(tmp_path, monkeypatch):
    man = tmp_path / "m.json"
    man.write_text(json.dumps({"files": []}))
    with pytest.raises(ValueError, match="exactly one"):
        sfs.expected_sha256_from_manifest(man)


# ---- the redaction rule on its own ------------------------------------------------------------------------------
@pytest.mark.parametrize("name,stat", [
    ("num_rows", True), ("row_count", True), ("nullCount", True), ("distinct_count", True), ("max", True),
    ("column_min", True), ("num_categories", True), ("n", True), ("description", False), ("primary_key", False),
    ("pandas", False), ("field_name", False), ("numpy_type", False),
])
def test_says_statistic(name, stat):
    assert sfs.says_statistic(name) is stat


def test_example_row_and_value_list_withheld():
    cols = frozenset({"a", "b"})
    log: list = []
    assert sfs._clean_json({"a": 1, "b": 2}, "$", cols, log) is sfs._WITHHELD
    assert sfs._clean_json(["x", "y"], "$", cols, log) is sfs._WITHHELD
    assert sfs._clean_json(["a", "b"], "$", cols, log) == ["a", "b"]           # a list of column names is schema
    assert sfs._clean_json({"precision": 3, "scale": 1, "width": 9}, "$", cols, log) == {"precision": 3, "scale": 1}
    assert [r["rule"] for r in log] == ["R4", "R4", "R5"]
    bare = sfs.redact_value("k", b"4321", cols, "kv")
    assert bare["treatment"] == "withheld" and "4321" not in json.dumps(bare)
    binary = sfs.redact_value("k", b"\xff\xfe\x00", cols, "kv")
    assert binary["treatment"] == "withheld" and binary["redactions"][0]["rule"] == "R5"


# ---- the module's source has no call that reads rows or statistics ---------------------------------------------
BARRED_ATTRS = {"read_table", "read_pandas", "to_table", "read_row_group", "read_row_groups", "num_rows",
                "row_group", "row_groups", "statistics", "iter_batches", "ParquetFile", "ParquetDataset",
                "read_parquet", "parquet_metadata", "to_pandas", "scan_parquet", "dataset", "num_row_groups"}
BARRED_NAMES = {"read_parquet", "read_table", "ParquetFile", "parquet_metadata"}
BARRED_IMPORTS = {"pyarrow.parquet", "pandas", "polars", "fastparquet", "pyarrow.dataset"}
BARRED_SQL = [r"parquet_metadata\s*\(", r"parquet_file_metadata\s*\(", r"read_parquet\s*\(", r"parquet_scan\s*\(",
              r"parquet_bloom_probe\s*\(", r"select\s+\*", r"\bcount\s*\(", r"\bdistinct\s*\("]


def scan_source(src: str) -> list[str]:
    tree = ast.parse(src)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in BARRED_ATTRS:
            hits.append(f"attribute {node.attr}")
        if isinstance(node, ast.Name) and node.id in BARRED_NAMES:
            hits.append(f"name {node.id}")
        if isinstance(node, ast.Import):
            hits += [f"import {a.name}" for a in node.names if a.name in BARRED_IMPORTS]
        if isinstance(node, ast.ImportFrom):
            if node.module in BARRED_IMPORTS:
                hits.append(f"from {node.module}")
            if node.module == "pyarrow" and any(a.name in {"parquet", "dataset"} for a in node.names):
                hits.append("from pyarrow import parquet/dataset")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for pat in BARRED_SQL:
                if re.search(pat, node.value, flags=re.I):
                    hits.append(f"string matching {pat}")
            if re.search(r"\bselect\b", node.value, flags=re.I) and re.search(r"\bfrom\b", node.value, flags=re.I):
                if node.value not in (sfs.SCHEMA_QUERY, sfs.KV_QUERY):
                    hits.append("a query other than the two fixed ones")
    return hits


def test_source_has_no_row_or_statistic_read():
    src = Path(sfs.__file__).read_text()
    assert scan_source(src) == []
    assert sfs.SCHEMA_QUERY.endswith("FROM parquet_schema(?)")
    assert sfs.KV_QUERY == "SELECT key, value FROM parquet_kv_metadata(?)"
    # the only con.execute calls run the two constants
    tree = ast.parse(src)
    executed = [n.args[0].id for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "execute"]
    assert executed == ["SCHEMA_QUERY", "KV_QUERY"]


@pytest.mark.parametrize("planted", [
    "n = pq.ParquetFile(p).metadata.num_rows",
    "t = pq.read_table(p)",
    "con.execute(\"SELECT * FROM parquet_metadata('x')\")",
    "s = f.metadata.row_group(0).column(0).statistics",
    "import pyarrow.parquet as pq",
    "for b in pf.iter_batches(): pass",
])
def test_source_scan_can_fail(planted):
    """Break: a barred line planted into a copy of the source in the test process is found by the scan."""
    src = Path(sfs.__file__).read_text() + "\n" + planted + "\n"
    assert scan_source(src) != []
