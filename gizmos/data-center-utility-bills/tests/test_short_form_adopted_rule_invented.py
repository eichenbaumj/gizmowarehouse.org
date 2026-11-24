"""Row U's Short Form rule as Joe adopted it on 2026-11-20 (ledger entry D-115), on invented inputs only (session 25,
job 1). Nothing here reads data/: every frame is built in the test, and where reconciliation_mu.main() is called its
paths are pointed at invented files in pytest's tmp_path and pandas' parquet reader is replaced by one that refuses.

His words: "Exclude a utility-state-year where the Short Form table records a filing, or, for 2019, the operational
flag is true. Keep other unit-years as 'kept with no record of a filing,' without claiming non-filing. Apply the
three-year requirement after exclusion. Retain the explicitly incomplete 2019 exclusion and its missing-flag/no-row
counts."

The world, row U's window 2015 to 2024. The filer table has a filler row (99, ZZ) in every window year but 2019, as the
real table has rows in every window year but 2019.
  A (1, TX)  2015-2024; a table row in 2017 (a record of a filing); its 2019 flag missing.
  B (2, TX)  2017, 2018, 2019; its 2019 flag true. 2019 leaves directly, then 2017 and 2018 leave through the
             three-year requirement (one flagged row directly, two other years through the requirement).
  C (3, TX)  2018-2020; its 2019 flag missing.
  D (4, TX)  2018-2020; no 2019 row in the flags file.
  E (5, TX)  2015, 2016 only: out at the three-year count, before any exclusion.
  F (6, TX)  2019 only, flag true: out at the three-year count whatever the exclusion.
  G (7, TX)  2020-2022, a table row in 2020; (7, OK) 2020-2022 with no row. By utility-state, OK stays.
  H (8, TX)  2015-2024 with no entity type: no ownership class, never in the frame.
Tests whose names end in `_can_fail` make a deliberate break in the test process (a monkeypatch, or an input changed
in the test) and show that the same check then fails.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pd = pytest.importorskip("pandas")

from pipeline.analysis import reconciliation_mu as mu  # noqa: E402
from pipeline.analysis import short_form_filers as sff  # noqa: E402

KEY = ["utility_id_eia", "state"]
W = (2015, 2024)
UNITS = {(1, "TX"): range(2015, 2025), (2, "TX"): (2017, 2018, 2019), (3, "TX"): (2018, 2019, 2020),
         (4, "TX"): (2018, 2019, 2020), (5, "TX"): (2015, 2016), (6, "TX"): (2019,), (7, "TX"): (2020, 2021, 2022),
         (7, "OK"): (2020, 2021, 2022)}
NO_TYPE = {(8, "TX"): range(2015, 2025)}

JOES_WORDS = ("Exclude a utility-state-year where the Short Form table records a filing, or, for 2019, the operational "
              "flag is true. Keep other unit-years as 'kept with no record of a filing,' without claiming non-filing. "
              "Apply the three-year requirement after exclusion. Retain the explicitly incomplete 2019 exclusion and its "
              "missing-flag/no-row counts.")
EXPECTED_CHOICES = {"window": (2015, 2024), "years": "years_filed", "level": "utility_state",
                    "no_row_in_covered_year": "kept_no_record_of_a_filing", "year_not_covered": "no_exclusion_labelled",
                    "year_2019": "flags_true_excluded_missing_kept", "no_2019_flags_row": "kept_no_record_of_a_filing"}
# A unit-year with no record must never be described as not having filed.
FORBIDDEN = re.compile(r"did not file|not a filer|non-filer\b|nonfiler|not filed|three filings", re.IGNORECASE)


def frame_pre() -> pd.DataFrame:
    rows = [(u, s, y) for (u, s), ys in UNITS.items() for y in ys]
    return pd.DataFrame(rows, columns=KEY + ["year"]).astype({"utility_id_eia": "int64", "year": "int64"})


def table() -> pd.DataFrame:
    rows = [(99, "ZZ", y) for y in range(2015, 2025) if y != 2019] + [(1, "TX", 2017), (7, "TX", 2020)]
    t = pd.DataFrame(rows, columns=KEY + ["year"])
    t["state"] = t.state.astype("string")
    return t


def flags() -> pd.DataFrame:
    return pd.DataFrame({"utility_id_eia": [1, 2, 3, 6, 1], "state": ["TX"] * 5, "year": [2019, 2019, 2019, 2019, 2018],
                         "short_form": pd.array([None, True, None, True, None], dtype="boolean"),
                         "data_observed": [True] * 5})


def quantities() -> pd.DataFrame:
    rows = [(u, s, y, "Cooperative") for (u, s), ys in UNITS.items() for y in ys]
    rows += [(u, s, y, None) for (u, s), ys in NO_TYPE.items() for y in ys]
    return pd.DataFrame(rows, columns=KEY + ["year", "entity_type"])


def _get(r, u, s, y):
    v = r[(r.utility_id_eia == u) & (r.state == s) & (r.year == y)]
    assert len(v) == 1
    return (None if pd.isna(v.short_form.iloc[0]) else bool(v.short_form.iloc[0])), v.reading.iloc[0]


# ---- the adopted choices are what his words say ---------------------------------------------------------------------
def _choices_mismatch() -> list:
    bad = []
    if dict(sff.ADOPTED_ROW_U_CHOICES) != EXPECTED_CHOICES:
        bad.append("choices")
    if tuple(sff.ADOPTED_ROW_U_CHOICES["window"]) != tuple(mu.RYU_WINDOW):
        bad.append("window")
    if sff.ADOPTED_ROW_U_MU_CODE != "unit_years_filed" or mu.U_SHORT_FORM_ADOPTED_CODE != "unit_years_filed":
        bad.append("code")
    if sff.ADOPTED_ROW_U_WORDS != JOES_WORDS or "D-115" not in sff.ADOPTED_ROW_U_RULING:
        bad.append("words")
    return bad


def test_the_adopted_choices_are_joes_words():
    assert _choices_mismatch() == []
    with pytest.raises(TypeError):                       # one named place, not editable in passing
        sff.ADOPTED_ROW_U_CHOICES["years"] = "ever_filed"
    lab = mu.U_SHORT_FORM_ADOPTED_LABEL
    for phrase in ("D-115", "a record shows a Short Form filing", "kept with no record of a filing",
                   "three-year count is taken after the exclusion", "2019 exclusion is explicitly incomplete",
                   "missing flag", "no flags row", "does not establish non-filing", "not the paper's sample",
                   "comparison-only", "Outcome availability"):
        assert phrase in lab, phrase
    assert not FORBIDDEN.search(lab)
    assert mu.U_SHORT_FORM_NOT_APPLIED_LABEL.startswith("No Short Form exclusion is applied")   # unchanged label
    assert "none_in_outcome_frame" in mu.SHORT_FORM_RULES and mu.U_SHORT_FORM_ADOPTED_CODE in mu.SHORT_FORM_RULES


def test_the_adopted_choices_can_fail(monkeypatch):
    """Break: the stored choices given the stopping 2019 option in the test process; the check then fails."""
    monkeypatch.setattr(sff, "ADOPTED_ROW_U_CHOICES", {**EXPECTED_CHOICES, "year_2019": "flags_missing_stops"})
    assert _choices_mismatch() == ["choices"]


# ---- each case of the flags, with a known answer --------------------------------------------------------------------
def _case_mismatches(r) -> list:
    want = {(1, "TX", 2017): True,      # a table row
            (2, "TX", 2019): True,      # a 2019 flag of true
            (3, "TX", 2019): False,     # a missing 2019 flag: kept with no record of a filing
            (4, "TX", 2019): False,     # no 2019 flags row: kept with no record of a filing
            (1, "TX", 2018): False,     # no table row in a covered year: kept with no record of a filing
            (7, "OK", 2020): False}     # the other state of a utility with a table row (by utility-state)
    return [k for k, v in want.items() if _get(r, *k)[0] is not v]


def test_each_case_of_the_adopted_flags():
    r = sff.adopted_row_u_flags(frame_pre(), table(), flags())
    assert _case_mismatches(r) == []
    assert len(r) == len(frame_pre()) and int(r.short_form.sum()) == 4      # A 2017, B 2019, F 2019, G TX 2020
    assert "missing flag" in _get(r, 3, "TX", 2019)[1] and "no record" in _get(r, 3, "TX", 2019)[1]
    assert "no row in the flags file" in _get(r, 4, "TX", 2019)[1] and "no record" in _get(r, 4, "TX", 2019)[1]
    assert not any(FORBIDDEN.search(t) for t in r.reading)
    # the same as sample_flags_from_table with the choices spelled out
    spelled = sff.sample_flags_from_table(frame_pre(), table(), flags(), **EXPECTED_CHOICES)
    assert r.equals(spelled)


def test_table_row_case_can_fail():
    """Break: A's 2017 table row left out of the table in the test process; that case then fails."""
    t = table()
    t = t[~((t.utility_id_eia == 1) & (t.year == 2017))]
    assert (1, "TX", 2017) in _case_mismatches(sff.adopted_row_u_flags(frame_pre(), t, flags()))


def test_flag_true_case_can_fail():
    """Break: B's 2019 flag made missing in the test process; that case then fails."""
    f = flags()
    f.loc[(f.utility_id_eia == 2), "short_form"] = pd.NA
    assert (2, "TX", 2019) in _case_mismatches(sff.adopted_row_u_flags(frame_pre(), table(), f))


def test_missing_flag_case_can_fail(monkeypatch):
    """Break: the stored 2019 choice switched to the stopping option in the test process; the missing flag then
    stops the flags in words instead of being kept."""
    monkeypatch.setattr(sff, "ADOPTED_ROW_U_CHOICES", {**EXPECTED_CHOICES, "year_2019": "flags_missing_stops"})
    with pytest.raises(ValueError, match="missing flag"):
        sff.adopted_row_u_flags(frame_pre(), table(), flags())


def test_no_flags_row_case_can_fail(monkeypatch):
    """Break: the stored no-flags-row choice switched to 'stop' in the test process; D's 2019 then stops."""
    monkeypatch.setattr(sff, "ADOPTED_ROW_U_CHOICES", {**EXPECTED_CHOICES, "no_2019_flags_row": "stop"})
    with pytest.raises(ValueError, match="no row in the flags file"):
        sff.adopted_row_u_flags(frame_pre(), table(), flags())


def test_by_utility_state_case_can_fail(monkeypatch):
    """Break: the stored level switched to 'utility' in the test process; (7, OK) 2020 then leaves."""
    monkeypatch.setattr(sff, "ADOPTED_ROW_U_CHOICES", {**EXPECTED_CHOICES, "level": "utility"})
    assert (7, "OK", 2020) in _case_mismatches(sff.adopted_row_u_flags(frame_pre(), table(), flags()))


# ---- the three-year requirement after the exclusion, and the counts reported apart ----------------------------------
def _yrs(d: dict) -> dict:
    return {k: v for k, v in d.items() if v}


def _sample_mismatches(s) -> list:
    bad = []
    fr = s["frame_with_no_exclusion"]
    if (fr["unit_years"], fr["utility_states"], fr["utilities"]) != (25, 6, 5):
        bad.append("frame")
    if (fr["before_the_three_year_count"]["unit_years"], fr["before_the_three_year_count"]["utilities"]) != (28, 7):
        bad.append("frame before the count")
    d = s["leaving_directly_where_a_record_shows_a_filing"]
    if _yrs(d["unit_years_by_year"]) != {"2017": 1, "2019": 1, "2020": 1} or d["unit_years_total"] != 3:
        bad.append("direct")
    if _yrs(d["utilities_by_year"]) != {"2017": 1, "2019": 1, "2020": 1} or d["utilities"] != 3:
        bad.append("direct utilities")
    t = s["leaving_through_the_three_year_requirement_after_the_exclusion"]
    if _yrs(t["unit_years_by_year"]) != {"2017": 1, "2018": 1} or t["unit_years_total"] != 2 or t["utilities"] != 1:
        bad.append("three-year")
    f = s["sample_under_the_adopted_rule"]
    if (f["unit_years"], f["utility_states"], f["utilities"]) != (20, 5, 4):
        bad.append("sample")
    if (f["utility_states_removed_entirely_from_the_frame"], f["utilities_removed_entirely_from_the_frame"]) != (1, 1):
        bad.append("removed entirely")
    o = s["in_run_u_steps_order"]
    if (o["rows_before_the_three_year_count"], o["flagged_unit_years_among_them"], o["after_the_short_form_filter"],
            o["after_the_three_year_count"]) != (28, 4, 24, 20):
        bad.append("code order")
    y = s["year_2019_explicitly_incomplete"]
    if y["in_the_frame_with_no_exclusion"] != {"unit_years_in_2019": 4, "flagged_true": 1,
                                               "kept_with_no_record_either_way_missing_flag": 2,
                                               "kept_with_no_record_either_way_no_flags_row": 1}:
        bad.append("2019 in the frame")
    if y["in_the_sample_under_the_adopted_rule"] != {"unit_years_in_2019": 3, "flagged_true": 0,
                                                     "kept_with_no_record_either_way_missing_flag": 2,
                                                     "kept_with_no_record_either_way_no_flags_row": 1}:
        bad.append("2019 in the sample")
    return bad


def test_the_three_year_requirement_is_applied_after_the_exclusion():
    s = sff.adopted_row_u_sample(frame_pre(), table(), flags())
    assert _sample_mismatches(s) == []
    # B: one flagged unit-year leaves directly, and its two other years leave through the three-year requirement.
    # Taking the count before the exclusion only, and not again after it, would keep B's 2017 and 2018.
    pre = frame_pre()
    counted_first, _ = mu._min_years(pre, 3, "utility")
    fl = sff.adopted_row_u_flags(pre, table(), flags())
    wrong, _ = mu._u_drop_short_form(counted_first, mu.ryu_spec("unit_years_filed"), fl, W)
    assert len(wrong) == 22 and {2017, 2018} <= set(wrong[wrong.utility_id_eia == 2].year)
    assert s["in_run_u_steps_order"]["same_sample_as_reported_apart"] is True
    assert s["label"] == mu.U_SHORT_FORM_ADOPTED_LABEL and s["reconciliation_mu_code"] == "unit_years_filed"
    assert s["choices_supplied_to_sample_flags_from_table"] == {**EXPECTED_CHOICES, "window": [2015, 2024]}


def test_three_year_requirement_can_fail(monkeypatch):
    """Break: reconciliation_mu._min_years made the identity in the test process; the frame, the leavers through the
    three-year requirement and the sample then differ from the known answer."""
    monkeypatch.setattr(mu, "_min_years", lambda o, n, level: (o, "count off"))
    bad = _sample_mismatches(sff.adopted_row_u_sample(frame_pre(), table(), flags()))
    assert "three-year" in bad and "sample" in bad


def test_2019_counts_can_fail():
    """Break: C's 2019 flag set to true in the test process; the 2019 counts then differ."""
    f = flags()
    f.loc[(f.utility_id_eia == 3) & (f.year == 2019), "short_form"] = True
    bad = _sample_mismatches(sff.adopted_row_u_sample(frame_pre(), table(), f))
    assert "2019 in the frame" in bad and "2019 in the sample" in bad


def test_the_two_computations_must_agree(monkeypatch):
    """The sample is computed in run_u_step's order and reported apart; if they disagreed nothing would be reported.
    Break: the Short Form filter replaced in the test process by one that drops nothing; the check then stops."""
    monkeypatch.setattr(mu, "_u_drop_short_form", lambda o, spec, f, w: (o, "nothing dropped"))
    with pytest.raises(ValueError, match="differs between run_u_step's order and the reduction reported apart"):
        sff.adopted_row_u_sample(frame_pre(), table(), flags())


# ---- reconciliation_mu's row U block, built from the records passed in ----------------------------------------------
def _strings(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def _block():
    # The classes as reconciliation_mu.main now builds them (Joe, 2026-11-20, D-117): adopted_row_u_ownership_classes,
    # which searches exactly 2001 to 2025. A filler unit with no entity type, outside the 50 states and DC, covers the
    # years outside 2015 to 2024 in the classes' input only; the block itself is given quantities() as before, so no
    # count moves (brought along 2026-11-20, session 26).
    q = quantities()
    pad = pd.DataFrame([(999, "ZZ", y, None) for y in list(range(2001, 2015)) + [2025]], columns=KEY + ["year",
                                                                                                       "entity_type"])
    own_u = mu.adopted_row_u_ownership_classes(pd.concat([q, pad], ignore_index=True)).set_index(KEY).ownership_class
    return mu._short_form_for_row_u(q, own_u, flags(), table())


def test_row_u_block_reports_the_sample_under_the_adopted_rule():
    b = _block()
    s = b["sample_under_the_adopted_short_form_rule"]
    assert _sample_mismatches(s) == []                         # unit 8, with no ownership class, never enters
    assert b["row_u_quantity_sample_in_the_window"]["unit_years"] == 25
    assert b["filer_table_rows"] == len(table())
    assert "D-115" in b["status"] and mu.U_SHORT_FORM_ADOPTED_LABEL in b["status"]
    assert "STOPPED" not in b["status"] and "what_2019_alone_shows_NOT_the_rule_applied" not in b
    assert "explicitly incomplete" in s["year_2019_explicitly_incomplete"]["statement"]
    assert "not the paper's" in s["not_the_papers_sample"] and "comparison-only" in s["comparison_only"]
    p = s[sff.PAPER_FIGURE_KEY]
    assert p["retained_utilities"] == 1798 and p["short_form_group"] == "approximately 560"
    assert "never a target" in p["note"]
    assert [t for t in _strings(b) if FORBIDDEN.search(t)] == []
    json.dumps(b)                                              # the block is writable as it stands


def test_forbidden_wording_scan_can_fail():
    """Break: a sentence that reads an absent row as not having filed is planted into the block in the test process;
    the scan then finds it."""
    b = _block()
    b["sample_under_the_adopted_short_form_rule"]["planted"] = "these 193 unit-years did not file"
    assert [t for t in _strings(b) if FORBIDDEN.search(t)] != []


# ---- main stops in words when the filer table is missing ------------------------------------------------------------
@pytest.fixture
def invented_paths(tmp_path, monkeypatch):
    interim, frozen = tmp_path / "interim", tmp_path / "frozen"
    interim.mkdir()
    frozen.mkdir()
    flags().to_parquet(interim / "flags.parquet", index=False)
    monkeypatch.setattr(mu, "INTERIM", interim)
    monkeypatch.setattr(mu, "FROZEN", frozen)
    monkeypatch.setattr(mu, "SHORT_FORM_FLAGS", interim / "flags.parquet")
    monkeypatch.setattr(mu, "SHORT_FORM_FILER_TABLE", interim / "no_such_filer_table.parquet")
    monkeypatch.setattr(mu, "DESIGN_SUMMARY", frozen / "reconciliation_mu_design.json")

    def refuse(*a, **k):
        raise AssertionError("main read a parquet file")
    monkeypatch.setattr(pd, "read_parquet", refuse)
    return interim, frozen


def test_main_stops_in_words_when_the_filer_table_is_missing(invented_paths, capsys):
    interim, frozen = invented_paths
    assert mu.main() == 1
    out = capsys.readouterr().out
    assert "STOPPED, nothing written" in out and "no_such_filer_table.parquet" in out and "not repeated" in out
    assert list(frozen.iterdir()) == []


def test_main_stop_can_fail(invented_paths, monkeypatch):
    """Break: the filer table pointed at an existing invented file in the test process; main then goes on to read
    (and the refusing reader raises), so the stop is what kept it from reading."""
    interim, _ = invented_paths
    present = interim / "filers.parquet"
    present.write_bytes(b"invented")
    monkeypatch.setattr(mu, "SHORT_FORM_FILER_TABLE", present)
    with pytest.raises(AssertionError, match="read a parquet file"):
        mu.main()


# ---- what a caller must pass after the freeze: flags that cover every outcome unit-year -----------------------------
def _outcome_rows() -> pd.DataFrame:
    """Invented outcome rows, as run_u_step has them after the window, jurisdiction and missing-price rules: the frame
    before the three-year count."""
    return frame_pre().assign(value=1.0)


def _ownership() -> pd.DataFrame:
    return pd.DataFrame([(u, s, "cooperative") for (u, s) in UNITS], columns=KEY + ["ownership_class"])


def test_u_sample_rules_with_the_adopted_flags_give_the_known_sample():
    o = _outcome_rows()
    fl = sff.adopted_row_u_flags(frame_pre(), table(), flags())
    kept, notes = mu.u_sample_rules(o, _ownership(), mu.ryu_spec(mu.U_SHORT_FORM_ADOPTED_CODE), fl, W)
    assert len(kept) == 20 and 2 not in set(kept.utility_id_eia)
    assert any("4 unit-years left out as Short Form filers (unit_years_filed)" in n for n in notes)


def test_flags_built_on_a_frame_that_misses_an_outcome_unit_year_stop_the_step():
    """After the freeze the flags must be built on a frame covering every outcome unit-year that reaches the filter.
    Here the frame misses C's 2020, and the step stops in words rather than reading that unit-year as anything."""
    fr = frame_pre()
    fr = fr[~((fr.utility_id_eia == 3) & (fr.year == 2020))]
    fl = sff.adopted_row_u_flags(fr, table(), flags())
    with pytest.raises(ValueError, match="1 outcome unit-years have no row in sample_flags"):
        mu.u_sample_rules(_outcome_rows(), _ownership(), mu.ryu_spec(mu.U_SHORT_FORM_ADOPTED_CODE), fl, W)


def test_coverage_stop_can_fail(monkeypatch):
    """Break: reconciliation_mu._u_drop_short_form replaced by a pass-through in the test process; the uncovered
    unit-year then goes through without a stop."""
    monkeypatch.setattr(mu, "_u_drop_short_form", lambda o, spec, f, w: (o, "no check"))
    fr = frame_pre()
    fr = fr[~((fr.utility_id_eia == 3) & (fr.year == 2020))]
    fl = sff.adopted_row_u_flags(fr, table(), flags())
    kept, _ = mu.u_sample_rules(_outcome_rows(), _ownership(), mu.ryu_spec(mu.U_SHORT_FORM_ADOPTED_CODE), fl, W)
    assert len(kept) > 0


# ---- a step whose window runs past row U's own (U3, 2015 to 2025): the same rule, year by year ----------------------

def _frame_with_2025() -> pd.DataFrame:
    extra = pd.DataFrame([(1, "TX", 2025), (9, "TX", 2025)], columns=KEY + ["year"]).astype({"utility_id_eia": "int64", "year": "int64"})
    return pd.concat([frame_pre(), extra], ignore_index=True)


def _table_with_2025() -> pd.DataFrame:
    t = pd.concat([table(), pd.DataFrame([(99, "ZZ", 2025), (9, "TX", 2025)], columns=KEY + ["year"])], ignore_index=True)
    t["state"] = t.state.astype("string")
    return t


def test_the_adopted_window_refuses_a_2025_unit_year_and_the_step_window_reads_it_by_the_same_rule():
    fr, tb = _frame_with_2025(), _table_with_2025()
    with pytest.raises(ValueError, match="outside the window"):
        sff.adopted_row_u_flags(fr, tb, flags())
    r = sff.adopted_row_u_flags(fr, tb, flags(), step_window=mu.U_STEPS["U3"]["window"])
    got = {(int(u), s, int(y)): bool(v) for u, s, y, v in zip(r.utility_id_eia, r.state, r.year, r.short_form)}
    # known answers in 2025: a table row that year leaves; no row that year stays, with no record of a filing
    assert got[(9, "TX", 2025)] is True and got[(1, "TX", 2025)] is False
    # and no flag of 2015 to 2024 moves when the bound is widened
    base = sff.adopted_row_u_flags(frame_pre(), table(), flags())
    for u, s, y, v in zip(base.utility_id_eia, base.state, base.year, base.short_form):
        assert got[(int(u), s, int(y))] == bool(v), (u, s, y)
    kept = r[(r.year == 2025) & ~r.short_form.astype(bool)].reading.iloc[0]
    assert "no record of a Short Form filing" in kept and not FORBIDDEN.search(kept)


def test_the_step_window_may_only_contain_the_adopted_window():
    for bad in ((2016, 2025), (2015, 2023), (2016, 2023)):
        with pytest.raises(ValueError, match="does not contain the adopted window"):
            sff.adopted_row_u_flags(frame_pre(), table(), flags(), step_window=bad)
    assert sff.ADOPTED_ROW_U_CHOICES["window"] == (2015, 2024)      # the named place is not changed by a call


def test_step_window_case_can_fail(monkeypatch):
    # the break, in the test process: a builder that ignores the 2025 table row. The known answer for (9, TX, 2025) then fails.
    real = sff.sample_flags_from_table

    def blind_to_2025(frame, tb, fl, **kw):
        return real(frame, tb[tb.year != 2025], fl, **kw)
    monkeypatch.setattr(sff, "sample_flags_from_table", blind_to_2025)
    with pytest.raises(AssertionError):
        test_the_adopted_window_refuses_a_2025_unit_year_and_the_step_window_reads_it_by_the_same_rule()
