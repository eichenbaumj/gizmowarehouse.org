#!/bin/bash
# Stage 05 — build PMTiles vector archive from the enriched parcel GeoJSON.
#
# Prerequisites:
#   - tippecanoe: brew install tippecanoe
#   - stage 04 has produced output/parcels_with_tax_*_enriched.geojson
#
# v2 changes (vs v1):
#   - z=12..15 (was z=10..16) — NTA aggregates cover z<12 in the frontend;
#     z=16 was overkill (parcels already pixel-clear at z=15).
#   - -y filter to ship only properties used at render time (drops `owner`,
#     `address`, `lat`, `lon`, `bct2020`, `cd`, `borough`, `units_res`,
#     `etr_vs_median`, `zipcode`). Halves tile size.
#   - --maximum-tile-bytes=500000 to cap individual tile size (helps dense
#     Manhattan tiles render quickly).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INPUT="${1:-$SCRIPT_DIR/output/parcels_with_tax_enriched.geojson}"
OUTPUT="${2:-$SCRIPT_DIR/output/parcels.pmtiles}"

if ! command -v tippecanoe &> /dev/null; then
    echo "ERROR: tippecanoe not found. brew install tippecanoe" >&2
    exit 1
fi

if [ ! -f "$INPUT" ]; then
    echo "ERROR: missing $INPUT — run stages 03 + 04 first." >&2
    exit 1
fi

echo "Building PMTiles from $INPUT..."

# -y flags: keep only the properties the map actually paints / displays.
# Anything else (owner, address, lat/lon, etc.) is fetched on demand via
# the parcel-detail panel from the parcels GeoJSON or other source.
tippecanoe \
    -o "$OUTPUT" \
    -Z 12 -z 15 \
    -l parcels \
    -y bbl -y address -y bldg_class -y tax_class \
    -y market_value -y billable_av -y tax_bill -y etr -y tax_per_sqft \
    -y mv_y2023 -y mv_y2026 \
    -y exempt_fraction -y exempt_total \
    -y units_total -y year_built -y bldg_area -y num_floors \
    -y data_quality \
    -y aggregation -y units_aggregated \
    --maximum-tile-bytes=500000 \
    --coalesce-densest-as-needed \
    --extend-zooms-if-still-dropping \
    --force \
    "$INPUT"

echo ""
echo "Output: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
