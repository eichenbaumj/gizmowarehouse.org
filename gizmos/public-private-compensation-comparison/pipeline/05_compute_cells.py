"""Stage 05 — compute weighted wage cells from the PUMS analysis frame.

Outputs (output/):
  analysis_frame.parquet  — slim person frame for the regressions (stage 06)
  cells_national.parquet  — year x domain x govlevel x percentile -> real hourly wage
  cells_state.parquet     — latest year: state x domain x sector -> p50 real wage
  educ_gradient.json      — latest year: education x sector p50/mean (the CBO-style gradient)
  macro_percentiles.json  — economy-wide p50/p90/p95 by year (macro overlay)

Run: python 05_compute_cells.py
"""

from __future__ import annotations

import json
import numpy as np
import pandas as pd

import config
from pums_lib import load_analysis_frame, weighted_quantile

GOVLEVELS = ["private_fp", "private_np", "local", "state", "federal"]
SMALL_CELL = 100  # unweighted-n threshold below which a cell is flagged


def wq(g: pd.DataFrame, q: float) -> float:
    return weighted_quantile(g["real_hourly_wage"].to_numpy(),
                             g["PWGTP"].to_numpy(float), q / 100.0)


def cells_for(df: pd.DataFrame, group_cols: list[str], percentiles) -> pd.DataFrame:
    out = []
    for keys, g in df.groupby(group_cols, observed=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        rec = dict(zip(group_cols, keys))
        rec["n_unweighted"] = int(len(g))
        rec["weighted_n"] = float(g["PWGTP"].sum())
        for p in percentiles:
            rec[f"p{p}"] = round(wq(g, p), 2)
        out.append(rec)
    return pd.DataFrame(out)


def main() -> None:
    print("Stage 05 — compute cells")
    df = load_analysis_frame()
    print(f"  analysis frame: {len(df):,} person-rows across {df['year'].nunique()} years")

    # slim frame for regressions (stage 06)
    slim_cols = ["year", "real_hourly_wage", "educ", "age", "sector", "govlevel",
                 "domain", "SEX", "RAC1P", "WKHP", "state_fips", "state_abbr", "PWGTP", "ft_fy"]
    df[slim_cols].to_parquet(config.OUTPUT_DIR / "analysis_frame.parquet", index=False)

    # ---- level series uses full-time / full-year ----
    ff = df[df["ft_fy"]].copy()
    print(f"  FT/FY subset: {len(ff):,} rows")

    # add sector-aggregate rows (public = local+state+federal; private = fp+np)
    def with_aggregates(frame: pd.DataFrame) -> pd.DataFrame:
        pub = frame[frame["sector"] == "public"].copy(); pub["govlevel"] = "public"
        pri = frame[frame["sector"] == "private"].copy(); pri["govlevel"] = "private"
        return pd.concat([frame, pub, pri], ignore_index=True)

    # ---- national: year x domain x govlevel x percentile ----
    nat_src = with_aggregates(ff)
    # also an "all occupations" domain
    allocc = nat_src.copy(); allocc["domain"] = "all"
    nat_src = pd.concat([nat_src, allocc], ignore_index=True)
    nat = cells_for(nat_src, ["year", "domain", "govlevel"], config.PERCENTILES)
    nat.to_parquet(config.OUTPUT_DIR / "cells_national.parquet", index=False)
    print(f"  national cells: {len(nat):,}")

    # ---- state cross-section (latest year): state x domain x sector -> p50 ----
    # Plus a national "US" pseudo-state (all states pooled) for the default view.
    latest = ff[ff["year"] == config.PUMS_LATEST_YEAR].copy()
    st_src = latest[latest["sector"].isin(["public", "private"])].copy()
    allocc_s = st_src.copy(); allocc_s["domain"] = "all"
    st_src = pd.concat([st_src, allocc_s], ignore_index=True)
    national = st_src.copy(); national["state_abbr"] = "US"
    st_src = pd.concat([st_src, national], ignore_index=True)
    st = cells_for(st_src, ["state_abbr", "domain", "sector"], [50, 90])
    st.to_parquet(config.OUTPUT_DIR / "cells_state.parquet", index=False)
    print(f"  state cells: {len(st):,} (incl. national US)")

    # ---- wage distribution by year (real 2026 annual $) + government line ----
    # Serves Chart A (private vs government median) and Chart B (private p50/p90/p95
    # + government median). Government shown with and without teachers (SOC 25).
    def wqa(frame: pd.DataFrame, q: float) -> float:
        return weighted_quantile(frame["real_annual_wage"].to_numpy(),
                                 frame["PWGTP"].to_numpy(float), q / 100.0)

    dist = []
    for y, g in ff.groupby("year"):
        priv = g[g["sector"] == "private"]
        pub = g[g["sector"] == "public"]
        pub_nt = pub[~pub["is_teacher"]]
        dist.append({
            "year": int(y),
            "private_p50": round(wqa(priv, 50), 0),
            "private_p90": round(wqa(priv, 90), 0),
            "private_p95": round(wqa(priv, 95), 0),
            "gov_p50": round(wqa(pub, 50), 0),
            "gov_p50_no_teachers": round(wqa(pub_nt, 50), 0),
            "n_unweighted": int(len(g)),
        })

    # ---- high-skill variant of the ladder: same distribution restricted to the
    # elite-pooled domains (software, legal, finance, engineering, management).
    # This is the "Where government pay sits" chart filtered to the professions
    # where the top of the private market has pulled away hardest. Elite private
    # pooled is millions of records, so p95 stays well-sampled.
    ELITE = ["software_it", "legal", "finance", "engineering", "management"]
    dist_hs = []
    for y, g in ff[ff["domain"].isin(ELITE)].groupby("year"):
        priv = g[g["sector"] == "private"]
        pub = g[g["sector"] == "public"]
        dist_hs.append({
            "year": int(y),
            "private_p50": round(wqa(priv, 50), 0),
            "private_p90": round(wqa(priv, 90), 0),
            "private_p95": round(wqa(priv, 95), 0),
            "gov_p50": round(wqa(pub, 50), 0),
            "gov_p50_no_teachers": round(wqa(pub, 50), 0),  # no teachers in the elite set
            "n_unweighted": int(len(g)),
        })

    (config.OUTPUT_DIR / "wage_distribution.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION,
        "dollar_year": config.DOLLAR_YEAR,
        "note": "Real annual wages (constant 2026 dollars) for full-time/full-year workers "
                "aged 25-64, ACS PUMS. private_p50/p90/p95 = private-sector distribution; "
                "gov_p50 = government median (gov_p50_no_teachers excludes SOC 25 education). "
                "Top-coding caps the private top, so p90/p95 understate the true top.",
        "distribution": dist,
        "distribution_highskill": dist_hs,
        "highskill_domains": ELITE,
        "highskill_note": "Same ladder restricted to the high-skill domains (software & IT, "
                          "legal, finance, engineering, management), private and government.",
    }, separators=(",", ":")))
    print(f"  wage distribution: {len(dist)} years (real ${config.DOLLAR_YEAR} annual); "
          f"high-skill variant: {len(dist_hs)} years")

    # ---- education gradient (latest year): educ x sector p50/mean ----
    grad = []
    for (e, s), g in latest.groupby(["educ", "sector"], observed=True):
        if s not in ("public", "private") or e is None or (isinstance(e, float) and np.isnan(e)):
            continue
        wsum = g["PWGTP"].sum()
        grad.append({
            "educ": str(e), "sector": s,
            "p50": round(wq(g, 50), 2),
            "mean": round(float((g["real_hourly_wage"] * g["PWGTP"]).sum() / wsum), 2),
            "n_unweighted": int(len(g)),
        })
    (config.OUTPUT_DIR / "educ_gradient.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION, "year": config.PUMS_LATEST_YEAR,
        "note": "Raw (unadjusted) real hourly wage by education x sector, ACS PUMS FT/FY. "
                "Composition-adjusted federal gradient is in stage 06; CBO 2024 is the anchor.",
        "gradient": grad,
    }, separators=(",", ":")))
    print(f"  educ gradient: {len(grad)} cells")
    print("Stage 05 done.")


if __name__ == "__main__":
    main()
