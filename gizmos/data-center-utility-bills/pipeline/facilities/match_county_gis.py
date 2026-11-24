#!/usr/bin/env python3
"""Match permitted Virginia sites to two county GIS layers that date data center buildings.

Northern Virginia holds the largest share of the sites that had only a
permit-based start year, most of them Amazon buildings with no operator page
and no press. Two counties publish, as open map services, a record per data
center building with the year it was built:

  Loudoun County         "Existing Structures", structures whose use is
                         COM_DATA_CENTER: address and "Demographic Year Built".
  Prince William County  "Data Center Buildings": building name, address,
                         status (Completed or not), year built, and the date
                         of the occupancy certificate.

Neither needs a web search. A match needs the same street number and the
first word of the street name, within the county's own records.

What a match is worth (docs/DECISIONS.md, D-15): a government record of the
year a building was built, medium confidence. It is the building's year,
which for a purpose-built data center is within about a year of first load.
Prince William's occupancy date is closer to first use than a year built and
is preferred where present. A building Prince William lists as not completed
is evidence that it was not operating at the layer's last edit date.

Outputs:
  pipeline/facilities/leads/county_gis_matches.csv   every match, for review
  pipeline/facilities/verified/batch_r3c_0.json      (with --write-batch) the
      matches that pass the rules below, for sites with no sourced year yet

Rules for a match to become an override (D-15):
  * the building is Completed (Prince William) or Existing or Permitted
    (Loudoun) and has a real year built: Loudoun writes 1000 for unknown;
  * built in 2005 or later. An older structure may be an office or warehouse
    converted to a data center years afterwards, and the county's year is the
    building's (Loudoun lists 1990 for one data center), so those stay leads;
  * the year is the occupancy-certificate year where Prince William gives one
    within two years of the year built (a certificate decades older belongs
    to an earlier use of the address), otherwise the year built; the
    earliest, if several buildings share the address;
  * a building the county lists as planned or under construction is NOT taken
    as proof the site is idle: an older building at the same address may be
    running. Those stay leads.
On 16 sites that also have an independently sourced year, the county year is
within one year for 13 and within two for all 16.

Run:  python3 -I pipeline/facilities/match_county_gis.py [--write-batch]
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.facilities import sources  # noqa: E402
from pipeline.facilities.match_energystar import address_key, same_address  # noqa: E402

RAW = ROOT / "data" / "raw" / "county_gis"
OUT = ROOT / "pipeline" / "facilities" / "leads" / "county_gis_matches.csv"
UA = {"User-Agent": "research-data-fetch/1.0"}
LAYERS = {
    "loudoun": {
        "url": "https://logis.loudoun.gov/gis/rest/services/Projects/BuildOut_LandUse/MapServer/0/query",
        "where": "LU_USE='COM_DATA_CENTER'",
    },
    "prince_william": {
        "url": "https://gisweb.pwcva.gov/arcgis/rest/services/CountyMapper/LandDevelopment/MapServer/10/query",
        "where": "1=1",
    },
}


def fetch_layer(name: str) -> list[dict]:
    path = RAW / f"{name}.json"
    if not path.exists():
        rows, offset = [], 0
        while True:
            q = urllib.parse.urlencode({"where": LAYERS[name]["where"], "outFields": "*", "returnGeometry": "false",
                                        "f": "json", "resultOffset": offset, "resultRecordCount": 1000})
            with urllib.request.urlopen(urllib.request.Request(f"{LAYERS[name]['url']}?{q}", headers=UA), timeout=120) as r:
                d = json.load(r)
            if "error" in d:
                raise RuntimeError(f"{name}: {d['error']}")
            feats = d.get("features", [])
            rows += [f["attributes"] for f in feats]
            if not d.get("exceededTransferLimit") or not feats:
                break
            offset += len(feats)
        RAW.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"retrieved": date.today().isoformat(), "rows": rows}))
    return json.loads(path.read_text())["rows"]


def day(epoch_ms) -> str | None:
    return None if epoch_ms in (None, "") else datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).date().isoformat()


def buildings() -> pd.DataFrame:
    """Both layers in one shape: county, address, name, status, year_built, occupancy_date, as_of."""
    lou = [{"county": "Loudoun", "address": (r["LU_ADDRESS"] or "").strip(), "name": None,
            "status": r.get("LU_DEVELOP_STATUS"), "year_built": r.get("LU_DEMOG_YEAR_BUILT"),
            "occupancy_date": None, "as_of": day(r.get("LU_AS_OF_DATE")),
            "source_url": LAYERS["loudoun"]["url"]} for r in fetch_layer("loudoun")]
    pwc = [{"county": "Prince William", "address": (r["Address"] or "").strip(), "name": r.get("BuildingName"),
            "status": r.get("BuildingStatus"), "year_built": r.get("YearBuilt"),
            "occupancy_date": day(r.get("OCCDate")), "as_of": day(r.get("LastEditDate")),
            "source_url": LAYERS["prince_william"]["url"]} for r in fetch_layer("prince_william")]
    b = pd.DataFrame(lou + pwc)
    b["year_built"] = pd.to_numeric(b.year_built, errors="coerce")
    return b[b.address.str.len() > 0].reset_index(drop=True)


def main() -> int:
    b = buildings()
    fac = pd.read_parquet(ROOT / "data" / "interim" / "facilities.parquet").set_index("fid")
    bi = sources.load_bi().set_index("src_id")
    hits = []
    for fid, c in fac[(fac.src == "bi") & (fac.state == "VA")].iterrows():
        key = address_key(bi.address.get(fid))
        if not key:
            continue
        for x in b.itertuples():
            if same_address(key, x.address):
                hits.append({"fid": fid, "permit_address": bi.address.get(fid), "county": x.county,
                             "county_address": x.address, "building_name": x.name, "status": x.status,
                             "year_built": None if pd.isna(x.year_built) else int(x.year_built),
                             "occupancy_date": x.occupancy_date, "layer_as_of": x.as_of, "source_url": x.source_url})
    out = pd.DataFrame(hits).sort_values(["county", "fid", "county_address"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"county buildings: {len(b)} | Virginia permitted sites matched: {out.fid.nunique()} of "
          f"{int(((fac.src == 'bi') & (fac.state == 'VA')).sum())} | rows: {len(out)}")
    if "--write-batch" in sys.argv:
        write_batch(out, fac)
    return 0


MIN_YEAR = 2005
BUILT = {"Completed", "Existing or Permitted"}


def record_url(county: str, address: str) -> str:
    """A link that returns just this building's record, so a reader can check it."""
    if county == "Loudoun":
        q = {"where": f"LU_ADDRESS LIKE '{address}%'", "outFields": "LU_ADDRESS,LU_USE,LU_DEVELOP_STATUS,LU_DEMOG_YEAR_BUILT"}
        base = LAYERS["loudoun"]["url"]
    else:
        q = {"where": f"Address='{address}'", "outFields": "BuildingName,Address,BuildingStatus,YearBuilt,OCCDate,PermitStatus"}
        base = LAYERS["prince_william"]["url"]
    return base + "?" + urllib.parse.urlencode({**q, "returnGeometry": "false", "f": "pjson"})


def write_batch(matches: pd.DataFrame, fac: pd.DataFrame) -> None:
    ver = ROOT / "pipeline" / "facilities" / "verified"
    paged = dated_from_a_page(ver)  # decided from the committed files alone, so a re-run gives the same batch
    recs = []
    for fid, g in matches.groupby("fid"):
        if fid in paged:
            continue  # already dated from a page a checker opened
        ok = g[g.status.isin(BUILT) & g.year_built.between(MIN_YEAR, date.today().year)].copy()
        if not len(ok):
            continue
        # An occupancy date far from the year built belongs to an earlier use of the address.
        ok["year"] = [int(str(o)[:4]) if isinstance(o, str) and o and abs(int(str(o)[:4]) - int(y)) <= 2 else int(y)
                      for o, y in zip(ok.occupancy_date, ok.year_built)]
        r = ok.sort_values("year").iloc[0]
        quote = (f"{r.county_address} | {r.building_name} | {r.status} | Year Built {int(r.year_built)} | occupancy {r.occupancy_date}"
                 if r.county == "Prince William" else
                 f"{r.county_address} | COM_DATA_CENTER | {r.status} | Demographic Year Built {int(r.year_built)}")
        recs.append({
            "fid": fid, "group": "county", "state": "VA", "is_data_center": True,
            "site_name": f"{g.permit_address.iloc[0]}" + (f" ({r.building_name})" if isinstance(r.building_name, str) else ""),
            "energized_year": int(r.year), "energized_year_source_url": record_url(r.county, r.county_address),
            "year_confidence": "medium", "year_basis": "government_record_year_built_or_construction_complete",
            "year_evidence_quote": quote,
            "year_site_match": f"{r.county} County record at the permit's street address ({len(g)} building record(s) matched).",
            "load_mw_2025": None, "load_basis": None, "load_source_url": None,
            "serving_utility": None, "utility_source_url": None, "utility_confidence": None,
            "notes": f"{r.county} County GIS, layer as of {r.layer_as_of}. The year is the building's "
                     + ("occupancy certificate" if isinstance(r.occupancy_date, str) and r.occupancy_date else "year built")
                     + ", which for a purpose-built data center is within about a year of first load.",
        })
    (ver / "batch_r3c_0.json").write_text(json.dumps(recs, indent=1) + "\n")
    print(f"batch_r3c_0.json: {len(recs)} sites dated from county records")


def dated_from_a_page(ver: Path) -> set[str]:
    """Sites with a usable start year in any verification file other than the county batch."""
    from pipeline.facilities.apply_verified import usable
    out: set[str] = set()
    for p in sorted(ver.glob("batch_*.json")):
        if p.name.startswith("batch_r3c_"):
            continue
        for r in json.loads(p.read_text()):
            if r.get("energized_year") is not None and usable(r.get("energized_year_source_url"), r.get("year_confidence")):
                out.add(r["fid"])
    return out
