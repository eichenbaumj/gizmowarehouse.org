"""The pre-freeze quantity summaries (pipeline/analysis/prefreeze_summaries.py), on invented inputs only.

Covers: rule 2.4's per-pair removal (a membership-only link removes and is labelled; an unknown match is counted and kept;
a host left with four matches is named and kept; a host left with none is not estimable; a unit removed from one host's
stack stays in another's), the known omissions (loaded, reaching a pair, flagged and not removed), the assumed-spell count,
the reach of rows with no size (assigned against candidate), the sensitivity that excludes hosts with unresolved ownership
(it drops exactly the hosts ownership.unresolved_ownership_hosts names), the late hosts and the shares of load, and the
tariff pairing. One test loads the shipped supplier_known_omissions.csv (under pipeline/, no price).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, influence  # noqa: E402
from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import prefreeze_summaries as pf  # noqa: E402
from pipeline.analysis import suppliers as sp  # noqa: E402
from test_matching_rules import COOP, FUEL, IOU, PUBLIC, ladder, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
MEMBER = "MEMBERSHIP_ONLY: the source shows membership, not that this supplier provided all or most of the unit's requirements."
D, A = "documented", "assumed"


def build(hosts, comps, **kw):
    treated, clean, q, regions, dd = world(hosts, comps)
    d = design.build(treated, clean, q, regions, FUEL, dd, **kw)
    d.gas = GAS
    return d, q


def mixed(first_id, n, start=10_050):
    states = ["AA", "AB", "BB", "BC"]
    return [(first_id + i, states[i % 4], start + 100 * i, COOP) for i in range(n)]


def suppliers(*specs):
    """specs: (id, state, supplier, kind, from, to, note[, from_basis, to_basis]) -> a table as suppliers.load returns it."""
    base = {"name": "x", "source_url": "https://example.org", "source_kind": "supplier_member_list", "quote": "q", "date_opened": "2026-11-18"}
    rows = []
    for s in specs:
        u, st, sup, k, lo, hi, note, *basis = s
        fb, tb = basis if basis else (A, A)
        rows.append({**base, "utility_id_eia": u, "state": st, "supplier": sup, "supplier_kind": k, "from_year": lo, "to_year": hi,
                     "from_year_basis": fb, "to_year_basis": tb, "note": note})
    return pd.DataFrame(rows, columns=list(sp.COLUMNS)).astype({"utility_id_eia": int, "from_year": int, "to_year": int})


def keys(d, i):
    return [tuple(k) for k in d.hosts.match_keys.iloc[i]]


# ---- rule 2.4: per host and match pair ------------------------------------------------------------------------------

def two_hosts():
    d, q = build([(1, "AA", 10_000, COOP), (2, "AA", 10_500, COOP)], mixed(10, 14))
    shared = [k for k in keys(d, 0) if k in set(keys(d, 1))]
    return d, shared


def test_a_membership_only_link_removes_the_match_from_that_hosts_stack_only_and_is_labelled():
    d, shared = two_hosts()
    x = shared[0]
    t = suppliers((1, "AA", "JAA", "joint_action_agency", 2001, 2025, MEMBER), (x[0], x[1], "JAA", "joint_action_agency", 2001, 2025, MEMBER),
                  (2, "AA", "G&T Two", "g_and_t_cooperative", 2001, 2025, ""))
    r = pf.supplier_exercise(d, t)
    det = r["detected_exclusions"]
    assert [(e["host"], e["match"]) for e in det] == [("1:AA", pf.label(x))]
    assert det[0]["rests_on_membership_alone"] is True and det[0]["rests_on_assumed_years"] is True
    assert det[0]["years"] == own_rules.window_years(2015)
    assert r["detected_exclusions_resting_on_membership_alone"] == det
    after = {e["host"]: e["matches_left"] for e in r["after_removal_no_rematching"]["matches_left_by_host"]}
    assert after == {"1:AA": 9, "2:AA": 10}                              # nothing rematched; host 2 keeps x
    e = pf.remove_pairs(d, {((1, "AA"), 2015): {x}})
    assert x not in keys(e, 0) and x in keys(e, 1) and keys(e, 1) == keys(d, 1)
    assert keys(e, 0) == [k for k in keys(d, 0) if k != x]               # order kept


def test_an_unknown_match_is_counted_and_kept():
    d, shared = two_hosts()
    x = shared[0]
    t = suppliers((1, "AA", "G&T One", "g_and_t_cooperative", 2001, 2025, ""), (x[0], x[1], "unknown", "unknown", 2001, 2025, ""))
    r = pf.supplier_exercise(d, t)
    assert r["detected_exclusions"] == []
    host1_unknown = [u for u in r["unknown_pairs"] if u["host"] == "1:AA"]
    assert len(host1_unknown) == 10 and pf.label(x) in [u["match"] for u in host1_unknown]   # rows missing count as unknown too
    assert all(u["match_unknown_years"] == own_rules.window_years(2015) for u in host1_unknown)
    assert r["counts"]["unknown_pairs_counted_not_removed"] == 20               # host 2 has no row: every pair unknown
    assert {e["host"]: e["matches_left"] for e in r["after_removal_no_rematching"]["matches_left_by_host"]} == {"1:AA": 10, "2:AA": 10}
    assert r["counts"]["pairs_that_could_be_tested_at_all"] == 0


def test_a_host_left_with_four_matches_is_named_and_kept_and_one_left_with_none_is_not_estimable():
    d, _ = build([(1, "AA", 10_000, COOP), (101, "AA", 30_000, COOP)], mixed(10, 12) + mixed(110, 12, start=30_050), k=5)
    m0, m1 = keys(d, 0), keys(d, 1)
    assert not set(m0) & set(m1)
    t = suppliers((1, "AA", "JAA", "joint_action_agency", 2001, 2025, ""), (m0[0][0], m0[0][1], "JAA", "joint_action_agency", 2001, 2025, ""),
                  (101, "AA", "G&T", "g_and_t_cooperative", 2001, 2025, ""),
                  *[(k[0], k[1], "G&T", "g_and_t_cooperative", 2001, 2025, "", D, D) for k in m1])
    r = pf.supplier_exercise(d, t)
    a = r["after_removal_no_rematching"]
    assert [x["host"] for x in a["hosts_with_fewer_than_five_matches_inadequate_support_kept"]] == ["1:AA"]
    assert a["hosts_with_fewer_than_five_matches_inadequate_support_kept"][0]["matches_left"] == 4
    assert [x["host"] for x in a["hosts_with_no_matches_not_estimable"]] == ["101:AA"]
    assert "1:AA" in a["the_estimate_is_over"] and "101:AA" not in a["the_estimate_is_over"]
    assert a["hosts_in_the_estimate_after_removal"] == 1
    doc = [x for x in r["detected_exclusions"] if x["host"] == "101:AA"]
    assert len(doc) == 5 and all(x["rests_on_assumed_years"] for x in doc)          # the host's own row is assumed at both ends


def test_a_removal_with_documented_rows_on_both_sides_does_not_rest_on_assumed_years():
    d, shared = two_hosts()
    x = shared[0]
    t = suppliers((1, "AA", "JAA", "joint_action_agency", 2001, 2025, "", D, A), (x[0], x[1], "JAA", "joint_action_agency", 2009, 2025, "", D, A))
    det = pf.supplier_exercise(d, t)["detected_exclusions"]
    assert det[0]["years_documented_on_both_sides"] == [] and det[0]["rests_on_assumed_years"]     # 2001 and 2009 differ
    t = suppliers((1, "AA", "JAA", "joint_action_agency", 2009, 2025, "", D, A), (x[0], x[1], "JAA", "joint_action_agency", 2009, 2025, "", D, A))
    det = pf.supplier_exercise(d, t)["detected_exclusions"]
    assert det[0]["years_documented_on_both_sides"] == [2009] and not det[0]["rests_on_assumed_years"]


# ---- the known omissions -------------------------------------------------------------------------------------------

def omissions(*rows):
    return pd.DataFrame([dict(zip(pf.OMISSION_COLUMNS, r)) for r in rows], columns=list(pf.OMISSION_COLUMNS))


def test_an_alias_reaches_a_pair_and_flags_it_unresolved_without_removing_it():
    d, shared = two_hosts()
    x = shared[0]
    t = suppliers((1, "AA", "Name One", "g_and_t_cooperative", 2001, 2025, ""), (x[0], x[1], "Name Two", "federal_pma", 2012, 2025, ""))
    om = omissions(("", "Name One | Name Two", "alias", "e", "f", "2026-11-19", ""))
    r = pf.supplier_exercise(d, t, om)
    assert r["detected_exclusions"] == []
    reached = r["known_omissions_reaching_this_design"]
    assert [(z["host"], z["match"], z["status"]) for z in reached] == [("1:AA", pf.label(x), pf.UNRESOLVED)]
    assert reached[0]["years"] == list(range(2012, 2019))
    assert r["counts"]["pairs_unresolved_by_this_exercise"] == 1
    assert {e["host"]: e["matches_left"] for e in r["after_removal_no_rematching"]["matches_left_by_host"]}["1:AA"] == 10


def test_a_pair_omission_reaches_only_its_own_pair_in_either_order():
    pairs = [((1, "AA"), 2015, (5, "AA")), ((2, "AA"), 2015, (5, "AA")), ((5, "AA"), 2015, (1, "AA"))]
    om = omissions(("1:AA", "5:AA", "system_agreement", "e", "f", "2026-11-19", ""))
    got = pf.omission_pairs(om, pairs, suppliers())
    assert [(z["host"], z["match"]) for z in got] == [("1:AA", "5:AA"), ("5:AA", "1:AA")]


def test_the_omissions_loader_checks_its_rows(tmp_path):
    p = tmp_path / "o.csv"
    good = dict(zip(pf.OMISSION_COLUMNS, ("1:AA", "5:AA", "system_agreement", "evidence", "file line 1", "2026-11-19", "")))
    pd.DataFrame([good]).to_csv(p, index=False)
    assert len(pf.load_known_omissions(p)) == 1
    for bad, msg in (({"kind": "rumour"}, "kind"), ({"evidence": ""}, "evidence"), ({"entered": "soon"}, "entered"),
                     ({"kind": "alias"}, "alias")):
        pd.DataFrame([{**good, **bad}]).to_csv(p, index=False)
        with pytest.raises(ValueError, match=msg):
            pf.load_known_omissions(p)


def test_the_shipped_list_of_known_omissions_is_dated_and_unamended():
    t = pf.load_known_omissions()
    assert set(t.entered) == {"2026-11-19"} and set(t.amended) == {""}
    assert ("17166:NV", "13407:NV", "system_agreement") in set(zip(t.host, t.match_or_unit, t.kind))
    names = set(sp.load().supplier.str.strip())
    for r in t[t.kind == "alias"].itertuples():                       # alias names are spelled exactly as the supplier table has them
        assert set(s.strip() for s in r.match_or_unit.split(pf.ALIAS_SEPARATOR)) <= names


# ---- the assumed-spell count ---------------------------------------------------------------------------------------

def own_table(*specs):
    base = {"name": "x", "how_it_changed": "", "source_url": "https://example.org", "source_kind": "sec_filing", "quote": "q", "date_opened": "2026-11-18"}
    t = pd.DataFrame([{**base, "utility_id_eia": u, "state": st, "ultimate_parent": p, "from_year": lo, "to_year": hi, "from_year_basis": fb,
                       "to_year_basis": tb} for u, st, p, lo, hi, fb, tb in specs], columns=own_rules.COLUMNS + list(own_rules.BASIS))
    return t.astype({"utility_id_eia": int, "from_year": int, "to_year": int})


def test_the_assumed_spell_count_classes_each_selected_unit_by_its_weakest_window_basis():
    comps = ladder(30, 4, own=IOU) + ladder(50, 8, own=PUBLIC, start=10_075)
    t = own_table((1, "", "P1", 2001, 2025, D, D), (30, "", "O30", 2001, 2025, A, A), (31, "", "O31", 2005, 2025, D, A),
                  (32, "", "O32", 2001, 2025, D, D))                        # 33 has no row: rule 2.2 keeps it from an IOU host
    d, q = build([(1, "AA", 10_000, IOU)], comps, ownership=t)
    chosen = set(keys(d, 0))
    assert (33, "AA") not in chosen and {(30, "AA"), (31, "AA"), (32, "AA")} <= chosen
    r = pf.assumed_spell_count(d, t, ps.ownership_classes(q))
    assert [u["match"] for u in r["units_relying_on_a_spell_assumed_at_both_ends"]] == ["30:AA"]
    assert [u["match"] for u in r["units_relying_on_a_spell_assumed_at_one_end_and_none_at_both"]] == ["31:AA"]
    assert [u["match"] for u in r["units_documented_at_both_ends_throughout"]] == ["32:AA"]
    assert r["units_by_weakest_basis"]["no_row_own_owner_by_convention"] == 7 and r["selected_comparison_units"] == 10
    assert r["investor_owned_host_and_investor_owned_match_pairs"] == 3 and r["of_which_with_a_row_in_every_window_year"] == 3
    assert r["units_relying_on_a_spell_assumed_at_both_ends"][0]["serves"] == [{"host": "1:AA", "cohort": 2015, "basis": "assumed_at_both_ends"}]


def test_a_partly_covered_investor_owned_match_is_listed_with_its_uncovered_years():
    comps = ladder(30, 2, own=IOU) + ladder(50, 9, own=PUBLIC, start=10_075)
    t = own_table((1, "", "P1", 2001, 2025, D, D), (30, "", "O30", 2012, 2025, D, A), (31, "", "O31", 2001, 2025, A, D))
    # Rule 2.2 read year by year (Joe, 2026-11-19, D-107): the matching itself now bars 30:AA, so the check finds no pair.
    # Until then this test built the design with the bar applied only to a unit with no row in any window year.
    d, q = build([(1, "AA", 10_000, IOU)], comps, ownership=t)
    assert (30, "AA") not in [tuple(k) for k in d.hosts.match_keys.iloc[0]]
    assert {"utility": "30:AA", "why": own_rules.NO_ROW} in d.hosts.excluded_from_its_pool.iloc[0]
    r = pf.assumed_spell_count(d, t, ps.ownership_classes(q))
    assert r["investor_owned_pairs_with_an_uncovered_window_year"] == []
    assert r["of_which_with_a_row_in_every_window_year"] == 1
    # The check still lists such a pair where the bar is not applied (rule 2.3's labelled sensitivity skips rule 2.2's bar)
    d, q = build([(1, "AA", 10_000, IOU)], comps, ownership=t, affiliates_included=True)
    r = pf.assumed_spell_count(d, t, ps.ownership_classes(q))
    gap = r["investor_owned_pairs_with_an_uncovered_window_year"]
    assert [(g["match"], g["window_years_without_a_row"]) for g in gap] == [("30:AA", [2009, 2010, 2011])]
    assert r["of_which_with_a_row_in_every_window_year"] == 1


# ---- rows with no size ---------------------------------------------------------------------------------------------

def test_unsized_reach_counts_assigned_and_candidate_rows_and_their_net_weight():
    fac = pd.DataFrame([("f1", "AA", None, 10.0, "10;11", False), ("f2", "AA", None, 11.0, "11", False),
                        ("f3", "AA", 5.0, 12.0, "12", True), ("f4", "BB", None, 10.0, "10", False),
                        ("f5", "AA", None, 1.0, "1;13", False), ("f6", "AA", None, None, "13", False)],
                       columns=["fid", "state", "mw_full", "utility_id_eia", "utility_candidates", "in_dose"])
    d = SimpleNamespace(hosts=pd.DataFrame({"key": [(1, "AA"), (2, "AA")], "match_keys": [[(10, "AA"), (12, "AA")], [(10, "AA"), (13, "AA")]]}))
    net = {(10, "AA"): 0.5, (12, "AA"): 0.25, (13, "AA"): 0.25}
    r = pf.unsized_reach(fac, d, net)
    assert r["rows_with_no_size"] == 5 and r["comparison_units_in_the_design"] == 3
    by = {x["unit"]: x for x in r["reached_comparison_units"]}
    assert set(by) == {"10:AA", "13:AA"}                                   # 12:AA's only row (f3) has a size
    assert (by["10:AA"]["rows_assigned"], by["10:AA"]["rows_as_a_candidate"]) == (1, 1)    # f4 is in another state
    assert (by["13:AA"]["rows_assigned"], by["13:AA"]["rows_as_a_candidate_not_assigned"]) == (0, 2)
    assert by["10:AA"]["serves"] == ["1:AA", "2:AA"] and by["10:AA"]["share_of_the_comparison_sides_net_weight"] == 0.5
    assert r["comparison_units_reached_as_the_assigned_utility"] == 1 and r["comparison_units_reached_as_a_candidate_only"] == 1
    assert r["share_of_comparison_net_weight_reached"] == 0.75
    hosts = {x["unit"]: x for x in r["hosts"]}
    assert hosts["1:AA"]["rows_assigned"] == 1 and hosts["2:AA"]["rows_assigned_or_candidate"] == 0


# ---- the sensitivity excluding hosts with unresolved ownership -----------------------------------------------------

def test_the_sensitivity_drops_exactly_the_hosts_unresolved_ownership_hosts_names():
    from test_ownership_unresolved import build as build_rules, two_host_world
    w = two_host_world()
    head, sens = build_rules(ps.HEADLINE_RULES, w), build_rules(ps.UNRESOLVED_OWNERSHIP_EXCLUDED, w)
    treated, clean, q, regions, dd, t, usable = w
    named = own_rules.unresolved_ownership_hosts(t, [(tuple(k), int(g)) for k, g in zip(head.hosts.key, head.hosts.cohort)],
                                                 ps.ownership_classes(q))
    r = pf.unresolved_ownership_sensitivity(head, sens)
    assert [x["host"] for x in r["hosts_excluded"]] == [pf.label(k) for k in named] == ["1:AA"]
    assert r["hosts_excluded"][0]["years"] == named[(1, "AA")]["years"]
    assert [x["host"] for x in r["remaining"]] == ["2:AA"] and r["every_remaining_hosts_matches_unchanged"]
    assert r["hosts_under_the_headline_rules"] == 2 and r["hosts_remaining"] == 1
    assert isinstance(r["fit_estimable_by_the_rank_test"], bool)
    assert [s["host"] for s in r["support_of_the_remaining_hosts"]] == ["2:AA"]


# ---- figures of open item 13 ----------------------------------------------------------------------------------------

def test_late_hosts_and_the_four_shares_of_load():
    rows = []
    for (u, first, mw) in ((1, 2008, 50.0), (2, 2015, 30.0), (3, 2024, 15.0), (4, None, 5.0)):
        for y in range(2001, 2026):
            dose = 0.03 if first is not None and y >= first else 0.001
            rows.append((u, "AA", y, dose, mw if y == 2025 else 0.0))
    dose = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "dose", "dc_mw"])
    r = pf.late_hosts_and_shares(dose, 0.02, {(2, "AA")})
    assert r["counts"] == {"long_time_hosts": 1, "cohort_utilities": 1, "headline_set": 1, "late_hosts": 1}
    assert r["late_hosts"] == ["3:AA"] and r["late_hosts_first_crossing"] == {"3:AA": 2024}
    s = r["shares_of_the_years_data_center_load"]
    assert s == {"long_time_hosts": 0.5, "cohort_utilities": 0.3, "headline_set": 0.3, "late_hosts": 0.15,
                 "remainder_never_reaching_the_threshold": 0.05}


def test_tariff_pairing_names_a_cohort_utility_with_no_comparison():
    sample = pd.DataFrame({"host_id": [1, 2], "state": ["AA", "AA"], "comparison_id": [9.0, float("nan")]})
    r = pf.tariff_pairing(sample, {(1, "AA"): "One", (2, "AA"): "Two", (3, "AA"): "Three"})
    assert not r["every_cohort_utility_paired"] and r["cohort_utilities_paired"] == 1
    assert [(u["utility"], u["in_the_sample_without_a_comparison"]) for u in r["unpaired"]] == [("2:AA", True), ("3:AA", False)]


def g12_record():
    """An invented record with the fields of data/frozen/g12_mean_estimate_nothing_planted.json that the carrier reads."""
    def fig(named, m2, m1, s2, s1, e2, e1):
        mean = lambda v, n: {"datasets": n, "datasets_used": n, "percent": {"mean_estimate": v, "interval_of_the_mean_95": [v - 1, v + 1]}}  # noqa: E731
        rp = lambda sl, e, n, src: {"source": src, "datasets_used": n, "slope_of_the_estimate_on_the_realised_change": sl,  # noqa: E731
                                    "root_mean_square_error_log_points": e}
        return {"is_the_named_figure": named, "stage2_20000_datasets": mean(m2, 20), "stage1_2000_datasets": mean(m1, 2),
                "realised_path": {"stage2_recomputed": rp(s2, e2, 20, "recomputed"), "stage1_stored": rp(s1, e1, 2, "stored")}}
    return {"figures": {"G12_fuel_shocks_not_linear_in_the_share": fig(True, 0.5, -0.25, -0.3, -0.2, 0.01, 0.02),
                        "G11_fuel_shocks_linear_in_the_share": fig(False, 0.125, 0.75, 0.4, 0.6, 0.03, 0.04)}}


def test_the_g12_diagnostics_are_carried_with_their_sources_and_units_and_carry_no_verdict():
    r = pf.g12_descriptive_diagnostics(g12_record())
    assert set(r["processes"]) == {"G12", "G11"}
    g12, g11 = r["processes"]["G12"], r["processes"]["G11"]
    assert g12["is_the_named_figure"] is True and g11["is_the_named_figure"] is False
    # known answers: the mean as the record gives it in percent, the slope unchanged, the error as 100 times log points
    assert g12["by_stage"]["stage2"]["mean_estimate_pct"] == 0.5 and g12["by_stage"]["stage1"]["mean_estimate_pct"] == -0.25
    assert g12["by_stage"]["stage2"]["slope_of_the_estimate_on_the_realised_change"] == -0.3
    assert g12["by_stage"]["stage1"]["slope_of_the_estimate_on_the_realised_change"] == -0.2
    assert g12["by_stage"]["stage2"]["root_mean_square_error_pct"] == pytest.approx(1.0, abs=1e-12)
    assert g12["by_stage"]["stage1"]["root_mean_square_error_pct"] == pytest.approx(2.0, abs=1e-12)
    assert g11["by_stage"]["stage2"]["slope_of_the_estimate_on_the_realised_change"] == 0.4
    assert g11["by_stage"]["stage1"]["root_mean_square_error_pct"] == pytest.approx(4.0, abs=1e-12)
    # each figure names its source, and stage 2's and stage 1's sources are different fields of the record
    s2, s1 = g12["by_stage"]["stage2"], g12["by_stage"]["stage1"]
    assert s2["slope_and_error_source"].endswith("realised_path.stage2_recomputed") and s2["slope_and_error_source_as_the_record_states_it"] == "recomputed"
    assert s1["slope_and_error_source"].endswith("realised_path.stage1_stored") and s1["slope_and_error_source_as_the_record_states_it"] == "stored"
    assert pf.G12_RECORD_NAME in s2["mean_source"] and "percent" in s2["mean_source"]
    assert set(r["units"]) == {"mean_estimate_pct", "slope_of_the_estimate_on_the_realised_change", "root_mean_square_error_pct"}
    assert "no unit" in r["units"]["slope_of_the_estimate_on_the_realised_change"]
    # the statement is Joe's of 2026-11-20 and nothing in the output is a verdict or a threshold
    assert "zero in expectation under the construction and cannot establish adequacy" in r["statement"]
    assert "descriptive diagnostics, not a new validation verdict or selection criterion" in r["statement"]
    assert "would not necessarily identify a failure" in r["statement"]
    flat = repr(r).lower()
    for bad in ("verdict\": ", "passes", "adequate\"", "threshold_", "is a failure of the adjustment"):
        assert bad not in flat, bad


def test_the_g12_diagnostics_derive_nothing_for_a_figure_the_record_lacks():
    doc = g12_record()
    del doc["figures"]["G11_fuel_shocks_linear_in_the_share"]["realised_path"]["stage2_recomputed"]
    with pytest.raises(KeyError):
        pf.g12_descriptive_diagnostics(doc)


def test_the_module_never_opens_an_outcome():
    src = Path(pf.__file__).read_text()
    for bad in ("load_outcomes", "read_listed_outcomes", "'blind'", '"blind"', '"availability"', "DECISIONS.md", "run_availability"):
        assert bad not in src, bad
