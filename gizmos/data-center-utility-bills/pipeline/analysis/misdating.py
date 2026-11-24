#!/usr/bin/env python3
"""How far off each cohort utility's first-crossing year could be, given how wrong permit-based years are.

A utility's first crossing rests on its sites' start years. Some are sourced;
the rest are a generator permit year plus one, and the dating passes measured
how wrong that is (data/frozen/dating_report.json: about one site in four is
dated five or more years late). This module turns the site-level error into a
utility-level one, from load and sales quantities only. No price.

For each cohort utility, many times over: every site of its that is still
permit-dated gets a start year redrawn as its recorded year minus an error
drawn from the measured errors of sites in its size class; its load is ramped
from the redrawn year; the utility's first crossing is recomputed. The gap
between the redrawn crossing and the recorded one is that utility's date error
in that draw. Sites with a sourced year, an operator's reported electricity or
Epoch's timeline are left as they are, and a utility whose first crossing rests
on its own count of its load (D-34) has no error.

The power simulation gives each stand-in host a date error drawn from the
distribution of the host it stands in for (D-38).

Output: data/frozen/misdating.json
Run after build_inventory.py and dating_report.py:  python3 -I pipeline/analysis/misdating.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.electricity import panel  # noqa: E402
from pipeline.facilities.buildout import RAMP_YEARS  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
SEED = 20261113
DRAWS = 1000
NEVER = 99                      # the redrawn dates leave the utility under the threshold through 2025
KEY = ps.KEY
SIZE_EDGES = (20.0, 50.0)       # generator-based MW, the classes the dating report uses
SIZE_LABELS = ("under_20", "20_to_50", "50_plus")


def size_class(generator_kw) -> str:
    mw = 0.0 if pd.isna(generator_kw) else float(generator_kw) * 0.5 / 1000.0
    return SIZE_LABELS[int(np.digitize(mw, SIZE_EDGES))]


def crossing_errors(recorded: int, other_mw: np.ndarray, sites: pd.DataFrame, base_gwh: float, theta: float,
                    errors: dict[str, np.ndarray], years: np.ndarray, rng: np.random.Generator, draws: int = DRAWS) -> np.ndarray:
    """Redrawn first crossing minus the recorded one, `draws` times, for one utility.

    other_mw   the utility's load by year from every site that is not permit-dated
    sites      its permit-dated sites: mw_full, energized_year, size (a key of `errors`)
    """
    if not len(sites):
        return np.zeros(draws, dtype=int)
    mw, start = sites.mw_full.values.astype(float), sites.energized_year.values.astype(float)
    err = np.column_stack([rng.choice(errors[c], size=draws) for c in sites["size"]])        # draws x sites
    true_start = start[None, :] - err                                                         # recorded minus (recorded minus true)
    age = years[None, None, :] - true_start[:, :, None]                                       # draws x sites x years
    load = (mw[None, :, None] * np.clip((age + 1) / RAMP_YEARS, 0.0, 1.0) * (age >= 0)).sum(1) + other_mw[None, :]
    over = load * 8.76 >= theta * base_gwh
    first = np.where(over.any(1), years[over.argmax(1)], recorded + NEVER)
    return (first - recorded).astype(int)


def host_errors(theta: float, seed: int = SEED, draws: int = DRAWS) -> dict:
    """{(utility, state): array of date errors} for every cohort utility at this threshold."""
    q = panel.load_quantities()
    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    fac = pd.read_parquet(INTERIM / "facilities.parquet")
    fy = pd.read_parquet(INTERIM / "facility_year.parquet")
    fy = fy[~fy.crypto]
    report = json.loads((FROZEN / "dating_report.json").read_text())["permit_dating_error"]
    errors = {k: np.array(v, dtype=float) for k, v in report["errors_in_years_by_generator_based_size_mw"].items()}
    history = ps.history_settled(theta)
    treated, _ = ps.design(q, dose, theta, history)
    years = np.arange(int(fy.year.min()), int(fy.year.max()) + 1)
    base = dose.drop_duplicates(KEY).set_index(KEY).base_retail_gwh
    permit = fac[fac.in_dose & ~fac.is_crypto & (fac.date_basis == "first_generator_permit_plus_lag")].copy()
    permit["size"] = [size_class(k) for k in permit.generator_kw]
    rng = np.random.default_rng(seed)
    out = {}
    for r in treated.sort_values(KEY).itertuples():
        k = (int(r.utility_id_eia), r.state)
        if k in history:
            out[k] = np.zeros(draws, dtype=int)
            continue
        mine = permit[(permit.utility_id_eia == k[0]) & (permit.state == k[1])]
        rest = fy[(fy.utility_id_eia == k[0]) & (fy.state == k[1]) & ~fy.fid.isin(mine.fid)]
        other = rest.groupby("year").mw.sum().reindex(years).fillna(0.0).values
        out[k] = crossing_errors(int(r.cohort), other, mine, float(base[k]), theta, errors, years, rng, draws)
    return out


def describe(e: np.ndarray) -> dict:
    never = e >= NEVER - 30
    return {"exact": round(float((e == 0).mean()), 3), "within_1_year": round(float((np.abs(e) <= 1).mean()), 3),
            "true_crossing_2_or_more_years_earlier": round(float((e <= -2).mean()), 3),
            "true_crossing_5_or_more_years_earlier": round(float((e <= -5).mean()), 3),
            "true_crossing_2_or_more_years_later": round(float(((e >= 2) & ~never).mean()), 3),
            "never_reaches_the_threshold": round(float(never.mean()), 3)}


def main() -> int:
    q = panel.load_quantities()
    names = q.groupby(KEY).utility_name.last()
    report = {"what_this_is": "For each cohort utility, the first-crossing year recomputed with its permit-dated sites' start years "
                              "redrawn from the measured permit-dating errors, minus the recorded first crossing. Negative: the "
                              "utility really crossed earlier than recorded.",
              "draws_per_utility": DRAWS, "seed": SEED, "thresholds": {}}
    for theta in (0.02, 0.05):
        errs = host_errors(theta)
        aside = ps.set_aside(theta)
        hosts = {f"{k[0]}:{k[1]}": {"name": names.get(k), "in_headline_set": k not in aside, **describe(e)} for k, e in errs.items()}
        pool = lambda keep: np.concatenate([e for k, e in errs.items() if keep(k)]) if any(keep(k) for k in errs) else np.zeros(1)  # noqa: E731
        report["thresholds"][f"{theta:.0%}"] = {
            ps.HEADLINE_SET: {"hosts": int(sum(k not in aside for k in errs)), **describe(pool(lambda k: k not in aside))},
            "set_aside_cohort_utilities": {"hosts": int(sum(k in aside for k in errs)), **describe(pool(lambda k: k in aside))},
            "every_cohort_utility": {"hosts": len(errs), **describe(pool(lambda k: True))},
            "by_utility": hosts}
    (FROZEN / "misdating.json").write_text(json.dumps(report, indent=2) + "\n")
    for t, v in report["thresholds"].items():
        print(t, {k: v[k] for k in (ps.HEADLINE_SET, "set_aside_cohort_utilities", "every_cohort_utility")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
