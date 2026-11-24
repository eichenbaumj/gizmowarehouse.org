"""The results writer and the execution coordinator (pipeline/analysis/execute_outcomes.py). Invented inputs only.

Every directory written is under pytest's tmp_path. No file under data/ is read. The door to outcomes is replaced by an
invented one everywhere but in two tests: one passes an invented reader and an invented plan state through the real
door's own parameters with the gate path monkeypatched to a file under tmp_path and the variable set through
monkeypatch, and one shows the real door refusing (the gate path monkeypatched to a file that does not exist). The real
gate file is never created. Git is replaced by an invented runner, or run in a repository built under tmp_path.
"""
from __future__ import annotations

import builtins
import copy
import dataclasses
import hashlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import execute_outcomes as eo  # noqa: E402
from pipeline.analysis import outcome_frames as of  # noqa: E402
from pipeline.analysis import run_outcomes as ro  # noqa: E402

IDS = [e.id for e in ro.ORDER_OF_UNBLINDING]
U, C, IAS = "reconciliation_row_U", "reconciliation_row_C", "inventory_against_sales"
COMMIT = "c" * 40
PKG_OK = {"package": "diff-diff", "pinned_version": "4.0.0", "imports": True, "version": "4.0.0", "why_not": None}
PKG_MISSING = {"package": "diff-diff", "pinned_version": "4.0.0", "imports": False, "version": None,
               "why_not": "PackageMissing: invented"}
SENTINEL = 12345.678


TREES = {"pipeline": "1" * 40, "tests": "2" * 40, "PREANALYSIS.md": "3" * 40}      # invented git object ids


def fake_git(commit=COMMIT, porcelain="", fail=None, trees=None):
    """An invented git. `trees` replaces the invented object id of a path (None: that id cannot be read)."""
    calls = []
    ids = {**TREES, **(trees or {})}

    def git(args):
        calls.append(list(args))
        if fail == args[0]:
            return 128, ""
        if args[0] == "rev-parse":
            if str(args[-1]).startswith("HEAD:./"):
                v = ids.get(str(args[-1])[len("HEAD:./"):])
                return (0, v + "\n") if v else (128, "")
            return 0, commit + "\n"
        if args[0] == "status":
            return 0, porcelain
        return 1, ""
    git.calls = calls
    return git


def prov(inputs_are=ro.INVENTED_INPUTS, git=None, **kw):
    return eo.provenance(inputs_are=inputs_are, git=git or fake_git(), package_state=kw.pop("package_state", PKG_OK),
                         **kw)


class Recorder:
    """An invented run: records each call, returns an invented record, raises or fails for the ids named."""

    def __init__(self, raise_for=(), fail_for=(), on_call=None):
        self.calls, self.raise_for, self.fail_for, self.on_call = [], set(raise_for), set(fail_for), on_call

    def __call__(self, entry_id, inputs, outcomes):
        self.calls.append(entry_id)
        if self.on_call:
            self.on_call(entry_id)
        if entry_id in self.raise_for:
            raise RuntimeError(f"invented failure raised for {entry_id}")
        rec = ro.REGISTRY_BY_ID[entry_id].as_record()
        if entry_id in self.fail_for:
            rec.update(estimated=False, results={"invented set": {"estimated": False,
                                                                  "failure_in_words": "invented: the slope could not be computed"}},
                       failures_in_words={"invented set": "invented: the slope could not be computed"})
            return rec
        rec.update(estimated=True, results={"invented set": {"estimated": True, "estimate": 0.25}})
        return rec


def coord(out, run=None, p=None, inputs=None, outcomes=None):
    return eo.Coordinator(out, inputs, outcomes, provenance=p or prov(), run=run if run is not None else Recorder())


def manifest(out):
    return json.loads((Path(out) / eo.MANIFEST).read_text())


def entry_ids(out):
    return [r["entry_id"] for r in manifest(out)["records"] if r["kind"] == eo.KIND_ENTRY]


def strict_load(text):
    def reject(c):
        raise ValueError(f"non-strict JSON constant {c}")
    return json.loads(text, parse_constant=reject)


# ---- the order -------------------------------------------------------------------------------------------------------------

def test_the_registry_order_starts_with_rows_u_and_c_and_the_inventory_check():
    assert IDS[:3] == [U, C, IAS]
    assert eo.check_recorded_order() == IDS


def test_a_full_sequence_writes_every_entry_in_the_recorded_order(tmp_path):
    rec = Recorder()
    out = tmp_path / "out"
    done = coord(out, rec).run()
    assert rec.calls == IDS
    assert entry_ids(out) == IDS
    assert entry_ids(out)[:3] == [U, C, IAS]
    assert [r["sequence"] for r in manifest(out)["records"]] == list(range(1, len(IDS) + 1))
    stages = [r["stage"] for r in manifest(out)["records"]]
    assert stages[:3] == ["row_U", "row_C", "inventory_against_sales"] and set(stages[3:]) == {"remaining"}
    assert done["next_expected"] is None and len(done["written"]) == len(IDS)
    # the report has one section per entry, in the same order
    report = (out / eo.REPORT).read_text()
    pos = [report.index(f"[record {i:04d}] {e}") for i, e in enumerate(IDS, 1)]
    assert pos == sorted(pos)


def test_requests_out_of_order_and_twice_are_refused_and_nothing_is_written_for_them(tmp_path):
    out = tmp_path / "out"
    rec = Recorder()
    c = coord(out, rec)
    with pytest.raises(eo.OrderRefused, match="next entry expected is reconciliation_row_U"):
        c.run_entry(C)
    assert not out.exists() and rec.calls == []
    c.run_entry(U)
    with pytest.raises(eo.OrderRefused, match="next entry expected is reconciliation_row_C"):
        c.run_entry(IAS)
    c.run_entry(C)
    with pytest.raises(eo.OrderRefused, match="next entry expected is inventory_against_sales"):
        c.run_entry("main_headline_set")
    with pytest.raises(eo.OrderRefused, match="already written and reported.*never run twice"):
        c.run_entry(U)
    with pytest.raises(eo.OrderRefused, match="not in the executable order"):
        c.run_entry("reconciliation_row_M")
    assert entry_ids(out) == [U, C] and rec.calls == [U, C]
    assert sorted(p.name for p in out.iterdir()) == ["0001_reconciliation_row_U.json", "0002_reconciliation_row_C.json",
                                                     eo.MANIFEST, eo.REPORT]


def test_a_stage_named_out_of_order_is_refused(tmp_path):
    out = tmp_path / "out"
    rec = Recorder()
    c = coord(out, rec)
    for st in ("row_C", "inventory_against_sales", "remaining"):
        with pytest.raises(eo.OrderRefused, match="refused out of order: the next entry expected is reconciliation_row_U"):
            c.run_stage(st)
    with pytest.raises(eo.OrderRefused, match="is not a stage"):
        c.run_stage("bogus")
    with pytest.raises(eo.OrderRefused, match="is not a stage"):
        c.run(through="bogus")
    assert rec.calls == [] and not out.exists()
    c.run_stage("row_U")
    with pytest.raises(eo.OrderRefused, match="already written"):
        c.run_stage("row_U")
    with pytest.raises(eo.OrderRefused, match="next entry expected is reconciliation_row_C"):
        c.run_stage("remaining")
    assert rec.calls == [U]


def test_through_stops_where_asked_and_a_second_coordinator_takes_up_at_the_next_entry(tmp_path):
    out = tmp_path / "out"
    r1 = Recorder()
    d1 = coord(out, r1).run(through="row_C")
    assert r1.calls == [U, C] and entry_ids(out) == [U, C] and d1["next_expected"] == IAS
    r2 = Recorder()
    c2 = coord(out, r2, p=prov())                    # a later process: a new provenance with its own time
    assert c2.next_expected() == IAS
    c2.run(through="inventory_against_sales")
    assert r2.calls == [IAS]
    r3 = Recorder()
    d3 = coord(out, r3).run()
    assert r3.calls == IDS[3:] and entry_ids(out) == IDS and d3["next_expected"] is None
    r4 = Recorder()
    assert coord(out, r4).run()["written"] == [] and r4.calls == []


def test_the_first_three_ids_check_refuses_an_altered_start(monkeypatch, tmp_path):
    order = list(ro.ORDER_OF_UNBLINDING)
    swapped = (order[1], order[0], *order[2:])
    monkeypatch.setattr(ro, "ORDER_OF_UNBLINDING", swapped)
    with pytest.raises(eo.OrderRefused, match="begins"):
        coord(tmp_path / "out")
    monkeypatch.setattr(ro, "ORDER_OF_UNBLINDING", (order[0], order[2], order[1], *order[3:]))
    with pytest.raises(eo.OrderRefused, match="begins"):
        coord(tmp_path / "out")
    monkeypatch.setattr(ro, "ORDER_OF_UNBLINDING", tuple(order[3:]))
    with pytest.raises(eo.OrderRefused, match="begins"):
        coord(tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_a_manifest_under_another_order_or_a_damaged_directory_is_not_taken_up(tmp_path, monkeypatch):
    out = tmp_path / "out"
    coord(out).run(through="row_C")
    p = out / "0001_reconciliation_row_U.json"
    os.chmod(p, 0o644)
    p.write_text(p.read_text().replace('"estimated": true', '"estimated": false', 1))
    with pytest.raises(eo.DirectoryDamaged, match="sha256"):
        coord(out)
    out2 = tmp_path / "out2"
    coord(out2).run(through="row_U")
    order = list(ro.ORDER_OF_UNBLINDING)
    monkeypatch.setattr(ro, "ORDER_OF_UNBLINDING", tuple(order[:3] + order[4:]))
    with pytest.raises(eo.OrderRefused, match="another order"):
        coord(out2)


# ---- reported before the next runs ---------------------------------------------------------------------------------------

def test_each_entry_is_written_and_reported_before_the_next_is_run(tmp_path):
    out = tmp_path / "out"
    seen = []

    def check(entry_id):
        i = IDS.index(entry_id)
        if i == 0:
            seen.append(not (out / eo.MANIFEST).exists())
            return
        prev = IDS[i - 1]
        fname = f"{i:04d}_{prev}.json"
        man = json.loads((out / eo.MANIFEST).read_text())
        listed = [r for r in man["records"] if r["entry_id"] == prev]
        file_ok = (out / fname).exists()
        sha_ok = bool(listed) and hashlib.sha256((out / fname).read_bytes()).hexdigest() == listed[0]["sha256"]
        report_ok = f"[record {i:04d}] {prev}" in (out / eo.REPORT).read_text()
        seen.append(file_ok and sha_ok and report_ok)

    coord(out, Recorder(on_call=check)).run()
    assert len(seen) == len(IDS) and all(seen)


# ---- provenance ---------------------------------------------------------------------------------------------------------------

def test_every_record_carries_the_full_provenance(tmp_path, monkeypatch):
    gate = tmp_path / "no_gate_here"
    monkeypatch.setattr(ro.panel, "GATE_FILE", gate)
    monkeypatch.delenv(ro.AUTH_ENV, raising=False)
    out = tmp_path / "out"
    p = prov(outcome_record={"frame_fingerprint": "f" * 64}, assembled_record={"side": {"counts": 3}})
    coord(out, p=p).run(through="inventory_against_sales")
    for line in manifest(out)["records"]:
        rec = strict_load((out / line["file"]).read_text())
        pv = rec["provenance"]
        assert pv["frozen_commit"] == ro.FREEZE_COMMIT == "ea426c4b3c971fcf826bdda1fd7a3f3e6bb9fb23"
        assert pv["approved_specification_commit"] == ro.APPROVED_SPECIFICATION_COMMIT
        assert pv["code"]["commit"] == COMMIT and pv["code"]["tree_clean"] is True
        assert pv["code"]["code_identity"] == TREES and pv["code"]["established"] is True
        assert pv["gate"] == {"gate_file": "no_gate_here", "gate_file_exists": False,
                              "authorization_variable": ro.AUTH_ENV, "authorization_variable_is_1": False}
        assert pv["outcome_file_hash"] == "f" * 64
        assert pv["inputs_are"] == ro.INVENTED_INPUTS
        assert pv["assembled_inputs_record_fingerprint"] == eo.fingerprint_record({"side": {"counts": 3}})
        assert pv["interpreter"]["python_version"] and pv["interpreter"]["version"] == sys.version
        assert set(pv["libraries"]) == {"numpy", "pandas", "scipy", "statsmodels"}
        assert pv["libraries"]["numpy"] == np.__version__ and pv["libraries"]["pandas"] == pd.__version__
        assert pv["pinned_package"]["imports"] is True and pv["pinned_package"]["version"] == "4.0.0"
        assert pv["platform"]["system"] and pv["time_utc"]
        assert not str(pv["interpreter"]["executable"]).startswith(str(Path.home()))


def test_provenance_says_in_words_when_no_outcome_was_read():
    p = prov()
    assert p["outcome_file_hash"] is None and "no outcome was read" in p["outcome_file_hash_in_words"]
    with pytest.raises(ValueError, match="inputs_are"):
        eo.provenance(inputs_are="something else", git=fake_git(), package_state=PKG_OK)


def test_the_real_pinned_package_check_reports_this_interpreter():
    st = eo.pinned_package_state()
    assert st["pinned_version"] == "4.0.0"
    if st["imports"]:
        assert st["version"] == "4.0.0" and st["why_not"] is None
    else:
        assert st["version"] is None and st["why_not"]


def _repo(tmp_path):
    r = tmp_path / "repo"
    (r / "pipeline").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "pipeline" / "m.py").write_text("x = 1\n")
    (r / "tests" / "t.py").write_text("y = 1\n")
    (r / "PREANALYSIS.md").write_text("plan\n")
    g = ["git", "-c", "user.name=invented", "-c", "user.email=invented@example.invalid", "-c", "commit.gpgsign=false"]
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "-q"], cwd=r, check=True, env=env)
    subprocess.run([*g, "add", "-A"], cwd=r, check=True, env=env)
    subprocess.run([*g, "commit", "-q", "-m", "invented"], cwd=r, check=True, env=env)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r, capture_output=True, text=True, check=True).stdout.strip()
    return r, head


def test_code_state_on_a_repository_built_under_tmp_path(tmp_path, monkeypatch):
    # git finds its repository from the folder alone, looks no higher than tmp_path, and uses no global or system
    # configuration, for every call below and not only the three that build the repository
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    r, head = _repo(tmp_path)
    st = eo.code_state(root=r)
    assert st["established"] and st["commit"] == head and st["tree_clean"] is True
    for path in ("pipeline", "tests", "PREANALYSIS.md"):
        want = subprocess.run(["git", "rev-parse", f"HEAD:{path}"], cwd=r, capture_output=True, text=True,
                              check=True).stdout.strip()
        assert st["code_identity"][path] == want and len(want) == 40
    (r / "pipeline" / "m.py").write_text("x = 2\n")
    assert eo.code_state(root=r)["tree_clean"] is False
    subprocess.run(["git", "checkout", "-q", "--", "pipeline/m.py"], cwd=r, check=True)
    (r / "tests" / "new_untracked.py").write_text("z = 1\n")
    assert eo.code_state(root=r)["tree_clean"] is False
    (r / "tests" / "new_untracked.py").unlink()
    (r / "elsewhere.txt").write_text("not code\n")
    assert eo.code_state(root=r)["tree_clean"] is True          # only pipeline, tests and the plan are checked
    plain = tmp_path / "not_a_repo"
    plain.mkdir()
    # git looks no higher than tmp_path, so a temporary folder that lies inside a repository is never read as that one
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    st = eo.code_state(root=plain, git=None)
    assert st["established"] is False
    assert st["commit"] is None and st["tree_clean"] is None and st["why"]


def test_code_state_with_an_invented_git_that_fails():
    st = eo.code_state(git=fake_git(fail="status"))
    assert st["commit"] == COMMIT and st["tree_clean"] is None and not st["established"] and "status" in st["why"]
    st = eo.code_state(git=fake_git(fail="rev-parse"))
    assert st["commit"] is None and not st["established"]
    st = eo.code_state(git=fake_git(trees={"tests": None}))
    assert st["commit"] == COMMIT and st["tree_clean"] is True and not st["established"]
    assert st["code_identity"] == {"pipeline": TREES["pipeline"], "tests": None, "PREANALYSIS.md": None}
    assert "HEAD:./tests" in st["why"]


def _base_and_changed(kind):
    if kind in ("pipeline", "tests", "PREANALYSIS.md"):          # the code's identity: one path's git object id differs
        return prov(), prov(git=fake_git(trees={kind: "9" * 40}))
    if kind == "identity not read":
        return prov(), prov(git=fake_git(trees={"pipeline": None}))
    if kind == "outcome hash":
        return prov(outcome_record={"frame_fingerprint": "a" * 64}), prov(outcome_record={"frame_fingerprint": "b" * 64})
    if kind == "inputs":
        return prov(), prov(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE)
    if kind == "library versions":
        a = prov()
        b = copy.deepcopy(a)
        b["libraries"]["numpy"] = "0.0.1"
        return a, b
    if kind == "pinned package version":
        return prov(), prov(package_state={**PKG_OK, "version": "4.0.1"})
    if kind == "python version":
        a = prov()
        b = copy.deepcopy(a)
        b["interpreter"]["python_version"] = "3.12.0"
        return a, b
    if kind == "assembled record":
        return prov(assembled_record={"x": 1}), prov(assembled_record={"x": 2})
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["pipeline", "tests", "PREANALYSIS.md", "identity not read", "outcome hash", "inputs",
                                  "library versions", "pinned package version", "python version", "assembled record"])
def test_a_resumed_run_whose_provenance_differs_is_refused(tmp_path, kind):
    out = tmp_path / "out"
    a, b = _base_and_changed(kind)
    coord(out, p=a).run(through="row_U")
    before = (out / eo.MANIFEST).read_text()
    rec = Recorder()
    with pytest.raises(eo.ProvenanceDisagrees, match="does not agree"):
        coord(out, rec, p=b)
    assert rec.calls == [] and (out / eo.MANIFEST).read_text() == before


def test_a_resumed_run_agrees_when_only_clock_readings_differ(tmp_path):
    out = tmp_path / "out"
    a = prov(outcome_record={"frame_fingerprint": "a" * 64}, assembled_record={"x": 1, "seconds": 1.5,
                                                                            "_seconds_by_source": {"s": 1.5}})
    coord(out, p=a).run(through="row_U")
    b = prov(outcome_record={"frame_fingerprint": "a" * 64}, assembled_record={"x": 1, "seconds": 9.0,
                                                                            "_seconds_by_source": {"s": 9.0}})
    rec = Recorder()
    coord(out, rec, p=b).run(through="row_C")
    assert rec.calls == [C]
    # an outcome hash on one side only is not a disagreement (the brief: compared when both have one)
    coord(out, Recorder(), p=prov(assembled_record={"x": 1})).run(through="inventory_against_sales")
    assert entry_ids(out) == [U, C, IAS]


# ---- failure isolation -----------------------------------------------------------------------------------------------------------

def test_a_run_that_raises_and_a_run_that_fails_in_words_are_written_and_the_others_still_run(tmp_path):
    out = tmp_path / "out"
    rec = Recorder(raise_for={C}, fail_for={IAS})
    coord(out, rec).run()
    assert rec.calls == IDS and entry_ids(out) == IDS
    lines = {r["entry_id"]: r for r in manifest(out)["records"]}
    c_rec = strict_load((out / lines[C]["file"]).read_text())
    assert lines[C]["estimated"] is False and c_rec["body"]["raised"] is True
    assert "RuntimeError: invented failure raised for reconciliation_row_C" in c_rec["body"]["failure_in_words"]
    i_rec = strict_load((out / lines[IAS]["file"]).read_text())
    assert lines[IAS]["estimated"] is False
    assert i_rec["body"]["results"]["invented set"]["failure_in_words"] == "invented: the slope could not be computed"
    assert all(lines[i]["estimated"] for i in IDS if i not in (C, IAS))
    report = (out / eo.REPORT).read_text()
    assert "invented failure raised for reconciliation_row_C" in report
    assert "invented: the slope could not be computed" in report


def test_the_report_names_the_entry_its_section_sets_labels_and_estimates_and_no_number(tmp_path):
    out = tmp_path / "out"
    coord(out).run(through="row_U")
    report = (out / eo.REPORT).read_text()
    e = ro.REGISTRY_BY_ID[U]
    assert f"entry: {U}" in report and f"plan section: {e.section}" in report
    assert all(lab in report for lab in e.labels)
    assert "invented set: estimated" in report and "0001_reconciliation_row_U.json" in report
    assert "0.25" not in report                              # the number stays in the JSON record


# ---- the writer ---------------------------------------------------------------------------------------------------------------

@dataclasses.dataclass
class Invented:
    a: int
    b: object


class Unknown:
    pass


def test_the_writer_converts_by_rule_and_lists_what_the_rule_does_not_cover(tmp_path):
    w = eo.ResultsWriter(tmp_path / "out")
    body = {"np_int": np.int64(3), "np_float": np.float32(0.5), "np_bool": np.bool_(True),
            "arr": np.array([[1.0, np.nan], [np.inf, 2.0]]),
            "frame": pd.DataFrame({"a": [1, 2], "b": [0.5, np.nan]}),
            "series": pd.Series([1.0, -np.inf], index=["x", "y"], name="s"),
            "set": {3, 1, 2}, "tuple_keys": {(1, "AA"): 1.0, (2, "AB"): 2.0}, "int_keys": {2015: 1.1},
            "colliding_keys": {1: "a", "1": "b"},
            "nan": float("nan"), "inf": float("inf"), "ninf": float("-inf"), "na": pd.NA,
            "dc": Invented(1, np.int64(2)), "exc": ValueError("invented"), "unknown": Unknown(), "nested": [Unknown()]}
    line = w.write(kind=eo.KIND_ENTRY, stage="row_U", entry_id=U, estimated=True, body=body, provenance=prov(),
                   report_section="invented")
    rec = strict_load((tmp_path / "out" / line["file"]).read_text())
    b = rec["body"]
    assert b["np_int"] == 3 and b["np_float"] == 0.5 and b["np_bool"] is True
    assert b["arr"] == [[1.0, {"$float": "NaN"}], [{"$float": "Infinity"}, 2.0]]
    assert b["frame"]["$frame"]["columns"] == ["a", "b"] and b["frame"]["$frame"]["rows"][1] == [2, {"$float": "NaN"}]
    assert b["series"]["$series"]["values"] == [1.0, {"$float": "-Infinity"}]
    assert b["set"] == {"$set": [1, 2, 3]}
    assert b["tuple_keys"] == {'[1, "AA"]': 1.0, '[2, "AB"]': 2.0} and b["int_keys"] == {"2015": 1.1}
    assert b["colliding_keys"] == {"$mapping": [[1, "a"], ["1", "b"]]}
    assert b["nan"] == {"$float": "NaN"} and b["inf"] == {"$float": "Infinity"} and b["ninf"] == {"$float": "-Infinity"}
    assert b["na"] == {"$missing": "NA"}
    assert b["dc"]["$dataclass"].endswith("Invented") and b["dc"]["fields"] == {"a": 1, "b": 2}
    assert b["exc"] == {"$exception": "ValueError", "message": "invented"}
    assert b["unknown"].startswith("<not serialized:") and "Unknown" in b["unknown"]
    paths = {x["path"]: x["type"] for x in rec["not_serialized"]}
    assert set(paths) == {'$.body["unknown"]', '$.body["nested"][0]'} and all("Unknown" in t for t in paths.values())
    assert line["sha256"] == hashlib.sha256((tmp_path / "out" / line["file"]).read_bytes()).hexdigest()


def test_the_writer_never_overwrites(tmp_path):
    out = tmp_path / "out"
    w = eo.ResultsWriter(out)
    w.write(kind=eo.KIND_ENTRY, stage="row_U", entry_id=U, estimated=True, body={}, provenance=prov(),
            report_section="one", sequence=1)
    with pytest.raises(eo.RecordRefused, match="sequence number 1 is already in the manifest"):
        w.write(kind=eo.KIND_ENTRY, stage="row_U", entry_id=U, estimated=True, body={}, provenance=prov(),
                report_section="again", sequence=1)
    (out / "0002_reconciliation_row_C.json").write_text("left by something else\n")
    with pytest.raises(eo.RecordRefused, match="already exists"):
        w.write(kind=eo.KIND_ENTRY, stage="row_C", entry_id=C, estimated=True, body={}, provenance=prov(),
                report_section="two")
    assert (out / "0002_reconciliation_row_C.json").read_text() == "left by something else\n"
    assert [r["sequence"] for r in manifest(out)["records"]] == [1]
    with pytest.raises(eo.RecordRefused, match="provenance"):
        w.write(kind=eo.KIND_ENTRY, stage="row_C", entry_id=C, estimated=True, body={}, provenance={},
                report_section="two")
    assert not [p for p in out.iterdir() if p.name.startswith(eo.TMP_PREFIX)]


def test_a_coordinator_refuses_when_the_next_record_file_is_already_there(tmp_path):
    out = tmp_path / "out"
    coord(out).run(through="row_U")
    (out / "0002_reconciliation_row_C.json").write_text("left by something else\n")
    with pytest.raises(eo.RecordRefused, match="already exists"):
        coord(out).run_entry(C)
    assert (out / "0002_reconciliation_row_C.json").read_text() == "left by something else\n"
    assert entry_ids(out) == [U]


def _all_paths(base: Path) -> set:
    return {p for p in base.rglob("*")}


def test_nothing_is_written_outside_the_directory_given(tmp_path, monkeypatch):
    out = (tmp_path / "given" / "out").resolve()
    (tmp_path / "keep.txt").write_text("x\n")
    p = prov()
    before = _all_paths(tmp_path)
    attempts = []

    def inside(path) -> bool:
        try:
            Path(os.fsdecode(path)).resolve().relative_to(out)
            return True
        except ValueError:
            return False

    def guard(path, what):
        attempts.append((what, str(path)))
        if not inside(path):
            raise AssertionError(f"{what} outside the directory given: {path}")

    real_open, real_os_open, real_replace, real_link = builtins.open, os.open, os.replace, os.link
    real_write_text, real_write_bytes, real_mkdir = Path.write_text, Path.write_bytes, Path.mkdir

    def b_open(file, mode="r", *a, **k):
        if isinstance(file, (str, bytes, os.PathLike)) and any(c in mode for c in "wax+"):
            guard(file, "open")
        return real_open(file, mode, *a, **k)

    def o_open(path, flags, *a, **k):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            guard(path, "os.open")
        return real_os_open(path, flags, *a, **k)

    def o_replace(src, dst, *a, **k):
        guard(src, "os.replace")
        guard(dst, "os.replace")
        return real_replace(src, dst, *a, **k)

    def o_link(src, dst, *a, **k):
        guard(dst, "os.link")
        return real_link(src, dst, *a, **k)

    def p_write_text(self, *a, **k):
        guard(self, "Path.write_text")
        return real_write_text(self, *a, **k)

    def p_write_bytes(self, *a, **k):
        guard(self, "Path.write_bytes")
        return real_write_bytes(self, *a, **k)

    def p_mkdir(self, *a, **k):
        if not (inside(self) or out.is_relative_to(Path(self).resolve())):
            raise AssertionError(f"mkdir outside the directory given: {self}")
        return real_mkdir(self, *a, **k)

    with monkeypatch.context() as m:
        m.setattr(builtins, "open", b_open)
        m.setattr(os, "open", o_open)
        m.setattr(os, "replace", o_replace)
        m.setattr(os, "link", o_link)
        m.setattr(Path, "write_text", p_write_text)
        m.setattr(Path, "write_bytes", p_write_bytes)
        m.setattr(Path, "mkdir", p_mkdir)
        coord(out, Recorder(raise_for={C}), p=p).run()
    after = _all_paths(tmp_path)
    new = {x for x in after - before if not x.resolve().is_relative_to(out)}
    assert new == {tmp_path / "given"}                       # the parent made for the directory, and nothing in it but out
    assert {x.name for x in (tmp_path / "given").iterdir()} == {"out"}
    assert attempts and all(inside(pth) for _w, pth in attempts)
    assert entry_ids(out) == IDS


# ---- the research path, with everything replaced -----------------------------------------------------------------------------

R_UNITS = [(10, "AL"), (11, "AZ"), (12, "CA")]
R_YEARS = range(2013, 2026)


def invented_outcome_file():
    rows = []
    for i, (u, st) in enumerate(R_UNITS):
        for y in R_YEARS:
            price = SENTINEL if (i, y) == (0, 2016) else 10.0 + i + 0.1 * (y - 2013)
            rows.append({"utility_id_eia": u, "state": st, "year": y, "res_revenue_full": 1000.0 + y,
                         "res_price": price, "res_price_delivery_only": np.nan, "res_price_default_service": price,
                         "res_bill_per_customer_month": 100.0 + i, "res_kwh_per_customer_month": 900.0 + i,
                         "energy_price_state": 5.0})
    return pd.DataFrame(rows)


def invented_quantities():
    return pd.DataFrame([{"utility_id_eia": u, "state": st, "year": y, "res_customers": 1000.0 + 10 * i}
                         for i, (u, st) in enumerate(R_UNITS) for y in R_YEARS])


def invented_flags():
    f = pd.DataFrame([(u, st, y, False) for u, st in R_UNITS for y in range(2015, 2026)],
                     columns=["utility_id_eia", "state", "year", "short_form"])
    return f


@dataclasses.dataclass
class FakeAssembled:
    inputs: object
    cpi_factors: dict
    record: dict
    deferred: list
    inputs_are: str


def fake_inputs(inv=ro.RESEARCH_DATA_AFTER_THE_FREEZE, u_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE):
    side = SimpleNamespace(q=invented_quantities(), usable={(u, st, y) for u, st in R_UNITS for y in R_YEARS})
    return SimpleNamespace(side=side, reconciliation_u=SimpleNamespace(sample_flags=invented_flags()),
                           inventory_inputs_are=inv, reconciliation_u_inputs_are=u_are,
                           inventory_as_built=ro.InventoryAsBuilt(dose_fingerprint="e" * 64, source="invented"))


class Calls:
    def __init__(self):
        self.log = []


def research_kit(calls, frame=None, inputs=None, door_raises=None):
    frame = invented_outcome_file() if frame is None else frame

    def assembler(*, inputs_are):
        calls.log.append(("assembler", inputs_are))
        return FakeAssembled(inputs=inputs or fake_inputs(), cpi_factors={y: 1.0 + 0.01 * (2024 - y) for y in range(2015, 2025)},
                             record={"side": {"supplied": True, "counts": {"quantity_rows": 39}, "seconds": 0.1},
                                     "_seconds_by_source": {"design_load": 0.1}},
                             deferred=[{"field": "peaks", "reason_in_words": "invented: not supplied"}],
                             inputs_are=inputs_are)

    def door():
        calls.log.append(("door",))
        if door_raises is not None:
            raise door_raises
        return ro.OutcomesRead(frame=frame, record={"purpose_passed": ro.POST_FREEZE_PURPOSE,
                                                    "frame_fingerprint": ro.frame_fingerprint(frame),
                                                    "frame_shape": list(frame.shape),
                                                    "frame_columns": [str(c) for c in frame.columns]})

    def package_check():
        calls.log.append(("package",))
        return PKG_OK

    return dict(door=door, assembler=assembler, package_check=package_check, git=fake_git())


def test_the_research_path_runs_in_order_and_writes_the_first_record_before_any_entry(tmp_path):
    out = tmp_path / "out"
    calls = Calls()
    firsts = []

    def on_call(entry_id):
        if not firsts:
            man = json.loads((out / eo.MANIFEST).read_text())
            firsts.append([r["kind"] for r in man["records"]])

    rec = Recorder(on_call=on_call)
    done = eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, run=rec,
                               **research_kit(calls))
    assert firsts == [[eo.KIND_READ_TIME_CHECKS]]
    assert rec.calls == IDS
    assert [r["kind"] for r in manifest(out)["records"]] == [eo.KIND_READ_TIME_CHECKS] + [eo.KIND_ENTRY] * len(IDS)
    assert entry_ids(out) == IDS and done["next_expected"] is None
    assert [c[0] for c in calls.log] == ["package", "assembler", "door"]
    assert calls.log.count(("door",)) == 1
    first = strict_load((out / manifest(out)["records"][0]["file"]).read_text())
    body = first["body"]
    assert first["stage"] == eo.BEFORE_ANY_ESTIMATE and first["sequence"] == 1
    assert body["door_record"]["frame_fingerprint"] == ro.frame_fingerprint(invented_outcome_file())
    assert body["assembler_record"]["side"]["counts"]["quantity_rows"] == 39
    assert body["inventory_check_inputs"]["inventory_inputs_are"] == ro.RESEARCH_DATA_AFTER_THE_FREEZE
    assert set(body["frames_built"]) == set(of.NAMES)
    assert body["read_time_checks"]["coverage"]["passed"] is True
    assert body["read_time_checks"]["row_u_short_form_flags"]["window"] == [2015, 2025]
    assert first["provenance"]["outcome_file_hash"] == ro.frame_fingerprint(invented_outcome_file())
    assert first["provenance"]["inputs_are"] == ro.RESEARCH_DATA_AFTER_THE_FREEZE


def test_no_outcome_value_reaches_the_provenance_the_manifest_or_the_first_record(tmp_path):
    out = tmp_path / "out"
    frame = invented_outcome_file()
    assert (frame.res_price == SENTINEL).sum() == 1
    eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, run=Recorder(),
                        **research_kit(Calls(), frame=frame))
    digits = ("12345.678", "12345.67", "12345678")
    man_text = (out / eo.MANIFEST).read_text()
    assert not any(d in man_text for d in digits)
    lines = manifest(out)["records"]
    first_text = (out / lines[0]["file"]).read_text()
    assert not any(d in first_text for d in digits)
    for line in lines:
        pv = json.dumps(strict_load((out / line["file"]).read_text())["provenance"])
        assert not any(d in pv for d in digits)
    # the reshaped price frame that reached the runs does carry the planted value: the check above is not vacuous
    seen = {}

    def keep(entry_id, inputs, outcomes):
        seen.setdefault("frames", outcomes)
        return {"estimated": False, "failure_in_words": "invented"}
    eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=tmp_path / "out2", run=keep,
                        through="row_U", **research_kit(Calls(), frame=frame))
    assert (seen["frames"][of.PRICE_DELIVERY_INCLUSIVE].value == SENTINEL).sum() == 1


def test_the_research_path_refuses_invented_inputs_before_anything(tmp_path):
    calls = Calls()
    with pytest.raises(eo.ResearchPathRefused, match="does not take INVENTED_INPUTS"):
        eo.execute_research(inputs_are=ro.INVENTED_INPUTS, output_dir=tmp_path / "out", run=Recorder(),
                            **research_kit(calls))
    with pytest.raises(eo.ResearchPathRefused, match="takes"):
        eo.execute_research(inputs_are="anything", output_dir=tmp_path / "out", run=Recorder(), **research_kit(calls))
    assert calls.log == [] and not (tmp_path / "out").exists()


def test_the_research_path_refuses_without_the_pinned_package_before_the_door(tmp_path):
    calls = Calls()
    kit = research_kit(calls)
    kit["package_check"] = lambda: (calls.log.append(("package",)), PKG_MISSING)[1]
    rec = Recorder()
    with pytest.raises(eo.ResearchPathRefused, match="diff-diff 4.0.0 does not import"):
        eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=tmp_path / "out", run=rec, **kit)
    assert calls.log == [("package",)] and rec.calls == [] and not (tmp_path / "out").exists()


def test_the_research_path_refuses_a_dirty_tree_before_the_door(tmp_path):
    calls = Calls()
    for git in (fake_git(porcelain=" M pipeline/analysis/x.py\n"), fake_git(porcelain="?? tests/new.py\n"),
                fake_git(fail="status")):
        kit = research_kit(calls)
        kit["git"] = git
        with pytest.raises(eo.ResearchPathRefused, match="uncommitted change"):
            eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=tmp_path / "out",
                                run=Recorder(), **kit)
    assert ("door",) not in calls.log and ("assembler", ro.RESEARCH_DATA_AFTER_THE_FREEZE) not in calls.log
    assert not (tmp_path / "out").exists()


def test_a_door_that_refuses_stops_everything_and_nothing_is_written(tmp_path):
    calls = Calls()
    rec = Recorder()
    with pytest.raises(ro.OutcomeAccessRefused, match="invented refusal"):
        eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=tmp_path / "out", run=rec,
                            **research_kit(calls, door_raises=ro.OutcomeAccessRefused("invented refusal")))
    assert calls.log.count(("door",)) == 1 and rec.calls == [] and not (tmp_path / "out").exists()


@pytest.mark.parametrize("inv,u_are", [(ro.INVENTED_INPUTS, ro.RESEARCH_DATA_AFTER_THE_FREEZE),
                                       (ro.RESEARCH_DATA_AFTER_THE_FREEZE, ro.INVENTED_INPUTS),
                                       (None, ro.RESEARCH_DATA_AFTER_THE_FREEZE)])
def test_inconsistent_statements_of_what_the_inputs_are_are_refused_before_the_door(tmp_path, inv, u_are):
    calls = Calls()
    with pytest.raises(eo.ResearchPathRefused, match="must be"):
        eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=tmp_path / "out", run=Recorder(),
                            **research_kit(calls, inputs=fake_inputs(inv, u_are)))
    assert ("door",) not in calls.log and not (tmp_path / "out").exists()


def test_the_research_path_resumes_with_one_read_per_process_and_refuses_a_changed_outcome_file(tmp_path):
    out = tmp_path / "out"
    c1 = Calls()
    eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, through="row_C", run=Recorder(),
                        **research_kit(c1))
    assert c1.log.count(("door",)) == 1 and entry_ids(out) == [U, C]
    changed = invented_outcome_file()
    changed.loc[0, "res_price"] = 11.5
    rec = Recorder()
    with pytest.raises(eo.ProvenanceDisagrees, match="outcome file's hash differs"):
        eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, run=rec,
                            **research_kit(Calls(), frame=changed))
    assert rec.calls == [] and entry_ids(out) == [U, C]
    c3 = Calls()
    rec3 = Recorder()
    eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, run=rec3, **research_kit(c3))
    assert c3.log.count(("door",)) == 1 and rec3.calls == IDS[2:]
    kinds = [r["kind"] for r in manifest(out)["records"]]
    assert kinds[:4] == [eo.KIND_READ_TIME_CHECKS, eo.KIND_ENTRY, eo.KIND_ENTRY, eo.KIND_READ_TIME_CHECKS]
    assert entry_ids(out) == IDS


def test_which_entries_take_an_outcome_is_read_from_the_registrys_fields():
    assert eo.takes_outcome(U) and eo.takes_outcome(C) and eo.takes_outcome("main_headline_set")
    assert not eo.takes_outcome(IAS)
    for i in IDS:
        e = ro.REGISTRY_BY_ID[i]
        assert eo.takes_outcome(i) == (e.outcome is not None or bool(e.outcomes))


def _first_process(out, through="row_U"):
    calls = Calls()
    eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, through=through, run=Recorder(),
                        **research_kit(calls))
    assert calls.log.count(("door",)) == 1                 # a first process with through="row_U" still reads once
    return (out / eo.MANIFEST).read_text()


@pytest.mark.parametrize("kind", ["code identity", "library versions", "damaged directory", "changed order"])
def test_what_can_be_refused_without_the_outcomes_is_refused_before_the_door(tmp_path, monkeypatch, kind):
    out = tmp_path / "out"
    before = _first_process(out)
    calls = Calls()
    kit = research_kit(calls)
    expected = eo.ProvenanceDisagrees
    if kind == "code identity":
        kit["git"] = fake_git(trees={"pipeline": "9" * 40})
    elif kind == "library versions":
        real = eo.library_versions
        monkeypatch.setattr(eo, "library_versions", lambda: {**real(), "scipy": "0.0.1"})
    elif kind == "damaged directory":
        p = out / "0002_reconciliation_row_U.json"
        os.chmod(p, 0o644)
        p.write_text(p.read_text() + " ")
        before = (out / eo.MANIFEST).read_text()
        expected = eo.DirectoryDamaged
    else:
        order = list(ro.ORDER_OF_UNBLINDING)
        monkeypatch.setattr(ro, "ORDER_OF_UNBLINDING", tuple(order[:3] + order[4:]))
        expected = eo.OrderRefused
    rec = Recorder()
    with pytest.raises(expected):
        eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, run=rec, **kit)
    assert ("door",) not in calls.log and rec.calls == []
    assert (out / eo.MANIFEST).read_text() == before


def test_a_resume_with_another_outcome_hash_reads_once_and_writes_nothing(tmp_path):
    out = tmp_path / "out"
    before = _first_process(out)
    changed = invented_outcome_file()
    changed.loc[1, "res_price"] = 10.5
    calls = Calls()
    rec = Recorder()
    with pytest.raises(eo.ProvenanceDisagrees, match="outcome file's hash differs"):
        eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, run=rec,
                            **research_kit(calls, frame=changed))
    assert calls.log.count(("door",)) == 1 and rec.calls == []
    assert (out / eo.MANIFEST).read_text() == before
    assert sorted(p.name for p in out.iterdir()) == ["0001_read_time_checks.json", "0002_reconciliation_row_U.json",
                                                     eo.MANIFEST, eo.REPORT]


def test_a_process_that_runs_only_the_inventory_check_does_not_read_the_outcomes(tmp_path):
    out = tmp_path / "out"
    _first_process(out, through="row_C")
    assert entry_ids(out) == [U, C]
    calls2 = Calls()
    got = []

    def keep(entry_id, inputs, outcomes):
        got.append((entry_id, outcomes))
        return Recorder()(entry_id, inputs, outcomes)
    done = eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out,
                               through="inventory_against_sales", run=keep, **research_kit(calls2))
    assert ("door",) not in calls2.log and done["outcomes_read"] is False and done["first_record"] is None
    assert got == [(IAS, None)]                              # run with no outcome frames
    lines = manifest(out)["records"]
    assert [r["kind"] for r in lines] == [eo.KIND_READ_TIME_CHECKS, eo.KIND_ENTRY, eo.KIND_ENTRY, eo.KIND_ENTRY]
    assert lines[-1]["entry_id"] == IAS
    pv = strict_load((out / lines[-1]["file"]).read_text())["provenance"]
    assert pv["outcome_file_hash"] is None
    assert "no outcome was read by this process" in pv["outcome_file_hash_in_words"]
    # the manifest has a hash and this process has none: accepted, since the hash is compared only when both have one
    assert manifest(out)["provenance"]["outcome_file_hash"]
    calls3 = Calls()
    rec3 = Recorder()
    eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, run=rec3, **research_kit(calls3))
    assert calls3.log.count(("door",)) == 1 and rec3.calls == IDS[3:]
    assert entry_ids(out) == IDS
    kinds = [r["kind"] for r in manifest(out)["records"]]
    assert kinds.count(eo.KIND_READ_TIME_CHECKS) == 2 and kinds[4] == eo.KIND_READ_TIME_CHECKS


def test_a_failed_check_that_does_not_block_is_recorded_and_fills_nothing(tmp_path):
    """Row U's flag coverage is recorded and does not stop the run (the row refuses step by step under its own rule).
    The blocking checks are in tests/test_integrity_stop_invented.py (session 28, D-122)."""
    out = tmp_path / "out"
    frame = invented_outcome_file()
    inputs = fake_inputs()
    flags = inputs.reconciliation_u.sample_flags
    inputs.reconciliation_u.sample_flags = flags[~((flags.utility_id_eia == 11) & (flags.year == 2020))].reset_index(drop=True)
    seen = {}

    def keep(entry_id, inputs, outcomes):
        seen.setdefault("frames", outcomes)
        return {"estimated": False, "failure_in_words": "invented"}
    eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, run=keep, through="row_U",
                        **research_kit(Calls(), frame=frame, inputs=inputs))
    first = strict_load((out / manifest(out)["records"][0]["file"]).read_text())["body"]
    assert first["read_time_checks"]["row_u_short_form_flags"]["passed"] is False
    assert first["read_time_checks_failed"] == ["row_u_short_form_flags"]
    assert first["blocked_before_any_estimator"] is False and first["blocking_decision"]["blocks"] is False
    assert [r["check"] for r in first["blocking_decision"]["recorded_and_not_blocking"]] == ["row_u_short_form_flags"]
    assert len(seen["frames"][of.PRICE]) == len(frame)          # nothing filled, and the run went on


def test_main_with_no_arguments_prints_what_it_would_do_and_does_nothing(capsys, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(eo, "execute_research", lambda **k: called.append(k))
    assert eo.main([]) == 0
    assert "With no arguments nothing is done" in capsys.readouterr().out and called == []


def test_main_refuses_invented_inputs_and_passes_explicit_arguments(capsys, tmp_path, monkeypatch):
    assert eo.main(["--inputs-are", ro.INVENTED_INPUTS, "--output-dir", str(tmp_path / "o")]) == 2
    assert "does not take INVENTED_INPUTS" in capsys.readouterr().out and not (tmp_path / "o").exists()
    called = []
    monkeypatch.setattr(eo, "execute_research", lambda **k: called.append(k) or {"written": []})
    assert eo.main(["--inputs-are", ro.RESEARCH_DATA_AFTER_THE_FREEZE, "--output-dir", str(tmp_path / "o"),
                    "--through", "row_C"]) == 0
    assert called == [{"inputs_are": ro.RESEARCH_DATA_AFTER_THE_FREEZE, "output_dir": tmp_path / "o",
                       "through": "row_C"}]


def test_the_default_output_location_is_under_data_results_and_no_test_uses_it():
    d = eo.default_output_dir()
    assert d.parent == eo.DEFAULT_OUTPUT_ROOT == ROOT / "data" / "results" / "outcome_runs"
    assert not d.exists()


# ---- integration with the real door and the real run ----------------------------------------------------------------------------

DOOR_HAS_NEW_FORM = set(inspect.signature(ro.load_outcomes_after_the_freeze).parameters) >= {"reader", "plan_state",
                                                                                             "purpose"}


@pytest.mark.skipif(not DOOR_HAS_NEW_FORM, reason="the registry's door does not yet take reader and plan_state")
def test_the_real_door_with_an_invented_reader_and_plan_state_feeds_the_first_record(tmp_path, monkeypatch):
    gate = tmp_path / "invented_gate" / "GATE1_SIGNED"
    gate.parent.mkdir()
    gate.write_text("invented gate for a test\n")
    monkeypatch.setattr(ro.panel, "GATE_FILE", gate)
    monkeypatch.setenv(ro.AUTH_ENV, "1")
    frame = invented_outcome_file()
    purposes = []

    def reader(*, purpose):
        purposes.append(purpose)
        return frame

    def plan_state():
        return {"established": True, "plan_has_no_uncommitted_change": True, "freeze_commit_is_an_ancestor_of_head": True,
                "freeze_commit": ro.FREEZE_COMMIT, "head": "invented", "plan_equals_the_freeze_commits": True}

    calls = Calls()
    kit = research_kit(calls)
    kit["door"] = lambda: ro.load_outcomes_after_the_freeze(reader=reader, plan_state=plan_state)
    out = tmp_path / "out"
    eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=out, through="row_U", run=Recorder(),
                        **kit)
    assert purposes == [ro.POST_FREEZE_PURPOSE]
    first = strict_load((out / manifest(out)["records"][0]["file"]).read_text())
    dr = first["body"]["door_record"]
    assert dr["frame_fingerprint"] == ro.frame_fingerprint(frame) == first["provenance"]["outcome_file_hash"]
    assert dr["gate_file"] == "GATE1_SIGNED" and dr["gate_file_existed"] is True
    assert dr["authorization_variable_was_1"] is True and dr["plan_state"]["head"] == "invented"
    assert dr["reader"]["qualified_name"].endswith("reader")
    assert first["provenance"]["gate"]["gate_file_exists"] is True
    assert first["provenance"]["gate"]["authorization_variable_is_1"] is True


def test_the_real_door_refuses_on_the_research_path_while_there_is_no_gate_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ro.panel, "GATE_FILE", tmp_path / "absent" / "GATE1_SIGNED")
    monkeypatch.delenv(ro.AUTH_ENV, raising=False)
    kit = research_kit(Calls())
    kit.pop("door")
    rec = Recorder()
    with pytest.raises(ro.OutcomeAccessRefused, match="gate file GATE1_SIGNED does not exist"):
        eo.execute_research(inputs_are=ro.RESEARCH_DATA_AFTER_THE_FREEZE, output_dir=tmp_path / "out", run=rec, **kit)
    assert rec.calls == [] and not (tmp_path / "out").exists()


@pytest.fixture(scope="module")
def invented_world():
    import test_run_outcomes_invented as w                       # read-only use of its helpers
    inputs, aux = w.build_world()
    return w, inputs, aux


def test_the_real_run_on_an_invented_world_writes_the_first_three_stages_and_the_headline(tmp_path, invented_world):
    w, inputs, aux = invented_world
    assert inputs.reconciliation_u_inputs_are == ro.INVENTED_INPUTS
    outcomes = w.all_outcomes(w.outcome(aux["dd"]))
    out = tmp_path / "out"
    c = eo.Coordinator(out, inputs, outcomes, provenance=prov())          # run: run_outcomes.run, looked up when called
    c.run(through="inventory_against_sales")
    c.run_entry("main_headline_set")
    lines = manifest(out)["records"]
    assert [x["entry_id"] for x in lines] == [U, C, IAS, "main_headline_set"]
    recs = {x["entry_id"]: strict_load((out / x["file"]).read_text()) for x in lines}
    for eid, rec in recs.items():
        assert rec["estimated"] is True, (eid, rec["body"].get("failures_in_words"))
        assert rec["body"]["id"] == eid
    head = recs["main_headline_set"]["body"]["results"][ro.set_label(ro.H2)]
    assert head["estimated"] is True
    # the planted headline, 0.05 log points, within the invented world's tolerance (as its own test asserts)
    assert abs(head["headline"]["log_points"] - 0.05) < w.TOL
    ias_res = recs[IAS]["body"]["results"][ro.set_label(ro.H2)]
    assert abs(ias_res["slope"]["slope"] - w.IAS_SLOPE) < 1e-6
    report = (out / eo.REPORT).read_text()
    assert all(f"entry: {e}" in report for e in (U, C, IAS, "main_headline_set"))
