"""The influence deletions of a market region, a state and Virginia (pipeline/analysis/influence_deletions.py), on invented
quantities and invented outcomes only. No file under data/ is read.

The invented world: two market regions, "West" (states AA, AB, AC, AD) and "East" (BA, BB, BC, BD). Six hosts, three in
each region (one per state AA, AB, AC, BA, BB, BC; cohorts 2013 to 2018; public and cooperative, so no ownership row is
needed), and sixty comparison utilities, thirty in each region spread over its four states and across the hosts' sizes.
Every unit-year is usable. The design is built under the headline rules by design.build_with_rules.

The planted answers. The outcome is a unit effect + a calendar-year effect + 0.02 x heating degree days + a host path that
is zero before event year 0 and the host's own level from event year 0 on. With no noise, a design whose remaining hosts
share one level estimates that level exactly (tolerance 1e-8):
  * East's hosts at 0.09 and West's at 0.02: East left out gives 0.02, West left out gives 0.09.
  * the host in BC at 0.09 and the rest at 0.02: state BC left out gives 0.02, though BC's comparison utilities also leave
    every remaining East host's matches.
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
from pipeline.analysis import influence_deletions as idl  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import table  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
WEST, EAST = ["AA", "AB", "AC", "AD"], ["BA", "BB", "BC", "BD"]
REGION_OF = {**{s: "West" for s in WEST}, **{s: "East" for s in EAST}, "VA": "East"}
COOP, PUB = "cooperative", "public"
HDD_BETA = 0.02
NONE = ps.UnknownLoad.none("invented data in a test")
TOL = 1e-8

# (id, state, residential customers, ownership, cohort)
HOSTS = [(1, "AA", 10_000, PUB, 2013), (2, "AB", 14_000, COOP, 2014), (3, "AC", 18_000, PUB, 2015),
         (4, "BA", 12_000, COOP, 2016), (5, "BB", 16_000, PUB, 2017), (6, "BC", 20_000, COOP, 2018)]
COMPS = ([(100 + i, WEST[i % 4], 8_000 + 500 * i, (COOP, PUB)[i % 2]) for i in range(30)]
         + [(200 + i, EAST[i % 4], 8_000 + 500 * i, (COOP, PUB)[i % 2]) for i in range(30)])


def world(hosts=HOSTS, comps=COMPS):
    units = [h[:4] for h in hosts] + list(comps)
    states = sorted({u[1] for u in units})
    q = pd.DataFrame([(u, st, y, own, float(size), 1.0, True) for u, st, size, own in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    regions = pd.DataFrame([(u, st, y, REGION_OF[st]) for u, st, *_ in units for y in YEARS], columns=KEY + ["year", "region"])
    rng = np.random.default_rng(3)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in states for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    fuel = {s: i % 2 for i, s in enumerate(states)}
    gas = {s: 0.05 + 0.08 * i for i, s in enumerate(states)}
    treated = pd.DataFrame([(h[0], h[1], h[4]) for h in hosts], columns=KEY + ["cohort"])
    clean = pd.DataFrame([c[:2] for c in comps], columns=KEY)
    usable = {(u, st, y) for u, st, *_ in units for y in YEARS}
    d = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, ps.HEADLINE_RULES, ownership=table([]), usable=usable,
                             gas=gas, ownership_of=ps.ownership_classes(q), unknown_load=NONE, theta=0.02)
    return d, dd


def outcome(dd, levels, hosts=HOSTS, comps=COMPS, noise=0.0, seed=7):
    cohort = {(h[0], h[1]): h[4] for h in hosts}
    rng = np.random.default_rng(seed)
    year_fx = dict(zip(YEARS, rng.normal(0, 0.05, len(YEARS))))
    rows = []
    for u, st, *_ in [h[:4] for h in hosts] + list(comps):
        a = rng.normal(0, 0.2)
        for y in YEARS:
            v = a + year_fx[y] + HDD_BETA * float(dd.hdd[(st, y)]) + noise * rng.normal()
            g = cohort.get((u, st))
            if g is not None and y >= g:
                v += levels[(u, st)]
            rows.append((u, st, y, v))
    return pd.DataFrame(rows, columns=KEY + ["year", "value"])


EAST_HIGH = {(h[0], h[1]): (0.09 if REGION_OF[h[1]] == "East" else 0.02) for h in HOSTS}
BC_HIGH = {(h[0], h[1]): (0.09 if h[1] == "BC" else 0.02) for h in HOSTS}


@pytest.fixture(scope="module")
def built():
    return world()


def _run(rs, kind, value):
    return next(x for x in rs["deletions"] if x["kind"] == kind and x["value"] == value)


# ---- the planted answers --------------------------------------------------------------------------------------------

def check_region_planted(d, dd):
    """The planted region assertions, in one function so a deliberate break can be shown to fail them."""
    rs = idl.run_deletions(d, outcome(dd, EAST_HIGH), "value", full_design_validation=False)
    east, west = _run(rs, "region", "East"), _run(rs, "region", "West")
    assert east["estimated"] and west["estimated"]
    assert abs(east["result"]["headline"]["log_points"] - 0.02) < TOL
    assert abs(west["result"]["headline"]["log_points"] - 0.09) < TOL
    assert east["result"]["hosts_in_the_design"] == ["1:AA", "2:AB", "3:AC"]
    assert east["what_left"]["matched_units_leaving_remaining_hosts"] == []
    full = rs["full_design"]["headline"]["log_points"]
    assert 0.02 + 0.01 < full < 0.09 - 0.01                       # the full design mixes both
    return rs


def test_a_region_left_out_takes_its_hosts_and_recovers_the_other_regions_planted_effect(built):
    d, dd = built
    rs = check_region_planted(d, dd)
    e = _run(rs, "region", "East")
    assert e["result"]["validation"] == oa.NOT_VALIDATED and e["result"]["validation_check"]["claimed"] is False
    assert e["label"].endswith(oa.NOT_VALIDATED) and "region East left out" in e["label"]
    assert e["after_deletion"]["rank_test_before_any_fit"]["estimable"] is True


def test_the_region_check_fails_when_the_deletion_is_broken(built, monkeypatch):
    """Deliberate breaks in the test process: the region deletion keeps every host, or drops the wrong region."""
    d, dd = built
    real = idl.influence._without
    monkeypatch.setattr(idl.influence, "_without", lambda dd_, keep: real(dd_, np.ones(len(keep), bool)))
    with pytest.raises(AssertionError):
        check_region_planted(d, dd)
    monkeypatch.undo()
    real_region = idl.delete_region
    monkeypatch.setattr(idl, "delete_region", lambda d_, r: real_region(d_, "West" if r == "East" else "East"))
    with pytest.raises(AssertionError):
        check_region_planted(d, dd)


def test_a_state_left_out_takes_its_host_and_its_comparison_utilities_from_every_remaining_host(built):
    d, dd = built
    r = idl.estimate_deletion(d, "state", "BC", outcome(dd, BC_HIGH), "value")
    assert r["estimated"] and abs(r["result"]["headline"]["log_points"] - 0.02) < TOL
    assert r["what_left"]["hosts_leaving"] == ["6:BC"]
    e, _ = idl.delete_state(d, "BC")
    before = {oa._host_label(k): list(mk) for k, mk in zip(d.hosts.key, d.hosts.match_keys)}
    after = {oa._host_label(k): list(mk) for k, mk in zip(e.hosts.key, e.hosts.match_keys)}
    assert set(after) == {"1:AA", "2:AB", "3:AC", "4:BA", "5:BB"}
    for h, mk in after.items():                                   # no rematching: the others in the same order
        assert mk == [m for m in before[h] if m[1] != "BC"]
        assert all(m[1] != "BC" for m in mk)
    lost = {h: len(before[h]) - len(after[h]) for h in after}
    assert lost["4:BA"] > 0 and lost["5:BB"] > 0 and lost["1:AA"] == 0          # East hosts lose their BC matches
    left = set(r["what_left"]["matched_units_leaving_remaining_hosts"])
    assert left and all(u.endswith(":BC") for u in left)
    assert e.rules is d.rules and e.support_table is None and len(d.hosts) == 6   # rules carried; d unchanged
    assert any(x["utility"] == "6:BC" and "state BC is left out" in x["why"] for x in e.dropped)


def test_every_region_and_state_present_is_run_and_virginia_once(built):
    d, dd = built
    assert idl.regions_present(d) == ["East", "West"]
    present = idl.states_present(d)
    assert set(present) <= set(WEST + EAST) and {"AA", "AB", "AC", "BA", "BB", "BC"} <= set(present)
    plan = idl.deletion_list(d)
    assert plan[:2] == [("region", "East"), ("region", "West")] and plan[-1] == ("state", "VA")
    assert [p for p in plan if p == ("state", "VA")] == [("state", "VA")]


# ---- Virginia ---------------------------------------------------------------------------------------------------------

def test_virginia_removes_nothing_says_so_and_is_not_in_the_range(built):
    d, dd = built
    rs = idl.run_deletions(d, outcome(dd, EAST_HIGH), "value", full_design_validation=False)
    va = _run(rs, "state", "VA")
    assert va["what_left"]["removes_nothing"] is True and va["virginia"] == idl.VIRGINIA_REMOVES_NOTHING
    assert rs["virginia"] == idl.VIRGINIA_REMOVES_NOTHING
    assert "not presented as a check passed" in va["virginia"] and "checked on the design" in va["virginia"]
    assert abs(va["result"]["headline"]["log_points"] - rs["full_design"]["headline"]["log_points"]) < 1e-10
    assert va["result"]["validation"] == oa.NOT_VALIDATED
    s = rs["summary"]
    assert "state VA" not in s["deletions_in_the_range"]
    assert s["deletions_that_remove_nothing_reported_beside_the_range"] == ["state VA"]


def test_virginia_present_is_reported_as_removing_what_it_removes():
    comps = COMPS + [(300, "VA", 15_000, COOP)]
    hosts = HOSTS
    d, dd = world(hosts, comps)
    in_va = [m for mk in d.hosts.match_keys for m in mk if m[1] == "VA"]
    assert in_va                                                  # the guard: the VA unit is matched to an East host
    r = idl.estimate_deletion(d, "state", "VA", outcome(dd, EAST_HIGH, hosts, comps), "value")
    assert r["what_left"]["removes_nothing"] is False
    assert r["virginia"] != idl.VIRGINIA_REMOVES_NOTHING and "removes 0 host(s) and 1 matched" in r["virginia"]
    assert idl.deletion_list(d).count(("state", "VA")) == 1


# ---- rule 7's treatment -----------------------------------------------------------------------------------------------

def _thin_world():
    """East has two hosts, in BA (12,000 customers) and in BC (31,000). East's comparison utilities: ten in BD near
    30,000 and four in BC near 9,000. The host in BA is matched to the four in BC and six in BD; the host in BC is matched
    to the ten in BD. Leaving BD out leaves the first with four matches and the second with none."""
    east = [(200 + i, "BD", 30_000 + 10 * i, COOP) for i in range(10)] + [(220 + i, "BC", 9_000 + 10 * i, PUB) for i in range(4)]
    west = [(100 + i, WEST[i % 4], 8_000 + 500 * i, (COOP, PUB)[i % 2]) for i in range(30)]
    hosts = [(1, "AA", 10_000, PUB, 2013), (2, "AB", 14_000, COOP, 2014), (3, "AC", 18_000, PUB, 2015),
             (4, "BA", 12_000, COOP, 2016), (6, "BC", 31_000, COOP, 2018)]
    return hosts, west + east


def test_a_host_left_short_stays_and_a_host_left_with_none_is_named_not_estimable():
    hosts, comps = _thin_world()
    d, dd = world(hosts, comps)
    m = {oa._host_label(k): list(mk) for k, mk in zip(d.hosts.key, d.hosts.match_keys)}
    assert all(x[1] == "BD" for x in m["6:BC"]) and len(m["6:BC"]) == 10          # guard: BC's host matched only in BD
    n_ba_bc = sum(x[1] == "BC" for x in m["4:BA"])
    assert 0 < n_ba_bc < 5                                                         # guard: BA's host has some BC matches
    levels = {(h[0], h[1]): 0.02 for h in hosts}
    r = idl.estimate_deletion(d, "state", "BD", outcome(dd, levels, hosts, comps), "value")
    a = r["after_deletion"]
    assert [x["host"] for x in a["hosts_with_fewer_than_five_matches_inadequately_supported_kept"]] == ["4:BA"]
    assert a["hosts_with_fewer_than_five_matches_inadequately_supported_kept"][0]["matches_left"] == n_ba_bc
    assert [x["host"] for x in a["hosts_with_no_matches_not_estimable"]] == ["6:BC"]
    assert r["estimated"] and abs(r["result"]["headline"]["log_points"] - 0.02) < TOL
    assert "4:BA" in r["result"]["hosts_in_the_design"]                            # short, and stays
    assert r["result"]["hosts_with_no_matches"] == ["6:BC"]                        # named by the kernel, not stacked
    assert r["result"]["count_N"] == 4


def test_a_host_with_zero_weight_is_named_not_estimable(built, monkeypatch):
    d, dd = built
    real = influence.estimable
    monkeypatch.setattr(idl.influence, "estimable", lambda e, fc: {**real(e, fc), "hosts_with_zero_weight": ["1:AA"]})
    r = idl.estimate_deletion(d, "region", "East", outcome(dd, EAST_HIGH), "value", names={(1, "AA"): "One"})
    z = r["after_deletion"]["hosts_with_zero_weight_not_estimable"]
    assert z == [{"host": "1:AA", "name": "One", "why": idl.ZERO_WORDS}]


def test_the_rank_test_comes_before_any_fit(built, monkeypatch):
    d, dd = built
    calls = []
    monkeypatch.setattr(idl.influence, "estimable", lambda e, fc: {"estimable": False, "smallest_singular_value_ratio": 0.0,
                                                                      "hosts_with_no_matches": [], "hosts_with_zero_weight": []})
    monkeypatch.setattr(idl.oa, "estimate", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(idl.oa, "outcome_vector", lambda *a, **k: calls.append(2))
    r = idl.estimate_deletion(d, "state", "AA", outcome(dd, EAST_HIGH), "value")
    assert calls == [] and r["estimated"] is False and r["result"] is None
    assert "rank test made before any fit" in r["failure_in_words"]


def test_a_deletion_that_leaves_no_host_is_not_estimable_in_words():
    hosts = [h for h in HOSTS if REGION_OF[h[1]] == "East"]
    d, dd = world(hosts, COMPS)
    r = idl.estimate_deletion(d, "region", "East", outcome(dd, EAST_HIGH, hosts), "value")
    assert r["estimated"] is False and "no host remains" in r["failure_in_words"]


# ---- the summary ----------------------------------------------------------------------------------------------------

def test_the_range_and_the_deletion_that_moves_it_most(built):
    d, dd = built
    rs = idl.run_deletions(d, outcome(dd, EAST_HIGH, noise=0.01), "value", full_design_validation=False)
    s = rs["summary"]
    est = {f"{x['kind']} {x['value']}": x["result"]["headline"]["log_points"] for x in rs["deletions"] if x["estimated"]
           and not x["what_left"]["removes_nothing"]}
    assert s["range_of_estimates_log_points"] == [min(est.values()), max(est.values())]
    f = rs["full_design"]["headline"]["log_points"]
    best = max(est, key=lambda k: abs(est[k] - f))
    assert s["moves_it_most"]["deletion"] == best and s["exact_tie_for_moves_it_most"] is None
    assert best in ("region East", "region West")


def test_an_exact_tie_for_the_largest_move_is_named_and_none_is_picked():
    full = {"headline": {"log_points": 0.05, "range_90_log_points": [0.01, 0.09]}}
    mk = lambda kind, v, est: {"kind": kind, "value": v, "estimated": True, "failure_in_words": None,  # noqa: E731
                               "what_left": {"removes_nothing": False},
                               "result": {"headline": {"log_points": est, "range_90_log_points": [est - 0.06, est + 0.06]}}}
    s = idl.summarise(full, [mk("region", "East", 0.03), mk("region", "West", 0.07), mk("state", "AA", 0.06)])
    assert s["moves_it_most"] is None
    assert s["exact_tie_for_moves_it_most"]["deletions"] == ["region East", "region West"]
    spans = [x["deletion"] for x in s["ranges_that_span_zero_where_the_full_designs_does_not"]]
    assert spans == ["region East", "state AA"] and all(x["words"] == idl.SPANS_ZERO
                                                        for x in s["ranges_that_span_zero_where_the_full_designs_does_not"])


def test_quantity_summary_reads_no_outcome_and_carries_virginias_line(built):
    d, _ = built
    s = idl.quantity_summary(d, names={(6, "BC"): "Six"})
    assert s["virginia"] == idl.VIRGINIA_REMOVES_NOTHING
    bc = next(r for r in s["deletions"] if r["kind"] == "state" and r["value"] == "BC")
    assert bc["hosts_leaving"] == [{"host": "6:BC", "name": "Six"}] and bc["rank_test_before_any_fit"]["estimable"]
    assert all(r["label"].endswith(oa.NOT_VALIDATED) for r in s["deletions"])


def test_no_function_reads_a_file():
    import ast
    src = Path(idl.__file__).read_text()
    tree = ast.parse(src)
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not {"load_outcomes", "read_listed_outcomes", "read_parquet", "read_csv"} & calls
    assert "data/blind" not in src and "availability" not in src


def test_the_definitions_of_r7s_terms_are_marked_adopted():
    """D-111 (item N-16): the definitions of "present", a state deletion, the range's members and "moves most" are Joe's,
    and the module says so; the one reading that is not N-16 (Virginia listed once) stays marked."""
    doc = " ".join(idl.__doc__.split())
    head = doc.split("The agent's readings")[0]
    assert "Adopted by Joe on 2026-11-19 (D-111)" in head
    for words in ("a region is present when it is the reference-year region of a host",
                  "a state deletion removes units in that state",
                  "is reported beside them and is not in the range",
                  "\"Moves it most\" is the largest absolute difference in log points"):
        assert words in head, words
    assert "listed once, as Virginia" in doc.split("The agent's readings")[1]
    assert "agent's reading" not in idl.regions_present.__doc__ and "agent's reading" not in idl.summarise.__doc__
