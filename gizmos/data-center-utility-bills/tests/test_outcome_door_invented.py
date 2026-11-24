"""The door to outcomes, run_outcomes.load_outcomes_after_the_freeze, and its plan check, frozen_plan_state (session 27;
Joe, 2026-11-20, D-120: "Build the outcome-reader entry point, retaining the freeze and explicit run-authorization checks
and refusing the exempt construction and simulation routes. Test it with invented readers and files only; do not call
the real outcome reader.").

Invented readers and files only. The gate file is a path under pytest's tmp_path and the authorization variable is set
through monkeypatch. The real reader is never invoked: where the default reader is tested, panel.load_outcomes is
replaced by an invented recorder first. frozen_plan_state is run on invented git repositories built under tmp_path.
Nothing here reads data/.
"""
from __future__ import annotations

import ast
import functools
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import run_outcomes as ro  # noqa: E402

GOOD_PLAN = {"established": True, "plan_has_no_uncommitted_change": True, "freeze_commit_is_an_ancestor_of_head": True,
             "freeze_commit": ro.FREEZE_COMMIT, "head": "invented-head", "plan_blob": "invented-blob",
             "plan_equals_the_freeze_commits": True, "plan_file": ro.PLAN_FILE, "why": None}


def good_plan():
    return dict(GOOD_PLAN)


def invented_outcomes() -> pd.DataFrame:
    """An invented outcome frame. Its values are chosen so that none of them, as a string, can appear by accident in the
    record (the record must carry no value)."""
    return pd.DataFrame({"utility_id_eia": [910001, 910002, 910003], "state": ["QQ", "QQ", "QR"],
                         "year": [2011, 2012, 2013], "value": [0.123456789, 98.7654321, 4242.4242]})


class Recorder:
    """An invented reader that records every call and returns an invented frame."""

    def __init__(self, frame=None):
        self.calls = []
        self.frame = invented_outcomes() if frame is None else frame

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.frame


@pytest.fixture
def opened(tmp_path, monkeypatch):
    """The gate file exists under tmp_path and the variable is "1": every refusal before the plan check is passed."""
    gate = tmp_path / "GATE1_SIGNED"
    gate.write_text("invented")
    monkeypatch.setattr(ro.panel, "GATE_FILE", gate)
    monkeypatch.setenv(ro.AUTH_ENV, "1")
    return gate


@pytest.fixture(autouse=True)
def no_real_reader(monkeypatch):
    """Every test: the panel's real reader and the simulation's reader are replaced by functions that fail the test if
    called, unless a test replaces them again with its own recorder."""
    def forbidden(*a, **k):
        raise AssertionError("a real outcome reader was called")
    monkeypatch.setattr(ro.panel, "load_outcomes", forbidden)
    monkeypatch.setattr(ro.ps, "read_listed_outcomes", forbidden)


# ---- the constants ----------------------------------------------------------------------------------------------------

def test_the_constants_are_the_freeze_and_the_panels_exempt_purposes():
    assert ro.POST_FREEZE_PURPOSE == "outcome_analysis_after_the_freeze"
    assert ro.EXEMPT_PURPOSES == ("construction_qa", "power_simulation")
    assert ro.FREEZE_COMMIT == "ea426c4b3c971fcf826bdda1fd7a3f3e6bb9fb23"
    assert ro.APPROVED_SPECIFICATION_COMMIT == "ed3a2ff20ececaf005b0a3256a63c5d1d930095a"
    assert ro.PLAN_FILE == "PREANALYSIS.md"
    # the two exempt purposes are the ones panel.load_outcomes names in its source (read as text, not called)
    src = (ROOT / "pipeline/electricity/panel.py").read_text()
    for p in ro.EXEMPT_PURPOSES:
        assert f'purpose == "{p}"' in src or f'purpose != "{p}"' in src, p
    sig = inspect.signature(ro.load_outcomes_after_the_freeze).parameters
    assert list(sig) == ["reader", "purpose", "plan_state"]
    assert all(v.kind is inspect.Parameter.KEYWORD_ONLY for v in sig.values())
    assert sig["reader"].default is None and sig["plan_state"].default is None
    assert sig["purpose"].default == ro.POST_FREEZE_PURPOSE


# ---- refusal 1: the purpose -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("exempt", ["construction_qa", "power_simulation"])
def test_an_exempt_purpose_is_refused_by_name_whatever_the_gate(exempt, tmp_path, monkeypatch):
    rec = Recorder()
    # with the gate shut
    monkeypatch.setattr(ro.panel, "GATE_FILE", tmp_path / "GATE1_SIGNED")
    monkeypatch.delenv(ro.AUTH_ENV, raising=False)
    with pytest.raises(ro.OutcomeAccessRefused) as e:
        ro.load_outcomes_after_the_freeze(reader=rec, purpose=exempt, plan_state=good_plan)
    msg = str(e.value)
    assert repr(exempt) in msg and "construction and simulation routes are never taken through this door" in msg
    # and with it open: still refused, with the same words, before anything else
    (tmp_path / "GATE1_SIGNED").write_text("invented")
    monkeypatch.setenv(ro.AUTH_ENV, "1")
    with pytest.raises(ro.OutcomeAccessRefused, match="never taken through this door"):
        ro.load_outcomes_after_the_freeze(reader=rec, purpose=exempt, plan_state=good_plan)
    assert rec.calls == []


@pytest.mark.parametrize("other", ["", "outcome_analysis", None, "OUTCOME_ANALYSIS_AFTER_THE_FREEZE"])
def test_any_other_purpose_is_refused(other, opened):
    rec = Recorder()
    with pytest.raises(ro.OutcomeAccessRefused, match="is not 'outcome_analysis_after_the_freeze', the only purpose"):
        ro.load_outcomes_after_the_freeze(reader=rec, purpose=other, plan_state=good_plan)
    assert rec.calls == []


def test_the_purpose_is_refused_before_the_plan_check_is_called(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(ro.panel, "GATE_FILE", tmp_path / "absent")
    with pytest.raises(ro.OutcomeAccessRefused, match="exempt purposes"):
        ro.load_outcomes_after_the_freeze(reader=Recorder(), purpose="construction_qa",
                                          plan_state=lambda: seen.append(1) or good_plan())
    assert seen == []


# ---- refusals 2 and 3: the gate file, then the variable ---------------------------------------------------------------

def test_no_gate_file_is_refused_first_whatever_the_variable(tmp_path, monkeypatch):
    rec, seen = Recorder(), []
    monkeypatch.setattr(ro.panel, "GATE_FILE", tmp_path / "GATE1_SIGNED")
    for v in (None, "0", "1"):
        if v is None:
            monkeypatch.delenv(ro.AUTH_ENV, raising=False)
        else:
            monkeypatch.setenv(ro.AUTH_ENV, v)
        with pytest.raises(ro.OutcomeAccessRefused) as e:
            ro.load_outcomes_after_the_freeze(reader=rec, plan_state=lambda: seen.append(1) or good_plan())
        msg = str(e.value)
        assert "the gate file GATE1_SIGNED does not exist" in msg
        assert "the plan is frozen at commit ea426c4" in msg and "Joe's separate authorization to access outcomes" in msg
        assert "the plan is not frozen" not in msg
    assert rec.calls == [] and seen == []


@pytest.mark.parametrize("value", [None, "", "0", "true", "yes", " 1", "1 ", "01", "2"])
def test_the_variable_must_be_exactly_1(value, tmp_path, monkeypatch):
    gate = tmp_path / "GATE1_SIGNED"
    gate.write_text("invented")
    monkeypatch.setattr(ro.panel, "GATE_FILE", gate)
    if value is None:
        monkeypatch.delenv(ro.AUTH_ENV, raising=False)
    else:
        monkeypatch.setenv(ro.AUTH_ENV, value)
    rec, seen = Recorder(), []
    with pytest.raises(ro.OutcomeAccessRefused, match=f"the environment variable {ro.AUTH_ENV} is not set to 1"):
        ro.load_outcomes_after_the_freeze(reader=rec, plan_state=lambda: seen.append(1) or good_plan())
    assert rec.calls == [] and seen == []


def test_the_gate_file_is_looked_up_when_called(tmp_path, monkeypatch, opened):
    """The gate path is read from panel.GATE_FILE at call time, so moving it after import changes the answer."""
    rec = Recorder()
    assert ro.load_outcomes_after_the_freeze(reader=rec, plan_state=good_plan).frame is rec.frame
    monkeypatch.setattr(ro.panel, "GATE_FILE", tmp_path / "elsewhere" / "GATE1_SIGNED")
    with pytest.raises(ro.OutcomeAccessRefused, match="does not exist"):
        ro.load_outcomes_after_the_freeze(reader=rec, plan_state=good_plan)
    assert len(rec.calls) == 1


# ---- refusal 4: the plan ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("change,words", [
    ({"established": False, "why": "invented: git could not be run"}, "could not be established (invented: git could"),
    ({"established": None}, "could not be established"),
    ({"plan_has_no_uncommitted_change": False}, "PREANALYSIS.md has an uncommitted change, staged or not"),
    ({"plan_has_no_uncommitted_change": None}, "has an uncommitted change"),
    ({"freeze_commit_is_an_ancestor_of_head": False}, "the freeze commit ea426c4b3c971fcf826bdda1fd7a3f3e6bb9fb23 is not "
                                                      "an ancestor of HEAD invented-head"),
])
def test_a_plan_that_is_not_the_committed_frozen_one_is_refused(change, words, opened):
    rec = Recorder()
    with pytest.raises(ro.OutcomeAccessRefused) as e:
        ro.load_outcomes_after_the_freeze(reader=rec, plan_state=lambda: {**GOOD_PLAN, **change})
    assert words in str(e.value)
    assert rec.calls == []


def test_a_plan_check_that_returns_no_record_is_refused(opened):
    with pytest.raises(ro.OutcomeAccessRefused, match="the plan check returned a str"):
        ro.load_outcomes_after_the_freeze(reader=Recorder(), plan_state=lambda: "invented")


def test_a_committed_amendment_is_recorded_and_not_refused(opened):
    rec = Recorder()
    got = ro.load_outcomes_after_the_freeze(reader=rec,
                                            plan_state=lambda: {**GOOD_PLAN, "plan_equals_the_freeze_commits": False})
    assert got.record["plan_state"]["plan_equals_the_freeze_commits"] is False and len(rec.calls) == 1


def test_the_default_plan_check_is_frozen_plan_state_looked_up_when_called(opened, monkeypatch):
    seen = []
    monkeypatch.setattr(ro, "frozen_plan_state", lambda: seen.append(1) or good_plan())
    rec = Recorder()
    ro.load_outcomes_after_the_freeze(reader=rec)
    assert seen == [1] and len(rec.calls) == 1
    assert inspect.signature(ro.load_outcomes_after_the_freeze).parameters["plan_state"].default is None


# ---- refusal 5: the simulation's reader ---------------------------------------------------------------------------------

def test_the_simulations_reader_is_refused_by_identity_and_never_called(opened, monkeypatch):
    calls = []

    def simulation_reader(*a, **k):
        calls.append(1)
        return invented_outcomes()
    monkeypatch.setattr(ro.ps, "read_listed_outcomes", simulation_reader)
    for r in (simulation_reader, functools.partial(simulation_reader)):
        with pytest.raises(ro.OutcomeAccessRefused, match="power_simulation.read_listed_outcomes .* never taken through "
                                                          "this door"):
            ro.load_outcomes_after_the_freeze(reader=r, plan_state=good_plan)
    # also when the panel's default reader has been pointed at it
    monkeypatch.setattr(ro.panel, "load_outcomes", simulation_reader)
    with pytest.raises(ro.OutcomeAccessRefused, match="read_listed_outcomes"):
        ro.load_outcomes_after_the_freeze(plan_state=good_plan)
    assert calls == []


def test_a_reader_that_cannot_be_called_is_refused(opened):
    with pytest.raises(ro.OutcomeAccessRefused, match="the reader is a str, which cannot be called"):
        ro.load_outcomes_after_the_freeze(reader="invented", plan_state=good_plan)


def test_the_order_of_the_refusals(tmp_path, monkeypatch):
    """Everything wrong at once, then each fault mended in turn: the refusal moves purpose, gate file, variable, plan,
    reader, in that order."""
    def sim(*a, **k):
        raise AssertionError("called")
    monkeypatch.setattr(ro.ps, "read_listed_outcomes", sim)
    gate = tmp_path / "GATE1_SIGNED"
    monkeypatch.setattr(ro.panel, "GATE_FILE", gate)
    monkeypatch.setenv(ro.AUTH_ENV, "0")
    bad_plan = lambda: {**GOOD_PLAN, "plan_has_no_uncommitted_change": False}       # noqa: E731
    kw = dict(reader=sim, purpose="power_simulation", plan_state=bad_plan)
    order = []
    for mend in (lambda: kw.update(purpose=ro.POST_FREEZE_PURPOSE), lambda: gate.write_text("invented"),
                 lambda: monkeypatch.setenv(ro.AUTH_ENV, "1"), lambda: kw.update(plan_state=good_plan), None):
        with pytest.raises(ro.OutcomeAccessRefused) as e:
            ro.load_outcomes_after_the_freeze(**kw)
        order.append(str(e.value))
        if mend:
            mend()
    keys = ["exempt purposes", "gate file GATE1_SIGNED does not exist", "is not set to 1", "uncommitted change",
            "read_listed_outcomes"]
    assert [k in m for k, m in zip(keys, order)] == [True] * 5, order


# ---- the call -----------------------------------------------------------------------------------------------------------

def test_the_reader_is_called_exactly_once_with_exactly_the_post_freeze_purpose(opened):
    rec = Recorder()
    got = ro.load_outcomes_after_the_freeze(reader=rec, plan_state=good_plan)
    assert rec.calls == [((), {"purpose": ro.POST_FREEZE_PURPOSE})]
    assert isinstance(got, ro.OutcomesRead) and got.frame is rec.frame          # untouched: the very object returned


def test_the_default_reader_is_the_panels_looked_up_when_called(opened, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(ro.panel, "load_outcomes", rec)
    got = ro.load_outcomes_after_the_freeze(reader=None, plan_state=good_plan)
    assert rec.calls == [((), {"purpose": ro.POST_FREEZE_PURPOSE})] and got.frame is rec.frame
    assert "units" not in rec.calls[0][1]


def test_no_reader_is_bound_at_definition_or_import_time():
    src = (ROOT / "pipeline/analysis/run_outcomes.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "load_outcomes_after_the_freeze")
    for d in fn.args.kw_defaults + fn.args.defaults:
        assert not (isinstance(d, ast.Attribute) and d.attr in ("load_outcomes", "read_listed_outcomes")), ast.dump(d)
    # no module-level name holds either reader
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for x in ast.walk(n.value):
                assert not (isinstance(x, ast.Attribute) and x.attr in ("load_outcomes", "read_listed_outcomes"))


def test_neither_exempt_purpose_can_be_passed_by_any_route_in_the_source():
    """The door's own source: no exempt purpose literal anywhere in it, no call whose arguments carry one, the reader
    called once with exactly purpose=POST_FREEZE_PURPOSE, and no call to read_listed_outcomes or load_outcomes by name."""
    fn = ast.parse(inspect.getsource(ro.load_outcomes_after_the_freeze)).body[0]
    consts = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not set(ro.EXEMPT_PURPOSES) & set(consts)
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    names = [n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None) for n in calls]
    assert "read_listed_outcomes" not in names and "load_outcomes" not in names
    reader_calls = [n for n in calls if getattr(n.func, "id", None) == "reader"]
    assert len(reader_calls) == 1
    (rc,) = reader_calls
    assert rc.args == [] and [k.arg for k in rc.keywords] == ["purpose"]
    assert isinstance(rc.keywords[0].value, ast.Name) and rc.keywords[0].value.id == "POST_FREEZE_PURPOSE"


def test_a_reader_that_returns_no_frame_is_refused(opened):
    for bad in (None, {"value": [1.0]}, np.array([1.0]), "x"):
        rec = Recorder(frame=bad)
        rec.frame = bad
        with pytest.raises(ro.OutcomeAccessRefused, match="not a DataFrame"):
            ro.load_outcomes_after_the_freeze(reader=rec, plan_state=good_plan)
        assert len(rec.calls) == 1


# ---- the record -------------------------------------------------------------------------------------------------------

def test_the_record_says_how_the_frame_was_read_and_carries_no_value(opened):
    rec = Recorder()
    got = ro.load_outcomes_after_the_freeze(reader=rec, plan_state=good_plan)
    r = got.record
    assert r["purpose_passed"] == ro.POST_FREEZE_PURPOSE
    assert r["gate_file"] == "GATE1_SIGNED" and r["gate_file_existed"] is True
    assert r["authorization_variable"] == ro.AUTH_ENV and r["authorization_variable_was_1"] is True
    assert r["plan_state"] == GOOD_PLAN and r["freeze_commit_required"] == ro.FREEZE_COMMIT
    assert r["approved_specification_commit"] == ro.APPROVED_SPECIFICATION_COMMIT
    assert r["reader"] == {"module": Recorder.__module__, "qualified_name": "Recorder"}
    assert r["frame_shape"] == [3, 4] and r["frame_columns"] == ["utility_id_eia", "state", "year", "value"]
    assert r["frame_dtypes"] == [["utility_id_eia", "int64"], ["state", "object"], ["year", "int64"],
                                 ["value", "float64"]]
    assert r["frame_fingerprint"] == ro.frame_fingerprint(invented_outcomes())
    assert r["read_at_utc"].endswith("+00:00")
    text = json.dumps(r)                                    # the record is plain JSON
    for v in rec.frame["value"]:
        assert repr(float(v)) not in text and f"{v}" not in text, v
    for v in rec.frame["utility_id_eia"]:
        assert str(int(v)) not in text                       # not even a key: the record holds no row
    assert str(ROOT) not in text                              # and no absolute path


def test_the_fingerprint_in_the_record_moves_with_the_frame(opened):
    a = ro.load_outcomes_after_the_freeze(reader=Recorder(), plan_state=good_plan).record["frame_fingerprint"]
    f = invented_outcomes()
    f.loc[1, "value"] = f.loc[1, "value"] + 1e-9
    b = ro.load_outcomes_after_the_freeze(reader=Recorder(f), plan_state=good_plan).record["frame_fingerprint"]
    shuffled = invented_outcomes().iloc[[2, 0, 1]][["value", "year", "state", "utility_id_eia"]]
    c = ro.load_outcomes_after_the_freeze(reader=Recorder(shuffled), plan_state=good_plan).record["frame_fingerprint"]
    assert a != b and a == c


# ---- frozen_plan_state on invented git repositories -------------------------------------------------------------------

GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


def git(cwd, *args) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}    # no global hook or template
    out = subprocess.run(["git", *GIT_ID, *args], cwd=str(cwd), capture_output=True, text=True, check=True, env=env)
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An invented repository: the plan sits in a subfolder (as the gizmo folder sits in the warehouse repository), with
    a first commit, a freeze commit that changes the plan, and a later commit that touches another file."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    top = tmp_path / "invented_repo"
    sub = top / "gizmo"
    sub.mkdir(parents=True)
    git(top, "init", "-q")
    (sub / "PLAN.md").write_text("draft\n")
    git(top, "add", "-A")
    git(top, "commit", "-q", "-m", "first")
    first = git(top, "rev-parse", "HEAD")
    (sub / "PLAN.md").write_text("frozen\n")
    git(top, "add", "-A")
    git(top, "commit", "-q", "-m", "freeze")
    freeze = git(top, "rev-parse", "HEAD")
    (sub / "other.txt").write_text("later\n")
    git(top, "add", "-A")
    git(top, "commit", "-q", "-m", "later")
    return {"top": top, "sub": sub, "first": first, "freeze": freeze}


def state(repo, **kw):
    return ro.frozen_plan_state(repo["sub"], freeze_commit=kw.pop("freeze", repo["freeze"]), plan_file="PLAN.md")


def test_a_clean_frozen_plan_passes(repo, opened):
    s = state(repo)
    assert s["established"] is True and s["why"] is None
    assert s["plan_has_no_uncommitted_change"] is True and s["freeze_commit_is_an_ancestor_of_head"] is True
    assert s["plan_equals_the_freeze_commits"] is True
    assert s["head"] == git(repo["top"], "rev-parse", "HEAD") and len(s["head"]) == 40
    assert s["plan_blob"] == git(repo["top"], "rev-parse", "HEAD:gizmo/PLAN.md")
    assert s["freeze_commit"] == repo["freeze"]
    rec = Recorder()
    got = ro.load_outcomes_after_the_freeze(reader=rec, plan_state=lambda: s)
    assert len(rec.calls) == 1 and got.record["plan_state"] == s
    assert str(repo["top"]) not in json.dumps(s)


def test_an_uncommitted_edit_of_the_plan_is_refused_staged_or_not(repo, opened):
    (repo["sub"] / "PLAN.md").write_text("frozen, then edited\n")
    s = state(repo)
    assert s["established"] is True and s["plan_has_no_uncommitted_change"] is False
    with pytest.raises(ro.OutcomeAccessRefused, match="uncommitted change"):
        ro.load_outcomes_after_the_freeze(reader=Recorder(), plan_state=lambda: s)
    git(repo["top"], "add", "gizmo/PLAN.md")                                                       # staged
    assert state(repo)["plan_has_no_uncommitted_change"] is False
    git(repo["top"], "reset", "-q", "--hard")
    assert state(repo)["plan_has_no_uncommitted_change"] is True
    (repo["sub"] / "PLAN.md").unlink()                                                            # deleted
    assert state(repo)["plan_has_no_uncommitted_change"] is False


def test_an_untracked_plan_is_refused(tmp_path, monkeypatch, opened):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    top = tmp_path / "r"
    top.mkdir()
    git(top, "init", "-q")
    (top / "a.txt").write_text("a\n")
    git(top, "add", "-A")
    git(top, "commit", "-q", "-m", "a")
    c = git(top, "rev-parse", "HEAD")
    (top / "PLAN.md").write_text("never committed\n")
    s = ro.frozen_plan_state(top, freeze_commit=c, plan_file="PLAN.md")
    assert s["plan_blob"] is None and s["plan_has_no_uncommitted_change"] is False
    with pytest.raises(ro.OutcomeAccessRefused):
        ro.load_outcomes_after_the_freeze(reader=Recorder(), plan_state=lambda: s)


def test_a_freeze_commit_that_is_not_an_ancestor_is_refused(repo, opened):
    git(repo["top"], "checkout", "-q", "-b", "side", repo["first"])
    (repo["sub"] / "PLAN.md").write_text("another history\n")
    git(repo["top"], "commit", "-q", "-am", "side")
    s = state(repo)
    assert s["established"] is True and s["freeze_commit_is_an_ancestor_of_head"] is False
    assert s["plan_has_no_uncommitted_change"] is True and s["plan_equals_the_freeze_commits"] is False
    with pytest.raises(ro.OutcomeAccessRefused, match="is not an ancestor of HEAD"):
        ro.load_outcomes_after_the_freeze(reader=Recorder(), plan_state=lambda: s)


def test_a_committed_amendment_passes_with_the_plan_unequal_to_the_freeze_commits(repo, opened):
    (repo["sub"] / "PLAN.md").write_text("frozen\n\nDeviations log: an amendment, committed\n")
    git(repo["top"], "commit", "-q", "-am", "amendment")
    s = state(repo)
    assert s["established"] is True and s["plan_has_no_uncommitted_change"] is True
    assert s["freeze_commit_is_an_ancestor_of_head"] is True and s["plan_equals_the_freeze_commits"] is False
    rec = Recorder()
    got = ro.load_outcomes_after_the_freeze(reader=rec, plan_state=lambda: s)
    assert len(rec.calls) == 1 and got.record["plan_state"]["plan_equals_the_freeze_commits"] is False


def test_a_folder_that_is_not_a_repository_is_not_established(tmp_path, monkeypatch, opened):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "PLAN.md").write_text("x\n")
    s = ro.frozen_plan_state(plain, freeze_commit="0" * 40, plan_file="PLAN.md")
    assert s["established"] is False and "not inside a git work tree" in s["why"]
    with pytest.raises(ro.OutcomeAccessRefused, match="could not be established"):
        ro.load_outcomes_after_the_freeze(reader=Recorder(), plan_state=lambda: s)
    missing = ro.frozen_plan_state(tmp_path / "no_such_folder", plan_file="PLAN.md")
    assert missing["established"] is False and "git could not be run" in missing["why"]
    assert str(tmp_path) not in missing["why"]


def test_a_freeze_commit_unknown_to_the_repository_is_not_established(repo, opened):
    s = state(repo, freeze="1234567" * 5 + "12345")
    assert s["established"] is False and "could not be found or compared" in s["why"]


def test_a_freeze_commit_without_the_plan_is_not_established(repo, opened):
    """A commit with no plan file named as the freeze (an unrelated orphan commit, so merge-base answers 'not an
    ancestor' and the plan lookup at the freeze commit fails): not established."""
    top = repo["top"]
    branch = git(top, "branch", "--show-current")
    git(top, "checkout", "-q", "--orphan", "bare")
    git(top, "rm", "-rq", "--cached", ".")
    (top / "x.txt").write_text("x\n")
    git(top, "add", "x.txt")
    git(top, "commit", "-q", "-m", "no plan")
    orphan = git(top, "rev-parse", "HEAD")
    git(top, "checkout", "-q", "-f", branch)
    s = state(repo, freeze=orphan)
    assert s["established"] is False and "holds no PLAN.md" in s["why"]


def test_the_plan_check_uses_only_read_only_git_commands():
    fn = ast.parse(inspect.getsource(ro.frozen_plan_state)).body[0]
    verbs = [n.args[1].value for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_git"
             and len(n.args) > 1 and isinstance(n.args[1], ast.Constant)]
    assert set(verbs) == {"rev-parse", "status", "merge-base"}, verbs
    src = inspect.getsource(ro._git)
    assert "GIT_OPTIONAL_LOCKS" in src and "check=False" in src
