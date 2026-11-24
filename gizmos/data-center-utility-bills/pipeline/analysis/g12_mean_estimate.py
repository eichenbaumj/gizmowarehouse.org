#!/usr/bin/env python3
"""G12's mean estimate with nothing planted (session 24, exercise 4b; authorized by Joe on 2026-11-20, D-113).

The specification is docs/gate1/simulation-spec-4b-g12-mean-estimate-2026-11-20.md. This module implements it and
chooses nothing it does not state; where the agent that wrote it had to read something the specification leaves open,
the place says "the agent's reading".

What it does. It reads the per-dataset records that step E's stage 1 and stage 2 left on disk, for the two walk processes
G11 and G12 only, by path (block_PP_BBBBB.json, as inference_comparison.run_blocks named them) together with each run's
manifest.json. Before any figure it makes the three checks of the specification's section 5 for each stage and each of
the two processes, and stops in words, writing nothing, if any fails or a block is missing. It then gives the mean of
candidate C's headline estimate over the datasets in which C computed one, for stage 2's 20,000 and stage 1's 2,000
datasets, for G12 (the named figure) and G11 (beside it, labelled as not the named figure), with the figures the
specification puts beside it, and writes data/frozen/g12_mean_estimate_nothing_planted.json once.

What it does not do. It draws no dataset, calls no stage driver or block runner of the comparison and builds no design.
It reads no price: every price behind the records was made up by the comparison. It writes nothing under the run folders.
It does not change the fuel-mix control, set a threshold or try any other process, candidate or control.

Run once, from the gizmo folder:

  python3 -I pipeline/analysis/g12_mean_estimate.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from pipeline.analysis import inference_comparison as ic  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
RUN_ROOT = ROOT / "data" / "interim" / "inference_comparison"
STAGES = ("stage1", "stage2")
RUN_DIRS = {"stage1": RUN_ROOT / "stage1", "stage2": RUN_ROOT / "stage2"}       # the only folders opened under data/interim
STAGE_FILES = {"stage1": FROZEN / ic.PATHS["stage1"], "stage2": FROZEN / ic.PATHS["stage2"]}
POWER_FILE = FROZEN / "power_simulation.json"
OUT = FROZEN / "g12_mean_estimate_nothing_planted.json"
SPEC = ROOT / "docs" / "gate1" / "simulation-spec-4b-g12-mean-estimate-2026-11-20.md"

G11, G12 = ic.WALK_PROCESSES
PROCESSES = (G12, G11)                  # G12 is the named figure; G11 is beside it and is not
CANDIDATE = "C"                         # the candidate stage 1 selected and stage 2 validated
STAGE1_CANDIDATES = ("A", "B", "C")
Z = 1.96                                # the interval of the mean: plus and minus 1.96 standard errors (specification, section 4)
PERCENT = 100.0                         # percent is 100 times the log-point figure, as the stage reports and power_simulation do
AGREEMENT_TOLERANCE = 1e-9              # the agent's reading of "floating-point noise", in log points (see agreement)
HALF_WIDTH_PATH = ("new_host_estimate", "2%", "headline_set", "nothing_planted", "range_half_width_mean")

LIMIT_READ_FROM_THE_CODE = (
    "In G12 the fuel shock is a national walk whose steps are normal with mean zero, loaded by the square root of a state's "
    "gas share plus a state deviation. The walk and its mirror image are equally likely, and the headline estimate is a "
    "linear function of the outcome. So the estimate's mean over datasets is zero in expectation whatever the adjustment "
    "does. A measured mean near zero is what this construction gives whether or not the linear adjustment is adequate; the "
    "mean can show a failure only if it is away from zero, and it cannot show adequacy. What bears on adequacy in these "
    "records is how the estimate moves with the realised walk (the slope on the realised change and the root-mean-square "
    "error). This is the session's reading of the code, written before any record was read.")


class Refused(Exception):
    """The exercise stops, with its reason in words. Nothing is written."""

    def __init__(self, why: str):
        super().__init__(why)
        self.why = why


@dataclass
class Paths:
    """Every path the runner opens or writes. The defaults are the real ones; tests pass their own."""
    run_dirs: dict = field(default_factory=lambda: dict(RUN_DIRS))
    stage_files: dict = field(default_factory=lambda: dict(STAGE_FILES))
    power_file: Path = POWER_FILE
    out: Path = OUT
    spec: Path = SPEC


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path, what: str) -> tuple[dict, str]:
    """A JSON file and the sha256 of the bytes it was parsed from. A missing file is a stop in words."""
    if not path.is_file():
        raise Refused(f"{path} is missing: {what}")
    raw = path.read_bytes()
    return json.loads(raw), sha256(raw)


# ================================================================================================================
# Reading the records by path
# ================================================================================================================

def block_path(run_dir: Path, p: int, b: int) -> Path:
    """The block file's name exactly as inference_comparison.run_blocks writes it."""
    return run_dir / f"block_{p:02d}_{b:05d}.json"


def read_process(run_dir: Path, process: str, datasets: int) -> dict:
    """Every record of one process, from the block files named by inference_comparison.blocks for `datasets` datasets a
    process, read by path in block order (no listing of the folder). A missing block, or a block whose header is not the
    one its name says, is a stop in words naming it. Reads only; writes nothing."""
    p = ic.PROCESSES.index(process)
    records, hashes = [], []
    for pp, b, k0, k1 in ic.blocks(datasets, processes=[p]):
        f = block_path(run_dir, pp, b)
        if not f.is_file():
            raise Refused(f"block {f.name} of {process} (datasets {k0} to {k1 - 1}) is missing from {run_dir}: the exercise "
                          "stops. The stage is not rerun to refill it (specification, sections 5 and 8)")
        raw = f.read_bytes()
        blk = json.loads(raw)
        header = {"process": process, "p": pp, "block": b, "k_from": k0, "k_to": k1}
        wrong = {k: blk.get(k) for k, v in header.items() if blk.get(k) != v}
        if wrong:
            raise Refused(f"block {f.name} in {run_dir} does not carry the header its name gives ({header}); it carries {wrong}: "
                          "the exercise stops")
        records += blk["records"]
        hashes.append(f"{f.name} {sha256(raw)}")
    return {"records": records, "blocks_read": len(hashes),
            "block_files_sha256": sha256("\n".join(hashes).encode()),
            "block_files_sha256_is": "the sha256 of the lines 'name sha256' of every block file read, in block order "
                                     "(the agent's addition, for provenance)"}


# ================================================================================================================
# The three checks of the specification's section 5
# ================================================================================================================

def check_identity(stage: str, manifest: dict, stage_file: dict) -> dict:
    """Check 1: the manifest's fingerprint equals the stage file's fingerprint.sha256, and its stage, seed, datasets a
    process and candidates equal the stage file's (stage 2's file names its one candidate under `candidate`)."""
    stored_candidates = list(stage_file["candidates"]) if stage == "stage1" else [stage_file.get("candidate")]
    pairs = {"fingerprint_sha256": (manifest.get("fingerprint_sha256"), stage_file.get("fingerprint", {}).get("sha256")),
             "stage": (manifest.get("stage"), stage),
             "seed": (manifest.get("seed"), stage_file.get("seed")),
             "datasets_per_process": (manifest.get("datasets_per_process"), stage_file.get("datasets_per_process")),
             "candidates": (manifest.get("candidates"), stored_candidates)}
    differ = {k: {"manifest": a, "stage_file": b} for k, (a, b) in pairs.items() if a != b}
    if differ:
        raise Refused(f"check 1 fails for {stage}: the run folder's manifest and the stage file differ in {differ}. The records "
                      "are not shown to be the run's own, and the exercise stops (specification, section 5)")
    if CANDIDATE not in stored_candidates:
        raise Refused(f"check 1 fails for {stage}: candidate {CANDIDATE} is not among the run's candidates {stored_candidates}")
    return {"check": "1. the manifest's fingerprint, stage, seed, datasets a process and candidates equal the stage file's",
            "stage": stage, "compared": {k: a for k, (a, _) in pairs.items()}, "holds": True}


def check_records(stage: str, process: str, records: list, n: int) -> dict:
    """Check 2: the count of records for the process equals the stage file's datasets a process, every block is present
    (read_process stops otherwise) and every dataset number 0 to n-1 is present exactly once."""
    wrong_process = sum(r.get("process") != process for r in records)
    ks = Counter(int(r["k"]) for r in records)
    repeated = sorted(k for k, c in ks.items() if c > 1)
    absent = sorted(set(range(n)) - set(ks))
    outside = sorted(k for k in ks if not 0 <= k < n)
    problems = []
    if len(records) != n:
        problems.append(f"{len(records)} records, not {n}")
    if repeated:
        problems.append(f"dataset numbers repeated: {repeated[:10]}")
    if absent:
        problems.append(f"dataset numbers absent: {absent[:10]}")
    if outside:
        problems.append(f"dataset numbers outside 0 to {n - 1}: {outside[:10]}")
    if wrong_process:
        problems.append(f"{wrong_process} records name another process")
    if problems:
        raise Refused(f"check 2 fails for {process} in {stage}: " + "; ".join(problems) + ". The exercise stops (specification, "
                      "section 5)")
    return {"check": "2. the count of records equals the stage file's datasets a process, every block present, every dataset "
                     "number present exactly once", "stage": stage, "process": process, "records": len(records),
            "datasets_per_process": n, "holds": True}


def stored_counts(stage: str, stage_file: dict, process: str) -> dict:
    """The stage file's stored counts under candidate C, with the key path each was read from."""
    if stage == "stage1":
        cell = stage_file["by_candidate"][CANDIDATE]["by_process"][process]
        base = f"by_candidate.{CANDIDATE}.by_process[{process}]"
        return {"miss": cell["range_misses_the_true_value"]["count"],
                "reject": cell["early_years_test_rejects_a_flat_history"]["count"],
                "failures": cell["numerical_failures"]["count"],
                "keys": {"miss": f"{base}.range_misses_the_true_value.count",
                         "reject": f"{base}.early_years_test_rejects_a_flat_history.count",
                         "failures": f"{base}.numerical_failures.count"}}
    return {"miss": stage_file["range"]["by_process"][process]["count"],
            "reject": stage_file["early_years_test"]["by_process"][process]["count"],
            "failures": stage_file["numerical_failures"][process]["count"],
            "keys": {"miss": f"range.by_process[{process}].count", "reject": f"early_years_test.by_process[{process}].count",
                     "failures": f"numerical_failures[{process}].count"}}


def candidate_results(records: list, candidate: str = CANDIDATE) -> list:
    out = []
    for r in records:
        if candidate not in r.get("results", {}):
            raise Refused(f"dataset {r.get('k')} of {r.get('process')} carries no reading for candidate {candidate}: the "
                          "exercise stops")
        out.append(r["results"][candidate])
    return out


def check_counts(stage: str, stage_file: dict, process: str, records: list) -> dict:
    """Check 3: the count of ranges missing the true value (`miss`) and of early-years tests rejecting a flat history
    (`reject`), recomputed from the records under candidate C, equal the stage file's stored counts exactly. The count of
    numerical failures is also compared and recorded; it is not one of the specification's three checks and does not stop."""
    rs = candidate_results(records)
    got = {"miss": int(sum(bool(r["miss"]) for r in rs)), "reject": int(sum(bool(r["reject"]) for r in rs))}
    stored = stored_counts(stage, stage_file, process)
    differ = {k: {"recomputed": got[k], "stored": stored[k], "stored_at": stored["keys"][k]} for k in got if got[k] != stored[k]}
    if differ:
        raise Refused(f"check 3 fails for {process} in {stage}: the counts recomputed from the records under candidate "
                      f"{CANDIDATE} differ from the stage file's: {differ}. The exercise stops (specification, section 5)")
    fails = int(sum(r["failure"] is not None for r in rs))
    return {"check": "3. the range-miss and early-years-rejection counts recomputed from the records under candidate C equal "
                     "the stage file's stored counts exactly", "stage": stage, "process": process,
            "recomputed": got, "stored": {k: stored[k] for k in got}, "stored_at": {k: stored["keys"][k] for k in got},
            "holds": True,
            "also_compared_not_a_check_of_the_specification": {
                "numerical_failures_recomputed": fails, "numerical_failures_stored": stored["failures"],
                "stored_at": stored["keys"]["failures"], "agree": fails == stored["failures"]}}


# ================================================================================================================
# The figures
# ================================================================================================================

def computed(r: dict) -> bool:
    """The candidate computed an estimate: no failure recorded and a finite estimate (specification, section 4)."""
    e = r.get("estimate")
    return r.get("failure") is None and e is not None and math.isfinite(float(e))


NON_FINITE_LABEL = "no failure recorded but the estimate is not finite"


def left_out_cause(r: dict) -> str:
    if r.get("failure") is not None:
        return str(r["failure"].get("cause"))
    return NON_FINITE_LABEL


def moments(est: np.ndarray) -> dict:
    """Mean, standard deviation (n - 1 in the divisor), standard error (sd over the square root of n) and the interval
    of the mean plus and minus 1.96 standard errors, in log points. None where fewer than two values make a figure undefined."""
    n = len(est)
    mean = float(est.mean()) if n else None
    sd = float(est.std(ddof=1)) if n > 1 else None
    se = sd / math.sqrt(n) if sd is not None else None
    lo, hi = (mean - Z * se, mean + Z * se) if se is not None else (None, None)
    return {"mean": mean, "sd": sd, "se": se, "lo": lo, "hi": hi}


def mean_figure(records: list, candidate: str = CANDIDATE) -> dict:
    """The mean of the candidate's headline estimate over the datasets in which it computed one, with the count used, the
    count left out and the left-out by cause. Log points and percent (100 times the log-point figure)."""
    rs = candidate_results(records, candidate)
    use = [r for r in rs if computed(r)]
    left = [r for r in rs if not computed(r)]
    est = np.array([float(r["estimate"]) for r in use], dtype=float)
    m = moments(est)
    pct = lambda x: None if x is None else PERCENT * x  # noqa: E731
    return {"candidate": candidate, "over": "datasets in which the candidate computed an estimate (no failure recorded and a "
                                            "finite estimate)",
            "datasets": len(rs), "datasets_used": len(use), "datasets_left_out": len(left),
            "left_out_by_cause": dict(sorted(Counter(left_out_cause(r) for r in left).items())),
            "log_points": {"mean_estimate": m["mean"], "standard_deviation": m["sd"], "standard_error": m["se"],
                           "interval_of_the_mean_95": [m["lo"], m["hi"]]},
            "percent": {"mean_estimate": pct(m["mean"]), "standard_deviation": pct(m["sd"]), "standard_error": pct(m["se"]),
                        "interval_of_the_mean_95": [pct(m["lo"]), pct(m["hi"])]},
            "interval": "the mean plus and minus 1.96 standard errors; the standard deviation has n - 1 in its divisor",
            "percent_is": "100 times the log-point figure, as the stage reports and power_simulation.json give percent",
            "interval_contains_zero": None if m["lo"] is None else bool(m["lo"] <= 0.0 <= m["hi"])}


def agreement(records: list, names=STAGE1_CANDIDATES, tol: float = AGREEMENT_TOLERANCE) -> dict:
    """Stage 1 only: whether candidates A, B and C carry the same estimate on every dataset where all three computed one.
    The largest absolute difference is reported as it is. The tolerance that separates floating-point noise from a
    difference is the agent's reading (the specification names none); a difference above it is said, not hidden."""
    diffs = []
    by = [candidate_results(records, n) for n in names]
    for rs in zip(*by):
        if all(computed(x) for x in rs):
            e = [float(x["estimate"]) for x in rs]
            diffs.append(max(e) - min(e))
    d = np.array(diffs, dtype=float)
    largest = float(d.max()) if len(d) else None
    beyond = int((d > tol).sum())
    out = {"candidates": list(names), "datasets_compared": len(d), "largest_absolute_difference_log_points": largest,
           "datasets_differing_by_more_than_the_tolerance": beyond, "tolerance_log_points": tol,
           "tolerance_is": "the agent's reading of floating-point noise; the specification names no tolerance",
           "agree": beyond == 0}
    out["statement"] = ("the three candidates carry the same estimate, within the tolerance, on every dataset where all three "
                        "computed one" if beyond == 0 else
                        f"the candidates' estimates DIFFER by more than {tol} log points on {beyond} of {len(d)} datasets "
                        f"(largest {largest}); the specification's premise that the estimate is the same least-squares number "
                        "under every candidate does not hold in these records, and this is reported, not hidden")
    return out


def stored_realised_path(stage1_file: dict, process: str) -> dict:
    """Stage 1's stored realised-path statistics under candidate C, read by name and not recomputed."""
    rp = stage1_file["by_candidate"][CANDIDATE]["by_process"][process]["realised_path"]
    return {"source": f"{ic.PATHS['stage1']}, by_candidate.{CANDIDATE}.by_process[{process}].realised_path, read by name and "
                      "not recomputed",
            "over": rp.get("over"), "datasets_used": rp.get("datasets_used"),
            "slope_of_the_estimate_on_the_realised_change": rp.get("slope_of_the_estimate_on_the_realised_change"),
            "root_mean_square_error_log_points": rp.get("root_mean_square_error")}


def recomputed_realised_path(records: list) -> dict:
    """Stage 2's realised-path statistics, which its stored file does not hold, recomputed from the records with the
    comparison's own function (inference_comparison.realised_path, imported and not reimplemented)."""
    rp = ic.realised_path(candidate_results(records), [r["realised_change"] for r in records])
    return {"source": "recomputed from stage 2's per-dataset records under candidate C by inference_comparison.realised_path; "
                      f"{ic.PATHS['stage2']} holds no realised-path statistics",
            "over": rp.get("over"), "datasets_used": rp.get("datasets_used"),
            "slope_of_the_estimate_on_the_realised_change": rp.get("slope_of_the_estimate_on_the_realised_change"),
            "root_mean_square_error_log_points": rp.get("root_mean_square_error")}


def stage2_holds_realised_path(stage2_file: dict) -> bool:
    return "realised_path" in json.dumps(stage2_file)


def half_width(power: dict) -> float:
    x = power
    for k in HALF_WIDTH_PATH:
        if not isinstance(x, dict) or k not in x:
            raise Refused(f"power_simulation.json has no {'.'.join(HALF_WIDTH_PATH)}: the half-width beside the mean cannot be read")
        x = x[k]
    return float(x)


# ================================================================================================================
# The run
# ================================================================================================================

def compute(paths: Paths) -> dict:
    """Every check first, for both stages and both processes, then the figures. Returns the report; writes nothing."""
    files, hashes, records, checks = {}, {"stage_files": {}, "manifests": {}, "block_files": {}}, {}, []
    for stage in STAGES:
        sf, h = read_json(paths.stage_files[stage], f"the stored {stage} file is needed to check the records against")
        files[stage] = sf
        hashes["stage_files"][stage] = {"path": paths.stage_files[stage].name, "sha256": h}
        man, mh = read_json(paths.run_dirs[stage] / "manifest.json", f"the {stage} run's manifest is needed for check 1")
        hashes["manifests"][stage] = {"path": f"{stage}/manifest.json", "sha256": mh}
        checks.append(check_identity(stage, man, sf))
        n = int(sf["datasets_per_process"])
        for process in PROCESSES:
            got = read_process(paths.run_dirs[stage], process, n)
            hashes["block_files"][f"{stage}:{process}"] = {k: got[k] for k in ("blocks_read", "block_files_sha256",
                                                                                "block_files_sha256_is")}
            checks.append(check_records(stage, process, got["records"], n))
            checks.append(check_counts(stage, sf, process, got["records"]))
            records[(stage, process)] = got["records"]

    power, ph = read_json(paths.power_file, "the selected procedure's mean range half-width is read from it")
    hashes["power_simulation"] = {"path": paths.power_file.name, "sha256": ph}
    hw = half_width(power)
    spec_raw = paths.spec.read_bytes() if paths.spec.is_file() else None
    if spec_raw is None:
        raise Refused(f"{paths.spec} is missing: the output records the specification's sha256")
    hashes["specification"] = {"path": str(paths.spec.relative_to(ROOT)) if paths.spec.is_relative_to(ROOT) else paths.spec.name,
                               "sha256": sha256(spec_raw)}
    hashes["this_module"] = {"path": "pipeline/analysis/g12_mean_estimate.py", "sha256": sha256(Path(__file__).read_bytes())}

    s2_holds = stage2_holds_realised_path(files["stage2"])
    figures = {}
    for process in PROCESSES:
        named = process == G12
        figures[process] = {
            "is_the_named_figure": named,
            "label": ("G12's mean estimate with nothing planted, the named figure" if named else
                      "G11's mean estimate with nothing planted, beside G12's for the comparison the plan's sentence makes; "
                      "NOT the named figure"),
            "stage2_20000_datasets": mean_figure(records[("stage2", process)]),
            "stage1_2000_datasets": mean_figure(records[("stage1", process)]),
            "stage1_candidates_agree": agreement(records[("stage1", process)]),
            "realised_path": {"stage1_stored": stored_realised_path(files["stage1"], process),
                              "stage2_recomputed": recomputed_realised_path(records[("stage2", process)]),
                              "stage2_file_holds_realised_path_statistics": s2_holds}}

    return {
        "what_this_is": (
            "G12's mean estimate with nothing planted (session 24, exercise 4b), authorized by Joe on 2026-11-20 (D-113). The "
            "specification is docs/gate1/simulation-spec-4b-g12-mean-estimate-2026-11-20.md (sha256 under hashes.specification). "
            "It is the mean of candidate C's headline estimate over the G12 datasets of step E's stage 2 (20,000) and stage 1 "
            "(2,000), with G11's beside it labelled as not the named figure, computed from the preserved per-dataset records "
            "of stages 1 and 2. No dataset was drawn and no stage was rerun. Every price behind the records was made up; no "
            "price was read. It is not a fresh run of G12, not a threshold, and not a change to the fuel-mix control. The "
            "plan sets no threshold for a mean away from zero and none is set here. The plan, PREANALYSIS.md, is a draft "
            "pre-analysis plan and is not frozen."),
        "limit_read_from_the_code": LIMIT_READ_FROM_THE_CODE,
        "checks": checks,
        "figures": figures,
        "beside_the_mean": {
            "range_half_width_mean_pct": hw,
            "source": "power_simulation.json, " + ".".join(HALF_WIDTH_PATH) + " (percent), read by name and not recomputed",
            "why": "the selected procedure's mean range half-width on the headline set, so that the size of a mean can be judged"},
        "hashes_as_read": hashes,
    }


def refuse_if_exists(out: Path) -> None:
    if out.exists():
        raise Refused(f"{out} exists: the exercise writes its file once and does not overwrite it")


def write_once(out: Path, report: dict) -> None:
    text = json.dumps(report, indent=1, allow_nan=False) + "\n"
    with open(out, "x") as fh:                      # "x": fails rather than overwrite
        fh.write(text)


def main(argv: list[str] | None = None, paths: Paths | None = None) -> int:
    paths = paths or Paths()
    try:
        refuse_if_exists(paths.out)
        report = compute(paths)
        write_once(paths.out, report)
    except Refused as e:
        print(f"REFUSED: {e.why}", file=sys.stderr)
        return 2
    g = report["figures"][G12]
    for key in ("stage2_20000_datasets", "stage1_2000_datasets"):
        f = g[key]
        print(f"G12 {key}: mean {f['percent']['mean_estimate']}% (interval {f['percent']['interval_of_the_mean_95']}), "
              f"used {f['datasets_used']}, left out {f['datasets_left_out']} {f['left_out_by_cause']}")
    print(f"wrote {paths.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
