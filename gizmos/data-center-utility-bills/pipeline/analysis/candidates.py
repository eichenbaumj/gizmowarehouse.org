#!/usr/bin/env python3
"""Step E's three candidate inference procedures for the headline number, on one assembled design.

The specification is docs/gate1/step-e-rules-2026-11-18.md (D-95), with docs/DECISIONS.md D-59 rule 4.1 (the candidates)
and D-61 section 7.2 as the rules file amends it. Reads no price and no outcome: a candidate is handed an outcome vector
y (made up by inference_comparison.py) and the true value of the headline number for that outcome.

Each candidate returns, for one dataset, a `result` dict:
    estimate          the headline number (mean of event years 2 and 3)
    covered           one test at the true value (E3.1): True if its p-value is 0.10 or more; None if the dataset failed
    early_rejected    the early-years test (event years -6, -5, -4) rejects at 0.10; None if the dataset failed
    lo, hi            the 90% range's two endpoints (NaN on a side that is not bounded)
    lo_state, hi_state  each side's end state: "bounded", "search incomplete" or "numerical failure" (E3.2; three states,
                      "unbounded" is never assigned)
    width             hi - lo; infinite where a side is incomplete or failed (E3.3)
    failure           None, or {"cause", "where", "detail"} (E4.1)
    miss, reject      what the cells count: a failed dataset is a miss AND a rejection (E4.1), reported apart (E4.3)
    power_detects     on the same dataset with D-38's ramp to 5% planted on every host: the test of the value zero
                      rejects at 0.10 with the estimate above zero (for A, the range lies above zero). A failure of that
                      computation counts as no detection and is recorded in `power_failure`; it does not fail the flat
                      dataset (the planted outcome is a different outcome).

A  the bootstrap as built: estimator.Fit.summary unchanged (wild cluster bootstrap by state, unrestricted residuals,
   Rademacher, 999 replications, bootstrap-t, equal-tailed 90%), with its failure handling (E4.4). Coverage at the true
   value is whether the range contains it, which for an equal-tailed bootstrap-t range is the test at that value (E3.1).
B  the null-imposed wild cluster bootstrap with test inversion (D-59 rule 4.1 B; E3.1, E3.2). Exact and vectorized: see
   the class docstring for the identities. The same Rademacher draws for every hypothesized value in a dataset.
C  CR2 with the Satterthwaite t interval and the approximate Hotelling test (D-59 rule 4.1 C), formulas from
   Pustejovsky and Tipton as opened in step E; the version and equation numbers are recorded beside each formula below.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

from pipeline.analysis import estimator
from pipeline.analysis import power_simulation as ps

LEVEL = 0.90
ALPHA = 0.10                                        # covered if p >= 0.10 (E3.1); the early-years test fails below 0.10
BOOT = ps.BOOT                                      # 999 replications (D-59 rule 4.1)
BRACKET = (10, 20, 40, 80, 160, 320, 640)           # clustered standard errors from the estimate (E3.2; D-61 7.2)
TOLERANCE = 0.0005                                  # bisection to 0.05% of price, in log points (D-58 4.1; E3.2)
PLANTED_POWER = float(np.log1p(0.05))               # D-38's ramp to 5% on every host (E2.4: power at a planted 5%)
CR2_EIGEN_TOLERANCE = 1e-8                          # eigenvalues of B_i at or below this times the largest are taken as zero
TIE = 1e-9                                          # B: a replication whose statistic equals the data's counts as "at least"
#   The replication whose weights are all +1 (or all -1) rebuilds the data exactly, so its |t*| equals the data's |t| in
#   exact arithmetic; rounding must not decide whether it counts. "At least" is read with a relative tolerance of 1e-9.

BOUNDED, INCOMPLETE, FAILED = "bounded", "search incomplete", "numerical failure"
END_STATES = (BOUNDED, INCOMPLETE, FAILED)          # "unbounded" is never assigned (E3.2; D-95 Q-b)
CANDIDATES = ("A", "B", "C")

# Failure causes (E4.1, E4.3). The first five are estimator's, shared with the job-U and simulation readings.
RANK_DEFICIENT = estimator.RANK_DEFICIENT
NON_FINITE_STANDARD_ERROR = estimator.NON_FINITE_STANDARD_ERROR
SINGULAR_WALD_VARIANCE = estimator.SINGULAR_WALD_VARIANCE
NON_FINITE_BOOTSTRAP_T = estimator.NON_FINITE_BOOTSTRAP_T
NON_FINITE_BOOTSTRAP_WALD = estimator.NON_FINITE_BOOTSTRAP_WALD
NON_FINITE_OUTCOME = "non_finite_outcome"
SINGULAR_RESTRICTION = "singular_early_years_restriction"          # B: the restricted fit for the early-years test
NON_FINITE_ADJUSTMENT = "non_finite_cr2_adjustment"                # C: B_i or its pseudo-inverse square root
UNDEFINED_DEGREES_OF_FREEDOM = "undefined_or_non_finite_degrees_of_freedom"   # C: nu or eta - q + 1 not finite and positive
FAILURE_CAUSES = (RANK_DEFICIENT, NON_FINITE_STANDARD_ERROR, SINGULAR_WALD_VARIANCE, NON_FINITE_BOOTSTRAP_T,
                  NON_FINITE_BOOTSTRAP_WALD, NON_FINITE_OUTCOME, SINGULAR_RESTRICTION, NON_FINITE_ADJUSTMENT,
                  UNDEFINED_DEGREES_OF_FREEDOM)
WHERE = ("design", "fit", "test_at_the_true_value", "early_years_test", "range", "endpoint_lower", "endpoint_upper")


class Failed(Exception):
    """A numerical failure inside a candidate's computation (E4.1). Carries the cause code and where it arose."""

    def __init__(self, cause: str, where: str, detail: str = ""):
        super().__init__(f"{cause} at {where}: {detail}")
        self.cause, self.where, self.detail = cause, where, detail

    def record(self) -> dict:
        return {"cause": self.cause, "where": self.where, "detail": self.detail}


class Problem:
    """What does not change from one made-up dataset to the next: the regressors, the fixed effects, the clusters, the
    headline combination, the early-years columns and the planted ramp (inference_check.fixed_parts).

    X        (N, K) regressors before the fixed effects are removed; the event-time columns first (ps.assemble's order)
    groups   list of (N,) fixed-effect codes, utilities first (estimator.Projection)
    cluster  (N,) cluster labels (states). Clusters are numbered in SORTED label order (np.unique), and every bootstrap
             weight matrix v has one column per cluster in that order
    ramp     (N,) the planted path for the power reading: on host rows, D-38's ramp (0 before event year 0, a third a year,
             1 from event year 2); 0 on comparison rows. None: no power reading is made
    combo    (K,) the headline as a combination of the K coefficients; default ps.headline_combo(K), the mean of event
             years 2 and 3 with zeros on every control column
    pre      the column indices of the three early coefficients (event years -6, -5, -4); default ps.PRE_IDX
    """

    def __init__(self, X, groups, cluster, ramp=None, projection=None, combo=None, pre=None):
        self.X = np.asarray(X, dtype=float)
        self.N, self.K = self.X.shape
        self.groups = groups
        self.cluster = np.asarray(cluster)
        self.ramp = None if ramp is None else np.asarray(ramp, dtype=float)
        self.projection = projection if projection is not None else estimator.Projection(groups)
        self.combo = ps.headline_combo(self.K) if combo is None else np.asarray(combo, dtype=float)
        self.pre = list(ps.PRE_IDX) if pre is None else list(pre)
        self.codes = np.unique(self.cluster, return_inverse=True)[1]
        self.G = int(self.codes.max()) + 1

    @classmethod
    def from_fixed_parts(cls, f: dict) -> "Problem":
        return cls(f["X"], f["groups"], f["cluster"], f.get("ramp"), f.get("projection"), f.get("combo"))


def result(candidate: str, *, estimate=np.nan, covered=None, early_rejected=None, lo=np.nan, hi=np.nan,
           lo_state=FAILED, hi_state=FAILED, failure=None, power_detects=False, power_failure=None, **extra) -> dict:
    """One dataset's reading for one candidate. A failed dataset (failure not None) is a miss and a rejection (E4.1)."""
    if failure is not None:
        covered, early_rejected = None, None
        lo_state = lo_state if lo_state != BOUNDED else FAILED
        hi_state = hi_state if hi_state != BOUNDED else FAILED
    width = float(hi - lo) if (lo_state == BOUNDED and hi_state == BOUNDED and failure is None) else float("inf")
    out = {"candidate": candidate, "estimate": float(estimate), "covered": covered, "early_rejected": early_rejected,
           "lo": float(lo) if lo_state == BOUNDED else float("nan"), "hi": float(hi) if hi_state == BOUNDED else float("nan"),
           "lo_state": lo_state, "hi_state": hi_state, "width": width, "failure": failure,
           "miss": bool(failure is not None or not covered), "reject": bool(failure is not None or early_rejected),
           "power_detects": bool(power_detects) if power_failure is None else False, "power_failure": power_failure}
    out.update(extra)
    return out


def failed_result(candidate: str, f: Failed, estimate=np.nan, power_failure=None) -> dict:
    return result(candidate, estimate=estimate, failure=f.record(), power_failure=power_failure or f.record())


def _check_outcome(y) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    if not np.isfinite(y).all():
        raise Failed(NON_FINITE_OUTCOME, "fit", "the outcome has a value that is not finite")
    return y


# ================================================================================================================
# A. The bootstrap as built
# ================================================================================================================

class CandidateA:
    """estimator.Fit.summary as it now is (D-59 rule 4.1 A), with the failure handling of E4.4 already in it."""

    name = "A"

    def __init__(self, problem: Problem, boot: int = BOOT):
        self.p, self.boot = problem, boot

    def run(self, y, truth: float, v: np.ndarray, planted: float | None = PLANTED_POWER) -> dict:
        """y (N,) outcome; truth the headline's true value; v (boot, G) Rademacher weights, columns in sorted cluster-label
        order (Problem); planted the size of the ramp for the power reading (None: no power reading). The planted outcome
        y + planted * ramp is read with the SAME v."""
        p = self.p
        try:
            y = _check_outcome(y)
            paths = p.ramp[:, None] if (p.ramp is not None and planted is not None) else None
            fit = estimator.Fit(y, p.X, p.groups, p.cluster, paths, projection=p.projection)
        except estimator.RankDeficient as e:
            return failed_result("A", Failed(RANK_DEFICIENT, "fit", str(e)))
        except Failed as f:
            return failed_result("A", f)
        z = fit.summary(v, p.combo, p.pre)
        power, power_failure = False, None
        if paths is not None:
            zp = fit.summary(v, p.combo, None, path=0, tau=planted)
            if zp["numerical_failure"]:
                power_failure = {"cause": zp["numerical_failure"], "where": "range", "detail": "planted 5% ramp"}
            else:
                power = bool(zp["lo"] > 0)
        if z["numerical_failure"]:
            where = "fit" if z["analytic_failure"] else "range"
            return result("A", estimate=z["est"], failure={"cause": z["numerical_failure"], "where": where, "detail": ""},
                          power_detects=power, power_failure=power_failure)
        lo, hi = z["lo"], z["hi"]
        return result("A", estimate=z["est"], covered=bool(lo <= truth <= hi), early_rejected=bool(z["pre_p_bootstrap"] < ALPHA),
                      lo=lo, hi=hi, lo_state=BOUNDED, hi_state=BOUNDED, power_detects=power, power_failure=power_failure)


# ================================================================================================================
# B. The null-imposed wild cluster bootstrap with test inversion
# ================================================================================================================

class _Parts:
    """The pieces of the full wild cluster bootstrap that a residual-like vector u gives (estimator.py's identities):
        S[h]       = X~_h' u_h                                   (G x K) cluster scores
        Tc[g, h]   = (X~ m)_g' [M_D(u 1_h)]_g                    (G x G) T[g, h, :] contracted with m = (X~'X~)^-1 c
        Tp[g, h, j]= (X~ Mp_j)_g' [M_D(u 1_h)]_g                 (G x G x 3) T contracted with the early columns of the inverse
    Every one is linear in u, so a sum of vectors has the sum of their parts (`combine`)."""

    __slots__ = ("S", "Tc", "Tp")

    def __init__(self, S, Tc, Tp):
        self.S, self.Tc, self.Tp = S, Tc, Tp

    @staticmethod
    def combine(terms) -> "_Parts":
        S = Tc = Tp = 0.0
        for a, x in terms:
            S, Tc, Tp = S + a * x.S, Tc + a * x.Tc, Tp + a * x.Tp
        return _Parts(S, Tc, Tp)


class CandidateB:
    """Null-imposed wild cluster bootstrap with test inversion (D-59 rule 4.1 B; E3.1, E3.2; D-61 7.2 as amended).

    For a hypothesized value theta of the headline number c'b, the fit is redone with c'b = theta imposed (fixed effects
    re-estimated), bootstrap outcomes y* = fitted_R + v_g * u_R (Rademacher by state, the restricted residuals), each refit
    without the restriction, t* = (c'b* - theta) / se*(y*), p = share of |t*| >= |t(theta)|, t(theta) = (est - theta) / se.

    Exact identities used (with X~, y~ the regressors and outcome after the fixed effects are removed, m = (X~'X~)^-1 c,
    kappa = 1 / c'm, u the unrestricted residuals, delta = est - theta):
      the restricted residuals are u_R = u + delta * w, with w = kappa X~ m (a design quantity);
      the projected bootstrap outcome is X~ b_R + M_D(u_R * v), so b* - b_R = (X~'X~)^-1 sum_h v_h X~_h' u_R,h, and the refit's
      cluster scores are sum_h v_h T_R[g, h] - A_g (b* - b_R), exactly as estimator.Fit.bootstrap (T_R built from u_R);
      everything is linear in u_R, so t*'s numerator and the vector whose squares give se* are (thing for u) + delta *
      (thing for w). One projection of the G columns u * 1_h per outcome gives every replication at every theta.
    The early-years test imposes R b = 0 (R selects the three early coefficients): the restricted fit is
    b_R = b - M R' (R M R')^-1 R b, so u_R = u + W_e (R b) with W_e = X~ M R' (R M R')^-1 (a design quantity), M = (X~'X~)^-1;
    each refit's Wald statistic (its own CR1 variance) is compared with the data's.
    The same Rademacher matrix v is used at every theta of a dataset and for its early-years test (rule 4.1 B).
    """

    name = "B"

    def __init__(self, problem: Problem, boot: int = BOOT):
        self.p, self.boot = problem, boot
        self.design_failure: Failed | None = None
        p = problem
        try:
            Xt = p.projection(p.X)
            estimator.check_rank(Xt, p.X)
        except estimator.RankDeficient as e:
            self.design_failure = Failed(RANK_DEFICIENT, "fit", str(e))
            return
        self.Xt = Xt
        self.M = np.linalg.inv(Xt.T @ Xt)
        self.C = estimator.indicator(p.codes)
        self.Ag = np.stack([Xt[p.codes == g].T @ Xt[p.codes == g] for g in range(p.G)])
        self.factor = (p.G / (p.G - 1)) * ((p.N - 1) / (p.N - p.K))     # the same CR1 factor as estimator.Fit
        self.mc = self.M @ p.combo
        cmc = float(p.combo @ self.mc)
        self.xm = Xt @ self.mc
        self.Mp = self.M[:, p.pre]
        self.xp = Xt @ self.Mp
        self.Agm = self.Ag @ self.mc                                        # G x K
        self.AgMp = self.Ag @ self.Mp                                      # G x K x 3
        self.w_parts = self.parts(Xt @ self.mc / cmc)                      # the headline restriction's direction
        try:
            self.RMRinv = np.linalg.inv(self.M[np.ix_(p.pre, p.pre)])
        except np.linalg.LinAlgError:
            self.RMRinv = None
        self.we_parts = None
        if self.RMRinv is not None:
            We = self.xp @ self.RMRinv                                     # N x 3: the early restriction's directions
            self.we_parts = [self.parts(We[:, j]) for j in range(We.shape[1])]
        self.ramp_u = self.ramp_b = self.ramp_parts = None
        if p.ramp is not None:
            rt = p.projection(p.ramp)
            self.ramp_b = self.M @ (Xt.T @ rt)
            self.ramp_u = rt - Xt @ self.ramp_b
            self.ramp_parts = self.parts(self.ramp_u)

    def _require(self):
        """Every public method fails in words on a design that failed when the candidate was built."""
        if self.design_failure is not None:
            raise self.design_failure

    # ---- the pieces ------------------------------------------------------------------------------------------
    def parts(self, u: np.ndarray) -> _Parts:
        self._require()
        p = self.p
        Wm = p.projection(self.C.multiply(u[:, None]).toarray())                     # N x G: M_D(u 1_h)
        S = np.asarray(self.C.T @ (self.Xt * u[:, None]))
        Tc = np.asarray(self.C.T @ (self.xm[:, None] * Wm))
        Tp = np.asarray(self.C.T @ (self.xp[:, :, None] * Wm[:, None, :]).reshape(p.N, -1)).reshape(p.G, len(p.pre), p.G)
        return _Parts(S, Tc, Tp.transpose(0, 2, 1))

    def unrestricted(self, y: np.ndarray):
        self._require()
        yt = self.p.projection(y)
        b = self.M @ (self.Xt.T @ yt)
        u = yt - self.Xt @ b
        return b, u

    def _boot_headline(self, v: np.ndarray, x: _Parts):
        """(numerator, the G-vector whose squares give se*^2 / factor) for every replication, from the parts of a vector."""
        num = v @ (x.S @ self.mc)
        shift = v @ (x.S @ self.M)
        return num, v @ x.Tc.T - shift @ self.Agm.T

    def session(self, y: np.ndarray, v: np.ndarray) -> "_Session":
        """Everything one dataset needs for any hypothesized value: one set of draws v (boot, G; columns in sorted
        cluster-label order), fixed for the dataset. Raises Failed on a design that failed when the candidate was built."""
        self._require()
        b, u = self.unrestricted(y)
        return _Session(self, b, u, self.parts(u), v)

    def run(self, y, truth: float, v: np.ndarray, planted: float | None = PLANTED_POWER) -> dict:
        """As CandidateA.run: v (boot, G), columns in sorted cluster-label order, used for every hypothesized value, for the
        early-years test and for the planted outcome alike."""
        if self.design_failure is not None:
            return failed_result("B", self.design_failure)
        try:
            y = _check_outcome(y)
        except Failed as f:
            return failed_result("B", f)
        s = self.session(y, v)
        power, power_failure = self._power(s, planted)
        try:
            s.check_standard_error()
            covered = s.p_value(truth, "test_at_the_true_value") >= ALPHA          # E3.1: ONE test at the true value
            early = s.early_years_p() < ALPHA
            lo, lo_state = s.endpoint(-1)
            hi, hi_state = s.endpoint(+1)
        except Failed as f:                     # any failure fails the dataset; both sides read as failed (E4.1, E3.3)
            return result("B", estimate=s.est, failure=f.record(), power_detects=power, power_failure=power_failure)
        return result("B", estimate=s.est, covered=bool(covered), early_rejected=bool(early), lo=lo, hi=hi,
                      lo_state=lo_state, hi_state=hi_state, power_detects=power, power_failure=power_failure)

    def _power(self, s: "_Session", planted):
        if planted is None or self.ramp_parts is None:
            return False, None
        sp = _Session(self, s.b + planted * self.ramp_b, s.u + planted * self.ramp_u,
                      _Parts.combine([(1.0, s.u_parts), (planted, self.ramp_parts)]), s.v)
        try:
            sp.check_standard_error()
            return bool(sp.est > 0 and sp.p_value(0.0, "range") < ALPHA), None
        except Failed as f:
            return False, f.record()


class _Session:
    """One dataset under candidate B: the unrestricted fit, the parts of its residuals, and the one draw matrix v."""

    def __init__(self, cand: CandidateB, b, u, u_parts: _Parts, v: np.ndarray):
        self.c, self.b, self.u, self.u_parts, self.v = cand, b, u, u_parts, np.asarray(v, dtype=float)
        p = cand.p
        self.est = float(p.combo @ b)
        S = u_parts.S
        self.V = cand.factor * cand.M @ (S.T @ S) @ cand.M                  # CR1, as estimator.Fit.vcov
        self.se = float(np.sqrt(max(float(p.combo @ self.V @ p.combo), 0.0)))
        self.num_u, self.x_u = cand._boot_headline(self.v, u_parts)
        self.num_w, self.x_w = cand._boot_headline(self.v, cand.w_parts)
        self.evaluated: list = []                                             # (theta, p) in the order computed

    def check_standard_error(self):
        if not (np.isfinite(self.est) and np.isfinite(self.se) and self.se > 0):
            raise Failed(NON_FINITE_STANDARD_ERROR, "fit", "the clustered standard error is not finite and positive")

    def tstar(self, theta: float) -> np.ndarray:
        """Every replication's bootstrap t at the hypothesized value theta (the same v for every theta)."""
        delta = self.est - theta
        num = self.num_u + delta * self.num_w
        x = self.x_u + delta * self.x_w
        se = np.sqrt(self.c.factor * (x ** 2).sum(1))
        with np.errstate(divide="ignore", invalid="ignore"):
            return num / np.where(se > 0, se, np.nan)

    def p_value(self, theta: float, where: str) -> float:
        t = self.tstar(theta)
        if not np.isfinite(t).all():                                            # E4.1: never dropped, never quantiled around
            raise Failed(NON_FINITE_BOOTSTRAP_T, where, f"{int((~np.isfinite(t)).sum())} of {len(t)} replications at {theta!r}")
        p = float(np.mean(at_least(np.abs(t), abs((self.est - theta) / self.se))))
        self.evaluated.append((float(theta), p))
        return p

    def early_years_p(self) -> float:
        """Null-imposed bootstrap p-value of the Wald statistic on the three early coefficients (rule 4.1 B)."""
        c, pre = self.c, self.c.p.pre
        if c.we_parts is None:
            raise Failed(SINGULAR_RESTRICTION, "early_years_test", "the early coefficients' block of the inverse is singular")
        bp = self.b[pre]
        try:
            wald = float(bp @ np.linalg.solve(self.V[np.ix_(pre, pre)], bp))
        except np.linalg.LinAlgError:
            wald = float("nan")
        if not np.isfinite(wald):
            raise Failed(SINGULAR_WALD_VARIANCE, "early_years_test", "the data's early-years variance cannot be inverted")
        lam = bp                                                    # u_R = u + W_e (R b)
        x = _Parts.combine([(1.0, self.u_parts)] + [(float(lam[j]), c.we_parts[j]) for j in range(len(lam))])
        shift = self.v @ (x.S @ c.M)
        d = shift[:, pre]
        P = np.einsum("bh,ghj->bgj", self.v, x.Tp) - np.einsum("bk,gkj->bgj", shift, c.AgMp)
        Vb = c.factor * np.einsum("bgi,bgj->bij", P, P)
        try:
            ws = np.einsum("bi,bi->b", d, np.linalg.solve(Vb, d[:, :, None])[:, :, 0])
        except np.linalg.LinAlgError:
            ws = np.array([estimator._solve_or_nan(m, z) for z, m in zip(d, Vb)])
        if not np.isfinite(ws).all():
            raise Failed(NON_FINITE_BOOTSTRAP_WALD, "early_years_test", f"{int((~np.isfinite(ws)).sum())} replications")
        return float(np.mean(at_least(ws, wald)))

    def endpoint(self, sign: int) -> tuple[float, str]:
        """One side of the 90% range by the doubling bracket, then bisection (E3.2). Raises Failed on a numerical failure."""
        where = "endpoint_upper" if sign > 0 else "endpoint_lower"
        return search_side(lambda theta: self.p_value(theta, where), self.est, self.se, sign)


def at_least(stat: np.ndarray, data: float) -> np.ndarray:
    """stat >= data, with exact ties (to a relative TIE) counted as at least: the p-value's numerator."""
    return stat >= data - TIE * max(1.0, abs(data))


def search_side(pfun, est: float, se: float, sign: int, bracket=BRACKET, tol: float = TOLERANCE) -> tuple[float, str]:
    """From the estimate outward the bracket doubles (10, 20, 40, ... 640 clustered standard errors) until the p-value
    falls below 0.10, then bisection to `tol` (E3.2; D-61 7.2). Returns (endpoint, end state).

    bounded            a crossing was found; the endpoint is the midpoint of the final bisection interval, whose ends
                       are no more than `tol` apart (inner end p >= 0.10, outer end p < 0.10)
    search incomplete  no crossing by the last bracket (the 640 cap: E4.2, not a failure), or the p-value rose along the
                       bracket (not monotone); the endpoint is NaN and the side is infinitely wide (E3.3)
    numerical failure  `pfun` raised Failed; it propagates, and the dataset fails (E4.1)
    """
    inner, p_inner = 0.0, 1.0                     # at the estimate itself t = 0, and every |t*| >= 0: p = 1
    for k in bracket:
        d = k * se
        p = pfun(est + sign * d)
        if p > p_inner:
            return float("nan"), INCOMPLETE       # not monotone along the bracket
        if p < ALPHA:
            outer = d
            while outer - inner > tol:
                mid = 0.5 * (inner + outer)
                if pfun(est + sign * mid) >= ALPHA:
                    inner = mid
                else:
                    outer = mid
            return float(est + sign * 0.5 * (inner + outer)), BOUNDED
        inner, p_inner = d, p
    return float("nan"), INCOMPLETE               # the cap: "search incomplete beyond est +/- 640 se", never "unbounded"


# ================================================================================================================
# C. CR2 with small-sample degrees of freedom
# ================================================================================================================
# Source, as opened in step E (2026-11-18): James E. Pustejovsky and Elizabeth Tipton, "Small sample methods for
# cluster-robust variance estimation and hypothesis testing in fixed effects models", arXiv:1601.01981v2 [stat.ME],
# submitted 6 Nov 2022 (title page dated November 8, 2022), https://arxiv.org/pdf/1601.01981v2 (the revision that corrects
# the statement of Theorem 2; published version J. Business & Economic Statistics 36(4), 2018, doi:10.1080/07350015.2016.1247004,
# which was not opened). Equation numbers below are those of v2.
#
# Notation (v2 Section 1.1-1.2): R = the regressors here (event times, degree days, gas-share columns), S = fixed effects
# identified across clusters (the block-by-region-by-year effects), T = within-cluster effects (utility effects); W = I
# (ordinary least squares) and the working model Phi = I (identity), as rule 4.1 C fixes. R.. = X~ (regressors after
# every fixed effect is removed), M_R.. = (X~'X~)^-1, H_X the projection on the full model [R S T].
#   Eq. (4)   V_CR = M_R.. ( sum_i R.._i' W_i A_i e_i e_i' A_i' W_i R.._i ) M_R..        e = the full model's residuals
#   Eq. (8)   B_i  = D_i (I - H_X)_i Phi (I - H_X)_i' D_i'                                  with Phi = I, D_i = I
#   Eq. (7)   A_i  = D_i' B_i^{+1/2} D_i            B_i^{+1/2}: symmetric square root of the Moore-Penrose inverse
#   Sec. 2.2  (I - H_X)_i = (I - H_R..)_i (I - H_S..)(I - H_T): the adjustment is computed on the FULL model, every
#             absorbed effect included (rule 4.1 C: the region-by-year effects and gas-share controls are not nested in states)
#   Eq. (11)  nu_M = (sum_i p_i' Phi p_i)^2 / sum_i sum_j (p_i' Phi p_j)^2,   p_i = (I - H_X)_i' A_i W_i R.._i M_R.. c
#   Eq. (10)  Q = (C b - d)' (C V_CR C')^-1 (C b - d)
#   Sec. 3.2  G = C M_R.. R..' W Phi W R.. M_R.. C' (= C M_R.. C' here); g_1..g_q the columns of G^{-1/2}
#             p_si = (I - H_X)_i' A_i W_i R.._i M_R.. C g_s
#   Eq. (13)  eta_M = q(q+1) / sum_{s,t} sum_{i,j} (p_si' Phi p_tj p_ti' Phi p_sj + p_si' Phi p_sj p_ti' Phi p_tj)
#   Eq. (12)  (eta - q + 1) / (eta q) * Q  ~approx F(q, eta - q + 1)      the approximate Hotelling T^2 (AHT) test
#   Sec. 3.1  for one constraint: Z = c'b / sqrt(c' V_CR c) against t(nu_M) (the Satterthwaite t)
# Eq. (9) and Theorem 2 (absorbing only the within-cluster effects) are NOT used: v2 restates Theorem 2, and the full-model
# form of Eq. (7)-(8) is the one rule 4.1 C names.

def mp_inverse_sqrt(B: np.ndarray, tol: float = CR2_EIGEN_TOLERANCE) -> np.ndarray:
    """B^{+1/2} of Eq. (7): the symmetric square root of the Moore-Penrose inverse of a symmetric matrix.

    Eigenvalues at or below `tol` times the largest are the null space (zero in exact arithmetic; B_i is singular whenever
    a fixed effect is nested in cluster i). Raises Failed if B is not finite.
    """
    if not np.isfinite(B).all():
        raise Failed(NON_FINITE_ADJUSTMENT, "design", "B_i is not finite")
    lam, vec = np.linalg.eigh(0.5 * (B + B.T))
    top = float(lam.max()) if lam.size else 0.0
    if not np.isfinite(lam).all():
        raise Failed(NON_FINITE_ADJUSTMENT, "design", "the eigenvalues of B_i are not finite")
    keep = lam > tol * top if top > 0 else np.zeros_like(lam, dtype=bool)
    inv_sqrt = np.zeros_like(lam)
    inv_sqrt[keep] = 1.0 / np.sqrt(lam[keep])
    return (vec * inv_sqrt) @ vec.T


def satterthwaite(P: np.ndarray) -> float:
    """Eq. (11) with Phi = I: P holds p_1..p_m as columns."""
    gram = P.T @ P
    return float(np.trace(gram) ** 2 / (gram ** 2).sum())


def aht_degrees_of_freedom(P: np.ndarray) -> float:
    """Eq. (13) with Phi = I: P[:, s, i] = p_si (N x q x m)."""
    q = P.shape[1]
    gram = np.einsum("nsi,ntj->sitj", P, P)                                  # gram[s, i, t, j] = p_si' p_tj
    first = np.einsum("sitj,tisj->", gram, gram)                              # p_si'p_tj * p_ti'p_sj
    second = np.einsum("sisj,titj->", gram, gram)                             # p_si'p_sj * p_ti'p_tj
    return float(q * (q + 1) / (first + second))


def symmetric_inverse_sqrt(G: np.ndarray) -> np.ndarray:
    lam, vec = np.linalg.eigh(0.5 * (G + G.T))
    if not (np.isfinite(lam).all() and lam.min() > 0):
        raise Failed(UNDEFINED_DEGREES_OF_FREEDOM, "design", "G = C M C' is not positive definite")
    return (vec / np.sqrt(lam)) @ vec.T


class CandidateC:
    """CR2 (Eq. 4, 7, 8 on the full model, Phi = I, W = I), a Satterthwaite t range (Eq. 11, Sec. 3.1) for the headline,
    and the AHT test (Eq. 10, 12, 13) for the three early coefficients. Everything but the residuals is a design quantity,
    computed once: the adjustment matrices, F_i = A_i X~_i M (so Eq. 4's middle is sum_i (F_i' e_i)(F_i' e_i)'), nu and eta.
    A design-level failure fails every dataset (E4.1)."""

    name = "C"

    def __init__(self, problem: Problem, tol: float = CR2_EIGEN_TOLERANCE):
        self.p = p = problem
        self.design_failure: Failed | None = None
        self.early_failure: Failed | None = None
        try:
            Xt = p.projection(p.X)
            estimator.check_rank(Xt, p.X)
        except estimator.RankDeficient as e:
            self.design_failure = Failed(RANK_DEFICIENT, "fit", str(e))
            return
        self.Xt, self.M = Xt, np.linalg.inv(Xt.T @ Xt)
        self.Cind = estimator.indicator(p.codes)
        q = len(p.pre)
        Cm = np.zeros((q, p.K))
        Cm[np.arange(q), p.pre] = 1.0
        self.Cm = Cm
        try:
            Ginv_half = symmetric_inverse_sqrt(Cm @ self.M @ Cm.T)                  # Sec. 3.2: G^{-1/2} under Phi = W = I
        except Failed as f:
            Ginv_half, self.early_failure = None, Failed(f.cause, "early_years_test", f.detail)
        F = np.zeros((p.N, p.K))
        P_head = np.zeros((p.N, p.G))
        P_early = np.zeros((p.N, q, p.G))
        self.adjustment_rank = []
        try:
            for i in range(p.G):
                idx = np.flatnonzero(p.codes == i)
                E = np.zeros((p.N, len(idx)))
                E[idx, np.arange(len(idx))] = 1.0
                Q = p.projection(E) - Xt @ (self.M @ Xt[idx].T)                  # (I - H_X)[:, i]  (Sec. 2.2 factorization)
                B = Q.T @ Q                                                      # Eq. (8), Phi = I, D_i = I
                A = mp_inverse_sqrt(B, tol)                                      # Eq. (7)
                self.adjustment_rank.append(int(np.linalg.matrix_rank(A)) if A.size else 0)
                Fi = A @ Xt[idx] @ self.M                                        # A_i R.._i M_R..
                F[idx] = Fi
                P_head[:, i] = Q @ (Fi @ p.combo)                                # p_i of Eq. (11)
                if Ginv_half is not None:
                    P_early[:, :, i] = Q @ (Fi @ Cm.T @ Ginv_half)              # p_si of Eq. (13)
        except Failed as f:
            self.design_failure = f
            return
        if not (np.isfinite(F).all() and np.isfinite(P_head).all() and np.isfinite(P_early).all()):
            self.design_failure = Failed(NON_FINITE_ADJUSTMENT, "design", "an adjusted cluster term is not finite")
            return
        self.F = F
        with np.errstate(divide="ignore", invalid="ignore"):
            self.nu = satterthwaite(P_head)
            self.eta = aht_degrees_of_freedom(P_early) if Ginv_half is not None else float("nan")
        if not (np.isfinite(self.nu) and self.nu > 0):
            self.design_failure = Failed(UNDEFINED_DEGREES_OF_FREEDOM, "range", f"Satterthwaite nu = {self.nu!r}")
            return
        if self.early_failure is None and not (np.isfinite(self.eta) and self.eta - q + 1 > 0):
            self.early_failure = Failed(UNDEFINED_DEGREES_OF_FREEDOM, "early_years_test", f"AHT eta = {self.eta!r}")
        self.crit = float(stats.t.ppf((1 + LEVEL) / 2, self.nu))
        self.ramp_u = self.ramp_b = None
        if p.ramp is not None:
            rt = p.projection(p.ramp)
            self.ramp_b = self.M @ (Xt.T @ rt)
            self.ramp_u = rt - Xt @ self.ramp_b

    def _require(self):
        """Every public method fails in words on a design that failed when the candidate was built."""
        if self.design_failure is not None:
            raise self.design_failure

    def vcov(self, u: np.ndarray) -> np.ndarray:
        """Eq. (4) with W = I: M (sum_i X~_i' A_i e_i e_i' A_i X~_i) M = sum_i (F_i' e_i)(F_i' e_i)'."""
        self._require()
        scores = np.asarray(self.Cind.T @ (self.F * u[:, None]))                # G x K: row i is (A_i X~_i M)' e_i
        return scores.T @ scores

    def fit(self, y: np.ndarray):
        self._require()
        yt = self.p.projection(y)
        b = self.M @ (self.Xt.T @ yt)
        return b, yt - self.Xt @ b

    def t_test(self, est: float, se: float, theta: float) -> float:
        """Two-sided p-value of the Satterthwaite t (Sec. 3.1, Eq. 11) at the hypothesized value theta."""
        self._require()
        return float(2.0 * stats.t.sf(abs((est - theta) / se), self.nu))

    def aht(self, b: np.ndarray, V: np.ndarray) -> float:
        """p-value of the AHT test of the three early coefficients being zero (Eq. 10, 12). NaN where eta <= q - 1 (run()
        turns that into a failure through early_failure)."""
        self._require()
        q = len(self.p.pre)
        bc, Vc = self.Cm @ b, self.Cm @ V @ self.Cm.T
        try:
            Q = float(bc @ np.linalg.solve(Vc, bc))
        except np.linalg.LinAlgError:
            Q = float("nan")
        if not np.isfinite(Q):
            raise Failed(SINGULAR_WALD_VARIANCE, "early_years_test", "C V_CR2 C' cannot be inverted")
        Fstat = (self.eta - q + 1) / (self.eta * q) * Q
        return float(stats.f.sf(Fstat, q, self.eta - q + 1))

    def run(self, y, truth: float, v=None, planted: float | None = PLANTED_POWER) -> dict:
        """`v` is accepted and ignored: C draws nothing. The planted outcome y + planted * ramp uses the same design-level
        quantities. A design-level failure of the early-years test (eta <= q - 1) fails every dataset, the planted one too,
        so it is recorded in power_failure, as failed_result records a design-level failure for A and B."""
        if self.design_failure is not None:
            return failed_result("C", self.design_failure)
        try:
            y = _check_outcome(y)
        except Failed as f:
            return failed_result("C", f)
        p = self.p
        b, u = self.fit(y)
        est = float(p.combo @ b)
        power, power_failure = False, None
        if planted is not None and self.ramp_u is not None and self.early_failure is not None:
            power_failure = self.early_failure.record()
        elif planted is not None and self.ramp_u is not None:
            bp = b + planted * self.ramp_b
            Vp = self.vcov(u + planted * self.ramp_u)
            ep, sep = float(p.combo @ bp), float(np.sqrt(max(float(p.combo @ Vp @ p.combo), 0.0)))
            if np.isfinite(sep) and sep > 0 and np.isfinite(ep):
                power = bool(ep > 0 and self.t_test(ep, sep, 0.0) < ALPHA)
            else:
                power_failure = {"cause": NON_FINITE_STANDARD_ERROR, "where": "range", "detail": "planted 5% ramp"}
        try:
            V = self.vcov(u)
            se = float(np.sqrt(max(float(p.combo @ V @ p.combo), 0.0)))
            if not (np.isfinite(est) and np.isfinite(se) and se > 0):
                raise Failed(NON_FINITE_STANDARD_ERROR, "fit", "the CR2 standard error is not finite and positive")
            covered = self.t_test(est, se, truth) >= ALPHA                       # E3.1: one test at the true value
            if self.early_failure is not None:
                raise self.early_failure
            early = self.aht(b, V) < ALPHA
        except Failed as f:
            return result("C", estimate=est, failure=f.record(), power_detects=power, power_failure=power_failure)
        return result("C", estimate=est, covered=bool(covered), early_rejected=bool(early), lo=est - self.crit * se,
                      hi=est + self.crit * se, lo_state=BOUNDED, hi_state=BOUNDED, power_detects=power, power_failure=power_failure)


def prepare(problem: Problem, names=CANDIDATES, boot: int = BOOT) -> dict:
    """The candidates named, each with its design-level precomputation done once."""
    make = {"A": lambda: CandidateA(problem, boot), "B": lambda: CandidateB(problem, boot), "C": lambda: CandidateC(problem)}
    return {n: make[n]() for n in names}
