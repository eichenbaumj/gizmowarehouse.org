"""The general fit and the full wild cluster bootstrap, against regressions done the long way. Synthetic data only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import estimator as es  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.electricity import market_region as mr  # noqa: E402

KEY = ps.KEY


def unbalanced(seed=0, units=36, years=10, clusters=6):
    """Units over years, with a cell-by-year effect that a third of the units move between, and a second grouping."""
    rng = np.random.default_rng(seed)
    u = np.repeat(np.arange(units), years)
    t = np.tile(np.arange(years), units)
    home = np.arange(units) % 3
    cell = home[u].copy()
    movers = np.arange(units) % 3 == 0
    cell[(movers[u]) & (t >= 4)] = (home[u][(movers[u]) & (t >= 4)] + 1) % 3      # a third change cell in year 4
    other = (np.arange(units) % 2)[u] * years + t
    cl = (np.arange(units) % clusters)[u]
    X = np.column_stack([rng.normal(size=len(u)) + 0.3 * (u % 5), rng.normal(size=len(u)), (u < 8) * (t >= 6) * 1.0])
    y = X @ np.array([0.5, -0.2, 0.1]) + rng.normal(size=units)[u] + rng.normal(size=(3, years))[cell, t] + 0.3 * rng.normal(size=len(u))
    return y, X, [u, cell * years + t, other], cl


def dummies(groups):
    cols = []
    for g in groups:
        codes = np.unique(g, return_inverse=True)[1]
        cols.append(np.eye(codes.max() + 1)[codes])
    return np.column_stack(cols)


def long_way(y, X, groups, cl):
    """Least squares with every fixed effect as a dummy column; cluster-robust variance from the same fit."""
    D = dummies(groups)
    Z = np.column_stack([X, D])
    coef = np.linalg.lstsq(Z, y, rcond=None)[0]
    u = y - Z @ coef
    Xt = X - D @ np.linalg.lstsq(D, X, rcond=None)[0]
    A = np.linalg.inv(Xt.T @ Xt)
    codes = np.unique(cl, return_inverse=True)[1]
    G, (N, K) = codes.max() + 1, X.shape
    S = np.stack([Xt[codes == g].T @ u[codes == g] for g in range(G)])
    V = (G / (G - 1)) * ((N - 1) / (N - K)) * A @ (S.T @ S) @ A
    return coef[:K], u, V, Z @ coef


def test_fixed_effects_are_removed_exactly_whatever_the_pattern_of_cells():
    y, X, groups, _ = unbalanced()
    D = dummies(groups)
    by_projection = es.Projection(groups)(np.column_stack([y, X]))
    by_dummies = np.column_stack([y, X]) - D @ np.linalg.lstsq(D, np.column_stack([y, X]), rcond=None)[0]
    assert by_projection == pytest.approx(by_dummies, abs=1e-8)


def test_the_fit_matches_least_squares_with_dummies():
    y, X, groups, cl = unbalanced(seed=3)
    b, _, V, _ = long_way(y, X, groups, cl)
    fit = es.Fit(y, X, groups, cl)
    assert fit.coef() == pytest.approx(b, abs=1e-8)
    assert fit.vcov() == pytest.approx(V, rel=1e-6)


def test_each_bootstrap_replication_matches_refitting_everything():
    """A replication flips each cluster's residuals, rebuilds the outcome and refits, fixed effects included."""
    y, X, groups, cl = unbalanced(seed=5)
    b, u, _, fitted = long_way(y, X, groups, cl)
    fit = es.Fit(y, X, groups, cl)
    combo, pre = np.array([0.0, 0.5, 0.5]), [0, 1]
    codes = np.unique(cl, return_inverse=True)[1]
    rng = np.random.default_rng(9)
    v = es.rademacher(rng, 12, fit.G)
    got = fit.bootstrap(v, combo, pre)
    for i in range(len(v)):
        b_star, _, V_star, _ = long_way(fitted + v[i][codes] * u, X, groups, cl)
        d = b_star - b
        assert got["t"][i] == pytest.approx(float(combo @ d) / np.sqrt(combo @ V_star @ combo), rel=1e-6)
        assert got["wald"][i] == pytest.approx(float(d[pre] @ np.linalg.solve(V_star[np.ix_(pre, pre)], d[pre])), rel=1e-6)


def test_a_planted_path_needs_no_refit():
    y, X, groups, cl = unbalanced(seed=7)
    path = (groups[0] < 8) * (np.tile(np.arange(10), 36) >= 3) * 1.0          # starts three years before the regressor says
    fit = es.Fit(y, X, groups, cl, path)
    for tau in (0.0, 0.03, 0.2):
        b, _, V, _ = long_way(y + tau * path, X, groups, cl)
        assert fit.coef(0, tau) == pytest.approx(b, abs=1e-8)
        assert fit.vcov(0, tau) == pytest.approx(V, rel=1e-6)
    v = es.rademacher(np.random.default_rng(1), 199, fit.G)
    with_path = fit.summary(v, np.array([0, 0, 1.0]), None, 0, 0.2)
    refit = es.Fit(y + 0.2 * path, X, groups, cl).summary(v, np.array([0, 0, 1.0]))
    assert (with_path["est"], with_path["lo"], with_path["hi"]) == pytest.approx((refit["est"], refit["lo"], refit["hi"]), rel=1e-6)


def test_the_bootstrap_p_value_for_the_early_years_is_the_share_of_replications_at_least_as_large():
    y, X, groups, cl = unbalanced(seed=11)
    fit = es.Fit(y, X, groups, cl)
    v = es.rademacher(np.random.default_rng(2), 499, fit.G)
    s = fit.summary(v, np.array([1.0, 0, 0]), [1, 2])
    wald = fit.bootstrap(v, np.array([1.0, 0, 0]), [1, 2])["wald"]
    assert s["pre_p_bootstrap"] == pytest.approx(float(np.mean(wald >= s["pre_wald"])))
    assert 0.0 <= s["pre_p_bootstrap"] <= 1.0


# ---- the simulation's pieces ---------------------------------------------------------------------

REGIONS = (("PJM", ["OH", "PA", "VA"]), ("MISO", ["IN", "MI", "WI"]))
FUEL = {"OH": 0, "PA": 1, "VA": 2, "IN": 0, "MI": 1, "WI": 2}
# Made-up 2008-2010 gas shares: the gas-share control is the default from step D (D-59 item 7), so a draw needs them.
GAS = {"OH": 0.05, "PA": 0.20, "VA": 0.35, "IN": 0.10, "MI": 0.25, "WI": 0.40}


def synthetic(n_per_region=24, noise=0.02, seed=1, movers=4, move_year=2011):
    """Two regions; `movers` utilities in each MISO state group change to PJM in `move_year`.

    Prices follow the region a utility is in that year, so a fit that kept a mover in one region's
    year effects would be wrong and a fit that reads the region year by year is exact.
    """
    rng = np.random.default_rng(seed)
    years = list(range(2001, 2026))
    shock = {r: rng.normal(0, 0.05, len(years)).cumsum() for r, _ in REGIONS}
    price, quant, reg, uid = [], [], [], 0
    for region, states in REGIONS:
        for i in range(n_per_region):
            uid += 1
            st = states[i % 3]
            level = rng.normal(2.4, 0.2)
            moves = region == "MISO" and i < movers
            for t, year in enumerate(years):
                r = "PJM" if moves and year >= move_year else region
                price.append((uid, st, year, level + shock[r][t] + rng.normal(0, noise)))
                quant.append((uid, st, year, "cooperative" if i % 2 else "investor_owned", 5_000 * (1 + i)))
                reg.append((uid, st, year, r))
    p = pd.DataFrame(price, columns=KEY + ["year", "log_price"])
    q = pd.DataFrame(quant, columns=KEY + ["year", "ownership", "res_customers"])
    regions = pd.DataFrame(reg, columns=KEY + ["year", "region"])
    dd = pd.DataFrame([(st, y, 5.0 + 0.1 * rng.normal(), 1.0 + 0.1 * rng.normal()) for st in FUEL for y in years],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    return p, q, regions, dd


def windows_for(p, q, regions, dd, cohorts):
    units = q[KEY].drop_duplicates()
    unit_code = {k: i for i, k in enumerate(map(tuple, units.values))}
    state_code = {s: i for i, s in enumerate(sorted(units.state.unique()))}
    return ps.build_windows(cohorts, p, q, regions, FUEL, dd, unit_code, state_code), len(unit_code)


def hosts():
    return pd.DataFrame([
        dict(cohort=2012, region="PJM", ownership="investor_owned", log_size=np.log(40_000), state="OH", key=(901, "OH")),
        dict(cohort=2012, region="MISO", ownership="cooperative", log_size=np.log(20_000), state="IN", key=(902, "IN")),
        dict(cohort=2014, region="MISO", ownership="investor_owned", log_size=np.log(60_000), state="MI", key=(903, "MI")),
        dict(cohort=2016, region="PJM", ownership="cooperative", log_size=np.log(90_000), state="PA", key=(904, "PA")),
    ])


@pytest.mark.parametrize("form", ["none", "nearest_in_size"])
def test_a_utility_that_changes_region_takes_each_regions_year_effects_in_turn(form):
    """With no noise the estimate is exactly zero, which it would not be if movers kept one region's year effects."""
    p, q, regions, dd = synthetic(noise=0.0)
    windows, n = windows_for(p, q, regions, dd, [2012, 2014, 2016])
    assert any((w.region_t.min(1) != w.region_t.max(1)).any() for w in windows.values())
    rng = np.random.default_rng(4)
    picks, _ = ps.pick_stand_ins(hosts(), windows, n, rng)
    blocks, lost = ps.build_blocks(windows, picks, form, n)
    out = ps.one_draw(windows, blocks, {}, rng, boot=99, gas=GAS)
    assert lost == 0
    assert out["exact"][0]["est"] == pytest.approx(0.0, abs=1e-9)
    assert out["exact"][0]["max_abs_early"] == pytest.approx(0.0, abs=1e-9)
    for i, pct in enumerate(ps.TAUS_PCT):
        assert out["exact"][i]["est"] == pytest.approx(np.log1p(pct / 100), abs=1e-9)        # a planted effect comes back whole


def test_the_window_reads_the_region_of_the_reference_year_for_matching():
    p, q, regions, dd = synthetic()
    windows, _ = windows_for(p, q, regions, dd, [2012, 2018])
    w = windows[2012]                              # reference year 2009, before the 2011 move
    mover = [i for i, k in enumerate(w.keys) if k[0] == 25][0]      # the first MISO utility moves
    assert w.region[mover] == "MISO" and len(set(w.region_t[mover])) == 2
    w = windows[2018]                              # window 2012 to 2021, wholly after it
    mover = [i for i, k in enumerate(w.keys) if k[0] == 25][0]
    assert w.region[mover] == "PJM" and len(set(w.region_t[mover])) == 1


def test_a_misdated_effect_is_seen_only_as_far_as_the_arithmetic_says():
    """No noise, so each case has an exact answer. The reference year is three before the recorded date."""
    p, q, regions, dd = synthetic(noise=0.0)
    windows, n = windows_for(p, q, regions, dd, [2012, 2014, 2016])
    rng = np.random.default_rng(6)
    picks, _ = ps.pick_stand_ins(hosts(), windows, n, rng)
    blocks, _ = ps.build_blocks(windows, picks, "nearest_in_size", n)
    five, t5 = ps.TAUS_PCT.index(5), np.log1p(0.05)
    seen = lambda shift: ps.one_draw(windows, blocks, {(g, int(j)): shift for g, j, _ in picks}, rng, boot=99, gas=GAS)  # noqa: E731
    # began two years early: the reference year is still clean, so the whole effect is seen (the anticipation window's job)
    assert seen(-2)["misdated"][five]["est"] == pytest.approx(t5, abs=1e-9)
    # began four years early: two thirds of it is already in the reference year
    assert seen(-4)["misdated"][five]["est"] == pytest.approx(t5 / 3, abs=1e-9)
    # began two years late: event years 2 and 3 catch a third and two thirds
    assert seen(2)["misdated"][five]["est"] == pytest.approx(t5 / 2, abs=1e-9)
    # began before the window opens, or never: nothing is seen
    assert seen(-12)["misdated"][five]["est"] == pytest.approx(0.0, abs=1e-9)
    assert seen(60)["misdated"][five]["est"] == pytest.approx(0.0, abs=1e-9)
    # an early start shows up in the early years, which is what the flat-before test looks at
    assert seen(-5)["misdated"][five]["max_abs_early"] > 0.01
    assert seen(-2)["exact"][five]["est"] == pytest.approx(t5, abs=1e-9)        # the exact-date reading is untouched


def test_planted_path_follows_the_true_start():
    tt = np.arange(ps.T)
    assert ps.planted_path(tt, 0.0) == pytest.approx(ps.RAMP)
    assert ps.planted_path(tt, -2.0)[ps.PRE - 2:ps.PRE + 1] == pytest.approx([1 / 3, 2 / 3, 1.0])
    assert ps.planted_path(tt, 60.0).sum() == 0.0


def test_the_closed_form_and_the_general_fit_agree_where_nothing_moves():
    """Same blocks, no controls, one region per utility: the estimate and its standard error are the same number."""
    p, q, regions, dd = synthetic(noise=0.03, movers=0, seed=8)
    windows, n = windows_for(p, q, regions, dd, [2012, 2014, 2016])
    rng = np.random.default_rng(2)
    picks, _ = ps.pick_stand_ins(hosts(), windows, n, rng)
    blocks, _ = ps.build_blocks(windows, picks, "none", n)
    old = ps.estimate(windows, blocks, (0.0,), rng, boot=50)[0]
    a = ps.assemble(windows, blocks, controls=False)
    fit = es.Fit(a["y"], a["X"], a["groups"], a["cluster"])
    assert float(ps.W_HEAD @ fit.coef()) == pytest.approx(old["est"], abs=1e-10)
    assert float(np.sqrt(ps.W_HEAD @ fit.vcov() @ ps.W_HEAD)) == pytest.approx(old["se"], rel=1e-8)


def test_the_early_years_test_fails_a_flat_history_about_one_time_in_ten():
    """Fresh synthetic prices each time, so the draws are independent. Six clusters, so the band is wide."""
    rng = np.random.default_rng(13)
    fails, covered = [], []
    for seed in range(160):
        p, q, regions, dd = synthetic(n_per_region=18, noise=0.03, seed=500 + seed, movers=2)
        windows, n = windows_for(p, q, regions, dd, [2012, 2014, 2016])
        picks, _ = ps.pick_stand_ins(hosts(), windows, n, rng)
        blocks, _ = ps.build_blocks(windows, picks, "nearest_in_size", n)
        z = ps.one_draw(windows, blocks, {}, rng, boot=199, gas=GAS)["exact"][0]
        fails.append(z["pre_p_bootstrap"] < 0.10)
        covered.append(z["lo"] <= 0 <= z["hi"])
    assert 0.03 <= np.mean(fails) <= 0.20
    assert 0.80 <= np.mean(covered) <= 0.99


def test_detectable_reads_the_grid():
    assert ps.detectable([0.05, 0.4, 0.9, 1.0], taus=(0, 1, 2, 3)) == pytest.approx(1.8)
    assert ps.detectable([0.05, 0.1, 0.2], taus=(0, 1, 2)) is None
    assert ps.detectable([0.9, 1.0], taus=(0, 1)) == 0.0


# ---- market region year by year --------------------------------------------------------------------

def moves_table(rows):
    base = {"source_url": "https://example.org/release", "source_quote": "joined on", "confidence": "high", "checked_on": "2026-11-12"}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_first_year_in_the_new_region_follows_from_the_date(tmp_path):
    ok = moves_table([{"move_id": "a", "from_region": "MISO", "to_region": "PJM", "effective_date": "2011-06-01", "first_year_in_new_region": "2011"},
                      {"move_id": "b", "from_region": "X", "to_region": "SPP", "effective_date": "2015-10-01", "first_year_in_new_region": "2016"}])
    ok.to_csv(tmp_path / "m.csv", index=False)
    assert len(mr.load_moves(tmp_path / "m.csv")) == 2
    bad = ok.assign(first_year_in_new_region=["2011", "2015"])
    bad.to_csv(tmp_path / "bad.csv", index=False)
    with pytest.raises(ValueError):
        mr.load_moves(tmp_path / "bad.csv")
    ok.assign(source_quote=["", "x"]).to_csv(tmp_path / "unsourced.csv", index=False)
    with pytest.raises(ValueError):
        mr.load_moves(tmp_path / "unsourced.csv")


def test_regions_by_year_follow_the_dated_moves_and_the_reported_codes():
    rows = []
    for year in range(2005, 2019):
        code = lambda c: c if year >= 2013 else "UNK"  # noqa: E731
        rows += [(1, "KY", year, code("LGEE"), "investor_owned"),        # left MISO in 2006
                 (2, "NE", year, code("NPPD" if year == 2013 else "SWPP"), "public"),   # joined SPP in April 2009
                 (3, "SD", year, code("WAUE" if year < 2016 else "SWPP"), "cooperative"),   # joined SPP in October 2015
                 (4, "AR", year, code("MISO"), "investor_owned"),         # joined MISO on 19 December 2013
                 (5, "OH", year, code("PJM"), "public"),                  # in a zone that left MISO in 2012
                 (6, "OH", year, code("PJM"), "investor_owned"),          # never moved
                 (7, "TX", year, code("SPS" if year == 2013 else "ERCO"), "investor_owned"),  # a move EIA itself shows
                 (8, "OH", year, "UNK", "public"),                        # never reports a code
                 (9, "OH", year, code("PJM"), "cooperative")]             # a second Ohio utility that never moved
    q = pd.DataFrame(rows, columns=KEY + ["year", "balancing_authority", "ownership"])
    zones = pd.DataFrame([(5, "OH", "DEOK", "public")], columns=KEY + ["zone", "ownership"])
    r = mr.by_unit_year(q, years=range(2005, 2019), zones=zones).set_index(KEY + ["year"]).region
    at = lambda u, st, y: r[(u, st, y)]  # noqa: E731
    assert (at(1, "KY", 2006), at(1, "KY", 2007), at(1, "KY", 2015)) == ("MISO", "Southeast", "Southeast")
    assert (at(2, "NE", 2008), at(2, "NE", 2009)) == (mr.UPPER_MIDWEST, "SPP")
    assert (at(3, "SD", 2014), at(3, "SD", 2015), at(3, "SD", 2016)) == (mr.UPPER_MIDWEST, mr.UPPER_MIDWEST, "SPP")
    assert (at(4, "AR", 2012), at(4, "AR", 2013), at(4, "AR", 2014)) == ("Southeast", "Southeast", "MISO")
    assert (at(5, "OH", 2011), at(5, "OH", 2012)) == ("MISO", "PJM")
    assert {at(6, "OH", y) for y in range(2005, 2019)} == {"PJM"}
    assert (at(7, "TX", 2012), at(7, "TX", 2013), at(7, "TX", 2014)) == ("SPP", "SPP", "ERCOT")
    assert {at(8, "OH", y) for y in range(2005, 2019)} == {"PJM"}         # its state's most common region each year
    m = mr.movers(mr.by_unit_year(q, years=range(2005, 2019), zones=zones))
    assert set(m.utility_id_eia) == {1, 2, 3, 4, 5, 7}


def test_the_committed_moves_table_is_sourced_and_dated():
    m = mr.load_moves()
    assert {"atsi", "deok", "miso_south", "nebraska", "ugp", "lgee", "ekpc", "big_rivers"} <= set(m.move_id)
    assert m.source_url.str.startswith("http").all() and (m.checked_on == "2026-11-12").all()


# ---- date errors -------------------------------------------------------------------------------------

def test_a_utilitys_date_error_follows_its_permit_dated_sites():
    from pipeline.analysis import misdating as md
    years = np.arange(2001, 2026)
    sites = pd.DataFrame({"mw_full": [30.0], "energized_year": [2015.0], "size": ["20_to_50"]})
    base, theta = 1000.0, 0.02                       # the threshold is 20 GWh a year, 2.28 MW on average
    other = np.zeros(len(years))
    rng = np.random.default_rng(0)
    exact = md.crossing_errors(2015, other, sites, base, theta, {"20_to_50": np.array([0.0])}, years, rng, draws=5)
    assert (exact == 0).all()
    late = md.crossing_errors(2015, other, sites, base, theta, {"20_to_50": np.array([5.0])}, years, rng, draws=5)
    assert (late == -5).all()                        # the permit dated the site five years late: it really crossed in 2010
    none = md.crossing_errors(2015, other, sites.iloc[:0], base, theta, {}, years, rng, draws=5)
    assert (none == 0).all()                         # no permit-dated site, no error
    already = md.crossing_errors(2015, np.full(len(years), 5.0), sites, base, theta, {"20_to_50": np.array([-3.0])}, years, rng, draws=3)
    assert (already == 2001 - 2015).all()            # other sites alone were over the threshold from the first panel year
    small = pd.DataFrame({"mw_full": [1.0], "energized_year": [2015.0], "size": ["under_20"]})
    never = md.crossing_errors(2015, other, small, base, theta, {"under_20": np.array([0.0])}, years, rng, draws=3)
    assert (never >= md.NEVER - 30).all()            # too small to reach the threshold at all


def test_a_fit_whose_regressors_are_not_identified_raises_and_returns_nothing():
    # D-59, item 7: an explicit failure, never coefficients from an unstable inverse.
    y, X, groups, cl = unbalanced()
    es.Fit(y, X, groups, cl)                                             # the full-rank case still fits
    absorbed = np.column_stack([X, (groups[0] % 4 == 0) * 1.0])          # constant within unit: the unit effects remove it
    with pytest.raises(es.RankDeficient, match="not identified"):
        es.Fit(y, absorbed, groups, cl)
    twice = np.column_stack([X, X[:, 0] * 2.0])                          # a column that repeats another
    with pytest.raises(es.RankDeficient):
        es.Fit(y, twice, groups, cl)
    only = ((groups[0] % 3 == 0) * 1.0)[:, None]                         # every regressor absorbed
    with pytest.raises(es.RankDeficient, match="absorb every regressor"):
        es.Fit(y, only, groups, cl)
    assert es.check_rank(es.Projection(groups)(X), X)["ratio"] > es.RANK_TOLERANCE
