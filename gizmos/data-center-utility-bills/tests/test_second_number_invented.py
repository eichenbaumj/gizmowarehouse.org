"""The second number's frame, doses, classes, runs and interfaces (pipeline/analysis/second_number.py). Invented inputs only:
no file under data/ is read, no price exists anywhere here; every "price" is a number made up in the test."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import estimator  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import second_number as sn  # noqa: E402
from pipeline.facilities import buildout  # noqa: E402
from pipeline.facilities import timing as tm  # noqa: E402
import stepd_world as W  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
STATES = ("AA", "AB", "BB", "BC", "CA", "CB")
TOL = 1e-10


def invented_world(n_per_state=12, seed=7, host_dose=0.30):
    """Utilities in six states, two regions (some utilities move between 2009 and 2024), three size bands; a small own
    load-share trace for every utility (under 0.5%) and one host per state with a large one. Made up."""
    rng = np.random.default_rng(seed)
    units, q, reg, dose = [], [], [], []
    for si, st in enumerate(STATES):
        for i in range(n_per_state):
            u = 100 * (si + 1) + i
            size = [5_000, 50_000, 500_000][i % 3] + 37 * i
            units.append((u, st))
            r0 = "West" if si < 3 else "PJM"
            moves = (i % 5 == 0)
            for y in YEARS:
                q.append((u, st, y, "cooperative", size, 1.0, True))
                reg.append((u, st, y, ("PJM" if r0 == "West" else "West") if (moves and y >= 2015) else r0))
                d = host_dose * max(0.0, (y - 2012) / 10) if i == 0 else 0.004 * rng.uniform() * (y >= 2005)
                dose.append((u, st, y, d))
    q = pd.DataFrame(q, columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    regions = pd.DataFrame(reg, columns=KEY + ["year", "region"])
    dose = pd.DataFrame(dose, columns=KEY + ["year", "dose"])
    prices = q[KEY + ["year"]].assign(res_price=np.exp(rng.normal(-2.0, 0.08, len(q))))
    usable = {(u, st, y) for u, st in units for y in YEARS}
    return units, q, regions, dose, prices, usable


def log_outcome(prices):
    return prices.assign(log_price=np.log(prices.res_price))[KEY + ["year", "log_price"]]


# ---- 1. the frame and the estimator --------------------------------------------------------------------------------

def test_a_planted_slope_is_recovered():
    """y's change = b * x's change (capped at 25) + a cell effect + noise. Noise-free: exact to 1e-10. With noise of
    sd 0.002 log points per unit on 72 units: within 0.002 of b."""
    units, q, regions, dose, prices, usable = invented_world()
    f = sn.build_frame(units, q, regions, usable)
    pts = sn.dose_points(dose)
    x = sn.dose_matrix(pts, f.keys, f.years)
    b = 0.004                                                       # log points per point of load share
    rng = np.random.default_rng(1)
    cell_eff = {c: rng.normal(0, 0.05) for c in np.unique(f.cell)}
    for noise, tol in ((0.0, TOL), (0.002, 0.002)):
        dx = sn.change(x, f.n_pre, 25.0)
        dy = b * dx + np.array([cell_eff[c] for c in f.cell]) + rng.normal(0, noise, len(dx))
        y = np.zeros(x.shape)
        y[:, f.n_pre:] = dy[:, None]                                # pre at zero, post at the planted change
        res = sn.fit(f, x, y, np.random.default_rng(2), boot=199, caps=(25.0,))
        r = res["capped_at_25_points"]
        assert abs(r["est"] - b) <= tol, (noise, r["est"])
        if noise:
            assert r["numerical_failure"] is None and r["lo"] < r["est"] < r["hi"]     # one draw: coverage is not tested here


def test_the_cap_at_25_by_hand():
    x = np.array([[24.0, 26.0, 30.0, 20.0, 25.0, 40.0], [0.0, 0.0, 0.0, 1.0, 2.0, 3.0]])
    assert sn.change(x, 3, 25.0)[0] == pytest.approx((20 + 25 + 25) / 3 - (24 + 25 + 25) / 3, abs=1e-12)    # -4/3
    assert sn.change(x, 3, None)[0] == pytest.approx(85.0 / 3 - 80.0 / 3, abs=1e-12)                         # 5/3
    assert sn.change(x, 3, 50.0)[0] == sn.change(x, 3, None)[0]
    assert sn.change(x, 3, 25.0)[1] == pytest.approx(2.0, abs=1e-12)


def _simulation_path(monkeypatch, units, q, regions, dose, prices, usable, seed=(5, 6), boot=99):
    """run_second_number with no stand-in placed (pick_stand_ins returns none), one draw, every chunk's raw result kept:
    the simulation's computation on the comparison units with their own load-share traces."""
    captured = []
    real_run = ps._run

    def keep(task, ctx, chunks, workers):
        out = real_run(task, ctx, chunks, workers)
        captured.append(out)
        return out
    monkeypatch.setattr(ps, "pick_stand_ins", lambda real, stacks, n, rng: ([], {"tiers": {}, "size_gaps": []}))
    monkeypatch.setattr(ps, "_run", keep)
    hosts = [(u, st) for u, st in units if u % 100 == 0]
    clean = pd.DataFrame([k for k in units if k not in hosts], columns=KEY)
    ps.run_second_number(q, dose, clean, regions, prices, seed, draws=1, boot=boot, usable=usable,
                         unknown_load=ps.UnknownLoad.none("invented"))
    return clean, captured


def test_the_wrapper_equals_the_simulations_path(monkeypatch):
    units, q, regions, dose, prices, usable = invented_world()
    seed, boot = (5, 6), 99
    clean, captured = _simulation_path(monkeypatch, units, q, regions, dose, prices, usable, seed, boot)
    codes = sn.region_codes(regions)
    pts = sn.dose_points(dose)
    for i, (name, frame) in enumerate((("long_difference", sn.build_frame(list(map(tuple, clean.values)), q, regions, usable, codes=codes)),
                                       ("panel", sn.panel_frame(list(map(tuple, clean.values)), q, regions, usable, codes=codes)))):
        x = sn.dose_matrix(pts, frame.keys, frame.years)
        y = sn.outcome_matrix(log_outcome(prices), frame.keys, frame.years)
        mine = sn.fit(frame, x, y, np.random.default_rng(list(seed + (i, 0))), boot=boot)
        sim = captured[i][0]
        for cap in ps.CAPS:
            a, b = mine[sn.cap_label(cap)], sim[cap][0]
            assert a["numerical_failure"] is None and b["numerical_failure"] is None
            for f in ("est", "se", "lo", "hi"):
                assert abs(a[f] - b[f]) <= TOL, (name, cap, f, a[f], b[f])
    # The closed-form slope of the first runs gives the same point estimate on the long comparison (one grouping).
    f = sn.build_frame(list(map(tuple, clean.values)), q, regions, usable, codes=codes)
    xf, yf = ps.per_point_frame("long_difference", np.minimum(sn.dose_matrix(pts, f.keys, f.years), 25.0),
                                sn.outcome_matrix(log_outcome(prices), f.keys, f.years))
    s = ps.slope(xf, yf, f.cell, f.state, np.random.default_rng(0), boot=9)
    r = sn.fit(f, sn.dose_matrix(pts, f.keys, f.years), sn.outcome_matrix(log_outcome(prices), f.keys, f.years),
               np.random.default_rng(0), boot=9, caps=(25.0,))
    assert abs(s["est"] - r["capped_at_25_points"]["est"]) <= TOL


def test_the_equality_test_can_fail(monkeypatch):
    """The same comparison with the weights drawn from another seed moves the range: the test above is not vacuous."""
    units, q, regions, dose, prices, usable = invented_world()
    clean, captured = _simulation_path(monkeypatch, units, q, regions, dose, prices, usable)
    f = sn.build_frame(list(map(tuple, clean.values)), q, regions, usable, codes=sn.region_codes(regions))
    x, y = sn.dose_matrix(sn.dose_points(dose), f.keys, f.years), sn.outcome_matrix(log_outcome(prices), f.keys, f.years)
    other = sn.fit(f, x, y, np.random.default_rng([9, 9, 9]), boot=99)
    assert abs(other["uncapped"]["lo"] - captured[0][0][None][0]["lo"]) > TOL


def test_fit_on_changes_equals_fit_on_years():
    units, q, regions, dose, prices, usable = invented_world()
    f = sn.build_frame(units, q, regions, usable)
    x = sn.dose_matrix(sn.dose_points(dose), f.keys, f.years)
    y = sn.outcome_matrix(log_outcome(prices), f.keys, f.years)
    a = sn.fit(f, x, y, np.random.default_rng(3), boot=99)
    dx = {sn.cap_label(c): sn.change(x, f.n_pre, c) for c in ps.CAPS}
    b = sn.fit_changes(f, dx, y[:, 3:].mean(1) - y[:, :3].mean(1), np.random.default_rng(3), boot=99)
    for lab in dx:
        for k in ("est", "se", "lo", "hi"):
            assert abs(a[lab][k] - b[lab][k]) <= 1e-12


def test_the_outcome_is_an_argument_and_a_missing_unit_year_stops():
    units, q, regions, dose, prices, usable = invented_world()
    f = sn.build_frame(units, q, regions, usable)
    out = log_outcome(prices)
    with pytest.raises(ValueError, match="lacks 1 unit-year"):
        sn.outcome_matrix(out.drop(out.index[(out.year == 2024)][:1]), f.keys, f.years)


def test_the_frame_reads_usability_from_the_flag_and_names_who_it_leaves_out():
    units, q, regions, dose, prices, usable = invented_world()
    gone = units[3]
    usable = usable - {(gone[0], gone[1], 2009)}
    f = sn.build_frame(units, q, regions, usable)
    assert gone not in f.keys and len(f.keys) == len(units) - 1
    assert f.left_out == [{"utility": f"{gone[0]}:{gone[1]}", "why": "not usable in 2009 (res_price_usable)"}]


def test_leverage_is_second_number_leverages_computation():
    units, q, regions, dose, prices, usable = invented_world()
    q = q.assign(utility_name="x")
    out, table = ic.second_number_leverage(q, dose, regions, ps.UnknownLoad.none("invented"))
    f = sn.build_frame(units, q, regions, usable, codes=sn.region_codes(regions))
    x = sn.dose_matrix(sn.dose_points(dose), f.keys, f.years)
    t = table.set_index(KEY)
    assert len(t) == len(f.keys)
    for cap in ps.CAPS:
        lev = sn.leverage(sn.change(x, f.n_pre, cap), f)
        ref = t.loc[f.keys, f"leverage_{sn.cap_label(cap)}"].values
        assert np.abs(lev.round(6) - ref).max() <= 1e-6


# ---- 2 and 3. histories, and the classes as first built (SUPERSEDED RECORD, D-102; the adopted ones: test_second_number_adopted_invented.py) ---------------------------------------------------------------------------------

def test_case_points_and_within_history_changes_by_hand():
    units = pd.MultiIndex.from_tuples([(1, "AA"), (2, "AA"), (3, "AA")], names=KEY)
    z = pd.DataFrame(0.0, index=units, columns=YEARS)
    ab = z.copy()
    ab.loc[(1, "AA"), 2009:] = 10.0                                # 10 GWh from 2009
    lower = z.copy()                                              # its one unresolved site taken off
    upper = ab.copy()
    upper.loc[(2, "AA"), 2024:] = 5.0                             # an unresolved site listing 2 counted on it
    m = {"as_built": ab, "no_anchoring": ab / 2, "lower_as_built": lower, "lower_no_anchoring": lower,
         "upper_as_built": upper, "upper_no_anchoring": upper / 2}
    base = pd.Series([100.0, 100.0, np.nan], index=units)          # 3 has no base and no load: zero
    pts, no_base = sn.case_points(m, base)
    assert no_base == []
    ch = sn.history_changes(pts, cap=25.0)
    # utility 1 as assigned: (10 + 10 + 10)/3 - (0 + 10 + 10)/3 points
    assert ch.loc[(1, "AA"), "as_assigned_as_built"] == pytest.approx(10 - 20 / 3)
    assert ch.loc[(1, "AA"), "lower_as_built"] == 0.0
    assert ch.loc[(2, "AA"), "upper_as_built"] == pytest.approx(10 / 3)
    assert ch.loc[(3, "AA")].eq(0).all()
    m2 = {k: v.copy() for k, v in m.items()}
    m2["upper_as_built"].loc[(3, "AA"), 2020] = 1.0               # load on a utility with no base: no dose, named
    _, no_base = sn.case_points(m2, base)
    assert no_base == [(3, "AA")]


@pytest.mark.parametrize("assigned, changes, expected", [
    (0.0, [0.0, 0.0, 0.0], sn.NO_SITE),
    (0.0, [0.0, 0.0, 0.5], sn.APPARENT_ZERO),                    # zero as assigned and positive in one case
    (0.0, [0.0, 0.0, 9.0], sn.APPARENT_ZERO),
    (3.0, [3.0, 1.5, 2.999], sn.SETTLED),                        # differs by less than two points
    (3.0, [3.0, 1.0, 3.0], sn.UNCERTAIN),                        # exactly two points apart: not settled
    (1.5, [1.5, 0.0, 1.5], sn.SETTLED),                          # lower case zero, range under two: settled
    (3.0, [3.0, 1.0, 3.0 + 1e-12], sn.UNCERTAIN),                # just over two points: not settled
    (3.0, [3.0, 0.0, 5.0], sn.UNCLASSIFIED),                     # zero in a case, not settled: none of the four
    (5.0, [5.0, 2.0, 8.0], sn.UNCERTAIN),
])
def test_classes_at_their_boundaries(assigned, changes, expected):
    assert sn.classify(assigned, np.array(changes)) == expected


def test_a_site_taken_off_never_makes_a_verified_zero():
    """Lower case zero, as assigned positive: never 'no site in reach'."""
    assert sn.classify(4.0, [4.0, 0.0, 4.0]) != sn.NO_SITE
    assert sn.classify(0.5, [0.5, 0.0, 0.5]) == sn.SETTLED


def test_a_common_dose_is_exact_equality_at_every_cap():
    """common_dose is the superseded every-cap rule (D-102), kept as the record; common_by_cap is the description per form."""
    same = {"uncapped": np.array([3.0, 3.0]), "capped_at_25_points": np.array([3.0, 3.0]), "capped_at_50_points": np.array([3.0, 3.0])}
    assert sn.common_dose(same) == {k: 3.0 for k in same}
    near = {**same, "uncapped": np.array([3.0, 3.0 + 1e-9])}
    assert sn.common_dose(near) is None
    assert sn.common_by_cap(near)["capped_at_25_points"] == 3.0 and sn.common_by_cap(near)["uncapped"] is None


def _unknown_world():
    """State AA: site u (load unknown, start in 2021 to 2024, no convention) on utility 1; site p (permit) on utility 2,
    which a load-unknown site reaches only through the state's factor; site a, unresolved between 1 and 3, on 1."""
    sites = [{"fid": "u", "state": "AA", "mw": 40.0, "year": 2022, "utility": 1},
             {"fid": "p", "state": "AA", "mw": 10.0, "year": 2008, "utility": 2},
             {"fid": "a", "state": "AA", "mw": 6.0, "year": 2009, "utility": 1, "assign": "smallest_polygon", "candidates": "1;3"}]
    base_mw = {(1, "AA"): 4.0, (2, "AA"): 4.0, (3, "AA"): 4.0}
    epri = {"AA": 30.0 * 8.76 / 1000}
    inp = W.make(sites, base_mw, epri=epri)
    entries = [W.date("u", 2021, 2024, None)]
    S = tm.StateRun(inp, entries, "AA", screen=(0,)).cases[0]["S"]
    return inp, S, epri


def test_load_unknown_histories_cross_the_dates_with_ruling_4s_cases_and_recompute_the_factor():
    inp, S, epri = _unknown_world()
    k2 = (2, "AA")
    base2 = float(inp.base[k2])
    r = sn.unknown_load_histories(S, k2, base2, ["u"])
    assert r.established and r.histories == 4 * 3 * 2              # four start years, three cases, two readings
    # By hand: the factor is (EPRI) / (2024 permit total), the 2024 permit total p's 10 MW + a's 6 MW + u's ramp in 2024.
    exp = []
    for s in (2021, 2022, 2023, 2024):
        permit = (10.0 + 6.0 + buildout.ramp_mw(40.0, s, 2024)) * 8.76 / 1000
        fct = min(max(epri["AA"] / permit, 0.2), 3.0)
        ld = np.array([buildout.ramp_mw(10.0 * fct, 2008, y) for y in list(ps.LONG_PRE) + list(ps.LONG_POST)]) * 8.76 / base2 * 100
        exp.append(ld[3:].mean() - ld[:3].mean())
    raw = np.array([buildout.ramp_mw(10.0, 2008, y) for y in list(ps.LONG_PRE) + list(ps.LONG_POST)]) * 8.76 / base2 * 100
    exp.append(raw[3:].mean() - raw[:3].mean())                    # with no anchoring
    got = r.changes["uncapped"]
    assert got.min() == pytest.approx(min(exp), abs=1e-9) and got.max() == pytest.approx(max(exp), abs=1e-9)
    assert len(set(np.round(got, 9))) > 1 and r.common_dose is None
    assert r.common_by_cap == sn.common_by_cap(r.changes) and r.common_by_cap["uncapped"] is None


def test_ruling_4s_cases_on_the_enumerations_assignment_questions():
    inp, S, _ = _unknown_world()
    c1 = sn.rule4_case_settings(S, (1, "AA"))
    c3 = sn.rule4_case_settings(S, (3, "AA"))
    qa = next(i for i, q in enumerate(S.qs) if q.fid == "a" and q.name == "assignment")
    assert S.qs[qa].values[c1["lower"][qa]] is None and qa not in c1["upper"]       # 1: a taken off
    assert S.qs[qa].values[c3["upper"][qa]] == 3 and qa not in c3["lower"]          # 3: a counted on it
    r3 = sn.unknown_load_histories(S, (3, "AA"), float(inp.base[(3, "AA")]), ["u"])
    assert r3.changes["uncapped"].max() > 0 and r3.changes["uncapped"].min() == 0.0  # zero unless a is put on it


# ---- 4. the runs ---------------------------------------------------------------------------------------------------

def _classified(assigned_by_uid: dict, no_assigned=(), established=None):
    """Adopted classes for invented utilities whose histories give one change each (range zero), the same at every form."""
    labs = [sn.cap_label(c) for c in ps.CAPS]
    a = {lab: dict(assigned_by_uid) for lab in labs}
    ch = {lab: {**{u: np.array([v, v]) for u, v in assigned_by_uid.items()}, **{u: np.array([1.0, 9.0]) for u in no_assigned}}
          for lab in labs}
    reach = {u: v != 0 for u, v in assigned_by_uid.items()}
    return sn.classify_by_cap(a, ch, reach, list(no_assigned), {} if established is None else established)


def test_a_utility_with_no_assigned_dose_is_left_out_and_named():
    """Superseded by the adopted classification's tests (test_second_number_adopted_invented.py) for the per-form detail;
    kept here for the as-built behaviour that survives: with no common change, out of every run and named."""
    cl = _classified({"1:AA": 1.0, "2:AA": 0.0, "3:AA": 4.0}, no_assigned=["9:AA"])
    keys = [(1, "AA"), (2, "AA"), (3, "AA"), (9, "AA")]
    z = np.zeros(4, dtype=int)
    f = sn.Frame("long_difference", keys, list(sn.PRE) + list(sn.POST), 3, [z.copy()], z.copy(), z.copy(), z.copy(), z.copy(), z.copy())
    s = sn.run_samples(f, cl)
    for name, r in s.items():
        for lab, x in r.items():
            assert "9:AA" not in x["utilities"] and "9:AA" in x["left_out_named"], (name, lab)
    lab = sn.cap_label(sn.MAIN_CAP)
    assert s[sn.RUN_SETTLED][lab]["utilities"] == ["1:AA", "2:AA", "3:AA"]        # classes 4, 2 and 4


def test_leave_ten_out_drops_the_ten_highest_leverage_utilities_that_are_not_settled():
    lev = {f"{i}:AA": float(i) for i in range(1, 21)}
    classes = {f"{i}:AA": (sn.SETTLED if i in (20, 18) else sn.UNCERTAIN if i % 2 else sn.APPARENT_ZERO) for i in range(1, 21)}
    classes["17:AA"] = sn.NO_ENDPOINT_EXPOSURE                    # class 2 is not among the not settled (D-105)
    ten = sn.leave_out_ten(lev, classes)
    assert ten == [f"{i}:AA" for i in (19, 16, 15, 14, 13, 12, 11, 10, 9, 8)]


def test_a_run_reports_its_class_counts_and_the_leverage_share_not_settled():
    units, q, regions, dose, prices, usable = invented_world()
    f = sn.build_frame(units, q, regions, usable)
    x = sn.dose_matrix(sn.dose_points(dose), f.keys, f.years)
    labs = [sn.cap_label(c) for c in ps.CAPS]
    a = {lab: dict(zip(map(sn._uid, f.keys), sn.change(x, f.n_pre, c))) for lab, c in zip(labs, ps.CAPS)}
    # hosts get an invented second history 5 points higher after (class 5 at every form); everyone else one history
    ch = {lab: {u: (np.array([v, v + 5.0]) if int(u.split(":")[0]) % 100 == 0 else np.array([v])) for u, v in a[lab].items()}
          for lab in labs}
    reach = {sn._uid(k): True for k in f.keys}
    cl = sn.classify_by_cap(a, ch, reach, [], {})
    ids = [sn._uid(k) for k in f.keys]
    r = sn.run_summary({lab: ids for lab in labs}, f, cl)
    lev = sn.leverage(sn.change(x, f.n_pre, 25.0), f)
    hosts = np.array([k[0] % 100 == 0 for k in f.keys])
    lab = sn.cap_label(25.0)
    assert r[lab]["class_counts"][sn.UNCERTAIN] == 6 and r[lab]["not_settled_utilities_classes_5_to_8"] == 6
    assert r[lab]["share_of_leverage_held_by_classes_5_to_8_not_settled"] == pytest.approx(lev[hosts].sum(), abs=1e-6)
    res = sn.run_single_dose({lab: ids for lab in labs}, f, cl, log_outcome(prices), np.random.default_rng(0), boot=49)
    assert res[lab]["utilities"] == len(f.keys) and np.isfinite(res[lab]["est"])


# ---- 5. the jointly consistent interface -----------------------------------------------------------------------------

def _inventory(s2_on, s3_start=2018):
    return pd.DataFrame([
        {"fid": "s1", "src": "bi", "state": "AA", "utility_id_eia": 1.0, "energized_year": 2005.0, "mw_full_raw": 10.0,
         "mw_basis": "generator_capacity_x_kappa", "is_crypto": False},
        {"fid": "s2", "src": "bi", "state": "AA", "utility_id_eia": float(s2_on), "energized_year": 2015.0, "mw_full_raw": 20.0,
         "mw_basis": "generator_capacity_x_kappa", "is_crypto": False},
        {"fid": "s3", "src": "bi", "state": "AA", "utility_id_eia": 3.0, "energized_year": float(s3_start), "mw_full_raw": 30.0,
         "mw_basis": "generator_capacity_x_kappa", "is_crypto": False}])


def test_one_whole_inventory_history_differs_from_independently_assembled_extremes():
    base = pd.Series([400.0, 400.0, 4000.0], index=pd.MultiIndex.from_tuples([(1, "AA"), (2, "AA"), (3, "AA")], names=KEY))
    epri = pd.Series({"AA": 0.3})
    on1 = sn.doses_from_one_history(_inventory(1), epri, base)
    on2 = sn.doses_from_one_history(_inventory(2), epri, base)
    c1, c2 = on1["change"]["uncapped"], on2["change"]["uncapped"]
    # By hand: factor = 0.3 TWh / (10 + 20 + 30 MW at full in 2024) x 8.76 / 1000; utility 1's dose with s2 on it.
    fct = 0.3 / (60.0 * 8.76 / 1000)
    assert float(on1["factor"].factor["AA"]) == pytest.approx(fct)
    yrs = list(ps.LONG_PRE) + list(ps.LONG_POST)
    ld1 = np.array([(buildout.ramp_mw(10 * fct, 2005, y) + buildout.ramp_mw(20 * fct, 2015, y)) * 8.76 / 400 * 100 for y in yrs])
    assert c1[(1, "AA")] == pytest.approx(ld1[3:].mean() - ld1[:3].mean(), abs=1e-9)
    # Each utility's own upper case put together: s2 on 1 AND on 2. No single history gives that vector.
    assembled = pd.Series({(1, "AA"): c1[(1, "AA")], (2, "AA"): c2[(2, "AA")], (3, "AA"): c1[(3, "AA")]})
    assert not np.allclose(assembled.values, c1.reindex(assembled.index).values)
    assert not np.allclose(assembled.values, c2.reindex(assembled.index).values)
    # A later start of s3 changes the 2024 permit total and so every permit-based dose in the state, utility 1's included,
    # though nothing on utility 1 moved: holding the factor fixed would give the wrong dose.
    late = sn.doses_from_one_history(_inventory(1, s3_start=2023), epri, base)
    assert late["factor"].factor["AA"] != on1["factor"].factor["AA"]
    assert abs(late["change"]["uncapped"][(1, "AA")] - c1[(1, "AA")]) > 1e-6
    with pytest.raises(ValueError, match="appears twice"):
        sn.doses_from_one_history(pd.concat([_inventory(1), _inventory(2).iloc[[1]]]), epri, base)


# ---- 6. E3's 2024 to 2025 alternative ------------------------------------------------------------------------------

def test_the_2024_to_2025_alternative_by_hand():
    units, q, regions, dose, prices, usable = invented_world()
    only_2023 = units[5]
    usable = usable - {(only_2023[0], only_2023[1], 2023)}
    f6 = sn.build_frame(units, q, regions, usable)
    f5 = sn.build_frame(units, q, regions, usable, post=sn.E3_POST)
    assert only_2023 not in f6.keys and only_2023 in f5.keys       # usable in the five years involved
    assert f5.years == [2008, 2009, 2010, 2024, 2025] and f5.n_pre == 3
    x = np.array([[1.0, 2.0, 3.0, 30.0, 40.0]])
    assert sn.change(x, 3, 25.0)[0] == pytest.approx((25 + 25) / 2 - 2.0)
    assert sn.change(x, 3, None)[0] == pytest.approx(35.0 - 2.0)
    # The outcome's change over the revised period, by hand, through the same fit.
    y = sn.outcome_matrix(log_outcome(prices), f5.keys, f5.years)
    dx = {"capped_at_25_points": sn.change(sn.dose_matrix(sn.dose_points(dose), f5.keys, f5.years), 3, 25.0)}
    a = sn.fit_changes(f5, dx, y[:, 3:].mean(1) - y[:, :3].mean(1), np.random.default_rng(1), boot=49, caps=(25.0,))
    b = sn.fit(f5, sn.dose_matrix(sn.dose_points(dose), f5.keys, f5.years), y, np.random.default_rng(1), boot=49, caps=(25.0,))
    assert abs(a["capped_at_25_points"]["est"] - b["capped_at_25_points"]["est"]) <= 1e-12


# ---- 7. the year-by-year side run ------------------------------------------------------------------------------------

def test_the_panel_frame_is_the_simulations_coding():
    units, q, regions, dose, prices, usable = invented_world(n_per_state=6)
    f = sn.panel_frame(units, q, regions, usable)
    P = len(ps.PANEL_YEARS)
    assert f.years == list(ps.PANEL_YEARS) and len(f.groups) == 2 and len(f.cluster) == len(f.keys) * P
    assert len(np.unique(f.groups[0])) == len(f.keys)
