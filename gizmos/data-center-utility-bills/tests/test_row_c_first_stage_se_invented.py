"""Row C's first-stage standard error, reported in words (session 28; Joe, 2026-11-20, D-122). Invented inputs only.

His answer: "Report it in words (Recommended)", to an option that read: "A reporting-only repair, tested on invented
inputs: the value stays as computed and a failure in words is added to the step. No estimate, sample or inference rule
changes." And his technical note of the same day, unchanged: "zero variance produces a zero standard error; negative
variance produces NaN."

Every world here is invented, in tests/test_reconciliation_c_invented.py (its `world`) or in
tests/test_run_outcomes_invented.py (its `build_world`), whose helpers are imported and not changed. No file under data/
is read and nothing is written.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_reconciliation_c_invented as w  # noqa: E402  read-only use of its invented world

from pipeline.analysis import execute_outcomes as eo  # noqa: E402
from pipeline.analysis import reconciliation_c as rc  # noqa: E402

REAL_IV_FIT = rc.iv_fit


# ---- the words, as a pure function of the variance's diagonal ---------------------------------------------------------------

def test_a_positive_variance_has_no_words():
    assert rc.first_stage_se_in_words([0.04]) is None
    assert rc.first_stage_se_in_words(np.array([1e-300, 2.0, 1e300])) is None
    assert rc.first_stage_se_in_words([]) is None


def test_a_zero_variance_gives_a_zero_standard_error_which_is_a_number_and_is_not_reported():
    """His note: "zero variance produces a zero standard error"."""
    d = np.array([0.0])
    assert np.sqrt(d)[0] == 0.0 and not np.isnan(np.sqrt(d)[0])
    assert rc.first_stage_se_in_words(d) is None
    assert rc.first_stage_se_in_words(np.array([-0.0, 0.0, 3.0])) is None       # minus zero is zero: its root is a number
    assert not np.isnan(np.sqrt(np.array([-0.0]))[0])


def test_a_negative_variance_gives_a_standard_error_that_is_not_a_number_and_is_reported_in_words():
    """His note: "negative variance produces NaN"."""
    d = np.array([-1e-18])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        assert np.isnan(np.sqrt(d)[0])
    words = rc.first_stage_se_in_words(d)
    assert words and "is not a number for 1 of the 1 excluded-instrument coefficients" in words
    assert "negative for 1 and not finite for 0" in words and "left as computed" in words
    assert "1e-18" not in words and "e-18" not in words                         # counts, never the variance itself


@pytest.mark.parametrize("bad,neg,nonfinite", [([np.nan], 0, 1), ([np.inf], 0, 1), ([-np.inf], 0, 1),
                                               ([-2.0, np.nan, 4.0, 0.0], 1, 1)])
def test_a_variance_that_is_not_finite_is_reported_in_words_with_counts(bad, neg, nonfinite):
    words = rc.first_stage_se_in_words(bad)
    assert f"is not a number for {neg + nonfinite} of the {len(bad)} excluded-instrument coefficients" in words
    assert f"negative for {neg} and not finite for {nonfinite}" in words


def test_the_words_are_given_exactly_where_the_computed_standard_error_is_not_a_number():
    rng = np.random.default_rng(28)
    for _ in range(200):
        d = rng.choice([-1.0, -1e-30, -0.0, 0.0, 1e-30, 1.0, np.nan, np.inf, -np.inf], size=int(rng.integers(1, 4)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            se = np.sqrt(d)
        # +inf has a square root that is a number (infinite); it is still reported, as a variance that is not finite
        assert (rc.first_stage_se_in_words(d) is not None) == bool(np.isnan(se).any() or np.isinf(d).any())


# ---- the fit and the step: the value stays as computed, and nothing else moves -------------------------------------------------

def _matrices():
    out, reg, share, sp, _own = w.world(seed=3, share_mult=4.0)
    f, g1, g2 = w.transformed(out, reg, share, sp)
    return (out, reg, share, sp), (rc.within(f[["y", "d", "z"]].to_numpy(float), g1, g2), g1, g2)


def test_an_ordinary_fit_keeps_its_first_stage_standard_error_and_has_no_words():
    _frames, (M, g1, g2) = _matrices()
    kabs = rc.absorbed_df_not_nested(g1, g2)
    fit = rc.iv_fit(M[:, 0], M[:, 1:2], M[:, 2:3], g1, "cr1_stata", kabs)
    fs = rc.iv_fit(M[:, 1], M[:, 2:3], None, g1, "cr1_stata", kabs)
    assert fit.first_stage_se_failure is None
    assert np.isfinite(fit.first_stage_se).all() and fit.first_stage_se[0] == pytest.approx(fs.se[0], rel=1e-12)
    ols = rc.iv_fit(M[:, 0], M[:, 1:2], None, g1, "cr1_stata", kabs)
    assert ols.first_stage_se is None and ols.first_stage_se_failure is None


def _first_stage_variance(value):
    """iv_fit with the first stage's cluster-robust variance replaced by `value`, in this process only. The first stage
    is the fit's own inner call (no endogenous regressor, the instruments as W); every other call is untouched."""
    def patched(y, X, Z, cluster, small_sample, k_absorbed, W=None):
        fit = REAL_IV_FIT(y, X, Z, cluster, small_sample, k_absorbed, W=W)
        if Z is None and W is not None and np.asarray(X).reshape(len(y), -1).shape[1] == 0:
            fit.vcov = np.full_like(fit.vcov, 0.0)
            np.fill_diagonal(fit.vcov, value)
        return fit
    return patched


def test_a_negative_first_stage_variance_is_reported_in_the_step_and_nothing_else_changes(monkeypatch):
    (out, reg, share, sp), _m = _matrices()
    args = ("C1u", "", out, reg, share, sp, "paper", w.CH, None, True, None, None)
    clean = rc.run_step(*args)
    assert clean.failure is None and "first_stage_se_failure" not in clean.extra and clean.extra == {}
    monkeypatch.setattr(rc, "iv_fit", _first_stage_variance(-1e-12))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        r = rc.run_step(*args)
    assert any("invalid value encountered in sqrt" in str(c.message) for c in caught)   # the value is as computed
    words = r.extra["first_stage_se_failure"]
    assert words.startswith("C1u: the first-stage standard error is not a number for 1 of the 1")
    assert "negative for 1 and not finite for 0" in words
    # a reporting-only repair: the step is estimated, and no estimate, sample or inference figure moves
    assert r.failure is None
    assert (r.estimate, r.se, r.n_obs, r.n_units, r.singleton_rows_dropped) == \
        (clean.estimate, clean.se, clean.n_obs, clean.n_units, clean.singleton_rows_dropped)
    assert r.first_stage_coef == clean.first_stage_coef and r.accounting == clean.accounting and r.caps == clean.caps
    assert r.first_stage_f < 0                                 # from the same variance, left as computed and not replaced
    d = r.as_dict()
    assert d["extra"] == {"first_stage_se_failure": words} and d["failure"] is None
    # the registry counts a step as failed by its `failure` field alone, so this step still counts as computed
    assert not [x for x in [d] if x.get("failure")]
    assert isinstance(d["estimate"], float) and np.isfinite(d["estimate"])
    # and the coordinator's plain-text report lists the words with the failures in words
    found = eo._failures({"steps": [d]})
    assert found == [("steps[0].extra.first_stage_se_failure", words)]


def test_the_fit_itself_carries_the_value_as_computed_and_the_words(monkeypatch):
    _frames, (M, g1, g2) = _matrices()
    kabs = rc.absorbed_df_not_nested(g1, g2)
    clean = rc.iv_fit(M[:, 0], M[:, 1:2], M[:, 2:3], g1, "cr1_stata", kabs)
    monkeypatch.setattr(rc, "iv_fit", _first_stage_variance(-4.0))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        fit = REAL_IV_FIT(M[:, 0], M[:, 1:2], M[:, 2:3], g1, "cr1_stata", kabs)
    assert np.isnan(fit.first_stage_se).all() and fit.first_stage_se_failure
    assert np.array_equal(fit.coef, clean.coef) and np.array_equal(fit.vcov, clean.vcov)
    assert np.array_equal(fit.first_stage_coef, clean.first_stage_coef)


def test_a_zero_first_stage_variance_is_the_existing_numerical_failure_and_not_this_report(monkeypatch):
    """With one instrument a zero variance is singular, so the first-stage F cannot be computed and the step stops in
    the words it already had (the singular-variance failure, session 21). The standard error's line is never reached,
    and nothing here reports a zero as not a number."""
    (out, reg, share, sp), _m = _matrices()
    monkeypatch.setattr(rc, "iv_fit", _first_stage_variance(0.0))
    r = rc.run_step("C1u", "", out, reg, share, sp, "paper", w.CH, None, True, None, None)
    assert r.failure and "singular" in r.failure and "first_stage_se_failure" not in r.extra


def test_the_conditional_f_tells_its_caller_and_returns_the_same_numbers(monkeypatch):
    out, reg, share, sp, own = w.world(seed=5, own_beta={True: 0.1, False: 0.4}, share_mult=4.0)
    f, g1, g2 = w.transformed(out, reg, share, sp)
    other = np.array([own[u] != "investor_owned" for u in zip(f.utility_id_eia, f.state)], dtype=float)
    f = f.assign(d_other=f.d * other, z_other=f.z * other)
    M = rc.within(f[["y", "d", "d_other", "z", "z_other"]].to_numpy(float), g1, g2)
    kabs = rc.absorbed_df_not_nested(g1, g2)
    plain = rc.sw_conditional_f(M[:, 1:3], M[:, 3:5], g1, "cr1_stata", kabs)
    notes = []
    assert rc.sw_conditional_f(M[:, 1:3], M[:, 3:5], g1, "cr1_stata", kabs, notes=notes) == plain and notes == []

    def patched(y, X, Z, cluster, small_sample, k_absorbed, W=None):       # the helper fits report a failure in words
        fit = REAL_IV_FIT(y, X, Z, cluster, small_sample, k_absorbed, W=W)
        if Z is not None:
            fit.first_stage_se_failure = "invented words"
        return fit
    monkeypatch.setattr(rc, "iv_fit", patched)
    notes = []
    assert rc.sw_conditional_f(M[:, 1:3], M[:, 3:5], g1, "cr1_stata", kabs, notes=notes) == plain
    assert notes == ["in the helper fit for endogenous regressor 1 of 2, invented words",
                     "in the helper fit for endogenous regressor 2 of 2, invented words"]
    assert rc.sw_conditional_f(M[:, 1:3], M[:, 3:5], g1, "cr1_stata", kabs) == plain       # with no list, nothing changes
    split = rc.ownership_split("C1", out, reg, share, sp, "paper", w.CH, None, own)
    assert split["failure"] is None and split["first_stage_se_failure"].startswith("C1, interaction, inside Sanderson")
    assert split["first_stage_se_failure"].count("invented words") == 2
    monkeypatch.setattr(rc, "iv_fit", REAL_IV_FIT)
    clean = rc.ownership_split("C1", out, reg, share, sp, "paper", w.CH, None, own)
    assert "first_stage_se_failure" not in clean
    assert {k: v for k, v in split.items() if k != "first_stage_se_failure"} == clean      # no figure of the step moves


# ---- the invented world of the registry, where the suite showed the warning ----------------------------------------------------

def _row_c_records(x, out=None):
    """Every record of row C inside the registry's result, at any depth: a mapping that holds the row's `steps` list and
    the registry's `steps_with_a_failure`."""
    out = [] if out is None else out
    if isinstance(x, dict):
        if isinstance(x.get("steps"), list) and "steps_with_a_failure" in x:
            out.append(x)
        for v in x.values():
            _row_c_records(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _row_c_records(v, out)
    return out


@pytest.fixture(scope="module")
def registry_world():
    import test_run_outcomes_invented as rw                      # read-only use of its helpers
    inputs, aux = rw.build_world()
    return rw, inputs, aux


def test_on_the_registrys_invented_world_every_step_with_such_a_standard_error_says_so(registry_world, monkeypatch):
    rw, inputs, aux = registry_world
    from pipeline.analysis import run_outcomes as ro
    seen = []

    def spy(y, X, Z, cluster, small_sample, k_absorbed, W=None):
        fit = REAL_IV_FIT(y, X, Z, cluster, small_sample, k_absorbed, W=W)
        if Z is not None and fit.first_stage_se is not None:
            seen.append((bool(np.isnan(fit.first_stage_se).any()), fit.first_stage_se_failure))
        return fit
    monkeypatch.setattr(rc, "iv_fit", spy)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        res = ro.run("reconciliation_row_C", inputs, rw.all_outcomes(rw.outcome(aux["dd"])))
    assert seen and all((words is not None) == nan for nan, words in seen)
    # not vacuous: this world does give a first-stage variance below zero, which is where the suite showed the warning
    assert sum(nan for nan, _words in seen) >= 1
    rows = _row_c_records(res)
    assert rows
    steps = [s for r in rows for s in r["steps"]]
    # in a step's own fit (C1 to C4) the words are under `extra`; inside the ownership split's conditional F, where the
    # standard error is a by-product nothing reads, they are on the split's record, one note for each such helper fit
    own = [s for s in steps if isinstance(s.get("extra"), dict) and s["extra"].get("first_stage_se_failure")]
    split = [s for s in steps if isinstance(s.get("first_stage_se_failure"), str)]
    notes = sum(s["first_stage_se_failure"].count("in the helper fit for endogenous regressor") for s in split)
    assert len(own) + notes == sum(nan for nan, _words in seen)
    said = own + split
    for s in own:
        assert s["failure"] is None and s["extra"]["first_stage_se_failure"].startswith(f"{s['step']}: ")
        assert isinstance(s["estimate"], float) and np.isfinite(s["estimate"])
    for s in split:
        assert s["first_stage_se_failure"].startswith(f"{s['step']}, interaction, inside Sanderson and Windmeijer")
        assert "nothing in this step reads" in s["first_stage_se_failure"] and s.get("failure") is None
        assert np.isfinite(s["investor_owned"]["estimate"]) and np.isfinite(s["all_other"]["estimate"])
    for r in rows:
        assert r["estimated"] is True
        assert not [x for x in r["steps_with_a_failure"] if "first-stage standard error" in str(x.get("failure_in_words"))]
    # the coordinator's report lists the words with the failures in words, whatever the depth of the row's record
    listed = [words for _where, words in eo._failures(res) if "first-stage standard error is not a number" in words]
    assert len(listed) == len(said)
