#!/usr/bin/env python3
"""The customer-weighted fit (PREANALYSIS.md, Electricity: the main estimate, Weights: "The same estimate weighted by
each host's residential customers in its reference year is reported next to it and labelled"). A point estimate,
labelled descriptive, with NO range. Reads NO outcome: the outcome is an argument of `weighted_fit`.

Joe's ruling of 2026-11-19 (D-105), his words: "Accept the customer-weighted fit as descriptive, distinguishing nominal
customer weights from effective regression contributions."

The specification, as the session's brief for session 20 states it
------------------------------------------------------------------
Weighted least squares on the stacked sample. Every row of a host's sub-experiment (the host's rows and its matched
comparison utilities' rows in that stack) carries that host's residential customers in its reference year (cohort - 3)
as its weight. Reported as a point estimate labelled descriptive, with no range: the selected inference procedure has no
path that takes weights and was not validated with them.

What is reused, and what is new
-------------------------------
The regressors, fixed effects and clusters are the kernel's, by calling the function the kernel calls:
outcome_analysis.estimate stacks outcome_analysis.stackable(d) and calls inference_check.fixed_parts(stackable(d),
fuel_control); this module calls the same two functions and takes X (event-time columns on host rows, the two degree-day
columns, the gas-share-by-calendar-year columns kept by power_simulation.screen_controls), `groups` (utility effects and
block-by-region-by-year effects, and under the categorical fuel control the cohort-by-fuel-group-by-year effects),
`combo` (power_simulation.headline_combo: the mean of event years 2 and 3) and the row order (outcome_analysis.stacked_rows).
The outcome is aligned by the kernel's own guard (outcome_analysis._aligned): a vector built by outcome_vector for other
rows is refused. The rank test is estimator.check_rank, the shared estimator's. Nothing in candidates.py, estimator.py,
inference_check.py, influence.py, design.py or outcome_analysis.py is changed; the validated path's numbers do not move.

New here: the weighted problem. With W the diagonal of row weights (normalized to mean 1 before solving; least squares
is unchanged by a common scale), every column (y and X) is multiplied by sqrt(W), and the fixed effects are removed by
projecting off sqrt(W) D, D the indicator columns of every grouping, with the projection's pseudo-inverse taken once on
the small dense matrix (sqrt(W) D)'(sqrt(W) D) at relative cutoff 1e-10, the cutoff estimator.Projection uses. This is
the least-squares projection under the weights; the kernel's estimator.Projection is the same projection when every
weight is equal. Then b = (Xw' Xw)^-1 Xw' yw with Xw and yw the projected weighted columns, and the headline is combo'b.
With every weight equal it returns the kernel's unweighted point estimate (tested to 1e-10).

Two things are reported beside the estimate, under names that cannot be confused
--------------------------------------------------------------------------------
Their exact definitions are the constants NOMINAL_DEFINITION and EFFECTIVE_DEFINITION, written into every result and
into the summary file (Joe, 2026-11-19: "For customer-weighted shares, retain the calculations and clarify exactly what
'effective contribution' measures. No influence analysis is requested. Record that this clarification supersedes my
earlier phrase if needed."). No calculation was changed for that clarification; the definitions and the labels shown
beside the keys (NOMINAL_LABEL, EFFECTIVE_LABEL) were added. In short:
nominal_customer_weight_shares
    each stacked host's residential customers in its reference year over the sum across the stacked hosts. What the
    weights say before the regression.
effective_contributions_to_the_weighted_headline
    computed from the regressors and the weights alone, no outcome. The weighted headline is linear in the outcome:
    headline = omega'y with omega = W X~ (X~' W X~)^-1 combo, X~ the regressors with the fixed effects removed under the
    weights (in the code, omega = sqrt(W) Xw (Xw'Xw)^-1 combo). A host's effective contribution is the sum of omega over
    its OWN rows (the host's rows in its own sub-experiment, not its matches' rows) in event years 2 and 3, the two
    headline years. Because omega'X = combo', these sums add to exactly 1 over the stacked hosts (the event-time columns
    are the host-row indicators of each event year, and combo puts 1/2 on each headline year), so they can be read beside
    the nominal shares. With every weight equal, omega is inference_check.implied_weights' vector and each host's sum is
    outcome_analysis.host_weights' (tested to 1e-10). That the host's own rows in event years 2 and 3 are what is summed
    was accepted by Joe on 2026-11-19 (D-111), with this definition: it is the definition outcome_analysis.host_weights
    and influence.zero_weight_hosts already use for the unweighted fit; the brief says "the implied weight on its own
    treated rows".
    A host's contribution can be negative or exceed its nominal share: the regression's weight on a host depends on its
    stack's structure and on the controls shared across stacks, not on its customers alone.
    What it measures, exactly: if every outcome value on the host's own rows in event years 2 and 3 rose by the same
    amount c and nothing else changed, the weighted headline would rise by c times the host's effective contribution.
    It is not influence, not leverage and not the change in the estimate when the host is left out (EFFECTIVE_DEFINITION;
    tests/test_weighted_fit_invented.py plants a world in which it and a leave-one-out change rank the hosts differently).

The agent's readings (not stated by Joe's words or the plan)
------------------------------------------------------------
- The customers are `res_customers` in the quantities frame (data/interim/panel_quantities.parquet), for the host's own
  unit (utility_id_eia and state) in the cohort's reference year, cohort - 3.
- A host with no customer value in its reference year, or one that is not finite, or not above zero, is a failure in
  words and nothing is fitted: a zero weight would drop the host's stack silently, and no value is filled.
- Hosts with no matched comparison utility are not stacked (outcome_analysis.stackable); they carry no weight and no
  share and are named.

What is here
------------
customer_weights(d, customers)          {host label: residential customers in its reference year}, stacked hosts only
nominal_shares(weights)                 {host label: share of the customer weight}
row_weights(d, weights)                 the weight of every stacked row, in the kernel's row order
weighted_parts(d, weights, fuel_control=None)
                                        the kernel's regressors under the weights, projected, rank-tested
effective_contributions(d, weights, fuel_control=None)
                                        omega per row and summed per host (no outcome)
weighted_fit(d, y, weights, fuel_control=None)
                                        the weighted point estimate on the caller's outcome, with both readings beside it
main()                                  the quantity-only summary on the headline design at 2% as it stands, written to
                                        data/frozen/customer_weighted_fit_design.json (provisional)

Run:  python3 -I pipeline/analysis/weighted_fit.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import sparse  # noqa: E402

from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import estimator  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
CUSTOMERS = "res_customers"
OUT = ROOT / "data" / "frozen" / "customer_weighted_fit_design.json"
RCOND = 1e-10                       # estimator.Projection's pseudo-inverse cutoff

DESCRIPTIVE_LABEL = ("descriptive: the customer-weighted point estimate, with no range (the selected inference procedure "
                     "has no path that takes weights and was not validated with them; Joe, 2026-11-19, D-105)")
NO_RANGE = ("no range is reported: the selected procedure (CR2, Satterthwaite) was validated on the unweighted headline "
            "design and has no weighted path")
NO_VALIDATION = ("not applicable: a descriptive point estimate with no range, so no validation is claimed (None is kept "
                 "for the validated headline alone)")
# The two shares beside the weighted estimate (Joe, 2026-11-19: "clarify exactly what 'effective contribution' measures").
# The keys other code and tests read are unchanged; each LABEL is the plain name shown beside its key. The effective
# contribution's definition and its label "own-row headline weight" were accepted by Joe on 2026-11-19 (D-111).
NOMINAL_LABEL = "nominal customer share (each host's reference-year residential customers over all stacked hosts')"
EFFECTIVE_LABEL = ("own-row headline weight (the share of the weighted headline's weight on host rows in event years 2 and 3 "
                   "that falls on this host's own rows)")
NOMINAL_DEFINITION = (
    "Nominal customer share. Each stacked host's residential customers in its reference year (cohort - 3), over the sum of "
    "those customers across the stacked hosts; the shares add to 1. It is computed from the customer counts alone, before "
    "any regression. Every row of a host's sub-experiment (its own rows and its matched comparison utilities' rows) carries "
    "that host's customers as its weight, so the nominal share is the weight the specification gives the host's whole "
    "sub-experiment relative to the others. It is not the weight the fitted headline places on the host (that is the "
    "effective contribution), it is not a measure of statistical influence on the estimate, it is not leverage, and it is "
    "not how far the estimate would move without the host.")
EFFECTIVE_DEFINITION = (
    "Effective contribution, shown as the own-row headline weight. The weighted headline is a fixed linear combination of "
    "the outcome rows, headline = omega'y, with omega = W X~ (X~'W X~)^-1 combo: W holds the customer weights on every "
    "stacked row, X~ is the regressors (the event-time columns on host rows, the degree-day columns and the gas-share "
    "controls) with the fixed effects removed under those weights, and combo takes the mean of event years 2 and 3. A "
    "host's effective contribution is the sum of omega over that host's own rows in event years 2 and 3 (its rows in its "
    "own sub-experiment, not its matched comparison utilities' rows). Across the stacked hosts these sums add to exactly "
    "1, because omega'X equals combo' and the event-time columns are the indicators of host rows by event year. It is "
    "therefore the share of the weighted headline's total weight on host rows in event years 2 and 3 that falls on that "
    "host's own rows. It is a signed share and can be negative or larger than the host's nominal share. In exact terms, if "
    "every outcome value on the host's own rows in event years 2 and 3 rose by the same amount c and nothing else changed, "
    "the weighted headline would rise by c times the host's effective contribution. It is computed from the design's "
    "regressors, its fixed effects and the customer weights alone; no outcome, price, revenue or bill enters, and it is the "
    "same whatever the outcome. It is not a measure of statistical influence on the estimate, it is not leverage (the "
    "diagonal of the fit's hat matrix), and it is not how far the estimate would move if the host were left out: each of "
    "those depends on the outcomes or on a refit without the host, and none of them is computed here. With every weight "
    "equal it is the unweighted fit's host weight (outcome_analysis.host_weights). That the host's own rows in event years "
    "2 and 3 are what is summed, read from 'the implied weight on its own treated rows', was accepted by Joe on "
    "2026-11-19 (D-111) with this definition. This "
    "definition supersedes the earlier phrase 'effective regression contributions' (Joe, 2026-11-19, D-105) where the two "
    "differ: the quantity is a share of the headline's weight on host rows, computed from the design before any outcome, "
    "and not a contribution of the host's data to the estimate in any sense that depends on the outcome.")


class CustomerWeightMissing(ValueError):
    """A stacked host has no usable customer count in its reference year. Raised in words; nothing is filled."""


def _label(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def _stacked_hosts(d) -> list:
    return [h for h in d.hosts.itertuples() if len(h.matches) > 0] if len(d.hosts) else []


def customer_weights(d, customers: pd.DataFrame, column: str = CUSTOMERS) -> dict:
    """{host label: the host's residential customers in its reference year (cohort - 3)} for every stacked host, read from
    `customers` (utility_id_eia, state, year, `column`; the quantities frame). Stops in words on a missing column, a
    repeated unit-year, or a stacked host whose value is absent, not finite or not above zero."""
    need = KEY + ["year", column]
    miss = [c for c in need if c not in customers.columns]
    if miss:
        raise CustomerWeightMissing(f"the customers frame has no column {miss}")
    f = customers[need]
    keys = list(zip(f.utility_id_eia.astype(int), f.state.astype(str), f.year.astype(int)))
    if len(set(keys)) != len(keys):
        raise CustomerWeightMissing("the customers frame repeats a unit-year; stopping")
    look = dict(zip(keys, pd.to_numeric(f[column], errors="coerce").to_numpy(dtype=float)))
    out, bad = {}, []
    for h in _stacked_hosts(d):
        k = (int(h.key[0]), str(h.key[1]))
        year = int(h.cohort) + ps.REF
        v = look.get((k[0], k[1], year))
        if v is None or not np.isfinite(v) or v <= 0:
            bad.append(f"{_label(k)}, reference year {year}: "
                       f"{'no row' if v is None else ('not finite' if not np.isfinite(v) else f'{v:g}, not above zero')}")
            continue
        out[_label(k)] = float(v)
    if bad:
        raise CustomerWeightMissing("not computed: a stacked host has no usable residential customer count in its reference "
                                    "year, and no value is filled: " + "; ".join(bad))
    return out


def nominal_shares(weights: dict) -> dict:
    """{host label: weight over the sum of weights}."""
    tot = float(sum(weights.values()))
    return {h: float(v) / tot for h, v in weights.items()}


def row_weights(d, weights: dict) -> np.ndarray:
    """Every stacked row's weight, in the kernel's row order (outcome_analysis.stacked_rows): the weight of the host whose
    sub-experiment the row is in. A stacked host missing from `weights` stops in words."""
    rows = oa.stacked_rows(d)
    host = rows.block_host_id.astype(int).astype(str) + ":" + rows.block_host_state.astype(str)
    missing = sorted(set(host) - set(weights))
    if missing:
        raise CustomerWeightMissing(f"no weight was given for the stacked hosts {missing}")
    return host.map(weights).to_numpy(dtype=float)


class _WeightedProjection:
    """The least-squares projection off the fixed effects under row weights: M -> M - Zw (Zw'Zw)^+ Zw'M with
    Zw = sqrt(W) D, D the indicator columns of every grouping. Applied to columns already multiplied by sqrt(W)."""

    def __init__(self, groups: list, sqrt_w: np.ndarray, rcond: float = RCOND):
        coded = [np.unique(g, return_inverse=True)[1] for g in groups]
        D = sparse.hstack([estimator.indicator(c) for c in coded], format="csr")
        self.Z = sparse.diags(sqrt_w) @ D
        self.P = np.linalg.pinv((self.Z.T @ self.Z).toarray(), rcond=rcond, hermitian=True)

    def __call__(self, M: np.ndarray) -> np.ndarray:
        M = np.array(M, dtype=float, copy=True)
        flat = M.ndim == 1
        if flat:
            M = M[:, None]
        M = M - self.Z @ (self.P @ (self.Z.T @ M))
        return M[:, 0] if flat else M


def _fuel_control(d, fuel_control):
    return oa._fuel_control(d, fuel_control)


def weighted_parts(d, weights: dict, fuel_control: str | None = None) -> dict:
    """The kernel's regressors for design `d` (inference_check.fixed_parts on outcome_analysis.stackable(d), as
    outcome_analysis.estimate builds them), weighted and projected. Raises estimator.RankDeficient in words where the
    weighted regressors are not all identified once the fixed effects are removed (estimator.check_rank)."""
    fc = _fuel_control(d, fuel_control)
    rows = oa.stacked_rows(d)
    if not len(rows):
        raise estimator.RankDeficient("no host in the design has a matched comparison utility")
    f = ic.fixed_parts(oa.stackable(d), fc)
    if f["X"].shape[0] != len(rows):
        raise RuntimeError("the kernel's regressors and its stacked rows differ in length; stopping")
    w = row_weights(d, weights)
    w = w / w.mean()
    s = np.sqrt(w)
    proj = _WeightedProjection(f["groups"], s)
    Xw = s[:, None] * f["X"]
    Xt = proj(Xw)
    rank = estimator.check_rank(Xt, Xw)
    A = Xt.T @ Xt
    return {"rows": rows, "sqrt_w": s, "projection": proj, "Xt": Xt, "A": A, "combo": np.asarray(f["combo"], dtype=float),
            "columns": f["columns"], "fuel_control": f["fuel_control"], "rank": rank,
            "control_columns_left_out": f["control_columns_left_out"]}


def _per_host(rows: pd.DataFrame, omega: np.ndarray) -> dict:
    sel = rows.is_host.to_numpy() & rows.event_year.isin(list(ps.HEADLINE)).to_numpy()
    lab = rows.block_host_id.astype(int).astype(str) + ":" + rows.block_host_state.astype(str)
    s = pd.Series(omega[sel]).groupby(lab[sel].to_numpy()).sum()
    return {h: float(v) for h, v in s.items()}


def effective_contributions(d, weights: dict, fuel_control: str | None = None) -> dict:
    """From the regressors and the weights alone (no outcome): omega for every stacked row (kernel row order) and each
    host's effective contribution (the sum of omega over its own rows in event years 2 and 3). See the module docstring."""
    p = weighted_parts(d, weights, fuel_control)
    omega = p["sqrt_w"] * (p["Xt"] @ np.linalg.solve(p["A"], p["combo"]))
    per = _per_host(p["rows"], omega)
    hosts = [_label(h.key) for h in _stacked_hosts(d)]
    per = {h: per.get(h, 0.0) for h in hosts}
    return {"omega": omega, "by_host": per, "sum_over_hosts": float(sum(per.values())), "parts": p}


def weighted_fit(d, y, weights: dict, *, fuel_control: str | None = None) -> dict:
    """The customer-weighted point estimate on design `d` for the outcome `y` (aligned to outcome_analysis.stacked_rows(d)
    and checked by the kernel's guard: build it with outcome_analysis.outcome_vector on this design). `weights` maps each
    stacked host's label to its weight (customer_weights). Returns the estimate in log points and percent, the weighted
    event-year coefficients, the label DESCRIPTIVE_LABEL, no range, the nominal shares and the effective contributions
    under their own names, and the hosts with no matches. A rank failure returns no estimate and the failure in words."""
    rows = oa.stacked_rows(d)
    yv, alignment = oa._aligned(y, rows)
    hosts = [_label(k) for k in d.hosts.key] if len(d.hosts) else []
    no_match = [_label(k) for k, m in zip(d.hosts.key, d.hosts.matches) if len(m) == 0] if len(d.hosts) else []
    stacked = {h: weights[h] for h in hosts if h not in no_match and h in weights}
    out = {"label": DESCRIPTIVE_LABEL, "range_90_log_points": None, "no_range": NO_RANGE,
           "validation": NO_VALIDATION,
           "hosts_in_the_design": hosts, "hosts_with_no_matches": no_match, "outcome_alignment": alignment,
           "weights": "each host's residential customers in its reference year, on every row of its sub-experiment",
           "customer_weights": stacked,
           "nominal_customer_weight_shares": nominal_shares(stacked) if stacked else {},
           "nominal_label": NOMINAL_LABEL, "nominal_definition": NOMINAL_DEFINITION,
           "effective_contributions_to_the_weighted_headline": None, "effective_label": EFFECTIVE_LABEL,
           "effective_definition": EFFECTIVE_DEFINITION,
           "estimate_log_points": float("nan"), "estimate_percent": float("nan"), "event_year_coefficients": None,
           "estimated": False, "failure_in_words": None}
    if not np.isfinite(yv).all():
        out["failure_in_words"] = "the outcome has a value that is not finite"
        return out
    try:
        ec = effective_contributions(d, weights, fuel_control)
    except (estimator.RankDeficient, CustomerWeightMissing) as exc:
        out["failure_in_words"] = f"not computed: {type(exc).__name__}: {exc}"
        return out
    p = ec["parts"]
    yt = p["projection"](p["sqrt_w"] * yv)
    b = np.linalg.solve(p["A"], p["Xt"].T @ yt)
    est = float(p["combo"] @ b)
    times = list(ps.EVENT_TIMES)
    coefs = {str(e): float(b[i]) for i, e in enumerate(times)}
    coefs[str(ps.REF)] = 0.0
    out.update(estimate_log_points=est, estimate_percent=float(100.0 * np.expm1(est)),
               event_year_coefficients={str(e): coefs[str(e)] for e in range(min(times), max(times) + 1)},
               effective_contributions_to_the_weighted_headline=ec["by_host"],
               effective_contributions_sum=ec["sum_over_hosts"], estimate_as_omega_times_y=float(ec["omega"] @ yv),
               fuel_control=p["fuel_control"], columns=list(p["columns"]), rows=int(len(rows)), estimated=bool(np.isfinite(est)))
    return out


# ---- main: the quantity-only summary on the design as it stands -------------------------------------------------------

def summary_hosts(d, weights: dict, names: dict | None = None, fuel_control: str | None = None) -> dict:
    """The per-host part of the summary file, from the design and the customer weights alone (no outcome): each host's
    customers, its nominal share, its effective contribution under the customer weights and, for reference, under equal
    weights, with the labels and the exact definitions beside them, and the sums."""
    nom = nominal_shares(weights)
    eff = effective_contributions(d, weights, fuel_control)["by_host"]
    equal = effective_contributions(d, {h: 1.0 for h in weights}, fuel_control)["by_host"]
    cohort = {_label(k): int(g) for k, g in zip(d.hosts.key, d.hosts.cohort)}
    names = names or {}
    return {"nominal_label": NOMINAL_LABEL, "nominal_definition": NOMINAL_DEFINITION,
            "effective_label": EFFECTIVE_LABEL, "effective_definition": EFFECTIVE_DEFINITION,
            "hosts": [{"host": h, "name": names.get((int(h.split(":")[0]), h.split(":")[1])), "cohort": cohort[h],
                       "reference_year": cohort[h] + ps.REF, "residential_customers_in_the_reference_year": weights[h],
                       "nominal_customer_weight_share": nom[h],
                       "effective_contribution_to_the_weighted_headline": eff[h],
                       "unweighted_fit_contribution_for_reference": equal[h]} for h in sorted(weights, key=lambda h: -nom[h])],
            "sums": {"nominal": float(sum(nom.values())), "effective_weighted": float(sum(eff.values())),
                     "unweighted": float(sum(equal.values()))}}


def main() -> int:
    """The headline set at 2% under the headline rules, built as design.main and design_weights.main build it; the
    customers from the quantities frame; the nominal shares and the effective contributions (weighted, and the unweighted
    fit's beside them for reference), regressors and weights only. No price or outcome is read; nothing is fitted."""
    from pipeline.analysis import usable_flag
    rules = ps.HEADLINE_RULES
    q, dose, regions, fuel, dd = dsg.load()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    names = {(int(k[0]), k[1]): v for k, v in q.groupby(KEY).utility_name.last().items()}
    treated, clean = dsg.split(0.02, ps.HEADLINE_SET, q, dose)
    d = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                             ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
    w = customer_weights(d, q)
    part = summary_hosts(d, w, names, rules.fuel_control)
    fp = dsg.run_fingerprint(d, rules=rules, usable=usable,
                             assumptions={"kind": "customer_weighted_fit_design", "set": ps.HEADLINE_SET, "threshold": 0.02},
                             settings={"weights": CUSTOMERS, "year": "cohort - 3"}, seeds=None)
    doc = {"what_this_is": ("The customer-weighted fit's design side on the headline set at 2% under the headline rules "
                            "(Electricity: the main estimate, Weights; Joe, 2026-11-19, D-105: descriptive, nominal customer "
                            "weights kept apart from effective regression contributions). For each host: its residential "
                            "customers in its reference year, its NOMINAL share of the customer weight, and its EFFECTIVE "
                            "contribution to the weighted fit's headline (the own-row headline weight), computed from the "
                            "regressors and the weights alone; the unweighted fit's contribution is beside it for reference. "
                            "What each share measures, and what it does not, is in nominal_definition and effective_definition "
                            "(Joe, 2026-11-19: clarify exactly what 'effective contribution' measures; no calculation changed "
                            "and no influence analysis is run). Quantities only: no price, revenue, "
                            "bill or outcome is read and nothing is fitted. PROVISIONAL: the design stands as of 2026-11-18 and "
                            "the plan is a DRAFT, not frozen."),
           "built_by": "pipeline/analysis/weighted_fit.py (main)",
           "customers_source": f"data/interim/panel_quantities.parquet, field {CUSTOMERS}, the host's unit in cohort - 3",
           "set": ps.HEADLINE_SET, "threshold": 0.02, "rules": rules.label, "label": DESCRIPTIVE_LABEL,
           **part,
           "design_inputs_sha256": fp["of"]["design_inputs"], "fingerprint": fp}
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    for x in doc["hosts"]:
        print(f"{x['host']:<9} {str(x['name']):<34} customers {x['residential_customers_in_the_reference_year']:>10,.0f}  "
              f"nominal {100 * x['nominal_customer_weight_share']:6.2f}%  effective (weighted) "
              f"{100 * x['effective_contribution_to_the_weighted_headline']:7.2f}%  unweighted "
              f"{100 * x['unweighted_fit_contribution_for_reference']:7.2f}%")
    print("sums", doc["sums"])
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
