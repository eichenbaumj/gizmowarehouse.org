"""The power simulation's machinery, on synthetic utilities. No real prices."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
REGIONS = (("PJM", ["OH", "PA", "VA"]), ("West", ["OR", "AZ", "UT"]))


def synthetic(n_per_region=30, noise=0.02, seed=1):
    """Two regions, three states each, utilities observed 2001-2025 with a region-by-year shock and a utility level."""
    rng = np.random.default_rng(seed)
    rows, attrs = [], []
    uid = 0
    for region, states in REGIONS:
        shock = rng.normal(0, 0.05, 25).cumsum()
        for i in range(n_per_region):
            uid += 1
            st = states[i % 3]
            level = rng.normal(2.4, 0.2)
            for t, year in enumerate(range(2001, 2026)):
                rows.append((uid, st, year, level + shock[t] + rng.normal(0, noise)))
            attrs.append((uid, st, region, "cooperative" if i % 2 else "investor_owned", 5_000 * (1 + i)))
    p = pd.DataFrame(rows, columns=KEY + ["year", "log_price"])
    a = pd.DataFrame(attrs, columns=KEY + ["region", "ownership", "res_customers"]).set_index(KEY)
    return p, a


def stacks_for(p, a, cohorts):
    unit_code = {k: i for i, k in enumerate(a.index)}
    state_code = {s: i for i, s in enumerate(sorted({k[1] for k in a.index}))}
    return {g: ps.Stack(g, ps.balanced(p, "log_price", range(g - ps.PRE, g + ps.POST + 1)), a, unit_code, state_code)
            for g in cohorts}, len(unit_code)


def real_list():
    return pd.DataFrame([
        dict(cohort=2012, region="PJM", ownership="investor_owned", log_size=np.log(40_000), state="OH"),
        dict(cohort=2012, region="West", ownership="cooperative", log_size=np.log(20_000), state="OR"),
        dict(cohort=2016, region="PJM", ownership="cooperative", log_size=np.log(90_000), state="PA"),
        dict(cohort=2016, region="PJM", ownership="investor_owned", log_size=np.log(40_000), state="OH"),
        dict(cohort=2020, region="West", ownership="investor_owned", log_size=np.log(60_000), state="AZ"),
    ])


RNG = lambda seed=0: np.random.default_rng(seed)  # noqa: E731


@pytest.mark.parametrize("form", ps.SIZE_FORMS)
def test_estimator_returns_zero_and_the_planted_effect_exactly_without_noise(form):
    p, a = synthetic(noise=0.0)
    stacks, n = stacks_for(p, a, [2012, 2016, 2020])
    picks, _ = ps.pick_stand_ins(real_list(), stacks, n, RNG(3))
    blocks, lost = ps.build_blocks(stacks, picks, form, n)
    zero, two, five = ps.estimate(stacks, blocks, (0.0, np.log(1.02), np.log(1.05)), RNG(), boot=50)
    assert lost == 0
    assert zero["est"] == pytest.approx(0.0, abs=1e-12)
    assert two["est"] == pytest.approx(np.log(1.02), abs=1e-12)
    assert five["est"] == pytest.approx(np.log(1.05), abs=1e-12)
    assert zero["max_abs_early"] == pytest.approx(0.0, abs=1e-12)


def test_planting_shifts_every_draw_by_the_planted_amount_and_leaves_the_range_alone():
    p, a = synthetic(noise=0.03)
    stacks, n = stacks_for(p, a, [2012, 2016, 2020])
    rng = RNG(5)
    for _ in range(20):
        picks, _ = ps.pick_stand_ins(real_list(), stacks, n, rng)
        blocks, _ = ps.build_blocks(stacks, picks, "none", n)
        zero, five = ps.estimate(stacks, blocks, (0.0, 0.05), rng, boot=199)
        assert five["est"] - zero["est"] == pytest.approx(0.05, abs=1e-10)
        assert five["se"] == pytest.approx(zero["se"], rel=1e-8)
        assert five["hi"] - five["lo"] == pytest.approx(zero["hi"] - zero["lo"], rel=1e-8)
        assert five["pre_wald"] == pytest.approx(zero["pre_wald"], rel=1e-6)     # the planted path starts at entry


def test_estimates_center_on_zero_and_the_range_covers_it_about_nine_times_in_ten():
    """Fresh synthetic prices for every draw, so the draws are independent.

    (Within one data set the stand-ins come from the same few utilities in each state, so
    draws repeat; that is a property of keeping the hosts' state structure, not of the estimator.)
    """
    rng = RNG(11)
    est, covered = [], []
    for seed in range(200):
        p, a = synthetic(n_per_region=30, noise=0.03, seed=100 + seed)
        stacks, n = stacks_for(p, a, [2012, 2016, 2020])
        blocks, _ = ps.build_blocks(stacks, ps.pick_stand_ins(real_list(), stacks, n, rng)[0], "none", n)
        r = ps.estimate(stacks, blocks, (0.0,), rng, boot=199)[0]
        est.append(r["est"])
        covered.append(r["lo"] <= 0 <= r["hi"])
    assert abs(np.mean(est)) < 3 * np.std(est) / np.sqrt(len(est))
    assert 0.80 <= np.mean(covered) <= 0.99          # six clusters and five hosts: wide, but in the neighbourhood of 90%


def brute_force(stacks, blocks, v_by_state):
    """The same regression and one wild-cluster replication, done the long way on the stacked rows."""
    Xs, ys, cl = [], [], []
    for g, tr, comp in blocks:
        s = stacks[g]
        rows = np.concatenate([tr, comp])
        Y = s.y[rows]
        td = np.zeros(len(rows)); td[:len(tr)] = 1.0; td -= td.mean()  # noqa: E702
        ys.append((Y - Y.mean(1, keepdims=True) - Y.mean(0, keepdims=True) + Y.mean()).ravel())
        Xs.append(np.einsum("i,kt->itk", td, ps.YP).reshape(len(rows) * ps.T, len(ps.EVENT_TIMES)))
        cl.append(np.repeat(s.state[rows], ps.T))
    X, y, c = np.vstack(Xs), np.concatenate(ys), np.concatenate(cl)
    codes = np.unique(c, return_inverse=True)[1]
    G, (N, K) = codes.max() + 1, X.shape
    factor = (G / (G - 1)) * ((N - 1) / (N - K))
    inv = np.linalg.inv(X.T @ X)

    def fit(yy):
        b = inv @ (X.T @ yy)
        u = yy - X @ b
        sc = np.column_stack([np.bincount(codes, weights=X[:, k] * u, minlength=G) for k in range(K)])
        V = factor * inv @ (sc.T @ sc) @ inv
        return b, u, float(ps.W_HEAD @ b), float(np.sqrt(ps.W_HEAD @ V @ ps.W_HEAD))

    b, u, est, se = fit(y)
    v = np.array([v_by_state[k] for k in np.unique(c)])[codes]
    _, _, est_star, se_star = fit(X @ b + v * u)
    return est, se, (est_star - est) / se_star


@pytest.mark.parametrize("form", ps.SIZE_FORMS)
def test_closed_form_matches_the_regression_and_the_bootstrap_done_the_long_way(form):
    p, a = synthetic(noise=0.03, seed=4)
    stacks, n = stacks_for(p, a, [2012, 2016, 2020])
    picks, _ = ps.pick_stand_ins(real_list(), stacks, n, RNG(8))
    blocks, _ = ps.build_blocks(stacks, picks, form, n)
    res = ps.estimate(stacks, blocks, (0.0,), RNG(), boot=10)[0]
    states = sorted({k[1] for k in a.index})
    code = {s: i for i, s in enumerate(states)}
    rng = RNG(21)
    for _ in range(5):
        v = rng.integers(0, 2, len(states)) * 2.0 - 1.0
        est, se, t_long = brute_force(stacks, blocks, {code[s]: v[i] for i, s in enumerate(states)})
        assert res["est"] == pytest.approx(est, abs=1e-12) and res["se"] == pytest.approx(se, rel=1e-9)
        # rebuild the closed form's inputs the way estimate() does, with these weights
        zs, tds, cl = [], [], []
        rows_n = 0
        for g, tr, comp in blocks:
            s = stacks[g]
            rows = np.concatenate([tr, comp])
            Y = s.y[rows]
            td = np.zeros(len(rows)); td[:len(tr)] = 1.0; td -= td.mean()  # noqa: E702
            zs.append((Y - Y.mean(0, keepdims=True)) @ ps.YP.T); tds.append(td); cl.append(s.state[rows])  # noqa: E702
            rows_n += len(rows) * ps.T
        Z, td, c = np.vstack(zs), np.concatenate(tds), np.concatenate(cl)
        uniq, codes = np.unique(c, return_inverse=True)
        G, C = len(uniq), float(td @ td)
        c_g = np.bincount(codes, weights=td ** 2, minlength=G)
        s1 = np.column_stack([np.bincount(codes, weights=td * Z[:, k], minlength=G) for k in range(len(ps.EVENT_TIMES))])
        S = s1 - np.outer(c_g, ps.M @ (ps.M_INV @ s1.sum(0) / C))
        factor = (G / (G - 1)) * ((rows_n - 1) / (rows_n - len(ps.EVENT_TIMES)))
        t_closed = ps.bootstrap_t(S @ (ps.M_INV @ ps.W_HEAD) / C, c_g / C, factor, None, v=v[uniq][None, :])[0]
        assert t_closed == pytest.approx(t_long, rel=1e-8)


def test_interval_is_the_bootstrap_t_interval():
    tstar = np.linspace(-3, 2, 501)                       # skewed: more mass below zero
    lo, hi = ps.interval(1.0, 0.5, tstar, level=0.9)
    assert lo == pytest.approx(1.0 - 0.5 * np.quantile(tstar, 0.95))
    assert hi == pytest.approx(1.0 - 0.5 * np.quantile(tstar, 0.05))
    assert hi - 1.0 > 1.0 - lo                            # the long lower tail of t* stretches the upper end


def test_a_stand_in_is_used_once_and_comes_from_the_hosts_own_state_and_ownership_when_it_can():
    p, a = synthetic()
    stacks, n = stacks_for(p, a, [2012, 2016, 2020])
    real = real_list()
    picks, how = ps.pick_stand_ins(real, stacks, n, RNG(2))
    chosen = [stacks[g].keys[j] for g, j, _ in picks]
    assert len(set(chosen)) == len(real)
    assert how["tiers"]["own_state_and_ownership"] == len(real)
    for g, j, i in picks:
        r = real.iloc[i]
        assert (g, stacks[g].state_name[j], stacks[g].ownership[j]) == (r.cohort, r.state, r.ownership)
    assert len(how["size_gaps"]) == len(real) and max(how["size_gaps"]) < 1.5


def test_hosts_in_a_state_with_no_candidates_share_one_substitute_state():
    p, a = synthetic()
    stacks, n = stacks_for(p, a, [2012])
    real = pd.DataFrame([dict(cohort=2012, region="PJM", ownership="cooperative", log_size=np.log(30_000 + 9_000 * i), state="WV")
                         for i in range(4)])
    for seed in range(5):
        picks, how = ps.pick_stand_ins(real, stacks, n, RNG(seed))
        states = {stacks[g].state_name[j] for g, j, _ in picks}
        assert len(states) == 1 and states <= {"OH", "PA", "VA"}          # one state, in the same market region
        assert how["tiers"]["substitute_state_and_ownership"] == 4


def test_stand_in_falls_back_when_the_region_has_none_of_that_ownership():
    p, a = synthetic()
    stacks, n = stacks_for(p, a, [2012])
    real = pd.DataFrame([dict(cohort=2012, region="PJM", ownership="public", log_size=np.log(30_000), state="OH")])
    picks, how = ps.pick_stand_ins(real, stacks, n, RNG(2))
    assert how["tiers"]["own_state"] == 1
    assert stacks[2012].state_name[picks[0][1]] == "OH"


def test_size_band_compares_within_the_band_and_matching_takes_the_nearest():
    p, a = synthetic()
    stacks, n = stacks_for(p, a, [2012])
    s = stacks[2012]
    real = real_list().iloc[:2]
    picks, _ = ps.pick_stand_ins(real, stacks, n, RNG(1))
    for g, tr, comp in ps.build_blocks(stacks, picks, "size_band", n)[0]:
        assert set(s.band[comp]) == set(s.band[tr]) and set(s.region[comp]) == set(s.region[tr])
    blocks, _ = ps.build_blocks(stacks, picks, "nearest_in_size", n)
    assert len(blocks) == len(picks)
    for g, tr, comp in blocks:
        assert len(tr) == 1 and len(comp) == ps.MATCH_K
        others = np.flatnonzero((s.region == s.region[tr[0]]) & ~np.isin(np.arange(len(s.keys)), [j for _, j, _ in picks]))
        far = np.setdiff1d(others, comp)
        assert np.abs(s.size[comp] - s.size[tr[0]]).max() <= np.abs(s.size[far] - s.size[tr[0]]).min() + 1e-12
    assert list(ps.size_band([9_999, 10_000, 99_999, 100_000])) == [0, 1, 1, 2]


def test_a_host_with_no_comparison_utility_in_its_cell_is_counted_as_dropped():
    p, a = synthetic(n_per_region=3)
    a = a.copy()
    a["res_customers"] = [5_000, 6_000, 500_000, 5_000, 6_000, 7_000]       # one large utility alone in its band
    stacks, n = stacks_for(p, a, [2012])
    j = int(np.flatnonzero(stacks[2012].band == 2)[0])
    blocks, lost = ps.build_blocks(stacks, [(2012, j, 0)], "size_band", n)
    assert lost == 1 and blocks == []
    blocks, lost = ps.build_blocks(stacks, [(2012, j, 0)], "nearest_in_size", n)
    assert lost == 0 and len(blocks[0][2]) == 2                           # matching still finds its region's two others


def test_a_stand_in_is_not_a_comparison_utility_in_another_cohort():
    """Moving one stand-in's cohort must not leave it in the other cohort's comparison group."""
    p, a = synthetic(noise=0.03)
    stacks, n = stacks_for(p, a, [2012, 2016])
    real = real_list().iloc[:3]
    picks, _ = ps.pick_stand_ins(real, stacks, n, RNG(4))
    est = lambda st: ps.estimate(st, ps.build_blocks(st, picks, "none", n)[0], (0.0,), RNG(), boot=10)[0]["est"]  # noqa: E731
    base = est(stacks)
    # Corrupt a 2012 stand-in's price in the years after its own window (2016 onward):
    # the estimate may only change through the 2016 cohort if the utility were still a comparison there.
    g, j, _ = next(x for x in picks if x[0] == 2012)
    key = stacks[2012].keys[j]
    p2 = p.copy()
    p2.loc[(p2.utility_id_eia == key[0]) & (p2.state == key[1]) & (p2.year >= 2016), "log_price"] += 5.0
    stacks2, _ = stacks_for(p2, a, [2012, 2016])
    assert est(stacks2) == pytest.approx(base, abs=1e-12)


def test_per_point_slope_is_recovered_exactly_and_ignores_utility_and_cell_year_effects():
    rng = RNG(3)
    n, T = 40, 21
    cell = np.array(["PJM|0", "PJM|1", "West|0", "West|1"])[np.arange(n) % 4]
    state = np.array(["OH", "PA", "OR", "AZ", "VA", "UT"])[np.arange(n) % 6]
    x = np.zeros((n, T))
    x[:8, 10:] = rng.uniform(1, 12, (8, 1)) * np.linspace(0.2, 1, T - 10)       # eight hosts whose load share grows
    level = rng.normal(2.4, 0.3, (n, 1))
    shock = {c: rng.normal(0, 0.05, T).cumsum() for c in np.unique(cell)}
    y = level + np.vstack([shock[c] for c in cell]) + 0.004 * x                   # 0.4% of price per point
    res = ps.slope(x, y, cell, state, rng, boot=50)
    assert res["est"] == pytest.approx(0.004, abs=1e-12)
    xf, yf = ps.per_point_frame("long_difference", x[:, [3, 4, 5, 18, 19, 20]], y[:, [3, 4, 5, 18, 19, 20]])
    assert xf.shape == (n, 1)
    assert ps.slope(xf, yf, cell, state, rng, boot=50)["est"] == pytest.approx(0.004, abs=1e-12)


def test_smallest_detectable_is_the_effect_found_in_four_draws_of_five():
    rng = RNG(9)
    est0, half = rng.normal(0, 0.01, 1000), np.abs(rng.normal(0.016, 0.002, 1000))
    mde = ps.smallest_detectable(est0, half, bar=0.8)
    detected = lambda t: np.mean(est0 + t - half > 0)  # noqa: E731
    assert detected(mde + 1e-4) >= 0.8
    assert detected(mde - 1e-3) < 0.8
    assert detected(mde) == pytest.approx(0.8, abs=0.002)


def test_market_region_from_balancing_authority_and_state_fallback():
    q = pd.DataFrame({"utility_id_eia": [1, 2, 3, 4], "state": ["OH", "OH", "OR", "OH"], "year": [2020] * 4,
                      "balancing_authority": ["PJM", "PJM", "BPAT", "UNK"]})
    r = ps.market_regions(q)
    assert r[(1, "OH")] == "PJM" and r[(3, "OR")] == "West"
    assert r[(4, "OH")] == "PJM"       # unknown code takes its state's most common region


def test_market_region_is_by_utility_and_state_and_changes_are_listed():
    from pipeline.electricity import market_region as mr
    q = pd.DataFrame({
        "utility_id_eia": [7, 7, 7, 7, 7, 9, 9], "state": ["ND", "ND", "ND", "WY", "WY", "OK", "OK"],
        "year": [2012, 2013, 2017, 2013, 2017, 2013, 2014],
        "balancing_authority": [None, "SWPP", "MISO", "WACM", "WACM", "GRDA", "SWPP"]})
    fixed = mr.fixed(q)
    assert fixed[(7, "ND")] == "MISO"                      # the region most recently reported
    assert fixed[(7, "WY")] == "West"                      # the same utility id, another state, another market
    ch = mr.changes(q).set_index(["utility_id_eia", "state"])
    assert list(ch.index) == [(7, "ND")]
    assert ch.loc[(7, "ND"), "first_change_year"] == 2017
    assert "SPP to MISO in 2017" in ch.loc[(7, "ND"), "path"]
    # Grand River Dam's own 2013 code and the pool's consolidated code are the same market, so no change
    assert (9, "OK") not in ch.index
    by_year = mr.by_year(q).set_index(["utility_id_eia", "state", "year"]).region
    assert (7, "ND", 2012) not in by_year.index and by_year[(7, "ND", 2013)] == "SPP"


def test_every_code_in_the_panel_has_a_region():
    """A code with no region silently falls to the state's most common one; this keeps the map complete."""
    from pipeline.electricity import market_region as mr, panel
    path = panel.INTERIM / "panel_quantities.parquet"
    if not path.exists():
        pytest.skip("panel not built")
    codes = set(pd.read_parquet(path, columns=["balancing_authority"]).balancing_authority.dropna())
    assert codes - set(mr.REGION_OF_BA) == set()


def test_design_keeps_hosts_and_crypto_hosts_out_of_the_comparison_group():
    q = pd.DataFrame({"utility_id_eia": [1, 2, 3, 4, 5, 6], "state": ["OH"] * 6, "year": [2020] * 6})
    dose = pd.DataFrame({
        "utility_id_eia": [1, 1, 2, 3, 4, 6], "state": ["OH"] * 6, "year": [2010, 2015, 2015, 2015, 2024, 2015],
        "dose": [0.001, 0.03, 0.004, 0.0, 0.03, np.nan], "crypto_mw": [0, 0, 0, 5.0, 0, 0],
        "base_retail_gwh": [1000, 1000, 1000, 1000, 1000, np.nan]})
    treated, clean = ps.design(q, dose, 0.02)
    assert list(treated.utility_id_eia) == [1] and list(treated.cohort) == [2015]   # 4 crosses too late to be a cohort
    assert sorted(clean.utility_id_eia) == [2, 5]     # 3 is a crypto host (4.4%), 4 a later host, 6 has no sales base


def test_a_utility_on_the_price_hold_is_on_neither_side(tmp_path):
    q = pd.DataFrame({"utility_id_eia": [1, 2, 3], "state": ["OH"] * 3, "year": [2020] * 3})
    dose = pd.DataFrame({"utility_id_eia": [1], "state": ["OH"], "year": [2015], "dose": [0.03], "crypto_mw": [0.0], "base_retail_gwh": [1000.0]})
    treated, clean = ps.design(q, dose, 0.02, hold={(3, "OH")})
    assert list(treated.utility_id_eia) == [1] and list(clean.utility_id_eia) == [2]      # 3 has no load and is still not a comparison
    f = tmp_path / "hold.csv"
    f.write_text("utility_id_eia,state,name,why\n3,OH,Somewhere,held\n")
    assert ps.price_hold(f) == {(3, "OH")} and ps.price_hold(tmp_path / "missing.csv") == set()
    held = ps.price_hold()                                                                 # the committed list: every row has a reason
    rows = pd.read_csv(ps.PRICE_HOLD)
    assert len(held) == len(rows) and rows.why.str.len().gt(20).all()


def write_reports(tmp_path, by_years=None, lists=None):
    dating = {"2%": {"dependent_utilities": ["803:AZ"]}, "5%": {"dependent_utilities": ["803:AZ", "4110:IL"]}}
    if by_years:
        dating["2%"] = {"dependent_utilities": sorted(set().union(*by_years.values())), "dependent_utilities_by_years_earlier": by_years}
    (tmp_path / "dating_sensitivity.json").write_text(json.dumps({"thresholds": dating}))
    (tmp_path / "buildout_sensitivity.json").write_text(json.dumps(
        {"thresholds": {"2%": {"utilities_still_unsettled": [{"utility": "14006:OH"}]}, "5%": {"utilities_still_unsettled": []}}}))
    if lists is not None:
        (tmp_path / "treatment_bounds.json").write_text(json.dumps({"thresholds": {"2%": {"lists": lists}, "5%": {"lists": lists}}}))


def test_dates_and_histories_join_undated_sites_unverified_histories_and_rappahannock(tmp_path):
    write_reports(tmp_path)
    assert set(ps.dates_and_histories_reasons(0.02, tmp_path)) == {(803, "AZ"), (14006, "OH")}
    assert set(ps.dates_and_histories_reasons(0.05, tmp_path)) == {(803, "AZ"), (4110, "IL"), (40228, "VA")}


def test_the_headline_set_drops_the_ten_year_case_and_reads_the_bounds_lists(tmp_path):
    write_reports(tmp_path, by_years={"3_years": ["803:AZ"], "5_years": ["803:AZ", "1:CO"], "10_years": ["803:AZ", "1:CO", "9:WY"]},
                  lists={"does_not_keep_its_place": ["16572:AZ"], "texas_hosts_held_under_ruling_3": ["7:TX"]})
    reasons = ps.dates_and_histories_reasons(0.02, tmp_path)
    assert reasons[(9, "WY")] == [ps.TEN_YEAR_REASON]                      # depends on the ten-year case and on nothing nearer
    headline = ps.set_aside(0.02, tmp_path)
    assert headline == {(803, "AZ"), (1, "CO"), (14006, "OH"), (16572, "AZ"), (7, "TX")}
    assert ps.set_aside(0.02, tmp_path, ten_year_case=True) == headline | {(9, "WY")}


def test_set_aside_refuses_to_run_without_the_bounds_lists(tmp_path):
    write_reports(tmp_path)
    with pytest.raises(FileNotFoundError):
        ps.set_aside(0.02, tmp_path)
    (tmp_path / "treatment_bounds.json").write_text(json.dumps({"thresholds": {"2%": {}}}))   # written before D-46
    with pytest.raises(KeyError):
        ps.set_aside(0.02, tmp_path)


def form(drift, width, covers=0.9, dropped=0.0):
    return {"mean_estimate_nothing_planted": drift, "range_width_mean": width, "interval_covers_zero": covers,
            "hosts_left_without_a_comparison_utility_per_draw": dropped}


def test_size_adjustment_is_chosen_by_the_rule_written_before_the_run():
    run = lambda **f: {"hosts_in_the_panel_for_their_whole_window": 30, "size_adjustment": {"none": form(0.8, 5.0), **f}}  # noqa: E731
    # smallest placebo drift wins
    assert ps.choose_size_form(run(size_band=form(0.5, 6.0), nearest_in_size=form(-0.1, 7.0)))["chosen"] == "nearest_in_size"
    # within a tenth of a point of each other, the narrower range wins
    assert ps.choose_size_form(run(size_band=form(0.15, 6.0), nearest_in_size=form(-0.1, 7.0)))["chosen"] == "size_band"
    # a form that loses more than one host in ten, or whose intervals are miscalibrated, is not eligible
    assert ps.choose_size_form(run(size_band=form(0.0, 4.0, dropped=3.5), nearest_in_size=form(0.4, 7.0)))["chosen"] == "nearest_in_size"
    assert ps.choose_size_form(run(size_band=form(0.0, 4.0, covers=0.80), nearest_in_size=form(0.4, 7.0)))["chosen"] == "nearest_in_size"
    assert ps.choose_size_form(run(size_band=form(0.0, 4.0, covers=0.80), nearest_in_size=form(0.4, 7.0, covers=0.99)))["chosen"] is None


# ---- the committed run (docs/DECISIONS.md, D-31 and D-32) -------------------

def test_committed_run_is_the_one_the_standard_describes_and_recovers_what_was_planted():
    """The frozen report is the run of D-38: its seed, its sets, and the things a correct run must show."""
    r = json.loads((Path(__file__).resolve().parents[1] / "data" / "frozen" / "power_simulation.json").read_text())
    _check_committed_run(r, ps.SELECTED)


def test_labelled_run_of_the_bootstrap_as_built_if_on_file_is_the_one_the_standard_describes():
    """The labelled run of procedure A (D-59 rule 4.7), when one has been made: its own file, 999 replications, the same checks."""
    path = ps.output_path("power_simulation.json", ps.HEADLINE_RULES, ps.AS_BUILT)
    if not path.exists():
        pytest.skip(f"{path.name} has not been run; the headline file is the selected procedure's (C)")
    _check_committed_run(json.loads(path.read_text()), ps.AS_BUILT)


def _check_committed_run(r: dict, procedure: str) -> None:
    # The headline file is written only under the selected procedure (C: CR2 with Satterthwaite degrees of freedom, no
    # bootstrap, so no replication count); the labelled run of the bootstrap as built (A) has 999 and its own file
    # (power_simulation.main, output_path; step-e rules E6.1 step 9; D-59 rule 4.7).
    assert r["procedure"]["procedure"] == procedure
    assert r["procedure"]["range"] == ps.PROCEDURE_TEXT[procedure]["range"]
    if procedure == ps.SELECTED:
        assert r["procedure"]["stage2_verdicts"] == {"range": "passed", "early_years_test": "passed"}
    boot = ps.BOOT if procedure == ps.AS_BUILT else None
    assert r["seed"] == ps.SEED_D38 and r["draws"] == ps.DRAWS and r["bootstrap_replications"] == boot
    assert "D-38" in r["standard"]
    if "main_set" in r["new_host_estimate"]["2%"]:
        pytest.skip("the frozen report is still the D-39 run on the sets as they stood before D-46; it is rerun after job V")
    assert set(r["new_host_estimate"]["2%"]) == {ps.HEADLINE_SET, "every_cohort_utility", ps.TEN_YEAR_SET}
    for theta, sets in r["new_host_estimate"].items():
        for name, x in sets.items():
            assert x["draws"] == ps.DRAWS and x["comparison_form"] == "nearest_in_size"
            assert x.get("bootstrap_replications", boot) == boot, (theta, name)
            assert x["hosts_in_the_panel_for_their_whole_window"] <= x["hosts_as_built"]
            assert abs(sum(x["stand_in_match"].values()) - 1.0) < 0.01
            exact, wrong = x["start_years_exact"], x["start_years_misdated"]
            # with the start years right the planted effect comes back whole; with them wrong, less of it does
            assert exact["planted_5pct"]["share_of_the_planted_effect_recovered"] == pytest.approx(1.0, abs=1e-6), (theta, name)
            share_wrong = wrong["planted_5pct"]["share_of_the_planted_effect_recovered"]
            assert 0.3 < share_wrong <= exact["planted_5pct"]["share_of_the_planted_effect_recovered"] + 1e-6, (theta, name)
            # Strictly less than whole only where some drawn error costs the headline. By planted_path (reference year -3,
            # headline years 2 and 3), errors of 0, -1 and -2 (true crossing up to two years earlier) cost nothing; +1 and
            # later, -3 and earlier, and never (60) cost something. within_1_year (|error| <= 1, rounded to three decimals)
            # is a coarser proxy for that: too loose for +1, which it counts as within a year but which costs a sixth,
            # and too strict for -2, which it does not count but which costs nothing. The committed report does not record
            # the share of errors one year later, so the exact condition cannot be read from it. Where within_1_year is
            # 1.0 only "no more than with exact start years" is checked, here and for the smallest increase below. The
            # direct guard that errors are applied, and at what cost, is tests/test_date_errors_invented.py.
            misdating_can_cost = x["date_errors_drawn_for_these_hosts"]["within_1_year"] < 1.0
            if misdating_can_cost:
                assert share_wrong < 1.0, (theta, name)
            # the keys were renamed at Stop 3 (wording only); the committed report keeps the old ones until it is rerun
            key = next(k for k in (ps.SMALLEST_INCREASE_KEY, "smallest_effect_whose_range_excludes_zero_in_80pct_of_draws") if k in exact)
            if exact[key] is None:              # no effect on the grid (up to 12%) is told from zero four times in five: a set this small sees nothing that size
                assert wrong[key] is None
            elif misdating_can_cost:
                assert wrong[key] is None or wrong[key] > exact[key], (theta, name)
            else:
                assert wrong[key] is None or wrong[key] >= exact[key], (theta, name)
            rates = list(exact.get(ps.POWER_BY_TAU_KEY, exact.get("range_excludes_zero_by_planted_pct")).values())
            assert all(b >= a - 1e-9 for a, b in zip(rates, rates[1:]))            # a larger effect is never harder to see
            assert x["nothing_planted"]["range_width_median"] > 0
        assert sets[ps.HEADLINE_SET]["hosts_as_built"] <= sets["every_cohort_utility"]["hosts_as_built"]   # the headline set is never the larger one
    for name, c in r["early_years_test_size_on_made_up_prices"].items():
        lo, hi = c["band"]
        assert c["datasets"] == ps.SIZE_DATASETS and c["inside_the_band_written_in_advance"] == (lo <= c["early_years_test_fails_at_p_below_0.10"] <= hi)
    assert set(r["per_point_of_load"]) == {"long_difference", "panel"}
    for d in r["per_point_of_load"].values():
        caps = {"uncapped", "capped_at_25_points", "capped_at_50_points"}
        assert caps <= set(d)
        assert d["uncapped"]["range_half_width_mean"] < d["capped_at_50_points"]["range_half_width_mean"] < d["capped_at_25_points"]["range_half_width_mean"]
        # the cap is there because a few hosts carry the uncapped number
        assert d["capped_at_25_points"]["share_of_load_share_variation_from_the_three_largest_hosts"] < d["uncapped"]["share_of_load_share_variation_from_the_three_largest_hosts"]
    if "added_after_the_first_run" in r:          # the comparison of the two bootstraps was run once, on the D-39 run, and is not repeated
        assert "not in the standard" in r["added_after_the_first_run"]["full_bootstrap_against_the_shortcut"]["why"]

