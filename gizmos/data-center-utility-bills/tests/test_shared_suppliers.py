"""Rule 2.4's shared-supplier exercise: which of a host's matches share its supplier (D-58 rule 2.4; the owner's ruling of
2026-11-18, Stop 3: "Membership-only rows are treated as sharing a supplier in the exercise, labelled as resting on
membership").

Only the selection the exercise will call is built here; the exercise's run is not. Invented tables only, except one test
that loads the shipped suppliers.csv (no price, no revenue).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import suppliers as sp  # noqa: E402

WINDOW = list(range(2009, 2019))
HOST = (1, "AA")


def table(*specs):
    """specs: (id, state, supplier, kind, from, to, note) -> a supplier table as suppliers.load returns it."""
    base = {"name": "x", "from_year_basis": "assumed", "to_year_basis": "assumed", "source_url": "https://example.org",
            "source_kind": "supplier_member_list", "quote": "q", "date_opened": "2026-11-18"}
    t = pd.DataFrame([{**base, "utility_id_eia": u, "state": st, "supplier": s, "supplier_kind": k, "from_year": lo, "to_year": hi,
                       "note": note} for u, st, s, k, lo, hi, note in specs], columns=list(sp.COLUMNS))
    return t.astype({"utility_id_eia": int, "from_year": int, "to_year": int})


MEMBER = "MEMBERSHIP_ONLY: the source shows membership, not that this supplier provided all or most of the unit's requirements."


def shared(t, matches, **kw):
    return sp.shared_with_host(t, HOST, WINDOW, matches, **kw)


def test_a_documented_shared_supplier_is_removed_and_tagged_documented():
    t = table((1, "AA", "G&T One", "g_and_t_cooperative", 2001, 2025, ""), (2, "AA", "G&T One", "g_and_t_cooperative", 2001, 2025, ""),
              (3, "AA", "G&T Two", "g_and_t_cooperative", 2001, 2025, ""))
    r = shared(t, [(2, "AA"), (3, "AA")])
    assert [(x["utility"], x["tag"], x["suppliers"]) for x in r["shares"]] == [("2:AA", sp.DOCUMENTED, ["G&T One"])]
    assert r["not_shared"] == ["3:AA"] and r["unknown"] == [] and r["removed_resting_on_membership_only"] == []


@pytest.mark.parametrize("side", ["host", "match", "both"])
def test_membership_only_counts_as_sharing_and_is_listed_apart(side):
    t = table((1, "AA", "JAA", "joint_action_agency", 2001, 2025, MEMBER if side in ("host", "both") else ""),
              (2, "AA", "JAA", "joint_action_agency", 2001, 2025, MEMBER if side in ("match", "both") else ""))
    r = shared(t, [(2, "AA")])
    assert [(x["utility"], x["tag"]) for x in r["shares"]] == [("2:AA", sp.MEMBERSHIP_ONLY)]
    assert [x["utility"] for x in r["removed_resting_on_membership_only"]] == ["2:AA"]


def test_one_documented_year_makes_the_share_documented():
    t = table((1, "AA", "JAA", "joint_action_agency", 2001, 2025, ""),
              (2, "AA", "JAA", "joint_action_agency", 2001, 2012, MEMBER), (2, "AA", "JAA", "joint_action_agency", 2013, 2025, ""))
    r = shared(t, [(2, "AA")])
    assert r["shares"][0]["tag"] == sp.DOCUMENTED and r["shares"][0]["membership_only_years"] == list(range(2009, 2013))


def test_a_share_outside_the_window_does_not_count():
    t = table((1, "AA", "JAA", "joint_action_agency", 2001, 2025, ""), (2, "AA", "JAA", "joint_action_agency", 2001, 2005, ""),
              (2, "AA", "Other", "joint_action_agency", 2006, 2025, ""))
    assert shared(t, [(2, "AA")])["shares"] == []


def test_an_unknown_supplier_is_never_removed_and_is_counted():
    t = table((1, "AA", "G&T One", "g_and_t_cooperative", 2001, 2025, ""), (2, "AA", "unknown", "unknown", 2001, 2025, ""))
    r = shared(t, [(2, "AA"), (3, "AA")])                                    # 3 has no row at all
    assert r["shares"] == [] and [x["utility"] for x in r["unknown"]] == ["2:AA", "3:AA"]
    assert r["counts"] == {"matches": 2, "removed": 0, "removed_documented": 0, "removed_resting_on_membership_only": 0,
                           "unknown": 2, "not_shared": 0}


def test_a_host_whose_supplier_is_unknown_removes_nothing_and_says_so():
    t = table((1, "AA", "unknown", "unknown", 2001, 2025, ""), (2, "AA", "G&T One", "g_and_t_cooperative", 2001, 2025, ""))
    r = shared(t, [(2, "AA")])
    assert r["shares"] == [] and r["host_supplier_unknown_years"] == WINDOW and [x["utility"] for x in r["unknown"]] == ["2:AA"]


def test_own_generation_is_not_a_shared_supplier_by_name():
    t = table((1, "AA", "own generation (Big Co)", "own_generation", 2001, 2025, ""),
              (2, "AA", "own generation (Big Co)", "own_generation", 2001, 2025, ""))
    r = shared(t, [(2, "AA")])
    assert r["shares"] == [] and r["not_shared"] == ["2:AA"]


def test_one_supplied_the_other_counts_when_the_supplier_is_named_as_a_unit():
    """A match that buys its requirements from the host (the host's id given for that supplier's name) shares a supplier."""
    t = table((1, "AA", "own generation (Big Co)", "own_generation", 2001, 2025, ""),
              (2, "AA", "Big Co requirements service", "investor_owned_requirements", 2001, 2025, ""))
    assert shared(t, [(2, "AA")])["shares"] == []                             # without the mapping it cannot be seen
    r = shared(t, [(2, "AA")], supplier_ids={"Big Co requirements service": {1}})
    assert [(x["utility"], x["tag"], x["how"]) for x in r["shares"]] == [("2:AA", sp.DOCUMENTED, [sp.SUPPLIED_THE_OTHER])]


def test_a_blank_state_row_covers_every_state_of_the_id_and_a_match_of_the_hosts_own_id_is_left_to_rule_2_3():
    t = table((1, "", "JAA", "joint_action_agency", 2001, 2025, ""), (2, "", "JAA", "joint_action_agency", 2001, 2025, ""))
    r = shared(t, [(2, "BB"), (1, "BB")])
    assert [x["utility"] for x in r["shares"]] == ["2:BB"] and r["own_utility_not_assessed"] == ["1:BB"]


def test_the_shipped_table_loads_and_its_membership_rows_are_recognised():
    t = sp.load()
    assert len(t) == 256 and int(sp.membership_only(t).sum()) == 26
    assert set(t.supplier_kind) <= set(sp.KINDS)
