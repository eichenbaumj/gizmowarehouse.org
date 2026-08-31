#!/usr/bin/env python3
"""Diagnose current 1-mi cell labels in the Medicaid Work Requirements grid.

Reads the baked grid_1mi.geojson, ranks cells by subject_count × total_pop (so
a bad label on a high-exposure cell counts more than a bad label on a rural
empty cell), reconstructs the popup label the way the frontend would, and
prints the top N labels plus aggregate stats.

Optionally compares before/after by reading a second --baseline grid file.

Run:
    python3 tools/diagnose-medicaid-labels.py
    python3 tools/diagnose-medicaid-labels.py --top 200
    python3 tools/diagnose-medicaid-labels.py --grid path/to/grid_1mi.geojson
    python3 tools/diagnose-medicaid-labels.py --baseline path/to/old.geojson
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import pyogrio

REPO = Path(__file__).resolve().parent.parent
DEFAULT_GRID = REPO / "gizmos/medicaid-work-requirements/pipeline/output/grid_1mi.geojson"

# Cities that are too coarse a label — if a cell labels as "Near {one of these}"
# without further neighborhood specificity, flag as low-information.
COARSE_CITIES = {
    ("Chicago", "IL"), ("New York", "NY"), ("Los Angeles", "CA"),
    ("Philadelphia", "PA"), ("Phoenix", "AZ"), ("Houston", "TX"),
    ("San Antonio", "TX"), ("Detroit", "MI"), ("San Diego", "CA"),
    ("San Jose", "CA"), ("Dallas", "TX"), ("Indianapolis", "IN"),
    ("Jacksonville", "FL"), ("San Francisco", "CA"), ("Columbus", "OH"),
    ("Fort Worth", "TX"), ("Charlotte", "NC"), ("Seattle", "WA"),
    ("Denver", "CO"), ("Washington", "DC"), ("Nashville", "TN"),
    ("Boston", "MA"), ("El Paso", "TX"), ("Portland", "OR"),
    ("Las Vegas", "NV"), ("Oklahoma City", "OK"), ("Memphis", "TN"),
    ("Louisville", "KY"), ("Baltimore", "MD"), ("Milwaukee", "WI"),
    ("Albuquerque", "NM"), ("Tucson", "AZ"), ("Fresno", "CA"),
    ("Sacramento", "CA"), ("Kansas City", "MO"), ("Mesa", "AZ"),
    ("Atlanta", "GA"), ("Omaha", "NE"), ("Colorado Springs", "CO"),
    ("Raleigh", "NC"), ("Long Beach", "CA"), ("Virginia Beach", "VA"),
    ("Miami", "FL"), ("Oakland", "CA"), ("Minneapolis", "MN"),
    ("Tulsa", "OK"), ("Bakersfield", "CA"), ("Wichita", "KS"),
    ("Arlington", "TX"), ("Aurora", "CO"), ("Tampa", "FL"),
    ("New Orleans", "LA"), ("Cleveland", "OH"), ("Honolulu", "HI"),
    ("Anaheim", "CA"), ("Lexington", "KY"), ("Stockton", "CA"),
    ("Pittsburgh", "PA"), ("Newark", "NJ"), ("Buffalo", "NY"),
    ("Cincinnati", "OH"), ("St. Louis", "MO"), ("Saint Paul", "MN"),
}


def build_label(row: dict) -> str:
    """Mimic the frontend popup title for a grid cell."""
    place = (row.get("nearest_place_name") or "").strip()
    place_st = (row.get("nearest_place_state") or "").strip()
    landmark = (row.get("landmark_name") or "").strip()
    county = (row.get("parent_county_name") or "").strip()
    county_st = (row.get("parent_state_abbr") or "").strip()
    state = place_st or county_st
    if place:
        head = f"Near {place}, {state}".rstrip(", ")
        if landmark:
            return f"{head} · by {landmark}"
        return head
    if landmark:
        return f"Near {landmark}, {state}".rstrip(", ")
    return f"1-mi cell · {county or '—'} County, {county_st}".rstrip(", ")


def classify(row: dict) -> str:
    """Bucket each cell's label quality."""
    place = (row.get("nearest_place_name") or "").strip()
    place_st = (row.get("nearest_place_state") or "").strip()
    landmark = (row.get("landmark_name") or "").strip()
    if not place and not landmark:
        return "no_place_no_landmark"
    if place and (place, place_st) in COARSE_CITIES and not landmark:
        return "coarse_city_no_landmark"
    if place and (place, place_st) in COARSE_CITIES and landmark:
        return "coarse_city_with_landmark"
    if not place:
        return "landmark_only"
    if not landmark:
        return "place_only"
    return "place_and_landmark"


def load_grid(path: Path) -> pd.DataFrame:
    print(f"Loading {path.name} ({path.stat().st_size / 1e6:.0f} MB)...", file=sys.stderr)
    t0 = time.time()
    df = pyogrio.read_dataframe(path, read_geometry=False, use_arrow=True)
    print(f"  {len(df):,} rows in {time.time() - t0:.1f}s", file=sys.stderr)
    return df


def summarize(df: pd.DataFrame, label_col: str = "label") -> None:
    bucket = df["bucket"].value_counts()
    total = len(df)
    print(f"\nLabel-quality breakdown ({total:,} cells total):")
    for k in [
        "place_and_landmark", "place_only", "landmark_only",
        "coarse_city_with_landmark", "coarse_city_no_landmark",
        "no_place_no_landmark",
    ]:
        n = int(bucket.get(k, 0))
        pct = 100 * n / total if total else 0
        print(f"  {k:<30s} {n:>10,}  ({pct:>5.1f}%)")

    # Same breakdown weighted by subject_count_strict (the harm-weighting)
    subj_total = float(df["subject_count_strict"].sum())
    print(f"\nLabel-quality weighted by subject_count_strict "
          f"({subj_total:,.0f} subjects total):")
    by_bucket = df.groupby("bucket")["subject_count_strict"].sum()
    for k in [
        "place_and_landmark", "place_only", "landmark_only",
        "coarse_city_with_landmark", "coarse_city_no_landmark",
        "no_place_no_landmark",
    ]:
        n = float(by_bucket.get(k, 0))
        pct = 100 * n / subj_total if subj_total else 0
        print(f"  {k:<30s} {n:>12,.0f}  ({pct:>5.1f}%)")


def print_top(df: pd.DataFrame, n: int, header: str) -> None:
    print(f"\n{header}")
    print("-" * 110)
    fmt = "{:>7} {:>8} {:>7} {:>6}  {}"
    print(fmt.format("subj", "pop", "rate%", "bucket", "label"))
    print("-" * 110)
    for _, r in df.head(n).iterrows():
        print(fmt.format(
            int(r["subject_count_strict"]),
            int(r["total_pop"]),
            f"{100 * float(r['subject_rate']):.1f}",
            r["bucket"][:6],
            r["label"][:90],
        ))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default=str(DEFAULT_GRID),
                    help="Path to grid_1mi.geojson")
    ap.add_argument("--baseline", default=None,
                    help="Optional second grid path for before/after compare")
    ap.add_argument("--top", type=int, default=100,
                    help="Show top N cells by subject_count")
    ap.add_argument("--coarse-top", type=int, default=50,
                    help="Show top N cells among the 'coarse city' bucket")
    args = ap.parse_args()

    grid_path = Path(args.grid)
    if not grid_path.exists():
        print(f"ERROR: {grid_path} missing.", file=sys.stderr)
        sys.exit(1)

    df = load_grid(grid_path)
    df["label"] = df.apply(build_label, axis=1)
    df["bucket"] = df.apply(classify, axis=1)
    df["impact"] = df["subject_count_strict"].fillna(0) * df["total_pop"].fillna(0)
    df = df.sort_values("subject_count_strict", ascending=False)

    summarize(df)

    coarse = df[df["bucket"].isin({"coarse_city_no_landmark", "coarse_city_with_landmark"})]
    coarse = coarse.sort_values("subject_count_strict", ascending=False)

    print_top(df, args.top, f"Top {args.top} cells by subject_count_strict (any bucket):")
    print_top(coarse, args.coarse_top,
              f"Top {args.coarse_top} cells in COARSE-CITY buckets (where neighborhood labels matter most):")

    if args.baseline:
        base_path = Path(args.baseline)
        if not base_path.exists():
            print(f"\nWARN: baseline {base_path} missing — skipping compare", file=sys.stderr)
        else:
            base = load_grid(base_path)
            base["label"] = base.apply(build_label, axis=1)
            base["bucket"] = base.apply(classify, axis=1)
            merged = df.merge(
                base[["cell_id", "label", "bucket"]].rename(
                    columns={"label": "label_old", "bucket": "bucket_old"}
                ),
                on="cell_id",
                how="left",
            )
            changed = merged[merged["label"] != merged["label_old"]]
            print(f"\nLabel changes vs baseline: {len(changed):,} cells "
                  f"({100*len(changed)/len(merged):.1f}%)")
            sample = changed.sort_values("subject_count_strict", ascending=False).head(30)
            print("\nLargest-impact label changes (top 30):")
            print("-" * 110)
            for _, r in sample.iterrows():
                print(f"  subj={int(r['subject_count_strict']):>6}  "
                      f"OLD: {r['label_old'][:50]:<52s}  NEW: {r['label'][:50]}")


if __name__ == "__main__":
    main()
