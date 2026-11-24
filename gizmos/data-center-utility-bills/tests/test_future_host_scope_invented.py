"""The future-host criterion does not reach the headline design's comparison pool. Invented inputs only.

PREANALYSIS.md, Inference ("The future-host criterion does not reach the headline design", corrected 2026-11-19,
D-101): the criterion (D-29; D-86 list 1, item 11) says which utilities that first cross in 2023 or later may serve as
comparisons in the side run and in E2. The headline design's rule is stricter: a comparison utility is under 0.5% in
every panel year. So a utility the criterion would admit for some cohort is still in no headline pool, and building the
criterion can neither add a unit to that pool nor remove one.

These tests read no file under data/. The price hold is passed in as an empty set so that none is read.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import power_simulation as ps  # noqa: E402

YEARS = range(2001, 2026)
THETA = 0.02


def _dose(shares: dict) -> pd.DataFrame:
    """{(utility, state): {year: share}} as the dose frame design() reads; a year not named is zero."""
    rows = []
    for (u, st), by_year in shares.items():
        for y in YEARS:
            rows.append({"utility_id_eia": u, "state": st, "year": y, "dose": float(by_year.get(y, 0.0)),
                         "crypto_mw": 0.0, "base_retail_gwh": 1000.0})
    return pd.DataFrame(rows)


def _units(shares: dict) -> pd.DataFrame:
    return pd.DataFrame([{"utility_id_eia": u, "state": st, "year": y} for (u, st) in shares for y in YEARS])


def _admitted_by_the_criterion(by_year: dict, cohort: int) -> bool:
    """The plan's future-host rule in symbols: under 0.5% in every year through g+3, first crossing at g+7 or later."""
    crossing = min((y for y in YEARS if by_year.get(y, 0.0) >= THETA), default=None)
    if crossing is None or crossing < 2023:
        return False
    quiet = all(by_year.get(y, 0.0) < ps.CLEAN_BELOW for y in YEARS if y <= cohort + 3)
    return quiet and crossing >= cohort + 7


HOST = (1, "AA")            # crosses 2% in 2015: a cohort host
FUTURE = (2, "AA")          # nothing until 2023, then 3%: a future host
CLEAN = (3, "AA")           # 0.1% throughout: a comparison utility
CREEPING = (4, "AA")        # under 0.5% until 2025, then 0.6%: never a host at 2%, and not under 0.5% throughout
SHARES = {
    HOST: {y: 0.03 for y in YEARS if y >= 2015},
    FUTURE: {y: 0.03 for y in YEARS if y >= 2023},
    CLEAN: {y: 0.001 for y in YEARS},
    CREEPING: {**{y: 0.001 for y in YEARS}, 2025: 0.006},
}


def _design():
    treated, clean = ps.design(_units(SHARES), _dose(SHARES), THETA, history={}, hold=set())
    hosts = {(int(r.utility_id_eia), r.state): int(r.cohort) for r in treated.itertuples()}
    pool = {(int(u), st) for u, st in zip(clean.utility_id_eia, clean.state)}
    return hosts, pool


def test_the_headline_pool_is_under_half_a_percent_in_every_year():
    hosts, pool = _design()
    assert hosts == {HOST: 2015}
    assert pool == {CLEAN}
    assert CREEPING not in pool and CREEPING not in hosts          # one year at 0.6% is enough to leave the pool


def test_a_future_host_the_criterion_admits_is_still_in_no_headline_pool():
    hosts, pool = _design()
    admitted_for = [g for g in range(ps.COHORTS[0], ps.COHORTS[1] + 1) if _admitted_by_the_criterion(SHARES[FUTURE], g)]
    assert admitted_for == list(range(2011, 2017))                  # crossing 2023: cohorts through 2016
    assert FUTURE not in pool and FUTURE not in hosts               # a late host is on neither side of the headline design


def test_the_criterion_can_only_add_units_the_headline_rule_excludes():
    """Every unit the criterion admits for any cohort fails the headline rule, so the two sets never meet."""
    _, pool = _design()
    admitted = {k for k, by_year in SHARES.items()
                if any(_admitted_by_the_criterion(by_year, g) for g in range(ps.COHORTS[0], ps.COHORTS[1] + 1))}
    assert admitted == {FUTURE}
    assert admitted.isdisjoint(pool)
    assert all(max(SHARES[k].values()) >= THETA for k in admitted)  # each crosses 2%, so none is under 0.5% throughout
