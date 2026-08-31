"""Stage 09b — percentile cutoffs (concentration slider) + concentration block.

The map's concentration slider dims every feature whose metric value falls below
a chosen percentile ("show me the top 20%"). The frontend (`cutoffFor` in
MedicaidWorkRequirementsMap.tsx) reads `summary.percentile_cutoffs[mode][primitive]
= {pctKey: value}` and nearest-key-matches the slider position. Until now that
block was absent, so the slider was inert above 50%. This stage computes it for
every (mode × primitive) from the same data the map paints.

It also computes the `concentration` block (share of subject enrollees in the
top-N counties + p90/95/99), which backs the headline concentration callout
(`concentrationCalloutText`) — also absent until now.

Percentiles are unweighted over EXACTLY the features each layer draws (counties
geojson; all grid cells in the metrics parquet; all 5-mi hexes), because the
renderer compares each feature's raw value to the cutoff with no weighting.

Patches both the shipped SPA copy (public/data/medicaid-state-summary.json — what
the frontend fetches) and the build mirror (output/state_summary.json), additively.
Idempotent: overwrites the two keys, preserves everything else.

Run after stage 09:  python 09b_percentile_cutoffs.py
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np
import pandas as pd

import config

COUNTIES_GEOJSON = config.PUBLIC_DATA_DIR / "medicaid-counties.geojson"
HEX5_GEOJSON = config.OUTPUT_DIR / "hex_5mi.geojson"
GRID_METRICS = config.OUTPUT_DIR / "grid_1mi_metrics.parquet"

PUBLIC_SUMMARY = config.PUBLIC_DATA_DIR / "medicaid-state-summary.json"
OUTPUT_SUMMARY = config.OUTPUT_DIR / "state_summary.json"

# mode key (frontend) -> the feature property that mode paints / filters on.
MODE_PROPERTY = {
    "subject_count": "subject_count_strict",
    "subject_rate": "subject_rate",
    "burden_index": "burden_index_centered",
    "loss_exposure": "loss_exposure_strict",
}
PCT_KEYS = [50, 60, 67, 70, 75, 80, 85, 90, 95, 97, 99]
TOP_N = [5, 10, 25, 50, 100, 250, 500]
NATIONAL_COUNTIES = 3109  # must match medicaidConcentration.ts


def _geojson_frame(path) -> pd.DataFrame:
    gj = json.loads(path.read_text())
    return pd.DataFrame([f.get("properties", {}) for f in gj.get("features", [])])


def _values(frame: pd.DataFrame, prop: str) -> np.ndarray:
    if prop not in frame.columns:
        return np.array([])
    return pd.to_numeric(frame[prop], errors="coerce").dropna().to_numpy()


def _cutoffs_for(frame: pd.DataFrame) -> dict:
    """percentile_cutoffs sub-tree for one primitive: {mode: {pctKey: value}}."""
    out = {}
    for mode, prop in MODE_PROPERTY.items():
        vals = _values(frame, prop)
        if vals.size == 0:
            continue  # frontend cutoffFor returns null gracefully
        out[mode] = {str(p): float(np.percentile(vals, p)) for p in PCT_KEYS}
    return out


def _concentration(counties: pd.DataFrame) -> dict:
    subj = pd.to_numeric(counties["subject_count_strict"], errors="coerce").fillna(0.0)
    subj = subj.sort_values(ascending=False).to_numpy()
    total = float(subj.sum())
    cum = np.cumsum(subj)
    share = {str(n): float(cum[min(n, len(subj)) - 1] / total) for n in TOP_N if len(subj)}
    return {
        "share_in_top_n_counties": share,
        "p90_county_subject_count": float(np.percentile(subj, 90)),
        "p95_county_subject_count": float(np.percentile(subj, 95)),
        "p99_county_subject_count": float(np.percentile(subj, 99)),
    }


def _patch(path, percentile_cutoffs: dict, concentration: dict) -> None:
    if not path.exists():
        print(f"  (skip {path} — not present)")
        return
    d = json.loads(path.read_text())
    d["percentile_cutoffs"] = percentile_cutoffs
    d["concentration"] = concentration
    path.write_text(json.dumps(d, indent=2))
    print(f"-> patched {path.relative_to(config.REPO_ROOT)}")


def main() -> None:
    for p in (COUNTIES_GEOJSON, HEX5_GEOJSON, GRID_METRICS, PUBLIC_SUMMARY):
        if not p.exists():
            print(f"ERROR: {p} missing.", file=sys.stderr)
            sys.exit(1)

    print("Loading layers...")
    counties = _geojson_frame(COUNTIES_GEOJSON)
    hex5 = _geojson_frame(HEX5_GEOJSON)
    grid = pd.read_parquet(GRID_METRICS, columns=list(MODE_PROPERTY.values()))
    print(f"  counties={len(counties):,}  hex5mi={len(hex5):,}  grid={len(grid):,}")

    cutoffs = {}  # mode -> primitive -> {pct: value}
    sources = {"counties": counties, "hex5mi": hex5, "grid": grid}
    for prim, frame in sources.items():
        sub = _cutoffs_for(frame)
        for mode, pcts in sub.items():
            cutoffs.setdefault(mode, {})[prim] = pcts

    concentration = _concentration(counties)

    _report(cutoffs, concentration)

    _patch(PUBLIC_SUMMARY, cutoffs, concentration)
    _patch(OUTPUT_SUMMARY, cutoffs, concentration)


def _report(cutoffs: dict, conc: dict) -> None:
    print("\n--- percentile_cutoffs (mode × primitive present) -----------------")
    for mode in MODE_PROPERTY:
        prims = cutoffs.get(mode, {})
        bits = []
        for prim in ("counties", "hex5mi", "grid"):
            if prim in prims:
                p50 = prims[prim]["50"]; p90 = prims[prim]["90"]; p99 = prims[prim]["99"]
                bits.append(f"{prim}: p50={p50:.3g} p90={p90:.3g} p99={p99:.3g}")
        print(f"  {mode:14s} " + " | ".join(bits))
    print("  QA targets (config comments): subject_count grid p50≈2/p99≈325, "
          "hex p50≈55; counties p50≈2.3k")

    print("\n--- concentration --------------------------------------------------")
    share = conc["share_in_top_n_counties"]
    for n, s in share.items():
        print(f"  top {int(n):>4} counties ({int(n)/NATIONAL_COUNTIES*100:4.1f}% of "
              f"{NATIONAL_COUNTIES}) -> {s*100:5.1f}% of subject enrollees")
    # Verify the tour's hardcoded "85% in 16% of counties" against real data.
    for tn, s in share.items():
        if s >= 0.70:
            print(f"  callout (≥70%): {s*100:.0f}% live in top {tn} "
                  f"({int(tn)/NATIONAL_COUNTIES*100:.1f}% of counties)")
            break
    n16 = int(round(0.16 * NATIONAL_COUNTIES))
    near = min(share.items(), key=lambda kv: abs(int(kv[0]) - n16))
    print(f"  tour check: top {near[0]} (~16% of counties) holds {float(near[1])*100:.0f}% "
          f"(tour copy says 85% in 16%)")
    print("-------------------------------------------------------------------\n")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"Stage 09b done in {time.time() - t0:.1f}s")
