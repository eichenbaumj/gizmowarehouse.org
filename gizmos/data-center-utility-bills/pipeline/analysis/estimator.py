#!/usr/bin/env python3
"""Least squares with several sets of fixed effects, and the wild cluster bootstrap done in full.

The plan's regressions have utility effects, market-region-by-year effects that
a utility can move between (docs/DECISIONS.md, D-30), fuel-mix-group-by-year
effects and two degree-day controls. With utilities changing region inside a
window the design is no longer a balanced two-way layout, so the closed form in
power_simulation.estimate() does not apply. This module is the general fit.

Fixed effects are removed exactly: the utility effects by subtracting means, the
rest by solving the small system that is left (class Projection). That is the
least-squares projection for any number of groupings and any pattern of cells.

The bootstrap is the planned one (PREANALYSIS.md): wild cluster bootstrap by
state, bootstrap-t, unrestricted residuals, Rademacher weights. Each replication
multiplies every cluster's residuals by plus or minus one, rebuilds the outcome,
and refits everything, fixed effects included. It is done without refitting in a
loop. With X the regressors after the fixed effects are removed, u the
residuals, and M the projection that removes the fixed effects:

    replication's coefficients minus the estimate   A^-1 * sum_h v_h S_h         S_h = X_h' u_h
    replication's residuals                         sum_h v_h M(u 1_h) - X * (that shift)
    replication's cluster scores                    sum_h v_h T[g, h] - A_g * shift   T[g, h] = X_g' [M(u 1_h)]_g

so one projection of the G columns u*1_h gives every replication exactly. The
closed form used in the first two simulation runs dropped the term in which
re-estimating the region-by-year effects moves residuals between clusters; this
does not. The two agree where every fixed effect is nested inside a cluster.

Planted effects. Outcomes are y + tau * p for a planted path p. Everything above
is linear in the outcome, so u(tau) = u0 + tau * up and the same for S and T:
one fit gives the estimate, its standard error and its bootstrap range for any
tau, which is how a misdated effect (a path that is not in the span of the
event-time regressors) is handled without refitting.
"""
from __future__ import annotations

import numpy as np
from scipy import sparse


def indicator(codes: np.ndarray) -> sparse.csr_matrix:
    """N x groups matrix of ones marking each row's group."""
    codes = np.asarray(codes)
    n = len(codes)
    return sparse.csr_matrix((np.ones(n), (np.arange(n), codes)), shape=(n, int(codes.max()) + 1))


class Projection:
    """Removes a set of fixed effects from columns, exactly.

    The first grouping (utilities, by convention: the one with the most levels) is swept out by
    subtracting group means. The other groupings' indicator columns, with the first grouping swept
    out of them, form a small dense system that is solved once by pseudo-inverse, so cells that are
    collinear with one another or with the first grouping cost nothing. This is the least-squares
    projection itself, not an iteration toward it; an earlier version alternated between the
    groupings and did not converge when a few utilities linked two large regions.
    """

    def __init__(self, groups: list[np.ndarray], rcond: float = 1e-10):
        coded = [np.unique(g, return_inverse=True)[1] for g in groups]
        self.Su = indicator(coded[0])
        self.nu = np.asarray(self.Su.sum(0)).ravel()
        self.D = None
        if len(coded) > 1:
            self.D = sparse.hstack([indicator(c) for c in coded[1:]], format="csr")
            UD = (self.Su.T @ self.D).toarray()                                 # first grouping x other levels
            gram = (self.D.T @ self.D).toarray() - UD.T @ (UD / self.nu[:, None])
            self.P = np.linalg.pinv(gram, rcond=rcond, hermitian=True)
        self.iterations = 1

    def _sweep(self, M: np.ndarray) -> np.ndarray:
        return M - self.Su @ ((self.Su.T @ M) / self.nu[:, None])

    def __call__(self, M: np.ndarray) -> np.ndarray:
        M = np.array(M, dtype=float, copy=True)
        flat = M.ndim == 1
        if flat:
            M = M[:, None]
        M = self._sweep(M)
        if self.D is not None:
            M = M - self._sweep(self.D @ (self.P @ (self.D.T @ M)))
        return M[:, 0] if flat else M


RANK_TOLERANCE = 1e-8


class RankDeficient(ValueError):
    """The regressors are not all identified once the fixed effects are removed (D-59, item 7).

    Raised before anything is inverted, so a fit that cannot be computed fails in words and never returns
    coefficients from an unstable inverse. Callers that loop over datasets count it; they do not drop it.
    """


def check_rank(Xt: np.ndarray, X: np.ndarray | None = None, tol: float = RANK_TOLERANCE) -> dict:
    """Singular values of the regressors after the fixed effects are removed; raises RankDeficient if they fail.

    Two tests. The smallest singular value has to be more than `tol` times the largest. And the largest has to be
    more than `tol` times the largest singular value of the regressors before the fixed effects were removed (`X`,
    when given): otherwise everything was absorbed and what is left is rounding error, which can pass the first test.
    """
    Xt = np.asarray(Xt, dtype=float)
    if Xt.ndim != 2 or Xt.shape[1] == 0:
        raise RankDeficient("there are no regressors")
    sv = np.linalg.svd(Xt, compute_uv=False)
    top, low = float(sv[0]), float(sv[-1])
    before = float(np.linalg.svd(np.asarray(X, dtype=float), compute_uv=False)[0]) if X is not None else None
    out = {"largest": top, "smallest": low, "ratio": (low / top) if top > 0 else 0.0,
           "largest_relative_to_before_the_fixed_effects": (top / before) if before else None}
    if not np.isfinite(sv).all():
        raise RankDeficient("the regressors are not finite after the fixed effects are removed")
    if top <= 0 or (before is not None and top <= tol * before):
        raise RankDeficient("the fixed effects absorb every regressor: nothing is identified")
    if low <= tol * top:
        k = int((sv <= tol * top).sum())
        raise RankDeficient(f"{k} of {Xt.shape[1]} regressors are not identified once the fixed effects are removed "
                            f"(smallest singular value {low:.3g} against {top:.3g})")
    return out


class Fit:
    """One regression: y on X with fixed effects, clustered, with the pieces the bootstrap needs.

    Raises RankDeficient, before inverting anything, if the regressors are not all identified.

    y        (N,) outcome
    X        (N, K) regressors (not yet purged of the fixed effects)
    groups   list of (N,) fixed-effect codes
    cluster  (N,) cluster codes
    paths    (N, P) planted paths, optional. The outcome under path j at size tau is y + tau * paths[:, j].
    projection  optional Projection(groups) already computed (ps.assemble builds one to screen the gas-share columns)
    """

    def __init__(self, y, X, groups, cluster, paths=None, projection: Projection | None = None):
        y, X = np.asarray(y, dtype=float), np.asarray(X, dtype=float)
        self.N, self.K = X.shape
        proj = projection if projection is not None else Projection(groups)     # a Projection of the same groups may be reused
        P = np.zeros((self.N, 0)) if paths is None else np.asarray(paths, dtype=float).reshape(self.N, -1)
        self.n_paths = P.shape[1]
        R = proj(np.column_stack([y, X, P]))
        yt, Xt, Pt = R[:, 0], R[:, 1:1 + self.K], R[:, 1 + self.K:]
        codes = np.unique(cluster, return_inverse=True)[1]
        self.G = int(codes.max()) + 1
        C = indicator(codes)
        self.rank = check_rank(Xt, X)                                   # fails in words; never an unstable inverse (D-59)
        self.A = Xt.T @ Xt
        self.Ainv = np.linalg.inv(self.A)
        # coefficients and residuals: column 0 is the data, column 1 + j is planted path j
        Y = np.column_stack([yt, Pt])
        self.B = self.Ainv @ (Xt.T @ Y)                                 # K x (1 + P)
        U = Y - Xt @ self.B                                             # N x (1 + P)
        self.S = np.stack([C.T @ (Xt * U[:, [j]]) for j in range(U.shape[1])])          # (1 + P) x G x K
        self.Ag = np.stack([(Xt[codes == g].T @ Xt[codes == g]) for g in range(self.G)])  # G x K x K
        # M(u 1_h) for every cluster h and every outcome column, then T[j, g, h, k] = X_g' [M(u_j 1_h)]_g
        W = proj(np.column_stack([C.multiply(U[:, [j]]).toarray() for j in range(U.shape[1])]))
        W = W.reshape(self.N, U.shape[1], self.G)
        self.T = np.stack([np.stack([C.T @ (Xt[:, [k]] * W[:, j, :]) for k in range(self.K)], axis=-1)
                           for j in range(U.shape[1])])                   # (1 + P) x G x G x K
        self.factor = (self.G / (self.G - 1)) * ((self.N - 1) / (self.N - self.K))
        self.iterations = proj.iterations

    # ---- one outcome: the data plus tau times a planted path --------------------------------
    def _mix(self, arr, path, tau):
        return arr[0] if path is None or tau == 0 else arr[0] + tau * arr[1 + path]

    def coef(self, path=None, tau=0.0) -> np.ndarray:
        return self._mix(self.B.T, path, tau)

    def vcov(self, path=None, tau=0.0) -> np.ndarray:
        S = self._mix(self.S, path, tau)
        return self.factor * self.Ainv @ (S.T @ S) @ self.Ainv

    def bootstrap(self, v: np.ndarray, combo: np.ndarray, pre: list[int] | None = None, path=None, tau=0.0,
                  shortcut: bool = False) -> dict:
        """Bootstrap-t statistics for the combination `combo` of coefficients, and Wald statistics for `pre`.

        v is replications x clusters, Rademacher. Returns {"t": (B,), "wald": (B,) or None}.
        `shortcut` reproduces what the first two simulation runs did: residuals are flipped after the fixed
        effects are removed and the fixed effects are not re-estimated, so a cluster's scores move only with
        its own weight. It exists to measure the difference (D-39), not to be used.
        """
        S, T = self._mix(self.S, path, tau), self._mix(self.T, path, tau)
        if shortcut:
            T = np.zeros_like(T)
            T[np.arange(self.G), np.arange(self.G)] = S
        shift = v @ S @ self.Ainv                                           # B x K: replication's coefficients minus the estimate
        scores = np.einsum("bh,ghk->bgk", v, T) - np.einsum("gkl,bl->bgk", self.Ag, shift)
        a = scores @ (self.Ainv @ combo)                                     # B x G
        se = np.sqrt(self.factor * (a ** 2).sum(1))
        out = {"t": (shift @ combo) / np.where(se > 0, se, np.nan), "wald": None}
        if pre:
            proj = scores @ self.Ainv[pre].T                                 # B x G x len(pre)
            V = self.factor * np.einsum("bgi,bgj->bij", proj, proj)
            d = shift[:, pre]
            try:
                out["wald"] = np.einsum("bi,bi->b", d, np.linalg.solve(V, d[:, :, None])[:, :, 0])
            except np.linalg.LinAlgError:
                # A replication whose variance cannot be inverted has no statistic. It is marked (NaN) and counted as a
                # numerical failure of the dataset by summary(); it is never replaced by a pseudo-inverse (D-95 item 7, E4.1).
                out["wald"] = np.array([_solve_or_nan(m, x) for x, m in zip(d, V)])
                out["singular_replications"] = int(np.isnan(out["wald"]).sum())
        return out

    def summary(self, v: np.ndarray, combo: np.ndarray, pre: list[int] | None = None, path=None, tau=0.0, level=0.90,
                shortcut: bool = False) -> dict:
        """Estimate, standard error, bootstrap-t range, and the early-years test with its bootstrap p-value.

        Numerical failures are never dropped (D-95 section 3 item 7; docs/gate1/step-e-rules-2026-11-18.md E4.1). If any
        bootstrap replication is not finite, or a variance cannot be inverted, the dataset has failed: `numerical_failure`
        carries the cause (one of FAILURE_CAUSES) and the range and the bootstrap p-value are NaN, so no quantile is taken
        over the replications that happened to be finite. `analytic_failure` is set only when the estimate, its standard
        error or the observed early-years statistic cannot be computed, which fails the analytic readings too. Callers
        count a failed dataset in the denominator, as a miss and a rejection, and report the causes apart.
        """
        b, V = self.coef(path, tau), self.vcov(path, tau)
        est, se = float(combo @ b), float(np.sqrt(max(float(combo @ V @ combo), 0.0)))
        out = {"est": est, "se": se, "lo": np.nan, "hi": np.nan, "clusters": self.G, "numerical_failure": None, "analytic_failure": None}
        if not (np.isfinite(est) and np.isfinite(se) and se > 0):
            out["numerical_failure"] = out["analytic_failure"] = NON_FINITE_STANDARD_ERROR
        wald = np.nan
        if pre:
            bp = b[pre]
            out.update(pre_wald=np.nan, pre_p_bootstrap=np.nan, max_abs_early=float(np.abs(bp).max()))
            try:
                wald = float(bp @ np.linalg.solve(V[np.ix_(pre, pre)], bp))
            except np.linalg.LinAlgError:
                wald = np.nan
            if not np.isfinite(wald):
                out["numerical_failure"] = out["numerical_failure"] or SINGULAR_WALD_VARIANCE
                out["analytic_failure"] = out["analytic_failure"] or SINGULAR_WALD_VARIANCE
            out["pre_wald"] = wald
        if out["numerical_failure"]:
            return out
        bs = self.bootstrap(v, combo, pre, path, tau, shortcut)
        cause = bootstrap_failure(bs, pre)
        if cause:
            out["numerical_failure"] = cause
            return out
        lo_q, hi_q = np.quantile(bs["t"], [(1 - level) / 2, (1 + level) / 2])
        out["lo"], out["hi"] = est - hi_q * se, est - lo_q * se
        if pre:
            out["pre_p_bootstrap"] = float(np.mean(bs["wald"] >= wald))
        return out


# Causes of a numerical failure (D-95 item 7; E4.1, E4.3). Each is reported apart from ordinary misses and rejections.
RANK_DEFICIENT = "rank_deficient"                                  # estimator.RankDeficient, raised before any inverse
NON_FINITE_STANDARD_ERROR = "non_finite_or_zero_standard_error"
SINGULAR_WALD_VARIANCE = "singular_early_years_variance"
NON_FINITE_BOOTSTRAP_T = "non_finite_bootstrap_replication"
NON_FINITE_BOOTSTRAP_WALD = "non_finite_bootstrap_early_years_replication"
FAILURE_CAUSES = (RANK_DEFICIENT, NON_FINITE_STANDARD_ERROR, SINGULAR_WALD_VARIANCE, NON_FINITE_BOOTSTRAP_T, NON_FINITE_BOOTSTRAP_WALD)


def bootstrap_failure(bs: dict, pre) -> str | None:
    """The cause if any replication of the bootstrap is not finite, else None. Nothing is dropped or replaced."""
    if not np.isfinite(np.asarray(bs["t"], dtype=float)).all():
        return NON_FINITE_BOOTSTRAP_T
    if pre and not np.isfinite(np.asarray(bs["wald"], dtype=float)).all():
        return NON_FINITE_BOOTSTRAP_WALD
    return None


def _solve_or_nan(m: np.ndarray, x: np.ndarray) -> float:
    try:
        return float(x @ np.linalg.solve(m, x))
    except np.linalg.LinAlgError:
        return float("nan")


def rademacher(rng: np.random.Generator, boot: int, clusters: int) -> np.ndarray:
    return rng.integers(0, 2, size=(boot, clusters)) * 2.0 - 1.0
