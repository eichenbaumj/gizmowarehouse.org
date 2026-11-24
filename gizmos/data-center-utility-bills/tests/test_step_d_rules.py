"""Step D: the opt-in rules become the defaults (HANDOVER.md D.2; D-54 ruling 2; D-58 rules 2.2, 2.3, 6.3; D-94; D-95).

Invented quantities only. The old behaviours stay reachable by a labelled variant, never by omission.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, ownership  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import COHORT, COOP, FUEL, IOU, PUBLIC, YEARS, keys_of, ladder, table, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
NONE = ps.UnknownLoad.none("invented data: no load-unknown site")       # D-96's input is required; here there is none


def header_only(tmp_path):
    path = tmp_path / "ownership.csv"
    path.write_text(",".join(ownership.COLUMNS) + "\n")
    return ownership.load(path)


def all_usable(units):
    return {(u, st, y) for u, st, *_ in units for y in YEARS}


def headline(treated, clean, q, regions, dd, t, usable, rules=ps.HEADLINE_RULES, **kw):
    return design.build_with_rules(treated, clean, q, regions, FUEL, dd, rules, ownership=t, usable=usable, gas=GAS, unknown_load=NONE, **kw)


# ---- the defaults ----------------------------------------------------------------------------------

def test_the_headline_rules_are_the_default_everywhere():
    r = ps.HEADLINE_RULES
    assert (r.ownership, r.usable, r.support, r.fuel_control) == ("table", "flag", "applied", ps.GAS_SHARE)
    assert inspect.signature(design.build_with_rules).parameters["rules"].default is r
    for fn in (ps.run_new_hosts, ps.run_size_check):
        assert inspect.signature(fn).parameters["rules"].default is r
    for fn in (ps.assemble, ps.one_draw, ic.fixed_parts, ic.implied_weights, ic.absorbed_hosts):
        assert inspect.signature(fn).parameters["fuel_control"].default == ps.GAS_SHARE
    assert ps.rules_from_argv([]) is r and ps.rules_from_argv(["x", "--rules=sensitivity_no_fuel_control"]) is ps.NO_FUEL_CONTROL
    with pytest.raises(SystemExit):
        ps.rules_from_argv(["--rules=nonsense"])


def test_every_old_behaviour_is_a_labelled_variant():
    v = ps.RULE_VARIANTS
    assert v["sensitivity_affiliates_readmitted"].ownership == "affiliates_readmitted"
    assert v["sensitivity_categorical_fuel_control"].fuel_control == ps.CATEGORICAL
    assert v["sensitivity_no_fuel_control"].fuel_control == ps.NO_FUEL
    before = v["as_built_before_step_d"]
    assert (before.ownership, before.usable, before.support, before.fuel_control) == ("off", "positive_sales", "reported_only", ps.CATEGORICAL)
    with pytest.raises(ValueError):
        ps.Rules("bad", fuel_control="something_else")


@pytest.mark.parametrize("missing", ["ownership", "usable", "gas"])
def test_a_rule_without_its_input_stops_rather_than_falling_back(missing):
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, COOP)], ladder(10, 12))
    kw = {"ownership": table([]), "usable": all_usable([(1, "AA", 0, 0)] + ladder(10, 12)), "gas": GAS, "unknown_load": NONE}
    kw[missing] = None
    with pytest.raises(ValueError, match="pass"):
        design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, **kw)


def test_the_variant_before_step_d_reproduces_the_bare_build():
    comps = [(1, "BB", 10_000, COOP)] + ladder(10, 12)
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, COOP)], comps)
    old = design.build(treated, clean, q, regions, FUEL, dd)
    same = design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.AS_BEFORE_STEP_D, unknown_load=NONE)
    pd.testing.assert_frame_equal(old.hosts, same.hosts)
    assert (1, "BB") in keys_of(same)                                 # nothing excluded before step D


# ---- ownership by default ----------------------------------------------------------------------------

def test_by_default_a_unit_of_the_hosts_own_utility_is_never_matched(tmp_path):
    comps = [(1, "BB", 10_000, COOP)] + ladder(10, 12)
    units = [(1, "AA", 10_000, COOP)] + comps
    treated, clean, q, regions, dd = world(units[:1], comps)
    d = headline(treated, clean, q, regions, dd, header_only(tmp_path), all_usable(units))
    assert (1, "BB") not in keys_of(d) and keys_of(d) == [(10 + i, "AA") for i in range(10)]


def test_by_default_an_investor_owned_candidate_with_no_row_is_out_for_an_investor_owned_host_and_named(tmp_path):
    host = (1, "AA", 10_000, IOU)
    comps = [(40, "AA", 10_010, IOU), (41, "AA", 10_020, PUBLIC)] + ladder(60, 12)
    treated, clean, q, regions, dd = world([host], comps)
    t = header_only(tmp_path)                                          # the table is a header: no IOU can be shown unaffiliated
    d = headline(treated, clean, q, regions, dd, t, all_usable([host] + comps))
    assert (40, "AA") not in keys_of(d) and keys_of(d)[0] == (41, "AA")
    assert {"utility": "40:AA", "why": ownership.NO_ROW} in d.hosts.excluded_from_its_pool.iloc[0]
    own = ps.ownership_classes(q)
    named = design.investor_owned_without_rows(t, [((1, "AA"), "host"), ((40, "AA"), "comparison"), ((41, "AA"), "comparison"),
                                                    ((60, "AA"), "comparison")], own, pd.Series({(40, "AA"): "Forty Power"}))
    assert [(x["utility"], x["role"]) for x in named] == [("1:AA", "host"), ("40:AA", "comparison")]
    assert named[1]["name"] == "Forty Power" and "not eligible" in named[1]["consequence"]


def test_a_row_for_the_unit_or_for_every_state_of_its_id_takes_it_off_the_no_row_list():
    t = table([{"utility_id_eia": 40, "state": "AA", "ultimate_parent": "Z", "from_year": 2001, "to_year": 2025},
               {"utility_id_eia": 41, "state": "", "ultimate_parent": "Y", "from_year": 2001, "to_year": 2025}])
    own = {(40, "AA"): IOU, (41, "BB"): IOU, (42, "AA"): IOU}
    named = design.investor_owned_without_rows(t, [((40, "AA"), "comparison"), ((41, "BB"), "comparison"), ((42, "AA"), "comparison")], own)
    assert [x["utility"] for x in named] == ["42:AA"]


def test_affiliates_readmitted_is_the_labelled_sensitivity_and_keeps_the_own_utility_out():
    host = (1, "AA", 10_000, IOU)
    comps = [(1, "BB", 10_000, IOU), (20, "AA", 10_010, IOU)] + ladder(30, 12, own=IOU)
    treated, clean, q, regions, dd = world([host], comps)
    rows = [{"utility_id_eia": 1, "state": "", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
            {"utility_id_eia": 20, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025}]
    rows += [{"utility_id_eia": 30 + i, "state": "", "ultimate_parent": f"O{i}", "from_year": 2001, "to_year": 2025} for i in range(12)]
    t = table(rows)
    usable = all_usable([host] + comps)
    d = headline(treated, clean, q, regions, dd, t, usable)
    assert (20, "AA") not in keys_of(d) and (1, "BB") not in keys_of(d)
    s = headline(treated, clean, q, regions, dd, t, usable, rules=ps.AFFILIATES_READMITTED)
    assert keys_of(s)[0] == (20, "AA") and (1, "BB") not in keys_of(s)


# ---- full-window eligibility from the flag by default ---------------------------------------------

def test_by_default_a_host_without_a_full_usable_window_is_dropped_by_name(tmp_path):
    hosts = [(1, "AA", 10_000, COOP), (2, "AA", 10_000, COOP)]
    comps = ladder(10, 12)
    treated, clean, q, regions, dd = world(hosts, comps)
    usable = all_usable(hosts + comps) - {(2, "AA", 2010), (10, "AA", 2012)}
    d = headline(treated, clean, q, regions, dd, header_only(tmp_path), usable)
    assert list(d.hosts.key) == [(1, "AA")] and (10, "AA") not in keys_of(d)
    assert {"utility": "2:AA", "cohort": COHORT, "why": design.NOT_USABLE} in d.dropped


# ---- the support rule applied by default -----------------------------------------------------------

def test_by_default_a_host_that_does_not_keep_its_place_leaves_the_estimate_named(tmp_path):
    hosts = [(1, "AA", 10_000, COOP), (2, "BB", 30_000, COOP)]
    comps = ladder(10, 9) + ladder(40, 12, state="BB", start=30_050)
    region = lambda key, year: "East" if key[1] == "BB" else "West"  # noqa: E731
    treated, clean, q, regions, dd = world(hosts, comps, region=region)
    usable = all_usable(hosts + comps)
    d = headline(treated, clean, q, regions, dd, header_only(tmp_path), usable)
    assert list(d.hosts.key) == [(2, "BB")]
    gone = [x for x in d.dropped if x["utility"] == "1:AA"]
    assert gone and design.SUPPORT_RULE in gone[0]["why"] and "9 eligible in its region" in gone[0]["why"]
    assert not d.support_table.set_index("utility_id_eia").keeps_its_place[1]
    kept = design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.replace(ps.HEADLINE_RULES, label="report_only", support="reported_only"),
                                   ownership=header_only(tmp_path), usable=usable, gas=GAS, unknown_load=NONE)
    assert set(kept.hosts.key) == {(1, "AA"), (2, "BB")}               # reported only: moves no one


def test_apply_support_rule_does_not_change_its_input():
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, COOP)], ladder(10, 9))
    d = design.build(treated, clean, q, regions, FUEL, dd)
    e, rule = design.apply_support_rule(d)
    assert len(d.hosts) == 1 and len(e.hosts) == 0 and not rule.keeps_its_place.iloc[0] and d.dropped == []


# ---- the simulation's defaults -------------------------------------------------------------------------

def test_exclusions_apply_the_ownership_rules_to_the_stand_in_as_a_host(tmp_path):
    stand_in = (1, "AA", 10_000, IOU)
    comps = [(1, "BB", 10_005, COOP), (20, "AA", 10_010, IOU), (21, "AA", 10_015, IOU), (22, "AA", 10_020, COOP)] + ladder(30, 10)
    treated, clean, q, regions, dd = world([], [stand_in] + comps)
    units = clean[ps.KEY].drop_duplicates()
    unit_code = {k: i for i, k in enumerate(map(tuple, units.values))}
    state_code = {s: i for i, s in enumerate(sorted(units.state.unique()))}
    template = q[ps.KEY + ["year"]].assign(log_price=0.0)
    windows = ps.build_windows([COHORT], template, q, regions, FUEL, dd, unit_code, state_code)
    w = windows[COHORT]
    j = w.keys.index((1, "AA"))
    t = table([{"utility_id_eia": 1, "state": "", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
               {"utility_id_eia": 20, "state": "AA", "ultimate_parent": "P", "from_year": 2012, "to_year": 2012}])
    own = ps.ownership_classes(q)
    out = {w.keys[i] for i in ps.Exclusions(windows, t, own)(COHORT, j)}
    assert out == {(1, "BB"), (20, "AA"), (21, "AA")}                  # own utility; same parent in 2012; IOU with no row
    readmit = {w.keys[i] for i in ps.Exclusions(windows, t, own, affiliates_included=True)(COHORT, j)}
    assert readmit == {(1, "BB")}
    blocks, lost = ps.build_blocks(windows, [(COHORT, j, 0)], "nearest_in_size", len(unit_code), excluded=ps.Exclusions(windows, t, own))
    got = {w.keys[i] for i in blocks[0][2]}
    assert lost == 0 and not got & {(1, "BB"), (20, "AA"), (21, "AA")} and (22, "AA") in got and len(got) == ps.MATCH_K
    import pickle
    assert pickle.loads(pickle.dumps(ps.Exclusions(windows, t, own)))(COHORT, j) == ps.Exclusions(windows, t, own)(COHORT, j)


def test_real_hosts_reads_the_usable_set_when_given():
    hosts = [(1, "AA", 10_000, COOP), (2, "AA", 12_000, COOP)]
    treated, clean, q, regions, dd = world(hosts, ladder(10, 3))
    every = ps.real_hosts(treated, q, regions, FUEL)
    assert set(every.key) == {(1, "AA"), (2, "AA")}
    usable = all_usable(hosts) - {(2, "AA", 2011)}
    assert set(ps.real_hosts(treated, q, regions, FUEL, usable).key) == {(1, "AA")}


def test_outcome_rows_take_the_usable_set_from_step_d():
    p = pd.DataFrame({"utility_id_eia": [1, 1, 2], "state": ["AA"] * 3, "year": [2010, 2011, 2010],
                      "meets_size_floor": [True, True, False], "res_price": [0.1, 0.1, 0.1]})
    assert len(ps.outcome_rows(p, None)) == 2
    assert list(ps.outcome_rows(p, {(1, "AA", 2011), (2, "AA", 2010)}).year) == [2011, 2010]


def test_rule_inputs_returns_none_for_what_the_rules_do_not_use():
    q = pd.DataFrame({"utility_id_eia": [1], "state": ["AA"], "year": [2010], "ownership": [COOP]})
    o, u, g = ps.rule_inputs(ps.AS_BEFORE_STEP_D, q, ownership="x", usable={1}, gas={"AA": 0.1})
    assert (o, u, g) == (None, None, None)
    o, u, g = ps.rule_inputs(ps.HEADLINE_RULES, q, ownership="x", usable={1}, gas={"AA": 0.1})
    assert (o, u, g) == ("x", {1}, {"AA": 0.1})


def test_simulation_hosts_are_the_hosts_the_design_keeps(tmp_path):
    hosts = [(1, "AA", 10_000, COOP), (2, "AA", 10_000, COOP)]
    comps = ladder(10, 12)
    treated, clean, q, regions, dd = world(hosts, comps)
    usable = all_usable(hosts + comps) - {(2, "AA", 2013)}
    kept, d = ps.simulation_hosts(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, header_only(tmp_path), usable, GAS, NONE)
    assert list(zip(kept.utility_id_eia, kept.state)) == [(1, "AA")]
    assert d.dropped[0]["utility"] == "2:AA"


def test_the_main_entry_points_build_through_the_rules():
    """design.main, the inference check and the simulation call build_with_rules (or simulation_hosts), never a bare build."""
    for mod, fn in ((design, "main"), (ic, "main")):
        src = inspect.getsource(getattr(mod, fn))
        assert "build_with_rules(" in src and "design.build(" not in src and " build(treated" not in src
    for fn in (ps.run_new_hosts, ps.run_size_check):
        src = inspect.getsource(fn)
        assert "simulation_hosts(" in src and "Exclusions(" in src and "rule_inputs(" in src
    src = inspect.getsource(ps.main)
    assert "rules_from_argv" in src and "**rk" in src


def test_the_simulation_threads_exclusions_and_the_fuel_control_into_each_draw():
    for chunk in (ps._host_chunk, ps._size_chunk, ps._shortcut_chunk):
        src = inspect.getsource(chunk)
        assert 'excluded=c.get("excluded")' in src and "fuel_control" in src and "gas" in src
    assert np.array_equal(ps.headline_combo(len(ps.W_HEAD) + 2), ps.COMBO)
