"""Stage 13b — upload ONLY the state-brief PDFs to R2.

Use this after re-baking briefs (stage 12) when the tiles haven't changed.
Stage 13 (13_upload_r2.py) re-pushes ~1.18 GB of unchanged PMTiles every run;
this uploads just public/assets/medicaid-briefs/*.pdf, which is what changes
when the brief template or its inline SVGs are edited.

Cache policy: briefs are RE-BAKED in place at stable URLs
(data.gizmowarehouse.org/medicaid-work-requirements/briefs/medicaid_brief_XX.pdf),
so they are NOT immutable. We send a revalidatable Cache-Control so an edited
brief actually propagates instead of being pinned for a year. (Tiles in
stage 13 stay immutable — they get versioned filenames when they change.)

Required environment (in .env.local at repo root): R2_S3_ENDPOINT,
R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY (R2_BUCKET optional, defaults to config).

Run:
  cd pipeline && python3 13b_upload_briefs.py            # upload all briefs
  cd pipeline && python3 13b_upload_briefs.py --state NY # one brief
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from dotenv import load_dotenv

import config

load_dotenv(config.REPO_ROOT / ".env.local")

BUCKET = os.environ.get("R2_BUCKET", config.R2_BUCKET)
ENDPOINT = os.environ.get("R2_S3_ENDPOINT")
ACCESS_KEY = os.environ.get("R2_ACCESS_KEY_ID")
SECRET_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")

BRIEFS_DIR = config.PUBLIC_ASSETS_DIR / "medicaid-briefs"
# Revalidatable: cache for an hour, then check origin. Mutable asset.
BRIEF_CACHE_CONTROL = "public, max-age=3600, must-revalidate"


def main(only_state: str | None = None) -> None:
    missing = [k for k, v in {
        "R2_S3_ENDPOINT": ENDPOINT,
        "R2_ACCESS_KEY_ID": ACCESS_KEY,
        "R2_SECRET_ACCESS_KEY": SECRET_KEY,
    }.items() if not v]
    if missing:
        print(f"ERROR: missing R2 credentials in .env.local: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    if not BRIEFS_DIR.exists():
        print(f"ERROR: no briefs dir at {BRIEFS_DIR}. Run stage 12 first.", file=sys.stderr)
        sys.exit(1)

    pdfs = sorted(BRIEFS_DIR.glob("*.pdf"))
    if only_state:
        pdfs = [p for p in pdfs if p.stem.upper().endswith(f"_{only_state.upper()}")]
    if not pdfs:
        print("Nothing to upload.")
        return

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

    print(f"Uploading {len(pdfs)} brief(s) to s3://{BUCKET}/{config.R2_PREFIX}/briefs/ ...")
    for p in pdfs:
        key = f"{config.R2_PREFIX}/briefs/{p.name}"
        s3.upload_file(
            str(p), BUCKET, key,
            ExtraArgs={
                "ContentType": "application/pdf",
                "CacheControl": BRIEF_CACHE_CONTROL,
            },
        )
        print(f"  -> {key:58s}  ({p.stat().st_size/1e3:6.1f} KB)")

    print(f"\nDone. Public base: {config.R2_PUBLIC_BASE}/briefs/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", help="Only upload this state (2-letter abbr)", default=None)
    args = ap.parse_args()
    t0 = time.time()
    main(args.state)
    print(f"Stage 13b done in {time.time() - t0:.1f}s")
