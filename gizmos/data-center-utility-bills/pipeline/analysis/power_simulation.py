#!/usr/bin/env python3
"""Power simulation: how wide a range does each design give?

Reads the residential prices of utilities that never host material data center
load, one file per utility, and opens no other price file
(panel.load_outcomes, purpose="power_simulation"). No headline regression.

The standard this run is held to was written and committed before it was run
(docs/DECISIONS.md, D-31). What it simulates is the specification in
PREANALYSIS.md as rewritten to D-26:

  New-host estimate (the main one). Stacked event study, one sub-experiment per
  cohort, six years before first crossing to three after, reference year three
  before, utility effects and market-region-by-year effects, headline the mean
  of event years 2 and 3. Run with three forms of size adjustment so the
  simulation can choose one:
    none             every comparison utility in the host's market region
    size_band        only those in the host's size band (region by band by year)
    nearest_in_size  the MATCH_K comparison utilities in the region closest to
                     the host in residential customers
  Size is residential customers in the cohort's reference year, before entry.

  Per point of load (the second number), on every utility with any load:
    long_difference  change in log price from 2008-2010 to 2023-2025 on the
                     change in load share, within market region and size band
    panel            log price on load share year by year, 2005-2025, utility
                     effects and region-by-band-by-year effects

What one draw does
------------------
Every real host is replaced by a stand-in that never hosted material load. The
stand-in comes from the host's own state when the state has one (same ownership
group if possible), so the stand-ins sit in the same states, in the same
numbers, as the hosts they replace; a state with no eligible utility is given
one substitute state in the same market region for the whole draw. Among the
candidates the stand-in is drawn from the five closest in size. It takes the
host's first-crossing year (or, for the per-point designs, the host's load
history). The stand-ins never hosted anything, so the true effect is zero and
what comes back is the design's noise; planted effects are added only to check
that the estimator returns them.

Intervals and the early-years test come from the procedure the run names (D-59 rule
4.7; step E). By default, C, the selected and validated procedure: the 90% CR2 t range
with Satterthwaite degrees of freedom and the approximate Hotelling test on event years
-6, -5 and -4 (pipeline/analysis/candidates.py). With --procedure=A, the labelled run
"figures for the bootstrap as built": a wild cluster bootstrap by state (bootstrap-t,
unrestricted residuals, Rademacher weights, BOOT replications) and a Wald statistic
with a bootstrap p-value, written to its own file. The second number (per point of
load) keeps the bootstrap as built under either: the comparison did not cover it.

Run:  python3 -I pipeline/analysis/power_simulation.py                    under C
      python3 -I pipeline/analysis/power_simulation.py --procedure=A      labelled, own file

How the figures are read (adopted by the owner on 2026-11-18, Stop 3, after the simulation's results were available;
no additional run was made for them, and no number or computation changed):
  - The reported power at a planted effect is the probability that the 90% range lies entirely above zero under a
    planted positive effect. The result read off it is the "smallest increase detected in the correct direction four
    times in five". The range is the two-sided 90% range as constructed; the power figure is not a separate test.
  - Numerical failures stay in the denominator and count as no detection in the power readings. That is separate
    from the calibration readings, where a failure counts as a miss and as a rejection. The failure count is
    reported, including zero.
  - Full-window usability on the access list is a requirement in addition to the never-host and price-hold
    restrictions and replaces none of them (simulation_access_list.DESCRIPTION).

Not in the simulation, stated in the report: fuel-mix-by-year effects and
degree days (not built); future hosts as a second comparison group; each
sub-experiment uses utilities observed in all ten of its years; every stand-in
is perfectly dated.

Run:  python3 -I pipeline/analysis/power_simulation.py
Output: data/frozen/power_simulation.json
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

# One thread per process: the run of D-38 spreads its draws over worker processes instead.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from pipeline.electricity import market_region, panel  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"

SEED = 20261112
DRAWS = 2000
BOOT = 999
COHORTS = (2011, 2022)
PRE, POST, REF = 6, 3, -3
T = PRE + POST + 1
EVENT_TIMES = [e for e in range(-PRE, POST + 1) if e != REF]
HEADLINE = (2, 3)
EARLY = (-6, -5, -4)                   # the years the combined pre-period test covers
PLANTED = (0.0, 0.02, 0.05)            # share of residential price
REFERENCE_LINE = 0.02                  # about $3 a month; a reference, not a bar (D-26)
CLEAN_BELOW = 0.005                    # comparison utilities: load share under 0.5% throughout
CRYPTO_LIMIT = 0.02
NEAREST = 5                            # stand-in drawn from this many closest in size
POWER_BAR = 0.80
LEVEL = 0.90
PRETEST_FAILS = 0.10                   # a truly flat history should fail the combined test this often
SIZE_BANDS = (10_000, 100_000)         # residential customers: under 10,000; 10,000 to 99,999; 100,000 or more
MATCH_K = 10
SIZE_FORMS = ("none", "size_band", "nearest_in_size")
# Added after the first run (D-32), not part of the rule in D-31: comparison utilities from the host's own state only.
ADDED_FORMS = ("same_state",)
LONG_PRE, LONG_POST = (2008, 2009, 2010), (2023, 2024, 2025)
PANEL_YEARS = tuple(range(2005, 2026))
KEY = ["utility_id_eia", "state"]
REGION_OF_BA = market_region.REGION_OF_BA

# Each event-time dummy, demeaned over the ten years (K x T), and the matrices built from it.
YP = np.full((len(EVENT_TIMES), T), -1.0 / T)
for _k, _e in enumerate(EVENT_TIMES):
    YP[_k, _e + PRE] += 1.0
M = YP @ YP.T
M_INV = np.linalg.inv(M)
W_HEAD = np.array([1.0 / len(HEADLINE) if e in HEADLINE else 0.0 for e in EVENT_TIMES])
PRE_IDX = [EVENT_TIMES.index(e) for e in EARLY]
RAMP = np.array([0.0] * PRE + [min(1.0, (e + 1) / 3) for e in range(POST + 1)])
RAMP_Z = YP @ (RAMP - RAMP.mean())     # what a planted path adds to a unit's projected outcome, per unit of td


def failed(rows: pd.DataFrame, col: str = "numerical_failure") -> pd.Series:
    """True for each dataset whose computation failed (D-95 section 3 item 7). A frame without the column has none."""
    if col not in rows:
        return pd.Series(False, index=rows.index)
    return rows[col].map(lambda c: isinstance(c, str) and bool(c))


def failure_summary(rows: pd.DataFrame, col: str = "numerical_failure") -> dict:
    """Failure counts and causes, reported apart from ordinary misses and rejections (E4.3)."""
    f = failed(rows, col)
    causes = rows.loc[f, col].value_counts().to_dict() if f.any() else {}
    return {"count": int(f.sum()), "of": int(len(rows)), "by_cause": {str(k): int(v) for k, v in causes.items()},
            "how_counted": "kept in the denominator; counted as a miss and as a rejection in calibration rates, and as no "
                           "detection in power rates; nothing dropped or replaced (D-95 section 3 item 7; E4.1)"}


def market_regions(q: pd.DataFrame) -> pd.Series:
    """Market region per utility-state (pipeline/electricity/market_region.py)."""
    return market_region.fixed(q)


def size_band(customers) -> np.ndarray:
    return np.digitize(np.asarray(customers, dtype=float), SIZE_BANDS)


def history_settled(theta: float, frozen: Path | None = None) -> dict:
    """{(utility, state): {"group", "first_crossing"}}: utilities whose first crossing a utility-level history fixes (D-34)."""
    path = (frozen or FROZEN) / "buildout_sensitivity.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text())["thresholds"][f"{theta:.0%}"].get("settled_by_utility_level_history", [])
    return {(int(r["utility"].split(":")[0]), r["utility"].split(":")[1]): r for r in rows}


PRICE_HOLD = Path(__file__).resolve().parent / "price_hold.csv"


def price_hold(path: Path | None = None) -> set:
    """Utilities that were hosts until a verification Joe has not yet confirmed took their sites off them (D-50, D-51).

    They are on neither side of any design, and no price of theirs is read, until he confirms at Gate 1:
    if a verification were reversed, a utility read as a comparison would turn out to have been a host.
    """
    path = path or PRICE_HOLD
    if not path.exists():
        return set()
    h = pd.read_csv(path)
    return set(zip(h.utility_id_eia.astype(int), h.state))


def design(q: pd.DataFrame, dose: pd.DataFrame, theta: float, history: dict | None = None,
           hold: set | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(treated utilities with their cohort, comparison-eligible utilities), from load and sales only.

    `history` is history_settled(): where a utility's own count of its data center load fixes its first
    crossing, that year replaces the inventory's (D-34). Comparison eligibility still rests on the inventory.
    `hold` (default: price_hold()) is left out of the comparison-eligible utilities.
    """
    first = dose[dose.dose >= theta].groupby(KEY).year.min().rename("cohort")
    for k, v in (history or {}).items():
        if v["group"] == "cohort":
            first[k] = int(v["first_crossing"])
        else:                                   # an early host, or outside the cohorts: not a cohort utility
            first = first.drop(k, errors="ignore")
            if v["group"] == "early":
                first[k] = COHORTS[0] - 1
    first = first.rename_axis(KEY).reset_index()
    treated = first[first.cohort.between(*COHORTS)].copy()
    d = dose.assign(crypto_share=dose.crypto_mw * 8.76 / dose.base_retail_gwh)
    worst = d.groupby(KEY).agg(max_dose=("dose", "max"), max_crypto=("crypto_share", "max"),
                               has_base=("base_retail_gwh", lambda x: float(x.notna().any()))).reset_index()
    units = q[KEY].drop_duplicates().merge(worst, on=KEY, how="left")
    # A utility with load on it but no 2009-2011 sales to divide by cannot be shown to be clean.
    clean = units[(units.max_dose.fillna(0) < CLEAN_BELOW) & (units.max_crypto.fillna(0) < CRYPTO_LIMIT)
                  & (units.has_base.fillna(1.0) > 0)]
    held = price_hold() if hold is None else hold
    clean = clean[[(int(u), st) not in held for u, st in zip(clean.utility_id_eia, clean.state)]]
    return treated, clean[KEY]


HEADLINE_SET = "headline_set"                             # D-40 and D-46: the set the headline is estimated on
TEN_YEAR_SET = "headline_set_with_the_ten_year_case"       # the labelled side set: D-20 as first written, ten years earlier included
TEN_YEAR_REASON = "D-20 at ten years earlier only"


def dates_and_histories_reasons(theta: float, frozen: Path | None = None) -> dict:
    """{(utility, state): [reasons]} for utilities set aside on site dates or load histories, from the frozen load-and-sales reports.

    D-20: timing depends on large sites that are still permit-dated, tested at 3, 5 and 10 years earlier. A
    utility that depends only on the ten-year case carries TEN_YEAR_REASON and nothing else from D-20, so the
    headline set (D-40: the three- and five-year cases) can leave it in. D-28: the first crossing or the group
    depends on a load history that could not be verified. D-26: Rappahannock Electric Cooperative, from the 5% run.
    A utility whose first crossing rests on its own count of its load (D-34) depends on neither and is not listed.
    """
    frozen = frozen or FROZEN
    t = f"{theta:.0%}"
    dating = json.loads((frozen / "dating_sensitivity.json").read_text())["thresholds"][t]
    by_years = dating.get("dependent_utilities_by_years_earlier")
    out: dict[str, list[str]] = {}
    if by_years is None:                      # an older report with no breakdown: every dependent utility is D-20's
        for u in dating["dependent_utilities"]:
            out.setdefault(u, []).append("D-20: its timing depends on large sites that are still permit-dated")
    else:
        near = set(by_years["3_years"]) | set(by_years["5_years"])
        for u in sorted(near):
            out.setdefault(u, []).append("D-20: its timing depends on large permit-dated sites started three or five years earlier")
        for u in sorted(set(by_years["10_years"]) - near):
            out.setdefault(u, []).append(TEN_YEAR_REASON)
    path = frozen / "buildout_sensitivity.json"
    if path.exists():
        for u in json.loads(path.read_text())["thresholds"][t]["utilities_still_unsettled"]:
            out.setdefault(u["utility"], []).append("D-28: its place depends on a load history that could not be verified")
    if theta == 0.05:
        out.setdefault("40228:VA", []).append("D-26: its sales base straddles a purchase of territory")
    for (u, st) in history_settled(theta, frozen):
        out.pop(f"{u}:{st}", None)
    return {(int(x.split(":")[0]), x.split(":")[1]): v for x, v in out.items()}


# Lists treatment_bounds.py freezes that record a verdict and set no one aside. A utility a load-unknown site reaches
# whose place the enumeration over that site's histories has decided keeps its place (Joe, D-96: "Derive eligibility
# and reference decisions from the admissible histories"); treatment_bounds' own headline set keeps it, and so must
# this function. Every other list sets its members aside.
LISTS_THAT_SET_NO_ONE_ASIDE = frozenset({"unknown_load_decided_by_the_enumeration"})


def bounds_lists(theta: float, frozen: Path | None = None) -> dict:
    """The lists treatment_bounds.py freezes for this threshold (D-46): who does not keep their place, and who is held."""
    path = (frozen or FROZEN) / "treatment_bounds.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run pipeline/facilities/treatment_bounds.py (the headline set is defined there, D-46)")
    lists = json.loads(path.read_text())["thresholds"][f"{theta:.0%}"].get("lists")
    if lists is None:
        raise KeyError(f"{path} was written before D-46: rerun pipeline/facilities/treatment_bounds.py")
    return {name: {(int(x.split(":")[0]), x.split(":")[1]) for x in xs} for name, xs in lists.items()}


def set_aside(theta: float, frozen: Path | None = None, ten_year_case: bool = False) -> set:
    """Utilities left out of the headline set, as hosts and as comparison utilities (D-40, D-46).

    On site dates and load histories: D-20 tested at three and five years earlier, and D-28
    (`dates_and_histories_reasons`). On the bounds: every utility that does not keep its place between the
    inventory as built and with no anchoring, or under D-44's other tests, and every utility unsettled on
    assignment under D-46's ruling 4 (`bounds_lists`). `ten_year_case=True` adds D-20's ten-years-earlier case, which gives the
    labelled side set; whether that case stays in the rule is Joe's at Gate 1 (D-40's addendum).
    """
    reasons = dates_and_histories_reasons(theta, frozen)
    out = {k for k, why in reasons.items() if ten_year_case or any(not x.startswith(TEN_YEAR_REASON) for x in why)}
    for name, members in bounds_lists(theta, frozen).items():
        if name in LISTS_THAT_SET_NO_ONE_ASIDE:
            continue
        out |= members
    return out


def balanced(frame: pd.DataFrame, col: str, years) -> pd.DataFrame:
    """Utility-by-year matrix of `col` for utilities observed in every one of `years`."""
    w = frame[frame.year.isin(years)].pivot_table(index=KEY, columns="year", values=col)
    w = w.reindex(columns=list(years))
    return w[w.notna().all(axis=1)]


class Stack:
    """A set of never-host utilities with complete data: one cohort's sub-experiment, or a per-point sample.

    `y` is what the design needs per unit (ten years of log price for a cohort);
    `attrs` gives region, ownership and the size measure (residential customers) per unit.
    """

    def __init__(self, cohort: int, y: pd.DataFrame, attrs: pd.DataFrame, unit_code: dict, state_code: dict):
        self.cohort = cohort
        self.keys = list(y.index)
        self.y = y.values
        a = attrs.reindex(y.index)
        self.region = a.region.values
        self.ownership = a.ownership.values
        self.size = np.log(a.res_customers.values.astype(float))
        self.band = size_band(a.res_customers.values)
        self.unit = np.array([unit_code[k] for k in self.keys])            # the same utility has one code in every stack
        self.state_name = np.array([k[1] for k in self.keys])
        self.state = np.array([state_code[k[1]] for k in self.keys])


TIERS = ("own_state_and_ownership", "own_state", "substitute_state_and_ownership", "substitute_state",
         "region_and_ownership", "region_only", "ownership_only")


def pick_stand_ins(real: pd.DataFrame, stacks: dict[int, Stack], n_units: int, rng: np.random.Generator,
                   nearest: int | None = NEAREST) -> tuple[list, dict]:
    """One stand-in per real host, keeping the hosts' state structure.

    Returns [(cohort, row index in that stack, position of the host in `real`)] and a record of how each
    was matched: the tier used and the gap in log size between host and stand-in.
    A host is matched in its own state if the state has a free never-host utility (same
    ownership group first). If not, the host's state is given one substitute state in the
    same market region for the rest of the draw, so hosts that share a state still share one.
    """
    used = np.zeros(n_units, dtype=bool)
    substitute: dict[str, str] = {}
    out, tiers, gaps = [], dict.fromkeys(TIERS, 0), []
    for i in rng.permutation(len(real)):
        r = real.iloc[i]
        s = stacks[int(r.cohort)]
        free = ~used[s.unit]
        own = s.ownership == r.ownership

        def first_nonempty(options):
            for lab, mask in options:
                c = np.flatnonzero(mask & free)
                if len(c):
                    return c, lab
            return np.array([], dtype=int), None

        in_state = s.state_name == r.state
        cand, label = first_nonempty([("own_state_and_ownership", in_state & own), ("own_state", in_state)])
        if not len(cand):
            if r.state not in substitute:
                pool = np.flatnonzero((s.region == r.region) & free & (s.state_name != r.state))
                if len(pool):
                    same_own = pool[s.ownership[pool] == r.ownership]
                    substitute[r.state] = str(rng.choice(np.unique(s.state_name[same_own if len(same_own) else pool])))
            if r.state in substitute:
                in_sub = s.state_name == substitute[r.state]
                cand, label = first_nonempty([("substitute_state_and_ownership", in_sub & own), ("substitute_state", in_sub)])
        if not len(cand):
            cand, label = first_nonempty([("region_and_ownership", (s.region == r.region) & own),
                                          ("region_only", s.region == r.region), ("ownership_only", own)])
        if not len(cand):
            raise RuntimeError(f"no stand-in available for a {r.region} {r.ownership} utility in cohort {r.cohort}")
        near = cand if nearest is None else cand[np.argsort(np.abs(s.size[cand] - r.log_size))[:nearest]]
        j = int(rng.choice(near))
        used[s.unit[j]] = True
        out.append((s.cohort, j, int(i)))
        tiers[label] += 1
        gaps.append(abs(float(s.size[j] - r.log_size)))
    return out, {"tiers": tiers, "size_gaps": gaps}


def build_blocks(stacks: dict[int, Stack], picks: list, form: str, n_units: int,
                 excluded: Callable[[int, int], set[int]] | None = None) -> tuple[list, int]:
    """Comparison sets for one draw. Returns [(cohort, treated rows, comparison rows)] and hosts left without one.

    A stand-in is treated in its own cohort and is nobody's comparison anywhere else.
    `excluded(cohort, host_row)`, optional, gives the rows of that cohort's stack that may not be that host's
    comparisons (D-54, ruling 2; D-58, rule 2.3). In the nearest_in_size form they leave the pool before the
    nearest MATCH_K are taken, so the next nearest enters. The other forms do not use it. None changes nothing.
    """
    if form not in SIZE_FORMS + ADDED_FORMS:
        raise ValueError(f"unknown comparison form: {form}")
    pseudo = np.zeros(n_units, dtype=bool)
    by_cohort: dict[int, list[int]] = {}
    for g, j, _ in picks:
        by_cohort.setdefault(g, []).append(j)
        pseudo[stacks[g].unit[j]] = True
    blocks, dropped = [], 0
    for g, rows in by_cohort.items():
        s = stacks[g]
        rows = np.array(rows)
        ok = ~pseudo[s.unit]
        if form == "nearest_in_size":
            for j in rows:
                comp = np.flatnonzero((s.region == s.region[j]) & ok)
                if excluded is not None:
                    bad = excluded(g, int(j))
                    if bad:
                        comp = comp[~np.isin(comp, np.fromiter(bad, dtype=int))]
                if not len(comp):
                    dropped += 1
                    continue
                comp = comp[np.argsort(np.abs(s.size[comp] - s.size[j]), kind="stable")[:MATCH_K]]
                blocks.append((g, np.array([j]), comp))
            continue
        if form == "none":
            cell = s.region
        elif form == "same_state":
            cell = np.array([f"{r}|{st}" for r, st in zip(s.region, s.state_name)])
        else:
            cell = np.array([f"{r}|{b}" for r, b in zip(s.region, s.band)])
        for c in np.unique(cell[rows]):
            tr = rows[cell[rows] == c]
            comp = np.flatnonzero((cell == c) & ok)
            if not len(comp):
                dropped += len(tr)
                continue
            blocks.append((g, tr, comp))
    return blocks, dropped


def bootstrap_t(a: np.ndarray, share: np.ndarray, factor: float, rng: np.random.Generator | None, boot: int = BOOT,
                v: np.ndarray | None = None) -> np.ndarray:
    """Wild cluster bootstrap-t statistics for one linear combination of coefficients.

    `a[g]` is cluster g's contribution to the estimate's sampling error (its score
    projected on the combination); `share[g]` is the cluster's share of the regressor's
    sum of squares. With Rademacher weights v, a replication's estimate moves by v.a, and
    its cluster scores are v[g]*a[g] - share[g]*(v.a), because refitting takes back each
    cluster's share of the shift. Unrestricted residuals; the statistic is centred on the estimate.
    `v` fixes the weights (replications by clusters), for tests.
    """
    if v is None:
        v = rng.integers(0, 2, size=(boot, len(a))) * 2.0 - 1.0
    shift = v @ a
    scores = v * a - np.outer(shift, share)
    se = np.sqrt(factor * (scores ** 2).sum(1))
    return shift / np.where(se > 0, se, np.nan)


def interval(est: float, se: float, tstar: np.ndarray, level: float = LEVEL) -> tuple[float, float]:
    """The bootstrap-t range. If any replication is not finite the dataset has failed and the range is (NaN, NaN):
    no quantile is taken over the replications that happened to be finite (D-95 section 3 item 7; E4.1)."""
    tstar = np.asarray(tstar, dtype=float)
    if not np.isfinite(tstar).all() or not np.isfinite(se):
        return float("nan"), float("nan")
    lo_q, hi_q = np.quantile(tstar, [(1 - level) / 2, (1 + level) / 2])
    return est - hi_q * se, est - lo_q * se


def closed_form_failure(tstar: np.ndarray, se: float) -> str | None:
    """The cause, for the closed-form designs, when a replication or the standard error is not finite (E4.1, E4.3)."""
    if not (np.isfinite(se) and se > 0):
        return "non_finite_or_zero_standard_error"
    return None if np.isfinite(np.asarray(tstar, dtype=float)).all() else "non_finite_bootstrap_replication"


def estimate(stacks: dict[int, Stack], blocks: list, planted: tuple[float, ...], rng: np.random.Generator,
             boot: int = BOOT) -> list[dict]:
    """Stacked event study on one draw's blocks, once per planted effect (in log points).

    Within a block the outcome is demeaned by utility and by year, which removes utility
    effects and the block's year effects (market region by year, or region by size band by
    year, or a matched set's year effects). The regressors are the host indicator, demeaned
    in the block, times each event-time dummy, so the fit can be done utility by utility.
    A planted path lies in the span of the regressors: it moves the coefficients and leaves
    the residuals, the standard error and the bootstrap alone.
    """
    K = len(EVENT_TIMES)
    zs, tds, cl = [], [], []
    n_rows = 0
    for g, tr, comp in blocks:
        s = stacks[g]
        rows = np.concatenate([tr, comp])
        Y = s.y[rows]
        td = np.zeros(len(rows))
        td[:len(tr)] = 1.0
        td -= td.mean()
        zs.append((Y - Y.mean(0, keepdims=True)) @ YP.T)        # the unit mean drops out: each row of YP sums to zero
        tds.append(td)
        cl.append(s.state[rows])
        n_rows += len(rows) * T
    Z, td, c = np.vstack(zs), np.concatenate(tds), np.concatenate(cl)
    codes = np.unique(c, return_inverse=True)[1]
    G = int(codes.max()) + 1
    C = float(td @ td)
    c_g = np.bincount(codes, weights=td ** 2, minlength=G)
    s1 = np.column_stack([np.bincount(codes, weights=td * Z[:, k], minlength=G) for k in range(K)])   # G x K
    factor = (G / (G - 1)) * ((n_rows - 1) / (n_rows - K))
    beta0 = M_INV @ s1.sum(0) / C
    S = s1 - np.outer(c_g, M @ beta0)                            # cluster scores of X'u, the same for every planted effect
    V = factor * (M_INV @ (S.T @ S) @ M_INV) / C ** 2
    se = float(np.sqrt(W_HEAD @ V @ W_HEAD))
    tstar = bootstrap_t(S @ (M_INV @ W_HEAD) / C, c_g / C, factor, rng, boot)
    failure = closed_form_failure(tstar, se)
    crit = float(stats.t.ppf((1 + LEVEL) / 2, G - 1))
    out = []
    for tau in planted:
        beta = beta0 + tau * (M_INV @ RAMP_Z)
        est = float(W_HEAD @ beta)
        lo, hi = interval(est, se, tstar)
        bp = beta[PRE_IDX]
        wald = float(bp @ np.linalg.solve(V[np.ix_(PRE_IDX, PRE_IDX)], bp))
        out.append({"est": est, "se": se, "lo": lo, "hi": hi, "lo_analytic": est - crit * se, "hi_analytic": est + crit * se,
                    "clusters": G, "pre_wald": wald, "max_abs_early": float(np.abs(bp).max()), "numerical_failure": failure})
    return out


def slope(x: np.ndarray, y: np.ndarray, cell: np.ndarray, state: np.ndarray, rng: np.random.Generator,
          boot: int = BOOT) -> dict:
    """Per-point slope of y on x within cells, clustered by state, with the same bootstrap.

    x and y are units by periods (one period for the long difference). Both are demeaned
    by cell-period and, when there is more than one period, by unit: utility effects and
    cell-by-year effects.
    """
    xt, yt = np.empty(x.shape, dtype=float), np.empty(y.shape, dtype=float)
    for cval in np.unique(cell):
        m = cell == cval
        for src, dst in ((x, xt), (y, yt)):
            b = src[m]
            dst[m] = (b - b.mean(1, keepdims=True) - b.mean(0, keepdims=True) + b.mean()) if b.shape[1] > 1 else b - b.mean(0, keepdims=True)
    sxx = float((xt ** 2).sum())
    beta = float((xt * yt).sum() / sxx)
    u = yt - beta * xt
    codes = np.unique(state, return_inverse=True)[1]
    G = int(codes.max()) + 1
    s_g = np.bincount(codes, weights=(xt * u).sum(1), minlength=G)
    c_g = np.bincount(codes, weights=(xt ** 2).sum(1), minlength=G)
    factor = G / (G - 1)
    se = float(np.sqrt(factor * (s_g ** 2).sum()) / sxx)
    tstar = bootstrap_t(s_g / sxx, c_g / sxx, factor, rng, boot)
    lo, hi = interval(beta, se, tstar)
    return {"est": beta, "se": se, "lo": lo, "hi": hi, "clusters": G, "numerical_failure": closed_form_failure(tstar, se)}


def smallest_detectable(est0: np.ndarray, half: np.ndarray, bar: float = POWER_BAR) -> float:
    """Smallest planted effect whose interval lies entirely above zero in `bar` of the draws (the legacy run of D-38).

    The estimators are linear in the outcome and what is planted lies in the span of the
    regressors, so planting t moves every draw's estimate by exactly t and leaves its
    interval's width alone (the simulation checks this). Detection at t is
    est0 + t - half > 0, where `half` is the distance from the estimate down to the
    interval's lower end, so the answer is a quantile of half - est0.

    A draw with a numerical failure (NaN) stays in the denominator and never detects anything: it is counted as
    +infinity, against the design, not dropped (D-95 item 7).
    """
    need = np.asarray(half, dtype=float) - np.asarray(est0, dtype=float)
    with np.errstate(invalid="ignore"):
        q = float(np.quantile(np.where(np.isfinite(need), need, np.inf), bar))
    return np.inf if np.isnan(q) else q          # interpolating toward a failed draw: the bar is out of reach


def attributes(q: pd.DataFrame, regions: pd.Series) -> pd.DataFrame:
    return q.groupby(KEY).agg(ownership=("ownership", "last")).join(regions)


def summarise(rows: pd.DataFrame, scale: float = 100.0) -> dict:
    """What the zero-effect draws say about a design. `scale` turns the estimate's units into the reported ones."""
    half_lo = (rows.est - rows.lo).values
    pct = lambda x: round(scale * float(x), 3)  # noqa: E731
    return {
        "mean_estimate_nothing_planted": pct(rows.est.mean()),
        "sd_of_estimates": pct(rows.est.std()),
        "mean_standard_error": pct(rows.se.mean()),
        "range_width_mean": pct((rows.hi - rows.lo).mean()),
        "range_width_median": pct((rows.hi - rows.lo).median()),
        "range_half_width_mean": pct((rows.hi - rows.lo).mean() / 2),
        "interval_covers_zero": round(float(((rows.lo <= 0) & (rows.hi >= 0)).mean()), 3),
        "smallest_effect_detected_in_80pct_of_draws": pct(smallest_detectable(rows.est.values, half_lo)),
        "clusters_median": int(rows.clusters.median()),
        "numerical_failures": failure_summary(rows),
        "moments_are_over": ("each mean, standard deviation and median is over the draws whose value for it is not NaN (pandas "
                             "skips NaN and nothing else). A failed draw keeps what it computed: its estimate enters the mean and "
                             "standard deviation of estimates, and its standard error the mean standard error, unless NaN. Its "
                             "range is NaN whenever its bootstrap or its standard error is not finite, and then it is left out "
                             "of the range widths, does not cover zero, and never detects in the smallest effect (D-95 item 7)"),
    }


def run_event_study(theta: float, label: str, treated: pd.DataFrame, clean: pd.DataFrame, q: pd.DataFrame,
                    regions: pd.Series, prices: pd.DataFrame, rng: np.random.Generator, draws: int = DRAWS,
                    forms: tuple[str, ...] = SIZE_FORMS) -> dict:
    attrs = attributes(q, regions)
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    ok = q[q.meets_size_floor & (q.res_mwh > 0)]
    real = []
    for r in treated.itertuples():
        years = range(r.cohort - PRE, r.cohort + POST + 1)
        have = ok[(ok.utility_id_eia == r.utility_id_eia) & (ok.state == r.state) & ok.year.isin(years)]
        k = (r.utility_id_eia, r.state)
        if len(have) == len(years) and k in attrs.index and pd.notna(attrs.loc[k, "region"]):
            real.append({"cohort": r.cohort, "region": attrs.loc[k, "region"], "ownership": attrs.loc[k, "ownership"],
                         "log_size": float(np.log(cust.loc[k, r.cohort + REF])), "state": r.state})
    real = pd.DataFrame(real)

    p = prices.merge(clean, on=KEY).merge(q[KEY + ["year", "meets_size_floor"]], on=KEY + ["year"])
    p = p[p.meets_size_floor & (p.res_price > 0)].assign(log_price=lambda d: np.log(d.res_price))
    unit_code = {k: i for i, k in enumerate(map(tuple, clean.values))}
    state_code = {st: i for i, st in enumerate(sorted(clean.state.unique()))}
    stacks = {}
    for g in sorted(real.cohort.unique()):
        y = balanced(p, "log_price", range(g - PRE, g + POST + 1))
        a = attrs.reindex(y.index).assign(res_customers=cust.reindex(y.index)[g + REF].values)
        keep = (a.region.notna() & (a.res_customers > 0)).values
        stacks[int(g)] = Stack(int(g), y[keep], a[keep], unit_code, state_code)

    logs = tuple(float(np.log1p(t)) for t in PLANTED)
    rows = {f: {t: [] for t in PLANTED} for f in forms}
    tiers, gaps, dropped, comp_gap = dict.fromkeys(TIERS, 0), [], dict.fromkeys(forms, 0), {f: [] for f in forms}
    for _ in range(draws):
        picks, how = pick_stand_ins(real, stacks, len(unit_code), rng)
        for k, v in how["tiers"].items():
            tiers[k] += v
        gaps += how["size_gaps"]
        for form in forms:
            blocks, lost = build_blocks(stacks, picks, form, len(unit_code))
            dropped[form] += lost
            for g, tr, comp in blocks:        # how far the comparison utilities are from their hosts in size
                s = stacks[g]
                comp_gap[form].append(float(np.abs(s.size[comp].mean() - s.size[tr].mean())))
            for t, res in zip(PLANTED, estimate(stacks, blocks, logs, rng)):
                rows[form][t].append(res)

    out = {"hosts_as_built": int(len(treated)), "hosts_in_the_panel_for_their_whole_window": int(len(real)),
           "their_states": int(real.state.nunique()),
           "their_cohorts": {str(k): int(v) for k, v in real.cohort.value_counts().sort_index().items()},
           "their_regions": real.region.value_counts().to_dict(), "their_ownership": real.ownership.value_counts().to_dict(),
           "comparison_utilities_eligible": int(len(clean)),
           "comparison_utilities_per_cohort_observed_all_ten_years": {str(g): len(s.keys) for g, s in stacks.items()},
           "stand_in_match": {k: round(v / (draws * len(real)), 3) for k, v in tiers.items()},
           "stand_in_size_gap_log_points": {"median": round(float(np.median(gaps)), 3), "p90": round(float(np.quantile(gaps, 0.9)), 3)},
           "draws": draws, "bootstrap_replications": BOOT, "size_adjustment": {}}
    for form in forms:
        base = pd.DataFrame(rows[form][0.0])
        d = summarise(base)
        d["hosts_left_without_a_comparison_utility_per_draw"] = round(dropped[form] / draws, 2)
        d["comparison_size_gap_log_points_median"] = round(float(np.median(comp_gap[form])), 3)
        d["analytic_interval_covers_zero"] = round(float(((base.lo_analytic <= 0) & (base.hi_analytic >= 0)).mean()), 3)
        d["upper_end_below_the_2pct_reference_line"] = round(float((base.hi < np.log1p(REFERENCE_LINE)).mean()), 3)
        for t in PLANTED[1:]:
            x = pd.DataFrame(rows[form][t])
            d[f"planted_{t:.0%}"] = {
                "interval_excludes_zero_from_above": round(float((x.lo > 0).mean()), 3),
                "interval_covers_the_planted_effect": round(float(((x.lo <= np.log1p(t)) & (x.hi >= np.log1p(t))).mean()), 3),
                "max_abs_shift_error_vs_zero_draws": float(np.abs((x.est - base.est) - np.log1p(t)).max())}
        crit = float(np.quantile(base.pre_wald, 1 - PRETEST_FAILS))
        d["combined_pre_period_test"] = {
            "statistic": "Wald statistic on event years -6, -5 and -4, state-clustered",
            "value_a_flat_history_exceeds_one_time_in_ten": round(crit, 2),
            "share_failing_at_the_chi_square_10pct_value": round(float((base.pre_wald > stats.chi2.ppf(0.9, len(EARLY))).mean()), 3),
            "old_band_all_three_within_1pct": round(float((base.max_abs_early <= 0.01).mean()), 3)}
        out["size_adjustment"][form] = d
        print(f"  {theta:.0%} {label} [{form}]: {len(real)} hosts, drift {d['mean_estimate_nothing_planted']}%, "
              f"range +/-{d['range_half_width_mean']}%, covers {d['interval_covers_zero']:.0%}, "
              f"smallest detectable {d['smallest_effect_detected_in_80pct_of_draws']}%", flush=True)
    return out


def choose_size_form(result: dict) -> dict:
    """Apply the rule in D-31 to one run's three forms."""
    forms = result["size_adjustment"]
    hosts = result["hosts_in_the_panel_for_their_whole_window"]
    eligible = [f for f in SIZE_FORMS if f != "none"
                and forms[f]["hosts_left_without_a_comparison_utility_per_draw"] <= 0.10 * hosts
                and 0.85 <= forms[f]["interval_covers_zero"] <= 0.95]
    if not eligible:
        return {"chosen": None, "eligible": [],
                "why": "neither size adjustment keeps nine hosts in ten and covers zero in 85% to 95% of draws"}
    drift = {f: abs(forms[f]["mean_estimate_nothing_planted"]) for f in eligible}
    best = min(drift.values())
    close = [f for f in eligible if drift[f] <= best + 0.10]
    chosen = min(close, key=lambda f: forms[f]["range_width_mean"])
    return {"chosen": chosen, "eligible": eligible, "abs_drift_pct": drift,
            "why": "smallest placebo drift among the eligible forms; within a tenth of a point, the narrower range"}


def per_point_frame(name: str, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The regression's x and y for a per-point design, from units-by-years load share and log price."""
    if name == "long_difference":
        n = len(LONG_PRE)
        return (x[:, n:].mean(1, keepdims=True) - x[:, :n].mean(1, keepdims=True),
                y[:, n:].mean(1, keepdims=True) - y[:, :n].mean(1, keepdims=True))
    return x, y


def run_per_point(q: pd.DataFrame, dose: pd.DataFrame, clean: pd.DataFrame, regions: pd.Series, prices: pd.DataFrame,
                  rng: np.random.Generator, draws: int = DRAWS, cap: float | None = None) -> dict:
    """Both per-point-of-load designs, with every material host replaced by a stand-in carrying its load history.

    `cap` (points of load share) counts a utility's load share at no more than that in any year. Added after
    the first run (D-32), because a few utilities whose load is several times their 2009-2011 sales carry
    most of the variation.
    """
    attrs = attributes(q, regions)
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    D = dose.pivot_table(index=KEY, columns="year", values="dose").reindex(columns=range(2001, 2026)).fillna(0.0) * 100.0
    hosts_all = [k for k in D.index if D.loc[k].max() >= CLEAN_BELOW * 100]
    if cap is not None:
        D = D.clip(upper=cap)
    ok = q[q.meets_size_floor & (q.res_mwh > 0)]
    p = prices.merge(clean, on=KEY).merge(q[KEY + ["year", "meets_size_floor"]], on=KEY + ["year"])
    p = p[p.meets_size_floor & (p.res_price > 0)].assign(log_price=lambda d: np.log(d.res_price))
    unit_code = {k: i for i, k in enumerate(map(tuple, clean.values))}
    state_code = {st: i for i, st in enumerate(sorted(clean.state.unique()))}
    hosts_all = [k for k in hosts_all if k in attrs.index and pd.notna(attrs.loc[k, "region"])]
    out = {}
    designs = {"long_difference": (LONG_PRE + LONG_POST, LONG_PRE[-1]), "panel": (PANEL_YEARS, PANEL_YEARS[0])}
    for name, (years, size_year) in designs.items():
        years = list(years)
        y = balanced(p, "log_price", years)
        a = attrs.reindex(y.index).assign(res_customers=cust.reindex(y.index)[size_year].values)
        keep = (a.region.notna() & (a.res_customers > 0)).values
        s = Stack(0, y[keep], a[keep], unit_code, state_code)
        have = ok[ok.year.isin(years)].groupby(KEY).size()
        real = pd.DataFrame([{"cohort": 0, "region": attrs.loc[k, "region"], "ownership": attrs.loc[k, "ownership"],
                              "log_size": float(np.log(cust.loc[k, size_year])), "state": k[1], "key": k}
                             for k in hosts_all if have.get(k, 0) == len(years) and cust.loc[k, size_year] > 0])
        own_dose = D.reindex(pd.MultiIndex.from_tuples(s.keys)).fillna(0.0)[years].values    # the never-hosts' own trace of load
        host_dose = np.vstack([D.loc[k, years].values for k in real.key])
        cell = np.array([f"{r}|{b}" for r, b in zip(s.region, s.band)])
        res, tiers, gaps = [], dict.fromkeys(TIERS, 0), []
        for _ in range(draws):
            picks, how = pick_stand_ins(real, {0: s}, len(unit_code), rng)
            for k, v in how["tiers"].items():
                tiers[k] += v
            gaps += how["size_gaps"]
            x = own_dose.copy()
            for _, j, i in picks:
                x[j] = host_dose[i]
            xf, yf = per_point_frame(name, x, s.y)
            res.append(slope(xf, yf, cell, s.state, rng))
        base = pd.DataFrame(res)
        d = summarise(base, scale=100.0)      # log points per point of load share -> percent of price per point
        hx = per_point_frame(name, host_dose, host_dose)[0]
        dev = np.sort(((hx.max(1) - hx.max(1).mean()) ** 2))[::-1]
        d.update({
            "share_of_load_share_variation_from_the_three_largest_hosts": round(float(dev[:3].sum() / dev.sum()), 3),
            "unit": "percent of residential price per point of load share",
            "utilities_with_material_load_given_a_stand_in": int(len(real)),
            "utilities_in_the_sample": int(len(s.keys)),
            "their_states": int(real.state.nunique()),
            "stand_in_match": {k: round(v / (draws * len(real)), 3) for k, v in tiers.items()},
            "stand_in_size_gap_log_points": {"median": round(float(np.median(gaps)), 3)},
            "load_share_points_of_the_median_host": round(float(np.median(hx.max(1))), 2),
        })
        out[name] = d
        print(f"  per point [{name}]: {len(real)} hosts, drift {d['mean_estimate_nothing_planted']}, "
              f"range +/-{d['range_half_width_mean']} % per point, covers {d['interval_covers_zero']:.0%}", flush=True)
    return out


# ================================================================================================
# The run of D-38: market region read year by year, fuel-mix and degree-day controls, the early
# years tested with a bootstrap p-value, and hosts whose start years are wrong. Everything above
# this line is the closed form the first two runs used (D-22, D-31); it is kept because the tests
# hold the general fit to it where the two must agree.
# ================================================================================================

from pipeline.analysis import estimator  # noqa: E402

SEED_D38 = 20261113
TAUS_PCT = tuple(range(0, 13))                 # planted effects, percent of residential price
LONG_REGION_YEARS = (2009, 2024)               # the years a utility's region is read in for the long comparison
NEVER = 99                                     # a date error meaning the redrawn dates never reach the threshold
CAPS = (None, 25.0, 50.0)                      # load share counted at no more than this many points (None: uncapped)
MAIN_CAP = 25.0
N_CONTROLS = 2                                 # heating and cooling degree days, thousands
COMBO = np.concatenate([W_HEAD, np.zeros(N_CONTROLS)])   # the headline with the degree-day controls only; see headline_combo


def headline_combo(k: int) -> np.ndarray:
    """The headline (mean of event years 2 and 3) as a combination of k regressors whose first columns are the event times.

    The number of control columns is not fixed under the gas-share control (one per calendar year in the stacked
    sample, less the first and any redundant one), so the combination is built from the fit's width.
    """
    if k < len(W_HEAD):
        raise ValueError(f"{k} regressors cannot hold the {len(W_HEAD)} event-time columns")
    return np.concatenate([W_HEAD, np.zeros(k - len(W_HEAD))])


# The fuel-mix control (D-59 item 7, with D-61 section 8). The headline uses the gas share; the other two are the
# labelled sensitivities D-59 keeps ("the categorical specification as it was" and "no fuel-mix control").
GAS_SHARE = "gas_share_by_calendar_year"
CATEGORICAL = "categorical_fuel_mix_group_by_year"
NO_FUEL = "no_fuel_control"
FUEL_CONTROLS = (GAS_SHARE, CATEGORICAL, NO_FUEL)
FIRST_YEAR_LEFT_OUT = ("the first calendar year of the stacked sample (normalization: a utility's share does not change, so "
                       "the year columns sum to what the utility effects remove; D-59 item 7)")
REDUNDANT_LEFT_OUT = ("a linear combination of the fixed effects and the control columns before it in calendar order "
                      "(singular-value ratio under 1e-8), judged with the event-time columns set aside (D-59 item 7; D-61 section 8)")
GAS_ASSUMPTION = ("After the other controls, differences in outcomes are modeled as linear in the state's 2008 to 2010 gas share, "
                  "with a slope free to differ by calendar year. A state's generation mix is a proxy for what a utility is "
                  "exposed to; the adjustment does not establish that it measures any utility's own power supply (D-59 item 7).")


@dataclass(frozen=True)
class Rules:
    """Which comparison and specification rules a run applies.

    From step D the headline rules are the default everywhere (HANDOVER.md, D.2; D-94; D-95): the ownership table
    (D-54 ruling 2; D-58 rules 2.2 and 2.3), full-window eligibility from the quantities file's usable flag (D-58
    rule 6.3 with D-94's source), the support rule (D-54 ruling 2) applied, and the gas-share control (D-59 item 7).
    Every older behaviour is reachable only by naming a labelled variant.

    ownership     "table": no same-parent affiliate, no unit of the host's own utility, no investor-owned candidate
                  without a row for an investor-owned host. "affiliates_readmitted": rule 2.3's sensitivity, same-parent
                  affiliates back, the host's own utility still out. "off": nothing excluded (before step D).
    usable        "flag": the usable flag (usable_flag.read). "positive_sales": the template before step D.
    support       "applied": hosts that do not keep their place under D-54's ruling 2 leave the estimate, named.
                  "reported_only": the rule is reported and moves no one (before step D).
    fuel_control  one of FUEL_CONTROLS.
    unresolved_ownership
                  "kept": an investor-owned host whose ownership is unresolved in a year of its window
                  (ownership.unresolved_ownership_hosts) stays in, named as a stated limitation; its investor-owned
                  matches are not described as shown to be unaffiliated. "hosts_excluded": the step F sensitivity the owner
                  adopted on 2026-11-18 (Stop 3), which drops those hosts and changes nothing else (no rematching to public
                  or cooperative units). Needs the ownership table.
    """
    label: str
    ownership: str = "table"
    usable: str = "flag"
    support: str = "applied"
    fuel_control: str = GAS_SHARE
    unresolved_ownership: str = "kept"

    def __post_init__(self):
        if self.ownership not in ("table", "affiliates_readmitted", "off"):
            raise ValueError(f"unknown ownership rule {self.ownership!r}")
        if self.unresolved_ownership not in ("kept", "hosts_excluded"):
            raise ValueError(f"unknown unresolved_ownership rule {self.unresolved_ownership!r}")
        if self.unresolved_ownership == "hosts_excluded" and self.ownership == "off":
            raise ValueError("excluding hosts with unresolved ownership needs the ownership table (ownership 'table' or "
                             "'affiliates_readmitted')")
        if self.usable not in ("flag", "positive_sales"):
            raise ValueError(f"unknown usable rule {self.usable!r}")
        if self.support not in ("applied", "reported_only"):
            raise ValueError(f"unknown support rule {self.support!r}")
        if self.fuel_control not in FUEL_CONTROLS:
            raise ValueError(f"unknown fuel control {self.fuel_control!r}")


HEADLINE_RULES = Rules("headline")
AFFILIATES_READMITTED = replace(HEADLINE_RULES, label="sensitivity_affiliates_readmitted", ownership="affiliates_readmitted")
CATEGORICAL_FUEL = replace(HEADLINE_RULES, label="sensitivity_categorical_fuel_control", fuel_control=CATEGORICAL)
NO_FUEL_CONTROL = replace(HEADLINE_RULES, label="sensitivity_no_fuel_control", fuel_control=NO_FUEL)
UNRESOLVED_OWNERSHIP_EXCLUDED = replace(HEADLINE_RULES, label="sensitivity_hosts_with_unresolved_ownership_excluded",
                                        unresolved_ownership="hosts_excluded")
AS_BEFORE_STEP_D = Rules("as_built_before_step_d", ownership="off", usable="positive_sales", support="reported_only",
                         fuel_control=CATEGORICAL)
RULE_VARIANTS = {r.label: r for r in (HEADLINE_RULES, AFFILIATES_READMITTED, CATEGORICAL_FUEL, NO_FUEL_CONTROL, AS_BEFORE_STEP_D,
                                       UNRESOLVED_OWNERSHIP_EXCLUDED)}


def rules_from_argv(argv: list[str]) -> Rules:
    """`--rules=<label>` picks a labelled variant; with none the headline rules apply."""
    names = [a.split("=", 1)[1] for a in argv if a.startswith("--rules=")]
    if not names:
        return HEADLINE_RULES
    if names[0] not in RULE_VARIANTS:
        raise SystemExit(f"unknown --rules={names[0]}; the labelled variants are {sorted(RULE_VARIANTS)}")
    return RULE_VARIANTS[names[0]]


# ---- load unknown (D-96) --------------------------------------------------------------------------------------------
# The owner's ruling: "retain both sites and their known attributes, mark their starts unresolved, and assign no single
# load history. This means unknown, not zero or never operating. ... Do not let the incomplete inventory frame silently
# determine comparisons, exposure measures or simulation price access. ... Carry unsettled second-number doses to step F
# with the specified timing cases." The inventory writes the sites and every utility they reach, directly or through the
# state's factor, to UNKNOWN_LOAD_FILE (pipeline/facilities/corrections.py, unknown_load_reach). For a utility on it, the
# frame's load share, dose and comparison eligibility are not admissible readings: its place is taken from the enumeration
# (treatment_bounds.json's list "unknown_load_decided_by_the_enumeration", per threshold), or it is excluded and named.
UNKNOWN_LOAD_FILE = "unknown_load_sites_and_affected_utilities.json"
LOAD_UNKNOWN = "load unknown (D-96): dose not settled, carried to step F"
DECIDED_LIST = "unknown_load_decided_by_the_enumeration"


class UnknownLoadMissing(RuntimeError):
    """A rebuilt inventory without its unknown-load file: the run cannot tell which frame readings are admissible."""


@dataclass(frozen=True)
class UnknownLoad:
    """The utilities a load-unknown site reaches, and, per threshold, those whose place the enumeration decided."""
    affected: frozenset
    decided: dict                  # "2%" / "5%" -> frozenset of (utility_id_eia, state)
    source: str
    sites: int = 0

    @staticmethod
    def none(why: str) -> "UnknownLoad":
        """No unknown-load utility, said in words (a pre-step-D inventory, or invented data in a test)."""
        return UnknownLoad(frozenset(), {}, why, 0)

    def settled(self, key, theta: float) -> bool:
        """True if the frame's place for `key` is admissible at `theta`: not reached, or decided by the enumeration."""
        k = (int(key[0]), str(key[1]))
        return k not in self.affected or k in self.decided.get(f"{theta:.0%}", frozenset())

    def gate(self, frame: pd.DataFrame, theta: float, role: str) -> tuple[pd.DataFrame, list]:
        """Rows of `frame` (utility_id_eia, state, ...) whose place is settled at `theta`, and the others, named."""
        ok = np.array([self.settled(k, theta) for k in zip(frame.utility_id_eia, frame.state)], dtype=bool) if len(frame) else np.zeros(0, bool)
        named = [{"utility": f"{int(u)}:{st}", "role": role, "why": LOAD_UNKNOWN}
                 for u, st in zip(frame.utility_id_eia[~ok], frame.state[~ok])] if len(frame) else []
        return frame[ok], named

    def every(self, frame: pd.DataFrame, role: str) -> tuple[pd.DataFrame, list]:
        """Rows of `frame` not reached at all, and the reached ones named. For doses (the second number): no dose of a
        reached utility is settled, whatever its place, so none is computed."""
        ok = np.array([(int(u), str(st)) not in self.affected for u, st in zip(frame.utility_id_eia, frame.state)], dtype=bool) \
            if len(frame) else np.zeros(0, bool)
        named = [{"utility": f"{int(u)}:{st}", "role": role, "why": LOAD_UNKNOWN}
                 for u, st in zip(frame.utility_id_eia[~ok], frame.state[~ok])] if len(frame) else []
        return frame[ok], named


def rebuilt_inventory(interim: Path | None = None) -> bool:
    """Whether the inventory is the step-D rebuild, by the test treatment_bounds.py uses (facilities carry `date_rule`).
    Reads the file's column names only."""
    import pyarrow.parquet as pq
    path = (interim or INTERIM) / "facilities.parquet"
    if not path.exists():
        raise UnknownLoadMissing(f"{path} is missing: cannot tell whether the inventory is rebuilt, so the unknown-load "
                                 "utilities cannot be established (D-96); stopping")
    return "date_rule" in pq.read_schema(path).names


def _key(x: str) -> tuple:
    u, st = str(x).split(":")
    return (int(u), st)


def load_unknown_load(frozen: Path | None = None, rebuilt: bool | None = None, interim: Path | None = None) -> UnknownLoad:
    """The unknown-load utilities and the enumeration's verdicts on them. Stops in words when it cannot establish them.

    Absent file: on a rebuilt inventory the run stops (UnknownLoadMissing); on an inventory from before step D there are
    no load-unknown rows and the result says so. The verdicts come from treatment_bounds.json only if that report was
    written against the same list of affected utilities; otherwise none is taken and every affected utility is excluded.
    """
    frozen = frozen or FROZEN
    path = frozen / UNKNOWN_LOAD_FILE
    rebuilt = rebuilt_inventory(interim) if rebuilt is None else rebuilt
    if not path.exists():
        if rebuilt:
            raise UnknownLoadMissing(f"{path.name} is missing on a rebuilt inventory: the utilities whose load is unknown (D-96) "
                                     "cannot be told from the frame, so no comparison, dose or price access can be decided; "
                                     "run build_inventory.py with its step-D inputs, then timing.py and treatment_bounds.py")
        return UnknownLoad.none("inventory from before step D: no load-unknown rows, no unknown-load file")
    doc = json.loads(path.read_text())
    every = doc.get("every_affected_utility")
    if not isinstance(every, list) or not all(isinstance(x, str) and x.count(":") == 1 for x in every):
        raise UnknownLoadMissing(f"{path.name} has no well-formed every_affected_utility list ('id:state' strings); stopping")
    affected = frozenset(_key(x) for x in every)
    decided: dict = {}
    tb = frozen / "treatment_bounds.json"
    if tb.exists():
        rep = json.loads(tb.read_text())
        written_against = (rep.get("step_d") or {}).get("unknown_load_affected_utilities")
        if written_against is not None and sorted(written_against) == sorted(every):
            for t, r in rep.get("thresholds", {}).items():
                decided[t] = frozenset(_key(x) for x in r.get("lists", {}).get(DECIDED_LIST, [])) & affected
    return UnknownLoad(affected, decided, str(path), len(doc.get("sites", [])))


def require_unknown_load(unknown_load) -> "UnknownLoad":
    if not isinstance(unknown_load, UnknownLoad):
        raise ValueError("pass unknown_load=load_unknown_load() (D-96): who has a load the frame cannot settle must be known "
                         "before any comparison, dose or price access is decided; UnknownLoad.none(why) says there is none")
    return unknown_load


def load_gas_share(frozen: Path | None = None) -> dict:
    """State -> gas_share_mean: the state's share of net generation from gas, averaged over 2008 to 2010, the number the
    three fuel-mix groups were cut from (D-59 item 7). Fixed; no later year's share is used anywhere. Stops if the
    frozen file lacks a state's share or repeats a state, rather than filling it."""
    f = pd.read_csv((frozen or FROZEN) / "fuel_mix_groups.csv", keep_default_na=False, na_values=[""])
    for c in ("state", "gas_share_mean"):
        if c not in f.columns:
            raise ValueError(f"fuel_mix_groups.csv has no {c} column")
    if not f.state.is_unique or f.gas_share_mean.isna().any():
        raise ValueError("fuel_mix_groups.csv repeats a state or lacks a gas_share_mean; the gas-share control cannot be built")
    return dict(zip(f.state, f.gas_share_mean.astype(float)))


def load_controls(frozen: Path | None = None) -> tuple[dict, pd.DataFrame]:
    """(state -> fuel-mix group code, degree days indexed by state and year in thousands). PREANALYSIS.md, D-29."""
    frozen = frozen or FROZEN
    f = pd.read_csv(frozen / "fuel_mix_groups.csv")
    fuel = dict(zip(f.state, f.fuel_mix_group.map({"low": 0, "mid": 1, "high": 2})))
    d = pd.read_csv(frozen / "degree_days.csv").set_index(["state", "year"])[["hdd", "cdd"]] / 1000.0
    return fuel, d


class Window(Stack):
    """One cohort's sub-experiment with what the full specification needs: each utility's region in each
    window year, its state's fuel-mix group, and its state's degree days by year.

    `region` (inherited) is the region in the cohort's reference year, which is what stand-ins and
    comparison utilities are matched on. `region_t` is the region year by year, as integer codes.
    """

    def __init__(self, cohort, y, attrs, unit_code, state_code, region_t, fuel, hdd, cdd):
        super().__init__(cohort, y, attrs, unit_code, state_code)
        self.region_t, self.fuel, self.hdd, self.cdd = region_t, fuel, hdd, cdd


def region_matrix(regions: pd.DataFrame, index: pd.MultiIndex, years, codes: dict) -> np.ndarray:
    """Units by years matrix of region codes, from market_region.by_unit_year()."""
    w = regions[regions.year.isin(list(years))].pivot_table(index=KEY, columns="year", values="region", aggfunc="first")
    w = w.reindex(index=index, columns=list(years))
    return w.apply(lambda col: col.map(codes)).values


def build_windows(cohorts, p: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict, dd: pd.DataFrame,
                  unit_code: dict, state_code: dict) -> dict[int, Window]:
    """Never-host utilities with a price, a region, a fuel-mix group and degree days in every window year."""
    own = q.groupby(KEY).agg(ownership=("ownership", "last"))
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    codes = {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}
    names = {i: r for r, i in codes.items()}
    out = {}
    for g in cohorts:
        years = list(range(g - PRE, g + POST + 1))
        y = balanced(p, "log_price", years)
        rt = region_matrix(regions, y.index, years, codes)
        states = y.index.get_level_values(1)
        fu = np.array([fuel.get(st, np.nan) for st in states], dtype=float)
        hdd = np.array([[dd.hdd.get((st, yr), np.nan) for yr in years] for st in states])
        cdd = np.array([[dd.cdd.get((st, yr), np.nan) for yr in years] for st in states])
        size = cust.reindex(y.index)[g + REF].values
        keep = (~np.isnan(rt).any(1)) & ~np.isnan(fu) & ~np.isnan(hdd).any(1) & ~np.isnan(cdd).any(1) & (size > 0)
        a = own.reindex(y.index).assign(res_customers=size, region=[names.get(c) if not np.isnan(c) else None for c in rt[:, PRE + REF]])
        out[int(g)] = Window(int(g), y[keep], a[keep], unit_code, state_code, rt[keep].astype(int), fu[keep].astype(int),
                             hdd[keep], cdd[keep])
    return out


def planted_path(tt: np.ndarray, shift: np.ndarray) -> np.ndarray:
    """What a unit effect adds in window year index tt when the true first crossing is `shift` years after the recorded one."""
    e = tt - PRE - shift
    return np.where(e >= 0, np.minimum(1.0, (e + 1) / 3.0), 0.0)


def assemble(windows: dict[int, Window], blocks: list, errors: dict | None = None, controls: bool = True,
             fuel_control: str = GAS_SHARE, gas: dict | None = None) -> dict:
    """Stack one draw's blocks into the arrays the regression takes.

    blocks        [(cohort, treated rows, comparison rows)] from build_blocks
    errors        {(cohort, row): years by which the true first crossing differs from the recorded one}; missing is 0
    controls      False drops every control (the same-state side form)
    fuel_control  GAS_SHARE (the headline, D-59 item 7), CATEGORICAL (cohort-by-fuel-mix-group-by-year effects, the
                  labelled sensitivity) or NO_FUEL
    gas           state -> 2008-2010 gas share (load_gas_share()); required by GAS_SHARE

    Returns y, X (event-time regressors, the two degree-day controls, then the gas-share columns kept), the fixed-effect
    codes (utility; block by region by year; and, for CATEGORICAL only, cohort by fuel-mix group by year), the cluster
    codes, two planted paths (dated exactly; dated with the errors), the column labels, the control columns left out
    with their reasons, and the Projection of the fixed effects when it was built (so the fit can reuse it).

    The gas-share columns (D-59 item 7; D-61 section 8): for each calendar year in the stacked sample, the state's share
    times an indicator for that year, one column per calendar year shared by every cohort and matched set. The first
    calendar year's column is left out. After the fixed effects are removed, the rest are added in calendar order after
    the degree-day columns; a column that is a linear combination of the fixed effects and the control columns before it
    (singular-value ratio under 1e-8) is left out and listed with its year. The event-time columns are set aside for that
    judgment, and no control is ever removed to identify an event-time column: if one is not identified, estimator.Fit
    raises RankDeficient, in words.
    """
    if fuel_control not in FUEL_CONTROLS:
        raise ValueError(f"unknown fuel control {fuel_control!r}; one of {FUEL_CONTROLS}")
    errors = errors or {}
    order = {g: i for i, g in enumerate(sorted(windows))}
    ys, trs, tts, units, cells, fuels, cl, hd, cd, sh, cal, st = [], [], [], [], [], [], [], [], [], [], [], []
    n_units = 0
    for b, (g, tr, comp) in enumerate(blocks):
        s = windows[g]
        rows = np.concatenate([tr, comp])
        n = len(rows)
        tt = np.tile(np.arange(T), n)
        ys.append(s.y[rows].ravel())
        trs.append(np.repeat(np.r_[np.ones(len(tr)), np.zeros(len(comp))], T))
        tts.append(tt)
        units.append(n_units + np.repeat(np.arange(n), T))
        n_units += n
        cells.append((b * 1000 + s.region_t[rows].ravel()) * T + tt)
        fuels.append((order[g] * 3 + np.repeat(s.fuel[rows], T)) * T + tt)
        cl.append(np.repeat(s.state[rows], T))
        hd.append(s.hdd[rows].ravel())
        cd.append(s.cdd[rows].ravel())
        sh.append(np.repeat(np.r_[[errors.get((g, int(j)), 0) for j in tr], np.zeros(len(comp))], T))
        cal.append(g - PRE + tt)
        st.append(np.repeat(s.state_name[rows], T))
    y, tr, tt = np.concatenate(ys), np.concatenate(trs), np.concatenate(tts)
    X = np.column_stack([tr * (tt == e + PRE) for e in EVENT_TIMES])
    columns = [f"event_year_{e}" for e in EVENT_TIMES]
    groups = [np.concatenate(units), np.concatenate(cells)]
    left_out, projection = [], None
    if controls:
        dd = np.column_stack([np.concatenate(hd), np.concatenate(cd)])
        X = np.column_stack([X, dd])
        columns += ["heating_degree_days", "cooling_degree_days"]
        if fuel_control == CATEGORICAL:
            groups.append(np.concatenate(fuels))
        elif fuel_control == GAS_SHARE:
            years = np.concatenate(cal)
            share = gas_share_of_rows(np.concatenate(st), gas)
            calendar = sorted(int(x) for x in np.unique(years))
            left_out.append({"year": calendar[0], "why": FIRST_YEAR_LEFT_OUT})
            cand = np.column_stack([share * (years == yr) for yr in calendar[1:]]) if len(calendar) > 1 else np.zeros((len(y), 0))
            projection = estimator.Projection(groups)
            kept, dropped = screen_controls(dd, cand, projection)
            left_out += [{"year": calendar[1 + j], "why": REDUNDANT_LEFT_OUT} for j in dropped]
            X = np.column_stack([X, cand[:, kept]])
            columns += [f"gas_share_x_{calendar[1 + j]}" for j in kept]
    shift = np.concatenate(sh)
    paths = np.column_stack([tr * planted_path(tt, 0.0), tr * planted_path(tt, shift)])
    return {"y": y, "X": X, "groups": groups, "cluster": np.concatenate(cl), "paths": paths, "columns": columns,
            "fuel_control": fuel_control if controls else "no_controls", "control_columns_left_out": left_out,
            "projection": projection}


def gas_share_of_rows(states: np.ndarray, gas: dict | None) -> np.ndarray:
    """Each row's state's 2008-2010 gas share. Stops, naming the states, if any has none: nothing is filled."""
    if gas is None:
        raise ValueError("the gas-share control (D-59 item 7) needs each state's 2008-2010 share: pass gas=load_gas_share(), "
                         "or name a labelled variant (fuel_control=CATEGORICAL or NO_FUEL)")
    missing = sorted({str(x) for x in np.unique(states) if x not in gas or not np.isfinite(gas[x])})
    if missing:
        raise ValueError(f"no 2008-2010 gas share for states {missing}; the gas-share control cannot be built")
    return np.array([float(gas[x]) for x in states])


def screen_controls(fixed: np.ndarray, candidates: np.ndarray, projection, tol: float = estimator.RANK_TOLERANCE) -> tuple[list, list]:
    """Which candidate control columns to keep, in order, after the fixed effects are removed (D-59 item 7; D-61 section 8).

    fixed        controls that are never left out here (the two degree-day columns), considered first
    candidates   the gas-share columns in calendar order
    A candidate is left out if, after the fixed effects are removed, it is absorbed (what is left is no more than `tol`
    times the column before removal) or the smallest singular value of it with the informative control columns before
    it is no more than `tol` times the largest. The event-time columns take no part. A fixed column that fails the test
    is kept in the regression (so the fit's own rank check fails in words) but is not used to judge later candidates.
    Returns (indices of candidates kept, indices left out).
    """
    raw = np.column_stack([fixed, candidates]) if candidates.size else np.asarray(fixed, dtype=float)
    t = projection(raw)
    nf = fixed.shape[1]
    basis, kept, dropped = [], [], []
    for j in range(raw.shape[1]):
        before, after = float(np.linalg.norm(raw[:, j])), float(np.linalg.norm(t[:, j]))
        redundant = before == 0.0 or after <= tol * before
        if not redundant:
            sv = np.linalg.svd(t[:, basis + [j]], compute_uv=False)
            redundant = bool(sv[-1] <= tol * sv[0])
        if not redundant:
            basis.append(j)
        if j >= nf:
            (dropped if redundant else kept).append(j - nf)
    return kept, dropped


def detectable(rate_by_tau: np.ndarray, taus=TAUS_PCT, bar: float = POWER_BAR):
    """Smallest planted effect (percent) whose 90% range lies entirely above zero in `bar` of the draws, read off the grid:
    the "smallest increase detected in the correct direction four times in five" (owner's wording, 2026-11-18)."""
    r = np.asarray(rate_by_tau, dtype=float)
    hit = np.flatnonzero(r >= bar)
    if not len(hit):
        return None
    i = int(hit[0])
    if i == 0:
        return float(taus[0])
    return round(float(taus[i - 1] + (bar - r[i - 1]) / (r[i] - r[i - 1]) * (taus[i] - taus[i - 1])), 2)


def failed_reading(cause: str, clusters: int, detail: str = "") -> dict:
    """What a dataset whose fit could not be computed contributes: NaN everywhere, the cause, kept (D-95 item 7)."""
    nan = float("nan")
    return {"est": nan, "se": nan, "lo": nan, "hi": nan, "clusters": int(clusters), "pre_wald": nan, "pre_p_bootstrap": nan,
            "max_abs_early": nan, "lo_analytic": nan, "hi_analytic": nan, "numerical_failure": cause, "analytic_failure": cause,
            "failure_detail": detail}


# ---- the inference procedure (step E; docs/DECISIONS.md D-59 rule 4.7) ----------------------------------------------
# "The procedure is selected and validated before the power and range-width simulation whose figures will be quoted. A
# simulation run earlier is labelled as figures for the bootstrap as built." Step E selected and validated candidate C
# (CR2 with the Satterthwaite t range for the headline, the approximate Hotelling test for the early years;
# pipeline/analysis/candidates.py). From now on the simulation runs under C by default; "A" (the wild cluster bootstrap as
# built, estimator.Fit.summary) is a labelled run written to its own file, never over the headline file.
SELECTED, AS_BUILT = "C", "A"
PROCEDURES = (SELECTED, AS_BUILT)
AS_BUILT_LABEL = "figures for the bootstrap as built"
AS_BUILT_SUFFIX = "_figures_for_the_bootstrap_as_built"
STAGE1_FILE, STAGE2_FILE = "inference_comparison_stage1.json", "inference_validation_stage2.json"
SMALLEST_INCREASE_KEY = "smallest_increase_detected_in_the_correct_direction_four_times_in_five"
POWER_BY_TAU_KEY = "range_entirely_above_zero_by_planted_pct"
POWER = {
    "name": "smallest increase detected in the correct direction four times in five",
    "definition": ("power at a planted effect is the probability that the 90% range lies entirely above zero under a planted "
                   "positive effect; the smallest increase is the smallest planted effect on the grid (percent of residential "
                   "price, interpolated) at which that probability reaches 80%. The 90% range is the two-sided range as "
                   "constructed; the power figure is not a separate test"),
    "numerical_failures": ("a draw with a numerical failure stays in the denominator and counts as no detection for power. "
                           "This is separate from the calibration readings (the range with nothing planted and the early-years "
                           "test), where a failure counts as a miss and as a rejection. The failure count is reported, including "
                           "zero"),
    "adopted": "readings adopted by the owner on 2026-11-18 (Stop 3), after the simulation's results were available",
}
READINGS_ADOPTED = ("The power wording, the treatment of numerical failures in power readings, and the access list's full-window "
                    "requirement as an addition to the never-host and price-hold restrictions were adopted by the owner on "
                    "2026-11-18 (Stop 3), after the simulation's results were available. No additional run was made for them.")
SECOND_NUMBER_INFERENCE = ("not under the selected procedure: the comparison did not cover this estimator. Its range is the "
                           "wild cluster bootstrap by state as built (estimator.Fit.summary: bootstrap-t, unrestricted "
                           "residuals, Rademacher), on the per-point slope")
PROCEDURE_TEXT = {
    SELECTED: {"range": "90% CR2 t range with Satterthwaite degrees of freedom (Pustejovsky and Tipton 2018, arXiv v2 Eq. 4, 7, 8, 11)",
               "early_years_test": "approximate Hotelling test on event years -6, -5 and -4 with CR2 (Eq. 10, 12, 13), failing at p below 0.10",
               "told_from_zero": "the 90% CR2 t range lies entirely above zero"},
    AS_BUILT: {"range": "90% wild cluster bootstrap-t range by state (unrestricted residuals, Rademacher, 999 replications)",
               "early_years_test": "Wald statistic on event years -6, -5 and -4 with a wild cluster bootstrap p-value, failing at p below 0.10",
               "told_from_zero": "the 90% bootstrap-t range lies entirely above zero"},
}


def procedure_from_argv(argv: list[str]) -> str:
    """`--procedure=A` names the labelled run of the bootstrap as built; with none the selected procedure (C) applies."""
    names = [a.split("=", 1)[1] for a in argv if a.startswith("--procedure=")]
    if not names:
        return SELECTED
    if names[0] not in PROCEDURES:
        raise SystemExit(f"unknown --procedure={names[0]}; one of {list(PROCEDURES)} (C: the selected procedure; A: {AS_BUILT_LABEL})")
    return names[0]


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_procedure(frozen: Path | None = None) -> dict:
    """What the run under the selected procedure rests on, read from step E's two files. Stops in words unless stage 1
    selected C and stage 2 validated C with both verdicts "passed" (E5.1), on one comparison fingerprint."""
    frozen = frozen or FROZEN
    s1p, s2p = frozen / STAGE1_FILE, frozen / STAGE2_FILE
    for path, what in ((s1p, "stage 1 (the selection)"), (s2p, "stage 2 (the validation)")):
        if not path.exists():
            raise SystemExit(f"{path} is missing: the simulation runs as the selected procedure only on step E's {what}; "
                             f"run step E, or name the labelled run --procedure=A ({AS_BUILT_LABEL})")
    s1, s2 = json.loads(s1p.read_text()), json.loads(s2p.read_text())
    chosen = (s1.get("selection") or {}).get("selected")
    if chosen != SELECTED:
        raise SystemExit(f"stage 1 selected {chosen!r}, not {SELECTED!r}: this simulation is wired for C; it will not run "
                         "another candidate as 'the selected procedure'")
    if s2.get("candidate") != SELECTED:
        raise SystemExit(f"stage 2 validated {s2.get('candidate')!r}, not {SELECTED!r}; stopping")
    verdicts = {"range": (s2.get("range") or {}).get("verdict"), "early_years_test": (s2.get("early_years_test") or {}).get("verdict")}
    if any(v != "passed" for v in verdicts.values()):
        raise SystemExit(f"stage 2's verdicts are {verdicts}: C is not validated on both rates (E5.1), so it is not run as the "
                         "selected procedure; the ranges are exploratory (E2.3, D-58 4.5) and that choice returns to the owner")
    f1, f2 = (s1.get("fingerprint") or {}).get("sha256"), (s2.get("fingerprint") or {}).get("sha256")
    if not f1 or f1 != f2:
        raise SystemExit("stage 1 and stage 2 were run under different comparison fingerprints; stopping")
    return {"procedure": SELECTED, "label": "the selected and validated procedure (step E)", **PROCEDURE_TEXT[SELECTED],
            "stage1_file": STAGE1_FILE, "stage1_sha256": _sha256(s1p), "stage2_file": STAGE2_FILE, "stage2_sha256": _sha256(s2p),
            "comparison_fingerprint": f1, "stage2_verdicts": verdicts,
            "validated_datasets_per_process": s2.get("datasets_per_process")}


def as_built_provenance() -> dict:
    return {"procedure": AS_BUILT, "label": AS_BUILT_LABEL, **PROCEDURE_TEXT[AS_BUILT],
            "note": "labelled run (D-59 rule 4.7): not the selected procedure; written to its own file"}


def c_reading(cand, b: np.ndarray, u: np.ndarray) -> dict:
    """One outcome's reading under C, in the keys read_draws and the size check read, from candidates.CandidateC's own
    methods (vcov: Eq. 4; crit: the Satterthwaite t quantile; aht: Eq. 10, 12), the computation step E validated.

    A failure anywhere (a standard error not finite and positive, the early-years test's degrees of freedom undefined, its
    variance singular) fails the reading: `numerical_failure` carries the cause and the range is NaN, so the reading
    counts as a miss and a rejection in calibration and as no detection in power (E4.1)."""
    from pipeline.analysis import candidates as cd
    combo = cand.p.combo
    est = float(combo @ b)
    out = {"est": est, "se": float("nan"), "lo": float("nan"), "hi": float("nan"), "clusters": int(cand.p.G),
           "pre_wald": float("nan"), "pre_p": float("nan"), "numerical_failure": None, "analytic_failure": None,
           "degrees_of_freedom": float(cand.nu), "procedure": SELECTED}
    V = cand.vcov(u)
    se = float(np.sqrt(max(float(combo @ V @ combo), 0.0)))
    out["se"] = se
    try:
        if not (np.isfinite(est) and np.isfinite(se) and se > 0):
            raise cd.Failed(cd.NON_FINITE_STANDARD_ERROR, "fit", "the CR2 standard error is not finite and positive")
        if cand.early_failure is not None:
            raise cand.early_failure
        p = cand.aht(b, V)
        if not np.isfinite(p):
            raise cd.Failed(cd.UNDEFINED_DEGREES_OF_FREEDOM, "early_years_test", "the AHT p-value is not finite")
    except cd.Failed as f:
        out["numerical_failure"] = out["analytic_failure"] = f.cause
        return out
    bc = cand.Cm @ b
    out.update(lo=est - cand.crit * se, hi=est + cand.crit * se, pre_p=p,
               pre_wald=float(bc @ np.linalg.solve(cand.Cm @ V @ cand.Cm.T, bc)))
    return out


def _one_draw_c(a: dict, rng, boot: int, taus) -> dict:
    """one_draw under C. C's design-level quantities (the adjustment matrices, nu, eta) are computed once per draw, since
    the stand-ins change the design draw by draw; every planted size and dating then costs one CR2 variance, because the
    fit is linear in the outcome: (b, u) for y + tau * path = (b, u)(y) + tau * (b, u)(path).
    The draw consumes the same random numbers as under A (the Rademacher matrix A would use is drawn and discarded), so the
    two procedures see the same stand-ins and the same made-up prices draw for draw."""
    from pipeline.analysis import candidates as cd
    prob = cd.Problem(a["X"], a["groups"], a["cluster"], projection=a["projection"], combo=headline_combo(a["X"].shape[1]), pre=PRE_IDX)
    cand = cd.CandidateC(prob)
    if cand.design_failure is None or cand.design_failure.cause != estimator.RANK_DEFICIENT:
        estimator.rademacher(rng, boot, prob.G)                           # A draws this once its fit passes the rank check
    if cand.design_failure is not None:
        bad = failed_reading(cand.design_failure.cause, prob.G, cand.design_failure.detail)
        bad.update(pre_p=float("nan"), procedure=SELECTED)
        return {"exact": [dict(bad) for _ in taus], "misdated": [dict(bad) for _ in taus], "control_columns_left_out": a["control_columns_left_out"]}
    b0, u0 = cand.fit(a["y"])
    paths = [cand.fit(a["paths"][:, j]) for j in range(a["paths"].shape[1])]
    out = {"exact": [], "misdated": []}
    for name, j in (("exact", 0), ("misdated", 1)):
        bp, up = paths[j]
        for pct in taus:
            if pct == 0 and name == "misdated":
                out[name].append(out["exact"][0])
                continue
            tau = float(np.log1p(pct / 100.0))
            out[name].append(c_reading(cand, b0 + tau * bp, u0 + tau * up))
    out["control_columns_left_out"] = a["control_columns_left_out"]
    return out


def one_draw(windows, blocks, errors, rng, boot: int = BOOT, controls: bool = True, taus=TAUS_PCT,
             fuel_control: str = GAS_SHARE, gas: dict | None = None, procedure: str = AS_BUILT) -> dict:
    """Fit one draw and read it at every planted effect, dated exactly and dated with errors, under `procedure` (the
    function's default is the bootstrap as built, for the job-U and test callers; the simulation's drivers pass C).

    A fit that raises RankDeficient is not skipped: every reading of the draw carries the cause (D-95 item 7).
    """
    a = assemble(windows, blocks, errors, controls, fuel_control, gas)
    if procedure == SELECTED:
        return _one_draw_c(a, rng, boot, taus)
    if procedure != AS_BUILT:
        raise ValueError(f"unknown procedure {procedure!r}; one of {PROCEDURES}")
    try:
        fit = estimator.Fit(a["y"], a["X"], a["groups"], a["cluster"], a["paths"], projection=a["projection"])
    except estimator.RankDeficient as e:
        bad = failed_reading(estimator.RANK_DEFICIENT, len(np.unique(a["cluster"])), str(e))
        return {"exact": [dict(bad) for _ in taus], "misdated": [dict(bad) for _ in taus], "control_columns_left_out": a["control_columns_left_out"]}
    combo = headline_combo(fit.K)
    v = estimator.rademacher(rng, boot, fit.G)
    out = {"exact": [], "misdated": []}
    for name, path in (("exact", 0), ("misdated", 1)):
        for pct in taus:
            if pct == 0 and name == "misdated":
                out[name].append(out["exact"][0])
                continue
            out[name].append(fit.summary(v, combo, PRE_IDX, path, float(np.log1p(pct / 100.0))))
    crit = float(stats.t.ppf((1 + LEVEL) / 2, fit.G - 1))
    z = out["exact"][0]
    z["lo_analytic"], z["hi_analytic"] = z["est"] - crit * z["se"], z["est"] + crit * z["se"]
    if z["analytic_failure"]:
        z["lo_analytic"] = z["hi_analytic"] = float("nan")
    out["control_columns_left_out"] = a["control_columns_left_out"]
    return out


def draw_errors(real: pd.DataFrame, picks: list, host_errs: dict, rng: np.random.Generator) -> dict:
    """A date error for each stand-in, drawn from the distribution of the host it stands in for."""
    out = {}
    for g, j, i in picks:
        e = host_errs.get(real.key.iloc[i])
        d = int(rng.choice(e)) if e is not None and len(e) else 0
        out[(g, int(j))] = 60 if d >= NEVER - 30 else d      # past the window either way
    return out


def read_draws(draws: list[dict], hosts: int, procedure: str = AS_BUILT) -> dict:
    """What a set of draws says: the placebo, the early-years test, and planted effects dated right and wrong.

    Numerical failures (D-95 section 3 item 7; E4.1, E4.3) stay in every denominator. In the calibration readings a
    failed draw counts as a range that misses zero and as an early-years test that rejects; in the power readings it
    counts as no detection, which is also against the design. Failure counts and causes are reported apart, including a
    count of zero, and the rates that include them say so.

    Power at a planted effect is the share of draws whose 90% range lies entirely above zero (`POWER`, adopted on
    2026-11-18 after the results were available); the smallest planted effect at which it reaches 80% is the "smallest
    increase detected in the correct direction four times in five" (SMALLEST_INCREASE_KEY). Moments (means, standard
    deviations, medians) are pandas reductions, which skip NaN and nothing else, and are labelled as such: a draw that
    failed before an estimate existed (failed_reading: a rank-deficient fit, or under C a design failure) is NaN
    everywhere and is left out of every moment; a draw that failed after its estimate was computed keeps its estimate,
    and its standard error unless that is NaN, in the moments, while its range is NaN and is left out of the range widths.
    Every failed draw is counted in the failure counts and in every rate's denominator.
    """
    pct = lambda x: round(100.0 * float(x), 3)  # noqa: E731
    zero = pd.DataFrame([d["exact"][0] for d in draws])
    bad, bad_a = failed(zero), failed(zero, "analytic_failure")
    covers = (zero.lo <= 0) & (zero.hi >= 0) & ~bad
    c = procedure == SELECTED
    pre = "pre_p" if c else "pre_p_bootstrap"                 # the chosen procedure's early-years p-value
    covers_a = None if c else (zero.lo_analytic <= 0) & (zero.hi_analytic >= 0) & ~bad_a
    out = {"hosts_in_the_panel_for_their_whole_window": hosts, "draws": len(draws), "clusters_median": int(zero.clusters.median()),
           "procedure": {"name": procedure, **PROCEDURE_TEXT[procedure]},
           "numerical_failures": ({"selected_procedure": failure_summary(zero)} if c else
                                  {"bootstrap": failure_summary(zero), "analytic": failure_summary(zero, "analytic_failure")}),
           "rates_include_numerical_failures": True,
           "power": dict(POWER),
           "nothing_planted": {
               "moments_are_over": ("every draw whose value for the moment is not NaN (pandas skips NaN and nothing else). A draw "
                                    "that failed before an estimate existed has none and is left out. A draw that failed after its "
                                    "estimate was computed keeps its estimate and its standard error in these moments, each unless "
                                    "it is NaN; its range is NaN, so it is left out of the range widths. Every failed draw is counted "
                                    "as a failure, as a range that misses zero, as an early-years test that rejects and as no "
                                    "detection"),
               "mean_estimate": pct(zero.est.mean()), "sd_of_estimates": pct(zero.est.std()), "mean_standard_error": pct(zero.se.mean()),
               "range_half_width_mean": pct((zero.hi - zero.lo).mean() / 2), "range_width_median": pct((zero.hi - zero.lo).median()),
               "range_covers_zero": round(float(covers.mean()), 3),
               "analytic_range_covers_zero": None if c else round(float(covers_a.mean()), 3)},
           "early_years_test": {
               "statistic": PROCEDURE_TEXT[procedure]["early_years_test"],
               "share_of_flat_histories_failing_at_p_below_0.10": round(float(((zero[pre] < PRETEST_FAILS) | bad).mean()), 3),
               "share_failing_at_p_below_0.05": round(float(((zero[pre] < 0.05) | bad).mean()), 3),
               "share_failing_at_the_chi_square_10pct_value": None if c else
                   round(float(((zero.pre_wald > stats.chi2.ppf(0.9, len(EARLY))) | bad_a).mean()), 3)}}
    if c:
        out["not_reported_under_the_selected_procedure"] = ("the analytic CR1 t range and the chi-square reading of the Wald "
                                                            "statistic, which belong to the bootstrap as built's readings")
    for name in ("exact", "misdated"):
        by_tau = [pd.DataFrame([d[name][i] for d in draws]) for i in range(len(TAUS_PCT))]
        rate = [float(((x.lo > 0) & ~failed(x)).mean()) for x in by_tau]
        five = by_tau[TAUS_PCT.index(5)]
        t5 = float(np.log1p(0.05))
        five_bad = failed(five)
        out["start_years_exact" if name == "exact" else "start_years_misdated"] = {
            SMALLEST_INCREASE_KEY: detectable(rate),
            POWER_BY_TAU_KEY: {str(t): round(r, 3) for t, r in zip(TAUS_PCT, rate)},
            "planted_5pct": {"mean_estimate": pct(five.est.mean()), "share_of_the_planted_effect_recovered": round(float(five.est.mean() - zero.est.mean()) / t5, 3),
                             "range_half_width_mean": pct((five.hi - five.lo).mean() / 2),
                             "range_covers_the_planted_effect": round(float(((five.lo <= t5) & (five.hi >= t5) & ~five_bad).mean()), 3),
                             "early_years_test_fails_at_p_below_0.10": round(float(((five[pre] < PRETEST_FAILS) | five_bad).mean()), 3),
                             "numerical_failures": failure_summary(five)}}
    return out


def real_hosts(treated: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict, usable: set | None = None) -> pd.DataFrame:
    """Hosts with an outcome in all ten window years, with what a stand-in is matched on.

    `usable` (usable_flag.read().usable) is who has an outcome from step D (D-58 rule 6.3; D-94). None keeps the
    template before step D: residential sales above zero and the customer floor.
    """
    own = q.groupby(KEY).ownership.last()
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    reg = regions.set_index(KEY + ["year"]).region
    if usable is None:
        ok = q[q.meets_size_floor & (q.res_mwh > 0)]
        have = ok.groupby(KEY).year.agg(set)
    else:
        have: dict = {}
        for u, st, yr in usable:
            have.setdefault((int(u), st), set()).add(int(yr))
    rows = []
    for r in treated.itertuples():
        k = (int(r.utility_id_eia), r.state)
        years = set(range(r.cohort - PRE, r.cohort + POST + 1))
        ref = r.cohort + REF
        if years <= have.get(k, set()) and (k + (ref,)) in reg.index and r.state in fuel:
            rows.append({"cohort": int(r.cohort), "region": reg[k + (ref,)], "ownership": own.get(k),
                         "log_size": float(np.log(cust.loc[k, ref])), "state": r.state, "key": k})
    return pd.DataFrame(rows)


class Exclusions:
    """build_blocks' `excluded` for a draw under the ownership rules (D-54 ruling 2; D-58 rules 2.2 and 2.3).

    The stand-in takes the host's place, so the rules are applied to it as a host: a unit of its own utility (the same
    EIA id) never; with the table, no same-parent affiliate in any year of its window and, if it is investor-owned, no
    investor-owned candidate without a row; `affiliates_included` is rule 2.3's sensitivity. A class, not a closure,
    so worker processes can receive it.
    """

    def __init__(self, windows: dict, table: pd.DataFrame | None, ownership_of: dict | None, affiliates_included: bool = False):
        self.windows, self.table, self.ownership_of, self.affiliates = windows, table, ownership_of, affiliates_included
        self._cache: dict = {}

    def __call__(self, g: int, row: int) -> set:
        if (g, row) not in self._cache:
            from pipeline.analysis import ownership as own_rules
            w = self.windows[g]
            host = (int(w.keys[row][0]), w.keys[row][1])
            cand = [(int(k[0]), k[1]) for k in w.keys]
            years = range(g - PRE, g + POST + 1)
            if self.table is None:
                out = {k for k in cand if k[0] == host[0]}
            else:
                out = set(own_rules.ineligible_for(self.table, host, years, [k for k in cand if k != host], self.ownership_of, self.affiliates))
            self._cache[(g, row)] = {i for i, k in enumerate(cand) if k in out}
        return self._cache[(g, row)]


def ownership_classes(q: pd.DataFrame) -> dict:
    """Each unit's EIA ownership class, its last value: what rule 2.2's fail-closed test reads."""
    return {(int(u), s): o for (u, s), o in q.groupby(KEY).ownership.last().items()}


def rule_inputs(rules: Rules, q: pd.DataFrame, ownership=None, usable=None, gas=None) -> tuple:
    """The inputs the rules need, loaded from their committed sources where not given: the ownership table
    (pipeline/analysis/ownership.csv), the usable flag (usable_flag.read: five columns of the quantities file) and the
    gas shares (data/frozen/fuel_mix_groups.csv). An input the rules do not use is returned as None."""
    from pipeline.analysis import ownership as own_rules
    from pipeline.analysis import usable_flag
    if rules.ownership == "off":
        ownership = None
    elif ownership is None:
        ownership = own_rules.load()
    if rules.usable != "flag":
        usable = None
    elif usable is None:
        usable = usable_flag.read().usable
    if rules.fuel_control != GAS_SHARE:
        gas = None
    elif gas is None:
        gas = load_gas_share()
    return ownership, usable, gas


def simulation_hosts(treated: pd.DataFrame, clean: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict,
                     dd: pd.DataFrame, rules: Rules, ownership=None, usable=None, gas=None, unknown_load=None, theta: float = 0.02):
    """The hosts the estimate is run on under `rules`, which are the hosts the stand-ins replace, and the design.

    The real design is built with the same rules (design.build_with_rules): a host without a full usable window, or
    one that does not keep its place under the support rule when it is applied, is not given a stand-in. Returns
    (treated rows kept, the Design).
    """
    from pipeline.analysis import design as dsg      # imported here: design imports this module
    d = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                             unknown_load=unknown_load, theta=theta)
    keep = {tuple(k) for k in d.hosts.key} if len(d.hosts) else set()
    mask = [(int(u), st) in keep for u, st in zip(treated.utility_id_eia, treated.state)]
    return treated[mask], d


def outcome_rows(p: pd.DataFrame, usable: set | None) -> pd.DataFrame:
    """Price rows that count as outcomes: in the usable set from step D, else the filter before it."""
    if usable is None:
        return p[p.meets_size_floor & (p.res_price > 0)]
    keys = [(int(u), st, int(y)) in usable for u, st, y in zip(p.utility_id_eia, p.state, p.year)]
    return p[keys]


CHUNK = 25                                     # draws per task; each task has its own seed, so the result does not depend on the worker count
_CTX: dict = {}


def _init(ctx: dict) -> None:
    _CTX.clear()
    _CTX.update(ctx)


def _chunks(seed: tuple, draws: int) -> list:
    return [(seed + (c,), min(CHUNK, draws - c * CHUNK)) for c in range((draws + CHUNK - 1) // CHUNK)]


def _run(task, ctx: dict, chunks: list, workers: int) -> list:
    """Run `task` over the chunks, in this process or in `workers` fresh ones."""
    if workers <= 1:
        _init(ctx)
        return [task(c) for c in chunks]
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn"), initializer=_init, initargs=(ctx,)) as ex:
        return list(ex.map(task, chunks))


def _host_chunk(args) -> dict:
    seed, n = args
    rng = np.random.default_rng(list(seed))
    c = _CTX
    real, windows, n_units = c["real"], c["windows"], c["n_units"]
    results, tiers, dropped, moved = [], dict.fromkeys(TIERS, 0), 0, 0
    for _ in range(n):
        picks, how = pick_stand_ins(real, windows, n_units, rng)
        for k, v in how["tiers"].items():
            tiers[k] += v
        blocks, lost = build_blocks(windows, picks, c["form"], n_units, excluded=c.get("excluded"))
        dropped += lost
        for g, tr, comp in blocks:
            rt = windows[g].region_t[np.concatenate([tr, comp])]
            moved += int((rt.min(1) != rt.max(1)).sum())
        results.append(one_draw(windows, blocks, draw_errors(real, picks, c["host_errs"], rng), rng, c["boot"],
                                controls=c["form"] != "same_state", fuel_control=c["fuel_control"], gas=c.get("gas"),
                                procedure=c["procedure"]))
    return {"results": results, "tiers": tiers, "dropped": dropped, "moved": moved}


def run_new_hosts(label: str, treated: pd.DataFrame, clean: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict,
                  dd: pd.DataFrame, prices: pd.DataFrame, host_errs: dict, seed: tuple, draws: int = DRAWS,
                  form: str = "nearest_in_size", boot: int = BOOT, workers: int = 1, rules: Rules = HEADLINE_RULES,
                  ownership=None, usable=None, gas=None, unknown_load=None, theta: float = 0.02, procedure: str = SELECTED,
                  provenance: dict | None = None) -> dict:
    """The new-host estimate on one set of hosts, in the adopted form or a labelled side form, under `rules`.

    `procedure` is the inference every range, width, detectable effect, recovery figure and early-years rate comes from:
    C, the selected and validated procedure (the default), or A, the labelled bootstrap as built. `provenance` (from
    selected_procedure() or as_built_provenance()) goes into the output and the fingerprint.

    From step D the headline rules are the default (Rules): the stand-ins replace the hosts the design keeps, outcomes
    are the usable unit-years, each stand-in's comparisons leave out its own utility, same-parent affiliates and (if it is
    investor-owned) investor-owned units without an ownership row, and the fit carries the gas-share control.
    """
    ownership, usable, gas = rule_inputs(rules, q, ownership, usable, gas)
    unknown_load = require_unknown_load(unknown_load)
    clean, load_unknown = unknown_load.gate(clean, theta, "comparison")       # no stand-in or comparison from a frame share (D-96)
    treated, real_design = simulation_hosts(treated, clean, q, regions, fuel, dd, rules, ownership, usable, gas, unknown_load, theta)
    real = real_hosts(treated, q, regions, fuel, usable)
    p = prices.merge(clean, on=KEY).merge(q[KEY + ["year", "meets_size_floor"]], on=KEY + ["year"])
    p = outcome_rows(p, usable).assign(log_price=lambda d: np.log(d.res_price))
    unit_code = {k: i for i, k in enumerate(map(tuple, clean.values))}
    state_code = {st: i for i, st in enumerate(sorted(clean.state.unique()))}
    windows = build_windows(sorted(real.cohort.unique()), p, q, regions, fuel, dd, unit_code, state_code)
    excluded = None if rules.ownership == "off" else Exclusions(windows, ownership, ownership_classes(q), rules.ownership == "affiliates_readmitted")
    if procedure not in PROCEDURES:
        raise ValueError(f"unknown procedure {procedure!r}; one of {PROCEDURES}")
    ctx = {"real": real, "windows": windows, "n_units": len(unit_code), "host_errs": host_errs, "form": form, "boot": boot,
           "excluded": excluded, "fuel_control": rules.fuel_control, "gas": gas, "procedure": procedure}
    parts = _run(_host_chunk, ctx, _chunks(seed, draws), workers)
    results = [r for part in parts for r in part["results"]]
    tiers = {k: sum(part["tiers"][k] for part in parts) for k in TIERS}
    dropped, moved = sum(part["dropped"] for part in parts), sum(part["moved"] for part in parts)
    out = read_draws(results, int(len(real)), procedure)
    out["procedure_provenance"] = provenance
    e = np.concatenate([host_errs[k] for k in real.key if k in host_errs]) if len(real) else np.zeros(1)
    out.update({"hosts_as_built": int(len(treated)), "their_states": int(real.state.nunique()),
                "their_ownership": real.ownership.value_counts().to_dict(), "their_regions_in_the_reference_year": real.region.value_counts().to_dict(),
                "comparison_form": form, "bootstrap_replications": boot if procedure == AS_BUILT else None, "rules": rules.label,
                "fuel_control": rules.fuel_control if form != "same_state" else "no_controls",
                "gas_share_assumption": GAS_ASSUMPTION if rules.fuel_control == GAS_SHARE and form != "same_state" else None,
                "hosts_not_given_a_stand_in": real_design.dropped,
                "hosts_with_unresolved_ownership": getattr(real_design, "unresolved_ownership", None),
                "load_unknown_excluded": load_unknown + [x for x in real_design.load_unknown_excluded if x["role"] == "host"],
                "stand_in_match": {k: round(v / (draws * len(real)), 3) for k, v in tiers.items()},
                "hosts_left_without_a_comparison_utility_per_draw": round(dropped / draws, 2),
                "utilities_that_change_region_inside_their_window_per_draw": round(moved / draws, 1),
                "date_errors_drawn_for_these_hosts": {"exact": round(float((e == 0).mean()), 3), "within_1_year": round(float((np.abs(e) <= 1).mean()), 3),
                                                      "true_crossing_2_or_more_years_earlier": round(float((e <= -2).mean()), 3)}})
    out["fingerprint"] = _fingerprint(real_design, rules, usable,
                                      {"kind": "new_host_estimate", "draws": draws, "form": form, "taus_pct": list(TAUS_PCT),
                                       "host_date_errors": {f"{k[0]}:{k[1]}": list(map(int, v)) for k, v in sorted(host_errs.items())},
                                       "stand_ins_from_nearest": NEAREST},
                                      {"bootstrap_replications": boot, "level": LEVEL, "pretest_fails": PRETEST_FAILS,
                                       "procedure": procedure, "procedure_provenance": provenance}, seed)
    n = out["nothing_planted"]
    print(f"  {label} [{form}, procedure {procedure}]: {len(real)} hosts, drift {n['mean_estimate']}%, range +/-{n['range_half_width_mean']}%, covers "
          f"{n['range_covers_zero']:.0%}, early-years test fails {out['early_years_test']['share_of_flat_histories_failing_at_p_below_0.10']:.0%}, "
          f"smallest increase detected in the correct direction four times in five {out['start_years_exact'][SMALLEST_INCREASE_KEY]}% "
          f"exact, {out['start_years_misdated'][SMALLEST_INCREASE_KEY]}% misdated", flush=True)
    return out


# ---- the size of the early-years test, on made-up prices -------------------------------------------
# The placebo draws above reuse the same few stand-ins (they must come from the hosts' own states), so
# the share of them that fail the test is not a clean read of how often a flat history fails. This
# check makes a fresh set of prices for every draw, with no effect of anything in them, on the real
# utilities, states, regions and windows. The prices have a utility level, a market-region-by-year
# shock that a utility follows as it moves, a state-by-year shock (so that utilities in a state move
# together, which is what clustering by state is for) and the utility's own persistent noise.
SIZE_DGP = {"region_step_sd": 0.03, "state_sd": 0.015, "state_rho": 0.6, "own_sd": 0.03, "own_rho": 0.7}
SIZE_DATASETS = 1000
SIZE_BAND = (0.07, 0.13)                        # "about one time in ten" (D-33), with room for 1,000 draws' sampling error
FIRST_YEAR = 2001


def made_up_prices(region_all: np.ndarray, state_all: np.ndarray, rng: np.random.Generator, dgp: dict = SIZE_DGP) -> np.ndarray:
    """Units by years (2001 to 2025) log prices with nothing in them but levels, shocks and noise."""
    n, years = region_all.shape

    def ar1(rows, rho, sd):
        e = rng.normal(0, sd, (rows, years))
        for t in range(1, years):
            e[:, t] += rho * e[:, t - 1]
        return e

    region = rng.normal(0, dgp["region_step_sd"], (int(region_all.max()) + 1, years)).cumsum(1)
    state = ar1(int(state_all.max()) + 1, dgp["state_rho"], dgp["state_sd"])
    return (rng.normal(2.4, 0.2, (n, 1)) + region[region_all, np.arange(years)[None, :]] + state[state_all]
            + ar1(n, dgp["own_rho"], dgp["own_sd"]))


def _size_chunk(args) -> list:
    seed, n = args
    rng = np.random.default_rng(list(seed))
    c = _CTX
    real, windows, n_units = c["real"], c["windows"], c["n_units"]
    out = []
    for _ in range(n):
        P = made_up_prices(c["region_all"], c["state_all"], rng)
        for g, w in windows.items():
            w.y = P[w.unit][:, g - PRE - FIRST_YEAR:g + POST + 1 - FIRST_YEAR]
        picks, _how = pick_stand_ins(real, windows, n_units, rng)
        blocks, _lost = build_blocks(windows, picks, c["form"], n_units, excluded=c.get("excluded"))
        z = one_draw(windows, blocks, {}, rng, c["boot"], taus=(0,), fuel_control=c["fuel_control"], gas=c.get("gas"),
                     procedure=c["procedure"])["exact"][0]
        out.append({k: z.get(k, np.nan) for k in ("est", "se", "lo", "hi", "pre_wald", "pre_p_bootstrap", "pre_p", "numerical_failure",
                                                   "analytic_failure")})
    return out


def run_size_check(label: str, treated: pd.DataFrame, clean: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict,
                   dd: pd.DataFrame, seed: tuple, datasets: int = SIZE_DATASETS, form: str = "nearest_in_size", boot: int = BOOT,
                   workers: int = 1, rules: Rules = HEADLINE_RULES, ownership=None, usable=None, gas=None,
                   unknown_load=None, theta: float = 0.02, procedure: str = SELECTED, provenance: dict | None = None) -> dict:
    """How often the early-years test fails, and the range misses zero, when the prices are made up and flat, under `rules`
    and `procedure` (C by default; A the labelled bootstrap as built)."""
    ownership, usable, gas = rule_inputs(rules, q, ownership, usable, gas)
    unknown_load = require_unknown_load(unknown_load)
    clean, load_unknown = unknown_load.gate(clean, theta, "comparison")
    treated, real_design = simulation_hosts(treated, clean, q, regions, fuel, dd, rules, ownership, usable, gas, unknown_load, theta)
    real = real_hosts(treated, q, regions, fuel, usable)
    if usable is None:
        ok = q[q.meets_size_floor & (q.res_mwh > 0)][KEY + ["year"]].merge(clean, on=KEY)
    else:                                                    # from step D: who has an outcome is the usable flag (D-94)
        ok = pd.DataFrame(sorted(usable), columns=KEY + ["year"]).merge(clean, on=KEY)
    template = ok.assign(log_price=0.0)                      # which utility has a price in which year
    unit_code = {k: i for i, k in enumerate(map(tuple, clean.values))}
    state_code = {st: i for i, st in enumerate(sorted(clean.state.unique()))}
    windows = build_windows(sorted(real.cohort.unique()), template, q, regions, fuel, dd, unit_code, state_code)
    codes = {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}
    idx = pd.MultiIndex.from_tuples(list(unit_code))
    region_all = region_matrix(regions, idx, range(FIRST_YEAR, 2026), codes)
    region_all = np.where(np.isnan(region_all), 0, region_all).astype(int)
    state_all = np.array([state_code[k[1]] for k in unit_code])
    excluded = None if rules.ownership == "off" else Exclusions(windows, ownership, ownership_classes(q), rules.ownership == "affiliates_readmitted")
    if procedure not in PROCEDURES:
        raise ValueError(f"unknown procedure {procedure!r}; one of {PROCEDURES}")
    ctx = {"real": real, "windows": windows, "n_units": len(unit_code), "form": form, "boot": boot,
           "region_all": region_all, "state_all": state_all, "excluded": excluded, "fuel_control": rules.fuel_control, "gas": gas,
           "procedure": procedure}
    z = pd.DataFrame([r for part in _run(_size_chunk, ctx, _chunks(seed, datasets), workers) for r in part])
    bad, bad_a = failed(z), failed(z, "analytic_failure")
    c = procedure == SELECTED
    pre = z.pre_p if c else z.pre_p_bootstrap                 # the chosen procedure's early-years p-value
    fail = float(((pre < PRETEST_FAILS) | bad).mean())
    out = {"datasets": int(len(z)), "hosts": int(len(real)), "made_up_prices": SIZE_DGP, "rules": rules.label,
           "procedure": {"name": procedure, **PROCEDURE_TEXT[procedure]}, "procedure_provenance": provenance,
           "load_unknown_excluded": load_unknown + [x for x in real_design.load_unknown_excluded if x["role"] == "host"],
           "numerical_failures": ({"selected_procedure": failure_summary(z)} if c else
                                  {"bootstrap": failure_summary(z), "analytic": failure_summary(z, "analytic_failure")}),
           "rates_include_numerical_failures": True,
           "early_years_test_fails_at_p_below_0.10": round(fail, 3),
           "early_years_test_fails_at_p_below_0.05": round(float(((pre < 0.05) | bad).mean()), 3),
           "fails_at_the_chi_square_10pct_value": None if c else
               round(float(((z.pre_wald > stats.chi2.ppf(0.9, len(EARLY))) | bad_a).mean()), 3),
           "range_misses_zero": round(float(((z.lo > 0) | (z.hi < 0) | bad).mean()), 3),
           "mean_estimate_pct": round(100 * float(z.est.mean()), 3), "sd_of_estimates_pct": round(100 * float(z.est.std()), 3),
           "range_half_width_mean_pct": round(100 * float((z.hi - z.lo).mean() / 2), 3),
           "inside_the_band_written_in_advance": bool(SIZE_BAND[0] <= fail <= SIZE_BAND[1]), "band": list(SIZE_BAND),
           "fingerprint": _fingerprint(real_design, rules, usable, {"kind": "size_check", "datasets": datasets, "form": form,
                                                                    "made_up_prices": SIZE_DGP},
                                       {"bootstrap_replications": boot, "level": LEVEL, "pretest_fails": PRETEST_FAILS,
                                        "procedure": procedure, "procedure_provenance": provenance}, seed)}
    chi = out["fails_at_the_chi_square_10pct_value"]
    print(f"  size check {label} [procedure {procedure}]: {len(real)} hosts, early-years test fails {fail:.1%} of flat histories"
          f"{'' if chi is None else f' (chi-square value {chi:.1%})'}; range misses zero {out['range_misses_zero']:.1%}", flush=True)
    return out


def _point_chunk(args) -> dict:
    seed, n = args
    rng = np.random.default_rng(list(seed))
    c = _CTX
    s, real = c["s"], c["real"]
    res = {cap: [] for cap in CAPS}
    for _ in range(n):
        picks, _how = pick_stand_ins(real, {0: s}, c["n_units"], rng)
        x = c["own_dose"].copy()
        for _, j, i in picks:
            x[j] = c["host_dose"][i]
        for cap in CAPS:
            xc = x if cap is None else np.minimum(x, cap)
            xf, yf = per_point_frame(c["name"], xc, s.y)
            try:
                fit = estimator.Fit(yf.ravel(), xf.reshape(-1, 1), c["groups"], c["cluster"])
            except estimator.RankDeficient as e:          # counted, never skipped (D-95 item 7)
                res[cap].append(failed_reading(estimator.RANK_DEFICIENT, len(np.unique(c["cluster"])), str(e)))
                continue
            res[cap].append(fit.summary(estimator.rademacher(rng, c["boot"], fit.G), np.ones(1)))
    return res


def run_second_number(q: pd.DataFrame, dose: pd.DataFrame, clean: pd.DataFrame, regions: pd.DataFrame, prices: pd.DataFrame,
                      seed: tuple, draws: int = DRAWS, boot: int = BOOT, workers: int = 1, usable: set | None = None,
                      unknown_load=None) -> dict:
    """Per point of load, both forms, at each cap, with every material host replaced by a stand-in carrying its load history.

    Long comparison: the change in log price from 2008-2010 to 2023-2025 on the change in load share, within
    the utility's region before, its region after, and its size band. Year by year: log price on load share,
    2005 to 2025, utility effects and region-by-band-by-year effects with the region read each year.
    """
    own = q.groupby(KEY).agg(ownership=("ownership", "last"))
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    # D-96: a utility a load-unknown site reaches has no settled dose. It is neither a host with a load history nor a
    # never-host with none; no dose is computed for it, and it is named as carried to step F with the timing cases.
    unknown_load = require_unknown_load(unknown_load)
    clean, carried = unknown_load.every(clean, "comparison")
    dose_units = dose[KEY].drop_duplicates()
    _, carried_hosts = unknown_load.every(dose_units, "dose")
    dose = dose[[(int(u), st) not in unknown_load.affected for u, st in zip(dose.utility_id_eia, dose.state)]]
    D0 = dose.pivot_table(index=KEY, columns="year", values="dose").reindex(columns=range(2001, 2026)).fillna(0.0) * 100.0
    hosts_all = [k for k in D0.index if D0.loc[k].max() >= CLEAN_BELOW * 100]
    ok = q[q.meets_size_floor & (q.res_mwh > 0)]
    p = prices.merge(clean, on=KEY).merge(q[KEY + ["year", "meets_size_floor"]], on=KEY + ["year"])
    p = outcome_rows(p, usable).assign(log_price=lambda d: np.log(d.res_price))
    unit_code = {k: i for i, k in enumerate(map(tuple, clean.values))}
    state_code = {st: i for i, st in enumerate(sorted(clean.state.unique()))}
    codes = {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}
    reg = regions.set_index(KEY + ["year"]).region
    out = {}
    designs = {"long_difference": (list(LONG_PRE + LONG_POST), LONG_PRE[-1]), "panel": (list(PANEL_YEARS), PANEL_YEARS[0])}
    for name, (years, size_year) in designs.items():
        y = balanced(p, "log_price", years)
        rt = region_matrix(regions, y.index, years, codes)
        size = cust.reindex(y.index)[size_year].values
        keep = (~np.isnan(rt).any(1)) & (size > 0)
        ref_year = LONG_REGION_YEARS[0] if name == "long_difference" else size_year
        names = {i: r for r, i in codes.items()}
        col = years.index(ref_year)
        a = own.reindex(y.index).assign(res_customers=size, region=[names.get(c) if not np.isnan(c) else None for c in rt[:, col]])
        s = Stack(0, y[keep], a[keep], unit_code, state_code)
        rt = rt[keep].astype(int)
        have = ok[ok.year.isin(years)].groupby(KEY).size()
        real = pd.DataFrame([{"cohort": 0, "region": reg.get(k + (ref_year,)), "ownership": own.ownership.get(k),
                              "log_size": float(np.log(cust.loc[k, size_year])), "state": k[1], "key": k}
                             for k in hosts_all if have.get(k, 0) == len(years) and cust.loc[k, size_year] > 0
                             and pd.notna(reg.get(k + (ref_year,)))])
        own_dose = D0.reindex(pd.MultiIndex.from_tuples(s.keys)).fillna(0.0)[years].values
        host_dose = np.vstack([D0.loc[k, years].values for k in real.key])
        n, P = len(s.keys), len(years)
        if name == "long_difference":
            a_pre, a_post = rt[:, years.index(LONG_REGION_YEARS[0])], rt[:, years.index(LONG_REGION_YEARS[1])]
            groups = [(a_pre * 1000 + a_post) * 10 + s.band]
            cluster = s.state
        else:
            tt = np.tile(np.arange(P), n)
            groups = [np.repeat(np.arange(n), P), (rt.ravel() * 10 + np.repeat(s.band, P)) * P + tt]
            cluster = np.repeat(s.state, P)
        ctx = {"s": s, "real": real, "n_units": len(unit_code), "own_dose": own_dose, "host_dose": host_dose, "name": name,
               "groups": groups, "cluster": cluster, "boot": boot}
        parts = _run(_point_chunk, ctx, _chunks(seed + (len(out),), draws), workers)
        res = {cap: [r for part in parts for r in part[cap]] for cap in CAPS}
        d = {}
        for cap in CAPS:
            base = pd.DataFrame(res[cap])
            hd = host_dose if cap is None else np.minimum(host_dose, cap)
            hx = per_point_frame(name, hd, hd)[0]
            dev = np.sort((hx.max(1) - hx.max(1).mean()) ** 2)[::-1]
            d["uncapped" if cap is None else f"capped_at_{cap:.0f}_points"] = {
                "numerical_failures": failure_summary(base),
                "moments_are_over": ("every draw whose value for the moment is not NaN (pandas skips NaN and nothing else). A draw "
                                     "that failed before an estimate existed (a rank-deficient fit) has none and is left out. A draw "
                                     "that failed after its estimate was computed keeps its estimate, unless NaN, in the mean "
                                     "estimate; its range is NaN, so it is left out of the range widths. Every failed draw is "
                                     "counted as a failure and as a range that does not cover zero"),
                "mean_estimate_nothing_planted": round(100 * float(base.est.mean()), 4),
                "range_half_width_mean": round(100 * float((base.hi - base.lo).mean() / 2), 4),
                "range_covers_zero": round(float(((base.lo <= 0) & (base.hi >= 0) & ~failed(base)).mean()), 3),
                "share_of_load_share_variation_from_the_three_largest_hosts": round(float(dev[:3].sum() / dev.sum()), 3),
                "load_share_points_of_the_median_host": round(float(np.median(hx.max(1))), 2),
                "range_half_width_at_the_median_hosts_load_pct_of_price": round(100 * float((base.hi - base.lo).mean() / 2) * float(np.median(hx.max(1))), 3)}
        d.update({"unit": "percent of residential price per point of load share", "utilities_with_material_load_given_a_stand_in": int(len(real)),
                  "utilities_in_the_sample": int(n), "their_states": int(real.state.nunique()),
                  "utilities_that_change_region_in_the_sample": int((rt.min(1) != rt.max(1)).sum())})
        d["inference"] = SECOND_NUMBER_INFERENCE
        d["carried_to_step_f"] = sorted({x["utility"] for x in carried + carried_hosts})
        d["carried_to_step_f_why"] = LOAD_UNKNOWN
        out[name] = d
        m = d[f"capped_at_{MAIN_CAP:.0f}_points"]
        print(f"  per point [{name}]: {len(real)} hosts; capped at 25: range +/-{m['range_half_width_mean']} % per point, covers "
              f"{m['range_covers_zero']:.0%}; uncapped +/-{d['uncapped']['range_half_width_mean']}", flush=True)
    return out


def read_listed_outcomes(units: pd.DataFrame, list_path: Path | None = None, hash_path: Path | None = None) -> pd.DataFrame:
    """The ONE way this module reads prices: per-unit outcome files of units on the simulation's access list, and only those.

    (a) reads the list and its recorded SHA-256, recomputes the hash, and refuses if either is missing or they differ;
    (b) refuses if any requested unit is not on the list, saying how many and naming the first few;
    (c) passes exactly the requested units, every one of them listed, to panel.load_outcomes, and nothing else.
    (docs/gate1/step-e-rules-2026-11-18.md section 9, adopted in D-95: "restrict the reader to those named units".)
    """
    from pipeline.analysis import simulation_access_list as sal
    allowed = sal.verified_list(list_path, hash_path)
    req = units[KEY].drop_duplicates()
    keys = [(int(u), str(st)) for u, st in zip(req.utility_id_eia, req.state)]
    off = [k for k in keys if k not in allowed]
    if off:
        raise PermissionError(f"{len(off)} requested units are not on the simulation's access list (first: "
                              f"{', '.join(f'{u}:{st}' for u, st in off[:5])}); no price is read")
    return panel.load_outcomes(purpose="power_simulation", units=pd.DataFrame(keys, columns=KEY))


def restrict_to_access_list(clean: pd.DataFrame, list_path: Path | None = None, hash_path: Path | None = None) -> tuple[pd.DataFrame, int]:
    """The comparison-eligible units the simulation may use: those on the (verified) access list. Returns them and how many
    eligible units were left out; their reasons are in simulation_access_excluded.csv. Comparison eligibility alone is not
    permission to read prices (D-95)."""
    from pipeline.analysis import simulation_access_list as sal
    allowed = sal.verified_list(list_path, hash_path)
    on = [(int(u), st) in allowed for u, st in zip(clean.utility_id_eia, clean.state)]
    return clean[on], int(len(clean) - sum(on))


def _fingerprint(d, rules: Rules, usable, assumptions: dict, settings: dict, seed) -> dict:
    """The run's fingerprint (D-58 rule 10 as widened by D-59 item 5): see design.run_fingerprint."""
    from pipeline.analysis import design as dsg
    return dsg.run_fingerprint(d, rules=rules, usable=usable, assumptions=assumptions, settings=settings, seeds=seed)


def output_path(name: str, rules: Rules, procedure: str = SELECTED) -> Path:
    """The headline run writes `name`; a labelled variant writes beside it with its label, never over it. A run of the
    bootstrap as built (procedure A) carries AS_BUILT_SUFFIX as well, so it never writes over the selected procedure's file."""
    base = name if rules == HEADLINE_RULES else name.replace(".json", f"_{rules.label}.json")
    if procedure == AS_BUILT:
        base = base.replace(".json", f"{AS_BUILT_SUFFIX}.json")
    elif procedure != SELECTED:
        raise ValueError(f"unknown procedure {procedure!r}; one of {PROCEDURES}")
    return FROZEN / base


def write_report(report: dict, rules: Rules, procedure: str) -> Path:
    """Writes the simulation's report where `procedure` says, and refuses a run of A aimed at the selected procedure's file."""
    path = output_path("power_simulation.json", rules, procedure)
    if procedure != SELECTED and path == output_path("power_simulation.json", rules, SELECTED):
        raise RuntimeError("a run of the bootstrap as built may never write over the selected procedure's output")
    if report.get("procedure", {}).get("procedure") != procedure:
        raise RuntimeError(f"the report says procedure {report.get('procedure', {}).get('procedure')!r} but is being written as {procedure!r}")
    path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return path


# ---- added after the first run of D-38 was read (D-39); labelled as such in the report -----------------
ADDED_DRAWS = 500


def _shortcut_chunk(args) -> list:
    seed, n = args
    rng = np.random.default_rng(list(seed))
    c = _CTX
    real, windows, n_units = c["real"], c["windows"], c["n_units"]
    out = []
    for _ in range(n):
        picks, _how = pick_stand_ins(real, windows, n_units, rng)
        blocks, _lost = build_blocks(windows, picks, "nearest_in_size", n_units, excluded=c.get("excluded"))
        a = assemble(windows, blocks, fuel_control=c.get("fuel_control", GAS_SHARE), gas=c.get("gas"))
        try:
            fit = estimator.Fit(a["y"], a["X"], a["groups"], a["cluster"], projection=a["projection"])
        except estimator.RankDeficient:               # counted, never skipped (D-95 item 7)
            out.append({"full_half": np.nan, "short_half": np.nan, "full_covers": False, "short_covers": False,
                        "full_p": np.nan, "short_p": np.nan, "full_failure": estimator.RANK_DEFICIENT, "short_failure": estimator.RANK_DEFICIENT})
            continue
        combo = headline_combo(fit.K)
        v = estimator.rademacher(rng, c["boot"], fit.G)
        full, short = fit.summary(v, combo, PRE_IDX), fit.summary(v, combo, PRE_IDX, shortcut=True)
        out.append({"full_half": (full["hi"] - full["lo"]) / 2, "short_half": (short["hi"] - short["lo"]) / 2,
                    "full_covers": bool(full["lo"] <= 0 <= full["hi"]), "short_covers": bool(short["lo"] <= 0 <= short["hi"]),
                    "full_p": full["pre_p_bootstrap"], "short_p": short["pre_p_bootstrap"],
                    "full_failure": full["numerical_failure"], "short_failure": short["numerical_failure"]})
    return out


def run_added() -> int:
    """Both bootstraps on the same draws: the full one, and the shortcut the first two runs used."""
    q = panel.load_quantities()
    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    regions = market_region.by_unit_year(q)
    fuel, dd = load_controls()
    workers = max(1, min(10, (os.cpu_count() or 2) - 2))
    rules = rules_from_argv(sys.argv)
    ownership, usable, gas = rule_inputs(rules, q)
    unknown = load_unknown_load()
    path = output_path("power_simulation.json", rules, AS_BUILT)        # about the bootstrap as built: its own file (rule 4.7)
    if not path.exists():
        raise SystemExit(f"{path.name} is missing: --added extends the labelled run of the bootstrap as built; run "
                         "power_simulation.py --procedure=A first")
    report = json.loads(path.read_text())
    treated, clean = design(q, dose, 0.02, history_settled(0.02))
    clean, _off_list = restrict_to_access_list(clean)
    clean, _unknown = unknown.gate(clean, 0.02, "comparison")
    aside = set_aside(0.02)
    prices = read_listed_outcomes(clean)[KEY + ["year", "res_price"]]
    keep = lambda d: d[[k not in aside for k in zip(d.utility_id_eia, d.state)]]  # noqa: E731
    added = {"why": "D-37 found that the bootstrap in the first two runs (D-22, D-31) did not re-estimate the region-by-year effects "
                    "in each replication. This run does both bootstraps on the same draws, to see how much that mattered. It was "
                    "not in the standard (D-38).", "draws": ADDED_DRAWS, "threshold": "2%", "sets": {}}
    for i, (name, (tr, cl)) in enumerate({HEADLINE_SET: (keep(treated), keep(clean)), "every_cohort_utility": (treated, clean)}.items()):
        tr, _d = simulation_hosts(tr, cl, q, regions, fuel, dd, rules, ownership, usable, gas, unknown, 0.02)
        real = real_hosts(tr, q, regions, fuel, usable)
        p = prices.merge(cl, on=KEY).merge(q[KEY + ["year", "meets_size_floor"]], on=KEY + ["year"])
        p = outcome_rows(p, usable).assign(log_price=lambda d: np.log(d.res_price))
        unit_code = {k: j for j, k in enumerate(map(tuple, cl.values))}
        state_code = {st: j for j, st in enumerate(sorted(cl.state.unique()))}
        windows = build_windows(sorted(real.cohort.unique()), p, q, regions, fuel, dd, unit_code, state_code)
        excluded = None if rules.ownership == "off" else Exclusions(windows, ownership, ownership_classes(q), rules.ownership == "affiliates_readmitted")
        ctx = {"real": real, "windows": windows, "n_units": len(unit_code), "boot": BOOT, "excluded": excluded,
               "fuel_control": rules.fuel_control, "gas": gas}
        z = pd.DataFrame([r for part in _run(_shortcut_chunk, ctx, _chunks((SEED_D38, 100 + i), ADDED_DRAWS), workers) for r in part])
        added["sets"][name] = {
            "range_half_width_mean_pct": {"full_bootstrap": round(100 * float(z.full_half.mean()), 3), "shortcut": round(100 * float(z.short_half.mean()), 3)},
            "shortcut_width_over_full_width_mean": round(float((z.short_half / z.full_half).mean()), 3),
            "range_covers_zero": {"full_bootstrap": round(float(z.full_covers.mean()), 3), "shortcut": round(float(z.short_covers.mean()), 3)},
            "early_years_test_fails_at_p_below_0.10": {"full_bootstrap": round(float(((z.full_p < PRETEST_FAILS) | failed(z, "full_failure")).mean()), 3),
                                                       "shortcut": round(float(((z.short_p < PRETEST_FAILS) | failed(z, "short_failure")).mean()), 3)},
            "numerical_failures": {"full_bootstrap": failure_summary(z, "full_failure"), "shortcut": failure_summary(z, "short_failure")}}
        print(name, added["sets"][name], flush=True)
    added["rules"] = rules.label
    report["added_after_the_first_run"] = {"full_bootstrap_against_the_shortcut": added}
    write_report(report, rules, AS_BUILT)
    return 0


def main() -> int:
    if "--added" in sys.argv:
        return run_added()
    from pipeline.analysis import misdating
    from pipeline.analysis import simulation_access_list as sal
    procedure = procedure_from_argv(sys.argv)    # C, the selected procedure, unless the labelled run --procedure=A
    provenance = selected_procedure() if procedure == SELECTED else as_built_provenance()   # stops in words before any read
    q = panel.load_quantities()
    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    regions = market_region.by_unit_year(q)
    fuel, dd = load_controls()
    workers = max(1, min(10, (os.cpu_count() or 2) - 2))
    rules = rules_from_argv(sys.argv)            # the headline rules unless a labelled variant is named (step D)
    ownership, usable, gas = rule_inputs(rules, q)
    unknown = load_unknown_load()                # stops in words on a rebuilt inventory without its file (D-96)
    rk = {"rules": rules, "ownership": ownership, "usable": usable, "gas": gas, "unknown_load": unknown,
          "procedure": procedure, "provenance": provenance}
    run_id = 0                                   # each configuration gets its own stream of seeds: (seed, configuration, chunk)
    report = {
        "what_this_is": "Stand-ins drawn from never-host utilities take the real hosts' places, states and first-crossing years; "
                        "the specification in PREANALYSIS.md is run on each draw, read with the inference procedure named in "
                        "`procedure`. Only never-host utilities' prices are read, one file per utility, through the access list.",
        "procedure": provenance,
        "standard": "docs/DECISIONS.md, D-38, committed before this was run.",
        "not_in_the_simulation": [
            "future hosts as a second comparison group",
            "each sub-experiment uses utilities observed in all ten of its years",
            "Callaway and Sant'Anna's estimator",
            "utilities in Alaska and Hawaii, which have no degree-day series",
        ],
        "rules": {"label": rules.label, "ownership": rules.ownership, "usable": rules.usable, "support": rules.support,
                  "fuel_control": rules.fuel_control, "unresolved_ownership": rules.unresolved_ownership},
        "access_list": sal.DESCRIPTION,
        "readings_adopted": READINGS_ADOPTED,
        "gas_share_assumption": GAS_ASSUMPTION if rules.fuel_control == GAS_SHARE else None,
        "ownership_assumption": "municipal systems, public power districts and distribution cooperatives with no row in the "
                                "ownership table are each taken as their own owner, from EIA's ownership class (D-58 rule 2.2)",
        "seed": SEED_D38, "draws": DRAWS, "bootstrap_replications": BOOT if procedure == AS_BUILT else None,
        "planted_effects_pct": list(TAUS_PCT),
        "new_host_estimate": {}, "early_years_test_size_on_made_up_prices": {}, "side_runs": {}, "per_point_of_load": {},
    }
    as_sets = lambda t, c, aside: (t[[k not in aside for k in zip(t.utility_id_eia, t.state)]],  # noqa: E731
                                   c[[k not in aside for k in zip(c.utility_id_eia, c.state)]])
    for theta in (0.02, 0.05):
        treated, clean = design(q, dose, theta, history_settled(theta))
        clean, off_list = restrict_to_access_list(clean)          # only units on the committed access list (section 9)
        report.setdefault("comparison_units_left_out_by_the_access_list", {})[f"{theta:.0%}"] = off_list
        host_errs = misdating.host_errors(theta)
        prices = read_listed_outcomes(clean)[KEY + ["year", "res_price"]]
        sets = {HEADLINE_SET: as_sets(treated, clean, set_aside(theta)), "every_cohort_utility": (treated, clean)}
        if theta == 0.02:
            sets[TEN_YEAR_SET] = as_sets(treated, clean, set_aside(theta, ten_year_case=True))
        t = f"{theta:.0%}"
        report["new_host_estimate"][t] = {}
        for name, (tr, cl) in sets.items():
            run_id += 1
            report["new_host_estimate"][t][name] = run_new_hosts(f"{t} {name}", tr, cl, q, regions, fuel, dd, prices, host_errs,
                                                                 (SEED_D38, run_id), workers=workers, theta=theta, **rk)
        if theta == 0.02:
            for name, (tr, cl) in sets.items():
                run_id += 1
                report["early_years_test_size_on_made_up_prices"][name] = run_size_check(
                    f"{t} {name}", tr, cl, q, regions, fuel, dd, (SEED_D38, run_id), workers=workers, theta=theta, **rk)
            for name in (HEADLINE_SET, "every_cohort_utility"):
                tr, cl = sets[name]
                run_id += 1
                report["side_runs"][f"comparison_utilities_from_the_hosts_own_state_{name}"] = run_new_hosts(
                    f"{t} {name}", tr, cl, q, regions, fuel, dd, prices, host_errs, (SEED_D38, run_id), form="same_state", workers=workers, theta=theta, **rk)
            run_id += 1
            report["per_point_of_load"] = run_second_number(q, dose, clean, regions, prices, (SEED_D38, run_id), workers=workers, usable=usable,
                                                            unknown_load=unknown)
        write_report(report, rules, procedure)
    return 0


if __name__ == "__main__":
    # Run as a file, this module would exist twice: as __main__, and as pipeline.analysis.power_simulation, which design,
    # candidates and inference_check import. An object one copy makes (UnknownLoad, Rules, Exclusions) then fails the
    # other copy's isinstance and equality checks: the first real run under C stopped in design.build_with_rules for
    # exactly that reason, with unknown_load supplied. Everything runs in the one module the others import.
    from pipeline.analysis import power_simulation as _the_module
    sys.exit(_the_module.main())
