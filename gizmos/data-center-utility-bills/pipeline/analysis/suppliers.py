"""Shared suppliers (D-58 rule 2.4): which of a host's matches share its supplier in a year of its window.

The table is `suppliers.csv` beside this file: one row per unit and spell, naming the unit's wholesale supplier and its
kind. A blank `state` means every state of that EIA id. Rule 2.4 removes nothing by default; it defines a reported
exercise that removes every comparison sharing its host's supplier in a year of the host's window, keeps the host's
remaining matches with no rematching, and names each host left with fewer than five matches or with none. This module
holds only the selection that exercise calls. The exercise's run is not built here.

Rule 2.4's text: a comparison "shares the host's supplier" in a year if both bought all or most of their requirements
from the same wholesale supplier (a generation and transmission cooperative, a joint action agency, a federal power
marketing administration, an investor-owned utility's requirements service), or one supplied the other, or both were
parties to one system agreement that allocates generation costs by formula. A unit whose supplier could not be
established is marked unknown and counted.

How this module reads it (each a reading, stated for the owner to strike):
  - Same wholesale supplier: the two units' rows covering the year name the same `supplier`, compared as exact strings
    after trimming spaces. A supplier named two ways (for instance with and without "(through a member G&T)") does not
    match.
  - Own generation (`supplier_kind` own_generation) is never a shared supplier by name: two units that generate for
    themselves do not share a supplier unless one supplied the other.
  - One supplied the other: seen only when the caller says which EIA ids a supplier name stands for (`supplier_ids`); the
    table names suppliers in words, not by id. Without that mapping this route finds nothing.
  - A system agreement that allocates generation costs by formula has no kind in the table and is not detected.
  - A row's assumed years count as covering the year, as in the ownership table.
  - Membership only (owner's ruling, 2026-11-18, Stop 3): "Membership-only rows are treated as sharing a supplier in the
    exercise, labelled as resting on membership." A row whose `note` begins MEMBERSHIP_ONLY counts. A share is
    `documented` if in some window year both units' rows naming that supplier include one that is not membership-only;
    otherwise it is `membership_only`, and such removals are also listed apart by name.
  - Unknown: a unit-year is unknown if no row covers it with a supplier other than "unknown" or blank. A match that shares
    nothing is `unknown` if the host or the match is unknown in any window year; it is never removed, and it is counted.
  - A match with the host's own EIA id is left to rule 2.3 (it is never matched) and is not assessed here.

Reads no price and no revenue.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

PATH = Path(__file__).resolve().parent / "suppliers.csv"
COLUMNS = ("utility_id_eia", "state", "name", "supplier", "supplier_kind", "from_year", "to_year", "from_year_basis",
           "to_year_basis", "source_url", "source_kind", "quote", "date_opened", "note")
KINDS = ("g_and_t_cooperative", "joint_action_agency", "federal_pma", "own_generation", "unknown")   # as the shipped table has them
OWN_GENERATION, UNKNOWN = "own_generation", "unknown"
MEMBERSHIP_MARK = "MEMBERSHIP_ONLY"
DOCUMENTED, MEMBERSHIP_ONLY = "documented", "membership_only"
SAME_SUPPLIER, SUPPLIED_THE_OTHER = "same wholesale supplier", "one supplied the other"


def load(path: Path | str | None = None) -> pd.DataFrame:
    """The supplier table, checked: every column, whole-number ids and years, spells that do not end before they start."""
    path = Path(path or PATH)
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in COLUMNS if c not in t.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns: {missing}")
    t = t[list(COLUMNS)].apply(lambda c: c.str.strip())
    for i, r in t.iterrows():
        try:
            int(r.utility_id_eia)
            lo, hi = int(r.from_year), int(r.to_year)
        except ValueError:
            raise ValueError(f"row {i + 2} of {path.name} has an id or year that is not a whole number") from None
        if lo > hi:
            raise ValueError(f"row {i + 2} of {path.name} has from_year {lo} after to_year {hi}")
    return t.astype({"utility_id_eia": int, "from_year": int, "to_year": int}).reset_index(drop=True)


def membership_only(table: pd.DataFrame) -> pd.Series:
    """True for each row whose note begins MEMBERSHIP_ONLY: the source shows membership, not "all or most" supply."""
    return table.note.astype(str).str.strip().str.startswith(MEMBERSHIP_MARK)


def _covering(table: pd.DataFrame, key: tuple, y: int) -> pd.DataFrame:
    """Rows of unit `key` (its own state, or blank for every state) whose spell covers year y."""
    return table[(table.utility_id_eia == int(key[0])) & ((table.state == key[1]) | (table.state == ""))
                 & (table.from_year <= y) & (table.to_year >= y)]


def _known(rows: pd.DataFrame) -> pd.DataFrame:
    s = rows.supplier.astype(str).str.strip()
    return rows[(s != "") & (s.str.lower() != UNKNOWN) & (rows.supplier_kind != UNKNOWN)]


def _named(rows: pd.DataFrame) -> dict:
    """supplier name -> True if some row naming it is not membership-only (own generation left out)."""
    out: dict = {}
    for name, mem, kind in zip(rows.supplier.str.strip(), membership_only(rows), rows.supplier_kind):
        if kind == OWN_GENERATION:
            continue
        out[name] = out.get(name, False) or not mem
    return out


def shared_with_host(table: pd.DataFrame, host: tuple, window_years: Iterable[int], matches: Iterable[tuple],
                     supplier_ids: dict | None = None) -> dict:
    """The host's matches that share its supplier in a year of `window_years` (D-58 rule 2.4; readings in the docstring).

    Returns {"shares": [{"utility", "key", "tag", "suppliers", "how", "years", "membership_only_years"}],
    "removed_resting_on_membership_only": [the shares tagged membership_only], "unknown": [{"utility", "key",
    "host_unknown_years", "match_unknown_years"}], "not_shared": ["id:ST"], "own_utility_not_assessed": ["id:ST"],
    "host_supplier_unknown_years": [years], "counts": {...}}. Nothing is removed for an unknown supplier.
    """
    years = [int(y) for y in window_years]
    host = (int(host[0]), host[1])
    ids = {str(k).strip(): {int(i) for i in v} for k, v in (supplier_ids or {}).items()}
    host_rows = {y: _known(_covering(table, host, y)) for y in years}
    host_unknown = [y for y in years if not len(host_rows[y])]
    out = {"shares": [], "removed_resting_on_membership_only": [], "unknown": [], "not_shared": [], "own_utility_not_assessed": [],
           "host_supplier_unknown_years": host_unknown}
    n = 0
    for m in matches:
        m = (int(m[0]), m[1])
        label = f"{m[0]}:{m[1]}"
        if m[0] == host[0]:
            out["own_utility_not_assessed"].append(label)
            continue
        n += 1
        names, how, share_years, documented_years = set(), set(), [], []
        match_unknown = []
        for y in years:
            mine = _known(_covering(table, m, y))
            if not len(mine):
                match_unknown.append(y)
            hn, mn = _named(host_rows[y]), _named(mine)
            year_doc, year_share = False, False
            for s in set(hn) & set(mn):
                names.add(s), how.add(SAME_SUPPLIER)
                year_share = True
                year_doc = year_doc or (hn[s] and mn[s])
            for rows, other in ((host_rows[y], m), (mine, host)):        # one supplied the other
                for s, mem in zip(rows.supplier.str.strip(), membership_only(rows)):
                    if other[0] in ids.get(s, set()):
                        names.add(s), how.add(SUPPLIED_THE_OTHER)
                        year_share = True
                        year_doc = year_doc or not mem
            if year_share:
                share_years.append(y)
                if year_doc:
                    documented_years.append(y)
        if share_years:
            entry = {"utility": label, "key": m, "tag": DOCUMENTED if documented_years else MEMBERSHIP_ONLY,
                     "suppliers": sorted(names), "how": sorted(how), "years": share_years,
                     "membership_only_years": [y for y in share_years if y not in documented_years]}
            out["shares"].append(entry)
            if entry["tag"] == MEMBERSHIP_ONLY:
                out["removed_resting_on_membership_only"].append(entry)
        elif host_unknown or match_unknown:
            out["unknown"].append({"utility": label, "key": m, "host_unknown_years": host_unknown, "match_unknown_years": match_unknown})
        else:
            out["not_shared"].append(label)
    out["counts"] = {"matches": n, "removed": len(out["shares"]),
                     "removed_documented": sum(1 for x in out["shares"] if x["tag"] == DOCUMENTED),
                     "removed_resting_on_membership_only": len(out["removed_resting_on_membership_only"]),
                     "unknown": len(out["unknown"]), "not_shared": len(out["not_shared"])}
    return out
