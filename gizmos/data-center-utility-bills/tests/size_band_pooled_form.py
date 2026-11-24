"""Test support: the agent's construction of the pooled size-band form, for comparison with the per-host form as built.

This is NOT a replacement for pipeline/analysis/size_band_run.py and nothing in the pipeline imports it. It exists so that
tests/test_size_band_equivalence_invented.py can test, rather than infer, whether the size-band side run as built (one
sub-experiment per host, every eligible unit of the host's cell its comparisons) is the same design as the pooled form
the plan describes. It reads no file and no outcome: an outcome, where one is used, is an argument built by the caller.

The two forms
-------------
per_host (as built)
    size_band_run.build's design, stacked as outcome_analysis.estimate stacks it (outcome_analysis.stackable(d).blocks()):
    one block per host, the host's row and every eligible unit of its cell (reference-year region by size band) after
    the ownership exclusions decided for that host.
pooled (the plan's words and the simulation's form)
    PREANALYSIS.md, Size adjustment: "cells of reference-year region by size band; utility effects and cell-by-year
    effects". power_simulation.build_blocks, form "size_band": for each cohort, one block per cell holding every host of
    that cohort in the cell and every comparison unit in the cell. The block is cohort by cell because the reference
    year, and with it each unit's region and band, is the cohort's.

Every form here is stacked by power_simulation.assemble, unchanged: event-time columns on host rows, the two degree-day
columns, the gas-share-by-calendar-year columns kept by power_simulation.screen_controls; utility effects (one per unit
per block) and block-by-region-by-year effects; clusters by state. `stack` rebuilds the gas-share screening only so that
the cell-by-year effect can be coded another way for one named variant; with the kernel's coding it reproduces assemble
exactly (tested).

Where the plan's words admit more than one pooled construction (the agent's readings)
-------------------------------------------------------------------------------------
pooled_union
    A block's comparison units are those eligible for AT LEAST ONE host of the block (each host's eligible cell units,
    joined). Follows "comparison utilities every unit eligible under the main design's rules" read for the block. A unit
    eligible for one host and not another is then a comparison for both: the ownership exclusion is not kept for the
    host it excludes.
pooled_intersection
    Those eligible for EVERY host of the block. Keeps every host's ownership exclusion, at the cost of leaving out, for a
    host, units eligible for it.
pooled_simulation_literal
    Every comparison-eligible unit in the cell before any ownership exclusion, as power_simulation.build_blocks forms
    its "size_band" blocks (its `excluded` argument is used by the nearest-in-size form only). It equals pooled_union
    unless some unit of a cell is excluded for every host of the block.
pooled_union_cell_year_across_cohorts
    The union blocks, with the cell-by-year effect coded by reference-year region, size band, region in the year and
    calendar year ACROSS cohorts, so that blocks of different cohorts in one cell share their year effects. Follows
    "cell-by-year effects" read with no cohort in it. Utility effects stay one per unit per block, as the stack has them.
Not built: a block that is a cell alone across cohorts with ONE copy of each comparison unit. A unit's size band and
region are measured in each cohort's reference year and can differ between cohorts, and the windows differ, so that
form needs choices the plan does not make (which reference year places a unit, which years it covers).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import estimator  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
PER_HOST = "per_host"
UNION = "pooled_union"
INTERSECTION = "pooled_intersection"
LITERAL = "pooled_simulation_literal"
ACROSS = "pooled_union_cell_year_across_cohorts"
VARIANTS = (PER_HOST, UNION, INTERSECTION, LITERAL, ACROSS)
POOLED = (UNION, INTERSECTION, LITERAL, ACROSS)
BLOCK_FE = "block_by_region_by_year"                       # the kernel's coding (power_simulation.assemble)
ACROSS_FE = "cell_by_region_by_calendar_year_across_cohorts"
SV_TOL = estimator.RANK_TOLERANCE


def _key(k) -> tuple:
    return (int(k[0]), str(k[1]))


def cell_of(d, h) -> tuple:
    """(cohort, reference-year region, size band) of a host row of d.hosts, read from its cohort's window."""
    w = d.windows[int(h.cohort)]
    return (int(h.cohort), str(w.region[int(h.row)]), int(w.band[int(h.row)]))


def per_host_blocks(d) -> list:
    """The blocks outcome_analysis.estimate stacks for the size-band design as built (hosts with no match left out)."""
    return oa.stackable(d).blocks()


def literal_cell_rows(d, h) -> np.ndarray:
    """Every comparison-eligible unit in the host's cell before any ownership exclusion (power_simulation.build_blocks'
    size_band cells): is_comp in the cohort's window, same reference-year region and size band."""
    g = int(h.cohort)
    w = d.windows[g]
    j = int(h.row)
    return np.flatnonzero(d.is_comp[g] & (w.region == w.region[j]) & (w.band == w.band[j]))


def pooled_blocks(d, comparisons: str = "union") -> tuple[list, list]:
    """Blocks of the pooled form: one per cohort and cell. `comparisons` is "union", "intersection" or "literal" (see the
    module docstring). Returns ([(cohort, host rows, comparison rows)], [cell records]); a cell whose comparison set is
    empty is not stacked and is recorded with its hosts."""
    if comparisons not in ("union", "intersection", "literal"):
        raise ValueError(f"unknown comparison rule {comparisons!r}")
    by_cell: dict = {}
    for h in d.hosts.itertuples():
        by_cell.setdefault(cell_of(d, h), []).append(h)
    blocks, cells = [], []
    for c in sorted(by_cell, key=lambda x: (x[0], x[1], x[2])):
        hs = by_cell[c]
        sets = [set(int(m) for m in h.matches) for h in hs]
        if comparisons == "union":
            comp = set().union(*sets)
        elif comparisons == "intersection":
            comp = set.intersection(*sets)
        else:
            comp = set(int(m) for m in literal_cell_rows(d, hs[0]))
        tr = np.array(sorted(int(h.row) for h in hs), dtype=int)
        comp = np.array(sorted(comp), dtype=int)
        cells.append({"cohort": c[0], "region": c[1], "size_band": c[2], "hosts": [_key(h.key) for h in hs],
                      "comparisons": int(len(comp)), "stacked": bool(len(comp))})
        if len(comp):
            blocks.append((c[0], tr, comp))
    return blocks, cells


def blocks_for(d, variant: str) -> list:
    if variant == PER_HOST:
        return per_host_blocks(d)
    rule = {UNION: "union", INTERSECTION: "intersection", LITERAL: "literal", ACROSS: "union"}[variant]
    return pooled_blocks(d, rule)[0]


def rows_of(d, blocks: list) -> pd.DataFrame:
    """One row per stacked observation in power_simulation.assemble's order: block by block, its host rows then its
    comparison rows, each over the ten window years."""
    out = []
    for b, (g, tr, comp) in enumerate(blocks):
        w = d.windows[g]
        hosts = tuple(_key(w.keys[int(r)]) for r in tr)
        cell = (str(w.region[int(tr[0])]), int(w.band[int(tr[0])]))
        for j, r in enumerate(np.concatenate([np.asarray(tr, int), np.asarray(comp, int)])):
            k = _key(w.keys[int(r)])
            for t in range(ps.T):
                out.append((b, int(g), cell[0], cell[1], hosts, k[0], k[1], int(g) - ps.PRE + t, t - ps.PRE, j < len(tr),
                            int(w.region_t[int(r), t])))
    return pd.DataFrame(out, columns=["block", "cohort", "cell_region", "size_band", "block_hosts", "utility_id_eia", "state",
                                      "year", "event_year", "is_host", "region_code_in_year"])


def stack(d, blocks: list, *, fe: str = BLOCK_FE, controls: bool = True) -> dict:
    """The stacked regression for `blocks`: X, columns, fixed-effect groups, clusters, the projection, the controls left out
    and the rows. The event-time and degree-day columns, the utility effects, the block-by-region-by-year effects and the
    clusters are power_simulation.assemble's (called with fuel_control NO_FUEL); the gas-share columns are built and
    screened exactly as assemble builds and screens them, against `fe`'s fixed effects. controls=False drops every control
    (a diagnostic only, not a form)."""
    if fe not in (BLOCK_FE, ACROSS_FE):
        raise ValueError(f"unknown fixed-effect coding {fe!r}")
    for w in d.windows.values():
        w.y = np.zeros((len(w.keys), ps.T))                 # as inference_check.fixed_parts: no outcome is in the stack
    a = ps.assemble(d.windows, blocks, controls=controls, fuel_control=ps.NO_FUEL)
    rows = rows_of(d, blocks)
    groups = list(a["groups"])
    if fe == ACROSS_FE:
        code = pd.MultiIndex.from_arrays([rows.cell_region, rows.size_band, rows.region_code_in_year, rows.year])
        groups[1] = pd.factorize(code)[0]
    X, columns, left_out, projection = a["X"], list(a["columns"]), [], estimator.Projection(groups)
    if controls:
        years = rows.year.to_numpy()
        share = ps.gas_share_of_rows(rows.state.to_numpy(), d.gas)
        calendar = sorted(int(x) for x in np.unique(years))
        left_out.append({"year": calendar[0], "why": ps.FIRST_YEAR_LEFT_OUT})
        cand = (np.column_stack([share * (years == yr) for yr in calendar[1:]]) if len(calendar) > 1
                else np.zeros((len(years), 0)))
        kept, dropped = ps.screen_controls(X[:, len(ps.EVENT_TIMES):], cand, projection)
        left_out += [{"year": calendar[1 + j], "why": ps.REDUNDANT_LEFT_OUT} for j in dropped]
        X = np.column_stack([X, cand[:, kept]])
        columns += [f"gas_share_x_{calendar[1 + j]}" for j in kept]
    return {"X": X, "columns": columns, "groups": groups, "cluster": a["cluster"], "projection": projection,
            "control_columns_left_out": left_out, "rows": rows, "fe": fe}


def form(d, variant: str, *, controls: bool = True) -> dict:
    """stack() for a named variant."""
    return stack(d, blocks_for(d, variant), fe=ACROSS_FE if variant == ACROSS else BLOCK_FE, controls=controls)


def operator(st: dict) -> dict:
    """The headline's implied weights on the stacked rows, from the regressors alone: w = X~ (X~'X~)^-1 combo, combo the
    mean of event years 2 and 3 (inference_check.implied_weights' formula). The estimate on any outcome y of these rows
    is w'y. Also the rank: singular values of X~ and the count above SV_TOL times the largest. Raises
    estimator.RankDeficient, in words, where the fit cannot be computed."""
    Xt = st["projection"](st["X"])
    sv = np.linalg.svd(Xt, compute_uv=False)
    rank = int((sv > SV_TOL * sv[0]).sum()) if sv.size and sv[0] > 0 else 0
    estimator.check_rank(Xt, st["X"])
    combo = ps.headline_combo(st["X"].shape[1])
    w = Xt @ (np.linalg.inv(Xt.T @ Xt) @ combo)
    return {"w": w, "rank": rank, "columns": int(st["X"].shape[1]), "smallest_singular_value_ratio": float(sv[-1] / sv[0]),
            "Xt": Xt, "combo": combo}


def net_weights(st: dict, w: np.ndarray) -> pd.Series:
    """The weight on each observed outcome (a unit in a calendar year): the signed sum of the weights of its stacked
    copies (inference_check.net_weights' net reading, kept signed here)."""
    r = st["rows"]
    return pd.Series(w).groupby([r.utility_id_eia.to_numpy(), r.state.to_numpy(), r.year.to_numpy()]).sum()


def multiplicities(st: dict) -> pd.Series:
    """How many stacked rows each observed outcome (unit, calendar year) has."""
    r = st["rows"]
    return r.groupby(["utility_id_eia", "state", "year"]).size()


def host_headline_weights(st: dict, w: np.ndarray) -> dict:
    """Each host's own rows' weight in event years 2 and 3 (outcome_analysis.host_weights' reading)."""
    r = st["rows"]
    m = r.is_host.to_numpy() & r.event_year.isin(list(ps.HEADLINE)).to_numpy()
    s = pd.Series(w[m]).groupby([r.utility_id_eia.to_numpy()[m], r.state.to_numpy()[m]]).sum()
    return {_key(k): float(v) for k, v in s.items()}


def fixed_effects(st: dict) -> dict:
    """Counts of the two fixed-effect groupings' levels, and the dimension of the space they span on the rows."""
    g = st["groups"]
    n_unit = int(len(np.unique(g[0])))
    n_cell = int(len(np.unique(g[1])))
    D = np.column_stack([estimator.indicator(np.unique(x, return_inverse=True)[1]).toarray() for x in g])
    sv = np.linalg.svd(D, compute_uv=False)
    return {"utility_effects": n_unit, "cell_by_year_effects": n_cell, "span_dimension": int((sv > 1e-9 * sv[0]).sum())}


def controls_absorbed(st: dict) -> dict:
    """The controls kept, those left out by the screening and, of those kept, any that the fixed effects absorb exactly
    (outcome_analysis.exactly_absorbed_controls, at its tolerance)."""
    yes, _ = oa.exactly_absorbed_controls(st["X"], st["projection"], st["columns"], len(ps.EVENT_TIMES))
    return {"kept": [c for c in st["columns"][len(ps.EVENT_TIMES):]],
            "left_out": [x["year"] for x in st["control_columns_left_out"]],
            "kept_but_exactly_absorbed": [c["column"] for c in yes]}


def outcome_for(st: dict, frame: pd.DataFrame, column: str) -> np.ndarray:
    """The outcome for every stacked row, from a long frame keyed by utility_id_eia, state and year (an invented outcome
    in the tests). Stops on a missing unit-year; fills nothing."""
    f = frame[KEY + ["year", column]].copy()
    f["utility_id_eia"] = f.utility_id_eia.astype(int)
    m = st["rows"][KEY + ["year"]].merge(f, on=KEY + ["year"], how="left", validate="many_to_one")
    v = m[column].to_numpy(dtype=float)
    if not np.isfinite(v).all():
        raise ValueError("the outcome frame lacks a unit-year the stack needs")
    return v


def fit_headline(st: dict, y: np.ndarray) -> float:
    """The headline from a fit (estimator.Fit, the shared estimator): combo'b."""
    b = estimator.Fit(y, st["X"], st["groups"], st["cluster"], projection=st["projection"]).coef()
    return float(ps.headline_combo(st["X"].shape[1]) @ b)


def kernel_reading(st: dict, y: np.ndarray) -> dict:
    """The selected procedure's reading on this stack, as outcome_analysis._read computes it (candidates.Problem,
    candidates.CandidateC, power_simulation.c_reading): the estimate, its CR2 standard error and the 90% range. For an
    invented outcome only."""
    from pipeline.analysis import candidates as cd
    combo = ps.headline_combo(st["X"].shape[1])
    pre = [ps.EVENT_TIMES.index(e) for e in ps.EARLY]
    cand = cd.CandidateC(cd.Problem(st["X"], st["groups"], st["cluster"], projection=st["projection"], combo=combo, pre=pre))
    b, u = cand.fit(y)
    r = ps.c_reading(cand, b, u)
    return {"estimate": float(combo @ b), "se": float(r["se"]), "lo": float(r["lo"]), "hi": float(r["hi"]),
            "numerical_failure": r["numerical_failure"]}


def compare(d, a: str, b: str, *, controls: bool = True) -> dict:
    """Variant a against variant b on one design, from the regressors alone (no outcome):
    rows and their multiplicities, rank and columns, fixed effects, controls, host headline weights and the net weight
    on every observed outcome. Differences are b minus a."""
    sa, sb_ = form(d, a, controls=controls), form(d, b, controls=controls)
    oa_, ob = operator(sa), operator(sb_)
    na, nb = net_weights(sa, oa_["w"]), net_weights(sb_, ob["w"])
    keys = na.index.union(nb.index)
    na, nb = na.reindex(keys, fill_value=0.0), nb.reindex(keys, fill_value=0.0)
    ma, mb = multiplicities(sa), multiplicities(sb_)
    mk = ma.index.union(mb.index)
    ma, mb = ma.reindex(mk, fill_value=0), mb.reindex(mk, fill_value=0)
    ha, hb = host_headline_weights(sa, oa_["w"]), host_headline_weights(sb_, ob["w"])
    diff_net = (nb - na).abs()
    return {"a": a, "b": b, "controls": controls,
            "rows": (int(len(sa["rows"])), int(len(sb_["rows"]))),
            "blocks": (int(sa["rows"].block.nunique()), int(sb_["rows"].block.nunique())),
            "observed_outcomes": (int((ma > 0).sum()), int((mb > 0).sum())),
            "same_observed_outcomes": bool(((ma > 0) == (mb > 0)).all()),
            "max_multiplicity": (int(ma.max()), int(mb.max())),
            "outcomes_with_different_multiplicity": int((ma != mb).sum()),
            "multiplicity_a": ma, "multiplicity_b": mb,
            "rank": (oa_["rank"], ob["rank"]), "columns": (oa_["columns"], ob["columns"]),
            "column_names": (sa["columns"], sb_["columns"]),
            "smallest_singular_value_ratio": (oa_["smallest_singular_value_ratio"], ob["smallest_singular_value_ratio"]),
            "fixed_effects": (fixed_effects(sa), fixed_effects(sb_)),
            "controls": (controls_absorbed(sa), controls_absorbed(sb_)),
            "host_headline_weights": (ha, hb),
            "max_host_weight_difference": float(max(abs(hb.get(k, 0.0) - ha.get(k, 0.0)) for k in set(ha) | set(hb))),
            "net_weights": (na, nb), "max_net_weight_difference": float(diff_net.max()),
            "net_weight_l1_difference": float(diff_net.sum()), "net_weight_l1": (float(na.abs().sum()), float(nb.abs().sum())),
            "stacks": (sa, sb_), "operators": (oa_, ob)}


def block_sets(blocks: list) -> set:
    """The blocks as a set of (cohort, host rows, comparison rows), order-free, for an exact comparison of two forms."""
    return {(int(g), tuple(sorted(int(x) for x in tr)), frozenset(int(x) for x in comp)) for g, tr, comp in blocks}


def summary(c: dict) -> dict:
    """The serialisable part of compare()'s result, for a report."""
    lab = lambda k: f"{k[0]}:{k[1]}"  # noqa: E731
    ha, hb = c["host_headline_weights"]
    return {"a": c["a"], "b": c["b"], "rows": list(c["rows"]), "blocks": list(c["blocks"]),
            "observed_outcomes": list(c["observed_outcomes"]), "same_observed_outcomes": c["same_observed_outcomes"],
            "max_multiplicity": list(c["max_multiplicity"]),
            "outcomes_with_different_multiplicity": c["outcomes_with_different_multiplicity"],
            "rank": list(c["rank"]), "columns": list(c["columns"]),
            "same_column_names": c["column_names"][0] == c["column_names"][1],
            "fixed_effects": list(c["fixed_effects"]), "controls": list(c["controls"]),
            "host_headline_weights": [{lab(k): v for k, v in ha.items()}, {lab(k): v for k, v in hb.items()}],
            "max_host_weight_difference": c["max_host_weight_difference"],
            "max_net_weight_difference": c["max_net_weight_difference"],
            "net_weight_l1_difference": c["net_weight_l1_difference"], "net_weight_l1": list(c["net_weight_l1"])}


def real_design(which: str = ps.HEADLINE_SET, theta: float = 0.02):
    """The size-band design as size_band_run.main builds it, from the same quantity-side inputs (design.load: the
    quantities file, the dose file, market regions, fuel-mix groups and degree days; the usable flag through usable_flag;
    the ownership table; the unknown-load list). No price, revenue, bill or outcome is read. Returns (the size-band
    design, the design-inputs hash of the ten-nearest headline design on the same inputs). Not called by any test."""
    from pipeline.analysis import design as dsg
    from pipeline.analysis import size_band_run as sbr
    from pipeline.analysis import usable_flag
    q, dose, regions, fuel, dd = dsg.load()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(ps.HEADLINE_RULES, q, usable=flags.usable)
    kw = dict(ownership=ownership, usable=usable, gas=gas, ownership_of=ps.ownership_classes(q),
              unknown_load=ps.load_unknown_load(), theta=theta)
    treated, clean = dsg.split(theta, which, q, dose)
    d = sbr.build(treated, clean, q, regions, fuel, dd, **kw)
    head = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, ps.HEADLINE_RULES, **kw)
    return d, oa.design_hashes(head, usable, ps.HEADLINE_RULES.fuel_control)["design_inputs"]


def main(argv: list[str]) -> int:
    """Prints the comparison of the per-host form with every pooled variant on a real set at 2% (default: the headline
    set), quantity side only. Writes nothing. Run: python3 -I tests/size_band_pooled_form.py [set]"""
    import json
    from pipeline.analysis import size_band_run as sbr
    which = argv[0] if argv else ps.HEADLINE_SET
    d, head_sha = real_design(which)
    s = sbr.quantity_summary(d)
    out = {"set": which, "threshold": 0.02, "headline_design_inputs_sha256": head_sha, "hosts": int(len(d.hosts)),
           "hosts_sharing_a_cohort_and_a_cell": s["hosts_sharing_a_cohort_and_a_cell"],
           "first_limb_failures": [x["utility"] for x in s["first_limb_failures"]],
           "per_host_blocks_equal_pooled_union_blocks": block_sets(blocks_for(d, PER_HOST)) == block_sets(blocks_for(d, UNION)),
           "comparisons": [summary(compare(d, PER_HOST, v)) for v in POOLED]}
    print(json.dumps(out, indent=1, default=str))
    return 0


def canonical(st: dict, op: dict | None = None) -> pd.DataFrame:
    """The stacked regressors (and, given op, the weights) indexed by (cohort, cell, unit, year), sorted, for an element-
    by-element comparison of two stacks with the same rows. Raises if a key repeats (a stack with duplicated rows)."""
    r = st["rows"]
    idx = pd.MultiIndex.from_arrays([r.cohort, r.cell_region, r.size_band, r.utility_id_eia, r.state, r.year])
    if idx.has_duplicates:
        raise ValueError("the stack repeats an observed outcome within a cohort and cell: no one-to-one comparison")
    X = pd.DataFrame(st["X"], index=idx, columns=st["columns"])
    if op is not None:
        X["__weight"] = op["w"]
    return X.sort_index()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
