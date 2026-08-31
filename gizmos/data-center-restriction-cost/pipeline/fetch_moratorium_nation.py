"""Fetch the Moratorium Nation inventory CSV (CC-BY-4.0) and filter to
data-center sector rows.

Discovery order:
  0. canonical raw.githubusercontent URL (verified 2026-08-08)
  1. scrape the project index page for *.csv hrefs
  2. GitHub API tree listing -> raw.githubusercontent.com

Outputs:
  raw/moratorium_inventory.csv  (full file, cached)
  raw/mn_dc_rows.csv            (rows whose sectors array contains "data_center",
                                 original columns preserved)

QA: filtered count must be >= config.MN_DC_MIN_ROWS (hard fail);
    warn above config.MN_DC_WARN_ROWS.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys

import config


def _discover_csv_urls() -> list[str]:
    """Return candidate CSV URLs, canonical first."""
    urls = [config.MN_CSV_CANONICAL]

    # Fallback (a): index page scan for csv hrefs
    try:
        html = config.http_get(config.MN_INDEX_URL).decode("utf-8", "replace")
        for href in re.findall(r'href="([^"]+\.csv[^"]*)"', html, flags=re.I):
            url = href if href.startswith("http") else config.MN_SITE_BASE + href.lstrip("/")
            if url not in urls:
                urls.append(url)
    except RuntimeError as err:
        print(f"  [mn] index-page discovery failed (non-fatal): {err}")

    # Fallback (b): GitHub tree API
    try:
        tree = json.loads(config.http_get(config.MN_GH_TREE_URL).decode("utf-8"))
        for node in tree.get("tree", []):
            path = node.get("path", "")
            if path.lower().endswith(".csv") and "inventory" in path.lower():
                url = config.MN_GH_RAW_BASE + path
                if url not in urls:
                    urls.append(url)
    except (RuntimeError, json.JSONDecodeError) as err:
        print(f"  [mn] GitHub tree discovery failed (non-fatal): {err}")

    return urls


def _parse_sectors(raw: str) -> list[str]:
    """`sectors` is a JSON-array string with variable internal whitespace."""
    try:
        val = json.loads(raw or "[]")
        return [str(v) for v in val] if isinstance(val, list) else []
    except json.JSONDecodeError:
        # tolerate malformed rows: fall back to keyword scan
        return ["data_center"] if "data_center" in (raw or "") else []


def _is_dc_row(row: dict) -> bool:
    if "sectors" in row and (row.get("sectors") or "").strip():
        return "data_center" in _parse_sectors(row["sectors"])
    # If no sector/technology column exists, keyword-match across all fields.
    blob = " ".join(str(v) for v in row.values()).lower()
    return "data center" in blob or "data_center" in blob


def main() -> int:
    config.ensure_dirs()

    body = None
    for url in _discover_csv_urls():
        try:
            print(f"  [mn] fetching {url}")
            candidate = config.http_get(url)
            # sanity: parses as CSV with a plausible header
            head = candidate[:2048].decode("utf-8-sig", "replace")
            if "jurisdiction" in head and "," in head:
                body = candidate
                break
            print("  [mn] response did not look like the inventory CSV; trying next")
        except RuntimeError as err:
            print(f"  [mn] {err}")
    if body is None:
        print("  [mn] FATAL: could not retrieve the Moratorium Nation CSV from any source")
        return 1

    config.MN_RAW_CSV.write_bytes(body)

    text = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    rows = list(reader)
    dc_rows = [r for r in rows if _is_dc_row(r)]

    with open(config.MN_DC_ROWS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dc_rows)

    n = len(dc_rows)
    print(f"  [mn] total rows {len(rows)}; data-center rows {n} -> {config.MN_DC_ROWS_CSV.name}")
    if n < config.MN_DC_MIN_ROWS:
        print(f"  [mn] FATAL: data-center row count {n} < gate {config.MN_DC_MIN_ROWS}")
        return 1
    if n > config.MN_DC_WARN_ROWS:
        print(
            f"  [mn] WARN: data-center row count {n} > {config.MN_DC_WARN_ROWS}. "
            f"Expected: the sector filter keeps multi-sector instruments (e.g. "
            f"data_center+crypto) and pending/unverified rows, so it runs above the "
            f"tracker's published since-2023 adoption count "
            f"({config.MN_PUBLISHED_DC_TOTAL}). See DECISIONS.md."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
