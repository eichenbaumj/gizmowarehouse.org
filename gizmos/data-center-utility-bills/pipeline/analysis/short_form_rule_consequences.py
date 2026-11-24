#!/usr/bin/env python3
"""Consequences of each alternative Short Form exclusion rule for row U, counted on the quantity side only.

THESE ARE CONSEQUENCES OF ALTERNATIVES, set side by side with no ranking. Every alternative is run through
short_form_filers.readings() with every choice supplied explicitly. Joe adopted one of them for row U on 2026-11-20
(ledger entry D-115): years filed, by utility-state, with 2019 read from the operational file's flags, a flag of true
excluded and a missing flag or absent flags row kept with no record of a filing (the pairing
years_filed|by_utility_state under d1 below; its choices are short_form_filers.ADOPTED_ROW_U_CHOICES). ADOPTED names it
in the output. The counts here are no part of any reason for that rule. Row U's sample under it is reported by
reconciliation_mu main() in data/frozen/reconciliation_mu_design.json.

The frame counted against: row U's quantity-side sample frame with no Short Form exclusion, as reconciliation_mu main()
builds it for data/frozen/reconciliation_mu_design.json (row_u_quantity_sample_in_the_window): unit-years 2015 to 2024
(reconciliation_mu.RYU_WINDOW) in the 50 states and DC with an ownership class under scheme U, then the three-year count
by utility. It is built here by short_form_filers.row_u_quantity_frame from reconciliation_mu's adopted row U ownership
classes (the panel's entity type, the utility-level modal reported type carried across the panel and not the latest
year-by-year EIA classification, read over 2001 to 2025; Joe, 2026-11-20, D-117 and D-119) and _min_years. No price is read, so the paper's missing-price drop is not applied; it is NOT the paper's sample. Removals
are counted twice: directly on that frame, and with the three-year count taken again after the exclusion, which is the
order reconciliation_mu.u_sample_rules applies (ownership, Short Form, then the three-year count).

Inputs, all on the quantity side: data/interim/reconciliation_short_form_filers.parquet (the filer table written by
short_form_filers.py), data/interim/reconciliation_short_form_flags.parquet (the 2019 flags, read by name) and
data/interim/panel_quantities.parquet through pipeline.electricity.panel.load_quantities (no price column). Nothing
under data/raw is read. main() writes data/frozen/reconciliation_short_form_rule_consequences.json, counts only.
Written 2026-11-20, session 24, job 2; the adopted alternative named in session 25 (D-115). The plan is a DRAFT
pre-analysis plan, not frozen; these counts are provisional.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.analysis import reconciliation_mu as mu  # noqa: E402
from pipeline.analysis import short_form_filers as sff  # noqa: E402
from pipeline.electricity.panel import load_quantities  # noqa: E402

OUT = ROOT / "data" / "frozen" / "reconciliation_short_form_rule_consequences.json"
KEY = ["utility_id_eia", "state"]

PAPER_PRINTED = {
    "retained_utilities": sff.PAPER_RETAINED_UTILITIES,
    "short_form_group": sff.PAPER_SHORT_FORM_GROUP,
    "where": "Ryu and Hiatt, Sec. 2.2 (p. 6) and endnote 10 (p. 17), as quoted in the access request",
    "note": "printed figures only, for comparison; never a target, a tiebreak or a reason for any choice",
}

WHAT_THIS_IS = (
    "Consequences of alternative Short Form exclusion rules for row U, counted on the quantity side only. Joe adopted "
    "one of them on 2026-11-20 (D-115): years filed, by utility-state, 2019 from the operational file's flags with a "
    "flag of true excluded and every other 2019 unit-year kept with no record of a filing (named in the field "
    "adopted_by_joe_2026_11_20_d115). The counts are no part of any reason for it. Counts only, against row U's "
    "quantity-side frame with no exclusion (as reconciliation_mu builds it for reconciliation_mu_design.json; no price "
    "read, so NOT the paper's sample). The alternatives are listed side by side and not ranked. The plan is a DRAFT "
    "pre-analysis plan and is not frozen; these counts are provisional. A table row means 'has a row in the Short Form "
    "table that year'; reading no row as 'kept, with no record of a Short Form filing' is a convention, adopted for "
    "row U and used here inside the alternatives that name it; it is no claim about whether a unit filed.")

# The alternative Joe adopted on 2026-11-20 (D-115), by its names in this file's output.
ADOPTED = {"pairing": "years_filed|by_utility_state", "year_2019": "d1_flags_as_source_true_removed_missing_kept",
           "ruling": "Joe, 2026-11-20 (D-115)",
           "choices": "short_form_filers.ADOPTED_ROW_U_CHOICES, supplied by short_form_filers.adopted_row_u_flags",
           "reconciliation_mu_code": "unit_years_filed"}

PAIRINGS = (("years_filed", "utility_state"), ("years_filed", "utility"), ("ever_filed", "utility_state"),
            ("ever_filed", "utility"))
MU_CODES = {("years_filed", "utility_state"): "unit_years_filed",
            ("ever_filed", "utility"): "utilities_ever_filed"}
D_OPTIONS = {"d1_flags_as_source_true_removed_missing_kept": "flags_true_excluded_missing_kept",
             "d2_no_exclusion_in_2019": "no_exclusion_labelled"}
# The adopted alternative, as named above, carries exactly the adopted choices (the fixed counting choices of
# alternative() included).
assert tuple(ADOPTED["pairing"].split("|by_")) == (sff.ADOPTED_ROW_U_CHOICES["years"], sff.ADOPTED_ROW_U_CHOICES["level"])
assert D_OPTIONS[ADOPTED["year_2019"]] == sff.ADOPTED_ROW_U_CHOICES["year_2019"]
assert ADOPTED["reconciliation_mu_code"] == MU_CODES[(sff.ADOPTED_ROW_U_CHOICES["years"],
                                                      sff.ADOPTED_ROW_U_CHOICES["level"])] == sff.ADOPTED_ROW_U_MU_CODE


def _by_year(df: pd.DataFrame, window) -> dict:
    c = df.groupby("year").size()
    return {str(y): int(c.get(y, 0)) for y in range(window[0], window[1] + 1)}


def _units(df) -> set:
    return set(zip(df.utility_id_eia.astype("int64"), df.state.astype(str)))


def alternative(frame: pd.DataFrame, frame_pre: pd.DataFrame, table: pd.DataFrame, flags: pd.DataFrame,
                res: pd.DataFrame, window, *, years: str, level: str, year_2019: str) -> dict:
    """One alternative's consequences. frame: the frame after the three-year count; frame_pre: before it. Choices other
    than years, level and year_2019 are fixed here for counting only: no row in a covered year kept under a convention (no record of a filing), a
    window year the table does not cover (other than 2019) not excluded, and a 2019 unit-year with no flags row read as
    kept under the same convention; the stop counts of the other options are reported apart (stopping_options)."""
    kw = dict(window=tuple(window), years=years, level=level, no_row_in_covered_year="kept_no_record_of_a_filing",
              year_not_covered="no_exclusion_labelled", year_2019=year_2019, no_2019_flags_row="kept_no_record_of_a_filing")
    # the fixed counting choices are the adopted ones (D-115), so the adopted alternative is counted under its own rule
    assert all(kw[k] == sff.ADOPTED_ROW_U_CHOICES[k] for k in
               ("no_row_in_covered_year", "year_not_covered", "no_2019_flags_row"))
    r = sff.readings(frame, table, flags, **kw)
    if r.short_form.isna().any():
        raise AssertionError("a counting alternative stopped; it should not under the fixed counting choices")
    removed = r[r.short_form.astype(bool)]
    kept = r[~r.short_form.astype(bool)]
    f_units, k_units = _units(frame), _units(kept)
    f_utils, k_utils = set(frame.utility_id_eia), set(kept.utility_id_eia)
    # with the three-year count taken again after the exclusion (u_sample_rules' order)
    rp = sff.readings(frame_pre, table, flags, **kw)
    kept_pre = frame_pre[~rp.short_form.astype(bool).values]
    after, _ = mu._min_years(kept_pre, mu.RYU_MIN_YEARS, mu.RYU_MIN_YEARS_LEVEL)
    res_uy = set(zip(res.utility_id_eia.astype("int64"), res.state.astype(str), res.year.astype("int64")))
    rem_uy = set(zip(removed.utility_id_eia.astype("int64"), removed.state.astype(str), removed.year.astype("int64")))
    return {
        "choices_as_supplied": kw,
        "directly_on_the_frame": {
            "unit_years_removed_by_year": _by_year(removed, window),
            "unit_years_removed_total": int(len(removed)),
            "utility_states_with_any_unit_year_removed": len(_units(removed)),
            "utility_states_removed_entirely": len(f_units - k_units),
            "utilities_removed_entirely": len(f_utils - k_utils),
            "removed_unit_years_with_residential_sales_in_the_quantities": len(rem_uy & res_uy)},
        "with_the_three_year_count_taken_again_after_the_exclusion": {
            "unit_years_remaining": int(len(after)), "unit_years_removed_total": int(len(frame) - len(after)),
            "unit_years_removed_by_year": {y: int(v) - _by_year(after, window)[y]
                                           for y, v in _by_year(frame, window).items()},
            "utility_states_remaining": len(_units(after)), "utilities_remaining": int(after.utility_id_eia.nunique()),
            "utility_states_removed_entirely": len(f_units - _units(after)),
            "utilities_removed_entirely": len(f_utils - set(after.utility_id_eia))},
    }


def consequences(frame: pd.DataFrame, frame_pre: pd.DataFrame, table: pd.DataFrame, flags: pd.DataFrame,
                 q: pd.DataFrame, window) -> dict:
    """Every alternative's counts. Pure: takes the frames, the filer table, the flags and the quantities."""
    lo, hi = window
    res = sff.residential_rows(q)
    covered = sorted(int(y) for y in table[(table.year >= lo) & (table.year <= hi)].year.unique())
    empty_other_than_2019 = [y for y in range(lo, hi + 1) if y not in covered and y != 2019]
    out = {"pairings_of_a_and_b": {}}
    for years, level in PAIRINGS:
        name = f"{years}|by_{level}"
        out["pairings_of_a_and_b"][name] = {
            "reconciliation_mu_code": MU_CODES.get((years, level),
                                                   "not coded in reconciliation_mu (would need that module changed)"),
            **{d: alternative(frame, frame_pre, table, flags, res, window, years=years, level=level, year_2019=opt)
               for d, opt in D_OPTIONS.items()}}

    # (c): no row in a covered year kept under the adopted convention (no record of a filing), against stopping: how many
    # frame unit-years would stop
    stop_c = {}
    for level in ("utility_state", "utility"):
        r = sff.readings(frame, table, flags, window=tuple(window), years="years_filed", level=level,
                         no_row_in_covered_year="stop", year_not_covered="no_exclusion_labelled",
                         year_2019="no_exclusion_labelled", no_2019_flags_row="kept_no_record_of_a_filing")
        s = r[r.short_form.isna()]
        stop_c[f"by_{level}"] = {"unit_years_that_would_stop_by_year": _by_year(s, window),
                                 "unit_years_that_would_stop_total": int(len(s))}
    # (d): 2019
    f19 = flags[flags.year == 2019].copy()
    f19["short_form"] = f19.short_form.astype("boolean")
    fr19 = frame[frame.year == 2019].merge(f19[KEY + ["short_form"]].drop_duplicates(KEY), on=KEY, how="left",
                                          indicator=True)
    t18, t20 = sff._units(table[table.year == 2018]), sff._units(table[table.year == 2020])
    true_units = sff._units(f19[f19.short_form.fillna(False).astype(bool)])
    # ever: units flagged under ever_filed|by_utility_state whose window filings all fall in years they are not in
    # the frame
    tw = table[(table.year >= lo) & (table.year <= hi)]
    t_years = tw.groupby(KEY).year.apply(set)
    f_years = frame.groupby(KEY).year.apply(set)
    ever_units = set(t_years.index) & set(f_years.index)
    only_outside = sum(1 for k in ever_units if not (t_years[k] & f_years[k]))
    added = _added_2026_11_20(frame, fr19, table, t_years, f_years, ever_units, window)
    return {
        "frame": {
            "what_it_is": ("row U's quantity-side frame with no Short Form exclusion: unit-years 2015 to 2024 in the "
                           "50 states and DC with an ownership class (scheme U, the panel's entity type, the "
                           "utility-level modal reported type carried across the panel, read over 2001 to 2025; D-117 "
                           "and D-119), then the three-year count by utility; built by "
                           "short_form_filers.row_u_quantity_frame from "
                           "reconciliation_mu.adopted_row_u_ownership_classes and _min_years, as reconciliation_mu main() builds it "
                           "for reconciliation_mu_design.json. No price read; NOT the paper's sample"),
            "unit_years": int(len(frame)), "utility_states": len(_units(frame)),
            "utilities": int(frame.utility_id_eia.nunique()), "unit_years_by_year": _by_year(frame, window),
            "before_the_three_year_count": {"unit_years": int(len(frame_pre)), "utility_states": len(_units(frame_pre)),
                                            "utilities": int(frame_pre.utility_id_eia.nunique())},
            "unit_years_with_residential_sales_in_the_quantities": len(
                set(zip(frame.utility_id_eia, frame.state, frame.year)) &
                set(zip(res.utility_id_eia.astype("int64"), res.state.astype(str), res.year.astype("int64"))))},
        "window": [lo, hi],
        "adopted_by_joe_2026_11_20_d115": dict(ADOPTED),
        "window_years_the_table_covers": covered,
        "window_years_other_than_2019_the_table_does_not_cover": empty_other_than_2019,
        "fixed_for_counting": ("in every pairing: a unit-year with no row in a covered year kept under a convention, with no record of a "
                               "Short Form filing, never shown not to have filed; a window year other "
                               "than 2019 with no table row not excluded (there is none: see the field above, so this "
                               "choice has no effect here); a 2019 unit-year with no row in the flags file kept under the "
                               "same convention. What stopping would do instead is under stopping_options."),
        **out,
        "ever_filed_by_utility_state_units_whose_window_filings_all_fall_in_years_they_are_not_in_the_frame": (
            only_outside),
        "ever_filed_by_utility_state_units_in_the_frame_with_some_window_filing": len(ever_units),
        "stopping_options": {
            "c_no_row_in_a_covered_year_stops": stop_c,
            "d_2019_missing_flag_stops_frame_unit_years": int(((fr19._merge == "both") & fr19.short_form.isna()).sum()),
            "d_2019_no_flags_row_stops_frame_unit_years": int((fr19._merge == "left_only").sum()),
            "note": ("frame unit-years of 2019 whose flag is missing, and whose 2019 row is absent from the flags file; "
                     "under the stopping options these cannot be read and the rule is not applied"),
        },
        "d_2019": {
            "frame_unit_years_in_2019": int(len(fr19)),
            "frame_2019_unit_years_flagged_true": int((fr19.short_form == True).sum()),          # noqa: E712
            "frame_2019_unit_years_with_a_missing_flag": int(((fr19._merge == "both") & fr19.short_form.isna()).sum()),
            "frame_2019_unit_years_with_no_2019_row_in_the_flags_file": int((fr19._merge == "left_only").sum()),
            "d3_continuity_of_the_utility_states_flagged_true_in_2019": {
                "flagged_true": len(true_units),
                "with_a_table_row_in_both_2018_and_2020": len(true_units & t18 & t20),
                "in_2018_only": len((true_units & t18) - t20), "in_2020_only": len((true_units & t20) - t18),
                "in_neither": len(true_units - t18 - t20)},
        },
        **added,
        "paper_printed_figures": PAPER_PRINTED,
    }


def _neighbours(units: set, t18: set, t20: set) -> dict:
    return {"table_row_in_both_2018_and_2020": len(units & t18 & t20), "in_2018_only": len((units & t18) - t20),
            "in_2020_only": len((units & t20) - t18), "in_neither": len(units - t18 - t20)}


def _added_2026_11_20(frame, fr19, table, t_years, f_years, ever_units, window) -> dict:
    """Counts added at the coordinator's request of 2026-11-20 (session 24, job 2 follow-up). Counts only."""
    lo, hi = window
    t18, t20 = sff._units(table[table.year == 2018]), sff._units(table[table.year == 2020])
    not_true = fr19[~(fr19.short_form == True).fillna(False).astype(bool)]                  # noqa: E712
    missing = not_true[(not_true._merge == "both") & not_true.short_form.isna()]
    no_row = not_true[not_true._merge == "left_only"]
    # frame unit-years of units with a table row in some window year, by frame year
    later, not_later = {}, {}
    for y in range(lo, hi + 1):
        later[str(y)] = not_later[str(y)] = 0
    for (u, s, y) in zip(frame.utility_id_eia.astype("int64"), frame.state.astype(str), frame.year.astype("int64")):
        k = (u, s)
        if k not in ever_units:
            continue
        if min(t_years[k]) > y:
            later[str(int(y))] += 1
        else:
            not_later[str(int(y))] += 1
    first_any = table.groupby(KEY).year.min()
    first_any.index = [(int(u), str(s)) for u, s in first_any.index]
    first_2020_frame_by_2019 = sum(1 for k in ever_units if int(first_any[k]) == 2020 and max(f_years[k]) <= 2019)
    first_2020_in_window_frame_by_2019 = sum(1 for k in ever_units if min(t_years[k]) == 2020
                                             and max(f_years[k]) <= 2019)
    return {
        "frame_2019_unit_years_not_flagged_by_table_rows_in_2018_and_2020": {
            "what_this_is": ("row U frame unit-years of 2019 that are not flagged true, which are the unit-years the "
                             "2019 convention keeps, split by whether the utility-state has a Short Form table row in "
                             "2018 and in 2020. A table row in the neighbouring years establishes nothing about 2019."),
            "with_a_flags_row_whose_flag_is_missing": {"unit_years": int(len(missing)),
                                                      **_neighbours(sff._units(missing), t18, t20)},
            "with_no_flags_row": {"unit_years": int(len(no_row)), **_neighbours(sff._units(no_row), t18, t20)},
        },
        "frame_unit_years_of_units_with_a_table_row_in_some_window_year": {
            "what_this_is": ("by frame year, the frame unit-years of utility-states with a Short Form table row in "
                             "some window year (the units an 'ever' reading reaches), split by whether every one of "
                             "the unit's window table rows is in a later year than that frame year"),
            "all_the_units_table_rows_later_than_this_year": later,
            "not_all_later": not_later,
            "total": int(sum(later.values()) + sum(not_later.values())),
        },
        "units_reached_by_ever_whose_first_table_year_is_2020_and_frame_years_all_2019_or_earlier": {
            "first_table_year_over_the_whole_table_2012_to_2025": first_2020_frame_by_2019,
            "first_table_year_within_the_window": first_2020_in_window_frame_by_2019,
            "of_units_reached_by_ever": len(ever_units),
        },
    }


def main() -> int:
    q = load_quantities()
    q = q[["utility_id_eia", "state", "year", "entity_type", "res_mwh"]]
    table = pd.read_parquet(sff.OUT_TABLE)
    table["state"] = table.state.astype("string")
    flags = pd.read_parquet(sff.FLAGS_2019, columns=["utility_id_eia", "state", "year", "short_form"])
    frame = sff.row_u_quantity_frame(q)
    frame_pre = sff.row_u_quantity_frame(q, three_year_count=False)
    rec = {"what_this_is": WHAT_THIS_IS,
           "written_by": "pipeline/analysis/short_form_rule_consequences.py main(), 2026-11-20, session 24, job 2",
           "inputs": ["data/interim/reconciliation_short_form_filers.parquet",
                      "data/interim/reconciliation_short_form_flags.parquet",
                      "data/interim/panel_quantities.parquet (quantity columns; no price column exists)"],
           **consequences(frame, frame_pre, table, flags, q, mu.RYU_WINDOW)}
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
