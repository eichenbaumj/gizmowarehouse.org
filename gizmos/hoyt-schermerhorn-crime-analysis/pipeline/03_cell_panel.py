"""Stage 03: every violent complaint citywide 2006-2026 assigned to the explorer lattice.

Outputs
  output/violent_citywide.parquet   one row per violent complaint (primary + explorer extras), with
                                    cell_id, class, flags, zone-ish markers, vintage
  output/cell_year_class.parquet    deployed cell x year x class x count (zero-filled), primary rule
  output/cell_year_class_stable.parquet  same, codes that existed in 2006 only (config.STABLE_CODE_EXCLUDE_PD_DESC)
  output/index_series.parquet       geo x year x class x variant x count for
                                    city / brooklyn / pct84 / cell_40_42 / core400 / core400_ex_courthouse
  output/panel_summary.json         conservation + pins"""
from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib import classify, geo, io  # noqa: E402

GEOS = ["city", "brooklyn", "pct84", "cell_40_42", "core400", "core300", "core500", "core400_ex_courthouse"]


def build_violent() -> tuple[pd.DataFrame, dict]:
    df = io.read_cache("violent_rows")
    rank = df["vintage"].map({"main": 0, "held": 1}).fillna(2)
    df = df.assign(_rank=rank).sort_values(["cmplnt_num", "_rank"])
    dups = df.duplicated("cmplnt_num", keep="first")
    dup_report = {"duplicates_dropped": int(dups.sum())}
    df = df[~dups].drop(columns="_rank").reset_index(drop=True)
    f = classify.flags(df)
    df = pd.concat([df, f], axis=1)
    df = df[df["year"].between(config.YEARS[0], config.YEARS[-1])].reset_index(drop=True)
    df["violent_primary"] = df["ky_cd"].isin(config.VIOLENT_PRIMARY)
    df["violent_explorer"] = df["violent_primary"] | df["ky_cd"].isin(config.EXPLORER_EXTRA_HOMICIDE)
    df["stable_code"] = ~df["pd_desc"].fillna("").isin(config.STABLE_CODE_EXCLUDE_PD_DESC)
    df["cls"] = classify.classify_frame(df)
    df.loc[df["ky_cd"].isin(config.EXPLORER_EXTRA_HOMICIDE), "cls"] = "homicide_negligent"
    df["transit"] = classify.is_transit(df)
    has = df["lat"].notna() & df["lon"].notna() & ~((df["lat"] == 0) & (df["lon"] == 0))
    ids = np.full(len(df), None, dtype=object)
    off = np.ones(len(df), dtype=bool)
    i, o = geo.assign_cells(df.loc[has, "lon"].to_numpy(), df.loc[has, "lat"].to_numpy())
    ids[has.to_numpy()] = i
    off[has.to_numpy()] = o
    df["cell_id"] = ids
    df["off_lattice"] = off
    df["has_coord"] = has
    df["dist_m"] = np.where(has, geo.haversine_m(df["lat"].fillna(0), df["lon"].fillna(0), config.STATION_LAT, config.STATION_LON), np.nan)
    d_ct = np.where(has, geo.haversine_m(df["lat"].fillna(0), df["lon"].fillna(0), config.COURTHOUSE_LAT, config.COURTHOUSE_LON), np.inf)
    df["at_courthouse_point"] = d_ct <= config.COURTHOUSE_MATCH_M
    df["precinct_field"] = pd.to_numeric(df["addr_pct_cd"], errors="coerce")
    df["brooklyn"] = df["boro_nm"].fillna("").str.upper() == "BROOKLYN"
    df["reported_by_h1_end"] = df["rpt_date"] <= pd.to_datetime(df["year"].astype("Int64").astype(str) + "-" + config.H1_END_MMDD, errors="coerce")
    df["h1"] = df["doy"] <= 181
    conserve = geo.conservation(df.loc[has, "cell_id"].to_numpy(), df.loc[has, "off_lattice"].to_numpy())
    rep = {"dedupe": dup_report, "rows": int(len(df)), "no_coord": int((~has).sum()), "conservation": conserve}
    return df, rep


def panel(df: pd.DataFrame, stable_only: bool = False) -> pd.DataFrame:
    dep = geo.deployed_cells()["id"].tolist()
    v = df[df["violent_primary"] & df["cell_id"].notna()]
    if stable_only:
        v = v[v["stable_code"]]
    g = v.groupby(["cell_id", "year", "cls"]).size().rename("n").reset_index()
    full = pd.MultiIndex.from_product([dep, config.YEARS, config.CLASSES], names=["cell_id", "year", "cls"]).to_frame(index=False)
    out = full.merge(g, how="left", on=["cell_id", "year", "cls"]).fillna({"n": 0})
    out["n"] = out["n"].astype(int)
    return out


def geo_mask(df: pd.DataFrame, g: str) -> pd.Series:
    if g == "city":
        return pd.Series(True, index=df.index)
    if g == "brooklyn":
        return df["brooklyn"]
    if g == "pct84":
        return df["precinct_field"] == config.PRECINCT_CORE
    if g == "cell_40_42":
        return df["cell_id"] == config.CELL_ID
    if g in ("core400", "core300", "core500"):
        return df["dist_m"] <= config.CORE_RADII_M[g]
    if g == "core400_ex_courthouse":
        return (df["dist_m"] <= config.CORE_RADII_M["core400"]) & ~df["at_courthouse_point"]
    raise KeyError(g)


def index_series(df: pd.DataFrame) -> pd.DataFrame:
    """variant encodes the definition grid dimensions that matter at the series level:
    rule in {primary, explorer} x transit in {in, out} x default_time in {in, out} x vintage in {main_held, main}
    x window in {full, same_year_report, h1_full, h1_reported}."""
    rows = []
    for g in GEOS:
        m = geo_mask(df, g)
        for rule, transit, dflt, vint, window in product(("primary", "wide"), ("in", "out"), ("in", "out"), ("main_held", "main"), ("full", "same_year_report", "h1_full", "h1_reported")):
            mm = m.copy()
            mm &= df["violent_explorer"] if rule == "wide" else df["violent_primary"]
            if transit == "out":
                mm &= ~df["transit"]
            if dflt == "out":
                mm &= ~df["default_time"]
            if vint == "main":
                mm &= df["vintage"] == "main"
            if window == "same_year_report":
                mm &= df["rpt_date"].dt.year == df["year"]
            elif window == "h1_full":
                mm &= df["h1"]
            elif window == "h1_reported":
                mm &= df["h1"] & df["reported_by_h1_end"]
            sub = df[mm]
            cnt = sub.groupby(["year", "cls"]).size()
            for (y, c), n in cnt.items():
                rows.append((g, rule, transit, dflt, vint, window, int(y), c, int(n)))
            tot = sub.groupby("year").size()
            for y, n in tot.items():
                rows.append((g, rule, transit, dflt, vint, window, int(y), "all", int(n)))
    return pd.DataFrame(rows, columns=["geo", "rule", "transit", "default_time", "vintage", "window", "year", "cls", "n"])


def main() -> None:
    df, rep = build_violent()
    df.to_parquet(config.OUT_DIR / "violent_citywide.parquet", index=False)
    p = panel(df)
    p.to_parquet(config.OUT_DIR / "cell_year_class.parquet", index=False)
    panel(df, stable_only=True).to_parquet(config.OUT_DIR / "cell_year_class_stable.parquet", index=False)
    s = index_series(df)
    s.to_parquet(config.OUT_DIR / "index_series.parquet", index=False)
    pins = {}
    for y in config.PIN_CITY_VIOLENT_EXPLORER:
        ex = df[(df["year"] == y) & df["violent_explorer"] & df["has_coord"]]
        pins[str(y)] = {"wide_rule_with_coords_all_vintages": int(len(ex)),
                        "wide_rule_with_coords_main_only": int((ex["vintage"] == "main").sum()),
                        "pin": config.PIN_CITY_VIOLENT_EXPLORER[y]}
    cell = p[p["cell_id"] == config.CELL_ID].groupby("year")["n"].sum()
    rep["pins"] = pins
    rep["cell_40_42_by_year"] = {int(k): int(v) for k, v in cell.items()}
    rep["deployed_cells"] = int(p["cell_id"].nunique())
    (config.OUT_DIR / "panel_summary.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
