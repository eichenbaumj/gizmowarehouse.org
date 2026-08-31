#!/usr/bin/env python3
"""Stage 02 — fetch PVAD (Property Valuation and Assessment Data) from NYC DOF.

The current dataset is 8y4t-faws on Socrata, updated with the FY26
tentative roll in March 2026. (The legacy yjxr-fw8i set has been
unmaintained since 2022.) One row per parid (BBL + subident). Provides
current market value (curmkttot, the FULLVAL equivalent), current
billable AV (curtxbtot), tax class, and exemptions. Joined to PLUTO on
BBL in stage 03.

Usage:
    python 02_fetch_pvad.py                      # full citywide
    python 02_fetch_pvad.py --boro 3             # one borough (1=MN, 2=BX, 3=BK, 4=QN, 5=SI)
    python 02_fetch_pvad.py --boro 3 --year 2025 # one borough, one tax year
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import quote

import requests
from tqdm import tqdm

import config


def fetch(where_clause: str | None, out_path, max_retries: int = 4) -> int:
    """Download the PVAD CSV. Retries on transient Socrata read timeouts —
    the citywide dump is ~2 GB and a long-running stream gets dropped
    server-side once or twice on a typical run."""
    base = (
        f"https://data.cityofnewyork.us/resource/{config.PVAD_DATASET_ID}.csv?"
        f"$select={','.join(config.PVAD_FIELDS)}&$limit=10000000"
    )
    if where_clause:
        base += "&$where=" + quote(where_clause)
    print(f"GET {base[:180]}{'...' if len(base) > 180 else ''}")

    for attempt in range(1, max_retries + 1):
        try:
            with requests.get(base, stream=True, timeout=(30, 120)) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                bar = tqdm(
                    total=total or None,
                    unit="B",
                    unit_scale=True,
                    desc="pvad",
                    disable=not sys.stderr.isatty(),
                )
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
                            bar.update(len(chunk))
                bar.close()
            return out_path.stat().st_size
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            partial = out_path.stat().st_size / (1 << 20) if out_path.exists() else 0
            print(
                f"  attempt {attempt}/{max_retries} failed after "
                f"{partial:.0f} MB: {type(e).__name__}: {str(e)[:150]}",
                file=sys.stderr,
            )
            if out_path.exists():
                out_path.unlink()
            if attempt == max_retries:
                raise
    raise RuntimeError("unreachable")


def fetch_metadata() -> dict:
    r = requests.get(config.PVAD_METADATA_URL, timeout=30)
    r.raise_for_status()
    j = r.json()
    return {
        "dataset_id": config.PVAD_DATASET_ID,
        "dataset_name": j.get("name"),
        "data_updated_at": j.get("dataUpdatedAt") or j.get("rowsUpdatedAt"),
        "metadata_updated_at": j.get("metadataUpdatedAt"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boro", help="1=MN, 2=BX, 3=BK, 4=QN, 5=SI")
    ap.add_argument("--year", help="tax year (e.g. 2026)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    where_parts: list[str] = []
    if args.boro:
        where_parts.append(f"boro='{args.boro}'")
    if args.year:
        where_parts.append(f"year='{args.year}'")
    where = " AND ".join(where_parts) if where_parts else None

    tag = "_".join(filter(None, [f"boro{args.boro}" if args.boro else None, f"y{args.year}" if args.year else None]))
    out = config.RAW_DIR / (args.out or (f"pvad.{tag}.csv" if tag else "pvad.csv"))

    size = fetch(where, out)
    rows = sum(1 for _ in open(out)) - 1
    print(f"Wrote {out} ({size / (1<<20):.1f} MB, {rows:,} rows)")

    meta = fetch_metadata()
    (config.RAW_DIR / "pvad.meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Dataset last updated: {meta['data_updated_at']}")


if __name__ == "__main__":
    main()
