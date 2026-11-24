#!/usr/bin/env python3
"""Fetch the two inputs to the Scalera, Bosetti and Pecci (CEPR) instrument.

Replication row C in PREANALYSIS.md needs their shift-share instrument:

    (year >= 2021) x ln(national private data center construction spending)
                   x the territory's 2017-2019 share of the nation's census
                     blocks with fiber to the end user

Both parts are public. This script downloads them into data/raw/ (gitignored,
re-fetchable) and touches no price data.

1. FCC Form 477 fixed broadband deployment, the six filings of 2017-2019
   (June and December each year), from the FCC's open-data API. We pull only
   what the instrument uses: the distinct census blocks (2010 vintage) where
   any provider reports technology code 50, "fiber to the end user", to homes
   or businesses. Each state pull is checked against the API's own count.
2. Census block internal points (latitude and longitude), from the Census
   Bureau's LODES 7 geography crosswalk, which lists every 2010 block. Needed
   to place blocks in utility territories without downloading block polygons.
3. Census Value of Construction Put in Place, private, not seasonally
   adjusted, monthly: the "Data center" column (published from 2014).
4. CPI-U annual averages from BLS, to put spending in 2024 dollars as the
   paper does.

Run:  python3 -I pipeline/instrument/fetch_instrument_inputs.py
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
UA = {"User-Agent": "research-data-fetch/1.0"}

FCC_BASE = "https://opendata.fcc.gov/resource/"
# Dataset ids from the FCC open-data catalog (api.us.socrata.com, domain opendata.fcc.gov).
FCC_FILINGS = {
    "2017-06": ("9r8r-g7ut", "Fixed Broadband Deployment Data: June, 2017 Status V1"),
    "2017-12": ("pq3u-a6vs", "Fixed Broadband Deployment Data: Dec, 2017 Status V2"),
    "2018-06": ("ehbi-rr4z", "Fixed Broadband Deployment Data: Jun, 2018 Status V1"),
    "2018-12": ("kydr-hyy5", "Fixed Broadband Deployment Data: Dec, 2018 Status V1"),
    "2019-06": ("c67e-jknh", "Fixed Broadband Deployment Data: Jun, 2019 Status V2"),
    "2019-12": ("whue-6pnt", "Fixed Broadband Deployment Data: December 2019"),
}
FIBER_TO_END_USER = 50
PAGE = 1_000_000  # larger than any state's count of fiber blocks; checked below

STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
          "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
LODES_URL = "https://lehd.ces.census.gov/data/lodes/LODES7/{st}/{st}_xwalk.csv.gz"
VIP_URL = "https://www.census.gov/construction/c30/xlsx/privtime.xlsx"
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0?startyear={a}&endyear={b}&annualaverage=true"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get(url: str, timeout: int = 600, tries: int = 6) -> bytes:
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # transient API errors are common on long group-by queries
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed after {tries} tries: {url}: {last!r}")


def download(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(get(url))
    return {"url": url, "path": str(dest.relative_to(ROOT)), "bytes": dest.stat().st_size, "sha256": sha256(dest)}


def soql(dataset: str, fmt: str, **params: str) -> str:
    return f"{FCC_BASE}{dataset}.{fmt}?" + urllib.parse.urlencode({f"${k}": v for k, v in params.items()})


def fetch_filing(tag: str, dataset: str) -> dict:
    """Distinct fiber blocks for one filing, state by state, verified against the API's counts."""
    dest = RAW / "fcc477" / f"fiber_blocks_{tag}.csv.gz"
    counts_path = RAW / "fcc477" / f"fiber_block_counts_{tag}.json"
    where = f"techcode={FIBER_TO_END_USER}"
    if not counts_path.exists():
        rows = json.loads(get(soql(dataset, "json", select="stateabbr,count(distinct blockcode) as n",
                                   where=where, group="stateabbr", limit="100")))
        counts_path.parent.mkdir(parents=True, exist_ok=True)
        counts_path.write_text(json.dumps({r["stateabbr"]: int(r["n"]) for r in rows}, indent=1, sort_keys=True))
    expected = json.loads(counts_path.read_text())

    if not dest.exists():
        def one(st: str) -> list[str]:
            text = get(soql(dataset, "csv", select="blockcode", where=f"{where} AND stateabbr='{st}'",
                            group="blockcode", order="blockcode", limit=str(PAGE)), timeout=180).decode()
            blocks = [row[0] for row in csv.reader(io.StringIO(text))][1:]
            if len(blocks) != expected.get(st, 0) or len(blocks) >= PAGE:
                raise RuntimeError(f"{tag} {st}: pulled {len(blocks)} blocks, API count says {expected.get(st, 0)}")
            if any(len(b) != 15 or not b.isdigit() for b in blocks):
                raise RuntimeError(f"{tag} {st}: malformed block code")
            return blocks

        with ThreadPoolExecutor(max_workers=4) as pool:  # a few at a time; this is a public API
            per_state = list(pool.map(one, sorted(expected)))
        tmp = dest.with_suffix(".tmp")
        with gzip.open(tmp, "wt", newline="") as f:
            f.write("blockcode\n")
            for blocks in per_state:
                f.writelines(b + "\n" for b in blocks)
        tmp.rename(dest)
    n = sum(1 for _ in gzip.open(dest, "rt")) - 1
    if n != sum(expected.values()):
        raise RuntimeError(f"{tag}: file has {n} blocks, API counts sum to {sum(expected.values())}")
    print(f"  {tag}: {n:,} fiber blocks in {len(expected)} states and territories", flush=True)
    return {"filing": tag, "dataset": dataset, "url": f"https://opendata.fcc.gov/d/{dataset}",
            "query": f"distinct blockcode where {where}", "path": str(dest.relative_to(ROOT)),
            "fiber_blocks": n, "states_and_territories": len(expected), "sha256": sha256(dest)}


def main() -> int:
    manifest: dict = {"fetched_at": datetime.now(timezone.utc).isoformat(), "fcc477": [], "files": []}

    print("FCC Form 477, technology code 50, distinct blocks per filing")
    for tag, (dataset, title) in FCC_FILINGS.items():
        entry = fetch_filing(tag, dataset)
        entry["title"] = title
        manifest["fcc477"].append(entry)

    print("Census block internal points (LODES 7 crosswalk)")
    for st in STATES:
        manifest["files"].append(download(LODES_URL.format(st=st.lower()),
                                          RAW / "lodes_xwalk" / f"{st.lower()}_xwalk.csv.gz"))
    print(f"  {len(STATES)} state files")

    print("Census construction spending and CPI")
    manifest["files"].append(download(VIP_URL, RAW / "census_vip" / "privtime.xlsx"))
    cpi_path = RAW / "bls" / "cpi_u_annual.json"
    if not cpi_path.exists():
        out = {}
        for a, b in ((2006, 2015), (2016, 2025)):  # the keyless API serves ten years per request
            d = json.loads(get(BLS_URL.format(a=a, b=b)))
            if d.get("status") != "REQUEST_SUCCEEDED":
                raise RuntimeError(f"BLS: {d.get('status')} {d.get('message')}")
            for row in d["Results"]["series"][0]["data"]:
                if row["period"] == "M13":
                    out[row["year"]] = float(row["value"])
        cpi_path.parent.mkdir(parents=True, exist_ok=True)
        cpi_path.write_text(json.dumps({"series": "CUUR0000SA0", "annual_average": out}, indent=1, sort_keys=True))
    manifest["files"].append({"url": "https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0",
                              "path": str(cpi_path.relative_to(ROOT)), "bytes": cpi_path.stat().st_size,
                              "sha256": sha256(cpi_path)})

    (ROOT / "data" / "frozen").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "frozen" / "fetch_manifest_instrument.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("manifest written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
