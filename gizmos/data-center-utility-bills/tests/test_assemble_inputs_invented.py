"""The input assembler (pipeline/analysis/assemble_inputs.py) on invented inputs only.

The invented world is tests/test_run_outcomes_invented.build_world (five hosts, their comparison utilities, an invented
inventory, invented rows U and C): every loader of assemble_inputs.Sources is replaced by one that returns a piece of that
world, and no file under data/ is read. One test replaces every real loader (each assemble_inputs._real_* and the module
functions they call) with one that fails if called, and requires the assembly never to trip it.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import assemble_inputs as ai  # noqa: E402
from pipeline.analysis import condition4_peaks as c4  # noqa: E402
from pipeline.analysis import conditions as cn  # noqa: E402
from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import run_outcomes as ro  # noqa: E402

import test_run_outcomes_invented as W  # noqa: E402

INV = ro.INVENTED_INPUTS
CPI = {y: 1.0 + 0.01 * (2024 - y) for y in range(2015, 2025)}
NOT_SUPPLIED_BY_DESIGN = {"reconciliation_m", "inventory_readings"}       # row M out of scope; the obsolete readings


@pytest.fixture(scope="module")
def world():
    inp, w = W.build_world()
    return inp, w


def sources_for(world, **override):
    """Every loader replaced by one that returns a piece of the invented world."""
    inp, _ = world
    side = inp.side
    sets = dict(inp.sets)
    ctx = inp.inventory_contexts[ro.HEADLINE_SET]
    calls = {"split_doses": []}

    def split(theta, which, q, dose):
        calls["split_doses"].append(dose)
        return sets[(which, theta)]
    s = dict(
        design_load=lambda: (side.q, side.dose, side.regions, side.fuel, side.dd),
        usable=lambda: side.usable,
        rule_inputs=lambda rules, q, usable: (side.ownership, usable, side.gas),
        unknown_load=lambda: side.unknown_load,
        split=split,
        d34_table=lambda: pd.DataFrame(),
        price_hold=lambda: set(),
        every_cohort_at=lambda theta, q, dose, d34, hold: sets[(ro.EVERY, theta)],
        validation_reference=lambda: inp.validation_reference,
        catches_drift=lambda: {ro.HEADLINE_SET: True},
        suppliers=lambda: inp.suppliers,
        omissions=lambda: pd.DataFrame(columns=["host", "match", "kind"]),
        e5_anchor=lambda: inp.e5_anchor,
        e6_changers=lambda side_, sets_: set(W.CHANGERS),
        future_hosts=lambda side_: {"admitted": inp.future_admitted, "histories": inp.e2_histories, "aside": set(),
                                    "hold": set(), "late": set(inp.e2_late)},
        inventory=lambda: inp.inventory,
        inventory_context=lambda theta, which: ctx,
        e7_errors=lambda: inp.e7_errors,
        peaks=lambda: cn.read_peaks(inp.peaks),
        succession=lambda: inp.succession,
        has_predecessors=lambda q: {(1, "AA")},
        second_number=lambda side_: dict(inp.second_number),
        timing_added=lambda: dict(inp.timing_added),
        row_u=lambda q: inp.reconciliation_u,
        row_c=lambda q, dose: (inp.reconciliation_c, dict(CPI)),
        cs_lists=lambda: (set(), set(), {}),
    )
    s.update(override)
    return ai.Sources(**s), calls


def full_split(world):
    inp, _ = world
    sets = dict(inp.sets)
    return lambda theta, which, q, dose: sets[(which, theta)]


# ---- filling every field --------------------------------------------------------------------------------------------

def test_every_field_is_filled_from_the_replaced_loaders(world):
    src, _ = sources_for(world)
    a = ai.assemble(inputs_are=INV, sources=src)
    assert a.deferred == []
    assert sorted(a.sources_replaced) == sorted(ai.SOURCE_NAMES)
    for f in dataclasses.fields(ro.RunInputs):
        r = a.record[f.name]
        if f.name in NOT_SUPPLIED_BY_DESIGN:
            assert r["supplied"] is False and "note" in r
            continue
        assert r["supplied"] is True, f.name
        assert all(b.startswith("replaced: ") for b in r["built_by"]), (f.name, r["built_by"])
        assert r["files"] == [], f.name                       # a replaced loader opens no file the assembler records
    assert set(a.inputs.sets) == set(ai.required_set_keys())
    assert a.inputs.e7_draws == 200
    assert a.cpi_factors == CPI
    assert a.record["has_predecessors"]["counts"] == {"units": 1}
    assert a.inputs.peaks.columns.tolist() == list(c4.PEAKS_AS_READ)


def test_inputs_are_is_required_refused_unless_one_of_the_two_and_stamps_both_fields(world):
    src, _ = sources_for(world)
    with pytest.raises(TypeError):
        ai.assemble(sources=src)                              # noqa: required keyword
    for bad in ("research", "invented", None, ""):
        with pytest.raises(ai.InputsAreRefused, match="must be one of"):
            ai.assemble(inputs_are=bad, sources=src)
    for are in ro.INPUTS_ARE:
        a = ai.assemble(inputs_are=are, sources=sources_for(world)[0])
        assert a.inputs.reconciliation_u_inputs_are == are and a.inputs.inventory_inputs_are == are
        assert a.inputs_are == are


def test_the_stamp_is_the_fingerprint_of_the_very_dose_frame_split_and_stored_as_side_dose(world):
    inp, _ = world
    src, calls = sources_for(world)
    a = ai.assemble(inputs_are=INV, sources=src)
    assert a.inputs.side.dose is inp.side.dose
    assert calls["split_doses"] and all(d is inp.side.dose for d in calls["split_doses"])
    assert a.inputs.inventory_as_built.dose_fingerprint == ro.frame_fingerprint(inp.side.dose)
    assert a.inputs.inventory_as_built.split is src.split            # an invented split is carried for the re-split
    r = ai.assemble(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, sources=sources_for(world)[0])
    assert r.inputs.inventory_as_built.split is None                 # research data: design.split, never a stand-in


# ---- failures -------------------------------------------------------------------------------------------------------

def boom(msg):
    def f(*a, **k):
        raise RuntimeError(msg)
    return f


def test_a_loader_that_raises_defers_its_field_in_words_and_the_others_are_still_filled(world):
    src, _ = sources_for(world, suppliers=boom("invented supplier failure"), future_hosts=boom("invented e2 failure"))
    a = ai.assemble(inputs_are=INV, sources=src)
    by = {d["field"]: d for d in a.deferred}
    assert set(by) == {"suppliers", "future_admitted", "e2_histories", "e2_aside", "e2_hold", "e2_late"}
    assert "invented supplier failure" in by["suppliers"]["reason_in_words"]
    assert all("invented e2 failure" in by[f]["reason_in_words"] for f in ("future_admitted", "e2_late"))
    assert a.inputs.suppliers is None and a.inputs.future_admitted is None and a.inputs.e2_late is None
    assert a.inputs.omissions is not None and a.inputs.reconciliation_u is not None and a.inputs.peaks is not None
    assert a.record["suppliers"]["supplied"] is False and a.record["omissions"]["supplied"] is True
    needs = {n["entry"]: n for n in ai.stated_needs_check(a)}
    assert needs["shared_suppliers_removed"]["all_required_supplied"] is False
    assert "suppliers" in needs["shared_suppliers_removed"]["missing_in_words"]
    assert needs["E2"]["all_required_supplied"] is False and needs["main_headline_set"]["all_required_supplied"]


def test_peaks_absent_is_deferred_in_words_and_never_read_from_the_raw_file(world, monkeypatch, tmp_path):
    monkeypatch.setattr(cn, "read_peaks", lambda *a, **k: pytest.fail("the raw file was read"))
    monkeypatch.setattr(c4, "RETAINED", tmp_path / "absent.parquet")
    monkeypatch.setattr(c4, "RECORD", tmp_path / "absent.json")
    monkeypatch.setitem(ai.FILES, "peaks", ())                       # the record's hashes touch no real retained file
    src, _ = sources_for(world, peaks=None)                          # the real loader: condition4_peaks.load_retained
    a = ai.assemble(inputs_are=INV, sources=src)
    (d,) = [x for x in a.deferred if x["field"] == "peaks"]
    assert "has not been made" in d["reason_in_words"] and a.inputs.peaks is None


def test_a_failure_to_build_the_predecessors_withdraws_the_peaks_so_nothing_runs_with_an_empty_set(world):
    src, _ = sources_for(world, has_predecessors=boom("no column"))
    a = ai.assemble(inputs_are=INV, sources=src)
    fields = {d["field"] for d in a.deferred}
    assert {"has_predecessors", "peaks"} <= fields
    assert a.inputs.peaks is None and a.inputs.has_predecessors == set()
    needs = {n["entry"]: n for n in ai.stated_needs_check(a)}
    assert needs["condition_4_past_utilization"]["all_required_supplied"] is False


@pytest.mark.parametrize("which", ["design_load", "usable", "rule_inputs", "unknown_load", "split", "every_cohort_at",
                                   "d34_table", "price_hold"])
def test_a_failure_building_side_or_sets_stops_the_assembly(world, which):
    src, _ = sources_for(world, **{which: boom(f"invented {which} failure")})
    with pytest.raises(ai.AssemblyStopped, match=f"invented {which} failure"):
        ai.assemble(inputs_are=INV, sources=src)


# ---- the path guard and the hash list -----------------------------------------------------------------------------------

def test_the_path_guard_is_condition4s_and_the_hash_list_refuses_raw_blind_and_unlisted_files():
    assert ai.check_path is c4.refuse_raw_or_blind
    for p in ("data/raw/pudl/x.parquet", "data/blind/panel_outcomes.parquet"):
        with pytest.raises(c4.PathRefused):
            ai.check_path(ROOT / p)
        with pytest.raises(c4.PathRefused):
            ai.hashable(ROOT / p)
    assert ai.hashable(ROOT / "data/frozen/treatment_bounds.json")
    assert ai.hashable(ROOT / "data/interim/panel_quantities.parquet")
    assert ai.hashable(ROOT / "data/interim/reconciliation_short_form_flags.parquet")
    assert ai.hashable(ROOT / "pipeline/analysis/price_hold.csv")
    assert not ai.hashable(ROOT / "data/interim/reconciliation_polygon_incidence.parquet")
    assert not ai.hashable(ROOT / "data/frozen/water/x.json") and not ai.hashable(ROOT / "pipeline/water/x.py")
    assert not ai.hashable(ROOT / "docs/DECISIONS.md")


def test_no_traced_file_of_any_real_loader_is_under_raw_or_blind():
    for name, files in ai.FILES.items():
        assert name in ai.SOURCE_NAMES, name
        for f in files:
            ai.check_path(ROOT / f)


def test_a_real_loader_whose_files_include_a_raw_path_is_refused_before_it_is_called(world, monkeypatch):
    monkeypatch.setitem(ai.FILES, "suppliers", ("data/raw/pudl/some_table.parquet",))
    monkeypatch.setattr(ai, "_real_suppliers", lambda: pytest.fail("a loader with a raw path was called"))
    src, _ = sources_for(world, suppliers=None)
    a = ai.assemble(inputs_are=INV, sources=src)
    (d,) = [x for x in a.deferred if x["field"] == "suppliers"]
    assert "PathRefused" in d["reason_in_words"] and "data/raw" in d["reason_in_words"]


# ---- the needs table ----------------------------------------------------------------------------------------------------

def test_the_needs_table_covers_every_executable_entry_and_names_only_runinputs_fields():
    ids = [e.id for e in ro.ORDER_OF_UNBLINDING]
    assert len(ids) == 57
    assert set(ids) == set(ai.NEEDS)
    names = {f.name for f in dataclasses.fields(ro.RunInputs)}
    for eid, n in ai.NEEDS.items():
        assert set(n["required"]) | set(n["if_supplied"]) <= names, eid
        if ro.REGISTRY_BY_ID[eid].status != ro.BUILT:
            assert n["required"] == (), eid


def test_every_entry_has_every_required_input_on_the_full_invented_assembly(world):
    a = ai.assemble(inputs_are=INV, sources=sources_for(world)[0])
    rows = ai.stated_needs_check(a)
    assert len(rows) == 57
    bad = {r["entry"]: r["missing_in_words"] for r in rows if not r["all_required_supplied"]}
    assert bad == {}
    agree = next(r for r in rows if r["entry"] == "estimators_agree")
    assert {s["set"] for s in agree["sets"]} == {ro.set_label(s) for _e, s in ro.SIDE_BY_SIDE_RUNS}


def test_a_missing_set_or_context_is_named_by_the_needs_check(world):
    a = ai.assemble(inputs_are=INV, sources=sources_for(world)[0])
    a.inputs.sets.pop((ro.HEADLINE_SET, 0.05))
    a.inputs.inventory_contexts.pop(ro.EVERY)
    rows = {r["entry"]: r for r in ai.stated_needs_check(a)}
    assert "sets[headline_set at 5%]" in rows["threshold_5pct"]["missing_in_words"]
    assert "inventory_contexts[every_cohort_utility]" in rows["E4a"]["missing_in_words"]


# ---- the quantity-side checks -----------------------------------------------------------------------------------------

def test_the_quantity_side_checks_pass_on_correct_inputs(world):
    a = ai.assemble(inputs_are=INV, sources=sources_for(world)[0])
    c = ai.quantity_side_checks(a)
    assert c["headline_design"]["check_passed"] is True and c["headline_design"]["hosts"] == 5
    assert c["dose_stamp"]["equal"] is True
    assert c["headline_resplit"]["hosts_equal"] and c["headline_resplit"]["comparison_units_equal"]
    assert set(c["other_sets"]) == {ro.set_label(s) for s in a.inputs.sets if s != ro.H2}
    assert all(v["built"] for v in c["other_sets"].values())
    assert c["residential_customers"]["positive_and_finite_on_every_required_unit_year"] is True
    assert c["residential_customers"]["affected_unit_years"] == 0
    assert c["row_u"]["supplied"] and c["row_c"]["supplied"] and c["has_predecessors_units"] == 1
    exp = {"required_unit_years": c["residential_customers"]["required_unit_years"], "affected_unit_years": 0}
    c2 = ai.quantity_side_checks(a, expected_customers=exp)
    assert c2["residential_customers"]["equal_to_the_figure_on_file"] is True
    c3 = ai.quantity_side_checks(a, expected_customers={**exp, "required_unit_years": 536})
    assert c3["residential_customers"]["equal_to_the_figure_on_file"] is False


def test_a_changed_dose_frame_is_reported(world):
    a = ai.assemble(inputs_are=INV, sources=sources_for(world)[0])
    d = a.inputs.side.dose.copy()
    d.loc[d.index[0], "dose"] = d.loc[d.index[0], "dose"] + 0.5
    a.inputs.side.dose = d
    c = ai.quantity_side_checks(a, split=full_split(world))
    assert c["dose_stamp"]["equal"] is False
    assert c["dose_stamp"]["stamp_prefix"] != c["dose_stamp"]["side_dose_prefix"]


def test_a_host_dropped_from_the_headline_set_is_reported(world):
    inp, _ = world
    t, cl = inp.sets[ro.H2]
    dropped = (t[t.utility_id_eia != 4].reset_index(drop=True), cl)
    sets = dict(inp.sets)
    sets[ro.H2] = dropped
    src, _ = sources_for(world, split=lambda theta, which, q, dose: sets[(which, theta)])
    a = ai.assemble(inputs_are=INV, sources=src)
    c = ai.quantity_side_checks(a, split=full_split(world))
    assert c["headline_resplit"]["hosts_equal"] is False
    assert c["headline_resplit"]["hosts_split_again_not_supplied"] == 1
    assert c["headline_resplit"]["comparison_units_equal"] is True
    assert c["headline_design"]["check_passed"] is False
    assert "differ from those of the validated design" in c["headline_design"]["check_in_words"]


def test_the_quantity_side_checks_never_call_the_inventory_check_or_a_registry_run(world, monkeypatch):
    a = ai.assemble(inputs_are=INV, sources=sources_for(world)[0])
    monkeypatch.setattr(ro.ias, "check", lambda *x, **k: pytest.fail("inventory_against_sales.check was called"))
    monkeypatch.setattr(ro, "run", lambda *x, **k: pytest.fail("a registry entry was run"))
    monkeypatch.setattr(ro, "run_all", lambda *x, **k: pytest.fail("the registry was run"))
    monkeypatch.setattr(oa, "estimate", lambda *x, **k: pytest.fail("the kernel estimated something"))
    ai.quantity_side_checks(a)
    ai.stated_needs_check(a)


# ---- no real loader is called ---------------------------------------------------------------------------------------

def test_no_real_loader_is_called_when_every_source_is_replaced(world, monkeypatch):
    from pipeline.analysis import inventory_runs as ir
    from pipeline.analysis import usable_flag
    tripped = []

    def trap(name):
        def f(*a, **k):
            tripped.append(name)
            raise AssertionError(f"real loader {name} was called")
        return f
    for n in ai.SOURCE_NAMES:
        monkeypatch.setattr(ai, "_real_" + n, trap("_real_" + n))
    for mod, n in ((dsg, "load"), (dsg, "split"), (ps, "load_unknown_load"), (ps, "price_hold"), (ps, "rule_inputs"),
                   (ps, "history_settled"), (usable_flag, "read"), (oa, "read_validation_reference"),
                   (ro, "catches_drift_from_file"), (c4, "load_retained"), (ir, "load_inventory"), (ir, "load_errors"),
                   (cn, "read_peaks")):
        monkeypatch.setattr(mod, n, trap(f"{mod.__name__}.{n}"))
    monkeypatch.setattr(ir.Context, "from_files", classmethod(lambda cls, *a, **k: trap("Context.from_files")()))
    src, _ = sources_for(world, peaks=lambda: W.peaks())          # cn.read_peaks is trapped here, so not called
    a = ai.assemble(inputs_are=INV, sources=src)
    assert tripped == [] and a.deferred == []


def test_an_unreplaced_source_resolves_to_the_real_loader_when_assemble_is_called(world, monkeypatch):
    assert all(getattr(ai.Sources(), n) is None for n in ai.SOURCE_NAMES)
    monkeypatch.setattr(ai, "_real_catches_drift", lambda: {"looked_up": True})
    src, _ = sources_for(world, catches_drift=None)
    a = ai.assemble(inputs_are=INV, sources=src)
    assert a.inputs.catches_drift == {"looked_up": True}
    assert a.record["catches_drift"]["built_by"][0].endswith("<lambda>")


def test_the_record_carries_counts_and_no_value(world):
    a = ai.assemble(inputs_are=INV, sources=sources_for(world)[0])
    s = ai.summary(a)
    assert s["entries_with_every_required_input"] == 57 and s["entries_missing_an_input"] == {}
    text = repr(s)
    assert "log_points" not in text and "res_price" not in text
    assert a.record["sets"]["counts"][ro.set_label(ro.H2)]["hosts"] == 5


# ---- the premise of the reading on the second number's units (the coordinator's instruction of 2026-11-20) --------------

def stored_design(classes):
    return {"utilities_with_no_assigned_dose": {u: {"by_form": {lab: {"class": c} for lab, c in by.items()}}
                                                for u, by in classes.items()}}


def test_the_second_number_premise_is_checked_from_the_stored_summary_and_a_change_is_reported(world, tmp_path):
    import json as _json
    from pipeline.analysis import second_number as sn
    labs = [sn.cap_label(c) for c in sn.CAPS]
    NSD = "no_single_dose"                      # the class name as the stored file writes it
    a = ai.assemble(inputs_are=INV, sources=sources_for(world)[0])
    c = ai.quantity_side_checks(a)
    assert c["second_number_units_premise"]["checked"] is False          # invented inputs: no stored file read
    good = tmp_path / "second_number_design.json"
    good.write_text(_json.dumps(stored_design({"900:OR": {l: NSD for l in labs},
                                               "901:OR": {l: NSD for l in labs}})))
    r = ai.quantity_side_checks(a, second_number_design=good)["second_number_units_premise"]
    assert r["checked"] and r["premise_holds"] and r["units_with_no_single_dose_at_every_form"] == 2
    bad = tmp_path / "changed.json"
    bad.write_text(_json.dumps(stored_design({"900:OR": {**{l: NSD for l in labs}, labs[1]: "settled"}})))
    r = ai.quantity_side_checks(a, second_number_design=bad)["second_number_units_premise"]
    assert r["premise_holds"] is False and r["units_with_another_class_at_some_form"] == {"900:OR": {labs[1]: "settled"}}
    inside = tmp_path / "inside.json"
    u = a.inputs.second_number["units"][0]
    inside.write_text(_json.dumps(stored_design({sn._uid(u): {l: NSD for l in labs}})))
    r = ai.quantity_side_checks(a, second_number_design=inside)["second_number_units_premise"]
    assert r["premise_holds"] is False and r["listed_units_inside_the_assembled_units"] == [sn._uid(u)]
