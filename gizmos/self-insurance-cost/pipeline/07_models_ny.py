"""Stage 07: the New York test.

Inputs: output/labels_inferred.parquet (entity-level decade means + labels), output/ny_panel.parquet.
Outputs: output/models_ny.json  {specs: [...], sample: {...}, strata: [...]}
         output/switcher_candidates.csv

Pre-registered primary spec (SCOPING.md): coarsened exact matching within class x population bin x region
on 2015–2024 entity means of real cost of risk per resident; ratio of means (self-insured / covered) with a
county-clustered bootstrap. As published, the headline (config.PRIMARY_SPEC) matches on class x population
bin only, because adding region leaves 49 of 76 governments with a peer; the region match is reported beside
it. The outcome is the liability cost of risk (operating-fund 1910/1930/1931 plus fund-family lines coded
liability from each note; audit 2026-10-10). Bands are weighted by their number of self-insured governments
and each government's average is capped at its class's 99th percentile.

Supporting specs: ratio of medians; pooled OLS twin; permutation test; per dollar of spending; judgments-only
(mechanism); all-funds and operating-only outcomes; counties and towns only; unclear labels both ways; windows,
accrual, and law-department sensitivities. Blocks: volatility (the swing, the true worst year, budget scale),
exposure (police measures on the custodial-free denominator), heterogeneity (named subgroups), big_governments
(who has no covered peer and what they hold). Every spec is a record {spec_id, outcome, sample, n_self,
n_covered, coef, lo, hi, se_type, note}.
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
B = config.B_EXPLORATORY


def region_of(county: str) -> str:
    for r, s in REGION.items():
        if county in s:
            return r
    return "Western-Central"


def held_out(ent: pd.DataFrame) -> pd.Series:
    """Document-labeled governments whose books cannot carry the comparison (reason in holdout_reason)."""
    h = ent["jc_contaminated"].astype(bool) | ent["coded_elsewhere_holdout"].astype(bool)
    if "premiums_elsewhere_holdout" in ent:
        h = h | ent["premiums_elsewhere_holdout"].astype(bool)
    return h


def usable(ent: pd.DataFrame) -> pd.DataFrame:
    return ent[(ent["n_years"] >= 8) & ~held_out(ent) & ent["treat"].isin(["self", "covered"]) & (ent["pop_mean"] > 0)].copy()


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
        if f(a) <= 0 or f(b) <= 0:  # a ratio needs two positive bills (a resample can land on a reserve-release year)
            continue
        d = np.log(f(a)) - np.log(f(b))
        diffs.append((d, len(a)))
        strata.append({"stratum": key, "n_self": int(len(a)), "n_covered": int(len(b)),
                       "self": round(float(f(a)), 2), "covered": round(float(f(b)), 2)})
    if not diffs:
        return float("nan"), 0, 0, strata
    w = np.array([n for _, n in diffs], dtype=float)
    d = np.array([d for d, _ in diffs])
    return float(np.exp(np.sum(w * d) / w.sum())), int(sum(s["n_self"] for s in strata)), int(sum(s["n_covered"] for s in strata)), strata


def cluster_boot(df: pd.DataFrame, y: str, stat: str = "mean", b: int | None = None) -> tuple[float, float]:
    counties = df["county"].unique()
    vals = []
    for _ in range(b or B):
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
    base = usable(ent)
    base["pop_bin"] = base["pop_bin"].astype(int)
    base["stratum"] = base["cls"] + "|" + base["pop_bin"].astype(str) + "|" + base["region"]
    OUT = {"cor_liab_pc_mean": "liability cost of risk per resident, 2024$",
           "cor_pc_mean": "all-funds cost of risk per resident (sensitivity)",
           "cor_op_pc_mean": "operating-fund cost of risk per resident (sensitivity)",
           "cor_strict_pc_mean": "liability cost of risk, lines coded mixed or unknown left out (sensitivity)",
           "cor_liab_share_mean": "liability cost of risk per dollar of spending",
           "jc_liab_pc_mean": "judgments per resident (mechanism)",
           "ins_liab_pc_mean": "premiums per resident (mechanism)"}
    for c in list(OUT) + ["cor_liab_pc_p90", "cor_liab_pc_max"]:
        base[c + "_w"] = base.groupby("cls")[c].transform(winsor)
    specs = []

    def run(sample_name: str, df: pd.DataFrame, prefix: str, headline: bool = False, outcomes=None, region: bool = False) -> None:
        if df["treat"].nunique() < 2:
            return
        for y in (outcomes or OUT):
            yw = y + "_w"
            r, ns, nc, strata = matched_diff(df, yw)
            big = headline and y in ("cor_liab_pc_mean", "cor_pc_mean", "cor_op_pc_mean", "cor_strict_pc_mean")
            lo, hi = cluster_boot(df, yw, b=config.B_HEADLINE if big else config.B_EXPLORATORY)
            sid = f"{prefix}_{y.replace('_mean', '')}"
            specs.append({"spec_id": sid, "outcome": OUT[y], "sample": sample_name,
                          "estimator": "CEM ratio of means (self/covered), class x pop-bin" + (" x region" if region else ""),
                          "n_self": ns, "n_covered": nc, "coef": round(r, 3) if np.isfinite(r) else None,
                          "lo": round(lo, 3) if np.isfinite(lo) else None, "hi": round(hi, 3) if np.isfinite(hi) else None,
                          "se_type": f"county-cluster bootstrap 95%, B={config.B_HEADLINE if big else config.B_EXPLORATORY}", "n": ns + nc,
                          "perm_p": permutation_p(df, yw, r) if np.isfinite(r) and sid == config.PRIMARY_SPEC else None,
                          "exploratory": not headline,
                          "strata": strata if y in ("cor_liab_pc_mean", "cor_pc_mean") else None})
            rm, _, _, mstrata = matched_diff(df, yw, "median")
            specs.append({"spec_id": sid + "__medians", "outcome": OUT[y], "sample": sample_name, "estimator": "CEM ratio of medians",
                          "n_self": ns, "n_covered": nc, "coef": round(rm, 3) if np.isfinite(rm) else None, "lo": None, "hi": None,
                          "se_type": "none", "n": ns + nc, "exploratory": True,
                          "strata": mstrata if y == "cor_liab_pc_mean" else None})
        d = df.copy()
        d["ly"] = np.log(d["cor_liab_pc_mean_w"] + 1)
        d["lpop"] = np.log(d["pop_mean"])
        d["self"] = (d["treat"] == "self").astype(int)
        try:
            m = smf.ols("ly ~ self + lpop + I(lpop**2) + police_share + capital_share + C(cls) + C(region)",
                        data=d.fillna({"police_share": 0, "capital_share": 0})).fit(cov_type="cluster", cov_kwds={"groups": d["county"]})
            b, se = m.params["self"], m.bse["self"]
            specs.append({"spec_id": f"{prefix}_ols_log_cor_liab_pc", "outcome": "log(1 + liability cost of risk per resident)",
                          "sample": sample_name, "estimator": "OLS, class + region FE, size and service-mix covariates", "n_self": int(d["self"].sum()),
                          "n_covered": int((1 - d["self"]).sum()), "coef": round(float(np.exp(b)), 3), "lo": round(float(np.exp(b - 1.96 * se)), 3),
                          "hi": round(float(np.exp(b + 1.96 * se)), 3), "se_type": "county-clustered", "n": int(m.nobs), "note": "exp(coef) = ratio",
                          "exploratory": not headline})
        except Exception as e:  # noqa: BLE001
            specs.append({"spec_id": f"{prefix}_ols_log_cor_liab_pc", "sample": sample_name, "coef": None, "lo": None, "hi": None, "n": 0,
                          "note": f"OLS failed: {e}", "exploratory": True})

    doc = base[base["label_source"] == "document"].copy()
    core2 = doc.copy()
    core2["stratum"] = core2["cls"] + "|" + core2["pop_bin"].astype(str)
    run("document_core_classbin", core2, "ny_core_classbin", headline=True)                       # the headline
    run("document_core_classbin counties and towns", core2[core2["cls"].isin(["county", "town"])], "ny_core_counties_towns", headline=True,
        outcomes=["cor_liab_pc_mean", "cor_pc_mean"])
    run("document_core class x pop-bin x region (pre-registered)", doc, "ny_core_prereg_region", headline=True,
        outcomes=["cor_liab_pc_mean", "cor_pc_mean"], region=True)
    run("all (document + premium signature)", base, "ny_all", outcomes=["cor_liab_pc_mean"])
    for cls in config.OSC_CORE_CLASSES:
        run(f"class_{cls}", core2[core2["cls"] == cls], f"ny_core_{cls}", outcomes=["cor_liab_pc_mean"])
    run("drop_nyc_suburbs", core2[core2["region"] != "NYC suburbs"], "ny_core_drop_nyc_suburbs", outcomes=["cor_liab_pc_mean"])
    # unclear and mixed labels assigned both ways
    oth = ent[(ent["label_source"] == "document") & (ent["treat"] == "other") & ~held_out(ent) & (ent["n_years"] >= 8) & (ent["pop_mean"] > 0)].copy()
    for as_, tag in (("self", "unclear_as_self"), ("covered", "unclear_as_covered")):
        o = oth.assign(treat=as_)
        both = pd.concat([doc, o], ignore_index=True)
        both["pop_bin"] = both["pop_bin"].astype(int)
        both["stratum"] = both["cls"] + "|" + both["pop_bin"].astype(str)
        both["cor_liab_pc_mean_w"] = both.groupby("cls")["cor_liab_pc_mean"].transform(winsor)
        run(f"document_core_classbin, unclear/mixed labels as {as_}", both, f"ny_core_{tag}", outcomes=["cor_liab_pc_mean"])

    # ---- sensitivities on the document core: windows, accrual view, defense costs ----
    core_names = set(doc["entity_name"])
    pc = panel[panel["entity_name"].isin(core_names)].sort_values(["entity_name", "fy"]).copy()
    pc["dW"] = pc.groupby("entity_name")["claims_liability"].diff().fillna(0.0)
    pc["accrual_pc"] = ((pc["judgments_liab"] + pc["dW"]) * pc["cpi_factor"] + pc["ins_liab_real"]) / pc["population"]
    pc["cor_law_pc"] = (pc["cost_of_risk_liab_real"] + pc["law_exp_real"]) / pc["population"]
    meta = doc[["entity_name", "cls", "county", "region", "treat", "pop_bin"]]
    for (y0, y1), tag in (((2015, 2019), "w2015_2019"), ((2020, 2024), "w2020_2024"), ((2015, 2024), "w2015_2024")):
        w = pc[pc["fy"].between(y0, y1)].groupby("entity_name").agg(cor_liab_pc=("cor_liab_pc", "mean"), accrual_pc=("accrual_pc", "mean"),
                                                                     cor_law_pc=("cor_law_pc", "mean"), n=("fy", "count")).reset_index()
        w = w[w["n"] >= max(3, (y1 - y0 + 1) * 0.6)].merge(meta, on="entity_name")
        w["stratum"] = w["cls"] + "|" + w["pop_bin"].astype(str)
        for y, label in (("cor_liab_pc", "liability cost of risk per resident"),
                         ("accrual_pc", "accrual cost per resident (judgments + change in claims payable + premiums)"),
                         ("cor_law_pc", "liability cost of risk + law department per resident")):
            if tag == "w2015_2024" and y == "cor_liab_pc":
                continue
            w[y + "_w"] = w.groupby("cls")[y].transform(winsor)
            r, ns, nc, strata = matched_diff(w, y + "_w")
            lo, hi = cluster_boot(w, y + "_w")
            specs.append({"spec_id": f"ny_core_classbin_{y}__{tag}", "outcome": label, "sample": f"document_core_classbin {y0}-{y1}",
                          "estimator": "CEM ratio of means, class x pop-bin", "n_self": ns, "n_covered": nc,
                          "coef": round(r, 3) if np.isfinite(r) else None, "lo": round(lo, 3) if np.isfinite(lo) else None,
                          "hi": round(hi, 3) if np.isfinite(hi) else None, "se_type": f"county-cluster bootstrap 95%, B={config.B_EXPLORATORY}",
                          "n": ns + nc, "exploratory": True})

    # ---- volatility: what a premium buys ------------------------------------------------------------
    core = doc.copy()
    wv = panel[panel["entity_name"].isin(core_names) & panel["fy"].between(*config.HEADLINE_YEARS)]
    def cv(s: pd.Series) -> float:
        return float(s.std() / s.mean()) if s.mean() > 0 else np.nan
    per = wv.groupby("entity_name").agg(yoy_cv=("cor_liab_pc", cv), cv_premiums=("ins_liab_pc", cv), cv_judgments=("jc_liab_pc", cv),
                                         n_neg_years=("cor_liab_pc", lambda x: int((x < 0).sum()))).reset_index()
    core = core.merge(per, on="entity_name", how="left")
    # A government whose recorded liability cost falls below zero in some year (reserve releases booked as negative
    # claims, e.g. Onondaga) has no meaningful average to measure a swing or a worst year against: counted in the level
    # comparison, left out of the swing block, and named in the chart's note.
    core["max_over_mean"] = core["cor_liab_pc_max"] / core["cor_liab_pc_mean"]
    core["p90_over_mean"] = core["cor_liab_pc_p90"] / core["cor_liab_pc_mean"]
    core["premium_share"] = core["ins_liab_pc_mean"] / core["cor_liab_pc_mean"]
    core["ly"] = np.log1p(core["cor_liab_pc_mean_w"]); core["lpop"] = np.log(core["pop_mean"]); core["self"] = (core["treat"] == "self").astype(int)
    for c in ("police_share", "capital_share", "law_enf_share", "jail_share"):
        core[c] = core[c].fillna(0)
    left_out = core[core["n_neg_years"] > 0][["muni_code", "entity_name", "cls", "treat", "n_neg_years"]].to_dict(orient="records")
    level_core = core
    core = core[core["n_neg_years"] == 0].copy()
    grp_s, grp_c = core[core["self"] == 1], core[core["self"] == 0]  # (not S/C: patsy resolves C() in this frame)
    med = lambda d, c: round(float(d[c].median()), 3)  # noqa: E731
    vcore = core[np.isfinite(core["yoy_cv"]) & (core["yoy_cv"] > 0)].copy()
    vcore["stratum"] = vcore["cls"] + "|" + vcore["pop_bin"].astype(int).astype(str)
    r_m, ns_m, nc_m, st_m = matched_diff(vcore, "yoy_cv", "median")
    lo_m, hi_m = cluster_boot(vcore, "yoy_cv", "median", b=config.B_HEADLINE)
    mv = smf.ols("np.log(yoy_cv) ~ self + lpop + C(cls)", data=vcore).fit(cov_type="HC1")
    bv, sv = mv.params["self"], mv.bse["self"]
    by_class = {}
    for cls, sub in core.groupby("cls"):
        ss, cc = sub[sub["self"] == 1], sub[sub["self"] == 0]
        by_class[cls] = {"n_self": int(len(ss)), "n_covered": int(len(cc)),
                         "yoy_cv_self": med(ss, "yoy_cv") if len(ss) else None, "yoy_cv_covered": med(cc, "yoy_cv") if len(cc) else None,
                         "max_over_mean_self": med(ss, "max_over_mean") if len(ss) else None,
                         "max_over_mean_covered": med(cc, "max_over_mean") if len(cc) else None}
    volatility = {
        "yoy_cv_self": med(grp_s, "yoy_cv"), "yoy_cv_covered": med(grp_c, "yoy_cv"), "n_self": int(len(grp_s)), "n_covered": int(len(grp_c)),
        "max_over_mean_self": med(grp_s, "max_over_mean"), "max_over_mean_covered": med(grp_c, "max_over_mean"),
        "p90_over_mean_self": med(grp_s, "p90_over_mean"), "p90_over_mean_covered": med(grp_c, "p90_over_mean"),
        "matched_ratio": round(r_m, 3), "matched_lo": round(lo_m, 3), "matched_hi": round(hi_m, 3), "matched_n": [ns_m, nc_m], "matched_strata": st_m,
        "controlled_ratio": round(float(np.exp(bv)), 3), "controlled_lo": round(float(np.exp(bv - 1.96 * sv)), 3),
        "controlled_hi": round(float(np.exp(bv + 1.96 * sv)), 3),
        "cv_premiums_self": med(grp_s, "cv_premiums"), "cv_premiums_covered": med(grp_c, "cv_premiums"),
        "cv_judgments_self": med(grp_s, "cv_judgments"), "cv_judgments_covered": med(grp_c, "cv_judgments"),
        "premium_share_self": med(grp_s, "premium_share"), "premium_share_covered": med(grp_c, "premium_share"),
        "left_out": left_out,
        "budget_share_self": round(float(grp_s["cor_liab_budget_share"].median()), 5), "budget_share_covered": round(float(grp_c["cor_liab_budget_share"].median()), 5),
        "worst_year_budget_share_self": round(float(grp_s["worst_year_budget_share"].median()), 5),
        "worst_year_budget_share_covered": round(float(grp_c["worst_year_budget_share"].median()), 5),
        "with_police_dept": {t: {"n": int(len(g)), "yoy_cv": med(g, "yoy_cv")} for t, g in core[core["has_police_dept"]].groupby("treat")},
        "no_police_dept": {t: {"n": int(len(g)), "yoy_cv": med(g, "yoy_cv")} for t, g in core[~core["has_police_dept"]].groupby("treat")},
        "by_class": by_class,
        "definition": "yoy_cv = standard deviation / mean of real liability cost of risk per resident across 2015-2024 within each government; "
                      "max_over_mean = its worst year over its average; medians by group; matched = ratio of medians within class x pop-bin, "
                      "weighted by self-insured count; controlled = OLS of log(yoy_cv) on self, log population, class (HC1)"}

    # ---- exposure: what goes with a bigger bill (custodial-free denominator) -------------------------
    swing_core = core
    core = level_core
    core["police_dept"] = core["has_police_dept"].astype(int)
    def fit(f, d=core):
        return smf.ols(f, data=d).fit(cov_type="HC1")
    mA = fit("ly ~ self + lpop + police_share + capital_share + C(cls)")
    mB = fit("ly ~ self + lpop + law_enf_share + capital_share + C(cls)")
    mC = fit("ly ~ self + lpop + police_dept + police_share + capital_share + C(cls)")
    # the department contrast itself (no share term: governments without a department have a share of about zero,
    # so holding share fixed would compare a department with no police spending to no department)
    mF = fit("ly ~ self + lpop + police_dept + capital_share + C(cls)")
    within = core.groupby("cls")["police_dept"].agg(["sum", "count"])
    withp = core[core["has_police_dept"]]
    mD = fit("ly ~ self + lpop + police_share + capital_share + C(cls)", withp) if len(withp) >= 15 else None
    towns = core[core["cls"] == "town"]
    mE = fit("ly ~ self + lpop + police_dept", towns) if towns["police_dept"].nunique() == 2 else None

    def per10(m, term):
        b_, se_ = m.params[term], m.bse[term]
        return {"ratio_per_10pts": round(float(np.exp(b_ * 0.10)), 3), "lo": round(float(np.exp((b_ - 1.96 * se_) * 0.10)), 3),
                "hi": round(float(np.exp((b_ + 1.96 * se_) * 0.10)), 3)}

    def ratio(m, term):
        b_, se_ = m.params[term], m.bse[term]
        return {"ratio": round(float(np.exp(b_)), 3), "lo": round(float(np.exp(b_ - 1.96 * se_)), 3), "hi": round(float(np.exp(b_ + 1.96 * se_)), 3)}

    exposure = {"dept_model": {"police_dept": ratio(mF, "police_dept"), "self": ratio(mF, "self"), "n": int(mF.nobs),
                               "with_dept_by_class": {c: [int(r["sum"]), int(r["count"])] for c, r in within.iterrows()}},
                "police_share_model": {**per10(mA, "police_share"), "self": ratio(mA, "self"), "n": int(mA.nobs), "r2": round(float(mA.rsquared), 3)},
                "law_enf_share_model": {**per10(mB, "law_enf_share"), "self": ratio(mB, "self"), "n": int(mB.nobs), "r2": round(float(mB.rsquared), 3)},
                "dept_and_share_model": {"police_dept": ratio(mC, "police_dept"), "share_per_10pts": per10(mC, "police_share"), "self": ratio(mC, "self"),
                                         "n": int(mC.nobs)},
                "share_among_police_depts": ({**per10(mD, "police_share"), "n": int(mD.nobs)} if mD is not None else None),
                "towns_police_dept": ({**ratio(mE, "police_dept"), "n": int(mE.nobs)} if mE is not None else None),
                "r2": {"full": round(float(mA.rsquared), 3),
                       "without_structure": round(float(smf.ols("ly ~ lpop + police_share + capital_share + C(cls)", data=core).fit().rsquared), 3),
                       "without_police": round(float(smf.ols("ly ~ self + lpop + capital_share + C(cls)", data=core).fit().rsquared), 3),
                       "without_class": round(float(smf.ols("ly ~ self + lpop + police_share + capital_share", data=core).fit().rsquared), 3),
                       "class_only": round(float(smf.ols("ly ~ C(cls)", data=core).fit().rsquared), 3)},
                "size_within_class": ratio(mA, "lpop"),
                "note": "police_share = account 3120 / total spending net of interfund transfers, debt principal, and the GASB 84 custodial fund; "
                        "law_enf_share adds the sheriff (3110). Cross-sectional associations, not effects."}

    # ---- heterogeneity: the named subgroups ----------------------------------------------------------
    het = {}
    def sub_ratio(name, sub, formula="ly ~ self + lpop + C(cls)"):
        if sub["self"].nunique() == 2 and len(sub) >= 8:
            mm = smf.ols(formula if sub["cls"].nunique() > 1 else formula.replace(" + C(cls)", ""), data=sub).fit(cov_type="HC1")
            s2 = sub.copy(); s2["stratum"] = s2["cls"] + "|" + s2["pop_bin"].astype(int).astype(str)
            rr, nss, ncc, _ = matched_diff(s2, "cor_liab_pc_mean_w")
            het[name] = {"n": int(len(sub)), "n_self": int(sub["self"].sum()), "n_covered": int((1 - sub["self"]).sum()),
                         **ratio(mm, "self"), "matched": round(rr, 3) if np.isfinite(rr) else None, "matched_n": [nss, ncc]}
    sub_ratio("police_dept_governments", core[core["has_police_dept"]])
    sub_ratio("no_police_dept_governments", core[~core["has_police_dept"]])
    cty = core[core["cls"] == "county"].copy()
    cty["sj"] = cty["law_enf_share"] + cty["jail_share"]
    sub_ratio("counties_high_sheriff_jail", cty[cty["sj"] >= cty["sj"].median()])
    sub_ratio("counties_low_sheriff_jail", cty[cty["sj"] < cty["sj"].median()])
    sub_ratio("towns_with_police_dept", core[(core["cls"] == "town") & core["has_police_dept"]])
    sub_ratio("cities_and_villages", core[core["cls"].isin(["city", "village"])])

    # ---- big governments: who has no covered peer, and what they hold --------------------------------
    labd = ent[(ent["label_source"] == "document") & ent["treat"].isin(["self", "covered"]) & (ent["pop_mean"] > 0)].copy()
    edges = [0, 25_000, 50_000, 100_000, 250_000, 500_000, 10**9]
    labd["band"] = pd.cut(labd["pop_mean"], edges, right=False, labels=["<25K", "25-50K", "50-100K", "100-250K", "250-500K", "500K+"])
    gradient = {str(b_): {"n": int(len(g)), "n_self": int((g["treat"] == "self").sum())} for b_, g in labd.groupby("band", observed=True)}
    ceilings = {}
    for cls, g in labd.groupby("cls"):
        cov = g[g["treat"] == "covered"]
        if len(cov):
            top = cov.sort_values("pop_mean").iloc[-1]
            above = g[(g["pop_mean"] > top["pop_mean"])]
            ceilings[cls] = {"largest_covered": top["entity_name"], "largest_covered_pop": round(float(top["pop_mean"]), -2),
                             "n_above": int(len(above)), "n_above_self": int((above["treat"] == "self").sum()), "above": sorted(above["entity_name"])}
    above_names = {n for c in ceilings.values() for n in c["above"]}
    w_all = panel[panel["cls"].isin(config.OSC_CORE_CLASSES) & panel["fy"].between(*config.HEADLINE_YEARS)]
    flagged = set(ent.loc[ent["jc_contaminated"].astype(bool), "entity_name"])
    w_clean = w_all[~w_all["entity_name"].isin(flagged)]
    yr = w_clean.groupby("fy")["cost_of_risk_liab_real"].sum()
    yr_above = w_clean[w_clean["entity_name"].isin(above_names)].groupby("fy")["cost_of_risk_liab_real"].sum()
    sir = pd.to_numeric(labd["sir_per_occurrence"], errors="coerce")
    rs = labd.assign(sir=sir)[sir > config.SELF_INSURED_MIN_SIR]
    big = {"self_share_by_band": gradient, "ceilings": ceilings,
           "share_of_liability_dollars_above_ceilings": round(float((yr_above / yr).mean()), 3),
           "share_note": "mean over 2015-2024 of real liability cost of risk outside NYC held by governments larger than the largest covered peer "
                         "of their class, excluding governments whose judgments line carries benefit claims or refunds; as booked, so it "
                         "understates governments whose claims are booked elsewhere (Suffolk, Erie)",
           "retention_vs_population_spearman": round(float(rs["sir"].corr(rs["pop_mean"], method="spearman")), 3) if len(rs) > 5 else None,
           "retention_median_by_band": {str(b_): round(float(g["sir"].median()), -3) for b_, g in rs.groupby("band", observed=True)},
           "n_with_retention": int(len(rs)),
           "self_swing_cv_vs_pop_spearman": round(float(grp_s["yoy_cv"].corr(grp_s["pop_mean"], method="spearman")), 3),
           "self_worst_year_budget_share_by_band": {str(b_): round(float(g["worst_year_budget_share"].median()), 5)
                                                    for b_, g in grp_s.assign(band=pd.cut(grp_s["pop_mean"], [0, 50_000, 150_000, 10**9], right=False,
                                                                                       labels=["<50K", "50-150K", "150K+"])).groupby("band", observed=True)}}
    # statewide order of magnitude (nominal, FY2022-2024): as booked, and net of judgments lines that carry benefits or refunds
    w3 = panel[panel["cls"].isin(config.OSC_CORE_CLASSES) & panel["fy"].between(2022, 2024)]
    statewide = {"fy": [2022, 2023, 2024],
                 "liability_as_booked": [round(float(w3[w3["fy"] == y]["cost_of_risk_liab"].sum()), -5) for y in (2022, 2023, 2024)],
                 "liability_net_flagged": [round(float(w3[(w3["fy"] == y) & ~w3["entity_name"].isin(flagged)]["cost_of_risk_liab"].sum()), -5)
                                           for y in (2022, 2023, 2024)],
                 "all_funds_as_booked": [round(float(w3[w3["fy"] == y]["cost_of_risk"].sum()), -5) for y in (2022, 2023, 2024)]}

    sample = {"n_entities_total": int(len(ent)), "n_document": int((ent["label_source"] == "document").sum()),
              "n_core_used": int(len(doc)), "n_core_self": int((doc.treat == "self").sum()), "n_core_covered": int((doc.treat == "covered").sum()),
              "n_held_out": int((held_out(ent) & (ent["label_source"] == "document")).sum()),
              "window": list(config.HEADLINE_YEARS), "snapshot": config.SNAPSHOT_DATE}
    out = {"specs": specs, "sample": sample, "exposure": exposure, "heterogeneity": het, "volatility": volatility,
           "big_governments": big, "statewide": statewide}
    config.MODELS_NY_JSON.write_text(json.dumps(out, indent=1, default=float))
    prim = next(s for s in specs if s["spec_id"] == config.PRIMARY_SPEC)
    print(f"  primary: ratio {prim['coef']} [{prim['lo']}, {prim['hi']}] n_self {prim['n_self']} n_covered {prim['n_covered']} perm_p {prim['perm_p']}")
    print(f"  swing: {volatility['yoy_cv_self']} vs {volatility['yoy_cv_covered']}; matched {volatility['matched_ratio']} "
          f"[{volatility['matched_lo']}, {volatility['matched_hi']}]; worst year {volatility['max_over_mean_self']} vs {volatility['max_over_mean_covered']}")
    sw = switcher_candidates(panel)
    sw.to_csv(config.OUTPUT_DIR / "switcher_candidates.csv", index=False)
    print(f"  switcher candidates: {len(sw)} (top by population-weighted shift listed in output/switcher_candidates.csv)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
