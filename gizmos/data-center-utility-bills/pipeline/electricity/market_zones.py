#!/usr/bin/env python3
"""Which Ohio, Pennsylvania and Kentucky utilities sat in the two transmission zones that left MISO for PJM.

FirstEnergy's American Transmission Systems zone (Ohio Edison, Cleveland
Electric Illuminating, Toledo Edison, Pennsylvania Power) was integrated into
PJM on 1 June 2011, and Duke Energy Ohio and Duke Energy Kentucky on
1 January 2012 (pipeline/electricity/market_moves.csv). Municipal systems and
cooperatives inside those zones moved with them. EIA reports a balancing
authority only from 2013, when all of them say PJM, so which zone a small
system was in has to come from the territory map (docs/DECISIONS.md, D-30, D-37).

Rule. A utility in those three states whose reported market is PJM is placed
in the zone of the investor-owned territory that contains more than half of
its own territory. A utility whose territory lies mostly outside every
investor-owned polygon takes the nearest one, and is marked as placed by
distance. A utility with no polygon on the map is not placed and is read as
PJM throughout. This is inference from a map of about 2022; it is medium
confidence at best and is written out so that it can be checked by hand.

Quantities only: the panel's utility list and the territory polygons. No price.

Output: pipeline/electricity/pjm_late_zones.csv
Run:  python3 -I pipeline/electricity/market_zones.py     (needs data/raw/territories/, fetch_territories.py)
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.electricity import market_region, panel  # noqa: E402

OUT = ROOT / "pipeline" / "electricity" / "pjm_late_zones.csv"
TERRITORIES = ROOT / "data" / "raw" / "territories" / "retail_service_territories.geojson"
EQUAL_AREA = "EPSG:5070"
STATES = ("OH", "PA", "KY")
# Investor-owned territories by the zone their transmission is in. EIA utility ids.
ZONES = {
    "ATSI": {13998: "Ohio Edison", 3755: "Cleveland Electric Illuminating", 18997: "Toledo Edison", 14716: "Pennsylvania Power"},
    "DEOK": {3542: "Duke Energy Ohio", 19446: "Duke Energy Kentucky"},
    "AEP": {14006: "Ohio Power", 22053: "Kentucky Power", 20521: "Wheeling Power"},
    "DAYTON": {4922: "Dayton Power and Light"},
    "DUQUESNE": {5487: "Duquesne Light"},
    "ALLEGHENY": {20387: "West Penn Power"},
    "PENELEC": {14711: "Pennsylvania Electric"},
    "METED": {12390: "Metropolitan Edison"},
    "PPL": {14715: "PPL Electric Utilities"},
    "PECO": {14940: "PECO Energy"},
}
INSIDE = 0.5


def main() -> int:
    warnings.filterwarnings("ignore")
    q = panel.load_quantities()
    units = q[q.state.isin(STATES)][["utility_id_eia", "state"]].drop_duplicates()
    names = q.groupby(["utility_id_eia", "state"]).utility_name.last()
    own = q.groupby(["utility_id_eia", "state"]).ownership.last()
    region = market_region.fixed(q)
    terr = gpd.read_file(TERRITORIES).to_crs(EQUAL_AREA)
    terr["geometry"] = terr.geometry.buffer(0)
    terr["ID"] = pd.to_numeric(terr.ID, errors="coerce")
    terr = terr[terr.ID.notna()].assign(ID=lambda d: d.ID.astype(int))
    terr = terr.dissolve(by="ID").reset_index()
    zone_of = {i: z for z, ids in ZONES.items() for i in ids}
    zones = terr[terr.ID.isin(zone_of)].assign(zone=lambda d: d.ID.map(zone_of)).dissolve(by="zone").reset_index()[["zone", "geometry"]]
    poly = terr.set_index("ID").geometry
    rows = []
    for u, st in units.itertuples(index=False):
        k = (u, st)
        if region.get(k) != "PJM":
            continue
        if u in zone_of:
            rows.append((u, st, names.get(k), own.get(k), zone_of[u], "the zone's own investor-owned utility", 1.0))
            continue
        if u not in poly.index:
            rows.append((u, st, names.get(k), own.get(k), "", "no territory polygon; not placed", None))
            continue
        g = poly[u]
        share = zones.geometry.intersection(g).area / g.area if g.area > 0 else zones.geometry.area * 0
        best = int(share.values.argmax())
        if share.iloc[best] > INSIDE:
            rows.append((u, st, names.get(k), own.get(k), zones.zone.iloc[best], "more than half of its territory is inside", round(float(share.iloc[best]), 3)))
        else:
            near = int(zones.geometry.distance(g.representative_point()).values.argmin())
            rows.append((u, st, names.get(k), own.get(k), zones.zone.iloc[near], "nearest investor-owned territory", round(float(share.iloc[near]), 3)))
    out = pd.DataFrame(rows, columns=["utility_id_eia", "state", "utility_name", "ownership", "zone", "basis", "share_of_territory_inside"])
    out = out.sort_values(["state", "zone", "utility_name"])
    out.to_csv(OUT, index=False)
    print(out.groupby(["state", "zone", "basis"]).size().to_string())
    print("wrote", OUT.relative_to(ROOT), len(out), "utilities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
