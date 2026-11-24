"""Composition of every design builder with the estimation kernel (pipeline/analysis/run_outcomes.py). Invented inputs only.

One invented world: five hosts in five states (cohorts 2012, 2015, 2015, 2017, 2019; two investor-owned, one with no
ownership row), sixteen comparison utilities near each host in size spread over eight states, ten more in the states of
hosts 1 and 3 (so the own-state run has a pool there), two market regions (host 1, its sixteen, the ten in its state and
the late host in "North" in every year; everything else in "West", but for host 2's two nearest, in "East" before 2004;
session 21, so that each region left out keeps a host), an investor-owned affiliate of host 4, a late host (unit 98), an
ownership table with basis columns, a supplier table, an invented inventory whose permit-dated sites put each host's
first crossing at its cohort (host 4's state has an anchoring factor of 2), peak demands, delivery-only sales and doses.

Outcomes are invented: unit effect + calendar-year effect + 0.02 x heating degree days + noise of sd 1e-4, plus a planted
path on hosts from their real first crossing (LONG: 0.01, 0.03, 0.05, 0.05, 0.06, 0.07, 0.08 in event years 0 to 6, held
after). Unless a test says otherwise the tolerance is 1e-3 log points (a tenth of a point of price), ten times the noise.
The second number's runs get their own outcome, linear in load share (0.004 per point), so the slope is known.

No file under data/ is read: the price hold, set-aside list and D-34 table are passed in as empty, every set is supplied.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import future_hosts as fh  # noqa: E402
from pipeline.analysis import inventory_against_sales as ias  # noqa: E402
from pipeline.analysis import inventory_runs as ir  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import reconciliation_c as rc  # noqa: E402
from pipeline.analysis import reconciliation_mu as rmu  # noqa: E402
from pipeline.analysis import run_outcomes as ro  # noqa: E402
from pipeline.analysis import second_number as sn  # noqa: E402
from pipeline.analysis import short_form_filers as sff  # noqa: E402
from pipeline.analysis import side_runs as sr  # noqa: E402
from pipeline.analysis import suppliers as sp  # noqa: E402
from pipeline.facilities import corrections as cx  # noqa: E402
from test_inventory_runs_invented import inventory, site  # noqa: E402
from test_matching_rules import table  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
STATES = ["AA", "AB", "AC", "AD", "BA", "BB", "BC", "BD"]
FUEL = {s: i % 2 for i, s in enumerate(STATES)}
GAS = {s: g for s, g in zip(STATES, (0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75))}
IOU, COOP, PUB = "investor_owned", "cooperative", "public"
HDD_BETA = 0.02
TOL = 1e-3
NONE = ps.UnknownLoad.none("invented data in a test")

HOSTS = [(1, "AA", 10_000, IOU, 2012), (2, "AC", 30_000, COOP, 2015), (3, "BA", 50_000, PUB, 2015),
         (4, "BC", 70_000, IOU, 2017), (5, "BD", 90_000, COOP, 2019)]
COHORT = {(h[0], h[1]): h[4] for h in HOSTS}
NEAR = [(100 * (j + 1) + i, STATES[i % 8], h[2] + 50 + 40 * i, (COOP, PUB)[i % 2]) for j, h in enumerate(HOSTS) for i in range(16)]
FAR = [(1000 + i, "AA", 12_000 + 10 * i, COOP) for i in range(10)] + [(3000 + i, "BA", 52_000 + 10 * i, PUB) for i in range(10)]
# Two large units in each of the states of hosts 2, 4 and 5 (session 21): with host 1's ladder in "North", each of those
# states holds eight West units of the near ladders, and these two bring its own-state pool to ten. At 200,000 customers
# and up they are in another size band and far from every host, so no nearest-ten match or size-band cell takes them.
FAR += [(5000 + 10 * j + i, st, 200_000 + 10 * i, COOP) for j, st in enumerate(("AC", "BC", "BD")) for i in range(2)]
AFFILIATE = (777, "AD", 70_010, IOU)          # same parent as host 4: out under the headline rules, back under rule 2.3's sensitivity
FUTURE = (98, "AB", 10_010, COOP)             # a late host: nearest in size to host 1
COMPS = NEAR + FAR + [AFFILIATE]
UNITS = [h[:4] for h in HOSTS] + COMPS + [FUTURE]
CHANGERS = {(200, "AA"), (201, "AB")}         # host 2's two nearest: in "East" before 2004 (E6)
LONG = {0: 0.01, 1: 0.03, 2: 0.05, 3: 0.05, 4: 0.06, 5: 0.07, 6: 0.08}
B_SECOND = 0.004                              # the second number's planted slope, log points per point of load share
HOST_BASE_GWH = 80.0 * 8.76 / 0.02            # 80 MW of load is 2% of a host's 2009-2011 sales


def p(e: int) -> float:
    """The planted host path at real event time e."""
    return 0.0 if e < 0 else LONG[min(e, 6)]


# ---- the world ---------------------------------------------------------------------------------------------------------

NORTH = ({(1, "AA"), FUTURE[:2]} | {(u, st) for u, st, *_ in NEAR if 100 <= u < 200}
         | {(u, st) for u, st, *_ in FAR if u < 3000})       # host 1's ladder, its state's ten and the late host


def region(key, year):
    if key in NORTH:
        return "North"
    return "East" if key in CHANGERS and year < 2004 else "West"


NONRES_BASE_MWH = 500_000.0
IAS_SLOPE = 0.8              # hosts' non-residential sales grow by 0.8 x the inventory's added load (inventory_against_sales)


def dose_value(u, st, y) -> float:
    if (u, st) in COHORT:
        return (0.15 if u in (1, 2) else 0.06) if y >= COHORT[(u, st)] else 0.0
    if (u, st) == FUTURE[:2]:
        return 0.03 if y >= 2025 else 0.0
    return 0.001


def quantities():
    """Non-residential sales: flat at NONRES_BASE_MWH, plus, at hosts, IAS_SLOPE x the inventory's load (dose x 1,000 GWh),
    so the inventory check's slope is IAS_SLOPE exactly (comparison utilities grow at 0)."""
    rows = []
    for u, st, size, own in UNITS:
        for y in YEARS:
            delivery = 5.0 if (u, st) == (1, "AA") and y == COHORT[(1, "AA")] + ps.REF else 0.0
            nonres = NONRES_BASE_MWH + (IAS_SLOPE * dose_value(u, st, y) * 1000.0 * 1000.0 if (u, st) in COHORT else 0.0)
            rows.append((u, st, y, own, float(size), 1.0, True, f"U{u}{st}", delivery, nonres))
    return pd.DataFrame(rows, columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor",
                                             "utility_name", "res_mwh_delivery", "nonres_mwh"])


def doses():
    """The invented dose frame: hosts 1 and 2 at 15% from their cohort, hosts 3 to 5 at 6%; comparison utilities at 0.1%;
    the late host at 3% from 2025. Every first crossing is the same at 1%, 2% and 5%."""
    rows = []
    for u, st, *_ in UNITS:
        for y in YEARS:
            v = dose_value(u, st, y)
            rows.append((u, st, y, v, 0.0, 1000.0, v * 1000.0))
    return pd.DataFrame(rows, columns=KEY + ["year", "dose", "crypto_mw", "base_retail_gwh", "dc_gwh"])


def ownership_table():
    t = table([{"utility_id_eia": 4, "state": "BC", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
               {"utility_id_eia": 777, "state": "AD", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025}])
    t["state"] = ["BC", "AD"]
    t["from_year_basis"], t["to_year_basis"] = "documented", "documented"
    return t


def supplier_table(d):
    """Host 2 and its nearest match share a joint agency (membership only); every other row unknown."""
    base = {"name": "x", "source_url": "https://example.org", "source_kind": "supplier_member_list", "quote": "q",
            "date_opened": "2026-11-18", "from_year_basis": "assumed", "to_year_basis": "assumed"}
    first = tuple(d.hosts.match_keys.iloc[[k == (2, "AC") for k in d.hosts.key].index(True)][0])
    note = "MEMBERSHIP_ONLY: the source shows membership, not that this supplier provided all or most of the unit's requirements."
    rows = [{**base, "utility_id_eia": 2, "state": "AC", "supplier": "JAA", "supplier_kind": "joint_action_agency",
             "from_year": 2001, "to_year": 2025, "note": note},
            {**base, "utility_id_eia": first[0], "state": first[1], "supplier": "JAA", "supplier_kind": "joint_action_agency",
             "from_year": 2001, "to_year": 2025, "note": note}]
    return pd.DataFrame(rows, columns=list(sp.COLUMNS)).astype({"utility_id_eia": int, "from_year": int, "to_year": int}), first


def peaks():
    rows = []
    for j, (u, st, *_) in enumerate(HOSTS):
        for y in YEARS:
            rows.append((u, st, f"{y}-01-01", 100.0 * (1 + 0.01 * (j + 1) * (y - 2001)), 90.0, False, True))
    return pd.DataFrame(rows, columns=list(ro.cn.PEAK_COLUMNS))


def invented_inventory():
    sites = [site("s1", "AA", 1, 100.0, 2010, 2015), site("s2", "AC", 2, 100.0, 2013), site("s3", "BA", 3, 100.0, 2013),
             site("s4", "BC", 4, 50.0, 2015), site("s5", "BD", 5, 100.0, 2017),
             site("s98", "AB", 98, 100.0, 2024, date_basis="verified_public_source")]
    full = lambda mw: mw * 8.76 / 1000.0                                                     # noqa: E731
    epri = {"AA": full(100), "AC": full(100), "BA": full(100), "BC": 2 * full(50), "BD": full(100), "AB": full(100) / 3}
    base = {(h[0], h[1]): HOST_BASE_GWH for h in HOSTS} | {FUTURE[:2]: HOST_BASE_GWH}
    return inventory(sites, epri, base)


def build_world(e7_errors=1):
    q = quantities()
    regions = pd.DataFrame([(u, st, y, region((u, st), y)) for u, st, *_ in UNITS for y in YEARS], columns=KEY + ["year", "region"])
    rng = np.random.default_rng(5)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in STATES for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    usable = {(u, st, y) for u, st, *_ in UNITS for y in YEARS}
    own = ownership_table()
    dose = doses()
    side = sr.Inputs(q, dose, regions, FUEL, dd, ownership=own, usable=usable, gas=GAS, unknown_load=NONE)
    treated = pd.DataFrame([(h[0], h[1], h[4]) for h in HOSTS], columns=KEY + ["cohort"])
    clean = pd.DataFrame([c[:2] for c in COMPS], columns=KEY)
    sets = {ro.H2: (treated, clean), (ro.TEN_YEAR_SET, 0.02): (treated[treated.utility_id_eia != 3], clean),
            (ro.PLUS_UNSETTLED, 0.02): (treated, clean), ro.E2_: (treated, clean)}
    for theta, which in ((0.01, ro.EVERY), (0.05, ro.HEADLINE_SET), (0.05, ro.EVERY)):
        sets[(which, theta)] = ps.design(q, dose, theta, {}, hold=set())
    inv = invented_inventory()
    ctx = ir.Context(q, regions, FUEL, dd, ps.HEADLINE_RULES, own, usable, GAS, ps.ownership_classes(q), NONE, 0.02,
                     history={}, aside=set(), hold=set())
    inp = ro.RunInputs(side=side, sets=sets)
    head = inp.build(ro.H2)
    sup, shared = supplier_table(head)
    units = [(u, st) for u, st, *_ in UNITS]
    pts = sn.dose_points(dose)
    f = sn.build_frame(units, q, regions, usable)
    x = sn.dose_matrix(pts, f.keys, f.years)
    # The adopted classification's inputs (second_number section 3a): one modeled history per utility here, so every
    # change is its own range; reach from the endpoint years' load shares, uncapped.
    assigned = {sn.cap_label(c): dict(zip(map(sn._uid, f.keys), sn.change(x, f.n_pre, c))) for c in sn.CAPS}
    changes = {lab: {u: np.array([v]) for u, v in a.items()} for lab, a in assigned.items()}
    reach = {sn._uid(k): sn.reach_from_endpoints(row) for k, row in zip(f.keys, x)}
    inp.suppliers, inp.omissions = sup, None
    inp.e5_anchor, inp.e6_changers = e5_anchor(), set(CHANGERS)
    inp.future_admitted = {2012: [FUTURE[:2]]}
    inp.e2_histories, inp.e2_aside, inp.e2_hold = e2_histories(FUTURE[:2]), set(), set()
    inp.e2_late = {FUTURE[:2]}
    inp.inventory, inp.inventory_contexts = inv, {ro.HEADLINE_SET: ctx, ro.EVERY: ctx}
    inp.e7_errors = {c: np.array([float(e7_errors)]) for c in ("under_20", "20_to_50", "50_plus")}
    inp.e7_draws = 3
    inp.peaks = peaks()
    from pipeline.electricity import succession as succ
    inp.succession = pd.DataFrame(columns=succ.COLUMNS).astype({"predecessor_id": "Int64", "successor_id": "Int64"})  # none
    # The bootstrap seed of a research run is 20261205 (Joe, D-107); this world passes its own and says it is invented.
    inp.second_number = {"units": units, "seed": 5, "invented_inputs": True, "boot": 99, "assigned": assigned,
                         "changes": changes, "reach": reach, "no_assigned": [], "established": {},
                         "scenario_units": units, "scenario_points": scenario_points(dose),
                         "scenario_no_dose": {ro.ss.SCENARIO_A: [], ro.ss.SCENARIO_B: [(5, "BD")]}}
    inp.catches_drift = {ro.HEADLINE_SET: True}
    # The invented world's headline design stands in for the validated one: its hashes are the reference the kernel checks
    # main_headline_set's claim against (outcome_analysis.ValidationReference; session 19).
    inp.validation_reference = oa.ValidationReference.of_design(head, usable, source="invented: this world's headline design")
    inp.reconciliation_m, inp.reconciliation_u, inp.reconciliation_c = row_m_inputs(), row_u_inputs(), row_c_inputs()
    inp.inventory_readings = ias.ADOPTED
    inp.inventory_inputs_are = ias.INVENTED_INPUTS
    inp.reconciliation_u_inputs_are = ro.INVENTED_INPUTS          # session 27: required by row U's entry
    inp.timing_added = dict(TIMING_ADDED)
    inp.cs_sample = ro.CSSampleInputs(host_aside=set(), comparison_aside=set(), hold=set(), history={})
    return inp, {"shared_supplier_match": shared, "dd": dd}


# ---- the second number's two sensitivity scenarios and the timing run (session 21) --------------------------------------

TIMING_ADDED = {FUTURE[:2]: 2016}            # the late host added at an invented no-anchoring year (one host, not two)


def scenario_points(dose):
    """Invented scenario load shares in points (as second_number_scenarios.points_of returns them): scenario A moves
    host 3 from 6 to 9 points from its cohort; scenario B gives host 5 load and no base (NaN, no dose) and host 4 12
    points. Nothing is realised: the registry reads no inventory file."""
    base = sn.dose_points(dose)
    a, b = base.copy(), base.copy()
    a.loc[(3, "BA"), [y for y in YEARS if y >= COHORT[(3, "BA")]]] = 9.0
    b.loc[(5, "BD"), :] = np.nan
    b.loc[(4, "BC"), [y for y in YEARS if y >= COHORT[(4, "BC")]]] = 12.0
    return {ro.ss.SCENARIO_A: a, ro.ss.SCENARIO_B: b}


def points_outcome(points, noise=1e-5, seed=9):
    """Linear in the given load shares: unit effect + year effect + 0.004 x points (capped at 25; none exceed it); a unit
    with no dose (NaN) carries no load term."""
    rng = np.random.default_rng(seed)
    year_fx = dict(zip(YEARS, rng.normal(0, 0.05, len(YEARS))))
    rows = []
    for (u, st), row in points.iterrows():
        a = rng.normal(0, 0.2)
        for y in YEARS:
            v = row[y]
            rows.append((u, st, y, a + year_fx[y] + B_SECOND * (0.0 if np.isnan(v) else min(v, 25.0)) + noise * rng.normal()))
    return pd.DataFrame(rows, columns=KEY + ["year", "value"])


# ---- E2 and E5 inputs (Joe's rulings of 2026-11-19) ----------------------------------------------------------------------

def e2_histories(*keys):
    """E2 records whose single history crosses 2% in 2025, so the fake date f is 2018 (as tests/test_future_hosts_invented)."""
    hist = {y: (0.03 if y >= 2025 else 0.0) for y in fh.PANEL_YEARS}
    return {k: {"histories": pd.DataFrame([hist]), "complete": True, "why_incomplete": [], "slow_path": None} for k in keys}


def e5_anchor(dropped=("BD",)):
    """An invented full state_anchor table: the states in `dropped` with a computed factor of 2.5, AB with the fallback 1.0
    (flagged, not dropped), every other state a computed 1.0. The report block carries the first two states only."""
    rows = []
    for st in STATES:
        if st in dropped:
            rows.append({"state": st, "epri_twh": 5.0, "permit_twh": 1.0, "epoch_twh": 0.0, "raw_factor": 2.5, "factor": 2.5, "flag": "ok"})
        elif st == "AB":
            rows.append({"state": st, "epri_twh": 5.0, "permit_twh": 0.0, "epoch_twh": 0.0, "raw_factor": float("nan"),
                         "factor": 1.0, "flag": "no_dated_permits"})
        else:
            rows.append({"state": st, "epri_twh": 5.0, "permit_twh": 1.0, "epoch_twh": 0.0, "raw_factor": 1.0, "factor": 1.0, "flag": "ok"})
    t = pd.DataFrame(rows)
    return ro.E5Inputs(block=t.iloc[:2].to_dict("records"), all_states=t)


# ---- the reconciliation rows: their own invented panels (rows M, U and C read no Design) ----------------------------------

R_STATES = ["AL", "AZ", "AR", "CA", "CO", "CT"]      # real contiguous codes: rows M, U and C refuse others
R_UNITS = [(500 + i, R_STATES[i % 6]) for i in range(36)]
R_YEARS = range(2005, 2026)
M_EFFECT = 0.03             # a constant log effect from the first year: every step's pooled and class estimate is 0.03
U_BETA = 0.01               # log price on ln(MW + 1)
C_BETA = 0.1                # cents per kWh per operating facility
M_FIRST = {u: (2012 + (i % 6) if i < 18 else np.nan) for i, u in enumerate(R_UNITS)}
U_MW = {u: (20.0 + 10.0 * i if i < 24 else 0.0) for i, u in enumerate(R_UNITS)}


def _treatment(rule, table):
    return rmu.rt.Treatment(rule, table.assign(rule=rule), pd.DataFrame(columns=["fid", "reason"]))


def row_m_inputs(steps=tuple(rmu.M_STEPS)):
    rules = {"M0": "county_touch|above_5mw|site|mw_full", "M1": "verified|above_5mw|site|mw_full",
             "M2": "verified|above_5mw|site|mw_full", "M3": "verified|above_5mw|site|mw_full", "M4": "verified|dose_at_least_0.02"}
    fy = pd.DataFrame([(u, st, M_FIRST[(u, st)]) for u, st in R_UNITS], columns=KEY + ["first_year"])
    # The settled fields at the paper's values (file dated 2026-10-23); the open ones chosen for the invented world.
    spec = rmu.MeeksSpec(covariates=(), aggregation="simple", se_method="influence_function", anticipation=0,
                         unbalanced="pairwise", treated_after_window="never_treated", jurisdictions=rmu.CONTIGUOUS_48,
                         customer_floor=None, exclude_short_form=True, require_three_classes=True,
                         short_form_years=M_SHORT_FORM_YEARS, three_classes_level="unit", three_classes_test="positive_sales",
                         retail_component="implied_by_a_residential_price", window_start_cohort="left_out_and_counted",
                         weighting="unweighted")
    own = pd.DataFrame([(u, st, rmu.M_CLASSES[i % 3]) for i, (u, st) in enumerate(R_UNITS)], columns=KEY + ["ownership_class"])
    return ro.RowMInputs(spec=spec, treatments={k: _treatment(rules[k], fy) for k in steps}, ownership=own, customers=None,
                         sample_flags=m_sample_flags())


M_SHORT_FORM_YEARS = (2010, 2024)


def m_sample_flags():
    """Row M's sample flags, every unit passing: no Short Form filer, every pair serving the three classes, read over
    the spec's years under its test."""
    return pd.DataFrame([(u, st, False, M_SHORT_FORM_YEARS[0], M_SHORT_FORM_YEARS[1], True, "positive_sales")
                         for u, st in R_UNITS],
                        columns=KEY + ["ever_short_form", "short_form_first_year_read", "short_form_last_year_read",
                                       "has_three_classes", "three_classes_test"])


def u_mw_table():
    return pd.DataFrame([(u, st, y, U_MW[(u, st)] * max(0, y - 2014) / 10.0) for u, st in R_UNITS for y in range(2015, 2026)],
                        columns=KEY + ["year", "mw"])


U_STEP_WINDOW = (2015, 2025)        # U3's window; the adopted rule is applied year by year over it (session 25's reading)
U_OUTSIDER = (9999, "AL")           # a unit in no outcome frame: its table rows make every year but 2019 a covered year


def u_filer_table(extra=()) -> pd.DataFrame:
    """An invented filer table (utility_id_eia, state, year), shaped like the real one: rows in every year from 2012 to
    2025 but 2019, here only for a unit in no outcome frame, plus `extra` unit-years (a record of a filing)."""
    rows = [(*U_OUTSIDER, y) for y in range(2012, 2026) if y != 2019] + [tuple(x) for x in extra]
    return pd.DataFrame(rows, columns=KEY + ["year"])


def u_2019_flags(true=(), no_row=()) -> pd.DataFrame:
    """Invented 2019 flags, shaped like the real file: True or missing, never False. Every R unit has a 2019 row with
    a missing flag, but the units in `true` (flag True) and in `no_row` (no flags row at all)."""
    rows = [(u, st, 2019, (True if (u, st) in set(true) else None)) for u, st in R_UNITS if (u, st) not in set(no_row)]
    f = pd.DataFrame(rows, columns=KEY + ["year", "short_form"])
    f["short_form"] = f.short_form.astype("boolean")
    return f


def u_flags_frame(units=R_UNITS, years=range(U_STEP_WINDOW[0], U_STEP_WINDOW[1] + 1), drop=()) -> pd.DataFrame:
    return pd.DataFrame([(u, st, y) for u, st in units for y in years if (u, st, y) not in set(drop)],
                        columns=KEY + ["year"])


def adopted_flags(table=None, flags=None, frame=None) -> pd.DataFrame:
    """sample_flags under the adopted rule (D-115), as a caller builds them: short_form_filers.adopted_row_u_flags on a
    frame of every R unit-year in 2015 to 2025, with step_window=(2015, 2025)."""
    return sff.adopted_row_u_flags(u_flags_frame() if frame is None else frame,
                                   u_filer_table() if table is None else table,
                                   u_2019_flags() if flags is None else flags, step_window=U_STEP_WINDOW)


def row_u_inputs(indistinguishable=False):
    rules = {"U0": "polygon_smallest_any_type|site_year_load", "U1": "verified|site_year_load", "U2": "verified|site_year_load",
             "U3": "verified|site_year_load"}
    mw = u_mw_table()
    # The specification is fixed (D-107) and the Short Form rule is the one Joe adopted on 2026-11-20 (D-115): the caller
    # passes ryu_spec(U_SHORT_FORM_ADOPTED_CODE) and flags from short_form_filers.adopted_row_u_flags. Here no R unit-year
    # has a record of a filing, so nothing leaves and every step keeps the planted world whole.
    spec = rmu.ryu_spec(rmu.U_SHORT_FORM_ADOPTED_CODE)
    own = pd.DataFrame([(u, st, rmu.U_CLASSES[i % 3]) for i, (u, st) in enumerate(R_UNITS)], columns=KEY + ["ownership_class"])
    return ro.RowUInputs(spec=spec, treatments={k: _treatment(r, mw) for k, r in rules.items()}, ownership=own,
                         sample_flags=adopted_flags(), u1_indistinguishable=indistinguishable)


def reconciliation_level(which, seed=11):
    """A price LEVEL frame (value) for rows M and U: exp(unit + year + the planted effect). `which` "M" plants M_EFFECT
    from the first year, "U" plants U_BETA x ln(MW + 1); noise of sd 1e-6 in logs."""
    rng = np.random.default_rng(seed)
    a = {u: rng.normal(0, 0.2) for u in R_UNITS}
    yf = {y: rng.normal(0, 0.05) for y in R_YEARS}
    mw = {(u, st, y): m for u, st, y, m in u_mw_table().itertuples(index=False)}
    rows = []
    for u, st in R_UNITS:
        for y in R_YEARS:
            fy = M_FIRST[(u, st)]
            eff = (M_EFFECT if which == "M" and not np.isnan(fy) and y >= fy else 0.0)
            eff += U_BETA * np.log(mw.get((u, st, y), 0.0) + 1.0) if which == "U" else 0.0
            rows.append((u, st, y, float(np.exp(a[(u, st)] + yf[y] + eff + 1e-6 * rng.normal()))))
    return pd.DataFrame(rows, columns=KEY + ["year", "value"])


C_UNITS = [(700 + i, R_STATES[i % 6]) for i in range(120)]


def _c_world():
    rng = np.random.default_rng(3)
    share = {u: float(rng.uniform(0.0001, 0.003)) for u in C_UNITS}
    host = set(C_UNITS[:60])
    m = {u: int(min(3, np.floor(share[u] * 1500))) for u in C_UNITS}
    cnt = {(u, st, y): float(m[(u, st)] if (u, st) in host and y >= 2021 else 0) for u, st in C_UNITS for y in rc.YEARS}
    counts = pd.DataFrame([(u, st, y, v) for (u, st, y), v in cnt.items() if v > 0], columns=KEY + ["year", "value"])
    a = {u: rng.normal(10, 1) for u in C_UNITS}
    sy = {(s, y): rng.normal(0, 0.3) for s in R_STATES for y in rc.YEARS}
    out = pd.DataFrame([(u, st, y, a[(u, st)] + sy[(st, y)] + C_BETA * cnt[(u, st, y)] + 1e-6 * rng.normal())
                        for u, st in C_UNITS for y in rc.YEARS], columns=KEY + ["year", "value"])
    return share, counts, out


def row_c_inputs(polygon=True):
    share, counts, _ = _c_world()
    return ro.RowCInputs(choices=rc.SPECIFICATION, counts_polygon=counts if polygon else None, counts_verified=counts,
                         dose_verified=counts.assign(value=counts.value * 0.01), share=share,
                         spending_tables={"paper": {y: 10.0 + y - 2015 for y in rc.YEARS},
                                          "current": {y: 11.0 + 1.1 * (y - 2015) for y in rc.YEARS}},
                         ownership={u: ("investor_owned" if i % 2 else "cooperative") for i, u in enumerate(C_UNITS)},
                         c4_cap=rc.OURS_C4_CAP, hosts_for_c5=rc.never_host_units(None, None, counts, "zero_count_panel_years"),
                         c5_counts_name="the invented polygon counts")


def row_c_outcome():
    return _c_world()[2]


def levels(y, scale=50.0):
    """The supplementary outcomes are supplied as LEVELS and logged by supplementary_outcomes (Joe, 2026-11-20, D-117):
    exp(y) times a positive scale, whose natural log is y + ln(scale), so the kernel's estimate is y's (the constant is
    absorbed by the unit effects)."""
    return y.assign(value=np.exp(y.value.to_numpy(dtype=float)) * scale)


def all_outcomes(y):
    """Every outcome name: `y` for the price outcome, its levels (levels(y)) for the three supplementary outcomes (session
    26: they are supplied as levels), and the reconciliation rows' own frames."""
    out = {ro.PRICE: y, **{o: levels(y) for o in (ro.KWH, ro.BILL, ro.CUSTOMERS)}}
    out[ro.PRICE_DEFAULT_SERVICE] = out[ro.PRICE_DELIVERY_INCLUSIVE] = reconciliation_level("M")
    out[ro.PRICE_CENTS_REAL_2024] = row_c_outcome()
    return out


@pytest.fixture(scope="module")
def world():
    return build_world()


def outcome(dd, cohorts=None, path=p, noise=1e-4, seed=7, levels=None):
    """Invented outcomes keyed by utility_id_eia, state, year, value. `cohorts` overrides the hosts' real first crossings
    (the date the path is planted from); `levels` {host: level} plants a constant level from event year 0 instead."""
    cohorts = COHORT if cohorts is None else cohorts
    rng = np.random.default_rng(seed)
    year_fx = dict(zip(YEARS, rng.normal(0, 0.05, len(YEARS))))
    rows = []
    for u, st, *_ in UNITS:
        a = rng.normal(0, 0.2)
        for y in YEARS:
            v = a + year_fx[y] + HDD_BETA * float(dd.hdd[(st, y)]) + noise * rng.normal()
            g = cohorts.get((u, st))
            if g is not None:
                v += (levels[(u, st)] if y >= g else 0.0) if levels is not None else path(y - g)
            rows.append((u, st, y, v))
    return pd.DataFrame(rows, columns=KEY + ["year", "value"])


def second_number_outcome(dose, noise=1e-5, seed=9):
    """Linear in load share: unit effect + year effect + 0.004 x load share in points (capped at 25; none here exceed it)."""
    rng = np.random.default_rng(seed)
    year_fx = dict(zip(YEARS, rng.normal(0, 0.05, len(YEARS))))
    a = {k: rng.normal(0, 0.2) for k in map(tuple, dose[KEY].drop_duplicates().values)}
    v = [a[(u, st)] + year_fx[y] + B_SECOND * min(100 * d, 25.0) + noise * rng.normal()
         for u, st, y, d in zip(dose.utility_id_eia, dose.state, dose.year, dose.dose)]
    return pd.DataFrame({"utility_id_eia": dose.utility_id_eia, "state": dose.state, "year": dose.year, "value": v})


def one(r, s=ro.H2):
    """The result for set `s` of a run() record."""
    return r["results"][ro.set_label(s)]


def head(r):
    return r["headline"]["log_points"]


def assert_labelled_not_validated(entry_id, res):
    assert res["validation"] == ro.NOT_VALIDATED, entry_id
    assert ro.NOT_VALIDATED in ro.REGISTRY_BY_ID[entry_id].labels


def assert_nothing_dropped(roster, res):
    """Every host of the set is in the design or named among the dropped, with a reason."""
    d = res["design"]
    seen = {h["utility"] for h in d["hosts"]} | {x["utility"] for x in d["hosts_dropped"]}
    assert {f"{u}:{s}" for u, s in zip(roster.utility_id_eia, roster.state)} <= seen
    assert all(x.get("why") for x in d["hosts_dropped"])


# ---- the registry -----------------------------------------------------------------------------------------------------

def test_the_registry_follows_the_plans_order_and_marks_every_entry():
    ids = [e.id for e in ro.REGISTRY]
    order = ["reconciliation_row_U", "reconciliation_row_C", "inventory_against_sales",
             "main_headline_set", "main_ten_year_set", "main_plus_unsettled", "main_every_cohort_utility",
             "second_number_as_assigned", "affiliates_readmitted", "shared_suppliers_removed", "leave_one_comparison_out",
             "leave_one_company_out", "unresolved_ownership_excluded", "later_start_plus_1", "callaway_santanna",
             "longer_horizon", "future_hosts_as_comparisons", "own_state_comparisons", "threshold_1pct", "threshold_5pct",
             "E1", "E2", "E3", "E4a", "E4b", "E5", "E6", "E7_earlier", "condition_1_load_share",
             "condition_4_past_utilization", "influence_each_market_region_left_out", "tariff_check", "regional_layer"]
    assert [i for i in ids if i in order] == order
    # Row M is out of scope for this freeze (D-109): after the executable order, which begins with rows U and C
    assert [e.id for e in ro.ORDER_OF_UNBLINDING][:2] == ["reconciliation_row_U", "reconciliation_row_C"]
    assert ids[-1] == "reconciliation_row_M" and "reconciliation_row_M" not in [e.id for e in ro.ORDER_OF_UNBLINDING]
    for e in ro.REGISTRY:
        assert e.status in ro.STATUSES and (e.status == ro.BUILT) == (e.runner is not None)
        assert e.status == ro.BUILT or e.reason
    for i in ("reconciliation_row_U", "reconciliation_row_C", "inventory_against_sales",
              "callaway_santanna", "estimators_agree", "timing_run_no_anchoring_years",
              "second_number_sensitivity_scenario_a_runner_up_placement",
              "second_number_sensitivity_scenario_b_other_end_of_every_dated_interval",
              "second_number_settled_only_classes_2_to_4"):
        assert ro.REGISTRY_BY_ID[i].status == ro.BUILT and ro.REGISTRY_BY_ID[i].needs, i
    # Joe's ruling of 2026-11-19 (D-107): the scenarios are built, nothing is blocked, the seed is not asked for
    assert "second_number_alternatives" not in ro.REGISTRY_BY_ID
    assert [e.id for e in ro.REGISTRY if e.status == ro.BLOCKED] == []
    assert [e.id for e in ro.REGISTRY if e.status == ro.NOT_BUILT] == ["tariff_check", "regional_layer", "exploratory_work"]
    for i in ("second_number_as_assigned", "second_number_e3_after_period_2024_2025", "second_number_year_by_year"):
        assert not ro.REGISTRY_BY_ID[i].needs, i
    # Joe adopted row U's Short Form rule on 2026-11-20 (D-115): no built entry has a stopped step (session 25)
    assert [e.id for e in ro.REGISTRY if e.stopped_on_research_inputs] == []
    for e in ro.REGISTRY:
        if e.status == ro.BUILT and e.id != "main_headline_set" and "estimate (CR2" in e.estimator:
            assert ro.NOT_VALIDATED in e.labels, e.id
    assert ro.HEADLINE in ro.REGISTRY_BY_ID["main_headline_set"].labels


def test_main_writes_a_quantity_free_list(tmp_path, monkeypatch):
    monkeypatch.setattr(ro, "OUT", tmp_path / "outcome_run_registry.json")
    assert ro.main() == 0
    doc = json.loads((tmp_path / "outcome_run_registry.json").read_text())
    assert [e["id"] for e in doc["entries"]] == [e.id for e in ro.REGISTRY]
    # session 27: the status wording is the freeze's (2026-11-20, commit ea426c4), no longer PROVISIONAL or a DRAFT
    w = doc["what_this_is"]
    assert "frozen on Joe's explicit approval on 2026-11-20 at commit ea426c4" in w and "ed3a2ff" in w
    assert "not externally preregistered" in w and "GATE1_SIGNED did not exist" in w
    assert "PROVISIONAL" not in w and "DRAFT" not in w and "not frozen" not in w
    assert sum(doc["counts_by_status"].values()) == len(ro.REGISTRY)
    built_with_needs = [e.id for e in ro.REGISTRY if e.status == ro.BUILT and e.needs]
    assert doc["built_entries_with_needs"] == len(built_with_needs) > 0 and doc["built_entries_with_needs_ids"] == built_with_needs
    assert "nothing more" in doc["built_is_not_ready"]
    rec = {e["id"]: e for e in doc["entries"]}
    assert rec["reconciliation_row_M"]["status"] == ro.OUT_OF_SCOPE and "data/raw" in rec["reconciliation_row_M"]["reason"]
    assert rec["reconciliation_row_M"]["needs_before_research_data"] is None
    assert rec["inventory_against_sales"]["reads_an_outcome"] is False
    assert doc["built_entries_with_stopped_steps"] == 0                     # D-115 (session 25)
    assert doc["built_entries_with_stopped_steps_ids"] == []
    assert rec["reconciliation_row_U"]["stopped_on_research_inputs"] is None
    assert rec["main_headline_set"]["stopped_on_research_inputs"] is None


VERDICT_WORDS = __import__("re").compile(
    r"\breproduced\b|\bsurviv|\bin_band\b|\bmatch(es)? (their|the paper)|replicat|reproduction test|"
    r"band beside it until joe rules|chooses no sentence|no sentence chosen|is with joe", __import__("re").IGNORECASE)


def test_no_registry_text_says_a_ruled_choice_is_open_or_promises_a_reproduction_verdict():
    """Joe's rulings of 2026-11-19 (D-107 and D-109): the seed, the common-dose scope and the scenarios are ruled; rows U
    and C are comparison-only and return no reproduction verdict; row M is out of scope for this freeze, its verdict logic
    dormant and not applied. No entry's text, row M's included, and nothing in the registry document or its order of
    unblinding says otherwise."""
    for e in ro.REGISTRY:
        text = " ".join([e.section, e.builder, e.estimator, e.reason, e.needs, e.stopped_on_research_inputs, e.context,
                         *e.labels])
        low = text.lower()
        assert "alternatives" not in low and "names no seed" not in low and "choice of scope" not in low, e.id
        assert "is joe's" not in low, e.id
        assert not VERDICT_WORDS.search(text), (e.id, VERDICT_WORDS.search(text))
        if e.id in ("reconciliation_row_U", "reconciliation_row_C"):
            assert "no reproduction verdict" in low and "comparison-only" in low and "d-109" in low, e.id
            assert "not independent validation" in low and "no assigned site is not proof of no facility" in low, e.id
        if e.id == "reconciliation_row_M":
            assert "out of scope for this freeze" in low and "dormant" in low and "not applied in this freeze" in low
            assert "reported first" not in low and ro.RECONCILIATION not in e.labels
    doc = ro.registry_document()
    assert not VERDICT_WORDS.search(json.dumps(doc))
    # the order of unblinding: every entry in it is executable, none is out of scope, and row M is not among them
    assert all(x.status != ro.OUT_OF_SCOPE for x in ro.ORDER_OF_UNBLINDING)
    assert doc["order_of_unblinding"] == [x.id for x in ro.ORDER_OF_UNBLINDING]
    src = (ROOT / "pipeline/analysis/run_outcomes.py").read_text()
    assert "since the choice of scope is Joe's" not in src and "NEEDS_SN_SEED" not in src
    assert "until Joe rules on the TYPE classing" not in src and "U0 is STOPPED" not in src


def test_a_run_that_is_not_built_estimates_nothing_and_says_why(world):
    inp, _ = world
    for i in ("regional_layer", "tariff_check", "exploratory_work"):
        r = ro.run(i, inp, pd.DataFrame(columns=KEY + ["year", "value"]))
        assert r["estimated"] is False and r["results"] is None and r["reason"] and r["status"] != ro.BUILT


# ---- the gate ---------------------------------------------------------------------------------------------------------

def test_the_gate_refuses_whatever_is_set_and_never_calls_the_outcome_reader(tmp_path, monkeypatch):
    """Session 27: the door is built (tests/test_outcome_door_invented.py holds its full tests). Without the gate file or
    the variable it refuses and the reader is never called; with both, an invented plan state and the panel's reader
    replaced by an invented recorder, the third outcome is one call with purpose=POST_FREEZE_PURPOSE (no longer
    NotImplementedError). The real reader is never invoked."""
    called = []
    invented = pd.DataFrame({"utility_id_eia": [1], "state": ["AA"], "year": [2010], "value": [0.0]})

    def recorder(*a, **k):
        called.append((a, k))
        return invented
    monkeypatch.setattr(ro.panel, "load_outcomes", recorder)
    monkeypatch.setattr(ro.panel, "GATE_FILE", tmp_path / "GATE1_SIGNED")
    monkeypatch.delenv(ro.AUTH_ENV, raising=False)
    plan = lambda: {"established": True, "plan_has_no_uncommitted_change": True,           # noqa: E731
                    "freeze_commit_is_an_ancestor_of_head": True, "freeze_commit": ro.FREEZE_COMMIT, "head": "invented",
                    "plan_equals_the_freeze_commits": True}
    with pytest.raises(ro.OutcomeAccessRefused, match="gate file GATE1_SIGNED does not exist"):
        ro.load_outcomes_after_the_freeze(plan_state=plan)
    monkeypatch.setenv(ro.AUTH_ENV, "1")
    with pytest.raises(ro.OutcomeAccessRefused, match="does not exist"):
        ro.load_outcomes_after_the_freeze(plan_state=plan)
    (tmp_path / "GATE1_SIGNED").write_text("invented")
    monkeypatch.setenv(ro.AUTH_ENV, "0")
    with pytest.raises(ro.OutcomeAccessRefused, match=f"{ro.AUTH_ENV} is not set to 1"):
        ro.load_outcomes_after_the_freeze(plan_state=plan)
    assert called == []
    monkeypatch.setenv(ro.AUTH_ENV, "1")
    got = ro.load_outcomes_after_the_freeze(plan_state=plan)
    assert called == [((), {"purpose": ro.POST_FREEZE_PURPOSE})] and got.frame is invented


def test_no_call_in_the_module_reads_an_outcome_file():
    tree = ast.parse((ROOT / "pipeline/analysis/run_outcomes.py").read_text())
    banned = {"load_outcomes", "read_listed_outcomes", "read_parquet", "read_csv", "load_quantities"}
    calls = [n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert not banned & set(calls)
    src = (ROOT / "pipeline/analysis/run_outcomes.py").read_text()
    assert '"blind"' not in src and "'blind'" not in src and "data/blind" not in src and "availability" not in src


# ---- the main estimates ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("entry_id,s", [("main_headline_set", ro.H2), ("main_ten_year_set", (ro.TEN_YEAR_SET, 0.02)),
                                        ("main_plus_unsettled", (ro.PLUS_UNSETTLED, 0.02)),
                                        ("main_every_cohort_utility", ro.E2_)])
def test_the_main_estimate_recovers_the_planted_effect_on_every_set(world, entry_id, s):
    inp, w = world
    r = ro.run(entry_id, inp, outcome(w["dd"]))
    res = one(r, s)
    assert res["numerical_failure"] is None and abs(head(res) - 0.05) < TOL
    lo, hi = res["headline"]["range_90_log_points"]
    assert lo < head(res) < hi
    assert res["trend_illustrations"]["computed"] and res["trend_illustrations"]["count"] == 6
    assert res["early_years_test"]["p_value"] is not None
    assert_nothing_dropped(inp.set_frames(s)[0], res)
    if entry_id == "main_headline_set":
        assert res["validation"] is None and res["count_N"] == 5
        assert res["early_years_reading"][0] in (oa.EARLY_NOT_DETECTED, oa.EARLY_FAILS)
    else:
        assert_labelled_not_validated(entry_id, res)
        assert res["early_years_reading"][0].startswith("not chosen")


@pytest.mark.parametrize("entry_id", ["other_outcome_kwh_per_customer", "other_outcome_bill_per_customer",
                                      "other_outcome_residential_customers"])
def test_other_outcomes_take_their_own_frame_and_are_not_run_on_price(world, entry_id):
    """Session 26 (D-117): the frame is the outcome's LEVEL; its natural log carries the planted 0.05 (tolerance 1e-3)."""
    inp, w = world
    y = outcome(w["dd"])
    assert ro.run(entry_id, inp, y)["failure_in_words"].startswith("no outcome frame was supplied")
    r = ro.run(entry_id, inp, {ro.REGISTRY_BY_ID[entry_id].outcome: levels(y)})
    assert one(r)["computable"] is True and abs(head(one(r)) - 0.05) < TOL
    assert_labelled_not_validated(entry_id, one(r))


# ---- rules 2 and 7 -------------------------------------------------------------------------------------------------

def test_affiliates_readmitted_brings_back_host_4s_affiliate_and_recovers_the_effect(world):
    inp, w = world
    res = one(ro.run("affiliates_readmitted", inp, outcome(w["dd"])))
    m4 = next(h["matches"] for h in res["design"]["hosts"] if h["utility"] == "4:BC")
    assert "777:AD" in m4
    headline = ro.design_facts(inp.build(ro.H2))["hosts"]
    assert "777:AD" not in next(h["matches"] for h in headline if h["utility"] == "4:BC")
    assert abs(head(res) - 0.05) < TOL
    assert_labelled_not_validated("affiliates_readmitted", res)


def test_shared_suppliers_removed_takes_one_match_from_host_2_only(world):
    inp, w = world
    res = one(ro.run("shared_suppliers_removed", inp, outcome(w["dd"])))
    ex = res["supplier_exercise"]
    shared = f"{w['shared_supplier_match'][0]}:{w['shared_supplier_match'][1]}"
    assert [(x["host"], x["match"]) for x in ex["detected_exclusions"]] == [("2:AC", shared)]
    n = {h["utility"]: len(h["matches"]) for h in res["design"]["hosts"]}
    assert n["2:AC"] == 9 and all(v == 10 for k, v in n.items() if k != "2:AC")
    assert abs(head(res) - 0.05) < TOL
    assert_labelled_not_validated("shared_suppliers_removed", res)


@pytest.mark.parametrize("entry_id", ["leave_one_comparison_out", "leave_one_company_out"])
def test_every_deletion_is_estimated_and_recovers_the_effect(world, entry_id):
    inp, w = world
    res = one(ro.run(entry_id, inp, outcome(w["dd"])))
    dels = res["deletions"]
    d = inp.build(ro.H2)
    distinct = {tuple(m) for mk in d.hosts.match_keys for m in mk}
    assert len(dels) == len(distinct)                     # every utility its own company here, but for no parent shared in the fit
    assert all(abs(x["estimate_log_points"] - 0.05) < TOL and x["validation"] == ro.NOT_VALIDATED for x in dels)
    assert all(np.isfinite(x["net_weight_removed"]) and x["estimable_by_the_rank_test_before_any_fit"] for x in dels)
    lo, hi = res["range_of_estimates_across_deletions"]
    assert abs(lo - 0.05) < TOL and abs(hi - 0.05) < TOL
    assert res["deletion_that_moves_it_most"] is not None and res["deletions_not_computed"] == []
    assert res["validation"] == ro.NOT_VALIDATED


def test_the_unresolved_ownership_sensitivity_drops_host_1_by_name(world):
    inp, w = world
    r = ro.run("unresolved_ownership_excluded", inp, outcome(w["dd"]))
    res = one(r)
    hosts = {h["utility"] for h in res["design"]["hosts"]}
    assert "1:AA" not in hosts and "4:BC" in hosts
    assert any(x["utility"] == "1:AA" and "unresolved" in x["why"] for x in res["design"]["hosts_dropped"])
    assert abs(head(res) - 0.05) < TOL
    assert_labelled_not_validated("unresolved_ownership_excluded", res)
    assert_nothing_dropped(inp.set_frames(ro.H2)[0], res)


# ---- runs that move event dates (G-a) -----------------------------------------------------------------------------------

@pytest.mark.parametrize("k,expected,out", [(1, (p(3) + p(4)) / 2 - p(-2), set()),
                                            (3, (p(5) + p(6)) / 2 - p(0), set()),
                                            (5, (p(7) + p(8)) / 2 - p(2), {"5:BD"})])
def test_the_later_start_shift_returns_what_the_planted_path_implies(world, k, expected, out):
    """Every permit-dated site moves k years later, so every host's crossing moves k years (host 5's to 2024 at +5: out,
    named). With the path planted at the real date, the re-dated design's headline is the mean of p(k+2) and p(k+3) less
    p(k-3): exact here because every retained host carries the same shift, so the deviation is in the span of the
    event-time columns (0.055, 0.065, 0.03)."""
    inp, w = world
    res = one(ro.run(f"later_start_plus_{k}", inp, outcome(w["dd"])))
    moved = res["redated"]["crossings"]
    assert all(v["moved_by"] == k for v in moved.values())
    assert set(res["redated"]["hosts_out_and_why"]) == out
    assert abs(head(res) - expected) < TOL
    assert_labelled_not_validated(f"later_start_plus_{k}", res)


def test_e4a_moves_host_1_and_recovers_the_effect_planted_at_the_new_date(world):
    inp, w = world
    r = ro.run("E4a", inp, outcome(w["dd"]))
    res = one(r)
    cross = res["redated"]["crossings"]
    assert cross["1:AA"]["alternative"] == 2015 and all(v["moved_by"] == 0 for k, v in cross.items() if k != "1:AA")
    new = {(int(k.split(":")[0]), k.split(":")[1]): v["alternative"] for k, v in cross.items()}
    at_new = one(ro.run("E4a", inp, outcome(w["dd"], cohorts=new)))
    assert abs(head(at_new) - 0.05) < TOL
    # With the path at the real date the value depends on the fit's weights (one host moves three years, the others do
    # not), so it is not derived exactly here: a finite, labelled estimate is checked, lying between the unmoved hosts'
    # 0.05 and host 1's own implied (p(5) + p(6)) / 2 - p(0) = 0.065, and away from 0.05 by more than the noise.
    assert np.isfinite(head(res)) and 0.05 + TOL < head(res) < 0.065
    assert_labelled_not_validated("E4a", res)


def test_e4b_takes_host_4_out_by_name_and_recovers_the_effect(world):
    inp, w = world
    res = one(ro.run("E4b", inp, outcome(w["dd"])))
    assert res["redated"]["hosts_out_and_why"] == {"4:BC": ir.NO_CROSSING}
    assert res["factors"]["BC"] == {"as_built": pytest.approx(2.0), "alternative": 1.0}
    assert abs(head(res) - 0.05) < TOL
    assert_labelled_not_validated("E4b", res)


@pytest.mark.parametrize("direction,expected", [("earlier", (p(1) + p(2)) / 2 - p(-4)), ("later", (p(3) + p(4)) / 2 - p(-2))])
def test_e7_draws_with_a_known_error_return_the_implied_headline(world, direction, expected):
    """A degenerate error distribution of one year: every permit-dated host moves one year in every draw (0.04 earlier,
    0.055 later). Three draws a direction; every one computes; no failure, a count of zero reported."""
    inp, w = world
    res = one(ro.run(f"E7_{direction}", inp, outcome(w["dd"])))
    assert res["draws_attempted"] == 3 and res["draws_computed"] == 3
    assert res["draws_that_could_not_be_computed"] == {"count": 0, "by_cause": {}}
    for v in res["percentiles_of_the_headline_point_estimate_log_points"].values():
        assert abs(v - expected) < TOL
    assert res["percentiles_are_over"] == "the 3 draws that computed, of 3" and res["validation"] == ro.NOT_VALIDATED


def test_e7_counts_a_draw_that_cannot_be_computed_by_cause():
    inp, w = build_world(e7_errors=12)                    # every host moves twelve years: out of 2011 to 2022 or no crossing
    res = one(ro.run("E7_later", inp, outcome(w["dd"])))
    assert res["draws_computed"] == 0 and res["draws_that_could_not_be_computed"]["count"] == 3
    assert res["draws_that_could_not_be_computed"]["by_cause"] == {"no host retained in the draw": 3}
    assert res["percentiles_of_the_headline_point_estimate_log_points"] is None and res["estimated"] is False


# ---- side runs -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("s", [ro.H2, ro.E2_])
def test_the_longer_horizon_recovers_event_years_4_to_6_and_the_three_year_number(world, s):
    inp, w = world
    res = one(ro.run("longer_horizon", inp, outcome(w["dd"])), s)
    assert abs(res["six_years"]["headline"]["log_points"] - (p(4) + p(5) + p(6)) / 3) < TOL
    assert abs(res["three_years_same_utilities"]["headline"]["log_points"] - 0.05) < TOL
    assert res["validation"] == res["six_years"]["validation"] == res["three_years_same_utilities"]["validation"] == ro.NOT_VALIDATED


def test_future_hosts_enter_host_1s_matches_and_the_effect_comes_back(world):
    inp, w = world
    res = one(ro.run("future_hosts_as_comparisons", inp, outcome(w["dd"])))
    assert res["against_the_headline_design"]["totals"]["future_host_matches"] == 1
    assert "98:AB" in next(h["matches"] for h in res["design"]["hosts"] if h["utility"] == "1:AA")
    assert abs(head(res) - 0.05) < TOL
    assert_labelled_not_validated("future_hosts_as_comparisons", res)


def test_own_state_matches_only_in_the_hosts_state_and_leaves_out_the_absorbed_controls(world):
    """Every host's state holds at least ten eligible units in its region (host 1's North pool in AA; in the West, two of
    each other near ladder per state, plus the ten in BA and the two large units in AC, BC and BD), so all five keep
    their place, each matched inside its own state."""
    inp, w = world
    res = one(ro.run("own_state_comparisons", inp, outcome(w["dd"])))
    hosts = res["design"]["hosts"]
    assert len(hosts) == 5
    assert all(m.split(":")[1] == h["utility"].split(":")[1] for h in hosts for m in h["matches"])
    assert res["headline"]["log_points"] == res["headline"]["log_points"]
    assert [c["column"] for c in res["controls_left_out_as_exactly_absorbed"]][:2] == ["heating_degree_days", "cooling_degree_days"]
    assert res["numerical_failure"] is None and abs(head(res) - 0.05) < TOL
    assert_labelled_not_validated("own_state_comparisons", res)


@pytest.mark.parametrize("entry_id,sets", [("threshold_1pct", [(ro.EVERY, 0.01)]),
                                           ("threshold_5pct", [(ro.HEADLINE_SET, 0.05), (ro.EVERY, 0.05)])])
def test_the_threshold_runs_compose(world, entry_id, sets):
    inp, w = world
    r = ro.run(entry_id, inp, outcome(w["dd"]))
    for s in sets:
        res = one(r, s)
        assert abs(head(res) - 0.05) < TOL and res["count_N"] == 5
        assert_labelled_not_validated(entry_id, res)


@pytest.mark.parametrize("entry_id", ["fuel_mix_categorical", "fuel_mix_none"])
def test_the_fuel_mix_sensitivities_compose(world, entry_id):
    inp, w = world
    res = one(ro.run(entry_id, inp, outcome(w["dd"])))
    assert res["numerical_failure"] is None and abs(head(res) - 0.05) < TOL
    assert_labelled_not_validated(entry_id, res)


# ---- E1 to E6 ------------------------------------------------------------------------------------------------------

def test_e1_returns_about_zero_when_the_effect_starts_at_the_real_date(world):
    inp, w = world
    r = ro.run("E1", inp, outcome(w["dd"]))
    for s in ro.PRIMARY_AND_COMPANION:
        res = one(r, s)
        assert abs(head(res)) < TOL
        assert [x["utility"] for x in res["left_out_before_matching"]] == ["1:AA"]           # cohort 2012
        assert_nothing_dropped(inp.set_frames(s)[0], res)
        assert_labelled_not_validated("E1", res)
    # the same run with the path planted six years early returns it: the fake date is what the design stacks on
    early = {k: g - 6 for k, g in COHORT.items()}
    assert abs(head(one(ro.run("E1", inp, outcome(w["dd"], cohorts=early)))) - 0.05) < TOL


def test_e2_returns_about_zero_for_a_late_host_with_nothing_before_its_crossing(world):
    inp, w = world
    res = one(ro.run("E2", inp, outcome(w["dd"])), (ro.E2_SAMPLE, 0.02))
    assert [h["utility"] for h in res["design"]["hosts"]] == ["98:AB"] and res["design"]["hosts"][0]["cohort"] == 2018
    assert abs(head(res)) < TOL
    assert_labelled_not_validated("E2", res)
    planted = one(ro.run("E2", inp, outcome(w["dd"], cohorts={(98, "AB"): 2018})), (ro.E2_SAMPLE, 0.02))
    assert abs(head(planted) - 0.05) < TOL


def test_e3_keeps_cohorts_2011_to_2017_and_names_host_5(world):
    inp, w = world
    res = one(ro.run("E3", inp, outcome(w["dd"])))
    assert [x["utility"] for x in res["left_out_before_matching"]] == ["5:BD"]
    assert abs(head(res) - 0.05) < TOL and res["count_N"] == 4
    assert_nothing_dropped(inp.set_frames(ro.H2)[0], res)
    assert_labelled_not_validated("E3", res)


def test_e5_drops_host_5_and_its_states_comparisons_without_rematching(world):
    inp, w = world
    res = one(ro.run("E5", inp, outcome(w["dd"])))
    assert res["design"]["gb"]["hosts_removed"][0]["utility"] == "5:BD"
    assert all(len(h["matches"]) == 9 and not any(m.endswith(":BD") for m in h["matches"]) for h in res["design"]["hosts"])
    assert abs(head(res) - 0.05) < TOL
    assert_nothing_dropped(inp.set_frames(ro.H2)[0], res)
    assert_labelled_not_validated("E5", res)


def test_e6_removes_the_two_region_changers_from_host_2(world):
    inp, w = world
    res = one(ro.run("E6", inp, outcome(w["dd"])))
    n = {h["utility"]: len(h["matches"]) for h in res["design"]["hosts"]}
    assert n["2:AC"] == 8 and sorted(res["design"]["gb"]["comparison_units_removed_that_were_matched"]) == ["200:AA", "201:AB"]
    assert abs(head(res) - 0.05) < TOL
    assert_labelled_not_validated("E6", res)


# ---- the four conditions ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("entry_id", ["condition_1_load_share", "condition_2_investor_owned", "condition_3_retail_choice_proxy",
                                      "condition_4_past_utilization"])
def test_every_condition_is_estimable_and_about_zero_when_every_host_has_the_same_effect(world, entry_id):
    inp, w = world
    res = one(ro.run(entry_id, inp, outcome(w["dd"])))
    c = res["contrast"]
    assert c["estimable"] and abs(c["difference_log_points"]) < TOL
    assert res["label"] == ro.DESCRIPTIVE_CONTRAST and c["what_this_is"] == ro.DESCRIPTIVE_CONTRAST
    assert "range" not in c or c.get("range") is None


def test_condition_1_returns_the_planted_difference_between_groups(world):
    """Hosts 1 and 2 are at 15% in event year 3, the rest at 6%: levels of 0.08 and 0.02 give a difference of 0.06."""
    inp, w = world
    levels = {k: (0.08 if k[0] in (1, 2) else 0.02) for k in COHORT}
    res = one(ro.run("condition_1_load_share", inp, outcome(w["dd"], levels=levels)))
    assert abs(res["contrast"]["difference_log_points"] - 0.06) < TOL
    g = res["contrast"]["groups"]
    assert g["first"]["hosts"] == 2 and g["second"]["hosts"] == 3 and "driven_by" in g["first"]


def test_condition_3_names_its_one_host_group_and_reports_the_state_reading_beside_it(world):
    inp, w = world
    res = one(ro.run("condition_3_retail_choice_proxy", inp, outcome(w["dd"])))
    assert res["contrast"]["groups"]["first"]["named"][0]["utility"] == "1:AA" and "driven_by" in res["contrast"]["groups"]["first"]
    assert res["beside_it_the_state_reading"]["reading"] == ro.cn.STATE_ANY


def test_condition_4_takes_its_peak_rows_in_either_form_and_groups_them_the_same(world, monkeypatch):
    """Session 27: RunInputs.peaks in conditions.PEAK_COLUMNS form goes through conditions.read_peaks(frame); in
    PEAKS_AS_READ form, what conditions.read_peaks returns and what the session's one authorized read retains, it is used
    as it is. Invented peaks: both forms give the same grouping and the same contrast on planted host levels (a difference
    by host, so the groups matter), and conditions.read_peaks is never called without a source."""
    inp, w = world
    raw = peaks()
    as_read = ro.cn.read_peaks(raw)
    assert tuple(as_read.columns) == ro.PEAKS_AS_READ
    seen = []
    real = ro.cn.read_peaks

    def guarded(source=None):
        assert source is not None, "conditions.read_peaks called without a source"
        seen.append(tuple(source.columns))
        return real(source)
    monkeypatch.setattr(ro.cn, "read_peaks", guarded)
    levels = {k: 0.01 * k[0] for k in COHORT}
    once = [tuple(ro.cn.PEAK_COLUMNS)] * len(ro.REGISTRY_BY_ID["condition_4_past_utilization"].sets)   # one call a set
    y = outcome(w["dd"], levels=levels)
    a = one(ro.run("condition_4_past_utilization", ro.RunInputs(**{**inp.__dict__, "peaks": raw}), y))
    assert seen == once
    b = one(ro.run("condition_4_past_utilization", ro.RunInputs(**{**inp.__dict__, "peaks": as_read}), y))
    assert seen == once                                                # the as-read form does not go through it again
    shuffled = as_read[list(reversed(ro.PEAKS_AS_READ))]
    c = one(ro.run("condition_4_past_utilization", ro.RunInputs(**{**inp.__dict__, "peaks": shuffled}), y))
    assert a["estimated"] and json.dumps(a["contrast"], sort_keys=True, default=str) == \
        json.dumps(b["contrast"], sort_keys=True, default=str) == json.dumps(c["contrast"], sort_keys=True, default=str)
    hosts = ro.cn.hosts_of(inp.build(ro.H2))
    q = inp.side.q[ro.KEY + ["year", "res_customers"]]
    ga = ro.cn.past_utilization_grouping(hosts, ro.peaks_as_read(raw), inp.has_predecessors, q, succession=inp.succession)
    gb = ro.cn.past_utilization_grouping(hosts, ro.peaks_as_read(as_read), inp.has_predecessors, q,
                                         succession=inp.succession)
    from dataclasses import asdict
    assert set(ga.member.values()) == {True, False}                      # both groups are populated
    assert json.dumps(asdict(ga), sort_keys=True, default=str) == json.dumps(asdict(gb), sort_keys=True, default=str)
    # a frame with peak_mw and any other column set is refused in words; None is stopped before read_peaks
    bad = one(ro.run("condition_4_past_utilization",
                     ro.RunInputs(**{**inp.__dict__, "peaks": as_read.assign(extra=1)}), y))
    assert bad["estimated"] is False and "not exactly" in bad["failure_in_words"] and "peak_mw" in bad["failure_in_words"]
    none = one(ro.run("condition_4_past_utilization", ro.RunInputs(**{**inp.__dict__, "peaks": None}), y))
    assert none["failure_in_words"].startswith("MissingInput") and "RunInputs.peaks" in none["failure_in_words"]
    assert seen == once + [tuple(ro.cn.PEAK_COLUMNS)]          # plus the direct peaks_as_read(raw) above; never without one


# ---- the second number -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("entry_id", ["second_number_as_assigned", "second_number_settled_only_classes_2_to_4",
                                      "second_number_ten_highest_leverage_left_out", "second_number_e3_after_period_2024_2025",
                                      "second_number_year_by_year"])
def test_the_second_number_recovers_its_planted_slope_and_is_labelled_not_calibrated(world, entry_id):
    inp, w = world
    res = one(ro.run(entry_id, inp, second_number_outcome(inp.side.dose)), ro.SN_SAMPLE)
    for cap in sn.CAPS:
        assert abs(res[sn.cap_label(cap)]["est"] - B_SECOND) < 1e-4, cap            # tolerance: 2.5% of the slope
        assert res[sn.cap_label(cap)]["inference"] == sn.INFERENCE_LABEL
    assert res["label"] == ro.NOT_CALIBRATED and ro.NOT_CALIBRATED in ro.REGISTRY_BY_ID[entry_id].labels


def test_the_second_number_without_a_seed_draws_from_20261205(world, monkeypatch):
    """Joe's seed (D-107): a config with no seed draws from second_number.bootstrap_rng(), seed 20261205. The generator
    the run is handed is checked against one built from 20261205 by its first draws."""
    inp, w = world
    seen = []
    real = ro.sn.bootstrap_rng
    monkeypatch.setattr(ro.sn, "bootstrap_rng", lambda *a, **k: seen.append((a, k)) or real(*a, **k))
    cfg = {k: v for k, v in inp.second_number.items() if k not in ("seed", "invented_inputs")}
    inp2 = ro.RunInputs(side=inp.side, sets=inp.sets, second_number=cfg)
    r = ro.run("second_number_as_assigned", inp2, second_number_outcome(inp.side.dose))
    res = one(r, ro.SN_SAMPLE)
    assert r["estimated"] and abs(res[sn.cap_label(sn.MAIN_CAP)]["est"] - B_SECOND) < 1e-4
    assert seen == [((None,), {"invented_inputs": False})]
    assert sn.BOOTSTRAP_SEED == 20261205
    a = real(None).integers(0, 2**31, 5)
    assert np.array_equal(a, np.random.default_rng(20261205).integers(0, 2**31, 5))


def test_the_second_number_with_another_seed_and_no_invented_flag_is_refused_in_words(world):
    inp, w = world
    cfg = {k: v for k, v in inp.second_number.items() if k != "invented_inputs"}
    for eid in ("second_number_as_assigned", "second_number_settled_only_classes_2_to_4", "second_number_year_by_year",
                "second_number_sensitivity_scenario_a_runner_up_placement"):
        r = ro.run(eid, ro.RunInputs(**{**inp.__dict__, "second_number": cfg}), second_number_outcome(inp.side.dose))
        msg = one(r, ro.SN_SAMPLE)["failure_in_words"]
        assert r["estimated"] is False and msg.startswith("ValueError") and "20261205" in msg and "5 is refused" in msg, eid


def test_an_established_common_change_at_the_25_point_form_only_enters_that_forms_settled_run_alone(world):
    """Host 3 (3:BA) is given no dose as assigned, as a utility a load-unknown site reaches, with an established common
    change of 6 points at the 25-point form only (its real change there). At 50 points no finding is supplied, and
    uncapped its histories give two changes (6 and 9), so no single dose: class 1 at both, out of both forms' runs and
    named. At 25 points it is settled (one history) and in the settled run."""
    inp, w = world
    cfg = inp.second_number
    u = "3:BA"
    c25, c50, unc = (sn.cap_label(c) for c in (25.0, 50.0, None))
    assigned = {lab: {k: v for k, v in a.items() if k != u} for lab, a in cfg["assigned"].items()}
    changes = {lab: dict(c) for lab, c in cfg["changes"].items()}
    changes[unc][u] = np.array([6.0, 9.0])
    assert float(cfg["changes"][c25][u][0]) == 6.0
    established = {u: {c25: {"established": True, "dose": 6.0, "why": "invented: every admissible history gives 6"}}}
    sn_cfg = {**cfg, "assigned": assigned, "changes": changes, "no_assigned": [u], "established": established}
    inp2 = ro.RunInputs(**{**inp.__dict__, "second_number": sn_cfg})
    res = one(ro.run("second_number_settled_only_classes_2_to_4", inp2, second_number_outcome(inp.side.dose)), ro.SN_SAMPLE)
    assert res["estimated"]
    assert res["sample"][c25]["left_out_named"] == {}
    assert u in res["sample"][c50]["left_out_named"] and u in res["sample"][unc]["left_out_named"]
    assert "no common-dose finding supplied" in res["sample"][c50]["left_out_named"][u]
    assert res["class_counts"][c25][sn.NO_SINGLE_DOSE] == 0 and res["class_counts"][c50][sn.NO_SINGLE_DOSE] == 1
    assert res["class_counts"][unc][sn.NO_SINGLE_DOSE] == 1
    assert res[c25]["utilities"] == res[c50]["utilities"] + 1 == res[unc]["utilities"] + 1
    assert res["common_dose_finding"]["supplied"] is True
    assert res["common_dose_finding"]["established_by_utility_and_form"] == {u: {c25: True}}
    for cap in sn.CAPS:
        assert abs(res[sn.cap_label(cap)]["est"] - B_SECOND) < 1e-4, cap
    # with the exclusion retained ({}), the utility is out of the 25-point form too
    inp3 = ro.RunInputs(**{**inp.__dict__, "second_number": {**sn_cfg, "established": {}}})
    res3 = one(ro.run("second_number_settled_only_classes_2_to_4", inp3, second_number_outcome(inp.side.dose)), ro.SN_SAMPLE)
    assert u in res3["sample"][c25]["left_out_named"] and res3["common_dose_finding"]["supplied"] is False


def test_a_second_number_config_without_the_common_dose_finding_is_refused_in_words(world):
    inp, w = world
    cfg = {k: v for k, v in inp.second_number.items() if k != "established"}
    inp2 = ro.RunInputs(**{**inp.__dict__, "second_number": cfg})
    for eid in ("second_number_settled_only_classes_2_to_4", "second_number_ten_highest_leverage_left_out"):
        r = ro.run(eid, inp2, second_number_outcome(inp.side.dose))
        msg = one(r, ro.SN_SAMPLE)["failure_in_words"]
        assert r["estimated"] is False and msg.startswith("MissingInput") and "'established'" in msg and "{}" in msg


def test_no_trace_of_the_superseded_class_name():
    for path in (ROOT / "pipeline/analysis/run_outcomes.py", Path(__file__)):
        text = path.read_text().replace("no_trace_of_the_superseded", "")
        assert ("no site " + "in reach") not in text and ("no_site" + "_in_reach") not in text, path


# ---- run_all and a broken run --------------------------------------------------------------------------------------

def diff_diff_here() -> bool:
    try:
        import diff_diff  # noqa: F401
    except ImportError:
        return False
    return True


def test_run_all_returns_every_entry_with_its_status_and_every_built_run_computes(world):
    """Every built entry computes, with three exceptions allowed only where they must be: Callaway and Sant'Anna under an
    interpreter without diff-diff 4.0.0 is a failure in words that names the .venv; the five-highest-load deletion
    on this world, which has five hosts, so dropping five leaves none (not estimable, in words; session 20); and the
    size-band side run, refused in words on this world, where hosts 2 and 3 share a cohort and a cell, as outside this
    freeze (Joe, 2026-11-19, D-111). That it composes is shown on its own variant world
    (test_the_size_band_side_run_composes_and_matches_within_each_hosts_cell)."""
    inp, w = world
    y = outcome(w["dd"])
    out = ro.run_all(inp, all_outcomes(y))
    assert [r["id"] for r in out["runs"]] == [e.id for e in ro.ORDER_OF_UNBLINDING]
    assert [x["id"] for x in out["out_of_scope_for_this_freeze"]] == ["reconciliation_row_M"]
    for r, e in zip(out["runs"], ro.ORDER_OF_UNBLINDING):
        assert r["status"] == e.status
        if e.status == ro.BUILT:
            assert set(r["results"]) == {ro.set_label(s) for s in e.sets}, e.id
            if e.id == "callaway_santanna" and not diff_diff_here():
                assert ".venv" in one(r)["failure_in_words"]
                continue
            if e.id == "influence_five_highest_load_utilities_dropped":
                assert "5 hosts are in the estimate" in one(r)["failure_in_words"] and not r["estimated"]
                continue
            if e.id == "size_band_side_run":
                assert_size_band_refused_on_the_shared_world(r)
                continue
            assert r["estimated"], (e.id, r.get("failures_in_words"))
        else:
            assert r["results"] is None and r["reason"]
    assert out["counts"]["built_set_runs_not_computed"] == (2 if diff_diff_here() else 3)
    assert "size_band_side_run (headline_set at 2%)" in out["counts"]["not_computed"]


def test_a_run_missing_a_unit_year_is_reported_in_words_and_the_others_still_run(world):
    inp, w = world
    y = outcome(w["dd"])
    broken = y[~((y.utility_id_eia == 1) & (y.year == 2010))]
    out = ro.run_all(inp, all_outcomes(broken))
    runs = {r["id"]: r for r in out["runs"]}
    msg = one(runs["main_headline_set"])["failure_in_words"]
    assert msg.startswith("OutcomeMisaligned") and "1:AA in 2010" in msg and "nothing is filled" in msg
    assert runs["main_headline_set"]["estimated"] is False
    assert runs["E2"]["estimated"] and abs(head(one(runs["E2"], (ro.E2_SAMPLE, 0.02)))) < TOL      # host 1 is not in it
    assert "main_headline_set (headline_set at 2%)" in out["counts"]["not_computed"]
    assert len(out["runs"]) == len(ro.ORDER_OF_UNBLINDING) == len(ro.REGISTRY) - 1


# ---- entries wired in session 19: the reconciliation rows, the inventory check, Callaway and Sant'Anna, the table ------

def recon_frames(which="M"):
    f = reconciliation_level(which)
    return {ro.PRICE_DEFAULT_SERVICE: f, ro.PRICE_DELIVERY_INCLUSIVE: f}


# Row M is out of scope for this freeze (Joe, 2026-11-19, D-109). The two tests below are tests of DORMANT code: they call
# the dormant runner (run_outcomes.ROW_M_DORMANT_RUNNER, that is _row_mu("M")) directly on invented inputs, never through
# the registry, which refuses row M (test_row_m_is_out_of_scope_for_this_freeze_and_the_registry_refuses_it).

def dormant_row_m(inputs, frames):
    return ro.ROW_M_DORMANT_RUNNER(inputs, ro.PAPER_SAMPLE, frames, ro.REGISTRY_BY_ID["reconciliation_row_M"])


def test_dormant_row_m_code_returns_the_planted_effect_at_every_step(world):
    """Dormant code (D-109). A constant log effect of 0.03 from each unit's first year, in levels: every step's pooled
    estimate and each ownership class's is 0.03 (tolerance 1e-5; noise sd 1e-6 in logs)."""
    inp, _ = world
    res = dormant_row_m(inp, recon_frames("M"))
    assert [x["step"] for x in res["steps"]] == list(rmu.M_STEPS) and res["steps_not_computed"] == []
    for x in res["steps"]:
        assert abs(x["pooled"]["estimate"] - M_EFFECT) < 1e-5, x["step"]
        assert all(abs(v["estimate"] - M_EFFECT) < 1e-5 for v in x["by_ownership"].values()), x["step"]
    assert res["label"] == ro.RECONCILIATION and res["validation"] == ro.OTHER_ESTIMATOR and len(res["movement"]) == 5


def test_dormant_row_m_code_names_exactly_what_is_missing(world):
    """Dormant code (D-109): a missing treatment or price frame is named per step; without RowMInputs the runner stops in
    words."""
    inp, _ = world
    part = ro.RunInputs(side=inp.side, sets=inp.sets, reconciliation_m=row_m_inputs(steps=("M1", "M2", "M3", "M4")))
    f = reconciliation_level("M")
    res = dormant_row_m(part, {ro.PRICE_DEFAULT_SERVICE: f})
    why = {x["step"]: x.get("failure_in_words") for x in res["steps"] if not x["computed"]}
    assert set(why) == {"M0", "M2", "M3", "M4"} and "no treatment for M0" in why["M0"]
    assert all(why[k].startswith("no outcome frame was supplied for 'res_price'") for k in ("M2", "M3", "M4"))
    assert res["estimated"] and abs(res["steps"][1]["pooled"]["estimate"] - M_EFFECT) < 1e-5
    bare = ro.RunInputs(side=inp.side, sets=inp.sets)
    with pytest.raises(ro.MissingInput, match="RunInputs.reconciliation_m"):
        dormant_row_m(bare, {ro.PRICE_DEFAULT_SERVICE: f})


def test_row_m_is_out_of_scope_for_this_freeze_and_the_registry_refuses_it(world):
    """Joe's ruling of 2026-11-19 (D-109): row M has the out-of-scope status, is in no executable order and no built
    count, and run() refuses it in words before any input or outcome is looked at (here inputs and outcomes that would
    fail on first touch)."""
    e = ro.REGISTRY_BY_ID["reconciliation_row_M"]
    assert ro.OUT_OF_SCOPE == "out_of_scope_for_this_freeze" and ro.OUT_OF_SCOPE in ro.STATUSES
    assert e.status == ro.OUT_OF_SCOPE and e.runner is None and not e.needs and not e.stopped_on_research_inputs
    assert e.outcome is None and e.outcomes == () and e.outcome_names() == []
    assert e not in ro.ORDER_OF_UNBLINDING and ro.OUT_OF_SCOPE_FOR_THIS_FREEZE == (e,)
    assert e.id not in [x.id for x in ro.REGISTRY if x.status == ro.BUILT]
    assert ro.ORDER_OF_UNBLINDING == tuple(x for x in ro.REGISTRY if x.id != e.id)

    class Untouchable:
        def __getattr__(self, name):
            raise AssertionError(f"an input was looked at: {name}")
    with pytest.raises(ro.OutOfScopeForThisFreeze, match=r"out of scope for this freeze .*\(D-109\)"):
        ro.run("reconciliation_row_M", Untouchable(), Untouchable())
    inp, w = world
    with pytest.raises(ro.OutOfScopeForThisFreeze, match="out of scope for this freeze"):
        ro.run("reconciliation_row_M", inp, recon_frames("M"))
    out = ro.run_all(inp, all_outcomes(outcome(w["dd"])))
    assert "reconciliation_row_M" not in [r["id"] for r in out["runs"]]
    assert out["out_of_scope_for_this_freeze"] == [{"id": e.id, "status": ro.OUT_OF_SCOPE, "reason": e.reason}]
    assert out["counts"]["entries"] == len(ro.ORDER_OF_UNBLINDING)


def test_the_registry_document_counts_54_built_0_blocked_3_not_built_and_row_m_out_of_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(ro, "OUT", tmp_path / "outcome_run_registry.json")
    assert ro.main() == 0
    doc = json.loads((tmp_path / "outcome_run_registry.json").read_text())
    c = doc["counts_by_status"]
    assert (c[ro.BUILT], c[ro.BLOCKED], c[ro.NOT_BUILT], c[ro.OUT_OF_SCOPE]) == (54, 0, 3, 1)
    assert c[ro.BUILT] + c[ro.BLOCKED] + c[ro.NOT_BUILT] + c[ro.OUT_OF_SCOPE] == len(doc["entries"]) == len(ro.REGISTRY)
    assert c[ro.DESIGN_ONLY] == c[ro.NEEDS_PACKAGE] == 0
    by = {s: [e["id"] for e in doc["entries"] if e["status"] == s] for s in ro.STATUSES}
    assert {s: len(v) for s, v in by.items()} == c                                      # the counts are the entries'
    assert doc["out_of_scope_for_this_freeze"] == {"count": 1, "ids": ["reconciliation_row_M"],
                                                   "ruling": "Joe, 2026-11-19 (D-109)"}
    assert by[ro.OUT_OF_SCOPE] == doc["out_of_scope_for_this_freeze"]["ids"]
    order = doc["order_of_unblinding"]
    assert order == [e.id for e in ro.ORDER_OF_UNBLINDING] and order[:2] == ["reconciliation_row_U", "reconciliation_row_C"]
    assert "reconciliation_row_M" not in order and len(order) == len(doc["entries"]) - 1
    assert doc["built_entries_with_stopped_steps_ids"] == [] and doc["built_entries_with_stopped_steps"] == 0   # D-115
    assert "reconciliation_row_M" not in doc["built_entries_with_needs_ids"]
    m = next(e for e in doc["entries"] if e["id"] == "reconciliation_row_M")
    assert m["reads_an_outcome"] is False and m["context_reported_as_the_papers"].startswith("The paper's published")
    for k, (est, se) in rmu.PAPER_M.items():
        assert f"{est:.3f} ({se:.3f})" in m["context_reported_as_the_papers"], k


def _sentences(text: str) -> list:
    import re
    return [x for x in re.split(r"(?<=[.;])\s+", text) if x]


def test_row_m_text_never_reads_missing_coverage_as_no_treatment_but_in_the_sentence_that_forbids_it():
    e = ro.REGISTRY_BY_ID["reconciliation_row_M"]
    text = " ".join([e.section, e.builder, e.estimator, e.reason, e.needs, e.stopped_on_research_inputs, e.context,
                     *e.labels])
    hits = [x for x in _sentences(text) if "untreated" in x.lower() or "evidence of no treatment" in x.lower()]
    assert len(hits) == 1 and "never described as untreated or as evidence of no treatment" in hits[0], hits
    low = e.reason.lower()
    for phrase in ("out of scope for this freeze by joe's ruling of 2026-11-19 (d-109)", "m0 to m4 are not run",
                   "not read and not authorized", "approximations of ours", "not to fetch county boundaries",
                   "kept as they are and are dormant", "verdict logic is dormant and not applied in this freeze",
                   "reported as the paper's, as context", "nothing of ours is set beside them as a test"):
        assert phrase in low, phrase


def test_row_u_returns_the_planted_slope_at_every_step_and_returns_the_adopted_u1_sentence(world):
    """ln price = unit + year + 0.01 x ln(MW + 1): every step's pooled coefficient is 0.01 (tolerance 1e-5)."""
    inp, _ = world
    res = one(ro.run("reconciliation_row_U", inp, recon_frames("U")), ro.PAPER_SAMPLE)
    assert [x["step"] for x in res["steps"]] == list(rmu.U_STEPS) and res["steps_not_computed"] == []
    for x in res["steps"]:
        assert abs(x["pooled"]["estimate"] - U_BETA) < 1e-5, x["step"]
    u1 = next(x for x in res["steps"] if x["step"] == "U1")
    assert res["label"] == ro.RECONCILIATION
    # No reproduction verdict anywhere (Joe, D-107 and D-109): U1 returns the adopted sentence (D-109), the ownership
    # estimates and U0's pooled estimate are comparisons with no verdict, the paper's band beside the latter.
    fact = u1["ownership_comparison"]["co_op_and_municipal_each_above_investor_owned_in_our_estimates"]
    assert u1["u1_sentence"]["sentence"] == ((rmu.U1_SENTENCE_EACH_ABOVE if fact else rmu.U1_SENTENCE_NOT_EACH_ABOVE)
                                             + " " + rmu.U1_CONTROLS_SENTENCE)
    for x in res["steps"]:
        assert x["ownership_comparison"]["verdict"] is None and x["ownership_comparison"]["label"] == rmu.U_OWNERSHIP_COMPARISON_LABEL
        assert not {"reproduced", "in_band", "sentence"} & set(x), x["step"]
    u0 = res["steps"][0]
    assert u0["pooled_comparison"]["verdict"] is None and u0["pooled_comparison"]["paper_band_beside"] == list(rmu.BAND_U)
    assert ro.ROW_U_NO_VERDICT in ro.REGISTRY_BY_ID["reconciliation_row_U"].labels


def test_row_u_passes_the_short_form_flags_and_a_flag_based_rule_stops_on_a_missing_flag(world):
    """RowUInputs.sample_flags reaches run_u_step: under 'unit_years_filed' a flag table that flags one unit's 2019 drops
    that unit-year, and the same table with a missing flag stops every step in words (no missing flag read as False)."""
    inp, _ = world
    f = pd.DataFrame([(u, st, y, (u, st, y) == (R_UNITS[0][0], R_UNITS[0][1], 2019)) for u, st in R_UNITS for y in R_YEARS],
                     columns=KEY + ["year", "short_form"])
    spec = rmu.ryu_spec("unit_years_filed")
    b = inp.reconciliation_u
    ok = ro.RowUInputs(spec=spec, treatments=b.treatments, ownership=b.ownership, sample_flags=f, u1_indistinguishable=None)
    res = one(ro.run("reconciliation_row_U", ro.RunInputs(**{**inp.__dict__, "reconciliation_u": ok}), recon_frames("U")),
              ro.PAPER_SAMPLE)
    u1 = next(x for x in res["steps"] if x["step"] == "U1")
    assert any("1 unit-years left out as Short Form filers" in n for n in u1["notes"])
    assert abs(u1["pooled"]["estimate"] - U_BETA) < 1e-5
    miss = f.assign(short_form=f.short_form.astype(object).where(f.year == 2019, None))
    bad = ro.RowUInputs(spec=spec, treatments=b.treatments, ownership=b.ownership, sample_flags=miss, u1_indistinguishable=None)
    res = one(ro.run("reconciliation_row_U", ro.RunInputs(**{**inp.__dict__, "reconciliation_u": bad}), recon_frames("U")),
              ro.PAPER_SAMPLE)
    assert res["estimated"] is False and res["steps_not_computed"] == list(rmu.U_STEPS)
    assert all("missing flag" in x["failure_in_words"] for x in res["steps"])


def test_row_c_returns_the_planted_coefficient_and_names_the_missing_polygon_counts(world):
    """cents per kWh = unit + state-by-year + 0.1 x the operating count: C0 (OLS), C1 and C3 (instrumented) return 0.1
    (tolerance 1e-5). With no polygon counts C0 to C2 are reported as not run, in words, and C3 onward still run."""
    inp, _ = world
    y = {ro.PRICE_CENTS_REAL_2024: row_c_outcome()}
    res = one(ro.run("reconciliation_row_C", inp, y), ro.PAPER_SAMPLE)
    est = {x["step"]: x.get("estimate") for x in res["steps"] if x.get("estimate") is not None}
    for k in ("C0", "C1", "C3"):
        assert abs(est[k] - C_BETA) < 1e-5, k
    assert res["label"] == ro.RECONCILIATION and res["validation"] == ro.OTHER_ESTIMATOR
    # No reproduction verdict (Joe, D-107): every step a comparison with no verdict, C0 with the paper's band beside it
    for x in res["steps"]:
        assert "reproduced" not in x and "in_band" not in x, x.get("step")
        if "comparison" in x and x["comparison"]:
            assert x["comparison"]["verdict"] is None, x.get("step")
    c0 = next(x for x in res["steps"] if x["step"] == "C0")
    assert c0["comparison"]["label"] == rc.C0_COMPARISON_LABEL and list(c0["comparison"]["band_beside"]) == list(rc.BANDS["C0"])
    assert {x.get("spending_series") for x in res["steps"] if x.get("step") == "C3"} == {"paper", "current"}
    assert ro.ROW_C_NO_VERDICT in ro.REGISTRY_BY_ID["reconciliation_row_C"].labels
    # a departure from the specification is refused in words, and the row is not run
    from dataclasses import replace
    off = ro.RowCInputs(**{**inp.reconciliation_c.__dict__, "choices": replace(rc.SPECIFICATION, drop_singletons=False)})
    r = ro.run("reconciliation_row_C", ro.RunInputs(**{**inp.__dict__, "reconciliation_c": off}), y)
    assert r["estimated"] is False and "refuses to depart from its specification" in one(r, ro.PAPER_SAMPLE)["failure_in_words"]
    nop = ro.RunInputs(side=inp.side, sets=inp.sets, reconciliation_c=row_c_inputs(polygon=False))
    res2 = one(ro.run("reconciliation_row_C", nop, y), ro.PAPER_SAMPLE)
    assert res2["steps"][0]["step"] == "C0-C2" and "polygon assignment table was not supplied" in res2["steps"][0]["failure"]
    assert res2["estimated"] and abs(next(x for x in res2["steps"] if x["step"] == "C3")["estimate"] - C_BETA) < 1e-5


def test_inventory_against_sales_reads_no_outcome_and_returns_the_planted_slope(world):
    """Hosts' non-residential sales grow by 0.8 x the inventory's added load and comparison utilities' do not grow: the
    slope is 0.8 (tolerance 1e-9), the plan's 'between' sentence, every host at least half. No outcome is passed."""
    inp, _ = world
    r = ro.run("inventory_against_sales", inp, None)
    res = one(r)
    assert abs(res["slope"]["slope"] - IAS_SLOPE) < 1e-9 and res["reading"] == ias.SENTENCE_BETWEEN
    assert res["share_with_excess_at_least_half_the_inventory"] == 1.0 and res["validation"] == ro.QUANTITIES_ONLY
    assert ro.REGISTRY_BY_ID["inventory_against_sales"].outcome is None and r["reads_an_outcome"] is False
    assert res["settings"] == ias.SETTINGS and res["inputs_are"] == ias.INVENTED_INPUTS
    # inventory_inputs_are is required, and research data is refused before the freeze, in words
    bare = ro.RunInputs(side=inp.side, sets=inp.sets)
    assert "RunInputs.inventory_inputs_are" in one(ro.run("inventory_against_sales", bare, None))["failure_in_words"]
    real = ro.RunInputs(**{**inp.__dict__, "inventory_inputs_are": ias.RESEARCH_DATA_AFTER_THE_FREEZE})
    msg = one(ro.run("inventory_against_sales", real, None))["failure_in_words"]
    assert msg.startswith("InventoryCheckRefused") and "not run on research data" in msg


def test_the_invented_world_has_non_residential_sales_for_2009_to_2011_at_every_host(world):
    """The check's base is the host's non-residential sales averaged over 2009 to 2011 (D-107); every host of the
    invented world has them, so no host is left out for a missing base year."""
    inp, _ = world
    q = inp.side.q
    for u, st, *_ in HOSTS:
        v = q[(q.utility_id_eia == u) & (q.state == st) & q.year.isin(ias.BASE_YEARS)].nonres_mwh
        assert len(v) == 3 and v.notna().all() and (v > 0).all(), (u, st)
    res = one(ro.run("inventory_against_sales", inp, None))
    assert res["hosts_left_out"] == [] and res["hosts_with_a_figure"] == 5


def test_callaway_santanna_without_the_package_is_a_failure_in_words_naming_the_venv(world, monkeypatch):
    inp, w = world

    def missing():
        raise ro.csa.PackageMissing("diff-diff==4.0.0 (import diff_diff) is not installed")
    monkeypatch.setattr(ro.csa, "_import_pinned", missing)
    r = ro.run("callaway_santanna", inp, outcome(w["dd"]))
    res = one(r)
    assert r["estimated"] is False and ".venv" in res["failure_in_words"] and res["label"] == ro.CS_RANGE_LABEL


@pytest.mark.skipif(not diff_diff_here(), reason="diff-diff 4.0.0 is installed only in the gizmo folder's .venv; run this "
                                                  "file with .venv/bin/python -I -m pytest")
def test_callaway_santanna_returns_the_planted_effect_under_the_pinned_package(world, monkeypatch):
    """With no degree-day term in the invented outcome (so nothing outside the package's covariates moves price), the
    headline 0.5 x (ATT(2) + ATT(3)) against g-3 is p(2) and p(3)'s mean, 0.05 (tolerance 1e-3)."""
    inp, w = world
    monkeypatch.setattr(sys.modules[__name__], "HDD_BETA", 0.0)
    res = one(ro.run("callaway_santanna", inp, outcome(w["dd"])))
    assert res["numerical_failure"] is None and abs(res["headline"] - 0.05) < TOL
    assert res["range_label"] == ro.CS_RANGE_LABEL and res["label"] == ro.CS_RANGE_LABEL
    assert res["sample"]["hosts"] == 5
    # and in the side-by-side table its row is estimated, with the plan's label for its range
    t = one(ro.run("estimators_agree", inp, outcome(w["dd"])), ro.SIDE_BY_SIDE)["table"]
    cs = next(r for r in t["rows"] if r["estimator"] == "callaway_santanna")
    assert cs["status"] == "estimated" and cs["plan_labels"] == [ro.et.CALLAWAY_SANTANNA_RANGE_LABEL]
    assert abs(cs["estimate"] - 0.05) < TOL


def test_estimators_agree_assembles_with_callaway_santanna_failed_in_words(world, monkeypatch):
    """The table assembles from the four stacked sets and Callaway and Sant'Anna. The stacked headline row carries the
    kernel's checked validation (no label); the other three carry the plan's words; Callaway and Sant'Anna, made to fail
    as on an interpreter without the package, is a failed row in words."""
    inp, w = world

    def missing():
        raise ro.csa.PackageMissing("diff-diff==4.0.0 (import diff_diff) is not installed")
    monkeypatch.setattr(ro.csa, "_import_pinned", missing)
    res = one(ro.run("estimators_agree", inp, outcome(w["dd"])), ro.SIDE_BY_SIDE)
    rows = {r["name"]: r for r in res["table"]["rows"]}
    assert len(rows) == 5 and res["estimated"]
    head_row = rows[f"stacked: {ro.set_label(ro.H2)}"]
    assert head_row["validated"] and head_row["plan_labels"] == [] and abs(head_row["estimate"] - 0.05) < TOL
    for ss in ((ro.TEN_YEAR_SET, 0.02), (ro.PLUS_UNSETTLED, 0.02), ro.E2_):
        assert rows[f"stacked: {ro.set_label(ss)}"]["plan_labels"] == [ro.NOT_VALIDATED]
    cs = rows[f"Callaway and Sant'Anna: {ro.set_label(ro.H2)}"]
    assert cs["status"] == "failed" and ".venv" in cs["failure_in_words"]
    assert res["table"]["expected_rows_not_supplied"] == []
    # without the validation reference the headline row is not validated and carries the plan's words
    bare = ro.RunInputs(**{**inp.__dict__, "validation_reference": None})
    rows2 = {r["name"]: r for r in one(ro.run("estimators_agree", bare, outcome(w["dd"])), ro.SIDE_BY_SIDE)["table"]["rows"]}
    assert rows2[f"stacked: {ro.set_label(ro.H2)}"]["plan_labels"] == [ro.NOT_VALIDATED]


# ---- the rulings of 2026-11-19 in E2 and E5 ---------------------------------------------------------------------------

def test_e2_applies_the_ownership_rule_and_cannot_run_without_the_table(world):
    """An investor-owned pseudo-host with no ownership row covering its fake window (host 1's unit, invented as a late
    host here) is left out and named; the cooperative late host stays. Without the ownership table the run stops in
    words, so the rule cannot be skipped."""
    inp, w = world
    both = ro.RunInputs(**{**inp.__dict__, "e2_histories": e2_histories(FUTURE[:2], (1, "AA"))})
    res = one(ro.run("E2", both, outcome(w["dd"])), (ro.E2_SAMPLE, 0.02))
    assert [h["utility"] for h in res["design"]["hosts"]] == ["98:AB"]
    (x,) = res["e2_units_left_out"]
    assert x["utility"] == "1:AA" and x["ownership_rule_of_2026_11_19"] is True
    assert res["e2_ownership_rule"] == ro.E2_OWNERSHIP_RULE
    s = inp.side
    no_table = sr.Inputs(s.q, s.dose, s.regions, s.fuel, s.dd, ownership=None, usable=s.usable, gas=s.gas,
                         unknown_load=s.unknown_load, ownership_of=s.ownership_of)
    r = ro.run("E2", ro.RunInputs(**{**inp.__dict__, "side": no_table}), outcome(w["dd"]))
    assert r["estimated"] is False and "RunInputs.side.ownership" in one(r, (ro.E2_SAMPLE, 0.02))["failure_in_words"]


def test_e5_takes_its_states_from_the_full_state_anchor_table(world):
    """BD has a computed factor of 2.5 (dropped), AB the fallback 1.0 (flagged, not dropped). With BC computed at 2.5 too,
    host 4 (BC) leaves as well. Without the table the run stops in words."""
    inp, w = world
    res = one(ro.run("E5", inp, outcome(w["dd"])))
    assert res["states_dropped"] == ["BD"] and res["states_flagged_not_dropped"] == ["AB"]
    assert "full" in res["states_built_from"] or "every state" in res["states_built_from"]
    two = one(ro.run("E5", ro.RunInputs(**{**inp.__dict__, "e5_anchor": e5_anchor(("BC", "BD"))}), outcome(w["dd"])))
    assert two["states_dropped"] == ["BC", "BD"] and {x["utility"] for x in two["design"]["gb"]["hosts_removed"]} == {"4:BC", "5:BD"}
    r = ro.run("E5", ro.RunInputs(side=inp.side, sets=inp.sets), outcome(w["dd"]))
    assert "RunInputs.e5_anchor" in one(r)["failure_in_words"]


# ---- Joe's rulings of 2026-11-19 (D-105), wired in session 20 ------------------------------------------------------------

def test_the_five_highest_load_deletion_composes_and_recovers_the_kept_hosts_effect(world, monkeypatch):
    """This world has five hosts, so the plan's five leave none: the run says so in words and the ranking is still
    reported (hosts 1 and 2 at 150 GWh, hosts 3 to 5 at 60 GWh, each in its own event year 3). To show the deletion
    composes with the kernel, the count is set to two in the test process: hosts 1 and 2 (planted level 0.09) leave with
    their sub-experiments, hosts 3 to 5 (planted level 0.03 from event year 0) keep their matches, and the estimate is
    0.03 (tolerance 1e-3, the noise is 1e-4)."""
    inp, w = world
    lv = {(1, "AA"): 0.09, (2, "AC"): 0.09, (3, "BA"): 0.03, (4, "BC"): 0.03, (5, "BD"): 0.03}
    y = outcome(w["dd"], levels=lv)
    eid = "influence_five_highest_load_utilities_dropped"
    res = one(ro.run(eid, inp, y))
    assert res["estimated"] is False and "5 hosts are in the estimate" in res["failure_in_words"]
    assert [x["dc_gwh"] for x in res["ranking"]["ranking"]] == [150.0, 150.0, 60.0, 60.0, 60.0]
    assert res["validation"] == ro.NOT_VALIDATED
    monkeypatch.setattr(ro.il, "HOW_MANY", 2)
    res = one(ro.run(eid, inp, y))
    assert res["estimated"] and res["ranking"]["to_drop"] == ["1:AA", "2:AC"]
    assert abs(res["estimate_log_points"] - 0.03) < TOL and res["full_design_estimate_log_points"] > 0.04
    assert abs(res["moves_by_log_points"] - (res["estimate_log_points"] - res["full_design_estimate_log_points"])) < 1e-15
    assert res["rank_test_before_any_fit"]["estimable"] is True
    assert_labelled_not_validated(eid, res)
    assert res["deletion"]["hosts_in_the_design"] == ["3:BA", "4:BC", "5:BD"]
    head_matches = {h["utility"]: h["matches"] for h in ro.design_facts(inp.build(ro.H2))["hosts"]}
    kept = ro.il.drop_the_five(inp.build(ro.H2), inp.side.dose)[0]
    assert {h["utility"]: h["matches"] for h in ro.design_facts(kept)["hosts"]} == {k: head_matches[k] for k in ("3:BA", "4:BC", "5:BD")}
    # an exact tie at the line (rank 3 and rank 4 both at 60 GWh) stops the run and names the tied hosts
    monkeypatch.setattr(ro.il, "HOW_MANY", 3)
    res = one(ro.run(eid, inp, y))
    assert res["estimated"] is False and res["ranking"]["tie_at_the_line"]["hosts"] == ["3:BA", "4:BC", "5:BD"]
    assert "exact tie at the line between rank 3 and rank 4" in res["failure_in_words"]


def test_the_customer_weighted_fit_composes_and_returns_the_planted_weighted_answer(world):
    """Residential customers 10,000 to 90,000 (hosts 1 to 5), the same in every year. With every host on the same path
    the weighted headline is 0.05, the planted value (the effective contributions add to one). With host-specific levels
    from event year 0, the weighted estimate is the sum over host rows in event years 0 to 3 of the weighted fit's implied
    weight times the level, computed from the regressors and the customers alone (tolerance 1e-3, the noise is 1e-4), and
    it differs from the unweighted estimate."""
    inp, w = world
    eid = "customer_weighted"
    res = one(ro.run(eid, inp, outcome(w["dd"])))
    assert res["estimated"] and abs(res["estimate_log_points"] - 0.05) < TOL
    assert res["range_90_log_points"] is None and res["label"] == ro.DESCRIPTIVE_WEIGHTED and "descriptive" in res["label"]
    assert res["validation"] == ro.WEIGHTED_NO_VALIDATION and ro.WEIGHTED_NO_VALIDATION in ro.REGISTRY_BY_ID[eid].labels
    tot = sum(h[2] for h in HOSTS)
    assert res["nominal_customer_weight_shares"] == pytest.approx({f"{h[0]}:{h[1]}": h[2] / tot for h in HOSTS}, abs=1e-15)
    assert abs(sum(res["effective_contributions_to_the_weighted_headline"].values()) - 1.0) < 1e-10
    lv = {(1, "AA"): 0.01, (2, "AC"): 0.02, (3, "BA"): 0.03, (4, "BC"): 0.05, (5, "BD"): 0.08}
    d = inp.build(ro.H2)
    rows = oa.stacked_rows(d)
    cw = ro.wf.customer_weights(d, inp.side.q)
    omega = ro.wf.effective_contributions(d, cw)["omega"]
    level = np.array([lv[(int(u), st)] if host and e >= 0 else 0.0
                      for u, st, host, e in zip(rows.block_host_id, rows.block_host_state, rows.is_host, rows.event_year)])
    expect = float(omega @ level)
    y = outcome(w["dd"], levels=lv)
    res = one(ro.run(eid, inp, y))
    assert abs(res["estimate_log_points"] - expect) < TOL
    unweighted = one(ro.run("main_headline_set", inp, y))["headline"]["log_points"]
    assert abs(res["estimate_log_points"] - unweighted) > 2 * TOL
    assert res["design"]["hosts"] and REG_ENTRY_IS_BUILT(eid)


def REG_ENTRY_IS_BUILT(eid):                                    # noqa: N802
    e = ro.REGISTRY_BY_ID[eid]
    return e.status == ro.BUILT and e.runner is not None and not e.needs


def test_the_customer_weighted_fit_without_a_customer_count_is_a_failure_in_words(world, monkeypatch):
    """Host 3's reference-year row taken out of the frame the weights are read from (the design is built as before)."""
    inp, w = world
    real = ro.wf.customer_weights
    gone = lambda q: q[~((q.utility_id_eia == 3) & (q.year == COHORT[(3, "BA")] + ps.REF))]   # noqa: E731
    monkeypatch.setattr(ro.wf, "customer_weights", lambda d, q: real(d, gone(q)))
    r = ro.run("customer_weighted", inp, outcome(w["dd"]))
    assert r["estimated"] is False and "CustomerWeightMissing" in one(r)["failure_in_words"] and "3:BA" in one(r)["failure_in_words"]


def test_the_registry_labels_callaway_santanna_secondary_and_uncalibrated_and_never_the_packages_interval():
    e = ro.REGISTRY_BY_ID["callaway_santanna"]
    assert ro.CS_RANGE_LABEL in e.labels and ro.CS_RANGE_LABEL == ro.csa.RANGE_LABEL == ro.et.CALLAWAY_SANTANNA_RANGE_LABEL
    assert "secondary" in ro.CS_RANGE_LABEL and "uncalibrated" in ro.CS_RANGE_LABEL
    for entry in ro.REGISTRY:
        for text in (entry.estimator, entry.builder, entry.reason, entry.needs, *entry.labels):
            assert "package's interval" not in text and "rests on the package" not in text, entry.id
    assert ro.REGISTRY_BY_ID["customer_weighted"].status == ro.BUILT
    assert ro.REGISTRY_BY_ID["influence_five_highest_load_utilities_dropped"].status == ro.BUILT
    for now in ("influence_each_market_region_left_out", "influence_each_state_left_out", "influence_virginia_left_out",
                "size_band_side_run", "timing_run_no_anchoring_years"):
        assert ro.REGISTRY_BY_ID[now].status == ro.BUILT and ro.NOT_VALIDATED in ro.REGISTRY_BY_ID[now].labels, now


# ---- Joe's ruling of 2026-11-19 (D-107), wired in session 21: the scenarios and R7's runs --------------------------------

SCENARIO_IDS = {ro.ss.SCENARIO_A: "second_number_sensitivity_scenario_a_runner_up_placement",
                ro.ss.SCENARIO_B: "second_number_sensitivity_scenario_b_other_end_of_every_dated_interval"}


@pytest.mark.parametrize("name", list(SCENARIO_IDS))
def test_each_sensitivity_scenario_recovers_its_planted_slope_and_reports_its_sample_differences(world, name):
    """The outcome is linear in the SCENARIO's load shares (0.004 per point), which differ from the primary run's: under
    A host 3 is at 9 points, under B host 4 at 12 and host 5 has load and no base. Every form returns 0.004 (tolerance
    1e-4, 2.5% of the slope). Under B host 5 leaves the sample and is named; the primary run's sample here is the late host
    short (a unit the scenario takes and the primary run does not, as the load-unknown units are), so it is named as in
    the scenario only."""
    inp, _ = world
    eid = SCENARIO_IDS[name]
    pts = inp.second_number["scenario_points"][name]
    cfg = {**inp.second_number, "units": [u for u in inp.second_number["units"] if u != FUTURE[:2]]}
    r = ro.run(eid, ro.RunInputs(**{**inp.__dict__, "second_number": cfg}), points_outcome(pts))
    res = one(r, ro.SN_SAMPLE)
    assert res["estimated"], res.get("failure_in_words")
    for cap in sn.CAPS:
        assert abs(res[sn.cap_label(cap)]["est"] - B_SECOND) < 1e-4, cap
    assert res["label"] == ro.NOT_CALIBRATED and res["scenario_label"] == ro.ss.LABELS[name]
    assert set(ro.REGISTRY_BY_ID[eid].labels) == {ro.ss.LABELS[name], ro.NOT_CALIBRATED}
    assert "not a bound" in res["scenario_label"] and res["scenario"] == name
    diff = res["sample_differences_from_the_primary_run"]
    assert diff["in_the_scenario_only"] == ["98:AB"]
    if name == ro.ss.SCENARIO_B:
        assert diff["in_the_primary_run_only"] == ["5:BD"] and diff["units_with_load_and_no_positive_base_no_dose"] == ["5:BD"]
        assert any(x["utility"] == "5:BD" and "no dose" in x["why"] for x in res["left_out"])
    else:
        assert diff["in_the_primary_run_only"] == []
    # the primary run's outcome is not the scenario's: fitted on it the slope moves, so the scenario's points are used
    off = one(ro.run(eid, inp, second_number_outcome(inp.side.dose)), ro.SN_SAMPLE)
    assert abs(off[sn.cap_label(sn.MAIN_CAP)]["est"] - B_SECOND) > 1e-4
    # without the scenario's points the run stops in words
    cut = {**inp.second_number, "scenario_points": {}}
    r = ro.run(eid, ro.RunInputs(**{**inp.__dict__, "second_number": cut}), points_outcome(pts))
    assert r["estimated"] is False and "'scenario_points'" in one(r, ro.SN_SAMPLE)["failure_in_words"]


def test_each_market_region_left_out_recovers_the_planted_level_of_the_hosts_that_stay(world):
    """Two regions: North holds host 1 and its comparison utilities, West the other four. Host 1 is planted at 0.09 and
    the others at 0.03 from event year 0: North left out returns 0.03, West left out 0.09 (tolerance 1e-3), and the
    deletion that moves the estimate most is named. Each deleted design is labelled not validated, and so is the full
    design beside them."""
    inp, w = world
    eid = "influence_each_market_region_left_out"
    lv = {(1, "AA"): 0.09, (2, "AC"): 0.03, (3, "BA"): 0.03, (4, "BC"): 0.03, (5, "BD"): 0.03}
    res = one(ro.run(eid, inp, outcome(w["dd"], levels=lv)))
    assert res["estimated"] and res["validation"] == ro.NOT_VALIDATED and res["label"] == ro.INFLUENCE_LABELS["region"]
    by = {x["value"]: x for x in res["deletions"]}
    assert set(by) == {"North", "West"}
    assert by["North"]["what_left"]["hosts_leaving"] == ["1:AA"]
    assert abs(by["North"]["result"]["headline"]["log_points"] - 0.03) < TOL
    assert abs(by["West"]["result"]["headline"]["log_points"] - 0.09) < TOL
    assert all(x["result"]["validation"] == ro.NOT_VALIDATED for x in res["deletions"])
    assert res["full_design"]["validation"] == ro.NOT_VALIDATED
    s = res["summary"]
    lo, hi = s["range_of_estimates_log_points"]
    assert abs(lo - 0.03) < TOL and abs(hi - 0.09) < TOL and s["moves_it_most"]["deletion"] == "region West"
    assert_labelled_not_validated(eid, res)
    # every host on the same path: each deletion returns the planted 0.05
    res = one(ro.run(eid, inp, outcome(w["dd"])))
    assert all(abs(x["result"]["headline"]["log_points"] - 0.05) < TOL for x in res["deletions"])


def test_each_state_left_out_removes_its_hosts_and_its_comparison_utilities_without_rematching(world):
    """Eight states, each a host's or a matched comparison utility's. AA left out takes host 1 and every AA comparison
    utility from the other hosts' matches (two from each nearest ten, so eight left: named as nothing, at least five).
    Every deletion returns the planted 0.05 (tolerance 1e-3); Virginia is not among them."""
    inp, w = world
    eid = "influence_each_state_left_out"
    res = one(ro.run(eid, inp, outcome(w["dd"])))
    assert res["estimated"] and res["label"] == ro.INFLUENCE_LABELS["state"]
    by = {x["value"]: x for x in res["deletions"]}
    assert sorted(by) == sorted(STATES) and "VA" not in by
    aa = by["AA"]
    assert aa["what_left"]["hosts_leaving"] == ["1:AA"]
    left = {x["host"]: x["matches_left"] for x in aa["after_deletion"]["matches_left_by_host"]}
    assert set(left) == {"2:AC", "3:BA", "4:BC", "5:BD"} and all(n == 8 for n in left.values())
    assert aa["after_deletion"]["hosts_with_fewer_than_five_matches_inadequately_supported_kept"] == []
    assert all(abs(x["result"]["headline"]["log_points"] - 0.05) < TOL for x in res["deletions"])
    assert all(x["result"]["validation"] == ro.NOT_VALIDATED for x in res["deletions"])
    lo, hi = res["summary"]["range_of_estimates_log_points"]
    assert abs(lo - 0.05) < TOL and abs(hi - 0.05) < TOL
    assert_labelled_not_validated(eid, res)


def test_virginia_left_out_says_it_removes_nothing_and_is_not_presented_as_a_check_passed(world):
    inp, w = world
    eid = "influence_virginia_left_out"
    y = outcome(w["dd"])
    res = one(ro.run(eid, inp, y))
    assert res["virginia"] == ro.idl.VIRGINIA_REMOVES_NOTHING and "not presented as a check passed" in res["virginia"]
    assert res["estimated"] and abs(res["estimate_log_points"] - 0.05) < TOL
    full = one(ro.run("main_headline_set", inp, y))["headline"]["log_points"]
    assert abs(res["estimate_log_points"] - full) < 1e-12          # nothing removed: the design's own estimate
    assert res["deletions"][0]["what_left"]["removes_nothing"] is True
    assert res["validation"] == ro.NOT_VALIDATED and res["deletions"][0]["result"]["validation"] == ro.NOT_VALIDATED
    assert_labelled_not_validated(eid, res)


# The size-band side run's world (Joe, 2026-11-19, D-111). The registry's world has hosts 2 (AC, 30,000) and 3 (BA, 50,000)
# in cohort 2015 and both in West and the 10,000 to 99,999 band, a shared cohort and cell, which size_band_run.build refuses
# as outside this freeze. The variant sets host 3 aside from the headline set at 2%: the smallest change that leaves no two
# hosts sharing a cohort and a cell. Nothing else in the world changes, and no other test uses the variant.
SIZE_BAND_HOSTS = [h for h in HOSTS if h[0] != 3]


def size_band_inputs(inp):
    t, c = inp.sets[ro.H2]
    return ro.RunInputs(**{**inp.__dict__, "sets": {**inp.sets, ro.H2: (t[t.utility_id_eia != 3], c)}})


def assert_size_band_refused_on_the_shared_world(r):
    """The registry's world: refused in words before any design is returned, naming 2:AC and 3:BA and the ruling."""
    msg = one(r)["failure_in_words"]
    assert r["estimated"] is False and msg.startswith("OutsideTheAdoptedScope"), msg
    assert "hosts 2:AC and 3:BA share cohort 2015" in msg and "D-111" in msg and "outside this freeze" in msg, msg


def test_the_size_band_side_run_composes_and_matches_within_each_hosts_cell(world):
    """On the registry's world (hosts 2 and 3 in one cohort and one cell) the run is refused in words as outside this
    freeze (D-111). On the variant world (host 3 set aside) every host is in the 10,000 to 99,999 band, so each host's
    comparison utilities are every eligible unit of its reference-year region: North's for host 1, West's for the rest
    (host 4's affiliate out under rule 2.3). The planted 0.05 comes back (tolerance 1e-3), labelled a side run on a
    design on which no validation was made: "built" means the builder and the estimator compose on invented inputs."""
    inp, w = world
    eid = "size_band_side_run"
    assert_size_band_refused_on_the_shared_world(ro.run(eid, inp, outcome(w["dd"])))
    inp = size_band_inputs(inp)
    res = one(ro.run(eid, inp, outcome(w["dd"])))
    assert res["estimated"] and abs(res["estimate_log_points"] - 0.05) < TOL
    assert res["label"] == ro.sbr.LABEL and res["result"]["validation"] == ro.NOT_VALIDATED
    cells = {c["host"]: c for c in res["cells"]}
    assert set(cells) == {f"{h[0]}:{h[1]}" for h in SIZE_BAND_HOSTS}
    assert cells["1:AA"]["region"] == "North" and all(region(_key(m), 2009) == "North" for m in cells["1:AA"]["comparisons"])
    assert all(c["region"] == "West" for h, c in cells.items() if h != "1:AA")
    assert "777:AD" not in cells["4:BC"]["comparisons"]
    assert all(c["comparison_utilities_in_its_cell"] > 10 for c in cells.values())
    assert_labelled_not_validated(eid, res)
    # a level planted on host 1 alone moves the estimate: the fit is on the size-band design
    lv = {(1, "AA"): 0.09, (2, "AC"): 0.03, (3, "BA"): 0.03, (4, "BC"): 0.03, (5, "BD"): 0.03}
    moved = one(ro.run(eid, inp, outcome(w["dd"], levels=lv)))
    assert 0.03 + TOL < moved["estimate_log_points"] < 0.09 - TOL


def _key(label):
    u, st = label.split(":")
    return (int(u), st)


def test_the_timing_run_adds_its_host_at_its_year_and_recovers_the_planted_effect(world):
    """The late host (98:AB) added at an invented no-anchoring year of 2016, matched at its own reference year; the other
    hosts' matches are checked unchanged. With the path planted at 98's year too, the timing run returns 0.05 (tolerance
    1e-3); with nothing planted on 98 it does not, so the added host is in the fit. Without timing_added the run stops in
    words."""
    inp, w = world
    eid = "timing_run_no_anchoring_years"
    planted = outcome(w["dd"], cohorts={**COHORT, FUTURE[:2]: 2016})
    res = one(ro.run(eid, inp, planted))
    assert res["estimated"] and abs(res["estimate_log_points"] - 0.05) < TOL, res.get("failure_in_words")
    rec = res["record"]
    assert rec["original_hosts_unchanged"] is True and "98:AB" in rec["hosts_in_the_timing_design"]
    (added,) = rec["added_hosts"]
    assert added["host"] == "98:AB" and added["no_anchoring_year"] == 2016 and added["reference_year"] == 2013
    assert added["in_the_design"] is True
    assert res["label"] == ro.tr.LABEL and res["result"]["validation"] == ro.NOT_VALIDATED and res["count_N"] == 6
    assert_labelled_not_validated(eid, res)
    unplanted = one(ro.run(eid, inp, outcome(w["dd"])))
    assert unplanted["estimate_log_points"] < 0.05 - TOL
    r = ro.run(eid, ro.RunInputs(**{**inp.__dict__, "timing_added": None}), planted)
    assert r["estimated"] is False and "RunInputs.timing_added" in one(r)["failure_in_words"]


# ---- session 24 (Joe, 2026-11-20, D-113): where the drift flag comes from ------------------------------------------------

def _drift_file(tmp_path, **over) -> Path:
    """An invented exercise-4a result: only the fields catches_drift_from_file reads, each the module's unless `over`
    replaces it. No rate, no dataset and no price is in it."""
    from pipeline.analysis import early_years_drift as eyd
    doc = {"seed": eyd.SEED, "drift_log_points_a_year": eyd.DRIFT,
           "design_inputs_sha256": eyd.REQUIRED_DESIGN_INPUTS + "0" * 52,
           "reading_rule": {"outcome": eyd.ADDED}}
    for k, v in over.items():
        if k == "outcome":
            doc["reading_rule"]["outcome"] = v
        else:
            doc[k] = v
    p = tmp_path / "invented_early_years_drift.json"
    p.write_text(json.dumps(doc))
    return p


@pytest.mark.parametrize("which,expected", [("ADDED", {ps.HEADLINE_SET: True}), ("NOT_ADDED", {ps.HEADLINE_SET: False}),
                                            ("SPLIT", {})])
def test_the_drift_flag_follows_each_of_the_three_outcomes_for_the_headline_set_alone(tmp_path, which, expected):
    from pipeline.analysis import early_years_drift as eyd
    got = ro.catches_drift_from_file(_drift_file(tmp_path, outcome=getattr(eyd, which)))
    assert got == expected
    for other in (ps.TEN_YEAR_SET, ro.PLUS_UNSETTLED, ro.EVERY):
        assert got.get(other) is None, other


def test_an_absent_drift_file_gives_no_value_and_the_reading_selects_no_second_sentence(tmp_path):
    assert ro.catches_drift_from_file(tmp_path / "no_such_file.json") == {}


@pytest.mark.parametrize("over,words", [
    ({"design_inputs_sha256": "0" * 64}, "design-inputs hash"),
    ({"design_inputs_sha256": None}, "design-inputs hash"),
    ({"seed": 20261205}, "seed"),
    ({"seed": True}, "seed"),
    ({"drift_log_points_a_year": 0.02}, "drift"),
    ({"outcome": "added for every set"}, "reading-rule outcome"),
    ({"outcome": None}, "reading-rule outcome"),
])
def test_a_drift_file_that_is_not_exercise_4as_is_refused_in_words(tmp_path, over, words):
    with pytest.raises(ro.DriftFileRefused, match=words):
        ro.catches_drift_from_file(_drift_file(tmp_path, **over))


def test_the_stored_drift_file_gives_true_for_the_headline_set_and_nothing_for_another_and_the_text_quotes_it():
    """The real stored file (a frozen summary of made-up prices; no price in it) is read by name. Its outcome is 'added',
    so the headline set gets True and no other set gets a value. The registry's text quotes the file's two rates and
    their exact intervals."""
    assert ro.EARLY_YEARS_DRIFT_FILE.exists()
    got = ro.catches_drift_from_file()
    assert got == {ps.HEADLINE_SET: True} and got == ro.catches_drift_from_file(ro.EARLY_YEARS_DRIFT_FILE)
    assert got.get(ps.TEN_YEAR_SET) is None and got.get(ro.EVERY) is None
    doc = json.loads(ro.EARLY_YEARS_DRIFT_FILE.read_text())
    text = ro.REGISTRY_BY_ID["main_headline_set"].estimator
    for proc in ("G0_as_in_D38", "G6_all_of_it"):
        d = doc["by_process"][proc]["early_years_test_detects_the_drift"]
        lo, hi = d["exact_95_interval"]
        assert d["rate"] < 0.5 and f"{d['rate']:g}" in text and f"{lo:g} to {hi:g}" in text, proc
    for phrase in ("data/frozen/early_years_drift_selected_procedure.json", "catches_drift_from_file", "D-113",
                   "exercise 4a", "changes no rule", "already fixed", "not evidence about real pre-trends",
                   "two assumed kinds", "companion sets get no value"):
        assert phrase in text, phrase


def test_no_runner_fills_the_drift_flag_unless_a_caller_passes_it():
    tree = ast.parse((ROOT / "pipeline/analysis/run_outcomes.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and (getattr(n.func, "id", None) == "catches_drift_from_file"
                  or getattr(n.func, "attr", None) == "catches_drift_from_file")]
    assert calls == []
    assert ro.RunInputs.__dataclass_fields__["catches_drift"].default is None

# ---- session 25 (Joe, 2026-11-20, D-115): row U under the adopted Short Form rule; E7's contexts for both sets -------------
# Replaces session 24's test_row_u_stopped_step_records_stage_2_taken_and_the_rule_undecided, which tested the stopped step
# D-115 ended.

ROW_U_BARRED = ("is joe's", "is with joe", "chooses no sentence", "not a filer", "did not file", "not filed", "non-filer",
                "nonfiler", "three filings excluded", "pre-registered", "preregistered", "stopped outside 2019",
                "undecided", "'none_in_outcome_frame' runs", "until joe rules")


def _entry_text(e) -> str:
    return " ".join([e.section, e.builder, e.estimator, e.reason, e.needs, e.stopped_on_research_inputs, e.context,
                     *e.labels])


def test_row_u_has_no_stopped_step_and_its_text_carries_the_adopted_rule():
    e = ro.REGISTRY_BY_ID["reconciliation_row_U"]
    assert e.status == ro.BUILT and e.stopped_on_research_inputs == "" and e.as_record()["stopped_on_research_inputs"] is None
    assert not hasattr(ro, "STOPPED_U")
    assert [x.id for x in ro.REGISTRY if x.stopped_on_research_inputs] == []
    assert rmu.U_SHORT_FORM_ADOPTED_LABEL in e.needs and rmu.U_SHORT_FORM_ADOPTED_CODE == "unit_years_filed"
    text = _entry_text(e)
    low = text.lower()
    for phrase in ("d-115", "ryu_spec(reconciliation_mu.u_short_form_adopted_code)", "adopted_row_u_flags",
                   "adopted_row_u_choices", "where a record shows a short form filing", "explicitly incomplete",
                   "1,780 have a missing flag and 193 have no flags row", "kept with no record either way",
                   "does not establish non-filing", "not the paper's sample", "comparison-only",
                   "three-year count is taken after the exclusion",
                   "one flagged unit-year of 2019 leaves directly, and the same utility's 2023 and 2024 leave through the "
                   "three-year requirement", "step_window=(2015, 2025)", "never from a new read under data/raw",
                   "18,172 rows", "13,090 unit-years", "recorded as not computed", "1,798", "approximately 560",
                   "for comparison only and are no part of any reason"):
        assert phrase in low, phrase
    for bad in ROW_U_BARRED:
        assert bad not in low, bad
    assert "—" not in text
    assert "availability" not in (ROOT / "pipeline/analysis/run_outcomes.py").read_text().lower()


def test_row_u_entry_counts_are_the_stored_quantity_summary_and_the_papers_are_printed_as_the_papers():
    """The counts NEEDS_U carries as text equal data/frozen/reconciliation_mu_design.json (a quantity-side summary; no
    price in it) and the paper's two figures equal short_form_filers' constants."""
    b = json.loads((ROOT / "data/frozen/reconciliation_mu_design.json").read_text())["short_form_flags_for_row_u"]
    s = b["sample_under_the_adopted_short_form_rule"]
    t = ro.REGISTRY_BY_ID["reconciliation_row_U"].needs
    n = lambda v: f"{int(v):,}"                                                              # noqa: E731
    fr, kept = s["frame_with_no_exclusion"], s["sample_under_the_adopted_rule"]
    y19 = s["year_2019_explicitly_incomplete"]["in_the_frame_with_no_exclusion"]
    assert (f"the frame with no exclusion has {n(fr['unit_years'])} unit-years and {n(fr['utilities'])} utilities"
            in t)
    assert f"leaving {n(kept['unit_years'])} unit-years and {n(kept['utilities'])} utilities" in t
    assert (s["leaving_directly_where_a_record_shows_a_filing"]["unit_years_by_year"]
            == {str(y): int(y == 2019) for y in range(2015, 2025)})
    assert (s["leaving_through_the_three_year_requirement_after_the_exclusion"]["unit_years_by_year"]
            == {str(y): int(y in (2023, 2024)) for y in range(2015, 2025)})
    assert s["leaving_through_the_three_year_requirement_after_the_exclusion"]["utilities"] == 1
    assert (f"Of the frame's {n(y19['unit_years_in_2019'])} unit-years of 2019, {n(y19['flagged_true'])} has a flag of "
            f"true, {n(y19['kept_with_no_record_either_way_missing_flag'])} have a missing flag and "
            f"{n(y19['kept_with_no_record_either_way_no_flags_row'])} have no flags row") in t
    u3 = b["step_u3_window_under_the_adopted_rule"]
    assert (f"({n(u3['unit_years_in_the_years_past_row_us_own_window']['2025'])} unit-years, "
            f"{n(u3['of_them_with_a_record_of_a_filing'])} with a record of a filing" in t)
    assert f"({n(b['filer_table_rows'])} rows" in t
    assert f"paper's {n(sff.PAPER_RETAINED_UTILITIES)} utilities retained" in t and sff.PAPER_SHORT_FORM_GROUP in t


def _row_u_run(sample_flags, outcome_frame):
    b = row_u_inputs()
    inp = ro.RunInputs(side=None, sets={}, reconciliation_u=ro.RowUInputs(
        spec=rmu.ryu_spec(rmu.U_SHORT_FORM_ADOPTED_CODE), treatments=b.treatments, ownership=b.ownership,
        sample_flags=sample_flags, u1_indistinguishable=None), reconciliation_u_inputs_are=ro.INVENTED_INPUTS)
    return ro.run("reconciliation_row_U", inp, {ro.PRICE_DEFAULT_SERVICE: outcome_frame,
                                                ro.PRICE_DELIVERY_INCLUSIVE: outcome_frame})


def test_row_u_runs_under_the_adopted_rule_with_flags_from_adopted_row_u_flags_and_returns_the_known_sample():
    """Known answer, invented records. A table row for unit 0 in 2017 and a 2019 flag of true for units 1 and 4 leave;
    unit 2's missing 2019 flag and unit 3's absent flags row are kept with no record either way; unit 4 is in the outcome
    only in 2018 to 2020, so once its flagged 2019 leaves it has two years and its 2018 and 2020 leave through the
    three-year count, taken after the exclusion. In 2015 to 2024: 35 x 10 + 3 = 353 unit-years, less 3 by the records
    and 2 by the count, 348 (a count taken before the exclusion would keep 350). U3 adds 2025 for the 35 units that have
    it: 383. Every step's pooled slope stays the planted 0.01 (tolerance 1e-5)."""
    u0, u1, u2, u3, u4 = R_UNITS[:5]
    flags = adopted_flags(table=u_filer_table(extra=[(*u0, 2017)]), flags=u_2019_flags(true=[u1, u4], no_row=[u3]))
    f = {(int(a), str(b), int(c)): bool(v) for a, b, c, v in zip(flags.utility_id_eia, flags.state, flags.year,
                                                                   flags.short_form)}
    assert f[(*u0, 2017)] and f[(*u1, 2019)] and f[(*u4, 2019)] and int(flags.short_form.sum()) == 3
    assert not f[(*u2, 2019)] and not f[(*u3, 2019)] and not f[(*u0, 2016)] and not f[(*u1, 2025)]
    y = reconciliation_level("U")
    y = y[~((y.utility_id_eia == u4[0]) & (y.state == u4[1]) & ~y.year.isin([2018, 2019, 2020]))]
    res = one(_row_u_run(flags, y), ro.PAPER_SAMPLE)
    assert res["estimated"] is True and res["steps_not_computed"] == []
    for x in res["steps"]:
        assert x["pooled"]["n"] == (383 if x["step"] == "U3" else 348), (x["step"], x["pooled"]["n"])
        assert "3 unit-years left out as Short Form filers (unit_years_filed)" in x["notes"], x["notes"]
        assert any(m.startswith("2 unit-years of utilit") for m in x["notes"]), x["notes"]
        assert abs(x["pooled"]["estimate"] - U_BETA) < 1e-5, x["step"]
        assert x["specification"]["short_form_exclusion"]["as_supplied"] == rmu.U_SHORT_FORM_ADOPTED_CODE
        assert x["short_form_status"].endswith(rmu.U_SHORT_FORM_ADOPTED_LABEL)


def test_row_u_flags_that_miss_an_outcome_unit_year_record_every_step_not_computed_in_words():
    """A frame for adopted_row_u_flags that leaves out one outcome unit-year (unit 5 in 2016, in every step's window):
    no step runs, each is recorded as not computed with the words of run_u_step's stop, and nothing reads the gap as
    kept."""
    frame = u_flags_frame(drop=[(*R_UNITS[5], 2016)])
    r = _row_u_run(adopted_flags(frame=frame), reconciliation_level("U"))
    res = one(r, ro.PAPER_SAMPLE)
    assert r["estimated"] is False and res["estimated"] is False and res["steps_not_computed"] == list(rmu.U_STEPS)
    for x in res["steps"]:
        assert x["computed"] is False
        assert "1 outcome unit-years have no row in sample_flags and 0 have a missing flag" in x["failure_in_words"]
        assert "no missing flag is read as False" in x["failure_in_words"]
    assert all(s in res["failure_in_words"] for s in rmu.U_STEPS)


def test_e7_entries_name_each_sets_context_and_where_both_quantity_summaries_are_written():
    """E7 is wired for the headline set and for every cohort utility on the quantity side (inventory_runs.E7_SETS). Each
    E7 entry says what the caller's context for each set must be, every cohort utility's with no set-aside list as
    design.split gives it, and names both blocks of data/frozen/inventory_run_designs.json. No file is read here."""
    assert ir.E7_SETS == (ps.HEADLINE_SET, ro.EVERY) == tuple(s[0] for s in ro.PRIMARY_AND_COMPANION)
    assert ir.E7_BLOCK_KEY == {ps.HEADLINE_SET: "E7", ro.EVERY: "E7_every_cohort_utility"}
    assert ir.aside_for(0.02, ro.EVERY) == set() and ir.THETA == 0.02 and ir.E7_SEED == 20261203 and ir.E7_DRAWS == 200
    for eid in ("E7_earlier", "E7_later"):
        e = ro.REGISTRY_BY_ID[eid]
        assert e.sets == ro.PRIMARY_AND_COMPANION and not e.needs, eid
        for phrase in ("inventory_runs.Context.from_files(0.02) for the headline set",
                       'inventory_runs.Context.from_files(0.02, which="every_cohort_utility") for every cohort utility',
                       "no set-aside list, as design.split does", "data/frozen/inventory_run_designs.json",
                       "blocks E7 and E7_every_cohort_utility", "200 draws a direction under seed 20261203"):
            assert phrase in e.builder, (eid, phrase)
        assert "headline set alone" not in e.builder.lower() and "headline set only" not in e.builder.lower()
    doc = ro.RunInputs.__doc__
    assert 'which="every_cohort_utility"' in doc and "inventory_runs.aside_for" in doc


# ---- session 26 (Joe, 2026-11-20, D-117): the supplementary outcomes, row C's price series, ownership, E7's denominator ---

from pipeline.analysis import supplementary_outcomes as so  # noqa: E402

SUPPLEMENTARY_IDS = {ro.KWH: "other_outcome_kwh_per_customer", ro.BILL: "other_outcome_bill_per_customer",
                     ro.CUSTOMERS: "other_outcome_residential_customers"}


def _same(a, b) -> bool:
    """Exact equality of two results, nested dicts, lists, arrays and frames included; NaN equals NaN."""
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(_same(x, z) for x, z in zip(a, b))
    if isinstance(a, np.ndarray):
        return (isinstance(b, np.ndarray) and a.shape == b.shape
                and bool(np.array_equal(a, b, equal_nan=a.dtype.kind == "f")))
    if isinstance(a, (pd.DataFrame, pd.Series)):
        return type(a) is type(b) and a.equals(b)
    if isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b):
        return True
    try:
        return bool(a == b)
    except Exception:                                                   # noqa: BLE001
        return False


def _required(inp):
    """The headline design's stacked rows, its distinct required unit-years, and the required unit-year with the most
    stacked rows (a comparison utility can sit in several blocks), with that count."""
    rows = oa.stacked_rows(inp.build(ro.H2))
    per = rows.groupby(["utility_id_eia", "state", "year"]).size()
    (u, st, yr), m = per.idxmax(), int(per.max())
    return rows, len(per), (int(u), str(st), int(yr)), m


def _at(frame, key):
    u, st, yr = key
    return (frame.utility_id_eia == u) & (frame.state == st) & (frame.year == yr)


@pytest.mark.parametrize("name", list(SUPPLEMENTARY_IDS))
def test_each_supplementary_entry_is_the_kernel_on_the_natural_log_of_the_levels(world, name):
    """Positive invented levels exp(y) x 50 through run(): the result is exactly (to the bit) estimate_design on their
    natural log taken in the test, the planted 0.05 comes back (tolerance 1e-3), the record carries computable True, the
    outcome's specification and the kernel's NOT_VALIDATED label."""
    inp, w = world
    y = outcome(w["dd"])
    lv = levels(y)
    eid = SUPPLEMENTARY_IDS[name]
    res = one(ro.run(eid, inp, {name: lv}))
    expect = ro.estimate_design(inp.build(ro.H2), lv.assign(value=np.log(lv.value.to_numpy(dtype=float))),
                                validated=False)
    assert res["headline"]["log_points"] == expect["headline"]["log_points"]
    assert res["headline"]["range_90_log_points"] == expect["headline"]["range_90_log_points"]
    assert _same({k: res[k] for k in expect}, expect)
    assert abs(head(res) - 0.05) < TOL
    assert res["computable"] is True and res["estimated"] is True
    assert res["specification"] == so.SPECS[name].as_dict() and res["specification"]["transformation"] == "natural log"
    assert res["supplementary"]["constant_added"] == "none"
    assert res["validation"] == ro.NOT_VALIDATED and res["label"] == so.SUPPLEMENTARY_LABEL
    assert_labelled_not_validated(eid, res)


BAD = {"zero": (so.NONPOSITIVE, 0.0), "negative": (so.NONPOSITIVE, -7.654321), "absent_row": (so.MISSING, None),
       "nan": (so.MISSING, float("nan")), "plus_infinity": (so.NONFINITE, float("inf")),
       "minus_infinity": (so.NONFINITE, float("-inf"))}


@pytest.mark.parametrize("case", list(BAD))
def test_a_bad_level_on_a_required_row_makes_the_result_non_computable_in_words(world, case):
    """One required unit-year (the one with the most stacked rows) made zero, negative, absent, NaN or infinite: through
    run() the result has estimated False and computable False, the reason with 1 unit-year and that unit-year's count of
    stacked rows, and a failure_in_words that names the counts and the unit-year by key and shows no value."""
    inp, w = world
    reason, bad = BAD[case]
    rows, n_uy, key, m = _required(inp)
    lv = levels(outcome(w["dd"]))
    if bad is None:
        lv = lv[~_at(lv, key)]
    else:
        lv = lv.copy()
        lv.loc[_at(lv, key), "value"] = bad
    for name, eid in SUPPLEMENTARY_IDS.items():
        r = ro.run(eid, inp, {name: lv})
        res = one(r)
        assert r["estimated"] is False and res["estimated"] is False and res["computable"] is False, (case, name)
        nc = res["non_computable"]
        assert nc["reasons"][reason]["unit_years"] == 1 and nc["reasons"][reason]["stacked_rows"] == m
        assert all(c["unit_years"] == 0 for k, c in nc["reasons"].items() if k != reason)
        assert (nc["affected_unit_years"], nc["affected_stacked_rows"]) == (1, m)
        assert (nc["required_unit_years"], nc["required_stacked_rows"]) == (n_uy, len(rows))
        words = res["failure_in_words"]
        assert f"1 of its {n_uy} required unit-years ({m} of {len(rows)} stacked rows)" in words
        assert f"{reason}: {key[0]}:{key[1]} in {key[2]}" in words and f"1 {reason} ({m} stacked rows)" in words
        assert r["failures_in_words"] == {ro.set_label(ro.H2): words}
        shown = [repr(bad), f"{bad:g}" if bad is not None else "None", "nan", "inf"]
        shown += [f"{v:g}" for v in lv.value.iloc[:30]] + [repr(float(v)) for v in lv.value.iloc[:30]]
        assert not any(s in words for s in shown if s not in ("0", "None")), (case, [s for s in shown if s in words])
        assert "headline" not in res and res["validation"] == ro.NOT_VALIDATED and res["specification"]["name"] == name


def test_a_bad_level_on_a_unit_year_the_design_does_not_use_changes_nothing(world):
    """The late host (98:AB) is in no block of the headline design: its levels made negative, NaN and absent leave every
    supplementary result exactly as it is on the clean frame."""
    inp, w = world
    rows, *_ = _required(inp)
    assert not ((rows.utility_id_eia == 98) & (rows.state == "AB")).any()
    lv = levels(outcome(w["dd"]))
    bad = lv.copy()
    bad.loc[_at(bad, (98, "AB", 2010)), "value"] = -1.0
    bad.loc[_at(bad, (98, "AB", 2011)), "value"] = float("nan")
    bad = bad[~_at(bad, (98, "AB", 2012))]
    for name, eid in SUPPLEMENTARY_IDS.items():
        clean, dirty = ro.run(eid, inp, {name: lv}), ro.run(eid, inp, {name: bad})
        assert one(dirty)["computable"] is True and _same(dirty, clean), name


def test_one_supplementary_outcomes_failure_leaves_the_others_and_the_headline_exactly_as_they_are(world):
    """kWh per customer non-computable (a NaN on a required row) beside clean bill, customers and price: the other two
    supplementary results and main_headline_set's are equal, in full, to their results with no failure anywhere."""
    inp, w = world
    y = outcome(w["dd"])
    _, _, key, _ = _required(inp)
    broken = levels(y)
    broken.loc[_at(broken, key), "value"] = float("nan")
    clean = {ro.PRICE: y, ro.KWH: levels(y), ro.BILL: levels(y), ro.CUSTOMERS: levels(y)}
    dirty = {**clean, ro.KWH: broken}
    assert one(ro.run(SUPPLEMENTARY_IDS[ro.KWH], inp, dirty))["computable"] is False
    for eid in (SUPPLEMENTARY_IDS[ro.BILL], SUPPLEMENTARY_IDS[ro.CUSTOMERS], "main_headline_set"):
        a, b = ro.run(eid, inp, dirty), ro.run(eid, inp, clean)
        assert a["estimated"] and _same(a, b), eid
        assert head(one(a)) == head(one(b)) and one(a)["headline"]["range_90_log_points"] == one(b)["headline"]["range_90_log_points"]


def test_no_constant_is_added_before_the_log(world):
    """A level of 1.0 on every row: every logged value is exactly 0.0 (log1p would give 0.693...), and through the entry
    the estimate is 0 (tolerance 1e-10). Levels exp(y) (near 1, where log and log1p part most) return the planted 0.05
    (tolerance 1e-3), which log1p would halve."""
    inp, w = world
    y = outcome(w["dd"])
    ones = y.assign(value=1.0)
    logged, rec = so.log_frame_for_design(inp.build(ro.H2), ones, ro.KWH)
    assert (logged.value.to_numpy() == 0.0).all() and rec["constant_added"] == "none"
    res = one(ro.run(SUPPLEMENTARY_IDS[ro.KWH], inp, {ro.KWH: ones}))
    assert res["computable"] is True and abs(head(res)) < 1e-10
    res = one(ro.run(SUPPLEMENTARY_IDS[ro.BILL], inp, {ro.BILL: levels(y, scale=1.0)}))
    assert abs(head(res) - 0.05) < TOL


def test_the_supplementary_entries_carry_the_settled_specification_and_no_reading():
    """READING and the old sentence that scale and transformation are unstated are gone from the three entries and from
    the runner; each entry's labels carry NEXT_TO_PRICE, the supplementary label, the validation limit and NOT_VALIDATED;
    its estimator says the log is taken by supplementary_outcomes on the levels the caller supplies; OUTCOME_IN_WORDS
    gives the level and its unit. READING is still used elsewhere."""
    import inspect
    for name, eid in SUPPLEMENTARY_IDS.items():
        e = ro.REGISTRY_BY_ID[eid]
        text = _entry_text(e).lower()
        assert ro.READING not in e.labels and "agent's reading" not in text, eid
        assert "scale and transformation" not in text and "not stated in the plan" not in text, eid
        assert e.labels == (ro.NEXT_TO_PRICE, so.SUPPLEMENTARY_LABEL, so.VALIDATION_LIMIT, ro.NOT_VALIDATED), eid
        assert "supplementary_outcomes.run_on_design" in e.estimator and "levels the caller supplies" in e.estimator
        assert so.SPECS[name].unit in e.estimator and so.NON_COMPUTABLE_RULE in e.estimator
        assert ro.OUTCOME_IN_WORDS[name].startswith("the level of " + so.SPECS[name].unit), name
        assert not e.needs and e.status == ro.BUILT and e.outcome == name, eid
    src = inspect.getsource(ro._other_outcome)
    assert "READING" not in src and "not stated in the plan" not in src and "so.run_on_design" in src
    assert (ro.KWH, ro.BILL, ro.CUSTOMERS) == so.NAMES
    assert any(ro.READING in lab for e in ro.REGISTRY for lab in e.labels)


def test_needs_u_and_needs_c_carry_the_settled_ownership_and_row_cs_price_series():
    for e_id, call in (("reconciliation_row_U", "reconciliation_mu.adopted_row_u_ownership_classes(q)"),
                       ("reconciliation_row_C", "reconciliation_c.adopted_row_c_ownership(q)")):
        t = ro.REGISTRY_BY_ID[e_id].needs
        low = t.lower()
        assert "pick is open" not in low and "ownership classes (scheme u" not in low, e_id
        assert "the fiber shares (december filings) and the ownership classes" not in low, e_id
        assert call in t and "2001 to 2025" in t and "time-invariant" in t and "D-117" in t, e_id
        assert rmu.OWNERSHIP_MISSING_TREATMENT in t and "reconciliation_mu.PANEL_ENTITY_TYPE_STATEMENT" in t, e_id
        # D-119 (Joe, 2026-11-20): the type is described as the panel's modal type, kept with no further raw read
        assert rmu.OWNERSHIP_PICK_D117 in t and ro.OWNERSHIP_PANEL_TEXT in t, e_id
        assert "utility-level modal reported type carried across the panel" in t and "D-119" in t, e_id
        assert "no claim is made that it equals EIA's year-by-year record" in t, e_id
        assert "the reading over the years searched changes no class" in t, e_id
    c = ro.REGISTRY_BY_ID["reconciliation_row_C"].needs
    assert "res_price" in c and "our comparison specification" in c.lower()
    assert "not a claim that the paper used exactly this construction" in c
    assert rc.PRICE_SERIES_LABEL in c and rc.PRICE_SERIES_NOT_CHECKED in c and "Still the caller's" not in c
    assert ("The fiber shares are an input the caller supplies, their content settled as the shares from the December "
            "Form 477 filings (ours, adopted by Joe on 2026-11-19, D-107)") in c
    assert "is the paper's series" not in c.replace("does not establish that it is the paper's series", "")
    assert rc.OURS_PRICE_SERIES in ro.OUTCOME_IN_WORDS[ro.PRICE_CENTS_REAL_2024]
    assert "our comparison specification" in ro.OUTCOME_IN_WORDS[ro.PRICE_CENTS_REAL_2024]
    for doc in (ro.RowUInputs.__doc__, ro.RowCInputs.__doc__):
        assert "2001 to 2025" in doc and "D-117" in doc and "pick is open" not in doc
    assert "adopted_row_u_ownership_classes" in ro.RowUInputs.__doc__
    assert "adopted_row_c_ownership" in ro.RowCInputs.__doc__ and "PRICE_SERIES_NOT_CHECKED" in ro.RowCInputs.__doc__
    assert rc.SPECIFICATION.price_series == rc.OURS_PRICE_SERIES == "res_price"


def test_row_c_with_another_price_series_is_recorded_as_not_computed_in_words(world):
    from dataclasses import replace
    inp, _ = world
    y = {ro.PRICE_CENTS_REAL_2024: row_c_outcome()}
    off = ro.RowCInputs(**{**inp.reconciliation_c.__dict__,
                           "choices": replace(rc.SPECIFICATION, price_series=ro.PRICE_DEFAULT_SERVICE)})
    r = ro.run("reconciliation_row_C", ro.RunInputs(**{**inp.__dict__, "reconciliation_c": off}), y)
    assert r["estimated"] is False and "failure_in_words" in one(r, ro.PAPER_SAMPLE)
    msg = one(r, ro.PAPER_SAMPLE)["failure_in_words"]
    assert msg.startswith("ValueError: Row C refuses to depart from its specification")
    assert f"price_series is {ro.PRICE_DEFAULT_SERVICE!r}" in msg and rc.PRICE_SERIES_NOT_CHECKED in msg


def test_e7_builder_names_the_reference_design_denominator_and_the_stored_figures():
    rec = json.loads((ROOT / "data/frozen/e7_reporting_denominator.json").read_text())["result"]
    n_ref, n_roster = rec["hosts_in_reference_design"], rec["hosts_in_roster"]
    assert (n_ref, n_roster) == (36, 41)
    for eid in ("E7_earlier", "E7_later"):
        b = ro.REGISTRY_BY_ID[eid].builder
        for phrase in (f"the {n_ref} hosts of the set's reference design", f"the roster of {n_roster} reported beside it",
                       "D-117", "presentation only", "nothing redrawn", "e7_presentation.denominators",
                       "data/frozen/e7_reporting_denominator.json", "every cohort utility the primary reporting denominator"):
            assert phrase in b, (eid, phrase)


def test_the_registry_counts_and_what_a_stated_need_is():
    c = {s: sum(1 for e in ro.REGISTRY if e.status == s) for s in ro.STATUSES}
    assert len(ro.REGISTRY) == 58
    assert (c[ro.BUILT], c[ro.BLOCKED], c[ro.NOT_BUILT], c[ro.OUT_OF_SCOPE], c[ro.DESIGN_ONLY], c[ro.NEEDS_PACKAGE]) == \
        (54, 0, 3, 1, 0, 0)
    assert [e.id for e in ro.REGISTRY if e.stopped_on_research_inputs] == []
    with_needs = [e.id for e in ro.REGISTRY if e.status == ro.BUILT and e.needs]
    assert with_needs == ["reconciliation_row_U", "reconciliation_row_C", "inventory_against_sales",
                          "timing_run_no_anchoring_years", "second_number_settled_only_classes_2_to_4",
                          "second_number_ten_highest_leverage_left_out",
                          "second_number_sensitivity_scenario_a_runner_up_placement",
                          "second_number_sensitivity_scenario_b_other_end_of_every_dated_interval",
                          "callaway_santanna", "estimators_agree"]
    doc = ro.registry_document()
    assert doc["built_entries_with_needs"] == 10 and doc["built_entries_with_needs_ids"] == with_needs
    t = doc["built_is_not_ready"]
    assert "open elements of the specification that the plan does not settle" not in t and "nothing more" in t
    choice = [e.id for e in ro.REGISTRY if e.status == ro.BUILT and "is the caller's choice" in e.needs]
    assert choice == [] and "One element is still named" not in t     # D-119 settled the last one
    assert "No needs text of a built entry names an element as the caller's choice" in t and "D-119" in t
    assert all(" is open" not in e.needs and "open element" not in e.needs for e in ro.REGISTRY if e.status == ro.BUILT)
    assert "fiber shares" in t and "Joe may strike" in t


def test_the_stored_registry_is_the_registry_document():
    """data/frozen/outcome_run_registry.json, as run_outcomes.main writes it, equals registry_document() field by field."""
    stored = json.loads((ROOT / "data/frozen/outcome_run_registry.json").read_text())
    assert stored == json.loads(json.dumps(ro.registry_document()))


# ---- Joe's rulings of 2026-11-20 (D-119): rows U and C's ownership type described, the inventory's history settled --
def _registry_d119_problems(needs_u: str, needs_c: str, needs_ias: str, built_is_not_ready: str, docs: dict) -> list:
    bad = []
    for name, t in {"needs_u": needs_u, "needs_c": needs_c, **docs}.items():
        flat = " ".join(t.split())
        rest = flat.replace(rmu.OWNERSHIP_RULING_D119_WORDS, "").replace(
            "not the latest year-by-year EIA classification", "").lower()
        for phrase in ("latest", "most recent", "last nonmissing reported", "pick is open", "is the caller's choice",
                       "still the caller's"):
            if phrase in rest:
                bad.append((name, phrase))
        if "utility-level modal reported type carried across the panel" not in flat or "D-119" not in flat:
            bad.append((name, "no modal description or no D-119"))
    low = needs_ias.lower()
    if "caller's choice" in low or ias.INVENTORY_HISTORY_D119_WORDS not in needs_ias or \
            "inventory as built" not in needs_ias or "RunInputs.side.dose" not in needs_ias or \
            "cannot detect a frame built from another history" not in needs_ias:
        bad.append(("needs_ias", "history not settled in its text"))
    if "is still named" in built_is_not_ready or "D-119" not in built_is_not_ready:
        bad.append(("built_is_not_ready", "still names a caller's choice"))
    return bad


def _registry_d119_inputs() -> tuple:
    by = ro.REGISTRY_BY_ID
    docs = {"row_u_inputs": ro.RowUInputs.__doc__, "row_c_inputs": ro.RowCInputs.__doc__,
            "module": ro.__doc__.split("Session 26 (")[1].split("Readings that are the agent's")[0]}
    return (by["reconciliation_row_U"].needs, by["reconciliation_row_C"].needs, by["inventory_against_sales"].needs,
            ro.BUILT_IS_NOT_READY, docs)


def test_d119_registry_texts_carry_both_rulings():
    assert _registry_d119_problems(*_registry_d119_inputs()) == []
    assert ro.NEEDS_IAS == ro.REGISTRY_BY_ID["inventory_against_sales"].needs
    assert all("is the caller's choice" not in e.needs and "still the caller's" not in e.needs.lower()
               for e in ro.REGISTRY if e.status == ro.BUILT)
    assert ro.registry_document()["built_is_not_ready"] == ro.BUILT_IS_NOT_READY
    # the runner gives the check the frame the registry names: RunInputs.side.dose
    import inspect
    assert "ias.check(ias.hosts_from_design(d), inputs.side.q, inputs.side.dose" in inspect.getsource(
        ro._inventory_against_sales)


def test_d119_registry_text_checks_can_fail():
    """Break: each text put back to its D-117 wording in the test process; the check names each one."""
    u, c, i, b, docs = _registry_d119_inputs()
    old_u = u.replace(rmu.OWNERSHIP_PICK_D117, "last nonmissing reported entity type").replace(
        ro.OWNERSHIP_PANEL_TEXT, "The panel's entity_type is one type per utility id.")
    old_i = ("RunInputs.inventory_inputs_are. side.dose needs dc_gwh; which history of the inventory is supplied is the "
             "caller's choice.")
    old_b = "One element is still named in a needs text as the caller's choice and is not settled there."
    bad = _registry_d119_problems(old_u, c, old_i, old_b, docs)
    assert ("needs_u", "last nonmissing reported") in bad and ("needs_u", "no modal description or no D-119") in bad
    assert ("needs_ias", "history not settled in its text") in bad
    assert ("built_is_not_ready", "still names a caller's choice") in bad
    assert _registry_d119_problems(u, c + " Still the caller's: the fiber shares.", i, b, docs) == [
        ("needs_c", "still the caller's")]
