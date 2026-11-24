"""Code identity on a resume (session 28; Joe, 2026-11-20, D-122: "Compare code identity"). Invented inputs only.

A resumed run is refused unless the git tree ids of pipeline and tests and the blob id of PREANALYSIS.md at its commit
equal the manifest's. The commit is recorded with every result and is not compared, so a commit that changes documents
only is accepted and a commit that changes a file under pipeline, under tests or the plan is refused in words.

Every repository here is built under pytest's tmp_path with invented files, an invented author and no global or system
git configuration; git looks no higher than tmp_path. Every directory written is under tmp_path. No file under data/ is
read, the door to outcomes is an invented one, and the real gate file is never created. The one real path reached is
an existence check of the gate file's path in the gizmo folder, made by the code under test
(execute_outcomes.gate_state) each time a provenance is built; nothing is opened. The helpers of
tests/test_execute_outcomes_invented.py are imported and not changed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_execute_outcomes_invented as k  # noqa: E402  read-only use of its invented frames and its kit

from pipeline.analysis import execute_outcomes as eo  # noqa: E402
from pipeline.analysis import run_outcomes as ro  # noqa: E402

RESEARCH = ro.RESEARCH_DATA_AFTER_THE_FREEZE
PATHS = ("pipeline", "tests", "PREANALYSIS.md")
G = ["git", "-c", "user.name=invented", "-c", "user.email=invented@example.invalid", "-c", "commit.gpgsign=false"]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An invented repository whose gizmo folder sits inside it, as the real one does, with a document beside the code
    and an unrelated folder elsewhere in the repository."""
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(name, raising=False)                      # git finds its repository from the folder alone
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    top = tmp_path / "warehouse"
    r = top / "gizmos" / "invented-gizmo"
    (r / "pipeline" / "analysis").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "docs").mkdir()
    (top / "elsewhere").mkdir()
    (r / "pipeline" / "analysis" / "m.py").write_text("x = 1\n")
    (r / "tests" / "t.py").write_text("y = 1\n")
    (r / "PREANALYSIS.md").write_text("the invented plan\n")
    (r / "docs" / "record.md").write_text("a record\n")
    (top / "elsewhere" / "other.txt").write_text("someone else's work\n")
    subprocess.run(["git", "init", "-q"], cwd=top, check=True)
    commit(top, "invented: the execution commit")
    return top, r


def commit(top, message):
    subprocess.run([*G, "add", "-A"], cwd=top, check=True)
    subprocess.run([*G, "commit", "-q", "-m", message], cwd=top, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=top, capture_output=True, text=True, check=True).stdout.strip()


def prov(r, **kw):
    return eo.provenance(inputs_are=ro.INVENTED_INPUTS, root=r, package_state=k.PKG_OK, **kw)


def test_the_commit_and_the_three_ids_are_in_every_record(repo, tmp_path):
    top, r = repo
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=top, capture_output=True, text=True, check=True).stdout.strip()
    st = eo.code_state(root=r)
    assert st["established"] is True and st["tree_clean"] is True and st["commit"] == head
    assert set(st["code_identity"]) == set(PATHS) == set(eo.CODE_PATHS)
    for path in PATHS:                                               # the ids are git's own, asked another way
        want = subprocess.run(["git", "rev-parse", f"HEAD:gizmos/invented-gizmo/{path}"], cwd=top, capture_output=True,
                              text=True, check=True).stdout.strip()
        assert st["code_identity"][path] == want and len(want) == 40
    kinds = {p: subprocess.run(["git", "cat-file", "-t", st["code_identity"][p]], cwd=top, capture_output=True,
                               text=True, check=True).stdout.strip() for p in PATHS}
    assert kinds == {"pipeline": "tree", "tests": "tree", "PREANALYSIS.md": "blob"}
    out = tmp_path / "out"
    k.coord(out, p=prov(r)).run(through="inventory_against_sales")
    man = k.manifest(out)
    assert man["provenance"]["code"]["commit"] == head and man["provenance"]["code"]["code_identity"] == st["code_identity"]
    assert len(man["records"]) == 3
    for line in man["records"]:
        pv = k.strict_load((out / line["file"]).read_text())["provenance"]
        assert pv["code"]["commit"] == head and pv["code"]["code_identity"] == st["code_identity"]
        assert "Compare code identity" in pv["code"]["code_identity_means"]


def test_a_documents_only_commit_and_a_commit_elsewhere_are_accepted_on_resume(repo, tmp_path):
    top, r = repo
    out = tmp_path / "out"
    first = prov(r)
    k.coord(out, p=first).run(through="row_U")
    (r / "docs" / "record.md").write_text("a record, with the run's record added after the run\n")
    (r / "HANDOVER.md").write_text("a new document beside the code\n")
    h2 = commit(top, "invented: documents only")
    (top / "elsewhere" / "other.txt").write_text("someone else's later work\n")
    h3 = commit(top, "invented: an unrelated commit elsewhere in the repository")
    later = prov(r)
    assert first["code"]["commit"] != h2 != h3 and later["code"]["commit"] == h3
    assert later["code"]["code_identity"] == first["code"]["code_identity"] and later["code"]["tree_clean"] is True
    assert eo.agreement(first, later) == []
    rec = k.Recorder()
    k.coord(out, rec, p=later).run(through="row_C")
    assert rec.calls == [k.C] and k.entry_ids(out) == [k.U, k.C]
    # the commit of the code that ran is still recorded with every result: each record names its own run's commit
    lines = k.manifest(out)["records"]
    commits = [k.strict_load((out / x["file"]).read_text())["provenance"]["code"]["commit"] for x in lines]
    assert commits == [first["code"]["commit"], h3]
    assert k.manifest(out)["provenance"]["code"]["commit"] == first["code"]["commit"]      # the manifest is not edited


@pytest.mark.parametrize("changed", ["pipeline", "tests", "PREANALYSIS.md"])
def test_a_commit_that_changes_the_code_the_tests_or_the_plan_is_refused_in_words(repo, tmp_path, changed):
    top, r = repo
    out = tmp_path / "out"
    first = prov(r)
    k.coord(out, p=first).run(through="row_U")
    before = (out / eo.MANIFEST).read_text()
    target = {"pipeline": r / "pipeline" / "analysis" / "m.py", "tests": r / "tests" / "t.py",
              "PREANALYSIS.md": r / "PREANALYSIS.md"}[changed]
    target.write_text(target.read_text() + "# one changed line\n")
    commit(top, f"invented: a change under {changed}")
    later = prov(r)
    assert later["code"]["tree_clean"] is True                        # committed: the clean-tree rule alone would pass it
    differing = [p for p in PATHS if later["code"]["code_identity"][p] != first["code"]["code_identity"][p]]
    assert differing == [changed]
    rec = k.Recorder()
    with pytest.raises(eo.ProvenanceDisagrees, match=f"the code identity of {changed} differs"):
        k.coord(out, rec, p=later)
    assert rec.calls == [] and (out / eo.MANIFEST).read_text() == before and k.entry_ids(out) == [k.U]


def test_a_new_file_under_the_code_changes_the_identity_and_an_uncommitted_one_is_not_clean(repo):
    top, r = repo
    first = eo.code_state(root=r)
    (r / "tests" / "test_new.py").write_text("z = 1\n")
    dirty = eo.code_state(root=r)
    assert dirty["tree_clean"] is False and dirty["code_identity"] == first["code_identity"]   # HEAD has not moved
    commit(top, "invented: a new test file")
    after = eo.code_state(root=r)
    assert after["tree_clean"] is True and after["code_identity"]["tests"] != first["code_identity"]["tests"]
    assert after["code_identity"]["pipeline"] == first["code_identity"]["pipeline"]


def test_an_identity_that_either_side_lacks_is_a_difference_and_never_an_agreement():
    a = k.prov()
    assert eo.agreement(a, k.prov()) == []
    assert eo.agreement(a, k.prov(git=k.fake_git(commit="d" * 40))) == []       # another commit, the same three ids
    for path in PATHS:
        for other in (k.prov(git=k.fake_git(trees={path: None})), ):
            diffs = eo.agreement(a, other)
            assert any(f"the code identity of {path} cannot be compared" in d for d in diffs)
            assert any("cannot be compared" in d for d in eo.agreement(other, a))
    old_style = {x: y for x, y in a.items()}
    old_style["code"] = {"commit": k.COMMIT, "tree_clean": True}               # a manifest with a commit and no ids
    assert len([d for d in eo.agreement(old_style, a) if "cannot be compared" in d]) == 3
    assert len([d for d in eo.agreement(old_style, old_style) if "cannot be compared" in d]) == 3


def test_the_research_path_resumes_after_a_documents_only_commit_and_refuses_a_code_commit_before_the_door(repo, tmp_path):
    top, r = repo
    out = tmp_path / "out"

    def go(calls, rec, through):
        kit = k.research_kit(calls)
        kit.pop("git")                                               # the real git, in the invented repository
        return eo.execute_research(inputs_are=RESEARCH, output_dir=out, run=rec, through=through, root=r, **kit)

    c1 = k.Calls()
    go(c1, k.Recorder(), "row_C")
    assert k.entry_ids(out) == [k.U, k.C] and c1.log.count(("door",)) == 1
    (r / "docs" / "record.md").write_text("the run's record, committed after the run\n")
    commit(top, "invented: the record of the run")
    c2, rec2 = k.Calls(), k.Recorder()
    go(c2, rec2, "inventory_against_sales")
    assert rec2.calls == [k.IAS] and ("door",) not in c2.log
    (r / "pipeline" / "analysis" / "m.py").write_text("x = 2\n")
    commit(top, "invented: a change to the code after the first read")
    c3, rec3 = k.Calls(), k.Recorder()
    before = (out / eo.MANIFEST).read_text()
    with pytest.raises(eo.ProvenanceDisagrees, match="the code identity of pipeline differs"):
        go(c3, rec3, None)
    assert ("door",) not in c3.log and rec3.calls == [] and (out / eo.MANIFEST).read_text() == before


def test_the_research_path_refuses_before_anything_is_read_when_the_identity_cannot_be_read(tmp_path):
    calls = k.Calls()
    kit = k.research_kit(calls)
    kit["git"] = k.fake_git(trees={"PREANALYSIS.md": None})
    with pytest.raises(eo.ResearchPathRefused, match="code's identity"):
        eo.execute_research(inputs_are=RESEARCH, output_dir=tmp_path / "out", run=k.Recorder(), **kit)
    assert ("door",) not in calls.log and ("assembler", RESEARCH) not in calls.log and not (tmp_path / "out").exists()
