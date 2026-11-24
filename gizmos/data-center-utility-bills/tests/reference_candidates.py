"""Naive reference implementations of step E's candidates B and C, written from the specification and the paper only.

Written without reading pipeline/analysis/candidates.py, its tests, or inference_comparison.py. Every fixed effect is an
explicit dummy column, every matrix is dense, and every bootstrap replication and every cluster is a Python loop. Nothing
is shared with the implementation (estimator.py is not imported either).

Sources
  Specification: docs/gate1/step-e-rules-2026-11-18.md sections 1 to 4; docs/DECISIONS.md D-59 rule 4.1 (lines 1408-1448)
  and D-61 section 7.2 (lines 1850-1868).
  Paper: Pustejovsky and Tipton, "Small sample methods for cluster-robust variance estimation and hypothesis testing in
  fixed effects models", arXiv:1601.01981v2 (stat.ME, 6 Nov 2022; dated November 8, 2022 on its title page), fetched
  2026-11-18 and read through pdftotext. Equations used: (1) the model, (2) the absorbed estimator, (4) the CRVE with
  adjustment matrices, (7) and (8) the generalized BRL adjustment A_i = D_i' B_i^{+1/2} D_i with
  B_i = D_i (I - H_X)_i Phi (I - H_X)_i' D_i', (10) the Wald statistic, (11) the Satterthwaite degrees of freedom with
  p_i = (I - H_X)_i' A_i W_i R''_i M c, (12) the AHT F approximation, (13) the AHT degrees of freedom with
  p_si = (I - H_X)_i' A_i W_i R''_i M C g_s and g_s the columns of G^{-1/2}, G = C M R''' W Phi W R'' M C'.
  Here W = I and Phi = I (the identity working model), so D_i = I and G = C M C'.

Conventions that are mine, not the specification's (each is a place a second programmer could differ)
  * The "state-clustered standard error" is the CR1 form estimator.Fit uses (read as text, not imported):
    factor G/(G-1) * (N-1)/(N-K), K the number of regressors (fixed effects not counted), scores X~_g' u_g.
    The p-value of B does not depend on the factor (it cancels in t and t*); the bracket's width in standard errors does.
  * The Rademacher matrix v is replications x clusters with columns in the order of the sorted unique cluster labels.
  * The Moore-Penrose inverse square root in Eq. (7) treats eigenvalues at or below 1e-8 times the largest as zero
    (the paper gives the exact-arithmetic definition; any tolerance is a numerical convention).
  * Exact ties are real, not rare: a replication whose v is +1 (or -1) on every cluster rebuilds the data (y* = y, for
    every theta) or its mirror (y* = 2 fitted_R - y, giving t* = -t), so |t*| = |t| in exact arithmetic; with 6 to 9 clusters such rows are a few
    percent of 199 or 999 draws. "At least" counts them, so a replication within TIE = 1e-9 of the data's statistic
    (relative, or absolute when the statistic is below 1) counts. Values between 1e-9 and 1e-6 of it are "near ties"
    whose side rounding could decide; the comparison tests skip those and count the skips.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

ALPHA = 0.10
BRACKET = (10, 20, 40, 80, 160, 320, 640)
TOL = 0.0005
EIGEN_TOL = 1e-8
TIE = 1e-9


class ReferenceFailure(Exception):
    pass


# ---- the design, the long way --------------------------------------------------------------------------------------
def dummies(groups) -> np.ndarray:
    """One indicator column per level of every grouping (collinear across groupings; handled by pinv/lstsq)."""
    cols = []
    for g in groups:
        levels = sorted(set(np.asarray(g).tolist()))
        for lev in levels:
            cols.append((np.asarray(g) == lev).astype(float))
    return np.column_stack(cols)


def cluster_lists(cluster) -> list[np.ndarray]:
    """Row indices of each cluster, clusters in sorted label order (the column order of v)."""
    cluster = np.asarray(cluster)
    return [np.flatnonzero(cluster == lab) for lab in sorted(set(cluster.tolist()))]


class Design:
    """y-independent pieces: Z = [X, D], the beta rows of pinv(Z), the hat matrix, X with the dummies partialled out."""

    def __init__(self, X, groups, cluster):
        self.X = np.asarray(X, dtype=float)
        self.N, self.K = self.X.shape
        self.D = dummies(groups)
        self.Z = np.column_stack([self.X, self.D])
        self.clusters = cluster_lists(cluster)
        self.G = len(self.clusters)
        # X~ = (I - H_D) X: the residual of each regressor on all the dummies
        self.Xt = self.X - self.D @ np.linalg.lstsq(self.D, self.X, rcond=None)[0]
        sv = np.linalg.svd(self.Xt, compute_uv=False)
        sv0 = np.linalg.svd(self.X, compute_uv=False)
        if not np.all(np.isfinite(sv)) or sv[0] <= 1e-8 * sv0[0] or sv[-1] <= 1e-8 * sv[0]:
            raise ReferenceFailure("rank_deficient")
        Zp = np.linalg.pinv(self.Z, rcond=1e-10)
        self.L = Zp[: self.K]                       # beta-hat = L @ y (unique because beta is identified)
        self.H = self.Z @ Zp                        # H_X of the FULL model, dummies included
        self.IH = np.eye(self.N) - self.H
        self.Minv = np.linalg.inv(self.Xt.T @ self.Xt)   # M_{R''} in the paper's notation
        self.factor = (self.G / (self.G - 1)) * ((self.N - 1) / (self.N - self.K))

    # unrestricted least squares, the long way
    def fit(self, y):
        y = np.asarray(y, dtype=float)
        if not np.all(np.isfinite(y)):
            raise ReferenceFailure("non_finite_outcome")
        b = self.L @ y
        u = self.IH @ y
        return b, u

    def fit_by_lstsq(self, y):
        """Literal LSDV by lstsq, used to check the pinv shortcut above on a few replications."""
        coef = np.linalg.lstsq(self.Z, y, rcond=None)[0]
        return coef[: self.K], y - self.Z @ coef

    def cr1(self, u) -> np.ndarray:
        """State-clustered (CR1) variance of beta-hat: factor * sum_g (L_g u_g)(L_g u_g)'."""
        V = np.zeros((self.K, self.K))
        for idx in self.clusters:
            s = self.L[:, idx] @ u[idx]
            V += np.outer(s, s)
        return self.factor * V

    def restricted_fit(self, y, R, r):
        """Least squares of y on [X, D] subject to R beta = r (fixed effects re-estimated). Returns fitted, residuals.

        R beta = r is solved by substitution: beta = beta0 + N gamma, beta0 any particular solution, N a basis of null(R).
        """
        R = np.atleast_2d(np.asarray(R, dtype=float))
        r = np.atleast_1d(np.asarray(r, dtype=float))
        beta0 = np.linalg.lstsq(R, r, rcond=None)[0]
        _, s, vt = np.linalg.svd(R)
        rank = int((s > 1e-12 * s[0]).sum())
        Nb = vt[rank:].T                              # K x (K - rank)
        Zr = np.column_stack([self.X @ Nb, self.D])
        coef = np.linalg.lstsq(Zr, y - self.X @ beta0, rcond=None)[0]
        fitted = self.X @ beta0 + Zr @ coef
        return fitted, y - fitted


# ---- candidate B ---------------------------------------------------------------------------------------------------
def b_tstar(des: Design, y, c, theta, v) -> tuple[np.ndarray, float]:
    """Every replication's bootstrap t at theta, and the data's t. One full (pinv) refit per replication, in a loop."""
    c = np.asarray(c, dtype=float)
    b, u = des.fit(y)
    se = float(np.sqrt(c @ des.cr1(u) @ c))
    if not np.isfinite(se) or se <= 0:
        raise ReferenceFailure("non_finite_or_zero_standard_error")
    t_data = (c @ b - theta) / se
    fitted_R, u_R = des.restricted_fit(np.asarray(y, float), c[None, :], [theta])
    out = np.empty(v.shape[0])
    for rep in range(v.shape[0]):
        w = np.empty(des.N)
        for g, idx in enumerate(des.clusters):
            w[idx] = v[rep, g]
        ystar = fitted_R + w * u_R
        bs, us = des.fit(ystar)
        ses = float(np.sqrt(c @ des.cr1(us) @ c))
        out[rep] = (c @ bs - theta) / ses if ses > 0 else np.nan
    return out, float(t_data)


def b_pvalue(des, y, c, theta, v) -> dict:
    ts, t = b_tstar(des, y, c, theta, v)
    if not np.all(np.isfinite(ts)):
        raise ReferenceFailure("non_finite_bootstrap_replication")
    a, d = np.abs(ts), abs(t)
    scale = max(d, 1.0)                     # absolute near 0: at theta = est the data's t is rounding noise
    gap = np.abs(a - d)
    near_tie = bool(np.any((gap > TIE * scale) & (gap <= 1e-6 * scale)))   # close, but not counted as a tie: ambiguous
    p = float(np.mean(a >= d - TIE * scale))
    return {"p": p, "t": t, "tstar": ts, "near_tie": near_tie}


def wald(bsel, Vsel) -> float:
    return float(bsel @ np.linalg.solve(Vsel, bsel))


def b_early_p(des, y, pre, v) -> dict:
    """Null-imposed bootstrap of the Wald statistic on the early coefficients (R beta = 0 imposed)."""
    pre = list(pre)
    q = len(pre)
    b, u = des.fit(y)
    V = des.cr1(u)
    W = wald(b[pre], V[np.ix_(pre, pre)])
    R = np.zeros((q, des.K))
    for j, k in enumerate(pre):
        R[j, k] = 1.0
    fitted_R, u_R = des.restricted_fit(np.asarray(y, float), R, np.zeros(q))
    Ws = np.empty(v.shape[0])
    for rep in range(v.shape[0]):
        w = np.empty(des.N)
        for g, idx in enumerate(des.clusters):
            w[idx] = v[rep, g]
        bs, us = des.fit(fitted_R + w * u_R)
        Vs = des.cr1(us)
        Ws[rep] = wald(bs[pre], Vs[np.ix_(pre, pre)])
    scale = max(abs(W), 1.0)
    gap = np.abs(Ws - W)
    near_tie = bool(np.any((gap > TIE * scale) & (gap <= 1e-6 * scale)))
    return {"p": float(np.mean(Ws >= W - TIE * scale)), "W": W, "Wstar": Ws, "near_tie": near_tie}


def b_search(pfun, est, se, sign) -> tuple[float, str]:
    """The doubling bracket then bisection (E3.2), my reading:
    walk 10, 20, ..., 640 se from the estimate; the first point with p < 0.10 is the crossing. If p rises between two
    successive bracket points before that (p not monotone along the bracket), the side is "search incomplete"; no
    crossing by 640 is "search incomplete". Bisect between the last bracket point with p >= 0.10 (the estimate itself
    when the crossing is at 10 se) and the crossing until they are at most TOL apart; return the midpoint."""
    inner, p_prev = est, 1.0
    for k in BRACKET:
        theta = est + sign * k * se
        p = pfun(theta)
        if p < ALPHA:
            lo_, hi_ = inner, theta                        # lo_ has p >= 0.10, hi_ has p < 0.10
            while abs(hi_ - lo_) > TOL:
                mid = 0.5 * (lo_ + hi_)
                if pfun(mid) >= ALPHA:
                    lo_ = mid
                else:
                    hi_ = mid
            return 0.5 * (lo_ + hi_), "bounded"
        if p > p_prev:
            return np.nan, "search incomplete"
        inner, p_prev = theta, p
    return np.nan, "search incomplete"


# ---- candidate C: CR2, Satterthwaite, AHT --------------------------------------------------------------------------
def mp_inverse_sqrt(B, tol=EIGEN_TOL) -> np.ndarray:
    """Symmetric square root of the Moore-Penrose inverse of a symmetric matrix (Eq. 7's B_i^{+1/2})."""
    B = 0.5 * (B + B.T)
    lam, Q = np.linalg.eigh(B)
    keep = lam > tol * lam.max()
    out = np.zeros_like(B)
    for j in range(len(lam)):
        if keep[j]:
            out += np.outer(Q[:, j], Q[:, j]) / np.sqrt(lam[j])
    return out


class CR2:
    """Eq. (4), (7), (8) with W = Phi = I on the full model (H_X includes every dummy), then (10)-(13)."""

    def __init__(self, des: Design, tol=EIGEN_TOL):
        self.des = des
        self.A = []
        for idx in des.clusters:
            rows = des.IH[idx, :]                   # (I - H_X)_i, n_i x N
            Bi = rows @ rows.T                      # Eq. (8) with D_i = I, Phi = I
            self.A.append(mp_inverse_sqrt(Bi, tol))  # Eq. (7) with D_i = I

    def vcov(self, u) -> np.ndarray:
        d = self.des
        mid = np.zeros((d.K, d.K))
        for idx, Ai in zip(d.clusters, self.A):
            s = d.Xt[idx].T @ Ai @ u[idx]
            mid += np.outer(s, s)
        return d.Minv @ mid @ d.Minv

    def p_vectors(self, cvec) -> list[np.ndarray]:
        """p_i = (I - H_X)_i' A_i R''_i M c, each an N-vector (Eq. 11's definition)."""
        d = self.des
        out = []
        for idx, Ai in zip(d.clusters, self.A):
            out.append(d.IH[idx, :].T @ (Ai @ (d.Xt[idx] @ (d.Minv @ cvec))))
        return out

    def satterthwaite(self, c) -> float:
        P = self.p_vectors(np.asarray(c, float))
        num = sum(float(p @ p) for p in P) ** 2
        den = 0.0
        for pi in P:
            for pj in P:
                den += float(pi @ pj) ** 2
        return num / den

    def aht_p(self, pre) -> list[list[np.ndarray]]:
        """P[s][i] = p_si = (I - H_X)_i' A_i R''_i M C g_s, g_s the columns of G^{-1/2}, G = C M C' (Sec. 3.2)."""
        d = self.des
        q = len(pre)
        Cm = np.zeros((q, d.K))
        for j, k in enumerate(pre):
            Cm[j, k] = 1.0
        Gm = Cm @ d.Minv @ Cm.T
        lam, Q = np.linalg.eigh(Gm)
        Gmh = Q @ np.diag(lam ** -0.5) @ Q.T        # G^{-1/2}, symmetric
        return [self.p_vectors(Cm.T @ Gmh[:, s]) for s in range(q)]

    def eta(self, pre) -> float:
        """Eq. (13) with Phi = I."""
        d = self.des
        q = len(pre)
        P = self.aht_p(pre)
        m = d.G
        den = 0.0
        for s in range(q):
            for t in range(q):
                for i in range(m):
                    for j in range(m):
                        den += (P[s][i] @ P[t][j]) * (P[t][i] @ P[s][j]) + (P[s][i] @ P[s][j]) * (P[t][i] @ P[t][j])
        return q * (q + 1) / den

    def t_pvalue(self, est, se, theta, nu) -> float:
        return float(2 * stats.t.sf(abs(est - theta) / se, nu))

    def aht_pvalue(self, b, V, pre, eta) -> dict:
        q = len(pre)
        Q = wald(b[list(pre)], V[np.ix_(list(pre), list(pre))])
        F = (eta - q + 1) / (eta * q) * Q
        return {"Q": Q, "F": F, "p": float(stats.f.sf(F, q, eta - q + 1))}


def c_all(des: Design, y, c, pre, truth) -> dict:
    cr2 = CR2(des)
    b, u = des.fit(y)
    V = cr2.vcov(u)
    c = np.asarray(c, float)
    est, se = float(c @ b), float(np.sqrt(c @ V @ c))
    nu = cr2.satterthwaite(c)
    eta = cr2.eta(pre)
    crit = float(stats.t.ppf(1 - ALPHA / 2, nu))
    aht = cr2.aht_pvalue(b, V, pre, eta)
    p_truth = cr2.t_pvalue(est, se, truth, nu)
    return {"b": b, "u": u, "V": V, "est": est, "se": se, "nu": nu, "eta": eta, "crit": crit,
            "lo": est - crit * se, "hi": est + crit * se, "p_truth": p_truth, "covered": p_truth >= ALPHA,
            "aht": aht, "early_rejected": aht["p"] < ALPHA, "cr2": cr2}
