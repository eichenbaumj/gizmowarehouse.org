"""Weights on the design: the net figure, and what the fuel-mix cells do to a host (D-55, D-57). Synthetic data only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import design, inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
FUEL = {"AA": 0, "AB": 0, "BB": 1, "BC": 1}        # two states a group, so the degree-day controls are identified


def frames(host_states: list[str], comparison_states: list[str], cohort: int = 2015):
    """Hosts and never-host utilities in one region, with sizes that put every comparison within reach of every host."""
    hosts = [(1 + i, st) for i, st in enumerate(host_states)]
    units = hosts + [(10 + i, st) for i, st in enumerate(comparison_states)]
    q = pd.DataFrame([(u, st, y, "cooperative", 10_000 + 100 * u, 1.0, True) for u, st in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    regions = pd.DataFrame([(u, st, y, "West") for u, st in units for y in YEARS], columns=KEY + ["year", "region"])
    rng = np.random.default_rng(3)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in FUEL for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    treated = pd.DataFrame({"utility_id_eia": [u for u, _ in hosts], "state": [st for _, st in hosts], "cohort": [cohort] * len(hosts)})
    clean = pd.DataFrame(units[len(hosts):], columns=KEY)
    return treated, clean, q, regions, dd


# These tests are about D-57's categorical cells, which from step D are the labelled sensitivity, not the default
# (D-59 item 7): each names the categorical control explicitly.
CAT = ps.CATEGORICAL


def headline_weights(d) -> tuple[pd.Series, pd.DataFrame]:
    wt = ic.implied_weights(d, CAT)
    head = wt[wt.event_year.isin(ps.HEADLINE)]
    return head[head.is_host].groupby("utility").weight.sum(), head[~head.is_host]


def test_a_host_alone_in_its_cohorts_fuel_mix_group_carries_no_weight():
    # Cheyenne Light in the 26-host set (D-57): every one of its matches is in another fuel-mix group, so the
    # cohort-by-group-by-year effects fit its ten rows exactly. A second host, with matches in its own group, carries the estimate.
    treated, clean, q, regions, dd = frames(["AA", "BB"], ["BB", "BC"] * 6)
    d = design.build(treated, clean, q, regions, FUEL, dd)
    cells = ic.fuel_mix_cells(d).set_index("utility")
    assert cells.other_rows_in_its_cohort_and_fuel_mix_group[(1, "AA")] == 0
    wt = ic.implied_weights(d, CAT)
    assert np.abs(wt[wt.is_host & (wt.utility == (1, "AA"))].weight).max() < 1e-9          # zero in every year of its window
    host, _ = headline_weights(d)
    assert abs(host[(2, "BB")] - 1.0) < 1e-9
    report = ic.weights_report(wt, pd.Series({(1, "AA"): "Alone", (2, "BB"): "Other"}), cells.reset_index())
    assert report["hosts_whose_weight_is_zero"] == ["Alone"] and report["fuel_mix_cells"]["hosts_alone_in_their_cell"] == ["Alone"]
    assert report["effective_number_of_hosts"] == 1.0


def test_a_host_with_one_match_in_its_fuel_mix_group_is_compared_with_that_one():
    # Arizona Public Service and El Paso Electric on the headline set (D-57).
    treated, clean, q, regions, dd = frames(["AA"], ["BB", "BC"] * 4 + ["BB", "AB"])
    d = design.build(treated, clean, q, regions, FUEL, dd)
    cells = ic.fuel_mix_cells(d).iloc[0]
    assert cells.other_rows_in_its_cohort_and_fuel_mix_group == 1 and cells.its_own_matches_in_that_group == [(19, "AB")]
    host, comp = headline_weights(d)
    comp = comp.groupby("utility").weight.sum()
    assert abs(host[(1, "AA")] - 1.0) < 1e-9
    assert abs(comp[(19, "AB")] + 1.0) < 1e-6                       # the one same-group match carries all of it
    assert np.abs(comp.drop((19, "AB"))).max() < 0.01               # the other nine carry next to nothing (what is left comes through the degree-day controls)


def test_with_every_match_in_the_hosts_group_the_ten_share_the_weight():
    treated, clean, q, regions, dd = frames(["AA"], ["AA", "AB"] * 6)
    d = design.build(treated, clean, q, regions, FUEL, dd)
    host, comp = headline_weights(d)
    comp = comp.groupby("utility").weight.sum()
    assert abs(host[(1, "AA")] - 1.0) < 1e-9 and len(comp) == 10 and np.allclose(comp.values, -0.1, atol=0.005)


def test_net_weight_adds_signed_copies_of_a_utility_year_before_taking_magnitudes():
    # One comparison utility matched to two hosts of the same cohort: its 2017 rows offset, its 2018 rows add.
    wt = pd.DataFrame([
        {"block_host": (1, "AA"), "cohort": 2015, "utility": (9, "BB"), "is_host": False, "event_year": 2, "weight": 0.25},
        {"block_host": (2, "AA"), "cohort": 2015, "utility": (9, "BB"), "is_host": False, "event_year": 2, "weight": -0.25},
        {"block_host": (1, "AA"), "cohort": 2015, "utility": (9, "BB"), "is_host": False, "event_year": 3, "weight": -0.10},
        {"block_host": (2, "AA"), "cohort": 2015, "utility": (9, "BB"), "is_host": False, "event_year": 3, "weight": -0.20},
        # the same calendar year reached from another cohort's stack is the same observed outcome
        {"block_host": (3, "AA"), "cohort": 2016, "utility": (9, "BB"), "is_host": False, "event_year": 2, "weight": 0.30},
        {"block_host": (1, "AA"), "cohort": 2015, "utility": (1, "AA"), "is_host": True, "event_year": 2, "weight": 0.5},
    ])
    n = ic.net_weights(wt).loc[[(9, "BB")]].iloc[0]
    assert abs(n.sum_of_absolute_row_weights - 1.10) < 1e-12
    assert abs(n.net_weight - 0.0) < 1e-12                           # 2017: +0.25 - 0.25; 2018: -0.10 - 0.20 + 0.30
    assert n.hosts_matched_to == 3
    wt.loc[4, "weight"] = 0.0
    assert abs(ic.net_weights(wt).loc[[(9, "BB")]].iloc[0].net_weight - 0.30) < 1e-12


def test_the_frozen_weights_give_the_net_figures_of_d55():
    """El Paso Electric 0.339, PacifiCorp in Wyoming 0.117, NorthWestern in Montana 0.108 on the headline set as frozen on 2026-11-14."""
    path = Path(__file__).resolve().parents[1] / "data" / "frozen" / "design_weights.csv"
    wt = pd.read_csv(path)
    wt = wt[wt.set == ps.HEADLINE_SET]
    if not {"5701:TX", "14354:WY", "12825:MT"} <= set(wt.utility):       # the design has been rebuilt since; D-55's figures are history
        return
    n = ic.net_weights(wt)
    assert n.index[0] == "5701:TX"
    assert [round(float(n.net_weight[k]), 3) for k in ("5701:TX", "14354:WY", "12825:MT")] == [0.339, 0.117, 0.108]
    assert round(float(n.sum_of_absolute_row_weights["5701:TX"]), 4) == 0.4786


def test_a_design_in_which_every_host_is_absorbed_fails_in_words():
    # The one-host case of D-57: before the rank check this returned weights of order 1e14 (D-59, item 7).
    import pytest
    from pipeline.analysis import estimator
    treated, clean, q, regions, dd = frames(["AA"], ["BB", "BC"] * 6)
    d = design.build(treated, clean, q, regions, FUEL, dd)
    with pytest.raises(estimator.RankDeficient):
        ic.implied_weights(d, CAT)
