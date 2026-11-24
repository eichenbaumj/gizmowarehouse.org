"""Load histories: the slow-build alternative, verified phases, and the table's rules. Synthetic sites only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.facilities import buildout as bo  # noqa: E402
from pipeline.facilities import dating_sensitivity as ds  # noqa: E402


def table(rows):
    base = dict.fromkeys(bo.COLUMNS)
    return pd.DataFrame([{**base, "kind": "phases", "source_url": "https://example.org/release", "source_quote": "opened",
                          "confidence": "high", "checked_on": "2026-11-11", **r} for r in rows])


def test_ramp_reaches_full_load_in_the_third_year():
    assert [bo.ramp_mw(90.0, 2010, y) for y in (2009, 2010, 2011, 2012, 2020)] == pytest.approx([0, 30, 60, 90, 90])


def test_slow_path_reaches_full_load_the_year_after_the_latest_permit():
    # opened 2010, latest generator permit 2023: full in 2024, one fifteenth of the load a year
    assert bo.slow_end_year(2010, 2023) == 2024
    assert bo.slow_mw(150.0, 2010, 2023, 2010) == pytest.approx(10.0)
    assert bo.slow_mw(150.0, 2010, 2023, 2017) == pytest.approx(80.0)
    assert bo.slow_mw(150.0, 2010, 2023, 2024) == pytest.approx(150.0)
    assert bo.slow_mw(150.0, 2010, 2023, 2009) == 0.0


def test_slow_path_is_never_faster_than_the_ramp_and_equals_it_without_later_permits():
    for latest in (np.nan, 2009, 2010, 2011):                  # no later permit: the two paths are the same
        assert [bo.slow_mw(90.0, 2010, latest, y) for y in range(2009, 2014)] == pytest.approx(
            [bo.ramp_mw(90.0, 2010, y) for y in range(2009, 2014)])
    for y in range(2005, 2026):
        assert bo.slow_mw(90.0, 2010, 2020, y) <= bo.ramp_mw(90.0, 2010, y) + 1e-12


def test_phases_each_ramp_like_a_new_site():
    phases = [(2010, 0.25), (2016, 1.0)]                       # a quarter of the campus in 2010, the rest from 2016
    assert bo.phased_mw(120.0, phases, 2009) == 0.0
    assert bo.phased_mw(120.0, phases, 2010) == pytest.approx(10.0)
    assert bo.phased_mw(120.0, phases, 2012) == pytest.approx(30.0)
    assert bo.phased_mw(120.0, phases, 2015) == pytest.approx(30.0)
    assert bo.phased_mw(120.0, phases, 2016) == pytest.approx(60.0)
    assert bo.phased_mw(120.0, phases, 2018) == pytest.approx(120.0)
    # one phase holding the whole site is the ordinary ramp
    assert bo.phased_mw(120.0, [(2010, 1.0)], 2011) == pytest.approx(bo.ramp_mw(120.0, 2010, 2011))


def test_the_inventory_uses_a_verified_history_and_leaves_epoch_sites_alone():
    from pipeline.facilities import build_inventory as bi
    phases = {"bi:1-0": [(2010, 0.25), (2016, 1.0)], "epoch:Big": [(2010, 0.5), (2012, 1.0)]}
    assert bi.site_mw("bi", "bi:1-0", 2010, 120.0, 2012, {}, phases) == pytest.approx(30.0)
    assert bi.site_mw("bi", "bi:1-0", 2010, 120.0, 2012, {}) == pytest.approx(120.0)        # no history: full by year three
    assert bi.site_mw("bi", "bi:2-0", 2010, 120.0, 2012, {}, phases) == pytest.approx(120.0)
    assert bi.site_mw("epoch", "epoch:Big", 2010, 500.0, 2012, {("Big", 2011): 40.0}, phases) == 40.0
    assert bi.RAMP_YEARS == bo.RAMP_YEARS and bi.PERMIT_LAG == bo.PERMIT_LAG


def test_material_means_a_change_of_group_or_a_cohort_year_moving_by_two():
    assert bo.material(2010, 2013)            # early host becomes a cohort utility
    assert bo.material(2021, 2023)            # cohort utility becomes a late host
    assert bo.material(2014, 2016)            # stays in the cohorts, two years later
    assert not bo.material(2014, 2015)
    assert not bo.material(2003, 2008)        # an early host either way
    assert bo.material(np.nan, 2015) and not bo.material(np.nan, np.nan)
    assert [bo.group(y) for y in (2010, 2011, 2022, 2023, np.nan)] == ["early", "cohort", "cohort", "late", "never"]


def test_first_crossings_and_paths_on_a_small_utility():
    """One utility with 1,000 GWh of base sales: 2% is 2.28 MW. A 6 MW site opened 2010 with permits to 2019."""
    fac = pd.DataFrame({"fid": ["bi:1-0"], "utility_id_eia": [5.0], "state": ["OH"], "energized_year": [2010.0],
                        "latest_permit_year": [2019.0], "mw_full": [6.0]})
    fy = pd.DataFrame(columns=["fid", "utility_id_eia", "state", "year", "mw"])
    base = pd.Series({(5, "OH"): 1000.0})
    years = list(range(2001, 2026))
    ramp = bo.first_crossings(bo.paths(fac, fy, years, {"bi:1-0": "ramp"}), base, 0.02)
    slow = bo.first_crossings(bo.paths(fac, fy, years, {"bi:1-0": "slow"}), base, 0.02)
    assert ramp[(5, "OH")] == 2011            # 4 MW in the second year
    assert slow[(5, "OH")] == 2014            # full in 2020, so 6/11 MW a year: 2.7 MW in the fifth year
    assert bo.material(ramp[(5, "OH")], slow[(5, "OH")])


@pytest.mark.parametrize("rows, message", [
    ([dict(fid="a", year=2010, cumulative_share=0.5, source_url=None), dict(fid="a", year=2012, cumulative_share=1.0)], "source"),
    ([dict(fid="a", year=2010, cumulative_share=0.5, source_url="https://www.baxtel.com/x"),
      dict(fid="a", year=2012, cumulative_share=1.0)], "source"),
    ([dict(fid="a", year=2010, cumulative_share=0.5, confidence="low"), dict(fid="a", year=2012, cumulative_share=1.0)], "source"),
    ([dict(fid="a", year=2010, cumulative_share=0.5, source_quote=None), dict(fid="a", year=2012, cumulative_share=1.0)], "quote"),
    ([dict(fid="a", year=2010, cumulative_share=0.5), dict(fid="a", year=2012, cumulative_share=0.9)], "rise to 1.0"),
    ([dict(fid="a", year=2010, cumulative_share=0.6), dict(fid="a", year=2012, cumulative_share=0.5)], "rise to 1.0"),
    ([dict(fid="a", year=2010, cumulative_share=1.0)], "two or more"),
    ([dict(fid="a", year=2010, cumulative_share=0.5), dict(fid="a", year=2010, cumulative_share=1.0)], "own year"),
    ([dict(fid="a", year=2010, cumulative_share=0.5), dict(fid="a", kind="single_building")], "one kind"),
    ([dict(fid="a", kind="single_building"), dict(fid="a", kind="single_building")], "one row"),
    ([dict(fid="a", kind="guess")], "unknown kind"),
])
def test_unusable_histories_are_refused(rows, message):
    with pytest.raises(ValueError, match=message):
        bo.validate(table(rows))


def test_a_valid_table_is_read_into_phases_and_single_buildings():
    t = bo.validate(table([dict(fid="a", year=2012, cumulative_share=1.0), dict(fid="a", year=2010, cumulative_share=0.4),
                           dict(fid="b", kind="single_building")]))
    assert bo.phases_by_site(t) == {"a": [(2010, 0.4), (2012, 1.0)]}
    assert bo.single_buildings(t) == {"b"}


def test_committed_histories_are_valid_and_sourced():
    t = bo.load()
    assert len(t) > 0
    hand = pd.read_csv(bo.VERIFIED[0]) if bo.VERIFIED[0].exists() else pd.DataFrame(columns=bo.COLUMNS)
    county = pd.read_csv(bo.VERIFIED[1])
    assert (county.kind == "single_building").all() and (county.confidence == "medium").all()
    assert county.source_url.str.contains("loudoun.gov|pwcva.gov").all()
    assert hand.source_url.str.startswith("https://").all()
    assert t.fid.nunique() == len(set(hand.fid) | set(county.fid))


# ---- the widened dating stress test (D-26, D-28) ------------------------------

def test_dating_cases_move_sites_both_ways_and_can_leave_them_out():
    rest = pd.DataFrame({"utility_id_eia": [5], "state": ["OH"], "year": [2015], "mw": [0.5]})
    sites = pd.DataFrame({"energized_year": [2015.0], "mw_full": [30.0]}, index=["bi:9-0"])
    where = pd.DataFrame({"utility_id_eia": [5], "state": ["OH"]}, index=["bi:9-0"])
    base = pd.Series({(5, "OH"): 10_000.0})                  # 2% is 22.8 MW: reached in the site's third year
    years = range(2001, 2026)
    cross = lambda shift: ds.first_crossings(rest, sites, where, base, years, 0.02, shift).get((5, "OH"))  # noqa: E731
    assert cross(0) == 2017
    assert cross(-5) == 2012 and cross(-10) == 2007          # earlier starts
    assert cross(3) == 2020                                  # a later start
    assert cross(None) is None                               # not operating: never a host
    assert ds.moved(cross(0), cross(-10)) and ds.moved(cross(0), cross(3)) and ds.moved(cross(0), cross(None))
    assert not ds.moved(2017, 2018)
