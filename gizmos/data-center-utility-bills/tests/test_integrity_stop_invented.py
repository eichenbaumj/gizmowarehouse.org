"""The stop before any estimator (session 28; Joe, 2026-11-20, D-122). Invented inputs only.

His words, unchanged: "Add a narrow stop before any estimator is called when structural key or outcome/quantity coverage
inconsistencies, or contradictions between the usable flags and observed prices, make execution inconsistent with the
frozen inputs. Persist the check report and explain the failure." And: "Do not turn expected missingness outside required
rows, supplementary loggability counts, or the frozen rows' legitimate missing-data rules into blanket failures." And:
"Use invented inputs to demonstrate that an integrity failure prevents estimator calls, that the failure report survives,
and that expected missingness remains permitted."

Every frame here is invented in this file or in tests/test_execute_outcomes_invented.py, whose helpers are imported and
not changed. Every directory written is under pytest's tmp_path. No file under data/ is read, the door to outcomes is an
invented one, git is an invented runner, and the real gate file is never created. The one real path reached is an
existence check of the gate file's path in the gizmo folder, made by the code under test (execute_outcomes.gate_state)
each time a provenance is built; nothing is opened. No research outcome was used to write or to tune anything here.
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

import test_execute_outcomes_invented as k  # noqa: E402  read-only use of its invented frames and its kit

from pipeline.analysis import execute_outcomes as eo  # noqa: E402
from pipeline.analysis import outcome_frames as of  # noqa: E402
from pipeline.analysis import run_outcomes as ro  # noqa: E402

RESEARCH = ro.RESEARCH_DATA_AFTER_THE_FREEZE
WINDOW = (2015, 2025)
UNIT = (11, "AZ")                      # one invented utility-state of the kit's three
YEAR = 2020
DIGITS = ("12345.678", "12345.67", "12345678")        # the kit's planted value, k.SENTINEL, however it is written


def _row(frame, unit=UNIT, year=YEAR):
    return (frame.utility_id_eia == unit[0]) & (frame.state == unit[1]) & (frame.year == year)


def world():
    """The kit's invented world: 3 utility-states, 2013 to 2025, every unit-year usable, every flag False."""
    inputs = k.fake_inputs()
    return k.invented_outcome_file(), inputs


# ---- each blocking finding: one invented break of the frozen inputs' consistency ---------------------------------------------

def _outcome_key_column_missing(o, inputs):
    return o.drop(columns=["state"]), inputs


def _outcome_year_is_text(o, inputs):
    o = o.copy()
    o["year"] = o["year"].astype(str)
    return o, inputs


def _outcome_id_not_whole(o, inputs):
    o = o.copy()
    o["utility_id_eia"] = o["utility_id_eia"].astype(float)
    o.loc[_row(o), "utility_id_eia"] = 11.5
    return o, inputs


def _quantity_key_column_missing(o, inputs):
    inputs.side.q = inputs.side.q.drop(columns=["year"])
    return o, inputs


def _quantity_state_missing_on_a_row(o, inputs):
    q = inputs.side.q.copy()
    q["state"] = q["state"].astype(object)
    q.loc[_row(q), "state"] = None
    inputs.side.q = q
    return o, inputs


def _outcome_unit_year_repeated(o, inputs):
    return pd.concat([o, o[_row(o)]], ignore_index=True), inputs


def _quantity_unit_year_repeated(o, inputs):
    q = inputs.side.q
    inputs.side.q = pd.concat([q, q[_row(q)]], ignore_index=True)
    return o, inputs


def _usable_unit_year_has_no_outcome_row(o, inputs):
    return o[~_row(o)].reset_index(drop=True), inputs


def _unit_year_that_is_not_usable_has_no_outcome_row(o, inputs):
    """His safeguard: "Do not assume a non-usable flag makes absence harmless." The unit-year is taken out of the usable
    set, so the only thing wrong is that the quantity panel has a row the outcome file lacks."""
    inputs.side.usable = inputs.side.usable - {(UNIT[0], UNIT[1], YEAR)}
    return o[~_row(o)].reset_index(drop=True), inputs


def _outcome_unit_year_absent_from_the_quantity_panel(o, inputs):
    q = inputs.side.q
    inputs.side.q = q[~_row(q)].reset_index(drop=True)
    inputs.side.usable = inputs.side.usable - {(UNIT[0], UNIT[1], YEAR)}
    return o, inputs


def _price(value):
    def brk(o, inputs):
        o = o.copy()
        o.loc[_row(o), "res_price"] = value
        return o, inputs
    return brk


def _no_usable_set(o, inputs):
    inputs.side.usable = None
    return o, inputs


def _no_price_column(o, inputs):
    return o.drop(columns=["res_price"]), inputs


BLOCKING = {
    "an outcome key column is missing": (_outcome_key_column_missing, {"key_types"}),
    "an outcome year is text": (_outcome_year_is_text, {"key_types"}),
    "an outcome id is not a whole number": (_outcome_id_not_whole, {"key_types"}),
    "a quantity key column is missing": (_quantity_key_column_missing, {"key_types"}),
    "a quantity state is missing": (_quantity_state_missing_on_a_row, {"key_types"}),
    "an outcome unit-year is repeated": (_outcome_unit_year_repeated, {"duplicate_unit_years_in_outcomes"}),
    "a quantity unit-year is repeated": (_quantity_unit_year_repeated, {"key_types"}),
    "a usable unit-year has no outcome row": (_usable_unit_year_has_no_outcome_row,
                                              {"coverage", "usable_without_positive_price"}),
    "a unit-year that is not usable has no outcome row": (_unit_year_that_is_not_usable_has_no_outcome_row, {"coverage"}),
    "an outcome unit-year is absent from the quantity panel": (_outcome_unit_year_absent_from_the_quantity_panel,
                                                               {"coverage"}),
    "a usable price is missing": (_price(np.nan), {"usable_without_positive_price"}),
    "a usable price is plus infinity": (_price(np.inf), {"usable_without_positive_price"}),
    "a usable price is zero": (_price(0.0), {"usable_without_positive_price"}),
    "a usable price is negative": (_price(-3.0), {"usable_without_positive_price"}),
    "no usable set reaches the check": (_no_usable_set, {"usable_without_positive_price"}),
    "the price column is missing": (_no_price_column, {"usable_without_positive_price"}),
}


# ---- each kind of expected missingness: the run goes on --------------------------------------------------------------------------

def _price_missing_where_not_usable(o, inputs):
    """A price that is missing on a unit-year that is not usable, where the row exists."""
    inputs.side.usable = inputs.side.usable - {(UNIT[0], UNIT[1], YEAR)}
    return _price(np.nan)(o, inputs)


def _kwh_and_bill_not_loggable(o, inputs):
    o = o.copy()
    o.loc[_row(o), "res_kwh_per_customer_month"] = np.nan
    o.loc[_row(o, year=2021), "res_kwh_per_customer_month"] = 0.0
    o.loc[_row(o), "res_bill_per_customer_month"] = -1.0
    o.loc[_row(o, year=2022), "res_bill_per_customer_month"] = np.inf
    return o, inputs


def _row_u_flags_row_missing(o, inputs):
    f = inputs.reconciliation_u.sample_flags
    inputs.reconciliation_u.sample_flags = f[~_row(f)].reset_index(drop=True)
    return o, inputs


def _row_u_flag_missing(o, inputs):
    f = inputs.reconciliation_u.sample_flags.copy()
    f["short_form"] = f["short_form"].astype("boolean")
    f.loc[_row(f), "short_form"] = pd.NA
    inputs.reconciliation_u.sample_flags = f
    return o, inputs


def _row_u_and_c_prices_missing(o, inputs):
    """Row U's default-service price and the delivery-only price missing on rows: the rows' own missing-price rules."""
    o = o.copy()
    o.loc[o.utility_id_eia == 12, "res_price_default_service"] = np.nan
    o["res_price_delivery_only"] = np.nan
    return o, inputs


def _key_types_differ_in_width(o, inputs):
    o = o.copy()
    o["utility_id_eia"] = o["utility_id_eia"].astype("int32")
    o["year"] = o["year"].astype(float)                      # whole numbers held as floats cast cleanly
    q = inputs.side.q.copy()
    q["year"] = q["year"].astype("int16")
    inputs.side.q = q
    return o, inputs


def _nothing(o, inputs):
    return o, inputs


EXPECTED_MISSINGNESS = {
    "nothing is wrong": (_nothing, []),
    "a price is missing where the unit-year is not usable": (_price_missing_where_not_usable, []),
    "kWh and bill rows cannot be logged": (_kwh_and_bill_not_loggable, []),
    "row U's flags lack a row": (_row_u_flags_row_missing, ["row_u_short_form_flags"]),
    "row U's flag is missing": (_row_u_flag_missing, ["row_u_short_form_flags"]),
    "row U's and the delivery-only prices are missing": (_row_u_and_c_prices_missing, []),
    "key types differ in width": (_key_types_differ_in_width, []),
}


def checked_for(brk):
    o, inputs = brk(*world())
    return of.read_time_checks(o, inputs.side.q, inputs.side.usable, inputs.reconciliation_u.sample_flags, WINDOW)


def run_research(tmp_path, brk, run=None, name="out", **over):
    o, inputs = brk(*world())
    calls = k.Calls()
    rec = k.Recorder() if run is None else run
    kit = k.research_kit(calls, frame=o, inputs=inputs)
    kit.update(over)
    out = tmp_path / name
    return out, calls, rec, (lambda **kw: eo.execute_research(inputs_are=RESEARCH, output_dir=out, run=rec,
                                                              **{**kit, **kw}))


def first_record(out):
    line = k.manifest(out)["records"][0]
    return line, k.strict_load((out / line["file"]).read_text())


# ---- the decision, as a pure function on the checks -----------------------------------------------------------------------------

def test_the_blocking_checks_are_the_four_he_named_and_the_coverage_rule_is_two_way():
    assert set(of.BLOCKING_CHECKS) == {"key_types", "duplicate_unit_years_in_outcomes", "coverage",
                                       "usable_without_positive_price"}
    assert set(of.RECORDED_AND_NOT_BLOCKING) == {"kwh_and_bill_not_loggable", "row_u_short_form_flags"}
    assert not set(of.BLOCKING_CHECKS) & set(of.RECORDED_AND_NOT_BLOCKING)
    # every check read_time_checks makes is sorted into exactly one of the two lists
    made = {name for name, v in checked_for(_nothing).items() if isinstance(v, dict) and "passed" in v}
    assert made == set(of.BLOCKING_CHECKS) | set(of.RECORDED_AND_NOT_BLOCKING)
    for words in ("Two-way coverage", "panel.py", "build_panel.py", "write_usable_flag.py", "whatever its usable flag"):
        assert words in of.COVERAGE_RULE


@pytest.mark.parametrize("name", sorted(BLOCKING))
def test_each_blocking_finding_blocks_and_is_named_in_words(name):
    brk, expected = BLOCKING[name]
    d = of.blocking_decision(checked_for(brk))
    got = {b["check"] for b in d["blocking"]}
    assert d["blocks"] is True and expected <= got, (name, got)
    assert d["in_words"].startswith("BLOCKED before any estimator: ")
    for b in d["blocking"]:
        assert b["check"] in of.BLOCKING_CHECKS and b["why"] and b["rule"] == of.BLOCKING_CHECKS[b["check"]]
        assert b["check"] in b["why"]


@pytest.mark.parametrize("name", sorted(EXPECTED_MISSINGNESS))
def test_each_kind_of_expected_missingness_does_not_block(name):
    brk, recorded = EXPECTED_MISSINGNESS[name]
    checked = checked_for(brk)
    d = of.blocking_decision(checked)
    assert d["blocks"] is False and d["blocking"] == []
    assert [r["check"] for r in d["recorded_and_not_blocking"] if r["passed"] is False] == recorded
    assert d["in_words"].startswith("no blocking integrity check failed")
    for b in of.BLOCKING_CHECKS:
        assert checked[b]["passed"] is True


def test_the_expected_missingness_cases_do_plant_what_they_say():
    """So that the tests above are not vacuous: each planted gap is counted by the checks or is in the frames."""
    c = checked_for(_kwh_and_bill_not_loggable)["kwh_and_bill_not_loggable"]
    assert c["res_kwh_per_customer_month"]["missing"] == 1 and c["res_kwh_per_customer_month"]["not_positive"] == 1
    assert c["res_bill_per_customer_month"]["not_positive"] == 1 and c["res_bill_per_customer_month"]["not_finite"] == 1
    assert c["passed"] is None
    assert checked_for(_row_u_flags_row_missing)["row_u_short_form_flags"]["with_no_flags_row"] == 1
    assert checked_for(_row_u_flag_missing)["row_u_short_form_flags"]["with_a_missing_flag"] == 1
    o, inputs = _price_missing_where_not_usable(*world())
    assert o.res_price.isna().sum() == 1 and (UNIT[0], UNIT[1], YEAR) not in inputs.side.usable
    kt = checked_for(_key_types_differ_in_width)["key_types"]
    assert kt["passed"] is True and kt["same_dtype_by_column"] == {"utility_id_eia": False, "state": True, "year": False}


def test_a_check_that_was_not_made_or_did_not_come_back_blocks():
    good = checked_for(_nothing)
    for name in of.BLOCKING_CHECKS:
        absent = {a: b for a, b in good.items() if a != name}
        d = of.blocking_decision(absent)
        assert d["blocks"] and [b["check"] for b in d["blocking"]] == [name] and "absent" in d["blocking"][0]["why"]
        unmade = {**good, name: {"passed": None, "passes": "not applicable: invented"}}
        d = of.blocking_decision(unmade)
        assert d["blocks"] and [b["check"] for b in d["blocking"]] == [name] and "could not be made" in d["blocking"][0]["why"]
    for bad in (None, [], "text"):
        d = of.blocking_decision(bad)
        assert d["blocks"] and d["blocking"][0]["check"] == "read_time_checks"
    d = of.blocking_decision(None, checks_raised="KeyError")
    assert d["blocks"] and "KeyError" in d["in_words"]
    d = of.blocking_decision(good, reshaper_raised="ValueError")
    assert d["blocks"] and [b["check"] for b in d["blocking"]] == ["reshape"] and "ValueError" in d["in_words"]
    # a check that is recorded only never blocks, whatever it says
    for name in of.RECORDED_AND_NOT_BLOCKING:
        d = of.blocking_decision({**good, name: {"passed": False, "passes": "no: invented"}})
        assert d["blocks"] is False and [r["check"] for r in d["recorded_and_not_blocking"]] == [name]


def test_the_decision_carries_counts_and_keys_and_no_value():
    o, inputs = _price(k.SENTINEL * -1)(*world())             # a planted negative price on a usable unit-year
    checked = of.read_time_checks(o, inputs.side.q, inputs.side.usable, inputs.reconciliation_u.sample_flags, WINDOW)
    d = of.blocking_decision(checked)
    b = d["blocking"][0]
    assert b["check"] == "usable_without_positive_price" and b["counts"]["price_not_positive"] == 1
    assert b["counts"]["examples"] == ["11:AZ in 2020"]
    text = json.dumps(d)
    assert not any(x in text for x in DIGITS)


# ---- the research path: an integrity failure prevents estimator calls, and the report survives -----------------------------------

@pytest.mark.parametrize("name", sorted(BLOCKING))
def test_a_blocking_finding_stops_the_run_with_no_estimator_called_and_the_report_on_disk(tmp_path, name):
    brk, expected = BLOCKING[name]
    out, calls, rec, go = run_research(tmp_path, brk)
    with pytest.raises(eo.IntegrityCheckBlocked, match="stopped before any estimator is called") as ei:
        go()
    assert rec.calls == []                                            # the recording runner shows zero calls
    assert calls.log.count(("door",)) == 1
    # the report survives: the record, its manifest line with its hash, and its section of the plain-text report
    man = k.manifest(out)
    assert [r["kind"] for r in man["records"]] == [eo.KIND_READ_TIME_CHECKS] and k.entry_ids(out) == []
    line, first = first_record(out)
    assert eo.ResultsWriter(out).verify(line) is None
    assert ei.value.first_record == line and line["estimated"] is False and line["stage"] == eo.BEFORE_ANY_ESTIMATE
    body = first["body"]
    assert body["blocked_before_any_estimator"] is True and body["blocking_decision"]["blocks"] is True
    got = {b["check"] for b in body["blocking_decision"]["blocking"]}
    assert expected <= got and got <= set(of.BLOCKING_CHECKS)
    assert body["read_time_checks"] is not None and set(of.BLOCKING_CHECKS) <= set(body["read_time_checks"])
    assert body["door_record"]["frame_fingerprint"] == first["provenance"]["outcome_file_hash"]
    # the failure is explained in words, in the record, in the report and in the refusal
    report = (out / eo.REPORT).read_text()
    assert "BLOCKED BEFORE ANY ESTIMATOR: no entry was run" in report
    for b in body["blocking_decision"]["blocking"]:
        assert f"  - {b['check']}: {b['why']}" in report and b["why"] in str(ei.value)
    assert sorted(p.name for p in out.iterdir()) == ["0001_read_time_checks.json", eo.MANIFEST, eo.REPORT]


@pytest.mark.parametrize("name", sorted(EXPECTED_MISSINGNESS))
def test_expected_missingness_lets_the_run_proceed(tmp_path, name):
    brk, recorded = EXPECTED_MISSINGNESS[name]
    out, calls, rec, go = run_research(tmp_path, brk)
    done = go(through="row_C")
    assert rec.calls == [k.U, k.C] and k.entry_ids(out) == [k.U, k.C] and done["next_expected"] == k.IAS
    _line, first = first_record(out)
    body = first["body"]
    assert body["blocked_before_any_estimator"] is False and body["blocking_decision"]["blocking"] == []
    assert body["read_time_checks_failed"] == recorded
    report = (out / eo.REPORT).read_text()
    assert "blocking integrity checks: none failed" in report and "BLOCKED" not in report
    for name_ in recorded:
        assert f"  - recorded and not blocking: {name_}:" in report


def test_a_blocked_run_hands_no_frame_to_anything_and_leaves_no_value_in_the_record(tmp_path, monkeypatch):
    o, inputs = _price(-k.SENTINEL)(*world())
    assert (o.res_price == k.SENTINEL).sum() == 1 and (o.res_price == -k.SENTINEL).sum() == 1
    calls, rec, out = k.Calls(), k.Recorder(), tmp_path / "out"
    seen = []
    real = eo.Coordinator.adopt

    def adopt(self, provenance, outcomes):
        seen.append(outcomes)
        return real(self, provenance, outcomes)
    monkeypatch.setattr(eo.Coordinator, "adopt", adopt)
    with pytest.raises(eo.IntegrityCheckBlocked):
        eo.execute_research(inputs_are=RESEARCH, output_dir=out, run=rec, **k.research_kit(calls, frame=o, inputs=inputs))
    assert seen == [None] and rec.calls == []
    for p in out.iterdir():
        assert not any(d in p.read_text() for d in DIGITS), p.name


def test_checks_or_a_reshaper_that_raise_stop_the_run_and_the_record_is_written(tmp_path):
    def raising_checks(*a, **kw):
        raise KeyError(f"an invented message that carries {k.SENTINEL}")

    def raising_reshaper(*a, **kw):
        raise ValueError(f"an invented message that carries {k.SENTINEL}")

    for name, over, check, word in (("c", {"checks": raising_checks}, "read_time_checks", "KeyError"),
                                    ("r", {"reshaper": raising_reshaper}, "reshape", "ValueError")):
        out, calls, rec, go = run_research(tmp_path, _nothing, name=name, **over)
        with pytest.raises(eo.IntegrityCheckBlocked, match=word):
            go()
        assert rec.calls == [] and calls.log.count(("door",)) == 1
        line, first = first_record(out)
        assert eo.ResultsWriter(out).verify(line) is None
        assert [b["check"] for b in first["body"]["blocking_decision"]["blocking"]] == [check]
        text = (out / line["file"]).read_text() + (out / eo.REPORT).read_text()
        assert word in text and not any(d in text for d in DIGITS)   # the type's name, never the message
    # a decision that raises, or that is not a record with a true or false `blocks`, stops the run as well
    for name, decide in (("d1", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("invented"))),
                         ("d2", lambda *a, **kw: {"blocks": None}), ("d3", lambda *a, **kw: None)):
        out, calls, rec, go = run_research(tmp_path, _nothing, name=name, decide=decide)
        with pytest.raises(eo.IntegrityCheckBlocked, match="could not be made"):
            go()
        assert rec.calls == [] and k.entry_ids(out) == []
        assert first_record(out)[1]["body"]["blocked_before_any_estimator"] is True


def test_the_same_rule_applies_to_a_later_process_that_reads_the_outcomes(tmp_path):
    out, calls, rec, go = run_research(tmp_path, _nothing)
    go(through="row_U")
    assert rec.calls == [k.U]
    # a later process on the same directory reads the same file; its checks are made again, and a blocking one stops it
    good = of.read_time_checks

    def checks_that_now_fail(*a, **kw):
        c = good(*a, **kw)
        c["coverage"] = {**c["coverage"], "passed": False, "passes": "no: invented for the later process"}
        return c
    out2, calls2, rec2, go2 = run_research(tmp_path, _nothing, checks=checks_that_now_fail)
    assert out2 == out
    before = k.entry_ids(out)
    with pytest.raises(eo.IntegrityCheckBlocked, match="invented for the later process"):
        go2(through="row_C")
    assert rec2.calls == [] and calls2.log.count(("door",)) == 1 and k.entry_ids(out) == before == [k.U]
    kinds = [r["kind"] for r in k.manifest(out)["records"]]
    assert kinds == [eo.KIND_READ_TIME_CHECKS, eo.KIND_ENTRY, eo.KIND_READ_TIME_CHECKS]
    blocked = k.strict_load((out / k.manifest(out)["records"][-1]["file"]).read_text())["body"]
    assert blocked["blocked_before_any_estimator"] is True
    # and a blocked directory is not taken past its stop by asking again: the checks are made again and stop it again
    out3, calls3, rec3, go3 = run_research(tmp_path, _nothing, checks=checks_that_now_fail)
    with pytest.raises(eo.IntegrityCheckBlocked):
        go3()
    assert rec3.calls == [] and k.entry_ids(out) == [k.U]


def test_main_reports_a_blocked_run_in_words_with_its_own_exit_code(capsys, tmp_path, monkeypatch):
    def blocked(**kw):
        raise eo.IntegrityCheckBlocked("the run is stopped before any estimator is called: invented")
    monkeypatch.setattr(eo, "execute_research", blocked)
    assert eo.main(["--inputs-are", RESEARCH, "--output-dir", str(tmp_path / "o"), "--through", "row_C"]) == 3
    printed = capsys.readouterr().out
    assert printed.startswith("blocked: the run is stopped before any estimator is called")


def test_pieces_that_return_something_malformed_still_stop_the_run_with_the_record_written(tmp_path):
    """Whatever a replaced piece returns after the read, no estimator is called and the first record is on disk."""
    class Shaped:
        frames, report, sources = [], "not a mapping", None
    cases = {
        "checks return a list": {"checks": lambda *a, **kw: ["not", "a", "record"]},
        "checks return text": {"checks": lambda *a, **kw: "not a record"},
        "the reshaper's report is not a mapping": {"reshaper": lambda *a, **kw: Shaped()},
        "the decision's findings are not records": {"decide": lambda *a, **kw: {"blocks": True, "blocking": ["text"]}},
        "the decision says go with findings that are not records": {
            "decide": lambda *a, **kw: {"blocks": False, "blocking": [], "recorded_and_not_blocking": [1]}},
    }
    for i, (name, over) in enumerate(cases.items()):
        out, calls, rec, go = run_research(tmp_path, _nothing, name=f"m{i}", **over)
        with pytest.raises(eo.IntegrityCheckBlocked):
            go()
        assert rec.calls == [] and calls.log.count(("door",)) == 1, name
        line, first = first_record(out)
        assert eo.ResultsWriter(out).verify(line) is None and first["body"]["blocked_before_any_estimator"] is True, name
        assert "BLOCKED BEFORE ANY ESTIMATOR" in (out / eo.REPORT).read_text(), name


def test_a_process_that_reads_no_outcome_is_not_run_on_top_of_a_standing_block(tmp_path):
    """Rows U and C written under passing checks; a later process that reads the outcomes is blocked; a process that
    would run only the inventory check, which reads no outcome and so makes no check of its own, is then refused."""
    out, calls, rec, go = run_research(tmp_path, _nothing)
    go(through="row_C")
    assert k.entry_ids(out) == [k.U, k.C]
    good = of.read_time_checks

    def checks_that_now_fail(*a, **kw):
        c = good(*a, **kw)
        c["coverage"] = {**c["coverage"], "passed": False, "passes": "no: invented for the later process"}
        return c
    _o, _c, rec2, go2 = run_research(tmp_path, _nothing, checks=checks_that_now_fail)
    with pytest.raises(eo.IntegrityCheckBlocked):
        go2()
    assert rec2.calls == []
    before = (out / eo.MANIFEST).read_text()
    _o, calls3, rec3, go3 = run_research(tmp_path, _nothing)
    with pytest.raises(eo.IntegrityCheckBlocked, match="standing block"):
        go3(through="inventory_against_sales")
    assert rec3.calls == [] and ("door",) not in calls3.log and (out / eo.MANIFEST).read_text() == before
    # and where the directory's last word is a passing check, the inventory-only process runs as before
    out4, calls4, rec4, go4 = run_research(tmp_path, _nothing, name="clean")
    go4(through="row_C")
    _o, calls5, rec5, go5 = run_research(tmp_path, _nothing, name="clean")
    go5(through="inventory_against_sales")
    assert rec5.calls == [k.IAS] and ("door",) not in calls5.log


# ---- one deliberate break per rule, made in the test process ---------------------------------------------------------------------

BREAK_FOR_RULE = {
    "key_types": "a quantity key column is missing",
    "duplicate_unit_years_in_outcomes": "an outcome unit-year is repeated",
    "coverage": "a unit-year that is not usable has no outcome row",
    "usable_without_positive_price": "a usable price is negative",
}


@pytest.mark.parametrize("rule", sorted(BREAK_FOR_RULE))
def test_each_rule_is_what_names_its_finding_shown_by_taking_the_rule_away(tmp_path, monkeypatch, rule):
    """With the rule in place the finding stops the run and is named (the tests above). With that one rule taken out of
    the decision, in this process only, the finding is no longer named by it. For the two rules whose finding fails no
    other check (coverage, and the usable flag against the price) the run then goes on and the estimator is called,
    which is what the rule prevents. A key that cannot be used, or a repeated outcome unit-year, also leaves other
    blocking checks unable to be made, and those still stop the run, as they should."""
    brk, _expected = BLOCKING[BREAK_FOR_RULE[rule]]
    with_rule = of.blocking_decision(checked_for(brk))
    assert with_rule["blocks"] is True and rule in {b["check"] for b in with_rule["blocking"]}
    monkeypatch.setattr(of, "BLOCKING_CHECKS", {a: b for a, b in of.BLOCKING_CHECKS.items() if a != rule})
    broken = of.blocking_decision(checked_for(brk))
    assert rule not in {b["check"] for b in broken["blocking"]}
    if rule in ("coverage", "usable_without_positive_price"):
        assert broken["blocks"] is False
        out, calls, rec, go = run_research(tmp_path, brk)
        go(through="row_U")
        assert rec.calls == [k.U]                                  # with the rule broken, the estimator is called
    else:
        assert broken["blocks"] is True                            # other checks cannot be made, and they stop it
