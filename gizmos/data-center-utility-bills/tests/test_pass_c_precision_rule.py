"""The precision rule's table (docs/gate1/precision-rule-2026-11-18.md): the arithmetic and the reading of fields,
on made-up rows. No file under data/ and no network."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import pass_c_precision_rule as pr  # noqa: E402


def cond(site="s", cls="meets all six conditions: medium", tied="address"):
    return {"site": site, "class_under_D63": cls, "tied_to_the_facility_by": tied}


def prow(site="s", pub="A state agency", name="layer", basis="tied parcel 1 (tied to the facility by address)",
         extent="100", at="'Alpha' (OBJECTID 1)", low="1000", high="1062.5",
         rel="esriSpatialRelWithin (calibrated on this layer with a 1 m disc)"):
    return {"site": site, "layer_publisher": pub, "layer_name": name, "location_basis": basis, "parcel_extent_m": extent,
            "at_point": at, "nearest_line_m_low": low, "nearest_line_m_high": high, "relation_used_for_contains": rel}


def one(c, rows):
    return pr.table([c], rows)[0]


def test_the_allowance_is_one_and_a_half_percent_and_five_metres():
    assert pr.allowed_low(1000) == 1000 * 0.985 - 5.0 == 980.0


def test_a_tied_site_well_inside_one_feature_stands_and_says_accuracy_is_unknown():
    r = one(cond(), [prow()])
    assert r["P1_location_resolved"] == "yes" and r["P2_whole_location_on_one_side"] == "holds"
    assert r["what_the_rule_says"].startswith("reliance stands") and "unknown accuracy" in r["what_the_rule_says"]


def test_an_untied_point_defeats_reliance_whatever_the_distance():
    r = one(cond(tied="neither"), [prow(basis="a point not tied to the facility", extent="", low="20000", high="")])
    assert r["what_the_rule_says"].startswith("reliance defeated: P1")


def test_a_line_that_may_lie_within_the_extent_defeats_reliance():
    # 300 m x 0.985 - 5 = 290.5 m, short of an extent of 298 m, though the raw low end is beyond it
    r = one(cond(), [prow(extent="298", low="300", high="310")])
    assert r["P2_whole_location_on_one_side"] == "fails" and "P2" in r["what_the_rule_says"]
    assert "290.5" in r["P2_by_layer"]


def test_distance_never_upgrades_a_lead_or_a_statement():
    far = [prow(low="20000", high="")]
    assert one(cond(cls="lead"), far)["what_the_rule_says"].startswith("a lead")
    assert one(cond(cls="supports a statement on file; not itself sufficient"), far)["what_the_rule_says"].startswith(
        "does not rely on a depiction")


def test_no_distance_and_an_untested_edge_are_not_shown():
    assert pr.p2_layer(prow(low="", high=""), 100.0)[0] == "not shown"
    assert pr.p2_layer(prow(rel="none: for a 1 m disc neither relation returned the at-point set"), 100.0)[0] == "not shown"
    assert pr.p2_layer(prow(at="nothing"), 100.0)[0] == "not shown"
    assert pr.p2_layer(prow(), None)[0] == "not shown"


def test_two_spellings_of_one_entity_are_not_a_conflict_and_two_entities_are():
    a = prow(name="one", at="'PGE' (OBJECTID 116)")
    b = prow(name="two", at="'Portland General Electric' (OBJECTID 7)")
    assert one(cond(), [a, b])["P3_conflict"] == "no"
    c = prow(name="three", at="'Beta Cooperative' (OBJECTID 9)")
    r = one(cond(), [a, c])
    assert r["P3_conflict"] == "yes" and r["P3_conflict_only_from_a_layer_of_lower_standing"] == "no"
    assert "P3" in r["what_the_rule_says"]


def test_a_conflict_from_a_layer_of_lower_standing_is_marked_as_reading_three():
    a = prow(name="state", at="'Alpha' (OBJECTID 1)")
    h = prow(name="national", pub="HIFLD copy (ORNL / DOE CESER data)", at="'Gamma' (OBJECTID 3)", low="50", high="60")
    r = one(cond(), [a, h])
    assert r["P3_conflict_only_from_a_layer_of_lower_standing"] == "yes"
    assert "reading 3" in r["what_the_rule_says"]
    assert r["P2_whole_location_on_one_side"] == "holds"          # the lower-standing layer's line does not decide P2


def test_a_layer_that_returns_nothing_at_the_point_is_not_a_conflict():
    a = prow(name="state", at="'Alpha' (OBJECTID 1)")
    n = prow(name="coops only", at="nothing", low="700", high="750", rel="not needed: nothing at the point")
    assert one(cond(), [a, n])["P3_conflict"] == "no"


def test_a_listing_is_undone_by_a_conflict_and_not_by_a_distance():
    ok = one(cond(cls="checks a town listing: the listing holds"), [prow()])
    assert ok["what_the_rule_says"] == "the layers do not undo the listing"
    a, c = prow(name="a"), prow(name="c", at="'Beta' (OBJECTID 2)")
    r = one(cond(cls="checks a town listing: the listing holds"), [a, c])
    assert "the listing no longer suffices unless a record" in r["what_the_rule_says"] and r["needs_a_reading"]
    untied = one(cond(cls="checks a town listing: the listing holds", tied="neither"), [prow(basis="a point not tied")])
    assert untied["what_the_rule_says"].startswith("the layers cannot check the listing")


def test_the_table_on_file_is_what_the_rule_gives_and_no_class_is_written():
    if not pr.OUT.exists():
        import pytest
        pytest.skip("the table has not been written")
    before = pr.CONDITIONS.read_bytes()
    assert pr.main(["--check"]) == 0
    assert pr.CONDITIONS.read_bytes() == before
