"""The code traps session 18 listed, checked on the paths the pre-freeze work uses (session 19; Joe, D-103). Invented inputs
only: no file under data/ is read, and no real price hold, D-34 table or step E file is opened (where a module path would
read one, the test points it at a file it writes itself or makes the reader raise).

Each test says what wrong estimate or wrong label it guards against. The traps:
  1  validation labels: only the design the selected procedure was validated on may come out unlabelled, and the kernel
     checks the claim against the design's inputs rather than trusting a flag
  2  outcome-array alignment: an outcome vector built for one design can never be read against another's rows
  3  design rules after deletions: a design changed after it was built keeps the rules (and the lists) it was built under
  4  the 1% run: the comparison pool at 1% is built from a price hold and a D-34 table the caller passes, never from a
     file a module path happens to point at
Tolerances: 1e-10 where the computation is the same; 1e-3 log points where the run_outcomes world's noise (sd 1e-4)
enters, as in tests/test_run_outcomes_invented.py.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import conditions as cn  # noqa: E402
from pipeline.analysis import design  # noqa: E402
from pipeline.analysis import influence  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import prefreeze_summaries as pf  # noqa: E402
from pipeline.analysis import run_outcomes as ro  # noqa: E402
from pipeline.analysis import side_runs as sr  # noqa: E402
from pipeline.facilities import utility_history as uh  # noqa: E402
from test_outcome_analysis_invented import COMPS, FUEL, GAS, HOSTS, IOU, make, outcomes  # noqa: E402
import test_run_outcomes_invented as rw  # noqa: E402

KEY = ps.KEY
TOL = 1e-3


def headline_design():
    """make()'s invented design with the headline rules attached, as build_with_rules attaches them (make builds through
    design.build, which attaches none)."""
    d, q, regions, dd = make()
    d.rules = ps.HEADLINE_RULES
    return d, q, regions, dd


def claim_for(d, usable=None):
    """A validation reference made from `d` itself and the claim that `d` is that design."""
    ref = oa.ValidationReference.of_design(d, usable, source="invented: the design under test")
    return oa.ValidationClaim(ref, usable)


@pytest.fixture(scope="module")
def world():
    inp, w = rw.build_world()
    if hasattr(oa, "ValidationReference"):          # absent from the code as found; the tests that need it then fail
        inp.validation_reference = oa.ValidationReference.of_design(inp.build(ro.H2), inp.side.usable,
                                                                    source="invented: the run_outcomes world's headline design")
    return inp, w


# ======================================================================================================================
# Trap 1: validation labels
# ======================================================================================================================

def test_estimate_has_no_default_claim_of_validation():
    """Guards against: a caller that forgets the argument getting a result with no NOT_VALIDATED label on any design
    (the default was True, which is wrong for every design but one)."""
    p = inspect.signature(oa.estimate).parameters["validated_design"]
    assert p.default is inspect.Parameter.empty and p.kind is inspect.Parameter.KEYWORD_ONLY
    d, q, regions, dd = headline_design()
    y = oa.outcome_vector(d, outcomes(dd=dd, noise=0.01), "log_price")
    with pytest.raises(TypeError):
        oa.estimate(d, y)


def test_a_bare_true_cannot_claim_validation():
    """Guards against: a deleted design claimed as validated by a flag the kernel cannot check."""
    d, q, regions, dd = headline_design()
    e = influence.leave_out(d, {tuple(d.hosts.match_keys.iloc[0][0])})
    y = oa.outcome_vector(e, outcomes(dd=dd, noise=0.01), "log_price")
    with pytest.raises(TypeError, match="cannot be claimed with True"):
        oa.estimate(e, y, validated_design=True)


def test_the_claim_passes_on_the_validated_design_and_changes_no_number():
    """The validated path: the claim checks the design's inputs and rules and leaves every number as it was (exactly)."""
    d, q, regions, dd = headline_design()
    y = oa.outcome_vector(d, outcomes(dd=dd, noise=0.02, state_sd=0.01), "log_price")
    yes = oa.estimate(d, y, validated_design=claim_for(d))
    no = oa.estimate(d, y, validated_design=False)
    assert yes["validation"] is None and no["validation"] == oa.NOT_VALIDATED
    assert yes["validation_check"]["claimed"] and yes["validation_check"]["passed"]
    assert no["validation_check"] == {"claimed": False, "passed": None, "why": oa.NOT_CLAIMED}
    for k in ("headline", "early_years_test", "event_year_coefficients", "host_headline_weights", "count_N"):
        assert yes[k] == no[k], k


def _refused(r):
    return r["validation"] == oa.NOT_VALIDATED and r["validation_check"]["claimed"] and not r["validation_check"]["passed"]


def test_a_claim_is_refused_on_every_design_that_is_not_the_validated_one():
    """Guards against: a side run, a deletion, a pair removal, a host left out, a changed fuel control, the absorbed-controls
    option, another usable set, other rules or no rules at all coming out labelled as validated because the caller claimed
    it with the validated design's reference."""
    d, q, regions, dd = headline_design()
    frame = outcomes(dd=dd, noise=0.02, state_sd=0.01)
    c = claim_for(d)
    first = tuple(d.hosts.match_keys.iloc[0][0])
    cases = {}
    e = influence.leave_out(d, {first})
    e.rules = d.rules
    cases["one comparison left out"] = (e, {})
    p = pf.remove_pairs(d, {(tuple(d.hosts.key.iloc[1]), int(d.hosts.cohort.iloc[1])): {tuple(d.hosts.match_keys.iloc[1][0])}})
    cases["one pair removed (rule 2.4)"] = (p, {})
    h = influence._without(d, np.array([True, True, True, False]))
    h.rules = d.rules
    cases["a host left out"] = (h, {})
    cases["the headline set under the categorical fuel control"] = (d, {"fuel_control": ps.CATEGORICAL})
    cases["the absorbed-controls option"] = (d, {"absorbed_controls": oa.LEAVE_OUT_IF_EXACTLY_ABSORBED})
    import copy
    r2 = copy.copy(d)
    r2.rules = ps.AFFILIATES_READMITTED
    cases["the same hosts and matches under other rules"] = (r2, {})
    r0 = copy.copy(d)
    del r0.rules
    cases["a design that carries no rules"] = (r0, {"fuel_control": ps.GAS_SHARE})
    for name, (x, kw) in cases.items():
        r = oa.estimate(x, oa.outcome_vector(x, frame, "log_price"), validated_design=c, **kw)
        assert _refused(r), name
        assert r["validation_check"]["why"], name
    # another usable set: the claim carries the usable set the validated design was built on; a different one is refused
    other = oa.ValidationClaim(c.reference, {(1, "AA", 2001)})
    assert _refused(oa.estimate(d, oa.outcome_vector(d, frame, "log_price"), validated_design=other))
    # a claim with no reference is refused in words
    none = oa.estimate(d, oa.outcome_vector(d, frame, "log_price"), validated_design=oa.ValidationClaim(None, None))
    assert _refused(none) and "no validation reference" in none["validation_check"]["why"]


def test_windows_of_any_length_cannot_claim_validation():
    """Guards against: the thirteen-year window (or any span) labelled as validated: estimate_span stacks windows it cannot
    check against the validated design."""
    d, q, regions, dd = headline_design()
    ds = oa.stackable(d)
    y = oa.outcome_vector(d, outcomes(dd=dd, noise=0.02), "log_price")
    with pytest.raises(ValueError, match="cannot claim validation"):
        oa.estimate_span(ds.windows, ds.blocks(), y, 6, 3, (2, 3), gas=GAS, validated_design=True)
    assert oa.estimate_span(ds.windows, ds.blocks(), y, 6, 3, (2, 3), gas=GAS)["validation"] == oa.NOT_VALIDATED


def test_the_reference_is_read_from_the_step_e_files_and_they_must_agree(tmp_path):
    """The reference is the design_inputs and rules components recorded in the step E files and design_support.json's
    headline set; files that disagree are refused in words. Written here as invented JSON."""
    fp = lambda di, ru: {"fingerprint": {"sha256": "x", "of": {"design_inputs": di, "rules": ru}, "version": 1}}  # noqa: E731
    import json
    for f in oa.VALIDATION_FILES:
        (tmp_path / f).write_text(json.dumps(fp("aaa", "bbb")))
    (tmp_path / oa.DESIGN_SUPPORT_FILE).write_text(json.dumps({"sets": {ps.HEADLINE_SET: fp("aaa", "bbb")}}))
    ref = oa.read_validation_reference(tmp_path)
    assert ref.design_inputs_sha == "aaa" and ref.rules_sha == "bbb" and all(f in ref.source for f in oa.VALIDATION_FILES)
    (tmp_path / oa.VALIDATION_FILES[-1]).write_text(json.dumps(fp("ccc", "bbb")))
    with pytest.raises(ValueError, match="do not agree"):
        oa.read_validation_reference(tmp_path)


# ---- trap 1 on the registry ----------------------------------------------------------------------------------------

def test_the_registrys_headline_is_validated_only_with_the_reference(world):
    inp, w = world
    y = rw.outcome(w["dd"])
    res = rw.one(ro.run("main_headline_set", inp, y))
    assert res["validation"] is None and res["validation_check"]["passed"]
    bare = ro.RunInputs(side=inp.side, sets=inp.sets, catches_drift=inp.catches_drift)
    res0 = rw.one(ro.run("main_headline_set", bare, y))
    assert res0["validation"] == oa.NOT_VALIDATED and "no validation reference" in res0["validation_check"]["why"]
    assert abs(rw.head(res0) - rw.head(res)) == 0.0


def test_the_registrys_headline_entry_on_the_wrong_set_or_rules_is_not_labelled_validated(world):
    """Guards against: main_headline_set labelled validated because of its entry id and set label alone, when the caller
    supplied another set under the H2 key or other rules in RunInputs.side."""
    inp, w = world
    y = rw.outcome(w["dd"])
    wrong_set = ro.RunInputs(side=inp.side, sets={**inp.sets, ro.H2: inp.sets[(ro.TEN_YEAR_SET, 0.02)]})
    wrong_set.validation_reference = inp.validation_reference
    assert rw.one(ro.run("main_headline_set", wrong_set, y))["validation"] == oa.NOT_VALIDATED
    s = inp.side
    cat = sr.Inputs(s.q, s.dose, s.regions, s.fuel, s.dd, ownership=s.ownership, usable=s.usable, gas=s.gas,
                    unknown_load=s.unknown_load, ownership_of=s.ownership_of, rules=ps.CATEGORICAL_FUEL)
    wrong_rules = ro.RunInputs(side=cat, sets=inp.sets)
    wrong_rules.validation_reference = inp.validation_reference
    assert rw.one(ro.run("main_headline_set", wrong_rules, y))["validation"] == oa.NOT_VALIDATED


def test_a_condition_contrast_is_not_labelled_like_the_validated_headline(world):
    """Guards against: a descriptive contrast (no range, no test) carrying validation None, the value the validated
    headline carries, so that a reader filtering on it takes the contrast for validated."""
    inp, w = world
    res = rw.one(ro.run("condition_2_investor_owned", inp, rw.outcome(w["dd"])))
    assert res["validation"] == ro.NO_RANGE_NO_VALIDATION


def _validation_none_paths(x, path=()):
    out = []
    if isinstance(x, dict):
        if "validation" in x and x["validation"] is None:
            out.append(path)
        for k, v in x.items():
            out += _validation_none_paths(v, path + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            out += _validation_none_paths(v, path + (i,))
    return out


def test_every_registry_result_but_the_validated_headline_carries_a_label_and_every_vector_is_certified(world, monkeypatch):
    """Over run_all: (trap 1) the only result anywhere, nested results included (each deletion, each set, the longer
    horizon's two numbers), whose validation is None is main_headline_set on the headline set at 2%; (trap 2) every outcome
    vector the kernel and the conditions read was built by outcome_vector for the very rows it is read against."""
    inp, w = world
    seen = []

    def wrap(fn, name, pos):
        def inner(*a, **k):
            y = a[pos]
            seen.append((name, type(y).__name__, getattr(y, "rows_signature", None) is not None))
            return fn(*a, **k)
        return inner
    monkeypatch.setattr(oa, "estimate", wrap(oa.estimate, "estimate", 1))
    monkeypatch.setattr(oa, "estimate_span", wrap(oa.estimate_span, "estimate_span", 2))
    monkeypatch.setattr(cn, "contrast", wrap(cn.contrast, "contrast", 1))
    y = rw.outcome(w["dd"])
    out = ro.run_all(inp, rw.all_outcomes(y))
    # Callaway and Sant'Anna where diff-diff is absent, and always two more: the five-highest-load deletion (session 20),
    # since this world has five hosts, so dropping the five leaves none and the run is not estimable, in words; and the
    # size-band side run, refused in words because hosts 2 and 3 share a cohort and a cell (Joe, 2026-11-19, D-111).
    assert out["counts"]["built_set_runs_not_computed"] == (2 if rw.diff_diff_here() else 3)
    runs = {r["id"]: r for r in out["runs"]}
    rw.assert_size_band_refused_on_the_shared_world(runs["size_band_side_run"])
    nones = [(r["id"],) + p for r in out["runs"] for p in _validation_none_paths(r.get("results") or {})]
    assert nones == [("main_headline_set", ro.set_label(ro.H2))]
    # The size-band side run's result is exercised on its own variant world (host 3 set aside, no shared cohort and cell),
    # under the same wrappers: it carries a label at every level and the vector the kernel reads is certified.
    before = len(seen)
    sb = ro.run("size_band_side_run", rw.size_band_inputs(inp), y)
    assert sb["estimated"] and _validation_none_paths(sb.get("results") or {}) == []
    assert len(seen) > before
    assert seen and all(certified for _, _, certified in seen), [s for s in seen if not s[2]][:5]


# ======================================================================================================================
# Trap 2: outcome-array alignment
# ======================================================================================================================

def _long_world_with_a_lonely_host():
    """make()'s design with host 4 alone in its region (no matches), its thirteen-year windows, and LONG effects planted."""
    region = lambda key, year: "East" if key == (4, "BC") else "West"   # noqa: E731
    d, q, regions, dd = make(region=region)
    keys = list(d.unit_code)
    template = pd.DataFrame([(k[0], k[1], y, 0.0) for k in keys for y in range(2001, 2026)], columns=KEY + ["year", "log_price"])
    cohorts = sorted(int(g) for g in d.hosts.cohort.unique())
    w13 = sr.build_windows_span(cohorts, template, q, regions, FUEL, dd, d.unit_code, d.state_code, 6, 6)
    blocks13 = []
    for h in d.hosts.itertuples():
        idx = {tuple(k): i for i, k in enumerate(w13[int(h.cohort)].keys)}
        blocks13.append((int(h.cohort), np.array([idx[tuple(h.key)]]), np.array([idx[tuple(m)] for m in h.match_keys], dtype=int)))
    return d, w13, blocks13, outcomes(dd=dd, noise=0.01, state_sd=0.01)


def test_the_span_vector_drops_blocks_with_no_comparison_rows_itself():
    """Guards against: a caller of outcome_vector_span that does not filter the blocks with no comparison rows. Before the
    repair it got OutcomeMisaligned (an exception, not a wrong estimate: a host-only block adds its own rows, never zero);
    now the vector is built on the rows estimate_span stacks, and the estimate is the filtered caller's to 1e-12."""
    d, w13, blocks13, frame = _long_world_with_a_lonely_host()
    assert any(len(b[2]) == 0 for b in blocks13)
    stacked = [b for b in blocks13 if len(b[2])]
    filtered = oa.estimate_span(w13, stacked, oa.outcome_vector_span(w13, stacked, 6, 6, frame, "log_price"), 6, 6, (4, 5, 6), gas=GAS)
    unfiltered = oa.estimate_span(w13, blocks13, oa.outcome_vector_span(w13, blocks13, 6, 6, frame, "log_price"), 6, 6, (4, 5, 6), gas=GAS)
    assert abs(filtered["headline"]["log_points"] - unfiltered["headline"]["log_points"]) < 1e-12
    assert unfiltered["hosts_with_no_matches"] == ["4:BC"]


def test_a_vector_for_a_redated_design_is_refused_by_the_original_of_the_same_length():
    """Guards against: a silent wrong estimate when an outcome vector built for one design is read against another design
    with the same number of stacked rows (here host 1 re-dated from 2013 to 2014: same hosts, same matches, other years).
    Before the repair the length check passed and an estimate came back for the wrong years."""
    hosts_b = [(1, "AA", 10_000, IOU, 2014)] + HOSTS[1:]
    a, q, regions, dd = make()
    b, *_ = make(hosts=hosts_b)
    frame = outcomes(dd=dd, noise=0.01)
    ya, yb = oa.outcome_vector(a, frame, "log_price"), oa.outcome_vector(b, frame, "log_price")
    assert len(ya) == len(yb) and not np.array_equal(ya, yb)
    with pytest.raises(oa.OutcomeMisaligned, match="built for other rows"):
        oa.estimate(b, ya, validated_design=False)
    assert np.isfinite(oa.estimate(b, yb, validated_design=False)["headline"]["log_points"])


def test_a_vector_for_one_pair_removal_is_refused_by_another_of_the_same_length():
    """Guards against: the same with rule 2.4's per-pair removals: one match out of host 2's stack against one out of
    host 3's (equal length, different rows)."""
    d, q, regions, dd = make()
    frame = outcomes(dd=dd, noise=0.01)
    k2, k3 = (tuple(d.hosts.key.iloc[1]), int(d.hosts.cohort.iloc[1])), (tuple(d.hosts.key.iloc[2]), int(d.hosts.cohort.iloc[2]))
    b = pf.remove_pairs(d, {k2: {tuple(d.hosts.match_keys.iloc[1][0])}})
    c = pf.remove_pairs(d, {k3: {tuple(d.hosts.match_keys.iloc[2][0])}})
    yb = oa.outcome_vector(b, frame, "log_price")
    assert len(yb) == len(oa.stacked_rows(c))
    with pytest.raises(oa.OutcomeMisaligned, match="built for other rows"):
        oa.estimate(c, yb, validated_design=False, fuel_control=ps.GAS_SHARE)


def test_a_sliced_or_recomputed_vector_is_no_longer_certified_but_its_length_is_still_checked():
    """A view, a slice or arithmetic on a certified vector loses the certificate (it may no longer be the rows it was built
    for); a plain array is read with its length checked only, and the result says so."""
    d, q, regions, dd = make()
    y = oa.outcome_vector(d, outcomes(dd=dd, noise=0.01), "log_price")
    assert y.rows_signature is not None
    assert getattr(y[:-1], "rows_signature", None) is None and getattr(y + 0.0, "rows_signature", None) is None
    r = oa.estimate(d, np.asarray(y, dtype=float).copy(), validated_design=False, fuel_control=ps.GAS_SHARE)
    assert r["outcome_alignment"] == oa.ALIGNMENT_LENGTH_ONLY
    r = oa.estimate(d, y, validated_design=False, fuel_control=ps.GAS_SHARE)
    assert r["outcome_alignment"] == oa.ALIGNMENT_CHECKED


def test_a_condition_that_drops_a_not_classifiable_host_reads_the_same_rows_as_a_design_built_without_it():
    """Guards against: conditions.contrast slicing the outcome for its not-classifiable host out of order. The contrast with
    host 2 not classifiable equals the contrast on the design without host 2 and its own vector (to 1e-12)."""
    d, q, regions, dd = make()
    frame = outcomes(dd=dd, noise=0.01, state_sd=0.01)
    member = {"1:AA": True, "3:BA": False, "4:BC": True}
    g = cn.Grouping("test", "A", "B", member, {k: None for k in member}, "invented", kind="invented",
                    extra={"not_classifiable": {"2:AC": "invented"}})
    r = cn.contrast(d, oa.outcome_vector(d, frame, "log_price"), g)
    e = influence._without(d, np.array([True, False, True, True]))
    r2 = cn.contrast(e, oa.outcome_vector(e, frame, "log_price"),
                     cn.Grouping("test", "A", "B", member, {k: None for k in member}, "invented", kind="invented"),
                     fuel_control=ps.GAS_SHARE)
    assert r["estimable"] and abs(r["difference_log_points"] - r2["difference_log_points"]) < 1e-12


# ======================================================================================================================
# Trap 3: design rules after deletions
# ======================================================================================================================

def test_remove_pairs_keeps_the_rules_and_lists_the_design_was_built_under(world):
    """Guards against: the shared-supplier removal reporting a design without its rules, its unresolved-ownership
    limitation list or its load-unknown exclusions (design_facts reads them), and against the kernel guessing its fuel
    control. The support table is not carried: it describes the matches before the removal."""
    inp, w = world
    d = inp.build(ro.H2)
    first = tuple(d.hosts.match_keys.iloc[1][0])
    e = pf.remove_pairs(d, {(tuple(d.hosts.key.iloc[1]), int(d.hosts.cohort.iloc[1])): {first}})
    assert e.rules is d.rules
    assert e.unresolved_ownership == d.unresolved_ownership and e.load_unknown_excluded == d.load_unknown_excluded
    assert e.unknown_load_source == d.unknown_load_source and e.support_table is None
    facts = ro.design_facts(e)
    assert "unresolved_ownership" in facts and "load_unknown_excluded" in facts


def test_a_design_with_no_rules_and_no_named_fuel_control_stops_in_words():
    """Guards against: the kernel guessing the gas-share control for a design whose rules a deletion dropped. Under the
    categorical or no-fuel rules the design carries no gas shares, so the guess failed with a message about gas shares that
    named neither the lost rules nor the deletion; it now says what is missing."""
    treated, clean, q, regions, dd = __import__("test_outcome_analysis_invented").world()
    d = design.build(treated, clean, q, regions, FUEL, dd)
    d.gas = None
    with pytest.raises(ValueError, match="carries no rules"):
        oa.estimate(d, np.zeros(len(oa.stacked_rows(d))), validated_design=False)


def test_on_the_headline_rules_a_deletion_without_its_rules_gives_the_same_estimate(world):
    """No wrong estimate on the paths used: every deletion in the registry is on a design built under the headline rules,
    whose fuel control (gas share) was the kernel's fallback. The estimate with the rules carried equals it exactly."""
    inp, w = world
    d = inp.build(ro.H2)
    e = influence.leave_out(d, {tuple(d.hosts.match_keys.iloc[0][0])})
    frame = rw.outcome(w["dd"])
    y = oa.outcome_vector(e, frame, ro.OUTCOME)
    a = oa.estimate(e, y, validated_design=False, fuel_control=ps.GAS_SHARE)
    b = oa.estimate(ro.carry_design_attributes(d, e), y, validated_design=False)
    assert a["headline"] == b["headline"] and a["fuel_control"] == b["fuel_control"] == ps.GAS_SHARE


def test_deletions_on_a_design_under_other_rules_are_estimated_under_those_rules(world):
    """Guards against: rule 7's deletions on a design built under rules other than the headline rules (here the categorical
    fuel control in RunInputs.side) failing one by one, or being fitted under the gas-share control: influence.leave_out
    returns a design without `rules`. Before the repair every deletion was recorded as not computed."""
    inp, w = world
    s = inp.side
    cat = sr.Inputs(s.q, s.dose, s.regions, s.fuel, s.dd, ownership=s.ownership, usable=s.usable, gas=s.gas,
                    unknown_load=s.unknown_load, ownership_of=s.ownership_of, rules=ps.CATEGORICAL_FUEL)
    res = rw.one(ro.run("leave_one_comparison_out", ro.RunInputs(side=cat, sets=inp.sets), rw.outcome(w["dd"])))
    assert res["deletions_not_computed"] == []
    assert all(abs(x["estimate_log_points"] - 0.05) < TOL for x in res["deletions"])
    assert res["full_design"]["fuel_control"] == ps.CATEGORICAL


# ======================================================================================================================
# Trap 4: the 1% run's price hold and D-34 table
# ======================================================================================================================

def test_side_runs_every_cohort_at_takes_the_hold_and_the_history_and_reads_no_file(world, tmp_path, monkeypatch):
    """Session 19, first the trap (code as found): with no hold argument every_cohort_at read the file at
    power_simulation.PRICE_HOLD, so a listed unit left the invented pool without the caller passing anything. Now the
    history and the hold are required keywords: a file at PRICE_HOLD listing invented unit 101:AB changes nothing, and a
    call without them stops."""
    inp, w = world
    f = tmp_path / "price_hold.csv"
    f.write_text("utility_id_eia,state,name,why\n101,AB,invented,invented\n")
    monkeypatch.setattr(ps, "PRICE_HOLD", f)
    monkeypatch.setattr(uh, "load", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the D-34 table was read")))
    _, clean = sr.every_cohort_at(0.01, inp.side.q, inp.side.dose, history={}, hold=set())
    assert (101, "AB") in set(zip(clean.utility_id_eia, clean.state))
    with pytest.raises(TypeError):
        sr.every_cohort_at(0.01, inp.side.q, inp.side.dose, history={})
    with pytest.raises(ValueError, match="neither is read from a file"):
        sr.every_cohort_at(0.01, inp.side.q, inp.side.dose, history=None, hold=set())


def test_the_registrys_one_percent_set_takes_the_hold_and_the_d34_table_as_arguments_and_opens_no_file(world, monkeypatch):
    """Guards against: the 1% set built on invented inputs picking up the real price hold or D-34 table. The registry's
    builder requires both (no default), refuses None, and opens no file."""
    inp, w = world
    sig = inspect.signature(ro.every_cohort_utility_at).parameters
    assert sig["hold"].default is inspect.Parameter.empty and sig["d34_table"].default is inspect.Parameter.empty
    monkeypatch.setattr(ps, "price_hold", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the price hold file was read")))
    monkeypatch.setattr(uh, "load", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the D-34 table was read")))
    q, dose = inp.side.q, inp.side.dose
    t, c = ro.every_cohort_utility_at(0.01, q, dose, d34_table=pd.DataFrame(), hold={(101, "AB")})
    t0, c0 = ps.design(q, dose, 0.01, {}, hold={(101, "AB")})
    assert t.equals(t0) and c.equals(c0) and (101, "AB") not in set(zip(c.utility_id_eia, c.state))
    with pytest.raises(ro.MissingInput, match="price hold"):
        ro.every_cohort_utility_at(0.01, q, dose, d34_table=pd.DataFrame(), hold=None)
    with pytest.raises(ro.MissingInput, match="D-34"):
        ro.every_cohort_utility_at(0.01, q, dose, d34_table=None, hold=set())
