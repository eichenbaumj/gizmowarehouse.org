"""The verification pass's records as D-61 leaves them: kinds, statuses and files that have to agree with one another."""
import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
V = ROOT / "pipeline" / "facilities" / "verified"

KINDS = {"stated_start", "operating_by", "not_before", "built_or_generators_by", "not_operating_as_of"}
STATUSES = {"resolved", "resolved for part", "unresolved", "not examined"}
QUESTIONS = {"assignment", "operating date", "capacity coverage"}


def rows(name):
    return list(csv.DictReader(open(V / name)))


def test_every_date_evidence_row_has_a_kind_under_d61():
    for r in rows("date_evidence.csv"):
        assert r["kind_d61"] in KINDS, r["site"]
        assert r["url"].startswith("http") and r["quote"].strip()


def test_generator_and_construction_records_are_not_classed_as_operation():
    for r in rows("date_evidence.csv"):
        words = (r["quote"] + " " + r["note_d61"]).lower()
        if r["kind_d61"] in ("operating_by", "stated_start"):
            assert "generator activity" not in r["note_d61"].lower() or "not" in r["note_d61"].lower()
        if "yearbuilt" in r["quote"].lower().replace(" ", "").replace("_", ""):
            assert r["kind_d61"] == "built_or_generators_by", r["site"]
        del words


def test_a_site_known_not_to_have_operated_has_no_convention_year():
    c = {(x["fid"], x["kind"]): x for x in json.load(open(V / "pass_c_corrections.json"))}
    d = c[("bi:852-0", "date")]
    assert d["latest"] is None and d["never_is_possible"] is True and d["convention"] is None


def test_withdrawn_records_are_not_in_any_batch_that_will_be_applied():
    withdrawn = {r["fid"] for r in json.load(open(V / "pass_c_withdrawn.json"))}
    assert {"bi:1123-0", "bi:438-0", "bi:821-0"} <= withdrawn
    assert {"bi:928-0", "bi:914-0", "bi:444-0"} <= withdrawn  # D-63 rules 2 and 6
    for name in ("batch_c_0.json", "batch_c_1.json", "batch_c_2.json", "batch_c_3.json"):
        fids = {r["fid"] for r in json.load(open(V / name))}
        assert not (fids & withdrawn), name
    # batch_c_4 holds the Lewisville record that replaced a withdrawn one; the two San Antonio layer records are out of it
    assert not ({r["fid"] for r in json.load(open(V / "batch_c_4.json"))} & {"bi:928-0", "bi:914-0"})
    for r in json.load(open(V / "pass_c_withdrawn.json")):
        assert r["withdrawn_under"].startswith(("D-61", "D-63")) and r["status_now"]
    # a withdrawn record comes back only as a new record that says under which rule it was re-entered
    for r in json.load(open(V / "batch_c_5.json")):
        assert r["notes"].startswith("Re-entered under D-63 rule 6") and r["map_placement"]["parcel_point_on_grid"]


def test_archive_records_keep_the_original_url_the_capture_and_the_site_identity():
    for r in json.load(open(V / "batch_c_4.json")):
        if "web.archive.org" in r["utility_source_url"]:
            assert r["utility_source_original_url"].startswith("http")
            assert "Internet Archive" in r["utility_source_capture"]
            assert r["utility_source_site_identity"]


def test_every_listed_site_has_its_three_questions_with_a_known_status():
    q = rows("pass_c_questions.csv")
    by_site = {}
    for r in q:
        assert r["question"] in QUESTIONS and r["status"] in STATUSES
        by_site.setdefault(r["site"], set()).add(r["question"])
    targets = {r["site"] for r in rows("pass_c_targets.csv")}
    assert targets <= set(by_site)
    assert all(v == QUESTIONS for v in by_site.values())


def test_no_question_is_called_exhausted_and_an_open_one_says_what_is_open():
    for r in rows("pass_c_questions.csv"):
        assert "exhaust" not in " ".join(r.values()).lower()
        if r["closes_as"].startswith("closed with this avenue unpursued"):
            assert ":" in r["closes_as"]
        if r["question"] == "assignment" and r["status"] in ("unresolved", "resolved for part"):
            assert r["still_open"].strip(), r["site"]


def test_only_a_layer_that_meets_all_six_conditions_stands_behind_a_map_verification():
    cls = {r["site"]: r["class_under_D63"] for r in rows("pass_c_layer_conditions.csv")}
    for name in ("batch_c_0.json", "batch_c_1.json", "batch_c_2.json", "batch_c_3.json", "batch_c_4.json"):
        for r in json.load(open(V / name)):
            if r["utility_evidence_kind"] == "local map with a utility page":
                assert cls[r["fid"]].startswith("meets all six"), (name, r["fid"], cls[r["fid"]])


def test_the_corrections_file_is_one_the_expansion_test_accepts():
    pytest.importorskip("pandas")
    if not (ROOT / "data" / "interim" / "facilities.parquet").exists():
        pytest.skip("the inventory is not built")
    import sys
    sys.path.insert(0, str(ROOT))
    from pipeline.facilities import pass_c_expand as px
    inp = px.load_frozen()
    for name, least in (("pass_c_corrections.json", 55), ("pass_c_corrections_variant.json", 55), ("pass_c_corrections_d63.json", 40)):
        c = json.load(open(V / name))
        px.check_unresolved_count(c)
        assert len(px.parse_corrections(c, inp)) >= least


def test_every_layer_reading_has_a_class_under_d63_and_the_earlier_class_is_kept():
    for r in rows("pass_c_layer_conditions.csv"):
        assert r["class_under_D61"] and r["class_under_D63"], r["site"]


def test_a_layer_not_drawn_from_the_official_record_names_and_excludes_no_one():
    """D-63 rules 2 and 5: the Texas commission's layers are leads, so nothing is narrowed or verified on them."""
    texas = [r for r in rows("pass_c_layer_conditions.csv")
             if "pass_c_layers_L3" in r["record_check"] or "pass_c_layers_added" in r["record_check"]]
    assert len(texas) >= 25
    for r in texas:
        c = r["class_under_D63"]
        assert not c.startswith(("meets", "narrows")), (r["site"], c)
    assert not any("not certificated" in r["the_sessions_reading"] for r in rows("pass_c_layer_conditions.csv"))


def test_no_narrowing_is_entered_as_off_the_panel():
    """D-63 rule 5: a correction that takes a site off the panel has to be a verification."""
    for x in json.load(open(V / "pass_c_corrections_d63.json")):
        assert x["kind"] != "narrow", x["fid"]
        if x["kind"] == "assign" and x["to"] == "off_panel":
            assert "NARROWED" not in x["why"], x["fid"]


def test_the_reopened_site_and_the_two_step_building_are_entered_as_d63_rule_8_asks():
    c = json.load(open(V / "pass_c_corrections_d63.json"))
    kinds = {(x["fid"], x["kind"]): x for x in c}
    assert kinds[("bi:821-0", "reopen")]["candidates"]
    split = kinds[("bi:837-0", "capacity_split")]
    assert split["rest_earliest"] == 2016 and 0.4 < split["first_share"] < 0.6
    assert kinds[("bi:837-0", "date")]["convention"] is None
