"""Stage 08b — metro-level private comparator for the city view.

Each city is compared to the PRIVATE sector in its own metro (the central
county/counties), not the whole state. We pull ACS PUMS private workers (COW 1-2)
for the metro's PUMAs (crosswalks/city_to_puma.csv) and compute the median and
90th-percentile real annual wage by domain, in constant 2026 dollars.

Output: output/metro_private.json   {city: {domain: {p50, p90, n}}, _meta: {...}}
Run: python 08b_metro_comparator.py
"""

from __future__ import annotations

import json
import numpy as np
import pandas as pd
import requests

import config
from fetchers import UA
from pums_lib import cpi_annual, cpi_target, load_crosswalk, map_domain, weighted_quantile

YEAR = config.PUMS_LATEST_YEAR  # 2023
GET = ["PWGTP", "WAGP", "SOCP", "COW", "WKHP", "WKWN", "ADJINC", "AGEP", "PUMA"]


def load_city_pumas() -> dict[str, tuple[str, set[str]]]:
    df = pd.read_csv(config.CROSSWALK_DIR / "city_to_puma.csv",
                     dtype={"state_fips": str, "puma": str})
    out: dict[str, tuple[str, set[str]]] = {}
    for city, g in df.groupby("city"):
        out[city] = (g["state_fips"].iloc[0], set(g["puma"]))
    return out


def fetch_state_private(fips: str) -> pd.DataFrame:
    params = {"get": ",".join(GET), "AGEP": "25:64", "COW": "1,2", "for": f"state:{fips}"}
    if config.CENSUS_API_KEY:
        params["key"] = config.CENSUS_API_KEY
    url = config.PUMS_BASE.format(year=YEAR)
    r = requests.get(url, params=params, headers=UA, timeout=120)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.loc[:, ~df.columns.duplicated()]
    for c in ["PWGTP", "WAGP", "WKHP", "WKWN", "ADJINC", "AGEP"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # constant-2026 real annual wage
    adj = df["ADJINC"].astype(float)
    adj = adj.where(adj <= 10, adj / 1e6).fillna(1.0)
    factor = cpi_target() / cpi_annual()[YEAR]
    df["real_annual_wage"] = df["WAGP"] * adj * factor
    # full-time / full-year, positive wages
    df = df[(df["WAGP"] > 0) & (df["WKHP"] >= config.MIN_HOURS_FT) & (df["WKWN"] >= config.MIN_WEEKS_FY)]
    xwalk = load_crosswalk()
    df["domain"] = df["SOCP"].astype(str).map(lambda s: map_domain(s, xwalk))
    df["PUMA"] = df["PUMA"].astype(str).str.zfill(5)
    return df[["PUMA", "domain", "real_annual_wage", "PWGTP"]]


def wq(frame: pd.DataFrame, q: float) -> float:
    return weighted_quantile(frame["real_annual_wage"].to_numpy(),
                             frame["PWGTP"].to_numpy(float), q / 100.0)


def main() -> None:
    print("Stage 08b — metro private comparator")
    city_pumas = load_city_pumas()
    states = sorted({st for st, _ in city_pumas.values()})
    state_frames = {}
    for fips in states:
        state_frames[fips] = fetch_state_private(fips)
        print(f"  state {fips}: {len(state_frames[fips]):,} private FT/FY rows")

    out: dict = {"_meta": {"year": YEAR, "dollar_year": config.DOLLAR_YEAR,
                           "note": "Private-sector median/p90 real annual wage in the city's "
                                   "metro (central county/counties), ACS PUMS, full-time/full-year."}}
    for city, (fips, pumas) in city_pumas.items():
        sub = state_frames[fips][state_frames[fips]["PUMA"].isin(pumas)]
        doms: dict = {}
        for dom in (["all"] + sorted(sub["domain"].unique())):
            g = sub if dom == "all" else sub[sub["domain"] == dom]
            if dom == "other" or len(g) < 50:
                continue
            doms[dom] = {"p50": round(wq(g, 50), 0), "p90": round(wq(g, 90), 0), "n": int(len(g))}
        out[city] = doms
        out["_meta"][city] = {"pumas": len(pumas), "n": int(len(sub))}
        sw = doms.get("software_it", {})
        print(f"  {city}: {len(sub):,} metro-private rows; software p50=${sw.get('p50',0):,.0f} p90=${sw.get('p90',0):,.0f}")

    (config.OUTPUT_DIR / "metro_private.json").write_text(json.dumps(out, separators=(",", ":")))
    print("Stage 08b done.")


if __name__ == "__main__":
    main()
