"""pass_c_precision_apply: invented records only, then the file on disk against the script."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pass_c_precision_apply", ROOT / "pipeline" / "facilities" / "pass_c_precision_apply.py")
m = importlib.util.module_from_spec(spec)
sys.modules["pass_c_precision_apply"] = m
spec.loader.exec_module(m)


def row(site, says, kind="M", on_file="meets all six conditions: medium", needs=""):
    return dict(site=site, kind=kind, class_on_file=on_file, what_the_rule_says=says, needs_a_reading=needs)


RES = {"sites": {"x:1": {"resolution": "resolved", "conflicting_name": "SOMEONE", "resolved_by": "a certificate", "the_sessions_reading": True},
                 "x:2": {"resolution": "unresolved", "conflicting_name": "SOMEONE", "resolved_by": "", "the_sessions_reading": True},
                 "x:3": {"resolution": "stands", "conflicting_name": "SOMEONE", "resolved_by": "a ruling", "the_sessions_reading": False}},
       "omaha": {"sites": ["o:1"]}}


def test_a_record_the_rule_lets_stand_keeps_its_class_with_the_limitation():
    r = m.classify(row("a:1", m.STANDS), RES)
    assert r["class_under_the_precision_rule"] == "meets all six conditions: medium"
    assert r["stated_limitation"] == m.UNKNOWN_ACCURACY and r["rests_on_a_reading_of_the_sessions"] == "no"


def test_a_lead_and_a_statement_are_unchanged():
    assert m.classify(row("a:2", m.LEAD, kind="N", on_file="lead"), RES)["class_under_the_precision_rule"] == "lead"
    s = m.classify(row("a:3", m.STATEMENT, kind="S", on_file="supports a statement on file; not itself sufficient"), RES)
    assert s["class_under_the_precision_rule"].startswith("supports a statement") and s["stated_limitation"] == ""


def test_a_resolved_conflict_keeps_the_class_and_says_whose_reading_it_is():
    r = m.classify(row("x:1", "reliance defeated under reading 3", needs="whether a record on file resolves the conflict"), RES)
    assert r["class_under_the_precision_rule"] == "meets all six conditions: medium"
    assert r["rests_on_a_reading_of_the_sessions"] == "yes" and "a certificate" in r["basis"]


def test_an_unresolved_conflict_defeats_reliance():
    r = m.classify(row("x:2", "reliance defeated under reading 3", needs="whether a record on file resolves the conflict"), RES)
    assert r["class_under_the_precision_rule"].startswith("reliance defeated") and "unresolved" in r["class_under_the_precision_rule"]


def test_a_ruling_is_not_marked_as_the_sessions_reading():
    assert m.classify(row("x:3", "reliance defeated under reading 3", needs="x"), RES)["rests_on_a_reading_of_the_sessions"] == "no"


def test_the_omaha_application_needs_the_table_to_say_reliance_stands():
    assert "two measured layers" in m.classify(row("o:1", m.STANDS, needs="whether the record relies on the map that has no distance"), RES)["basis"]
    with pytest.raises(ValueError):
        m.classify(row("o:1", m.LEAD), RES)


def test_a_record_needing_a_reading_with_no_resolution_is_refused():
    with pytest.raises(ValueError):
        m.classify(row("z:9", m.STANDS, needs="something"), RES)
    with pytest.raises(ValueError):
        m.classify(row("z:8", "something new"), RES)


def test_a_resolution_for_a_site_not_in_the_table_is_refused():
    with pytest.raises(ValueError):
        m.build([row("a:1", m.STANDS)], RES)


def test_the_file_on_disk_is_what_the_script_writes():
    assert m.main(["--check"]) == 0
