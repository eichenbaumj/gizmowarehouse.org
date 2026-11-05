"""Stage 11: the citywide context the rewritten storyboard needs.

  output/density.json        per-cell denominators (2020 residents, 2022 LEHD jobs) and the density-adjusted
                             ranks for 2024-25 under residents, jobs, residents+jobs
  output/precincts_1990.json 1990 / 1993 / 1998 / 2001 / 2025 per precinct from the 77 CompStat PDFs
                             (robbery, felony assault, murder), plus the published 2000-2024 by-precinct table
  output/improvers.json      cells with the biggest violent-complaint declines 2006-08 -> 2023-25, and the
                             top-20%-of-cells concentration facts
  output/timelapse.json      every complaint within 400 m in the chosen month, with hour/day, class, zone,
                             and a block-face jitter seed (coordinates stay NYPD-rounded)
  output/sankey.json         place (premise group x zone) -> class flows, 2024-25, within 400 m
"""
from __future__ import annotations

import gzip
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib import geo  # noqa: E402
from lib.dq import clean_nan  # noqa: E402

BORO_FIPS = {"36005": "Bronx", "36047": "Brooklyn", "36061": "Manhattan", "36081": "Queens", "36085": "Staten Island"}
CENSUS_DIR = config.CRIME_PIPELINE / "data" / "reference" / "census2020"
TABBLOCK_DIR = config.CRIME_PIPELINE / "data" / "reference" / "blocks2020" / "tabblock"
LODES = config.RAW_DIR / "lodes" / "ny_wac_S000_JT00_2022.csv.gz"
PDF_DIR = config.RAW_DIR / "precinct_pdfs"
TIMELAPSE_YEAR, TIMELAPSE_MONTH = 2025, 10
MIN_EARLY_PER_YEAR = 30


# ---------------------------------------------------------------- density
def block_centroids() -> pd.DataFrame:
    import geopandas as gpd
    parts = []
    for fips in BORO_FIPS:
        z = TABBLOCK_DIR / f"tl_2020_{fips}_tabblock20.zip"
        g = gpd.read_file(f"zip://{z}")
        g = g.to_crs(4326)
        c = g.geometry.representative_point()
        parts.append(pd.DataFrame({"geoid": g["GEOID20"].astype(str), "lat": c.y.values, "lon": c.x.values, "boro": BORO_FIPS[fips]}))
    return pd.concat(parts, ignore_index=True)


def density() -> dict:
    blocks = block_centroids()
    pop = {}
    for fips in BORO_FIPS:
        pop.update(json.loads((CENSUS_DIR / f"pl2020_block_{fips}.json").read_text()))
    blocks["pop"] = blocks["geoid"].map(pop).fillna(0).astype(int)
    with gzip.open(LODES, "rt") as f:
        wac = pd.read_csv(f, usecols=["w_geocode", "C000"], dtype={"w_geocode": str})
    wac = wac[wac["w_geocode"].str[:5].isin(BORO_FIPS)]
    blocks["jobs"] = blocks["geoid"].map(wac.set_index("w_geocode")["C000"]).fillna(0).astype(int)
    ids, off = geo.assign_cells(blocks["lon"].to_numpy(), blocks["lat"].to_numpy())
    blocks["cell_id"] = ids
    by = blocks[blocks["cell_id"].notna()].groupby("cell_id")[["pop", "jobs"]].sum()
    panel = pd.read_parquet(config.OUT_DIR / "cell_year_class.parquet")
    rec = panel[panel["year"].isin(config.RECENT_YEARS)].groupby("cell_id")["n"].sum()
    df = pd.DataFrame({"count_2024_25": rec}).join(by, how="left").fillna(0)
    df["pop_jobs"] = df["pop"] + df["jobs"]
    names = geo.cell_name_map()
    out = {"snapshot": config.SNAPSHOT_DATE, "sources": {"residents": "2020 Census PL 94-171 block population", "jobs": "LEHD LODES 8 WAC 2022, all jobs (C000), workplace block"},
           "min_denominator": 500, "ranks": {}, "this_cell": {}, "top20": {}}
    cid = config.CELL_ID
    out["this_cell"] = {"count_2024_25": int(df.loc[cid, "count_2024_25"]), "residents": int(df.loc[cid, "pop"]), "jobs": int(df.loc[cid, "jobs"])}
    for key, col in (("residents", "pop"), ("jobs", "jobs"), ("residents_plus_jobs", "pop_jobs")):
        sub = df[df[col] >= out["min_denominator"]].copy()
        sub["rate"] = sub["count_2024_25"] / sub[col] * 1000 / 2  # per 1,000 per year
        sub = sub.sort_values("rate", ascending=False)
        rank = int(list(sub.index).index(cid)) + 1 if cid in sub.index else None
        out["ranks"][key] = {"rank": rank, "n_cells": int(len(sub)), "rate_per_1000_per_year": round(float(sub.loc[cid, "rate"]), 2) if cid in sub.index else None,
                             "denominator": int(df.loc[cid, col])}
        out["top20"][key] = [{"cell_id": c, "name": names.get(c, c), "rate": round(float(r.rate), 2), "count_2024_25": int(r.count_2024_25), "denominator": int(r[col])} for c, r in sub.head(20).iterrows()]
    out["count_rank"] = int(list(df.sort_values("count_2024_25", ascending=False).index).index(cid)) + 1
    df.reset_index().rename(columns={"index": "cell_id"}).to_csv(config.OUT_DIR / "cell_density.csv", index=False)
    write_grid_rates(df, out["min_denominator"])
    return out


def write_grid_rates(df: pd.DataFrame, min_pop: int) -> None:
    """Add residents, jobs and the per-resident rate and rank to public grid.geojson (written by stage 08), for the
    citywide per-resident map. Rate is violent complaints per 1,000 residents per year over 2024-25; cells under
    `min_pop` residents get null so empty commercial cells cannot dominate the map."""
    path = config.PUBLIC_DATA_DIR / "grid.geojson"
    g = json.loads(path.read_text())
    elig = df[df["pop"] >= min_pop].copy()
    elig["rate"] = elig["count_2024_25"] / elig["pop"] * 1000 / 2
    elig = elig.sort_values("rate", ascending=False)
    rank = {c: i + 1 for i, c in enumerate(elig.index)}
    for f in g["features"]:
        cid = f["properties"]["cell_id"]
        pop = int(df.loc[cid, "pop"]) if cid in df.index else 0; jobs = int(df.loc[cid, "jobs"]) if cid in df.index else 0
        f["properties"].update({"residents": pop, "jobs": jobs,
                                "rate_res": round(float(elig.loc[cid, "rate"]), 2) if cid in elig.index else None,
                                "rank_res": rank.get(cid)})
    g["n_cells_rate_res"] = int(len(elig)); g["min_residents"] = int(min_pop)
    path.write_text(json.dumps(g, separators=(",", ":"), allow_nan=False))
    print(f"grid.geojson: per-resident rate on {len(elig)} cells with {min_pop}+ residents")


# ---------------------------------------------------------------- 1990 precincts
ROW_LABELS = ("Murder", "Rape", "Robbery", "Fel. Assault", "Burglary", "Gr. Larceny", "G.L.A.", "TOTAL")
NUM_RE = re.compile(r"[\d,]+|\*\*\*\.\*|-?\d+\.\d")


def parse_hist_table(hist: str) -> dict:
    """Column-position parse of the Historical Perspective table. The header gives the x position of
    each year; every numeric token in a data row is assigned to the nearest year column, so a precinct
    with no 1990 column (the 33rd, created 1994) yields None for 1990 instead of shifted values, and a
    blank latest-year cell followed by "***.*" change columns reads as 0."""
    lines = hist.splitlines()
    hdr = next((l for l in lines if re.search(r"\b(19\d\d)\b.*\b(20\d\d)\b", l) and "Chg" not in l), None)
    if not hdr:
        return {}
    cols = [(int(m.group()), m.start() + len(m.group()) / 2) for m in re.finditer(r"\b(19|20)\d\d\b", hdr)]
    years = [c[0] for c in cols]
    out = {}
    for l in lines:
        m = re.match(r"^\s*(" + "|".join(re.escape(x) for x in ROW_LABELS) + r")\s", l)
        if not m:
            continue
        label = m.group(1)
        vals: dict = {y: None for y in years}
        for t in re.finditer(r"[\d,]+", l[m.end():]):
            x = m.end() + t.start() + len(t.group()) / 2
            yr = min(cols, key=lambda c: abs(c[1] - x))
            if abs(yr[1] - x) <= 7:
                vals[yr[0]] = int(t.group().replace(",", ""))
        # the latest year prints a blank for zero (its change columns show ***.*)
        if vals.get(years[-1]) is None and "***.*" in l:
            vals[years[-1]] = 0
        out[label] = {str(y): v for y, v in vals.items()}
    return out


def precincts_1990() -> dict:
    out = {"snapshot": config.SNAPSHOT_DATE, "source": "NYPD CompStat precinct reports, Historical Perspective table (calendar years 1990, 1993, 1998, 2001, 2025)", "precincts": {}}
    for p in sorted(PDF_DIR.glob("cs-en-us-*pct.pdf")):
        if p.stat().st_size < 10_000:
            continue
        pct = int(p.stem.split("-")[-1].replace("pct", ""))
        txt = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
        if "Historical Perspective" not in txt:
            continue
        hist = txt.split("Historical Perspective", 1)[1]
        rows = parse_hist_table(hist)
        if rows:
            out["precincts"][str(pct)] = rows
    # summaries for the prose: violent (murder + robbery + felony assault) change 1990 -> latest, by precinct
    summ = []
    for pct, rows in out["precincts"].items():
        try:
            y0, y1 = "1990", "2025"
            if any(rows[k][y] is None for k in ("Murder", "Robbery", "Fel. Assault") for y in (y0, y1)):
                summ.append({"precinct": int(pct), "violent_1990": None, "violent_2025": None, "change_pct": None, "robbery_change_pct": None,
                             "fel_assault_change_pct": None, "murder_1990": rows["Murder"][y0], "murder_2025": rows["Murder"][y1], "note": "no 1990 column in NYPD's table"})
                continue
            v0 = rows["Murder"][y0] + rows["Robbery"][y0] + rows["Fel. Assault"][y0]
            v1 = rows["Murder"][y1] + rows["Robbery"][y1] + rows["Fel. Assault"][y1]
            summ.append({"precinct": int(pct), "violent_1990": v0, "violent_2025": v1, "change_pct": round((v1 / v0 - 1) * 100, 1) if v0 else None,
                         "robbery_change_pct": round((rows["Robbery"][y1] / rows["Robbery"][y0] - 1) * 100, 1) if rows["Robbery"][y0] else None,
                         "fel_assault_change_pct": round((rows["Fel. Assault"][y1] / rows["Fel. Assault"][y0] - 1) * 100, 1) if rows["Fel. Assault"][y0] else None,
                         "murder_1990": rows["Murder"][y0], "murder_2025": rows["Murder"][y1]})
        except KeyError:
            continue
    names = pd.read_csv(config.CROSSWALKS / "precinct_names.csv", dtype={"precinct": int})
    nm = names.set_index("precinct")
    for r in summ:
        if r["precinct"] in nm.index:
            r["borough"] = nm.loc[r["precinct"], "borough"]; r["neighborhoods"] = nm.loc[r["precinct"], "neighborhoods"]
    out["summary"] = sorted(summ, key=lambda r: (r["change_pct"] if r["change_pct"] is not None else 1e9))
    out["names_note"] = "Neighborhood labels are approximate descriptions of each precinct's coverage, for finding your precinct; boundaries are NYPD's."
    out["n_precincts"] = len(out["precincts"])
    # Citywide 1990 = sum of the precinct tables. The 33rd (1994) and 121st (2013) have no 1990 column; their
    # ground sat inside older precincts then, so nothing is lost. Both sums must equal NYPD's published citywide
    # totals (2,262 murders, 100,280 robberies), which catches any drift in the PDF parse.
    sums_1990 = {k: sum(r[k]["1990"] for r in out["precincts"].values() if r.get(k, {}).get("1990") is not None) for k in ("Murder", "Robbery")}
    assert sums_1990 == {"Murder": 2262, "Robbery": 100280}, f"1990 precinct sums drifted from NYPD citywide totals: {sums_1990}"
    out["city"] = {"murder_1990": sums_1990["Murder"], "robbery_1990": sums_1990["Robbery"], "murder_2025": 305,
                   "source": "1990: sum of NYPD CompStat precinct Historical Perspective tables, equal to NYPD's citywide totals; 2025: NYPD year-end release"}
    tbl = PDF_DIR / "seven-major-by-precinct-2000-2024.pdf"
    if tbl.exists() and tbl.stat().st_size > 10_000:
        out["table_2000_2024_pdf"] = str(tbl.name)
    write_precinct_geojson(summ)
    return out


def write_precinct_geojson(summ: list[dict]) -> None:
    """precincts.geojson: NYPD precinct polygons (simplified to ~5 m) carrying the 1990 -> 2025 summary, for the
    clickable choropleth. Precincts without a 1990 line keep null change fields."""
    import geopandas as gpd
    g = geo.read_precincts()
    g["geometry"] = g.geometry.simplify(0.00005)
    by = {r["precinct"]: r for r in summ}
    feats = []
    keys = ("violent_1990", "violent_2025", "change_pct", "robbery_change_pct", "fel_assault_change_pct", "murder_1990", "murder_2025", "borough", "neighborhoods")
    for _, row in g.iterrows():
        pct = int(row["Precinct"]); r = by.get(pct, {})
        props = {"precinct": pct, **{k: r.get(k) for k in keys}}
        feats.append({"type": "Feature", "geometry": json.loads(gpd.GeoSeries([row.geometry]).to_json())["features"][0]["geometry"], "properties": props})
    fc = {"type": "FeatureCollection", "n": len(feats), "features": feats}
    out = config.PUBLIC_DATA_DIR / "precincts.geojson"
    out.write_text(json.dumps(fc, separators=(",", ":"), allow_nan=False))
    print(f"precincts.geojson: {len(feats)} polygons, {out.stat().st_size / 1e6:.2f} MB")


# ---------------------------------------------------------------- improvers + concentration
FAMILIES = {"robbery": ("street_robbery", "retail_robbery"), "felony_assault": ("other_assault", "officer_assault"), "homicide": ("homicide",)}
Y0, Y1 = config.CHANGE_YEAR_EARLY, config.CHANGE_YEAR_LATE
W0, W1 = config.CHANGE_WINDOW_EARLY, config.CHANGE_WINDOW_LATE


def _pct(late: float, early: float) -> float | None:
    return round(float(late / early * 100 - 100), 1) if early else None


def city_change_by_family(panel: pd.DataFrame) -> dict:
    """Citywide change, Y0 -> Y1 single years, for robbery, felony assault and homicide separately."""
    byc = panel.groupby(["year", "cls"])["n"].sum().unstack(fill_value=0)
    out = {}
    for fam, classes in FAMILIES.items():
        ser = byc[list(classes)].sum(axis=1)
        out[fam] = {"early": int(ser.loc[Y0]), "late": int(ser.loc[Y1]), "change_pct": _pct(ser.loc[Y1], ser.loc[Y0])}
    return out


def cell_area_names() -> dict[str, str]:
    """cell_id -> approximate area name: the first neighborhood listed (crosswalks/precinct_names.csv) for the
    precinct NYPD assigns most of the cell's complaints to. Uses the complaints' own precinct field rather than
    polygon containment, so gaps in the precinct geojson cannot leave a cell unnamed."""
    v = pd.read_parquet(config.OUT_DIR / "violent_citywide.parquet", columns=["cell_id", "precinct_field"])
    v = v.dropna(subset=["cell_id", "precinct_field"])
    modal = v.groupby("cell_id")["precinct_field"].agg(lambda x: int(x.value_counts().idxmax()))
    nm = pd.read_csv(config.CROSSWALKS / "precinct_names.csv", dtype={"precinct": int}).set_index("precinct")["neighborhoods"]
    return {cid: str(nm.loc[p]).split(";")[0].strip() for cid, p in modal.items() if p in nm.index}


def _cell_frame(panel: pd.DataFrame) -> pd.DataFrame:
    """Per cell: single-year endpoints (the printed numbers) and three-year window means (the guard)."""
    tot = panel.groupby(["cell_id", "year"])["n"].sum().unstack(fill_value=0)
    df = pd.DataFrame({"early": tot[Y0], "late": tot[Y1],
                       "early_w": tot[list(range(W0[0], W0[1] + 1))].mean(axis=1), "late_w": tot[list(range(W1[0], W1[1] + 1))].mean(axis=1)})
    df["change_pct"] = (df["late"] / df["early"] - 1) * 100
    df["change_pct_windowed"] = (df["late_w"] / df["early_w"] - 1) * 100
    return df, tot


def improvers() -> dict:
    """Every 'since 2006' figure: single years Y0 vs Y1, codes that existed in Y0 only. Raw (all-code) figures
    ship beside them. A cell is named among the biggest declines only if its three-year-window change also
    clears config.CHANGE_GUARD_DECLINE_PCT, so one freak year cannot put a cell on the list."""
    panel_raw = pd.read_parquet(config.OUT_DIR / "cell_year_class.parquet")
    panel = pd.read_parquet(config.OUT_DIR / "cell_year_class_stable.parquet")
    names = geo.cell_name_map()
    df, tot = _cell_frame(panel)
    raw, tot_raw = _cell_frame(panel_raw)
    eligible = df[df["early"] >= MIN_EARLY_PER_YEAR].sort_values("change_pct")
    guard_ok = eligible["change_pct_windowed"] <= config.CHANGE_GUARD_DECLINE_PCT
    declines = eligible[guard_ok]
    guard_dropped = [{"cell_id": c, "name": names.get(c, c), "change_pct": round(float(r.change_pct), 1), "change_pct_windowed": round(float(r.change_pct_windowed), 1)}
                     for c, r in eligible[~guard_ok].head(15).iterrows() if r.change_pct <= declines["change_pct"].iloc[min(14, len(declines) - 1)]]
    increases = eligible[eligible["change_pct_windowed"] >= 0].sort_values("change_pct", ascending=False)

    areas = cell_area_names()

    def row(c, r):
        return {"cell_id": c, "name": names.get(c, c), "area": areas.get(c), "early": int(r.early), "late": int(r.late), "change_pct": round(float(r.change_pct), 1),
                "change_pct_windowed": round(float(r.change_pct_windowed), 1),
                "early_raw": int(raw.loc[c, "early"]), "late_raw": int(raw.loc[c, "late"]), "change_pct_raw": _pct(raw.loc[c, "late"], raw.loc[c, "early"])}

    # concentration (2024-25, all codes: it describes the present, not a change)
    rec = tot_raw[list(config.RECENT_YEARS)].sum(axis=1).sort_values(ascending=False)
    cum = rec.cumsum() / rec.sum()
    n = len(rec)
    k20 = int(np.ceil(n * 0.2))
    share_top20 = float(rec.head(k20).sum() / rec.sum())
    k_half = int((cum < 0.5).sum()) + 1
    k_20 = int((cum < 0.2).sum()) + 1  # fewest cells that hold a fifth of the city's violent complaints
    # cells of the 84th Precinct (intersecting its polygon), same single-year change
    import geopandas as gpd
    from shapely.geometry import box
    pct = geo.read_precincts()
    p84 = pct[pct["Precinct"] == config.PRECINCT_CORE].geometry.iloc[0]
    cells = geo.deployed_cells()
    in84 = []
    for _, c in cells.iterrows():
        cell_box = box(c["west"], c["south"], c["east"], c["north"])
        inter = cell_box.intersection(p84).area / cell_box.area
        if inter >= 0.25:
            cid = c["id"]
            e = int(df.loc[cid, "early"]) if cid in df.index else 0; l = int(df.loc[cid, "late"]) if cid in df.index else 0
            in84.append({"cell_id": cid, "name": names.get(cid, cid), "share_in_precinct": round(float(inter), 2), "early": e, "late": l,
                         "change_pct": (_pct(l, e) if e >= 5 else None),
                         "lat": round(float((c["south"] + c["north"]) / 2), 6), "lon": round(float((c["west"] + c["east"]) / 2), 6)})
    in84.sort(key=lambda r: (r["change_pct"] if r["change_pct"] is not None else 1e9))
    simp = gpd.GeoSeries([p84], crs=4326).simplify(0.00005).iloc[0]
    (config.PUBLIC_DATA_DIR / "precinct84.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": json.loads(gpd.GeoSeries([simp]).to_json())["features"][0]["geometry"], "properties": {"precinct": 84}}]}, separators=(",", ":")))
    ids84 = [r["cell_id"] for r in in84]
    tot84_e = int(sum(r["early"] for r in in84)); tot84_l = int(sum(r["late"] for r in in84))
    tot84_e_raw = int(raw.loc[ids84, "early"].sum()); tot84_l_raw = int(raw.loc[ids84, "late"].sum())
    city_e = int(tot[Y0].sum()); city_l = int(tot[Y1].sum()); city_e_raw = int(tot_raw[Y0].sum()); city_l_raw = int(tot_raw[Y1].sum())
    excl = panel_raw.groupby("year")["n"].sum() - panel.groupby("year")["n"].sum()
    strang = pd.read_parquet(config.OUT_DIR / "violent_citywide.parquet", columns=["year", "pd_desc"])
    strang_2025 = int(((strang["year"] == Y1) & (strang["pd_desc"] == "STRANGULATION 1ST")).sum())
    out = {"snapshot": config.SNAPSHOT_DATE, "year_early": Y0, "year_late": Y1, "min_early": MIN_EARLY_PER_YEAR,
           "basis": "codes that existed in 2006 (config.STABLE_CODE_EXCLUDE_PD_DESC dropped); single-year endpoints; *_raw = all codes",
           "excluded_codes": sorted(config.STABLE_CODE_EXCLUDE_PD_DESC), "strangulation_law_effective": config.STRANGULATION_LAW_EFFECTIVE,
           "excluded_count": {str(Y0): int(excl.get(Y0, 0)), str(Y1): int(excl.get(Y1, 0))}, "strangulation_2025": strang_2025,
           "guard": {"window_early": list(W0), "window_late": list(W1), "decline_pct": config.CHANGE_GUARD_DECLINE_PCT, "dropped_from_declines": guard_dropped},
           "precinct_84": {"cells": in84, "early": tot84_e, "late": tot84_l, "change_pct": _pct(tot84_l, tot84_e),
                           "early_raw": tot84_e_raw, "late_raw": tot84_l_raw, "change_pct_raw": _pct(tot84_l_raw, tot84_e_raw),
                           "n_down": sum(1 for r in in84 if r["change_pct"] is not None and r["change_pct"] < 0), "n_up": sum(1 for r in in84 if r["change_pct"] is not None and r["change_pct"] > 0),
                           "bounds": [round(x, 5) for x in p84.bounds]},
           "biggest_declines": [row(c, r) for c, r in declines.head(15).iterrows()],
           "biggest_increases": [row(c, r) for c, r in increases.head(15).iterrows()],
           "this_cell": {**row(config.CELL_ID, df.loc[config.CELL_ID]),
                         "rank_among_eligible_by_change": int(list(eligible.index).index(config.CELL_ID)) + 1 if config.CELL_ID in eligible.index else None, "n_eligible": int(len(eligible))},
           "city": {"early": city_e, "late": city_l, "change_pct": _pct(city_l, city_e), "early_raw": city_e_raw, "late_raw": city_l_raw, "change_pct_raw": _pct(city_l_raw, city_e_raw)},
           "city_change_pct": _pct(city_l, city_e),
           "city_change_by_family_pct": city_change_by_family(panel), "city_change_by_family_pct_raw": city_change_by_family(panel_raw),
           "concentration": {"n_cells": n, "n_cells_with_any": int((rec > 0).sum()), "top20pct_cells": k20, "top20pct_share": round(share_top20, 3),
                             "cells_for_half": k_half, "cells_for_half_share_of_all": round(k_half / n, 3),
                             "cells_for_20pct": k_20, "cells_for_20pct_share_of_all": round(k_20 / n, 4),
                             "threshold_count_top20pct": int(rec.iloc[k20 - 1]), "threshold_count_half": int(rec.iloc[k_half - 1])}}
    return out


def timelapse() -> dict:
    c = pd.read_parquet(config.OUT_DIR / "core_incidents.parquet")
    m = c[c["in_core400"] & (c["year"] == TIMELAPSE_YEAR) & (c["month"] == TIMELAPSE_MONTH)].copy()
    m = m[m["violent_primary"] | (m["ky_cd"] == "341") | (m["ky_cd"] == "109") | (m["ky_cd"] == "344")]
    m = m.sort_values(["date", "cmplnt_fr_tm"])
    rng = np.random.default_rng(7)
    rows = []
    for _, r in m.iterrows():
        kind = r["cls"] if r["violent_primary"] else ("petit_larceny" if r["ky_cd"] == "341" else ("grand_larceny" if r["ky_cd"] == "109" else "misd_assault"))
        rows.append({"d": int(r["date"].day), "dow": int(r["dow"]), "h": (int(r["hour"]) if pd.notna(r["hour"]) else None), "default_time": bool(r["default_time"]),
                     "kind": kind, "zone": r["zone"], "lat": round(float(r["lat"]), 6), "lon": round(float(r["lon"]), 6),
                     "premise": r["premise_group"], "jitter": [round(float(rng.uniform(-1, 1)), 3), round(float(rng.uniform(-1, 1)), 3)]})
    counts = {"violent": int(m["violent_primary"].sum()), "petit_larceny": int((m["ky_cd"] == "341").sum()), "grand_larceny": int((m["ky_cd"] == "109").sum()), "misd_assault": int((m["ky_cd"] == "344").sum())}
    return {"snapshot": config.SNAPSHOT_DATE, "year": TIMELAPSE_YEAR, "month": TIMELAPSE_MONTH, "days": 31, "first_dow": int(pd.Timestamp(TIMELAPSE_YEAR, TIMELAPSE_MONTH, 1).dayofweek),
            "radius_m": 400, "counts": counts, "note": "Coordinates are NYPD-rounded points; the jitter seed spreads dots within ~25 m for legibility only.", "rows": rows}


# ---------------------------------------------------------------- sankey
def sankey() -> dict:
    c = pd.read_parquet(config.OUT_DIR / "core_incidents.parquet")
    v = c[c["in_core400"] & c["violent_primary"] & c["year"].isin(config.RECENT_YEARS)].copy()
    def place(r):
        if r["zone"] == "courthouse":
            return "120 Schermerhorn (court and booking)"
        if r["zone"] == "transit":
            return "Subway stations"
        g = r["premise_group"]
        if g in ("chain store", "department store", "clothing store", "drug store", "variety store", "supermarket", "bodega", "fast food", "restaurant", "bank", "commercial building"):
            return "Stores and restaurants"
        if g in ("apartment house", "house", "public housing"):
            return "Apartment buildings"
        if g in ("hotel", "shelter"):
            return "Hotels and shelters"
        if g == "street":
            return "Sidewalk"
        return "Other or unrecorded"
    v["place"] = v.apply(place, axis=1)
    flows = v.groupby(["place", "cls"]).size().reset_index(name="n")
    places = flows.groupby("place")["n"].sum().sort_values(ascending=False)
    return {"snapshot": config.SNAPSHOT_DATE, "window": "2024_25", "footprint": "core400", "total": int(len(v)),
            "places": [{"name": p, "n": int(n)} for p, n in places.items()],
            "classes": [{"name": k, "n": int(x)} for k, x in v.groupby("cls").size().sort_values(ascending=False).items()],
            "flows": [{"place": r.place, "cls": r.cls, "n": int(r.n)} for r in flows.itertuples()]}


def points() -> dict:
    """Every violent complaint citywide in 2024-25 with a coordinate, as compact [lon, lat, class] triples
    for the explorer map's zoomed-in incident layer. Coordinates are NYPD's rounded points (5 dp)."""
    v = pd.read_parquet(config.OUT_DIR / "violent_citywide.parquet", columns=["year", "lat", "lon", "cls", "violent_primary", "has_coord"])
    v = v[v["violent_primary"] & v["has_coord"] & v["year"].isin(config.RECENT_YEARS)]
    classes = config.CLASSES
    idx = {c: i for i, c in enumerate(classes)}
    rows = [[round(float(r.lon), 5), round(float(r.lat), 5), idx.get(r.cls, len(classes))] for r in v.itertuples()]
    return {"snapshot": config.SNAPSHOT_DATE, "window": "2024_25", "classes": classes, "n": len(rows), "note": "NYPD-rounded points; several complaints can share one point", "p": rows}


def main() -> None:
    for name, fn in (("density", density), ("precincts_1990", precincts_1990), ("improvers", improvers), ("timelapse", timelapse), ("sankey", sankey), ("points_2024_25", points)):
        out = fn()
        (config.OUT_DIR / f"{name}.json").write_text(json.dumps(clean_nan(out), indent=1, default=float, allow_nan=False))
        (config.PUBLIC_DATA_DIR / f"{name}.json").write_text(json.dumps(clean_nan(out), separators=(",", ":"), default=float, allow_nan=False))
        print(f"  {name}.json written")
    d = json.loads((config.OUT_DIR / "density.json").read_text()); i = json.loads((config.OUT_DIR / "improvers.json").read_text()); p = json.loads((config.OUT_DIR / "precincts_1990.json").read_text())
    t = json.loads((config.OUT_DIR / "timelapse.json").read_text())
    ctx_path = config.PUBLIC_DATA_DIR / "context.json"
    ctx = json.loads(ctx_path.read_text()) if ctx_path.exists() else {}
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    ordinal = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
    ctx["precincts"] = {"murder_1990": p["city"]["murder_1990"], "murder_2025": p["city"]["murder_2025"], "n": p["n_precincts"], "n_with_change": sum(1 for x in p["summary"] if x["change_pct"] is not None),
                        "most_improved_1": ordinal(p["summary"][0]["precinct"]), "most_improved_2": ordinal(p["summary"][1]["precinct"]), "most_improved_3": ordinal(p["summary"][2]["precinct"]),
                        "pct84_change": p["precincts"].get("84") and next(x["change_pct"] for x in p["summary"] if x["precinct"] == 84),
                        "pct84_robbery_change": next(x["robbery_change_pct"] for x in p["summary"] if x["precinct"] == 84), "pct84_fel_assault_change": next(x["fel_assault_change_pct"] for x in p["summary"] if x["precinct"] == 84)}
    fam = i["city_change_by_family_pct"]; fam_raw = i["city_change_by_family_pct_raw"]
    ctx["improvers"] = {"year_early": i["year_early"], "year_late": i["year_late"],
                        "decline_1": i["biggest_declines"][0]["name"], "decline_2": i["biggest_declines"][1]["name"], "decline_3": i["biggest_declines"][2]["name"],
                        "decline_1_area": i["biggest_declines"][0]["area"], "decline_2_area": i["biggest_declines"][1]["area"], "decline_3_area": i["biggest_declines"][2]["area"],
                        "decline_1_pct_abs": int(round(abs(i["biggest_declines"][0]["change_pct"]))), "decline_2_pct_abs": int(round(abs(i["biggest_declines"][1]["change_pct"]))), "decline_3_pct_abs": int(round(abs(i["biggest_declines"][2]["change_pct"]))),
                        **{f"decline_{k + 1}_{end}": int(i["biggest_declines"][k][end]) for k in range(3) for end in ("early", "late")},
                        "p84_change_pct": int(round(i["precinct_84"]["change_pct"])), "p84_change_pct_raw": int(round(i["precinct_84"]["change_pct_raw"])), "p84_n_down": i["precinct_84"]["n_down"], "p84_n_up": i["precinct_84"]["n_up"],
                        "this_cell_early": i["this_cell"]["early"], "this_cell_late": i["this_cell"]["late"], "this_cell_change_pct": i["this_cell"]["change_pct"],
                        "city_change_pct": i["city"]["change_pct"], "city_change_pct_round": int(round(i["city"]["change_pct"])), "city_change_pct_raw_round": int(round(i["city"]["change_pct_raw"])),
                        "city_robbery_change_pct_abs": int(round(abs(fam["robbery"]["change_pct"]))), "city_fel_assault_change_pct": int(round(fam["felony_assault"]["change_pct"])), "city_fel_assault_change_pct_raw": int(round(fam_raw["felony_assault"]["change_pct"])),
                        "strangulation_2025": i["strangulation_2025"], "excluded_2025": i["excluded_count"][str(i["year_late"])],
                        "top20pct_share": i["concentration"]["top20pct_share"], "top20pct_cells": i["concentration"]["top20pct_cells"], "cells_for_half": i["concentration"]["cells_for_half"], "n_cells": i["concentration"]["n_cells"],
                        "cells_for_20pct": i["concentration"]["cells_for_20pct"], "area_pct_20": round(i["concentration"]["cells_for_20pct_share_of_all"] * 100, 1), "area_pct_half": int(round(i["concentration"]["cells_for_half_share_of_all"] * 100))}
    ctx["density"] = {"rank_residents": d["ranks"]["residents"]["rank"], "rank_jobs": d["ranks"]["jobs"]["rank"], "rank_residents_plus_jobs": d["ranks"]["residents_plus_jobs"]["rank"],
                      "n_cells_residents": d["ranks"]["residents"]["n_cells"], "n_cells_jobs": d["ranks"]["jobs"]["n_cells"], "n_cells_residents_plus_jobs": d["ranks"]["residents_plus_jobs"]["n_cells"],
                      "residents": d["this_cell"]["residents"], "jobs": d["this_cell"]["jobs"],
                      "per_1000_residents": int(round(d["ranks"]["residents"]["rate_per_1000_per_year"])) if d["ranks"]["residents"]["rate_per_1000_per_year"] is not None else None,  # per year
                      "rank_residents_top_pct": round(d["ranks"]["residents"]["rank"] / d["ranks"]["residents"]["n_cells"] * 100, 1)}
    ctx["timelapse"] = {"year": t["year"], "month": t["month"], "month_name": months[t["month"] - 1], **t["counts"]}
    # What grew within 400 m once the courthouse point is set aside: per-type yearly means, 2010s vs 2024-25, read
    # from the same ribbon series the twenty-year chart draws, so the prose and the lines agree.
    rib = json.loads((config.PUBLIC_DATA_DIR / "ribbon.json").read_text())["geos"]["core400_ex_courthouse"]
    yrs = rib["years"]
    def era(vals, lo, hi):
        sel = [v for y, v in zip(yrs, vals) if lo <= int(y) <= hi]
        return sum(sel) / len(sel)
    # The plaza stop (City Point, s06), for the mall paragraph: petit larceny before and after the 2016 opening and
    # the 2024-25 violent mix, from the same stops.json the ledger card reads.
    plaza = next(s for s in json.loads((config.PUBLIC_DATA_DIR / "stops.json").read_text())["stops"] if s["id"] == "s06")
    pl = {int(y): n for y, n in plaza["petit_larceny_by_year"].items()}
    vc = plaza["by_class_2024_25"]
    robberies = vc.get("street_robbery", 0) + vc.get("retail_robbery", 0)
    ph = plaza["peak_hour"]
    ctx["plaza"] = {"pl_pre_max": max(pl.get(y, 0) for y in range(2006, 2016)), "pl_2017": pl.get(2017, 0), "pl_2024": pl.get(2024, 0),
                    "violent_2024_25": plaza["totals"]["2024_25"], "robberies_2024_25": robberies,
                    "shoplift_share_2024_25": plaza["shoplift_origin_share_2024_25"],
                    "assaults_2024_25": vc.get("other_assault", 0) + vc.get("officer_assault", 0), "officer_assaults_2024_25": vc.get("officer_assault", 0),
                    "peak_hour_label": f"{(ph % 12) or 12} {'a.m.' if ph < 12 else 'p.m.'}"}
    assert ctx["plaza"]["violent_2024_25"] == robberies + ctx["plaza"]["assaults_2024_25"] + vc.get("homicide", 0), "plaza violent mix does not sum"
    # Overnight (10pm-6am) shares for the closing recommendations, rounded exactly as the hour-bars card shows them.
    night = json.loads((config.PUBLIC_DATA_DIR / "clock.json").read_text())["night"]
    ctx["clock"] = {"night_core_pct": int(round(night["core400"]["share"] * 100)), "night_city_pct": int(round(night["city"]["share"] * 100))}
    ctx["growth"] = {}
    for k in ("street_robbery", "retail_robbery", "other_assault"):
        base, now = era(rib["by_class"][k], 2010, 2019), era(rib["by_class"][k], 2024, 2025)
        ctx["growth"][f"{k}_2010s"] = int(round(base)); ctx["growth"][f"{k}_2024_25"] = int(round(now)); ctx["growth"][f"{k}_ratio"] = round(now / base, 1)
    facts_path = config.CROSSWALKS / "opening_facts.json"
    if facts_path.exists():
        f = json.loads(facts_path.read_text())
        ctx["opening"] = {k: v["value"] for k, v in f.items()}
        ctx["opening"]["robbery_rank_of"] = f["robbery_rank_2025"]["of"]
        ctx["opening"]["lowest_murder_count"] = f["lowest_murder_year"]["murders"]
        # 1990 counts come from the CompStat precinct tables, not the crosswalk, so the prose and the precinct map share one source
        ctx["opening"]["murders_1990"] = p["city"]["murder_1990"]
        ctx["opening"]["robberies_1990"] = p["city"]["robbery_1990"]
        ctx["opening"]["murders_per_day_1990"] = round(p["city"]["murder_1990"] / 365, 1)
        ctx["opening"]["residents_per_robbery_1990"] = round(f["population_1990"]["value"] / p["city"]["robbery_1990"])
        # 1990 large-city robbery rank (pull_ucr_1990.py). NYC's UCR row must match CompStat and the census, so the
        # rank and the counts in the sentence describe the same numbers.
        ucr = pd.read_csv(config.CROSSWALKS / "ucr_1990_large_city_robbery.csv").sort_values("robbery_per_100k", ascending=False).reset_index(drop=True)
        ny = ucr[ucr.ori == "NY03030"].iloc[0]
        assert (ny.robbery, ny.population) == (p["city"]["robbery_1990"], f["population_1990"]["value"]), f"UCR 1990 NYC row disagrees: {ny.to_dict()}"
        ctx["opening"]["robbery_rank_1990"] = int(ny.name) + 1
        ctx["opening"]["robbery_rank_1990_of"] = len(ucr)
        ctx["opening"]["robbery_rate_1990_per_100k"] = float(ny.robbery_per_100k)
        runner = ucr[ucr.ori != "NY03030"].iloc[0]
        ctx["opening"]["robbery_runner_up_1990"] = runner.agency_name.title()
        ctx["opening"]["robbery_runner_up_1990_per_100k"] = float(runner.robbery_per_100k)
    ctx_path.write_text(json.dumps(clean_nan(ctx), indent=1, allow_nan=False))
    print("density ranks:", d["ranks"], "| count rank", d["count_rank"], "| this cell", d["this_cell"])
    print("concentration:", i["concentration"]); print("this cell change:", i["this_cell"], "| city", i["city_change_pct"])
    print("biggest declines:", [(x["name"], x["change_pct"]) for x in i["biggest_declines"][:6]])
    print("precincts parsed:", p["n_precincts"], "| 84th:", p["precincts"].get("84", {}).get("Fel. Assault"))
    print("stage 11 done")


if __name__ == "__main__":
    main()
