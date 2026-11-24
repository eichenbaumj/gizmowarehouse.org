"""The second number's two sensitivity scenarios (pipeline/analysis/second_number_scenarios.py; Joe, D-107, R2 of D-106).

Invented inputs only: no file under data/ is read and no price exists here; every "outcome" is a number made up in the
test. Each test plants an answer; tolerances are stated. The checks are shown able to fail by deliberate breaks made in
the test process (monkeypatch), not in the code, at the end of the file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import second_number as sn  # noqa: E402
from pipeline.analysis import second_number_scenarios as ss  # noqa: E402
from pipeline.facilities import buildout  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_pass_c_expand import GWH, mini  # noqa: E402
from test_second_number_invented import invented_world  # noqa: E402

KEY = ss.KEY
YEARS = ss.YEARS
C25 = sn.cap_label(25.0)
TOL = 1e-10


def sites_frame(rows):
    return pd.DataFrame(rows, columns=["fid", "state", "utility_id_eia", "candidates", "load_gwh"])


def date(fid, earliest, latest, convention, never=False):
    return {"fid": fid, "kind": "date", "earliest": earliest, "latest": latest, "never_is_possible": never,
            "convention": convention}


# ---- 1. scenario A: runner-up placement ----------------------------------------------------------------------------

PANEL = {(5, "AA"), (6, "AA"), (7, "AA"), (8, "AA")}


def check_candidate_order():
    """Stored order is kept: the site is on 6, its list is 7;5;6, everything fits, so it goes to 7, the first other."""
    p = ss.runner_up_placement(sites_frame([("s1", "AA", 6, "7;5;6", 10.0)]), {}, {(5, "AA"): 1e3, (7, "AA"): 1e3},
                               PANEL)
    assert p.to_utility.tolist() == [7] and p.moved.tolist() == [True]
    p = ss.runner_up_placement(sites_frame([("s1", "AA", 6, [6, 5, 7], 10.0)]), {}, {(5, "AA"): 1e3, (7, "AA"): 1e3},
                               PANEL)
    assert p.to_utility.tolist() == [5]                                    # the unit it is on goes to the end


def test_the_candidate_order_is_the_stored_order_with_the_current_unit_last():
    check_candidate_order()


def test_the_capacity_test_takes_the_first_candidate_that_can_hold_the_full_load():
    # 7 carries 95 of 100: 10 more does not fit (105 > 100); 5 carries 0 of 50: fits.
    p = ss.runner_up_placement(sites_frame([("s1", "AA", 6, "7;5", 10.0)]), {(7, "AA"): 95.0},
                               {(7, "AA"): 100.0, (5, "AA"): 50.0}, PANEL)
    assert p.to_utility.tolist() == [5]
    assert p.tried[0][0] == (7, "does not fit: 95.000 + 10.000 > 100.000 GWh")
    # exactly at capacity fits (<=, as pick_utilities)
    p = ss.runner_up_placement(sites_frame([("s1", "AA", 6, "7;5", 5.0)]), {(7, "AA"): 95.0}, {(7, "AA"): 100.0}, PANEL)
    assert p.to_utility.tolist() == [7]


def check_tie_break():
    """Two equal sites, room on 7 for one: the lower site id is placed first and takes it."""
    s = sites_frame([("s9", "AA", 6, "7", 10.0), ("s2", "AA", 6, "7", 10.0)])
    p = ss.runner_up_placement(s, {}, {(7, "AA"): 15.0}, PANEL).set_index("fid")
    assert p.loc["s2", "to_utility"] == 7 and p.loc["s9", "to_utility"] == 6
    assert p.loc["s2", "rank"] == 0


def test_ties_are_broken_by_site_id_and_larger_sites_go_first():
    check_tie_break()
    s = sites_frame([("a", "AA", 6, "7", 5.0), ("b", "AA", 6, "7", 12.0)])
    p = ss.runner_up_placement(s, {}, {(7, "AA"): 15.0}, PANEL).set_index("fid")
    assert p.loc["b", "to_utility"] == 7 and p.loc["a", "to_utility"] == 6        # b (larger) first; a no longer fits


def test_off_the_panel_is_never_chosen_and_a_unit_with_no_sales_row_is_skipped():
    s = sites_frame([("s1", "AA", 6, "99;7;5", 10.0)])                    # 99 is not a panel unit in AA
    p = ss.runner_up_placement(s, {}, {(99, "AA"): 1e6, (5, "AA"): 1e3}, PANEL)   # 7 has no sales row
    assert p.to_utility.tolist() == [5]
    assert [t[0] for t in p.tried[0]] == [7, 5] and "no sales row" in p.tried[0][0][1]
    p = ss.runner_up_placement(sites_frame([("s1", "BB", 6, "7;5", 10.0)]), {}, {(7, "BB"): 1e3}, PANEL)
    assert p.to_utility.tolist() == [6] and not p.moved.any()            # the candidates are panel units in AA, not BB


def test_a_site_that_fits_nowhere_else_stays():
    p = ss.runner_up_placement(sites_frame([("s1", "AA", 6, "7;5", 10.0)]), {}, {(7, "AA"): 5.0, (5, "AA"): 9.0}, PANEL)
    assert p.to_utility.tolist() == [6] and not p.moved.any() and "stays" in p.why[0]
    p = ss.runner_up_placement(sites_frame([("s1", "AA", 6, "6", 10.0)]), {}, {}, PANEL)
    assert p.why[0].startswith("no other panel candidate")


def test_each_placed_site_counts_where_it_lands():
    """Joe's rule (D-111): the sites being placed are lifted off first and each counts where it lands. 7 carries 30 of
    other load (capacity 60). big (50, on 7) moves to 5. stay (40, on 7) has no other candidate with a sales row, stays
    and counts on 7 from its turn (70). small (20, on 8) is then tested against 70 and stays on 8; without stay it would
    have fit (30 + 20 <= 60)."""
    s = sites_frame([("big", "AA", 7, "5;7", 50.0), ("stay", "AA", 7, "8;7", 40.0), ("small", "AA", 8, "7;8", 20.0)])
    cap = {(5, "AA"): 100.0, (7, "AA"): 60.0}
    p = ss.runner_up_placement(s, {(7, "AA"): 30.0}, cap, PANEL).set_index("fid")
    assert p.loc["big", "to_utility"] == 5 and p.loc["stay", "to_utility"] == 7 and p.loc["small", "to_utility"] == 8
    assert p.loc["small", "tried"][0] == (7, "does not fit: 70.000 + 20.000 > 60.000 GWh")
    p = ss.runner_up_placement(s[s.fid != "stay"], {(7, "AA"): 30.0}, cap, PANEL).set_index("fid")
    assert p.loc["small", "to_utility"] == 7


def check_packed_unit(carried=None):
    """The bi:13-0 situation, invented. L (12, on 6) has one other candidate, 5 (capacity 15), which as assigned carries
    the smaller unresolved site p (9) that will itself move to 7. Lifted first, 5 carries nothing when L is tested, so L
    moves there and p moves on to 7. Under the earlier reading (5 carries p's 9 at the start) L was blocked and stayed."""
    s = sites_frame([("L", "AA", 6, "5;6", 12.0), ("p", "AA", 5, "5;7", 9.0)])
    p = ss.runner_up_placement(s, {} if carried is None else carried, {(5, "AA"): 15.0, (7, "AA"): 100.0}, PANEL)
    p = p.set_index("fid")
    assert p.loc["L", "to_utility"] == 5 and p.loc["L", "moved"] and p.loc["p", "to_utility"] == 7


def test_a_larger_site_is_not_blocked_by_smaller_unresolved_sites_that_leave():
    check_packed_unit()


def test_the_start_leaves_the_sites_being_placed_out():
    """carried_without counts every site on a unit at MW x 8.76 except the sites being placed; a missing load is zero
    and a site with no utility or no state counts nowhere."""
    k = 1 / 8.76
    fac = pd.DataFrame({"utility_id_eia": [6, 6, 5, 5, None, 7], "state": ["AA", "AA", "AA", "AA", "AA", None],
                        "mw_full": [12 * k, 3 * k, 9 * k, None, 4 * k, 2 * k]},
                       index=pd.Index(["L", "r", "p", "z", "n", "x"], name="fid"))
    c = ss.carried_without(fac, {"L", "p"})
    assert c == pytest.approx({(6, "AA"): 3.0, (5, "AA"): 0.0})
    assert ss.carried_without(fac, set()) == pytest.approx({(6, "AA"): 15.0, (5, "AA"): 9.0})


def test_each_site_is_placed_once():
    with pytest.raises(ValueError, match="appears twice"):
        ss.runner_up_placement(sites_frame([("s1", "AA", 6, "7", 1.0), ("s1", "AA", 6, "7", 1.0)]), {}, {}, PANEL)


# ---- 2. scenario B: the other end of every dated interval -----------------------------------------------------------

def check_other_end():
    assert ss.other_end(date("x", 2010, 2015, 2015))["setting"] == 2010                    # late end -> early end
    assert ss.other_end(date("x", 2010, 2015, 2010))["setting"] == 2015                    # early end -> late end
    r = ss.other_end(date("x", None, 2011, 2011))                                          # open below, late convention
    assert r["setting"] == px.OPEN_BELOW_START == 1999 and r["moves"] == "earlier"
    assert ss.other_end(date("x", 2005, 2015, 2008))["setting"] == 2015                    # interior: late end farther
    assert ss.other_end(date("x", 2005, 2015, 2010))["setting"] == 2005                    # interior tie: the early end
    assert ss.other_end(date("x", None, 2012, 2011))["setting"] == 1999                    # bi:1250-0's shape
    r = ss.other_end(date("x", 2014, 2014, 2014))
    assert r["setting"] == 2014 and r["moves"] == "none"                                   # a one-year interval keeps it
    r = ss.other_end(date("x", 2016, None, 2016, never=True))
    assert r["setting"] == "never" and r["moves"] == "later"


def test_the_other_end_of_each_interval():
    check_other_end()


def test_an_entry_with_no_convention_is_not_moved_by_rule_b():
    with pytest.raises(ValueError, match="no convention"):
        ss.other_end(date("x", 2024, None, None, never=True))


def test_open_below_is_full_load_from_2001():
    inp = mini([{"fid": "q1", "st": "DD", "u": 7, "raw": 4.0, "year": 2011},
                {"fid": "s8", "st": "DD", "u": 8, "raw": 4.0, "year": 2010}], {(7, "DD"): 1e3, (8, "DD"): 1e3})
    entries = [date("q1", None, 2011, 2011)]
    settings = {"DD": {"q1 date": ss.other_end(entries[0])["setting"]}}
    h = ss.realise_history(inp, entries, settings)
    q1 = h["gwh"].loc[(7, "DD")]
    assert q1[2001] == pytest.approx(4.0 * GWH, abs=1e-9) and q1[2002] == pytest.approx(4.0 * GWH, abs=1e-9)


def test_rule_b_counts_and_the_load_unknown_sites_early_end():
    state_of = {"a": "AA", "b": "AA", "c": "BB", "bi:852-0": "OR", "bi:837-0": "OR"}
    entries = [date("a", 2010, 2015, 2015), date("b", 2010, 2015, 2010), date("c", 2014, 2014, 2014),
               date("bi:852-0", 2024, None, None, never=True), date("bi:837-0", 2011, 2019, None),
               {"fid": "bi:837-0", "kind": "capacity_split", "first_share": 0.495, "rest_earliest": 2011}]
    s, rec = ss.scenario_b_settings(entries, state_of)
    assert s == {"AA": {"a date": 2010, "b date": 2015},
                 "OR": {"bi:852-0 date": 2024, "bi:837-0 date": 2011, "bi:837-0 capacity": 2011}}
    assert [r["moves"] for r in rec] == ["earlier", "later", "none"]


# ---- 3. each site once, one utility, one history; the factor; the loop -----------------------------------------------

def anchoring_world():
    """DD: q1 (utility 7) dated 2016 to 2024; s8 utility 8's permit site; m9 a measured figure on 9. Factor 0.5 with q1
    at full load in 2024 (test_pass_c_expand's world). Two candidates for s8 (8;7), unresolved."""
    sites = [{"fid": "q1", "st": "DD", "u": 7, "raw": 4.0, "year": 2016},
             {"fid": "s8", "st": "DD", "u": 8, "raw": 4.0, "year": 2010, "cands": "8;7", "assign": "smallest_polygon"},
             {"fid": "m9", "st": "DD", "u": 9, "raw": 3.0, "year": 2010, "basis": "verified_public_figure"}]
    epri = {"DD": 0.5 * 8 * GWH / 1000 + 3 * GWH / 1000}
    return mini(sites, {(7, "DD"): 1e3, (8, "DD"): 1e3, (9, "DD"): 1e3}, epri), epri["DD"]


def check_factor():
    """q1 at the late end (2024) carries a third of its load in 2024: the permit total is (4 + 4/3) MW x 8.76 / 1000 TWh,
    the measured 3 x 8.76 / 1000, and the factor is the build's arithmetic on those totals, by hand: 0.75."""
    inp, epri = anchoring_world()
    entries = [date("q1", 2016, 2024, 2016)]
    h = ss.realise_history(inp, entries, {"DD": {"q1 date": ss.other_end(entries[0])["setting"]}})
    permit = (4.0 + buildout.ramp_mw(4.0, 2024, 2024)) * GWH / 1000
    measured = 3.0 * GWH / 1000
    by_hand = min(max((epri - measured) / permit, 0.2), 3.0)
    assert by_hand == pytest.approx(0.75, abs=1e-12)
    assert h["factor"]["DD"] == pytest.approx(by_hand, abs=1e-12) and h["frozen_factor"]["DD"] == pytest.approx(0.5)
    # s8's load moves with the factor though nothing on 8 moved
    assert h["gwh"].loc[(8, "DD"), 2015] == pytest.approx(4.0 * 0.75 * GWH, abs=1e-9)


def test_the_factor_is_the_builds_arithmetic_on_the_historys_totals():
    check_factor()


def test_a_moved_site_is_on_one_utility_in_one_history():
    inp, _ = anchoring_world()
    h0 = ss.realise_history(inp, [], {})
    h = ss.realise_history(inp, [], {"DD": {"s8 assignment": 7}})
    assert h["gwh"].loc[(8, "DD")].sum() == 0.0
    assert h["gwh"].loc[(7, "DD")].values == pytest.approx(h0["gwh"].loc[(7, "DD")].values + h0["gwh"].loc[(8, "DD")].values)
    assert h["gwh"].values.sum() == pytest.approx(h0["gwh"].values.sum())                  # moved, not copied
    with pytest.raises(ValueError, match="not in"):
        ss.realise_history(inp, [], {"DD": {"zz assignment": 7}})
    with pytest.raises(ValueError, match="set twice"):
        ss.scenario_a_settings(pd.DataFrame([{"fid": "s8", "state": "DD", "to_utility": 7, "moved": True}] * 2),
                               {"s8": "DD", "bi:852-0": "OR", "bi:837-0": "OR"})


def check_reconstruction():
    inp, _ = anchoring_world()
    h = ss.realise_history(inp, [], {})
    g = (inp.fy.groupby(KEY + ["year"]).mw.sum() * GWH).rename("dc_gwh").reset_index()
    dose_file = g.assign(dose=g.dc_gwh / 1e3)
    ok = ss.reconstruction_check(h["gwh"], inp.base, dose_file, [])
    assert ok["DD"]["passes"] and ok["DD"]["units_agree"] == 3 and not ok["DD"]["disagreements"]
    bad = dose_file.copy()
    bad.loc[(bad.utility_id_eia == 8) & (bad.year == 2015), "dose"] *= 1 + 1e-6
    r = ss.reconstruction_check(h["gwh"], inp.base, bad, [])["DD"]
    assert not r["passes"] and r["disagreements"][0]["utility"] == "8:DD" and r["disagreements"][0]["years"] == [2015]
    assert r["disagreements"][0]["realised"][0] != r["disagreements"][0]["dose_file"][0]
    left = ss.reconstruction_check(h["gwh"], inp.base, bad, [(8, "DD")])["DD"]          # a unit a load-unknown site reaches
    assert left["passes"] and left["units_left_out_as_reached_by_a_load_unknown_site"] == ["8:DD"]


def test_the_reconstruction_check_passes_on_the_inventory_and_reports_a_discrepancy():
    check_reconstruction()


def test_agreement_is_relative_and_exact_at_zero():
    assert ss.agree(1.0, 1.0 + 5e-10).all() and not ss.agree(1.0, 1.0 + 5e-9).all()
    assert ss.agree(0.0, 0.0).all() and not ss.agree(0.0, 1e-300).all()


# ---- 4. neither rule takes a dose, a price or an estimate -----------------------------------------------------------

def check_refusals():
    with pytest.raises(ValueError, match="no dose, price or estimate"):
        ss.runner_up_placement(sites_frame([("s1", "AA", 6, "7", 1.0)]).assign(dose=0.1), {}, {}, PANEL)
    with pytest.raises(ValueError, match="no dose, price or estimate"):
        ss.runner_up_placement(sites_frame([("s1", "AA", 6, "7", 1.0)]).assign(res_price=0.1), {}, {}, PANEL)
    with pytest.raises(ValueError, match="no dose, price or estimate"):
        ss.other_end({**date("x", 2010, 2015, 2015), "estimate": 0.3})


def test_neither_rule_takes_a_dose_a_price_or_an_estimate():
    check_refusals()
    ss._check_rule_signatures()


# ---- 5. labels, and the wrapper on invented outcomes -----------------------------------------------------------------

def test_each_label_says_what_differs_besides_its_own_question():
    for name in ss.SCENARIOS:
        lab = ss.LABELS[name]
        assert "sensitivity scenario" in lab.lower() and "alternative" not in lab.lower()
        assert "not a bound" in lab and "not necessarily a one-change comparison" in lab
        for must in ("bi:852-0", "bi:837-0", "Oregon's factor", "sample"):
            assert must in lab, (name, must)
        assert "—" not in lab
    assert ss.LOAD_UNKNOWN_EARLY_END == {"bi:852-0 date": 2024, "bi:837-0 date": 2011, "bi:837-0 capacity": 2011}
    assert all(n.startswith("sensitivity_scenario_") for n in ss.SCENARIOS)


def check_planted_slope(rng_seed=3):
    """y's change = b x the scenario's change in dose capped at 25 + a cell effect; noise-free, exact to 1e-10."""
    units, q, regions, dose, prices, usable = invented_world()
    points = sn.dose_points(dose)
    f = ss.scenario_frame(points, units, q, regions, usable, sn.region_codes(regions), no_dose=[units[0]])
    assert units[0] not in f.keys and any("no dose" in x["why"] for x in f.left_out)
    x = sn.dose_matrix(points, f.keys, f.years)
    b = 0.004
    rng = np.random.default_rng(1)
    cell = {c: rng.normal(0, 0.05) for c in np.unique(f.cell)}
    dy = b * sn.change(x, f.n_pre, 25.0) + np.array([cell[c] for c in f.cell])
    y = np.zeros(x.shape)
    y[:, f.n_pre:] = dy[:, None]
    out = pd.DataFrame([(k[0], k[1], yr, y[i, j]) for i, k in enumerate(f.keys) for j, yr in enumerate(f.years)],
                       columns=KEY + ["year", "log_price"])
    r = ss.run_scenario(f, points, out, sn.bootstrap_rng(rng_seed, invented_inputs=True), boot=49)
    assert abs(r[C25]["est"] - b) <= TOL, r[C25]["est"]
    assert r["label"].startswith("sensitivity scenario")


def test_the_scenario_run_recovers_a_planted_slope_on_invented_outcomes():
    check_planted_slope()


# ---- 6. each check above can fail: deliberate breaks in the test process --------------------------------------------

def test_the_candidate_order_check_can_fail(monkeypatch):
    monkeypatch.setattr(ss, "_candidates", lambda v: list(reversed(ss.asg.candidates(v) if isinstance(v, str) else v)))
    with pytest.raises(AssertionError):
        check_candidate_order()


def test_the_packed_unit_check_can_fail():
    """Start from the earlier reading (the placed sites counted where they sit): L is blocked and the check fails."""
    with pytest.raises(AssertionError):
        check_packed_unit(carried={(6, "AA"): 12.0, (5, "AA"): 9.0})


def test_the_start_check_can_fail(monkeypatch):
    """Replace carried_without inside this process with one that lifts nothing (the earlier reading's start): the
    start test fails."""
    real = ss.carried_without
    monkeypatch.setattr(ss, "carried_without", lambda fac, placed: real(fac, set()))
    with pytest.raises(AssertionError):
        test_the_start_leaves_the_sites_being_placed_out()


def test_the_tie_break_check_can_fail(monkeypatch):
    real = pd.DataFrame.sort_values

    def by_id_descending(self, by=None, ascending=True, **k):
        if by == ["load_gwh", "_fid"]:
            ascending = [False, False]
        return real(self, by=by, ascending=ascending, **k)
    monkeypatch.setattr(pd.DataFrame, "sort_values", by_id_descending)
    with pytest.raises(AssertionError):
        check_tie_break()


def test_the_other_end_check_can_fail(monkeypatch):
    monkeypatch.setattr(ss.px, "OPEN_BELOW_START", 2005)
    with pytest.raises(AssertionError):
        check_other_end()


def test_the_factor_check_can_fail(monkeypatch):
    monkeypatch.setattr(px, "_factor", lambda epri, m, p: 1.0)                   # the factor never recomputed
    with pytest.raises(AssertionError):
        check_factor()


def test_the_reconstruction_check_can_fail(monkeypatch):
    monkeypatch.setattr(ss, "agree", lambda a, b, rel=ss.TOLERANCE_REL: np.ones(np.shape(np.asarray(a)), dtype=bool))
    with pytest.raises(AssertionError):
        check_reconstruction()


def test_the_refusal_check_can_fail(monkeypatch):
    monkeypatch.setattr(ss, "REFUSED", ())
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        check_refusals()


def test_the_planted_slope_check_can_fail(monkeypatch):
    monkeypatch.setattr(sn, "dose_matrix", lambda points, keys, years: np.zeros((len(keys), len(years))))
    with pytest.raises(AssertionError):
        check_planted_slope()
