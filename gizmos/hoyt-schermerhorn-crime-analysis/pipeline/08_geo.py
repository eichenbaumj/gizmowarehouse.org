"""Stage 08: geometry for the page.
  footprints.geojson  NYC Building Footprints (Socrata 5zhs-2jue) clipped to the study box, height capped
  labels.geojson      hand labels from crosswalks/labels.csv
  grid.geojson        the deployed explorer cells with 2024-25 counts and ranks (for the citywide pull-out)
The footprint fetch is the one network call; it is cached in raw/footprints_raw.geojson."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib import geo  # noqa: E402

FOOTPRINT_DS = "5zhs-2jue"
CLIP = {"lat0": 40.6855, "lat1": 40.6945, "lon0": -73.9935, "lon1": -73.9775}
ROLE_POINTS = {"courthouse": (40.6899, -73.9887), "station_hoyt": (40.6885, -73.9850), "station_dekalb": (40.6906, -73.9814), "station_nevins": (40.6883, -73.9802)}


def fetch_footprints() -> dict:
    p = config.RAW_DIR / "footprints_raw.geojson"
    if p.exists():
        return json.loads(p.read_text())
    url = (f"https://data.cityofnewyork.us/resource/{FOOTPRINT_DS}.geojson?$where=within_box(the_geom,{CLIP['lat1']},{CLIP['lon0']},{CLIP['lat0']},{CLIP['lon1']})&$limit=20000")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(r.text)
    return r.json()


def round_coords(coords, nd=6):
    if isinstance(coords[0], (float, int)):
        return [round(coords[0], nd), round(coords[1], nd)]
    return [round_coords(c, nd) for c in coords]


def centroid(geom) -> tuple[float, float]:
    pts = []
    def walk(c):
        if isinstance(c[0], (float, int)):
            pts.append(c)
        else:
            for x in c:
                walk(x)
    walk(geom["coordinates"])
    a = np.array(pts)
    return float(a[:, 1].mean()), float(a[:, 0].mean())


def main() -> None:
    config.PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    fc = fetch_footprints()
    feats = []
    for f in fc["features"]:
        props = f.get("properties", {})
        h = pd.to_numeric(props.get("height_roof"), errors="coerce")
        h = float(h) if pd.notna(h) else 10.0
        h_m = min(h * 0.3048, config.FOOTPRINT_CAP_M)
        lat, lon = centroid(f["geometry"])
        role = "building"
        for r, (rl, rn) in ROLE_POINTS.items():
            if geo.haversine_m(lat, lon, rl, rn) <= 45:
                role = "courthouse" if r == "courthouse" else "station"
        feats.append({"type": "Feature", "geometry": {"type": f["geometry"]["type"], "coordinates": round_coords(f["geometry"]["coordinates"])},
                      "properties": {"bin": props.get("bin"), "height_m": round(h_m, 1), "height_ft_raw": round(h, 1), "role": role, "year_built": props.get("construction_year")}})
    out = {"type": "FeatureCollection", "snapshot": config.SNAPSHOT_DATE, "height_cap_m": config.FOOTPRINT_CAP_M, "source": f"NYC Open Data Building Footprints {FOOTPRINT_DS}", "features": feats}
    (config.PUBLIC_DATA_DIR / "footprints.geojson").write_text(json.dumps(out, separators=(",", ":")))

    labels = pd.read_csv(config.CROSSWALKS / "labels.csv")
    lf = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(float(r.lon), 6), round(float(r.lat), 6)]},
           "properties": {"name": r["name"], "kind": r.kind, "status": r.status}} for _, r in labels.iterrows()]
    (config.PUBLIC_DATA_DIR / "labels.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": lf}, indent=0))

    ladder = json.loads((config.OUT_DIR / "ladder.json").read_text())
    panel = pd.read_parquet(config.OUT_DIR / "cell_year_class.parquet")
    rec = panel[panel["year"].isin(config.RECENT_YEARS)].groupby("cell_id")["n"].sum()
    rank = rec.rank(ascending=False, method="min").astype(int)
    names = geo.cell_name_map()
    cells = geo.deployed_cells()
    # Stage 11 adds per-resident fields (residents, jobs, rate_res, rank_res) to this file; keep them on a
    # partial rerun, the same way stage 09 keeps stage 11's context blocks.
    grid_path = config.PUBLIC_DATA_DIR / "grid.geojson"
    prev = json.loads(grid_path.read_text()) if grid_path.exists() else {}
    prev_props = {f["properties"]["cell_id"]: {k: f["properties"][k] for k in config.GRID_STAGE11_PROPS if k in f["properties"]} for f in prev.get("features", [])}
    gf = []
    for _, c in cells.iterrows():
        cid = c["id"]
        gf.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[round(c["west"], 6), round(c["south"], 6)], [round(c["east"], 6), round(c["south"], 6)],
                                                                                        [round(c["east"], 6), round(c["north"], 6)], [round(c["west"], 6), round(c["north"], 6)], [round(c["west"], 6), round(c["south"], 6)]]]},
                   "properties": {"cell_id": cid, "name": names.get(cid, cid), "count_2024_25": int(rec.get(cid, 0)), "rank": int(rank.get(cid, len(cells))),
                                  "is_focus": cid in (config.CELL_ID, config.TIMES_SQUARE_CELL), **prev_props.get(cid, {})}})
    top = {k: prev[k] for k in ("n_cells_rate_res", "min_residents") if k in prev}
    grid_path.write_text(json.dumps({"type": "FeatureCollection", "window": "2024_25", "n_cells": len(gf), **top, "features": gf}, separators=(",", ":")))
    print(f"stage 08 done: {len(feats)} footprints ({(config.PUBLIC_DATA_DIR / 'footprints.geojson').stat().st_size / 1e6:.2f} MB), {len(lf)} labels, {len(gf)} cells "
          f"({(config.PUBLIC_DATA_DIR / 'grid.geojson').stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
