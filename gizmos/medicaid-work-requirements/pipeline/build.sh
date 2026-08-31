#!/usr/bin/env bash
# Orchestrator for the Medicaid Work Requirements pipeline.
#
# Usage:
#   ./build.sh                          # full nationwide rebuild
#   ./build.sh --sample-state PA        # fast local iteration on one state
#   ./build.sh --skip-tiles             # Python-only rerun (skip tippecanoe)
#   ./build.sh --skip-upload            # build everything locally, skip R2 push
#   ./build.sh --skip-grid              # use cached 1-mile grid from prior run
#   ./build.sh --from 04                # resume from stage 04
#
# See METHODOLOGY.md for what each stage does and config.py for parameters.

set -euo pipefail
cd "$(dirname "$0")"

# ---- args ------------------------------------------------------------------
SAMPLE_STATE=""
SKIP_TILES=0
SKIP_UPLOAD=0
SKIP_GRID=0
FROM_STAGE="01"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sample-state) SAMPLE_STATE="$2"; shift 2 ;;
        --skip-tiles) SKIP_TILES=1; shift ;;
        --skip-upload) SKIP_UPLOAD=1; shift ;;
        --skip-grid) SKIP_GRID=1; shift ;;
        --from) FROM_STAGE="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

export MWR_SAMPLE_STATE="$SAMPLE_STATE"

run_stage() {
    local stage="$1"
    local script="$2"
    if [[ "$stage" < "$FROM_STAGE" ]]; then
        echo "==> [skip] stage $stage ($script) — before --from $FROM_STAGE"
        return
    fi
    echo
    echo "============================================================"
    echo "==> Stage $stage: $script"
    echo "============================================================"
    if [[ "$script" == *.sh ]]; then
        bash "$script"
    else
        python3 "$script"
    fi
}

# ---- stages ----------------------------------------------------------------
run_stage 01 01_fetch_acs.py
run_stage 02 02_fetch_geometry.py
run_stage 03 03_fetch_admin_calibration.py
run_stage 04 04_compute_expansion_pool.py
# 04d (state ex parte capability scoring) runs before 04b/04c because both
# depend on per-state flags + scores to compute admin-failure rates.
run_stage 04d 04d_compile_state_ex_parte.py
# 04b populates the PUMS v2 cache (work-doc subgroup shares plus medically-frail,
# caregiver, and full-time-student weighted counts + subject_pool_weighted denom).
# 04e and 04c consume the v2 schema; 04b auto-detects and rebuilds v1 caches.
run_stage 04b 04b_fetch_pums_workdoc_breakdown.py
# 04e — per-state exemption-eligibility rates (PUMS + SAMHSA NSDUH + BJS NPS)
# consumed by 04c. Requires raw/manual/samhsa_nsduh_state_sud.csv and
# raw/manual/bjs_nps_state_releases.csv — see raw/manual/README.md.
run_stage 04e 04e_compute_state_exemption_rates.py
# 04f — benchmark validation of 04e rates against KFF/NCES/PPI (non-blocking;
# emits a console table and writes state_exemption_rates_validation.parquet).
run_stage 04f 04f_validate_state_exemption_rates.py
run_stage 04c 04c_build_exemption_breakdown.py
run_stage 05 05_apply_exemptions.py
run_stage 06 06_compute_burden_index.py
run_stage 07 07_aggregate.py
# 07b (loss-breakdown JSON) combines 04b + 04c + 04d into the file consumed by
# the MedicaidLossSankey component. Runs after 07 to use updated state totals.
run_stage 07b 07b_build_loss_breakdown.py
# 07c refreshes the shipped county GeoJSON (public/data/medicaid-counties.geojson)
# from the real county model in county_summary.parquet — and apportions 07b's
# bottom-up per-state loss to counties so the map's "Projected coverage loss"
# matches the Sankey/briefs/headline — so it must run AFTER 07b. It supersedes
# the placeholder seed from tools/bake-placeholder-counties-and-hexes.py and must
# run before stage 12, which reads the public geojson via lib/write_csv.py.
run_stage 07c 07c_build_public_counties.py

if [[ "$SKIP_GRID" -eq 0 ]]; then
    # Stage 08 (rewritten): resample tract metrics onto the NPE 1-mile hex mesh,
    # tract dasymetric-by-population, bottom-up per-state loss, identity/label
    # columns. Writes grid_1mi.geojson + grid_1mi_metrics.parquet. (08b is retired —
    # its loss/rate/working-age logic now lives in stage 08.)
    run_stage 08 08_resample_to_grid.py
    # Place labels (Tier A NYC NTA → B OSM → C Census place → D county) then
    # Medicaid landmarks. Each REWRITES grid_1mi.geojson in place, so they run
    # sequentially, after 08, before the label→parquet merge. (Repo-root tools/.)
    echo; echo "==> Baking place labels + landmarks onto grid_1mi.geojson"
    python3 ../../../tools/bake-medicaid-place-labels.py
    python3 ../../../tools/bake-medicaid-landmarks.py
    # Copy the baked place_*/landmark_* columns into grid_1mi_metrics.parquet so
    # stage 09 can label hexes from the parquet alone (never opens the giant GeoJSON).
    python3 ../../../tools/merge-grid-labels-into-parquet.py
    # Stage 09 (rewritten): aggregate the 1-mile grid onto a complete,
    # non-overlapping pointy-top 5-mile hex tiling (reads the parquet). Still emits
    # hex_20mi via the same tiler so stage 10/13's coarse_hex.pmtiles keep building.
    run_stage 09 09_build_coarse_hexes.py
    # 09b computes percentile_cutoffs (concentration slider) + the concentration
    # block, patched into medicaid-state-summary.json. Reads counties/grid/hex.
    run_stage 09b 09b_percentile_cutoffs.py
else
    echo "==> [skip] stages 08/labels/landmarks/merge/09/09b (--skip-grid)"
fi

if [[ "$SKIP_TILES" -eq 0 ]]; then
    run_stage 10 10_build_tiles.sh
else
    echo "==> [skip] stage 10 (--skip-tiles)"
fi

run_stage 11 11_build_state_csvs.py
run_stage 12 12_build_state_pdfs.py

if [[ "$SKIP_UPLOAD" -eq 0 ]]; then
    run_stage 13 13_upload_r2.py
else
    echo "==> [skip] stage 13 (--skip-upload)"
fi

echo
echo "==> Done."
