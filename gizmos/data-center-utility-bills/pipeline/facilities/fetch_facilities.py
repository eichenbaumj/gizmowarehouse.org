#!/usr/bin/env python3
"""Fetch data-center facility sources into data/raw/facilities/ (gitignored).

Sources and what each is trusted for:

  osm       OpenStreetMap objects tagged as data centers in the US (ODbL).
            This is the upstream source of the PNNL IM3 Open Source Data
            Center Atlas. Trusted for location and footprint, NOT for dates
            or load.
  epoch     Epoch AI Frontier Data Centers (CC BY 4.0). About a hundred very
            large AI sites with construction timelines from imagery and
            permits. Trusted for dates and load at the sites it covers.
  bi        Business Insider's 2025 census built from state air permits for
            backup generators. No license is stated, so the file stays in
            data/raw/ and is never committed or redistributed. We use it for
            derived variables only (permit year, generator capacity) and cite
            it. Trusted for existence and rough size; permit year is when a
            generator was permitted, not when the site was energized.

Run:  python3 -I pipeline/facilities/fetch_facilities.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "facilities"
UA = {"User-Agent": "research-data-fetch/1.0"}

OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = """
[out:json][timeout:600];
area["ISO3166-1"="US"][admin_level=2]->.us;
(
  nwr["telecom"="data_center"](area.us);
  nwr["building"="data_center"](area.us);
  nwr["man_made"="data_center"](area.us);
);
out center tags meta;
"""

SIMPLE = {
    "epoch/data_centers.zip": "https://epoch.ai/data/data_centers/data_centers.zip",
    "bi/index.js": "https://tbimedia.s3.us-east-1.amazonaws.com/bistudios/_00/dev_edit/"
                   "graphics/2025/09/2025-09-datacenters-map-table/index.js",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save(req: urllib.request.Request, dest: Path, timeout: int) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, dest.open("wb") as f:
            lm = r.headers.get("Last-Modified")
            while chunk := r.read(1 << 20):
                f.write(chunk)
    except Exception as e:
        return {"url": req.full_url, "ok": False, "error": repr(e)}
    return {"url": req.full_url, "ok": True, "path": str(dest.relative_to(ROOT)),
            "bytes": dest.stat().st_size, "sha256": sha256(dest), "last_modified": lm}


def main() -> int:
    manifest = {"fetched_at": datetime.now(timezone.utc).isoformat(), "files": []}
    for rel, url in SIMPLE.items():
        manifest["files"].append(save(urllib.request.Request(url, headers=UA), RAW / rel, 180))
    body = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode()
    manifest["files"].append(
        save(urllib.request.Request(OVERPASS, data=body, headers=UA), RAW / "osm" / "us_data_centers.json", 900))
    (ROOT / "data" / "frozen" / "fetch_manifest_facilities.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for f in manifest["files"]:
        print(("ok  " if f["ok"] else "FAIL"), f["url"][:90], f.get("bytes", f.get("error")))
    return 0 if all(f["ok"] for f in manifest["files"]) else 1


if __name__ == "__main__":
    sys.exit(main())
