"""Stage 09: public JSON (per DATA_CONTRACT.md) and downloadable CSVs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib import geo
from lib.dq import clean_nan  # noqa: E402

BASE = list(range(config.BASE_YEARS[0], config.BASE_YEARS[1] + 1))
RECENT = list(config.RECENT_YEARS)
YEARS = [str(y) for y in config.YEARS]
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def by_class_year(df: pd.DataFrame) -> dict:
    g = df.groupby(["year", "cls"]).size()
    out = {y: {c: 0 for c in config.CLASSES} for y in YEARS}
    for (y, c), n in g.items():
        if str(int(y)) in out and c in out[str(int(y))]:
            out[str(int(y))][c] = int(n)
    return out


def hour_hist(df: pd.DataFrame) -> list[int]:
    return np.bincount(df["hour"].dropna().astype(int).to_numpy(), minlength=24)[:24].tolist()


def week(df: pd.DataFrame) -> list[list[int]]:
    d = df.dropna(subset=["hour", "dow"])
    m = np.zeros((7, 24), dtype=int)
    for (dw, h), n in d.groupby([d["dow"].astype(int), d["hour"].astype(int)]).size().items():
        m[dw, h] = n
    return m.tolist()


def meta(**extra) -> dict:
    return {"snapshot": config.SNAPSHOT_DATE, "partial_year": config.PARTIAL_YEAR, "partial_through": config.PARTIAL_END,
            "definitions": {"violent": "NYPD ky_cd 101 murder, 105 robbery, 106 felony assault", "core": f"{config.CORE_RADII_M['core400']} m of Hoyt-Schermerhorn station",
                            "coordinates": "NYPD-generalized (midblock or intersection); never an address"}, **extra}


def main() -> None:
    config.PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    core_all = pd.read_parquet(config.OUT_DIR / "core_incidents.parquet")
    v = core_all[core_all["violent_primary"] & core_all["in_core400"]].copy()
    clean = v[~v["default_time"]]
    stats = json.loads((config.OUT_DIR / "stats.json").read_text())
    head = json.loads((config.OUT_DIR / "headlines.json").read_text())["claims"]
    dq = json.loads((config.OUT_DIR / "dq.json").read_text())
    dq_tables = json.loads((config.OUT_DIR / "dq_tables.json").read_text())
    comps = json.loads((config.OUT_DIR / "comparators.json").read_text())
    ladder = json.loads((config.OUT_DIR / "ladder.json").read_text())
    idx = pd.read_parquet(config.OUT_DIR / "index_series.parquet")
    vc = pd.read_parquet(config.OUT_DIR / "violent_citywide.parquet")
    vc = vc[vc["violent_primary"]]
    labels = pd.read_csv(config.CROSSWALKS / "labels.csv")

    # ---------------- stops.json ----------------
    v["pt4"] = v["lat"].round(4).astype(str) + "," + v["lon"].round(4).astype(str)
    v.loc[v["at_courthouse_point"], "pt4"] = "courthouse"
    pl = core_all[(core_all["ky_cd"] == "341") & core_all["in_core400"]].copy()
    pl["pt4"] = pl["lat"].round(4).astype(str) + "," + pl["lon"].round(4).astype(str)
    # misdemeanor assault (ky_cd 344): not in the violent set, but the offense people feel most on a sidewalk
    ma = core_all[(core_all["ky_cd"] == "344") & core_all["in_core400"]].copy()
    ma["pt4"] = ma["lat"].round(4).astype(str) + "," + ma["lon"].round(4).astype(str)
    stops = []
    suppressed_pts = suppressed_n = 0
    for i, (pt, g) in enumerate(sorted(v.groupby("pt4"), key=lambda kv: -len(kv[1]))):
        if len(g) < config.MIN_POINT_N:
            suppressed_pts += 1; suppressed_n += len(g); continue
        lat, lon = float(g["lat"].mean()), float(g["lon"].mean())
        d = geo.haversine_m(labels["lat"].to_numpy(), labels["lon"].to_numpy(), lat, lon)
        j = int(np.argmin(d))
        near = labels.iloc[j]
        zone = g["zone"].mode().iloc[0]
        rec = g[g["year"].isin(RECENT)]
        hh = hour_hist(g[~g["default_time"]])
        rob = rec[rec["ky_cd"] == "105"]
        stops.append({
            "id": f"s{i+1:02d}", "lat": round(lat, 6), "lon": round(lon, 6), "zone": zone,
            "label": (config.COURTHOUSE_ADDRESS if pt == "courthouse" else f"near {near['name']}"),
            "label_status": "verified" if pt == "courthouse" else ("unverified" if d[j] > 60 else near["status"]),
            "nearest_label_m": round(float(d[j])),
            "totals": {"all": int(len(g)), "2024_25": int(len(rec)), "2006_2026": int(len(g))},
            "by_class_year": by_class_year(g), "by_class_2024_25": {c: int((rec["cls"] == c).sum()) for c in config.CLASSES},
            "hour_hist": hour_hist(g), "hour_hist_clean": hh, "week": week(g[~g["default_time"]]),
            "premise_mix_2023_26": g[g["year"] >= 2023]["premise_group"].value_counts().to_dict(),
            "petit_larceny_by_year": ({str(int(y)): int(n) for y, n in pl[pl["pt4"] == pt].groupby("year").size().items()} if pt != "courthouse" else None),
            "misd_assault_by_year": ({str(int(y)): int(n) for y, n in ma[ma["pt4"] == pt].groupby("year").size().items()} if pt != "courthouse" else None),
            "peak_hour": int(np.argmax(hh)) if sum(hh) else None,
            "shoplift_origin_share_2024_25": (round(float(rob["pd_desc"].fillna("").str.contains("SHOPLIFTING").mean()), 3) if len(rob) else None),
            "street_view_url": f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat:.6f},{lon:.6f}",
            "footprint": None,
        })
    zones_out = {}
    for z in config.ZONES:
        g = v[v["zone"] == z]
        gz = g[~g["default_time"]]
        rec = g[g["year"].isin([2023, 2024, 2025, 2026])]
        demo = None
        if len(rec) >= config.DEMOGRAPHIC_MIN_N:
            demo = {"victim_sex": rec["vic_sex"].value_counts(normalize=True).round(3).to_dict(), "victim_age": rec["vic_age_group"].value_counts(normalize=True).round(3).to_dict(),
                    "suspect_sex": rec["susp_sex"].value_counts(normalize=True).round(3).to_dict(), "n": int(len(rec)), "window": "2023_26"}
        zones_out[z] = {"by_class_year": by_class_year(g), "hour_hist": hour_hist(g), "hour_hist_clean": hour_hist(gz), "week": week(gz),
                        "night_share": round(float(gz["night"].mean()), 4) if len(gz) else None, "premise_mix_2023_26": rec["premise_group"].value_counts().to_dict(),
                        "premise_mix_2010_19": g[g["year"].between(2010, 2019)]["premise_group"].value_counts().to_dict(), "demographics": demo}
    (config.PUBLIC_DATA_DIR / "stops.json").write_text(json.dumps(clean_nan(meta(stops=stops, suppressed={"n_points": suppressed_pts, "n_incidents": suppressed_n, "rule": f"fewer than {config.MIN_POINT_N} incidents"}, zones=zones_out)), separators=(",", ":"), allow_nan=False))

    # ---------------- zones.json ----------------
    prim = {"rule": "primary", "transit": "in", "default_time": "in", "vintage": "main_held"}
    def idx_series(geo_, window="full"):
        m = (idx["geo"] == geo_) & (idx["window"] == window)
        for k, val in prim.items():
            m &= idx[k] == val
        s = idx[m]
        return {str(int(y)): {c: int(n) for c, n in grp.set_index("cls")["n"].items()} for y, grp in s.groupby("year")}
    zones_json = meta(by_zone_year_class={z: by_class_year(v[v["zone"] == z]) for z in config.ZONES},
                      footprints={fp: idx_series(fp) for fp in ("core400", "core300", "core500", "cell_40_42", "core400_ex_courthouse")},
                      h1={"full": {}, "reported_by_june_30": {}}, totals_2024_25={z: int((v[v["year"].isin(RECENT)]["zone"] == z).sum()) for z in config.ZONES})
    for y in config.H1_YEARS:
        hy = v[(v["year"] == y) & (v["doy"] <= 181)]
        zones_json["h1"]["full"][str(y)] = {z: int((hy["zone"] == z).sum()) for z in config.ZONES}
        hr = hy[hy["reported_by_h1_end"]]
        zones_json["h1"]["reported_by_june_30"][str(y)] = {z: int((hr["zone"] == z).sum()) for z in config.ZONES}
    (config.PUBLIC_DATA_DIR / "zones.json").write_text(json.dumps(clean_nan(zones_json), separators=(",", ":"), allow_nan=False))

    # ---------------- ladder.json ----------------
    lad = meta(**ladder, hubs=comps["hubs"], this_cell=comps["this_cell"], courthouses=comps["courthouses"], spillover=comps["spillover"], neighbors=comps["neighbors"], percentiles=comps["percentiles"])
    (config.PUBLIC_DATA_DIR / "ladder.json").write_text(json.dumps(clean_nan(lad), separators=(",", ":"), allow_nan=False))

    # ---------------- ribbon.json ----------------
    geos = {}
    for g in ("core400", "cell_40_42", "pct84", "brooklyn", "city", "core400_ex_courthouse"):
        s = idx_series(g)
        geos[g] = {"years": YEARS, "by_class": {c: [s.get(y, {}).get(c, 0) for y in YEARS] for c in config.CLASSES}, "all": [s.get(y, {}).get("all", 0) for y in YEARS], "partial": {"2026": True}}
    index_2010s = {}
    for g, d in geos.items():
        index_2010s[g] = {}
        for key, arr in list(d["by_class"].items()) + [("all", d["all"])]:
            base = np.mean([arr[YEARS.index(str(y))] for y in BASE])
            index_2010s[g][key] = [round(x / base, 3) if base else None for x in arr]
    petit = core_all[(core_all["ky_cd"] == "341") & core_all["in_core400"]].groupby("year").size()
    h8 = head["claim_8"]["reported_by_june_30"]
    ribbon = meta(geos=geos, index_2010s=index_2010s, petit_larceny={"core400": [int(petit.get(int(y), 0)) for y in YEARS], "years": YEARS},
                  h1={"rule": "reported_by_june_30", "panels": {"city": h8["city"], "brooklyn": h8["brooklyn"], "core400": h8["core400"], "street_stores": zones_json["h1"]["reported_by_june_30"] and {y: zones_json["h1"]["reported_by_june_30"][y]["street_stores"] for y in zones_json["h1"]["reported_by_june_30"]},
                                                                 "courthouse": {y: zones_json["h1"]["reported_by_june_30"][y]["courthouse"] for y in zones_json["h1"]["reported_by_june_30"]},
                                                                 "street_robbery": {str(y): int(((v["year"] == y) & (v["doy"] <= 181) & v["reported_by_h1_end"] & (v["cls"] == "street_robbery")).sum()) for y in config.H1_YEARS}}})
    (config.PUBLIC_DATA_DIR / "ribbon.json").write_text(json.dumps(clean_nan(ribbon), separators=(",", ":"), allow_nan=False))

    # ---------------- clock.json ----------------
    def share(h):
        t = sum(h); return [round(x / t, 5) if t else 0 for x in h]
    city_clean = vc[~vc["default_time"]]
    bk = city_clean[city_clean["brooklyn"]]
    hour_share = {"core400": share(hour_hist(v)), "core400_clean": share(hour_hist(clean)), "city": share(hour_hist(vc)), "city_clean": share(hour_hist(city_clean)), "brooklyn": share(hour_hist(bk))}
    weeks = {"core400": week(clean), "city": week(city_clean)}
    for z in config.ZONES:
        hour_share[z] = share(hour_hist(clean[clean["zone"] == z])); weeks[z] = week(clean[clean["zone"] == z])
    for h in comps["hubs"]:
        pass
    clock = meta(hour_share=hour_share, week=weeks, week_max={k: int(np.max(w)) for k, w in weeks.items()}, night=stats["p7_night_bootstrap"],
                 night_gap_pp=stats["p7_night_bootstrap"]["gap_pp_city_minus_core"], default_time_share=dq_tables["default_time_share"],
                 chi_square_vs_city=stats["p6_hour_chi_square"], weekday_chi_square=stats["p8_weekday_chi_square"], clock_ok=bool(head["claim_5"]["publishable"]),
                 hub_night_shares={h["name"]: h["night_share"] for h in comps["hubs"]})
    (config.PUBLIC_DATA_DIR / "clock.json").write_text(json.dumps(clean_nan(clock), separators=(",", ":"), allow_nan=False))

    # ---------------- dq.json + context.json ----------------
    (config.PUBLIC_DATA_DIR / "dq.json").write_text(json.dumps(clean_nan(dq), separators=(",", ":"), allow_nan=False))
    c1 = head["claim_1"]; c3 = head["claim_3"]; c5 = head["claim_5"]; c6 = head["claim_6"]; c7 = head["claim_7"]
    ctx = {"snapshot": config.SNAPSHOT_DATE, "years": {"first": config.YEARS[0], "last": config.YEARS[-1], "partial": config.PARTIAL_YEAR, "partial_through": config.PARTIAL_END},
           "cell": {"id": config.CELL_ID, "n_cells": ladder["n_cells"], "count_2024_25": ladder["primary"]["all"]["count"], "rank_all": c7["ranks"]["all"], "rank_no_officer": c7["ranks"]["no_officer"],
                    "rank_no_officer_no_retail": c7["ranks"]["no_officer_no_retail"], "rank_no_courthouse": ladder["primary"]["no_courthouse"]["rank"], "count_no_courthouse": ladder["primary"]["no_courthouse"]["count"], "times_square_count_2024_25": next(t["count"] for t in ladder["top20"] if t["cell_id"] == config.TIMES_SQUARE_CELL)},
           "core": {"radius_m": 400, "violent_2006_2026": int(len(v)), "courthouse_point_total": int(c6["words"]["count_2006_2026_core400"]) if False else int(sum(c6["by_year"].values())),
                    "courthouse_point_2024_25": int(sum(c6["by_year"][str(y)] for y in RECENT)), "courthouse_point_share_2024_25": c6["primary"]["value"]},
           "night": {"core_share": c5["bootstrap"]["core400"]["share"], "city_share": c5["bootstrap"]["city"]["share"], "gap_pp": c5["bootstrap"]["gap_pp_city_minus_core"]["value"], "gap_ci": c5["bootstrap"]["gap_pp_city_minus_core"]["ci"],
                     "weekday_share_core": round(float(np.sum(np.asarray(weeks["core400"])[:5]) / np.sum(weeks["core400"])), 3), "weekday_share_city": round(float(np.sum(np.asarray(weeks["city"])[:5]) / np.sum(weeks["city"])), 3)},
           "index": {"core_2024_25_vs_2010s": c1["primary"]["value"], "core_ex_courthouse_2024_25_vs_2010s": c1["comparators"]["core_ex_courthouse"], "brooklyn_2024_25_vs_2010s": c1["comparators"]["brooklyn"],
                     "city_2024_25_vs_2010s": c1["comparators"]["city"], "pct84_2024_25_vs_2010s": c1["comparators"]["pct84"]},
           "retail": {"shoplift_robbery_base_per_year": round(np.mean([c3["by_year"][str(y)] for y in range(2012, 2020)]), 1), "shoplift_robbery_2024": c3["by_year"]["2024"], "shoplift_robbery_2025": c3["by_year"]["2025"],
                      "shoplift_code_first_year": c3["code_first_seen"], "petit_larceny_2010s_per_year": round(float(petit.loc[2010:2019].mean())), "petit_larceny_peak_year": int(petit.loc[2006:2025].idxmax()), "petit_larceny_peak": int(petit.loc[2006:2025].max())},
           "street_robbery": {"vs_2010s": head["claim_2"]["primary"]["value"], "min_year_count": min(head["claim_2"]["by_year"].values()), "max_year_count": max(head["claim_2"]["by_year"].values()), "publishable": head["claim_2"]["publishable"]},
           "h1": {"rule": "reported_by_june_30", **{k: h8[k] for k in ("core400", "city", "brooklyn", "core400_ex_courthouse")}, "courthouse": {y: zones_json["h1"]["reported_by_june_30"][y]["courthouse"] for y in zones_json["h1"]["reported_by_june_30"]},
                  "street_stores": {y: zones_json["h1"]["reported_by_june_30"][y]["street_stores"] for y in zones_json["h1"]["reported_by_june_30"]}},
           "words": {cid: c["primary"]["words"] for cid, c in head.items()}, "publishable": {cid: c["publishable"] for cid, c in head.items()}}
    # Stage 11 adds its own blocks (opening, precincts, improvers, density, timelapse) to this file; keep
    # them on a partial rerun so the page's tokens never go dark between stages 09 and 11.
    ctx_path = config.PUBLIC_DATA_DIR / "context.json"
    if ctx_path.exists():
        prev = json.loads(ctx_path.read_text())
        for k in config.CONTEXT_STAGE11_BLOCKS:
            if k in prev and k not in ctx:
                ctx[k] = prev[k]
    ctx_path.write_text(json.dumps(clean_nan(ctx), indent=1, allow_nan=False))

    # ---------------- downloads ----------------
    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    def write_csv(name: str, df: pd.DataFrame) -> None:
        p = config.ASSETS_DIR / f"{config.ASSET_PREFIX}{name}.csv"
        with open(p, "w") as f:
            f.write(config.CSV_HEADER_COMMENT + "\n")
            df.to_csv(f, index=False)
        print(f"  wrote {p.name}: {len(df):,} rows, {p.stat().st_size / 1e6:.1f} MB")
    keep_ky = config.VIOLENT_PRIMARY | config.CONTEXT_KY | {"341", "109"}
    dl = core_all[(core_all["in_core500"]) & (core_all["ky_cd"].isin(keep_ky) | core_all["theft_of_services"])].copy()
    dl["date"] = dl["date"].dt.strftime("%Y-%m-%d")
    cols = ["cmplnt_num", "date", "cmplnt_fr_tm", "year", "hour", "dow", "ky_cd", "ofns_desc", "pd_cd", "pd_desc", "law_cat_cd", "crm_atpt_cptd_cd", "prem_typ_desc", "loc_of_occur_desc",
            "juris_desc", "lat", "lon", "dist_m", "cell_id", "zone", "cls", "point_id", "default_time", "lag_days", "vintage", "reported_by_h1_end"]
    dl = dl[cols].rename(columns={"cmplnt_fr_tm": "time", "cls": "class"})
    dl["dist_m"] = dl["dist_m"].round(0)
    dl.loc[~dl["ky_cd"].isin(config.VIOLENT_PRIMARY), "class"] = "not_violent"
    assert not any(c in dl.columns for c in config.DROP_FROM_DOWNLOADS)
    write_csv("core-incidents", dl.sort_values(["date", "time"]))
    write_csv("yearly-series", idx.sort_values(["geo", "rule", "transit", "default_time", "vintage", "window", "year", "cls"]))
    panel = pd.read_csv(config.OUT_DIR / "cell_change_panel.csv")
    write_csv("cell-ranking", panel)
    rows = []
    for t in dq["tests"]:
        rows.append({"id": t["id"], "group": t["group"], "title": t["title"], "status": t["status"], "threshold": json.dumps(t["threshold"]), "reading": t["reading"],
                     "affects": ";".join(t["affects"]), "footnote": t["footnote"] or "", "value": json.dumps(t["value"], default=str)[:2000]})
    write_csv("dq-audit", pd.DataFrame(rows))
    write_bundle([f"{config.ASSET_PREFIX}{n}.csv" for n in ("core-incidents", "yearly-series", "cell-ranking", "dq-audit")], len(dq["tests"]))
    sizes = {p.name: p.stat().st_size for p in config.PUBLIC_DATA_DIR.iterdir()}
    print("stage 09 done:", {k: f"{s / 1e3:.0f} KB" for k, s in sizes.items()})


def write_bundle(csv_names: list[str], n_dq_tests: int) -> None:
    """One zip with the four CSVs and a README (what each file is, every column, definitions, caveats, source,
    terms). The README is generated here so it can never drift from the files beside it."""
    import zipfile
    cols = {}
    for n in csv_names:
        with open(config.ASSETS_DIR / n) as f:
            f.readline(); cols[n] = f.readline().strip().split(",")
    core, yearly, cells, dq = csv_names
    dd = {
        "cmplnt_num": "NYPD complaint id (unique per incident)", "date": "date the incident began (cmplnt_fr_dt)", "time": "time it began (cmplnt_fr_tm; 00:00 and 12:00 are often placeholders, see default_time)",
        "year": "year of date", "hour": "hour of time, 0 to 23", "dow": "weekday, 0 = Monday", "ky_cd": "NYPD offense class code (101 murder, 105 robbery, 106 felony assault, 341 petit larceny, 109 grand larceny, 344 misdemeanor assault, ...)",
        "ofns_desc": "offense description for ky_cd", "pd_cd": "NYPD internal classification code", "pd_desc": "description for pd_cd (e.g. ROBBERY, BEGAN AS SHOPLIFTING)",
        "law_cat_cd": "FELONY, MISDEMEANOR or VIOLATION", "crm_atpt_cptd_cd": "COMPLETED or ATTEMPTED", "prem_typ_desc": "premise type as recorded (STREET, CHAIN STORE, ...)",
        "loc_of_occur_desc": "INSIDE, FRONT OF, OPPOSITE OF, REAR OF (often blank)", "juris_desc": "responding jurisdiction (NYPD, transit, housing)",
        "lat": "latitude as published by NYPD, rounded to a midblock or intersection", "lon": "longitude, same", "dist_m": "meters from the Hoyt-Schermerhorn station point",
        "cell_id": "id of the 0.33-mile map cell the point falls in", "zone": "street_stores, courthouse (within 15 m of 120 Schermerhorn), or transit (station footprints)",
        "class": "street_robbery, retail_robbery (began as shoplifting or in a store), other_assault, officer_assault, homicide, or not_violent",
        "point_id": "id of the rounded point (all complaints at identical coordinates share one)", "default_time": "true when the time is a placeholder (midnight or noon)",
        "lag_days": "days between the incident date and the report date", "vintage": "main (the current Open Data files) or held (late-reported 2025 rows from an earlier pull)",
        "reported_by_h1_end": "true when the report date is on or before June 30 of the incident year (used for first-half comparisons)",
        "geo": "core400 (within 400 m of the station), core300, core500, core400_ex_courthouse, cell_40_42, pct84, brooklyn, city", "rule": "primary (ky_cd 101/105/106) or wide (adds negligent homicide 102/103)",
        "transit": "in = complaints on station footprints included; out = excluded", "window": "full year, same_year_report, h1_full (Jan to Jun), or h1_reported (Jan to Jun, reported by June 30)",
        "cls": "offense class (see class above; all = every class)", "n": "count of complaints", "base": "average violent complaints per year, 2010 to 2019", "recent": "violent complaints, 2024 and 2025 combined",
        "ratio": "recent per year divided by base", "name": "nearest intersection, for finding the cell", "id": "test id", "group": "test family", "title": "what the test checks",
        "status": "pass, warn, report, kill, fail or skipped", "threshold": "the pass threshold, as JSON", "reading": "plain-language result", "affects": "which of the piece's claims the test guards", "footnote": "the caveat the page prints when the test warns", "value": "the measured value, as JSON",
    }
    def section(fn, blurb):
        lines = [f"### {fn}", "", blurb, "", "| column | meaning |", "|---|---|"]
        for c in cols[fn]: lines.append(f"| `{c}` | {dd.get(c, '')} |")
        return "\n".join(lines)
    readme = f"""# The Trouble With Hoyt-Schermerhorn: data bundle

Data behind the piece at https://gizmowarehouse.org/gizmo/{config.SLUG}. Snapshot {config.SNAPSHOT_DATE}.
Questions: joe@group17a.com.

## Source

NYPD Complaint Data, Historic (NYC Open Data qgea-i56i) and Year-To-Date (5uac-w243), as published. Every
file is derived from those two datasets. Coordinates are NYPD's: each complaint is placed at a midblock or
intersection point, never an address. Victim and suspect demographic columns are not included. The 2026
file covers January through June only; 2025 includes late-reported rows held from an earlier pull
(vintage = held), so 2025 counts can exceed what a fresh download shows.

## Definitions

- A **complaint** is a crime reported to or recorded by the police, one incident per record. Not a 311 request.
- **Violent** means ky_cd 101 (murder), 105 (robbery) and 106 (felony assault). The four classes split those:
  street robbery, robbery that began as shoplifting or in a store, assault on an officer, and other felony assault.
- **Since 2006** comparisons in the piece use single years (2006 against 2025) and only offense codes that
  existed in 2006; the yearly series here carries every code, and the piece's methods note states both figures.
- **The courthouse point** is every complaint within 15 m of 120 Schermerhorn Street (Brooklyn Criminal
  Court and Central Booking). Hours there are when complaints were recorded, not when anything happened.
- **Map cells** are the 2,854 cells of a 0.33-mile square grid over the city; cell 40_42 is the one the piece is about.

## Files

{section(core, "Every complaint within 500 m of the Hoyt-Schermerhorn station, 2006 to June 2026: the violent classes plus petit and grand larceny, theft of services, drugs and weapons. The first line is a comment with the snapshot and source.")}

{section(yearly, "Violent complaints per year by place, class and definition variant, so every figure in the piece can be recomputed under every rule.")}

{section(cells, "All 2,854 map cells: average violent complaints per year in the 2010s, the 2024 to 2025 total, and the ratio.")}

{section(dq, f"The data-quality audit the piece was gated on: {n_dq_tests} tests with their status, threshold, reading and the caveat each one adds.")}

## Terms

The underlying data is public under the NYC Open Data terms of use. These derived files may be reused with
attribution to NYPD / NYC Open Data and a link to the piece. No warranty: NYPD revises its files, and a later
download will not match this snapshot exactly.
"""
    out = config.ASSETS_DIR / f"{config.ASSET_PREFIX}data.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(f"{config.SLUG}-data/README.md", readme)
        for n in csv_names: z.write(config.ASSETS_DIR / n, f"{config.SLUG}-data/{n}")
    print(f"  wrote {out.name}: {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
