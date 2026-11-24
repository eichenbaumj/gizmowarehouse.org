"""Run fingerprints (D-58 rule 10, widened by D-59 item 5): design inputs, code version, assumptions, settings, seeds.

The same inputs give the same fingerprint; changing one host, one match, one usable unit-year, one regressor or one seed
each changes it. Invented quantities only.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, influence  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import COOP, FUEL, YEARS, table, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
HOSTS = [(1, "AA", 10_000, COOP), (2, "BB", 12_000, COOP)]


def comps():
    states = ["AA", "AB", "BB", "BC"]
    return [(10 + i, states[i % 4], 10_050 + 100 * i, COOP) for i in range(16)]


def usable_all(units):
    return {(u, st, y) for u, st, *_ in units for y in YEARS}


def build(hosts=HOSTS, cs=None, usable=None, gas=GAS, dd_bump=0.0):
    cs = comps() if cs is None else cs
    treated, clean, q, regions, dd = world(hosts, cs)
    if dd_bump:
        dd = dd.copy()
        dd.loc[("AA", 2012), "hdd"] += dd_bump                          # a year inside the window
    usable = usable_all(list(hosts) + cs) if usable is None else usable
    d = design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, ownership=table([]), usable=usable, gas=gas,
                                 unknown_load=ps.UnknownLoad.none("invented data: no load-unknown site"))
    return d, usable


def fp(d, usable, seeds=(1, 2), assumptions=None, settings=None):
    return design.run_fingerprint(d, rules=ps.HEADLINE_RULES, usable=usable, assumptions=assumptions or {"draws": 10},
                                  settings=settings or {"boot": 9}, seeds=list(seeds))


def test_the_same_inputs_give_the_same_fingerprint():
    d1, u1 = build()
    d2, u2 = build()
    a, b = fp(d1, u1), fp(d2, u2)
    assert a == b and len(a["sha256"]) == 64
    assert set(a["of"]) == {"design_inputs", "rules", "code_version", "assumptions", "settings", "seeds"}
    assert fp(d1, set(sorted(u1, reverse=True)))["sha256"] == a["sha256"]          # order of a set does not matter


def test_building_the_fingerprint_leaves_the_windows_outcomes_alone():
    d, u = build()
    before = {g: w.y.copy() for g, w in d.windows.items()}
    fp(d, u)
    assert all(np.array_equal(before[g], w.y) for g, w in d.windows.items())


def test_one_host_more_changes_it():
    d, u = build()
    e, v = build(hosts=HOSTS + [(3, "AB", 11_000, COOP)])
    assert fp(d, u)["of"]["design_inputs"] != fp(e, v)["of"]["design_inputs"]


def test_one_match_changes_it():
    d, u = build()
    e = influence.leave_out(d, {tuple(d.hosts.match_keys.iloc[0][3])})
    assert fp(d, u)["sha256"] != fp(e, u)["sha256"]


def test_one_usable_unit_year_changes_it():
    d, u = build()
    u2 = set(u) - {(10, "AA", 2003)}                                   # outside every window: the design is the same, the input is not
    assert fp(d, u)["sha256"] != fp(d, u2)["sha256"]


def test_one_regressor_changes_it():
    d, u = build()
    e, _ = build(dd_bump=0.25)                                         # one state-year's degree days
    assert fp(d, u)["of"]["design_inputs"] != fp(e, u)["of"]["design_inputs"]
    g, _ = build(gas={**GAS, "BC": 0.81})                              # one state's gas share
    assert fp(d, u)["sha256"] != fp(g, u)["sha256"]
    cat = design.run_fingerprint(d, rules=ps.CATEGORICAL_FUEL, usable=u, assumptions={"draws": 10}, settings={"boot": 9}, seeds=[1, 2])
    assert cat["of"]["design_inputs"] != fp(d, u)["of"]["design_inputs"]  # the fuel control is a regressor


def test_one_seed_assumption_or_setting_changes_it():
    d, u = build()
    base = fp(d, u)
    assert fp(d, u, seeds=(1, 3))["sha256"] != base["sha256"]
    assert fp(d, u, assumptions={"draws": 11})["sha256"] != base["sha256"]
    assert fp(d, u, settings={"boot": 10})["sha256"] != base["sha256"]


def test_the_code_version_is_the_hash_of_the_module_files(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    one = design.code_version(("a.py",), tmp_path)
    (tmp_path / "a.py").write_text("x = 2\n")
    assert design.code_version(("a.py",), tmp_path) != one
    assert "pipeline/analysis/usable_flag.py" in design.CODE_FILES and "pipeline/analysis/estimator.py" in design.CODE_FILES


def test_the_clusters_are_part_of_it():
    d, u = build()
    inputs = design.design_inputs(d, ps.GAS_SHARE, u)
    assert inputs["clusters"] and set(inputs["clusters"]) <= {"AA", "AB", "BB", "BC"}


def test_every_expensive_run_writes_one():
    assert "run_fingerprint(" in inspect.getsource(design.main)
    assert "run_fingerprint(" in inspect.getsource(ic.main)
    for fn in (ps.run_new_hosts, ps.run_size_check):
        assert '"fingerprint"' in inspect.getsource(fn) and "_fingerprint(" in inspect.getsource(fn)
