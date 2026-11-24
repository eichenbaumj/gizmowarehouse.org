"""Assignment evidence (docs/DECISIONS.md, D-46 ruling 4 as amended; D-48). Load and sales only; no price is read."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import assignment as asg  # noqa: E402

UNITS = pd.MultiIndex.from_tuples([(1, "AA"), (2, "AA"), (3, "AA"), (9, "TX")], names=asg.KEY)
BASE = pd.Series([1000.0, 1000.0, 1000.0, 1000.0], index=UNITS)          # 2% is 20 GWh, 0.5% is 5 GWh


def inventory():
    """Four sites. s1 verified on utility 1; s2 placed by the map on 1 with 2 as another candidate; s3 in one territory (3); s4 in Texas."""
    fac = pd.DataFrame({
        "fid": ["s1", "s2", "s3", "s4"], "state": ["AA", "AA", "AA", "TX"],
        "utility_assign": ["verified_by_hand", "smallest_polygon", "unique", "unique"],
        "utility_candidates": ["1;2", "1;2", "3", "9"], "state_scale": [1.0, 2.0, 1.0, 1.0]}).set_index("fid")
    rows = []
    for fid, u, st, start, mw in (("s1", 1, "AA", 2012, 1.5), ("s2", 1, "AA", 2015, 2.0), ("s3", 3, "AA", 2014, 3.0), ("s4", 9, "TX", 2013, 3.0)):
        rows += [(fid, u, st, y, mw) for y in asg.YEARS if y >= start]
    return fac, pd.DataFrame(rows, columns=["fid"] + asg.KEY + ["year", "mw"])


def test_a_site_is_resolved_if_verified_or_alone_in_a_territory_outside_ercot():
    fac, _ = inventory()
    res = asg.resolved(fac, ercot_units={(9, "TX")})
    assert res.to_dict() == {"s1": True, "s2": False, "s3": True, "s4": False}      # one territory does not resolve a site inside ERCOT
    assert asg.resolved(fac, ercot_units=set())["s4"]                                 # the same site outside ERCOT would be resolved
    off = fac.assign(utility_assign=["wholesale_direct", "behind_the_meter", "ercot_wires_outside_panel", "fallback_largest_flagged"])
    assert list(asg.resolved(off, set())) == [True, True, True, False]


def test_the_lower_case_takes_unresolved_sites_off_and_the_upper_case_counts_them_on_every_candidate():
    fac, fy = inventory()
    m = asg.matrices(fy, fac, UNITS, asg.resolved(fac, {(9, "TX")}))
    gwh = lambda mw: mw * 8.76  # noqa: E731
    assert m["as_built"].loc[(1, "AA"), 2016] == pytest.approx(gwh(3.5))
    assert m["lower_as_built"].loc[(1, "AA"), 2016] == pytest.approx(gwh(1.5))        # s2 is unresolved and comes off
    assert m["upper_as_built"].loc[(1, "AA"), 2016] == pytest.approx(gwh(3.5))        # it is already on utility 1: counted once
    assert m["upper_as_built"].loc[(2, "AA"), 2016] == pytest.approx(gwh(2.0))        # and is counted on its other candidate too
    assert m["upper_as_built"].loc[(2, "AA"), 2013] == 0.0                            # s1 is verified: it enters no one else's upper case
    assert m["no_anchoring"].loc[(1, "AA"), 2016] == pytest.approx(gwh(1.5 + 1.0))    # s2's estimate with the state factor of 2 taken off
    assert m["upper_no_anchoring"].loc[(2, "AA"), 2016] == pytest.approx(gwh(1.0))
    assert m["lower_as_built"].loc[(9, "TX")].sum() == 0.0                            # every map-placed Texas site in ERCOT comes off
    assert m["upper_as_built"].loc[(3, "AA")].equals(m["as_built"].loc[(3, "AA")])     # a resolved site moves in neither case


def test_a_cohort_host_has_to_hold_in_all_four_cases():
    years = dict.fromkeys(asg.CASES, 2015.0)
    assert asg.verdict("cohort", 2015.0, years, {}) == "keeps its place"
    assert asg.verdict("cohort", 2015.0, {**years, "upper_no_anchoring": 2014.0}, {}) == "keeps its place"     # one year is inside the tolerance
    assert "lower as built" in asg.verdict("cohort", 2015.0, {**years, "lower_as_built": np.nan}, {})
    assert "upper no anchoring: first crossing 2009" in asg.verdict("cohort", 2015.0, {**years, "upper_no_anchoring": 2009.0}, {})
    assert asg.verdict("early", 2008.0, dict.fromkeys(asg.CASES, 2005.0), {}) == "keeps its place"
    assert "not before 2011" in asg.verdict("early", 2008.0, {**dict.fromkeys(asg.CASES, 2005.0), "lower_as_built": 2013.0}, {})


def test_a_comparison_utility_is_judged_on_its_upper_case_only():
    shares = {"upper_as_built": 0.004, "upper_no_anchoring": 0.0049}
    assert asg.verdict("comparison", np.nan, {}, shares) == "keeps its place"
    assert "upper no anchoring" in asg.verdict("comparison", np.nan, {}, {**shares, "upper_no_anchoring": 0.006})
    assert asg.verdict("late", 2024.0, {}, {}) == "not tested"


def test_end_to_end_on_the_made_up_inventory():
    fac, fy = inventory()
    regions = pd.Series(["West", "West", "West", "ERCOT"], index=UNITS)
    t, m, res = asg.evaluate(fac, fy, UNITS, BASE, regions, thresholds=(0.02,))
    # Utility 1: 13 GWh from the verified site, 30.7 with the unresolved one. It crosses 2% in 2015 as built and never in the lower case.
    assert t.at[(1, "AA"), "as_built_2%"] == 2015 and np.isnan(t.at[(1, "AA"), "lower_as_built_2%"])
    # Utility 2 has no site of its own, and the unresolved site that could be its would put it over 0.5%.
    assert t.at[(2, "AA"), "max_share_as_built"] == 0.0 and t.at[(2, "AA"), "max_share_upper_as_built"] == pytest.approx(2.0 * 8.76 / 1000)
    assert asg.verdict("comparison", np.nan, {}, {c: t.at[(2, "AA"), f"max_share_{c}"] for c in ("upper_as_built", "upper_no_anchoring")}).startswith("upper as built")
    assert t.at[(1, "AA"), "unresolved_sites_on_it"] == 1 and t.at[(3, "AA"), "unresolved_sites_on_it"] == 0


def test_the_largest_sites_in_the_crossing_year_are_the_worklist():
    _, fy = inventory()
    assert asg.determining_sites(fy, (1, "AA"), 2015, 20.0) == ["s2", "s1"]            # largest first, until the threshold is reached
    assert asg.determining_sites(fy, (1, "AA"), 2015, 10.0) == ["s2"]


FROZEN = ROOT / "data" / "frozen"


# The bounds' step D lists that can take a host the assignment table keeps out of every_cohort_utility (treatment_bounds
# .step_d_reasons). Named explicitly so that a difference with any other cause fails.
STEP_D_LISTS = ("step_d_does_not_keep_its_place_within_its_dates", "step_d_unsettled", "step_d_open_below_only",
                "step_d_fails_only_jointly_with_its_unresolved_sites", "step_d_unresolved_by_a_stress_scenario",
                "unknown_load_unsettled")


def holds_disagreements(a: dict, b: dict) -> list[str]:
    """Where the assignment table and the bounds report disagree on who holds, beyond what step D explains.

    Before step D the two were EQUAL: both were ruling 4 on the same inventory. From step D the assignment table is still
    ruling 4 alone, on the rebuilt inventory at its convention dates, while the bounds also apply step D's place test
    (dated intervals, the crossed screen, the joint case of an unresolved row across its interval, stress scenarios,
    unknown load), which can only take hosts OUT. So the bounds' set must be a subset of the table's, and every host in
    the difference must be on one of the bounds' step D lists.
    """
    out = []
    for t in ("2%", "5%"):
        holds = {h["utility"] for h in a["thresholds"][t]["hosts"] if h["verdict"] == "keeps its place"}
        left = {x["utility"] for x in b["thresholds"][t]["sets"]["every_cohort_utility"]["left"]}
        lists = b["thresholds"][t]["lists"]
        on_step_d = set().union(*(set(lists.get(n, [])) for n in STEP_D_LISTS))
        out += [f"{u} at {t}: the bounds keep it and the assignment table does not" for u in sorted(left - holds)]
        out += [f"{u} at {t}: out of the bounds on no step D list" for u in sorted((holds - left) - on_step_d)]
    return out


def test_the_holds_check_fails_both_ways_on_invented_reports():
    a = {"thresholds": {t: {"hosts": [{"utility": "1:AA", "verdict": "keeps its place"},
                                      {"utility": "2:AA", "verdict": "keeps its place"}]} for t in ("2%", "5%")}}

    def b(left, lists):
        return {"thresholds": {t: {"sets": {"every_cohort_utility": {"left": [{"utility": u} for u in left]}},
                                   "lists": lists} for t in ("2%", "5%")}}
    assert holds_disagreements(a, b(["1:AA"], {"step_d_fails_only_jointly_with_its_unresolved_sites": ["2:AA"]})) == []
    assert holds_disagreements(a, b(["1:AA", "2:AA", "3:AA"], {})) == [
        "3:AA at 2%: the bounds keep it and the assignment table does not",
        "3:AA at 5%: the bounds keep it and the assignment table does not"]
    assert holds_disagreements(a, b(["1:AA"], {"unsettled_on_assignment_under_ruling_4": ["2:AA"]})) == [
        "2:AA at 2%: out of the bounds on no step D list", "2:AA at 5%: out of the bounds on no step D list"]


@pytest.mark.skipif(not (FROZEN / "assignment_evidence.json").exists(), reason="assignment.py has not been run")
def test_the_frozen_table_and_the_bounds_report_agree_on_who_holds():
    a = json.loads((FROZEN / "assignment_evidence.json").read_text())
    b = json.loads((FROZEN / "treatment_bounds.json").read_text())
    assert holds_disagreements(a, b) == []
    s = a["sites"]
    assert s["resolved"] + s["unresolved"] == s["all"]
    sites = pd.read_csv(FROZEN / "assignment_evidence_sites.csv")
    assert not sites[sites.how_placed.isin(asg.VERIFIED)].resolved.eq(False).any()     # a site verified by hand is never listed as unresolved


VERIFIED_DIR = ROOT / "pipeline" / "facilities" / "verified"


def test_every_assignment_verification_records_its_kind_its_period_and_who_opened_it():
    kinds = {"site statement", "territory listing", "local map with a utility page", "permit record"}
    files = sorted(VERIFIED_DIR.glob("batch_v_*.json"))
    assert files
    for f in files:
        for r in json.loads(f.read_text()):
            assert r["group"] == "assign" and r["utility_evidence_kind"] in kinds, (f.name, r["fid"])
            assert r["utility_evidence_period"] and r["utility_source_url"].startswith("http") and r["opened_by_session_model"]
            assert r["utility_confidence"] in ("high", "medium")
            if r["utility_evidence_kind"] == "territory listing":                       # D-48: never in Texas
                assert r["state"] != "TX", r["fid"]


@pytest.mark.skipif(not (FROZEN / "ten_year_screen.json").exists(), reason="ten_year.py has not been run")
def test_the_ten_year_material_agrees_with_the_frozen_sets():
    r = json.loads((FROZEN / "ten_year_screen.json").read_text())
    head = pd.read_csv(FROZEN / "headline_set.csv")
    for t in ("2%", "5%"):
        h = head[head.threshold == t]
        x = r["thresholds"][t]["headline_set"]
        assert x["hosts"] == int(h.in_headline_set.sum())
        assert x["left_if_the_ten_year_case_were_also_a_screen"] == int(h.in_set_with_the_ten_year_case.sum())   # the side set, computed a second way
        c = r["thresholds"][t]["comparison_utilities"]
        assert c["no_longer_under_0.5pct_at_3_years_earlier"] <= c["no_longer_under_0.5pct_at_5_years_earlier"] <= c["no_longer_under_0.5pct_at_10_years_earlier"]
    sites = r["headline_hosts_permit_dated_sites_of_20_mw_or_more"]
    assert all(s["mw"] >= 20 for s in sites)
    assert not set(s["host"] for s in sites) & set(r["headline_hosts_with_none"])
