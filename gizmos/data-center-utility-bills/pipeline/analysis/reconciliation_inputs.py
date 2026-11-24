#!/usr/bin/env python3
"""Quantity-side inputs for the reconciliation rows U and C (R4, accesses 1 to 3; Joe, D-107, 2026-11-19).

Reads NO price, NO revenue and NO bill. The three reads under data/raw are the only ones the owner authorized for
this job, each through a reader with a fixed column list held as a module constant:

  access 1  read_type_values()     the field TYPE of data/raw/territories/retail_service_territories.geojson,
                                   nothing else, for its distinct values
  access 2  read_territories()     ID, TYPE and geometry of the same layer, by a column list; never NAME, STATE,
                                   CNTRL_AREA, HOLDING_CO, RETAIL_MWH, CUSTOMERS, YEAR or SOURCEDATE
  access 3  read_short_form()      utility_id_eia, state, report_date, short_form, data_observed of
                                   data/raw/pudl/core_eia861__yearly_operational_data_misc.parquet, by a column list

Pure functions build the two tables from frames passed in:

  polygon_incidence()   one row per inventory site and territory polygon that strictly contains its point:
                        fid, utility_id_reported, area, type_class
  short_form_flags()    one row per unit and year: utility_id_eia, state, year, short_form, data_observed

The TYPE mapping (TYPE_CLASS below) is the agent's reading of "clearly supported" as the session read it: a value is
`retail` only if its own text names retail service, `wholesale_only` only if its own text names wholesale only, and
anything else is `ambiguous`. A value not in the mapping, or a missing TYPE, is `ambiguous`. Nothing here treats
`ambiguous` as retail or as wholesale-only; instead dependent_sites() lists, for each ambiguous value, every site
whose assignment under row U's rule or row C's rule would turn on how that value is classed.

main() does the three reads and writes data/interim/reconciliation_polygon_incidence.parquet,
data/interim/reconciliation_short_form_flags.parquet and the quantity-only summary
data/frozen/reconciliation_polygon_incidence_summary.json. Written 2026-11-19 (session 21, job 4).

main_types() (session 22, Joe's ruling of 2026-11-19, D-109, which covers "the repeat territory-layer read by the same
three authorized fields") repeats access 2 ONLY: ID, TYPE and geometry through read_territories, once, and writes
data/interim/reconciliation_polygon_incidence_types.parquet (TYPED_INCIDENCE_COLUMNS: the incidence with the layer's own
TYPE value, which the first table carries only as a class). It first rebuilds the first table's four columns from the
same read and stops, writing nothing, if they differ from the table on file in any row. It reads nothing else under
data/raw (not the short-form file) and does not hash the layer. Run it as `reconciliation_inputs.py --types-only`.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TERRITORY_LAYER = ROOT / "data" / "raw" / "territories" / "retail_service_territories.geojson"
OPERATIONAL_MISC = ROOT / "data" / "raw" / "pudl" / "core_eia861__yearly_operational_data_misc.parquet"
FACILITIES = ROOT / "data" / "interim" / "facilities.parquet"
OUT_INCIDENCE = ROOT / "data" / "interim" / "reconciliation_polygon_incidence.parquet"
OUT_SHORT_FORM = ROOT / "data" / "interim" / "reconciliation_short_form_flags.parquet"
OUT_SUMMARY = ROOT / "data" / "frozen" / "reconciliation_polygon_incidence_summary.json"
OUT_TYPED_INCIDENCE = ROOT / "data" / "interim" / "reconciliation_polygon_incidence_types.parquet"

# ---- the fixed column lists, one per access ---------------------------------------------------------------------
ACCESS_1_FIELDS = ("TYPE",)                       # read with read_geometry=False
ACCESS_2_FIELDS = ("ID", "TYPE")                  # plus the geometry
NEVER_LOADED_TERRITORY_FIELDS = ("NAME", "STATE", "CNTRL_AREA", "HOLDING_CO", "RETAIL_MWH", "CUSTOMERS", "YEAR",
                                 "SOURCEDATE")
ACCESS_3_COLUMNS = ("utility_id_eia", "state", "report_date", "short_form", "data_observed")
FACILITY_COLUMNS = ("fid", "lat", "lon")

# ---- the two tables' columns, exactly ---------------------------------------------------------------------------
INCIDENCE_COLUMNS = ("fid", "utility_id_reported", "area", "type_class")
TYPED_INCIDENCE_COLUMNS = ("fid", "polygon", "utility_id_reported", "area", "TYPE")   # session 22, D-109
SHORT_FORM_COLUMNS = ("utility_id_eia", "state", "year", "short_form", "data_observed")

# ---- containment and area, as the inventory build places a point (pipeline/facilities/build_inventory.py) ----------
POINT_CRS = 4326          # facilities.parquet lat and lon
EQUAL_AREA_CRS = 5070     # NAD83 / CONUS Albers, metres; Albers is equal-area everywhere, so areas outside CONUS hold
AREA_UNITS = "square kilometres in EPSG:5070 (NAD83 / Conus Albers equal-area)"
CONTAINMENT = ("geopandas.sjoin(points, polygons, predicate='within'): the point lies in the polygon's interior and "
               "not on its boundary, which is the paper's 'strictly contains'; the same predicate, projection and "
               "buffer(0) repair as build_inventory.assign_utility, except that polygons with a non-numeric ID are "
               "kept here and listed, where the build drops them")

# ---- the TYPE mapping: the agent's reading, filled after access 1 ----------------------------------------------------
CLASSES = ("retail", "wholesale_only", "ambiguous")
# Access 1 (2026-11-19) found ten distinct values and no missing value. None of them names retail service, and none
# names wholesale only, so under the reading every one is `ambiguous`. The field does not mark wholesale-only
# territories by name. Recorded with the polygon counts in docs/gate1/territory-type-mapping-2026-11-19.md.
_OWNERSHIP = ("names an ownership or governance type; it does not name retail service or wholesale-only service. "
              "That such utilities usually sell at retail is outside knowledge, not the value's text")
TYPE_CLASS: dict[str, str] = {
    "COMMUNITY CHOICE AGGREGATOR": "ambiguous",
    "COOPERATIVE": "ambiguous",
    "FEDERAL": "ambiguous",
    "INVESTOR OWNED": "ambiguous",
    "MUNICIPAL": "ambiguous",
    "MUNICIPAL MKTG AUTHORITY": "ambiguous",
    "NOT AVAILABLE": "ambiguous",
    "POLITICAL SUBDIVISION": "ambiguous",
    "STATE": "ambiguous",
    "WHOLESALE POWER MARKETER": "ambiguous",
}
TYPE_CLASS_REASON: dict[str, str] = {
    "COMMUNITY CHOICE AGGREGATOR": ("names an aggregation arrangement; the text does not say retail or wholesale-only "
                                    "service"),
    "COOPERATIVE": _OWNERSHIP,
    "FEDERAL": _OWNERSHIP,
    "INVESTOR OWNED": _OWNERSHIP,
    "MUNICIPAL": _OWNERSHIP,
    "MUNICIPAL MKTG AUTHORITY": ("names a municipal marketing authority; 'marketing' does not say retail or "
                                 "wholesale-only service"),
    "NOT AVAILABLE": "names no type at all",
    "POLITICAL SUBDIVISION": _OWNERSHIP,
    "STATE": _OWNERSHIP,
    "WHOLESALE POWER MARKETER": ("the only value whose text names wholesale, but it names a wholesale marketer and "
                                 "not wholesale ONLY; reading it as a territory with no retail service would add "
                                 "'only' from outside the text. The nearest candidate for wholesale_only, left for "
                                 "the session and Joe"),
}

# =================================================================================================================
# Readers (the only code that touches data/raw)
# =================================================================================================================
def _guarded(read_fn, allowed: tuple[str, ...], what: str):
    """Wrap a reader so that a request for any column outside `allowed` raises before the read."""
    def call(path, columns, **kw):
        cols = tuple(columns)
        extra = sorted(set(cols) - set(allowed))
        if extra:
            raise PermissionError(f"{what}: columns {extra} are outside the authorized list {list(allowed)}")
        return read_fn(path, columns=list(cols), **kw)
    return call


def _duckdb_select(path, columns) -> pd.DataFrame:
    """SELECT the named columns, and nothing else, from a parquet file."""
    import duckdb
    for c in columns:
        if not str(c).replace("_", "").isalnum():
            raise ValueError(f"column name {c!r} is not a plain identifier")
    path = str(path)
    if "'" in path:
        raise ValueError("a path with a quote is refused")
    cols = ", ".join(columns)
    return duckdb.connect().execute(f"select {cols} from read_parquet('{path}')").df()


def _check_out(frame: pd.DataFrame, allowed: tuple[str, ...], what: str) -> pd.DataFrame:
    extra = sorted(set(frame.columns) - set(allowed) - {"geometry"})
    if extra:
        raise PermissionError(f"{what}: the reader returned columns {extra} outside the authorized list")
    return frame


def read_type_values(path=TERRITORY_LAYER, read_fn=None) -> list:
    """Access 1. The distinct values of TYPE, and nothing else (no geometry, no other field, no counts)."""
    if read_fn is None:
        import pyogrio
        read_fn = pyogrio.read_dataframe
    df = _guarded(read_fn, ACCESS_1_FIELDS, "access 1")(path, columns=ACCESS_1_FIELDS, read_geometry=False)
    df = _check_out(pd.DataFrame(df), ACCESS_1_FIELDS, "access 1")
    if "geometry" in df.columns:
        raise PermissionError("access 1 returned a geometry; it reads TYPE only")
    vals = pd.unique(df["TYPE"])
    return sorted(vals, key=lambda v: (v is None or (isinstance(v, float) and np.isnan(v)), str(v)))


def read_territories(path=TERRITORY_LAYER, read_fn=None):
    """Access 2. ID, TYPE and geometry, by a column list. Returns a GeoDataFrame with exactly ID, TYPE, geometry."""
    if read_fn is None:
        import pyogrio
        read_fn = pyogrio.read_dataframe
    gdf = _guarded(read_fn, ACCESS_2_FIELDS, "access 2")(path, columns=ACCESS_2_FIELDS)
    gdf = _check_out(gdf, ACCESS_2_FIELDS, "access 2")
    if list(gdf.columns) != list(ACCESS_2_FIELDS) + ["geometry"]:
        raise ValueError(f"access 2 returned columns {list(gdf.columns)}, expected {list(ACCESS_2_FIELDS)} + geometry")
    return gdf


def read_short_form(path=OPERATIONAL_MISC, read_fn=None) -> pd.DataFrame:
    """Access 3. The five columns, by a column list passed to the parquet reader; no schema or footer is printed.

    The default reader is duckdb with a SELECT of exactly those columns, as conditions.read_peaks reads the same file:
    pyarrow 19 refuses this file ("Repetition level histogram size mismatch", found 2026-11-19)."""
    if read_fn is None:
        read_fn = _duckdb_select
    df = _guarded(read_fn, ACCESS_3_COLUMNS, "access 3")(path, columns=ACCESS_3_COLUMNS)
    df = _check_out(df, ACCESS_3_COLUMNS, "access 3")
    if list(df.columns) != list(ACCESS_3_COLUMNS):
        raise ValueError(f"access 3 returned columns {list(df.columns)}, expected {list(ACCESS_3_COLUMNS)}")
    return df


def read_sites(path=FACILITIES) -> pd.DataFrame:
    """The inventory's site id and point (a permitted quantity file under data/interim)."""
    return pd.read_parquet(path, columns=list(FACILITY_COLUMNS))


def file_size_and_sha256(path) -> tuple[int, str]:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return Path(path).stat().st_size, h.hexdigest()


# =================================================================================================================
# Pure functions
# =================================================================================================================
def classify_type(value, mapping: dict[str, str] | None = None) -> str:
    """The class of one TYPE value under the mapping; a value not in it, or a missing value, is `ambiguous`."""
    mapping = TYPE_CLASS if mapping is None else mapping
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "ambiguous"
    cls = mapping.get(str(value), "ambiguous")
    if cls not in CLASSES:
        raise ValueError(f"mapping gives {value!r} the class {cls!r}, not one of {CLASSES}")
    return cls


def numeric_id(raw) -> int | None:
    """The layer's ID as an integer where it is all digits (as build_inventory reads it), else None."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    s = str(raw).strip()
    if s.isdigit():
        return int(s)
    if isinstance(raw, (int, np.integer)):
        return int(raw)
    return None


def polygon_incidence_full(sites: pd.DataFrame, territories, mapping: dict[str, str] | None = None) -> pd.DataFrame:
    """Every (site, polygon) pair where the polygon strictly contains the site's point, over every polygon in the layer.

    sites        fid, lat, lon (EPSG:4326); a site with a missing lat or lon has no point and no row.
    territories  GeoDataFrame with ID, TYPE, geometry (any CRS set on it).
    Returns fid, polygon (the polygon's row position in the layer), id_raw, utility_id_reported (nullable integer),
    TYPE, area (km2, EPSG:5070), type_class. The extra columns serve the summary; incidence_table() keeps the four."""
    import geopandas as gpd
    missing = [c for c in FACILITY_COLUMNS if c not in sites.columns]
    if missing:
        raise ValueError(f"sites lacks {missing}")
    if sites.fid.duplicated().any():
        raise ValueError("sites has a repeated fid")
    has_pt = sites.lat.notna() & sites.lon.notna()
    s = sites[has_pt]
    pts = gpd.GeoDataFrame({"fid": s.fid.values}, geometry=gpd.points_from_xy(s.lon, s.lat), crs=POINT_CRS)
    pts = pts.to_crs(EQUAL_AREA_CRS)
    terr = territories[list(ACCESS_2_FIELDS) + ["geometry"]].copy()
    terr["polygon"] = np.arange(len(terr))
    terr["geometry"] = terr.geometry.buffer(0)   # as build_inventory.assign_utility: repairs self-intersections
    terr = terr.to_crs(EQUAL_AREA_CRS)
    terr["polygon_km2"] = terr.geometry.area / 1e6
    j = gpd.sjoin(pts, terr[["polygon", "ID", "TYPE", "polygon_km2", "geometry"]], predicate="within", how="inner")
    # j["polygon_km2"], never j.area: on the joined frame .area is the POINT geometry's area, which is zero
    out = pd.DataFrame({"fid": j["fid"].values, "polygon": j["polygon"].values.astype(int), "id_raw": j["ID"].values,
                        "TYPE": j["TYPE"].values, "area": j["polygon_km2"].values.astype(float)})
    out["utility_id_reported"] = pd.array([numeric_id(v) for v in out.id_raw], dtype="Int64")
    out["type_class"] = [classify_type(v, mapping) for v in out.TYPE]
    return out.sort_values(["fid", "area", "polygon"]).reset_index(drop=True)


def incidence_table(full: pd.DataFrame) -> pd.DataFrame:
    """The table as written: exactly INCIDENCE_COLUMNS."""
    t = full[list(INCIDENCE_COLUMNS)].copy()
    t["utility_id_reported"] = t.utility_id_reported.astype("Int64")
    t["area"] = t.area.astype(float)
    t["type_class"] = t.type_class.astype(str)
    if tuple(t.columns) != INCIDENCE_COLUMNS:
        raise AssertionError(f"incidence columns {list(t.columns)} != {list(INCIDENCE_COLUMNS)}")
    bad = sorted(set(t.type_class) - set(CLASSES))
    if bad:
        raise ValueError(f"type_class values {bad} outside {CLASSES}")
    return t.reset_index(drop=True)


def typed_incidence_table(full: pd.DataFrame) -> pd.DataFrame:
    """The incidence with the layer's own TYPE value: exactly TYPED_INCIDENCE_COLUMNS (polygon is the polygon's row
    position in the layer as read). No other field of the layer is carried."""
    t = full[list(TYPED_INCIDENCE_COLUMNS)].copy()
    t["polygon"] = t.polygon.astype(int)
    t["utility_id_reported"] = t.utility_id_reported.astype("Int64")
    t["area"] = t.area.astype(float)
    t["TYPE"] = t.TYPE.astype(object).where(t.TYPE.notna(), None)
    if tuple(t.columns) != TYPED_INCIDENCE_COLUMNS:
        raise AssertionError(f"typed incidence columns {list(t.columns)} != {list(TYPED_INCIDENCE_COLUMNS)}")
    return t.reset_index(drop=True)


def same_incidence(rebuilt: pd.DataFrame, on_file: pd.DataFrame) -> list[str]:
    """Differences, in words, between the first table rebuilt from a new read and the table on file (empty if none).
    Rows are compared in the tables' own order (both sorted by fid, area, polygon) and areas to 1e-9 km2."""
    out = []
    if tuple(on_file.columns) != INCIDENCE_COLUMNS:
        return [f"the table on file has columns {list(on_file.columns)}, not {list(INCIDENCE_COLUMNS)}"]
    if len(rebuilt) != len(on_file):
        return [f"{len(rebuilt)} rows rebuilt against {len(on_file)} on file"]
    a, b = rebuilt.reset_index(drop=True), on_file.reset_index(drop=True)
    if not (a.fid.astype(str).values == b.fid.astype(str).values).all():
        out.append("fid differs in some row")
    ua, ub = a.utility_id_reported.astype("Int64"), b.utility_id_reported.astype("Int64")
    if not ((ua == ub).fillna(ua.isna() & ub.isna())).all():
        out.append("utility_id_reported differs in some row")
    if not np.allclose(a.area.astype(float).values, b.area.astype(float).values, rtol=0, atol=1e-9):
        out.append("area differs in some row")
    if not (a.type_class.astype(str).values == b.type_class.astype(str).values).all():
        out.append("type_class differs in some row")
    return out


def short_form_flags(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per unit and year from access 3's five columns; year from report_date. Exactly SHORT_FORM_COLUMNS."""
    missing = [c for c in ACCESS_3_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"the access 3 frame lacks {missing}")
    extra = sorted(set(raw.columns) - set(ACCESS_3_COLUMNS))
    if extra:
        raise PermissionError(f"the access 3 frame carries columns {extra} outside the authorized list")
    t = pd.DataFrame({"utility_id_eia": raw.utility_id_eia.values, "state": raw.state.values,
                      "year": pd.to_datetime(raw.report_date).dt.year.values,
                      "short_form": raw.short_form.values, "data_observed": raw.data_observed.values})
    t = t.sort_values(["utility_id_eia", "state", "year"], kind="mergesort").reset_index(drop=True)
    if tuple(t.columns) != SHORT_FORM_COLUMNS:
        raise AssertionError(f"short-form columns {list(t.columns)} != {list(SHORT_FORM_COLUMNS)}")
    return t


# ---- the two rules, used only to find the sites an ambiguous value would decide ------------------------------------
def _key(r) -> str:
    """A polygon's identity for comparing outcomes: its numeric id, or its raw id where non-numeric."""
    return str(int(r.utility_id_reported)) if pd.notna(r.utility_id_reported) else f"raw:{r.id_raw}"


def rule_u_outcome(polys: pd.DataFrame, classes: dict[int, str]) -> tuple:
    """Row U's rule for one site, as R5 adopted it (D-107): retail polygons first; the smallest retail polygon where
    several contain the site (an exact tie between different ids is reported as a tie, not broken); unassigned where
    only wholesale-only polygons contain it; no polygon, none. `classes` gives each polygon row's class, and must
    give retail or wholesale_only for every polygon (an ambiguous polygon is resolved by the caller, both ways)."""
    if polys.empty:
        return ("no_polygon",)
    cls = polys.polygon.map(classes)
    if cls.isna().any() or (~cls.isin(["retail", "wholesale_only"])).any():
        raise ValueError("rule_u_outcome needs every polygon classed retail or wholesale_only")
    retail = polys[cls.values == "retail"]
    if retail.empty:
        return ("unassigned_wholesale_only",)
    top = retail[retail.area == retail.area.min()]
    ids = tuple(sorted({_key(r) for r in top.itertuples()}))
    return ("assigned", ids[0]) if len(ids) == 1 else ("tie", ids)


def rule_c_outcome(polys: pd.DataFrame) -> tuple:
    """Row C's rule for one site: the smallest polygon over every territory in the layer, whatever its type."""
    if polys.empty:
        return ("no_polygon",)
    top = polys[polys.area == polys.area.min()]
    ids = tuple(sorted({_key(r) for r in top.itertuples()}))
    return ("assigned", ids[0]) if len(ids) == 1 else ("tie", ids)


def dependent_sites(full: pd.DataFrame, layer_values=None, mapping: dict[str, str] | None = None
                    ) -> dict[str, dict[str, list]]:
    """For each TYPE value classed ambiguous, the sites whose row U or row C outcome turns on its class.

    A site depends on value V under a rule if, for some classing (retail or wholesale-only) of the OTHER ambiguous
    values among its own polygons, classing V as retail and classing it as wholesale-only give different outcomes.
    Row C's rule does not read the type, so its lists are empty by construction; they are computed, not assumed.
    layer_values: every TYPE value in the layer, so that an ambiguous value no site falls in is listed with empty
    lists rather than left out."""
    out: dict[str, dict[str, list]] = {}
    amb_values = {str(v) for v, c in zip(full.TYPE, full.type_class) if c == "ambiguous"}
    if layer_values is not None:
        amb_values |= {str(v) for v in layer_values if classify_type(v, mapping) == "ambiguous"}
    amb_values = sorted(amb_values)
    for v in amb_values:
        out[v] = {"row_u": [], "row_c": []}
    for fid, g in full.groupby("fid", sort=True):
        g = g.reset_index(drop=True)
        amb_here = sorted({str(v) for v, c in zip(g.TYPE, g.type_class) if c == "ambiguous"})
        if not amb_here:
            continue
        fixed = {int(p): c for p, c, t in zip(g.polygon, g.type_class, g.TYPE) if c != "ambiguous"}
        if len(amb_here) > 16:
            raise ValueError(f"site {fid} has {len(amb_here)} ambiguous values; enumeration refused")
        for v in amb_here:
            others = [w for w in amb_here if w != v]
            dep_u = dep_c = False
            for combo in itertools.product(("retail", "wholesale_only"), repeat=len(others)):
                assign = dict(zip(others, combo))
                res = []
                for cv in ("retail", "wholesale_only"):
                    assign[v] = cv
                    classes = dict(fixed)
                    for p, c, t in zip(g.polygon, g.type_class, g.TYPE):
                        if c == "ambiguous":
                            classes[int(p)] = assign[str(t)]
                    res.append((rule_u_outcome(g, classes), rule_c_outcome(g)))
                dep_u |= res[0][0] != res[1][0]
                dep_c |= res[0][1] != res[1][1]
                if dep_u and dep_c:
                    break
            if dep_u:
                out[v]["row_u"].append(fid)
            if dep_c:
                out[v]["row_c"].append(fid)
    return out


def incidence_summary(sites: pd.DataFrame, territories, full: pd.DataFrame,
                      mapping: dict[str, str] | None = None) -> dict:
    """Quantity-only counts for the summary file. Layer ids are listed; no name or other field is."""
    has_pt = sites.lat.notna() & sites.lon.notna()
    per_site = full.groupby("fid").polygon.nunique()
    with_pt = set(sites.fid[has_pt])
    in_none = sorted(with_pt - set(per_site.index))
    ids = territories.ID
    nonnum_mask = np.array([numeric_id(v) is None for v in ids])
    nonnum_ids = sorted({str(v) for v in ids[nonnum_mask]})
    poly_class = pd.Series([classify_type(v, mapping) for v in territories.TYPE])
    nn_sites = full[full.utility_id_reported.isna()]
    num_ids = pd.Series([numeric_id(v) for v in ids]).dropna().astype(int)
    return {
        "sites": int(len(sites)),
        "sites_with_point": int(has_pt.sum()),
        "sites_without_point": sorted(sites.fid[~has_pt].tolist()),
        "sites_in_no_polygon": {"count": len(in_none), "fids": in_none},
        "sites_in_exactly_one_polygon": int((per_site == 1).sum()),
        "sites_in_several_polygons": int((per_site > 1).sum()),
        "incidence_rows": int(len(full)),
        "polygons_in_layer": int(len(territories)),
        "polygons_by_class": {c: int((poly_class == c).sum()) for c in CLASSES},
        "polygons_by_type_value": {str(k): int(v) for k, v in
                                   territories.TYPE.astype(object).where(territories.TYPE.notna(), "<missing>")
                                   .value_counts().sort_index().items()},
        "polygons_with_missing_or_empty_geometry": int((territories.geometry.isna() | territories.geometry.is_empty).sum()),
        "polygons_invalid_as_read": int((~territories.geometry.is_valid).sum()),
        "polygons_empty_after_buffer0_repair": int(territories.geometry.buffer(0).is_empty.sum()),
        "numeric_ids_appearing_on_more_than_one_polygon": int(num_ids.duplicated(keep=False).groupby(num_ids).any().sum()),
        "non_numeric_ids": {"count_of_polygons": int(nonnum_mask.sum()), "distinct_ids": nonnum_ids,
                            "incidence_rows_with_non_numeric_id": int(len(nn_sites)),
                            "sites_inside_a_non_numeric_id_polygon": sorted(set(nn_sites.fid))},
        "incidence_rows_by_class": {c: int((full.type_class == c).sum()) for c in CLASSES},
    }


# =================================================================================================================
# main
# =================================================================================================================
def short_form_summary(t: pd.DataFrame) -> dict:
    def counts(col):
        x = t[col].astype(object).where(t[col].notna(), "<missing>").astype(str)
        tab = pd.crosstab(t.year, x)
        return {str(int(y)): {str(k): int(v) for k, v in row.items() if v} for y, row in tab.iterrows()}
    dup = t.duplicated(["utility_id_eia", "state", "year"], keep=False)
    return {"rows": int(len(t)), "years": [int(t.year.min()), int(t.year.max())] if len(t) else [],
            "units": int(t[["utility_id_eia", "state"]].drop_duplicates().shape[0]),
            "rows_sharing_unit_and_year_with_another_row": int(dup.sum()),
            "unit_years_with_more_than_one_row": [
                {"utility_id_eia": int(k[0]), "state": str(k[1]), "year": int(k[2]), "rows": int(n),
                 "short_form_values": sorted({str(v) for v in g.short_form.astype(object).where(g.short_form.notna(), "<missing>")}),
                 "data_observed_values": sorted({str(v) for v in g.data_observed})}
                for k, g in t[dup].groupby(["utility_id_eia", "state", "year"], sort=True) for n in [len(g)]],
            "kept_as_found": "rows sharing a unit and year are all kept in the table, not collapsed; the consumer decides",
            "short_form_values": sorted({str(v) for v in t.short_form.astype(object).where(t.short_form.notna(), "<missing>")}),
            "short_form_by_year": counts("short_form"),
            "data_observed_by_year": counts("data_observed")}


def main() -> int:
    if not TYPE_CLASS:
        raise SystemExit("TYPE_CLASS is empty: access 1 and the mapping come first")
    size, sha = file_size_and_sha256(TERRITORY_LAYER)
    terr = read_territories()
    sites = read_sites()
    full = polygon_incidence_full(sites, terr)
    table = incidence_table(full)
    OUT_INCIDENCE.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(OUT_INCIDENCE, index=False)
    deps = dependent_sites(full, layer_values=pd.unique(terr.TYPE))
    row_c = {fid: rule_c_outcome(g) for fid, g in full.groupby("fid", sort=True)}
    sf = short_form_flags(read_short_form())
    sf.to_parquet(OUT_SHORT_FORM, index=False)
    summary = {
        "what_this_is": ("Quantity-only summary of the polygon incidence table and the Short Form flags table built "
                         "for reconciliation rows U and C (R4 accesses 1 to 3, D-107). PROVISIONAL: the design stands "
                         "as of 2026-11-18 and the pre-analysis plan is a DRAFT, not frozen. No price, revenue or bill "
                         "was read. The TYPE mapping is the agent's reading, not a ruling."),
        "written_by": "pipeline/analysis/reconciliation_inputs.py main(), 2026-11-19 (session 21, job 4)",
        "territory_layer": {"path": str(TERRITORY_LAYER.relative_to(ROOT)), "size_bytes": size, "sha256": sha,
                            "fields_read": list(ACCESS_2_FIELDS) + ["geometry"],
                            "note": "in no fetch manifest; size and hash recorded as found on 2026-11-19"},
        "incidence_table": {"path": str(OUT_INCIDENCE.relative_to(ROOT)), "columns": list(INCIDENCE_COLUMNS),
                            "rows": int(len(table)), "area_units": AREA_UNITS, "containment": CONTAINMENT,
                            "sites_source": "data/interim/facilities.parquet fid, lat, lon (every row, crypto included)"},
        "type_mapping_agents_reading": {k: {"class": TYPE_CLASS[k], "why": TYPE_CLASS_REASON.get(k, "")}
                                        for k in sorted(TYPE_CLASS)},
        "counts": incidence_summary(sites, terr, full),
        "ambiguous_values_and_the_sites_they_would_decide": {
            "rule_u": ("retail polygons first; the smallest retail polygon where several contain the site; unassigned "
                       "where only wholesale-only polygons contain it (R5 as adopted, D-107)"),
            "rule_c": "the smallest polygon over every territory in the layer, whatever its type",
            "by_value": {v: {"row_u_count": len(d["row_u"]), "row_u_fids": d["row_u"],
                             "row_c_count": len(d["row_c"]), "row_c_fids": d["row_c"]} for v, d in deps.items()},
            "sites_any_ambiguous_value_decides_under_row_u": sorted({f for d in deps.values() for f in d["row_u"]}),
            "row_c_rule_outcomes": {"assigned": sum(o[0] == "assigned" for o in row_c.values()),
                                    "tie_in_area_not_broken": {fid: list(o[1]) for fid, o in row_c.items()
                                                               if o[0] == "tie"}}},
        "short_form_flags": {"path": str(OUT_SHORT_FORM.relative_to(ROOT)), "columns": list(SHORT_FORM_COLUMNS),
                             "source_columns_read": list(ACCESS_3_COLUMNS), **short_form_summary(sf)},
        "notes": [
            "Whether the short_form flag in core_eia861__yearly_operational_data_misc is what Ryu and Hiatt mean by "
            "Short Form filers (endnote 10, p. 17) is NOT established; nothing here asserts it.",
            "These are filing flags, not prices.",
            "short_form is True on 1,038 rows, all in 2019, and missing on every other row; it is never False. Rows per "
            "year fall from about 3,270 in 2011 to about 2,190 in 2012. The agent's reading, not established: utilities "
            "that filed the Short Form may be absent from this table in most years rather than flagged, so a missing "
            "flag cannot be read as 'not a Short Form filer'. reconciliation_mu.run_u_step refuses a missing short_form "
            "for an outcome unit-year, so it would refuse this table as it stands; how to read a missing flag or an "
            "absent row is not decided here.",
            "An ambiguous TYPE value is carried as ambiguous; nothing here treats it as retail or as wholesale-only.",
        ],
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({"incidence_rows": len(table), "short_form_rows": len(sf), "summary": str(OUT_SUMMARY)}))
    return 0


def main_types() -> int:
    """The repeat read (D-109): access 2 once (ID, TYPE, geometry), the first table's four columns checked against the
    table on file, then the typed table written. Nothing else under data/raw is read; the layer is not hashed."""
    terr = read_territories(TERRITORY_LAYER)        # the one read: ID, TYPE and geometry, by the fixed column list
    sites = read_sites(FACILITIES)
    full = polygon_incidence_full(sites, terr)
    diffs = same_incidence(incidence_table(full), pd.read_parquet(OUT_INCIDENCE))
    if diffs:
        raise SystemExit("the rebuilt incidence differs from data/interim/reconciliation_polygon_incidence.parquet ("
                         + "; ".join(diffs) + "); nothing written")
    typed = typed_incidence_table(full)
    typed.to_parquet(OUT_TYPED_INCIDENCE, index=False)
    print(json.dumps({"layer_reads": 1, "fields_read": list(ACCESS_2_FIELDS) + ["geometry"],
                      "typed_incidence_rows": len(typed), "first_table_matches": True,
                      "path": (str(OUT_TYPED_INCIDENCE.relative_to(ROOT)) if OUT_TYPED_INCIDENCE.is_relative_to(ROOT)
                               else str(OUT_TYPED_INCIDENCE))}))
    return 0


if __name__ == "__main__":
    sys.exit(main_types() if sys.argv[1:] == ["--types-only"] else main())
