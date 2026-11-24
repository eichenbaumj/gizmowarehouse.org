#!/usr/bin/env python3
"""The precision fields of the verification pass's layer records (docs/DECISIONS.md, D-65 item 2; D-66 section 5).

For every site in `verified/pass_c_layer_conditions.csv` and every territory layer on file for it that is an ArcGIS
REST layer, this records:

  1. the location and its uncertainty: the record's point, how it is tied to the facility, the distance from the
     inventory's point already on file and, where the record's parcel query can return the parcel's outline, the
     greatest distance from the point to that outline's vertices ("parcel extent": the parcel's size, not a survey
     accuracy). A location not tied to a parcel has uncertainty "unknown";
  2. what the layer returns at the point (object ids and a readable name);
  3. the distance to the nearest drawn line, found WITHOUT downloading territory geometry: 32-sided discs around the
     point are put to the layer with two questions (which features touch the disc; which features contain the whole
     disc). The relation that means "the feature contains the query geometry" is calibrated on each layer with a 1 m
     disc (esriSpatialRelWithin, then esriSpatialRelContains); if neither returns the at-point set, the intersects
     question is used alone and the row says the feature's own edge and holes were not tested. Radii 25 m to 20 km;
     the bracket is halved four times. Beyond 20 km: "more than 20 km";
  4. every name the layer returns within 5 km (`--radius-km`);
  5. conflicting geometry: what each of the site's layers returns at the point and where each changes, side by side.
     Different spellings are not judged here: names that differ are flagged "names differ; to be read";
  6. the publisher's own statements: the layer's, its service's and its catalog item's description, licence and
     access texts, fetched again and kept word for word (HTML tags stripped) in a sidecar JSON; the CSV quotes, verbatim,
     the sentences that speak to positional accuracy and to completeness, or says nothing was found.

Every request is appended to the request log in the format of `leads/pass_c_layers_L1_log.csv`. Only URLs on file in
the four layer files are fetched (layer, service root, catalog item, parcel layer), with query parameters. Plain
urllib, a generic User-Agent, 0.25 s between requests, a timeout, two retries. Nothing under data/ is read.

Run from the gizmo folder:
    python3 -I pipeline/facilities/pass_c_precision.py
    python3 -I pipeline/facilities/pass_c_precision.py --sites bi:837-0,bi:821-0 --out T.csv --log T-log.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import html
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent              # pipeline/facilities
ROOT = HERE.parents[1]                              # the gizmo folder
CONDITIONS = HERE / "verified" / "pass_c_layer_conditions.csv"
LAYER_FILES = [HERE / "leads" / f"pass_c_layers_{n}.json" for n in ("L1", "L2", "L3", "added")]
OUT_CSV = HERE / "verified" / "pass_c_layer_precision.csv"
OUT_PUBLISHERS = HERE / "verified" / "pass_c_layer_publishers.json"
OUT_LOG = HERE / "leads" / "pass_c_precision_log.csv"

USER_AGENT = "research-script/1.0 (urllib)"
PAUSE_S = 0.25
TIMEOUT_S = 45
RETRIES = 2
EARTH_R = 6371008.8                                  # mean Earth radius, metres
DISC_SIDES = 32
RADII = [25, 50, 100, 250, 500, 1000, 2000, 5000, 10000, 20000]
HALVINGS = 4
CALIBRATION_R = 1.0
REL_INTERSECTS = "esriSpatialRelIntersects"
CONTAINS_CANDIDATES = ["esriSpatialRelWithin", "esriSpatialRelContains"]

ROUND = "D-66 precision"
WHO = "pass_c_precision.py, run by the session"
LOG_COLUMNS = ["date", "target", "round", "who", "avenue", "query_or_url", "result", "note"]

LIMITATION = ("Agreeing probes and a large distance are recorded and prove nothing about the layer's accuracy, which is "
              "unknown. The distance is to the line as drawn, not to the true boundary.")
NOTHING_FOUND = "the publisher says nothing found on this"
NOT_TESTED = "the feature's own edge and holes were not tested"

COLUMNS = ["site", "layer_publisher", "layer_name", "layer_url", "location_basis", "lat", "lon",
           "metres_from_the_inventory_point", "parcel_extent_m", "location_uncertainty", "at_point",
           "nearest_line_m_low", "nearest_line_m_high", "what_changes_there", "relation_used_for_contains",
           "names_within_5km", "conflicting_geometry", "statements_on_accuracy", "statements_on_completeness",
           "limitation", "queried_on"]

TEXT_KEYS = ["description", "serviceDescription", "snippet", "copyrightText", "licenseInfo", "accessInformation"]
ACCURACY_WORDS = ["accura", "precis", "approximat", "generaliz", "generalis", "survey", "scale", "error",
                  "not intended", "legal", "official", "disclaim", r"\bas is\b", "as-is",
                  # beyond the brief's list (its "words like"): Collin County's and HIFLD's own wording
                  "illustrative", "boundary dispute", "limitation"]
COMPLETENESS_WORDS = ["complete", "all utilities", "missing", "coverage", "overlap", r"\bgaps?\b", "updated", "current"]

LAYER_RE = re.compile(r"^https?://[^?#\s]+/(FeatureServer|MapServer)/\d+$", re.I)
ITEM_RE = re.compile(r"https?://[^\s;'\"()<>]+?/sharing/rest/content/items/[0-9a-fA-F]{32}")
TIED = {"address", "owner", "address and owner"}


# --------------------------------------------------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def disc_ring(lat: float, lon: float, radius_m: float, sides: int = DISC_SIDES) -> list[list[float]]:
    """A closed ring of `sides` vertices [lon, lat] at `radius_m` around the point.

    Metres become degrees with a local equirectangular approximation (dlat = d/R; dlon = d/(R cos lat)). The ring runs
    clockwise (north, east, south, west), which is the outer-ring orientation ArcGIS expects.
    """
    ring = []
    coslat = math.cos(math.radians(lat))
    for k in range(sides):
        t = 2 * math.pi * k / sides
        dlat = math.degrees(radius_m * math.cos(t) / EARTH_R)
        dlon = math.degrees(radius_m * math.sin(t) / (EARTH_R * coslat))
        ring.append([round(lon + dlon, 8), round(lat + dlat, 8)])
    ring.append(list(ring[0]))
    return ring


def disc_geometry(lat: float, lon: float, radius_m: float) -> str:
    return json.dumps({"rings": [disc_ring(lat, lon, radius_m)], "spatialReference": {"wkid": 4326}},
                      separators=(",", ":"))


def web_mercator_to_lonlat(x: float, y: float) -> tuple[float, float]:
    r = 6378137.0
    return math.degrees(x / r), math.degrees(2 * math.atan(math.exp(y / r)) - math.pi / 2)


def point_in_rings(lon: float, lat: float, rings: list) -> bool:
    """Even-odd rule over every ring (holes included)."""
    inside = False
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i][0], ring[i][1]
            x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
            if (y1 > lat) != (y2 > lat):
                x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
                if x > lon:
                    inside = not inside
    return inside


def parse_point_param(url: str | None) -> tuple[float, float] | None:
    """(lat, lon) from a query URL's `geometry=lon,lat` point parameter, if it has one."""
    if not url:
        return None
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    g = (qs.get("geometry") or [""])[0]
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", g)
    if not m:
        return None
    return float(m.group(2)), float(m.group(1))


# --------------------------------------------------------------------------------------------------------------------
# Publisher text
# --------------------------------------------------------------------------------------------------------------------

def strip_html(text: str) -> str:
    """Tags removed, entities decoded, whitespace collapsed; block ends become line breaks. Words are not touched."""
    if not text:
        return ""
    t = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", str(text))
    t = re.sub(r"(?i)</\s*(p|div|li|h[1-6]|tr)\s*>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t).replace("\xa0", " ")
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in t.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def sentences(text: str) -> list[str]:
    out = []
    for line in text.split("\n"):
        for s in re.split(r"(?<=[.!?])\s+(?=[\"'(\[A-Z0-9])", line):
            s = s.strip()
            if s:
                out.append(s)
    return out


def _matches(sentence: str, words: list[str]) -> bool:
    low = sentence.lower()
    return any(re.search(w, low) if w.startswith("\\b") else (w in low) for w in words)


def extract_statements(texts: list[tuple[str, str]], words: list[str]) -> str:
    """`texts` is [(source label, stripped text)]. Returns the matching sentences verbatim, each with its source label,
    joined by " | ", or the fixed nothing-found wording."""
    seen, parts = set(), []
    for label, text in texts:
        for s in sentences(text):
            if _matches(s, words) and s not in seen:
                seen.add(s)
                parts.append(f'{label}: "{s}"')
    return " | ".join(parts) if parts else NOTHING_FOUND


# --------------------------------------------------------------------------------------------------------------------
# Fetching and logging
# --------------------------------------------------------------------------------------------------------------------

@dataclass
class Response:
    status: int | None
    data: dict | None
    error: str | None = None


def build_request(url: str) -> urllib.request.Request:
    """The only headers sent: a generic User-Agent and Accept. Nothing personal or project-identifying."""
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})


class HttpFetcher:
    def __init__(self, pause: float = PAUSE_S, timeout: float = TIMEOUT_S, retries: int = RETRIES):
        self.pause, self.timeout, self.retries = pause, timeout, retries

    def get(self, url: str) -> Response:
        last = Response(None, None, "not attempted")
        for attempt in range(self.retries + 1):
            time.sleep(self.pause)
            try:
                with urllib.request.urlopen(build_request(url), timeout=self.timeout) as r:
                    body = r.read()
                    status = r.status
            except urllib.error.HTTPError as e:
                last = Response(e.code, None, f"HTTP {e.code}")
                if e.code in (400, 401, 403, 404, 405, 498, 499):
                    return last                        # a refusal or a bad request: not retried, not worked around
                continue
            except Exception as e:                     # timeouts, resets, DNS
                last = Response(None, None, f"{type(e).__name__}: {e}"[:200])
                continue
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
            except ValueError:
                return Response(status, None, f"HTTP {status}, not JSON")
            if isinstance(data, dict) and isinstance(data.get("error"), dict):
                code = data["error"].get("code")
                msg = str(data["error"].get("message") or "")[:150]
                last = Response(status, None, f"ArcGIS error {code}: {msg}")
                if code in (400, 401, 403, 404, 498, 499):
                    return last
                continue
            return Response(status, data if isinstance(data, dict) else {"_list": data})
        return last


class Requester:
    """Wraps a fetcher; logs every request (appended and flushed one row at a time) and counts them."""

    def __init__(self, fetcher, log_path: Path, today: str):
        self.fetcher, self.log_path, self.today = fetcher, Path(log_path), today
        self.n_requests = self.n_errors = 0
        self.urls: list[str] = []
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.log_path.exists() or self.log_path.stat().st_size == 0
        self._fh = open(self.log_path, "a", newline="", encoding="utf-8")
        self._w = csv.writer(self._fh)
        if new:
            self._w.writerow(LOG_COLUMNS)
            self._fh.flush()

    def close(self):
        self._fh.close()

    def get(self, url: str, target: str, note: str, empty_if=None) -> Response:
        resp = self.fetcher.get(url)
        self.n_requests += 1
        self.urls.append(url)
        if resp.error or resp.data is None:
            self.n_errors += 1
            result = "error " + (f"HTTP {resp.status}" if resp.status else "no HTTP status") + \
                     (f" ({resp.error})" if resp.error and not resp.error.startswith("HTTP") else "")
        elif empty_if is not None and empty_if(resp.data):
            result = "empty"
        else:
            result = "found"
        self._w.writerow([self.today, target, ROUND, WHO, "map", url, result, note])
        self._fh.flush()
        return resp


def make_url(base: str, params: dict) -> str:
    return base + "?" + urllib.parse.urlencode(params)


# --------------------------------------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------------------------------------

@dataclass
class Layer:
    publisher: str
    layer_name: str
    layer_url: str
    query_url: str | None
    returned: list
    fields: dict

    @property
    def queryable(self) -> bool:
        return bool(LAYER_RE.match(self.layer_url or ""))


@dataclass
class Site:
    fid: str
    lat: float | None
    lon: float | None
    tie: str
    metres: str
    parcel_query: str | None
    parcel_layer: str | None
    parcel_desc: str
    situs: str
    layers: list[Layer] = field(default_factory=list)
    note: str = ""


def load_conditions(path: Path = CONDITIONS) -> list[str]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [r["site"] for r in csv.DictReader(fh)]


def load_records(paths=LAYER_FILES) -> tuple[dict, dict, dict]:
    """Returns ({fid: raw record}, {layer_url: [item URLs on file]}, {layer_url: (publisher, layer_name)})."""
    recs, items, names = {}, {}, {}
    for p in paths:
        for r in json.loads(Path(p).read_text(encoding="utf-8")):
            recs[r["fid"]] = r
            for b in r.get("b_layers") or []:
                if isinstance(b, dict) and b.get("layer_url"):
                    names.setdefault(b["layer_url"], (b.get("publisher") or "", b.get("layer_name") or ""))
            for c in r.get("c_coverage") or []:
                lu = c.get("layer_url")
                if not lu:
                    continue
                for m in ITEM_RE.findall(str(c.get("description_url") or "")):
                    items.setdefault(lu, [])
                    if m not in items[lu]:
                        items[lu].append(m)
    return recs, items, names


def normalize(fid: str, rec: dict | None, layer_names: dict) -> Site:
    if rec is None:
        return Site(fid, None, None, "", "", None, None, "", "",
                    note="no record for this site in the four layer files on file (leads/pass_c_layers_*.json)")
    a = rec.get("a_coordinates")
    if isinstance(a, dict):
        layers = [Layer(b.get("publisher") or "", b.get("layer_name") or "", b.get("layer_url") or "",
                        b.get("query_url"), list(b.get("returned") or []),
                        b.get("fields") if isinstance(b.get("fields"), dict) else {})
                  for b in rec.get("b_layers") or [] if isinstance(b, dict)]
        pq = a.get("query_url")
        return Site(fid, a.get("point_lat"), a.get("point_lon"), str(a.get("tied_to_facility_by") or ""),
                    "" if a.get("metres_from_inventory_point") is None else str(a.get("metres_from_inventory_point")),
                    pq, a.get("parcel_layer_url"), str(a.get("parcel_id") or ""), str(a.get("situs_address") or ""),
                    layers)
    # The expansion test's format (pass_c_layers_added.json): the point is the queries' geometry; no tie is stated.
    urls = rec.get("urls") or {}
    pt = parse_point_param(rec.get("parcel_query")) or next(
        (p for p in (parse_point_param(u) for u in urls.values()) if p), None)
    layers = []
    for kind, u in urls.items():
        lu = u.split("/query")[0]
        pub, lname = layer_names.get(lu, ("", ""))
        layers.append(Layer(pub or "not stated in the record", lname or kind, lu, u,
                            list((rec.get("point") or {}).get(kind) or []), {}))
    return Site(fid, pt[0] if pt else None, pt[1] if pt else None, "not stated in the record", "",
                rec.get("parcel_query"), None, "; ".join(rec.get("parcel") or []), "", layers)


# --------------------------------------------------------------------------------------------------------------------
# The measurements
# --------------------------------------------------------------------------------------------------------------------

def _ci(d: dict, key: str):
    if key in d:
        return d[key]
    for k, v in d.items():
        if k.lower() == key.lower():
            return v
    return None


class LayerProbe:
    """Queries one layer around one point. All queries ask for ids and one name field only, never geometry."""

    def __init__(self, req: Requester, layer: Layer, meta: dict, target: str, lat: float, lon: float):
        self.req, self.layer, self.meta, self.target, self.lat, self.lon = req, layer, meta, target, lat, lon
        self.base = layer.layer_url + "/query"
        fields = meta.get("fields") or []
        self.oid = meta.get("objectIdField") or next(
            (f["name"] for f in fields if f.get("type") == "esriFieldTypeOID"), "OBJECTID")
        self.name_field = choose_name_field(meta, layer)
        self.names: dict = {}
        self._cache: dict = {}

    def _params(self, geometry: str, gtype: str, rel: str) -> dict:
        out = self.oid if not self.name_field or self.name_field.lower() == self.oid.lower() \
            else f"{self.oid},{self.name_field}"
        return {"geometry": geometry, "geometryType": gtype, "inSR": "4326", "spatialRel": rel,
                "outFields": out, "returnGeometry": "false", "f": "json"}

    def _run(self, params: dict, note: str) -> frozenset:
        url = make_url(self.base, params)
        resp = self.req.get(url, self.target, note, empty_if=lambda d: not d.get("features"))
        if resp.data is None:
            raise QueryError(f"{note}: {resp.error or 'no data'} ({url[:120]}...)")
        ids = set()
        for f in resp.data.get("features") or []:
            attrs = f.get("attributes") or {}
            oid = _ci(attrs, self.oid)
            if oid is None:
                oid = json.dumps(attrs, sort_keys=True)
            ids.add(oid)
            nm = _ci(attrs, self.name_field) if self.name_field else None
            self.names[oid] = "" if nm is None else str(nm)
        return frozenset(ids)

    def at_point(self) -> frozenset:
        if "point" not in self._cache:
            self._cache["point"] = self._run(self._params(f"{self.lon},{self.lat}", "esriGeometryPoint",
                                                          REL_INTERSECTS), "point")
        return self._cache["point"]

    def disc(self, rel: str, r: float) -> frozenset:
        key = (rel, round(r, 3))
        if key not in self._cache:
            short = "intersects" if rel == REL_INTERSECTS else f"contains({rel.replace('esriSpatialRel', '')})"
            self._cache[key] = self._run(self._params(disc_geometry(self.lat, self.lon, r), "esriGeometryPolygon", rel),
                                         f"{short} r={_fmt(r)}")
        return self._cache[key]

    def label(self, ids) -> str:
        if not ids:
            return "nothing"
        parts = []
        for i in sorted(ids, key=str):
            nm = self.names.get(i, "")
            parts.append(f"'{nm}' ({self.oid} {i})" if nm else f"({self.oid} {i})")
        return "; ".join(parts)

    def name_set(self, ids) -> list[str]:
        return sorted({self.names.get(i, "") or f"({self.oid} {i})" for i in ids})


class QueryError(Exception):
    pass


def choose_name_field(meta: dict, layer: Layer) -> str | None:
    fields = meta.get("fields") or []
    strings = {f["name"].lower(): f["name"] for f in fields if f.get("type") == "esriFieldTypeString"}
    saved = []
    if layer.query_url:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(layer.query_url).query)
        saved = [s.strip() for s in (qs.get("outFields") or [""])[0].split(",") if s.strip()]
    for s in saved:
        if s.lower() in strings:
            return strings[s.lower()]
    df = meta.get("displayField")
    if df and df.lower() in strings:
        return strings[df.lower()]
    for s in layer.fields:
        if s.lower() in strings:
            return strings[s.lower()]
    return next(iter(strings.values()), None)


def calibrate(probe: LayerProbe, at_point: frozenset) -> tuple[str | None, str]:
    """Find the spatialRel under which, for a 1 m disc, the server returns the features containing the disc: the
    at-point set. Tried in order: esriSpatialRelWithin, esriSpatialRelContains."""
    got = {}
    for rel in CONTAINS_CANDIDATES:
        try:
            got[rel] = probe.disc(rel, CALIBRATION_R)
        except QueryError:
            got[rel] = None
        if got[rel] == at_point:
            others = "; ".join(f"{r.replace('esriSpatialRel', '')} not tried" if r not in got else
                               f"{r.replace('esriSpatialRel', '')} returned "
                               + ("an error" if got[r] is None else probe.label(got[r]))
                               for r in CONTAINS_CANDIDATES if r != rel)
            return rel, (f"{rel} (calibrated on this layer with a 1 m disc: it returned the at-point set; {others})")
    desc = "; ".join(f"{r.replace('esriSpatialRel', '')} returned " + ("an error" if g is None else probe.label(g))
                     for r, g in got.items())
    return None, (f"none: for a 1 m disc neither esriSpatialRelWithin nor esriSpatialRelContains returned the at-point "
                  f"set ({desc}); intersects alone used, {NOT_TESTED}")


@dataclass
class Bracket:
    low: float | None
    high: float | None
    what: str


def bracket(probe: LayerProbe, P: frozenset, rel: str | None) -> Bracket:
    """The largest radius whose answers equal the at-point answer and the next one up; then four halvings."""
    def ok(r: float) -> bool:
        if probe.disc(REL_INTERSECTS, r) != P:
            return False
        if P and rel:
            return probe.disc(rel, r) == P
        return True

    low, high = 0.0, None
    for r in RADII:
        if ok(r):
            low = float(r)
        else:
            high = float(r)
            break
    if high is None:
        return Bracket(float(RADII[-1]), None, f"nothing changes within {RADII[-1] // 1000} km: more than "
                                               f"{RADII[-1] // 1000} km")
    for _ in range(HALVINGS):
        mid = (low + high) / 2
        if ok(mid):
            low = mid
        else:
            high = mid
    return Bracket(low, high, what_changes(probe, P, rel, high))


def what_changes(probe: LayerProbe, P: frozenset, rel: str | None, r: float) -> str:
    inter = probe.disc(REL_INTERSECTS, r)
    parts = []
    if not P:
        parts.append(f"{probe.label(inter)} touches the disc (nearest feature of any name; nothing at the point)")
        return "; ".join(parts)
    new = inter - P
    if new:
        parts.append(f"a neighbouring feature touches the disc: {probe.label(new)}")
    gone = P - inter
    if gone:
        parts.append(f"the point's own feature no longer touches the disc: {probe.label(gone)}")
    if rel:
        cont = probe.disc(rel, r)
        lost = P - cont
        if lost:
            parts.append(f"the point's own feature stops containing the disc (its own edge or a hole): "
                         f"{probe.label(lost)}")
        extra = cont - P
        if extra:
            parts.append(f"a feature not at the point contains the disc: {probe.label(extra)}")
    else:
        parts.append(NOT_TESTED)
    return "; ".join(parts) if parts else "no change found at this radius"


def _fmt(x) -> str:
    if x is None:
        return ""
    x = float(x)
    return str(int(round(x))) if abs(x - round(x)) < 1e-9 else f"{x:.1f}"


# --------------------------------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------------------------------

class Run:
    def __init__(self, req: Requester, items: dict, today: str, names_radius_m: float = 5000.0):
        self.req, self.items, self.today, self.names_radius_m = req, items, today, names_radius_m
        self.meta: dict = {}          # layer_url -> layer json (or None if it failed) + error
        self.publishers: dict = {}    # layer_url -> sidecar record
        self.calibration: dict = {}   # layer_url -> (rel, text)

    # ---- metadata ---------------------------------------------------------------------------------------------
    def layer_meta(self, layer_url: str) -> tuple[dict | None, str | None]:
        if layer_url in self.meta:
            return self.meta[layer_url]
        sources = []
        lr = self.req.get(layer_url + "?f=json", "layer metadata", "layer json")
        sources.append(self._source(layer_url + "?f=json", "layer", lr))
        root = layer_url.rsplit("/", 1)[0]
        sr = self.req.get(root + "?f=json", "layer metadata", "service root json")
        sources.append(self._source(root + "?f=json", "service", sr))
        for item in self.items.get(layer_url, []):
            ir = self.req.get(item + "?f=json", "layer metadata", "catalog item json")
            sources.append(self._source(item + "?f=json", "item " + item.rsplit("/", 1)[-1], ir))
        self.publishers[layer_url] = {"fetched_on": self.today, "sources": sources}
        if lr.data is None:
            out = (None, f"the layer's own ?f=json failed ({lr.error})")
        else:
            out = (lr.data, None)
        self.meta[layer_url] = out
        return out

    @staticmethod
    def _source(url: str, kind: str, resp: Response) -> dict:
        texts = {}
        if resp.data:
            for k in TEXT_KEYS:
                v = resp.data.get(k)
                if isinstance(v, str) and v.strip():
                    texts[k] = strip_html(v)
        return {"url": url, "kind": kind, "status": resp.status, "error": resp.error, "texts": texts}

    def statements(self, layer_url: str) -> tuple[str, str]:
        rec = self.publishers.get(layer_url)
        if not rec:
            return "not fetched", "not fetched"
        texts = [(f"{s['kind']} {k}", v) for s in rec["sources"] for k, v in s["texts"].items()]
        return extract_statements(texts, ACCURACY_WORDS), extract_statements(texts, COMPLETENESS_WORDS)

    # ---- location ----------------------------------------------------------------------------------------------
    def location(self, s: Site) -> dict:
        tie = s.tie.strip()
        parcel = s.parcel_desc if s.parcel_desc and s.parcel_desc.lower() != "none" else ""
        if tie in TIED:
            basis = f"tied parcel {parcel} (tied to the facility by {tie})" if parcel else \
                f"tied to the facility by {tie}"
        elif tie == "not stated in the record":
            basis = (f"the point of the record's queries; parcel at the point on file ({parcel}); "
                     f"the record does not state a tie") if parcel else \
                "the point of the record's queries; no parcel on file; the record does not state a tie"
        else:
            basis = "a point not tied to the facility (tie on file: " + (tie or "not stated") + ")"
            if parcel:
                basis += f"; parcel on file at it: {parcel}"
        if s.situs and s.situs.lower() not in parcel.lower():
            basis += f"; situs address on file: {s.situs}"
        extent, why = None, ""
        if tie == "neither":
            why = "not computed: the location is not tied to a parcel"
        else:
            extent, why = self.parcel_extent(s)
        if tie in TIED and extent is not None:
            unc = (f"parcel extent {_fmt(extent)} m: the outline reaches up to {_fmt(extent)} m from the point; this is "
                   f"the parcel's size, not a survey accuracy{why}")
        elif tie in TIED:
            unc = f"unknown: the parcel's outline could not be fetched ({why})"
        else:
            unc = "unknown: the location is not tied to a parcel"
        return {"location_basis": basis, "lat": "" if s.lat is None else s.lat, "lon": "" if s.lon is None else s.lon,
                "metres_from_the_inventory_point": s.metres if s.metres != "" else "not on file",
                "parcel_extent_m": _fmt(extent) if extent is not None else why,
                "location_uncertainty": unc}

    def parcel_extent(self, s: Site) -> tuple[float | None, str]:
        q = s.parcel_query
        if not q or not q.startswith("http"):
            return None, "no parcel query on file"
        pu = urllib.parse.urlparse(q)
        if not re.search(r"/(FeatureServer|MapServer)/\d+/query$", pu.path, re.I):
            return None, f"the query on file is not a parcel-layer query ({q[:100]})"
        params = dict(urllib.parse.parse_qsl(pu.query, keep_blank_values=True))
        if "geometry" not in params and "where" not in params:
            return None, "the parcel query on file has neither a point nor a where clause"
        for k in ("returnIdsOnly", "returnCountOnly", "returnCentroid", "returnExtentOnly"):
            params.pop(k, None)
        params.update({"returnGeometry": "true", "outSR": "4326", "f": "json"})
        base = q.split("?", 1)[0]
        resp = self.req.get(make_url(base, params), s.fid, "parcel outline",
                            empty_if=lambda d: not d.get("features"))
        if resp.data is None:
            # Some servers refuse outSR on this query. One retry in the layer's own spatial reference; a Web Mercator
            # outline is converted here, any other is reported as not convertible.
            first_error = resp.error
            params.pop("outSR", None)
            resp = self.req.get(make_url(base, params), s.fid, "parcel outline, without outSR (retry)",
                                empty_if=lambda d: not d.get("features"))
            if resp.data is None:
                return None, f"the parcel query failed: {first_error}; without outSR: {resp.error}"
        feats = [f for f in resp.data.get("features") or [] if (f.get("geometry") or {}).get("rings")]
        if not feats:
            return None, "the parcel query returned no outline"
        sref = resp.data.get("spatialReference") or {}
        wkid = sref.get("latestWkid") or sref.get("wkid")
        if wkid in (102100, 3857, 102113, 900913):
            feats = [{**f, "geometry": {"rings": [[list(web_mercator_to_lonlat(v[0], v[1])) for v in ring]
                                                  for ring in f["geometry"]["rings"]]}} for f in feats]
        elif wkid not in (4326, None):
            return None, f"the outline came back in wkid {wkid}, not WGS84 or Web Mercator"
        inside = [f for f in feats if point_in_rings(s.lon, s.lat, f["geometry"]["rings"])]
        if inside:
            chosen = inside[0]
        elif len(feats) == 1:
            chosen = feats[0]
        else:
            return None, f"the parcel query returned {len(feats)} outlines and none contains the point"
        d = max(haversine_m(s.lat, s.lon, v[1], v[0]) for ring in chosen["geometry"]["rings"] for v in ring)
        note = "" if inside else "; the point lies outside the one outline returned"
        return d, note

    # ---- one site ----------------------------------------------------------------------------------------------
    def site_rows(self, s: Site) -> list[dict]:
        base = {"site": s.fid, "limitation": LIMITATION, "queried_on": self.today}
        if s.lat is None or s.lon is None:
            why = s.note or "no coordinates on file in the record"
            row = {**base, "layer_publisher": "; ".join(l.publisher for l in s.layers),
                   "layer_name": "; ".join(l.layer_name for l in s.layers),
                   "layer_url": "; ".join(l.layer_url for l in s.layers),
                   "at_point": f"no layer can be queried: {why}"}
            return [_complete(row)]
        try:
            loc = self.location(s)
        except Exception as e:  # noqa: BLE001 - recorded on the row, the run goes on
            loc = {"location_basis": f"error while reading the location: {type(e).__name__}: {e}"}
        queryable = [l for l in s.layers if l.queryable]
        if not queryable:
            why = ("no territory layer on file" if not s.layers else
                   "no layer on file is an ArcGIS REST layer: " +
                   "; ".join(f"{l.layer_name} ({l.layer_url})" for l in s.layers))
            row = {**base, **loc, "layer_publisher": "; ".join(l.publisher for l in s.layers),
                   "layer_name": "; ".join(l.layer_name for l in s.layers),
                   "layer_url": "; ".join(l.layer_url for l in s.layers),
                   "at_point": f"no layer can be queried: {why}"}
            return [_complete(row)]
        rows, results = [], []
        for l in s.layers:
            row = {**base, **loc, "layer_publisher": l.publisher, "layer_name": l.layer_name, "layer_url": l.layer_url}
            if not l.queryable:
                row["at_point"] = f"not queried: not an ArcGIS REST layer ({l.layer_url})"
                row["statements_on_accuracy"] = row["statements_on_completeness"] = "not fetched"
                rows.append(row)
                continue
            try:
                res = self.measure(s, l)
                row.update(res["row"])
                results.append((l, res))
            except Exception as e:  # noqa: BLE001 - one failed layer writes a row and the run moves on
                row["at_point"] = f"error: {type(e).__name__}: {e}"
                try:
                    acc, comp = self.statements(l.layer_url)
                    row["statements_on_accuracy"], row["statements_on_completeness"] = acc, comp
                except Exception:  # noqa: BLE001
                    pass
            rows.append(row)
        sentence = conflict_sentence(results)
        for row in rows:
            row["conflicting_geometry"] = sentence
        return [_complete(r) for r in rows]

    def measure(self, s: Site, l: Layer) -> dict:
        meta, err = self.layer_meta(l.layer_url)
        acc, comp = self.statements(l.layer_url)
        if meta is None:
            raise QueryError(err)
        probe = LayerProbe(self.req, l, meta, s.fid, s.lat, s.lon)
        P = probe.at_point()
        if P:
            if l.layer_url not in self.calibration:
                self.calibration[l.layer_url] = calibrate(probe, P)
            rel, rel_text = self.calibration[l.layer_url]
        else:
            rel, rel_text = None, ("not needed: nothing at the point; the distance to the nearest feature of any name "
                                   "is bracketed by the intersects question alone")
        b = bracket(probe, P, rel)
        names_ids = probe.disc(REL_INTERSECTS, self.names_radius_m)
        at = probe.label(P)
        saved = sorted(str(x) for x in l.returned)
        now_names = probe.name_set(P)
        if not same_as_saved(saved, now_names):
            at += f"; the earlier check saved: {saved if saved else 'nothing'}"
        sp = parse_point_param(l.query_url)
        if sp:
            d = haversine_m(s.lat, s.lon, sp[0], sp[1])
            if d > 1:
                at += f"; the earlier check queried this layer at a point {_fmt(d)} m from this one"
        row = {"at_point": at,
               "nearest_line_m_low": _fmt(b.low) if b.high is not None else "more than 20 km",
               "nearest_line_m_high": _fmt(b.high) if b.high is not None else "more than 20 km",
               "what_changes_there": b.what, "relation_used_for_contains": rel_text,
               "names_within_5km": "; ".join(probe.name_set(names_ids)) or "nothing",
               "statements_on_accuracy": acc, "statements_on_completeness": comp}
        return {"row": row, "names_at_point": now_names, "bracket": b, "label": l.layer_name or l.layer_url}


def same_as_saved(saved: list[str], now: list[str]) -> bool:
    """The earlier check saved either bare names or "name | other field | ..." strings. They match when each saved
    entry is a name returned now (exactly, or as the first " | "-separated part) and every name now is among them."""
    heads = sorted(s.split(" | ", 1)[0] for s in saved)
    return heads == sorted(now)


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


def conflict_sentence(results: list) -> str:
    if not results:
        return "No layer at this site could be queried; nothing to compare."
    if len(results) == 1:
        l, r = results[0]
        return (f"One layer only ({r['label']}), so nothing to compare; it returns "
                f"{_names_text(r['names_at_point'])} at the point.")
    sets = [frozenset(_norm(n) for n in r["names_at_point"]) for _, r in results]
    side = "; ".join(f"{r['label']} returns {_names_text(r['names_at_point'])}" for _, r in results)
    brk = "; ".join(f"{r['label']} changes at {_bracket_text(r['bracket'])}" for _, r in results)
    if all(x == sets[0] for x in sets):
        head = ("The layers agree at the point: every one returns " + _names_text(results[0][1]["names_at_point"]) +
                ".")
    else:
        head = f"The layers return different answers at the point ({side}). Names differ; to be read."
    return f"{head} Within each bracket: {brk}."


def _names_text(names: list[str]) -> str:
    return "nothing" if not names else ", ".join(f"'{n}'" for n in names)


def _bracket_text(b: Bracket) -> str:
    if b.high is None:
        return "more than 20 km"
    return f"{_fmt(b.low)}-{_fmt(b.high)} m ({b.what})"


def _complete(row: dict) -> dict:
    return {c: row.get(c, "") for c in COLUMNS}


def write_csv(rows: list[dict], path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def run(sites: list[str] | None, out: Path, log: Path, publishers: Path, radius_km: float = 5.0,
        fetcher=None, conditions: Path = CONDITIONS, layer_files=LAYER_FILES, today: str | None = None,
        echo=print) -> dict:
    today = today or _dt.date.today().isoformat()
    order = load_conditions(conditions)
    recs, items, layer_names = load_records(layer_files)
    for fid in recs:                      # a record not in the conditions file is still processed, after them
        if fid not in order:
            order.append(fid)
    if sites:
        unknown = [x for x in sites if x not in order]
        if unknown:
            raise SystemExit(f"not in the conditions file or the layer files: {', '.join(unknown)}")
        order = [x for x in order if x in sites]
    req = Requester(fetcher or HttpFetcher(), log, today)
    runner = Run(req, items, today, radius_km * 1000.0)
    rows = []
    try:
        for fid in order:
            s = normalize(fid, recs.get(fid), layer_names)
            n0 = req.n_requests
            site_rows = runner.site_rows(s)
            rows.extend(site_rows)
            for r in site_rows:
                echo(f"{fid} | {r['layer_name'][:45] or '-'} | at point: {r['at_point'][:70]} | "
                     f"line {r['nearest_line_m_low']}-{r['nearest_line_m_high']} m")
            echo(f"  ({req.n_requests - n0} requests for {fid})")
    finally:
        write_csv(rows, out)
        Path(publishers).parent.mkdir(parents=True, exist_ok=True)
        Path(publishers).write_text(json.dumps(runner.publishers, indent=1, ensure_ascii=False) + "\n",
                                    encoding="utf-8")
        req.close()
    echo(f"requests {req.n_requests}, errors {req.n_errors}, rows {len(rows)}")
    return {"rows": rows, "requests": req.n_requests, "errors": req.n_errors, "urls": req.urls,
            "publishers": runner.publishers}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sites", help="comma-separated site ids (default: every site)")
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--log", default=str(OUT_LOG))
    ap.add_argument("--publishers", default=None,
                    help="sidecar JSON path (default: the real path, or <out stem>-publishers.json beside a non-default "
                         "--out, so a trial run does not overwrite it)")
    ap.add_argument("--radius-km", type=float, default=5.0)
    a = ap.parse_args(argv)
    out = Path(a.out)
    if a.publishers:
        pub = Path(a.publishers)
    elif out.resolve() == OUT_CSV.resolve():
        pub = OUT_PUBLISHERS
    else:
        pub = out.with_name(out.stem + "-publishers.json")
    sites = [x.strip() for x in a.sites.split(",") if x.strip()] if a.sites else None
    run(sites, out, Path(a.log), pub, a.radius_km)


if __name__ == "__main__":
    main()
