"""Step E's three candidates against slow, independent calculations (docs/gate1/step-e-rules-2026-11-18.md). Invented data only.

A: estimator.Fit.summary unchanged, coverage as the range containing the true value.
B: the vectorized null-imposed bootstrap equals refitting every replication by dense least squares with every fixed effect
   as a dummy (to 1e-10), with the same draws at every hypothesized value; the three end states; the cap is "search
   incomplete", not a failure; coverage from the one test at the true value.
C: CR2, Satterthwaite and AHT against the long way (dense H_X, every fixed effect a dummy), on a design whose fixed effects
   are not nested in the clusters; CR2's unbiasedness under the working model (Theorem 1). R and clubSandwich are not on
   this machine (checked 2026-11-18), so there is no clubSandwich comparison.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import estimator as es  # noqa: E402

PRE = [0, 1, 2]
COMBO = np.array([0.0, 0.0, 0.0, 0.5, 0.5])


def invented(seed=0, units=30, years=8, clusters=6, effect_sd=1.0):
    """Units over years; utility effects nested in clusters; a cell-by-year effect a third of the units move between and a
    second grouping, both crossing clusters (as the region-by-year effects and gas-share controls cross states)."""
    rng = np.random.default_rng(seed)
    u = np.repeat(np.arange(units), years)
    t = np.tile(np.arange(years), units)
    home = np.arange(units) % 3
    cell = home[u].copy()
    movers = np.arange(units) % 3 == 0
    cell[movers[u] & (t >= 4)] = (home[u][movers[u] & (t >= 4)] + 1) % 3
    other = (np.arange(units) % 2)[u] * years + t
    cl = (np.arange(units) % clusters)[u]
    treated = (u % 4 == 0)
    X = np.column_stack([treated * (t == 1), treated * (t == 2), treated * (t == 3), treated * (t == 6), treated * (t == 7)]).astype(float)
    X = np.column_stack([X, rng.normal(size=len(u)) + 0.2 * (u % 5)])                # a control, like the degree days
    combo = np.r_[COMBO, 0.0]
    y = rng.normal(size=units)[u] * effect_sd + rng.normal(size=(3, years))[cell, t] + 0.3 * rng.normal(size=len(u)) \
        + 0.4 * rng.normal(size=clusters)[cl]
    ramp = treated * np.clip((t - 4 + 1) / 3, 0, 1)
    return y, X, [u, cell * years + t, other], cl, combo, ramp


def problem(seed=0, **kw):
    y, X, groups, cl, combo, ramp = invented(seed, **kw)
    return y, cd.Problem(X, groups, cl, ramp=ramp, combo=combo, pre=PRE)


def dummies(groups):
    cols = []
    for g in groups:
        codes = np.unique(g, return_inverse=True)[1]
        cols.append(np.eye(codes.max() + 1)[codes])
    return np.column_stack(cols)


def null_basis(R):
    """Columns spanning {b : R b = 0}."""
    _, s, vt = np.linalg.svd(np.atleast_2d(R))
    return vt[(s > 1e-12).sum():].T


# ---- the slow way: dense least squares with dummies, one replication at a time ------------------------------------

def cr1(X, D, e, codes):
    Xt = X - D @ np.linalg.lstsq(D, X, rcond=None)[0]
    Ainv = np.linalg.inv(Xt.T @ Xt)
    G, (N, K) = codes.max() + 1, X.shape
    S = np.stack([Xt[codes == g].T @ e[codes == g] for g in range(G)])
    return (G / (G - 1)) * ((N - 1) / (N - K)) * Ainv @ (S.T @ S) @ Ainv


def restricted(y, X, D, R, r):
    """Least squares of y on X and the dummies subject to R b = r, by reparametrising b = b0 + N z (no shared identity)."""
    R = np.atleast_2d(R)
    b0 = np.linalg.lstsq(R, np.atleast_1d(r), rcond=None)[0]
    N = null_basis(R)
    Z = np.column_stack([X @ N, D])
    coef = np.linalg.lstsq(Z, y - X @ b0, rcond=None)[0]
    resid = y - X @ b0 - Z @ coef
    return y - resid, resid


def slow_tstar(y, X, groups, cl, combo, theta, v):
    D = dummies(groups)
    codes = np.unique(cl, return_inverse=True)[1]
    fitted, resid = restricted(y, X, D, combo, theta)
    Z = np.column_stack([X, D])
    out = []
    for vb in v:
        ys = fitted + vb[codes] * resid
        coef = np.linalg.lstsq(Z, ys, rcond=None)[0]
        b, e = coef[:X.shape[1]], ys - Z @ coef
        V = cr1(X, D, e, codes)
        out.append((combo @ b - theta) / np.sqrt(combo @ V @ combo))
    return np.array(out)


def slow_wald(y, X, groups, cl, pre, v):
    D = dummies(groups)
    codes = np.unique(cl, return_inverse=True)[1]
    R = np.eye(X.shape[1])[pre]
    fitted, resid = restricted(y, X, D, R, np.zeros(len(pre)))
    Z = np.column_stack([X, D])
    out = []
    for vb in v:
        ys = fitted + vb[codes] * resid
        coef = np.linalg.lstsq(Z, ys, rcond=None)[0]
        b, e = coef[:X.shape[1]], ys - Z @ coef
        V = cr1(X, D, e, codes)
        out.append(b[pre] @ np.linalg.solve(V[np.ix_(pre, pre)], b[pre]))
    return np.array(out)


def data_stats(y, X, groups, cl, combo, pre):
    D = dummies(groups)
    codes = np.unique(cl, return_inverse=True)[1]
    Z = np.column_stack([X, D])
    coef = np.linalg.lstsq(Z, y, rcond=None)[0]
    b, e = coef[:X.shape[1]], y - Z @ coef
    V = cr1(X, D, e, codes)
    return float(combo @ b), float(np.sqrt(combo @ V @ combo)), float(b[pre] @ np.linalg.solve(V[np.ix_(pre, pre)], b[pre]))


# ================================================================================================================
# B
# ================================================================================================================

@pytest.mark.parametrize("seed", [1, 4])
def test_b_vectorized_bootstrap_equals_refitting_every_replication_with_the_same_draws_at_every_value(seed):
    y, p = problem(seed)
    v = es.rademacher(np.random.default_rng(seed), 25, p.G)
    s = cd.CandidateB(p).session(y, v)
    est, se, _ = data_stats(y, p.X, p.groups, p.cluster, p.combo, PRE)
    assert s.est == pytest.approx(est, abs=1e-10) and s.se == pytest.approx(se, rel=1e-10)
    for theta in (est, est - 0.7 * se, est + 3.1 * se, 0.0, est + 40 * se):     # one v for all of them
        slow = slow_tstar(y, p.X, p.groups, p.cluster, p.combo, theta, v)
        assert s.tstar(theta) == pytest.approx(slow, rel=1e-10, abs=1e-10)
        p_slow = float(np.mean(np.abs(slow) >= abs((est - theta) / se) - 1e-9 * max(1, abs((est - theta) / se))))
        assert s.p_value(theta, "range") == p_slow


def test_b_early_years_bootstrap_equals_refitting_every_replication():
    y, p = problem(2)
    v = es.rademacher(np.random.default_rng(9), 25, p.G)
    s = cd.CandidateB(p).session(y, v)
    _, _, wald = data_stats(y, p.X, p.groups, p.cluster, p.combo, PRE)
    slow = slow_wald(y, p.X, p.groups, p.cluster, PRE, v)
    assert s.early_years_p() == float(np.mean(slow >= wald - 1e-9 * max(1, wald)))
    # and the statistics themselves, through the same pieces the session uses
    c = s.c
    x = cd._Parts.combine([(1.0, s.u_parts)] + [(float(s.b[PRE][j]), c.we_parts[j]) for j in range(3)])
    shift = v @ (x.S @ c.M)
    P = np.einsum("bh,ghj->bgj", v, x.Tp) - np.einsum("bk,gkj->bgj", shift, c.AgMp)
    Vb = c.factor * np.einsum("bgi,bgj->bij", P, P)
    d = shift[:, PRE]
    fast = np.einsum("bi,bi->b", d, np.linalg.solve(Vb, d[:, :, None])[:, :, 0])
    assert fast == pytest.approx(slow, rel=1e-9, abs=1e-10)


def test_b_on_an_assembled_design_matches_the_slow_way_too():
    f = assembled_problem()
    rng = np.random.default_rng(5)
    y = rng.normal(size=f.N) + 0.1 * rng.normal(size=f.G)[f.codes]
    v = es.rademacher(rng, 15, f.G)
    s = cd.CandidateB(f).session(y, v)
    for theta in (0.0, s.est + 2 * s.se):
        assert s.tstar(theta) == pytest.approx(slow_tstar(y, f.X, f.groups, f.cluster, f.combo, theta, v), rel=1e-9, abs=1e-9)


def test_b_uses_one_draw_matrix_for_the_whole_dataset():
    y, p = problem(3)
    v = es.rademacher(np.random.default_rng(1), 49, p.G)
    b = cd.CandidateB(p)
    r = b.run(y, 0.0, v)
    s = b.session(y, v)                                                   # an independent session with the same v
    assert r["covered"] == (s.p_value(0.0, "x") >= 0.10)
    lo, lo_state = s.endpoint(-1)
    hi, hi_state = s.endpoint(+1)
    assert (lo_state, hi_state) == (r["lo_state"], r["hi_state"]) == (cd.BOUNDED, cd.BOUNDED)
    assert (lo, hi) == (r["lo"], r["hi"])
    assert s.p_value(lo + 0.001, "x") >= 0.10 and s.p_value(lo - 0.001, "x") < 0.10      # the crossing, to the tolerance
    assert s.p_value(hi - 0.001, "x") >= 0.10 and s.p_value(hi + 0.001, "x") < 0.10


def test_b_coverage_is_the_one_test_at_the_true_value_and_not_the_endpoints(monkeypatch):
    y, p = problem(6)
    v = es.rademacher(np.random.default_rng(2), 49, p.G)
    b = cd.CandidateB(p)
    honest = b.run(y, 0.0, v)
    # endpoints that would say the opposite: coverage must not move
    if honest["covered"]:                                                 # a range wholly above the true value
        fake = lambda self, sign: (50.0 + sign, cd.BOUNDED)  # noqa: E731
    else:                                                                 # a range around it
        fake = lambda self, sign: (100.0 * sign, cd.BOUNDED)  # noqa: E731
    monkeypatch.setattr(cd._Session, "endpoint", fake)
    twisted = b.run(y, 0.0, v)
    assert twisted["covered"] == honest["covered"]
    assert twisted["miss"] == (not honest["covered"])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_b_the_replication_that_rebuilds_the_data_counts_as_at_least_as_large(seed):
    """All +1 (or all -1) weights rebuild the data exactly: its statistic equals the data's in exact arithmetic, so the
    p-value is 1 if every replication is that one, whatever the rounding."""
    y, p = problem(seed)
    s = cd.CandidateB(p).session(y, np.vstack([np.ones((3, p.G)), -np.ones((2, p.G))]))
    for theta in (0.0, s.est + 2.5 * s.se, s.est - 7 * s.se):
        assert s.p_value(theta, "x") == 1.0
    assert s.early_years_p() == 1.0


def test_b_a_bounded_side_is_found_to_the_tolerance():
    crossing = 0.0123
    pfun = lambda theta: 0.5 if theta < crossing else 0.05                   # noqa: E731
    end, state = cd.search_side(pfun, 0.0, 0.001, +1)
    assert state == cd.BOUNDED and abs(end - crossing) <= cd.TOLERANCE / 2 + 1e-12
    end, state = cd.search_side(lambda th: 0.5 if th > -crossing else 0.05, 0.0, 0.001, -1)
    assert state == cd.BOUNDED and abs(end + crossing) <= cd.TOLERANCE / 2 + 1e-12


def test_b_the_bracket_doubles_from_ten_to_640_standard_errors():
    seen = []
    cd.search_side(lambda th: seen.append(th) or 0.5, 1.0, 0.01, +1)
    assert seen == pytest.approx([1.0 + k * 0.01 for k in (10, 20, 40, 80, 160, 320, 640)])


def test_b_the_cap_is_search_incomplete_and_not_a_failure(monkeypatch):
    end, state = cd.search_side(lambda th: 0.5, 0.0, 0.01, +1)
    assert state == cd.INCOMPLETE and np.isnan(end)
    y, p = problem(7)
    v = es.rademacher(np.random.default_rng(3), 49, p.G)
    b = cd.CandidateB(p)
    real = cd.search_side
    monkeypatch.setattr(cd, "search_side", lambda pfun, est, se, sign, **k: real(lambda th: 0.5, est, se, sign) if sign > 0 else real(pfun, est, se, sign))
    r = b.run(y, 0.0, v)
    assert r["failure"] is None and r["hi_state"] == cd.INCOMPLETE and r["width"] == float("inf")
    assert r["miss"] == (not r["covered"])                                 # the cap costs width only (E4.2)


def test_b_not_monotone_along_the_bracket_is_search_incomplete():
    ps_ = iter([0.4, 0.6, 0.05])
    end, state = cd.search_side(lambda th: next(ps_), 0.0, 0.01, +1)
    assert state == cd.INCOMPLETE and np.isnan(end)


def test_b_a_non_finite_replication_fails_the_dataset_as_a_miss_and_a_rejection(monkeypatch):
    y, p = problem(8)
    v = es.rademacher(np.random.default_rng(4), 49, p.G)
    b = cd.CandidateB(p)
    real = cd._Session.tstar

    def one_nan_far_out(self, theta):
        t = real(self, theta)
        if abs(theta - self.est) > 15 * self.se:                          # only during the endpoint search
            t = t.copy()
            t[3] = np.nan
        return t
    monkeypatch.setattr(cd._Session, "tstar", one_nan_far_out)
    r = b.run(y, 0.0, v)
    assert r["failure"]["cause"] == cd.NON_FINITE_BOOTSTRAP_T and r["failure"]["where"].startswith("endpoint")
    assert r["miss"] and r["reject"] and r["covered"] is None and r["width"] == float("inf")
    assert cd.FAILED in (r["lo_state"], r["hi_state"])


def test_b_a_non_finite_replication_at_the_true_value_fails_the_test(monkeypatch):
    y, p = problem(8)
    v = es.rademacher(np.random.default_rng(4), 49, p.G)
    monkeypatch.setattr(cd._Session, "tstar", lambda self, th: np.full(len(self.v), np.inf))
    r = cd.CandidateB(p).run(y, 0.0, v)
    assert r["failure"]["where"] == "test_at_the_true_value" and r["miss"] and r["reject"]


# ================================================================================================================
# C: the long way
# ================================================================================================================

def mp_sqrt_long(B):
    """B^{+1/2} the long way: pinv, then the symmetric square root of that."""
    Bp = np.linalg.pinv(B, rcond=1e-8, hermitian=True)
    lam, vec = np.linalg.eigh(Bp)
    return (vec * np.sqrt(np.clip(lam, 0, None))) @ vec.T


def cr2_long(y, X, groups, cl, combo, pre, absorb_all=True):
    """Dense H_X on [X, every dummy]; Eq. (4), (7), (8), (11), (12), (13) with Phi = W = I, written out loop by loop."""
    D = dummies(groups)
    Z = np.column_stack([X, D])
    H = Z @ np.linalg.pinv(Z)
    IH = np.eye(len(y)) - H
    Xdd = X - D @ np.linalg.lstsq(D, X, rcond=None)[0]
    M = np.linalg.inv(Xdd.T @ Xdd)
    if not absorb_all:                                                   # the adjustment WITHOUT the absorbed effects
        IH = np.eye(len(y)) - Xdd @ M @ Xdd.T
    e = (np.eye(len(y)) - H) @ y
    b = M @ Xdd.T @ y
    codes = np.unique(cl, return_inverse=True)[1]
    G = codes.max() + 1
    mid = np.zeros((X.shape[1], X.shape[1]))
    Cm = np.eye(X.shape[1])[pre]
    lam, vec = np.linalg.eigh(Cm @ M @ Cm.T)
    Gih = (vec / np.sqrt(lam)) @ vec.T
    p_head, p_early, Bs = [], [], []
    for i in range(G):
        idx = np.flatnonzero(codes == i)
        Bi = IH[idx, :] @ IH[idx, :].T
        Ai = mp_sqrt_long(Bi)
        Bs.append(Bi)
        mid += Xdd[idx].T @ Ai @ np.outer(e[idx], e[idx]) @ Ai @ Xdd[idx]
        p_head.append(IH[idx, :].T @ Ai @ Xdd[idx] @ M @ combo)
        p_early.append([IH[idx, :].T @ Ai @ Xdd[idx] @ M @ Cm.T @ Gih[:, s] for s in range(len(pre))])
    V = M @ mid @ M
    num = sum(p @ p for p in p_head) ** 2
    den = sum((pi @ pj) ** 2 for pi in p_head for pj in p_head)
    nu = num / den
    q = len(pre)
    tot = 0.0
    for s in range(q):
        for t in range(q):
            for i in range(G):
                for j in range(G):
                    psi, ptj, pti, psj = p_early[i][s], p_early[j][t], p_early[i][t], p_early[j][s]
                    tot += (psi @ ptj) * (pti @ psj) + (psi @ psj) * (pti @ ptj)
    eta = q * (q + 1) / tot
    Q = b[pre] @ np.linalg.solve(V[np.ix_(pre, pre)], b[pre])
    p_aht = stats.f.sf((eta - q + 1) / (eta * q) * Q, q, eta - q + 1)
    return {"V": V, "nu": nu, "eta": eta, "b": b, "p_aht": p_aht, "B": Bs, "M": M}


def test_c_matches_the_long_way_with_effects_not_nested_in_clusters():
    y, p = problem(11)
    long = cr2_long(y, p.X, p.groups, p.cluster, p.combo, PRE)
    c = cd.CandidateC(p)
    assert c.design_failure is None and c.early_failure is None
    b, u = c.fit(y)
    assert b == pytest.approx(long["b"], abs=1e-10)
    assert c.vcov(u) == pytest.approx(long["V"], rel=1e-8, abs=1e-14)
    assert c.nu == pytest.approx(long["nu"], rel=1e-8)
    assert c.eta == pytest.approx(long["eta"], rel=1e-8)
    assert c.aht(b, c.vcov(u)) == pytest.approx(long["p_aht"], rel=1e-7)
    r = c.run(y, 0.0)
    se = float(np.sqrt(p.combo @ long["V"] @ p.combo))
    crit = stats.t.ppf(0.95, long["nu"])
    assert r["lo"] == pytest.approx(r["estimate"] - crit * se, rel=1e-8) and r["hi"] == pytest.approx(r["estimate"] + crit * se, rel=1e-8)
    assert r["covered"] == (2 * stats.t.sf(abs(r["estimate"]) / se, long["nu"]) >= 0.10)


def test_c_differs_from_an_adjustment_that_leaves_out_the_absorbed_effects():
    """The rule computes the adjustment on the full model; on this design the shortcut gives another answer, so the
    long-way test above would catch it."""
    y, p = problem(11)
    full = cr2_long(y, p.X, p.groups, p.cluster, p.combo, PRE)
    short = cr2_long(y, p.X, p.groups, p.cluster, p.combo, PRE, absorb_all=False)
    assert not np.allclose(full["V"], short["V"], rtol=1e-4)


def test_c_on_an_assembled_design_with_gas_share_columns_matches_the_long_way():
    f = assembled_problem()
    rng = np.random.default_rng(12)
    y = rng.normal(size=f.N) + 0.2 * rng.normal(size=f.G)[f.codes]
    long = cr2_long(y, f.X, f.groups, f.cluster, f.combo, f.pre)
    c = cd.CandidateC(f)
    b, u = c.fit(y)
    assert c.vcov(u) == pytest.approx(long["V"], rel=1e-7, abs=1e-14)
    assert c.nu == pytest.approx(long["nu"], rel=1e-7)


def test_c_is_exactly_unbiased_under_the_working_model():
    """Theorem 1: with Phi = I, sum_i M X~_i' A_i B_i A_i X~_i M = M, i.e. E[V_CR2] = sigma^2 M."""
    y, p = problem(13, units=36, clusters=9)
    long = cr2_long(y, p.X, p.groups, p.cluster, p.combo, PRE)
    c = cd.CandidateC(p)
    tot = sum(c.F[p.codes == i].T @ long["B"][i] @ c.F[p.codes == i] for i in range(p.G))
    assert tot == pytest.approx(long["M"], rel=1e-7, abs=1e-12)


def test_c_eta_reduces_to_nu_for_one_constraint():
    rng = np.random.default_rng(0)
    P = rng.normal(size=(40, 6))
    P = P / np.sqrt(np.trace(P.T @ P))                                    # scaled as G^{-1/2} scales it (sum p_i'p_i = 1)
    assert cd.aht_degrees_of_freedom(P[:, None, :]) == pytest.approx(cd.satterthwaite(P), rel=1e-12)


def test_c_pseudo_inverse_square_root_drops_the_null_space():
    rng = np.random.default_rng(1)
    Q = np.linalg.qr(rng.normal(size=(5, 5)))[0]
    B = (Q * np.array([2.0, 0.5, 1e-17, 0.0, 3.0])) @ Q.T
    A = cd.mp_inverse_sqrt(B)
    assert A @ B @ A == pytest.approx(Q[:, [0, 1, 4]] @ Q[:, [0, 1, 4]].T, abs=1e-10)
    with pytest.raises(cd.Failed):
        cd.mp_inverse_sqrt(np.full((2, 2), np.nan))


# ================================================================================================================
# A, and failures common to all three
# ================================================================================================================

def test_a_is_fit_summary_as_built_and_covers_when_the_range_holds_the_true_value():
    y, p = problem(14)
    v = es.rademacher(np.random.default_rng(5), 99, p.G)
    r = cd.CandidateA(p).run(y, 0.0, v)
    fit = es.Fit(y, p.X, p.groups, p.cluster, p.ramp[:, None], projection=p.projection)
    z = fit.summary(v, p.combo, PRE)
    assert (r["lo"], r["hi"], r["estimate"]) == (z["lo"], z["hi"], z["est"])
    assert r["covered"] == (z["lo"] <= 0.0 <= z["hi"]) and r["early_rejected"] == (z["pre_p_bootstrap"] < 0.10)
    assert r["lo_state"] == r["hi_state"] == cd.BOUNDED and r["width"] == z["hi"] - z["lo"]


def test_a_non_finite_replication_fails_a_as_a_miss_and_a_rejection(monkeypatch):
    y, p = problem(14)
    v = es.rademacher(np.random.default_rng(5), 99, p.G)
    real = es.Fit.bootstrap

    def poisoned(self, *a, **k):
        out = real(self, *a, **k)
        out["t"] = out["t"].copy()
        out["t"][0] = np.inf
        return out
    monkeypatch.setattr(es.Fit, "bootstrap", poisoned)
    r = cd.CandidateA(p).run(y, 0.0, v)
    assert r["failure"]["cause"] == es.NON_FINITE_BOOTSTRAP_T and r["miss"] and r["reject"] and r["width"] == float("inf")


@pytest.mark.parametrize("name", ["A", "B", "C"])
def test_a_rank_deficient_design_fails_every_candidate_in_words(name):
    y, X, groups, cl, combo, ramp = invented(15)
    X = np.column_stack([X, X[:, 0] + X[:, 1]])                          # one column the sum of two others
    p = cd.Problem(X, groups, cl, ramp=ramp, combo=np.r_[combo, 0.0], pre=PRE)
    cand = cd.prepare(p, [name], boot=19)[name]
    r = cand.run(y, 0.0, es.rademacher(np.random.default_rng(0), 19, p.G))
    assert r["failure"]["cause"] == cd.RANK_DEFICIENT and r["miss"] and r["reject"] and r["covered"] is None
    assert r["width"] == float("inf")


@pytest.mark.parametrize("name", ["A", "B", "C"])
def test_a_non_finite_outcome_is_a_failure_not_a_drop(name):
    y, p = problem(16)
    y = y.copy()
    y[5] = np.nan
    r = cd.prepare(p, [name], boot=19)[name].run(y, 0.0, es.rademacher(np.random.default_rng(0), 19, p.G))
    assert r["failure"] is not None and r["miss"] and r["reject"]


def test_c_undefined_degrees_of_freedom_fail_every_dataset(monkeypatch):
    y, p = problem(17)
    monkeypatch.setattr(cd, "satterthwaite", lambda P: float("nan"))
    r = cd.CandidateC(p).run(y, 0.0)
    assert r["failure"]["cause"] == cd.UNDEFINED_DEGREES_OF_FREEDOM and r["miss"] and r["reject"]


def test_power_reads_the_planted_ramp_on_the_same_dataset():
    y, p = problem(18)
    v = es.rademacher(np.random.default_rng(6), 99, p.G)
    big = 5.0                                                              # a planted effect no procedure can miss
    for name, cand in cd.prepare(p, boot=99).items():
        assert cand.run(y, 0.0, v, planted=big)["power_detects"], name
        assert not cand.run(y, 0.0, v, planted=None)["power_detects"], name


# ---- an assembled design: the real code path (design.build_with_rules, inference_check.fixed_parts) ---------------

def assembled_problem():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_inference_comparison import invented_design  # noqa: E402
    from pipeline.analysis import inference_check as ic
    d, *_ = invented_design(hosts=2, comps=14)
    return cd.Problem.from_fixed_parts(ic.fixed_parts(d))


# ---- public methods on a design that failed when the candidate was built ------------------------------------------

def failed_problem():
    y, X, groups, cl, combo, ramp = invented(15)
    X = np.column_stack([X, X[:, 0] + X[:, 1]])                          # one column the sum of two others
    return y, cd.Problem(X, groups, cl, ramp=ramp, combo=np.r_[combo, 0.0], pre=PRE)


def test_every_public_method_of_a_failed_design_fails_in_words():
    y, p = failed_problem()
    v = es.rademacher(np.random.default_rng(0), 19, p.G)
    b, c = cd.CandidateB(p, boot=19), cd.CandidateC(p)
    assert b.design_failure is not None and c.design_failure is not None
    calls = [lambda: b.session(y, v), lambda: b.parts(y), lambda: b.unrestricted(y),
             lambda: c.fit(y), lambda: c.vcov(y), lambda: c.t_test(0.1, 0.1, 0.0), lambda: c.aht(np.zeros(p.K), np.eye(p.K))]
    for call in calls:
        with pytest.raises(cd.Failed) as e:
            call()
        assert e.value.cause == cd.RANK_DEFICIENT


def test_c_records_the_power_failure_when_the_aht_degrees_of_freedom_are_undefined(monkeypatch):
    """eta <= q - 1 is a design-level failure of C: every dataset fails, the planted one too, as A and B record a
    design-level failure in power_failure (failed_result)."""
    y, p = problem(19)
    monkeypatch.setattr(cd, "aht_degrees_of_freedom", lambda P: 1.5)          # q = 3: eta - q + 1 = -0.5
    r = cd.CandidateC(p).run(y, 0.0, planted=5.0)
    assert r["failure"]["cause"] == cd.UNDEFINED_DEGREES_OF_FREEDOM and r["miss"] and r["reject"]
    assert r["power_failure"] is not None and r["power_failure"]["cause"] == cd.UNDEFINED_DEGREES_OF_FREEDOM
    assert r["power_detects"] is False
    # and A and B on a design-level failure record it the same way
    yf, pf = failed_problem()
    for name, cand in cd.prepare(pf, boot=19).items():
        rr = cand.run(yf, 0.0, es.rademacher(np.random.default_rng(0), 19, pf.G))
        assert rr["power_failure"] is not None and rr["power_detects"] is False, name
