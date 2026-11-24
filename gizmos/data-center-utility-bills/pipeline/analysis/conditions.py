#!/usr/bin/env python3
"""The four conditions tested (PREANALYSIS.md, "Conditions tested (four)"): the host groupings and the descriptive contrast.

Reads NO outcome. The groupings are built from quantity files only; `contrast` takes the outcome as an argument.

The owner's ruling of 2026-11-19, verbatim:
    "Adopt event-year-3 load share for the descriptive exposure grouping and the panel's ownership classification, with
    their timing and construction stated accurately. Treat observed delivery-only residential activity in the cohort
    reference year as a proxy for retail choice, not a definitive regulatory classification. Use the existing quantity
    field that actually supports it and specify the rule. If peak-demand utilization cannot be constructed from existing
    permitted inputs, report it as unavailable; no new collection or substitute measure."

Condition 1. Load share of 10% or more versus less (a descriptive exposure grouping).
    Field: `dose` in data/interim/utility_year_dose.parquet, the column power_simulation.design reads to find first
    crossings: data center load as a share of the unit's 2009-2011 retail sales, on the inventory as built, with
    cryptocurrency mines NOT counted (crypto is a separate column, `crypto_mw`, used only to bar comparison utilities;
    `dose_with_crypto` is not read). Year: event year 3, the calendar year cohort + 3, where the cohort is the host's
    first crossing as the design carries it (for a host whose own count of its load fixes its first crossing, D-34, that
    year; its `dose` in cohort + 3 is still the inventory's). Rule: 10% or more is dose >= 0.10. A host with no dose row
    in that year, or a value that is not finite, stops the grouping in words.

Condition 2. Investor-owned versus public and cooperative (the panel's ownership classification).
    Field: `ownership` in data/interim/panel_quantities.parquet, read per unit as power_simulation.ownership_classes reads
    it (each unit's last value). How the panel builds it (pipeline/electricity/panel.py, build): the MODAL EIA entity type
    over every year of the utility's own filings (rows reported under the unit's own EIA id; a predecessor summed into
    the unit does not count), mapped "Investor Owned" to investor_owned, "Cooperative" to cooperative, and "Municipal",
    "Political Subdivision", "State" and "Federal" to public. It is one value per EIA id for every year and every state:
    no year's value is chosen, and a utility whose EIA type changed over time takes the type it carried most often.
    Not the ownership table (ownership.csv), which records ultimate parents and is not read here.

Condition 3. Retail-choice state versus vertically integrated: a PROXY, not a regulatory classification.
    Field: `res_mwh_delivery` in data/interim/panel_quantities.parquet: residential MWh the unit reported under EIA-861's
    "delivery" service type (the utility delivers; a competitive supplier sells the energy), summed over the rows EIA
    observed (imputed rows are excluded by the panel build). `delivery_share` is that field divided by all residential
    MWh, so the two give the same yes or no; the field itself is the one that records the sales. Year: the cohort's
    reference year, cohort - 3.
    Rule (the reading coded, HOST_OWN): a host is in the "delivery-only residential activity observed" group if its own
    unit reports delivery-only residential sales above zero in its cohort's reference year. A missing value in that
    field on a row that exists means no delivery-only rows were reported and counts as not above zero, as the panel build
    itself fills it (panel.py, build: `z("res_mwh_delivery")`). A host with no row in its reference year stops the grouping
    in words. The other reading (STATE_ANY): any unit in the host's state reports delivery-only residential sales above
    zero in that year. It is computed and reported beside the first, never used in its place.
    Why the host's own unit is the reading coded (adopted by Joe on 2026-11-19, D-111): the ruling speaks of
    "observed delivery-only residential activity in the cohort reference year" and of "the existing quantity field",
    which is recorded per unit; the plan's condition is worded at the state level ("Retail-choice state"), which is the
    other reading.

Condition 4. Past utilization before entry (peak demand relative to the prior maximum), above versus below the median.
    It measures how hard the system had been used, not spare generation or network capacity (the plan's words).
    Source: data/raw/pudl/core_eia861__yearly_operational_data_misc.parquet, EIA-861's operational data as PUDL publishes
    it, the panel's own source (fetched by pipeline/electricity/fetch_eia861.py). It is read by explicit columns only
    (PEAK_COLUMNS: utility_id_eia, state, report_date, summer_peak_demand_mw, winter_peak_demand_mw, short_form,
    data_observed) and no other column. The session ruled on 2026-11-19 that this table is an existing permitted input.
    How it is keyed (checked 2026-11-19 on those columns): one row per utility id and year, filed under ONE state. No
    utility id has rows in two states in any year (0 of 66,311 utility-years); PacifiCorp (14354) files every year
    under OR only, for the company as a whole. The only repeated (utility, state, year) keys are EIA's placeholder id
    88888 in TX. 195 rows are flagged not observed (EIA-imputed), all in 2004 (179) and 2005 (16).
    The rule. Lines 1 to 6 read the plan's one-line definition as the coordinator's instruction of 2026-11-19 wrote
    it, adopted by Joe on 2026-11-19 (D-111); line 7 is the AGENT'S reading:
      1. A unit-year's peak demand is the larger of the summer and winter peak demand it reports for that year. A zero or
         missing value in both is no report.
      2. A host's past utilization is its peak demand in its reference year (cohort - 3) divided by the largest peak
         demand it reported in any earlier year from 2001 on. It needs a report in the reference year and in at least one
         earlier year.
      3. Above versus below the median: the median of that ratio among the hosts in the estimate that have one. "Above"
         is strictly above; a host at the median is in the second group.
      4. A host with no ratio is "not classifiable on this condition", named with the reason, and left out of this one
         contrast only; it stays in every other run. No substitute series (no sales-based measure, no load factor, no
         interpolation, no other year).
      5. Keys: the row whose utility and state match the panel unit. If the utility has no row for that state in a year it
         needs, but files exactly one operational record that year under another state, the record is NOT used: the host
         is "not classifiable: its operational record is filed for the utility as a whole under another state". A unit
         with summed predecessors (has_predecessors) uses the successor id's own filings only (peaks are not additive),
         and is flagged so. Extended by the session on 2026-11-19: if the host's utility id has panel units in more than
         one state, its single operational record is filed for the utility as a whole, so the host is "not classifiable:
         its utility serves more than one state in the panel and files one operational record for the whole utility",
         whichever state the record is filed under. Coded: the distinct states among the rows of panel_quantities.parquet
         for that utility id in the host's window years (cohort - 6 to cohort + 3), any row whatever its flags; more than
         one state means not classifiable. This is checked before every other reason. Single-state utilities are unchanged.
      6. If the condition cannot classify at least one host into each group for a set, the contrast is "not estimable"
         with the reason, kept in the record.
      7. (agent's reading) A row flagged not observed (data_observed false: EIA imputed it) is no report, as the panel
         build treats imputed rows everywhere (D-27). It touches 2004 and 2005 only.
    A repeated (utility, state, year) key for a host stops in words.
    8. Comparable footprints (the owner's ruling of 2026-11-19, verbatim: "Existing permitted operational quantities may
       support utilization, but use comparable utility footprints over the ratio's history; otherwise mark the ratio
       unavailable."). The ratio's history is every year from 2001 through R. The three tests below read "comparable
       utility footprints", adopted by Joe on 2026-11-19 (D-111); a host's ratio is used only if all three hold, and
       otherwise it is "unavailable: footprint not shown comparable over the ratio's history", named with the test(s)
       that failed and left out of this one contrast only (footprint_tests; FOOTPRINT_RULE):
         (i) one state: in every year of the history in which the utility id has any panel unit, all its units are in
             the host's state (rule 5's multi-state test extended from the event window to the ratio's history).
         (ii) no succession inside the history: no succession.csv row (either action) with an effective year after 2001
             and on or before R by which a predecessor is summed into the host's unit (directly or through a chain) or
             the host's unit is itself the predecessor. A merger wholly before 2002 or after R does not fail it. A unit
             the panel flags has_predecessors with no row naming its predecessors fails, since no date can be read.
             Extended by the session on 2026-11-19 to the whole EIA id, since the operational schedule is filed by the
             utility and not by the panel unit: any row in ANY state that names the host's EIA id as predecessor or as
             successor (directly or through a chain), with an effective year in the same span, also fails it (territory
             entered or left the filing utility inside the ratio's history).
         (iii) customer continuity: res_customers present in every year of the history and never changing by 10% or more
             between consecutive years (exactly 10% fails; the line is a convention fixed by the session before any
             customer series was examined for this purpose). A missing year fails; so does a zero count, from which no
             change can be measured (the agent's reading).
       The order of reasons: rule 5's multi-state test first, then no report in R or in an earlier year, then the
       footprint. Every host's reference-year peak, prior maximum and its year, and each test's result are listed
       whatever its reason, so a reader can see each case; no threshold on peaks is added.

The contrast (`contrast`): "Each is an interaction in the main regression, and what is reported is the difference
between the two groups." The main regression's event-time columns are interacted with an indicator for the hosts in the
first group; the difference is the mean of the interaction's coefficients in event years 2 and 3, fitted by the kernel
(outcome_analysis.point_fit, the shared estimator with its rank test before any inverse). Descriptive and exploratory:
no range, no test, no stars. Beside it, by group: the host count and the hosts' names, the number of states and the
concentration of weight. A group of one or two hosts is described as driven by those utilities. A contrast the fit
cannot estimate is "not estimable" and stays in the record. Passing the rank test establishes computational
estimability only. No host-count cutoff, no merging of groups.

Run:  python3 -I pipeline/analysis/conditions.py     writes data/frozen/conditions_groups.json (quantities only)
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import estimator  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import influence  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
KEY = ps.KEY
LOAD_SHARE_LINE = 0.10
EVENT_YEAR_OF_LOAD_SHARE = 3
INVESTOR_OWNED, PUBLIC, COOPERATIVE = "investor_owned", "public", "cooperative"
OWNERSHIP_CLASSES = (INVESTOR_OWNED, PUBLIC, COOPERATIVE)
HOST_OWN, STATE_ANY = "host_own_unit", "any_unit_in_the_hosts_state"
CONDITIONS = ("load_share_10pct_or_more", "investor_owned", "retail_choice_proxy", "past_utilization")

PROXY_LABEL = ("a proxy for retail choice (observed delivery-only residential activity in the cohort reference year), "
               "not a regulatory classification")
DESCRIPTIVE_LABEL = ("descriptive and exploratory: no range, no test, no significance stars; the headline procedure's "
                     "validation is not transferred to it; one group's estimate beside the other's is not evidence that "
                     "the two differ, and only the difference is described")
ESTIMABLE_MEANS = "passing the rank test establishes computational estimability only"
DRIVEN_BY = ("this contrast is driven by those particular utilities ({names}), not evidence of a general {kind} effect")
PEAK_FILE = ROOT / "data" / "raw" / "pudl" / "core_eia861__yearly_operational_data_misc.parquet"
PEAK_COLUMNS = ("utility_id_eia", "state", "report_date", "summer_peak_demand_mw", "winter_peak_demand_mw", "short_form",
                "data_observed")
PEAK_TABLE = {
    "file": "data/raw/pudl/core_eia861__yearly_operational_data_misc.parquet",
    "columns_read": list(PEAK_COLUMNS),
    "keying_checked_2026_11_19": ("one row per utility id and year, filed under one state; no utility id has rows in two "
                                  "states in any year (0 of 66,311 utility-years); PacifiCorp (14354) files under OR only; "
                                  "repeated (utility, state, year) keys only for EIA's placeholder id 88888 in TX; 195 rows "
                                  "not observed (EIA-imputed), all in 2004 and 2005"),
    "coverage_counted_2026_11_19": {"rows": 66329, "years": [2001, 2025], "utility_state_pairs": 4903,
                                    "rows_with_summer_peak": 60126, "rows_with_winter_peak": 60068},
}
RULE_SOURCE = ("lines 1 to 6 read the plan's one-line definition (coordinator's instruction of 2026-11-19), adopted by "
               "Joe on 2026-11-19 (D-111); line 7 (EIA-imputed rows are no report) is the agent's reading")
NO_REF = "not classifiable on this condition: no peak-demand report in its reference year"
NO_EARLIER = "not classifiable on this condition: no peak-demand report in any earlier year from 2001"
OTHER_STATE = ("not classifiable on this condition: its operational record is filed for the utility as a whole under "
               "another state ({state})")
MULTI_STATE = ("not classifiable on this condition: its utility serves more than one state in the panel and files one "
               "operational record for the whole utility")
FIRST_YEAR = 2001

# Comparable footprints (Joe's ruling of 2026-11-19 on past utilization; the three tests adopted by Joe on 2026-11-19,
# D-111).
UTILIZATION_RULING_2026_11_19 = ("Existing permitted operational quantities may support utilization, but use comparable "
                                 "utility footprints over the ratio's history; otherwise mark the ratio unavailable.")
CUSTOMER_CHANGE_LINE = 0.10            # a convention fixed by the session before any customer series was examined for this purpose
FOOTPRINT_UNAVAILABLE = "unavailable: footprint not shown comparable over the ratio's history"
TEST_ONE_STATE = "(i) one state"
TEST_NO_SUCCESSION = "(ii) no succession inside the history"
TEST_CUSTOMERS = "(iii) customer continuity"
FOOTPRINT_TESTS = (TEST_ONE_STATE, TEST_NO_SUCCESSION, TEST_CUSTOMERS)
FOOTPRINT_SOURCE = ("the three footprint tests read 'comparable utility footprints' in the owner's ruling of 2026-11-19, "
                    "adopted by Joe on 2026-11-19 (D-111); the 10% line in test (iii) is a convention fixed by the "
                    "session before any customer series was examined for this purpose")
FOOTPRINT_RULE = {
    "history": "every year from 2001 through the reference year R = cohort - 3",
    TEST_ONE_STATE: ("in every year of the history in which the utility (its EIA id) has any panel unit, all its units are in "
                     "one state, the host's (the operational schedule is filed once for the whole utility)"),
    TEST_NO_SUCCESSION: ("no row of pipeline/electricity/succession.csv, of either action, with an effective year after 2001 "
                         "and on or before R in which a predecessor is summed into the host's unit (directly or through a "
                         "chain) or the host's unit is itself the predecessor; a merger wholly before the history or after R "
                         "does not fail it. A unit the panel flags has_predecessors with no row naming its predecessors fails "
                         "(no date can be read). Extended by the session on 2026-11-19 to the whole EIA id, the utility "
                         "that files the schedule: any row in any state naming the host's EIA id as predecessor or as "
                         "successor, with an effective year in the same span, also fails it"),
    TEST_CUSTOMERS: ("res_customers in panel_quantities.parquet present in every year of the history and never changing by 10% "
                     "or more, up or down, between consecutive years (exactly 10% fails); a missing year, or a zero count "
                     "from which no change can be measured, means comparability is not shown"),
    "source": FOOTPRINT_SOURCE,
}


class ConditionInputError(ValueError):
    """A host's value for a condition cannot be read as the rule specifies. Raised in words; nothing is filled."""


@dataclass(frozen=True)
class Grouping:
    """One condition's split of the hosts. `member[label]` is True for the first group. `value[label]` is what the rule
    read for that host."""
    condition: str
    first: str
    second: str
    member: dict
    value: dict
    rule: str
    label: str = ""
    kind: str = ""                         # for the "driven by" sentence: "ownership-type", "exposure", "retail-choice"
    extra: dict = field(default_factory=dict)


def _label(key) -> str:
    return f"{int(key[0])}:{key[1]}"


def hosts_of(d) -> list:
    """[((utility_id_eia, state), cohort)] for every host in the design."""
    return [((int(k[0]), k[1]), int(g)) for k, g in zip(d.hosts.key, d.hosts.cohort)] if len(d.hosts) else []


# ---- the groupings ---------------------------------------------------------------------------------------------------

def load_share_grouping(hosts: list, dose: pd.DataFrame) -> Grouping:
    """Condition 1: `dose` in event year 3 (cohort + 3), 10% or more (dose >= 0.10) against less. See the module docstring."""
    for c in KEY + ["year", "dose"]:
        if c not in dose.columns:
            raise ConditionInputError(f"the dose frame has no column {c!r}")
    idx = dose.assign(utility_id_eia=dose.utility_id_eia.astype(int), year=dose.year.astype(int)).set_index(KEY + ["year"]).sort_index()
    member, value = {}, {}
    for key, g in hosts:
        yr = g + EVENT_YEAR_OF_LOAD_SHARE
        k = (key[0], key[1], yr)
        if k not in idx.index:
            raise ConditionInputError(f"{_label(key)} has no dose row in event year 3 ({yr}); its load-share group cannot be read")
        v = idx.loc[[k], "dose"]
        if len(v) != 1:
            raise ConditionInputError(f"{_label(key)} has {len(v)} dose rows in {yr}; stopping")
        v = float(v.iloc[0])
        if not np.isfinite(v):
            raise ConditionInputError(f"{_label(key)}'s dose in {yr} is missing or not finite; nothing is filled")
        value[_label(key)] = {"year": yr, "load_share": v}
        member[_label(key)] = v >= LOAD_SHARE_LINE
    return Grouping("load_share_10pct_or_more", "load share 10% or more in event year 3", "load share under 10% in event year 3",
                    member, value, "dose (data center load over 2009-2011 retail sales, crypto not counted, inventory as built) "
                    "in calendar year cohort + 3; first group if dose >= 0.10", "descriptive exposure grouping", "load-share")


def ownership_grouping(hosts: list, ownership_of: dict) -> Grouping:
    """Condition 2: the panel's ownership class (power_simulation.ownership_classes), investor-owned against public and
    cooperative. A class outside the three stops in words."""
    member, value = {}, {}
    for key, _ in hosts:
        c = ownership_of.get((int(key[0]), key[1]))
        if c not in OWNERSHIP_CLASSES:
            raise ConditionInputError(f"{_label(key)} has ownership class {c!r}, not one of {OWNERSHIP_CLASSES}; nothing is assumed")
        value[_label(key)] = {"ownership_class": c}
        member[_label(key)] = c == INVESTOR_OWNED
    return Grouping("investor_owned", "investor-owned", "public and cooperative", member, value,
                    "the panel's ownership class: the modal EIA entity type over the utility's own filings, one value per "
                    "EIA id for every year (pipeline/electricity/panel.py)", "the panel's ownership classification", "ownership-type")


def retail_choice_grouping(hosts: list, q: pd.DataFrame, reading: str = HOST_OWN) -> Grouping:
    """Condition 3, the proxy. HOST_OWN (coded): the host's own unit reports res_mwh_delivery above zero in its cohort's
    reference year (cohort - 3). STATE_ANY (reported beside it): any unit in the host's state does. A missing field value
    on an existing row is no delivery-only rows reported and counts as not above zero. A host with no row in its
    reference year stops in words (both readings), and so does a state with no row at all that year (STATE_ANY)."""
    if reading not in (HOST_OWN, STATE_ANY):
        raise ValueError(f"unknown reading {reading!r}; one of {(HOST_OWN, STATE_ANY)}")
    for c in KEY + ["year", "res_mwh_delivery"]:
        if c not in q.columns:
            raise ConditionInputError(f"the quantities frame has no column {c!r}")
    f = q[KEY + ["year", "res_mwh_delivery"]].copy()
    f["utility_id_eia"], f["year"] = f.utility_id_eia.astype(int), f.year.astype(int)
    f["active"] = f.res_mwh_delivery.fillna(0.0) > 0
    own = f.set_index(KEY + ["year"]).sort_index()
    by_state = f.groupby(["state", "year"]).agg(units=("active", "size"), units_with_delivery_only=("active", "sum"))
    member, value = {}, {}
    for key, g in hosts:
        ref = g + ps.REF
        k = (key[0], key[1], ref)
        if k not in own.index:
            raise ConditionInputError(f"{_label(key)} has no row in the quantities file in its reference year ({ref}); its "
                                      "retail-choice proxy cannot be read")
        rows = own.loc[[k]]
        if len(rows) != 1:
            raise ConditionInputError(f"{_label(key)} has {len(rows)} rows in {ref}; stopping")
        raw = rows.res_mwh_delivery.iloc[0]
        own_v = None if pd.isna(raw) else float(raw)
        if (key[1], ref) not in by_state.index:
            raise ConditionInputError(f"no unit in {key[1]} has a row in {ref}")
        st = by_state.loc[(key[1], ref)]
        value[_label(key)] = {"reference_year": ref, "host_res_mwh_delivery": own_v,
                              "host_reports_delivery_only_residential_sales": bool(rows.active.iloc[0]),
                              "units_in_state": int(st.units), "units_in_state_with_delivery_only_residential_sales": int(st.units_with_delivery_only)}
        member[_label(key)] = bool(rows.active.iloc[0]) if reading == HOST_OWN else bool(st.units_with_delivery_only > 0)
    rule = ("the host's own unit reports delivery-only residential sales (res_mwh_delivery) above zero in its cohort's "
            "reference year" if reading == HOST_OWN else
            "any unit in the host's state reports delivery-only residential sales (res_mwh_delivery) above zero in the "
            "host's cohort's reference year")
    return Grouping("retail_choice_proxy", "delivery-only residential activity observed (retail-choice proxy)",
                    "no delivery-only residential activity observed", member, value, rule, PROXY_LABEL, "retail-choice",
                    {"reading": reading})


def read_peaks(source=None) -> pd.DataFrame:
    """The peak-demand rows, by explicit columns only (PEAK_COLUMNS). `source` is None (the file, read by duckdb with a
    SELECT of those columns and nothing else) or any frame-like object, from which exactly `source[list(PEAK_COLUMNS)]`
    is requested. Returns utility_id_eia, state, year, peak_mw (the larger of summer and winter; NaN where neither is a
    report), short_form, data_observed."""
    if source is None:
        import duckdb
        cols = ", ".join(PEAK_COLUMNS)
        raw = duckdb.connect().execute(f"select {cols} from read_parquet('{PEAK_FILE}')").df()
    else:
        raw = source[list(PEAK_COLUMNS)]
    out = pd.DataFrame({"utility_id_eia": pd.to_numeric(raw["utility_id_eia"]).astype(int), "state": raw["state"].astype(object),
                        "year": pd.to_datetime(raw["report_date"]).dt.year.astype(int)})
    s = pd.to_numeric(raw["summer_peak_demand_mw"], errors="coerce").to_numpy(dtype=float)
    w = pd.to_numeric(raw["winter_peak_demand_mw"], errors="coerce").to_numpy(dtype=float)
    s = np.where(s > 0, s, np.nan)
    w = np.where(w > 0, w, np.nan)
    peak = np.fmax(s, w)                                              # rule 1: the larger; NaN only if neither is positive
    observed = raw["data_observed"].astype("boolean").fillna(True).to_numpy(dtype=bool)
    peak = np.where(observed, peak, np.nan)                           # rule 7 (agent's reading): an imputed row is no report
    out["peak_mw"] = peak
    out["short_form"] = raw["short_form"].astype("boolean").to_numpy()
    out["data_observed"] = observed
    return out


def _effective_year(v) -> int | None:
    """The year of a succession row's effective_date ("2002-01-01", "2007-02", "2017"); None if it cannot be read."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    t = str(v).strip()
    return int(t[:4]) if len(t) >= 4 and t[:4].isdigit() else None


def succession_events(key: tuple, succession: pd.DataFrame) -> dict:
    """Rows of the succession table that touch the unit `key` = (utility_id_eia, state): {"into_the_unit": rows whose
    predecessor is summed into it, directly or through a chain (succession.resolve), "unit_is_predecessor": rows, of either
    action, whose predecessor is the unit itself, "same_id_other_states": rows in another state that name the same EIA id
    as predecessor (either action) or as successor (directly, or as the final successor of a chain)}. Each row: predecessor, state, action, successor, effective_date, year."""
    from pipeline.electricity import succession as succ
    u, st = int(key[0]), key[1]
    t = succession
    s = t[t.action == "sum"]
    final = succ.resolve(t)

    def rec(r):
        return {"predecessor": f"{int(r.predecessor_id)}:{r.state}", "action": r.action,
                "successor": None if pd.isna(r.successor_id) else int(r.successor_id),
                "final_successor": final.get((int(r.predecessor_id), r.state)),
                "effective_date": None if pd.isna(r.effective_date) else str(r.effective_date),
                "year": _effective_year(r.effective_date)}
    into = [rec(r) for r in s.itertuples() if r.state == st and final.get((int(r.predecessor_id), r.state)) == u]
    itself = [rec(r) for r in t.itertuples() if int(r.predecessor_id) == u and r.state == st]
    other = [rec(r) for r in t.itertuples() if r.state != st and (
        int(r.predecessor_id) == u or (not pd.isna(r.successor_id) and int(r.successor_id) == u)
        or (r.action == "sum" and final.get((int(r.predecessor_id), r.state)) == u))]
    return {"into_the_unit": into, "unit_is_predecessor": itself, "same_id_other_states": other}


def footprint_tests(key: tuple, ref: int, panel_units: pd.DataFrame, succession: pd.DataFrame,
                    has_predecessors: set) -> dict:
    """The three footprint tests over the ratio's history, FIRST_YEAR through the reference year `ref` (the reading of
    the owner's ruling of 2026-11-19, adopted by Joe on 2026-11-19, D-111; FOOTPRINT_RULE). `panel_units` carries
    utility_id_eia, state, year and res_customers for every panel row. Returns {test: {"passes": bool, ...detail}};
    every test is evaluated, none stops."""
    u, st = int(key[0]), key[1]
    hist = list(range(FIRST_YEAR, int(ref) + 1))
    out = {}

    mine = panel_units[(panel_units.utility_id_eia == u) & panel_units.year.between(FIRST_YEAR, ref)]
    by_year = mine.groupby("year").state.agg(lambda x: sorted(set(x)))
    other_years = {int(y): s_ for y, s_ in by_year.items() if any(x != st for x in s_)}
    out[TEST_ONE_STATE] = {"passes": not other_years,
                           "years_with_a_unit_of_the_utility_in_another_state": {str(y): s_ for y, s_ in sorted(other_years.items())}}

    ev = succession_events(key, succession)
    inside = lambda e: e["year"] is None or FIRST_YEAR < e["year"] <= ref  # noqa: E731  (a date that cannot be read is not shown outside)
    hits = [{**e, "kind": "a predecessor summed into the host's unit"} for e in ev["into_the_unit"] if inside(e)]
    hits += [{**e, "kind": "the host's unit is itself the predecessor"} for e in ev["unit_is_predecessor"] if inside(e)]
    # The session's extension of 2026-11-19: the filing utility is the EIA id, so a row in another state counts too.
    hits += [{**e, "kind": ("the host's EIA id, the utility that files the operational schedule, is named as predecessor or "
                            "successor in another state (extended 2026-11-19; adopted by Joe on 2026-11-19, D-111)")}
             for e in ev["same_id_other_states"] if inside(e)]
    flagged = key in has_predecessors
    unnamed = flagged and not ev["into_the_unit"]
    out[TEST_NO_SUCCESSION] = {
        "passes": not hits and not unnamed, "rows_inside_the_history": hits,
        "rows_outside_the_history": [e for e in ev["into_the_unit"] + ev["unit_is_predecessor"] + ev["same_id_other_states"]
                                     if not inside(e)],
        "panel_flags_has_predecessors": flagged,
        "flagged_but_no_row_names_its_predecessors": unnamed,
        "rows_name_predecessors_but_the_panel_does_not_flag_it": bool(ev["into_the_unit"]) and not flagged}

    rows = panel_units[(panel_units.utility_id_eia == u) & (panel_units.state == st) & panel_units.year.between(FIRST_YEAR, ref)]
    if rows.year.duplicated().any():
        raise ConditionInputError(f"{u}:{st} has more than one panel row in {sorted(set(rows.year[rows.year.duplicated()]))}; stopping")
    c = rows.set_index("year").res_customers
    missing = [y for y in hist if y not in c.index or pd.isna(c.get(y))]
    jumps, zero, largest = [], [], None
    line = Fraction(str(CUSTOMER_CHANGE_LINE))
    for y in hist[1:]:
        if y in missing or (y - 1) in missing:
            continue
        a, b = float(c[y - 1]), float(c[y])
        if a <= 0:
            zero.append(y - 1)
            continue
        ch = (b - a) / a
        if largest is None or abs(ch) > abs(largest["change"]):
            largest = {"from_year": y - 1, "to_year": y, "from": a, "to": b, "change": ch}
        if Fraction(abs(b - a)) >= line * Fraction(a):
            jumps.append({"from_year": y - 1, "to_year": y, "from": a, "to": b, "change": ch})
    out[TEST_CUSTOMERS] = {"passes": not missing and not jumps and not zero, "years_missing": missing,
                           "changes_of_10_percent_or_more": jumps, "zero_counts_no_change_measurable": zero,
                           "largest_year_on_year_change": largest, "line": CUSTOMER_CHANGE_LINE,
                           "line_is": "a convention fixed by the session before any customer series was examined for this purpose"}
    return out


def past_utilization_grouping(hosts: list, peaks: pd.DataFrame, has_predecessors: set | None = None,
                              panel_units: pd.DataFrame | None = None, *, succession: pd.DataFrame | None = None) -> Grouping:
    """Condition 4 by the rule in the module docstring (lines 1 to 8). `peaks` is read_peaks(); `has_predecessors` is the
    set of panel units with summed predecessors (flagged; the successor id's own filings are used either way).
    `panel_units` (utility_id_eia, state, year and res_customers: the panel's rows) decides the multi-state rule and the
    footprint tests; it is required, with res_customers. `succession` is the succession table (succession.load()); None
    reads pipeline/electricity/succession.csv.

    Returns a Grouping whose `member` holds only the classifiable hosts; extra["not_classifiable"] maps each other host to
    its reason, extra["median"] is the median ratio. contrast leaves the unclassifiable hosts out of this contrast only."""
    has_predecessors = has_predecessors or set()
    if panel_units is None:
        raise ValueError("pass panel_units (utility_id_eia, state, year from panel_quantities.parquet): the multi-state rule needs it")
    if "res_customers" not in panel_units.columns:
        raise ConditionInputError("panel_units has no res_customers column: the customer-continuity test of comparable "
                                  "footprints (the owner's ruling of 2026-11-19) needs it; pass utility_id_eia, state, year "
                                  "and res_customers from panel_quantities.parquet")
    if succession is None:
        from pipeline.electricity import succession as succ
        succession = succ.load()
    pu = panel_units[KEY + ["year", "res_customers"]].assign(utility_id_eia=lambda x: x.utility_id_eia.astype(int),
                                                             year=lambda x: x.year.astype(int))
    pu_by_id = {u: f for u, f in pu.groupby("utility_id_eia")}
    by_id = {u: f for u, f in peaks.groupby("utility_id_eia")}
    ratios, reasons, value = {}, {}, {}
    for key, g in hosts:
        lab, ref = _label(key), g + ps.REF
        f = by_id.get(key[0], peaks.iloc[0:0])
        own = f[f.state == key[1]]
        dup = own.year.duplicated(keep=False)
        if dup.any():
            raise ConditionInputError(f"{lab} has more than one operational row for {key[1]} in {sorted(set(own.year[dup]))}; stopping")
        other = f[f.state != key[1]]
        rep = own[own.peak_mw.notna()].set_index("year").peak_mw
        v = {"reference_year": ref, "has_predecessors": key in has_predecessors,
             "peaks_from": "the successor id's own filings only (peaks are not additive)" if key in has_predecessors else "the unit's own filings"}

        mine = pu_by_id.get(key[0], pu.iloc[0:0])
        window_states = sorted(set(mine[mine.year.between(g - ps.PRE, g + ps.POST)].state))
        v["panel_states_of_its_utility_in_its_window"] = window_states

        def filed_elsewhere(years):
            o = other[other.year.isin(list(years)) & other.peak_mw.notna()]
            return sorted(set(o.state)) if len(o) and not len(own[own.year.isin(list(years))]) else []

        # Every host's own-state peaks are listed, whether or not its ratio is used, so a reader can see each case.
        earlier = rep[(rep.index >= FIRST_YEAR) & (rep.index < ref)]
        v.update(peak_mw_in_reference_year=float(rep[ref]) if ref in rep.index else None,
                 prior_maximum_mw=float(earlier.max()) if len(earlier) else None,
                 prior_maximum_year=int(earlier.idxmax()) if len(earlier) else None, earlier_years_reported=int(len(earlier)))
        tests = footprint_tests(key, ref, pu, succession, has_predecessors)
        failed = [t for t in FOOTPRINT_TESTS if not tests[t]["passes"]]
        v["footprint_tests"] = {t: tests[t] for t in FOOTPRINT_TESTS}
        v["footprint_tests_failed"] = failed
        if len(window_states) > 1:
            reasons[lab] = MULTI_STATE
        elif ref not in rep.index:
            ref_other = other[other.year == ref]
            if len(own[own.year == ref]) == 0 and len(ref_other) == 1:
                reasons[lab] = OTHER_STATE.format(state=ref_other.state.iloc[0])
            else:
                reasons[lab] = NO_REF
        elif not len(earlier):
            elsewhere = filed_elsewhere(range(FIRST_YEAR, ref))
            reasons[lab] = OTHER_STATE.format(state=", ".join(elsewhere)) if elsewhere else NO_EARLIER
        else:
            ratio = float(rep[ref]) / float(earlier.max())
            ref_row = own[own.year == ref].iloc[0]
            v["reference_year_short_form"] = None if pd.isna(ref_row.short_form) else bool(ref_row.short_form)
            if failed:
                reasons[lab] = f"{FOOTPRINT_UNAVAILABLE} (failed: {'; '.join(failed)})"
                v["ratio_not_used_footprint_not_shown_comparable"] = ratio
            else:
                ratios[lab] = ratio
                v["ratio"] = ratio
        if lab in reasons:
            v["not_classifiable"] = reasons[lab]
        value[lab] = v
    med = float(np.median(list(ratios.values()))) if ratios else None
    member = {lab: r > med for lab, r in ratios.items()}               # rule 3: strictly above; the median host is second
    for lab in ratios:
        value[lab]["median_of_classifiable_hosts"] = med
    return Grouping("past_utilization", "past utilization above the median", "past utilization at or below the median",
                    member, value, "peak demand in the reference year over the largest peak reported in any earlier year "
                    "from 2001 (peak = the larger of summer and winter); used only where the utility's footprint is shown "
                    "comparable over 2001 to the reference year by tests (i) one state, (ii) no succession inside the "
                    "history and (iii) customer continuity; first group if strictly above the median among the "
                    f"classifiable hosts in the estimate; {RULE_SOURCE}; {FOOTPRINT_SOURCE}",
                    "measures how hard the system had been used; not a measure of spare generation or network capacity",
                    "past-utilization", {"not_classifiable": reasons, "median": med})


# ---- the contrast ----------------------------------------------------------------------------------------------------

def _weight_concentration(weights: dict | None, labels: list) -> dict:
    if weights is None:
        return {"share_of_host_side_weight": None, "largest_single_host_share_within_group": None,
                "effective_number_of_hosts": None, "why_none": "the weights cannot be computed: the rank test failed"}
    total = sum(weights.values())
    w = np.array([weights.get(h, 0.0) for h in labels], dtype=float)
    s = float(w.sum())
    return {"share_of_host_side_weight": float(s / total) if total else None,
            "largest_single_host_share_within_group": float(np.abs(w).max() / np.abs(w).sum()) if len(w) and np.abs(w).sum() > 0 else None,
            "effective_number_of_hosts": float(s ** 2 / (w ** 2).sum()) if len(w) and (w ** 2).sum() > 0 else None}


def describe_groups(d, grouping: Grouping, names: dict | None = None, weights: dict | None = None) -> dict:
    """By group: host count, the hosts (label and name), the states and their number, and the concentration of weight
    (each group's share of the host-side headline weight from inference_check.implied_weights, the largest single host's
    share within the group, and the effective number of hosts, (sum w)^2 / sum w^2). The weights are the main design's,
    computed from the regressors alone (the agent's reading of "the concentration of weight")."""
    names = names or {}
    out = {}
    for flag, label in ((True, grouping.first), (False, grouping.second)):
        hs = [(k, g) for k, g in hosts_of(d) if grouping.member.get(_label(k)) is flag]
        labels = [_label(k) for k, _ in hs]
        states = sorted({k[1] for k, _ in hs})
        entry = {"group": label, "hosts": len(hs), "named": [{"utility": _label(k), "name": names.get(k), "cohort": g} for k, g in hs],
                 "states": states, "number_of_states": len(states), **_weight_concentration(weights, labels)}
        if 0 < len(hs) <= 2:
            entry["driven_by"] = DRIVEN_BY.format(names=", ".join(str(names.get(k) or _label(k)) for k, _ in hs), kind=grouping.kind)
        out["first" if flag else "second"] = entry
    nc = grouping.extra.get("not_classifiable") or {}
    hs = [(k, g) for k, g in hosts_of(d) if _label(k) in nc]
    if hs:
        out["not_classifiable"] = {"hosts": len(hs), "left_out_of": "this condition's contrast only; every other run keeps them",
                                   "named": [{"utility": _label(k), "name": names.get(k), "cohort": g, "why": nc[_label(k)]} for k, g in hs],
                                   **_weight_concentration(weights, [_label(k) for k, _ in hs])}
    return out


def contrast(d, y, grouping: Grouping, *, fuel_control: str | None = None, names: dict | None = None) -> dict:
    """The difference between the two groups' headline (mean of event years 2 and 3), as an interaction in the main
    regression; descriptive, no range, no test. `y` is aligned to outcome_analysis.stacked_rows(d).

    The first group's hosts get the main event-time columns times an indicator; the difference (first minus second) is
    the mean of the interaction coefficients in event years 2 and 3, in log points. Fitted by outcome_analysis.point_fit
    (estimator.Fit: the rank test before any inverse). A group with no host in the design, or a fit that fails its rank
    test, is "not estimable" with its reason, and the record is returned either way. Hosts with no matched comparison
    utility are not stacked (outcome_analysis.stackable) and are named.
    """
    fc = oa._fuel_control(d, fuel_control)
    rows = oa.stacked_rows(d)
    y = np.asarray(y, dtype=float)
    if y.ndim != 1 or len(y) != len(rows):
        raise oa.OutcomeMisaligned(f"the outcome has shape {y.shape}; the design has {len(rows)} stacked rows")
    nc = grouping.extra.get("not_classifiable") or {}
    missing = [_label(k) for k, _ in hosts_of(d) if _label(k) not in grouping.member and _label(k) not in nc]
    if missing:
        raise ConditionInputError(f"the grouping has no value for hosts {missing}; nothing is assumed")
    if nc and len(d.hosts):
        # A host not classifiable on this condition leaves this one contrast only (rule 4): its block and its rows go.
        keep_host = np.array([_label(k) not in nc for k in d.hosts.key])
        keep_row = np.array([f"{u}:{s}" not in nc for u, s in zip(rows.block_host_id, rows.block_host_state)], dtype=bool)
        d, y, rows = influence._without(d, keep_host), y[keep_row], rows[keep_row].reset_index(drop=True)
    ds = oa.stackable(d)
    no_matches = [_label(k) for k, m in zip(d.hosts.key, d.hosts.matches) if len(m) == 0] if len(d.hosts) else []
    try:
        weights = oa.host_weights(ds, fc) if len(rows) else None
    except estimator.RankDeficient:
        weights = None
    rec = {"condition": grouping.condition, "rule": grouping.rule, "label": grouping.label, "reading": grouping.extra.get("reading"),
           "difference_is": f"{grouping.first} minus {grouping.second}", "what_this_is": DESCRIPTIVE_LABEL,
           "estimable_means": ESTIMABLE_MEANS, "hosts_with_no_matches_not_stacked": no_matches,
           "hosts_not_classifiable_left_out_of_this_contrast": nc,
           "groups": describe_groups(ds, grouping, names, weights),
           "estimable": False, "difference_log_points": None, "difference_log_points_x100": None, "not_estimable_because": None}
    empty = [rec["groups"][s]["group"] for s in ("first", "second") if rec["groups"][s]["hosts"] == 0]
    if empty:
        rec["not_estimable_because"] = f"no host in this design is in the group(s) {empty}" + (
            "; hosts not classifiable on this condition are counted in neither group" if nc else "")
        return rec
    if not np.isfinite(y).all():
        rec["not_estimable_because"] = oa.FAILURE_IN_WORDS[oa.cd.NON_FINITE_OUTCOME]
        return rec
    f = ic.fixed_parts(ds, fc)
    K = oa.K_EVENT
    first = {h for h, v in grouping.member.items() if v}
    in_first = np.array([f"{u}:{s}" in first for u, s in zip(rows.block_host_id, rows.block_host_state)], dtype=float)
    X = np.column_stack([f["X"][:, :K], f["X"][:, :K] * in_first[:, None], f["X"][:, K:]])
    combo = np.zeros(X.shape[1])
    combo[K:2 * K] = ps.W_HEAD
    try:
        b = oa.point_fit(y, X, f["groups"], f["cluster"], f["projection"])
    except estimator.RankDeficient as e:
        rec["not_estimable_because"] = f"the fit fails its rank test before any inverse: {e}"
        return rec
    diff = float(combo @ b)
    rec.update(estimable=True, difference_log_points=diff, difference_log_points_x100=100.0 * diff)
    return rec


# ---- the quantity-only summary -------------------------------------------------------------------------------------

def _host_rows(d, names, groupings, weights, settled) -> list:
    out = []
    for key, g in hosts_of(d):
        lab = _label(key)
        r = {"utility": lab, "name": names.get(key), "state": key[1], "cohort": g,
             "cohort_from_its_own_count_of_its_load_D34": key in settled,
             "headline_weight": None if weights is None else weights.get(lab)}
        for gr in groupings:
            tag = gr.condition if gr.extra.get("reading") in (None, HOST_OWN) else f"{gr.condition}_{gr.extra['reading']}"
            if lab in gr.member:
                r[tag] = {"value": gr.value[lab], "in_first_group": bool(gr.member[lab]), "group": gr.first if gr.member[lab] else gr.second}
            else:
                r[tag] = {"value": gr.value[lab], "in_first_group": None, "group": None, "not_classifiable": gr.extra["not_classifiable"][lab]}
        out.append(r)
    return out


def summarise_set(d, dose: pd.DataFrame, q: pd.DataFrame, ownership_of: dict, names, settled: set, fc: str,
                  peaks: pd.DataFrame, has_predecessors: set) -> dict:
    hosts = hosts_of(d)
    ds = oa.stackable(d)
    try:
        weights = oa.host_weights(ds, fc) if len(ds.hosts) else None
    except estimator.RankDeficient:
        weights = None
    gs = [load_share_grouping(hosts, dose), ownership_grouping(hosts, ownership_of),
          retail_choice_grouping(hosts, q, HOST_OWN), retail_choice_grouping(hosts, q, STATE_ANY),
          past_utilization_grouping(hosts, peaks, has_predecessors, q)]
    by_condition = {}
    for gr in gs:
        tag = gr.condition if gr.extra.get("reading") in (None, HOST_OWN) else f"{gr.condition}_{gr.extra['reading']}"
        by_condition[tag] = {"rule": gr.rule, "label": gr.label, "groups": describe_groups(d, gr, names, weights)}
        if gr.condition == "past_utilization":
            g = by_condition[tag]["groups"]
            by_condition[tag]["median_ratio"] = gr.extra["median"]
            by_condition[tag]["every_host_peaks_and_footprint_tests"] = [
                {"utility": lab, "name": names.get(oa_key(lab)), "reference_year": v["reference_year"],
                 "peak_mw_in_reference_year": v.get("peak_mw_in_reference_year"), "prior_maximum_mw": v.get("prior_maximum_mw"),
                 "prior_maximum_year": v.get("prior_maximum_year"),
                 "ratio": v.get("ratio", v.get("ratio_not_used_footprint_not_shown_comparable")),
                 "ratio_used": "ratio" in v,
                 **{t: bool(v["footprint_tests"][t]["passes"]) for t in FOOTPRINT_TESTS},
                 "group": None if lab not in gr.member else (gr.first if gr.member[lab] else gr.second),
                 "not_classifiable": gr.extra["not_classifiable"].get(lab)}
                for lab, v in gr.value.items()]
            by_condition[tag]["contrast_estimable_on_quantities"] = (
                "no: " + ", ".join(g[s]["group"] for s in ("first", "second") if g[s]["hosts"] == 0) + " has no classifiable host"
                if any(g[s]["hosts"] == 0 for s in ("first", "second")) else "both groups have a host (the rank test is made with the fit)")
    own3, st3 = gs[2], gs[3]
    differ = [h for h in own3.member if own3.member[h] != st3.member[h]]
    by_condition["retail_choice_proxy_the_two_readings"] = {
        "coded": HOST_OWN, "reported_beside_it": STATE_ANY,
        "hosts_whose_group_differs_between_the_readings": [{"utility": h, "name": names.get(oa_key(h))} for h in differ],
        "counts_in_first_group": {HOST_OWN: int(sum(own3.member.values())), STATE_ANY: int(sum(st3.member.values()))}}
    return {"hosts_in_the_design": len(hosts), "hosts_dropped_from_the_design": d.dropped,
            "host_weights_from": "inference_check.implied_weights on the design as built (regressors only; no outcome)",
            "hosts": _host_rows(d, names, gs, weights, settled), "conditions": by_condition}


def oa_key(label: str) -> tuple:
    u, s = label.split(":")
    return (int(u), s)


def main() -> int:
    """The headline set and every cohort utility as built, at 2%, under the headline rules, built as design.main builds
    them; each host's value and group on conditions 1 to 3 (condition 3 under both readings), counts, names, states and
    weight shares; condition 4 from the peak-demand table (read by explicit columns only), each host's ratio and group or
    its reason for not being classifiable. Quantities only: no price, revenue or bill is read."""
    from pipeline.analysis import design, usable_flag
    rules = ps.HEADLINE_RULES
    q, dose, regions, fuel, dd = design.load()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    names = q.groupby(KEY).utility_name.last()
    names = {(int(u), s): n for (u, s), n in names.items()}
    settled = set(ps.history_settled(0.02))
    peaks = read_peaks()
    has_pred = {(int(u), s) for u, s in q.loc[q.has_predecessors.astype(bool), KEY].drop_duplicates().itertuples(index=False)}
    classes_per_id = q.groupby("utility_id_eia").ownership.nunique()
    report = {
        "what_this_is": ("Quantity-only and provisional. The host groupings for the four conditions tested (PREANALYSIS.md, "
                         "'Conditions tested (four)'), under the owner's ruling of 2026-11-19, on the design as it stands of "
                         "2026-11-18 (the plan is a DRAFT and not frozen; every set membership here is provisional, Inference). "
                         "No outcome, price, revenue or bill is read; no contrast is estimated. Built by "
                         "pipeline/analysis/conditions.py."),
        "threshold": "2%", "rules": rules.label,
        "condition_1": {"field": "utility_year_dose.parquet: dose (crypto not counted)", "year": "cohort + 3 (event year 3)",
                        "rule": "10% or more: dose >= 0.10", "what_it_is": "descriptive exposure grouping"},
        "condition_2": {"field": "panel_quantities.parquet: ownership, read by power_simulation.ownership_classes",
                        "construction": "modal EIA entity type over the utility's own filings, one value per EIA id for every year",
                        "eia_ids_with_more_than_one_class_in_the_file": int((classes_per_id > 1).sum())},
        "condition_3": {"field": "panel_quantities.parquet: res_mwh_delivery", "year": "cohort - 3 (the reference year)",
                        "rule_coded": "the host's own unit reports delivery-only residential sales above zero",
                        "reported_beside_it": "any unit in the host's state reports delivery-only residential sales above zero",
                        "label": PROXY_LABEL},
        "condition_4": {"source": PEAK_TABLE, "rule": RULE_SOURCE,
                        "peak": "the larger of summer and winter peak demand; zero or missing in both is no report; an EIA-imputed row is no report",
                        "ratio": "peak in the reference year (cohort - 3) over the largest peak reported in any earlier year from 2001",
                        "groups": "strictly above the median of the classifiable hosts in the estimate, against at or below it",
                        "not_classifiable": "named with the reason and left out of this condition's contrast only",
                        "comparable_footprints": {"ruling_of_2026_11_19": UTILIZATION_RULING_2026_11_19, **FOOTPRINT_RULE},
                        "what_it_measures": "how hard the system had been used; not spare generation or network capacity"},
        "sets": {}}
    for which in (ps.HEADLINE_SET, "every_cohort_utility"):
        treated, clean = design.split(0.02, which, q, dose)
        d = design.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                                    ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
        report["sets"][which] = summarise_set(d, dose, q, ownership_of, names, settled, rules.fuel_control, peaks, has_pred)
        s = report["sets"][which]
        print(which, "| hosts", s["hosts_in_the_design"])
        for tag, c in s["conditions"].items():
            if "groups" in c:
                g1, g2 = c["groups"]["first"], c["groups"]["second"]
                print(f"  {tag}: {g1['hosts']} / {g2['hosts']} hosts; states {g1['number_of_states']} / {g2['number_of_states']}; "
                      f"weight {g1['share_of_host_side_weight']} / {g2['share_of_host_side_weight']}")
    (FROZEN / "conditions_groups.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
