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
    keep = ["cls", "muni_code", "entity_name", "county", "region", "pop_mean", "pop_bin", "n_years", "ins_pc_mean", "jc_pc_mean",
            "cor_pc_mean", "cor_op_pc_mean", "cor_share_mean", "cor_pc_p90", "structure", "structure_raw", "sir_per_occurrence",
            "pool_name", "nymir_member", "label_source", "sig_structure", "jc_contaminated", "coded_elsewhere_holdout", "treat"]
    for c in ("structure_raw", "sir_per_occurrence", "pool_name", "nymir_member"):
        if c not in ent.columns:
            ent[c] = None
    # the chart plots the document core; the periphery rides in the CSV download, not the page JSON
    e = ent[(ent["label_source"] == "document") | ent["cls"].isin(["county", "city"])][keep].copy()
    for c in ("pop_mean",):
        e[c] = e[c].round(0)
    for c in ("ins_pc_mean", "jc_pc_mean", "cor_pc_mean", "cor_op_pc_mean", "cor_pc_p90"):
        e[c] = e[c].round(2)
    e["cor_share_mean"] = e["cor_share_mean"].round(5)
    rows = e.replace({np.nan: None}).to_dict(orient="records")
    # group summary for the mix exhibit and the static stand-ins: document core, usable rows only
    core = e[(e["label_source"] == "document") & e["treat"].isin(["self", "covered"]) & ~e["jc_contaminated"].astype(bool)
             & ~e["coded_elsewhere_holdout"].astype(bool) & (e["n_years"] >= 8)]
    summary = {}
    for t_, g in core.groupby("treat"):
        summary[t_] = {"n": int(len(g)), "n_county": int((g["cls"] == "county").sum()), "n_city": int((g["cls"] == "city").sum()),
                       "median_cor_pc": round(float(g["cor_pc_mean"].median()), 1), "median_ins_pc": round(float(g["ins_pc_mean"].median()), 1),
                       "median_jc_pc": round(float(g["jc_pc_mean"].median()), 1), "median_p90": round(float(g["cor_pc_p90"].median()), 1),
                       "mean_cor_pc": round(float(g["cor_pc_mean"].mean()), 1), "mean_ins_pc": round(float(g["ins_pc_mean"].mean()), 1),
                       "mean_jc_pc": round(float(g["jc_pc_mean"].mean()), 1),
                       "premium_share_of_cost": round(float(g["ins_pc_mean"].sum() / max(g["cor_pc_mean"].sum(), 1e-9)), 3)}
    summary_by_class = {}
    for (cls_, t_), g in core.groupby(["cls", "treat"]):
        summary_by_class.setdefault(cls_, {})[t_] = {"n": int(len(g)), "median_cor_pc": round(float(g["cor_pc_mean"].median()), 1),
            "median_ins_pc": round(float(g["ins_pc_mean"].median()), 1), "median_jc_pc": round(float(g["jc_pc_mean"].median()), 1),
            "median_p90": round(float(g["cor_pc_p90"].median()), 1)}
    bins = {}
    for (cls_, b), g in core.groupby(["cls", "pop_bin"]):
        bins[f"{cls_}|{int(b)}"] = {t_: {"n": int(len(h)), "median_cor_pc": round(float(h["cor_pc_mean"].median()), 1)} for t_, h in g.groupby("treat")}
    holdouts = e[(e["label_source"] == "document") & (e["jc_contaminated"].astype(bool) | e["coded_elsewhere_holdout"].astype(bool))][["entity_name", "structure", "jc_contaminated", "coded_elsewhere_holdout"]].to_dict(orient="records")
    fetchers.write_json(config.PUBLIC_JSON["ny_entities"], {"snapshot": config.SNAPSHOT_DATE, "window": list(config.HEADLINE_YEARS), "rows": rows,
                                                            "summary": summary, "summary_by_class": summary_by_class, "bins": bins, "holdouts": holdouts,
                                                            "pop_bins": config.POP_BINS})

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
    cols = ["cls", "muni_code", "entity_name", "county", "fy", "fy_end", "population", "ins_premium", "judgments", "self_ins_admin",
            "cost_of_risk", "cost_of_risk_op", "wc_cost", "law_exp", "police_exp", "total_exp", "claims_liability", "cpi_factor", "cor_pc", "cor_share"]
    p = panel[panel["cls"].isin(config.OSC_CORE_CLASSES)][cols].copy()
    for c in ("population", "ins_premium", "judgments", "self_ins_admin", "cost_of_risk", "cost_of_risk_op", "wc_cost", "law_exp", "police_exp", "total_exp", "claims_liability"):
        p[c] = p[c].round(0)
    p["cpi_factor"] = p["cpi_factor"].round(4); p["cor_pc"] = p["cor_pc"].round(2); p["cor_share"] = p["cor_share"].round(5)
    _csv_with_header(p, config.ASSET_NY_PANEL_CSV)
    _csv_with_header(a.round(4), config.ASSET_NTD_PANEL_CSV)
    if config.NY_LABELS_CSV.exists():
        lab = pd.read_csv(config.NY_LABELS_CSV, dtype=str).fillna("")
        if config.NTD_LABELS_CSV.exists():
            lab = pd.concat([lab, pd.read_csv(config.NTD_LABELS_CSV, dtype=str).fillna("")], ignore_index=True)
        _csv_with_header(lab, config.ASSET_LABELS_CSV)
    if not config.ASSET_METHODOLOGY_MD.exists():
        print(f"  NOTE: {config.ASSET_METHODOLOGY_MD.name} not written yet (hand-written at M3)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
