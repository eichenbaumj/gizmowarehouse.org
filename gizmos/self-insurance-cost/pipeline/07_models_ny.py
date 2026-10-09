"""Stage 07: the New York test.

Inputs: output/labels_inferred.parquet (entity-level decade means + labels), output/ny_panel.parquet.
Outputs: output/models_ny.json  {specs: [...], sample: {...}, strata: [...]}
         output/switcher_candidates.csv

Pre-registered primary spec (SCOPING.md): coarsened exact matching within class x population bin x region
on 2015–2024 entity means of real cost of risk per resident; ratio of means (self-insured / covered) with a
county-clustered bootstrap. Supporting specs: ratio of medians; pooled OLS on log cost per resident with
covariates; permutation test on the matched difference; the per-dollar-of-spending outcome; judgments-only
(mechanism); the one-bad-year (p90) statistic. Every spec is a record {spec_id, outcome, sample, n_self,
n_covered, coef, lo, hi, se_type, note}. Treatment comes from the document label when present and the
premium signature otherwise; label_source is carried so the core-only cut can be reported separately.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

import config

SELF = {"self_insured", "self_insured_with_excess"}
COVERED = {"pool", "commercial"}
REGION = {
    "NYC suburbs": {"Nassau", "Suffolk", "Westchester", "Rockland", "Putnam"},
    "Hudson Valley": {"Orange", "Dutchess", "Ulster", "Sullivan", "Columbia", "Greene", "Delaware"},
    "Capital-North": {"Albany", "Rensselaer", "Saratoga", "Schenectady", "Schoharie", "Warren", "Washington",
                      "Fulton", "Montgomery", "Hamilton", "Essex", "Clinton", "Franklin", "St. Lawrence",
                      "Jefferson", "Lewis", "Herkimer", "Oneida", "Otsego"},
}
RNG = np.random.default_rng(20261008)
B = 300


def region_of(county: str) -> str:
    for r, s in REGION.items():
        if county in s:
            return r
    return "Western-Central"


def treat_of(row) -> str:
    if row["label_source"] == "document":
        return "self" if row["structure"] in SELF else "covered" if row["structure"] in COVERED else "other"
    return {"signature_self_insured": "self", "signature_insured": "covered"}.get(row["sig_structure"], "other")


def winsor(s: pd.Series, q: float = 0.99) -> pd.Series:
    hi = s.quantile(q)
    return s.clip(upper=hi)


def matched_diff(df: pd.DataFrame, y: str, stat: str = "mean") -> tuple[float, int, int, list]:
    """Weighted (by n_self) average of within-stratum log differences self - covered. Returns exp() ratio."""
    diffs, strata = [], []
    for key, g in df.groupby("stratum"):
        a, b = g[g.treat == "self"][y], g[g.treat == "covered"][y]
        if len(a) == 0 or len(b) == 0:
            continue
        f = np.mean if stat == "mean" else np.median
        d = np.log(f(a) + 1e-9) - np.log(f(b) + 1e-9)
        diffs.append((d, len(a)))
        strata.append({"stratum": key, "n_self": int(len(a)), "n_covered": int(len(b)),
                       "self": round(float(f(a)), 2), "covered": round(float(f(b)), 2)})
    if not diffs:
        return float("nan"), 0, 0, strata
    w = np.array([n for _, n in diffs], dtype=float)
    d = np.array([d for d, _ in diffs])
    return float(np.exp(np.sum(w * d) / w.sum())), int(sum(s["n_self"] for s in strata)), int(sum(s["n_covered"] for s in strata)), strata


def cluster_boot(df: pd.DataFrame, y: str, stat: str = "mean") -> tuple[float, float]:
    counties = df["county"].unique()
    vals = []
    for _ in range(B):
        pick = RNG.choice(counties, size=len(counties), replace=True)
        parts = [df[df.county == c] for c in pick]
        r, _, _, _ = matched_diff(pd.concat(parts), y, stat)
        if np.isfinite(r):
            vals.append(r)
    if len(vals) < 50:
        return float("nan"), float("nan")
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def permutation_p(df: pd.DataFrame, y: str, observed: float, n: int = 400) -> float:
    cnt = 0
    for _ in range(n):
        d2 = df.copy()
        d2["treat"] = d2.groupby("stratum")["treat"].transform(lambda s: RNG.permutation(s.values))
        r, _, _, _ = matched_diff(d2, y)
        if np.isfinite(r) and abs(np.log(r)) >= abs(np.log(observed)):
            cnt += 1
    return cnt / n


def switcher_candidates(panel: pd.DataFrame) -> pd.DataFrame:
    """Single-break level shift in real insurance per capita, 1996–2024, >=3 years each side, ratio >=3 or <=1/3."""
    y0, y1 = config.PANEL_YEARS
    p = panel[panel["cls"].isin(config.OSC_CORE_CLASSES) & panel["fy"].between(y0, y1)].copy()
    rows = []
    for (cls, mc), g in p.groupby(["cls", "muni_code"]):
        g = g.sort_values("fy")
        s = np.log1p(g["ins_pc"].clip(lower=0).values)
        yrs = g["fy"].values
        if len(s) < 8:
            continue
        best = None
        for k in range(3, len(s) - 3):
            a, b = s[:k], s[k:]
            sse = ((a - a.mean()) ** 2).sum() + ((b - b.mean()) ** 2).sum()
            if best is None or sse < best[0]:
                best = (sse, k, a.mean(), b.mean())
        sse, k, ma, mb = best
        ratio = np.exp(mb) / max(np.exp(ma), 1e-9)
        if ratio >= 3 or ratio <= 1 / 3:
            jc = g["jc_pc"].values
            rows.append({"cls": cls, "muni_code": mc, "entity_name": g["entity_name"].iloc[-1], "county": g["county"].iloc[-1],
                         "break_year": int(yrs[k]), "ins_pc_before": round(float(np.expm1(ma)), 2), "ins_pc_after": round(float(np.expm1(mb)), 2),
                         "premium_ratio": round(float(ratio), 2), "direction": "to_insured" if ratio > 1 else "to_self_insured",
                         "jc_pc_before": round(float(np.nanmean(jc[:k])), 2), "jc_pc_after": round(float(np.nanmean(jc[k:])), 2),
                         "pop_mean": round(float(g["population"].mean()), 0)})
    out = pd.DataFrame(rows)
    if len(out):
        out["abs_shift"] = (out["ins_pc_after"] - out["ins_pc_before"]).abs() * out["pop_mean"]
        out = out.sort_values("abs_shift", ascending=False)
    return out


def main(argv: list[str] | None = None) -> int:
    ent = pd.read_parquet(config.LABELS_INFERRED_PARQUET)
    panel = pd.read_parquet(config.NY_PANEL_PARQUET)
    ent["region"] = ent["county"].map(region_of)
    ent["treat"] = ent.apply(treat_of, axis=1)
    base = ent[(ent["n_years"] >= 8) & ~ent["jc_contaminated"] & ~ent["coded_elsewhere_holdout"]
               & ent["treat"].isin(["self", "covered"]) & (ent["pop_mean"] > 0)].copy()
    base["pop_bin"] = base["pop_bin"].astype(int)
    base["stratum"] = base["cls"] + "|" + base["pop_bin"].astype(str) + "|" + base["region"]
    for c in ("cor_pc_mean", "cor_op_pc_mean", "jc_pc_mean", "cor_share_mean", "cor_pc_p90"):
        base[c + "_w"] = base.groupby("cls")[c].transform(winsor)
    specs = []

    def run(sample_name: str, df: pd.DataFrame) -> None:
        if df["treat"].nunique() < 2:
            return
        for y, label in (("cor_pc_mean_w", "cost of risk per resident, 2024$"), ("cor_op_pc_mean_w", "operating-fund cost of risk per resident"),
                         ("cor_share_mean_w", "cost of risk per dollar of spending"), ("jc_pc_mean_w", "judgments per resident (mechanism)"),
                         ("cor_pc_p90_w", "90th-percentile year, cost per resident")):
            r, ns, nc, strata = matched_diff(df, y)
            lo, hi = cluster_boot(df, y)
            sid = f"ny_matched_decade_mean_{y.replace('_mean_w','').replace('_w','')}" + ("" if sample_name == "all" else f"__{sample_name}")
            if y == "cor_pc_mean_w" and sample_name == "document_core_classbin":
                sid = config.PRIMARY_SPEC
            specs.append({"spec_id": sid, "outcome": label, "sample": sample_name, "estimator": "CEM ratio of means (self/covered), class x pop-bin x region",
                          "n_self": ns, "n_covered": nc, "coef": round(r, 3) if np.isfinite(r) else None,
                          "lo": round(lo, 3) if np.isfinite(lo) else None, "hi": round(hi, 3) if np.isfinite(hi) else None,
                          "se_type": "county-cluster bootstrap 95%", "n": ns + nc,
                          "perm_p": permutation_p(df, y, r) if np.isfinite(r) and y == "cor_pc_mean_w" and sample_name.startswith("document") else None,
                          "exploratory": not sample_name.startswith("document"),
                          "strata": strata if y == "cor_pc_mean_w" else None})
            rm, _, _, _ = matched_diff(df, y, "median")
            specs.append({"spec_id": sid + "__medians", "outcome": label, "sample": sample_name, "estimator": "CEM ratio of medians",
                          "n_self": ns, "n_covered": nc, "coef": round(rm, 3) if np.isfinite(rm) else None, "lo": None, "hi": None,
                          "se_type": "none", "n": ns + nc, "exploratory": True})
        # OLS twin
        d = df.copy()
        d["ly"] = np.log(d["cor_pc_mean_w"] + 1)
        d["lpop"] = np.log(d["pop_mean"])
        d["self"] = (d["treat"] == "self").astype(int)
        try:
            m = smf.ols("ly ~ self + lpop + I(lpop**2) + police_share + capital_share + C(cls) + C(region)", data=d.fillna({"police_share": 0, "capital_share": 0})
                        ).fit(cov_type="cluster", cov_kwds={"groups": d["county"]})
            b, se = m.params["self"], m.bse["self"]
            specs.append({"spec_id": "ny_ols_log_cor_pc" + ("" if sample_name == "all" else f"__{sample_name}"), "outcome": "log(1 + cost of risk per resident)",
                          "sample": sample_name, "estimator": "OLS, class + region FE, size and service-mix covariates", "n_self": int(d["self"].sum()),
                          "n_covered": int((1 - d["self"]).sum()), "coef": round(float(np.exp(b)), 3), "lo": round(float(np.exp(b - 1.96 * se)), 3),
                          "hi": round(float(np.exp(b + 1.96 * se)), 3), "se_type": "county-clustered", "n": int(m.nobs), "note": "exp(coef) = ratio"})
        except Exception as e:  # noqa: BLE001
            specs.append({"spec_id": "ny_ols_log_cor_pc", "sample": sample_name, "coef": None, "lo": None, "hi": None, "n": 0, "note": f"OLS failed: {e}"})

    run("all", base)
    run("document_core", base[base["label_source"] == "document"])
    core2 = base[base["label_source"] == "document"].copy()
    core2["stratum"] = core2["cls"] + "|" + core2["pop_bin"].astype(str)
    run("document_core_classbin", core2)
    for cls in config.OSC_CORE_CLASSES:
        run(f"class_{cls}", base[base["cls"] == cls])
    run("drop_nyc_suburbs", base[base["region"] != "NYC suburbs"])

    # ---- sensitivities on the document core: windows, accrual view, defense costs ----
    core_names = set(base.loc[base["label_source"] == "document", "entity_name"])
    pc = panel[panel["entity_name"].isin(core_names)].sort_values(["entity_name", "fy"]).copy()
    pc["dW"] = pc.groupby("entity_name")["claims_liability"].diff().fillna(0.0)
    pc["accrual_pc"] = ((pc["judgments"] + pc["dW"]) * pc["cpi_factor"] + pc["ins_premium_real"]) / pc["population"]
    pc["cor_law_pc"] = (pc["cost_of_risk_real"] + pc["law_exp_real"]) / pc["population"]
    meta = base[base["label_source"] == "document"][["entity_name", "cls", "county", "region", "treat", "pop_bin"]]
    for (y0, y1), tag in (((2015, 2019), "w2015_2019"), ((2010, 2019), "w2010_2019"), ((2015, 2024), "w2015_2024")):
        w = pc[pc["fy"].between(y0, y1)].groupby("entity_name").agg(cor_pc=("cor_pc", "mean"), accrual_pc=("accrual_pc", "mean"),
                                                                     cor_law_pc=("cor_law_pc", "mean"), n=("fy", "count")).reset_index()
        w = w[w["n"] >= max(3, (y1 - y0 + 1) * 0.6)].merge(meta, on="entity_name")
        w["stratum"] = w["cls"] + "|" + w["pop_bin"].astype(str)
        for y, label in (("cor_pc", "cost of risk per resident"), ("accrual_pc", "accrual cost per resident (judgments + change in claims payable + premiums)"),
                         ("cor_law_pc", "cost of risk + law department per resident")):
            if tag == "w2015_2024" and y == "cor_pc":
                continue
            w[y + "_w"] = w.groupby("cls")[y].transform(winsor)
            r, ns, nc, strata = matched_diff(w, y + "_w")
            lo, hi = cluster_boot(w, y + "_w")
            specs.append({"spec_id": f"ny_core_classbin_{y}__{tag}", "outcome": label, "sample": f"document_core_classbin {y0}-{y1}",
                          "estimator": "CEM ratio of means, class x pop-bin", "n_self": ns, "n_covered": nc,
                          "coef": round(r, 3) if np.isfinite(r) else None, "lo": round(lo, 3) if np.isfinite(lo) else None,
                          "hi": round(hi, 3) if np.isfinite(hi) else None, "se_type": "county-cluster bootstrap 95%", "n": ns + nc, "exploratory": True})
    # ---- the argument: exposure drives the level, structure drives the swing ----------------------
    core = base[base["label_source"] == "document"].copy()
    wv = panel[panel["entity_name"].isin(set(core["entity_name"])) & panel["fy"].between(*config.HEADLINE_YEARS)]
    yoy = wv.groupby("entity_name").apply(lambda g: g["cor_pc"].std() / g["cor_pc"].mean() if g["cor_pc"].mean() > 0 else np.nan,
                                           include_groups=False).rename("yoy_cv")
    core = core.merge(yoy, on="entity_name", how="left")
    core["ly"] = np.log1p(core["cor_pc_mean_w"]); core["lpop"] = np.log(core["pop_mean"]); core["self"] = (core["treat"] == "self").astype(int)
    core["police_share"] = core["police_share"].fillna(0); core["capital_share"] = core["capital_share"].fillna(0)
    m = smf.ols("ly ~ self + lpop + police_share + capital_share + C(cls)", data=core).fit(cov_type="HC1")
    b, se = m.params["police_share"], m.bse["police_share"]
    exposure = {"police_share_coef_log": round(float(b), 3), "se": round(float(se), 3),
                "ratio_per_10pts": round(float(np.exp(b * 0.10)), 3), "lo_per_10pts": round(float(np.exp((b - 1.96 * se) * 0.10)), 3),
                "hi_per_10pts": round(float(np.exp((b + 1.96 * se) * 0.10)), 3),
                "self_ratio_same_model": round(float(np.exp(m.params["self"])), 3), "n": int(m.nobs),
                "r2_with_structure": round(float(m.rsquared), 3),
                "r2_without_structure": round(float(smf.ols("ly ~ lpop + police_share + capital_share + C(cls)", data=core).fit().rsquared), 3),
                "r2_without_police": round(float(smf.ols("ly ~ self + lpop + capital_share + C(cls)", data=core).fit().rsquared), 3)}
    het = {}
    for name, sub in (("police_governments", core[core["police_share"] > 0.02]), ("no_police_governments", core[core["police_share"] <= 0.02])):
        if sub["self"].nunique() == 2 and len(sub) >= 10:
            mm = smf.ols("ly ~ self + lpop + police_share + C(cls)", data=sub).fit(cov_type="HC1")
            bb, ss = mm.params["self"], mm.bse["self"]
            het[name] = {"n": int(len(sub)), "n_self": int(sub["self"].sum()), "ratio": round(float(np.exp(bb)), 3),
                         "lo": round(float(np.exp(bb - 1.96 * ss)), 3), "hi": round(float(np.exp(bb + 1.96 * ss)), 3)}
    by_class = {}
    for cls, sub in core.groupby("cls"):
        row = {"n_self": int(sub["self"].sum()), "n_covered": int((1 - sub["self"]).sum()),
               "yoy_cv_self": round(float(sub[sub["self"] == 1]["yoy_cv"].median()), 3) if sub["self"].sum() else None,
               "yoy_cv_covered": round(float(sub[sub["self"] == 0]["yoy_cv"].median()), 3) if (1 - sub["self"]).sum() else None}
        if sub["self"].nunique() == 2 and sub["self"].sum() >= 3 and (1 - sub["self"]).sum() >= 3:
            mm = smf.ols("ly ~ self + lpop", data=sub).fit(cov_type="HC1"); bb, ss = mm.params["self"], mm.bse["self"]
            row.update({"ratio": round(float(np.exp(bb)), 3), "lo": round(float(np.exp(bb - 1.96 * ss)), 3), "hi": round(float(np.exp(bb + 1.96 * ss)), 3)})
        by_class[cls] = row
    pol = core[core["police_share"] > 0.02].copy()
    pol["tercile"] = pd.qcut(pol["police_share"], 3, labels=["low", "mid", "high"])
    terciles = {}
    for (tc, tr), sub in pol.groupby(["tercile", "treat"], observed=True):
        terciles.setdefault(str(tc), {})[tr] = {"n": int(len(sub)), "median_cor_pc": round(float(sub["cor_pc_mean"].median()), 1),
                                              "yoy_cv": round(float(sub["yoy_cv"].median()), 3), "police_share": round(float(sub["police_share"].median()), 3)}
    volatility = {"yoy_cv_self": round(float(core[core["self"] == 1]["yoy_cv"].median()), 3),
                  "yoy_cv_covered": round(float(core[core["self"] == 0]["yoy_cv"].median()), 3),
                  "p90_over_mean_self": round(float((core[core["self"] == 1]["cor_pc_p90"] / core[core["self"] == 1]["cor_pc_mean"]).median()), 3),
                  "p90_over_mean_covered": round(float((core[core["self"] == 0]["cor_pc_p90"] / core[core["self"] == 0]["cor_pc_mean"]).median()), 3),
                  "by_class": by_class, "police_terciles": terciles,
                  "definition": "yoy_cv = std / mean of real cost of risk per resident across 2015-2024 within each government; medians by group"}
    sample = {"n_entities_total": int(len(ent)), "n_used": int(len(base)), "n_self": int((base.treat == "self").sum()),
              "n_covered": int((base.treat == "covered").sum()), "n_document": int((base.label_source == "document").sum()),
              "n_contaminated_dropped": int(ent["jc_contaminated"].sum()), "n_holdout": int(ent["coded_elsewhere_holdout"].sum()),
              "window": list(config.HEADLINE_YEARS), "snapshot": config.SNAPSHOT_DATE}
    out = {"specs": specs, "sample": sample, "exposure": exposure, "heterogeneity": het, "volatility": volatility}
    config.MODELS_NY_JSON.write_text(json.dumps(out, indent=1, default=float))
    prim = next(s for s in specs if s["spec_id"] == config.PRIMARY_SPEC)
    print(f"  primary: ratio {prim['coef']} [{prim['lo']}, {prim['hi']}] n_self {prim['n_self']} n_covered {prim['n_covered']} perm_p {prim['perm_p']}")
    sw = switcher_candidates(panel)
    sw.to_csv(config.OUTPUT_DIR / "switcher_candidates.csv", index=False)
    print(f"  switcher candidates: {len(sw)} (top by population-weighted shift listed in output/switcher_candidates.csv)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
