"""Fetch datacentertracker.org's dataset (CC BY 4.0). NON-FATAL by design:
any failure writes raw/dct_status.json {"dct_available": false, ...} and
exits 0 — the build proceeds without the DCT layer.

The site's advertised CSV/JSON downloads are client-side blobs generated in
js/app.js from data/fights.json; there is no static CSV endpoint (verified
2026-08-08). We fetch fights.json directly, with a homepage/JS scan as
fallback discovery in case the endpoint moves.

Outputs:
  raw/dct_fights.json            (full dataset, cached)
  raw/dct_status.json            ({"dct_available": bool, ...})
  raw/dct-spotcheck-sample.csv   (25 seeded-random rows for manual spot-check)
"""
from __future__ import annotations

import csv
import json
import random
import re
import sys

import config

SPOTCHECK_N = 25
SPOTCHECK_SEED = 17  # reproducible sample
SPOTCHECK_COLS = [
    "id", "jurisdiction", "state", "county", "action_type", "date", "status",
    "scope", "authority_level", "company", "project_name", "megawatts",
    "investment_million_usd", "summary", "sources",
]


def _discover_urls() -> list[str]:
    urls = [config.DCT_FIGHTS_URL]
    try:
        html = config.http_get(config.DCT_HOME_URL).decode("utf-8", "replace")
        candidates = re.findall(
            r'(?:href|src)="([^"]*(?:\.csv|\.json|export|api)[^"]*)"', html, flags=re.I
        )
        # also scan referenced same-site scripts for fetch()/data paths
        for script in re.findall(r'src="(js/[^"]+\.js[^"]*)"', html):
            try:
                js = config.http_get(config.DCT_HOME_URL + script).decode("utf-8", "replace")
                candidates += re.findall(r"""['"]([^'"]*data/[^'"]*\.json)['"]""", js)
                candidates += re.findall(r"""fetch\(['"]([^'"]+)['"]\)""", js)
            except RuntimeError:
                pass
        for c in candidates:
            if c.startswith("http") and "datacentertracker" not in c:
                continue  # third-party asset
            url = c if c.startswith("http") else config.DCT_HOME_URL + c.lstrip("/")
            if url not in urls and ("mask" not in url):
                urls.append(url)
    except RuntimeError as err:
        print(f"  [dct] homepage discovery failed (non-fatal): {err}")
    return urls


def _write_status(available: bool, **extra) -> None:
    payload = {"dct_available": available, "retrieved": config.SNAPSHOT_DATE, **extra}
    config.DCT_STATUS_JSON.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    config.ensure_dirs()
    data = None
    used_url = None
    last_err = None
    for url in _discover_urls():
        try:
            print(f"  [dct] fetching {url}")
            body = config.http_get(url)
            parsed = json.loads(body.decode("utf-8"))
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) \
                    and "jurisdiction" in parsed[0]:
                data = parsed
                used_url = url
                config.DCT_RAW_JSON.write_bytes(body)
                break
            print("  [dct] response was JSON but not the fights dataset; trying next")
        except (RuntimeError, json.JSONDecodeError, UnicodeDecodeError) as err:
            last_err = err
            print(f"  [dct] {err}")

    if data is None:
        _write_status(False, error=str(last_err or "no candidate URL yielded the dataset"))
        print("  [dct] unavailable — build will proceed without the DCT layer (non-fatal)")
        return 0

    # 25-row seeded-random sample for a later manual primary-document spot-check
    rng = random.Random(SPOTCHECK_SEED)
    sample = rng.sample(data, min(SPOTCHECK_N, len(data)))
    with open(config.DCT_SPOTCHECK_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SPOTCHECK_COLS, extrasaction="ignore")
        writer.writeheader()
        for row in sample:
            flat = dict(row)
            for key in ("action_type", "sources"):
                if isinstance(flat.get(key), list):
                    flat[key] = "; ".join(str(x) for x in flat[key])
            writer.writerow(flat)

    _write_status(True, url=used_url, rows=len(data),
                  spotcheck_file=config.DCT_SPOTCHECK_CSV.name)
    print(f"  [dct] cached {len(data)} rows; spot-check sample -> {config.DCT_SPOTCHECK_CSV.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
