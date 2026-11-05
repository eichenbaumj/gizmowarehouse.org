"""Stage 06: inference. P1 Poisson/NB observed vs expected given the city trend; P2 Wheeler z; P3 placebo
percentile across cells; P4 leave-one-year-out; P5 split-half; P6 hour-profile chi-square; P7 bootstrap
night shares; P8 weekday chi-square. Writes output/stats.json and output/stats_dq.json."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib import stats as st  # noqa: E402
from lib.dq import Registry  # noqa: E402

BASE = list(range(config.BASE_YEARS[0], config.BASE_YEARS[1] + 1))
RECENT = list(config.RECENT_YEARS)
B = int(os.environ.get("HS_B", config.BOOTSTRAP_B))


def main() -> None:
    reg = Registry()
    out: dict = {}
    v = pd.read_parquet(config.OUT_DIR / "violent_citywide.parquet")
    vp = v[v["violent_primary"]].copy()
    panel = pd.read_parquet(config.OUT_DIR / "cell_year_class.parquet")
    core = vp[vp["dist_m"] <= 400]
    core_ex = core[~core["at_courthouse_point"]]
    city = vp

    def yearly(df, cls=None):
        d = df if cls is None else df[df["cls"] == cls]
        return d.groupby("year").size().reindex(config.YEARS, fill_value=0)

    # ---- P1 / P2: observed vs expected given the city trend, by class --------
    cell_panel = panel.groupby(["cell_id", "year"])["n"].sum().unstack(fill_value=0)
    cell_base = cell_panel[BASE].mean(axis=1)
    cell_rec = cell_panel[RECENT].mean(axis=1)
    city_y = yearly(city)
    city_ratio = city_y[RECENT].mean() / city_y[BASE].mean()
    alpha = st.nb_dispersion(cell_rec.to_numpy(), (cell_base * city_ratio).to_numpy())
    p1 = {}
    for label, df in (("core400", core), ("core400_ex_courthouse", core_ex)):
        p1[label] = {}
        for cls in [None] + config.CLASSES:
            cy = yearly(city, cls); ky = yearly(df, cls)
            exp = st.expected_from_city(ky[BASE].mean(), cy[BASE].mean(), cy[RECENT].mean())
            obs = ky[RECENT].mean()
            pz, pp = st.poisson_z(obs * len(RECENT), exp * len(RECENT))
            nz, npv = st.nb_z(obs * len(RECENT), exp * len(RECENT), alpha)
            wz = st.wheeler_z(obs, ky[BASE].mean())
            p1[label][cls or "all"] = {"observed_per_year": round(float(obs), 2), "expected_per_year": round(float(exp), 2),
                                       "ratio_obs_exp": round(float(obs / exp), 3) if exp else None,
                                       "poisson_z": round(pz, 2), "nb_z": round(nz, 2), "nb_alpha": round(alpha, 4), "wheeler_z": round(wz, 2)}
    out["p1_observed_vs_expected"] = p1
    nbz = p1["core400"]["all"]["nb_z"]
    reg.kill_if("P1", "inference", "core growth exceeds the city trend (negative binomial z)", nbz < config.KILL_NB_Z, p1["core400"]["all"], config.KILL_NB_Z,
                f"core 2024-25 observed {p1['core400']['all']['observed_per_year']}/yr vs {p1['core400']['all']['expected_per_year']}/yr expected on the city trend; NB z {nbz}; "
                f"ex-courthouse NB z {p1['core400_ex_courthouse']['all']['nb_z']}", ["claim_1"],
                "The block's rise is within what the citywide trend and ordinary cell-to-cell variation would produce.")
    reg.report("P2", "inference", "Wheeler z by class", {k: p1["core400"][k]["wheeler_z"] for k in p1["core400"]}, f"all-violent Wheeler z {p1['core400']['all']['wheeler_z']}", ["claim_1"])

    # ---- P3: placebo across cells ---------------------------------------------
    exp_cells = cell_base * city_ratio
    zc = (cell_rec - exp_cells) / np.sqrt(exp_cells + alpha * exp_cells ** 2)
    ok = cell_base >= config.COMPARATOR_BASE_MIN
    top = cell_base >= cell_base[cell_base > 0].quantile(1 - config.COMPARATOR_TOP_DECILE)
    me = float(zc.loc[config.CELL_ID])
    pct_ok = float((zc[ok] < me).mean() * 100)
    pct_top = float((zc[top] < me).mean() * 100)
    out["p3_placebo"] = {"cell_nb_z": round(me, 2), "percentile_base_ge_20": round(pct_ok, 1), "n_base_ge_20": int(ok.sum()),
                         "percentile_top_decile": round(pct_top, 1), "n_top_decile": int(top.sum()),
                         "top_cells_by_z": [{"cell_id": c, "z": round(float(z), 2)} for c, z in zc[ok].sort_values(ascending=False).head(10).items()]}
    reg.kill_if("P3", "inference", "placebo percentile of the cell's z among comparable cells", pct_top < config.KILL_P3_PERCENTILE, out["p3_placebo"], config.KILL_P3_PERCENTILE,
                f"cell z {me:.2f} is at the {pct_top:.1f} percentile of {int(top.sum())} top-decile cells ({pct_ok:.1f} of {int(ok.sum())} with base >= 20)", ["claim_1"],
                "Many comparable cells moved as much as this one; the rise is not singled out by the data.")

    # ---- P4: leave-one-year-out; P5 split-half ---------------------------------
    p4 = {}
    kills4 = []
    warns4 = []
    for cid, (df, cls) in {"claim_1": (core, None), "claim_3": (core, "retail_robbery"), "claim_4": (core, "other_assault")}.items():
        ky = yearly(df, cls)
        r = st.loyo_ratios(ky[BASE], ky[RECENT])
        p4[cid] = r
        if not r["direction_holds"]:
            kills4.append(cid)
        if r["full"] and (r["max"] - r["min"]) / r["full"] > config.WARN_LOYO_RANGE * 2:
            warns4.append(cid)
    out["p4_loyo"] = p4
    for cid in p4:
        reg.kill_if(f"P4_{cid}", "inference", f"leave-one-year-out direction holds ({cid})", cid in kills4, {"min": round(p4[cid]["min"], 2), "max": round(p4[cid]["max"], 2), "full": round(p4[cid]["full"], 2)}, "direction",
                    f"ratio {p4[cid]['full']:.2f}, range {p4[cid]['min']:.2f} to {p4[cid]['max']:.2f} dropping any one year", [cid],
                    "The comparison flips when a single year is dropped.")
        reg.warn_if(f"P4w_{cid}", "inference", f"leave-one-year-out magnitude stable ({cid})", cid in warns4, {"min": round(p4[cid]["min"], 2), "max": round(p4[cid]["max"], 2)}, config.WARN_LOYO_RANGE,
                    f"range width {(p4[cid]['max'] - p4[cid]['min']) / p4[cid]['full']:.0%} of the point estimate", [cid],
                    "The size of this change depends noticeably on which years are included.")
    p5 = {}
    for cid, (df, cls) in {"claim_1": (core, None), "claim_3": (core, "retail_robbery"), "claim_4": (core, "other_assault")}.items():
        d = df if cls is None else df[df["cls"] == cls]
        halves = {}
        for name, m in (("odd_months", d["month"] % 2 == 1), ("even_months", d["month"] % 2 == 0), ("jan_jun", d["month"] <= 6), ("jul_dec", d["month"] > 6)):
            ky = d[m].groupby("year").size().reindex(config.YEARS, fill_value=0)
            halves[name] = float(ky[RECENT].mean() / ky[BASE].mean()) if ky[BASE].mean() else None
        agree = all((x > 1) == (list(halves.values())[0] > 1) for x in halves.values() if x is not None)
        p5[cid] = {"halves": {k: round(x, 2) if x else None for k, x in halves.items()}, "agree": agree}
        reg.kill_if(f"P5_{cid}", "inference", f"split-half agreement ({cid})", not agree, p5[cid], "direction", f"halves {p5[cid]['halves']}", [cid],
                    "Alternate halves of the data disagree on the direction of this change.")
    out["p5_split_half"] = p5

    # ---- claim 2: street robbery flat ------------------------------------------
    sr = yearly(core, "street_robbery").loc[2006:2025]
    tr = st.poisson_trend(sr.index.to_numpy(), sr.to_numpy())
    mm = float(sr.max() / sr.min()) if sr.min() else np.inf
    flat = tr.get("ci_contains_zero", False) and mm < config.FLAT_MAXMIN
    out["claim_2_street_robbery"] = {"by_year": {int(k): int(x) for k, x in sr.items()}, "trend": tr, "max_over_min": round(mm, 2), "flat": bool(flat),
                                     "city_trend": st.poisson_trend(np.array(range(2006, 2026)), yearly(city, "street_robbery").loc[2006:2025].to_numpy())}
    reg.kill_if("P9", "inference", "street robbery flat 2006-2025 (slope CI spans zero, max/min < 1.5)", not flat,
                {"pct_per_year": round(tr.get("pct_per_year", np.nan), 2), "ci": [round(x, 4) for x in tr.get("ci", [np.nan, np.nan])], "max_over_min": round(mm, 2)}, {"max_over_min": config.FLAT_MAXMIN},
                f"slope {tr.get('pct_per_year', float('nan')):+.1f}%/yr (CI {tr.get('ci', [None, None])}), max/min {mm:.2f}", ["claim_2"],
                "Street robbery is not flat by the stated test; the piece says it changed little rather than not at all.")

    # ---- P6 / P7 / P8: time profiles ---------------------------------------------
    clean = vp[~vp["default_time"]]
    def hist(df, col="hour", k=24):
        return np.bincount(df[col].dropna().astype(int).to_numpy(), minlength=k)[:k]
    zones = {"core400": clean[clean["dist_m"] <= 400], "street_stores": clean[(clean["dist_m"] <= 400) & ~clean["at_courthouse_point"] & ~clean["transit"]],
             "courthouse": clean[clean["at_courthouse_point"]], "transit": clean[(clean["dist_m"] <= 400) & clean["transit"] & ~clean["at_courthouse_point"]]}
    city_h = hist(clean)
    p6 = {}
    for g, df in zones.items():
        s, p = st.chi_square_profile(hist(df), city_h)
        p6[g] = {"stat": round(s, 1), "p": p, "n": int(len(df))}
    out["p6_hour_chi_square"] = p6
    reg.kill_if("P6", "inference", "core hour profile differs from the city (chi-square, default times excluded)", p6["core400"]["p"] >= config.CLOCK_P, p6, config.CLOCK_P,
                f"core chi-square {p6['core400']['stat']} (p={p6['core400']['p']:.2g}, n={p6['core400']['n']})", ["claim_5"],
                "The block's hour-of-day pattern is not distinguishable from the city's; the clock stage does not ship.")
    p7 = {}
    for g, df in zones.items():
        m, lo, hi = st.bootstrap_share(df["night"].to_numpy(), B=B)
        p7[g] = {"share": round(m, 4), "ci": [round(lo, 4), round(hi, 4)], "n": int(len(df))}
    m, lo, hi = st.bootstrap_share(clean["night"].to_numpy(), B=B)
    p7["city"] = {"share": round(m, 4), "ci": [round(lo, 4), round(hi, 4)], "n": int(len(clean))}
    bk = clean[clean["brooklyn"]]
    m, lo, hi = st.bootstrap_share(bk["night"].to_numpy(), B=B)
    p7["brooklyn"] = {"share": round(m, 4), "ci": [round(lo, 4), round(hi, 4)], "n": int(len(bk))}
    g, glo, ghi = st.bootstrap_gap(zones["core400"]["night"].to_numpy(), clean["night"].to_numpy(), B=B)
    p7["gap_pp_city_minus_core"] = {"value": round(g, 2), "ci": [round(glo, 2), round(ghi, 2)]}
    out["p7_night_bootstrap"] = p7
    reg.report("P7", "inference", "night shares with bootstrap intervals", p7, f"core {p7['core400']['share']:.1%} [{p7['core400']['ci'][0]:.1%}, {p7['core400']['ci'][1]:.1%}] vs city {p7['city']['share']:.1%}; gap {g:.1f} pp [{glo:.1f}, {ghi:.1f}]", ["claim_5"])
    s, p = st.chi_square_profile(hist(zones["core400"], "dow", 7), hist(clean, "dow", 7))
    out["p8_weekday_chi_square"] = {"stat": round(s, 1), "p": p, "core_dow": hist(zones["core400"], "dow", 7).tolist(), "city_dow": hist(clean, "dow", 7).tolist()}
    reg.report("P8", "inference", "weekday profile vs city", out["p8_weekday_chi_square"], f"chi-square {s:.1f} (p={p:.2g})", ["claim_5"])

    (config.OUT_DIR / "stats.json").write_text(json.dumps(out, indent=1, default=float))
    reg.save(config.OUT_DIR / "stats_dq.json")
    print("stage 06 done; kills:", reg.kills())


if __name__ == "__main__":
    main()
