#!/usr/bin/env python3
"""Build the utility x state x year panel and print a construction QA report.

Run:  python3 -I pipeline/electricity/build_panel.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.electricity import panel  # noqa: E402
from pipeline.electricity import succession as succ  # noqa: E402

BIG = 20_000  # residential customers; every break at a unit this size is classified in succession.csv


def succession_report(sales: pd.DataFrame, table: pd.DataFrame, q: pd.DataFrame) -> dict:
    """Check the succession table against the data it is applied to. Quantities only.

    For every summed row: both ids must exist in the sales data for that state,
    and the combined unit's retail sales must not jump at the handover. Then:
    which large units still stop early or start late with no row in the table.
    """
    raw, _ = panel.build(sales, succession={})  # ids as EIA reported them
    key = ["utility_id_eia", "state"]
    span = raw.groupby(key).agg(first=("year", "min"), last=("year", "max"), peak_res=("res_customers", "max"))
    mapping = succ.resolve(table)
    tot = q.set_index(key + ["year"]).total_retail_mwh
    rows, problems = [], []
    for r in table[table.action == "sum"].itertuples():
        pid, st, final = int(r.predecessor_id), r.state, mapping[(int(r.predecessor_id), r.state)]
        if (pid, st) not in span.index:
            problems.append(f"predecessor {pid}:{st} has no rows in the sales data")
            continue
        if (final, st) not in span.index and (final, st) not in set(zip(q.utility_id_eia, q.state)):
            problems.append(f"successor {final}:{st} has no rows in the sales data")
            continue
        last = int(span.loc[(pid, st), "last"])
        before, after = tot.get((final, st, last), float("nan")), tot.get((final, st, last + 1), float("nan"))
        rows.append({"predecessor": f"{pid}:{st}", "unit": f"{final}:{st}", "predecessor_last_year": last,
                     "predecessor_peak_res_customers": int(span.loc[(pid, st), "peak_res"]),
                     "unit_sales_change_at_handover": None if not (before > 0 and after > 0) else round(after / before - 1, 3)})
    handled = set(zip(table.predecessor_id.astype(int), table.state))
    successors = {(int(r.successor_id), r.state) for r in table[table.action == "sum"].itertuples()}
    big = span[span.peak_res >= BIG]
    stops = [f"{u}:{st}" for (u, st), r in big.iterrows() if r["last"] < raw.year.max() and (u, st) not in handled]
    starts = [f"{u}:{st}" for (u, st), r in big.iterrows() if r["first"] > raw.year.min() and (u, st) not in successors]
    jumps = [x for x in rows if x["unit_sales_change_at_handover"] is not None and abs(x["unit_sales_change_at_handover"]) > 0.15]
    return {
        "rows_summed": int((table.action == "sum").sum()),
        "rows_not_linked": int((table.action == "not_linked").sum()),
        "units_with_predecessors": len({(u, st) for (_, st), u in mapping.items()}),
        "unit_years_blending_more_than_one_id": int((q.n_ids_reporting > 1).sum()),
        "problems": problems,
        "summed": rows,
        "summed_with_a_sales_jump_over_15pct_at_handover": [x["predecessor"] for x in jumps],
        f"units_of_{BIG}_res_customers_that_stop_early_with_no_row": sorted(stops),
        f"units_of_{BIG}_res_customers_that_start_late_and_succeed_no_one": sorted(starts),
    }


def main() -> int:
    sales = panel.load_sales()
    table = succ.load()
    mapping = succ.resolve(table)
    q, o = panel.build(sales, succession=mapping)
    panel.write(q, o)
    panel.reported_ids(sales, succession=mapping).to_parquet(panel.INTERIM / "panel_reported_ids.parquet", index=False)

    m = q.merge(o, on=panel.KEYS)
    priced = m[m.res_price.notna()]
    by_year = (
        priced.groupby("year")
        .apply(lambda d: pd.Series({
            "units": len(d),
            "units_size_floor": int(d.meets_size_floor.sum()),
            "res_twh": d.res_mwh.sum() / 1e6,
            "price_sales_weighted": (d.res_revenue_full.sum() / d.res_mwh.sum()) / 10.0,
            "price_median": d.res_price.median(),
        }), include_groups=False)
    )
    # National residential sales actually reported to EIA (all sellers), to show coverage.
    res_all = sales[(sales.customer_class == "residential") & sales.service_type.isin(["bundled", "delivery"])]
    nat = res_all.groupby("year").sales_mwh.sum() / 1e6
    by_year["coverage_of_reported_res_twh"] = by_year.res_twh / nat
    report = {
        "rows": int(len(m)),
        "priced_rows": int(len(priced)),
        "units_ever": int(priced.groupby(["utility_id_eia", "state"]).ngroups),
        "years": [int(priced.year.min()), int(priced.year.max())],
        "unpriced_reasons": {
            "no_residential_sales": int((m.res_mwh <= 0).sum()),
            "sales_but_unpriceable": int(((m.res_mwh > 0) & m.res_price.isna()).sum()),
        },
        "implausible_price_rows": int(((priced.res_price < 2) | (priced.res_price > 80)).sum()),
        "ownership_units_2025": priced[priced.year == priced.year.max()].ownership.value_counts().to_dict(),
        "delivery_share_gt_10pct_units_2025": int(
            (priced[priced.year == priced.year.max()].delivery_share > 0.10).sum()),
    }
    out = ROOT / "data" / "frozen" / "panel_construction_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    srep = succession_report(sales, table, q)
    (ROOT / "data" / "frozen" / "succession_report.json").write_text(json.dumps(srep, indent=2) + "\n")
    pd.set_option("display.width", 200)
    print(by_year.round(3).to_string())
    print(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in srep.items() if k != "summed"}, indent=2))
    if srep["problems"]:
        print("SUCCESSION TABLE DOES NOT MATCH THE DATA:", *srep["problems"], sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
