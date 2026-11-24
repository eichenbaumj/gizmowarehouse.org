#!/usr/bin/env python3
"""The second number, per point of load (PREANALYSIS.md, "The second number: per point of load"; D-26, D-30, D-33, D-100,
D-101). Pre-freeze implementation. Load, sales and the usable flag only: nothing here reads, opens or prints a price,
a revenue or a bill. Every function that will one day take outcomes takes them as an argument.

What it builds
--------------
1. The primary run's frame, as the simulation's long comparison builds it (power_simulation.run_second_number), but
   on a sample the caller names and with the outcome as an argument: the change in log residential price from the
   2008 to 2010 average to the 2023 to 2025 average on the change in load share in points over the same span, within
   the utility's market region in 2009, its region in 2024 and its size band (residential customers in 2010), clustered
   by state; utilities usable in all six years. Load share counted at no more than 25 points, with the uncapped and
   50-point versions beside it every time. The fit and its range are the simulation's: estimator.Fit and
   Fit.summary with Rademacher weights, 999 replications (the wild cluster bootstrap as built, candidate A). The plan
   labels that range "not calibrated by the inference comparison" (D-101) and so does every output here.
2. Endpoint doses under uncertain assignment (rule 8.1): each utility's change in dose computed within one feasible
   history, the same at both endpoints. The histories are D-46 ruling 4's cases (as assigned; every unresolved site on
   it taken off; every unresolved site that lists it as a candidate counted on it), each as built and with no anchoring,
   read from assignment.matrices exactly as built. For a utility a site with no load history reaches, that site's
   admissible histories (timing.py's enumeration of its date and capacity questions) crossed with the same three
   cases, with the state's factor recomputed in each (pass_c_exact._State.grid).
3. The classification Joe adopted on 2026-11-19 (D-105), eight classes tested in order, first match wins, every
   utility in exactly one, AT EACH OF THE THREE CAPS SEPARATELY (section 3a). His words, unchanged: "Adopt the proposed
   classification with these qualifications: classify each form at its own cap; retain the apparent-zero flags when
   the settled convention takes precedence; count classes 5–8 as unsettled for leverage reporting; and name class 2
   for what it establishes-no endpoint exposure in modeled histories, not verified absence of sites. Apply the
   common-dose exception consistently to Umatilla. If complete admissible histories establish one common change in
   capped dose, apply that exception for the capped form. Otherwise retain exclusion and state what remains
   unestablished. Do not decide this merely by following the current code. Keep analysis eligibility separate from
   simulation-access eligibility." (His dashes are written here as hyphens.) Whether a common change is established
   for a utility at a capped form is NOT decided here: it is an explicit argument, `established`, with no default,
   which common_dose_rule.established_as_ruled supplies. Joe ruled on 2026-11-19 (D-107): "Keep Umatilla excluded
   from the common-dose exception: the wider admissible histories contain a counterexample. Do not narrow those
   histories to obtain settled status." So the exception is judged on the place test's wider set, and the summary's
   path refuses any other mapping (design_summary). "Settled" (class 4) is conditional on rule 8.1's modeled histories
   with dates held at their conventions (SETTLED_IS_CONDITIONAL, his clarification of the same day). The four classes
   as first built (D-102) are kept in section 3b as the superseded record and nothing in the analysis path calls them.
4. The runs of rule 8.3 on single doses, per form with that form's own classes: as assigned; classes 2 to 4 only,
   each at its dose as assigned; the ten highest-leverage utilities among classes 5 to 8 left out. With each: class
   counts, the share of leverage held by classes 5 to 8 (not settled) and, on its own line, by class 2. The bootstrap
   draws from BOOTSTRAP_SEED, 20261205 (Joe, D-107), unless a test on invented inputs passes its own generator.
5. One whole-inventory history read through build_inventory.state_anchor (doses_from_one_history). The two sensitivity
   scenarios Joe adopted on 2026-11-19 (D-107, R2 of D-106) are built in second_number_scenarios.py through
   pass_c_exact.realise, not through this function, which needs the EPRI totals under data/raw.
6. E3's after-period alternative (2024 to 2025), and the year-by-year side run's wrapper.

Run:  python3 -I pipeline/analysis/second_number.py
Output: data/frozen/second_number_design.json (quantity-only, provisional)
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

from pipeline.analysis import estimator  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
OUT = FROZEN / "second_number_design.json"

KEY = ps.KEY
YEARS = list(range(2001, 2026))
CAPS = ps.CAPS                                  # (None, 25.0, 50.0): the order the simulation draws its weights in
MAIN_CAP = ps.MAIN_CAP                          # 25 points (D-33)
BOOT = ps.BOOT                                  # 999
PRE, POST = ps.LONG_PRE, ps.LONG_POST           # 2008-2010, 2023-2025
E3_POST = (2024, 2025)                          # E3's after-period alternative (D-99)
REGION_YEARS = ps.LONG_REGION_YEARS             # region read in 2009 and in 2024
SIZE_YEAR = ps.LONG_PRE[-1]                     # size band from residential customers in 2010, as the simulation reads it
PANEL_YEARS = ps.PANEL_YEARS                    # 2005-2025, the year-by-year side run
SETTLED_BELOW = 2.0                             # points of load share; a convention chosen before any range was computed (rule 8.2)
LEAVE_OUT = 10                                  # the ten highest-leverage utilities that are not settled (rule 8.3)
INFERENCE_LABEL = ("wild cluster bootstrap as built (by state, unrestricted residuals, Rademacher weights, 999 "
                   "replications, bootstrap-t, equal-tailed; candidate A, estimator.Fit.summary): not calibrated by the "
                   "inference comparison (D-101)")
# The second number's bootstrap seed, adopted by Joe on 2026-11-19 (D-107, from D-106 R9). Used nowhere else: 20261130
# and 20261201 to 20261204 are taken by the inference comparison, E7 and Callaway and Sant'Anna. Every bootstrap in this
# module draws from bootstrap_rng() when no generator is passed.
BOOTSTRAP_SEED = 20261205
# Joe's clarification of 2026-11-19 (D-107) asks for this sentence; the wording is the session's, his to change.
SETTLED_IS_CONDITIONAL = ("\"Settled\" (class 4) is conditional on rule 8.1's modeled histories with dates held at their "
                          "conventions: a settled utility is settled within those histories, and its dose was not tested "
                          "against the admissible range of any site's date (Joe, D-107, 2026-11-19; the wording is the "
                          "session's)")


def bootstrap_rng(seed: int | None = None, *, invented_inputs: bool = False) -> np.random.Generator:
    """The generator the second number's bootstrap draws from: seed BOOTSTRAP_SEED (20261205, Joe, D-107) by default.

    A research run takes no other seed: passing one is refused in words. A test on invented inputs may pass its own by
    saying so (invented_inputs=True). The functions of this module also accept a generator directly, as the tests on
    invented inputs pass one; a run on research data builds its generator here and nowhere else."""
    if seed is None:
        seed = BOOTSTRAP_SEED
    if not isinstance(seed, (int, np.integer)) or isinstance(seed, bool):
        raise TypeError(f"the bootstrap seed is an integer, not {seed!r}")
    if int(seed) != BOOTSTRAP_SEED and not invented_inputs:
        raise ValueError(f"the second number's bootstrap seed is {BOOTSTRAP_SEED}, adopted by Joe on 2026-11-19 (D-107); "
                         f"{seed} is refused for a research run. A test on invented inputs passes invented_inputs=True")
    return np.random.default_rng(int(seed))

# ---- The adopted classification (Joe, 2026-11-19, D-105): eight classes, in the order tested, at each cap separately.
NO_SINGLE_DOSE = "no_single_dose"                                           # 1
NO_ENDPOINT_EXPOSURE = "no_endpoint_exposure_in_modeled_histories"          # 2 (renamed by Joe; not a verified absence of sites)
ZERO_CHANGE_LOAD_IN_REACH = "zero_exposure_change_load_in_reach"            # 3
SETTLED = "settled"                                                         # 4
UNCERTAIN = "uncertain_positive_exposure"                                   # 5
APPARENT_ZERO = "apparent_zero"                                             # 6
POSITIVE_ZERO_SOME = "positive_as_assigned_zero_in_some_history"            # 7
OTHER_NOT_SETTLED = "other_not_settled"                                     # 8
ADOPTED_CLASSES = (NO_SINGLE_DOSE, NO_ENDPOINT_EXPOSURE, ZERO_CHANGE_LOAD_IN_REACH, SETTLED, UNCERTAIN, APPARENT_ZERO,
                   POSITIVE_ZERO_SOME, OTHER_NOT_SETTLED)
CLASS_NUMBER = {c: i + 1 for i, c in enumerate(ADOPTED_CLASSES)}
NOT_SETTLED = (UNCERTAIN, APPARENT_ZERO, POSITIVE_ZERO_SOME, OTHER_NOT_SETTLED)          # classes 5 to 8 (Joe, D-105)
SETTLED_RUN_CLASSES = (NO_ENDPOINT_EXPOSURE, ZERO_CHANGE_LOAD_IN_REACH, SETTLED)         # classes 2 to 4 (rule 8.3)
NOT_A_VERIFIED_ZERO = "not_a_verified_zero"     # the retained flag: class 4, zero as assigned, above zero in some history
RUN_AS_ASSIGNED = "as_assigned"
RUN_SETTLED = "settled_only_classes_2_to_4"
RUN_LEAVE_TEN = "ten_highest_leverage_not_settled_left_out"
RUNS = (RUN_AS_ASSIGNED, RUN_SETTLED, RUN_LEAVE_TEN)
FINDING_NOTE = "docs/gate1/umatilla-common-dose-finding-2026-11-19.md"

# ---- SUPERSEDED RECORD (D-102): the four classes as first built. Kept as the record of what was first built; nothing
# in the analysis path uses these names (the proposal's record, second_number_classes.py, and the as-built tests do).
NO_SITE = "no_site_in_reach"
CLASSES = (SETTLED, UNCERTAIN, APPARENT_ZERO, NO_SITE)
UNCLASSIFIED = "in_none_of_the_four_classes"
NO_RANGE = "no_range_established"

# D-46 ruling 4's cases, each as built and with no anchoring: the history name and assignment.matrices' key.
HISTORIES = {
    "as_assigned_as_built": "as_built", "as_assigned_no_anchoring": "no_anchoring",
    "lower_as_built": "lower_as_built", "lower_no_anchoring": "lower_no_anchoring",
    "upper_as_built": "upper_as_built", "upper_no_anchoring": "upper_no_anchoring",
}
ASSIGNED = "as_assigned_as_built"               # the dose as assigned: the inventory as built (the dose file)


def cap_label(cap) -> str:
    return "uncapped" if cap is None else f"capped_at_{cap:.0f}_points"


# ================================================================================================================
# 1. The frame
# ================================================================================================================

@dataclass
class Frame:
    """One long comparison's sample, in the simulation's order, and who was left out of it and why.

    keys      sample units, (utility_id_eia, state), in the order the simulation's balanced() pivot gives
    years     pre + post, the columns of x and y
    groups    the fixed-effect codings estimator.Fit takes
    cluster   cluster codes per row (state codes for the long comparison)
    band      size band per unit; region_pre / region_post the region codes in the two region years (long form)
    left_out  [{"utility", "why"}] for every candidate unit not in the sample
    """
    name: str
    keys: list
    years: list
    n_pre: int
    groups: list
    cluster: np.ndarray
    band: np.ndarray
    state: np.ndarray
    region_pre: np.ndarray | None = None
    region_post: np.ndarray | None = None
    left_out: list = field(default_factory=list)

    @property
    def cell(self) -> np.ndarray:
        """The long comparison's one fixed-effect coding (region before x region after x band)."""
        return self.groups[0]


def _uid(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def region_codes(regions: pd.DataFrame) -> dict:
    """The simulation's region coding: every region in the frame, sorted (run_second_number)."""
    return {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}


def build_frame(units, q: pd.DataFrame, regions: pd.DataFrame, usable: set, pre=PRE, post=POST, name: str = "long_difference",
                size_year: int = SIZE_YEAR, region_years=REGION_YEARS, codes: dict | None = None) -> Frame:
    """The sample and its fixed effects for the units the caller names, read from quantities and the usable flag only.

    A unit is in the sample if it is usable in every year of `pre + post` (`usable`: the set of (utility, state, year)
    the usable flag passes; a missing unit-year is unusable), has a market region in each of those years and has
    residential customers in `size_year`. The checks, their order and the codings are run_second_number's:
    groups (region in region_years[0] * 1000 + region in region_years[1]) * 10 + size band; clusters by state
    (state codes sorted over the states of `units`, which leaves the clusters' order the same as the simulation's).
    With name="panel", every year of `pre` is a column (pass post=()), the groups are utility effects and region-by-band-
    by-year effects with the region read each year, and the clusters are states repeated over the years.
    """
    years = list(pre) + list(post)
    units = sorted({(int(u), str(s)) for u, s in units})
    codes = region_codes(regions) if codes is None else codes
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    state_code = {st: i for i, st in enumerate(sorted({k[1] for k in units}))}
    left, keep = [], []
    idx = pd.MultiIndex.from_tuples(units, names=KEY) if units else pd.MultiIndex.from_tuples([], names=KEY)
    rt_all = ps.region_matrix(regions, idx, years, codes) if units else np.zeros((0, len(years)))
    for i, k in enumerate(units):
        miss = [y for y in years if (k[0], k[1], y) not in usable]
        if miss:
            left.append({"utility": _uid(k), "why": f"not usable in {', '.join(map(str, miss))} (res_price_usable)"})
            continue
        if np.isnan(rt_all[i]).any():
            left.append({"utility": _uid(k), "why": "no market region in some year of the comparison"})
            continue
        size = cust.loc[k, size_year] if (k in cust.index and size_year in cust.columns) else np.nan
        if not (pd.notna(size) and size > 0):
            left.append({"utility": _uid(k), "why": f"no residential customers in {size_year} (size band undefined)"})
            continue
        keep.append(i)
    keys = [units[i] for i in keep]
    rt = rt_all[keep].astype(int) if keep else np.zeros((0, len(years)), dtype=int)
    size = np.array([cust.loc[k, size_year] for k in keys], dtype=float)
    band = ps.size_band(size) if len(keys) else np.zeros(0, dtype=int)
    state = np.array([state_code[k[1]] for k in keys], dtype=int)
    n, P = len(keys), len(years)
    if name == "long_difference":
        a_pre, a_post = rt[:, years.index(region_years[0])], rt[:, years.index(region_years[1])]
        groups = [(a_pre * 1000 + a_post) * 10 + band]
        return Frame(name, keys, years, len(pre), groups, state, band, state, a_pre, a_post, left)
    tt = np.tile(np.arange(P), n)
    groups = [np.repeat(np.arange(n), P), (rt.ravel() * 10 + np.repeat(band, P)) * P + tt]
    return Frame(name, keys, years, len(pre), groups, np.repeat(state, P), band, state, None, None, left)


def outcome_matrix(outcome: pd.DataFrame, keys: list, years: list, col: str = "log_price") -> np.ndarray:
    """Units by years of the outcome the caller passes (KEY + year + `col`). Every sample unit-year must be there:
    a missing one stops the run in words. Nothing is filled or interpolated."""
    w = outcome[outcome.year.isin(years)].pivot_table(index=KEY, columns="year", values=col)
    w = w.reindex(index=pd.MultiIndex.from_tuples(keys, names=KEY), columns=list(years))
    if w.isna().any().any():
        n = int(w.isna().sum().sum())
        raise ValueError(f"the outcome passed lacks {n} unit-year(s) of the sample; the sample comes from the usable flag, so "
                         "the outcome and the flag disagree. Stopping; nothing is filled")
    return w.values.astype(float)


def dose_points(dose: pd.DataFrame, col: str = "dose") -> pd.DataFrame:
    """Utility-by-year load share in points from a dose frame (KEY + year + col), every year 2001 to 2025, missing as
    zero: run_second_number's D0 before it drops the load-unknown utilities (callers do that themselves)."""
    return dose.pivot_table(index=KEY, columns="year", values=col).reindex(columns=YEARS).fillna(0.0) * 100.0


def dose_matrix(points: pd.DataFrame, keys: list, years: list) -> np.ndarray:
    """Units by years of load share in points for the sample; a unit with no row carries no load (as the simulation)."""
    return points.reindex(pd.MultiIndex.from_tuples(keys, names=KEY)).fillna(0.0)[list(years)].values.astype(float)


def change(x: np.ndarray, n_pre: int, cap=None) -> np.ndarray:
    """The change in dose per unit: the load share, counted at no more than `cap` points in each year, averaged over the
    after years less the same averaged over the before years (rule 8.1's definition). x is units by (pre + post)."""
    xc = x if cap is None else np.minimum(x, cap)
    return xc[:, n_pre:].mean(1) - xc[:, :n_pre].mean(1)


def leverage(dx: np.ndarray, frame: Frame) -> np.ndarray:
    """Each unit's share of the variation in the change in load share left after the fixed effects are removed: the
    computation of inference_check.second_number_leverage (x demeaned within cell, squared, over its sum), done here
    through estimator.Projection so it holds for any coding. Zero variation gives NaN for every unit."""
    xt = estimator.Projection(frame.groups)(np.asarray(dx, dtype=float))
    s = float((xt ** 2).sum())
    return xt ** 2 / s if s > 0 else np.full(len(xt), np.nan)


def fit(frame: Frame, x: np.ndarray, y: np.ndarray, rng: np.random.Generator | None = None, boot: int = BOOT,
        caps=CAPS) -> dict:
    """The second number on one frame: per cap, the slope of the change in log price on the change in load share and its
    range. This is power_simulation._point_chunk's computation for one dataset: per_point_frame, estimator.Fit with the
    frame's groups and clusters, Fit.summary with Rademacher weights drawn from `rng` in the order of `caps` (default
    bootstrap_rng(), seed 20261205). A fit that is rank deficient is a numerical failure, counted and reported with its
    cause, never dropped (D-95 item 7).
    x is units by years of load share in points (uncapped); y is units by years of log price.
    The estimate is in log points per point of load share."""
    if frame.name == "long_difference" and frame.n_pre != len(ps.LONG_PRE):
        raise ValueError("per_point_frame splits the years after the first three; the before period must be 2008 to 2010")
    rng = bootstrap_rng() if rng is None else rng
    out = {}
    for cap in caps:
        xc = x if cap is None else np.minimum(x, cap)
        xf, yf = ps.per_point_frame(frame.name, xc, y)
        try:
            f = estimator.Fit(yf.ravel(), xf.reshape(-1, 1), frame.groups, frame.cluster)
        except estimator.RankDeficient as e:
            out[cap_label(cap)] = ps.failed_reading(estimator.RANK_DEFICIENT, len(np.unique(frame.cluster)), str(e))
            continue
        r = f.summary(estimator.rademacher(rng, boot, f.G), np.ones(1))
        r["inference"] = INFERENCE_LABEL
        out[cap_label(cap)] = r
    return out


def run(frame: Frame, points: pd.DataFrame, outcome: pd.DataFrame, rng: np.random.Generator | None = None,
        boot: int = BOOT, caps=CAPS, outcome_col: str = "log_price") -> dict:
    """The second number on a frame, with the outcome as an argument (KEY + year + log_price), its leverage per unit at
    each cap reported with each estimate (D-41). The bootstrap draws from bootstrap_rng() (seed 20261205) by default."""
    rng = bootstrap_rng() if rng is None else rng
    x = dose_matrix(points, frame.keys, frame.years)
    y = outcome_matrix(outcome, frame.keys, frame.years, outcome_col)
    res = fit(frame, x, y, rng, boot, caps)
    if frame.name == "long_difference":
        for cap in caps:
            res[cap_label(cap)]["leverage"] = dict(zip(map(_uid, frame.keys), leverage(change(x, frame.n_pre, cap), frame).round(8)))
    res["utilities"] = len(frame.keys)
    return res


# ================================================================================================================
# 2. Endpoint doses under uncertain assignment (rule 8.1)
# ================================================================================================================

def case_points(m: dict, base: pd.Series) -> tuple[dict, list]:
    """Load share in points by utility and year in each of the six histories, from assignment.matrices' GWh.

    A utility with load in some history and no positive 2009-2011 sales to divide by has no dose: it is returned in the
    second list, named, and its rows are NaN. A utility with no load anywhere and no base carries zero, as the
    simulation reads it."""
    b = base.reindex(m["as_built"].index)
    pos = (b > 0).values
    no_base = set()
    for key in HISTORIES.values():
        g = m[key]
        no_base |= set(g.index[g.gt(0).any(axis=1).values & ~pos])
    bad = np.array([k in no_base for k in b.index])
    pts = {}
    for h, key in HISTORIES.items():
        g = m[key]
        p = g.div(b.where(b > 0), axis=0) * 100.0
        p[~pos] = 0.0                                     # no base and no load anywhere: carries no load
        p[bad] = np.nan                                   # no base and load somewhere: no dose
        pts[h] = p
    return pts, sorted(no_base)


def history_changes(pts: dict, n_pre: int = len(PRE), years=None, cap=MAIN_CAP) -> pd.DataFrame:
    """Units by histories: the change in dose within each history, the same history at both endpoints."""
    years = list(years or (list(PRE) + list(POST)))
    return pd.DataFrame({h: change(p[years].values, n_pre, cap) for h, p in pts.items()}, index=next(iter(pts.values())).index)


@dataclass
class UnknownLoadRange:
    """A utility a site with no load history reaches: its within-history changes over every admissible history of those
    sites crossed with ruling 4's three cases, as built (factor recomputed) and with no anchoring."""
    utility: str
    changes: dict                           # cap label -> np.ndarray of within-history changes
    histories: int
    established: bool
    why: str = ""
    common_dose: dict | None = None         # SUPERSEDED (D-102): {cap label: dose} only where every cap is common; reported only
    common_by_cap: dict | None = None       # {cap label: the change every history gives, or None}: description, not a finding


def rule4_case_settings(S, k: tuple) -> dict:
    """For utility k, the setting of every assignment question of S in each of ruling 4's cases:
    as assigned (each site where the inventory has it), lower (every unresolved site now on k taken off the panel),
    upper (every unresolved site that lists k among its candidates counted on k). {case: {qid: setting index}}."""
    out = {"as_assigned": {}, "lower": {}, "upper": {}}
    for qid, qq in enumerate(S.qs):
        if qq.name != "assignment":
            continue
        vals = qq.values                                            # [the utility it is on, other candidates..., None]
        on_k = vals[0] == k[0]
        if on_k:
            out["lower"][qid] = vals.index(None)
        elif k[0] in vals:
            out["upper"][qid] = vals.index(k[0])
    return out


def unknown_load_histories(S, k: tuple, base_k: float, fids: list, years=None, n_pre: int = len(PRE),
                           caps=CAPS) -> UnknownLoadRange:
    """Rule 8.1 for a utility a load-unknown site reaches: every setting of those sites' date and capacity questions
    (timing.py's enumeration, `S` its pass_c_exact._State), crossed with ruling 4's three cases, each as built with the
    state's factor recomputed in the configuration (S.grid) and with no anchoring. Every other question stays at the
    reference configuration's setting, as in the inventory. Returns every within-history change per cap."""
    years = list(years or (list(PRE) + list(POST)))
    cols = [YEARS.index(y) for y in years]
    uid = _uid(k)
    if not (pd.notna(base_k) and base_k > 0):
        return UnknownLoadRange(uid, {}, 0, False, "no positive 2009-2011 sales to divide by")
    hist_q = [qid for qid, qq in enumerate(S.qs) if qq.fid in fids and qq.name in ("date", "capacity")]
    if not hist_q:
        return UnknownLoadRange(uid, {}, 0, False, f"none of {fids} has a date or capacity question in this state's enumeration")
    cases = rule4_case_settings(S, k)
    ab_all, na_all = [], []
    for case, fixed in cases.items():
        axes = sorted([(qid, list(range(len(S.qs[qid].values)))) for qid in hist_q] + [(qid, [v]) for qid, v in fixed.items()])
        ab, na, _ = S.grid(k, axes)
        ab_all.append(ab)
        na_all.append(na)
    gwh = np.vstack(ab_all + na_all)
    pts = gwh[:, cols] / base_k * 100.0
    ch = {cap_label(c): change(pts, n_pre, c) for c in caps}
    return UnknownLoadRange(uid, ch, int(len(pts)), True, "", common_dose(ch), common_by_cap(ch))


def common_by_cap(ch: dict) -> dict:
    """{cap label: the change every history gives, or None where they differ}. Exact equality: a narrow range is not a
    common dose (rule 8.3), and no midpoint is taken. For the capped forms this is a description of the histories this
    module enumerates and NOT the finding: Joe (D-105) said whether a common change is established is not to be decided
    "merely by following the current code", so the capped forms take the `established` argument (section 3a)."""
    out = {}
    for lab, v in ch.items():
        v = np.asarray(v, dtype=float)
        out[lab] = float(v[0]) if (len(v) and np.isfinite(v).all() and np.all(v == v[0])) else None
    return out


def common_dose(ch: dict) -> dict | None:
    """SUPERSEDED RECORD (D-102), replaced by Joe's per-form rule (D-105) and used by nothing in the analysis path.
    {cap label: dose} where every history gives exactly the same change at EVERY cap; else None. As first built a
    utility entered a single-dose run only where all three were common."""
    out = common_by_cap(ch)
    return out if all(v is not None for v in out.values()) else None


def oregon_state(fids: list):
    """timing.py's enumeration for the state of the load-unknown sites, built the way timing.load_rebuilt builds it but
    without epoch_gaps.parquet, which this module may not open. Its only use there is the 2024 anchoring of a fixed-history
    row taken out as not a site; frozen_2024_mw is left empty, so such a row stops the run in words
    (pass_c_expand._sites raises) rather than being given a number. Screen shift 0 only (the agent's reading: the
    generic screen is a headline-set rule, not one of the site's admissible histories)."""
    from pipeline.facilities import assignment as asg
    from pipeline.facilities import buildout
    from pipeline.facilities import corrections as cx
    from pipeline.facilities import pass_c_expand as px
    from pipeline.facilities import timing as tm
    fac, fy, q, units, base, regions = asg.load_inputs()
    fac = tm.patch_unknown(fac)
    fy_all = pd.read_parquet(INTERIM / "facility_year.parquet")
    anchor = pd.read_parquet(INTERIM / "state_anchor.parquet").set_index("state")
    phases = buildout.phases_by_site(buildout.load())
    names = q.groupby(asg.KEY).utility_name.last()
    inp = px.Inputs.build(fac, fy, units, base, regions, names, anchor, phases, {}, fy_all)
    states = sorted({str(fac.state[f]) for f in fids})
    entries = tm.timing_entries(cx.load(cx.CORRECTIONS))
    return {st: tm.StateRun(inp, entries, st, screen=(0,)).cases[0]["S"] for st in states}, inp


# ================================================================================================================
# 3. The classes
# ================================================================================================================

# ---- 3a. The adopted classification (Joe, 2026-11-19, D-105) -------------------------------------------------------
#
# Tested in this order, first match wins, every utility in exactly one class AT EACH CAP SEPARATELY ("classify each
# form at its own cap"). For one utility at one cap: d = its single dose at that cap (the change as assigned, or for a
# utility a load-unknown site reaches, an established common change), lo and hi = the smallest and largest change at
# that cap over its modeled histories, reach = data center load above zero in some year of either endpoint period in
# some modeled history.
#   1 no single dose                          a site with no load history reaches it and no common change at that cap is
#                                             established (capped forms: the `established` argument; uncapped: below)
#   2 no endpoint exposure in modeled histories   reach is false (not a verified absence of sites: D-46 ruling 6)
#   3 zero exposure change, load in reach     reach is true and the change at that cap is zero in every history
#   4 settled                                 hi - lo < 2 points; tested BEFORE apparent zero. Where d == 0 and hi > 0 the
#                                             utility keeps the flag NOT_A_VERIFIED_ZERO (retained, reported by name)
#   5 uncertain positive exposure             not settled, lo > 0
#   6 apparent zero                           not settled, d == 0, hi > 0
#   7 positive as assigned, zero in some history   not settled, d > 0, lo <= 0
#   8 other, not settled                      anything left
# "Not settled" in leverage reporting is classes 5 to 8 only; class 2's share of leverage is reported on its own line.
# Zero is exact equality, as the classes were first built.

def reach_from_endpoints(endpoint_points) -> bool:
    """Whether some modeled history carries data center load above zero in some year of either endpoint period.
    endpoint_points: histories by the endpoint years (2008 to 2010 and 2023 to 2025), load share in points, UNCAPPED.
    False is class 2: no endpoint exposure in modeled histories, which is not a verified absence of sites (D-46 ruling
    6: the inventory can be missing sites). The same at every cap, since a share above zero stays above zero under any
    positive cap."""
    e = np.asarray(endpoint_points, dtype=float)
    if e.size == 0 or not np.isfinite(e).all():
        raise ValueError("endpoint load shares must be present and finite to say whether load is in reach")
    return bool((e > 0).any())


def zero_change_kind(endpoint_points, n_pre: int, cap) -> str:
    """For one history whose change at `cap` is zero: why it is zero. endpoint_points: the endpoint years, uncapped."""
    e = np.asarray(endpoint_points, dtype=float)
    if np.all(e == 0):
        return "no_load_at_either_endpoint"
    if cap is not None and np.all(e >= cap):
        return "at_or_above_the_cap_in_every_endpoint_year"
    unc = float(e[n_pre:].mean() - e[:n_pre].mean())
    return "equal_capped_averages_below_the_cap" + ("" if unc == 0 else "_uncapped_change_not_zero")


def adopted_class(dose, changes, reach: bool, why_no_single_dose: str | None = None) -> dict:
    """The adopted classification for ONE utility at ONE cap.

    dose     its single dose at this cap: the change as assigned, or (a utility a load-unknown site reaches) the
             established common change, which stands where "as assigned" is needed (D-105). None: no single dose,
             class 1, and `why_no_single_dose` must say why.
    changes  the change at this cap in every modeled history (rule 8.1)
    reach    reach_from_endpoints over those histories
    Returns {"class", "class_number", "flag", "dose", "lo", "hi", "reach", "why"}. Stops in words on inconsistent inputs;
    nothing is filled or dropped."""
    if dose is None or (isinstance(dose, float) and np.isnan(dose)):
        if not why_no_single_dose:
            raise ValueError("a utility with no single dose is class 1, and why it has none must be stated")
        return {"class": NO_SINGLE_DOSE, "class_number": 1, "flag": None, "dose": None, "lo": None, "hi": None,
                "reach": reach, "why": why_no_single_dose}
    a = float(dose)
    v = np.asarray(changes, dtype=float)
    if not np.isfinite(a):
        raise ValueError("the single dose must be finite")
    if v.size == 0 or not np.isfinite(v).all():
        raise ValueError("a utility with a single dose needs a finite change in every modeled history; none is filled")
    lo, hi = float(v.min()), float(v.max())
    if not (lo <= a <= hi):
        raise ValueError(f"the single dose ({a}) lies outside the range of its modeled histories [{lo}, {hi}]; the history "
                         "that gives it must be one of them. Stopping in words")
    out = {"flag": None, "dose": a, "lo": lo, "hi": hi, "reach": bool(reach), "why": None}
    if not reach:
        if lo != 0 or hi != 0:
            raise ValueError("no endpoint exposure in any modeled history but a change other than zero: the inputs are "
                             "inconsistent")
        cls = NO_ENDPOINT_EXPOSURE
    elif lo == 0 and hi == 0:
        cls = ZERO_CHANGE_LOAD_IN_REACH
    elif hi - lo < SETTLED_BELOW:
        cls = SETTLED
        if a == 0 and hi > 0:
            out["flag"] = NOT_A_VERIFIED_ZERO          # retained: settled takes precedence over apparent zero (D-105)
    elif lo > 0:
        cls = UNCERTAIN
    elif a == 0 and hi > 0:
        cls = APPARENT_ZERO
    elif a > 0 and lo <= 0:
        cls = POSITIVE_ZERO_SOME
    else:
        cls = OTHER_NOT_SETTLED
    return {**out, "class": cls, "class_number": CLASS_NUMBER[cls]}


def zero_common_change_trap(uid: str, lab: str) -> str:
    return (f"{uid} at {lab}: an established common change of exactly zero cannot be classed. Class 2 (no endpoint "
            "exposure in modeled histories) and class 3 (zero exposure change, load in reach) are told apart by the "
            "endpoint loads of each history, and unknown_load_histories does not return endpoint loads. Stopping in "
            "words; neither class is assumed")


def single_dose_without_assignment(uid: str, lab: str, changes, established: dict) -> tuple:
    """For a utility a load-unknown site reaches: its single dose at form `lab`, or None, and why (Joe, D-105).

    Capped forms: the common change is taken from `established` ({uid: {cap label: {"established", "dose", "why"}}}),
    common_dose_rule.established_as_ruled's finding (the wider admissible histories, Joe, D-107); a missing entry reads
    "no finding supplied" and is not established. Nothing here decides it
    from the histories this module enumerates ("Do not decide this merely by following the current code").
    Uncapped form: no exception applies. The agent's reading: his words "for the capped form" leave the uncapped form
    under rule 8.3's sentence as written, so it has a single dose only if its histories here actually give one common
    change (exact equality); an `established` entry for the uncapped form is not read.
    Returns (dose or None, why, source)."""
    v = np.asarray(changes, dtype=float)
    rng = (f"; its change over the admissible histories evaluated runs from {v.min():.6f} to {v.max():.6f} points"
           if v.size and np.isfinite(v).all() else "; no range over its admissible histories was established")
    if lab == cap_label(None):
        c = common_by_cap({lab: v})[lab]
        if c is None:
            return None, ("uncapped form: no common-dose exception applies (the agent's reading of 'for the capped "
                          "form') and its histories give no one common change" + rng), "rule 8.3 as written"
        return c, "uncapped form: every admissible history gives this one change (rule 8.3 as written)", "rule 8.3 as written"
    e = (established.get(uid) or {}).get(lab)
    if e is None:
        return None, "no common-dose finding supplied for this form; the exclusion is retained" + rng, "exclusion retained"
    if not isinstance(e, dict) or not isinstance(e.get("established"), (bool, np.bool_)) or "why" not in e:
        raise ValueError(f"{uid} at {lab}: the common-dose finding must be {{'established': bool, 'dose': float or None, "
                         f"'why': str}}; got {e!r}")
    if not e["established"]:
        return None, "no common change established: " + str(e["why"]) + rng, "exclusion retained"
    d = e.get("dose")
    if d is None or not np.isfinite(float(d)):
        raise ValueError(f"{uid} at {lab}: established is true but no finite dose is given")
    if float(d) == 0.0:
        raise ValueError(zero_common_change_trap(uid, lab))
    return float(d), "common change established: " + str(e["why"]), "common_dose_rule finding"


def classify_by_cap(assigned: dict, changes: dict, reach: dict, no_assigned, established: dict) -> dict:
    """The adopted classification of every utility at every cap.

    assigned     {cap label: {uid: change as assigned}} for every utility with a dose as assigned
    changes      {cap label: {uid: within-history changes}} for every utility; for a utility with no dose as assigned
                 whose range could not be established, an empty array
    reach        {uid: bool} for every utility with a dose as assigned (reach_from_endpoints)
    no_assigned  the utilities a load-unknown site reaches (no dose as assigned)
    established  the common-dose finding, REQUIRED, no default: {} retains the exclusion at every form
    A utility with no dose as assigned that gets a single dose at a form is classed from its histories at that form,
    the common change standing where "as assigned" is needed. Its reach is taken as true: a change other than zero
    needs load in some endpoint year of the histories that give it (the agent's reading). A common change of exactly
    zero stops in words (zero_common_change_trap).
    Returns {cap label: {uid: adopted_class(...) plus "has_assigned_dose" and "dose_source"}}."""
    if not isinstance(established, dict):
        raise TypeError("established must be a mapping ({} for none)")
    no_assigned = list(no_assigned)
    both = set(no_assigned) & set(next(iter(assigned.values()), {}))
    if both:
        raise ValueError(f"utilities both with and without a dose as assigned: {sorted(both)}")
    out = {}
    for lab, chl in changes.items():
        a = assigned.get(lab, {})
        ids = set(a) | set(no_assigned)
        if set(chl) != ids:
            raise ValueError(f"at {lab}: the histories and the utilities do not match ({len(set(chl) ^ ids)} differ)")
        cls = {}
        for u in sorted(ids):
            if u in a:
                if u not in reach:
                    raise ValueError(f"{u}: whether load is in reach was not supplied")
                cls[u] = {**adopted_class(a[u], chl[u], reach[u]), "has_assigned_dose": True, "dose_source": "as assigned"}
            else:
                d, why, src = single_dose_without_assignment(u, lab, chl[u], established)
                if d is None:
                    cls[u] = {**adopted_class(None, chl[u], None, why), "has_assigned_dose": False, "dose_source": src}
                else:
                    r = adopted_class(d, chl[u], True)
                    cls[u] = {**r, "why": why, "has_assigned_dose": False, "dose_source": src}
        out[lab] = cls
    return out


def check_one_class_each(classified: dict, utilities) -> dict:
    """Every utility in exactly one adopted class at every cap. Returns the class counts by cap; stops in words otherwise."""
    want = set(utilities)
    counts = {}
    for lab, cls in classified.items():
        if set(cls) != want:
            raise ValueError(f"at {lab}: {len(want - set(cls))} utilities have no class and {len(set(cls) - want)} are not "
                             "in the sample")
        bad = {u: e.get("class") for u, e in cls.items() if e.get("class") not in ADOPTED_CLASSES}
        if bad:
            raise ValueError(f"at {lab}: classes outside the adopted eight: {bad}")
        counts[lab] = {c: int(sum(e["class"] == c for e in cls.values())) for c in ADOPTED_CLASSES}
        if sum(counts[lab].values()) != len(want):
            raise ValueError(f"at {lab}: the classes do not add up to the sample")
    return counts


def classes_at(classified: dict, lab: str) -> dict:
    return {u: e["class"] for u, e in classified[lab].items()}


def single_doses(classified: dict) -> dict:
    """{cap label: {uid: single dose}} for every utility not in class 1 at that cap."""
    return {lab: {u: e["dose"] for u, e in cls.items() if e["class"] != NO_SINGLE_DOSE} for lab, cls in classified.items()}


# ---- 3b. SUPERSEDED RECORD (D-102): the four classes as first built ------------------------------------------------
# Kept as the record of what was first built. Nothing in the analysis path calls classify or classify_without_assigned:
# the summary, the runs and the registry's inputs take the adopted classification of section 3a.

def classify(assigned: float, changes) -> str:
    """SUPERSEDED RECORD (D-102). Rule 8.2 on the within-history changes in dose, at 25 points only, as first built.

    The order of the tests as first built (the agent's reading at the time, since the plan's four definitions overlap):
    zero in every case; zero as assigned and above zero in some case; differs by less than two points; above zero in
    every case. A range that met none was returned as UNCLASSIFIED."""
    v = np.asarray(changes, dtype=float)
    if v.size == 0 or not np.isfinite(v).all() or not np.isfinite(assigned):
        return NO_RANGE
    if np.all(v == 0):
        return NO_SITE
    if assigned == 0 and np.any(v > 0):
        return APPARENT_ZERO
    if v.max() - v.min() < SETTLED_BELOW:
        return SETTLED
    if np.all(v > 0):
        return UNCERTAIN
    return UNCLASSIFIED


def classify_without_assigned(changes) -> str:
    """SUPERSEDED RECORD (D-102). The as-built classes for a utility with no dose as assigned, classed on its range alone."""
    v = np.asarray(changes, dtype=float)
    if v.size == 0 or not np.isfinite(v).all():
        return NO_RANGE
    if np.all(v == 0):
        return NO_SITE
    if v.max() - v.min() < SETTLED_BELOW:
        return SETTLED
    if np.all(v > 0):
        return UNCERTAIN
    return UNCLASSIFIED


# ================================================================================================================
# 4. The runs on single doses (rule 8.3), per form with that form's classes
# ================================================================================================================

def fit_changes(frame: Frame, dx: dict, dy: np.ndarray, rng: np.random.Generator | None = None, boot: int = BOOT,
                caps=CAPS) -> dict:
    """The long comparison on changes given directly: dx {cap label: change in load share per unit, in frame order},
    dy the change in log price per unit. Used for runs whose units carry a change and no year-by-year dose (a utility
    whose common change is established). The same Fit and the same draws, in the order of `caps`, as fit(); the
    generator defaults to bootstrap_rng() (seed 20261205)."""
    rng = bootstrap_rng() if rng is None else rng
    out = {}
    for cap in caps:
        xf = np.asarray(dx[cap_label(cap)], dtype=float).reshape(-1, 1)
        try:
            f = estimator.Fit(np.asarray(dy, dtype=float).ravel(), xf, frame.groups, frame.cluster)
        except estimator.RankDeficient as e:
            out[cap_label(cap)] = ps.failed_reading(estimator.RANK_DEFICIENT, len(np.unique(frame.cluster)), str(e))
            continue
        r = f.summary(estimator.rademacher(rng, boot, f.G), np.ones(1))
        r["inference"] = INFERENCE_LABEL
        r["leverage"] = dict(zip(map(_uid, frame.keys), leverage(xf.ravel(), frame).round(8)))
        out[cap_label(cap)] = r
    return out


def leave_out_ten(lev: dict, classes_at_cap: dict, n: int = LEAVE_OUT) -> list:
    """The n highest-leverage utilities among classes 5 to 8 (not settled, D-105) at one cap. Ties broken by utility id
    string so the list is fixed. lev: {uid: leverage}; classes_at_cap: {uid: adopted class}."""
    cand = [(u, l) for u, l in lev.items() if classes_at_cap[u] in NOT_SETTLED and np.isfinite(l)]
    return [u for u, _ in sorted(cand, key=lambda t: (-t[1], t[0]))[:n]]


def _positions(frame: Frame) -> dict:
    return {_uid(k): i for i, k in enumerate(frame.keys)}


def run_samples(frame: Frame, classified: dict, n: int = LEAVE_OUT) -> dict:
    """Who is in each run on single doses (rule 8.3), at each form with that form's own classes (adopted by Joe on
    2026-11-19, D-111: "each form's run uses the members its own cap's classes give"). `classified` is
    classify_by_cap's output for every utility in `frame`. Returns {run name: {cap label: {"utilities": [...],
    "left_out_named": {uid: why}, ...}}}.

    as assigned   every utility with a dose as assigned, the same at every form; every utility with none is left out
                  and named, those with an established common change included (they enter the other two runs)
    settled only  classes 2, 3 and 4 at that form, each at its single dose (as assigned, or the established change)
    leave ten out every utility with a single dose at that form less the ten highest-leverage utilities among classes 5
                  to 8 there. The ranking leverage is each utility's leverage at that form among every utility with a
                  single dose at that form, which is the run as assigned when no common change is established (adopted
                  by Joe on 2026-11-19, D-111; as first built the ranking was the run as assigned at 25 points).
    Class 1 at a form is out of every run of that form and named, with its reason."""
    pos = _positions(frame)
    out = {r: {} for r in RUNS}
    for lab, cls in classified.items():
        if set(cls) != set(pos):
            raise ValueError(f"at {lab}: the classes and the frame's utilities differ ({len(set(cls) ^ set(pos))} utilities)")
        order = [_uid(k) for k in frame.keys]
        class1 = {u: cls[u]["why"] for u in order if cls[u]["class"] == NO_SINGLE_DOSE}
        pool = [u for u in order if cls[u]["class"] != NO_SINGLE_DOSE]
        sub = sub_frame(frame, [pos[u] for u in pool])
        lev = dict(zip(pool, leverage(np.array([cls[u]["dose"] for u in pool], dtype=float), sub))) if pool else {}
        ten = leave_out_ten(lev, {u: cls[u]["class"] for u in pool}, n)
        out[RUN_AS_ASSIGNED][lab] = {
            "utilities": [u for u in order if cls[u]["has_assigned_dose"]],
            "left_out_named": {u: ("no assigned dose: a site with no load history reaches it"
                                   + ("" if cls[u]["class"] == NO_SINGLE_DOSE else
                                      f"; its established common change at this form ({cls[u]['dose']}) enters this "
                                      "form's other runs"))
                               for u in order if not cls[u]["has_assigned_dose"]}}
        out[RUN_SETTLED][lab] = {"utilities": [u for u in pool if cls[u]["class"] in SETTLED_RUN_CLASSES],
                                 "left_out_named": class1}
        out[RUN_LEAVE_TEN][lab] = {"utilities": [u for u in pool if u not in set(ten)], "the_ten": ten,
                                   "the_tens_ranking_leverage": {u: round(float(lev[u]), 8) for u in ten},
                                   "left_out_named": class1}
    return out


def run_summary(members: dict, frame: Frame, classified: dict) -> dict:
    """For one run, at each form ({cap label: [uid]}): class counts, how many are not settled (classes 5 to 8), the share
    of leverage held by classes 5 to 8, the share held by class 2 on its own line, and how many settled utilities carry
    the not-a-verified-zero flag. Leverage is computed within the run's own sample at that form, on its single doses."""
    pos = _positions(frame)
    out = {}
    for lab, ids in members.items():
        cls = classified[lab]
        ids = list(ids)
        missing = set(ids) - set(pos)
        if missing:
            raise ValueError(f"{len(missing)} utilities of the run are not in the frame: {sorted(missing)[:5]}")
        c1 = [u for u in ids if cls[u]["class"] == NO_SINGLE_DOSE]
        if c1:
            raise ValueError(f"at {lab}: class 1 utilities have no single dose and cannot be in a run: {c1}")
        sub = sub_frame(frame, sorted(pos[u] for u in ids))
        sids = [_uid(k) for k in sub.keys]
        lev = leverage(np.array([cls[u]["dose"] for u in sids], dtype=float), sub)
        c = np.array([cls[u]["class"] for u in sids], dtype=object)
        ns = np.isin(c, NOT_SETTLED)
        c2 = c == NO_ENDPOINT_EXPOSURE
        ok = bool(np.isfinite(lev).all())
        out[lab] = {"utilities": len(sids),
                    "class_counts": {k: int((c == k).sum()) for k in ADOPTED_CLASSES},
                    "not_settled_utilities_classes_5_to_8": int(ns.sum()),
                    "share_of_leverage_held_by_classes_5_to_8_not_settled": round(float(lev[ns].sum()), 6) if ok else None,
                    "share_of_leverage_held_by_class_2_no_endpoint_exposure": round(float(lev[c2].sum()), 6) if ok else None,
                    "settled_utilities_flagged_not_a_verified_zero": int(sum(cls[u]["flag"] == NOT_A_VERIFIED_ZERO
                                                                             for u in sids))}
    return out


def run_single_dose(members: dict, frame: Frame, classified: dict, outcome: pd.DataFrame,
                    rng: np.random.Generator | None = None, boot: int = BOOT, outcome_col: str = "log_price") -> dict:
    """One of rule 8.3's runs on single doses, with the outcome as an argument: at each form, its estimate and range on
    that form's members (members: {cap label: [uid]}, every form of CAPS), each utility at its single dose, with the
    run summary. The weights are drawn from `rng` (default bootstrap_rng(), seed 20261205) in the order of CAPS, one fit
    per form; where the members are the same at every form this is fit_changes on one frame, and so the same as fit()
    on years."""
    rng = bootstrap_rng() if rng is None else rng
    labs = [cap_label(c) for c in CAPS]
    if set(members) != set(labs):
        raise ValueError(f"a run on single doses is reported at every form ({labs}); got {sorted(members)}")
    summ = run_summary(members, frame, classified)
    pos = _positions(frame)
    out = {}
    for cap in CAPS:
        lab = cap_label(cap)
        sub = sub_frame(frame, sorted(pos[u] for u in members[lab]))
        y = outcome_matrix(outcome, sub.keys, sub.years, outcome_col)
        dy = y[:, sub.n_pre:].mean(1) - y[:, :sub.n_pre].mean(1)
        dx = {lab: np.array([classified[lab][_uid(k)]["dose"] for k in sub.keys], dtype=float)}
        r = fit_changes(sub, dx, dy, rng, boot, caps=(cap,))[lab]
        r.update(summ[lab])
        out[lab] = r
    return out


def sub_frame(frame: Frame, keep: list) -> Frame:
    """The frame restricted to the units at positions `keep` (long comparison only)."""
    if frame.name != "long_difference":
        raise ValueError("sub_frame is for the long comparison")
    keep = list(keep)
    return Frame(frame.name, [frame.keys[i] for i in keep], frame.years, frame.n_pre, [frame.groups[0][keep]],
                 frame.cluster[keep], frame.band[keep], frame.state[keep], frame.region_pre[keep], frame.region_post[keep], [])


# ================================================================================================================
# 5. One whole-inventory history through build_inventory.state_anchor (the sensitivity scenarios are elsewhere)
# ================================================================================================================

MEASURED_BASIS = ("verified_public_figure", "operator_reported_energy")


def doses_from_one_history(inventory: pd.DataFrame, epri_twh: pd.Series, base: pd.Series, epoch_path: dict | None = None,
                           phases: dict | None = None, energy: dict | None = None, gaps: dict | None = None,
                           years=None, n_pre: int = len(PRE), caps=CAPS) -> dict:
    """Every utility's change in dose read from ONE whole-inventory history, every state's factor recomputed from it.

    `inventory` is one facilities frame in which every site has one assignment, date and capacity setting: columns fid,
    src, state, utility_id_eia (NaN for a site on no panel utility), energized_year (NaN for no operation), mw_full_raw
    (the unscaled full load), mw_basis, is_crypto. The factor is build_inventory.state_anchor's, computed exactly as
    build_inventory.main computes it (rows with a year and a load, measured rows left unscaled, the 2024 EPRI total,
    clipped to [0.2, 3.0], 1 where there is nothing to scale); each permit-based row is then scaled by its state's factor,
    its site-years come from build_inventory.site_mw, data center rows (not crypto) on a panel utility are summed to
    utility-year GWh, and the dose is GWh over the 2009-2011 base (`base`, GWh, by (utility_id_eia, state)).

    The caller supplies the history; nothing here defines one. The two sensitivity scenarios Joe adopted on 2026-11-19
    (D-107) are not built through this function, which needs the EPRI totals under data/raw: second_number_scenarios.py
    builds them state by state through pass_c_exact.realise. Returns {"points": utility-by-year load share in points, "factor": the state table,
    "change": {cap label: Series of within-history changes}}."""
    from pipeline.facilities import build_inventory as bi
    years = list(years or (list(PRE) + list(POST)))
    fac = inventory.reset_index(drop=True).copy()
    need = ["fid", "src", "state", "utility_id_eia", "energized_year", "mw_full_raw", "mw_basis", "is_crypto"]
    missing = [c for c in need if c not in fac.columns]
    if missing:
        raise ValueError(f"the history lacks columns {missing}")
    if fac.fid.duplicated().any():
        raise ValueError("a site appears twice in the history: one history gives each site one setting")
    measured = (fac.src == "epoch") | fac.mw_basis.isin(MEASURED_BASIS)
    t = bi.state_anchor(fac.assign(mw_full=fac.mw_full_raw), measured, epri_twh, epoch_path or {}, year=2024,
                        phases=phases, energy=energy, gaps=gaps)
    scale = np.where(measured, 1.0, fac.state.map(t.factor).fillna(1.0).astype(float))
    fac["mw_full"] = fac.mw_full_raw * scale
    on = fac.energized_year.notna() & fac.mw_full.notna() & fac.utility_id_eia.notna() & ~fac.is_crypto.astype(bool)
    rows = []
    for r in fac[on].itertuples():
        for y in YEARS:
            mw = bi.site_mw(r.src, r.fid, r.energized_year, r.mw_full, y, epoch_path or {}, phases, energy, gaps)
            if mw > 0:
                rows.append((int(r.utility_id_eia), r.state, y, mw * 8.76))
    g = pd.DataFrame(rows, columns=KEY + ["year", "gwh"])
    units = base.index
    gwh = (g.groupby(KEY + ["year"]).gwh.sum().unstack("year").reindex(index=units, columns=YEARS).fillna(0.0)
           if len(g) else pd.DataFrame(0.0, index=units, columns=YEARS))
    pts = gwh.div(base.where(base > 0), axis=0) * 100.0
    ch = {cap_label(c): pd.Series(change(pts[years].values, n_pre, c), index=units) for c in caps}
    return {"points": pts, "factor": t, "change": ch}


LIMITATION_CHECK = [
    {"statement": "The only whole-inventory assignment it builds is the inventory as assigned (pipeline/facilities/build_inventory.py).",
     "accurate": True,
     "what_the_code_does": "build_inventory.main builds one facilities frame: one serving utility per site (pick_utilities, "
                           "then overrides and step D's assignment corrections), one date and one capacity per site, one "
                           "state factor per state (state_anchor at 2024). Nothing in it enumerates another assignment. "
                           "pass_c_expand.scratch_state rebuilds a scenario for one state at a time, with assignment held "
                           "at the corrections, so it is not a whole-inventory assignment either."},
    {"statement": "D-46 ruling 4's cases (assignment.py, CASES and matrices) are each utility's own extremes and, by that "
                  "module's own description, cannot all be true at once.",
     "accurate": True,
     "what_the_code_does": "matrices returns utility-by-year GWh for every utility in the lower and upper cases (as built "
                           "and with no anchoring) and for the inventory as built. In the upper matrix an unresolved site is "
                           "added to every candidate at once, and in the lower matrix it is on no one; the module docstring "
                           "says a site that is a candidate for two utilities is counted on each in its own upper case, "
                           "which cannot both be true. The as-built case reads the inventory's factor; no factor is "
                           "recomputed, which is right for a move of assignment alone (the anchoring does not depend on "
                           "who serves a site). It supplies loads by year, so each utility's within-case endpoint doses "
                           "can be read from it; it does not supply a joint inventory."},
    {"statement": "The verification pass's state scenarios all_earliest and all_latest (pass_c_expand.py) are joint within a "
                  "state for date and capacity questions only, hold assignment at the map, and are not ordered by dose.",
     "accurate": True,
     "what_the_code_does": "run_state adds all_earliest ({q: EARLY for every date and capacity question in the state}) and "
                           "all_latest; scratch_state applies them to one state with assignment corrections as given and "
                           "otherwise as mapped. That an earlier start can raise the 2008-2010 endpoint as well as the later "
                           "one follows from the ramp (buildout.ramp_mw is non-increasing in the start year in every year), "
                           "so neither scenario orders a change in dose. Note: run_state runs on the inventory the pass's "
                           "corrections are written against (load_frozen), not on the step D rebuild."},
    {"statement": "The place test's enumeration (pipeline/facilities/timing.py) runs over each utility's dependency "
                  "component and records places and crossings, not endpoint doses.",
     "accurate": "accurate as to what it records, with one qualification",
     "what_the_code_does": "StateRun.evaluate records places, crossings, ranges of crossings and verdicts. The pure function "
                           "it evaluates with, pass_c_exact._State.grid, returns the utility's GWh in every panel year, as "
                           "built (factor recomputed per configuration) and with no anchoring, for every configuration of "
                           "the questions relevant to that utility. So within-history endpoint doses for ONE utility can be "
                           "read from it (this module does so for the two load-unknown utilities), but each configuration is "
                           "of that utility's relevant questions only, every other question at the reference: it is not a "
                           "whole-inventory scenario."},
    {"statement": "The second number's simulation (power_simulation.run_second_number) reads doses as assigned only and leaves "
                  "out every utility a load-unknown site reaches.",
     "accurate": True,
     "what_the_code_does": "run_second_number drops every unit in unknown_load.affected from the comparison pool and from the "
                           "dose frame before building D0 from the dose file (the inventory as assigned), and names them as "
                           "carried to step F."},
]

SENSITIVITY_SCENARIOS = (
    "Joe adopted the two whole-inventory histories of D-106 R2 on 2026-11-19 (D-107), including their early-end settings "
    "for the two sites with no load history, and asked that they be described as sensitivity scenarios, not bounds or "
    "necessarily one-change comparisons with the primary analysis, with the sample differences reported. Scenario A "
    "places every unresolved load-carrying site at its runner-up under the inventory's own placement rule; scenario B "
    "puts each date entry in force that has a convention at the other end of its interval. In both, bi:852-0 starts in "
    "2024, bi:837-0's date and the rest of its capacity are at 2011, and each state's factor is recomputed. Built in "
    "pipeline/analysis/second_number_scenarios.py; the quantity-side summary is data/frozen/second_number_scenarios.json.")


# ================================================================================================================
# 7. The year-by-year side run
# ================================================================================================================

def panel_frame(units, q: pd.DataFrame, regions: pd.DataFrame, usable: set, codes: dict | None = None) -> Frame:
    """The year-by-year side run's sample (2005 to 2025, utility effects and region-by-band-by-year effects with the region
    read each year, size band from 2005 customers): run_second_number's "panel" form."""
    return build_frame(units, q, regions, usable, pre=PANEL_YEARS, post=(), name="panel", size_year=PANEL_YEARS[0], codes=codes)


# ================================================================================================================
# main: the quantity-only design summary
# ================================================================================================================

def _sample_candidates(q: pd.DataFrame, hold: set, affected: set) -> tuple[list, dict]:
    """Every panel unit, less the price hold (on neither side of any design) and the load-unknown units (handled apart)."""
    units = sorted({(int(u), str(s)) for u, s in zip(q.utility_id_eia, q.state)})
    named = {}
    out = []
    for k in units:
        if k in hold:
            named[_uid(k)] = "price hold (price_hold.csv): on neither side of any design"
        elif k in affected:
            named[_uid(k)] = "reached by a site with no load history: no assigned dose (handled under rule 8.1 apart)"
        else:
            out.append(k)
    return out, named


def simulation_access_separation(q: pd.DataFrame, dose: pd.DataFrame, unknown, assigned_keys: list, names) -> dict:
    """Analysis eligibility kept apart from simulation-access eligibility (Joe, D-105). Nothing in this module's sample
    path (build_frame, _sample_candidates, classify_by_cap, run_samples) takes or reads the simulation's access list;
    this function reads it ONLY to count who the simulation's long comparison would not have used, and its result feeds
    no membership. Quantity and access-list files only, at 2%, as power_simulation.main builds that sample:
    design(q, dose, 0.02, history_settled(0.02)) -> restrict_to_access_list -> unknown.gate(0.02)."""
    theta = 0.02
    d = dose.assign(crypto_share=dose.crypto_mw * 8.76 / dose.base_retail_gwh)
    per = d.groupby(KEY).agg(max_dose=("dose", "max"), max_crypto_share=("crypto_share", "max"))
    _tr, clean = ps.design(q, dose, theta, ps.history_settled(theta))
    listed, _off = ps.restrict_to_access_list(clean)
    gated, _ = unknown.gate(listed, theta, "comparison")
    as_set = lambda f: set(zip(f.utility_id_eia.astype(int), f.state))          # noqa: E731
    s_clean, s_listed, s_gated = as_set(clean), as_set(listed), as_set(gated)
    excl = pd.read_csv(ROOT / "pipeline" / "analysis" / "simulation_access_excluded.csv",
                       dtype={"utility_id_eia": int, "state": str})
    reason = {(int(r.utility_id_eia), r.state): r.reason for r in excl.itertuples()}
    zero = [k for k in assigned_keys if not (k in per.index and per.loc[k, "max_dose"] > 0)]
    left = [k for k in zero if k not in s_gated]
    not_eligible = [k for k in left if k not in s_clean]
    off_list = [k for k in left if k in s_clean and k not in s_listed]
    gate_only = [k for k in left if k in s_listed]
    crypto = [k for k in not_eligible if k in per.index and per.loc[k, "max_crypto_share"] >= ps.CRYPTO_LIMIT]
    by_reason = {}
    for k in off_list:
        by_reason.setdefault(reason.get(k, "reason not found in simulation_access_excluded.csv"), []).append(_uid(k))
    in_sample = set(assigned_keys)
    return {
        "statement": ("The simulation's access list (pipeline/analysis/simulation_access_list.*) decides nothing about who is "
                      "in the second number's sample. The sample is every panel unit usable in all six years with a market "
                      "region and a size band, less the price hold (build_frame, _sample_candidates); neither takes the "
                      "access list, and this count is the only place the module reads it. Every unit counted here stays "
                      "in the sample."),
        "how": "power_simulation.design at 2% with history_settled(0.02), restrict_to_access_list, unknown.gate at 2%",
        "zero_dose_as_assigned_means": "no data center load in any year of utility_year_dose.parquet's dose column",
        "zero_dose_units_in_the_sample_not_in_the_simulations_sample": len(left),
        "of_them_not_comparison_eligible_in_design": len(not_eligible),
        "of_those_with_crypto_mining_load_2pct_or_more_of_base": len(crypto),
        "of_them_comparison_eligible_but_off_the_access_list": len(off_list),
        "off_the_access_list_by_reason": {r: len(v) for r, v in sorted(by_reason.items())},
        "of_them_on_the_list_but_out_at_the_load_unknown_gate": len(gate_only),
        "all_stay_in_the_second_numbers_sample": all(k in in_sample for k in left),
        "crypto_units": [{"utility": _uid(k), "name": names.get(k)} for k in crypto],
        "off_list_units_by_reason": {r: [{"utility": u, "name": names.get((int(u.split(":")[0]), u.split(":")[1]))}
                                         for u in sorted(v)] for r, v in sorted(by_reason.items())},
    }


def _named(names, uids, extra=None) -> list:
    return [{"utility": u, "name": names.get((int(u.split(":")[0]), u.split(":")[1])), **((extra or {}).get(u, {}))}
            for u in sorted(uids)]


def design_summary(established: dict, verdicts_by_scope: dict) -> dict:
    """Everything the JSON carries. Reads quantities, the usable flag and the inventory; no price.
    `established`: the common-dose finding for the capped forms, REQUIRED with no default. `verdicts_by_scope`: {scope:
    verdicts} for both scopes, REQUIRED, recorded in the file as given. Joe ruled on 2026-11-19 (D-107) that the
    exception is judged on the wider admissible histories, which contain a counterexample, and that they are not
    narrowed to obtain settled status. So `established` must be common_dose_rule.established_as_ruled(verdicts_by_scope),
    the ruled scope's verdicts, and anything else is refused in words: the summary cannot be built on rule 8.1's own
    histories, nor with the exclusion retained by an empty mapping where the ruled scope would establish a change."""
    if not isinstance(established, dict) or not isinstance(verdicts_by_scope, dict):
        raise TypeError("established must be a mapping ({} for none)")
    from pipeline.analysis import common_dose_rule as cdr
    if established != cdr.established_as_ruled(verdicts_by_scope):
        raise ValueError("the common-dose mapping applied must be common_dose_rule.established_as_ruled(verdicts_by_scope): "
                         + cdr.RULING + ". Another mapping is refused")
    from pipeline.analysis import usable_flag
    from pipeline.electricity import market_region, panel
    from pipeline.facilities import assignment as asg
    q = panel.load_quantities()
    flags = usable_flag.read()
    usable = flags.usable
    regions = market_region.by_unit_year(q)
    codes = region_codes(regions)
    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    unknown = ps.load_unknown_load()
    affected = set(unknown.affected)
    hold = ps.price_hold()
    names = q.groupby(KEY).utility_name.last()
    labs = [cap_label(c) for c in CAPS]
    main_lab = cap_label(MAIN_CAP)

    # ---- rule 8.1's six histories from assignment.matrices, as built
    fac, fy, _q, units, base, regions_fixed = asg.load_inputs()
    _t, m, is_resolved = asg.evaluate(fac, fy, units, base, regions_fixed)
    pts, no_base = case_points(m, base)
    file_pts = dose_points(dose)
    common_idx = file_pts.index.intersection(pts[ASSIGNED].index)
    not_aff = [k for k in common_idx if (int(k[0]), k[1]) not in affected and k not in set(no_base)]
    diff = (pts[ASSIGNED].loc[not_aff] - file_pts.loc[not_aff]).abs().values
    reproduce = {"max_abs_difference_points": float(np.nanmax(diff)) if diff.size else 0.0,
                 "units_compared": len(not_aff),
                 "what": "the as-built case of assignment.matrices over the 2009-2011 base against utility_year_dose.dose, "
                         "in points, every unit with a dose row that no load-unknown site reaches"}

    # ---- the frame: every candidate and every load-unknown unit, by usability, region and size
    cands, named = _sample_candidates(q, hold, affected)
    no_base_ids = {_uid(k) for k in no_base}
    frame = build_frame(cands + sorted(affected), q, regions, usable, codes=codes)
    for k in frame.keys:
        if _uid(k) in no_base_ids:
            frame.left_out.append({"utility": _uid(k), "why": "load in some history and no positive 2009-2011 sales: no dose"})
    frame_left = frame.left_out
    frame = sub_frame(frame, [i for i, k in enumerate(frame.keys) if _uid(k) not in no_base_ids])
    frame.left_out = frame_left
    in_frame = {_uid(k) for k in frame.keys}
    assigned_keys = [k for k in frame.keys if k not in affected]          # units with a dose as assigned
    idx = pd.MultiIndex.from_tuples(assigned_keys, names=KEY)
    ch = {cap_label(c): history_changes({h: p.reindex(idx) for h, p in pts.items()}, cap=c) for c in CAPS}
    endpoint_years = list(PRE) + list(POST)
    ends = {_uid(k): np.vstack([pts[h].loc[k, endpoint_years].values for h in HISTORIES]) for k in assigned_keys}
    reach = {u: reach_from_endpoints(e) for u, e in ends.items()}
    assigned = {lab: {_uid(k): float(ch[lab].loc[k, ASSIGNED]) for k in assigned_keys} for lab in labs}
    changes = {lab: {_uid(k): ch[lab].loc[k].values for k in assigned_keys} for lab in labs}

    # ---- the load-unknown utilities: within-history ranges from timing.py's enumeration of their sites
    unk_rows = {}
    sites = json.loads((FROZEN / ps.UNKNOWN_LOAD_FILE).read_text()).get("sites", [])
    fids = [s["fid"] for s in sites]
    try:
        S_by_state, inp = oregon_state(fids)
        failed = None
    except Exception as e:                             # reported, never papered over
        S_by_state, inp, failed = {}, None, f"{type(e).__name__}: {e}"
    unk_in_frame = []
    for k in sorted(affected):
        uid = _uid(k)
        entry = {"name": names.get(k), "in_the_frame_by_usability_region_and_size": uid in in_frame,
                 "why_not_in_the_frame": next((x["why"] for x in frame.left_out if x["utility"] == uid), None),
                 "left_out_of_the_primary_run": "no assigned dose: a site with no load history reaches it (D-96 item 2, D-99)"}
        r = None
        if failed or k[1] not in S_by_state:
            entry.update(range_established=False, why="no range over its admissible histories was established: "
                                                      + (failed or f"no enumeration for {k[1]}"))
        else:
            r = unknown_load_histories(S_by_state[k[1]], k, float(inp.base.get(k, np.nan)), fids)
            if not r.established:
                entry.update(range_established=False, why="no range over its admissible histories was established: " + r.why)
            else:
                entry.update(range_established=True, histories_evaluated=r.histories,
                             histories_are="every setting of the date and capacity questions of " + ", ".join(fids)
                                           + " in timing.py's enumeration, crossed with ruling 4's three cases, each as "
                                             "built (the state's factor recomputed in the configuration) and with no "
                                             "anchoring",
                             range_of_change_points={lab: [round(float(x.min()), 6), round(float(x.max()), 6)]
                                                     for lab, x in r.changes.items()},
                             one_change_over_the_histories_evaluated_here_by_form=r.common_by_cap,
                             note_on_that_field=("a description of the histories this module enumerates, not the finding: "
                                                 "for the capped forms whether a common change is established comes from "
                                                 "the `established` argument (Joe, D-105: not decided merely by "
                                                 "following the current code)"))
        unk_rows[uid] = entry
        if uid in in_frame:
            unk_in_frame.append(uid)
            for lab in labs:
                changes[lab][uid] = (np.asarray(r.changes[lab], dtype=float) if (r is not None and r.established)
                                     else np.array([]))

    # ---- the adopted classification at each form, every utility in exactly one class at each
    classified = classify_by_cap(assigned, changes, reach, unk_in_frame, established)
    counts = check_one_class_each(classified, in_frame)
    for uid in unk_in_frame:
        unk_rows[uid]["by_form"] = {lab: {"class": classified[lab][uid]["class"], "single_dose": classified[lab][uid]["dose"],
                                          "source": classified[lab][uid]["dose_source"], "why": classified[lab][uid]["why"]}
                                    for lab in labs}
        unk_rows[uid]["established_entry_supplied"] = established.get(uid)

    scopes_differ = {}
    for uid in sorted({u for v in verdicts_by_scope.values() for u in v}):
        labs_ = sorted({lab for v in verdicts_by_scope.values() for lab in v.get(uid, {})})
        d = [lab for lab in labs_ if len({(bool(v.get(uid, {}).get(lab, {}).get("established")), v.get(uid, {}).get(lab, {}).get("dose"))
                                          for v in verdicts_by_scope.values()}) > 1]
        if d:
            scopes_differ[uid] = d

    # ---- the enumeration's reproduction of the as-built case on its own state (a consistency check)
    grid_check = None
    if S_by_state:
        st = next(iter(S_by_state))
        S = S_by_state[st]
        diffs = []
        for k in S.units:
            if k in affected or k not in pts[ASSIGNED].index:
                continue
            ab, _na, _ = S.grid(k, [])
            b = float(inp.base.get(k, np.nan))
            if b > 0:
                diffs.append(float(np.abs(ab[0] / b * 100.0 - pts[ASSIGNED].loc[k].values).max()))
        grid_check = {"state": st, "units": len(diffs), "max_abs_difference_points": max(diffs) if diffs else None,
                      "what": "pass_c_exact._State.grid at the reference configuration (screen shift 0) against the as-built "
                              "case, every unit of the state that no load-unknown site reaches"}

    # ---- the runs on single doses (rule 8.3), per form
    samples = run_samples(frame, classified)
    runs = {}
    for name in RUNS:
        s = samples[name]
        runs[name] = {"by_form": run_summary({lab: s[lab]["utilities"] for lab in labs}, frame, classified),
                      "left_out_named_by_form": {lab: s[lab]["left_out_named"] for lab in labs}}
        if name == RUN_LEAVE_TEN:
            runs[name]["the_ten_by_form"] = {lab: _named(names, s[lab]["the_ten"],
                                                         {u: {"class": classified[lab][u]["class"],
                                                              "ranking_leverage": s[lab]["the_tens_ranking_leverage"][u]}
                                                          for u in s[lab]["the_ten"]}) for lab in labs}
    runs["sensitivity_scenarios"] = {"status": "adopted by Joe on 2026-11-19 (D-107); built and summarized apart",
                                     "what": SENSITIVITY_SCENARIOS}
    member_diff = {}
    for name in (RUN_SETTLED, RUN_LEAVE_TEN):
        sets = {lab: set(samples[name][lab]["utilities"]) for lab in labs}
        union = set().union(*sets.values())
        member_diff[name] = {u: [lab for lab in labs if u in sets[lab]] for u in sorted(union)
                             if not all(u in sets[lab] for lab in labs)}

    # ---- leverage in the run as assigned, per form (D-41), for the per-utility listing
    a_sub = sub_frame(frame, [i for i, k in enumerate(frame.keys) if k not in affected])
    lev = {lab: dict(zip(map(_uid, a_sub.keys), leverage(np.array([assigned[lab][_uid(k)] for k in a_sub.keys]), a_sub)))
           for lab in labs}

    # ---- per utility
    per = []
    for k in assigned_keys:
        uid = _uid(k)
        per.append({"utility": uid, "name": names.get(k),
                    "class_by_form": {lab: classified[lab][uid]["class"] for lab in labs},
                    "flag_by_form": {lab: classified[lab][uid]["flag"] for lab in labs},
                    "load_at_an_endpoint_in_some_modeled_history": reach[uid],
                    "assigned_change_in_dose_points": {lab: round(assigned[lab][uid], 6) for lab in labs},
                    "range_over_histories_points": {lab: [round(float(ch[lab].loc[k].min()), 6), round(float(ch[lab].loc[k].max()), 6)]
                                                    for lab in labs},
                    "leverage_as_assigned": {lab: (None if not np.isfinite(lev[lab][uid]) else round(float(lev[lab][uid]), 8))
                                             for lab in labs}})

    # ---- named lists, per form
    def rng_of(uid, lab):
        e = classified[lab][uid]
        return {"single_dose_points": None if e["dose"] is None else round(e["dose"], 6),
                "range_points": None if e["lo"] is None else [round(e["lo"], 6), round(e["hi"], 6)]}
    named_by_form = {}
    for lab, cap in zip(labs, CAPS):
        cls = classified[lab]
        zc = {}
        for u in in_frame:
            if cls[u]["class"] == ZERO_CHANGE_LOAD_IN_REACH and u in ends:
                kinds = {h: zero_change_kind(ends[u][i], len(PRE), cap) for i, h in enumerate(HISTORIES)}
                zc[u] = {**rng_of(u, lab), "zero_change_kind_by_history": kinds,
                         "largest_endpoint_load_share_points_any_history_uncapped": round(float(ends[u].max()), 3)}
        named_by_form[lab] = {
            "class_1_no_single_dose": _named(names, [u for u in in_frame if cls[u]["class"] == NO_SINGLE_DOSE],
                                             {u: {"why": cls[u]["why"]} for u in in_frame}),
            "class_3_zero_exposure_change_load_in_reach": _named(names, list(zc), zc),
            "class_4_settled_flagged_not_a_verified_zero": _named(
                names, [u for u in in_frame if cls[u]["flag"] == NOT_A_VERIFIED_ZERO], {u: rng_of(u, lab) for u in in_frame}),
        }
    class_differs = {u: {lab: classified[lab][u]["class"] for lab in labs} for u in sorted(in_frame)
                     if len({classified[lab][u]["class"] for lab in labs}) > 1}
    class2_load_between = [_uid(k) for k in assigned_keys if classified[main_lab][_uid(k)]["class"] == NO_ENDPOINT_EXPOSURE
                           and any(float(np.nanmax(p.loc[k].values)) > 0 for p in pts.values())]
    near_zero = sorted({u for lab in labs for u in changes[lab]
                        if np.any((changes[lab][u] != 0) & (np.abs(changes[lab][u]) < 1e-9))})

    # ---- analysis eligibility apart from simulation access
    access = simulation_access_separation(q, dose, unknown, assigned_keys, names)

    # ---- E3: the 2024 to 2025 after period, the same dose definition and classification over the revised years
    e3 = build_frame(cands, q, regions, usable, post=E3_POST, codes=codes)
    e3_left = e3.left_out
    e3 = sub_frame(e3, [i for i, k in enumerate(e3.keys) if _uid(k) not in no_base_ids])
    e3.left_out = e3_left
    a_ids, b_ids = {_uid(k) for k in assigned_keys}, {_uid(k) for k in e3.keys}
    e3_years = list(PRE) + list(E3_POST)
    idx3 = pd.MultiIndex.from_tuples(e3.keys, names=KEY)
    ch3 = {cap_label(c): history_changes({h: p.reindex(idx3) for h, p in pts.items()}, years=e3_years, cap=c) for c in CAPS}
    reach3 = {_uid(k): reach_from_endpoints(np.vstack([pts[h].loc[k, e3_years].values for h in HISTORIES])) for k in e3.keys}
    cls3 = classify_by_cap({lab: {_uid(k): float(ch3[lab].loc[k, ASSIGNED]) for k in e3.keys} for lab in labs},
                           {lab: {_uid(k): ch3[lab].loc[k].values for k in e3.keys} for lab in labs}, reach3, [], {})
    e3_out = {"after_period": list(E3_POST), "years_that_must_be_usable": e3_years, "utilities": len(e3.keys),
              "added_against_the_primary": sorted(b_ids - a_ids), "dropped_against_the_primary": sorted(a_ids - b_ids),
              "added_why": {u: next((x["why"] for x in frame.left_out if x["utility"] == u), "not in the primary frame")
                            for u in sorted(b_ids - a_ids)},
              "class_counts_by_form": check_one_class_each(cls3, b_ids),
              "run_as_assigned_by_form": run_summary({lab: sorted(b_ids) for lab in labs}, e3, cls3),
              "utilities_whose_class_differs_from_the_primary_by_form": {
                  lab: sorted(u for u in a_ids & b_ids if cls3[lab][u]["class"] != classified[lab][u]["class"]) for lab in labs},
              "reach_read_at": "2008-2010 and 2024-2025, its own endpoint years (adopted by Joe on 2026-11-19, D-111)",
              "load_unknown_utilities": "left out, as in the primary run; their ranges over 2024-2025 are not computed here",
              "the_primary_version": "unchanged (after period 2023-2025)"}

    pf = panel_frame(cands, q, regions, usable, codes=codes)
    why_counts = {}
    for x in frame.left_out:
        w = "not usable in some year of 2008-2010 or 2023-2025" if x["why"].startswith("not usable") else x["why"]
        why_counts[w] = why_counts.get(w, 0) + 1
    return {
        "what_this_is": ("Quantity-only and PROVISIONAL: the second number's sample, doses, dose ranges over D-46 ruling 4's "
                         "cases, the classification Joe adopted on 2026-11-19 (D-105) at each of the three forms, and the "
                         "runs of rule 8.3 on the design as it stands on 2026-11-18. The plan is a DRAFT and not frozen. No "
                         "price, revenue or bill was read; usability is the quantities file's res_price_usable flag. No "
                         "estimate is here. The common-dose finding for the capped forms (common_dose_rule.py) is applied "
                         "on the wider admissible histories, as Joe ruled on 2026-11-19 (D-107): they contain a "
                         "counterexample for Umatilla, which stays excluded; both scopes' verdicts are kept on record in "
                         "common_dose_finding. data/frozen/second_number_classification_proposal.json is kept unchanged as "
                         "the record of what was proposed (D-104)."),
        "inference_when_estimated": INFERENCE_LABEL,
        "built_by": "pipeline/analysis/second_number.py",
        "common_dose_finding": {"built_by": "pipeline/analysis/common_dose_rule.py: oregon_verdicts(scope) for each "
                                              "scope, the mapping applied by established_as_ruled (the ruled scope, "
                                              + cdr.RULED_SCOPE + ")",
                                "ruling": cdr.RULING,
                                "ruled_scope": cdr.RULED_SCOPE,
                                "verdicts_by_scope": verdicts_by_scope,
                                "mapping_applied": established,
                                "finding_note": FINDING_NOTE,
                                "forms_where_the_scopes_differ": scopes_differ,
                                "what_the_scopes_found": (("As found, " + ", ".join(
                                    f"{names.get((int(u.split(':')[0]), u.split(':')[1]))} ({u}) at {', '.join(v)}"
                                    for u, v in scopes_differ.items()) + " has a common capped change under rule 8.1's "
                                    "own histories and none under the place test's wider set, where an admissible "
                                    "history is a counterexample (each scope's reason is in verdicts_by_scope). Under "
                                    "Joe's ruling the wider set governs and the exclusion is retained there. Every "
                                    "other form of these utilities has the same verdict under both scopes.")
                                    if scopes_differ else "The scopes agree on every form."),
                                "rule": ("Joe, D-105: a common change in capped dose established from complete admissible "
                                         "histories is applied for that capped form; otherwise exclusion is retained and "
                                         "what remains unestablished is stated. Joe, D-107: the complete admissible "
                                         "histories are the wider set, not narrowed to obtain settled status. The "
                                         "uncapped form takes no exception (the agent's reading of 'for the capped "
                                         "form'): it enters only if its histories here give one common change, and they "
                                         "do not for either utility.")},
        "definitions": {
            "change_in_dose": "the load share in points, counted at no more than the cap in each year, averaged over 2023-2025 "
                              "less the same averaged over 2008-2010 (rule 8.1)",
            "histories": list(HISTORIES),
            "classes_in_order_first_match_wins": [f"{CLASS_NUMBER[c]} {c}" for c in ADOPTED_CLASSES],
            "classified_at": "each form at its own cap: uncapped, capped at 25 points, capped at 50 points (D-105)",
            "class_2": ("no data center load above zero in any year of 2008-2010 or 2023-2025 in any modeled history; what "
                        "it establishes is no endpoint exposure in modeled histories, not a verified absence of sites "
                        "(D-46 ruling 6)"),
            "settled_before_apparent_zero": ("class 4 is tested before class 6; a class 4 utility that is zero as assigned "
                                             "and above zero in some history keeps the flag " + NOT_A_VERIFIED_ZERO),
            "settled_is_conditional": SETTLED_IS_CONDITIONAL,
            "not_settled": "classes 5 to 8 only, for leverage reporting; class 2's share is reported on its own line",
            "two_point_line": "applied at each form to that form's change; a convention chosen before any range was computed",
            "runs": {RUN_AS_ASSIGNED: "every utility with a dose as assigned, the same at every form",
                     RUN_SETTLED: "classes 2, 3 and 4 at that form, each at its dose as assigned",
                     RUN_LEAVE_TEN: ("every utility with a single dose at that form less the ten highest-leverage among "
                                     "classes 5 to 8 at that form, ranked by leverage at that form among every utility with "
                                     "a single dose there (adopted by Joe on 2026-11-19, D-111)"),
                     "per_form_members": "each form's run uses the members its own cap's classes give (adopted by Joe on 2026-11-19, "
                                         "D-111)"},
            "sample": ("every panel unit usable in all six years with a market region in each and residential customers in "
                       "2010, less the price hold. Crypto-mining load and the simulation's access list are not grounds the "
                       "plan gives for leaving a unit out of the second number, and none is applied"),
        },
        "reproduction_checks": {"as_built_case_against_the_dose_file": reproduce, "enumeration_against_the_as_built_case": grid_check},
        "sample": {"utilities_with_an_assigned_dose": len(assigned_keys), "units_in_the_frame": len(frame.keys),
                   "panel_units": int(len(q[KEY].drop_duplicates())),
                   "left_out_before_the_frame": {u: w for u, w in named.items() if not w.startswith("reached by")},
                   "left_out_by_the_frame_counts": why_counts, "left_out_by_the_frame": frame.left_out},
        "analysis_eligibility_apart_from_simulation_access": access,
        "class_counts_by_form": counts,
        "named_by_form": named_by_form,
        "utilities_whose_class_differs_between_forms": class_differs,
        "run_members_that_differ_between_forms": member_diff,
        "class_2_with_load_outside_the_endpoint_years_capped_25": _named(names, class2_load_between),
        "near_zero_changes_not_exactly_zero": {"utilities": near_zero,
                                               "what": "a change in some history above zero and under 1e-9 in absolute value "
                                                       "at some form (a floating-point residue exact equality would not "
                                                       "treat as zero)"},
        "utilities_with_no_assigned_dose": unk_rows,
        "runs": runs,
        "e3_after_period_2024_2025": e3_out,
        "year_by_year_side_run": {"utilities": len(pf.keys), "years": f"{PANEL_YEARS[0]}-{PANEL_YEARS[-1]}",
                                  "size_band_from": f"residential customers in {PANEL_YEARS[0]}"},
        "limitation_check": LIMITATION_CHECK,
        "utilities": per,
    }


def common_dose_finding() -> tuple[dict, dict]:
    """The common-dose finding for the capped forms from quantity files: both scopes' verdicts (common_dose_rule.
    oregon_verdicts), kept on record as what was found, and the mapping applied, which is the ruled scope's
    (established_as_ruled). Joe ruled on 2026-11-19 (D-107) that the exception is judged on the wider admissible
    histories, which contain a counterexample for Umatilla; that is the only scope this path applies."""
    from pipeline.analysis import common_dose_rule as cdr
    by_scope = {scope: cdr.oregon_verdicts(scope) for scope in cdr.SCOPES}
    return cdr.established_as_ruled(by_scope), by_scope


def main() -> int:
    established, by_scope = common_dose_finding()
    doc = design_summary(established, by_scope)
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    s = doc["sample"]
    print(f"utilities with an assigned dose {s['utilities_with_an_assigned_dose']} (frame {s['units_in_the_frame']})")
    for lab, c in doc["class_counts_by_form"].items():
        print(f"  {lab}: {c}")
    for name, r in doc["runs"].items():
        for lab, x in r.get("by_form", {}).items():
            print(f"  {name} {lab}: {x['utilities']} utilities; not settled share {x['share_of_leverage_held_by_classes_5_to_8_not_settled']}; "
                  f"class 2 share {x['share_of_leverage_held_by_class_2_no_endpoint_exposure']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
