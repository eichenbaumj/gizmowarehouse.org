"""The joint check (docs/DECISIONS.md, D-46 ruling 5 as amended). Load and sales only; no price is read.

The sort is held to a search over every subset on small made-up states, for both counts: the number
that could each fail somewhere in the period, and the number that could be at the level in the same year.
The search does not use the idea of a per-utility cost. It tries every way of giving each utility either
no hidden load or a breach in one particular year, builds the hidden-load paths that would take, and checks
them against the rule's own constraints: never negative, never shrinking, under each utility's sales bound
in every year, and summing to no more than the state's budget in the last year.
"""
import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import joint_check as jc  # noqa: E402

YEARS = [2020, 2021, 2022, 2023, 2024]


def state(rng, n, years=YEARS, tight=False):
    """A made-up state: (load, base, room) for n utilities. `tight` makes the sales bound bind often."""
    idx = pd.MultiIndex.from_tuples([(i + 1, "ZZ") for i in range(n)], names=jc.KEY)
    base = pd.Series(rng.uniform(200, 4000, n), index=idx)
    load = pd.DataFrame(rng.uniform(0, 0.004, (n, len(years))) * base.values[:, None], index=idx, columns=years)
    room = pd.DataFrame(rng.uniform(0.0005 if tight else 0.02, 0.02 if tight else 0.5, (n, len(years))) * base.values[:, None],
                        index=idx, columns=years)
    return load, base, room


def paths_feasible(choice, d, room, budget):
    """Is this assignment of breach years possible? choice[i] is a column index, or None for no hidden load."""
    n, T = d.shape
    h = np.zeros((n, T))
    for i, t in enumerate(choice):
        if t is not None:
            h[i, t:] = d[i, t]                    # the least a non-shrinking path can carry and still breach in t
    if (h > room + 1e-9).any():
        return False
    return h[:, -1].sum() <= budget + 1e-9


def brute_somewhere(d, room, budget):
    n, T = d.shape
    best = 0
    for choice in itertools.product([None] + list(range(T)), repeat=n):
        k = sum(c is not None for c in choice)
        if k > best and paths_feasible(choice, d, room, budget):
            best = k
    return best


def brute_same_year(d, room, budget):
    n, T = d.shape
    best = 0
    for t in range(T):
        for r in range(n, best, -1):
            if any(paths_feasible([t if i in s else None for i in range(n)], d, room, budget) for s in itertools.combinations(range(n), r)):
                best = r
                break
    return best


@pytest.mark.parametrize("seed", range(40))
def test_the_sort_matches_a_search_over_every_subset_for_both_counts(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(2, 6))
    load, base, room = state(rng, n, tight=bool(seed % 2))
    d = jc.deficits(load, base)
    ok = jc.fits(d, room)
    costs = jc.cost_somewhere(d, ok)
    finite = costs[np.isfinite(costs)]
    # budgets from nothing to everything, and several that fall between two utilities' costs
    budgets = [0.0, float(finite.sum()) + 1.0] + list(rng.uniform(0, float(finite.sum()) + 1.0, 4)) if len(finite) else [0.0, 5.0]
    for budget in budgets:
        assert jc.most(costs.values, budget) == brute_somewhere(d.values, room.values, budget)
        assert jc.same_year(d, ok, budget)[0] == brute_same_year(d.values, room.values, budget)


def test_hidden_load_has_to_fit_in_every_later_year_not_only_the_year_it_breaches():
    idx = pd.MultiIndex.from_tuples([(1, "ZZ")], names=jc.KEY)
    load = pd.DataFrame([[0.0, 0.0, 0.0]], index=idx, columns=[2022, 2023, 2024])
    base = pd.Series([1000.0], index=idx)                         # 0.5% is 5 GWh
    room = pd.DataFrame([[10.0, 10.0, 3.0]], index=idx, columns=[2022, 2023, 2024])
    d = jc.deficits(load, base)
    ok = jc.fits(d, room)
    assert not ok.values.any()                                     # 5 GWh fits in 2022 but could not still be there in 2024
    assert math.isinf(jc.cost_somewhere(d, ok).iloc[0])
    room.loc[(1, "ZZ"), 2024] = 6.0
    assert jc.fits(d, room).values.all()


def test_a_cheapest_year_is_used_and_the_two_counts_can_differ():
    idx = pd.MultiIndex.from_tuples([(1, "ZZ"), (2, "ZZ")], names=jc.KEY)
    base = pd.Series([1000.0, 1000.0], index=idx)                  # each needs 5 GWh less its own load
    load = pd.DataFrame([[4.0, 0.0, 0.0], [0.0, 0.0, 4.0]], index=idx, columns=[2022, 2023, 2024])
    room = pd.DataFrame(100.0, index=idx, columns=[2022, 2023, 2024])
    d = jc.deficits(load, base)
    ok = jc.fits(d, room)
    assert list(jc.cost_somewhere(d, ok)) == [1.0, 1.0]            # one is cheapest in 2022, the other in 2024
    assert jc.most(jc.cost_somewhere(d, ok).values, 2.0) == 2      # both could fail somewhere in the period on 2 GWh
    n, year, by_year = jc.same_year(d, ok, 2.0)
    assert n == 1 and by_year == {2022: 1, 2023: 0, 2024: 1}       # but never both in the same year


def test_a_year_with_no_sales_reported_bounds_nothing_and_no_base_means_no_figure():
    idx = pd.MultiIndex.from_tuples([(1, "ZZ"), (2, "ZZ")], names=jc.KEY)
    base = pd.Series([1000.0, np.nan], index=idx)
    load = pd.DataFrame(0.0, index=idx, columns=[2023, 2024])
    room = pd.DataFrame([[np.nan, 9.0], [50.0, 50.0]], index=idx, columns=[2023, 2024])
    d = jc.deficits(load, base)
    ok = jc.fits(d, room)
    assert ok.loc[(1, "ZZ")].all() and not ok.loc[(2, "ZZ")].any()
    assert math.isinf(jc.cost_somewhere(d, ok).loc[(2, "ZZ")])


def test_a_hosts_matches_are_counted_state_by_state_and_2025_is_left_out():
    idx = pd.MultiIndex.from_tuples([(1, "AA"), (2, "AA"), (3, "BB"), (4, "BB")], names=jc.KEY)
    years = list(range(2015, 2025))
    base = pd.Series([1000.0, 2000.0, 1000.0, 4000.0], index=idx)   # needs 5, 10, 5 and 20 GWh
    load = pd.DataFrame(0.0, index=idx, columns=years)
    room = pd.DataFrame(1000.0, index=idx, columns=years)
    d = jc.deficits(load, base)
    ok = jc.fits(d, room)
    r = jc.host_check(list(idx), list(range(2016, 2026)), d, ok, {"AA": 6.0, "BB": 100.0})
    assert r["partly_assessed_2025_left_out"] and r["years_assessed"] == [2016, 2024]
    assert r["could_fail_somewhere_in_its_window_within_the_remainders"] == 3       # one in AA (6 buys the 5), both in BB
    assert r["by_state"]["AA"]["hidden_gwh_to_reach_its_cheapest_1_2_3_and_so_on"] == [5.0, 15.0]
    tip = r["tipping_requirement_ignoring_the_remainders"]
    assert tip["5"]["total_gwh"] is None                                            # it has four matches
    # Budgets do not move between states: BB's 100 cannot buy AA's second utility.
    r2 = jc.host_check(list(idx), list(range(2016, 2025)), d, ok, {"AA": 6.0, "BB": 1000.0})
    assert r2["could_fail_somewhere_in_its_window_within_the_remainders"] == 3 and not r2["partly_assessed_2025_left_out"]


def test_the_tipping_requirement_ignores_the_remainders_and_says_when_they_would_not_allow_it():
    idx = pd.MultiIndex.from_tuples([(i, "AA" if i <= 6 else "BB") for i in range(1, 11)], names=jc.KEY)
    years = list(range(2010, 2020))
    base = pd.Series([200.0 * i for i in range(1, 11)], index=idx)                  # needs 1, 2, ..., 10 GWh
    d = jc.deficits(pd.DataFrame(0.0, index=idx, columns=years), base)
    ok = jc.fits(d, pd.DataFrame(1e6, index=idx, columns=years))
    r = jc.host_check(list(idx), years, d, ok, {"AA": 3.0, "BB": 0.0})
    tip = r["tipping_requirement_ignoring_the_remainders"]
    assert tip["5"]["total_gwh"] == 15.0 and tip["6"]["total_gwh"] == 21.0 and tip["10"]["total_gwh"] == 55.0
    assert tip["6"]["one_combination_by_state_gwh"] == {"AA": 21.0}
    assert r["could_fail_somewhere_in_its_window_within_the_remainders"] == 2      # 3 GWh buys the 1 and the 2
    assert tip["5"]["within_the_remainders"] == "not feasible"


def test_smallest_to_reach_and_most_are_inverse_readings():
    costs = [3.0, 1.0, math.inf, 2.0]
    assert jc.smallest_to_reach(costs, 2) == 3.0 and jc.most(costs, 3.0) == 2 and jc.most(costs, 2.999) == 1
    assert math.isinf(jc.smallest_to_reach(costs, 4))                               # one of the four cannot be reached at any price
