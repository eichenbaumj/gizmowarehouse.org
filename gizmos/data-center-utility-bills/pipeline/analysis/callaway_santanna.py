#!/usr/bin/env python3
"""Callaway and Sant'Anna's estimator with two years of anticipation: the sample, the frame, the pinned call, and a
reference computation for tests (PREANALYSIS.md, "Other runs", the bullet "Callaway and Sant'Anna's estimator with two
years of anticipation"; docs/research/callaway-santanna-implementation.md).

Reads NO price. Outcomes are an argument: `frame()` takes an outcome frame supplied by the caller and opens no file to
get one, and `main()` writes a quantity-only summary of the sample.

The owner's ruling of 2026-11-19, which governs the sample (verbatim):

    "For Callaway-Sant'Anna, explicitly preserve applicable load, uncertainty, customer-floor, price-hold, own-utility
    and ownership restrictions. Unknown ownership must not become evidence of independence. Use the proposed
    conservative exclusion of comparisons affiliated with any included host, over the relevant host windows, and
    disclose the resulting sample difference. Apply the adopted assumed-spell convention. The package's observation
    requirements must still use our usable flag. Test the gas-share implementation on invented inputs with a known
    answer and a stated numerical tolerance. A coding failure calls for a bounded repair, not automatic omission of the
    covariate. If the specified estimator cannot be implemented, report that limitation rather than silently
    substituting a different specification."

This run's comparison sample is not the headline's (Joe, 2026-11-19, D-111)
--------------------------------------------------------------------------
His words: "Retain the 680 never-treated units outside the hosts' regions in the specified Callaway-Sant'Anna comparison
sample. Disclose this sample difference prominently; differences from the headline estimate cannot be attributed solely
to the estimator." On the headline set at 2%, 680 of the 1,670 never-treated units are in no cohort's host region at
that cohort's reference year (g-3), and 605 of them are in none of the four host regions (West, ERCOT, SPP, Southeast) at
any of the five reference years (docs/gate1/callaway-santanna-regions-without-host-2026-11-19.md, counted from sample()
on quantity files). The headline's matched comparison utilities come from each host's own region in its reference year.
These units stay here and region enters as a covariate. A difference between this run's estimate and the headline
estimate cannot be attributed solely to the estimator. sample_difference() and the summary carry this first
(REGION_SAMPLE_DIFFERENCE).

What is here
------------
sample()            treated units (the set's hosts with their cohorts) and never-treated units (the comparison-eligible
                    units of the main design), each restriction a named step with the units it removes.
frame()             the long frame the package takes: one row per USABLE unit-year and nothing else.
run()               the pinned call on diff-diff 4.0.0, imported lazily; refuses in words if the package is missing or
                    is another version, and never falls back to anything else.
reference_att(), reference_event_study()
                    the outcome-regression estimator written directly in numpy, a REFERENCE FOR TESTS. It is not the
                    run and is never reported as an estimate.
sample_difference() what the never-treated sample differs in from the main design's matched comparison utilities.
main()              writes data/frozen/callaway_santanna_sample.json (quantities only, provisional).

Observation requirements (the agent's reading of the plan and the ruling, written down here)
---------------------------------------------------------------------------------------------
The plan pins `allow_unbalanced_panel=False` "(each group-time effect on units observed at g-3 and t; the
repeated-cross-section option is not used)". The research note found by running that diff-diff computes each ATT(g, t)
on the units that have a row at both g-3 and t (its exiting units were units whose rows stop). So "observed" is coded as
"has a row", and a row exists only where the usable flag says the unit-year is usable (`res_price_usable`, read through
usable_flag.read). A unit-year that is not usable has NO ROW, never a row with a missing outcome: how the package treats
a missing outcome value inside a present row was not tested, and a missing row is what was tested. A usable unit-year
whose outcome the caller did not supply stops the frame in words (a missing input is reported, not worked around).

Never-treated units are NOT additionally required to be usable over a whole window. The main design's rule 4 (usable in
all ten years of the host's window, applied before matching) is per host, and one never-treated unit serves every cohort
at once in this estimator; the plan's own wording for this run is the pairwise one above. Hosts ARE required to have a
full usable window: the plan's set rules move a host without one out of the set ("named and moved to a side run"), so
they are not the set's hosts. With full windows the hosts are observed at g-3 and every t of their window, so the
pairwise rule only ever trims never-treated units.

Unknown ownership in part of a window
-------------------------------------
Rule 2.2 is read year by year in every design (Joe, 2026-11-19, D-107): ownership.ineligible_for bars an investor-owned
candidate for an investor-owned host when some year of the host's window has no row covering it. This sample applies that
same rule through STEP_OWNERSHIP, host by host over the included hosts, union taken: "Unknown ownership must not become
evidence of independence". Units barred although a row covers part of the window are named apart, with their uncovered
years (Sample.unknown_ownership_year_exclusions). Until that ruling this exclusion was a separate step labelled the
session's reading for this run only; it is now the main design's own rule and no longer a separate step.

Covariates and the region of a unit that changes region
-------------------------------------------------------
Market region enters as 0/1 dummy columns, one region left out, read YEAR BY YEAR from market_region.by_unit_year, and
the state's 2008 to 2010 gas share (power_simulation.load_gas_share; power_simulation.gas_share_of_rows, which stops on a
missing state rather than filling it). The frame carries each unit-year's own region and relies on the package reading
it at g-3, which gives a unit's region in the cohort's reference year, the region the main design matches on. A frame
cannot carry one fixed region per never-treated unit, since one never-treated unit serves cohorts with different
reference years. The reference computation reads covariates at g-3 explicitly.

What the installed package does, checked 2026-11-19 on diff-diff 4.0.0 (installed in the gizmo folder's .venv; source
lines below are in .venv/lib/python3.13/site-packages/diff_diff/) and pinned by tests on invented inputs in
tests/test_callaway_santanna_package.py:

  Covariate timing. Covariates are read at the base period of each ATT(g, t), for treated and comparison units alike,
  never at t: staggered.py 879-885 keeps one covariate matrix per period, and both regression paths take the matrix of
  the base period (staggered.py 1084-1089, the per-cell path the state-clustered call takes; staggered.py 1489 and
  1615-1616, the vectorized path the unit-level call takes). The base period is the last observed period p with
  p + 2 < g (staggered.py 248-261), which is g-3 on the frame's consecutive years.

  Covariance and range. With n_bootstrap=999 the event-study result's covariance is the covariance (ddof=1) of the
  multiplier-bootstrap draws, not the analytic influence-function covariance (staggered_results.py 484-501;
  staggered_bootstrap.py 704-718), and each event year's standard error is the standard deviation of the same draws
  (bootstrap_utils.py 465-466), so the covariance's diagonal is the squared standard errors. The package's own interval
  for an event year is a percentile interval of the draws at its alpha, 0.05 by default, so 95% (bootstrap_utils.py
  469-471, 996-1023), and it applies no degrees of freedom (the event study's df is cleared, staggered_results.py 501).
  The package gives no interval for the mean of two event years. The headline's standard error here, the square root of
  w' V w with V that covariance, is therefore the standard deviation of the bootstrap draws of 0.5 x (ES(2) + ES(3)).
  The 90% range is this module's t-based construction on that standard error: the headline plus or minus the t critical
  value on the number of states less one, times the standard deviation of the bootstrap draws of the headline. The
  package's multiplier bootstrap supplies the standard error and nothing else; the range is not the package's and is
  never described as the package's. Joe accepted this construction on 2026-11-19 (D-105), in his words: "Accept the
  Callaway–Sant'Anna interval as the explicitly described t-based construction using its bootstrap standard error,
  labelled secondary and uncalibrated. Do not call it the package's interval or launch another validation campaign."
  RANGE_LABEL carries both words, secondary and uncalibrated. The weights are drawn per state with cluster="state" and per unit with cluster=None
  (staggered.py 355-366, 2137-2148), and which weights the seed produces depends on the package's weight backend, "rust"
  in this install (bootstrap_chunking.py 73-87); run() records the backend.

  Aggregation weights. They depend on the cluster argument. With cluster="state" the package builds a survey design with
  the state as the primary sampling unit and unit weights of one (staggered.py 2137-2148, 889-895), and every event-study
  horizon then weights each cohort by its number of units in the WHOLE frame (staggered_aggregation.py 64-91 and
  918-931). With cluster=None the weight is the number of the cohort's units observed at both g-3 and t (the cell's
  n_treated, staggered.py 1056-1062 and staggered_aggregation.py 926-931). The two agree whenever every host has a row in
  every year of its window, which sample() guarantees (a host without a full usable window is not one of the set's
  hosts). On a frame where they differ, the state-clustered and the unit-level calls return different point estimates,
  and run() reports both and whether they agree.

  Covariates dropped by the package. With its default rank_deficient_action="warn" the package drops a linearly
  dependent covariate column with a warning, and it falls back to an estimate without covariates, with a warning, in a
  cell where a covariate is missing (rank deficiency: staggered.py 1548-1557, linalg.py 1818-1825; missing covariate:
  staggered.py 1091-1100, 1620-1632). Neither may pass silently (the ruling: a coding failure is not a reason to leave
  the covariate out), so run() records every such warning and labels the result a numerical failure.

Stated differences from the main estimate (PREANALYSIS.md): the comparison sample, first, as above (D-111); no
ten-closest-in-size restriction (neither package does nearest-neighbour matching); the comparison group is every
never-treated unit, not each host's ten, never-treated units in a region with no host staying in; region and gas share
enter as covariates in an outcome regression, not as region-by-year effects within matched sets and gas share by
calendar year; no degree-day controls; the range is secondary and uncalibrated, the module's t-based construction (the
headline plus or minus the t critical value on the number of states less one, times the standard deviation of the
bootstrap draws of the headline), its standard error from the package's multiplier bootstrap on the influence function by
state with no refit; it is not one of step E's candidates and not calibrated by the inference comparison.

Run:  python3 -I pipeline/analysis/callaway_santanna.py      writes data/frozen/callaway_santanna_sample.json
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
OUT = FROZEN / "callaway_santanna_sample.json"
KEY = ps.KEY

# ---- the pinned call (PREANALYSIS.md, "Other runs"; Joe, D-99) ---------------------------------------------------------
PINNED_PACKAGE = "diff-diff"
PINNED_VERSION = "4.0.0"
SEED = 20261204                                   # used nowhere else; fixed 2026-11-19
PINNED_CALL = dict(control_group="never_treated", anticipation=2, base_period="universal", estimation_method="reg",
                   cluster="state", n_bootstrap=999, bootstrap_weights="rademacher", seed=SEED, cband=False,
                   allow_unbalanced_panel=False)
ANTICIPATION = 2
BASE_OFFSET = -(ANTICIPATION + 1)                 # every event year measured against g-3
HEADLINE = (2, 3)
EVENT_YEARS = tuple(range(-ps.PRE, ps.POST + 1))  # -6 .. 3 are read from the event study
LEVEL = 0.90
NEVER_TREATED = 0                                 # the package's never-treated coding of first_treat (research note)
YEARS = tuple(range(ps.COHORTS[0] - ps.PRE, ps.COHORTS[1] + ps.POST + 1))   # 2005 .. 2025, every window year

PLAN_UNCALIBRATED_WORDS = "not calibrated by the inference comparison"     # the plan's words (Reported checks)
RANGE_LABEL = ("secondary and uncalibrated: a t-based range, the headline plus or minus the t critical value on the number "
               "of states less one times the bootstrap standard error of the headline (the module's construction, accepted "
               "by Joe on 2026-11-19, D-105); " + PLAN_UNCALIBRATED_WORDS)
RANGE_TEXT = ("Secondary and uncalibrated. The range is this module's t-based construction: the headline plus or minus the "
              "t critical value on G - 1 degrees of freedom, G the number of states, times the headline's standard error. "
              "The standard error is the standard deviation of the bootstrap draws of the headline, from the package's "
              "multiplier bootstrap on the influence function by state with no refit (Rademacher weights, 999 draws, seed "
              "20261204), taken from the covariance of the event-study draws. The package supplies the standard error, not "
              "the range: its own intervals are 95% percentile intervals for single event years, which are not used, and "
              "it gives none for the mean of two event years. Joe accepted the construction on 2026-11-19 (D-105), "
              "labelled secondary and uncalibrated. Not one of step E's candidates and not calibrated by the inference "
              "comparison. In the tests of 2026-11-14 on made-up data, intervals covered a few points short of 90%.")
RANGE_DIFFERENCE = ("the range is secondary and uncalibrated: the module's t-based construction (the headline plus or minus "
                    "the t critical value on the number of states less one, times the standard deviation of the bootstrap "
                    "draws of the headline), its standard error from the package's multiplier bootstrap; "
                    + PLAN_UNCALIBRATED_WORDS)
COVARIATE_WARNING = ("rank-deficient", "falling back to unconditional", "missing values in covariates")

# ---- the comparison sample against the headline's (Joe, 2026-11-19, D-111; module docstring) ---------------------------
ESTIMATOR_ATTRIBUTION = ("A difference between this run's estimate and the headline estimate cannot be attributed solely "
                         "to the estimator.")
REGION_SAMPLE_DIFFERENCE = (
    "This run's comparison sample differs from the headline's. On the headline set at 2%, 680 of the 1,670 never-treated "
    "units are in no cohort's host region at that cohort's reference year (g-3), and 605 of them are in none of the four "
    "host regions (West, ERCOT, SPP, Southeast) at any of the five reference years (counted 2026-11-19 from this module's "
    "sample() on quantity files; docs/gate1/callaway-santanna-regions-without-host-2026-11-19.md). The headline's matched "
    "comparison utilities come from each host's own region in its reference year. These units stay in this run's sample "
    "by Joe's ruling of 2026-11-19 (D-111) and inform the gas-share slope, region entering as a covariate. "
    + ESTIMATOR_ATTRIBUTION)
REGION_SAMPLE_DIFFERENCE_OTHER_SET = (
    "This run's comparison sample differs from the headline's. Never-treated units in no host's region at a cohort's "
    "reference year (g-3) stay in this run's sample by Joe's ruling of 2026-11-19 (D-111), region entering as a covariate. "
    "The count on file (680 of 1,670 never-treated units, 605 on the stricter count) is for the headline set at 2% and was "
    "not made for this set. " + ESTIMATOR_ATTRIBUTION)


def region_sample_difference(theta: float, which: str) -> str:
    """The disclosure for a set: with the count on file for the headline set at 2%, without it for any other set."""
    return REGION_SAMPLE_DIFFERENCE if (which == ps.HEADLINE_SET and theta == 0.02) else REGION_SAMPLE_DIFFERENCE_OTHER_SET

# ---- step names (each removes units and is counted) ----------------------------------------------------------------
STEP_LOAD = "load"
STEP_ASIDE = "set_aside"
STEP_UNKNOWN = "uncertainty_load_unknown"
STEP_FLOOR = "customer_floor"
STEP_HOLD = "price_hold"
STEP_INPUTS = "main_design_window_inputs"
STEP_OWN = "own_utility"
STEP_OWNERSHIP = "ownership_any_included_host"
# Until 2026-11-19 a ninth step, "investor_owned_with_a_year_of_unknown_ownership_in_an_investor_owned_hosts_window",
# removed units with a row for part of an investor-owned host's window. Joe's ruling of that day (D-107) made rule 2.2
# year by year in every design, so ownership.ineligible_for removes them in STEP_OWNERSHIP and the step is gone.
STEPS = (STEP_LOAD, STEP_ASIDE, STEP_UNKNOWN, STEP_FLOOR, STEP_HOLD, STEP_INPUTS, STEP_OWN, STEP_OWNERSHIP)
UNKNOWN_YEARS_LABEL = "unknown ownership in these years is not evidence of independence"
UNKNOWN_YEARS_READING = ("Rule 2.2 read year by year, the main design's own rule (Joe, 2026-11-19, D-107): an investor-owned "
                         "unit with a year of an investor-owned included host's window that no ownership row covers is "
                         "excluded by ownership.ineligible_for, because unknown ownership must not become evidence of "
                         "independence. Those with a row for part of the window are named apart with their uncovered "
                         "years. The one difference from the main design is the union: here a unit barred for one host is "
                         "out for every cohort, where the main design bars it only for the hosts whose windows it does not "
                         "cover.")
STEP_RULE = {
    STEP_LOAD: ("Comparison utilities, rule 2: under 0.5% in every year as built (power_simulation.design takes the largest "
                "share over all years), no crypto-mining load of 2% or more, and a unit with load but no 2009-2011 sales "
                "cannot be shown clean. Every host, early host and late host fails it, so none is a never-treated unit."),
    STEP_ASIDE: ("Comparison utilities, rule 2: not set aside on either side (power_simulation.set_aside, as design.split "
                 "applies it to the set's comparison utilities): every admissible history and no anchoring."),
    STEP_UNKNOWN: ("Comparison utilities, rule 2 (D-96 item 2): a unit reached by a site with no load history is eligible only "
                   "if the enumeration decided it (UnknownLoad.gate, as design.build_with_rules applies it)."),
    STEP_FLOOR: ("Unit: at least 2,000 residential customers. A unit that meets the customer floor in no year has no "
                 "usable year; in every other unit the floor enters year by year through the usable flag."),
    STEP_HOLD: "Comparison utilities, rule 5: not in price_hold.csv.",
    STEP_INPUTS: ("The agent's reading: the never-treated units are the comparison-eligible units of the main design, whose "
                  "windows hold only units whose state has a 2008-2010 gas share and degree days (power_simulation."
                  "build_windows); Alaska and Hawaii are outside every run with degree-day controls."),
    STEP_OWN: "Comparison utilities, rule 3: a unit sharing an EIA id with any included host (D-54 ruling 2).",
    STEP_OWNERSHIP: ("Comparison utilities, rule 3, under the owner's ruling of 2026-11-19: a unit ownership.ineligible_for "
                     "excludes for ANY included host, over THAT host's window (g-6 to g+3), the union over hosts. Same "
                     "ultimate parent in a window year (documented and assumed spell ends both entering, each labelled), "
                     "or investor-owned with no ownership row covering some year of the window of an investor-owned host "
                     "(rule 2.2 read year by year, D-107: unknown ownership is not evidence of independence). A unit "
                     "with a row for part of that window is named apart with its uncovered years."),
}

HOST_EARLY = "early host: first crossing before 2011 (on neither side)"
HOST_LATE = "late host: first crossing in 2023 or later (on neither side)"
HOST_NOT_USABLE = ("no usable outcome in every year of its window: the plan's set rules move such a host out of the set "
                   "(named and moved to a side run), so it is not one of the set's hosts here")


class PackageMissing(RuntimeError):
    """diff-diff is not installed; the run is not made and nothing is substituted for it."""


class PackageVersionRefused(RuntimeError):
    """diff-diff is installed at a version other than the pinned one; the run is not made."""


class ReferenceFailure(RuntimeError):
    """The reference computation cannot be computed for a group and year (a rank-deficient comparison regression, or no
    treated or never-treated unit observed at both g-3 and t). Counted and reported, never dropped silently."""


# ---- the sample --------------------------------------------------------------------------------------------------------

@dataclass
class Sample:
    """Treated units with their cohorts, never-treated units, and every step with what it removed."""
    theta: float
    which: str
    hosts: pd.DataFrame                    # utility_id_eia, state, cohort
    never_treated: pd.DataFrame            # utility_id_eia, state
    steps: list = field(default_factory=list)          # [{"step", "rule", "removed", "units", "remaining"}]
    hosts_dropped: list = field(default_factory=list)  # [{"utility", "cohort", "why"}]
    hosts_neither_side: dict = field(default_factory=dict)
    ownership_exclusions: dict = field(default_factory=dict)   # (u, st) -> [{"host", "why", "basis"}]
    # the units of ownership_exclusions barred under rule 2.2 although a row covers part of the host's window
    unknown_ownership_year_exclusions: dict = field(default_factory=dict)   # (u, st) -> [{"host", "uncovered_years", "label"}]

    def removed_by(self, step: str) -> set:
        return {tuple(_key(x)) for s in self.steps if s["step"] == step for x in s["units"]}


def _key(x) -> tuple:
    if isinstance(x, str):
        u, st = x.split(":")
        return (int(u), st)
    return (int(x[0]), str(x[1]))


def _label(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def first_crossings(dose: pd.DataFrame, theta: float, history: dict | None = None) -> pd.Series:
    """Each unit's first year at or over `theta`, with D-34's utility-level histories as power_simulation.design applies
    them. Used only to COUNT the early and late hosts that design() leaves on neither side."""
    first = dose[dose.dose >= theta].groupby(KEY).year.min()
    for k, v in (history or {}).items():
        if v["group"] == "cohort":
            first[k] = int(v["first_crossing"])
        else:
            first = first.drop(k, errors="ignore")
            if v["group"] == "early":
                first[k] = ps.COHORTS[0] - 1
    return first


def aside_sets(theta: float, which: str, frozen: Path | None = None) -> tuple[set, set]:
    """(set aside as hosts, set aside as comparison utilities) for a named set, exactly as design.split applies them.

    Every cohort utility as built sets no one aside on either side; the headline set and the set with the ten-year case
    take power_simulation.set_aside on both sides; the headline set plus the hosts unsettled on assignment takes the
    headline's comparison utilities and puts those hosts back."""
    from pipeline.analysis import design as dsg
    if which == "every_cohort_utility":
        return set(), set()
    aside = ps.set_aside(theta, frozen, ten_year_case=(which == ps.TEN_YEAR_SET))
    if which == dsg.PLUS_UNSETTLED:
        lists = ps.bounds_lists(theta, frozen)
        other = {k for k, why in ps.dates_and_histories_reasons(theta, frozen).items()
                 if any(not x.startswith(ps.TEN_YEAR_REASON) for x in why)}
        return other | lists["does_not_keep_its_place"], aside
    return aside, aside


def _row_basis(rows: pd.DataFrame) -> list:
    if not len(rows):
        return []
    if not all(c in rows.columns for c in own_rules.BASIS):
        return [{"utility": _label((r.utility_id_eia, r.state or "every state")), "parent": r.ultimate_parent,
                 "spell": [int(r.from_year), int(r.to_year)], "basis": "no basis columns in the table"} for r in rows.itertuples()]
    return [{"parent": r.ultimate_parent, "spell": [int(r.from_year), int(r.to_year)],
             "from_year_basis": r.from_year_basis, "to_year_basis": r.to_year_basis} for r in rows.itertuples()]


def ownership_basis(table: pd.DataFrame, host: tuple, cand: tuple, years) -> dict:
    """What a same-parent exclusion rests on, labelled (Joe, D-99: documented and assumed spell ends both enter, each
    labelled). Lists every year a parent is shared and the covering rows of both units with their bases.

    label  "documented at both ends"        every row it rests on is documented at both ends
           "assumed at both ends (ownership convention)"   at least one row it rests on is assumed at both ends: under the
                                            plan such a row counts as a row (the table admits a row only with a source
                                            and a quote; see the module's report on the parent-identity mark)
           "rests on an assumed spell end"  otherwise, at least one end assumed
           "no basis columns"               an invented table without the basis columns
    """
    shared, rows = [], []
    for y in years:
        common = own_rules.parents(table, host, [y]) & own_rules.parents(table, cand, [y])
        if common:
            shared.append(int(y))
            for k in (host, cand):
                r = own_rules._rows(table, k, [y])
                rows.append(r[r.ultimate_parent.isin(common)])
    used = pd.concat(rows).drop_duplicates() if rows else pd.DataFrame(columns=own_rules.COLUMNS)
    if not len(used):
        label = None
    elif not all(c in used.columns for c in own_rules.BASIS):
        label = "no basis columns"
    elif ((used.from_year_basis == "assumed") & (used.to_year_basis == "assumed")).any():
        label = "assumed at both ends (ownership convention)"
    elif ((used.from_year_basis == "assumed") | (used.to_year_basis == "assumed")).any():
        label = "rests on an assumed spell end"
    else:
        label = "documented at both ends"
    return {"shared_parent_years": shared, "label": label, "rows": _row_basis(used)}


def sample(theta: float, which: str, q: pd.DataFrame, dose: pd.DataFrame, *, host_aside: set, comparison_aside: set,
           hold: set, unknown_load: "ps.UnknownLoad", ownership: pd.DataFrame, ownership_of: dict, usable: set,
           gas: dict, dd_states: set, history: dict | None = None, names: pd.Series | None = None) -> Sample:
    """The Callaway and Sant'Anna sample for one set at one threshold, every restriction a named, counted step.

    Hosts: power_simulation.design's cohort utilities (first crossing 2011 to 2022; early and late hosts are on neither
    side and counted), less `host_aside` (design.split), less those a load-unknown site reaches that the enumeration did
    not decide, less those without a full usable window (named; see the module docstring).

    Never-treated units, in order (STEPS): load (power_simulation.design with no price hold, so the hold is its own
    step), set aside, load unknown, customer floor, price hold, the main design's window inputs, own utility, ownership
    over the included hosts. Ownership reuses ownership.ineligible_for host by host, each over its own window, and takes
    the union; nothing about affiliation is re-implemented here. Rule 2.2 there is read year by year (D-107), and the
    units it bars although a row covers part of the window are named in unknown_ownership_year_exclusions.

    Every input is passed in; nothing is read from disk. `usable` is usable_flag.read().usable; `ownership` is
    ownership.load(); `ownership_of` is power_simulation.ownership_classes(q); `dd_states` the states with degree days.
    """
    unknown_load = ps.require_unknown_load(unknown_load)
    names = names if names is not None else pd.Series(dtype=object)
    nm = lambda k: None if names is None else names.get(k)  # noqa: E731
    treated, clean_load = ps.design(q, dose, theta, history, hold=set())
    out = Sample(theta, which, treated.iloc[0:0][KEY + ["cohort"]], clean_load.iloc[0:0][KEY])

    # -- hosts -------------------------------------------------------------------------------------------------------
    first = first_crossings(dose, theta, history)
    out.hosts_neither_side = {
        HOST_EARLY: sorted(_label(k) for k, g in first.items() if g < ps.COHORTS[0]),
        HOST_LATE: sorted(_label(k) for k, g in first.items() if g > ps.COHORTS[1])}
    hosts = treated[[(int(u), s) not in host_aside for u, s in zip(treated.utility_id_eia, treated.state)]]
    hosts, gated = unknown_load.gate(hosts, theta, "host")
    out.hosts_dropped += [{"utility": x["utility"], "cohort": None, "why": x["why"]} for x in gated]
    keep = []
    for r in hosts.itertuples():
        k, g = (int(r.utility_id_eia), r.state), int(r.cohort)
        if all((k[0], k[1], y) in usable for y in ownership_window(g)):
            keep.append(True)
        else:
            keep.append(False)
            out.hosts_dropped.append({"utility": _label(k), "name": nm(k), "cohort": g, "why": HOST_NOT_USABLE})
    hosts = hosts[np.array(keep, dtype=bool)] if len(hosts) else hosts
    out.hosts = hosts[KEY + ["cohort"]].reset_index(drop=True).astype({"utility_id_eia": int, "cohort": int})
    host_list = [((int(u), s), int(g)) for u, s, g in zip(out.hosts.utility_id_eia, out.hosts.state, out.hosts.cohort)]

    # -- never-treated -----------------------------------------------------------------------------------------------
    universe = {(int(u), s) for u, s in q[KEY].drop_duplicates().itertuples(index=False)}
    remaining = set(universe)

    def step(name: str, removed: set, detail: dict | None = None):
        removed = removed & remaining
        remaining.difference_update(removed)
        entry = {"step": name, "rule": STEP_RULE[name], "removed": len(removed),
                 "units": sorted(_label(k) for k in removed), "remaining": len(remaining)}
        if detail:
            entry.update(detail)
        out.steps.append(entry)

    load_ok = {(int(u), s) for u, s in clean_load.itertuples(index=False)}
    cohort_hosts = {(int(u), s) for u, s in zip(treated.utility_id_eia, treated.state)}
    step(STEP_LOAD, universe - load_ok, {"of_which_cohort_utilities_at_this_threshold": len(cohort_hosts - load_ok)})
    step(STEP_ASIDE, set(comparison_aside))
    frame_left = pd.DataFrame(sorted(remaining), columns=KEY)
    _, gated = unknown_load.gate(frame_left, theta, "comparison")
    step(STEP_UNKNOWN, {_key(x["utility"]) for x in gated})
    floor = {(int(u), s) for u, s in q[q.meets_size_floor.astype(bool)][KEY].drop_duplicates().itertuples(index=False)}
    step(STEP_FLOOR, universe - floor)
    step(STEP_HOLD, {(int(u), s) for u, s in hold})
    step(STEP_INPUTS, {k for k in remaining if k[1] not in dd_states or k[1] not in gas or not np.isfinite(gas[k[1]])})
    host_ids = {k[0] for k, _ in host_list}
    step(STEP_OWN, {k for k in remaining if k[0] in host_ids})
    excl: dict = {}
    unknown_years: dict = {}
    # Only a candidate with a row in the table (a parent to share) or an investor-owned one (rule 2.2's bar) can be
    # excluded by ineligible_for once the own-utility step has run; the others are passed over for speed only. The
    # result is the same: ineligible_for returns nothing for a unit with no row that is not investor-owned.
    in_table = set(zip(ownership.utility_id_eia.astype(int), ownership.state)) if len(ownership) else set()
    ids_every_state = set(ownership[ownership.state == ""].utility_id_eia.astype(int)) if len(ownership) else set()
    cands = sorted(k for k in remaining if k in in_table or k[0] in ids_every_state
                   or own_rules._ownership(ownership_of, k) == own_rules.INVESTOR_OWNED)
    for hk, g in host_list:
        years = ownership_window(g)
        why = own_rules.ineligible_for(ownership, hk, years, cands, ownership_of)
        for c, reason in why.items():
            if reason == own_rules.OWN_UTILITY:          # removed by the own-utility step already; cannot reach here
                continue
            rec = {"host": _label(hk), "host_name": nm(hk), "cohort": g, "why": reason}
            if reason == own_rules.SAME_PARENT:
                rec["basis"] = ownership_basis(ownership, hk, c, years)
            else:
                missing = [y for y in years if not len(own_rules._rows(ownership, c, [y]))]
                if len(missing) < len(years):                # a row covers part of the window (rule 2.2 read year by year)
                    rec["basis"] = {"label": f"no ownership row covering {len(missing)} of the host's window years; "
                                             "unknown ownership is not evidence of independence (rule 2.2 read year by "
                                             "year, Joe, 2026-11-19, D-107)", "uncovered_years": missing}
                    unknown_years.setdefault(c, []).append({"host": _label(hk), "host_name": nm(hk), "cohort": g,
                                                            "uncovered_years": missing, "label": UNKNOWN_YEARS_LABEL})
                else:
                    rec["basis"] = {"label": "no ownership row covering any year of the host's window; unknown ownership is "
                                             "not evidence of independence (the owner's ruling of 2026-11-19; rule 2.2)"}
            excl.setdefault(c, []).append(rec)
    out.ownership_exclusions = excl
    out.unknown_ownership_year_exclusions = unknown_years
    only_partial = sorted(_label(c) for c, v in excl.items() if c in unknown_years
                          and all(x["why"] == own_rules.NO_ROW and "uncovered_years" in x["basis"] for x in v))
    step(STEP_OWNERSHIP, set(excl), {"by_reason": {r: sum(any(x["why"] == r for x in v) for v in excl.values())
                                                   for r in (own_rules.SAME_PARENT, own_rules.NO_ROW)},
                                     "resting_on_an_assumed_spell": sorted(_label(c) for c, v in excl.items() if any(
                                         x["why"] == own_rules.SAME_PARENT and x["basis"]["label"] != "documented at both ends"
                                         for x in v)),
                                     "with_a_row_for_part_of_an_investor_owned_hosts_window": sorted(_label(c) for c in unknown_years),
                                     "removed_only_for_a_row_for_part_of_a_window": only_partial})
    out.never_treated = pd.DataFrame(sorted(remaining), columns=KEY)
    return out


def ownership_window(g: int) -> list:
    return own_rules.window_years(g)


# ---- the frame ----------------------------------------------------------------------------------------------------------

def region_column(region: str) -> str:
    return "region_" + "".join(ch if ch.isalnum() else "_" for ch in str(region))


@dataclass
class Frame:
    data: pd.DataFrame
    covariates: list
    region_left_out: str | None
    report: dict


def frame(s: Sample, regions: pd.DataFrame, gas: dict, outcomes: pd.DataFrame, usable: set,
          outcome: str = "outcome") -> Frame:
    """The long frame the package takes, one row per USABLE unit-year (module docstring).

    regions   market_region.by_unit_year(q): KEY + year + region
    gas       state -> 2008-2010 gas share (power_simulation.load_gas_share)
    outcomes  supplied by the caller: KEY + year + `outcome`. This function never opens a file to get it.
    usable    usable_flag.read().usable

    Hosts have rows only in their own window (g-6 to g+3): the event years read are -6 to 3, and with
    allow_unbalanced_panel=False each ATT(g, t) uses only the rows at g-3 and t. Never-treated units have rows in every
    usable year from 2005 to 2025. first_treat is the cohort for hosts and 0 for never-treated units. `state` is the
    cluster. Region dummies are each unit-year's own region (the package reads covariates at the base period); one region
    is left out, the first in sorted order among those in the frame. A usable unit-year with no outcome, or a
    non-finite outcome, stops in words. An outcome supplied for a unit-year that is not usable is not used, and counted.
    """
    if outcome not in outcomes.columns:
        raise ValueError(f"the outcome frame has no {outcome!r} column")
    if outcomes.duplicated(KEY + ["year"]).any():
        raise ValueError("the outcome frame repeats a (utility_id_eia, state, year) key; stopping")
    units = [((int(u), s), int(g)) for u, s, g in zip(s.hosts.utility_id_eia, s.hosts.state, s.hosts.cohort)]
    units += [((int(u), st), NEVER_TREATED) for u, st in zip(s.never_treated.utility_id_eia, s.never_treated.state)]
    rows, not_usable = [], 0
    for k, g in units:
        years = range(g - ps.PRE, g + ps.POST + 1) if g else YEARS
        for y in years:
            if (k[0], k[1], y) in usable:
                rows.append((k[0], k[1], y, g))
            else:
                not_usable += 1
    f = pd.DataFrame(rows, columns=KEY + ["year", "first_treat"])
    o = outcomes[KEY + ["year", outcome]].astype({"utility_id_eia": int, "year": int})
    f = f.merge(o, on=KEY + ["year"], how="left")
    bad = f[~np.isfinite(f[outcome].astype(float))]
    if len(bad):
        raise ValueError(f"{len(bad)} usable unit-years have no finite outcome in the frame supplied; the frame is not "
                         "built and nothing is filled (first: "
                         f"{_label((bad.utility_id_eia.iloc[0], bad.state.iloc[0]))} {int(bad.year.iloc[0])})")
    in_frame = set(zip(f.utility_id_eia, f.state, f.year))
    unit_keys = {k for k, _ in units}
    supplied_unused = sum((int(u), s) in unit_keys and (int(u), s, int(y)) not in in_frame
                          for u, s, y in zip(o.utility_id_eia, o.state, o.year))
    reg = regions[KEY + ["year", "region"]].astype({"utility_id_eia": int, "year": int})
    f = f.merge(reg, on=KEY + ["year"], how="left")
    if f.region.isna().any():
        n = int(f.region.isna().sum())
        raise ValueError(f"{n} usable unit-years have no market region; stopping")
    present = sorted(f.region.unique())
    left_out = present[0] if present else None
    covs = []
    for r in present[1:]:
        c = region_column(r)
        f[c] = (f.region == r).astype(float)
        covs.append(c)
    f["gas_share"] = ps.gas_share_of_rows(f.state.values, gas)
    covs.append("gas_share")
    codes = {k: i + 1 for i, k in enumerate(sorted({k for k, _ in units}))}
    f.insert(0, "unit_id", [codes[(int(u), s)] for u, s in zip(f.utility_id_eia, f.state)])
    f = f.sort_values(["unit_id", "year"]).reset_index(drop=True)
    movers = (f.groupby("unit_id").region.nunique() > 1)
    rep = {"rows": int(len(f)), "units": int(f.unit_id.nunique()), "hosts": int((f.groupby("unit_id").first_treat.first() > 0).sum()),
           "unit_years_not_usable_and_without_a_row": int(not_usable),
           "outcome_values_supplied_for_unit_years_without_a_row": int(max(supplied_unused, 0)),
           "region_left_out": left_out, "covariates": covs,
           "units_whose_region_changes_inside_the_frame": int(movers.sum()),
           "observation_rule": "a row exists only for a usable unit-year (res_price_usable); the package's "
                               "allow_unbalanced_panel=False then uses units with rows at g-3 and t"}
    return Frame(f, covs, left_out, rep)


# ---- the pinned call ---------------------------------------------------------------------------------------------------

def _import_pinned():
    """diff_diff at the pinned version, or a refusal in words. Never a fallback."""
    try:
        import diff_diff  # noqa: F401
    except ImportError as e:
        raise PackageMissing(f"{PINNED_PACKAGE}=={PINNED_VERSION} (import diff_diff) is not installed, so Callaway and "
                             "Sant'Anna's estimator cannot be run. Nothing is substituted for it (the owner's ruling of "
                             "2026-11-19): install the pinned version and run again, or report the limitation.") from e
    v = getattr(diff_diff, "__version__", None)
    if v != PINNED_VERSION:
        raise PackageVersionRefused(f"{PINNED_PACKAGE} is installed at version {v!r}, not the pinned {PINNED_VERSION}; the "
                                    "plan pins that version exactly (D-99), so the run is refused. Nothing is substituted.")
    return diff_diff


def _get(obj, name: str):
    if not hasattr(obj, name):
        raise AttributeError(f"the package's event-study result has no {name!r}; this call is written against the names the "
                             "research note of 2026-11-14 records (event_time, att, se, vcov, vcov_index). A bounded repair "
                             "of this mapping is needed; nothing is substituted.")
    return getattr(obj, name)


def headline_from_event_study(es) -> dict:
    """0.5 x (ATT(2) + ATT(3)) and its standard error w' V w from the event-study covariance, with every event year -6 to
    3. A non-finite value is a numerical failure: reported with its cause, no range.

    Under the pinned call V is the covariance of the bootstrap draws (module docstring), so w' V w is the variance of the
    draws of the headline. The package stores no covariance (vcov None) when a covered horizon has a non-finite draw or
    fewer than two clusters (staggered_bootstrap.py 92-98), and leaves out of vcov_index a horizon whose bootstrap
    standard error is not finite; either case for event year 2 or 3 is a numerical failure with the point estimate kept
    and labelled descriptive."""
    times = [int(x) for x in np.asarray(_get(es, "event_time")).ravel()]
    att = np.asarray(_get(es, "att"), dtype=float).ravel()
    vi, Vraw = _get(es, "vcov_index"), _get(es, "vcov")
    idx = [] if vi is None else [int(x) for x in np.asarray(vi).ravel()]
    by_e = dict(zip(times, att))
    out = {"event_years": {str(e): (float(by_e[e]) if e in by_e else None) for e in EVENT_YEARS}}
    missing = [e for e in HEADLINE if e not in by_e]
    if missing:
        out.update(headline=None, se=None, numerical_failure=f"event years {missing} not in the package's event study")
        return out
    est = float(sum(by_e[e] for e in HEADLINE) / len(HEADLINE))
    uncovered = [e for e in HEADLINE if e not in idx]
    if Vraw is None or uncovered:
        why = ("the package stored no event-study covariance" if Vraw is None else
               f"event years {uncovered} have no finite bootstrap standard error and are not in the covariance")
        out.update(headline=est if np.isfinite(est) else None, headline_label="descriptive: its variance could not be computed",
                   se=None, numerical_failure=why)
        return out
    V = np.asarray(Vraw, dtype=float)
    w = np.zeros(len(idx))
    for e in HEADLINE:
        w[idx.index(e)] = 1.0 / len(HEADLINE)
    var = float(w @ V @ w)
    if not np.isfinite(est):
        out.update(headline=None, se=None, numerical_failure="a headline event-year effect is not finite")
    elif not np.isfinite(var) or var < 0:
        out.update(headline=est, headline_label="descriptive: its variance could not be computed", se=None,
                   numerical_failure="the headline's variance from the event-study covariance is not finite or is negative")
    else:
        out.update(headline=est, se=float(np.sqrt(var)), numerical_failure=None)
    return out


def run(f: Frame | pd.DataFrame, covariates: list | None = None, outcome: str = "outcome") -> dict:
    """The pinned call on diff-diff 4.0.0 (PREANALYSIS.md, "Other runs"), state-clustered, and the same call with
    cluster=None beside it for unit-level standard errors (Joe, D-99).

    Returns the headline 0.5 x (ATT(2) + ATT(3)), its standard error from the event-study covariance (under the pinned
    call, the covariance of the bootstrap draws; module docstring), the 90% range (headline +/- the t(G-1) critical value
    times that standard error, G the number of states; this module's t-based construction, since the package applies no
    degrees of freedom to bootstrap inference and gives no interval for the mean of two event years; accepted by Joe on
    2026-11-19, D-105), labelled RANGE_LABEL (secondary and uncalibrated), the event years -6 to 3, and the unit-level figures,
    including the unit-level call's own headline: with cluster=None the package weights cohorts by the units observed at
    g-3 and t rather than by cohort size, so the two headlines agree only when every host has a row in every window year,
    and `headlines_agree` says whether they do (to 1e-9).

    Every warning the package raises is recorded. A warning that the package dropped a covariate column or fell back to
    an estimate without covariates (COVARIATE_WARNING) is a numerical failure of that call: the covariate was not
    used as specified, so the result is labelled and never passed off as the specified estimator (the ruling). If the
    package is missing or another version, it raises PackageMissing or PackageVersionRefused. It never falls back.
    """
    import warnings
    dd = _import_pinned()
    data = f.data if isinstance(f, Frame) else f
    covs = list(f.covariates if isinstance(f, Frame) and covariates is None else (covariates or []))
    fit_kw = dict(outcome=outcome, unit="unit_id", time="year", first_treat="first_treat", covariates=covs)
    from scipy import stats
    from diff_diff.bootstrap_chunking import effective_weight_backend

    def one(cluster):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            est = dd.CallawaySantAnna(**{**PINNED_CALL, "cluster": cluster})
            res = est.fit(data, **fit_kw)
            h = headline_from_event_study(res.aggregate("event_study"))
        msgs = sorted({str(w.message) for w in caught})
        dropped = [m for m in msgs if any(k in m.lower() for k in COVARIATE_WARNING)]
        h["package_warnings"] = msgs
        h["covariate_warnings"] = dropped
        if dropped:
            h["headline_label"] = "not the specified estimator: the package did not use every covariate in every cell"
            h["numerical_failure"] = "; ".join(x for x in [h["numerical_failure"],
                                                          f"{len(dropped)} covariate warning(s) from the package"] if x)
        h["n_clusters"] = getattr(res, "n_clusters", None)
        h["bootstrap"] = (None if res.bootstrap_results is None else
                          {"n_bootstrap": int(res.bootstrap_results.n_bootstrap),
                           "weight_type": res.bootstrap_results.weight_type})
        return h

    state = one("state")
    unit = one(None)
    g = int(data.state.nunique())
    agree = (state["headline"] is not None and unit["headline"] is not None
             and abs(state["headline"] - unit["headline"]) <= 1e-9)
    out = {"package": f"{PINNED_PACKAGE}=={dd.__version__}", "call": {**PINNED_CALL}, "covariates": covs,
           "headline": state["headline"], "se_state_clustered": state["se"], "event_years": state["event_years"],
           "se_unit_level": unit["se"], "headline_unit_level_call": unit["headline"], "headlines_agree": bool(agree),
           "numerical_failure": state["numerical_failure"],
           "numerical_failure_unit_level": unit["numerical_failure"], "clusters": g,
           "package_clusters_state_call": state["n_clusters"], "bootstrap_state_call": state["bootstrap"],
           "bootstrap_weight_backend": effective_weight_backend(),
           "covariate_warnings": state["covariate_warnings"],
           "covariate_warnings_unit_level": unit["covariate_warnings"],
           "package_warnings": state["package_warnings"], "package_warnings_unit_level": unit["package_warnings"]}
    if "headline_label" in state:
        out["headline_label"] = state["headline_label"]
    if state["se"] is not None and state["numerical_failure"] is None and g > 1:
        crit = float(stats.t.ppf(0.5 + LEVEL / 2, g - 1))
        out["range_90"] = [state["headline"] - crit * state["se"], state["headline"] + crit * state["se"]]
        out["range_label"] = RANGE_LABEL
        out["range_text"] = RANGE_TEXT
    else:
        out["range_90"] = None
        out["range_label"] = "no range: " + (state["numerical_failure"] or "fewer than two clusters")
    return out


# ---- the reference computation (for tests; NOT the run) ------------------------------------------------------------------

def _base_and_t(data: pd.DataFrame, g: int, t: int, outcome: str, covariates: list, cohort_value: int):
    sub = data[data.first_treat == cohort_value]
    base = sub[sub.year == g + BASE_OFFSET].set_index("unit_id")
    now = sub[sub.year == t].set_index("unit_id")
    ids = base.index.intersection(now.index)
    dy = (now.loc[ids, outcome] - base.loc[ids, outcome]).to_numpy(float)
    X = np.column_stack([np.ones(len(ids))] + [base.loc[ids, c].to_numpy(float) for c in covariates])
    return dy, X


def reference_att(data: pd.DataFrame, g: int, t: int, covariates: list, outcome: str = "outcome") -> tuple[float, int]:
    """REFERENCE FOR TESTS, not the run. ATT(g, t) by outcome regression with never-treated comparison units, universal
    base period g-3 (two years of anticipation), and covariates read at g-3:

        mean over treated units of group g of [ (Y_t - Y_{g-3}) - X_i' b ],
        b from least squares of (Y_t - Y_{g-3}) on (1, X) among never-treated units,

    every unit observed (has a row) at both g-3 and t. Returns (ATT, number of treated units used). A comparison
    regression that is rank deficient (singular-value ratio under 1e-10), or no unit on either side, raises
    ReferenceFailure."""
    dy1, X1 = _base_and_t(data, g, t, outcome, covariates, g)
    dy0, X0 = _base_and_t(data, g, t, outcome, covariates, NEVER_TREATED)
    if not len(dy1) or not len(dy0):
        raise ReferenceFailure(f"ATT({g}, {t}): no treated or no never-treated unit observed at both {g + BASE_OFFSET} and {t}")
    sv = np.linalg.svd(X0, compute_uv=False)
    if sv.min() <= 1e-10 * sv.max() or X0.shape[0] < X0.shape[1]:
        raise ReferenceFailure(f"ATT({g}, {t}): the never-treated regression on {X0.shape[1] - 1} covariates is rank deficient")
    b, *_ = np.linalg.lstsq(X0, dy0, rcond=None)
    return float(np.mean(dy1 - X1 @ b)), int(len(dy1))


COHORT_WEIGHTS = "cohort"     # the cohort's units in the whole frame: the package with cluster="state" (the pinned call)
CELL_WEIGHTS = "cell"         # the cohort's units observed at g-3 and g+e: the package with cluster=None


def reference_event_study(data: pd.DataFrame, e: int, covariates: list, outcome: str = "outcome",
                          weights: str = COHORT_WEIGHTS) -> float:
    """REFERENCE FOR TESTS, not the run. The event-study effect at event year e: ATT(g, g+e) averaged over the groups g
    with a treated unit observed at g-3 and g+e.

    weights  COHORT_WEIGHTS (default): each group weighted by its number of units in the whole frame, what diff-diff
             4.0.0 does under the pinned call with cluster="state". CELL_WEIGHTS: by the number of its units observed at
             both g-3 and g+e, what the package does with cluster=None (module docstring, "Aggregation weights"; pinned
             by tests/test_callaway_santanna_package.py). The two agree when every host has a row in every window year,
             as sample() guarantees."""
    if weights not in (COHORT_WEIGHTS, CELL_WEIGHTS):
        raise ValueError(f"weights must be {COHORT_WEIGHTS!r} or {CELL_WEIGHTS!r}, not {weights!r}")
    num = den = 0.0
    for g in sorted(int(x) for x in data.first_treat.unique() if x != NEVER_TREATED):
        att, n = reference_att(data, g, g + e, covariates, outcome)
        if weights == COHORT_WEIGHTS:
            n = int(data.loc[data.first_treat == g, "unit_id"].nunique())
        num += n * att
        den += n
    if den == 0:
        raise ReferenceFailure(f"event year {e}: no group observed")
    return num / den


def reference_headline(data: pd.DataFrame, covariates: list, outcome: str = "outcome",
                       weights: str = COHORT_WEIGHTS) -> float:
    """REFERENCE FOR TESTS: 0.5 x (ES(2) + ES(3))."""
    return float(np.mean([reference_event_study(data, e, covariates, outcome, weights) for e in HEADLINE]))


# ---- the disclosed sample difference ----------------------------------------------------------------------------------

def main_design_units(d) -> tuple[set, set]:
    """(matched comparison units, eligible pool units) of the main design built by design.build_with_rules: the union over
    its hosts of their ten matches and of their region's eligible pool in the reference year after exclusions."""
    matched, pool = set(), set()
    for h in d.hosts.itertuples():
        w = d.windows[h.cohort]
        matched |= {(int(k[0]), k[1]) for k in h.match_keys}
        excluded = {_key(x["utility"]) for x in getattr(h, "excluded_from_its_pool", []) or []}
        for m in np.flatnonzero(d.is_comp[h.cohort] & (w.region == w.region[h.row])):
            k = (int(w.keys[m][0]), w.keys[m][1])
            if k not in excluded:
                pool.add(k)
    return matched, pool


def sample_difference(s: Sample, matched: set, pool: set, main_hosts: set, names: pd.Series | None = None) -> dict:
    nm = (lambda k: None) if names is None else names.get
    nt = {(int(u), st) for u, st in zip(s.never_treated.utility_id_eia, s.never_treated.state)}
    kept_elsewhere = []
    for c, recs in sorted(s.ownership_exclusions.items()):
        if c in matched or c in pool:
            kept_elsewhere.append({"utility": _label(c), "name": nm(c),
                                   "in_the_main_design_as": "a matched comparison utility" if c in matched else "in an eligible pool",
                                   "excluded_here_for": [{"host": r["host"], "host_name": r["host_name"], "why": r["why"],
                                                          "basis": r["basis"]["label"]} for r in recs]})
    cs_hosts = {(int(u), st) for u, st in zip(s.hosts.utility_id_eia, s.hosts.state)}
    host_ids = {}
    for k in sorted(cs_hosts):                     # sorted, so the lists do not follow the process's string hashing
        host_ids.setdefault(k[0], []).append(_label(k))
    unknown_kept = [{"utility": _label(c), "name": nm(c),
                     "in_the_main_design_as": "a matched comparison utility" if c in matched else "in an eligible pool",
                     "excluded_here_for": [{"host": r["host"], "host_name": r["host_name"], "uncovered_years": r["uncovered_years"]}
                                           for r in recs]}
                    for c, recs in sorted(s.unknown_ownership_year_exclusions.items()) if c in matched or c in pool]
    own_kept = [{"utility": _label(c), "name": nm(c),
                 "in_the_main_design_as": "a matched comparison utility" if c in matched else "in an eligible pool",
                 "shares_its_eia_id_with_hosts": host_ids.get(c[0], [])}
                for c in sorted(s.removed_by(STEP_OWN)) if c in matched or c in pool]
    return {
        "comparison_sample_difference_disclosed": region_sample_difference(s.theta, s.which),
        "never_treated_units": len(nt),
        "main_design_matched_comparison_units": len(matched),
        "main_design_eligible_pool_units": len(pool),
        "matched_units_that_are_never_treated_here": len(matched & nt),
        "pool_units_that_are_never_treated_here": len(pool & nt),
        "matched_units_not_never_treated_here": sorted(_label(k) for k in matched - nt),
        "never_treated_here_outside_every_main_design_pool": len(nt - pool),
        "removed_by_the_any_host_ownership_exclusion_that_the_main_design_keeps_for_some_host": kept_elsewhere,
        "removed_by_the_any_host_own_utility_exclusion_that_the_main_design_keeps_for_some_host": own_kept,
        "removed_for_a_year_of_unknown_ownership_that_the_main_design_keeps_for_some_host": unknown_kept,
        "unknown_ownership_years_difference": ("Both this run and the main design bar an investor-owned unit with no ownership "
                                               "row in a year of an investor-owned host's window (rule 2.2 read year by year, "
                                               "Joe, 2026-11-19, D-107). The main design bars it for that host only; this run "
                                               "takes the union over the included hosts, so the unit is out for every cohort. "
                                               "The units listed beside this are matched or pooled in the main design for a "
                                               "host whose window their rows cover."),
        "hosts_here_not_in_the_main_design_estimate": sorted(_label(k) for k in cs_hosts - main_hosts),
        "hosts_in_the_main_design_estimate_not_here": sorted(_label(k) for k in main_hosts - cs_hosts),
        "stated_differences_from_the_main_estimate": [
            "no ten-closest-in-size restriction: neither package does nearest-neighbour matching",
            "the comparison group is every never-treated unit, not each host's ten matched comparison utilities",
            "market region (dummy columns, read at the base period g-3) and the state's 2008-2010 gas share enter as "
            "covariates in an outcome regression, not as region-by-year effects within matched sets and gas share by "
            "calendar year",
            "no heating or cooling degree days",
            "never-treated units are not required to be usable over a whole window; each group-time effect uses units "
            "usable at g-3 and t",
            "ownership exclusions are the union over every included host, each over that host's window, not host by host",
            "an investor-owned unit with a year of unknown ownership in any investor-owned included host's window is excluded "
            "for every cohort; the main design applies the same rule (rule 2.2 read year by year, D-107) host by host",
            "never-treated units in a region with no host in its reference year stay in the sample and inform the gas-share "
            "slope (the main design's rule 1 is per host; here region is a covariate); kept by Joe's ruling of 2026-11-19 "
            "(D-111) and counted in comparison_sample_difference_disclosed. " + ESTIMATOR_ATTRIBUTION,
            "the support rule (D-54 ruling 2) is not applied: it is defined on each host's ten matches, which this run does "
            "not have; hosts the main design drops under it stay here and are named in hosts_here_not_in_the_main_design_estimate",
            RANGE_DIFFERENCE,
        ]}


# ---- main: a quantity-only summary ------------------------------------------------------------------------------------

def coverage(s: Sample, usable: set) -> dict:
    """Units by usable-year coverage: never-treated units by the number of usable years 2005-2025, and per cohort how many
    are usable at g-3 and at both g+2 and g+3, and at g-3 and every window year."""
    nt = [(int(u), st) for u, st in zip(s.never_treated.utility_id_eia, s.never_treated.state)]
    hist: dict = {}
    for k in nt:
        n = sum((k[0], k[1], y) in usable for y in YEARS)
        hist[n] = hist.get(n, 0) + 1
    per = {}
    for g in sorted(int(x) for x in s.hosts.cohort.unique()):
        ok = lambda k, ys: all((k[0], k[1], y) in usable for y in ys)  # noqa: E731
        per[str(g)] = {"hosts": int((s.hosts.cohort == g).sum()),
                       "never_treated_usable_at_g_minus_3_g_plus_2_and_g_plus_3": sum(ok(k, (g - 3, g + 2, g + 3)) for k in nt),
                       "never_treated_usable_in_every_window_year": sum(ok(k, range(g - ps.PRE, g + ps.POST + 1)) for k in nt)}
    return {"never_treated_by_usable_years_2005_2025": {str(n): hist[n] for n in sorted(hist)}, "by_cohort": per}


SETS = (ps.HEADLINE_SET, "every_cohort_utility")


def main() -> int:
    """Writes OUT for the headline set at 2% and every cohort utility as built (the labelled companion). Load, sales,
    customers, ownership and the usable flag only: no price, no revenue."""
    from pipeline.analysis import design as dsg
    from pipeline.analysis import usable_flag
    from pipeline.electricity import market_region, panel
    q = panel.load_quantities()
    dose = pd.read_parquet(ps.INTERIM / "utility_year_dose.parquet")
    regions = market_region.by_unit_year(q)
    fuel, dd = ps.load_controls()
    names = q.groupby(KEY).utility_name.last()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(ps.HEADLINE_RULES, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    dd_states = set(dd.index.get_level_values("state"))
    theta = 0.02
    history = ps.history_settled(theta)
    hold = ps.price_hold()
    report = {
        "what_this_is": ("Callaway and Sant'Anna's sample, step by step, for the headline set at 2% and for every cohort "
                         "utility as built (the labelled companion). Provisional: the design stands as of 2026-11-18 and the "
                         "plan is not frozen. Quantities only (load, sales, customers, ownership, the usable flag); no price, "
                         "revenue or bill is read. The estimator itself has not been run on the study's data; diff-diff "
                         "4.0.0 is installed only in the gizmo folder's isolated .venv and has been run there on invented "
                         "inputs only."),
        "comparison_sample_difference_headline_set_at_2pct": REGION_SAMPLE_DIFFERENCE,
        "ruling": "the owner's ruling of 2026-11-19 on Callaway and Sant'Anna (pipeline/analysis/callaway_santanna.py)",
        "pinned_call": {**PINNED_CALL, "package": f"{PINNED_PACKAGE}=={PINNED_VERSION}"},
        "steps_in_order": {k: STEP_RULE[k] for k in STEPS},
        "unknown_ownership_years": UNKNOWN_YEARS_READING,
        "parent_identity_mark": ("The ownership table carries no column marking a row's parent identity as supported. A row "
                                 "is in the table only with a source and a quote (ownership.load), and the existing code counts "
                                 "every row, assumed at both ends or not, as a row; this sample does the same."),
        "sets": {}}
    for which in SETS:
        host_aside, comp_aside = aside_sets(theta, which)
        s = sample(theta, which, q, dose, host_aside=host_aside, comparison_aside=comp_aside, hold=hold, unknown_load=unknown,
                   ownership=ownership, ownership_of=ownership_of, usable=usable, gas=gas, dd_states=dd_states,
                   history=history, names=names)
        # consistency with design.split: the same hosts before this run's gate and full-window drop, and the same pool
        # after the load rule, the set-aside lists and the price hold, which are the three restrictions split applies
        tr, cl = dsg.split(theta, which, q, dose)
        t0, c0 = ps.design(q, dose, theta, history, hold=set())
        mine_pool = {(int(u), st) for u, st in zip(c0.utility_id_eia, c0.state)} - comp_aside - hold
        mine_hosts = {(int(u), st) for u, st in zip(t0.utility_id_eia, t0.state)} - host_aside
        split_check = (mine_pool == {(int(u), st) for u, st in zip(cl.utility_id_eia, cl.state)}
                       and mine_hosts == {(int(u), st) for u, st in zip(tr.utility_id_eia, tr.state)})
        if not split_check:
            raise RuntimeError(f"{which}: the sample's load, set-aside and price-hold steps do not reproduce design.split; stopping")
        d = dsg.build_with_rules(tr, cl, q, regions, fuel, dd, ps.HEADLINE_RULES, ownership=ownership, usable=usable,
                                 gas=gas, ownership_of=ownership_of, unknown_load=unknown, theta=theta)
        matched, pool = main_design_units(d)
        main_hosts = {(int(k[0]), k[1]) for k in d.hosts.key} if len(d.hosts) else set()
        nm = names.get
        report["sets"][which] = {
            "threshold": "2%",
            "hosts_in_the_set_before_this_runs_drops": int(len(tr)),
            "hosts_on_neither_side": {k: {"count": len(v)} for k, v in s.hosts_neither_side.items()},
            "hosts_dropped": s.hosts_dropped,
            "hosts": [{"utility": _label((u, st)), "name": nm((int(u), st)), "cohort": int(g),
                       "ownership_class": ownership_of.get((int(u), st))}
                      for u, st, g in zip(s.hosts.utility_id_eia, s.hosts.state, s.hosts.cohort)],
            "cohorts_and_group_sizes": {str(int(g)): int(n) for g, n in s.hosts.cohort.value_counts().sort_index().items()},
            "never_treated_steps": [{k: v for k, v in st.items() if k != "units" or st["step"] in (STEP_HOLD, STEP_OWN, STEP_UNKNOWN)}
                                    for st in s.steps],
            "never_treated_units": int(len(s.never_treated)),
            "ownership_exclusions_named": [{"utility": _label(c), "name": nm(c), "for_hosts": v}
                                           for c, v in sorted(s.ownership_exclusions.items())],
            "excluded_for_a_year_of_unknown_ownership_named": [{"utility": _label(c), "name": nm(c), "for_hosts": v}
                                                               for c, v in sorted(s.unknown_ownership_year_exclusions.items())],
            "rows_for_part_of_a_window": {
                "rule": UNKNOWN_YEARS_READING,
                "units_removed_only_for_a_row_for_part_of_a_window": [
                    {"utility": u, "name": nm(_key(u)), "matched_in_the_main_design": _key(u) in matched}
                    for u in next(st for st in s.steps if st["step"] == STEP_OWNERSHIP)["removed_only_for_a_row_for_part_of_a_window"]],
                "of_them_matched_in_the_main_design": [
                    {"utility": u, "name": nm(_key(u))}
                    for u in next(st for st in s.steps if st["step"] == STEP_OWNERSHIP)["removed_only_for_a_row_for_part_of_a_window"]
                    if _key(u) in matched]},
            "usable_year_coverage": coverage(s, usable),
            "sample_difference_from_the_main_design": sample_difference(s, matched, pool, main_hosts, names),
            "main_design_hosts_dropped": d.dropped,
            "consistency_with_design_split": bool(split_check)}
        print(which, "| hosts", len(s.hosts), "| never-treated", len(s.never_treated),
              "| removed by step", {st["step"]: st["removed"] for st in s.steps})
    OUT.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
