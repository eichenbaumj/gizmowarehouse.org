#!/usr/bin/env python3
"""Step D, inventory side: the adopted corrections reach the real inventory (docs/gate1/step-d-inventory-design-2026-11-18.md,
with Joe's rulings on its ten points recorded in that note's addendum).

Load and sales only. Nothing here reads a price, opens data/blind, or touches the availability files.

How a correction is READ is pass_c_expand's, imported unchanged (`parse_corrections`, `Correction.history`,
`_apply_fields`): this module only hands it the frame build_inventory has in hand. What the real inventory DOES with a
history is build_inventory's own arithmetic (`state_anchor`, `site_mw`, `pick_utilities`). The scratch rebuild in
pass_c_expand is therefore an independent check on the real one (pipeline/facilities/step_d_check.py).

Where each kind enters build_inventory.main:
  location        before the territory join (`apply_locations`): a parcel centroid, labelled a coordinate convention;
                  the territory candidates become the UNION of those at the old point and those at the new one, so a
                  supplier is never dropped because a centroid falls on one side of a line (Joe, R8).
  year-built      after apply_overrides (`relabel_year_built`): the 115 rows whose start is a year built on a
                  government record keep their years, relabelled "year built used as start by convention"; the review
                  of those records is recorded as unpursued (Joe, R1).
  date, capacity  after mw_full_raw is set and before state_anchor (`apply_timing`): each row's history at its
                  convention. A row whose start (or capacity question) has no convention is marked LOAD UNKNOWN: no
                  single history, no load in the frame, `load_unknown` True. Unknown, not zero and not "never" (Joe, R2).
  assign, reopen, candidates, narrow
                  after the utility block and the successor mapping (`apply_assignment`).

The 'stress' field a date entry may carry (Joe, R4) is ignored here: a stress scenario is reported by timing.py and is
never a history the inventory carries or an admissible history that decides a place.

Run as a module only (imported by build_inventory, apply_verified, timing, later_start, step_d_check).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

VER = ROOT / "pipeline" / "facilities" / "verified"
CORRECTIONS = VER / "pass_c_corrections_s17.json"          # the file in force (D-95); the orchestrator may point elsewhere
LOCATIONS = VER / "step_d_locations.json"
GOV_YEARS = VER / "government_record_years.csv"
WITHDRAWN = VER / "pass_c_withdrawn.json"
DATE_EVIDENCE = VER / "date_evidence.csv"

ASSIGNMENT_KINDS = ("assign", "narrow", "candidates", "reopen")
TIMING_KINDS = ("size", "date", "phases", "capacity_split", "not_a_site")

# A pass assignment withdrawn by a ruling whose record still sits in a batch_c file. Kept here, citing the ruling, so no
# record file is edited.
WITHDRAWN_BY_RULING = {
    "bi:941-0": "D-95 (Joe, 2026-11-18): the pass's assignment withdrawn; the row goes back to the inventory's two candidates",
}
# The five Oregon first-fuel start years (D-17) are NOT applied as start years: first generator fuel supplies no
# operating-date bound (D-61 5.1; D-96 reading (1); Joe at Stop 3, 2026-11-18). Their records in batch_r3c_1.json are
# otherwise applied in full. Each row is DATED BY ITS OWN DATE ENTRY in the corrections file in force (Joe at Stop 3,
# 2026-11-18, the evidence-based treatment): bi:820-0 not before 2018 on a new-source construction permit on file, the
# other four open below; every late end is the permit-based year, a labelled convention and a tested end. Nothing here
# places them in the generic screen; a row with a date entry leaves it like any other dated row. (Until 2026-11-18 they
# were plain permit-dated rows in the screen, the session's application, overruled at Stop 3.) bi:841-0 (a DEQ
# statement that the facility "was built in 2012") is not first fuel and is not here.
FIRST_FUEL_RECORD_FILE = "batch_r3c_1.json"
FIRST_FUEL_NOT_A_START = {
    fid: ("first generator fuel is on file as evidence that generators were present; it supplies no operating-date bound "
          "(D-61 5.1; D-96 reading (1); Joe at Stop 3, 2026-11-18). The row is dated by its date entry in the corrections "
          "file in force.")
    for fid in ("bi:819-0", "bi:820-0", "bi:822-0", "bi:823-0", "bi:846-0")}

# Rows whose location stays unresolved (Joe, R8): their points are carried as they are and are not verified.
LOCATION_UNRESOLVED = {
    "bi:446-0": "FedEx, Colorado Springs: the inventory's point is on another owner's parcel (350 Spectrum Loop); not corrected (Joe, R8)",
    "bi:937-0": "NSA Utah Data Center: the inventory's point is a residential parcel in Lehi; no record gives the location; not corrected (Joe, R8)",
}

# date_basis labels written by step D. The permit label is build_inventory's own.
PERMIT_LABEL = "first_generator_permit_plus_lag"
YEAR_BUILT_LABEL = "year_built_used_as_start_by_convention"
EVIDENCE_CONVENTION_LABEL = "convention_latest_year_the_evidence_allows"          # D-58 rule 1.4
INTERVAL_LABEL = "convention_year_within_a_dated_interval"
UNRESOLVED_LABEL = "unresolved_start_load_unknown"
NOT_A_SITE_LABEL = "not_a_site_by_correction"
YEAR_BUILT_REVIEW = ("unpursued: the record was not opened for what the building was built as; Joe's closure ruling "
                     "(R1, 2026-11-18) supersedes D-63 rule 3's requirement to read it in step D")
LOCATION_CONVENTION = "parcel_centroid_coordinate_convention"
LOCATION_AS_SOURCED = "as_sourced"
LOCATION_UNRESOLVED_LABEL = "location_unresolved"

INTERVAL_COLUMNS = ["date_rule", "date_inventory_year", "date_earliest", "date_latest", "date_never_possible",
                    "date_ends", "date_convention", "date_convention_is", "capacity_first_share", "capacity_convention",
                    "load_unknown", "load_unknown_why"]


# ---- fingerprints -----------------------------------------------------------------------------------------------

def sha256(path: Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fingerprint(files: list, **settings) -> dict:
    """SHA-256 of each file (None where absent) and the settings a run used. Written into every step D output."""
    out = {"files": {}, "settings": settings}
    for f in files:
        p = Path(f)
        try:
            key = str(p.resolve().relative_to(ROOT))
        except ValueError:
            key = str(p)
        out["files"][key] = sha256(p)
    return out


def code_files() -> list[Path]:
    here = ROOT / "pipeline" / "facilities"
    return [here / n for n in ("corrections.py", "apply_verified.py", "build_inventory.py", "timing.py", "dating_sensitivity.py",
                               "ten_year.py", "later_start.py", "treatment_bounds.py", "step_d_check.py",
                               "pass_c_expand.py", "pass_c_exact.py", "assignment.py", "buildout.py")]


# ---- reading the files ------------------------------------------------------------------------------------------

def load(path: Path | None = None) -> list[dict]:
    path = Path(path or CORRECTIONS)
    out = json.loads(path.read_text())
    if not isinstance(out, list):
        raise ValueError(f"{path}: a corrections file is a list of corrections")
    for c in out:
        if c.get("kind") not in ASSIGNMENT_KINDS + TIMING_KINDS:
            raise ValueError(f"{path}: {c.get('fid')}: unknown kind {c.get('kind')!r}")
        if "stress" in c and c["kind"] != "date":
            raise ValueError(f"{c['fid']}: only a date entry may carry a stress scenario")
    return out


def stripped(corrections: list[dict]) -> list[dict]:
    """The corrections without the fields pass_c_expand does not read (it ignores them anyway; this keeps it explicit)."""
    return [{k: v for k, v in c.items() if k not in ("stress",)} for c in corrections]


def split(corrections: list[dict]) -> tuple[list[dict], list[dict]]:
    return ([c for c in corrections if c["kind"] in ASSIGNMENT_KINDS],
            [c for c in corrections if c["kind"] in TIMING_KINDS])


def withdrawn_fids(path: Path | None = None) -> dict[str, str]:
    p = Path(path or WITHDRAWN)
    out = dict(WITHDRAWN_BY_RULING)
    if p.exists():
        for r in json.loads(p.read_text()):
            out.setdefault(r["fid"], f"withdrawn under {r.get('withdrawn_under', 'the pass')}")
    return out


def reopened_fids(corrections: list[dict]) -> set[str]:
    return {c["fid"] for c in corrections if c["kind"] == "reopen"}


def first_fuel_report(fac: pd.DataFrame, gov: pd.DataFrame | None = None, permit_lag: int = 1) -> list[dict]:
    """The five first-fuel rows by name, after apply_timing: the first-fuel year set aside, the permit-based year, and the
    interval their date entry gives them. Stops if the year the build had before the entry was applied
    (`date_inventory_year`) is not the permit-based year (a first-fuel year leaked in as a start), or if a row has no date
    entry applied (the corrections file in force governs these rows)."""
    gov = pd.read_csv(GOV_YEARS) if gov is None else gov
    ff = gov.set_index("fid").inventory_year
    out = []

    def val(x):
        if x is None or (not isinstance(x, str) and pd.isna(x)):
            return None
        return int(x) if isinstance(x, (int, float, np.integer, np.floating)) else x
    for fid, why in FIRST_FUEL_NOT_A_START.items():
        r = fac.loc[fid]
        pb = None if pd.isna(r.first_permit_year) else int(r.first_permit_year) + permit_lag
        if r.get("date_rule") != "interval":
            raise ValueError(f"{fid}: no date entry applied (date_rule {r.get('date_rule')!r}); the five Oregon rows are dated "
                             f"by their entries in the corrections file in force")
        before = val(r.get("date_inventory_year"))
        if before != pb:
            raise ValueError(f"{fid}: expected the build's year before the entry to be its permit-based year {pb}, found "
                             f"{before} (a first-fuel year must not be applied as a start)")
        out.append({"fid": fid, "first_fuel_year_set_aside": None if fid not in ff.index else int(ff[fid]),
                    "permit_based_year": pb, "year_carried": val(r.energized_year), "date_basis": r.date_basis,
                    "dated_by": "its date entry in the corrections file in force",
                    "interval": {"earliest": val(r.get("date_earliest")), "latest": val(r.get("date_latest")),
                                 "convention": val(r.get("date_convention")), "ends": r.get("date_ends")},
                    "note": why})
    return out


def load_locations(path: Path | None = None) -> dict:
    p = Path(path or LOCATIONS)
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    out = {}
    for r in d.get("locations", []):
        if r.get("centroid") is None:
            continue                                                   # a request that returned nothing corrects nothing
        out[r["fid"]] = r
    return out


# ---- the view pass_c_expand.parse_corrections reads ---------------------------------------------------------------

def view(fac: pd.DataFrame, phases: dict, fy_fids=()) -> SimpleNamespace:
    """What px.parse_corrections reads from an Inputs (fac by fid, fixed, phases, the fids carrying site-years)."""
    fixed = (fac.src == "epoch") | (fac.get("load_history", pd.Series("", index=fac.index)) == "operator_reported_energy")
    return SimpleNamespace(fac=fac, fixed=fixed, phases=phases, fy=pd.DataFrame({"fid": list(fy_fids)}))


# ---- year-built relabel (Joe, R1) ----------------------------------------------------------------------------------

def relabel_year_built(fac: pd.DataFrame, gov: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Relabel the rows whose start is a year built on a government record. Labels only: no year and no load changes.

    `fac` is indexed by fid. Every year-built row has to be found carrying a sourced year (`verified_public_source`);
    otherwise the run stops, because the table and the inventory no longer describe the same rows.
    """
    gov = pd.read_csv(GOV_YEARS) if gov is None else gov
    ids = list(gov.fid[gov.record_is == "year built"])
    missing = [f for f in ids if f not in fac.index]
    if missing:
        raise ValueError(f"{len(missing)} year-built rows are not in the inventory: {missing[:10]}")
    wrong = [f for f in ids if fac.date_basis[f] != "verified_public_source"]
    if wrong:
        raise ValueError(f"{len(wrong)} year-built rows do not carry a sourced year ('verified_public_source'): {wrong[:10]}")
    fac = fac.copy()
    fac.loc[ids, "date_basis"] = YEAR_BUILT_LABEL
    if "year_built_review" not in fac:
        fac["year_built_review"] = None
    fac.loc[ids, "year_built_review"] = YEAR_BUILT_REVIEW
    return fac, ids


def year_built_table(fac: pd.DataFrame, ids: list[str], corrections: list[dict], permit_lag: int = 1) -> pd.DataFrame:
    """One row for each of the year-built rows (Joe, R1): which carry two different years (a provisional interval),
    which have one year (the year built and the permit-based year coincide), which have no size. None is verified."""
    prov = {c["fid"]: c for c in corrections if c["kind"] == "date" and c.get("convention_is") == "provisional"}
    rows = []
    for f in ids:
        r = fac.loc[f]
        pb = (r.first_permit_year + permit_lag) if pd.notna(r.get("first_permit_year", np.nan)) else np.nan
        yb = r.date_inventory_year if pd.notna(r.get("date_inventory_year", np.nan)) else r.energized_year
        size = pd.notna(r.mw_full_raw)
        one = pd.notna(pb) and pd.notna(yb) and int(pb) == int(yb)
        if size and not one:
            cls = "two_years_differ_carried_as_a_provisional_interval"
        elif one:
            cls = "one_year_the_year_built_and_the_permit_based_year_coincide"
        else:
            cls = "no_size_carries_no_load_in_any_history_and_the_years_differ"
        rows.append({"fid": f, "state": r.state, "utility_id_eia": r.utility_id_eia, "mw_full_raw": r.mw_full_raw,
                     "year_built": yb, "permit_based_year": pb, "class": cls, "has_size": bool(size),
                     "provisional_interval_in_the_corrections": f in prov,
                     "interval": (f"{prov[f]['earliest']}-{prov[f]['latest']}" if f in prov else None),
                     "status": "year built used as start by convention; not a verified operating start",
                     "record_review": YEAR_BUILT_REVIEW})
    t = pd.DataFrame(rows)
    bad = t[(t["class"] == "two_years_differ_carried_as_a_provisional_interval") != t.provisional_interval_in_the_corrections]
    if len(bad):
        raise ValueError(f"the corrections' provisional intervals and the rows whose two years differ do not match: "
                         f"{list(bad.fid)[:10]}")
    return t


# ---- timing (dates, capacity) -----------------------------------------------------------------------------------

def _label(c, inventory_year) -> str:
    d = c.date
    if d.get("convention_is") == "provisional":
        return YEAR_BUILT_LABEL
    if pd.isna(inventory_year):
        return INTERVAL_LABEL
    lo = -math.inf if d.get("earliest") is None else d["earliest"]
    hi = math.inf if (d.get("never_is_possible") or d.get("latest") is None) else d["latest"]
    return EVIDENCE_CONVENTION_LABEL if not (lo <= inventory_year <= hi) else INTERVAL_LABEL


def apply_timing(fac: pd.DataFrame, phases: dict, corrections: list[dict], fy_fids=()) -> tuple[pd.DataFrame, dict, dict]:
    """Every date, capacity, size, phases and not_a_site correction at its convention, on a copy indexed by fid.

    Returns (fac, phases, report). A row with a question that has no convention is LOAD UNKNOWN: its energized_year is
    cleared so it carries no load in the frame, `load_unknown` is True, and its inventory year is kept in
    `date_inventory_year` so the enumeration can rebuild every admissible history (Joe, R2).
    """
    _, timing = split(corrections)
    fac = fac.copy()
    phases = dict(phases)
    for col in INTERVAL_COLUMNS:
        if col not in fac:
            fac[col] = (False if col == "load_unknown" else None)
    fac["load_unknown"] = fac.load_unknown.fillna(False).astype(bool)
    if not timing:
        return fac, phases, {"applied": [], "load_unknown": []}
    parsed = px.parse_corrections(stripped(timing), view(fac, phases, fy_fids))
    applied, unknown = [], []
    for fid, c in parsed.items():
        inv_year = fac.energized_year[fid]
        fac.loc[fid, "date_inventory_year"] = inv_year
        if c.size is not None:
            fac.loc[fid, ["mw_full", "mw_full_raw"]] = [c.size, c.size]
            if c.size_measured:
                fac.loc[fid, "mw_basis"] = "verified_public_figure"
        if c.date:
            d = c.date
            fac.loc[fid, ["date_rule", "date_earliest", "date_latest", "date_never_possible", "date_ends", "date_convention",
                          "date_convention_is"]] = ["interval", d.get("earliest"), d.get("latest"), bool(d.get("never_is_possible")),
                                                   d.get("ends"), d.get("convention"), d.get("convention_is")]
        if c.split:
            fac.loc[fid, ["capacity_first_share", "capacity_convention"]] = [c.split.get("first_share"), c.split.get("convention")]
            if not c.date:
                fac.loc[fid, "date_rule"] = "capacity_split"
        if c.not_a_site:
            fac.loc[fid, ["energized_year", "date_basis", "date_rule"]] = [np.nan, NOT_A_SITE_LABEL, "not_a_site"]
            applied.append(fid)
            continue
        loose = [q for q in c.questions() if c.convention(q) is None]
        if loose:
            fac.loc[fid, ["energized_year", "date_basis", "load_unknown", "load_unknown_why"]] = [
                np.nan, UNRESOLVED_LABEL, True,
                f"no convention for its {' and '.join(loose)} question: no single load history is assigned; the load is "
                f"unknown, not zero and not 'never operating' (Joe, R2)"]
            phases.pop(fid, None)
            unknown.append(fid)
            continue
        h = c.history({}) or None
        if h is None:                                                   # a size alone
            applied.append(fid)
            continue
        if h[0] == "never":
            fac.loc[fid, "energized_year"] = np.nan
        elif h[0] == "ramp":
            fac.loc[fid, "energized_year"] = float(h[1])
            phases.pop(fid, None)
        else:                                                            # phases: a split at its convention, or dated phases
            phases[fid] = [(float(y), float(s)) for y, s in h[1]]
            if pd.isna(inv_year):
                fac.loc[fid, "energized_year"] = float(h[1][0][0])
            fac.loc[fid, "load_history"] = "capacity_split_at_its_convention" if c.split else "phases_by_correction"
        if c.date:
            fac.loc[fid, "date_basis"] = _label(c, inv_year)
        applied.append(fid)
    return fac, phases, {"applied": sorted(applied), "load_unknown": sorted(unknown)}


# ---- assignment ---------------------------------------------------------------------------------------------------

def apply_assignment(fac: pd.DataFrame, corrections: list[dict], withdrawn: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """assign, reopen, candidates and narrow corrections on a copy indexed by fid, after the utility block.

    An assign that the verification records already put in place is left as the records put it (the label an ERCOT
    wires company carries is kept); one they contradict stops the run. Every withdrawn assignment still carried as
    verified must be re-verified by an assign correction or reopened, or the run stops.
    """
    asgn, _ = split(corrections)
    fac = fac.copy()
    report = {"assign_already_in_place": [], "assign_applied": [], "reopened": [], "candidates_widened": [], "narrowed": []}
    parsed = px.parse_corrections(stripped(asgn), view(fac, {}, ())) if asgn else {}
    measured = pd.Series(False, index=fac.index)
    off_kinds = [a for a in asg.VERIFIED if a != "verified_by_hand"]
    for fid, c in parsed.items():
        now_u, now_a = fac.utility_id_eia[fid], fac.utility_assign[fid]
        if c.assign is not None:
            if c.assign == px.OFF:
                ok = pd.isna(now_u) and now_a in off_kinds
            else:
                ok = pd.notna(now_u) and int(now_u) == c.assign[0] and now_a in asg.VERIFIED
                if now_a in asg.VERIFIED and pd.notna(now_u) and int(now_u) != c.assign[0]:
                    raise ValueError(f"{fid}: the verification records put it on {int(now_u)} and the corrections assign it to "
                                     f"{c.assign[0]}; they disagree and the run stops")
            if c.assign == px.OFF and now_a == "verified_by_hand":
                raise ValueError(f"{fid}: the records verify it on a panel utility and the corrections put it off the panel")
            if ok:
                report["assign_already_in_place"].append(fid)
                continue
            report["assign_applied"].append(fid)
        px._apply_fields(fac, measured, c)
        if c.reopen is not None:
            report["reopened"].append(fid)
        if c.widen is not None:
            report["candidates_widened"].append(fid)
        if c.narrow is not None:
            report["narrowed"].append(fid)
    wd = withdrawn if withdrawn is not None else withdrawn_fids()
    assigned = {c["fid"] for c in asgn if c["kind"] == "assign"}
    still = [f for f in wd if f in fac.index and fac.utility_assign[f] in asg.VERIFIED
             and f not in assigned and f not in reopened_fids(corrections)]
    if still:
        raise ValueError(f"withdrawn assignments still carried as verified, with no later record and no reopen: {still}")
    return fac, {k: sorted(v) for k, v in report.items()}


# ---- locations (Joe, R8) -------------------------------------------------------------------------------------------

LOCATION_LOG = ROOT / "pipeline" / "facilities" / "leads" / "step_d_coordinates_log_2026-11-18.csv"
LOG_COLUMNS = ["requested_at_utc", "fid", "parcel_id", "url", "http_status", "bytes", "features_returned", "outcome"]
CLIENT = "Python-urllib (17A data-center study, step D parcel geometry; one request per parcel)"


def parcel_requests(batch_path: Path | None = None) -> list[dict]:
    """The recorded parcel ids of the rows whose coordinates step D corrects (Joe, R8): one request per parcel id, to the
    county layer the record names. Read from the verification record itself (batch_c_6.json, `parcel_tie`)."""
    import re
    rows = json.loads(Path(batch_path or VER / "batch_c_6.json").read_text())
    out = []
    for r in rows:
        if r["fid"] not in ("bi:910-0", "bi:911-0", "epoch:Microsoft SAT14"):
            continue
        tie = r["parcel_tie"]
        for pid in re.findall(r"\d{6,}", tie["where"]):
            out.append({"fid": r["fid"], "parcel_id": int(pid), "layer": tie["layer"], "tied_by": tie["tied_by"],
                        "owner_on_record": tie.get("owner"), "record": "pipeline/facilities/verified/batch_c_6.json"})
    return out


def esri_rings_to_geojson(rings: list) -> dict:
    """An Esri polygon's rings as a GeoJSON MultiPolygon: clockwise rings are outer rings (Esri's rule), counter-
    clockwise rings are holes of the outer ring that contains them."""
    from shapely.geometry import Polygon, mapping
    def area2(r):
        return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]))
    outers = [Polygon(r) for r in rings if area2(r) < 0]
    holes = [Polygon(r) for r in rings if area2(r) > 0]
    polys = []
    for o in outers:
        mine = [list(h.exterior.coords) for h in holes if o.contains(h.representative_point())]
        polys.append(Polygon(o.exterior.coords, mine))
    if not polys:
        raise ValueError("an Esri polygon with no clockwise (outer) ring")
    return {"type": "MultiPolygon", "coordinates": [mapping(p)["coordinates"] for p in polys]}


def fetch_parcel_locations(out_path: Path | None = None, log_path: Path | None = None, opener=None) -> dict:
    """ONE logged geometry request per recorded parcel id, no retries (Joe, R8). Refuses to send a request for a parcel
    the log already records, so a second run cannot become a retry. Writes step_d_locations.json: per row the parcel ids,
    each parcel's geometry as returned (WGS84), and the centroid of their union, labelled a coordinate convention."""
    import csv
    import datetime as dt
    import urllib.parse
    import urllib.request
    from shapely.geometry import shape
    from shapely.ops import unary_union
    log_path = Path(log_path or LOCATION_LOG)
    out_path = Path(out_path or LOCATIONS)
    done = set()
    if log_path.exists():
        with log_path.open() as fh:
            done = {(r["fid"], int(r["parcel_id"])) for r in csv.DictReader(fh)}
    reqs = parcel_requests()
    if any((q["fid"], q["parcel_id"]) in done for q in reqs):
        raise SystemExit(f"{log_path} already records a request for these parcels; no retries are authorized (Joe, R8)")
    opener = opener or urllib.request.urlopen
    new_log = not log_path.exists()
    geoms: dict = {}
    with log_path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_COLUMNS)
        if new_log:
            w.writeheader()
        for q in reqs:
            params = {"where": f"PropID={q['parcel_id']}", "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json"}
            url = q["layer"].rstrip("/") + "/query?" + urllib.parse.urlencode(params)
            row = {"requested_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "fid": q["fid"],
                   "parcel_id": q["parcel_id"], "url": url, "http_status": "", "bytes": 0, "features_returned": 0, "outcome": ""}
            try:
                req = urllib.request.Request(url, headers={"User-Agent": CLIENT})
                with opener(req, timeout=60) as resp:
                    body = resp.read()
                    row["http_status"], row["bytes"] = getattr(resp, "status", 200), len(body)
                gj = json.loads(body)
                feats = gj.get("features", [])
                row["features_returned"] = len(feats)
                if len(feats) == 1 and (feats[0].get("geometry") or {}).get("rings"):
                    geoms.setdefault(q["fid"], []).append({"parcel_id": q["parcel_id"],
                                                           "geometry": esri_rings_to_geojson(feats[0]["geometry"]["rings"]),
                                                           "esri_geometry": feats[0]["geometry"],
                                                           "attributes": feats[0].get("attributes", {})})
                    row["outcome"] = "one parcel with geometry"
                else:
                    row["outcome"] = f"not used: {len(feats)} features" + ("" if not gj.get("error") else f"; error {gj['error']}")
            except Exception as e:                                       # recorded, never retried
                row["outcome"] = f"failed: {repr(e)[:200]}"
            w.writerow(row)
    locs = []
    for fid in dict.fromkeys(q["fid"] for q in reqs):
        mine = [q for q in reqs if q["fid"] == fid]
        got = geoms.get(fid, [])
        rec = {"fid": fid, "parcel_ids": [q["parcel_id"] for q in mine], "layer": mine[0]["layer"],
               "tying_record": mine[0]["record"], "tied_by": mine[0]["tied_by"], "owner_on_record": mine[0]["owner_on_record"],
               "parcels": got, "centroid": None,
               "label": "parcel centroid used as a coordinate convention (Joe, R8, 2026-11-18); not a surveyed location",
               "log": str(log_path.relative_to(ROOT)) if log_path.is_relative_to(ROOT) else str(log_path)}
        if got and len(got) == len(mine):
            u = unary_union([shape(g["geometry"]) for g in got])
            c = u.centroid
            rec["centroid"] = {"lat": float(c.y), "lon": float(c.x), "computed_as": "centroid of the union of the parcels "
                               "in WGS84 degrees (shapely); a convention"}
        else:
            rec["why_no_centroid"] = "not every recorded parcel returned one geometry; the row's point is not corrected"
        locs.append(rec)
    doc = {"what_this_is": "Step D coordinate corrections (Joe, R8): one logged request per recorded parcel id; the parcel "
                           "centroid is a coordinate convention, the parcel geometry is kept for the adopted precision checks.",
           "not_corrected": LOCATION_UNRESOLVED, "locations": locs}
    out_path.write_text(json.dumps(doc, indent=1) + "\n")
    return doc


def union_candidates(new: list, old: list) -> list:
    """The corrected point's candidates (smallest polygon first), then any the old point had that the new one lacks.
    A supplier is never removed because a centroid falls on one side of a boundary."""
    return list(dict.fromkeys([int(x) for x in (new or [])] + [int(x) for x in (old or [])]))


# ---- what the unknown-load rows reach (Joe, R2) ----------------------------------------------------------------------

def unknown_load_reach(fac: pd.DataFrame, fy: pd.DataFrame, anchor: pd.DataFrame, units, corrections: list[dict],
                       measured: pd.Series) -> dict:
    """For each LOAD UNKNOWN row: the utilities it reaches directly (on it, or a candidate) and through its state's
    factor. Through the factor: the frame counts the row as nothing in 2024; if any admissible history gives the state a
    different factor, every panel utility carrying permit-based load in that state is affected."""
    parsed = {c["fid"]: c for c in corrections if c["kind"] in ("date", "capacity_split")}
    unit_set = {(int(u), s) for u, s in units}
    out = {"sites": [], "utilities_directly": set(), "utilities_through_the_state_factor": set()}
    for fid in fac.index[fac.load_unknown.fillna(False).astype(bool)]:
        r = fac.loc[fid]
        st = r.state
        direct = {(int(u), st) for u in asg.candidates(r.utility_candidates)} | (
            {(int(r.utility_id_eia), st)} if pd.notna(r.utility_id_eia) else set())
        direct &= unit_set
        # The row's 2024 contribution across its admissible histories, against the frame's nothing.
        d = parsed.get(fid, {})
        starts = []
        if d.get("kind") == "date":
            lo = d.get("earliest") if d.get("earliest") is not None else px.OPEN_BELOW_START
            hi = d.get("latest") if d.get("latest") is not None else px.YEARS[-1] + 1
            starts = list(range(int(lo), int(hi) + 1)) + (["never"] if d.get("never_is_possible") else [])
        raw = float(r.mw_full_raw) if pd.notna(r.mw_full_raw) else 0.0
        a24 = sorted({0.0 if s == "never" else px.site_mw(("ramp", float(s)), raw, px.ANCHOR_YEAR) * 8.76 / 1000.0
                      for s in starts} | ({raw * 8.76 / 1000.0} if not starts else set()))
        through = set()
        if st in anchor.index and raw > 0 and not bool(measured.get(fid, False)):
            a = anchor.loc[st]
            f0 = float(a.factor)
            fs = {px._factor(float(a.epri_twh), float(a.epoch_twh), float(a.permit_twh) + x) for x in a24}
            if any(abs(f - f0) > px.FACTOR_TOL * max(1.0, abs(f0)) for f in fs):
                perm = fy[(fy.state == st) & ~fy.fid.map(measured).fillna(False).astype(bool)]
                through = {(int(u), s) for u, s in perm[["utility_id_eia", "state"]].drop_duplicates().values} & unit_set
        out["utilities_directly"] |= direct
        out["utilities_through_the_state_factor"] |= through
        out["sites"].append({"fid": fid, "state": st, "why": r.load_unknown_why,
                             "utilities_directly": sorted(f"{u}:{s}" for u, s in direct),
                             "state_factor_moves_across_its_histories": bool(through),
                             "its_2024_twh_across_admissible_histories": [round(x, 6) for x in a24]})
    key = lambda s: sorted(f"{u}:{st}" for u, st in s)  # noqa: E731
    return {"what_this_is": ("Rows whose start (or capacity) is unresolved carry NO single load history (Joe, R2, 2026-11-18). "
                             "Their load is UNKNOWN, not zero. Every utility listed here has its load share, dose, place and "
                             "comparison eligibility decided by the enumeration of admissible histories (timing.py) or carried "
                             "as unsettled; never by the inventory frame alone. Code that reads a share, a dose or eligibility "
                             "from the frame must refuse these utilities as settled."),
            "sites": out["sites"], "utilities_directly": key(out["utilities_directly"]),
            "utilities_through_the_state_factor": key(out["utilities_through_the_state_factor"]),
            "every_affected_utility": key(out["utilities_directly"] | out["utilities_through_the_state_factor"])}
