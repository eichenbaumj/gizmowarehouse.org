"""Step E's candidates B and C (and A's wrapper) against naive references written from the specification and the paper.

Independent check: written without reading pipeline/analysis/candidates.py or its own tests. The interface is learned from
help(candidates) and by calling it. The references are in tests/reference_candidates.py (dense, explicit dummies, loops).
Invented designs only; no file under data/ is read.

Tolerances (stated once, used throughout)
  RTOL_ALG = 1e-6   coefficients, residuals, variances, t statistics, degrees of freedom (two exact computations)
  bootstrap p-values: equal exactly, unless a replication's |t*| is within 1e-7 (relative) of the data's |t| (a tie the
    two sides may break differently by rounding); such values are skipped and counted
  endpoints: within the bisection tolerance 0.0005 (both are midpoints of intervals at most 0.0005 wide around the same
    crossing of a step function)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import estimator as es  # noqa: E402  (A is "the existing estimator, treated as given")
import reference_candidates as ref  # noqa: E402

RTOL_ALG = 1e-6
EVENT_TIMES = [-6, -5, -4, -2, -1, 0, 1, 2, 3]          # power_simulation.EVENT_TIMES (read as text)
PRE_IDX = [0, 1, 2]
T = 10


# ---- the generator -------------------------------------------------------------------------------------------------
def make_design(seed, G, *, near_collinear=False, absorbed_host=False, third_fe=False, single_unit_cluster=True,
                hosts_in=None, shuffle=True, sd_cluster=0.5):
    """A stacked event-study-like panel: units in states (clusters), ten window years each, unit effects (nested in
    states), region-by-calendar-year effects with regions that cross states and units that move region in year 5, an
    optional third grouping crossing states, two controls (optionally nearly collinear), hosts with nine event-year
    dummies (reference year -3 omitted). Cluster labels are non-contiguous and rows are shuffled so the label order
    differs from the order of appearance.
    """
    rng = np.random.default_rng(seed)
    sizes = rng.integers(1, 5, size=G)                      # unbalanced: 1 to 4 units a state
    if single_unit_cluster:
        sizes[0] = 1
    state_of_unit = np.repeat(np.arange(G), sizes)
    n_units = len(state_of_unit)
    n_regions = 3
    home = rng.integers(0, n_regions, size=n_units)
    movers = rng.random(n_units) < 0.3
    offset = rng.integers(0, 3, size=n_units)              # calendar start of each unit's window
    host = np.zeros(n_units, bool)
    cand_states = np.arange(G) if hosts_in is None else np.asarray(hosts_in)
    for s in cand_states:
        us = np.flatnonzero(state_of_unit == s)
        if hosts_in is not None or rng.random() < 0.5:
            host[rng.choice(us)] = True
    if host.sum() < 2:                                       # at least two hosts in two states
        for s in cand_states[:2]:
            host[np.flatnonzero(state_of_unit == s)[0]] = True
    region = np.repeat(home[:, None], T, axis=1)
    region[movers, 5:] = (home[movers, None] + 1) % n_regions
    if absorbed_host:                                        # a host alone in its own region: fully absorbed
        h = np.flatnonzero(host)[-1]
        region[h, :] = n_regions
    rows_u = np.repeat(np.arange(n_units), T)
    tt = np.tile(np.arange(T), n_units)
    cal = offset[rows_u] + tt
    cells = region.ravel() * 100 + cal
    groups = [rows_u, cells]
    if third_fe:
        fuel = rng.integers(0, 2, size=n_units)
        groups.append(fuel[rows_u] * 100 + cal)
    Xe = np.column_stack([host[rows_u] * (tt == e + 6) for e in EVENT_TIMES]).astype(float)
    c1 = rng.normal(size=len(rows_u)) + 0.5 * cal
    c2 = (c1 + 1e-3 * rng.normal(size=len(rows_u))) if near_collinear else rng.normal(size=len(rows_u))
    X = np.column_stack([Xe, c1, c2])
    labels = (np.arange(G)[::-1] * 7 + 3)[state_of_unit]     # distinct, non-contiguous, reversed against appearance
    cluster = labels[rows_u]
    e_state = sd_cluster * rng.normal(size=(G, T + 3))
    y = (rng.normal(size=n_units)[rows_u] + rng.normal(size=(n_regions + 1, T + 3))[region.ravel(), cal]
         + e_state[state_of_unit[rows_u], cal] + (0.3 + 0.4 * rng.random(n_units))[rows_u] * rng.normal(size=len(rows_u))
         + X[:, 9:] @ np.array([0.2, -0.1]))
    ramp = host[rows_u] * np.where(tt - 6 >= 0, np.minimum(1.0, (tt - 6 + 1) / 3.0), 0.0)
    if shuffle:
        perm = rng.permutation(len(y))
        X, y, cluster, ramp = X[perm], y[perm], cluster[perm], ramp[perm]
        groups = [g[perm] for g in groups]
    combo = np.zeros(X.shape[1])
    combo[7] = combo[8] = 0.5
    return {"X": X, "y": y, "groups": groups, "cluster": cluster, "ramp": ramp, "combo": combo, "pre": PRE_IDX,
            "G": G, "seed": seed}


SPECS = [  # (seed, G, options) : 22 designs
    (101, 6, {}), (102, 7, {"near_collinear": True}), (103, 8, {"absorbed_host": True}),
    (104, 9, {"third_fe": True}), (105, 10, {}), (106, 11, {"near_collinear": True, "third_fe": True}),
    (107, 12, {"absorbed_host": True, "near_collinear": True}), (108, 13, {}), (109, 14, {"third_fe": True}),
    (110, 15, {"absorbed_host": True}), (111, 16, {}), (112, 17, {"near_collinear": True}), (113, 18, {"third_fe": True}),
    (114, 19, {}), (115, 20, {"absorbed_host": True, "third_fe": True}), (116, 21, {}), (117, 22, {"near_collinear": True}),
    (118, 23, {}), (119, 24, {"third_fe": True, "absorbed_host": True}), (120, 25, {}),
    (121, 6, {"hosts_in": [1, 2], "near_collinear": True}), (122, 8, {"hosts_in": [0, 3], "sd_cluster": 1.5}),
]
BOOT = 199          # replications in the comparisons (both sides take the same v); 999 in test_b_full_999


def draws(G, boot, seed):
    return np.random.default_rng(seed).integers(0, 2, size=(boot, G)) * 2.0 - 1.0


def build(spec):
    seed, G, opts = spec
    d = make_design(seed, G, **opts)
    prob = cd.Problem(d["X"], d["groups"], d["cluster"], ramp=d["ramp"], combo=d["combo"], pre=d["pre"])
    des = ref.Design(d["X"], d["groups"], d["cluster"])
    return d, prob, des


TALLY = {"comparisons": 0, "agree": 0, "skipped_ties": 0}


def agree(cond, msg=""):
    TALLY["comparisons"] += 1
    assert cond, msg
    TALLY["agree"] += 1


def close(a, b, rtol=RTOL_ALG, atol=1e-10):
    return np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=rtol, atol=atol)


# ---- the reference checks itself -----------------------------------------------------------------------------------
def test_reference_pinv_refit_is_the_lstsq_refit():
    d, _, des = build(SPECS[2])
    for k in range(3):
        yk = d["y"] + np.random.default_rng(k).normal(size=len(d["y"]))
        b1, u1 = des.fit(yk)
        b2, u2 = des.fit_by_lstsq(yk)
        assert close(b1, b2, 1e-8) and close(u1, u2, 1e-8, 1e-8)


def test_reference_restricted_fit_satisfies_the_restriction_and_is_least_squares():
    d, _, des = build(SPECS[4])
    c = d["combo"]
    fitted, u = des.restricted_fit(d["y"], c[None, :], [0.123])
    # the restricted fitted values are X beta + D alpha with c'beta = 0.123: regress them on Z and read beta
    beta = des.L @ fitted
    assert c @ beta == pytest.approx(0.123, abs=1e-9)
    # residuals orthogonal to every direction the restriction leaves free (D and X null(c'))
    assert np.abs(des.D.T @ u).max() < 1e-8


# ---- hand-checkable tiny cases -------------------------------------------------------------------------------------
def tiny():
    """Four rows, two clusters {0,1} and {2,3}, one regressor x = (1, -1, 2, -2), an intercept as the only fixed effect,
    y = (1, 0, 0, 1).
      x has mean 0, so x~ = x, x'x = 10. y - ybar = (.5, -.5, -.5, .5); x'(y - ybar) = .5 + .5 - 1 - 1 = -1; b = -0.1.
      residuals u = (y - ybar) - b x = (.6, -.6, -.3, .3).
      CR1: scores s_1 = 1(.6) + (-1)(-.6) = 1.2, s_2 = 2(-.3) + (-2)(.3) = -1.2; sum s^2 = 2.88; CR0 = 2.88 / 100 = .0288.
        factor G/(G-1) (N-1)/(N-K) = 2 * 3/3 = 2, so V = .0576 and se = .24.
      CR2 (full model: H = 11'/4 + xx'/10, so H_jk = .25 + x_j x_k / 10):
        cluster 1 block of I - H: [[.65, -.15], [-.15, .65]], eigenvalues .8 on (1,-1)/sqrt2 and .5 on (1,1)/sqrt2.
        cluster 2 block: [[.35, .15], [.15, .35]], eigenvalues .5 on (1,1)/sqrt2 and .2 on (1,-1)/sqrt2.
        x_1 = (1,-1) lies on the .8 eigenvector, so A_1 x_1 = x_1/sqrt(.8); x_1'A_1 u_1 = 1.2/sqrt(.8).
        x_2 = (2,-2) lies on the .2 eigenvector, so x_2'A_2 u_2 = -1.2/sqrt(.2).
        middle = 1.44/.8 + 1.44/.2 = 1.8 + 7.2 = 9; V_CR2 = 9 / 100 = .09, se = .3.
      Satterthwaite (Eq. 11): p_1 = (I-H)[:, {0,1}] A_1 x_1 / 10 = (.8, -.8, -.4, .4) / (10 sqrt .8);
        p_2 = (-.8, .8, .4, -.4) / (10 sqrt .2). p_1'p_1 = .02, p_2'p_2 = .08, p_1'p_2 = -.04.
        nu = (.02 + .08)^2 / (.02^2 + .08^2 + 2 * .04^2) = .01 / .01 = 1.
      B at theta = 0 with v = the four sign patterns:
        restricted fit at b = 0: u_R = (.5, -.5, -.5, .5). v = (1, 1): y* = y, t* = -.1/.24 = -.41667.
        v = (1, -1): v u_R = (.5, -.5, .5, -.5), b* = x'(v u_R)/10 = .3, residuals (.2, -.2, -.1, .1), scores .4, -.4,
        V* = 2 * .32 / 100 = .0064, se* = .08, t* = 3.75. v = (-1, 1): t* = -3.75. v = (-1, -1): t* = .41667.
        |t| = .41667, so every replication is at least as large: p = 1 (two of them tie exactly).
    """
    X = np.array([[1.0], [-1.0], [2.0], [-2.0]])
    y = np.array([1.0, 0.0, 0.0, 1.0])
    groups = [np.zeros(4, int)]
    cluster = np.array([0, 0, 1, 1])
    return X, y, groups, cluster


def test_tiny_by_hand_reference():
    X, y, groups, cluster = tiny()
    des = ref.Design(X, groups, cluster)
    b, u = des.fit(y)
    assert b[0] == pytest.approx(-0.1) and u == pytest.approx([.6, -.6, -.3, .3])
    assert des.cr1(u)[0, 0] == pytest.approx(0.0576)
    c = ref.c_all(des, y, [1.0], [0], 0.0)
    assert c["V"][0, 0] == pytest.approx(0.09) and c["nu"] == pytest.approx(1.0)
    assert c["eta"] == pytest.approx(1.0)
    v = np.array([[1, 1], [1, -1], [-1, 1], [-1, -1]], float)
    ts, t = ref.b_tstar(des, y, [1.0], 0.0, v)
    assert t == pytest.approx(-0.1 / 0.24) and ts == pytest.approx([-0.1 / .24, 3.75, -3.75, 0.1 / .24])


def test_tiny_by_hand_implementation():
    X, y, groups, cluster = tiny()
    prob = cd.Problem(X, groups, cluster, combo=np.array([1.0]), pre=[0])
    B = cd.CandidateB(prob, boot=4)
    v = np.array([[1, 1], [1, -1], [-1, 1], [-1, -1]], float)
    s = B.session(y, v)
    agree(s.est == pytest.approx(-0.1), f"B estimate {s.est}")
    agree(s.se == pytest.approx(0.24), f"B clustered se {s.se} (hand: .24)")
    agree(np.allclose(s.tstar(0.0), [-0.1 / .24, 3.75, -3.75, 0.1 / .24]), f"B t* {s.tstar(0.0)}")
    agree(s.p_value(0.0, "test_at_the_true_value") == 1.0)
    C = cd.CandidateC(prob)
    b, u = C.fit(y)
    agree(np.allclose(C.vcov(u), [[0.09]]), f"CR2 {C.vcov(u)} (hand: .09)")
    agree(C.nu == pytest.approx(1.0), f"nu {C.nu} (hand: 1)")
    agree(C.t_test(-0.1, 0.3, 0.0) == pytest.approx(2 * stats.t.sf(1 / 3, 1)))


def test_tiny_two_cluster_cr2_with_a_cluster_nested_effect():
    """Unit effects nested in clusters make B_i singular (the case Eq. 7's Moore-Penrose inverse exists for)."""
    rng = np.random.default_rng(5)
    units, Tn = 6, 4
    u = np.repeat(np.arange(units), Tn)
    t = np.tile(np.arange(Tn), units)
    cl = (np.arange(units) % 3)[u]
    X = np.column_stack([(u < 3) * (t >= 2) * 1.0, rng.normal(size=len(u))])
    y = rng.normal(size=len(u))
    des = ref.Design(X, [u, t], cl)
    c = ref.c_all(des, y, [1.0, 0.0], [0], 0.0)
    prob = cd.Problem(X, [u, t], cl, combo=np.array([1.0, 0.0]), pre=[0])
    C = cd.CandidateC(prob)
    b, uu = C.fit(y)
    agree(close(C.vcov(uu), c["V"]), f"CR2 {C.vcov(uu)} vs {c['V']}")
    agree(C.nu == pytest.approx(c["nu"], rel=RTOL_ALG), f"nu {C.nu} vs {c['nu']}")
    agree(C.eta == pytest.approx(c["eta"], rel=RTOL_ALG), f"eta {C.eta} vs {c['eta']}")


# ---- the twenty-two invented designs -------------------------------------------------------------------------------
@pytest.fixture(scope="module", params=range(len(SPECS)), ids=[f"seed{s[0]}_G{s[1]}" for s in SPECS])
def case(request):
    return build(SPECS[request.param])


def test_unrestricted_fit_and_clustered_se(case):
    d, prob, des = case
    B = cd.CandidateB(prob, boot=BOOT)
    v = draws(d["G"], BOOT, d["seed"])
    s = B.session(d["y"], v)
    b, u = des.fit(d["y"])
    agree(close(s.b, b), f"b {s.b} vs {b}")
    agree(close(s.u, u, atol=1e-9), "residuals")
    agree(close(s.V, des.cr1(u)), "CR1 variance")
    agree(s.se == pytest.approx(np.sqrt(d["combo"] @ des.cr1(u) @ d["combo"]), rel=RTOL_ALG), "clustered se")


def test_b_tstar_and_pvalue_at_several_values(case):
    d, prob, des = case
    B = cd.CandidateB(prob, boot=BOOT)
    v = draws(d["G"], BOOT, d["seed"])
    s = B.session(d["y"], v)
    for k in (-3.0, -1.5, 0.0, 0.7, 2.0, 25.0):
        theta = s.est + k * s.se
        r = ref.b_pvalue(des, d["y"], d["combo"], theta, v)
        agree(close(s.tstar(theta), r["tstar"], rtol=1e-6, atol=1e-8), f"t* at {k} se")
        if r["near_tie"]:
            TALLY["skipped_ties"] += 1
            continue
        agree(s.p_value(theta, "test_at_the_true_value") == r["p"], f"p at {k} se: {s.p_value(theta, 'x')} vs {r['p']}")


def test_b_early_years_test(case):
    d, prob, des = case
    B = cd.CandidateB(prob, boot=BOOT)
    v = draws(d["G"], BOOT, d["seed"])
    s = B.session(d["y"], v)
    r = ref.b_early_p(des, d["y"], d["pre"], v)
    if r["near_tie"]:
        TALLY["skipped_ties"] += 1
        return
    agree(s.early_years_p() == r["p"], f"early p {s.early_years_p()} vs {r['p']}")


def test_b_endpoints_and_run(case):
    d, prob, des = case
    B = cd.CandidateB(prob, boot=BOOT)
    v = draws(d["G"], BOOT, d["seed"])
    s = B.session(d["y"], v)
    pf = lambda th: ref.b_pvalue(des, d["y"], d["combo"], th, v)["p"]   # noqa: E731
    for sign in (1, -1):
        e_imp, st_imp = s.endpoint(sign)
        e_ref, st_ref = ref.b_search(pf, s.est, s.se, sign)
        agree(st_imp == st_ref, f"side {sign}: state {st_imp} vs {st_ref}")
        if st_ref == "bounded":
            agree(abs(e_imp - e_ref) <= ref.TOL + 1e-12, f"side {sign}: endpoint {e_imp} vs {e_ref}")
            # the implementation's own endpoint straddles 0.10 on my p-function (assuming local monotonicity)
            agree(pf(e_imp - sign * ref.TOL) >= 0.10 and pf(e_imp + sign * ref.TOL) < 0.10, "endpoint straddles 0.10")
    truth = 0.0
    res = B.run(d["y"], truth, v, planted=None)
    rp = ref.b_pvalue(des, d["y"], d["combo"], truth, v)
    if not rp["near_tie"]:
        agree(res["covered"] == (rp["p"] >= 0.10), "covered at the true value")
    re = ref.b_early_p(des, d["y"], d["pre"], v)
    if not re["near_tie"]:
        agree(res["early_rejected"] == (re["p"] < 0.10), "early_rejected")
    w_ref = (res["hi"] - res["lo"]) if (res["lo_state"] == res["hi_state"] == "bounded") else np.inf
    agree(res["width"] == pytest.approx(w_ref), "width")
    agree(res["miss"] == (not res["covered"]) and res["reject"] == res["early_rejected"], "miss/reject")


def test_b_power_detects(case):
    """power_detects: on y + planted * ramp, the test of zero rejects at 0.10 with the estimate above zero."""
    d, prob, des = case
    B = cd.CandidateB(prob, boot=BOOT)
    v = draws(d["G"], BOOT, d["seed"])
    planted = 0.05
    res = B.run(d["y"], 0.0, v, planted=planted)
    yp = d["y"] + planted * d["ramp"]
    r = ref.b_pvalue(des, yp, d["combo"], 0.0, v)
    if r["near_tie"]:
        TALLY["skipped_ties"] += 1
        return
    est = float(d["combo"] @ des.fit(yp)[0])
    agree(res["power_detects"] == (r["p"] < 0.10 and est > 0), f"power {res['power_detects']} vs p={r['p']} est={est}")


def test_c_against_reference(case):
    d, prob, des = case
    C = cd.CandidateC(prob)
    r = ref.c_all(des, d["y"], d["combo"], d["pre"], 0.0)
    b, u = C.fit(d["y"])
    agree(close(b, r["b"]), "C coefficients")
    V = C.vcov(u)
    agree(close(V, r["V"], rtol=1e-6, atol=1e-12), f"CR2 variance, max rel diff {np.max(np.abs(V - r['V'])) / np.max(np.abs(r['V']))}")
    agree(C.nu == pytest.approx(r["nu"], rel=RTOL_ALG), f"nu {C.nu} vs {r['nu']}")
    agree(C.eta == pytest.approx(r["eta"], rel=RTOL_ALG), f"eta {C.eta} vs {r['eta']}")
    agree(C.crit == pytest.approx(r["crit"], rel=RTOL_ALG), f"crit {C.crit} vs {r['crit']}")
    for theta in (0.0, r["est"] + r["se"], r["est"] - 2.5 * r["se"]):
        agree(C.t_test(r["est"], r["se"], theta) == pytest.approx(r["cr2"].t_pvalue(r["est"], r["se"], theta, r["nu"]), rel=1e-6))
    res = C.run(d["y"], 0.0, None, planted=None)
    q = len(d["pre"])
    if not r["eta"] > q - 1:
        # Eq. (12)'s F(q, eta - q + 1) has no positive denominator degrees of freedom: undefined, so (E4.1) a failure
        agree(np.isnan(C.aht(r["b"], r["V"])), "AHT p is NaN where eta <= q - 1")
        agree(failed_ok(res) and res["failure"]["cause"] == cd.UNDEFINED_DEGREES_OF_FREEDOM, f"C failure {res['failure']}")
        return
    agree(C.aht(r["b"], r["V"]) == pytest.approx(r["aht"]["p"], rel=1e-6, abs=1e-12), f"AHT p {C.aht(r['b'], r['V'])} vs {r['aht']['p']}")
    agree(res["lo"] == pytest.approx(r["lo"], rel=1e-6) and res["hi"] == pytest.approx(r["hi"], rel=1e-6), "C range")
    agree(res["covered"] == r["covered"] and res["early_rejected"] == r["early_rejected"], "C covered / early")
    agree(res["lo_state"] == res["hi_state"] == "bounded" and res["width"] == pytest.approx(r["hi"] - r["lo"]), "C width")
    # the module-level formula functions on my own P matrices
    P = np.column_stack(r["cr2"].p_vectors(np.asarray(d["combo"], float)))
    agree(cd.satterthwaite(P) == pytest.approx(r["nu"], rel=RTOL_ALG), "satterthwaite(P)")
    Pq = r["cr2"].aht_p(d["pre"])
    P3 = np.stack([np.column_stack(Pq[s]) for s in range(len(d["pre"]))], axis=1)     # N x q x m, P3[:, s, i] = p_si
    agree(cd.aht_degrees_of_freedom(P3) == pytest.approx(r["eta"], rel=RTOL_ALG), "aht_degrees_of_freedom(P)")


def test_c_power_detects(case):
    d, prob, des = case
    C = cd.CandidateC(prob)
    res = C.run(d["y"], 0.0, None, planted=0.05)
    r = ref.c_all(des, d["y"] + 0.05 * d["ramp"], d["combo"], d["pre"], 0.0)
    if not r["eta"] > len(d["pre"]) - 1:
        # the flat dataset failed at the AHT (eta <= q - 1): no detection is counted. NOTE: power_failure is None here,
        # although the result docstring says a failure is "recorded in power_failure"; reported, not asserted.
        agree(res["power_detects"] is False, "C power on a failed design")
        return
    agree(res["power_detects"] == (r["p_truth"] < 0.10 and r["est"] > 0), "C power")


def test_a_wrapper_reads_the_estimator(case):
    d, prob, des = case
    A = cd.CandidateA(prob, boot=BOOT)
    v = draws(d["G"], BOOT, d["seed"])
    truth = 0.0
    res = A.run(d["y"], truth, v, planted=None)
    fit = es.Fit(d["y"], d["X"], d["groups"], d["cluster"])
    sm = fit.summary(v, d["combo"], d["pre"])
    agree(res["lo"] == pytest.approx(sm["lo"]) and res["hi"] == pytest.approx(sm["hi"]), "A range")
    agree(res["covered"] == (sm["lo"] <= truth <= sm["hi"]), "A covered")
    agree(res["early_rejected"] == (sm["pre_p_bootstrap"] < 0.10), "A early")
    agree(res["width"] == pytest.approx(sm["hi"] - sm["lo"]), "A width")
    resp = A.run(d["y"], truth, v, planted=0.05)
    smp = es.Fit(d["y"] + 0.05 * d["ramp"], d["X"], d["groups"], d["cluster"]).summary(v, d["combo"], d["pre"])
    agree(resp["power_detects"] == (smp["lo"] > 0), "A power: range above zero")


# ---- B with 999 replications on three designs ----------------------------------------------------------------------
@pytest.mark.parametrize("i", [0, 9, 19])
def test_b_full_999(i):
    d, prob, des = build(SPECS[i])
    v = draws(d["G"], 999, d["seed"] + 1)
    B = cd.CandidateB(prob)
    s = B.session(d["y"], v)
    r = ref.b_pvalue(des, d["y"], d["combo"], 0.0, v)
    if not r["near_tie"]:
        agree(s.p_value(0.0, "test_at_the_true_value") == r["p"], "p at zero, 999")
    e = ref.b_early_p(des, d["y"], d["pre"], v)
    if not e["near_tie"]:
        agree(s.early_years_p() == e["p"], "early p, 999")


# ---- end states ----------------------------------------------------------------------------------------------------
INCOMPLETE_CASES = [(906, 6), (906, 7), (907, 6), (934, 7), (935, 6), (945, 7)]


@pytest.mark.parametrize("seed,G", INCOMPLETE_CASES)
def test_search_incomplete_when_p_never_falls_below_ten_percent(seed, G):
    """Six or seven clusters, one host, in one state: the null-imposed p-value stays at or above 0.10 out to 640 se on
    one side (found by a scan over seeds 900-959; the reference confirms it independently below)."""
    d = make_design(seed, G, hosts_in=[2])
    prob = cd.Problem(d["X"], d["groups"], d["cluster"], ramp=d["ramp"], combo=d["combo"], pre=d["pre"])
    des = ref.Design(d["X"], d["groups"], d["cluster"])
    v = draws(G, BOOT, 3)
    s = cd.CandidateB(prob, boot=BOOT).session(d["y"], v)
    pf = lambda th: ref.b_pvalue(des, d["y"], d["combo"], th, v)["p"]   # noqa: E731
    seen = []
    for sign in (1, -1):
        st_ref = ref.b_search(pf, s.est, s.se, sign)[1]
        p640 = pf(s.est + sign * 640 * s.se)
        seen.append((sign, st_ref, p640))
        e, st = s.endpoint(sign)
        agree(st == st_ref, f"side {sign}: {st} vs reference {st_ref} (p at 640 se on the reference: {p640})")
        if st_ref == "search incomplete":
            agree(np.isnan(e), "incomplete endpoint is NaN")
    # the case must actually exercise the incomplete state on at least one side (self-check of the construction)
    assert any(st == "search incomplete" for _, st, _ in seen), seen
    res = cd.CandidateB(prob, boot=BOOT).run(d["y"], 0.0, v, planted=None)
    agree(res["width"] == np.inf and res["failure"] is None, "incomplete is infinitely wide and not a failure")
    agree("unbounded" not in (res["lo_state"], res["hi_state"]), "never unbounded")


def test_search_side_end_states_on_synthetic_p_functions():
    """search_side on p-functions written down by hand: a crossing, none by 640, a rise along the bracket, a failure."""
    est, se = 1.0, 0.01
    crossing = 1.0 + 0.137
    st = cd.search_side(lambda th: 0.5 if th < crossing else 0.05, est, se, 1)
    agree(st[1] == "bounded" and abs(st[0] - crossing) <= 0.0005, f"bounded {st}")
    st = cd.search_side(lambda th: 0.5, est, se, 1)
    agree(st[1] == "search incomplete" and np.isnan(st[0]), f"never crosses {st}")
    # p falls then rises along the bracket before any crossing: not monotone
    st = cd.search_side(lambda th: 0.3 if abs(th - est) < 15 * se else 0.6, est, se, 1)
    agree(st[1] == "search incomplete", f"rising p {st}")
    st = cd.search_side(lambda th: 0.5 if th > 1.0 - 0.042 else 0.0, est, se, -1)
    agree(st[1] == "bounded" and abs(st[0] - (1.0 - 0.042)) <= 0.0005, f"lower side {st}")

    def boom(th):
        raise cd.Failed(cd.NON_FINITE_BOOTSTRAP_T, "endpoint_upper")
    with pytest.raises(cd.Failed):
        cd.search_side(boom, est, se, 1)


# ---- failures are reported, never valid results --------------------------------------------------------------------
def failed_ok(res):
    return (res["failure"] is not None and res["covered"] is None and res["early_rejected"] is None and res["miss"]
            and res["reject"] and res["width"] == np.inf and "unbounded" not in (res["lo_state"], res["hi_state"]))


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_outcome_fails_every_candidate(bad):
    d, prob, _ = build(SPECS[5])
    y = d["y"].copy()
    y[17] = bad
    v = draws(d["G"], BOOT, 1)
    for C in (cd.CandidateA(prob, boot=BOOT), cd.CandidateB(prob, boot=BOOT), cd.CandidateC(prob)):
        agree(failed_ok(C.run(y, 0.0, v)), f"{C.name} on a non-finite outcome")


@pytest.mark.parametrize("how", ["duplicate_column", "absorbed_by_unit_effect", "event_year_never_observed"])
def test_rank_deficient_design_fails_every_candidate(how):
    d = make_design(303, 9)
    X = d["X"].copy()
    if how == "duplicate_column":
        X[:, 10] = X[:, 9]
    elif how == "absorbed_by_unit_effect":
        X[:, 10] = (d["groups"][0] % 3).astype(float)            # constant within each unit
    else:
        X[:, 0] = 0.0                                             # an event year with no host row
    prob = cd.Problem(X, d["groups"], d["cluster"], ramp=d["ramp"], combo=d["combo"], pre=d["pre"])
    v = draws(d["G"], BOOT, 1)
    with pytest.raises(ref.ReferenceFailure):
        ref.Design(X, d["groups"], d["cluster"])
    for C in (cd.CandidateA(prob, boot=BOOT), cd.CandidateB(prob, boot=BOOT), cd.CandidateC(prob)):
        res = C.run(d["y"], 0.0, v)
        agree(failed_ok(res) and res["failure"]["cause"] == "rank_deficient", f"{C.name}: {res['failure']}")


@pytest.mark.parametrize("seed,G", [(914, 6), (933, 6), (952, 7)])
def test_naturally_rank_deficient_single_host_design_fails(seed, G):
    """One host in one state whose event years the fixed effects absorb (found by the same scan): run() must fail every
    candidate with rank_deficient, and the reference agrees the design is rank deficient."""
    d = make_design(seed, G, hosts_in=[2])
    with pytest.raises(ref.ReferenceFailure):
        ref.Design(d["X"], d["groups"], d["cluster"])
    prob = cd.Problem(d["X"], d["groups"], d["cluster"], ramp=d["ramp"], combo=d["combo"], pre=d["pre"])
    v = draws(G, BOOT, 3)
    for C in (cd.CandidateA(prob, boot=BOOT), cd.CandidateB(prob, boot=BOOT), cd.CandidateC(prob)):
        res = C.run(d["y"], 0.0, v)
        agree(failed_ok(res) and res["failure"]["cause"] == "rank_deficient", f"{C.name}: {res['failure']}")


def test_b_session_on_a_failed_design_raises_failed():
    # was a strict xfail (AttributeError); fixed in candidates.py: session() now raises Failed (rank_deficient)
    d = make_design(914, 6, hosts_in=[2])
    prob = cd.Problem(d["X"], d["groups"], d["cluster"], ramp=d["ramp"], combo=d["combo"], pre=d["pre"])
    B = cd.CandidateB(prob, boot=BOOT)
    assert B.design_failure is not None
    with pytest.raises(cd.Failed):
        B.session(d["y"], draws(6, BOOT, 3))


@pytest.mark.xfail(strict=True,
                   reason="UNDERSPECIFIED: an outcome fitted exactly by the fixed effects has, in exact arithmetic, zero "
                          "residuals and a zero clustered se (E4.1: non_finite_or_zero_standard_error); numerically the se "
                          "is ~1e-15 and all three candidates (and my reference) accept it as a valid, bounded result")
def test_zero_standard_error_fails_every_candidate():
    """An outcome fitted exactly by the fixed effects: every residual is zero, the clustered se is zero."""
    d, prob, des = build(SPECS[3])
    y = des.D @ np.random.default_rng(0).normal(size=des.D.shape[1])
    v = draws(d["G"], BOOT, 1)
    for C in (cd.CandidateA(prob, boot=BOOT), cd.CandidateB(prob, boot=BOOT), cd.CandidateC(prob)):
        res = C.run(y, 0.0, v)
        agree(failed_ok(res), f"{C.name}: zero residuals gave {res}")


def test_mp_inverse_sqrt_against_reference():
    rng = np.random.default_rng(9)
    Q = np.linalg.qr(rng.normal(size=(5, 5)))[0]
    B = Q @ np.diag([2.0, 0.5, 0.1, 0.0, 0.0]) @ Q.T
    agree(close(cd.mp_inverse_sqrt(B), ref.mp_inverse_sqrt(B), atol=1e-10), "B^{+1/2}")
    Bn = B.copy()
    Bn[0, 0] = np.nan
    with pytest.raises(cd.Failed):
        cd.mp_inverse_sqrt(Bn)


def test_zz_tally():
    """Prints the count of comparisons (runs last in file order)."""
    print(f"\nTALLY {TALLY}")
