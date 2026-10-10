"""Stage 03: entity × fiscal-year panel for New York local governments.

From output/osc_long.parquet. One row per (cls, muni_code, fy) with:
  ins_premium      all-fund 1910 Unallocated Insurance
  judgments        all-fund 1930 Judgments and Claims + 1931 Property Loss
  *_op             the same excluding the M/MS/S/CS self-insurance fund family
  ins_liab, judgments_liab
                   liability lines as coded in crosswalks/ny_line_coding.csv (read from each government's statements):
                   operating-fund lines count unless they are internal charges into a self-insurance fund; fund-family
                   and 1722 excess-insurance lines count when they pay liability (workers' comp and health are out)
  cost_of_risk     ins_premium + judgments (all funds; sensitivity)
  cost_of_risk_op  operating funds only (sensitivity)
  cost_of_risk_liab  ins_liab + judgments_liab (the headline numerator)
  self_ins_admin   1710 Self Insurance Administration in the MS/S/CS funds (separate; in practice comp overhead)
  wc_cost          9040 Workers' Compensation (separate; not in the headline)
  law_exp 1420, dues 1920 (placebo), other_gg 1989, police 3120, sheriff 3110, jail 3150, highway 5110
  capital_outlay   object digit 2 across all expenditure accounts
  custodial_exp    GASB 84 custodial fund (TC): taxes collected for others and passed through
  total_exp        all expenditures minus interfund transfers (99xx), debt principal (97xx object 6), and custodial
  total_exp_gross  all expenditures
  b_fund_share     B-fund (town outside village) share of total_exp
  claims_liability GL W686 Judgments and Claims Payable; insurance_reserve A863; recoveries 2680
  population       decennial (OSC/NHGIS 1970–2020) + Census subcounty estimates 2000–2024, interpolated
  cpi_factor       CPI-U at fiscal-year-end month rebased to the 2024 average
  *_real, cor_pc / cor_op_pc / cor_liab_pc (per resident, 2024 $), cor_liab_share (per dollar of total_exp),
  police_share (3120), law_enf_share (3120 + 3110), jail_share, capital_share

Population exists only for counties, cities, towns, villages. School and fire districts carry NaN
and are compared per dollar of spending only.
"""

from __future__ import annotations

import re
import sys

import numpy as np
import pandas as pd

import config
import fetchers

DEC_XLSX = config.RAW_DIR / "pop" / "decennial-populations-nys-cctvs-1970-2020.xlsx"
CENSUS_FILES = {  # Census Bureau subcounty population estimates (NY rows), by vintage
    "2000s": config.RAW_DIR / "pop" / "sub-est2009_36.csv",   # intercensal 2000–2009 (national file, filtered to NY)
    "2010s": config.RAW_DIR / "pop" / "sub-est2019_36.csv",
    "2020s": config.RAW_DIR / "pop" / "sub-est2024.csv",
}
CENSUS_URLS = {
    "2000s": "https://www2.census.gov/programs-surveys/popest/datasets/2000-2010/intercensal/cities/sub-est00int.csv",
    "2010s": "https://www2.census.gov/programs-surveys/popest/datasets/2010-2019/cities/totals/sub-est2019_36.csv",
    "2020s": "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/cities/totals/sub-est2024.csv",
}
DEC_URL = "https://www.osc.ny.gov/files/local-government/data/excel/decennial-populations-nys-cctvs-1970-2020.xlsx"


def _population() -> pd.DataFrame:
    """Long table: muni_code, year, population (1996–2026) for counties/cities/towns/villages."""
    fetchers.download(DEC_URL, DEC_XLSX)
    for k, p in CENSUS_FILES.items():
        fetchers.download(CENSUS_URLS[k], p)
    dec = pd.read_excel(DEC_XLSX, sheet_name="Data", header=2, dtype=str)
    dec.columns = [str(c).strip() for c in dec.columns]
    dec["g"] = dec["Geo ID"].astype(str).str.replace(r"^\d{7}US", "", regex=True)
    pop = {}  # (muni_code) -> {year: pop}
    for _, r in dec.iterrows():
        d = {}
        for y in ("1990", "2000", "2010", "2020"):
            v = pd.to_numeric(r.get(y), errors="coerce")
            if pd.notna(v):
                d[int(y)] = float(v)
        pop[r["Muni Code"]] = d
    # Census annual estimates keyed by GEOID: towns = county subdivision (36+county+cousub),
    # cities/villages = place (36+place), counties = 36+county
    geo_to_muni = dict(zip(dec["g"], dec["Muni Code"]))
    for k, p in CENSUS_FILES.items():
        c = pd.read_csv(p, encoding="latin-1", dtype=str)
        c = c[c["STATE"] == "36"]
        years = [col for col in c.columns if col.startswith("POPESTIMATE")]
        for _, r in c.iterrows():
            if r["SUMLEV"] == "061":
                g = "36" + r["COUNTY"] + r["COUSUB"]
            elif r["SUMLEV"] == "162":
                g = "36" + r["PLACE"]
            elif r["SUMLEV"] == "050":
                g = "36" + r["COUNTY"]
            else:
                continue
            mc = geo_to_muni.get(g)
            if not mc:
                continue
            for col in years:
                y = int(col[-4:])
                v = pd.to_numeric(r[col], errors="coerce")
                if pd.notna(v) and v > 0:
                    pop[mc][y] = float(v)
    rows = []
    for mc, d in pop.items():
        if not d:
            continue
        s = pd.Series(d).sort_index()
        full = s.reindex(range(1990, 2027)).interpolate(method="linear", limit_direction="both")
        for y, v in full.items():
            if 1996 <= y <= 2026:
                rows.append((mc, int(y), float(v)))
    out = pd.DataFrame(rows, columns=["muni_code", "fy", "population"])
    print(f"  population: {out['muni_code'].nunique()} entities, {len(out):,} entity-years")
    return out


def _line_shares() -> dict[tuple[str, str, str], tuple[float, float]]:
    """(entity_name, fund, acct) -> (liability share, strict share) from the per-line coding.

    The strict share sends lines coded mixed/unknown without a documented split to 0 (a sensitivity)."""
    if not config.LINE_CODING_CSV.exists():
        print("  NOTE: no line coding; fund-family lines count as booked, 1722 stays out")
        return {}
    c = pd.read_csv(config.LINE_CODING_CSV, dtype=str).fillna("")
    out = {}
    for _, r in c.iterrows():
        share = pd.to_numeric(r.get("liability_share", ""), errors="coerce")
        if pd.notna(share):
            out[(r["entity_name"], r["fund"], r["acct"])] = (float(share), float(share))
        elif r["coding"] in config.FUND_FAMILY_DEFAULT_SHARE:
            v = config.FUND_FAMILY_DEFAULT_SHARE[r["coding"]]
            out[(r["entity_name"], r["fund"], r["acct"])] = (v, v)
        else:
            out[(r["entity_name"], r["fund"], r["acct"])] = (config.FUND_FAMILY_UNRESOLVED_SHARE, 0.0)
    return out


def _cpi() -> pd.DataFrame:
    cpi = fetchers.fetch_fred(config.CPI_SERIES)
    cpi["ym"] = cpi["date"].dt.strftime("%Y-%m")
    base = cpi[cpi["date"].dt.year == config.DEFLATE_TO_YEAR]["value"].mean()
    cpi["cpi_factor"] = base / cpi["value"]
    return cpi[["ym", "cpi_factor"]]


def main(argv: list[str] | None = None) -> int:
    argv = argv or []
    force = "--force" in argv
    if config.NY_PANEL_PARQUET.exists() and not force:
        print(f"  cached {config.NY_PANEL_PARQUET.name}")
        return 0
    long = pd.read_parquet(config.OSC_LONG_PARQUET)
    long["acct"] = long["acct"].astype(str)
    long["fund"] = long["fund"].astype(str)
    long["obj"] = long["obj"].astype(str)
    long["section"] = long["section"].astype(str)
    long["cls"] = long["cls"].astype(str)          # categorical keys would make groupby emit every class x code combo
    long["county"] = long["county"].astype(str)
    key = ["cls", "muni_code", "fy"]
    ex = long[long["section"] == "EXPENDITURE"]

    def s(mask, name):
        return ex[mask].groupby(key)["amount"].sum().rename(name)

    a = ex["acct"]
    parts = [
        s(a == config.ACCT_INSURANCE, "ins_premium"),
        s(a.isin([config.ACCT_JUDGMENTS, config.ACCT_PROPERTY_LOSS]), "judgments"),
        s((a == config.ACCT_INSURANCE) & ~ex["fund"].isin(config.SELF_INS_FUND_FAMILY), "ins_premium_op"),
        s(a.isin([config.ACCT_JUDGMENTS, config.ACCT_PROPERTY_LOSS]) & ~ex["fund"].isin(config.SELF_INS_FUND_FAMILY), "judgments_op"),
        s(a == "1720", "benefits_awards"),
        s(a == "1722", "excess_insurance"),
        s(a == "9060", "health_insurance"),
        s((a == config.ACCT_SELF_INS_ADMIN) & ex["fund"].isin(config.SELF_INS_ADMIN_FUNDS), "self_ins_admin"),
        s(a == config.ACCT_WORKERS_COMP, "wc_cost"),
        s(a == config.ACCT_LAW, "law_exp"),
        s(a == config.ACCT_DUES, "dues"),
        s(a == config.ACCT_OTHER_GG, "other_gg"),
        s(a == config.ACCT_POLICE, "police_exp"),
        s(a == config.ACCT_SHERIFF, "sheriff_exp"),
        s(a == config.ACCT_JAIL, "jail_exp"),
        s(a == config.ACCT_HIGHWAY, "highway_exp"),
        s(ex["obj"] == "2", "capital_outlay"),
        s(a.str.startswith("99"), "interfund_transfers"),
        s(a.str.startswith("97") & (ex["obj"] == "6"), "debt_principal"),
        s(ex["fund"] == "B", "b_fund_exp"),
        s(ex["fund"] == config.FUND_CUSTODIAL, "custodial_exp"),
        ex.groupby(key)["amount"].sum().rename("total_exp_gross"),
    ]
    gl = long[long["section"] == "GL"]
    parts.append(gl[(gl["acct"] == config.GL_CLAIMS_PAYABLE)].groupby(key)["amount"].sum().rename("claims_liability"))
    parts.append(gl[(gl["acct"] == config.GL_INSURANCE_RESERVE)].groupby(key)["amount"].sum().rename("insurance_reserve"))
    rv = long[long["section"] == "REVENUE"]
    parts.append(rv[rv["acct"] == config.REV_INSURANCE_RECOVERIES].groupby(key)["amount"].sum().rename("insurance_recoveries"))
    # liability lines, weighted by their documented liability share: operating 1910/1930/1931 count unless coded
    # as internal charges; fund-family lines count per their coding; 1722 excess insurance counts only where coded
    shares = _line_shares()
    lm = a.isin([config.ACCT_INSURANCE, config.ACCT_JUDGMENTS, config.ACCT_PROPERTY_LOSS, config.ACCT_EXCESS])
    ln = ex[lm].groupby(key + ["entity_name", "fund", "acct"])["amount"].sum().reset_index()
    fam = ln["fund"].isin(config.SELF_INS_FUND_FAMILY)
    default = np.where(ln["acct"] == config.ACCT_EXCESS, config.EXCESS_UNCODED_SHARE,
                       np.where(fam, config.FUND_FAMILY_UNCODED_SHARE, 1.0))
    got = [shares.get((e, f_, ac)) for e, f_, ac in zip(ln["entity_name"], ln["fund"], ln["acct"])]
    ln["share"] = [g[0] if g else d for g, d in zip(got, default)]
    ln["share_strict"] = [g[1] if g else d for g, d in zip(got, default)]
    ln["is_ins"] = ln["acct"].isin([config.ACCT_INSURANCE, config.ACCT_EXCESS])
    for col, sh in (("", "share"), ("_strict", "share_strict")):
        ln["liab"] = ln["amount"] * ln[sh]
        parts.append(ln[ln["is_ins"]].groupby(key)["liab"].sum().rename(f"ins_liab{col}"))
        parts.append(ln[~ln["is_ins"]].groupby(key)["liab"].sum().rename(f"judgments_liab{col}"))
    panel = pd.concat(parts, axis=1).fillna(0.0).reset_index()
    names = (long.sort_values("fy").groupby(["cls", "muni_code"])
             .agg(entity_name=("entity_name", "last"), county=("county", "last"), fy_end=("fy_end", "last")).reset_index())
    fy_end = long.groupby(key)["fy_end"].first().reset_index()
    panel = panel.merge(names.drop(columns="fy_end"), on=["cls", "muni_code"], how="left").merge(fy_end, on=key, how="left")

    # Liability cost of risk = premiums + judgments/claims + property loss, all funds. The 1710 self-insurance
    # administration line is workers'-comp plan overhead in practice (DECISIONS.md 2026-10-08) and is kept separate.
    panel["cost_of_risk"] = panel["ins_premium"] + panel["judgments"]
    # Operating-fund variant: excludes the M/MS/S/CS self-insurance fund family (benefit claims live there)
    panel["cost_of_risk_op"] = panel["ins_premium_op"] + panel["judgments_op"]
    # Headline: the liability lines as coded (ins_liab / judgments_liab built above); strict sends unresolved lines to 0
    panel["cost_of_risk_liab"] = panel["ins_liab"] + panel["judgments_liab"]
    panel["cost_of_risk_liab_strict"] = panel["ins_liab_strict"] + panel["judgments_liab_strict"]
    panel["law_enf_exp"] = panel["police_exp"] + panel["sheriff_exp"]
    panel["total_exp"] = panel["total_exp_gross"] - panel["interfund_transfers"] - panel["debt_principal"] - panel["custodial_exp"]
    panel["b_fund_share"] = np.where(panel["total_exp"] > 0, panel["b_fund_exp"] / panel["total_exp"], np.nan)

    # population + CPI
    pop = _population()
    panel = panel.merge(pop, on=["muni_code", "fy"], how="left")
    cpi = _cpi()
    fe = pd.to_datetime(panel["fy_end"], errors="coerce")
    panel["fy_end_ym"] = fe.dt.strftime("%Y-%m")
    panel = panel.merge(cpi, left_on="fy_end_ym", right_on="ym", how="left").drop(columns=["ym"])
    # rows whose fy_end is missing or past the CPI series: use June of the fiscal year
    miss = panel["cpi_factor"].isna()
    fallback = panel.loc[miss, "fy"].astype(int).astype(str) + "-06"
    panel.loc[miss, "cpi_factor"] = fallback.map(dict(zip(cpi["ym"], cpi["cpi_factor"])))
    panel["cpi_factor"] = panel["cpi_factor"].fillna(1.0)

    for c in ("ins_premium", "judgments", "self_ins_admin", "cost_of_risk", "cost_of_risk_op", "cost_of_risk_liab", "cost_of_risk_liab_strict",
              "ins_liab", "judgments_liab", "wc_cost", "law_exp", "total_exp"):
        panel[f"{c}_real"] = panel[c] * panel["cpi_factor"]
    with np.errstate(divide="ignore", invalid="ignore"):
        panel["cor_pc"] = panel["cost_of_risk_real"] / panel["population"]
        panel["cor_op_pc"] = panel["cost_of_risk_op_real"] / panel["population"]
        panel["cor_liab_pc"] = panel["cost_of_risk_liab_real"] / panel["population"]
        panel["cor_strict_pc"] = panel["cost_of_risk_liab_strict_real"] / panel["population"]
        panel["ins_liab_pc"] = panel["ins_liab_real"] / panel["population"]
        panel["jc_liab_pc"] = panel["judgments_liab_real"] / panel["population"]
        panel["cor_liab_share"] = np.where(panel["total_exp"] > 0, panel["cost_of_risk_liab"] / panel["total_exp"], np.nan)
        panel["law_enf_share"] = np.where(panel["total_exp"] > 0, panel["law_enf_exp"] / panel["total_exp"], np.nan)
        panel["jail_share"] = np.where(panel["total_exp"] > 0, panel["jail_exp"] / panel["total_exp"], np.nan)
        panel["ins_pc"] = panel["ins_premium_real"] / panel["population"]
        panel["jc_pc"] = panel["judgments_real"] / panel["population"]
        panel["cor_share"] = np.where(panel["total_exp"] > 0, panel["cost_of_risk"] / panel["total_exp"], np.nan)
        panel["police_share"] = np.where(panel["total_exp"] > 0, panel["police_exp"] / panel["total_exp"], np.nan)
        panel["capital_share"] = np.where(panel["total_exp"] > 0, panel["capital_outlay"] / panel["total_exp"], np.nan)
    panel["fy"] = panel["fy"].astype(int)
    panel = panel.sort_values(key).reset_index(drop=True)
    panel.to_parquet(config.NY_PANEL_PARQUET, index=False)
    core = panel[panel["cls"].isin(config.OSC_CORE_CLASSES) & (panel["fy"] >= config.HEADLINE_YEARS[0])]
    print(f"  wrote {config.NY_PANEL_PARQUET.name}: {len(panel):,} entity-years; core headline-window rows "
          f"{len(core):,}, with population {core['population'].notna().mean():.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
