"""The later-start sensitivity (pipeline/facilities/later_start.py) on made-up inventories."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stepd_world as W  # noqa: E402
from pipeline.facilities import later_start as ls  # noqa: E402

BASE = {(1, "AA"): 10.0, (2, "AA"): 1000.0}


def site(fid, mw, year, utility=1, **kw):
    return {"fid": fid, "state": "AA", "mw": mw, "year": year, "utility": utility, **kw}


def test_every_permit_dated_row_moves_and_nothing_else():
    inp = W.make([site("g", 5, 2015), site("small", 0.5, 2012), site("p", 5, 2010, date_basis="verified_public_source")], BASE)
    ent, bad, patch = ls.shifted(inp, [], 3, {}, "AA")
    got = {c["fid"]: c["convention"] for c in ent}
    assert got == {"g": 2018, "small": 2015}                       # no size floor; a sourced year does not move
    assert bad == [] and patch == {}


def test_a_permit_based_convention_moves_and_an_evidence_end_holds_and_is_listed():
    inp = W.make([site("a", 20, 2015, first_permit_year=2014), site("b", 20, 2015, first_permit_year=2014)], BASE)
    entries = [W.date("a", 2012, 2015, 2015), W.date("b", 2012, 2015, 2015, ends="evidence")]
    ent, bad, _ = ls.shifted(inp, entries, 3, {}, "AA")
    by = {c["fid"]: c for c in ent}
    assert by["a"]["convention"] == 2018 and by["a"]["latest"] == 2018
    assert by["b"]["convention"] == 2015 and by["b"]["latest"] == 2015
    assert {(x["site"], x["field"]) for x in bad} == {("b", "convention"), ("b", "latest")}


def test_an_operating_by_record_bounds_the_shift():
    inp = W.make([site("a", 20, 2015, first_permit_year=2014)], BASE)
    ev = pd.DataFrame({"site": ["a"], "kind_d61": ["operating_by"], "year": [2016]})
    ent, bad, _ = ls.shifted(inp, [W.date("a", 2012, 2015, 2015)], 5, ls.evidence_bounds(ev), "AA")
    assert ent[0]["convention"] == 2016 and bad and bad[0]["held_at"] == 2016


def test_known_phases_and_provisional_conventions_do_not_move():
    inp = W.make([site("ph", 20, 2010), site("y", 20, 2015, first_permit_year=2014)], BASE, phases={"ph": [(2010, 0.5), (2015, 1.0)]})
    ent, _, _ = ls.shifted(inp, [W.date("y", 2012, 2015, 2015, convention_is="provisional")], 3, {}, "AA")
    assert [c["fid"] for c in ent] == ["y"] and ent[0]["convention"] == 2015


def test_a_capacity_splits_late_year_moves():
    inp = W.make([site("a", 20, 2019, first_permit_year=2018)], BASE)
    entries = [W.date("a", 2011, 2019, None), {"fid": "a", "kind": "capacity_split", "first_share": 0.5, "rest_earliest": 2011}]
    ent, _, patch = ls.shifted(inp, entries, 1, {}, "AA")
    assert patch == {"a": 2020.0}
    assert {c["fid"]: c.get("latest") for c in ent if c["kind"] == "date"} == {"a": 2020}


def test_a_start_pushed_past_2025_carries_no_load_and_weakens_the_place():
    inp = W.make([site("a", 20, 2022)], BASE)
    res = ls.run(inp, [], shifts=(5,), thetas=(0.02,), states=["AA"])
    u = next(x for x in res["shifts"][5]["utilities"] if x["utility"] == "1:AA")
    assert u["primary_keeps"] is True and u["keeps_under_the_later_start"] is False and u["weakened"]
    assert u["range"]["earliest_crossing"] is None                # no load in the panel


def test_a_shift_of_zero_reproduces_the_primary():
    inp = W.make([site("a", 20, 2015), site("b", 30, 2023, utility=2)], BASE)
    res = ls.run(inp, [W.date("a", 2014, 2015, 2015)], shifts=(0,), thetas=(0.02,), states=["AA"])
    for u in res["shifts"][0]["utilities"]:
        assert u["keeps_under_the_later_start"] == u["primary_keeps"]
    f = res["shifts"][0]["factor_by_state"]["AA"]
    assert f["primary"] == f["shifted"]


def test_a_later_start_moves_the_factor_and_another_utility():
    sites = [site("x", 9.0, 2010), site("late", 30.0, 2021, utility=2)]
    inp = W.make(sites, BASE, epri={"AA": 39 * 8.76 / 1000})
    res = ls.run(inp, [], shifts=(3,), thetas=(0.02,), states=["AA"])
    f = res["shifts"][3]["factor_by_state"]["AA"]
    assert f["shifted"] > f["primary"]
    u = next(x for x in res["shifts"][3]["utilities"] if x["utility"] == "1:AA")
    assert u["weakened"]
