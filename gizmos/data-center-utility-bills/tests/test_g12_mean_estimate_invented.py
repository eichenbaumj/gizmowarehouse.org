"""G12's mean estimate with nothing planted (pipeline/analysis/g12_mean_estimate.py; D-113, exercise 4b), on INVENTED block
files, manifests, stage files and a power file written into pytest's tmp_path. No test opens data/interim/inference_comparison
or writes under data/frozen; every path the runner uses is passed to it through g12.Paths. Every estimate here is made up
and bears on nothing.
"""
from __future__ import annotations

import ast
import inspect
import json
import math
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import g12_mean_estimate as g12  # noqa: E402
from pipeline.analysis import inference_comparison as icp  # noqa: E402

FP = "f" * 64
N1, N2 = 50, 75                         # invented stage sizes: two and three blocks of 25
TOL = 1e-12                             # tolerance on every known answer, log points
HALF_WIDTH = 6.652                      # the invented power file's half-width (percent)
OFFSETS = (-0.02, -0.01, 0.0, 0.01, 0.02)


def est_g12(k: int) -> float:
    return 0.005 + OFFSETS[k % 5]


def est_g11(k: int) -> float:
    return -0.001 + OFFSETS[(k + 2) % 5]


def ok_result(name: str, e: float, covered: bool = True, early_rejected: bool = False) -> dict:
    return cd.result(name, estimate=e, covered=covered, early_rejected=early_rejected, lo=e - 0.05, hi=e + 0.05,
                     lo_state=cd.BOUNDED, hi_state=cd.BOUNDED)


def failed(name: str, cause: str, e: float = float("nan")) -> dict:
    return cd.result(name, estimate=e, failure={"cause": cause, "where": "fit", "detail": "invented"})


def make_records(process: str, n: int, names, est, special=None) -> list:
    """Records shaped as inference_comparison.one writes them. Every seventh dataset's range misses and every eleventh
    dataset's early-years test rejects, so the stored counts are not zero. `special[k]` replaces a dataset's readings."""
    special = special or {}
    out = []
    for k in range(n):
        if k in special:
            res = {c: special[k](c) for c in names}
        else:
            res = {c: ok_result(c, est(k), covered=k % 7 != 0, early_rejected=k % 11 == 0) for c in names}
        out.append({"process": process, "k": k, "realised_change": 0.01 * ((k * 37) % 23 - 11), "results": res})
    return out


def counts(records: list, c: str = "C") -> dict:
    rs = [r["results"][c] for r in records]
    return {"miss": sum(r["miss"] for r in rs), "reject": sum(r["reject"] for r in rs),
            "failures": sum(r["failure"] is not None for r in rs)}


def write_blocks(run_dir: Path, process: str, records: list, n: int) -> None:
    p = icp.PROCESSES.index(process)
    for pp, b, k0, k1 in icp.blocks(n, processes=[p]):
        blk = {"process": process, "p": pp, "block": b, "k_from": k0, "k_to": k1,
               "records": [r for r in records if k0 <= r["k"] < k1]}
        (run_dir / f"block_{pp:02d}_{b:05d}.json").write_text(json.dumps(blk, indent=1))


def make_world(tmp_path: Path, special: dict | None = None) -> tuple[g12.Paths, dict]:
    """An invented world: both run folders (G12 and G11 blocks only), their manifests, both stage files with counts made
    from the records, an invented power file, an invented specification file. `special[(stage, process)]` passes a
    dataset override to make_records."""
    special = special or {}
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    run_dirs = {s: tmp_path / "runs" / s for s in g12.STAGES}
    recs = {}
    for stage, n, names in (("stage1", N1, ("A", "B", "C")), ("stage2", N2, ("C",))):
        run_dirs[stage].mkdir(parents=True)
        seed = icp.SEEDS[stage]
        (run_dirs[stage] / "manifest.json").write_text(json.dumps(
            {"stage": stage, "seed": seed, "datasets_per_process": n, "candidates": list(names), "fingerprint_sha256": FP}))
        for proc, est in ((g12.G12, est_g12), (g12.G11, est_g11)):
            recs[(stage, proc)] = make_records(proc, n, names, est, special.get((stage, proc)))
            write_blocks(run_dirs[stage], proc, recs[(stage, proc)], n)
    procs = (g12.G12, g12.G11)
    s1 = {"seed": icp.SEEDS["stage1"], "datasets_per_process": N1, "candidates": ["A", "B", "C"], "fingerprint": {"sha256": FP},
          "by_candidate": {"C": {"by_process": {
              p: {"range_misses_the_true_value": {"count": counts(recs[("stage1", p)])["miss"]},
                  "early_years_test_rejects_a_flat_history": {"count": counts(recs[("stage1", p)])["reject"]},
                  "numerical_failures": {"count": counts(recs[("stage1", p)])["failures"]},
                  "realised_path": {"over": "datasets whose candidate computed an estimate", "datasets_used": N1,
                                    "slope_of_the_estimate_on_the_realised_change": 0.123 if p == g12.G12 else 0.456,
                                    "root_mean_square_error": 0.0789}} for p in procs}}}}
    s2 = {"candidate": "C", "seed": icp.SEEDS["stage2"], "datasets_per_process": N2, "fingerprint": {"sha256": FP},
          "range": {"by_process": {p: {"count": counts(recs[("stage2", p)])["miss"]} for p in procs}},
          "early_years_test": {"by_process": {p: {"count": counts(recs[("stage2", p)])["reject"]} for p in procs}},
          "numerical_failures": {p: {"count": counts(recs[("stage2", p)])["failures"]} for p in procs}}
    stage_files = {"stage1": frozen / "inference_comparison_stage1.json", "stage2": frozen / "inference_validation_stage2.json"}
    stage_files["stage1"].write_text(json.dumps(s1))
    stage_files["stage2"].write_text(json.dumps(s2))
    power = frozen / "power_simulation.json"
    power.write_text(json.dumps({"new_host_estimate": {"2%": {"headline_set": {"nothing_planted": {"range_half_width_mean": HALF_WIDTH}}}}}))
    spec = tmp_path / "spec.md"
    spec.write_text("invented specification\n")
    paths = g12.Paths(run_dirs=run_dirs, stage_files=stage_files, power_file=power, out=frozen / "g12_out.json", spec=spec)
    return paths, recs


def edit_json(path: Path, fn) -> None:
    d = json.loads(path.read_text())
    fn(d)
    path.write_text(json.dumps(d))


def expected(values: list) -> dict:
    """The known answer, computed with the statistics module, independently of numpy."""
    m, sd = statistics.fmean(values), statistics.stdev(values)
    se = sd / math.sqrt(len(values))
    return {"mean": m, "sd": sd, "se": se, "lo": m - 1.96 * se, "hi": m + 1.96 * se}


def assert_figure(f: dict, values: list) -> None:
    e = expected(values)
    lp, pc = f["log_points"], f["percent"]
    assert lp["mean_estimate"] == pytest.approx(e["mean"], abs=TOL)
    assert lp["standard_deviation"] == pytest.approx(e["sd"], abs=TOL)
    assert lp["standard_error"] == pytest.approx(e["se"], abs=TOL)
    assert lp["interval_of_the_mean_95"] == pytest.approx([e["lo"], e["hi"]], abs=TOL)
    assert pc["mean_estimate"] == pytest.approx(100 * e["mean"], abs=100 * TOL)
    assert pc["interval_of_the_mean_95"] == pytest.approx([100 * e["lo"], 100 * e["hi"]], abs=100 * TOL)
    assert f["datasets_used"] == len(values)
    assert f["interval_contains_zero"] == (e["lo"] <= 0 <= e["hi"])


# ---- group 1: the mean with a known answer -----------------------------------------------------------------------------

def test_mean_standard_deviation_standard_error_and_interval_known_answer():
    recs = make_records(g12.G12, N2, ("C",), est_g12)
    f = g12.mean_figure(recs)
    # by hand: mean 0.005; deviations -0.02..0.02 fifteen times each, so the sum of squares is 15 x 0.001 = 0.015
    sd = math.sqrt(0.015 / (N2 - 1))
    assert f["log_points"]["mean_estimate"] == pytest.approx(0.005, abs=TOL)
    assert f["log_points"]["standard_deviation"] == pytest.approx(sd, abs=TOL)
    assert f["log_points"]["standard_error"] == pytest.approx(sd / math.sqrt(N2), abs=TOL)
    assert_figure(f, [est_g12(k) for k in range(N2)])
    assert f["datasets_left_out"] == 0 and f["left_out_by_cause"] == {}
    assert f["interval_contains_zero"] is False          # 0.005 +/- 1.96 x 0.00164 lies above zero


def test_interval_contains_zero_when_the_mean_is_zero():
    recs = make_records(g12.G12, 50, ("C",), lambda k: OFFSETS[k % 5])
    f = g12.mean_figure(recs)
    assert f["log_points"]["mean_estimate"] == pytest.approx(0.0, abs=TOL)
    assert f["interval_contains_zero"] is True


# ---- group 2: a failed dataset and a non-finite estimate are counted, left out and reported by cause ----------------

def test_failed_and_non_finite_datasets_left_out_and_reported_by_cause():
    special = {3: lambda c: failed(c, cd.RANK_DEFICIENT, e=5.0),            # a failure that still carries a finite estimate
               8: lambda c: failed(c, cd.NON_FINITE_ADJUSTMENT),
               13: lambda c: failed(c, cd.RANK_DEFICIENT),
               4: lambda c: cd.result(c, estimate=float("nan"), covered=True, early_rejected=False,
                                      lo=0.0, hi=0.0, lo_state=cd.BOUNDED, hi_state=cd.BOUNDED),
               9: lambda c: cd.result(c, estimate=float("inf"), covered=True, early_rejected=False,
                                      lo=0.0, hi=0.0, lo_state=cd.BOUNDED, hi_state=cd.BOUNDED)}
    recs = make_records(g12.G12, N2, ("C",), est_g12, special)
    f = g12.mean_figure(recs)
    assert f["datasets"] == N2 and f["datasets_used"] == N2 - 5 and f["datasets_left_out"] == 5
    assert f["left_out_by_cause"] == {cd.NON_FINITE_ADJUSTMENT: 1, cd.RANK_DEFICIENT: 2, g12.NON_FINITE_LABEL: 2}
    assert_figure(f, [est_g12(k) for k in range(N2) if k not in special])


def test_failed_dataset_through_the_whole_run_and_json_round_trip(tmp_path):
    special = {("stage2", g12.G12): {5: lambda c: failed(c, cd.RANK_DEFICIENT, e=9.0)}}
    paths, _ = make_world(tmp_path, special)
    assert g12.main(paths=paths) == 0
    out = json.loads(paths.out.read_text())
    f = out["figures"][g12.G12]["stage2_20000_datasets"]
    assert f["left_out_by_cause"] == {cd.RANK_DEFICIENT: 1}
    assert f["log_points"]["mean_estimate"] == pytest.approx(statistics.fmean([est_g12(k) for k in range(N2) if k != 5]), abs=TOL)
    c3 = [c for c in out["checks"] if c.get("process") == g12.G12 and c["stage"] == "stage2" and c["check"].startswith("3.")][0]
    assert c3["also_compared_not_a_check_of_the_specification"]["numerical_failures_recomputed"] == 1
    assert c3["also_compared_not_a_check_of_the_specification"]["agree"] is True


# ---- group 3: each of the three checks refuses in words, and nothing is written ------------------------------------

def run_refused(paths: g12.Paths, capsys) -> str:
    assert g12.main(paths=paths) == 2
    assert not paths.out.exists()
    return capsys.readouterr().err


def test_check1_refuses_when_the_fingerprint_differs(tmp_path, capsys):
    paths, _ = make_world(tmp_path)
    edit_json(paths.stage_files["stage2"], lambda d: d["fingerprint"].update(sha256="0" * 64))
    with pytest.raises(g12.Refused, match="check 1 fails for stage2.*fingerprint_sha256"):
        g12.compute(paths)
    assert "check 1 fails" in run_refused(paths, capsys)


@pytest.mark.parametrize("key,value", [("seed", 1), ("datasets_per_process", N1 + 25), ("candidates", ["C"]), ("stage", "stage2")])
def test_check1_refuses_when_seed_size_candidates_or_stage_differ(tmp_path, capsys, key, value):
    paths, _ = make_world(tmp_path)
    edit_json(paths.run_dirs["stage1"] / "manifest.json", lambda d: d.update({key: value}))
    with pytest.raises(g12.Refused, match=f"check 1 fails for stage1.*{key}"):
        g12.compute(paths)
    assert "check 1 fails" in run_refused(paths, capsys)


def test_check1_passes_and_records_what_was_compared(tmp_path):
    paths, _ = make_world(tmp_path)
    rep = g12.compute(paths)
    c1 = [c for c in rep["checks"] if c["check"].startswith("1.")]
    assert len(c1) == 2 and all(c["holds"] for c in c1)
    assert c1[0]["compared"]["fingerprint_sha256"] == FP


def test_check2_refuses_on_a_missing_block_naming_it(tmp_path, capsys):
    paths, _ = make_world(tmp_path)
    p = icp.PROCESSES.index(g12.G11)
    (paths.run_dirs["stage2"] / f"block_{p:02d}_00001.json").unlink()
    with pytest.raises(g12.Refused, match=f"block block_{p:02d}_00001.json of {g12.G11}.*missing"):
        g12.compute(paths)
    assert "is missing" in run_refused(paths, capsys)


def test_check2_refuses_on_a_repeated_dataset_number(tmp_path, capsys):
    paths, _ = make_world(tmp_path)
    p = icp.PROCESSES.index(g12.G12)
    f = paths.run_dirs["stage1"] / f"block_{p:02d}_00001.json"
    edit_json(f, lambda d: d["records"][3].update(k=29))                # dataset 28 becomes a second 29
    with pytest.raises(g12.Refused, match=r"check 2 fails .*repeated: \[29\].*absent: \[28\]"):
        g12.compute(paths)
    assert "check 2 fails" in run_refused(paths, capsys)


def test_check2_refuses_on_an_absent_dataset_number(tmp_path, capsys):
    paths, _ = make_world(tmp_path)
    p = icp.PROCESSES.index(g12.G12)
    edit_json(paths.run_dirs["stage2"] / f"block_{p:02d}_00002.json", lambda d: d["records"].pop())
    with pytest.raises(g12.Refused, match=rf"check 2 fails .*{N2 - 1} records, not {N2}.*absent: \[{N2 - 1}\]"):
        g12.compute(paths)
    assert "check 2 fails" in run_refused(paths, capsys)


def test_reader_refuses_a_block_whose_header_is_not_its_name(tmp_path, capsys):
    paths, _ = make_world(tmp_path)
    p = icp.PROCESSES.index(g12.G12)
    edit_json(paths.run_dirs["stage2"] / f"block_{p:02d}_00000.json", lambda d: d.update(k_to=24))
    with pytest.raises(g12.Refused, match="does not carry the header its name gives"):
        g12.compute(paths)
    run_refused(paths, capsys)


@pytest.mark.parametrize("stage,key", [("stage1", "range_misses_the_true_value"), ("stage1", "early_years_test_rejects_a_flat_history"),
                                       ("stage2", "range"), ("stage2", "early_years_test")])
@pytest.mark.parametrize("delta", [1, -1])
def test_check3_refuses_when_a_stored_count_is_off_by_one(tmp_path, capsys, stage, key, delta):
    paths, _ = make_world(tmp_path)

    def bump(d):
        cell = d["by_candidate"]["C"]["by_process"][g12.G11][key] if stage == "stage1" else d[key]["by_process"][g12.G11]
        cell["count"] += delta
    edit_json(paths.stage_files[stage], bump)
    with pytest.raises(g12.Refused, match=f"check 3 fails for {g12.G11} in {stage}"):
        g12.compute(paths)
    assert "check 3 fails" in run_refused(paths, capsys)


def test_check3_passes_on_the_stored_counts_and_names_their_keys(tmp_path):
    paths, recs = make_world(tmp_path)
    rep = g12.compute(paths)
    c3 = {(c["stage"], c["process"]): c for c in rep["checks"] if c["check"].startswith("3.")}
    assert set(c3) == {(s, p) for s in g12.STAGES for p in (g12.G12, g12.G11)}
    want = counts(recs[("stage2", g12.G12)])
    assert c3[("stage2", g12.G12)]["recomputed"] == {"miss": want["miss"], "reject": want["reject"]} and want["miss"] > 0
    assert c3[("stage2", g12.G12)]["stored_at"]["miss"] == f"range.by_process[{g12.G12}].count"
    assert c3[("stage1", g12.G12)]["stored_at"]["reject"] == \
        f"by_candidate.C.by_process[{g12.G12}].early_years_test_rejects_a_flat_history.count"


# ---- group 4: the candidates' agreement check in stage 1 ---------------------------------------------------------------

def test_agreement_holds_when_the_candidates_carry_the_same_estimate():
    a = g12.agreement(make_records(g12.G12, N1, ("A", "B", "C"), est_g12))
    assert a["agree"] is True and a["datasets_compared"] == N1 and a["largest_absolute_difference_log_points"] == 0.0


def test_agreement_finds_a_planted_difference_and_says_so():
    special = {7: lambda c: ok_result(c, est_g12(7) + (1e-6 if c == "A" else 0.0)),
               9: lambda c: failed(c, cd.RANK_DEFICIENT) if c == "B" else ok_result(c, est_g12(9) + (0.5 if c == "C" else 0.0))}
    a = g12.agreement(make_records(g12.G12, N1, ("A", "B", "C"), est_g12, special))
    assert a["agree"] is False
    assert a["datasets_compared"] == N1 - 1                          # dataset 9: B failed, so it is not compared
    assert a["datasets_differing_by_more_than_the_tolerance"] == 1
    assert a["largest_absolute_difference_log_points"] == pytest.approx(1e-6, abs=1e-12)
    assert "DIFFER" in a["statement"]


def test_agreement_difference_reaches_the_written_file(tmp_path):
    special = {("stage1", g12.G12): {2: lambda c: ok_result(c, est_g12(2) + (1e-4 if c == "B" else 0.0))}}
    paths, _ = make_world(tmp_path, special)
    assert g12.main(paths=paths) == 0
    a = json.loads(paths.out.read_text())["figures"][g12.G12]["stage1_candidates_agree"]
    assert a["agree"] is False and a["largest_absolute_difference_log_points"] == pytest.approx(1e-4, abs=1e-12)


# ---- group 5: the output is written once ---------------------------------------------------------------------------

def test_refuses_when_the_output_exists_and_leaves_it_untouched(tmp_path, capsys):
    paths, _ = make_world(tmp_path)
    paths.out.write_text("already here\n")
    assert g12.main(paths=paths) == 2
    assert paths.out.read_text() == "already here\n"
    assert "exists" in capsys.readouterr().err
    with pytest.raises(g12.Refused, match="exists"):
        g12.refuse_if_exists(paths.out)


def test_whole_run_writes_once_with_the_named_parts(tmp_path, monkeypatch):
    paths, recs = make_world(tmp_path)

    def no_listing(*a, **k):
        raise AssertionError("the runner listed a folder")
    for name in ("iterdir", "glob", "rglob"):
        monkeypatch.setattr(Path, name, no_listing)
    assert g12.main(paths=paths) == 0
    out = json.loads(paths.out.read_text())
    assert out["limit_read_from_the_code"] == g12.LIMIT_READ_FROM_THE_CODE
    assert g12.LIMIT_READ_FROM_THE_CODE.startswith("In G12 the fuel shock is a national walk")
    assert g12.LIMIT_READ_FROM_THE_CODE.endswith("written before any record was read.")
    assert "D-113" in out["what_this_is"] and "not frozen" in out["what_this_is"] and "no price was read" in out["what_this_is"]
    assert len(out["checks"]) == 2 + 2 * 2 * 2 and all(c["holds"] for c in out["checks"])
    g = out["figures"][g12.G12]
    assert g["is_the_named_figure"] is True and out["figures"][g12.G11]["is_the_named_figure"] is False
    assert "NOT the named figure" in out["figures"][g12.G11]["label"]
    assert_figure(g["stage2_20000_datasets"], [est_g12(k) for k in range(N2)])
    assert_figure(g["stage1_2000_datasets"], [est_g12(k) for k in range(N1)])
    assert_figure(out["figures"][g12.G11]["stage2_20000_datasets"], [est_g11(k) for k in range(N2)])
    assert out["beside_the_mean"]["range_half_width_mean_pct"] == HALF_WIDTH
    rp = g["realised_path"]
    assert rp["stage1_stored"]["slope_of_the_estimate_on_the_realised_change"] == 0.123
    assert rp["stage2_file_holds_realised_path_statistics"] is False
    ref = icp.realised_path([r["results"]["C"] for r in recs[("stage2", g12.G12)]], [r["realised_change"] for r in recs[("stage2", g12.G12)]])
    assert rp["stage2_recomputed"]["slope_of_the_estimate_on_the_realised_change"] == ref["slope_of_the_estimate_on_the_realised_change"]
    assert rp["stage2_recomputed"]["root_mean_square_error_log_points"] == ref["root_mean_square_error"]
    h = out["hashes_as_read"]
    import hashlib
    assert h["stage_files"]["stage1"]["sha256"] == hashlib.sha256(paths.stage_files["stage1"].read_bytes()).hexdigest()
    assert h["manifests"]["stage2"]["sha256"] == hashlib.sha256((paths.run_dirs["stage2"] / "manifest.json").read_bytes()).hexdigest()
    assert h["specification"]["sha256"] == hashlib.sha256(paths.spec.read_bytes()).hexdigest()
    assert h["this_module"]["sha256"] == hashlib.sha256(Path(g12.__file__).read_bytes()).hexdigest()
    assert g12.main(paths=paths) == 2                                  # a second run refuses


def test_default_paths_are_the_specifications():
    root = Path(g12.__file__).resolve().parents[2]
    assert g12.RUN_DIRS == {"stage1": root / "data/interim/inference_comparison/stage1",
                            "stage2": root / "data/interim/inference_comparison/stage2"}
    assert g12.OUT == root / "data/frozen/g12_mean_estimate_nothing_planted.json"
    assert g12.STAGE_FILES == {"stage1": root / "data/frozen/inference_comparison_stage1.json",
                               "stage2": root / "data/frozen/inference_validation_stage2.json"}
    assert (g12.G11, g12.G12) == icp.WALK_PROCESSES and g12.CANDIDATE == "C"


# ---- group 6: the source names no stage function and no forbidden folder ------------------------------------------

FORBIDDEN_CALLS = {"stage1", "stage2", "run_blocks", "benchmark", "benchmark_timings", "write_budget", "real_design",
                   "build_context", "dataset", "draw", "one", "_block", "_write_json", "load_outcomes", "read_listed_outcomes",
                   "iterdir", "glob", "rglob", "listdir", "scandir", "walk", "write_text", "write_bytes", "unlink", "mkdir"}


def scan(src: str) -> list:
    """What the source would do that the exercise forbids: a forbidden call, a string naming the folder of real outcomes,
    or an open() in any mode other than reading or exclusive creation."""
    bad = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in FORBIDDEN_CALLS:
                bad.append(f"call {name}")
            if name == "open" and len(node.args) > 1:
                mode = getattr(node.args[1], "value", None)
                if mode not in ("r", "rb", "x"):
                    bad.append(f"open mode {mode!r}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "blind" in node.value:
            bad.append(f"string {node.value[:40]!r}")
    return bad


def test_source_names_no_stage_function_and_no_forbidden_folder():
    src = inspect.getsource(g12)
    assert scan(src) == []
    assert "blind" not in src


def test_scan_catches_planted_lines():
    found = scan("ic.stage1(x)\nic.run_blocks(1)\nopen('data/blind/p.parquet', 'w')\nPath('a').iterdir()\n")
    assert "call stage1" in found and "call run_blocks" in found and "call iterdir" in found
    assert "open mode 'w'" in found and any(f.startswith("string") for f in found)


def test_interim_paths_are_only_the_two_run_folders():
    src = inspect.getsource(g12)
    strings = [n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "interim" in strings and "inference_comparison" in strings
    assert not any(s in strings for s in ("availability", "water", "snapshot-2026-11-14"))
