#!/usr/bin/env python3
"""Do the estimators agree? (PREANALYSIS.md, "Reported checks", the bullet of that name; registry id `estimators_agree`
in run_outcomes.py.) It only assembles other runs' results. Reads NO price and opens NO file; there is no main().
It carries no reconciliation row and no label of rows U or C, and none of its labels or returned strings is a
reproduction verdict (checked 2026-11-19 against Joe's ruling D-107; tests/test_estimators_table_invented.py scans them).

The plan, verbatim:

    "The stacked estimate, the Callaway and Sant'Anna estimate, and the headline set against the set with the ten-year
    case, the set with every host unsettled on assignment put back and every cohort utility as built, side by side with
    their ranges. They estimate somewhat different averages and need not agree. Reading: the size of the gaps, and
    whether any range excludes another's estimate. The Callaway and Sant'Anna range is not calibrated by the inference
    comparison and is labelled so."

And from Inference, "Where the validation does not transfer": a range reported under the selected procedure on any design
other than the headline set at 2% "carries the words "under the procedure validated on the headline set; no validation
was made on this design"".

What is here
------------
row_input(...)            builds one run's plain mapping (the fields below) and checks it.
from_stacked_result(...)  fills the mapping from what outcome_analysis.estimate returns (headline.log_points,
                          headline.range_90_log_points, headline.status, numerical_failure.in_words). Reads dict keys only;
                          outcome_analysis is not imported.
from_callaway_santanna_result(...)
                          fills it from what callaway_santanna.run is documented to return (headline, range_90,
                          range_label, numerical_failure). Reads dict keys only; callaway_santanna is not imported.
table(results)            the rows, every pairwise gap and, for each ordered pair, whether A's range excludes B's estimate.

A run's mapping
---------------
name               a unique name
estimator          STACKED or CALLAWAY_SANTANNA
set, threshold     the set the run is on and its threshold (0.02 for the five rows the plan names)
status             ESTIMATED or FAILED
estimate           a finite number, or None (a FAILED run may carry a point estimate that still computed; it is then
                   labelled descriptive by the caller and takes part in no range comparison)
range_low, range_high
                   both given or both None. A side whose search was incomplete may be -inf or +inf (Inference: an
                   incomplete side counts as infinitely wide). A FAILED run has no range.
units              one string for the whole table (for example "log_points"); a table mixing units stops in words.
label              the caller's own label (for example the outcome 2 or 3 wording, or "descriptive"); may be None.
failure_in_words   required for a FAILED run, and for an ESTIMATED run with no range (the plan's outcome 3: "no
                   procedure qualified"); None otherwise.
validated          True only for a stacked run whose result the kernel labelled validated after checking the claim
                   (outcome_analysis.estimate: `validation` None and `validation_check.passed` True); False otherwise,
                   and always False for Callaway and Sant'Anna. from_stacked_result reads it from the result.

Labels the plan fixes are added here, never left to the caller: CALLAWAY_SANTANNA_RANGE_LABEL on a Callaway and Sant'Anna
range, NOT_VALIDATED on every stacked range the kernel did not label validated. CALLAWAY_SANTANNA_RANGE_LABEL is
callaway_santanna.RANGE_LABEL word for word (a test checks it; the module is not imported here): the range is secondary
and uncalibrated, the module's t-based construction (the headline plus or minus the t critical value on the number of
states less one, times the standard deviation of the bootstrap draws of the headline), accepted by Joe on 2026-11-19
(D-105), and it ends in the plan's words, "not calibrated by the inference comparison". It is never called the package's
interval: the package's multiplier bootstrap supplies the standard error only. The Callaway and Sant'Anna row also
carries CALLAWAY_SANTANNA_SAMPLE_LABEL in `sample_label`, with or without a range (Joe, 2026-11-19, D-111): its
comparison sample keeps 680 of 1,670 never-treated units that are in no cohort's host region at that cohort's reference
year (605 on the stricter count), and a difference between its estimate and the headline estimate cannot be attributed
solely to the estimator. Since session 19 the stacked label is
decided from the result's own validation (`validated`), not from the set name and threshold, so a headline-set row whose
claim the kernel refused is labelled not validated. The set-name rule is kept as a cross-check only: a row marked
validated on any set but the headline set at 2% is refused (the unsafe direction).

The agent's readings (not stated by the plan)
---------------------------------------------
- A gap is estimate A less estimate B, for every unordered pair of rows that both have a finite estimate, with its size.
  A gap that involves a point estimate with no range is flagged `involves_an_estimate_with_no_range`; it is still a gap
  between two numbers, and whether to show such gaps is the session's call.
- "A's range excludes B's estimate" is B's estimate below A's lower end or above A's upper end; an estimate exactly at an
  end is inside (a closed range). It is tested for every ordered pair in which both runs have a range: the brief's rule
  that a run with no range takes part in no range comparison is read as applying to both places in the pair.
- The five rows the plan names are EXPECTED_ROWS; a table without one of them says which, and nothing is filled.
"""
from __future__ import annotations

import math
from itertools import combinations, permutations

STACKED = "stacked"
CALLAWAY_SANTANNA = "callaway_santanna"
ESTIMATED = "estimated"
FAILED = "failed"

HEADLINE_SET = "headline_set"
TEN_YEAR_SET = "headline_set_with_the_ten_year_case"
PLUS_UNSETTLED = "headline_set_plus_hosts_unsettled_on_assignment"
EVERY_COHORT_UTILITY = "every_cohort_utility"
HEADLINE_THRESHOLD = 0.02

# The plan's words (PREANALYSIS.md: Reported checks; Inference, "Where the validation does not transfer").
PLAN_UNCALIBRATED_WORDS = "not calibrated by the inference comparison"     # the plan's words for the range
CALLAWAY_SANTANNA_RANGE_LABEL = ("secondary and uncalibrated: a t-based range, the headline plus or minus the t critical "
                                 "value on the number of states less one times the bootstrap standard error of the headline "
                                 "(the module's construction, accepted by Joe on 2026-11-19, D-105); "
                                 + PLAN_UNCALIBRATED_WORDS)
# The Callaway and Sant'Anna row's sample label (Joe, 2026-11-19, D-111): callaway_santanna.REGION_SAMPLE_DIFFERENCE and
# REGION_SAMPLE_DIFFERENCE_OTHER_SET word for word (a test checks it; the module is not imported here). Its comparison
# sample keeps never-treated units in no host's region, so its estimate differs from the headline's in sample as well as
# in estimator.
CALLAWAY_SANTANNA_ESTIMATOR_ATTRIBUTION = ("A difference between this run's estimate and the headline estimate cannot be "
                                           "attributed solely to the estimator.")
CALLAWAY_SANTANNA_SAMPLE_LABEL = (
    "This run's comparison sample differs from the headline's. On the headline set at 2%, 680 of the 1,670 never-treated "
    "units are in no cohort's host region at that cohort's reference year (g-3), and 605 of them are in none of the four "
    "host regions (West, ERCOT, SPP, Southeast) at any of the five reference years (counted 2026-11-19 from this module's "
    "sample() on quantity files; docs/gate1/callaway-santanna-regions-without-host-2026-11-19.md). The headline's matched "
    "comparison utilities come from each host's own region in its reference year. These units stay in this run's sample "
    "by Joe's ruling of 2026-11-19 (D-111) and inform the gas-share slope, region entering as a covariate. "
    + CALLAWAY_SANTANNA_ESTIMATOR_ATTRIBUTION)
CALLAWAY_SANTANNA_SAMPLE_LABEL_OTHER_SET = (
    "This run's comparison sample differs from the headline's. Never-treated units in no host's region at a cohort's "
    "reference year (g-3) stay in this run's sample by Joe's ruling of 2026-11-19 (D-111), region entering as a covariate. "
    "The count on file (680 of 1,670 never-treated units, 605 on the stricter count) is for the headline set at 2% and was "
    "not made for this set. " + CALLAWAY_SANTANNA_ESTIMATOR_ATTRIBUTION)
NOT_VALIDATED = "under the procedure validated on the headline set; no validation was made on this design"
NEED_NOT_AGREE = "They estimate somewhat different averages and need not agree."
READING = "Reading: the size of the gaps, and whether any range excludes another's estimate."

# The five rows the plan names: (estimator, set, threshold).
EXPECTED_ROWS = (
    (STACKED, HEADLINE_SET, HEADLINE_THRESHOLD),
    (CALLAWAY_SANTANNA, HEADLINE_SET, HEADLINE_THRESHOLD),
    (STACKED, TEN_YEAR_SET, HEADLINE_THRESHOLD),
    (STACKED, PLUS_UNSETTLED, HEADLINE_THRESHOLD),
    (STACKED, EVERY_COHORT_UTILITY, HEADLINE_THRESHOLD),
)

FIELDS = ("name", "estimator", "set", "threshold", "status", "estimate", "range_low", "range_high", "units", "label",
          "failure_in_words", "validated")


class TableRefused(ValueError):
    """A mapping is inconsistent or the table is malformed. Raised in words; nothing is filled or guessed."""


def _finite(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(float(x))


def _number_or_inf(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and not math.isnan(float(x))


def check_input(r: dict) -> dict:
    """The mapping checked and returned as a plain dict with every field. Raises TableRefused in words."""
    missing = [f for f in FIELDS if f not in r]
    if missing:
        raise TableRefused(f"run {r.get('name')!r} has no field {missing}")
    extra = [f for f in r if f not in FIELDS]
    if extra:
        raise TableRefused(f"run {r.get('name')!r} has fields this table does not know: {extra}")
    name = r["name"]
    if not isinstance(name, str) or not name:
        raise TableRefused("every run needs a non-empty name")
    if r["estimator"] not in (STACKED, CALLAWAY_SANTANNA):
        raise TableRefused(f"run {name!r}: estimator {r['estimator']!r} is not {STACKED!r} or {CALLAWAY_SANTANNA!r}")
    if r["status"] not in (ESTIMATED, FAILED):
        raise TableRefused(f"run {name!r}: status {r['status']!r} is not {ESTIMATED!r} or {FAILED!r}")
    lo, hi, est = r["range_low"], r["range_high"], r["estimate"]
    has_range = lo is not None or hi is not None
    if has_range and (lo is None or hi is None):
        raise TableRefused(f"run {name!r}: a range needs both ends (low {lo!r}, high {hi!r})")
    if has_range:
        if not (_number_or_inf(lo) and _number_or_inf(hi)):
            raise TableRefused(f"run {name!r}: a range end is not a number (low {lo!r}, high {hi!r})")
        if float(lo) > float(hi):
            raise TableRefused(f"run {name!r}: the range's low end {lo} is above its high end {hi}")
        if lo == math.inf or hi == -math.inf:
            raise TableRefused(f"run {name!r}: the range ({lo}, {hi}) is empty")
    if est is not None and not _finite(est):
        raise TableRefused(f"run {name!r}: the estimate {est!r} is not a finite number; a run with no estimate gives None")
    if r["status"] == ESTIMATED:
        if est is None:
            raise TableRefused(f"run {name!r}: an estimated run needs a finite estimate")
        if not has_range and not r["failure_in_words"]:
            raise TableRefused(f"run {name!r}: an estimated run with no range says why in failure_in_words")
    else:
        if not r["failure_in_words"]:
            raise TableRefused(f"run {name!r}: a failed run gives its failure in words")
        if has_range:
            raise TableRefused(f"run {name!r}: a failed run has no range (Inference, numerical failures in the analysis)")
    if not isinstance(r["units"], str) or not r["units"]:
        raise TableRefused(f"run {name!r}: units must be named")
    if not isinstance(r["validated"], bool):
        raise TableRefused(f"run {name!r}: validated must be True or False, not {r['validated']!r}")
    if r["validated"] and r["estimator"] != STACKED:
        raise TableRefused(f"run {name!r}: only a stacked run can carry the kernel's validation")
    if r["validated"] and not (r["set"] == HEADLINE_SET and r["threshold"] == HEADLINE_THRESHOLD):
        raise TableRefused(f"run {name!r}: marked validated on {r['set']} at {r['threshold']}; the procedure was validated "
                           "on the headline set at 2% only, so this is refused (the set-name cross-check)")
    return {f: r[f] for f in FIELDS}


def row_input(name: str, estimator: str, set_: str, threshold: float, *, status: str, estimate, range_low, range_high,
              units: str, label: str | None, failure_in_words: str | None, validated: bool) -> dict:
    """One run's mapping, checked. Every argument is required."""
    return check_input({"name": name, "estimator": estimator, "set": set_, "threshold": threshold, "status": status,
                        "estimate": estimate, "range_low": range_low, "range_high": range_high, "units": units,
                        "label": label, "failure_in_words": failure_in_words, "validated": validated})


def validated_by_the_kernel(result: dict) -> bool:
    """Whether an outcome_analysis.estimate result carries the kernel's checked validation: `validation` None AND
    `validation_check.passed` True. A result with no `validation` key is refused: it is not the kernel's."""
    if "validation" not in result:
        raise TableRefused("the stacked result carries no `validation`; it is not an outcome_analysis.estimate result")
    return result["validation"] is None and (result.get("validation_check") or {}).get("passed") is True


def from_stacked_result(name: str, set_: str, threshold: float, result: dict, *, label: str | None = None) -> dict:
    """The mapping from an outcome_analysis.estimate result: headline.log_points, headline.range_90_log_points,
    headline.status and numerical_failure.in_words. Units are log points. A result with a numerical failure is FAILED,
    carrying its point estimate if one computed (labelled with the kernel's status, which says descriptive) and no range.
    `validated` is read from the result (validated_by_the_kernel).
    """
    validated = validated_by_the_kernel(result)
    head = result["headline"]
    est = head.get("log_points")
    est = float(est) if _finite(est) else None
    rng = head.get("range_90_log_points")
    failure = result.get("numerical_failure")
    words = (failure.get("in_words") or failure.get("cause")) if failure else None
    own = label if label is not None else head.get("status")
    if failure is not None or rng is None:
        return row_input(name, STACKED, set_, threshold, status=FAILED if failure is not None or est is None else ESTIMATED,
                         estimate=est, range_low=None, range_high=None, units="log_points", label=own,
                         failure_in_words=words or "no range was returned", validated=validated)
    return row_input(name, STACKED, set_, threshold, status=ESTIMATED, estimate=est, range_low=float(rng[0]),
                     range_high=float(rng[1]), units="log_points", label=own, failure_in_words=None, validated=validated)


def from_callaway_santanna_result(name: str, set_: str, threshold: float, result: dict, *, units: str = "log_points") -> dict:
    """The mapping from a callaway_santanna.run result: headline, range_90, range_label and numerical_failure. The
    outcome the caller gave the package is in `units` (the run's outcome is log price, so log points by default)."""
    est = result.get("headline")
    est = float(est) if _finite(est) else None
    rng = result.get("range_90")
    failure = result.get("numerical_failure")
    if rng is None or failure:
        words = failure or result.get("range_label") or "no range was returned"
        return row_input(name, CALLAWAY_SANTANNA, set_, threshold, status=FAILED if (failure or est is None) else ESTIMATED,
                         estimate=est, range_low=None, range_high=None, units=units, label=result.get("headline_label"),
                         failure_in_words=str(words), validated=False)
    return row_input(name, CALLAWAY_SANTANNA, set_, threshold, status=ESTIMATED, estimate=est, range_low=float(rng[0]),
                     range_high=float(rng[1]), units=units, label=None, failure_in_words=None, validated=False)


def plan_labels(r: dict) -> list:
    """The labels the plan fixes for this run's range (none if it has no range)."""
    if r["range_low"] is None:
        return []
    if r["estimator"] == CALLAWAY_SANTANNA:
        return [CALLAWAY_SANTANNA_RANGE_LABEL]
    if r["validated"]:
        if not (r["set"] == HEADLINE_SET and r["threshold"] == HEADLINE_THRESHOLD):      # check_input refuses it first
            raise TableRefused(f"run {r['name']!r}: validated on a set other than the headline set at 2%")
        return []
    return [NOT_VALIDATED]


def sample_label(r: dict) -> str | None:
    """The Callaway and Sant'Anna row's sample label, with or without a range (D-111): the count on file for the headline
    set at 2%, the label without it on any other set. None for a stacked row."""
    if r["estimator"] != CALLAWAY_SANTANNA:
        return None
    if r["set"] == HEADLINE_SET and r["threshold"] == HEADLINE_THRESHOLD:
        return CALLAWAY_SANTANNA_SAMPLE_LABEL
    return CALLAWAY_SANTANNA_SAMPLE_LABEL_OTHER_SET


def table(results: list) -> dict:
    """The side-by-side table from each run's mapping (see the module docstring).

    Returns
      rows                     one per run, in the order given: the mapping, the plan's labels, the sample label
                               (sample_label; the Callaway and Sant'Anna row only, D-111), and whether it takes part in
                               range comparisons
      gaps                     every unordered pair with two finite estimates: a, b, a_minus_b, size
      exclusions               every ordered pair (A, B) where both have a range: whether A's range excludes B's estimate
      any_range_excludes_another_estimate, ranges_that_exclude (the True entries), largest_gap
      expected_rows_not_supplied   which of the plan's five rows are missing
      need_not_agree, reading  the plan's sentences
    """
    rows = [check_input(r) for r in results]
    names = [r["name"] for r in rows]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise TableRefused(f"run names given twice: {dup}")
    units = sorted({r["units"] for r in rows})
    if len(units) > 1:
        raise TableRefused(f"the runs are in different units {units}; a table compares numbers in one unit")
    out_rows = []
    for r in rows:
        in_cmp = r["range_low"] is not None
        out_rows.append({**r, "plan_labels": plan_labels(r), "sample_label": sample_label(r),
                         "takes_part_in_range_comparisons": in_cmp,
                         "range_low_search_incomplete": in_cmp and r["range_low"] == -math.inf,
                         "range_high_search_incomplete": in_cmp and r["range_high"] == math.inf})
    gaps = []
    for a, b in combinations(out_rows, 2):
        if a["estimate"] is None or b["estimate"] is None:
            continue
        diff = float(a["estimate"]) - float(b["estimate"])
        gaps.append({"a": a["name"], "b": b["name"], "a_minus_b": diff, "size": abs(diff),
                     "involves_an_estimate_with_no_range": not (a["takes_part_in_range_comparisons"]
                                                                and b["takes_part_in_range_comparisons"])})
    exclusions = []
    for a, b in permutations([r for r in out_rows if r["takes_part_in_range_comparisons"]], 2):
        e = float(b["estimate"])
        below, above = e < float(a["range_low"]), e > float(a["range_high"])
        exclusions.append({"range_of": a["name"], "estimate_of": b["name"], "excludes": bool(below or above),
                           "side": "below the range" if below else ("above the range" if above else None)})
    present = {(r["estimator"], r["set"], r["threshold"]) for r in rows}
    hits = [x for x in exclusions if x["excludes"]]
    return {
        "units": units[0] if units else None,
        "rows": out_rows,
        "gaps": gaps,
        "largest_gap": max(gaps, key=lambda g: g["size"]) if gaps else None,
        "exclusions": exclusions,
        "ranges_that_exclude": hits,
        "any_range_excludes_another_estimate": bool(hits),
        "runs_in_no_range_comparison": [{"name": r["name"], "status": r["status"], "failure_in_words": r["failure_in_words"]}
                                        for r in out_rows if not r["takes_part_in_range_comparisons"]],
        "expected_rows_not_supplied": [{"estimator": e, "set": s, "threshold": t} for e, s, t in EXPECTED_ROWS
                                       if (e, s, t) not in present],
        "need_not_agree": NEED_NOT_AGREE,
        "reading": READING,
    }
