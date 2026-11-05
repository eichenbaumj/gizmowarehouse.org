"""Inference helpers: Poisson / negative-binomial observed-vs-expected, Wheeler z, bootstrap, chi-square,
Poisson trend slope, leave-one-year-out and split-half."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps


def expected_from_city(core_base: float, city_base: float, city_recent: float) -> float:
    """Expected recent count in the core if it had followed the city's trend from the base period."""
    return core_base * (city_recent / city_base) if city_base else np.nan


def poisson_z(observed: float, expected: float) -> tuple[float, float]:
    if expected <= 0:
        return np.nan, np.nan
    z = (observed - expected) / np.sqrt(expected)
    p = 2 * (1 - sps.norm.cdf(abs(z)))
    return float(z), float(p)


def nb_dispersion(cell_recent: np.ndarray, cell_expected: np.ndarray) -> float:
    """Method-of-moments alpha for NB2 (var = mu + alpha mu^2) from the cell panel."""
    mu = np.asarray(cell_expected, float)
    y = np.asarray(cell_recent, float)
    ok = mu > 0
    num = ((y[ok] - mu[ok]) ** 2 - mu[ok]).sum()
    den = (mu[ok] ** 2).sum()
    return float(max(num / den, 0.0)) if den > 0 else 0.0


def nb_z(observed: float, expected: float, alpha: float) -> tuple[float, float]:
    if expected <= 0:
        return np.nan, np.nan
    var = expected + alpha * expected ** 2
    z = (observed - expected) / np.sqrt(var)
    p = 2 * (1 - sps.norm.cdf(abs(z)))
    return float(z), float(p)


def wheeler_z(current: float, prior: float) -> float:
    """Wheeler (2016) Poisson z for the difference of two counts."""
    return float(2 * (np.sqrt(current) - np.sqrt(prior)))


def rate_ratio_z(a: float, na: float, b: float, nb: float) -> tuple[float, float]:
    """z for log rate ratio between two Poisson rates (a/na vs b/nb)."""
    if a <= 0 or b <= 0:
        return np.nan, np.nan
    lr = np.log((a / na) / (b / nb))
    se = np.sqrt(1 / a + 1 / b)
    z = lr / se
    return float(z), float(2 * (1 - sps.norm.cdf(abs(z))))


def bootstrap_share(flags: np.ndarray, B: int = 2000, seed: int = 17) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    f = np.asarray(flags, bool)
    n = len(f)
    if n == 0:
        return np.nan, np.nan, np.nan
    draws = rng.binomial(n, f.mean(), size=B) / n
    return float(f.mean()), float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def bootstrap_gap(flags_a: np.ndarray, flags_b: np.ndarray, B: int = 2000, seed: int = 17) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    a, b = np.asarray(flags_a, bool), np.asarray(flags_b, bool)
    da = rng.binomial(len(a), a.mean(), size=B) / len(a)
    db = rng.binomial(len(b), b.mean(), size=B) / len(b)
    g = (db - da) * 100
    return float((b.mean() - a.mean()) * 100), float(np.percentile(g, 2.5)), float(np.percentile(g, 97.5))


def chi_square_profile(obs: np.ndarray, ref: np.ndarray) -> tuple[float, float]:
    obs = np.asarray(obs, float)
    ref = np.asarray(ref, float)
    exp = ref / ref.sum() * obs.sum()
    keep = exp > 0
    stat, p = sps.chisquare(obs[keep], exp[keep])
    return float(stat), float(p)


def poisson_trend(years: np.ndarray, counts: np.ndarray) -> dict:
    """Poisson GLM log(count) = a + b*year; returns slope per year with 95% CI (statsmodels if available)."""
    try:
        import statsmodels.api as sm
        X = sm.add_constant(np.asarray(years, float) - np.mean(years))
        m = sm.GLM(np.asarray(counts, float), X, family=sm.families.Poisson()).fit()
        b = float(m.params[1]); se = float(m.bse[1])
        return {"slope": b, "ci": [b - 1.96 * se, b + 1.96 * se], "pct_per_year": (np.exp(b) - 1) * 100, "ci_contains_zero": bool(b - 1.96 * se <= 0 <= b + 1.96 * se)}
    except Exception as e:  # pragma: no cover
        return {"slope": np.nan, "ci": [np.nan, np.nan], "error": str(e)}


def loyo_ratios(base: pd.Series, recent: pd.Series) -> dict:
    """Ratio of recent mean to base mean, dropping each year in turn."""
    out = {}
    full = recent.mean() / base.mean()
    for y in base.index:
        out[int(y)] = float(recent.mean() / base.drop(y).mean())
    for y in recent.index:
        out[int(y)] = float(recent.drop(y).mean() / base.mean())
    vals = np.array(list(out.values()))
    return {"full": float(full), "min": float(vals.min()), "max": float(vals.max()), "by_dropped_year": out,
            "direction_holds": bool((vals > 1).all() if full > 1 else (vals < 1).all())}
