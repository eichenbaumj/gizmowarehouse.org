"""Stage 13 — upload tile + summary artifacts to Cloudflare R2.

Copies the pattern from gizmos/nyc-property-tax-map/pipeline/06_upload_r2.py.
Uses the same gizmo-warehouse-data bucket, custom domain at
data.gizmowarehouse.org, with prefix `medicaid-work-requirements/`.

Required environment (in .env.local at repo root):
  R2_ACCOUNT_ID
  R2_BUCKET
  R2_S3_ENDPOINT
  R2_ACCESS_KEY_ID
  R2_SECRET_ACCESS_KEY
  R2_PUBLIC_URL  (optional, for echoing share URLs)

Run: python 13_upload_r2.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

import config

load_dotenv(config.REPO_ROOT / ".env.local")

ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
BUCKET = os.environ.get("R2_BUCKET", config.R2_BUCKET)
ENDPOINT = os.environ.get("R2_S3_ENDPOINT")
ACCESS_KEY = os.environ.get("R2_ACCESS_KEY_ID")
SECRET_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
PUBLIC_BASE = os.environ.get("R2_PUBLIC_URL", config.R2_PUBLIC_BASE)

REQUIRED = {"R2_ACCOUNT_ID": ACCOUNT_ID, "R2_S3_ENDPOINT": ENDPOINT,
            "R2_ACCESS_KEY_ID": ACCESS_KEY, "R2_SECRET_ACCESS_KEY": SECRET_KEY}
missing = [k for k, v in REQUIRED.items() if not v]
if missing:
    print(
        f"ERROR: missing R2 credentials in .env.local: {', '.join(missing)}\n"
        "See tools/HOSTING_DATA.md for setup.",
        file=sys.stderr,
    )
    sys.exit(1)

# Files to upload, keyed by their R2 object key under the prefix.
TILES_DIR = config.OUTPUT_DIR
BRIEFS_DIR = config.PUBLIC_ASSETS_DIR / "medicaid-briefs"
DATA_DIR = config.PUBLIC_ASSETS_DIR / "medicaid-data"

# Each entry is (local_path, r2_key, category). Categories let a partial
# re-deploy push only what changed, e.g. `--only briefs,json` after a PDF
# re-bake (default: upload everything).
UPLOADS = []

# Only the two tilesets the SPA actually reads (config.gridPmtilesUrl +
# config.hex5miGeoJsonUrl) are versioned and uploaded. The unversioned
# grid.pmtiles, counties.pmtiles, and coarse_hex.pmtiles are not consumed by the
# SPA, so we don't push them (keeps a version bump from touching live objects).
# v7 (2026-06-25): grid rebuilt to include WI/GA subject-via-1115-waiver cells +
# carries the subject_via_waiver property; bumped from v6 in lockstep with the
# config URL. Old v6 stays on R2 until the config bump deploys.
for name in ["grid.v7.pmtiles"]:
    p = TILES_DIR / name
    if p.exists():
        UPLOADS.append((p, name, "tiles"))

# 5-mi hex GeoJSON is the frontend's hex layer source (config.hex5miGeoJsonUrl).
# R2 objects are served `immutable`, so a stable name + changed bytes would serve
# stale data — the key is versioned (hex-5mi.v4.geojson) and bumped in the config
# in lockstep with grid.v7. v4 (2026-06-25): now includes WI/GA waiver cells.
HEX5_GEOJSON = TILES_DIR / "hex_5mi.geojson"
if HEX5_GEOJSON.exists():
    UPLOADS.append((HEX5_GEOJSON, "hex-5mi.v4.geojson", "tiles"))

for name in ["state_summary.json", "medicaid-loss-breakdown.json"]:
    p = TILES_DIR / name
    if p.exists():
        UPLOADS.append((p, name, "json"))

# Also upload the SPA-shipped versions from public/data so the R2 mirror stays
# in sync. (The SPA primarily reads /data/* relative URLs, but external
# consumers fetch from data.gizmowarehouse.org/medicaid-work-requirements/.)
PUBLIC_LOSS_BREAKDOWN = config.PUBLIC_DATA_DIR / "medicaid-loss-breakdown.json"
if PUBLIC_LOSS_BREAKDOWN.exists():
    UPLOADS.append((PUBLIC_LOSS_BREAKDOWN, "medicaid-loss-breakdown.json", "json"))

if BRIEFS_DIR.exists():
    for p in BRIEFS_DIR.glob("*.pdf"):
        UPLOADS.append((p, f"briefs/{p.name}", "briefs"))

if DATA_DIR.exists():
    for p in DATA_DIR.glob("*.csv"):
        UPLOADS.append((p, f"data/{p.name}", "csv"))

CATEGORIES = {"tiles", "json", "briefs", "csv"}


def main(only: set[str] | None = None, skip: set[str] | None = None) -> None:
    import boto3
    from botocore.config import Config as BotoConfig

    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )

    uploads = UPLOADS
    if only:
        uploads = [u for u in uploads if u[2] in only]
    if skip:
        uploads = [u for u in uploads if u[2] not in skip]

    if not uploads:
        print("Nothing to upload — pipeline outputs missing or filtered out.")
        return

    selected = only if only else (CATEGORIES - (skip or set()))
    print(f"Uploading {len(uploads)} object(s) [{', '.join(sorted(selected))}] to s3://{BUCKET}/{config.R2_PREFIX}/...")
    for local, key, _cat in uploads:
        full_key = f"{config.R2_PREFIX}/{key}"
        size_mb = local.stat().st_size / 1e6
        print(f"  -> {full_key:60s}  ({size_mb:6.2f} MB)")
        s3.upload_file(
            str(local),
            BUCKET,
            full_key,
            ExtraArgs={
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )

    print(f"\nPublic URLs under: {PUBLIC_BASE}/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Upload Medicaid artifacts to R2.")
    ap.add_argument("--only", default=None,
                    help="Comma-separated categories to upload (tiles,json,briefs,csv). Default: all.")
    ap.add_argument("--skip", default=None,
                    help="Comma-separated categories to skip.")
    args = ap.parse_args()

    def _parse(s):
        if not s:
            return None
        vals = {x.strip() for x in s.split(",") if x.strip()}
        bad = vals - CATEGORIES
        if bad:
            print(f"ERROR: unknown categor(ies) {sorted(bad)}; valid: {sorted(CATEGORIES)}",
                  file=sys.stderr)
            sys.exit(1)
        return vals

    only = _parse(args.only)
    skip = _parse(args.skip)
    t0 = time.time()
    main(only=only, skip=skip)
    print(f"\nStage 13 done in {time.time() - t0:.1f}s")
