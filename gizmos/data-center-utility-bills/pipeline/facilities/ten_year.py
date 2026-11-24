#!/usr/bin/env python3
"""The ten-year material for Gate 1 (docs/DECISIONS.md, D-40's addendum): what the ten-year screen moves, and each
headline host's large permit-dated sites with what is on file about older operation.

Load and sales only; no price is read. Nothing here is applied to anyone: the screen that decides the
headline set is still D-20 at three and five years, and the written proposal for a site-specific check
(docs/gate1/ten-year-material.md) waits for Joe.

The shifts start every still permit-dated site of 20 MW or more 3, 5 and 10 years before its permit-based
year, as dating_sensitivity.py does. For hosts the test is D-20's (a change of group, or a cohort
crossing that moves by two years or more). For comparison utilities it is the eligibility rule itself:
still under 0.5% of base in every panel year.

Step D (D-58 rule 1.7, last point): each state's anchoring factor is recomputed in every shifted case
(dating_sensitivity.shifted_rows); the result with the factor held at its built value is kept beside it, and the
utilities that change for that reason alone are listed.

Run:  python3 -I pipeline/facilities/ten_year.py        (after treatment_bounds.py)
Output: data/frozen/ten_year_screen.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.facilities import dating_sensitivity as ds  # noqa: E402
from pipeline.facilities.buildout import RAMP_YEARS, ramp_mw  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
KEY = ds.KEY
SHIFTS = (3, 5, 10)
CLEAN_BELOW = 0.005


def shifted_share(rest: pd.DataFrame, sites: pd.DataFrame, where: pd.DataFrame, base: pd.Series, years, shift: int) -> pd.Series:
    """Each utility's largest load share in any panel year with the undated sites started `shift` years earlier."""
    rows = []
    for fid in where.index.intersection(sites.index):
        f = sites.loc[fid]
        start = f.energized_year - shift
        rows += [(where.utility_id_eia[fid], where.state[fid], y, ramp_mw(f.mw_full, start, y, RAMP_YEARS)) for y in years if y >= start]
    d = pd.concat([rest, pd.DataFrame(rows, columns=rest.columns)]).groupby(KEY + ["year"]).mw.sum().reset_index()
    d["share"] = d.mw * 8.76 / d.set_index(KEY).index.map(base)
    return d.groupby(KEY).share.max()


def shares_from_rows(rows: pd.DataFrame, base: pd.Series) -> pd.Series:
    """Each utility's largest load share in any panel year, from site-year rows (KEY, year, mw)."""
    d = rows.groupby(KEY + ["year"]).mw.sum().reset_index()
    d["share"] = d.mw * 8.76 / d.set_index(KEY).index.map(base)
    return d.groupby(KEY).share.max()


def main() -> int:
    from pipeline.analysis import power_simulation as ps
    from pipeline.electricity import panel
    from pipeline.facilities import sources

    fac = pd.read_parquet(INTERIM / "facilities.parquet").set_index("fid")
    fy = pd.read_parquet(INTERIM / "facility_year.parquet")
    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    q = panel.load_quantities()
    names = q.groupby(KEY).utility_name.last()
    base = dose.drop_duplicates(KEY).set_index(KEY).base_retail_gwh
    und = fac[fac.in_dose & ~fac.is_crypto & (fac.mw_full >= 20) & (fac.date_basis == "first_generator_permit_plus_lag")]
    years = range(int(fy.year.min()), int(fy.year.max()) + 1)
    fy = fy[~fy.crypto]
    where = fy[fy.fid.isin(und.index)].drop_duplicates("fid").set_index("fid")[KEY]
    rest = fy[~fy.fid.isin(und.index)][KEY + ["year", "mw"]]
    key_of = lambda k: f"{int(k[0])}:{k[1]}"  # noqa: E731
    head = pd.read_csv(FROZEN / "headline_set.csv")
    bi = sources.load_bi().set_index("src_id")
    leads = pd.read_csv(ROOT / "pipeline" / "facilities" / "leads" / "public_record_leads.csv")
    report = {"what_this_is": "What starting every still permit-dated site of 20 MW or more 3, 5 and 10 years earlier does to hosts and to comparison "
                              "utilities, and each headline host's such sites. Load and sales only. A stress test: it decides nothing.",
              "undated_large_sites_carrying_load": int(len(und)), "their_mw": round(float(und.mw_full.sum()), 1),
              "utilities_they_are_on": int(where.drop_duplicates().shape[0]),
              "of_them_filed_as_an_update_to_an_existing_source": int(und.left_censored.fillna(False).astype(bool).sum()), "thresholds": {}}
    anchor = pd.read_parquet(INTERIM / "state_anchor.parquet").set_index("state")
    fy_dc = pd.read_parquet(INTERIM / "facility_year.parquet")
    fy_dc = fy_dc[~fy_dc.crypto]
    rows = {(k, rc): ds.shifted_rows(fac, fy_dc, anchor, und, years, -k, recompute=rc) for k in (0,) + SHIFTS for rc in (True, False)}
    for theta in (0.02, 0.05):
        t = f"{theta:.0%}"
        cross = {k: ds.crossings(rows[(k, True)], base, theta) for k in (0,) + SHIFTS}
        held = {k: ds.crossings(rows[(k, False)], base, theta) for k in (0,) + SHIFTS}
        moved_held = {k: ds.dependent(held[0], held[k]) for k in SHIFTS}
        built = cross[0]
        treated, clean = ps.design(q, dose, theta, ps.history_settled(theta))
        cohort = set(zip(treated.utility_id_eia.astype(int), treated.state))
        moved = {k: ds.dependent(built, cross[k]) for k in SHIFTS}
        near = moved[3] | moved[5]
        ten_only = moved[10] - near
        h = head[head.threshold == t].set_index(KEY)
        in_head = {k for k in h.index if bool(h.at[k, "in_headline_set"])}
        groups = lambda s: {"early": int((s < 2011).sum()), "cohort": int(s.between(2011, 2022).sum()), "late": int((s > 2022).sum())}  # noqa: E731

        def describe(k):
            return {"utility": key_of(k), "name": names.get(k), "as_built": ds.cohort(built.get(k)) + ("" if pd.isna(built.get(k)) else f" {int(built.get(k))}"),
                    **{f"{n}_years_earlier": ("never" if pd.isna(cross[n].get(k)) else int(cross[n].get(k))) for n in SHIFTS},
                    "in_the_headline_set": k in in_head, "a_cohort_utility": k in cohort}

        comp = list(zip(clean.utility_id_eia.astype(int), clean.state))
        aside = ps.set_aside(theta)
        eligible = [k for k in comp if k not in aside]
        comp_fail = {}
        for n in SHIFTS:
            share = shares_from_rows(rows[(n, True)], base)
            comp_fail[n] = sorted(k for k in eligible if share.get(k, 0.0) >= CLEAN_BELOW)
        comp_hosting = sorted({tuple(x) for x in where.drop_duplicates().values} & set(eligible))
        report["thresholds"][t] = {
            "groups_as_built": groups(built), **{f"groups_at_{n}_years_earlier": groups(cross[n]) for n in SHIFTS},
            "utilities_that_change_place": {f"at_{n}_years": len(moved[n]) for n in SHIFTS},
            "factor": "recomputed in every shifted case (D-58 rule 1.7, from step D)",
            "factor_held_at_its_built_value": {"utilities_that_change_place": {f"at_{n}_years": len(moved_held[n]) for n in SHIFTS}},
            "changed_by_the_factor_recompute_alone": {f"at_{n}_years": {
                "move_only_with_the_factor_recomputed": [key_of(k) for k in sorted(moved[n] - moved_held[n])],
                "move_only_with_the_factor_held": [key_of(k) for k in sorted(moved_held[n] - moved[n])]} for n in SHIFTS},
            "the_standard_screen_three_and_five_years": {"utilities": len(near), "of_which_cohort_utilities": len(near & cohort)},
            "moved_by_ten_years_and_by_neither_three_nor_five": {
                "utilities": len(ten_only), "of_which_cohort_utilities": len(ten_only & cohort),
                "of_which_in_the_headline_set": len(ten_only & in_head), "list": [describe(k) for k in sorted(ten_only, key=lambda k: (k[1], k[0]))]},
            "headline_set": {"hosts": len(in_head), "left_if_the_ten_year_case_were_also_a_screen": len(in_head - ten_only),
                             "would_leave": [names.get(k) for k in sorted(in_head & ten_only, key=lambda k: (k[1], k[0]))]},
            "comparison_utilities": {
                "eligible": len(eligible), "of_which_carry_an_undated_large_site": len(comp_hosting),
                **{f"no_longer_under_0.5pct_at_{n}_years_earlier": len(comp_fail[n]) for n in SHIFTS},
                "names_at_ten_years": [names.get(k) for k in comp_fail[10]],
                "why_so_few": "a site of 20 MW is 175 GWh a year, so a utility that carries one and is still under 0.5% has to sell 35 TWh or more"},
        }
    sites = []
    h2 = head[(head.threshold == "2%") & head.in_headline_set]
    for r in h2.itertuples():
        mine = und[(und.utility_id_eia == r.utility_id_eia) & (und.state == r.state)].sort_values("mw_full", ascending=False)
        for fid, f in mine.iterrows():
            lead = leads[leads.fid == fid]
            sites.append({"host": r.name, "host_first_crossing": int(r.first_crossing), "site": fid, "operator": f.operator,
                          "place": f"{bi.city.get(fid) or ''}, {f.county_name} County, {f.state}".strip(", "),
                          "mw": round(float(f.mw_full), 1), "permit_based_start": int(f.energized_year), "first_permit_year": int(f.first_permit_year),
                          "latest_permit_year": int(f.latest_permit_year), "permit_kind": bi.permit_kind.get(fid),
                          "filed_as_an_update_to_an_existing_source": bool(f.left_censored) if pd.notna(f.left_censored) else False,
                          "serving_utility": f.utility_assign, "after_the_hosts_first_crossing": bool(f.energized_year > r.first_crossing),
                          "public_record_on_file": None if lead.empty else {"source": lead.source.iloc[0], "record": lead.record.iloc[0], "caution": lead.caution.iloc[0]}})
    report["headline_hosts_permit_dated_sites_of_20_mw_or_more"] = sites
    report["headline_hosts_with_none"] = sorted(set(h2.name) - {s["host"] for s in sites})
    from pipeline.facilities import corrections as cx
    report["fingerprint"] = cx.fingerprint([*cx.code_files(), INTERIM / "facilities.parquet", INTERIM / "facility_year.parquet",
                                            INTERIM / "state_anchor.parquet", FROZEN / "headline_set.csv"],
                                           thresholds=[0.02, 0.05], shifts=list(SHIFTS), min_mw=20)
    (FROZEN / "ten_year_screen.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({t: {k: v for k, v in r.items() if k != "moved_by_ten_years_and_by_neither_three_nor_five"} for t, r in report["thresholds"].items()}, indent=1, default=str))
    print(json.dumps(report["thresholds"]["2%"]["moved_by_ten_years_and_by_neither_three_nor_five"], indent=1, default=str))
    for s in sites:
        print(s["host"], s["site"], s["operator"], s["place"], s["mw"], s["permit_based_start"], s["permit_kind"], s["after_the_hosts_first_crossing"], bool(s["public_record_on_file"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
