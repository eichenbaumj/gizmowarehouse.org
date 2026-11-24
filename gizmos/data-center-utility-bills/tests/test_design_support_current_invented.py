"""The current design summary (pipeline/analysis/design_support_current.py) and the prefreeze reader's use of it, on
invented inputs only. No file under data/ is read or written: every write goes to pytest's tmp_path.

Joe, 2026-11-19: "Keep the historical step E files untouched at their existing paths. Write current design summaries
under distinct names and have the prefreeze summary reader explicitly use those current files. Verify the writer's suffix
behavior before relying on it."
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, ownership, usable_flag  # noqa: E402
from pipeline.analysis import design_support_current as dsc  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import prefreeze_summaries as pf  # noqa: E402
from test_matching_rules import COOP, FUEL, IOU, YEARS, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
STATES = ["AA", "AB", "BB", "BC"]
NONE = ps.UnknownLoad.none("invented data: no load-unknown site")


def invented():
    """test_entry_points.invented's world: three hosts, an IOU host with no ownership row, one host without a full window."""
    hosts = [(1, "AA", 10_000, IOU), (2, "BB", 12_000, COOP), (3, "AB", 11_000, COOP)]
    comps = [(10 + i, STATES[i % 4], 9_000 + 150 * i, IOU if i % 5 == 0 else COOP) for i in range(28)] + [(1, "BC", 10_100, IOU)]
    treated, clean, q, regions, dd = world(hosts, comps)
    q["utility_name"] = [f"Utility {u}" for u in q.utility_id_eia]
    usable = {(u, st, y) for u, st, *_ in hosts + comps for y in YEARS} - {(3, "AB", 2012)}
    reasons = {(u, st, y): ("none" if (u, st, y) in usable else "under_customer_floor") for u, st, *_ in hosts + comps for y in YEARS}
    flags = usable_flag.Flags(usable=usable, reason=reasons, rows=len(reasons), source="invented")
    dose = q[ps.KEY + ["year"]].assign(dose=0.0, crypto_mw=0.0, base_retail_gwh=1000.0)
    return treated, clean, q, regions, dd, flags, dose


@pytest.fixture
def patched(monkeypatch, tmp_path):
    treated, clean, q, regions, dd, flags, dose = invented()
    header = tmp_path / "ownership.csv"
    header.write_text(",".join(ownership.COLUMNS) + "\n")
    monkeypatch.setattr(design, "load", lambda: (q, dose, regions, FUEL, dd))
    monkeypatch.setattr(design, "split", lambda theta, which, q_, dose_, frozen=None: (treated, clean))
    monkeypatch.setattr(design, "SETS", (ps.HEADLINE_SET,))
    monkeypatch.setattr(usable_flag, "read", lambda path=None: flags)
    real_load = ownership.load
    monkeypatch.setattr(ownership, "load", lambda path=None: real_load(header))
    monkeypatch.setattr(ps, "load_gas_share", lambda frozen=None: GAS)
    monkeypatch.setattr(ps, "load_unknown_load", lambda *a, **k: NONE)
    for mod in (design, ps, dsc):
        monkeypatch.setattr(mod, "FROZEN", tmp_path)
    return tmp_path


HISTORICAL = {"design_support.json": b'{"sets": {}, "historical": "step E"}\n', "design_support.csv": b"a,b\n1,2\n",
              "full_window_eligibility.csv": b"x\n1\n"}


def put_historical(folder: Path) -> dict:
    for name, body in HISTORICAL.items():
        (folder / name).write_bytes(body)
    return {name: hashlib.sha256(body).hexdigest() for name, body in HISTORICAL.items()}


# ---- the suffix finding, as a fact about design.main's source --------------------------------------------------------

def test_design_main_names_its_files_from_the_rules_alone_so_headline_rules_write_the_historical_paths():
    """The finding behind the driver: design.main's suffix is empty under the headline rules and otherwise the variant's
    label, and its folder is design.FROZEN. Read from the source; design.main is not run."""
    src = (ROOT / "pipeline" / "analysis" / "design.py").read_text()
    tree = ast.parse(src)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    body = ast.unparse(main)
    assert "suffix = '' if rules == ps.HEADLINE_RULES else f'_{rules.label}'" in body
    for name in ("design_support{suffix}.csv", "full_window_eligibility{suffix}.csv", "design_support{suffix}.json"):
        assert f"FROZEN / f'{name}'" in body, name
    assert "rules = ps.rules_from_argv(sys.argv)" in body


# ---- the driver writes the current names and nothing else ----------------------------------------------------------

def test_the_driver_writes_only_the_current_names_and_leaves_the_historical_files_untouched(patched):
    tmp = patched
    before = put_historical(tmp)
    report, tables, rows = dsc.build_report(tmp)
    written = dsc.write(report, tables, tmp)
    assert set(written) == {dsc.CURRENT_JSON_NAME, dsc.CURRENT_CSV_NAME}
    for name, h in before.items():
        assert hashlib.sha256((tmp / name).read_bytes()).hexdigest() == h, name
    assert sorted(p.name for p in tmp.iterdir()) == sorted([*HISTORICAL, "ownership.csv", dsc.CURRENT_JSON_NAME, dsc.CURRENT_CSV_NAME])
    doc = json.loads((tmp / dsc.CURRENT_JSON_NAME).read_text())
    assert doc["what_this_is"] == dsc.WHAT_THIS_IS and doc["written_by"] == dsc.THIS_FILE
    s = doc["sets"][ps.HEADLINE_SET]
    assert {"utility": "3:AB", "cohort": 2015, "why": design.NOT_USABLE} in s["hosts_dropped"]
    assert len(s["fingerprint"]["sha256"]) == 64 and s["support_rule_by_host"]
    assert doc["full_window_eligibility_rows"]["rows_equal_the_historical_file_byte_for_byte"] is False   # invented bytes
    assert doc["against_the_historical_record"][ps.HEADLINE_SET]["equal"] is False                         # no set in the invented record
    csv = pd.read_csv(tmp / dsc.CURRENT_CSV_NAME)
    assert set(csv.set) == {ps.HEADLINE_SET} and len(csv) == ps.T * len(s["hosts"])


def test_the_what_this_is_says_current_not_validation_historical_untouched_and_provisional():
    w = dsc.WHAT_THIS_IS
    for phrase in ("current design summary", "after the ownership repair of 2026-11-19", "not a validation record",
                   "data/frozen/design_support.json, left untouched", "PROVISIONAL", "DRAFT, not frozen"):
        assert phrase in w, phrase
    assert "—" not in w


def test_the_driver_refuses_to_write_a_historical_name(monkeypatch, tmp_path):
    monkeypatch.setattr(dsc, "CURRENT_JSON_NAME", "design_support.json")
    with pytest.raises(RuntimeError, match="must differ"):
        dsc.write({"sets": {}}, [pd.DataFrame({"a": [1]})], tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_the_eligibility_rows_are_compared_with_the_historical_file_byte_for_byte(tmp_path):
    rows = pd.DataFrame([(1, "AA", 2015, 1, 2012, "x")], columns=design.GAP_COLUMNS)
    (tmp_path / dsc.HISTORICAL_ELIGIBILITY_NAME).write_bytes(rows.to_csv(index=False).encode())
    r = dsc.eligibility_rows_against_the_historical_file(rows, tmp_path)
    assert r["rows_equal_the_historical_file_byte_for_byte"] and r["sha256_of_the_rows_this_run_computes"] == r["sha256_of_the_historical_file"]
    r = dsc.eligibility_rows_against_the_historical_file(rows.assign(missing_years=2), tmp_path)
    assert not r["rows_equal_the_historical_file_byte_for_byte"] and "not on file" in r["reading"]


def test_the_driver_calls_design_functions_and_never_design_main():
    tree = ast.parse((ROOT / "pipeline" / "analysis" / "design_support_current.py").read_text())
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "design"}
    assert "main" not in used
    assert {"build_with_rules", "support", "investor_owned_without_rows", "eligibility_summary", "window_gaps", "run_fingerprint"} <= used
    src = (ROOT / "pipeline" / "analysis" / "design_support_current.py").read_text()
    for bad in ("load_outcomes", "read_listed_outcomes", "data/blind", "DECISIONS.md"):
        assert bad not in src, bad


# ---- the prefreeze reader reads the current summary by name ---------------------------------------------------------

def test_the_prefreeze_reader_names_the_current_summary_and_says_which_file_it_read(tmp_path, monkeypatch):
    assert pf.DESIGN_SUMMARY_NAME == "design_support_current.json" and pf.DESIGN_SUMMARY.name == pf.DESIGN_SUMMARY_NAME
    body = b'{"what_this_is": "a current design summary", "written_by": "x.py", "sets": {}}\n'
    (tmp_path / pf.DESIGN_SUMMARY_NAME).write_bytes(body)
    (tmp_path / "design_support.json").write_bytes(b'{"what_this_is": "historical", "sets": {}}\n')
    monkeypatch.setattr(pf, "DESIGN_SUMMARY", tmp_path / pf.DESIGN_SUMMARY_NAME)
    doc, rec = pf.read_design_summary()
    check_record(doc, rec, body)


def check_record(doc, rec, body):
    assert rec["file"] == "data/frozen/design_support_current.json"
    assert rec["sha256"] == hashlib.sha256(body).hexdigest()
    assert rec["what_this_is"] == "a current design summary" == doc["what_this_is"]


def test_the_record_check_fails_if_the_reader_falls_back_to_the_historical_record(tmp_path, monkeypatch):
    """A deliberate break in the test process: DESIGN_SUMMARY pointed back at design_support.json. check_record fails."""
    body = b'{"what_this_is": "a current design summary", "written_by": "x.py", "sets": {}}\n'
    (tmp_path / pf.DESIGN_SUMMARY_NAME).write_bytes(body)
    (tmp_path / "design_support.json").write_bytes(b'{"what_this_is": "historical", "sets": {}}\n')
    monkeypatch.setattr(pf, "DESIGN_SUMMARY", tmp_path / "design_support.json")
    doc, rec = pf.read_design_summary()
    with pytest.raises(AssertionError):
        check_record(doc, rec, body)


def test_the_usable_flag_block_names_the_summary_it_came_from():
    doc = {"sets": {"s": {"hosts_in_the_set": 2, "full_window_eligibility": {
        "hosts": {"hosts_without_a_full_window": [{"utility": "3:AB", "name": "Three", "cohort": 2015}]},
        "comparisons": {"candidates": 5, "by_cohort": {"2015": {"without_a_full_window": 1, "with_a_full_window": 4}}}}}}}
    r = pf.usable_flag_removals(doc)
    assert r["s"]["source"] == "data/frozen/design_support_current.json, sets.s.full_window_eligibility"
    assert r["s"]["hosts_removed_by_the_flag"] == 1


def test_no_design_check_in_the_prefreeze_main_reads_the_historical_record_by_path():
    """The main reads the design summary only through read_design_summary (DESIGN_SUMMARY); the historical name occurs in
    prose and in the record's explanation, never as a path joined to FROZEN."""
    src = (ROOT / "pipeline" / "analysis" / "prefreeze_summaries.py").read_text()
    tree = ast.parse(src)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    body = ast.unparse(main)
    assert "read_design_summary()" in body
    assert "FROZEN / 'design_support.json'" not in body and 'FROZEN / "design_support.json"' not in body
