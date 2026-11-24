"""The two disclosed enforcement gaps, closed in run_outcomes (session 27; Joe, 2026-11-20, D-120): "Close the two
disclosed enforcement gaps: reject unadopted Short Form rules for research execution of row U, and verify that the
headline design and inventory-against-sales check use the same inventory-as-built inputs. Test both correct inputs and
deliberate mismatches."

Gap 1: row U on research data takes only the adopted Short Form rule (reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE, D-115)
and a specification equal to ryu_spec of it (run_outcomes._row_u_guard). Gap 2: the inventory check is given the frame
the headline set was split from (run_outcomes._same_inventory_as_built: equal content by hash and the set reproduced).

Invented frames only, from tests/test_run_outcomes_invented.py's world. The gate file is a path under tmp_path and the
authorization variable is set through monkeypatch; design.split is replaced by an invented function through monkeypatch
and the real frozen lists are never read. The inventory check is never run on real frames. Nothing here reads data/.
"""
from __future__ import annotations

import copy
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import inventory_against_sales as ias  # noqa: E402
from pipeline.analysis import reconciliation_mu as rmu  # noqa: E402
from pipeline.analysis import run_outcomes as ro  # noqa: E402

import test_run_outcomes_invented as rw  # noqa: E402

KEY = ["utility_id_eia", "state"]
UNADOPTED = tuple(c for c in rmu.SHORT_FORM_RULES if c != rmu.U_SHORT_FORM_ADOPTED_CODE)


def one(r, s):
    return r["results"][ro.set_label(s)]


@pytest.fixture
def gate_open(tmp_path, monkeypatch):
    gate = tmp_path / "GATE1_SIGNED"
    gate.write_text("invented")
    monkeypatch.setattr(ro.panel, "GATE_FILE", gate)
    monkeypatch.setenv(ro.AUTH_ENV, "1")
    return gate


@pytest.fixture
def gate_shut(tmp_path, monkeypatch):
    monkeypatch.setattr(ro.panel, "GATE_FILE", tmp_path / "GATE1_SIGNED")
    monkeypatch.delenv(ro.AUTH_ENV, raising=False)
    return tmp_path / "GATE1_SIGNED"


# ======================================================================================================================
# Gap 1: row U
# ======================================================================================================================

def row_u(spec=None, are=ro.INVENTED_INPUTS, flags="adopted"):
    b = rw.row_u_inputs()
    spec = b.spec if spec is None else spec
    sample_flags = b.sample_flags if flags == "adopted" else flags
    u = ro.RowUInputs(spec=spec, treatments=b.treatments, ownership=b.ownership, sample_flags=sample_flags,
                      u1_indistinguishable=None)
    return ro.RunInputs(side=None, sets={}, reconciliation_u=u, reconciliation_u_inputs_are=are)


@pytest.fixture
def step_calls(monkeypatch):
    calls = []
    real = rmu.run_u_step

    def counted(*a, **k):
        calls.append(a[0])
        return real(*a, **k)
    monkeypatch.setattr(rmu, "run_u_step", counted)
    return calls


def run_u(inp):
    return ro.run("reconciliation_row_U", inp, rw.recon_frames("U"))


def assert_planted(res):
    assert res["steps_not_computed"] == [] and [x["step"] for x in res["steps"]] == list(rmu.U_STEPS)
    for x in res["steps"]:
        assert abs(x["pooled"]["estimate"] - rw.U_BETA) < 1e-5, x["step"]     # tolerance 1e-5, as the world's tests


def assert_refused(r, *words, steps=None):
    res = one(r, ro.PAPER_SAMPLE)
    assert r["estimated"] is False and res["estimated"] is False and "steps" not in res
    for w in words:
        assert w in res["failure_in_words"], (w, res["failure_in_words"])
    if steps is not None:
        assert steps == []
    return res["failure_in_words"]


def test_correct_research_inputs_pass_the_guard_and_every_step_runs(gate_open, step_calls):
    spec = rmu.ryu_spec(rmu.U_SHORT_FORM_ADOPTED_CODE)
    r = run_u(row_u(spec, ro.RESEARCH_DATA_AFTER_THE_FREEZE))
    res = one(r, ro.PAPER_SAMPLE)
    assert r["estimated"] and "failure_in_words" not in res
    assert_planted(res)
    assert step_calls == list(rmu.U_STEPS)
    assert res["inputs_checked"] == {"inputs_are": ro.RESEARCH_DATA_AFTER_THE_FREEZE, "short_form_rule_checked": True,
                                     "short_form_exclusion": rmu.U_SHORT_FORM_ADOPTED_CODE,
                                     "specification": "reconciliation_mu.ryu_spec(reconciliation_mu."
                                                      "U_SHORT_FORM_ADOPTED_CODE)"}


@pytest.mark.parametrize("code", UNADOPTED)
def test_each_unadopted_code_is_refused_on_research_data_and_no_step_runs(code, gate_open, step_calls):
    assert len(UNADOPTED) == 2
    flags = None if code == "none_in_outcome_frame" else "adopted"
    r = run_u(row_u(rmu.ryu_spec(code), ro.RESEARCH_DATA_AFTER_THE_FREEZE, flags=flags))
    msg = assert_refused(r, "RowUInputsRefused", f"Short Form rule {code!r}", repr(rmu.U_SHORT_FORM_ADOPTED_CODE),
                         "D-115", "no other code is accepted for research execution", steps=step_calls)
    assert r["failures_in_words"] == {ro.set_label(ro.PAPER_SAMPLE): msg}


@pytest.mark.parametrize("field,value", [("ss_correction", "clusters_only"),
                                         ("jurisdictions", tuple(reversed(rmu.RYU_OURS_JURISDICTIONS))),
                                         ("min_years", (3, "utility_state", "every_other_restriction")),
                                         ("weighting", "customers")])
def test_a_changed_other_field_is_refused_on_research_data(field, value, gate_open, step_calls):
    """The session's reading: every field other than the Short Form rule is fixed (D-107) and must equal ryu_spec's. The
    reversed jurisdictions pass reconciliation_mu's own check (it sorts them) and are still refused here."""
    spec = replace(rmu.ryu_spec(rmu.U_SHORT_FORM_ADOPTED_CODE), **{field: value})
    if field == "jurisdictions":
        spec.check()                                         # passes the module's check, and is refused by the registry
    assert_refused(run_u(row_u(spec, ro.RESEARCH_DATA_AFTER_THE_FREEZE)), "RowUInputsRefused",
                   "is not reconciliation_mu.ryu_spec(reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE)",
                   f"the fields that differ: {field}", "the session's reading", steps=step_calls)


def test_a_spec_that_is_not_a_ryuspec_is_refused_on_research_data(gate_open, step_calls):
    class Lookalike:
        short_form_exclusion = rmu.U_SHORT_FORM_ADOPTED_CODE
    assert_refused(run_u(row_u(Lookalike(), ro.RESEARCH_DATA_AFTER_THE_FREEZE)), "RowUInputsRefused",
                   "is not reconciliation_mu.ryu_spec", steps=step_calls)


def test_no_value_and_an_unknown_value_are_refused_and_none_is_chosen(gate_open, step_calls):
    assert_refused(run_u(row_u(are=None)), "MissingInput", "RunInputs.reconciliation_u_inputs_are",
                   "no value is chosen for the caller", steps=step_calls)
    for bad in ("research_data", "invented", ias.INVENTED_INPUTS.upper(), ""):
        assert_refused(run_u(row_u(are=bad)), "RowUInputsRefused", f"reconciliation_u_inputs_are is {bad!r}",
                       repr(ro.INVENTED_INPUTS), repr(ro.RESEARCH_DATA_AFTER_THE_FREEZE), steps=step_calls)
    assert ro.RunInputs.__dataclass_fields__["reconciliation_u_inputs_are"].default is None


def test_research_data_without_the_gate_file_then_without_the_variable_is_refused_in_that_order(tmp_path, monkeypatch,
                                                                                               step_calls):
    spec = rmu.ryu_spec("utilities_ever_filed")               # unadopted too: the gate is refused before the code
    gate = tmp_path / "GATE1_SIGNED"
    monkeypatch.setattr(ro.panel, "GATE_FILE", gate)
    monkeypatch.delenv(ro.AUTH_ENV, raising=False)
    inp = row_u(spec, ro.RESEARCH_DATA_AFTER_THE_FREEZE)
    assert_refused(run_u(inp), "RowUInputsRefused", "row U is not run on research data: the gate file GATE1_SIGNED "
                   "does not exist", steps=step_calls)
    monkeypatch.setenv(ro.AUTH_ENV, "1")
    assert_refused(run_u(inp), "the gate file GATE1_SIGNED does not exist", steps=step_calls)
    gate.write_text("invented")
    monkeypatch.setenv(ro.AUTH_ENV, "0")
    assert_refused(run_u(inp), f"the environment variable {ro.AUTH_ENV} is not set to 1", steps=step_calls)
    monkeypatch.setenv(ro.AUTH_ENV, "1")
    assert_refused(run_u(inp), "Short Form rule 'utilities_ever_filed'", steps=step_calls)


@pytest.mark.parametrize("code", rmu.SHORT_FORM_RULES)
def test_invented_inputs_still_run_all_three_codes_with_the_gate_shut(code, gate_shut, step_calls):
    flags = None if code == "none_in_outcome_frame" else "adopted"
    r = run_u(row_u(rmu.ryu_spec(code), ro.INVENTED_INPUTS, flags=flags))
    res = one(r, ro.PAPER_SAMPLE)
    assert r["estimated"] and "failure_in_words" not in res
    assert_planted(res)
    assert step_calls == list(rmu.U_STEPS)
    assert res["inputs_checked"]["short_form_rule_checked"] is False


def test_row_m_dormant_runner_is_not_wrapped():
    assert ro.ROW_M_DORMANT_RUNNER.__qualname__.startswith("_row_mu.")
    assert ro.REGISTRY_BY_ID["reconciliation_row_U"].runner.__qualname__.startswith("_row_u_guarded.")


# ======================================================================================================================
# Gap 2: the inventory as built
# ======================================================================================================================

@pytest.fixture(scope="module")
def world():
    inp, w = rw.build_world()
    return inp


def headline_split(inp, record=None):
    """An invented split: returns copies of the headline set the world supplies, so the set is reproduced exactly."""
    t, c = inp.sets[ro.H2]

    def split(theta, which, q, dose):
        if record is not None:
            record.append((theta, which))
        return t.copy(), c.copy()
    return split


def stamped(inp, *, split=None, dose=None, sets=None, are=ro.INVENTED_INPUTS, stamp="make"):
    out = ro.RunInputs(**{**inp.__dict__})
    out.inventory_inputs_are = are
    if stamp == "make":
        stamp = ro.InventoryAsBuilt(ro.frame_fingerprint(inp.side.dose), "invented: the world's dose frame", split=split)
    out.inventory_as_built = stamp
    if dose is not None:
        side = copy.copy(inp.side)
        side.dose = dose
        out.side = side
    if sets is not None:
        out.sets = {**inp.sets, ro.H2: sets}
    return out


@pytest.fixture
def check_calls(monkeypatch):
    calls = []
    real = ias.check

    def counted(*a, **k):
        calls.append(k.get("inputs_are"))
        return real(*a, **k)
    monkeypatch.setattr(ias, "check", counted)
    return calls


def run_ias(inp):
    return one(ro.run("inventory_against_sales", inp, None), ro.H2)


def test_invented_inputs_with_a_stamp_and_an_invented_split_pass(world, check_calls):
    seen = []
    res = run_ias(stamped(world, split=headline_split(world, seen)))
    assert res["estimated"] and abs(res["slope"]["slope"] - rw.IAS_SLOPE) < 1e-9          # the planted slope
    chk = res["inventory_as_built_check"]
    assert chk["checked"] is True and chk["dose_fingerprint"] == ro.frame_fingerprint(world.side.dose)
    assert chk["hosts_with_cohort_reproduced"] == len(world.sets[ro.H2][0])
    assert chk["comparison_eligible_units_reproduced"] == len(world.sets[ro.H2][1])
    assert seen == [(0.02, ro.HEADLINE_SET)] and check_calls == [ro.INVENTED_INPUTS]


def test_invented_inputs_with_no_stamp_run_as_before(world, check_calls):
    res = run_ias(stamped(world, stamp=None))
    assert res["estimated"] and res["inventory_as_built_check"]["checked"] is False and check_calls == [ro.INVENTED_INPUTS]


def test_research_labelled_inputs_pass_with_design_split_replaced_by_an_invented_function(world, gate_open, monkeypatch,
                                                                                         check_calls):
    seen = []
    monkeypatch.setattr(ro.dsg, "split", headline_split(world, seen))
    res = run_ias(stamped(world, are=ro.RESEARCH_DATA_AFTER_THE_FREEZE))
    assert res["estimated"] and res["inputs_are"] == ro.RESEARCH_DATA_AFTER_THE_FREEZE
    assert res["inventory_as_built_check"]["checked"] is True and res["inventory_as_built_check"]["split"] == "design.split"
    assert seen == [(0.02, ro.HEADLINE_SET)] and check_calls == [ro.RESEARCH_DATA_AFTER_THE_FREEZE]


def mismatched(world, kind):
    t, c = world.sets[ro.H2]
    if kind == "dose_changed_after_the_stamp":
        d = world.side.dose.copy()
        d.loc[d.index[0], "dc_gwh"] = d.loc[d.index[0], "dc_gwh"] + 1.0
        return dict(dose=d), "is not the frame the sets were split from"
    if kind == "host_added":
        extra = pd.DataFrame([(990001, "ZZ", 2015)], columns=KEY + ["cohort"])
        return dict(sets=(pd.concat([t, extra], ignore_index=True), c)), "1 host-and-cohort pairs supplied and not reproduced"
    if kind == "host_dropped":
        return dict(sets=(t.iloc[1:], c)), "0 host-and-cohort pairs supplied and not reproduced, 1 reproduced and not supplied"
    if kind == "cohort_changed":
        t2 = t.copy()
        t2.loc[t2.index[0], "cohort"] = int(t2.cohort.iloc[0]) + 1
        return dict(sets=(t2, c)), "1 host-and-cohort pairs supplied and not reproduced, 1 reproduced and not supplied"
    if kind == "comparison_unit_dropped":
        return dict(sets=(t, c.iloc[1:])), "0 comparison-eligible units supplied and not reproduced, 1 reproduced and not supplied"
    raise AssertionError(kind)


KINDS = ("dose_changed_after_the_stamp", "host_added", "host_dropped", "cohort_changed", "comparison_unit_dropped")


@pytest.mark.parametrize("kind", KINDS)
def test_each_deliberate_mismatch_is_refused_in_words_on_invented_inputs(kind, world, check_calls):
    kw, words = mismatched(world, kind)
    res = run_ias(stamped(world, split=headline_split(world), **kw))
    assert res["estimated"] is False and res["failure_in_words"].startswith("InventoryNotAsBuilt")
    assert words in res["failure_in_words"], res["failure_in_words"]
    assert check_calls == []                                  # refused before the check computes anything


@pytest.mark.parametrize("kind", KINDS)
def test_each_deliberate_mismatch_is_refused_in_words_on_research_data(kind, world, gate_open, monkeypatch, check_calls):
    monkeypatch.setattr(ro.dsg, "split", headline_split(world))
    kw, words = mismatched(world, kind)
    res = run_ias(stamped(world, are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, **kw))
    assert res["estimated"] is False and res["failure_in_words"].startswith("InventoryNotAsBuilt")
    assert words in res["failure_in_words"] and check_calls == []
    assert "990001" not in res["failure_in_words"]           # counts, never a list of utilities


def test_no_stamp_on_research_data_is_refused(world, gate_open, monkeypatch, check_calls):
    monkeypatch.setattr(ro.dsg, "split", headline_split(world))
    res = run_ias(stamped(world, are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, stamp=None))
    assert res["failure_in_words"].startswith("InventoryNotAsBuilt") and "RunInputs.inventory_as_built" in res["failure_in_words"]
    assert check_calls == []
    res = run_ias(stamped(world, are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, stamp="not a stamp"))
    assert "not an InventoryAsBuilt" in res["failure_in_words"] and check_calls == []


def test_a_substituted_split_on_research_data_is_refused(world, gate_open, check_calls):
    res = run_ias(stamped(world, split=headline_split(world), are=ro.RESEARCH_DATA_AFTER_THE_FREEZE))
    assert res["failure_in_words"].startswith("InventoryNotAsBuilt")
    assert "a substituted split function is refused on research data" in res["failure_in_words"] and check_calls == []


def test_the_modules_guard_still_refuses_research_data_without_the_gate_file_and_the_variable(world, gate_shut,
                                                                                              monkeypatch, check_calls):
    """inventory_against_sales._gate is unchanged and is reached first: research data with no gate file, then with no
    variable, is refused in its words, a correct stamp or not, and the split is never called."""
    seen = []
    monkeypatch.setattr(ro.dsg, "split", headline_split(world, seen))
    for stamp in ("make", None):
        res = run_ias(stamped(world, are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, stamp=stamp))
        assert res["failure_in_words"].startswith("InventoryCheckRefused") and "does not exist" in res["failure_in_words"]
    gate_shut.write_text("invented")
    res = run_ias(stamped(world, are=ro.RESEARCH_DATA_AFTER_THE_FREEZE))
    assert res["failure_in_words"].startswith("InventoryCheckRefused") and "is not set to 1" in res["failure_in_words"]
    assert seen == [] and check_calls == []
