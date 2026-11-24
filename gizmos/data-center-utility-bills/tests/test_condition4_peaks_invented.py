"""Condition 4's peak rows: the one authorized read and the retained input (pipeline/analysis/condition4_peaks.py).

Invented inputs only. The raw table is an INVENTED parquet file under pytest's tmp_path, and conditions.PEAK_FILE is
replaced with it through monkeypatch, so conditions.read_peaks()'s own default path (duckdb, a select of the seven
columns) is exercised on the invented file. The invented file carries extra columns, one named like a revenue column
with a sentinel value, and the tests require that neither reaches the retained file or the record. No file under data/
is read or written; every write goes to tmp_path, checked by a spy on the module's two writers.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import condition4_peaks as c4  # noqa: E402
from pipeline.analysis import conditions as cn  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

SENTINEL = 987654321.125
REVENUE_COLUMN = "sales_revenue"
HOSTS = [((1, "AA"), 2015), ((2, "AB"), 2015), ((3, "AC"), 2016), ((4, "AD"), 2017)]
GROWTH = {1: 0.00, 2: 0.02, 3: 0.04, 4: 0.06}


def raw_frame() -> pd.DataFrame:
    """The invented peak table: the seven columns, a revenue-like column with a sentinel and a customers column. Four
    hosts with a peak in every year 2001 to 2025 (rising at their own rate), and rows that exercise the round trip: an
    unobserved row, a row with a winter peak only, a row with neither peak, a missing short-form mark, a missing
    data_observed (read_peaks reads it as observed), and a repeated (utility, state, year) key at EIA's placeholder id."""
    rows = []
    for (u, st), _g in HOSTS:
        for y in range(2001, 2026):
            rows.append((u, st, f"{y}-01-01", 100.0 * (1 + GROWTH[u]) ** (y - 2001), 90.0, False, True))
    rows += [(9, "ZZ", "2004-01-01", 50.0, 40.0, True, False),           # not observed: no report
             (9, "ZZ", "2005-01-01", np.nan, 40.0, None, True),          # winter only, short form mark missing
             (9, "ZZ", "2006-01-01", np.nan, np.nan, False, None),       # neither peak; data_observed missing
             (9, "ZZ", "2007-01-01", 0.0, -1.0, True, True),             # nonpositive peaks are no report
             (88888, "TX", "2010-01-01", 5.0, 4.0, False, True),         # a repeated key
             (88888, "TX", "2010-01-01", 6.0, 3.0, False, True)]
    f = pd.DataFrame(rows, columns=list(cn.PEAK_COLUMNS))
    f["report_date"] = pd.to_datetime(f.report_date)
    f["short_form"] = pd.array(list(f.short_form), dtype="boolean")
    f["data_observed"] = pd.array(list(f.data_observed), dtype="boolean")
    f[REVENUE_COLUMN] = SENTINEL
    f["customers"] = 12345
    return f


@pytest.fixture
def world(tmp_path, monkeypatch):
    raw = tmp_path / "raw_peak_table_invented.parquet"
    raw_frame().to_parquet(raw, index=False)
    monkeypatch.setattr(cn, "PEAK_FILE", raw)
    calls = []
    original = cn.read_peaks

    def counted(*a, **k):
        calls.append((a, k))
        return original(*a, **k)
    monkeypatch.setattr(cn, "read_peaks", counted)
    writes = []
    real_pq, real_js = c4._write_parquet, c4._write_json
    monkeypatch.setattr(c4, "_write_parquet", lambda f, p: (writes.append(Path(p)), real_pq(f, p))[1])
    monkeypatch.setattr(c4, "_write_json", lambda o, p: (writes.append(Path(p)), real_js(o, p))[1])
    out = {"raw": raw, "retained": tmp_path / "out" / "condition4_peak_rows.parquet",
           "record": tmp_path / "out" / "condition4_peak_read_record.json", "calls": calls, "writes": writes,
           "tmp": tmp_path, "original": original}
    (tmp_path / "out").mkdir()
    return out


def read(world):
    return c4.read_once_and_retain(retained=world["retained"], record=world["record"], command="invented test")


def test_the_whole_path_on_the_invented_file_reads_once_with_the_default_reader_and_selects_seven_columns(world):
    doc = read(world)
    # the default reader (conditions.read_peaks, looked up when called) was called exactly once with no argument
    assert world["calls"] == [((), {})]
    assert list(doc["columns_selected"]) == list(cn.PEAK_COLUMNS) and len(cn.PEAK_COLUMNS) == 7
    assert doc["columns_retained"] == list(c4.PEAKS_AS_READ)
    assert doc["raw_file"]["sha256"] == hashlib.sha256(world["raw"].read_bytes()).hexdigest()
    assert doc["retained_file"]["sha256"] == hashlib.sha256(world["retained"].read_bytes()).hexdigest()
    assert doc["authorizing_words"] == c4.AUTHORIZING_WORDS and doc["command"] == "invented test"
    c = doc["counts"]
    assert c["rows"] == 4 * 25 + 6 and c["first_year"] == 2001 and c["last_year"] == 2025
    assert c["distinct_utility_state_pairs"] == 6
    assert c["rows_not_observed"] == 1                     # the one False; the missing data_observed reads as observed
    assert c["rows_with_a_peak"] == 100 + 2 + 1            # hosts; 88888 twice; 9 in 2005 (winter only)
    assert c["rows_marked_short_form"] == 2 and c["rows_with_the_short_form_mark_missing"] == 1
    assert c["rows_sharing_a_utility_state_year_key"] == 2 and c["repeated_utility_state_year_keys"] == 1


def test_neither_the_revenue_like_column_nor_its_sentinel_reaches_the_retained_file_or_the_record(world):
    read(world)
    stored = pd.read_parquet(world["retained"])
    assert list(stored.columns) == list(c4.PEAKS_AS_READ)
    assert not (stored.select_dtypes("number") == SENTINEL).any().any()
    text = world["record"].read_text()
    for needle in (REVENUE_COLUMN, "customers", repr(SENTINEL), "987654321"):
        assert needle not in text, needle
    blob = world["retained"].read_bytes()
    assert REVENUE_COLUMN.encode() not in blob and b"customers" not in blob
    assert np.float64(SENTINEL).tobytes() not in blob


def test_nothing_is_written_outside_tmp_path_and_only_the_two_named_files(world):
    doc = read(world)
    # the parquet goes to a temporary name in the same folder and is renamed into place, then the record is written
    assert world["writes"] == [c4._partial(world["retained"]), world["record"]]
    assert world["retained"].exists() and not c4._partial(world["retained"]).exists()
    assert doc["retained_file"]["representation"] == c4.NULLABLE and doc["usable_by_load_retained"] is True
    for p in world["writes"]:
        assert world["tmp"] in p.parents


def test_a_second_read_is_refused_in_words_and_the_reader_is_not_called_again(world):
    read(world)
    with pytest.raises(c4.SecondReadRefused, match="covers one read"):
        read(world)
    assert len(world["calls"]) == 1
    # either file alone is enough to refuse
    world["record"].unlink()
    with pytest.raises(c4.SecondReadRefused):
        read(world)
    assert len(world["calls"]) == 1


def test_the_round_trip_is_exact_with_missing_values_an_unobserved_row_a_winter_only_row_and_a_row_with_neither(world):
    read(world)
    back = c4.load_retained(world["retained"], world["record"])
    direct = world["original"](raw_frame())                     # read_peaks on the same rows in memory
    pd.testing.assert_frame_equal(back, direct, check_exact=True)
    z = back[back.utility_id_eia == 9].set_index("year")
    assert np.isnan(z.peak_mw[2004]) and not bool(z.data_observed[2004])        # unobserved: no report
    assert z.peak_mw[2005] == 40.0 and z.short_form[2005] is pd.NA               # winter only; mark missing
    assert np.isnan(z.peak_mw[2006]) and bool(z.data_observed[2006])             # neither; missing observed reads True
    assert np.isnan(z.peak_mw[2007])
    assert back.short_form.dtype == object                                       # read_peaks' own representation


def test_the_round_trip_without_any_missing_short_form_keeps_the_bool_representation(world, monkeypatch):
    f = raw_frame()
    f["short_form"] = pd.array([False] * len(f), dtype="boolean")
    f.to_parquet(world["raw"], index=False)
    read(world)
    back = c4.load_retained(world["retained"], world["record"])
    assert back.short_form.dtype == bool
    pd.testing.assert_frame_equal(back, world["original"](f), check_exact=True)


def test_load_retained_refuses_a_changed_file_and_never_falls_back_to_the_raw_file(world, monkeypatch):
    read(world)
    stored = pd.read_parquet(world["retained"])
    stored.loc[0, "peak_mw"] = stored.loc[0, "peak_mw"] + 1.0
    stored.to_parquet(world["retained"], index=False)
    monkeypatch.setattr(cn, "read_peaks", lambda *a, **k: pytest.fail("the raw file was read as a fallback"))
    with pytest.raises(c4.RetainedRefused, match="sha256"):
        c4.load_retained(world["retained"], world["record"])


def test_load_retained_says_the_read_has_not_been_made_when_the_file_is_absent(world, monkeypatch):
    monkeypatch.setattr(cn, "read_peaks", lambda *a, **k: pytest.fail("the raw file was read as a fallback"))
    with pytest.raises(c4.RetainedAbsent, match="has not been made"):
        c4.load_retained(world["retained"], world["record"])


def test_the_retained_frame_gives_the_same_condition_4_grouping_as_the_frame_read_directly(world):
    from pipeline.electricity import succession as succ
    read(world)
    back = c4.load_retained(world["retained"], world["record"])
    direct = world["original"](raw_frame())
    panel = pd.DataFrame([(u, st, y, 1000.0) for (u, st), _ in HOSTS for y in range(2001, 2026)],
                         columns=ps.KEY + ["year", "res_customers"])
    none = pd.DataFrame(columns=succ.COLUMNS).astype({"predecessor_id": "Int64", "successor_id": "Int64"})
    g1 = cn.past_utilization_grouping(HOSTS, back, set(), panel, succession=none)
    g2 = cn.past_utilization_grouping(HOSTS, direct, set(), panel, succession=none)
    assert g1.member == g2.member and g1.extra == g2.extra and g1.value == g2.value
    assert len(g1.member) == 4                                   # every invented host is classifiable
    assert sorted(k for k, v in g1.member.items() if v) == ["3:AC", "4:AD"]


def test_a_reader_returning_other_columns_is_retained_recorded_and_refused_by_the_loader(world):
    n = []

    def bad():
        n.append(1)
        return world["original"](raw_frame()).assign(extra=1)
    doc = c4.read_once_and_retain(retained=world["retained"], record=world["record"], reader=bad)
    assert len(n) == 1 and world["retained"].exists() and world["record"].exists()
    assert doc["usable_by_load_retained"] is False and "not exactly" in doc["problems_in_words"][0]
    assert list(pd.read_parquet(world["retained"]).columns) == list(c4.PEAKS_AS_READ)    # the extra column not stored
    with pytest.raises(c4.RetainedRefused, match="not a second read"):
        c4.load_retained(world["retained"], world["record"])


def test_a_raw_file_other_than_conditions_peak_file_is_refused(world):
    other = world["tmp"] / "other.parquet"
    raw_frame().to_parquet(other, index=False)
    with pytest.raises(c4.PathRefused, match="not conditions.PEAK_FILE"):
        c4.read_once_and_retain(retained=world["retained"], record=world["record"], raw_file=other)
    assert world["calls"] == []


def test_the_path_guard_refuses_raw_and_blind_by_text_and_passes_others(tmp_path, monkeypatch):
    import os
    touched = []
    monkeypatch.setattr(os, "stat", lambda *a, **k: touched.append(a) or pytest.fail("the guard touched the file system"))
    for p in ("data/raw/x.parquet", "data/blind/outcomes_by_unit/1_AA.parquet", "/no/such/Data/Raw/y",
              "data/interim/../raw/z.parquet", str(ROOT / "data" / "blind")):
        with pytest.raises(c4.PathRefused):
            c4.refuse_raw_or_blind(p)
    for p in ("data/interim/panel_quantities.parquet", "data/frozen/x.json", "pipeline/raw/x.py", "rawdata/blind.txt"):
        assert c4.refuse_raw_or_blind(p).is_absolute()
    assert touched == []


def test_the_retained_and_record_paths_are_guarded_too(world):
    with pytest.raises(c4.PathRefused):
        c4.read_once_and_retain(retained=world["tmp"] / "data" / "raw" / "r.parquet", record=world["record"])
    with pytest.raises(c4.PathRefused):
        c4.load_retained(world["tmp"] / "data" / "blind" / "r.parquet", world["record"])
    assert world["calls"] == []


def test_main_without_the_flag_reads_nothing(world, capsys, monkeypatch):
    monkeypatch.setattr(c4, "read_once_and_retain", lambda **k: pytest.fail("read without --read-once"))
    assert c4.main([]) == 0
    assert "Nothing read" in capsys.readouterr().out
    assert world["calls"] == []


def test_the_authorizing_words_are_copied_exactly_from_the_handover():
    lines = (ROOT / "HANDOVER_session27_2026-11-20.md").read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("**His acceptance and one narrow exception"))
    block, i = [], start + 2
    while i < len(lines) and lines[i].startswith(">"):
        block.append(lines[i][2:] if lines[i].startswith("> ") else lines[i][1:])
        i += 1
    assert "\n".join(block) == c4.AUTHORIZING_WORDS


def test_the_six_columns_are_what_read_peaks_returns_and_what_the_registry_takes():
    f = cn.read_peaks(raw_frame())
    assert tuple(f.columns) == c4.PEAKS_AS_READ
    from pipeline.analysis import run_outcomes as ro
    assert tuple(ro.PEAKS_AS_READ) == c4.PEAKS_AS_READ          # present since the registry owner's change of session 27


def test_the_record_is_json_with_counts_and_no_peak_value(world):
    doc = read(world)
    on_disk = json.loads(world["record"].read_text())
    assert on_disk == doc
    flat = json.dumps(on_disk["counts"])
    assert "100.0" not in flat and "40.0" not in flat


# ---- the one read is never lost (the coordinator's instruction of 2026-11-20) -------------------------------------------

def after_failure(world, doc=None):
    """What must hold after any failure once reader() has returned: the frame is on disk under tmp_path, the reader was
    called exactly once, and a second call is refused without reading again."""
    on_disk = [p for p in (world["retained"], c4._pickled(world["retained"])) if p.exists()]
    assert on_disk and all(world["tmp"] in p.parents for p in on_disk)
    assert world["calls"] == [((), {})]
    with pytest.raises(c4.SecondReadRefused):
        read(world)
    assert len(world["calls"]) == 1


def test_a_failing_nullable_write_falls_back_to_text_and_the_loader_restores_it(world, monkeypatch):
    real = c4._write_parquet
    seen = []

    def first_fails(f, p):
        seen.append(p)
        if len(seen) == 1:
            raise TypeError("invented: this dtype cannot be written")
        return real(f, p)
    monkeypatch.setattr(c4, "_write_parquet", first_fails)
    doc = read(world)
    assert doc["retained_file"]["representation"] == c4.TEXT
    assert doc["retained_file"]["representations_that_failed_before_it"] == [f"{c4.NULLABLE}: TypeError"]
    assert doc["retained_file"]["reads_back_equal"] is True and doc["usable_by_load_retained"] is True
    stored = pd.read_parquet(world["retained"])
    assert set(stored.short_form) == {"True", "False", ""}
    pd.testing.assert_frame_equal(c4.load_retained(world["retained"], world["record"]), world["original"](raw_frame()),
                                  check_exact=True)
    after_failure(world)


def test_both_parquet_writes_failing_leave_a_pickle_the_loader_restores(world, monkeypatch):
    monkeypatch.setattr(c4, "_write_parquet", lambda f, p: (_ for _ in ()).throw(OSError("invented")))
    doc = read(world)
    assert doc["retained_file"]["representation"] == c4.PICKLE
    assert doc["retained_file"]["path"].endswith(".pkl") and not world["retained"].exists()
    assert len(doc["retained_file"]["representations_that_failed_before_it"]) == 2
    pd.testing.assert_frame_equal(c4.load_retained(world["retained"], world["record"]), world["original"](raw_frame()),
                                  check_exact=True)
    after_failure(world)


def test_every_representation_failing_raises_in_words_after_one_read(world, monkeypatch):
    monkeypatch.setattr(c4, "_write_parquet", lambda f, p: (_ for _ in ()).throw(OSError("invented")))
    monkeypatch.setattr(c4, "_write_pickle", lambda f, p: (_ for _ in ()).throw(OSError("invented")))
    with pytest.raises(RuntimeError, match="could not be stored in any representation"):
        read(world)
    assert world["calls"] == [((), {})] and not world["record"].exists()


def test_a_read_back_that_differs_is_recorded_in_words_with_no_value_and_the_loader_refuses(world, monkeypatch, capsys):
    real = c4._from_storage

    def changed(stored, rep=c4.NULLABLE):
        f = real(stored, rep)
        f.loc[0, "peak_mw"] = f.loc[0, "peak_mw"] + 1.25
        return f
    monkeypatch.setattr(c4, "_from_storage", changed)
    doc = read(world)
    assert doc["retained_file"]["reads_back_equal"] is False and doc["usable_by_load_retained"] is False
    words = "; ".join(doc["problems_in_words"])
    assert "column peak_mw: 1 rows differ" in words and "rows that differ in some common column: 1 of 106" in words
    text = world["record"].read_text() + capsys.readouterr().out
    assert "101.25" not in text and "100.0" not in text
    assert "needs a look before use" in text
    monkeypatch.setattr(c4, "_from_storage", real)
    with pytest.raises(c4.RetainedRefused, match="needs repair of the loader, not a second read"):
        c4.load_retained(world["retained"], world["record"])
    after_failure(world)


def test_a_read_back_that_raises_is_recorded_and_the_frame_kept(world, monkeypatch):
    monkeypatch.setattr(c4, "_from_storage", lambda *a, **k: (_ for _ in ()).throw(ValueError("invented")))
    doc = read(world)
    assert doc["retained_file"]["reads_back_equal"] is False
    assert any("read-back itself failed (ValueError)" in p for p in doc["problems_in_words"])
    after_failure(world)


def test_a_failing_record_write_prints_the_record_and_raises_with_the_frame_kept(world, monkeypatch, capsys):
    monkeypatch.setattr(c4, "_write_json", lambda o, p: (_ for _ in ()).throw(OSError("invented: disk full")))
    with pytest.raises(OSError, match="disk full"):
        read(world)
    out = capsys.readouterr().out
    assert "THE RECORD COULD NOT BE WRITTEN" in out
    printed = json.loads(out[out.index("{"):])
    assert printed["counts"]["rows"] == 106 and printed["retained_file"]["reads_back_equal"] is True
    assert not world["record"].exists()
    with pytest.raises(c4.RetainedAbsent, match="no second read is needed"):
        c4.load_retained(world["retained"], world["record"])
    after_failure(world)


def test_a_leftover_partial_file_also_refuses_a_second_read(world):
    c4._partial(world["retained"]).write_bytes(b"partial")
    with pytest.raises(c4.SecondReadRefused, match="partly written"):
        read(world)
    assert world["calls"] == []
