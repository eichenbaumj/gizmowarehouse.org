"""The usable flag reader (D-94, "The usable flag's source"; D-95 section 3 item 5). Invented quantities files only.

The owner's words govern: read the required columns explicitly; missing unit-years are unusable; missing or malformed
flags and duplicate keys stop for correction rather than being silently coerced; rely on the accepted audit's recorded
checks without reopening its protected artifacts; report exclusions without price or revenue values.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import usable_flag as uf  # noqa: E402
from pipeline.electricity import availability_codes as av  # noqa: E402

SECRET = 123.456789          # a made-up "price": it must never appear in any message or output

# Every file opened from Python in this process, while a test holds a list here. The reader opens the quantities
# file through Python's open, so the hook sees it; a native open under the guarded directory fails on its permissions.
_SINK: dict = {"opened": None}


def _hook(event, args):
    if event == "open" and _SINK["opened"] is not None and args and isinstance(args[0], (str, bytes, os.PathLike)):
        _SINK["opened"].append(os.fsdecode(args[0]))


sys.addaudithook(_hook)


def rows(n_units=3, years=range(2009, 2019)):
    """An invented quantities frame: keys, the flag, the reason, and columns the reader must never read."""
    out = []
    for u in range(1, n_units + 1):
        for y in years:
            out.append({"utility_id_eia": u, "state": "AA", "year": y, av.FLAG_COL: True, av.REASON_COL: av.NO_EXCLUSION,
                        "res_mwh": 1.0, "res_price_secret": SECRET, "ownership": "cooperative"})
    return pd.DataFrame(out)


def write(tmp_path, frame, name="panel_quantities.parquet", schema=None):
    path = tmp_path / "interim" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False, schema=schema)
    pq.write_table(table, path)
    return path


def mark(frame, key, reason):
    i = (frame.utility_id_eia == key[0]) & (frame.state == key[1]) & (frame.year == key[2])
    frame.loc[i, av.FLAG_COL] = False
    frame.loc[i, av.REASON_COL] = reason
    return frame


# ---- the happy path --------------------------------------------------------------------------------

def test_returns_the_usable_unit_years_in_the_form_design_build_takes(tmp_path):
    f = mark(rows(), (2, "AA", 2012), "under_customer_floor")
    path = write(tmp_path, f)
    got = uf.read(path)
    assert isinstance(got.usable, set) and len(got.usable) == len(f) - 1
    assert (2, "AA", 2012) not in got.usable and (2, "AA", 2011) in got.usable
    assert all(isinstance(u, int) and isinstance(s, str) and isinstance(y, int) for u, s, y in got.usable)
    assert got.reason[(2, "AA", 2012)] == "under_customer_floor"
    assert got.rows == len(f)


def test_reads_only_the_key_flag_and_reason_columns(tmp_path, monkeypatch):
    path = write(tmp_path, rows())
    seen = {}
    real = pd.read_parquet

    def spy(p, *a, **k):
        seen["columns"] = list(k.get("columns") or [])
        return real(p, *a, **k)

    monkeypatch.setattr(uf.pd, "read_parquet", spy)
    uf.read(path)
    assert seen["columns"] == list(av.KEYS) + [av.FLAG_COL, av.REASON_COL]
    assert list(uf.READ_COLUMNS) == list(av.KEYS) + [av.FLAG_COL, av.REASON_COL]


def test_the_constants_are_imported_not_copied():
    src = (Path(uf.__file__)).read_text()
    assert '"res_price_usable"' not in src and '"res_price_first_exclusion_reason"' not in src
    assert "av.FLAG_COL" in src and "av.REASON_COL" in src and "av.KEYS" in src


def test_the_default_path_is_the_panel_loaders_quantities_file():
    from pipeline.electricity import panel
    assert uf.QUANTITIES == panel.INTERIM / "panel_quantities.parquet"


# ---- stops for correction --------------------------------------------------------------------------

def test_a_missing_required_column_stops_and_names_it(tmp_path):
    path = write(tmp_path, rows().drop(columns=[av.REASON_COL]))
    with pytest.raises(uf.UsableFlagError, match=rf"missing .*{av.REASON_COL}"):
        uf.read(path)


def test_a_null_flag_stops_with_its_count_and_is_never_read_as_false(tmp_path):
    f = rows()
    f[av.FLAG_COL] = f[av.FLAG_COL].astype(object)
    f.loc[[0, 5], av.FLAG_COL] = None
    path = write(tmp_path, f, schema=pa.schema([("utility_id_eia", pa.int64()), ("state", pa.string()), ("year", pa.int32()),
                                                (av.FLAG_COL, pa.bool_()), (av.REASON_COL, pa.string()), ("res_mwh", pa.float64()),
                                                ("res_price_secret", pa.float64()), ("ownership", pa.string())]))
    with pytest.raises(uf.UsableFlagError, match=r"2 rows have no .*flag"):
        uf.read(path)


@pytest.mark.parametrize("bad", ["integers", "strings"])
def test_a_flag_that_is_not_strictly_boolean_stops(tmp_path, bad):
    f = rows()
    f[av.FLAG_COL] = 1 if bad == "integers" else "True"
    path = write(tmp_path, f)
    with pytest.raises(uf.UsableFlagError, match=r"not strictly true or false"):
        uf.read(path)


def test_duplicate_keys_stop_with_their_count(tmp_path):
    f = rows()
    f = pd.concat([f, f.iloc[[3, 4]]], ignore_index=True)
    path = write(tmp_path, f)
    with pytest.raises(uf.UsableFlagError, match=r"4 rows repeat a key \(utility_id_eia, state, year\).*over 2 repeated keys"):
        uf.read(path)


def test_a_reason_outside_the_fixed_list_stops(tmp_path):
    f = mark(rows(), (1, "AA", 2010), "made_up_reason")
    path = write(tmp_path, f)
    with pytest.raises(uf.UsableFlagError, match=r"1 rows? .*not in the fixed list"):
        uf.read(path)


def test_a_null_reason_stops(tmp_path):
    f = rows()
    f.loc[2, av.REASON_COL] = None
    path = write(tmp_path, f)
    with pytest.raises(uf.UsableFlagError, match=r"1 rows? have no first exclusion reason"):
        uf.read(path)


def test_a_flag_that_disagrees_with_its_reason_stops(tmp_path):
    f = rows()
    f.loc[1, av.REASON_COL] = "under_customer_floor"          # flag still True
    path = write(tmp_path, f)
    with pytest.raises(uf.UsableFlagError, match=r"1 rows? .*disagree"):
        uf.read(path)


def test_a_null_key_stops(tmp_path):
    f = rows()
    f["state"] = f["state"].astype(object)
    f.loc[0, "state"] = None
    path = write(tmp_path, f)
    with pytest.raises(uf.UsableFlagError, match=r"1 rows? .*no utility_id_eia, state or year"):
        uf.read(path)


def test_no_error_message_carries_a_value_of_another_column(tmp_path):
    for mutate in (lambda f: pd.concat([f, f.iloc[[0]]], ignore_index=True),
                   lambda f: mark(f, (1, "AA", 2010), "made_up_reason")):
        path = write(tmp_path, mutate(rows()))
        with pytest.raises(uf.UsableFlagError) as e:
            uf.read(path)
        assert str(SECRET) not in str(e.value) and "123.45" not in str(e.value)


# ---- the protected artifacts stay closed -------------------------------------------------------------

def test_the_reader_never_opens_anything_under_the_availability_directory(tmp_path):
    """A temp tree with a mask beside the quantities file: every file opened in-process is recorded, and the
    availability directory is made unreadable, so an attempt to open the mask would also fail loudly."""
    path = write(tmp_path, mark(rows(), (3, "AA", 2015), "no_residential_sales"))
    guarded = tmp_path / "interim" / "availability"
    guarded.mkdir()
    pq.write_table(pa.table({"usable": [True]}), guarded / "mask.parquet")
    (guarded / "sidecar.json").write_text("{}")
    opened: list[str] = []
    _SINK["opened"] = opened
    os.chmod(guarded, 0)
    try:
        got = uf.read(path)
        rep = uf.report(got, [((3, "AA"), 2016)])
    finally:
        os.chmod(guarded, 0o700)
        _SINK["opened"] = None
    assert any(p.endswith("panel_quantities.parquet") for p in opened), "the hook did not see the read, so the test proves nothing"
    assert not [p for p in opened if "availability" in p], opened
    assert rep["hosts_without_a_full_window"][0]["utility"] == "3:AA"


def test_the_module_names_no_availability_artifact():
    src = Path(uf.__file__).read_text()
    code = "\n".join(ln for ln in src.split("\n") if not ln.lstrip().startswith("#"))
    body = code.split('"""', 2)[2]                                  # past the module docstring, which describes the bar
    assert "interim/availability" not in body and "/ \"availability\"" not in body and "mask" not in body.lower()


# ---- the report: who lacks a full window, with reason codes only -------------------------------------

def test_report_names_units_without_a_full_window_and_the_reason_per_missing_year(tmp_path):
    f = rows(n_units=3)
    f = mark(f, (1, "AA", 2011), "under_customer_floor")
    f = mark(f, (1, "AA", 2014), "price_not_above_zero")
    f = f[~((f.utility_id_eia == 2) & (f.year == 2018))]                 # a unit-year with no row is unusable
    got = uf.read(write(tmp_path, f))
    rep = uf.report(got, [((1, "AA"), 2015), ((2, "AA"), 2015), ((3, "AA"), 2015)], role="host")
    by = {r["utility"]: r for r in rep["hosts_without_a_full_window"]}
    assert set(by) == {"1:AA", "2:AA"}
    assert by["1:AA"]["missing_years"] == [{"year": 2011, "first_exclusion_reason": "under_customer_floor"},
                                           {"year": 2014, "first_exclusion_reason": "price_not_above_zero"}]
    assert by["2:AA"]["missing_years"] == [{"year": 2018, "first_exclusion_reason": av.NOT_IN_PANEL}]
    assert rep["units_checked"] == 3 and rep["with_a_full_window"] == 1
    assert rep["missing_unit_years_by_first_exclusion_reason"] == {"under_customer_floor": 1, "price_not_above_zero": 1,
                                                                   av.NOT_IN_PANEL: 1}
    flat = repr(rep)
    assert str(SECRET) not in flat and "res_mwh" not in flat


def test_report_counts_a_unit_once_per_cohort_window(tmp_path):
    got = uf.read(write(tmp_path, rows(n_units=1, years=range(2005, 2020))))
    rep = uf.report(got, [((1, "AA"), 2012), ((1, "AA"), 2016)], role="comparison")
    assert rep["comparisons_without_a_full_window"] == [] and rep["units_checked"] == 2
    rep = uf.report(got, [((1, "AA"), 2018)], role="comparison")          # window 2012 to 2021, the file ends in 2019
    assert [m["year"] for m in rep["comparisons_without_a_full_window"][0]["missing_years"]] == [2020, 2021]


def test_validate_frame_is_the_same_check_on_a_frame_in_memory():
    f = rows()
    got = uf.validate(f[list(uf.READ_COLUMNS)])
    assert len(got.usable) == len(f)
    with pytest.raises(uf.UsableFlagError):
        uf.validate(pd.concat([f, f.iloc[[0]]])[list(uf.READ_COLUMNS)])
    assert np.isfinite(len(got.reason))
