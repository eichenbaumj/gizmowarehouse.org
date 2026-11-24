"""The supplementary outcomes (pipeline/analysis/supplementary_outcomes.py) on invented designs and invented levels only.

Each test's body is a check_* function that reads the module's functions at call time, so the same body can be run with
a function of the module replaced by a wrong version. test_each_check_fails_under_a_break runs every check under such a
break, made in the test process only, and asserts the check then fails. The designs and the log-scale world are those of
tests/test_outcome_analysis_invented.py (make, outcomes); levels are exp of its log values. The only file read is the one
stored summary, data/frozen/supplementary_outcomes_spec.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import supplementary_outcomes as so  # noqa: E402
from test_outcome_analysis_invented import make, outcomes  # noqa: E402

KEY3 = ["utility_id_eia", "state", "year"]
EFFECT = 0.05                                             # hosts' level times exp(0.05) in every post year
FLAT = {0: EFFECT, 1: EFFECT, 2: EFFECT, 3: EFFECT}
TOL = 1e-9          # stated tolerance: no noise, so the only error is log(exp(x)) rounding (about 1e-16 a value)
DISTINCT = -731.904862                                    # a planted bad value whose digits must never appear
STORED = ROOT / "data" / "frozen" / so.OUT_NAME


# ---- the invented world -----------------------------------------------------------------------------------------------

def world(effect=FLAT):
    """(design, levels frame): levels = exp of an exactly additive-in-logs world (unit + year + degree days), hosts'
    levels multiplied by exp(effect) in post years. Column `value`."""
    d, q, regions, dd = make()
    logs = outcomes(dd=dd, noise=0.0, effect=effect)
    levels = logs.rename(columns={"log_price": "value"})
    levels["value"] = np.exp(levels["value"])
    return d, levels


def kernel(d, logged: pd.DataFrame) -> dict:
    """What a caller passes as `estimate`: the kernel on the logged frame, not validated."""
    r = oa.estimate(d, oa.outcome_vector(d, logged, "value"), validated_design=False)
    r["estimated"] = r["headline"]["log_points"] == r["headline"]["log_points"]
    return r


def required(d) -> pd.DataFrame:
    """The design's stacked rows counted per unit-year (a test-side count, independent of the module)."""
    return oa.stacked_rows(d).groupby(KEY3).size().rename("n").reset_index()


def shared_comparison(d) -> tuple:
    """A comparison unit-year that is stacked more than once (a comparison for two or more hosts), and its count."""
    rows = oa.stacked_rows(d)
    comp = rows[~rows.is_host].groupby(KEY3).size()
    many = comp[comp > 1]
    assert len(many), "the invented design has no comparison utility shared by two hosts in one calendar year"
    (u, s, y), n = many.index[0], int(many.iloc[0])
    return (int(u), s, int(y)), n


def host_unit_year(d) -> tuple:
    rows = oa.stacked_rows(d)
    r = rows[rows.is_host].iloc[0]
    return (int(r.utility_id_eia), r.state, int(r.year))


def unused_unit_year(d, levels) -> tuple:
    """A unit-year of the levels frame that no stacked row uses."""
    need = set(map(tuple, required(d)[KEY3].itertuples(index=False)))
    for u, s, y in levels[KEY3].itertuples(index=False):
        if (int(u), s, int(y)) not in need:
            return int(u), s, int(y)
    raise AssertionError("every unit-year of the invented frame is used")


def put(levels, key, value) -> pd.DataFrame:
    out = levels.copy()
    m = (out.utility_id_eia == key[0]) & (out.state == key[1]) & (out.year == key[2])
    assert m.sum() == 1
    out.loc[m, "value"] = value
    return out


def drop(levels, key) -> pd.DataFrame:
    m = (levels.utility_id_eia == key[0]) & (levels.state == key[1]) & (levels.year == key[2])
    assert m.sum() == 1
    return levels[~m]


# ---- the checks ------------------------------------------------------------------------------------------------------

def check_positive_levels_give_the_kernels_estimate_on_their_log():
    d, levels = world()
    r = so.run_on_design(d, levels, so.KWH, kernel)
    direct = levels.copy()
    direct["value"] = np.log(direct["value"])
    k = kernel(d, direct)
    assert r["computable"] is True and r["specification"]["transformation"] == "natural log"
    assert r["headline"]["log_points"] == k["headline"]["log_points"]               # exactly the kernel's
    assert r["event_year_coefficients"] == k["event_year_coefficients"]
    assert r["headline"]["range_90_log_points"] == k["headline"]["range_90_log_points"]
    assert r["validation"] == oa.NOT_VALIDATED
    assert r["supplementary"]["required_stacked_rows"] == len(oa.stacked_rows(d))


def check_a_planted_effect_is_recovered():
    d, levels = world()
    r = so.run_on_design(d, levels, so.BILL, kernel)
    assert abs(r["headline"]["log_points"] - EFFECT) < TOL
    for e in range(-6, 0):
        assert abs(r["event_year_coefficients"][str(e)]) < TOL
    for e in range(0, 4):
        assert abs(r["event_year_coefficients"][str(e)] - EFFECT) < TOL


BAD_CASES = {                     # name: (value or None for an absent row, expected reason)
    "zero": (0.0, so.NONPOSITIVE),
    "negative": (-2.0, so.NONPOSITIVE),
    "absent_row": (None, so.MISSING),
    "nan": (np.nan, so.MISSING),
    "plus_infinity": (np.inf, so.NONFINITE),
    "minus_infinity": (-np.inf, so.NONFINITE),
}


def check_a_bad_value_on_a_required_row_is_not_computable(case: str, where: str):
    value, reason = BAD_CASES[case]
    d, levels = world()
    if where == "host":
        key, n = host_unit_year(d), 1
    else:
        key, n = shared_comparison(d)
        assert n > 1
    bad = drop(levels, key) if value is None and case == "absent_row" else put(levels, key, value)
    with pytest.raises(so.NotComputable) as exc:
        so.log_frame_for_design(d, bad, so.CUSTOMERS)
    rec = exc.value.record
    assert rec["computable"] is False and rec["outcome"] == so.CUSTOMERS
    assert rec["affected_unit_years"] == 1 and rec["affected_stacked_rows"] == n
    assert rec["reasons"][reason]["unit_years"] == 1 and rec["reasons"][reason]["stacked_rows"] == n
    assert rec["reasons"][reason]["examples"] == [f"{key[0]}:{key[1]} in {key[2]}"]
    for other in so.REASONS:
        if other != reason:
            assert rec["reasons"][other]["unit_years"] == 0 and rec["reasons"][other]["stacked_rows"] == 0
    req = required(d)
    assert rec["required_unit_years"] == len(req) and rec["required_stacked_rows"] == int(req.n.sum())
    assert f"1 {reason} ({n} stacked rows)" in rec["in_words"]
    json.dumps(rec)                                                         # JSON-ready


def check_two_reasons_at_once_are_both_counted():
    d, levels = world()
    shared, n = shared_comparison(d)
    host = host_unit_year(d)
    bad = put(put(levels, shared, 0.0), host, np.inf)
    with pytest.raises(so.NotComputable) as exc:
        so.log_frame_for_design(d, bad, so.KWH)
    rec = exc.value.record
    assert rec["reasons"][so.NONPOSITIVE]["unit_years"] == 1 and rec["reasons"][so.NONPOSITIVE]["stacked_rows"] == n
    assert rec["reasons"][so.NONFINITE]["unit_years"] == 1 and rec["reasons"][so.NONFINITE]["stacked_rows"] == 1
    assert rec["reasons"][so.MISSING]["unit_years"] == 0
    assert rec["affected_unit_years"] == 2 and rec["affected_stacked_rows"] == n + 1
    assert f"1 {so.NONPOSITIVE} ({n} stacked rows)" in rec["in_words"] and f"1 {so.NONFINITE} (1 stacked rows)" in rec["in_words"]


def check_a_bad_value_on_an_unused_unit_year_changes_nothing():
    d, levels = world()
    base_frame, base_rec = so.log_frame_for_design(d, levels, so.KWH)
    base = so.run_on_design(d, levels, so.KWH, kernel)
    key = unused_unit_year(d, levels)
    for v in (0.0, np.nan, -3.0):
        f, rec = so.log_frame_for_design(d, put(levels, key, v), so.KWH)
        pd.testing.assert_frame_equal(f, base_frame, check_exact=True)
        assert rec == base_rec
        r = so.run_on_design(d, put(levels, key, v), so.KWH, kernel)
        assert r["headline"]["log_points"] == base["headline"]["log_points"]
        assert r["event_year_coefficients"] == base["event_year_coefficients"]


def check_no_constant_is_added():
    d, levels = world()
    ones = levels.copy()
    ones["value"] = 1.0
    f, rec = so.log_frame_for_design(d, ones, so.CUSTOMERS)
    assert (f["value"] == 0.0).all()                                        # log(1) is exactly 0
    assert rec["constant_added"] == "none"
    f2, _ = so.log_frame_for_design(d, levels, so.CUSTOMERS)
    m = f2.merge(levels, on=KEY3, suffixes=("", "_level"))
    assert np.array_equal(m["value"].to_numpy(), np.log(m["value_level"].to_numpy()))
    assert not np.allclose(m["value"].to_numpy(), np.log1p(m["value_level"].to_numpy()), rtol=0, atol=1e-6)
    req = required(d)
    assert list(f2[KEY3].itertuples(index=False, name=None)) == list(req[KEY3].itertuples(index=False, name=None))


def _design_hash(d) -> str:
    return dsg.fingerprint({"x": dsg.design_inputs(d, ps.GAS_SHARE, None)})["sha256"]


def check_the_callers_frame_and_the_design_are_not_changed():
    d, levels = world()
    frame_before = levels.copy(deep=True)
    hash_before, sig_before = _design_hash(d), oa.rows_signature(oa.stacked_rows(d))
    hosts_before = d.hosts.copy(deep=True)
    so.run_on_design(d, levels, so.KWH, kernel)
    so.run_on_design(d, put(levels, host_unit_year(d), 0.0), so.KWH, kernel)
    pd.testing.assert_frame_equal(levels, frame_before, check_exact=True)
    assert _design_hash(d) == hash_before and oa.rows_signature(oa.stacked_rows(d)) == sig_before
    pd.testing.assert_frame_equal(d.hosts, hosts_before)


def check_no_outcome_value_appears_in_any_message_or_record():
    d, levels = world()
    shared, _ = shared_comparison(d)
    host = host_unit_year(d)
    bad = put(put(levels, shared, DISTINCT), host, np.nan)
    digits = ["731.9", "7319", "904862", "-731"]
    good_value = float(levels.loc[(levels.utility_id_eia == shared[0]) & (levels.state == shared[1])
                                  & (levels.year == shared[2]), "value"].iloc[0])
    digits.append(repr(good_value)[:8])
    texts = []
    with pytest.raises(so.NotComputable) as exc:
        so.log_frame_for_design(d, bad, so.BILL)
    texts += [str(exc.value), json.dumps(exc.value.record)]
    r = so.run_on_design(d, bad, so.BILL, kernel)
    texts.append(json.dumps(r))
    texts.append(json.dumps(so.check_levels(oa.stacked_rows(d), bad)))
    with pytest.raises(oa.OutcomeMisaligned) as dup:
        so.check_levels(oa.stacked_rows(d), pd.concat([bad, bad[(bad.utility_id_eia == shared[0]) & (bad.year == shared[2])]]))
    texts.append(str(dup.value))
    words = bad.copy()
    words["value"] = words["value"].astype(object)
    on_host = (words.utility_id_eia == host[0]) & (words.state == host[1]) & (words.year == host[2])
    words.loc[on_host, "value"] = "secret-731.904862"                     # text on a required row stops, unshown
    with pytest.raises(oa.OutcomeMisaligned) as nn:
        so.check_levels(oa.stacked_rows(d), words)
    texts.append(str(nn.value))
    for t in texts:
        for dg in digits:
            assert dg not in t, f"{dg!r} appears in {t[:80]!r}"


def check_a_repeated_unit_year_or_a_missing_column_stops_as_the_kernel_stops():
    d, levels = world()
    rows = oa.stacked_rows(d)
    with pytest.raises(oa.OutcomeMisaligned, match="repeats a unit-year"):
        so.check_levels(rows, pd.concat([levels, levels.iloc[:1]]))
    with pytest.raises(oa.OutcomeMisaligned, match="repeats a unit-year"):
        so.log_frame_for_design(d, pd.concat([levels, levels.iloc[:1]]), so.KWH)
    with pytest.raises(oa.OutcomeMisaligned, match="no column"):
        so.check_levels(rows, levels.drop(columns=["year"]))
    with pytest.raises(oa.OutcomeMisaligned, match="no column"):
        so.log_frame_for_design(d, levels.rename(columns={"value": "level"}), so.KWH)
    # the kernel stops on the same two frames in the same words
    with pytest.raises(oa.OutcomeMisaligned, match="repeats a unit-year"):
        oa.outcome_vector(d, pd.concat([levels, levels.iloc[:1]]), "value")
    with pytest.raises(oa.OutcomeMisaligned, match="no column"):
        oa.outcome_vector(d, levels.drop(columns=["year"]), "value")


def check_run_on_design_does_not_call_estimate_when_not_computable():
    d, levels = world()
    calls = []

    def spy(design, logged):
        calls.append(1)
        return {"estimated": True}

    r = so.run_on_design(d, put(levels, host_unit_year(d), 0.0), so.CUSTOMERS, spy)
    assert calls == []
    assert r["estimated"] is False and r["computable"] is False
    assert r["non_computable"]["reasons"][so.NONPOSITIVE]["unit_years"] == 1
    assert r["failure_in_words"] == r["non_computable"]["in_words"]
    assert r["specification"] == so.SPECS[so.CUSTOMERS].as_dict()
    ok = so.run_on_design(d, levels, so.CUSTOMERS, spy)
    assert calls == [1] and ok["computable"] is True


def check_specs_carry_the_three_outcomes():
    s = so.SPECS
    assert set(s) == {so.KWH, so.BILL, so.CUSTOMERS} == {"kwh_per_residential_customer", "bill_per_customer",
                                                          "residential_customers"}
    assert s[so.KWH].source_column == "res_kwh_per_customer_month"
    assert s[so.BILL].source_column == "res_bill_per_customer_month"
    assert s[so.CUSTOMERS].source_column == "res_customers"
    assert s[so.KWH].unit == "kWh per residential customer per month"
    assert s[so.BILL].unit == "nominal dollars per residential customer per month"
    assert s[so.CUSTOMERS].unit == "residential customers, a count"
    for spec in s.values():
        assert spec.transformation == "natural log" and spec.constant_added is None
        assert spec.imputation == "none" and spec.rows_dropped == "none"
        assert "non-computable" in spec.non_computable_rule and "No validation was made" in spec.validation_limit
    assert "the gated door" in s[so.KWH].source_file and "panel_quantities.parquet" in s[so.CUSTOMERS].source_file
    assert so.JOE_WORDS_ATTRIBUTION == "Joe, 2026-11-20 (D-117)" and so.JOE_WORDS.startswith("Settle the supplementary")
    with pytest.raises(TypeError):
        s["x"] = None                                                       # read-only mapping


def check_the_stored_summary_carries_the_specification():
    stored = json.loads(STORED.read_text())
    part = so.spec_part()
    for k, v in part.items():
        assert stored[k] == json.loads(json.dumps(v)), k
    assert "DRAFT, not frozen" in stored["what_this_is"]


# ---- the tests -------------------------------------------------------------------------------------------------------

def test_positive_levels_give_the_kernels_estimate_on_their_log():
    check_positive_levels_give_the_kernels_estimate_on_their_log()


def test_a_planted_effect_is_recovered():
    check_a_planted_effect_is_recovered()


@pytest.mark.parametrize("where", ["host", "shared_comparison"])
@pytest.mark.parametrize("case", list(BAD_CASES))
def test_a_bad_value_on_a_required_row_is_not_computable(case, where):
    check_a_bad_value_on_a_required_row_is_not_computable(case, where)


def test_two_reasons_at_once_are_both_counted():
    check_two_reasons_at_once_are_both_counted()


def test_a_bad_value_on_an_unused_unit_year_changes_nothing():
    check_a_bad_value_on_an_unused_unit_year_changes_nothing()


def test_no_constant_is_added():
    check_no_constant_is_added()


def test_the_callers_frame_and_the_design_are_not_changed():
    check_the_callers_frame_and_the_design_are_not_changed()


def test_no_outcome_value_appears_in_any_message_or_record():
    check_no_outcome_value_appears_in_any_message_or_record()


def test_a_repeated_unit_year_or_a_missing_column_stops_as_the_kernel_stops():
    check_a_repeated_unit_year_or_a_missing_column_stops_as_the_kernel_stops()


def test_run_on_design_does_not_call_estimate_when_not_computable():
    check_run_on_design_does_not_call_estimate_when_not_computable()


def test_specs_carry_the_three_outcomes():
    check_specs_carry_the_three_outcomes()


def test_the_stored_summary_carries_the_specification():
    check_the_stored_summary_carries_the_specification()


# ---- every check fails under a break made here ------------------------------------------------------------------------

_real_log_frame = so.log_frame_for_design
_real_check = so.check_levels
_real_keys = so._keys_of


def _log1p_frame(d, frame, name, column="value"):
    f, rec = _real_log_frame(d, frame, name, column)
    lv = f.merge(frame[KEY3 + [column]].astype({"utility_id_eia": int, "year": int}), on=KEY3, suffixes=("", "_lv"))
    f[column] = np.log1p(lv[column + "_lv"].to_numpy(dtype=float))
    return f, rec


def _stacked_zeroed(rows, frame, column="value"):
    c = _real_check(rows, frame, column)
    for v in c["reasons"].values():
        v["stacked_rows"] = v["unit_years"]
    c["affected_stacked_rows"] = c["affected_unit_years"]
    return c


def _first_reason_only(rows, frame, column="value"):
    c = _real_check(rows, frame, column)
    seen = False
    for v in c["reasons"].values():
        if v["unit_years"] and seen:
            v["unit_years"], v["stacked_rows"], v["examples"] = 0, 0, []
        seen = seen or bool(v["unit_years"])
    return c


def _whole_frame_check(rows, frame, column="value"):
    """Classifies every row of the frame, the design's or not (the wrong rule)."""
    f = frame[KEY3].copy()
    f["is_host"] = False
    return _real_check(pd.concat([rows[KEY3 + ["is_host"]], f], ignore_index=True), frame, column)


def _mutating_frame(d, frame, name, column="value"):
    frame[column] = frame[column] * 1.0 + 0.0
    frame.loc[frame.index[0], column] = 12345.0
    return _real_log_frame(d, frame, name, column)


def _leaky_check(rows, frame, column="value"):
    c = _real_check(rows, frame, column)
    vals = pd.to_numeric(frame[column], errors="coerce")
    c["reasons"][so.NONPOSITIVE]["examples"].append(f"{float(vals.min()):.6f}")
    return c


def _no_dup_check(frame, column):
    f = frame[KEY3 + [column]].copy() if all(c in frame.columns for c in KEY3 + [column]) else frame.copy()
    for c in ("utility_id_eia", "year"):
        if c in f.columns:
            f[c] = f[c].astype(int)
    return f.drop_duplicates(KEY3) if all(c in f.columns for c in KEY3) else f


def _swallowing_log_frame(d, frame, name, column="value"):
    try:
        return _real_log_frame(d, frame, name, column)
    except so.NotComputable:
        return frame.copy(), {}


def _wrong_specs():
    s = dict(so.SPECS)
    from dataclasses import replace
    s[so.KWH] = replace(s[so.KWH], transformation="log1p")
    return s


def _wrong_spec_part():
    p = _real_spec_part()
    p["specifications"][so.BILL]["unit"] = "real 2024 dollars per residential customer per month"
    return p


_real_spec_part = so.spec_part
FAIL = (AssertionError, pytest.fail.Exception)

BREAKS = [
    ("kernel_on_log", check_positive_levels_give_the_kernels_estimate_on_their_log, "log_frame_for_design", _log1p_frame, FAIL),
    ("planted_effect", check_a_planted_effect_is_recovered, "log_frame_for_design", _log1p_frame, FAIL),
    ("two_reasons", check_two_reasons_at_once_are_both_counted, "check_levels", _first_reason_only, FAIL),
    ("unused_unit_year", check_a_bad_value_on_an_unused_unit_year_changes_nothing, "check_levels", _whole_frame_check,
     FAIL + (so.NotComputable,)),
    ("no_constant", check_no_constant_is_added, "log_frame_for_design", _log1p_frame, FAIL),
    ("not_mutated", check_the_callers_frame_and_the_design_are_not_changed, "log_frame_for_design", _mutating_frame, FAIL),
    ("no_value_shown", check_no_outcome_value_appears_in_any_message_or_record, "check_levels", _leaky_check, FAIL),
    ("stops_as_kernel", check_a_repeated_unit_year_or_a_missing_column_stops_as_the_kernel_stops, "_keys_of", _no_dup_check,
     FAIL),
    ("estimate_not_called", check_run_on_design_does_not_call_estimate_when_not_computable, "log_frame_for_design",
     _swallowing_log_frame, FAIL),
    ("specs", check_specs_carry_the_three_outcomes, "SPECS", None, FAIL),
    ("stored_summary", check_the_stored_summary_carries_the_specification, "spec_part", _wrong_spec_part, FAIL),
]
# Every reason case is also broken: each of the twelve parametrized cases fails when stacked counts are replaced by
# unit-year counts (shared comparison) or when the reasons are relabelled (host).
for _case in BAD_CASES:
    BREAKS.append((f"bad_value_{_case}_shared",
                   (lambda c: lambda: check_a_bad_value_on_a_required_row_is_not_computable(c, "shared_comparison"))(_case),
                   "check_levels", _stacked_zeroed, FAIL))


def _relabelled(rows, frame, column="value"):
    """Moves every reason's counts one place along REASONS (missing to nonfinite, and so on)."""
    c = _real_check(rows, frame, column)
    old = {k: dict(v) for k, v in c["reasons"].items()}
    for i, k in enumerate(so.REASONS):
        src = old[so.REASONS[i - 1]]
        c["reasons"][k].update(unit_years=src["unit_years"], stacked_rows=src["stacked_rows"], examples=src["examples"])
    return c


for _case in BAD_CASES:
    BREAKS.append((f"bad_value_{_case}_host",
                   (lambda c: lambda: check_a_bad_value_on_a_required_row_is_not_computable(c, "host"))(_case),
                   "check_levels", _relabelled, FAIL))


@pytest.mark.parametrize("name,check,attr,wrong,raises", BREAKS, ids=[b[0] for b in BREAKS])
def test_each_check_fails_under_a_break(name, check, attr, wrong, raises, monkeypatch):
    if attr == "SPECS":
        monkeypatch.setattr(so, "SPECS", _wrong_specs())
    else:
        monkeypatch.setattr(so, attr, wrong)
    with pytest.raises(raises):
        check()
