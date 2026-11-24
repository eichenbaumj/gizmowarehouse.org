#!/usr/bin/env python3
"""The results writer and the execution coordinator for the runs on outcomes after the freeze.

The owner's words (Joe, session 27), unchanged: "Build the results writer and execution coordinator so that results are
recorded with their provenance and the frozen commit, and execution and reporting follow the recorded order: U, then C,
then the inventory-against-sales check, then the remaining runs. Test this sequence entirely on invented inputs."

The plan is frozen at commit ea426c4 (the approved specification is commit ed3a2ff); it is internally frozen and not
externally preregistered. Freeze approval, implementation readiness and authorization to access outcomes are three
separate steps. When this module was built (session 27) only the first had been given and GATE1_SIGNED did not exist;
Joe's limited, conditional authorization of 2026-11-20 (D-122) is for one read through this module and rows U and C,
and the changes session 28 made here under it are the stop before any estimator and the resume check on code identity,
both made before any outcome was read. Nothing here creates GATE1_SIGNED or sets the variable
DCUB_OUTCOME_RUN_AUTHORIZED. Everything here was built and tested on invented inputs only.

What is here
------------
provenance(...)         the record carried by every result: the frozen commit and the approved specification's commit;
                        the commit of the code that ran (git rev-parse HEAD in the gizmo folder), the code's identity
                        (the git tree ids of pipeline and tests and the blob id of PREANALYSIS.md at that commit) and
                        whether the folder's code and plan have no uncommitted change (git status --porcelain --
                        pipeline tests PREANALYSIS.md prints nothing, untracked files included); the gate file's name
                        and whether it exists (looked up
                        when called, never created) and whether the variable is "1"; the hash of the outcome file as the
                        reader returned it (from the door's record, None in words when nothing was read); what the inputs
                        are; the fingerprint of the assembler's record; the interpreter, the versions of numpy, pandas,
                        scipy and statsmodels, and whether the pinned package imports with its version; the platform; the
                        UTC time. No outcome value is in it.
to_jsonable(obj)        the conversion rule for anything JSON cannot hold (below).
ResultsWriter(dir)      writes into ONE directory given by the caller and nowhere else: one JSON file per record, a
                        manifest.json listing every record in the order written, and a plain-text report.txt appended in
                        the same order. It never overwrites, and every write is atomic.
Coordinator(dir, ...)   the stages in the recorded order, row_U, row_C, inventory_against_sales and remaining, with the
                        order read from the manifest on disk so that a later process can take the sequence up again.
execute_research(...)   the research path, one function, with every piece replaceable and looked up when called.
main(argv)              calls execute_research with explicit arguments; with no arguments it prints what it would do and
                        does nothing.

Where the order of unblinding is enforced
-----------------------------------------
run_outcomes.run and run_outcomes.run_all are not changed by this module and do not check the order: run runs any entry
at any time and run_all runs every entry in one pass. The coordinator is where the order is enforced. An entry is run
only when every entry before it in run_outcomes.ORDER_OF_UNBLINDING is written and reported; a request out of order is
refused in words that name the next entry expected, and an entry already written is refused and never run twice. At the
start the coordinator checks that the first three ids of ORDER_OF_UNBLINDING are reconciliation_row_U,
reconciliation_row_C and inventory_against_sales, in that order, so that a later change to the registry cannot silently
reorder the stages.

"Written and reported" (the session's reading, stated here as the brief asks): the record file exists in the directory
with the sha256 the manifest gives it, manifest.json lists it, and its section is in report.txt. The coordinator checks
all three on disk for every earlier entry before it runs the next one. Whether a run pauses for Joe after rows U and C is
not decided here; `through=` stops after any stage, and a later coordinator on the same directory takes up at the next
entry.

The conversion rule (the agent's reading of "converted by rule")
-----------------------------------------------------------------
None, bool, int and str are kept. A finite float is kept; NaN, plus infinity and minus infinity become {"$float": "NaN"},
{"$float": "Infinity"} and {"$float": "-Infinity"}, so the file is strict JSON. numpy integers, floats, booleans and
strings become their Python values under the same rule; numpy arrays become nested lists. A pandas DataFrame becomes
{"$frame": {"columns", "dtypes", "index", "rows"}}, a Series {"$series": {"name", "dtype", "index", "values"}}, an Index a
list, a Timestamp its ISO text, pd.NA and NaT {"$missing": "NA"} and {"$missing": "NaT"}. A set or frozenset becomes
{"$set": [...]} sorted by the JSON text of each member; a tuple becomes a list. A mapping whose keys are all text stays a
mapping; keys that are whole numbers or booleans or None become their text, a tuple key becomes the JSON text of the
tuple as a list (for example [1, "AA"]), and a mapping whose converted keys would collide, or that has a key of any other
kind, becomes {"$mapping": [[key, value], ...]}. A dataclass becomes {"$dataclass": its qualified name, "fields": {...}},
an exception {"$exception": its type name, "message": its text}, a path its text, a date or time its ISO text, an Enum its
value. Anything else becomes the text "<not serialized: module.QualifiedName>" and its place in the record is listed
under `not_serialized` with its type; a cycle is treated the same way. Nothing is ever an error that loses the result.

How the Callaway and Sant'Anna entry is run (the session's decision and reading)
-------------------------------------------------------------------------------
The whole research execution is one pass under .venv/bin/python -I, where diff-diff 4.0.0 imports, so the
callaway_santanna entry and its row of the side-by-side table (estimators_agree) are never a failure in words for want of
the package. The research path refuses in words, before anything is read, unless the pinned package imports. On
2026-11-20 the machine's Python and .venv had the same Python 3.13.5, numpy 2.4.6, pandas 2.2.3, scipy 1.17.1 and
statsmodels 0.14.6 (the session's reading); every record carries the versions of the run that wrote it, so a difference
is visible, and a resumed run whose versions differ from the manifest's is refused.

The research path, in order
---------------------------
(a) inputs_are must be RESEARCH_DATA_AFTER_THE_FREEZE; INVENTED_INPUTS is refused on this path (tests of the sequence use
    the coordinator directly), and the first three ids of ORDER_OF_UNBLINDING are checked; (b) the pinned package must
    import; (c) the code's working tree must be clean as in provenance; (d) the inputs are assembled on the quantity side
    (assemble_inputs.assemble, looked up when called) and RunInputs.inventory_inputs_are and reconciliation_u_inputs_are
    must both be RESEARCH_DATA_AFTER_THE_FREEZE; (d') nothing that can be refused without the outcomes waits for them:
    the provenance is built without an outcome record and the output directory is checked against it before the door
    (a manifest written under another order, a damaged directory, and a resume whose frozen commit, specification
    commit, code identity, inputs, Python and library versions or assembler fingerprint disagree with the manifest's are
    all refused with the door not called); and a process that will run no entry taking an outcome does not read the
    outcomes. Which entries take one is read from the registry's own fields (run_outcomes.REGISTRY_BY_ID[id].outcome
    and .outcomes, takes_outcome). A process taken up after rows U and C with through="inventory_against_sales" runs
    only the inventory check, which reads quantities only, so the door is not called, no read-time record is written
    for that process, the entry is run with no outcome frames, and the provenance says in words that no outcome was
    read by this process (NO_READ_BY_THIS_PROCESS); a later process with an outcome hash agrees with it, since the hash
    is compared only when both sides have one; (e) when an entry to run takes an outcome, the outcomes are read ONCE
    through
    run_outcomes.load_outcomes_after_the_freeze() and by no other route, and any refusal of the door stops everything with
    nothing run and nothing written, and after the read the outcome hash is compared with the manifest's (a different
    hash is refused with nothing written); (f) before any estimate, outcome_frames.read_time_checks and outcome_frames.reshape
    are computed and written, with the assembler's record and the door's record, as the first record of the directory
    (counts and keys only, no value); a failed check fills, drops and repairs nothing; (f') THE STOP BEFORE ANY
    ESTIMATOR (Joe, 2026-11-20, D-122): outcome_frames.blocking_decision is asked, and when a blocking check did not
    pass (a key column missing or untypable, a repeated outcome unit-year, the two files not holding the same
    unit-years, a usable-flagged unit-year with no outcome row or a missing, non-finite or non-positive price, or the
    checks or the reshaper raising) the first record is written with the full check report and the decision in words,
    IntegrityCheckBlocked is raised and no stage is run; a check that is recorded and does not block (the loggability
    counts, row U's flag coverage) leaves the affected runs to stop in their own words; (g) the stages, in order, with
    the inventory check's inputs as the assembler built them.

Code identity on a resume (Joe, 2026-11-20, D-122: "Compare code identity")
--------------------------------------------------------------------------
A resumed run is refused unless the git tree ids of pipeline and tests and the blob id of PREANALYSIS.md at its commit
equal the manifest's. The commit is recorded with every result and is not compared, so a later commit that changes
documents only, or a commit elsewhere in the repository, does not make a continuation refuse, and a commit that changes
any file under pipeline, under tests or the plan does. The clean-tree requirement on those three paths is unchanged.
This check was changed once, before the first read of an outcome, and is not changed after it.
Nothing in a test calls this path with the real door, the real assembler or a real file: the real door refuses anyway
while the gate file does not exist.

Files this module can open or write
-----------------------------------
It writes only inside the directory the caller gives: <dir>/manifest.json, <dir>/report.txt, <dir>/NNNN_<id>.json and
temporary files <dir>/.tmp-*.part that are renamed or removed. It reads those same files. It creates <dir> (with its
parents) on the first write and never before. DEFAULT_OUTPUT_ROOT (<gizmo>/data/results/outcome_runs/<UTC stamp>) is used
only when main is given "--output-dir default". It runs git read-only in the gizmo folder (rev-parse and status) and
looks up whether the gate file exists. Through the pieces it calls on the research path (the assembler and the door) it
reaches what those modules read; it opens nothing else itself.

Readings that are the agent's, not the plan's, are marked where they are used.

Run:  .venv/bin/python -I pipeline/analysis/execute_outcomes.py      prints what it would do and does nothing
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import enum
import hashlib
import importlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePath

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import run_outcomes as ro  # noqa: E402

# ---- constants ---------------------------------------------------------------------------------------------------------

DEFAULT_OUTPUT_ROOT = ROOT / "data" / "results" / "outcome_runs"
MANIFEST = "manifest.json"
REPORT = "report.txt"
TMP_PREFIX = ".tmp-"
TMP_SUFFIX = ".part"

STAGE_ROW_U, STAGE_ROW_C, STAGE_INVENTORY, STAGE_REMAINING = "row_U", "row_C", "inventory_against_sales", "remaining"
STAGES = (STAGE_ROW_U, STAGE_ROW_C, STAGE_INVENTORY, STAGE_REMAINING)
RECORDED_START = ("reconciliation_row_U", "reconciliation_row_C", "inventory_against_sales")
STAGE_OF_START = dict(zip(RECORDED_START, STAGES[:3]))
BEFORE_ANY_ESTIMATE = "before_any_estimate"
KIND_ENTRY, KIND_READ_TIME_CHECKS = "entry", "read_time_checks"

ROW_U_WINDOW = (2015, 2025)        # U3's window, as RowUInputs and short_form_filers.adopted_row_u_flags take it
CODE_PATHS = ("pipeline", "tests", "PREANALYSIS.md")
LIBRARIES = ("numpy", "pandas", "scipy", "statsmodels")

# Keys left out of the assembler's record before it is fingerprinted, because they are clock readings that differ from
# one assembly to the next on the same inputs (assemble_inputs records seconds per field and per source). The agent's
# reading: the fingerprint is meant to show the same inputs, not the same timing.
VOLATILE_RECORD_KEYS = frozenset({"seconds", "_seconds_by_source", "read_at_utc", "time_utc", "written_at_utc",
                                  "assembled_at_utc"})

CODE_IDENTITY_MEANS = ("git rev-parse --verify HEAD:./<path>, run in the gizmo folder, for pipeline, tests and "
                       "PREANALYSIS.md: the git tree id of pipeline and of tests and the blob id of the plan at the "
                       "commit. An id depends only on the content under its path, so with tree_clean true the three ids "
                       "are the code and the plan that ran, whatever else the repository's commit holds. A resumed run "
                       "is refused unless all three equal the manifest's (Joe, 2026-11-20, D-122: \"Compare code "
                       "identity\"); the commit is recorded and not compared")

FROZEN_PLAN_STATEMENT = ("the plan is frozen at commit ea426c4 (approved specification ed3a2ff), internally frozen and "
                         "not externally preregistered")

ORDER_ENFORCEMENT = ("run_outcomes.run and run_outcomes.run_all are not changed and do not check the order; the "
                     "coordinator in pipeline/analysis/execute_outcomes.py is where the order is enforced")


# ---- refusals ----------------------------------------------------------------------------------------------------------

class OrderRefused(RuntimeError):
    """A request out of the recorded order, an entry already written, a stage named out of order, or a registry whose
    order does not begin with rows U and C and the inventory check. Raised in words; nothing is run or written."""


class RecordRefused(RuntimeError):
    """The writer refuses a record: its file already exists, its sequence number is already in the manifest, it has no
    provenance, or its path would leave the directory. Raised in words; nothing is overwritten."""


class ProvenanceDisagrees(RuntimeError):
    """A resumed run whose provenance does not agree with the manifest's. Raised in words before anything is run."""


class DirectoryDamaged(RuntimeError):
    """The manifest lists a record whose file is missing or whose hash differs, or whose report section is absent, or
    the manifest's entries are not a prefix of the recorded order. Raised in words; nothing is run."""


class ResearchPathRefused(PermissionError):
    """The research path refuses in words before reading anything: invented inputs, the pinned package not importable,
    a working tree with an uncommitted change, or inputs whose stated kind is not research data after the freeze."""


class IntegrityCheckBlocked(RuntimeError):
    """A blocking read-time integrity check did not pass (outcome_frames.blocking_decision). Raised in words AFTER the
    first record, with the full check report and the decision, is written and reported, and BEFORE any stage: no
    estimator is called. `decision` is the decision's record and `first_record` the manifest line of the record written."""

    def __init__(self, message: str, decision: dict | None = None, first_record: dict | None = None):
        super().__init__(message)
        self.decision, self.first_record = decision, first_record


# ---- small helpers -----------------------------------------------------------------------------------------------------

def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _words(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _qualname(obj) -> str:
    t = obj if isinstance(obj, type) else type(obj)
    return f"{t.__module__}.{t.__qualname__}"


def _display_path(p) -> str:
    """A path for a record with no absolute path that carries a person's name (the agent's reading): inside the gizmo
    folder as ./relative, inside the home folder as ~/relative, otherwise as it is."""
    try:
        q = Path(p)
    except TypeError:
        return str(p)
    for base, label in ((ROOT, "."), (Path.home(), "~")):
        try:
            return f"{label}/{q.relative_to(base).as_posix()}"
        except ValueError:
            continue
    return str(q)


def stage_of(entry_id: str) -> str:
    return STAGE_OF_START.get(entry_id, STAGE_REMAINING)


def order_ids() -> list:
    """The ids of run_outcomes.ORDER_OF_UNBLINDING, looked up when called."""
    return [getattr(e, "id", e) for e in ro.ORDER_OF_UNBLINDING]


def check_recorded_order(ids=None) -> list:
    """Refuses in words (OrderRefused) unless the first three ids of ORDER_OF_UNBLINDING are reconciliation_row_U,
    reconciliation_row_C and inventory_against_sales in that order and no id repeats. Returns the ids."""
    ids = order_ids() if ids is None else list(ids)
    if tuple(ids[:3]) != RECORDED_START:
        raise OrderRefused(f"the registry's order of unblinding begins {ids[:3]}, not {list(RECORDED_START)}: the recorded "
                           "order is row U, then row C, then the inventory-against-sales check, then the remaining runs, "
                           "and the coordinator does not run a registry whose order has changed at its start")
    if len(set(ids)) != len(ids):
        raise OrderRefused("the registry's order of unblinding repeats an id; nothing is run")
    return ids


# ---- the conversion rule -------------------------------------------------------------------------------------------------

def _float(x: float):
    if math.isnan(x):
        return {"$float": "NaN"}
    if math.isinf(x):
        return {"$float": "Infinity" if x > 0 else "-Infinity"}
    return x


def _sort_key(v) -> str:
    return json.dumps(v, sort_keys=True, allow_nan=False, default=str)


def to_jsonable(obj, path: str = "$", not_serialized: list | None = None, _stack: set | None = None):
    """obj converted by the rule in the module docstring. `not_serialized` collects {"path", "type"} for everything the
    rule does not cover; such a thing is written as a string naming its type."""
    ns = [] if not_serialized is None else not_serialized
    stack = set() if _stack is None else _stack

    def uncovered(why_type: str):
        ns.append({"path": path, "type": why_type})
        return f"<not serialized: {why_type}>"

    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return int(obj)
    if isinstance(obj, float):
        return _float(float(obj))
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return _float(float(obj))
    if isinstance(obj, np.str_):
        return str(obj)
    if isinstance(obj, (np.datetime64, np.timedelta64)):
        return str(obj)
    if obj is pd.NA:
        return {"$missing": "NA"}
    if obj is pd.NaT:
        return {"$missing": "NaT"}
    if isinstance(obj, (pd.Timestamp, _dt.datetime, _dt.date, _dt.time)):
        return obj.isoformat()
    if isinstance(obj, (pd.Timedelta, _dt.timedelta)):
        return str(obj)
    if isinstance(obj, enum.Enum):
        return to_jsonable(obj.value, path, ns, stack)
    if isinstance(obj, PurePath):
        return str(obj)
    if isinstance(obj, BaseException):
        return {"$exception": type(obj).__name__, "message": str(obj)}

    oid = id(obj)
    if oid in stack:
        return uncovered(f"cycle back to a {_qualname(obj)}")
    stack.add(oid)
    try:
        if isinstance(obj, np.ndarray):
            return to_jsonable(obj.tolist(), path, ns, stack)
        if isinstance(obj, pd.DataFrame):
            return {"$frame": {"columns": [to_jsonable(c, f"{path}.columns[{i}]", ns, stack)
                                           for i, c in enumerate(obj.columns)],
                               "dtypes": [str(t) for t in obj.dtypes],
                               "index": [to_jsonable(x, f"{path}.index[{i}]", ns, stack)
                                         for i, x in enumerate(obj.index)],
                               "rows": [[to_jsonable(v, f"{path}.rows[{i}][{j}]", ns, stack) for j, v in enumerate(row)]
                                        for i, row in enumerate(obj.itertuples(index=False, name=None))]}}
        if isinstance(obj, pd.Series):
            return {"$series": {"name": to_jsonable(obj.name, f"{path}.name", ns, stack), "dtype": str(obj.dtype),
                                "index": [to_jsonable(x, f"{path}.index[{i}]", ns, stack)
                                          for i, x in enumerate(obj.index)],
                                "values": [to_jsonable(v, f"{path}.values[{i}]", ns, stack)
                                           for i, v in enumerate(obj.tolist())]}}
        if isinstance(obj, pd.Index):
            return [to_jsonable(x, f"{path}[{i}]", ns, stack) for i, x in enumerate(obj.tolist())]
        if isinstance(obj, (set, frozenset)):
            members = [to_jsonable(x, f"{path}{{}}", ns, stack) for x in obj]
            return {"$set": sorted(members, key=_sort_key)}
        if isinstance(obj, (list, tuple)):
            return [to_jsonable(x, f"{path}[{i}]", ns, stack) for i, x in enumerate(obj)]
        if isinstance(obj, dict):
            return _mapping(obj, path, ns, stack)
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {"$dataclass": _qualname(obj),
                    "fields": {f.name: to_jsonable(getattr(obj, f.name, None), f"{path}.{f.name}", ns, stack)
                               for f in dataclasses.fields(obj)}}
        return uncovered(_qualname(obj))
    finally:
        stack.discard(oid)


def _key_text(k):
    """A mapping key as text by the rule, or None when the rule does not cover it."""
    if isinstance(k, str):
        return k
    if isinstance(k, np.str_):
        return str(k)
    if k is None or isinstance(k, (bool, np.bool_)):
        return json.dumps(bool(k) if k is not None else None)
    if isinstance(k, (int, np.integer)):
        return str(int(k))
    if isinstance(k, tuple):
        try:
            return json.dumps(to_jsonable(list(k), "$key", []), allow_nan=False)
        except (TypeError, ValueError):
            return None
    return None


def _mapping(d: dict, path: str, ns: list, stack: set):
    texts = [_key_text(k) for k in d]
    if all(t is not None for t in texts) and len(set(texts)) == len(texts):
        return {t: to_jsonable(v, f"{path}[{json.dumps(t)}]", ns, stack) for t, v in zip(texts, d.values())}
    return {"$mapping": [[to_jsonable(k, f"{path}.key[{i}]", ns, stack),
                          to_jsonable(v, f"{path}.value[{i}]", ns, stack)] for i, (k, v) in enumerate(d.items())]}


def _dumps(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=False, allow_nan=False, ensure_ascii=False) + "\n"


def fingerprint_record(record) -> str | None:
    """sha256 of a record converted by the rule, with VOLATILE_RECORD_KEYS left out at every depth. None for None."""
    if record is None:
        return None

    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k not in VOLATILE_RECORD_KEYS}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    conv = strip(to_jsonable(record, "$", []))
    return hashlib.sha256(json.dumps(conv, sort_keys=True, allow_nan=False).encode()).hexdigest()


# ---- provenance ------------------------------------------------------------------------------------------------------------

def _default_git(root):
    def git(args):
        p = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=False,
                           env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        return p.returncode, p.stdout
    return git


def code_state(git=None, root=None) -> dict:
    """The commit of the code, the code's identity and whether the gizmo folder's code and plan have no uncommitted
    change. Read-only git: rev-parse HEAD, status --porcelain -- pipeline tests PREANALYSIS.md, and rev-parse
    HEAD:./<path> for each of the three paths (the git tree id of pipeline and of tests and the blob id of the plan at
    the commit), with `root` (the gizmo folder by default) as the working directory. `git` replaces the runner: a
    callable taking the argument list and returning (returncode,
    stdout). Untracked files under those paths count as an uncommitted change (the agent's reading: they can be code
    that ran)."""
    run = git if git is not None else _default_git(ROOT if root is None else root)
    out = {"commit": None, "tree_clean": None, "paths_checked": list(CODE_PATHS), "uncommitted_lines": None,
           "established": False, "why": None,
           "tree_clean_means": ("git status --porcelain -- pipeline tests PREANALYSIS.md, run in the gizmo folder, printed "
                                "nothing (untracked files included), so the commit is the code that ran"),
           "code_identity": {p: None for p in CODE_PATHS},
           "code_identity_means": CODE_IDENTITY_MEANS}
    try:
        rc, so = run(["rev-parse", "--verify", "HEAD"])
        if rc != 0 or not so.strip():
            out["why"] = f"git rev-parse --verify HEAD returned {rc}: the code's commit could not be read"
            return out
        out["commit"] = so.strip()
        rc, so = run(["status", "--porcelain", "--", *CODE_PATHS])
        if rc != 0:
            out["why"] = f"git status --porcelain returned {rc}: whether the tree is clean could not be read"
            return out
        lines = [x for x in so.splitlines() if x.strip()]
        out["uncommitted_lines"] = len(lines)
        out["tree_clean"] = not lines
        for path in CODE_PATHS:
            rc, so = run(["rev-parse", "--verify", f"HEAD:./{path}"])
            if rc != 0 or not so.strip():
                out["why"] = (f"git rev-parse --verify HEAD:./{path} returned {rc}: the code's identity could not be "
                              "read")
                return out
            out["code_identity"][path] = so.strip()
    except (OSError, ValueError) as exc:
        out["why"] = f"git could not be run in the gizmo folder ({type(exc).__name__})"
        return out
    out["established"] = True
    return out


def pinned_package_state() -> dict:
    """Whether diff-diff imports at the pinned version, through callaway_santanna._import_pinned (looked up when called).
    Never raises."""
    csa = ro.csa
    rec = {"package": csa.PINNED_PACKAGE, "pinned_version": csa.PINNED_VERSION, "imports": False, "version": None,
           "why_not": None}
    try:
        mod = csa._import_pinned()
        rec.update(imports=True, version=getattr(mod, "__version__", None))
    except Exception as exc:                                         # noqa: BLE001  recorded in words
        rec["why_not"] = _words(exc)
    return rec


def library_versions() -> dict:
    out = {}
    for name in LIBRARIES:
        try:
            out[name] = getattr(importlib.import_module(name), "__version__", None)
        except Exception as exc:                                     # noqa: BLE001  recorded in words
            out[name] = f"not importable: {type(exc).__name__}"
    return out


def gate_state() -> dict:
    """The gate file's name and whether it exists (run_outcomes.panel.GATE_FILE, looked up when called; never created),
    and whether the authorization variable is exactly "1"."""
    gate = Path(ro.panel.GATE_FILE)
    return {"gate_file": gate.name, "gate_file_exists": gate.exists(), "authorization_variable": ro.AUTH_ENV,
            "authorization_variable_is_1": os.environ.get(ro.AUTH_ENV) == "1"}


def provenance(*, inputs_are: str, outcome_record: dict | None = None, assembled_record=None, git=None, root=None,
               package_state: dict | None = None, code: dict | None = None) -> dict:
    """The provenance recorded with every result. No outcome value is in it: the outcome file appears only as its hash,
    taken from the door's record (frame_fingerprint), and the assembler's record only as a fingerprint.

    inputs_are: run_outcomes.INVENTED_INPUTS or RESEARCH_DATA_AFTER_THE_FREEZE, recorded as given (a value outside
    INPUTS_ARE is refused in words). outcome_record: the door's record (OutcomesRead.record) or None when no outcome was
    read. assembled_record: the assembler's record, fingerprinted by fingerprint_record. git, root: passed to code_state.
    package_state: pinned_package_state()'s result when the caller already has it. code: code_state()'s result when the
    caller already has it."""
    if inputs_are not in ro.INPUTS_ARE:
        raise ValueError(f"inputs_are is {inputs_are!r}; it must be {ro.INVENTED_INPUTS!r} or "
                         f"{ro.RESEARCH_DATA_AFTER_THE_FREEZE!r}")
    h = (outcome_record or {}).get("frame_fingerprint") if isinstance(outcome_record, dict) else None
    pkg = pinned_package_state() if package_state is None else dict(package_state)
    vi = sys.version_info
    return {
        "frozen_commit": ro.FREEZE_COMMIT,
        "approved_specification_commit": ro.APPROVED_SPECIFICATION_COMMIT,
        "plan": FROZEN_PLAN_STATEMENT,
        "code": code_state(git, root) if code is None else dict(code),
        "gate": gate_state(),
        "outcome_file_hash": h,
        "outcome_file_hash_in_words": (
            "frame_fingerprint of the outcome file as the reader returned it, from the door's record" if h else
            "None: no outcome was read for this record"),
        "inputs_are": inputs_are,
        "assembled_inputs_record_fingerprint": fingerprint_record(assembled_record),
        "assembled_inputs_record_fingerprint_means": (
            "sha256 of the assembler's record converted by the writer's rule, with clock readings left out "
            f"({', '.join(sorted(VOLATILE_RECORD_KEYS))}); None when no assembler record was given"),
        "interpreter": {"executable": _display_path(sys.executable), "version": sys.version,
                        "python_version": f"{vi.major}.{vi.minor}.{vi.micro}"},
        "libraries": library_versions(),
        "pinned_package": pkg,
        "platform": {"platform": platform.platform(), "machine": platform.machine(), "system": platform.system()},
        "order_of_unblinding_starts": list(RECORDED_START),
        "order_enforcement": ORDER_ENFORCEMENT,
        "time_utc": _utc_now(),
    }


def agreement(old: dict, new: dict) -> list:
    """The differences, in words, between a manifest's provenance and a resumed run's on what must agree: the frozen
    commit, the approved specification's commit, the code's identity (the git tree ids of pipeline and tests and the
    blob id of PREANALYSIS.md; Joe, 2026-11-20, D-122, "Compare code identity"), what the inputs are, the Python version
    and the library versions with the pinned package's, the outcome hash when both have one, and the assembler record's
    fingerprint. Empty when they agree. The code's commit is recorded with every result and is not compared: a later
    commit that leaves the three paths byte for byte as they were is the same code. An identity that either side lacks
    is a difference, never an agreement."""
    diffs = []

    def g(d, *path):
        for p in path:
            d = d.get(p) if isinstance(d, dict) else None
        return d

    for label, path in (("the frozen commit", ("frozen_commit",)),
                        ("the approved specification's commit", ("approved_specification_commit",)),
                        ("what the inputs are", ("inputs_are",)),
                        ("the Python version", ("interpreter", "python_version")),
                        ("the library versions", ("libraries",)),
                        ("the pinned package's version", ("pinned_package", "version")),
                        ("the assembled inputs' record fingerprint", ("assembled_inputs_record_fingerprint",))):
        a, b = g(old, *path), g(new, *path)
        if a != b:
            diffs.append(f"{label} differs (manifest {a!r}, this run {b!r})")
    for path in CODE_PATHS:
        a, b = g(old, "code", "code_identity", path), g(new, "code", "code_identity", path)
        if not a or not b:
            diffs.append(f"the code identity of {path} cannot be compared (manifest {a!r}, this run {b!r}); a run is "
                         "taken up only when both carry the git object id of that path")
        elif a != b:
            diffs.append(f"the code identity of {path} differs (manifest {str(a)[:12]}, this run {str(b)[:12]}): what "
                         f"is under {path} is not what the manifest's run executed")
    a, b = old.get("outcome_file_hash"), new.get("outcome_file_hash")
    if a and b and a != b:
        diffs.append(f"the outcome file's hash differs (manifest {a[:12]}, this run {b[:12]})")
    return diffs


# ---- the results writer ------------------------------------------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _report_header(sequence: int, name: str) -> str:
    return f"[record {sequence:04d}] {name}"


class ResultsWriter:
    """Writes into ONE directory, given by the caller, and nowhere else. The directory (with its parents) is created on
    the first write and never before.

    For each record: (1) the record file NNNN_<id>.json, written to a temporary file in the same directory and then
    linked to its final name, which fails if that name exists, the temporary file then removed (a rename that cannot
    overwrite; where hard links are not supported, an existence check and a rename); (2) manifest.json, rewritten
    through a temporary file and a rename with the record appended, carrying the file's sha256, the stage, the entry id,
    whether it was estimated and the time; (3) report.txt, rewritten through a temporary file and a rename with the
    record's section appended. "Written and reported" means all three are done (the session's reading). Every record
    carries the full provenance; a record with none is refused. A record file that exists, or a sequence number already
    in the manifest, is refused in words and nothing is overwritten."""

    def __init__(self, directory):
        if directory is None:
            raise RecordRefused("the writer needs a directory given by the caller; there is no default")
        self.directory = Path(directory).resolve()

    # -- reading ----------------------------------------------------------------------------------------------------
    @property
    def manifest_path(self) -> Path:
        return self.directory / MANIFEST

    @property
    def report_path(self) -> Path:
        return self.directory / REPORT

    def manifest(self) -> dict | None:
        p = self.manifest_path
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def report_text(self) -> str:
        p = self.report_path
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # -- writing ----------------------------------------------------------------------------------------------------
    def _inside(self, p: Path) -> Path:
        p = Path(p)
        if p.parent.resolve() != self.directory:
            raise RecordRefused(f"refused: {p.name} would be written outside the directory given")
        return p

    def _tmp(self, text: str) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=TMP_PREFIX, suffix=TMP_SUFFIX, dir=str(self.directory))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self._inside(Path(tmp))
        return tmp

    def _replace(self, final: Path, text: str) -> None:
        tmp = self._tmp(text)
        os.replace(tmp, str(self._inside(final)))

    def _create(self, final: Path, text: str) -> None:
        """Atomic creation that never overwrites."""
        final = self._inside(final)
        if final.exists():
            raise RecordRefused(f"refused: {final.name} already exists in the directory; a record is never overwritten")
        tmp = self._tmp(text)
        try:
            try:
                os.link(tmp, str(final))
            except FileExistsError:
                raise RecordRefused(f"refused: {final.name} already exists in the directory; a record is never "
                                    "overwritten") from None
            except OSError:
                if final.exists():
                    raise RecordRefused(f"refused: {final.name} already exists in the directory; a record is never "
                                        "overwritten") from None
                os.replace(tmp, str(final))
                tmp = None
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    @staticmethod
    def _refuse_overwrite(seq: int, used: set, final: Path) -> None:
        if seq in used:
            raise RecordRefused(f"refused: sequence number {seq} is already in the manifest; a record is never "
                                "overwritten")
        if final.exists():
            raise RecordRefused(f"refused: {final.name} already exists in the directory; a record is never overwritten")

    def write(self, *, kind: str, stage: str, entry_id: str | None, estimated: bool, body, provenance: dict,
              report_section: str, sequence: int | None = None) -> dict:
        """Writes one record and returns its manifest line. body is converted by the rule (to_jsonable); what the rule
        does not cover is listed under not_serialized in the record."""
        if not isinstance(provenance, dict) or not provenance:
            raise RecordRefused("refused: a record is written only with its full provenance")
        man = self.manifest()
        records = [] if man is None else list(man.get("records", []))
        used = {r["sequence"] for r in records}
        seq = (max(used) + 1 if used else 1) if sequence is None else int(sequence)
        name = entry_id if entry_id else kind
        fname = f"{seq:04d}_{_SAFE.sub('_', name)}.json"
        final = self.directory / fname
        self._refuse_overwrite(seq, used, final)
        ns: list = []
        conv = to_jsonable(body, "$.body", ns)
        rec = {"sequence": seq, "kind": kind, "stage": stage, "entry_id": entry_id, "estimated": bool(estimated),
               "written_at_utc": _utc_now(), "provenance": provenance, "body": conv, "not_serialized": ns,
               "manifest_file": MANIFEST, "report_file": REPORT}
        try:
            text = _dumps(rec)
        except (TypeError, ValueError) as exc:           # the rule should leave nothing; never lose the result
            rec["body"] = f"<not serialized: the converted body could not be written as JSON ({_words(exc)})>"
            rec["not_serialized"] = ns + [{"path": "$.body", "type": f"whole body: {_words(exc)}"}]
            text = _dumps(rec)
        self._create(final, text)
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        line = {"sequence": seq, "file": fname, "sha256": sha, "kind": kind, "stage": stage, "entry_id": entry_id,
                "estimated": bool(estimated), "written_at_utc": rec["written_at_utc"]}
        if man is None:
            man = {"what_this_is": ("The manifest of one execution directory: every record written, in the order "
                                    "written, with its file's sha256. " + FROZEN_PLAN_STATEMENT + ". " +
                                    ORDER_ENFORCEMENT + ". Written by pipeline/analysis/execute_outcomes.py."),
                   "order_of_unblinding": order_ids(), "provenance": provenance, "records": []}
        man["records"] = records + [line]
        self._replace(self.manifest_path, _dumps(man))
        section = (_report_header(seq, name) + "\n" + f"file: {fname} (the numbers are in this JSON record)\n"
                   + report_section.rstrip("\n") + "\n\n")
        self._replace(self.report_path, self.report_text() + section)
        return line

    def verify(self, line: dict) -> str | None:
        """None when the manifest line's record is written and reported; otherwise what is wrong, in words."""
        p = self.directory / line["file"]
        if not p.exists():
            return f"record {line['sequence']} ({line['file']}) is listed in the manifest and its file is missing"
        if hashlib.sha256(p.read_bytes()).hexdigest() != line["sha256"]:
            return f"record {line['sequence']} ({line['file']}) does not have the sha256 the manifest gives it"
        name = line["entry_id"] or line["kind"]
        if _report_header(line["sequence"], name) not in self.report_text():
            return f"record {line['sequence']} ({line['file']}) has no section in {REPORT}"
        return None


# ---- the report section of an entry -----------------------------------------------------------------------------------------

def _failures(obj, path="", out=None, depth=0) -> list:
    """Every failure in words in a run's record: values of keys whose name says failure, reason_not_built or
    outcomes_missing, at any depth, with where they sit."""
    out = [] if out is None else out
    if depth > 12:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            ks = str(k)
            here = f"{path}.{ks}" if path else ks
            if ("failure" in ks or ks in ("reason_not_built", "outcomes_missing")) and v:
                if isinstance(v, str):
                    out.append((here, v))
                elif isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v):
                    out.extend((here, x) for x in v)
                elif isinstance(v, dict) and all(isinstance(x, str) for x in v.values()):
                    out.extend((f"{here}.{kk}", x) for kk, x in v.items())
                else:
                    _failures(v, here, out, depth + 1)
            else:
                _failures(v, here, out, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _failures(v, f"{path}[{i}]", out, depth + 1)
    return out


def entry_report_section(entry_id: str, result) -> str:
    """The plain-text section for one entry: its id, plan section, sets, labels, whether each set's result was estimated
    and every failure in words. No number: the numbers stay in the JSON record."""
    e = ro.REGISTRY_BY_ID.get(entry_id)
    r = result if isinstance(result, dict) else {}
    section = r.get("plan_section") or (e.section if e else "not in the registry")
    sets = r.get("sets") or ([ro.set_label(s) for s in e.sets] if e else [])
    labels = r.get("labels") or (list(e.labels) if e else [])
    lines = [f"entry: {entry_id}", f"stage: {stage_of(entry_id)}", f"plan section: {section}",
             f"sets: {'; '.join(map(str, sets)) or 'none'}", "labels:"]
    lines += [f"  - {x}" for x in labels] or ["  none"]
    lines.append(f"estimated: {'yes' if r.get('estimated') else 'no'}")
    res = r.get("results")
    if isinstance(res, dict) and res:
        lines.append("each set's result:")
        for k, v in res.items():
            est = v.get("estimated") if isinstance(v, dict) else None
            lines.append(f"  - {k}: {'estimated' if est else 'not estimated'}")
    else:
        lines.append("each set's result: none returned" + (f" (status {r.get('status')})" if r.get("status") else ""))
    fails = _failures(r)
    if fails:
        lines.append("failures in words:")
        lines += [f"  - {where}: {words}" for where, words in fails]
    else:
        lines.append("failures in words: none")
    return "\n".join(lines)


# ---- the coordinator -------------------------------------------------------------------------------------------------------

class Coordinator:
    """The stages in the recorded order over one directory. inputs: a run_outcomes.RunInputs. outcomes: what
    run_outcomes.run takes (a frame or a mapping of outcome name to frame). provenance: provenance()'s result, written
    with every record. run: replaces run_outcomes.run (looked up when called when None).

    At construction it checks the start of the registry's order (check_recorded_order), reads the manifest when one
    exists, refuses in words a manifest whose order of unblinding differs from the registry's, a damaged directory, and
    a provenance that does not agree with the manifest's (agreement). Nothing is written by the construction."""

    def __init__(self, directory, inputs, outcomes, *, provenance: dict, run=None):
        self.ids = check_recorded_order()
        self.writer = directory if isinstance(directory, ResultsWriter) else ResultsWriter(directory)
        self.inputs, self.outcomes, self.provenance, self._run = inputs, outcomes, provenance, run
        man = self.writer.manifest()
        if man is not None:
            if man.get("order_of_unblinding") != self.ids:
                raise OrderRefused("the manifest was written under another order of unblinding than the registry's now; "
                                   "the sequence is not taken up")
            diffs = agreement(man.get("provenance") or {}, provenance)
            if diffs:
                raise ProvenanceDisagrees("the run is not taken up: its provenance does not agree with the manifest's. "
                                          + "; ".join(diffs))
        self._state()

    # -- the order as it stands on disk -----------------------------------------------------------------------------
    def _state(self) -> dict:
        """The entries written and reported, in order, read from the manifest on disk and verified."""
        man = self.writer.manifest()
        lines = [] if man is None else list(man.get("records", []))
        for line in lines:
            why = self.writer.verify(line)
            if why:
                raise DirectoryDamaged(f"the directory cannot be taken up: {why}")
        written = [x["entry_id"] for x in lines if x.get("kind") == KIND_ENTRY]
        if written != self.ids[:len(written)]:
            raise DirectoryDamaged(f"the entries in the manifest, {written}, are not the start of the recorded order")
        nxt = self.ids[len(written)] if len(written) < len(self.ids) else None
        return {"written": written, "next": nxt, "lines": lines}

    def next_expected(self) -> str | None:
        return self._state()["next"]

    def _refuse_out_of_order(self, entry_id: str, state: dict) -> None:
        if entry_id not in self.ids:
            raise OrderRefused(f"{entry_id!r} is not in the executable order of unblinding (run_outcomes."
                               "ORDER_OF_UNBLINDING); it is not run")
        if entry_id in state["written"]:
            n = state["written"].index(entry_id)
            raise OrderRefused(f"{entry_id} is already written and reported (entry {n + 1} of the order); an entry is "
                               "never run twice")
        if entry_id != state["next"]:
            raise OrderRefused(f"{entry_id} is refused out of order: the next entry expected is {state['next']} "
                               f"(stage {stage_of(state['next'])}), and every entry before {entry_id} in the recorded "
                               "order must be written and reported before it is run")

    # -- running ----------------------------------------------------------------------------------------------------
    def run_entry(self, entry_id: str) -> dict:
        """Runs one entry when it is the next expected, writes its record and returns the manifest line."""
        state = self._state()
        self._refuse_out_of_order(entry_id, state)
        fn = self._run if self._run is not None else ro.run
        try:
            result = fn(entry_id, self.inputs, self.outcomes)
        except Exception as exc:                                     # noqa: BLE001  written in words, never dropped
            result = {"id": entry_id, "estimated": False, "raised": True,
                      "failure_in_words": f"run_outcomes.run raised {_words(exc)}; nothing was estimated for this entry"}
        if not isinstance(result, dict):
            result = {"id": entry_id, "estimated": False, "returned": result,
                      "failure_in_words": f"run returned a {type(result).__name__}, not a record"}
        return self.writer.write(kind=KIND_ENTRY, stage=stage_of(entry_id), entry_id=entry_id,
                                 estimated=bool(result.get("estimated")), body=result, provenance=self.provenance,
                                 report_section=entry_report_section(entry_id, result))

    def stage_ids(self, stage: str) -> list:
        if stage not in STAGES:
            raise OrderRefused(f"{stage!r} is not a stage; the stages are {list(STAGES)}, in that order")
        if stage == STAGE_REMAINING:
            return self.ids[3:]
        return [self.ids[STAGES.index(stage)]]

    def run_stage(self, stage: str) -> list:
        """Every entry of `stage` not yet written, in order. Refused in words when the stage is not the next one."""
        ids = self.stage_ids(stage)
        state = self._state()
        todo = [i for i in ids if i not in state["written"]]
        if not todo:
            raise OrderRefused(f"the stage {stage} is already written and reported; an entry is never run twice")
        if state["next"] not in ids:
            raise OrderRefused(f"the stage {stage} is refused out of order: the next entry expected is {state['next']} "
                               f"(stage {stage_of(state['next'])})")
        return [self.run_entry(i) for i in todo]

    def pending(self, through: str | None = None) -> list:
        """The ids this coordinator would run with run(through=...), read from the manifest on disk, in order."""
        if through is not None and through not in STAGES:
            raise OrderRefused(f"through={through!r} is not a stage; the stages are {list(STAGES)}")
        last = STAGES.index(through) if through is not None else len(STAGES) - 1
        written = set(self._state()["written"])
        return [i for st in STAGES[:last + 1] for i in self.stage_ids(st) if i not in written]

    def adopt(self, provenance: dict, outcomes) -> None:
        """Takes the provenance made after the read (with the outcome hash) and the outcome frames, after checking the
        provenance against the manifest's again, the outcome hash now included. Refused in words (ProvenanceDisagrees)
        before anything is written."""
        man = self.writer.manifest()
        if man is not None:
            diffs = agreement(man.get("provenance") or {}, provenance)
            if diffs:
                raise ProvenanceDisagrees("the run is not taken up: its provenance does not agree with the manifest's. "
                                          + "; ".join(diffs))
        self.provenance, self.outcomes = provenance, outcomes

    def run(self, through: str | None = None) -> dict:
        """From the next entry expected up to and including the stage `through` (every stage when None), then stops."""
        if through is not None and through not in STAGES:
            raise OrderRefused(f"through={through!r} is not a stage; the stages are {list(STAGES)}")
        last = STAGES.index(through) if through is not None else len(STAGES) - 1
        written = []
        for st in STAGES[:last + 1]:
            state = self._state()
            if all(i in state["written"] for i in self.stage_ids(st)):
                continue
            written += self.run_stage(st)
        return {"written": written, "next_expected": self.next_expected(), "stopped_after": STAGES[last]}


# ---- the research path ---------------------------------------------------------------------------------------------------------

def default_output_dir() -> Path:
    return DEFAULT_OUTPUT_ROOT / _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _require_pinned(state: dict) -> None:
    if not state.get("imports"):
        raise ResearchPathRefused(
            "the research path is not run: the pinned package diff-diff 4.0.0 does not import under this interpreter "
            f"({_display_path(sys.executable)}; {state.get('why_not')}). The whole research execution is one pass under "
            ".venv/bin/python -I so that the Callaway and Sant'Anna entry and its row of the side-by-side table are not "
            "failures for want of the package; nothing was read")


def _require_clean(code: dict) -> None:
    if code.get("tree_clean") is not True:
        why = code.get("why") or f"{code.get('uncommitted_lines')} lines from git status --porcelain"
        raise ResearchPathRefused(
            "the research path is not run: the gizmo folder's code and plan are not shown to have no uncommitted change "
            f"under {', '.join(CODE_PATHS)} ({why}), so the commit recorded would not be the code that ran; nothing was "
            "read")


def _require_identity(code: dict) -> None:
    ids = code.get("code_identity") if isinstance(code.get("code_identity"), dict) else {}
    missing = [p for p in CODE_PATHS if not ids.get(p)]
    if missing or code.get("established") is not True:
        raise ResearchPathRefused(
            "the research path is not run: the code's identity (the git object ids of "
            f"{', '.join(CODE_PATHS)} at the commit) could not be read for {missing or 'the commit'} "
            f"({code.get('why')}), so a later process could not prove it runs the same code; nothing was read")


def _require_research_fields(inputs) -> None:
    bad = {f: getattr(inputs, f, None) for f in ("inventory_inputs_are", "reconciliation_u_inputs_are")
           if getattr(inputs, f, None) != ro.RESEARCH_DATA_AFTER_THE_FREEZE}
    if bad:
        raise ResearchPathRefused(
            f"the research path is not run: the assembled inputs say {bad}, and on this path both inventory_inputs_are "
            f"and reconciliation_u_inputs_are must be {ro.RESEARCH_DATA_AFTER_THE_FREEZE!r}; no outcome was read")


def takes_outcome(entry_id: str) -> bool:
    """Whether a registry entry takes an outcome, from the registry's own fields (run_outcomes.REGISTRY_BY_ID[id].outcome
    and .outcomes), looked up when called; no list is typed here."""
    e = ro.REGISTRY_BY_ID[entry_id]
    return e.outcome is not None or bool(e.outcomes)


NO_READ_BY_THIS_PROCESS = ("None: no outcome was read by this process, because no entry it runs takes an outcome (the "
                           "registry's outcome and outcomes fields); the door was not called")


def _preflight(output_dir, prov0: dict, run):
    """Everything that can be refused without the outcomes, before the door: the start of the order, a manifest written
    under another order, a damaged directory, and agreement with the manifest's provenance on all but the outcome hash
    (prov0 carries none). Returns the Coordinator, which holds no outcomes yet; nothing is written."""
    return Coordinator(output_dir, None, None, provenance=prov0, run=run)


def last_read_time_record(writer: ResultsWriter) -> tuple:
    """(manifest line, body) of the directory's most recent record of the read-time checks, or (None, None)."""
    man = writer.manifest()
    lines = [x for x in (man or {}).get("records", []) if x.get("kind") == KIND_READ_TIME_CHECKS]
    if not lines:
        return None, None
    rec = json.loads((writer.directory / lines[-1]["file"]).read_text(encoding="utf-8"))
    return lines[-1], rec.get("body")


def _refuse_on_a_standing_block(coord: "Coordinator") -> None:
    """Raises IntegrityCheckBlocked, with nothing run and nothing written, when the most recent record of the read-time
    checks in the directory says the run was blocked before any estimator. A later process that reads the outcomes makes
    the checks again itself; this is for a process that reads none."""
    line, body = last_read_time_record(coord.writer)
    if line is None or not isinstance(body, dict):
        return
    if body.get("blocked_before_any_estimator") is not False:
        decision = body.get("blocking_decision") if isinstance(body.get("blocking_decision"), dict) else {}
        raise IntegrityCheckBlocked(
            "the run is stopped before any estimator is called: the directory's most recent record of the read-time "
            f"checks, record {line['sequence']} ({line['file']}), says the run was blocked ("
            + str(decision.get("in_words")) + "); no entry is run on top of a standing block, and nothing was read or "
            "written by this process", decision=decision, first_record=line)


def _read_outcomes_once(door):
    """The door, called once with no argument. Its refusal propagates unchanged."""
    got = door()
    frame, record = getattr(got, "frame", None), getattr(got, "record", None)
    if not isinstance(frame, pd.DataFrame) or not isinstance(record, dict):
        raise ResearchPathRefused(f"the door returned a {type(got).__name__} without a frame and a record; nothing is "
                                  "run and nothing is written")
    return frame, record


def execute_research(*, inputs_are: str, output_dir, through: str | None = None, door=None, assembler=None,
                     reshaper=None, checks=None, decide=None, package_check=None, run=None, git=None,
                     root=None) -> dict:
    """The research path, in the order of the module docstring, (a) to (g). Every piece is replaceable and looked up
    when called: door (run_outcomes.load_outcomes_after_the_freeze), assembler (assemble_inputs.assemble), reshaper
    (outcome_frames.reshape), checks (outcome_frames.read_time_checks), decide (outcome_frames.blocking_decision),
    package_check (pinned_package_state), run (run_outcomes.run), git and root (code_state). Returns what was written
    and the next entry expected. Raises IntegrityCheckBlocked, after the first record is written and before any stage,
    when a blocking read-time check did not pass."""
    # (a) what the inputs are, and the start of the recorded order
    if inputs_are == ro.INVENTED_INPUTS:
        raise ResearchPathRefused("the research path does not take INVENTED_INPUTS: the sequence on invented inputs is "
                                  "tested through the coordinator directly; nothing was read")
    if inputs_are != ro.RESEARCH_DATA_AFTER_THE_FREEZE:
        raise ResearchPathRefused(f"inputs_are is {inputs_are!r}; the research path takes "
                                  f"{ro.RESEARCH_DATA_AFTER_THE_FREEZE!r} only; nothing was read")
    if through is not None and through not in STAGES:
        raise OrderRefused(f"through={through!r} is not a stage; the stages are {list(STAGES)}")
    check_recorded_order()
    if output_dir is None:
        raise ResearchPathRefused("the research path needs an output directory given by the caller")
    # (b) the pinned package, before anything is read
    pkg = (package_check if package_check is not None else pinned_package_state)()
    _require_pinned(pkg)
    # (c) the code's working tree
    code = code_state(git, root)
    _require_clean(code)
    _require_identity(code)
    # (d) the inputs, on the quantity side
    if assembler is None:
        from pipeline.analysis import assemble_inputs           # looked up here, never at import
        assembler = assemble_inputs.assemble
    assembled = assembler(inputs_are=inputs_are)
    inputs = assembled.inputs
    _require_research_fields(inputs)
    # (d') everything that can be refused without the outcomes, before the door
    assembled_record = getattr(assembled, "record", None)
    prov0 = provenance(inputs_are=inputs_are, outcome_record=None, assembled_record=assembled_record,
                       package_state=pkg, code=code)
    coord = _preflight(output_dir, prov0, run)
    todo = coord.pending(through)
    if not any(takes_outcome(i) for i in todo):
        # No entry this process runs takes an outcome: the door is not called and no read-time record is written.
        # The stop holds for such a process too (the session's reading of "any later process", session 28): when the
        # directory's most recent record of the read-time checks says the run was blocked, nothing is run on top of it.
        _refuse_on_a_standing_block(coord)
        prov0["outcome_file_hash_in_words"] = NO_READ_BY_THIS_PROCESS
        coord.adopt(prov0, None)
        coord.inputs = inputs
        done = coord.run(through=through)
        return {"output_dir": _display_path(coord.writer.directory), "first_record": None, "outcomes_read": False,
                **done}
    # (e) the outcomes, once, through the door
    door = door if door is not None else ro.load_outcomes_after_the_freeze
    frame, door_record = _read_outcomes_once(door)
    # (f) the checks and the reshaped frames, before any estimate
    from pipeline.analysis import outcome_frames as of           # looked up here, never at import
    reshaper = of.reshape if reshaper is None else reshaper
    checks = of.read_time_checks if checks is None else checks
    decide = of.blocking_decision if decide is None else decide
    side = inputs.side
    u = getattr(inputs, "reconciliation_u", None)
    # Nothing between the read and the first record may lose the report: a check or a reshaper that raises is recorded
    # by its type name (a message could carry a value) and stops the run through the decision below.
    checks_raised = reshaper_raised = None
    try:
        checked = checks(frame, side.q, getattr(side, "usable", None),
                         getattr(u, "sample_flags", None) if u is not None else None, ROW_U_WINDOW)
    except Exception as exc:                                         # noqa: BLE001  recorded in words; the run is stopped
        checked, checks_raised = None, type(exc).__name__
    else:
        if not isinstance(checked, dict):                            # not a record of checks: treated as not made
            checked, checks_raised = None, f"nothing usable (a {type(checked).__name__}, not a record of checks)"
    try:
        reshaped = reshaper(frame, side.q, getattr(assembled, "cpi_factors", None))
        frames, reshape_report = reshaped.frames, reshaped.report
        if not isinstance(frames, dict) or not isinstance(reshape_report, dict):
            raise TypeError("the reshaper's frames and report are not mappings")
    except Exception as exc:                                         # noqa: BLE001  recorded in words; the run is stopped
        reshaped, frames, reshape_report, reshaper_raised = None, {}, {}, type(exc).__name__
    # (f') the decision, in its one named place, before any stage
    # Fail closed: the run goes on only when the decision says, in so many words, that nothing blocks.
    try:
        decision = decide(checked, checks_raised=checks_raised, reshaper_raised=reshaper_raised)
        if not isinstance(decision, dict) or not isinstance(decision.get("blocks"), bool):
            raise TypeError("the decision is not a record with a true or false `blocks`")
        if not all(isinstance(b, dict) for b in (decision.get("blocking") or [])) or \
                not all(isinstance(b, dict) for b in (decision.get("recorded_and_not_blocking") or [])):
            raise TypeError("the decision's findings are not records")
    except Exception as exc:                                         # noqa: BLE001  recorded in words; the run is stopped
        why = (f"the decision on the read-time checks could not be made ({type(exc).__name__}); a run with no decision "
               "is stopped before any estimator")
        decision = {"blocks": True, "blocking": [{"check": "blocking_decision", "passed": None, "why": why}],
                    "recorded_and_not_blocking": [], "in_words": "BLOCKED before any estimator: " + why}
    blocked = decision["blocks"] is not False
    prov = provenance(inputs_are=inputs_are, outcome_record=door_record, assembled_record=assembled_record,
                      package_state=pkg, code=code)
    # the outcome hash against the manifest's, before anything is written; a blocked run hands no frame to anything
    coord.adopt(prov, None if blocked else frames)
    coord.inputs = inputs
    stamp = getattr(inputs, "inventory_as_built", None)
    first = {
        "what_this_is": ("The record made before any estimate: the door's record of the one read, the assembler's "
                         "record, the checks that can only be made when the outcome file is read, the decision on "
                         "whether they stop the run before any estimator (blocking_decision) and the reshaper's "
                         "report. Counts and keys only, no value. " + FROZEN_PLAN_STATEMENT + ". A failed check fills, "
                         "drops and repairs nothing: a blocking one stops the run here with no entry run, and one that "
                         "is recorded only leaves the affected runs to stop in their own words."),
        "door_record": door_record,
        "assembler_record": assembled_record,
        "assembler_deferred": getattr(assembled, "deferred", None),
        "assembler_inputs_are": getattr(assembled, "inputs_are", None),
        "inventory_check_inputs": {
            "inventory_inputs_are": inputs.inventory_inputs_are,
            "reconciliation_u_inputs_are": inputs.reconciliation_u_inputs_are,
            "inventory_as_built": (None if stamp is None else
                                   {"dose_fingerprint": getattr(stamp, "dose_fingerprint", None),
                                    "source": getattr(stamp, "source", None)}),
            "taken_from": "the assembled inputs (RunInputs), as the assembler built them"},
        "read_time_checks": checked,
        "read_time_checks_raised": checks_raised,
        "read_time_checks_failed": sorted(k for k, v in (checked or {}).items()
                                          if isinstance(v, dict) and v.get("passed") is False),
        "blocking_decision": decision,
        "blocked_before_any_estimator": blocked,
        "reshape_report": reshape_report,
        "reshaper_raised": reshaper_raised,
        "reshape_sources": getattr(reshaped, "sources", None),
        "frames_built": sorted(frames),
        "frames_not_built": {k: v.get("reason_not_built") for k, v in reshape_report.items()
                             if isinstance(v, dict) and not v.get("built")},
        "row_u_window": list(ROW_U_WINDOW),
    }
    try:
        section = _checks_report_section(first)
    except Exception as exc:                                         # noqa: BLE001  the record is still written
        section = ("the record made before any estimate (counts and keys only); its plain-text section could not be "
                   f"composed ({type(exc).__name__}), and the JSON record holds everything. "
                   + ("BLOCKED BEFORE ANY ESTIMATOR: no entry was run." if blocked else ""))
    first_line = coord.writer.write(kind=KIND_READ_TIME_CHECKS, stage=BEFORE_ANY_ESTIMATE, entry_id=None,
                                    estimated=False, body=first, provenance=prov, report_section=section)
    if blocked:
        # The report is on disk (the record, its manifest line and its section of the report). No stage is run.
        raise IntegrityCheckBlocked(
            "the run is stopped before any estimator is called: " + str(decision.get("in_words")) + ". The check "
            f"report is record {first_line['sequence']} ({first_line['file']}) in "
            f"{_display_path(coord.writer.directory)}; no entry was run, and nothing is filled, dropped or repaired",
            decision=decision, first_record=first_line)
    # (g) the stages, in order
    done = coord.run(through=through)
    return {"output_dir": _display_path(coord.writer.directory), "first_record": first_line, "outcomes_read": True,
            **done}


def _checks_report_section(first: dict) -> str:
    lines = ["the record made before any estimate (counts and keys only)",
             f"frames built: {', '.join(first['frames_built']) or 'none'}"]
    for k, why in first["frames_not_built"].items():
        lines.append(f"  - not built: {k}: {why}")
    lines.append("read-time checks that did not pass: " + (", ".join(first["read_time_checks_failed"]) or "none"))
    if first.get("read_time_checks_raised"):
        lines.append(f"the read-time checks raised {first['read_time_checks_raised']} and returned nothing")
    if first.get("reshaper_raised"):
        lines.append(f"the reshaper raised {first['reshaper_raised']} and returned nothing")
    decision = first.get("blocking_decision") or {}
    if decision.get("blocks"):
        lines.append("BLOCKED BEFORE ANY ESTIMATOR: no entry was run. Blocking findings, in words:")
        for b in decision.get("blocking") or []:
            lines.append(f"  - {b.get('check')}: {b.get('why')}")
    else:
        lines.append("blocking integrity checks: none failed; estimation may proceed in the recorded order")
    for r in decision.get("recorded_and_not_blocking") or []:
        lines.append(f"  - recorded and not blocking: {r.get('check')}: {r.get('why_it_does_not_block')}")
    deferred = first.get("assembler_deferred") or []
    lines.append(f"assembler inputs deferred: {len(deferred)}")
    for d in deferred:
        if isinstance(d, dict):
            lines.append(f"  - {d.get('field')}: {d.get('reason_in_words')}")
    return "\n".join(lines)


# ---- main ---------------------------------------------------------------------------------------------------------------------

WHAT_IT_WOULD_DO = (
    "execute_outcomes: the research path after the freeze. With no arguments nothing is done.\n"
    "Arguments: --inputs-are research_data_after_the_freeze (the only value this path takes), --output-dir <a new "
    "directory, or 'default' for data/results/outcome_runs/<UTC stamp>>, --through row_U|row_C|inventory_against_sales|"
    "remaining (optional).\n"
    "It would, in order: refuse invented inputs; check that the order of unblinding begins with rows U and C and the "
    "inventory check; refuse unless diff-diff 4.0.0 imports (run under .venv/bin/python -I); refuse unless git status "
    "--porcelain -- pipeline tests PREANALYSIS.md prints nothing; assemble the inputs on the quantity side; read the "
    "outcomes once through run_outcomes.load_outcomes_after_the_freeze, which refuses without GATE1_SIGNED, without "
    "DCUB_OUTCOME_RUN_AUTHORIZED=1 and when the plan is not the committed frozen one; write the read-time checks, the "
    "decision on whether they stop the run and the reshaper's report as the first record; stop there, with no entry "
    "run, when a blocking integrity check did not pass (exit code 3); otherwise run the stages in the recorded order, "
    "writing and reporting each entry before the next is run. A resumed run is refused unless the git object ids of "
    "pipeline, tests and PREANALYSIS.md equal the manifest's.\n"
    + FROZEN_PLAN_STATEMENT + ". GATE1_SIGNED is created only on Joe's separate "
    "authorization to access outcomes.")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        print(WHAT_IT_WOULD_DO)
        return 0
    ap = argparse.ArgumentParser(prog="execute_outcomes")
    ap.add_argument("--inputs-are", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--through", choices=STAGES, default=None)
    a = ap.parse_args(argv)
    out = default_output_dir() if a.output_dir == "default" else Path(a.output_dir)
    try:
        done = execute_research(inputs_are=a.inputs_are, output_dir=out, through=a.through)
    except IntegrityCheckBlocked as exc:
        print(f"blocked: {exc}")
        return 3
    except (ResearchPathRefused, OrderRefused, ProvenanceDisagrees, DirectoryDamaged, RecordRefused,
            ro.OutcomeAccessRefused) as exc:
        print(f"refused: {exc}")
        return 2
    print(json.dumps(to_jsonable(done), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
