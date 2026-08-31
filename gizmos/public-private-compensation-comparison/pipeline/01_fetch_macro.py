"""Stage 01 — macro published series (no microdata).

Builds the over-time compensation-growth divergence and the long median-wage
line from authoritative published series:
  - BLS ECI: private vs state&local total-comp and wages indexes (2001+),
    deflated to REAL and rebased so sectors are comparable.
  - FRED median usual weekly real earnings (1979+) — the long median-worker line.
  - BEA federal compensation per FTE (1998+) — fills the federal line ECI lacks.

Output: output/macro_published.json  (assembled into macro_topdist.json at stage 11)

Run: python 01_fetch_macro.py
"""

from __future__ import annotations

import config
from fetchers import fetch_bls, fetch_fred, write_json

BASE = 2005  # common rebase year for the real-growth indices


def annual_mean(df, value_col="value"):
    """Collapse a (possibly quarterly/monthly) FRED/BLS frame to annual means."""
    g = df.copy()
    g["year"] = g["date"].dt.year if "date" in g.columns else g["year"]
    return g.groupby("year")[value_col].mean()


def main() -> None:
    print("Stage 01 — macro published series")

    # --- CPI-U: annual means + latest-month target (for constant 2026 dollars) ---
    cpi_monthly = fetch_fred(config.FRED_SERIES["cpi_u"]).sort_values("date")
    cpi = annual_mean(cpi_monthly)
    cpi_base = cpi.loc[BASE]
    cpi_target = float(cpi_monthly.iloc[-1]["value"])
    cpi_target_date = str(cpi_monthly.iloc[-1]["date"].date())
    print(f"  CPI-U {BASE}={cpi_base:.1f}  target({cpi_target_date})={cpi_target:.1f}")

    out: dict = {
        "schema_version": config.SCHEMA_VERSION,
        "base_year_index": BASE,
        "deflator_note": config.DEFLATOR_NOTE,
        "cpi_target": cpi_target,
        "cpi_target_date": cpi_target_date,
        "dollar_year": config.DOLLAR_YEAR,
        "cpi_u_annual": {int(y): round(float(v), 3) for y, v in cpi.items()},
    }

    # --- BLS ECI: private vs state&local, total comp + wages ---------------
    eci_ids = list(config.ECI_SERIES.values())
    eci_raw = fetch_bls(eci_ids, config.ECI_START_YEAR, config.BASE_YEAR + 2)
    id_to_name = {v: k for k, v in config.ECI_SERIES.items()}
    eci_out: dict = {}
    for sid, df in eci_raw.items():
        name = id_to_name[sid]
        # quarterly index -> annual mean nominal index
        ser = df[df["period"].str.startswith("Q")].groupby("year")["value"].mean()
        # real index: nominal ECI index / CPI, rebased to BASE=100
        real = (ser / cpi.reindex(ser.index))
        real = real / real.loc[BASE] * 100.0
        eci_out[name] = [
            {"year": int(y), "index_nominal": round(float(ser.loc[y]), 2),
             "real_index": round(float(real.loc[y]), 2)}
            for y in ser.index if y in real.index
        ]
    out["eci"] = eci_out
    print(f"  ECI: {len(eci_out)} series, "
          f"{eci_out['private_totalcomp'][0]['year']}–{eci_out['private_totalcomp'][-1]['year']}")

    # --- FRED median usual weekly real earnings (1982-84$, 1979+) ----------
    mwe = annual_mean(fetch_fred(config.FRED_SERIES["median_real_weekly_earnings"]))
    mwe_idx = mwe / mwe.loc[BASE] * 100.0
    out["median_real_weekly_earnings"] = [
        {"year": int(y), "real_1982_84d": round(float(mwe.loc[y]), 1),
         "real_index": round(float(mwe_idx.loc[y]), 2)}
        for y in mwe.index
    ]
    print(f"  median real weekly earnings: {int(mwe.index.min())}–{int(mwe.index.max())}")

    # --- BEA federal compensation per FTE (nominal $, 1998+) ---------------
    fed = annual_mean(fetch_fred(config.FRED_SERIES["federal_comp_per_fte"]))
    # deflate to constant 2026 dollars (latest CPI month)
    fed_real = fed * (cpi_target / cpi.reindex(fed.index))
    fed_idx = (fed / cpi.reindex(fed.index))
    fed_idx = fed_idx / fed_idx.loc[BASE] * 100.0
    out["federal_comp_per_fte"] = [
        {"year": int(y), "nominal": round(float(fed.loc[y]), 0),
         "real_dollars": round(float(fed_real.loc[y]), 0),
         "real_index": round(float(fed_idx.loc[y]), 2)}
        for y in fed.index if y in fed_idx.index
    ]
    print(f"  federal comp/FTE: {int(fed.index.min())}–{int(fed.index.max())}")

    write_json(config.OUTPUT_DIR / "macro_published.json", out)
    print("Stage 01 done.")


if __name__ == "__main__":
    main()
