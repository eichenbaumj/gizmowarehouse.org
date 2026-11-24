"""The five-highest-load deletion (pipeline/analysis/influence_load.py) on invented quantities and invented outcomes only.

An invented world of seven hosts in seven states (cohorts 2013 to 2019, public and cooperative so no ownership row is
needed), sixty comparison utilities spread over eight states and across the hosts' sizes, every unit-year usable, built
under the headline rules by design.build_with_rules. Each host's data center load in its own event year 3 is set in an
invented load frame (LOAD): the five largest are hosts 1 to 5, the two kept are hosts 6 and 7.

The planted answer: the outcome is a unit effect + a calendar-year effect + 0.02 x heating degree days + a host path that
is zero before event year 0 and a host's own level from event year 0 on. Hosts 1 to 5 get 0.09, hosts 6 and 7 get 0.02.
With no noise the estimate over the two kept hosts is 0.02 exactly (tolerance 1e-8), while the full design's estimate is
pulled toward 0.09. No file under data/ is read.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import influence  # noqa: E402
from pipeline.analysis import influence_load as il  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import table  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
STATES = ["AA", "AB", "AC", "AD", "BA", "BB", "BC", "BD"]
FUEL = {s: i % 2 for i, s in enumerate(STATES)}
GAS = {s: g for s, g in zip(STATES, (0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75))}
COOP, PUB = "cooperative", "public"
HDD_BETA = 0.02
NONE = ps.UnknownLoad.none("invented data in a test")

# (id, state, residential customers, ownership, cohort)
HOSTS = [(1, "AA", 10_000, PUB, 2013), (2, "AB", 14_000, COOP, 2014), (3, "AC", 18_000, PUB, 2015),
         (4, "AD", 22_000, COOP, 2016), (5, "BA", 26_000, PUB, 2017), (6, "BB", 30_000, COOP, 2018),
         (7, "BC", 34_000, PUB, 2019)]
COMPS = [(100 + i, STATES[i % 8], 8_000 + 450 * i, (COOP, PUB)[i % 2]) for i in range(60)]
COHORT = {(h[0], h[1]): h[4] for h in HOSTS}
LOAD = {(1, "AA"): 900.0, (2, "AB"): 700.0, (3, "AC"): 500.0, (4, "AD"): 300.0, (5, "BA"): 200.0, (6, "BB"): 100.0,
        (7, "BC"): 50.0}
LEVEL = {k: (0.09 if k[0] <= 5 else 0.02) for k in COHORT}
TOL = 1e-8


def world(hosts=HOSTS, comps=COMPS):
    units = [h[:4] for h in hosts] + list(comps)
    q = pd.DataFrame([(u, st, y, own, float(size), 1.0, True) for u, st, size, own in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    regions = pd.DataFrame([(u, st, y, "West") for u, st, *_ in units for y in YEARS], columns=KEY + ["year", "region"])
    rng = np.random.default_rng(3)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in STATES for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    treated = pd.DataFrame([(h[0], h[1], h[4]) for h in hosts], columns=KEY + ["cohort"])
    clean = pd.DataFrame([c[:2] for c in comps], columns=KEY)
    usable = {(u, st, y) for u, st, *_ in units for y in YEARS}
    d = dsg.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, ownership=table([]), usable=usable,
                             gas=GAS, ownership_of=ps.ownership_classes(q), unknown_load=NONE, theta=0.02)
    return d, dd


def load_frame(load=LOAD, skip=()):
    """dc_gwh for every host-year: the host's LOAD value in every year (so event year 3 reads it), minus `skip`."""
    rows = [(k[0], k[1], y, v) for k, v in load.items() for y in YEARS if (k[0], k[1], y) not in skip]
    return pd.DataFrame(rows, columns=KEY + ["year", "dc_gwh"])


def outcome(dd, levels=LEVEL, noise=0.0, seed=7):
    rng = np.random.default_rng(seed)
    year_fx = dict(zip(YEARS, rng.normal(0, 0.05, len(YEARS))))
    rows = []
    for u, st, *_ in [h[:4] for h in HOSTS] + COMPS:
        a = rng.normal(0, 0.2)
        for y in YEARS:
            v = a + year_fx[y] + HDD_BETA * float(dd.hdd[(st, y)]) + noise * rng.normal()
            g = COHORT.get((u, st))
            if g is not None and y >= g:
                v += levels[(u, st)]
            rows.append((u, st, y, v))
    return pd.DataFrame(rows, columns=KEY + ["year", "value"])


@pytest.fixture(scope="module")
def built():
    return world()


# ---- the planted answer ---------------------------------------------------------------------------------------------

def check_planted(d, dd):
    """The assertions of the planted test, kept in one function so a deliberate break can be shown to fail them."""
    y = outcome(dd)
    r = il.estimate_without_the_five(d, load_frame(), y, "value")
    assert r["failure_in_words"] is None and r["estimated"]
    assert r["ranking"]["to_drop"] == ["1:AA", "2:AB", "3:AC", "4:AD", "5:BA"]
    assert r["ranking"]["kept"] == ["6:BB", "7:BC"]
    k = r["result"]
    assert abs(k["headline"]["log_points"] - 0.02) < TOL
    assert k["validation"] == oa.NOT_VALIDATED and k["validation_check"]["claimed"] is False
    assert k["hosts_in_the_design"] == ["6:BB", "7:BC"] and k["count_N"] == 2
    full = oa.estimate(d, oa.outcome_vector(d, y, "value"), validated_design=False)["headline"]["log_points"]
    assert full > 0.05                                 # five of seven hosts at 0.09: the full estimate is pulled up
    return r


def test_the_estimate_over_the_kept_hosts_recovers_their_planted_effect(built):
    d, dd = built
    r = check_planted(d, dd)
    assert r["rank_test_before_any_fit"]["estimable"] is True


def test_the_check_fails_when_the_deletion_is_broken(built, monkeypatch):
    """Deliberate breaks in the test process: keep every host (the deletion does nothing), or rank by the smallest load.
    Either way the planted assertions fail."""
    d, dd = built
    real_without = influence._without
    monkeypatch.setattr(il.influence, "_without", lambda dd_, keep: real_without(dd_, np.ones(len(keep), bool)))
    with pytest.raises(AssertionError):
        check_planted(d, dd)
    monkeypatch.undo()
    real = il._load_lookup                           # negated loads put hosts 6 and 7 at the top
    monkeypatch.setattr(il, "_load_lookup", lambda f: {k: -v for k, v in real(f).items()})
    with pytest.raises(AssertionError):
        check_planted(d, dd)


def test_the_remaining_hosts_keep_their_matches_untouched_and_the_rules_are_carried(built):
    d, _ = built
    e, r = il.drop_the_five(d, load_frame())
    before = {oa._host_label(k): list(mk) for k, mk in zip(d.hosts.key, d.hosts.match_keys)}
    after = {oa._host_label(k): list(mk) for k, mk in zip(e.hosts.key, e.hosts.match_keys)}
    assert set(after) == {"6:BB", "7:BC"} and all(after[h] == before[h] for h in after)
    assert e.rules is d.rules and e.support_table is None
    named = {x["utility"]: x["why"] for x in e.dropped}
    assert all(named.get(h) == il.WHY_DROPPED for h in r["to_drop"])
    assert len(d.hosts) == 7                         # the design passed in is not changed


def test_the_ranking_reports_every_host_its_load_and_the_gaps(built):
    d, _ = built
    r = il.ranking(d, load_frame(), names={(6, "BB"): "Six"})
    assert [x["host"] for x in r["ranking"]] == [f"{h[0]}:{h[1]}" for h in HOSTS]
    assert [x["dc_gwh"] for x in r["ranking"]] == [900.0, 700.0, 500.0, 300.0, 200.0, 100.0, 50.0]
    assert [x["gap_to_the_next_rank_gwh"] for x in r["ranking"]] == [200.0, 200.0, 200.0, 100.0, 100.0, 50.0, None]
    assert r["gap_at_the_line_gwh"] == 100.0 and r["exact_ties"] == [] and r["tie_at_the_line"] is None
    assert r["ranking"][5]["name"] == "Six" and r["ranking"][0]["event_year_3_calendar_year"] == 2016


def test_load_is_read_in_each_hosts_own_event_year_3(built):
    """Each host's load is LOAD in its own event year 3 and zero in every other year: the ranking is unchanged. Put a large
    load on host 7 in every year but its event year 3 and it stays last."""
    d, _ = built
    rows = [(k[0], k[1], y, (v if y == COHORT[k] + 3 else 0.0)) for k, v in LOAD.items() for y in YEARS]
    r = il.ranking(d, pd.DataFrame(rows, columns=KEY + ["year", "dc_gwh"]))
    assert r["to_drop"] == ["1:AA", "2:AB", "3:AC", "4:AD", "5:BA"]
    rows = [(k[0], k[1], y, (v if y == COHORT[k] + 3 else (5000.0 if k == (7, "BC") else 0.0))) for k, v in LOAD.items()
            for y in YEARS]
    r = il.ranking(d, pd.DataFrame(rows, columns=KEY + ["year", "dc_gwh"]))
    assert r["ranking"][-1]["host"] == "7:BC" and r["ranking"][-1]["dc_gwh"] == 50.0


# ---- the branches ---------------------------------------------------------------------------------------------------

def test_an_exact_tie_at_the_line_stops_the_run_and_names_the_tied_hosts(built):
    d, dd = built
    tied = {**LOAD, (6, "BB"): 200.0}                  # host 5 and host 6 both at 200: rank 5 and rank 6
    r = il.estimate_without_the_five(d, load_frame(tied), outcome(dd), "value")
    assert r["estimated"] is False and r["result"] is None and r["rank_test_before_any_fit"] is None
    t = r["ranking"]["tie_at_the_line"]
    assert t["hosts"] == ["5:BA", "6:BB"] and t["ranks"] == [5, 6] and t["dc_gwh"] == 200.0
    assert "exact tie at the line between rank 5 and rank 6" in r["failure_in_words"]
    assert "5:BA" in r["failure_in_words"] and "6:BB" in r["failure_in_words"] and "not decided by the code" in r["failure_in_words"]
    assert r["ranking"]["to_drop"] is None and r["ranking"]["gap_at_the_line_gwh"] == 0.0


def test_a_tie_away_from_the_line_is_listed_and_does_not_stop_the_run(built):
    d, dd = built
    tied = {**LOAD, (2, "AB"): 900.0}                  # hosts 1 and 2 tie at the top: both are dropped either way
    r = il.estimate_without_the_five(d, load_frame(tied), outcome(dd), "value")
    assert r["estimated"] and r["ranking"]["exact_ties"] == [{"hosts": ["1:AA", "2:AB"], "dc_gwh": 900.0, "ranks": [1, 2]}]
    assert abs(r["result"]["headline"]["log_points"] - 0.02) < TOL


def test_a_near_tie_at_the_line_is_reported_with_its_gap_and_decides_nothing(built):
    d, _ = built
    near = {**LOAD, (6, "BB"): 200.0 - 1e-9}
    r = il.ranking(d, load_frame(near))
    assert r["failure_in_words"] is None and r["tie_at_the_line"] is None
    assert r["to_drop"][-1] == "5:BA" and 0 < r["gap_at_the_line_gwh"] < 1e-8


@pytest.mark.parametrize("how", ["no_row", "nan"])
def test_a_host_with_no_load_in_its_event_year_3_is_a_failure_in_words(built, how):
    d, dd = built
    if how == "no_row":
        f = load_frame(skip={(4, "AD", COHORT[(4, "AD")] + 3)})
    else:
        f = load_frame()
        f.loc[(f.utility_id_eia == 4) & (f.year == COHORT[(4, "AD")] + 3), "dc_gwh"] = np.nan
    r = il.estimate_without_the_five(d, f, outcome(dd), "value")
    assert r["estimated"] is False and r["result"] is None
    assert "4:AD" in r["failure_in_words"] and "not read as zero" in r["failure_in_words"] and "2019" in r["failure_in_words"]
    assert r["ranking"]["ranking"] is None


def test_five_or_fewer_hosts_leave_nothing_and_are_not_estimable():
    d, dd = world(hosts=HOSTS[:5])
    r = il.estimate_without_the_five(d, load_frame(), outcome(dd), "value")
    assert r["estimated"] is False and r["result"] is None
    assert "5 hosts are in the estimate" in r["failure_in_words"] and "leaves no host" in r["failure_in_words"]
    assert len(r["ranking"]["ranking"]) == 5                    # the ranking is still reported


def test_a_load_frame_that_repeats_a_unit_year_stops_in_words(built):
    d, _ = built
    f = load_frame()
    with pytest.raises(il.LoadFrameRefused, match="repeats a unit-year"):
        il.ranking(d, pd.concat([f, f.iloc[:1]]))
    with pytest.raises(il.LoadFrameRefused, match="no column"):
        il.ranking(d, f.rename(columns={"dc_gwh": "dc_mw"}))


def test_a_deleted_design_that_fails_the_rank_test_is_not_fitted(built, monkeypatch):
    d, dd = built
    calls = []
    monkeypatch.setattr(il.influence, "estimable", lambda e, fc: {"estimable": False, "smallest_singular_value_ratio": 0.0,
                                                                     "hosts_with_no_matches": [], "hosts_with_zero_weight": []})
    monkeypatch.setattr(il.oa, "estimate", lambda *a, **k: calls.append(1))
    r = il.estimate_without_the_five(d, load_frame(), outcome(dd), "value")
    assert calls == [] and r["estimated"] is False and "rank test made before any fit" in r["failure_in_words"]


def test_no_function_reads_a_file():
    import ast
    tree = ast.parse(Path(il.__file__).read_text())
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not {"load_outcomes", "read_listed_outcomes", "read_parquet", "read_csv"} & calls
    src = Path(il.__file__).read_text()
    assert "data/blind" not in src and "availability" not in src
