"""Step E's drivers: the made-up prices G0 to G12, the seeds, the screen and the width ranking, the benchmark, the budget and
the two stages (docs/gate1/step-e-rules-2026-11-18.md). Invented designs and invented tables only; nothing here reads a
price, an outcome or anything under data/. No rate computed here bears on the choice: the designs are made up.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import design  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import inference_comparison as icp  # noqa: E402
from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import COOP, table  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
STATES = ["AA", "AB", "BB", "BC", "CA", "CB"]
FUEL = {st: i % 3 for i, st in enumerate(STATES)}
GAS = {st: 0.05 + 0.15 * i for i, st in enumerate(STATES)}


TERRITORY = "ZZ"            # a panel state with no row in the fixed gas-share / fuel-mix file (as AS, GU, PR, VI)


def invented_design(hosts=2, comps=14, cohorts=(2015,), seed=3, territory=False):
    """Made-up quantities: hosts and never-host utilities across six states in one region, every year usable. With
    `territory`, one host and three never-host utilities sit in a state with no gas share, no fuel-mix group and no
    degree days, sized to be the nearest matches of everyone."""
    hs = [(1 + i, STATES[i % len(STATES)], 10_000 + 40 * i, COOP, cohorts[i % len(cohorts)]) for i in range(hosts)]
    cs = [(100 + i, STATES[(i + 1) % len(STATES)], 10_050 + 60 * i, COOP, None) for i in range(comps)]
    if territory:
        hs.append((90, TERRITORY, 10_010, COOP, cohorts[0]))
        cs += [(190 + i, TERRITORY, 10_001 + i, COOP, None) for i in range(3)]
    units = hs + cs
    q = pd.DataFrame([(u, st, y, own, size, 1.0, True) for u, st, size, own, _ in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    q["utility_name"] = [f"U{u}" for u in q.utility_id_eia]
    regions = pd.DataFrame([(u, st, y, "West") for u, st, *_ in units for y in YEARS], columns=KEY + ["year", "region"])
    rng = np.random.default_rng(seed)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in STATES for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    treated = pd.DataFrame({"utility_id_eia": [h[0] for h in hs], "state": [h[1] for h in hs], "cohort": [h[4] for h in hs]})
    clean = pd.DataFrame([(u, st) for u, st, *_ in cs], columns=KEY)
    usable = {(u, st, y) for u, st, *_ in units for y in YEARS}
    if territory:
        return treated, clean, q, regions, dd, usable
    d = design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, ownership=table([]), usable=usable, gas=GAS,
                                unknown_load=ps.UnknownLoad.none("invented data: no load-unknown site"))
    return d, regions, q, usable


@pytest.fixture(scope="module")
def world():
    d, regions, q, usable = invented_design(hosts=3, comps=16, cohorts=(2014, 2016))
    built = icp.build_context(d, regions, q, table([]), None, "ownership only (test)", boot=19)
    fp = icp.comparison_fingerprint(d, ps.HEADLINE_RULES, usable, built["quantities"], 19, cd.CANDIDATES)
    return {"d": d, "regions": regions, "q": q, "usable": usable, **built, "fp": fp}


def original_made_up(region_all, state_all, owner_all, rng, dgp):
    """inference_check.made_up as it stood before step E's two optional keys, copied verbatim."""
    n, years = region_all.shape

    def ar1(rows, rho, sd):
        e = rng.normal(0, 1.0, (rows, years))
        for t in range(1, years):
            e[:, t] += rho * e[:, t - 1]
        return e * (sd if np.isscalar(sd) else np.asarray(sd)[:, None])

    region = rng.normal(0, dgp["region_step_sd"], (int(region_all.max()) + 1, years)).cumsum(1)
    state = ar1(int(state_all.max()) + 1, dgp["state_rho"], dgp["state_sd"])
    scale = np.exp(rng.normal(0, dgp["own_scale_sd"], n)) if dgp.get("own_scale_sd") else np.ones(n)
    if dgp.get("steps"):
        st = dgp["steps"]
        jumps = (rng.random((n, years)) < st["prob"]) * rng.normal(st["mean"], st["sd"], (n, years))
        own = (jumps.cumsum(1) + rng.normal(0, st["noise_sd"], (n, years))) * scale[:, None]
    else:
        own = ar1(n, dgp["own_rho"], dgp["own_sd"] * scale)
    out = rng.normal(2.4, 0.2, (n, 1)) + region[region_all, np.arange(years)[None, :]] + state[state_all] + own
    if dgp.get("ownership_step_sd"):
        walk = rng.normal(0, dgp["ownership_step_sd"], (len(ic.OWNERSHIP) + 1, years)).cumsum(1)
        out = out + walk[owner_all]
    return out


def increment(world, p, seed=11):
    """Process p's draw minus G0's on the same generator: what p adds (G8, G10, G11, G12 are G0 plus a part drawn after)."""
    c = world["ctx"]
    P, change = icp.draw(p, np.random.default_rng(seed), c)
    P0 = ic.made_up(c["region_all"], c["state_all"], c["owner_all"], np.random.default_rng(seed), ic.GRID["G0_as_in_D38"])
    return P - P0, change


# ================================================================================================================
# The made-up prices
# ================================================================================================================

def test_there_are_thirteen_processes_in_the_fixed_order():
    assert icp.PROCESSES[:7] == tuple(ic.GRID) and len(icp.PROCESSES) == 13
    assert [p.split("_")[0] for p in icp.PROCESSES] == [f"G{i}" for i in range(13)]


@pytest.mark.parametrize("p", range(7))
def test_g0_to_g6_are_inference_checks_processes_unchanged(world, p):
    c = world["ctx"]
    a, _ = icp.draw(p, np.random.default_rng(5), c)
    b = original_made_up(c["region_all"], c["state_all"], c["owner_all"], np.random.default_rng(5), ic.GRID[icp.PROCESSES[p]])
    assert np.array_equal(a, b)


def test_g7_triples_own_noise_at_the_seven_units_from_the_weights_and_nowhere_else(world):
    d, c = world["d"], world["ctx"]
    wt = ic.implied_weights(d)
    net = ic.net_weights(wt).net_weight.sort_values(ascending=False, kind="stable")
    head = wt[wt.is_host & wt.event_year.isin(ps.HEADLINE)].groupby("utility").weight.sum().sort_values(ascending=False, kind="stable")
    want = [icp.label(k) for k in list(net.index[:5]) + list(head.index[:2])]
    q = world["quantities"]["g7_units"]
    assert [x["utility"] for x in q["comparison_utilities"] + q["hosts"]] == want
    diff, _ = increment(world, 7)
    rows = sorted(d.unit_code[(int(u.split(":")[0]), u.split(":")[1])] for u in want)
    assert sorted(np.flatnonzero(np.abs(diff).max(1) > 0)) == rows                  # only those units move
    # their own part is exactly three times G0's: G7 minus G0 is twice G0's own part there
    dgp = ic.GRID["G0_as_in_D38"]
    rng = np.random.default_rng(11)
    n, years = c["region_all"].shape
    rng.normal(0, dgp["region_step_sd"], (int(c["region_all"].max()) + 1, years))
    rng.normal(0, 1.0, (int(c["state_all"].max()) + 1, years))
    e = rng.normal(0, 1.0, (n, years))
    for t in range(1, years):
        e[:, t] += dgp["own_rho"] * e[:, t - 1]
    assert diff[rows] == pytest.approx(2 * dgp["own_sd"] * e[rows], abs=1e-12)
    assert np.array_equal(c["g7_scale"], icp.build_context(d, world["regions"], world["q"], table([]), None, "x", boot=19)["ctx"]["g7_scale"])


def g8_world(suppliers):
    d, regions, q, usable = invented_design(hosts=2, comps=14)
    own = table([{"utility_id_eia": 100, "ultimate_parent": "Parent X", "from_year": 2001, "to_year": 2025},
                 {"utility_id_eia": 101, "ultimate_parent": "Parent X", "from_year": 2001, "to_year": 2025}])
    return d, icp.build_context(d, regions, q, own, suppliers, "test", boot=19)


def suppliers_table(rows):
    base = {"state": "", "name": "x", "supplier_kind": "g_and_t", "from_year_basis": "documented", "to_year_basis": "documented",
            "source_url": "https://example.org", "source_kind": "filing", "quote": "q", "date_opened": "2026-11-18", "note": ""}
    t = pd.DataFrame([{**base, **r} for r in rows], columns=list(icp.SUPPLIER_COLUMNS))
    return t.astype({"utility_id_eia": int, "from_year": int, "to_year": int})


def test_g8_units_of_one_parent_share_its_shock_and_an_unknown_supplier_gives_none():
    sup = suppliers_table([{"utility_id_eia": 102, "supplier": "Coop Supply", "from_year": 2001, "to_year": 2025},
                           {"utility_id_eia": 103, "supplier": "Coop Supply", "from_year": 2001, "to_year": 2025},
                           {"utility_id_eia": 104, "supplier": "unknown", "from_year": 2001, "to_year": 2025}])
    d, built = g8_world(sup)
    world = {"ctx": built["ctx"]}
    diff, _ = increment(world, 8)
    row = lambda u: d.unit_code[[k for k in d.unit_code if k[0] == u][0]]  # noqa: E731
    assert np.array_equal(diff[row(100)], diff[row(101)])                       # one parent, one shock
    assert not np.allclose(diff[row(102)], diff[row(103)])                       # own companies differ ...
    g = built["ctx"]["g8"]
    # ... while their supplier shock is shared: each carries one own-company shock and the one supplier shock
    for u in (102, 103):
        assert sum(1 for i in range(len(g["unit"])) if g["unit"][i] == row(u) and g["year"][i] == 0) == 2
    assert sum(1 for i in range(len(g["unit"])) if g["unit"][i] == row(104) and g["year"][i] == 0) == 1     # unknown: none
    assert built["quantities"]["g8"]["suppliers"] == 1 and built["quantities"]["g8"]["companies"] == 1


def test_g8_reads_the_same_parents_as_the_ownership_module():
    own = table([{"utility_id_eia": 100, "ultimate_parent": "P", "from_year": 2005, "to_year": 2012},
                 {"utility_id_eia": 100, "ultimate_parent": "Q", "from_year": 2012, "to_year": 2025, "state": "AB"},
                 {"utility_id_eia": 101, "ultimate_parent": "Q", "from_year": 2001, "to_year": 2025}])
    keys = [(100, "AB"), (100, "BB"), (101, "BB")]
    g = icp.g8_loadings(keys, own, None)
    names = {}
    # rebuild the entity names in first-seen order to read back each unit-year's parents
    order = []
    for u, key in enumerate(keys):
        for t, y in enumerate(YEARS):
            ps_ = sorted(own_rules.parents(own, key, [y]))
            order += [f"company:{p}" for p in ps_] or [f"company:own:{icp.label(key)}"]
    for n in order:
        names.setdefault(n, len(names))
    inv = {i: n for n, i in names.items()}
    for u, key in enumerate(keys):
        for t, y in enumerate(YEARS):
            got = sorted(inv[g["entity"][i]] for i in np.flatnonzero((g["unit"] == u) & (g["year"] == t)))
            want = sorted(f"company:{p}" for p in own_rules.parents(own, key, [y])) or [f"company:own:{icp.label(key)}"]
            assert got == want, (key, y)
            assert g["weight"][(g["unit"] == u) & (g["year"] == t)].sum() == pytest.approx(1.0)   # the mean in a sale year


def test_g8_without_the_supplier_table_stops_in_words_unless_the_labelled_flag(tmp_path):
    with pytest.raises(icp.Refused, match="--g8-ownership-only"):
        icp.load_suppliers(tmp_path / "suppliers.csv")
    t, mode = icp.load_suppliers(tmp_path / "suppliers.csv", ownership_only=True)
    assert t is None and "ownership only" in mode
    (tmp_path / "suppliers.csv").write_text("utility_id_eia,state,supplier\n1,AA,X\n")
    with pytest.raises(icp.Refused, match="lacks columns"):
        icp.load_suppliers(tmp_path / "suppliers.csv")


def test_g9_loads_the_regional_walk_unequally(world):
    diff, _ = increment(world, 9)
    assert np.linalg.matrix_rank(diff, tol=1e-10) == 1                        # one region here: (loading - 1) times its walk
    assert np.unique(np.round(diff[:, -1] / diff[0, -1], 8)).size > 5


def test_g10_adds_a_trend_of_its_own_to_each_utility(world):
    diff, _ = increment(world, 10)
    t = np.arange(diff.shape[1])
    slopes = diff[:, 1]
    assert diff == pytest.approx(slopes[:, None] * t[None, :], abs=1e-12)
    assert 0.002 < slopes.std() < 0.009


def test_g11_and_g12_load_one_national_walk_and_record_the_realised_change(world):
    c = world["ctx"]
    diff, change = increment(world, 11)
    share = c["share_state"][c["state_all"]]
    walk = diff[np.argmax(share)] / share.max()
    assert diff == pytest.approx(share[:, None] * walk[None, :], abs=1e-12)
    manual = sum(w * (0.5 * (walk[g + 2 - 2001] + walk[g + 3 - 2001]) - walk[g - 3 - 2001]) for g, w in c["hosts"])
    assert change == pytest.approx(manual, abs=1e-12)
    assert sum(w for _, w in c["hosts"]) == pytest.approx(1.0, abs=1e-9)
    diff12, change12 = increment(world, 12)
    assert np.linalg.matrix_rank(diff12, tol=1e-10) == 1
    same_state = [np.flatnonzero(c["state_all"] == s) for s in np.unique(c["state_all"])]
    for rows in same_state:
        assert np.allclose(diff12[rows], diff12[rows[0]])                       # the state's deviation is fixed in the dataset
    assert change12 == pytest.approx(change, abs=1e-15)                          # the unloaded walk: the same draw on the same seed


# ---- units outside the design: a state with no gas share, a unit with no region ------------------------------------

def territory_design():
    treated, clean, q, regions, dd, usable = invented_design(hosts=3, comps=16, cohorts=(2014, 2016), territory=True)
    d = design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, ownership=table([]), usable=usable, gas=GAS,
                                unknown_load=ps.UnknownLoad.none("invented data: no load-unknown site"))
    return d, regions, q


def test_the_design_never_takes_a_unit_whose_state_has_no_gas_share():
    """build_windows keeps a unit only with a fuel-mix group (the same file as the gas share), so the territory's host is
    dropped by name and its utilities, though nearest in size, are matched to no one; they stay in the panel's unit codes."""
    d, _, _ = territory_design()
    assert {"utility": f"90:{TERRITORY}", "cohort": 2014,
            "why": "no region, fuel-mix group or degree days in every year of its window"} in d.dropped
    assert all(TERRITORY not in {k[1] for k in w.keys} for w in d.windows.values())
    assert all(k[1] != TERRITORY for mk in d.hosts.match_keys for k in mk) and len(d.hosts) == 3
    assert any(k[1] == TERRITORY for k in d.unit_code) and TERRITORY in d.state_code


def test_g11_and_g12_give_a_state_with_no_gas_share_no_walk_and_say_so():
    d, regions, q = territory_design()
    built = icp.build_context(d, regions, q, table([]), None, "test", boot=19)
    c = built["ctx"]
    assert built["quantities"]["states_with_no_gas_share_given_no_fuel_walk"] == [TERRITORY]
    rows = [d.unit_code[k] for k in d.unit_code if k[1] == TERRITORY]
    for p in (11, 12):
        diff, change = increment({"ctx": c}, p)
        assert np.abs(diff[rows]).max() == 0.0 and np.abs(np.delete(diff, rows, axis=0)).max() > 0 and change is not None
    y, boot, _ = icp.dataset(1, 12, 0, c)
    assert np.isfinite(y).all()


def test_a_design_row_in_a_state_with_no_gas_share_stops_in_words():
    d, regions, q = territory_design()
    d.gas = {k: v for k, v in GAS.items() if k != d.hosts.state.iloc[0]}
    with pytest.raises(icp.Refused, match="no 2008-2010 gas share"):
        icp.build_context(d, regions, q, table([]), None, "test", boot=19)


def test_a_design_row_with_no_region_in_an_observed_year_stops_in_words():
    d, regions, q = territory_design()
    host = d.hosts.key.iloc[0]
    year = int(d.hosts.cohort.iloc[0])
    gone = regions[~((regions.utility_id_eia == host[0]) & (regions.state == host[1]) & (regions.year == year))]
    with pytest.raises(icp.Refused, match="no market region"):
        icp.build_context(d, gone, q, table([]), None, "test", boot=19)


def test_units_outside_the_design_with_no_region_or_ownership_class_are_defined_and_counted():
    d, regions, q = territory_design()
    terr = [k for k in d.unit_code if k[1] == TERRITORY]
    gone = regions[~regions.utility_id_eia.isin([k[0] for k in terr])]                 # no region in any year
    q2 = q.assign(ownership=np.where(q.utility_id_eia.isin([k[0] for k in terr]), "federal", q.ownership))
    built = icp.build_context(d, gone, q2, table([]), None, "test", boot=19)
    assert built["quantities"]["design_units_with_an_ownership_class_outside_the_three"] == 0
    for p in range(13):
        y, _, _ = icp.dataset(2, p, 0, built["ctx"])
        assert np.isfinite(y).all()


# ================================================================================================================
# Seeds (E1.5)
# ================================================================================================================

def test_each_dataset_has_its_own_seed_and_a_separate_bootstrap_stream(world):
    c = world["ctx"]
    y1, b1, _ = icp.dataset(7, 3, 12, c)
    y2, b2, _ = icp.dataset(7, 3, 12, c)
    assert np.array_equal(y1, y2) and np.array_equal(icp.bootstrap_weights(b1, 19, 4), icp.bootstrap_weights(b2, 19, 4))
    assert not np.array_equal(y1, icp.dataset(7, 3, 13, c)[0]) and not np.array_equal(y1, icp.dataset(7, 4, 12, c)[0])
    assert not np.array_equal(y1, icp.dataset(8, 3, 12, c)[0])
    # the data stream never touches the bootstrap stream: drawing weights first changes nothing in the dataset
    rng, boot = icp.streams(7, 3, 12)
    icp.bootstrap_weights(boot, 999, 50)
    P, _ = icp.draw(3, rng, c)
    assert np.array_equal(P[c["obs_unit"], c["obs_year"]], y1)


def test_every_candidate_sees_the_same_dataset_and_removing_one_changes_nothing_for_the_others(world):
    c = world["ctx"]
    y, boot, _ = icp.dataset(1, 11, 4, c)
    every = icp.run_candidates(y, boot, c)
    for names in (["A", "C"], ["C", "B"], ["B"], ["C", "A"]):
        some = icp.run_candidates(y, boot, c, names)
        for n in names:
            assert json.dumps(some[n], default=str) == json.dumps(every[n], default=str)


def test_results_do_not_depend_on_the_worker_count_and_a_run_resumes_block_by_block(world, tmp_path):
    c = world["ctx"]
    man = {"stage": "t", "seed": 5, "datasets_per_process": 3, "candidates": list(c["names"]), "fingerprint_sha256": "x"}
    one = icp.run_blocks("t", 5, c, tmp_path / "w1", 3, 1, man)
    three = icp.run_blocks("t", 5, c, tmp_path / "w3", 3, 3, man)
    dump = lambda r: json.dumps(r, default=str, sort_keys=True)  # noqa: E731
    assert dump(one) == dump(three) and len(one) == 13 * 3
    victim = tmp_path / "w1" / "block_05_00000.json"
    victim.unlink()
    again = icp.run_blocks("t", 5, c, tmp_path / "w1", 3, 1, man)
    assert dump(again) == dump(one) and victim.exists()
    with pytest.raises(icp.Refused, match="seed"):
        icp.run_blocks("t", 6, c, tmp_path / "w1", 3, 1, {**man, "seed": 6})


# ================================================================================================================
# The screen and the ranking (E1.2, E2.1 to E2.3)
# ================================================================================================================

def test_the_screen_threshold_comes_from_the_binomial_and_is_241_at_2000():
    thr = icp.screen_threshold(2000)
    assert thr == 241
    assert stats.binom.sf(240, 2000, 0.10) <= 0.05 / 26 < stats.binom.sf(239, 2000, 0.10)


def cells(**over):
    base = {f"{p}: {k}": 200 for p in icp.PROCESSES for k in ("range_misses_the_true_value", "early_years_test_rejects_a_flat_history")}
    return {**base, **over}


def test_a_cell_at_241_excludes_and_240_does_not():
    w = {c: np.ones(50) for c in "ABC"}
    s = {c: 0.0 for c in "ABC"}
    key = f"{icp.PROCESSES[4]}: early_years_test_rejects_a_flat_history"
    r = icp.select({"A": cells(**{key: 241}), "B": cells(**{key: 240}), "C": cells()}, w, s, 2000)
    assert r["screen"]["survivors"] == ["B", "C"] and r["screen"]["cells_at_or_over_the_threshold"]["A"] == [key]


def test_width_is_looked_at_only_after_the_screen():
    key = f"{icp.PROCESSES[0]}: range_misses_the_true_value"
    rng = np.random.default_rng(0)
    base = rng.uniform(1, 2, 400)
    w = {"A": base * 3, "B": base * 0.5, "C": base}                                # B is by far the narrowest ...
    r = icp.select({"A": cells(), "B": cells(**{key: 300}), "C": cells()}, w, {c: 0.0 for c in "ABC"}, 2000)
    assert r["selected"] == "C"                                                    # ... and is screened out first


def test_no_candidate_survives_selects_nothing_and_says_no_stage_2():
    key = f"{icp.PROCESSES[12]}: range_misses_the_true_value"
    r = icp.select({c: cells(**{key: 400}) for c in "ABC"}, {c: np.ones(10) for c in "ABC"}, {c: 0.0 for c in "ABC"}, 2000)
    assert r["selected"] is None and "No candidate survives" in r["statement"] and "No stage 2 is run" in r["statement"]


def test_paired_log_ratio_treats_infinities_as_the_rule_says():
    d = icp.paired_log_ratio([1.0, np.inf, np.inf, 2.0], [2.0, np.inf, 1.0, np.inf])
    assert d[0] == pytest.approx(np.log(0.5)) and d[1] == 0.0 and d[2] == np.inf and d[3] == -np.inf


def test_narrower_needs_the_whole_interval_for_the_median_below_zero():
    rng = np.random.default_rng(1)
    w = rng.uniform(1, 2, 2000)
    assert icp.narrower(w * 0.9, w)[0]                                            # uniformly narrower
    assert not icp.narrower(w, w)[0]                                             # identical: d = 0, tied
    mixed = w * np.where(np.arange(2000) % 2 == 0, 0.9, 1.1)                       # narrower half the time: tied
    assert not icp.narrower(mixed, w)[0]
    infinite = np.where(np.arange(2000) < 1100, np.inf, w * 0.5)                   # infinite more than half the time
    assert not icp.narrower(infinite, w)[0] and icp.narrower(w, infinite)[0]
    both = np.full(2000, np.inf)
    assert not icp.narrower(both, both)[0]                                       # both infinite everywhere: d = 0


def test_the_order_statistic_interval_has_at_least_95pct_coverage():
    for n in (100, 2000, 26000):
        r = icp.median_interval_order(n)
        assert 1 - 2 * stats.binom.cdf(r - 1, n, 0.5) >= 0.95 > 1 - 2 * stats.binom.cdf(r, n, 0.5)


def test_a_tie_including_the_bootstrap_as_built_goes_to_it():
    rng = np.random.default_rng(2)
    w = rng.uniform(1, 2, 2000)
    r = icp.select({c: cells() for c in "ABC"}, {"A": w, "B": w * 0.999 * np.where(np.arange(2000) % 2, 0.8, 1.25), "C": w * 1.5},
                   {c: 0.0 for c in "ABC"}, 2000)
    assert r["selected"] == "A"


def test_a_strictly_narrower_b_beats_a():
    rng = np.random.default_rng(3)
    w = rng.uniform(1, 2, 2000)
    r = icp.select({c: cells() for c in "ABC"}, {"A": w, "B": w * 0.8, "C": w * 1.5}, {c: 0.0 for c in "ABC"}, 2000)
    assert r["selected"] == "B"


@pytest.mark.parametrize("sb, sc, want", [(0.01, 0.02, "B"), (0.03, 0.02, "C"), (0.02, 0.02, "C")])
def test_b_tied_with_c_goes_to_fewer_incomplete_and_failed_ranges_then_to_c(sb, sc, want):
    rng = np.random.default_rng(4)
    w = rng.uniform(1, 2, 2000)
    alt = w * np.where(np.arange(2000) % 2, 0.8, 1.25)
    key = f"{icp.PROCESSES[0]}: range_misses_the_true_value"
    r = icp.select({"A": cells(**{key: 999}), "B": cells(), "C": cells()}, {"A": w, "B": w, "C": alt}, {"A": 0.0, "B": sb, "C": sc}, 2000)
    assert r["selected"] == want


# ================================================================================================================
# Summaries: failures, realised paths
# ================================================================================================================

def rec(process, **kw):
    base = cd.result("A", estimate=0.01, covered=True, early_rejected=False, lo=-0.1, hi=0.1, lo_state=cd.BOUNDED, hi_state=cd.BOUNDED)
    return {"process": process, "k": 0, "realised_change": kw.pop("change", None), "results": {"A": {**base, **kw}}}


def test_a_failure_counts_as_a_miss_and_a_rejection_and_is_reported_apart():
    p = icp.PROCESSES[0]
    failed = cd.result("A", failure={"cause": cd.NON_FINITE_BOOTSTRAP_T, "where": "range", "detail": ""})
    records = [rec(p) for _ in range(8)] + [rec(p, covered=False, miss=True)] + [{"process": p, "k": 9, "realised_change": None, "results": {"A": failed}}]
    for q in icp.PROCESSES[1:]:
        records.append(rec(q))
    s = icp.summarise_stage(records, ["A"], 10)["A"]["by_process"][p]
    assert s["range_misses_the_true_value"]["count"] == 2 and s["early_years_test_rejects_a_flat_history"]["count"] == 1
    assert s["numerical_failures"] == {"count": 1, "causes": {cd.NON_FINITE_BOOTSTRAP_T: 1}, "where": {"range": 1}}
    assert s["ordinary_misses"] == 1 and s["ordinary_rejections"] == 0 and s["rates_include_failure_penalties"]
    assert s["widths"]["infinite"] == 1 and s["end_states_by_side"]["lo"][cd.FAILED] == pytest.approx(0.1)


def test_the_realised_path_statistics_for_g11_and_g12():
    rs = [cd.result("A", estimate=2.0 * x, covered=abs(x) < 0.5, early_rejected=False, lo=-1, hi=1, lo_state=cd.BOUNDED, hi_state=cd.BOUNDED)
          for x in np.linspace(-1, 1, 9)]
    out = icp.realised_path(rs, list(np.linspace(-1, 1, 9)))
    assert out["slope_of_the_estimate_on_the_realised_change"] == pytest.approx(2.0)
    assert out["root_mean_square_error"] == pytest.approx(np.sqrt(np.mean((2 * np.linspace(-1, 1, 9)) ** 2)))
    small, mid, big = out["thirds_by_size_of_the_realised_change"]
    assert small["range_misses"]["count"] == 0 and big["range_misses"]["count"] == 3


# ================================================================================================================
# The benchmark, the budget and the two stages
# ================================================================================================================

FORBIDDEN = ("rate", "estimate", "range", "p_value", "pvalue", "width", "state", "failure", "covered", "miss", "reject", "endpoint",
             "power", "lower", "upper", "detect", "verdict")


def all_keys(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from all_keys(v)
    elif isinstance(x, list):
        for v in x:
            yield from all_keys(v)


def test_the_benchmark_writes_timings_and_no_performance_key(world, tmp_path):
    r = icp.benchmark(world["ctx"], world["fp"], 2, tmp_path / "bench.json", datasets=1)
    keys = list(all_keys(json.loads((tmp_path / "bench.json").read_text())))
    bad = [k for k in keys if k not in icp.PROCESSES and any(f in k.lower() for f in FORBIDDEN)]   # process names are labels
    assert not bad, bad
    sec = r["seconds_a_dataset"]["by_candidate_and_process"]
    assert set(sec) == set("ABC") and all(len(v) == 13 and all(x > 0 for x in v.values()) for v in sec.values())
    assert r["seed"] == 20261130 and r["workers"] == 2 and r["fingerprint"] == world["fp"]
    # the worker returns nothing but timings
    icp._init(world["ctx"])
    rows = icp._timed((icp.SEEDS["benchmark"], [(0, 0)]))
    assert set(rows[0]) == {"process", "generation", "candidates"} and set(rows[0]["candidates"]) == set("ABC")


def test_projected_hours_follow_e53():
    gen = {p: 0.1 for p in icp.PROCESSES}
    sec = {n: {p: s for p in icp.PROCESSES} for n, s in (("A", 1.0), ("B", 2.0), ("C", 0.5))}
    h = icp.projections(sec, gen)
    assert h["stage1_all_three_candidates_2000_a_process"] == pytest.approx(1.25 * 2000 * 13 * 3.6 / 36000, rel=1e-4)
    assert h["validation_by_candidate"]["B"]["20000"] == pytest.approx(1.25 * 20000 * 13 * 2.1 / 36000, rel=1e-4)


def fake_benchmark(path, fp, stage1_hours=1.0, validation=None):
    validation = validation or {n: {"20000": 50.0, "10000": 25.0, "5000": 12.5} for n in "ABC"}
    icp._write_json(path, {"fingerprint": fp, "projected_hours": {"stage1_all_three_candidates_2000_a_process": stage1_hours,
                                                                   "validation_by_candidate": validation}})


def test_the_budget_takes_the_largest_rung_under_72_hours_from_timings_alone(tmp_path):
    fake_benchmark(tmp_path / "b.json", {"sha256": "f"}, validation={"A": {"20000": 71.9, "10000": 36, "5000": 18},
                                                                     "B": {"20000": 150, "10000": 75, "5000": 37.5},
                                                                     "C": {"20000": 400, "10000": 200, "5000": 100}})
    b = icp.write_budget(tmp_path / "b.json", tmp_path / "budget.json")["datasets_per_process_by_candidate"]
    assert b == {"A": 20000, "B": 5000, "C": icp.NONE_FITS}
    with pytest.raises(icp.Refused, match="benchmark"):
        icp.write_budget(tmp_path / "none.json", tmp_path / "budget.json")


def test_stage1_refuses_without_the_benchmark_and_the_budget(world, tmp_path):
    ctx, fp, q = world["ctx"], world["fp"], world["quantities"]
    with pytest.raises(icp.Refused, match="benchmark"):
        icp.stage1(ctx, fp, q, tmp_path, tmp_path / "runs", 1, datasets=2)
    fake_benchmark(tmp_path / icp.PATHS["benchmark"], {"sha256": "another"})
    with pytest.raises(icp.Refused, match="another fingerprint"):
        icp.stage1(ctx, fp, q, tmp_path, tmp_path / "runs", 1, datasets=2)
    fake_benchmark(tmp_path / icp.PATHS["benchmark"], fp, stage1_hours=12.5)
    with pytest.raises(icp.Refused, match="twelve-hour"):
        icp.stage1(ctx, fp, q, tmp_path, tmp_path / "runs", 1, datasets=2)
    fake_benchmark(tmp_path / icp.PATHS["benchmark"], fp, stage1_hours=11.9)
    with pytest.raises(icp.Refused, match="budget"):
        icp.stage1(ctx, fp, q, tmp_path, tmp_path / "runs", 1, datasets=2)
    assert not (tmp_path / "runs").exists()                                     # nothing was drawn


def test_stage1_and_stage2_end_to_end_on_an_invented_design(world, tmp_path):
    ctx, fp, q = world["ctx"], world["fp"], world["quantities"]
    icp.benchmark(ctx, fp, 1, tmp_path / icp.PATHS["benchmark"], datasets=1)
    icp.write_budget(tmp_path / icp.PATHS["benchmark"], tmp_path / icp.PATHS["budget"])
    r = icp.stage1(ctx, fp, q, tmp_path, tmp_path / "runs", 1, datasets=3)
    assert r["seed"] == 20261201 and set(r["by_candidate"]) == set("ABC")
    cell = r["by_candidate"]["B"]["by_process"][icp.PROCESSES[11]]
    assert {"range_misses_the_true_value", "early_years_test_rejects_a_flat_history", "numerical_failures", "end_states_by_side",
            "widths", "power_at_a_planted_5pct_ramp", "realised_path"} <= set(cell)
    assert "realised_path" not in r["by_candidate"]["B"]["by_process"][icp.PROCESSES[0]]
    assert r["selection"]["screen"]["threshold_count"] == icp.screen_threshold(3)
    s1 = json.loads((tmp_path / icp.PATHS["stage1"]).read_text())
    s1["selection"]["selected"] = "C"                                            # whatever stage 1 chose is what stage 2 runs
    icp._write_json(tmp_path / icp.PATHS["stage1"], s1)
    asked = []

    def ctx_for(name):
        asked.append(name)
        built = icp.build_context(world["d"], world["regions"], world["q"], table([]), None, "ownership only (test)", boot=19, names=[name])
        return built["ctx"]
    r2 = icp.stage2(ctx_for, fp, q, tmp_path, tmp_path / "runs", 1, datasets=2)
    assert asked == ["C"] and r2["candidate"] == "C" and r2["seed"] == 20261202
    assert r2["range"]["verdict"] in (icp.PASSED, icp.EXCESS, icp.IMPRECISE)
    with pytest.raises(icp.Refused, match="never extended"):
        icp.stage2(ctx_for, fp, q, tmp_path, tmp_path / "runs", 1, datasets=4)


def test_stage2_refuses_when_stage1_selected_nothing_or_no_budget_fits_or_another_seed(world, tmp_path):
    fp = world["fp"]
    icp._write_json(tmp_path / icp.PATHS["stage1"], {"fingerprint": fp, "selection": {"selected": None}})
    with pytest.raises(icp.Refused, match="no stage 2"):
        icp.stage2(lambda n: None, fp, {}, tmp_path, tmp_path / "runs", 1)
    icp._write_json(tmp_path / icp.PATHS["stage1"], {"fingerprint": fp, "selection": {"selected": "B"}})
    icp._write_json(tmp_path / icp.PATHS["budget"], {"fingerprint": fp, "datasets_per_process_by_candidate": {"B": icp.NONE_FITS}})
    with pytest.raises(icp.Refused, match="no validation budget"):
        icp.stage2(lambda n: None, fp, {}, tmp_path, tmp_path / "runs", 1)
    icp._write_json(tmp_path / icp.PATHS["budget"], {"fingerprint": fp, "datasets_per_process_by_candidate": {"B": 5000}})
    icp._write_json(tmp_path / "runs" / "stage2" / "manifest.json", {"seed": 1234})
    with pytest.raises(icp.Refused, match="another seed"):
        icp.stage2(lambda n: None, fp, {}, tmp_path, tmp_path / "runs", 1)
    icp._write_json(tmp_path / icp.PATHS["stage1"], {"fingerprint": {"sha256": "other"}, "selection": {"selected": "B"}})
    with pytest.raises(icp.Refused, match="another fingerprint"):
        icp.stage2(lambda n: None, fp, {}, tmp_path, tmp_path / "runs", 1)


@pytest.mark.parametrize("counts, want", [
    ({p: 180 for p in icp.PROCESSES}, icp.PASSED),                                 # 9.0% of 2,000: bound 10.05%
    ({**{p: 180 for p in icp.PROCESSES}, icp.PROCESSES[3]: 230}, icp.EXCESS),      # 11.5% measured
    ({**{p: 180 for p in icp.PROCESSES}, icp.PROCESSES[3]: 210}, icp.IMPRECISE),   # 10.5%: bound 11.6%, measured under 11%
])
def test_stage2_has_three_verdicts(counts, want):
    assert icp.verdict(counts, 2000)["verdict"] == want


def test_the_upper_bound_is_the_rate_plus_1645_standard_errors():
    v = icp.verdict({icp.PROCESSES[0]: 100}, 1000)["by_process"][icp.PROCESSES[0]]
    assert v["upper_bound_95"] == pytest.approx(0.1 + 1.645 * np.sqrt(0.09 / 1000), abs=1e-5)


def test_main_stops_in_words_without_a_subcommand(capsys):
    assert icp.main([]) == 2
