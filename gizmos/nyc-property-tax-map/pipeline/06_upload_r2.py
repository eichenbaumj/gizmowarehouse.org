#!/usr/bin/env python3
"""Stage 06 — push the citywide PMTiles + NTA aggregates to Cloudflare R2.

Reads R2 credentials from `.env.local` at the repo root. Uses boto3 because
R2 is S3-compatible and we already have boto3 in the poverty-explorer
deploy pattern.

Files uploaded (all under prefix `nyc-property-tax/` in the bucket):
  - parcels.pmtiles       (the slim citywide tile archive)
  - nta-aggregates.geojson (low-zoom layer)
  - stats.json            (citywide medians for legend)
  - class-medians.json    (class-stratified medians)

After upload, files are served at `<R2_PUBLIC_URL>/nyc-property-tax/<file>`.
R2_PUBLIC_URL should be a custom domain (e.g. `https://data.gizmowarehouse.org`),
NOT the bucket's `pub-*.r2.dev` URL — see tools/HOSTING_DATA.md for why
(short version: r2.dev hostnames get classification-blocked by OpenDNS /
corporate DNS filters and break for many readers).

Usage:
    python3 pipeline/06_upload_r2.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env.local"


def load_env(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main():
    if not ENV_FILE.exists():
        print(f"ERROR: missing {ENV_FILE}.", file=sys.stderr)
        print(
            "Create it with R2_ACCOUNT_ID, R2_BUCKET, R2_S3_ENDPOINT, "
            "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY (see R2_SETUP.md).",
            file=sys.stderr,
        )
        sys.exit(1)
    env = load_env(ENV_FILE)
    required = {
        "R2_BUCKET", "R2_S3_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
    }
    missing = required - env.keys()
    if missing:
        print(f"ERROR: missing keys in {ENV_FILE}: {sorted(missing)}", file=sys.stderr)
        sys.exit(1)

    try:
        import boto3
    except ImportError:
        print("Installing boto3...", file=sys.stderr)
        os.system(f"{sys.executable} -m pip install --quiet boto3")
        import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=env["R2_S3_ENDPOINT"],
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = env["R2_BUCKET"]

    # Source path (in pipeline/output) → key in the bucket.
    pipeline_out = Path(__file__).resolve().parent / "output"
    public_data = REPO_ROOT / "public" / "data"
    uploads = [
        (pipeline_out / "parcels.pmtiles", "nyc-property-tax/parcels.pmtiles", "application/octet-stream"),
        (public_data / "nyc-nta-aggregates.geojson", "nyc-property-tax/nta-aggregates.geojson", "application/geo+json"),
        (public_data / "nyc-property-tax-stats.json", "nyc-property-tax/stats.json", "application/json"),
        (public_data / "nyc-property-tax-class-medians.json", "nyc-property-tax/class-medians.json", "application/json"),
    ]

    for local, key, content_type in uploads:
        if not local.exists():
            print(f"  SKIP {key} (missing source: {local})")
            continue
        size_mb = local.stat().st_size / (1 << 20)
        print(f"Uploading {local.name} ({size_mb:.1f} MB) -> {bucket}/{key} ...")
        with open(local, "rb") as f:
            s3.upload_fileobj(
                f, bucket, key,
                ExtraArgs={
                    "ContentType": content_type,
                    # Cache for a year — content-versioned via filename.
                    "CacheControl": "public, max-age=31536000, immutable",
                },
            )
        print(f"  OK -> {env.get('R2_PUBLIC_URL', '')}/{key}")

    print()
    print("Done. Update src/config/nycPropertyTaxMap.ts:")
    print(f"  parcelsPmtilesUrl: \"{env.get('R2_PUBLIC_URL', '')}/nyc-property-tax/parcels.pmtiles\"")
    print(f"  ntaGeoJsonUrl:    \"{env.get('R2_PUBLIC_URL', '')}/nyc-property-tax/nta-aggregates.geojson\"")
    print(f"  statsUrl:         \"{env.get('R2_PUBLIC_URL', '')}/nyc-property-tax/stats.json\"")
    print(f"  classMediansUrl:  \"{env.get('R2_PUBLIC_URL', '')}/nyc-property-tax/class-medians.json\"")


if __name__ == "__main__":
    main()
