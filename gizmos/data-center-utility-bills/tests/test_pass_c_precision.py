"""The precision fields (docs/DECISIONS.md, D-65 item 2; D-66 section 5): pass_c_precision.py against a fake server.

No network. The fake server holds a made-up world in local metres around a site point and answers ArcGIS-style point
and polygon queries under the relations the script uses. Discs are read back as circles (centre and mean vertex
distance), so the answers are exact for the radius the script asked for.
"""
import csv
import json
import math
import sys
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import pass_c_precision as pp  # noqa: E402

LAT0, LON0 = 45.0, -120.0
LAYER = "https://example.test/arcgis/rest/services/Territories/FeatureServer/0"
SERVICE = "https://example.test/arcgis/rest/services/Territories/FeatureServer"
ITEM = "https://www.arcgis.com/sharing/rest/content/items/0123456789abcdef0123456789abcdef"
PARCEL_LAYER = "https://parcels.test/arcgis/rest/services/Parcels/MapServer/3"


# ---- the fake world ------------------------------------------------------------------------------------------------

def to_xy(lon, lat):
    x = math.radians(lon - LON0) * pp.EARTH_R * math.cos(math.radians(LAT0))
    y = math.radians(lat - LAT0) * pp.EARTH_R
    return x, y


def to_lonlat(x, y):
    return (LON0 + math.degrees(x / (pp.EARTH_R * math.cos(math.radians(LAT0)))),
            LAT0 + math.degrees(y / pp.EARTH_R))


def west_of(a):       # the half-plane x < a
    return {"inter": lambda cx, cy, r: cx - r < a, "cont": lambda cx, cy, r: cx + r < a}


def east_of(a):       # the half-plane x >= a
    return {"inter": lambda cx, cy, r: cx + r >= a, "cont": lambda cx, cy, r: cx - r >= a}


def everywhere():
    return {"inter": lambda cx, cy, r: True, "cont": lambda cx, cy, r: True}


def everywhere_but_hole(hx, hy, hr):
    def d(cx, cy):
        return math.hypot(cx - hx, cy - hy)
    return {"inter": lambda cx, cy, r: not (d(cx, cy) + r <= hr), "cont": lambda cx, cy, r: d(cx, cy) >= r + hr}


class FakeServer:
    """mode 'within': esriSpatialRelWithin returns features containing the query (Esri's documented sense);
    'contains': the server has the two the other way round; 'none': neither relation works (an error)."""

    def __init__(self, features, mode="within", meta_extra=None, parcel=None):
        self.features, self.mode, self.urls = features, mode, []
        self.meta_extra = meta_extra or {}
        self.parcel = parcel

    def get(self, url):
        self.urls.append(url)
        base, _, q = url.partition("?")
        qs = dict(urllib.parse.parse_qsl(q))
        if base == LAYER and qs == {"f": "json"}:
            return pp.Response(200, {"objectIdField": "OBJECTID", "displayField": "NAME",
                                     "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"},
                                                {"name": "NAME", "type": "esriFieldTypeString"}],
                                     **self.meta_extra})
        if base == SERVICE and qs == {"f": "json"}:
            return pp.Response(200, {"serviceDescription": "Service areas as drawn."})
        if base == ITEM and qs == {"f": "json"}:
            return pp.Response(200, {"snippet": "Territories.", "licenseInfo": "Provided as is."})
        if base == PARCEL_LAYER + "/query":
            return pp.Response(200, self.parcel)
        assert base == LAYER + "/query", url
        rel = qs["spatialRel"]
        if qs["geometryType"] == "esriGeometryPoint":
            lon, lat = map(float, qs["geometry"].split(","))
            cx, cy = to_xy(lon, lat)
            r = 0.0
        else:
            ring = json.loads(qs["geometry"])["rings"][0][:-1]
            pts = [to_xy(*v) for v in ring]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            r = sum(math.hypot(p[0] - cx, p[1] - cy) for p in pts) / len(pts)
        if rel == pp.REL_INTERSECTS:
            hit = [f for f in self.features if f["geom"]["inter"](cx, cy, r)]
        else:
            if self.mode == "none":
                return pp.Response(200, None, "ArcGIS error 400: unsupported spatialRel")
            feature_contains_query = (rel == "esriSpatialRelWithin") == (self.mode == "within")
            hit = [f for f in self.features if f["geom"]["cont"](cx, cy, r)] if feature_contains_query else []
        return pp.Response(200, {"features": [{"attributes": {"OBJECTID": f["id"], "NAME": f["name"]}}
                                              for f in hit]})


def write_inputs(tmp_path, parcel_query=None, tie="address", extra_layers=()):
    cond = tmp_path / "conditions.csv"
    with open(cond, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["site", "parcel_or_point"])
        w.writerow(["t:1", "x"])
    rec = {"fid": "t:1",
           "a_coordinates": {"point_lat": LAT0, "point_lon": LON0, "tied_to_facility_by": tie,
                             "metres_from_inventory_point": 0, "parcel_id": "P-1", "situs_address": "1 Test Rd",
                             "parcel_layer_url": PARCEL_LAYER if parcel_query else None, "query_url": parcel_query},
           "b_layers": [{"publisher": "Test Commission", "layer_name": "Territories", "layer_url": LAYER,
                         "query_url": LAYER + f"/query?geometry={LON0}%2C{LAT0}&outFields=NAME&f=json",
                         "returned": ["Alpha Power"], "fields": {"NAME": "Alpha Power"}}, *extra_layers],
           "c_coverage": [{"layer_url": LAYER, "description_url": f"{SERVICE}?f=json ; {ITEM}?f=json"}]}
    lf = tmp_path / "layers.json"
    lf.write_text(json.dumps([rec]))
    return cond, [lf]


def run_fake(tmp_path, server, **kw):
    cond, lfs = write_inputs(tmp_path, **kw)
    res = pp.run(None, tmp_path / "out.csv", tmp_path / "log.csv", tmp_path / "pub.json", fetcher=server,
                 conditions=cond, layer_files=lfs, today="2026-11-16", echo=lambda *_: None)
    return res, res["rows"]


# ---- tests ---------------------------------------------------------------------------------------------------------

def test_disc_vertices_are_at_the_radius():
    ring = pp.disc_ring(45.0, -120.0, 1000.0)
    assert len(ring) == pp.DISC_SIDES + 1 and ring[0] == ring[-1]
    for lon, lat in ring[:-1]:
        assert abs(pp.haversine_m(45.0, -120.0, lat, lon) - 1000.0) < 1.0


def test_disc_is_clockwise():
    ring = pp.disc_ring(45.0, -120.0, 500.0)
    area2 = sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))
    assert area2 < 0                                    # negative shoelace sum: clockwise


def test_bracket_and_halvings_at_730_m(tmp_path):
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": west_of(730)},
                         {"id": 2, "name": "Beta Coop", "geom": east_of(730)}])
    res, rows = run_fake(tmp_path, server)
    (row,) = rows
    low, high = float(row["nearest_line_m_low"]), float(row["nearest_line_m_high"])
    assert low <= 730 <= high
    assert high - low <= 500 / 16 + 1e-9
    assert row["relation_used_for_contains"].startswith("esriSpatialRelWithin")
    assert "'Beta Coop'" in row["what_changes_there"] and "neighbouring" in row["what_changes_there"]
    assert "'Alpha Power' (OBJECTID 1)" == row["at_point"]
    assert row["names_within_5km"] == "Alpha Power; Beta Coop"
    assert row["limitation"] == pp.LIMITATION
    assert row["location_uncertainty"].startswith("unknown: the parcel's outline could not be fetched")
    assert "One layer only" in row["conflicting_geometry"]


def test_hole_is_found_by_the_contains_question(tmp_path):
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": everywhere_but_hole(400, 0, 50)}])
    _, rows = run_fake(tmp_path, server)
    (row,) = rows
    low, high = float(row["nearest_line_m_low"]), float(row["nearest_line_m_high"])
    assert low <= 350 <= high and high - low <= 250 / 16 + 1e-9
    assert "stops containing the disc (its own edge or a hole)" in row["what_changes_there"]
    assert "neighbouring" not in row["what_changes_there"]


def test_nothing_at_the_point(tmp_path):
    server = FakeServer([{"id": 7, "name": "Gamma PUD", "geom": east_of(3000)}])
    _, rows = run_fake(tmp_path, server)
    (row,) = rows
    assert row["at_point"].startswith("nothing")
    assert "the earlier check saved: ['Alpha Power']" in row["at_point"]
    low, high = float(row["nearest_line_m_low"]), float(row["nearest_line_m_high"])
    assert low <= 3000 <= high and high - low <= 3000 / 16 + 1e-9
    assert "'Gamma PUD'" in row["what_changes_there"] and "nothing at the point" in row["what_changes_there"]
    assert row["relation_used_for_contains"].startswith("not needed")
    assert not any("esriSpatialRelWithin" in u or "esriSpatialRelContains" in u for u in server.urls)


@pytest.mark.parametrize("mode,expected", [("within", "esriSpatialRelWithin"), ("contains", "esriSpatialRelContains")])
def test_calibration_picks_the_relation_that_works(tmp_path, mode, expected):
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": west_of(730)},
                         {"id": 2, "name": "Beta Coop", "geom": east_of(730)}], mode=mode)
    _, rows = run_fake(tmp_path, server)
    assert rows[0]["relation_used_for_contains"].startswith(expected + " (calibrated")
    assert any(f"spatialRel={expected}" in u for u in server.urls if "r=" not in u)


def test_calibration_fallback_when_neither_works(tmp_path):
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": everywhere_but_hole(400, 0, 50)},
                         {"id": 2, "name": "Beta Coop", "geom": east_of(5000)}], mode="none")
    _, rows = run_fake(tmp_path, server)
    (row,) = rows
    assert row["relation_used_for_contains"].startswith("none:")
    assert pp.NOT_TESTED in row["relation_used_for_contains"]
    assert pp.NOT_TESTED in row["what_changes_there"]
    # With intersects alone the hole at 350 m is not seen; the neighbour at 5 km is.
    low, high = float(row["nearest_line_m_low"]), float(row["nearest_line_m_high"])
    assert low <= 5000 <= high
    log = list(csv.DictReader(open(tmp_path / "log.csv")))
    assert sum(r["result"].startswith("error") for r in log) == 2      # the two failed calibration queries, logged


def test_more_than_20_km(tmp_path):
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": everywhere()}])
    _, rows = run_fake(tmp_path, server)
    (row,) = rows
    assert row["nearest_line_m_low"] == row["nearest_line_m_high"] == "more than 20 km"
    assert "more than 20 km" in row["what_changes_there"]


def test_sentence_extraction_verbatim_and_nothing_found():
    raw = ("<p>This layer is <b>approximate</b> and not intended for legal use.</p><div>Updated yearly by staff."
           "</div>Colors&nbsp;are arbitrary.")
    text = pp.strip_html(raw)
    acc = pp.extract_statements([("layer description", text)], pp.ACCURACY_WORDS)
    comp = pp.extract_statements([("layer description", text)], pp.COMPLETENESS_WORDS)
    assert acc == 'layer description: "This layer is approximate and not intended for legal use."'
    assert comp == 'layer description: "Updated yearly by staff."'
    assert pp.extract_statements([("x", "Colors are arbitrary.")], pp.ACCURACY_WORDS) == pp.NOTHING_FOUND
    assert pp.NOTHING_FOUND == "the publisher says nothing found on this"
    assert pp.extract_statements([("item licenseInfo", "Provided as is.")], pp.ACCURACY_WORDS) == \
        'item licenseInfo: "Provided as is."'


def test_publisher_texts_reach_the_row_and_the_sidecar(tmp_path):
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": everywhere()}],
                        meta_extra={"description": "<p>Boundaries are generalized from paper maps.</p>",
                                    "copyrightText": "State of Test"})
    res, rows = run_fake(tmp_path, server)
    (row,) = rows
    assert row["statements_on_accuracy"] == ('layer description: "Boundaries are generalized from paper maps." | '
                                             'item 0123456789abcdef0123456789abcdef licenseInfo: "Provided as is."')
    assert row["statements_on_completeness"] == pp.NOTHING_FOUND
    side = json.loads((tmp_path / "pub.json").read_text())
    kinds = [s["kind"] for s in side[LAYER]["sources"]]
    assert kinds == ["layer", "service", "item 0123456789abcdef0123456789abcdef"]
    assert side[LAYER]["sources"][0]["texts"]["copyrightText"] == "State of Test"


def test_parcel_extent(tmp_path):
    corners = [to_lonlat(x, y) for x, y in [(-50, 50), (50, 50), (50, -50), (-50, -50), (-50, 50)]]
    parcel = {"spatialReference": {"wkid": 4326}, "features": [{"geometry": {"rings": [corners]}}]}
    q = PARCEL_LAYER + f"/query?geometry={LON0}%2C{LAT0}&geometryType=esriGeometryPoint&outFields=%2A" \
                       "&returnGeometry=false&f=json"
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": everywhere()}], parcel=parcel)
    _, rows = run_fake(tmp_path, server, parcel_query=q)
    (row,) = rows
    assert abs(float(row["parcel_extent_m"]) - 50 * math.sqrt(2)) < 1.0
    assert row["location_uncertainty"].startswith("parcel extent 70.7 m")
    assert "not a survey accuracy" in row["location_uncertainty"]


def test_untied_location_is_unknown_and_pdf_layer_gets_a_row(tmp_path):
    pdf = {"publisher": "Utility", "layer_name": "Map (PDF)", "layer_url": "https://utility.test/map.pdf",
           "query_url": None, "returned": [], "fields": {}}
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": everywhere()}])
    _, rows = run_fake(tmp_path, server, tie="neither", extra_layers=[pdf])
    assert len(rows) == 2
    assert rows[0]["location_uncertainty"] == "unknown: the location is not tied to a parcel"
    assert rows[1]["at_point"].startswith("not queried: not an ArcGIS REST layer")
    assert not any("utility.test" in u for u in server.urls)


def test_conflict_sentence_flags_different_names():
    b = pp.Bracket(100.0, 131.25, "x")
    res = [(None, {"label": "A", "names_at_point": ["PGE"], "bracket": b}),
           (None, {"label": "B", "names_at_point": ["Portland General Electric"], "bracket": b})]
    s = pp.conflict_sentence(res)
    assert "Names differ; to be read." in s and "'PGE'" in s and "'Portland General Electric'" in s
    same = [(None, {"label": "A", "names_at_point": ["PGE"], "bracket": b}),
            (None, {"label": "B", "names_at_point": ["pge "], "bracket": b})]
    assert pp.conflict_sentence(same).startswith("The layers agree at the point")


def test_requests_hold_only_the_layer_url_and_query_parameters(tmp_path):
    corners = [to_lonlat(x, y) for x, y in [(-50, 50), (50, 50), (50, -50), (-50, -50), (-50, 50)]]
    parcel = {"spatialReference": {"wkid": 4326}, "features": [{"geometry": {"rings": [corners]}}]}
    q = PARCEL_LAYER + f"/query?geometry={LON0}%2C{LAT0}&geometryType=esriGeometryPoint&outFields=%2A&f=json"
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": west_of(730)},
                         {"id": 2, "name": "Beta Coop", "geom": east_of(730)}], parcel=parcel)
    res, _ = run_fake(tmp_path, server, parcel_query=q)
    allowed_bases = {LAYER, LAYER + "/query", SERVICE, ITEM, PARCEL_LAYER + "/query"}
    allowed_keys = {"f", "geometry", "geometryType", "inSR", "spatialRel", "outFields", "returnGeometry", "outSR"}
    assert server.urls == res["urls"]
    for u in server.urls:
        base, _, q = u.partition("?")
        assert base in allowed_bases, u
        keys = {k for k, _ in urllib.parse.parse_qsl(q)}
        assert keys <= allowed_keys, u
        assert "@" not in u and "user" not in u.lower()
    req = pp.build_request(LAYER + "?f=json")
    assert {k.lower(): v for k, v in req.header_items()} == {"user-agent": "research-script/1.0 (urllib)",
                                                            "accept": "application/json"}
    log = list(csv.DictReader(open(tmp_path / "log.csv")))
    assert len(log) == len(server.urls)
    assert {r["round"] for r in log} == {"D-66 precision"}
    assert {r["who"] for r in log} == {"pass_c_precision.py, run by the session"}
    assert {r["avenue"] for r in log} == {"map"}
    assert {r["target"] for r in log} == {"t:1", "layer metadata"}
    assert [r["query_or_url"] for r in log] == server.urls


def test_a_failing_layer_writes_a_row_and_the_run_goes_on(tmp_path):
    class Broken(FakeServer):
        def get(self, url):
            self.urls.append(url)
            return pp.Response(403, None, "HTTP 403")
    _, rows = run_fake(tmp_path, Broken([]))
    (row,) = rows
    assert row["at_point"].startswith("error:") and "403" in row["at_point"]
    assert row["limitation"] == pp.LIMITATION


def test_site_without_a_record_gets_one_row(tmp_path):
    cond, lfs = write_inputs(tmp_path)
    with open(cond, "a", newline="") as fh:
        csv.writer(fh).writerow(["t:2", ""])
    server = FakeServer([{"id": 1, "name": "Alpha Power", "geom": everywhere()}])
    res = pp.run(["t:2"], tmp_path / "o.csv", tmp_path / "l.csv", tmp_path / "p.json", fetcher=server,
                 conditions=cond, layer_files=lfs, today="2026-11-16", echo=lambda *_: None)
    (row,) = res["rows"]
    assert row["at_point"].startswith("no layer can be queried: no record for this site")
    assert server.urls == []


def test_parcel_extent_retries_without_outsr_and_reads_web_mercator(tmp_path):
    def merc(lon, lat):
        r = 6378137.0
        return [math.radians(lon) * r, r * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))]
    corners = [merc(*to_lonlat(x, y)) for x, y in [(-50, 50), (50, 50), (50, -50), (-50, -50), (-50, 50)]]

    class NoOutSR(FakeServer):
        def get(self, url):
            if url.startswith(PARCEL_LAYER) and "outSR" in url:
                self.urls.append(url)
                return pp.Response(200, None, "ArcGIS error 400: Invalid query parameters.")
            return super().get(url)
    parcel = {"spatialReference": {"wkid": 102100, "latestWkid": 3857}, "features": [{"geometry": {"rings": [corners]}}]}
    q = PARCEL_LAYER + f"/query?geometry={LON0}%2C{LAT0}&geometryType=esriGeometryPoint&outFields=%2A&f=json"
    server = NoOutSR([{"id": 1, "name": "Alpha Power", "geom": everywhere()}], parcel=parcel)
    _, rows = run_fake(tmp_path, server, parcel_query=q)
    assert abs(float(rows[0]["parcel_extent_m"]) - 50 * math.sqrt(2)) < 1.0
    log = list(csv.DictReader(open(tmp_path / "log.csv")))
    assert [r["note"] for r in log if "parcel" in r["note"]] == ["parcel outline", "parcel outline, without outSR (retry)"]


def test_saved_answer_comparison():
    assert pp.same_as_saved(["CITY OF ELK RIVER | MUNICIPAL | 5773", "CITY OF ST PAUL - (NE) | NOT AVAILABLE | 1"],
                            ["CITY OF ELK RIVER", "CITY OF ST PAUL - (NE)"])
    assert pp.same_as_saved(["PacifiCorp"], ["PacifiCorp"]) and pp.same_as_saved([], [])
    assert not pp.same_as_saved(["PacifiCorp"], []) and not pp.same_as_saved([], ["PGE"])


def test_illustrative_and_limitations_wording_counts_as_accuracy():
    t = ("Collin County Copyright -This data is a graphic representation of Collin County and should only be used for "
         "illustrative purposes. In no way should this data be used to settle any boundary dispute or locational "
         "conflict.")
    out = pp.extract_statements([("item licenseInfo", t)], pp.ACCURACY_WORDS)
    assert out.count('item licenseInfo: "') == 2 and "illustrative purposes." in out
