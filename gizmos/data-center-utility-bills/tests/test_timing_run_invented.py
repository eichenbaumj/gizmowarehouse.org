"""The timing run (pipeline/analysis/timing_run.py) on invented quantities and invented outcomes only. No file under data/ is
read: the two frozen files' records are written out here as small frames.

The invented world: two market regions, "West" (AA to AD) and "East" (BA to BD). Seven hosts (cohorts 2013 to 2019), and
two hosts to add, 50:BA and 51:BB, at years 2015 and 2017. Thirty comparison utilities in each region. In East half the
comparison utilities grow 3% a year in residential customers and half shrink 2% a year, so which ten are nearest an added
host depends on the year size is read in (the guard that "matched at its own reference year" is tested).

The planted answer: unit effect + calendar-year effect + 0.02 x heating degree days + 0.04 on every host's rows from its
cohort year on (the added hosts' cohorts are their added years). With no noise the timing run's estimate is 0.04 exactly
(tolerance 1e-8).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import ownership  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import timing_run as tr  # noqa: E402
from test_matching_rules import table  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
WEST, EAST = ["AA", "AB", "AC", "AD"], ["BA", "BB", "BC", "BD"]
REGION_OF = {**{s: "West" for s in WEST}, **{s: "East" for s in EAST}, "CC": "South"}
COOP, PUB, IOU = "cooperative", "public", "investor_owned"
HDD_BETA = 0.02
EFFECT = 0.04
TOL = 1e-8
NONE = ps.UnknownLoad.none("invented data in a test")

# (id, state, residential customers in 2001, ownership, cohort)
SEVEN = [(1, "AA", 10_000, PUB, 2013), (2, "AB", 14_000, COOP, 2014), (3, "AC", 18_000, PUB, 2015),
         (4, "AD", 22_000, COOP, 2016), (5, "BC", 26_000, PUB, 2017), (6, "BD", 30_000, COOP, 2018),
         (7, "BC", 12_000, PUB, 2019)]
ADDED = {(50, "BA"): 2015, (51, "BB"): 2017}
ADDED_UNITS = [(50, "BA", 15_000, PUB), (51, "BB", 20_000, COOP)]
COMPS = ([(100 + i, WEST[i % 4], 8_000 + 500 * i, (COOP, PUB)[i % 2]) for i in range(30)]
         + [(200 + i, EAST[i % 4], 8_000 + 600 * i, (COOP, PUB)[i % 2]) for i in range(30)])


def growth(u: int) -> float:
    """East comparison utilities: even ids grow 3% a year, odd ids shrink 2% a year; everyone else is flat."""
    if 200 <= u < 300:
        return 1.03 if u % 2 == 0 else 0.98
    return 1.0


def size_in(u: int, size: float, y: int) -> float:
    return float(size) * growth(u) ** (y - 2001)


def world(seven=SEVEN, added_units=ADDED_UNITS, comps=COMPS, unusable=(), own_table=None, unknown=NONE):
    units = [h[:4] for h in seven] + list(added_units) + list(comps)
    states = sorted({u[1] for u in units})
    q = pd.DataFrame([(u, st, y, own, size_in(u, size, y), 1.0, True) for u, st, size, own in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    regions = pd.DataFrame([(u, st, y, REGION_OF[st]) for u, st, *_ in units for y in YEARS], columns=KEY + ["year", "region"])
    rng = np.random.default_rng(3)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in states for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    fuel = {s: i % 2 for i, s in enumerate(states)}
    gas = {s: 0.05 + 0.07 * i for i, s in enumerate(states)}
    treated = pd.DataFrame([(h[0], h[1], h[4]) for h in seven], columns=KEY + ["cohort"])
    clean = pd.DataFrame([c[:2] for c in comps], columns=KEY)
    usable = {(u, st, y) for u, st, *_ in units for y in YEARS} - set(unusable)
    kw = dict(ownership=table([]) if own_table is None else own_table, usable=usable, gas=gas,
              ownership_of=ps.ownership_classes(q), unknown_load=unknown, theta=0.02)
    return SimpleWorld(treated, clean, q, regions, fuel, dd, kw)


class SimpleWorld:
    def __init__(self, treated, clean, q, regions, fuel, dd, kw):
        self.treated, self.clean, self.q, self.regions, self.fuel, self.dd, self.kw = treated, clean, q, regions, fuel, dd, kw

    def build(self, added=ADDED, names=None):
        return tr.build(self.treated, self.clean, added, self.q, self.regions, self.fuel, self.dd, names=names, **self.kw)

    def headline(self):
        return dsg.build_with_rules(self.treated, self.clean, self.q, self.regions, self.fuel, self.dd, ps.HEADLINE_RULES,
                                    **self.kw)


def outcome(dd, seven=SEVEN, added=ADDED, added_units=ADDED_UNITS, comps=COMPS, noise=0.0, seed=7, effect=EFFECT):
    cohort = {(h[0], h[1]): h[4] for h in seven}
    cohort.update({tuple(k): v for k, v in added.items()})
    rng = np.random.default_rng(seed)
    year_fx = dict(zip(YEARS, rng.normal(0, 0.05, len(YEARS))))
    rows = []
    for u, st, *_ in [h[:4] for h in seven] + list(added_units) + list(comps):
        a = rng.normal(0, 0.2)
        for y in YEARS:
            v = a + year_fx[y] + HDD_BETA * float(dd.hdd[(st, y)]) + noise * rng.normal()
            g = cohort.get((u, st))
            if g is not None and y >= g:
                v += effect
            rows.append((u, st, y, v))
    return pd.DataFrame(rows, columns=KEY + ["year", "value"])


@pytest.fixture(scope="module")
def w():
    return world()


def _added(rec, lab):
    return next(a for a in rec["added_hosts"] if a["host"] == lab)


# ---- the planted answer ---------------------------------------------------------------------------------------------

def check_planted(w, added_for_the_build=ADDED):
    d, rec = w.build(added_for_the_build)
    r = tr.estimate_timing_run(d, rec, outcome(w.dd), "value")
    assert r["estimated"] and r["failure_in_words"] is None
    assert abs(r["result"]["headline"]["log_points"] - EFFECT) < TOL
    assert r["result"]["validation"] == oa.NOT_VALIDATED and r["label"] == tr.LABEL
    assert set(r["result"]["hosts_in_the_design"]) == {f"{h[0]}:{h[1]}" for h in SEVEN} | {"50:BA", "51:BB"}
    return r


def test_the_timing_run_recovers_the_planted_effect(w):
    r = check_planted(w)
    assert r["rank_test_before_any_fit"]["estimable"] is True


def test_the_planted_check_fails_when_the_added_hosts_take_the_wrong_years(w):
    """Deliberate break in the test process: build with each added host two years later than its year."""
    with pytest.raises(AssertionError):
        check_planted(w, {k: y + 2 for k, y in ADDED.items()})


# ---- matching at its own reference year; the seven unchanged ----------------------------------------------------------

def nearest_in(comps, host_size, y, k=ps.MATCH_K):
    sizes = np.log([size_in(u, s, y) for u, _, s, _ in comps])
    order = np.argsort(np.abs(sizes - np.log(host_size)), kind="stable")[:k]
    return [f"{comps[i][0]}:{comps[i][1]}" for i in order]


def test_each_added_host_is_matched_at_its_own_reference_year(w):
    d, rec = w.build()
    east = [c for c in COMPS if REGION_OF[c[1]] == "East"]
    for (u, st, size, _), (k, y) in zip(ADDED_UNITS, ADDED.items()):
        a = _added(rec, f"{u}:{st}")
        assert a["reference_year"] == y - 3 and a["no_anchoring_year"] == y and a["in_the_design"]
        got = [m["utility"] for m in a["matches"]]
        assert sorted(got) == sorted(nearest_in(east, size, y - 3))
        assert sorted(nearest_in(east, size, y - 3)) != sorted(nearest_in(east, size, 2016))    # the guard (as built: 2019)
        row = next(r for r in d.hosts.itertuples() if r.key == (u, st))
        assert [f"{m[0]}:{m[1]}" for m in row.match_keys] == got and int(row.cohort) == y


def test_the_seven_hosts_matches_are_byte_for_byte_unchanged(w):
    d, rec = w.build()
    base = w.headline()
    assert rec["original_hosts_unchanged"] is True and rec["original_hosts_differences"] == []
    a = json.dumps(tr._hosts_and_matches(base))
    b = json.dumps([x for x in tr._hosts_and_matches(d) if x[0] not in ("50:BA", "51:BB")])
    assert a == b
    assert rec["original_hosts"] == [f"{h[0]}:{h[1]}" for h in SEVEN]


def test_a_change_to_the_sevens_matches_is_found_and_the_run_is_refused(w):
    d, rec = w.build()
    base = w.headline()
    e = dsg.Design(d.hosts.copy(), d.windows, d.is_comp, list(d.dropped), d.region_names, d.unit_code, d.state_code, d.gas)
    e.hosts.at[0, "match_keys"] = list(reversed(e.hosts.at[0, "match_keys"]))
    same = tr.original_hosts_unchanged(base, e, ADDED)
    assert same["unchanged"] is False and same["differences"][0].startswith("1:AA")
    r = tr.estimate_timing_run(d, {**rec, "original_hosts_unchanged": False, "original_hosts_differences": same["differences"]},
                               outcome(w.dd), "value")
    assert r["estimated"] is False and "not the timing run R7 defines" in r["failure_in_words"]


# ---- an added host that fails a rule is named ----------------------------------------------------------------------------

def test_an_added_host_failing_the_support_rule_is_named_and_not_kept():
    """Host 52 in state CC, region South, with six comparison utilities there: fewer than ten in its region."""
    south = [(400 + i, "CC", 15_000 + 500 * i, COOP) for i in range(6)]
    ww = world(added_units=ADDED_UNITS + [(52, "CC", 16_000, PUB)], comps=COMPS + south)
    added = {**ADDED, (52, "CC"): 2016}
    d, rec = ww.build(added)
    a = _added(rec, "52:CC")
    assert a["in_the_design"] is False and a["rules"]["support_rule"]["keeps_its_place"] is False
    assert any(dsg.SUPPORT_RULE in x for x in a["named_as_failing"])
    assert a["rules"]["support_rule"]["pool_in_the_reference_year"] == 6
    assert sorted(m["utility"] for m in a["matches"]) == sorted(f"{u}:CC" for u, *_ in south)
    assert "52:CC" not in {oa._host_label(k) for k in d.hosts.key} and rec["original_hosts_unchanged"]
    assert _added(rec, "50:BA")["in_the_design"] is True


def test_an_added_host_without_a_full_usable_window_is_named_and_not_kept():
    ww = world(unusable={(51, "BB", 2016)})                       # 51:BB at 2017: window 2011 to 2020
    d, rec = ww.build()
    a = _added(rec, "51:BB")
    assert a["in_the_design"] is False and a["rules"]["full_window_usable"] == "fails: " + dsg.NOT_USABLE
    assert a["named_as_failing"] == [dsg.NOT_USABLE] and a["matches"] is None
    assert rec["original_hosts_unchanged"]


def test_an_added_host_reached_by_a_load_unknown_site_is_named():
    unknown = ps.UnknownLoad(frozenset({(50, "BA")}), {"2%": frozenset()}, "invented", 1)
    ww = world(unknown=unknown)
    d, rec = ww.build()
    a = _added(rec, "50:BA")
    assert a["in_the_design"] is False and a["rules"]["load_unknown_gate"] == "fails: " + ps.LOAD_UNKNOWN


def test_the_ownership_rules_apply_to_an_added_hosts_pool():
    """50:BA made investor-owned with a parent P. In East, 214:BC (investor-owned) has the same parent, and 216:BA
    (investor-owned) has no row: both are excluded from 50:BA's pool under every version of rule 2.2, and named."""
    comps = [(u, s, size, (IOU if u in (214, 216) else own)) for u, s, size, own in COMPS]
    added_units = [(50, "BA", 15_000, IOU), (51, "BB", 20_000, COOP)]
    t = table([{"utility_id_eia": 50, "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
               {"utility_id_eia": 214, "ultimate_parent": "P", "from_year": 2001, "to_year": 2025}])
    ww = world(added_units=added_units, comps=comps, own_table=t)
    d, rec = ww.build()
    ex = {x["utility"]: x["why"] for x in _added(rec, "50:BA")["rules"]["ownership_exclusions_on_its_pool"]}
    assert ex.get("214:BC") == ownership.SAME_PARENT and ex.get("216:BA") == ownership.NO_ROW
    got = [m["utility"] for m in _added(rec, "50:BA")["matches"]]
    assert "214:BC" not in got and "216:BA" not in got and len(got) == 10


def test_a_unit_with_a_row_for_part_of_the_window_is_barred_with_its_uncovered_years():
    """Rule 2.2 read year by year (D-107): 216:BA has a row from 2014 only, so in 50:BA's window (2009 to 2018) the years
    2009 to 2013 are uncovered and it is barred; the record gives those years."""
    comps = [(u, s, size, (IOU if u in (214, 216) else own)) for u, s, size, own in COMPS]
    added_units = [(50, "BA", 15_000, IOU), (51, "BB", 20_000, COOP)]
    t = table([{"utility_id_eia": 50, "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
               {"utility_id_eia": 214, "ultimate_parent": "Q", "from_year": 2001, "to_year": 2025},
               {"utility_id_eia": 216, "ultimate_parent": "R", "from_year": 2014, "to_year": 2025}])
    ww = world(added_units=added_units, comps=comps, own_table=t)
    _, rec = ww.build()
    ex = {x["utility"]: x for x in _added(rec, "50:BA")["rules"]["ownership_exclusions_on_its_pool"]}
    assert ex["216:BA"]["why"] == ownership.NO_ROW
    assert ex["216:BA"]["uncovered_window_years"] == [2009, 2010, 2011, 2012, 2013]
    assert ex["216:BA"]["no_row_covers_any_window_year"] is False
    assert "214:BC" not in ex


# ---- the years from the files ---------------------------------------------------------------------------------------------

RECORD = [{"utility": "15466:CO", "name": "Public Service Co of Colorado", "as_built": 2019, "no_anchoring": 2015},
          {"utility": "14006:OH", "name": "Ohio Power Co", "as_built": 2019, "no_anchoring": 2017}]


def csv_frame(y_co=2015, y_oh=2017):
    return pd.DataFrame([{"threshold": "2%", "utility_id_eia": 15466, "state": "CO", "first_crossing_no_anchoring": y_co},
                         {"threshold": "2%", "utility_id_eia": 14006, "state": "OH", "first_crossing_no_anchoring": y_oh},
                         {"threshold": "5%", "utility_id_eia": 15466, "state": "CO", "first_crossing_no_anchoring": 2099}])


def test_the_years_are_read_from_the_record_and_checked_against_the_csv():
    y = tr.no_anchoring_years(RECORD, csv_frame())
    assert y["years"] == {(15466, "CO"): 2015, (14006, "OH"): 2017} and y["files_agree"] is True
    assert y["differences_from_the_plan"] == []


def test_files_that_disagree_stop_in_words():
    with pytest.raises(tr.TimingRunRefused, match="disagree"):
        tr.no_anchoring_years(RECORD, csv_frame(y_oh=2016))


def test_a_year_the_plan_does_not_give_is_used_and_the_difference_reported():
    rec = [dict(RECORD[0]), {**RECORD[1], "no_anchoring": 2016}]
    y = tr.no_anchoring_years(rec, csv_frame(y_oh=2016))
    assert y["years"][(14006, "OH")] == 2016
    assert y["differences_from_the_plan"] == ["14006:OH (Ohio Power Co): the files give 2016, the plan says 2017"]


def test_a_record_without_the_plans_two_hosts_or_a_year_stops_in_words():
    with pytest.raises(tr.TimingRunRefused, match="the plan's timing run"):
        tr.no_anchoring_years(RECORD[:1], None)
    with pytest.raises(tr.TimingRunRefused, match="no no-anchoring year"):
        tr.no_anchoring_years([RECORD[0], {**RECORD[1], "no_anchoring": None}], None)


def test_a_host_already_in_the_set_or_among_the_comparisons_cannot_be_added(w):
    with pytest.raises(tr.TimingRunRefused, match="already a host"):
        w.build({(1, "AA"): 2012})
    with pytest.raises(tr.TimingRunRefused, match="comparison-eligible"):
        w.build({(200, "BA"): 2015})


def test_the_rank_test_comes_before_any_fit(w, monkeypatch):
    d, rec = w.build()
    calls = []
    monkeypatch.setattr(tr.influence, "estimable", lambda e, fc: {"estimable": False, "smallest_singular_value_ratio": 0.0,
                                                                     "hosts_with_no_matches": [], "hosts_with_zero_weight": []})
    monkeypatch.setattr(tr.oa, "estimate", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(tr.oa, "outcome_vector", lambda *a, **k: calls.append(2))
    r = tr.estimate_timing_run(d, rec, outcome(w.dd), "value")
    assert calls == [] and r["estimated"] is False and "rank test made before any fit" in r["failure_in_words"]


def test_only_main_reads_a_file():
    import ast
    src = Path(tr.__file__).read_text()
    tree = ast.parse(src)
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name != "main"]:
        calls = {c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", None)
                 for c in ast.walk(fn) if isinstance(c, ast.Call)}
        assert not {"load_outcomes", "read_listed_outcomes", "read_parquet", "read_csv", "read_text", "load"} & calls, fn.name
    assert "data/blind" not in src and "availability" not in src
