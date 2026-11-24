#!/usr/bin/env python3
"""The reshaper for the specified outcome frames, and the checks that can only be made when the outcome file is read.

Reads NO file. The outcome file's frame, the quantity panel's frame and row C's price-index factors are arguments; the
reshaper returns one frame per named outcome of the registry (run_outcomes.OUTCOMES), each with the columns the registry
takes (utility_id_eia, state, year, value). The plan is frozen at commit ea426c4 (the approved specification is commit
ed3a2ff); it is internally frozen and not externally preregistered. No host utility's price in the outcome data has been
read; one lapse in source access is disclosed in the plan and qualifies that statement. Everything here was built and
tested on invented frames only. Reading the outcome file is a later, separately authorized step, and nothing here does it.

Owner's words (Joe, session 27): "Build the reshaper for the specified outcome frames, following the frozen source
columns, units, transformations and non-computable rules. Test it on invented inputs only."

The seven frames, and where each construction is read
------------------------------------------------------
Units are read from pipeline/electricity/panel.py build() as code (never run here). Revenue there is in dollars, which
is the agent's reading of panel.py, the same reading supplementary_outcomes states. The price line divides revenue by MWh
and by 10 to give cents per kWh, which holds for dollars.

PRICE ("log_residential_price"): the natural log of the outcome file's res_price (res_revenue_full / res_mwh / 10, cents
  per kWh, competitive supply added for delivery-only customers). Plan, section "Electricity: the main estimate", the
  Outcome bullet ("log residential price"); power_simulation builds the same thing as np.log(res_price) on the rows it
  keeps. Neither the usable flag nor the size floor is applied here. The plan's Outcome and Missing data bullets apply
  the flag to the design (who is in a sub-experiment, who is an eligible comparison utility), the designs are built on
  the usable set, and the kernel reads only a design's rows. The frame carries every row of the outcome file.
PRICE_DEFAULT_SERVICE ("res_price_default_service"): the level of res_price_default_service (bundled revenue over
  bundled sales / 10, cents per kWh). Row U logs it (reconciliation_mu._outcome_rows inside run_u_step), so it is
  supplied as a level, untouched.
PRICE_DELIVERY_INCLUSIVE ("res_price"): the level of res_price, cents per kWh, untouched, for row U, which logs it.
PRICE_CENTS_REAL_2024: res_price times row C's CPI-U factor for its year (reconciliation_c.cpi_factors_to_2024, the
  factor cpi_u[2024] / cpi_u[year]), real 2024 cents per kWh. Our comparison specification (reconciliation_c.
  PRICE_SERIES_LABEL), and not a claim that the paper used exactly this construction. By the session's reading
  (ROW_C_WINDOW_RULE) this frame carries only the unit-years of row C's window, reconciliation_c.YEARS (2015 to 2024),
  the row's own first step; rows outside it are counted and are not in the frame. A window year with no factor stops
  this frame in words and nothing is filled. No other frame is restricted in any way.
KWH: the level of res_kwh_per_customer_month (res_mwh * 1000 / res_customers / 12, kWh per residential customer per
  month). BILL: the level of res_bill_per_customer_month (res_revenue_full / res_customers / 12, nominal dollars per
  residential customer per month, no price index). CUSTOMERS: the level of res_customers, from the QUANTITY panel's frame
  and never from the outcome file. For these three supplementary_outcomes takes the log and applies the non-computable
  rule (Joe, 2026-11-20, D-117); the caller supplies levels in each Spec's unit (supplementary_outcomes.SPECS). The
  reshaper adds no constant, fills nothing and drops nothing.

What the reshaper never does
----------------------------
It never fills, imputes, clips, deduplicates or drops a row to make a frame acceptable to the kernel
(outcome_analysis._vector_for_rows stops on a missing column, a repeated unit-year, a missing unit-year and a value that
is not finite). A missing source column stops the frames built from it. A repeated (utility_id_eia, state, year) in a
source frame stops every frame built from that source, with the count and no value. A frame that cannot be built is
absent from Reshaped.frames and present in Reshaped.report with its reason; the other frames are still built. No message,
record or exception carries a value of an outcome, only counts and keys. The source frames are never modified.

Values that cannot be transformed (the agent's reading, stated in VALUE_RULES and in each frame's report)
----------------------------------------------------------------------------------------------------------
For the log price, a source res_price that is missing, not finite, or zero or negative has no logarithm. Its row is kept
with NaN as the value and counted by reason. The reshaper never produces an infinite value. NaN is the one value the
kernel refuses on any row a design needs, so such a row can never enter an estimate, and the frame is not stopped. Unit-
years outside the usable set carry a missing price by construction (panel.py leaves an unpriceable row's price missing),
and the usable flag, which requires res_price above zero, keeps them out of every design. Stopping the whole frame for
them would block a construction the plan specifies.
For rows U and C, NaN is the panel's own marker of no price, which each row's code treats under its own missing-price
rule; it is carried. A value of plus or minus infinity in their source stops the frame instead, because neither row's code
refuses it (row U would take its log as an observed price, row C would count it as observed in its balanced sample), and
turning it into NaN would silently move the row's sample. panel.py stops a priceable row whose price is not finite, so
this cannot arise from the panel's build; the stop is defensive. Zero or negative levels are carried (row U records them
as numerical failures in words; row C works in levels).
For the three supplementary levels every value is carried untouched, infinity included, because
supplementary_outcomes.check_levels classifies missing, not finite and not positive on the rows a design requires, and
the D-117 rule is defined on those rows only.

Key types
---------
The kernel casts the id and the year and not the state. Every frame comes back with utility_id_eia and year as int64,
state as an object column of plain Python str, and value as float64. An id or year that is missing, not a whole number,
boolean or text is refused in words (never truncated, and never parsed from text, which is the agent's reading). A missing
state, or a state that is not text, is refused in words.

read_time_checks
----------------
Pure checks on frames, for the authorized read (deferred, and nothing runs them now). Counts and keys only; each returns a
`passed` field and a `passes` sentence. Row C's price-balanced sample is the row's own computation
(reconciliation_c.build_panel and balanced_units) and is not rebuilt here.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import reconciliation_c as rc  # noqa: E402
from pipeline.analysis import reconciliation_mu as rmu  # noqa: E402
from pipeline.analysis import supplementary_outcomes as so  # noqa: E402

KEY = list(oa.KEY)                         # utility_id_eia, state
UNIT_YEAR = KEY + ["year"]
VALUE = "value"                            # run_outcomes.OUTCOME
FRAME_COLUMNS = UNIT_YEAR + [VALUE]

FROZEN_AT = "ea426c4"
BLINDING = ("No host utility's price in the outcome data has been read; one lapse in source access is disclosed in the "
            "plan and qualifies that statement.")
# What a record made at a read says (session 28): the present tense above stops being accurate at the first authorized
# read, so a record written at a read carries a statement that does not depend on when it is read back.
BLINDING_AT_A_READ = ("When these checks are run on the research outcome file, that file has been read through the guarded "
                      "coordinator, and the time of the read is in the door's record beside this one (read_at_utc). No "
                      "host utility's price in the outcome data was read before the first authorized read, with one "
                      "lapse in source access disclosed in the plan.")

# The outcome names. run_outcomes imports more than this module needs and may one day import this module, so the names
# are taken from the modules run_outcomes takes them from, and the two it defines itself are written here; a test holds
# them equal to run_outcomes.OUTCOMES.
PRICE = "log_residential_price"
KWH, BILL, CUSTOMERS = so.KWH, so.BILL, so.CUSTOMERS
PRICE_DEFAULT_SERVICE = rmu.DEFAULT_SERVICE            # "res_price_default_service"
PRICE_DELIVERY_INCLUSIVE = rmu.DELIVERY_INCLUSIVE      # "res_price"
PRICE_CENTS_REAL_2024 = "res_price_cents_per_kwh_real_2024"
NAMES = (PRICE, KWH, BILL, CUSTOMERS, PRICE_DEFAULT_SERVICE, PRICE_DELIVERY_INCLUSIVE, PRICE_CENTS_REAL_2024)

# The outcome file's columns, as panel.build() returns them (outcome_cols, read as code).
OUTCOME_FILE_COLUMNS = ("utility_id_eia", "state", "year", "res_revenue_full", "res_price", "res_price_delivery_only",
                        "res_price_default_service", "res_bill_per_customer_month", "res_kwh_per_customer_month",
                        "energy_price_state")

OUTCOME_FILE = "outcomes"
QUANTITY_PANEL = "quantities"
SOURCE_IN_WORDS = {OUTCOME_FILE: "the panel's outcome file (a frame the caller passes; this module opens no file)",
                   QUANTITY_PANEL: "the panel's quantity file (a frame the caller passes; this module opens no file)"}

LOG, LEVEL, DEFLATE = "natural log", "level, untouched", "times row C's CPI-U factor for the year"

# How a value that cannot be transformed or carried is handled, per frame (the agent's reading; module docstring).
NAN_FOR_NO_LOG = ("a missing, not finite, or zero or negative res_price has no logarithm, so the row is kept with NaN and "
                  "counted by reason, never an infinite value; the kernel refuses NaN on any row a design needs, so it "
                  "never enters an estimate (the agent's reading)")
ROW_LEVEL_RULE = ("NaN is carried (the panel's marker of no price, which the row's code treats under its missing-price "
                  "rule); zero or negative is carried; plus or minus infinity stops the frame, because the row's code "
                  "does not refuse it and turning it into NaN would silently move the row's sample (the agent's reading)")
SUPPLEMENTARY_RULE = ("every value carried untouched, infinity included, because supplementary_outcomes classifies missing, not "
                      "finite and not positive on the rows a design requires and applies the D-117 rule there")
ROW_C_LEVEL_RULE = ("inside row C's window, " + ROW_LEVEL_RULE + "; outside the window a row is not in the frame and "
                    "is counted, an infinite value there included (the session's reading)")
VALUE_RULES = MappingProxyType({PRICE: NAN_FOR_NO_LOG, PRICE_DEFAULT_SERVICE: ROW_LEVEL_RULE,
                                PRICE_DELIVERY_INCLUSIVE: ROW_LEVEL_RULE, PRICE_CENTS_REAL_2024: ROW_C_LEVEL_RULE,
                                KWH: SUPPLEMENTARY_RULE, BILL: SUPPLEMENTARY_RULE, CUSTOMERS: SUPPLEMENTARY_RULE})

ROW_C_YEARS = tuple(int(y) for y in rc.YEARS)          # 2015-2024
ROW_C_WINDOW_IN_WORDS = f"row C's window, the years {ROW_C_YEARS[0]} to {ROW_C_YEARS[-1]} (reconciliation_c.YEARS)"
ROW_C_WINDOW_RULE = (
    "The session's reading (session 27): this frame is built on the unit-years whose year is in reconciliation_c.YEARS "
    "and no other, so it is row C's window and not the whole outcome file. That is the row's own first step "
    "(reconciliation_c.build_panel keeps year in YEARS before anything else), and cpi_factors_to_2024 is specified for "
    "that window (it refuses only a missing window year). Rows outside the window are not in the frame and are counted "
    "(rows_outside_row_c_window). A window year with no factor stops the frame and nothing is filled; a year outside the "
    "window needs no factor. An infinite value inside the window stops the frame; one outside the window is outside the "
    "frame and is counted (rows_outside_row_c_window_not_finite), not a stop, since the row never reads it. No other "
    "frame is restricted.")
ROW_C_BALANCED_SAMPLE_LEFT_TO_THE_ROW = (
    "Row C's price-balanced sample (units with a non-missing price in every year 2015-2024, contiguous states, a fiber "
    "share) is the row's own computation in reconciliation_c.build_panel and balanced_units. It is not rebuilt or checked "
    "here.")


@dataclass(frozen=True)
class FrameSpec:
    """One outcome frame: where its value comes from, in what unit, how it is transformed and where that is read."""
    name: str
    source: str
    source_column: str
    source_unit: str
    transformation: str
    unit: str
    read_from: str
    handled_by: str


SPECS = MappingProxyType({
    PRICE: FrameSpec(
        PRICE, OUTCOME_FILE, "res_price",
        "cents per kWh, nominal: res_revenue_full / res_mwh / 10.0 (panel.py build)", LOG,
        "natural log of cents per kWh",
        "PREANALYSIS.md, Electricity: the main estimate, the Outcome bullet ('log residential price'); "
        "power_simulation.py, np.log(res_price) on the rows it keeps",
        "outcome_analysis.outcome_vector, which reads the design's rows only and refuses NaN"),
    PRICE_DEFAULT_SERVICE: FrameSpec(
        PRICE_DEFAULT_SERVICE, OUTCOME_FILE, "res_price_default_service",
        "cents per kWh, nominal: res_revenue_bundled / res_mwh_bundled / 10.0 where bundled sales are positive (panel.py "
        "build)", LEVEL, "cents per kWh, nominal",
        "PREANALYSIS.md, The reconciliation rows, row U's specification; reconciliation_mu.DEFAULT_SERVICE, logged in "
        "reconciliation_mu._outcome_rows inside run_u_step",
        "reconciliation_mu.run_u_step, which logs it"),
    PRICE_DELIVERY_INCLUSIVE: FrameSpec(
        PRICE_DELIVERY_INCLUSIVE, OUTCOME_FILE, "res_price",
        "cents per kWh, nominal: res_revenue_full / res_mwh / 10.0 (panel.py build)", LEVEL, "cents per kWh, nominal",
        "reconciliation_mu.DELIVERY_INCLUSIVE, logged in reconciliation_mu._outcome_rows inside run_u_step",
        "reconciliation_mu.run_u_step, which logs it"),
    PRICE_CENTS_REAL_2024: FrameSpec(
        PRICE_CENTS_REAL_2024, OUTCOME_FILE, rc.OURS_PRICE_SERIES, rc.PRICE_SERIES_UNIT, DEFLATE,
        rc.PRICE_SERIES_REAL_UNIT,
        "PREANALYSIS.md, The reconciliation rows, row C's specification (D-117 and D-111); reconciliation_c."
        "OURS_PRICE_SERIES, PRICE_SERIES_LABEL, cpi_factors_to_2024 and build_panel. " + rc.PRICE_SERIES_LABEL,
        "reconciliation_c (row C), in levels"),
    KWH: FrameSpec(
        KWH, OUTCOME_FILE, so.SPECS[KWH].source_column, so.SPECS[KWH].unit + ": " + so.SPECS[KWH].level_in_the_panel,
        LEVEL, so.SPECS[KWH].unit,
        "PREANALYSIS.md, Other outcomes and robustness (D-117); supplementary_outcomes.SPECS",
        "supplementary_outcomes, which logs it and applies the non-computable rule"),
    BILL: FrameSpec(
        BILL, OUTCOME_FILE, so.SPECS[BILL].source_column, so.SPECS[BILL].unit + ": " + so.SPECS[BILL].level_in_the_panel,
        LEVEL, so.SPECS[BILL].unit,
        "PREANALYSIS.md, Other outcomes and robustness (D-117); supplementary_outcomes.SPECS",
        "supplementary_outcomes, which logs it and applies the non-computable rule"),
    CUSTOMERS: FrameSpec(
        CUSTOMERS, QUANTITY_PANEL, so.SPECS[CUSTOMERS].source_column,
        so.SPECS[CUSTOMERS].unit + ": " + so.SPECS[CUSTOMERS].level_in_the_panel, LEVEL, so.SPECS[CUSTOMERS].unit,
        "PREANALYSIS.md, Other outcomes and robustness (D-117: 'a column of the quantity file'); "
        "supplementary_outcomes.SPECS",
        "supplementary_outcomes, which logs it and applies the non-computable rule"),
})


class ReshapeRefused(ValueError):
    """A source frame, a column or the factors cannot be used as they stand. The message carries counts, column names,
    dtype names and keys, never a value of an outcome."""


@dataclass
class Reshaped:
    """frames: outcome name to its frame (utility_id_eia int64, state str objects, year int64, value float64), for every
    frame that could be built. report: outcome name to a counts-only record, for every name, built or not."""
    frames: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)


# ---- keys ------------------------------------------------------------------------------------------------------------

def _whole_int64(s: pd.Series, column: str, source: str) -> np.ndarray:
    """A key column as int64, refused in words if any entry is missing, boolean, text or not a whole number."""
    if pd.api.types.is_bool_dtype(s.dtype):
        raise ReshapeRefused(f"{source}: {column} is boolean (dtype {s.dtype}); a key is a whole number")
    n_missing = int(s.isna().sum())
    if n_missing:
        raise ReshapeRefused(f"{source}: {n_missing} rows have no {column}; nothing is filled")
    if pd.api.types.is_integer_dtype(s.dtype):
        return s.to_numpy(dtype="int64")
    if pd.api.types.is_float_dtype(s.dtype):
        v = s.to_numpy(dtype=float)
    elif s.dtype == object:
        kinds = {type(x).__name__ for x in s if not isinstance(x, (int, float, np.integer, np.floating))
                 or isinstance(x, (bool, np.bool_))}
        if kinds:
            raise ReshapeRefused(f"{source}: {column} holds entries that are not numbers (types {sorted(kinds)}); a key "
                                 "is never parsed from text")
        v = np.array([float(x) for x in s], dtype=float)
    else:
        raise ReshapeRefused(f"{source}: {column} has dtype {s.dtype}, not a whole-number type; a key is never parsed "
                             "from text")
    bad = ~np.isfinite(v) | (v != np.round(v)) | (np.abs(v) > 2.0 ** 53)
    if bad.any():
        raise ReshapeRefused(f"{source}: {int(bad.sum())} rows have a {column} that is not a whole number; nothing is "
                             "truncated")
    return v.astype("int64")


def _state_strings(s: pd.Series, source: str) -> np.ndarray:
    """The state column as an object array of plain Python str. A missing state, or one that is not text, is refused."""
    n_missing = int(s.isna().sum())
    if n_missing:
        raise ReshapeRefused(f"{source}: {n_missing} rows have no state; nothing is filled")
    vals = s.astype(object).to_numpy()
    kinds = {type(x).__name__ for x in vals if not isinstance(x, str)}
    if kinds:
        raise ReshapeRefused(f"{source}: state holds entries that are not text (types {sorted(kinds)})")
    return np.array([str(x) for x in vals], dtype=object)


def _keys(frame, source: str) -> pd.DataFrame:
    """The source's unit-year keys, typed explicitly, in the source's row order, on a fresh index. Stops in words on a
    frame that is not a DataFrame, a missing key column, a bad key or a repeated unit-year."""
    if not isinstance(frame, pd.DataFrame):
        raise ReshapeRefused(f"{source}: not a DataFrame ({type(frame).__name__})")
    missing = [c for c in UNIT_YEAR if c not in frame.columns]
    if missing:
        raise ReshapeRefused(f"{source}: no key column {missing}")
    k = pd.DataFrame({"utility_id_eia": _whole_int64(frame["utility_id_eia"], "utility_id_eia", source),
                      "state": _state_strings(frame["state"], source),
                      "year": _whole_int64(frame["year"], "year", source)})
    k["state"] = k["state"].astype(object)
    dup = k.duplicated(UNIT_YEAR, keep=False)
    if dup.any():
        first = k[dup].iloc[0]
        raise ReshapeRefused(f"{source}: {int(dup.sum())} rows repeat a unit-year ({int(k.duplicated(UNIT_YEAR).sum())} "
                             f"repeated keys), for example {int(first.utility_id_eia)}:{first.state} in "
                             f"{int(first.year)}; nothing is deduplicated")
    return k


# ---- values ----------------------------------------------------------------------------------------------------------

def _floats(s: pd.Series, column: str, source: str) -> np.ndarray:
    """A value column as float64, None, NaN and pd.NA alike becoming NaN. Boolean, text or any other non-number is refused
    in words without showing it."""
    if pd.api.types.is_bool_dtype(s.dtype):
        raise ReshapeRefused(f"{source}: {column} is boolean (dtype {s.dtype}), not a number")
    if pd.api.types.is_numeric_dtype(s.dtype):
        return s.to_numpy(dtype=float, na_value=np.nan)
    if s.dtype == object:
        ok = [x is None or (isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, (bool, np.bool_)))
              or (x is pd.NA) for x in s]
        n_bad = len(ok) - int(sum(ok))
        if n_bad:
            raise ReshapeRefused(f"{source}: {n_bad} rows of {column} hold something that is not a number (not shown)")
        return np.array([np.nan if (x is None or x is pd.NA) else float(x) for x in s], dtype=float)
    raise ReshapeRefused(f"{source}: {column} has dtype {s.dtype}, not a number type; a value is never parsed from text")


def _counts(v: np.ndarray) -> dict:
    missing = np.isnan(v)
    nonfinite = np.isinf(v)
    return {"values_missing": int(missing.sum()), "values_not_finite": int(nonfinite.sum()),
            "values_not_positive": int((np.isfinite(v) & (v <= 0)).sum())}


def _factor_lookup(cpi_factors, years: np.ndarray) -> np.ndarray:
    """Row C's factor for each year, refused in words if the factors are not a mapping, a key is not a whole year, a
    factor is not a positive finite number, or a year of the frame has none. Nothing is filled."""
    if not isinstance(cpi_factors, Mapping):
        raise ReshapeRefused(f"row C's factors are not a mapping of year to factor ({type(cpi_factors).__name__}); "
                             "reconciliation_c.cpi_factors_to_2024 returns one")
    table = {}
    for y, f in cpi_factors.items():
        if isinstance(y, (bool, np.bool_)) or not isinstance(y, (int, np.integer)):
            raise ReshapeRefused(f"row C's factors have a key that is not a whole year (type {type(y).__name__})")
        if isinstance(f, (bool, np.bool_)) or not isinstance(f, (int, float, np.integer, np.floating)) \
                or not np.isfinite(f) or f <= 0:
            raise ReshapeRefused(f"row C's factor for {int(y)} is not a positive finite number")
        table[int(y)] = float(f)
    absent = sorted({int(y) for y in years} - set(table))
    if absent:
        raise ReshapeRefused(f"row C's factors have no factor for {len(absent)} years of the frame, {absent}; nothing is "
                             "filled (reconciliation_c.cpi_factors_to_2024)")
    return np.array([table[int(y)] for y in years], dtype=float)


def _frame(keys: pd.DataFrame, value: np.ndarray) -> pd.DataFrame:
    f = keys.copy()
    f[VALUE] = np.asarray(value, dtype="float64")
    f["state"] = f["state"].astype(object)
    return f[FRAME_COLUMNS]


def _build(name: str, source_frame: pd.DataFrame, keys: pd.DataFrame, cpi_factors) -> tuple[pd.DataFrame, dict]:
    """One frame and its counts. Raises ReshapeRefused in words when it cannot be built."""
    spec = SPECS[name]
    src = SOURCE_IN_WORDS[spec.source]
    if spec.source_column not in source_frame.columns:
        raise ReshapeRefused(f"{src}: no column {spec.source_column!r}; this frame is not built")
    v = _floats(source_frame[spec.source_column], spec.source_column, src)
    counts = _counts(v)
    extra = {}
    if spec.transformation == LOG:
        ok = np.isfinite(v) & (v > 0)
        out = np.full(v.shape, np.nan)
        out[ok] = np.log(v[ok])
        extra = {"set_to_nan_by_the_transformation": int((~ok).sum()),
                 "set_to_nan_because_missing": counts["values_missing"],
                 "set_to_nan_because_not_finite": counts["values_not_finite"],
                 "set_to_nan_because_not_positive": counts["values_not_positive"]}
    elif spec.transformation == DEFLATE:
        # The session's reading (session 27): this frame is row C's window only (ROW_C_WINDOW_RULE).
        inside = keys["year"].isin(ROW_C_YEARS).to_numpy()
        outside = ~inside
        extra = {"row_c_window": ROW_C_WINDOW_IN_WORDS, "row_c_window_rule": ROW_C_WINDOW_RULE,
                 "rows_outside_row_c_window": int(outside.sum()),
                 "rows_outside_row_c_window_not_finite": int((outside & np.isinf(v)).sum()),
                 "counts_are_over": "the rows inside row C's window"}
        keys = keys[inside].reset_index(drop=True)
        v = v[inside]
        counts = _counts(v)
        if counts["values_not_finite"]:
            raise ReshapeRefused(f"{src}: {counts['values_not_finite']} rows of {spec.source_column} inside row C's "
                                 "window are plus or minus infinity, which row C's code would count as observed; this "
                                 "frame is stopped and nothing is replaced")
        factor = _factor_lookup(cpi_factors, keys["year"].to_numpy())
        with np.errstate(over="ignore"):             # an overflow is caught on the next line and stops the frame
            out = v * factor
        overflow = np.isfinite(v) & ~np.isfinite(out)
        if overflow.any():
            raise ReshapeRefused(f"{int(overflow.sum())} rows are not finite after the deflation; this frame is stopped")
    else:
        if name in (PRICE_DEFAULT_SERVICE, PRICE_DELIVERY_INCLUSIVE) and counts["values_not_finite"]:
            raise ReshapeRefused(f"{src}: {counts['values_not_finite']} rows of {spec.source_column} are plus or minus "
                                 "infinity, which row U's code would log as an observed price; this frame is stopped and "
                                 "nothing is replaced")
        out = v.copy()
    if np.isinf(out).any() and spec.transformation != LEVEL:
        raise AssertionError("the reshaper produced an infinite value")      # unreachable by construction; checked
    f = _frame(keys, out)
    rec = {**counts, **extra, "rows_in": int(len(source_frame)), "rows_out": int(len(f)),
           "values_missing_out": int(np.isnan(out).sum()), "values_not_finite_out": int(np.isinf(out).sum())}
    return f, rec


def reshape(outcomes, quantities, cpi_factors) -> Reshaped:
    """The seven outcome frames from the outcome file's frame, the quantity panel's frame and row C's factors (a mapping
    of year to factor, as reconciliation_c.cpi_factors_to_2024 returns it). Opens no file and modifies no argument.

    Every name in NAMES is in the report; a frame that cannot be built is absent from `frames` and its record carries
    `built: False` and `reason_not_built` in words. One frame's failure never stops another's: a problem with a source's
    keys stops the frames of that source only, a missing column stops the frames built from it only, and a factor problem
    stops row C's frame only."""
    out = Reshaped()
    sources = {OUTCOME_FILE: outcomes, QUANTITY_PANEL: quantities}
    keys, key_problem = {}, {}
    for which, frame in sources.items():
        try:
            keys[which] = _keys(frame, SOURCE_IN_WORDS[which])
            out.sources[which] = {"rows": int(len(frame)), "key_dtypes_in": {c: str(frame[c].dtype) for c in UNIT_YEAR},
                                  "keys_usable": True}
        except ReshapeRefused as e:
            key_problem[which] = str(e)
            out.sources[which] = {"keys_usable": False, "reason": str(e)}
    for name in NAMES:
        spec = SPECS[name]
        rec = {"name": name, "source": SOURCE_IN_WORDS[spec.source], "source_column": spec.source_column,
               "source_unit": spec.source_unit, "transformation": spec.transformation, "unit": spec.unit,
               "read_from": spec.read_from, "handled_by": spec.handled_by, "value_rule": VALUE_RULES[name]}
        if name == PRICE_CENTS_REAL_2024:
            rec["label"] = rc.PRICE_SERIES_LABEL
            rec["left_to_the_row"] = ROW_C_BALANCED_SAMPLE_LEFT_TO_THE_ROW
        if spec.source in key_problem:
            rec.update(built=False, reason_not_built=key_problem[spec.source])
        else:
            try:
                f, counts = _build(name, sources[spec.source], keys[spec.source], cpi_factors)
                out.frames[name] = f
                rec.update(built=True, reason_not_built=None, **counts)
            except ReshapeRefused as e:
                rec.update(built=False, reason_not_built=str(e))
        out.report[name] = rec
    return out


# ======================================================================================================================
# The checks that can only be made at the authorized read (deferred; pure functions on frames)
# ======================================================================================================================

EXAMPLES = 5


def _label(u, s, y) -> str:
    return f"{int(u)}:{s} in {int(y)}"


def _verdict(ok: bool | None, yes: str, no: str, na: str = "") -> dict:
    if ok is None:
        return {"passed": None, "passes": "not applicable: " + na}
    return {"passed": bool(ok), "passes": ("yes: " + yes) if ok else ("no: " + no)}


def _check_key_types(outcomes, quantities) -> tuple[dict, dict]:
    res, keys = {}, {}
    for which, frame in ((OUTCOME_FILE, outcomes), (QUANTITY_PANEL, quantities)):
        dt = ({c: str(frame[c].dtype) for c in UNIT_YEAR if c in frame.columns}
              if isinstance(frame, pd.DataFrame) else {})
        try:
            keys[which] = _keys(frame, SOURCE_IN_WORDS[which])
            res[which] = {"dtypes": dt, "usable_as_keys": True, "reason": None}
        except ReshapeRefused as e:
            res[which] = {"dtypes": dt, "usable_as_keys": False, "reason": str(e)}
    same = {c: res[OUTCOME_FILE]["dtypes"].get(c) == res[QUANTITY_PANEL]["dtypes"].get(c) for c in UNIT_YEAR}
    res["same_dtype_by_column"] = same
    ok = res[OUTCOME_FILE]["usable_as_keys"] and res[QUANTITY_PANEL]["usable_as_keys"]
    res.update(_verdict(ok, "both frames' keys are whole-number ids and years and text states with no repeated unit-year "
                            "(dtypes may differ; both are cast to int64, str and int64)",
                        "a frame's keys cannot be used as they stand; see each frame's reason"))
    return res, keys


def _outcome_keys_without_dup_stop(outcomes) -> pd.DataFrame | None:
    """The outcome frame's keys typed as _keys types them, but without the repeated-unit-year stop, so the duplicate check
    can count. None if the keys themselves cannot be typed."""
    if not isinstance(outcomes, pd.DataFrame) or any(c not in outcomes.columns for c in UNIT_YEAR):
        return None
    try:
        return pd.DataFrame({"utility_id_eia": _whole_int64(outcomes["utility_id_eia"], "utility_id_eia", "o"),
                             "state": _state_strings(outcomes["state"], "o"),
                             "year": _whole_int64(outcomes["year"], "year", "o")})
    except ReshapeRefused:
        return None


def read_time_checks(outcomes, quantities, usable=None, row_u_flags=None, row_u_window=None) -> dict:
    """The checks that can only be made when the outcome file is read: counts and keys only, never a value.

    `outcomes` is the outcome file's frame, `quantities` the quantity panel's frame, `usable` the set of (utility_id_eia,
    state, year) that usable_flag.validate gives, `row_u_flags` row U's Short Form flags frame (utility_id_eia, state,
    year, short_form) and `row_u_window` a (first year, last year) pair. Returns a dict of checks, each with counts and
    `passed` (True, False, or None where it does not apply) and `passes` in words. Raises nothing for a bad frame: the
    check that cannot be made says so."""
    out = {"what_this_is": ("checks for an authorized read of the outcome file, on frames passed in. The plan is frozen "
                            "at commit " + FROZEN_AT + ". " + BLINDING_AT_A_READ),
           "left_to_the_rows": [ROW_C_BALANCED_SAMPLE_LEFT_TO_THE_ROW]}
    kt, keys = _check_key_types(outcomes, quantities)
    out["key_types"] = kt

    # Repeated unit-years in the outcome file.
    ok_ = _outcome_keys_without_dup_stop(outcomes)
    if ok_ is None:
        out["duplicate_unit_years_in_outcomes"] = {"rows_repeating": None, "repeated_keys": None,
                                                   **_verdict(None, "", "", "the outcome frame's keys cannot be typed")}
    else:
        dup = ok_.duplicated(UNIT_YEAR, keep=False)
        ex = sorted({_label(*r) for r in ok_[dup][UNIT_YEAR].itertuples(index=False)})[:EXAMPLES]
        out["duplicate_unit_years_in_outcomes"] = {
            "rows_repeating": int(dup.sum()), "repeated_keys": int(ok_.duplicated(UNIT_YEAR).sum()), "examples": ex,
            **_verdict(not dup.any(), "no unit-year is repeated", "unit-years are repeated; nothing is deduplicated")}

    both = OUTCOME_FILE in keys and QUANTITY_PANEL in keys
    if both:
        o, q = keys[OUTCOME_FILE], keys[QUANTITY_PANEL]
        m = q.merge(o, on=UNIT_YEAR, how="outer", indicator=True)
        q_only = m[m["_merge"] == "left_only"]
        o_only = m[m["_merge"] == "right_only"]
        out["coverage"] = {
            "quantity_unit_years_with_no_outcome_row": int(len(q_only)),
            "outcome_unit_years_with_no_quantity_row": int(len(o_only)),
            "examples_quantity_only": sorted({_label(*r) for r in q_only[UNIT_YEAR].itertuples(index=False)})[:EXAMPLES],
            "examples_outcome_only": sorted({_label(*r) for r in o_only[UNIT_YEAR].itertuples(index=False)})[:EXAMPLES],
            **_verdict(len(q_only) == 0 and len(o_only) == 0,
                       "the two frames hold the same unit-years (panel.build returns both from one frame)",
                       "the two frames do not hold the same unit-years")}
    else:
        out["coverage"] = _verdict(None, "", "", "a frame's keys cannot be used (see key_types)")

    # Usable unit-years with no positive finite res_price row.
    if usable is None:
        out["usable_without_positive_price"] = _verdict(None, "", "", "no usable set was passed")
    elif OUTCOME_FILE not in keys or "res_price" not in outcomes.columns:
        out["usable_without_positive_price"] = _verdict(None, "", "", "the outcome frame's keys or its res_price column "
                                                                      "cannot be used")
    else:
        try:
            v = _floats(outcomes["res_price"], "res_price", SOURCE_IN_WORDS[OUTCOME_FILE])
        except ReshapeRefused as e:
            out["usable_without_positive_price"] = _verdict(None, "", "", str(e))
        else:
            o = keys[OUTCOME_FILE].assign(_v=v)
            u = pd.DataFrame(sorted((int(a), str(b), int(c)) for a, b, c in usable), columns=UNIT_YEAR)
            m = u.merge(o, on=UNIT_YEAR, how="left", indicator=True)
            vals = m["_v"].to_numpy(dtype=float)
            no_row = (m["_merge"] == "left_only").to_numpy()
            miss = ~no_row & np.isnan(vals)
            nonfin = ~no_row & np.isinf(vals)
            nonpos = ~no_row & np.isfinite(vals) & (vals <= 0)
            bad = no_row | miss | nonfin | nonpos
            out["usable_without_positive_price"] = {
                "usable_unit_years": int(len(u)), "with_no_outcome_row": int(no_row.sum()),
                "price_missing": int(miss.sum()), "price_not_finite": int(nonfin.sum()),
                "price_not_positive": int(nonpos.sum()),
                "examples": sorted({_label(*r) for r in m[bad][UNIT_YEAR].itertuples(index=False)})[:EXAMPLES],
                **_verdict(not bad.any(), "every usable unit-year has a positive finite res_price row (the usable flag "
                                          "requires res_price above zero)",
                           "some usable unit-years have no positive finite res_price row")}

    # kWh and bill: rows that could not be logged, over the whole outcome file.
    lg = {}
    for col in (so.SPECS[KWH].source_column, so.SPECS[BILL].source_column):
        if not isinstance(outcomes, pd.DataFrame) or col not in outcomes.columns:
            lg[col] = {"reason": f"no column {col!r} in the outcome frame"}
            continue
        try:
            v = _floats(outcomes[col], col, SOURCE_IN_WORDS[OUTCOME_FILE])
        except ReshapeRefused as e:
            lg[col] = {"reason": str(e)}
            continue
        c = _counts(v)
        lg[col] = {"rows": int(len(v)), "missing": c["values_missing"], "not_finite": c["values_not_finite"],
                   "not_positive": c["values_not_positive"]}
    out["kwh_and_bill_not_loggable"] = {
        **lg, "passed": None,
        "passes": ("not a gate: these are counts over every row of the outcome file. The non-computable rule (D-117) is "
                   "applied by supplementary_outcomes on the rows a design requires, and only there")}

    # Row U's Short Form flags against the outcome unit-years in the window.
    if row_u_flags is None or row_u_window is None:
        out["row_u_short_form_flags"] = _verdict(None, "", "", "no flags frame or no window was passed")
    elif OUTCOME_FILE not in keys:
        out["row_u_short_form_flags"] = _verdict(None, "", "", "the outcome frame's keys cannot be used")
    elif not isinstance(row_u_flags, pd.DataFrame) or not set(UNIT_YEAR + ["short_form"]) <= set(row_u_flags.columns):
        out["row_u_short_form_flags"] = _verdict(None, "", "", "the flags frame lacks utility_id_eia, state, year or "
                                                               "short_form")
    else:
        lo, hi = (int(row_u_window[0]), int(row_u_window[1]))
        try:
            fk = pd.DataFrame({"utility_id_eia": _whole_int64(row_u_flags["utility_id_eia"], "utility_id_eia", "flags"),
                               "state": _state_strings(row_u_flags["state"], "flags"),
                               "year": _whole_int64(row_u_flags["year"], "year", "flags")})
        except ReshapeRefused as e:
            out["row_u_short_form_flags"] = _verdict(None, "", "", str(e))
        else:
            fk["short_form"] = row_u_flags["short_form"].astype("boolean").to_numpy()
            clash = fk.groupby(UNIT_YEAR).short_form.apply(
                lambda x: x.astype(object).where(x.notna(), "NA").nunique() > 1)
            fk = fk.drop_duplicates(UNIT_YEAR)
            o = keys[OUTCOME_FILE]
            ow = o[(o.year >= lo) & (o.year <= hi)]
            m = ow.merge(fk, on=UNIT_YEAR, how="left", indicator=True)
            no_row = (m["_merge"] == "left_only").to_numpy()
            missing = ((m["_merge"] == "both") & m.short_form.isna()).to_numpy()
            by_price = {}
            for col in (rmu.DEFAULT_SERVICE, rmu.DELIVERY_INCLUSIVE):
                if col in outcomes.columns:
                    try:
                        v = _floats(outcomes[col], col, SOURCE_IN_WORDS[OUTCOME_FILE])
                    except ReshapeRefused as e:
                        by_price[col] = {"reason": str(e)}
                        continue
                    has = pd.Series(~np.isnan(v), index=keys[OUTCOME_FILE].index)[ow.index].to_numpy()
                    by_price[col] = {"unit_years_in_window_with_a_price": int(has.sum()),
                                     "of_which_no_flags_row": int((no_row & has).sum()),
                                     "of_which_missing_flag": int((missing & has).sum())}
            bad = no_row | missing
            out["row_u_short_form_flags"] = {
                "window": [lo, hi], "outcome_unit_years_in_window": int(len(ow)),
                "with_no_flags_row": int(no_row.sum()), "with_a_missing_flag": int(missing.sum()),
                "flags_unit_years_whose_rows_disagree": int(clash.sum()),
                "by_row_u_price_column": by_price,
                "examples": sorted({_label(*r) for r in m[bad][UNIT_YEAR].itertuples(index=False)})[:EXAMPLES],
                "note": ("reconciliation_mu._u_drop_short_form stops a step when an outcome unit-year reaching it has no "
                         "flags row or a missing flag, or when flag rows of one unit-year disagree; it reaches only rows "
                         "left after the window, jurisdiction and missing-price rules, so the counts by price column are "
                         "closer to what a step sees. These counts are no claim about whether any unit filed."),
                **_verdict(not bad.any() and not clash.any(),
                           "every outcome unit-year in the window has a True or False flag and no flag rows disagree",
                           "some outcome unit-years in the window have no flags row or a missing flag, or flag rows "
                           "disagree; row U's Short Form step would stop")}
    return out


# ======================================================================================================================
# The decision on the checks' result: what stops a run before any estimator is called (session 28, D-122)
# ======================================================================================================================
#
# The owner's words (Joe, 2026-11-20, D-122), unchanged: "Add a narrow stop before any estimator is called when structural
# key or outcome/quantity coverage inconsistencies, or contradictions between the usable flags and observed prices, make
# execution inconsistent with the frozen inputs. Persist the check report and explain the failure." And: "Do not turn
# expected missingness outside required rows, supplementary loggability counts, or the frozen rows' legitimate
# missing-data rules into blanket failures." And, on coverage: "resolve from construction code whether identical keys are
# required. If so, enforce two-way coverage. Otherwise, block missing rows that could change U/C's samples. Do not assume
# a non-usable flag makes absence harmless. Resolve this before the read."
#
# This is the one named place where that decision is made. execute_outcomes.execute_research asks it after every read of
# the outcomes and before any stage. It changes no check, no frame, no eligibility rule, no transformation and no
# estimate; it reads the checks' own `passed` fields and says which of them stop the run.

COVERAGE_RULE = (
    "Two-way coverage, resolved from the construction code before any read (session 28, by reading and not by running): "
    "pipeline/electricity/panel.py build() returns p[quantity_cols].copy() and p[outcome_cols].copy(), two column "
    "subsets of one frame, so the two files hold the same rows and the same keys one for one; "
    "pipeline/electricity/build_panel.py writes them as returned (q, o = panel.build(...); panel.write(q, o)); and "
    "pipeline/electricity/write_usable_flag.py, which rewrote the quantity file with the usable flag, required at that "
    "write that the outcome file on disk was identical to the outcomes it built and that the outer merge of the two "
    "frames on the keys matched on every row in both directions with equal row counts. Identical keys are therefore "
    "required by construction, and a unit-year in one file and not in the other blocks, whatever its usable flag: a "
    "flag that is not usable does not make an absent row harmless, since rows U and C have sample rules of their own.")

BLOCKING_CHECKS = MappingProxyType({
    "key_types": ("a key column missing or untypable in either file (a repeated unit-year in either file also fails "
                  "this check, because the keys are then not usable as keys)"),
    "duplicate_unit_years_in_outcomes": "a repeated unit-year in the outcome file",
    "coverage": "the outcome file and the quantity panel do not hold the same unit-years (two-way coverage)",
    "usable_without_positive_price": ("a unit-year the usable flag marks usable that has no outcome row, or whose "
                                      "res_price is missing, not finite or not positive"),
})

RECORDED_AND_NOT_BLOCKING = MappingProxyType({
    "kwh_and_bill_not_loggable": ("supplementary loggability counts over every row of the outcome file; the "
                                  "non-computable rule (D-117) is applied by supplementary_outcomes on the rows a "
                                  "design requires, and only there"),
    "row_u_short_form_flags": ("row U's flag coverage, which the row refuses step by step under its own rule "
                               "(reconciliation_mu._u_drop_short_form)"),
})

ALSO_NOT_BLOCKING = (
    "a price that is missing on a unit-year that is not usable, where the row exists (no check counts it as a failure); "
    "key types that differ in width and cast cleanly (key_types records same_dtype_by_column and passes); row C's "
    "price-balanced sample and row U's missing-price rule, which are the rows' own computations; a frame the reshaper "
    "could not build for want of a column, which stops the runs that need it in their own words")

A_CHECK_NOT_MADE_BLOCKS = (
    "The session's reading (session 28), his to strike: a blocking check whose result is not `passed: True` stops the "
    "run, including one that could not be made (passed None) or is absent from the checks, because a run whose "
    "structural checks cannot be made is not shown to be consistent with the frozen inputs. The same holds when the "
    "checks themselves raised, or the reshaper raised: nothing can be handed to an estimator, and the report is written "
    "and not lost.")


def _counts_only(check: dict) -> dict:
    """The whole-number counts of one check's record, and its examples (keys), for the decision's words. No value."""
    out = {}
    for k, v in check.items():
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, np.integer)):
            out[k] = int(v)
    if check.get("examples"):
        out["examples"] = list(check["examples"])
    for k in ("examples_quantity_only", "examples_outcome_only"):
        if check.get(k):
            out[k] = list(check[k])
    return out


def blocking_decision(checked, checks_raised: str | None = None, reshaper_raised: str | None = None) -> dict:
    """Whether the read-time checks stop the run before any estimator, which checks stop it and why, in words.

    checked: what read_time_checks returned. checks_raised, reshaper_raised: the type name of an exception the checks or
    the reshaper raised, when one did (a type name only, since a message could carry a value). Returns a record with
    `blocks` (True or False), `blocking` (one item per blocking finding: the check, the rule, its `passed`, its counts
    and keys, and `why` in words), `recorded_and_not_blocking` (the checks that say they did not pass and do not stop the run;
    the loggability counts are never a pass or a failure and are in the checks' own record),
    and the rules in words. Counts and keys only, never a value of an outcome. Raises nothing."""
    blocking = []
    usable = isinstance(checked, dict)
    if checks_raised:
        blocking.append({"check": "read_time_checks", "rule": "the read-time checks must be computed", "passed": None,
                         "counts": {},
                         "why": (f"the read-time checks raised {checks_raised} and returned nothing, so no structural "
                                 "check was made; the run is stopped before any estimator")})
    elif not usable:
        blocking.append({"check": "read_time_checks", "rule": "the read-time checks must be computed", "passed": None,
                         "counts": {},
                         "why": (f"the read-time checks returned a {type(checked).__name__}, not a record of checks, so "
                                 "no structural check was made; the run is stopped before any estimator")})
    else:
        for name, rule in BLOCKING_CHECKS.items():
            c = checked.get(name)
            passed = c.get("passed") if isinstance(c, dict) else None
            if passed is True:
                continue
            if not isinstance(c, dict):
                why = (f"{name} is absent from the read-time checks, so it was not made ({rule}); a blocking check that "
                       "is not made stops the run")
                counts = {}
            elif passed is False:
                why = f"{name} did not pass ({rule}). The check's own words: {c.get('passes')}"
                counts = _counts_only(c)
            else:
                why = (f"{name} could not be made ({rule}). The check's own words: {c.get('passes')}. A blocking check "
                       "that cannot be made stops the run")
                counts = _counts_only(c)
            blocking.append({"check": name, "rule": rule, "passed": passed, "counts": counts, "why": why})
    if reshaper_raised:
        blocking.append({"check": "reshape", "rule": "the reshaper must return its frames and its report",
                         "passed": None, "counts": {},
                         "why": (f"the reshaper raised {reshaper_raised} and returned nothing, so no outcome frame can be "
                                 "handed to an estimator; the run is stopped before any estimator")})
    recorded = []
    if usable:
        for name, what in RECORDED_AND_NOT_BLOCKING.items():
            c = checked.get(name)
            if isinstance(c, dict) and c.get("passed") is False:
                recorded.append({"check": name, "passed": False, "why_it_does_not_block": what})
    return {
        "what_this_is": ("the decision made before any estimator is called (Joe, 2026-11-20, D-122): whether the "
                         "read-time checks stop the run, which stop it and why. Counts and keys only, no value."),
        "blocks": bool(blocking),
        "blocking": blocking,
        "blocking_checks": dict(BLOCKING_CHECKS),
        "recorded_and_not_blocking": recorded,
        "recorded_and_not_blocking_checks": dict(RECORDED_AND_NOT_BLOCKING),
        "also_not_blocking": ALSO_NOT_BLOCKING,
        "coverage_rule": COVERAGE_RULE,
        "a_check_not_made_blocks": A_CHECK_NOT_MADE_BLOCKS,
        "in_words": ("no blocking integrity check failed; estimation may proceed in the recorded order" if not blocking
                     else "BLOCKED before any estimator: " + " | ".join(b["why"] for b in blocking)),
    }
