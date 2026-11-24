"""Treatment-history bounds (docs/DECISIONS.md, D-44 and D-45). Load and sales only; no price is read."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import build_inventory as bi  # noqa: E402
from pipeline.facilities import buildout  # noqa: E402
from pipeline.facilities import treatment_bounds as tb  # noqa: E402

YEARS = tb.YEARS
UNITS = pd.MultiIndex.from_tuples([(1, "AA"), (2, "AA"), (3, "BB")], names=tb.KEY)


def frame(values: dict) -> pd.DataFrame:
    """A utility-by-year table that is `default` everywhere except the years named."""
    out = pd.DataFrame(0.0, index=UNITS, columns=YEARS)
    for k, by_year in values.items():
        for y, v in by_year.items():
            out.loc[k, y] = v
    return out


# ---- the tolerance ---------------------------------------------------------------

def test_same_place_is_the_same_group_and_a_cohort_year_within_one():
    assert tb.same_place(2015, 2016) and tb.same_place(2015, 2014)
    assert not tb.same_place(2015, 2017)                 # two years is a move
    assert not tb.same_place(2011, 2010)                 # one year, but it leaves the cohorts
    assert tb.same_place(2005, 2001)                     # early hosts are not dated
    assert not tb.same_place(2020, np.nan) and tb.same_place(np.nan, None)
    assert tb.group(2010) == "early" and tb.group(2011) == "cohort" and tb.group(2022) == "cohort" and tb.group(2023) == "late"


def test_first_crossing_and_largest_share():
    base = pd.Series([1000.0, 1000.0, np.nan], index=UNITS)
    gwh = frame({(1, "AA"): {2014: 19.0, 2015: 20.0, 2016: 60.0}, (3, "BB"): {2012: 500.0}})
    first = tb.first_crossing(gwh, base, 0.02)
    assert first[(1, "AA")] == 2015 and np.isnan(first[(2, "AA")])
    assert np.isnan(first[(3, "BB")])                    # load but no base: no crossing can be dated
    share = tb.max_share(gwh, base)
    assert share[(1, "AA")] == pytest.approx(0.06) and share[(2, "AA")] == 0.0 and np.isnan(share[(3, "BB")])


# ---- reading C: the remainder left unassigned ------------------------------------------

def test_hidden_load_is_capped_by_the_remainder_and_by_the_utilitys_own_sales():
    a = frame({(1, "AA"): {y: 10.0 for y in YEARS}})
    nonres = frame({(1, "AA"): {y: 40.0 for y in YEARS}, (2, "AA"): {y: 500.0 for y in YEARS}, (3, "BB"): {y: 500.0 for y in YEARS}})
    rem = pd.Series([100.0, 100.0, 0.0], index=UNITS)
    c = tb.ceiling(a, nonres, rem)
    assert c.loc[(1, "AA"), 2010] == pytest.approx(40.0)          # its sales less its own load leave room for 30 of the 100
    assert c.loc[(2, "AA"), 2010] == pytest.approx(100.0)         # room for all of it: each utility is bounded on its own
    assert (c.loc[(3, "BB")] == 0.0).all()                        # no remainder in its state, nothing hidden
    assert c.sum().sum() > rem.sum()                              # the bounds are not added up across utilities


def test_the_2024_remainder_does_not_bound_2025():
    a = frame({})
    nonres = frame({(2, "AA"): {**{y: 500.0 for y in YEARS}, 2025: 560.0}})
    c = tb.ceiling(a, nonres, pd.Series([100.0, 100.0, 0.0], index=UNITS))
    assert c.loc[(2, "AA"), 2024] == pytest.approx(100.0)
    assert c.loc[(2, "AA"), 2025] == pytest.approx(160.0)         # the remainder plus the utility's growth in sales since 2024


def test_a_year_with_no_sales_reported_is_bounded_by_the_remainder_alone():
    nonres = frame({(1, "AA"): {y: 40.0 for y in YEARS}})
    nonres.loc[(1, "AA"), 2021] = np.nan
    c = tb.ceiling(frame({}), nonres, pd.Series([100.0, 100.0, 0.0], index=UNITS))
    assert c.loc[(1, "AA"), 2020] == pytest.approx(40.0) and c.loc[(1, "AA"), 2021] == pytest.approx(100.0)


def test_no_site_is_raised_reading_c_never_falls_below_reading_a():
    a = frame({(1, "AA"): {y: 10.0 + y - 2001 for y in YEARS}})
    nonres = frame({(1, "AA"): {y: 5.0 for y in YEARS}})           # the inventory already exceeds its sales: no room, and no cut
    c = tb.ceiling(a, nonres, pd.Series([100.0, 100.0, 0.0], index=UNITS))
    assert (c.loc[(1, "AA")] == a.loc[(1, "AA")]).all()


def test_largest_rise_looks_only_forward_in_time():
    nonres = frame({(1, "AA"): {y: 100.0 for y in YEARS}, (2, "AA"): {y: 100.0 for y in YEARS}})
    nonres.loc[(1, "AA"), 2010] = 60.0
    nonres.loc[(1, "AA"), 2020] = 130.0                             # up 70 from the 2010 low
    nonres.loc[(2, "AA"), 2005] = 180.0                             # a fall afterwards is not a rise
    r = tb.largest_rise(nonres)
    assert r[(1, "AA")] == pytest.approx(70.0) and r[(2, "AA")] == pytest.approx(80.0)


def test_state_kinds():
    anchor = pd.DataFrame({"state": ["TX", "NM", "VA"], "epri_twh": [33.5, 0.98, 33.9], "epoch_twh": [6.7, 1.14, 5.4],
                           "permit_twh": [6.4, 0.002, 68.9], "raw_factor": [4.2, 0.0, 0.41], "factor": [3.0, 0.2, 0.41],
                           "flag": ["undercounted", "overcounted", "ok"]})
    s = tb.state_remainders(anchor)
    assert s.loc["TX", "kind"] == "falls_short" and s.loc["TX", "remainder_twh"] == pytest.approx(20.4) and s.loc["TX", "at_the_cap"]
    assert s.loc["NM", "kind"] == "measured_load_at_or_above_the_total" and s.loc["NM", "remainder_twh"] == 0.0
    assert s.loc["VA", "kind"] == "estimates_scaled_down" and not s.loc["VA", "at_the_cap"]


# ---- who keeps their place (D-46, rulings 1 and 2) -------------------------------------------

def row(**kw):
    base = {"state_kind": "falls_short", "state_remainder_gwh": 500.0, "clean_b": False, "max_share_a": 0.03, "max_share_c": 0.2,
            "b_2%": 2015.0, "a_2%": 2015.0, "c_earliest_2%": 2015.0, "c_latest_2%": 2015.0, "settled_by_its_own_count_2%": None}
    return {**base, **kw}


def test_a_cohort_host_keeps_its_place_if_the_built_and_unanchored_inventories_agree():
    assert tb.keeps_its_place(row(), "2%") == ("cohort", "keeps its place")
    assert tb.keeps_its_place(row(**{"a_2%": 2016.0}), "2%")[1] == "keeps its place"            # one year is inside the tolerance
    assert "no anchoring" in tb.keeps_its_place(row(**{"a_2%": 2018.0, "c_latest_2%": 2018.0}), "2%")[1]
    assert "never" in tb.keeps_its_place(row(**{"a_2%": np.nan, "c_latest_2%": np.nan}), "2%")[1]


def test_the_unassigned_remainder_is_reported_and_no_longer_decides():
    r = row(**{"c_earliest_2%": 2001.0})
    assert tb.keeps_its_place(r, "2%") == ("cohort", "keeps its place")                          # D-44 as first written took this host out
    assert "as early as 2001" in tb.with_the_remainder_unassigned(r, "2%")
    assert tb.with_the_remainder_unassigned(row(), "2%") == "holds"
    assert tb.with_the_remainder_unassigned(row(state_remainder_gwh=0.0), "2%") == "the state has no remainder"
    clean = {"b_2%": np.nan, "a_2%": np.nan, "c_earliest_2%": np.nan, "c_latest_2%": np.nan, "clean_b": True}
    assert tb.keeps_its_place(row(**clean, max_share_a=0.001, max_share_c=0.3), "2%") == ("comparison", "keeps its place")
    assert "remainder" in tb.with_the_remainder_unassigned(row(**clean, max_share_a=0.001, max_share_c=0.3), "2%")
    assert "remainder" in tb.with_the_remainder_unassigned(row(**clean, max_share_a=0.0, max_share_c=np.inf), "2%")   # no base to divide by


def test_an_early_host_keeps_its_place_if_no_anchoring_keeps_it_before_2011():
    assert tb.keeps_its_place(row(**{"b_2%": 2008.0, "a_2%": 2009.0, "c_earliest_2%": 2001.0, "c_latest_2%": 2009.0}), "2%") == ("early", "keeps its place")
    assert "not before 2011" in tb.keeps_its_place(row(**{"b_2%": 2008.0, "a_2%": 2014.0, "c_latest_2%": 2014.0}), "2%")[1]


def test_a_comparison_utility_has_to_stay_under_half_a_percent_with_no_anchoring():
    clean = {"b_2%": np.nan, "a_2%": np.nan, "c_earliest_2%": np.nan, "c_latest_2%": np.nan, "clean_b": True}
    assert tb.keeps_its_place(row(**clean, max_share_a=0.001, max_share_c=0.004), "2%") == ("comparison", "keeps its place")
    assert "no anchoring" in tb.keeps_its_place(row(**clean, max_share_a=0.007, max_share_c=0.007), "2%")[1]


def test_a_state_whose_estimates_are_scaled_down_gets_the_same_test():
    # Ruling 2: Salt River Project's case, 2009 with no anchoring against 2016 as built.
    r = row(state_kind="estimates_scaled_down", state_remainder_gwh=0.0, **{"b_2%": 2016.0, "a_2%": 2009.0})
    assert "2009 against 2016" in tb.keeps_its_place(r, "2%")[1]
    assert tb.keeps_its_place(row(state_kind="estimates_scaled_down", state_remainder_gwh=0.0), "2%")[1] == "keeps its place"
    clean = {"b_2%": np.nan, "a_2%": np.nan, "clean_b": True}
    assert "no anchoring" in tb.keeps_its_place(row(state_kind="estimates_scaled_down", **clean, max_share_a=0.006), "2%")[1]


def test_a_utility_settled_by_its_own_count_is_judged_on_that():
    r = row(**{"settled_by_its_own_count_2%": "outside", "a_2%": 2001.0})
    assert tb.keeps_its_place(r, "2%")[1].startswith("keeps its place")


# ---- the histories changed one at a time ----------------------------------------------

def test_a_step_that_fills_over_five_years_is_never_ahead_of_one_that_fills_over_three():
    phases = [(2012, 0.4), (2016, 1.0)]
    for y in range(2010, 2026):
        assert tb.phased_mw(100.0, phases, y, 5) <= buildout.phased_mw(100.0, phases, y) + 1e-9
    assert tb.phased_mw(100.0, phases, 2012, 3) == pytest.approx(buildout.phased_mw(100.0, phases, 2012))
    assert tb.phased_mw(100.0, phases, 2025, 5) == pytest.approx(100.0)


def test_swap_replaces_only_the_named_sites():
    fy = pd.DataFrame({"fid": ["a", "a", "b"], "utility_id_eia": [1, 1, 1], "state": ["AA"] * 3, "year": [2010, 2011, 2010], "mw": [5.0, 6.0, 7.0]})
    where = fy.drop_duplicates("fid").set_index("fid")[tb.KEY]
    out = tb.swap(fy, where, {"a": {2010: 0.0, 2011: 1.0, 2012: 2.0}})
    assert sorted(out[out.fid == "a"].mw) == [1.0, 2.0] and list(out[out.fid == "b"].mw) == [7.0]


# ---- Epoch rows already running before Epoch's first entry (T3) ---------------------------

def test_the_working_line_runs_from_the_sourced_start_to_the_first_entry():
    assert buildout.gap_mw(60.0, 2021, 2023, 2020) == 0.0
    assert buildout.gap_mw(60.0, 2021, 2023, 2021) == pytest.approx(20.0)
    assert buildout.gap_mw(60.0, 2021, 2023, 2022) == pytest.approx(40.0)
    assert buildout.gap_mw(60.0, 2021, 2023, 2023) == 0.0            # from the first entry on, Epoch's own series is used


def test_an_epoch_row_with_a_sourced_start_before_its_first_entry_carries_the_line_and_then_epochs_figures():
    path = {("Old Campus", 2024): 60.0, ("Old Campus", 2025): 90.0, ("New Campus", 2025): 50.0}
    fac = pd.DataFrame({"fid": ["epoch:Old Campus", "epoch:New Campus", "epoch:Reported"], "src": ["epoch"] * 3,
                        "date_basis": ["verified_public_source", "epoch_timeline", "verified_public_source"],
                        "energized_year": [2021.0, 2025.0, 2015.0]})
    gaps = bi.epoch_gaps(fac, {**path, ("Reported", 2024): 10.0}, skip={"epoch:Reported"})
    assert gaps == {"epoch:Old Campus": (2021, 2024, 60.0)}           # a row its operator reports on is governed by the report
    mw = lambda y: bi.site_mw("epoch", "epoch:Old Campus", 2021.0, 90.0, y, path, gaps=gaps)  # noqa: E731
    assert mw(2020) == 0.0 and mw(2021) == pytest.approx(15.0) and mw(2023) == pytest.approx(45.0)
    assert mw(2024) == 60.0 and mw(2025) == 90.0
    assert bi.site_mw("epoch", "epoch:Old Campus", 2021.0, 90.0, 2022, path) == 0.0   # without the line: nothing, as before


def test_the_assumed_line_is_left_out_of_the_state_anchoring():
    path = {("Old Campus", 2026): 100.0}
    fac = pd.DataFrame({"fid": ["epoch:Old Campus", "bi:1-0"], "src": ["epoch", "bi"], "state": ["XX", "XX"],
                        "energized_year": [2019.0, 2015.0], "mw_full": [100.0, 50.0]})
    t = bi.state_anchor(fac, fac.src == "epoch", pd.Series({"XX": 1.0}), path)
    assert t.loc["XX", "epoch_twh"] == 0.0                            # Epoch shows nothing for 2024, so nothing counts as measured


# ---- the frozen report --------------------------------------------------------------------

REPORT = ROOT / "data" / "frozen" / "treatment_bounds.json"
TABLE = ROOT / "data" / "frozen" / "treatment_bounds_by_utility.csv"


HEADLINE = ROOT / "data" / "frozen" / "headline_set.csv"


def d46_no_anchoring_violations(table: pd.DataFrame) -> list:
    """Early hosts in a state whose estimates are scaled down that fail, or are set aside, on D-46's no-anchoring
    reason. D-46 says there can be none: more load cannot move a first crossing later."""
    out = []
    for t in ("2%", "5%"):
        e = table[(table[f"place_{t}"] == "early") & (table.state_kind == "estimates_scaled_down")]
        for _, r in e.iterrows():
            verdict, lost = str(r[f"t1_{t}"]), str(r.get(f"lost_{t}", "") if pd.notna(r.get(f"lost_{t}", "")) else "")
            if verdict.startswith("no anchoring") or "D-46: no anchoring" in lost:
                out.append(f"{int(r.utility_id_eia)}:{r.state} at {t}")
    return out


def test_the_d46_claim_check_fails_on_an_early_host_with_the_no_anchoring_reason():
    ok = pd.DataFrame({"utility_id_eia": [1, 2], "state": ["AA", "BB"], "state_kind": ["estimates_scaled_down"] * 2,
                       "place_2%": ["early", "early"], "t1_2%": ["keeps its place"] * 2, "lost_2%": ["", "Step D: unsettled: x"],
                       "place_5%": ["early", "early"], "t1_5%": ["keeps its place"] * 2, "lost_5%": ["", ""]})
    assert d46_no_anchoring_violations(ok) == []                        # a step D reason is not a D-46 violation
    bad = ok.copy()
    bad.loc[0, "t1_2%"] = "no anchoring puts the first crossing at 2012, not before 2011"
    bad.loc[1, "lost_5%"] = "D-46: no anchoring puts the first crossing at 2012, not before 2011"
    assert d46_no_anchoring_violations(bad) == ["1:AA at 2%", "2:BB at 5%"]
    other = bad.assign(state_kind="falls_short")                       # outside scaled-down states the claim says nothing
    assert d46_no_anchoring_violations(other) == []


@pytest.mark.skipif(not (REPORT.exists() and TABLE.exists()), reason="treatment_bounds.py has not been run")
def test_the_frozen_report_hangs_together():
    r = json.loads(REPORT.read_text())
    for t, th in r["thresholds"].items():
        for name, s in th["sets"].items():
            unsettled = s["unsettled_on_assignment_list"]
            assert s["after"] == len(s["left"]) and s["unsettled_on_assignment"] == len(unsettled)
            assert s["before"] == len(s["left"]) + len(unsettled) + len(s["lost"])
            assert s["keep_their_place_between_the_built_and_unanchored_inventories"] == s["after"] + s["unsettled_on_assignment"]
            assert all(x["why"] for x in s["lost"]) and all(x["why"].startswith("D-46, ruling 4") for x in unsettled)
        head, ten, wide = th["sets"]["headline_set"], th["sets"]["set_with_the_ten_year_case"], th["sets"]["every_cohort_utility"]
        ids = lambda s: {x["utility"] for x in s["left"]}  # noqa: E731
        assert ids(ten) <= ids(head) <= ids(wide)                         # the ten-year case only ever takes hosts out
        lists = th["lists"]
        assert not ids(head) & (set(lists["does_not_keep_its_place"]) | set(lists["unsettled_on_assignment_under_ruling_4"]))
        c = th["comparison_utilities"]
        assert c["keep_their_place_between_the_built_and_unanchored_inventories"] == c["under_0.5pct_as_built_and_not_set_aside"] - len(c["do_not"])
        assert c["keep_their_place"] == c["keep_their_place_between_the_built_and_unanchored_inventories"] - c["fail_the_upper_case_of_ruling_4"]
        assert sum(c["by_region_keep_their_place"].values()) == c["keep_their_place"]
        # the remainder is reported, not a filter: fewer would hold with it unassigned than keep their place
        assert c["reported_not_a_filter_with_the_remainder_unassigned"]["of_those_that_keep_their_place_how_many_would_hold"] <= c["keep_their_place"]
        # D-46: in a state whose estimates are scaled down, taking the anchoring off raises every scaled site's load, and
        # more load cannot move a first crossing later, so an early host there never fails on no anchoring. Before step D
        # that was the only reason an early host could lose its place, so the count that keep it EQUALLED the count in
        # those states. From step D, timing.py's reasons (dated intervals, the crossed screen, unsettled references, the
        # ceiling, stress scenarios, unknown load) can also set an early host aside, so only the narrower claim can hold:
        # none fails on the D-46 no-anchoring reason (checked on the table below), and the count is at most the total.
        e = th["early_hosts"]
        assert e["of_which_keep_their_place"] <= e["in_states_whose_estimates_are_scaled_down"]
    assert d46_no_anchoring_violations(pd.read_csv(TABLE)) == []
    kinds = {v["kind"] for v in r["states"].values()}
    assert kinds <= {"falls_short", "measured_load_at_or_above_the_total", "estimates_scaled_down"}
    for v in r["states"].values():
        assert (v["remainder_twh"] > 0) == (v["kind"] == "falls_short")


@pytest.mark.skipif(not (REPORT.exists() and HEADLINE.exists()), reason="treatment_bounds.py has not been run")
def test_the_headline_list_the_report_and_set_aside_name_the_same_hosts():
    from pipeline.analysis import power_simulation as ps
    r = json.loads(REPORT.read_text())
    h = pd.read_csv(HEADLINE)
    for theta in tb.THRESHOLDS:
        t = f"{theta:.0%}"
        rows = h[h.threshold == t]
        listed = set(rows[rows.in_headline_set].utility_id_eia.astype(str) + ":" + rows[rows.in_headline_set].state)
        assert listed == {x["utility"] for x in r["thresholds"][t]["sets"]["headline_set"]["left"]}
        ten = set(rows[rows.in_set_with_the_ten_year_case].utility_id_eia.astype(str) + ":" + rows[rows.in_set_with_the_ten_year_case].state)
        assert ten == {x["utility"] for x in r["thresholds"][t]["sets"]["set_with_the_ten_year_case"]["left"]}
        aside, aside_ten = ps.set_aside(theta), ps.set_aside(theta, ten_year_case=True)
        cohort = set(zip(rows.utility_id_eia.astype(int), rows.state))
        assert {f"{u}:{s}" for u, s in cohort - aside} == listed and {f"{u}:{s}" for u, s in cohort - aside_ten} == ten
        assert (rows[~rows.in_headline_set].why_not_in_the_headline_set.fillna("") != "").all()   # everyone left out has a reason on file
        assert (rows[rows.in_headline_set].why_not_in_the_headline_set.fillna("") == "").all()


@pytest.mark.skipif(not TABLE.exists(), reason="treatment_bounds.py has not been run")
def test_in_the_frozen_table_reading_c_brackets_reading_a():
    t = pd.read_csv(TABLE)
    for th in ("2%", "5%"):
        both = t[t[f"a_{th}"].notna() & t[f"c_earliest_{th}"].notna()]
        assert (both[f"c_earliest_{th}"] <= both[f"a_{th}"]).all()      # hidden load can only bring a crossing forward
        assert t[f"c_latest_{th}"].equals(t[f"a_{th}"])                 # the latest possible crossing is with none of the remainder
    short = t[t.state_kind == "falls_short"]
    assert (short.state_remainder_gwh > 0).all() and (t[t.state_kind != "falls_short"].state_remainder_gwh == 0).all()
