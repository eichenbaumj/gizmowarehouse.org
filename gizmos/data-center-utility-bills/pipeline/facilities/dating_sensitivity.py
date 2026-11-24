#!/usr/bin/env python3
"""Which utilities' treatment timing depends on large sites that are still permit-dated.

After the dating passes (docs/DECISIONS.md, D-15 to D-18) some sites of 20 MW
or more still carry only a permit-based start year. This script asks what that
could do to the design, using load and sales quantities only. No price data.

Three kinds of case, each recomputing every utility's load share (D-26, D-28):

  earlier  the undated sites started 3, 5 and 10 years before their permit-based
           year. Permit years miss late far more often than early: about one
           permit-dated site in four is five or more years late.
  later    they started 2 and 3 years after it. About 7% of permit-dated sites
           with a sourced year opened three or more years after the permit said.
  status   the sites whose operating status two public records disagree on, or
           that no dated page settles, carry no load at all (UNSETTLED_STATUS).

A utility's timing "depends on undated sites" under a case if it enters or
leaves the 2011 to 2022 cohorts, or stays in them with a first-crossing year
that moves by two years or more (D-10's tolerance). The set D-20 sets aside
from the headline is the one from the earlier cases, as D-20 defined it; the
later and status cases are reported next to it and their utilities listed.

The shifts are illustrative bounds, not estimates. The registered misdating
stress test (PREANALYSIS.md) redraws dates from the measured error distribution.

Step D (D-58 rule 1.7, last point): the state's anchoring factor is recomputed in
every case. A shifted site's 2024 load changes with its start when that start is
2022 or later, which changes the state's permit-based 2024 total and so the factor
on every other permit-based site in the state. The figures with the factor held at
its built value are kept beside, and every utility whose result changes for that
reason alone is listed. Sites with a dated interval (step D's corrections) carry
another date_basis and are tested over their intervals (timing.py), not here.

Output: data/frozen/dating_sensitivity.json
Run after build_inventory.py:  python3 -I pipeline/facilities/dating_sensitivity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.facilities.buildout import RAMP_YEARS, ramp_mw  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

COHORTS = (2011, 2022)
EARLIER = (3, 5, 10)
LATER = (2, 3)
MOVE_TOLERANCE = 2
KEY = ["utility_id_eia", "state"]
# Sites that may not be operating. None has a dated public page saying it is running or is not (D-17, D-18).
UNSETTLED_STATUS = {
    "bi:1301-0": "QTS Glendale, Arizona: the operator's page says 'In Development'; the assessor's roll shows partly built buildings",
    "bi:32-0": "STACK Phoenix 02, Arizona: the assessor's roll shows the land vacant",
    "bi:1004-3": "Amazon Village Place, Gainesville, Virginia: the county lists it under construction, the state lists it operating",
    "bi:976-0": "Microsoft AVC17, near Clarksville, Virginia: a news page says under construction, the state lists it operating",
}


def cohort(first_year) -> str:
    if pd.isna(first_year):
        return "never"
    return "before" if first_year < COHORTS[0] else ("treated" if first_year <= COHORTS[1] else "later")


def moved(a, b) -> bool:
    """Does a first crossing that goes from a to b change the utility's place in the design?"""
    return cohort(a) != cohort(b) or (cohort(a) == "treated" and abs(a - b) >= MOVE_TOLERANCE)


def first_crossings(rest: pd.DataFrame, sites: pd.DataFrame, where: pd.DataFrame, base: pd.Series, years,
                    theta: float, shift: int | None) -> pd.Series:
    """First year each utility's load share reaches theta.

    `sites` are put back with their start moved by `shift` years (negative is earlier);
    shift=None leaves them out altogether.
    """
    parts = [rest]
    if shift is not None and len(sites):
        rows = []
        for fid in where.index.intersection(sites.index):
            f = sites.loc[fid]
            start = f.energized_year + shift
            rows += [(where.utility_id_eia[fid], where.state[fid], y, ramp_mw(f.mw_full, start, y, RAMP_YEARS))
                     for y in years if y >= start]
        parts.append(pd.DataFrame(rows, columns=rest.columns))
    d = pd.concat(parts).groupby(KEY + ["year"]).mw.sum().reset_index()
    d["dose"] = d.mw * 8.76 / d.set_index(KEY).index.map(base)
    return d[d.dose >= theta].groupby(KEY).year.min()


def factor_after_shift(fac: pd.DataFrame, fy: pd.DataFrame, anchor: pd.DataFrame, sites, shift: int | None) -> dict:
    """Each state's anchoring factor with `sites` started `shift` years later (negative: earlier), recomputed by
    build_inventory's arithmetic (pass_c_expand._factor): the EPRI total less measured load, over the permit-based 2024
    total. A site's own 2024 contribution is read from its built 2024 site-year, unscaled. shift None takes the sites out."""
    out = {}
    y24 = fy[fy.year == px.ANCHOR_YEAR].groupby("fid").mw.sum()
    for st in sorted({fac.state[f] for f in sites if f in fac.index}):
        if st not in anchor.index:
            continue
        a = anchor.loc[st]
        delta = 0.0
        for fid in [f for f in sites if f in fac.index and fac.state[f] == st]:
            r = fac.loc[fid]
            before = float(y24.get(fid, 0.0)) / float(r.state_scale)
            after = 0.0 if shift is None else ramp_mw(float(r.mw_full_raw), float(r.energized_year) + shift, px.ANCHOR_YEAR, RAMP_YEARS)
            delta += (after - before) * 8.76 / 1000.0
        f0 = float(a.factor)
        f1 = px._factor(float(a.epri_twh), float(a.epoch_twh), float(a.permit_twh) + delta)
        out[st] = f0 if abs(f1 - f0) <= px.FACTOR_TOL * max(1.0, abs(f0)) else f1
    return out


def shifted_rows(fac: pd.DataFrame, fy: pd.DataFrame, anchor: pd.DataFrame, sites: pd.DataFrame, years, shift: int | None,
                 recompute: bool = True) -> pd.DataFrame:
    """Data-center site-years (KEY, year, mw) with `sites` started `shift` years later (negative: earlier) and, with
    `recompute`, every permit-based site in an affected state rescaled to the recomputed factor. recompute=False is the
    screen as first written (the factor held at its built value)."""
    measured = (fac.src == "epoch") | fac.mw_basis.isin(px.MEASURED_BASIS)
    ids = [f for f in sites.index if f in fac.index]
    new = factor_after_shift(fac, fy, anchor, ids, shift) if recompute else {}
    ratio = {st: f / float(anchor.factor[st]) for st, f in new.items()}
    rest = fy[~fy.fid.isin(ids)].copy()
    scale = rest.fid.map(lambda f: 1.0 if bool(measured.get(f, False)) else ratio.get(fac.state.get(f), 1.0))
    rest["mw"] = rest.mw * scale.values
    parts = [rest[KEY + ["year", "mw"]]]
    if shift is not None:
        rows = []
        for fid in ids:
            f = fac.loc[fid]
            if pd.isna(f.utility_id_eia):
                continue
            mw = float(f.mw_full_raw) * new[f.state] if f.state in new else float(f.mw_full)
            start = f.energized_year + shift
            rows += [(int(f.utility_id_eia), f.state, y, ramp_mw(mw, start, y, RAMP_YEARS)) for y in years if y >= start]
        if rows:
            parts.append(pd.DataFrame(rows, columns=KEY + ["year", "mw"]))
    return pd.concat(parts, ignore_index=True)


def crossings(rows: pd.DataFrame, base: pd.Series, theta: float) -> pd.Series:
    d = rows.groupby(KEY + ["year"]).mw.sum().reset_index()
    d["dose"] = d.mw * 8.76 / d.set_index(KEY).index.map(base)
    return d[d.dose >= theta].groupby(KEY).year.min()


def dependent(built: pd.Series, alt: pd.Series) -> set:
    return {u for u in set(built.index) | set(alt.index) if moved(built.get(u), alt.get(u))}


def groups(first: pd.Series) -> dict:
    g = first.map(cohort).value_counts()
    return {"early_hosts": int(g.get("before", 0)), "cohort_utilities": int(g.get("treated", 0)),
            "late_hosts": int(g.get("later", 0))}


def main() -> int:
    fac = pd.read_parquet(ROOT / "data" / "interim" / "facilities.parquet").set_index("fid")
    fy = pd.read_parquet(ROOT / "data" / "interim" / "facility_year.parquet")
    dose = pd.read_parquet(ROOT / "data" / "interim" / "utility_year_dose.parquet")
    base = dose.drop_duplicates(KEY).set_index(KEY).base_retail_gwh
    und = fac[fac.in_dose & ~fac.is_crypto & (fac.mw_full >= 20) & (fac.date_basis == "first_generator_permit_plus_lag")]
    years = range(int(fy.year.min()), int(fy.year.max()) + 1)
    fy = fy[~fy.crypto]
    where = fy[fy.fid.isin(und.index)].drop_duplicates("fid").set_index("fid")[KEY]
    rest = fy[~fy.fid.isin(und.index)][KEY + ["year", "mw"]]
    unsettled = [f for f in UNSETTLED_STATUS if f in fac.index and bool(fac.in_dose.get(f, False))]
    without_unsettled = fy[~fy.fid.isin(unsettled)][KEY + ["year", "mw"]]

    hosts = set(map(tuple, where.drop_duplicates().values))
    fmt = lambda s: sorted(f"{int(u[0])}:{u[1]}" for u in s)  # noqa: E731
    report = {"undated_large_sites_carrying_load": int(len(und)), "their_mw": round(float(und.mw_full.sum()), 1),
              "utilities_hosting_them": len(hosts),
              "definition": f"timing depends on undated sites if, with those sites started {', '.join(map(str, EARLIER))} years "
                            f"earlier, the utility enters or leaves the {COHORTS[0]}-{COHORTS[1]} cohorts or its first crossing "
                            f"moves by {MOVE_TOLERANCE} years or more (D-20). The later-start and status cases use the same test.",
              "sites_that_may_not_be_operating": {f: {"why": UNSETTLED_STATUS[f], "mw": round(float(fac.mw_full[f]), 1),
                                                      "permit_based_start": int(fac.energized_year[f]),
                                                      "sourced_start_year": bool(fac.date_basis[f] != "first_generator_permit_plus_lag")}
                                                  for f in unsettled},
              "thresholds": {}}
    anchor = pd.read_parquet(ROOT / "data" / "interim" / "state_anchor.parquet").set_index("state")
    fy_all = pd.read_parquet(ROOT / "data" / "interim" / "facility_year.parquet")
    fy_dc = fy_all[~fy_all.crypto]

    def block(theta: float, recompute: bool) -> dict:
        cross = lambda shift: crossings(shifted_rows(fac, fy_dc, anchor, und, years, shift, recompute), base, theta)  # noqa: E731
        built = cross(0)
        treated = {u for u, y in built.items() if cohort(y) == "treated"}
        by_shift = {k: dependent(built, cross(-k)) for k in EARLIER}
        earlier = set().union(*by_shift.values())
        later = set().union(*(dependent(built, cross(k)) for k in LATER))
        no_unsettled = first_crossings(without_unsettled, und.iloc[:0], where, base, years, theta, None)
        status = dependent(built, no_unsettled)
        ever = lambda s: set(s.index)  # noqa: E731
        removed = cross(None)
        return {
            "as_built": groups(built),
            "treated_as_built": len(treated),
            "treated_hosting_an_undated_large_site": len(treated & hosts),
            "utilities_whose_timing_depends_on_undated_sites": len(earlier),
            "of_which_treated_as_built": len(earlier & treated),
            "treated_whose_timing_does_not_depend_on_them": len(treated - earlier),
            "treated_if_undated_sites_are_removed": int(sum(cohort(y) == "treated" for y in removed)),
            "treated_if_started_earlier": {f"{k}_years": int(sum(cohort(y) == "treated" for y in cross(-k))) for k in EARLIER},
            "dependent_utilities": fmt(earlier),
            "dependent_utilities_by_years_earlier": {f"{k}_years": fmt(v) for k, v in by_shift.items()},
            "groups_if_started_earlier": {f"{k}_years": groups(cross(-k)) for k in EARLIER},
            "groups_if_started_later": {f"{k}_years": groups(cross(k)) for k in LATER},
            "also_dependent_if_started_later": fmt(later - earlier),
            "of_which_treated_as_built_later": len((later - earlier) & treated),
            "groups_if_unsettled_sites_are_not_operating": groups(no_unsettled),
            "utilities_that_change_group_if_unsettled_sites_are_not_operating": fmt(status),
            "utilities_that_stop_being_hosts_if_unsettled_sites_are_not_operating": fmt(ever(built) - ever(no_unsettled)),
            "treated_whose_timing_depends_on_none_of_the_three": len(treated - earlier - later - status),
        }

    report["factor"] = ("recomputed in every case (D-58 rule 1.7, from step D); the figures with the factor held at its "
                        "built value are under factor_held_at_its_built_value")
    report["state_factor_by_case"] = {f"{k}_years_earlier": factor_after_shift(fac, fy_dc, anchor, list(und.index), -k)
                                      for k in EARLIER}
    for theta in (0.02, 0.05):
        t = f"{theta:.0%}"
        new, old = block(theta, True), block(theta, False)
        moved_alone = {}
        for k in EARLIER:
            a = set(new["dependent_utilities_by_years_earlier"][f"{k}_years"])
            b = set(old["dependent_utilities_by_years_earlier"][f"{k}_years"])
            moved_alone[f"{k}_years"] = {"dependent_only_with_the_factor_recomputed": sorted(a - b),
                                         "dependent_only_with_the_factor_held": sorted(b - a)}
        report["thresholds"][t] = {**new, "factor_held_at_its_built_value": old,
                                   "changed_by_the_factor_recompute_alone": moved_alone}
    from pipeline.facilities import corrections as cx
    report["fingerprint"] = cx.fingerprint([*cx.code_files(), ROOT / "data" / "interim" / "facilities.parquet",
                                            ROOT / "data" / "interim" / "facility_year.parquet",
                                            ROOT / "data" / "interim" / "state_anchor.parquet"],
                                           thresholds=[0.02, 0.05], earlier=list(EARLIER), later=list(LATER), min_mw=20)
    (ROOT / "data" / "frozen" / "dating_sensitivity.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
