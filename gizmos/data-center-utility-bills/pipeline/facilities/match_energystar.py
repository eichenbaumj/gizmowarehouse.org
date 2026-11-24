#!/usr/bin/env python3
"""Match undated permitted sites to EPA's ENERGY STAR certified data centers registry.

The registry (one public page, a few hundred buildings) lists each certified
data center by street address with its owner and a "Year Constructed". It
needs no web search, so it is a cheap lead for dating sites.

It is a lead, not a verdict. "Year Constructed" is the building's year:

  * for a purpose-built data center it is usually within a year of first load;
  * for a converted building it can be decades early (a Miami carrier hotel
    is listed as 1927);
  * for a building delivered in phases it can be a later phase.

So matches are written to pipeline/facilities/leads/ and shown to checkers by
make_date_worklist.py. A registry year becomes an override only when a
person or the session model has looked at the row and the site and recorded
it in a verified/ batch file, at medium confidence (docs/DECISIONS.md, D-15).

A match needs the same state, the same street number, and the first word of
the street name.

Run:  python3 -I pipeline/facilities/match_energystar.py
"""
from __future__ import annotations

import html
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.facilities import sources  # noqa: E402

URL = "https://www.energystar.gov/buildings/certified-data-centers"
RAW = ROOT / "data" / "raw" / "energystar" / "certified_data_centers.html"
OUT = ROOT / "pipeline" / "facilities" / "leads" / "energystar_matches.csv"
STATES = {
    "Alabama": "AL", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO", "Connecticut": "CT",
    "Delaware": "DE", "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
DIRECTIONS = {"n", "s", "e", "w", "ne", "nw", "se", "sw", "north", "south", "east", "west"}


def parse_registry(page: str) -> pd.DataFrame:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S):
        td = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x))).strip()
              for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(td) >= 7:
            rows.append({"registry_name": td[0], "state": STATES.get(td[1]), "registry_owner": td[2],
                         "year_constructed": pd.to_numeric(td[6], errors="coerce")})
    return pd.DataFrame(rows)


def address_key(address) -> tuple[str, str] | None:
    """Street number and first word of the street name, directions dropped."""
    m = re.match(r"\s*(\d{2,6})\s+(.*)", str(address))
    if not m:
        return None
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", m.group(2).lower()).split() if w not in DIRECTIONS]
    return (m.group(1), words[0]) if words else None


def same_address(key: tuple[str, str], registry_name: str) -> bool:
    name = re.sub(r"[^a-z0-9 ]", " ", registry_name.lower())
    return bool(re.search(rf"\b{key[0]}\b", name) and re.search(rf"\b{re.escape(key[1])}", name))


def main() -> int:
    RAW.parent.mkdir(parents=True, exist_ok=True)
    if not RAW.exists():
        req = urllib.request.Request(URL, headers={"User-Agent": "research-data-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            RAW.write_bytes(r.read())
    reg = parse_registry(RAW.read_text(errors="ignore"))
    if len(reg) < 100:
        raise RuntimeError("registry page layout changed: fewer than 100 rows parsed")

    fac = pd.read_parquet(ROOT / "data" / "interim" / "facilities.parquet").set_index("fid")
    bi = sources.load_bi().set_index("src_id")
    cand = fac[fac.src == "bi"]
    hits = []
    for fid, c in cand.iterrows():
        key = address_key(bi.address.get(fid))
        if not key:
            continue
        for x in reg[reg.state == c.state].itertuples():
            if same_address(key, x.registry_name):
                hits.append({"fid": fid, "state": c.state, "registry_name": x.registry_name,
                             "registry_owner": x.registry_owner,
                             "year_constructed": None if pd.isna(x.year_constructed) else int(x.year_constructed),
                             "source_url": URL, "retrieved": date.today().isoformat()})
    out = pd.DataFrame(hits).sort_values(["state", "fid"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    undated = out.fid.map(lambda f: "year" not in (fac.verified_fields.get(f) or ""))
    print(f"registry rows: {len(reg)} | permitted sites matched: {out.fid.nunique()} | of which without a sourced year: {int(undated.sum())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
