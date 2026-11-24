"""Joe's common-dose rule (2026-11-19) on invented histories, each test with a planted answer.

pipeline/analysis/common_dose_rule.py. Established only for a capped form, only where every history gives exactly the
same change, and only where the histories are complete or the bounds argument holds. Never for the uncapped form, never
from a narrow range. These tests read no file under data/: every state, history and extreme is built here. The
tolerance for each planted dose is exact equality (0.0), since the rule itself uses no tolerance.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import common_dose_rule as cdr  # noqa: E402

C25, C50, UNC = "capped_at_25_points", "capped_at_50_points", "uncapped"
COMPLETE = cdr.Completeness(True, "invented: every admissible history listed")
INCOMPLETE = cdr.Completeness(False, "invented: one question held at the reference", ("site x date: held at 2022",))
PLANTED_25, PLANTED_50 = 25.0, 50.0
YEARS = list(range(2001, 2026))


# ---- the rule on histories --------------------------------------------------------------------------------------

def test_complete_and_common_at_a_capped_form_is_established_at_the_planted_dose():
    ch = {C25: np.full(12, PLANTED_25), C50: np.full(12, PLANTED_50)}
    v = cdr.apply_rule(ch, completeness=COMPLETE, bounds=None)
    assert v[C25]["established"] and v[C25]["dose"] == PLANTED_25          # tolerance 0
    assert v[C50]["established"] and v[C50]["dose"] == PLANTED_50


def test_complete_and_not_common_is_not_established():
    ch = {C25: np.array([25.0, 25.0, 18.0, 25.0])}
    v = cdr.apply_rule(ch, completeness=COMPLETE, bounds=None)
    assert not v[C25]["established"] and v[C25]["dose"] is None
    assert "not common" in v[C25]["why"] and "18" in v[C25]["why"]


def test_a_narrow_range_is_not_a_common_dose():
    ch = {C25: np.array([25.0, 25.0 - 1e-12])}
    v = cdr.apply_rule(ch, completeness=COMPLETE, bounds=None)
    assert not v[C25]["established"] and v[C25]["dose"] is None


def test_common_but_not_complete_is_not_established_and_names_the_gap():
    ch = {C25: np.full(6, PLANTED_25)}
    v = cdr.apply_rule(ch, completeness=INCOMPLETE, bounds=None)
    assert not v[C25]["established"] and v[C25]["dose"] is None
    assert "site x date: held at 2022" in v[C25]["why"] and "no bounds argument" in v[C25]["why"]


def test_no_statement_of_completeness_is_not_completeness():
    v = cdr.apply_rule({C25: np.full(3, PLANTED_25)}, completeness=None, bounds=None)
    assert not v[C25]["established"] and "no statement of completeness" in v[C25]["why"]


def test_common_at_25_and_not_at_50():
    ch = {C25: np.full(4, PLANTED_25), C50: np.array([50.0, 41.0, 50.0, 47.5])}
    v = cdr.apply_rule(ch, completeness=COMPLETE, bounds=None)
    assert v[C25]["established"] and v[C25]["dose"] == PLANTED_25
    assert not v[C50]["established"] and v[C50]["dose"] is None


def test_uncapped_is_never_established_by_the_exception():
    ch = {UNC: np.full(5, 700.0), C25: np.full(5, PLANTED_25)}
    holds = cdr.BoundsResult(UNC, True, 700.0, (), (), "invented")
    v = cdr.apply_rule(ch, completeness=COMPLETE, bounds={UNC: holds})
    assert not v[UNC]["established"] and v[UNC]["dose"] is None and "capped form only" in v[UNC]["why"]
    assert v[C25]["established"]


def test_both_keywords_are_required():
    with pytest.raises(TypeError):
        cdr.apply_rule({C25: np.full(2, 25.0)})                              # noqa: the missing keywords are the point


# ---- the bounds argument ----------------------------------------------------------------------------------------

def _extremes(pre_lo, pre_hi, post_lo, post_hi):
    lo = dict(zip((2008, 2009, 2010, 2023, 2024, 2025), pre_lo + post_lo))
    hi = dict(zip((2008, 2009, 2010, 2023, 2024, 2025), pre_hi + post_hi))
    return lo, hi


def test_bounds_argument_holds_and_establishes_with_no_enumeration():
    lo, hi = _extremes([0, 0, 0], [0, 0, 0], [60.0, 80.0, 95.0], [900.0, 1000.0, 1100.0])
    b25 = cdr.bounds_from_extremes(lo, hi, label=C25)
    b50 = cdr.bounds_from_extremes(lo, hi, label=C50)
    assert b25.holds and b25.dose == PLANTED_25 and b50.holds and b50.dose == PLANTED_50
    v = cdr.apply_rule({}, completeness=INCOMPLETE, bounds={C25: b25, C50: b50})
    assert v[C25]["established"] and v[C25]["dose"] == PLANTED_25
    assert v[C50]["established"] and v[C50]["dose"] == PLANTED_50


def test_bounds_with_every_year_at_the_cap_give_a_common_zero():
    lo, hi = _extremes([30.0, 30.0, 30.0], [80.0, 80.0, 80.0], [60.0, 80.0, 95.0], [900.0, 1000.0, 1100.0])
    b = cdr.bounds_from_extremes(lo, hi, label=C25)
    assert b.holds and b.dose == 0.0


def test_bounds_argument_fails_at_a_named_step():
    # 2009 can carry up to 12 points in some history and nothing in another: undecided, 25 short at its least
    lo, hi = _extremes([0, 0, 0], [0, 12.0, 0], [60.0, 80.0, 95.0], [900.0, 1000.0, 1100.0])
    b = cdr.bounds_from_extremes(lo, hi, label=C25)
    assert not b.holds and b.dose is None and len(b.failed) == 1
    assert "before year 2009" in b.failed[0] and "12" in b.failed[0] and "25 short" in b.failed[0]
    v = cdr.apply_rule({C25: np.full(9, PLANTED_25)}, completeness=INCOMPLETE, bounds={C25: b})
    assert not v[C25]["established"] and "before year 2009" in v[C25]["why"]


def test_bounds_argument_fails_in_an_after_year_short_of_the_cap():
    lo, hi = _extremes([0, 0, 0], [0, 0, 0], [60.0, 40.0, 95.0], [900.0, 1000.0, 1100.0])
    assert cdr.bounds_from_extremes(lo, hi, label=C25).holds
    b50 = cdr.bounds_from_extremes(lo, hi, label=C50)
    assert not b50.holds and len(b50.failed) == 1 and "after year 2024" in b50.failed[0] and "10 short" in b50.failed[0]


def test_bounds_and_histories_that_disagree_establish_nothing():
    lo, hi = _extremes([0, 0, 0], [0, 0, 0], [60.0, 80.0, 95.0], [900.0, 1000.0, 1100.0])
    b = cdr.bounds_from_extremes(lo, hi, label=C25)
    v = cdr.apply_rule({C25: np.full(3, 20.0)}, completeness=INCOMPLETE, bounds={C25: b})
    assert not v[C25]["established"] and "disagree" in v[C25]["why"]


# ---- the extremes from an invented state --------------------------------------------------------------------------

def _ramp(mw, start):
    return np.array([0.0 if y < start else mw * min(1.0, (y - start + 1) / 3) for y in YEARS])


def _state(starts_a):
    """One utility k = (1, "ZZ") with two permit sites: A (100 MW raw) with a date question whose settings are
    `starts_a`, and B (50 MW raw, no question, starting 2020) on k. A third site C on another utility. Nothing measured."""
    k = (1, "ZZ")
    q_a = SimpleNamespace(fid="A", name="date", values=list(starts_a), default=len(starts_a) - 1)
    A = SimpleNamespace(fid="A", kind="permit", unit=[k] * len(starts_a),
                        load=np.vstack([_ramp(100.0, s) for s in starts_a]), a=np.full(len(starts_a), 0.876),
                        na_div=(1.0, 1.0), idx=np.arange(len(starts_a)).reshape(-1, 1), questions=["date"])
    B = SimpleNamespace(fid="B", kind="permit", unit=[k], load=_ramp(50.0, 2020)[None, :], a=np.array([0.438]),
                        na_div=(1.0, 1.0), idx=np.zeros((1, 0), dtype=int), questions=[])
    C = SimpleNamespace(fid="C", kind="permit", unit=[(2, "ZZ")], load=_ramp(500.0, 2001)[None, :], a=np.array([4.38]),
                        na_div=(1.0, 1.0), idx=np.zeros((1, 0), dtype=int), questions=[])
    return SimpleNamespace(sites=[A, B, C], site_qids=[[0], [], []], qs=[q_a], m0=0.0, frozen=0.5), k


def test_load_extremes_on_an_invented_state_make_the_argument_hold():
    S, k = _state([2015, 2016])
    rows = cdr.allowed_rows(S, free_qids=[0], fixed_options={})
    ext = cdr.load_extremes(S, k, 100.0, rows, scale_lo=0.2, scale_hi=3.0, factor_tol=1e-12,
                            years=[2008, 2009, 2010, 2023, 2024, 2025])
    # least after-year load: 0.2 x (100 + 50) MW x 8.76 / 100 GWh x 100 = 262.8 points; before years zero
    assert ext["clip"][0][3] == pytest.approx(262.8, abs=1e-9) and ext["clip"][1][:3] == [0.0, 0.0, 0.0]
    b = cdr.bounds_argument(ext, label=C50)
    assert b.holds and b.dose == PLANTED_50


def test_load_extremes_on_an_invented_state_fail_where_a_start_reaches_the_before_period():
    S, k = _state([2005, 2015, 2016])
    rows = cdr.allowed_rows(S, free_qids=[0], fixed_options={})
    ext = cdr.load_extremes(S, k, 100.0, rows, scale_lo=0.2, scale_hi=3.0, factor_tol=1e-12,
                            years=[2008, 2009, 2010, 2023, 2024, 2025])
    b = cdr.bounds_argument(ext, label=C25)
    assert not b.holds and [s.year for s in b.steps if s.value is None] == [2008, 2009, 2010]
    # held at the reference (the last setting, 2016) the same state has no before-period load: the scope decides
    rows_ref = cdr.allowed_rows(S, free_qids=[], fixed_options={})
    ext_ref = cdr.load_extremes(S, k, 100.0, rows_ref, scale_lo=0.2, scale_hi=3.0, factor_tol=1e-12,
                                years=[2008, 2009, 2010, 2023, 2024, 2025])
    assert cdr.bounds_argument(ext_ref, label=C25).holds


# ---- admissible settings and coverage ----------------------------------------------------------------------------

def test_admissible_settings_from_the_entry():
    open_below = {"kind": "date", "earliest": None, "latest": 2006, "never_is_possible": False}
    assert cdr.admissible_settings(open_below, first_year=2001, last_year=2025, ramp_years=3) == list(range(1999, 2007))
    open_above = {"kind": "date", "earliest": 2024, "latest": None, "never_is_possible": True}
    assert cdr.admissible_settings(open_above, first_year=2001, last_year=2025, ramp_years=3) == [2024, 2025, 2026, "never"]
    split = {"kind": "capacity_split", "rest_earliest": 2011}
    assert cdr.admissible_settings(split, first_year=2001, last_year=2025, ramp_years=3, inventory_year=2014) == [2011, 2012, 2013, 2014]


def _qs():
    return [SimpleNamespace(fid="U", name="date", values=[2024, 2025, 2026], default=0),           # "never" left out
            SimpleNamespace(fid="H", name="date", values=[2010, 2015, 2020], default=2),           # held at 2020
            SimpleNamespace(fid="G", name="assignment", values=[1, 7, None], default=0)]           # on k=1, candidate 7


def test_coverage_finds_a_missing_admissible_setting_and_a_held_question():
    qs = _qs()
    adm = {("U", "date"): [2024, 2025, 2026, "never"]}
    cases = cdr.rule4_cases(qs, 1)
    assert cases == {"as_assigned": {}, "lower": {2: 2}, "upper": {}}
    cov = cdr.coverage_check(qs, k_id=1, unknown_fids=["U"], varied_qids=[0], case_settings=cases,
                             relevant=[(1, [[0], [1], [2]]), (2, [[0], [1, 2]])], admissible=adm, histories=2 * 3 * 3)
    assert not cov["scope"]["rule_8_1_text"]["complete"]
    assert any("missing ['never']" in g for g in cov["scope"]["rule_8_1_text"]["gaps"])
    held = {h["site"]: h for h in cov["relevant_questions_not_varied"]}
    assert held["H"]["classes_not_reached"] == [[2010], [2015]] and held["G"]["classes_not_reached"] == []


def test_coverage_complete_in_the_narrow_scope_only():
    qs = _qs()
    qs[0].values = [2024, 2025, 2026, "never"]
    adm = {("U", "date"): [2024, 2025, 2026, "never"]}
    cov = cdr.coverage_check(qs, k_id=1, unknown_fids=["U"], varied_qids=[0], case_settings=cdr.rule4_cases(qs, 1),
                             relevant=[(0, [[0], [1], [2, 3]]), (1, [[0], [1], [2]])], admissible=adm, histories=2 * 3 * 4,
                             wider_set_gaps=["screen held at shift 0"])
    assert cov["scope"]["rule_8_1_text"]["complete"]
    assert not cov["scope"]["place_test_wider_set"]["complete"]
    assert "screen held at shift 0" in cov["scope"]["place_test_wider_set"]["gaps"]
    assert cdr.completeness_for(cov, "rule_8_1_text").complete
    assert not cdr.completeness_for(cov, "place_test_wider_set").complete


def test_coverage_flags_a_wrong_case_and_a_wrong_count():
    qs = _qs()
    qs[0].values = [2024, 2025, 2026, "never"]
    adm = {("U", "date"): [2024, 2025, 2026, "never"]}
    cov = cdr.coverage_check(qs, k_id=1, unknown_fids=["U"], varied_qids=[0],
                             case_settings={"as_assigned": {}, "lower": {}, "upper": {}}, relevant=[],
                             admissible=adm, histories=10)
    gaps = cov["scope"]["rule_8_1_text"]["gaps"]
    assert any("'lower'" in g for g in gaps) and any("10 histories returned, 24 expected" in g for g in gaps)


# ---- witnesses and the scope ---------------------------------------------------------------------------------------

def test_witness_changes_evaluate_single_configurations():
    calls = []

    def grid(k, axes):
        calls.append(axes)
        x = np.zeros((1, len(YEARS)))
        x[0, YEARS.index(2023):] = 40.0                       # 40 GWh on a 100 GWh base: 40 points after
        if axes[0][1][0] == 0:
            x[0, YEARS.index(2008):YEARS.index(2011)] = 30.0  # the earliest setting also loads the before period
        return x, x * 2.0, (1,)
    S = SimpleNamespace(grid=grid, qs=[SimpleNamespace(fid="W", name="date", values=[1999, 2019])])

    def change(x, n_pre, cap=None):
        xc = x if cap is None else np.minimum(x, cap)
        return xc[:, n_pre:].mean(1) - xc[:, :n_pre].mean(1)
    ch, desc = cdr.witness_changes(S, (1, "ZZ"), 100.0, [{0: 0}, {0: 1}], caps=(25.0,), change_fn=change,
                                   cap_label_fn=lambda c: f"capped_at_{c:.0f}_points")
    assert [a for a in calls] == [[(0, [0])], [(0, [1])]]
    assert list(ch[C25]) == [0.0, 0.0, 25.0, 25.0] and desc == [{"W date": 1999}, {"W date": 2019}]
    v = cdr.apply_rule(ch, completeness=INCOMPLETE, bounds=None)
    assert not v[C25]["established"] and "not common" in v[C25]["why"]


def test_the_scope_has_no_default_and_is_checked_before_anything_is_read():
    with pytest.raises(TypeError):
        cdr.oregon_verdicts()                                               # noqa: the missing scope is the point
    with pytest.raises(ValueError):
        cdr.oregon_verdicts("everything")


# ---- established only under every scope (invented verdicts) ------------------------------------------------------

def _v(est, dose, why):
    return {"established": est, "dose": dose, "why": why}


def _by_scope(narrow, wide):
    return {"rule_8_1_text": {"9:XX": narrow}, "place_test_wider_set": {"9:XX": wide}}


def check_scopes_that_differ_are_not_established():
    r = cdr.established_under_every_scope(_by_scope({C25: _v(True, 25.0, "narrow ok")},
                                                    {C25: _v(False, None, "0.0 in one configuration")}))["9:XX"][C25]
    assert not r["established"] and r["dose"] is None
    assert "established at 25.0 under rule 8.1's own histories (narrow ok)" in r["why"]
    assert "not established under the place test's wider set (0.0 in one configuration)" in r["why"]
    assert "D-107" in r["why"] and "exclusion is retained" in r["why"]
    assert "choice of scope is Joe's" not in r["why"] and "meanwhile" not in r["why"]      # ruled, no longer open


def test_scopes_that_agree_establish_the_planted_dose():
    r = cdr.established_under_every_scope(_by_scope({C25: _v(True, 25.0, "a"), C50: _v(False, None, "b")},
                                                    {C25: _v(True, 25.0, "c"), C50: _v(False, None, "d")}))["9:XX"]
    assert r[C25]["established"] and r[C25]["dose"] == PLANTED_25                 # tolerance 0
    assert not r[C50]["established"] and "not established under any scope" in r[C50]["why"]


def test_scopes_that_differ_are_not_established():
    check_scopes_that_differ_are_not_established()


def test_doses_that_differ_between_scopes_are_not_established():
    r = cdr.established_under_every_scope(_by_scope({C25: _v(True, 25.0, "a")}, {C25: _v(True, 24.0, "b")}))["9:XX"][C25]
    assert not r["established"] and r["dose"] is None and "established at 24.0 under the place test's" in r["why"]


def test_a_missing_scope_is_refused():
    with pytest.raises(ValueError, match="missing"):
        cdr.established_under_every_scope({"rule_8_1_text": {"9:XX": {C25: _v(True, 25.0, "a")}}})
    with pytest.raises(ValueError, match="different forms"):
        cdr.established_under_every_scope(_by_scope({C25: _v(True, 25.0, "a")}, {C50: _v(True, 50.0, "b")}))


# ---- Joe's ruling (D-107, 2026-11-19): the wider admissible histories govern ---------------------------------------

def check_the_ruled_scope_is_applied():
    """Planted: the narrow scope establishes 25.0 and the wider one finds a counterexample (Umatilla's case), so the
    mapping applied is not established; where only the wider scope establishes, its planted dose is applied."""
    r = cdr.established_as_ruled(_by_scope({C25: _v(True, 25.0, "narrow ok"), C50: _v(False, None, "n50")},
                                           {C25: _v(False, None, "0.0 in one configuration"),
                                            C50: _v(True, 50.0, "w50")}))["9:XX"]
    assert not r[C25]["established"] and r[C25]["dose"] is None
    assert "D-107" in r[C25]["why"] and "Under the place test's wider set: 0.0 in one configuration" in r[C25]["why"]
    assert "recorded beside it, not applied, under rule 8.1's own histories: established at 25.0 (narrow ok)" in r[C25]["why"]
    assert r[C50]["established"] and r[C50]["dose"] == PLANTED_50                       # tolerance 0
    assert "not established (n50)" in r[C50]["why"]


def test_the_ruled_scope_is_the_wider_set_and_is_applied():
    assert cdr.RULED_SCOPE == "place_test_wider_set" and cdr.RULED_SCOPE in cdr.SCOPES
    check_the_ruled_scope_is_applied()


def test_the_ruled_mapping_needs_both_scopes_on_record():
    with pytest.raises(ValueError, match="both stay on record"):
        cdr.established_as_ruled({"place_test_wider_set": {"9:XX": {C25: _v(False, None, "w")}}})
    with pytest.raises(ValueError, match="different forms"):
        cdr.established_as_ruled(_by_scope({C25: _v(True, 25.0, "a")}, {C50: _v(True, 50.0, "b")}))


def test_no_string_of_the_module_says_the_scope_is_open():
    src = (ROOT / "pipeline" / "analysis" / "common_dose_rule.py").read_text()
    for phrase in ("choice of scope is Joe's", "is Joe's to choose", "until he makes it", "meanwhile", "Joe's to decide"):
        assert phrase not in src, phrase
    with pytest.raises(ValueError, match="D-107"):
        cdr.oregon_verdicts("everything")


def test_the_ruled_scope_check_can_fail(monkeypatch):
    """A deliberate break in the test process: the narrow scope applied instead of the ruled one."""
    monkeypatch.setattr(cdr, "RULED_SCOPE", "rule_8_1_text")
    with pytest.raises(AssertionError):
        check_the_ruled_scope_is_applied()


def test_the_disagreement_check_can_fail(monkeypatch):
    """A deliberate break in the test process: verdicts that never retain the exclusion."""
    monkeypatch.setattr(cdr, "_verdict", lambda est, dose, why: {"established": True, "dose": dose, "why": why})
    with pytest.raises(AssertionError):
        check_scopes_that_differ_are_not_established()
