"""The influence checks of D-58, rule 7: leave one comparison out, and leave one company out. Quantities only.

A comparison utility may be matched to more than one host. In both checks every copy of what is removed
leaves every host's stack, each host keeps its remaining matches in their order, and nothing is rematched.

This module specifies the deletions and what can be said about each before any outcome is read: the net
weight of what is removed (on the full design), the hosts each deletion leaves with fewer than five matches
(inadequate support), with none, or with zero weight, and whether the fit can be computed at all, by a rank
test on the regressors after the fixed effects are removed, made before any fit (D-57 found that
estimator.Fit inverts the regressors' cross-product without checking its rank).

Run on outcomes only after the freeze. This module reads no outcome: no price, no revenue, nothing under
data/blind/. The estimate and its range for each deletion are added after the freeze, under the procedure
rule 4 selects.

Run:  python3 -I pipeline/analysis/influence.py      the deletions on quantities only, before the freeze (step E), for the
      headline set and the set with the ten-year case; writes data/frozen/influence_on_quantities.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # run as a file: python3 -I pipeline/analysis/influence.py

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import design, estimator  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

INADEQUATE = 5                 # D-58, rule 7 (and rule 2.4): a host left with fewer matches than this has inadequate support
RANK_TOLERANCE = 1e-8          # smallest singular value over the largest, after the fixed effects are removed
FROZEN = design.FROZEN
SETS = (ps.HEADLINE_SET, ps.TEN_YEAR_SET)       # the headline set and the set with the ten-year case beside it
TOP = 10
ZERO_WEIGHT = 1e-9             # a host's headline weight below this in magnitude is zero (as inference_check.weights_report)


def label(key: tuple) -> str:
    return f"{int(key[0])}:{key[1]}"


def _norm(key: tuple) -> tuple:
    return (int(key[0]), key[1])


def leave_out(d: design.Design, keys: set) -> design.Design:
    """A new Design with every copy of each comparison key in `keys` removed from every host's matches.

    Hosts are never removed, and each keeps its remaining matches in their original order. `d` is not changed:
    the hosts frame is a copy with new lists, and the windows (which no deletion alters) are shared.
    """
    gone = {_norm(k) for k in keys}
    hosts = d.hosts.copy()
    matches, match_keys = [], []
    for h in d.hosts.itertuples():
        kept = [(int(m), mk) for m, mk in zip(h.matches, h.match_keys) if _norm(mk) not in gone]
        matches.append([m for m, _ in kept])
        match_keys.append([mk for _, mk in kept])
    if len(hosts):
        hosts["matches"] = pd.Series(matches, index=hosts.index, dtype=object)
        hosts["match_keys"] = pd.Series(match_keys, index=hosts.index, dtype=object)
    return design.Design(hosts, d.windows, d.is_comp, list(d.dropped), dict(d.region_names), dict(d.unit_code), dict(d.state_code), d.gas)


def _without(d: design.Design, keep: np.ndarray) -> design.Design:
    """The same design with only the hosts marked in `keep`; the hosts with no matches are what is left out."""
    return design.Design(d.hosts[keep].copy(), d.windows, d.is_comp, list(d.dropped), d.region_names, d.unit_code, d.state_code, d.gas)


def estimable(d: design.Design, fuel_control: str = ps.GAS_SHARE) -> dict:
    """Whether the fit can be computed, decided before any fit, and which hosts carry nothing.

    A host with no matches is reported and left out of the design used for the rank test and the weights, since
    a block with no comparison rows cannot be stacked. The rank test takes the regressors as the fit does (the
    event-time columns, the two degree-day controls and, under the gas-share control, the gas-share columns that
    ps.assemble keeps: every column, whatever their number), removes the fixed effects
    (inference_check.fixed_parts, estimator.Projection) and compares the smallest singular value with the
    largest. The fit is called estimable only if that ratio is above RANK_TOLERANCE and the largest singular
    value is itself above RANK_TOLERANCE times the largest singular value of the regressors before the fixed
    effects are removed (so that a design in which every regressor is absorbed, leaving only rounding error,
    is not called estimable because its rounding errors happen to be of similar size). Host weights are
    computed only when the fit is estimable.
    """
    n = np.array([len(m) for m in d.hosts.matches]) if len(d.hosts) else np.array([], dtype=int)
    none = [label(k) for k, c in zip(d.hosts.key, n) if c == 0] if len(d.hosts) else []
    out = {"estimable": False, "smallest_singular_value_ratio": 0.0, "largest_singular_value_relative_to_the_unprojected_regressors": 0.0,
           "hosts_with_no_matches": none, "hosts_with_zero_weight": []}
    if not len(d.hosts) or not (n > 0).any():
        return out
    sub = _without(d, n > 0)
    f = ic.fixed_parts(sub, fuel_control)
    X = f["X"]                                                  # all of it: the number of control columns is not fixed
    Xt = (f["projection"] or estimator.Projection(f["groups"]))(X)
    sv = np.linalg.svd(Xt, compute_uv=False)
    raw = float(np.linalg.svd(X, compute_uv=False).max()) if X.size else 0.0
    largest = float(sv.max()) if sv.size else 0.0
    ratio = float(sv.min() / largest) if largest > 0 else 0.0
    scale = largest / raw if raw > 0 else 0.0
    out["smallest_singular_value_ratio"] = ratio
    out["largest_singular_value_relative_to_the_unprojected_regressors"] = scale
    out["estimable"] = bool(ratio > RANK_TOLERANCE and scale > RANK_TOLERANCE)
    if out["estimable"]:
        out["hosts_with_zero_weight"] = zero_weight_hosts(sub, fuel_control)
    return out


def zero_weight_hosts(d: design.Design, fuel_control: str = ps.GAS_SHARE) -> list:
    """Hosts whose headline weight (the sum of their rows' weights in event years 2 and 3) is zero. Call only on an estimable design."""
    wt = ic.implied_weights(d, fuel_control)
    head = wt[wt.is_host & wt.event_year.isin(ps.HEADLINE)].groupby("utility").weight.sum()
    return [label(k) for k in d.hosts.key if abs(float(head.get(k, 0.0))) < ZERO_WEIGHT]


def _years_in_fit(d: design.Design) -> dict:
    """Each comparison utility in the fit and the calendar years it appears in (the windows of the hosts it is matched to)."""
    out: dict = {}
    for h in d.hosts.itertuples():
        years = range(int(h.cohort) - ps.PRE, int(h.cohort) + ps.POST + 1)
        for mk in h.match_keys:
            out.setdefault(_norm(mk), set()).update(years)
    return out


def deletions(d: design.Design, ownership: pd.DataFrame | None, ownership_of: dict | None = None,
              fuel_control: str = ps.GAS_SHARE) -> pd.DataFrame:
    """One row per deletion of both checks of D-58, rule 7, with what can be said before any outcome is read.

    kind "comparison": one row per distinct comparison utility-state in the fit.
    kind "company":    one row per company (ownership.company_of over the years the unit appears in the fit; a
                       utility with no parent is its own company, so every comparison utility is in one). With no
                       ownership table every utility is its own company, the company rows would repeat the
                       comparison rows, and they are omitted; the frame's attrs["company_rows"] says so.
    `ownership_of`, optional, flags in each company row the investor-owned units whose company is taken from
    the absence of a row (rule 2.2 makes them ineligible against investor-owned hosts, but not against others).
    `fuel_control` is the regressors' fuel-mix control (the gas-share control by default from step D, D-59 item 7).

    net_weight_removed is the sum of inference_check.net_weights(...).net_weight over the removed utilities on
    the FULL design (NaN when the full design is not estimable). Host lists are labels "id:state";
    hosts_with_fewer_than_five_matches holds hosts left with one to four, hosts_with_no_matches those with none.
    """
    full = estimable(d, fuel_control)
    net: dict = {}
    if full["estimable"]:
        n = np.array([len(m) for m in d.hosts.matches])
        net = {_norm(k): float(v) for k, v in ic.net_weights(ic.implied_weights(_without(d, n > 0), fuel_control)).net_weight.items()}
    years = _years_in_fit(d)
    plan = [("comparison", label(k), {k}, None) for k in sorted(years)]
    if ownership is not None:
        firms: dict = {}
        for k, ys in years.items():
            firms.setdefault(own_rules.company_of(ownership, k, sorted(ys)), set()).add(k)
        for name in sorted(firms):
            units = firms[name]
            flag = None
            if ownership_of is not None:
                flag = [label(k) for k in sorted(units) if ownership_of.get(k) == own_rules.INVESTOR_OWNED
                        and not own_rules.parents(ownership, k, sorted(years[k]))]
            plan.append(("company", name, units, flag))
    rows = []
    for kind, removed, units, flag in plan:
        e = leave_out(d, units)
        counts = {label(h.key): len(h.matches) for h in e.hosts.itertuples()}
        r = estimable(e, fuel_control)
        row = {"kind": kind, "removed": removed, "units": [label(k) for k in sorted(units)], "units_removed": len(units),
               "net_weight_removed": float(sum(net.get(k, 0.0) for k in units)) if full["estimable"] else float("nan"),
               "hosts_with_fewer_than_five_matches": [h for h, c in counts.items() if 0 < c < INADEQUATE],
               "hosts_with_no_matches": r["hosts_with_no_matches"], "hosts_with_zero_weight": r["hosts_with_zero_weight"],
               "estimable": r["estimable"]}
        if ownership_of is not None:
            row["investor_owned_units_with_no_row"] = flag if flag is not None else []
        rows.append(row)
    out = pd.DataFrame(rows, columns=["kind", "removed", "units", "units_removed", "net_weight_removed", "hosts_with_fewer_than_five_matches",
                                      "hosts_with_no_matches", "hosts_with_zero_weight", "estimable"]
                       + (["investor_owned_units_with_no_row"] if ownership_of is not None else []))
    out.attrs["company_rows"] = ("computed from the ownership table" if ownership is not None else
                                 "omitted: no ownership table, so every utility is its own company and the comparison rows already cover it")
    out.attrs["full_design"] = full
    return out


# ---- the run before the freeze: rule 7's deletions on quantities only (step E) ------------------------------------------

def _row(r) -> dict:
    return {"kind": r.kind, "removed": r.removed}


def summarise(out: pd.DataFrame) -> dict:
    """What rule 7 asks of the deletions before any outcome is read: counts by kind, whether the full design is estimable,
    every deletion that leaves a host short, without matches or without weight, or the fit not estimable (by name), the
    deletions that remove the most net weight, and the largest net weight removed by one company."""
    full = out.attrs.get("full_design", {})
    named = lambda col: [{**_row(r), "hosts": list(getattr(r, col))} for r in out.itertuples() if len(getattr(r, col))]  # noqa: E731
    s = {"deletions": {k: int(v) for k, v in out.kind.value_counts().sort_index().items()},
         "company_rows": out.attrs.get("company_rows"),
         "full_design_estimable": bool(full.get("estimable", False)),
         "leave_a_host_with_fewer_than_five_matches": named("hosts_with_fewer_than_five_matches"),
         "leave_a_host_with_no_matches": named("hosts_with_no_matches"),
         "leave_a_host_with_zero_weight": named("hosts_with_zero_weight"),
         "make_the_fit_not_estimable": [_row(r) for r in out.itertuples() if not r.estimable]}
    w = out[np.isfinite(out.net_weight_removed.astype(float))]
    if not s["full_design_estimable"] or w.empty:
        s["ten_deletions_removing_the_most_net_weight"] = []
        s["largest_net_weight_removed_by_one_company"] = None
        s["net_weight_note"] = "the full design is not estimable, so no net weight is computed (rule 7: a rank test before any fit)"
        return s
    top = w.sort_values("net_weight_removed", ascending=False, kind="stable").head(TOP)
    s["ten_deletions_removing_the_most_net_weight"] = [{**_row(r), "units": list(r.units), "net_weight_removed": round(float(r.net_weight_removed), 6)}
                                                       for r in top.itertuples()]
    comp = w[w.kind == "company"]
    if comp.empty:
        s["largest_net_weight_removed_by_one_company"] = None
    else:
        r = comp.sort_values("net_weight_removed", ascending=False, kind="stable").iloc[0]
        s["largest_net_weight_removed_by_one_company"] = {
            "company": r.removed, "net_weight_removed": round(float(r.net_weight_removed), 6), "units": list(r.units),
            "investor_owned_units_with_no_row": list(r.get("investor_owned_units_with_no_row", []) or [])}
    s["net_weight_note"] = ("net weight as D-57 defines it, on the full design under the gas-share control: signed weights summed "
                            "by utility-state and calendar year, then magnitudes")
    return s


def main() -> int:
    """Rule 7's two influence checks on the design that will be run, on quantities only, before the freeze.

    Builds the headline set and the set with the ten-year case at 2% exactly as design.main does (build_with_rules with the
    headline rules: the ownership table, the usable flag, the gas shares, the unknown-load file), runs `deletions` under
    the gas-share control, and writes data/frozen/influence_on_quantities.json. No price and no outcome is read.
    """
    from pipeline.analysis import usable_flag
    rules = ps.HEADLINE_RULES
    q, dose, regions, fuel, dd = design.load()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    report = {"what_this_is": "D-58 rule 7 before the freeze, on quantities only: for each deletion (one comparison utility-state, "
                              "or one company with every unit of its ultimate parent; a utility with no parent is its own company), "
                              "which hosts it leaves short, without matches or without weight, and whether the fit can be computed. "
                              "No price and no outcome is read.",
              "rules": rules.label, "fuel_control": ps.GAS_SHARE, "threshold": "2%",
              "ownership_assumption": "municipal systems, public power districts and distribution cooperatives with no row are each "
                                      "their own owner (D-58 rule 2.2); investor-owned units whose company is taken from the absence "
                                      "of a row are flagged in each company row",
              "sets": {}}
    for which in SETS:
        treated, clean = design.split(0.02, which, q, dose)
        d = design.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                                    ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
        out = deletions(d, ownership, ownership_of, ps.GAS_SHARE)
        s = summarise(out)
        s["hosts_in_the_design"] = int(len(d.hosts))
        s["fingerprint"] = design.run_fingerprint(
            d, rules=rules, usable=usable, assumptions={"kind": "influence_on_quantities", "set": which, "threshold": 0.02},
            settings={"inadequate": INADEQUATE, "zero_weight": ZERO_WEIGHT, "rank_tolerance": RANK_TOLERANCE}, seeds=None)
        report["sets"][which] = s
        big = max((x["net_weight_removed"] for x in s["ten_deletions_removing_the_most_net_weight"]), default=None)
        print(f"{which}: deletions run {len(out)}, leave a host short {len(s['leave_a_host_with_fewer_than_five_matches'])}, "
              f"leave a host with no weight {len(s['leave_a_host_with_zero_weight'])}, largest net weight removed "
              f"{'not computed' if big is None else round(big, 4)}", flush=True)
    (FROZEN / "influence_on_quantities.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
