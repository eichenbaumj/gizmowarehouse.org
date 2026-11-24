"""Unknown-load utilities are never settled from the frame (D-96). Invented inputs only.

The owner's ruling: "Do not let the incomplete inventory frame silently determine comparisons, exposure measures or
simulation price access. ... Carry unsettled second-number doses to step F with the specified timing cases."
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import COOP, FUEL, YEARS, keys_of, ladder, table, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}


def write_unknown(frozen: Path, every, decided=None, against=None):
    frozen.mkdir(parents=True, exist_ok=True)
    (frozen / ps.UNKNOWN_LOAD_FILE).write_text(json.dumps({
        "what_this_is": "invented", "sites": [{"fid": "x1", "state": "AA"}], "utilities_directly": every,
        "utilities_through_the_state_factor": [], "every_affected_utility": every, "fingerprint": "f"}))
    if decided is not None:
        (frozen / "treatment_bounds.json").write_text(json.dumps({
            "step_d": {"unknown_load_affected_utilities": every if against is None else against},
            "thresholds": {t: {"lists": {ps.DECIDED_LIST: v, "unknown_load_unsettled": []}} for t, v in decided.items()}}))


def headline(treated, clean, q, regions, dd, units, unknown, theta=0.02):
    usable = {(u, st, y) for u, st, *_ in units for y in YEARS}
    return design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, ownership=table([]), usable=usable,
                                   gas=GAS, unknown_load=unknown, theta=theta)


# ---- the loader --------------------------------------------------------------------------------------------------

def test_an_absent_file_on_a_rebuilt_inventory_stops_in_words(tmp_path):
    with pytest.raises(ps.UnknownLoadMissing, match="missing on a rebuilt inventory"):
        ps.load_unknown_load(tmp_path, rebuilt=True)
    none = ps.load_unknown_load(tmp_path, rebuilt=False)
    assert none.affected == frozenset() and "before step D" in none.source


def test_whether_the_inventory_is_rebuilt_is_read_from_the_facilities_columns(tmp_path):
    with pytest.raises(ps.UnknownLoadMissing, match="facilities.parquet is missing"):
        ps.rebuilt_inventory(tmp_path)
    pq.write_table(pa.table({"fid": ["a"]}), tmp_path / "facilities.parquet")
    assert ps.rebuilt_inventory(tmp_path) is False
    pq.write_table(pa.table({"fid": ["a"], "date_rule": ["x"]}), tmp_path / "facilities.parquet")
    assert ps.rebuilt_inventory(tmp_path) is True
    with pytest.raises(ps.UnknownLoadMissing):                       # rebuilt, and no unknown-load file beside it
        ps.load_unknown_load(tmp_path / "frozen", interim=tmp_path)


def test_a_malformed_file_stops(tmp_path):
    tmp_path.joinpath(ps.UNKNOWN_LOAD_FILE).write_text(json.dumps({"every_affected_utility": [12]}))
    with pytest.raises(ps.UnknownLoadMissing, match="well-formed"):
        ps.load_unknown_load(tmp_path, rebuilt=True)


def test_verdicts_are_taken_only_from_bounds_written_against_the_same_list(tmp_path):
    write_unknown(tmp_path, ["11:AA", "12:AA"], decided={"2%": ["11:AA"], "5%": []})
    u = ps.load_unknown_load(tmp_path, rebuilt=True)
    assert u.affected == {(11, "AA"), (12, "AA")} and u.settled((11, "AA"), 0.02) and not u.settled((11, "AA"), 0.05)
    assert not u.settled((12, "AA"), 0.02) and u.settled((99, "AA"), 0.02)
    write_unknown(tmp_path, ["11:AA", "12:AA"], decided={"2%": ["11:AA"]}, against=["11:AA"])     # stale bounds
    assert not ps.load_unknown_load(tmp_path, rebuilt=True).settled((11, "AA"), 0.02)


# ---- the design ----------------------------------------------------------------------------------------------------

def test_an_unknown_load_utility_is_never_a_comparison_on_a_frame_share_alone(tmp_path):
    host = (1, "AA", 10_000, COOP)
    comps = [(11, "AA", 10_001, COOP)] + ladder(20, 12)                # 11 is the nearest in size and clean on the frame
    treated, clean, q, regions, dd = world([host], comps)
    write_unknown(tmp_path, ["11:AA"], decided={"2%": [], "5%": ["11:AA"]})
    u = ps.load_unknown_load(tmp_path, rebuilt=True)
    d = headline(treated, clean, q, regions, dd, [host] + comps, u)
    assert (11, "AA") not in keys_of(d) and len(keys_of(d)) == 10
    assert d.load_unknown_excluded == [{"utility": "11:AA", "role": "comparison", "why": ps.LOAD_UNKNOWN}]
    assert ps.LOAD_UNKNOWN == "load unknown (D-96): dose not settled, carried to step F"
    decided = headline(treated, clean, q, regions, dd, [host] + comps, u, theta=0.05)              # the enumeration settled it at 5%
    assert keys_of(decided)[0] == (11, "AA") and decided.load_unknown_excluded == []


def test_an_unknown_load_host_is_dropped_by_name(tmp_path):
    hosts = [(1, "AA", 10_000, COOP), (2, "AA", 10_000, COOP)]
    comps = ladder(20, 12)
    treated, clean, q, regions, dd = world(hosts, comps)
    write_unknown(tmp_path, ["2:AA"], decided={"2%": []})
    d = headline(treated, clean, q, regions, dd, hosts + comps, ps.load_unknown_load(tmp_path, rebuilt=True))
    assert list(d.hosts.key) == [(1, "AA")]
    assert {"utility": "2:AA", "cohort": None, "why": ps.LOAD_UNKNOWN} in d.dropped


def test_the_input_is_required():
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, COOP)], ladder(20, 12))
    with pytest.raises(ValueError, match="unknown_load"):
        design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.AS_BEFORE_STEP_D)


# ---- the second number -------------------------------------------------------------------------------------------

def second_number_world():
    units = [(1, "AA", 10_000, COOP), (2, "AB", 10_000, COOP)] + ladder(20, 12) + ladder(40, 12, state="AB")
    treated, clean, q, regions, dd = world([], units)
    q["utility_name"] = [f"U{u}" for u in q.utility_id_eia]
    dose = pd.DataFrame([(u, st, y, (0.02 * (y >= 2015)) if u in (1, 2) else 0.0) for u, st, *_ in units for y in YEARS],
                        columns=ps.KEY + ["year", "dose"])
    return q, dose, regions, clean


def test_the_second_numbers_leverage_names_an_unknown_load_utility_as_carried_to_step_f(tmp_path):
    q, dose, regions, _ = second_number_world()
    write_unknown(tmp_path, ["2:AB", "25:AA"], decided={"2%": ["25:AA"]})            # decided on place still has no dose
    u = ps.load_unknown_load(tmp_path, rebuilt=True)
    out, t = ic.second_number_leverage(q, dose, regions, u)
    assert out["carried_to_step_f"] == ["25:AA", "2:AB"] and out["carried_to_step_f_why"] == ps.LOAD_UNKNOWN
    assert not {(2, "AB"), (25, "AA")} & set(zip(t.utility_id_eia, t.state))
    with pytest.raises(ValueError, match="unknown_load"):
        ic.second_number_leverage(q, dose, regions)


def test_the_second_number_simulation_computes_no_dose_for_them_and_names_them(tmp_path):
    q, dose, regions, clean = second_number_world()
    clean = clean[~clean.utility_id_eia.isin([1, 2])]
    rng = np.random.default_rng(0)
    prices = q[ps.KEY + ["year"]].assign(res_price=np.exp(rng.normal(-2, 0.05, len(q))))
    write_unknown(tmp_path, ["2:AB", "25:AA"])
    u = ps.load_unknown_load(tmp_path, rebuilt=True)
    out = ps.run_second_number(q, dose, clean, regions, prices, (1, 2), draws=2, boot=9, unknown_load=u)
    for name in ("long_difference", "panel"):
        assert out[name]["carried_to_step_f"] == ["25:AA", "2:AB"]
        assert out[name]["utilities_with_material_load_given_a_stand_in"] == 1      # host 1 only; 2 has no settled dose
    with pytest.raises(ValueError, match="unknown_load"):
        ps.run_second_number(q, dose, clean, regions, prices, (1, 2), draws=1, boot=9)


def test_the_simulation_takes_no_stand_in_or_comparison_from_an_unknown_load_utility(tmp_path):
    host = (1, "AA", 10_000, COOP)
    comps = [(11, "AA", 10_001, COOP)] + ladder(20, 14)
    treated, clean, q, regions, dd = world([host], comps)
    write_unknown(tmp_path, ["11:AA"], decided={"2%": []})
    u = ps.load_unknown_load(tmp_path, rebuilt=True)
    rng = np.random.default_rng(0)
    prices = q[ps.KEY + ["year"]].assign(res_price=np.exp(rng.normal(-2, 0.05, len(q))))
    q["utility_name"] = "x"
    usable = {(a, st, y) for a, st, *_ in [host] + comps for y in YEARS}
    out = ps.run_new_hosts("t", treated, clean, q, regions, FUEL, dd, prices, {(1, "AA"): np.array([0])}, (1, 2), draws=2, boot=9,
                           ownership=table([]), usable=usable, gas=GAS, unknown_load=u)
    assert {"utility": "11:AA", "role": "comparison", "why": ps.LOAD_UNKNOWN} in out["load_unknown_excluded"]
    with pytest.raises(ValueError, match="unknown_load"):
        ps.run_size_check("t", treated, clean, q, regions, FUEL, dd, (1, 3), datasets=1, boot=9, ownership=table([]),
                          usable=usable, gas=GAS)


def test_every_main_loads_the_unknown_load_file():
    import inspect
    for fn in (design.main, ic.main, ps.main, ps.run_added):
        assert "load_unknown_load()" in inspect.getsource(fn), fn.__name__
