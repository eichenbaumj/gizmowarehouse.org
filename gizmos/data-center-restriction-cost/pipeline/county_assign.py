"""County assignment + aggregation for the map's county friction layer.

Every local action row gets a county via point-in-polygon against the
Census county/equivalents file already in the repo (medicaid-counties.geojson,
49 states — no AK/HI, so Anchorage is an accepted miss rendered as a point).
Counties then aggregate to one display category each, precedence:

    live county-wide restriction > live town-level restriction >
    live conditions > pending only > lapsed only

"live" = status in LIVE_STATUSES ({enacted, in_force}). The emitted
counties.geojson carries only counties with at least one assigned action,
coordinates rounded to 4 decimals (~11 m), so the payload stays small.

The frontend re-derives display categories client-side (so the
community-rows toggle re-shades consistently); verify_claims.py recomputes
this module's default aggregation independently and fails on drift.
"""

from __future__ import annotations

import json

import config
import geocode as geomod

LIVE_STATUSES = {"enacted", "in_force"}
LAPSED_STATUSES = {"expired", "replaced"}

# Properties copied from the source county file (medicaid-specific props dropped).
_KEEP_PROPS = ("GEOID", "state_fips", "state_abbr", "county_name")


class CountyFeat:
    __slots__ = ("props", "polys", "bbox")

    def __init__(self, props, polys, bbox):
        self.props = props
        self.polys = polys  # list of polygons; each polygon = list of rings
        self.bbox = bbox


def _rings(geometry):
    t = geometry["type"]
    if t == "Polygon":
        return [geometry["coordinates"]]
    if t == "MultiPolygon":
        return geometry["coordinates"]
    return []


def load_county_features():
    doc = json.loads(config.COUNTIES_GEOJSON.read_text())
    feats = []
    for f in doc["features"]:
        polys = _rings(f["geometry"])
        if not polys:
            continue
        xs = [pt[0] for poly in polys for ring in poly for pt in ring]
        ys = [pt[1] for poly in polys for ring in poly for pt in ring]
        props = {k: f["properties"].get(k) for k in _KEEP_PROPS}
        feats.append(CountyFeat(props, polys, (min(xs), min(ys), max(xs), max(ys))))
    return feats


def _ray_cast(x, y, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _in_polygon(x, y, poly):
    # First ring is the shell; the rest are holes.
    if not _ray_cast(x, y, poly[0]):
        return False
    for hole in poly[1:]:
        if _ray_cast(x, y, hole):
            return False
    return True


def point_in_county(lon, lat, feats):
    for f in feats:
        bx0, by0, bx1, by1 = f.bbox
        if not (bx0 <= lon <= bx1 and by0 <= lat <= by1):
            continue
        for poly in f.polys:
            if _in_polygon(lon, lat, poly):
                return f
    return None


def nearest_county(lon, lat, feats, state_abbr, max_deg=0.12):
    """Fallback for simplification slivers: nearest in-state vertex within
    ~12 km. Restricted to the row's own state (a border sliver must not cross
    into the neighboring state's county); the radius is loose enough for
    border cities whose simplified county edge misses them (Bristol, TN)."""
    best, best_d2 = None, max_deg * max_deg
    for f in feats:
        if f.props.get("state_abbr") != state_abbr:
            continue
        bx0, by0, bx1, by1 = f.bbox
        if not (bx0 - max_deg <= lon <= bx1 + max_deg and by0 - max_deg <= lat <= by1 + max_deg):
            continue
        for poly in f.polys:
            for pt in poly[0]:
                d2 = (pt[0] - lon) ** 2 + (pt[1] - lat) ** 2
                if d2 < best_d2:
                    best, best_d2 = f, d2
    return best


# Consolidated city-county governments: a city action IS county-wide.
_CONSOLIDATED_PREFIXES = ("indianapolis", "nashville", "lexington", "louisville",
                          "jacksonville", "philadelphia", "san francisco", "denver")


def is_county_wide(row, county_props):
    """Does this action bind the whole county (or county-equivalent)?

    True when the acting government IS the county: typed county; named so the
    jurisdiction string STARTS with the county's name and says County/Parish
    (catches "Maricopa County Board of Supervisors" typed municipality, while
    excluding "Calipatria, Imperial County" — a city with its county appended);
    a county-equivalent independent city (VA-style) whose polygon is the city;
    or a known consolidated city-county (Indianapolis/Marion etc.).
    """
    if row["jurisdiction_type"] == "county":
        return True, None
    jur_norm = geomod.norm_county(row["jurisdiction"])
    county_norm = geomod.norm_county(county_props["county_name"] or "")
    says_county = "county" in row["jurisdiction"].lower() or "parish" in row["jurisdiction"].lower()
    if county_norm and says_county and jur_norm.startswith(county_norm):
        return True, "county-named authority typed as municipality"
    # County-equivalent independent cities: the polygon IS the city.
    cn = (county_props["county_name"] or "").lower()
    if cn.endswith(" city") and geomod.norm_place(row["jurisdiction"]).startswith(geomod.norm_place(cn[:-5])):
        return True, "county-equivalent independent city"
    if jur_norm.startswith(_CONSOLIDATED_PREFIXES):
        return True, "consolidated city-county"
    return False, None


def assign_counties(local_actions, feats, log):
    log.setdefault("county_assign_misses", [])
    log.setdefault("county_wide_promotions", [])
    log.setdefault("county_assign_nearest", [])
    for a in local_actions:
        if a["lat"] is None or a["lon"] is None:
            a["county_fips"] = None
            a["county_name"] = None
            a["county_wide"] = False
            a["county_assign"] = "none"
            log["county_assign_misses"].append(
                {"id": a["id"], "state": a["state"], "jurisdiction": a["jurisdiction"], "why": "no coordinates"})
            continue
        f = point_in_county(a["lon"], a["lat"], feats)
        prov = "pip"
        # A point that lands in the wrong state's county (border coordinates,
        # simplified polygons) is treated as a miss and re-resolved in-state.
        if f is not None and f.props.get("state_abbr") != a["state"]:
            f = None
        if f is None:
            f = nearest_county(a["lon"], a["lat"], feats, a["state"])
            prov = "nearest_boundary"
            if f is not None:
                log["county_assign_nearest"].append(
                    {"id": a["id"], "assigned": f.props["GEOID"], "county": f.props["county_name"]})
        if f is None:
            a["county_fips"] = None
            a["county_name"] = None
            a["county_wide"] = a["jurisdiction_type"] == "county"
            a["county_assign"] = "none"
            log["county_assign_misses"].append(
                {"id": a["id"], "state": a["state"], "jurisdiction": a["jurisdiction"], "why": "outside all polygons"})
            continue
        wide, promo = is_county_wide(a, f.props)
        if promo:
            log["county_wide_promotions"].append({"id": a["id"], "why": promo, "county": f.props["county_name"]})
        a["county_fips"] = f.props["GEOID"]
        a["county_name"] = f.props["county_name"]
        a["county_wide"] = wide
        a["county_assign"] = prov


def aggregate_counties(local_actions):
    """Default-view (in-force, all datasets) category per county GEOID."""
    by_county = {}
    for a in local_actions:
        if not a.get("county_fips"):
            continue
        by_county.setdefault(a["county_fips"], []).append(a)

    out = {}
    for geoid, rows in by_county.items():
        live = [r for r in rows if r["status"] in LIVE_STATUSES]
        pending = [r for r in rows if r["status"] == "pending"]
        lapsed = [r for r in rows if r["status"] in LAPSED_STATUSES]
        live_restr = [r for r in live if r["class"] == "restriction"]
        live_cond = [r for r in live if r["class"] == "condition"]
        if any(r["county_wide"] for r in live_restr):
            cat = "county_restriction"
        elif live_restr:
            cat = "town_restriction"
        elif live_cond:
            cat = "conditions_only"
        elif pending:
            cat = "pending_only"
        else:
            cat = "lapsed_only"
        out[geoid] = {
            "category": cat,
            "n_total": len(rows),
            "n_live": len(live),
            "n_pending": len(pending),
            "n_lapsed": len(lapsed),
            "n_live_county_restriction": sum(1 for r in live_restr if r["county_wide"]),
            "n_live_town_restriction": sum(1 for r in live_restr if not r["county_wide"]),
            "n_live_conditions": len(live_cond),
            "action_ids": [r["id"] for r in rows],
        }
    return out


def _round_geom(geometry, nd=4):
    def rr(ring):
        return [[round(pt[0], nd), round(pt[1], nd)] for pt in ring]

    t = geometry["type"]
    if t == "Polygon":
        return {"type": "Polygon", "coordinates": [rr(r) for r in geometry["coordinates"]]}
    return {"type": "MultiPolygon",
            "coordinates": [[rr(r) for r in poly] for poly in geometry["coordinates"]]}


def write_counties_geojson(summaries):
    doc = json.loads(config.COUNTIES_GEOJSON.read_text())
    features = []
    for f in doc["features"]:
        geoid = f["properties"].get("GEOID")
        s = summaries.get(geoid)
        if not s:
            continue
        props = {k: f["properties"].get(k) for k in _KEEP_PROPS}
        props.update(s)
        features.append({"type": "Feature", "geometry": _round_geom(f["geometry"]), "properties": props})
    out = {"type": "FeatureCollection", "snapshot_date": config.SNAPSHOT_DATE, "features": features}
    config.COUNTIES_OUT_JSON.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    return len(features)
