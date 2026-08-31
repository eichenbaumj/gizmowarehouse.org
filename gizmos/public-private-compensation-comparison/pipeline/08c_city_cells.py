"""Stage 08c — city-government pay by occupation domain vs a private comparator.

Classifies each city payroll record's title -> domain, deflates to constant 2026
dollars, takes the median city-government salary per domain, and joins the
metro private median (from stage 08b, metro_private.json, already 2026$) as the
comparator.

  Comparator: each city is compared to the PRIVATE sector in its own metro (the
  central county/counties, via crosswalks/city_to_puma.csv) — e.g. SF government
  vs Bay Area private, not all of California — so high-cost metros are not
  understated. (Earlier versions used a same-STATE comparator.)

Output: public/data/compgap/localities/cities.json
Run: python 08c_city_cells.py
"""

from __future__ import annotations

import json
import pandas as pd

import config
from city_lib import classify_title, load_title_rules
from pums_lib import cpi_annual, cpi_target

CITY_RAW = config.RAW_DIR / "cities"
MIN_N = 30  # suppress city-domain cells thinner than this


def main() -> None:
    print("Stage 08c — city cells")
    rules = load_title_rules()
    cpi = cpi_annual()
    target = cpi_target()

    # private comparator: the city's own METRO private sector (central county/
    # counties), median + p90 real annual wage in 2026$, from stage 08b. This
    # compares SF government to Bay Area private, not all of California.
    metro = json.loads((config.OUTPUT_DIR / "metro_private.json").read_text())

    name_by_key = {c["key"]: c for c in config.CITY_SOURCES}
    cities_meta, records, coverage = [], [], {}

    for src in config.CITY_SOURCES:
        f = CITY_RAW / f"{src['key']}.parquet"
        if not f.exists():
            print(f"  {src['key']}: no data (skipped)")
            continue
        df = pd.read_parquet(f)
        df["domain"] = df["title"].map(lambda t: classify_title(t, rules))
        dy = int(df["data_year"].iloc[0])
        factor = target / cpi.get(dy, cpi[max(cpi)])
        df["pay_2026"] = df["pay_annual"] * factor

        mapped = (df["domain"] != "other").mean()
        coverage[src["key"]] = round(float(mapped) * 100, 1)
        cities_meta.append({"key": src["key"], "name": src["name"], "state": src["state"],
                            "data_year": dy, "n": int(len(df)), "title_coverage_pct": coverage[src["key"]]})

        # all-occupations + per-domain medians
        for dom in (["all"] + sorted(df["domain"].unique())):
            sub = df if dom == "all" else df[df["domain"] == dom]
            if dom == "other":
                continue
            n = len(sub)
            if n < MIN_N:
                continue
            gov = float(sub["pay_2026"].median())
            gov90 = float(sub["pay_2026"].quantile(0.9))
            pm = metro.get(src["key"], {}).get(dom)
            rec = {"city": src["key"], "domain": dom,
                   "gov_p50": round(gov, 0), "gov_p90": round(gov90, 0), "n": int(n)}
            if pm:
                rec["private_p50_metro"] = round(pm["p50"], 0)
                rec["gap_vs_private_pct"] = round((gov / pm["p50"] - 1) * 100, 1)
                if pm.get("p90"):
                    rec["private_p90_metro"] = round(pm["p90"], 0)
                    rec["gap_top_pct"] = round((gov90 / pm["p90"] - 1) * 100, 1)
            records.append(rec)

        # validation: top titles in the elite domains
        for dom in ["software_it", "legal", "engineering", "finance", "management"]:
            tops = df[df["domain"] == dom]["title"].value_counts().head(3).index.tolist()
            if tops:
                print(f"    {src['key']}/{dom}: {tops}")
        print(f"  {src['key']}: {len(df):,} rows, {dy}, title coverage {coverage[src['key']]}%")

    out = {
        "schema_version": config.SCHEMA_VERSION,
        "dollar_year": config.DOLLAR_YEAR,
        "comparator_note": "City-government median/p90 base pay by domain (full-time), constant "
                           "2026 dollars, vs the private sector in that city's METRO (central "
                           "county/counties) from ACS PUMS. Title-to-domain mapping is keyword-based.",
        "cities": cities_meta,
        "records": records,
    }
    (config.PUBLIC_LOCALITIES_DIR / "cities.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"  wrote cities.json: {len(cities_meta)} cities, {len(records)} records")
    print("Stage 08c done.")


if __name__ == "__main__":
    main()
