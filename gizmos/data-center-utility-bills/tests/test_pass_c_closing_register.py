"""Tests for pipeline/facilities/pass_c_closing_register.py, on invented inputs only.

Every input here is made up inside this file or under tmp_path. Nothing is read
from data/, from the real table of questions, or from the attribution driver.
"""
import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from collections import Counter

SCRIPT = Path(__file__).resolve().parents[1] / "pipeline" / "facilities" / "pass_c_closing_register.py"
_spec = importlib.util.spec_from_file_location("pass_c_closing_register", SCRIPT)
reg = importlib.util.module_from_spec(_spec)
sys.modules["pass_c_closing_register"] = reg
_spec.loader.exec_module(reg)


# ----------------------------------------------------------------------------
# Invented inputs
# ----------------------------------------------------------------------------

def _util(method="exact", place="comparison", defined=True, why=None, rel=(), kept=()):
    return {
        "method": method,
        "why_conservative": why,
        "configurations": 1,
        "complete": method == "exact",
        "reference": {"defined": defined, "place": place if defined else None,
                      "crossing": "never", "why_undefined": None if defined else "invented",
                      "undefined_by": [], "settings_enumerated": 1, "searched": True, "pair": None},
        "relevant_questions": [{"fid": f, "question": q, "settings": 2, "merged_settings": []} for f, q in rel],
        "kept_questions": [
            ({"fid": f, "question": q, "witness": {}} if method == "exact"
             else {"fid": f, "question": q, "channel": "own load"})
            for f, q in kept
        ],
        "joins": [],
        "factor_matters": False,
    }


CEILING = "999 configurations, over the ceiling of 100000"


def invented_attribution():
    """Two states: AA (one of the invented 'D-68' states) and BB (first run)."""
    return {
        "hosts": [{"utility": "1:AA", "name": "Host One"}],
        "counts": {},
        "expansion": {},
        "exact": {
            "AA": {
                "questions": [
                    {"fid": "s1", "question": "assignment", "settings": 3},
                    {"fid": "s2", "question": "date", "settings": 3},
                    {"fid": "s3", "question": "assignment", "settings": 3},
                    {"fid": "s4", "question": "capacity", "settings": 2},
                    {"fid": "s5", "question": "assignment", "settings": 3},
                    {"fid": "s6", "question": "assignment", "settings": 3},
                ],
                "utilities": {
                    # the host keeps s1
                    "1:AA": _util(place="cohort", rel=[("s1", "assignment")], kept=[("s1", "assignment")]),
                    # a comparison utility keeps s2, and s1 is relevant to it but not kept
                    "2:AA": _util(place="comparison", rel=[("s1", "assignment"), ("s2", "date"),
                                                           ("s6", "assignment")],
                                  kept=[("s2", "date")]),
                    # an over-the-ceiling conservative utility, early on the reference, keeps s3
                    "3:AA": _util(method="conservative", why=CEILING, place="early",
                                  rel=[("s3", "assignment")], kept=[("s3", "assignment")]),
                    # an exact utility whose reference is undefined keeps s5
                    "4:AA": _util(defined=False, rel=[("s5", "assignment")], kept=[("s5", "assignment")]),
                    # s4 is relevant to no one
                },
            },
            "BB": {
                "questions": [{"fid": "s9", "question": "assignment", "settings": 2}],
                "utilities": {
                    "9:BB": _util(place="comparison", rel=[("s9", "assignment")], kept=[("s9", "assignment")]),
                },
            },
        },
    }


ATTR_CSV_ROWS = [
    {"utility": "1:AA", "utility_name": "Host One", "one_of_the_26_hosts": "True", "method": "exact",
     "reference_place": "cohort", "site": "s1", "question": "assignment", "site_state": "AA",
     "site_is_on": "1:AA", "operator": "Opco", "county": "Alpha", "mw_full": "12.5",
     "already_on_the_target_list": "True"},
    {"utility": "2:AA", "utility_name": "Compare Two", "one_of_the_26_hosts": "False", "method": "exact",
     "reference_place": "comparison", "site": "s2", "question": "date", "site_state": "AA",
     "site_is_on": "2:AA", "operator": "Datco", "county": "Beta", "mw_full": "",
     "already_on_the_target_list": "False"},
    {"utility": "3:AA", "utility_name": "Ceiling Three", "one_of_the_26_hosts": "False", "method": "conservative",
     "reference_place": "early", "site": "s3", "question": "assignment", "site_state": "AA",
     "site_is_on": "3:AA", "operator": "Thirdco", "county": "Gamma", "mw_full": "40",
     "already_on_the_target_list": "False"},
    {"utility": "4:AA", "utility_name": "Undefined Four", "one_of_the_26_hosts": "False", "method": "exact",
     "reference_place": "", "site": "s5", "question": "assignment", "site_state": "AA",
     "site_is_on": "4:AA", "operator": "Fifthco", "county": "Delta", "mw_full": "8",
     "already_on_the_target_list": "False"},
    {"utility": "9:BB", "utility_name": "Nine", "one_of_the_26_hosts": "False", "method": "exact",
     "reference_place": "comparison", "site": "s9", "question": "assignment", "site_state": "BB",
     "site_is_on": "9:BB", "operator": "Ninco", "county": "Omega", "mw_full": "30",
     "already_on_the_target_list": "False"},
]

TABLE_COLUMNS = ["site", "site_label", "state", "on_the_list_for", "question", "status", "evidence_on_file",
                 "what_it_covers_and_when", "still_open", "decisive_in_the_expansion_test_for",
                 "avenues_tried_in_the_log", "leads_that_remain", "closes_as"]


def _t(site, label, state, host, question, status, evidence="ev", still_open="", avenues="map 2", leads=""):
    return {"site": site, "site_label": label, "state": state, "on_the_list_for": host, "question": question,
            "status": status, "evidence_on_file": evidence, "what_it_covers_and_when": "",
            "still_open": still_open, "decisive_in_the_expansion_test_for": "",
            "avenues_tried_in_the_log": avenues, "leads_that_remain": leads, "closes_as": ""}


TABLE_ROWS = [
    # s1 is on the fixed list and open in the check (assignment)
    _t("s1", "Opco, Alpha County, AA", "AA", "Host One", "assignment", "unresolved"),
    _t("s1", "Opco, Alpha County, AA", "AA", "Host One", "operating date", "unresolved",
       leads="The utility's rate case docket"),
    _t("s1", "Opco, Alpha County, AA", "AA", "Host One", "capacity coverage", "not examined"),
    # t7 is on the fixed list, its state is in the check, none of its questions is open
    _t("t7", "Sevenco, Beta County, AA", "AA", "Host One", "assignment", "resolved"),
    _t("t7", "Sevenco, Beta County, AA", "AA", "Host One", "operating date", "unresolved"),
    _t("t7", "Sevenco, Beta County, AA", "AA", "Host One", "capacity coverage", "resolved for part"),
    # tx1 is on the fixed list, Texas is not in the invented check
    _t("tx1", "Texco, Harris County, TX", "TX", "City of Houstonia - (TX)", "assignment", "unresolved",
       leads="The recorded plat's electric easement."),
    _t("tx1", "Texco, Harris County, TX", "TX", "City of Houstonia - (TX)", "operating date", "resolved"),
    _t("tx1", "Texco, Harris County, TX", "TX", "City of Houstonia - (TX)", "capacity coverage", "not examined"),
]

CORRECTIONS = [
    {"fid": "s1", "kind": "assign", "to": [1, "AA"], "why": "verified onto the host by an invented record"},
    {"fid": "t7", "kind": "reopen", "candidates": [1, 2], "why": "an invented reopening"},
    {"fid": "s3", "kind": "date", "earliest": 2010, "latest": 2015, "convention": 2015,
     "never_is_possible": False, "ends": "evidence", "why": "an invented date record"},
    {"fid": "s5", "kind": "candidates", "candidates": [4, 5], "why": "an invented widening"},
]

LOG_COLUMNS = ["date", "target", "round", "who", "avenue", "query_or_url", "result", "note"]
LOG_ROWS = [
    {"date": "2026-01-01", "target": "s3", "round": "1", "who": "x", "avenue": "map", "query_or_url": "q",
     "result": "r", "note": ""},
    {"date": "2026-01-01", "target": "s3", "round": "1", "who": "x", "avenue": "map", "query_or_url": "q",
     "result": "r", "note": ""},
    {"date": "2026-01-01", "target": "s3", "round": "1", "who": "x", "avenue": "government",
     "query_or_url": "q", "result": "r", "note": ""},
]

BROWSER_MD = """# Invented browser list

## 4. Something else

| Site (what it decides) | Page |
|---|---|
| Ninco, Omega (Nine) | `https://example.invalid/` |

## 5. After session 10: what still needs a person

| Site (what it decides) | Page | What to do | What I need from it |
|---|---|---|---|
| Texco, 1 Main St, Houstonia (Houstonia) | `https://example.invalid/a` | Open it. | The address. |
| An unnamed building, 2 Side St (Somewhere) | `https://example.invalid/b` | Open it. | The line. |
| Row for bi:77-0 by id | `https://example.invalid/c` | Open it. | Anything. |

## 6. After that

| Opco, Alpha (Host) | not in section 5 |
"""


def _write_csv(path, columns, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow(r)


@pytest.fixture
def files(tmp_path):
    p = {
        "attribution": tmp_path / "attr.json",
        "attribution_csv": tmp_path / "attr.csv",
        "table": tmp_path / "questions.csv",
        "log": tmp_path / "log.csv",
        "corrections": tmp_path / "corr.json",
        "browser": tmp_path / "browser.md",
        "named": tmp_path / "named_avenues_absent.csv",  # absent unless a test writes it
    }
    p["attribution"].write_text(json.dumps(invented_attribution()))
    _write_csv(p["attribution_csv"], list(ATTR_CSV_ROWS[0].keys()), ATTR_CSV_ROWS)
    _write_csv(p["table"], TABLE_COLUMNS, TABLE_ROWS)
    _write_csv(p["log"], LOG_COLUMNS, LOG_ROWS)
    p["corrections"].write_text(json.dumps(CORRECTIONS))
    p["browser"].write_text(BROWSER_MD)
    return p


def _argv(files, out, *extra):
    return ["--attribution", str(files["attribution"]), "--attribution-csv", str(files["attribution_csv"]),
            "--questions", str(files["table"]), "--log", str(files["log"]),
            "--corrections", str(files["corrections"]), "--browser-list", str(files["browser"]),
            "--named-avenues", str(files["named"]),
            "--states-of-d68", "AA", "--out", str(out), *extra]


def _build(files, texas="pending"):
    inputs = reg.load_inputs(
        attribution=files["attribution"], attribution_csv=files["attribution_csv"], questions=files["table"],
        log=files["log"], corrections=files["corrections"], browser_list=files["browser"],
        states_of_d68="AA", texas_request=texas, named_avenues=files["named"])
    return reg.build_register(inputs)


def _row(result, site, question):
    hits = [r for r in result.rows if r["site"] == site and r["question"] == question]
    assert len(hits) == 1, (site, question, hits)
    return hits[0]


# ----------------------------------------------------------------------------
# Name mapping
# ----------------------------------------------------------------------------

def test_name_mapping():
    assert reg.table_question("assignment") == "assignment"
    assert reg.table_question("date") == "operating date"
    assert reg.table_question("capacity") == "capacity coverage"
    with pytest.raises(ValueError):
        reg.table_question("operating date")


def test_name_mapping_end_to_end(files):
    res = _build(files)
    assert _row(res, "s2", "operating date")["open_in_the_check"] == "yes"
    assert _row(res, "s4", "capacity coverage")["open_in_the_check"] == "yes"
    assert not [r for r in res.rows if r["question"] in ("date", "capacity")]


# ----------------------------------------------------------------------------
# Union of rows
# ----------------------------------------------------------------------------

def test_union_of_rows_without_duplicates(files):
    res = _build(files)
    keys = [(r["site"], r["question"]) for r in res.rows]
    assert len(keys) == len(set(keys))
    expected = {(t["site"], t["question"]) for t in TABLE_ROWS} | {
        ("s2", "operating date"), ("s3", "assignment"), ("s4", "capacity coverage"),
        ("s5", "assignment"), ("s6", "assignment"), ("s9", "assignment")}
    assert set(keys) == expected
    # s1 assignment is in both sources and appears once
    assert keys.count(("s1", "assignment")) == 1


def test_rows_sorted_and_columns_in_order(files):
    res = _build(files)
    assert [k for k in res.rows[0] if not k.startswith("_")] == reg.COLUMNS
    header = reg.render_csv(res.rows).splitlines()[0]
    assert header == ",".join(reg.COLUMNS)
    order = [(r["state"], r["site"], r["question"]) for r in res.rows]
    assert order == sorted(order)


# ----------------------------------------------------------------------------
# Coverage labels
# ----------------------------------------------------------------------------

def test_coverage_label_rule():
    d68 = {"AA"}
    check_states = {"AA", "BB"}
    assert reg.coverage_label("AA", True, d68, check_states) == "seventeen states of D-68"
    assert reg.coverage_label("BB", True, d68, check_states) == \
        "first run 2026-11-18, for descriptive counts only"
    assert reg.coverage_label("AA", False, d68, check_states) == "not an open question in the check"
    assert reg.coverage_label("TX", False, d68, check_states) == "not in any state's check"


def test_coverage_labels_end_to_end(files):
    res = _build(files)
    assert _row(res, "s1", "assignment")["coverage"] == "seventeen states of D-68"
    assert _row(res, "s9", "assignment")["coverage"] == "first run 2026-11-18, for descriptive counts only"
    assert _row(res, "t7", "assignment")["coverage"] == "not an open question in the check"
    assert _row(res, "tx1", "assignment")["coverage"] == "not in any state's check"


# ----------------------------------------------------------------------------
# Status, with overrides both ways
# ----------------------------------------------------------------------------

def test_status_reopen_overrides_resolved_table_status():
    status, why = reg.status_for("assignment", {"status": "resolved"}, {"reopen"}, open_in_check=False)
    assert status == "unresolved"
    assert why


def test_status_assign_overrides_unresolved_table_status():
    status, why = reg.status_for("assignment", {"status": "unresolved"}, {"assign"}, open_in_check=True)
    assert status == "resolved (entered in the corrections in force)"
    assert why


def test_status_assign_leaves_other_table_statuses_and_questions_alone():
    assert reg.status_for("assignment", {"status": "not examined"}, {"assign"}, True) == ("not examined", None)
    assert reg.status_for("operating date", {"status": "unresolved"}, {"assign", "reopen"}, True) == \
        ("unresolved", None)


def test_status_not_in_table():
    assert reg.status_for("assignment", None, set(), open_in_check=True) == ("unresolved", None)
    with pytest.raises(ValueError):
        reg.status_for("assignment", None, set(), open_in_check=False)


def test_status_overrides_listed_end_to_end(files):
    res = _build(files)
    assert _row(res, "s1", "assignment")["status"] == "resolved (entered in the corrections in force)"
    assert _row(res, "t7", "assignment")["status"] == "unresolved"
    sites = sorted(o["site"] for o in res.overrides)
    assert sites == ["s1", "t7"]


# ----------------------------------------------------------------------------
# closes_as, one test per rule
# ----------------------------------------------------------------------------

def _ctx(**kw):
    base = dict(status="unresolved", state="AA", question="assignment", on_the_fixed_list="yes",
                open_in_the_check="yes", coverage="seventeen states of D-68", avenues_tried="map 2",
                leads_that_remain="", still_open="", site="x1")
    base.update(kw)
    return base


def test_closes_as_resolved_forms():
    for s in ("resolved", "resolved (entered in the corrections in force)"):
        assert reg.closes_as(_ctx(status=s), set(), "pending")[0] == "resolved"


def test_closes_as_resolved_for_part_both_forms():
    text, keys = reg.closes_as(_ctx(status="resolved for part", leads_that_remain="A certificate."), set(),
                               "pending")
    assert text == ("resolved for part; for the rest, closed with these avenues unpursued: "
                    "the lead on file: A certificate.")
    assert keys == [reg.AV_LEAD_KEY]
    text, keys = reg.closes_as(_ctx(status="resolved for part"), set(), "pending")
    assert text == "resolved for part; for the rest, every avenue of rule 3.3 tried and no lead remaining"
    assert keys == [reg.AV_ALL_TRIED]


def test_closes_as_not_examined_both_ways():
    assert reg.closes_as(_ctx(status="not examined"), set(), "pending")[0] == \
        "not examined: no avenue was run on this question"
    assert reg.closes_as(_ctx(status="not examined", open_in_the_check="no"), set(), "pending")[0] == \
        "not examined: no avenue was run on this question and it is not an open question in the check"


def test_rule_1_never_run():
    assert reg.avenue_never_run(_ctx(on_the_fixed_list="no", avenues_tried="none")) == \
        "rule 3.3's lookups, never run on this site"
    assert reg.avenue_never_run(_ctx(on_the_fixed_list="no", avenues_tried="map 2")) == \
        "rule 3.3's rounds, not run in full on this site (attempts on file are in avenues_tried)"
    assert reg.avenue_never_run(_ctx()) is None


def test_rule_2_texas_request():
    assert reg.avenue_texas_request(_ctx(state="TX"), "pending") == \
        "the request to the Texas commission for the official certificated-area maps (pending)"
    assert reg.avenue_texas_request(_ctx(state="TX"), "declined") == \
        "the request to the Texas commission for the official certificated-area maps (declined)"
    assert reg.avenue_texas_request(_ctx(state="TX", question="operating date"), "pending") is None
    assert reg.avenue_texas_request(_ctx(state="AA"), "pending") is None
    with pytest.raises(ValueError):
        reg.avenue_texas_request(_ctx(state="TX"), "  ")


def test_rule_2_texas_status_is_free_text_passed_verbatim(files):
    status = "sent by the owner on 2026-11-18 by his own report; reply pending"
    assert reg.avenue_texas_request(_ctx(state="TX"), status) == \
        "the request to the Texas commission for the official certificated-area maps (" + status + ")"
    res = _build(files, texas=status)
    assert ("the request to the Texas commission for the official certificated-area maps (" + status + ")"
            in _row(res, "tx1", "assignment")["closes_as"])
    assert "(" + status + ")" in reg.render_summary(res)


def test_rule_3_browser_row():
    assert reg.avenue_browser(_ctx(site="x1"), {"x1"}) == "the browser sitting's page for this site"
    assert reg.avenue_browser(_ctx(site="x1"), {"x2"}) is None


def test_rule_4_load_only_route():
    for text in ("a docket", "the Rate Case", "a tariff sheet", "the resource plan", "the IRP",
                 "later filings", "testimony", "PUCO", "a commission case"):
        assert reg.avenue_load_only(_ctx(leads_that_remain=text)) == "a load-only route for mixed filings", text
    assert reg.avenue_load_only(_ctx(still_open="the 2024 testimony")) == "a load-only route for mixed filings"
    # whole words only: an airport is not an IRP, a profiling is not a filing
    assert reg.avenue_load_only(_ctx(leads_that_remain="the airport's profiling page")) is None
    assert reg.avenue_load_only(_ctx()) is None


def test_rule_5_lead_on_file():
    assert reg.avenue_lead(_ctx(leads_that_remain="The county's plat.")) == "the lead on file: The county's plat."
    # consumed by rule 4 when the lead itself names a mixed filing
    assert reg.avenue_lead(_ctx(leads_that_remain="The utility's rate case.")) is None
    # rule 4 on still_open does not consume the lead
    assert reg.avenue_lead(_ctx(leads_that_remain="A plat.", still_open="a docket")) == "the lead on file: A plat."
    assert reg.avenue_lead(_ctx(leads_that_remain="  ")) is None


def test_rule_5_a_lead_that_says_none_is_no_lead():
    for text in ("None found beyond the regulator's file.", "  none needed", "None"):
        assert reg.avenue_lead(_ctx(leads_that_remain=text)) is None, text
    assert reg.avenue_lead(_ctx(leads_that_remain="Nonesuch Road plat")) == "the lead on file: Nonesuch Road plat"
    text, _ = reg.closes_as(_ctx(question="operating date", leads_that_remain="None found."), set(), "pending")
    assert text == "unresolved with every avenue of rule 3.3 tried and no lead remaining"


def test_rule_6_operating_date_with_nothing_left():
    text, keys = reg.closes_as(_ctx(question="operating date"), set(), "pending")
    assert text == "unresolved with every avenue of rule 3.3 tried and no lead remaining"
    assert keys == ["unresolved with every avenue of rule 3.3 tried and no lead remaining"]
    assert reg.rule_6_adds_nothing(_ctx(question="operating date"), set())
    assert not reg.rule_6_adds_nothing(_ctx(question="operating date", leads_that_remain="A lead."), set())


def test_rule_6_refuses_to_say_every_avenue_tried_when_none_was():
    with pytest.raises(ValueError):
        reg.closes_as(_ctx(question="operating date", avenues_tried="none"), set(), "pending")


def test_closes_as_joins_several_avenues():
    text, keys = reg.closes_as(
        _ctx(state="TX", site="x1", leads_that_remain="A plat."), {"x1"}, "pending")
    assert text == ("unresolved; closed with these avenues unpursued: the request to the Texas commission for the "
                    "official certificated-area maps (pending); the browser sitting's page for this site; "
                    "the lead on file: A plat.")
    assert len(keys) == 3


def test_first_run_suffix():
    text, keys = reg.closes_as(
        _ctx(on_the_fixed_list="no", coverage="first run 2026-11-18, for descriptive counts only",
             avenues_tried="none"), set(), "pending")
    assert text == ("unresolved; closed with these avenues unpursued: rule 3.3's lookups, never run on this site; "
                    "no lookup was made in this state")
    assert "no lookup was made in this state" in keys
    # not for the seventeen states
    text, _ = reg.closes_as(_ctx(on_the_fixed_list="no", avenues_tried="none"), set(), "pending")
    assert not text.endswith("no lookup was made in this state")


def test_closes_as_end_to_end(files):
    res = _build(files)
    assert _row(res, "s1", "operating date")["closes_as"] == \
        "unresolved; closed with these avenues unpursued: a load-only route for mixed filings"
    assert _row(res, "t7", "operating date")["closes_as"] == \
        "unresolved with every avenue of rule 3.3 tried and no lead remaining"
    assert _row(res, "tx1", "assignment")["closes_as"] == (
        "unresolved; closed with these avenues unpursued: the request to the Texas commission for the official "
        "certificated-area maps (pending); the browser sitting's page for this site; "
        "the lead on file: The recorded plat's electric easement.")
    assert _row(res, "s9", "assignment")["closes_as"].endswith("; no lookup was made in this state")
    res2 = _build(files, texas="declined")
    assert "(declined)" in _row(res2, "tx1", "assignment")["closes_as"]


# ----------------------------------------------------------------------------
# Browser list
# ----------------------------------------------------------------------------

def test_browser_section_5_only_and_matching():
    cells = reg.parse_browser_section_5(BROWSER_MD)
    assert len(cells) == 3
    sites = {"tx1": ("Texco, Harris County, TX", "City of Houstonia - (TX)"),
             "s1": ("Opco, Alpha County, AA", "Host One"),
             "bi:77-0": ("Someco, X County, AA", "Host One")}
    matched, unmatched = reg.match_browser_rows(cells, sites)
    assert matched == {"tx1": [cells[0]], "bi:77-0": [cells[2]]}
    assert unmatched == [cells[1]]


def test_browser_name_match_needs_one_site_and_the_host():
    cells = ["Walmart, 1 Road, Springfield (Springfield)"]
    two = {"a": ("Walmart, X County, AA", "City of Springfield - (AA)"),
           "b": ("Walmart, Y County, AA", "City of Springfield - (AA)")}
    assert reg.match_browser_rows(cells, two) == ({}, cells)
    wrong_host = {"a": ("Walmart, X County, AA", "Shelbyville Power")}
    assert reg.match_browser_rows(cells, wrong_host) == ({}, cells)


def test_browser_section_missing_raises():
    with pytest.raises(ValueError):
        reg.parse_browser_section_5("# nothing here\n")


# ----------------------------------------------------------------------------
# retained_because
# ----------------------------------------------------------------------------

def test_retained_kept_for_host_and_relevant_not_kept(files):
    res = _build(files)
    r = _row(res, "s1", "assignment")
    assert r["kept_for_hosts"] == "Host One"
    assert r["relevant_not_kept_for"] == "1"
    # kept by a utility, so the future-host item does not apply although one utility does not keep it
    assert r["retained_because"] == "kept for a listed host"


def test_retained_relevant_and_kept_by_no_one(files):
    res = _build(files)
    r = _row(res, "s6", "assignment")
    assert r["relevant_not_kept_for"] == "1"
    assert r["kept_for_other_utilities"] == "0"
    assert r["retained_because"] == (
        "relevant and not kept under the place criterion: retained because the future-host criterion "
        "is not implemented")


def test_retained_consequential_comparison(files):
    res = _build(files)
    r = _row(res, "s2", "operating date")
    assert r["kept_for_other_utilities"] == "1"
    assert r["kept_for_other_utilities_by_reference_place"] == "comparison 1"
    assert r["retained_because"] == "kept for another utility: a consequential comparison question"


def test_retained_undefined_reference_is_consequential(files):
    res = _build(files)
    r = _row(res, "s5", "assignment")
    assert r["kept_for_other_utilities_by_reference_place"] == "undefined 1"
    assert r["retained_because"] == "kept for another utility: a consequential comparison question"


def test_retained_only_over_the_ceiling(files):
    res = _build(files)
    r = _row(res, "s3", "assignment")
    assert r["kept_only_by_the_conservative_result"] == "yes"
    assert r["kept_for_other_utilities_by_reference_place"] == "early 1"
    assert r["retained_because"] == (
        "kept for another utility that is not a comparison utility on the reference; kept only by the "
        "conservative result for a utility over the search ceiling")
    assert r["evidence_on_file"] == ""  # its correction is a date record, not about the assignment
    assert r["avenues_tried"] == "government 1; map 2"


def test_retained_relevant_to_no_one(files):
    res = _build(files)
    r = _row(res, "s4", "capacity coverage")
    assert r["retained_because"] == (
        "relevant to no utility under the place criterion: retained because the future-host criterion "
        "is not implemented")
    assert r["status"] == "unresolved"
    assert r["avenues_tried"] == "none"
    assert r["label"] == "" and r["mw_full"] == ""


def test_retained_on_the_fixed_list_not_open(files):
    res = _build(files)
    assert _row(res, "t7", "operating date")["retained_because"] == \
        "on the fixed list; not an open question in the check"


def test_retained_unit_order_and_conservative_not_over_ceiling_raises():
    utils = {"h:AA": {"method": "conservative", "why": "a divisor", "place_key": "early", "host": True}}
    with pytest.raises(ValueError):
        reg.retained_because(keepers=["h:AA"], relevant=["h:AA"], utils=utils, open_in_check=True,
                             on_fixed_list=False)


def test_csv_labels_and_mw(files):
    res = _build(files)
    assert _row(res, "s9", "assignment")["label"] == "Ninco, Omega"
    assert _row(res, "s9", "assignment")["mw_full"] == "30"
    assert _row(res, "s2", "operating date")["mw_full"] == ""
    assert _row(res, "s1", "assignment")["label"] == "Opco, Alpha County, AA"
    assert _row(res, "s5", "assignment")["evidence_on_file"] == "an invented widening"


# ----------------------------------------------------------------------------
# Unexpected shapes raise
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("breaker", [
    lambda a: a.pop("hosts"),
    lambda a: a["exact"]["AA"].pop("utilities"),
    lambda a: a["exact"]["AA"]["questions"].append({"fid": "s7", "question": "weather"}),
    lambda a: a["exact"]["AA"]["utilities"]["2:AA"].update(method="guess"),
    lambda a: a["exact"]["AA"]["utilities"]["2:AA"]["kept_questions"].append({"fid": "s4", "question": "capacity"}),
    lambda a: a["exact"]["AA"]["utilities"]["2:AA"]["relevant_questions"].append("s4"),
    lambda a: a["exact"]["AA"]["utilities"].update({"5:BB": a["exact"]["AA"]["utilities"]["2:AA"]}),
    lambda a: a["exact"]["BB"]["questions"].append({"fid": "s1", "question": "assignment"}),
    lambda a: a["hosts"].append({"utility": "77:AA", "name": "Missing"}),
    lambda a: a["exact"]["AA"]["utilities"]["2:AA"]["reference"].update(place="sideways"),
])
def test_unexpected_json_shape_raises(breaker):
    a = invented_attribution()
    breaker(a)
    with pytest.raises(ValueError):
        reg.index_check(a)


# ----------------------------------------------------------------------------
# Summary and CLI
# ----------------------------------------------------------------------------

def test_summary_counts_add_up(files):
    res = _build(files)
    md = reg.render_summary(res)
    assert md.startswith(reg.OPENING)
    n = len(res.rows)
    tables = reg.summary_tables(res)
    assert sum(tables["status"]["all"].values()) == n
    assert sum(tables["coverage"]["all"].values()) == n
    split = tables["status"]
    assert sum(split["seventeen states of D-68"].values()) + sum(split["first-run states"].values()) \
        + sum(split["states not in the check"].values()) == n
    unresolved = sum(1 for r in res.rows if r["status"] == "unresolved")
    assert tables["status"]["all"]["unresolved"] == unresolved
    # every unresolved row carries at least one avenue entry
    assert all(r["_avenues"] for r in res.rows if r["status"] == "unresolved")
    assert f"| total | {n} |" in md
    # reasons are counted as whole items (one of them carries a semicolon of its own)
    assert set(tables["retained"]["all"]) <= set(reg.RETAINED_ORDER)
    for item in reg.RETAINED_ORDER:
        assert tables["retained"]["all"][item] == sum(1 for r in res.rows if item in r["_retained"])
    # t7 and tx1 (three each) and s1's operating date and capacity coverage
    assert tables["retained"]["all"][reg.R_FIXED] == 8
    assert f"| {reg.R_FIXED} | 8 |" in md


def test_written_strings_carry_no_em_dash_or_banned_word(files, tmp_path):
    res = _build(files)
    text = reg.render_csv(res.rows) + reg.render_summary(res)
    assert "—" not in text
    csv_text = reg.render_csv(res.rows)
    assert "exhausted" not in csv_text.lower()
    md = reg.render_summary(res)
    # the word appears once, and only in the owner's phrase
    assert md.lower().count("exhausted") == 1
    assert md.count("the class the owner's ruling calls exhausted") == 1


def test_cli_writes_and_check_notices_a_changed_file(files, tmp_path, capsys):
    out = tmp_path / "out" / "register"
    assert reg.main(_argv(files, out)) == 0
    printed = capsys.readouterr().out
    assert str(out) + ".csv" in printed and "rows: 15" in printed
    assert reg.main(_argv(files, out, "--check")) == 0
    csv_path = Path(str(out) + ".csv")
    csv_path.write_text(csv_path.read_text().replace("unresolved", "resolved", 1))
    assert reg.main(_argv(files, out, "--check")) == 1
    assert reg.main(_argv(files, out)) == 0
    md_path = Path(str(out) + ".md")
    md_path.write_text(md_path.read_text() + "\nextra line\n")
    assert reg.main(_argv(files, out, "--check")) == 1


# ----------------------------------------------------------------------------
# Rule 1 against the log, end to end
# ----------------------------------------------------------------------------

def test_rule_1_wording_follows_the_log(files):
    res = _build(files)
    assert "rule 3.3's lookups, never run on this site" in _row(res, "s9", "assignment")["closes_as"]
    assert ("rule 3.3's rounds, not run in full on this site (attempts on file are in avenues_tried)"
            in _row(res, "s3", "assignment")["closes_as"])


# ----------------------------------------------------------------------------
# Named avenues
# ----------------------------------------------------------------------------

NAMED_COLUMNS = ["site", "question", "avenue", "source"]


def test_named_avenues_absent_file_changes_nothing(files):
    assert not files["named"].exists()
    res = _build(files)
    assert _row(res, "t7", "operating date")["closes_as"] == \
        "unresolved with every avenue of rule 3.3 tried and no lead remaining"


def test_named_avenues_added_after_rules_1_to_5(files):
    _write_csv(files["named"], NAMED_COLUMNS, [
        {"site": "t7", "question": "", "avenue": "the county clerk's deed index", "source": "invented"},
        {"site": "tx1", "question": "assignment", "avenue": "the utility's line extension notice",
         "source": "invented"},
        {"site": "tx1", "question": "operating date", "avenue": "never added: the row is resolved",
         "source": "invented"},
    ])
    res = _build(files)
    # blank question: every unresolved question of the site
    assert _row(res, "t7", "assignment")["closes_as"] == \
        "unresolved; closed with these avenues unpursued: the county clerk's deed index"
    assert _row(res, "t7", "operating date")["closes_as"] == \
        "unresolved; closed with these avenues unpursued: the county clerk's deed index"
    # the resolved-for-part row of the same site takes it too
    assert _row(res, "t7", "capacity coverage")["closes_as"] == \
        "resolved for part; for the rest, closed with these avenues unpursued: the county clerk's deed index"
    assert _row(res, "tx1", "assignment")["closes_as"].endswith(
        "the lead on file: The recorded plat's electric easement.; the utility's line extension notice")
    assert _row(res, "tx1", "operating date")["closes_as"] == "resolved"
    assert _row(res, "tx1", "capacity coverage")["closes_as"].startswith("not examined")
    tables = reg.summary_tables(res)
    # the per-avenue table is of unresolved rows; the resolved-for-part row is classed separately
    assert tables["avenues"]["all"]["the county clerk's deed index"] == 2
    assert _row(res, "t7", "capacity coverage")["closing_class"] == \
        "resolved for part; the rest closed with named avenues unpursued"


def test_named_avenues_unknown_site_raises(files):
    _write_csv(files["named"], NAMED_COLUMNS, [
        {"site": "nowhere", "question": "", "avenue": "x", "source": "invented"}])
    with pytest.raises(ValueError):
        _build(files)


def test_named_avenues_bad_question_or_blank_avenue_raises(files):
    _write_csv(files["named"], NAMED_COLUMNS, [
        {"site": "t7", "question": "date", "avenue": "x", "source": "invented"}])
    with pytest.raises(ValueError):
        _build(files)
    _write_csv(files["named"], NAMED_COLUMNS, [
        {"site": "t7", "question": "", "avenue": "  ", "source": "invented"}])
    with pytest.raises(ValueError):
        _build(files)


# ----------------------------------------------------------------------------
# Browser list: the one explicit mapping
# ----------------------------------------------------------------------------

def test_browser_explicit_mapping_for_340_progress_circle():
    cell = "The Cheyenne expansion building, 340 Progress Circle (Cheyenne Light)"
    sites = {"bi:1123-0": ("Lunavi, Laramie County, WY", "Cheyenne Light Fuel & Power")}
    assert reg.match_browser_rows([cell], sites) == ({"bi:1123-0": [cell]}, [])
    with pytest.raises(ValueError):
        reg.match_browser_rows([cell], {})


# ----------------------------------------------------------------------------
# Summary additions
# ----------------------------------------------------------------------------

def test_summary_per_host_table_and_paths(files):
    res = _build(files)
    md = reg.render_summary(res)
    assert "| Host One | 1:AA | 1 | 0 |" in md
    assert str(files["corrections"]) in md and str(files["attribution"]) in md


def test_per_host_counts_unresolved(files):
    a = invented_attribution()
    a["exact"]["AA"]["utilities"]["1:AA"] = _util(
        place="cohort", rel=[("s1", "assignment"), ("s3", "assignment")],
        kept=[("s1", "assignment"), ("s3", "assignment")])
    files["attribution"].write_text(json.dumps(a))
    res = _build(files)
    assert reg.per_host_counts(res) == [("Host One", "1:AA", 2, 1)]


# ----------------------------------------------------------------------------
# closing_class and the reconciliation
# ----------------------------------------------------------------------------

def test_closing_class_rule():
    cc = reg.closing_class
    assert cc("resolved", "map 2", []) == "resolved"
    assert cc("resolved (entered in the corrections in force)", "none", []) == "resolved"
    assert cc("resolved for part", "map 2", ["a lead"]) == \
        "resolved for part; the rest closed with named avenues unpursued"
    assert cc("resolved for part", "map 2", []) == "resolved for part; the rest with every avenue tried"
    assert cc("not examined", "map 2", []) == "not examined: no avenue was run on this question"
    assert cc("unresolved", "none", ["x"]) == \
        "unresolved; never looked up: closed with rule 3.3's lookups unpursued"
    assert cc("unresolved", "map 1", ["x"]) == \
        "unresolved; looked up in part: closed with named avenues unpursued"
    assert cc("unresolved", "map 1", []) == "unresolved; every avenue of rule 3.3 tried and no lead remaining"
    with pytest.raises(ValueError):
        cc("unresolved", "none", [])  # never looked up, yet nothing named: closes_as would have raised
    with pytest.raises(ValueError):
        cc("open", "map 1", [])


def test_closing_class_is_a_partition_and_last_column(files):
    res = _build(files)
    assert reg.COLUMNS[-1] == "closing_class"
    assert all(r["closing_class"] in reg.CLOSING_CLASSES for r in res.rows)
    counts = Counter(r["closing_class"] for r in res.rows)
    assert sum(counts.values()) == len(res.rows)
    assert counts["unresolved; never looked up: closed with rule 3.3's lookups unpursued"] == 5
    assert counts["unresolved; looked up in part: closed with named avenues unpursued"] == 3
    assert counts["unresolved; every avenue of rule 3.3 tried and no lead remaining"] == 2
    assert counts["resolved for part; the rest with every avenue tried"] == 1
    # the class agrees with the wording of closes_as
    for r in res.rows:
        if r["closing_class"].startswith("unresolved; every avenue"):
            assert r["closes_as"] == reg.AV_ALL_TRIED


def test_reconciliation_numbers(files):
    res = _build(files)
    rec = reg.reconciliation(res)
    n_unres = sum(1 for r in res.rows if r["status"] == "unresolved")
    assert n_unres == 10
    assert sum(rec["unresolved_by_class"].values()) == n_unres
    assert rec["by_number"] == {"0": 2, "1": 7, "2": 0, "3 or more": 1}
    assert sum(rec["by_number"].values()) == n_unres
    # alone + with another = rows carrying it; the rows with exactly one avenue are the "alone" total
    for av, (alone, with_other) in rec["alone_with"].items():
        assert alone + with_other == sum(1 for r in res.rows if r["status"] == "unresolved" and av in r["_named"])
    assert sum(a for a, _w in rec["alone_with"].values()) == rec["by_number"]["1"]
    assert rec["alone_with"][reg.AV_BROWSER] == (0, 1)
    assert rec["alone_with"][reg.AV_NEVER_RUN] == (5, 0)
    assert rec["avenue_mentions"] == 7 + 3


def test_reconciliation_section_in_summary(files):
    res = _build(files)
    md = reg.render_summary(res)
    assert "## Reconciliation" in md
    assert "| total | 15 |" in md  # rows by closing class add to the row total
    assert "| unresolved rows | 10 |" in md
    assert "10 avenue entries" in md and "10 unresolved rows" in md
    assert "| 3 or more | 1 |" in md


# ----------------------------------------------------------------------------
# Paths in the summary
# ----------------------------------------------------------------------------

def test_display_path_relative_inside_the_project(tmp_path):
    inside = reg.PROJECT / "pipeline" / "facilities" / "verified" / "x.json"
    assert reg.display_path(str(inside)) == "pipeline/facilities/verified/x.json"
    spelled = reg.PROJECT / "pipeline" / ".." / "pipeline" / "facilities" / "verified" / "x.json"
    assert reg.display_path(str(spelled)) == "pipeline/facilities/verified/x.json"
    outside = tmp_path / "a" / ".." / "y.json"
    assert reg.display_path(str(outside)) == str((tmp_path / "y.json").resolve())


def test_check_passes_however_the_paths_are_spelled(files, tmp_path):
    out = tmp_path / "out" / "register"
    assert reg.main(_argv(files, out)) == 0
    respelled = dict(files)
    for k in ("attribution", "corrections"):
        p = files[k]
        respelled[k] = p.parent / "sub" / ".." / p.name
    (tmp_path / "sub").mkdir()
    assert reg.main(_argv(respelled, out, "--check")) == 0
