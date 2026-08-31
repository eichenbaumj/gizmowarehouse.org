"""Stage 07 — workforce composition for the Sankey + within-domain composition
for the tooltips.

Reads the cached latest-year PUMS state parquets directly (the slim analysis
frame drops SOCP, which we need here) and produces two shipped files:

  workforce_composition.json  — government employment (millions, ACS weighted) by
      level x workgroup, on a RICHER occupation taxonomy than the 11 wage domains
      (soc_to_workgroup.csv) so the Sankey's "Other" slice stays small. Active-duty
      military is its own workgroup. Carries a universe note explaining why these
      ACS totals differ from the CES headcounts in the hero strip.

  domain_composition.json     — per wage-domain: a plain-English "includes" string
      and, for Legal and Protective service, the government-vs-private mix of
      sub-occupations (lawyers vs paralegals; police/fire vs security guards).

Universe: employed residents aged 25-64, wage/salary class of worker (COW 1-5),
ACS 1-year PUMS (latest year). Civilian employed (ESR 1-2) PLUS armed forces
(ESR 4-5), so the military shows up. Weighted by PWGTP.

Run: python 07_workforce_composition.py
"""

from __future__ import annotations

import json
import glob

import numpy as np
import pandas as pd

import config
from pums_lib import load_crosswalk, map_domain

PUMS_RAW = config.RAW_DIR / "pums"
YEAR = config.PUMS_LATEST_YEAR


def load_workgroup_xwalk() -> list[tuple[str, str, str]]:
    """[(soc_prefix, workgroup, label)] sorted longest-prefix-first."""
    df = pd.read_csv(config.CROSSWALK_DIR / "soc_to_workgroup.csv", dtype={"soc_prefix": str})
    rows = [(str(r.soc_prefix), r.workgroup, r.workgroup_label) for r in df.itertuples()]
    return sorted(rows, key=lambda t: -len(t[0]))


def map_workgroup(socp: str, xwalk) -> str:
    if not isinstance(socp, str):
        return "other"
    for prefix, wg, _ in xwalk:
        if socp.startswith(prefix):
            return wg
    return "other"


# Plain-English description of what each wage-domain filter includes (the SOC
# mapping in human terms). Stable, hand-written, used in the domain tooltips.
DOMAIN_INCLUDES = {
    "all": "Every occupation, government and private.",
    "software_it": "Software developers, IT and systems administration, data, "
                   "cybersecurity, and other computer occupations (SOC 15-1).",
    "legal": "Lawyers, judges, paralegals, and legal support workers (SOC 23).",
    "finance": "Accountants, auditors, financial analysts, and examiners (SOC 13-2).",
    "engineering": "Civil, mechanical, electrical, and other professional engineers (SOC 17-2).",
    "management": "Managers, directors, and executives across all functions (SOC 11).",
    "healthcare": "Physicians, nurses, pharmacists, therapists, and other clinicians (SOC 29).",
    "education": "Teachers, professors, instructors, and librarians (SOC 25).",
    "protective_service": "Police, firefighters, corrections officers, detectives, and "
                          "security guards (SOC 33).",
    "skilled_trades": "Electricians, plumbers, mechanics, and other building and "
                      "repair trades (SOC 47 and 49).",
    "admin_clerical": "Clerks, secretaries, administrative specialists, and postal "
                      "workers (SOC 43).",
}

# Sub-occupation buckets for the two domains Joe asked about, keyed by 4-digit SOC
# minor group. The mix differs sharply between government and private (e.g. private
# "Protective service" is mostly mall-type security guards), which is the whole
# point of showing it.
SUBGROUPS = {
    "legal": {
        "2310": "Lawyers & judges",
        "2320": "Paralegals & legal support",
    },
    "protective_service": {
        "3330": "Police, detectives & corrections",
        "3320": "Firefighters",
        "3310": "First-line supervisors",
        "3390": "Security guards & other",
    },
}


def load_latest_pums() -> pd.DataFrame:
    files = sorted(glob.glob(str(PUMS_RAW / f"{YEAR}_*.parquet")))
    if not files:
        raise RuntimeError(f"No {YEAR} PUMS parquets in raw/pums — run stage 03 first.")
    df = pd.concat(
        (pd.read_parquet(f, columns=["PWGTP", "COW", "SOCP", "AGEP", "ESR"]) for f in files),
        ignore_index=True,
    )
    df = df[df["AGEP"].between(config.AGE_MIN, config.AGE_MAX)]
    df["cow"] = df["COW"].astype(str).str.replace(".0", "", regex=False)
    df["esr"] = df["ESR"].astype(str).str.replace(".0", "", regex=False)
    df = df[df["cow"].isin(config.PUMS_COW)]
    df = df[df["esr"].isin(["1", "2", "4", "5"])]   # employed civilian + armed forces
    df["govlevel"] = df["cow"].map(config.PUMS_COW)
    df["soc"] = df["SOCP"].astype(str)
    df["weight"] = pd.to_numeric(df["PWGTP"], errors="coerce").fillna(0.0)
    return df


def main() -> None:
    print("Stage 07 — workforce composition")
    df = load_latest_pums()
    print(f"  {YEAR} employed (25-64, COW 1-5, incl. armed forces): {len(df):,} rows")

    # ---------- workforce_composition.json (Sankey) ----------
    wg_x = load_workgroup_xwalk()
    wg_labels = {wg: lab for _, wg, lab in wg_x}
    wg_labels["other"] = "Other occupations"
    df["workgroup"] = df["soc"].map(lambda s: map_workgroup(s, wg_x))
    # Count ALL uniformed personnel (armed forces by ESR) as military, not just the
    # military-specific occupation codes (SOC 55). Otherwise service members in
    # medical, legal, admin, or trade roles scatter into civilian buckets and the
    # military slice (0.43M) badly understates the ~0.85M uniformed force aged 25-64.
    df.loc[df["esr"].isin(["4", "5"]), "workgroup"] = "military"

    gov = df[df["govlevel"].isin(["federal", "state", "local"])]
    levels = ["federal", "state", "local"]
    matrix = []
    for lvl in levels:
        sub = gov[gov["govlevel"] == lvl]
        tot = sub["weight"].sum()
        for wg, g in sub.groupby("workgroup"):
            m = g["weight"].sum() / 1e6
            if m <= 0:
                continue
            matrix.append({
                "govlevel": lvl,
                "workgroup": wg,
                "employed_m": round(float(m), 3),
                "share_of_level_pct": round(float(g["weight"].sum() / tot * 100), 1),
            })

    wg_totals = (gov.groupby("workgroup")["weight"].sum() / 1e6).sort_values(ascending=False)
    workgroups = [{"key": wg, "label": wg_labels.get(wg, wg), "total_m": round(float(v), 3)}
                  for wg, v in wg_totals.items()]
    level_totals = {lvl: round(float(gov[gov["govlevel"] == lvl]["weight"].sum() / 1e6), 2)
                    for lvl in levels}
    other_share = round(float(wg_totals.get("other", 0.0) / wg_totals.sum() * 100), 1)

    # CES headcounts (the hero strip) for the explicit ACS-vs-CES reconciliation.
    shape = json.loads((config.OUTPUT_DIR / "shape.json").read_text())["latest"]
    ces = {"federal": round(shape["federal_k"] / 1000, 2),
           "state": round(shape["state_k"] / 1000, 2),
           "local": round(shape["local_k"] / 1000, 2)}

    (config.PUBLIC_DATA_DIR / "workforce_composition.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION,
        "year": YEAR,
        "source": "acs_pums",
        "universe": "Employed residents aged 25-64, wage/salary workers (incl. active-duty "
                    "military), ACS 1-year PUMS, weighted by person weight.",
        "levels": levels,
        "level_totals_m": level_totals,
        "ces_level_totals_m": ces,
        "acs_vs_ces_note": (
            "These ACS figures count employed *people* aged 25-64 by their occupation, and "
            "include active-duty military; the hero strip above uses BLS CES, which counts "
            "payroll *jobs* of all ages, civilian only. The two measure different things, so "
            "the totals don't match exactly — the Sankey is about the occupation mix, not the "
            "headcount."),
        "workgroups": workgroups,
        "matrix": matrix,
        "other_share_pct": other_share,
    }, separators=(",", ":")))
    print(f"  workforce_composition.json: {len(matrix)} flows, {len(workgroups)} workgroups, "
          f"'Other' = {other_share}% of government")
    print(f"    ACS level totals (M): {level_totals}  |  CES: {ces}")

    # ---------- domain_composition.json (tooltips) ----------
    xwalk = load_crosswalk()
    df["domain"] = df["soc"].map(lambda s: map_domain(s, xwalk))
    df["sector"] = np.where(df["cow"].isin(config.COW_PUBLIC), "government",
                    np.where(df["cow"].isin(config.COW_PRIVATE), "private", "other"))

    domains_out = {}
    for dom, includes in DOMAIN_INCLUDES.items():
        rec = {"includes": includes}
        if dom in SUBGROUPS:
            buckets = SUBGROUPS[dom]
            sub = df[(df["domain"] == dom) & (df["sector"].isin(["government", "private"]))].copy()
            sub["bucket"] = sub["soc"].str[:4].map(buckets).fillna("Other roles")
            breakdown = {}
            for sec in ["government", "private"]:
                s = sub[sub["sector"] == sec]
                tot = s["weight"].sum()
                if tot <= 0:
                    continue
                shares = (s.groupby("bucket")["weight"].sum() / tot * 100).sort_values(ascending=False)
                breakdown[sec] = [{"label": b, "pct": round(float(p))} for b, p in shares.items()]
            rec["breakdown"] = breakdown
        domains_out[dom] = rec

    (config.PUBLIC_DATA_DIR / "domain_composition.json").write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION,
        "year": YEAR,
        "source": "acs_pums",
        "note": "Plain-English description of each occupation filter, plus the "
                "government-vs-private sub-occupation mix for Legal and Protective service "
                "(ACS PUMS, employed 25-64).",
        "domains": domains_out,
    }, separators=(",", ":")))
    print(f"  domain_composition.json: {len(domains_out)} domains "
          f"({', '.join(SUBGROUPS)} with gov/private breakdown)")
    print("Stage 07 done.")


if __name__ == "__main__":
    main()
