"""Full-window eligibility from the quantities file's usable flag (D-94, "The usable flag's source"; D-95 section 3 item 5).

The owner's words, which govern this module:

    "use the existing quantities-file res_price_usable column for full-window eligibility, for hosts and comparisons
    alike... Read the required columns explicitly. Missing unit-years are unusable; missing or malformed flags and
    duplicate keys stop for correction rather than being silently coerced. Rely on the accepted audit's recorded checks
    without rerunning it or reopening its protected artifacts. Report exclusions and their consequences without price
    or revenue values."

So this module reads five columns of the quantities file, by name, and nothing else: the three keys, the flag and the
first exclusion reason (their names come from pipeline/electricity/availability_codes.py). It never opens the audit's
mask, sidecar or any other file of the audit (D-83's bar on the mask stands; D-94 substitutes this source for the mask
D-58 rule 6.4 named), and it reruns none of the audit's checks. The checks below are structural only: the columns are
there, the keys are whole and unique, the flag is strictly true or false, the reason is from the fixed list and agrees
with the flag. Any failure stops with a worded error giving the problem and how many rows, and never a value of any
other column. No price, no revenue, no ratio is read, printed or returned.

What it returns, `Flags.usable`, is the set of (utility_id_eia, state, year) with a usable outcome, the form
design.build(usable=...) takes. A unit-year with no row in the file is not in the set, so it is unusable.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd
import pyarrow.parquet as pq

from pipeline.electricity import availability_codes as av
from pipeline.electricity import panel

# The panel loader's own path (panel.load_quantities reads this file). Only the five columns below are read from it.
QUANTITIES = panel.INTERIM / "panel_quantities.parquet"
READ_COLUMNS = tuple(av.KEYS) + (av.FLAG_COL, av.REASON_COL)
# The first exclusion reasons the panel build can write: its reasons in order, then "none" for a usable unit-year.
VALID_REASONS = av.BUILD_REASONS + (av.NO_EXCLUSION,)
WINDOW = (6, 3)                     # years before and after first crossing (PREANALYSIS.md; power_simulation.PRE, POST)


class UsableFlagError(ValueError):
    """The quantities file's flag cannot be used as it stands. It is corrected at its source, never coerced here (D-94)."""


@dataclass
class Flags:
    """What the reader returns: the usable unit-years, each row's first exclusion reason, and the row count read."""
    usable: set
    reason: dict = field(repr=False)
    rows: int = 0
    source: str = ""


def _stop(problem: str, n: int, extra: str = "") -> None:
    raise UsableFlagError(f"{n} rows {problem} in the quantities file's usable flag{extra}; stopping for correction (D-94: "
                          "missing or malformed flags and duplicate keys are not coerced)")


def _strict_bool(col: pd.Series) -> pd.Series:
    """True where a value is a real boolean. Integers 0/1, strings and anything else are not."""
    if col.dtype == bool:
        return pd.Series(True, index=col.index)
    return col.map(lambda v: type(v).__name__ in ("bool", "bool_"))


def validate(frame: pd.DataFrame, source: str = "a frame in memory") -> Flags:
    """The structural checks on the five columns, in the order a correction would need them. Stops on the first failure."""
    missing = [c for c in READ_COLUMNS if c not in frame.columns]
    if missing:
        raise UsableFlagError(f"the quantities file is missing required columns {missing} (D-94: the required columns are read "
                              "explicitly); stopping for correction")
    f = frame[list(READ_COLUMNS)]
    keys = list(av.KEYS)
    n = int(f[keys].isna().any(axis=1).sum())
    if n:
        _stop("have no utility_id_eia, state or year", n)
    n = int(f.duplicated(keys, keep=False).sum())
    if n:
        _stop("repeat a key (utility_id_eia, state, year)", n, f", over {int(f.duplicated(keys).sum())} repeated keys")
    flag = f[av.FLAG_COL]
    n = int(flag.isna().sum())
    if n:
        _stop(f"have no {av.FLAG_COL} flag (a missing flag is never read as false)", n)
    n = int((~_strict_bool(flag)).sum())
    if n:
        _stop(f"carry a {av.FLAG_COL} value that is not strictly true or false", n, f" (column dtype {flag.dtype})")
    reason = f[av.REASON_COL]
    n = int(reason.isna().sum())
    if n:
        _stop("have no first exclusion reason", n)
    bad = ~reason.isin(VALID_REASONS)
    if bad.any():
        codes = sorted(map(str, reason[bad].unique()))[:5]
        _stop(f"carry a first exclusion reason not in the fixed list {list(VALID_REASONS)}", int(bad.sum()), f" (codes found: {codes})")
    usable = flag.astype(bool)
    n = int(((reason == av.NO_EXCLUSION) != usable).sum())
    if n:
        _stop(f"have a flag and a first exclusion reason that disagree (usable exactly where the reason is '{av.NO_EXCLUSION}')", n)
    k = list(zip(f.utility_id_eia.astype(int), f.state.astype(str), f.year.astype(int)))
    return Flags(usable={x for x, ok in zip(k, usable) if ok}, reason=dict(zip(k, reason.astype(str))), rows=len(f), source=source)


def read(path: Path | str | None = None) -> Flags:
    """Read the five columns from the quantities file and validate them. Opens that one file and nothing else.

    The file is opened through Python's own `open`, so a test can watch every path this module opens.
    """
    path = Path(path or QUANTITIES)
    with open(path, "rb") as fh:
        names = pq.read_schema(fh).names
        missing = [c for c in READ_COLUMNS if c not in names]
        if missing:
            raise UsableFlagError(f"the quantities file is missing required columns {missing} (D-94: the required columns are "
                                  "read explicitly); stopping for correction")
        fh.seek(0)
        frame = pd.read_parquet(fh, columns=list(READ_COLUMNS))
    return validate(frame, source=str(path))


def window_years(cohort: int) -> range:
    return range(int(cohort) - WINDOW[0], int(cohort) + WINDOW[1] + 1)


def report(flags: Flags, units: Iterable[tuple], role: str = "host") -> dict:
    """Who lacks a full window, with the first exclusion reason for each missing year. Reason codes only.

    units   [((utility_id_eia, state), cohort)]: a unit in one cohort's window (a comparison may appear once per cohort)
    role    "host" or "comparison", which only names the list

    A missing year whose unit-year has no row in the quantities file carries availability_codes.NOT_IN_PANEL, the code
    the accepted audit uses for that case (it is a code from the fixed vocabulary, not a reading of the audit's files).
    """
    lacking, by_reason, checked = [], Counter(), 0
    for key, cohort in units:
        checked += 1
        u, s = int(key[0]), str(key[1])
        miss = [{"year": y, "first_exclusion_reason": flags.reason.get((u, s, y), av.NOT_IN_PANEL)}
                for y in window_years(cohort) if (u, s, y) not in flags.usable]
        if miss:
            lacking.append({"utility": f"{u}:{s}", "cohort": int(cohort), "missing_years": miss})
            by_reason.update(m["first_exclusion_reason"] for m in miss)
    return {f"{role}s_without_a_full_window": lacking, "units_checked": checked, "with_a_full_window": checked - len(lacking),
            "missing_unit_years_by_first_exclusion_reason": dict(by_reason),
            "rule": "a unit is eligible for a window only if usable in all ten years of it, hosts and comparisons alike "
                    "(D-58 rule 6.3; source of the flag: D-94). Reason codes only; no price or revenue is read."}
