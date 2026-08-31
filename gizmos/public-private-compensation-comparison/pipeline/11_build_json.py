"""Stage 11 — assemble the shipped static JSON the frontend loads.

Reads the stage 01/02/05/06 outputs and writes to public/data/compgap/:
  national_series.json   — year x domain x govlevel: p50/p75/p90, raw gap, adjusted gap
  cross_section.json     — latest year domain x govlevel (with adjusted gaps)
  macro_topdist.json     — economy-wide percentiles + ECI divergence + median + federal + shape
  state_cross_section.json — latest year: state x domain x sector p50 (explorer state filter)
  educ_gradient.json     — raw + adjusted education gradient (the thesis anchor)
  meta.json              — labels, vintage pins, deflator, caveat strings keyed by flag
  headline.json          — token values for markdown interpolation

Run: python 11_build_json.py
"""

from __future__ import annotations

import json

import pandas as pd

import config
from pums_lib import domain_labels

SMALL_CELL = 100
OUT = config.PUBLIC_DATA_DIR


def _load(name):
    return json.loads((config.OUTPUT_DIR / name).read_text())


def main() -> None:
    print("Stage 11 — assemble shipped JSON")
    labels = domain_labels()
    labels["all"] = "All occupations"
    macro_pub = _load("macro_published.json")
    shape = _load("shape.json")
    wage_dist = _load("wage_distribution.json")
    educ_raw = _load("educ_gradient.json")
    adj = _load("adjusted_gaps.json")
    nat = pd.read_parquet(config.OUTPUT_DIR / "cells_national.parquet")
    st = pd.read_parquet(config.OUTPUT_DIR / "cells_state.parquet")

    # ---------- national_series.json ----------
    # raw gap vs private_fp, same domain & year, at p50
    piv = nat.set_index(["year", "domain", "govlevel"])
    series = []
    for r in nat.itertuples():
        flags = []
        if r.n_unweighted < SMALL_CELL:
            flags.append("small_cell")
        rec = {
            "year": int(r.year), "domain": r.domain, "govlevel": r.govlevel,
            "p50": r.p50, "p75": r.p75, "p90": r.p90,
            "n_unweighted": int(r.n_unweighted),
        }
        # raw gap vs private_fp at the median AND at the top of the field (p90)
        key = (r.year, r.domain, "private_fp")
        if r.govlevel != "private_fp" and key in piv.index:
            base = piv.loc[key, "p50"]
            if base and base > 0:
                rec["gap_vs_private_fp_pct"] = round((r.p50 / base - 1) * 100, 1)
            base90 = piv.loc[key, "p90"]
            if base90 and base90 > 0:
                rec["gap_vs_private_fp_pct_p90"] = round((r.p90 / base90 - 1) * 100, 1)
        if flags:
            rec["flags"] = flags
        series.append(rec)

    # attach adjusted gaps: 'all' domain uses by_govlevel_year; specific domains use by_domain_latest
    adj_year = adj.get("by_govlevel_year", {})
    adj_dom = adj.get("by_domain_latest", {})
    for rec in series:
        gov, dom, yr = rec["govlevel"], rec["domain"], rec["year"]
        if gov in ("private_fp",):
            continue
        if dom == "all" and str(yr) in {str(k) for k in adj_year}:
            ay = adj_year.get(yr) or adj_year.get(str(yr))
            if ay and gov in ay:
                rec["adj_gap_pct"] = ay[gov]
        if yr == config.PUMS_LATEST_YEAR and dom in adj_dom and gov in adj_dom[dom]:
            rec["adj_gap_pct"] = adj_dom[dom][gov]["adj_gap_pct"]
            rec["adj_gap_lo"] = adj_dom[dom][gov]["range_lo"]
            rec["adj_gap_hi"] = adj_dom[dom][gov]["range_hi"]

    present_domains = [d for d in
                       ["all", "software_it", "legal", "finance", "engineering",
                        "management", "healthcare", "education", "protective_service",
                        "skilled_trades", "admin_clerical"]
                       if d in set(nat["domain"])]
    (OUT / "national_series.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION,
        "base_year": config.BASE_YEAR,
        "deflator": config.DEFLATOR_NOTE,
        "domains": [{"key": d, "label": labels.get(d, d),
                     "is_elite": int(d in ("software_it", "legal", "finance",
                                           "engineering", "management"))}
                    for d in present_domains],
        "govlevels": ["private_fp", "private_np", "private", "local", "state", "federal", "public"],
        "govlevel_labels": {
            "private_fp": "Private (for-profit)", "private_np": "Private (nonprofit)",
            "private": "Private (all)", "local": "Local government",
            "state": "State government", "federal": "Federal government",
            "public": "Government (all)"},
        "series": series,
    }, separators=(",", ":")))
    print(f"  national_series.json: {len(series)} records, {len(present_domains)} domains")

    # ---------- cross_section.json (latest year) ----------
    cs = [r for r in series if r["year"] == config.PUMS_LATEST_YEAR]
    (OUT / "cross_section.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION, "year": config.PUMS_LATEST_YEAR,
        "source": "acs_pums", "series": cs,
    }, separators=(",", ":")))
    print(f"  cross_section.json: {len(cs)} records")

    # ---------- macro_topdist.json ----------
    (OUT / "macro_topdist.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION,
        "dollar_year": wage_dist["dollar_year"],
        "wage_distribution": wage_dist["distribution"],
        "wage_distribution_note": wage_dist["note"],
        "wage_distribution_highskill": wage_dist.get("distribution_highskill", []),
        "highskill_domains": wage_dist.get("highskill_domains", []),
        "wage_distribution_highskill_note": wage_dist.get("highskill_note", ""),
        "eci": macro_pub["eci"],
        "median_real_weekly_earnings": macro_pub["median_real_weekly_earnings"],
        "federal_comp_per_fte": macro_pub["federal_comp_per_fte"],
        "shape": {
            "employment_trend": shape["ces_employment_trend"],
            "latest": shape["latest"],
            "govsemp": shape["govsemp_by_govtype"],
            "govsemp_year": shape["govsemp_year"],
            "teachers_k12_m": config.NCES_PUBLIC_K12_TEACHERS_M,
            "local_gov_education_share_pct": round(config.LOCAL_GOV_EDUCATION_SHARE * 100),
        },
    }, separators=(",", ":")))
    print("  macro_topdist.json written")

    # ---------- state_cross_section.json ----------
    st_recs = []
    for r in st.itertuples():
        rec = {"state": r.state_abbr, "domain": r.domain, "sector": r.sector,
               "p50": r.p50, "p90": r.p90, "n_unweighted": int(r.n_unweighted)}
        if r.n_unweighted < SMALL_CELL:
            rec["flags"] = ["small_cell"]
        st_recs.append(rec)
    (OUT / "state_cross_section.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION, "year": config.PUMS_LATEST_YEAR,
        "source": "acs_pums", "note": "Public vs private median real hourly wage by "
        "state and domain. Private comparator is same-state PUMS (place-of-residence).",
        "records": st_recs,
    }, separators=(",", ":")))
    print(f"  state_cross_section.json: {len(st_recs)} records")

    # ---------- educ_gradient.json (raw + adjusted) ----------
    (OUT / "educ_gradient.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION, "year": config.PUMS_LATEST_YEAR,
        "raw": educ_raw["gradient"],
        "adjusted_by_education": adj.get("adjusted_gradient_by_education", {}),
        "cbo_2024_total_comp_premium": config.CBO_2024_FEDERAL_TOTALCOMP_PREMIUM,
        "note": "Raw = ACS PUMS unadjusted p50/mean by education x sector. Adjusted = "
                "composition-controlled federal/state/local premium within each education "
                "bucket. CBO 2024 is the total-compensation anchor.",
    }, separators=(",", ":")))
    print("  educ_gradient.json written")

    # ---------- meta.json ----------
    (OUT / "meta.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION,
        "generated_from": "ACS PUMS 1-year (Census microdata API), BLS ECI, BEA NIPA "
                          "(via FRED), Census ASPEP govsemp, CBO 2024.",
        "pums_years": config.PUMS_YEARS,
        "pums_latest_year": config.PUMS_LATEST_YEAR,
        "deflator": config.DEFLATOR_NOTE,
        "base_year": config.BASE_YEAR,
        "domain_labels": labels,
        "flag_caveats": {
            "small_cell": "Fewer than 100 unweighted PUMS respondents in this cell — "
                          "treat as indicative; standard error is wide.",
            "wages_only": "Wages/salary only — excludes the benefits and pension value "
                          "where public compensation is relatively richer.",
            "top_coded": "ACS PUMS top-codes very high wages, so the public-private gap at "
                         "the top is a floor; the true private lead is likely larger.",
            "median_granularity": "ACS reports wages in rounded amounts, so a median can sit "
                                  "on a common round-number salary. Medians are interpolated "
                                  "within the bracket (the standard linear method); even so, "
                                  "read small median differences as approximate and weight the "
                                  "top-of-field comparison, which is far more separated.",
        },
        "quantile_method": "Weighted quantiles use linear interpolation (Hazen plotting "
                           "position), the standard convention for survey weights.",
        "citations": {
            "cbo_2024": config.CBO_CITATION,
            "biggs_richwine": "Biggs & Richwine (AEI), composition-adjusted public pay premia.",
        },
    }, separators=(",", ":")))
    print("  meta.json written")

    # ---------- headline.json (token values) ----------
    latest_shape = shape["latest"]
    bl = adj.get("by_govlevel_latest", {})
    bd = adj.get("by_domain_latest", {})

    # ACS workforce totals (employed 25-64) — the hero strip + Sankey use these so
    # the whole piece sits in one universe. Stage 07 wrote them already.
    wfc = json.loads((config.PUBLIC_DATA_DIR / "workforce_composition.json").read_text())
    lt = wfc["level_totals_m"]
    acs_local_edu = next((m["employed_m"] for m in wfc["matrix"]
                          if m["govlevel"] == "local" and m["workgroup"] == "education"), None)
    acs_shape = {
        "federal_m": round(lt["federal"], 1),
        "state_m": round(lt["state"], 1),
        "local_m": round(lt["local"], 1),
        "total_m": round(lt["federal"] + lt["state"] + lt["local"], 1),
        "local_education_m": round(acs_local_edu, 1) if acs_local_edu else None,
        "local_education_share_pct": round(acs_local_edu / lt["local"] * 100) if acs_local_edu else None,
        "year": wfc["year"],
    }

    def dom_gap(domain, gov):
        return ((bd.get(domain) or {}).get(gov) or {}).get("adj_gap_pct")

    # macro: top-vs-median private real wage growth across the PUMS window
    dist = wage_dist["distribution"]
    d0, d1 = dist[0], dist[-1]
    p95_growth = round((d1["private_p95"] / d0["private_p95"] - 1) * 100, 1)
    p50_growth = round((d1["private_p50"] / d0["private_p50"] - 1) * 100, 1)

    headline = {
        "schema_version": config.SCHEMA_VERSION,
        "shape": {
            "federal_m": round(latest_shape["federal_k"] / 1000, 2),
            "state_m": round(latest_shape["state_k"] / 1000, 2),
            "local_m": round(latest_shape["local_k"] / 1000, 2),
            "government_total_m": round(latest_shape["government_total_k"] / 1000, 2),
            "gov_share_pct": latest_shape["gov_share_of_nonfarm_pct"],
            "year": latest_shape["year"],
        },
        "acs_shape": acs_shape,
        "teachers": {
            "k12_millions": config.NCES_PUBLIC_K12_TEACHERS_M,
            "local_gov_education_share_pct": round(config.LOCAL_GOV_EDUCATION_SHARE * 100),
        },
        "dollars": {
            "year": wage_dist["dollar_year"],
            "private_median_k": round(d1["private_p50"] / 1000),
            "private_p95_k": round(d1["private_p95"] / 1000),
            "gov_median_k": round(d1["gov_p50_no_teachers"] / 1000),
        },
        "adjusted": {
            "federal_gap_pct": (bl.get("federal") or {}).get("adj_gap_pct"),
            "state_gap_pct": (bl.get("state") or {}).get("adj_gap_pct"),
            "local_gap_pct": (bl.get("local") or {}).get("adj_gap_pct"),
            "software_state_gap_pct": dom_gap("software_it", "state"),
            "software_local_gap_pct": dom_gap("software_it", "local"),
            "software_federal_gap_pct": dom_gap("software_it", "federal"),
            "legal_state_gap_pct": dom_gap("legal", "state"),
            "engineering_state_gap_pct": dom_gap("engineering", "state"),
        },
        "macro": {
            "p95_real_growth_pct": p95_growth,
            "p50_real_growth_pct": p50_growth,
            "first_year": d0["year"],
            "latest_year": d1["year"],
        },
        "cbo_doctorate_premium_pct": round(
            config.CBO_2024_FEDERAL_TOTALCOMP_PREMIUM["professional_or_doctorate"] * 100),
        "cbo_masters_premium_pct": round(
            config.CBO_2024_FEDERAL_TOTALCOMP_PREMIUM["masters"] * 100),
    }
    (OUT / "headline.json").write_text(json.dumps(headline, separators=(",", ":")))
    print("  headline.json written")
    print("Stage 11 done.")


if __name__ == "__main__":
    main()
