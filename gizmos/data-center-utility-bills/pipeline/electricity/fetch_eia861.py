#!/usr/bin/env python3
"""Fetch EIA-861 inputs into data/raw/ (gitignored, re-fetchable).

Two sources, deliberately redundant:

1. PUDL (Catalyst Cooperative, CC-BY-4.0): cleaned, harmonized EIA-861 tables
   as parquet. This is the workhorse for the long panel because the pre-2012
   EIA files change layout almost every year and PUDL has already reconciled
   them.
2. Raw EIA zips for the most recent years. Used to (a) add any year PUDL has
   not ingested yet and (b) cross-check PUDL against the source on overlapping
   years, so a PUDL transcription error cannot silently enter the panel.

Run:  python3 -I pipeline/electricity/fetch_eia861.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

PUDL_BASE = "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/stable/"
PUDL_TABLES = [
    "core_eia861__yearly_sales",
    "core_eia861__yearly_service_territory",
    "core_eia861__yearly_utility_data_misc",
    "core_eia861__yearly_operational_data_misc",
    "core_eia861__yearly_operational_data_revenue",
    "core_eia861__yearly_balancing_authority",
    "core_eia861__assn_balancing_authority",
    "core_eia861__assn_utility",
    "core_eia861__yearly_short_form",
    # EIA's own schedule of mergers and acquisitions, 2007 on: a source for succession.csv
    "core_eia861__yearly_mergers",
]

EIA_BASE = "https://www.eia.gov/electricity/data/eia861/"
EIA_ZIPS = {
    2025: "zip/f8612025.zip",
    2024: "archive/zip/f8612024.zip",
    2023: "archive/zip/f8612023.zip",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "research-data-fetch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r, dest.open("wb") as f:
            last_modified = r.headers.get("Last-Modified")
            while chunk := r.read(1 << 20):
                f.write(chunk)
    except Exception as e:  # report and continue; missing optional tables are not fatal
        return {"url": url, "ok": False, "error": repr(e)}
    return {
        "url": url,
        "ok": True,
        "path": str(dest.relative_to(ROOT)),
        "bytes": dest.stat().st_size,
        "sha256": sha256(dest),
        "last_modified": last_modified,
    }


def main() -> int:
    manifest = {"fetched_at": datetime.now(timezone.utc).isoformat(), "files": []}
    for t in PUDL_TABLES:
        manifest["files"].append(fetch(f"{PUDL_BASE}{t}.parquet", RAW / "pudl" / f"{t}.parquet"))
    for year, rel in EIA_ZIPS.items():
        manifest["files"].append(fetch(EIA_BASE + rel, RAW / "eia861_zip" / f"f861{year}.zip"))
    out = ROOT / "data" / "frozen" / "fetch_manifest_eia861.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    bad = [f for f in manifest["files"] if not f["ok"]]
    for f in manifest["files"]:
        print(("ok  " if f["ok"] else "FAIL"), f["url"], f.get("bytes", f.get("error")))
    # The sales table and the newest raw zip are required; everything else is optional.
    required = {f"{PUDL_BASE}core_eia861__yearly_sales.parquet", EIA_BASE + EIA_ZIPS[2025]}
    return 1 if any(f["url"] in required for f in bad) else 0


if __name__ == "__main__":
    sys.exit(main())
