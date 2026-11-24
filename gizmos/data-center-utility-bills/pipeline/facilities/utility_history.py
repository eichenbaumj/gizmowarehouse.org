#!/usr/bin/env python3
"""Utility-level histories of data center load, and what each one settles.

A utility's own count of the data center load on its system (a resource plan,
rate case testimony, a load forecast, a grid operator's file) is read against
the same threshold the inventory uses: data center energy as a share of the
utility's 2009 to 2011 retail sales. The rule is docs/DECISIONS.md, D-34,
written before any history was looked for. Load quantities only; no price.

How one figure is read
----------------------
Each row of verified/utility_history.csv is turned into a lower and an upper
bound on the utility's data center energy that year (GWh):

  GWh              as given
  share_of_sales   times the panel's retail sales for that year
  MW, average      times 8.76
  MW, demand       lower bound at a load factor of 0.6 (or the document's own),
                   upper bound at 1.0: the MW running every hour of the year
  MW, connected    no lower bound; upper bound at 1.0. Capacity is not load.

  bound = at_least / at_most   "exceeded 100 MW": only one side is known
  value_error                  reading error of a chart with no printed numbers
  coverage = larger_area       a zone or holding company: no lower bound
  coverage = part              some of the utility's data centers: no upper bound

The year is BELOW the threshold if the upper bound is under it, AT OR ABOVE if
the lower bound reaches it, and decides nothing otherwise.

What a history settles
----------------------
The last year shown below and the first year shown at or above bracket the
first crossing. The candidates are the years after the one and up to the other.
The utility is settled if every candidate puts it in the same group (early host
before 2011, cohort 2011 to 2022, later) and, for a cohort utility, the
candidates span fewer than two years; the crossing is then the last candidate,
the first year the utility's own figure shows it at or above. A figure at or
above before 2011 settles an early host. A figure below in 2022 or later, with
none at or above before it, settles the utility as outside the cohorts.

Run:  python3 -I pipeline/facilities/utility_history.py     (validates the table and prints the readings)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

TABLE = ROOT / "pipeline" / "facilities" / "verified" / "utility_history.csv"
COLUMNS = ["utility_id_eia", "state", "year", "value", "value_error", "bound", "unit", "mw_kind", "load_factor", "coverage",
           "source_url", "source_type", "source_quote", "read_from_chart", "confidence", "checked_on", "note"]
UNITS = {"GWh", "share_of_sales", "MW"}
MW_KINDS = {"average", "demand", "connected"}
BOUNDS = {"exact", "at_least", "at_most"}
COVERAGE = {"utility", "larger_area", "part"}
BLOCKED_DOMAINS = {"baxtel.com", "datacentermap.com", "datacenters.com", "cleanview.co", "datacenterhawk.com"}
LOAD_FACTOR_LOW = 0.6
COHORTS = (2011, 2022)
MOVE_TOLERANCE = 2
KEY = ["utility_id_eia", "state"]


def load(path: Path | None = None) -> pd.DataFrame:
    path = path or TABLE
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    t = pd.read_csv(path, dtype={"state": str, "unit": str, "mw_kind": str, "bound": str, "coverage": str,
                                 "source_url": str, "source_type": str, "source_quote": str, "confidence": str,
                                 "checked_on": str, "note": str})
    return validate(t)


def validate(t: pd.DataFrame) -> pd.DataFrame:
    """Refuse a table the build should not read. Every row needs a source that was opened (D-34)."""
    missing = [c for c in COLUMNS if c not in t.columns]
    if missing:
        raise ValueError(f"utility history table is missing columns: {missing}")
    if not len(t):
        return t[COLUMNS]
    if t[["utility_id_eia", "state", "year", "value"]].isna().any().any():
        raise ValueError("every utility history row needs a utility, a state, a year and a value")
    if not set(t.unit) <= UNITS or not set(t.bound) <= BOUNDS or not set(t.coverage) <= COVERAGE:
        raise ValueError("unknown unit, bound or coverage in the utility history table")
    mw = t.unit == "MW"
    if not set(t.mw_kind[mw]) <= MW_KINDS or t.mw_kind[mw].isna().any():
        raise ValueError("a figure in MW has to say whether it is average load, demand, or connected capacity")
    if (t.load_factor.dropna() <= 0).any() or (t.load_factor.dropna() > 1).any():
        raise ValueError("a load factor is between 0 and 1")
    if (t.value < 0).any() or (t.value_error.fillna(0) < 0).any():
        raise ValueError("values and reading errors cannot be negative")
    chart = t.read_from_chart.astype(str).str.lower().isin(["true", "1"])
    if (chart & t.value_error.isna()).any():
        raise ValueError("a value read from a chart needs its reading error")
    if (chart & (t.confidence != "medium")).any():
        raise ValueError("a value read from a chart is medium confidence")
    dom = t.source_url.map(lambda u: urlparse(u).netloc.replace("www.", "") if isinstance(u, str) else "")
    if (dom == "").any() or dom.isin(BLOCKED_DOMAINS).any() or not t.confidence.isin(["high", "medium"]).all():
        raise ValueError("every utility history row needs a source that is not a directory site, at high or medium confidence")
    if t.source_quote.isna().any() or t.checked_on.isna().any() or t.source_type.isna().any():
        raise ValueError("every utility history row needs a quote, the kind of document, and the date it was opened")
    return t[COLUMNS]


def bounds_gwh(row, sales_gwh: float | None = None) -> tuple[float, float]:
    """(lower, upper) bound on the utility's data center energy in the row's year, in GWh."""
    err = 0.0 if pd.isna(row.value_error) else float(row.value_error)
    v_lo, v_hi = max(float(row.value) - err, 0.0), float(row.value) + err
    if row.unit == "GWh":
        lo, hi = v_lo, v_hi
    elif row.unit == "share_of_sales":
        if sales_gwh is None or not np.isfinite(sales_gwh):
            return 0.0, np.inf                      # no sales figure for that year: the share cannot be turned into energy
        lo, hi = v_lo * sales_gwh, v_hi * sales_gwh
    elif row.mw_kind == "average":
        lo, hi = v_lo * 8.76, v_hi * 8.76
    elif row.mw_kind == "demand":
        if pd.notna(row.load_factor):
            lo, hi = v_lo * row.load_factor * 8.76, v_hi * row.load_factor * 8.76
        else:
            lo, hi = v_lo * LOAD_FACTOR_LOW * 8.76, v_hi * 8.76
    else:                                           # connected, contracted or requested capacity is not load
        lo, hi = 0.0, v_hi * 8.76
    if row.bound == "at_least":
        hi = np.inf
    if row.bound == "at_most":
        lo = 0.0
    if row.coverage == "larger_area":
        lo = 0.0
    if row.coverage == "part":
        hi = np.inf
    return lo, hi


def verdict(lo: float, hi: float, threshold_gwh: float) -> str:
    if hi < threshold_gwh:
        return "below"
    if lo >= threshold_gwh:
        return "at_or_above"
    return "undecided"


def group(year) -> str:
    return "early" if year < COHORTS[0] else ("cohort" if year <= COHORTS[1] else "late")


def settle(verdicts: dict[int, str]) -> dict:
    """What one utility's year-by-year verdicts settle at one threshold.

    Returns {"settled": bool, "group": early / cohort / outside_cohorts / None, "first_crossing": year or None,
             "last_below": year or None, "first_at_or_above": year or None, "why": text}.
    """
    above = sorted(y for y, v in verdicts.items() if v == "at_or_above")
    first_above = above[0] if above else None
    below = sorted(y for y, v in verdicts.items() if v == "below" and (first_above is None or y < first_above))
    last_below = below[-1] if below else None
    out = {"settled": False, "group": None, "first_crossing": None, "last_below": last_below,
           "first_at_or_above": first_above, "why": ""}
    if first_above is None:
        if last_below is not None and last_below >= COHORTS[1]:
            out.update(settled=True, group="outside_cohorts",
                       why=f"below the threshold in {last_below}, and in no earlier year at or above it")
        else:
            out["why"] = "no year is shown at or above the threshold"
        return out
    if first_above < COHORTS[0]:
        out.update(settled=True, group="early", why=f"at or above the threshold in {first_above}, before the cohorts begin")
        return out
    if last_below is None:
        out["why"] = f"at or above in {first_above}, but no earlier year is shown below, so the crossing could be any year up to then"
        return out
    candidates = list(range(last_below + 1, first_above + 1))
    groups = {group(y) for y in candidates}
    if len(groups) > 1:
        out["why"] = f"the crossing is between {candidates[0]} and {candidates[-1]}, which spans {' and '.join(sorted(groups))}"
        return out
    g = groups.pop()
    if g == "cohort" and candidates[-1] - candidates[0] >= MOVE_TOLERANCE:
        out["why"] = (f"a cohort utility, but the crossing is only known to be between {candidates[0]} and {candidates[-1]}, "
                      f"which is {MOVE_TOLERANCE} years or more apart")
        return out
    out.update(settled=True, group="cohort" if g == "cohort" else "outside_cohorts",
               first_crossing=candidates[-1] if g == "cohort" else None,
               why=f"below in {last_below}, at or above in {first_above}")
    return out


def read(t: pd.DataFrame, base_gwh: pd.Series, sales_gwh: pd.Series, thresholds=(0.02, 0.05)) -> dict:
    """Every utility's readings and what they settle, per threshold.

    `base_gwh` is indexed by (utility, state): mean retail sales 2009-2011. `sales_gwh` by (utility, state, year).
    Where a utility has several figures for one year, the year is below only if every one says so, at or above
    only if every one says so, and otherwise decides nothing.
    """
    out = {}
    for (u, st), g in t.groupby(KEY):
        key = f"{int(u)}:{st}"
        if (u, st) not in base_gwh.index or not np.isfinite(base_gwh[(u, st)]):
            out[key] = {"error": "no 2009-2011 sales base for this utility in the panel"}
            continue
        base = float(base_gwh[(u, st)])
        entry = {"base_retail_gwh": round(base, 1), "figures": [], "thresholds": {}}
        rows = []
        for r in g.sort_values("year").itertuples():
            lo, hi = bounds_gwh(r, sales_gwh.get((u, st, int(r.year))))
            rows.append((int(r.year), lo, hi))
            entry["figures"].append({"year": int(r.year), "value": float(r.value), "unit": r.unit,
                                     "mw_kind": None if pd.isna(r.mw_kind) else r.mw_kind, "bound": r.bound,
                                     "coverage": r.coverage, "gwh_lower": round(lo, 1),
                                     "gwh_upper": None if not np.isfinite(hi) else round(hi, 1),
                                     "share_of_base_lower": round(lo / base, 4),
                                     "share_of_base_upper": None if not np.isfinite(hi) else round(hi / base, 4),
                                     "source_url": r.source_url})
        for theta in thresholds:
            thr = theta * base
            by_year: dict[int, set] = {}
            for y, lo, hi in rows:
                by_year.setdefault(y, set()).add(verdict(lo, hi, thr))
            verdicts = {y: (v.pop() if len(v) == 1 else "undecided") for y, v in by_year.items()}
            s = settle(verdicts)
            s["threshold_gwh"] = round(thr, 1)
            s["verdicts"] = {str(y): v for y, v in sorted(verdicts.items())}
            entry["thresholds"][f"{theta:.0%}"] = s
        out[key] = entry
    return out


def settled(report: dict, theta: float) -> dict[tuple[int, str], dict]:
    """{(utility, state): {"group", "first_crossing"}} for the utilities a history settles at this threshold."""
    t = f"{theta:.0%}"
    out = {}
    for key, entry in report.items():
        s = entry.get("thresholds", {}).get(t)
        if s and s["settled"]:
            u, st = key.split(":")
            out[(int(u), st)] = {"group": s["group"], "first_crossing": s["first_crossing"]}
    return out


def panel_inputs() -> tuple[pd.Series, pd.Series]:
    """(2009-2011 sales base by utility-state, retail sales by utility-state-year), both in GWh, from the panel."""
    dose = pd.read_parquet(ROOT / "data" / "interim" / "utility_year_dose.parquet")
    q = pd.read_parquet(ROOT / "data" / "interim" / "panel_quantities.parquet")
    base = dose.drop_duplicates(KEY).set_index(KEY).base_retail_gwh
    missing = q[q.year.isin((2009, 2010, 2011))].groupby(KEY).total_retail_mwh.mean() / 1000.0
    base = base.combine_first(missing)              # a utility the inventory puts no load on still has a base
    sales = q.set_index(KEY + ["year"]).total_retail_mwh / 1000.0
    return base, sales


def main() -> int:
    t = load()
    base, sales = panel_inputs()
    report = read(t, base, sales)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
