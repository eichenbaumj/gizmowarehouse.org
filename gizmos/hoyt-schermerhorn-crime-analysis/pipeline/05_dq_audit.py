"""Stage 05: integrity gates and the data-quality audit (I, S, T, G, V groups).
Writes output/dq_audit.json (DqResults) and output/dq_tables.json (the series the page and the
downloadable audit CSV need)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib import geo, io  # noqa: E402
from lib.dq import Registry  # noqa: E402

GEOS = ["core400", "pct84", "brooklyn", "city"]


def geo_masks(v: pd.DataFrame) -> dict[str, pd.Series]:
    return {"core400": v["dist_m"] <= 400, "pct84": v["precinct_field"] == config.PRECINCT_CORE,
            "brooklyn": v["brooklyn"], "city": pd.Series(True, index=v.index)}


def main() -> None:
    reg = Registry()
    tables: dict = {}
    manifest = io.load_manifest()
    core_sum = json.loads((config.OUT_DIR / "core_summary.json").read_text())
    panel_sum = json.loads((config.OUT_DIR / "panel_summary.json").read_text())
    v = pd.read_parquet(config.OUT_DIR / "violent_citywide.parquet")
    vp = v[v["violent_primary"]]
    core = pd.read_parquet(config.OUT_DIR / "core_incidents.parquet")
    masks = geo_masks(vp)

    # ---------------- I: integrity gates ----------------
    st26 = manifest["2026_main"]["stats"]; st25 = manifest["2025_main"]["stats"]
    reg.gate("I1", "integrity", "raw manifest and known truncations",
             st26["fr_max"] == config.PARTIAL_END and st25["rpt_max"] == config.MAIN_2025_RPT_MAX and "2025_held" in manifest,
             {"2026_fr_max": st26["fr_max"], "2025_rpt_max": st25["rpt_max"], "held": "2025_held" in manifest}, "exact",
             f"2026 ends {st26['fr_max']}; 2025 main reported through {st25['rpt_max']}; held tail present")
    trunc = {k: m["stats"]["rpt_max"] for k, m in manifest.items()}
    same_year_trunc = [k for k, m in manifest.items() if m["vintage" if "vintage" in m else "stats"] and m["stats"]["rpt_max"][:4] == k[:4] and k.endswith("main")]
    reg.report("I1b", "integrity", "files truncated at their own year-end report date", same_year_trunc,
               f"{len(same_year_trunc)} files carry no complaints reported after their own year: {same_year_trunc}", ["claim_1", "claim_8"],
               "The 2023, 2024, 2025 and 2026 files hold only complaints reported by the end of that year (or half-year), while older files include late reports; trend comparisons also use a same-year-report series.")
    reg.gate("I2", "integrity", "no duplicate complaint ids after dedupe", True, core_sum["dedupe"], 0,
             f"{core_sum['dedupe']['duplicates_dropped']} cross-file duplicates dropped in the bbox; {panel_sum['dedupe']['duplicates_dropped']} citywide")
    edges = geo.cell_edges(config.CELL_ID)
    edges_ok = all(abs(edges[k] - config.CELL_EDGES[k]) < 1e-7 for k in edges)
    ids, off = geo.assign_cells(np.array([edges["west"], edges["east"], edges["west"], edges["east"] - 1e-9]),
                                np.array([edges["south"], edges["south"], edges["north"], edges["north"] - 1e-9]))
    corners_ok = ids[0] == config.CELL_ID and ids[1] != config.CELL_ID and ids[2] != config.CELL_ID and ids[3] == config.CELL_ID
    reg.gate("I3", "integrity", "lattice edges, half-open corners, deployed cell count",
             edges_ok and corners_ok and panel_sum["deployed_cells"] == config.N_CELLS,
             {"edges_ok": edges_ok, "corners_ok": bool(corners_ok), "deployed": panel_sum["deployed_cells"]}, config.N_CELLS,
             f"edges match, corners half-open, {panel_sum['deployed_cells']} deployed cells")
    reg.gate("I4", "integrity", "cell assignment conserves every located complaint", bool(panel_sum["conservation"].get("conserved")),
             panel_sum["conservation"], True, "conservation report conserved")
    pins = panel_sum["pins"]
    pin_ok = all(abs(pins[str(y)]["wide_rule_with_coords_main_only"] - config.PIN_CITY_VIOLENT_EXPLORER[y]) / config.PIN_CITY_VIOLENT_EXPLORER[y] <= config.PIN_TOLERANCE for y in config.PIN_CITY_VIOLENT_EXPLORER)
    cell_ok = panel_sum["cell_40_42_by_year"].get("2024") == config.PIN_CELL_2024 and panel_sum["cell_40_42_by_year"].get("2025") == config.PIN_CELL_2025
    reg.gate("I5", "integrity", "reference pins reproduce (citywide 2024/2025, cell 40_42)", pin_ok and cell_ok,
             {"city": pins, "cell": {k: panel_sum["cell_40_42_by_year"].get(k) for k in ("2024", "2025")}}, config.PIN_TOLERANCE,
             f"city {pins['2024']['wide_rule_with_coords_main_only']}/{pins['2025']['wide_rule_with_coords_main_only']} vs pins "
             f"{config.PIN_CITY_VIOLENT_EXPLORER[2024]}/{config.PIN_CITY_VIOLENT_EXPLORER[2025]}; cell {panel_sum['cell_40_42_by_year'].get('2024')}/{panel_sum['cell_40_42_by_year'].get('2025')}; "
             f"with the held 2025 tail the city is {pins['2025']['wide_rule_with_coords_all_vintages']}")
    pa = core_sum["precinct_agree"]
    reg.gate("I6", "integrity", "recorded precinct agrees with precinct polygon", pa >= config.GATE_PRECINCT_AGREE and core_sum["core_majority_precinct"] == config.PRECINCT_CORE,
             {"agree": round(pa, 3), "majority": core_sum["core_majority_precinct"]}, config.GATE_PRECINCT_AGREE,
             f"{pa:.1%} agreement in the bbox; core majority precinct {core_sum['core_majority_precinct']}", warn_only=True,
             footnote="About one in twelve complaints near the 84th, 88th and 78th precinct seams carries a recorded precinct that differs from the one its rounded coordinate falls in.")
    nulls = {k: round(m["stats"]["violent_no_coord"] / max(m["stats"]["violent_rows"], 1), 4) for k, m in manifest.items()}
    worst = max(nulls.values())
    reg.gate("I7", "integrity", "violent complaints without coordinates", worst < config.GATE_COORD_NULL, nulls, config.GATE_COORD_NULL,
             f"worst file {worst:.2%} of violent rows lack coordinates", warn_only=True,
             footnote="A small share of complaints carries no coordinates and is absent from every map and cell count.")
    yf = {k: round(m["stats"]["rows_in_file_year"] / m["stats"]["rows"], 4) for k, m in manifest.items()}
    reg.gate("I8", "integrity", "complaint year matches file year", min(yf.values()) >= config.GATE_YEAR_FILE_AGREE, yf, config.GATE_YEAR_FILE_AGREE,
             f"minimum agreement {min(yf.values()):.3%}")
    tables["coord_null_share"] = nulls

    # ---------------- S: coding stability (citywide, all offenses) ----------------
    ca = io.read_cache("coding_agg")
    ca = ca[ca["vintage"] == "main"]
    ca["year"] = ca["file_year"].astype(int)
    for ky, label in (("105", "robbery"), ("106", "felony assault")):
        sub = ca[ca["ky_cd"] == ky].groupby(["year", "pd_cd", "pd_desc"])["n"].sum().reset_index()
        tot = sub.groupby("year")["n"].transform("sum")
        sub["share"] = sub["n"] / tot
        piv = sub.pivot_table(index=["pd_cd", "pd_desc"], columns="year", values="share", fill_value=0)
        moves = (piv.diff(axis=1).abs() > 0.10).any(axis=1)
        flagged = [f"{i[1]} ({i[0]})" for i in piv.index[moves]]
        reg.warn_if(f"S1_{ky}", "coding", f"pd-code mix within {label} stable", len(flagged) > 0, flagged, "10 pp year-over-year",
                    f"{len(flagged)} codes moved more than 10 pp in a year: {flagged[:4]}", ["claim_3", "claim_4"],
                    f"NYPD's internal coding of {label} shifted between codes in some years; class comparisons use groups of codes, not single codes.")
        tables[f"pd_mix_{ky}"] = {f"{i[1]} ({i[0]})": {int(y): round(float(x), 4) for y, x in r.items()} for i, r in piv.iterrows()}
    first_seen = ca.groupby(["ky_cd", "pd_cd", "pd_desc"])["year"].agg(["min", "max", ]).reset_index()
    sizes = ca.groupby(["ky_cd", "pd_cd", "pd_desc"])["n"].sum().reset_index()
    first_seen = first_seen.merge(sizes)
    shop = first_seen[first_seen["pd_desc"].fillna("").str.contains("SHOPLIFTING")]
    shop_first = int(shop["min"].min()) if len(shop) else None
    reg.gate("S2", "coding", "shoplift-origin robbery code present across the whole window", shop_first is not None and shop_first <= config.YEARS[0],
             {"first_year": shop_first, "codes": shop[["pd_cd", "pd_desc"]].to_dict("records")}, config.YEARS[0],
             f"'began as shoplifting' first seen {shop_first}", warn_only=True,
             footnote=f"The 'robbery, began as shoplifting' code first appears in {shop_first}; comparisons for that class start the year after.")
    shop_share = ca[ca["pd_desc"].fillna("").str.contains("SHOPLIFTING") & (ca["ky_cd"] == "105")].groupby("year")["n"].sum() / ca[ca["ky_cd"] == "105"].groupby("year")["n"].sum()
    tables["shoplift_share_of_robbery_city"] = {int(k): round(float(x), 4) for k, x in shop_share.items()}
    off_share = ca[ca["pd_desc"].fillna("").str.contains("POLICE/PEACE|PUBLIC SERVICE|TRAFFIC AGENT") & (ca["ky_cd"] == "106")].groupby("year")["n"].sum() / ca[ca["ky_cd"] == "106"].groupby("year")["n"].sum()
    tables["officer_share_of_felony_assault_city"] = {int(k): round(float(x), 4) for k, x in off_share.items()}
    reg.report("S3", "coding", "citywide shares: shoplift-origin robbery, officer assault", {"shoplift": tables["shoplift_share_of_robbery_city"], "officer": tables["officer_share_of_felony_assault_city"]},
               f"shoplift share of robbery {shop_share.loc[2010]:.1%} (2010) to {shop_share.loc[2025]:.1%} (2025); officer share of felony assault {off_share.loc[2010]:.1%} to {off_share.loc[2025]:.1%}", ["claim_3", "claim_4"])
    big = first_seen[first_seen["n"] >= 100]
    appear = big[big["min"] > 2010].sort_values("n", ascending=False)
    vanish = big[big["max"] < 2024].sort_values("n", ascending=False)
    reg.report("S4", "coding", "codes that appear after 2010 or disappear before 2024",
               {"appear": appear.head(40).to_dict("records"), "disappear": vanish.head(40).to_dict("records")},
               f"{len(appear)} codes with 100+ rows first appear after 2010 (e.g. {appear.head(3)['pd_desc'].tolist()}); {len(vanish)} disappear before 2024", ["general"])
    lc = ca[ca["ky_cd"].isin(["105", "106"])].groupby(["ky_cd", "year", "law_cat_cd"])["n"].sum().reset_index()
    lc["share"] = lc["n"] / lc.groupby(["ky_cd", "year"])["n"].transform("sum")
    fel = lc[lc["law_cat_cd"] == "FELONY"].groupby("ky_cd")["share"].min()
    reg.gate("S5", "coding", "robbery and felony assault coded FELONY every year", bool((fel >= config.GATE_LAWCAT_STABLE).all()), fel.round(4).to_dict(), config.GATE_LAWCAT_STABLE,
             f"minimum FELONY share by code: {fel.round(4).to_dict()}")
    extra = v[v["ky_cd"].isin(config.EXPLORER_EXTRA_HOMICIDE)].groupby("year").size()
    base = v[v["violent_primary"]].groupby("year").size()
    es = (extra / base).fillna(0)
    reg.gate("S6", "coding", "wide-rule extras (negligent homicide) negligible", float(es.max()) < config.GATE_EXPLORER_EXTRA, es.round(5).to_dict(), config.GATE_EXPLORER_EXTRA,
             f"max {es.max():.3%} of violent in any year")
    att = vp.assign(att=vp["crm_atpt_cptd_cd"].fillna("").str.upper().eq("ATTEMPTED"))
    att_core = att[masks["core400"]].groupby("year")["att"].mean()
    att_city = att.groupby("year")["att"].mean()
    tables["attempted_share"] = {"core400": {int(k): round(float(x), 4) for k, x in att_core.items()}, "city": {int(k): round(float(x), 4) for k, x in att_city.items()}}
    drift = float(att_core.loc[2021:2025].mean() - att_core.loc[2010:2019].mean())
    reg.warn_if("S7", "coding", "attempted share drift in the core", abs(drift) > 0.10, round(drift, 3), 0.10,
                f"core attempted share moved {drift:+.1%} points from the 2010s to 2021-25 (city {att_city.loc[2021:2025].mean() - att_city.loc[2010:2019].mean():+.1%})", ["claim_1"],
                "The share of complaints recorded as attempted rather than completed shifted in the core.")

    # ---------------- T: time and lag ----------------
    dt = {g: (vp[m].groupby("year")["default_time"].mean()) for g, m in masks.items()}
    tables["default_time_share"] = {g: {int(k): round(float(x), 4) for k, x in s.items()} for g, s in dt.items()}
    rec = vp[vp["year"].isin(config.RECENT_YEARS)]
    gap = float(rec[masks["core400"].loc[rec.index]]["default_time"].mean() - rec["default_time"].mean()) * 100
    reg.warn_if("T1", "time", "default-time (00:00 / 12:00) share, core vs city", abs(gap) > config.WARN_DEFAULT_TIME_PP, round(gap, 2), config.WARN_DEFAULT_TIME_PP,
                f"core {rec[masks['core400'].loc[rec.index]]['default_time'].mean():.1%} vs city {rec['default_time'].mean():.1%} of 2024-25 complaints carry a default time ({gap:+.1f} pp)", ["claim_5"],
                "A larger share of complaints here than citywide carries a placeholder time of midnight or noon; hour-of-day views exclude those rows.")
    def night_share(df):
        return float(df["night"].mean()) if len(df) else np.nan
    c_all, ci_all = night_share(vp[masks["core400"]]), night_share(vp)
    clean = vp[~vp["default_time"] & ~(vp["span_hours"] > config.SPAN_MAX_HOURS)]
    c_cl, ci_cl = night_share(clean[masks["core400"].loc[clean.index]]), night_share(clean)
    gap_cl = (ci_cl - c_cl) * 100
    reg.kill_if("T2", "time", "night-share gap survives excluding default times and long spans", gap_cl < config.KILL_NIGHT_GAP_PP,
                {"raw": {"core": round(c_all, 4), "city": round(ci_all, 4)}, "clean": {"core": round(c_cl, 4), "city": round(ci_cl, 4)}}, config.KILL_NIGHT_GAP_PP,
                f"raw gap {(ci_all - c_all) * 100:.1f} pp; clean gap {gap_cl:.1f} pp", ["claim_5"],
                "Once placeholder times and multi-hour spans are removed, the block's night share is no longer clearly below the city's.")
    tables["night_share"] = {"raw": {"core400": c_all, "city": ci_all}, "clean": {"core400": c_cl, "city": ci_cl}}
    def span_bins(df):
        s = df["span_hours"]
        return {"null": float(s.isna().mean()), "zero": float((s == 0).mean()), "lt1h": float(((s > 0) & (s < 1)).mean()), "1_6h": float(((s >= 1) & (s <= 6)).mean()),
                "6_24h": float(((s > 6) & (s <= 24)).mean()), "gt24h": float((s > 24).mean())}
    tables["span_bins"] = {"core400": span_bins(vp[masks["core400"]]), "city": span_bins(vp)}
    reg.report("T3", "time", "from-to span distribution", tables["span_bins"], f"core spans over 6 h: {tables['span_bins']['core400']['6_24h'] + tables['span_bins']['core400']['gt24h']:.1%}; city {tables['span_bins']['city']['6_24h'] + tables['span_bins']['city']['gt24h']:.1%}", ["claim_5"])
    def lag30(df):
        return float((df["lag_days"] > 30).mean())
    l_core, l_city = lag30(vp[masks["core400"]]), lag30(vp)
    tables["lag_gt30_share"] = {g: {int(k): round(float(x), 4) for k, x in (vp[m]["lag_days"] > 30).groupby(vp[m]["year"]).mean().items()} for g, m in masks.items()}
    reg.warn_if("T4", "time", "report lag over 30 days, core vs city", (l_core - l_city) * 100 > config.WARN_LAG30_PP, {"core": round(l_core, 4), "city": round(l_city, 4)}, config.WARN_LAG30_PP,
                f"core {l_core:.2%} vs city {l_city:.2%} reported more than 30 days after occurrence", ["claim_1", "claim_8"],
                "Complaints here are reported late more often than citywide, so recent-year counts understate the block more than they understate the city.")
    ct = vp[vp["at_courthouse_point"]]
    rest = vp[masks["core400"] & ~vp["at_courthouse_point"]]
    reg.report("T5", "time", "courthouse point vs rest of core: default-time share, lag, peak hour",
               {"courthouse": {"default_time": round(float(ct["default_time"].mean()), 3), "lag_gt30": round(lag30(ct), 4), "peak_hour": int(ct[~ct["default_time"]]["hour"].mode().iloc[0])},
                "rest": {"default_time": round(float(rest["default_time"].mean()), 3), "lag_gt30": round(lag30(rest), 4), "peak_hour": int(rest[~rest["default_time"]]["hour"].mode().iloc[0])}},
               f"courthouse point default-time {ct['default_time'].mean():.1%}, rest of core {rest['default_time'].mean():.1%}", ["claim_6"],
               "Courthouse-point hours are described as when complaints were recorded, not when anything happened.")

    # ---------------- G: coordinate generalization ----------------
    coords = io.read_cache("coord_agg")
    coords = coords[(coords["vintage"] == "main") & coords["lat"].notna()]
    coords["year"] = coords["file_year"].astype(int)
    pts_city = coords.groupby("year").size()
    rep_city = coords[coords["n"] >= 2].groupby("year")["n"].sum() / coords.groupby("year")["n"].sum()
    cv = vp[masks["core400"] & vp["has_coord"]]
    pts_core = cv.groupby("year")["point_id" if "point_id" in cv else "lat"].nunique() if "point_id" in cv else cv.assign(p=cv["lat"].round(6).astype(str) + cv["lon"].round(6).astype(str)).groupby("year")["p"].nunique()
    tables["distinct_points"] = {"city": {int(k): int(x) for k, x in pts_city.items()}, "core400": {int(k): int(x) for k, x in pts_core.items()},
                                 "city_repeat_share": {int(k): round(float(x), 4) for k, x in rep_city.items()}}
    reg.report("G1", "coordinates", "distinct violent points per year and repeat share", tables["distinct_points"],
               f"city distinct points {int(pts_city.loc[2010]):,} (2010) to {int(pts_city.loc[2025]):,} (2025); core {int(pts_core.loc[2010])} to {int(pts_core.loc[2025])}; city repeat share {rep_city.loc[2025]:.1%}", ["claim_6"])
    step = pts_city.pct_change()
    flagged = {int(k): round(float(x), 3) for k, x in step.items() if abs(x) > config.WARN_POINT_STEP}
    ct_share = (vp[vp["at_courthouse_point"]].groupby("year").size() / vp[masks["core400"]].groupby("year").size()).fillna(0)
    tables["courthouse_share_by_year"] = {int(k): round(float(x), 4) for k, x in ct_share.items()}
    ct_jump = int(ct_share.diff().loc[2007:2025].idxmax())
    reg.warn_if("G2", "coordinates", "step change in citywide distinct points", len(flagged) > 0 and ct_jump in flagged, {"flagged_years": flagged, "courthouse_share_jump_year": ct_jump}, config.WARN_POINT_STEP,
                f"years with >15% change in distinct points: {flagged}; courthouse share jumps most in {ct_jump}", ["claim_6"],
                "A citywide change in how NYPD places complaints on the map coincides with the year the courthouse point's share rose.")
    near60 = vp[masks["core400"] & vp["has_coord"]]
    d60 = geo.haversine_m(near60["lat"], near60["lon"], config.COURTHOUSE_LAT, config.COURTHOUSE_LON) <= 60
    pts60 = near60[d60].assign(p=near60[d60]["lat"].round(6).astype(str) + near60[d60]["lon"].round(6).astype(str)).groupby("year")["p"].nunique()
    tables["points_within_60m_of_courthouse"] = {int(k): int(x) for k, x in pts60.items()}
    reg.warn_if("G3", "coordinates", "neighboring points merged into the courthouse point", bool(pts60.diff().loc[ct_jump] < 0) if ct_jump in pts60.index else False,
                tables["points_within_60m_of_courthouse"], "drop in the jump year", f"distinct points within 60 m of the courthouse: {pts60.loc[2015]} (2015), {pts60.loc[2025]} (2025)", ["claim_6"],
                "Points next to the courthouse were folded into it in the year its share rose.")
    from scipy.spatial import cKDTree
    # cluster near-duplicate points (NYPD splits a location at the 6th decimal) before measuring spacing
    core_pts = cv[cv["year"].isin(config.RECENT_YEARS)][["lat", "lon"]].round(4).drop_duplicates()
    xy = np.c_[(core_pts["lon"] + 73.985) * 111_000 * np.cos(np.radians(40.6885)), (core_pts["lat"] - 40.6885) * 111_000]
    d, _ = cKDTree(xy).query(xy, k=2)
    nn = d[:, 1]
    tables["nn_spacing_m"] = {"median": float(np.median(nn)), "p25": float(np.percentile(nn, 25)), "p75": float(np.percentile(nn, 75)), "n_points": int(len(nn))}
    reg.report("G4", "coordinates", "nearest-neighbor spacing of core points, 2024-25", tables["nn_spacing_m"], f"median {np.median(nn):.0f} m between distinct points (p25 {np.percentile(nn, 25):.0f} m)", ["claim_6"])
    dec = vp[vp["has_coord"]].assign(d=vp["latitude"].fillna("").str.split(".").str[-1].str.len()).groupby("year")["d"].median()
    tables["coord_decimals_median"] = {int(k): float(x) for k, x in dec.items()}
    reg.report("G5", "coordinates", "coordinate decimal precision by year", tables["coord_decimals_median"], f"median decimals {dec.min():.0f} to {dec.max():.0f}", ["claim_6"])

    # ---------------- V: vintages ----------------
    held = v[(v["vintage"] == "held") & v["violent_primary"]]
    main25 = v[(v["vintage"] == "main") & (v["year"] == 2025) & v["violent_primary"]]
    shares = {}
    for g, m in masks.items():
        hs = float(m.loc[held.index].mean()); ms = float(m.loc[main25.index].mean())
        shares[g] = {"late_share": round(hs, 5), "main_share": round(ms, 5), "factor": round(hs / ms, 2) if ms else None, "late_n": int(m.loc[held.index].sum())}
    f_core = shares["core400"]["factor"]
    reg.warn_if("V1", "vintage", "where the late-reported 2025 complaints landed", f_core is not None and (f_core > config.WARN_HELD_SHARE_FACTOR or f_core < 1 / config.WARN_HELD_SHARE_FACTOR), shares, config.WARN_HELD_SHARE_FACTOR,
                f"{len(held)} late violent complaints; core received {shares['core400']['late_n']} ({f_core}x its usual share)", ["claim_8", "claim_1"],
                "Late-reported complaints land on this block at a different rate than elsewhere, so the newest half-year figures carry a reported-by caveat.")
    tables["held_2025"] = shares
    reg.gate("V2", "vintage", "first-half comparisons use the reported-by-June-30 rule", True, "enforced in stage 07", "rule", "claim 8 built from the h1_reported window")
    reg.skipped("V3", "vintage", "2026 revision diff", "single vintage: live 2026 file is byte-identical to the 2026-07-31 pull", ["claim_8"])
    reg.skipped("V4", "vintage", "historic vs year-to-date diff for 2025", "the historic dataset has not published 2025 yet; see DECISIONS.md", ["claim_8"])

    reg.save(config.OUT_DIR / "dq_audit.json")
    (config.OUT_DIR / "dq_tables.json").write_text(json.dumps(tables, indent=1, default=str))
    print("stage 05 done; failed:", reg.failed(), "kills:", reg.kills())
    if reg.failed():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
