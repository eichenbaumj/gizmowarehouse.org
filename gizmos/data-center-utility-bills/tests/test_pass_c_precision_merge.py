"""The precision fields carried onto each layer-based record (docs/DECISIONS.md, D-65 item 2; D-66 section 5; D-69)."""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import pass_c_precision_merge as pm  # noqa: E402


def prow(site, layer, lo, hi, what="", acc="none", comp="none", at="'A' (1)", basis="tied parcel 1", unc="parcel extent 100.0 m",
         conflict="The layers agree"):
    return {"site": site, "layer_name": layer, "nearest_line_m_low": lo, "nearest_line_m_high": hi, "what_changes_there": what,
            "statements_on_accuracy": acc, "statements_on_completeness": comp, "at_point": at, "location_basis": basis,
            "location_uncertainty": unc, "conflicting_geometry": conflict, "limitation": "L"}


def test_a_sites_layers_are_folded_in_order_and_nothing_else_is_touched():
    conditions = [{"site": "s1", "class_under_D63": "lead", "note_D63": "x"}, {"site": "s2", "class_under_D63": "medium", "note_D63": ""}]
    precision = [prow("s1", "official", "500", "562.5", "a neighbour touches the disc"),
                 prow("s1", "copy", "more than 20 km", "more than 20 km"),
                 prow("s2", "", "", "", at="no layer can be queried")]
    out, fields = pm.merged(conditions, precision)
    assert fields == ["site", "class_under_D63", "note_D63"] + pm.NEW
    assert [(r["site"], r["class_under_D63"], r["note_D63"]) for r in out] == [("s1", "lead", "x"), ("s2", "medium", "")]
    assert out[0]["nearest_drawn_line_m_by_layer"] == ("official: 500 to 562.5 (a neighbour touches the disc) | "
                                                       "copy: more than 20 km")
    assert out[0]["location_uncertainty"] == "tied parcel 1; parcel extent 100.0 m"            # the same for both layers: once
    assert out[0]["precision_limitation"] == "L" and out[0]["conflicting_geometry"] == "The layers agree"
    assert out[1]["nearest_drawn_line_m_by_layer"] == "no layer: no layer can be queried"
    again, _ = pm.merged(out, precision)                                                        # running it twice changes nothing
    assert again == out


def test_a_record_with_no_precision_rows_is_refused_in_words():
    with pytest.raises(ValueError, match="no precision rows for s2"):
        pm.merged([{"site": "s1"}, {"site": "s2"}], [prow("s1", "official", "1", "2")])


def test_every_layer_record_on_file_carries_the_fields_as_the_precision_file_has_them():
    if not pm.PRECISION.exists():
        pytest.skip("the precision file has not been written")
    csv.field_size_limit(10 ** 9)
    with open(pm.CONDITIONS, newline="") as f:
        conditions = list(csv.DictReader(f))
    with open(pm.PRECISION, newline="") as f:
        precision = list(csv.DictReader(f))
    out, fields = pm.merged(conditions, precision)
    assert list(conditions[0]) == fields and conditions == out
    assert all(r["precision_limitation"].startswith("Agreeing probes and a large distance are recorded and prove nothing")
               for r in conditions)
    assert {r["site"] for r in precision} == {r["site"] for r in conditions}
