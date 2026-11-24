"""Is the size-band side run as built (one sub-experiment per host) the same design as the pooled form the plan intends?
Tested on invented inputs, not inferred from the absence of shared cohort-and-cell hosts (Joe, 2026-11-19: "For the
size-band form, test equivalence rather than infer it solely from the absence of shared cohort-and-cell hosts. Check
weighting, duplicated rows, controls and fixed effects on invented inputs. Report any difference and defer a new research
choice."). No file under data/ is read; every outcome is invented.

The per-host form is pipeline/analysis/size_band_run.py's design as outcome_analysis.estimate stacks it. The pooled forms
are the agent's construction of the plan's words in tests/size_band_pooled_form.py (pooled_union, pooled_intersection,
pooled_simulation_literal, pooled_union_cell_year_across_cohorts; that file says which words each follows).

The three invented worlds use test_size_band_run_invented.world: one market region, "West", over states AA to AD; twelve
comparison utilities under 10,000 customers, twelve of 10,000 to 99,999 and ten of 100,000 or more.
  W1  hosts 1 to 4 in cohorts 2013 to 2016, one per cohort, so no two share a cohort and a cell. Hosts 2 and 3 share the
      cell West by 10,000 to 99,999 in different cohorts.
  W2  hosts 2 and 3 both in cohort 2014 and in that cell, with the same eligible comparison utilities.
  W3  W2 plus a unit of host 3's own utility in state AA with 30,000 customers: in the cell, eligible for host 2 and not
      for host 3 (a unit of the host's own utility, rule 2.2).
What each comparison asserts is what is true of these worlds; where the forms differ the test asserts the difference and
its size, so that the file documents the result either way. The worlds were not tuned to obtain agreement.

Tolerances: element by element identity of regressors and weights 1e-12; estimates against w'y and between identical
forms 1e-10; recovery of a planted effect with no noise 1e-8; the documented sizes of differences 5e-5 (absolute) unless
stated.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import size_band_run as sb  # noqa: E402
import size_band_pooled_form as pf  # noqa: E402
from test_size_band_run_invented import COMPS, COOP, EFFECT, HOSTS, PUB, outcome, world  # noqa: E402

ID = 1e-12            # identity of regressors and weights
EST = 1e-10           # estimates
PLANT = 1e-8          # recovery of a planted effect with no noise
SIZE = 5e-5           # the documented size of a difference

H_SHARED = [(1, "AA", 9_000, PUB, 2013), (2, "AB", 11_000, COOP, 2014), (3, "AC", 40_000, PUB, 2014),
            (4, "AD", 300_000, COOP, 2016)]
OWN3 = (3, "AA", 30_000, PUB)                     # a unit of host 3's own utility, in the 10,000 to 99,999 band
MID_N = 12                                        # comparison utilities in the cell West by 10,000 to 99,999


def _w(hosts, comps):
    d, dd, _ = world(hosts, comps)
    return {"d": d, "dd": dd, "hosts": hosts, "comps": comps}


@pytest.fixture(scope="module")
def W1():
    return _w(HOSTS, COMPS)


@pytest.fixture(scope="module")
def W2():
    return _w(H_SHARED, COMPS)


@pytest.fixture(scope="module")
def W3():
    return _w(H_SHARED, COMPS + [OWN3])


def frame(w, noise=0.0, seed=11, effect=EFFECT):
    return outcome(w["dd"], w["hosts"], w["comps"], noise=noise, seed=seed, effect=effect)


def heterogeneous(w, effects: dict, seed=5):
    """An invented outcome with no common effect and effect_h added to host h's rows in event years 2 and 3 only."""
    f = frame(w, noise=0.0, seed=seed, effect=0.0)
    cohort = {(h[0], h[1]): h[4] for h in w["hosts"]}
    add = [effects.get((u, s), 0.0) if (u, s) in cohort and (y - cohort[(u, s)]) in ps.HEADLINE else 0.0
           for u, s, y in zip(f.utility_id_eia, f.state, f.year)]
    return f.assign(value=f.value + np.array(add))


def est(w, variant, f, controls=True):
    st = pf.form(w["d"], variant, controls=controls)
    op = pf.operator(st)
    y = pf.outcome_for(st, f, "value")
    b = pf.fit_headline(st, y)
    assert abs(b - float(op["w"] @ y)) < EST              # the implied weights reproduce the fit on this outcome
    return b, st, op


def hw(w, variant, controls=True):
    st = pf.form(w["d"], variant, controls=controls)
    return {f"{k[0]}:{k[1]}": v for k, v in pf.host_headline_weights(st, pf.operator(st)["w"]).items()}


# ---- the construction reproduces the kernel ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["W1", "W2", "W3"])
def test_the_per_host_stack_is_the_kernels_stack(name, request):
    """pf.stack on the per-host blocks returns inference_check.fixed_parts' regressors, groups and clusters exactly, and
    its rows are outcome_analysis.stacked_rows'."""
    w = request.getfixturevalue(name)
    d = w["d"]
    st = pf.form(d, pf.PER_HOST)
    f = ic.fixed_parts(oa.stackable(d), ps.GAS_SHARE)
    assert st["columns"] == f["columns"] and np.array_equal(st["X"], f["X"])
    assert all(np.array_equal(a, b) for a, b in zip(st["groups"], f["groups"])) and np.array_equal(st["cluster"], f["cluster"])
    r = oa.stacked_rows(d)
    assert np.array_equal(st["rows"][["utility_id_eia", "state", "year", "event_year", "is_host"]].to_numpy(),
                          r[["utility_id_eia", "state", "year", "event_year", "is_host"]].to_numpy())


@pytest.mark.parametrize("variant", [pf.UNION, pf.INTERSECTION, pf.LITERAL])
def test_the_pooled_stack_is_power_simulation_assemble_on_the_pooled_blocks(W3, variant):
    d = W3["d"]
    blocks = pf.blocks_for(d, variant)
    st = pf.stack(d, blocks)
    a = ps.assemble(d.windows, blocks, fuel_control=ps.GAS_SHARE, gas=d.gas)
    assert st["columns"] == a["columns"] and np.array_equal(st["X"], a["X"])
    assert all(np.array_equal(x, y) for x, y in zip(st["groups"], a["groups"]))


def test_the_per_host_estimate_is_the_modules_estimate(W2):
    """On a planted effect with noise, the per-host form here returns size_band_run.estimate_size_band's headline."""
    f = frame(W2, noise=0.05)
    b, _, _ = est(W2, pf.PER_HOST, f)
    r = sb.estimate_size_band(W2["d"], f, "value")
    assert r["estimated"] and abs(r["result"]["headline"]["log_points"] - b) < EST


# ---- W1: no two hosts share a cohort and a cell -----------------------------------------------------------------------

def test_W1_has_no_shared_cohort_and_cell(W1):
    assert sb.quantity_summary(W1["d"])["hosts_sharing_a_cohort_and_a_cell"] == []


@pytest.mark.parametrize("variant", [pf.UNION, pf.INTERSECTION, pf.LITERAL])
def test_W1_the_pooled_forms_are_the_per_host_form_exactly(W1, variant):
    """Same blocks; same rows and multiplicities; same regressors element by element, rank, controls and fixed effects;
    same implied weights on every stacked row; same estimate on any outcome."""
    d = W1["d"]
    assert pf.block_sets(pf.blocks_for(d, pf.PER_HOST)) == pf.block_sets(pf.blocks_for(d, variant))
    c = pf.compare(d, pf.PER_HOST, variant)
    assert c["rows"] == (500, 500) and c["outcomes_with_different_multiplicity"] == 0
    assert c["max_multiplicity"] == (2, 2)            # stacking repeats a comparison utility across cohorts in both forms
    assert c["rank"] == (23, 23) and c["columns"] == (23, 23) and c["column_names"][0] == c["column_names"][1]
    assert c["fixed_effects"][0] == c["fixed_effects"][1] == {"utility_effects": 50, "cell_by_year_effects": 40,
                                                              "span_dimension": 86}
    assert c["controls"][0] == c["controls"][1]
    assert c["controls"][0]["left_out"] == [2007] and c["controls"][0]["kept_but_exactly_absorbed"] == []
    (sa, sb_), (oa_, ob) = c["stacks"], c["operators"]
    A, B = pf.canonical(sa, oa_), pf.canonical(sb_, ob)
    assert A.index.equals(B.index) and list(A.columns) == list(B.columns)
    assert np.abs(A.to_numpy() - B.to_numpy()).max() < ID
    assert c["max_host_weight_difference"] < ID and c["max_net_weight_difference"] < ID
    for noise in (0.0, 0.05):
        f = frame(W1, noise=noise)
        ba, _, _ = est(W1, pf.PER_HOST, f)
        bb, _, _ = est(W1, variant, f)
        assert abs(ba - bb) < EST
        if noise == 0.0:
            assert abs(ba - EFFECT) < PLANT


def test_W1_cell_year_effects_across_cohorts_are_a_different_design(W1):
    """Hosts 2 and 3 share a cell in cohorts 2014 and 2015, whose windows overlap in nine calendar years. Coding the
    cell-by-year effect across cohorts merges those nine pairs: 31 cell-by-year effects instead of 40, the rest the same.
    The weights move, so this reading is not the per-host form even with no shared cohort and cell."""
    d = W1["d"]
    c = pf.compare(d, pf.PER_HOST, pf.ACROSS)
    assert c["rows"] == (500, 500) and c["outcomes_with_different_multiplicity"] == 0 and c["rank"] == (23, 23)
    assert c["fixed_effects"][1] == {"utility_effects": 50, "cell_by_year_effects": 31, "span_dimension": 78}
    assert c["controls"][0] == c["controls"][1]
    assert abs(c["max_net_weight_difference"] - 0.00811) < SIZE
    assert abs(c["max_host_weight_difference"] - 0.00291) < SIZE
    f = frame(W1, noise=0.0)
    assert abs(est(W1, pf.ACROSS, f)[0] - EFFECT) < PLANT          # the invented shocks are by band and calendar year
    f = frame(W1, noise=0.05)
    ba, bb = est(W1, pf.PER_HOST, f)[0], est(W1, pf.ACROSS, f)[0]
    assert abs(ba - bb) > 1e-4


# ---- W2: two hosts share a cohort and a cell, same eligible comparisons ------------------------------------------------

def test_W2_duplicated_rows(W2):
    """Per host, each of the cell's twelve comparison utilities enters twice (once in host 2's block and once in host 3's),
    each copy with its own utility effect: 120 outcome-years stacked twice. Pooled, once. The same outcome-years are
    used."""
    d = W2["d"]
    assert sb.quantity_summary(d)["hosts_sharing_a_cohort_and_a_cell"][0]["hosts"] == ["2:AB", "3:AC"]
    for v in (pf.UNION, pf.INTERSECTION, pf.LITERAL, pf.ACROSS):
        c = pf.compare(d, pf.PER_HOST, v)
        assert c["same_observed_outcomes"] and c["observed_outcomes"] == (380, 380)
        assert c["rows"] == (500, 380) and c["blocks"] == (4, 3)
        assert c["outcomes_with_different_multiplicity"] == MID_N * ps.T and c["max_multiplicity"] == (2, 1)
        ma, mb = c["multiplicity_a"], c["multiplicity_b"]
        twice = ma[ma == 2].index
        assert len(twice) == 120 and set(twice.droplevel(2)) == {(200 + i, ["AA", "AB", "AC", "AD"][i % 4]) for i in range(12)}
        assert (mb.loc[twice] == 1).all()
        assert c["fixed_effects"][0] == {"utility_effects": 50, "cell_by_year_effects": 40, "span_dimension": 86}
        assert c["fixed_effects"][1] == {"utility_effects": 38, "cell_by_year_effects": 30, "span_dimension": 65}


def test_W2_rank_and_controls_are_the_same(W2):
    c = pf.compare(W2["d"], pf.PER_HOST, pf.UNION)
    assert c["rank"] == (23, 23) and c["columns"] == (23, 23) and c["column_names"][0] == c["column_names"][1]
    assert c["controls"][0] == c["controls"][1] and c["controls"][0]["kept_but_exactly_absorbed"] == []


def test_W2_weighting_without_controls_follows_each_blocks_variance(W2):
    """With no controls (a diagnostic, not a form), the stacked fit weights each block by the within-block variance of
    the host indicator, C = m n / (m + n) for m hosts and n comparison utilities, split evenly among its hosts. Per host,
    hosts 2 and 3 each get 12/13; pooled, they get 12/14 each. Hosts 1 (12 comparisons) and 4 (10) are alone either way.
    So the per-host form gives the two hosts that share a cell more weight against hosts 1 and 4 than the pooled form."""
    C_ph = {"1:AA": 12 / 13, "2:AB": 12 / 13, "3:AC": 12 / 13, "4:AD": 10 / 11}
    C_po = {"1:AA": 12 / 13, "2:AB": 12 / 14, "3:AC": 12 / 14, "4:AD": 10 / 11}
    for v, C in ((pf.PER_HOST, C_ph), (pf.UNION, C_po)):
        got, tot = hw(W2, v, controls=False), sum(C.values())
        assert all(abs(got[h] - C[h] / tot) < ID for h in C)
    assert abs(hw(W2, pf.PER_HOST, False)["2:AB"] - 0.250951) < 1e-6 and abs(hw(W2, pf.UNION, False)["2:AB"] - 0.241690) < 1e-6


def test_W2_weighting_with_the_controls(W2):
    """Under the specification (degree days and gas share by year), the host weights per host and pooled, and the
    largest difference on any observed outcome."""
    ph, po = hw(W2, pf.PER_HOST), hw(W2, pf.UNION)
    expect_ph = {"1:AA": 0.25636, "2:AB": 0.25933, "3:AC": 0.27000, "4:AD": 0.21431}
    expect_po = {"1:AA": 0.26441, "2:AB": 0.24871, "3:AC": 0.26360, "4:AD": 0.22328}
    assert all(abs(ph[h] - expect_ph[h]) < SIZE and abs(po[h] - expect_po[h]) < SIZE for h in expect_ph)
    assert abs(sum(ph.values()) - 1) < ID and abs(sum(po.values()) - 1) < ID
    c = pf.compare(W2["d"], pf.PER_HOST, pf.UNION)
    assert abs(c["max_host_weight_difference"] - 0.01062) < SIZE and abs(c["max_net_weight_difference"] - 0.00814) < SIZE


def test_W2_estimates(W2):
    """A common planted effect is recovered exactly by both forms. A host-specific one is not weighted the same: each
    form returns the sum over hosts of its own host weight times the host's effect, and the two differ."""
    for v in (pf.PER_HOST, pf.UNION):
        assert abs(est(W2, v, frame(W2, noise=0.0))[0] - EFFECT) < PLANT
    effects = {(1, "AA"): 0.01, (2, "AB"): 0.05, (3, "AC"): 0.05, (4, "AD"): 0.01}
    f = heterogeneous(W2, effects)
    out = {}
    for v in (pf.PER_HOST, pf.UNION):
        b = est(W2, v, f)[0]
        weights = hw(W2, v)
        assert abs(b - sum(weights[f"{k[0]}:{k[1]}"] * e for k, e in effects.items())) < EST
        out[v] = b
    assert abs(out[pf.PER_HOST] - 0.031173) < SIZE and abs(out[pf.UNION] - 0.030492) < SIZE
    f = frame(W2, noise=0.05)
    assert abs(est(W2, pf.PER_HOST, f)[0] - est(W2, pf.UNION, f)[0]) > 1e-4


# ---- W3: two hosts share a cohort and a cell, eligibility differs ------------------------------------------------------

def test_W3_the_unit_is_eligible_for_host_2_and_not_host_3(W3):
    c = {x["host"]: x for x in W3["d"].cells}
    assert "3:AA" in c["2:AB"]["comparisons"] and "3:AA" not in c["3:AC"]["comparisons"]
    assert c["2:AB"]["comparison_utilities_in_its_cell"] == 13 and c["3:AC"]["comparison_utilities_in_its_cell"] == 12


def test_W3_what_each_pooled_construction_does_with_the_unit(W3):
    """Per host: 3:AA is host 2's comparison only, once (10 rows). pooled_union and pooled_simulation_literal: it sits in
    the one block that holds hosts 2 and 3, so it is a comparison for host 3 too, and host 3's ownership exclusion is not
    kept. pooled_intersection: it leaves the design, so host 2 loses a unit eligible for it."""
    d = W3["d"]
    key = (3, "AA")
    for v, n_rows, with_host3 in ((pf.PER_HOST, 10, False), (pf.UNION, 10, True), (pf.LITERAL, 10, True),
                                  (pf.INTERSECTION, 0, None)):
        r = pf.form(d, v)["rows"]
        mine = r[(r.utility_id_eia == 3) & (r.state == "AA")]
        assert len(mine) == n_rows
        if n_rows:
            assert any((3, "AC") in h for h in mine.block_hosts) is with_host3
    assert pf.block_sets(pf.blocks_for(d, pf.UNION)) == pf.block_sets(pf.blocks_for(d, pf.LITERAL))
    _, cells = pf.pooled_blocks(d, "union")
    assert key not in [h for x in cells for h in x["hosts"]]


def test_W3_rows_rank_controls_and_fixed_effects(W3):
    d = W3["d"]
    u = pf.compare(d, pf.PER_HOST, pf.UNION)
    assert u["rows"] == (510, 390) and u["same_observed_outcomes"] and u["outcomes_with_different_multiplicity"] == 120
    assert u["fixed_effects"][0]["utility_effects"] == 51 and u["fixed_effects"][1]["utility_effects"] == 39
    i = pf.compare(d, pf.PER_HOST, pf.INTERSECTION)
    assert i["rows"] == (510, 380) and not i["same_observed_outcomes"] and i["observed_outcomes"] == (390, 380)
    assert i["outcomes_with_different_multiplicity"] == 130
    for c in (u, i):
        assert c["rank"] == (23, 23) and c["controls"][0] == c["controls"][1]


def test_W3_weighting_and_estimates(W3):
    d = W3["d"]
    u, i = pf.compare(d, pf.PER_HOST, pf.UNION), pf.compare(d, pf.PER_HOST, pf.INTERSECTION)
    assert abs(u["max_net_weight_difference"] - 0.01751) < SIZE and abs(u["max_host_weight_difference"] - 0.01051) < SIZE
    assert abs(i["max_net_weight_difference"] - 0.01866) < SIZE and abs(i["max_host_weight_difference"] - 0.01157) < SIZE
    # The weight the unit's outcomes take (summed magnitudes over its calendar years): per host and union, not intersection.
    na = u["net_weights"][0].loc[(3, "AA")].abs().sum()
    nb = u["net_weights"][1].loc[(3, "AA")].abs().sum()
    assert na > 1e-3 and nb > 1e-3 and abs(na - nb) > 1e-4
    assert (3, "AA") not in {k[:2] for k in i["net_weights"][1][i["net_weights"][1] != 0].index}
    for v in (pf.PER_HOST, pf.UNION, pf.INTERSECTION):
        assert abs(est(W3, v, frame(W3, noise=0.0))[0] - EFFECT) < PLANT
    f = frame(W3, noise=0.05)
    b = {v: est(W3, v, f)[0] for v in (pf.PER_HOST, pf.UNION, pf.INTERSECTION)}
    assert abs(b[pf.PER_HOST] - b[pf.UNION]) > 1e-4 and abs(b[pf.PER_HOST] - b[pf.INTERSECTION]) > 1e-4


# ---- the selected procedure's reading, on one invented outcome with noise ---------------------------------------------

@pytest.mark.parametrize("name, same, d_est, d_se", [("W1", True, 0.0, 0.0), ("W2", False, 0.004331, 0.001647),
                                                     ("W3", False, 0.003436, 0.001503)])
def test_the_selected_procedures_reading_per_host_and_pooled(name, same, d_est, d_se, request):
    """kernel_reading on the per-host stack is the module's reading (estimate, CR2 standard error, range) to 1e-10. The
    pooled union form gives the same reading in W1 and a different one in W2 and W3: pooled minus per host, the
    estimate and the standard error move by the sizes given (one invented outcome, noise 0.05, seed 11)."""
    w = request.getfixturevalue(name)
    f = frame(w, noise=0.05)
    m = sb.estimate_size_band(w["d"], f, "value")["result"]["headline"]
    r = {}
    for v in (pf.PER_HOST, pf.UNION):
        st = pf.form(w["d"], v)
        r[v] = pf.kernel_reading(st, pf.outcome_for(st, f, "value"))
        assert r[v]["numerical_failure"] is None
    p = r[pf.PER_HOST]
    assert abs(p["estimate"] - m["log_points"]) < EST and abs(p["se"] - m["standard_error_log_points"]) < EST
    assert abs(p["lo"] - m["range_90_log_points"][0]) < EST and abs(p["hi"] - m["range_90_log_points"][1]) < EST
    de, ds = r[pf.UNION]["estimate"] - p["estimate"], r[pf.UNION]["se"] - p["se"]
    if same:
        assert abs(de) < EST and abs(ds) < EST
    else:
        assert abs(de - d_est) < SIZE and abs(ds - d_se) < SIZE


# ---- the checks can fail ----------------------------------------------------------------------------------------------

def test_the_W1_identity_check_fails_when_the_pooled_blocks_are_broken(W1, monkeypatch):
    """Deliberate break in the test process: the pooled blocks lose one comparison utility. The identity test must fail."""
    real = pf.pooled_blocks

    def broken(d, comparisons="union"):
        blocks, cells = real(d, comparisons)
        g, tr, comp = blocks[0]
        return [(g, tr, comp[1:])] + blocks[1:], cells

    monkeypatch.setattr(pf, "pooled_blocks", broken)
    with pytest.raises(AssertionError):
        test_W1_the_pooled_forms_are_the_per_host_form_exactly(W1, pf.UNION)


def test_the_support_file_reads_nothing():
    import ast
    src = Path(pf.__file__).read_text()
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
             for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)}
    assert not {"load_outcomes", "read_listed_outcomes", "read_parquet", "read_csv"} & calls
    assert "data/blind" not in src and "availability" not in src
