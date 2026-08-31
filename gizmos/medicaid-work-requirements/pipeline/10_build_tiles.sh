#!/usr/bin/env bash
# Stage 10 — build PMTiles vector tilesets via tippecanoe.
#
# Three output tilesets:
#   counties.pmtiles    — county polygons with all metrics, z=2-10
#   grid.pmtiles        — 1-mile cells, z=8-14
#   coarse_hex.pmtiles  — combined 5mi + 20mi, z=5-7
#
# Requires tippecanoe (brew install tippecanoe).

set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"
RAW_DIR="$PIPELINE_DIR/raw"
OUT_DIR="$PIPELINE_DIR/output"

if ! command -v tippecanoe &> /dev/null; then
    echo "ERROR: tippecanoe not found. Install with: brew install tippecanoe"
    exit 1
fi

# ----- Counties -------------------------------------------------------------
# We need to merge the cb_2024_counties shapefile with county_summary metrics.
# Stage 07 produces county_summary.parquet; we use ogr2ogr + a Python helper
# to attach metrics. For simplicity, generate a counties_with_metrics.geojson
# in stage 07 and consume it here. (Bumping this back to stage 07 — see TODO.)
COUNTIES_INPUT="$OUT_DIR/counties_with_metrics.geojson"
if [[ ! -f "$COUNTIES_INPUT" ]]; then
    echo "WARN: $COUNTIES_INPUT missing. Skipping counties tileset."
    echo "      (Stage 07 needs to write this — to be added in a follow-up.)"
else
    echo "==> Building counties.pmtiles..."
    tippecanoe \
        -o "$OUT_DIR/counties.pmtiles" \
        -Z 2 -z 10 \
        -l counties \
        --maximum-tile-bytes=500000 \
        --coalesce-densest-as-needed \
        --extend-zooms-if-still-dropping \
        --force \
        "$COUNTIES_INPUT"
    echo "    -> $(du -h "$OUT_DIR/counties.pmtiles" | cut -f1)"
fi

# ----- 1-mile grid ----------------------------------------------------------
GRID_INPUT="$OUT_DIR/grid_1mi.geojson"
if [[ ! -f "$GRID_INPUT" ]]; then
    echo "WARN: $GRID_INPUT missing. Skipping grid tileset."
else
    echo "==> Building grid.v7.pmtiles..."
    # -y is exclusive — only these properties survive the tile build: metric
    # fields + total_pop/expansion for the popup body, parent_county_name/state
    # for the sublabel, place_name/parent/state for the Tier A→D place label,
    # and landmark_name/category for the institutional anchor.
    #
    # maxzoom is 12, NOT 14. The per-cell place/landmark label strings make the
    # tile balloon at the top zooms (labeled: z12≈112 MB, z13≈240 MB, z14≈620 MB).
    # The 1-mile hexes are fully resolved by z12, so we stop there and let MapLibre
    # overzoom z12→14 (lossless for static polygons; popups still resolve via
    # queryRenderedFeatures). ~112 MB vs ~620 MB at z14 — this is the fix for the
    # tile-bloat issue. Drop --extend-zooms-if-still-dropping so it can't climb back.
    tippecanoe \
        -o "$OUT_DIR/grid.v7.pmtiles" \
        -Z 8 -z 12 \
        -l grid \
        -y subject_count_strict -y subject_rate \
        -y burden_index_centered -y loss_exposure_strict \
        -y total_pop -y expansion -y subject_via_waiver \
        -y parent_county_name -y parent_state_abbr \
        -y place_name -y place_parent -y place_state \
        -y landmark_name -y landmark_category \
        --maximum-tile-bytes=500000 \
        --coalesce-densest-as-needed \
        --force \
        "$GRID_INPUT"
    echo "    -> $(du -h "$OUT_DIR/grid.v7.pmtiles" | cut -f1)"
    # Also write a copy under the unversioned filename for any downstream
    # consumers that haven't been pointed at the versioned name.
    cp "$OUT_DIR/grid.v7.pmtiles" "$OUT_DIR/grid.pmtiles"
fi

# ----- Coarse hex (5mi + 20mi combined into one tileset, layer differentiates) ---
HEX5_INPUT="$OUT_DIR/hex_5mi.geojson"
HEX20_INPUT="$OUT_DIR/hex_20mi.geojson"
if [[ -f "$HEX5_INPUT" && -f "$HEX20_INPUT" ]]; then
    echo "==> Building coarse_hex.pmtiles (5mi + 20mi layers)..."
    tippecanoe \
        -o "$OUT_DIR/coarse_hex.pmtiles" \
        -Z 2 -z 8 \
        -L "{\"file\":\"$HEX5_INPUT\",\"layer\":\"hex_5mi\",\"minimum_zoom\":5,\"maximum_zoom\":8}" \
        -L "{\"file\":\"$HEX20_INPUT\",\"layer\":\"hex_20mi\",\"minimum_zoom\":2,\"maximum_zoom\":5}" \
        --maximum-tile-bytes=500000 \
        --coalesce-densest-as-needed \
        --force
    echo "    -> $(du -h "$OUT_DIR/coarse_hex.pmtiles" | cut -f1)"
else
    echo "WARN: coarse hex inputs missing. Skipping coarse_hex tileset."
fi

echo
echo "Tile artifacts in $OUT_DIR/:"
ls -lh "$OUT_DIR"/*.pmtiles 2>/dev/null || echo "  (none built)"
