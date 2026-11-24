"""The design side of the runs that move event dates (pipeline/analysis/inventory_runs.py): E4(a) the slow path, E4(b)
anchoring off, E7's redraw, the later-start shift, and the common core that re-dates hosts and applies G-a.

Invented inputs only: every inventory, dose and quantity frame is built here. No file under data/ is read; the price hold
and the set-aside list are passed in as empty sets so that none is read.
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

from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import inventory_runs as ir  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.facilities import corrections as cx  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_matching_rules import COOP, FUEL, ladder, table, world  # noqa: E402

YEARS = list(range(2001, 2026))
GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
NONE = ps.UnknownLoad.none("invented data: no load-unknown site")
TOL = 1e-9
HOST = (1, "AA")
THRESHOLD_MW = 80.0                       # the host's 2% line: base sales such that 80 MW of load is 2%
HOST_BASE_GWH = THRESHOLD_MW * 8.76 / 0.02


# ---- an invented inventory -------------------------------------------------------------------------------------------

def site(fid, state, utility, mw, start, latest_permit=None, date_basis=cx.PERMIT_LABEL, measured=False):
    return dict(fid=fid, state=state, utility=utility, mw=mw, start=start, latest_permit=latest_permit,
                date_basis=date_basis, measured=measured)


def ramp(mw, start, y):
    """The default three-year ramp written out by hand: a third in the start year, two thirds the next, full after."""
    age = y - start
    return 0.0 if age < 0 else mw * min(1.0, (age + 1) / 3.0)


def inventory(sites, epri: dict, base_gwh: dict, evidence=None, entries=()):
    """An Inventory built the way build_inventory builds one: each state's factor from its 2024 permit-based and measured
    totals against `epri` (TWh), permit-based rows scaled by it, site-years on the three-year ramp."""
    rows = []
    for s in sites:
        rows.append({"fid": s["fid"], "state": s["state"], "src": "bi", "load_history": "three_year_ramp",
                     "mw_basis": "verified_public_figure" if s["measured"] else "generator_capacity_x_kappa",
                     "energized_year": float(s["start"]) if s["start"] is not None else np.nan,
                     "mw_full_raw": float(s["mw"]), "generator_kw": float(s["mw"]) * 2000.0,
                     "utility_id_eia": float(s["utility"]) if s["utility"] is not None else np.nan,
                     "utility_assign": "unique", "utility_candidates": str(s["utility"]), "is_crypto": False,
                     "date_basis": s["date_basis"],
                     "first_permit_year": float(s["start"] - 1) if s["start"] is not None else np.nan,
                     "latest_permit_year": float(s["latest_permit"]) if s["latest_permit"] is not None else np.nan,
                     "load_unknown": False, "date_inventory_year": np.nan})
    fac = pd.DataFrame(rows).set_index("fid")
    measured = fac.mw_basis.eq("verified_public_figure")
    a24 = pd.Series({f: (ramp(r.mw_full_raw, r.energized_year, 2024) if pd.notna(r.energized_year) else 0.0) * 8.76 / 1000
                     for f, r in fac.iterrows()})
    states = sorted(fac.state.unique())
    permit = a24[~measured].groupby(fac.state[~measured]).sum().reindex(states).fillna(0.0)
    meas = a24[measured].groupby(fac.state[measured]).sum().reindex(states).fillna(0.0)
    factor = pd.Series({st: px._factor(epri[st], meas[st], permit[st]) for st in states})
    fac["state_scale"] = np.where(measured, 1.0, fac.state.map(factor))
    fac["mw_full"] = fac.mw_full_raw * fac.state_scale
    fac["in_dose"] = fac.energized_year.notna() & fac.utility_id_eia.notna()
    fy = [(f, int(r.utility_id_eia), r.state, y, ramp(r.mw_full, r.energized_year, y), False)
          for f, r in fac[fac.in_dose].iterrows() for y in YEARS if ramp(r.mw_full, r.energized_year, y) > 0]
    fy = pd.DataFrame(fy, columns=["fid", "utility_id_eia", "state", "year", "mw", "crypto"])
    units = pd.MultiIndex.from_tuples(sorted(base_gwh), names=ir.KEY)
    base = pd.Series([base_gwh[k] for k in sorted(base_gwh)], index=units, name="base_retail_gwh")
    anchor = pd.DataFrame({"epri_twh": pd.Series(epri), "permit_twh": permit, "epoch_twh": meas, "factor": factor})
    return ir.build_inputs(fac, fy, units, base, pd.Series("West", index=units), pd.Series("x", index=units), anchor, {},
                           list(entries), evidence)


# ---- an invented design world: the host plus twelve cooperative comparison utilities, everyone in "West" ----------------

def context(comps=None, usable=None):
    comps = comps if comps is not None else ladder(10, 12)
    _, _, q, regions, dd = world([(1, "AA", 10_000, COOP)], comps)
    if usable is None:
        usable = {(u, st, y) for u, st, *_ in [(1, "AA")] + comps for y in YEARS}
    ctx = ir.Context(q, regions, FUEL, dd, ps.HEADLINE_RULES, table([]), usable, GAS, ps.ownership_classes(q), NONE, 0.02,
                     history={}, aside=set(), hold=set())
    return ctx


def headline_reference(ctx, dose):
    """The headline pathway on invented inputs: power_simulation.design, then design.build_with_rules."""
    treated, clean = ps.design(ctx.q, dose, ctx.theta, ctx.history, hold=ctx.hold)
    d = dsg.build_with_rules(treated, clean, ctx.q, ctx.regions, ctx.fuel, ctx.dd, ctx.rules, ownership=ctx.ownership,
                             usable=ctx.usable, gas=ctx.gas, ownership_of=ctx.ownership_of, unknown_load=ctx.unknown, theta=ctx.theta)
    return treated, clean, d


def slow_world(**kw):
    """State AA, factor one as built (EPRI equals the 2024 permit total, 210 MW):
       s1 on the host, 100 MW, start 2010, latest permit 2015: slow path full in 2016 (a seven-year ramp);
       s2 on utility 10, 50 MW, start 2005, no later permit: the slow path is the ramp;
       s3 on utility 11, 60 MW, start 2022, latest permit 2026: full in 2024 on the ramp, half on the slow path (six years).
    """
    sites = [site("s1", "AA", 1, 100.0, 2010, 2015), site("s2", "AA", 10, 50.0, 2005), site("s3", "AA", 11, 60.0, 2022, 2026)]
    epri = {"AA": 210.0 * 8.76 / 1000}
    base = {HOST: HOST_BASE_GWH, (10, "AA"): 1e9, (11, "AA"): 1e9}
    return inventory(sites, epri, base, **kw)


# ---- E4(a), the slow path ----------------------------------------------------------------------------------------------

def test_the_slow_path_moves_the_hosts_crossing_by_two_years_and_the_factor_is_recomputed_by_hand():
    inv = slow_world()
    rb, rec = ir.e4a(inv)
    assert set(ir.slow_path_rows(inv)[0]) == {"s1", "s3"}                 # s2's slow path equals its ramp
    assert rec["not_moved"]["slow_path_equals_the_ramp"] == 1
    # By hand: as built the 2024 permit total is 210 MW (all three full), so the factor is 1. On the slow path s3 is at
    # (2024 - 2022 + 1) / 6 = 1/2 of 60 MW in 2024, s1 and s2 are full, so the total is 180 MW and the factor 210 / 180.
    assert rb.factors["AA"]["as_built"] == pytest.approx(1.0, abs=TOL)
    assert rb.factors["AA"]["alternative"] == pytest.approx(210.0 / 180.0, abs=TOL)
    # s1 on the slow path at that factor: 100 x 7/6 x (y - 2010 + 1) / 7 reaches 80 MW first in 2014 (83.3), not 2013 (66.7).
    f = 210.0 / 180.0
    s1 = rb.fy[rb.fy.fid == "s1"].set_index("year").mw
    for y, k in ((2010, 1), (2013, 4), (2014, 5), (2016, 7), (2020, 7)):
        assert s1[y] == pytest.approx(100.0 * f * k / 7.0, abs=TOL)
    as_built = ir.crossings(ir.dose_frame(inv.fy, inv.base), 0.02, {})
    alt = ir.crossings(ir.dose_frame(rb.fy, inv.base), 0.02, {})
    assert as_built[HOST] == ("cohort", 2012)                           # the ramp: 100 MW in 2012
    assert alt[HOST] == ("cohort", 2014)
    # s2 is not on the slow path; only the factor moves it.
    s2 = rb.fy[rb.fy.fid == "s2"].set_index("year").mw
    assert s2[2010] == pytest.approx(50.0 * f, abs=TOL)


def test_rows_the_plan_does_not_move_stay_on_their_histories():
    inv = slow_world()
    inv.fac.loc["s1", "load_history"] = "single_building_record"         # a single building (county rule or buildout.csv)
    changed, rec = ir.slow_path_rows(inv)
    assert "s1" not in changed and rec["not_moved"]["single_building"] == 1
    inv2 = slow_world()
    inv2.inp.phases["s3"] = [(2022, 0.5), (2024, 1.0)]                 # a verified phased history (D-28)
    inv2.inp.hist["s3"] = ("phases", inv2.inp.phases["s3"])
    assert "s3" not in ir.slow_path_rows(inv2)[0]


# ---- E4(b), anchoring off ----------------------------------------------------------------------------------------------

def test_anchoring_off_puts_every_factor_at_one_and_leaves_measured_load_alone():
    sites = [site("p", "BB", 5, 40.0, 2008), site("m", "BB", 6, 30.0, 2008, measured=True)]
    epri = {"BB": (30.0 + 2 * 40.0) * 8.76 / 1000}                     # factor (EPRI - measured) / permit = 2
    inv = inventory(sites, epri, {(5, "BB"): 1e6, (6, "BB"): 1e6})
    assert inv.fac.state_scale["p"] == pytest.approx(2.0, abs=TOL)
    rb = ir.e4b(inv)
    assert rb.factors["BB"] == {"as_built": pytest.approx(2.0, abs=TOL), "alternative": 1.0}
    p = rb.fy[rb.fy.fid == "p"].set_index("year").mw
    m = rb.fy[rb.fy.fid == "m"].set_index("year").mw
    assert p[2020] == pytest.approx(40.0, abs=TOL) and p[2008] == pytest.approx(40.0 / 3, abs=TOL)
    assert m[2020] == pytest.approx(30.0, abs=TOL)


# ---- E7, the redraw --------------------------------------------------------------------------------------------------

def degenerate(k):
    return {c: np.array([float(k)]) for c in ("under_20", "20_to_50", "50_plus")}


def e7_world(evidence=None):
    sites = [site("permit", "AA", 1, 100.0, 2014), site("verified", "AA", 10, 30.0, 2012, date_basis="verified_public_source")]
    epri = {"AA": 130.0 * 8.76 / 1000}
    return inventory(sites, epri, {HOST: HOST_BASE_GWH, (10, "AA"): 1e9}, evidence=evidence)


@pytest.mark.parametrize("k", [1, 3, 5])
def test_a_degenerate_error_moves_a_permit_dated_site_by_exactly_k_each_way_and_leaves_a_verified_site_alone(k):
    inv = e7_world()
    rows = ir.e7_rows(inv, unsettled={})
    assert list(rows.redrawn.fid) == ["permit"] and rows.redrawn["size"].iloc[0] == "50_plus"
    early, h1 = ir.e7_starts(rows, degenerate(k), "earlier", 0)
    late, h2 = ir.e7_starts(rows, degenerate(k), "later", 0)
    assert early == {"permit": 2014.0 - k} and late == {"permit": 2014.0 + k} and not h1 and not h2
    for starts in (early, late):
        rb = ir.rebuild(inv, ir.e7_changed(rows, starts))
        v = rb.fy[rb.fy.fid == "verified"]
        assert v.year.min() == 2012                                    # the verified site's start is untouched
        p = rb.fy[rb.fy.fid == "permit"]
        assert p.year.min() == int(starts["permit"])


def test_the_four_unsettled_sites_carry_no_load_in_a_draw():
    inv = e7_world()
    rows = ir.e7_rows(inv, unsettled={"verified": "invented: status unsettled"})
    rb = ir.rebuild(inv, ir.e7_changed(rows, ir.e7_starts(rows, degenerate(0), "earlier", 0)[0]))
    assert rows.no_load == ["verified"] and not (rb.fy.fid == "verified").any()


def test_the_ramp_governs_at_the_panel_start_and_after_2025():
    inv = e7_world()
    rows = ir.e7_rows(inv, unsettled={})
    starts, _ = ir.e7_starts(rows, degenerate(14), "earlier", 0)        # 2014 - 14 = 2000
    assert starts == {"permit": 2000.0}
    rb = ir.rebuild(inv, ir.e7_changed(rows, starts))
    f = rb.factors["AA"]["alternative"]
    p = rb.fy[rb.fy.fid == "permit"].set_index("year").mw
    assert p[2001] == pytest.approx(100.0 * f * 2 / 3, abs=TOL)          # two thirds in 2001
    assert p[2002] == pytest.approx(100.0 * f, abs=TOL)                  # full from 2002
    for start in (1999.0, 1990.0):
        p = ir.rebuild(inv, {"permit": ("ramp", start)}).fy.query("fid == 'permit'").set_index("year").mw
        assert p[2001] == pytest.approx(100.0 * f, abs=TOL) and len(p) == 25
    gone = ir.rebuild(inv, {"permit": ("ramp", 2026.0)})
    assert not (gone.fy.fid == "permit").any()
    # with no load in 2024 the state's permit total is the verified row's 30 MW alone, so the factor is 130 / 30, capped at 3
    assert gone.factors["AA"]["alternative"] == pytest.approx(px.SCALE_HI, abs=TOL)


def test_a_sourced_bound_holds_the_draw_and_is_counted():
    ev = pd.DataFrame([{"site": "permit", "kind": "operating_by", "year": 2016, "kind_d61": "operating_by"},
                       {"site": "permit", "kind": "not_before", "year": 2012, "kind_d61": "not_before"}])
    inv = e7_world(evidence=ev)
    rows = ir.e7_rows(inv, unsettled={})
    late, holds = ir.e7_starts(rows, degenerate(5), "later", 0)
    assert late == {"permit": 2016.0} and holds == [("permit", "not_after", 2019.0, 2016.0)]
    early, holds = ir.e7_starts(rows, degenerate(5), "earlier", 0)
    assert early == {"permit": 2012.0} and holds == [("permit", "not_before", 2009.0, 2012.0)]
    ctx = context()
    roster = pd.DataFrame([(1, "AA", 2015)], columns=ir.KEY + ["cohort"])
    res = [ir.e7_draw(ctx, inv, rows, degenerate(5), roster, "later", i) for i in range(3)]
    s = ir.e7_summary(res, roster, rows)
    assert s["draws_held_at_a_bound_by_row"] == {"permit": {"not_after": 3}} and s["draws_with_any_hold"] == 3


def test_a_host_whose_crossing_leaves_2011_to_2022_is_out_of_the_draw():
    inv = e7_world()
    rows = ir.e7_rows(inv, unsettled={})
    ctx = context()
    built = ir.crossings(ir.dose_frame(inv.fy, inv.base), 0.02, {})
    assert built[HOST][0] == "cohort"
    roster = pd.DataFrame([(1, "AA", built[HOST][1])], columns=ir.KEY + ["cohort"])
    r = ir.e7_draw(ctx, inv, rows, degenerate(6), roster, "earlier", 0)
    assert r.failure is None
    h = r.redated.hosts[0]
    assert h["group"] == "early" and h["status"] == "out" and h["why"].startswith(ir.GROUP_CHANGED)
    assert r.redated.retained() == [] and r.redated.design is None
    assert h["crossing"] < 2011 and r.errors["1:AA"] == h["crossing"] - built[HOST][1] == -6   # the site moved 6 years
    s = ir.e7_summary([r], roster, rows)
    assert s["by_host"]["1:AA"]["exact"] == 0.0 and s["mean_hosts_per_draw_in_the_design"] == 0.0
    late = ir.e7_draw(ctx, inv, rows, degenerate(12), roster, "later", 0)   # 2026: no load in the panel, no crossing
    assert late.redated.hosts[0]["why"] == ir.NO_CROSSING and late.errors["1:AA"] == ir.NEVER


def test_a_draw_is_reproducible_on_its_own_and_errors_are_drawn_within_size_class():
    inv = e7_world()
    rows = ir.e7_rows(inv, unsettled={})
    errs = {"under_20": np.array([100.0]), "20_to_50": np.array([200.0]), "50_plus": np.array([1.0, 2.0, 3.0])}
    a = [ir.e7_starts(rows, errs, "earlier", i)[0]["permit"] for i in range(30)]
    b = [ir.e7_starts(rows, errs, "earlier", i)[0]["permit"] for i in reversed(range(30))][::-1]
    assert a == b and set(a) <= {2011.0, 2012.0, 2013.0} and len(set(a)) > 1
    late = [ir.e7_starts(rows, errs, "later", i)[0]["permit"] for i in range(30)]
    assert [2014.0 - x for x in a] == [y - 2014.0 for y in late]     # the agent's reading of "its mirror": the same draws


# ---- the common core -------------------------------------------------------------------------------------------------

def test_the_core_returns_the_headline_design_exactly_when_the_inventory_is_unchanged():
    inv = slow_world()
    ctx = context()
    dose0 = ir.dose_frame(inv.fy, inv.base)
    rb = ir.rebuild(inv, {f: inv.history(f) for f in inv.fac.index})
    dose1 = ir.dose_frame(rb.fy, inv.base)
    k = ir.KEY + ["year"]
    pd.testing.assert_frame_equal(dose0.sort_values(k).reset_index(drop=True), dose1.sort_values(k).reset_index(drop=True))
    treated, clean, ref = headline_reference(ctx, dose0)
    assert list(map(tuple, treated[ir.KEY].values)) == [HOST] and int(treated.cohort.iloc[0]) == 2012
    alt = ir.redate(ctx, dose1, ir.roster_of(treated))
    pd.testing.assert_frame_equal(alt.design.hosts, ref.hosts)
    assert alt.design.dropped == ref.dropped
    pd.testing.assert_frame_equal(alt.clean.reset_index(drop=True), clean.reset_index(drop=True))
    assert alt.hosts[0]["status"] == "retained" and alt.hosts[0]["moved_by"] == 0


def test_rematching_happens_at_the_new_reference_year():
    """Comparison 99 is the nearest in size but usable only from 2008: outside the window of 2006-2015 the as-built
    crossing (2012) gives, inside the window of 2008-2017 the slow path's crossing (2014) gives. It enters at the new date."""
    comps = ladder(10, 12) + [(99, "AA", 10_001, COOP)]
    usable = {(u, st, y) for u, st, *_ in [(1, "AA")] + comps for y in YEARS if not (u == 99 and y < 2008)}
    ctx = context(comps, usable)
    inv = slow_world()
    roster = pd.DataFrame([(1, "AA", 2012)], columns=ir.KEY + ["cohort"])
    ref = ir.redate(ctx, ir.dose_frame(inv.fy, inv.base), roster)
    assert (99, "AA") not in [tuple(m) for m in ref.design.hosts.match_keys.iloc[0]]
    rb, _ = ir.e4a(inv)
    alt = ir.redate(ctx, ir.dose_frame(rb.fy, inv.base), roster, ref)
    h = alt.hosts[0]
    assert h["crossing"] == 2014 and h["status"] == "retained" and h["crossing_moved"] and not h["sample_changed"]
    keys = [tuple(m) for m in alt.design.hosts.match_keys.iloc[0]]
    assert keys[0] == (99, "AA") and int(alt.design.hosts.cohort.iloc[0]) == 2014
    assert h["matches_added"] == ["99:AA"] and len(h["matches_removed"]) == 1


def test_a_host_without_a_full_usable_new_window_is_named_and_not_substituted():
    comps = ladder(10, 12)
    usable = {(u, st, y) for u, st, *_ in [(1, "AA")] + comps for y in YEARS if not (u == 1 and y == 2017)}
    ctx = context(comps, usable)
    inv = slow_world()
    roster = pd.DataFrame([(1, "AA", 2012)], columns=ir.KEY + ["cohort"])
    rb, _ = ir.e4a(inv)
    alt = ir.redate(ctx, ir.dose_frame(rb.fy, inv.base), roster)
    h = alt.hosts[0]
    assert h["crossing"] == 2014 and h["status"] == "out" and h["why"] == dsg.NOT_USABLE
    assert alt.design is not None and len(alt.design.hosts) == 0                # no host substituted, no date invented


def test_a_later_start_shift_moves_a_permit_dated_row_k_years_later():
    inv = e7_world()
    changed, bad = ir.later_start_rows(inv, 3)
    assert changed == {"permit": ("ramp", 2017.0)} and bad == []


# ---- E7 on each named set: the headline set and every cohort utility (wired 2026-11-20, session 25) --------------------
#
# Joe, 2026-11-20: "Complete E7's already specified quantity-side checks for both the headline set and every cohort
# utility. Routine wiring of the existing E7 functions to the specified sets is within scope, provided it changes no
# research rule." design.split is replaced by an invented one and aside_for by an invented list, so no file is read.

EVERY = ir.EVERY_COHORT_UTILITY
HOST2 = (2, "AA")
HEAD_ASIDE = {HOST2, (13, "AA")}          # invented: the headline list takes out host 2 and comparison utility 13
LEGACY_E7_KEYS = ["partial_timing_run", "label", "seconds_per_draw", "projected_minutes_for_400_draws", "budget_minutes",
                  "seed", "rows_redrawn", "rows_redrawn_by_size_class", "permit_dated_rows_on_the_rebuilt_inventory",
                  "permit_dated_rows_not_redrawn", "rows_with_a_sourced_bound",
                  "unsettled_operating_status_no_load_in_every_draw", "error_sign", "directions"]


def two_set_world():
    """Two hosts in AA, each with one permit-dated site, and a verified site on comparison utility 10. Host 1 crosses 2%
    in 2016, host 2 in 2015. The headline set (invented) sets host 2 and comparison utility 13 aside; every cohort
    utility keeps both, as design.split keeps everything for that set."""
    sites = [site("permit", "AA", 1, 100.0, 2014), site("permit2", "AA", 2, 100.0, 2013),
             site("verified", "AA", 10, 30.0, 2012, date_basis="verified_public_source")]
    epri = {"AA": 230.0 * 8.76 / 1000}
    inv = inventory(sites, epri, {HOST: HOST_BASE_GWH, HOST2: HOST_BASE_GWH, (10, "AA"): 1e9})
    comps = ladder(10, 12)
    _, _, q, regions, dd = world([(1, "AA", 10_000, COOP), (2, "AA", 10_000, COOP)], comps)
    usable = {(u, st, y) for u, st, *_ in [(1, "AA"), (2, "AA")] + comps for y in YEARS}
    ctx = ir.Context(q, regions, FUEL, dd, ps.HEADLINE_RULES, table([]), usable, GAS, ps.ownership_classes(q), NONE, 0.02,
                     history={}, aside=set(HEAD_ASIDE), hold=set())
    return inv, ctx


def invented_aside(theta, which):
    return set() if which == EVERY else set(HEAD_ASIDE)


def invented_split(theta, which, q, dose, frozen=None):
    treated, clean = ps.design(q, dose, theta, {}, hold=set())
    out = invented_aside(theta, which)
    keep = lambda d: d[[(int(u), s) not in out for u, s in zip(d.utility_id_eia, d.state)]].reset_index(drop=True)  # noqa: E731
    return keep(treated), keep(clean)


@pytest.fixture
def two_sets(monkeypatch):
    monkeypatch.setattr(dsg, "split", invented_split)
    monkeypatch.setattr(ir, "aside_for", invented_aside)
    inv, ctx = two_set_world()
    dose = ir.dose_frame(inv.fy, inv.base)
    headline = ir.set_reference(ctx, ps.HEADLINE_SET, dose)
    rows = ir.e7_rows(inv, unsettled={})
    errors = {c: np.array([0.0, 1.0, 2.0]) for c in ("under_20", "20_to_50", "50_plus")}
    names = pd.Series(dtype=object)
    return dict(inv=inv, ctx=ctx, dose=dose, headline=headline, rows=rows, errors=errors, names=names)


def ticking(step=0.001):
    """A clock that moves `step` seconds per call, so timings are the same in every run."""
    t = [0.0]

    def clock():
        t[0] += step
        return t[0]
    return clock


def run_sets(w, sets=ir.E7_SETS, draws=4, budget=1e9, timing_draws=2, clock=None):
    return ir.e7_all_sets(w["ctx"], w["inv"], w["dose"], w["rows"], w["errors"], w["names"], w["headline"], draws=draws,
                          budget_minutes=budget, timing_draws=timing_draws, sets=sets, clock=clock or ticking())


def stub_draws(monkeypatch):
    """Replace e7_draw by a recorder. Each (roster, direction) is computed once for real (draw 0) and reused, and every
    call's set, direction, draw and seed is recorded. Keeps a run of 200 draws a direction fast on invented data."""
    real, cache, calls = ir.e7_draw, {}, []

    def rec(ctx, inv, rows, errors, roster, direction, draw, reference=None, seed=ir.E7_SEED):
        key = (tuple(map(tuple, roster[ir.KEY].values)), direction)
        calls.append((key[0], direction, int(draw), seed))
        if key not in cache:
            cache[key] = real(ctx, inv, rows, errors, roster, direction, 0, reference, seed)
        return ir.E7Draw(direction, draw, cache[key].holds, cache[key].redated, cache[key].errors, cache[key].failure)
    monkeypatch.setattr(ir, "e7_draw", rec)
    return calls


def test_e7_runs_each_named_set_through_the_same_functions_with_its_own_reference_and_roster(two_sets, monkeypatch):
    w = two_sets
    seen_runs, seen_refs = [], []
    real_run, real_ref = ir.e7_run, ir.set_reference

    def spy_run(ctx, inv, rows, errors, roster, ref, **kw):
        seen_runs.append((sorted(map(tuple, roster[ir.KEY].values)), frozenset(ctx.aside), rows is w["rows"],
                          errors is w["errors"]))
        return real_run(ctx, inv, rows, errors, roster, ref, **kw)

    def spy_ref(ctx, which, dose):
        seen_refs.append((which, frozenset(ctx.aside)))
        return real_ref(ctx, which, dose)
    monkeypatch.setattr(ir, "e7_run", spy_run)
    monkeypatch.setattr(ir, "set_reference", spy_ref)
    blocks, n_runs = run_sets(w)
    # one call of the same e7_run per set, in E7_SETS' order, each on the shared rows and errors and its own roster
    assert [r[0] for r in seen_runs] == [[HOST], [HOST, HOST2]]
    assert [r[1] for r in seen_runs] == [frozenset(HEAD_ASIDE), frozenset()]
    assert all(r[2] and r[3] for r in seen_runs)
    assert seen_refs == [(EVERY, frozenset())]           # the headline's reference is main's; every cohort utility gets its own
    assert list(blocks) == ["E7", "E7_every_cohort_utility"] and set(n_runs) == {ps.HEADLINE_SET, EVERY}
    every = blocks["E7_every_cohort_utility"]
    assert every["set"] == EVERY and "set" not in blocks["E7"]
    assert [h["utility"] for h in every["reference"]["hosts"]] == ["1:AA", "2:AA"]
    assert every["reference"]["eligible_comparison_utilities"] == len(w["headline"].ref.clean) + 1 == 12   # 13 kept
    assert set(every["directions"]["earlier"]["by_host"]) == {"1:AA", "2:AA"}
    assert set(blocks["E7"]["directions"]["earlier"]["by_host"]) == {"1:AA"}
    assert every["checks"] == {"core_on_the_dose_as_built_equals_design_build_with_rules": True,
                               "core_comparison_pool_equals_design_split": True}
    assert set(every) == set(blocks["E7"]) | {"set", "threshold", "what_this_is", "seed_and_draw_streams", "checks",
                                              "reference", "settings"}


def test_the_headline_block_is_the_same_with_or_without_the_second_set(two_sets):
    w = two_sets
    alone, _ = run_sets(w, sets=(ps.HEADLINE_SET,))
    both, _ = run_sets(w)
    assert list(alone) == ["E7"]
    assert both["E7"] == alone["E7"]
    assert list(both["E7"]) == LEGACY_E7_KEYS                                # the keys main wrote before, in order
    direct, _ = ir.e7_run(w["ctx"], w["inv"], w["rows"], w["errors"], w["headline"].roster, w["headline"].ref, draws=4,
                          budget_minutes=1e9, timing_draws=2, clock=ticking())
    assert direct == alone["E7"]


def test_each_set_uses_seed_20261203_and_200_draws_a_direction(two_sets, monkeypatch):
    w = two_sets
    calls = stub_draws(monkeypatch)
    blocks, n_runs = run_sets(w, draws=ir.E7_DRAWS)
    assert n_runs == {s: {"earlier": 200, "later": 200} for s in (ps.HEADLINE_SET, EVERY)}
    for roster in ((HOST,), (HOST, HOST2)):
        for d in ir.DIRECTIONS:
            mine = [(i, seed) for r, dd, i, seed in calls if r == roster and dd == d]
            assert sorted(i for i, _ in mine) == list(range(200))
            assert {seed for _, seed in mine} == {20261203}
    for b in blocks.values():
        assert b["seed"] == 20261203 and b["partial_timing_run"] is False
        assert b["label"] == "the specified 200 draws a direction"
        assert all(b["directions"][d]["draws_attempted"] == 200 for d in ir.DIRECTIONS)
    assert blocks["E7_every_cohort_utility"]["settings"] == {
        "e7_seed": 20261203, "e7_draws_specified": 200, "e7_draws_requested": 200,
        "e7_draws_run": {"earlier": 200, "later": 200}}


def test_draw_i_redraws_the_inventory_identically_for_both_sets(two_sets, monkeypatch):
    """The agent's reading of the seed for the second set. The streams of e7_starts are keyed by (seed, draw), not by set."""
    w = two_sets
    seen = []
    real = ir.rebuild

    def spy(inv, changed, anchoring="recompute"):
        seen.append(dict(changed))
        return real(inv, changed, anchoring)
    monkeypatch.setattr(ir, "rebuild", spy)
    run_sets(w, draws=3, timing_draws=2)
    assert len(seen) == 12                                                   # 2 sets x 2 directions x 3 draws
    head, every = seen[:6], seen[6:]
    assert head == every
    assert len({tuple(sorted(c.items())) for c in head}) > 1                 # the draws do differ from one another


def test_a_partial_run_is_labelled_partial_and_a_full_run_full_set_by_set(two_sets, monkeypatch):
    w = two_sets
    stub_draws(monkeypatch)
    # Each set times 2 draws between two clock readings. Headline: 10 s for 2 draws, so 400 draws project to 33.3 min;
    # every cohort utility: 10,000 s for 2. A budget of 60 minutes fits the first and not the second.
    readings = iter([0.0, 10.0, 0.0, 10_000.0])
    blocks, n_runs = run_sets(w, draws=ir.E7_DRAWS, budget=60.0, timing_draws=2, clock=lambda: next(readings))
    head, every = blocks["E7"], blocks["E7_every_cohort_utility"]
    assert head["partial_timing_run"] is False and head["label"] == "the specified 200 draws a direction"
    assert every["partial_timing_run"] is True
    assert every["label"] == "a partial timing run of {'earlier': 1, 'later': 1} draws, not the specified 200 a direction"
    assert "the specified 200 draws a direction" not in every["label"]
    assert n_runs[EVERY] == {"earlier": 1, "later": 1} and every["settings"]["e7_draws_run"] == {"earlier": 1, "later": 1}
    assert every["directions"]["earlier"]["draws_attempted"] == 1
    # a run with fewer draws than the plan's, set by --e7-draws, is never labelled the specified run
    few, _ = run_sets(w, draws=5)
    for b in few.values():
        assert b["partial_timing_run"] is False
        assert b["label"] == "5 draws a direction set by --e7-draws, not the specified 200"


def test_context_from_files_gives_every_cohort_utility_no_set_aside(monkeypatch):
    """Context.from_files reads files; every reader is replaced here. design.split keeps every unit for every cohort
    utility, so its context sets none aside; the headline and ten-year sets keep their lists."""
    _, ctx = two_set_world()
    monkeypatch.setattr(dsg, "load", lambda: (ctx.q, None, ctx.regions, ctx.fuel, ctx.dd))
    monkeypatch.setattr(ps, "rule_inputs", lambda rules, q: (None, None, None))
    monkeypatch.setattr(ps, "ownership_classes", lambda q: {})
    monkeypatch.setattr(ps, "load_unknown_load", lambda: NONE)
    monkeypatch.setattr(ps, "history_settled", lambda theta: {})
    monkeypatch.setattr(ps, "set_aside", lambda theta, frozen=None, ten_year_case=False:
                        {(7, "XX")} | ({(8, "XX")} if ten_year_case else set()))
    assert ir.Context.from_files(0.02).aside == {(7, "XX")}
    assert ir.Context.from_files(0.02, which=dsg.PLUS_UNSETTLED).aside == {(7, "XX")}
    assert ir.Context.from_files(0.02, which=ps.TEN_YEAR_SET).aside == {(7, "XX"), (8, "XX")}
    assert ir.Context.from_files(0.02, which=EVERY).aside == set()
    with pytest.raises(ValueError):
        ir.aside_for(0.02, "no_such_set")


def test_set_reference_stops_in_words_when_the_context_sets_aside_what_the_set_keeps(two_sets):
    w = two_sets
    with pytest.raises(SystemExit, match="comparison pool is not design.split's"):
        ir.set_reference(w["ctx"], EVERY, w["dose"])                       # the headline's list on every cohort utility


def test_a_budget_for_every_cohort_utility_alone_leaves_the_headline_budget_as_given(two_sets, monkeypatch):
    w = two_sets
    stub_draws(monkeypatch)
    readings = iter([0.0, 10.0, 0.0, 10.0])          # both sets: 400 draws project to 33.3 minutes
    blocks, _ = ir.e7_all_sets(w["ctx"], w["inv"], w["dose"], w["rows"], w["errors"], w["names"], w["headline"],
                               draws=ir.E7_DRAWS, budget_minutes=25.0, timing_draws=2, clock=lambda: next(readings),
                               budgets={EVERY: 600.0})
    head, every = blocks["E7"], blocks["E7_every_cohort_utility"]
    assert head["budget_minutes"] == 25.0 and head["partial_timing_run"] is True
    assert every["budget_minutes"] == 600.0 and every["partial_timing_run"] is False
    assert every["label"] == "the specified 200 draws a direction"
