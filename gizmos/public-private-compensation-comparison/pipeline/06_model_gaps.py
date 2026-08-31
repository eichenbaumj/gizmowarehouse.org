"""Stage 06 — composition-adjusted public-vs-private wage gaps.

Weighted (PWGTP) Mincer regressions on log real hourly wage, implemented in numpy
(no statsmodels — it has a scipy-version incompatibility in this env). HC1-robust
standard errors. For each government level vs private-for-profit:
  - adjusted gap %  (exp(coef)-1)
  - a specification-sensitivity RANGE (full / no-education / no-geography) — the
    spec choice is the EPI<->Biggs-Richwine dispute, so we show the spread.
fed/state/local kept separate (opposite signs). Plus the composition-adjusted
federal premium BY EDUCATION (the CBO-style gradient anchoring the elite-lag thesis).

Output: output/adjusted_gaps.json
Run: python 06_model_gaps.py
"""

from __future__ import annotations

import json
import numpy as np
import pandas as pd

import config

GOVLEVELS = ["private_np", "local", "state", "federal"]
SPECS = ["full", "no_education", "no_geography"]


def build_design(d: pd.DataFrame, drop_educ: bool, drop_geo: bool):
    """Return (X DataFrame of floats, list of govlevel dummy column names present)."""
    X = pd.DataFrame(index=d.index)
    X["const"] = 1.0
    gov = pd.get_dummies(d["govlevel"], prefix="gov")
    gov = gov.drop(columns=["gov_private_fp"], errors="ignore")
    X = X.join(gov)
    X["age"] = d["age"].to_numpy(float)
    X["age2"] = (d["age"].to_numpy(float)) ** 2
    X["WKHP"] = d["WKHP"].to_numpy(float)
    X["female"] = (d["SEX"] == 2).to_numpy(float)
    race = pd.get_dummies(d["RAC1P"].astype("Int64").astype(str), prefix="race")
    if race.shape[1] > 1:
        race = race.drop(columns=[race.columns[0]])
    X = X.join(race)
    if not drop_educ:
        ed = pd.get_dummies(d["educ"].astype(str), prefix="ed")
        if ed.shape[1] > 1:
            ed = ed.drop(columns=[ed.columns[0]])
        X = X.join(ed)
    if not drop_geo:
        st = pd.get_dummies(d["state_fips"].astype(str), prefix="st")
        if st.shape[1] > 1:
            st = st.drop(columns=[st.columns[0]])
        X = X.join(st)
    gov_cols = [c for c in X.columns if c.startswith("gov_")]
    return X.astype(float), gov_cols


def wls_hc1(y: np.ndarray, X: np.ndarray, w: np.ndarray):
    """Weighted least squares with HC1-robust covariance. Returns (beta, se)."""
    wX = w[:, None] * X
    XtWX = X.T @ wX
    bread = np.linalg.pinv(XtWX)
    beta = bread @ (X.T @ (w * y))
    resid = y - X @ beta
    n, k = X.shape
    meat = X.T @ ((w ** 2 * resid ** 2)[:, None] * X)
    cov = bread @ meat @ bread * (n / (n - k))
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    return beta, se


def run_spec(d: pd.DataFrame, drop_educ=False, drop_geo=False) -> dict:
    X, gov_cols = build_design(d, drop_educ, drop_geo)
    cols = list(X.columns)
    y = np.log(d["real_hourly_wage"].to_numpy(float))
    beta, se = wls_hc1(y, X.to_numpy(float), d["PWGTP"].to_numpy(float))
    out = {}
    for gc in gov_cols:
        gov = gc.replace("gov_", "")
        i = cols.index(gc)
        out[gov] = (float(np.expm1(beta[i]) * 100), float(se[i] * 100))
    return out


def gaps_with_range(d: pd.DataFrame) -> dict:
    by_spec = {
        "full": run_spec(d),
        "no_education": run_spec(d, drop_educ=True),
        "no_geography": run_spec(d, drop_geo=True),
    }
    out = {}
    for gov in GOVLEVELS:
        vals = [by_spec[s][gov][0] for s in SPECS if gov in by_spec[s]]
        if not vals:
            continue
        full = by_spec["full"].get(gov)
        out[gov] = {
            "adj_gap_pct": round(full[0], 1) if full else None,
            "se_pct": round(full[1], 2) if full else None,
            "range_lo": round(min(vals), 1),
            "range_hi": round(max(vals), 1),
        }
    return out


def main() -> None:
    print("Stage 06 — composition-adjusted gaps (numpy WLS, HC1)")
    df = pd.read_parquet(config.OUTPUT_DIR / "analysis_frame.parquet")
    df = df[df["ft_fy"] & df["sector"].isin(["public", "private"])].copy()
    df = df.dropna(subset=["educ", "age", "WKHP", "real_hourly_wage", "RAC1P", "SEX"])
    df = df[df["real_hourly_wage"] > 0]
    print(f"  regression sample (FT/FY): {len(df):,} rows")

    out = {"schema_version": config.SCHEMA_VERSION, "reference": "private_fp",
           "note": "Weighted (PWGTP) Mincer log-wage regressions, HC1 SEs (numpy). Gaps "
                   "are exp(coef)-1 vs private-for-profit. fed/state/local kept separate. "
                   "Range = full / no-education / no-geography specs."}

    latest = df[df["year"] == config.PUMS_LATEST_YEAR]
    out["by_govlevel_latest"] = gaps_with_range(latest)
    print("  latest adjusted gaps:", {k: v["adj_gap_pct"] for k, v in out["by_govlevel_latest"].items()})

    by_year = {}
    for y, g in df.groupby("year"):
        try:
            by_year[int(y)] = {gov: round(v[0], 1) for gov, v in run_spec(g).items()}
        except Exception as e:  # noqa: BLE001
            print(f"    year {y} failed: {e}")
    out["by_govlevel_year"] = by_year

    by_domain = {}
    for dom, g in latest.groupby("domain"):
        if dom == "other" or len(g) < 400 or g["sector"].nunique() < 2:
            continue
        try:
            by_domain[dom] = gaps_with_range(g)
        except Exception as e:  # noqa: BLE001
            print(f"    domain {dom} failed: {e}")
    out["by_domain_latest"] = by_domain
    print(f"  per-domain: {len(by_domain)} domains")

    grad = {}
    for e, g in latest.groupby("educ", observed=True):
        if g["sector"].nunique() < 2 or len(g) < 400:
            continue
        try:
            r = run_spec(g, drop_educ=True)
            grad[str(e)] = {gov: round(v[0], 1) for gov, v in r.items()}
        except Exception as ex:  # noqa: BLE001
            print(f"    educ {e} failed: {ex}")
    out["adjusted_gradient_by_education"] = grad
    print(f"  education gradient: {len(grad)} buckets")

    (config.OUTPUT_DIR / "adjusted_gaps.json").write_text(json.dumps(out, separators=(",", ":")))
    print("Stage 06 done.")


if __name__ == "__main__":
    main()
