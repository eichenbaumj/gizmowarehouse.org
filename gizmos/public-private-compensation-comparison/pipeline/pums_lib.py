"""Shared PUMS analysis helpers: load + restrict the frame, real hourly wage,
occupation->domain mapping, and weighted quantiles."""

from __future__ import annotations

import json
import numpy as np
import pandas as pd

import config

PUMS_RAW = config.RAW_DIR / "pums"

# WKW (weeks-worked recode, pre-2019) bin midpoints.
WKW_MIDPOINT = {1: 51.0, 2: 48.5, 3: 43.5, 4: 33.0, 5: 20.0, 6: 7.0}


def load_crosswalk() -> list[tuple[str, str, int]]:
    """Return [(soc_prefix, domain, is_elite)] sorted longest-prefix-first."""
    df = pd.read_csv(config.CROSSWALK_DIR / "soc_to_domain.csv", dtype={"soc_prefix": str})
    rows = [(str(r.soc_prefix), r.domain, int(r.is_elite)) for r in df.itertuples()]
    return sorted(rows, key=lambda t: -len(t[0]))


def domain_labels() -> dict[str, str]:
    df = pd.read_csv(config.CROSSWALK_DIR / "soc_to_domain.csv")
    return dict(zip(df["domain"], df["domain_label"]))


def map_domain(socp: str, xwalk: list[tuple[str, str, int]]) -> str:
    if not isinstance(socp, str):
        return "other"
    for prefix, domain, _ in xwalk:
        if socp.startswith(prefix):
            return domain
    return "other"


def cpi_annual() -> dict[int, float]:
    macro = json.loads((config.OUTPUT_DIR / "macro_published.json").read_text())
    return {int(k): float(v) for k, v in macro["cpi_u_annual"].items()}


def cpi_target() -> float:
    """Latest-month CPI level — the constant-2026-dollar deflation target."""
    macro = json.loads((config.OUTPUT_DIR / "macro_published.json").read_text())
    return float(macro["cpi_target"])


def load_analysis_frame() -> pd.DataFrame:
    """Concatenate all cached state-year parquets, apply the analysis restriction,
    and attach real hourly wage (constant BASE_YEAR dollars) + domain + govlevel."""
    files = sorted(PUMS_RAW.glob("*.parquet"))
    if not files:
        raise RuntimeError("No PUMS parquets in raw/pums — run stage 03 first.")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    # weeks worked. The coding changes by vintage (verified against the raw files):
    #   <=2007: WKW is CONTINUOUS weeks (0-52)
    #   2008-2018: WKW is the BINNED recode (1-6) -> bin midpoint
    #   2019+: WKWN is continuous weeks
    # The bin codes 1-6 collide numerically with continuous 1-6, so we MUST switch
    # on the survey year, not on the value.
    yr = df["year"].astype(int)
    weeks = pd.Series(np.nan, index=df.index, dtype=float)
    if "WKWN" in df.columns:
        m = yr >= 2019
        weeks.loc[m] = pd.to_numeric(df.loc[m, "WKWN"], errors="coerce")
    if "WKW" in df.columns:
        mb = (yr >= 2008) & (yr <= 2018)
        weeks.loc[mb] = df.loc[mb, "WKW"].map(WKW_MIDPOINT)
        mc = yr <= 2007
        weeks.loc[mc] = pd.to_numeric(df.loc[mc, "WKW"], errors="coerce")
    df["weeks"] = weeks

    # ADJINC: income-inflation factor. The API returns it inconsistently across
    # vintages — a 6-implied-decimal integer in some years (e.g. 2010 -> 1007624)
    # and an already-scaled float in others (e.g. 2023 -> 1.019518). Normalise: any
    # value >10 is integer-encoded, divide by 1e6. Missing pre-2010 -> 1.0.
    adj = df.get("ADJINC")
    adj = (adj if adj is not None else pd.Series(1.0, index=df.index)).astype(float).fillna(1.0)
    df["adjinc"] = adj.where(adj <= 10, adj / 1e6)

    # core restriction: employed wage/salary, positive wages/hours/weeks
    df = df[df["ESR"].isin([1, 2])]
    df = df[df["COW"].astype(str).isin(config.PUMS_COW) ]
    df = df[(df["WAGP"] > 0) & (df["WKHP"] > 0) & (df["weeks"] > 0)]

    # real annual wage in constant 2026 dollars (deflate each year to the latest CPI)
    cpi = cpi_annual()
    target = cpi_target()
    df["cpi_factor"] = df["year"].map(lambda y: target / cpi[int(y)])
    df["real_annual_wage"] = df["WAGP"] * df["adjinc"] * df["cpi_factor"]
    df["real_hourly_wage"] = df["real_annual_wage"] / (df["WKHP"] * df["weeks"])
    # trim implausible hourly wages (data errors / tiny denominators)
    df = df[(df["real_hourly_wage"] >= 2) & (df["real_hourly_wage"] <= 2000)]

    # full-time / full-year flag (the level-series cell)
    df["ft_fy"] = (df["WKHP"] >= config.MIN_HOURS_FT) & (df["weeks"] >= config.MIN_WEEKS_FY)

    # sector + domain
    cow = df["COW"].astype(str)
    df["govlevel"] = cow.map(config.PUMS_COW)
    df["sector"] = np.where(cow.isin(config.COW_PUBLIC), "public",
                    np.where(cow.isin(config.COW_PRIVATE), "private", "other"))
    xwalk = load_crosswalk()
    df["domain"] = df["SOCP"].astype(str).map(lambda s: map_domain(s, xwalk))
    # teachers (SOC 25 education-instruction group) — excluded from headline aggregates
    df["is_teacher"] = df["domain"] == config.TEACHER_DOMAIN

    # education buckets (for regression + CBO-style gradient)
    df["educ"] = pd.cut(df["SCHL"], bins=[-1, 15, 17, 19, 20, 21, 22, 24],
                        labels=["lt_hs", "hs", "some_college", "assoc",
                                "bachelors", "masters", "prof_doctorate"])
    df["age"] = df["AGEP"].astype(float)
    return df


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Weighted quantile (q in [0,1]) with LINEAR interpolation.

    Earlier this picked the value at the bracket where cumulative weight crossed
    the cutoff (a step function). Because ACS rounds reported wages, the median of
    several distinct groups would snap to the same modal salary — e.g. public and
    private "Legal" both landed on $107k to the dollar. Interpolating within the
    bracket separates them and matches numpy's default 'linear' convention.

    Uses the Hazen plotting position (each sorted value sits at the midpoint of its
    own weight interval), the standard choice for survey weights.
    """
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w)
    total = cw[-1]
    if total <= 0:
        return float("nan")
    pos = (cw - 0.5 * w) / total          # normalized midpoint position of each value
    return float(np.interp(q, pos, v))     # clamps to v[0]/v[-1] outside [pos[0], pos[-1]]
