#!/usr/bin/env python3
"""Exercise 4a of session 24: how often the selected procedure's early-years test detects a drift of 1% a year.

The specification is docs/gate1/simulation-spec-4a-early-years-drift-2026-11-20.md, committed before any dataset of the
exercise was drawn. Joe authorized the exercise on 2026-11-20 (D-113). Every price here is made up. No price is read.

What it does. On the real design (the headline set at 2% under the headline rules, built as the inference comparison
builds it, design-inputs hash b8515c35cba1), for each of two made-up price processes of the comparison (G0, the one D-38
used, and G6, all of it), 2,000 datasets are drawn, each from its own seed. Each dataset is read twice by candidate C
(CR2 with the Satterthwaite range for the headline, the approximate Hotelling test on event years -6, -5 and -4 for the
early years, failing at p below 0.10): once as drawn, with nothing planted, and once with the hosts' log prices drifting
away from their comparison utilities' by 0.01 a year over the whole window (D-49's trend path, inference_check.TREND_PATH,
through fixed_parts's `trend`). A detection is a drift reading with no numerical failure whose early-years test fails.
A drift reading that fails numerically stays in the denominator, is counted by cause and where, and counts as no detection.

Run once, as a file (it starts worker processes):
    python3 -I pipeline/analysis/early_years_drift.py
It writes data/frozen/early_years_drift_selected_procedure.json once, at the end, and refuses if that file exists. It
keeps no per-dataset record on disk and writes nothing else. It calls none of the comparison's stage drivers and edits no
module it imports. The plan is a draft and is not frozen.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import inference_comparison as icp  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

Refused = icp.Refused

# ---- the specification's elements (section 3) --------------------------------------------------------------------------
SEED = 20261206                                   # the session's; used nowhere else (spec section 3)
DRIFT = 0.01                                      # log points a year: Joe's words name 1% a year (D-113)
PROCESS_NAMES = ("G0_as_in_D38", "G6_all_of_it")  # D-49, "On G0 and on G6"
PROCESS_INDEX = {n: icp.PROCESSES.index(n) for n in PROCESS_NAMES}     # 0 and 6, the comparison's own indices
DATASETS = 2000                                   # a process (D-49, "How many")
BLOCK = 25                                        # datasets a block; a dataset's numbers never depend on it
MAX_WORKERS = 6                                   # another simulation holds 10 of this machine's 18 processors
REQUIRED_DESIGN_INPUTS = "b8515c35cba1"           # the first twelve characters of the design-inputs hash (spec section 3)
CANDIDATE = "C"                                   # the selected procedure (step E's selection and validation)
SPEC = "docs/gate1/simulation-spec-4a-early-years-drift-2026-11-20.md"
OUT = ROOT / "data" / "frozen" / "early_years_drift_selected_procedure.json"
THIS_FILE = "pipeline/analysis/early_years_drift.py"
CODE_FILES = dsg.CODE_FILES + icp.OWN_FILES + (THIS_FILE,)
G8_OWNERSHIP_ONLY = False                         # as the stage runs recorded it: G8 built from ownership and suppliers

# The drift's effect on the headline by construction: the headline is the mean of event years 2 and 3, and the planted
# path is years past the reference year, so a drift of d a year moves it by d times the mean of (2 - REF, 3 - REF).
HEADLINE_MULTIPLIER = float(np.mean([e - ps.REF for e in ps.HEADLINE]))   # 5.5 (D-53)

PROCEDURE = ("Candidate C, the selected procedure (candidates.CandidateC, unchanged): CR2 with the Satterthwaite t range "
             "for the headline (the mean of event years 2 and 3), and the approximate Hotelling test of event years -6, -5 "
             f"and -4 being zero for the early years, which fails at p below {cd.ALPHA} (candidates.ALPHA). Each dataset is "
             "read with CandidateC.run(y, 0.0, planted=None) as drawn, and with CandidateC.run(y + 0.01 * trend, 0.0, "
             "planted=None) with the drift planted. C draws nothing, so there is no bootstrap seed.")

# The reading rule's three outcomes (spec section 4). Never a boolean.
ADDED = "added"
NOT_ADDED = "not added"
SPLIT = "split: no rule chosen"
RULE_WORDS = {
    ADDED: "Both processes' measured detection rates are under one half, so the second sentence ('On a set this small it "
           "would miss a large one.') is added to the early-years reading for the headline set.",
    NOT_ADDED: "Both processes' measured detection rates are at or over one half, so the second sentence is not added for "
               "the headline set.",
    SPLIT: "One process's measured detection rate is under one half and the other's is not. The session chooses no rule "
           "(not the lower, not the higher, not an average): the two rates are reported, the code is left choosing no "
           "second sentence, and the matter goes back to Joe with one recommendation.",
}


# ================================================================================================================
# The pure core
# ================================================================================================================

def generator(p: int, k: int, seed: int = SEED) -> np.random.Generator:
    """Dataset k of process p draws from SeedSequence([seed, p, k, 0]), the layout of inference_comparison.streams."""
    return np.random.default_rng(np.random.SeedSequence([seed, p, k, 0]))


def reading(r: dict) -> dict:
    """What is kept of one candidate result: the estimate, the early-years test, the failure record, and `reject` (a
    failure or a failing test, as the comparison counts a flat history's rejections)."""
    return {"estimate": float(r["estimate"]), "early_rejected": r["early_rejected"], "failure": r["failure"],
            "reject": bool(r["reject"])}


def detected(r: dict) -> bool:
    """A detection: no numerical failure, and the early-years test fails. A failure is never a detection."""
    return r["failure"] is None and r["early_rejected"] is True


def one_dataset(p: int, k: int, ctx: dict, seed: int = SEED, drift: float = DRIFT) -> dict:
    """Dataset k of process p, read flat and with the drift planted.

    `ctx` carries the comparison's context (inference_comparison.build_context, names=["C"]) and `trend`, fixed_parts's
    host indicator times years past the reference year on the observed rows, in the same row order. The made-up prices
    come from the comparison's own `draw`; the planted outcome is y + drift * trend, which is the outcome D-49's exercise
    read through estimator.Fit's path argument (estimator.Fit: "The outcome under path j at size tau is y + tau *
    paths[:, j]")."""
    P, _ = icp.draw(p, generator(p, k, seed), ctx)
    y = P[ctx["obs_unit"], ctx["obs_year"]]
    c = ctx["candidates"][CANDIDATE]
    flat = c.run(y, 0.0, planted=None)
    drifted = c.run(y + drift * ctx["trend"], 0.0, planted=None)
    return {"process": icp.PROCESSES[p], "p": int(p), "k": int(k), "flat": reading(flat), "drift": reading(drifted)}


def _finite_mean(rs: list) -> dict:
    """The mean estimate over the readings in which the candidate computed an estimate (failure None and finite)."""
    est = np.array([r["estimate"] for r in rs if r["failure"] is None], dtype=float)
    est = est[np.isfinite(est)]
    m = float(est.mean()) if len(est) else None
    return {"log_points": m, "percent_as_100_times_log_points": None if m is None else 100.0 * m,
            "over": "datasets in which the candidate computed an estimate (no numerical failure, finite estimate)",
            "datasets_used": int(len(est))}


def summarise_process(records: list, drift: float = DRIFT) -> dict:
    """One process's summary over its datasets (records from one_dataset)."""
    n = len(records)
    drift_rs = [r["drift"] for r in records]
    flat_rs = [r["flat"] for r in records]
    det = icp.count([detected(r) for r in drift_rs])
    k = det["count"]
    lo, hi = det["exact_95_interval"] if n else (None, None)
    return {
        "datasets": n,
        "early_years_test_detects_the_drift": {
            **det,
            "what_counts": "a drift reading with no numerical failure whose early-years test fails at p below 0.10; a "
                           "dataset whose drift reading fails numerically stays in the denominator and counts as no detection",
            "interval": "Clopper and Pearson's exact 95% interval (inference_comparison.clopper_pearson)",
            "measured_share_under_one_half": bool(2 * k < n),
            "exact_95_interval_contains_one_half": bool(lo <= 0.5 <= hi) if n else None},
        "numerical_failures_under_the_drift_counted_as_no_detection": icp._failures(drift_rs),
        "mean_headline_estimate_with_the_drift_planted": _finite_mean(drift_rs),
        "bias_the_drift_puts_in_the_headline_by_construction": {
            "log_points": HEADLINE_MULTIPLIER * drift, "percent_as_100_times_log_points": 100.0 * HEADLINE_MULTIPLIER * drift,
            "why": f"the headline is the mean of event years 2 and 3, {HEADLINE_MULTIPLIER} years past the reference year on "
                   f"average, times the drift of {drift} a year"},
        "mechanics_reading_not_a_validation_figure_same_datasets_with_nothing_planted": {
            "what_this_is": "A mechanics reading, NOT a validation figure: the same datasets read with nothing planted, to "
                            "show how much of the detection rate is the test's ordinary rate of failing a flat history. It "
                            "is not set against the 11% standard; stage 2's rates stand as the validation (spec section 3).",
            "early_years_test_rejects_a_flat_history": {**icp.count([r["reject"] for r in flat_rs]),
                                                        "failures_counted_as_rejections": True},
            "numerical_failures": icp._failures(flat_rs),
            "mean_headline_estimate": _finite_mean(flat_rs)},
    }


def reading_rule(share_g0: float, share_g6: float) -> str:
    """Section 4 of the specification, on the two measured shares: ADDED if both are under one half, NOT_ADDED if both
    are at or over, SPLIT otherwise. Returns one of the three strings, never a boolean."""
    under = (share_g0 < 0.5, share_g6 < 0.5)
    if all(under):
        return ADDED
    if not any(under):
        return NOT_ADDED
    return SPLIT


# ================================================================================================================
# Workers and blocks
# ================================================================================================================

_W: dict = {}


def _init(ctx: dict) -> None:
    _W.clear()
    _W["ctx"] = ctx


def _block(args) -> list:
    p, k0, k1, seed, drift = args
    return [one_dataset(p, k, _W["ctx"], seed, drift) for k in range(k0, k1)]


def plan_blocks(datasets: int, block: int = BLOCK) -> list:
    """(p, k_from, k_to) for each block of each process, G0 first."""
    return [(PROCESS_INDEX[n], b * block, min(datasets, (b + 1) * block))
            for n in PROCESS_NAMES for b in range((datasets + block - 1) // block)]


def run_all(ctx: dict, datasets: int, workers: int, block: int = BLOCK, seed: int = SEED, drift: float = DRIFT) -> dict:
    """Every dataset of both processes, in worker processes started fresh (spawn) when workers > 1. Returns the records
    by process name, in dataset order. Nothing is written to disk."""
    todo = [(p, k0, k1, seed, drift) for p, k0, k1 in plan_blocks(datasets, block)]
    if workers <= 1:
        _init(ctx)
        parts = [_block(t) for t in todo]
    else:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn"), initializer=_init, initargs=(ctx,)) as ex:
            parts = list(ex.map(_block, todo))
    out = {n: [] for n in PROCESS_NAMES}
    for part in parts:
        for r in part:
            out[r["process"]].append(r)
    for n in PROCESS_NAMES:
        out[n].sort(key=lambda r: r["k"])
        if [r["k"] for r in out[n]] != list(range(datasets)):
            raise Refused(f"for {n} the datasets returned are not 0 to {datasets - 1} once each, so nothing is written")
    return out


# ================================================================================================================
# The design, its hash and the context
# ================================================================================================================

def design_inputs_hash(d, rules, usable) -> str:
    """The "design_inputs" component hash of design.run_fingerprint, as design.main, step E and
    outcome_analysis.design_hashes compute it (design.design_inputs under the rules' fuel control, design.fingerprint)."""
    return dsg.fingerprint({"design_inputs": dsg.design_inputs(d, rules.fuel_control, usable)})["of"]["design_inputs"]


def build(d, regions, q, ownership, suppliers, mode: str, rules) -> dict:
    """The comparison's context with candidate C alone, plus fixed_parts's `trend` on the observed rows. Checks in words
    that fixed_parts gives the same rows and regressors the context was built on."""
    built = icp.build_context(d, regions, q, ownership, suppliers, mode, rules, names=[CANDIDATE])
    ctx = built["ctx"]
    f = ic.fixed_parts(d, rules.fuel_control)
    prob = ctx["problem"]
    same = (np.array_equal(f["obs_unit"], ctx["obs_unit"]) and np.array_equal(f["obs_year"], ctx["obs_year"])
            and f["X"].shape == prob.X.shape and np.array_equal(f["X"], prob.X) and len(f["trend"]) == prob.N)
    if not same:
        raise Refused("fixed_parts did not give the rows and regressors the comparison's context was built on; the trend "
                      "cannot be aligned with the outcome, stopping before any dataset")
    return {"ctx": {**ctx, "trend": np.asarray(f["trend"], dtype=float)}, "quantities": built["quantities"]}


def real_inputs():
    """The real design exactly as the comparison builds it (inference_comparison.real_design), with G8 as the stage runs
    built it. Quantities only."""
    return icp.real_design(G8_OWNERSHIP_ONLY)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint_of(d, rules, usable, datasets: int, block: int) -> dict:
    return dsg.run_fingerprint(
        d, rules=rules, usable=usable,
        assumptions={"kind": "early_years_drift_selected_procedure", "set": ps.HEADLINE_SET, "threshold": 0.02,
                     "processes": {n: {"index": PROCESS_INDEX[n], "grid": ic.GRID[n]} for n in PROCESS_NAMES},
                     "drift_log_points_a_year": DRIFT, "trend_path_years_past_the_reference_year": ic.TREND_PATH.tolist(),
                     "truth_passed_to_the_candidate": 0.0},
        settings={"candidate": CANDIDATE, "level": cd.LEVEL, "alpha": cd.ALPHA, "cr2_eigen_tolerance": cd.CR2_EIGEN_TOLERANCE,
                  "datasets_per_process": datasets, "block": block},
        seeds=[SEED], code_files=CODE_FILES)


# ================================================================================================================
# The one run
# ================================================================================================================

def execute(out: Path, inputs, workers: int, datasets: int = DATASETS, block: int = BLOCK, spec: Path | None = None,
            required: str = REQUIRED_DESIGN_INPUTS) -> dict:
    """The run, given the design's inputs (the tuple real_design returns). Refuses if `out` exists, stops in words if the
    design-inputs hash does not begin with `required`, then draws, reads, summarises and writes `out` once. `datasets`
    and `required` differ from the constants in tests on invented designs only."""
    out = Path(out)
    if out.exists():
        raise Refused(f"{out.name} exists. The exercise is run once and is never extended or rerun after its answer is seen "
                      "(spec section 5)")
    d, regions, q, ownership, suppliers, mode, rules, usable = inputs
    h = design_inputs_hash(d, rules, usable)
    if not h.startswith(required):
        raise Refused(f"the design-inputs hash is {h[:12]}, not {required}. This is not the design the specification names "
                      "(spec section 6); stopping before any dataset is drawn")
    spec = ROOT / SPEC if spec is None else Path(spec)
    if not spec.exists():
        raise Refused(f"{spec} is missing. The run records the specification's hash and does not start without it")
    built = build(d, regions, q, ownership, suppliers, mode, rules)
    fp = fingerprint_of(d, rules, usable, datasets, block)
    t0 = time.perf_counter()
    records = run_all(built["ctx"], datasets, workers, block)
    seconds = time.perf_counter() - t0
    by = {n: summarise_process(records[n]) for n in PROCESS_NAMES}
    shares = {n: by[n]["early_years_test_detects_the_drift"]["count"] / by[n]["datasets"] for n in PROCESS_NAMES}
    outcome = reading_rule(shares["G0_as_in_D38"], shares["G6_all_of_it"])
    report = {
        "what_this_is": (
            "Exercise 4a of session 24: how often the selected procedure's early-years test detects a drift of 1% a year on "
            "the current design (the headline set at 2% under the headline rules). Authorized by Joe on 2026-11-20 (D-113). "
            f"Specification: {SPEC}, committed before any dataset was drawn. Every price here is made up, and no price was "
            "read. This is a property of this test on this design under made-up prices of two assumed kinds. It is NOT "
            "evidence about real pre-trends, NOT a validation figure (stage 2's rates stand as the validation), NOT a figure "
            "for the companion sets, and NOT a rerun of any stage of the comparison. The plan is a draft pre-analysis plan; "
            "it is not frozen and not registered with anyone outside. Run once; never extended or rerun after its answer is seen."),
        "seed": SEED,
        "stream_layout": "dataset k of process p draws from numpy.random.SeedSequence([20261206, p, k, 0]), p the "
                         "comparison's index of the process (0 for G0, 6 for G6); candidate C draws nothing",
        "datasets_per_process": datasets,
        "block": block,
        "drift_log_points_a_year": DRIFT,
        "drift_path": "0.01 times the host indicator times years past the reference year, over the whole window "
                      "(inference_check.fixed_parts's trend, inference_check.TREND_PATH), added to the made-up history",
        "processes": {n: {"index_in_the_comparison": PROCESS_INDEX[n], "grid": ic.GRID[n]} for n in PROCESS_NAMES},
        "procedure": PROCEDURE,
        "by_process": by,
        "reading_rule": {
            "rule": "Spec section 4. If both measured rates are under one half, the second sentence is added for the headline "
                    "set. If both are at or over, it is not added. If one is under and one is not, no rule is chosen and the "
                    "matter goes back to Joe",
            "measured_shares": shares,
            "outcome": outcome,
            "in_words": RULE_WORDS[outcome],
            "note": "The comparison is of the measured share with one half, as the plan's words have it, and each exact interval "
                    "is reported beside its share. That reading of the plan's words is the session's and is Joe's to strike"},
        "design_inputs_sha256": h,
        "design_quantities": built["quantities"],
        "fingerprint": fp,
        "specification_sha256": sha256_file(spec),
        "workers": workers,
        "machine": icp.machine(),
        "commit": icp.commit(),
        "seconds_for_the_datasets": round(seconds, 1),
        "per_dataset_records_kept": "No per-dataset record is written to disk.",
    }
    text = json.dumps(report, indent=1, default=icp._jsonable) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x") as fh:                    # exclusive creation: never overwrites, written once
        fh.write(text)
    return report


def worker_count() -> int:
    return max(1, min(MAX_WORKERS, os.cpu_count() or 1))


def main(argv: list[str] | None = None, *, out: Path | None = None, inputs_from=None) -> int:
    """The one real run. `out` and `inputs_from` (a callable returning real_design's tuple) are replaced in tests only."""
    out = OUT if out is None else Path(out)
    try:
        if out.exists():                          # before anything heavy is built
            raise Refused(f"{out.name} exists. The exercise is run once and is never extended or rerun after its answer is "
                          "seen (spec section 5)")
        inputs = (inputs_from or real_inputs)()
        r = execute(out, inputs, worker_count())
    except Refused as e:
        print(f"REFUSED: {e.why}", file=sys.stderr)
        return 2
    print(json.dumps({"reading_rule": r["reading_rule"], "workers": r["workers"],
                      "seconds_for_the_datasets": r["seconds_for_the_datasets"]}, indent=1, default=icp._jsonable))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
