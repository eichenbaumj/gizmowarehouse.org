#!/usr/bin/env python3
"""Where the dating of large sites stands, and how wrong permit-based years are.

Reads the built inventory and the round 3 worklist; touches no price data.

Reports, into data/frozen/dating_report.json:

  * the round 3 worklist (large sites that had only a permit-based year):
    how many now have a sourced start year, how many a dated public page
    shows as not yet operating, how many are still open;
  * treated-utility counts at the 2% and 5% thresholds, first crossing
    2011 to 2022 (the cohorts in PREANALYSIS.md);
  * the dating-error rate of the permit method: permit year plus one against
    the sourced year, for every permit-dated site that now has one. Round 3
    checkers were not shown the permit year, so their sites are reported
    separately as the cleanest read.

Run after apply_verified.py and build_inventory.py:
      python3 -I pipeline/facilities/dating_report.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.facilities.build_inventory import PERMIT_LAG  # noqa: E402

VER = ROOT / "pipeline" / "facilities" / "verified"
FROZEN = ROOT / "data" / "frozen"
COHORTS = (2011, 2022)


def error_stats(d: pd.DataFrame) -> dict:
    """d.err = permit-based year minus sourced year (positive: we dated it too late)."""
    if not len(d):
        return {"n": 0}
    e = d.err
    return {"n": int(len(d)),
            "within_1_year": round(float((e.abs() <= 1).mean()), 3),
            "within_2_years": round(float((e.abs() <= 2).mean()), 3),
            "permit_5_or_more_years_late": round(float((e >= 5).mean()), 3),
            "permit_3_or_more_years_early": round(float((e <= -3).mean()), 3),
            "median_error_years": float(e.median()),
            "mean_error_years": round(float(e.mean()), 2)}


def main() -> int:
    fac = pd.read_parquet(ROOT / "data" / "interim" / "facilities.parquet").set_index("fid")
    dose = pd.read_parquet(ROOT / "data" / "interim" / "utility_year_dose.parquet")
    work = pd.read_csv(VER / "r3_worklist.csv")
    r3_fids = {r["fid"] for p in glob.glob(str(VER / "batch_r3_*.json")) for r in json.loads(Path(p).read_text())}

    w = work.join(fac[["verified_fields", "date_basis", "mw_full", "energized_year"]], on="fid")
    gone = w.date_basis.isna()
    sourced = w.verified_fields.fillna("").str.contains("year")
    not_yet = w.date_basis.eq("verified_not_yet_operating")
    looked_up = w.fid.isin(r3_fids)
    worklist = {
        "sites": int(len(w)),
        "looked_up_so_far": int(looked_up.sum()),
        "sourced_start_year": int(sourced.sum()),
        "verified_not_yet_operating": int(not_yet.sum()),
        "no_longer_in_inventory": int(gone.sum()),
        "still_permit_dated": int((~sourced & ~not_yet & ~gone).sum()),
        "still_permit_dated_not_yet_looked_up": int((~sourced & ~not_yet & ~gone & ~looked_up).sum()),
        "mw_at_worklist_time": round(float(w.mw_at_worklist_time.sum()), 1),
        "mw_at_worklist_time_resolved": round(float(w.mw_at_worklist_time[sourced | not_yet | gone].sum()), 1),
    }

    treated = {}
    for theta in (0.02, 0.05):
        first = dose[dose.dose >= theta].groupby(["utility_id_eia", "state"]).year.min()
        treated[f"{theta:.0%}"] = {
            f"first_crossing_{COHORTS[0]}_{COHORTS[1]}": int(first.between(*COHORTS).sum()),
            "already_above_before_2011": int((first < COHORTS[0]).sum()),
            "first_crossing_2023_or_later": int((first > COHORTS[1]).sum()),
        }

    # Permit method against sourced years. Epoch rows never had a permit-based year.
    v = fac[(fac.src == "bi") & fac.verified_fields.fillna("").str.contains("year") & fac.first_permit_year.notna()].copy()
    v["err"] = (v.first_permit_year + PERMIT_LAG) - v.energized_year
    v["round3"] = v.index.isin(r3_fids)
    size = pd.cut(v.generator_kw.fillna(0) * 0.5 / 1000, [0, 20, 50, float("inf")], labels=["under_20", "20_to_50", "50_plus"],
                  right=False)
    errors = {
        "definition": f"first generator permit year + {PERMIT_LAG}, minus the sourced start year; positive means the permit dated the site too late",
        "all_permit_dated_sites_with_a_sourced_year": error_stats(v),
        "round_3_only_checker_blind_to_permit_year": error_stats(v[v.round3]),
        "earlier_rounds_only": error_stats(v[~v.round3]),
        "by_generator_based_size_mw": {str(k): error_stats(g) for k, g in v.groupby(size, observed=True)},
        # Every measured error, by size class: the distribution the misdating stress test draws from (PREANALYSIS.md).
        "errors_in_years_by_generator_based_size_mw": {str(k): sorted(int(e) for e in g.err) for k, g in v.groupby(size, observed=True)},
    }

    counted = fac[fac.in_dose & ~fac.is_crypto]
    big = counted[counted.mw_full >= 20]
    has_year = (counted.src == "epoch") | counted.verified_fields.fillna("").str.contains("year")
    coverage = {
        "sites_20mw_plus_in_load_measure": int(len(big)),
        "of_which_sourced_year_or_epoch": int(has_year.reindex(big.index).sum()),
        "share_of_counted_load_with_sourced_year_or_epoch": round(float(counted.mw_full[has_year].sum() / counted.mw_full.sum()), 3),
    }

    # The 60-site random sample of smaller sites: the national read on small-site dating.
    sm = pd.read_csv(VER / "sample_worklist.csv")
    in_inv = sm[sm.fid.isin(fac.index)]
    sv = v[v.index.isin(sm.fid)]
    # Split at 20 MW of generator-based size: the larger sample sites are also on the round 3
    # worklist, and the smaller ones are the only national read on small-site dating.
    sv_small = sv[sv.generator_kw.fillna(0) * 0.5 / 1000 < 20]
    errors["random_sample_of_smaller_sites"] = {
        "sample_sites": int(len(sm)), "still_in_inventory": int(len(in_inv)),
        "with_a_sourced_year": int(fac.loc[in_inv.fid].verified_fields.fillna("").str.contains("year").sum()),
        "verified_not_yet_operating": int(fac.loc[in_inv.fid].date_basis.eq("verified_not_yet_operating").sum()),
        **error_stats(sv),
        "errors_in_years": sorted(int(e) for e in sv.err),
        "generator_based_under_20_mw": {**error_stats(sv_small), "errors_in_years": sorted(int(e) for e in sv_small.err)},
        "generator_based_20_mw_and_up": error_stats(sv[~sv.index.isin(sv_small.index)]),
        "caution": "Small numbers, and only sites that could be sourced are measured; the ones still open may differ.",
    }

    report = {"round_3_worklist": worklist, "treated_utilities": treated, "permit_dating_error": errors,
              "dating_coverage": coverage}
    (FROZEN / "dating_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
