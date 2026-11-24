"""Date errors in the power simulation, on invented inputs only: the planted path, how errors reach what is stacked and
estimated, how they are drawn, and how the draws are read. No file under data/ is read.

Sign convention (pipeline/analysis/misdating.py, crossing_errors): an error is the true first crossing minus the recorded
one, so a negative error is a true crossing EARLIER than recorded. The window is recorded event years -6 to +3, the
reference year is -3 and the headline is the mean of event years 2 and 3 (power_simulation PRE, POST, REF, HEADLINE).

By planted_path, the share of a planted effect the headline keeps is: 1 for errors 0, -1 and -2; 5/6 for +1; 1/2 for
+2; 2/3 for -3 (the reference year is contaminated); 0 for an error of 60 ("never" after draw_errors' mapping). The tests
below check that table on the function and check that a cost-free error (-1) is still applied, which a headline reading
alone cannot show.
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import estimator as es  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
COHORT = 2012
STATES = ("OH", "PA", "VA", "IN", "MI", "WI")
GAS = {"OH": 0.05, "PA": 0.20, "VA": 0.35, "IN": 0.10, "MI": 0.25, "WI": 0.40}     # invented 2008-2010 gas shares
FIVE = ps.TAUS_PCT.index(5)
T5 = float(np.log1p(0.05))
ALL_SHIFTS = (-3, -2, -1, 0, 1, 2, 60)
COST_FREE = (-2, -1, 0)

# The headline's share of a planted effect under each error, worked out by hand from planted_path (module docstring).
HEADLINE_KEEPS = {-3: Fraction(2, 3), -2: Fraction(1), -1: Fraction(1), 0: Fraction(1), 1: Fraction(5, 6),
                  2: Fraction(1, 2), 60: Fraction(0)}

# The whole path over window indices 0 to 9 (event years -6 to +3), written out by hand, not from the formula.
t, d = 1 / 3, 2 / 3
PATHS = {
    -3: [0, 0, 0, t, d, 1, 1, 1, 1, 1],
    -2: [0, 0, 0, 0, t, d, 1, 1, 1, 1],
    -1: [0, 0, 0, 0, 0, t, d, 1, 1, 1],
    0: [0, 0, 0, 0, 0, 0, t, d, 1, 1],
    1: [0, 0, 0, 0, 0, 0, 0, t, d, 1],
    2: [0, 0, 0, 0, 0, 0, 0, 0, t, d],
    60: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
}


def idx(event_year: int) -> int:
    """Window index of a recorded event year."""
    return event_year + ps.PRE


def headline_minus_reference(path) -> float:
    """What the headline reads of a unit path: the mean of event years 2 and 3 less the reference year."""
    path = np.asarray(path, dtype=float)
    return float(np.mean([path[idx(e)] for e in ps.HEADLINE]) - path[idx(ps.REF)])


def test_the_window_is_the_one_these_tests_assume():
    assert (ps.PRE, ps.POST, ps.REF, ps.HEADLINE, ps.T) == (6, 3, -3, (2, 3), 10)


# ---- 1. planted_path, exactly --------------------------------------------------------------------------------------

@pytest.mark.parametrize("shift", ALL_SHIFTS)
def test_planted_path_is_the_whole_path_written_out_by_hand(shift):
    got = ps.planted_path(np.arange(ps.T), float(shift))
    assert got == pytest.approx(PATHS[shift], abs=1e-15)


@pytest.mark.parametrize("shift", ALL_SHIFTS)
def test_the_headline_keeps_the_share_of_the_planted_effect_the_path_gives(shift):
    keeps = headline_minus_reference(ps.planted_path(np.arange(ps.T), float(shift)))
    assert keeps == pytest.approx(float(HEADLINE_KEEPS[shift]), abs=1e-15)
    assert (keeps == pytest.approx(1.0, abs=1e-15)) == (shift in COST_FREE)


def test_planted_path_takes_a_shift_per_row_as_assemble_passes_it():
    tt = np.tile(np.arange(ps.T), len(ALL_SHIFTS))
    shift = np.repeat(np.array(ALL_SHIFTS, dtype=float), ps.T)
    assert ps.planted_path(tt, shift) == pytest.approx(np.concatenate([PATHS[s] for s in ALL_SHIFTS]), abs=1e-15)


# ---- an invented design small enough to reason about ---------------------------------------------------------------
# One cohort, one market region, six states with three never-host utilities each (18 units). Prices are a utility level
# plus a common year shock, with no noise, so with nothing planted every estimate is exactly zero.

def invented_windows(cohort: int = COHORT, per_state: int = 3, seed: int = 0):
    rng = np.random.default_rng(seed)
    years = list(range(cohort - ps.PRE, cohort + ps.POST + 1))
    keys = [(100 + 10 * s + i, st) for s, st in enumerate(STATES) for i in range(per_state)]
    shock = rng.normal(0, 0.05, len(years)).cumsum()
    index = pd.MultiIndex.from_tuples(keys, names=KEY)
    y = pd.DataFrame([rng.normal(2.4, 0.2) + shock for _ in keys], index=index, columns=years)
    attrs = pd.DataFrame({"region": "PJM", "ownership": ["cooperative" if k[0] % 2 else "investor_owned" for k in keys],
                          "res_customers": [5_000 + 1_000 * n for n in range(len(keys))]}, index=index)
    unit_code = {k: n for n, k in enumerate(keys)}
    state_code = {st: n for n, st in enumerate(sorted(STATES))}
    n = len(keys)
    hdd = np.array([[5.0 + 0.3 * STATES.index(k[1]) + 0.1 * rng.normal() for _ in years] for k in keys])
    cdd = np.array([[1.0 + 0.2 * STATES.index(k[1]) + 0.1 * rng.normal() for _ in years] for k in keys])
    w = ps.Window(cohort, y, attrs, unit_code, state_code, np.zeros((n, len(years)), dtype=int),
                  np.array([STATES.index(k[1]) % 3 for k in keys]), hdd, cdd)
    return {cohort: w}, n


def stand_in_rows(windows, cohort: int = COHORT) -> list[int]:
    """The first utility in each of OH, PA and VA stands in for a host."""
    w = windows[cohort]
    return [next(r for r, k in enumerate(w.keys) if k[1] == st) for st in ("OH", "PA", "VA")]


def invented_blocks():
    windows, n = invented_windows()
    picks = [(COHORT, j, i) for i, j in enumerate(stand_in_rows(windows))]
    blocks, lost = ps.build_blocks(windows, picks, "nearest_in_size", n)
    assert lost == 0 and len(blocks) == 3
    assert {len(comp) for _, _, comp in blocks} == {ps.MATCH_K}          # equal block sizes: the arithmetic below relies on it
    return windows, n, picks, blocks


def treated_rows(blocks, j: int) -> np.ndarray:
    """Stacked row numbers of stand-in row j, in window order (assemble stacks blocks in order, units by T years)."""
    off = 0
    for _, tr, comp in blocks:
        rows = list(tr) + list(comp)
        if j in list(tr):
            return off + rows.index(j) * ps.T + np.arange(ps.T)
        off += len(rows) * ps.T
    raise AssertionError(f"row {j} is not a stand-in")


def same_stack(a: dict, b: dict) -> bool:
    if a["columns"] != b["columns"] or a["control_columns_left_out"] != b["control_columns_left_out"]:
        return False
    if len(a["groups"]) != len(b["groups"]) or not all(np.array_equal(x, z) for x, z in zip(a["groups"], b["groups"])):
        return False
    return all(np.array_equal(a[k], b[k]) for k in ("y", "X", "cluster", "paths"))


# ---- 2. errors are applied; "applied but cost-free" is told apart from "not applied" -------------------------------

@pytest.mark.parametrize("controls", [True, False])
def test_no_errors_an_empty_dict_and_all_zero_errors_stack_the_same_and_a_nonzero_error_does_not(controls):
    windows, _, picks, blocks = invented_blocks()
    run = lambda e: ps.assemble(windows, blocks, errors=e, controls=controls, gas=GAS)  # noqa: E731
    none, empty, zeros = run(None), run({}), run({(g, int(j)): 0 for g, j, _ in picks})
    assert same_stack(none, empty) and same_stack(none, zeros)
    assert np.array_equal(none["paths"][:, 0], none["paths"][:, 1])           # with no error the two datings coincide
    g, j, _ = picks[0]
    moved = run({(g, int(j)): -1})
    assert not same_stack(none, moved)
    # only the misdated path moves; the outcome, the regressors, the fixed effects and the exact path do not
    assert np.array_equal(moved["y"], none["y"]) and np.array_equal(moved["X"], none["X"])
    assert all(np.array_equal(x, z) for x, z in zip(moved["groups"], none["groups"]))
    assert np.array_equal(moved["paths"][:, 0], none["paths"][:, 0])
    assert not np.array_equal(moved["paths"][:, 1], none["paths"][:, 1])


def test_an_error_of_minus_one_moves_that_stand_in_in_exactly_the_cells_the_path_says():
    windows, _, picks, blocks = invented_blocks()
    g, j, _ = picks[1]
    a = ps.assemble(windows, blocks, errors={(g, int(j)): -1}, controls=False)
    diff = a["paths"][:, 1] - a["paths"][:, 0]
    rows = treated_rows(blocks, j)
    expected = np.zeros(len(diff))
    expected[rows] = np.array(PATHS[-1]) - np.array(PATHS[0])
    assert diff == pytest.approx(expected, abs=1e-15)
    changed = sorted(int(r - rows[0]) - ps.PRE for r in np.flatnonzero(np.abs(diff) > 1e-12))
    assert changed == [-1, 0, 1]                                  # recorded event years -1, 0 and 1; each gains a third
    for e in (ps.REF, *ps.HEADLINE):
        assert diff[rows[idx(e)]] == 0.0                          # the reference year and the headline years are untouched


def test_an_error_of_minus_one_leaves_the_headline_and_moves_the_earlier_coefficients():
    """Fit on the stacked arrays (no controls): the coefficients on the planted paths are exact in arithmetic.

    With one stand-in per block and equal block sizes, each event-year coefficient is the mean over blocks of the
    treated-minus-comparison path, less the reference year. So one stand-in of three misdated by -1 adds a third of a
    third to event years -1, 0 and 1, and nothing anywhere else.
    """
    windows, _, picks, blocks = invented_blocks()
    g, j, _ = picks[0]
    a = ps.assemble(windows, blocks, errors={(g, int(j)): -1}, controls=False)
    fit = es.Fit(a["y"], a["X"], a["groups"], a["cluster"], a["paths"])
    b_exact, b_wrong = fit.coef(0, 1.0) - fit.coef(), fit.coef(1, 1.0) - fit.coef()
    assert float(ps.W_HEAD @ b_exact) == pytest.approx(1.0, abs=1e-10)
    assert float(ps.W_HEAD @ b_wrong) == pytest.approx(1.0, abs=1e-10)       # the headline is unchanged
    moved = {e: (b_wrong - b_exact)[ps.EVENT_TIMES.index(e)] for e in ps.EVENT_TIMES}
    for e, v in moved.items():
        assert v == pytest.approx(1 / 9 if e in (-1, 0, 1) else 0.0, abs=1e-10), e
    assert fit.coef()[ps.EVENT_TIMES.index(-1)] == pytest.approx(0.0, abs=1e-10)   # nothing in the invented outcome itself


@pytest.mark.parametrize("procedure", [ps.SELECTED, ps.AS_BUILT])
@pytest.mark.parametrize("shift", ALL_SHIFTS)
def test_one_draw_reads_a_uniform_error_at_the_share_the_path_gives(shift, procedure):
    """Every stand-in misdated by the same error, with the gas-share control: noise-free, so the headline is exact."""
    windows, _, picks, blocks = invented_blocks()
    out = ps.one_draw(windows, blocks, {(g, int(j)): shift for g, j, _ in picks}, np.random.default_rng(1), boot=19,
                      gas=GAS, procedure=procedure, taus=(0, 5))
    zero, five_exact, five_wrong = out["exact"][0], out["exact"][1], out["misdated"][1]
    assert zero["est"] == pytest.approx(0.0, abs=1e-9)
    assert five_exact["est"] == pytest.approx(T5, abs=1e-9)
    assert five_wrong["est"] == pytest.approx(T5 * float(HEADLINE_KEEPS[shift]), abs=1e-9)
    assert out["misdated"][0] is out["exact"][0]                  # nothing planted has one dating


@pytest.mark.parametrize("procedure", [ps.SELECTED, ps.AS_BUILT])
def test_one_draw_cannot_tell_a_cost_free_error_from_none_at_the_headline(procedure):
    """Why the guard above is needed: at the headline, every stand-in misdated by -1 reads exactly as no error at all.
    That the error is applied is shown on the stacked arrays and the event-year coefficients, not here."""
    windows, _, picks, blocks = invented_blocks()
    rng = lambda: np.random.default_rng(3)  # noqa: E731
    errs = {(g, int(j)): -1 for g, j, _ in picks}
    with_err = ps.one_draw(windows, blocks, errs, rng(), boot=19, gas=GAS, procedure=procedure, taus=(0, 5))
    without = ps.one_draw(windows, blocks, {}, rng(), boot=19, gas=GAS, procedure=procedure, taus=(0, 5))
    assert with_err["misdated"][1]["est"] == pytest.approx(without["misdated"][1]["est"], abs=1e-9)
    assert with_err["misdated"][1]["est"] == pytest.approx(T5, abs=1e-9)


def host_chunk_context(host_errs: dict, procedure: str = ps.SELECTED) -> dict:
    windows, n = invented_windows()
    real = pd.DataFrame([dict(cohort=COHORT, region="PJM", ownership=o, log_size=np.log(s), state=st, key=(900 + i, st))
                         for i, (st, o, s) in enumerate((("OH", "cooperative", 6_000), ("PA", "investor_owned", 9_000),
                                                         ("VA", "cooperative", 12_000)))])
    return {"real": real, "windows": windows, "n_units": n, "host_errs": host_errs, "form": "nearest_in_size", "boot": 19,
            "excluded": None, "fuel_control": ps.GAS_SHARE, "gas": GAS, "procedure": procedure}


def run_host_chunks(monkeypatch, host_errs: dict, draws: int = 4):
    """The simulation's own draw loop (_host_chunk via _run, one process), on the invented context; records the errors
    each draw passed to one_draw."""
    monkeypatch.setattr(ps, "_CTX", {})
    seen, real_one_draw = [], ps.one_draw

    def spy(windows, blocks, errors, *args, **kwargs):
        seen.append(dict(errors))
        return real_one_draw(windows, blocks, errors, *args, **kwargs)

    monkeypatch.setattr(ps, "one_draw", spy)
    parts = ps._run(ps._host_chunk, host_chunk_context(host_errs), ps._chunks((7,), draws), 1)
    return [r for p in parts for r in p["results"]], seen


@pytest.mark.parametrize("err, keeps", [(1, Fraction(5, 6)), (-1, Fraction(1)), (-3, Fraction(2, 3)), (2, Fraction(1, 2)),
                                        (99, Fraction(0))])
def test_the_draw_loop_carries_each_hosts_error_to_its_stand_in(monkeypatch, err, keeps):
    errs = {(900 + i, st): np.array([err]) for i, st in enumerate(("OH", "PA", "VA"))}
    results, seen = run_host_chunks(monkeypatch, errs)
    applied = 60 if err >= ps.NEVER - 30 else err
    assert len(seen) == 4 and all(len(e) == 3 and set(e.values()) == {applied} for e in seen)
    for r in results:
        assert r["exact"][FIVE]["est"] == pytest.approx(T5, abs=1e-9)
        assert r["misdated"][FIVE]["est"] == pytest.approx(T5 * float(keeps), abs=1e-9)


def test_the_draw_loop_with_no_distributions_gives_every_stand_in_an_error_of_zero(monkeypatch):
    results, seen = run_host_chunks(monkeypatch, {})
    assert all(set(e.values()) == {0} and len(e) == 3 for e in seen)
    for r in results:
        assert all(a["est"] == pytest.approx(b["est"], abs=1e-12) for a, b in zip(r["exact"], r["misdated"]))


# ---- 3. draw_errors -----------------------------------------------------------------------------------------------

def real_frame(keys):
    return pd.DataFrame({"key": list(keys)})


def test_a_host_with_no_distribution_or_an_empty_one_gets_zero():
    real = real_frame([(1, "OH"), (2, "PA"), (3, "VA")])
    picks = [(COHORT, np.int64(4), 0), (COHORT, 7, 1), (2014, 2, 2)]
    out = ps.draw_errors(real, picks, {(2, "PA"): np.array([], dtype=int), (9, "WI"): np.array([5])}, np.random.default_rng(0))
    assert out == {(COHORT, 4): 0, (COHORT, 7): 0, (2014, 2): 0}


def test_errors_come_only_from_the_hosts_own_distribution():
    real = real_frame([(1, "OH"), (2, "PA")])
    picks = [(COHORT, 3, 1), (COHORT, 5, 0)]            # row 3 stands in for host (2, PA), row 5 for (1, OH)
    dist = {(1, "OH"): np.array([-2, 1]), (2, "PA"): np.array([3, 5])}
    rng = np.random.default_rng(11)
    got = {(COHORT, 3): set(), (COHORT, 5): set()}
    for _ in range(200):
        for k, v in ps.draw_errors(real, picks, dist, rng).items():
            got[k].add(v)
    assert got == {(COHORT, 3): {3, 5}, (COHORT, 5): {-2, 1}}


def test_an_error_of_never_minus_thirty_or_more_becomes_sixty():
    from pipeline.analysis import misdating
    assert ps.NEVER == misdating.NEVER                  # the code that makes the errors and the code that maps them agree
    real = real_frame([(k, "OH") for k in range(6)])
    values = [ps.NEVER - 31, ps.NEVER - 30, ps.NEVER - 29, ps.NEVER, ps.NEVER + 5, 2]
    picks = [(COHORT, r, r) for r in range(6)]
    out = ps.draw_errors(real, picks, {(k, "OH"): np.array([v]) for k, v in enumerate(values)}, np.random.default_rng(0))
    assert [out[(COHORT, r)] for r in range(6)] == [ps.NEVER - 31, 60, 60, 60, 60, 2]
    assert headline_minus_reference(ps.planted_path(np.arange(ps.T), 60.0)) == 0.0          # past the window either way
    assert headline_minus_reference(ps.planted_path(np.arange(ps.T), float(ps.NEVER - 31))) == 0.0


def test_the_keys_are_cohort_and_row_as_python_ints_and_assemble_reads_them():
    windows, _, picks, blocks = invented_blocks()
    real = real_frame([(900 + i, "X") for i in range(len(picks))])
    np_picks = [(g, np.int64(j), i) for g, j, i in picks]
    out = ps.draw_errors(real, np_picks, {(900 + i, "X"): np.array([2]) for i in range(len(picks))}, np.random.default_rng(0))
    assert set(out) == {(g, int(j)) for g, j, _ in picks}
    assert all(type(g) is int and type(j) is int for g, j in out)
    a = ps.assemble(windows, blocks, errors=out, controls=False)
    for _, j, _ in picks:
        rows = treated_rows(blocks, j)
        assert a["paths"][rows, 1] == pytest.approx(PATHS[2], abs=1e-15)


# ---- 4. read_draws on invented draws ------------------------------------------------------------------------------

HALF = 0.025          # every invented range is the estimate plus or minus this


def reading(est: float, failure: str | None = None) -> dict:
    nan = float("nan")
    if failure:
        r = ps.failed_reading(failure, 6)
        r.update(pre_p=nan)
        return r
    return {"est": est, "se": HALF / 1.645, "lo": est - HALF, "hi": est + HALF, "clusters": 6, "pre_wald": 1.0,
            "pre_p": 0.5, "pre_p_bootstrap": 0.5, "max_abs_early": 0.0, "lo_analytic": est - HALF, "hi_analytic": est + HALF,
            "numerical_failure": None, "analytic_failure": None}


def invented_draws(good: int, failed: int, share: float) -> list[dict]:
    """`good` draws that recover each planted effect whole with exact dates and `share` of it misdated, then `failed`
    draws whose every reading is a numerical failure. Nothing planted has one reading, as in one_draw."""
    draws = []
    for _ in range(good):
        exact = [reading(float(np.log1p(p / 100))) for p in ps.TAUS_PCT]
        wrong = [exact[0]] + [reading(share * float(np.log1p(p / 100))) for p in ps.TAUS_PCT[1:]]
        draws.append({"exact": exact, "misdated": wrong})
    for _ in range(failed):
        bad = [reading(0.0, es.RANK_DEFICIENT) for _ in ps.TAUS_PCT]
        draws.append({"exact": bad, "misdated": [bad[0]] + [reading(0.0, es.RANK_DEFICIENT) for _ in ps.TAUS_PCT[1:]]})
    return draws


def first_detected(share: float) -> int:
    """The smallest planted percent on the grid whose invented range lies wholly above zero."""
    return next(p for p in ps.TAUS_PCT if share * np.log1p(p / 100) - HALF > 0)


def test_the_invented_ranges_are_first_wholly_above_zero_where_the_arithmetic_says():
    assert first_detected(1.0) == 3 and first_detected(0.5) == 6


@pytest.mark.parametrize("procedure", [ps.SELECTED, ps.AS_BUILT])
@pytest.mark.parametrize("failed", [0, 1])
def test_read_draws_reports_the_share_recovered_and_the_smallest_increase(procedure, failed):
    out = ps.read_draws(invented_draws(good=9, failed=failed, share=0.5), hosts=3, procedure=procedure)
    n = 9 + failed
    power = 9 / n                                      # a failed draw stays in the denominator and detects nothing
    ex, wr = out["start_years_exact"], out["start_years_misdated"]
    assert ex["planted_5pct"]["share_of_the_planted_effect_recovered"] == 1.0
    assert wr["planted_5pct"]["share_of_the_planted_effect_recovered"] == 0.5
    for x, first in ((ex, 3), (wr, 6)):
        rates = x[ps.POWER_BY_TAU_KEY]
        assert rates == {str(p): (round(power, 3) if p >= first else 0.0) for p in ps.TAUS_PCT}
        # interpolated between the last grid point at zero and the first at `power`
        assert x[ps.SMALLEST_INCREASE_KEY] == round((first - 1) + ps.POWER_BAR / power, 2)
        assert x["planted_5pct"]["numerical_failures"]["count"] == failed and x["planted_5pct"]["numerical_failures"]["of"] == n
    assert ex[ps.SMALLEST_INCREASE_KEY] == (2.8 if failed == 0 else 2.89)
    assert wr[ps.SMALLEST_INCREASE_KEY] == (5.8 if failed == 0 else 5.89)
    top = out["numerical_failures"]["selected_procedure" if procedure == ps.SELECTED else "bootstrap"]
    assert top["count"] == failed and top["of"] == n                          # reported, including when it is zero
    assert top["by_cause"] == ({es.RANK_DEFICIENT: 1} if failed else {})
    assert out["draws"] == n and out["rates_include_numerical_failures"] is True


def test_read_draws_does_not_detect_with_a_failed_draw_even_when_its_range_would_be_above_zero():
    """A failure is no detection however its range reads: give the failed draw a range wholly above zero."""
    draws = invented_draws(good=4, failed=0, share=1.0)
    bad = [dict(reading(float(np.log1p(p / 100))), numerical_failure=es.RANK_DEFICIENT, analytic_failure=es.RANK_DEFICIENT)
           for p in ps.TAUS_PCT]
    draws.append({"exact": bad, "misdated": list(bad)})
    out = ps.read_draws(draws, hosts=3, procedure=ps.SELECTED)
    assert out["start_years_exact"][ps.POWER_BY_TAU_KEY]["12"] == 0.8
    assert out["numerical_failures"]["selected_procedure"]["count"] == 1
