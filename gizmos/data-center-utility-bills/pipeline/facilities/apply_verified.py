#!/usr/bin/env python3
"""Turn hand-verification results into tables the inventory build reads.

Inputs (all under pipeline/facilities/verified/, each value carrying a source
URL and a confidence):
  batch_<k>.json      round 1: largest sites, dating sample, unplaced Epoch sites
  batch_r2_<k>.json   round 2: large sites still lacking a serving utility
  batch_r3_<k>.json   round 3: large sites still dated only by a permit (D-10, D-15)
  batch_r3b_<k>.json  round 3 retry of sites the first pass could not source
  batch_r3bb_<k>.json second retry (same rules as the first)
  batch_r3c_<k>.json  years from government records that need no search: county GIS layers
                      (match_county_gis.py) and assessor, air-permit and registry records
                      (write_public_records_batch.py); medium confidence, fills gaps only,
                      never replaces a year or a status sourced from a page
  batch_r3s_<k>.json  the random sample of smaller sites (make_date_worklist.py --sample)
  batch_r3u_<k>.json  loose ends from earlier rounds settled by hand: utility names that
                      did not resolve, a duplicate permit row, a registry-dated year
  batch_v_<k>.json    serving utilities verified for the assignment check (D-46 ruling 4, D-48);
                      each records the kind of evidence and the date or period its page speaks to
  state_<ST>.json     state sweeps for states where our permit data is thin
  batch_c_<k>.json    the verification pass's records (D-58 to D-95), read LAST (step D); a record whose
                      assignment was withdrawn (pass_c_withdrawn.json, or corrections.WITHDRAWN_BY_RULING) or
                      that the corrections in force reopen is skipped, and each skip is printed

Outputs:
  overrides.csv   one row per facility id with the verified facts
  new_sites.csv   facilities the state sweeps found that we did not have

Rules for what becomes an override:

  * Only findings with a source URL and confidence high or medium.
  * Nothing that rests on a data-center directory site. Baxtel's terms prohibit
    data mining; directories are leads for a person to follow up, not data we
    build on or republish.
  * A serving utility must resolve to exactly one EIA utility in that state
    through the alias table. Names that do not resolve are listed, not guessed.
  * Sites in ERCOT's competitive area resolve to their wires company, which
    has no usable residential price (docs/DECISIONS.md, D-4). They stay in the
    inventory, marked outside the host-utility panel.
  * Behind-the-meter and direct-wholesale sites carry no load on a retail utility.
  * A site a dated public page shows as still planned or under construction is
    marked not yet operating and carries no load in the panel years (D-15).
  * A permit row that duplicates another (duplicate_of) is dropped, so a site is counted once.
  * Later files overwrite earlier ones field by field.

Run:  python3 -I pipeline/facilities/apply_verified.py [--no-pass-records] [--corrections FILE]
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.electricity import panel  # noqa: E402

VER = ROOT / "pipeline" / "facilities" / "verified"
BLOCKED_DOMAINS = {"baxtel.com", "datacentermap.com", "datacenters.com", "cleanview.co", "datacenterhawk.com"}
SAME_SITE_M = 500  # a "new" site this close to one we already have is that site
# Government records matched without a search (county GIS, assessor rolls, air-permit
# files) fill gaps only: they never replace a year that a checker sourced for the site
# from a page, and never a status a dated page supports.
BULK_RECORD_GROUPS = {"county", "public_record"}

# (pattern on the verifier's wording, pattern on the EIA utility name). First match wins,
# so specific arrangements come before utility names.
ALIASES: list[tuple[str, str]] = [
    (r"behind the meter|^none|self-supplied|co-located with the on-site plant", "__BTM__"),
    (r"oncor|centerpoint|aep texas|tnmp|texas-new mexico", "__ERCOT_WIRES__"),
    (r"new york power authority|nypa|nyiso|no retail utility", "__WHOLESALE__"),
    (r"^tennessee valley authority", "__WHOLESALE__"),
    (r"eversource|nstar", r"^nstar electric"),
    (r"national grid.*massachusetts|massachusetts electric", r"^massachusetts electric"),
    (r"evergy,? kansas metro", r"^evergy metro$"),
    (r"denton municipal", r"^city of denton"),
    (r"dominion|virginia electric", r"virginia electric & power"),
    (r"novec|northern virginia elec", r"northern virginia elec"),
    (r"mecklenburg", r"mecklenburg electric"),
    (r"aep ohio|ohio power", r"^ohio power"),
    (r"indiana michigan", r"indiana michigan power"),
    (r"nipsco|northern indiana pub", r"northern indiana pub"),
    (r"win energy", r"win energy|western indiana energy"),
    (r"arizona public service|\baps\b", r"arizona public service"),
    (r"salt river", r"salt river project"),
    (r"cps energy|city of san antonio", r"san antonio"),
    (r"austin energy", r"austin energy|city of austin"),
    (r"garland power", r"garland"),
    (r"silicon valley power|city of santa clara", r"santa clara"),
    (r"city of palo alto", r"^city of palo alto"),
    (r"commonwealth edison|comed", r"commonwealth edison"),
    (r"dte electric", r"dte electric"),
    (r"consumers energy", r"consumers energy"),
    (r"duke energy indiana", r"duke energy indiana"),
    (r"duke energy", r"duke energy carolinas"),
    (r"alabama power", r"alabama power"),
    (r"huntsville utilities", r"huntsville"),
    (r"georgia power", r"georgia power"),
    (r"walton e", r"walton electric member"),
    (r"aiken electric", r"aiken electric"),
    (r"berkeley electric", r"berkeley electric"),
    (r"lockhart power", r"lockhart power"),
    (r"lakeland electric", r"lakeland"),
    (r"entergy louisiana", r"entergy louisiana"),
    (r"entergy mississippi", r"entergy mississippi"),
    (r"evergy missouri west", r"^evergy missouri west$"),
    (r"evergy missouri metro|evergy metro", r"^evergy metro$"),
    (r"evergy", r"evergy metro|evergy missouri|kansas city power"),
    (r"grand river dam", r"grand river dam"),
    (r"oklahoma gas|og&e", r"oklahoma gas & electric"),
    (r"grant county pud|pud no\.? ?2 of grant", r"grant county"),
    (r"douglas county pud|pud no\.? ?1 of douglas", r"douglas county"),
    (r"idaho power", r"idaho power"),
    (r"lincoln electric", r"lincoln electric system"),
    (r"southern public power", r"southern public power"),
    (r"nebraska public power|nppd", r"nebraska public power"),
    (r"omaha public power|oppd", r"omaha public power"),
    (r"memphis light|mlgw", r"memphis"),
    (r"knoxville utilities", r"knoxville"),
    (r"lenoir city", r"^city of lenoir - \(tn\)$"),  # EIA's name for the Lenoir City Utilities Board
    (r"jackson energy authority", r"jackson"),
    (r"brightridge|johnson city", r"johnson city|brightridge"),
    (r"hopkinsville", r"hopkinsville"),
    (r"jackson purchase", r"jackson purchase"),
    (r"west kentucky rural", r"west kentucky"),
    (r"kentucky utilities", r"kentucky utilities"),
    (r"cass county electric", r"cass county"),
    (r"mountrail-williams", r"mountrail"),
    (r"nodak", r"nodak"),
    (r"otter tail", r"otter tail"),
    (r"montana-dakota", r"montana-dakota"),
    (r"midamerican", r"midamerican"),
    (r"sierra pacific", r"sierra pacific"),
    (r"nv energy|nevada power", r"nevada power"),
    (r"northern wasco", r"northern wasco"),
    (r"pacific power|rocky mountain power|pacificorp", r"pacificorp"),
    (r"portland general", r"portland general"),
    (r"public service company of new mexico|\bpnm\b", r"public service co of nm|public service co of new mexico"),
    (r"umatilla", r"umatilla electric"),
    (r"we energies|wisconsin electric", r"wisconsin electric power"),
    (r"xcel.*minnesota|northern states power", r"northern states power co - minnesota"),
    (r"cheyenne light|black hills", r"cheyenne light"),
    (r"con edison|consolidated edison", r"consolidated edison"),
    (r"orange & rockland|orange and rockland", r"orange & rockland"),
    (r"nyseg|new york state elec", r"new york state elec"),
    (r"ppl electric", r"ppl electric"),
    (r"west penn", r"^west penn power"),
    (r"elk river municipal", r"^city of elk river"),
    (r"colorado springs utilities", r"^city of colorado springs"),
    (r"united power", r"^united power"),
    (r"city of hamilton", r"^city of hamilton - \(oh\)$"),  # batch_c_4, bi:1250-0 (step D)
]
STATUS = {"__BTM__": "behind_the_meter", "__ERCOT_WIRES__": "ercot_wires_outside_panel",
          "__WHOLESALE__": "wholesale_direct"}


def domain(u) -> str | None:
    return urlparse(u).netloc.replace("www.", "") if isinstance(u, str) and u else None


def usable(url, confidence) -> bool:
    return bool(domain(url)) and domain(url) not in BLOCKED_DOMAINS and confidence in ("high", "medium")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:60]


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def first_fuel_is_not_a_start(fid: str, source: str, step_d: bool | None = None) -> bool:
    """D-96 reading (1), Joe at Stop 3 (2026-11-18): a first-generator-fuel year from batch_r3c_1.json for one of the five
    Oregon rows is not applied as a start year (corrections.FIRST_FUEL_NOT_A_START): first fuel supplies no operating-date
    bound. Everything else in the record is applied. This places nothing in the generic screen: each of the five is dated
    by its own date entry in the corrections file in force, which build_inventory applies. Off before step D."""
    from pipeline.facilities import corrections as cx
    on = STEP_D if step_d is None else step_d
    return bool(on) and fid in cx.FIRST_FUEL_NOT_A_START and source == cx.FIRST_FUEL_RECORD_FILE


STEP_D = True    # set False by --no-pass-records, which reproduces the overrides of 2026-11-14


def batch_order(ver: Path) -> tuple[list[str], list[str], list[str]]:
    """(every batch file in sorted order, the assignment check's batch_v files, the verification pass's batch_c files).

    The order of reading is: every other batch in sorted order, the state sweeps, batch_v, then batch_c LAST (step D).
    """
    batches = sorted(glob.glob(str(Path(ver) / "batch_*.json")))          # batch_<k> sorts before batch_r2_<k>
    assignment = [p for p in batches if Path(p).name.startswith("batch_v_")]
    pass_records = [p for p in batches if Path(p).name.startswith("batch_c_")]
    return batches, assignment, pass_records


def reading_plan(ver: Path, corrections_path: Path | None = None, withdrawn_path: Path | None = None) -> list[tuple]:
    """The stages in the order main() reads them: (name, files, records to skip)."""
    batches, assignment, pass_records = batch_order(ver)
    states = sorted(glob.glob(str(Path(ver) / "state_*.json")))
    return [("batches", [p for p in batches if p not in assignment and p not in pass_records], {}),
            ("state_sweeps", states, {}),
            ("assignment_check", assignment, {}),
            ("verification_pass", pass_records, pass_record_skips(corrections_path, withdrawn_path))]


def pass_record_skips(corrections_path: Path | None = None, withdrawn_path: Path | None = None) -> dict[str, str]:
    """batch_c records that are NOT applied: a withdrawn assignment the corrections in force do not re-adopt with an assign
    (a later re-verification of a once-withdrawn site, which the corrections assign, IS applied), and every site the
    corrections in force reopen."""
    from pipeline.facilities import corrections as cx
    cp = Path(corrections_path or cx.CORRECTIONS)
    corr = cx.load(cp) if cp.exists() else []
    assigned = {c["fid"] for c in corr if c["kind"] == "assign"}
    out = {f: why for f, why in cx.withdrawn_fids(withdrawn_path).items() if f not in assigned}
    for f in cx.reopened_fids(corr):
        out[f] = "reopened by the corrections in force"
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-pass-records", action="store_true",
                    help="build as before step D: leave out batch_c and apply the five first-fuel years "
                         "(reproduces the overrides of 2026-11-14)")
    ap.add_argument("--corrections", default=None, help="the corrections file in force (default corrections.CORRECTIONS)")
    args = ap.parse_args(argv)
    global STEP_D
    STEP_D = not args.no_pass_records
    work = json.loads((ROOT / "data" / "interim" / "verify_worklist.json").read_text())["batches"]
    ours = {i["fid"]: i for b in work for i in b}
    # Names are matched as EIA reported them, then read as the unit that id now belongs to,
    # so "West Penn Power" still finds its territory after the FirstEnergy consolidation.
    in_panel = panel.load_quantities()[["utility_id_eia", "state"]].drop_duplicates()
    units = (panel.load_reported_ids().rename(columns={"reported_name": "utility_name"})
             .merge(in_panel, on=["utility_id_eia", "state"])[["utility_id_eia", "state", "utility_name"]])
    fac_path = ROOT / "data" / "interim" / "facilities.parquet"
    known = pd.read_parquet(fac_path) if fac_path.exists() else pd.DataFrame(columns=["fid", "lat", "lon", "src"])
    known = known[known.src != "state_search"]  # never match a new site to an earlier copy of itself

    acc: dict[str, dict] = {}
    new_sites: dict[str, dict] = {}
    unresolved: list[tuple] = []

    def evidence(o: dict, r: dict) -> None:
        """What kind of page a serving utility rests on and the date or period it speaks to (D-46, second addendum; D-48).
        Verifications made before 2026-11-14 carry neither; a later file that re-verifies a site replaces both."""
        o["utility_evidence_kind"] = r.get("utility_evidence_kind")
        o["utility_evidence_period"] = r.get("utility_evidence_period")
        if group_of(r) == "assign" and not (o["utility_evidence_kind"] and o["utility_evidence_period"]):
            raise SystemExit(f"{r['fid']}: an assignment verification needs utility_evidence_kind and utility_evidence_period (D-48)")

    def group_of(r: dict) -> str:
        return r.get("group", "big")

    def absorb(r: dict, fid: str, state: str | None, group: str, source: str = "") -> None:
        o = acc.setdefault(fid, {"fid": fid, "group": group})
        o["state"] = state
        if r.get("is_data_center") is False:
            o["drop_not_data_center"] = True
        if r.get("duplicate_of"):  # the same site under a second permit row: counted once, on the other id
            o["drop_not_data_center"] = True
            o["duplicate_of"] = r["duplicate_of"]
        if r.get("facility_type"):
            o["facility_type"] = r["facility_type"]
        if group == "epoch" and r.get("lat") is not None and r.get("lon") is not None:
            o["lat"], o["lon"] = float(r["lat"]), float(r["lon"])
        util, url, conf = r.get("serving_utility"), r.get("utility_source_url"), r.get("utility_confidence")
        arrangement = r.get("service_arrangement")
        target = next((t for pat, t in ALIASES if isinstance(util, str) and re.search(pat, util.lower())), None)
        if usable(url, conf) and (arrangement in ("behind_the_meter", "wholesale_direct") or target in STATUS):
            o["utility_status"] = arrangement if arrangement in ("behind_the_meter", "wholesale_direct") else STATUS[target]
            o["utility_source_url"] = url
            o.pop("utility_id_eia", None)
            o.pop("utility_name", None)
            evidence(o, r)
        elif isinstance(util, str) and usable(url, conf):
            if target:
                m = units[(units.state == state) & units.utility_name.str.lower().str.contains(target, regex=True, na=False)]
                m = m.drop_duplicates("utility_id_eia")  # two old names of one unit are one match
                if len(m) == 1:
                    o.update(utility_id_eia=int(m.utility_id_eia.iloc[0]), utility_name=m.utility_name.iloc[0],
                             utility_status="verified", utility_source_url=url)
                    evidence(o, r)
                else:
                    unresolved.append((fid, state, util[:60], f"{len(m)} EIA matches"))
            else:
                unresolved.append((fid, state, util[:60], "no alias"))
        if first_fuel_is_not_a_start(fid, source):
            set_aside.append((source, fid, r.get("energized_year")))
        elif r.get("energized_year") is not None and usable(r.get("energized_year_source_url"), r.get("year_confidence")) \
                and not (group in BULK_RECORD_GROUPS and (o.get("energized_year") is not None or o.get("not_yet_operating"))):
            o["energized_year"] = int(r["energized_year"])
            o["energized_year_source_url"] = r["energized_year_source_url"]
            o["year_confidence"] = r["year_confidence"]
            for k in ("not_yet_operating", "status_source_url", "status_as_of"):
                o.pop(k, None)  # a sourced start year supersedes an earlier "not yet operating"
        elif r.get("operating_status") == "not_yet_operating" and usable(r.get("status_source_url"), r.get("status_confidence")):
            o["not_yet_operating"] = True
            o["status_source_url"] = r["status_source_url"]
            o["status_as_of"] = r.get("status_as_of")
            o.pop("energized_year", None)
            o.pop("energized_year_source_url", None)
        ld_dom = domain(r.get("load_source_url"))
        if r.get("load_mw_2025") is not None and ld_dom and ld_dom not in BLOCKED_DOMAINS:
            o["load_mw_2025"] = float(r["load_mw_2025"])
            o["load_basis"] = r.get("load_basis")
            o["load_source_url"] = r["load_source_url"]

    def absorb_batches(paths: list[str], skip: dict | None = None) -> None:
        for p in paths:
            for r in json.loads(Path(p).read_text()):
                if skip and r["fid"] in skip:
                    skipped.append((Path(p).name, r["fid"], skip[r["fid"]]))
                    continue
                st = r.get("state") if isinstance(r.get("state"), str) and len(r["state"]) == 2 else ours.get(r["fid"], {}).get("state")
                absorb(r, r["fid"], st, r.get("group", "big"), Path(p).name)

    skipped: list[tuple] = []
    set_aside: list[tuple] = []
    known_ids = set(known.fid)

    def absorb_state_sweeps(paths: list[str]) -> None:
        for p in paths:
            for r in json.loads(Path(p).read_text()):
                fid = r.get("matches_known_fid")
                if fid and fid not in known_ids:
                    fid = None  # the checker named an id we do not have
                if not fid and r.get("lat") is not None and r.get("lon") is not None and len(known):
                    d = haversine_m(float(r["lat"]), float(r["lon"]), known.lat.values, known.lon.values)
                    if np.nanmin(d) <= SAME_SITE_M:
                        fid = known.fid.values[int(np.nanargmin(d))]
                if not fid:
                    fid = f"state:{r['state']}:{slug(r['site_name'])}"
                    new_sites[fid] = {"fid": fid, "state": r["state"], "name": r.get("site_name"),
                                      "operator": r.get("operator"), "facility_type": r.get("facility_type"),
                                      "city": r.get("city"), "county": r.get("county"),
                                      "lat": r.get("lat"), "lon": r.get("lon"),
                                      "location_source_url": r.get("location_source_url")}
                absorb(r, fid, r["state"], "state")

    # The order of reading (reading_plan): every other batch, the state sweeps, the assignment check's batch_v, and
    # the verification pass's batch_c LAST, so no older file overwrites a pass record. A batch_c record whose
    # assignment was withdrawn, or that the corrections in force reopen, is skipped whole and printed.
    for stage, paths, skip in reading_plan(VER, args.corrections):
        if stage == "verification_pass" and args.no_pass_records:
            continue
        if stage == "state_sweeps":
            absorb_state_sweeps(paths)
        else:
            absorb_batches(paths, skip=skip)

    df = pd.DataFrame([o for o in acc.values() if len(o) > 3])
    df.to_csv(VER / "overrides.csv", index=False)
    pd.DataFrame(list(new_sites.values())).to_csv(VER / "new_sites.csv", index=False)
    print("overrides written:", len(df), "| new sites:", len(new_sites))
    print("first-fuel years not applied as start years (D-96 reading (1)):", set_aside)
    print("verification-pass records skipped:", len(skipped))
    for s in skipped:
        print("   ", s)
    for c in ["utility_id_eia", "energized_year", "not_yet_operating", "load_mw_2025", "lat", "drop_not_data_center"]:
        if c in df:
            print(f"  {c}: {int(df[c].notna().sum())}")
    print("  utility_status:", df.utility_status.value_counts().to_dict())
    print("  facility_type:", df.facility_type.value_counts().to_dict() if "facility_type" in df else {})
    # A name one file could not resolve may be settled by a later file; list only what is still open.
    unresolved = [u for u in unresolved if not acc.get(u[0], {}).get("utility_status")]
    print("unresolved utility names:", len(unresolved))
    for u in unresolved:
        print("   ", u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
