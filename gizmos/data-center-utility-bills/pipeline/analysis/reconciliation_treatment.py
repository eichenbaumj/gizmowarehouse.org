#!/usr/bin/env python3
"""Treatment and assignment rules for the reconciliation rows (PREANALYSIS.md, "The reconciliation rows (reported
first, whatever they show)"), as pure functions over tables passed in as arguments.

Reads NO price and opens NO file. Every input is an argument. Written 2026-11-19 (session 19) for rows M and U; row C
may use the same tables. Changed in session 22 for Joe's ruling of 2026-11-19 (D-109): row U's polygon rule is the
smallest containing polygon over every polygon (ROW_U_POLYGON), the four entity types are listed (entity_type_list),
and the coincidence with row C's rule and the missing-coverage qualification are carried as constants.

Shared table shapes
-------------------
sites        one row per inventory site: fid, state, energized_year, mw_full, is_crypto (and mw_full_raw where a
             caller asks for it). data/interim/facilities.parquet has these columns. Cryptocurrency mines are not
             data centers (PREANALYSIS.md, Treatment; D-11, D-12) and every builder here leaves them out.
assignment   one row per (site, unit) under one named rule: fid, utility_id_eia, state, rule. A site may have
             several rows (county_touch) or one. A site with no row is listed in the rule's `unassigned` table with
             the reason in words, never dropped silently.
units        the panel units, one row per (utility_id_eia, state).

Assignment rules
----------------
county_touch       every utility whose EIA-861 service territory includes the site's county, in the site's state
                   (Meeks et al., Sec. 4.2, p. 18 and fn. 17, the file dated 2026-10-23; docs/gate1/
                   bounded-read-row-m-2026-11-19.md). Needs the EIA-861 service-territory table (county by
                   utility and state). That table is data/raw/pudl/core_eia861__yearly_service_territory.parquet
                   (data/frozen/fetch_manifest_eia861.json), which this agent was not allowed to read, so it is an
                   ARGUMENT. It also needs each site's county: facilities.parquet's county_name is missing for 1,046
                   of 2,244 rows (read 2026-11-19), so the site-to-county table is an argument too.
polygon_smallest   the territory polygon that strictly contains the site, chosen by area, under one of two priorities
                   (assign_polygon_smallest). Row U (Ryu and Hiatt, p. 5, Sec. 2.1) states the HIFLD electric retail
                   service territory layer and, where polygons overlap, "the utility whose polygon strictly contains the
                   facility's location, prioritizing retail providers over wholesale-only territories". This layer's
                   TYPE field does not establish which polygons are retail (none of its ten values names retail or
                   wholesale-only service), so row U does NOT apply that priority: by Joe's ruling of 2026-11-19 (D-109)
                   U0 takes the smallest polygon that contains the site over every polygon of the layer, the type not
                   read, as our labelled approximation (ROW_U_POLYGON, ROW_U_POLYGON_LABEL). Row C (Scalera, Bosetti
                   and Pecci, section 2.1 p. 4 and S1.1 p. 25): overlaps are given "to the smallest polygon" over every
                   territory in the layer, with no priority by type (ROW_C_POLYGON; that the type plays no part is our
                   reading of those passages, which speak of "all utility service territories" and name no type,
                   adopted by Joe on 2026-11-19, D-111). The two rows therefore apply ONE rule: agreement between U0 and C0 to C2 on the assignment is
                   that rule applied twice and is not independent validation (ROW_U_C_COINCIDENCE).
                   The incidence table (fid, polygon id, area, and type_class where the retail-first priority is asked
                   for) is an ARGUMENT, built by reconciliation_inputs from data/raw/territories/
                   retail_service_territories.geojson; nothing here reads the layer. The retail-first priority stays
                   available ("retail_first") and is no row's specification since D-109: under it an ambiguous polygon
                   is never classed by a guess, and a site whose unit would turn on that class is listed, not assigned.
                   entity_type_list() lists, for row U, the sites associated with four of the layer's entity types;
                   the list decides no assignment.
verified           the inventory's own assignment, facilities.utility_id_eia with the site's state. Only part of it is
                   verified by hand (utility_assign == "verified_by_hand", 181 rows of facilities.parquet on 2026-11-19,
                   159 of them data centers, and the three off-panel verified kinds); the rest is placed by the
                   inventory's map rules. The plan's steps U1 and C3 called it "the hand-verified serving utility" and
                   M1 "the one utility that serves the site"; R8, adopted by Joe on 2026-11-19 (D-107), names it "the
                   inventory's own assignment" with the count of hand-verified sites beside it.

Reported ids are mapped to panel units through a table like data/interim/panel_reported_ids.parquet
(utility_id_reported, state -> utility_id_eia). A reported id that is not a panel unit in the site's state is listed.

Treatment builders
------------------
first_year_above_size()   first year a data center above a size enters (row M, steps M0 to M3). How sites are
                          counted toward "above 5 MW" is an explicit argument with no default (see its docstring).
first_year_at_dose()      first year the unit's load share reaches a threshold (step M4; `dose` in
                          utility_year_dose.parquet).
cumulative_mw()           cumulative operating MW by unit and year, a multi-state utility's total entered in each
                          of its states (row U). How "operating" is dated is an explicit argument with no default.

Readings that are the agent's and not the plan's are marked "the agent's reading".
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

KEY = ["utility_id_eia", "state"]
RULES = ("county_touch", "polygon_smallest", "verified")
VERIFIED_BY_HAND_KINDS = ("verified_by_hand", "ercot_wires_outside_panel", "behind_the_meter", "wholesale_direct")
TERRITORY_VINTAGES = ("union_of_all_years", "year_of_entry")      # or an int year; see assign_county_touch
SIZE_COUNTING = ("site", "county_year_new_capacity")
MW_SOURCES = ("site_year_load", "full_size_from_energized_year")
WHOLESALE_ONLY_RULES = ("smallest_wholesale_only", "unassigned")
TYPE_CLASSES = ("retail", "wholesale_only", "ambiguous")     # the incidence table's type_class (D-107, access 2)
POLYGON_PRIORITIES = ("retail_first", "none")
# Row U's polygon rule (Joe, 2026-11-19, D-109): the smallest polygon that strictly contains the site, over every
# polygon of the layer, the type not read. OURS, not the paper's: a labelled approximation. The paper gives retail
# providers priority over wholesale-only territories (Ryu and Hiatt p. 5, Sec. 2.1); this layer's TYPE field does not
# establish which polygons are retail, so the priority is not applied. Rule name "polygon_smallest_any_type", the same
# rule as row C's (ROW_U_C_COINCIDENCE). Until D-109 row U's rule was retail first (D-107), which placed no site on
# this layer because every polygon is classed ambiguous.
ROW_U_POLYGON = {"priority": "none", "wholesale_only_sites": None}
ROW_U_POLYGON_LABEL = (
    "Our smallest-polygon approximation, not the paper's assignment. Each site goes to the smallest territory polygon "
    "that strictly contains it, over every polygon of the layer, the polygon's type not read (ours, a labelled "
    "approximation adopted by Joe on 2026-11-19, D-109). The paper gives priority to retail providers over "
    "wholesale-only territories (Ryu and Hiatt p. 5, Sec. 2.1). This layer's TYPE field does not establish which "
    "polygons are retail, so that priority is not applied, and exact reproduction of the paper's assignment is "
    "unavailable; the layer's vintage is also not the paper's. A site in two polygons of identical smallest area is "
    "listed with both and not placed (the tie is not broken), and a site in no polygon is listed and enters no utility. "
    "This is the same rule as row C's assignment at C0 to C2, so the two assignments agree by construction; that "
    "agreement is one rule applied twice and is not independent validation.")
# Row C's polygon rule: the smallest containing polygon over every territory, no priority by type (Scalera, Bosetti and
# Pecci, section 2.1 p. 4; S1.1 p. 25; settled from the paper; that the type plays no part is our reading of the paper's
# words, adopted by Joe on 2026-11-19, D-111).
# Rule name "polygon_smallest_any_type".
ROW_C_POLYGON = {"priority": "none", "wholesale_only_sites": None}
# The coincidence of the two rows' rules, said wherever both assignments are reported (Joe, 2026-11-19, D-109).
ROW_U_C_COINCIDENCE = (
    "U0's assignment and C0 to C2's assignment are the same rule, the smallest containing polygon over every polygon of "
    "the layer with the type not read, applied to the same table. Their agreement site by site is one rule applied twice "
    "and is not independent validation of either.")
# The missing-coverage qualification for rows U and C (Joe, 2026-11-19, D-109): "Missing territory coverage must never
# be described as evidence of no treatment." Kept apart from C5's operational never-host classification, which it does
# not redefine.
MISSING_COVERAGE_QUALIFICATION = (
    "No assigned site is not proof of no facility. A unit with no site assigned to it under the polygon rule, or under "
    "the inventory's own assignment, is not shown to have no data center. A site outside every polygon, a site in an "
    "exact area tie, a site the inventory does not list, or a polygon whose utility is not a panel unit all leave a unit "
    "with no assigned site. Missing territory coverage is never evidence of no treatment.")
# The four entity types whose sites row U lists (Joe, 2026-11-19, D-109), as the layer's TYPE field names them.
ROW_U_LISTED_ENTITY_TYPES = ("FEDERAL", "STATE", "MUNICIPAL MKTG AUTHORITY", "WHOLESALE POWER MARKETER")
ENTITY_TYPE_LIST_LABEL = (
    "Entity types as the layer's TYPE field names them, not a verified wholesale classification. For each type, the "
    "sites whose ASSIGNED polygon (the smallest containing polygon, U0's rule) carries that type are listed, and beside them the "
    "count of sites lying in ANY polygon of that type. The list decides no assignment, since U0 places every site by "
    "area alone, whatever these types are (Joe, 2026-11-19, D-109).")
_POLYGON_RULE_NAMES = {("retail_first", "unassigned"): "polygon_smallest_retail_first",
                       ("retail_first", "smallest_wholesale_only"): "polygon_smallest_wholesale_fallback",
                       ("none", None): "polygon_smallest_any_type"}
MAX_AMBIGUOUS_ENUMERATED = 12     # a site inside more ambiguous polygons than this is listed as dependent unexamined
# Row U's treatment as the paper states it (Ryu and Hiatt, session 20 bounded read; printed page numbers):
RYU_TERRITORY_LAYER = "HIFLD electric retail service territory shapefile"   # p. 5, Sec. 2.1, endnote 6
RYU_TREATMENT = "cumulative operating capacity in MW, summed over matched facilities, by utility and year"  # p. 5; Table A3 note p. 23
RYU_MULTI_STATE = "identical utility-level capacity in every state of the utility"                         # p. 6 Sec. 2.2; p. 8 Sec. 3.3


@dataclass
class Assignment:
    """An assignment under one rule: the (site, unit) rows and the sites left without a unit, each with its reason."""
    rule: str
    table: pd.DataFrame                    # fid, utility_id_eia, state, rule
    unassigned: pd.DataFrame               # fid, reason
    notes: list = field(default_factory=list)
    # sites whose unit would differ according to how an ambiguous polygon is classed (assign_polygon_smallest only):
    # fid, ambiguous_polygons, possible_units. Each is also in `unassigned`; none is placed by a guess.
    depends_on_ambiguous: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=["fid", "ambiguous_polygons", "possible_units"]))


@dataclass
class Treatment:
    """A treatment built from an assignment: one row per unit (first_year) or per unit-year (mw), and what was left out."""
    rule: str
    table: pd.DataFrame
    excluded_sites: pd.DataFrame           # fid, reason
    notes: list = field(default_factory=list)
    # fids of sites left out because their unit depends on how an ambiguous polygon is classed (from the assignment)
    depends_on_ambiguous: list = field(default_factory=list)


def _need(frame: pd.DataFrame, cols, what: str) -> None:
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise ValueError(f"{what} lacks the column(s) {missing}; the input is missing, not worked around")


def data_centers(sites: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(data center sites, the crypto mines left out with their reason). Crypto mines are not data centers."""
    _need(sites, ["fid", "is_crypto"], "sites")
    crypto = sites.is_crypto.fillna(False).astype(bool)
    out = sites.loc[crypto, ["fid"]].assign(reason="a cryptocurrency mine, not a data center")
    return sites.loc[~crypto].copy(), out


def map_reported_ids(frame: pd.DataFrame, reported_ids: pd.DataFrame, id_col: str) -> pd.DataFrame:
    """Map `id_col` (an id as EIA or the territory layer reported it) in `frame` to panel units by
    (utility_id_reported, state). Adds utility_id_eia; NaN where the id is not a panel unit in that state."""
    _need(reported_ids, ["utility_id_reported", "state", "utility_id_eia"], "reported_ids")
    m = reported_ids[["utility_id_reported", "state", "utility_id_eia"]].drop_duplicates(["utility_id_reported", "state"])
    left = frame.drop(columns=[c for c in ["utility_id_eia"] if c in frame.columns])
    out = left.merge(m, left_on=[id_col, "state"], right_on=["utility_id_reported", "state"], how="left")
    if id_col != "utility_id_reported":
        out = out.drop(columns="utility_id_reported")
    return out


# --------------------------------------------------------------------------------------------------------------------
# Assignment rules
# --------------------------------------------------------------------------------------------------------------------

def assign_verified(sites: pd.DataFrame) -> Assignment:
    """The inventory's own assignment: the site's utility_id_eia in the site's state. Crypto mines left out."""
    _need(sites, ["fid", "state", "utility_id_eia", "is_crypto"], "sites")
    dc, crypto = data_centers(sites)
    no_unit = dc.utility_id_eia.isna() | dc.state.isna()
    why = np.where(dc.utility_id_eia.isna(), "the inventory gives the site no utility", "the site has no state")
    if "utility_assign" in dc.columns:
        why = np.where(dc.utility_id_eia.isna(), "the inventory gives the site no utility (" + dc.utility_assign.astype(str) + ")", why)
    unassigned = pd.concat([crypto, pd.DataFrame({"fid": dc.fid[no_unit].values, "reason": np.asarray(why)[no_unit.values]})],
                           ignore_index=True)
    t = dc.loc[~no_unit, ["fid", "utility_id_eia", "state"]].copy()
    t["utility_id_eia"] = t.utility_id_eia.astype(int)
    t["rule"] = "verified"
    return Assignment("verified", t.reset_index(drop=True), unassigned)


def assign_county_touch(sites: pd.DataFrame, site_county: pd.DataFrame, territory_counties: pd.DataFrame,
                        reported_ids: pd.DataFrame, territory_vintage) -> Assignment:
    """Every utility whose EIA-861 service territory includes the site's county, in the site's state (row M, M0).

    site_county         fid, county (one county per site; a key both tables share, FIPS recommended)
    territory_counties  utility_id_reported, state, county, and `year` when territory_vintage is not "union_of_all_years"
    reported_ids        utility_id_reported, state -> utility_id_eia (panel units)
    territory_vintage   REQUIRED, no default. Which year's territory file maps counties to utilities. Meeks et al. do
                        not state it for the main treatment ("the set of counties it serves", p. 16, the file dated
                        2026-10-23); their wholesale-price, wildfire and instrument constructions use the counties
                        reported in EIA-861 in 2010 (SI-4, SI-6, SI-9) and their renewable-capacity control each year's
                        list (SI-5). Candidates: an int year (that year's rows only);
                        "union_of_all_years" (a county is touched if any year lists it); "year_of_entry" (the rows of
                        the site's energized_year; a site whose year is missing from the table is listed).
    """
    _need(site_county, ["fid", "county"], "site_county")
    _need(territory_counties, ["utility_id_reported", "state", "county"], "territory_counties")
    if not (isinstance(territory_vintage, (int, np.integer)) or territory_vintage in TERRITORY_VINTAGES):
        raise ValueError(f"territory_vintage must be an int year or one of {TERRITORY_VINTAGES}, not {territory_vintage!r}")
    dc, crypto = data_centers(sites)
    dc = dc.merge(site_county[["fid", "county"]].drop_duplicates("fid"), on="fid", how="left")
    rows, gone = [], [crypto]
    no_county = dc.county.isna() | dc.state.isna()
    gone.append(pd.DataFrame({"fid": dc.fid[no_county], "reason": "the site has no county or no state"}))
    dc = dc[~no_county]
    terr = territory_counties
    if isinstance(territory_vintage, (int, np.integer)):
        _need(terr, ["year"], "territory_counties")
        terr = terr[terr.year == int(territory_vintage)]
        if terr.empty:
            raise ValueError(f"territory_counties has no rows for {territory_vintage}")
    if territory_vintage == "year_of_entry":
        _need(terr, ["year"], "territory_counties")
        _need(dc, ["energized_year"], "sites")
        have = set(terr.year.unique())
        bad = dc.energized_year.isna() | ~dc.energized_year.isin(have)
        gone.append(pd.DataFrame({"fid": dc.fid[bad], "reason": "the site's energized_year is missing or not a year of the territory table"}))
        dc = dc[~bad]
        j = dc[["fid", "state", "county", "energized_year"]].merge(
            terr[["utility_id_reported", "state", "county", "year"]], left_on=["state", "county", "energized_year"],
            right_on=["state", "county", "year"], how="left")
    else:
        j = dc[["fid", "state", "county"]].merge(
            terr[["utility_id_reported", "state", "county"]].drop_duplicates(), on=["state", "county"], how="left")
    none = j.groupby("fid").utility_id_reported.apply(lambda s: s.isna().all())
    gone.append(pd.DataFrame({"fid": none.index[none.values], "reason": "no utility's territory lists the site's county"}))
    j = j.dropna(subset=["utility_id_reported"])
    j = map_reported_ids(j, reported_ids, "utility_id_reported")
    off = j.utility_id_eia.isna()
    notes = []
    if off.any():
        notes.append(f"{int(off.sum())} (site, reported utility) pairs name a utility that is not a panel unit in the "
                     f"site's state; listed in the unassigned table where a site is left with no panel unit")
    j = j[~off]
    nothing = sorted(set(none.index[~none.values]) - set(j.fid))
    gone.append(pd.DataFrame({"fid": nothing, "reason": "every utility touching the county is outside the panel in that state"}))
    t = j[["fid", "utility_id_eia", "state"]].drop_duplicates().copy()
    t["utility_id_eia"] = t.utility_id_eia.astype(int)
    t["rule"] = "county_touch"
    rows.append(t)
    return Assignment("county_touch", pd.concat(rows, ignore_index=True), pd.concat(gone, ignore_index=True), notes)


def assign_polygon_smallest(sites: pd.DataFrame, incidence: pd.DataFrame, reported_ids: pd.DataFrame, *,
                            priority: str, wholesale_only_sites: str | None) -> Assignment:
    """The territory polygon that strictly contains the site, the smallest by area under a priority (U0; C0 to C2).

    incidence     one row per (site, polygon) where the polygon strictly contains the site's point: fid,
                  utility_id_reported (the polygon's id), area (any one unit, e.g. km2 in an equal-area projection) and,
                  under priority "retail_first", type_class in TYPE_CLASSES. Built elsewhere from the territory layer;
                  not read here. A table with the old is_retail flag and no type_class is refused in words.
    reported_ids  utility_id_reported, state -> utility_id_eia
    priority      REQUIRED, keyword only. "none" (rows U and C since D-109: the smallest of every containing polygon,
                  the type not read; row C's from the paper's S1.1 p. 25, row U's our labelled approximation) or
                  "retail_first" (retail polygons before wholesale-only ones, the Ryu and Hiatt paper's priority, p. 5;
                  no row's specification since D-109, because this layer's TYPE field does not establish which
                  polygons are retail).
    wholesale_only_sites  REQUIRED with "retail_first", None with "none": a site that only wholesale-only polygons
                  contain. "unassigned" (listed, no unit) or "smallest_wholesale_only".

    Rows U and C both pass the rule {"priority": "none", "wholesale_only_sites": None} (ROW_U_POLYGON, ROW_C_POLYGON),
    named "polygon_smallest_any_type". The other names, "polygon_smallest_retail_first" and
    "polygon_smallest_wholesale_fallback", are neither row's specification.

    An exact tie in area between two different utilities' polygons is NOT broken (no rule in the plan or the papers):
    the site is listed with the tied ids. A site no polygon contains is listed. The chosen polygon's id is mapped to a
    panel unit in the site's state; a polygon whose utility is not a panel unit there leaves the site unassigned
    (listed).

    Ambiguous polygons (type_class "ambiguous", under "retail_first" only). For each site inside one or more, every way
    of classing those polygons as retail or wholesale-only is tried (2 to the power of their number; the agent's
    reading). The table carries each polygon's class and not its TYPE value, so polygons are classed one by one: this
    covers every joint classing of the TYPE values behind them, and can also list a site that a classing by TYPE
    value would not (two ambiguous polygons of one value classed apart); it errs toward listing. If every way gives the
    same panel unit,
    or no unit every time, the site takes that result and the ambiguity did not decide it. Otherwise the site is not
    assigned, it is listed in `unassigned` with the polygons and the units it could take, and it is in
    `depends_on_ambiguous`; a step built on this assignment says its result depends on those sites. A site inside more
    than MAX_AMBIGUOUS_ENUMERATED ambiguous polygons is listed as dependent without the enumeration.
    """
    if priority not in POLYGON_PRIORITIES:
        raise ValueError(f"priority must be one of {POLYGON_PRIORITIES}, not {priority!r}")
    if priority == "retail_first" and wholesale_only_sites not in WHOLESALE_ONLY_RULES:
        raise ValueError(f"wholesale_only_sites must be one of {WHOLESALE_ONLY_RULES} under priority 'retail_first', "
                         f"not {wholesale_only_sites!r}")
    if priority == "none" and wholesale_only_sites is not None:
        raise ValueError("wholesale_only_sites plays no part when no type is preferred; pass None")
    rule = _POLYGON_RULE_NAMES[(priority, wholesale_only_sites)]
    if priority == "retail_first" and "type_class" not in incidence.columns and "is_retail" in incidence.columns:
        raise ValueError("incidence carries is_retail and no type_class; since D-107 the table classes each polygon as "
                         "retail, wholesale_only or ambiguous, and an ambiguous one is not read as either")
    _need(incidence, ["fid", "utility_id_reported", "area"] + (["type_class"] if priority == "retail_first" else []),
          "incidence")
    dc, crypto = data_centers(sites)
    gone = [crypto]
    inc = incidence[incidence.fid.isin(dc.fid)].copy()
    if inc.area.isna().any():
        raise ValueError("incidence has a missing area; the input is incomplete")
    if priority == "retail_first":
        bad = sorted(set(inc.type_class.dropna().unique()) - set(TYPE_CLASSES))
        if inc.type_class.isna().any() or bad:
            raise ValueError(f"incidence type_class must be one of {TYPE_CLASSES} for every row (found {bad}, "
                             f"{int(inc.type_class.isna().sum())} missing); the input is incomplete")
    else:
        inc["type_class"] = "any"
    nopoly = sorted(set(dc.fid) - set(inc.fid))
    gone.append(pd.DataFrame({"fid": nopoly, "reason": "no territory polygon contains the site"}))
    state_of = dc.set_index("fid").state
    rep = reported_ids[["utility_id_reported", "state", "utility_id_eia"]].drop_duplicates(["utility_id_reported", "state"])
    unit_of = {(int(r), s): int(u) for r, s, u in zip(rep.utility_id_reported, rep.state, rep.utility_id_eia) if pd.notna(u)}

    def choose(g: pd.DataFrame, cls: list) -> tuple:
        """(kind, value): ("polygon", id), ("tie", ids) or ("wholesale_only", None), for one classing of g's rows."""
        if priority == "retail_first":
            pool = g[[c == "retail" for c in cls]]
            if pool.empty:
                if wholesale_only_sites == "unassigned":
                    return ("wholesale_only", None)
                pool = g
        else:
            pool = g
        top = pool[pool.area == pool.area.min()].utility_id_reported.unique()
        if len(top) > 1:
            return ("tie", tuple(sorted(int(x) for x in top)))
        return ("polygon", int(top[0]))

    def unit(kind_value: tuple, st) -> int | None:
        kind, v = kind_value
        return unit_of.get((v, st)) if kind == "polygon" and pd.notna(st) else None

    rows, dep = [], []
    for fid, g in inc.groupby("fid", sort=True):
        st = state_of.get(fid)
        cls = list(g.type_class)
        amb = [i for i, c in enumerate(cls) if c == "ambiguous"]
        if amb:
            amb_ids = sorted({int(x) for x in g.utility_id_reported.iloc[amb]})
            if len(amb) > MAX_AMBIGUOUS_ENUMERATED:
                dep.append({"fid": fid, "ambiguous_polygons": amb_ids, "possible_units": None})
                gone.append(pd.DataFrame({"fid": [fid], "reason": [
                    f"inside {len(amb)} polygons of ambiguous type {amb_ids}; not enumerated and not assigned by a guess"]}))
                continue
            outcomes = {}
            for combo in itertools.product(("retail", "wholesale_only"), repeat=len(amb)):
                c2 = list(cls)
                for i, c in zip(amb, combo):
                    c2[i] = c
                o = choose(g, c2)
                outcomes.setdefault(unit(o, st), o)
            if len(outcomes) > 1:
                units = sorted(("none" if u is None else f"{u}:{st}") for u in outcomes)
                dep.append({"fid": fid, "ambiguous_polygons": amb_ids, "possible_units": units})
                gone.append(pd.DataFrame({"fid": [fid], "reason": [
                    f"its unit depends on how the ambiguous polygon(s) {amb_ids} are classed (possible: {units}); "
                    f"not assigned by a guess"]}))
                continue
            choice = next(iter(outcomes.values()))
        else:
            choice = choose(g, cls)
        kind, v = choice
        if kind == "wholesale_only":
            gone.append(pd.DataFrame({"fid": [fid], "reason": ["only wholesale-only polygons contain the site"]}))
        elif kind == "tie":
            gone.append(pd.DataFrame({"fid": [fid], "reason": [f"tie in area between polygons {list(v)}; no tie rule"]}))
        else:
            rows.append({"fid": fid, "utility_id_reported": v, "state": st})
    t = pd.DataFrame(rows, columns=["fid", "utility_id_reported", "state"])
    nostate = t.state.isna()
    gone.append(pd.DataFrame({"fid": t.fid[nostate], "reason": "the site has no state"}))
    t = map_reported_ids(t[~nostate], reported_ids, "utility_id_reported")
    off = t.utility_id_eia.isna()
    gone.append(pd.DataFrame({"fid": t.fid[off], "reason": "the chosen polygon's utility is not a panel unit in the site's state"}))
    t = t[~off][["fid", "utility_id_eia", "state"]].copy()
    t["utility_id_eia"] = t.utility_id_eia.astype(int)
    t["rule"] = rule
    notes = []
    if dep:
        notes.append(f"{len(dep)} sites are not assigned because their unit depends on how ambiguous polygons are "
                     f"classed; a result built on this assignment depends on them")
    return Assignment(rule, t.reset_index(drop=True), pd.concat(gone, ignore_index=True), notes,
                      pd.DataFrame(dep, columns=["fid", "ambiguous_polygons", "possible_units"]))


def smallest_polygon_by_site(incidence: pd.DataFrame, fids=None) -> dict:
    """{fid: ("polygon", id) or ("tie", ids)} under the smallest-containing-polygon rule, the type not read: the same
    choice assign_polygon_smallest makes under priority "none" (an exact tie in area between different ids is not
    broken). A site with no incidence row is absent from the result."""
    _need(incidence, ["fid", "utility_id_reported", "area"], "incidence")
    inc = incidence if fids is None else incidence[incidence.fid.isin(set(fids))]
    if inc.area.isna().any():
        raise ValueError("incidence has a missing area; the input is incomplete")
    out = {}
    for fid, g in inc.groupby("fid", sort=True):
        top = g[g.area == g.area.min()].utility_id_reported.unique()
        out[fid] = ("tie", tuple(sorted(int(x) for x in top))) if len(top) > 1 else ("polygon", int(top[0]))
    return out


def entity_type_list(sites: pd.DataFrame, typed_incidence: pd.DataFrame, assignment: Assignment | None = None,
                     types=ROW_U_LISTED_ENTITY_TYPES) -> dict:
    """Row U's list of the sites associated with four of the layer's entity types (Joe, 2026-11-19, D-109).

    typed_incidence  one row per (site, polygon) that strictly contains the site: fid, utility_id_reported, area and
                     TYPE (the layer's own value; reconciliation_inputs.typed_incidence_table). type_class, if present,
                     is not read.
    assignment       U0's assignment (assign_polygon_smallest under ROW_U_POLYGON), to count how many listed sites map
                     to a panel unit; optional.
    For each type: `assigned_fids`, the data center sites whose ASSIGNED polygon (the smallest containing polygon, the
    rule U0 uses) carries that type; `lying_in_any_count`, the data center sites inside ANY polygon of that type (the
    meaning of "associated" Joe adopted: assigned polygon, with the count lying in any beside it). A site in an exact
    area tie has no assigned polygon; it is listed apart under `ties_not_broken` with the types of the tied polygons.
    Crypto mines are not data centers and are left out. The list decides no assignment."""
    _need(typed_incidence, ["fid", "utility_id_reported", "area", "TYPE"], "typed_incidence")
    dc, _ = data_centers(sites)
    inc = typed_incidence[typed_incidence.fid.isin(set(dc.fid))].copy()
    inc["TYPE"] = inc.TYPE.astype(object).where(inc.TYPE.notna(), "<missing>").astype(str)
    choice = smallest_polygon_by_site(inc)
    placed = set(assignment.table.fid) if assignment is not None else None
    by_type, ties = {}, {}
    for t in types:
        assigned = []
        for fid, (kind, v) in choice.items():
            if kind != "polygon":
                continue
            g = inc[inc.fid == fid]
            top = g[(g.area == g.area.min()) & (g.utility_id_reported == v)]
            if t in set(top.TYPE):
                assigned.append(fid)
        lying = sorted(set(inc.fid[inc.TYPE == t]))
        by_type[t] = {"assigned_fids": sorted(assigned), "assigned_count": len(assigned),
                      "lying_in_any_count": len(lying),
                      "assigned_and_mapped_to_a_panel_unit": (None if placed is None
                                                              else sum(f in placed for f in assigned))}
    for fid, (kind, v) in choice.items():
        if kind == "tie":
            g = inc[inc.fid == fid]
            ties[fid] = {"tied_polygon_ids": list(v),
                         "types_of_the_tied_polygons": sorted(set(g[g.area == g.area.min()].TYPE))}
    listed = sorted({f for d in by_type.values() for f in d["assigned_fids"]})
    return {"label": ENTITY_TYPE_LIST_LABEL, "types": list(types), "by_type": by_type,
            "listed_sites_any_type": len(listed),
            "listed_sites_mapped_to_a_panel_unit": None if placed is None else sum(f in placed for f in listed),
            "ties_not_broken": ties, "data_center_sites_with_a_containing_polygon": len(choice)}


def identical_site_by_site(a: Assignment, b: Assignment, fids) -> dict:
    """Whether two assignments give every site in `fids` the same result: the same panel units, or, for a site left
    without one, the same reason. Used to show by computation that U0 and C0 to C2 assign identically (and to report
    it as one rule applied twice, not as validation)."""
    def placed(x: Assignment) -> dict:
        return {f: tuple(sorted(zip(g.utility_id_eia.astype(int), g.state))) for f, g in x.table.groupby("fid")}
    pa, pb = placed(a), placed(b)
    ra = a.unassigned.drop_duplicates("fid").set_index("fid").reason.to_dict()
    rb = b.unassigned.drop_duplicates("fid").set_index("fid").reason.to_dict()
    differ = []
    for f in sorted(set(fids)):
        if (pa.get(f), ra.get(f)) != (pb.get(f), rb.get(f)):
            differ.append(f)
    n = len(set(fids))
    return {"sites_compared": n, "identical": n - len(differ), "differ": differ,
            "placed_on_the_same_unit": sum(1 for f in set(fids) if f in pa and pa.get(f) == pb.get(f)),
            "left_unplaced_for_the_same_reason": sum(1 for f in set(fids) if f not in pa and f not in pb
                                                     and ra.get(f) == rb.get(f))}


def compare_assignments(a: Assignment, b: Assignment) -> pd.DataFrame:
    """Site by site: the units each rule gives, and whether they agree. One row per site present in either rule."""
    def units_of(x: Assignment) -> pd.Series:
        return x.table.groupby("fid").apply(lambda g: tuple(sorted(zip(g.utility_id_eia.astype(int), g.state))),
                                             include_groups=False)
    ua, ub = units_of(a), units_of(b)
    fids = sorted(set(ua.index) | set(ub.index) | set(a.unassigned.fid) | set(b.unassigned.fid))
    out = pd.DataFrame({"fid": fids})
    out[a.rule] = [ua.get(f, ()) for f in fids]
    out[b.rule] = [ub.get(f, ()) for f in fids]
    out["agree"] = [x == y for x, y in zip(out[a.rule], out[b.rule])]
    out[f"{b.rule}_units_not_in_{a.rule}"] = [len(set(y) - set(x)) for x, y in zip(out[a.rule], out[b.rule])]
    return out


# --------------------------------------------------------------------------------------------------------------------
# Treatment builders
# --------------------------------------------------------------------------------------------------------------------

def first_year_above_size(sites: pd.DataFrame, assignment: Assignment, units: pd.DataFrame, size_column: str,
                          counting: str, threshold_mw: float = 5.0, site_county: pd.DataFrame | None = None) -> Treatment:
    """First year a data center above `threshold_mw` enters the unit (row M, steps M0 to M3). NaN: never in the inventory.

    The year is the site's energized_year (the inventory's start year as built). The 5 MW is the plan's and the paper's;
    "above" is strict (Meeks et al., file dated 2026-10-23, Sec. 4.2, p. 18: "We keep county-years with newly activated
    capacity above 5 MW").

    size_column   REQUIRED, no default. "mw_full" (the site's size as built, after the state anchoring factor) or
                  "mw_full_raw" (before it). The paper used its vendor's estimated power capacity; which of ours stands
                  for it is not settled. On the inventory read 2026-11-19 the two disagree about 5 MW for 91 sites.
    counting      REQUIRED, no default. The plan says "a data center above 5 MW enters a county"; the paper (Sec. 4.2
                  p. 18, read in the file dated 2026-10-23) sums newly activated capacity by county-year and keeps
                  county-years above 5 MW. The two differ, and which the row uses is with Joe (D-107, job 8).
                  "site": a site above the threshold. "county_year_new_capacity": the unit's assigned sites summed by
                  county and energized_year, a county-year above the threshold (needs `site_county`). Under
                  county_touch every unit touching a county carries all of its sites, so this is the paper's county
                  rule; under verified it is the unit's own sites in that county (the agent's reading of the rule
                  under one serving utility).

    A site with no size or no year cannot be said to be above 5 MW in any year: it is listed in excluded_sites with
    its reason and does not move a first year (the agent's reading; the count is reported).
    """
    if size_column not in ("mw_full", "mw_full_raw"):
        raise ValueError(f"size_column must be 'mw_full' or 'mw_full_raw', not {size_column!r}")
    if counting not in SIZE_COUNTING:
        raise ValueError(f"counting must be one of {SIZE_COUNTING}, not {counting!r}")
    _need(sites, ["fid", "energized_year", size_column], "sites")
    _need(units, KEY, "units")
    s = sites[["fid", "energized_year", size_column]].rename(columns={size_column: "size"})
    a = assignment.table.merge(s, on="fid", how="left")
    excl = [assignment.unassigned.assign(reason="no unit under the rule: " + assignment.unassigned.reason.astype(str))]
    bad_size, bad_year = a["size"].isna(), a.energized_year.isna()
    excl.append(pd.DataFrame({"fid": a.fid[bad_size].unique(), "reason": "no size on the inventory"}))
    excl.append(pd.DataFrame({"fid": a.fid[bad_year & ~bad_size].unique(), "reason": "no start year on the inventory"}))
    a = a[~bad_size & ~bad_year]
    if counting == "site":
        hit = a[a["size"] > threshold_mw]
    else:
        if site_county is None:
            raise ValueError("counting='county_year_new_capacity' needs site_county (fid, county)")
        a = a.merge(site_county[["fid", "county"]].drop_duplicates("fid"), on="fid", how="left")
        nc = a.county.isna()
        excl.append(pd.DataFrame({"fid": a.fid[nc].unique(), "reason": "no county, so no county-year to sum into"}))
        a = a[~nc]
        cy = a.groupby(KEY + ["county", "energized_year"], as_index=False)["size"].sum()
        hit = cy[cy["size"] > threshold_mw]
    first = hit.groupby(KEY).energized_year.min()
    out = units[KEY].drop_duplicates().merge(first.rename("first_year").reset_index(), on=KEY, how="left")
    out["rule"] = f"{assignment.rule}|above_{threshold_mw:g}mw|{counting}|{size_column}"
    return Treatment(out["rule"].iloc[0] if len(out) else assignment.rule, out, pd.concat(excl, ignore_index=True))


def first_year_at_dose(dose: pd.DataFrame, units: pd.DataFrame, threshold: float = 0.02) -> Treatment:
    """First year the unit's data center load share reaches `threshold` (step M4: "our 2% load threshold").

    dose  utility_id_eia, state, year, dose (data/interim/utility_year_dose.parquet; load over 2009-2011 retail
          sales, crypto not counted). "Reaches" is >=, as in the plan's Treatment bullet ("from the first year that
          share reaches 2%"). A unit-year with a missing dose never counts as reaching it; units with only missing
          doses are listed in notes.
    """
    _need(dose, KEY + ["year", "dose"], "dose")
    d = dose.dropna(subset=["dose"])
    hit = d[d.dose >= threshold]
    first = hit.groupby(KEY).year.min()
    out = units[KEY].drop_duplicates().merge(first.rename("first_year").reset_index(), on=KEY, how="left")
    out["rule"] = f"verified|dose_at_least_{threshold:g}"
    notes = []
    all_nan = dose.groupby(KEY).dose.apply(lambda s: s.isna().all())
    if all_nan.any():
        notes.append(f"{int(all_nan.sum())} units have no non-missing dose in any year and are never treated here")
    return Treatment(out["rule"].iloc[0] if len(out) else "dose", out, pd.DataFrame(columns=["fid", "reason"]), notes)


def cumulative_mw(assignment: Assignment, units: pd.DataFrame, years, mw_source: str,
                  site_year: pd.DataFrame | None = None, sites: pd.DataFrame | None = None) -> Treatment:
    """Cumulative operating data center MW by unit and year (row U), a multi-state utility's capacity entered in each
    of its states (PREANALYSIS.md, row U: "a multi-state utility's capacity entered in each of its states"; Ryu and
    Hiatt p. 6, Sec. 2.2, and p. 8, Sec. 3.3: "identical utility-level data center capacity"). The MW of every site
    assigned to the utility, in any state, is summed by utility and year and that total is put on every panel unit of
    the utility. A unit with no site carries 0. That the measure is cumulative operating capacity in MW, summed over the
    matched facilities by year, is the paper's (p. 5, Sec. 2.1; Table A3 note, p. 23).

    mw_source   REQUIRED, no default. How "operating" is dated is not stated by the paper (checked in session 20): it
                names the vendor's fields (utility power capacity in kW, operational status, build year; p. 5) but not
                how they become a yearly figure, whether a facility counts in its build year, whether capacity is
                phased in, or what status values count. The paper's measure is a vendor's capacity, not load, so
                exact reproduction of the measure is unavailable on our inventory. Candidates:
                "site_year_load": the inventory's load by site and year (`site_year`: fid, year, mw; with a `crypto`
                    column, crypto rows are left out), which carries the inventory's ramps and phased histories.
                    The plan's known mismatch ("their MW is a vendor's operating capacity; ours is estimated load")
                    reads as this one. It is row U's specification: ours, not the paper's, this study's approximation
                    adopted by Joe on 2026-11-19 (D-107; reconciliation_mu.RYU_OURS_MW_SOURCE).
                "full_size_from_energized_year": the site's mw_full in every year from its energized_year on
                    (`sites`). Sites with no size or no year are listed and carry nothing. Not row U's specification
                    since D-107; row U refuses a treatment built on it.
    """
    if mw_source not in MW_SOURCES:
        raise ValueError(f"mw_source must be one of {MW_SOURCES}, not {mw_source!r}")
    years = list(years)
    _need(units, KEY, "units")
    excl = [assignment.unassigned.assign(reason="no unit under the rule: " + assignment.unassigned.reason.astype(str))]
    a = assignment.table[["fid", "utility_id_eia"]]
    if a.fid.duplicated().any():
        raise ValueError("an assignment with several units per site cannot carry one site's MW; the U rules give one unit")
    if mw_source == "site_year_load":
        if site_year is None:
            raise ValueError("mw_source='site_year_load' needs site_year (fid, year, mw)")
        _need(site_year, ["fid", "year", "mw"], "site_year")
        sy = site_year
        if "crypto" in sy.columns:
            sy = sy[~sy.crypto.astype(bool)]
        sy = sy[["fid", "year", "mw"]]
        no_rows = sorted(set(a.fid) - set(sy.fid))
        excl.append(pd.DataFrame({"fid": no_rows, "reason": "no site-year load on the inventory"}))
        m = a.merge(sy, on="fid", how="inner")
    else:
        if sites is None:
            raise ValueError("mw_source='full_size_from_energized_year' needs sites (fid, energized_year, mw_full)")
        _need(sites, ["fid", "energized_year", "mw_full"], "sites")
        s = a.merge(sites[["fid", "energized_year", "mw_full"]], on="fid", how="left")
        bad = s.mw_full.isna() | s.energized_year.isna()
        excl.append(pd.DataFrame({"fid": s.fid[bad], "reason": "no size or no start year on the inventory"}))
        s = s[~bad]
        grid = s.merge(pd.DataFrame({"year": years}), how="cross")
        m = grid[grid.year >= grid.energized_year].rename(columns={"mw_full": "mw"})[["fid", "utility_id_eia", "year", "mw"]]
    by_utility = m[m.year.isin(years)].groupby(["utility_id_eia", "year"]).mw.sum()
    u = units[KEY].drop_duplicates()
    grid = u.merge(pd.DataFrame({"year": years}), how="cross")
    out = grid.merge(by_utility.rename("mw").reset_index(), on=["utility_id_eia", "year"], how="left")
    out["mw"] = out.mw.fillna(0.0)
    out["rule"] = f"{assignment.rule}|{mw_source}"
    notes = list(assignment.notes)
    off = set(by_utility.index.get_level_values(0)) - set(u.utility_id_eia)
    if off:
        notes.append(f"{len(off)} utilities carry load but have no panel unit; their MW enters no unit")
    dep = sorted(assignment.depends_on_ambiguous.fid) if len(assignment.depends_on_ambiguous) else []
    return Treatment(f"{assignment.rule}|{mw_source}", out, pd.concat(excl, ignore_index=True), notes, dep)


def cohort_counts(treatment: Treatment, window: tuple[int, int]) -> dict:
    """Quantity-side counts for a first-year treatment: units first treated before, inside and after the window, never,
    and the first years inside it. No outcome is involved."""
    fy = treatment.table.first_year
    lo, hi = window
    inside = fy[(fy >= lo) & (fy <= hi)]
    return {"units": int(len(fy)), "never_in_the_inventory": int(fy.isna().sum()),
            "first_treated_before_window": int((fy < lo).sum()), "first_treated_inside_window": int(len(inside)),
            "first_treated_after_window": int((fy > hi).sum()),
            "inside_window_by_first_year": {int(k): int(v) for k, v in inside.value_counts().sort_index().items()}}
