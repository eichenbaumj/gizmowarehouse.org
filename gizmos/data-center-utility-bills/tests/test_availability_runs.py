"""The flag build (P1), the audit (P2) and the preservation step run as real processes, under the real sandbox, on a
made-up tree.

Each test builds a tree in pytest's temporary folder, shaped like the warehouse (repo/gizmos/<gizmo>): copies of the
availability code (and the panel code it calls), a made-up ledger whose authorizing entry carries the pin block for
those copies, a made-up succession table, made-up raw sales, outcome and quantities files built from them, decoys
under data/ the processes must never read, a sibling gizmo's data/ and an access-records folder (under a made-up
HOME). No file under this repository's data/ is opened. Passing these is supporting evidence for the route's
guarantees, not proof of them (D-70 item 9).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import availability_synth as syn  # noqa: E402

from pipeline.electricity import availability_codes as av  # noqa: E402
from pipeline.electricity import availability_pins as pins  # noqa: E402
from pipeline.electricity import availability_run_check as check  # noqa: E402
from pipeline.electricity import panel  # noqa: E402
from pipeline.electricity import succession as succ  # noqa: E402

CODE = sorted(set(av.P1_PINNED) | set(av.P2_PINNED) | set(av.PRESERVE_PINNED) | {"pipeline/electricity/sandbox/denied_probe.txt"})
AUTH = "D-900"
SLUG = "-Users-jeichenbaum-Projects-personal-gizmo-warehouse"

# Each step's permitted success output, line by line. One source: the execution owner's checker, which the scale
# exercise also reads through this module.
P1_OK, P2_OK, PRESERVE_OK, PRESERVE_FILES = check.P1_OK, check.P2_OK, check.PRESERVE_OK, check.PRESERVE_FILES


def write_ledger(t: Path, versions: dict | None = None, pin: bool = True, interp: str | None = None) -> None:
    """A made-up ledger: D-899 says nothing of the audit; D-900 and D-902 each authorize it on this tree and pin its files."""
    block = pins.pin_block(t, versions, interp) if pin else ""
    (t / "docs").mkdir(exist_ok=True)
    (t / "docs/DECISIONS.md").write_text("# made-up ledger\n\n## D-899. Something else\n\nwords\n\n## D-900. Made up: the "
                                         f"availability audit run is authorized on this made-up tree\n\n```\n{block}\n```\n\n"
                                         "## D-902. Made up: a second availability authorization\n\n"
                                         f"```\n{pins.pin_block(t, versions, interp) if pin else ''}\n```\n")


def make_tree(base: Path, rows=None, raw_rows=None) -> Path:
    """A made-up gizmo folder at base/repo/gizmos/gizmo. `rows` build the outcomes on disk; `raw_rows` (default: the
    same) are the raw sales P1 reads."""
    t = base / "repo" / "gizmos" / "gizmo"
    for rel in CODE:
        (t / rel).parent.mkdir(parents=True, exist_ok=True)
        if rel == "pipeline/electricity/succession.csv":
            syn.succession_table().to_csv(t / rel, index=False)
        else:
            shutil.copy(ROOT / rel, t / rel)
    raw = t / "data/raw/pudl"
    raw.mkdir(parents=True)
    syn.write_sales_parquet(syn.sales_frame(rows), raw / "core_eia861__yearly_sales.parquet")
    sales = panel.load_sales(raw / "core_eia861__yearly_sales.parquet")
    q, o = panel.build(sales, succession=succ.resolve(succ.load(t / "pipeline/electricity/succession.csv")))
    old_interim, old_blind = panel.INTERIM, panel.BLIND
    try:
        panel.INTERIM, panel.BLIND = t / "data/interim", t / "data/blind"
        panel.write(q.drop(columns=list(av.NEW_QUANTITY_COLS)), o)        # the files as the panel build wrote them before P1
    finally:
        panel.INTERIM, panel.BLIND = old_interim, old_blind
    if raw_rows is not None:
        syn.write_sales_parquet(syn.sales_frame(raw_rows), raw / "core_eia861__yearly_sales.parquet")
    o.head(2).to_parquet(t / "data/blind/decoy_outcomes.parquet", index=False)
    o.head(2).to_parquet(t / "data/raw/decoy.parquet", index=False)
    (t / "data/interim/decoy.txt").write_text("decoy")
    sibling = base / "repo" / "gizmos" / "other" / "data"
    sibling.mkdir(parents=True)
    o.head(2).to_parquet(sibling / "decoy.parquet", index=False)
    records = base / "home" / ".claude" / "projects" / SLUG / "access-records"
    records.mkdir(parents=True)
    (records / "transcript.txt").write_text("a preserved transcript")
    write_ledger(t)
    return t


def home(t: Path) -> Path:
    return t.parents[2] / "home"


def env_for(t: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "AVAILABILITY_PROFILE_SHA256"}
    env["HOME"] = str(home(t))
    return env


@pytest.fixture()
def tree(tmp_path):
    return make_tree(tmp_path)


def run(t: Path, which: str, *args, launcher=True) -> subprocess.CompletedProcess:
    if launcher:
        cmd = ["sh", str(t / "pipeline/electricity/run_availability.sh"), which, *args]
    else:
        script = {"p1": "write_usable_flag.py", "p2": "audit_availability.py"}[which]
        cmd = [sys.executable, "-I", "-B", str(t / "pipeline/electricity" / script), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env_for(t), timeout=300)


def preserve(t: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-B", str(t / "pipeline/electricity/preserve_availability.py"), *args],
                          capture_output=True, text=True, env=env_for(t), timeout=120)


def blind_state(t: Path) -> dict:
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted((t / "data/blind").rglob("*")) if p.is_file()}


def lines(cp) -> list[str]:
    return cp.stdout.strip().splitlines()


def matches(cp, patterns) -> bool:
    got = lines(cp)
    return len(got) == len(patterns) and all(re.fullmatch(p, g) for p, g in zip(patterns, got))


def no_canary(*texts) -> bool:
    return not any(c in x for x in texts for c in syn.CANARY_STRINGS)


def stop_flag(t: Path) -> Path:
    return t / "stop_here_made_up"


def patch_stop(t: Path, rel: str, needle: str, indent: str = "    ") -> None:
    """Make a copied step stop right after `needle` whenever the flag file exists, and pin that copy ONCE, before any
    run. A test then turns the stop on and off by creating and removing the flag, with the code, the pins and the
    authorizing entry's text unchanged throughout, as they would be across a real retry (D-76, G7 and G8)."""
    patch(t, rel, needle, f'{indent}if os.path.exists({str(stop_flag(t))!r}):\n{indent}    raise RuntimeError("stopped (made up)")\n')


def reword_entry(t: Path) -> None:
    """Change the authorizing entry's words, not its pins."""
    ledger = t / "docs/DECISIONS.md"
    text = ledger.read_text()
    assert text.count("run is authorized on this made-up tree") == 1
    ledger.write_text(text.replace("run is authorized on this made-up tree", "run is authorized on this made-up tree, reworded since"))


def patch(t: Path, rel: str, needle: str, insert: str) -> None:
    """Change a copied code file, then re-pin it so the change is what is tested, not the pin."""
    p = t / rel
    src = p.read_text()
    assert src.count(needle) == 1, needle
    p.write_text(src.replace(needle, needle + insert))
    write_ledger(t)


# ---- the whole run, success ---------------------------------------------------------------------------

def test_p1_p2_and_preservation_succeed_print_only_their_lines_and_leave_blind_untouched(tree):
    before = blind_state(tree)
    a = run(tree, "p1", "--authorized-by", AUTH)
    assert a.returncode == 0 and matches(a, P1_OK), a.stdout
    assert a.stderr == ""
    assert blind_state(tree) == before
    q = pd.read_parquet(tree / "data/interim/panel_quantities.parquet")
    assert list(q.columns[-4:]) == list(av.NEW_QUANTITY_COLS)
    rec = json.loads((tree / "data/interim/availability/p1_record.json").read_text())
    assert list(rec["checks"]) == list(av.P1_CHECKS) and all(rec["checks"].values())
    assert rec["authorized_by"] == AUTH and rec["schema_version"] == av.SCHEMA_VERSIONS["p1_record"]
    assert rec["run_id"] == lines(a)[-1][-33:-1]
    data = str(tree / "data")
    touched = {e["path"].split(" -> ")[0] for e in rec["recorded_events"] if e["path"] and e["path"].startswith(data)}
    allowed = {str(tree / p) for p in ("data/raw/pudl/core_eia861__yearly_sales.parquet", "data/interim/panel_quantities.parquet",
                                       "data/interim/panel_quantities.parquet.tmp", "data/blind/panel_outcomes.parquet",
                                       "data/blind/outcomes_by_unit", "data/interim/availability/p1_record.json.tmp")}
    allowed |= {str(p) for p in (tree / "data/blind/outcomes_by_unit").iterdir()}
    assert touched <= allowed, touched - allowed
    assert all(e["allowed"] for e in rec["recorded_events"])

    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 0 and matches(b, P2_OK), b.stdout
    assert b.stderr == ""
    out = tree / "data/interim/availability"
    mask = pd.read_csv(out / "outcome_availability.csv")
    assert list(mask.columns) == list(av.MASK_COLUMNS)
    side = json.loads((out / "outcome_availability.json").read_text())
    assert side["status"] == "completed" and rec["status"] == "completed" and side["run_id"] == rec["run_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", side["attempt_id"]) and side["authorized_by"] == rec["authorized_by"] == AUTH
    assert side["mask_sha256"] == pins.guard.sha256(out / "outcome_availability.csv")
    # The identity chain the execution owner follows on the printed lines alone (D-76, G3 and G10).
    assert re.search(r"\(run ([0-9a-f]{32})\)$", lines(a)[-1]).group(1) == rec["run_id"] == re.search(r"\(run ([0-9a-f]{32})\)$", lines(b)[1]).group(1)
    assert re.search(r"\(audit attempt ([0-9a-f]{32})\)$", lines(b)[-1]).group(1) == side["attempt_id"]
    # Every field the made-up fixtures carry is one the real writers write, and the reverse (D-76, G2).
    import test_availability as TA
    assert set(rec) == set(TA.p1_record()) and set(side) == set(TA.sidecar_for(rec, b"", b""))
    assert rec["analysis_filter"] == side["analysis_filter"] == av.ANALYSIS_FILTER
    assert set(rec["inputs_sha256"]) == set(av.P1_INPUT_HASHES) and set(side["inputs_sha256"]) == set(av.P2_INPUT_HASHES)
    assert side["inputs_sha256"]["p1_record"] == side["p1_record_sha256"]
    assert side["flag_build"] == {k: rec[k] for k in av.SIDECAR_FLAG_BUILD_KEYS}
    assert re.fullmatch(r"[0-9a-f]{64}", rec["authorization_entry_sha256"]) and side["authorization_entry_sha256"] == rec["authorization_entry_sha256"]
    assert side["p1_record_sha256"] == pins.guard.sha256(out / "p1_record.json")
    assert list(side["counts_by_first_applicable_exclusion_reason"]) == list(av.ALL_CODES)
    assert "depend on" in side["counts_note"]
    p2_paths = {e["path"].split(" -> ")[0] for e in side["recorded_events"] if e["path"] and e["path"].startswith(data)}
    assert p2_paths <= {str(tree / p) for p in ("data/interim/panel_quantities.parquet", "data/interim/availability/p1_record.json",
                                                "data/interim/availability/outcome_availability.csv.tmp",
                                                "data/interim/availability/outcome_availability.json.tmp")}, p2_paths
    assert blind_state(tree) == before

    records = tree.parents[2] / "preserved"
    c = preserve(tree, "--authorized-by", AUTH, "--to", str(records))
    assert c.returncode == 0 and matches(c, PRESERVE_OK), c.stdout
    assert c.stderr == ""
    assert lines(c)[0].startswith(f"preserved run {rec['run_id']} (audit attempt {side['attempt_id']}) to ")
    dest = next(records.iterdir())
    manifest = json.loads((dest / "MANIFEST.json").read_text())
    assert manifest["schema_version"] == av.SCHEMA_VERSIONS["preserved_manifest"]
    assert manifest["authorization_entry_sha256"] == rec["authorization_entry_sha256"] and manifest["authorized_by"] == AUTH
    assert manifest["files_sha256"] == {f: pins.guard.sha256(out / f) for f in PRESERVE_FILES}
    assert sorted(p.name for p in dest.iterdir()) == sorted(["MANIFEST.json", "outcome_availability.csv", "outcome_availability.json", "p1_record.json"])
    assert oct(dest.stat().st_mode & 0o777) == "0o500"
    d = preserve(tree, "--authorized-by", AUTH, "--to", str(records))
    assert d.returncode == 2 and "never overwritten" in d.stdout and "returns to Joe" in d.stdout and len(lines(d)) == 1
    os.chmod(dest, 0o700)

    texts = [a.stdout, a.stderr, b.stdout, b.stderr, c.stdout] + [p.read_text() for p in out.iterdir()]
    assert no_canary(*texts)


# ---- the not-identical failure ------------------------------------------------------------------------

@pytest.mark.parametrize("how", ["one_value", "extra_file", "missing_file", "whole_file"])
def test_p1_writes_nothing_when_the_outcomes_on_disk_differ(tree, how):
    by_unit = tree / "data/blind/outcomes_by_unit"
    if how == "one_value":
        f = by_unit / "9_TX.parquet"
        d = pd.read_parquet(f)
        d.loc[0, "res_price"] = d.loc[0, "res_price"] + 1e-9
        d.to_parquet(f, index=False)
    elif how == "extra_file":
        shutil.copy(by_unit / "9_TX.parquet", by_unit / "999_TX.parquet")
    elif how == "missing_file":
        (by_unit / "9_TX.parquet").unlink()
    else:
        d = pd.read_parquet(tree / "data/blind/panel_outcomes.parquet")
        d.iloc[:-1].to_parquet(tree / "data/blind/panel_outcomes.parquet", index=False)
    q_before = (tree / "data/interim/panel_quantities.parquet").read_bytes()
    a = run(tree, "p1", "--authorized-by", AUTH)
    assert a.returncode == 1 and lines(a)[-1] == "wrote nothing"
    assert any(x.endswith(": no") for x in lines(a))
    assert (tree / "data/interim/panel_quantities.parquet").read_bytes() == q_before
    assert not (tree / "data/interim/availability/p1_record.json").exists()
    assert a.stderr == "" and no_canary(a.stdout)


# ---- stops: isolation, authorization, pins --------------------------------------------------------------

def test_without_the_sandbox_both_stop(tree):
    for which in ("p1", "p2"):
        r = run(tree, which, "--authorized-by", AUTH, launcher=False)
        assert r.returncode == 3 and lines(r) == [f"{which.upper()} stopped at isolation: operating-system isolation is not in "
                                                  "force (not started by run_availability.sh with the committed profile): stopped"]


def test_a_mismatched_profile_hash_stops_the_run(tree):
    env = env_for(tree)
    env["AVAILABILITY_PROFILE_SHA256"] = "0" * 64
    r = subprocess.run(["sandbox-exec", "-D", f"ROOT={tree}", "-D", f"REPO={tree.parents[1]}", "-D",
                        f"ACCESS_RECORDS={home(tree)}/.claude/projects/{SLUG}/access-records", "-f",
                        str(tree / "pipeline/electricity/sandbox/p2.sb"), sys.executable, "-I", "-B",
                        str(tree / "pipeline/electricity/audit_availability.py"), "--authorized-by", AUTH],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 3 and "isolation" in r.stdout


@pytest.mark.parametrize("args", [(), ("--authorized-by", "D-899"), ("--authorized-by", "D-901"), ("--authorized-by",)])
def test_without_an_authorizing_ledger_entry_both_stop(tree, args):
    for which in ("p1", "p2"):
        r = run(tree, which, *args)
        assert r.returncode == 4 and len(lines(r)) == 1
        assert ("not authorized" in r.stdout) or ("usage" in r.stdout)
    assert not (tree / "data/interim/availability/p1_record.json").exists()


def test_an_entry_without_a_pin_block_does_not_authorize(tree):
    write_ledger(tree, pin=False)
    for which in ("p1", "p2"):
        r = run(tree, which, "--authorized-by", AUTH)
        assert r.returncode == 4 and "carries no pin block" in r.stdout


@pytest.mark.parametrize("which, rel", [("p1", "pipeline/electricity/panel.py"), ("p1", "pipeline/electricity/sandbox/p1.sb"),
                                        ("p2", "pipeline/electricity/audit_availability.py"),
                                        ("p2", "pipeline/electricity/access_guard.py"), ("p1", "pipeline/electricity/succession.csv")])
def test_code_or_a_profile_changed_after_pinning_stops_the_run(tree, which, rel):
    comment = {".sb": "\n; changed after the pins were taken\n", ".csv": "\n"}.get(Path(rel).suffix, "\n# changed after the pins were taken\n")
    with open(tree / rel, "a") as f:
        f.write(comment)
    r = run(tree, which, "--authorized-by", AUTH)
    assert r.returncode == 4 and f"{rel} differs from the version {AUTH} pins" in r.stdout


def test_a_library_not_at_its_pinned_version_stops_the_run(tree):
    v = pins.library_versions()
    v["pandas"] = v["pandas"] + ".not-this-one"
    write_ledger(tree, versions=v)
    for which in ("p1", "p2"):
        r = run(tree, which, "--authorized-by", AUTH)
        assert r.returncode == 4 and lines(r)[-1] == f"{which.upper()} stopped at imports: not authorized: pandas is not at the pinned version"


# ---- stops: values, exceptions, stale inputs, interrupted runs -------------------------------------------

def test_a_non_finite_price_stops_p1_without_values(tmp_path):
    t = make_tree(tmp_path, raw_rows=syn.with_infinite_revenue())
    a = run(t, "p1", "--authorized-by", AUTH)
    assert a.returncode == 2 and lines(a)[-1] == "P1 stopped at build: NonFinitePrice"
    assert a.stderr == "" and "inf" not in a.stdout.lower()


def test_an_exception_carrying_values_is_reduced_to_its_class_name(tree):
    patch(tree, "pipeline/electricity/panel.py",
          "def build(sales: pd.DataFrame, succession: succ.Mapping | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:\n",
          f'    raise ValueError("price {syn.CANARY_REVENUE} and 17.315937 cents")\n')
    a = run(tree, "p1", "--authorized-by", AUTH)
    assert a.returncode == 2 and lines(a)[-1] == "P1 stopped at build: ValueError"
    assert a.stderr == "" and no_canary(a.stdout)


def test_p2_refuses_a_quantities_file_changed_since_p1(tree):
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    f = tree / "data/interim/panel_quantities.parquet"
    pd.read_parquet(f).iloc[1:].to_parquet(f, index=False)
    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 2 and "stale or changed" in b.stdout
    assert not (tree / "data/interim/availability/outcome_availability.csv").exists()


def test_p2_refuses_without_the_flag_build(tree):
    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 2 and lines(b) == ["P2 stopped at the flag build's record: FileNotFoundError"]


P1_SCRIPT, P2_SCRIPT, KEEP_SCRIPT = (f"pipeline/electricity/{n}" for n in ("write_usable_flag.py", "audit_availability.py",
                                                                           "preserve_availability.py"))
Q, RECORD = "data/interim/panel_quantities.parquet", "data/interim/availability/p1_record.json"
MASK, SIDECAR = "data/interim/availability/outcome_availability.csv", "data/interim/availability/outcome_availability.json"


def test_p1_stopped_between_its_two_writes_is_refused_by_p2_and_recovers_on_rerun(tree):
    patch_stop(tree, P1_SCRIPT, '    stage[0] = "write record"\n')
    stop_flag(tree).touch()
    a = run(tree, "p1", "--authorized-by", AUTH)
    assert a.returncode == 2 and lines(a)[-1] == "P1 stopped at write record: RuntimeError"
    assert list(pd.read_parquet(tree / Q).columns[-4:]) == list(av.NEW_QUANTITY_COLS)
    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 2 and "not marked completed" in b.stdout             # the attempt's record says in_progress
    stop_flag(tree).unlink()
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0              # compares only the existing columns
    assert run(tree, "p2", "--authorized-by", AUTH).returncode == 0


def test_p2_rerun_stopped_after_an_earlier_success_leaves_a_bundle_preservation_refuses(tree):
    """The outside read's R3 case: same P1 record, an identical mask written again, then a stop before the sidecar."""
    patch_stop(tree, P2_SCRIPT, '    stage[0] = "write sidecar"\n')
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    assert run(tree, "p2", "--authorized-by", AUTH).returncode == 0
    mask_before = (tree / MASK).read_bytes()
    stop_flag(tree).touch()
    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 2 and lines(b)[-1] == "P2 stopped at write sidecar: RuntimeError"
    assert (tree / MASK).read_bytes() == mask_before                              # identical bytes
    c = preserve(tree, "--authorized-by", AUTH, "--to", str(tree.parents[2] / "preserved"))
    assert c.returncode == 2 and "does not say the audit completed" in c.stdout
    assert not (tree.parents[2] / "preserved").exists() or not any((tree.parents[2] / "preserved").iterdir())


def test_p1_rerun_stopped_after_an_earlier_success_is_refused_by_p2_and_recovers(tree):
    """The R4 case: a second P1 writes byte-identical quantities and stops before its record."""
    patch_stop(tree, P1_SCRIPT, '    stage[0] = "write record"\n')
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    assert run(tree, "p2", "--authorized-by", AUTH).returncode == 0
    q_before = (tree / Q).read_bytes()
    stop_flag(tree).touch()
    a = run(tree, "p1", "--authorized-by", AUTH)
    assert a.returncode == 2 and lines(a)[-1] == "P1 stopped at write record: RuntimeError"
    assert (tree / Q).read_bytes() == q_before                                    # identical bytes
    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 2 and "not marked completed" in b.stdout
    stop_flag(tree).unlink()
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    assert run(tree, "p2", "--authorized-by", AUTH).returncode == 0


# ---- what the attempt markers cannot show (D-76, G3): only the current invocation's exit and success line count ----

def test_a_p1_rerun_stopped_before_its_marker_leaves_the_earlier_completed_run_which_still_passes(tree):
    """A stop before the marker is replaced leaves the earlier record, which still correctly describes the earlier
    output. The artifacts pass every check; the failed invocation shows only in its exit status and its missing
    success line. That is why a step is advanced on the current invocation's exit 0 and success line, never on the
    artifacts alone."""
    patch_stop(tree, P1_SCRIPT, '    stage[0] = "mark attempt"\n')
    first = run(tree, "p1", "--authorized-by", AUTH)
    assert first.returncode == 0
    before = {f: (tree / f).read_bytes() for f in (Q, RECORD)}
    stop_flag(tree).touch()
    a = run(tree, "p1", "--authorized-by", AUTH)
    assert a.returncode == 2 and lines(a)[-1] == "P1 stopped at mark attempt: RuntimeError"
    assert not any(x.startswith("wrote: ") for x in lines(a))
    assert {f: (tree / f).read_bytes() for f in (Q, RECORD)} == before           # the earlier run, untouched
    rec = json.loads((tree / RECORD).read_text())
    assert rec["status"] == "completed" and f"(run {rec['run_id']})" in lines(first)[-1]
    b = run(tree, "p2", "--authorized-by", AUTH)                                 # the earlier run is still a valid one
    assert b.returncode == 0 and f"(run {rec['run_id']})" in lines(b)[1]


def test_a_p2_rerun_stopped_before_its_marker_leaves_the_earlier_completed_audit_which_still_passes(tree):
    patch_stop(tree, P2_SCRIPT, '    stage[0] = "mark attempt"\n')
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    first = run(tree, "p2", "--authorized-by", AUTH)
    assert first.returncode == 0
    before = {f: (tree / f).read_bytes() for f in (MASK, SIDECAR)}
    stop_flag(tree).touch()
    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 2 and lines(b)[-1] == "P2 stopped at mark attempt: RuntimeError"
    assert {f: (tree / f).read_bytes() for f in (MASK, SIDECAR)} == before
    records = tree.parents[2] / "preserved"
    c = preserve(tree, "--authorized-by", AUTH, "--to", str(records))            # preserves the EARLIER attempt, and names it
    assert c.returncode == 0
    earlier = re.search(r"\(audit attempt ([0-9a-f]{32})\)$", lines(first)[-1]).group(1)
    assert f"(audit attempt {earlier})" in lines(c)[0]
    os.chmod(next(records.iterdir()), 0o700)


def test_a_step_that_dies_after_writing_completion_leaves_artifacts_that_pass_without_a_success_line(tree):
    """The other half of G3: completion metadata fully written, then the process stops before it reports success."""
    patch_stop(tree, P1_SCRIPT, '    })\n    write_record(record)\n')
    stop_flag(tree).touch()
    a = run(tree, "p1", "--authorized-by", AUTH)
    assert a.returncode == 2 and lines(a)[-1] == "P1 stopped at write record: RuntimeError"
    assert not any(x.startswith("wrote: ") for x in lines(a))
    assert json.loads((tree / RECORD).read_text())["status"] == "completed"       # the artifacts say completed
    stop_flag(tree).unlink()
    assert run(tree, "p2", "--authorized-by", AUTH).returncode == 0              # and nothing in them shows the stop


@pytest.mark.parametrize("stage, same", [("mark attempt", True), ("write record", False)])
def test_a_p1_retry_prints_the_stopped_attempts_input_hashes_only_if_that_attempt_had_not_replaced_the_quantities_file(tree, stage, same):
    """The execution instruction requires a P1 retry's printed input hashes to equal the stopped attempt's. P1 replaces
    the quantities file, one of its inputs, before it completes its record. So a stop before that write leaves a retry
    that matches, and a stop after it leaves one that cannot: that case is not retried and returns to Joe."""
    patch_stop(tree, P1_SCRIPT, f'    stage[0] = "{stage}"\n')
    stop_flag(tree).touch()
    stopped = run(tree, "p1", "--authorized-by", AUTH)
    assert stopped.returncode == 2 and lines(stopped)[-1] == f"P1 stopped at {stage}: RuntimeError"
    stop_flag(tree).unlink()
    retry = run(tree, "p1", "--authorized-by", AUTH)
    assert retry.returncode == 0 and lines(stopped)[1].startswith("inputs: sales ") and lines(retry)[1].startswith("inputs: sales ")
    sales_and_succession = lambda cp: lines(cp)[1].split(" | quantities ")[0]  # noqa: E731
    assert sales_and_succession(stopped) == sales_and_succession(retry)            # the other two inputs never move
    assert (lines(stopped)[1] == lines(retry)[1]) is same


# ---- the owner's procedure, rehearsed: capture as the run log's commands do, then the checker ------------------

def captured(t: Path, log: Path, step: str) -> int | None:
    """Run one step exactly as the run log's commands do: under /usr/bin/time -l -o, output and standard error to
    separate files, the exit status written by the shell. Returns the checker's own exit status."""
    log.mkdir(parents=True, exist_ok=True)
    if step == "preserve":
        cmd = f'"{os.path.realpath(sys.executable)}" -I -B pipeline/electricity/preserve_availability.py --authorized-by {AUTH} --to "{t.parents[2] / "preserved"}"'
    else:
        cmd = f"sh pipeline/electricity/run_availability.sh {step} --authorized-by {AUTH}"
    line = f'/usr/bin/time -l -o "{log}/time_{step}.txt" {cmd} > "{log}/{step}.out" 2> "{log}/{step}.err"; echo $? > "{log}/{step}.exit"'
    subprocess.run(["sh", "-c", line], cwd=t, env=env_for(t), timeout=300, check=True)
    return int((log / f"{step}.exit").read_text())


def verdict(log: Path, step: str, *args) -> tuple[int, list[str]]:
    r = subprocess.run([sys.executable, "-I", str(ROOT / "pipeline/electricity/availability_run_check.py"), step, "--log", str(log), *args],
                       capture_output=True, text=True, timeout=60)
    assert r.stderr == "", r.stderr
    return r.returncode, r.stdout.splitlines()


def test_the_owners_procedure_rehearsed_end_to_end_on_the_made_up_tree(tree):
    """The whole of the instruction's item 3 as the owner will carry it out, on made-up data: each step captured the
    way the run log's commands capture it, then judged by the checker before the next step starts."""
    log = tree.parents[2] / "log"
    assert captured(tree, log, "p1") == 0
    code, out = verdict(log, "p1")
    assert code == 0 and out[0] == "p1: ADVANCE", out
    assert captured(tree, log, "p2") == 0
    code, out = verdict(log, "p2")
    assert code == 0 and out[0] == "p2: ADVANCE", out
    assert captured(tree, log, "preserve") == 0
    code, out = verdict(log, "preserve")
    assert code == 0 and out[0] == "preserve: ADVANCE", out
    rec = json.loads((tree / RECORD).read_text())
    side = json.loads((tree / SIDECAR).read_text())
    assert f"identifiers: run {rec['run_id']}, audit attempt {side['attempt_id']}" in out
    assert all((log / f"{s}.err").read_text() == "" for s in ("p1", "p2", "preserve"))
    # Judged against the wrong step before, it does not advance: the identifiers are what tie the three together.
    other = tree.parents[2] / "other"
    other.mkdir()
    (other / "p1.out").write_text((log / "p1.out").read_text().replace(rec["run_id"], "0" * 32))
    code, out = verdict(log, "p2", "--before", str(other))
    assert code == 1 and out[0] == "p2: DO NOT ADVANCE" and any("run identifier" in x for x in out)
    os.chmod(next((tree.parents[2] / "preserved").iterdir()), 0o700)


@pytest.mark.parametrize("stage, first, then", [
    ("mark attempt", "p1: NOT DECIDED BY THE OUTPUT", "p1: ADVANCE"),
    ("write record", "p1: RETURN TO JOE", "p1: DO NOT ADVANCE"),
])
def test_a_stopped_p1_and_its_rerun_as_the_checker_sees_them(tree, stage, first, then):
    """A real P1 stopped at each of two stages. Before its marker: the output does not settle it, and a rerun (were it
    allowed) prints the same input hashes. After it replaced the quantities file: it returns to Joe, and the checker
    refuses a rerun's output because the input hashes no longer match."""
    patch_stop(tree, P1_SCRIPT, f'    stage[0] = "{stage}"\n')
    stopped, again = tree.parents[2] / "log" / "attempt1", tree.parents[2] / "log" / "attempt2"
    stop_flag(tree).touch()
    assert captured(tree, stopped, "p1") == 2
    code, out = verdict(stopped, "p1")
    assert code == 1 and out[0] == first, out
    stop_flag(tree).unlink()
    assert captured(tree, again, "p1") == 0
    code, out = verdict(again, "p1", "--stopped", str(stopped))
    assert out[0] == then, out
    code, out = verdict(again, "p1", "--retry")                                 # a retry judged without the stopped attempt's output
    assert code == 1 and out[0] == "p1: DO NOT ADVANCE"


def test_real_stops_of_p2_and_preservation_as_the_checker_sees_them(tree):
    log = tree.parents[2] / "log"
    assert captured(tree, log / "none", "p2") == 2                              # no flag build yet
    assert verdict(log / "none", "p2")[1][0] == "p2: RETURN TO JOE"
    assert captured(tree, log, "p1") == 0 and captured(tree, log, "p2") == 0
    assert captured(tree, log, "preserve") == 0
    assert captured(tree, log / "again", "preserve") == 2                       # the final folder already exists
    code, out = verdict(log / "again", "preserve", "--before", str(log))
    assert code == 1 and out[0] == "preserve: RETURN TO JOE" and any("already exists" in x for x in out)
    os.chmod(next((tree.parents[2] / "preserved").iterdir()), 0o700)


# ---- essential provenance, checked in the live audit (D-76, G2) ---------------------------------------------

@pytest.mark.parametrize("change, words", [
    (lambda r: r.pop("inputs_sha256"), "each of its four inputs"),
    (lambda r: r["inputs_sha256"].pop("outcomes"), "each of its four inputs"),
    (lambda r: r.update(analysis_filter="another filter"), "does not carry this code's analysis filter"),
    (lambda r: r["versions"].update(pandas="0.0.0"), "every library it used at its pinned version"),
    (lambda r: r.update(interpreter="/opt/made-up/bin/python3.13"), "does not record the pinned interpreter"),
    (lambda r: r.update(sandbox_profile_sha256="0" * 64), "does not record the pinned sandbox profile"),
])
def test_p2_refuses_a_flag_build_record_without_its_essential_provenance(tree, change, words):
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    rec = json.loads((tree / RECORD).read_text())
    change(rec)
    (tree / RECORD).write_text(json.dumps(rec, indent=2) + "\n")
    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 2 and len(lines(b)) == 1 and lines(b)[0].startswith("P2 stopped at the flag build's record: ") and words in b.stdout
    assert not (tree / MASK).exists() and not (tree / SIDECAR).exists()


def test_a_writer_whose_record_would_fail_the_readers_checks_stops_before_replacing_anything(tree):
    """P1 and P2 run the readers' own provenance checks on the record they are about to write. A writer changed so
    that its record would be refused (made up here, and pinned, so the change is what is tested) writes nothing."""
    q_before = (tree / Q).read_bytes()
    original = (tree / P1_SCRIPT).read_text()
    assert original.count('        "inputs_sha256": inputs,\n') == 1
    (tree / P1_SCRIPT).write_text(original.replace('        "inputs_sha256": inputs,\n', '        "inputs_sha256": {"sales": sales_sha},\n'))
    write_ledger(tree)
    a = run(tree, "p1", "--authorized-by", AUTH)
    assert a.returncode == 2 and lines(a)[-1].startswith("P1 stopped at record: the record this build would write does not pass the readers' checks (")
    assert "each of its four inputs" in lines(a)[-1]
    assert (tree / Q).read_bytes() == q_before and not (tree / RECORD).exists()
    (tree / P1_SCRIPT).write_text(original)
    p2_src = (tree / P2_SCRIPT).read_text()
    assert p2_src.count('        "analysis_filter": av.ANALYSIS_FILTER,\n') == 1
    (tree / P2_SCRIPT).write_text(p2_src.replace('        "analysis_filter": av.ANALYSIS_FILTER,\n', '        "analysis_filter": "another filter",\n'))
    write_ledger(tree)
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 2 and lines(b)[-1].startswith("P2 stopped at sidecar: the sidecar this audit would write does not pass the readers' checks (")
    assert not (tree / MASK).exists() and not (tree / SIDECAR).exists()


def test_an_authorizing_entry_reworded_between_steps_stops_the_next_step(tree):
    """D-76, G8: the execution entry's words and pins are frozen from P1's start to preservation's end. A change to
    the entry's text between steps, pins untouched, is refused by the next step."""
    original = (tree / "docs/DECISIONS.md").read_text()
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    reword_entry(tree)
    b = run(tree, "p2", "--authorized-by", AUTH)
    assert b.returncode == 2 and "P1's record was not made under this text of the authorizing entry" in b.stdout
    assert not (tree / MASK).exists()
    (tree / "docs/DECISIONS.md").write_text(original + "\n## D-903. A later entry, appended elsewhere\n\nan attempt log\n")
    assert run(tree, "p2", "--authorized-by", AUTH).returncode == 0              # appending elsewhere moves nothing
    reword_entry(tree)
    c = preserve(tree, "--authorized-by", AUTH, "--to", str(tree.parents[2] / "preserved"))
    assert c.returncode == 2 and "the sidecar was not made under this text of the authorizing entry" in c.stdout
    assert not (tree.parents[2] / "preserved").exists() or not any((tree.parents[2] / "preserved").iterdir())


# ---- a failure after preservation names the folder (D-76, G7) -----------------------------------------------

def test_preservation_stopped_after_naming_the_folder_says_so_and_is_never_retried_into_place(tree):
    patch_stop(tree, KEEP_SCRIPT, '        stage[0] = "confirm the named folder"\n', indent="        ")
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    assert run(tree, "p2", "--authorized-by", AUTH).returncode == 0
    records = tree.parents[2] / "preserved"
    stop_flag(tree).touch()
    c = preserve(tree, "--authorized-by", AUTH, "--to", str(records))
    final = next(records.iterdir())
    assert c.returncode == 5 and "nothing preserved" not in c.stdout and not final.name.endswith(".partial")
    assert lines(c) == [f"preservation stopped after the folder was named: {final} exists and holds the verified copy, but the step "
                        "stopped at confirm the named folder: RuntimeError. This is not a completed preservation. Do not rerun: "
                        "this stop returns to Joe"]
    assert c.stderr == ""
    assert sorted(p.name for p in final.iterdir()) == sorted(["MANIFEST.json", *PRESERVE_FILES]) and oct(final.stat().st_mode & 0o777) == "0o500"
    stop_flag(tree).unlink()
    d = preserve(tree, "--authorized-by", AUTH, "--to", str(records))            # no automatic recovery
    assert d.returncode == 2 and len(lines(d)) == 1 and "already exists" in d.stdout and "returns to Joe" in d.stdout
    os.chmod(final, 0o700)


def test_preservation_refuses_a_bundle_made_under_another_authorization(tree):
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    assert run(tree, "p2", "--authorized-by", AUTH).returncode == 0
    c = preserve(tree, "--authorized-by", "D-902", "--to", str(tree.parents[2] / "preserved"))
    assert c.returncode == 2 and "made under D-900, not D-902" in c.stdout


def test_p2_refuses_a_flag_build_run_under_another_authorization(tree):
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    b = run(tree, "p2", "--authorized-by", "D-902")
    assert b.returncode == 2 and "another authorization" in b.stdout


def test_the_launcher_stops_when_the_probe_is_unreadable_outside_the_sandbox(tree):
    probe = tree / "pipeline/electricity/sandbox/denied_probe.txt"
    os.chmod(probe, 0)
    try:
        for which in ("p1", "p2"):
            r = run(tree, which, "--authorized-by", AUTH)
            assert r.returncode == 3 and lines(r) == ["run_availability.sh stopped: the probe file is not readable outside the sandbox"]
    finally:
        os.chmod(probe, 0o644)


def test_the_launcher_reads_the_probe_outside_with_the_interpreter_it_then_starts():
    """D-76, G5 (the optional improvement, taken): the outside read is made by the same resolved binary that runs
    inside, so a control that treats binaries differently cannot let `cat` read what the interpreter could not."""
    sh = (ROOT / "pipeline/electricity/run_availability.sh").read_text()
    resolve, outside, start = sh.index('python=$(realpath "$(command -v python3)")'), sh.index('"$python" -I -B -c'), sh.index("exec sandbox-exec")
    assert resolve < outside < start and "cat " not in sh


def test_a_different_interpreter_from_the_pinned_one_stops_the_run(tree):
    write_ledger(tree, interp="/opt/made-up/bin/python3.13")
    for which in ("p1", "p2"):
        r = run(tree, which, "--authorized-by", AUTH)
        assert r.returncode == 4 and lines(r) == [f"{which.upper()} stopped at authorization: not authorized: this is not the pinned interpreter"]


def test_a_raw_file_seen_to_change_across_its_read_stops_p1(tree):
    patch(tree, "pipeline/electricity/write_usable_flag.py", "    sales = panel.load_sales(SALES)                    # a native read, declared in the record\n",
          '    sales_sha = "0" * 64                              # made up: the after-hash will not match\n')
    a = run(tree, "p1", "--authorized-by", AUTH)
    assert a.returncode == 2 and lines(a)[-1] == "P1 stopped at load: the raw sales file changed while it was being read: stopped"
    assert not (tree / "data/interim/availability/p1_record.json").exists()


def test_an_observation_flag_outside_true_false_or_missing_stops_p1(tmp_path):
    t = make_tree(tmp_path)
    raw = t / "data/raw/pudl/core_eia861__yearly_sales.parquet"
    d = pd.read_parquet(raw)
    d["data_observed"] = d.data_observed.map({True: "Y", False: "N"}).astype(object)
    d.to_parquet(raw, index=False)
    a = run(t, "p1", "--authorized-by", AUTH)
    assert a.returncode == 2 and lines(a)[-1] == "P1 stopped at load: an observation flag outside true, false or missing: stopped"


def test_preservation_needs_its_own_pins(tree):
    assert run(tree, "p1", "--authorized-by", AUTH).returncode == 0
    assert run(tree, "p2", "--authorized-by", AUTH).returncode == 0
    with open(tree / "pipeline/electricity/preserve_availability.py", "a") as f:
        f.write("\n# changed\n")
    c = preserve(tree, "--authorized-by", AUTH, "--to", str(tree.parents[2] / "preserved"))
    assert c.returncode == 4 and "preserve_availability.py differs" in c.stdout


# ---- native access, under the committed profiles ---------------------------------------------------------

def sandboxed(t: Path, profile: str, code: str) -> subprocess.CompletedProcess:
    return subprocess.run(["sandbox-exec", "-D", f"ROOT={t}", "-D", f"REPO={t.parents[1]}", "-D",
                           f"ACCESS_RECORDS={home(t)}/.claude/projects/{SLUG}/access-records", "-f",
                           str(t / "pipeline/electricity/sandbox" / profile), sys.executable, "-I", "-B", "-c", code],
                          capture_output=True, text=True, timeout=120, env=env_for(t))


@pytest.mark.parametrize("profile, path, ok", [
    ("p2.sb", "data/interim/panel_quantities.parquet", True),
    ("p2.sb", "data/blind/decoy_outcomes.parquet", False),
    ("p2.sb", "data/blind/panel_outcomes.parquet", False),
    ("p2.sb", "data/raw/decoy.parquet", False),
    ("p2.sb", "data/raw/pudl/core_eia861__yearly_sales.parquet", False),
    ("p2.sb", "../other/data/decoy.parquet", False),
    ("p1.sb", "data/raw/pudl/core_eia861__yearly_sales.parquet", True),
    ("p1.sb", "data/blind/panel_outcomes.parquet", True),
    ("p1.sb", "data/blind/outcomes_by_unit/9_TX.parquet", True),
    ("p1.sb", "data/blind/decoy_outcomes.parquet", False),
    ("p1.sb", "data/raw/decoy.parquet", False),
    ("p1.sb", "../other/data/decoy.parquet", False),
])
def test_native_reads_are_limited_by_the_profile(tree, profile, path, ok):
    target = os.path.normpath(str(tree / path))
    r = sandboxed(tree, profile, f"import pyarrow.parquet as pq; pq.read_table({target!r}); print('read')")
    assert (r.returncode == 0 and r.stdout.strip() == "read") is ok, r.stderr[-300:]


@pytest.mark.parametrize("profile", ["p1.sb", "p2.sb"])
def test_the_access_records_folder_is_unreadable_under_both_profiles(tree, profile):
    f = home(tree) / ".claude/projects" / SLUG / "access-records/transcript.txt"
    assert f.read_text() == "a preserved transcript"                          # readable outside the sandbox
    r = sandboxed(tree, profile, f"print(open({str(f)!r}).read())")
    assert r.returncode != 0 and "preserved" not in r.stdout


@pytest.mark.parametrize("profile, code, ok", [
    ("p1.sb", "import os; print(len(os.listdir({blind!r})))", False),
    ("p1.sb", "import os; print(len(os.listdir({by_unit!r})))", True),
    ("p2.sb", "import os; print(len(os.listdir({by_unit!r})))", False),
    ("p2.sb", "import os; print(len(os.listdir({data!r})))", False),
    ("p2.sb", "import os; print(len(os.listdir({sibling!r})))", False),
    ("p2.sb", "open({interim!r} + '/x.txt', 'w').write('x'); print('wrote')", False),
    ("p2.sb", "open({repo_file!r}, 'w').write('x'); print('wrote')", False),
    ("p1.sb", "open({blind!r} + '/x.txt', 'w').write('x'); print('wrote')", False),
    ("p2.sb", "open({probe!r}).read(); print('read')", False),
    ("p2.sb", "print(len(open({ledger!r}).read()) > 0)", True),
    ("p1.sb", "import duckdb; print(duckdb.sql(\"select count(*) from read_parquet('{sales}')\").fetchone()[0] > 0)", True),
    ("p1.sb", "import duckdb; duckdb.sql(\"select count(*) from read_parquet('{decoy}')\").fetchone()", False),
])
def test_listings_writes_and_native_libraries_are_limited_by_the_profile(tree, profile, code, ok):
    fill = {"blind": str(tree / "data/blind"), "by_unit": str(tree / "data/blind/outcomes_by_unit"), "data": str(tree / "data"),
            "interim": str(tree / "data/interim"), "repo_file": str(tree / "docs/DECISIONS.md"),
            "probe": str(tree / "pipeline/electricity/sandbox/denied_probe.txt"), "ledger": str(tree / "docs/DECISIONS.md"),
            "sibling": str(tree.parent / "other/data"),
            "sales": str(tree / "data/raw/pudl/core_eia861__yearly_sales.parquet"), "decoy": str(tree / "data/raw/decoy.parquet")}
    r = sandboxed(tree, profile, code.format(**fill))
    assert (r.returncode == 0) is ok, r.stderr[-300:]


# ---- the Python guard in a live process -----------------------------------------------------------------

def test_the_guard_refuses_in_a_live_p2_process(tree):
    records = home(tree) / ".claude/projects" / SLUG / "access-records/transcript.txt"
    code = f"""
import sys, os, subprocess
sys.path.insert(0, {str(tree)!r})
from pipeline.electricity import audit_availability as p2, access_guard as g
pol = p2.policy(); g.install(pol)
def attempt(f):
    try:
        f(); print("allowed")
    except PermissionError:
        print("refused")
attempt(lambda: open({str(tree / 'data/blind/decoy_outcomes.parquet')!r}, 'rb'))
attempt(lambda: open({str(tree / 'data/interim/decoy.txt')!r}))
attempt(lambda: os.listdir({str(tree / 'data')!r}))
attempt(lambda: os.symlink({str(tree / 'data/blind')!r}, {str(tree / 'link')!r}))
attempt(lambda: subprocess.run(['ls']))
attempt(lambda: __import__('duckdb'))
attempt(lambda: open({str(tree.parent / 'other/data/decoy.parquet')!r}, 'rb'))
attempt(lambda: open({str(records)!r}))
attempt(lambda: os.listdir({str(tree.parent / 'other/data')!r}))
attempt(lambda: open({str(tree / 'data/interim/panel_quantities.parquet')!r}, 'rb').close())
attempt(lambda: open({str(tree.parent / 'other/README.md')!r}, 'w').close())
"""
    r = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, timeout=120, env=env_for(tree))
    assert lines(r) == ["refused"] * 9 + ["allowed", "refused"], r.stdout + r.stderr[-500:]


# ---- aliases (the outside read's R6): the Python guard normalizes spelling only; the operating system resolves ----

@pytest.mark.parametrize("profile", ["p1.sb", "p2.sb"])
def test_a_symlink_outside_data_to_a_blinded_decoy_is_refused_by_the_sandbox(tree, profile):
    alias = tree.parents[1] / "alias_to_decoy.parquet"
    alias.symlink_to(tree / "data/blind/decoy_outcomes.parquet")
    folder_alias = tree.parents[1] / "alias_to_blind"
    folder_alias.symlink_to(tree / "data/blind", target_is_directory=True)
    for target in (alias, folder_alias / "decoy_outcomes.parquet"):
        r = sandboxed(tree, profile, f"import pyarrow.parquet as pq; pq.read_table({str(target)!r}); print('read')")
        assert r.returncode != 0 and "read" not in r.stdout, (target, r.stdout)
        r = sandboxed(tree, profile, f"open({str(target)!r}, 'rb').read(); print('read')")
        assert r.returncode != 0 and "read" not in r.stdout, (target, r.stdout)
