#!/usr/bin/env python3
"""The estimation kernel every post-freeze run on outcomes calls. Reads NO outcome: the outcome is an argument.

PREANALYSIS.md, "Electricity: the main estimate (new hosts)" through "Inference", "The headline: an estimate and its
range" and "Reported checks". Nothing in this module chooses a sample, drops a host or changes the procedure. The design
(a design.Design, built by the caller under the rules it names) fixes the hosts, their matched comparison utilities and
the windows; this module fits one outcome on it and reads the fit.

The computation is the one step E validated, called and not rewritten:
  the regressors, fixed effects and clusters  inference_check.fixed_parts (power_simulation.assemble: event-time columns
                                              on host rows, the two degree-day controls, the gas-share-by-calendar-year
                                              columns kept by screen_controls; utility effects and block-by-region-by-year
                                              effects; clusters by state)
  the procedure                               candidates.Problem.from_fixed_parts and candidates.CandidateC, the problem
                                              inference_comparison.build_context hands step E's candidates; its rank test
                                              (estimator.check_rank) runs in CandidateC's constructor before anything is
                                              inverted
  the reading                                 power_simulation.c_reading: the CR2 standard error, the 90% Satterthwaite t
                                              range and the approximate Hotelling test on event years -6, -5 and -4
tests/test_outcome_analysis_invented.py checks, on invented data, that `estimate` returns the same estimate, range and
early-years p-value as inference_comparison.run_candidates and power_simulation.c_reading on the same design and outcome.

Windows of other lengths and absorbed controls
---------------------------------------------
power_simulation.assemble and inference_check.fixed_parts are fixed at ten years. assemble_span stacks a window of any
length the same way, and estimate_span reads it with the same candidates.Problem, candidates.CandidateC and
power_simulation.c_reading, which take the number of columns, the headline combination and the early columns as
arguments. At six years before and three after it returns what estimate returns (tested to 1e-10). estimate_long_horizon
is the plan's longer horizon. estimate's option absorbed_controls=LEAVE_OUT_IF_EXACTLY_ABSORBED is for the own-state side
run only (adopted by Joe on 2026-11-19, D-111).

Validation (PREANALYSIS.md, Inference, "Where the validation does not transfer")
--------------------------------------------------------------------------------
The selected procedure was validated on one design: the headline set at 2% under the main specification. `estimate`
takes `validated_design` with no default. False (every design but that one) attaches NOT_VALIDATED. The claim that a
design IS the validated one is a ValidationClaim, never a bare True: the kernel checks it by recomputing the design's
inputs (design.design_inputs: hosts and cohorts, matches, the usable set, the regressors and their fuel control, the
clusters) and its rules, and comparing their hashes with the ones recorded in the step E files
(read_validation_reference). A claim that does not check is refused: the result carries NOT_VALIDATED and says why in
`validation_check`. estimate_span (windows of any length, the longer horizon) cannot claim validation at all. Added in
session 19 (Joe, D-103: check the code traps); the fit and its numbers are unchanged.

The outcome
-----------
`estimate` takes `y`, one value for each row of the stacked sample in the order power_simulation.assemble stacks the
design's blocks (host first, then its matches, each over its ten window years). `stacked_rows(d)` lists those rows.
A caller with a long frame keyed by utility_id_eia, state and year builds `y` with `outcome_vector(d, frame, column)`,
which stops in words on a missing unit-year, a duplicate key or a value that is not finite, and never fills anything.
outcome_vector returns an AlignedOutcome: the values with a signature of the rows they were built for. `estimate` and
`estimate_span` refuse (OutcomeMisaligned) a vector whose signature is not that of the rows they stack, so a vector built
for one design cannot be read against another of the same length (a re-dated design, another deletion). A plain array is
still read with its length checked, and the result says the alignment was checked by length only (`outcome_alignment`).

Numerical failures (PREANALYSIS.md, Inference, "Numerical failures in the analysis")
-------------------------------------------------------------------------------------
If the selected procedure fails for the estimate (a rank failure, a variance that is not finite, degrees of freedom that
are undefined, a test that cannot be computed), no range and no test result is reported. The failure and its cause are
reported in their place. A point estimate that still computes is labelled descriptive. No other procedure is substituted
and nothing is dropped.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import estimator  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import influence  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
K_EVENT = len(ps.EVENT_TIMES)
HEADLINE_MULTIPLIER = 5.5          # event years 2 and 3 are 5 and 6 years past the reference year: their mean is 5.5
FIXED_DRIFTS = (0.005, 0.01)       # the four fixed drift scenarios: 0.5% and 1% a year, away from and toward
ALPHA = cd.ALPHA                   # the early-years test fails at p below 0.10

DESCRIPTIVE = "descriptive: the selected procedure failed numerically, so no range and no test result is reported"
NOT_COMPUTED = "not computed: the fit failed its rank test before anything was inverted"

FAILURE_IN_WORDS = {
    cd.RANK_DEFICIENT: "the regressors are not all identified once the fixed effects are removed (the rank test made before any fit)",
    cd.NON_FINITE_STANDARD_ERROR: "the CR2 standard error of the headline is not finite and positive",
    cd.SINGULAR_WALD_VARIANCE: "the CR2 variance of the three early coefficients cannot be inverted",
    cd.NON_FINITE_OUTCOME: "the outcome has a value that is not finite",
    cd.NON_FINITE_ADJUSTMENT: "a CR2 adjustment matrix is not finite",
    cd.UNDEFINED_DEGREES_OF_FREEDOM: "the degrees of freedom are undefined or not finite",
    cd.NON_FINITE_BOOTSTRAP_T: "a bootstrap replication is not finite",
    cd.NON_FINITE_BOOTSTRAP_WALD: "a bootstrap replication of the early-years statistic is not finite",
    cd.SINGULAR_RESTRICTION: "the restricted fit for the early-years test cannot be computed",
}

# The plan's fixed sentences (Reported checks, the first two bullets). Text exactly as PREANALYSIS.md has it.
EARLY_NOT_DETECTED = "The test did not detect a difference in the years before."
EARLY_SMALL_SET = "On a set this small it would miss a large one."
EARLY_FAILS = ("Prices at hosts were already moving differently before the data centers arrived, so the estimate may "
               "reflect that trend.")
HALF_SENTENCE = ("If hosts had been drifting away from the comparison utilities by half the largest year-to-year change we "
                 "estimated in the early years, the estimate would move by {D} points.")
WHOLE_SENTENCE = ("If hosts had been drifting away from the comparison utilities by the whole of the largest year-to-year "
                  "change we estimated in the early years, the estimate would move by {D} points.")
# The plan says each of the two sentences "says it ignores the uncertainty in that early change" without fixing the words.
# The wording below is the agent's.
IGNORES_UNCERTAINTY = "This ignores the uncertainty in that estimated early change."
# The plan describes the four fixed scenarios and gives no sentence for them. The wording below is the agent's.
FIXED_SENTENCE = ("If hosts had been drifting {direction} the comparison utilities by {pct}% a year from the reference year "
                  "through the headline years, the estimate would move by {D} points.")
QUALIFICATIONS = (
    "Each is an illustration, an assumed continuation of pre-existing drift, not estimated bias, a confidence bound or a "
    "corrected causal effect.",
    "All six are reported regardless of which is more favorable.",
    "None determines the headline method or sample.",
    "None widens a range, is a bound, shows that real trends were that small, or supports causal language.",
    "No range is widened and no drift at which a range would include zero is computed.",
)


class OutcomeMisaligned(ValueError):
    """The outcome supplied does not line up with the design's stacked rows. Raised in words; nothing is filled."""


ALIGNMENT_CHECKED = "checked: the vector was built by outcome_vector for exactly the rows this fit stacks"
ALIGNMENT_LENGTH_ONLY = ("length only: a plain array (not built by outcome_vector, or sliced or recomputed since), so only "
                         "its length was checked against the rows this fit stacks")
SIGNATURE_COLUMNS = ["block", "cohort", "block_host_id", "block_host_state", "utility_id_eia", "state", "year", "event_year",
                     "is_host"]


def rows_signature(rows: pd.DataFrame) -> str:
    """A sha256 of the stacked rows, in order: which block, host, unit, calendar year and event year each value is for."""
    h = pd.util.hash_pandas_object(rows[SIGNATURE_COLUMNS], index=False).to_numpy()
    return hashlib.sha256(np.ascontiguousarray(h).tobytes() + f"|{len(rows)}".encode()).hexdigest()


class AlignedOutcome(np.ndarray):
    """An outcome vector with the signature of the stacked rows it was built for (`rows_signature`). Made only by
    outcome_vector and outcome_vector_span. Any view, slice or arithmetic on it is a plain certificate-free array (its
    `rows_signature` is None), since it may no longer be those rows."""

    def __new__(cls, values, signature: str):
        obj = np.asarray(values, dtype=float).view(cls)
        obj.rows_signature = signature
        return obj

    def __array_finalize__(self, obj):
        self.rows_signature = None

    def __array_wrap__(self, out, context=None, return_scalar=False):     # a ufunc's result is not certified
        out = np.asarray(out)
        return out[()] if return_scalar else out


def _aligned(y, rows: pd.DataFrame) -> tuple[np.ndarray, str]:
    """The outcome as a plain float vector after the checks: one dimension, one value per stacked row, and, for a vector
    outcome_vector built, the same rows in the same order. Returns (values, what was checked)."""
    sig = getattr(y, "rows_signature", None)
    v = np.array(y, dtype=float) if sig is not None else np.asarray(y, dtype=float)
    if v.ndim != 1 or len(v) != len(rows):
        raise OutcomeMisaligned(f"the outcome has shape {v.shape}; the design has {len(rows)} stacked rows")
    if sig is None:
        return v, ALIGNMENT_LENGTH_ONLY
    if sig != rows_signature(rows):
        raise OutcomeMisaligned("the outcome vector was built for other rows than this design stacks (another design, a "
                                "re-dated design, another deletion or another window), though its length is the same; "
                                "build it with outcome_vector on this design. Nothing is read")
    return v, ALIGNMENT_CHECKED


# ---- the rows and the outcome ----------------------------------------------------------------------------------------

def stackable(d):
    """The design that is stacked: `d` without its hosts that have no matched comparison utility.

    A block with no comparison rows cannot be stacked by power_simulation.assemble, and it would carry no weight. Such a
    host is named in every result (`hosts_with_no_matches`) and is not counted in N; nothing else is removed. This follows
    influence.estimable, which leaves such hosts out of the design used for the rank test and the weights."""
    if not len(d.hosts):
        return d
    n = np.array([len(m) for m in d.hosts.matches])
    return d if (n > 0).all() else influence._without(d, n > 0)


def stacked_rows_span(windows: dict, blocks: list, pre: int, post: int) -> pd.DataFrame:
    """One row per stacked observation for windows of years cohort - pre to cohort + post, in the order assemble_span (and,
    at pre = 6 and post = 3, power_simulation.assemble) stacks `blocks`: for each block the host, then its matches, each
    over every window year. Blocks with no comparison rows are left out here, as estimate_span leaves them out of its
    stacking (before session 19 the caller had to; one that did not got OutcomeMisaligned)."""
    T = pre + post + 1
    out = []
    for b, (g, tr, comp) in enumerate([blk for blk in blocks if len(blk[2])]):
        w = windows[g]
        host = w.keys[int(tr[0])]
        for j, r in enumerate(np.concatenate([np.asarray(tr, dtype=int), np.asarray(comp, dtype=int)])):
            key = w.keys[int(r)]
            for t in range(T):
                out.append((b, int(g), int(host[0]), host[1], int(key[0]), key[1], int(g) - pre + t, t - pre, j < len(tr)))
    return pd.DataFrame(out, columns=["block", "cohort", "block_host_id", "block_host_state", "utility_id_eia", "state",
                                      "year", "event_year", "is_host"])


def stacked_rows(d) -> pd.DataFrame:
    """One row per stacked observation, in the order power_simulation.assemble stacks the blocks of stackable(d): for each
    host's block, the host and then its matched comparison utilities, each over its ten window years (cohort - 6 to
    cohort + 3)."""
    d = stackable(d)
    return stacked_rows_span(d.windows, d.blocks(), ps.PRE, ps.POST)


def _vector_for_rows(rows: pd.DataFrame, frame: pd.DataFrame, column: str) -> np.ndarray:
    need = KEY + ["year", column]
    missing_cols = [c for c in need if c not in frame.columns]
    if missing_cols:
        raise OutcomeMisaligned(f"the outcome frame has no column {missing_cols}")
    f = frame[need].copy()
    f["utility_id_eia"] = f.utility_id_eia.astype(int)
    f["year"] = f.year.astype(int)
    dup = f.duplicated(KEY + ["year"], keep=False)
    if dup.any():
        first = f[dup].iloc[0]
        raise OutcomeMisaligned(f"the outcome frame repeats a unit-year ({int(dup.sum())} rows), for example "
                                f"{int(first.utility_id_eia)}:{first.state} in {int(first.year)}; stopping")
    m = rows.merge(f, on=KEY + ["year"], how="left", indicator=True)
    absent = m[m["_merge"] == "left_only"]
    if len(absent):
        named = sorted({f"{int(u)}:{s} in {int(y)}" for u, s, y in zip(absent.utility_id_eia, absent.state, absent.year)})
        raise OutcomeMisaligned(f"the outcome frame lacks {len(named)} unit-years the design needs, for example {named[:5]}; "
                                "nothing is filled")
    vals = m[column].to_numpy(dtype=float)
    bad = ~np.isfinite(vals)
    if bad.any():
        named = sorted({f"{int(u)}:{s} in {int(y)}" for u, s, y in zip(m.utility_id_eia[bad], m.state[bad], m.year[bad])})
        raise OutcomeMisaligned(f"the outcome is missing or not finite for {len(named)} unit-years the design needs, for "
                                f"example {named[:5]}; nothing is filled")
    return vals


def outcome_vector(d, frame: pd.DataFrame, column: str) -> np.ndarray:
    """The outcome for every stacked row, read from a long frame keyed by utility_id_eia, state and year.

    Stops in words (OutcomeMisaligned) on a frame without the key or the column, a duplicate key, a unit-year the design
    needs that the frame lacks, or a value that is missing or not finite. Never fills, interpolates or drops a row.
    A unit that is a comparison for several hosts takes the same value in each copy of a calendar year.
    Returns an AlignedOutcome carrying the rows' signature, which estimate checks.
    """
    rows = stacked_rows(d)
    return AlignedOutcome(_vector_for_rows(rows, frame, column), rows_signature(rows))


def outcome_vector_span(windows: dict, blocks: list, pre: int, post: int, frame: pd.DataFrame, column: str) -> np.ndarray:
    """outcome_vector for windows of any length (stacked_rows_span's order, blocks with no comparison rows left out), with
    the same stops in words. Returns an AlignedOutcome, which estimate_span checks."""
    rows = stacked_rows_span(windows, blocks, pre, post)
    return AlignedOutcome(_vector_for_rows(rows, frame, column), rows_signature(rows))


# ---- the kernel ----------------------------------------------------------------------------------------------------

def _fuel_control(d, fuel_control: str | None) -> str:
    """The fuel control the design was built under (d.rules, from design.build_with_rules), unless the caller names one.

    A design with no `rules` (influence.leave_out and influence._without return one; so does design.build) falls back to
    the gas-share control only if it carries gas shares, which build_with_rules attaches under the gas-share control
    alone. One with neither stops in words: before session 19 it fell back to the gas-share control and failed for want of
    gas shares, in a message that named neither the lost rules nor the deletion."""
    if fuel_control is not None:
        return fuel_control
    rules = getattr(d, "rules", None)
    if rules is not None:
        return rules.fuel_control
    if getattr(d, "gas", None) is None:
        raise ValueError("the design carries no rules (a deletion such as influence.leave_out, or a design built without "
                         "build_with_rules, drops them) and no gas shares, so its fuel control is unknown: name "
                         "fuel_control, or carry the rules it was built under (run_outcomes.carry_design_attributes)")
    return ps.GAS_SHARE


def point_fit(y: np.ndarray, X: np.ndarray, groups: list, cluster: np.ndarray, projection=None) -> np.ndarray:
    """Ordinary least squares coefficients with the fixed effects removed (estimator.Fit, the shared estimator). Its rank
    test runs before anything is inverted and raises estimator.RankDeficient in words. Point estimates only: no
    inference is read from it here."""
    return estimator.Fit(y, X, groups, cluster, projection=projection).coef()


def _failure(cause: str, where: str, detail: str = "") -> dict:
    return {"cause": cause, "where": where, "detail": detail, "in_words": FAILURE_IN_WORDS.get(cause, cause)}


def _pct(x: float) -> float:
    """A difference in log points as a percent difference in price: 100 * (exp(x) - 1)."""
    return float(100.0 * np.expm1(x)) if np.isfinite(x) else float("nan")


def _host_label(key) -> str:
    return f"{int(key[0])}:{key[1]}"


def host_weights(d, fuel_control: str) -> dict:
    """Each host's weight on the headline (its rows' weights in event years 2 and 3), from the regressors alone
    (inference_check.implied_weights). Raises estimator.RankDeficient where the fit cannot be computed."""
    wt = ic.implied_weights(d, fuel_control)
    head = wt[wt.is_host & wt.event_year.isin(ps.HEADLINE)].groupby("utility").weight.sum()
    return {_host_label(k): float(head.get(tuple(k), 0.0)) for k in d.hosts.key}


# ---- a window of any length ----------------------------------------------------------------------------------------

def event_times(pre: int, post: int) -> list:
    """Every event year in the window but the reference year (-3), in order: the event-time columns."""
    return [e for e in range(-pre, post + 1) if e != ps.REF]


def assemble_span(windows: dict, blocks: list, pre: int, post: int, *, controls: bool = True,
                  fuel_control: str = ps.GAS_SHARE, gas: dict | None = None) -> dict:
    """power_simulation.assemble for windows of years cohort - pre to cohort + post. assemble is fixed at ten years
    (ps.T, ps.EVENT_TIMES) and may not change, so this is its stacking written once more with the window's length as an
    argument; every step is assemble's, in assemble's order, and every shared piece is called, not rewritten
    (estimator.Projection, power_simulation.screen_controls, power_simulation.gas_share_of_rows, the left-out reasons).
    Regressors: an event-time column for every event year but -3 on host rows; the two degree-day columns; under the
    gas-share control, the state's share times an indicator for each calendar year but the first, screened in calendar
    order. Fixed effects: utility (a unit's copy in one block), block by region by year (region read year by year), and
    under CATEGORICAL cohort by fuel-mix group by year. Clusters: the row's state. At pre = 6 and post = 3 it returns
    assemble's X, groups and clusters (tested through estimate_span against estimate). No planted paths."""
    if fuel_control not in ps.FUEL_CONTROLS:
        raise ValueError(f"unknown fuel control {fuel_control!r}; one of {ps.FUEL_CONTROLS}")
    T = pre + post + 1
    times = event_times(pre, post)
    order = {g: i for i, g in enumerate(sorted(windows))}
    trs, tts, units, cells, fuels, cl, hd, cd_, cal, st = [], [], [], [], [], [], [], [], [], []
    n_units = 0
    for b, (g, tr, comp) in enumerate(blocks):
        s = windows[g]
        rows = np.concatenate([np.asarray(tr, dtype=int), np.asarray(comp, dtype=int)])
        n = len(rows)
        tt = np.tile(np.arange(T), n)
        trs.append(np.repeat(np.r_[np.ones(len(tr)), np.zeros(len(comp))], T))
        tts.append(tt)
        units.append(n_units + np.repeat(np.arange(n), T))
        n_units += n
        cells.append((b * 1000 + s.region_t[rows].ravel()) * T + tt)
        fuels.append((order[g] * 3 + np.repeat(s.fuel[rows], T)) * T + tt)
        cl.append(np.repeat(s.state[rows], T))
        hd.append(s.hdd[rows].ravel())
        cd_.append(s.cdd[rows].ravel())
        cal.append(g - pre + tt)
        st.append(np.repeat(s.state_name[rows], T))
    tr, tt = np.concatenate(trs), np.concatenate(tts)
    X = np.column_stack([tr * (tt == e + pre) for e in times])
    columns = [f"event_year_{e}" for e in times]
    groups = [np.concatenate(units), np.concatenate(cells)]
    left_out, projection = [], None
    if controls:
        dd = np.column_stack([np.concatenate(hd), np.concatenate(cd_)])
        X = np.column_stack([X, dd])
        columns += ["heating_degree_days", "cooling_degree_days"]
        if fuel_control == ps.CATEGORICAL:
            groups.append(np.concatenate(fuels))
        elif fuel_control == ps.GAS_SHARE:
            years = np.concatenate(cal)
            share = ps.gas_share_of_rows(np.concatenate(st), gas)
            calendar = sorted(int(x) for x in np.unique(years))
            left_out.append({"year": calendar[0], "why": ps.FIRST_YEAR_LEFT_OUT})
            cand = np.column_stack([share * (years == yr) for yr in calendar[1:]]) if len(calendar) > 1 else np.zeros((len(tr), 0))
            projection = estimator.Projection(groups)
            kept, dropped = ps.screen_controls(dd, cand, projection)
            left_out += [{"year": calendar[1 + j], "why": ps.REDUNDANT_LEFT_OUT} for j in dropped]
            X = np.column_stack([X, cand[:, kept]])
            columns += [f"gas_share_x_{calendar[1 + j]}" for j in kept]
    if projection is None:
        projection = estimator.Projection(groups)
    return {"X": X, "groups": groups, "cluster": np.concatenate(cl), "columns": columns, "event_times": times,
            "fuel_control": fuel_control if controls else "no_controls", "control_columns_left_out": left_out,
            "projection": projection}


def absorbed_hosts_span(X: np.ndarray, projection, rows: pd.DataFrame, k_event: int,
                        tol: float = estimator.RANK_TOLERANCE) -> list:
    """inference_check.absorbed_hosts on an assembled design of any window length, by the same test: a host is fully
    absorbed when its own event-time columns, once the fixed effects are removed, are a linear combination of the
    control columns (what is left is no more than `tol` times what there was). Hosts by label."""
    controls = projection(X[:, k_event:])
    out = []
    for b, blk in rows.groupby("block", sort=True):
        idx = blk.index[blk.is_host.to_numpy()].to_numpy()
        own = np.zeros((len(X), k_event))
        own[idx] = X[idx, :k_event]
        raw = float(np.linalg.svd(own, compute_uv=False).max()) if own.any() else 0.0
        if raw == 0.0:
            continue
        t = projection(own)
        if controls.shape[1]:
            t = t - controls @ np.linalg.lstsq(controls, t, rcond=None)[0]
        if float(np.linalg.svd(t, compute_uv=False).max()) <= tol * raw:
            out.append(f"{int(blk.block_host_id.iloc[0])}:{blk.block_host_state.iloc[0]}")
    return out


# ---- absorbed controls (the own-state side run) ---------------------------------------------------------------------
LEAVE_OUT_IF_EXACTLY_ABSORBED = "leave_out_if_exactly_absorbed"
ABSORBED_TOLERANCE = 1e-10
NOT_VALIDATED = "under the procedure validated on the headline set; no validation was made on this design"
NOT_CLAIMED = "not claimed: the caller passed validated_design=False"


# ---- the validated design, checked rather than trusted ----------------------------------------------------------------
FROZEN = Path(__file__).resolve().parents[2] / "data" / "frozen"
# The step E files: each records the fingerprint of the design the inference comparison and validation ran on.
VALIDATION_FILES = ("inference_comparison_benchmark.json", "inference_comparison_stage1.json",
                    "inference_validation_budget.json", "inference_validation_stage2.json")
DESIGN_SUPPORT_FILE = "design_support.json"          # its headline set's fingerprint, written by design.main


def rules_component(rules) -> dict:
    """The rules as design.run_fingerprint records them (its "rules" component)."""
    return {"label": rules.label, "ownership": rules.ownership, "usable": rules.usable, "support": rules.support,
            "fuel_control": rules.fuel_control, "unresolved_ownership": rules.unresolved_ownership}


def design_hashes(d, usable, fuel_control: str) -> dict:
    """The "design_inputs" and "rules" component hashes of design.run_fingerprint for design `d`, as design.main and step E
    computed them (design.design_inputs, design.fingerprint). No outcome is read: the regressors are assembled with the
    outcome set to zero, as design_inputs does. `rules` is None when the design carries none."""
    rules = getattr(d, "rules", None)
    comp = {"design_inputs": dsg.design_inputs(d, fuel_control, usable)}
    if rules is not None:
        comp["rules"] = rules_component(rules)
    of = dsg.fingerprint(comp)["of"]
    return {"design_inputs": of["design_inputs"], "rules": of.get("rules")}


@dataclass(frozen=True)
class ValidationReference:
    """The design the selected procedure was validated on, by the hashes of its design inputs and its rules."""
    design_inputs_sha: str
    rules_sha: str
    source: str

    @classmethod
    def of_design(cls, d, usable, *, fuel_control: str = ps.GAS_SHARE, source: str) -> "ValidationReference":
        """A reference made from a design in memory (tests on invented inputs; a check of the reference on real files)."""
        h = design_hashes(d, usable, fuel_control)
        if h["rules"] is None:
            raise ValueError("a validation reference needs a design that carries its rules (design.build_with_rules)")
        return cls(h["design_inputs"], h["rules"], source)


@dataclass(frozen=True)
class ValidationClaim:
    """The claim that a design is the validated one: the reference (read_validation_reference) and the usable set the
    design was built on (design_inputs includes it). The kernel checks it; a claim that does not check is refused."""
    reference: ValidationReference | None
    usable: object


def read_validation_reference(frozen: Path | None = None) -> ValidationReference:
    """The validated design's hashes, from the fingerprints recorded in the step E files (VALIDATION_FILES) and in
    design_support.json's headline set. Every one must record the same "design_inputs" and "rules" components; files that
    do not agree, or a file that is missing, stop in words. Reads fingerprints only: no price, no outcome."""
    frozen = FROZEN if frozen is None else Path(frozen)
    found = {}
    for f in VALIDATION_FILES + (DESIGN_SUPPORT_FILE,):
        p = frozen / f
        if not p.exists():
            raise FileNotFoundError(f"{f} is not in {frozen}: the validated design's fingerprint cannot be read")
        j = json.loads(p.read_text())
        fp = j["sets"][ps.HEADLINE_SET]["fingerprint"] if f == DESIGN_SUPPORT_FILE else j["fingerprint"]
        found[f] = (fp["of"]["design_inputs"], fp["of"]["rules"])
    if len(set(found.values())) != 1:
        raise ValueError(f"the files recording the validated design do not agree on its inputs or rules: "
                         f"{ {f: (a[:12], b[:12]) for f, (a, b) in found.items()} }")
    di, ru = next(iter(found.values()))
    return ValidationReference(di, ru, "the fingerprint recorded in " + ", ".join(found))


def _validation(d, fc: str, absorbed_controls, claim) -> dict:
    """The check of a claim that `d` is the validated design. Returns {"claimed", "passed", "why"[, "reference"]}."""
    if claim is False:
        return {"claimed": False, "passed": None, "why": NOT_CLAIMED}
    if not isinstance(claim, ValidationClaim):
        raise TypeError("validation cannot be claimed with True or any value but a ValidationClaim: pass "
                        "ValidationClaim(read_validation_reference(), the usable set the design was built on) so the kernel "
                        "can check it, or False")
    out = {"claimed": True, "passed": False}
    ref = claim.reference
    if ref is None:
        return {**out, "why": "refused: no validation reference was supplied (read_validation_reference reads it from the "
                              "step E files)"}
    out["reference"] = ref.source
    if absorbed_controls is not None:
        return {**out, "why": f"refused: the absorbed-controls option ({absorbed_controls}) is not the main specification"}
    if getattr(d, "rules", None) is None:
        return {**out, "why": "refused: the design carries no rules, so it cannot be shown to be the validated design"}
    try:
        h = design_hashes(d, claim.usable, fc)
    except Exception as exc:                                    # noqa: BLE001  a claim that cannot be checked is refused
        return {**out, "why": f"refused: the design's inputs could not be computed ({type(exc).__name__}: {exc})"}
    if h["rules"] != ref.rules_sha:
        return {**out, "why": f"refused: the design's rules ({d.rules.label}) are not the rules of the validated design"}
    if h["design_inputs"] != ref.design_inputs_sha:
        return {**out, "why": ("refused: the design's inputs (hosts and cohorts, matches, the usable set, the regressors and "
                               "their fuel control, the clusters) differ from those of the validated design")}
    return {**out, "passed": True, "why": "checked: the design's inputs and rules are those the procedure was validated on"}


def exactly_absorbed_controls(X: np.ndarray, projection, columns: list, k_event: int,
                              tol: float = ABSORBED_TOLERANCE) -> tuple[list, list]:
    """Each control column (every column after the event-time columns): the norm after the fixed effects are projected
    out, relative to its norm before. A column at or under `tol` is exactly absorbed. Returns (absorbed, not absorbed),
    each a list of {"column", "relative_norm_after_projection"}."""
    yes, no = [], []
    for j in range(k_event, X.shape[1]):
        before = float(np.linalg.norm(X[:, j]))
        after = float(np.linalg.norm(projection(X[:, j])))
        rel = after / before if before > 0 else 0.0
        (yes if rel <= tol else no).append({"column": columns[j], "index": j, "relative_norm_after_projection": rel})
    return yes, no


def _read(y, rows: pd.DataFrame, a: dict, times: list, headline_years, hosts: list, no_matches: list,
          absorbed: list, absorbed_controls: str | None) -> dict:
    """The fit and its reading on an assembled design `a` (X, groups, cluster, projection, columns): the computation
    step E validated (candidates.Problem, candidates.CandidateC, power_simulation.c_reading), whatever the window length.
    The combination is the mean of `headline_years`; the early-years test is on event years -6, -5 and -4."""
    nan = float("nan")
    k_event = len(times)
    head = {"log_points": nan, "percent": nan, "standard_error_log_points": nan, "degrees_of_freedom": nan,
            "range_90_log_points": None, "range_90_percent": None, "status": None,
            "event_years": [int(e) for e in headline_years]}
    early = {"Q": nan, "F": nan, "numerator_degrees_of_freedom": len(ps.EARLY), "denominator_degrees_of_freedom": nan,
             "p_value": None, "fails_at_p_below_0.10": None, "event_years": list(ps.EARLY)}
    X, columns = a["X"], list(a["columns"])
    out = {"procedure": {"name": ps.SELECTED, **ps.PROCEDURE_TEXT[ps.SELECTED]}, "hosts_in_the_design": hosts,
           "hosts_with_no_matches": no_matches, "numerical_failure": None, "fuel_control": a["fuel_control"],
           "control_columns_left_out": a["control_columns_left_out"], "hosts_fully_absorbed": absorbed,
           "absorbed_controls_option": absorbed_controls, "controls_left_out_as_exactly_absorbed": []}
    if absorbed_controls not in (None, LEAVE_OUT_IF_EXACTLY_ABSORBED):
        raise ValueError(f"unknown absorbed_controls option {absorbed_controls!r}; None or {LEAVE_OUT_IF_EXACTLY_ABSORBED!r}")
    if absorbed_controls == LEAVE_OUT_IF_EXACTLY_ABSORBED:
        yes, no = exactly_absorbed_controls(X, a["projection"], columns, k_event)
        gone = {c["index"] for c in yes}
        keep = [j for j in range(X.shape[1]) if j not in gone]
        X, columns = X[:, keep], [columns[j] for j in keep]
        out["controls_left_out_as_exactly_absorbed"] = [{k: v for k, v in c.items() if k != "index"} for c in yes]
        out["absorbed_tolerance"] = ABSORBED_TOLERANCE
    combo = np.zeros(X.shape[1])
    for e in headline_years:
        combo[times.index(e)] = 1.0 / len(headline_years)
    pre = [times.index(e) for e in ps.EARLY]
    problem = cd.Problem(X, a["groups"], a["cluster"], projection=a["projection"], combo=combo, pre=pre)
    cand = cd.CandidateC(problem)
    out.update({"columns": columns, "rows": int(problem.N), "regressors": int(problem.K), "clusters": int(problem.G)})
    if cand.design_failure is not None and cand.design_failure.cause == cd.RANK_DEFICIENT:
        out.update(event_year_coefficients=None, headline={**head, "status": NOT_COMPUTED}, early_years_test=early,
                   count_N=None, hosts_with_zero_weight=None, host_headline_weights=None,
                   numerical_failure=_failure(cd.RANK_DEFICIENT, cand.design_failure.where, cand.design_failure.detail))
        return out
    # Implied weights (inference_check.implied_weights' formula, w = X~ (X~'X~)^-1 combo) from the regressors alone.
    w = cand.Xt @ (cand.M @ combo)
    hw = pd.Series(w).groupby([rows.block_host_id.astype(str) + ":" + rows.block_host_state,
                               rows.is_host & rows.event_year.isin(list(headline_years))]).sum()
    weights = {h: float(hw.get((h, True), 0.0)) for h in hosts if h not in no_matches}
    zero = [h for h, v in weights.items() if abs(v) < influence.ZERO_WEIGHT]
    out["host_headline_weights"] = weights
    out["hosts_with_zero_weight"] = zero
    out["count_N"] = int(sum(1 for h in hosts if h not in zero and h not in absorbed and h not in no_matches))
    if not np.isfinite(y).all():
        b, failure = None, _failure(cd.NON_FINITE_OUTCOME, "fit", "the outcome has a value that is not finite")
    elif cand.design_failure is not None:
        # The procedure failed at the design level after the rank test passed: the point estimate still computes.
        b = point_fit(y, problem.X, problem.groups, problem.cluster, problem.projection)
        failure = _failure(cand.design_failure.cause, cand.design_failure.where, cand.design_failure.detail)
    else:
        b, u = cand.fit(y)
        r = ps.c_reading(cand, b, u)
        failure = None
        if r["numerical_failure"]:
            where = cand.early_failure.where if (cand.early_failure is not None and r["numerical_failure"] == cand.early_failure.cause) \
                else ("fit" if r["numerical_failure"] == cd.NON_FINITE_STANDARD_ERROR else "early_years_test")
            detail = cand.early_failure.detail if where == "early_years_test" and cand.early_failure is not None else ""
            failure = _failure(r["numerical_failure"], where, detail)
        else:
            q = len(ps.EARLY)
            head.update(standard_error_log_points=r["se"], degrees_of_freedom=float(cand.nu),
                        range_90_log_points=[r["lo"], r["hi"]], range_90_percent=[_pct(r["lo"]), _pct(r["hi"])],
                        status="estimate with its 90% range under the selected procedure")
            early.update({"Q": r["pre_wald"], "F": float((cand.eta - q + 1) / (cand.eta * q) * r["pre_wald"]),
                          "denominator_degrees_of_freedom": float(cand.eta - q + 1), "p_value": r["pre_p"],
                          "fails_at_p_below_0.10": bool(r["pre_p"] < ALPHA)})
    if b is None:
        out.update(event_year_coefficients=None, headline={**head, "status": DESCRIPTIVE}, early_years_test=early,
                   numerical_failure=failure)
        return out
    coefs = {str(e): float(b[i]) for i, e in enumerate(times)}
    coefs[str(ps.REF)] = 0.0
    coefs = {str(e): coefs[str(e)] for e in range(min(times), max(times) + 1)}
    est = float(combo @ b)
    head.update(log_points=est, percent=_pct(est))
    if failure is not None:
        head["status"] = DESCRIPTIVE
    out.update(event_year_coefficients=coefs, headline=head, early_years_test=early, numerical_failure=failure)
    return out


def _empty_result(fc, hosts, no_matches, headline_years) -> dict:
    nan = float("nan")
    return {"procedure": {"name": ps.SELECTED, **ps.PROCEDURE_TEXT[ps.SELECTED]}, "hosts_in_the_design": hosts,
            "hosts_with_no_matches": no_matches, "fuel_control": fc, "columns": None, "control_columns_left_out": None,
            "rows": 0, "regressors": 0, "clusters": 0, "hosts_fully_absorbed": [], "event_year_coefficients": None,
            "headline": {"log_points": nan, "percent": nan, "standard_error_log_points": nan, "degrees_of_freedom": nan,
                         "range_90_log_points": None, "range_90_percent": None, "status": NOT_COMPUTED,
                         "event_years": [int(e) for e in headline_years]},
            "early_years_test": {"Q": nan, "F": nan, "numerator_degrees_of_freedom": len(ps.EARLY),
                                 "denominator_degrees_of_freedom": nan, "p_value": None, "fails_at_p_below_0.10": None,
                                 "event_years": list(ps.EARLY)},
            "count_N": None, "hosts_with_zero_weight": None, "host_headline_weights": None,
            "numerical_failure": _failure(cd.RANK_DEFICIENT, "design", "no host in the design has a matched comparison utility")}


def estimate(d, y, *, validated_design, fuel_control: str | None = None, absorbed_controls: str | None = None) -> dict:
    """The main estimate on design `d` for the outcome `y` (aligned to stacked_rows(d); see outcome_vector).

    Returns a dict:
      event_year_coefficients   every event-year coefficient in log points, the reference year (-3) 0.0 by construction
      headline                  the mean of event years 2 and 3: log points, percent (100 * (exp(x) - 1)), the CR2
                                standard error, the Satterthwaite degrees of freedom, the 90% range in log points and in
                                percent, and `status`
      early_years_test          the approximate Hotelling test on event years -6, -5 and -4: Q (Eq. 10), the F statistic
                                (Eq. 12), its degrees of freedom, the p-value and whether it fails at p below 0.10
      clusters                  states in the fit
      count_N                   hosts in the estimate with weight (The headline, the count [N]); None if the weights
                                cannot be computed
      hosts_in_the_design, hosts_with_zero_weight, hosts_fully_absorbed, hosts_with_no_matches, host_headline_weights
      numerical_failure         None, or {"cause", "where", "detail", "in_words"}; the cause is one of
                                candidates.FAILURE_CAUSES (estimator.FAILURE_CAUSES and step E's additions)
      validation                None only when `validated_design` is a ValidationClaim that checks (the design's inputs
                                and rules hash to the validated design's); NOT_VALIDATED otherwise (the plan's words for a
                                design on which no validation was made)
      validation_check          {"claimed", "passed", "why"[, "reference"]}: what was claimed and what the check found
      outcome_alignment         ALIGNMENT_CHECKED for a vector from outcome_vector on this design, ALIGNMENT_LENGTH_ONLY
                                for a plain array

    validated_design (required, no default)
        False for every design but the validated one. ValidationClaim(reference, usable) to claim it; the kernel checks
        the claim (see the module docstring) and refuses one that does not check. True raises TypeError.
    A rank failure leaves no coefficient; any other failure leaves the point estimate, labelled descriptive, and no
    range or test result. The regressors, fixed effects and clusters are inference_check.fixed_parts'.

    absorbed_controls
        None (the default): nothing is left out. LEAVE_OUT_IF_EXACTLY_ABSORBED: adopted by Joe on 2026-11-19 (D-111) for
        the own-state side run ONLY (comparison utilities from the host's own state, where every match shares the
        host's state, so the state-level controls are constant within the matched set's year and its year effects take
        them). Each control
        column whose norm after the fixed effects are projected out is at most ABSORBED_TOLERANCE (1e-10) of its norm
        before is left out and named in `controls_left_out_as_exactly_absorbed`; leaving out a column the fixed effects
        absorb exactly does not change the fit. A column that is not exactly absorbed stays, and if the fit is still rank
        deficient the failure is reported in words as without the option.
    """
    if validated_design is not False and not isinstance(validated_design, ValidationClaim):
        _validation(d, None, absorbed_controls, validated_design)          # raises TypeError in words
    fc = _fuel_control(d, fuel_control)
    rows = stacked_rows(d)
    y, alignment = _aligned(y, rows)
    hosts = [_host_label(k) for k in d.hosts.key] if len(d.hosts) else []
    no_matches = [_host_label(k) for k, m in zip(d.hosts.key, d.hosts.matches) if len(m) == 0] if len(d.hosts) else []
    if len(rows) == 0:
        out = _empty_result(fc, hosts, no_matches, ps.HEADLINE)
    else:
        ds = stackable(d)
        f = ic.fixed_parts(ds, fc)
        out = _read(y, rows, f, list(ps.EVENT_TIMES), ps.HEADLINE, hosts, no_matches, ic.absorbed_hosts(ds, fc), absorbed_controls)
    check = _validation(d, fc, absorbed_controls, validated_design)
    out["validation"] = None if check["passed"] else NOT_VALIDATED
    out["validation_check"] = check
    out["outcome_alignment"] = alignment
    return out


def estimate_span(windows: dict, blocks: list, y, pre: int, post: int, headline_years, *, gas: dict | None = None,
                  fuel_control: str = ps.GAS_SHARE, absorbed_controls: str | None = None, controls: bool = True,
                  validated_design: bool = False) -> dict:
    """estimate for windows of years cohort - pre to cohort + post, stacked by assemble_span, with the headline the mean
    of `headline_years`. The inference is the same code: candidates.Problem and candidates.CandidateC take the number of
    columns from the regressors and the headline combination and the early columns as arguments, with nothing fixed at
    ten years, and power_simulation.c_reading reads the combination from the problem. The early-years test stays on
    event years -6, -5 and -4 (pre must be 6 or more). `y` is aligned to stacked_rows_span(windows, blocks, pre, post)
    (outcome_vector_span builds it; a vector it built is checked against these rows). Blocks with no comparison rows are
    named and left out, as stackable does. Every result carries NOT_VALIDATED: a span is stacked from windows and blocks,
    not from a Design, so it cannot be checked against the validated design, and `validated_design` anything but False
    raises (before session 19 True was accepted unchecked). At pre = 6, post = 3 and headline years (2, 3) it returns
    what estimate returns on the same design and outcome (tested to 1e-10)."""
    if validated_design is not False:
        raise ValueError("estimate_span cannot claim validation: it stacks windows of any length from blocks, not the "
                         "validated Design, so the claim cannot be checked; use estimate with a ValidationClaim")
    if pre < 6:
        raise ValueError("the early-years test is on event years -6, -5 and -4: pre must be 6 or more")
    bad = [e for e in headline_years if e not in event_times(pre, post)]
    if bad:
        raise ValueError(f"headline years {bad} are not event-time columns of a window from -{pre} to {post}")
    labels = [_host_label(windows[g].keys[int(tr[0])]) for g, tr, _ in blocks]
    no_matches = [h for h, (_, _, comp) in zip(labels, blocks) if len(comp) == 0]
    blocks = [b for b in blocks if len(b[2])]
    rows = stacked_rows_span(windows, blocks, pre, post)
    y, alignment = _aligned(y, rows)
    if not len(rows):
        out = _empty_result(fuel_control, labels, no_matches, headline_years)
    else:
        a = assemble_span(windows, blocks, pre, post, controls=controls, fuel_control=fuel_control, gas=gas)
        times = a["event_times"]
        absorbed = absorbed_hosts_span(a["X"], a["projection"], rows, len(times))
        out = _read(y, rows, a, times, tuple(headline_years), labels, no_matches, absorbed, absorbed_controls)
    out["window"] = {"pre": pre, "post": post}
    out["validation"] = NOT_VALIDATED
    out["validation_check"] = {"claimed": False, "passed": None, "why": NOT_CLAIMED}
    out["outcome_alignment"] = alignment
    return out


def estimate_long_horizon(lh, y13, y10, *, gas: dict | None = None, fuel_control: str | None = None) -> dict:
    """The longer horizon (plan, Other runs, "A longer horizon"): the thirteen-year fit on lh.windows13 and lh.blocks13
    (event years -6 to 6, headline the mean of event years 4 to 6, the early-years test on -6, -5 and -4), and beside it
    the three-year number as estimate(lh.design, y10): the same hosts and the same matched utilities on ten-year windows.
    That this is what "computed on those same utilities" means was adopted by Joe on 2026-11-19 (D-111). `y13` is aligned to
    stacked_rows_span(lh.windows13, lh.blocks13, 6, 6), `y10` to stacked_rows(lh.design). Both results carry NOT_VALIDATED:
    the longer horizon is a design on which no validation was made (PREANALYSIS.md, Inference, "Where the validation
    does not transfer"). The gas shares default to lh.design.gas."""
    d = lh.design
    fc = _fuel_control(d, fuel_control)
    gas = d.gas if gas is None else gas
    lengths = {windows_len(w) for w in lh.windows13.values()}
    if len(lengths) != 1:
        raise ValueError(f"the thirteen-year windows have different lengths {sorted(lengths)}")
    post = lengths.pop() - ps.PRE - 1
    long = estimate_span(lh.windows13, lh.blocks13, y13, ps.PRE, post, tuple(range(4, 7)), gas=gas, fuel_control=fc,
                         validated_design=False)
    three = estimate(d, y10, fuel_control=fc, validated_design=False)
    return {"what_this_is": ("the longer horizon: cohorts 2011 to 2019, the same utilities in every year; the headline is the "
                             "mean of event years 4 to 6, shown next to the three-year number on the same hosts and matches"),
            "same_utilities_reading": "the three-year number is estimate(lh.design, y10) on the same hosts and matches (adopted by "
                                      "Joe on 2026-11-19, D-111)",
            "validation": NOT_VALIDATED, "six_years": long, "three_years_same_utilities": three}


def windows_len(w) -> int:
    """The number of years in a window (its outcome matrix's columns)."""
    return int(np.asarray(w.y).shape[1])


# ---- the reported checks -------------------------------------------------------------------------------------------

def early_years_reading(result: dict, catches_a_1pct_drift_in_under_half: bool) -> list[str]:
    """The sentences the plan fixes for the early-years test (Reported checks, first bullet), chosen by its rule.

    Fails (p below 0.10): EARLY_FAILS. Does not fail: EARLY_NOT_DETECTED, followed by EARLY_SMALL_SET where the inference
    comparison finds the test catches a drift of 1% a year in fewer than half of datasets on the set
    (`catches_a_1pct_drift_in_under_half`, which the caller takes from that comparison and the simulation). Where the
    test could not be computed no test result is reported: the one sentence returned says so with the cause (the agent's
    wording; the plan fixes no sentence for that case).
    """
    if not isinstance(catches_a_1pct_drift_in_under_half, bool):
        raise TypeError("catches_a_1pct_drift_in_under_half must be True or False, taken from the inference comparison")
    t = result["early_years_test"]
    if t["fails_at_p_below_0.10"] is None:
        f = result.get("numerical_failure") or {}
        return [f"The early-years test could not be computed ({f.get('in_words', 'cause not recorded')}); no test result is reported."]
    if t["fails_at_p_below_0.10"]:
        return [EARLY_FAILS]
    return [EARLY_NOT_DETECTED] + ([EARLY_SMALL_SET] if catches_a_1pct_drift_in_under_half else [])


def _points(x: float) -> str:
    return f"{x:.2f}"


def trend_illustrations(result: dict) -> dict:
    """The six illustrations of "What a hidden trend would do" (Reported checks, second bullet; Joe, D-99 and D-100).

    m is the largest absolute year-to-year change among the estimated early coefficients: from -6 to -5, from -5 to -4,
    and from -4 to the reference year, whose coefficient is zero by construction. In log points; "points" below are
    log points times 100, the headline's own scale. Where two steps tie for the largest, the first in that order is named
    as `m_from`; m is the same either way.
      half    D  = 5.5 * m / 2
      whole   D' = 5.5 * m
      fixed   hosts drifting away from and toward the comparison utilities by 0.5% and by 1% a year from the reference
              year through the headline years: 5.5 * d, coded exactly (2.75 and 5.5 points; toward is the negative).
              The agent's reading of "about": a drift of d a year on host rows from the reference year is in the span of
              the event-time columns, so it moves event year e's coefficient by d * (e + 3) exactly and the headline by
              d * (5 + 6) / 2 = 5.5 * d exactly in the fit; "about" is read as the plan's rounding of d (a drift in
              percent of price) into log points, which this function does not attempt. "Away" is read as hosts' prices
              rising relative to the comparison utilities (the headline moves up) and "toward" as falling (it moves down).
    Six, never crossed into further scenarios. Every one carries QUALIFICATIONS. Computed from the coefficients, whatever
    the inference status; where the estimate is descriptive the record says so. Where no coefficient was computed (a
    rank failure), nothing is illustrated and the record says why.
    """
    coefs = result.get("event_year_coefficients")
    base = {"qualifications": list(QUALIFICATIONS), "count": 6, "crossed": False}
    if coefs is None:
        return {**base, "computed": False, "why": result["headline"]["status"], "illustrations": []}
    path = [coefs[str(e)] for e in (-6, -5, -4)] + [coefs[str(ps.REF)]]
    steps = {"-6 to -5": path[1] - path[0], "-5 to -4": path[2] - path[1], "-4 to the reference year": path[3] - path[2]}
    which = max(steps, key=lambda k: abs(steps[k]))
    m = abs(steps[which])
    D, Dp = HEADLINE_MULTIPLIER * m / 2 * 100, HEADLINE_MULTIPLIER * m * 100
    ill = [
        {"name": "half_of_the_largest_early_change", "points": D, "formula": "D = 5.5 * m / 2",
         "sentences": [HALF_SENTENCE.format(D=_points(D)), IGNORES_UNCERTAINTY]},
        {"name": "all_of_the_largest_early_change", "points": Dp, "formula": "D' = 5.5 * m",
         "sentences": [WHOLE_SENTENCE.format(D=_points(Dp)), IGNORES_UNCERTAINTY]},
    ]
    for d in FIXED_DRIFTS:
        for direction, sign in (("away from", 1.0), ("toward", -1.0)):
            pts = sign * HEADLINE_MULTIPLIER * d * 100
            ill.append({"name": f"fixed_{'away' if sign > 0 else 'toward'}_{100 * d:g}pct_a_year", "points": pts,
                        "formula": f"{'+' if sign > 0 else '-'}5.5 * {d}",
                        "sentences": [FIXED_SENTENCE.format(direction=direction, pct=f"{100 * d:g}", D=_points(pts))]})
    status = result["headline"]["status"]
    return {**base, "computed": True, "m_log_points": m, "m_from": which, "early_steps_log_points": steps,
            "coefficients_are": status, "illustrations": ill}
