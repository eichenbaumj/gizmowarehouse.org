"""Market region: the wholesale market a utility buys in, by utility and state.

Read from the balancing authority code each utility reports to EIA for each
state it serves (docs/DECISIONS.md, D-22, confirmed in D-25; made
utility-by-state in D-27). Two limits travel with every use:

  * EIA-861 carries a balancing authority code from 2013 on. Before 2013 the
    column is "UNK" for every row, so a market move before 2013 cannot be read
    from this source.
  * In 2013 many Southwest Power Pool members still reported the code of their
    own pre-consolidation balancing area (Westar, Nebraska Public Power, Grand
    River Dam and others). Those codes are read as SPP. The Western Area Power
    Administration's Upper Great Plains East area (WAUE) is also read as SPP,
    the market it joined in October 2015; that date is general knowledge, not a
    page opened for this project.

A change of code is not always a change of market: several are corrections of
what a utility reported. `changes()` lists every unit whose reported region is
not the same in all years, so they can be counted and, if needed, looked up.

Year by year (Joe, D-30; built in D-37)
---------------------------------------
`by_unit_year()` gives every utility-state a region in every year:

  * from 2013, the region of the code it reports that year (carried forward
    over years it does not report, and back to 2005 from its first report);
  * except that the dated moves in market_moves.csv govern the utilities they
    place. Each move has a first year in the new region: the year itself if
    the move took effect on or before 1 July, otherwise the next year. Before
    that year the utility is in the move's old region.

Three of the moves are out of markets altogether or into one from none. The
utilities of Nebraska, of MidAmerican's 2009 group and of the Upper Great
Plains were in no market before they joined one; they are grouped as "Upper
Midwest, no market" for those years. Kentucky's and the lower Mississippi's
joiners were in the Southeast group before.

Which small utilities moved with a balancing area is inference where EIA has
no code for it; market_moves.csv says how each move's utilities are placed,
and pjm_late_zones.csv lists the Ohio and Pennsylvania systems the territory
map puts in the two zones that left MISO for PJM.
"""
from __future__ import annotations

import pandas as pd

from pathlib import Path

KEY = ["utility_id_eia", "state"]
FIRST_YEAR_REPORTED = 2013
HERE = Path(__file__).resolve().parent
MOVES = HERE / "market_moves.csv"
ZONES = HERE / "pjm_late_zones.csv"
UPPER_MIDWEST = "Upper Midwest, no market"
YEARS = tuple(range(2001, 2026))
# Utilities a source names, by EIA id: MidAmerican Energy; Muscatine's Board of Water, Electric and Communications; Cedar Falls.
MIDAMERICAN_GROUP = {12341, 13143, 3203}
VALLEY_ELECTRIC = {19840}
# Moves where the code EIA reports afterwards does not show the move. Valley Electric still reports Nevada Power's
# code; the FERC order in market_moves.csv puts it in the California ISO's balancing area from 3 January 2013.
OVERRIDES_REPORTED = {"valley"}

REGION_OF_BA = {
    "PJM": "PJM", "OVEC": "PJM",
    "MISO": "MISO", "EEI": "MISO",
    "SWPP": "SPP", "SPA": "SPP",
    # balancing areas that were folded into the Southwest Power Pool's own area in 2014, as reported for 2013
    **dict.fromkeys(["WR", "NPPD", "OPPD", "LES", "WFEC", "SPS", "CSWS", "GRDA", "SECI", "KCPL", "EDE", "OKGE",
                     "MPS", "KACY", "INDN", "SPRM", "WAUE"], "SPP"),
    "ERCO": "ERCOT", "NYIS": "NYISO",
    "ISNE": "ISO-NE", "NBSO": "ISO-NE",
    **dict.fromkeys(["CISO", "BANC", "LDWP", "IID", "TIDC", "TID"], "California"),
    **dict.fromkeys(["TVA", "SOCO", "DUK", "CPLE", "CPLW", "SC", "SCEG", "LGEE", "AECI", "FMPP", "SEC", "FPC", "FPL",
                     "TEC", "JEA", "TAL", "GVL", "HST", "AEC", "SEPA", "NSB"], "Southeast"),
    **dict.fromkeys(["BPAT", "WACM", "PACE", "PACW", "WALC", "PSCO", "PNM", "NWMT", "NEVP", "SPPC", "AVA", "WAUW",
                     "EPE", "TEPC", "AZPS", "PSEI", "IPCO", "PGE", "DOPD", "CHPD", "GCPD", "SRP", "SCL", "TPWR"], "West"),
    **dict.fromkeys(["HECO", "CEA", "AMPL"], "Alaska and Hawaii"),
}


def by_year(q: pd.DataFrame) -> pd.DataFrame:
    """Region as reported, one row per utility-state-year that carries a known code."""
    r = q[KEY + ["year", "balancing_authority"]].copy()
    r["region"] = r.balancing_authority.map(REGION_OF_BA)
    return r.dropna(subset=["region"])[KEY + ["year", "region"]]


def fixed(q: pd.DataFrame) -> pd.Series:
    """One region per utility-state: the one it most recently reports.

    A utility-state with no known code in any year takes its state's most common region.
    """
    units = q[KEY].drop_duplicates()
    last = by_year(q).sort_values("year").groupby(KEY).region.last()
    u = units.join(last, on=KEY)
    by_state = u.dropna(subset=["region"]).groupby("state").region.agg(lambda x: x.value_counts().index[0])
    u["region"] = u.region.fillna(u.state.map(by_state))
    return u.set_index(KEY).region


def changes(q: pd.DataFrame) -> pd.DataFrame:
    """Utility-states whose reported region is not the same in every year, with the year of each change."""
    r = by_year(q).sort_values(KEY + ["year"])
    r["prev"] = r.groupby(KEY).region.shift()
    moved = r[r.prev.notna() & (r.prev != r.region)]
    out = (moved.assign(step=moved.prev + " to " + moved.region + " in " + moved.year.astype(str))
           .groupby(KEY).agg(first_change_year=("year", "min"), last_change_year=("year", "max"),
                             path=("step", "; ".join)).reset_index())
    return out


# ---- year by year ------------------------------------------------------------------------------

def load_moves(path: Path | None = None) -> pd.DataFrame:
    """The sourced table of market entries and exits. Every row needs a source that was opened."""
    m = pd.read_csv(path or MOVES, dtype=str).fillna("")
    need = ["move_id", "from_region", "to_region", "effective_date", "first_year_in_new_region", "source_url", "source_quote",
            "confidence", "checked_on"]
    missing = [c for c in need if c not in m.columns]
    if missing:
        raise ValueError(f"market moves table is missing columns: {missing}")
    if (m.source_url == "").any() or (m.source_quote == "").any() or (m.checked_on == "").any():
        raise ValueError("every market move needs a source, a quote and the date it was opened")
    if not m.confidence.isin(["high", "medium"]).all() or m.move_id.duplicated().any():
        raise ValueError("market moves are high or medium confidence, one row per move")
    for r in m.itertuples():                 # the first year in the new region follows from the date: on or before 1 July, that year
        if r.first_year_in_new_region and r.from_region not in ("", "none"):
            y, mm, dd = (int(x) for x in r.effective_date.split("-"))
            if int(r.first_year_in_new_region) != (y if (mm, dd) <= (7, 1) else y + 1):
                raise ValueError(f"{r.move_id}: first year in the new region does not follow from {r.effective_date}")
    return m


def move_groups(q: pd.DataFrame, zones: pd.DataFrame | None = None) -> pd.Series:
    """Which dated move, if any, each utility-state belongs to. Index KEY, value move_id.

    The rules are the ones market_moves.csv states in `units_placed_by`. `zones` is
    pjm_late_zones.csv (market_zones.py); Kentucky cooperatives are East Kentucky's
    members and are never placed by the map.
    """
    if zones is None:
        zones = pd.read_csv(ZONES) if ZONES.exists() else pd.DataFrame(columns=KEY + ["zone", "ownership"])
    codes = q[q.balancing_authority.notna() & (q.balancing_authority != "UNK")]
    ever = codes.groupby(KEY).balancing_authority.agg(set)
    own = q.groupby(KEY).ownership.last()
    early = codes[codes.year.isin((2013, 2014))].groupby(KEY).balancing_authority.agg(set)
    out = {}
    for k, c in ever.items():
        u, st = k
        if "LGEE" in c:
            out[k] = "lgee"
        elif c & {"NPPD", "OPPD", "LES"}:
            out[k] = "nebraska"
        elif "WAUE" in c:
            out[k] = "ugp"
        elif st == "KY" and "MISO" in c:
            out[k] = "big_rivers"
        elif st == "KY" and "PJM" in c and own.get(k) == "cooperative":
            out[k] = "ekpc"
        elif st in ("AR", "LA", "MS", "TX") and "MISO" in early.get(k, set()):
            out[k] = "miso_south"
    for k in q[KEY].drop_duplicates().itertuples(index=False):
        k = tuple(k)
        if k[0] in MIDAMERICAN_GROUP and k[1] in ("IA", "IL", "SD", "NE"):
            out[k] = "midamerican"
        if k[0] in VALLEY_ELECTRIC:
            out[k] = "valley"
    for r in zones.itertuples():
        k = (int(r.utility_id_eia), r.state)
        if r.zone in ("ATSI", "DEOK") and out.get(k) is None and not (r.state == "KY" and r.ownership == "cooperative"):
            out[k] = r.zone.lower()
    return pd.Series(out, dtype=object)


def by_unit_year(q: pd.DataFrame, years=YEARS, moves: pd.DataFrame | None = None, zones: pd.DataFrame | None = None) -> pd.DataFrame:
    """Region of every utility-state in every year: KEY + year + region + basis.

    basis is "reported" (the code EIA has for that year), "carried" (the nearest year with a code:
    forward, or back from the first report), "move" (a dated move's old or new region) or
    "state" (no code in any year: the state's most common region that year).
    """
    moves = load_moves() if moves is None else moves
    years = list(years)
    units = q[KEY].drop_duplicates()
    grid = units.merge(pd.DataFrame({"year": years}), how="cross")
    rep = by_year(q)
    # A code that names a balancing area a dated move covers is settled by the move, not by this map.
    g = grid.merge(rep, on=KEY + ["year"], how="left").sort_values(KEY + ["year"])
    g["basis"] = g.region.notna().map({True: "reported", False: None})
    filled = g.groupby(KEY).region.transform(lambda x: x.ffill().bfill())
    g.loc[g.region.isna() & filled.notna(), "basis"] = "carried"
    g["region"] = filled
    grp = move_groups(q, zones)
    sched = {r.move_id: (int(r.first_year_in_new_region), r.from_region, r.to_region)
             for r in moves.itertuples() if r.first_year_in_new_region and r.from_region not in ("", "none")}
    mv = pd.Series([grp.get(k) for k in zip(g.utility_id_eia, g.state)], index=g.index)
    for mid, (first, before, after) in sched.items():
        m = (mv == mid).values
        if not m.any():
            continue
        old = m & (g.year < first).values
        g.loc[old, ["region", "basis"]] = [before, "move"]
        # after the move the reported region stands where there is one; a carried or missing one takes the move's
        keep_reported = (g.basis == "reported").values & (mid not in OVERRIDES_REPORTED)
        new = m & (g.year >= first).values & ~keep_reported
        g.loc[new, ["region", "basis"]] = [after, "move"]
    by_state = (g.dropna(subset=["region"]).groupby(["state", "year"]).region.agg(lambda x: x.value_counts().index[0])
                .rename("state_region").reset_index())
    g = g.merge(by_state, on=["state", "year"], how="left")
    none = g.region.isna()
    g.loc[none, "region"] = g.loc[none, "state_region"]
    g.loc[none, "basis"] = "state"
    return g[KEY + ["year", "region", "basis"]].reset_index(drop=True)


def movers(regions: pd.DataFrame, first: int = 2005, last: int = 2025) -> pd.DataFrame:
    """Utility-states whose region is not the same in every year from `first` to `last`, with the path."""
    r = regions[regions.year.between(first, last)].sort_values(KEY + ["year"])
    r = r.assign(prev=r.groupby(KEY).region.shift())
    ch = r[r.prev.notna() & (r.prev != r.region)]
    return (ch.assign(step=ch.prev + " to " + ch.region + " in " + ch.year.astype(str))
            .groupby(KEY).agg(first_change_year=("year", "min"), n_changes=("year", "size"), path=("step", "; ".join)).reset_index())
