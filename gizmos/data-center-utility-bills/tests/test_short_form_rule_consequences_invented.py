"""Tests on invented frames for pipeline/analysis/short_form_rule_consequences.py (session 24, job 2). Each alternative
has a known answer planted in the world below; tests ending in `_can_fail` make a deliberate break in the test process
and show the check then fails. Nothing here reads data/.

World, window 2015 to 2020. The table has a filler row (99, ZZ) in 2015 to 2018 and 2020, so every window year but 2019
is covered.
  A (1, TX)  frame 2015-2020; a table row in 2017; 2019 flag missing.
  B (1, OK)  frame 2017, 2018; no table row (the other state of utility 1).
  C (2, TX)  frame 2015-2018; a table row in 2020, a year it is not in the frame.
  D (3, TX)  frame 2018-2020; 2019 flag true; no table row.
  E (4, TX)  frame 2017-2019; 2019 flag missing.
  F (5, TX)  frame 2018-2020; no 2019 row in the flags file.
  G (6, TX)  2015, 2016 before the three-year count only (two years: out).
  (7, TX)    not in the frame; 2019 flag true; table rows in 2018 and 2020.
Residential sales on every frame unit-year but A's 2017.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pd = pytest.importorskip("pandas")

from pipeline.analysis import short_form_rule_consequences as src  # noqa: E402

W = (2015, 2020)
FRAME_UNITS = {(1, "TX"): range(2015, 2021), (1, "OK"): (2017, 2018), (2, "TX"): range(2015, 2019),
               (3, "TX"): (2018, 2019, 2020), (4, "TX"): (2017, 2018, 2019), (5, "TX"): (2018, 2019, 2020)}


def _frame(pre=False):
    rows = [(u, s, y) for (u, s), ys in FRAME_UNITS.items() for y in ys]
    if pre:
        rows += [(6, "TX", 2015), (6, "TX", 2016)]
    return pd.DataFrame(rows, columns=["utility_id_eia", "state", "year"]).astype({"utility_id_eia": "int64",
                                                                                   "year": "int64"})


def _table():
    rows = [(99, "ZZ", y) for y in (2015, 2016, 2017, 2018, 2020)]
    rows += [(1, "TX", 2017), (2, "TX", 2020), (7, "TX", 2018), (7, "TX", 2020)]
    t = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year"])
    t["state"] = t.state.astype("string")
    return t


def _flags():
    return pd.DataFrame({"utility_id_eia": [1, 3, 4, 7], "state": ["TX", "TX", "TX", "TX"], "year": [2019] * 4,
                         "short_form": pd.array([None, True, None, True], dtype="boolean")})


def _q():
    f = _frame(pre=True)
    f["entity_type"] = "Cooperative"
    f["res_mwh"] = [None if (u, s, y) == (1, "TX", 2017) else 5.0 for u, s, y in zip(f.utility_id_eia, f.state, f.year)]
    return f


def _run():
    return src.consequences(_frame(), _frame(pre=True), _table(), _flags(), _q(), W)


KNOWN = {  # pairing, d option -> (direct removed total, utility-states entirely, utilities entirely)
    ("years_filed|by_utility_state", "d1"): (2, 0, 0),
    ("years_filed|by_utility", "d1"): (3, 0, 0),
    ("ever_filed|by_utility_state", "d1"): (13, 3, 2),
    ("ever_filed|by_utility", "d1"): (15, 4, 3),
    ("years_filed|by_utility_state", "d2"): (1, 0, 0),
    ("years_filed|by_utility", "d2"): (2, 0, 0),
    ("ever_filed|by_utility_state", "d2"): (10, 2, 1),
    ("ever_filed|by_utility", "d2"): (12, 3, 2),
}
D_NAME = {"d1": "d1_flags_as_source_true_removed_missing_kept", "d2": "d2_no_exclusion_in_2019"}


def _mismatches(out) -> list:
    bad = []
    for (pairing, d), want in KNOWN.items():
        x = out["pairings_of_a_and_b"][pairing][D_NAME[d]]["directly_on_the_frame"]
        got = (x["unit_years_removed_total"], x["utility_states_removed_entirely"], x["utilities_removed_entirely"])
        if got != want:
            bad.append((pairing, d, got, want))
    return bad


def test_each_alternative_known_answer():
    assert _mismatches(_run()) == []


def test_known_answer_can_fail():
    """Break: utility 1's 2017 table row removed in the test process; several known answers then fail."""
    t = _table()
    t = t[~((t.utility_id_eia == 1) & (t.year == 2017))]
    out = src.consequences(_frame(), _frame(pre=True), t, _flags(), _q(), W)
    assert _mismatches(out) != []


def test_by_year_and_residential_and_three_year_recount():
    out = _run()
    a = out["pairings_of_a_and_b"]["years_filed|by_utility_state"]["d1_flags_as_source_true_removed_missing_kept"]
    d = a["directly_on_the_frame"]
    assert d["unit_years_removed_by_year"] == {"2015": 0, "2016": 0, "2017": 1, "2018": 0, "2019": 1, "2020": 0}
    assert d["removed_unit_years_with_residential_sales_in_the_quantities"] == 1   # A 2017 has none, D 2019 has
    r = a["with_the_three_year_count_taken_again_after_the_exclusion"]
    # D keeps 2018 and 2020 only, two years, and leaves at the recount; G leaves as before
    assert r["unit_years_remaining"] == 17 and r["unit_years_removed_total"] == 4
    assert r["utilities_removed_entirely"] == 1 and r["utility_states_removed_entirely"] == 1
    assert r["unit_years_removed_by_year"] == {"2015": 0, "2016": 0, "2017": 1, "2018": 1, "2019": 1, "2020": 1}


def test_mu_codes_named():
    out = _run()
    p = out["pairings_of_a_and_b"]
    assert p["years_filed|by_utility_state"]["reconciliation_mu_code"] == "unit_years_filed"
    assert p["ever_filed|by_utility"]["reconciliation_mu_code"] == "utilities_ever_filed"
    assert "not coded" in p["years_filed|by_utility"]["reconciliation_mu_code"]
    assert "not coded" in p["ever_filed|by_utility_state"]["reconciliation_mu_code"]


def test_stopping_and_2019_counts():
    out = _run()
    s = out["stopping_options"]
    # non-2019 frame unit-years 17; with a row at utility-state level: A 2017 -> 16; by utility also B 2017 -> 15
    assert s["c_no_row_in_a_covered_year_stops"]["by_utility_state"]["unit_years_that_would_stop_total"] == 16
    assert s["c_no_row_in_a_covered_year_stops"]["by_utility"]["unit_years_that_would_stop_total"] == 15
    assert s["d_2019_missing_flag_stops_frame_unit_years"] == 2
    assert s["d_2019_no_flags_row_stops_frame_unit_years"] == 1
    d = out["d_2019"]
    assert d["frame_unit_years_in_2019"] == 4 and d["frame_2019_unit_years_flagged_true"] == 1
    assert d["d3_continuity_of_the_utility_states_flagged_true_in_2019"] == {
        "flagged_true": 2, "with_a_table_row_in_both_2018_and_2020": 1, "in_2018_only": 0, "in_2020_only": 0,
        "in_neither": 1}
    assert out["ever_filed_by_utility_state_units_in_the_frame_with_some_window_filing"] == 2
    assert out["ever_filed_by_utility_state_units_whose_window_filings_all_fall_in_years_they_are_not_in_the_frame"] == 1
    assert out["window_years_other_than_2019_the_table_does_not_cover"] == []


def test_frame_counts_and_paper_figures():
    out = _run()
    assert out["frame"]["unit_years"] == 21 and out["frame"]["utilities"] == 5
    assert out["frame"]["before_the_three_year_count"]["unit_years"] == 23
    assert out["paper_printed_figures"]["retained_utilities"] == 1798
    assert "never a target" in out["paper_printed_figures"]["note"]
    # brought to Joe's ruling of 2026-11-20 (D-115), session 25: the file stays a count of the alternatives and names
    # the one he adopted
    assert "Joe adopted" in src.WHAT_THIS_IS and "D-115" in src.WHAT_THIS_IS and "not ranked" in src.WHAT_THIS_IS
    assert "no part of any reason" in src.WHAT_THIS_IS
    a = out["adopted_by_joe_2026_11_20_d115"]
    assert a["pairing"] == "years_filed|by_utility_state" and a["year_2019"] == D_NAME["d1"]
    assert a["pairing"] in out["pairings_of_a_and_b"] and a["year_2019"] in out["pairings_of_a_and_b"][a["pairing"]]
    assert out["pairings_of_a_and_b"][a["pairing"]]["reconciliation_mu_code"] == a["reconciliation_mu_code"]


def test_the_adopted_alternative_carries_the_adopted_choices():
    """The alternative named as adopted is counted under exactly short_form_filers.ADOPTED_ROW_U_CHOICES."""
    out = _run()
    a = out["adopted_by_joe_2026_11_20_d115"]
    kw = out["pairings_of_a_and_b"][a["pairing"]][a["year_2019"]]["choices_as_supplied"]
    # the window is the invented world's (2015 to 2020); every other choice is the adopted one
    assert {k: v for k, v in kw.items() if k != "window"} == {k: v for k, v in src.sff.ADOPTED_ROW_U_CHOICES.items()
                                                             if k != "window"}


def test_the_adopted_alternative_check_can_fail(monkeypatch):
    """Break: the named adopted alternative pointed at d2 in the test process; its choices then differ from the
    adopted ones."""
    monkeypatch.setattr(src, "ADOPTED", {**src.ADOPTED, "year_2019": D_NAME["d2"]})
    out = _run()
    a = out["adopted_by_joe_2026_11_20_d115"]
    kw = out["pairings_of_a_and_b"][a["pairing"]][a["year_2019"]]["choices_as_supplied"]
    assert {k: v for k, v in kw.items() if k != "window"} != {k: v for k, v in src.sff.ADOPTED_ROW_U_CHOICES.items()
                                                             if k != "window"}


def test_no_ranking_language_in_the_module():
    text = Path(src.__file__).read_text().lower()
    for w in ("closest", "best match", "recommend", "preferred", "closer to the paper"):
        assert w not in text


# ---- counts added 2026-11-20 (follow-up): 2019 unit-years kept, units an 'ever' reading reaches ----------------------
def _table_with_neighbours():
    """The world's table plus E (4, TX) rows in 2018 and 2020 and F (5, TX) a row in 2020."""
    t = pd.concat([_table(), pd.DataFrame({"utility_id_eia": [4, 4, 5], "state": ["TX"] * 3,
                                           "year": [2018, 2020, 2020]})], ignore_index=True)
    t["state"] = t.state.astype("string")
    return t


def _added_known(out) -> list:
    bad = []
    k = out["frame_2019_unit_years_not_flagged_by_table_rows_in_2018_and_2020"]
    # not flagged true in 2019: A (missing flag, no neighbour rows), E (missing flag, rows 2018 and 2020),
    # F (no flags row, a row in 2020)
    if k["with_a_flags_row_whose_flag_is_missing"] != {"unit_years": 2, "table_row_in_both_2018_and_2020": 1,
                                                       "in_2018_only": 0, "in_2020_only": 0, "in_neither": 1}:
        bad.append("missing")
    if k["with_no_flags_row"] != {"unit_years": 1, "table_row_in_both_2018_and_2020": 0, "in_2018_only": 0,
                                  "in_2020_only": 1, "in_neither": 0}:
        bad.append("no row")
    return bad


def test_2019_kept_by_neighbour_rows_known_answer():
    out = src.consequences(_frame(), _frame(pre=True), _table_with_neighbours(), _flags(), _q(), W)
    assert _added_known(out) == []
    assert "establishes nothing about 2019" in \
        out["frame_2019_unit_years_not_flagged_by_table_rows_in_2018_and_2020"]["what_this_is"]


def test_2019_kept_by_neighbour_rows_can_fail():
    """Break: the neighbour rows are left out of the table in the test process; the known answer then fails."""
    out = src.consequences(_frame(), _frame(pre=True), _table(), _flags(), _q(), W)
    assert _added_known(out) != []


def _ever_known(out) -> list:
    bad = []
    e = out["frame_unit_years_of_units_with_a_table_row_in_some_window_year"]
    # units reached: A (table row 2017; frame 2015-2020) and C (table row 2020; frame 2015-2018)
    if e["all_the_units_table_rows_later_than_this_year"] != {"2015": 2, "2016": 2, "2017": 1, "2018": 1,
                                                              "2019": 0, "2020": 0}:
        bad.append("later")
    if e["not_all_later"] != {"2015": 0, "2016": 0, "2017": 1, "2018": 1, "2019": 1, "2020": 1}:
        bad.append("not later")
    if e["total"] != 10:
        bad.append("total")
    f = out["units_reached_by_ever_whose_first_table_year_is_2020_and_frame_years_all_2019_or_earlier"]
    if f != {"first_table_year_over_the_whole_table_2012_to_2025": 1, "first_table_year_within_the_window": 1,
             "of_units_reached_by_ever": 2}:
        bad.append("first 2020")
    return bad


def test_ever_reach_by_year_known_answer():
    assert _ever_known(_run()) == []


def test_ever_reach_can_fail():
    """Break: C's table row moved from 2020 to 2017 in the test process; the known answer then fails."""
    t = _table()
    t.loc[(t.utility_id_eia == 2) & (t.year == 2020), "year"] = 2017
    out = src.consequences(_frame(), _frame(pre=True), t, _flags(), _q(), W)
    assert _ever_known(out) != []


# ---- Joe's ruling of 2026-11-20 on what row U's ownership type is (D-119) --------------------------------------------
def _src_ownership_problems(texts: dict) -> list:
    bad = []
    for name, t in texts.items():
        t = " ".join(str(t).split()).replace('" "', "")
        rest = t.replace("not the latest year-by-year EIA classification", "").lower()
        for phrase in ("latest", "most recent", "last nonmissing reported", "caller's choice"):
            if phrase in rest:
                bad.append((name, phrase))
        if "modal" not in t or "D-119" not in t:
            bad.append((name, "no 'modal' or no D-119"))
    return bad


def test_d119_the_frame_texts_describe_the_modal_type():
    import inspect
    cons = inspect.getsource(src.consequences)
    texts = {"module": src.__doc__.split("The frame counted against")[1].split("Removals")[0],
             "frame_what_it_is": cons.split('"frame": {')[1].split('"unit_years"')[0]}
    assert _src_ownership_problems(texts) == []


def test_d119_the_frame_texts_check_can_fail():
    """Break: the D-117 wording given to the same check in the test process."""
    old = "(scheme U, the last nonmissing reported entity type over 2001 to 2025, D-117)"
    assert _src_ownership_problems({"x": old}) == [("x", "last nonmissing reported"), ("x", "no 'modal' or no D-119")]
