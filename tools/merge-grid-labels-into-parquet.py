#!/usr/bin/env python3
"""Merge baked place + landmark labels back into grid_1mi_metrics.parquet.

Stage 08 writes both grid_1mi.geojson and grid_1mi_metrics.parquet. The two
label bakes (bake-medicaid-place-labels.py, bake-medicaid-landmarks.py) then add
place_* / landmark_* columns to the GeoJSON only. Stage 09 reads the parquet
(never the multi-GB GeoJSON), so it can't see those labels unless we copy them
over. This step does that copy.

The GeoJSON properties are read WITHOUT geometry (read_geometry=False) — loading
the ~600 MB+ geometry here would OOM for no reason; we only need six columns.

Run (between the two bakes and stage 09):
    python3 tools/merge-grid-labels-into-parquet.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyogrio

REPO = Path(__file__).resolve().parent.parent
GRID_GEOJSON = REPO / "gizmos/medicaid-work-requirements/pipeline/output/grid_1mi.geojson"
GRID_PARQUET = REPO / "gizmos/medicaid-work-requirements/pipeline/output/grid_1mi_metrics.parquet"

LABEL_COLS = ["place_name", "place_parent", "place_state", "landmark_name", "landmark_category"]
STR_LABELS = ["place_name", "place_parent", "place_state", "landmark_name"]


def main() -> None:
    if not GRID_GEOJSON.exists() or not GRID_PARQUET.exists():
        print(f"ERROR: need both {GRID_GEOJSON.name} and {GRID_PARQUET.name}", file=sys.stderr)
        sys.exit(1)

    # Fail loudly if a bake didn't run (column absent), rather than silently
    # shipping a parquet with no labels for stage 09 to mode-aggregate.
    info = pyogrio.read_info(GRID_GEOJSON)
    fields = set(info["fields"])
    missing = [c for c in LABEL_COLS if c not in fields]
    if missing:
        print(f"ERROR: {GRID_GEOJSON.name} is missing {missing} — run both label bakes first.",
              file=sys.stderr)
        sys.exit(1)

    print(f"Reading label columns from {GRID_GEOJSON.name} (no geometry)...")
    labels = pyogrio.read_dataframe(
        GRID_GEOJSON, columns=["cell_id"] + LABEL_COLS, read_geometry=False, use_arrow=True
    )
    labels["cell_id"] = labels["cell_id"].astype(str)
    print(f"  {len(labels):,} rows")

    par = pd.read_parquet(GRID_PARQUET)
    par["cell_id"] = par["cell_id"].astype(str)
    n0 = len(par)

    # Idempotent: drop any prior label columns before re-merging.
    par = par.drop(columns=[c for c in LABEL_COLS if c in par.columns])
    merged = par.merge(labels, on="cell_id", how="left")
    for c in STR_LABELS:
        merged[c] = merged[c].fillna("")
    merged["landmark_category"] = merged["landmark_category"].fillna(99).astype(int)

    assert len(merged) == n0, f"row count changed in label merge ({n0} -> {len(merged)})"
    fill = float((merged["place_name"].astype(str) != "").mean())
    if fill < 0.5:
        print(f"WARN: place_name fill rate only {fill:.1%} — possible cell_id dtype mismatch")
    else:
        print(f"  place_name fill rate {fill:.1%}")

    merged.to_parquet(GRID_PARQUET, index=False)
    print(f"-> merged {len(LABEL_COLS)} label columns into {GRID_PARQUET.name}")


if __name__ == "__main__":
    main()
