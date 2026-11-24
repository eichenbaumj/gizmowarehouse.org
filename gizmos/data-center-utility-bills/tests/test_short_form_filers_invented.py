"""Tests on invented inputs for pipeline/analysis/short_form_filers.py (session 24, job 2; stage 2 of the Short Form
access request, authorized by Joe on 2026-11-20, D-113). The nine items of S2.3 of
docs/gate1/short-form-access-request-2026-11-19.md, in order.

Nothing here reads data/. Every parquet file, manifest, quantities frame and flags frame is invented in pytest's
tmp_path or in memory. Where main() or the default path is exercised, the module constants SHORT_FORM_TABLE, OUT_TABLE,
OUT_SUMMARY and FLAGS_2019, short_form_schema's SHORT_FORM_TABLE, MANIFEST and EXPECTED_SHA256, and the quantity reader
are all replaced in the test, so the real file under data/raw cannot be reached. Tests whose name ends in `_can_fail`
make a deliberate break in the test process and show the same check then fails.
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

pd = pytest.importorskip("pandas")
pytest.importorskip("duckdb")
pq = pytest.importorskip("pyarrow.parquet")
pa = pytest.importorskip("pyarrow")

from pipeline.analysis import reconciliation_inputs as ri  # noqa: E402
from pipeline.analysis import short_form_filers as sff  # noqa: E402
from pipeline.analysis import short_form_schema as sfs  # noqa: E402

SENTINEL = 987654.321
SENTINEL_TEXT = "987654"
FOURTEEN = ("report_date", "utility_id_eia", "utility_name_eia", "entity_type", "state",
            "balancing_authority_code_eia", "sales_revenue", "sales_mwh", "customers", "has_net_metering",
            "has_demand_side_management", "has_time_responsive_programs", "has_green_pricing", "data_maturity")
NOT_REQUESTED = tuple(c for c in FOURTEEN if c not in sff.ACCESS_4_COLUMNS)


def _source_frame() -> pd.DataFrame:
    """An invented Short Form source: fourteen columns, sales_revenue holding the sentinel. Utility 11 in TX has two
    balancing authorities in 2016 (two rows collapsed); utility 12 files in 2016 and 2018; nothing in 2017."""
    rows = [
        (11, "TX", "2016-01-01", "BA1"), (11, "TX", "2016-01-01", "BA2"), (11, "TX", "2018-01-01", "BA1"),
        (12, "OK", "2016-01-01", "BA3"), (12, "OK", "2018-01-01", "BA3"), (13, "TX", "2020-01-01", "BA1"),
    ]
    n = len(rows)
    return pd.DataFrame({
        "report_date": pd.to_datetime([r[2] for r in rows]).date,
        "utility_id_eia": [r[0] for r in rows],
        "utility_name_eia": ["zzname"] * n, "entity_type": ["Cooperative"] * n,
        "state": [r[1] for r in rows], "balancing_authority_code_eia": [r[3] for r in rows],
        "sales_revenue": [SENTINEL] * n, "sales_mwh": [1.5] * n, "customers": [7] * n,
        "has_net_metering": [True] * n, "has_demand_side_management": [False] * n,
        "has_time_responsive_programs": [False] * n, "has_green_pricing": [False] * n, "data_maturity": ["final"] * n,
    })


class StrictReader:
    """An invented reader over the source frame that raises on any column outside ACCESS_4_COLUMNS and records every
    request."""
    def __init__(self, frame=None, extra=None):
        self.frame = _source_frame() if frame is None else frame
        self.calls = []
        self.extra = extra

    def __call__(self, path, columns):
        self.calls.append(list(columns))
        bad = [c for c in columns if c not in sff.ACCESS_4_COLUMNS]
        if bad:
            raise AssertionError(f"the invented reader was asked for {bad}")
        out = self.frame[list(columns)].copy()
        if self.extra:
            out[self.extra] = self.frame[self.extra] if self.extra in self.frame else 0
        return out


def _quantities() -> pd.DataFrame:
    rows = []
    for y in range(2015, 2025):
        rows.append((11, "TX", y, "Cooperative", 100.0 if y != 2016 else None))
        rows.append((21, "TX", y, "Municipal", 50.0))
    rows.append((12, "OK", 2017, "Cooperative", 10.0))
    # Row U's ownership pick searches exactly 2001 to 2025 (Joe, 2026-11-20, D-117) and refuses quantities lacking a year
    # of that range, so the invented quantities cover it: a filler unit outside the 50 states and DC, with no entity type
    # and no residential sales, in the years outside row U's window. It has no class, enters no row U frame, has no
    # residential row and no table row, so no count below moves (added 2026-11-20, session 26).
    rows += [(999, "ZZ", y, None, None) for y in list(range(2001, 2015)) + [2025]]
    return pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "entity_type", "res_mwh"])


def _flags() -> pd.DataFrame:
    return pd.DataFrame({"utility_id_eia": [11, 12, 21], "state": ["TX", "OK", "TX"], "year": [2019, 2019, 2019],
                         "short_form": pd.array([True, True, None], dtype="boolean")})


def _manifest(path: Path, sha: str) -> None:
    path.write_text(json.dumps({"files": [{"path": sfs.MANIFEST_PATH_KEY, "sha256": sha}]}))


@pytest.fixture
def world(tmp_path, monkeypatch):
    f = tmp_path / "invented_short_form.parquet"
    _source_frame().to_parquet(f, index=False)
    sha = hashlib.sha256(f.read_bytes()).hexdigest()
    man = tmp_path / "manifest.json"
    _manifest(man, sha)
    monkeypatch.setattr(sfs, "SHORT_FORM_TABLE", f)
    monkeypatch.setattr(sfs, "MANIFEST", man)
    monkeypatch.setattr(sfs, "EXPECTED_SHA256", sha)
    monkeypatch.setattr(sff, "SHORT_FORM_TABLE", f)
    monkeypatch.setattr(sff, "OUT_TABLE", tmp_path / "out" / "filers.parquet")
    monkeypatch.setattr(sff, "OUT_SUMMARY", tmp_path / "out" / "summary.json")
    flags_path = tmp_path / "flags.parquet"
    _flags().to_parquet(flags_path, index=False)
    monkeypatch.setattr(sff, "FLAGS_2019", flags_path)
    monkeypatch.setattr(sff, "load_quantities", _quantities)
    return {"file": f, "sha": sha, "manifest": man, "tmp": tmp_path}


def _leaks(text: str) -> list[str]:
    found = []
    if SENTINEL_TEXT in text:
        found.append("sentinel")
    if "zzname" in text:
        found.append("utility name")
    return found


def test_constants():
    assert sff.SHORT_FORM_TABLE == ROOT / "data" / "raw" / "pudl" / "core_eia861__yearly_short_form.parquet"
    assert sff.ACCESS_4_COLUMNS == ("utility_id_eia", "report_date", "state")
    assert sff.NEVER_LOADED_SHORT_FORM_COLUMNS == ("sales_revenue",)
    assert not set(sff.ACCESS_4_COLUMNS) & set(sff.NEVER_LOADED_SHORT_FORM_COLUMNS)
    assert sff.FLAGS_2019 == ri.OUT_SHORT_FORM
    assert sff.OUT_TABLE == ROOT / "data" / "interim" / "reconciliation_short_form_filers.parquet"
    assert sff.OUT_SUMMARY == ROOT / "data" / "frozen" / "reconciliation_short_form_filers_summary.json"


# ---- item 1: an invented reader never asked for sales_revenue; the sentinel nowhere in the output ----------------------
def test_item1_reader_never_asked_for_revenue_and_sentinel_nowhere(world, monkeypatch, capsys):
    spy = StrictReader()
    monkeypatch.setattr(ri, "_duckdb_select", spy)
    assert sff.main() == 0
    assert spy.calls == [list(sff.ACCESS_4_COLUMNS)]
    out = capsys.readouterr().out
    table_bytes = sff.OUT_TABLE.read_bytes()
    summary = sff.OUT_SUMMARY.read_text()
    table_text = pd.read_parquet(sff.OUT_TABLE).to_csv()
    assert _leaks(out) == [] and _leaks(summary) == [] and _leaks(table_text) == []
    assert SENTINEL_TEXT.encode() not in table_bytes
    assert str(SENTINEL).encode() not in table_bytes
    assert list(pd.read_parquet(sff.OUT_TABLE).columns) == ["utility_id_eia", "state", "year"]


def test_item1_leak_check_can_fail():
    """Break: the sentinel planted into a summary text in the test process is found by the leak check."""
    assert _leaks(json.dumps({"x": SENTINEL})) == ["sentinel"]


# ---- item 2: a request naming a barred column raises before any read --------------------------------------------------
@pytest.mark.parametrize("col", NOT_REQUESTED)
def test_item2_barred_column_raises_before_read(world, col):
    spy = StrictReader()
    with pytest.raises(PermissionError, match="outside the authorized list"):
        sff.read_short_form_table(read_fn=spy, columns=list(sff.ACCESS_4_COLUMNS) + [col])
    assert spy.calls == []


def test_item2_guard_can_fail(world, monkeypatch):
    """Break: reconciliation_inputs._guarded replaced by a pass-through in the test process; the request for
    sales_revenue then reaches the reader."""
    monkeypatch.setattr(ri, "_guarded", lambda fn, allowed, what: fn)
    spy = StrictReader()
    with pytest.raises(AssertionError, match="sales_revenue"):
        sff.read_short_form_table(read_fn=spy, columns=list(sff.ACCESS_4_COLUMNS) + ["sales_revenue"])
    assert spy.calls == [list(sff.ACCESS_4_COLUMNS) + ["sales_revenue"]]


# ---- item 3: a reader that returns an extra column is refused after the read ------------------------------------------
@pytest.mark.parametrize("extra", ["sales_revenue", "customers", "geometry"])
def test_item3_extra_column_refused(world, extra):
    with pytest.raises(PermissionError, match="outside the authorized list|expected exactly"):
        sff.read_short_form_table(read_fn=StrictReader(extra=extra))


def test_item3_output_check_can_fail(world, monkeypatch):
    """Break: both output checks replaced by the identity; the extra column and the sentinel then come back."""
    monkeypatch.setattr(ri, "_check_out", lambda frame, allowed, what: frame)
    monkeypatch.setattr(sff, "_check_exact", lambda df: df)
    df = sff.read_short_form_table(read_fn=StrictReader(extra="sales_revenue"))
    assert "sales_revenue" in df.columns and (df.sales_revenue == SENTINEL).all()


# ---- item 4: another path refused; a hash mismatch stops before the reader -------------------------------------------
def test_item4_other_path_refused(world, tmp_path):
    other = tmp_path / "other.parquet"
    other.write_bytes(world["file"].read_bytes())
    spy = StrictReader()
    with pytest.raises(sff.Access4Refused, match="is refused"):
        sff.read_short_form_table(other, read_fn=spy)
    assert spy.calls == []


def test_item4_path_guard_can_fail(world, tmp_path, monkeypatch):
    other = tmp_path / "other.parquet"
    other.write_bytes(world["file"].read_bytes())
    monkeypatch.setattr(sff, "_check_path", lambda p: Path(p))
    spy = StrictReader()
    sff.read_short_form_table(other, read_fn=spy)
    assert spy.calls != []


def test_item4_hash_mismatch_stops_before_reader(world, monkeypatch, capsys):
    spy = StrictReader()
    monkeypatch.setattr(ri, "_duckdb_select", spy)
    _manifest(world["manifest"], "f" * 64)
    monkeypatch.setattr(sfs, "EXPECTED_SHA256", "f" * 64)
    hc, raw = sff.run_read(read_fn=spy)
    assert hc["equal"] is False and raw is None and spy.calls == []
    assert sff.main() == 1
    assert spy.calls == []
    assert not sff.OUT_TABLE.exists() and not sff.OUT_SUMMARY.exists()
    assert "reader was not called" in capsys.readouterr().out


def test_item4_hash_stop_can_fail(world, monkeypatch):
    """Break: short_form_schema.hash_check made to say equal; the reader is then called on a mismatch."""
    _manifest(world["manifest"], "f" * 64)
    real = sfs.hash_check
    monkeypatch.setattr(sfs, "hash_check", lambda p=None: {**real(p), "equal": True})
    spy = StrictReader()
    sff.run_read(read_fn=spy)
    assert spy.calls != []


# ---- item 5: an invented parquet file through the default DuckDB reader ----------------------------------------------
def test_item5_default_duckdb_reader_returns_three_columns(world):
    df = sff.read_short_form_table()
    assert list(df.columns) == list(sff.ACCESS_4_COLUMNS)
    assert len(df) == 6
    assert SENTINEL_TEXT not in df.to_csv()


def test_item5_can_fail(world, monkeypatch):
    """Break: the default reader replaced by one that selects every column, with both output checks off; then more
    than three columns and the sentinel come back."""
    import duckdb
    monkeypatch.setattr(ri, "_duckdb_select",
                        lambda path, columns: duckdb.connect().execute(f"select * from read_parquet('{path}')").df())
    monkeypatch.setattr(ri, "_check_out", lambda frame, allowed, what: frame)
    monkeypatch.setattr(sff, "_check_exact", lambda df: df)
    df = sff.read_short_form_table()
    assert len(df.columns) == 14 and SENTINEL_TEXT in df.to_csv()


# ---- item 6: the pure table builder on a known answer ----------------------------------------------------------------
def test_item6_table_builder_known_answer():
    raw = _source_frame()[list(sff.ACCESS_4_COLUMNS)]
    t, by_year = sff.build_table(raw)
    assert list(t.columns) == ["utility_id_eia", "state", "year"]
    assert str(t.utility_id_eia.dtype) == "int64" and str(t.year.dtype) == "int64" and str(t.state.dtype) == "string"
    assert [tuple(r) for r in t.itertuples(index=False)] == [(11, "TX", 2016), (11, "TX", 2018), (12, "OK", 2016),
                                                             (12, "OK", 2018), (13, "TX", 2020)]
    assert by_year == {"2016": {"rows_read": 3, "rows_after_collapsing": 2, "rows_collapsed": 1},
                       "2018": {"rows_read": 2, "rows_after_collapsing": 2, "rows_collapsed": 0},
                       "2020": {"rows_read": 1, "rows_after_collapsing": 1, "rows_collapsed": 0}}


def test_item6_builder_refuses_other_columns_and_missing_values():
    raw = _source_frame()
    with pytest.raises(PermissionError):
        sff.build_table(raw)
    r = raw[list(sff.ACCESS_4_COLUMNS)].copy()
    r.loc[0, "state"] = None
    with pytest.raises(ValueError, match="missing values"):
        sff.build_table(r)


def test_item6_can_fail(monkeypatch):
    """Break: drop_duplicates made the identity in the test process; the collapsed count and the rows then differ
    from the known answer."""
    monkeypatch.setattr(pd.DataFrame, "drop_duplicates", lambda self, *a, **k: self)
    t, by_year = sff.build_table(_source_frame()[list(sff.ACCESS_4_COLUMNS)])
    assert len(t) == 6 and by_year["2016"]["rows_collapsed"] == 0


def test_summary_counts_known_answer(world, monkeypatch):
    monkeypatch.setattr(ri, "_duckdb_select", StrictReader())
    assert sff.main() == 0
    s = json.loads(sff.OUT_SUMMARY.read_text())
    assert s["read"]["rows_read"] == 6 and s["read"]["rows_collapsed"] == 1
    assert s["by_year"]["2016"] == {"rows_read": 3, "rows_after_collapsing": 2, "rows_collapsed": 1,
                                    "utilities": 2, "utility_states": 2}
    assert s["years_with_no_row"]["years"] == [2012, 2013, 2014, 2015, 2017, 2019, 2021, 2022, 2023, 2024, 2025]
    cont = {(c["earlier"], c["later"]): c for c in s["continuity_of_utility_states_between_consecutive_years_with_rows"]}
    assert cont[(2016, 2018)]["utility_states_in_both"] == 2 and cont[(2016, 2018)]["years_apart"] == 2
    assert cont[(2018, 2020)] == {"earlier": 2018, "later": 2020, "years_apart": 2, "utility_states_in_both": 0,
                                  "in_earlier_only": 2, "in_later_only": 1}
    assert s["window"]["utility_states_with_a_row_in_some_window_year"] == 3
    aq = s["against_the_quantities"]
    # table window unit-years: (11,TX,2016) (11,TX,2018) (12,OK,2016) (12,OK,2018) (13,TX,2020)
    # quantities with residential sales: 11 TX every year but 2016 (missing); 12 OK only 2017
    assert aq["window_unit_years_of_the_table_also_with_residential_sales_in_the_quantities"] == 1
    assert aq["window_unit_years_of_the_table_also_with_any_row_in_the_quantities"] == 2
    cs = aq["coverage_and_switching"]["utility_state"]["over_every_window_year"]
    # 11 TX appears 2015-2024 in quantities, table rows 2016 and 2018: switches; 12 OK appears 2017, no table row
    # that year: switches; 13 TX never in quantities
    assert cs["appearing_in_the_quantities_in_some_window_year"] == 2
    assert cs["not_appearing_in_the_quantities_in_any_window_year"] == 1
    assert cs["with_a_table_row_in_every_window_year_in_which_they_appear_in_the_quantities"] == 0
    assert cs["switching"] == 2
    f = s["the_2019_flags"]
    assert f["utility_states_2019_flag_true"] == 2 and f["rows_2019_flag_missing"] == 1
    # 11 TX: table rows 2016 and 2018, not 2020 -> 2018 only; 12 OK: 2018 only
    assert f["continuity_of_the_flagged_utility_states_in_the_table"] == {
        "with_a_table_row_in_both_2018_and_2020": 0, "in_2018_only": 2, "in_2020_only": 0, "in_neither": 0}
    assert sff.PAPER_FIGURE_KEY in s and "never a target" in s[sff.PAPER_FIGURE_KEY]["note"]
    assert "D-113" in s["what_this_is"] and "convention" in s["what_this_is"] and "not frozen" in s["what_this_is"]


def test_summary_from_written_matches_main_and_reads_no_raw(world, monkeypatch):
    monkeypatch.setattr(ri, "_duckdb_select", StrictReader())
    assert sff.main() == 0
    first = json.loads(sff.OUT_SUMMARY.read_text())
    spy = StrictReader()
    monkeypatch.setattr(ri, "_duckdb_select", spy)
    monkeypatch.setattr(sfs, "hash_check", lambda p=None: (_ for _ in ()).throw(AssertionError("hashed")))
    assert sff.summary_from_written() == 0
    assert spy.calls == []
    assert json.loads(sff.OUT_SUMMARY.read_text()) == first


# ---- item 7: the sample_flags builder plants each case under each option ---------------------------------------------
# Window 2015-2021. The table has rows in 2015, 2016, 2017, 2018 and 2020 (filler utility 99), none in 2019 or 2021.
# Utility 1 files in TX in 2016 and has a second state, OK, with no row (one state of two).
# Utility 2 (TX) has no table row; its 2019 flag is missing.
# Utility 3 (TX) has no table row; its 2019 flag is true.
# Utility 4 (TX) has no table row and no 2019 row in the flags file.
W = (2015, 2021)


def _table7() -> pd.DataFrame:
    rows = [(99, "ZZ", y) for y in (2015, 2016, 2017, 2018, 2020)] + [(1, "TX", 2016)]
    t = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year"])
    t["state"] = t.state.astype("string")
    return t


def _flags7() -> pd.DataFrame:
    return pd.DataFrame({"utility_id_eia": [1, 1, 2, 3], "state": ["TX", "OK", "TX", "TX"], "year": [2019] * 4,
                         "short_form": pd.array([None, None, None, True], dtype="boolean")})


def _frame7() -> pd.DataFrame:
    rows = [(1, "TX", y) for y in (2016, 2017, 2019)] + [(1, "OK", y) for y in (2016, 2017)]
    rows += [(2, "TX", 2017), (2, "TX", 2019), (3, "TX", 2017), (3, "TX", 2019), (4, "TX", 2017), (4, "TX", 2019)]
    rows += [(2, "TX", 2021)]
    return pd.DataFrame(rows, columns=["utility_id_eia", "state", "year"])


BASE = dict(window=W, years="years_filed", level="utility_state", no_row_in_covered_year="kept_no_record_of_a_filing",
            year_not_covered="no_exclusion_labelled", year_2019="flags_true_excluded_missing_kept",
            no_2019_flags_row="kept_no_record_of_a_filing")


def _get(r, u, s, y):
    v = r[(r.utility_id_eia == u) & (r.state == s) & (r.year == y)].short_form
    assert len(v) == 1
    return None if pd.isna(v.iloc[0]) else bool(v.iloc[0])


def test_item7_years_filed_by_utility_state():
    r = sff.sample_flags_from_table(_frame7(), _table7(), _flags7(), **BASE)
    assert _get(r, 1, "TX", 2016) is True           # a filer year
    assert _get(r, 1, "TX", 2017) is False          # no row in a covered year: kept, no record of a filing
    assert _get(r, 1, "OK", 2016) is False          # the other state of a utility filing in one state
    assert _get(r, 2, "TX", 2019) is False          # 2019, missing flag: kept, no record of a filing (d1)
    assert _get(r, 3, "TX", 2019) is True           # 2019, flag true
    assert _get(r, 4, "TX", 2019) is False          # 2019, no flags row: kept, no record of a filing
    assert _get(r, 2, "TX", 2021) is False          # a year the table does not cover, no exclusion
    assert set(r.columns) >= {"utility_id_eia", "state", "year", "short_form", "reading"}
    assert len(r) == len(_frame7())


def test_item7_by_utility():
    r = sff.sample_flags_from_table(_frame7(), _table7(), _flags7(), **{**BASE, "level": "utility"})
    assert _get(r, 1, "OK", 2016) is True           # the utility filed in TX that year
    assert _get(r, 1, "OK", 2017) is False


def test_item7_ever_filed():
    r = sff.sample_flags_from_table(_frame7(), _table7(), _flags7(), **{**BASE, "years": "ever_filed"})
    assert all(_get(r, 1, "TX", y) is True for y in (2016, 2017, 2019))
    assert _get(r, 1, "OK", 2016) is False and _get(r, 1, "OK", 2017) is False
    assert _get(r, 3, "TX", 2017) is True           # ever, from the 2019 flag
    assert _get(r, 2, "TX", 2017) is False and _get(r, 4, "TX", 2017) is False
    ru = sff.sample_flags_from_table(_frame7(), _table7(), _flags7(), **{**BASE, "years": "ever_filed",
                                                                         "level": "utility"})
    assert _get(ru, 1, "OK", 2017) is True


def test_item7_ever_counts_a_filing_in_a_year_the_unit_is_not_in_the_frame():
    fr = _frame7()
    fr = fr[~((fr.utility_id_eia == 1) & (fr.state == "TX") & (fr.year == 2016))]
    r = sff.sample_flags_from_table(fr, _table7(), _flags7(), **{**BASE, "years": "ever_filed"})
    assert _get(r, 1, "TX", 2017) is True


def test_item7_d2_no_exclusion_in_2019():
    r = sff.sample_flags_from_table(_frame7(), _table7(), None, **{**BASE, "year_2019": "no_exclusion_labelled"})
    assert _get(r, 3, "TX", 2019) is False and "not applied" in r[(r.utility_id_eia == 3) & (r.year == 2019)].reading.iloc[0]


@pytest.mark.parametrize("change,stops", [
    ({"no_row_in_covered_year": "stop"}, "no row in a covered year"),
    ({"year_not_covered": "stop"}, "the table has no row that year"),
    ({"year_2019": "flags_missing_stops"}, "missing flag"),
    ({"no_2019_flags_row": "stop"}, "no row in the flags file"),
])
def test_item7_each_stop_option_stops_in_words(change, stops):
    with pytest.raises(ValueError, match=stops):
        sff.sample_flags_from_table(_frame7(), _table7(), _flags7(), **{**BASE, **change})
    r = sff.readings(_frame7(), _table7(), _flags7(), **{**BASE, **change})
    assert r.short_form.isna().any()


def test_item7_stop_counts_known_answer():
    r = sff.readings(_frame7(), _table7(), _flags7(), **{**BASE, "no_row_in_covered_year": "stop"})
    # covered-year unit-years with no row: 1TX2017, 1OK2016, 1OK2017, 2TX2017, 3TX2017, 4TX2017
    assert int(r.short_form.isna().sum()) == 6
    r = sff.readings(_frame7(), _table7(), _flags7(), **{**BASE, "year_2019": "flags_missing_stops"})
    assert int(r.short_form.isna().sum()) == 2     # 1TX2019 and 2TX2019 carry a missing flag


@pytest.mark.parametrize("drop", list(BASE))
def test_item7_every_choice_required(drop):
    kw = {k: v for k, v in BASE.items() if k != drop}
    with pytest.raises(sff.ChoiceNotSupplied, match="not supplied"):
        sff.sample_flags_from_table(_frame7(), _table7(), _flags7(), **kw)


@pytest.mark.parametrize("name", [k for k in BASE if k != "window"])
def test_item7_unknown_option_refused(name):
    with pytest.raises(sff.ChoiceNotSupplied, match="not a known option"):
        sff.sample_flags_from_table(_frame7(), _table7(), _flags7(), **{**BASE, name: "zz_unknown"})


def test_item7_table_with_2019_rows_stops():
    t = pd.concat([_table7(), pd.DataFrame({"utility_id_eia": [5], "state": ["TX"], "year": [2019]})])
    with pytest.raises(ValueError, match="2019 rows"):
        sff.sample_flags_from_table(_frame7(), t, _flags7(), **BASE)


def test_item7_output_runs_through_run_u_step_filter():
    """The output is accepted by reconciliation_mu's own Short Form filter under 'unit_years_filed' and removes exactly
    the rows flagged true."""
    from pipeline.analysis import reconciliation_mu as mu
    r = sff.sample_flags_from_table(_frame7(), _table7(), _flags7(), **BASE)
    o = _frame7()
    kept, note = mu._u_drop_short_form(o, mu.ryu_spec("unit_years_filed"), r, W)
    assert len(kept) == len(o) - int(r.short_form.sum())


# Brought to Joe's ruling of 2026-11-20 (D-115), session 25: before it, no module-level name could hold a chosen rule.
# Now the adopted choices live in exactly one named place, ADOPTED_ROW_U_CHOICES (with its ruling, his words and the
# reconciliation_mu code beside it), and sample_flags_from_table still fills no choice itself.
ADOPTED_NAMES = {"ADOPTED_ROW_U_RULING", "ADOPTED_ROW_U_WORDS", "ADOPTED_ROW_U_CHOICES", "ADOPTED_ROW_U_MU_CODE"}


def _rule_names(src: str) -> set:
    names = set()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and re.search(r"(CHOSEN|ADOPTED|DEFAULT_RULE|RULE$|^EXCLUSION)", t.id):
                    names.add(t.id)
    return names


def test_item7_the_adopted_rule_is_in_one_named_place_and_the_builder_fills_no_choice():
    assert _rule_names(Path(sff.__file__).read_text()) == ADOPTED_NAMES
    sig = __import__("inspect").signature(sff.sample_flags_from_table)
    for name in BASE:
        assert sig.parameters[name].default is sff._NOT_SUPPLIED
    doc = sff.sample_flags_from_table.__doc__
    assert "decides nothing by itself" in doc and "ADOPTED_ROW_U_CHOICES" in doc and "D-115" in doc
    # the adopted call is the only place in the module that passes ADOPTED_ROW_U_CHOICES
    tree = ast.parse(Path(sff.__file__).read_text())
    users = [f.name for f in tree.body if isinstance(f, ast.FunctionDef)
             and any(isinstance(n, ast.Name) and n.id == "ADOPTED_ROW_U_CHOICES" for n in ast.walk(f))]
    assert sorted(users) == ["adopted_row_u_flags", "adopted_row_u_sample"]
    call = [n for n in ast.walk(next(f for f in tree.body if isinstance(f, ast.FunctionDef)
                                     and f.name == "adopted_row_u_flags")) if isinstance(n, ast.Call)]
    # it builds the flags by one call of the builder and nothing else of this module; the builtins are the step-window
    # check's (dict of the choices, int of the bounds, the ValueError for a window that would cut the adopted one)
    called = [getattr(c.func, "id", None) for c in call]
    assert called.count("sample_flags_from_table") == 1
    assert set(called) <= {"sample_flags_from_table", "dict", "int", "ValueError"}, called


def test_item7_one_named_place_can_fail():
    """Break: a second module-level constant naming a chosen rule is planted into the source in the test process; the
    one-place check then fails."""
    src = Path(sff.__file__).read_text() + "\nCHOSEN_RULE = 'ever_filed'\n"
    assert _rule_names(src) != ADOPTED_NAMES


def test_item7_required_choices_can_fail(monkeypatch):
    """Break: _need_choice replaced by one that fills a default in the test process; an unsupplied choice is then
    not refused."""
    defaults = {"years": "years_filed", "level": "utility_state", "no_row_in_covered_year": "kept_no_record_of_a_filing",
                "year_not_covered": "no_exclusion_labelled", "year_2019": "no_exclusion_labelled",
                "no_2019_flags_row": "kept_no_record_of_a_filing"}
    monkeypatch.setattr(sff, "_need_choice", lambda name, value, options: defaults[name]
                        if value is sff._NOT_SUPPLIED else value)
    r = sff.sample_flags_from_table(_frame7(), _table7(), None, window=W)
    assert len(r) == len(_frame7())


def test_item7_planted_case_can_fail():
    """Break: the 2019 flag of utility 3 is flipped in the test process; the planted answer then fails."""
    f = _flags7()
    f.loc[f.utility_id_eia == 3, "short_form"] = pd.NA
    r = sff.sample_flags_from_table(_frame7(), _table7(), f, **BASE)
    assert _get(r, 3, "TX", 2019) is not True


# ---- item 8: a source scan --------------------------------------------------------------------------------------------
BARRED_ATTRS = {"read_table", "read_row_group", "statistics", "iter_batches", "ParquetFile", "ParquetDataset",
                "parquet_metadata", "num_row_groups", "row_group", "execute", "sql", "query"}
BARRED_IMPORTS = {"pyarrow.parquet", "pyarrow.dataset", "polars", "fastparquet", "duckdb"}
BARRED_SQL = [r"parquet_metadata\s*\(", r"read_parquet\s*\(", r"select\s+\*", r"\bselect\b[^\n]*\bfrom\b"]


def _docstrings(tree) -> set:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
                ids.add(id(b[0].value))
    return ids


def scan_source(src: str) -> list[str]:
    tree = ast.parse(src)
    docs = _docstrings(tree)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in BARRED_ATTRS:
            hits.append(f"attribute {node.attr}")
        if isinstance(node, ast.Attribute) and node.attr == "sales_revenue":
            hits.append("attribute sales_revenue")
        if isinstance(node, ast.Import):
            hits += [f"import {a.name}" for a in node.names if a.name in BARRED_IMPORTS]
        if isinstance(node, ast.ImportFrom) and node.module in BARRED_IMPORTS:
            hits.append(f"from {node.module}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "read_parquet":
            if not (node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in ("FLAGS_2019", "OUT_TABLE")):
                hits.append("read_parquet of something other than FLAGS_2019 or OUT_TABLE")
        if isinstance(node, (ast.List, ast.Tuple, ast.Subscript, ast.Compare)):
            consts = [n for n in ast.walk(node) if isinstance(n, ast.Constant) and n.value == "sales_revenue"]
            if consts and isinstance(node, (ast.List, ast.Subscript, ast.Compare)):
                hits.append("sales_revenue named in a list, subscript or comparison")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            for pat in BARRED_SQL:
                if re.search(pat, node.value, flags=re.I):
                    hits.append(f"string matching {pat}")
    # sales_revenue may appear as a constant only in the NEVER_LOADED tuple and in prose
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Tuple):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(isinstance(e, ast.Constant) and e.value == "sales_revenue" for e in node.value.elts):
                if names != ["NEVER_LOADED_SHORT_FORM_COLUMNS"]:
                    hits.append(f"sales_revenue in the tuple {names}")
    return hits


def test_item8_source_has_no_other_query_and_no_revenue_read():
    src = Path(sff.__file__).read_text()
    assert scan_source(src) == []
    tree = ast.parse(src)
    # the only reader of data/raw is the guarded one: _guarded, _check_out and _duckdb_select appear once each
    calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "ri"]
    assert calls.count("_guarded") == 1 and calls.count("_check_out") == 1


@pytest.mark.parametrize("planted", [
    "x = duckdb.connect().execute(\"select * from read_parquet('f')\")",
    "import pyarrow.parquet as pq",
    "df = pd.read_parquet(SHORT_FORM_TABLE, columns=['sales_revenue'])",
    "v = df.sales_revenue.sum()",
    "COLS = ('utility_id_eia', 'sales_revenue')",
])
def test_item8_source_scan_can_fail(planted):
    src = Path(sff.__file__).read_text() + "\n" + planted + "\n"
    assert scan_source(src) != []


# ---- row U's frame takes its ownership classes by Joe's pick of 2026-11-20 (D-117) ------------------------------------
def _quantities_d117() -> pd.DataFrame:
    """_quantities() plus (31, TX), typed Cooperative only before row U's window and missing in every window year (the
    last nonmissing type over 2001 to 2025 gives it a class), and (32, TX), with no type in any year (no class)."""
    extra = [(31, "TX", y, "Cooperative" if y < 2015 else None, 5.0) for y in range(2001, 2025)]
    extra += [(32, "TX", y, None, 5.0) for y in range(2015, 2025)]
    return pd.concat([_quantities(), pd.DataFrame(extra, columns=["utility_id_eia", "state", "year", "entity_type",
                                                                  "res_mwh"])], ignore_index=True)


def _frame_units(q) -> set:
    f = sff.row_u_quantity_frame(q)
    return set(zip(f.utility_id_eia, f.state))


def test_row_u_frame_uses_the_last_nonmissing_type_over_2001_to_2025():
    units = _frame_units(_quantities_d117())
    assert (31, "TX") in units and (32, "TX") not in units and {(11, "TX"), (21, "TX")} <= units
    assert not any(u == 999 for u, _ in units)
    with pytest.raises(ValueError, match="searches exactly 2001 to 2025"):
        sff.row_u_quantity_frame(_quantities_d117()[lambda d: d.year >= 2015])
    assert "adopted_row_u_ownership_classes" in sff.row_u_quantity_frame.__doc__


def test_row_u_frame_pick_can_fail(monkeypatch):
    """Break, made in the test process: the classes taken over row U's window only; (31, TX) then has no class and
    leaves the frame, so the known answer fails."""
    from pipeline.analysis import reconciliation_mu as mu
    monkeypatch.setattr(mu, "adopted_row_u_ownership_classes",
                        lambda q: mu.ownership_classes(q[q.year >= 2015], "U", "last"))
    assert (31, "TX") not in _frame_units(_quantities_d117())


# ---- Joe's rulings of 2026-11-20: row U's ownership type described (D-119); the window message names D-115 ------------
def _sff_ownership_problems(texts: dict) -> list:
    bad = []
    for name, t in texts.items():
        t = " ".join(str(t).split()).replace('" "', "")
        rest = t.replace("not the latest year-by-year EIA classification", "").lower()
        for phrase in ("latest", "most recent", "last nonmissing reported", "caller's choice", "not decided"):
            if phrase in rest:
                bad.append((name, phrase))
        if "modal" not in t or "D-119" not in t:
            bad.append((name, "no 'modal' or no D-119"))
    return bad


def _sff_ownership_texts() -> dict:
    import inspect
    sample = inspect.getsource(sff.adopted_row_u_sample)
    return {"row_u_quantity_frame": inspect.getdoc(sff.row_u_quantity_frame),
            "frame_with_no_exclusion": sample.split('"frame_with_no_exclusion": {')[1].split("**size(frame)")[0]}


def test_d119_row_u_frame_texts_describe_the_modal_type():
    assert _sff_ownership_problems(_sff_ownership_texts()) == []


def test_d119_row_u_frame_texts_can_fail():
    """Break: the D-117 wording given to the same check in the test process."""
    old = "with an ownership class (scheme U, the last nonmissing reported entity type over 2001 to 2025, D-117)"
    assert _sff_ownership_problems({"x": old}) == [("x", "last nonmissing reported"), ("x", "no 'modal' or no D-119")]


def test_d115_the_window_message_names_the_adopted_rule_and_not_an_open_choice():
    kw = {k: v for k, v in BASE.items() if k != "window"}
    with pytest.raises(sff.ChoiceNotSupplied) as e:
        sff.sample_flags_from_table(_frame7(), _table7(), _flags7(), **kw)
    msg = str(e.value)
    assert "not supplied" in msg and "D-115" in msg and "ADOPTED_ROW_U_CHOICES" in msg
    assert "not decided" not in msg and "Joe rules on it" not in msg
    # can fail: the old message fails the same checks
    old = "the choice 'window' was not supplied. It is not decided; Joe rules on it."
    assert "D-115" not in old and "not decided" in old
