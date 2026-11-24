"""Common controlling ownership of panel units, and who may not be compared with whom (D-58, rule 2).

The table is `ownership.csv` beside this file: one row per unit and spell, each with a primary source the
session model has opened (D-58, rule 2.2). A blank `state` means every state of that EIA id. Spells are
inclusive at both ends, and in the year a sale closes the old and the new parent both count (rule 2.1), which
is what two overlapping spells in that year give.

Municipal systems, public power districts and distribution cooperatives with no row are each taken as their
own owner. That is an assumption from EIA's ownership class (rule 2.2). An investor-owned unit with no row
covering a year of an investor-owned host's window cannot be shown to be unaffiliated with that host in that year,
so it is not eligible as a comparison for that host. Rule 2.2 is read year by year (Joe, 2026-11-19, D-107); before
that ruling the bar applied only to a unit with no row covering any year of the window.

Each row also says whether its first and last year are documented by its source or assumed (`from_year_basis`,
`to_year_basis`). The matching exclusions read every row as it stands, documented or assumed.

Hosts with unresolved ownership (the owner's ruling of 2026-11-18, Stop 3; the definition put to him with it). An
investor-owned host's ownership is UNRESOLVED if, for any year of its event window (cohort year g minus 6 through g
plus 3), no row covers that year, or a row covering it is assumed at both ends. Public and cooperative hosts are never
unresolved (rule 2.2: with no row they are their own owners). Such a host stays in the headline with the limitation
stated: its investor-owned matches are not excluded on the table as it stands, which is not the same as being shown
to be unaffiliated. The labelled step F sensitivity (power_simulation.UNRESOLVED_OWNERSHIP_EXCLUDED) drops those hosts
and changes nothing else: no host is rematched to public or cooperative units.

Reads no price and no revenue.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

PATH = Path(__file__).resolve().parent / "ownership.csv"
COLUMNS = ["utility_id_eia", "state", "name", "ultimate_parent", "from_year", "to_year", "how_it_changed",
           "source_url", "source_kind", "quote", "date_opened"]
REQUIRED = ("ultimate_parent", "from_year", "to_year", "source_url", "quote", "date_opened")
BASIS = ("from_year_basis", "to_year_basis")     # kept when the file has them (the shipped table does); see unresolved_ownership_hosts
BASIS_VALUES = ("documented", "assumed")
INVESTOR_OWNED = "investor_owned"
WINDOW_BEFORE, WINDOW_AFTER = 6, 3                # the event window: six years before first crossing to three after (rule 2.3)

OWN_UTILITY = "a unit of the host's own utility (D-54, ruling 2)"
SAME_PARENT = "same ultimate parent as the host in a year of its window (D-58, rule 2.3)"
NO_ROW = ("investor-owned with no row in the ownership table covering a year of the investor-owned host's window, so "
          "it cannot be shown to be unaffiliated with the host in that year (D-58, rule 2.2, read year by year, D-107)")


def load(path: Path | str | None = None) -> pd.DataFrame:
    """The ownership table, checked. Raises ValueError naming the first row that breaks rule 2.2's source standard."""
    t = pd.read_csv(path or PATH, dtype=str, keep_default_na=False)
    missing = [c for c in COLUMNS if c not in t.columns]
    if missing:
        raise ValueError(f"ownership table is missing columns: {missing}")
    basis = [c for c in BASIS if c in t.columns]
    if basis and len(basis) != len(BASIS):
        raise ValueError(f"ownership table has {basis} but not both of {list(BASIS)}")
    t = t[COLUMNS + basis].apply(lambda col: col.str.strip())
    for i, r in t.iterrows():
        where = f"row {i + 2} of the ownership table (utility_id_eia {r.utility_id_eia or '?'}, state {r.state or 'every state'})"
        if not r.utility_id_eia:
            raise ValueError(f"{where} has no utility_id_eia")
        blank = [c for c in REQUIRED if not r[c]]
        if blank:
            raise ValueError(f"{where} has no {', '.join(blank)}")
        bad = [c for c in basis if r[c] not in BASIS_VALUES]
        if bad:
            raise ValueError(f"{where} has a {', '.join(bad)} that is not one of {list(BASIS_VALUES)}")
        try:
            lo, hi = int(r.from_year), int(r.to_year)
        except ValueError:
            raise ValueError(f"{where} has a year that is not a whole number") from None
        if lo > hi:
            raise ValueError(f"{where} has from_year {lo} after to_year {hi}")
    t["utility_id_eia"] = t.utility_id_eia.astype(int)
    t["from_year"] = t.from_year.astype(int)
    t["to_year"] = t.to_year.astype(int)
    return t.reset_index(drop=True)


def _rows(table: pd.DataFrame, key: tuple, years: Iterable[int]) -> pd.DataFrame:
    """Rows of the unit `key` (its own state, or blank for every state) whose spell covers any of `years`."""
    years = [int(y) for y in years]
    if table is None or not len(table) or not years:
        return table.iloc[0:0] if table is not None else pd.DataFrame(columns=COLUMNS)
    mine = table[(table.utility_id_eia == int(key[0])) & ((table.state == key[1]) | (table.state == ""))]
    if not len(mine):
        return mine
    cover = pd.Series(False, index=mine.index)
    for y in years:
        cover |= (mine.from_year <= y) & (mine.to_year >= y)
    return mine[cover]


def parents(table: pd.DataFrame, key: tuple, years: Iterable[int]) -> set[str]:
    """The ultimate parents of unit `key` = (utility_id_eia, state) in any of `years`."""
    return set(_rows(table, key, years).ultimate_parent)


def affiliated(table: pd.DataFrame, a: tuple, b: tuple, years: Iterable[int]) -> bool:
    """True if a and b share an EIA id (in every year, table or no table) or an ultimate parent in one same year of `years`."""
    if int(a[0]) == int(b[0]):
        return True
    return any(parents(table, a, [y]) & parents(table, b, [y]) for y in years)


def ineligible_for(table: pd.DataFrame, host_key: tuple, window_years: Iterable[int], candidates: Iterable[tuple],
                   ownership_of: dict, affiliates_included: bool = False) -> dict:
    """The candidates that may not be matched to the host, each with its reason (D-54, ruling 2; D-58, rules 2.2 and 2.3).

    A unit of the host's own utility (the same EIA id) is out in every run. With `affiliates_included` (the
    sensitivity of rule 2.3) the other two reasons are not applied. The fail-closed reason applies only when the
    host and the candidate are both investor-owned and some year of the window has no row covering the candidate
    (rule 2.2 read year by year, D-107).
    `ownership_of` maps a unit to "investor_owned", "public" or "cooperative"; a unit it lacks raises, since the
    fail-closed rule cannot be decided without it.
    """
    window_years = [int(y) for y in window_years]
    host_key = (int(host_key[0]), host_key[1])
    out: dict = {}
    host_parents = {y: parents(table, host_key, [y]) for y in window_years} if not affiliates_included else {}
    host_iou = None
    for c in candidates:
        c = (int(c[0]), c[1])
        if c[0] == host_key[0]:
            out[c] = OWN_UTILITY
            continue
        if affiliates_included:
            continue
        if any(host_parents[y] & parents(table, c, [y]) for y in window_years):
            out[c] = SAME_PARENT
            continue
        if host_iou is None:
            host_iou = _ownership(ownership_of, host_key) == INVESTOR_OWNED
        if host_iou and _ownership(ownership_of, c) == INVESTOR_OWNED and any(not len(_rows(table, c, [y])) for y in window_years):
            out[c] = NO_ROW
    return out


def _ownership(ownership_of: dict, key: tuple) -> str:
    v = None if ownership_of is None else ownership_of.get(key)
    if not isinstance(v, str) or not v:
        raise ValueError(f"no ownership class for {key[0]}:{key[1]}; rule 2.2's fail-closed test needs one")
    return v


def company_of(table: pd.DataFrame, key: tuple, years: Iterable[int]) -> str:
    """The unit's company for leave-one-company-out (D-58, rule 7): its ultimate parent over `years`.

    Several parents in those years are joined, sorted, with " / ". A unit with no parent is its own company.
    """
    p = parents(table, key, years)
    return " / ".join(sorted(p)) if p else f"{int(key[0])}:{key[1]}"


# ---- hosts with unresolved ownership (owner's ruling, 2026-11-18, Stop 3) ----------------------------------------------

UNRESOLVED_NO_ROW = "no row of the ownership table covers this year"
UNRESOLVED_ASSUMED = "a row covering this year is assumed at both ends (from_year_basis and to_year_basis)"
UNRESOLVED_NO_BASIS = "the table carries no from_year_basis and to_year_basis, so no covering row can be shown to be documented"
UNRESOLVED_EXCLUDED = ("ownership unresolved in a year of its window, excluded by the labelled sensitivity "
                       "sensitivity_hosts_with_unresolved_ownership_excluded (owner's ruling, 2026-11-18)")
UNRESOLVED_LIMITATION = ("Investor-owned hosts whose ownership is unresolved in a year of their window: no row of the ownership "
                         "table covers the year, or a row covering it is assumed at both ends. In this run they are {fate}. Their "
                         "investor-owned matches are not shown to be unaffiliated with them: they are only not excluded on the "
                         "table as it stands. They are never rematched to public or cooperative units. The labelled sensitivity "
                         "sensitivity_hosts_with_unresolved_ownership_excluded drops them and changes nothing else.")


def window_years(cohort: int) -> list[int]:
    """The years of a host's event window: cohort year minus six through plus three."""
    return list(range(int(cohort) - WINDOW_BEFORE, int(cohort) + WINDOW_AFTER + 1))


def unresolved_ownership_hosts(table: pd.DataFrame, hosts_with_cohorts, ownership_of: dict) -> dict:
    """The hosts whose ownership is unresolved, each with the years and the reason (owner's ruling, 2026-11-18, Stop 3).

    `hosts_with_cohorts` is [((utility_id_eia, state), cohort)]. A host is unresolved if it is investor-owned and, for any
    year of its window (window_years), no row covers the year (a row of its own state, or a blank state for every state
    of its id), or a row covering it has both from_year_basis and to_year_basis "assumed". Where two rows cover a year (the
    year a sale closes, rule 2.1), one row assumed at both ends is enough: that parent's presence in the year is assumed.
    Public and cooperative hosts are never unresolved. A host whose ownership class is missing raises, as in
    ineligible_for; so does a covering row whose basis is not one of BASIS_VALUES. A table with no basis columns at all (an
    invented table; the shipped one has them) cannot show any row documented, so every covered year is unresolved for want
    of a basis (UNRESOLVED_NO_BASIS).

    Returns {(utility_id_eia, state): {"utility", "cohort", "years", "reason_by_year", "reason"}} for the unresolved
    hosts only. A host listed twice raises: one host, one window.
    """
    out: dict = {}
    seen: set = set()
    for key, g in hosts_with_cohorts:
        key, g = (int(key[0]), key[1]), int(g)
        if key in seen:
            raise ValueError(f"host {key[0]}:{key[1]} is listed twice; one host has one window")
        seen.add(key)
        if _ownership(ownership_of, key) != INVESTOR_OWNED:
            continue
        why: dict = {}
        for y in window_years(g):
            cover = _rows(table, key, [y])
            if not len(cover):
                why[y] = UNRESOLVED_NO_ROW
                continue
            if any(c not in cover.columns for c in BASIS):
                why[y] = UNRESOLVED_NO_BASIS
                continue
            vals = set(cover.from_year_basis) | set(cover.to_year_basis)
            if vals - set(BASIS_VALUES):
                raise ValueError(f"a row covering {key[0]}:{key[1]} in {y} has a basis that is not one of {list(BASIS_VALUES)}")
            if ((cover.from_year_basis == "assumed") & (cover.to_year_basis == "assumed")).any():
                why[y] = UNRESOLVED_ASSUMED
        if why:
            kinds = sorted(set(why.values()), key=[UNRESOLVED_NO_ROW, UNRESOLVED_ASSUMED, UNRESOLVED_NO_BASIS].index)
            out[key] = {"utility": f"{key[0]}:{key[1]}", "cohort": g, "years": sorted(why), "reason_by_year": why,
                        "reason": "; ".join(f"{k}: {', '.join(str(y) for y in sorted(why) if why[y] == k)}" for k in kinds)}
    return out

