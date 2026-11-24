"""The reshaper for the specified outcome frames (pipeline/analysis/outcome_frames.py). Invented inputs only.

One invented world: three utility-states (11:AA, 22:AB, 33:BA) over 2015 to 2017, an outcome frame with every column the
panel's outcome file carries (panel.build's outcome_cols), a quantity frame with res_customers, and an invented CPI-U
table turned into factors by reconciliation_c.cpi_factors_to_2024. Every value is planted from a formula, so each frame's
answer is known. Tolerances: the levels must be exactly equal; the log and the deflation within 1e-12 (relative for the
deflation), well above float rounding and far below any difference that matters.

No file under data/ is read. The plan is frozen at commit ea426c4; no host utility's price in the outcome data has been
read, with one lapse in source access disclosed in the plan qualifying that statement.
"""
from __future__ import annotations

import builtins
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import outcome_frames as of  # noqa: E402
from pipeline.analysis import reconciliation_c as rc  # noqa: E402
from pipeline.analysis import reconciliation_mu as rmu  # noqa: E402
from pipeline.analysis import supplementary_outcomes as so  # noqa: E402

UNITS = [(11, "AA"), (22, "AB"), (33, "BA")]
YEARS = [2015, 2016, 2017]
LOG_TOL = 1e-12
SENTINEL = 12345.678
SENTINEL_DIGITS = ("12345", "2345.6", "345.678", "9.421")      # the value, and the start of its natural log (9.4211...)
OUTCOME_COLS_FROM_FILE = ("res_price", "res_price_default_service", "res_bill_per_customer_month",
                          "res_kwh_per_customer_month")


def ro():
    """run_outcomes, imported when a test needs it (another agent may be editing it; a failed import fails only the
    tests that use it)."""
    from pipeline.analysis import run_outcomes
    return run_outcomes


# ---- the invented world ------------------------------------------------------------------------------------------------

def price(i, y):
    return 10.0 + i + 0.5 * (y - 2015)


def outcomes_frame():
    rows = []
    for i, (u, st) in enumerate(UNITS):
        for y in YEARS:
            p = price(i, y)
            rows.append({"utility_id_eia": u, "state": st, "year": y,
                         "res_revenue_full": 1_000_000.0 * (i + 1) + y,
                         "res_price": p,
                         "res_price_delivery_only": p - 6.0,
                         "res_price_default_service": p - 0.25,
                         "res_bill_per_customer_month": 100.0 + 10 * i + (y - 2015),
                         "res_kwh_per_customer_month": 900.0 + 7 * i - (y - 2015),
                         "energy_price_state": 55.0 + i})
    f = pd.DataFrame(rows, columns=list(of.OUTCOME_FILE_COLUMNS))
    f["year"] = f.year.astype("int32")                 # as the quantity file carries it
    return f


def quantities_frame():
    rows = [(u, st, y, 5_000 + 1_000 * i + (y - 2015)) for i, (u, st) in enumerate(UNITS) for y in YEARS]
    q = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "res_customers"])
    q["year"] = q.year.astype("int32")
    q["res_customers"] = q.res_customers.astype("Int64")   # the quantity file's nullable integer
    return q


CPI = {2014: 230.0, 2015: 240.0, 2016: 250.0, 2017: 256.0, 2018: 260.0, 2019: 264.0, 2020: 268.0, 2021: 280.0,
       2022: 290.0, 2023: 296.0, 2024: 300.0, 2025: 310.0}


def factors():
    t = pd.DataFrame({"year": list(CPI), "cpi_u": list(CPI.values())})
    return rc.cpi_factors_to_2024(t)


def run(o=None, q=None, f=None):
    return of.reshape(outcomes_frame() if o is None else o, quantities_frame() if q is None else q,
                      factors() if f is None else f)


def by_key(frame):
    return {(int(u), s, int(y)): v for u, s, y, v in frame[of.FRAME_COLUMNS].itertuples(index=False)}


def source_by_key(frame, column):
    return {(int(u), s, int(y)): float(v) for u, s, y, v in frame[["utility_id_eia", "state", "year", column]]
            .itertuples(index=False)}


def assert_types(frame):
    assert list(frame.columns) == of.FRAME_COLUMNS
    assert frame.utility_id_eia.dtype == np.int64
    assert frame.year.dtype == np.int64
    assert frame.value.dtype == np.float64
    assert frame.state.dtype == object
    assert all(type(s) is str for s in frame.state)


# ---- names -------------------------------------------------------------------------------------------------------------

def test_names_are_the_registrys():
    r = ro()
    assert of.NAMES == r.OUTCOMES
    assert (of.PRICE, of.KWH, of.BILL, of.CUSTOMERS) == (r.PRICE, r.KWH, r.BILL, r.CUSTOMERS)
    assert (of.PRICE_DEFAULT_SERVICE, of.PRICE_DELIVERY_INCLUSIVE, of.PRICE_CENTS_REAL_2024) == (
        r.PRICE_DEFAULT_SERVICE, r.PRICE_DELIVERY_INCLUSIVE, r.PRICE_CENTS_REAL_2024)
    assert of.VALUE == r.OUTCOME and of.KEY == list(r.KEY)


def test_every_frame_is_built_on_the_clean_world_with_its_types():
    res = run()
    assert set(res.frames) == set(of.NAMES) == set(res.report)
    for name, f in res.frames.items():
        assert_types(f)
        assert len(f) == 9
        rec = res.report[name]
        assert rec["built"] is True and rec["reason_not_built"] is None
        assert rec["rows_in"] == 9 and rec["rows_out"] == 9
        assert rec["values_missing"] == rec["values_not_finite"] == rec["values_not_positive"] == 0


# ---- the seven constructions, column by column ---------------------------------------------------------------------------

def test_log_price_is_the_natural_log_of_res_price():
    o = outcomes_frame()
    f = run(o=o).frames[of.PRICE]
    src = source_by_key(o, "res_price")
    got = by_key(f)
    assert set(got) == set(src)
    for k, v in got.items():
        assert abs(v - np.log(src[k])) < LOG_TOL
    # A known answer by hand: 11:AA in 2016 has res_price 10.5.
    assert abs(got[(11, "AA", 2016)] - np.log(10.5)) < LOG_TOL
    rec = run(o=o).report[of.PRICE]
    assert rec["source_column"] == "res_price" and rec["transformation"] == of.LOG
    assert "cents per kWh" in rec["source_unit"]


@pytest.mark.parametrize("name,column", [(of.PRICE_DEFAULT_SERVICE, "res_price_default_service"),
                                         (of.PRICE_DELIVERY_INCLUSIVE, "res_price"),
                                         (of.KWH, "res_kwh_per_customer_month"),
                                         (of.BILL, "res_bill_per_customer_month")])
def test_level_frames_are_the_source_column_untouched(name, column):
    o = outcomes_frame()
    res = run(o=o)
    assert by_key(res.frames[name]) == source_by_key(o, column)          # exact
    assert res.report[name]["source_column"] == column
    assert res.report[name]["transformation"] == of.LEVEL


def test_units_in_the_report():
    rep = run().report
    assert rep[of.KWH]["unit"] == "kWh per residential customer per month"
    assert rep[of.BILL]["unit"] == "nominal dollars per residential customer per month"
    assert "no price index" in rep[of.BILL]["source_unit"]
    assert rep[of.CUSTOMERS]["unit"] == "residential customers, a count"
    assert rep[of.PRICE_DEFAULT_SERVICE]["unit"] == "cents per kWh, nominal"
    assert rep[of.PRICE_CENTS_REAL_2024]["unit"] == rc.PRICE_SERIES_REAL_UNIT
    assert rep[of.PRICE_CENTS_REAL_2024]["label"] == rc.PRICE_SERIES_LABEL
    assert "balanced" in rep[of.PRICE_CENTS_REAL_2024]["left_to_the_row"]


def test_real_2024_price_is_res_price_times_the_years_factor():
    o = outcomes_frame()
    fac = factors()
    assert fac[2015] == pytest.approx(1.25, abs=1e-15)                     # 300 / 240
    got = by_key(run(o=o, f=fac).frames[of.PRICE_CENTS_REAL_2024])
    src = source_by_key(o, "res_price")
    for (u, s, y), v in got.items():
        want = src[(u, s, y)] * CPI[2024] / CPI[y]
        assert abs(v - want) <= LOG_TOL * abs(want)
    assert abs(got[(11, "AA", 2015)] - 12.5) <= LOG_TOL * 12.5             # 10.0 cents x 1.25
    assert got[(11, "AA", 2015)] != src[(11, "AA", 2015)]                  # deflated, not the nominal level


def test_customers_come_from_the_quantity_frame_even_when_the_outcome_frame_has_the_column():
    o = outcomes_frame().assign(res_customers=1.0)                         # a decoy of the same name
    q = quantities_frame()
    got = by_key(run(o=o, q=q).frames[of.CUSTOMERS])
    want = {(int(u), s, int(y)): float(c) for u, s, y, c in q.itertuples(index=False)}
    assert got == want
    assert all(v >= 5000 for v in got.values())
    assert run(o=o, q=q).report[of.CUSTOMERS]["source"].startswith("the panel's quantity file")


def test_customers_without_the_column_in_the_quantity_frame_stop_only_that_frame():
    o = outcomes_frame().assign(res_customers=1.0)
    res = run(o=o, q=quantities_frame().drop(columns="res_customers"))
    assert of.CUSTOMERS not in res.frames
    assert "res_customers" in res.report[of.CUSTOMERS]["reason_not_built"]
    assert set(res.frames) == set(of.NAMES) - {of.CUSTOMERS}


# ---- key types -----------------------------------------------------------------------------------------------------------

def test_id_int32_becomes_int64():
    o = outcomes_frame().astype({"utility_id_eia": "int32"})
    res = run(o=o)
    assert set(res.frames) == set(of.NAMES)
    for f in res.frames.values():
        assert_types(f)


def test_id_float_whole_is_accepted_as_int64():
    o = outcomes_frame().astype({"utility_id_eia": "float64"})
    res = run(o=o)
    assert set(res.frames) == set(of.NAMES)
    assert sorted(set(res.frames[of.PRICE].utility_id_eia)) == [11, 22, 33]
    assert_types(res.frames[of.PRICE])


def test_id_float_not_whole_is_refused_and_not_truncated():
    o = outcomes_frame().astype({"utility_id_eia": "float64"})
    o.loc[0, "utility_id_eia"] = 11.5
    res = run(o=o)
    outcome_file_frames = [n for n in of.NAMES if of.SPECS[n].source == of.OUTCOME_FILE]
    for n in outcome_file_frames:
        assert n not in res.frames
        assert "not a whole number" in res.report[n]["reason_not_built"]
    assert set(res.frames) == {of.CUSTOMERS}                                # the quantity frame's own frame survives


def test_missing_id_or_year_is_refused():
    o = outcomes_frame().astype({"utility_id_eia": "float64"})
    o.loc[1, "utility_id_eia"] = np.nan
    assert set(run(o=o).frames) == {of.CUSTOMERS}
    q = quantities_frame().astype({"year": "Int64"})
    q.loc[2, "year"] = pd.NA
    res = run(q=q)
    assert of.CUSTOMERS not in res.frames and "no year" in res.report[of.CUSTOMERS]["reason_not_built"]


def test_boolean_id_is_refused():
    o = outcomes_frame()
    o["utility_id_eia"] = [True, False, True] * 3
    assert set(run(o=o).frames) == {of.CUSTOMERS}


def test_nullable_integer_year_without_missing_is_accepted():
    q = quantities_frame().astype({"year": "Int64", "utility_id_eia": "Int64"})
    f = run(q=q).frames[of.CUSTOMERS]
    assert_types(f)


@pytest.mark.parametrize("kind", ["category", "string"])
def test_categorical_or_pandas_string_state_becomes_plain_str(kind):
    o = outcomes_frame().astype({"state": kind})
    q = quantities_frame().astype({"state": kind})
    res = run(o=o, q=q)
    assert set(res.frames) == set(of.NAMES)
    for f in res.frames.values():
        assert_types(f)
        assert set(f.state) == {"AA", "AB", "BA"}


def test_missing_state_is_refused():
    o = outcomes_frame()
    o.loc[4, "state"] = None
    res = run(o=o)
    assert set(res.frames) == {of.CUSTOMERS}
    assert "no state" in res.report[of.PRICE]["reason_not_built"]


def test_state_that_is_not_text_is_refused():
    q = quantities_frame()
    q["state"] = [1] * 9
    res = run(q=q)
    assert of.CUSTOMERS not in res.frames and "not text" in res.report[of.CUSTOMERS]["reason_not_built"]


def test_year_as_a_string_is_refused_not_parsed():
    o = outcomes_frame()
    o["year"] = o.year.astype(str)
    res = run(o=o)
    assert set(res.frames) == {of.CUSTOMERS}
    assert "never parsed from text" in res.report[of.PRICE]["reason_not_built"]
    o2 = outcomes_frame()
    o2["year"] = o2.year.astype("string")
    assert set(run(o=o2).frames) == {of.CUSTOMERS}


def test_a_source_that_is_not_a_frame_stops_only_its_own_frames():
    res = of.reshape({"res_price": [1.0]}, quantities_frame(), factors())
    assert set(res.frames) == {of.CUSTOMERS}
    assert "not a DataFrame" in res.report[of.PRICE]["reason_not_built"]
    res = of.reshape(outcomes_frame(), None, factors())
    assert set(res.frames) == set(of.NAMES) - {of.CUSTOMERS}


# ---- duplicates, missing columns, factors ----------------------------------------------------------------------------------

def test_a_repeated_unit_year_in_the_outcome_frame_stops_its_frames_with_the_count():
    o = outcomes_frame()
    o = pd.concat([o, o.iloc[[3]]], ignore_index=True)
    res = run(o=o)
    assert set(res.frames) == {of.CUSTOMERS}
    msg = res.report[of.PRICE]["reason_not_built"]
    assert "2 rows repeat a unit-year (1 repeated keys)" in msg and "22:AB in 2015" in msg


def test_a_repeated_unit_year_in_the_quantity_frame_stops_customers_only():
    q = quantities_frame()
    q = pd.concat([q, q.iloc[[0, 0]]], ignore_index=True)
    res = run(q=q)
    assert set(res.frames) == set(of.NAMES) - {of.CUSTOMERS}
    assert "3 rows repeat a unit-year (2 repeated keys)" in res.report[of.CUSTOMERS]["reason_not_built"]


FED_BY = {"res_price": {of.PRICE, of.PRICE_DELIVERY_INCLUSIVE, of.PRICE_CENTS_REAL_2024},
          "res_price_default_service": {of.PRICE_DEFAULT_SERVICE},
          "res_kwh_per_customer_month": {of.KWH},
          "res_bill_per_customer_month": {of.BILL}}


@pytest.mark.parametrize("column", sorted(FED_BY))
def test_each_missing_source_column_stops_only_the_frames_built_from_it(column):
    res = run(o=outcomes_frame().drop(columns=column))
    assert set(res.frames) == set(of.NAMES) - FED_BY[column]
    for n in FED_BY[column]:
        assert res.report[n]["built"] is False
        assert repr(column) in res.report[n]["reason_not_built"]


@pytest.mark.parametrize("column", ["utility_id_eia", "state", "year"])
def test_a_missing_key_column_stops_the_sources_frames(column):
    res = run(o=outcomes_frame().drop(columns=column))
    assert set(res.frames) == {of.CUSTOMERS}
    assert "no key column" in res.report[of.PRICE]["reason_not_built"]


def test_the_other_outcome_file_columns_are_not_needed():
    o = outcomes_frame().drop(columns=["res_revenue_full", "res_price_delivery_only", "energy_price_state"])
    assert set(run(o=o).frames) == set(of.NAMES)


def test_a_year_with_no_factor_stops_row_cs_frame_only_and_fills_nothing():
    fac = factors()
    del fac[2016]
    res = run(f=fac)
    assert of.PRICE_CENTS_REAL_2024 not in res.frames
    msg = res.report[of.PRICE_CENTS_REAL_2024]["reason_not_built"]
    assert "no factor for 1 years of the frame, [2016]" in msg
    assert set(res.frames) == set(of.NAMES) - {of.PRICE_CENTS_REAL_2024}


@pytest.mark.parametrize("bad", [None, [1.25], {2015: 0.0, 2016: 1.2, 2017: 1.1}, {2015: float("nan"), 2016: 1.2,
                                 2017: 1.1}, {"2015": 1.25, 2016: 1.2, 2017: 1.1}, {2015: True, 2016: 1.2, 2017: 1.1}])
def test_bad_factors_stop_row_cs_frame_only(bad):
    res = run(f=bad) if bad is not None else of.reshape(outcomes_frame(), quantities_frame(), None)
    assert set(res.frames) == set(of.NAMES) - {of.PRICE_CENTS_REAL_2024}
    assert "row C's factor" in res.report[of.PRICE_CENTS_REAL_2024]["reason_not_built"]


# ---- values that cannot be transformed ------------------------------------------------------------------------------------

def troubled():
    """11:AA 2015 missing, 11:AA 2016 zero, 11:AA 2017 negative, 22:AB 2015 +inf: in res_price."""
    o = outcomes_frame()
    o.loc[0, "res_price"] = np.nan
    o.loc[1, "res_price"] = 0.0
    o.loc[2, "res_price"] = -1.0
    o.loc[3, "res_price"] = np.inf
    return o


def test_log_price_keeps_every_row_with_nan_where_there_is_no_log_and_never_an_infinity():
    o = troubled()
    with np.errstate(all="raise"):                       # no log of zero or of a negative is ever attempted
        res = run(o=o)
    f = res.frames[of.PRICE]
    assert len(f) == 9 and np.isinf(f.value).sum() == 0
    got = by_key(f)
    for k in [(11, "AA", 2015), (11, "AA", 2016), (11, "AA", 2017), (22, "AB", 2015)]:
        assert np.isnan(got[k])
    assert abs(got[(33, "BA", 2017)] - np.log(price(2, 2017))) < LOG_TOL
    rec = res.report[of.PRICE]
    assert (rec["values_missing"], rec["values_not_finite"], rec["values_not_positive"]) == (1, 1, 2)
    assert rec["set_to_nan_by_the_transformation"] == 4
    assert rec["values_missing_out"] == 4 and rec["values_not_finite_out"] == 0


def test_an_infinite_price_stops_row_u_and_row_c_frames_and_nothing_is_replaced():
    res = run(o=troubled())
    for n in (of.PRICE_DELIVERY_INCLUSIVE, of.PRICE_CENTS_REAL_2024):
        assert n not in res.frames
        assert "infinity" in res.report[n]["reason_not_built"]
    o = outcomes_frame()
    o.loc[5, "res_price_default_service"] = -np.inf
    res = run(o=o)
    assert of.PRICE_DEFAULT_SERVICE not in res.frames
    assert set(res.frames) == set(of.NAMES) - {of.PRICE_DEFAULT_SERVICE}


def test_row_u_and_c_frames_carry_missing_and_nonpositive_levels():
    o = troubled()
    o.loc[3, "res_price"] = 11.0                         # no infinity: the frames are built
    res = run(o=o)
    for n in (of.PRICE_DELIVERY_INCLUSIVE, of.PRICE_CENTS_REAL_2024):
        got = by_key(res.frames[n])
        assert len(got) == 9 and np.isnan(got[(11, "AA", 2015)])
        assert got[(11, "AA", 2016)] == 0.0
        assert got[(11, "AA", 2017)] < 0
        rec = res.report[n]
        assert (rec["values_missing"], rec["values_not_positive"]) == (1, 2)
    assert abs(by_key(res.frames[of.PRICE_CENTS_REAL_2024])[(11, "AA", 2017)] - (-1.0 * CPI[2024] / CPI[2017])) < 1e-12


def test_supplementary_levels_are_carried_untouched_infinity_included():
    o = outcomes_frame()
    o.loc[0, "res_kwh_per_customer_month"] = np.inf
    o.loc[1, "res_kwh_per_customer_month"] = np.nan
    o.loc[2, "res_bill_per_customer_month"] = 0.0
    q = quantities_frame()
    q.loc[3, "res_customers"] = pd.NA
    res = run(o=o, q=q)
    k, b, c = (by_key(res.frames[n]) for n in (of.KWH, of.BILL, of.CUSTOMERS))
    assert np.isposinf(k[(11, "AA", 2015)]) and np.isnan(k[(11, "AA", 2016)])
    assert b[(11, "AA", 2017)] == 0.0
    assert np.isnan(c[(22, "AB", 2015)])
    assert res.report[of.KWH]["values_not_finite"] == 1 and res.report[of.KWH]["values_missing"] == 1
    assert res.report[of.CUSTOMERS]["values_missing"] == 1


def test_a_value_column_of_text_is_refused_without_showing_it():
    o = outcomes_frame()
    o["res_bill_per_customer_month"] = o.res_bill_per_customer_month.astype(object)
    o.loc[0, "res_bill_per_customer_month"] = str(SENTINEL)
    res = run(o=o)
    assert of.BILL not in res.frames
    msg = res.report[of.BILL]["reason_not_built"]
    assert "not a number" in msg and not any(d in msg for d in SENTINEL_DIGITS)
    o2 = outcomes_frame()
    o2["res_bill_per_customer_month"] = o2.res_bill_per_customer_month.astype(str)
    assert of.BILL not in run(o=o2).frames


def test_an_object_value_column_of_numbers_and_none_is_accepted():
    o = outcomes_frame()
    o["res_kwh_per_customer_month"] = [None] + [float(x) for x in o.res_kwh_per_customer_month[1:]]
    o["res_kwh_per_customer_month"] = o.res_kwh_per_customer_month.astype(object)
    f = run(o=o).frames[of.KWH]
    assert np.isnan(by_key(f)[(11, "AA", 2015)]) and f.value.dtype == np.float64


# ---- sources unchanged, no value shown, no file opened ---------------------------------------------------------------------

@pytest.mark.parametrize("variant", ["clean", "troubled", "types", "duplicate"])
def test_the_source_frames_are_unchanged(variant):
    o, q = outcomes_frame(), quantities_frame()
    if variant == "troubled":
        o = troubled()
    elif variant == "types":
        o = o.astype({"utility_id_eia": "float64", "state": "category"})
        q = q.astype({"state": "string"})
    elif variant == "duplicate":
        o = pd.concat([o, o.iloc[[0]]], ignore_index=True)
    o0, q0 = o.copy(deep=True), q.copy(deep=True)
    fac = factors()
    fac0 = dict(fac)
    of.reshape(o, q, fac)
    of.read_time_checks(o, q, usable={(11, "AA", 2015)}, row_u_flags=q.assign(short_form=False), row_u_window=(2015, 2017))
    pd.testing.assert_frame_equal(o, o0)
    pd.testing.assert_frame_equal(q, q0)
    assert fac == fac0


def _texts(res):
    return [repr(res.report), repr(res.sources)]


def test_no_report_or_message_carries_a_planted_value():
    for col in OUTCOME_COLS_FROM_FILE:
        o = outcomes_frame()
        o.loc[4, col] = SENTINEL
        # once built, once stopped by a duplicate, once stopped by an infinity elsewhere, once by a missing factor
        cases = [o, pd.concat([o, o.iloc[[0]]], ignore_index=True)]
        oi = o.copy()
        oi.loc[0, "res_price"] = np.inf
        oi.loc[0, "res_price_default_service"] = np.inf
        cases.append(oi)
        for c in cases:
            for fac in (factors(), {2015: 1.0}):
                res = of.reshape(c, quantities_frame(), fac)
                for t in _texts(res):
                    assert not any(d in t for d in SENTINEL_DIGITS), col
        checks = of.read_time_checks(o, quantities_frame(), usable={(22, "AB", 2016)},
                                     row_u_flags=quantities_frame().assign(short_form=False), row_u_window=(2015, 2017))
        assert not any(d in repr(checks) for d in SENTINEL_DIGITS)
    q = quantities_frame()
    q["res_customers"] = q.res_customers.astype(float)
    q.loc[4, "res_customers"] = SENTINEL
    for t in _texts(run(q=q)):
        assert not any(d in t for d in SENTINEL_DIGITS)


def test_no_raised_message_carries_a_planted_value():
    o = outcomes_frame()
    o.loc[4, "res_price"] = SENTINEL
    o.loc[0, "res_price"] = np.inf
    for fn, args in ((of._build, (of.PRICE_DELIVERY_INCLUSIVE, o, of._keys(o, "o"), factors())),
                     (of._build, (of.PRICE_CENTS_REAL_2024, o, of._keys(o, "o"), factors()))):
        with pytest.raises(of.ReshapeRefused) as e:
            fn(*args)
        assert not any(d in str(e.value) for d in SENTINEL_DIGITS)
    huge = outcomes_frame()
    huge.loc[4, "res_price"] = 1e308
    with pytest.raises(of.ReshapeRefused) as e:
        of._build(of.PRICE_CENTS_REAL_2024, huge, of._keys(huge, "o"), {2015: 1.25, 2016: 10.0, 2017: 1.0})
    assert "not finite after the deflation" in str(e.value) and "308" not in str(e.value)


def test_no_file_is_opened(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a file was opened")
    for target, name in ((builtins, "open"), (io, "open"), (pd, "read_parquet"), (pd, "read_csv"), (Path, "open"),
                         (Path, "read_text"), (Path, "read_bytes")):
        monkeypatch.setattr(target, name, refuse)
    o, q = outcomes_frame(), quantities_frame()
    fac = {y: CPI[2024] / v for y, v in CPI.items()}       # the factors by hand, as cpi_factors_to_2024 computes them
    res = of.reshape(o, q, fac)
    assert set(res.frames) == set(of.NAMES)
    of.read_time_checks(o, q, usable={(11, "AA", 2015)}, row_u_flags=q.assign(short_form=False), row_u_window=(2015, 2017))


def test_the_module_source_names_no_reader():
    text = (ROOT / "pipeline" / "analysis" / "outcome_frames.py").read_text()
    for word in ("read_parquet", "read_csv", "open(", "load_outcomes", "read_listed_outcomes", "data/blind", "data/raw",
                 "GATE1_SIGNED", "read_peaks"):
        assert word not in text, word


# ---- through the registry's column check and the kernel ---------------------------------------------------------------------

def test_every_frame_passes_the_registrys_column_check():
    r = ro()
    res = run()
    for name in of.NAMES:
        f, err = r._outcome_frame(res.frames, name)
        assert err is None and f is res.frames[name]


def stacked():
    """Invented stacked rows (outcome_analysis.stacked_rows's key columns): 11:AA's block with 22:AB as its comparison
    over 2015-2017, and 33:BA's block with 22:AB again, so 22:AB's unit-years appear twice."""
    rows = [(11, "AA", y) for y in YEARS] + [(22, "AB", y) for y in YEARS] + [(33, "BA", y) for y in YEARS] \
        + [(22, "AB", y) for y in YEARS]
    return pd.DataFrame(rows, columns=of.UNIT_YEAR)


def test_frames_go_through_the_kernels_alignment_with_the_planted_values():
    o = outcomes_frame()
    res = run(o=o)
    rows = stacked()
    src = source_by_key(o, "res_price")
    v = oa._vector_for_rows(rows, res.frames[of.PRICE], of.VALUE)
    want = np.log([src[(u, s, y)] for u, s, y in rows.itertuples(index=False)])
    assert np.max(np.abs(v - want)) < LOG_TOL
    for name in (of.PRICE_DEFAULT_SERVICE, of.KWH, of.BILL, of.CUSTOMERS, of.PRICE_CENTS_REAL_2024):
        assert len(oa._vector_for_rows(rows, res.frames[name], of.VALUE)) == len(rows)


def test_a_price_with_no_log_on_a_required_row_still_stops_the_kernel():
    o = outcomes_frame()
    o.loc[1, "res_price"] = 0.0                          # 11:AA in 2016, a required row
    f = run(o=o).frames[of.PRICE]
    with pytest.raises(oa.OutcomeMisaligned, match="missing or not finite for 1 unit-years"):
        oa._vector_for_rows(stacked(), f, of.VALUE)
    # Off the design's rows it does not matter: a design without 11:AA reads the rest.
    rows = stacked()
    assert len(oa._vector_for_rows(rows[rows.utility_id_eia != 11], f, of.VALUE)) == 9


def test_supplementary_check_classifies_the_carried_levels():
    o = outcomes_frame()
    o.loc[0, "res_kwh_per_customer_month"] = np.inf
    o.loc[4, "res_kwh_per_customer_month"] = 0.0         # 22:AB in 2016, twice in the stacked rows
    f = run(o=o).frames[of.KWH]
    c = so.check_levels(stacked(), f)
    assert c["reasons"][so.NONFINITE]["unit_years"] == 1
    assert c["reasons"][so.NONPOSITIVE]["unit_years"] == 1 and c["reasons"][so.NONPOSITIVE]["stacked_rows"] == 2
    assert c["reasons"][so.MISSING]["unit_years"] == 0


def test_row_u_preparation_reads_the_level_frame():
    o = outcomes_frame()
    o.loc[0, "res_price_default_service"] = np.nan
    o.loc[1, "res_price_default_service"] = 0.0
    f = run(o=o).frames[of.PRICE_DEFAULT_SERVICE]
    rows, notes, failures = rmu._outcome_rows(f, (2015, 2017), {"AA", "AB", "BA"})
    assert len(rows) == 7
    assert any("1 unit-years with no price" in n for n in notes)
    assert any("1 unit-years have a price that is not positive" in x for x in failures)
    src = source_by_key(o, "res_price_default_service")
    for u, s, y, lv in rows[["utility_id_eia", "state", "year", "y"]].itertuples(index=False):
        assert abs(lv - np.log(src[(u, s, y)])) < LOG_TOL           # row U logs the untouched level


# ---- read_time_checks -----------------------------------------------------------------------------------------------------

def usable_all():
    return {(u, s, y) for u, s in UNITS for y in YEARS}


def flags_frame():
    return quantities_frame()[of.UNIT_YEAR].assign(short_form=False)


def test_read_time_checks_on_the_clean_world_all_pass():
    c = of.read_time_checks(outcomes_frame(), quantities_frame(), usable=usable_all(), row_u_flags=flags_frame(),
                            row_u_window=(2015, 2017))
    for name in ("key_types", "duplicate_unit_years_in_outcomes", "coverage", "usable_without_positive_price",
                 "row_u_short_form_flags"):
        assert c[name]["passed"] is True, name
        assert c[name]["passes"].startswith("yes")
    assert c["kwh_and_bill_not_loggable"]["passed"] is None
    assert c["kwh_and_bill_not_loggable"]["res_kwh_per_customer_month"] == {"rows": 9, "missing": 0, "not_finite": 0,
                                                                             "not_positive": 0}
    assert c["key_types"]["same_dtype_by_column"] == {"utility_id_eia": True, "state": True, "year": True}
    assert c["left_to_the_rows"] == [of.ROW_C_BALANCED_SAMPLE_LEFT_TO_THE_ROW]


def test_read_time_checks_without_optional_inputs_say_not_applicable():
    c = of.read_time_checks(outcomes_frame(), quantities_frame())
    assert c["usable_without_positive_price"]["passed"] is None
    assert c["row_u_short_form_flags"]["passed"] is None
    assert c["row_u_short_form_flags"]["passes"].startswith("not applicable")


def test_read_time_checks_key_types_differ_but_pass_and_bad_keys_fail():
    o = outcomes_frame().astype({"year": "int64", "state": "category"})
    c = of.read_time_checks(o, quantities_frame())
    assert c["key_types"]["passed"] is True
    assert c["key_types"]["same_dtype_by_column"] == {"utility_id_eia": True, "state": False, "year": False}
    assert c["key_types"]["outcomes"]["dtypes"]["year"] == "int64"
    o2 = outcomes_frame()
    o2["year"] = o2.year.astype(str)
    c2 = of.read_time_checks(o2, quantities_frame())
    assert c2["key_types"]["passed"] is False and c2["coverage"]["passed"] is None


def test_read_time_checks_count_repeated_unit_years():
    o = pd.concat([outcomes_frame(), outcomes_frame().iloc[[0, 0, 5]]], ignore_index=True)
    c = of.read_time_checks(o, quantities_frame())
    d = c["duplicate_unit_years_in_outcomes"]
    assert (d["rows_repeating"], d["repeated_keys"], d["passed"]) == (5, 3, False)
    assert d["examples"] == ["11:AA in 2015", "22:AB in 2017"]


def test_read_time_checks_coverage_both_ways():
    o = outcomes_frame().iloc[1:]                                     # drop 11:AA 2015
    extra = outcomes_frame().iloc[[0]].assign(utility_id_eia=99)
    o = pd.concat([o, extra], ignore_index=True)
    c = of.read_time_checks(o, quantities_frame())["coverage"]
    assert c["quantity_unit_years_with_no_outcome_row"] == 1 and c["outcome_unit_years_with_no_quantity_row"] == 1
    assert c["examples_quantity_only"] == ["11:AA in 2015"] and c["examples_outcome_only"] == ["99:AA in 2015"]
    assert c["passed"] is False


def test_read_time_checks_usable_without_positive_price():
    o = troubled().iloc[:-1]                    # 33:BA 2017 has no row; 4 troubled prices
    use = usable_all()
    c = of.read_time_checks(o, quantities_frame(), usable=use)["usable_without_positive_price"]
    assert (c["usable_unit_years"], c["with_no_outcome_row"], c["price_missing"], c["price_not_finite"],
            c["price_not_positive"]) == (9, 1, 1, 1, 2)
    assert c["passed"] is False
    c2 = of.read_time_checks(o, quantities_frame(), usable={(22, "AB", 2016)})["usable_without_positive_price"]
    assert c2["passed"] is True


def test_read_time_checks_kwh_and_bill_counts():
    o = outcomes_frame()
    o.loc[0, "res_kwh_per_customer_month"] = np.nan
    o.loc[1, "res_kwh_per_customer_month"] = -np.inf
    o.loc[2, "res_bill_per_customer_month"] = 0.0
    o.loc[3, "res_bill_per_customer_month"] = -4.0
    c = of.read_time_checks(o, quantities_frame())["kwh_and_bill_not_loggable"]
    assert c["res_kwh_per_customer_month"] == {"rows": 9, "missing": 1, "not_finite": 1, "not_positive": 0}
    assert c["res_bill_per_customer_month"] == {"rows": 9, "missing": 0, "not_finite": 0, "not_positive": 2}
    c2 = of.read_time_checks(o.drop(columns="res_bill_per_customer_month"), quantities_frame())["kwh_and_bill_not_loggable"]
    assert "no column" in c2["res_bill_per_customer_month"]["reason"]


def test_read_time_checks_row_u_flags():
    fl = flags_frame()
    fl = fl[~((fl.utility_id_eia == 11) & (fl.year == 2016))]          # no row
    fl["short_form"] = fl.short_form.astype("boolean")
    fl.loc[(fl.utility_id_eia == 22) & (fl.year == 2017), "short_form"] = pd.NA     # a missing flag
    o = outcomes_frame()
    o.loc[1, "res_price_default_service"] = np.nan                    # 11:AA 2016 has no default-service price
    c = of.read_time_checks(o, quantities_frame(), row_u_flags=fl, row_u_window=(2016, 2017))["row_u_short_form_flags"]
    assert (c["outcome_unit_years_in_window"], c["with_no_flags_row"], c["with_a_missing_flag"]) == (6, 1, 1)
    assert c["examples"] == ["11:AA in 2016", "22:AB in 2017"]
    assert c["by_row_u_price_column"][rmu.DEFAULT_SERVICE] == {"unit_years_in_window_with_a_price": 5,
                                                                "of_which_no_flags_row": 0, "of_which_missing_flag": 1}
    assert c["by_row_u_price_column"][rmu.DELIVERY_INCLUSIVE]["of_which_no_flags_row"] == 1
    assert c["passed"] is False
    assert "filed" not in c["passes"]
    # Outside the window nothing is counted.
    c2 = of.read_time_checks(o, quantities_frame(), row_u_flags=fl, row_u_window=(2015, 2015))["row_u_short_form_flags"]
    assert c2["passed"] is True and c2["outcome_unit_years_in_window"] == 3


def test_read_time_checks_row_u_flags_that_disagree():
    fl = pd.concat([flags_frame(), flags_frame().iloc[[0]].assign(short_form=True)], ignore_index=True)
    c = of.read_time_checks(outcomes_frame(), quantities_frame(), row_u_flags=fl,
                            row_u_window=(2015, 2017))["row_u_short_form_flags"]
    assert c["flags_unit_years_whose_rows_disagree"] == 1 and c["passed"] is False


def test_read_time_checks_agree_with_row_us_own_stop():
    """Where the check says row U's Short Form step would stop, the step itself stops, on the same invented frames."""
    fl = flags_frame()
    fl = fl[~((fl.utility_id_eia == 11) & (fl.year == 2016))]
    f = run().frames[of.PRICE_DEFAULT_SERVICE]
    c = of.read_time_checks(outcomes_frame(), quantities_frame(), row_u_flags=fl, row_u_window=(2015, 2017))
    assert c["row_u_short_form_flags"]["passed"] is False
    spec = type("S", (), {"short_form_exclusion": "unit_years_filed"})()
    with pytest.raises(ValueError, match="1 outcome unit-years have no row in sample_flags and 0 have a missing flag"):
        rmu._u_drop_short_form(f, spec, fl, (2015, 2017))
    ok = of.read_time_checks(outcomes_frame(), quantities_frame(), row_u_flags=flags_frame(), row_u_window=(2015, 2017))
    assert ok["row_u_short_form_flags"]["passed"] is True
    kept, _ = rmu._u_drop_short_form(f, spec, flags_frame(), (2015, 2017))
    assert len(kept) == 9


# ---- row C's window (the session's reading, session 27) -------------------------------------------------------------------

LONG_YEARS = list(range(2001, 2026))
REAL_SPAN = {y: CPI[2024] / CPI[y] for y in range(2014, 2026)}          # factors for 2014-2025 only, as the real table


def long_outcomes():
    """The invented outcome frame over 2001 to 2025, the panel's span."""
    rows = []
    for i, (u, st) in enumerate(UNITS):
        for y in LONG_YEARS:
            p = 10.0 + i + 0.25 * (y - 2001)
            rows.append({"utility_id_eia": u, "state": st, "year": y, "res_revenue_full": 1.0, "res_price": p,
                         "res_price_delivery_only": p - 6.0, "res_price_default_service": p - 0.25,
                         "res_bill_per_customer_month": 100.0 + y - 2001, "res_kwh_per_customer_month": 900.0 - i,
                         "energy_price_state": 55.0})
    return pd.DataFrame(rows, columns=list(of.OUTCOME_FILE_COLUMNS)).astype({"year": "int32"})


def long_quantities():
    rows = [(u, st, y, 5_000 + 1_000 * i) for i, (u, st) in enumerate(UNITS) for y in LONG_YEARS]
    return pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "res_customers"]).astype({"year": "int32"})


def test_row_c_frame_is_the_window_only_on_the_panels_span_with_the_real_tables_factors():
    o = long_outcomes()
    res = of.reshape(o, long_quantities(), dict(REAL_SPAN))
    f = res.frames[of.PRICE_CENTS_REAL_2024]
    assert sorted(set(f.year)) == list(range(2015, 2025)) == list(rc.YEARS)
    assert len(f) == 3 * 10
    src = source_by_key(o, "res_price")
    for (u, s, y), v in by_key(f).items():
        want = src[(u, s, y)] * CPI[2024] / CPI[y]
        assert abs(v - want) <= LOG_TOL * abs(want)
    assert by_key(f)[(11, "AA", 2024)] == src[(11, "AA", 2024)]           # factor exactly 1 in 2024
    rec = res.report[of.PRICE_CENTS_REAL_2024]
    assert (rec["rows_in"], rec["rows_out"], rec["rows_outside_row_c_window"]) == (75, 30, 45)
    assert "2015 to 2024" in rec["row_c_window"] and "not the whole outcome file" in rec["row_c_window_rule"]
    assert "session's reading" in rec["row_c_window_rule"]
    for n in set(of.NAMES) - {of.PRICE_CENTS_REAL_2024}:                  # no other frame is restricted
        assert len(res.frames[n]) == 75 and sorted(set(res.frames[n].year)) == LONG_YEARS
        assert "rows_outside_row_c_window" not in res.report[n]


def test_a_window_year_with_no_factor_stops_row_c_and_a_year_outside_needs_none():
    fac = dict(REAL_SPAN)
    del fac[2019]
    res = of.reshape(long_outcomes(), long_quantities(), fac)
    assert of.PRICE_CENTS_REAL_2024 not in res.frames
    assert "[2019]" in res.report[of.PRICE_CENTS_REAL_2024]["reason_not_built"]
    assert set(res.frames) == set(of.NAMES) - {of.PRICE_CENTS_REAL_2024}
    fac = dict(REAL_SPAN)
    fac.pop(2013, None)
    del fac[2014], fac[2025]                                              # outside the window
    assert len(of.reshape(long_outcomes(), long_quantities(), fac).frames[of.PRICE_CENTS_REAL_2024]) == 30


def test_infinity_inside_the_window_stops_row_c_and_outside_is_counted():
    o = long_outcomes()
    o.loc[(o.year == 2005) & (o.utility_id_eia == 22), "res_price"] = np.inf
    res = of.reshape(o, long_quantities(), dict(REAL_SPAN))
    f = res.frames[of.PRICE_CENTS_REAL_2024]
    assert len(f) == 30 and np.isfinite(f.value).all()
    assert res.report[of.PRICE_CENTS_REAL_2024]["rows_outside_row_c_window_not_finite"] == 1
    o.loc[(o.year == 2020) & (o.utility_id_eia == 22), "res_price"] = -np.inf
    res = of.reshape(o, long_quantities(), dict(REAL_SPAN))
    assert of.PRICE_CENTS_REAL_2024 not in res.frames
    assert "inside row C's window" in res.report[of.PRICE_CENTS_REAL_2024]["reason_not_built"]


def unrestricted_deflated(o):
    """res_price times a factor for every year, built in the test, with no window."""
    every = {y: CPI[2024] / CPI.get(y, 200.0) for y in LONG_YEARS}
    k = o[["utility_id_eia", "state", "year"]].astype({"utility_id_eia": "int64", "year": "int64"})
    return k.assign(value=o.res_price.to_numpy(float) * np.array([every[y] for y in k.year]))


def test_the_window_is_the_unrestricted_frame_filtered_by_row_cs_years_and_build_panel_agrees():
    o = long_outcomes()
    o.loc[(o.year == 2017) & (o.utility_id_eia == 33), "res_price"] = np.nan      # one unit loses its balance
    restricted = of.reshape(o, long_quantities(), dict(REAL_SPAN)).frames[of.PRICE_CENTS_REAL_2024]
    full = unrestricted_deflated(o)
    filtered = full[full.year.isin(rc.YEARS)].reset_index(drop=True)
    filtered["state"] = filtered.state.astype(object)
    pd.testing.assert_frame_equal(restricted, filtered, rtol=1e-12, atol=0)
    share = {(u, s): 0.1 * (i + 1) for i, (u, s) in enumerate(UNITS)}
    reg = pd.DataFrame([(u, s, y, float(i + (y >= 2020))) for i, (u, s) in enumerate(UNITS) for y in rc.YEARS],
                       columns=["utility_id_eia", "state", "year", "value"])
    a = rc.build_panel(restricted, reg, share, None, rc.SPECIFICATION, None)
    b = rc.build_panel(full, reg, share, None, rc.SPECIFICATION, None)
    pd.testing.assert_frame_equal(a.frame, b.frame, rtol=1e-12, atol=0)
    assert a.accounting["balanced_units"] == b.accounting["balanced_units"] == 2
    acc_a, acc_b = a.accounting, b.accounting
    assert acc_a.keys() == acc_b.keys()
    for k in acc_a:
        assert (acc_a[k] == acc_b[k]) or (np.isnan(acc_a[k]) and np.isnan(acc_b[k])), k
