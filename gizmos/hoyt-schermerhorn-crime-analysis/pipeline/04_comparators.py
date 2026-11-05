"""Stage 04: comparison cells and rank ladders.

  output/comparators.json   hub cells, courthouse cells, neighbors: counts, class mixes, ratios, night shares
  output/ladder.json        2024-25 rank ladder under every definition variant + top-20 table
  output/cell_change_panel.csv  per-cell 2010s base, 2024-25 mean, ratio, by class; percentiles for 40_42
  output/comparators_dq.json    DqResults for C1-C3, H1-H3, K1-K2"""
from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib import geo  # noqa: E402
from lib.dq import Registry  # noqa: E402

BASE = list(range(config.BASE_YEARS[0], config.BASE_YEARS[1] + 1))
RECENT = list(config.RECENT_YEARS)
NB_YEARS = len(BASE)


def resolve_anchor(lat: float, lon: float) -> str:
    ids, off = geo.assign_cells(np.array([lon]), np.array([lat]))
    if off[0] or ids[0] is None:
        raise SystemExit(f"anchor {lat},{lon} is off-lattice")
    return str(ids[0])


def ratio_table(panel: pd.DataFrame) -> pd.DataFrame:
    """cell x class(+all): base mean/yr, recent mean/yr, ratio."""
    p = panel.copy()
    allrows = p.groupby(["cell_id", "year"])["n"].sum().rename("n").reset_index().assign(cls="all")
    p = pd.concat([p, allrows], ignore_index=True)
    base = p[p["year"].isin(BASE)].groupby(["cell_id", "cls"])["n"].sum() / NB_YEARS
    rec = p[p["year"].isin(RECENT)].groupby(["cell_id", "cls"])["n"].sum() / len(RECENT)
    t = pd.concat([base.rename("base"), rec.rename("recent")], axis=1).fillna(0).reset_index()
    t["ratio"] = np.where(t["base"] > 0, t["recent"] / t["base"], np.nan)
    return t


def percentile_of(t: pd.DataFrame, cls: str, cell: str, mask) -> dict:
    sub = t[(t["cls"] == cls) & mask & t["ratio"].notna()]
    me = sub[sub["cell_id"] == cell]
    if me.empty:
        return {"n": int(len(sub)), "percentile": None, "ratio": None}
    r = float(me["ratio"].iloc[0])
    pct = float((sub["ratio"] < r).mean() * 100)
    return {"n": int(len(sub)), "percentile": round(pct, 1), "ratio": round(r, 3)}


def main() -> None:
    reg = Registry()
    panel = pd.read_parquet(config.OUT_DIR / "cell_year_class.parquet")
    v = pd.read_parquet(config.OUT_DIR / "violent_citywide.parquet")
    names = geo.cell_name_map()
    dep = geo.deployed_cells().set_index("id")

    # ---- ladders over the definition grid (cell level, 2024-25) -------------
    vv = v[v["cell_id"].notna() & v["year"].isin(RECENT)]
    ladder_rows = []
    for rule, transit, vint in product(("primary", "wide"), ("in", "out"), ("main_held", "main")):
        m = vv["violent_explorer"] if rule == "wide" else vv["violent_primary"]
        if transit == "out":
            m &= ~vv["transit"]
        if vint == "main":
            m &= vv["vintage"] == "main"
        sub = vv[m]
        counts = {}
        for defn in ("all", "no_officer", "no_officer_no_retail", "no_courthouse"):
            s = sub
            if defn in ("no_officer", "no_officer_no_retail"):
                s = s[s["cls"] != "officer_assault"]
            if defn == "no_officer_no_retail":
                s = s[s["cls"] != "retail_robbery"]
            if defn == "no_courthouse":
                s = s[~s["at_courthouse_point"]]  # only this cell's count changes: the point is inside it
            c = s.groupby("cell_id").size().reindex(dep.index, fill_value=0).sort_values(ascending=False)
            rank = int(list(c.index).index(config.CELL_ID)) + 1
            counts[defn] = {"rank": rank, "count": int(c.get(config.CELL_ID, 0))}
            if rule == "primary" and transit == "in" and vint == "main_held":
                counts[defn]["top20"] = [
                    {"cell_id": cid, "name": names.get(cid, cid), "lat": float(dep.loc[cid, "south"] + dep.loc[cid, "north"]) / 2,
                     "lon": float(dep.loc[cid, "west"] + dep.loc[cid, "east"]) / 2, "count": int(n), "rank": i + 1}
                    for i, (cid, n) in enumerate(c.head(20).items())]
        ladder_rows.append({"rule": rule, "transit": transit, "vintage": vint, **{k: counts[k]["rank"] for k in counts},
                            "_counts": counts})
    primary = next(r for r in ladder_rows if r["rule"] == "primary" and r["transit"] == "in" and r["vintage"] == "main_held")
    top20 = primary["_counts"]["all"]["top20"]
    # class shares for the top-20 (primary)
    sub = vv[vv["violent_primary"]]
    for row in top20:
        s = sub[sub["cell_id"] == row["cell_id"]]
        row["officer_share"] = round(float((s["cls"] == "officer_assault").mean()), 3) if len(s) else 0
        row["retail_share"] = round(float((s["cls"] == "retail_robbery").mean()), 3) if len(s) else 0
    ranks = {k: primary["_counts"][k]["rank"] for k in ("all", "no_officer", "no_officer_no_retail")}
    steps_ok = (ranks["no_officer"] - ranks["all"] >= config.LADDER_MIN_STEP) and (ranks["no_officer_no_retail"] - ranks["no_officer"] >= config.LADDER_MIN_STEP)
    rank_range = [min(r["all"] for r in ladder_rows), max(r["all"] for r in ladder_rows)]
    reg.kill_if("L1", "ladder", "ladder steps each drop at least two places", not steps_ok, ranks, config.LADDER_MIN_STEP,
                f"ranks all/no_officer/no_officer_no_retail = {ranks['all']}/{ranks['no_officer']}/{ranks['no_officer_no_retail']}", ["claim_7"],
                "The rank ladder is not drawn because removing a class moved the cell fewer than two places.")
    reg.warn_if("L2", "ladder", "all-violent rank stable across definition variants", not (config.CLAIM7_TOL[0] <= rank_range[0] and rank_range[1] <= config.CLAIM7_TOL[1]),
                rank_range, list(config.CLAIM7_TOL), f"all-violent rank ranges {rank_range[0]} to {rank_range[1]} across violent rule x transit x vintage", ["claim_7"],
                "The cell's citywide rank moves outside #1 to #3 depending on how violent crime is defined.")
    ladder = {"window": "2024_25", "n_cells": int(len(dep)), "cell_id": config.CELL_ID,
              "primary": {k: {"rank": primary["_counts"][k]["rank"], "count": primary["_counts"][k]["count"]} for k in (*ranks, "no_courthouse")},
              "sensitivity": [{k: r[k] for k in ("rule", "transit", "vintage", "all", "no_officer", "no_officer_no_retail", "no_courthouse")} for r in ladder_rows],
              "top20": top20, "ladder_ok": bool(steps_ok)}

    # ---- change panel ---------------------------------------------------------
    t = ratio_table(panel)
    t["name"] = t["cell_id"].map(names)
    allc = t[t["cls"] == "all"].set_index("cell_id")
    base_all = allc["base"]
    masks = {
        "base_ge_20": t["cell_id"].map(base_all >= config.COMPARATOR_BASE_MIN).fillna(False),
        "top_decile": t["cell_id"].map(base_all >= base_all[base_all > 0].quantile(1 - config.COMPARATOR_TOP_DECILE)).fillna(False),
    }
    bk_cells = set(v[v["brooklyn"] & v["cell_id"].notna()]["cell_id"].value_counts().loc[lambda s: s >= 10].index)
    masks["brooklyn_base_ge_20"] = masks["base_ge_20"] & t["cell_id"].isin(bk_cells)
    pct = {cls: {mname: percentile_of(t, cls, config.CELL_ID, m) for mname, m in masks.items()} for cls in ["all"] + config.CLASSES}
    p_top = pct["all"]["top_decile"]["percentile"]
    reg.kill_if("C1", "cells", "cell's 2010s-to-2024-25 growth percentile among top-decile cells", p_top is None or p_top < config.KILL_C1_PERCENTILE,
                pct["all"], config.KILL_C1_PERCENTILE, f"all-violent ratio {pct['all']['top_decile']['ratio']}x sits at the {p_top} percentile of {pct['all']['top_decile']['n']} top-decile cells; "
                f"{pct['all']['base_ge_20']['percentile']} percentile among {pct['all']['base_ge_20']['n']} cells with base >= 20/yr", ["claim_1"],
                "The cell's growth is not unusual among comparable cells; the 2.6x figure is described as one of many, not exceptional.")
    doubled = allc[(allc["base"] >= 50) & (allc["ratio"] >= 2)].sort_values("ratio", ascending=False)
    reg.report("C2", "cells", "cells that doubled from a base of 50+/yr", [{"cell_id": c, "name": names.get(c, c), "base": round(r.base, 1), "recent": round(r.recent, 1), "ratio": round(r.ratio, 2)} for c, r in doubled.iterrows()],
               f"{len(doubled)} cells doubled from base >= 50/yr", ["claim_1"])
    row, col = map(int, config.CELL_ID.split("_"))
    nb_ids = [f"{row+dr}_{col+dc}" for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0)]
    neighbors = [{"cell_id": c, "name": names.get(c, c), "base": round(float(allc.loc[c, "base"]), 1) if c in allc.index else None,
                  "recent": round(float(allc.loc[c, "recent"]), 1) if c in allc.index else None,
                  "ratio": round(float(allc.loc[c, "ratio"]), 2) if c in allc.index and pd.notna(allc.loc[c, "ratio"]) else None} for c in nb_ids]
    reg.report("C3", "cells", "the eight neighboring cells", neighbors, "neighbor ratios: " + ", ".join(f"{n['cell_id']} {n['ratio']}" for n in neighbors), ["claim_1"])

    # ---- hubs -------------------------------------------------------------------
    def decompose(cell_ids: list[str], label_map: dict[str, str]) -> list[dict]:
        out = []
        for name, cid in label_map.items():
            s = v[(v["cell_id"] == cid) & v["violent_primary"]]
            rec = s[s["year"].isin(RECENT)]
            base = s[s["year"].isin(BASE)]
            by_cls_rec = rec.groupby("cls").size()
            by_cls_base = base.groupby("cls").size() / NB_YEARS
            ratios = {c: (round(float(by_cls_rec.get(c, 0) / len(RECENT) / by_cls_base[c]), 2) if by_cls_base.get(c, 0) > 0 else None) for c in config.CLASSES}
            ratios["all"] = round(float(len(rec) / len(RECENT) / (len(base) / NB_YEARS)), 2) if len(base) else None
            night = rec[~rec["default_time"]]
            out.append({"name": name, "cell_id": cid, "cell_name": names.get(cid, cid), "count_2024_25": int(len(rec)),
                        "by_class_2024_25": {c: int(by_cls_rec.get(c, 0)) for c in config.CLASSES},
                        "ratio_2024_25_vs_2010s": ratios,
                        "night_share": round(float(night["night"].mean()), 3) if len(night) else None,
                        "officer_share": round(float((rec["cls"] == "officer_assault").mean()), 3) if len(rec) else None,
                        "retail_share": round(float((rec["cls"] == "retail_robbery").mean()), 3) if len(rec) else None})
        return out

    hub_map = {n: resolve_anchor(*ll) for n, ll in config.HUB_ANCHORS.items()}
    assert hub_map["Times Square / Port Authority"] == config.TIMES_SQUARE_CELL, hub_map
    hubs = decompose(list(hub_map.values()), hub_map)
    me = decompose([config.CELL_ID], {"Hoyt-Schermerhorn / Fulton Mall": config.CELL_ID})[0]
    hub_med = {c: float(np.nanmedian([h["ratio_2024_25_vs_2010s"][c] for h in hubs if h["ratio_2024_25_vs_2010s"][c] is not None])) for c in ("retail_robbery", "officer_assault", "all")}
    reg.report("H1", "hubs", "hub cell decompositions", {"hubs": hubs, "this_cell": me}, f"hub median all-violent ratio {hub_med['all']:.2f}x vs this cell {me['ratio_2024_25_vs_2010s']['all']}x", ["claim_1", "claim_3", "claim_4"])
    my_retail = me["ratio_2024_25_vs_2010s"]["retail_robbery"]
    reg.kill_if("H2", "hubs", "shoplift-origin robbery growth exceeds the hub median", my_retail is None or my_retail <= hub_med["retail_robbery"],
                {"this_cell": my_retail, "hub_median": round(hub_med["retail_robbery"], 2)}, "hub median",
                f"retail-robbery ratio {my_retail}x vs hub median {hub_med['retail_robbery']:.2f}x; officer-assault {me['ratio_2024_25_vs_2010s']['officer_assault']}x vs hub median {hub_med['officer_assault']:.2f}x",
                ["claim_3"], "The rise in shoplifting-origin robbery here is no larger than at other commercial hubs; the piece calls it a hub-wide pattern.")
    hub_night = float(np.nanmedian([h["night_share"] for h in hubs if h["night_share"] is not None]))
    my_night = me["night_share"]
    reg.warn_if("H3", "hubs", "hub night shares vs this cell", abs(hub_night - my_night) * 100 <= config.WARN_HUB_NIGHT_PP,
                {"this_cell": my_night, "hub_median": round(hub_night, 3)}, config.WARN_HUB_NIGHT_PP,
                f"night share {my_night:.3f} here vs hub median {hub_night:.3f}", ["claim_5"],
                "Other commercial and transit hubs show a similarly daytime pattern; the afternoon peak is a destination pattern, not something unique to this block.")

    # ---- courthouses --------------------------------------------------------------
    ct_map = {n: resolve_anchor(*ll) for n, ll in config.COURTHOUSE_ANCHORS.items()}
    ct_map["Hoyt-Schermerhorn cell (this piece)"] = config.CELL_ID
    ct_map["cell 64_59 (flagged for officer assaults)"] = "64_59"
    courthouses = []
    jump_years = []
    for name, cid in ct_map.items():
        s = v[(v["cell_id"] == cid) & v["violent_primary"] & v["has_coord"]]
        s = s.assign(pt=s["lat"].round(6).astype(str) + "," + s["lon"].round(6).astype(str))
        rec = s[s["year"].isin(RECENT)]
        if rec.empty:
            continue
        top_pt = rec["pt"].value_counts().index[0]
        lat, lon = map(float, top_pt.split(","))
        # cluster: everything within COURTHOUSE_MATCH_M of the top point (NYPD points split at the 6th decimal)
        near = geo.haversine_m(s["lat"], s["lon"], lat, lon) <= config.COURTHOUSE_MATCH_M
        at = rec[geo.haversine_m(rec["lat"], rec["lon"], lat, lon) <= config.COURTHOUSE_MATCH_M]
        series = s[near].groupby("year").size().reindex(config.YEARS, fill_value=0)
        yoy = series.diff()
        jump = int(yoy.loc[2007:2025].idxmax()) if yoy.loc[2007:2025].max() > 0 else None
        jump_years.append(jump)
        courthouses.append({"name": name, "cell_id": cid, "cell_name": names.get(cid, cid), "cell_count_2024_25": int(len(rec)),
                            "largest_point": {"lat": lat, "lon": lon, "count": int(len(at)), "share_of_cell": round(float(len(at) / len(rec)), 3),
                                              "officer_share": round(float((at["cls"] == "officer_assault").mean()), 3),
                                              "null_premise_share": round(float(at["prem_typ_desc"].isna().mean() + (at["prem_typ_desc"] == "(null)").mean()), 3),
                                              "by_year": {int(y): int(n) for y, n in series.items()}},
                            "jump_year": jump})
    reg.report("K1", "courthouses", "largest single point in each courthouse cell", courthouses,
               "; ".join(f"{c['name'].split('(')[0].strip()}: {c['largest_point']['share_of_cell']:.0%} of cell at one point, {c['largest_point']['officer_share']:.0%} officer" for c in courthouses), ["claim_6"])
    # K3 spillover: is a courthouse cell unusually violent once its own front-door point is removed?
    dens = pd.read_csv(config.OUT_DIR / "cell_density.csv").set_index("cell_id")
    rec_all = v[v["violent_primary"] & v["has_coord"] & v["year"].isin(RECENT) & v["cell_id"].notna()]
    cnt = rec_all.groupby("cell_id").size().reindex(dep.index, fill_value=0)
    base = dens[dens["pop_jobs"] >= config.SPILLOVER_MIN_POP_JOBS].copy()
    base["cnt"] = cnt.reindex(base.index).fillna(0)
    spill = []
    for ct in courthouses:
        cid = ct["cell_id"]; lp = ct["largest_point"]
        s = rec_all[rec_all["cell_id"] == cid]
        at = geo.haversine_m(s["lat"], s["lon"], lp["lat"], lp["lon"]) <= config.COURTHOUSE_MATCH_M
        ex = int((~at).sum()); total = int(len(s))
        adj = cnt.copy(); adj[cid] = ex
        rank_ex = int((adj > ex).sum()) + 1
        pj = float(dens["pop_jobs"].get(cid, 0))
        rate = ex / pj * 1000 if pj else None
        rank_rate = None
        if cid in base.index and pj:
            b = base.copy(); b.loc[cid, "cnt"] = ex; b["rate"] = b["cnt"] / b["pop_jobs"] * 1000
            rank_rate = int((b["rate"] > rate).sum()) + 1
        spill.append({"name": ct["name"], "cell_id": cid, "cell_name": ct["cell_name"], "count_2024_25": total, "on_site": total - ex, "ex_site": ex,
                      "rank_all": int((cnt > total).sum()) + 1, "rank_ex_site": rank_ex, "pop_jobs": int(pj), "ex_site_per_1000_present": round(rate, 2) if rate is not None else None,
                      "rank_ex_site_per_person": rank_rate, "n_cells_per_person": int(len(base))})
    reg.report("K3", "courthouses", "courthouse cells without their on-site point: rank by count and per person present", spill,
               "; ".join(f"{x['name'].split('(')[0].strip()}: #{x['rank_ex_site']} by count, #{x['rank_ex_site_per_person']} of {x['n_cells_per_person']} per person" for x in spill), ["claim_6"])
    from collections import Counter
    jy = Counter([j for j in jump_years if j is not None])
    common = jy.most_common(1)[0] if jy else (None, 0)
    reg.warn_if("K2", "courthouses", "shared jump year across booking points", common[1] >= 3, dict(jy), 3,
                f"most common jump year {common[0]} shared by {common[1]} booking points", ["claim_4", "claim_6"],
                f"Several borough booking sites show their largest year-over-year jump in {common[0]}, which points to a citywide change in how these complaints are recorded rather than conditions on this block.")

    out = {"hubs": hubs, "this_cell": me, "hub_medians": hub_med, "courthouses": courthouses, "spillover": spill, "neighbors": neighbors,
           "percentiles": pct, "doubled_cells": reg.results[[r.id for r in reg.results].index("C2")].value}
    (config.OUT_DIR / "comparators.json").write_text(json.dumps(out, indent=1, default=str))
    (config.OUT_DIR / "ladder.json").write_text(json.dumps(ladder, indent=1))
    t.to_csv(config.OUT_DIR / "cell_change_panel.csv", index=False)
    reg.save(config.OUT_DIR / "comparators_dq.json")
    print("stage 04 done; kills:", reg.kills())


if __name__ == "__main__":
    main()
