#!/usr/bin/env bash
# Orchestrates the full public-private compensation pipeline, raw pull -> shipped JSON.
# Reads CENSUS_API_KEY from repo-root .env.local. Stages are individually resumable
# (the PUMS pull skips cached state-years). Run from this directory.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 01 macro (BLS ECI + FRED) =="      ; python3 01_fetch_macro.py
echo "== 02 shape (CES + ASPEP) =="         ; python3 02_fetch_shape.py
echo "== 03 PUMS pull (heavy; resumable) ==" ; python3 03_fetch_pums.py
echo "== 05 compute cells =="               ; python3 05_compute_cells.py
echo "== 06 model gaps =="                  ; python3 06_model_gaps.py
echo "== 07 workforce composition =="       ; python3 07_workforce_composition.py
echo "== 08a city payroll pull =="          ; python3 08a_fetch_cities.py
echo "== 08b metro private comparator =="   ; python3 08b_metro_comparator.py
echo "== 08c city cells vs comparator =="   ; python3 08c_city_cells.py
echo "== 11 assemble shipped JSON =="       ; python3 11_build_json.py
echo "Pipeline complete. Shipped JSON in public/data/compgap/."

# title->domain classification lives in city_lib.py + crosswalks/title_keywords.csv.
# Future: OEWS-by-ownership p90 tail; CA State Controller GCC bundle for more cities.
# (The metro-PUMA private comparator is implemented in stage 08b.)
