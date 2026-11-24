#!/usr/bin/env python3
"""The design side of the runs that do not change the facility inventory. Load and sales only; no price is read.

PREANALYSIS.md, "Other runs, listed in advance" and "Other outcomes and robustness". Each function here returns a
design.Design (the object the estimator path takes: hosts, windows, matches) or the closest thing to it, together with a
quantity-only report of who is in, who is left out and why. Matching, the support rule, ownership and usability are never
re-implemented: every design is built by design.build_with_rules under the headline rules, and every removal of units goes
through influence.leave_out. The fingerprinted files are not changed.

The runs:

E1   events shifted six years early (G-a). A shift of every host's cohort by six years is all the run needs: the builder's
     window for a cohort g' = g - 6 is g' - 6 to g' + 3 (calendar g - 12 to g - 3), its reference year is g' - 3 = g - 9,
     the ownership rule is read over that window and no later, usability is read over it, and the support rule reads fake
     event years 2 and 3. Hosts of cohorts 2011 and 2012 are left out and named.
E3   2021 to 2023 removed (full windows). The usable unit-years of 2021 to 2023 are taken out for every unit and the
     ten-year rule is kept, so cohorts 2018 to 2022 leave by name and cohorts 2011 to 2017 are unchanged, matches
     included (e3_equals_cohort_restriction checks this on any design).
E5   high-upward-scaling states dropped (G-b). Under Joe's ruling of 2026-11-19 the lists are built from the factor rule
     over every state of the full state_anchor table, not from inventory_report.json's block: a computed factor of 2 or
     more is dropped (the cap of 3.0 included, small state or not); the fallback 1.0 (raw factor undefined) is flagged
     and named on a second list, not dropped.
E6   comparison utilities that change market region dropped (G-b).
G-b  remove_units: hosts named and removed, comparison utilities removed from every host's matches by
     influence.leave_out with no rematching, and a host left with fewer than five (or none) excluded and named.
A longer horizon   cohorts 2011 to 2019, thirteen years g - 6 to g + 6; usability in all thirteen years and the ownership
     rule over all thirteen applied before matching, each host matched again among the units eligible for the long window.
Thresholds of 1% and 5%   every cohort utility as built at 1% (the owner's ruling of 2026-11-19); at 5% the headline rules
     and every cohort utility as built, Rappahannock Electric Cooperative set aside, the version with it as the footnote.
Own state   comparison utilities from the host's own state only, all other rules, the ten closest in size.

Run:  python3 -I pipeline/analysis/side_runs.py      writes data/frozen/side_run_designs.json (quantity only, provisional)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import design  # noqa: E402
from pipeline.analysis import influence  # noqa: E402
from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
FROZEN = ROOT / "data" / "frozen"
OUT = FROZEN / "side_run_designs.json"

# ---- E1 -------------------------------------------------------------------------------------------------------------
E1_SHIFT = 6
E1_COHORTS = (2013, 2022)                  # a host of 2011 or 2012 would need 1999 or 2000 (Joe, D-99)
E1_LEFT_OUT = ("cohort 2011 or 2012: its shifted window would begin in 1999 or 2000, before the panel; the ten-year window "
               "rule is kept intact (E1; Joe, D-99)")

# ---- E3 -------------------------------------------------------------------------------------------------------------
E3_DROPPED_YEARS = (2021, 2022, 2023)
E3_KEPT_COHORTS = (2011, 2017)
E3_LEFT_OUT = ("its ten-year window includes a year of 2021 to 2023, whose outcome rows this run removes, so it has no "
               "complete window (E3, full windows; Joe, D-99)")

# ---- G-b, E5, E6 ----------------------------------------------------------------------------------------------------
INADEQUATE = influence.INADEQUATE           # five (G-b; Joe, D-99; D-100)
GB_FEWER = "fewer than five surviving comparison utilities: excluded from this sensitivity's estimate (G-b; Joe, D-99; D-100)"
GB_NONE = "no surviving comparison utility: not estimable, excluded from this sensitivity's estimate (G-b)"
E5_FACTOR_AT_LEAST = 2.0
E5_HOST_DROPPED = "a host in a state whose anchoring factor is 2 or more (E5)"
E6_YEARS = (2001, 2025)

# ---- the longer horizon -------------------------------------------------------------------------------------------
LONG_PRE, LONG_POST = ps.PRE, 6
LONG_COHORTS = (2011, 2019)
LONG_HEADLINE = (4, 5, 6)
LONG_NOT_IN_COHORTS = "first crossing after 2019: six years after it would pass 2025 (the longer horizon covers 2011 to 2019)"
LONG_NOT_USABLE = ("not usable, or without a region, degree days or a fuel-mix group, in every one of the thirteen years g-6 to "
                   "g+6 (the longer horizon: rule 6.3 read for a thirteen-year window, adopted by Joe on 2026-11-19, D-111)")

# ---- thresholds -----------------------------------------------------------------------------------------------------
RAPPAHANNOCK = (40228, "VA")
RAPPAHANNOCK_ASIDE = ("set aside from the 5% run: its sales base straddles its 2010 purchase of half of Potomac Edison's "
                      "Virginia territory (D-26); the run with it included is the footnote")
EXPLORATORY_1PCT = ("exploratory: every cohort utility as built at 1%, not screened by a newly invented 1% place test, with the "
                    "comparison, availability and support restrictions applied (owner's ruling, 2026-11-19)")
OWNER_RULING_1PCT = ("Adopt every cohort utility as built for the 1% run, labelled exploratory and not screened by a newly "
                     "invented 1% place test. Preserve applicable comparison, availability and support restrictions.")


def label(key) -> str:
    return f"{int(key[0])}:{key[1]}"


def _norm(key) -> tuple:
    return (int(key[0]), str(key[1]))


class Inputs:
    """What every build here takes, under the headline rules: the quantity frames, the ownership table, the usable flag,
    the gas shares, the unknown-load verdicts and the ownership classes. Holds no price."""

    def __init__(self, q, dose, regions, fuel, dd, *, ownership, usable, gas, unknown_load, ownership_of=None,
                 rules: ps.Rules = ps.HEADLINE_RULES, names: pd.Series | None = None):
        self.q, self.dose, self.regions, self.fuel, self.dd = q, dose, regions, fuel, dd
        self.ownership, self.usable, self.gas, self.unknown_load = ownership, usable, gas, unknown_load
        self.ownership_of = ownership_of if ownership_of is not None else ps.ownership_classes(q)
        self.rules = rules
        self.names = names if names is not None else (q.groupby(KEY).utility_name.last() if "utility_name" in q else pd.Series(dtype=object))

    def build(self, treated: pd.DataFrame, clean: pd.DataFrame, theta: float, usable: set | None = None) -> design.Design:
        """design.build_with_rules under the rules held here; `usable` replaces the usable set for this build only."""
        return design.build_with_rules(treated, clean, self.q, self.regions, self.fuel, self.dd, self.rules,
                                       ownership=self.ownership, usable=self.usable if usable is None else usable, gas=self.gas,
                                       ownership_of=self.ownership_of, unknown_load=self.unknown_load, theta=theta)


# ---- helpers on built designs ----------------------------------------------------------------------------------------

def host_keys(d: design.Design) -> list:
    return [_norm(k) for k in d.hosts.key] if len(d.hosts) else []


def matches_of(d: design.Design) -> dict:
    """{host key: [match keys in order]}."""
    return {_norm(k): [_norm(m) for m in mk] for k, mk in zip(d.hosts.key, d.hosts.match_keys)} if len(d.hosts) else {}


def changes_against(base: design.Design, other: design.Design, key_map: dict | None = None) -> dict:
    """Hosts and matches of `other` against `base`: hosts only in one, and for each host in both the matches added and
    removed. `key_map` maps other's host keys to base's where they differ (they never do here; hosts are keyed by unit)."""
    a, b = matches_of(base), matches_of(other)
    common = sorted(set(a) & set(b))
    changed = []
    for k in common:
        add = [label(m) for m in b[k] if m not in set(a[k])]
        rem = [label(m) for m in a[k] if m not in set(b[k])]
        if add or rem:
            changed.append({"host": label(k), "matches_added": add, "matches_removed": rem})
    return {"hosts_only_in_the_headline_design": [label(k) for k in sorted(set(a) - set(b))],
            "hosts_only_in_this_run": [label(k) for k in sorted(set(b) - set(a))],
            "hosts_in_both": len(common), "hosts_with_changed_matches": changed,
            "hosts_with_identical_matches": len(common) - len(changed)}


def same_design(a: design.Design, b: design.Design) -> bool:
    """True if the two designs have the same hosts with the same cohorts and the same matches in the same order."""
    ka = [(label(k), int(g)) for k, g in zip(a.hosts.key, a.hosts.cohort)] if len(a.hosts) else []
    kb = [(label(k), int(g)) for k, g in zip(b.hosts.key, b.hosts.cohort)] if len(b.hosts) else []
    return ka == kb and matches_of(a) == matches_of(b)


def support_counts(d: design.Design, events=(2, 3)) -> list:
    """Per host: the pool in its reference year and how many of its matches are in its region in the given event years,
    read from the host's window (design.support's definitions). Works on a Design whose matches were cut by a removal."""
    out = []
    for h in d.hosts.itertuples():
        w = d.windows[h.cohort]
        mine = w.region_t[h.row]
        m = np.array(h.matches, dtype=int)
        row = {"host": label(h.key), "cohort": int(h.cohort), "pool_in_the_reference_year": int(h.pool_in_the_reference_year),
               "matched_set_size": int(len(m))}
        for e in events:
            t = e + ps.PRE
            row[f"matched_in_region_event_year_{e}"] = int((w.region_t[m, t] == mine[t]).sum()) if len(m) else 0
        out.append(row)
    return out


def named(d: design.Design, keys) -> list:
    return [{"utility": label(k), "name": d_name(d, k)} for k in keys]


def d_name(d, key):
    names = getattr(d, "names", None)
    if names is None:
        return None
    v = names.get(_norm(key)) if hasattr(names, "get") else None
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)


def checks(d: design.Design, fuel_control: str = ps.GAS_SHARE) -> dict:
    """influence.estimable on the design: the rank test made before any fit, hosts with no matches and hosts with zero
    headline weight, from the regressors alone (no outcome). The estimator's own rank test (outcome_analysis) decides the
    run; this is the pre-fit reading on quantities. A failure in it is counted and reported, never dropped."""
    try:
        r = influence.estimable(d, fuel_control)
        return {"estimable_by_the_rank_test_before_any_fit": bool(r["estimable"]),
                "smallest_singular_value_ratio": float(r["smallest_singular_value_ratio"]),
                "hosts_with_no_matches": r["hosts_with_no_matches"], "hosts_with_zero_weight": r["hosts_with_zero_weight"],
                "numerical_failure": None}
    except Exception as exc:                                   # noqa: BLE001  reported, never dropped
        return {"estimable_by_the_rank_test_before_any_fit": False, "numerical_failure": f"{type(exc).__name__}: {exc}"}


# ---- G-b: remove units, no rematching --------------------------------------------------------------------------------

def remove_units(d: design.Design, hosts_out: dict | None = None, comparisons_out: set | None = None) -> design.Design:
    """G-b. `hosts_out` {key: reason} leave the design, named. Every copy of each key in `comparisons_out` leaves every
    host's matches (influence.leave_out); nothing is rematched and each host keeps its remaining matches in order. A host
    left with fewer than INADEQUATE surviving comparisons is excluded from the estimate and named; one left with none is
    named as not estimable. The returned Design carries `gb` (what was removed and who is excluded, with surviving counts)."""
    hosts_out = {_norm(k): v for k, v in (hosts_out or {}).items()}
    gone = {_norm(k) for k in (comparisons_out or set())}
    keep = np.array([_norm(k) not in hosts_out for k in d.hosts.key], dtype=bool) if len(d.hosts) else np.zeros(0, bool)
    d1 = influence._without(d, keep) if len(d.hosts) else d
    removed_hosts = [{"utility": label(k), "cohort": int(g), "why": hosts_out[_norm(k)]}
                     for k, g in zip(d.hosts.key, d.hosts.cohort) if _norm(k) in hosts_out] if len(d.hosts) else []
    d2 = influence.leave_out(d1, gone)
    before = {_norm(k): len(m) for k, m in zip(d1.hosts.key, d1.hosts.matches)} if len(d1.hosts) else {}
    excluded, rows = [], []
    for k, g, m in (zip(d2.hosts.key, d2.hosts.cohort, d2.hosts.matches) if len(d2.hosts) else []):
        n = len(m)
        lost = before[_norm(k)] - n
        rows.append({"host": label(k), "cohort": int(g), "matches_before": before[_norm(k)], "comparisons_removed": lost, "surviving": n})
        if n == 0:
            excluded.append({"utility": label(k), "cohort": int(g), "why": GB_NONE, "surviving": 0})
        elif n < INADEQUATE:
            excluded.append({"utility": label(k), "cohort": int(g), "why": GB_FEWER, "surviving": n})
    out_keys = {e["utility"] for e in excluded}
    keep2 = np.array([label(k) not in out_keys for k in d2.hosts.key], dtype=bool) if len(d2.hosts) else np.zeros(0, bool)
    d3 = influence._without(d2, keep2) if len(d2.hosts) else d2
    d3.dropped = list(d.dropped) + [{"utility": x["utility"], "cohort": x["cohort"], "why": x["why"]} for x in removed_hosts + excluded]
    for attr in ("rules", "unresolved_ownership", "load_unknown_excluded", "unknown_load_source", "names"):
        if hasattr(d, attr):
            setattr(d3, attr, getattr(d, attr))
    d3.support_table = None          # the base design's table describes the matches before the removal; see gb["by_host"]
    # The hosts this run removed (by name or under G-b) leave the unresolved-ownership list: it lists hosts of the design
    # it describes. Entries for hosts an earlier rule already moved out (in_this_run "excluded") are kept. Session 19.
    gone_hosts = {x["utility"] for x in removed_hosts + excluded}
    unresolved_removed = []
    if getattr(d3, "unresolved_ownership", None):
        unresolved_removed = [x for x in d3.unresolved_ownership if x.get("utility") in gone_hosts]
        d3.unresolved_ownership = [x for x in d3.unresolved_ownership if x.get("utility") not in gone_hosts]
    present = {_norm(m) for mk in d1.hosts.match_keys for m in mk} if len(d1.hosts) else set()
    d3.gb = {"hosts_removed": removed_hosts, "hosts_excluded_under_g_b": excluded, "by_host": rows,
             "comparison_units_removed_that_were_matched": sorted(label(k) for k in gone & present),
             "comparison_units_on_the_list_not_matched_to_any_host": len(gone - present),
             "unresolved_ownership_hosts_removed_by_this_run": [x.get("utility") for x in unresolved_removed],
             "rule": "G-b: no rematching; a host left with fewer than five surviving comparisons is excluded and named, as is one "
                     "left with none (not estimable); a host left with zero weight is not estimable (the estimator's check). "
                     "The support rule's 8-of-10 lines are not re-applied after the removal (G-b gives its own rule; the agent's "
                     "reading); the surviving in-region counts are reported."}
    return d3


# ---- E1 --------------------------------------------------------------------------------------------------------------

def e1_hosts(treated: pd.DataFrame, shift: int = E1_SHIFT, cohorts=E1_COHORTS) -> tuple[pd.DataFrame, list]:
    """(hosts of cohorts 2013 to 2022 with cohort shifted to g - 6 and the real one kept as `real_cohort`, those left out)."""
    t = treated.copy()
    t["cohort"] = t.cohort.astype(int)
    inside = t.cohort.between(*cohorts)
    left = [{"utility": f"{int(u)}:{st}", "cohort": int(g), "why": E1_LEFT_OUT} for u, st, g in zip(t.utility_id_eia[~inside], t.state[~inside], t.cohort[~inside])]
    s = t[inside].copy()
    s["real_cohort"] = s.cohort
    s["cohort"] = s.cohort - shift
    return s, left


def e1(inp: Inputs, treated: pd.DataFrame, clean: pd.DataFrame, theta: float, shift: int = E1_SHIFT,
       cohorts=E1_COHORTS) -> design.Design:
    """E1 under G-a: each host's window is g-12 to g-3 with reference g-9; comparisons matched at g-9; the same-parent rule,
    usability and the support rule over the fake window only. The Design's cohorts are the fake dates g' = g - 6 (what the
    estimator stacks on); `real_cohort` maps each host to its real g; `left_out` names cohorts 2011 and 2012."""
    s, left = e1_hosts(treated, shift, cohorts)
    d = inp.build(s[KEY + ["cohort"]], clean, theta)
    real = {(int(u), st): int(g) for u, st, g in zip(s.utility_id_eia, s.state, s.real_cohort)}
    d.real_cohort = real
    d.left_out = left
    d.dropped = left + list(d.dropped)
    d.windows_in_calendar_years = {int(g): (int(g) - ps.PRE, int(g) + ps.POST) for g in d.windows}
    return d


def largest_share(dose: pd.DataFrame, key, first: int, last: int) -> float:
    """The unit's largest data center load share (the dose) in calendar years first to last; 0.0 where it has no row."""
    m = dose[(dose.utility_id_eia == int(key[0])) & (dose.state == key[1]) & dose.year.between(first, last)]
    return float(m.dose.max()) if len(m) and m.dose.notna().any() else 0.0


def e1_report(d: design.Design, dose: pd.DataFrame, theta: float) -> list:
    """Each retained host's largest load share over its fake window g-12 to g-3 (below the threshold by definition)."""
    out = []
    for k in host_keys(d):
        g = d.real_cohort[k]
        v = largest_share(dose, k, g - 12, g - 3)
        out.append({"host": label(k), "real_cohort": g, "fake_cohort": g - E1_SHIFT, "window": [g - 12, g - 3],
                    "reference_year": g - 9, "fake_headline_years": [g - 4, g - 3], "fake_anticipation_years": [g - 8, g - 7],
                    "fake_early_years": [g - 12, g - 11, g - 10], "largest_load_share_in_the_fake_window": round(v, 6),
                    "below_the_threshold": bool(v < theta)})
    return out


# ---- E3 --------------------------------------------------------------------------------------------------------------

def e3_usable(usable: set, years=E3_DROPPED_YEARS) -> set:
    """The usable set with every unit's 2021 to 2023 unit-years removed (E3: outcome rows of those years removed)."""
    return {(int(u), s, int(y)) for u, s, y in usable if int(y) not in years}


def e3(inp: Inputs, treated: pd.DataFrame, clean: pd.DataFrame, theta: float, years=E3_DROPPED_YEARS) -> design.Design:
    """E3, full windows: the design with 2021 to 2023 removed from the usable set and the ten-year rule kept. Hosts of
    cohorts 2018 to 2022 leave with E3_LEFT_OUT in `dropped`. The Design carries `left_out` (those hosts).

    The hosts whose window meets 2021 to 2023 are named here, by the same ten-year test the builder applies, before the
    builder is called: power_simulation.build_windows raises a TypeError, rather than returning an empty window, for a
    cohort in which no unit has a complete window, which is every cohort of 2018 to 2022 once those years are removed. The
    comparison utilities' eligibility is read by the builder on the reduced usable set."""
    dropped_years = tuple(years)
    usable3 = e3_usable(inp.usable, dropped_years)
    left, keep = [], []
    for u, st, g in zip(treated.utility_id_eia, treated.state, treated.cohort.astype(int)):
        years = range(g - ps.PRE, g + ps.POST + 1)
        meets = any(y in dropped_years for y in years)
        lacks = not all((int(u), st, y) in usable3 for y in years)
        if meets and lacks:
            left.append({"utility": f"{int(u)}:{st}", "cohort": int(g), "why": E3_LEFT_OUT})
        keep.append(not (meets and lacks))
    t = treated[np.array(keep, dtype=bool)] if len(treated) else treated
    d = inp.build(t, clean, theta, usable=usable3) if len(t) else _empty(inp, clean, theta)
    d.dropped = left + list(d.dropped)
    d.left_out = left
    return d


def _empty(inp: Inputs, clean: pd.DataFrame, theta: float) -> design.Design:
    """A Design with no host (every host left out before matching)."""
    d = design.Design(pd.DataFrame(columns=["key", "cohort", "row", "state", "region", "matches", "match_keys", "pool_in_the_reference_year"]),
                      {}, {}, [], {}, {}, {}, inp.gas)
    d.support_table, d.unresolved_ownership, d.load_unknown_excluded = None, [], []
    return d


def e3_restricted(inp: Inputs, treated: pd.DataFrame, clean: pd.DataFrame, theta: float) -> design.Design:
    """The headline design restricted to cohorts 2011 to 2017: what E3 must equal, hosts and matches."""
    t = treated[treated.cohort.astype(int).between(*E3_KEPT_COHORTS)]
    return inp.build(t, clean, theta)


def e3_equals_cohort_restriction(inp: Inputs, treated: pd.DataFrame, clean: pd.DataFrame, theta: float) -> bool:
    return same_design(e3(inp, treated, clean, theta), e3_restricted(inp, treated, clean, theta))


# ---- E5 --------------------------------------------------------------------------------------------------------------

STATE_ANCHOR_FIELDS = ("state", "epri_twh", "permit_twh", "epoch_twh", "raw_factor", "factor", "flag")


def read_state_anchor_block(path: Path | None = None) -> list:
    """inventory_report.json's state_anchor block, with its field names confirmed. Stops in words if a field is missing."""
    rep = json.loads(((path or FROZEN / "inventory_report.json")).read_text())
    block = rep.get("state_anchor")
    if not isinstance(block, list) or not block:
        raise ValueError("inventory_report.json has no state_anchor list; E5's list of states cannot be fixed")
    for r in block:
        missing = [f for f in STATE_ANCHOR_FIELDS if f not in r]
        if missing:
            raise ValueError(f"inventory_report.json state_anchor row {r.get('state')} lacks {missing}; E5's list cannot be fixed")
    return block


def _nan(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v))


E5_RULING_2026_11_19 = ("Resolve E5's omitted states against the actual adopted factor rule: valid computed factors of 3.0 "
                        "meet the exclusion threshold; fallback values receive the adopted fallback treatment.")
# The four the plan names at 0.2: on neither list, adopted by Joe on 2026-11-19 (D-111).
E5_LOWER_LIMIT_NAMED_IN_THE_PLAN = ("NE", "NM", "NV", "TN")
COMPUTED, FALLBACK = "computed", "fallback"


def _anchor_kind(raw, factor, lo: float, hi: float) -> dict:
    """How state_anchor arrived at a state's factor: a value computed from a defined raw factor (and whether clipped to the
    band), or the fallback 1.0 where the raw factor is undefined. Stops in words if the factor is not what the rule gives."""
    if _nan(raw):
        if _nan(factor) or float(factor) != 1.0:
            raise ValueError(f"raw factor undefined but factor {factor!r}, not the fallback 1.0; state_anchor's rule does not give it")
        return {"factor_is": FALLBACK, "clipped_to": None}
    raw = float(raw)
    want = min(max(raw, lo), hi)
    if _nan(factor) or abs(float(factor) - want) > 1e-9:
        raise ValueError(f"factor {factor!r} is not the raw factor {raw!r} clipped to [{lo}, {hi}]; state_anchor's rule does not give it")
    return {"factor_is": COMPUTED, "clipped_to": hi if raw > hi else lo if raw < lo else None}


def _lists(rows: list, lo: float) -> dict:
    """E5's two lists from rows that carry factor_is: a computed factor of 2 or more is dropped; a fallback is flagged and
    named, not dropped (the plan's adopted fallback treatment); a computed factor below 2 is on neither list."""
    dropped = [r for r in rows if r["factor_is"] == COMPUTED and r["factor"] >= E5_FACTOR_AT_LEAST]
    flagged = [{**r, "why": "raw factor undefined (no dated permit-based load to scale), factor set to the fallback 1.0; "
                            "flagged and not dropped, and not read as evidence of adequate coverage"}
               for r in rows if r["factor_is"] == FALLBACK]
    capped = [{**r, "cap": r["clipped_to"]} for r in rows if r["clipped_to"] is not None]
    lower = [r for r in rows if r["factor_is"] == COMPUTED and r["factor"] == lo]
    return {"dropped": dropped, "flagged_not_dropped": flagged, "capped": capped, "at_the_lower_limit": lower}


def e5_states(block: list, all_states: pd.DataFrame | None = None, lo: float | None = None, hi: float | None = None) -> dict:
    """E5's lists under Joe's ruling of 2026-11-19 (E5_RULING_2026_11_19), built from the factor rule over EVERY state of
    the full state_anchor table (`all_states`, data/interim/state_anchor.parquet), not from the report's block, which keeps
    only states whose EPRI total is 0.25 TWh or more:

    dropped              a computed factor (raw factor defined) of 2 or more, small state or not, so a computed factor
                         clipped to the cap of 3.0 is dropped
    flagged_not_dropped  the fallback 1.0 (raw factor undefined): the plan's adopted fallback treatment, flagged and named
                         on the second list, not dropped
    capped               computed factors clipped to the band [lo, hi] (reported)
    at_the_lower_limit   computed factors at the lower limit lo, on neither list: those the plan names are marked (adopted
                         by Joe on 2026-11-19, D-111), any other is reported as added by the full table and not decided
    computed_but_not_in_the_report_block  the states the block leaves out, each with how its factor arose

    `block` (inventory_report.json's state_anchor) is checked against the table for the states it carries (to the 3
    decimals the block is rounded to) and the lists the block alone gives are kept under `from_the_report_block_alone`
    for the record. Each row says whether its factor is computed or the fallback and whether it is clipped; the table's
    `flag` is carried but not used, since `small_state` is tested first and hides that. Stops in words on any
    inconsistency."""
    from pipeline.facilities import build_inventory as bi
    lo = bi.SCALE_LO if lo is None else lo
    hi = bi.SCALE_HI if hi is None else hi
    if all_states is None:
        raise ValueError("E5's lists are built from the full state_anchor table (Joe, 2026-11-19); pass it as all_states")
    for c in STATE_ANCHOR_FIELDS:
        if c not in all_states.columns:
            raise ValueError(f"the state_anchor table has no column {c!r}; E5's list cannot be fixed")
    if all_states.state.duplicated().any():
        raise ValueError(f"the state_anchor table repeats states {sorted(set(all_states.state[all_states.state.duplicated()]))}")
    inb = {r["state"]: r for r in block}
    table = {r.state: r for r in all_states.itertuples(index=False)}
    missing = sorted(set(inb) - set(table))
    if missing:
        raise ValueError(f"the report's block has states the full table lacks: {missing}")
    for st, b in inb.items():
        t = table[st]
        for fld in ("raw_factor", "factor", "epri_twh"):
            bv, tv = b[fld], getattr(t, fld)
            if _nan(bv) != _nan(tv) or (not _nan(bv) and abs(float(bv) - round(float(tv), 3)) > 5e-4 + 1e-12):
                raise ValueError(f"{st}: the report's block has {fld} {bv!r}, the table {tv!r}; they disagree")
    rows = []
    for st in sorted(table):
        t = table[st]
        kind = _anchor_kind(t.raw_factor, t.factor, lo, hi)
        rows.append({"state": st, "factor": None if _nan(t.factor) else float(t.factor),
                     "raw_factor": None if _nan(t.raw_factor) else float(t.raw_factor), "flag": t.flag,
                     "epri_twh": float(t.epri_twh), "permit_twh": float(t.permit_twh), "epoch_twh": float(t.epoch_twh),
                     "in_report_block": st in inb, **kind})
    out = _lists(rows, lo)
    for r in out["at_the_lower_limit"]:
        r["named_in_the_plan"] = r["state"] in E5_LOWER_LIMIT_NAMED_IN_THE_PLAN
        r["status"] = ("named in the plan, left as it is (adopted by Joe on 2026-11-19, D-111)" if r["named_in_the_plan"] else
                       "added by the full table, not decided (the ruling does not address the lower limit)")
    out["computed_but_not_in_the_report_block"] = [
        {**{k: r[k] for k in ("state", "factor", "raw_factor", "flag", "factor_is", "clipped_to", "epri_twh", "permit_twh")},
         "factor_2_or_more": bool(r["factor"] >= E5_FACTOR_AT_LEAST)} for r in rows if not r["in_report_block"]]
    out["from_the_report_block_alone"] = {k: [r["state"] for r in v] for k, v in
                                          _lists([r for r in rows if r["in_report_block"]], lo).items()}
    out["built_from"] = ("every state of data/interim/state_anchor.parquet, by the factor rule (Joe's ruling of 2026-11-19); "
                         "the report block is checked against it")
    out["ruling_of_2026_11_19"] = E5_RULING_2026_11_19
    return out


E5_DEFINITION = {
    "source": "pipeline/facilities/build_inventory.py, state_anchor(); reported in data/frozen/inventory_report.json, state_anchor",
    "raw_factor": "(EPRI's 2024 state total minus the measured (Epoch and operator-reported) load in 2024, floored at zero) divided by "
                  "the 2024 permit-based load; undefined where the permit-based load is zero",
    "factor": "raw_factor clipped to [SCALE_LO, SCALE_HI] = [0.2, 3.0]; where raw_factor is undefined, the fallback 1.0",
    "flag": "small_state where EPRI's total is under 0.25 TWh, else no_dated_permits where raw_factor is undefined, undercounted "
            "above 3.0, overcounted below 0.2, ok otherwise (checked in that order)",
    "report_block": "the report keeps only states whose EPRI total is 0.25 TWh or more (build_inventory.main); the factor is applied "
                    "to every state's permit-based rows, including those left out of the block",
    "applied_to": "permit-based rows only; measured rows are not scaled",
    "lists": ("built from every state of data/interim/state_anchor.parquet by the factor rule (Joe's ruling of 2026-11-19): a "
              "computed factor (raw factor defined) of 2 or more is dropped, the cap of 3.0 included, small state or not; the "
              "fallback 1.0 (raw factor undefined) is flagged and named on the second list, not dropped; computed factors at the "
              "lower limit of 0.2 are reported and on neither list, which Joe adopted on 2026-11-19 (D-111) for the four the plan "
              "names; any other is not decided"),
}


def factor_applied(fac: pd.DataFrame, rows: list) -> list:
    """For each state in `rows` (e5_states' row dicts), whether build_inventory applied its factor: the distinct state_scale
    values on its permit-based rows (not Epoch, not a verified public figure, not operator-reported energy: the rows
    build_inventory scales) and on its measured rows, from facilities.parquet. Quantities only."""
    measured = (fac.src == "epoch") | fac.mw_basis.isin(["verified_public_figure", "operator_reported_energy"])
    out = []
    for r in rows:
        f = fac[fac.state == r["state"]]
        m = measured[f.index]
        p_scales = sorted({round(float(x), 6) for x in f.state_scale[~m]})
        out.append({"state": r["state"], "factor": r["factor"], "factor_is": r["factor_is"],
                    "permit_based_rows": int((~m).sum()), "permit_based_rows_in_the_dose": int(f.in_dose[~m].sum()),
                    "state_scale_on_permit_based_rows": p_scales,
                    "state_scale_on_measured_rows": sorted({round(float(x), 6) for x in f.state_scale[m]}),
                    "factor_applied_to_permit_based_rows": (None if not len(p_scales) else
                                                            p_scales == [round(float(r["factor"]), 6)])})
    return out


def e5(d: design.Design, states: set) -> design.Design:
    """E5 under G-b: hosts in `states` removed and named; comparison utilities in `states` removed from every host's matches."""
    states = set(states)
    hosts_out = {k: E5_HOST_DROPPED for k in host_keys(d) if k[1] in states}
    comps = {_norm(m) for mk in (d.hosts.match_keys if len(d.hosts) else []) for m in mk if m[1] in states}
    return remove_units(d, hosts_out, comps)


# ---- E6 --------------------------------------------------------------------------------------------------------------

def region_changers(regions: pd.DataFrame, units, q: pd.DataFrame | None = None, years=E6_YEARS) -> dict:
    """Among `units`, those whose region (market_region.by_unit_year) is not the same in every year from `years[0]` to
    `years[1]` in which it has a region (the coded rule), and, as a gap count, those that would also count if a year in
    which the unit has no panel row counted as a change. by_unit_year gives every unit a region in every year (carried,
    moved or the state's), so a unit's absence from the panel does not by itself leave it without a region."""
    units = {_norm(k) for k in units}
    r = regions[regions.year.between(*years) & regions.region.notna()]
    r = r[[(int(u), s) in units for u, s in zip(r.utility_id_eia, r.state)]]
    n = r.groupby(KEY).region.nunique()
    changers = {_norm(k) for k, v in n.items() if v > 1}
    out = {"coded": sorted(changers)}
    if q is not None:
        yrs = set(range(years[0], years[1] + 1))
        have = q[q.year.between(*years)].groupby(KEY).year.agg(set)
        absent = {k for k in units if not yrs <= have.get(k, set())}
        out["absent_in_some_year"] = sorted(absent)
        out["coded_or_absent_in_some_year"] = sorted(changers | absent)
    return out


def e6(d: design.Design, changers: set) -> design.Design:
    """E6 under G-b: the listed comparison units removed from every host's matches. Hosts that change region stay."""
    return remove_units(d, {}, set(changers))


# ---- the longer horizon --------------------------------------------------------------------------------------------

def build_windows_span(cohorts, p: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict, dd: pd.DataFrame,
                       unit_code: dict, state_code: dict, pre: int = ps.PRE, post: int = ps.POST, ref: int = ps.REF) -> dict:
    """power_simulation.build_windows with the window's length as arguments: years g - pre to g + post, sizes and the
    matched region read in g + ref. With (PRE, POST, REF) it gives exactly what build_windows gives (tested); the
    fingerprinted function is not changed."""
    own = q.groupby(KEY).agg(ownership=("ownership", "last"))
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    codes = {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}
    names = {i: r for r, i in codes.items()}
    out = {}
    for g in cohorts:
        years = list(range(g - pre, g + post + 1))
        y = ps.balanced(p, "log_price", years)
        rt = ps.region_matrix(regions, y.index, years, codes)
        states = y.index.get_level_values(1)
        fu = np.array([fuel.get(st, np.nan) for st in states], dtype=float)
        hdd = np.array([[dd.hdd.get((st, yr), np.nan) for yr in years] for st in states]).reshape(len(states), len(years))
        cdd = np.array([[dd.cdd.get((st, yr), np.nan) for yr in years] for st in states]).reshape(len(states), len(years))
        size = cust.reindex(y.index)[g + ref].values
        keep = (~np.isnan(rt).any(1)) & ~np.isnan(fu) & ~np.isnan(hdd).any(1) & ~np.isnan(cdd).any(1) & (size > 0)
        a = own.reindex(y.index).assign(res_customers=size, region=[names.get(c) if not np.isnan(c) else None for c in rt[:, pre + ref]])
        out[int(g)] = ps.Window(int(g), y[keep], a[keep], unit_code, state_code, rt[keep].astype(int), fu[keep].astype(int),
                                hdd[keep], cdd[keep])
    return out


def _template(usable: set, everyone: pd.DataFrame) -> pd.DataFrame:
    ok = pd.DataFrame([(int(u), s, int(y)) for u, s, y in usable], columns=KEY + ["year"]).merge(everyone, on=KEY)
    return ok.assign(log_price=0.0)


def merge_into(base: design.Design, parts: list) -> design.Design:
    """One Design on `base`'s windows from per-host or per-group builds. Each part's hosts and matches are carried by key
    into base's windows (a part's window holds a subset of base's units: the same per-unit test on fewer units), so the
    matches are the part's and the estimator reads one set of windows. `support_table`, `dropped`, `unresolved_ownership`
    and `load_unknown_excluded` are the parts' together. Raises if a key is missing from base's windows."""
    rows, dropped, tables, unresolved, lu = [], [], [], [], []
    for p in parts:
        dropped += list(p.dropped)
        if getattr(p, "support_table", None) is not None:
            tables.append(p.support_table)
        unresolved += list(getattr(p, "unresolved_ownership", None) or [])
        lu += list(getattr(p, "load_unknown_excluded", None) or [])
        for h in p.hosts.to_dict("records"):
            g = int(h["cohort"])
            w = base.windows.get(g)
            if w is None or tuple(h["key"]) not in w.keys:
                raise ValueError(f"host {label(h['key'])} of cohort {g} is not in the base design's window")
            idx = {tuple(k): i for i, k in enumerate(w.keys)}
            miss = [label(m) for m in h["match_keys"] if tuple(m) not in idx]
            if miss:
                raise ValueError(f"matches {miss} of host {label(h['key'])} are not in the base design's window for {g}")
            h = dict(h)
            h["row"] = idx[tuple(h["key"])]
            h["matches"] = [idx[tuple(m)] for m in h["match_keys"]]
            rows.append(h)
    hosts = pd.DataFrame(rows) if rows else base.hosts.iloc[0:0].copy()
    if len(hosts):
        hosts = hosts.sort_values(["cohort", "row"], kind="stable").reset_index(drop=True)
    out = design.Design(hosts, base.windows, base.is_comp, dropped, base.region_names, base.unit_code, base.state_code, base.gas)
    out.support_table = pd.concat(tables, ignore_index=True) if tables else None
    out.unresolved_ownership = unresolved
    out.load_unknown_excluded = lu
    out.rules = getattr(base, "rules", None)
    return out


class LongHorizon:
    """The longer horizon's design: `design` on ten-year windows (the three-year number on the same utilities, and the
    support rule's event years 2 and 3), `windows13` the thirteen-year windows g-6 to g+6 by cohort, and `blocks13`
    [(cohort, host row, matched rows)] into them, the same hosts and matches. `report` is quantity only."""

    def __init__(self, d, windows13, blocks13, report):
        self.design, self.windows13, self.blocks13, self.report = d, windows13, blocks13, report


def long_horizon(inp: Inputs, treated: pd.DataFrame, clean: pd.DataFrame, theta: float, post: int = LONG_POST,
                 cohorts=LONG_COHORTS) -> LongHorizon:
    """Cohorts 2011 to 2019. For each cohort g the units eligible for the long window are those usable, with a region,
    degree days and a fuel-mix group, in every year g-6 to g+6 (applied before matching). For each host the ownership rule
    is read over g-6 to g+6 among the candidates in its region in its reference year, and they leave its pool before
    matching. Each host is then matched by design.build_with_rules on its own (the ten closest in size, the support rule on
    event years 2 and 3), and the hosts are put on one set of ten-year windows by merge_into."""
    t = treated.copy()
    t["cohort"] = t.cohort.astype(int)
    inside = t.cohort.between(*cohorts)
    left = [{"utility": f"{int(u)}:{st}", "cohort": int(g), "why": LONG_NOT_IN_COHORTS}
            for u, st, g in zip(t.utility_id_eia[~inside], t.state[~inside], t.cohort[~inside])]
    t = t[inside]
    base = inp.build(t[KEY + ["cohort"]], clean, theta)                       # windows that hold every unit the parts can use
    # the units the base build kept (after the unknown-load gate), so every code exists in base's unit_code
    everyone = pd.DataFrame(list(base.unit_code), columns=KEY)
    unit_code, state_code = base.unit_code, base.state_code
    template = _template(inp.usable, everyone)
    cohorts = sorted(int(g) for g in t.cohort.unique())
    windows13 = build_windows_span(cohorts, template, inp.q, inp.regions, inp.fuel, inp.dd, unit_code, state_code, LONG_PRE, post)
    clean_keys = {_norm(k) for k in clean[KEY].itertuples(index=False)}
    parts, extra_excluded, relabel = [], {}, []
    for r in t.itertuples():
        g, key = int(r.cohort), (int(r.utility_id_eia), r.state)
        w13 = windows13[g]
        ok13 = {_norm(k) for k in w13.keys}
        usable_g = {(u, s, y) for u, s, y in inp.usable if (int(u), s) in ok13}
        cand = []
        if key in ok13:
            j = [_norm(k) for k in w13.keys].index(key)
            region = w13.region[j]
            cand = [k for k, reg in zip(map(_norm, w13.keys), w13.region) if reg == region and k != key and k in clean_keys]
        out13 = {}
        if inp.rules.ownership != "off" and cand:
            out13 = own_rules.ineligible_for(inp.ownership, key, range(g - LONG_PRE, g + post + 1), cand, inp.ownership_of,
                                             inp.rules.ownership == "affiliates_readmitted")
        clean_h = clean[[(int(u), s) not in out13 for u, s in zip(clean.utility_id_eia, clean.state)]]
        p = inp.build(pd.DataFrame({"utility_id_eia": [key[0]], "state": [key[1]], "cohort": [g]}), clean_h, theta, usable=usable_g)
        for x in p.dropped:
            if x["why"] == design.NOT_USABLE:
                x["why"] = LONG_NOT_USABLE
        ten = set(own_rules.ineligible_for(inp.ownership, key, range(g - ps.PRE, g + ps.POST + 1), cand, inp.ownership_of,
                                           inp.rules.ownership == "affiliates_readmitted")) if inp.rules.ownership != "off" and cand else set()
        extra_excluded[label(key)] = [{"utility": label(c), "why": f"{why} (read over g-6 to g+6)"} for c, why in out13.items() if c not in ten]
        parts.append(p)
    d = merge_into(base, parts)
    d.dropped = left + list(d.dropped)
    blocks13 = []
    for h in d.hosts.itertuples():
        w = windows13[int(h.cohort)]
        idx = {tuple(k): i for i, k in enumerate(w.keys)}
        blocks13.append((int(h.cohort), np.array([idx[tuple(h.key)]]), np.array([idx[tuple(m)] for m in h.match_keys], dtype=int)))
    in_region_late = []
    for (g, tr, comp), h in zip(blocks13, d.hosts.itertuples()):
        w = windows13[g]
        row = {"host": label(h.key), "cohort": g}
        for e in [e for e in LONG_HEADLINE if e <= post]:
            t_ = e + LONG_PRE
            row[f"matched_in_region_event_year_{e}"] = int((w.region_t[comp, t_] == w.region_t[tr[0], t_]).sum())
        in_region_late.append(row)
    report = {"cohorts": list(LONG_COHORTS), "window": "g-6 to g+6", "headline": "mean of event years 4 to 6",
              "beside_it": "the three-year number (mean of event years 2 and 3) on the same hosts and the same matched utilities",
              "ownership_exclusions_added_by_the_years_g_plus_4_to_g_plus_6": {k: v for k, v in extra_excluded.items() if v},
              "matched_in_region_in_event_years_4_to_6": in_region_late,
              "support_rule": "applied as written (reference-year pool, event years 2 and 3); event years 4 to 6 are reported, not "
                              "tested (the plan states no support line for them; the agent's reading)"}
    return LongHorizon(d, windows13, blocks13, report)


# ---- thresholds -------------------------------------------------------------------------------------------------------

def history_at(theta: float, q: pd.DataFrame, dose: pd.DataFrame, table: pd.DataFrame | None = None) -> dict:
    """D-34 at any threshold, from the existing rule (pipeline/facilities/utility_history.py: read, settled) on the same
    base and sales buildout.py uses. The frozen files carry it at 2% and 5% only (ps.history_settled); this computes it at
    1% with no new rule. Returns {(utility, state): {"group", "first_crossing"}} as ps.design takes it."""
    from pipeline.facilities import utility_history as uh
    table = uh.load() if table is None else table
    if not len(table):
        return {}
    base = dose.drop_duplicates(KEY).set_index(KEY).base_retail_gwh
    base = base.combine_first(q[q.year.isin((2009, 2010, 2011))].groupby(KEY).total_retail_mwh.mean() / 1000.0)
    sales = q.set_index(KEY + ["year"]).total_retail_mwh / 1000.0
    return uh.settled(uh.read(table, base, sales, (theta,)), theta)


def every_cohort_at(theta: float, q: pd.DataFrame, dose: pd.DataFrame, *, history: dict, hold: set) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(hosts, comparison-eligible utilities) for every cohort utility as built at `theta`: ps.design with D-34 at `theta`
    (`history`, as history_at gives it) and the price hold `hold` (power_simulation.price_hold()). Both are required, with
    no default, and None is refused: before session 19 a missing history read the D-34 table and the hold was always read
    from price_hold.csv, so a run on invented inputs could pick up real lists of units without saying so.
    At 2% and 5% this equals design.split(theta, "every_cohort_utility", ...) when `history` is the frozen one."""
    if history is None or hold is None:
        raise ValueError("every_cohort_at needs history (history_at(theta, q, dose, table=...)) and hold "
                         "(power_simulation.price_hold()); neither is read from a file here")
    return ps.design(q, dose, theta, history, hold=set(hold))


def rappahannock_other_reasons(theta: float = 0.05, frozen: Path | None = None) -> list:
    """Rappahannock's reasons for being out of the headline set at `theta` other than D-26, from the frozen files."""
    why = [x for x in ps.dates_and_histories_reasons(theta, frozen).get(RAPPAHANNOCK, []) if not x.startswith("D-26")]
    for name, members in ps.bounds_lists(theta, frozen).items():
        if name not in ps.LISTS_THAT_SET_NO_ONE_ASIDE and RAPPAHANNOCK in members:
            why.append(f"treatment_bounds list {name}")
    return why


def without_rappahannock(treated: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    mask = np.array([_norm(k) != RAPPAHANNOCK for k in zip(treated.utility_id_eia, treated.state)], dtype=bool)
    left = [{"utility": label(RAPPAHANNOCK), "cohort": int(c), "why": RAPPAHANNOCK_ASIDE} for c in treated.cohort[~mask]]
    return treated[mask], left


# ---- own state -----------------------------------------------------------------------------------------------------

def own_state(inp: Inputs, treated: pd.DataFrame, clean: pd.DataFrame, theta: float) -> design.Design:
    """Comparison utilities from the host's own state only: for each state with a host, the pool restricted to that state,
    every other rule as in the headline (ownership, usability, price hold, unknown load, the ten closest in size, the support
    rule). The builder's pool is also the host's region in its reference year, which is kept (so the pool is the host's state
    within its region); the support rule's "in its region" lines are applied as written. Both adopted by Joe on 2026-11-19
    (D-111)."""
    base = inp.build(treated, clean, theta)
    parts = []
    for st in sorted(treated.state.unique()):
        p = inp.build(treated[treated.state == st], clean[clean.state == st], theta)
        parts.append(p)
    d = merge_into(base, parts)
    d.in_state_units_in_another_region = {}
    for h in d.hosts.itertuples():
        w = d.windows[h.cohort]
        other = sum(1 for k, reg, c in zip(w.keys, w.region, d.is_comp[h.cohort]) if c and k[1] == h.key[1] and reg != h.region)
        d.in_state_units_in_another_region[label(h.key)] = int(other)
    return d


# ---- reporting ------------------------------------------------------------------------------------------------------

def summary(d: design.Design, names: pd.Series, headline: design.Design | None = None, with_checks: bool = True) -> dict:
    """Quantity only: hosts retained (with cohorts, matches, support), hosts left out with reasons, changes against the
    headline design, and the pre-fit rank and zero-weight reading."""
    nm = lambda k: None if names.get(_norm(k)) is None else str(names.get(_norm(k)))  # noqa: E731
    hosts = []
    sup = {r["host"]: r for r in support_counts(d)} if len(d.hosts) else {}
    for h in d.hosts.itertuples():
        hosts.append({"utility": label(h.key), "name": nm(h.key), "cohort": int(h.cohort), "region": h.region,
                      "matched": [{"utility": label(m), "name": nm(m)} for m in h.match_keys], **{k: v for k, v in sup[label(h.key)].items()
                                                                                               if k not in ("host", "cohort")}})
    out = {"hosts_retained": len(hosts), "hosts": hosts,
           "hosts_left_out": [{**x, "name": nm(_key(x["utility"]))} for x in d.dropped],
           "support_rule_by_host": [] if getattr(d, "support_table", None) is None else d.support_table.to_dict("records"),
           "hosts_with_unresolved_ownership": [{"utility": x["utility"], "in_this_run": x.get("in_this_run")} for x in (getattr(d, "unresolved_ownership", None) or [])],
           "load_unknown_excluded": getattr(d, "load_unknown_excluded", [])}
    if headline is not None:
        out["changes_against_the_headline_design"] = changes_against(headline, d)
    if with_checks:
        out["pre_fit_checks"] = checks(d) if len(d.hosts) else {"estimable_by_the_rank_test_before_any_fit": False, "why": "no host retained"}
    return out


def _key(s: str) -> tuple:
    u, st = s.split(":")
    return (int(u), st)


def main() -> int:
    """Builds every run's design at 2% on the headline set (and every cohort utility as built, the labelled companion), the
    threshold runs at 1% and 5%, and writes data/frozen/side_run_designs.json. Load and sales only."""
    from pipeline.analysis import usable_flag
    t0 = time.time()
    rules = ps.HEADLINE_RULES
    q, dose, regions, fuel, dd = design.load()
    names = q.groupby(KEY).utility_name.last()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=flags.usable)
    inp = Inputs(q, dose, regions, fuel, dd, ownership=ownership, usable=usable, gas=gas, unknown_load=ps.load_unknown_load(),
                 rules=rules, names=names)
    timing = {}

    def timed(label_, f, *a):
        s = time.time()
        r = f(*a)
        timing[label_] = round(time.time() - s, 1)
        print(f"  {label_}: {timing[label_]} s", flush=True)
        return r

    report = {"what_this_is": "The design side of the runs that do not change the facility inventory (E1, E3 full windows, E5, E6, "
                              "the longer horizon, the thresholds of 1% and 5%, comparison utilities from the host's own state): hosts "
                              "retained, hosts left out with reasons, matches changed against the headline design, support, and the "
                              "fixed lists. Quantity only: load, sales, customers, ownership, the usable flag; no price, revenue or bill "
                              "is read. PROVISIONAL: the design as it stands on 2026-11-18; the plan is a draft and not frozen.",
              "built_by": "pipeline/analysis/side_runs.py", "rules": rules.label,
              "inference_note": "under the procedure validated on the headline set; no validation was made on these designs "
                                "(PREANALYSIS.md, Inference, where the validation does not transfer)",
              "code_version": design.code_version(design.CODE_FILES + ("pipeline/analysis/side_runs.py",)),
              "sets": {}}

    # E5 and E6 fixed lists (one each, before any set)
    block = read_state_anchor_block()
    all_states = pd.read_parquet(ROOT / "data" / "interim" / "state_anchor.parquet")
    lists5 = e5_states(block, all_states)
    drop_states = {r["state"] for r in lists5["dropped"]}
    block_states = set(lists5["from_the_report_block_alone"]["dropped"])        # the list before the ruling, for the record
    fac = pd.read_parquet(ROOT / "data" / "interim" / "facilities.parquet",
                          columns=["state", "src", "mw_basis", "state_scale", "in_dose"])
    report["e5_lists"] = {**lists5, "definition": E5_DEFINITION,
                          "fields_confirmed": list(STATE_ANCHOR_FIELDS),
                          "factor_applied_in_the_states_outside_the_report_block": factor_applied(
                              fac, [r for r in lists5["computed_but_not_in_the_report_block"]]),
                          "lists_before_the_ruling_of_2026_11_19": {
                              "dropped": sorted(block_states),
                              "flagged_not_dropped": lists5["from_the_report_block_alone"]["flagged_not_dropped"],
                              "built_from": "inventory_report.json's state_anchor block alone (states with an EPRI total of 0.25 TWh or more)"}}

    designs = {}
    for which in (ps.HEADLINE_SET, "every_cohort_utility"):
        print(which, flush=True)
        treated, clean = design.split(0.02, which, q, dose)
        head = timed(f"{which}: headline design", inp.build, treated, clean, 0.02)
        designs[which] = (treated, clean, head)
    matched_any = {_norm(m) for _, _, h in designs.values() for mk in h.hosts.match_keys for m in mk}
    ch = region_changers(regions, matched_any, q)
    report["e6_list"] = {"definition": "every comparison utility-state matched to any host in the headline design or in every cohort "
                                       "utility's design at 2% whose market region (market_region.by_unit_year) is not the same in every "
                                       "year 2001 to 2025 in which it has a region",
                         "units": [{"utility": label(k), "name": None if names.get(k) is None else str(names.get(k))} for k in ch["coded"]],
                         "count": len(ch["coded"]),
                         "gap_absent_in_any_year_counts_as_a_change": {
                             "count": len(ch["coded_or_absent_in_some_year"]),
                             "absent_from_the_panel_in_some_year_2001_to_2025": [label(k) for k in ch["absent_in_some_year"]]}}
    changers = set(ch["coded"])

    for which, (treated, clean, head) in designs.items():
        s = {"headline_design": summary(head, names, None)}
        d1 = timed(f"{which}: E1", e1, inp, treated, clean, 0.02)
        s["E1"] = {**summary(d1, names, head), "left_out_before_matching": d1.left_out, "hosts_by_window": e1_report(d1, dose, 0.02),
                   "cohort_note": "the Design's cohorts are the fake dates g - 6; real cohorts in hosts_by_window"}
        d3 = timed(f"{which}: E3", e3, inp, treated, clean, 0.02)
        s["E3"] = {**summary(d3, names, head), "equals_the_headline_design_restricted_to_cohorts_2011_to_2017":
                   same_design(d3, e3_restricted(inp, treated, clean, 0.02)),
                   "not_estimable_when": "no retained host meets the support rule and the full-window rule, or the fit fails the rank "
                                         "test (the estimator's); no host-count cutoff"}
        d5 = e5(head, drop_states)
        s["E5"] = {**summary(d5, names, head), "g_b": d5.gb, "states_dropped": sorted(drop_states)}
        b5 = e5(head, block_states)
        s["E5"]["before_the_ruling_of_2026_11_19_report_block_list"] = {
            "states_dropped": sorted(block_states), "hosts_retained": int(len(b5.hosts)),
            "hosts_removed": b5.gb["hosts_removed"], "hosts_excluded_under_g_b": b5.gb["hosts_excluded_under_g_b"],
            "comparison_units_removed_that_were_matched": b5.gb["comparison_units_removed_that_were_matched"],
            "status": "for the record: the run as it stood before the ruling; not the run"}
        d6 = e6(head, changers)
        s["E6"] = {**summary(d6, names, head), "g_b": d6.gb}
        lh = timed(f"{which}: longer horizon", long_horizon, inp, treated, clean, 0.02)
        s["longer_horizon"] = {**summary(lh.design, names, head), **lh.report,
                               "what_the_estimator_needs": "thirteen-year windows (side_runs.LongHorizon.windows13, blocks13): event "
                                                           "years -6 to +6 with -3 the reference, a headline combination over 4, 5 "
                                                           "and 6, and the three-year number on the same blocks; ps.assemble, "
                                                           "ps.T and ps.EVENT_TIMES are fixed at ten years"}
        os_ = timed(f"{which}: own state", own_state, inp, treated, clean, 0.02)
        s["own_state"] = {**summary(os_, names, head), "in_state_comparison_units_in_another_region_in_the_reference_year":
                          os_.in_state_units_in_another_region,
                          "rank_note": "with every matched set inside one state, the state-level degree-day columns are absorbed by the "
                                       "block-by-region-by-year effects and every gas-share column is screened out, so the main "
                                       "specification's regressors are rank deficient on this design (checked on quantities); the "
                                       "simulation ran this side form with no controls (ps.assemble controls=False). The run takes no "
                                       "controls where the set's year effects absorb them, adopted by Joe on "
                                       "2026-11-19 (D-111)"}
        report["sets"][f"{which}_2pct"] = s

    # thresholds
    th = {}
    h1 = history_at(0.01, q, dose)
    check = {f"{t:.0%}": sorted(label(k) for k in history_at(t, q, dose)) == sorted(label(k) for k in ps.history_settled(t)) for t in (0.02, 0.05)}
    tr1, cl1 = every_cohort_at(0.01, q, dose, history=h1, hold=ps.price_hold())
    d1pct = timed("1%: every cohort utility", inp.build, tr1, cl1, 0.01)
    th["1pct_every_cohort_utility_as_built"] = {**summary(d1pct, names, designs["every_cohort_utility"][2]), "label": EXPLORATORY_1PCT,
                                                "owner_ruling_2026_11_19": OWNER_RULING_1PCT, "cohort_utilities_as_built": int(len(tr1)),
                                                "d34_utility_level_histories_at_1pct": {label(k): v for k, v in h1.items()},
                                                "d34_recomputed_matches_the_frozen_lists_at": check,
                                                "unknown_load_at_1pct": "no enumeration verdict exists at 1%, so every utility a "
                                                                        "load-unknown site reaches is excluded on both sides (ps.UnknownLoad.gate)"}
    for which in (ps.HEADLINE_SET, "every_cohort_utility"):
        tr5, cl5 = design.split(0.05, which, q, dose)
        main5, left5 = without_rappahannock(tr5)
        d5m = timed(f"5%: {which}", inp.build, main5, cl5, 0.05)
        entry = {**summary(d5m, names, None), "set_aside_before_matching": left5}
        if which == ps.HEADLINE_SET:
            other = rappahannock_other_reasons(0.05)
            entry["footnote_with_rappahannock"] = ("identical to this run: Rappahannock is out of the headline set at 5% for other "
                                                   "reasons as well: " + "; ".join(other)) if other else "not computed"
        else:
            d5f = timed(f"5%: {which} footnote", inp.build, tr5, cl5, 0.05)
            entry["footnote_with_rappahannock"] = {**summary(d5f, names, d5m)}
        th[f"5pct_{which}"] = entry
    report["thresholds"] = th
    report["seconds"] = timing
    report["seconds_total"] = round(time.time() - t0, 1)
    OUT.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print("wrote", OUT, "in", report["seconds_total"], "s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
