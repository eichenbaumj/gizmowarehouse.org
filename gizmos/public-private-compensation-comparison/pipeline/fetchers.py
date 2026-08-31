"""Shared fetch helpers — FRED CSV, BLS API, Census API. All return clean data
or raise; no silent failures (per CLAUDE.md: stop and report on bad data)."""

from __future__ import annotations

import io
import json
import time

import pandas as pd
import requests

import config

UA = {"User-Agent": "gizmo-warehouse-research/1.0 (joe@group17a.com)"}


def fetch_fred(series_id: str) -> pd.DataFrame:
    """Return a DataFrame with columns [date, value] for a FRED series."""
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


def fetch_bls(series_ids: list[str], startyear: int, endyear: int) -> dict[str, pd.DataFrame]:
    """Fetch BLS v2 timeseries. Returns {series_id: DataFrame[year, period, value]}.

    BLS caps a single request at 20 years; we chunk if needed. Up to 50 series
    per POST with a registered key, 25 without; we keep requests small.
    """
    out: dict[str, pd.DataFrame] = {}
    # Chunk the year range into <=19-year windows.
    windows = []
    y0 = startyear
    while y0 <= endyear:
        y1 = min(y0 + 18, endyear)
        windows.append((y0, y1))
        y0 = y1 + 1
    for (ys, ye) in windows:
        payload = {"seriesid": series_ids, "startyear": str(ys), "endyear": str(ye)}
        if config.BLS_API_KEY:
            payload["registrationkey"] = config.BLS_API_KEY
        r = requests.post(
            config.BLS_API, json=payload, headers={**UA, "Content-Type": "application/json"}, timeout=40
        )
        r.raise_for_status()
        d = r.json()
        if d.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS request failed: {d.get('status')} {d.get('message')}")
        for s in d["Results"]["series"]:
            sid = s["seriesID"]
            rows = [
                {"year": int(x["year"]), "period": x["period"], "value": float(x["value"])}
                for x in s["data"]
                if x["value"] not in ("", "-")
            ]
            df = pd.DataFrame(rows)
            if sid in out:
                out[sid] = pd.concat([out[sid], df], ignore_index=True)
            else:
                out[sid] = df
        time.sleep(0.3)
    for sid, df in out.items():
        if df.empty:
            raise RuntimeError(f"BLS series {sid} returned no rows")
    return out


def census_get(url: str, params: dict) -> list[list[str]]:
    """GET a Census API endpoint, return the raw [header, *rows] table."""
    p = dict(params)
    if config.CENSUS_API_KEY:
        p["key"] = config.CENSUS_API_KEY
    r = requests.get(url, params=p, headers=UA, timeout=60)
    r.raise_for_status()
    txt = r.text.strip()
    if not txt.startswith("["):
        raise RuntimeError(f"Census API non-JSON response: {txt[:200]}")
    return json.loads(txt)


def write_json(path, obj) -> None:
    path.write_text(json.dumps(obj, separators=(",", ":")))
    print(f"  wrote {path}  ({path.stat().st_size/1024:.1f} KB)")
