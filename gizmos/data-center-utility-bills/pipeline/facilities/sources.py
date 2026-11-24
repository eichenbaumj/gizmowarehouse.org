"""Parsers for the three facility sources. Each returns a tidy DataFrame.

Nothing here assigns dates or load; that happens in build_inventory.py so the
rules are in one place and can be audited.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "facilities"


# --------------------------------------------------------------------------
# Business Insider (derived use only; never redistributed)
# --------------------------------------------------------------------------
def js_array_to_json(src: str, start: int) -> str:
    """Convert the JS array literal beginning at src[start] == '[' to JSON text.

    The file is a bundled web app, so the table is a JavaScript literal: keys
    are sometimes bare identifiers and strings may contain \\' escapes. We walk
    the text once, tracking whether we are inside a string, quote bare keys,
    and stop at the bracket that closes the array. No code is executed.
    """
    assert src[start] == "["
    out: list[str] = []
    depth = 0
    i = start
    n = len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":  # string literal in any of the three JS quote styles
            j = i + 1
            buf: list[str] = []
            while src[j] != c:
                d = src[j]
                if d == "\\":
                    nxt = src[j + 1]
                    if nxt == "u":
                        buf.append(chr(int(src[j + 2:j + 6], 16)))
                        j += 6
                        continue
                    buf.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                    j += 2
                    continue
                buf.append(d)
                j += 1
            out.append(json.dumps("".join(buf)))
            i = j + 1
            continue
        if c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            out.append(c)
            i += 1
            if depth == 0:
                break
            continue
        if c.isalpha() or c in "_$":
            m = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*").match(src, i)
            word = m.group(0)
            if src[m.end():m.end() + 1] == ":":
                out.append(f'"{word}"')
            elif word in ("true", "false", "null"):
                out.append(word)
            elif word == "void":  # `void 0` -> null
                out.append("null")
                i = m.end()
                while src[i] in " 0":
                    i += 1
                continue
            else:
                raise ValueError(f"unexpected bare token {word!r} at {i}")
            i = m.end()
            continue
        if c == "!" and src[i + 1] in "01":  # minified booleans: !0 / !1
            out.append("true" if src[i + 1] == "0" else "false")
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _num(x):
    if x is None:
        return None
    s = str(x).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def load_bi(path: Path | None = None) -> pd.DataFrame:
    path = path or RAW / "bi" / "index.js"
    src = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'=\[\{STATENAME:"', src)
    if not m:
        raise RuntimeError("Business Insider table marker not found; the file layout changed")
    rows = json.loads(js_array_to_json(src, m.start() + 1))
    recs = []
    for r in rows:
        recs.append({
            "src": "bi",
            "src_id": f"bi:{r.get('UNIQUE ID')}",
            "lat": _num(r.get("LAT")),
            "lon": _num(r.get("LONG")),
            "state": (r.get("STATE") or "").strip(),
            "county_name": (r.get("COUNTY") or "").strip(),
            "city": (r.get("CITY") or "").strip(),
            "address": (r.get("ADDRESS") or "").strip(),
            "operator": (r.get("BRAND") or r.get("COMPANY") or "").strip(),
            "company": (r.get("COMPANY") or "").strip(),
            "first_permit_year": _num(r.get("FIRST PERMIT ISSUE YEAR")),
            "latest_permit_year": _num(r.get("LATEST PERMIT ISSUE YEAR")),
            "construct_year": _num(r.get("DATA CENTER CONSTRUCT YEAR")),
            "permit_kind": (r.get("NEW PERMIT OR EXISTING UPDATE?") or "").strip(),
            "generator_kw": _num(r.get("TOTAL GENERATOR RATE CAPACITY KW")),
            "generator_kw_redacted": str(r.get("TOTAL GENERATOR RATE CAPACITY KW", "")).strip().lower() == "redacted",
            "n_buildings": _num(r.get("NUMBER OF BUILDINGS")),
            "water_daily_gal": _num(r.get("DAILY WATER CONSUMPTION (GALLONS)")),
            "water_annual_gal": _num(r.get("ANNUAL WATER CONSUMPTION (GALLONS)")),
        })
    df = pd.DataFrame(recs)
    # The source's "UNIQUE ID" repeats (one id can cover several permits on a
    # campus), so it cannot key a facility. Drop rows that are identical on every
    # substantive field, then number the remaining rows within each id.
    df = df.drop_duplicates(subset=[c for c in df.columns if c != "src_id"]).reset_index(drop=True)
    df["src_id"] = df.src_id + "-" + df.groupby("src_id").cumcount().astype(str)
    return df


# --------------------------------------------------------------------------
# OpenStreetMap (ODbL)
# --------------------------------------------------------------------------
def _year(s):
    m = re.match(r"\s*(\d{4})", str(s or ""))
    return float(m.group(1)) if m else None


def _power_mw(tags: dict):
    """OSM `it_power` / `input:electricity` style tags, e.g. '36 MW', '2500 kW'."""
    for k in ("it_power", "input:electricity", "power:rating", "rating"):
        v = tags.get(k)
        if not v:
            continue
        m = re.match(r"\s*([\d.,]+)\s*([kMG]?)W", str(v), flags=re.I)
        if m:
            x = float(m.group(1).replace(",", ""))
            unit = m.group(2).upper()
            return x * {"K": 1e-3, "M": 1.0, "G": 1e3, "": 1e-6}[unit]
    return None


def load_osm(path: Path | None = None) -> pd.DataFrame:
    path = path or RAW / "osm" / "us_data_centers.json"
    els = json.loads(path.read_text())["elements"]
    recs = []
    for e in els:
        t = e.get("tags", {})
        c = e.get("center") or e
        recs.append({
            "src": "osm",
            "src_id": f"osm:{e['type']}/{e['id']}",
            "lat": c.get("lat"),
            "lon": c.get("lon"),
            "state": t.get("addr:state", ""),
            "city": t.get("addr:city", ""),
            "name": t.get("name", ""),
            "operator": t.get("operator", "") or t.get("owner", ""),
            "osm_start_year": _year(t.get("start_date")),
            "osm_mw": _power_mw(t),
            "osm_last_edit": e.get("timestamp"),
        })
    return pd.DataFrame(recs).dropna(subset=["lat", "lon"])


# --------------------------------------------------------------------------
# Epoch AI (CC BY 4.0)
# --------------------------------------------------------------------------
def load_epoch(path: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (sites, timelines). Read straight from the zip; nothing is extracted."""
    path = path or RAW / "epoch" / "data_centers.zip"
    with zipfile.ZipFile(path) as z:
        sites = pd.read_csv(io.BytesIO(z.read("data_centers.csv")))
        tl = pd.read_csv(io.BytesIO(z.read("data_center_timelines.csv")))
    tl["Date"] = pd.to_datetime(tl["Date"], errors="coerce")
    return sites, tl
