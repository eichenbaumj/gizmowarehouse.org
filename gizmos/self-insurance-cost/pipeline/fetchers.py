"""Shared fetch helpers: cached downloads with a sha256 manifest, Socrata paging,
FRED CSV. Clean data or raise; no silent failures."""

from __future__ import annotations

import hashlib
import io
import json
import math
import time
from pathlib import Path

import pandas as pd
import requests

import config

UA = {"User-Agent": "gizmo-warehouse-research/1.0 (joe@group17a.com)"}
ZIP_MAGIC = b"PK\x03\x04"


def _manifest() -> dict:
    if config.RAW_MANIFEST.exists():
        return json.loads(config.RAW_MANIFEST.read_text())
    return {}


def _save_manifest(m: dict) -> None:
    config.RAW_MANIFEST.write_text(json.dumps(m, indent=2, sort_keys=True))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, *, force: bool = False, expect_zip: bool = False, timeout: int = 600) -> Path:
    """Download url to dest unless it already exists (and --force is off).
    Records url, sha256, bytes, fetched-at in raw/manifest.json."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        print(f"  cached {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")
        m = _manifest()
        key = str(dest.relative_to(config.RAW_DIR))
        if key not in m:  # file dropped in by hand or copied from a previous session
            m[key] = {"url": url, "sha256": sha256(dest), "bytes": dest.stat().st_size,
                      "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": "pre-existing file; sha recorded on first run"}
            _save_manifest(m)
        return dest
    print(f"  GET {url}")
    with requests.get(url, headers=UA, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    if expect_zip:
        with open(tmp, "rb") as f:
            if f.read(4) != ZIP_MAGIC:
                tmp.unlink()
                raise RuntimeError(f"{url} did not return a zip (the OSC site returns an HTML 404 under a .zip name)")
    tmp.rename(dest)
    m = _manifest()
    m[str(dest.relative_to(config.RAW_DIR))] = {
        "url": url, "sha256": sha256(dest), "bytes": dest.stat().st_size,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _save_manifest(m)
    print(f"  wrote {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")
    return dest


def socrata_all(dataset_id: str, *, where: str | None = None, select: str | None = None,
                page: int = 50_000) -> list[dict]:
    """Page through a Socrata dataset with $limit/$offset. Returns the rows."""
    url = f"{config.SOCRATA_DOMAIN}/resource/{dataset_id}.json"
    headers = dict(UA)
    if config.SOCRATA_APP_TOKEN:
        headers["X-App-Token"] = config.SOCRATA_APP_TOKEN
    rows: list[dict] = []
    offset = 0
    while True:
        params = {"$limit": page, "$offset": offset, "$order": ":id"}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select
        r = requests.get(url, params=params, headers=headers, timeout=120)
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
        time.sleep(0.2)
    if not rows:
        raise RuntimeError(f"Socrata {dataset_id} returned no rows for where={where!r}")
    return rows


def fetch_fred(series_id: str) -> pd.DataFrame:
    url = config.FRED_CSV.format(id=series_id)
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna()
    if df.empty:
        raise RuntimeError(f"FRED series {series_id} returned no usable rows")
    return df


def _clean(o):
    """NaN/inf are not JSON; the browser's JSON.parse rejects them. Write null instead."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(obj), separators=(",", ":"), allow_nan=False))
    print(f"  wrote {path}  ({path.stat().st_size/1024:.1f} KB)")
