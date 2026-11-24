"""The size-band form as a side run (pipeline/analysis/size_band_run.py), on invented quantities and invented outcomes only.
No file under data/ is read.

The invented world: one market region, "West", over states AA to AD. Four hosts (public and cooperative, so no ownership
row is needed): host 1 with 9,000 residential customers (band under 10,000), hosts 2 and 3 with 11,000 and 40,000 (band
10,000 to 99,999), host 4 with 300,000 (band 100,000 or more); cohorts 2013 to 2016. Comparison utilities: twelve with
6,000 to 9,900 customers, twelve with 10,100 to 60,000 and ten with 120,000 to 600,000. Every unit-year is usable unless
a test says otherwise.

The planted answer: the outcome is a unit effect + a calendar-year shock that differs by size band + 0.02 x heating
degree days + 0.03 on host rows from event year 0. With no noise the size-band form, whose year effects are by cell,
recovers 0.03 exactly (tolerance 1e-8). The ten-nearest form does not here: host 2 (11,000) has comparison utilities from
the band below among its ten nearest, whose shocks differ (the guard that the test can tell the two apart).
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
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import size_band_run as sb  # noqa: E402
from test_matching_rules import table  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
STATES = ["AA", "AB", "AC", "AD"]
COOP, PUB = "cooperative", "public"
HDD_BETA = 0.02
EFFECT = 0.03
NONE = ps.UnknownLoad.none("invented data in a test")
TOL = 1e-8

HOSTS = [(1, "AA", 9_000, PUB, 2013), (2, "AB", 11_000, COOP, 2014), (3, "AC", 40_000, PUB, 2015),
         (4, "AD", 300_000, COOP, 2016)]
SMALL = [(100 + i, STATES[i % 4], 6_000 + 300 * i, (COOP, PUB)[i % 2]) for i in range(12)]          # 6,000 to 9,300
MID = [(200 + i, STATES[i % 4], 10_100 + 4_500 * i, (COOP, PUB)[i % 2]) for i in range(12)]         # 10,100 to 59,600
LARGE = [(300 + i, STATES[i % 4], 120_000 + 50_000 * i, (COOP, PUB)[i % 2]) for i in range(10)]     # 120,000 to 570,000
COMPS = SMALL + MID + LARGE


def world(hosts=HOSTS, comps=COMPS, region_of=None, unusable=(), q_extra=()):
    region_of = region_of or {}
    units = [h[:4] for h in hosts] + list(comps)
    states = sorted({u[1] for u in units})
    q = pd.DataFrame([(u, st, y, own, float(size), 1.0, True) for u, st, size, own in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    regions = pd.DataFrame([(u, st, y, region_of.get(st, "West")) for u, st, *_ in units for y in YEARS],
                           columns=KEY + ["year", "region"])
    rng = np.random.default_rng(3)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in states for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    fuel = {s: i % 2 for i, s in enumerate(states)}
    gas = {s: 0.1 + 0.15 * i for i, s in enumerate(states)}
    treated = pd.DataFrame([(h[0], h[1], h[4]) for h in hosts], columns=KEY + ["cohort"])
    clean = pd.DataFrame([c[:2] for c in comps], columns=KEY)
    usable = {(u, st, y) for u, st, *_ in units for y in YEARS} - set(unusable)
    kw = dict(ownership=table([]), usable=usable, gas=gas, ownership_of=ps.ownership_classes(q), unknown_load=NONE, theta=0.02)
    try:
        d = sb.build(treated, clean, q, regions, fuel, dd, **kw)
    except sb.OutsideTheAdoptedScope:
        # A world in which two hosts share a cohort and a cell (the equivalence test's W2 and W3, and the guard's tests):
        # build refuses it (D-111), so the equivalence record's per-host design comes from the construction without the
        # refusal. Only the refusal class is caught; tests of the guard call sb.build directly.
        d = sb._per_host_design(treated, clean, q, regions, fuel, dd, **kw)
    return d, dd, (treated, clean, q, regions, fuel, dd, kw)


def band(size):
    return int(np.digitize(size, ps.SIZE_BANDS))


def outcome(dd, hosts=HOSTS, comps=COMPS, noise=0.0, seed=7, effect=EFFECT):
    cohort = {(h[0], h[1]): h[4] for h in hosts}
    rng = np.random.default_rng(seed)
    shock = {b: dict(zip(YEARS, rng.normal(0, 0.08, len(YEARS)))) for b in (0, 1, 2)}
    rows = []
    for u, st, size, _ in [h[:4] for h in hosts] + list(comps):
        a = rng.normal(0, 0.2)
        for y in YEARS:
            v = a + shock[band(size)][y] + HDD_BETA * float(dd.hdd[(st, y)]) + noise * rng.normal()
            g = cohort.get((u, st))
            if g is not None and y >= g:
                v += effect
            rows.append((u, st, y, v))
    return pd.DataFrame(rows, columns=KEY + ["year", "value"])


@pytest.fixture(scope="module")
def built():
    return world()


def _cells(d):
    return {c["host"]: c for c in d.cells}


# ---- the planted answer ---------------------------------------------------------------------------------------------

def check_planted(d, dd):
    r = sb.estimate_size_band(d, outcome(dd), "value")
    assert r["estimated"] and r["failure_in_words"] is None
    assert abs(r["result"]["headline"]["log_points"] - EFFECT) < TOL
    assert r["result"]["validation"] == oa.NOT_VALIDATED and r["label"] == sb.LABEL
    return r


def test_the_size_band_form_recovers_the_planted_effect_under_band_specific_shocks(built):
    d, dd, _ = built
    r = check_planted(d, dd)
    assert r["rank_test_before_any_fit"]["estimable"] is True
    assert r["result"]["hosts_in_the_design"] == ["1:AA", "2:AB", "3:AC", "4:AD"] and r["result"]["count_N"] == 4


def test_the_ten_nearest_form_does_not_recover_it_here(built):
    """The guard: in this world the two forms differ, so the planted test above checks the cells."""
    _, dd, (treated, clean, q, regions, fuel, dd_, kw) = built
    main = dsg.build_with_rules(treated, clean, q, regions, fuel, dd_, ps.HEADLINE_RULES, **kw)
    m2 = next(mk for k, mk in zip(main.hosts.key, main.hosts.match_keys) if k == (2, "AB"))
    assert any(band(dict((c[:2], c[2]) for c in COMPS)[tuple(m)]) == 0 for m in m2)
    k = oa.estimate(main, oa.outcome_vector(main, outcome(dd), "value"), validated_design=False)
    assert abs(k["headline"]["log_points"] - EFFECT) > 1e-4


def test_the_planted_check_fails_when_the_cells_are_broken(built, monkeypatch):
    """Deliberate break in the test process: rebuild with every unit read as one band, so the cells are the region."""
    _, dd, (treated, clean, q, regions, fuel, dd_, kw) = built
    real = ps.size_band
    monkeypatch.setattr(ps, "size_band", lambda c: np.zeros(len(np.asarray(c)), dtype=int))
    d_broken = sb.build(treated, clean, q, regions, fuel, dd_, **kw)
    monkeypatch.setattr(ps, "size_band", real)
    with pytest.raises(AssertionError):
        check_planted(d_broken, dd)


# ---- the comparison set -----------------------------------------------------------------------------------------------

def test_each_hosts_comparisons_are_every_eligible_unit_in_its_cell(built):
    d, _, _ = built
    c = _cells(d)
    expect = {1: SMALL, 2: MID, 3: MID, 4: LARGE}
    for h in HOSTS:
        got = set(c[f"{h[0]}:{h[1]}"]["comparisons"])
        assert got == {f"{u}:{s}" for u, s, *_ in expect[h[0]]}
        assert c[f"{h[0]}:{h[1]}"]["comparison_utilities_in_its_cell"] == len(expect[h[0]])
        assert c[f"{h[0]}:{h[1]}"]["eligible_in_its_region_in_the_reference_year"] == len(COMPS)
    assert c["1:AA"]["size_band"] == "under 10,000" and c["4:AD"]["size_band"] == "100,000 or more"
    assert c["2:AB"]["residential_customers_in_the_reference_year"] == 11_000.0 and c["2:AB"]["reference_year"] == 2011
    assert d.rules is sb.SIZE_BAND_RULES and d.support_table is None


def test_ownership_and_full_window_usability_apply_before_the_cells():
    """A unit of host 3's own utility in another state, in its band, is never its comparison (D-54 ruling 2); a mid-band
    unit with one unusable year in host 2's window is in no window of that cohort, so not host 2's comparison."""
    own = (3, "AA", 30_000, PUB)
    gap = MID[5]
    d, _, _ = world(comps=COMPS + [own], unusable={(gap[0], gap[1], 2010)})
    c = _cells(d)
    assert "3:AA" not in c["3:AC"]["comparisons"] and "3:AA" in c["2:AB"]["comparisons"]
    assert f"{gap[0]}:{gap[1]}" not in c["2:AB"]["comparisons"]           # host 2's window is 2008 to 2017
    assert f"{gap[0]}:{gap[1]}" not in c["3:AC"]["comparisons"]           # host 3's window, 2009 to 2018, has 2010 too
    d_all, _, _ = world(comps=COMPS + [own])
    assert f"{gap[0]}:{gap[1]}" in _cells(d_all)["2:AB"]["comparisons"]  # the guard: usable, it is host 2's comparison
    excluded = next(r for r in d.hosts.itertuples() if r.key == (3, "AC")).excluded_from_its_pool
    assert {"utility": "3:AA", "why": "a unit of the host's own utility (D-54, ruling 2)"} in excluded


def test_a_host_with_no_comparison_in_its_cell_is_named_not_estimable_and_the_rest_are_estimated():
    d, dd, _ = world(comps=SMALL + MID)                 # nothing of 100,000 or more: host 4's cell is empty
    c = _cells(d)
    assert c["4:AD"]["comparison_utilities_in_its_cell"] == 0
    r = sb.estimate_size_band(d, outcome(dd, comps=SMALL + MID), "value")
    assert r["hosts_with_no_comparison_in_its_cell_not_estimable"] == [{"host": "4:AD", "why": sb.NO_CELL}]
    assert r["estimated"] and abs(r["result"]["headline"]["log_points"] - EFFECT) < TOL
    assert r["result"]["hosts_with_no_matches"] == ["4:AD"] and r["result"]["count_N"] == 3
    s = sb.quantity_summary(d)
    assert [x["host"] for x in s["hosts_with_no_comparison_in_its_cell_not_estimable"]] == ["4:AD"]


def test_the_first_limb_names_and_leaves_out_a_host_with_fewer_than_ten_eligible_in_its_region():
    """A second region, East (state BA), with one host and nine comparison utilities: fewer than ten."""
    east_host = (5, "BA", 20_000, PUB, 2015)
    east = [(400 + i, "BA", 15_000 + 1_000 * i, COOP) for i in range(9)]
    hosts, comps = HOSTS + [east_host], COMPS + east
    d, dd, _ = world(hosts, comps, region_of={"BA": "East"})
    assert "5:BA" not in {oa._host_label(k) for k in d.hosts.key}
    assert d.first_limb_failures == ["5:BA"]
    why = next(x["why"] for x in d.dropped if x["utility"] == "5:BA")
    assert why == sb.FIRST_LIMB_WHY.format(n=9)
    r = sb.estimate_size_band(d, outcome(dd, hosts, comps), "value")
    assert r["first_limb_failures"] == ["5:BA"] and abs(r["result"]["headline"]["log_points"] - EFFECT) < TOL
    # Ten in the region pass the limb (the line is "at least ten").
    d10, _, _ = world(hosts, comps + [(409, "BA", 25_000, COOP)], region_of={"BA": "East"})
    assert "5:BA" in {oa._host_label(k) for k in d10.hosts.key}


def test_the_rank_test_comes_before_any_fit(built, monkeypatch):
    d, dd, _ = built
    calls = []
    monkeypatch.setattr(sb.influence, "estimable", lambda e, fc: {"estimable": False, "smallest_singular_value_ratio": 0.0,
                                                                     "hosts_with_no_matches": [], "hosts_with_zero_weight": []})
    monkeypatch.setattr(sb.oa, "estimate", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(sb.oa, "outcome_vector", lambda *a, **k: calls.append(2))
    r = sb.estimate_size_band(d, outcome(dd), "value")
    assert calls == [] and r["estimated"] is False and "rank test made before any fit" in r["failure_in_words"]


SHARED = [(1, "AA", 9_000, PUB, 2013), (2, "AB", 11_000, COOP, 2014), (3, "AC", 40_000, PUB, 2014)]
SHARED_GROUP = [{"cohort": 2014, "region": "West", "size_band": "10,000 to 99,999", "hosts": ["2:AB", "3:AC"]}]


def test_hosts_sharing_a_cohort_and_a_cell_are_listed():
    """On the construction without the refusal (the equivalence test's worlds), the summary still lists them, and the
    guard's grouping is the summary's."""
    d, _, _ = world(SHARED)
    s = sb.quantity_summary(d)
    assert s["hosts_sharing_a_cohort_and_a_cell"] == SHARED_GROUP
    assert sb.hosts_sharing_a_cohort_and_a_cell(d) == SHARED_GROUP
    assert s["hosts_by_cell"]["West | 10,000 to 99,999"] == ["2:AB", "3:AC"]


# ---- the adopted scope (Joe, 2026-11-19, D-111) and its guard ---------------------------------------------------------

def _inputs(hosts):
    _, _, (treated, clean, q, regions, fuel, dd, kw) = world(hosts)
    return (treated, clean, q, regions, fuel, dd), kw


def test_build_refuses_a_set_in_which_two_hosts_share_a_cohort_and_a_cell_naming_them():
    args, kw = _inputs(SHARED)
    with pytest.raises(sb.OutsideTheAdoptedScope) as e:
        sb.build(*args, **kw)
    msg = str(e.value)
    assert e.value.shared == SHARED_GROUP
    assert "hosts 2:AB and 3:AC share cohort 2014 and the cell West by 10,000 to 99,999" in msg
    assert "outside this freeze" in msg and "Joe on 2026-11-19 (D-111)" in msg and "headline set at 2%" in msg
    assert "no extension is built" in msg and "No design is returned and nothing is stacked" in msg
    assert "1:AA" not in msg                                     # only the hosts that share are named


def test_the_refusal_comes_before_anything_is_stacked(monkeypatch):
    """Nothing downstream of the refusal runs: no stack, no rank test, no fit."""
    args, kw = _inputs(SHARED)
    calls = []
    for mod, name in ((ps, "assemble"), (sb.influence, "estimable"), (sb.oa, "estimate")):
        monkeypatch.setattr(mod, name, lambda *a, _n=name, **k: calls.append(_n))
    with pytest.raises(sb.OutsideTheAdoptedScope):
        sb.build(*args, **kw)
    assert calls == []


def test_two_hosts_in_one_cell_but_different_cohorts_pass(built):
    """The base world: hosts 2 and 3 share the cell West by 10,000 to 99,999 in cohorts 2014 and 2015. Not a shared cohort
    and cell, so build returns the design."""
    d, _, (treated, clean, q, regions, fuel, dd, kw) = built
    assert sb.hosts_sharing_a_cohort_and_a_cell(d) == []
    d2 = sb.build(treated, clean, q, regions, fuel, dd, **kw)
    assert [oa._host_label(k) for k in d2.hosts.key] == ["1:AA", "2:AB", "3:AC", "4:AD"]


def test_the_design_with_no_shared_cell_is_unchanged_by_the_guard(built):
    """build on the base world returns exactly the construction without the refusal: the same stacked rows in the same
    order and the same implied weights on every stacked row (to 1e-12). The weights are computed with the equivalence
    test's support (tests/size_band_pooled_form.py), unchanged. The rows and weights before the edit of 2026-11-19 are
    compared in the session's scratch record, not here."""
    import size_band_pooled_form as pf
    _, _, (treated, clean, q, regions, fuel, dd, kw) = built
    a = sb.build(treated, clean, q, regions, fuel, dd, **kw)
    b = sb._per_host_design(treated, clean, q, regions, fuel, dd, **kw)
    ra, rb = oa.stacked_rows(a), oa.stacked_rows(b)
    assert len(ra) == 500 and ra.equals(rb)
    sa, sb_ = pf.form(a, pf.PER_HOST), pf.form(b, pf.PER_HOST)
    wa, wb = pf.operator(sa)["w"], pf.operator(sb_)["w"]
    assert np.array_equal(sa["X"], sb_["X"]) and np.abs(wa - wb).max() < 1e-12


def test_the_guard_test_fails_when_the_guard_is_broken(monkeypatch):
    """Deliberate break in the test process: the guard's grouping is made to find nothing. The refusal test must fail."""
    monkeypatch.setattr(sb, "hosts_sharing_a_cohort_and_a_cell", lambda d: [])
    with pytest.raises(BaseException) as e:
        test_build_refuses_a_set_in_which_two_hosts_share_a_cohort_and_a_cell_naming_them()
    assert e.type is not sb.OutsideTheAdoptedScope and "DID NOT RAISE" in str(e.value)


def test_the_label_says_adopted_and_says_the_scope():
    for text in (sb.LABEL, sb.OUTSIDE_THE_ADOPTED_SCOPE):
        assert "adopted by Joe on 2026-11-19 (D-111)" in text and "headline set at 2%" in text
        assert "share a cohort and a cell" in text and "outside this freeze" in text
    assert sb.LABEL.endswith(sb.NOT_VALIDATED)
    doc = sb.__doc__
    assert "The form and its scope, adopted by Joe on 2026-11-19 (D-111)" in doc
    assert "no extension is built for it" in doc and "890 stacked" in doc


def test_no_pipeline_module_calls_the_construction_without_the_refusal():
    """Only size_band_run.py names _per_host_design among pipeline/analysis/*.py (one folder, no recursion)."""
    folder = Path(sb.__file__).resolve().parent
    hits = sorted(p.name for p in folder.glob("*.py") if "_per_host_design" in p.read_text())
    assert hits == ["size_band_run.py"]


def test_no_function_reads_a_file():
    import ast
    src = Path(sb.__file__).read_text()
    tree = ast.parse(src)
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not {"load_outcomes", "read_listed_outcomes", "read_parquet", "read_csv"} & calls
    assert "data/blind" not in src and "availability" not in src
