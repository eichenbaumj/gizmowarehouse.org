#!/usr/bin/env python3
"""Fetch NOAA population-weighted heating and cooling degree days by state and year.

Product used: NOAA Climate Prediction Center (CPC) "Daily Degree Days", States (CONUS),
weights = Population (2010 Census), one pipe-delimited file per year and per
heating/cooling at
  https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/daily_data/<YEAR>/StatesCONUS.{Heating,Cooling}.txt
Each file's own header reads "Weights: Population". The 48 contiguous states are
keyed by two-letter code directly, so no code crosswalk is needed.

Why not NCEI nClimDiv (climdiv-hddcst / climdiv-cddcst): its state readme describes the
statewide values as area-weighted averages and mentions population weights only in one
loose sentence about degree days, which does not say the statewide files use them. The
CPC product says it in so many words (quoted into the report JSON). The nClimDiv readme
sentence is recorded in the report too, for the record.

Annual figure = sum of the daily values over the calendar year. A state-year with any
missing or negative day (or a file that does not cover Jan 1 to Dec 31) is dropped and
listed in the report. District of Columbia: not in the product; its rows are copied from
Maryland with basis = "Maryland, used for DC". Alaska and Hawaii: not in the product,
reported absent, not filled. Years 2001 to 2025; 2025 is kept only if the file covers the
full calendar year.

Raw files go under data/raw/cpc_degree_days/ (gitignored, re-fetchable).
Outputs: data/frozen/degree_days.csv, data/frozen/degree_days_report.json

Run:  python3 -I pipeline/electricity/fetch_degree_days.py
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "cpc_degree_days"
FROZEN = ROOT / "data" / "frozen"
UA = {"User-Agent": "research-data-fetch/1.0"}
BASE = "https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/daily_data/"
LANDING = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/"
EXPLAIN = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/ddayexp.shtml"
NCLIMDIV_README = "https://www.ncei.noaa.gov/pub/data/cirs/climdiv/state-readme.txt"
STATES_LIST = BASE + "regions/StatesCONUS.txt"
FIRST, LAST = 2001, 2025
ALL51 = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
         "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()

POP_SENTENCE = ("These data include population weighted State, Census Divisional and National data using "
                "2010 Census data (excluding Alaska and Hawaii)")
BASE_SENTENCE = ("A mean daily temperature (average of the daily maximum and minimum temperatures) of 65°F "
                 "is the base for both heating and cooling degree day computations.")


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def page_text(b: bytes) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", b.decode("latin-1"), flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


def save(url: str, dest: Path, files: list) -> bytes:
    b = get(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b)
    files.append({"url": url, "path": str(dest.relative_to(ROOT)), "bytes": len(b),
                  "sha256": hashlib.sha256(b).hexdigest()})
    return b


def parse(b: bytes, year: int):
    """Return (weights_line, {state: [daily values or None]}, n_days)."""
    lines = b.decode("latin-1").splitlines()
    weights = next(l for l in lines if l.startswith("Weights:"))
    hi = next(i for i, l in enumerate(lines) if l.startswith("Region|"))
    dates = lines[hi].split("|")[1:]
    covers = bool(dates) and dates[0] == f"{year}0101" and dates[-1] == f"{year}1231"
    out = {}
    for l in lines[hi + 1:]:
        if not l.strip():
            continue
        parts = l.split("|")
        vals = []
        for v in parts[1:]:
            try:
                x = float(v)
                vals.append(x if x >= 0 else None)
            except ValueError:
                vals.append(None)
        out[parts[0]] = vals if len(vals) == len(dates) else vals + [None] * (len(dates) - len(vals))
    return weights, out, len(dates), covers


def main() -> int:
    fetched_at = datetime.now(timezone.utc).isoformat()
    files: list = []
    try:
        land = page_text(save(LANDING, RAW / "docs" / "degree_days_landing.html", files))
        expl = page_text(save(EXPLAIN, RAW / "docs" / "ddayexp.shtml", files))
        ncl = page_text(save(NCLIMDIV_README, RAW / "docs" / "nclimdiv_state_readme.txt", files))
        states_list = save(STATES_LIST, RAW / "docs" / "StatesCONUS_regions.txt", files).decode()
    except Exception as e:
        print("FAIL fetching documentation", repr(e))
        return 1
    if POP_SENTENCE not in land or BASE_SENTENCE not in expl:
        print("STOP: the expected NOAA documentation sentences are not on the pages; not using this product blind")
        return 1
    listed = [l.split("|")[0] for l in states_list.splitlines()[1:] if l.strip()]
    nclimdiv_sentence = re.search(r"Population weights utilize the 2010 Census data\.", ncl)

    data: dict[tuple[str, int], dict] = {}
    dropped, year_notes, weights_lines = [], {}, set()
    for year in range(FIRST, LAST + 1):
        got = {}
        for kind in ("Heating", "Cooling"):
            url = f"{BASE}{year}/StatesCONUS.{kind}.txt"
            try:
                b = save(url, RAW / str(year) / f"StatesCONUS.{kind}.txt", files)
            except Exception as e:
                year_notes[year] = f"{kind} file not fetched: {e!r}"
                break
            w, vals, nd, covers = parse(b, year)
            weights_lines.add(w)
            if not covers:
                year_notes[year] = f"{kind} file does not cover Jan 1 to Dec 31; year left out"
                break
            got[kind] = vals
        else:
            for st in sorted(set(got["Heating"]) & set(got["Cooling"])):
                h, c = got["Heating"][st], got["Cooling"][st]
                if any(v is None for v in h) or any(v is None for v in c):
                    dropped.append({"state": st, "year": year,
                                    "missing_heating_days": sum(v is None for v in h),
                                    "missing_cooling_days": sum(v is None for v in c)})
                    continue
                data[(st, year)] = {"hdd": sum(h), "cdd": sum(c)}
    years_out = sorted({y for _, y in data})
    FROZEN.mkdir(parents=True, exist_ok=True)
    rows = []
    for (st, y), v in sorted(data.items()):
        rows.append({"state": st, "year": y, "hdd": int(v["hdd"]), "cdd": int(v["cdd"]), "basis": "NOAA state value"})
        if st == "MD":
            rows.append({"state": "DC", "year": y, "hdd": int(v["hdd"]), "cdd": int(v["cdd"]),
                         "basis": "Maryland, used for DC"})
    rows.sort(key=lambda r: (r["state"], r["year"]))
    with (FROZEN / "degree_days.csv").open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["state", "year", "hdd", "cdd", "basis"])
        wr.writeheader()
        wr.writerows(rows)

    native = {r["state"] for r in rows if r["basis"] == "NOAA state value"}
    report = {
        "product": "NOAA Climate Prediction Center daily degree days, population-weighted, States (CONUS)",
        "source_urls": {"data_pattern": BASE + "<YEAR>/StatesCONUS.{Heating,Cooling}.txt",
                        "state_list": STATES_LIST, "documentation_page": LANDING,
                        "explanation_page": EXPLAIN, "nclimdiv_state_readme_checked_and_not_used": NCLIMDIV_README},
        "file_names": [f["path"] for f in files if "/docs/" not in f["path"]],
        "files_with_hashes": files,
        "date_fetched": fetched_at,
        "date_stamps_note": "CPC files carry no date stamp in their names (the year is the directory); "
                            "nClimDiv (not used) files are dated 20261105 in their names",
        "population_weighting": {
            "noaa_sentence_verbatim": POP_SENTENCE + ", and heating fuel weighted Census Divisional and National data using "
                                      "the 2010 Annual Community Survey data.",
            "where": LANDING + " , section \"New Degree Days Products\" (first paragraph)",
            "file_header_lines_seen": sorted(weights_lines),
            "explanation_page_sentence": "State, Regional, and National Data Degree days are estimated for State climate "
                                         "divisions and then population weighted to more accurately reflect "
                                         "temperature-related energy consumption at the State, regional, and national "
                                         "levels. (" + EXPLAIN + "; this page is older and cites 2000 Census weights)",
            "nclimdiv_readme_methodology_sentence_verbatim": "Statewide, regional and national values in nClimDiv were "
                "derived from area-weighted averages of 5km X 5km grid-point estimates interpolated from station data. "
                "(" + NCLIMDIV_README + ")",
            "nclimdiv_readme_degree_day_sentence_verbatim": nclimdiv_sentence.group(0) if nclimdiv_sentence else None,
        },
        "base_temperature": {"sentence_verbatim": BASE_SENTENCE, "url": EXPLAIN},
        "aggregation": "annual = sum of daily values, Jan 1 to Dec 31; daily values are integer degree days as published",
        "years_requested": [FIRST, LAST],
        "years_in_output": [years_out[0], years_out[-1]] if years_out else None,
        "year_level_notes": {str(k): v for k, v in year_notes.items()},
        "jurisdictions_in_noaa_product": sorted(native),
        "jurisdictions_absent_from_product": sorted(set(ALL51) - native),
        "absent_handling": {"DC": "rows copied from Maryland, basis = 'Maryland, used for DC'",
                            "AK": "absent, not filled", "HI": "absent, not filled"},
        "state_list_matches_product_files": sorted(listed) == sorted(native),
        "state_years_dropped_for_missing_days": dropped,
    }
    (FROZEN / "degree_days_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("years", report["years_in_output"], "rows", len(rows), "absent", report["jurisdictions_absent_from_product"],
          "dropped", len(dropped), "notes", year_notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
