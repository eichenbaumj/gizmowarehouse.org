"""Stage 04c: entity-level treatment signature (premium-only) + contamination flag.

Collapses the headline window (config.HEADLINE_YEARS) to one row per core entity and derives:
  ins_pc_mean, cor_pc_mean, jc_pc_mean, cor_share_mean, pop_mean, n_years
  pop_bin           config.POP_BINS within class
  sig_structure     'signature_self_insured' if real insurance per capita is below
                    SIGNATURE_PREMIUM_RATIO x the class x pop-bin median in >= SIGNATURE_MIN_YEARS of the last 5 years;
                    'signature_insured' otherwise; 'unknown' if both lines are ~0 in most years
  jc_cv, jc_share, jc_contaminated   smooth-and-large judgments = benefit claims or tax refunds, not torts (DECISIONS.md),
                    tested on the liability judgments line (fund-family benefit lines are already out of it)
  cor_op_pc_mean    cost of risk excluding the M/MS/S/CS self-insurance fund family
  cor_liab_pc_*     the headline outcome (operating funds + fund-family lines coded liability): mean, max (the true
                    worst year), p90
  holdout_reason    why a document-labeled government is out of the comparison (benefit claims or refunds on the
                    judgments line; claims booked elsewhere; premiums booked on department lines)
The signature never uses the judgments line. Joins document labels when present. A stated retention above
config.SELF_INSURED_MIN_SIR is self-insurance and one at or below it is a deductible, whatever the note calls it.
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
                cor_liab_pc_mean=("cor_liab_pc", "mean"), cor_liab_pc_max=("cor_liab_pc", "max"),
                cor_strict_pc_mean=("cor_strict_pc", "mean"),
                cor_liab_pc_p90=("cor_liab_pc", lambda s: s.quantile(0.9)), cor_pc_max=("cor_pc", "max"),
                ins_liab_pc_mean=("ins_liab_pc", "mean"), jc_liab_pc_mean=("jc_liab_pc", "mean"),
                cor_liab_share_mean=("cor_liab_share", "mean"), law_enf_share=("law_enf_share", "mean"),
                jail_share=("jail_share", "mean"), police_years=("police_exp", lambda s: int((s > 0).sum())),
                jc_liab_real_mean=("judgments_liab_real", "mean"), jc_liab_real_std=("judgments_liab_real", "std"),
                cor_liab_real_mean=("cost_of_risk_liab_real", "mean"), cor_liab_real_std=("cost_of_risk_liab_real", "std"),
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
    ent["jc_cv"] = np.where(ent["jc_liab_real_mean"] > 0, ent["jc_liab_real_std"] / ent["jc_liab_real_mean"], np.nan)
    ent["jc_share"] = np.where(ent["total_exp_mean"] > 0, ent["jc_liab_real_mean"] / ent["total_exp_mean"], np.nan)
    ent["jc_contaminated"] = (ent["jc_share"] > 0.01) & (ent["jc_cv"] < 0.4)
    # a municipal police department = account 3120 at 1% or more of spending on average (a stray 3120 line in a
    # county that books its sheriff under 3110 is not a department)
    ent["has_police_dept"] = ent["police_share"].fillna(0) >= config.POLICE_DEPT_MIN_SHARE
    # budget scale: how big the bill and its worst year are against the government's own spending
    ent["cor_liab_budget_share"] = np.where(ent["total_exp_mean"] > 0, ent["cor_liab_real_mean"] / ent["total_exp_mean"], np.nan)
    ent["worst_year_budget_share"] = np.where(ent["total_exp_mean"] > 0,
        (ent["cor_liab_pc_max"] - ent["cor_liab_pc_mean"]) * ent["pop_mean"] / ent["total_exp_mean"], np.nan)
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
        lab = lab.drop_duplicates("entity_name", keep="last")[["entity_name", "county", "structure", "sir_per_occurrence", "pool_name",
                                                               "fiscal_year", "liability_claims_paid_latest_fy"]].rename(columns={"county": "county_lab"})
        ent = ent.drop(columns=["structure"]).merge(lab, on="entity_name", how="left")
        wrong = ent["county_lab"].fillna("").ne("") & ent["county_lab"].fillna("").ne(ent["county"])
        ent.loc[wrong, ["structure", "sir_per_occurrence", "pool_name", "fiscal_year", "liability_claims_paid_latest_fy"]] = np.nan
        ent["label_source"] = np.where(ent["structure"].notna(), "document", "unknown")
        ent["structure"] = ent["structure"].fillna("unknown")
        sir = pd.to_numeric(ent["sir_per_occurrence"], errors="coerce")
        ent["structure_raw"] = ent["structure"]
        # a retention at or below the deductible threshold is coverage with a deductible; above it, self-insurance,
        # whatever the note calls the arrangement (Putnam: a pool policy with a $250,000 liability deductible)
        ent.loc[(ent["structure"] == "self_insured_with_excess") & (sir <= config.SELF_INSURED_MIN_SIR), "structure"] = "commercial"
        ent.loc[ent["structure"].isin(["pool", "commercial"]) & (sir > config.SELF_INSURED_MIN_SIR), "structure"] = "self_insured_with_excess"
        self_ = ent["structure"].isin(["self_insured", "self_insured_with_excess"])
        # a documented self-insurer with no claim payments at all in the window books its claims elsewhere, unless one of
        # its self-insurance-fund lines is documented as paying liability (White Plains pays claims out of MS1910)
        coded_liab = set()
        if config.LINE_CODING_CSV.exists():
            lc = pd.read_csv(config.LINE_CODING_CSV, dtype=str).fillna("")
            lc_share = pd.to_numeric(lc["liability_share"], errors="coerce").fillna(lc["coding"].map({"liability": 1.0}).fillna(0.0))
            coded_liab = set(lc.loc[lc["fund"].isin(config.SELF_INS_FUND_FAMILY) & (lc_share > 0), "entity_name"])
        ent.loc[self_ & (ent["jc_liab_pc_mean"] <= 0) & ~ent["entity_name"].isin(coded_liab), "coded_elsewhere_holdout"] = True
        # ...and so does one whose note documents liability claims paid far above everything its Comptroller lines show
        # for liability that year (premiums + claims: some self-insurance funds book claim payments as 1910)
        paid = pd.to_numeric(ent["liability_claims_paid_latest_fy"], errors="coerce")
        fy_lab = pd.to_numeric(ent["fiscal_year"], errors="coerce")
        line = core.groupby(["cls", "muni_code", "fy"])["cost_of_risk_liab"].sum()
        osc_line = [line.get((c, m, int(y)), np.nan) if pd.notna(y) else np.nan for c, m, y in zip(ent["cls"], ent["muni_code"], fy_lab)]
        ent["osc_liab_label_fy"] = osc_line
        recon = self_ & (paid >= config.RECON_MIN_DOLLARS) & (paid > config.RECON_TOLERANCE * pd.Series(osc_line, index=ent.index).clip(lower=0))
        ent["recon_holdout"] = recon.fillna(False)
        ent.loc[ent["recon_holdout"], "coded_elsewhere_holdout"] = True
        # a covered government whose unallocated-insurance line is near zero books its premiums on department lines
        covered_ = ent["structure"].isin(["pool", "commercial"])
        ent["premiums_elsewhere_holdout"] = covered_ & (ent["ins_liab_pc_mean"] < config.COVERED_MIN_PREMIUM_PC)
    else:
        ent["premiums_elsewhere_holdout"] = False
        ent["recon_holdout"] = False
    ent["holdout_reason"] = ""
    ent.loc[ent["premiums_elsewhere_holdout"], "holdout_reason"] = "premiums booked on department lines"
    ent.loc[ent["coded_elsewhere_holdout"], "holdout_reason"] = "claims booked under other accounts"
    ent.loc[ent["jc_contaminated"], "holdout_reason"] = "judgments line carries other payments, such as benefit claims or tax refunds"
    for name, why in config.HOLDOUT_NOTES.items():
        ent.loc[(ent["entity_name"] == name) & (ent["holdout_reason"] != ""), "holdout_reason"] = why
    # which governments the labeling rule selects (every county; the largest cities, towns, villages by population)
    rank = ent.groupby("cls")["pop_mean"].rank(ascending=False, method="first")
    ent["in_label_rule"] = (ent["cls"] == "county") | (rank <= ent["cls"].map(config.LABEL_TOP_N).fillna(0))
    ent.to_parquet(config.LABELS_INFERRED_PARQUET, index=False)
    print(f"  wrote {config.LABELS_INFERRED_PARQUET.name}: {len(ent)} entities; signature counts "
          f"{ent['sig_structure'].value_counts().to_dict()}; contaminated {int(ent['jc_contaminated'].sum())}; "
          f"document-labeled {int((ent['label_source']=='document').sum())}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
