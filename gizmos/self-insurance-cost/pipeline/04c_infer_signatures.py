"""Stage 04c: entity-level treatment signature (premium-only) + contamination flag.

Collapses the headline window (config.HEADLINE_YEARS) to one row per core entity and derives:
  ins_pc_mean, cor_pc_mean, jc_pc_mean, cor_share_mean, pop_mean, n_years
  pop_bin           config.POP_BINS within class
  sig_structure     'signature_self_insured' if real insurance per capita is below
                    SIGNATURE_PREMIUM_RATIO x the class x pop-bin median in >= SIGNATURE_MIN_YEARS of the last 5 years;
                    'signature_insured' otherwise; 'unknown' if both lines are ~0 in most years
  jc_cv, jc_share, jc_contaminated   smooth-and-large judgments = benefit claims, not torts (DECISIONS.md)
  cor_op_pc_mean    cost of risk excluding the M/MS/S/CS self-insurance fund family
The signature never uses the judgments line. Joins document labels when present.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import config

SI_FUNDS = {"M", "MS", "S", "CS"}


def main(argv: list[str] | None = None) -> int:
    p = pd.read_parquet(config.NY_PANEL_PARQUET)
    y0, y1 = config.HEADLINE_YEARS
    core = p[p["cls"].isin(config.OSC_CORE_CLASSES) & p["fy"].between(y0, y1)].copy()


    # class x pop-bin median insurance per capita, by year
    core["pop_bin"] = pd.cut(core["population"], bins=config.POP_BINS, labels=False, right=False)
    med = core.groupby(["cls", "pop_bin", "fy"])["ins_pc"].transform("median")
    core["ins_low"] = core["ins_pc"] < config.SIGNATURE_PREMIUM_RATIO * med
    core["both_zero"] = (core["ins_premium"] <= 0) & (core["judgments"] <= 0)
    last5 = core[core["fy"] > y1 - 5]

    g = core.groupby(["cls", "muni_code"])
    ent = g.agg(entity_name=("entity_name", "last"), county=("county", "last"),
                pop_mean=("population", "mean"), n_years=("fy", "count"),
                ins_pc_mean=("ins_pc", "mean"), jc_pc_mean=("jc_pc", "mean"), cor_pc_mean=("cor_pc", "mean"),
                cor_op_pc_mean=("cor_op_pc", "mean"), cor_share_mean=("cor_share", "mean"),
                police_share=("police_share", "mean"), capital_share=("capital_share", "mean"),
                b_fund_share=("b_fund_share", "mean"), total_exp_mean=("total_exp_real", "mean"),
                jc_real_mean=("judgments_real", "mean"), jc_real_std=("judgments_real", "std"),
                claims_liability_last=("claims_liability", "last"),
                self_ins_admin_mean=("self_ins_admin_real", "mean"), benefits_awards_mean=("benefits_awards", "mean"),
                health_insurance_mean=("health_insurance", "mean"), wc_cost_mean=("wc_cost_real", "mean"),
                ins_pc_p90=("ins_pc", lambda s: s.quantile(0.9)), cor_pc_p90=("cor_pc", lambda s: s.quantile(0.9)),
                both_zero_years=("both_zero", "sum")).reset_index()
    l5 = last5.groupby(["cls", "muni_code"]).agg(ins_low_years=("ins_low", "sum"), n_last5=("fy", "count")).reset_index()
    ent = ent.merge(l5, on=["cls", "muni_code"], how="left")
    ent["pop_bin"] = pd.cut(ent["pop_mean"], bins=config.POP_BINS, labels=False, right=False)
    ent["jc_cv"] = np.where(ent["jc_real_mean"] > 0, ent["jc_real_std"] / ent["jc_real_mean"], np.nan)
    ent["jc_share"] = np.where(ent["total_exp_mean"] > 0, ent["jc_real_mean"] / ent["total_exp_mean"], np.nan)
    ent["jc_contaminated"] = (ent["jc_share"] > 0.01) & (ent["jc_cv"] < 0.4)
    ent["sig_structure"] = np.where(ent["both_zero_years"] >= ent["n_years"] * 0.6, "unknown",
                           np.where(ent["ins_low_years"] >= config.SIGNATURE_MIN_YEARS, "signature_self_insured", "signature_insured"))
    ent["coded_elsewhere_holdout"] = ent["entity_name"].isin(config.CODED_ELSEWHERE_HOLDOUT)
    # NYMIR roster: a documented pool membership (coverage lines not stated; for towns and villages it is the package)
    ent["nymir_member"] = False
    if config.POOL_ROSTER_CSV.exists():
        ros = pd.read_csv(config.POOL_ROSTER_CSV, dtype=str)
        ent["nymir_member"] = ent["entity_name"].isin(set(ros["entity_name"]))
        ent.loc[ent["nymir_member"] & (ent["sig_structure"] != "unknown"), "sig_structure"] = "signature_insured"

    # document labels
    ent["structure"] = "unknown"
    ent["label_source"] = "unknown"
    if config.NY_LABELS_CSV.exists():
        lab = pd.read_csv(config.NY_LABELS_CSV, dtype=str).fillna("")
        lab = lab[lab["structure"].isin(config.VALID_STRUCTURES)]
        lab = lab.drop_duplicates("entity_name", keep="last")[["entity_name", "structure", "sir_per_occurrence", "pool_name"]]
        ent = ent.drop(columns=["structure"]).merge(lab, on="entity_name", how="left")
        ent["label_source"] = np.where(ent["structure"].notna(), "document", "unknown")
        ent["structure"] = ent["structure"].fillna("unknown")
        sir = pd.to_numeric(ent["sir_per_occurrence"], errors="coerce")
        ent["structure_raw"] = ent["structure"]
        # a retention at or below the deductible threshold is coverage with a deductible
        ent.loc[(ent["structure"] == "self_insured_with_excess") & (sir <= config.SELF_INSURED_MIN_SIR), "structure"] = "commercial"
        # a documented self-insurer with no judgments at all in the window books its claims elsewhere
        ent.loc[ent["structure"].isin(["self_insured", "self_insured_with_excess"]) & (ent["jc_pc_mean"] <= 0), "coded_elsewhere_holdout"] = True
    ent.to_parquet(config.LABELS_INFERRED_PARQUET, index=False)
    print(f"  wrote {config.LABELS_INFERRED_PARQUET.name}: {len(ent)} entities; signature counts "
          f"{ent['sig_structure'].value_counts().to_dict()}; contaminated {int(ent['jc_contaminated'].sum())}; "
          f"document-labeled {int((ent['label_source']=='document').sum())}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
