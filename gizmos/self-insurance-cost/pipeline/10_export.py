"""Stage 10: export the files the site reads and the download pills.

public/data/self-insurance-cost/{ny_entities,ny_switchers,ntd_agencies,models,attribution}.json
public/assets/self-insurance-cost-{ny-panel,ntd-panel,treatment-labels}.csv (with the attribution header line)
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import config
import fetchers

sys.path.insert(0, str(config.PIPELINE_DIR))
import importlib
m07 = importlib.import_module("07_models_ny")


def _csv_with_header(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(config.CSV_HEADER_COMMENT + "\n")
        df.to_csv(f, index=False)
    print(f"  wrote {path.name}: {len(df):,} rows ({path.stat().st_size/1e6:.1f} MB)")


def main(argv: list[str] | None = None) -> int:
    config.ensure_dirs()
    ent = pd.read_parquet(config.LABELS_INFERRED_PARQUET)
    ent["region"] = ent["county"].map(m07.region_of)
    ent["treat"] = ent.apply(m07.treat_of, axis=1)
    keep = ["cls", "muni_code", "entity_name", "county", "region", "pop_mean", "pop_bin", "n_years",
            "cor_liab_pc_mean", "ins_liab_pc_mean", "jc_liab_pc_mean", "cor_liab_pc_max", "cor_liab_pc_p90", "cor_liab_share_mean",
            "cor_pc_mean", "cor_op_pc_mean", "cor_liab_budget_share", "worst_year_budget_share", "has_police_dept",
            "structure", "structure_raw", "sir_per_occurrence", "pool_name", "nymir_member", "label_source", "sig_structure",
            "jc_contaminated", "coded_elsewhere_holdout", "premiums_elsewhere_holdout", "holdout_reason", "in_label_rule", "treat"]
    for c in ("structure_raw", "sir_per_occurrence", "pool_name", "nymir_member", "premiums_elsewhere_holdout", "holdout_reason", "in_label_rule"):
        if c not in ent.columns:
            ent[c] = None
    # the chart plots the document core; the periphery rides in the CSV download, not the page JSON
    e = ent[(ent["label_source"] == "document") | ent["cls"].isin(["county", "city"])][keep].copy()
    for c in ("pop_mean",):
        e[c] = e[c].round(0)
    for c in ("cor_liab_pc_mean", "ins_liab_pc_mean", "jc_liab_pc_mean", "cor_liab_pc_max", "cor_liab_pc_p90", "cor_pc_mean", "cor_op_pc_mean"):
        e[c] = e[c].round(2)
    for c in ("cor_liab_share_mean", "cor_liab_budget_share", "worst_year_budget_share"):
        e[c] = e[c].round(5)
    # group summary for the static stand-ins: document core, usable rows only (the stage-07 rule)
    core = m07.usable(e[e["label_source"] == "document"])
    # the core chart plots every read government whose books carry the comparison, unclear and mixed ones as hollow marks
    e["plotted"] = ((e["label_source"] == "document") & ~m07.held_out(e) & (e["n_years"] >= 8) & (e["pop_mean"] > 0))
    rows = e.replace({np.nan: None}).to_dict(orient="records")
    summary = {}
    for t_, g in core.groupby("treat"):
        summary[t_] = {"n": int(len(g)), "n_county": int((g["cls"] == "county").sum()), "n_city": int((g["cls"] == "city").sum()),
                       "median_cor_pc": round(float(g["cor_liab_pc_mean"].median()), 1), "median_ins_pc": round(float(g["ins_liab_pc_mean"].median()), 1),
                       "median_jc_pc": round(float(g["jc_liab_pc_mean"].median()), 1), "median_max": round(float(g["cor_liab_pc_max"].median()), 1),
                       "mean_cor_pc": round(float(g["cor_liab_pc_mean"].mean()), 1), "mean_ins_pc": round(float(g["ins_liab_pc_mean"].mean()), 1),
                       "mean_jc_pc": round(float(g["jc_liab_pc_mean"].mean()), 1),
                       "premium_share_of_cost": round(float(g["ins_liab_pc_mean"].sum() / max(g["cor_liab_pc_mean"].sum(), 1e-9)), 3)}
    summary_by_class = {}
    for (cls_, t_), g in core.groupby(["cls", "treat"]):
        summary_by_class.setdefault(cls_, {})[t_] = {"n": int(len(g)), "median_cor_pc": round(float(g["cor_liab_pc_mean"].median()), 1),
            "median_ins_pc": round(float(g["ins_liab_pc_mean"].median()), 1), "median_jc_pc": round(float(g["jc_liab_pc_mean"].median()), 1),
            "median_max": round(float(g["cor_liab_pc_max"].median()), 1)}
    bins = {}
    for (cls_, b), g in core.groupby(["cls", "pop_bin"]):
        bins[f"{cls_}|{int(b)}"] = {t_: {"n": int(len(h)), "mean_cor_pc": round(float(h["cor_liab_pc_mean"].mean()), 1),
                                         "median_cor_pc": round(float(h["cor_liab_pc_mean"].median()), 1)} for t_, h in g.groupby("treat")}
    hmask = (e["label_source"] == "document") & m07.held_out(e)
    holdouts = e[hmask][["entity_name", "structure", "holdout_reason"]].to_dict(orient="records")
    thin = e[(e["label_source"] == "document") & ~hmask & (e["n_years"] < 8)][["entity_name", "n_years"]].to_dict(orient="records")
    # year-by-year liability cost per resident for every plotted government (the swing exhibit draws these)
    pnl = pd.read_parquet(config.NY_PANEL_PARQUET, columns=["muni_code", "fy", "cor_liab_pc"])
    pnl = pnl[pnl["muni_code"].isin(set(core["muni_code"])) & pnl["fy"].between(*config.HEADLINE_YEARS)]
    years = list(range(config.HEADLINE_YEARS[0], config.HEADLINE_YEARS[1] + 1))
    series = {mc: [None if pd.isna(v) else round(float(v), 2) for v in g.set_index("fy")["cor_liab_pc"].reindex(years)]
              for mc, g in pnl.groupby("muni_code")}
    # per-government swing fields the swing exhibit reads (stage 07 leaves out governments with a negative year)
    stats = {}
    for mc, g in pnl.groupby("muni_code"):
        v = g.set_index("fy")["cor_liab_pc"].reindex(years).dropna()
        mean = float(v.mean()) if len(v) else float("nan")
        n_neg = int((v < 0).sum())
        ok = n_neg == 0 and mean > 0
        stats[mc] = {"n_neg_years": n_neg, "worst_fy": int(v.idxmax()) if len(v) else None,
                     "worst_over_mean": round(float(v.max() / mean), 3) if ok else None,
                     "swing": round(float(v.std(ddof=1) / mean), 3) if ok and len(v) > 1 else None}
    for r in rows:
        r.update(stats.get(r["muni_code"], {"n_neg_years": None, "worst_fy": None, "worst_over_mean": None, "swing": None}))
    fetchers.write_json(config.PUBLIC_JSON["ny_entities"], {"snapshot": config.SNAPSHOT_DATE, "window": list(config.HEADLINE_YEARS), "rows": rows,
                                                            "summary": summary, "summary_by_class": summary_by_class, "bins": bins, "holdouts": holdouts,
                                                            "thin": thin, "years": years, "series": series, "pop_bins": config.POP_BINS})

    models = json.loads(config.MODELS_NY_JSON.read_text()) if config.MODELS_NY_JSON.exists() else {}
    ntd_models = json.loads(config.MODELS_NTD_JSON.read_text()) if config.MODELS_NTD_JSON.exists() else {}
    fetchers.write_json(config.PUBLIC_JSON["models"], {"snapshot": config.SNAPSHOT_DATE, "ny": models, "ntd": ntd_models})
    attribution = json.loads(config.ATTRIBUTION_JSON.read_text()) if config.ATTRIBUTION_JSON.exists() else {}
    fetchers.write_json(config.PUBLIC_JSON["attribution"], {"snapshot": config.SNAPSHOT_DATE, **attribution})

    sw_path = config.OUTPUT_DIR / "switchers_verified.json"
    sw = json.loads(sw_path.read_text()) if sw_path.exists() else {"note": "no verified switchers yet", "events": []}
    fetchers.write_json(config.PUBLIC_JSON["ny_switchers"], {"snapshot": config.SNAPSHOT_DATE, **sw})

    a = pd.read_parquet(config.NTD_PANEL_PARQUET)
    a = a.sort_values(["ntd_id", "fy"])
    dm = (a.groupby("ntd_id", as_index=False)
          .agg(agency=("agency", "last"), city=("city", "last"), state=("state", "last"), structure=("structure", "last"),
               label_source=("label_source", "last"), cl_share=("cl_share", "mean"), cl_per_vrm=("cl_per_vrm", "mean"),
               vrm=("vrm", "mean"), total_opex=("total_opex", "mean"), cl_expense=("cl_expense", "mean"), n=("fy", "count")))
    caps = pd.read_csv(config.STATE_CAPS_CSV, dtype=str).fillna("") if config.STATE_CAPS_CSV.exists() else None
    if caps is not None:
        dm = dm.merge(caps[["state", "cap_type"]], on="state", how="left")
    dm = dm.sort_values("vrm", ascending=False).head(300)
    for c in ("cl_share",):
        dm[c] = dm[c].round(4)
    for c in ("cl_per_vrm",):
        dm[c] = dm[c].round(3)
    for c in ("vrm", "total_opex", "cl_expense"):
        dm[c] = dm[c].round(0)
    fetchers.write_json(config.PUBLIC_JSON["ntd_agencies"], {"snapshot": config.SNAPSHOT_DATE, "years": config.NTD_YEARS,
                                                             "rows": dm.replace({np.nan: None}).to_dict(orient="records")})

    # downloads
    panel = pd.read_parquet(config.NY_PANEL_PARQUET)
    cols = ["cls", "muni_code", "entity_name", "county", "fy", "fy_end", "population", "ins_premium", "judgments", "ins_liab", "judgments_liab",
            "cost_of_risk_liab", "cost_of_risk", "cost_of_risk_op", "self_ins_admin", "wc_cost", "law_exp", "police_exp", "sheriff_exp", "jail_exp",
            "custodial_exp", "total_exp", "claims_liability", "cpi_factor", "cor_liab_pc", "cor_pc", "cor_liab_share"]
    p = panel[panel["cls"].isin(config.OSC_CORE_CLASSES)][cols].copy()
    for c in ("population", "ins_premium", "judgments", "ins_liab", "judgments_liab", "cost_of_risk_liab", "self_ins_admin", "cost_of_risk",
              "cost_of_risk_op", "wc_cost", "law_exp", "police_exp", "sheriff_exp", "jail_exp", "custodial_exp", "total_exp", "claims_liability"):
        p[c] = p[c].round(0)
    p["cpi_factor"] = p["cpi_factor"].round(4)
    for c in ("cor_liab_pc", "cor_pc"):
        p[c] = p[c].round(2)
    p["cor_liab_share"] = p["cor_liab_share"].round(5)
    _csv_with_header(p, config.ASSET_NY_PANEL_CSV)
    _csv_with_header(a.round(4), config.ASSET_NTD_PANEL_CSV)
    if config.NY_LABELS_CSV.exists():
        lab = pd.read_csv(config.NY_LABELS_CSV, dtype=str).fillna("")
        # what the comparison did with each label (the $100K rule and the holdouts move some rows)
        side = {"self": "self-insured", "covered": "covered", "other": "not compared (unclear or mixed)"}
        cmp_ = ent[ent["label_source"] == "document"].set_index("entity_name")
        def compared_as(n: str) -> str:
            if n not in cmp_.index:
                return "not in panel"
            r = cmp_.loc[n]
            if bool(r.get("jc_contaminated")) or bool(r.get("coded_elsewhere_holdout")) or bool(r.get("premiums_elsewhere_holdout")):
                return f"held out: {r.get('holdout_reason') or 'books cannot carry the comparison'}"
            if r["n_years"] < 8:
                return "not compared (fewer than 8 years of filings)"
            return side.get(r["treat"], "not compared")
        lab["compared_as"] = lab["entity_name"].map(compared_as)
        lab["selection"] = lab["entity_name"].map(lambda n: "" if n not in cmp_.index else
                                                  ("labeling rule" if bool(cmp_.loc[n].get("in_label_rule")) else "read beyond the rule"))
        if config.NTD_LABELS_CSV.exists():
            lab = pd.concat([lab, pd.read_csv(config.NTD_LABELS_CSV, dtype=str).fillna("")], ignore_index=True)
        _csv_with_header(lab, config.ASSET_LABELS_CSV)
    if not config.ASSET_METHODOLOGY_MD.exists():
        print(f"  NOTE: {config.ASSET_METHODOLOGY_MD.name} not written yet (hand-written at M3)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
