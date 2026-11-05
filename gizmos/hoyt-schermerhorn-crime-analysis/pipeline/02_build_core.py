"""Stage 02: the core incident table.

Reads the per-file bbox caches, dedupes across vintages (main over held), computes distance to the
station, footprint membership (300/400/500 m and the explorer cell), precinct (polygon join and the
recorded addr_pct_cd), zone, class, premise group, and the time/lag flags. Writes
output/core_incidents.parquet (every offense inside the bbox) and output/core_violent.parquet."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib import classify, geo, io  # noqa: E402


def dedupe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rank = df["vintage"].map({"main": 0, "held": 1}).fillna(2)
    df = df.assign(_rank=rank).sort_values(["cmplnt_num", "_rank"])
    before = len(df)
    dups = df.duplicated("cmplnt_num", keep="first")
    report = {"rows_before": int(before), "duplicates_dropped": int(dups.sum()),
              "dup_by_year": df[dups].groupby("file_year").size().to_dict()}
    return df[~dups].drop(columns="_rank"), report


def main() -> None:
    df = io.read_cache("bbox_rows")
    df, dd = dedupe(df)
    f = classify.flags(df)
    df = pd.concat([df, f], axis=1)
    df["dist_m"] = geo.haversine_m(df["lat"], df["lon"], config.STATION_LAT, config.STATION_LON)
    for k, r in config.CORE_RADII_M.items():
        df[f"in_{k}"] = df["dist_m"] <= r
    ids, off = geo.assign_cells(df["lon"].to_numpy(), df["lat"].to_numpy())
    df["cell_id"] = ids
    df["off_lattice"] = off
    df["in_cell"] = df["cell_id"] == config.CELL_ID
    df["precinct_poly"] = geo.precinct_join(df["lat"], df["lon"])
    df["precinct_field"] = pd.to_numeric(df["addr_pct_cd"], errors="coerce")
    d_ct = geo.haversine_m(df["lat"], df["lon"], config.COURTHOUSE_LAT, config.COURTHOUSE_LON)
    df["at_courthouse_point"] = d_ct <= config.COURTHOUSE_MATCH_M
    df["violent_primary"] = df["ky_cd"].isin(config.VIOLENT_PRIMARY)
    df["violent_explorer"] = df["violent_primary"] | df["ky_cd"].isin(config.EXPLORER_EXTRA_HOMICIDE)
    df["cls"] = classify.classify_frame(df)
    df["zone"] = classify.zone_frame(df, df["at_courthouse_point"])
    df["transit"] = classify.is_transit(df)
    df["premise_group"] = classify.premise_group(df["prem_typ_desc"])
    df["point_id"] = df["lat"].round(6).astype(str) + "," + df["lon"].round(6).astype(str)
    df["reported_by_h1_end"] = df["rpt_date"] <= pd.to_datetime(df["year"].astype("Int64").astype(str) + "-" + config.H1_END_MMDD, errors="coerce")
    df["theft_of_services"] = df["pd_desc"].fillna("").str.upper().str.startswith(config.THEFT_OF_SERVICES_PREFIX)
    df = df[df["year"].between(config.YEARS[0], config.YEARS[-1])]
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.OUT_DIR / "core_incidents.parquet", index=False)
    v = df[df["violent_primary"] | df["ky_cd"].isin(config.EXPLORER_EXTRA_HOMICIDE)]
    v.to_parquet(config.OUT_DIR / "core_violent.parquet", index=False)
    core = v[v["violent_primary"] & v[f"in_{config.PRIMARY_FOOTPRINT}"]]
    summary = {
        "dedupe": dd,
        "bbox_rows": int(len(df)),
        "violent_primary_core400": int(len(core)),
        "courthouse_point_core400": int(core["at_courthouse_point"].sum()),
        "off_lattice_in_bbox": int(df["off_lattice"].sum()),
        "precinct_agree": float((df["precinct_poly"] == df["precinct_field"]).mean()),
        "core_majority_precinct": int(core["precinct_poly"].mode().iloc[0]) if len(core) else None,
        "zone_2024_25": core[core["year"].isin(config.RECENT_YEARS)].groupby("zone").size().to_dict(),
        "class_by_year": core.groupby(["year", "cls"]).size().unstack(fill_value=0).to_dict(orient="index"),
    }
    (config.OUT_DIR / "core_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "class_by_year"}, indent=1, default=str))


if __name__ == "__main__":
    main()
