"""Tests on invented inputs for pipeline/analysis/reconciliation_inputs.py (session 21, job 4; R4 accesses 1 to 3).

Nothing here reads data/. Every layer and parquet file is invented in a temporary folder. Each group of tests has a
companion `..._can_fail` test that makes a deliberate break in the test process (a monkeypatched constant or function,
or a broken input) and shows the same check then fails.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import reconciliation_inputs as ri  # noqa: E402

gpd = pytest.importorskip("geopandas")
pyogrio = pytest.importorskip("pyogrio")
from shapely.geometry import Polygon, box  # noqa: E402

MODULE_PATH = ROOT / "pipeline" / "analysis" / "reconciliation_inputs.py"

# An invented mapping for the rule tests (the real one classes every value ambiguous).
MAP = {"RETAILISH": "retail", "WHOLESALE ONLY": "wholesale_only", "UNCLEAR": "ambiguous"}


# =================================================================================================================
# Fixed column lists
# =================================================================================================================
def check_columns(frame: pd.DataFrame, expected: tuple[str, ...], literal: tuple[str, ...]) -> None:
    assert expected == literal, f"the module constant {expected} is not the fixed list {literal}"
    assert tuple(frame.columns) == literal, f"columns {list(frame.columns)} != {list(literal)}"


INCIDENCE_LITERAL = ("fid", "utility_id_reported", "area", "type_class")
SHORT_FORM_LITERAL = ("utility_id_eia", "state", "year", "short_form", "data_observed")


def _full_frame():
    return pd.DataFrame({"fid": ["a", "a"], "polygon": [0, 1], "id_raw": ["10", "NA1"], "TYPE": ["X", "Y"],
                         "area": [1.0, 2.0], "utility_id_reported": pd.array([10, None], dtype="Int64"),
                         "type_class": ["ambiguous", "ambiguous"], "extra_decoy": [9, 9]})


def _sf_raw():
    return pd.DataFrame({"utility_id_eia": [2, 1, 1], "state": ["TX", "OK", "OK"],
                         "report_date": pd.to_datetime(["2019-01-01", "2020-01-01", "2019-01-01"]),
                         "short_form": pd.array([True, None, None], dtype="boolean"),
                         "data_observed": [True, True, False]})


def test_incidence_columns_fixed():
    check_columns(ri.incidence_table(_full_frame()), ri.INCIDENCE_COLUMNS, INCIDENCE_LITERAL)


def test_short_form_columns_fixed():
    t = ri.short_form_flags(_sf_raw())
    check_columns(t, ri.SHORT_FORM_COLUMNS, SHORT_FORM_LITERAL)
    assert t.year.tolist() == [2019, 2020, 2019]          # sorted by unit, state, year; year from report_date
    assert t.utility_id_eia.tolist() == [1, 1, 2]
    assert t.short_form.isna().tolist() == [True, True, False]   # a missing flag stays missing, never filled


def test_columns_fixed_can_fail(monkeypatch):
    # break 1: a column added to the module constant
    monkeypatch.setattr(ri, "INCIDENCE_COLUMNS", INCIDENCE_LITERAL + ("NAME",))
    with pytest.raises((AssertionError, KeyError)):
        check_columns(ri.incidence_table(_full_frame()), ri.INCIDENCE_COLUMNS, INCIDENCE_LITERAL)
    monkeypatch.undo()
    # break 2: a table that gained a column
    t = ri.short_form_flags(_sf_raw()).assign(sales_revenue=1.0)
    with pytest.raises(AssertionError):
        check_columns(t, ri.SHORT_FORM_COLUMNS, SHORT_FORM_LITERAL)


def test_short_form_flags_refuses_extra_column():
    with pytest.raises(PermissionError):
        ri.short_form_flags(_sf_raw().assign(sales_revenue=5.0))


# =================================================================================================================
# The geojson readers (accesses 1 and 2) against an invented layer with decoy fields
# =================================================================================================================
def _write_layer(path: Path) -> Path:
    feats = []
    for i, (fid_, typ, geom) in enumerate([
            ("101", "RETAILISH", box(-100, 40, -99, 41)), ("NA1", "UNCLEAR", box(-98, 40, -97, 41))]):
        feats.append({"type": "Feature",
                      "properties": {"OBJECTID": i, "ID": fid_, "NAME": f"Decoy Utility {i}", "TYPE": typ,
                                     "RETAIL_MWH": 123456.0 + i, "CUSTOMERS": 99, "STATE": "ZZ"},
                      "geometry": json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


class RaisingSource:
    """A source that raises on any column outside `allowed`, records every request, and delegates to a real reader."""
    def __init__(self, allowed, delegate):
        self.allowed, self.delegate, self.requests = set(allowed), delegate, []

    def __call__(self, path, columns=None, **kw):
        if columns is None:
            raise PermissionError("a read with no column list was requested")
        self.requests.append((list(columns), dict(kw)))
        bad = set(columns) - self.allowed
        if bad:
            raise PermissionError(f"columns {sorted(bad)} requested")
        return self.delegate(path, columns=columns, **kw)


def test_access_2_reader_reads_only_id_type_geometry(tmp_path):
    layer = _write_layer(tmp_path / "layer.geojson")
    src = RaisingSource({"ID", "TYPE"}, pyogrio.read_dataframe)
    g = ri.read_territories(layer, read_fn=src)
    assert list(g.columns) == ["ID", "TYPE", "geometry"]
    for decoy in ("NAME", "RETAIL_MWH", "CUSTOMERS", "STATE", "OBJECTID"):
        assert decoy not in g.columns
    assert src.requests == [(["ID", "TYPE"], {})]
    assert "Decoy" not in g.to_json() and "123456" not in g.to_json()


def test_access_1_reader_reads_only_type(tmp_path):
    layer = _write_layer(tmp_path / "layer.geojson")
    src = RaisingSource({"TYPE"}, pyogrio.read_dataframe)
    assert ri.read_type_values(layer, read_fn=src) == ["RETAILISH", "UNCLEAR"]
    assert src.requests == [(["TYPE"], {"read_geometry": False})]


def test_geojson_readers_can_fail(tmp_path, monkeypatch):
    layer = _write_layer(tmp_path / "layer.geojson")
    # break 1: the module's list widened to NAME; the source raises before reading
    monkeypatch.setattr(ri, "ACCESS_2_FIELDS", ("ID", "TYPE", "NAME"))
    src = RaisingSource({"ID", "TYPE"}, pyogrio.read_dataframe)
    with pytest.raises(PermissionError):
        ri.read_territories(layer, read_fn=src)
    monkeypatch.undo()
    # break 2: a reader that ignores the column list and returns every field; the reader refuses its output
    with pytest.raises(PermissionError):
        ri.read_territories(layer, read_fn=lambda p, columns, **kw: pyogrio.read_dataframe(p, **kw))
    with pytest.raises(PermissionError):
        ri.read_type_values(layer, read_fn=lambda p, columns, **kw: pyogrio.read_dataframe(p, **kw))
    # break 3: the test's own expectation fails on a widened read
    g = pyogrio.read_dataframe(layer, columns=["ID", "TYPE", "NAME"])
    with pytest.raises(AssertionError):
        assert list(g.columns) == ["ID", "TYPE", "geometry"]


# =================================================================================================================
# The parquet reader (access 3) against an invented file with decoy revenue columns
# =================================================================================================================
def _write_parquet(path: Path) -> Path:
    df = _sf_raw().assign(sales_revenue=[1.0, 2.0, 3.0], summer_peak_demand_mw=[5.0, 6.0, 7.0])
    df.to_parquet(path, index=False)
    return path


@pytest.mark.parametrize("delegate", ["duckdb", "pandas"])
def test_access_3_reader_reads_only_five(tmp_path, delegate):
    f = _write_parquet(tmp_path / "misc.parquet")
    real = ri._duckdb_select if delegate == "duckdb" else pd.read_parquet
    src = RaisingSource(set(ri.ACCESS_3_COLUMNS), real)
    df = ri.read_short_form(f, read_fn=src)
    assert list(df.columns) == list(SHORT_FORM_LITERAL[:2]) + ["report_date", "short_form", "data_observed"]
    assert "sales_revenue" not in df.columns and "summer_peak_demand_mw" not in df.columns
    assert src.requests == [(list(ri.ACCESS_3_COLUMNS), {})]


def test_access_3_default_reader_selects_only_five(tmp_path):
    f = _write_parquet(tmp_path / "misc.parquet")
    df = ri.read_short_form(f)          # duckdb SELECT of the five
    assert list(df.columns) == list(ri.ACCESS_3_COLUMNS)


def test_access_3_reader_can_fail(tmp_path, monkeypatch):
    f = _write_parquet(tmp_path / "misc.parquet")
    src = RaisingSource(set(SHORT_FORM_LITERAL[:2]) | {"report_date", "short_form", "data_observed"}, pd.read_parquet)
    # break 1: the module's list gains the revenue column; the source raises before reading
    monkeypatch.setattr(ri, "ACCESS_3_COLUMNS", ri.ACCESS_3_COLUMNS + ("sales_revenue",))
    with pytest.raises(PermissionError):
        ri.read_short_form(f, read_fn=lambda p, columns, **kw: src(p, columns=columns, **kw))
    monkeypatch.undo()
    # break 2: a reader that ignores the list and returns the decoy; the reader refuses its output
    with pytest.raises(PermissionError):
        ri.read_short_form(f, read_fn=lambda p, columns, **kw: pd.read_parquet(p))


# =================================================================================================================
# No price reader
# =================================================================================================================
FORBIDDEN_NAMES = {"load_outcomes", "load_sales", "read_listed_outcomes"}
FORBIDDEN_MODULES = ("panel", "power_simulation", "run_outcomes", "outcome_analysis")


def price_reader_hits(source: str) -> list[str]:
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            hits.append(node.attr)
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            hits.append(node.id)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = {a.name for a in node.names}
            if any(m in mod.split(".") for m in FORBIDDEN_MODULES) or names & (FORBIDDEN_NAMES | set(FORBIDDEN_MODULES)):
                hits.append(f"from {mod} import {sorted(names)}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if any(m in a.name.split(".") for m in FORBIDDEN_MODULES):
                    hits.append(f"import {a.name}")
    return hits


def test_no_price_reader_in_source():
    src = MODULE_PATH.read_text()
    assert price_reader_hits(src) == []
    for word in FORBIDDEN_NAMES:
        assert word not in src


def test_no_price_reader_imported_at_runtime():
    code = ("import sys; sys.path.insert(0, %r); import pipeline.analysis.reconciliation_inputs; "
            "print(sorted(m for m in sys.modules if m.startswith('pipeline')))" % str(ROOT))
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True).stdout
    mods = set(eval(out))
    assert mods <= {"pipeline", "pipeline.analysis", "pipeline.analysis.reconciliation_inputs"}, mods


def test_no_price_reader_can_fail():
    broken = MODULE_PATH.read_text() + "\nfrom pipeline.electricity import panel\nx = panel.load_outcomes()\n"
    assert price_reader_hits(broken) != []
    broken2 = "import pipeline.analysis.power_simulation as ps\nps.read_listed_outcomes()\n"
    assert len(price_reader_hits(broken2)) == 2


# =================================================================================================================
# Incidence and the two rules on an invented world
# =================================================================================================================
def _world():
    """Polygons (EPSG:4326) and sites. Sizes: BIG > MID > SMALL. Each site's expected case in its name."""
    polys = [
        ("1", "RETAILISH", box(-100, 30, -90, 40)),         # 0 BIG retail
        ("2", "RETAILISH", box(-99, 31, -98, 32)),          # 1 SMALL retail inside BIG
        ("3", "WHOLESALE ONLY", box(-95, 31, -94, 32)),     # 2 SMALL wholesale-only inside BIG
        ("4", "WHOLESALE ONLY", box(-80, 31, -79, 32)),     # 3 wholesale-only alone
        ("5", "UNCLEAR", box(-70, 31, -69, 32)),            # 4 ambiguous alone
        ("6", "UNCLEAR", box(-97, 33, -96, 34)),            # 5 SMALL ambiguous inside BIG
        ("NA7", "RETAILISH", box(-60, 31, -59, 32)),        # 6 non-numeric id
        ("8", "RETAILISH", box(-50, 31, -49, 32)),          # 7 tie: same box as 9
        ("9", "RETAILISH", box(-50, 31, -49, 32)),          # 8
    ]
    terr = gpd.GeoDataFrame({"ID": [p[0] for p in polys], "TYPE": [p[1] for p in polys]},
                            geometry=[p[2] for p in polys], crs=4326)
    sites = pd.DataFrame({
        "fid": ["two_retail", "retail_and_wholesale", "wholesale_alone", "ambiguous_alone", "ambiguous_in_retail",
                "in_none", "no_point", "non_numeric", "tie", "on_vertex", "big_only"],
        "lat": [31.5, 31.5, 31.5, 31.5, 33.5, 10.0, np.nan, 31.5, 31.5, 32.0, 35.0],
        "lon": [-98.5, -94.5, -79.5, -69.5, -96.5, 10.0, -98.0, -59.5, -49.5, -79.0, -92.0]})
    return terr, sites


def outcomes(full):
    """Row U with ambiguous polygons forced to fail loudly, and row C, for every site with rows."""
    res = {}
    for fid, g in full.groupby("fid"):
        cls = dict(zip(g.polygon, g.type_class))
        res[fid] = (ri.rule_u_outcome(g, cls) if "ambiguous" not in cls.values() else ("needs_classing",),
                    ri.rule_c_outcome(g))
    return res


def check_rules(full, deps):
    o = outcomes(full)
    assert o["two_retail"][0] == ("assigned", "2")                  # smallest of two retail
    assert o["retail_and_wholesale"][0] == ("assigned", "1")        # retail before a smaller wholesale-only one
    assert o["retail_and_wholesale"][1] == ("assigned", "3")        # row C: the smallest whatever its type
    assert o["wholesale_alone"][0] == ("unassigned_wholesale_only",)
    assert o["tie"][0][0] == "tie" and o["tie"][0][1] == ("8", "9") # a tie is reported, not broken
    assert o["big_only"][0] == ("assigned", "1")
    assert o["non_numeric"][0] == ("assigned", "raw:NA7")
    assert "in_none" not in o and "no_point" not in o and "on_vertex" not in o
    assert o["ambiguous_alone"][0] == ("needs_classing",)          # never silently retail or wholesale-only
    assert deps == {"UNCLEAR": {"row_u": ["ambiguous_alone", "ambiguous_in_retail"], "row_c": []}}


def test_incidence_and_rules():
    terr, sites = _world()
    full = ri.polygon_incidence_full(sites, terr, mapping=MAP)
    deps = ri.dependent_sites(full, layer_values=terr.TYPE, mapping=MAP)
    check_rules(full, deps)
    t = ri.incidence_table(full)
    assert set(t.type_class) == {"retail", "wholesale_only", "ambiguous"}
    assert t.loc[t.fid == "non_numeric", "utility_id_reported"].isna().all()
    assert (t.loc[t.fid == "ambiguous_alone", "type_class"] == "ambiguous").all()
    s = ri.incidence_summary(sites, terr, full, mapping=MAP)
    assert s["sites"] == 11 and s["sites_with_point"] == 10
    assert s["sites_without_point"] == ["no_point"]
    assert s["sites_in_no_polygon"] == {"count": 2, "fids": ["in_none", "on_vertex"]}
    assert s["sites_in_exactly_one_polygon"] == 4      # wholesale_alone, ambiguous_alone, non_numeric, big_only
    assert s["sites_in_several_polygons"] == 4         # two_retail, retail_and_wholesale, ambiguous_in_retail, tie
    assert s["polygons_by_class"] == {"retail": 5, "wholesale_only": 2, "ambiguous": 2}
    assert s["non_numeric_ids"]["distinct_ids"] == ["NA7"]
    assert s["non_numeric_ids"]["sites_inside_a_non_numeric_id_polygon"] == ["non_numeric"]


def test_rules_can_fail(monkeypatch):
    terr, sites = _world()
    full = ri.polygon_incidence_full(sites, terr, mapping=MAP)
    deps = ri.dependent_sites(full, layer_values=terr.TYPE, mapping=MAP)
    # break 1: row U takes the LARGEST retail polygon
    real = ri.rule_u_outcome

    def largest(polys, classes):
        flipped = polys.assign(area=-polys.area)
        return real(flipped, classes)
    monkeypatch.setattr(ri, "rule_u_outcome", largest)
    with pytest.raises(AssertionError):
        check_rules(full, deps)
    monkeypatch.undo()
    # break 2: the ambiguous value silently classed retail
    full2 = ri.polygon_incidence_full(sites, terr, mapping={**MAP, "UNCLEAR": "retail"})
    deps2 = ri.dependent_sites(full2, layer_values=terr.TYPE, mapping={**MAP, "UNCLEAR": "retail"})
    with pytest.raises(AssertionError):
        check_rules(full2, deps2)


def test_dependency_with_two_ambiguous_values():
    """A site in a small polygon of value A and a large of value B, both ambiguous: it depends on A (A retail gives A,
    A wholesale-only gives B or unassigned), and on B (with A wholesale-only, B decides between B and unassigned)."""
    terr = gpd.GeoDataFrame({"ID": ["1", "2", "3"], "TYPE": ["A", "B", "RETAILISH"]},
                            geometry=[box(0, 0, 1, 1), box(-5, -5, 5, 5), box(20, 20, 21, 21)], crs=4326)
    sites = pd.DataFrame({"fid": ["s", "r"], "lat": [0.5, 20.5], "lon": [0.5, 20.5]})
    m = {"RETAILISH": "retail"}
    full = ri.polygon_incidence_full(sites, terr, mapping=m)
    deps = ri.dependent_sites(full, layer_values=terr.TYPE, mapping=m)
    assert deps == {"A": {"row_u": ["s"], "row_c": []}, "B": {"row_u": ["s"], "row_c": []}}


def test_area_is_equal_area_km2():
    """A 1 by 1 degree cell at 40 to 41 N: its ellipsoidal area is about 9,358 km2 (pyproj geodesic, planted here)."""
    from pyproj import Geod
    cell = box(-100, 40, -99, 41)
    expect = abs(Geod(ellps="GRS80").geometry_area_perimeter(cell)[0]) / 1e6
    terr = gpd.GeoDataFrame({"ID": ["1"], "TYPE": ["RETAILISH"]}, geometry=[cell], crs=4326)
    sites = pd.DataFrame({"fid": ["x"], "lat": [40.5], "lon": [-99.5]})
    full = ri.polygon_incidence_full(sites, terr, mapping=MAP)
    # tolerance 0.5%: the projected polygon has straight edges between projected vertices, the geodesic one does not
    assert full.area.iloc[0] == pytest.approx(expect, rel=0.005)
    assert 9000 < full.area.iloc[0] < 9700


def test_area_can_fail(monkeypatch):
    """Break: the projection swapped for Web Mercator, which is not equal-area; the area check fails."""
    from pyproj import Geod
    cell = box(-100, 40, -99, 41)
    expect = abs(Geod(ellps="GRS80").geometry_area_perimeter(cell)[0]) / 1e6
    monkeypatch.setattr(ri, "EQUAL_AREA_CRS", 3857)
    terr = gpd.GeoDataFrame({"ID": ["1"], "TYPE": ["RETAILISH"]}, geometry=[cell], crs=4326)
    full = ri.polygon_incidence_full(pd.DataFrame({"fid": ["x"], "lat": [40.5], "lon": [-99.5]}), terr, mapping=MAP)
    with pytest.raises(AssertionError):
        assert full.area.iloc[0] == pytest.approx(expect, rel=0.005)


# =================================================================================================================
# The mapping
# =================================================================================================================
def test_mapping_never_resolves_unknown_or_missing():
    assert ri.classify_type("SOMETHING NEW") == "ambiguous"
    assert ri.classify_type(None) == "ambiguous"
    assert ri.classify_type(float("nan")) == "ambiguous"
    with pytest.raises(ValueError):
        ri.classify_type("X", {"X": "probably_retail"})


def test_real_mapping_is_complete_and_reasoned():
    assert set(ri.TYPE_CLASS.values()) <= set(ri.CLASSES)
    assert set(ri.TYPE_CLASS) == set(ri.TYPE_CLASS_REASON)
    assert all(ri.TYPE_CLASS_REASON[k] for k in ri.TYPE_CLASS)
    # the agent's reading as recorded in docs/gate1/territory-type-mapping-2026-11-19.md: every value ambiguous
    assert set(ri.TYPE_CLASS.values()) == {"ambiguous"}


def test_mapping_can_fail(monkeypatch):
    monkeypatch.setitem(ri.TYPE_CLASS, "INVESTOR OWNED", "retail")
    with pytest.raises(AssertionError):
        assert set(ri.TYPE_CLASS.values()) == {"ambiguous"}
    with pytest.raises(AssertionError):
        assert ri.classify_type("SOMETHING NEW", {"SOMETHING NEW": "retail"}) == "ambiguous"


def test_numeric_id():
    assert ri.numeric_id("01234") == 1234
    assert ri.numeric_id(" 77 ") == 77
    assert ri.numeric_id("NA1") is None and ri.numeric_id(None) is None and ri.numeric_id("12a") is None
    with pytest.raises(AssertionError):           # a deliberate wrong expectation fails
        assert ri.numeric_id("NA1") == 1


# =================================================================================================================
# The repeat read for the TYPE value (session 22; Joe's ruling of 2026-11-19, D-109)
# =================================================================================================================
TYPED_LITERAL = ("fid", "polygon", "utility_id_reported", "area", "TYPE")


def test_typed_incidence_columns_fixed():
    t = ri.typed_incidence_table(_full_frame())
    check_columns(t, ri.TYPED_INCIDENCE_COLUMNS, TYPED_LITERAL)
    assert t.TYPE.tolist() == ["X", "Y"] and "extra_decoy" not in t.columns and "id_raw" not in t.columns


def test_typed_incidence_columns_fixed_can_fail(monkeypatch):
    monkeypatch.setattr(ri, "TYPED_INCIDENCE_COLUMNS", TYPED_LITERAL + ("NAME",))
    with pytest.raises((AssertionError, KeyError)):
        check_columns(ri.typed_incidence_table(_full_frame()), ri.TYPED_INCIDENCE_COLUMNS, TYPED_LITERAL)


def test_same_incidence_finds_a_difference():
    t = ri.incidence_table(_full_frame())
    assert ri.same_incidence(t, t.copy()) == []
    assert ri.same_incidence(t, t.assign(area=t.area + 1e-6)) == ["area differs in some row"]
    assert ri.same_incidence(t, t.assign(utility_id_reported=pd.array([11, None], dtype="Int64"))) == [
        "utility_id_reported differs in some row"]
    assert ri.same_incidence(t, t.iloc[:1]) == ["2 rows rebuilt against 1 on file"]


def _types_world(tmp_path, monkeypatch):
    """An invented layer with decoy fields, invented sites, and the first table written from them, every path of
    main_types pointed into tmp_path. pyogrio's reader is wrapped to record each request and refuse decoy fields; the
    short-form reader refuses to run."""
    layer = _write_layer(tmp_path / "layer.geojson")
    fac = tmp_path / "facilities.parquet"
    pd.DataFrame({"fid": ["s1", "s2", "s3"], "lat": [40.5, 40.5, 10.0], "lon": [-99.5, -97.5, 10.0]}).to_parquet(fac)
    src = RaisingSource({"ID", "TYPE"}, pyogrio.read_dataframe)
    monkeypatch.setattr(pyogrio, "read_dataframe", src)
    for name, val in (("TERRITORY_LAYER", layer), ("FACILITIES", fac),
                      ("OUT_INCIDENCE", tmp_path / "incidence.parquet"),
                      ("OUT_TYPED_INCIDENCE", tmp_path / "typed.parquet")):
        monkeypatch.setattr(ri, name, val)

    def no_short_form(*a, **k):
        raise AssertionError("main_types must not read the short-form file")
    monkeypatch.setattr(ri, "read_short_form", no_short_form)
    first = ri.incidence_table(ri.polygon_incidence_full(ri.read_sites(fac), ri.read_territories(layer, read_fn=src)))
    first.to_parquet(tmp_path / "incidence.parquet", index=False)
    src.requests.clear()
    return src, first


def test_main_types_reads_the_layer_once_by_id_type_geometry(tmp_path, monkeypatch, capsys):
    src, first = _types_world(tmp_path, monkeypatch)
    assert ri.main_types() == 0
    assert src.requests == [(["ID", "TYPE"], {})]                    # one read, the two fields and the geometry
    typed = pd.read_parquet(tmp_path / "typed.parquet")
    assert tuple(typed.columns) == TYPED_LITERAL and typed.TYPE.tolist() == ["RETAILISH", "UNCLEAR"]
    assert typed.fid.tolist() == first.fid.tolist() and "Decoy" not in typed.to_json()
    assert json.loads(capsys.readouterr().out)["layer_reads"] == 1


def test_main_types_stops_when_the_first_table_differs_can_fail(tmp_path, monkeypatch):
    src, first = _types_world(tmp_path, monkeypatch)
    first.assign(area=first.area * 2).to_parquet(tmp_path / "incidence.parquet", index=False)
    with pytest.raises(SystemExit, match="area differs"):
        ri.main_types()
    assert not (tmp_path / "typed.parquet").exists()
