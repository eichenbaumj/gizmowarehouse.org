"""Stage 02 — the shape of public employment (intro section).

  - CES government employment (federal / state / local, thousands), annual means,
    the long headcount trend + government share of total nonfarm employment.
  - Census ASPEP govsemp: latest FTE and March payroll by government type
    (state vs local) — Census drops federal here after 2014, so federal headcount
    comes from CES and federal pay from BEA (stage 01).

Output: output/shape.json
Run: python 02_fetch_shape.py
"""

from __future__ import annotations

import config
from fetchers import census_get, fetch_fred, write_json


def annual_mean(df):
    """Annual means of a monthly series, dropping any in-progress year that does
    not yet have all 12 months (so 'latest' is never a partial-year average)."""
    g = df.copy()
    g["year"] = g["date"].dt.year
    grp = g.groupby("year")["value"]
    means, counts = grp.mean(), grp.count()
    full = counts[counts >= 12].index
    return means.loc[means.index.isin(full)]


def main() -> None:
    print("Stage 02 — shape of public employment")

    # --- CES employment trend (thousands) ----------------------------------
    series = {
        "federal": config.FRED_SERIES["emp_federal"],
        "state": config.FRED_SERIES["emp_state"],
        "local": config.FRED_SERIES["emp_local"],
        "government_total": config.FRED_SERIES["emp_government_total"],
        "total_nonfarm": config.FRED_SERIES["emp_total_nonfarm"],
    }
    trend = {k: annual_mean(fetch_fred(v)) for k, v in series.items()}

    common_years = sorted(
        set.intersection(*[set(s.index.astype(int)) for s in trend.values()])
    )
    employment_trend = {
        k: [{"year": int(y), "thousands": round(float(s.loc[y]), 1)} for y in common_years]
        for k, s in trend.items()
    }

    latest_y = common_years[-1]
    gov = trend["government_total"].loc[latest_y]
    nonfarm = trend["total_nonfarm"].loc[latest_y]
    latest = {
        "year": int(latest_y),
        "federal_k": round(float(trend["federal"].loc[latest_y]), 0),
        "state_k": round(float(trend["state"].loc[latest_y]), 0),
        "local_k": round(float(trend["local"].loc[latest_y]), 0),
        "government_total_k": round(float(gov), 0),
        "gov_share_of_nonfarm_pct": round(float(gov / nonfarm * 100), 1),
    }
    print(f"  CES {latest_y}: fed={latest['federal_k']:.0f}k state={latest['state_k']:.0f}k "
          f"local={latest['local_k']:.0f}k  gov share={latest['gov_share_of_nonfarm_pct']}%")

    # --- Census ASPEP govsemp: FTE + March payroll by gov type -------------
    tbl = census_get(
        config.GOVSEMP_API,
        {"get": "GOVTYPE,AGG_DESC,FTE,TOT_EMP,TOT_PAY", "for": "us:1",
         "time": str(config.GOVSEMP_YEAR)},
    )
    hdr, rows = tbl[0], tbl[1:]
    gi, ai = hdr.index("GOVTYPE"), hdr.index("AGG_DESC")
    fi, ei, pi = hdr.index("FTE"), hdr.index("TOT_EMP"), hdr.index("TOT_PAY")
    govsemp = {}
    for r in rows:
        if r[ai] != config.GOVSEMP_TOTAL_AGG:
            continue
        label = config.GOVTYPE.get(r[gi])
        if not label:
            continue
        govsemp[label] = {
            "fte": int(r[fi]),
            "total_employees": int(r[ei]),
            "march_monthly_payroll_usd": int(r[pi]),
            "implied_annual_payroll_usd": int(r[pi]) * 12,
        }
    print(f"  govsemp {config.GOVSEMP_YEAR}: state FTE={govsemp['state']['fte']:,} "
          f"local FTE={govsemp['local']['fte']:,}")

    out = {
        "schema_version": config.SCHEMA_VERSION,
        "ces_employment_trend": employment_trend,
        "latest": latest,
        "govsemp_year": config.GOVSEMP_YEAR,
        "govsemp_by_govtype": govsemp,
        "notes": {
            "ces": "CES government employment includes the Postal Service in 'federal'. "
                   "Thousands of employees, annual means of monthly SA series.",
            "govsemp": "Census ASPEP excludes federal employment after 2014; federal "
                       "headcount here is from CES and federal pay from BEA (stage 01). "
                       "TOT_PAY is the March monthly payroll; annual is March*12 (approx).",
        },
    }
    write_json(config.OUTPUT_DIR / "shape.json", out)
    print("Stage 02 done.")


if __name__ == "__main__":
    main()
