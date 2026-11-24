#!/usr/bin/env python3
"""The input assembler: run_outcomes.RunInputs filled from the permitted quantity-side records, with a record of where each
field came from. Reads NO outcome, price, revenue or bill, and runs no registry entry.

The plan is frozen at commit ea426c4 (the approved specification is commit ed3a2ff); it is internally frozen and not
externally preregistered. Joe's authorizing words (2026-11-20, D-120, item 3): "Build the input assembler from permitted
existing quantity-side records, supplying every required registry input, the headline validation reference, the
drift-reading flag, row U's adopted flags and ownership classes, row C's specified inputs, and each design's correct
context."

What is here
------------
Sources             every loader the assembler calls, each a member that defaults to None and is resolved to the real
                    loader (a module function `_real_<name>`, looked up when assemble is called) inside assemble. Tests
                    replace every member with an invented one; nothing is bound at definition or import time.
FILES               the files each real loader opens, traced from the code to its file-system calls (see the report of
                    session 27's assembler agent). None is under data/raw or data/blind; every one is passed through the
                    path guard before its loader is called, and hashed only where HASHABLE allows.
assemble(*, inputs_are, sources=None)
                    the RunInputs, row C's CPI-U factors and the record. `inputs_are` is required and must be
                    run_outcomes.INVENTED_INPUTS or RESEARCH_DATA_AFTER_THE_FREEZE; it stamps
                    reconciliation_u_inputs_are and inventory_inputs_are. side and sets are built first and a failure
                    there stops the assembly (AssemblyStopped); a failure on any other field is recorded in `deferred` in
                    words, the field left None, and the others are still built.
check_path(path)    condition4_peaks.refuse_raw_or_blind: refuses a path under data/raw or data/blind by its text alone.
NEEDS               for each registry entry of the executable order, the RunInputs fields its runner fetches (read from
                    the runners of run_outcomes.py by session 27's assembler agent), required and used if supplied.
stated_needs_check(assembled)
                    for each entry, whether the assembled inputs supply each field (and each set) it fetches.
quantity_side_checks(assembled)
                    counts and keys only, no outcome: the headline design and its check against the validation
                    reference, every other set's design, row U's flags frame and ownership classes and row C's ownership
                    against the panel, the dose stamp, the headline set split again from side.dose, residential customers
                    on the headline design's required unit-years. It does not call inventory_against_sales.check and runs
                    no registry entry.

Readings that are the agent's and not the plan's or the prompt's are marked "the agent's reading" where they are used.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import condition4_peaks as c4  # noqa: E402
from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import run_outcomes as ro  # noqa: E402
from pipeline.analysis import side_runs as sr  # noqa: E402

KEY = ps.KEY
FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
THETA = 0.02
H2 = ro.H2
EVERY = ro.EVERY
EXPECTED_DESIGN_INPUTS_PREFIX = "b8515c35cba1"
SUPPLEMENTARY_SPEC = FROZEN / "supplementary_outcomes_spec.json"
SECOND_NUMBER_DESIGN = FROZEN / "second_number_design.json"
INVENTORY_AS_BUILT_SOURCE = ("the frame design.load() returned, data/interim/utility_year_dose.parquet, the inventory as "
                             "built (the load history underlying the headline design; Joe, 2026-11-20, D-119)")
check_path = c4.refuse_raw_or_blind


class AssemblyStopped(RuntimeError):
    """side or sets could not be built: nothing else is assembled. Raised in words."""


class InputsAreRefused(ValueError):
    """`inputs_are` is not one of run_outcomes.INPUTS_ARE."""


# ======================================================================================================================
# Which files may be hashed, and the files each real loader opens (traced from the code)
# ======================================================================================================================

HASHABLE_INTERIM = frozenset({"panel_quantities.parquet", "panel_reported_ids.parquet", "utility_year_dose.parquet",
                              "facilities.parquet", "facility_year.parquet", "state_anchor.parquet",
                              "state_load_by_year.parquet", "reconciliation_short_form_filers.parquet",
                              "reconciliation_short_form_flags.parquet", "condition4_peak_rows.parquet"})


def hashable(path) -> bool:
    """Whether the assembler may hash `path`: a file under data/frozen (not data/frozen/water), one of the quantity files
    under data/interim the common brief and the assembler's prompt name (HASHABLE_INTERIM), or a file under pipeline/
    (not pipeline/water). The path guard runs first."""
    p = check_path(path)
    try:
        rel = p.relative_to(ROOT).parts
    except ValueError:
        return False
    if len(rel) >= 3 and rel[0] == "data" and rel[1] == "frozen":
        return rel[2] != "water"
    if len(rel) == 3 and rel[0] == "data" and rel[1] == "interim":
        return rel[2] in HASHABLE_INTERIM
    if len(rel) >= 2 and rel[0] == "pipeline":
        return rel[1] != "water"
    return False


_I, _F, _E = "data/interim/", "data/frozen/", "pipeline/electricity/"
_SIDE = (_I + "panel_quantities.parquet", _I + "utility_year_dose.parquet", _E + "market_moves.csv",
         _E + "pjm_late_zones.csv", _F + "fuel_mix_groups.csv", _F + "degree_days.csv")
_SPLIT = (_F + "buildout_sensitivity.json", _F + "dating_sensitivity.json", _F + "treatment_bounds.json",
          "pipeline/analysis/price_hold.csv")
_ASSIGNMENT = (_I + "facilities.parquet", _I + "facility_year.parquet", _I + "panel_quantities.parquet",
               _I + "utility_year_dose.parquet", _E + "market_moves.csv", _E + "pjm_late_zones.csv")
_ENUMERATION = _ASSIGNMENT + (_I + "state_anchor.parquet", "pipeline/facilities/verified/buildout.csv",
                              "pipeline/facilities/verified/buildout_county.csv",
                              "pipeline/facilities/verified/pass_c_corrections_s17.json")
FILES = {
    "design_load": _SIDE,
    "usable": (_I + "panel_quantities.parquet",),
    "rule_inputs": ("pipeline/analysis/ownership.csv", _F + "fuel_mix_groups.csv"),
    "unknown_load": (_F + "unknown_load_sites_and_affected_utilities.json", _F + "treatment_bounds.json",
                     _I + "facilities.parquet"),
    "split": _SPLIT,
    "d34_table": ("pipeline/facilities/verified/utility_history.csv",),
    "price_hold": ("pipeline/analysis/price_hold.csv",),
    "every_cohort_at": (),
    "validation_reference": tuple(_F + f for f in oa.VALIDATION_FILES + (oa.DESIGN_SUPPORT_FILE,)),
    "catches_drift": (_F + "early_years_drift_selected_procedure.json",),
    "suppliers": ("pipeline/analysis/suppliers.csv",),
    "omissions": ("pipeline/analysis/supplier_known_omissions.csv",),
    "e5_anchor": (_F + "inventory_report.json", _I + "state_anchor.parquet"),
    "e6_changers": (),
    "future_hosts": _ENUMERATION + (_F + "timing_place_test.json",) + _SPLIT,
    "inventory": _ENUMERATION + ("pipeline/facilities/verified/date_evidence.csv",),
    "inventory_context": _SIDE + ("pipeline/analysis/ownership.csv",
                                  _F + "unknown_load_sites_and_affected_utilities.json", _I + "facilities.parquet")
                         + _SPLIT[:3],
    "e7_errors": (_F + "dating_report.json",),
    "peaks": (_I + "condition4_peak_rows.parquet", _F + "condition4_peak_read_record.json"),
    "succession": (_E + "succession.csv",),
    "has_predecessors": (),
    "second_number": _ENUMERATION + ("pipeline/analysis/price_hold.csv",
                                     _F + "unknown_load_sites_and_affected_utilities.json"),
    "timing_added": (_F + "treatment_bounds.json", _F + "headline_set.csv"),
    "row_u": (_I + "facilities.parquet", _I + "facility_year.parquet", _I + "reconciliation_polygon_incidence.parquet",
              _I + "panel_reported_ids.parquet", _I + "reconciliation_short_form_filers.parquet",
              _I + "reconciliation_short_form_flags.parquet"),
    "row_c": (_I + "facilities.parquet", _F + "fiber_share_by_unit.csv", _F + "dc_construction_spending.csv",
              _I + "reconciliation_polygon_incidence.parquet", _I + "panel_reported_ids.parquet"),
    "cs_lists": _SPLIT[:3],
}


# ======================================================================================================================
# Sources: every loader, replaceable, resolved when assemble is called
# ======================================================================================================================

@dataclass
class Sources:
    """Every loader the assembler calls. Each member defaults to None and is resolved inside assemble to the module's
    `_real_<name>` (looked up at that moment, so a test that replaces it, or the module function it calls, is seen).
    Signatures:
      design_load()                       -> (q, dose, regions, fuel, dd)            design.load
      usable()                            -> the usable set                          usable_flag.read().usable
      rule_inputs(rules, q, usable)       -> (ownership, usable, gas)                power_simulation.rule_inputs
      unknown_load()                      -> power_simulation.UnknownLoad            power_simulation.load_unknown_load
      split(theta, which, q, dose)        -> (hosts with cohort, comparison units)   design.split
      d34_table()                         -> the D-34 table                          utility_history.load
      price_hold()                        -> set                                     power_simulation.price_hold
      every_cohort_at(theta, q, dose, d34, hold) -> (hosts, comparison units)        run_outcomes.every_cohort_utility_at
      validation_reference()                                                         outcome_analysis.read_validation_reference
      catches_drift()                     -> {set: bool}                             run_outcomes.catches_drift_from_file
      suppliers(), omissions()                                                       suppliers.load, the checked omissions
      e5_anchor()                         -> run_outcomes.E5Inputs
      e6_changers(side, sets)             -> set                                     side_runs.region_changers(...)["coded"]
      future_hosts(side)                  -> {"admitted", "histories", "aside", "hold", "late"}
      inventory()                                                                    inventory_runs.load_inventory
      inventory_context(theta, which)                                                inventory_runs.Context.from_files
      e7_errors()                                                                    inventory_runs.load_errors
      peaks()                             -> six-column frame                        condition4_peaks.load_retained
      succession()                                                                   succession.load
      has_predecessors(q)                 -> set of units                            the panel's has_predecessors column
      second_number(side)                 -> RunInputs.second_number
      timing_added()                      -> {(utility, state): year}                timing_run.no_anchoring_years
      row_u(q)                            -> run_outcomes.RowUInputs
      row_c(q, dose)                      -> (run_outcomes.RowCInputs, CPI-U factors)
      cs_lists()                          -> (host set-aside, comparison set-aside, D-34 history)"""
    design_load: object = None
    usable: object = None
    rule_inputs: object = None
    unknown_load: object = None
    split: object = None
    d34_table: object = None
    price_hold: object = None
    every_cohort_at: object = None
    validation_reference: object = None
    catches_drift: object = None
    suppliers: object = None
    omissions: object = None
    e5_anchor: object = None
    e6_changers: object = None
    future_hosts: object = None
    inventory: object = None
    inventory_context: object = None
    e7_errors: object = None
    peaks: object = None
    succession: object = None
    has_predecessors: object = None
    second_number: object = None
    timing_added: object = None
    row_u: object = None
    row_c: object = None
    cs_lists: object = None


SOURCE_NAMES = tuple(f.name for f in dataclasses.fields(Sources))


def _real(name: str):
    """The real loader for `name`, looked up in this module's namespace now (not at import)."""
    return globals()["_real_" + name]


# ---- the real loaders (each traced to its file-system calls; FILES lists them) ---------------------------------------

def _real_design_load():
    return dsg.load()


def _real_usable():
    from pipeline.analysis import usable_flag
    return usable_flag.read().usable


def _real_rule_inputs(rules, q, usable):
    return ps.rule_inputs(rules, q, usable=usable)


def _real_unknown_load():
    return ps.load_unknown_load()


def _real_split(theta, which, q, dose):
    return dsg.split(theta, which, q, dose)


def _real_d34_table():
    from pipeline.facilities import utility_history as uh
    return uh.load()


def _real_price_hold():
    return ps.price_hold()


def _real_every_cohort_at(theta, q, dose, d34, hold):
    return ro.every_cohort_utility_at(theta, q, dose, d34_table=d34, hold=hold)


def _real_validation_reference():
    return oa.read_validation_reference()


def _real_catches_drift():
    return ro.catches_drift_from_file()


def _real_suppliers():
    from pipeline.analysis import suppliers
    return suppliers.load()


def _real_omissions():
    from pipeline.analysis import prefreeze_summaries as pf
    return pf.load_known_omissions()                 # the CHECKED loader: the runner passes the list through unchecked


def _real_e5_anchor():
    return ro.E5Inputs(block=sr.read_state_anchor_block(),
                       all_states=pd.read_parquet(check_path(INTERIM / "state_anchor.parquet")))


def _real_e6_changers(side, sets):
    """As side_runs.main builds it: every comparison unit matched to any host of the headline design or of every cohort
    utility's design at 2%, then side_runs.region_changers(regions, those units, q)["coded"]."""
    matched = set()
    for which in (ps.HEADLINE_SET, EVERY):
        t, c = sets[(which, THETA)]
        d = side.build(t, c, THETA)
        matched |= {(int(m[0]), str(m[1])) for mk in d.hosts.match_keys for m in mk}
    return set(sr.region_changers(side.regions, matched, side.q)["coded"])


def _real_future_hosts(side):
    """As future_hosts.main builds them: the late hosts' histories (late_host_histories, whose place tests must each
    reproduce the frozen timing_place_test.json, else it stops), and, for each, the cohorts its histories admit where
    no other comparison rule fails; E2's set-aside list and price hold are power_simulation.set_aside(0.02) and
    price_hold(); every late host is kept out of E2's pool."""
    from pipeline.analysis import future_hosts as fh
    units, check = fh.late_host_histories(fh.THETA)
    if not check["all_reproduce"]:
        raise ValueError("a late host's place test does not reproduce data/frozen/timing_place_test.json; the future-host "
                         "lists are not built (future_hosts.main stops on the same check)")
    aside, hold = ps.set_aside(fh.THETA), ps.price_hold()
    admitted: dict = {}
    for k, r in sorted(units.items()):
        fails = fh.other_rule_failures(k, side.dose, aside, hold)
        cohorts = fh.admitted_cohorts(fh._all_histories(r), fh.THETA) if r["complete"] else []
        for g in cohorts:
            if not fails:
                admitted.setdefault(g, []).append(k)
    return {"admitted": admitted, "histories": units, "aside": set(aside), "hold": set(hold), "late": set(units)}


def _real_inventory():
    from pipeline.analysis import inventory_runs as ir
    return ir.load_inventory()


def _real_inventory_context(theta, which):
    from pipeline.analysis import inventory_runs as ir
    return ir.Context.from_files(theta, which=which)


def _real_e7_errors():
    from pipeline.analysis import inventory_runs as ir
    return ir.load_errors()


def _real_peaks():
    return c4.load_retained()


def _real_succession():
    from pipeline.electricity import succession as succ
    return succ.load()


def _real_has_predecessors(q):
    """As conditions.main builds it: every panel unit with a row whose has_predecessors flag is true."""
    if "has_predecessors" not in q.columns:
        raise ValueError("the quantities have no has_predecessors column; the set of units with summed predecessors "
                         "cannot be built")
    return {(int(u), str(s)) for u, s in q.loc[q.has_predecessors.astype(bool), KEY].drop_duplicates()
            .itertuples(index=False)}


def _real_second_number(side):
    """RunInputs.second_number, from second_number's own machinery as second_number.design_summary and
    second_number_scenarios.main build it, without running either module's main (each writes a file) and writing
    nothing.

    The primary sample's units: every panel unit less the price hold and the load-unknown units
    (second_number._sample_candidates), less the units with load in some history and no positive 2009-2011 sales
    (case_points' list), which design_summary takes out of its frame. assigned, changes and reach at each form, from rule
    8.1's six histories (assignment.evaluate, case_points, history_changes, reach_from_endpoints), for those units.
    established: second_number.common_dose_finding()[0], that is common_dose_rule.established_as_ruled on both scopes'
    verdicts (D-107). The agent's reading: the two units a load-unknown site reaches are NOT in `units`, so no_assigned
    is empty. RunInputs takes one `units` list for the run as assigned and the runs on single doses; design_summary
    keeps them out of the run as assigned ("no assigned dose") and in the frame of the classification, where under the
    ruled mapping neither has a single dose at any form. Leaving them out of `units` keeps the run as assigned as the
    plan states it and leaves them unnamed (rather than named as class 1) in the runs on single doses. The session
    adopted this as its disclosed reading. The stored design summary classes both as having no single dose at every
    form (data/frozen/second_number_design.json, field utilities_with_no_assigned_dose, each unit's by_form classes
    "no_single_dose"); quantity_side_checks reads that field each time and reports any unit it lists with another class
    at some form, so the premise is checked and not assumed.

    The two sensitivity scenarios: second_number_scenarios.real_inputs, the per-state reconstruction check
    (realise_history with no settings, reconstruction_check; computed in memory, no document written), each scenario's
    settings (placement_inputs, runner_up_placement, scenario_a_settings; scenario_b_settings), realise_history in the
    states that pass, then points_of. scenario_units: every panel unit less the price hold, the load-unknown units
    included, in the states that pass, as second_number_scenarios.main takes them. The bootstrap seed is not given, so
    second_number.BOOTSTRAP_SEED applies; boot is second_number.BOOT."""
    from pipeline.analysis import second_number as sn
    from pipeline.analysis import second_number_scenarios as ss
    from pipeline.facilities import assignment as asg
    q, regions, usable = side.q, side.regions, side.usable
    affected = set(side.unknown_load.affected)
    hold = ps.price_hold()
    fac, fy, _q, units, base, regions_fixed = asg.load_inputs()
    _t, m, _res = asg.evaluate(fac, fy, units, base, regions_fixed)
    pts, no_base = sn.case_points(m, base)
    no_base_ids = {sn._uid(k) for k in no_base}
    cands, _named = sn._sample_candidates(q, hold, affected)
    primary_units = [k for k in cands if sn._uid(k) not in no_base_ids]
    codes = sn.region_codes(regions)
    frame = sn.build_frame(primary_units, q, regions, usable, codes=codes)
    keys = list(frame.keys)
    idx = pd.MultiIndex.from_tuples(keys, names=KEY)
    labs = [sn.cap_label(c) for c in sn.CAPS]
    ch = {sn.cap_label(c): sn.history_changes({h: p.reindex(idx) for h, p in pts.items()}, cap=c) for c in sn.CAPS}
    endpoint_years = list(sn.PRE) + list(sn.POST)
    reach = {sn._uid(k): sn.reach_from_endpoints(np.vstack([pts[h].loc[k, endpoint_years].values for h in sn.HISTORIES]))
             for k in keys}
    assigned = {lab: {sn._uid(k): float(ch[lab].loc[k, sn.ASSIGNED]) for k in keys} for lab in labs}
    changes = {lab: {sn._uid(k): ch[lab].loc[k].values for k in keys} for lab in labs}
    established = sn.common_dose_finding()[0]

    inp, entries, dose_file, aff_list, _fids = ss.real_inputs()
    rec0 = ss.realise_history(inp, entries, {})
    check = ss.reconstruction_check(rec0["gwh"], inp.base, dose_file, aff_list, rec0["factor"], rec0["frozen_factor"])
    failed = sorted(st for st, r in check.items() if not r["passes"])
    state_of = inp.fac.state
    sites, carried, capacity = ss.placement_inputs(inp)
    placement = ss.runner_up_placement(sites, carried, capacity, set(inp.units))
    set_a = ss.scenario_a_settings(placement, state_of)
    set_b, _b_rec = ss.scenario_b_settings(entries, state_of)
    ok_states = [st for st in sorted({s for _, s in inp.units}) if st not in failed]
    hist = {ss.SCENARIO_A: ss.realise_history(inp, entries, {k: v for k, v in set_a.items() if k in ok_states}, ok_states),
            ss.SCENARIO_B: ss.realise_history(inp, entries, {k: v for k, v in set_b.items() if k in ok_states}, ok_states)}
    points, no_dose = {}, {}
    for name in ss.SCENARIOS:
        points[name], no_dose[name] = ss.points_of(hist[name]["gwh"], inp.base)
    scenario_units = [k for k in cands + sorted(affected) if k[1] in ok_states]
    return {"units": primary_units, "boot": sn.BOOT, "assigned": assigned, "changes": changes, "reach": reach,
            "no_assigned": [], "established": established, "scenario_units": scenario_units,
            "scenario_points": points, "scenario_no_dose": no_dose,
            "_assembly_counts": {"units_with_load_and_no_positive_base_left_out": len(no_base_ids),
                                 "load_unknown_units_left_out_of_units": len(affected),
                                 "primary_frame_units": len(keys),
                                 "reconstruction_check_states": len(check),
                                 "reconstruction_check_states_failing": failed}}


def _real_timing_added():
    from pipeline.analysis import timing_run as tr
    rec = json.loads(check_path(tr.TREATMENT_BOUNDS).read_text())
    for p in tr.RECORD_PATH:
        rec = rec[p]
    return dict(tr.no_anchoring_years(rec, pd.read_csv(check_path(tr.HEADLINE_CSV)))["years"])


def _real_row_u(q):
    """Row U's bundle as reconciliation_mu.main builds its parts. Treatments for U0 to U3: cumulative_mw on the
    inventory's site-year load over each step's window (U0 on assign_polygon_smallest under ROW_U_POLYGON over the
    polygon incidence table and the panel's reported ids; U1 to U3 on the inventory's own assignment). Ownership:
    adopted_row_u_ownership_classes on the quantities (utility_id_eia, state, year, entity_type), which refuses years
    other than exactly 2001 to 2025. Flags: short_form_filers.adopted_row_u_flags(frame, filer table, 2019 flags,
    step_window=(2015, 2025)), the frame being the quantity-side unit-years of 2015 to 2025 in the 50 states and DC with
    an ownership class, before the three-year count (as reconciliation_mu._short_form_for_row_u builds it for step U3),
    the filer table's state read as pandas string as main reads it; both records from data/interim, never from data/raw.
    u1_indistinguishable: None (nothing in the row's main or the registry's text settles a value; u1_sentence records it
    and decides nothing)."""
    from pipeline.analysis import reconciliation_mu as rmu
    from pipeline.analysis import reconciliation_treatment as rt
    from pipeline.analysis import short_form_filers as sff
    fac = pd.read_parquet(check_path(INTERIM / "facilities.parquet"))
    fy = pd.read_parquet(check_path(INTERIM / "facility_year.parquet"))
    units = q[KEY].drop_duplicates()
    ver = rt.assign_verified(fac)
    u0 = rt.assign_polygon_smallest(fac, pd.read_parquet(check_path(INTERIM / "reconciliation_polygon_incidence.parquet")),
                                    pd.read_parquet(check_path(INTERIM / "panel_reported_ids.parquet")),
                                    **rmu.RYU_OURS_POLYGON)
    treatments = {}
    for step, st in rmu.U_STEPS.items():
        lo, hi = st["window"]
        treatments[step] = rt.cumulative_mw(u0 if step == "U0" else ver, units, range(lo, hi + 1),
                                            rmu.RYU_OURS_MW_SOURCE, site_year=fy, sites=fac)
    own = rmu.adopted_row_u_ownership_classes(q[KEY + ["year", "entity_type"]])
    own_u = own.set_index(KEY).ownership_class
    lo3, hi3 = rmu.U_STEPS["U3"]["window"]
    w3 = q[(q.year >= lo3) & (q.year <= hi3) & q.state.isin(rmu.RYU_OURS_JURISDICTIONS)][KEY + ["year"]].drop_duplicates()
    w3 = w3[[own_u.get(k) is not None for k in zip(w3.utility_id_eia, w3.state)]]
    flags_2019 = pd.read_parquet(check_path(rmu.SHORT_FORM_FLAGS))
    table = pd.read_parquet(check_path(rmu.SHORT_FORM_FILER_TABLE))
    table["state"] = table.state.astype("string")
    flags = sff.adopted_row_u_flags(w3, table, flags_2019, step_window=(lo3, hi3))
    return ro.RowUInputs(spec=rmu.ryu_spec(rmu.U_SHORT_FORM_ADOPTED_CODE), treatments=treatments, ownership=own,
                         sample_flags=flags, u1_indistinguishable=None)


def _real_row_c(q, dose):
    """Row C's bundle as reconciliation_c.main builds its parts: the verified counts (operating_counts on the inventory's
    own assignment), the polygon counts (operating_counts on assign_polygon_smallest under ROW_C_POLYGON), the dose
    (load_share on utility_year_dose's dose), the December fiber shares (share_map on fiber_share_by_unit.csv), both
    spending series, adopted_row_c_ownership, OURS_C4_CAP, SPECIFICATION and C5's hosts from the row's own
    recomputation (never_host_units(None, None, verified counts, OURS_NEVER_HOST_BASIS)). Returns (RowCInputs, the CPI-U
    factors from cpi_factors_to_2024 on the frozen spending table)."""
    from pipeline.analysis import reconciliation_c as rc
    from pipeline.analysis import reconciliation_treatment as rt
    sites = pd.read_parquet(check_path(INTERIM / "facilities.parquet"),
                            columns=["fid", "state", "energized_year", "mw_full", "is_crypto", "utility_id_eia",
                                     "utility_assign", "lat", "lon"])
    verified = sites[["fid", "utility_id_eia", "state"]]
    qq = q[["utility_id_eia", "state", "year", "entity_type", "ownership"]].copy()
    qq["utility_id_eia"] = qq.utility_id_eia.astype(int)
    own_c = rc.adopted_row_c_ownership(qq)
    fiber = pd.read_csv(check_path(FROZEN / "fiber_share_by_unit.csv"))
    spend = pd.read_csv(check_path(FROZEN / "dc_construction_spending.csv"))
    counts_v, _ = rc.operating_counts(sites, verified)
    poly = rt.assign_polygon_smallest(sites, pd.read_parquet(check_path(INTERIM / "reconciliation_polygon_incidence.parquet")),
                                      pd.read_parquet(check_path(INTERIM / "panel_reported_ids.parquet")), **rt.ROW_C_POLYGON)
    counts_p, _ = rc.operating_counts(sites[["fid", "energized_year", "is_crypto"]], poly.table)
    bundle = ro.RowCInputs(choices=rc.SPECIFICATION, counts_polygon=counts_p, counts_verified=counts_v,
                           dose_verified=rc.load_share(dose[KEY + ["year", "dose"]]), share=rc.share_map(fiber),
                           spending_tables={n: rc.spending_series(spend, n) for n in rc.OURS_C5_SPENDING},
                           ownership=own_c, c4_cap=rc.OURS_C4_CAP,
                           hosts_for_c5=rc.never_host_units(None, None, counts_v, rc.OURS_NEVER_HOST_BASIS),
                           c5_counts_name=rc.OURS_C5_HOSTS_FROM)
    return bundle, rc.cpi_factors_to_2024(spend)


def _real_cs_lists():
    """design.split's set-aside lists for the headline set at 2% (callaway_santanna.aside_sets) and the D-34 history at
    2% (power_simulation.history_settled), as callaway_santanna.main passes them."""
    from pipeline.analysis import callaway_santanna as csa
    host_aside, comp_aside = csa.aside_sets(THETA, ps.HEADLINE_SET)
    return set(host_aside), set(comp_aside), ps.history_settled(THETA)


# ======================================================================================================================
# The assembly
# ======================================================================================================================

@dataclass
class Assembled:
    """inputs: the RunInputs. cpi_factors: row C's CPI-U factors (the reshaper takes them). record: for every RunInputs
    field whether it was supplied, the function that built it, the files it read with their sha256 where they may be
    hashed, counts only, and the seconds it took. deferred: every input that could not be supplied, with the reason in
    words. inputs_are: the caller's statement of what the inputs are."""
    inputs: ro.RunInputs
    cpi_factors: dict | None
    record: dict
    deferred: list
    inputs_are: str
    sources_replaced: list = field(default_factory=list)


def _name_of(fn) -> str:
    return f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', repr(fn))}"


def _words(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _sha(path: Path, cache: dict) -> str:
    if path not in cache:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        cache[path] = h.hexdigest()
    return cache[path]


def _set_counts(sets: dict) -> dict:
    return {ro.set_label(s): {"hosts": int(len(t)), "comparison_eligible_units": int(len(c))} for s, (t, c) in sets.items()}


def _len(x):
    try:
        return int(len(x))
    except TypeError:
        return None


def required_set_keys() -> list:
    """The (set, threshold) keys the registry's executable entries ask RunInputs.sets for: every key of an entry's sets
    whose name is one of design.SETS (E2's own sample, the second number's sample, the papers' samples and the
    side-by-side key are not keys of RunInputs.sets; E2's runner takes the headline set's comparison units)."""
    keys = []
    for e in ro.ORDER_OF_UNBLINDING:
        for s in e.sets:
            if s[0] in dsg.SETS and s[1] is not None and s not in keys:
                keys.append(s)
    for _eid, s in ro.SIDE_BY_SIDE_RUNS:
        if s not in keys:
            keys.append(s)
    return sorted(keys, key=lambda s: (s[1], dsg.SETS.index(s[0])))


def assemble(*, inputs_are: str, sources: Sources | None = None) -> Assembled:
    """RunInputs from the permitted quantity-side records, and the record of where each field came from.

    inputs_are: required, run_outcomes.INVENTED_INPUTS (tests) or RESEARCH_DATA_AFTER_THE_FREEZE; anything else is refused
    in words. It stamps reconciliation_u_inputs_are and inventory_inputs_are. sources: a Sources whose members replace
    the real loaders; a member left None is resolved to the real loader here, when called.

    side and sets are built first: side as side_runs.main builds side_runs.Inputs under the headline rules; the sets at
    2% and 5% by design.split and the 1% set by run_outcomes.every_cohort_utility_at with the D-34 table and the price
    hold passed explicitly, for exactly the keys the registry asks for. inventory_as_built is stamped from the very dose
    frame passed to design.split and stored as side.dose. A failure in this stage stops the assembly (AssemblyStopped).
    Every other field is built in its own try: a failure is recorded in `deferred` in words and the field left None.
    No outcome is read and no registry entry is run."""
    if inputs_are not in ro.INPUTS_ARE:
        raise InputsAreRefused(f"inputs_are must be one of {list(ro.INPUTS_ARE)}, in those words; got {inputs_are!r}. "
                               "Nothing was assembled")
    research = inputs_are == ro.RESEARCH_DATA_AFTER_THE_FREEZE
    sources = Sources() if sources is None else sources
    S, replaced = {}, []
    for n in SOURCE_NAMES:
        given = getattr(sources, n)
        S[n] = _real(n) if given is None else given
        if given is not None:
            replaced.append(n)
    rec: dict = {}
    deferred: list = []
    used: dict = {}                                  # field -> [source names it used]
    seconds: dict = {}

    def call(name, *a):
        t0 = time.time()
        if name not in replaced:
            for f in FILES.get(name, ()):
                check_path(ROOT / f)
        try:
            return S[name](*a)
        finally:
            seconds[name] = round(seconds.get(name, 0.0) + time.time() - t0, 2)

    # ---- the required stage: side and sets -----------------------------------------------------------------------
    try:
        q, dose, regions, fuel, dd = call("design_load")
        usable0 = call("usable")
        ownership, usable, gas = call("rule_inputs", ps.HEADLINE_RULES, q, usable0)
        unknown = call("unknown_load")
        names_series = (q.groupby(KEY).utility_name.last() if "utility_name" in q.columns else pd.Series(dtype=object))
        side = sr.Inputs(q, dose, regions, fuel, dd, ownership=ownership, usable=usable, gas=gas, unknown_load=unknown,
                         rules=ps.HEADLINE_RULES, names=names_series)
        if side.dose is not dose:
            raise AssemblyStopped("side.dose is not the frame design.load() returned")
        sets, d34, hold = {}, None, None
        for s in required_set_keys():
            if s[1] == 0.01:
                if d34 is None:
                    d34, hold = call("d34_table"), call("price_hold")
                sets[s] = call("every_cohort_at", s[1], q, dose, d34, hold)
            else:
                sets[s] = call("split", s[1], s[0], q, dose)
        stamp = ro.InventoryAsBuilt(dose_fingerprint=ro.frame_fingerprint(dose),
                                    source=(INVENTORY_AS_BUILT_SOURCE if research and "design_load" not in replaced
                                            else "invented: the frame the replaced design_load source returned, passed "
                                                 "to the split source and stored as side.dose"),
                                    split=None if research else (S["split"] if "split" in replaced else None))
    except AssemblyStopped:
        raise
    except Exception as exc:                                        # noqa: BLE001  stops, in words
        raise AssemblyStopped(f"side or sets could not be built, so nothing is assembled: {_words(exc)}") from exc
    used["side"] = ["design_load", "usable", "rule_inputs", "unknown_load"]
    used["sets"] = ["split"] + (["d34_table", "price_hold", "every_cohort_at"] if d34 is not None else [])
    used["inventory_as_built"] = ["design_load"]

    fields: dict = {"side": side, "sets": sets, "inventory_as_built": stamp, "inventory_inputs_are": inputs_are,
                    "reconciliation_u_inputs_are": inputs_are}
    extra_counts: dict = {}
    cpi = None

    def optional(fieldnames, srcs, build, why_needed):
        """Build one or more fields together; on failure each is deferred in words and left None."""
        try:
            vals = build()
        except Exception as exc:                                    # noqa: BLE001  deferred in words, never dropped
            for fn in fieldnames:
                fields[fn] = None
                deferred.append({"field": fn, "what": why_needed, "sources": list(srcs),
                                 "reason_in_words": _words(exc)})
            for fn in fieldnames:
                used[fn] = list(srcs)
            return None
        if len(fieldnames) == 1:
            vals = (vals,)
        for fn, v in zip(fieldnames, vals):
            fields[fn] = v
            used[fn] = list(srcs)
        return vals

    optional(["validation_reference"], ["validation_reference"], lambda: call("validation_reference"),
             "the headline validation reference (outcome_analysis.read_validation_reference)")
    optional(["catches_drift"], ["catches_drift"], lambda: call("catches_drift"),
             "the drift-reading flag for the headline set (run_outcomes.catches_drift_from_file)")
    optional(["suppliers"], ["suppliers"], lambda: call("suppliers"), "the supplier table (rule 2.4)")
    optional(["omissions"], ["omissions"], lambda: call("omissions"), "the checked list of known supplier omissions")
    optional(["e5_anchor"], ["e5_anchor"], lambda: call("e5_anchor"), "E5's state_anchor block and full table")
    optional(["e6_changers"], ["e6_changers"], lambda: call("e6_changers", side, sets),
             "E6's fixed list of comparison units that change market region")

    def _fh():
        r = call("future_hosts", side)
        return r["admitted"], r["histories"], r["aside"], r["hold"], r["late"]
    optional(["future_admitted", "e2_histories", "e2_aside", "e2_hold", "e2_late"], ["future_hosts"], _fh,
             "the future-host lists (future_hosts.main's admitted_by_cohort, late_host_histories, E2's lists)")
    optional(["inventory"], ["inventory"], lambda: call("inventory"), "the rebuilt inventory in memory")
    optional(["inventory_contexts"], ["inventory_context"],
             lambda: {ps.HEADLINE_SET: call("inventory_context", THETA, ps.HEADLINE_SET),
                      EVERY: call("inventory_context", THETA, EVERY)},
             "each set's inventory_runs.Context (E4a, E4b, E7, the later-start runs)")
    optional(["e7_errors"], ["e7_errors"], lambda: call("e7_errors"), "E7's permit-error distribution")
    fields["e7_draws"] = 200
    used["e7_draws"] = []
    optional(["peaks"], ["peaks"], lambda: call("peaks"),
             "condition 4's peak-demand rows, from the retained file of the one authorized read "
             "(condition4_peaks.load_retained); never read from data/raw here")
    hp = optional(["has_predecessors"], ["has_predecessors"], lambda: call("has_predecessors", q),
                  "the panel units with summed predecessors (condition 4)")
    if hp is None:
        # RunInputs defaults this field to an empty set, which would mark no unit and refuse nothing; so condition 4's
        # peaks are withdrawn too, and condition 4 is recorded as not computed in words (MissingInput on peaks).
        fields["has_predecessors"] = set()
        if fields.get("peaks") is not None:
            fields["peaks"] = None
            deferred.append({"field": "peaks", "what": "condition 4's peak rows",
                             "sources": ["peaks"],
                             "reason_in_words": ("withdrawn because the set of units with summed predecessors could not "
                                                 "be built; an empty set would mark no unit and nothing would refuse")})
    optional(["succession"], ["succession"], lambda: call("succession"), "the succession table (condition 4)")
    sn_cfg = optional(["second_number"], ["second_number"], lambda: call("second_number", side),
                      "the second number's configuration (second_number's machinery and second_number_scenarios' "
                      "realise_history and points_of)")
    if sn_cfg is not None and isinstance(fields["second_number"], dict) and "_assembly_counts" in fields["second_number"]:
        extra_counts["second_number"] = fields["second_number"].pop("_assembly_counts")
    fields["names"] = {(int(u), str(s)): n for (u, s), n in names_series.items()}
    used["names"] = ["design_load"]
    optional(["reconciliation_u"], ["row_u"], lambda: call("row_u", q),
             "row U's bundle (RowUInputs: the adopted Short Form spec, treatments U0 to U3, ownership classes, flags)")
    rc_pair = optional(["reconciliation_c"], ["row_c"], lambda: call("row_c", q, dose),
                       "row C's bundle (RowCInputs) and its CPI-U factors")
    if rc_pair is not None:
        bundle = fields["reconciliation_c"]
        if isinstance(bundle, tuple):
            fields["reconciliation_c"], cpi = bundle
    optional(["timing_added"], ["timing_added"], lambda: call("timing_added"),
             "the timing run's added hosts at their no-anchoring years")

    def _cs():
        host_aside, comp_aside, history = call("cs_lists")
        return ro.CSSampleInputs(host_aside=set(host_aside), comparison_aside=set(comp_aside),
                                 hold=set(call("price_hold")), history=dict(history))
    optional(["cs_sample"], ["cs_lists", "price_hold"], _cs, "Callaway and Sant'Anna's sample lists")

    names_ok = {f.name for f in dataclasses.fields(ro.RunInputs)}
    unknown_fields = sorted(set(fields) - names_ok)
    if unknown_fields:
        raise AssemblyStopped(f"the assembler built fields RunInputs does not have: {unknown_fields}")
    inputs = ro.RunInputs(**fields)

    # ---- the record ---------------------------------------------------------------------------------------------
    cache: dict = {}
    deferred_fields = {d["field"] for d in deferred}
    for f in dataclasses.fields(ro.RunInputs):
        v = getattr(inputs, f.name)
        srcs = used.get(f.name, [])
        files = []
        for s in srcs:
            if s in replaced:
                continue
            for rel in FILES.get(s, ()):
                if any(x["path"] == rel for x in files):
                    continue
                try:
                    p = check_path(ROOT / rel)
                except c4.PathRefused as exc:
                    files.append({"path": rel, "sha256": None, "refused_in_words": str(exc)})
                    continue
                if hashable(p) and p.exists():
                    files.append({"path": rel, "sha256": _sha(p, cache)})
                else:
                    files.append({"path": rel, "sha256": None,
                                  "why_not_hashed": ("read, not hashed: not on the assembler's hash list"
                                                     if p.exists() else "not on disk")})
        supplied = v is not None and f.name not in deferred_fields
        if f.name == "has_predecessors":
            supplied = f.name not in deferred_fields
        entry = {"supplied": supplied,
                 "built_by": [("replaced: " + _name_of(S[s])) if s in replaced else _name_of(_real(s)) for s in srcs],
                 "files": files,
                 "seconds": round(sum(seconds.get(s, 0.0) for s in srcs), 2),
                 "counts": _counts(f.name, v)}
        if f.name in extra_counts:
            entry["counts"] = {**(entry["counts"] or {}), **extra_counts[f.name]}
        if f.name == "reconciliation_m":
            entry["note"] = ("not built: row M is out of scope for this freeze (Joe, 2026-11-19, D-109) and no registry "
                             "entry reads it")
        if f.name == "inventory_readings":
            entry["note"] = "obsolete: None passes inventory_against_sales.ADOPTED (the check's four elements, D-107)"
        if f.name == "e7_draws":
            entry["note"] = "200 draws a direction, the plan's number (inventory_runs.E7_DRAWS)"
        rec[f.name] = entry
    rec["_cpi_factors"] = {"supplied": cpi is not None, "built_by": [_name_of(S["row_c"])],
                           "counts": None if cpi is None else {"years": len(cpi), "first": min(cpi), "last": max(cpi)}}
    rec["_seconds_by_source"] = dict(seconds)
    return Assembled(inputs=inputs, cpi_factors=cpi, record=rec, deferred=deferred, inputs_are=inputs_are,
                     sources_replaced=replaced)


def _counts(name: str, v) -> dict | None:
    """Counts only, never a value of anything."""
    if v is None:
        return None
    if name == "side":
        return {"quantity_rows": int(len(v.q)), "panel_units": int(v.q[KEY].drop_duplicates().shape[0]),
                "dose_rows": int(len(v.dose)), "usable_unit_years": _len(v.usable),
                "ownership_rows": _len(v.ownership), "unknown_load_units": _len(getattr(v.unknown_load, "affected", ())),
                "rules": v.rules.label}
    if name == "sets":
        return _set_counts(v)
    if name == "inventory_as_built":
        return {"dose_fingerprint_prefix": v.dose_fingerprint[:12], "split": "design.split" if v.split is None else
                _name_of(v.split)}
    if name == "has_predecessors":
        return {"units": int(len(v))}
    if name in ("e6_changers", "e2_aside", "e2_hold", "e2_late"):
        return {"units": int(len(v))}
    if name == "future_admitted":
        return {"cohorts": int(len(v)), "admitted_unit_cohorts": int(sum(len(x) for x in v.values()))}
    if name == "e2_histories":
        return {"late_hosts": int(len(v))}
    if name in ("suppliers", "omissions", "peaks", "succession"):
        return {"rows": int(len(v))}
    if name == "e5_anchor":
        return {"block_rows": int(len(v.block)), "state_anchor_rows": int(len(v.all_states))}
    if name == "inventory_contexts":
        return {k: {"aside": int(len(c.aside)), "history": int(len(c.history))} for k, c in v.items()}
    if name == "e7_errors":
        return {k: int(len(a)) for k, a in v.items()}
    if name == "names":
        return {"units": int(len(v))}
    if name == "timing_added":
        return {"hosts": int(len(v))}
    if name == "catches_drift":
        return {"sets_with_a_value": sorted(v)}
    if name == "validation_reference":
        return {"design_inputs_prefix": v.design_inputs_sha[:12], "rules_prefix": v.rules_sha[:12]}
    if name == "second_number":
        return {"units": len(v.get("units", [])), "scenario_units": len(v.get("scenario_units", [])),
                "assigned_forms": sorted(v.get("assigned", {})), "established_utilities": len(v.get("established", {})),
                "no_assigned": len(v.get("no_assigned", [])),
                "scenario_no_dose": {k: len(x) for k, x in (v.get("scenario_no_dose") or {}).items()}}
    if name == "reconciliation_u":
        return {"treatments": sorted(v.treatments), "ownership_units": int(len(v.ownership)),
                "flag_unit_years": None if v.sample_flags is None else int(len(v.sample_flags)),
                "flag_unit_years_with_a_record_of_a_filing": (None if v.sample_flags is None else
                                                              int(v.sample_flags.short_form.astype(bool).sum())),
                "short_form_exclusion": getattr(v.spec, "short_form_exclusion", None),
                "u1_indistinguishable": v.u1_indistinguishable}
    if name == "reconciliation_c":
        return {"counts_polygon_rows": None if v.counts_polygon is None else int(len(v.counts_polygon)),
                "counts_verified_rows": int(len(v.counts_verified)), "dose_rows": int(len(v.dose_verified)),
                "fiber_share_units": int(len(v.share)), "spending_series": sorted(v.spending_tables),
                "ownership_units": int(len(v.ownership)), "hosts_for_c5": int(len(v.hosts_for_c5)),
                "c4_cap": v.c4_cap}
    if name == "cs_sample":
        return {"host_aside": len(v.host_aside), "comparison_aside": len(v.comparison_aside), "hold": len(v.hold),
                "history": len(v.history)}
    if isinstance(v, (str, int, float, bool)):
        return {"value": v}
    return {"length": _len(v)}


# ======================================================================================================================
# What each registry entry fetches (read from the runners of run_outcomes.py), and whether it is supplied
# ======================================================================================================================

_B = ("side", "sets")
_INV = ("sets", "inventory", "inventory_contexts")
_SN = ("side", "second_number")
NEEDS: dict = {
    "reconciliation_row_U": {"required": ("reconciliation_u", "reconciliation_u_inputs_are"), "if_supplied": ()},
    "reconciliation_row_C": {"required": ("reconciliation_c",), "if_supplied": ()},
    "inventory_against_sales": {"required": _B + ("inventory_inputs_are", "inventory_as_built"),
                                "if_supplied": ("inventory_readings",)},
    "main_headline_set": {"required": _B + ("validation_reference",), "if_supplied": ("catches_drift",)},
    "main_ten_year_set": {"required": _B, "if_supplied": ("catches_drift",)},
    "main_plus_unsettled": {"required": _B, "if_supplied": ("catches_drift",)},
    "main_every_cohort_utility": {"required": _B, "if_supplied": ("catches_drift",)},
    "timing_run_no_anchoring_years": {"required": _B + ("timing_added",), "if_supplied": ("names",)},
    "customer_weighted": {"required": _B, "if_supplied": ()},
    "other_outcome_kwh_per_customer": {"required": _B, "if_supplied": ()},
    "other_outcome_bill_per_customer": {"required": _B, "if_supplied": ()},
    "other_outcome_residential_customers": {"required": _B, "if_supplied": ()},
    "second_number_as_assigned": {"required": _SN, "if_supplied": ()},
    "second_number_settled_only_classes_2_to_4": {"required": _SN, "if_supplied": ()},
    "second_number_ten_highest_leverage_left_out": {"required": _SN, "if_supplied": ()},
    "second_number_sensitivity_scenario_a_runner_up_placement": {"required": _SN, "if_supplied": ()},
    "second_number_sensitivity_scenario_b_other_end_of_every_dated_interval": {"required": _SN, "if_supplied": ()},
    "second_number_e3_after_period_2024_2025": {"required": _SN, "if_supplied": ()},
    "second_number_year_by_year": {"required": _SN, "if_supplied": ()},
    "affiliates_readmitted": {"required": _B, "if_supplied": ()},
    # the runner passes omissions through unchecked (None is read as no omission), so the assembler treats the checked
    # list as required (the agent's reading of the prompt's instruction)
    "shared_suppliers_removed": {"required": _B + ("suppliers", "omissions"), "if_supplied": ("names",)},
    "leave_one_comparison_out": {"required": _B, "if_supplied": ()},
    "leave_one_company_out": {"required": _B, "if_supplied": ()},
    "unresolved_ownership_excluded": {"required": _B, "if_supplied": ("names",)},
    "later_start_plus_1": {"required": _INV, "if_supplied": ()},
    "later_start_plus_3": {"required": _INV, "if_supplied": ()},
    "later_start_plus_5": {"required": _INV, "if_supplied": ()},
    "callaway_santanna": {"required": ("side", "cs_sample"), "if_supplied": ()},
    "estimators_agree": {"required": _B + ("cs_sample", "validation_reference"), "if_supplied": ("catches_drift",)},
    "longer_horizon": {"required": _B, "if_supplied": ()},
    "future_hosts_as_comparisons": {"required": _B + ("future_admitted",), "if_supplied": ()},
    "own_state_comparisons": {"required": _B, "if_supplied": ()},
    "threshold_1pct": {"required": _B, "if_supplied": ()},
    "threshold_5pct": {"required": _B, "if_supplied": ()},
    "fuel_mix_categorical": {"required": _B, "if_supplied": ()},
    "fuel_mix_none": {"required": _B, "if_supplied": ()},
    "size_band_side_run": {"required": _B, "if_supplied": ()},
    "E1": {"required": _B, "if_supplied": ()},
    "E2": {"required": _B + ("e2_histories", "e2_aside", "e2_hold", "e2_late"), "if_supplied": ()},
    "E3": {"required": _B, "if_supplied": ()},
    "E4a": {"required": _INV, "if_supplied": ()},
    "E4b": {"required": _INV, "if_supplied": ()},
    "E5": {"required": _B + ("e5_anchor",), "if_supplied": ()},
    "E6": {"required": _B + ("e6_changers",), "if_supplied": ()},
    "E7_earlier": {"required": _INV + ("e7_errors", "e7_draws"), "if_supplied": ()},
    "E7_later": {"required": _INV + ("e7_errors", "e7_draws"), "if_supplied": ()},
    "condition_1_load_share": {"required": _B, "if_supplied": ("names",)},
    "condition_2_investor_owned": {"required": _B, "if_supplied": ("names",)},
    "condition_3_retail_choice_proxy": {"required": _B, "if_supplied": ("names",)},
    "condition_4_past_utilization": {"required": _B + ("peaks", "succession", "has_predecessors"),
                                     "if_supplied": ("names",)},
    "influence_each_market_region_left_out": {"required": _B, "if_supplied": ("names",)},
    "influence_each_state_left_out": {"required": _B, "if_supplied": ("names",)},
    "influence_virginia_left_out": {"required": _B, "if_supplied": ("names",)},
    "influence_five_highest_load_utilities_dropped": {"required": _B, "if_supplied": ("names",)},
    "tariff_check": {"required": (), "if_supplied": ()},
    "regional_layer": {"required": (), "if_supplied": ()},
    "exploratory_work": {"required": (), "if_supplied": ()},
}
# The sets the main entries' runners call when estimators_agree composes them (run_outcomes.SIDE_BY_SIDE_RUNS).
_SIDE_BY_SIDE_SETS = tuple(s for _e, s in ro.SIDE_BY_SIDE_RUNS)


def _field_supplied(a: Assembled, f: str) -> bool:
    r = a.record.get(f)
    if r is not None:
        return bool(r["supplied"])
    return getattr(a.inputs, f, None) is not None


def stated_needs_check(assembled: Assembled) -> list:
    """For each entry of run_outcomes.ORDER_OF_UNBLINDING: the RunInputs fields its runner fetches (NEEDS), whether the
    assembled inputs supply each, the (set, threshold) keys it asks RunInputs.sets for and whether each is there, and,
    for the inventory runs, whether a context exists for each set. Counts and names only."""
    out = []
    for e in ro.ORDER_OF_UNBLINDING:
        need = NEEDS.get(e.id)
        if need is None:
            out.append({"entry": e.id, "status": e.status, "in_the_needs_table": False,
                        "all_required_supplied": False,
                        "missing_in_words": "the entry is not in the assembler's needs table"})
            continue
        rows = [{"field": f, "required": True, "supplied": _field_supplied(assembled, f)} for f in need["required"]]
        rows += [{"field": f, "required": False, "supplied": _field_supplied(assembled, f)} for f in need["if_supplied"]]
        set_keys = [s for s in e.sets if s[0] in dsg.SETS and s[1] is not None]
        if e.id == "estimators_agree":
            set_keys = list(_SIDE_BY_SIDE_SETS)
        if e.id == "E2":
            set_keys = [H2]
        sets_rows = [{"set": ro.set_label(s), "supplied": s in (assembled.inputs.sets or {})} for s in set_keys]
        ctx_rows = []
        if "inventory_contexts" in need["required"]:
            ctxs = assembled.inputs.inventory_contexts or {}
            ctx_rows = [{"set": s[0], "context_supplied": s[0] in ctxs} for s in set_keys]
        ok = (all(r["supplied"] for r in rows if r["required"]) and all(r["supplied"] for r in sets_rows)
              and all(r["context_supplied"] for r in ctx_rows))
        missing = [r["field"] for r in rows if r["required"] and not r["supplied"]] + \
                  [f"sets[{r['set']}]" for r in sets_rows if not r["supplied"]] + \
                  [f"inventory_contexts[{r['set']}]" for r in ctx_rows if not r["context_supplied"]]
        out.append({"entry": e.id, "status": e.status, "in_the_needs_table": True, "fields": rows, "sets": sets_rows,
                    "contexts": ctx_rows, "all_required_supplied": ok,
                    "missing_in_words": "; ".join(missing) if missing else None})
    return out


# ======================================================================================================================
# Quantity-side checks: counts and keys only, no outcome
# ======================================================================================================================

def _units(frame) -> set:
    return {(int(u), str(s)) for u, s in zip(frame.utility_id_eia, frame.state)}


def _unit_years(frame) -> set:
    return {(int(u), str(s), int(y)) for u, s, y in zip(frame.utility_id_eia, frame.state, frame.year)}


def _expected_customers(assembled: Assembled, expected):
    if expected is not None or assembled.inputs_are != ro.RESEARCH_DATA_AFTER_THE_FREEZE:
        return expected
    doc = json.loads(check_path(SUPPLEMENTARY_SPEC).read_text())
    c = doc["quantity_side_check"]
    return {"required_unit_years": c["required_unit_years"], "affected_unit_years": c["affected_unit_years"],
            "design_inputs_sha256_prefix": c.get("design_inputs_sha256_prefix"), "from": _rel(SUPPLEMENTARY_SPEC)}


def _rel(p) -> str:
    try:
        return str(Path(p).relative_to(ROOT))
    except ValueError:
        return str(p)


def second_number_premise(doc: dict, units) -> dict:
    """The premise of the session's reading on the second number's `units`: every unit the stored design summary lists
    under utilities_with_no_assigned_dose has the class second_number.NO_SINGLE_DOSE at every form (second_number.CAPS),
    and none of them is in `units`. Keys and class names only."""
    from pipeline.analysis import second_number as sn
    labs = [sn.cap_label(c) for c in sn.CAPS]
    listed = doc.get("utilities_with_no_assigned_dose") or {}
    in_units = {sn._uid(k) for k in (units or [])}
    other = {}
    for uid, e in sorted(listed.items()):
        by = e.get("by_form") or {}
        bad = {lab: (by.get(lab) or {}).get("class") for lab in labs if (by.get(lab) or {}).get("class") != sn.NO_SINGLE_DOSE}
        if bad:
            other[uid] = bad
    return {"units_listed": len(listed), "forms": labs,
            "units_with_no_single_dose_at_every_form": len(listed) - len(other),
            "units_with_another_class_at_some_form": other,
            "listed_units_inside_the_assembled_units": sorted(set(listed) & in_units),
            "premise_holds": bool(listed) and not other and not (set(listed) & in_units)}


def quantity_side_checks(assembled: Assembled, *, expected_customers: dict | None = None, split=None,
                         second_number_design=None) -> dict:
    """Counts and keys only; no outcome is read, no registry entry is run and inventory_against_sales.check is not
    called.

    headline_design: the headline set at 2% built by RunInputs.build; its design-inputs and rules hashes (prefixes) and
    the kernel's own check of the claim (outcome_analysis._validation with a ValidationClaim on the reference and
    side.usable, the claim main_headline_set makes), which reads no outcome. On research data the design-inputs hash is
    also compared with the prefix on file (b8515c35cba1). other_sets: every other set in RunInputs.sets built, or its
    failure in words. dose_stamp: side.dose's fingerprint against inventory_as_built. headline_resplit: the headline set
    split again from side.dose (the stamp's split, else design.split; `split` replaces both for a test) against the set
    supplied. row_u: the flags frame's unit-years covered and not covered against the quantity panel's unit-years of
    2015 to 2025, and the ownership classes against the panel's units. row_c: the ownership mapping against the panel's
    units. residential_customers: supplementary_outcomes.customers_check on the headline design's required unit-years,
    against the figure on file on research data (data/frozen/supplementary_outcomes_spec.json).
    second_number_units_premise: on research data (or with `second_number_design` given) the stored design summary's
    utilities_with_no_assigned_dose read and second_number_premise applied (keys and class names only)."""
    from pipeline.analysis import supplementary_outcomes as so
    inp = assembled.inputs
    side = inp.side
    out: dict = {"what_this_is": ("quantity-side checks only (counts and keys); no outcome, price, revenue or bill was "
                                  "read, no registry entry was run and inventory_against_sales.check was not called")}
    t0 = time.time()
    head = None
    try:
        head = inp.build(H2)
        fc = oa._fuel_control(head, None)
        h = oa.design_hashes(head, side.usable, fc)
        ref = inp.validation_reference
        check = oa._validation(head, fc, None, oa.ValidationClaim(ref, side.usable))
        out["headline_design"] = {"hosts": int(len(head.hosts)),
                                  "design_inputs_prefix": h["design_inputs"][:12],
                                  "rules_prefix": None if h["rules"] is None else h["rules"][:12],
                                  "reference_supplied": ref is not None,
                                  "check_passed": bool(check["passed"]), "check_in_words": check["why"]}
        if assembled.inputs_are == ro.RESEARCH_DATA_AFTER_THE_FREEZE:
            out["headline_design"]["design_inputs_prefix_on_file"] = EXPECTED_DESIGN_INPUTS_PREFIX
            out["headline_design"]["matches_the_prefix_on_file"] = h["design_inputs"].startswith(
                EXPECTED_DESIGN_INPUTS_PREFIX)
    except Exception as exc:                                        # noqa: BLE001  recorded in words
        out["headline_design"] = {"built": False, "failure_in_words": _words(exc), "check_passed": False}
    out["headline_design"]["seconds"] = round(time.time() - t0, 2)

    t0 = time.time()
    others = {}
    for s in (inp.sets or {}):
        if s == H2:
            continue
        try:
            d = inp.build(s)
            others[ro.set_label(s)] = {"built": True, "hosts": int(len(d.hosts)),
                                       "hosts_with_matches": int(sum(1 for m in d.hosts.match_keys if len(m)))
                                       if len(d.hosts) else 0}
        except Exception as exc:                                    # noqa: BLE001
            others[ro.set_label(s)] = {"built": False, "failure_in_words": _words(exc)}
    out["other_sets"] = others
    out["other_sets_seconds"] = round(time.time() - t0, 2)

    stamp = inp.inventory_as_built
    if stamp is None:
        out["dose_stamp"] = {"stamp_supplied": False, "equal": False}
        out["headline_resplit"] = {"computed": False, "why": "no stamp"}
    else:
        fp = ro.frame_fingerprint(side.dose)
        out["dose_stamp"] = {"stamp_supplied": True, "equal": fp == stamp.dose_fingerprint,
                             "stamp_prefix": stamp.dose_fingerprint[:12], "side_dose_prefix": fp[:12]}
        fn = split if split is not None else (stamp.split if stamp.split is not None else dsg.split)
        try:
            t, c = fn(THETA, ps.HEADLINE_SET, side.q, side.dose)
            t0_, c0_ = inp.sets[H2]
            ht, hs = _units(t0_), _units(t)
            out["headline_resplit"] = {
                "computed": True,
                "hosts_equal": ro.frame_fingerprint(t.reset_index(drop=True)) == ro.frame_fingerprint(t0_.reset_index(drop=True)),
                "comparison_units_equal": ro.frame_fingerprint(c.reset_index(drop=True)) == ro.frame_fingerprint(c0_.reset_index(drop=True)),
                "hosts_supplied": len(ht), "hosts_split_again": len(hs),
                "hosts_supplied_not_in_the_split_again": len(ht - hs), "hosts_split_again_not_supplied": len(hs - ht),
                "split_by": "design.split" if fn is dsg.split else _name_of(fn)}
        except Exception as exc:                                    # noqa: BLE001
            out["headline_resplit"] = {"computed": False, "failure_in_words": _words(exc)}

    q = side.q
    panel_units = _units(q[KEY].drop_duplicates())
    b = inp.reconciliation_u
    if b is None:
        out["row_u"] = {"supplied": False}
    else:
        lo, hi = 2015, 2025
        panel_uy = _unit_years(q[(q.year >= lo) & (q.year <= hi)][KEY + ["year"]].drop_duplicates())
        flags_uy = set() if b.sample_flags is None else _unit_years(b.sample_flags)
        own = b.ownership
        with_class = {k for k, c in zip(zip(own.utility_id_eia.astype(int), own.state.astype(str)), own.ownership_class)
                      if c is not None and not (isinstance(c, float) and np.isnan(c))}
        own_units = _units(own)
        out["row_u"] = {"supplied": True,
                        "panel_unit_years_2015_to_2025": len(panel_uy),
                        "flag_unit_years": len(flags_uy),
                        "panel_unit_years_covered_by_the_flags": len(panel_uy & flags_uy),
                        "panel_unit_years_not_covered": len(panel_uy - flags_uy),
                        "flag_unit_years_not_in_the_panel": len(flags_uy - panel_uy),
                        "not_covered_means": ("outside the 50 states and DC or with no ownership class (the frame's own "
                                              "rules); whether the frame covers every outcome unit-year cannot be shown "
                                              "before outcomes are read"),
                        "ownership_units": len(own_units), "ownership_units_with_a_class": len(with_class),
                        "ownership_units_with_no_class": len(own_units - with_class),
                        "panel_units": len(panel_units),
                        "panel_units_absent_from_the_ownership_table": len(panel_units - own_units),
                        "ownership_units_not_in_the_panel": len(own_units - panel_units)}
    c = inp.reconciliation_c
    if c is None:
        out["row_c"] = {"supplied": False}
    else:
        mapped = {(int(u), str(s)) for u, s in c.ownership}
        out["row_c"] = {"supplied": True, "panel_units": len(panel_units), "mapped_units": len(mapped),
                        "panel_units_with_no_class": len(panel_units - mapped),
                        "mapped_units_not_in_the_panel": len(mapped - panel_units),
                        "counts_polygon_supplied": c.counts_polygon is not None,
                        "hosts_for_c5": len(c.hosts_for_c5)}
    sn_path = second_number_design
    if sn_path is None and assembled.inputs_are == ro.RESEARCH_DATA_AFTER_THE_FREEZE:
        sn_path = SECOND_NUMBER_DESIGN
    if sn_path is None:
        out["second_number_units_premise"] = {"checked": False, "why": "invented inputs and no stored design summary "
                                                                       "given; no file under data/ is read"}
    else:
        try:
            doc = json.loads(check_path(sn_path).read_text())
            out["second_number_units_premise"] = {"checked": True, "from": _rel(sn_path),
                                                  **second_number_premise(doc, (inp.second_number or {}).get("units"))}
        except Exception as exc:                                    # noqa: BLE001
            out["second_number_units_premise"] = {"checked": False, "failure_in_words": _words(exc)}
    out["has_predecessors_units"] = int(len(inp.has_predecessors))
    out["peaks_rows"] = None if inp.peaks is None else int(len(inp.peaks))

    t0 = time.time()
    if head is None:
        out["residential_customers"] = {"computed": False, "why": "the headline design did not build"}
    else:
        try:
            cc = so.customers_check(head, q[KEY + ["year", "res_customers"]])
            r = {"computed": True, "required_unit_years": cc["required_unit_years"],
                 "affected_unit_years": cc["affected_unit_years"], "positive_and_finite_on_every_required_unit_year":
                 bool(cc["computable"]), "by_reason": {k: v["unit_years"] for k, v in cc["by_reason"].items()}}
            exp = _expected_customers(assembled, expected_customers)
            if exp is not None:
                r["on_file"] = exp
                r["equal_to_the_figure_on_file"] = (r["required_unit_years"] == exp["required_unit_years"]
                                                    and r["affected_unit_years"] == exp["affected_unit_years"])
            out["residential_customers"] = r
        except Exception as exc:                                    # noqa: BLE001
            out["residential_customers"] = {"computed": False, "failure_in_words": _words(exc)}
    out["residential_customers"]["seconds"] = round(time.time() - t0, 2)
    return out


def summary(assembled: Assembled) -> dict:
    """The record, the deferred list and the needs check together, counts only (for a dry run's printout)."""
    needs = stated_needs_check(assembled)
    return {"inputs_are": assembled.inputs_are, "sources_replaced": assembled.sources_replaced,
            "record": assembled.record, "deferred": assembled.deferred,
            "entries_with_every_required_input": sum(1 for n in needs if n["all_required_supplied"]),
            "entries_missing_an_input": {n["entry"]: n["missing_in_words"] for n in needs if not n["all_required_supplied"]}}


if __name__ == "__main__":
    print("pipeline/analysis/assemble_inputs.py has no main: call assemble(inputs_are=...) from a caller. Nothing was "
          "read.")
