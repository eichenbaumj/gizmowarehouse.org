#!/bin/bash
# Pipeline orchestrator. Runs all stages end-to-end.
#
# Usage:
#   ./build.sh                                    # full citywide
#   ./build.sh --sample-zip 11201                 # one zipcode (Brooklyn Heights)
#   ./build.sh --sample-boro BK                   # one borough
#   ./build.sh --skip-tiles --skip-upload         # Python stages only
#   ./build.sh --refresh                          # force-drop cached raw before fetch
#
# Stages:
#   01_fetch_pluto.py    — DCP MapPLUTO ArcGIS export to GeoJSON
#   02_fetch_pvad.py     — NYC DOF PVAD (8y4t-faws) CSV
#   03_compute_tax_bill.py  — join + tax bill + ETR + tax/sqft
#   04_aggregate.py      — citywide stats + CD/NTA aggregates
#   05_build_tiles.sh    — Tippecanoe → PMTiles
#   06_upload_r2.sh      — push to Cloudflare R2

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

SAMPLE_ZIP=""
SAMPLE_BORO=""
SKIP_TILES=0
SKIP_UPLOAD=0
REFRESH=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sample-zip) SAMPLE_ZIP="$2"; shift 2;;
        --sample-boro) SAMPLE_BORO="$2"; shift 2;;
        --skip-tiles) SKIP_TILES=1; shift;;
        --skip-upload) SKIP_UPLOAD=1; shift;;
        --refresh) REFRESH=1; shift;;
        *) echo "Unknown arg: $1"; exit 1;;
    esac
done

PLUTO_ARGS=()
PVAD_ARGS=()
PLUTO_TAG=""
if [ -n "$SAMPLE_ZIP" ]; then
    PLUTO_ARGS=(--sample-zip "$SAMPLE_ZIP")
    PLUTO_TAG="$SAMPLE_ZIP"
elif [ -n "$SAMPLE_BORO" ]; then
    PLUTO_ARGS=(--sample-boro "$SAMPLE_BORO")
    PLUTO_TAG="$SAMPLE_BORO"
    case "$SAMPLE_BORO" in
        MN|mn) PVAD_ARGS=(--boro 1);;
        BX|bx) PVAD_ARGS=(--boro 2);;
        BK|bk) PVAD_ARGS=(--boro 3);;
        QN|qn) PVAD_ARGS=(--boro 4);;
        SI|si) PVAD_ARGS=(--boro 5);;
    esac
fi

PLUTO_FILE="raw/pluto${PLUTO_TAG:+.$PLUTO_TAG}.geojson"
PVAD_BORO_TAG=""
if [ ${#PVAD_ARGS[@]} -gt 0 ]; then
    PVAD_BORO_TAG=".boro${PVAD_ARGS[1]}"
fi
PVAD_FILE="raw/pvad${PVAD_BORO_TAG}.csv"

# Stale-cache guard: if --refresh OR the cached raw files lack the CondoNo /
# condo_number columns added in the May 2026 condo-aggregation fix, drop them
# so stages 01–02 refetch fresh. Without this, a rebuild silently runs with
# pre-fix PLUTO/PVAD and every condo polygon flags `no_pvad_match`.
if [ "$REFRESH" -eq 1 ]; then
    echo "--refresh: dropping cached raw inputs"
    rm -f "$PLUTO_FILE" "$PVAD_FILE"
fi
if [ -f "$PLUTO_FILE" ] && ! head -c 200000 "$PLUTO_FILE" | grep -q '"CondoNo"'; then
    echo "  stale: $PLUTO_FILE lacks CondoNo — refetching"
    rm -f "$PLUTO_FILE"
fi
if [ -f "$PVAD_FILE" ] && ! head -1 "$PVAD_FILE" | grep -q "condo_number"; then
    echo "  stale: $PVAD_FILE lacks condo_number — refetching"
    rm -f "$PVAD_FILE"
fi

echo "=== Stage 01: PLUTO ==="
[ -f "$PLUTO_FILE" ] && echo "  cached: $PLUTO_FILE" || python3 01_fetch_pluto.py ${PLUTO_ARGS[@]+"${PLUTO_ARGS[@]}"}

echo "=== Stage 02: PVAD ==="
[ -f "$PVAD_FILE" ] && echo "  cached: $PVAD_FILE" || python3 02_fetch_pvad.py ${PVAD_ARGS[@]+"${PVAD_ARGS[@]}"}

echo "=== Stage 03: tax bill + ETR ==="
python3 03_compute_tax_bill.py --pluto "$PLUTO_FILE" --pvad "$PVAD_FILE"

echo "=== Stage 04: aggregate ==="
python3 04_aggregate.py

if [ "$SKIP_TILES" -eq 0 ]; then
    echo "=== Stage 05: tippecanoe ==="
    bash 05_build_tiles.sh
fi

if [ "$SKIP_UPLOAD" -eq 0 ] && [ "$SKIP_TILES" -eq 0 ]; then
    echo "=== Stage 06: upload ==="
    python3 06_upload_r2.py
fi

echo "=== Done ==="
