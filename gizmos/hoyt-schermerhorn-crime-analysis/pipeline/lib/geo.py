"""Haversine, lattice assignment (via crime-data-pipeline's assign.py), precinct join."""
from __future__ import annotations

import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

R_EARTH = 6_371_008.8


def haversine_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = map(np.radians, (np.asarray(lat1, float), np.asarray(lon1, float), lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(a))


@lru_cache(maxsize=1)
def _assign_module():
    spec = importlib.util.spec_from_file_location("lattice_assign", config.ASSIGN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=1)
def lattice_env() -> dict:
    return json.loads(config.LATTICE_JSON.read_text())


@lru_cache(maxsize=1)
def deployed_cells() -> pd.DataFrame:
    env = lattice_env()
    rows = [c for c in env["cells"] if c.get("deployed")]
    df = pd.DataFrame(rows)
    return df


def assign_cells(lon, lat) -> tuple[np.ndarray, np.ndarray]:
    """Returns (cell_id object array or None, off-lattice mask). Half-open rule on stored edges."""
    mod = _assign_module()
    ids, off = mod.assign(lattice_env(), lon, lat)
    return ids, off


def conservation(ids, off) -> dict:
    mod = _assign_module()
    rep = mod.conservation_report(ids, off)
    return rep if isinstance(rep, dict) else rep.__dict__


def cell_edges(cell_id: str) -> dict:
    env = lattice_env()
    for c in env["cells"]:
        if c["id"] == cell_id:
            return {"south": c["south"], "north": c["north"], "west": c["west"], "east": c["east"]}
    raise KeyError(cell_id)


def cell_name_map() -> dict[str, str]:
    """Names live only in the patched JSON (the CSV has placeholders)."""
    txt = config.GRID_CELLS_JSON.read_text().replace("NaN", "null")
    j = json.loads(txt)
    cells = j if isinstance(j, list) else j.get("cells") or j.get("features") or []
    out = {}
    for c in cells:
        props = c.get("properties", c)
        cid = props.get("cell_id") or props.get("id")
        if cid:
            out[str(cid)] = props.get("name") or str(cid)
    return out


def read_precincts():
    """NYPD precinct polygons in EPSG:4326 with an integer `Precinct` column, from the complete NYC Open Data
    file (78 polygons) or, if it has not been fetched, the crime-pipeline copy (77: no 123rd) with a warning."""
    import geopandas as gpd
    path = config.PRECINCTS_GEOJSON
    if not path.exists():
        print(f"WARNING: {path} missing; falling back to {config.PRECINCTS_GEOJSON_FALLBACK} (lacks the 123rd Precinct)")
        path = config.PRECINCTS_GEOJSON_FALLBACK
    pct = gpd.read_file(path).to_crs(4326)
    field = "Precinct" if "Precinct" in pct.columns else [c for c in pct.columns if "prec" in c.lower()][0]
    pct["Precinct"] = pd.to_numeric(pct[field], errors="coerce").astype(int)
    return pct


def precinct_join(lat: pd.Series, lon: pd.Series) -> pd.Series:
    import geopandas as gpd
    from shapely.geometry import Point

    pct = read_precincts()
    field = "Precinct"
    pts = gpd.GeoDataFrame({"i": lat.index}, geometry=[Point(x, y) for x, y in zip(lon, lat)], crs="EPSG:4326")
    j = gpd.sjoin(pts, pct[[field, "geometry"]], how="left", predicate="within")
    j = j.drop_duplicates("i").set_index("i")
    return pd.to_numeric(j[field], errors="coerce").reindex(lat.index)
