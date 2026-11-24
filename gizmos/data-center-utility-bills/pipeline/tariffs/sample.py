#!/usr/bin/env python3
"""Tariff check: which utilities' tariffs are collected, chosen from load and sales only.

PROPOSAL, not yet confirmed by Joe (docs/tariff-check.md, docs/DECISIONS.md D-30).
No tariff is collected, and no price is read, by this script.

Hosts: every cohort utility at the 2% load threshold (first crossing 2011 to
2022), whether or not it is in the headline set (D-40, D-46), so the check covers
the headline estimate and the every-cohort-utility run.

Each host gets one comparison utility, chosen without looking at any price:
  * it never hosts material load (under 0.5% throughout, no crypto load of 2%
    or more) and is not set aside;
  * it reports residential sales in every year of the host's ten-year window;
  * same state and same ownership group if there is one; else same state;
    else same market region and ownership group; else same market region;
  * among those, the closest in residential customers in the host's reference
    year (three years before first crossing);
  * a comparison utility is used once. Hosts are taken in a fixed random order
    (SEED), which is also the order of collection, so a collection that stops
    early is a random sample of the hosts.

The usage level is fixed per pair before collection: the host's average
monthly residential use in its reference year, rounded to the nearest 50 kWh,
from sales and customer counts. 1,000 kWh a month is computed alongside.

Output: data/frozen/tariff_check_sample.csv
Run:  python3 -I pipeline/tariffs/sample.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.electricity import panel  # noqa: E402

SEED = 20261112
THETA = 0.02
KEY = ps.KEY
TIERS = ("same_state_and_ownership", "same_state", "same_region_and_ownership", "same_region")


def choose(q: pd.DataFrame, dose: pd.DataFrame, regions: pd.Series, aside: set, seed: int = SEED, aside_ten: set | None = None) -> pd.DataFrame:
    aside_ten = aside if aside_ten is None else aside_ten
    treated, clean = ps.design(q, dose, THETA, ps.history_settled(THETA))
    clean = clean[[(int(u), s) not in aside for u, s in zip(clean.utility_id_eia, clean.state)]]
    attrs = ps.attributes(q, regions)
    ok = q[q.meets_size_floor & (q.res_mwh > 0)]
    cust = ok.pivot_table(index=KEY, columns="year", values="res_customers")
    mwh = ok.pivot_table(index=KEY, columns="year", values="res_mwh")
    names = q.groupby(KEY).utility_name.last()
    cand = attrs.reindex(pd.MultiIndex.from_frame(clean)).dropna(subset=["region"])
    used: set = set()
    rows = []
    order = np.random.default_rng(seed).permutation(len(treated))
    for rank, i in enumerate(order, start=1):
        h = treated.iloc[i]
        k = (int(h.utility_id_eia), h.state)
        ref = int(h.cohort) + ps.REF
        window = list(range(int(h.cohort) - ps.PRE, int(h.cohort) + ps.POST + 1))
        in_window = k in cust.index and cust.loc[k, window].notna().all()
        size = float(cust.loc[k, ref]) if k in cust.index and pd.notna(cust.loc[k, ref]) else np.nan
        use = float(mwh.loc[k, ref] * 1000 / cust.loc[k, ref] / 12) if np.isfinite(size) and size > 0 else np.nan
        row = {"collection_order": rank, "pair_id": f"P{rank:02d}", "host_id": k[0], "state": k[1], "host_name": names.get(k),
               "first_crossing": int(h.cohort), "window_start": window[0], "window_end": window[-1],
               "ownership": attrs.ownership.get(k), "market_region": attrs.region.get(k),
               "in_headline_set": k not in aside, "in_set_with_the_ten_year_case": k not in aside_ten, "host_reports_every_window_year": bool(in_window),
               "host_res_customers_reference_year": None if not np.isfinite(size) else int(size),
               "usage_kwh_per_month": None if not np.isfinite(use) else int(round(use / 50) * 50)}
        pool = cand[[c not in used and c in cust.index and bool(cust.loc[c, window].notna().all()) for c in cand.index]]
        same_state = pool.index.get_level_values(1) == k[1]
        own = (pool.ownership == row["ownership"]).values
        reg = (pool.region == row["market_region"]).values
        pick, tier = None, None
        for t, mask in zip(TIERS, (same_state & own, same_state, reg & own, reg)):
            c = pool[mask]
            if len(c) and np.isfinite(size):
                gap = np.abs(np.log(cust.loc[c.index, ref].values.astype(float)) - np.log(size))
                pick, tier = c.index[int(np.argmin(gap))], t
                row["size_gap_log_points"] = round(float(gap.min()), 3)
                break
        if pick is not None:
            used.add(pick)
            row.update({"comparison_id": int(pick[0]), "comparison_state": pick[1], "comparison_name": names.get(pick),
                        "comparison_ownership": attrs.ownership.get(pick), "match": tier,
                        "comparison_res_customers_reference_year": int(cust.loc[pick, ref])})
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    q = panel.load_quantities()
    dose = pd.read_parquet(ROOT / "data" / "interim" / "utility_year_dose.parquet")
    s = choose(q, dose, ps.market_regions(q), ps.set_aside(THETA), aside_ten=ps.set_aside(THETA, ten_year_case=True))
    s.to_csv(ROOT / "data" / "frozen" / "tariff_check_sample.csv", index=False)
    print("hosts:", len(s), "| in the headline set:", int(s.in_headline_set.sum()), "| with a comparison:", int(s.comparison_id.notna().sum()))
    print("match:", s.match.value_counts().to_dict())
    print("size gap, log points: median", round(float(s.size_gap_log_points.median()), 2), "max", round(float(s.size_gap_log_points.max()), 2))
    print("usage level kWh/month: min", int(s.usage_kwh_per_month.min()), "median", int(s.usage_kwh_per_month.median()),
          "max", int(s.usage_kwh_per_month.max()))
    print("ownership of hosts:", s.ownership.value_counts().to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
