"""Geocoding for local action rows.

Sources, in match order (first hit wins):
  1. manual_coords.csv                       -> provenance "manual"
  2. source dataset's own published lat/lon  -> provenance "source_dataset"
     (Moratorium Nation and datacentertracker.org both ship coordinates;
      these are preferred over our own geocoding per the discovery review)
  3. Census 2024 national place gazetteer    -> provenance "place_gazetteer"
  4. County ring-average centroid from
     public/data/medicaid-counties.geojson   -> provenance "county_centroid"
     (county hint column if the dataset has one, else "X County" parsed
      from the jurisdiction string)
  5. nothing                                 -> provenance "none"
     (rows are REPORTED in QA output, never dropped)

The gazetteer download is fallback-only and must not block the build: both
upstream datasets carry coordinates, so a Census outage costs nothing.
"""
from __future__ import annotations

import csv
import json
import re
import zipfile

import config

_SUFFIX_RE = re.compile(
    r"\s+(city|town|village|borough|cdp|township|charter township)$"
)
_COUNTY_SUFFIX_RE = re.compile(
    r"\s+(county|parish|borough|census area|municipality|city and borough)$"
)
_PREFIX_RE = re.compile(r"^(city|town|village|township|borough) of\s+")


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[.,'\"()]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_parenthetical(s: str) -> str:
    # Must run BEFORE _norm deletes the paren characters, or trailing
    # qualifiers like "Adel (Cook County)" / "... Authority (YCUA)" survive
    # normalization and break matching/dedup.
    return re.sub(r"\s*\([^)]*\)\s*$", "", s or "").strip()


def norm_place(s: str) -> str:
    s = _PREFIX_RE.sub("", _norm(_strip_parenthetical(s)))
    prev = None
    while prev != s:
        prev = s
        s = _SUFFIX_RE.sub("", s)
    return s


def norm_county(s: str) -> str:
    s = _norm(_strip_parenthetical(s))
    return _COUNTY_SUFFIX_RE.sub("", s)


def _ring_average(geometry: dict):
    """Flat ring-average centroid: mean of the outer-ring vertices of the
    largest polygon. Crude but adequate for county-level map fallback."""
    if geometry["type"] == "Polygon":
        rings = [geometry["coordinates"][0]]
    elif geometry["type"] == "MultiPolygon":
        rings = [poly[0] for poly in geometry["coordinates"]]
    else:
        return None
    ring = max(rings, key=len)
    n = len(ring)
    lon = sum(pt[0] for pt in ring) / n
    lat = sum(pt[1] for pt in ring) / n
    return (round(lat, 5), round(lon, 5))


class Geocoder:
    def __init__(self) -> None:
        self.manual: dict[tuple[str, str], tuple[float, float]] = {}
        self.gazetteer: dict[tuple[str, str], list[tuple[float, float]]] = {}
        self.counties: dict[tuple[str, str], tuple[float, float]] = {}
        self.gazetteer_ok = False
        self._load_manual()
        self._load_counties()
        self._load_gazetteer()

    # -- loaders ------------------------------------------------------------
    def _load_manual(self) -> None:
        if not config.MANUAL_COORDS_CSV.exists():
            return
        with open(config.MANUAL_COORDS_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    key = (row["state"].strip().upper(), norm_place(row["jurisdiction"]))
                    self.manual[key] = (float(row["lat"]), float(row["lon"]))
                except (KeyError, ValueError):
                    continue

    def _load_counties(self) -> None:
        with open(config.COUNTIES_GEOJSON, encoding="utf-8") as f:
            gj = json.load(f)
        for feature in gj["features"]:
            props = feature["properties"]
            centroid = _ring_average(feature["geometry"])
            if centroid:
                key = (props["state_abbr"], norm_county(props["county_name"]))
                self.counties[key] = centroid

    def _load_gazetteer(self) -> None:
        if not config.GAZ_PLACE_ZIP.exists():
            try:
                print(f"  [geo] downloading place gazetteer -> {config.GAZ_PLACE_ZIP.name}")
                body = config.http_get(config.GAZ_PLACE_URL, timeout=180)
                config.GAZ_PLACE_ZIP.write_bytes(body)
            except RuntimeError as err:
                print(f"  [geo] WARN gazetteer unavailable (fallback-only, non-fatal): {err}")
                return
        try:
            with zipfile.ZipFile(config.GAZ_PLACE_ZIP) as zf:
                name = zf.namelist()[0]
                text = zf.read(name).decode("utf-8-sig")
        except (zipfile.BadZipFile, IndexError, UnicodeDecodeError) as err:
            print(f"  [geo] WARN gazetteer cache unreadable (non-fatal): {err}")
            return
        lines = text.splitlines()
        header = [h.strip() for h in lines[0].split("\t")]
        i_state = header.index("USPS")
        i_name = header.index("NAME")
        i_lat = header.index("INTPTLAT")
        i_lon = header.index("INTPTLONG")
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) <= i_lon:
                continue
            try:
                coords = (float(parts[i_lat]), float(parts[i_lon].strip()))
            except ValueError:
                continue
            key = (parts[i_state], norm_place(parts[i_name]))
            self.gazetteer.setdefault(key, []).append(coords)
        self.gazetteer_ok = True
        print(f"  [geo] gazetteer loaded: {len(self.gazetteer)} place keys")

    # -- resolution ---------------------------------------------------------
    def resolve(self, state: str, jurisdiction: str, jurisdiction_type: str = "",
                county_hint: str = "", native=None):
        """Return (lat, lon, provenance). provenance in config.VALID_GEOCODE."""
        state = (state or "").strip().upper()
        key = (state, norm_place(jurisdiction))

        if key in self.manual:
            lat, lon = self.manual[key]
            return lat, lon, "manual"

        if native and native[0] is not None and native[1] is not None:
            try:
                return round(float(native[0]), 5), round(float(native[1]), 5), "source_dataset"
            except (TypeError, ValueError):
                pass

        jt = (jurisdiction_type or "").lower()
        if jt not in ("county", "parish"):
            hits = self.gazetteer.get(key)
            if hits and len(hits) == 1:
                lat, lon = hits[0]
                return lat, lon, "place_gazetteer"
            # ambiguous multi-place names are NOT resolved by guessing

        county_key = None
        if county_hint:
            county_key = (state, norm_county(county_hint))
        elif jt in ("county", "parish") or _COUNTY_SUFFIX_RE.search(_norm(jurisdiction)):
            county_key = (state, norm_county(jurisdiction))
        else:
            match = re.search(r"\(([^)]*county[^)]*)\)", jurisdiction, flags=re.I)
            if not match:
                match = re.search(r"([\w .'-]+?\s+county)\b", jurisdiction, flags=re.I)
            if match:
                county_key = (state, norm_county(match.group(1)))
        if county_key and county_key in self.counties:
            lat, lon = self.counties[county_key]
            return lat, lon, "county_centroid"

        return None, None, "none"
