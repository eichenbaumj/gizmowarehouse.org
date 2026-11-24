"""Utility successions: which EIA ids are one retail territory over time.

EIA-861 gives a utility a new id, or folds one utility into another, when
companies merge or a territory is sold. Left alone, the successor's sales jump
and the predecessor's series stops, which breaks two things: the price series
of the territory, and the 2009-2011 sales base that data center load is
divided by (docs/DECISIONS.md, D-21).

The fix is one hand-collected table, `succession.csv`, one row per predecessor
utility in one state:

  action = sum         the predecessor's whole retail territory in that state
                       went to one successor. Its rows are added into the
                       successor's for EVERY year, so the unit is the combined
                       territory throughout. Needs a source that was opened,
                       at high or medium confidence.
  action = not_linked  a break we looked at and deliberately left alone: the
                       territory was split among several buyers, the successor
                       is outside the panel, or the series simply stops being
                       published. The reason is in `note`.

What summing does to the price: before the merger, the combined unit's
residential price is the sales-weighted blend of tariffs that were set
separately. `n_ids_reporting` in the quantities frame says how many ids were
added together in each unit-year, so the analysis can find those years.

Chains are followed: Union Electric's Illinois territory went to Central
Illinois Public Service in 2005, which became Ameren Illinois in 2010, so all
of it lands on Ameren Illinois.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

TABLE = Path(__file__).resolve().parent / "succession.csv"
ACTIONS = {"sum", "not_linked"}
USABLE_CONFIDENCE = {"high", "medium"}
COLUMNS = [
    "predecessor_id", "state", "predecessor_name", "action", "successor_id", "successor_name",
    "effective_date", "source_url", "source_type", "source_quote", "confidence", "checked_on", "note",
]

Mapping = dict[tuple[int, str], int]


def load(path: Path | None = None) -> pd.DataFrame:
    """Read and validate the succession table. Raises on anything unusable."""
    t = pd.read_csv(path or TABLE, dtype={"predecessor_id": "Int64", "successor_id": "Int64"}, keep_default_na=False,
                    na_values=[""])
    validate(t)
    return t


def validate(t: pd.DataFrame) -> None:
    missing = [c for c in COLUMNS if c not in t]
    if missing:
        raise ValueError(f"succession table is missing columns: {missing}")
    if t.predecessor_id.isna().any() or t.state.isna().any():
        raise ValueError("every row needs a predecessor id and a state")
    bad = sorted(set(t.action) - ACTIONS)
    if bad:
        raise ValueError(f"unknown action(s): {bad}")
    dup = t[t.duplicated(["predecessor_id", "state"], keep=False)]
    if len(dup):
        raise ValueError(f"a predecessor can have one fate per state: {sorted(set(zip(dup.predecessor_id, dup.state)))}")
    s = t[t.action == "sum"]
    if s.successor_id.isna().any():
        raise ValueError("a summed row needs a successor id")
    if (s.predecessor_id == s.successor_id).any():
        raise ValueError("a utility cannot succeed itself")
    unsourced = s[s.source_url.isna() | ~s.confidence.isin(USABLE_CONFIDENCE)]
    if len(unsourced):
        raise ValueError("summed rows need a source URL and high or medium confidence: "
                         f"{sorted(zip(unsourced.predecessor_id, unsourced.state))}")
    unexplained = t[(t.action == "not_linked") & t.note.isna()]
    if len(unexplained):
        raise ValueError(f"a row left unlinked needs its reason in `note`: {sorted(unexplained.predecessor_id)}")
    resolve(t)  # raises on a cycle


def resolve(t: pd.DataFrame) -> Mapping:
    """{(predecessor id, state): final successor id}, with chains followed to the end."""
    s = t[t.action == "sum"]
    step = {(int(p), st): int(n) for p, st, n in zip(s.predecessor_id, s.state, s.successor_id)}
    out: Mapping = {}
    for (p, st) in step:
        seen, cur = {p}, step[(p, st)]
        while (cur, st) in step:
            if cur in seen:
                raise ValueError(f"succession table has a cycle through utility {cur} in {st}")
            seen.add(cur)
            cur = step[(cur, st)]
        out[(p, st)] = cur
    return out


def final_id(utility_id, state, mapping: Mapping):
    """The unit a reported id belongs to in a state (itself, unless it was absorbed)."""
    if pd.isna(utility_id):
        return utility_id
    return mapping.get((int(utility_id), state), int(utility_id))


def apply_ids(df: pd.DataFrame, mapping: Mapping, id_col: str = "utility_id_eia", state_col: str = "state") -> pd.Series:
    """Unit ids for a frame of reported ids. Rows with no id stay missing."""
    if not mapping:
        return df[id_col]
    m = pd.Series(mapping)
    m.index = pd.MultiIndex.from_tuples(m.index, names=[id_col, state_col])
    key = pd.MultiIndex.from_arrays([df[id_col].astype("Int64"), df[state_col]])
    mapped = pd.Series(m.reindex(key).values, index=df.index)
    return mapped.where(mapped.notna(), df[id_col]).astype(df[id_col].dtype)
