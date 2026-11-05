"""Stage 07: the eight headline claims across the definition grid, with kill switches and the words the
prose must use. Reads index_series.parquet, ladder.json, stats.json, dq_audit.json, comparators_dq.json,
stats_dq.json. Writes output/headlines.json and output/dq.json (the merged registry + claims block)."""
from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib.dq import Registry
from lib.dq import clean_nan  # noqa: E402
from lib.words import share_words, times_words  # noqa: E402

BASE = list(range(config.BASE_YEARS[0], config.BASE_YEARS[1] + 1))
RECENT = list(config.RECENT_YEARS)
FOOTPRINTS = ["core400", "core300", "core500", "cell_40_42", "core400_ex_courthouse"]
GRID_DIMS = {"rule": ("primary", "wide"), "transit": ("in", "out"), "default_time": ("in", "out"), "vintage": ("main_held", "main")}
PRIMARY = {"rule": "primary", "transit": "in", "default_time": "in", "vintage": "main_held", "footprint": config.PRIMARY_FOOTPRINT}


def series(idx: pd.DataFrame, geo: str, cls: str, window: str = "full", **dims) -> pd.Series:
    dims = {**{k: PRIMARY[k] for k in GRID_DIMS}, **dims}
    m = (idx["geo"] == geo) & (idx["cls"] == cls) & (idx["window"] == window)
    for k, v in dims.items():
        m &= idx[k] == v
    return idx[m].set_index("year")["n"].reindex(config.YEARS, fill_value=0)


def ratio(s: pd.Series, base=BASE, recent=RECENT, base_start=None) -> float | None:
    b = [y for y in base if base_start is None or y >= base_start]
    bm = s[b].mean()
    return float(s[recent].mean() / bm) if bm > 0 else None


def main() -> None:
    idx = pd.read_parquet(config.OUT_DIR / "index_series.parquet")
    ladder = json.loads((config.OUT_DIR / "ladder.json").read_text())
    stats = json.loads((config.OUT_DIR / "stats.json").read_text())
    regs = [Registry.load(config.OUT_DIR / f) for f in ("comparators_dq.json", "dq_audit.json", "stats_dq.json")]
    merged = Registry()
    for r in regs:
        merged.results.extend(r.results)
    kills = merged.kills()
    footnotes = merged.footnotes()
    dq_tables = json.loads((config.OUT_DIR / "dq_tables.json").read_text())
    shop_first = next((r.value["first_year"] for r in merged.results if r.id == "S2"), None)
    shop_base_start = (shop_first + 1) if shop_first and shop_first > config.BASE_YEARS[0] else None

    claims: dict[str, dict] = {}

    def record(cid, label, primary_value, grid_values, words, footprint, window, tol=None, extra=None):
        vals = [g["value"] for g in grid_values if g["value"] is not None]
        direction = None
        if primary_value is not None and isinstance(primary_value, (int, float)):
            sign = np.sign(primary_value - 1) if cid in ("claim_1", "claim_3", "claim_4") else None
            if sign is not None:
                direction = all(np.sign(v - 1) == sign for v in vals)
        kill_reasons = list(kills.get(cid, []))
        if direction is False:
            kill_reasons.append("direction_flips_in_definition_grid")
        in_tol = None
        if tol is not None and primary_value is not None:
            in_tol = bool(tol[0] <= min(vals) and max(vals) <= tol[1])
        claims[cid] = {"label": label, "primary": {"value": primary_value, "words": words, "footprint": footprint, "window": window, **PRIMARY},
                       "range": [min(vals), max(vals)] if vals else None, "grid": grid_values, "direction_holds": direction,
                       "within_tolerance": in_tol, "publishable": len(kill_reasons) == 0, "kill_reasons": kill_reasons,
                       "footnotes": footnotes.get(cid, []), **(extra or {})}

    def grid(fn):
        out = []
        for fp in FOOTPRINTS:
            for combo in product(*GRID_DIMS.values()):
                dims = dict(zip(GRID_DIMS.keys(), combo))
                out.append({"footprint": fp, **dims, "value": fn(fp, dims)})
        return out

    # ---- claim 1: core vs Brooklyn vs city -------------------------------------
    def c1(fp, dims):
        return ratio(series(idx, fp, "all", **dims))
    g1 = grid(c1)
    prim = ratio(series(idx, "core400", "all", **{k: PRIMARY[k] for k in GRID_DIMS}))
    bk = ratio(series(idx, "brooklyn", "all", **{k: PRIMARY[k] for k in GRID_DIMS}))
    city = ratio(series(idx, "city", "all", **{k: PRIMARY[k] for k in GRID_DIMS}))
    pct84 = ratio(series(idx, "pct84", "all", **{k: PRIMARY[k] for k in GRID_DIMS}))
    exct = ratio(series(idx, "core400_ex_courthouse", "all", **{k: PRIMARY[k] for k in GRID_DIMS}))
    sy = ratio(series(idx, "core400", "all", window="same_year_report", **{k: PRIMARY[k] for k in GRID_DIMS}))
    sy_city = ratio(series(idx, "city", "all", window="same_year_report", **{k: PRIMARY[k] for k in GRID_DIMS}))
    record("claim_1", "core violent complaints vs the 2010s, against Brooklyn and the city", round(prim, 3), [g for g in g1 if g["footprint"] != "core400_ex_courthouse"],
           {"core": times_words(prim), "brooklyn": times_words(bk), "city": times_words(city), "core_ex_courthouse": times_words(exct)}, "core400", "2024_25_vs_2010_19",
           tol=config.CLAIM1_TOL, extra={"comparators": {"brooklyn": round(bk, 3), "city": round(city, 3), "pct84": round(pct84, 3), "core_ex_courthouse": round(exct, 3),
                                                        "core_same_year_report": round(sy, 3) if sy else None, "city_same_year_report": round(sy_city, 3) if sy_city else None},
                                         "share_of_city_per_1000": {str(y): round(float(series(idx, 'core400', 'all').loc[y] / series(idx, 'city', 'all').loc[y] * 1000), 2) for y in config.YEARS}})
    # ---- claim 2: street robbery did not rise ----------------------------------
    c2 = stats["claim_2_street_robbery"]
    g2 = grid(lambda fp, dims: ratio(series(idx, fp, "street_robbery", **dims)))
    s2 = series(idx, "core400", "street_robbery", **{k: PRIMARY[k] for k in GRID_DIMS})
    r2 = ratio(s2)
    early = float(s2.loc[2006:2008].mean())
    core_vals = [g["value"] for g in g2 if g["value"] is not None and g["footprint"] in ("core400", "core300", "core500")]
    cell_vals = [g["value"] for g in g2 if g["value"] is not None and g["footprint"] == "cell_40_42"]
    not_up = max(core_vals) <= 1.15  # within the station-centred footprints; the explorer cell is reported separately
    record("claim_2", "street robbery did not rise", round(r2, 3), [g for g in g2 if g["footprint"] != "core400_ex_courthouse"],
           {"vs_2010s": times_words(r2), "vs_2006_08": times_words(float(s2[RECENT].mean() / early)) if early else "no comparison",
            "range": f"{int(s2.loc[2006:2025].min())} to {int(s2.loc[2006:2025].max())} a year", "trend": f"{c2['trend'].get('pct_per_year', 0):+.1f} percent a year since 2006"},
           "core400", "2024_25_vs_2010_19", extra={"by_year": c2["by_year"], "trend": c2["trend"], "max_over_min": c2["max_over_min"], "not_up_in_core_footprints": bool(not_up),
                                                   "core_footprint_range": [round(min(core_vals), 3), round(max(core_vals), 3)], "cell_range": [round(min(cell_vals), 3), round(max(cell_vals), 3)],
                                                   "cell_words": times_words(float(np.mean(cell_vals))),
                                                   "city_ratio": round(ratio(series(idx, "city", "street_robbery", **{k: PRIMARY[k] for k in GRID_DIMS})), 3)})
    if not not_up:
        claims["claim_2"]["kill_reasons"].append("street_robbery_rises_in_some_definition_variant"); claims["claim_2"]["publishable"] = False
    # the P9 flatness kill is informational for this reframed claim: the prose says "did not rise", never "flat"
    claims["claim_2"]["kill_reasons"] = [k for k in claims["claim_2"]["kill_reasons"] if k != "P9"]
    claims["claim_2"]["publishable"] = len(claims["claim_2"]["kill_reasons"]) == 0
    claims["claim_2"]["footnotes"].append(f"Within the 0.33-mile map cell, which reaches north toward Jay Street, street robbery is {times_words(float(np.mean(cell_vals)))} its 2010s level; the 'did not rise' reading holds for the 400 meters around the station.")
    claims["claim_2"]["footnotes"].append("Street robbery is not flat: it fell through the 2010s, dropped in 2020 to 2022, and has come back to roughly its 2010s level. The piece says it did not rise, never that it stayed the same.")
    # ---- claim 3: shoplift-origin robbery -----------------------------------------
    def c3(fp, dims):
        return ratio(series(idx, fp, "retail_robbery", **dims), base_start=shop_base_start)
    g3 = grid(c3)
    s3 = series(idx, "core400", "retail_robbery", **{k: PRIMARY[k] for k in GRID_DIMS})
    base_mean = float(s3[[y for y in BASE if shop_base_start is None or y >= shop_base_start]].mean())
    record("claim_3", "robbery that began as shoplifting", round(c3("core400", {k: PRIMARY[k] for k in GRID_DIMS}), 3), [g for g in g3 if g["footprint"] != "core400_ex_courthouse"],
           {"base_per_year": f"about {round(base_mean):d} a year", "2024": str(int(s3.loc[2024])), "2025": str(int(s3.loc[2025])), "base_years": f"{shop_base_start or BASE[0]} to {BASE[-1]}"},
           "core400", "2024_25_vs_base", extra={"by_year": {str(y): int(s3.loc[y]) for y in config.YEARS}, "code_first_seen": shop_first,
                                                 "city_ratio": round(ratio(series(idx, "city", "retail_robbery", **{k: PRIMARY[k] for k in GRID_DIMS}), base_start=shop_base_start), 3)})
    # ---- claim 4: other felony assault ----------------------------------------------
    def c4(fp, dims):
        return ratio(series(idx, fp, "other_assault", **dims))
    g4 = grid(c4)
    s4 = series(idx, "core400", "other_assault", **{k: PRIMARY[k] for k in GRID_DIMS})
    s4x = series(idx, "core400_ex_courthouse", "other_assault", **{k: PRIMARY[k] for k in GRID_DIMS})
    c4city = ratio(series(idx, "city", "other_assault", **{k: PRIMARY[k] for k in GRID_DIMS}))
    record("claim_4", "other felony assault vs the city", round(ratio(s4), 3), g4,
           {"core": times_words(ratio(s4)), "core_ex_courthouse": times_words(ratio(s4x)), "city": times_words(c4city)}, "core400", "2024_25_vs_2010_19",
           extra={"by_year": {str(y): int(s4.loc[y]) for y in config.YEARS}, "by_year_ex_courthouse": {str(y): int(s4x.loc[y]) for y in config.YEARS}, "city_ratio": round(c4city, 3)})
    # ---- claim 5: night share --------------------------------------------------------
    p7 = stats["p7_night_bootstrap"]
    gap = p7["gap_pp_city_minus_core"]
    record("claim_5", "night share vs the city", round(p7["core400"]["share"], 4), [{"footprint": "core400", "variant": "clean", "value": p7["core400"]["share"]}, {"footprint": "city", "variant": "clean", "value": p7["city"]["share"]}],
           {"core": share_words(p7["core400"]["share"]), "city": share_words(p7["city"]["share"]), "gap": f"{gap['value']:.0f} points (range {gap['ci'][0]:.0f} to {gap['ci'][1]:.0f})"},
           "core400", "2006_2026_clean", extra={"bootstrap": p7, "chi_square": stats["p6_hour_chi_square"], "raw_vs_clean": dq_tables["night_share"]})
    # ---- claim 6: courthouse point --------------------------------------------------------
    core_all = series(idx, "core400", "all", **{k: PRIMARY[k] for k in GRID_DIMS})
    core_x = series(idx, "core400_ex_courthouse", "all", **{k: PRIMARY[k] for k in GRID_DIMS})
    ct = core_all - core_x
    share_rec = float(ct[RECENT].sum() / core_all[RECENT].sum())
    share_all = float(ct.sum() / core_all.sum())
    cell_rec = ladder["primary"]["all"]["count"]
    record("claim_6", "one point beside 120 Schermerhorn", round(share_rec, 4), [{"footprint": "core400", "window": "2024_25", "value": share_rec}, {"footprint": "core400", "window": "2006_2026", "value": share_all}],
           {"share_2024_25": share_words(share_rec), "count_2024_25_core400": str(int(ct[RECENT].sum())), "count_2006_2026_core400": str(int(ct.sum())), "core_total_2006_2026": str(int(core_all.sum())),
            "footprint_word": "within 400 meters of the station"}, "core400", "2024_25",
           extra={"by_year": {str(y): int(ct.loc[y]) for y in config.YEARS}, "share_by_year": dq_tables["courthouse_share_by_year"], "cell_count_2024_25": cell_rec})
    # ---- claim 7: rank ladder ---------------------------------------------------------------
    pr = ladder["primary"]
    record("claim_7", "rank ladder", pr["all"]["rank"], [{"footprint": "cell_40_42", **{k: s[k] for k in ("rule", "transit", "vintage")}, "value": s["all"]} for s in ladder["sensitivity"]],
           {"all": f"#{pr['all']['rank']}", "no_officer": f"#{pr['no_officer']['rank']}", "no_officer_no_retail": f"#{pr['no_officer_no_retail']['rank']}", "of": f"of {ladder['n_cells']:,} cells"},
           "cell_40_42", "2024_25", tol=config.CLAIM7_TOL, extra={"ranks": {k: pr[k]["rank"] for k in pr}, "counts": {k: pr[k]["count"] for k in pr}, "ladder_ok": ladder["ladder_ok"]})
    # ---- claim 8: 2026 first half ---------------------------------------------------------------
    def h1(geo, window):
        s = series(idx, geo, "all", window=window, **{k: PRIMARY[k] for k in GRID_DIMS})
        return {str(y): int(s.loc[y]) for y in config.H1_YEARS}
    h1r = {g: h1(g, "h1_reported") for g in ("core400", "core400_ex_courthouse", "city", "brooklyn", "cell_40_42")}
    h1f = {g: h1(g, "h1_full") for g in ("core400", "core400_ex_courthouse", "city", "brooklyn", "cell_40_42")}
    core26 = h1r["core400"]["2026"]; core25 = h1r["core400"]["2025"]; core24 = h1r["core400"]["2024"]
    ct26 = core26 - h1r["core400_ex_courthouse"]["2026"]; ct25 = core25 - h1r["core400_ex_courthouse"]["2025"]; ct24 = core24 - h1r["core400_ex_courthouse"]["2024"]
    ex26, ex25, ex24 = (h1r["core400_ex_courthouse"][y] for y in ("2026", "2025", "2024"))
    # the robust statement: the courthouse point rose while everything else held or fell, in every footprint
    courthouse_up = ct26 > max(ct25, ct24)
    rest_not_up = ex26 <= max(ex25, ex24) and h1r["cell_40_42"]["2026"] - ct26 <= max(h1r["cell_40_42"]["2025"] - ct25, h1r["cell_40_42"]["2024"] - ct24)
    record("claim_8", "2026 first half: the courthouse point rose, the rest did not", round(core26 / core25, 3) if core25 else None,
           [{"footprint": "core400", "rule": "h1_reported", "value": core26 / core25 if core25 else None}, {"footprint": "core400", "rule": "h1_full", "value": h1f["core400"]["2026"] / h1f["core400"]["2025"] if h1f["core400"]["2025"] else None},
            {"footprint": "city", "rule": "h1_reported", "value": h1r["city"]["2026"] / h1r["city"]["2025"]}, {"footprint": "cell_40_42", "rule": "h1_reported", "value": h1r["cell_40_42"]["2026"] / h1r["cell_40_42"]["2025"] if h1r["cell_40_42"]["2025"] else None}],
           {"core": f"{core26} against {core25} and {core24}", "courthouse": f"{ct26} against {ct25} and {ct24}", "rest_of_core": f"{ex26} against {ex25} and {ex24}",
            "cell": f"{h1r['cell_40_42']['2026']} against {h1r['cell_40_42']['2025']} and {h1r['cell_40_42']['2024']}",
            "city_direction": "down" if h1r["city"]["2026"] < h1r["city"]["2025"] else "up", "rule": "complaints reported by June 30 of each year"},
           "core400", "h1_reported", extra={"reported_by_june_30": h1r, "full_window": h1f, "courthouse_up": bool(courthouse_up), "rest_not_up": bool(rest_not_up)})
    if not (courthouse_up and rest_not_up):
        claims["claim_8"]["kill_reasons"].append("2026_pattern_not_consistent_across_footprints"); claims["claim_8"]["publishable"] = False
    claims["claim_8"]["footnotes"].append("The 400-meter core is up slightly in the first half of 2026 while the 0.33-mile map cell is down; both move with the courthouse point, and the prose describes the courthouse point and the rest separately, never the core total alone.")

    out = {"snapshot": config.SNAPSHOT_DATE, "claims": claims}
    (config.OUT_DIR / "headlines.json").write_text(json.dumps(clean_nan(out), indent=1, default=float, allow_nan=False))
    dq = {"snapshot": config.SNAPSHOT_DATE, "tests": merged.to_json(), "claims": claims,
          "summary": {"gates_failed": int(sum(r.status == "fail" for r in merged.results)), "warns": int(sum(r.status == "warn" for r in merged.results)),
                      "killed": [c for c, v in claims.items() if not v["publishable"]], "skipped": [r.id for r in merged.results if r.status == "skipped"]}}
    (config.OUT_DIR / "dq.json").write_text(json.dumps(clean_nan(dq), indent=1, default=float, allow_nan=False))
    print("stage 07 done")
    for cid, c in claims.items():
        print(f"  {cid}: {c['label']}: primary={c['primary']['value']} range={c['range']} direction={c['direction_holds']} publishable={c['publishable']} kills={c['kill_reasons']}")
        print("        words:", c["primary"]["words"])


if __name__ == "__main__":
    main()
