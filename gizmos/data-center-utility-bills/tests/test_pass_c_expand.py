"""The broader expansion test of the verification pass (docs/DECISIONS.md, D-61 sections 4 and 5; D-46 ruling 4 as amended).

Load and sales only; no price is read. Every test but the last two works on a small made-up inventory, so none depends on
the real one. The last two rebuild the real inventory on scratch copies with no corrections and check that the rebuild
reproduces data/interim/facility_year.parquet and data/interim/state_anchor.parquet; they skip if those files are absent.
"""
import dataclasses
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import buildout  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

YEARS = asg.YEARS
AA_EPRI = 0.03504            # AA's permit-based 2024 total is 8 MW raw = 0.07008 TWh, so the frozen factor is 0.5
BB_EPOCH_MW = 5.0


def world(raw: dict | None = None) -> px.Inputs:
    """A made-up inventory in two states.

    AA, three permit-based sites, state factor 0.5:
      p1  4 MW raw (2 scaled), from 2012, verified on utility 1
      p2  2 MW raw (1 scaled), from 2015, placed on utility 1 by the map, utility 2 another candidate (unresolved)
      p3  2 MW raw (1 scaled), from 2016, alone in utility 3's territory (resolved)
    BB, factor 1:
      e1  an Epoch site on utility 4, 5 MW from 2018 (a measured history)
      ph  a permit site on utility 4 with a verified phased history, half in 2010 and the rest in 2020
    Utility 1's 2% threshold is 2.5 MW, so p1 alone (2 MW) never reaches it and with p2 it does in 2016.
    Utility 3's 2% threshold is 0.8 MW, so p3 crosses in the third year of its ramp.
    """
    phases = {"ph": [(2010, 0.5), (2020, 1.0)]}
    fac = pd.DataFrame({
        "fid": ["p1", "p2", "p3", "e1", "ph"],
        "state": ["AA", "AA", "AA", "BB", "BB"],
        "src": ["bi", "bi", "bi", "epoch", "bi"],
        "load_history": ["three_year_ramp", "three_year_ramp", "three_year_ramp", "epoch_timeline", "verified_phases"],
        "mw_basis": ["generator_capacity_x_kappa"] * 3 + ["epoch_timeline", "generator_capacity_x_kappa"],
        "energized_year": [2012.0, 2015.0, 2016.0, 2018.0, 2010.0],
        "mw_full_raw": [4.0, 2.0, 2.0, BB_EPOCH_MW, 4.0],
        "state_scale": [0.5, 0.5, 0.5, 1.0, 1.0],
        "utility_id_eia": [1.0, 1.0, 3.0, 4.0, 4.0],
        "utility_assign": ["verified_by_hand", "smallest_polygon", "unique", "verified_by_hand", "unique"],
        "utility_candidates": ["1", "1;2", "3", "4", "4"],
        "is_crypto": [False] * 5,
    }).set_index("fid")
    for fid, mw in (raw or {}).items():
        fac.loc[fid, "mw_full_raw"] = mw
    aa_permit_twh = fac.mw_full_raw[["p1", "p2", "p3"]].sum() * 8.76 / 1000
    fac["mw_full"] = fac.mw_full_raw * fac.state_scale
    fac["in_dose"] = True
    rows = []
    for fid, r in fac.iterrows():
        for y in YEARS:
            if fid == "e1":
                mw = BB_EPOCH_MW if y >= 2018 else 0.0
            elif fid == "ph":
                mw = buildout.phased_mw(r.mw_full, phases["ph"], y)
            else:
                mw = buildout.ramp_mw(r.mw_full, r.energized_year, y)
            if mw > 0:
                rows.append((fid, int(r.utility_id_eia), r.state, y, mw))
    fy = pd.DataFrame(rows, columns=["fid"] + asg.KEY + ["year", "mw"])
    units = pd.MultiIndex.from_tuples([(1, "AA"), (2, "AA"), (3, "AA"), (4, "BB")], names=asg.KEY)
    base = pd.Series([2.5 * 8.76 / 0.02, 1000.0, 0.8 * 8.76 / 0.02, 1000.0], index=units)
    regions = pd.Series("West", index=units)
    names = pd.Series(["One", "Two", "Three", "Four"], index=units)
    anchor = pd.DataFrame({"epri_twh": [0.5 * aa_permit_twh, 0.03504 + BB_EPOCH_MW * 8.76 / 1000],
                           "permit_twh": [aa_permit_twh, 4 * 8.76 / 1000],
                           "epoch_twh": [0.0, BB_EPOCH_MW * 8.76 / 1000]}, index=["AA", "BB"])
    anchor["factor"] = [0.5, 1.0]
    return px.Inputs.build(fac, fy, units, base, regions, names, anchor, phases, frozen_2024_mw={"e1": BB_EPOCH_MW})


def row(res, uid, st):
    return next(r for r in res["utilities"] if r["utility"] == f"{uid}:{st}")


def site_rows(fy, fid):
    return fy[fy.fid == fid].set_index("year").mw


# ---- the scratch rebuild ------------------------------------------------------------------------------------------

def test_no_corrections_changes_nothing():
    inp = world()
    fac, fy, factor = px.scratch_state(inp, {}, "AA", {})
    assert factor == pytest.approx(0.5)
    pd.testing.assert_frame_equal(fy.sort_values(["fid", "year"]).reset_index(drop=True),
                                  inp.fy[inp.fy.state == "AA"].sort_values(["fid", "year"]).reset_index(drop=True))
    res = px.expand([], inputs=inp)
    assert res["utilities"] == [] and res["states"] == {}


def test_an_assignment_move_touches_both_utilities():
    inp = world()
    res = px.expand([{"fid": "p2", "kind": "assign", "to": [2, "AA"]}], inputs=inp)
    touched = {r["utility"] for r in res["utilities"]}
    assert {"1:AA", "2:AA"} <= touched and "3:AA" not in touched
    one, two = row(res, 1, "AA"), row(res, 2, "AA")
    assert one["original"]["crossing"] == 2016 and one["reference"]["crossing"] == "never"
    assert one["reference_differs_from_original"]
    # Utility 2 carried nothing (a comparison utility failing its upper case); with p2 on it, it is over 0.5%.
    assert two["original"]["place"] == "comparison" and two["original"]["verdict"].startswith("upper as built")
    assert two["reference"]["place"] == "neither"
    _, fy, _ = px.scratch_state(inp, px.parse_corrections([{"fid": "p2", "kind": "assign", "to": [2, "AA"]}], inp), "AA", {})
    assert set(fy[fy.fid == "p2"].utility_id_eia) == {2}


def test_moving_a_site_between_utilities_of_one_state_leaves_the_factor_alone():
    inp = world()
    res = px.expand([{"fid": "p2", "kind": "assign", "to": "off_panel"}], inputs=inp)
    assert "AA" not in res["states"] or not res["states"]["AA"]["factor_changes"]


def test_narrowing_changes_the_upper_case_only():
    inp = world()
    inp.fac.loc["p2", "utility_candidates"] = "1;2;3"
    corr = px.parse_corrections([{"fid": "p2", "kind": "narrow", "candidates": [1, 2]}], inp)
    fac0, fy0, _ = px.scratch_state(inp, {}, "AA", {})
    fac1, fy1, _ = px.scratch_state(inp, corr, "AA", {})
    u = inp.units[inp.units.get_level_values("state") == "AA"]
    t0, m0, r0 = asg.evaluate(fac0, fy0, u, inp.base.reindex(u), inp.regions.reindex(u), thresholds=(0.02,))
    t1, m1, r1 = asg.evaluate(fac1, fy1, u, inp.base.reindex(u), inp.regions.reindex(u), thresholds=(0.02,))
    assert not r1["p2"]                                                                     # it stays unresolved
    assert m1["upper_as_built"].loc[(3, "AA")].sum() < m0["upper_as_built"].loc[(3, "AA")].sum()
    for name in ("as_built", "no_anchoring", "lower_as_built", "lower_no_anchoring"):
        pd.testing.assert_frame_equal(m0[name], m1[name])
    pd.testing.assert_series_equal(m0["upper_as_built"].loc[(2, "AA")], m1["upper_as_built"].loc[(2, "AA")])
    res = px.expand([{"fid": "p2", "kind": "narrow", "candidates": [1, 2]}], inputs=inp)
    assert {"1:AA", "2:AA", "3:AA"} <= {r["utility"] for r in res["utilities"]}            # was a candidate of 3: touched


def test_a_narrowed_list_has_to_keep_the_utility_the_site_is_on():
    inp = world()
    with pytest.raises(ValueError, match="not among"):
        px.parse_corrections([{"fid": "p2", "kind": "narrow", "candidates": [2]}], inp)


# ---- dates ----------------------------------------------------------------------------------------------------

def date(fid, earliest, latest, convention, never=False):
    return {"fid": fid, "kind": "date", "earliest": earliest, "latest": latest, "never_is_possible": never, "convention": convention}


def test_a_date_interval_gives_a_range_and_is_decisive_when_the_range_exceeds_one_year():
    inp = world()
    res = px.expand([date("p3", 2008, 2016, 2016)], inputs=inp)
    three = row(res, 3, "AA")
    assert three["original"]["crossing"] == 2018 and three["reference"]["crossing"] == 2018
    assert three["range"]["earliest_crossing"] == 2010 and three["range"]["latest_crossing"] == 2018
    assert three["range_kind"] == "tested"
    assert not three["keeps_its_place"]
    assert ["p3", "date"] in three["decisive_on_a_single_flip"] and "p3" in three["joins"]
    # A narrow interval moves each reading's crossing by one year at most: the date question is not decisive on a single
    # flip. The place test is still against the reference's as-built crossing, and the early end's no-anchoring reading
    # (unscaled p3 is twice the scaled one, so it crosses a year sooner) lands two years before it: the utility does not
    # keep its place. The joint check keeps the question all the same: utility 3's status is unsettled in the years its
    # ramp crosses, and the one-year tolerance is not used there (D-63 rule 7).
    res = px.expand([date("p3", 2015, 2016, 2016)], inputs=inp)
    three = row(res, 3, "AA")
    assert three["range"]["earliest_crossing"] == 2017 and three["decisive_on_a_single_flip"] == []
    assert {"fid": "p3", "question": "date", "channel": "own load"} in three["kept_questions"] and three["joins"] == ["p3"]
    assert not three["keeps_its_place"] and three["first_failure"].startswith("all_earliest: lower no anchoring: first crossing 2016")
    res = px.expand([date("p3", 2016, 2016, 2016)], inputs=inp)
    assert row(res, 3, "AA")["keeps_its_place"]


def test_open_below_means_full_load_from_2001_with_no_ramp():
    inp = world()
    corr = px.parse_corrections([date("p3", None, 2016, 2016)], inp)
    _, fy, factor = px.scratch_state(inp, corr, "AA", {("p3", "date"): "early"})
    s = site_rows(fy, "p3")
    assert s.index.min() == 2001 and s.loc[2001] == pytest.approx(1.0) and s.loc[2002] == pytest.approx(1.0)
    assert factor == pytest.approx(0.5)                                                    # 2024 is full load either way


def test_open_above_with_never_removes_the_load_and_changes_the_factor():
    inp = world()
    corrections = [date("p3", 2016, None, "never", never=True)]
    corr = px.parse_corrections(corrections, inp)
    _, fy, factor = px.scratch_state(inp, corr, "AA", {("p3", "date"): "convention"})
    assert "p3" not in set(fy.fid)
    assert factor == pytest.approx(AA_EPRI / (6 * 8.76 / 1000))                            # p3 leaves the 2024 permit total
    assert site_rows(fy, "p1").loc[2020] == pytest.approx(4.0 * factor)                    # every permit site in AA is rescaled
    res = px.expand(corrections, inputs=inp)
    st = res["states"]["AA"]
    assert st["frozen_factor"] == pytest.approx(0.5) and st["factor_changes"]
    assert st["factor_by_scenario"]["reference"] == pytest.approx(factor)
    one = row(res, 1, "AA")                                                                # touched only through the factor
    assert one["original"]["crossing"] == 2016 and one["reference"]["crossing"] == 2014


def test_a_date_of_2023_or_later_reaches_another_utility_through_the_factor():
    inp = world()
    corrections = [date("p3", 2016, 2024, 2016)]
    res = px.expand(corrections, inputs=inp)
    assert "1:AA" in {r["utility"] for r in res["utilities"]}                              # p3 is not on 1 and does not list it
    st = res["states"]["AA"]
    assert st["factor_varies_across_scenarios"] and st["envelope"]["ran"]
    assert st["factor_by_scenario"]["all_latest"] > 0.5
    v = px.factor_varies(inp, px.parse_corrections(corrections, inp), "AA")
    assert v["varies"] and v["sites_whose_2024_load_varies"] == ["p3"]
    # An interval that ends before 2023 leaves the factor alone and needs no envelope.
    v = px.factor_varies(inp, px.parse_corrections([date("p3", 2010, 2016, 2016)], inp), "AA")
    assert not v["varies"]


def test_the_envelope_is_not_run_past_4096_combinations(monkeypatch):
    inp = world()
    monkeypatch.setattr(px, "ENVELOPE_LIMIT", 1)
    res = px.expand([date("p3", 2016, 2024, 2016)], inputs=inp)
    env = res["states"]["AA"]["envelope"]
    assert not env["ran"] and "AA" in env["note"]


def test_an_unresolved_start_has_no_single_reference_history():
    inp = world()
    res = px.expand([date("p3", 2008, 2016, None)], inputs=inp)
    three = row(res, 3, "AA")
    # The reference repair (R6): the words now name the question the reference turns on and a pair of its settings.
    assert three["reference"].startswith("none (") and "p3 date" in three["reference"] and not three["keeps_its_place"]
    assert three["reference_rule"]["undefined_by"] == [{"fid": "p3", "question": "date"}]
    with pytest.raises(ValueError, match="more than 10"):
        px.check_unresolved_count([{"fid": f"x{i}", "kind": "date", "convention": None} for i in range(11)])


# ---- build-out and capacity ------------------------------------------------------------------------------------

def test_phases_are_not_moved_by_the_earliest_case():
    inp = world()
    corrections = [{"fid": "p3", "kind": "phases", "phases": [[2016, 0.5], [2020, 1.0]]}, date("p1", 2008, 2012, 2012)]
    corr = px.parse_corrections(corrections, inp)
    _, ref, _ = px.scratch_state(inp, corr, "AA", {("p1", "date"): "convention"})
    _, early, _ = px.scratch_state(inp, corr, "AA", {("p1", "date"): "early"})
    expect = {y: buildout.phased_mw(1.0, [(2016, 0.5), (2020, 1.0)], y) for y in YEARS}
    for fy in (ref, early):
        s = site_rows(fy, "p3")
        assert all(s.get(y, 0.0) == pytest.approx(expect[y]) for y in YEARS)
    assert site_rows(early, "p1").index.min() == 2008


def test_a_date_on_a_phased_site_is_refused():
    inp = world()
    with pytest.raises(ValueError, match="phased history"):
        px.parse_corrections([date("ph", 2005, 2010, 2010)], inp)


def test_a_capacity_split_gives_its_two_cases():
    inp = world()
    corr = px.parse_corrections([{"fid": "p3", "kind": "capacity_split", "first_phase_year": 2012, "first_share": 0.25}], inp)
    _, early, _ = px.scratch_state(inp, corr, "AA", {("p3", "capacity"): "early"})
    _, late, _ = px.scratch_state(inp, corr, "AA", {("p3", "capacity"): "late"})
    s_e, s_l = site_rows(early, "p3"), site_rows(late, "p3")
    assert s_e.index.min() == 2012 and s_e.loc[2014] == pytest.approx(1.0)                 # the whole row with the first phase
    assert s_l.loc[2014] == pytest.approx(0.25) and s_l.loc[2018] == pytest.approx(1.0)    # the rest at the inventory year (2016)
    corr = px.parse_corrections([{"fid": "p3", "kind": "capacity_split", "first_phase_year": 2012, "first_share": None}], inp)
    _, late, _ = px.scratch_state(inp, corr, "AA", {("p3", "capacity"): "late"})
    assert site_rows(late, "p3").index.min() == 2016                                       # nothing before the inventory year
    res = px.expand([{"fid": "p3", "kind": "capacity_split", "first_phase_year": 2012, "first_share": 0.25, "convention": "late"}],
                    inputs=inp)
    assert ["p3", "capacity"] in row(res, 3, "AA")["decisive_on_a_single_flip"]


def test_a_size_correction_is_scaled_by_the_state_factor_and_moves_it():
    inp = world()
    corr = px.parse_corrections([{"fid": "p3", "kind": "size", "mw_full": 6.0}], inp)
    _, fy, factor = px.scratch_state(inp, corr, "AA", {})
    assert factor == pytest.approx(AA_EPRI / (12 * 8.76 / 1000))
    assert site_rows(fy, "p3").loc[2020] == pytest.approx(6.0 * factor)


def test_not_a_site_carries_no_load_in_any_case():
    inp = world()
    corr = px.parse_corrections([{"fid": "p2", "kind": "not_a_site"}], inp)
    fac, fy, factor = px.scratch_state(inp, corr, "AA", {})
    assert "p2" not in set(fy.fid) and not fac.in_dose["p2"]
    assert factor == pytest.approx(AA_EPRI / (6 * 8.76 / 1000))
    # A measured site that is not a site leaves the measured side of its state's anchoring.
    corr = px.parse_corrections([{"fid": "e1", "kind": "not_a_site"}], inp)
    _, fy, factor = px.scratch_state(inp, corr, "BB", {})
    assert "e1" not in set(fy.fid) and factor == pytest.approx((0.03504 + BB_EPOCH_MW * 8.76 / 1000) / 0.03504)


def test_a_site_with_a_measured_history_refuses_a_date_correction():
    inp = world()
    with pytest.raises(ValueError, match="measured or operator-reported history"):
        px.parse_corrections([date("e1", 2015, 2018, 2018)], inp)
    with pytest.raises(ValueError, match="measured or operator-reported history"):
        px.parse_corrections([{"fid": "e1", "kind": "capacity_split", "first_phase_year": 2015, "first_share": None}], inp)
    px.parse_corrections([{"fid": "e1", "kind": "assign", "to": "off_panel"}], inp)       # an assignment is fine


# ---- what joins the list ---------------------------------------------------------------------------------------

def test_the_single_flip_output_is_kept_and_joins_now_come_from_the_joint_check():
    # Under D-61 4's reading p2's assignment was already decisive before and did not join. D-63 rule 7 replaces that
    # test: joins are the sites of the questions the joint check keeps, and p2 can change utility 1's statuses.
    inp = world()
    res = px.expand([date("p1", 2012, 2012, 2012)], inputs=inp)
    one = row(res, 1, "AA")
    assert ["p2", "assignment"] in one["decisive_on_a_single_flip"]
    assert ["p2", "assignment"] in one["already_decisive_before"]
    assert {"fid": "p2", "question": "assignment", "channel": "own load"} in one["kept_questions"]
    assert one["joins"] == ["p2"]


def test_an_assignment_question_that_becomes_decisive_joins_and_is_checked_against_the_targets(tmp_path):
    # p1 at 6 MW raw (3 scaled) carries utility 1 over 2% in 2014 alone, before p2 (2 scaled, from 2015) arrives: p2's
    # assignment decides nothing before. With p1 dated 2020, p1 alone crosses in 2022 and with p2 in 2020: now it does.
    inp = world(raw={"p1": 6.0, "p2": 4.0})
    before = px.expand([date("p1", 2012, 2012, 2012)], inputs=inp)
    assert row(before, 1, "AA")["decisive_on_a_single_flip"] == []
    targets = tmp_path / "targets.csv"
    pd.DataFrame({"site": ["p1"]}).to_csv(targets, index=False)
    res = px.expand([date("p1", 2012, 2020, 2020)], inputs=inp, targets=targets)
    one = row(res, 1, "AA")
    assert one["original"]["crossing"] == 2014 and one["reference"]["crossing"] == 2020
    assert ["p2", "assignment"] in one["decisive_on_a_single_flip"] and ["p2", "assignment"] not in one["already_decisive_before"]
    assert one["joins"] == ["p1", "p2"]
    assert one["joins_on_target_list"] == {"p1": "on the list", "p2": "new"}


def test_the_output_path_may_not_be_under_data():
    with pytest.raises(ValueError, match="outside data/"):
        px.check_out_path(ROOT / "data" / "frozen" / "x.json")
    px.check_out_path(Path("/tmp/somewhere/x.json"))


def test_the_old_assignment_only_test_still_runs():
    inp = world()
    old = (inp.fac, inp.fy, pd.DataFrame({"utility_id_eia": [1, 2, 3, 4], "state": ["AA", "AA", "AA", "BB"],
                                          "utility_name": ["One", "Two", "Three", "Four"]}), inp.units, inp.base, inp.regions)
    t = px.test([{"fid": "p2", "to": (2, "AA")}], inputs=old)
    assert set(t.utility) == {"1:AA", "2:AA"}


# ---- the joint check (D-63 rule 7), the reopen correction and rest_earliest (rule 8), the range kind (rule 4) --------

GWH = 8.76                    # GWh per MW-year
FLOOR = asg.CLEAN_BELOW


def mini(sites: list[dict], bases: dict, epri: dict | None = None) -> px.Inputs:
    """A made-up inventory from a list of sites; each state's factor is computed by build_inventory's arithmetic.

    A site: fid, st, u (utility or None), cands ("5;6"), assign (default "unique"), raw (MW), year, and optionally
    basis ("verified_public_figure" makes it measured and unscaled) or src="epoch" (a fixed measured history: `raw`
    from `year` on, no ramp). `bases` maps (utility, state) to the base-period sales in GWh; `epri` maps a state to
    its EPRI total in TWh (default: the state's own total, so the factor is 1).
    """
    rows = []
    for s in sites:
        rows.append({"fid": s["fid"], "state": s["st"], "src": s.get("src", "bi"),
                     "load_history": "epoch_timeline" if s.get("src") == "epoch" else "three_year_ramp",
                     "mw_basis": "epoch_timeline" if s.get("src") == "epoch" else s.get("basis", "generator_capacity_x_kappa"),
                     "energized_year": float(s["year"]) if s.get("year") is not None else np.nan,
                     "mw_full_raw": float(s["raw"]), "utility_id_eia": float(s["u"]) if s.get("u") is not None else np.nan,
                     "utility_assign": s.get("assign", "unique"), "utility_candidates": s.get("cands", str(s.get("u"))),
                     "is_crypto": False})
    fac = pd.DataFrame(rows).set_index("fid")
    epoch = fac.src == "epoch"
    measured = epoch | fac.mw_basis.isin(px.MEASURED_BASIS)
    y24 = pd.Series({f: (r.mw_full_raw if epoch[f] and r.energized_year <= 2024 else 0.0) if epoch[f]
                     else buildout.ramp_mw(r.mw_full_raw, r.energized_year, 2024) if pd.notna(r.energized_year) else 0.0
                     for f, r in fac.iterrows()}) * GWH / 1000
    states = sorted(fac.state.unique())
    permit = y24[~measured].groupby(fac.state[~measured]).sum().reindex(states).fillna(0.0)
    meas = y24[measured].groupby(fac.state[measured]).sum().reindex(states).fillna(0.0)
    ep = pd.Series({st: (epri or {}).get(st, float(permit[st] + meas[st])) for st in states})
    factor = pd.Series({st: px._factor(ep[st], meas[st], permit[st]) for st in states})
    fac["state_scale"] = np.where(measured, 1.0, fac.state.map(factor))
    fac["mw_full"] = fac.mw_full_raw * fac.state_scale
    fac["in_dose"] = fac.energized_year.notna() & fac.mw_full_raw.notna() & fac.utility_id_eia.notna()
    fy = []
    for fid, r in fac[fac.in_dose].iterrows():
        for y in YEARS:
            mw = (r.mw_full if y >= r.energized_year else 0.0) if epoch[fid] else buildout.ramp_mw(r.mw_full, r.energized_year, y)
            if mw > 0:
                fy.append((fid, int(r.utility_id_eia), r.state, y, mw))
    fy = pd.DataFrame(fy, columns=["fid"] + asg.KEY + ["year", "mw"])
    units = pd.MultiIndex.from_tuples(sorted(bases, key=lambda k: (k[1], k[0])), names=asg.KEY)
    base = pd.Series([float(bases[k]) for k in units], index=units)
    regions = pd.Series("West", index=units)
    names = pd.Series([f"U{k[0]}" for k in units], index=units)
    anchor = pd.DataFrame({"epri_twh": ep, "permit_twh": permit, "epoch_twh": meas, "factor": factor})
    frozen = {f: float(fac.mw_full_raw[f]) if fac.energized_year[f] <= 2024 else 0.0 for f in fac.index[epoch & fac.in_dose]}
    return px.Inputs.build(fac, fy, units, base, regions, names, anchor, {}, frozen_2024_mw=frozen)


def kept(jc, uid, st):
    return {(q["fid"], q["question"]) for q in jc["utilities"][f"{uid}:{st}"]["kept_questions"]}


def test_two_of_four_equal_sites_are_all_kept_though_none_is_decisive_on_a_single_flip():
    # Utility 5 needs two of its four 1 MW unresolved sites to reach 2% (1.5 MW). From none, one site never gets there;
    # from all four, taking one away still leaves three. No single flip shows any of them; every one is pivotal.
    sites = [{"fid": f"a{i}", "st": "CC", "u": 5, "cands": "5;6", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}
             for i in range(1, 5)] + [{"fid": "r6", "st": "CC", "u": 6, "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(5, "CC"): 1.5 * GWH / 0.02, (6, "CC"): 1e6})
    t, m, _ = asg.evaluate(inp.fac, inp.fy, inp.units, inp.base, inp.regions, thresholds=(0.02,))
    assert t.at[(5, "CC"), "as_built_2%"] == 2011 and np.isnan(t.at[(5, "CC"), "lower_as_built_2%"])
    assert m["as_built"].loc[(5, "CC")].max() / 4 < 1.5 * GWH                             # one site alone never crosses
    res = px.expand([{"fid": "r6", "kind": "assign", "to": [6, "CC"]}], inputs=inp)       # a correction that changes nothing
    five = row(res, 5, "CC")                                                              # touched only because a question can affect it
    assert not any(q[0].startswith("a") for q in five["decisive_on_a_single_flip"])
    assert five["joins"] == ["a1", "a2", "a3", "a4"]
    jc = px.joint_check(inp, {}, "CC")
    assert kept(jc, 5, "CC") == {(f"a{i}", "assignment") for i in range(1, 5)}
    assert kept(jc, 6, "CC") == set()                                                     # 4 MW is never 0.5% of utility 6


def anchoring_world():
    # DD: q1 (utility 7) dated 2016 to 2024 moves the state's factor (its 2024 load is full, two thirds or a third);
    # s8 is utility 8's only site, permit-based and scaled; m9 is utility 9's only site, a measured figure.
    sites = [{"fid": "q1", "st": "DD", "u": 7, "raw": 4.0, "year": 2016},
             {"fid": "s8", "st": "DD", "u": 8, "raw": 4.0, "year": 2010},
             {"fid": "m9", "st": "DD", "u": 9, "raw": 3.0, "year": 2010, "basis": "verified_public_figure"}]
    epri = {"DD": 0.5 * 8 * GWH / 1000 + 3 * GWH / 1000}                                  # factor 0.5 with q1 at full load in 2024
    return mini(sites, {(7, "DD"): 1e3, (8, "DD"): 2.5 * GWH / 0.02, (9, "DD"): 3 * GWH / 0.03}, epri)


def test_a_date_that_moves_the_factor_is_kept_for_another_utility_through_the_factor_only():
    inp = anchoring_world()
    corr = px.parse_corrections([date("q1", 2016, 2024, 2016)], inp)
    jc = px.joint_check(inp, corr, "DD")
    fr = jc["factor_range"]
    assert fr["low"] == pytest.approx(0.5, abs=1e-9) and fr["high"] == pytest.approx(0.75, abs=1e-9) and not fr["band_used"]
    # s8 scaled is 2 MW at factor 0.5 and 3 MW at 0.75, either side of utility 8's 2.5 MW threshold.
    eight = jc["utilities"]["8:DD"]
    assert {"fid": "q1", "question": "date", "channel": "factor"} in eight["kept_questions"]
    assert all(r == "as_built" for _, r, _ in eight["unsettled"])                         # no anchoring: 4 MW raw, settled
    assert jc["utilities"]["9:DD"]["kept_questions"] == [] and jc["utilities"]["9:DD"]["can_affect"] == []
    res = px.expand([date("q1", 2016, 2024, 2016)], inputs=inp)
    assert "8:DD" in {r["utility"] for r in res["utilities"]} and row(res, 8, "DD")["joins"] == ["q1"]


def test_a_comparison_utility_that_can_cross_the_floor_keeps_the_question_and_one_that_cannot_drops_it():
    sites = [{"fid": "x", "st": "EE", "u": 10, "cands": "10;11;12", "assign": "smallest_polygon", "raw": 2.0, "year": 2010}]
    inp = mini(sites, {(10, "EE"): 1e3, (11, "EE"): 2 * GWH / 0.01, (12, "EE"): 1e6})    # x is 1% of 11, 0.002% of 12
    jc = px.joint_check(inp, {}, "EE")
    eleven = jc["utilities"]["11:EE"]
    assert kept(jc, 11, "EE") == {("x", "assignment")}
    assert eleven["n_unsettled"] > 0 and {th for _, _, th in eleven["unsettled"]} == {FLOOR}   # under 2% in every case
    assert kept(jc, 12, "EE") == set() and jc["utilities"]["12:EE"]["n_unsettled"] == 0
    assert [q["fid"] for q in jc["utilities"]["12:EE"]["can_affect"]] == ["x"]           # it can affect 12, and is dropped


def test_a_reopened_assignment_is_a_question_for_each_candidate_and_the_refusals_are_in_words():
    inp = world()
    corr = px.parse_corrections([{"fid": "p1", "kind": "reopen", "candidates": [1, 2]}], inp)
    fac, fy, _ = px.scratch_state(inp, corr, "AA", {})
    t, m, r = asg.evaluate(fac, fy, inp.units[:3], inp.base[:3], inp.regions[:3], thresholds=(0.02,))
    assert not r["p1"] and fac.utility_id_eia["p1"] == 1                                   # unresolved, still on 1 as mapped
    assert m["upper_as_built"].loc[(2, "AA")].max() > m["as_built"].loc[(2, "AA")].max()    # 2's upper case carries it
    jc = px.joint_check(inp, corr, "AA")
    assert {"fid": "p1", "question": "assignment", "settings": 3} in jc["questions"]      # on 1, on 2, or off the panel
    assert ("p1", "assignment") in kept(jc, 1, "AA") and ("p1", "assignment") in kept(jc, 2, "AA")
    res = px.expand([{"fid": "p1", "kind": "reopen", "candidates": [1, 2]}], inputs=inp)
    assert {"1:AA", "2:AA"} <= {u["utility"] for u in res["utilities"]}
    with pytest.raises(ValueError, match="not verified"):
        px.parse_corrections([{"fid": "p2", "kind": "reopen", "candidates": [1, 2]}], inp)
    with pytest.raises(ValueError, match="reopen"):
        px.parse_corrections([{"fid": "p1", "kind": "reopen", "candidates": [1, 2]}, {"fid": "p1", "kind": "assign", "to": [1, "AA"]}], inp)
    with pytest.raises(ValueError, match="reopen"):
        px.parse_corrections([{"fid": "p1", "kind": "reopen", "candidates": [1, 2]}, {"fid": "p1", "kind": "narrow", "candidates": [1]}], inp)
    with pytest.raises(ValueError, match="empty"):
        px.parse_corrections([{"fid": "p1", "kind": "reopen", "candidates": []}], inp)


def test_a_reopened_site_that_was_verified_off_the_panel_is_entered_on_its_first_candidate():
    sites = [{"fid": "w", "st": "GG", "u": None, "cands": "", "assign": "wholesale_direct", "raw": 2.0, "year": 2010},
             {"fid": "k", "st": "GG", "u": 15, "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(15, "GG"): 1e3, (16, "GG"): 1e3})
    corr = px.parse_corrections([{"fid": "w", "kind": "reopen", "candidates": [16, 15]}], inp)
    fac, fy, _ = px.scratch_state(inp, corr, "GG", {})
    assert fac.utility_id_eia["w"] == 16 and set(fy[fy.fid == "w"].utility_id_eia) == {16}
    jc = px.joint_check(inp, corr, "GG")
    assert ("w", "assignment") in kept(jc, 15, "GG") and ("w", "assignment") in kept(jc, 16, "GG")


def split(fid, first, share, rest_earliest=None, convention=None):
    c = {"fid": fid, "kind": "capacity_split", "first_phase_year": first, "first_share": share, "convention": convention}
    if rest_earliest is not None:
        c["rest_earliest"] = rest_earliest
    return c


def test_rest_earliest_holds_the_rest_back_and_the_joint_check_covers_every_year_it_may_arrive():
    inp = world()
    corr = px.parse_corrections([split("p3", 2012, 0.5, rest_earliest=2014)], inp)
    _, early, _ = px.scratch_state(inp, corr, "AA", {("p3", "capacity"): "early"})
    _, late, _ = px.scratch_state(inp, corr, "AA", {("p3", "capacity"): "late"})
    for fy, rest in ((early, 2014), (late, 2016)):                                         # inventory year 2016: the late case is unchanged
        s = site_rows(fy, "p3")
        assert all(s.get(y, 0.0) == pytest.approx(buildout.phased_mw(1.0, [(2012, 0.5), (rest, 1.0)], y)) for y in YEARS)
    assert site_rows(early, "p3").loc[2013] == pytest.approx(buildout.ramp_mw(0.5, 2012, 2013))   # nothing of the rest before 2014
    jc = px.joint_check(inp, corr, "AA")
    assert {"fid": "p3", "question": "capacity", "settings": 3} in jc["questions"]
    u = inp.units[inp.units.get_level_values("state") == "AA"]
    for rest in (2014, 2015, 2016):
        fac, fy, _ = px.scratch_state(inp, corr, "AA", {("p3", "capacity"): rest})
        assert site_rows(fy, "p3").get(2015, 0.0) == pytest.approx(buildout.phased_mw(1.0, [(2012, 0.5), (rest, 1.0)], 2015))
        _, m, _ = asg.evaluate(fac, fy, u, inp.base.reindex(u), inp.regions.reindex(u), thresholds=(0.02,))
        for k in u:
            for reading in ("as_built", "no_anchoring"):
                lo, hi = jc["bounds"][k][reading]
                v = m[reading].loc[k].values
                assert (v >= lo - 1e-9).all() and (v <= hi + 1e-9).all(), (k, reading, rest)
    with pytest.raises(ValueError, match="first phase's share"):
        px.parse_corrections([split("p3", 2012, None, rest_earliest=2014)], inp)
    with pytest.raises(ValueError, match="after the inventory's year"):
        px.parse_corrections([split("p3", 2012, 0.5, rest_earliest=2017)], inp)


def test_a_utility_settled_far_above_or_far_below_both_thresholds_drops_every_question():
    sites = [{"fid": "big", "st": "FF", "u": 13, "raw": 100.0, "year": 1990},
             {"fid": "z", "st": "FF", "u": 13, "cands": "13;14", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(13, "FF"): 100 * GWH / 0.10, (14, "FF"): 1e7})                   # 13 at 10% or more; z under 0.01% of 14
    corr = px.parse_corrections([date("z", 2005, 2020, 2010)], inp)
    jc = px.joint_check(inp, corr, "FF")
    for uid in (13, 14):
        u = jc["utilities"][f"{uid}:FF"]
        assert u["n_unsettled"] == 0 and u["kept_questions"] == [] and u["joins"] == []
        assert {q["fid"] for q in u["can_affect"]} == {"z"}                               # it can affect both, and changes nothing


def test_the_range_is_admissible_only_when_every_date_question_that_can_affect_it_rests_on_evidence():
    inp = world()
    tested = row(px.expand([date("p3", 2010, 2016, 2016)], inputs=inp), 3, "AA")
    assert tested["range_kind"] == "tested"                                               # the default: an end rests on a permit year
    admissible = row(px.expand([{**date("p3", 2010, 2016, 2016), "ends": "evidence"}], inputs=inp), 3, "AA")
    assert admissible["range_kind"] == "admissible" and admissible["range"] == tested["range"]
    # A capacity question's late end is the inventory's permit-based year: always tested.
    both = row(px.expand([{**date("p3", 2010, 2016, 2016), "ends": "evidence"}, split("p3", None, 0.5, convention="early")],
                         inputs=inp), 3, "AA")
    assert both["range_kind"] == "tested"
    with pytest.raises(ValueError, match="ends"):
        px.parse_corrections([{**date("p3", 2010, 2016, 2016), "ends": "documented"}], inp)
    table = px._table(px.expand([date("p3", 2010, 2016, 2016)], inputs=inp))
    assert "tested or admissible range" in table and "(tested)" in table


# ---- the brute-force check of the guarantee ----------------------------------------------------------------------

def _realize(inp, corr, st, config):
    """One configuration through the module's own scratch rebuild and assignment.evaluate (not through the bounds)."""
    corr = dict(corr)
    choice = {}
    for (fid, q), v in config.items():
        if q == "assignment":
            to = px.OFF if v is None else (v, st)
            c = corr.get(fid) or px.Correction(fid=fid, state=st, inventory_year=inp.fac.energized_year[fid])
            corr[fid] = dataclasses.replace(c, assign=to, reopen=None, narrow=None)
        else:
            choice[(fid, q)] = v
    fac, fy, _ = px.scratch_state(inp, corr, st, choice)
    u = inp.units[inp.units.get_level_values("state") == st]
    _, m, _ = asg.evaluate(fac, fy, u, inp.base.reindex(u), inp.regions.reindex(u), thresholds=(0.02,))
    return {r: m[r] for r in ("as_built", "no_anchoring")}


def _brute_force(inp, corrections, st, space):
    """Every configuration of `space` ({question: [values]}); returns (configurations, assertion counts)."""
    corr = px.parse_corrections(corrections, inp)
    jc = px.joint_check(inp, corr, st)
    assert {(q["fid"], q["question"]): q["settings"] for q in jc["questions"]} == {q: len(v) for q, v in space.items()}
    qs = list(space)
    u = inp.units[inp.units.get_level_values("state") == st]
    base = inp.base.reindex(u)
    statuses, n_inside = {}, 0
    for combo in itertools.product(*(space[q] for q in qs)):
        config = dict(zip(qs, combo))
        m = _realize(inp, corr, st, config)
        st_cfg = {}
        for k in u:
            for reading, mat in m.items():
                v = mat.loc[k].values
                lo, hi = jc["bounds"][k][reading]
                assert (v >= lo - 1e-9).all() and (v <= hi + 1e-9).all(), (k, reading, config)   # (i)
                n_inside += len(v)
                for th in (0.02, FLOOR):
                    st_cfg[(k, reading, th)] = tuple(v >= th * base[k])
        statuses[combo] = st_cfg
    # (ii): any question whose setting alone changes any status, in any configuration of the others, is kept.
    decisive = set()
    for i, q in enumerate(qs):
        groups = {}
        for combo, s in statuses.items():
            groups.setdefault(combo[:i] + combo[i + 1:], []).append(s)
        for g in groups.values():
            for k in u:
                if any(a[key] != g[0][key] for a in g[1:] for key in a if key[0] == k):
                    decisive.add((q, k))
    for q, k in decisive:
        assert q in kept(jc, *k), (q, k)
    return len(statuses), n_inside, len(decisive), sum(len(kept(jc, *k)) for k in u)


BRUTE = {}


def test_brute_force_the_factor_moves():
    inp = world()
    space = {("p2", "assignment"): [1, 2, None], ("p3", "date"): list(range(2016, 2025)) + ["never"]}
    BRUTE["factor moves"] = _brute_force(inp, [date("p3", 2016, 2024, 2016, never=True)], "AA", space)
    assert BRUTE["factor moves"][0] == 30 and BRUTE["factor moves"][2] > 0


def test_brute_force_a_reopened_site():
    inp = world()
    space = {("p1", "assignment"): [1, 3, None], ("p1", "date"): list(range(2010, 2015)), ("p2", "assignment"): [1, 2, None]}
    BRUTE["reopened"] = _brute_force(inp, [{"fid": "p1", "kind": "reopen", "candidates": [1, 3]}, date("p1", 2010, 2014, 2012)],
                                     "AA", space)
    assert BRUTE["reopened"][0] == 45 and BRUTE["reopened"][2] > 0


def test_brute_force_a_capacity_split_dated_by_a_date_question():
    inp = world()
    space = {("p2", "assignment"): [1, 2, None], ("p3", "date"): [2011, 2012, 2013], ("p3", "capacity"): [2013, 2014, 2015, 2016]}
    BRUTE["capacity split"] = _brute_force(inp, [date("p3", 2011, 2013, 2012), split("p3", None, 0.5, rest_earliest=2013)],
                                           "AA", space)
    assert BRUTE["capacity split"][0] == 36 and BRUTE["capacity split"][2] > 0


def test_brute_force_a_measured_site_whose_date_moves_the_factor_from_the_measured_side():
    inp = world()
    space = {("p2", "assignment"): [1, 2, None], ("p3", "date"): list(range(2020, 2025))}
    BRUTE["measured date"] = _brute_force(inp, [{"fid": "p3", "kind": "size", "mw_full": 2.0, "measured": True},
                                                date("p3", 2020, 2024, 2020)], "AA", space)
    assert BRUTE["measured date"][0] == 15
    jc = px.joint_check(inp, px.parse_corrections([{"fid": "p3", "kind": "size", "mw_full": 2.0, "measured": True},
                                                   date("p3", 2020, 2024, 2020)], inp), "AA")
    assert jc["factor_range"]["low"] < jc["factor_range"]["high"]                          # it moves the factor


def test_brute_force_two_of_four():
    sites = [{"fid": f"a{i}", "st": "CC", "u": 5, "cands": "5;6", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}
             for i in range(1, 5)]
    inp = mini(sites, {(5, "CC"): 1.5 * GWH / 0.02, (6, "CC"): 1.5 * GWH / 0.02})
    space = {(f"a{i}", "assignment"): [5, 6, None] for i in range(1, 5)}
    BRUTE["two of four"] = _brute_force(inp, [], "CC", space)
    assert BRUTE["two of four"][0] == 81 and BRUTE["two of four"][2] == 8


# ---- the reproduction on the real files ------------------------------------------------------------------------

INTERIM = ROOT / "data" / "interim"
REAL = all((INTERIM / f).exists() for f in ("facilities.parquet", "facility_year.parquet", "state_anchor.parquet",
                                            "panel_quantities.parquet", "utility_year_dose.parquet", "epoch_gaps.parquet"))


@pytest.fixture(scope="module")
def real():
    return px.load_frozen()


@pytest.mark.skipif(not REAL, reason="data/interim/facilities.parquet and its companions are absent")
def test_the_scratch_rebuild_with_no_corrections_reproduces_the_frozen_inventory(real):
    rep = px.reproduce(real)
    # The anchoring: every state's permit-based 2024 total and factor, recomputed from the scratch histories.
    assert rep["anchor_states"] == len(real.anchor)
    assert rep["anchor_permit_twh_max_abs_diff"] < 1e-9
    assert rep["anchor_factor_max_abs_diff"] < 1e-12
    assert rep["state_scale_max_abs_diff"] < 1e-12
    # Every permit-based and figure-based site's rows rebuilt from its raw load, its history and the recomputed factor.
    assert rep["rebuilt_sites"] == rep["frozen_sites"] and rep["rebuilt_rows"] == rep["frozen_rows"]
    assert rep["rows_missing"] == 0 and rep["rows_extra"] == 0
    assert rep["rebuilt_mw_max_abs_diff"] < 1e-9
    # The measured histories the rebuild cannot recompute (Epoch timelines, operator reports) are held, never rebuilt.
    assert rep["measured_residual_min_twh"] >= -1e-9
    # Evaluating one state at a time gives exactly what the whole-panel evaluation gives.
    assert rep["per_state_evaluation_max_abs_diff"] == 0.0


@pytest.mark.skipif(not REAL, reason="data/interim/facilities.parquet and its companions are absent")
def test_scratch_state_with_no_corrections_returns_the_frozen_rows_in_every_state(real):
    for st in sorted(real.fac.state.dropna().unique()):
        _, fy, factor = px.scratch_state(real, {}, st, {})
        frozen = real.fy[real.fy.state == st]
        assert len(fy) == len(frozen), st
        assert factor == pytest.approx(real.frozen_factor(st), abs=1e-12), st


@pytest.mark.skipif(not REAL, reason="data/interim/facilities.parquet and its companions are absent")
def test_with_no_corrections_the_joint_check_reports_the_frozen_inventorys_open_assignments(real):
    # The questions are a property of the inputs: with no corrections, every unresolved site carrying load on the panel
    # (assignment.evaluate's own reading) is an assignment question, and no date or capacity question exists.
    _, _, r = asg.evaluate(real.fac, real.fy, real.units, real.base, real.regions, thresholds=(0.02,))
    # A row with no state carries site-years under state None: they land on no panel unit, and no state's rebuild holds
    # them (parse_corrections refuses such a row). They raise no question for any panel utility; listed, not dropped silently.
    stateless = real.fy[real.fy.state.isna()]
    assert not any((u, s) in set(real.units) for u, s in zip(stateless.utility_id_eia, stateless.state))
    expected = {(f, "assignment") for f in set(real.fy.fid) - set(stateless.fid) if not r[f]}
    found, n_kept = set(), 0
    for st in sorted(real.fac.state.dropna().unique()):
        jc = px.joint_check(real, {}, st)
        found |= {(q["fid"], q["question"]) for q in jc["questions"]}
        assert jc["factor_range"]["low"] == pytest.approx(real.frozen_factor(st), abs=1e-9), st      # nothing moves a factor
        assert jc["factor_range"]["high"] == pytest.approx(real.frozen_factor(st), abs=1e-9), st
        n_kept += sum(len(u["kept_questions"]) for u in jc["utilities"].values())
    assert found == expected and len(expected) > 0
    assert n_kept > 0


def test_a_range_that_no_date_question_reaches_is_not_called_admissible():
    """D-63 rule 4: with assignment corrections only, a utility's range rests on the inventory's own dates."""
    res = px.expand([{"fid": "p3", "kind": "assign", "to": "off_panel"}], inputs=world())
    assert res["utilities"] and all(u["range_kind"] == "inventory dates only" for u in res["utilities"])


def test_no_question_reaches_a_utility_through_a_factor_that_cannot_move():
    """Where the factor's outer bounds coincide, the factor channel is closed; where they do not, it is open."""
    inp = px.load_frozen() if (px.INTERIM / "facilities.parquet").exists() else None
    if inp is None:
        pytest.skip("the inventory is not built")
    for st in sorted(set(inp.fac.state.dropna())):
        jc = px.joint_check(inp, {}, st)
        fr = jc["factor_range"]
        channels = {q["channel"] for u in jc["utilities"].values() for q in u["kept_questions"]}
        if not fr["high"] > fr["low"]:
            assert channels <= {"own load"}, (st, channels)


# ---- D-65 items 1 and 5, D-66 sections 1 to 3 -----------------------------------------------------------------------

def test_a_fixed_history_on_a_row_not_marked_measured_is_refused_in_words():
    """D-65 item 1: fixed but factor-scaled is not a supported input; the frozen inventory has none."""
    inp = world()
    fac = inp.fac.copy()
    fac.loc["p3", "load_history"] = "operator_reported_energy"          # fixed, and still a generator-based size
    with pytest.raises(ValueError, match="not marked measured"):
        px.Inputs.build(fac, inp.fy, inp.units, inp.base, inp.regions, inp.names, inp.anchor, inp.phases, inp.frozen_2024_mw)
    if (px.INTERIM / "facilities.parquet").exists():
        real = px.load_frozen()                                           # loads, so the real inventory has none
        assert not (real.fixed & ~real.measured).any()


def test_an_unresolved_row_with_load_and_candidates_but_no_current_utility_is_refused_in_words():
    """D-65 item 5: handled or refused. Refused: the check has no as-mapped reading for it and does not invent one."""
    sites = [{"fid": "a", "st": "GG", "u": 20, "raw": 2.0, "year": 2010},
             {"fid": "lost", "st": "GG", "u": None, "cands": "20;21", "assign": "none", "raw": 2.0, "year": 2012}]
    inp = mini(sites, {(20, "GG"): 1e3, (21, "GG"): 1e3})
    with pytest.raises(ValueError, match="on no utility"):
        px.joint_check(inp, {}, "GG")
    # The same row with no size carries no load in any setting: it is counted as a missing input, not refused.
    sites[1]["raw"] = np.nan
    inp = mini(sites, {(20, "GG"): 1e3, (21, "GG"): 1e3})
    jc = px.joint_check(inp, {}, "GG")
    assert jc["unresolved_sites_with_no_load_in_any_setting"] == ["lost"]
    assert jc["missing_inputs"]["no_size"] == 1 and jc["missing_inputs"]["no_current_utility_other"] == 1
    # A row verified off the panel has no current utility and is resolved: no question, nothing refused.
    sites[1].update(raw=2.0, assign="wholesale_direct")
    inp = mini(sites, {(20, "GG"): 1e3, (21, "GG"): 1e3})
    jc = px.joint_check(inp, {}, "GG")
    assert jc["questions"] == [] and jc["missing_inputs"]["no_current_utility_verified_off_the_panel"] == 1


def test_rows_are_counted_by_what_is_missing_and_the_guarantee_is_stated():
    sites = [{"fid": "a", "st": "GG", "u": 20, "raw": 2.0, "year": 2010},
             {"fid": "nosize", "st": "GG", "u": 20, "cands": "20;21", "assign": "smallest_polygon", "raw": np.nan, "year": 2012},
             {"fid": "noyear", "st": "GG", "u": 21, "cands": "20;21", "assign": "smallest_polygon", "raw": 3.0, "year": None},
             {"fid": "b", "st": "HH", "u": 30, "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(20, "GG"): 1e3, (21, "GG"): 1e3, (30, "HH"): 1e3})
    m = px.missing_inputs(inp, "GG")
    assert (m["rows"], m["no_size"], m["no_start_year"], m["no_size_or_no_start_year"], m["no_current_utility"]) == (3, 1, 1, 2, 0)
    assert m["unresolved"] == 2 and m["unresolved_no_size"] == 1 and m["unresolved_no_start_year"] == 1
    whole = px.missing_inputs(inp)
    assert whole["rows"] == 4 and whole["no_state"] == 0 and whole["no_state_rows"] == []
    jc = px.joint_check(inp, {}, "GG")
    assert jc["missing_inputs"] == m and "modeled loads and enumerated uncertainties only" in jc["guarantee"]
    assert sorted(jc["unresolved_sites_with_no_load_in_any_setting"]) == ["nosize", "noyear"]
    res = px.expand([{"fid": "a", "kind": "assign", "to": "off_panel"}], inputs=inp)
    assert res["missing_inputs_in_the_inventory"]["rows"] == 4 and res["states"]["GG"]["missing_inputs"] == m
    assert "modeled loads" in res["guarantee"]


def test_a_candidates_correction_adds_a_possible_supplier_and_cannot_take_one_away():
    """D-66 section 1: a widening on a lead. The site is unresolved from then on, also where the map had it alone."""
    inp = world()
    jc0 = px.joint_check(inp, {}, "AA")
    assert kept(jc0, 3, "AA") == set()                                    # p3 is alone in utility 3's territory: resolved
    corr = px.parse_corrections([{"fid": "p3", "kind": "candidates", "candidates": [3, 2]}], inp)
    jc = px.joint_check(inp, corr, "AA")
    assert ("p3", "assignment") in kept(jc, 3, "AA")                      # utility 3 crosses with p3 and not without it
    assert {q["fid"] for q in jc["utilities"]["2:AA"]["can_affect"]} == {"p2", "p3"}
    res = px.expand([{"fid": "p3", "kind": "candidates", "candidates": [3, 2]}], inputs=inp)
    assert {"3:AA", "2:AA"} <= {r["utility"] for r in res["utilities"]}
    # p2's own list (1;2) widened with utility 3
    corr = px.parse_corrections([{"fid": "p2", "kind": "candidates", "candidates": [1, 2, 3]}], inp)
    assert {q["fid"] for q in px.joint_check(inp, corr, "AA")["utilities"]["3:AA"]["can_affect"]} == {"p2"}
    with pytest.raises(ValueError, match="leaves out"):
        px.parse_corrections([{"fid": "p2", "kind": "candidates", "candidates": [1, 3]}], inp)
    with pytest.raises(ValueError, match="reopen"):
        px.parse_corrections([{"fid": "p1", "kind": "candidates", "candidates": [1, 2]}], inp)
    with pytest.raises(ValueError, match="cannot come with"):
        px.parse_corrections([{"fid": "p2", "kind": "candidates", "candidates": [1, 2, 3]},
                              {"fid": "p2", "kind": "narrow", "candidates": [1]}], inp)


def test_a_provisional_convention_is_carried_and_checked():
    inp = world()
    d = dict(date("p3", 2014, 2016, 2014), convention_is="provisional")
    assert px.parse_corrections([d], inp)["p3"].date["convention_is"] == "provisional"
    assert px.parse_corrections([date("p3", 2014, 2016, 2014)], inp)["p3"].date["convention_is"] is None
    with pytest.raises(ValueError, match="provisional"):
        px.parse_corrections([dict(d, convention_is="settled")], inp)
    with pytest.raises(ValueError, match="has none"):
        px.parse_corrections([dict(date("p3", 2014, 2016, None), convention_is="provisional")], inp)


def _factor_world(epri_twh):
    # FF: q (utility 40) dated 2016 to 2024, so its 2024 load is full, two thirds or a third of 3 MW; s (utility 41) is
    # 3 MW from 2010, scaled; the permit total runs from 4 to 6 MW (0.03504 to 0.05256 TWh).
    sites = [{"fid": "q", "st": "FF", "u": 40, "raw": 3.0, "year": 2016},
             {"fid": "s", "st": "FF", "u": 41, "raw": 3.0, "year": 2010}]
    return mini(sites, {(40, "FF"): 1e3, (41, "FF"): 1e3}, {"FF": epri_twh})


def test_a_factor_held_at_the_cap_or_the_floor_in_every_setting_is_one_number_and_its_channel_is_closed():
    """D-66 section 3: the factor does not increase in either total, so its range is read from the ends."""
    for epri, held in ((1.0, px.SCALE_HI), (0.001, px.SCALE_LO)):          # raw factor at least 19, and at most 0.03
        inp = _factor_world(epri)
        jc = px.joint_check(inp, px.parse_corrections([date("q", 2016, 2024, 2016)], inp), "FF")
        fr = jc["factor_range"]
        assert fr["low"] == fr["high"] == held and not fr["band_used"] and not fr["permit_total_can_be_zero"]
        assert all(q["channel"] == "own load" for u in jc["utilities"].values() for q in u["kept_questions"])
        assert jc["utilities"]["41:FF"]["can_affect"] == []               # q reaches 41 only through the factor, which cannot move
        for v in (2016, 2022, 2023, 2024):                                 # and the rebuild agrees in every setting
            assert px.scratch_state(inp, px.parse_corrections([date("q", 2016, 2024, 2016)], inp), "FF", {("q", "date"): v})[2] == held


def test_a_factor_that_reaches_the_cap_in_some_settings_only_keeps_its_channel_open():
    # EPRI 0.12264 TWh = 14 MW: raw factor 14/6 = 2.33 with q full in 2024, 14/5 = 2.8, and 14/4 = 3.5, held to 3.0.
    inp = _factor_world(14 * GWH / 1000)
    corr = px.parse_corrections([date("q", 2016, 2024, 2016)], inp)
    jc = px.joint_check(inp, corr, "FF")
    fr = jc["factor_range"]
    assert fr["low"] == pytest.approx(14 / 6) and fr["high"] == px.SCALE_HI and not fr["band_used"]
    assert {"fid": "q", "question": "date"} in jc["utilities"]["41:FF"]["can_affect"]
    got = {v: px.scratch_state(inp, corr, "FF", {("q", "date"): v})[2] for v in (2016, 2023, 2024)}
    assert got[2016] == pytest.approx(14 / 6) and got[2023] == pytest.approx(2.8) and got[2024] == px.SCALE_HI
    assert all(fr["low"] - 1e-12 <= f <= fr["high"] + 1e-12 for f in got.values())


def test_the_factor_does_not_increase_in_either_total():
    """The analytic claim of D-66 section 3, on a grid that includes the cap, the floor and a total above EPRI's."""
    P = np.linspace(0.001, 2.0, 60)
    M = np.linspace(0.0, 1.5, 40)
    for epri in (0.0, 0.3, 1.0, 5.0):
        F = np.array([[px._factor(epri, m, p) for p in P] for m in M])
        assert (np.diff(F, axis=1) <= 0).all() and (np.diff(F, axis=0) <= 0).all()
        assert F.min() >= px.SCALE_LO and F.max() <= px.SCALE_HI
    assert px._factor(1.0, 0.0, 0.0) == 1.0 and px._factor(1.0, 2.0, 0.0) == 1.0     # no permit total: 1.0 by definition


def test_a_permit_total_that_can_be_zero_widens_the_range_to_one_and_a_total_that_is_always_zero_gives_one():
    # In some setting: the state's only permit-based site may never have operated. Factor 3.0 (held) with it, 1.0 without.
    sites = [{"fid": "only", "st": "JJ", "u": 50, "raw": 2.0, "year": 2015},
             {"fid": "m", "st": "JJ", "u": 51, "raw": 3.0, "year": 2010, "basis": "verified_public_figure"}]
    inp = mini(sites, {(50, "JJ"): 1e3, (51, "JJ"): 1e3}, {"JJ": 1.0})
    corr = px.parse_corrections([date("only", 2015, None, 2015, never=True)], inp)
    fr = px.joint_check(inp, corr, "JJ")["factor_range"]
    assert fr["permit_total_can_be_zero"] and fr["low"] == 1.0 and fr["high"] == px.SCALE_HI
    assert px.scratch_state(inp, corr, "JJ", {("only", "date"): "never"})[2] == 1.0
    assert px.scratch_state(inp, corr, "JJ", {("only", "date"): 2015})[2] == px.SCALE_HI
    # In every setting: a state with measured load only. The factor is 1.0 and nothing reaches anyone through it.
    inp = mini([sites[1]], {(51, "JJ"): 1e3}, {"JJ": 1.0})
    jc = px.joint_check(inp, {}, "JJ")
    assert jc["factor_range"]["low"] == jc["factor_range"]["high"] == 1.0
    assert "not needed" in jc["factor_range"]["monotonicity_check"]


def test_a_utility_with_no_single_reference_still_has_its_question_kept():
    """An unresolved start gives no single reference; that never makes its question irrelevant (D-65 item 4)."""
    inp = world()
    c = [date("p3", 2010, 2016, None)]                                     # utility 3 crosses in 2012 or in 2018
    res = px.expand(c, inputs=inp)
    three = row(res, 3, "AA")
    assert isinstance(three["reference"], str) and three["reference"].startswith("none")
    assert not three["keeps_its_place"] and three["first_failure"] == "no single reference"
    assert {"fid": "p3", "question": "date", "channel": "own load"} in three["kept_questions"] and three["joins"] == ["p3"]


# ---- the reference repair (docs/gate1/reference-repair-rule-2026-11-18.md; D-72 item 4, rule R6) --------------------
# The place test takes its reference from pass_c_exact.reference_of, with its own list of reference-defining questions
# (a date or capacity question with no convention; it does not read the provisional mark). Its scenarios are unchanged.

def interior_world() -> px.Inputs:
    """ZA: y (1 MW raw from 2005) and x (1 MW raw) on utility 1; EPRI 2 MW-equivalent; no measured load.

    With x's start a date question from 2005 to 2025 (or on to "never"), the state's 2024 permit total is 1 MW plus x's
    2024 load: 2 MW for a start up to 2022 (factor 1.0), 1 2/3 for 2023 (1.2), 1 1/3 for 2024 (1.5), and 1 MW for 2025,
    2026 or never (2.0). Utility 1's 2% threshold is 1.9 MW.
      start 2005: factor 1, y and x ramp together: 0.67, 1.33, 2.0 MW in 2005-2007         -> crosses in 2007 (early)
      start 2025 (or never): factor 2, y alone: 0.67, 1.33, 2.0 MW in 2005-2007         -> crosses in 2007 (early)
      start 2010: factor 1, y alone is 1.0 MW until x comes: 1.33, 1.67, 2.0 in 2010-2012 -> crosses in 2012 (cohort)
    The two ends agree and an interior year does not: the endpoint rule called this reference defined. Every load is at
    least 0.1 MW from the threshold. Utility 2 carries nothing.
    """
    sites = [{"fid": "y", "st": "ZA", "u": 1, "raw": 1.0, "year": 2005},
             {"fid": "x", "st": "ZA", "u": 1, "raw": 1.0, "year": 2005}]
    return mini(sites, {(1, "ZA"): 1.9 * GWH / 0.02, (2, "ZA"): 1e3}, {"ZA": 2.0 * GWH / 1000})


def capacity_world() -> px.Inputs:
    """ZC: the same arithmetic as interior_world on one site. x (2 MW raw, inventory year 2025) is split: half with a
    first phase in 2005, the rest arriving in any year from 2005 (rest_earliest) to 2025, with no convention. The first
    half plays y's part and the rest x's: the rest in 2005 or in 2025 crosses in 2007, in 2010 in 2012."""
    sites = [{"fid": "x", "st": "ZC", "u": 1, "raw": 2.0, "year": 2025}]
    return mini(sites, {(1, "ZC"): 1.9 * GWH / 0.02, (2, "ZC"): 1e3}, {"ZC": 2.0 * GWH / 1000})


def corners_world() -> px.Inputs:
    """ZB: two questions with no convention; the all-early and all-late corners agree and a mixed corner does not.

    y (1 MW raw from 2005) and x1 (0.5 MW raw, start 2005 or 2006) on utility 1 (threshold 1.25 MW); x2 (0.5 MW raw,
    start 2024 or 2025) on utility 2, reaching 1 through the factor only. EPRI 2 MW-equivalent.
      x1 2005, x2 2024: factor 2/1.667 = 1.2: 2006 1.2, 2007 1.8                        -> 2007
      x1 2006, x2 2025: factor 2/1.5 = 1.333: 2006 1.111, 2007 1.778                    -> 2007
      x1 2005, x2 2025: factor 1.333: 2006 1.333                                        -> 2006
      x1 2006, x2 2024: factor 1.2: 2006 1.0, 2007 1.6                                  -> 2007
    """
    sites = [{"fid": "y", "st": "ZB", "u": 1, "raw": 1.0, "year": 2005},
             {"fid": "x1", "st": "ZB", "u": 1, "raw": 0.5, "year": 2005},
             {"fid": "x2", "st": "ZB", "u": 2, "raw": 0.5, "year": 2024}]
    return mini(sites, {(1, "ZB"): 1.25 * GWH / 0.02, (2, "ZB"): 1e4}, {"ZB": 2.0 * GWH / 1000})


def test_the_place_test_has_no_reference_where_an_interior_start_moves_the_crossing():
    inp = interior_world()
    # 2005 to 2025: 21 settings, each a different load on 1. On to "never": 2026 and never put nothing on 1 and nothing in
    # the 2024 anchoring, so they are one class: 22.
    for corrections, n in (([date("x", 2005, 2025, None)], 21), ([date("x", 2005, None, None, never=True)], 22)):
        res = px.expand(corrections, inputs=inp)
        one = row(res, 1, "ZA")
        # The place test's scenarios are unchanged: the two reference variants are the two ends, which are also all
        # earliest and all latest, and every flip and envelope combination lands on one of them.
        assert res["states"]["ZA"]["scenarios"] == 2
        assert isinstance(one["reference"], str) and one["reference"].startswith("none (") and "x date" in one["reference"]
        assert not one["keeps_its_place"] and one["first_failure"] == "no single reference"
        rr = one["reference_rule"]
        assert rr["searched"] and rr["settings_enumerated"] == n
        assert rr["undefined_by"] == [{"fid": "x", "question": "date"}]
        assert one["reference_differs_from_original"] is None
    # The same site at a convention: the reference is the corrected inventory's, defined.
    one = row(px.expand([date("x", 2005, 2025, 2010)], inputs=inp), 1, "ZA")
    assert one["reference"]["place"] == "cohort" and one["reference"]["crossing"] == 2012
    assert one["reference_rule"] == {"settings_enumerated": 1, "searched": True, "undefined_by": [], "why_undefined": None}


def test_the_place_test_has_no_reference_where_an_interior_arrival_of_the_rest_moves_the_crossing():
    inp = capacity_world()
    res = px.expand([split("x", 2005, 0.5, rest_earliest=2005)], inputs=inp)
    one = row(res, 1, "ZC")
    assert one["reference"].startswith("none (") and "x capacity" in one["reference"]
    assert one["reference_rule"]["settings_enumerated"] == 21


def test_the_place_test_does_not_read_the_provisional_mark():
    inp = interior_world()
    res = px.expand([dict(date("x", 2005, 2025, 2005), convention_is="provisional")], inputs=inp)
    one = row(res, 1, "ZA")
    assert one["reference"]["place"] == "early" and one["reference"]["crossing"] == 2007   # at the convention: defined
    assert one["reference_rule"]["settings_enumerated"] == 1


def test_the_place_test_has_no_reference_where_a_mixed_corner_moves_the_crossing():
    inp = corners_world()
    res = px.expand([date("x1", 2005, 2006, None), date("x2", 2024, 2025, None)], inputs=inp)
    one = row(res, 1, "ZB")
    assert one["reference"].startswith("none (")
    assert {(q["fid"], q["question"]) for q in one["reference_rule"]["undefined_by"]} <= {("x1", "date"), ("x2", "date")}
    assert one["reference_rule"]["settings_enumerated"] == 4


def test_the_place_test_says_in_words_when_the_reference_was_not_searched(monkeypatch):
    from pipeline.facilities import pass_c_exact as pe
    monkeypatch.setattr(pe, "CEILING", 20)
    one = row(px.expand([date("x", 2005, 2025, None)], inputs=interior_world()), 1, "ZA")
    assert one["reference"].startswith("none (not searched") and "21" in one["reference"] and "20" in one["reference"]
    assert one["reference_rule"]["searched"] is False and one["reference_rule"]["settings_enumerated"] == 21
    monkeypatch.setattr(pe, "CEILING", 21)
    one = row(px.expand([date("x", 2005, 2025, None)], inputs=interior_world()), 1, "ZA")
    assert one["reference_rule"]["searched"] is True and one["reference"].startswith("none (the place")


def test_the_place_test_raises_if_its_reference_variants_disagree_with_the_shared_reference(monkeypatch):
    from pipeline.facilities import pass_c_exact as pe
    real = pe.reference_of

    def wrong(S, k, base_k, theta, defining, ceiling=None):
        rec, codes = real(S, k, base_k, theta, defining, pe.CEILING if ceiling is None else ceiling)
        if rec["defined"] and k == (3, "AA"):
            rec, codes = dict(rec, crossing="2001"), (codes[0], 0)
        return rec, codes
    monkeypatch.setattr(pe, "reference_of", wrong)
    with pytest.raises(ValueError, match="reference"):
        px.expand([date("p3", 2010, 2016, 2016)], inputs=world())
