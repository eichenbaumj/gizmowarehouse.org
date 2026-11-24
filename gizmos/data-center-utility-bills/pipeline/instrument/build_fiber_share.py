#!/usr/bin/env python3
"""Rebuild the two parts of the Scalera, Bosetti and Pecci (CEPR) instrument.

Touches NO price data. Inputs come from fetch_instrument_inputs.py.

Share: each utility-state's share of the nation's fiber blocks, 2017-2019
----------------------------------------------------------------------
The paper (appendix S1.5): merge block-level Form 477 fiber data to the HIFLD
territory polygons, count the fiber-containing blocks that intersect each
territory in each year, divide by the national count for the contiguous U.S.,
and average the shares over 2017-2019.

What we do, and where it can differ from theirs:

  * A block is "in" a territory when its internal point (the Census Bureau's
    own label point for the block) falls inside the polygon. They intersect
    block polygons, so a block straddling a boundary counts for both sides in
    their version and for one side in ours. Blocks are small; territories
    are not.
  * Territory polygons overlap. A block inside two territories counts toward
    both, as in the paper. Shares therefore sum to more than one.
  * The unit is utility by state: the block's own state (from its FIPS code)
    splits a multi-state utility's polygon.
  * Form 477 was filed twice a year. The paper says "annually" and does not
    say which filing. Primary here is the December filing of each year; the
    June filings and the mean of all six are kept alongside, and the report
    states how closely they agree (docs/DECISIONS.md, D-15).
  * National total: distinct fiber blocks in the 48 states and D.C. in that
    filing, whether or not they fall in any territory polygon. The paper's
    wording also allows a second reading (the sum of every territory's
    count). The two differ by one constant, about 2, which rescales the
    instrument and leaves a two-stage estimate unchanged; the report prints
    the check under both.

Folding into panel units (fiber_share_by_unit.csv)
--------------------------------------------------
The electricity panel sums merged utilities into one unit (D-21), so the
replication needs the fiber share keyed the same way. `fold_to_units` maps each
(territory id, state) through succession.apply_ids and combines rows that land
on one unit. The three shares are recomputed from the combined block counts
over the same national denominators, never averaged.

Summing the counts of two predecessors counts a block twice when it lies inside
both polygons. Block membership is not cached by the build, but the raw inputs
are on disk, so `distinct_counts` redoes the point-in-polygon join for ONLY the
territories of units that absorbed more than one map id and counts DISTINCT
blocks per unit. Those distinct counts are the ones written to
fiber_share_by_unit.csv for the folded units; the other units are unchanged.
`n_blocks_summed` and `fiber_blocks_2019-12_summed` are kept beside them, and
the report states how far the summed counts were from the distinct ones. If the
raw files are missing, `fold_to_units` falls back to the sum and the report
says so. Run just this step on the frozen files with `--fold-only`.

Shift: national private data center construction spending
---------------------------------------------------------
Census Value of Construction Put in Place, private, not seasonally adjusted:
monthly values summed to calendar years, converted to 2024 dollars with the
CPI-U annual average, as the paper describes.

Both parts are checked against the paper's own printed tables (S3, S4) and
the comparison is written to data/frozen/instrument_report.json.

Run:  python3 -I pipeline/instrument/build_fiber_share.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.electricity import panel, succession  # noqa: E402

RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
FROZEN = ROOT / "data" / "frozen"

FILINGS = ["2017-06", "2017-12", "2018-06", "2018-12", "2019-06", "2019-12"]
DEC = [f for f in FILINGS if f.endswith("-12")]
JUN = [f for f in FILINGS if f.endswith("-06")]
NOT_CONTIGUOUS = {"02", "15"}  # Alaska, Hawaii; territories are not in the block file at all
FIPS = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC",
        "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
        "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
        "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
        "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
        "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY"}

# Printed in the paper; used only to check our rebuild, never to tune it.
PAPER_S3_REAL_2024_BN = {2015: 3.63, 2016: 5.39, 2017: 5.97, 2018: 8.66, 2019: 10.4, 2020: 11.2,
                         2021: 11.5, 2022: 13.5, 2023: 20.6, 2024: 31.1}
PAPER_N_UTILITY_STATES = 1237  # their balanced estimation sample (Table S6)
PAPER_S4_PCT = {"mean": 0.0655, "sd": 0.190, "min": 0.0, "p10": 0.000527, "median": 0.0159, "p90": 0.132, "max": 2.29}


def load_territories() -> gpd.GeoDataFrame:
    terr = gpd.read_file(RAW / "territories" / "retail_service_territories.geojson")
    terr = terr[terr.ID.astype(str).str.fullmatch(r"\d+")].copy()
    terr["utility_id_eia"] = terr.ID.astype(int)
    terr["geometry"] = terr.geometry.buffer(0)  # repairs self-intersections, as in build_inventory.py
    return terr[["utility_id_eia", "geometry"]]


def fiber_sets() -> dict[str, np.ndarray]:
    out = {}
    for f in FILINGS:
        b = pd.read_csv(RAW / "fcc477" / f"fiber_blocks_{f}.csv.gz", dtype=str).blockcode
        out[f] = np.sort(b[~b.str[:2].isin(NOT_CONTIGUOUS) & b.str[:2].isin(FIPS)].astype("int64").unique())
    return out


def spending() -> pd.DataFrame:
    d = pd.read_excel(RAW / "census_vip" / "privtime.xlsx", header=None)
    hdr = d.index[d[0].astype(str).str.strip().eq("Date")][0]
    col = [j for j in d.columns if str(d.at[hdr, j]).strip().lower() == "data center"]
    if len(col) != 1:
        raise RuntimeError("Census workbook layout changed: no single 'Data center' column")
    m = d.loc[hdr + 1:, [0, col[0]]].copy()
    m.columns = ["label", "musd"]
    m = m[m.label.astype(str).str.match(r"^[A-Z][a-z]{2}-\d{2}")]
    m["date"] = pd.to_datetime(m.label.astype(str).str.slice(0, 6), format="%b-%y")
    m["musd"] = pd.to_numeric(m.musd, errors="coerce")
    m = m.dropna(subset=["musd"])
    y = m.groupby(m.date.dt.year).agg(nominal_musd=("musd", "sum"), months=("musd", "size"))
    y = y[y.months == 12].drop(columns="months")  # complete calendar years only
    cpi = {int(k): v for k, v in json.loads((RAW / "bls" / "cpi_u_annual.json").read_text())["annual_average"].items()}
    y["cpi_u"] = y.index.map(cpi)
    y["real_2024_musd"] = y.nominal_musd * cpi[2024] / y.cpi_u
    # The paper's own printed series, for running its specification as published (D-16).
    y["paper_table_s3_real_2024_bn"] = y.index.map(PAPER_S3_REAL_2024_BN)
    y.index.name = "year"
    return y.reset_index()


COUNT_COLS = ["n_blocks"] + [f"fiber_blocks_{f}" for f in FILINGS]
SHARE_COLS = ["fiber_share_dec", "fiber_share_jun", "fiber_share_all6"]
UNIT_COLS = ["utility_id_eia", "state"] + COUNT_COLS + SHARE_COLS


def shares_from_counts(c: pd.DataFrame, national: dict[str, int]) -> pd.DataFrame:
    """Recompute the three shares from block counts, as main() does for the territory table."""
    c = c.copy()
    sh = {f: c[f"fiber_blocks_{f}"] / national[f] for f in FILINGS}
    c["fiber_share_dec"] = sum(sh[f] for f in DEC) / len(DEC)
    c["fiber_share_jun"] = sum(sh[f] for f in JUN) / len(JUN)
    c["fiber_share_all6"] = sum(sh[f] for f in FILINGS) / len(FILINGS)
    return c


def fold_to_units(c: pd.DataFrame, mapping: dict, national: dict[str, int],
                  distinct: pd.DataFrame | None = None) -> pd.DataFrame:
    """Territory-keyed table -> panel-unit-keyed table.

    c: columns utility_id_eia, state, COUNT_COLS (shares ignored). mapping: succession.resolve().
    distinct: optional frame keyed (utility_id_eia = unit id, state) with COUNT_COLS holding
    DISTINCT-block counts; where present it replaces the summed counts of that unit.
    Shares are recomputed from the final counts, never averaged.
    """
    c = c.copy()
    c["map_id"] = c.utility_id_eia
    c["utility_id_eia"] = succession.apply_ids(c, mapping)
    g = c.groupby(["utility_id_eia", "state"])
    out = g[COUNT_COLS].sum()
    out["ids_folded"] = g.map_id.agg(lambda v: ";".join(str(int(i)) for i in sorted(set(v))))
    out["n_ids_folded"] = g.map_id.nunique()
    out = out.reset_index()
    out["n_blocks_summed"] = out.n_blocks
    out["fiber_blocks_2019-12_summed"] = out["fiber_blocks_2019-12"]
    if distinct is not None and len(distinct):
        d = distinct.set_index(["utility_id_eia", "state"])[COUNT_COLS]
        idx = out.set_index(["utility_id_eia", "state"]).index
        hit = idx.isin(d.index)
        for col in COUNT_COLS:
            out.loc[hit, col] = d.reindex(idx[hit])[col].values
    out = shares_from_counts(out, national)
    return out.sort_values(["utility_id_eia", "state"]).reset_index(drop=True)


def distinct_counts(terr: gpd.GeoDataFrame, fiber: dict[str, np.ndarray], mapping: dict,
                    c: pd.DataFrame) -> pd.DataFrame:
    """DISTINCT blocks per folded unit: rerun the point-in-polygon join for the territories of
    units that absorbed more than one map id, de-duplicate (block, unit), count."""
    m = c[["utility_id_eia", "state"]].copy()
    m["unit"] = succession.apply_ids(m, mapping)
    n = m.groupby(["unit", "state"]).utility_id_eia.transform("nunique")
    m = m[n > 1]
    rows = []
    for st, mm in m.groupby("state"):
        fips = next(k for k, v in FIPS.items() if v == st)
        x = pd.read_csv(RAW / "lodes_xwalk" / f"{st.lower()}_xwalk.csv.gz",
                        usecols=["tabblk2010", "blklatdd", "blklondd"], dtype={"tabblk2010": "int64"})
        pts = gpd.GeoDataFrame(x[["tabblk2010"]], geometry=gpd.points_from_xy(x.blklondd, x.blklatdd), crs=4326)
        t = terr[terr.utility_id_eia.isin(mm.utility_id_eia)]
        j = gpd.sjoin(pts, t, predicate="within", how="inner")[["tabblk2010", "utility_id_eia"]]
        j = j.merge(mm[["utility_id_eia", "unit"]], on="utility_id_eia")
        j = j.drop_duplicates(["tabblk2010", "unit"])
        for f in FILINGS:
            in_state = fiber[f][(fiber[f] // 10**13) == int(fips)]
            j[f] = np.isin(j.tabblk2010.values, in_state)
        g = j.groupby("unit").agg(n_blocks=("tabblk2010", "size"), **{f: (f, "sum") for f in FILINGS})
        g = g.rename(columns={f: f"fiber_blocks_{f}" for f in FILINGS}).reset_index()
        g["state"] = st
        rows.append(g.rename(columns={"unit": "utility_id_eia"}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["utility_id_eia", "state"] + COUNT_COLS)


def fold_report(c: pd.DataFrame, u: pd.DataFrame, mapping: dict, distinct_used: bool) -> dict:
    q = panel.load_quantities()
    names = q.sort_values("year").groupby(["utility_id_eia", "state"]).utility_name.last()
    panel_units = set(names.index)
    fl = q.groupby(["utility_id_eia", "state"]).meets_size_floor.agg(["any", "all"])
    have = set(zip(u.utility_id_eia, u.state))
    multi = u[u.n_ids_folded > 1]
    ratio = (multi.n_blocks_summed / multi.n_blocks)
    ratio_f = (multi["fiber_blocks_2019-12_summed"] / multi["fiber_blocks_2019-12"].where(multi["fiber_blocks_2019-12"] > 0))
    pre = c.assign(unit=succession.apply_ids(c, mapping))
    pre["in_panel"] = [(a, b) in panel_units for a, b in zip(pre.unit, pre.state)]
    ni = pre[~pre.in_panel]
    single = u[u.n_ids_folded == 1]
    rekeyed = int((single.utility_id_eia.values != single.ids_folded.astype(int).values).sum())

    def lst(frame):
        return [{"unit_id": int(r.utility_id_eia), "state": r.state, "name": names.get((r.utility_id_eia, r.state)),
                 "map_ids": r.ids_folded, "n_blocks_summed": int(r.n_blocks_summed), "n_blocks": int(r.n_blocks),
                 "fiber_2019_12_summed": int(r["fiber_blocks_2019-12_summed"]),
                 "fiber_2019_12": int(r["fiber_blocks_2019-12"])} for _, r in frame.iterrows()]

    return {
        "rows_before_territory_keyed": int(len(c)),
        "rows_after_unit_keyed": int(len(u)),
        "units_that_absorbed_more_than_one_map_id": int(len(multi)),
        "units_rekeyed_to_a_successor_id_without_merging": rekeyed,
        "folded_units": lst(multi),
        "map_id_state_rows_not_in_panel": int(len(ni)),
        "map_id_state_rows_not_in_panel_with_nonzero_fiber_share": int((ni.fiber_share_dec > 0).sum()),
        "panel_units_total": int(len(panel_units)),
        "panel_units_meeting_floor_in_any_year": int(fl["any"].sum()),
        "panel_units_meeting_floor_in_every_year": int(fl["all"].sum()),
        "panel_units_above_floor_any_year_without_fiber_row": int(sum(1 for k in fl.index[fl["any"].astype(bool)] if k not in have)),
        "panel_units_above_floor_every_year_without_fiber_row": int(sum(1 for k in fl.index[fl["all"].astype(bool)] if k not in have)),
        "sum_fiber_share_dec_before": float(c.fiber_share_dec.sum()),
        "sum_fiber_share_dec_after": float(u.fiber_share_dec.sum()),
        "block_counts_are_distinct_blocks_for_folded_units": bool(distinct_used),
        "summed_over_distinct_n_blocks": {"max": float(ratio.max()) if len(ratio) else None,
                                          "median": float(ratio.median()) if len(ratio) else None},
        "summed_over_distinct_fiber_blocks_2019_12": {"max": float(ratio_f.max()) if len(ratio_f) else None,
                                                      "median": float(ratio_f.median()) if len(ratio_f) else None},
    }


def run_fold(c: pd.DataFrame, national: dict[str, int], with_distinct: bool = True) -> pd.DataFrame:
    """Fold, write fiber_share_by_unit.csv, add `fiber_share_by_panel_unit` to the report."""
    mapping = succession.resolve(succession.load())
    distinct = None
    if with_distinct:
        try:
            distinct = distinct_counts(load_territories(), fiber_sets(), mapping, c)
        except FileNotFoundError as e:
            print(f"  raw block files missing ({e}); keeping summed counts", flush=True)
    u = fold_to_units(c, mapping, national, distinct)
    keep = UNIT_COLS + ["ids_folded", "n_ids_folded", "n_blocks_summed", "fiber_blocks_2019-12_summed"]
    u[keep].to_csv(FROZEN / "fiber_share_by_unit.csv", index=False, float_format="%.10g")
    u[keep].to_parquet(INTERIM / "fiber_share_by_unit.parquet", index=False)
    rp = FROZEN / "instrument_report.json"
    report = json.loads(rp.read_text())
    report["fiber_share_by_panel_unit"] = fold_report(c, u, mapping, distinct is not None)
    rp.write_text(json.dumps(report, indent=2) + "\n")
    return u


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fold-only", action="store_true",
                    help="fold the existing frozen fiber_share.csv into panel units; no rebuild")
    ap.add_argument("--no-distinct", action="store_true", help="with --fold-only: sum counts, skip the block-level recount")
    args = ap.parse_args()
    if args.fold_only:
        national = json.loads((FROZEN / "instrument_report.json").read_text())["national_fiber_blocks_contiguous"]
        u = run_fold(pd.read_csv(FROZEN / "fiber_share.csv"), national, with_distinct=not args.no_distinct)
        print(f"wrote {len(u)} unit rows")
        return 0
    terr = load_territories()
    fiber = fiber_sets()
    national = {f: int(len(v)) for f, v in fiber.items()}

    counts = []
    n_blocks_all = n_blocks_placed = 0
    unmatched = {f: 0 for f in FILINGS}
    seen = {f: 0 for f in FILINGS}
    for fips, st in FIPS.items():
        if fips in NOT_CONTIGUOUS:
            continue
        x = pd.read_csv(RAW / "lodes_xwalk" / f"{st.lower()}_xwalk.csv.gz",
                        usecols=["tabblk2010", "blklatdd", "blklondd"], dtype={"tabblk2010": "int64"})
        n_blocks_all += len(x)
        pts = gpd.GeoDataFrame(x[["tabblk2010"]], geometry=gpd.points_from_xy(x.blklondd, x.blklatdd), crs=4326)
        j = gpd.sjoin(pts, terr, predicate="within", how="inner")[["tabblk2010", "utility_id_eia"]]
        n_blocks_placed += j.tabblk2010.nunique()
        j["state"] = st
        for f in FILINGS:
            in_state = fiber[f][(fiber[f] // 10**13) == int(fips)]
            seen[f] += len(in_state)
            unmatched[f] += int((~np.isin(in_state, x.tabblk2010.values)).sum())
            j[f] = np.isin(j.tabblk2010.values, in_state)
        g = j.groupby(["utility_id_eia", "state"]).agg(n_blocks=("tabblk2010", "size"), **{f: (f, "sum") for f in FILINGS})
        counts.append(g.reset_index())
        print(f"  {st}: {len(x):,} blocks, {len(j):,} block-territory pairs", flush=True)

    c = pd.concat(counts, ignore_index=True)
    for f in FILINGS:
        c = c.rename(columns={f: f"fiber_blocks_{f}"})
        c[f"share_{f}"] = c[f"fiber_blocks_{f}"] / national[f]
    c["fiber_share_dec"] = c[[f"share_{f}" for f in DEC]].mean(axis=1)     # primary (D-15)
    c["fiber_share_jun"] = c[[f"share_{f}" for f in JUN]].mean(axis=1)
    c["fiber_share_all6"] = c[[f"share_{f}" for f in FILINGS]].mean(axis=1)
    c["pct_of_own_blocks_with_fiber_2019_12"] = c["fiber_blocks_2019-12"] / c.n_blocks
    c = c.sort_values(["utility_id_eia", "state"]).reset_index(drop=True)

    spend = spending()

    # ---- checks against the paper's printed tables -----------------------
    q = panel.load_quantities()
    yrs = q[q.year.between(2015, 2024)].groupby(["utility_id_eia", "state"]).year.nunique()
    balanced = yrs[yrs == 10].reset_index()[["utility_id_eia", "state"]]
    in_panel = balanced.merge(c, on=["utility_id_eia", "state"], how="left")
    s = in_panel.fiber_share_dec.fillna(0.0) * 100  # percent, as in Table S4
    overlap = float(c.fiber_share_dec.sum())  # how many territories the average fiber block falls in

    def stats(v: pd.Series) -> dict:
        return {"n": int(len(v)), "mean": round(float(v.mean()), 4), "sd": round(float(v.std()), 3),
                "min": round(float(v.min()), 6), "p10": round(float(v.quantile(0.1)), 6),
                "median": round(float(v.median()), 4), "p90": round(float(v.quantile(0.9)), 3),
                "max": round(float(v.max()), 2)}

    sp = spend.set_index("year")
    report = {
        "national_fiber_blocks_contiguous": national,
        "fcc_fiber_blocks_not_in_census_block_file": {f: f"{unmatched[f]} of {seen[f]}" for f in FILINGS},
        "census_blocks_contiguous": int(n_blocks_all),
        "census_blocks_inside_any_territory": int(n_blocks_placed),
        "utility_states_with_blocks": int(len(c)),
        "utility_states_with_fiber_2019_12": int((c["fiber_blocks_2019-12"] > 0).sum()),
        "sum_of_shares_dec": round(float(c.fiber_share_dec.sum()), 3),
        "correlation_between_definitions": {
            "dec_vs_jun": round(float(np.corrcoef(c.fiber_share_dec, c.fiber_share_jun)[0, 1]), 5),
            "dec_vs_all6": round(float(np.corrcoef(c.fiber_share_dec, c.fiber_share_all6)[0, 1]), 5),
        },
        "table_S4_check_pct_of_national_fiber_blocks": {
            "paper": PAPER_S4_PCT,
            "paper_sample_utility_states": PAPER_N_UTILITY_STATES,
            "paper_shares_sum_to_pct": round(PAPER_S4_PCT["mean"] * PAPER_N_UTILITY_STATES, 1),
            "ours_balanced_panel_2015_2024": stats(s),
            "ours_balanced_panel_shares_sum_to_pct": round(float(s.sum()), 1),
            # Second reading of the paper's wording: the national total is the sum of every
            # territory's count, so a block inside two territories is counted twice in it.
            "ours_balanced_panel_if_national_total_sums_territory_counts": stats(s / overlap),
            "ours_balanced_panel_sum_under_that_reading_pct": round(float(s.sum() / overlap), 1),
            "ours_all_utility_states_with_blocks": stats(c.fiber_share_dec * 100),
            "panel_utility_states_without_a_polygon": int(in_panel.n_blocks.isna().sum()),
        },
        "table_S3_check_real_2024_bn": {
            str(y): {"paper": PAPER_S3_REAL_2024_BN[y], "ours": round(float(sp.real_2024_musd[y]) / 1000, 2),
                     "ours_nominal": round(float(sp.nominal_musd[y]) / 1000, 2)}
            for y in PAPER_S3_REAL_2024_BN if y in sp.index},
    }

    INTERIM.mkdir(parents=True, exist_ok=True)
    c.to_parquet(INTERIM / "fiber_share.parquet", index=False)
    keep = ["utility_id_eia", "state", "n_blocks"] + [f"fiber_blocks_{f}" for f in FILINGS] + \
           ["fiber_share_dec", "fiber_share_jun", "fiber_share_all6"]
    c[keep].to_csv(FROZEN / "fiber_share.csv", index=False, float_format="%.10g")
    spend.to_csv(FROZEN / "dc_construction_spending.csv", index=False, float_format="%.6g")
    (FROZEN / "instrument_report.json").write_text(json.dumps(report, indent=2) + "\n")
    run_fold(c[keep], national)
    print(json.dumps(json.loads((FROZEN / "instrument_report.json").read_text()), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
