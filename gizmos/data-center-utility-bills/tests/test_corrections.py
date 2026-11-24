"""Step D: the adopted corrections reaching the real inventory (pipeline/facilities/corrections.py, the step D hooks in
apply_verified.py and build_inventory.py). Made-up inputs only, except the snapshot tests at the end, which skip if
data/interim/snapshot-2026-11-14/ is absent."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "interim" / "snapshot-2026-11-14"

import stepd_world as W  # noqa: E402
from pipeline.facilities import apply_verified as av  # noqa: E402
from pipeline.facilities import corrections as cx  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402


def frame(**over):
    """A pre-anchoring frame as build_inventory has it, indexed by fid."""
    f = pd.DataFrame({
        "fid": ["a", "b", "c", "e", "y"],
        "src": ["bi", "bi", "bi", "epoch", "bi"],
        "state": ["AA"] * 5,
        "energized_year": [2019.0, 2015.0, 2012.0, 2018.0, 2020.0],
        "date_basis": [cx.PERMIT_LABEL, cx.PERMIT_LABEL, cx.PERMIT_LABEL, "epoch_timeline", "verified_public_source"],
        "mw_full": [10.0, 8.0, 6.0, 5.0, 4.0],
        "mw_full_raw": [10.0, 8.0, 6.0, 5.0, 4.0],
        "mw_basis": ["generator_capacity_x_kappa"] * 3 + ["epoch_timeline", "generator_capacity_x_kappa"],
        "load_history": ["three_year_ramp"] * 3 + ["epoch_timeline", "three_year_ramp"],
        "first_permit_year": [2018.0, 2014.0, 2011.0, np.nan, 2017.0],
    }).set_index("fid")
    for k, v in over.items():
        f[k] = v
    return f


# ---- dates and capacity -------------------------------------------------------------------------------------------

def test_no_corrections_change_no_value():
    f = frame()
    out, ph, rep = cx.apply_timing(f, {}, [])
    pd.testing.assert_frame_equal(out[f.columns], f)
    assert rep == {"applied": [], "load_unknown": []} and not out.load_unknown.any()


def test_a_date_sets_the_convention_and_labels_why():
    f = frame()
    out, _, _ = cx.apply_timing(f, {}, [W.date("a", 2012, 2018, 2018, ends="evidence"),       # 2019 ruled out
                                        W.date("b", 2010, 2015, 2015),                          # 2015 not ruled out
                                        W.date("c", 2011, 2012, 2011, convention_is="provisional")])
    assert out.energized_year["a"] == 2018 and out.date_basis["a"] == cx.EVIDENCE_CONVENTION_LABEL
    assert out.date_basis["b"] == cx.INTERVAL_LABEL and out.energized_year["b"] == 2015
    assert out.date_basis["c"] == cx.YEAR_BUILT_LABEL and out.energized_year["c"] == 2011
    assert out.date_inventory_year["a"] == 2019 and out.date_ends["a"] == "evidence"
    assert out.mw_full["a"] == 10.0                                    # dates move no size


def test_a_start_with_no_convention_is_load_unknown_not_zero():
    f = frame()
    out, ph, rep = cx.apply_timing(f, {}, [W.date("a", 2011, 2019, None)])
    assert bool(out.load_unknown["a"]) and pd.isna(out.energized_year["a"])
    assert out.date_basis["a"] == cx.UNRESOLVED_LABEL and out.date_inventory_year["a"] == 2019
    assert "unknown, not zero" in out.load_unknown_why["a"]
    assert rep["load_unknown"] == ["a"]
    assert not out.load_unknown[["b", "c", "e", "y"]].any()


def test_a_capacity_split_at_its_convention_enters_the_phases():
    f = frame()
    out, ph, _ = cx.apply_timing(f, {}, [W.date("a", 2011, 2019, 2011),
                                         {"fid": "a", "kind": "capacity_split", "first_share": 0.5, "convention": "late"}])
    assert ph["a"] == [(2011.0, 0.5), (2019.0, 1.0)]
    assert out.load_history["a"] == "capacity_split_at_its_convention"


def test_a_capacity_split_with_no_convention_is_load_unknown():
    f = frame()
    out, ph, _ = cx.apply_timing(f, {}, [W.date("a", 2011, 2019, None),
                                         {"fid": "a", "kind": "capacity_split", "first_share": 0.495, "rest_earliest": 2011}])
    assert bool(out.load_unknown["a"]) and "a" not in ph


def test_a_stress_field_is_ignored_by_the_inventory():
    f = frame()
    plain, _, _ = cx.apply_timing(f, {}, [W.date("a", 2014, 2014, 2014)])
    stressed, _, _ = cx.apply_timing(f, {}, [W.date("a", 2014, 2014, 2014, stress={"start": None, "label": "x"})])
    pd.testing.assert_frame_equal(plain, stressed)


def test_a_known_phase_cannot_be_dated_over():
    f = frame()
    with pytest.raises(ValueError, match="verified phased history"):
        cx.apply_timing(f, {"a": [(2010, 0.5), (2015, 1.0)]}, [W.date("a", 2011, 2019, 2011)])


def test_a_measured_history_cannot_be_dated_over():
    with pytest.raises(ValueError, match="measured or operator-reported"):
        cx.apply_timing(frame(), {}, [W.date("e", 2011, 2019, 2011)])


# ---- the year-built relabel (Joe, R1) -------------------------------------------------------------------------------

def gov(ids):
    return pd.DataFrame({"fid": ids, "record_is": ["year built"] * len(ids)})


def test_the_relabel_changes_labels_and_nothing_else():
    f = frame()
    out, ids = cx.relabel_year_built(f, gov(["y"]))
    assert ids == ["y"] and out.date_basis["y"] == cx.YEAR_BUILT_LABEL
    assert "unpursued" in out.year_built_review["y"]
    same = [c for c in f.columns if c != "date_basis"]
    pd.testing.assert_frame_equal(out[same], f[same])


def test_the_relabel_stops_on_a_row_that_is_not_sourced():
    with pytest.raises(ValueError, match="do not carry a sourced year"):
        cx.relabel_year_built(frame(), gov(["a"]))


def test_the_year_built_table_accounts_for_every_row_and_verifies_none():
    f = frame(utility_id_eia=1.0)
    f.loc["b", ["date_basis", "mw_full_raw"]] = ["verified_public_source", np.nan]
    f.loc["c", "date_basis"] = "verified_public_source"
    f2, ids = cx.relabel_year_built(f, gov(["y", "b", "c"]))
    corr = [W.date("y", 2018, 2020, 2020, convention_is="provisional")]
    t = cx.year_built_table(f2, ids, corr).set_index("fid")
    assert t["class"]["y"].startswith("two_years_differ") and t["class"]["c"].startswith("one_year")
    assert t["class"]["b"].startswith("one_year") and not t.has_size["b"]
    assert (t.status == "year built used as start by convention; not a verified operating start").all()
    with pytest.raises(ValueError, match="do not match"):
        cx.year_built_table(f2, ids, [])                               # a differing row with no provisional interval


# ---- assignment ---------------------------------------------------------------------------------------------------

def aframe():
    f = frame()
    f["utility_id_eia"] = [1.0, 1.0, 3.0, 4.0, 1.0]
    f["utility_assign"] = ["verified_by_hand", "smallest_polygon", "unique", "verified_by_hand", "verified_by_hand"]
    f["utility_candidates"] = ["1;2", "1;2", "3", "4", "1"]
    return f


def test_a_reopen_unresolves_the_site_with_exactly_its_candidates():
    out, rep = cx.apply_assignment(aframe(), [{"fid": "a", "kind": "reopen", "candidates": [1, 5]}], withdrawn={})
    assert out.utility_assign["a"] == px.REOPENED and out.utility_candidates["a"] == "1;5" and out.utility_id_eia["a"] == 1
    assert rep["reopened"] == ["a"]


def test_a_withdrawn_verification_left_in_place_stops_the_run():
    with pytest.raises(ValueError, match="withdrawn assignments still carried as verified"):
        cx.apply_assignment(aframe(), [], withdrawn={"a": "D-95"})


def test_an_assign_the_records_contradict_stops_the_run():
    with pytest.raises(ValueError, match="disagree"):
        cx.apply_assignment(aframe(), [{"fid": "a", "kind": "assign", "to": [2, "AA"]}], withdrawn={})


def test_an_assign_already_in_place_is_left_as_the_records_put_it():
    out, rep = cx.apply_assignment(aframe(), [{"fid": "a", "kind": "assign", "to": [1, "AA"]},
                                              {"fid": "b", "kind": "assign", "to": [1, "AA"]}], withdrawn={})
    assert rep["assign_already_in_place"] == ["a"] and rep["assign_applied"] == ["b"]
    assert out.utility_assign["b"] == "verified_by_hand"


def test_a_candidates_correction_adds_and_never_removes():
    out, _ = cx.apply_assignment(aframe(), [{"fid": "b", "kind": "candidates", "candidates": [1, 2, 7]}], withdrawn={})
    assert out.utility_candidates["b"] == "1;2;7" and out.utility_assign["b"] == px.WIDENED
    with pytest.raises(ValueError, match="leaves out"):
        cx.apply_assignment(aframe(), [{"fid": "b", "kind": "candidates", "candidates": [1, 7]}], withdrawn={})


# ---- locations (Joe, R8) ----------------------------------------------------------------------------------------------

def test_the_candidates_after_a_move_are_the_union_new_first():
    assert cx.union_candidates([5, 6], [6, 7]) == [5, 6, 7]
    assert cx.union_candidates([], [7]) == [7]


def test_build_inventory_relocates_and_keeps_every_old_supplier():
    gpd = pytest.importorskip("geopandas")
    from pipeline.facilities import build_inventory as bi
    fac = gpd.GeoDataFrame({"fid": ["m", "n", "f"], "lat": [29.40, 29.50, 38.8], "lon": [-98.7, -98.6, -104.8]},
                           geometry=gpd.points_from_xy([-98.7, -98.6, -104.8], [29.40, 29.50, 38.8]), crs=4326).to_crs(bi.EQUAL_AREA)
    locs = {"m": {"centroid": {"lat": 29.45, "lon": -98.75}}}
    moved, old = bi.relocate(fac, locs, {"f": "unresolved"})
    assert set(moved.location_status) == {cx.LOCATION_CONVENTION, cx.LOCATION_AS_SOURCED, cx.LOCATION_UNRESOLVED_LABEL}
    assert moved.set_index("fid").lat["m"] == 29.45 and "m" in old

    def fake_assign(pts):                                               # territory by latitude band
        ids = list(pts.fid)
        lat = pts.to_crs(4326).geometry.y.values
        return pd.DataFrame({"candidates": [[10] if y < 29.42 else [20, 30] for y in lat]}, index=ids)
    c = bi.candidates_after_relocation(moved, old, assign=fake_assign)
    assert c.candidates["m"] == [20, 30, 10]                           # the old point's supplier is kept
    assert c.candidates["n"] == [20, 30]


# ---- apply_verified's reading order -------------------------------------------------------------------------------------

def test_the_verification_pass_records_are_read_last_and_skips_are_named(tmp_path):
    for n in ("batch_0.json", "batch_c_0.json", "batch_r2_0.json", "batch_r3_0.json", "batch_v_0.json", "state_XX.json"):
        (tmp_path / n).write_text("[]")
    corr = tmp_path / "corr.json"
    corr.write_text(json.dumps([{"fid": "bi:848-0", "kind": "reopen", "candidates": [1, 2]},
                                {"fid": "bi:821-0", "kind": "assign", "to": [19325, "OR"]}]))
    wd = tmp_path / "wd.json"
    wd.write_text(json.dumps([{"fid": "bi:1123-0", "withdrawn_under": "D-61"}, {"fid": "bi:821-0", "withdrawn_under": "D-61"}]))
    plan = av.reading_plan(tmp_path, corr, wd)
    assert [s for s, _, _ in plan] == ["batches", "state_sweeps", "assignment_check", "verification_pass"]
    assert [Path(p).name for p in plan[0][1]] == ["batch_0.json", "batch_r2_0.json", "batch_r3_0.json"]
    assert [Path(p).name for p in plan[-1][1]] == ["batch_c_0.json"]
    # bi:821-0 was withdrawn and later re-verified; the corrections assign it, so its pass record is applied
    assert set(plan[-1][2]) == {"bi:848-0", "bi:1123-0", "bi:941-0"}
    assert all(not s for _, _, s in plan[:-1])


# ---- what an unknown-load row reaches (Joe, R2) -------------------------------------------------------------------------

def test_the_unknown_load_reach_names_utilities_directly_and_through_the_factor():
    inp = W.make([{"fid": "u", "state": "AA", "mw": 10, "year": 2015, "utility": 1, "candidates": "1;2"},
                  {"fid": "o", "state": "AA", "mw": 10, "year": 2010, "utility": 3}],
                 {(1, "AA"): 10, (2, "AA"): 10, (3, "AA"): 10}, epri={"AA": 0.1})
    f = inp.fac.copy()
    f.loc["u", ["energized_year", "load_unknown", "load_unknown_why"]] = [np.nan, True, "no convention"]
    f["load_unknown"] = f.load_unknown.astype(bool)
    anchor = inp.anchor.copy()
    anchor.loc["AA", "permit_twh"] = 10 * 8.76 / 1000                  # the frame counts u as nothing
    anchor.loc["AA", "factor"] = px._factor(0.1, 0.0, anchor.permit_twh["AA"])
    fy = inp.fy[inp.fy.fid != "u"]
    r = cx.unknown_load_reach(f, fy, anchor, inp.units, [W.date("u", 2011, 2019, None)], inp.measured)
    assert r["utilities_directly"] == ["1:AA", "2:AA"]
    assert r["utilities_through_the_state_factor"] == ["3:AA"]
    assert r["every_affected_utility"] == ["1:AA", "2:AA", "3:AA"]


# ---- the snapshot (real data; skipped if absent) -------------------------------------------------------------------------

def test_the_frame_view_reads_corrections_as_the_frozen_inputs_do():
    if not (SNAP / "facilities.parquet").exists():
        pytest.skip(f"{SNAP} is absent: the orchestrator snapshots data/interim before the rebuild")
    from pipeline.facilities import buildout
    fac = pd.read_parquet(SNAP / "facilities.parquet").set_index("fid")
    corr = cx.load()
    _, timing = cx.split(corr)
    via_view = px.parse_corrections(cx.stripped(timing), cx.view(fac, buildout.phases_by_site(buildout.load())))
    assert sorted(via_view) == sorted({c["fid"] for c in timing})


# ---- the five Oregon first-fuel years (D-96 reading (1)) ------------------------------------------------------------

def test_a_first_fuel_year_is_not_applied_as_a_start_in_step_d():
    for fid in cx.FIRST_FUEL_NOT_A_START:
        assert av.first_fuel_is_not_a_start(fid, "batch_r3c_1.json", step_d=True)
        assert not av.first_fuel_is_not_a_start(fid, "batch_r3c_1.json", step_d=False)   # the 2026-11-14 reproduction
        assert not av.first_fuel_is_not_a_start(fid, "batch_r2_3.json", step_d=True)     # other records still apply
    assert not av.first_fuel_is_not_a_start("bi:841-0", "batch_r3c_1.json", step_d=True)
    assert set(cx.FIRST_FUEL_NOT_A_START) == {"bi:819-0", "bi:820-0", "bi:822-0", "bi:823-0", "bi:846-0"}


def test_the_build_report_names_the_five_and_stops_if_one_still_carries_its_first_fuel_year():
    """After apply_timing the five carry their date entries' intervals; the year the build had before the entries were
    applied (date_inventory_year) must be the permit-based year, never the first-fuel year."""
    ids = list(cx.FIRST_FUEL_NOT_A_START)
    f = pd.DataFrame({"first_permit_year": [2018.0] * 5, "energized_year": [2019.0] * 5,
                      "date_inventory_year": [2019.0] * 5, "date_rule": ["interval"] * 5,
                      "date_earliest": [None, 2018, None, None, None], "date_latest": [2019] * 5,
                      "date_convention": [2019] * 5, "date_ends": ["tested"] * 5,
                      "date_basis": [cx.INTERVAL_LABEL] * 5}, index=ids)
    gov = pd.DataFrame({"fid": ids, "inventory_year": [2018] * 5})
    rep = cx.first_fuel_report(f, gov)
    assert [r["permit_based_year"] for r in rep] == [2019] * 5
    assert [r["first_fuel_year_set_aside"] for r in rep] == [2018] * 5
    assert [r["dated_by"] for r in rep] == ["its date entry in the corrections file in force"] * 5
    assert rep[1]["interval"] == {"earliest": 2018, "latest": 2019, "convention": 2019, "ends": "tested"}
    f.loc[ids[0], ["date_inventory_year", "date_basis"]] = [2018.0, cx.EVIDENCE_CONVENTION_LABEL]
    with pytest.raises(ValueError, match="permit-based year"):
        cx.first_fuel_report(f, gov)


def test_the_build_report_stops_if_one_of_the_five_has_no_date_entry_applied():
    ids = list(cx.FIRST_FUEL_NOT_A_START)
    f = pd.DataFrame({"first_permit_year": [2018.0] * 5, "energized_year": [2019.0] * 5,
                      "date_inventory_year": [None] * 5, "date_rule": [None] * 5,
                      "date_basis": [cx.PERMIT_LABEL] * 5}, index=ids)
    gov = pd.DataFrame({"fid": ids, "inventory_year": [2018] * 5})
    with pytest.raises(ValueError, match="date entry"):
        cx.first_fuel_report(f, gov)


# ---- the five Oregon rows' date entries (Joe, Stop 3, 2026-11-18) ----------------------------------------------------

OREGON_IN_FORCE = {          # fid: (earliest, latest = convention); all "tested", never not possible, no provisional mark
    "bi:820-0": (2018, 2019),
    "bi:823-0": (None, 2019),
    "bi:822-0": (None, 2019),
    "bi:819-0": (None, 2022),
    "bi:846-0": (None, 2022),
}


def test_the_corrections_file_in_force_dates_the_five_oregon_rows_by_the_evidence_based_rule():
    """A new-source construction permit on file bounds bi:820-0 not before 2018; the other four have no supported lower
    bound and are open below. Every late end is the permit-based year, a labelled convention and a tested end. First
    fuel moves nothing."""
    corr = [c for c in cx.load() if c["fid"] in OREGON_IN_FORCE]
    assert sorted(c["fid"] for c in corr) == sorted(OREGON_IN_FORCE)
    for c in corr:
        lo, hi = OREGON_IN_FORCE[c["fid"]]
        assert c["kind"] == "date"
        assert (c["earliest"], c["latest"], c["convention"]) == (lo, hi, hi)
        assert c["ends"] == "tested" and c["never_is_possible"] is False and "convention_is" not in c and "stress" not in c
        w = c["why"]
        assert "permit-based" in w and "labelled convention" in w and "tested" in w and "first generator fuel" in w.lower()
        assert ("not before 2018" in w) if lo else ("open below" in w)
    assert "new source" in next(c for c in corr if c["fid"] == "bi:820-0")["why"]


def test_apply_verified_main_consults_the_first_fuel_exclusion_before_a_year():
    import inspect
    src = inspect.getsource(av.main)
    assert "if first_fuel_is_not_a_start(fid, source):" in src
    assert src.index("first_fuel_is_not_a_start(fid, source)") < src.index('o["energized_year"] = int(r["energized_year"])')
    assert 'absorb(r, r["fid"], st, r.get("group", "big"), Path(p).name)' in src
