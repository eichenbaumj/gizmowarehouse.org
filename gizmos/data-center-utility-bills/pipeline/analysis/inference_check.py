#!/usr/bin/env python3
"""Job U: the early-years test and the range on the design that will be run, with made-up outcomes.

Reads NO price. The standard is docs/DECISIONS.md, D-49, written and committed before this was run.

Part 1. The actual hosts of a set, their real matched comparison utilities, regions year by year,
fuel-mix groups and degree days (pipeline/analysis/design.py); the plan's estimator and its wild
cluster bootstrap (estimator.py). The outcome is made up afresh for every dataset from one of seven
price processes fixed in D-49, none with any effect in it. Reported: how often a flat history fails
the early-years test, how often the 90% range misses zero, the same for the analytic clustered
interval and the chi-square reading, and the test's power against a pre-trend of a stated size.

Part 2. Each host's and each event year's implied weight in the headline number, and inferred regions.
Part 3. Each utility's leverage on the per-point slope of the second number.

Run:  python3 -I pipeline/analysis/inference_check.py            (as a file: it starts worker processes)
      python3 -I pipeline/analysis/inference_check.py --quantities-only     parts 2 and 3 alone
Output: data/frozen/inference_check.json, design_weights.csv, second_number_leverage.csv
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from pipeline.analysis import design, estimator  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
KEY = ps.KEY
SEED = 20261114
DATASETS = 2000
BAND = (0.07, 0.13)                       # D-38's band, kept by D-49
FIRST_YEAR, LAST_YEAR = 2001, 2025
OWNERSHIP = ("investor_owned", "public", "cooperative")
BASE = {"region_step_sd": 0.03, "state_sd": 0.015, "state_rho": 0.6, "own_sd": 0.03, "own_rho": 0.7}
GRID = {
    "G0_as_in_D38": {**BASE},
    "G1_unequal_variances": {**BASE, "own_scale_sd": 0.5},
    "G2_more_persistence": {**BASE, "own_rho": 0.95, "state_rho": 0.9},
    "G3_less_persistence": {**BASE, "own_rho": 0.2, "state_rho": 0.2},
    "G4_rate_case_steps": {**BASE, "steps": {"prob": 0.25, "mean": 0.03, "sd": 0.04, "noise_sd": 0.01}},
    "G5_shocks_common_across_states": {**BASE, "ownership_step_sd": 0.02},
    "G6_all_of_it": {**BASE, "own_scale_sd": 0.5, "steps": {"prob": 0.25, "mean": 0.03, "sd": 0.04, "noise_sd": 0.01},
                     "ownership_step_sd": 0.02, "state_rho": 0.9},
}
TRENDS = (0.005, 0.01)                     # a host's drift away from its comparison utilities, per year
TREND_VERSIONS = ("G0_as_in_D38", "G6_all_of_it")
TREND_PATH = np.array([e - ps.REF for e in ps.EVENT_TIMES], dtype=float)   # years past the reference year


def made_up(region_all: np.ndarray, state_all: np.ndarray, owner_all: np.ndarray, rng: np.random.Generator, dgp: dict) -> np.ndarray:
    """Units by years (2001 to 2025) log prices with levels, shocks and noise and no effect of anything.

    Two optional keys serve step E's added processes (docs/DECISIONS.md D-59 rule 4.2; inference_comparison.py). Neither
    changes a draw of G0 to G6 when absent: `own_scale_fixed` (one number a unit, fixed across datasets) multiplies the
    utility's own noise and draws nothing (G7); `region_loading_sd` draws each utility's loading on its region's walk,
    1 + sd * z, AFTER every other draw of this function (G9).
    """
    n, years = region_all.shape

    def ar1(rows, rho, sd):
        e = rng.normal(0, 1.0, (rows, years))
        for t in range(1, years):
            e[:, t] += rho * e[:, t - 1]
        return e * (sd if np.isscalar(sd) else np.asarray(sd)[:, None])

    region = rng.normal(0, dgp["region_step_sd"], (int(region_all.max()) + 1, years)).cumsum(1)
    state = ar1(int(state_all.max()) + 1, dgp["state_rho"], dgp["state_sd"])
    scale = np.exp(rng.normal(0, dgp["own_scale_sd"], n)) if dgp.get("own_scale_sd") else np.ones(n)
    if dgp.get("own_scale_fixed") is not None:
        scale = scale * np.asarray(dgp["own_scale_fixed"], dtype=float)
    if dgp.get("steps"):
        st = dgp["steps"]
        jumps = (rng.random((n, years)) < st["prob"]) * rng.normal(st["mean"], st["sd"], (n, years))
        own = (jumps.cumsum(1) + rng.normal(0, st["noise_sd"], (n, years))) * scale[:, None]
    else:
        own = ar1(n, dgp["own_rho"], dgp["own_sd"] * scale)
    regional = region[region_all, np.arange(years)[None, :]]
    out = rng.normal(2.4, 0.2, (n, 1)) + regional + state[state_all] + own
    if dgp.get("ownership_step_sd"):
        walk = rng.normal(0, dgp["ownership_step_sd"], (len(OWNERSHIP) + 1, years)).cumsum(1)
        out = out + walk[owner_all]
    if dgp.get("region_loading_sd"):
        out = out + (dgp["region_loading_sd"] * rng.normal(0, 1.0, n))[:, None] * regional     # loading 1 + sd * z
    return out


def fixed_parts(d: design.Design, fuel_control: str = ps.GAS_SHARE) -> dict:
    """Everything about the regression that does not change from one made-up dataset to the next.

    The regressors are assembled under `fuel_control` (the gas-share control by default from step D, D-59 item 7; the
    categorical and no-fuel forms are the labelled sensitivities). `combo` is the headline as a combination of however
    many columns that gives, and `projection` the fixed effects' projection, reused by each dataset's fit.
    """
    blocks = d.blocks()
    for w in d.windows.values():
        w.y = np.zeros((len(w.keys), ps.T))
    a = ps.assemble(d.windows, blocks, fuel_control=fuel_control, gas=d.gas)
    obs_unit, obs_year = [], []
    for g, tr, comp in blocks:
        w = d.windows[g]
        rows = np.concatenate([tr, comp])
        obs_unit.append(np.repeat(w.unit[rows], ps.T))
        obs_year.append(np.tile(np.arange(g - ps.PRE, g + ps.POST + 1) - FIRST_YEAR, len(rows)))
    K = len(ps.EVENT_TIMES)
    trend = a["X"][:, :K] @ TREND_PATH                      # the host indicator times years past the reference year
    return {"X": a["X"], "groups": a["groups"], "cluster": a["cluster"], "trend": trend,
            "obs_unit": np.concatenate(obs_unit), "obs_year": np.concatenate(obs_year), "combo": ps.headline_combo(a["X"].shape[1]),
            "columns": a["columns"], "control_columns_left_out": a["control_columns_left_out"], "fuel_control": a["fuel_control"],
            "projection": a["projection"], "ramp": a["paths"][:, 0]}       # ramp: the planted path dated exactly (step E's power)


def unit_arrays(d: design.Design, regions: pd.DataFrame, q: pd.DataFrame) -> dict:
    """Each unit's region code by year, its state code and its ownership code, for the price process."""
    codes = {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}
    idx = pd.MultiIndex.from_tuples(list(d.unit_code))
    region_all = ps.region_matrix(regions, idx, range(FIRST_YEAR, LAST_YEAR + 1), codes)
    region_all = np.where(np.isnan(region_all), 0, region_all).astype(int)
    state_all = np.array([d.state_code[k[1]] for k in d.unit_code])
    own = q.groupby(KEY).ownership.last()
    owner_all = np.array([OWNERSHIP.index(own.get(k)) if own.get(k) in OWNERSHIP else len(OWNERSHIP) for k in d.unit_code])
    return {"region_all": region_all, "state_all": state_all, "owner_all": owner_all}


def read_dataset(fit: estimator.Fit, v: np.ndarray, trends=(), combo: np.ndarray | None = None) -> dict:
    """One made-up dataset's results: flat, and with each pre-trend planted on the hosts.

    `numerical_failure` (the bootstrap readings) and `analytic_failure` (the analytic and chi-square readings) carry a
    cause when the dataset failed (D-95 section 3 item 7; E4.1); the failed readings are NaN and summarise() counts them.
    """
    combo = ps.headline_combo(fit.K) if combo is None else combo
    z = fit.summary(v, combo, ps.PRE_IDX)
    crit = float(stats.t.ppf((1 + ps.LEVEL) / 2, fit.G - 1))
    analytic_ok = not z["analytic_failure"]
    out = {"est": z["est"], "se": z["se"], "lo": z["lo"], "hi": z["hi"],
           "lo_analytic": z["est"] - crit * z["se"] if analytic_ok else np.nan, "hi_analytic": z["est"] + crit * z["se"] if analytic_ok else np.nan,
           "pre_wald": z["pre_wald"], "pre_p": z["pre_p_bootstrap"],
           "pre_p_chi2": float(stats.chi2.sf(z["pre_wald"], len(ps.EARLY))) if analytic_ok else np.nan, "clusters": fit.G,
           "numerical_failure": z["numerical_failure"], "analytic_failure": z["analytic_failure"]}
    for delta in trends:
        t = fit.summary(v, combo, ps.PRE_IDX, path=0, tau=delta)
        out[f"trend_{delta}_pre_p"] = t["pre_p_bootstrap"]
        out[f"trend_{delta}_pre_p_chi2"] = float(stats.chi2.sf(t["pre_wald"], len(ps.EARLY))) if not t["analytic_failure"] else np.nan
        out[f"trend_{delta}_est"] = t["est"]
        out[f"trend_{delta}_failure"] = t["numerical_failure"]
    return out


def fit_dataset(y: np.ndarray, f: dict, rng: np.random.Generator, boot: int, trends=()) -> dict:
    """Fit one made-up dataset on the fixed parts and read it. A fit that raises RankDeficient is recorded as a failed
    dataset with its cause, kept in the denominator (D-95 item 7); it is never skipped."""
    try:
        fit = estimator.Fit(y, f["X"], f["groups"], f["cluster"], f["trend"][:, None], projection=f.get("projection"))
    except estimator.RankDeficient as e:
        out = {k: np.nan for k in ("est", "se", "lo", "hi", "lo_analytic", "hi_analytic", "pre_wald", "pre_p", "pre_p_chi2")}
        out.update(clusters=int(len(np.unique(f["cluster"]))), numerical_failure=estimator.RANK_DEFICIENT,
                   analytic_failure=estimator.RANK_DEFICIENT, failure_detail=str(e))
        for delta in trends:
            out.update({f"trend_{delta}_pre_p": np.nan, f"trend_{delta}_pre_p_chi2": np.nan, f"trend_{delta}_est": np.nan,
                        f"trend_{delta}_failure": estimator.RANK_DEFICIENT})
        return out
    return read_dataset(fit, estimator.rademacher(rng, boot, fit.G), trends, f.get("combo"))


def _chunk(args) -> list:
    seed, n = args
    rng = np.random.default_rng(list(seed))
    c = ps._CTX
    f, out = c["fixed"], []
    for _ in range(n):
        P = made_up(c["region_all"], c["state_all"], c["owner_all"], rng, c["dgp"])
        y = P[f["obs_unit"], f["obs_year"]]
        out.append(fit_dataset(y, f, rng, c["boot"], c["trends"]))
    return out


def rate(hits: np.ndarray) -> dict:
    """A share of datasets with its Monte Carlo standard error and 95% interval."""
    n, p = len(hits), float(np.mean(hits))
    se = float(np.sqrt(p * (1 - p) / n))
    return {"share": round(p, 4), "monte_carlo_se": round(se, 4), "interval_95": [round(max(0.0, p - 1.96 * se), 4), round(min(1.0, p + 1.96 * se), 4)],
            "inside_the_band": bool(BAND[0] <= p <= BAND[1])}


def summarise(z: pd.DataFrame, trends=()) -> dict:
    """Rates over every dataset. A failed dataset (D-95 section 3 item 7; E4.1) stays in the denominator: it counts as a
    rejection of a flat history and as a range that misses zero. Under a planted pre-trend, a failed dataset counts as
    no detection (against the procedure). Failure counts and causes are reported apart (E4.3); moments are over the
    datasets that computed, and say so."""
    bad, bad_a = ps.failed(z), ps.failed(z, "analytic_failure")
    out = {"datasets": int(len(z)), "states": int(z.clusters.median()),
           "numerical_failures": {"bootstrap": ps.failure_summary(z), "analytic": ps.failure_summary(z, "analytic_failure")},
           "rates_include_numerical_failures": True,
           "early_years_test_fails_a_flat_history": {
               "bootstrap_p_below_0.10": rate((z.pre_p < 0.10) | bad), "bootstrap_p_below_0.05": rate((z.pre_p < 0.05) | bad),
               "chi_square_p_below_0.10": rate((z.pre_p_chi2 < 0.10) | bad_a), "chi_square_p_below_0.05": rate((z.pre_p_chi2 < 0.05) | bad_a)},
           "range_misses_zero_nominal_10pct": {
               "bootstrap": rate((z.lo > 0) | (z.hi < 0) | bad), "analytic_clustered_t": rate((z.lo_analytic > 0) | (z.hi_analytic < 0) | bad_a)},
           "moments_are_over": "datasets without a numerical failure",
           "mean_estimate_pct": round(100 * float(z.est.mean()), 3), "sd_of_estimates_pct": round(100 * float(z.est.std()), 3),
           "range_half_width_mean_pct": {"bootstrap": round(100 * float((z.hi - z.lo).mean() / 2), 3),
                                         "analytic_clustered_t": round(100 * float((z.hi_analytic - z.lo_analytic).mean() / 2), 3)}}
    for delta in trends:
        tb = ps.failed(z, f"trend_{delta}_failure")
        out[f"with_a_pre_trend_of_{100 * delta:g}pct_a_year"] = {
            "early_years_test_fails": {"bootstrap_p_below_0.10": rate((z[f"trend_{delta}_pre_p"] < 0.10) & ~tb),
                                       "chi_square_p_below_0.10": rate((z[f"trend_{delta}_pre_p_chi2"] < 0.10) & ~bad_a)},
            "numerical_failures_counted_as_no_detection": ps.failure_summary(z, f"trend_{delta}_failure"),
            "mean_headline_estimate_pct": round(100 * float(z[f"trend_{delta}_est"].mean()), 3),
            "bias_the_trend_puts_in_the_headline_pct": round(100 * delta * 5.5, 3)}
    for d in out.values():
        if isinstance(d, dict):
            for r in d.values():
                if isinstance(r, dict) and "inside_the_band" in r and "pre_trend" in str(d):
                    r.pop("inside_the_band", None)
    return out


# ---- part 2: implied weights -------------------------------------------------------------------

def implied_weights(d: design.Design, fuel_control: str = ps.GAS_SHARE) -> pd.DataFrame:
    """The headline number's weight on every utility-year, from the regressors alone, after all controls.

    The estimate is combo'b with b = (X~'X~)^-1 X~'y, X~ the regressors after the fixed effects and
    controls are taken out, so it equals w'y with w = X~ (X~'X~)^-1 combo. No outcome enters.
    """
    f = fixed_parts(d, fuel_control)
    Xt = (f["projection"] or estimator.Projection(f["groups"]))(f["X"])
    estimator.check_rank(Xt, f["X"])                        # an explicit failure, never weights from an unstable inverse (D-59)
    w = Xt @ (np.linalg.inv(Xt.T @ Xt) @ f["combo"])
    rows, i = [], 0
    for b, (g, tr, comp) in enumerate(d.blocks()):
        win = d.windows[g]
        for j, r in enumerate(np.concatenate([tr, comp])):
            for t in range(ps.T):
                rows.append({"block_host": win.keys[tr[0]], "cohort": g, "utility": win.keys[r], "is_host": j < len(tr),
                             "event_year": t - ps.PRE, "weight": float(w[i])})
                i += 1
    return pd.DataFrame(rows)


def absorbed_hosts(d: design.Design, fuel_control: str = ps.GAS_SHARE, tol: float = estimator.RANK_TOLERANCE) -> list:
    """Hosts whose rows are fully absorbed, by label, decided from the regressors alone and whether or not the fit as a
    whole can be computed (D-59 item 7: "every host that is fully absorbed, by name").

    A host is fully absorbed when the event-time columns restricted to its own rows are, once the fixed effects are
    removed, a linear combination of the control columns: what is left of them is no more than `tol` times what there
    was (largest singular values). Such a host contributes nothing to the estimate. When the fit can be computed this
    agrees with a zero headline weight; when it cannot, it names the hosts that made it so.
    """
    f = fixed_parts(d, fuel_control)
    K = len(ps.EVENT_TIMES)
    proj = f["projection"] or estimator.Projection(f["groups"])
    controls = proj(f["X"][:, K:])
    out, start = [], 0
    for b, (g, tr, comp) in enumerate(d.blocks()):
        n = (len(tr) + len(comp)) * ps.T
        own = np.zeros((len(f["X"]), K))
        own[start:start + len(tr) * ps.T] = f["X"][start:start + len(tr) * ps.T, :K]
        start += n
        raw = float(np.linalg.svd(own, compute_uv=False).max()) if own.any() else 0.0
        if raw == 0.0:
            continue
        t = proj(own)
        if controls.shape[1]:
            t = t - controls @ np.linalg.lstsq(controls, t, rcond=None)[0]
        left = float(np.linalg.svd(t, compute_uv=False).max())
        if left <= tol * raw:
            key = d.windows[g].keys[tr[0]]
            out.append(f"{int(key[0])}:{key[1]}")
    return out


def net_weights(wt: pd.DataFrame) -> pd.DataFrame:
    """Each comparison utility's weight on the headline number, measured two ways (D-55; D-56, ruling 7).

    A comparison utility matched to several hosts has one copy of each of its years per host. The headline
    number's loading on one observed outcome (a utility in a calendar year) is the SIGNED sum of its copies.
      net_weight                 signed weights summed by utility and calendar year, then magnitudes summed over years
      sum_of_absolute_row_weights  magnitudes taken copy by copy and summed (what D-53 reported; it counts copies
                                 that offset one another as if they added)
    The calendar year of a row is its cohort plus its event year.
    """
    comp = wt[~wt.is_host].assign(year=lambda x: x.cohort + x.event_year, a=lambda x: x.weight.abs())
    net = comp.groupby(["utility", "year"]).weight.sum().abs().groupby("utility").sum().rename("net_weight")
    rows = comp.groupby("utility").agg(sum_of_absolute_row_weights=("a", "sum"), hosts_matched_to=("block_host", "nunique"))
    return rows.join(net).sort_values("net_weight", ascending=False)


def fuel_mix_cells(d: design.Design) -> pd.DataFrame:
    """Per host: who shares its cohort's fuel-mix-group-by-year cells (D-57, the trace of Cheyenne Light's zero weight).

    The fit has cohort-by-fuel-mix-group-by-year effects (ps.assemble). A host whose cohort has no other row in
    its state's fuel-mix group has those effects fit its ten rows exactly, and its outcome carries no weight. A host
    whose only other rows in the cell are a few of its own matches is in effect compared with those few. This
    counts rows; it changes nothing in the fit.
    """
    rec = []
    for g, tr, comp in d.blocks():
        w = d.windows[g]
        for j, r in enumerate(np.concatenate([tr, comp])):
            rec.append((g, int(w.fuel[r]), w.keys[tr[0]], w.keys[r], j < len(tr)))
    rec = pd.DataFrame(rec, columns=["cohort", "fuel", "block_host", "utility", "is_host"])
    out = []
    for h in d.hosts.itertuples():
        f = int(d.windows[h.cohort].fuel[h.row])
        cell = rec[(rec.cohort == h.cohort) & (rec.fuel == f)]
        others = cell[~(cell.is_host & (cell.utility == h.key))]
        mine = others[(others.block_host == h.key) & ~others.is_host]
        out.append({"utility": h.key, "cohort": int(h.cohort), "fuel_mix_group": f,
                    "other_rows_in_its_cohort_and_fuel_mix_group": int(len(others)),
                    "of_them_its_own_matches": int(len(mine)), "of_them_other_hosts": int(others.is_host.sum()),
                    "its_own_matches_in_that_group": [k for k in mine.utility]})
    return pd.DataFrame(out)


def weights_report(wt: pd.DataFrame, names: pd.Series, cells: pd.DataFrame | None = None) -> dict:
    head = wt[wt.is_host & wt.event_year.isin(ps.HEADLINE)]
    by_host = head.groupby("utility").weight.sum().sort_values(ascending=False)
    by_comp = net_weights(wt)
    by_abs = by_comp.sort_values("sum_of_absolute_row_weights", ascending=False)
    name = lambda k: names.get(k)  # noqa: E731
    label = lambda k: f"{k[0]}:{k[1]}"  # noqa: E731
    row = lambda k, r: {"utility": label(k), "name": name(k), "net_weight": round(float(r.net_weight), 4),  # noqa: E731
                        "sum_of_absolute_row_weights": round(float(r.sum_of_absolute_row_weights), 4), "hosts_matched_to": int(r.hosts_matched_to)}
    out = {
        "hosts": int(len(by_host)), "host_weights_sum_to": round(float(by_host.sum()), 6),
        "an_equal_weight_would_be": round(1.0 / len(by_host), 4) if len(by_host) else None,
        "largest": [{"utility": label(k), "name": name(k), "weight": round(float(v), 4)} for k, v in by_host.head(5).items()],
        "smallest": [{"utility": label(k), "name": name(k), "weight": round(float(v), 4)} for k, v in by_host.tail(5).items()],
        "effective_number_of_hosts": round(float(by_host.sum() ** 2 / (by_host ** 2).sum()), 2) if len(by_host) else None,
        "hosts_whose_weight_is_zero": [name(k) for k, v in by_host.items() if abs(v) < 1e-9],
        "by_host": {label(k): round(float(v), 4) for k, v in by_host.items()},
        "by_event_year_on_host_rows": {str(int(e)): round(float(v), 4) for e, v in wt[wt.is_host].groupby("event_year").weight.sum().items()},
        "comparison_utilities_in_the_fit": int(by_comp.shape[0]),
        "comparison_utilities_matched_to_more_than_one_host": int((by_comp.hosts_matched_to > 1).sum()),
        "which_weight_is_which": {
            "net_weight": "signed weights summed by utility-state and calendar year across every host's stack, then magnitudes summed over "
                          "years: the headline number's loading on that utility's observed outcomes (D-55; D-56, ruling 7)",
            "sum_of_absolute_row_weights": "magnitudes taken stack row by stack row and summed: the figure D-53 reported as 'absolute weight'. "
                                           "It counts a utility-year once per host it is matched to, so copies that offset still add"},
        "comparison_utilities_carrying_the_most_net_weight": [row(k, r) for k, r in by_comp.head(8).iterrows()],
        "comparison_utilities_with_the_largest_sum_of_absolute_row_weights": [row(k, r) for k, r in by_abs.head(8).iterrows()]}
    if cells is not None and len(cells):
        out["fuel_mix_cells"] = {
            "what_this_is": "For each host, the other rows in its cohort's fuel-mix-group-by-year cells. With none, those effects fit the host's "
                            "rows exactly and its weight is zero; with only a few of its own matches there, it is in effect compared with those few (D-57)",
            "hosts_alone_in_their_cell": [name(k) for k in cells[cells.other_rows_in_its_cohort_and_fuel_mix_group == 0].utility],
            "by_host": [{"utility": label(r.utility), "name": name(r.utility), "cohort": r.cohort, "fuel_mix_group": r.fuel_mix_group,
                         "other_rows_in_its_cohort_and_fuel_mix_group": r.other_rows_in_its_cohort_and_fuel_mix_group,
                         "of_them_its_own_matches": r.of_them_its_own_matches, "of_them_other_hosts": r.of_them_other_hosts,
                         "its_own_matches_in_that_group": [name(k) for k in r.its_own_matches_in_that_group]}
                        for r in cells.sort_values("other_rows_in_its_cohort_and_fuel_mix_group").itertuples()]}
    return out


def inferred_regions(d: design.Design, regions: pd.DataFrame, names: pd.Series) -> list:
    """Per host: window years before 2013 (region from the sourced table, not EIA's code), zone placements, and matches that change region."""
    zones = pd.read_csv(ROOT / "pipeline" / "electricity" / "pjm_late_zones.csv")
    zoned = set(zip(zones.utility_id_eia.astype(int), zones.state)) if {"utility_id_eia", "state"} <= set(zones.columns) else set()
    out = []
    for h in d.hosts.itertuples():
        w = d.windows[h.cohort]
        years = np.arange(h.cohort - ps.PRE, h.cohort + ps.POST + 1)
        rows = np.concatenate([[h.row], np.array(h.matches, dtype=int)])
        rt = w.region_t[rows]
        out.append({"utility": f"{h.key[0]}:{h.key[1]}", "name": names.get(h.key), "cohort": int(h.cohort),
                    "window_years_before_2013": int((years < 2013).sum()),
                    "utility_years_in_its_cells_with_a_region_from_the_sourced_table": int((years < 2013).sum() * len(rows)),
                    "of_its_utilities_how_many_are_placed_in_the_ohio_and_pennsylvania_zones": int(sum(w.keys[r] in zoned for r in rows)),
                    "matched_utilities_that_change_region_in_the_window": int((rt[1:].min(1) != rt[1:].max(1)).sum()),
                    "host_changes_region_in_the_window": bool(rt[0].min() != rt[0].max())})
    return out


# ---- part 3: leverage in the second number -----------------------------------------------------

def second_number_leverage(q: pd.DataFrame, dose: pd.DataFrame, regions: pd.DataFrame, unknown_load=None) -> tuple[dict, pd.DataFrame]:
    """Each utility's share of the variation in the change in load share left after the cell effects are removed.

    A utility a load-unknown site reaches has no settled dose (D-96): it is left out of the sample, no change in load
    share is computed for it, and it is named as carried to step F (`unknown_load`, ps.load_unknown_load(); required).
    """
    unknown_load = ps.require_unknown_load(unknown_load)
    names = q.groupby(KEY).utility_name.last()
    years = list(ps.LONG_PRE + ps.LONG_POST)
    ok = q[q.meets_size_floor & (q.res_mwh > 0) & q.year.isin(years)]
    have = ok.groupby(KEY).size()
    candidates = [k for k, n in have.items() if n == len(years)]
    units = [k for k in candidates if (int(k[0]), k[1]) not in unknown_load.affected]
    carried = sorted(f"{int(k[0])}:{k[1]}" for k in candidates if (int(k[0]), k[1]) in unknown_load.affected)
    reg = regions.set_index(KEY + ["year"]).region
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    D = dose.pivot_table(index=KEY, columns="year", values="dose").reindex(columns=range(2001, 2026)).fillna(0.0) * 100.0
    rows = []
    for k in units:
        r0, r1 = reg.get(k + (ps.LONG_REGION_YEARS[0],)), reg.get(k + (ps.LONG_REGION_YEARS[1],))
        size = cust.loc[k, ps.LONG_PRE[-1]] if k in cust.index else np.nan
        if pd.isna(r0) or pd.isna(r1) or not size > 0:
            continue
        x = D.loc[k] if k in D.index else pd.Series(0.0, index=D.columns)
        rows.append({"utility_id_eia": k[0], "state": k[1], "name": names.get(k), "cell": f"{r0}|{r1}|{int(ps.size_band([size])[0])}",
                     "pre": {c: float(np.minimum(x[list(ps.LONG_PRE)], c if c else np.inf).mean()) for c in (25.0, 50.0, 0.0)},
                     "post": {c: float(np.minimum(x[list(ps.LONG_POST)], c if c else np.inf).mean()) for c in (25.0, 50.0, 0.0)}})
    t = pd.DataFrame(rows)
    out, table = {"utilities_in_the_sample": int(len(t)), "with_any_change_in_load_share": None,
                  "carried_to_step_f": carried, "carried_to_step_f_why": ps.LOAD_UNKNOWN}, t[["utility_id_eia", "state", "name", "cell"]].copy()
    for cap, label in ((25.0, "capped_at_25_points"), (50.0, "capped_at_50_points"), (0.0, "uncapped")):
        dx = t.post.map(lambda v: v[cap]) - t.pre.map(lambda v: v[cap])
        xt = dx - dx.groupby(t.cell).transform("mean")
        lev = xt ** 2 / float((xt ** 2).sum())
        raw = (dx - dx.mean()) ** 2
        table[f"change_in_load_share_{label}"] = dx.round(4)
        table[f"leverage_{label}"] = lev.round(6)
        top = lev.sort_values(ascending=False)
        out[label] = {"three_largest_shares_of_leverage": round(float(top.head(3).sum()), 4), "ten_largest": round(float(top.head(10).sum()), 4),
                      "the_three": [{"name": t.name[i], "state": t.state[i], "leverage": round(float(top[i]), 4),
                                     "change_in_load_share_points": round(float(dx[i]), 2)} for i in top.head(3).index],
                      "raw_statistic_three_largest_squared_deviations_of_the_change": round(float(raw.sort_values(ascending=False).head(3).sum() / raw.sum()), 4),
                      "utilities_with_leverage_above_1pct": int((lev > 0.01).sum())}
        if out["with_any_change_in_load_share"] is None:
            out["with_any_change_in_load_share"] = int((dx.abs() > 0).sum())
    return out, table


def main() -> int:
    """Under the headline rules from step D (or a labelled variant: --rules=<label>), with a fingerprint per set."""
    quantities_only = "--quantities-only" in sys.argv
    sets = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--set=")] or list(design.SETS)
    rules = ps.rules_from_argv(sys.argv)
    q, dose, regions, fuel, dd = design.load()
    names = q.groupby(KEY).utility_name.last()
    ownership, usable, gas = ps.rule_inputs(rules, q)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()                  # stops in words on a rebuilt inventory without its file (D-96)
    workers = max(1, min(10, (os.cpu_count() or 2) - 2))
    path = ps.output_path("inference_check.json", rules)
    report = json.loads(path.read_text()) if path.exists() else {}
    report.update({"what_this_is": "Job U (docs/DECISIONS.md, D-49, committed before this was run): the early-years test and the range on the "
                                   "actual hosts with made-up outcomes, then weights, inferred regions and leverage. No price is read.",
                   "rules": {"label": rules.label, "ownership": rules.ownership, "usable": rules.usable, "support": rules.support,
                             "fuel_control": rules.fuel_control, "unresolved_ownership": rules.unresolved_ownership},
                   "gas_share_assumption": ps.GAS_ASSUMPTION if rules.fuel_control == ps.GAS_SHARE else None,
                   "seed": SEED, "datasets_per_cell": DATASETS, "bootstrap_replications": ps.BOOT, "band": list(BAND), "grid": GRID})
    report.setdefault("sets", {})
    all_weights = []
    for i, which in enumerate(sets):
        treated, clean = design.split(0.02, which, q, dose)
        d = design.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                                    ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
        entry = report["sets"].setdefault(which, {})
        entry.update({"hosts_in_the_set": int(len(treated)), "hosts_in_the_estimate": int(len(d.hosts)), "hosts_dropped": d.dropped,
                      "states_holding_a_host": int(d.hosts.state.nunique()) if len(d.hosts) else 0,
                      "host_names": [names.get(k) for k in d.hosts.key] if len(d.hosts) else [],
                      "load_unknown_excluded": d.load_unknown_excluded})
        if ownership is not None:
            units = [((int(u), st), "host") for u, st in zip(treated.utility_id_eia, treated.state)] + \
                    [((int(u), st), "comparison") for u, st in zip(clean.utility_id_eia, clean.state)]
            entry["investor_owned_units_with_no_ownership_row"] = design.investor_owned_without_rows(ownership, units, ownership_of, names)
        f = fixed_parts(d, rules.fuel_control)
        entry["regressors"] = {"columns": f["columns"], "control_columns_left_out": f["control_columns_left_out"], "fuel_control": f["fuel_control"]}
        entry["fully_absorbed_hosts"] = [names.get((int(x.split(":")[0]), x.split(":")[1])) or x for x in absorbed_hosts(d, rules.fuel_control)]
        if gas is not None and len(d.hosts):
            entry["gas_share_against_matches"] = design.gas_share_ranges(d, gas, names)
        try:
            wt = implied_weights(d, rules.fuel_control)
        except estimator.RankDeficient as e:              # reported in words; the fully absorbed hosts are named above
            entry["implied_weights"] = {"not_computed": str(e)}
            wt = None
        if wt is not None:
            entry["implied_weights"] = weights_report(wt, names, fuel_mix_cells(d))
            all_weights.append(wt.assign(set=which))
        entry["inferred_regions"] = inferred_regions(d, regions, names)
        entry["fingerprint"] = design.run_fingerprint(
            d, rules=rules, usable=usable, assumptions={"kind": "inference_check", "grid": GRID, "trends": list(TRENDS),
                                                        "trend_versions": list(TREND_VERSIONS), "datasets": DATASETS},
            settings={"bootstrap_replications": ps.BOOT, "level": ps.LEVEL, "band": list(BAND)}, seeds=[SEED, design.SETS.index(which)])
        if quantities_only or wt is None:
            continue
        ctx = {"fixed": fixed_parts(d, rules.fuel_control), **unit_arrays(d, regions, q), "boot": ps.BOOT}
        entry["made_up_prices"] = {}
        for j, (version, dgp) in enumerate(GRID.items()):
            trends = TRENDS if version in TREND_VERSIONS else ()
            parts = ps._run(_chunk, {**ctx, "dgp": dgp, "trends": trends}, ps._chunks((SEED, design.SETS.index(which), j), DATASETS), workers)
            z = pd.DataFrame([r for part in parts for r in part])
            entry["made_up_prices"][version] = summarise(z, trends)
            e = entry["made_up_prices"][version]
            print(f"  {which} {version}: early-years test fails {e['early_years_test_fails_a_flat_history']['bootstrap_p_below_0.10']['share']:.1%}, "
                  f"range misses zero {e['range_misses_zero_nominal_10pct']['bootstrap']['share']:.1%} "
                  f"(analytic {e['range_misses_zero_nominal_10pct']['analytic_clustered_t']['share']:.1%}); "
                  f"numerical failures {e['numerical_failures']['bootstrap']['count']}", flush=True)
            path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    lev, table = second_number_leverage(q, dose, regions, unknown)
    report["second_number_leverage"] = lev
    suffix = "" if rules == ps.HEADLINE_RULES else f"_{rules.label}"
    table.to_csv(FROZEN / f"second_number_leverage{suffix}.csv", index=False)
    if all_weights:
        w = pd.concat(all_weights, ignore_index=True)
        w["block_host"] = [f"{k[0]}:{k[1]}" for k in w.block_host]
        w["utility"] = [f"{k[0]}:{k[1]}" for k in w.utility]
        w.assign(weight=w.weight.round(8)).to_csv(FROZEN / f"design_weights{suffix}.csv", index=False)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
