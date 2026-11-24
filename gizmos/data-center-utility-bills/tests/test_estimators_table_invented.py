"""The side-by-side table of estimators (pipeline/analysis/estimators_table.py), on invented result mappings only.

No file under data/ is read and no estimate is computed: every result is a number written in the test. Covers: the five
rows the plan names with the labels it fixes; every pairwise gap; exclusion in both directions and at a range's end; a
failed run and a run with no range (outcome 3) appearing in words and in no range comparison; an incomplete side;
mapping checks; and the two adapters, on dicts shaped like outcome_analysis.estimate's and callaway_santanna.run's.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import estimators_table as et  # noqa: E402

TOL = 1e-12


def run(name, estimator, set_, est, lo, hi, *, status=et.ESTIMATED, failure=None, label=None, units="log_points", thr=0.02,
        validated=False):
    return {"name": name, "estimator": estimator, "set": set_, "threshold": thr, "status": status, "estimate": est,
            "range_low": lo, "range_high": hi, "units": units, "label": label, "failure_in_words": failure,
            "validated": validated}


def five():
    return [run("headline", et.STACKED, et.HEADLINE_SET, 0.020, -0.040, 0.080, validated=True),
            run("cs", et.CALLAWAY_SANTANNA, et.HEADLINE_SET, 0.090, 0.050, 0.130),
            run("ten_year", et.STACKED, et.TEN_YEAR_SET, 0.010, -0.050, 0.070),
            run("plus_unsettled", et.STACKED, et.PLUS_UNSETTLED, 0.030, -0.010, 0.070),
            run("every", et.STACKED, et.EVERY_COHORT_UTILITY, -0.010, -0.030, 0.010)]


def by(t, key, **match):
    return [x for x in t[key] if all(x[k] == v for k, v in match.items())]


def test_rows_and_the_plans_labels():
    t = et.table(five())
    rows = {r["name"]: r for r in t["rows"]}
    assert [r["name"] for r in t["rows"]] == ["headline", "cs", "ten_year", "plus_unsettled", "every"]
    assert rows["headline"]["plan_labels"] == []
    assert rows["cs"]["plan_labels"] == [et.CALLAWAY_SANTANNA_RANGE_LABEL]
    for n in ("ten_year", "plus_unsettled", "every"):
        assert rows[n]["plan_labels"] == [et.NOT_VALIDATED]
    assert t["expected_rows_not_supplied"] == []
    assert t["need_not_agree"] == et.NEED_NOT_AGREE and t["reading"] == et.READING


def test_headline_set_at_five_percent_is_not_validated():
    r = run("h5", et.STACKED, et.HEADLINE_SET, 0.0, -1.0, 1.0, thr=0.05)
    assert et.table([r])["rows"][0]["plan_labels"] == [et.NOT_VALIDATED]


def test_a_headline_row_whose_claim_the_kernel_refused_is_labelled_not_validated():
    """Session 19: the label follows the result's own validation, not the set name. The headline set at 2% whose claim was
    refused (or never made) carries the plan's words."""
    r = run("headline", et.STACKED, et.HEADLINE_SET, 0.02, -0.04, 0.08, validated=False)
    assert et.table([r])["rows"][0]["plan_labels"] == [et.NOT_VALIDATED]


@pytest.mark.parametrize("set_,thr,estimator", [(et.TEN_YEAR_SET, 0.02, et.STACKED), (et.HEADLINE_SET, 0.05, et.STACKED),
                                                (et.HEADLINE_SET, 0.02, et.CALLAWAY_SANTANNA)])
def test_a_row_marked_validated_anywhere_but_the_stacked_headline_at_two_percent_is_refused(set_, thr, estimator):
    """The set-name rule as a cross-check in the unsafe direction: a non-headline row claiming validation stops."""
    r = run("x", estimator, set_, 0.0, -1.0, 1.0, thr=thr, validated=True)
    with pytest.raises(et.TableRefused, match="validat"):
        et.table([r])


def test_every_pairwise_gap():
    t = et.table(five())
    assert len(t["gaps"]) == 10
    g = by(t, "gaps", a="headline", b="cs")[0]
    assert abs(g["a_minus_b"] - (0.020 - 0.090)) < TOL and abs(g["size"] - 0.070) < TOL
    assert abs(t["largest_gap"]["size"] - 0.100) < TOL and {t["largest_gap"]["a"], t["largest_gap"]["b"]} == {"cs", "every"}


def test_exclusion_each_direction():
    t = et.table(five())
    assert len(t["exclusions"]) == 20
    # The headline's range (-0.04, 0.08) excludes Callaway and Sant'Anna's 0.09, from above.
    x = by(t, "exclusions", range_of="headline", estimate_of="cs")[0]
    assert x["excludes"] and x["side"] == "above the range"
    # Callaway and Sant'Anna's range (0.05, 0.13) excludes the headline's 0.02, from below.
    x = by(t, "exclusions", range_of="cs", estimate_of="headline")[0]
    assert x["excludes"] and x["side"] == "below the range"
    # every's range (-0.03, 0.01) excludes plus_unsettled's 0.03 but the reverse does not hold.
    assert by(t, "exclusions", range_of="every", estimate_of="plus_unsettled")[0]["excludes"]
    assert not by(t, "exclusions", range_of="plus_unsettled", estimate_of="every")[0]["excludes"]
    assert t["any_range_excludes_another_estimate"]
    assert {(x["range_of"], x["estimate_of"]) for x in t["ranges_that_exclude"]} == {
        ("headline", "cs"), ("cs", "headline"), ("cs", "ten_year"), ("cs", "plus_unsettled"), ("cs", "every"),
        ("ten_year", "cs"), ("plus_unsettled", "cs"), ("every", "cs"), ("every", "headline"), ("every", "plus_unsettled")}
    # ten_year's 0.01 sits at every's upper end (0.01) and every's -0.01 at plus_unsettled's lower end: both inside.
    assert not by(t, "exclusions", range_of="every", estimate_of="ten_year")[0]["excludes"]


def test_an_estimate_at_a_ranges_end_is_inside():
    rs = [run("a", et.STACKED, et.HEADLINE_SET, 0.0, -0.05, 0.05), run("b", et.STACKED, et.TEN_YEAR_SET, 0.05, 0.0, 0.1)]
    t = et.table(rs)
    assert not by(t, "exclusions", range_of="a", estimate_of="b")[0]["excludes"]
    assert not by(t, "exclusions", range_of="b", estimate_of="a")[0]["excludes"]
    assert t["any_range_excludes_another_estimate"] is False


def test_failed_and_no_range_runs_appear_in_words_and_in_no_range_comparison():
    rs = five()
    rs[1] = run("cs", et.CALLAWAY_SANTANNA, et.HEADLINE_SET, None, None, None, status=et.FAILED,
                failure="diff-diff 4.0.0 is not installed")
    rs[4] = run("every", et.STACKED, et.EVERY_COHORT_UTILITY, -0.01, None, None, status=et.ESTIMATED,
                failure="no procedure qualified", label="descriptive")
    t = et.table(rs)
    rows = {r["name"]: r for r in t["rows"]}
    assert rows["cs"]["takes_part_in_range_comparisons"] is False and rows["cs"]["plan_labels"] == []
    assert rows["every"]["takes_part_in_range_comparisons"] is False and rows["every"]["label"] == "descriptive"
    assert {x["name"] for x in t["runs_in_no_range_comparison"]} == {"cs", "every"}
    assert all("cs" not in (x["range_of"], x["estimate_of"]) and "every" not in (x["range_of"], x["estimate_of"])
               for x in t["exclusions"])
    assert len(t["exclusions"]) == 6
    # A failed run with no estimate is in no gap; a point estimate with no range is in gaps, flagged.
    assert all("cs" not in (g["a"], g["b"]) for g in t["gaps"])
    eg = [g for g in t["gaps"] if "every" in (g["a"], g["b"])]
    assert len(eg) == 3 and all(g["involves_an_estimate_with_no_range"] for g in eg)
    assert not any(g["involves_an_estimate_with_no_range"] for g in t["gaps"] if "every" not in (g["a"], g["b"]))


def test_failed_run_keeps_a_descriptive_point_estimate():
    rs = [run("headline", et.STACKED, et.HEADLINE_SET, 0.02, None, None, status=et.FAILED,
              failure="the CR2 standard error of the headline is not finite and positive", label="descriptive"),
          run("ten", et.STACKED, et.TEN_YEAR_SET, 0.01, -0.02, 0.04)]
    t = et.table(rs)
    assert t["exclusions"] == [] and len(t["gaps"]) == 1 and t["gaps"][0]["involves_an_estimate_with_no_range"]


def test_incomplete_side_excludes_nothing_on_that_side():
    rs = [run("a", et.STACKED, et.HEADLINE_SET, 0.0, -0.05, math.inf), run("b", et.STACKED, et.TEN_YEAR_SET, 9.0, 8.0, 10.0)]
    t = et.table(rs)
    assert not by(t, "exclusions", range_of="a", estimate_of="b")[0]["excludes"]
    assert by(t, "exclusions", range_of="b", estimate_of="a")[0]["excludes"]
    assert t["rows"][0]["range_high_search_incomplete"] and not t["rows"][0]["range_low_search_incomplete"]


def test_expected_rows_not_supplied_are_named():
    t = et.table(five()[:2])
    assert {(x["estimator"], x["set"]) for x in t["expected_rows_not_supplied"]} == {
        (et.STACKED, et.TEN_YEAR_SET), (et.STACKED, et.PLUS_UNSETTLED), (et.STACKED, et.EVERY_COHORT_UTILITY)}


@pytest.mark.parametrize("bad,match", [
    (dict(range_low=0.1, range_high=-0.1), "low end"),
    (dict(range_low=0.1, range_high=None), "both ends"),
    (dict(status=et.FAILED, failure_in_words=None), "failure in words"),
    (dict(status=et.FAILED, failure_in_words="x"), "no range"),
    (dict(estimate=None), "finite estimate"),
    (dict(estimate=float("nan")), "not a finite number"),
    (dict(range_low=None, range_high=None), "says why"),
    (dict(estimator="ols"), "estimator"),
    (dict(units=""), "units"),
    (dict(validated=None), "validated must be True or False"),
])
def test_inconsistent_mappings_are_refused(bad, match):
    r = {**five()[0], **bad}
    with pytest.raises(et.TableRefused, match=match):
        et.table([r])


def test_table_level_refusals():
    rs = five()
    rs[1]["units"] = "percent"
    with pytest.raises(et.TableRefused, match="different units"):
        et.table(rs)
    with pytest.raises(et.TableRefused, match="given twice"):
        et.table(five() + five()[:1])
    with pytest.raises(et.TableRefused, match="has no field"):
        et.table([{k: v for k, v in five()[0].items() if k != "label"}])


def test_plan_words_are_verbatim():
    text = " ".join((ROOT / "PREANALYSIS.md").read_text().split())
    assert f'"{et.NOT_VALIDATED}"' in text
    # The plan's sentence as amended on 2026-11-19 (Joe, D-105); before that it read "is not calibrated by the inference
    # comparison and is labelled so".
    assert ("The Callaway and Sant'Anna range is the t-based construction on its bootstrap standard error, is "
            f"{et.PLAN_UNCALIBRATED_WORDS}, and is labelled secondary and uncalibrated") in text
    assert et.CALLAWAY_SANTANNA_RANGE_LABEL.endswith(et.PLAN_UNCALIBRATED_WORDS)     # the plan's words end the label
    assert et.NEED_NOT_AGREE in text and et.READING in text


def test_not_validated_matches_the_kernels_constant():
    # outcome_analysis is the kernel; it is read here only to check the two strings agree.
    from pipeline.analysis import outcome_analysis as oa
    assert oa.NOT_VALIDATED == et.NOT_VALIDATED


# ---- the adapters, on dicts shaped like the two modules' results ---------------------------------------------------------

NOT_VALIDATED_CHECK = {"claimed": False, "passed": None, "why": "not claimed"}
VALIDATED_CHECK = {"claimed": True, "passed": True, "why": "checked"}


def stacked_result(est, rng, failure=None, status="estimate with its 90% range under the selected procedure", validated=False):
    return {"headline": {"log_points": est, "range_90_log_points": rng, "status": status},
            "numerical_failure": failure, "validation": None if validated else et.NOT_VALIDATED,
            "validation_check": VALIDATED_CHECK if validated else NOT_VALIDATED_CHECK}


def test_from_stacked_result():
    r = et.from_stacked_result("headline", et.HEADLINE_SET, 0.02, stacked_result(0.02, [-0.04, 0.08], validated=True))
    assert r["status"] == et.ESTIMATED and r["range_low"] == -0.04 and r["units"] == "log_points" and r["validated"]
    refused = et.from_stacked_result("headline_refused", et.HEADLINE_SET, 0.02, stacked_result(0.02, [-0.04, 0.08]))
    assert refused["validated"] is False
    assert et.table([refused])["rows"][0]["plan_labels"] == [et.NOT_VALIDATED]
    # validation None without a passed check is not the kernel's validated label
    half = {**stacked_result(0.02, [-0.04, 0.08]), "validation": None}
    assert et.from_stacked_result("h", et.HEADLINE_SET, 0.02, half)["validated"] is False
    with pytest.raises(et.TableRefused, match="carries no `validation`"):
        et.from_stacked_result("h", et.HEADLINE_SET, 0.02, {k: v for k, v in stacked_result(0.02, None).items() if k != "validation"})
    f = et.from_stacked_result("ten", et.TEN_YEAR_SET, 0.02, stacked_result(
        0.01, None, {"cause": "x", "in_words": "the CR2 standard error of the headline is not finite and positive"},
        status="descriptive: the selected procedure failed numerically, so no range and no test result is reported"))
    assert f["status"] == et.FAILED and f["estimate"] == 0.01 and f["range_low"] is None
    assert f["label"].startswith("descriptive") and "CR2" in f["failure_in_words"]
    n = et.from_stacked_result("every", et.EVERY_COHORT_UTILITY, 0.02, stacked_result(
        float("nan"), None, {"cause": "rank_deficient", "in_words": "the regressors are not all identified"},
        status="not computed"))
    assert n["status"] == et.FAILED and n["estimate"] is None
    assert et.table([r, f, n])["rows"][0]["plan_labels"] == []


def test_from_callaway_santanna_result():
    ok = {"headline": 0.09, "range_90": [0.05, 0.13], "range_label": et.CALLAWAY_SANTANNA_RANGE_LABEL,
          "numerical_failure": None}
    r = et.from_callaway_santanna_result("cs", et.HEADLINE_SET, 0.02, ok)
    assert r["status"] == et.ESTIMATED and r["range_high"] == 0.13
    assert et.table([r])["rows"][0]["plan_labels"] == [et.CALLAWAY_SANTANNA_RANGE_LABEL]
    bad = {"headline": 0.09, "headline_label": "descriptive: its variance could not be computed", "range_90": None,
           "range_label": "no range: the headline's variance from the event-study covariance is not finite or is negative",
           "numerical_failure": "the headline's variance from the event-study covariance is not finite or is negative"}
    f = et.from_callaway_santanna_result("cs", et.HEADLINE_SET, 0.02, bad)
    assert f["status"] == et.FAILED and f["estimate"] == 0.09 and f["label"].startswith("descriptive")


# ---- Joe's ruling of 2026-11-19 (D-105) on the Callaway and Sant'Anna range ----------------------------------------------

def check_cs_label(label: str):
    assert "secondary" in label and "uncalibrated" in label
    assert "t-based" in label and "t critical value on the number of states less one" in label
    assert "package's interval" not in label and "package\u2019s interval" not in label and "rests on the package" not in label


def test_the_callaway_santanna_label_is_secondary_and_uncalibrated_and_never_the_packages_interval():
    check_cs_label(et.CALLAWAY_SANTANNA_RANGE_LABEL)
    t = et.table(five())
    for r in t["rows"]:
        for lab in r["plan_labels"]:
            assert "package's interval" not in lab
    assert next(r for r in t["rows"] if r["name"] == "cs")["plan_labels"] == [et.CALLAWAY_SANTANNA_RANGE_LABEL]
    # the table's label is the run's label word for word (callaway_santanna is imported here only to compare)
    from pipeline.analysis import callaway_santanna as cs
    assert et.CALLAWAY_SANTANNA_RANGE_LABEL == cs.RANGE_LABEL
    assert et.PLAN_UNCALIBRATED_WORDS == cs.PLAN_UNCALIBRATED_WORDS


def test_the_label_check_can_fail(monkeypatch):
    """A deliberate break in the test process: the label of before 2026-11-19 put back. The check fails on it."""
    monkeypatch.setattr(et, "CALLAWAY_SANTANNA_RANGE_LABEL", "not calibrated by the inference comparison")
    with pytest.raises(AssertionError):
        check_cs_label(et.CALLAWAY_SANTANNA_RANGE_LABEL)
    with pytest.raises(AssertionError):
        check_cs_label("secondary and uncalibrated: the package's interval")


VERDICT = re.compile(r"\breproduced\b|\bsurviv|matches the paper|\bas a miss\b|\bnot reproduce\b", re.IGNORECASE)


def _strings(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def test_no_label_or_returned_string_is_a_reproduction_verdict():
    """D-107: the table's labels must not return a reproduction verdict. The module's string constants and every
    string in a table (a full one, one with a failed run, one with rows missing) are scanned."""
    consts = [v for k, v in vars(et).items() if k.isupper() and isinstance(v, str)]
    assert consts and [c for c in consts if VERDICT.search(c)] == []
    rows = five()
    rows[1] = run("cs", et.CALLAWAY_SANTANNA, et.HEADLINE_SET, 0.09, None, None, status=et.FAILED, failure="no range")
    for t in (et.table(five()), et.table(rows), et.table(five()[:2])):
        assert [x for x in _strings(t) if VERDICT.search(x)] == []
        for r in t["rows"]:
            assert "reproduced" not in r and all(not VERDICT.search(lab) for lab in r["plan_labels"])


# ---- Joe's ruling of 2026-11-19 (D-111) on Callaway and Sant'Anna's comparison sample -----------------------------------

ATTRIBUTION = "A difference between this run's estimate and the headline estimate cannot be attributed solely to the estimator."


def check_cs_sample_label(label: str, *, with_count: bool):
    assert label and label.endswith(ATTRIBUTION)
    assert "comparison sample differs from the headline's" in label and "D-111" in label
    if with_count:
        assert "680 of the 1,670 never-treated units" in label and "605 of them" in label
    else:
        assert "680 of 1,670" in label and "was not made for this set" in label


def test_the_callaway_santanna_row_carries_the_sample_difference_with_the_count():
    t = et.table(five())
    rows = {r["name"]: r for r in t["rows"]}
    assert rows["cs"]["sample_label"] == et.CALLAWAY_SANTANNA_SAMPLE_LABEL
    check_cs_sample_label(rows["cs"]["sample_label"], with_count=True)
    assert all(r["sample_label"] is None for n, r in rows.items() if n != "cs")      # stacked rows carry none
    # a failed Callaway and Sant'Anna row with no range still carries it
    failed = five()
    failed[1] = run("cs", et.CALLAWAY_SANTANNA, et.HEADLINE_SET, 0.09, None, None, status=et.FAILED, failure="no range")
    cs_row = next(r for r in et.table(failed)["rows"] if r["name"] == "cs")
    assert cs_row["plan_labels"] == [] and cs_row["sample_label"] == et.CALLAWAY_SANTANNA_SAMPLE_LABEL
    # on any other set the count, made for the headline set at 2% only, is not attached to it
    other = run("cs5", et.CALLAWAY_SANTANNA, et.HEADLINE_SET, 0.09, 0.05, 0.13, thr=0.05)
    lab = et.table([other])["rows"][0]["sample_label"]
    assert lab == et.CALLAWAY_SANTANNA_SAMPLE_LABEL_OTHER_SET
    check_cs_sample_label(lab, with_count=False)
    # word for word the module's (callaway_santanna is imported here only to compare)
    from pipeline.analysis import callaway_santanna as cs
    assert et.CALLAWAY_SANTANNA_SAMPLE_LABEL == cs.REGION_SAMPLE_DIFFERENCE
    assert et.CALLAWAY_SANTANNA_SAMPLE_LABEL_OTHER_SET == cs.REGION_SAMPLE_DIFFERENCE_OTHER_SET
    assert et.CALLAWAY_SANTANNA_ESTIMATOR_ATTRIBUTION == cs.ESTIMATOR_ATTRIBUTION == ATTRIBUTION


def test_the_sample_label_check_can_fail(monkeypatch):
    """A deliberate break in the test process: the label without the attribution sentence, and without the count."""
    with pytest.raises(AssertionError):
        check_cs_sample_label(et.CALLAWAY_SANTANNA_SAMPLE_LABEL.replace(ATTRIBUTION, ""), with_count=True)
    with pytest.raises(AssertionError):
        check_cs_sample_label(et.CALLAWAY_SANTANNA_SAMPLE_LABEL.replace("680", "690"), with_count=True)
    monkeypatch.setattr(et, "CALLAWAY_SANTANNA_SAMPLE_LABEL", "comparison utilities differ")
    with pytest.raises(AssertionError):
        check_cs_sample_label(next(r for r in et.table(five())["rows"] if r["name"] == "cs")["sample_label"], with_count=True)
