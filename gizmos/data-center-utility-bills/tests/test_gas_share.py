"""The gas-share control (D-59 item 7, as specified there and in D-61 section 8). Invented quantities only.

The state's fixed 2008-2010 share times an indicator for each calendar year in the stacked sample; one slope per calendar
year shared across cohorts and matched sets; the first calendar year's column left out; the rest added in calendar order
after the fixed effects are removed, a column that is a linear combination of the fixed effects and the control columns
before it left out and listed with its year, judged with the event-time columns set aside; never a control removed to
rescue an event-time column.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, estimator, influence  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import COHORT, COOP, FUEL, ladder, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
K = len(ps.EVENT_TIMES)


def make(hosts, comps, region=None, cohort=COHORT, gas=GAS, k=ps.MATCH_K):
    treated, clean, q, regions, dd = world(hosts, comps, region=region, cohort=cohort)
    d = design.build(treated, clean, q, regions, FUEL, dd, k)
    d.gas = gas
    return d


def assembled(d, fuel_control=ps.GAS_SHARE):
    for w in d.windows.values():
        w.y = np.zeros((len(w.keys), ps.T))
    return ps.assemble(d.windows, d.blocks(), fuel_control=fuel_control, gas=d.gas)


def mixed(first_id, n, start=10_050):
    states = ["AA", "AB", "BB", "BC"]
    return [(first_id + i, states[i % 4], start + 100 * i, COOP) for i in range(n)]


def two_regions(key, year):
    return "East" if key[0] >= 100 else "West"


# ---- the columns ---------------------------------------------------------------------------------------

def test_one_column_per_calendar_year_less_the_first_each_the_share_times_that_year():
    d = make([(1, "AA", 10_000, COOP)], mixed(10, 12))
    a = assembled(d)
    years = list(range(COHORT - ps.PRE, COHORT + ps.POST + 1))
    assert a["columns"][:K] == [f"event_year_{e}" for e in ps.EVENT_TIMES]
    assert a["columns"][K:K + 2] == ["heating_degree_days", "cooling_degree_days"]
    assert a["columns"][K + 2:] == [f"gas_share_x_{y}" for y in years[1:]]
    assert a["control_columns_left_out"] == [{"year": years[0], "why": ps.FIRST_YEAR_LEFT_OUT}]
    assert len(a["groups"]) == 2                                       # no cohort-by-fuel-mix-group-by-year effects in the headline
    # the column for a year is the row's state's share in that year's rows and zero elsewhere
    w = d.windows[COHORT]
    blocks = d.blocks()
    states = np.concatenate([np.repeat(w.state_name[np.concatenate([tr, comp])], ps.T) for _, tr, comp in blocks])
    cal = np.concatenate([np.tile(np.arange(ps.T), len(tr) + len(comp)) + COHORT - ps.PRE for _, tr, comp in blocks])
    for j, y in enumerate(years[1:]):
        expect = np.array([GAS[s] for s in states]) * (cal == y)
        assert np.array_equal(a["X"][:, K + 2 + j], expect)


def test_one_slope_per_calendar_year_shared_across_cohorts():
    hosts = [(1, "AA", 10_000, COOP)]
    d1 = make(hosts, mixed(10, 12), cohort=2014)
    d2 = make(hosts, mixed(10, 12), cohort=2016)
    windows = {2014: d1.windows[2014], 2016: d2.windows[2016]}
    blocks = d1.blocks() + d2.blocks()
    for w in windows.values():
        w.y = np.zeros((len(w.keys), ps.T))
    a = ps.assemble(windows, blocks, gas=GAS)
    assert [c for c in a["columns"] if c.startswith("gas")] == [f"gas_share_x_{y}" for y in range(2009, 2020)]
    assert a["control_columns_left_out"][0]["year"] == 2008
    col = a["X"][:, a["columns"].index("gas_share_x_2012")]
    n1 = (1 + len(blocks[0][2])) * ps.T
    assert col[:n1].any() and col[n1:].any()                           # both cohorts' rows load on the one 2012 column


def test_a_state_with_no_share_stops_and_is_named():
    d = make([(1, "AA", 10_000, COOP)], mixed(10, 12), gas={"AA": 0.1, "AB": 0.3, "BB": 0.6})
    with pytest.raises(ValueError, match=r"no 2008-2010 gas share for states \['BC'\]"):
        assembled(d)
    d.gas = None
    with pytest.raises(ValueError, match="needs each state's 2008-2010 share"):
        assembled(d)


def test_the_labelled_variants_are_the_categorical_effects_and_no_fuel_control():
    d = make([(1, "AA", 10_000, COOP)], mixed(10, 12))
    cat, none = assembled(d, ps.CATEGORICAL), assembled(d, ps.NO_FUEL)
    assert len(cat["groups"]) == 3 and cat["X"].shape[1] == K + 2 and cat["control_columns_left_out"] == []
    assert len(none["groups"]) == 2 and none["X"].shape[1] == K + 2
    with pytest.raises(ValueError):
        assembled(d, "bins")


def test_the_frozen_file_gives_one_fixed_share_per_state(tmp_path):
    gas = ps.load_gas_share()
    assert len(gas) == 51 and all(np.isfinite(v) for v in gas.values())
    pd.DataFrame({"state": ["AA", "BB"], "gas_share_mean": [0.1, None]}).to_csv(tmp_path / "fuel_mix_groups.csv", index=False)
    with pytest.raises(ValueError, match="lacks a gas_share_mean"):
        ps.load_gas_share(tmp_path)


# ---- redundant columns -----------------------------------------------------------------------------------

def test_screen_leaves_out_a_combination_of_earlier_controls_and_lists_it():
    rng = np.random.default_rng(1)
    n = 60
    unit = np.repeat(np.arange(12), 5)
    proj = estimator.Projection([unit])
    dd = rng.normal(size=(n, 2))
    c = rng.normal(size=(n, 3))
    cand = np.column_stack([c[:, 0], c[:, 1], c[:, 0] - 2 * c[:, 1] + 0.5 * dd[:, 0], c[:, 2], (unit % 3) * 1.0])
    kept, dropped = ps.screen_controls(dd, cand, proj)
    assert kept == [0, 1, 3] and dropped == [2, 4]                      # 2: a combination before it; 4: absorbed by the unit effects


def test_a_redundant_degree_day_column_is_kept_for_the_fit_to_fail_and_does_not_poison_later_candidates():
    rng = np.random.default_rng(2)
    unit = np.repeat(np.arange(12), 5)
    proj = estimator.Projection([unit])
    hdd = rng.normal(size=60)
    dd = np.column_stack([hdd, (unit % 2) * 1.0])                      # the second degree-day column is absorbed
    cand = rng.normal(size=(60, 2))
    kept, dropped = ps.screen_controls(dd, cand, proj)
    assert kept == [0, 1] and dropped == []


def test_when_every_matched_utility_shares_the_hosts_state_every_gas_column_is_absorbed_and_listed():
    d = make([(1, "AA", 10_000, COOP)], ladder(10, 12, state="AA"))
    a = assembled(d)
    years = list(range(COHORT - ps.PRE, COHORT + ps.POST + 1))
    assert [x["year"] for x in a["control_columns_left_out"]] == years
    assert all(x["why"] == ps.REDUNDANT_LEFT_OUT for x in a["control_columns_left_out"][1:])
    assert a["X"].shape[1] == K + 2


def test_the_event_time_coefficients_do_not_depend_on_which_redundant_control_is_left_out():
    rng = np.random.default_rng(3)
    unit = np.repeat(np.arange(30), 6)
    t = np.tile(np.arange(6), 30)
    groups = [unit, t]
    ev = ((unit < 6) & (t >= 3)) * 1.0
    c1, c2 = rng.normal(size=180), rng.normal(size=180)
    c3 = c1 + c2
    y = 0.3 * ev + c1 - c2 + rng.normal(size=180) + rng.normal(size=30)[unit]
    drop3 = estimator.Fit(y, np.column_stack([ev, c1, c2]), groups, unit % 6)
    drop2 = estimator.Fit(y, np.column_stack([ev, c1, c3]), groups, unit % 6)
    assert drop3.coef()[0] == pytest.approx(drop2.coef()[0], abs=1e-10)


# ---- never rescue an event-time column -------------------------------------------------------------------

def test_a_host_whose_matches_all_have_one_other_share_fails_in_words_and_no_control_is_removed():
    # The host's share differs from every match's, and they all share one: each year's gas column is the cell effect plus
    # a multiple of the host's indicator, so the event-time columns are not identified with the controls in.
    d = make([(1, "AA", 10_000, COOP)], ladder(10, 12, state="BB"))
    a = assembled(d)
    # Judged with the event-time columns set aside, two gas columns are redundant: here the two degree-day columns also vary
    # only between the host's state and its matches' state, so they already take two of the nine directions the year
    # columns can take. Those two are left out and listed; the other seven stay although they leave the event-time
    # columns unidentified, and the fit fails in words.
    left = a["control_columns_left_out"]
    assert left[0]["why"] == ps.FIRST_YEAR_LEFT_OUT and [x["why"] for x in left[1:]] == [ps.REDUNDANT_LEFT_OUT] * 2
    assert a["X"].shape[1] == K + 2 + 7
    with pytest.raises(estimator.RankDeficient):
        estimator.Fit(np.random.default_rng(0).normal(size=len(a["y"])), a["X"], a["groups"], a["cluster"])
    with pytest.raises(estimator.RankDeficient):
        ic.implied_weights(d)
    assert ic.absorbed_hosts(d) == ["1:AA"]                            # named although the fit as a whole cannot be computed
    assert influence.estimable(d)["estimable"] is False
    rng = np.random.default_rng(5)
    draw = ps.one_draw(d.windows, d.blocks(), {}, rng, boot=19, gas=GAS)
    assert draw["exact"][0]["numerical_failure"] == estimator.RANK_DEFICIENT


def test_the_gas_share_columns_alone_can_leave_the_event_times_unidentified_and_every_column_enters_the_rank_test():
    # Matches in two states with one share between them: the degree days still vary among the matches, so without the
    # control the design is estimable; with it, each year's gas column is the cell effect plus a multiple of the host's
    # rows. influence.estimable must see the gas columns (it once sliced the regressors to a fixed width).
    gas = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.60}
    d = make([(1, "AA", 10_000, COOP)], [(10 + i, ["BB", "BC"][i % 2], 10_050 + 100 * i, COOP) for i in range(12)], gas=gas)
    assert influence.estimable(d, ps.NO_FUEL)["estimable"] is True
    assert influence.estimable(d)["estimable"] is False
    assert ic.absorbed_hosts(d) == ["1:AA"] and ic.absorbed_hosts(d, ps.NO_FUEL) == []
    a = assembled(d)
    assert [x["why"] for x in a["control_columns_left_out"]] == [ps.FIRST_YEAR_LEFT_OUT]   # no control removed to rescue them
    with pytest.raises(estimator.RankDeficient):
        estimator.Fit(np.zeros(len(a["y"])) + np.arange(len(a["y"])) % 7, a["X"], a["groups"], a["cluster"])


def test_a_fully_absorbed_host_is_named_when_the_fit_can_be_computed():
    # Host 1 (West, AA) is compared only with BB utilities; host 2 (East, BB) only with BB utilities, so the gas columns are
    # identified only through host 1's block, where they take up its rows. The fit is computed; host 1 carries nothing.
    west = ladder(10, 12, state="BB")
    east = ladder(110, 12, state="BB")
    d = make([(1, "AA", 10_000, COOP), (101, "BB", 10_000, COOP)], west + east, region=two_regions)
    wt = ic.implied_weights(d)
    head = wt[wt.is_host & wt.event_year.isin(ps.HEADLINE)].groupby("utility").weight.sum()
    assert abs(head[(1, "AA")]) < 1e-9 and head[(101, "BB")] == pytest.approx(1.0, abs=1e-9)
    assert ic.absorbed_hosts(d) == ["1:AA"]
    assert influence.estimable(d)["hosts_with_zero_weight"] == ["1:AA"]


def test_net_weights_are_after_all_controls_and_the_host_weights_sum_to_one():
    d = make([(1, "AA", 10_000, COOP), (101, "AB", 10_000, COOP)], mixed(10, 14) + mixed(110, 14), region=two_regions)
    wt = ic.implied_weights(d)
    head = wt[wt.is_host & wt.event_year.isin(ps.HEADLINE)].groupby("utility").weight.sum()
    assert head.sum() == pytest.approx(1.0, abs=1e-9)
    cat = ic.implied_weights(d, ps.CATEGORICAL)
    assert not np.allclose(wt.weight.values, cat.weight.values)          # the control changes the weights
    assert ic.absorbed_hosts(d) == []


# ---- each host's share against its matches ----------------------------------------------------------------

def test_each_hosts_share_is_shown_beside_its_matches_range_and_outside_is_named_extrapolation():
    d = make([(1, "AB", 10_000, COOP), (101, "AA", 10_000, COOP)],
             [(10 + i, ["AA", "BB"][i % 2], 10_050 + 100 * i, COOP) for i in range(12)]
             + [(110 + i, ["AB", "BC"][i % 2], 10_050 + 100 * i, COOP) for i in range(12)], region=two_regions)
    r = {x["utility"]: x for x in design.gas_share_ranges(d, GAS, pd.Series({(1, "AB"): "Inside Co"}))}
    assert r["1:AB"] == {"utility": "1:AB", "name": "Inside Co", "cohort": COHORT, "host_gas_share": 0.3,
                         "lowest_among_its_matches": 0.1, "highest_among_its_matches": 0.6,
                         "inside_its_matches_range": True, "extrapolation": False}
    assert r["101:AA"]["lowest_among_its_matches"] == 0.3 and r["101:AA"]["inside_its_matches_range"] is False
    assert r["101:AA"]["extrapolation"] is True
