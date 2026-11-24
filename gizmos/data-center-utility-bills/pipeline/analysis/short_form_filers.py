#!/usr/bin/env python3
"""Stage 2 of the Short Form access request: the read of three columns, the filer table and its count-only summary.

Authorized by Joe on 2026-11-20 (ledger entry D-113), in his words: "Authorize Short Form stage 2's read and summaries
only: items 1-3 of section S2.7 in `docs/gate1/short-form-access-request-2026-11-19.md`. Read only `utility_id_eia`,
`report_date` and `state` from `data/raw/pudl/core_eia861__yearly_short_form.parquet`, after the specified hash check
and invented-input tests. Never load `sales_revenue` or any other column. Build the specified filer table and
count-only summary. Items 4-5, the exclusion rule and fallback, remain undecided."

What this module opens under data/raw, and nothing else: the one file SHORT_FORM_TABLE, first as bytes for its SHA-256
through short_form_schema.hash_check(), and then, only if the hash equals the manifest's, its three columns
ACCESS_4_COLUMNS, every row, through reconciliation_inputs._guarded, reconciliation_inputs._check_out and the default
reconciliation_inputs._duckdb_select (a select of exactly those three columns). It never loads sales_revenue or any
other column, never reads a row-group or column statistic, and prints nothing from the file but counts.

The quantity side: data/interim/panel_quantities.parquet through pipeline.electricity.panel.load_quantities (the file
carries no price column) and the 2019 flags in data/interim/reconciliation_short_form_flags.parquet
(reconciliation_inputs.OUT_SHORT_FORM), read by name and not regenerated.

THE EXCLUSION RULE. sample_flags_from_table() still takes every choice of S2.5 as a required keyword argument with no
default and decides nothing by itself. Joe adopted one rule and its fallback on 2026-11-20 (ledger entry D-115), in his
words: "Exclude a utility-state-year where the Short Form table records a filing, or, for 2019, the operational flag is
true. Keep other unit-years as 'kept with no record of a filing,' without claiming non-filing. Apply the three-year
requirement after exclusion. Retain the explicitly incomplete 2019 exclusion and its missing-flag/no-row counts." The
choices that express it in this module's terms are in one named place, ADOPTED_ROW_U_CHOICES, and adopted_row_u_flags()
is the one call that supplies them. adopted_row_u_sample() counts row U's quantity-side sample under it.

A row of the table means "has a row in the Short Form table that year", which is a fact of the record. Reading no row
as "kept, with no record of a Short Form filing" is a convention, adopted by Joe for row U (D-115); the absence of a
row is no record either way. The False that sample_flags_from_table writes for such a unit-year means "kept
under a convention, with no record of a Short Form filing", never "shown not to have filed".

main() writes data/interim/reconciliation_short_form_filers.parquet and
data/frozen/reconciliation_short_form_filers_summary.json; it reads under data/raw and is run once only (D-113). The
summary file is a preserved record of that read and is not regenerated. Written 2026-11-20, session 24, job 2; the
adopted rule wired in session 25 (D-115). The plan is a DRAFT pre-analysis plan, not frozen and not registered outside;
this file is provisional.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.analysis import reconciliation_inputs as ri  # noqa: E402
from pipeline.analysis import reconciliation_mu as mu  # noqa: E402
from pipeline.analysis import short_form_schema as sfs  # noqa: E402
from pipeline.electricity.panel import load_quantities  # noqa: E402

# ---- the one file, the three columns, the barred column -------------------------------------------------------------
SHORT_FORM_TABLE = ROOT / "data" / "raw" / "pudl" / "core_eia861__yearly_short_form.parquet"
ACCESS_4_COLUMNS = ("utility_id_eia", "report_date", "state")
NEVER_LOADED_SHORT_FORM_COLUMNS = ("sales_revenue",)
assert not set(ACCESS_4_COLUMNS) & set(NEVER_LOADED_SHORT_FORM_COLUMNS), "the read list and the barred list overlap"
assert SHORT_FORM_TABLE == sfs.SHORT_FORM_TABLE, "this module and short_form_schema must name the same file"

# ---- outputs and quantity-side inputs ---------------------------------------------------------------------------------
OUT_TABLE = ROOT / "data" / "interim" / "reconciliation_short_form_filers.parquet"
OUT_SUMMARY = ROOT / "data" / "frozen" / "reconciliation_short_form_filers_summary.json"
FLAGS_2019 = ri.OUT_SHORT_FORM          # data/interim/reconciliation_short_form_flags.parquet, read by name
TABLE_COLUMNS = ("utility_id_eia", "state", "year")
KEY = ["utility_id_eia", "state"]

# The years the summary names when empty: 2012 to 2025 and any earlier year present (Joe's instruction for job 2).
SUMMARY_FIRST_YEAR, SUMMARY_LAST_YEAR = 2012, 2025

PAPER_SHORT_FORM_GROUP = "approximately 560"   # Ryu and Hiatt, endnote 10 (p. 17), as quoted in the access request
PAPER_RETAINED_UTILITIES = 1798                # Ryu and Hiatt, Sec. 2.2 (p. 6), as quoted in the access request
PAPER_FIGURE_KEY = ("paper_figure_printed_for_comparison_only_never_a_target_a_tiebreak_or_a_reason")

WHAT_THIS_IS = (
    "Stage 2 of the Short Form request (docs/gate1/short-form-access-request-2026-11-19.md, items 1 to 3 of S2.7), "
    "authorized by Joe on 2026-11-20 (D-113). Three columns only (utility_id_eia, report_date, state) of "
    "data/raw/pudl/core_eia861__yearly_short_form.parquet were read, after the hash check; sales_revenue and every other "
    "column were never loaded. Counts only. The plan is a DRAFT pre-analysis plan and is not frozen; these counts are "
    "provisional. A row of the filer table means 'has a row in the Short Form table that year', which is a fact of the "
    "record. Reading no row as 'kept, with no record of a Short Form filing' is a convention, which Joe adopted for "
    "row U on 2026-11-20 (D-115), after this summary's counts were taken; the summary itself applies no exclusion. "
    "Some rows in a year do not establish that the year is complete, and a missing 2019 flag is no record either way "
    "of a 2019 filing.")


class Access4Refused(PermissionError):
    """Raised when the reader is asked for any file but SHORT_FORM_TABLE."""


# =================================================================================================================
# The read (the only code that touches data/raw)
# =================================================================================================================
def _check_path(path) -> Path:
    p = Path(os.path.abspath(path))
    allowed = Path(os.path.abspath(SHORT_FORM_TABLE))
    if p != allowed:
        raise Access4Refused(f"access 4 reads only {allowed}; {p} is not that file and is refused")
    return p


def read_short_form_table(path=None, read_fn=None, columns=ACCESS_4_COLUMNS) -> pd.DataFrame:
    """Access 4. The three columns, by a column list, through reconciliation_inputs' guard (a request for any other
    column raises PermissionError before the reader is called) and its output check (a reader that returns any other
    column is refused after). The default reader is reconciliation_inputs._duckdb_select. No hash check here; run_read
    does that first."""
    path = SHORT_FORM_TABLE if path is None else path
    p = _check_path(path)
    if read_fn is None:
        read_fn = ri._duckdb_select
    df = ri._guarded(read_fn, ACCESS_4_COLUMNS, "access 4")(p, columns=columns)
    df = ri._check_out(pd.DataFrame(df), ACCESS_4_COLUMNS, "access 4")
    return _check_exact(df)


def _check_exact(df: pd.DataFrame) -> pd.DataFrame:
    """After _check_out (which lets a column named geometry through): the columns must be exactly ACCESS_4_COLUMNS."""
    if list(df.columns) != list(ACCESS_4_COLUMNS):
        raise PermissionError(f"access 4 returned columns {list(df.columns)}, expected exactly {list(ACCESS_4_COLUMNS)}")
    return df


def run_read(read_fn=None) -> tuple[dict, pd.DataFrame | None]:
    """The hash check first (short_form_schema.hash_check against the manifest); only if it matches, the one read.
    A mismatch returns (hash_check, None) and the reader is never called."""
    _check_path(SHORT_FORM_TABLE)
    hc = sfs.hash_check(SHORT_FORM_TABLE)
    if not hc["equal"]:
        return hc, None
    return hc, read_short_form_table(SHORT_FORM_TABLE, read_fn=read_fn)


# =================================================================================================================
# Pure functions
# =================================================================================================================
def build_table(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One row per distinct utility, state and year (year from report_date), columns exactly utility_id_eia (int64),
    state (string), year (int64). Returns the table and, by year, rows read, rows after collapsing and rows collapsed.
    A missing value in any of the three columns stops in words (the schema says all three are required)."""
    if list(raw.columns) != list(ACCESS_4_COLUMNS):
        raise PermissionError(f"build_table takes exactly {list(ACCESS_4_COLUMNS)}; got {list(raw.columns)}")
    nulls = {c: int(raw[c].isna().sum()) for c in ACCESS_4_COLUMNS}
    if any(nulls.values()):
        raise ValueError(f"missing values in the read: {nulls}; the schema says all three columns are required, so "
                         f"nothing is built")
    t = pd.DataFrame({"utility_id_eia": raw.utility_id_eia.astype("int64").values,
                      "state": raw.state.astype(str).values,
                      "year": pd.to_datetime(raw.report_date).dt.year.astype("int64").values})
    read_by_year = t.groupby("year").size()
    t = t.drop_duplicates().sort_values(list(TABLE_COLUMNS), kind="mergesort").reset_index(drop=True)
    t["state"] = t.state.astype("string")
    kept_by_year = t.groupby("year").size()
    if tuple(t.columns) != TABLE_COLUMNS:
        raise AssertionError(f"table columns {list(t.columns)} != {list(TABLE_COLUMNS)}")
    years = sorted(int(y) for y in read_by_year.index)
    by_year = {str(y): {"rows_read": int(read_by_year.get(y, 0)), "rows_after_collapsing": int(kept_by_year.get(y, 0)),
                        "rows_collapsed": int(read_by_year.get(y, 0) - kept_by_year.get(y, 0))} for y in years}
    return t, by_year


def residential_rows(q: pd.DataFrame) -> pd.DataFrame:
    """Unit-years of the quantities file with residential sales: res_mwh present and above zero (the agent's reading of
    'a row with residential sales')."""
    return q[q.res_mwh.notna() & (q.res_mwh > 0)][KEY + ["year"]].drop_duplicates()


def row_u_quantity_frame(q: pd.DataFrame, three_year_count: bool = True) -> pd.DataFrame:
    """Row U's quantity-side sample frame with no Short Form exclusion, built as reconciliation_mu main() builds it for
    data/frozen/reconciliation_mu_design.json (row_u_quantity_sample_in_the_window): unit-years in RYU_WINDOW, in the
    50 states and DC, with an ownership class under scheme U (the panel's entity type of each utility-state, the
    utility-level modal reported type carried across the panel and not the latest year-by-year EIA classification,
    read over the quantity panel's years 2001 to 2025, one class for every year of the unit, settled by Joe on
    2026-11-20, D-117 and D-119; reconciliation_mu.adopted_row_u_ownership_classes, which refuses quantities whose
    years are not exactly 2001 to 2025), then the three-year count by utility (reconciliation_mu._min_years). A unit with no entity
    type in any year has no class and is not in the frame. No price is read, so the paper's missing-price drop is not
    applied; NOT the paper's sample. three_year_count=False returns the rows before the three-year count, which is
    where run_u_step applies the Short Form filter."""
    lo, hi = mu.RYU_WINDOW
    own_u = mu.adopted_row_u_ownership_classes(q).set_index(mu.KEY).ownership_class
    w = q[(q.year >= lo) & (q.year <= hi) & q.state.isin(mu.RYU_OURS_JURISDICTIONS)][mu.KEY + ["year"]]
    w = w.drop_duplicates()
    w = w[[own_u.get(k) is not None and not (isinstance(own_u.get(k), float) and np.isnan(own_u.get(k)))
           for k in zip(w.utility_id_eia, w.state)]]
    if three_year_count:
        w, _ = mu._min_years(w, mu.RYU_MIN_YEARS, mu.RYU_MIN_YEARS_LEVEL)
    return w.astype({"utility_id_eia": "int64", "year": "int64"}).reset_index(drop=True)


def _units(df: pd.DataFrame) -> set:
    return set(zip(df.utility_id_eia.astype("int64"), df.state.astype(str)))


def _unit_years(df: pd.DataFrame) -> set:
    return set(zip(df.utility_id_eia.astype("int64"), df.state.astype(str), df.year.astype("int64")))


def continuity(table: pd.DataFrame) -> list[dict]:
    """For each pair of consecutive years among the years with rows: utility-states in both, in the earlier only, in
    the later only. The gap between the two years is given, so a pair that skips an empty year can be seen."""
    years = sorted(int(y) for y in table.year.unique())
    sets = {y: _units(table[table.year == y]) for y in years}
    out = []
    for a, b in zip(years, years[1:]):
        out.append({"earlier": a, "later": b, "years_apart": b - a, "utility_states_in_both": len(sets[a] & sets[b]),
                    "in_earlier_only": len(sets[a] - sets[b]), "in_later_only": len(sets[b] - sets[a])})
    return out


def _direction(seq: list[tuple[int, str]]) -> str:
    """Order of a switcher's years: 'L' a year in the quantities with no table row, 'S' a year with a table row."""
    ls = [y for y, c in seq if c == "L"]
    ss = [y for y, c in seq if c == "S"]
    if max(ls) < min(ss):
        return "quantities_years_all_before_table_years"
    if max(ss) < min(ls):
        return "table_years_all_before_quantities_years"
    return "interleaved"


def coverage_and_switching(table: pd.DataFrame, q: pd.DataFrame, window: tuple[int, int]) -> dict:
    """Of the utilities and utility-states with a table row in some window year: how many appear in the quantities in a
    window year; of those, how many have a table row in every window year in which they appear there, and how many
    switch (a window year with a table row and a window year in the quantities with no table row). Counted twice:
    over every window year, and over only the window years in which the table has any row (so that a year the table
    lacks does not by itself make a switch). Direction of switching is given for utility-states."""
    lo, hi = window
    tw = table[(table.year >= lo) & (table.year <= hi)]
    qw = q[(q.year >= lo) & (q.year <= hi)][KEY + ["year"]].drop_duplicates()
    covered = set(int(y) for y in tw.year.unique())
    out = {}
    for level, cols in (("utility_state", KEY), ("utility", ["utility_id_eia"])):
        t_keys = {tuple(r) for r in tw[cols].drop_duplicates().itertuples(index=False)}
        t_years = tw.groupby(cols).year.apply(lambda s: set(int(x) for x in s))
        q_years = qw.groupby(cols).year.apply(lambda s: set(int(x) for x in s))
        if level == "utility":
            t_years.index = [(k,) for k in t_years.index]
            q_years.index = [(k,) for k in q_years.index]
        else:
            t_years.index = [tuple(k) for k in t_years.index]
            q_years.index = [tuple(k) for k in q_years.index]
        res = {}
        for label, yrs in (("over_every_window_year", set(range(lo, hi + 1))),
                           ("over_window_years_in_which_the_table_has_rows", covered)):
            n_in_q = n_every = n_switch = 0
            directions: dict[str, int] = {}
            for k in t_keys:
                ty = t_years.get(k, set()) & yrs
                qy = (q_years.get(k, set()) if k in q_years.index else set()) & yrs
                if not qy:
                    continue
                n_in_q += 1
                if qy <= ty:
                    n_every += 1
                l_only = qy - ty
                if ty and l_only:
                    n_switch += 1
                    if level == "utility_state":
                        seq = sorted([(y, "L") for y in l_only] + [(y, "S") for y in ty])
                        d = _direction(seq)
                        directions[d] = directions.get(d, 0) + 1
            entry = {"with_a_table_row_in_some_window_year": len(t_keys),
                     "appearing_in_the_quantities_in_some_window_year": n_in_q,
                     "not_appearing_in_the_quantities_in_any_window_year": len(t_keys) - n_in_q,
                     "with_a_table_row_in_every_window_year_in_which_they_appear_in_the_quantities": n_every,
                     "switching": n_switch}
            if level == "utility_state":
                entry["switching_by_order_of_years"] = dict(sorted(directions.items()))
            res[label] = entry
        out[level] = res
    out["window_years_in_which_the_table_has_rows"] = sorted(covered)
    out["definitions"] = (
        "Appearing in the quantities: any row of panel_quantities.parquet for the utility-state (or utility) that year. "
        "Switching: at least one year with a table row and at least one year in the quantities with no table row, "
        "among the years counted. Order of years: whether every quantities-only year comes before every table year, "
        "after it, or neither. The agent's definitions.")
    return out


def summarize(table: pd.DataFrame, by_year_read: dict, q: pd.DataFrame, flags: pd.DataFrame,
              window: tuple[int, int]) -> dict:
    """S2.4's count-only summary. Pure: takes the table, the read's by-year counts, the quantities and the 2019 flags."""
    lo, hi = window
    years_present = sorted(int(y) for y in table.year.unique())
    first = min([SUMMARY_FIRST_YEAR] + years_present)
    last = max([SUMMARY_LAST_YEAR] + years_present)
    by_year = {}
    for y in range(first, last + 1):
        ty = table[table.year == y]
        r = by_year_read.get(str(y), {"rows_read": 0, "rows_after_collapsing": 0, "rows_collapsed": 0})
        by_year[str(y)] = {**r, "utilities": int(ty.utility_id_eia.nunique()), "utility_states": len(_units(ty))}
    empty = [y for y in range(first, last + 1) if by_year[str(y)]["rows_read"] == 0]
    tw = table[(table.year >= lo) & (table.year <= hi)]
    res = residential_rows(q)
    tw_uy = _unit_years(tw)
    res_uy = _unit_years(res)
    q_uy = _unit_years(q[KEY + ["year"]].drop_duplicates())

    # 2019: the flags file
    f = flags.copy()
    f19 = f[f.year == 2019]
    true19 = f19[f19.short_form.astype("boolean").fillna(False).astype(bool)]
    true_units = _units(true19)
    t18, t20 = _units(table[table.year == 2018]), _units(table[table.year == 2020])
    true_utils = set(true19.utility_id_eia.astype("int64"))
    u18 = set(table[table.year == 2018].utility_id_eia.astype("int64"))
    u20 = set(table[table.year == 2020].utility_id_eia.astype("int64"))
    miss19 = f19[f19.short_form.isna()]
    frame = row_u_quantity_frame(q)
    frame_units = _units(frame)
    f19_units = _units(f19)
    frame19 = frame[frame.year == 2019]
    m19 = frame19.merge(f19[KEY + ["short_form"]].drop_duplicates(), on=KEY, how="left", indicator=True)
    clash19 = f19.groupby(KEY).short_form.apply(lambda x: x.astype(object).where(x.notna(), "NA").nunique() > 1)

    return {
        "what_this_is": WHAT_THIS_IS,
        "written_by": "pipeline/analysis/short_form_filers.py main(), 2026-11-20, session 24, job 2",
        "table": {"path": str(OUT_TABLE.relative_to(ROOT)) if OUT_TABLE.is_relative_to(ROOT) else str(OUT_TABLE),
                  "columns": {"utility_id_eia": "int64", "state": "string", "year": "int64"},
                  "rows": int(len(table)),
                  "meaning_of_a_row": "has a row in the Short Form table that year (a fact of the record)"},
        "read": {"columns_read": list(ACCESS_4_COLUMNS), "never_loaded": list(NEVER_LOADED_SHORT_FORM_COLUMNS) +
                 ["every other column of the table"],
                 "rows_read": int(sum(v["rows_read"] for v in by_year_read.values())),
                 "rows_after_collapsing": int(len(table)),
                 "rows_collapsed": int(sum(v["rows_collapsed"] for v in by_year_read.values())),
                 "collapsing": ("rows repeated within a utility, state and year (for example one per balancing "
                                "authority, which was not read) are collapsed to one")},
        "by_year": by_year,
        "years_with_no_row": {"range_examined": [first, last], "years": empty},
        "years_with_rows": years_present,
        "continuity_of_utility_states_between_consecutive_years_with_rows": continuity(table),
        "no_completeness_threshold": ("no threshold for a 'complete' year is set; a year that looks thin is named in "
                                      "the report, and nothing is repaired"),
        "window": {"years": [lo, hi], "source": "reconciliation_mu.RYU_WINDOW",
                   "utilities_with_a_row_in_some_window_year": int(tw.utility_id_eia.nunique()),
                   "utility_states_with_a_row_in_some_window_year": len(_units(tw)),
                   "unit_years_in_the_window": len(tw_uy)},
        "against_the_quantities": {
            "source": ("data/interim/panel_quantities.parquet through pipeline.electricity.panel.load_quantities; the "
                       "file has no price column"),
            "coverage_and_switching": coverage_and_switching(table, q, window),
            "window_unit_years_of_the_table_also_with_residential_sales_in_the_quantities": len(tw_uy & res_uy),
            "window_unit_years_of_the_table_also_with_any_row_in_the_quantities": len(tw_uy & q_uy),
            "residential_sales_definition": "res_mwh present and above zero (the agent's reading)",
        },
        "the_2019_flags": {
            "source": "data/interim/reconciliation_short_form_flags.parquet (reconciliation_inputs.OUT_SHORT_FORM), read "
                      "by name, not regenerated",
            "what_the_flags_file_holds": ("utility_id_eia, state, year, short_form, data_observed: one row per row of the "
                                          "operational table, so it can say which unit-years have a 2019 row and which "
                                          "carry a missing flag; it holds nothing on units absent from that table"),
            "rows_2019": int(len(f19)), "rows_2019_flag_true": int(len(true19)),
            "rows_2019_flag_missing": int(len(miss19)),
            "rows_2019_flag_false": int((f19.short_form.astype("boolean") == False).sum()),  # noqa: E712
            "utility_states_2019_flag_true": len(true_units),
            "utility_states_2019_flag_missing": len(_units(miss19)),
            "utility_states_2019_whose_rows_disagree_on_the_flag": int(clash19.sum()),
            "continuity_of_the_flagged_utility_states_in_the_table": {
                "with_a_table_row_in_both_2018_and_2020": len(true_units & t18 & t20),
                "in_2018_only": len((true_units & t18) - t20),
                "in_2020_only": len((true_units & t20) - t18),
                "in_neither": len(true_units - t18 - t20)},
            "continuity_of_the_flagged_utilities_in_the_table_by_utility": {
                "utilities_flagged_true_in_2019": len(true_utils),
                "with_a_table_row_in_both_2018_and_2020": len(true_utils & u18 & u20),
                "in_2018_only": len((true_utils & u18) - u20), "in_2020_only": len((true_utils & u20) - u18),
                "in_neither": len(true_utils - u18 - u20)},
            "row_u_frame": {
                "what_it_is": ("row U's quantity-side frame with no Short Form exclusion, as reconciliation_mu builds "
                               "it for reconciliation_mu_design.json (short_form_rule_consequences.py gives the detail)"),
                "unit_years": int(len(frame)), "utility_states": len(frame_units),
                "utility_states_with_no_2019_row_in_the_flags_file": len(frame_units - f19_units),
                "frame_unit_years_in_2019": int(len(frame19)),
                "frame_2019_unit_years_with_no_2019_row_in_the_flags_file": int((m19._merge == "left_only").sum()),
                "frame_2019_unit_years_with_a_missing_flag": int(((m19._merge == "both") & m19.short_form.isna()).sum()),
                "frame_2019_unit_years_flagged_true": int((m19.short_form.astype("boolean") == True).sum())},  # noqa: E712
            "facts_and_conventions": ("a missing 2019 flag is no record of a filing and does not show that the unit had none; that the "
                                      "table has no 2019 row is what its own description says and what the counts "
                                      "show, and is not a reading of who filed in 2019"),
        },
        PAPER_FIGURE_KEY: {"short_form_group": PAPER_SHORT_FORM_GROUP,
                           "where": "Ryu and Hiatt, endnote 10 (p. 17), as quoted in the access request",
                           "note": ("printed beside the counts for comparison only; it is never a target, a tiebreak "
                                    "or a reason for any choice")},
    }


# =================================================================================================================
# The sample_flags builder (S2.3 item 7). It decides nothing; the adopted choices are supplied by adopted_row_u_flags.
# =================================================================================================================
YEARS_OPTIONS = ("years_filed", "ever_filed")
LEVEL_OPTIONS = ("utility_state", "utility")
NO_ROW_OPTIONS = ("kept_no_record_of_a_filing", "stop")
YEAR_NOT_COVERED_OPTIONS = ("no_exclusion_labelled", "stop")
YEAR_2019_OPTIONS = ("flags_true_excluded_missing_kept", "flags_missing_stops", "no_exclusion_labelled")
NO_2019_FLAGS_ROW_OPTIONS = ("kept_no_record_of_a_filing", "stop")
_NOT_SUPPLIED = object()


class ChoiceNotSupplied(ValueError):
    """A choice of S2.5 was not supplied or names an unknown option. sample_flags_from_table fills no choice itself;
    row U's adopted choices (D-115) are supplied by adopted_row_u_flags from ADOPTED_ROW_U_CHOICES."""


def _need_choice(name: str, value, options: tuple) -> str:
    if value is _NOT_SUPPLIED or value is None:
        raise ChoiceNotSupplied(f"the choice {name!r} was not supplied. This function fills no choice itself; row U's "
                                f"choices as Joe adopted them on 2026-11-20 (D-115) are supplied by adopted_row_u_flags "
                                f"from ADOPTED_ROW_U_CHOICES. Options: {list(options)}")
    if value not in options:
        raise ChoiceNotSupplied(f"the choice {name!r}={value!r} is not a known option; options: {list(options)}")
    return value


def readings(frame: pd.DataFrame, table: pd.DataFrame, flags: pd.DataFrame | None = None, *,
             window=_NOT_SUPPLIED, years=_NOT_SUPPLIED, level=_NOT_SUPPLIED, no_row_in_covered_year=_NOT_SUPPLIED,
             year_not_covered=_NOT_SUPPLIED, year_2019=_NOT_SUPPLIED, no_2019_flags_row=_NOT_SUPPLIED) -> pd.DataFrame:
    """The reading of every unit-year of `frame` under the supplied choices, with no stop raised: returns frame's
    utility_id_eia, state, year, plus short_form (nullable boolean: True leaves, False stays, missing where the chosen
    reading stops) and reading (words). A False written for a unit-year with no row, a missing 2019 flag or no 2019
    flags row means "kept under a convention, with no record of a Short Form filing", never "shown not to have filed". sample_flags_from_table() is this with a stop raised in words.

    Choices, all required here (S2.5); the set Joe adopted for row U on 2026-11-20 (D-115) is ADOPTED_ROW_U_CHOICES:
      window                (first, last): the years whose filings count.
      years                 'years_filed' (a unit-year leaves in a year a filing is found) or 'ever_filed' (every
                            frame unit-year of a unit with a filing found in any window year leaves; filings are looked
                            for over the whole window in the table, not only in the unit's frame years, the agent's
                            reading).
      level                 'utility_state' (a filing counts for its own state) or 'utility' (for every state of the
                            utility).
      no_row_in_covered_year 'kept_no_record_of_a_filing' or 'stop': a unit-year with no row, in a year the table
                            has any row.
      year_not_covered      'no_exclusion_labelled' or 'stop': a window year other than 2019 in which the table has no
                            row at all.
      year_2019             'flags_true_excluded_missing_kept' (d1: the 2019 flags as source, a flag of true
                            excluded and a missing flag kept under a convention, with no record of a filing), 'flags_missing_stops' (the flags as source, a missing flag stopping), or
                            'no_exclusion_labelled' (d2).
      no_2019_flags_row     'kept_no_record_of_a_filing' or 'stop': a frame unit-year of 2019 with no row in the
                            flags file, under either flags option (S2.5 (d1) as written stops it). Supplied always; it has no effect under
                            year_2019='no_exclusion_labelled'.
    If the table has any 2019 row, the 2019 choice was written for a table without one, and this stops in words."""
    if window is _NOT_SUPPLIED or window is None:
        raise ChoiceNotSupplied("the choice 'window' was not supplied. This function fills no choice itself; row U's "
                                "window as Joe adopted it on 2026-11-20 (D-115) is supplied by adopted_row_u_flags from "
                                "ADOPTED_ROW_U_CHOICES. It is (first, last), the years whose filings count")
    w = tuple(window)
    if not (isinstance(w, tuple) and len(w) == 2 and int(w[0]) <= int(w[1])):
        raise ChoiceNotSupplied(f"the choice 'window' must be (first, last); got {w!r}")
    years = _need_choice("years", years, YEARS_OPTIONS)
    level = _need_choice("level", level, LEVEL_OPTIONS)
    no_row_in_covered_year = _need_choice("no_row_in_covered_year", no_row_in_covered_year, NO_ROW_OPTIONS)
    year_not_covered = _need_choice("year_not_covered", year_not_covered, YEAR_NOT_COVERED_OPTIONS)
    year_2019 = _need_choice("year_2019", year_2019, YEAR_2019_OPTIONS)
    no_2019_flags_row = _need_choice("no_2019_flags_row", no_2019_flags_row, NO_2019_FLAGS_ROW_OPTIONS)
    lo, hi = int(w[0]), int(w[1])
    if (table.year == 2019).any():
        raise ValueError("the table has 2019 rows; the 2019 choice was written for a table with none, so nothing is read")
    uses_flags = year_2019 != "no_exclusion_labelled"
    if uses_flags and flags is None:
        raise ValueError(f"year_2019={year_2019!r} reads the 2019 flags, and none were passed")
    fr = frame[KEY + ["year"]].copy()
    fr["utility_id_eia"] = fr.utility_id_eia.astype("int64")
    fr["state"] = fr.state.astype(str)
    fr["year"] = fr.year.astype("int64")
    if fr.duplicated().any():
        raise ValueError("the frame repeats a unit-year")
    if ((fr.year < lo) | (fr.year > hi)).any():
        raise ValueError(f"the frame has unit-years outside the window {lo}-{hi}")
    tw = table[(table.year >= lo) & (table.year <= hi)]
    covered = set(int(y) for y in tw.year.unique())

    # filings found, at the chosen level: a set of (u, s, y) or (u, y)
    def k_of(u, s, y):
        return (u, s, y) if level == "utility_state" else (u, y)
    found = {k_of(int(u), str(s), int(y)) for u, s, y in zip(tw.utility_id_eia, tw.state, tw.year)}
    f19 = None
    if uses_flags:
        f19 = flags[flags.year == 2019][KEY + ["short_form"]].copy()
        f19["utility_id_eia"] = f19.utility_id_eia.astype("int64")
        f19["state"] = f19.state.astype(str)
        f19["short_form"] = f19.short_form.astype("boolean")
        clash = f19.groupby(KEY).short_form.apply(lambda x: x.astype(object).where(x.notna(), "NA").nunique() > 1)
        if clash.any():
            raise ValueError(f"the 2019 flags carry {int(clash.sum())} unit-states whose rows disagree; no row is chosen")
        f19 = f19.drop_duplicates(KEY)
        if lo <= 2019 <= hi:
            for u, s in zip(f19[f19.short_form.fillna(False)].utility_id_eia, f19[f19.short_form.fillna(False)].state):
                found.add(k_of(int(u), str(s), 2019))
        flag19 = {(int(u), str(s)): v for u, s, v in zip(f19.utility_id_eia, f19.state, f19.short_form)}

    def no_filing_reading(u, s, y):
        """(value, words) for a unit-year with no filing found: False, or None where the chosen reading stops."""
        if y == 2019:
            if not uses_flags:
                return False, "2019: no exclusion (labelled as not applied)"
            if (u, s) not in flag19:
                return ((False, "2019: no row in the flags file; kept under a convention, with no record of a Short Form filing")
                        if no_2019_flags_row == "kept_no_record_of_a_filing" else (None, "2019: no row in the flags file; stops"))
            if pd.isna(flag19[(u, s)]):
                return ((False, "2019: missing flag; kept under a convention, with no record of a Short Form filing")
                        if year_2019 == "flags_true_excluded_missing_kept" else (None, "2019: missing flag; stops"))
            return False, "2019: flag not true"
        if y not in covered:
            return ((False, f"{y}: the table has no row that year; no exclusion (labelled as not applied)")
                    if year_not_covered == "no_exclusion_labelled" else
                    (None, f"{y}: the table has no row that year; stops"))
        return ((False, f"{y}: no row in a year the table has rows; kept under a convention, with no record of a Short Form filing")
                if no_row_in_covered_year == "kept_no_record_of_a_filing" else (None, f"{y}: no row in a covered year; stops"))

    vals, words = [], []
    if years == "years_filed":
        for u, s, y in zip(fr.utility_id_eia, fr.state, fr.year):
            if k_of(int(u), s, int(y)) in found:
                vals.append(True)
                words.append(f"{int(y)}: a filing found ({'2019 flag true' if y == 2019 else 'a table row'}, "
                             f"by {level})")
            else:
                v, t = no_filing_reading(int(u), s, int(y))
                vals.append(v)
                words.append(t)
    else:
        ever = {(k[0], k[1]) if level == "utility_state" else (k[0],) for k in found}
        for u, s, y in zip(fr.utility_id_eia, fr.state, fr.year):
            uk = (int(u), s) if level == "utility_state" else (int(u),)
            if uk in ever:
                vals.append(True)
                words.append(f"a filing found in some window year (ever, by {level})")
            else:
                vals.append(None)   # resolved below over the unit's frame years
                words.append("")
        fr["_v"] = vals
        fr["_w"] = words
        unit_cols = KEY if level == "utility_state" else ["utility_id_eia"]
        for _, g in fr[fr._v.isna()].groupby(unit_cols):
            rs = [no_filing_reading(int(u), s, int(y)) for u, s, y in zip(g.utility_id_eia, g.state, g.year)]
            stops = [t for v, t in rs if v is None]
            if stops:
                for i in g.index:
                    fr.at[i, "_v"] = None
                    fr.at[i, "_w"] = "ever: no filing found and a frame year whose reading stops (" + stops[0] + ")"
            else:
                for i in g.index:
                    fr.at[i, "_v"] = False
                    fr.at[i, "_w"] = "ever: no record of a filing in any window year; every frame year kept under a convention"
        vals, words = list(fr._v), list(fr._w)
        fr = fr.drop(columns=["_v", "_w"])
    out = fr.reset_index(drop=True)
    out["short_form"] = pd.array([None if v is None else bool(v) for v in vals], dtype="boolean")
    out["reading"] = words
    return out


def sample_flags_from_table(frame: pd.DataFrame, table: pd.DataFrame, flags: pd.DataFrame | None = None, *,
                            window=_NOT_SUPPLIED, years=_NOT_SUPPLIED, level=_NOT_SUPPLIED,
                            no_row_in_covered_year=_NOT_SUPPLIED, year_not_covered=_NOT_SUPPLIED,
                            year_2019=_NOT_SUPPLIED, no_2019_flags_row=_NOT_SUPPLIED) -> pd.DataFrame:
    """The sample_flags frame reconciliation_mu.run_u_step takes (utility_id_eia, state, year, short_form, plus a
    `reading` column it does not read), for every unit-year of `frame`, under the choices supplied.

    This function decides nothing by itself: every choice of S2.5 is a required keyword argument with no default (see
    readings() for the options), an unsupplied or unknown choice raises in words, and a unit-year whose chosen reading
    stops raises in words with the count. Row U's choices as Joe adopted them on 2026-11-20 (D-115) are supplied by
    adopted_row_u_flags() from ADOPTED_ROW_U_CHOICES, and by no other call. A False means "kept under a convention,
    with no record of a Short Form filing", never "shown not to have filed". short_form is True where the unit-year
    leaves under the supplied choices, already carrying the 'ever' and 'utility' readings, so run_u_step's
    'unit_years_filed' applies it as it stands (for the pairing ever and by utility, its 'utilities_ever_filed' gives
    the same rows on a frame whose window equals the choice's window; the agent's reading)."""
    r = readings(frame, table, flags, window=window, years=years, level=level,
                 no_row_in_covered_year=no_row_in_covered_year, year_not_covered=year_not_covered,
                 year_2019=year_2019, no_2019_flags_row=no_2019_flags_row)
    stops = r[r.short_form.isna()]
    if len(stops):
        kinds = stops.reading.str.replace(r"^\d{4}: ", "", regex=True).value_counts()
        raise ValueError(f"{len(stops)} unit-years cannot be read under the choices supplied, so no sample_flags are "
                         f"built: " + "; ".join(f"{n} x {k}" for k, n in kinds.items()))
    return r


# =================================================================================================================
# Row U's Short Form rule as Joe adopted it on 2026-11-20 (D-115). The one named place for its choices.
# =================================================================================================================
ADOPTED_ROW_U_RULING = "adopted by Joe on 2026-11-20 (ledger entry D-115)"
ADOPTED_ROW_U_WORDS = (
    "Exclude a utility-state-year where the Short Form table records a filing, or, for 2019, the operational flag is "
    "true. Keep other unit-years as 'kept with no record of a filing,' without claiming non-filing. Apply the "
    "three-year requirement after exclusion. Retain the explicitly incomplete 2019 exclusion and its missing-flag/no-row "
    "counts.")
# His words in this module's terms (the session's reading of sections T4 and T6 of
# docs/gate1/short-form-access-request-2026-11-19.md, which he adopted): a filing is found only in the year it is on
# record (years_filed) and only for its own state (utility_state); a unit-year with no table row in a year the table has
# rows is kept with no record of a filing; a window year other than 2019 with no table row at all is not excluded and is
# labelled (the table covers every window year but 2019, so this choice has nothing to act on); 2019 reads the
# operational file's flags, a flag of true excluded and a missing flag kept with no record of a filing; a 2019 unit-year
# with no flags row kept the same way. The window is row U's own, reconciliation_mu.RYU_WINDOW.
ADOPTED_ROW_U_CHOICES = MappingProxyType({
    "window": tuple(mu.RYU_WINDOW),
    "years": "years_filed",
    "level": "utility_state",
    "no_row_in_covered_year": "kept_no_record_of_a_filing",
    "year_not_covered": "no_exclusion_labelled",
    "year_2019": "flags_true_excluded_missing_kept",
    "no_2019_flags_row": "kept_no_record_of_a_filing",
})
assert ADOPTED_ROW_U_CHOICES["window"] == (2015, 2024), "row U's window is 2015 to 2024 (reconciliation_mu.RYU_WINDOW)"
# reconciliation_mu's code for the pairing years filed, by utility-state: the flags are applied unit-year by unit-year.
ADOPTED_ROW_U_MU_CODE = mu.U_SHORT_FORM_ADOPTED_CODE
assert ADOPTED_ROW_U_MU_CODE == "unit_years_filed"


def adopted_row_u_flags(frame: pd.DataFrame, table: pd.DataFrame, flags: pd.DataFrame,
                        step_window: tuple[int, int] | None = None) -> pd.DataFrame:
    """Row U's sample_flags under the rule Joe adopted on 2026-11-20 (D-115): sample_flags_from_table with exactly
    ADOPTED_ROW_U_CHOICES. frame: the unit-years the flags must cover (utility_id_eia, state, year, every year in row
    U's window, none repeated); table: the filer table (data/interim/reconciliation_short_form_filers.parquet);
    flags: the 2019 flags (data/interim/reconciliation_short_form_flags.parquet). Both records are passed in, and
    nothing is read here.

    short_form is True where a record shows a filing (a table row that year, or a 2019 flag of true) and False
    everywhere else, which means kept with no record of a filing and is no claim about whether the unit filed. The
    2019 exclusion is explicitly incomplete. It rests on the flags, and a 2019 unit-year with a missing flag or no flags
    row is kept with no record either way. The result goes to reconciliation_mu.run_u_step as sample_flags under
    short_form_exclusion ADOPTED_ROW_U_MU_CODE ('unit_years_filed'), whose own order then takes the three-year count
    after the exclusion. run_u_step raises on any outcome unit-year with no row here, so `frame` must cover every
    unit-year of the outcome frame that reaches the Short Form filter.

    sample_flags_from_table folds an 'ever' or a 'by utility' reading into the flag and tells the caller to pass
    'unit_years_filed' whatever the choices. Under the adopted rule neither folding is in play (years_filed, by
    utility-state), so the flag is each unit-year's own record and passing 'unit_years_filed' misleads nothing.

    step_window (added 2026-11-20, session 25; the session's reading, Joe's to strike). Row U's step U3 runs on 2015 to
    2025 (reconciliation_mu.U_STEPS), one year past the window the choices name, and a frame with a 2025 unit-year is
    refused under that window. His rule is stated for a utility-state-year ("Exclude a utility-state-year where the
    Short Form table records a filing, or, for 2019, the operational flag is true"), so for a step whose window runs
    past row U's own the same rule is applied year by year over the step's window: pass that window here. It may only
    contain the adopted window, never cut it. Under years_filed by utility-state a filing counts for its own year alone,
    so widening the frame's bound changes no flag of 2015 to 2024. On the records on file on 2026-11-20 no unit-year of
    2025 in the quantity panel has a row in the filer table, so this reading and a reading with no exclusion in 2025
    give the same flags there; the count is in docs/gate1/final-quantity-regeneration-2026-11-20.md."""
    choices = dict(ADOPTED_ROW_U_CHOICES)
    if step_window is not None:
        lo, hi = int(step_window[0]), int(step_window[1])
        a_lo, a_hi = ADOPTED_ROW_U_CHOICES["window"]
        if lo > a_lo or hi < a_hi:
            raise ValueError(f"step_window {(lo, hi)} does not contain the adopted window {(a_lo, a_hi)}; the adopted "
                             f"rule is not applied to a narrower window here")
        choices["window"] = (lo, hi)
    return sample_flags_from_table(frame, table, flags, **choices)


def _uy_list(df: pd.DataFrame) -> set:
    return set(zip(df.utility_id_eia.astype("int64"), df.state.astype(str), df.year.astype("int64")))


def _leaving(gone: pd.DataFrame, window: tuple[int, int]) -> dict:
    """Unit-years and distinct utilities in `gone`, by year and in total."""
    lo, hi = window
    return {"unit_years_by_year": {str(y): int((gone.year == y).sum()) for y in range(lo, hi + 1)},
            "utilities_by_year": {str(y): int(gone[gone.year == y].utility_id_eia.nunique()) for y in range(lo, hi + 1)},
            "unit_years_total": int(len(gone)), "utility_states": len(_units(gone)),
            "utilities": int(gone.utility_id_eia.nunique())}


def adopted_row_u_sample(frame_pre: pd.DataFrame, table: pd.DataFrame, flags: pd.DataFrame) -> dict:
    """Row U's quantity-side sample under the adopted rule (D-115), counts only. Pure: takes the frame, the filer table
    and the 2019 flags. frame_pre: row U's quantity-side rows BEFORE the three-year count (window, jurisdictions,
    ownership class; row_u_quantity_frame(q, three_year_count=False) or the same rows built by reconciliation_mu).

    Two computations, which must give the same sample (a check that stops in words if they do not):
      in the code's order: the flags built on frame_pre by adopted_row_u_flags, reconciliation_mu._u_drop_short_form
        under 'unit_years_filed', then reconciliation_mu._min_years. This is run_u_step's own order.
      reported apart, against the frame with no exclusion (frame_pre after the three-year count): the unit-years a
        record removes directly, then the unit-years that leave through the three-year requirement applied after
        that exclusion. This is how the reduction is described ("one flagged row leaves directly, and two other years
        leave through the three-year requirement", Joe, D-115, on the counts of 2026-11-20).
    The 2019 counts of unit-years kept with no record either way (a missing flag; no flags row) are given for the frame
    and for the sample after the rule. No price is read and the paper's missing-price drop is not applied, so this is
    NOT the paper's sample."""
    lo, hi = mu.RYU_WINDOW
    cols = ["utility_id_eia", "state", "year"]
    pre = frame_pre[cols].drop_duplicates().astype({"utility_id_eia": "int64", "year": "int64"})
    pre["state"] = pre.state.astype(str)
    pre = pre.reset_index(drop=True)
    frame, _ = mu._min_years(pre, mu.RYU_MIN_YEARS, mu.RYU_MIN_YEARS_LEVEL)
    sf = adopted_row_u_flags(pre, table, flags)
    spec = mu.ryu_spec(ADOPTED_ROW_U_MU_CODE)
    # the code's order (run_u_step): the Short Form filter on the rows before the count, then the count
    kept_pre, note_sf = mu._u_drop_short_form(pre, spec, sf, mu.RYU_WINDOW)
    final, note_count = mu._min_years(kept_pre, mu.RYU_MIN_YEARS, mu.RYU_MIN_YEARS_LEVEL)
    # reported apart, against the frame with no exclusion
    flag_of = {k: bool(v) for k, v in zip(zip(sf.utility_id_eia, sf.state, sf.year), sf.short_form)}
    direct_mask = [flag_of[k] for k in zip(frame.utility_id_eia, frame.state, frame.year)]
    direct = frame[direct_mask]
    after_direct = frame[[not x for x in direct_mask]]
    final_apart, _ = mu._min_years(after_direct, mu.RYU_MIN_YEARS, mu.RYU_MIN_YEARS_LEVEL)
    if _uy_list(final_apart) != _uy_list(final):
        raise ValueError("the sample under the adopted rule differs between run_u_step's order and the reduction "
                         "reported apart; nothing is reported")
    in_final = _uy_list(final_apart)
    three_year = after_direct[[k not in in_final for k in
                               zip(after_direct.utility_id_eia, after_direct.state, after_direct.year)]]
    pre_flagged = int(sf.short_form.sum())

    def counts_2019(rows: pd.DataFrame) -> dict:
        f19 = flags[flags.year == 2019][cols[:2] + ["short_form"]].copy()
        f19["utility_id_eia"] = f19.utility_id_eia.astype("int64")
        f19["state"] = f19.state.astype(str)
        f19["short_form"] = f19.short_form.astype("boolean")
        f19 = f19.drop_duplicates(cols[:2])
        r19 = rows[rows.year == 2019].merge(f19, on=cols[:2], how="left", indicator=True)
        return {"unit_years_in_2019": int(len(r19)),
                "flagged_true": int((r19.short_form == True).sum()),                        # noqa: E712
                "kept_with_no_record_either_way_missing_flag": int(((r19._merge == "both") & r19.short_form.isna()).sum()),
                "kept_with_no_record_either_way_no_flags_row": int((r19._merge == "left_only").sum())}

    def size(rows: pd.DataFrame) -> dict:
        return {"unit_years": int(len(rows)), "utility_states": len(_units(rows)),
                "utilities": int(rows.utility_id_eia.nunique())}

    return {
        "rule": ADOPTED_ROW_U_RULING,
        "rule_in_joes_words": ADOPTED_ROW_U_WORDS,
        "choices_supplied_to_sample_flags_from_table": {k: (list(v) if isinstance(v, tuple) else v)
                                                        for k, v in ADOPTED_ROW_U_CHOICES.items()},
        "reconciliation_mu_code": ADOPTED_ROW_U_MU_CODE,
        "label": mu.U_SHORT_FORM_ADOPTED_LABEL,
        "frame_with_no_exclusion": {
            "what_it_is": ("row U's quantity-side frame: unit-years 2015 to 2024 in the 50 states and DC with an "
                           "ownership class (scheme U, the panel's entity type, the utility-level modal reported type "
                           "carried across the panel, read over 2001 to 2025; D-117 and D-119), then the three-year "
                           "count by "
                           "utility, with no Short Form exclusion. No price read, so the paper's missing-price drop is "
                           "not applied"),
            **size(frame), "before_the_three_year_count": size(pre)},
        "leaving_directly_where_a_record_shows_a_filing": {
            "what_it_is": ("unit-years of the frame with no exclusion that carry a record of a Short Form filing (a "
                           "table row that year, or a 2019 flag of true) and leave for that reason"),
            **_leaving(direct, (lo, hi))},
        "leaving_through_the_three_year_requirement_after_the_exclusion": {
            "what_it_is": ("unit-years of the frame with no exclusion that carry no record of a filing and leave "
                           "because, once the direct exclusion is made, their utility appears in fewer than three years; "
                           "the three-year requirement is applied after the exclusion"),
            **_leaving(three_year, (lo, hi))},
        "sample_under_the_adopted_rule": {
            **size(final),
            "utility_states_removed_entirely_from_the_frame": len(_units(frame) - _units(final)),
            "utilities_removed_entirely_from_the_frame": len(set(frame.utility_id_eia) - set(final.utility_id_eia))},
        "in_run_u_steps_order": {
            "what_it_is": ("the same sample computed as run_u_step orders it: the Short Form filter on the rows before "
                           "the three-year count, then the count. Most flagged 2019 unit-years belong to utilities in "
                           "the panel in no other window year, which the three-year count removes with or without the "
                           "exclusion, so the reduction is reported against the frame with no exclusion"),
            "rows_before_the_three_year_count": int(len(pre)),
            "flagged_unit_years_among_them": pre_flagged,
            "after_the_short_form_filter": int(len(kept_pre)), "after_the_three_year_count": int(len(final)),
            "same_sample_as_reported_apart": True,
            "notes": [note_sf, note_count]},
        "year_2019_explicitly_incomplete": {
            "statement": ("The 2019 exclusion is explicitly incomplete. In 2019 the Short Form table has no rows, and the "
                          "exclusion rests on the operational file's flags; a 2019 unit-year with a missing flag or with "
                          "no flags row is kept with no record either way. A missing flag or an absent row does not "
                          "establish non-filing."),
            "in_the_frame_with_no_exclusion": counts_2019(frame),
            "in_the_sample_under_the_adopted_rule": counts_2019(final)},
        "not_the_papers_sample": ("The sample is still not the paper's. No price was read, the paper's missing-price "
                                  "drop is not applied, and the row's other approximations are ours."),
        "comparison_only": ("Row U is comparison-only (Joe, 2026-11-19, D-109); no reproduction claim attaches to it, "
                            "and these counts are no part of any reason for the rule."),
        PAPER_FIGURE_KEY: {"retained_utilities": PAPER_RETAINED_UTILITIES, "short_form_group": PAPER_SHORT_FORM_GROUP,
                           "where": "Ryu and Hiatt, Sec. 2.2 (p. 6) and endnote 10 (p. 17), as quoted in the access request",
                           "note": ("printed beside our counts for comparison only; never a target, a tiebreak or a "
                                    "reason for any choice")},
    }


# =================================================================================================================
# main
# =================================================================================================================
def main() -> int:
    hc, raw = run_read()
    print(f"hash equal: {hc['equal']}")
    if raw is None:
        print("stage 2 stopped at the hash; the reader was not called and nothing else was read")
        return 1
    print(f"columns returned: {list(raw.columns)}; rows read: {len(raw)}")
    table, by_year_read = build_table(raw)
    del raw
    # The table and the read's counts are written before the summary is computed, so that a failure in the summary
    # never calls for a second read: summary_from_written() rebuilds it from these two records alone.
    OUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(OUT_TABLE, index=False)
    _write_json(OUT_SUMMARY, {"what_this_is": WHAT_THIS_IS, "status": "the read's counts only; the summary follows",
                              "hash_check": hc, "read_by_year": by_year_read})
    print(f"table rows: {len(table)}; wrote {OUT_TABLE.name}")
    return _finish_summary(table, by_year_read, hc)


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _finish_summary(table: pd.DataFrame, by_year_read: dict, hc: dict) -> int:
    q = load_quantities()
    q = q[[c for c in ("utility_id_eia", "state", "year", "entity_type", "res_mwh") if c in q.columns]]
    flags = pd.read_parquet(FLAGS_2019, columns=["utility_id_eia", "state", "year", "short_form"])
    summary = summarize(table, by_year_read, q, flags, mu.RYU_WINDOW)
    summary["hash_check"] = hc
    summary["read_by_year"] = by_year_read
    _write_json(OUT_SUMMARY, summary)
    print(f"wrote {OUT_SUMMARY.name}")
    return 0


def summary_from_written() -> int:
    """Rebuild the summary from the written table and the read's counts in the summary file, reading nothing under
    data/raw. For use only if the summary step failed after the one read."""
    rec = json.loads(OUT_SUMMARY.read_text(encoding="utf-8"))
    table = pd.read_parquet(OUT_TABLE)
    table["state"] = table.state.astype("string")
    return _finish_summary(table, rec["read_by_year"], rec["hash_check"])


if __name__ == "__main__":
    sys.exit(summary_from_written() if sys.argv[1:] == ["--summary-from-written"] else main())
