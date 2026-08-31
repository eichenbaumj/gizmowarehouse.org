"""Merge the four action layers into the frozen actions.json schema and the
flat CSV export.

Layers:
  1. Moratorium Nation data-center rows        (dataset "moratorium_nation", level local)
  2. datacentertracker.org local formal actions (dataset "datacentertracker", level local)
     - included only when fetch_datacentertracker succeeded
     - deduped against MN (same jurisdiction+state, same action family,
       within 60 days -> keep MN, log the pair)
  3. state_actions.csv                          (dataset "curated_state", level state)
  4. tariff_layer.csv                           (dataset "curated_tariff", level puc)

Also derives state_status for all 51 states and writes:
  public/data/data-center-restriction-cost/actions.json
  public/assets/data-center-restriction-cost-actions.csv
  raw/build_actions_log.json   (dedup pairs, drops, recodes, geocode misses)
"""
from __future__ import annotations

import csv
import datetime
import json
import re
import sys

import config
import county_assign
import build_footprint
import geocode as geomod

# ---------------------------------------------------------------------------
# Mappings
# ---------------------------------------------------------------------------
MN_STATUS_MAP = {
    "active": "in_force",
    "extended": "in_force",
    "pending": "pending",
    "expired": "expired",
    "rescinded": "expired",   # lapsed with nothing in its place; disposition in summary
    "replaced": "replaced",   # superseded by a successor instrument (usually still restricts)
}

MN_JT_MAP = {
    "County": "county",
    "Parish": "county",
    "City": "municipality",
    "Town": "municipality",
    "Village": "municipality",
    "Township": "municipality",
    "Other": "municipality",
    "Tribal": "tribal",
    "Utility-authority": "utility",
}

# DCT: only formal local-government action types enter the map.
DCT_TYPE_PRIORITY = [
    ("moratorium", "moratorium", "restriction", "pause"),
    ("zoning_restriction", "zoning_exclusion", "restriction", "zoning"),
    ("permit_denial", "project_rejection", "restriction", "rejection"),
    ("ordinance", "ordinance_conditions", "condition", "ordinance"),
]
DCT_STATUS_MAP = {
    "active": "in_force",
    "passed": "enacted",
    "approved": "enacted",
    "signed": "enacted",
    "moratorium passed": "enacted",
    "moratorium enacted": "enacted",
    "moratorium adopted": "enacted",
    "passed (first hearing)": "enacted",
    "passed (nonbinding)": "enacted",
    "expired": "expired",
    "pending": "pending",
    "filed": "pending",
    "proposed": "pending",
    "hearing": "pending",
    "drafted": "pending",
    "first_reading": "pending",
    "second_reading": "pending",
    "announced": "pending",
}
DCT_AUTHORITY_JT = {
    "county_commission": "county",
    "city_council": "municipality",
    "village_board": "municipality",
    "township_board": "municipality",
    "planning_commission": "municipality",
    "tribal_government": "tribal",
}
DCT_MIN_DATE = "2023-01-01"   # crypto-era pre-2023 rows are out of scope

TARIFF_ID_SLUG = {
    "AEP Ohio": "aep",
    "Indiana Michigan Power": "im",
    "Georgia Power (PSC rule)": "psc-rule",
    "Dominion Energy (GS-5)": "dominion-gs5",
    "Portland General Electric (Schedule 96)": "pge-sch96",
    "Evergy": "evergy",
    "Consumers Energy": "consumers",
    "El Paso Electric": "epe",
}

_BAN_RE = re.compile(r"\bban\b|\bprohibit", re.I)
_MW_RE = re.compile(
    r"(?:above|over|exceeding|at or above|at least|>=|>|≥)\s*(\d+(?:\.\d+)?)\s*(?:MW|megawatt)"
    r"|(\d+(?:\.\d+)?)\s*MW\s*(?:\+|or more|and up|and larger|or greater|or above)",
    re.I,
)


def _clip(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _parse_mw_threshold(*fields) -> float | None:
    for field in fields:
        match = _MW_RE.search(field or "")
        if match:
            val = float(match.group(1) or match.group(2))
            if 0 < val <= 1000:
                return int(val) if val == int(val) else val
    return None


def _load_states():
    with open(config.US_STATES_GEOJSON, encoding="utf-8") as f:
        gj = json.load(f)
    abbr_to_fips, abbr_to_name = {}, {}
    for feature in gj["features"]:
        props = feature["properties"]
        abbr_to_fips[props["STUSPS"]] = props["STATEFP"]
        abbr_to_name[props["STUSPS"]] = props["NAME"]
    return abbr_to_fips, abbr_to_name


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------
def build_mn_actions(geocoder, abbr_to_fips, log):
    actions = []
    with open(config.MN_DC_ROWS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        jt_raw = row["jurisdiction_type"]
        state = row["state_abbrev"].strip().upper()
        if jt_raw == "Aggregate meta-row":
            log["mn_skipped"].append({"id": row["moratorium_id"], "why": "aggregate meta-row"})
            continue
        if jt_raw == "State":
            # Statewide instruments are hand-curated; the one MN state row is
            # NY EO 62, which duplicates curated ny-eo62-2026.
            log["dedup_pairs"].append({
                "kept": "ny-eo62-2026" if state == "NY" else f"curated:{state}",
                "dropped": f"mn:{row['moratorium_id']}",
                "why": "statewide instrument carried in the curated state layer",
            })
            continue
        if state not in abbr_to_fips:
            log["mn_skipped"].append({"id": row["moratorium_id"], "why": f"unmapped state {state}"})
            continue

        enacted_status = (row.get("enacted_status") or "").strip().lower()
        status = MN_STATUS_MAP.get(enacted_status)
        if status is None:
            log["mn_skipped"].append({"id": row["moratorium_id"],
                                      "why": f"unmapped enacted_status {enacted_status!r}"})
            continue

        text_blob = " ".join([row.get("legal_basis", ""), row.get("trigger", "")])
        action_type = "moratorium"
        if row.get("duration_kind") == "indefinite" and _BAN_RE.search(text_blob):
            action_type = "ban"
            log["mn_ban_recodes"].append(row["moratorium_id"])

        jur = row["jurisdiction"].strip()
        if jt_raw in ("City", "Town", "Village"):
            clean = re.sub(r"^(city|town|village) of\s+", "", jur, flags=re.I)
            display = f"{clean} ({jt_raw.lower()})"
        else:
            display = jur

        # Summary: duration + adoption date + disposition, no invented facts.
        days = (row.get("duration_days") or "").strip()
        if days:
            base = f"{int(float(days))}-day data-center moratorium"
        elif action_type == "ban":
            base = "Indefinite prohibition on data centers"
        elif row.get("duration_kind") == "until_date":
            base = "Data-center moratorium running to a set end date"
        else:
            base = "Data-center moratorium"
        date_iso = (row.get("date_enacted_iso") or "").strip() or None
        parts = [base]
        if date_iso:
            parts.append(f"adopted {date_iso}")
        disposition = {
            "active": "active per tracker",
            "extended": "extended and active per tracker",
            "pending": "adoption pending or unconfirmed",
            "expired": "since expired",
            "rescinded": "since rescinded",
            "replaced": "since replaced by permanent regulations",
        }[enacted_status]
        parts.append(disposition)
        summary = ", ".join(parts) + " (Moratorium Nation)"

        native = (row.get("latitude") or None, row.get("longitude") or None)
        lat, lon, prov = geocoder.resolve(state, jur, MN_JT_MAP.get(jt_raw, "municipality"),
                                          native=native)

        actions.append({
            "id": row["moratorium_id"] or f"mn-{state.lower()}-{geomod.norm_place(jur).replace(' ', '-')}",
            "level": "local",
            "state_fips": abbr_to_fips[state],
            "state": state,
            "jurisdiction": display,
            "jurisdiction_type": MN_JT_MAP.get(jt_raw, "municipality"),
            "action_type": action_type,
            "class": "restriction",
            "status": status,
            "date": date_iso,
            "mw_threshold": _parse_mw_threshold(row.get("affected_projects"),
                                                row.get("legal_basis"), row.get("trigger")),
            "lat": lat,
            "lon": lon,
            "geocode": prov,
            "summary": summary,
            "source_url": config.MN_SITE_BASE,
            "source_name": config.MN_SOURCE_NAME,
            "dataset": "moratorium_nation",
        })
    return actions


def _dct_pick_type(action_types):
    for raw, mapped, klass, family in DCT_TYPE_PRIORITY:
        if raw in action_types:
            return mapped, klass, family
    return None, None, None


def build_dct_actions(geocoder, abbr_to_fips, mn_actions, log):
    if not config.DCT_STATUS_JSON.exists():
        log["dct_note"] = "dct_status.json missing; DCT layer skipped"
        return []
    status_doc = json.loads(config.DCT_STATUS_JSON.read_text())
    if not status_doc.get("dct_available"):
        log["dct_note"] = f"DCT unavailable: {status_doc.get('error')}"
        return []
    data = json.loads(config.DCT_RAW_JSON.read_text())

    # Manual spot-check corrections (dct_overrides.json): excluded rows never
    # enter the dataset; patched rows get field-level fixes. Every application
    # is logged so the build log shows what human review changed.
    overrides_path = config.PIPELINE_DIR / "dct_overrides.json"
    overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    log.setdefault("dct_overridden", [])

    # MN index for dedup: (state, normalized jurisdiction) -> [dates] (pause family only)
    mn_index = {}
    for act in mn_actions:
        key = (act["state"], geomod.norm_place(act["jurisdiction"]))
        mn_index.setdefault(key, []).append((act["date"], act["id"]))

    def within_60_days(d1, d2):
        if not d1 or not d2:
            return True  # conservative: missing dates count as a match
        try:
            a = datetime.date.fromisoformat(d1[:10])
            b = datetime.date.fromisoformat(d2[:10])
        except ValueError:
            return True
        return abs((a - b).days) <= 60

    actions = []
    counters = {"non_local": 0, "no_formal_type": 0, "pre_2023": 0}
    for row in data:
        if row.get("scope") != "local":
            counters["non_local"] += 1
            continue
        mapped_type, klass, family = _dct_pick_type(row.get("action_type") or [])
        if mapped_type is None:
            counters["no_formal_type"] += 1
            continue
        date = (row.get("date") or "").strip() or None
        if date and date < DCT_MIN_DATE:
            counters["pre_2023"] += 1
            log["dct_dropped_pre2023"].append(row["id"])
            continue
        raw_status = (row.get("status") or "").strip().lower()
        if mapped_type == "project_rejection" and raw_status in ("denied", "passed", "approved"):
            status = "enacted"
        else:
            status = DCT_STATUS_MAP.get(raw_status)
        if status is None:
            log["dct_dropped_status"].append({"id": row["id"], "status": raw_status})
            continue
        state = (row.get("state") or "").strip().upper()
        if state not in abbr_to_fips:
            log["dct_dropped_status"].append({"id": row["id"], "status": f"unmapped state {state}"})
            continue

        # dedup vs MN (pause family only — MN tracks moratoria/bans)
        if family == "pause":
            key = (state, geomod.norm_place(row.get("jurisdiction") or ""))
            hits = mn_index.get(key, [])
            match = next((mn_id for mn_date, mn_id in hits if within_60_days(mn_date, date)), None)
            if match:
                log["dedup_pairs"].append({
                    "kept": f"mn:{match}", "dropped": f"dct:{row['id']}",
                    "why": "same jurisdiction+state, pause family, within 60 days (or undated)",
                })
                continue

        jur = (row.get("jurisdiction") or "").strip()
        jt = DCT_AUTHORITY_JT.get(row.get("authority_level") or "")
        if jt is None:
            low = jur.lower()
            if re.search(r"\b(county|parish)$", low):
                jt = "county"
            elif re.search(r"\b(pud|utility|utilities|power district)\b", low):
                jt = "utility"
            else:
                jt = "municipality"

        native = (row.get("lat"), row.get("lng"))
        lat, lon, prov = geocoder.resolve(state, jur, jt, county_hint=row.get("county") or "",
                                          native=native)

        sources = [s for s in (row.get("sources") or []) if isinstance(s, str) and s.startswith("http")]
        summary = _clip(row.get("summary") or f"{mapped_type} action") + " (datacentertracker.org)"

        act_id = f"dct-{row['id']}"
        if act_id in overrides.get("exclude", {}):
            log["dct_overridden"].append({"id": act_id, "applied": "excluded",
                                          "why": overrides["exclude"][act_id]})
            continue

        actions.append({
            "id": f"dct-{row['id']}",
            "level": "local",
            "state_fips": abbr_to_fips[state],
            "state": state,
            "jurisdiction": jur,
            "jurisdiction_type": jt,
            "action_type": mapped_type,
            "class": klass,
            "status": status,
            "date": date,
            "mw_threshold": None,  # DCT's megawatts field is project size, not a threshold
            "lat": lat,
            "lon": lon,
            "geocode": prov,
            "summary": summary,
            "source_url": sources[0] if sources else config.DCT_HOME_URL,
            "source_name": config.DCT_SOURCE_NAME,
            "dataset": "datacentertracker",
        })
        patch = overrides.get("patch", {}).get(act_id)
        if patch:
            fields = [k for k in patch if not k.startswith("_")]
            for k in fields:
                actions[-1][k] = patch[k]
            log["dct_overridden"].append({"id": act_id, "applied": "patched",
                                          "fields": fields, "why": patch.get("_reason", "")})
    log["dct_filter_counters"] = counters
    return actions


def build_state_actions(abbr_to_fips, abbr_to_name, log):
    actions = []
    with open(config.STATE_ACTIONS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            state = row["state"].strip().upper()
            mw = row["mw_threshold"].strip()
            actions.append({
                "id": row["action_id"].strip(),
                "level": "state",
                "state_fips": abbr_to_fips[state],
                "state": state,
                "jurisdiction": f"{abbr_to_name[state]} (statewide)",
                "jurisdiction_type": "state",
                "action_type": row["action_type"].strip(),
                "class": row["class"].strip(),
                "status": row["status"].strip(),
                "date": row["date"].strip() or None,
                "mw_threshold": float(mw) if mw and "." in mw else (int(mw) if mw else None),
                "lat": None,
                "lon": None,
                "geocode": "none",
                "summary": row["summary"].strip(),
                "source_url": row["source_url"].strip(),
                "source_name": row["source_name"].strip(),
                "dataset": "curated_state",
                "note": f"Instrument: {row['instrument'].strip()}",
            })
    return actions


def build_tariff_actions(abbr_to_fips, log):
    actions = []
    with open(config.TARIFF_LAYER_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            state = row["state"].strip().upper()
            utility = row["utility"].strip()
            date = row["date"].strip() or None
            year = date[:4] if date else "eei"
            slug = TARIFF_ID_SLUG.get(utility) or re.sub(r"[^a-z0-9]+", "-", utility.lower()).strip("-")
            mw = row["threshold_mw"].strip()
            note_bits = []
            if row["docket"].strip():
                note_bits.append(f"Docket {row['docket'].strip()}")
            if row["min_take_pct"].strip():
                note_bits.append(f"minimum take {row['min_take_pct'].strip()}%")
            if row["term_years"].strip():
                note_bits.append(f"term {row['term_years'].strip()} yr")
            actions.append({
                "id": f"{state.lower()}-{slug}-tariff-{year}",
                "level": "puc",
                "state_fips": abbr_to_fips[state],
                "state": state,
                "jurisdiction": f"{utility} territory",
                "jurisdiction_type": "utility",
                "action_type": "large_load_tariff",
                "class": "condition",
                "status": row["status"].strip(),
                "date": date,
                "mw_threshold": int(mw) if mw else None,
                "lat": None,
                "lon": None,
                "geocode": "none",
                "summary": row["summary"].strip(),
                "source_url": row["source_url"].strip(),
                "source_name": row["source_name"].strip(),
                "dataset": "curated_tariff",
                "note": "; ".join(note_bits) if note_bits else None,
            })
    return actions


# ---------------------------------------------------------------------------
# state_status derivation
# ---------------------------------------------------------------------------
ACTIVE_STATUSES = {"enacted", "in_force"}


def derive_state_status(all_actions, abbr_to_fips, abbr_to_name):
    per_state = {}
    for abbr, fips in abbr_to_fips.items():
        state_rows = [a for a in all_actions if a["state"] == abbr and a["level"] == "state"]
        has = {
            "restriction": any(a["class"] == "restriction" and a["status"] in ACTIVE_STATUSES
                               for a in state_rows),
            "conditions": any(a["class"] == "condition" and a["status"] in ACTIVE_STATUSES
                              and a["action_type"] != "incentive_rollback" for a in state_rows),
            "rollback": any(a["action_type"] == "incentive_rollback"
                            and a["status"] in ACTIVE_STATUSES for a in state_rows),
            "preemption": any(a["class"] == "preemption" and a["status"] in ACTIVE_STATUSES
                              for a in state_rows),
        }
        if has["restriction"]:
            status = "enacted_restriction"
        elif has["conditions"]:
            status = "enacted_conditions"
        elif has["rollback"]:
            status = "incentive_rollback"
        elif has["preemption"]:
            status = "preemption"
        else:
            status = "none"
        tariff = "approved" if any(a["level"] == "puc" and a["state"] == abbr
                                   for a in all_actions) else None
        action_ids = [a["id"] for a in sorted(
            (a for a in all_actions if a["state"] == abbr and a["level"] in ("state", "puc")),
            key=lambda a: (a["date"] or "9999", a["id"]))]
        per_state[fips] = {
            "abbr": abbr,
            "name": abbr_to_name[abbr],
            "status": status,
            "tariff": tariff,
            "action_ids": action_ids,
        }
    return dict(sorted(per_state.items()))


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
def write_actions_json(all_actions, state_status, dct_used, footprint=None):
    sources = [
        {
            "id": "moratorium_nation",
            "name": config.MN_SOURCE_NAME,
            "url": config.MN_SITE_BASE,
            "license": config.MN_LICENSE,
            "retrieved": config.SNAPSHOT_DATE,
            "note": "Local moratorium instruments, primary-document-backed; data-center rows only",
        },
        {
            "id": "curated_state",
            "name": "Hand-curated state actions (17A research corpus)",
            "url": "",
            "license": "CC-BY-4.0",
            "retrieved": config.SNAPSHOT_DATE,
            "note": "Enacted state laws, EOs, and vetoes, each with a primary or near-primary citation",
        },
        {
            "id": "curated_tariff",
            "name": "Hand-curated PUC large-load tariff layer",
            "url": "",
            "license": "CC-BY-4.0",
            "retrieved": config.SNAPSHOT_DATE,
            "note": "Commission-approved tariffs with docket numbers; counts attributed to EEI tracker",
        },
    ]
    if dct_used:
        sources.insert(1, {
            "id": "datacentertracker",
            "name": config.DCT_SOURCE_NAME,
            "url": config.DCT_HOME_URL,
            "license": config.DCT_LICENSE,
            "retrieved": config.SNAPSHOT_DATE,
            "note": "AI-assembled local-action tracker; formal local government actions only, "
                    "deduped against Moratorium Nation; pending manual spot-check "
                    "(raw/dct-spotcheck-sample.csv)",
        })

    counts = {
        "local_documented": sum(1 for a in all_actions if a["level"] == "local"),
        "state_actions": sum(1 for a in all_actions if a["level"] == "state"),
        "tariff_rows_curated": sum(1 for a in all_actions if a["level"] == "puc"),
        "tariff_states_approved_eei": config.EEI_TARIFF_APPROVED,
        "tariff_states_pending_eei": config.EEI_TARIFF_PENDING,
        "eei_vintage": config.EEI_VINTAGE,
        "mn_dc_moratoria_published": config.MN_PUBLISHED_DC_TOTAL,
    }

    if footprint:
        sources.append({
            "id": "epri_footprint",
            "name": footprint["source"],
            "url": footprint["source_url"],
            "license": "EPRI public dashboard data (attributed)",
            "retrieved": config.SNAPSHOT_DATE,
            "note": "Per-state data center electricity use, 2024 historical + 2030 medium scenario",
        })
    payload = {
        "snapshot_date": config.SNAPSHOT_DATE,
        "sources": sources,
        "counts": counts,
        "state_status": state_status,
        "footprint": footprint,
        "actions": all_actions,
    }
    config.ACTIONS_JSON.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    return counts


CSV_FIELDS = [
    "id", "dataset", "level", "state", "state_fips", "jurisdiction",
    "jurisdiction_type", "action_type", "class", "status", "date",
    "mw_threshold", "lat", "lon", "geocode", "county_fips", "county_name",
    "county_wide", "summary", "source_name", "source_url", "note",
]


def write_assets_csv(all_actions):
    header_comment = (
        f"# Data-center restriction & condition actions — snapshot {config.SNAPSHOT_DATE}. "
        f"License CC-BY-4.0. Includes data from Moratorium Nation (ALEA Institute, "
        f"https://mjbommar.github.io/moratorium-data-2026/, CC-BY-4.0) and "
        f"datacentertracker.org (CC BY 4.0). Documented actions, not a census.\n"
    )
    with open(config.ASSETS_CSV, "w", newline="", encoding="utf-8") as f:
        f.write(header_comment)
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for act in all_actions:
            writer.writerow({k: ("" if act.get(k) is None else act.get(k)) for k in CSV_FIELDS})


def main() -> int:
    config.ensure_dirs()
    log = {
        "dedup_pairs": [], "mn_skipped": [], "mn_ban_recodes": [],
        "dct_dropped_status": [], "dct_dropped_pre2023": [],
    }
    abbr_to_fips, abbr_to_name = _load_states()
    geocoder = geomod.Geocoder()

    mn_actions = build_mn_actions(geocoder, abbr_to_fips, log)
    dct_actions = build_dct_actions(geocoder, abbr_to_fips, mn_actions, log)
    state_actions = build_state_actions(abbr_to_fips, abbr_to_name, log)
    tariff_actions = build_tariff_actions(abbr_to_fips, log)

    all_actions = (
        sorted(state_actions, key=lambda a: (a["state"], a["date"] or "9999"))
        + sorted(tariff_actions, key=lambda a: (a["state"], a["id"]))
        + sorted(mn_actions + dct_actions, key=lambda a: (a["state"], a["jurisdiction"], a["id"]))
    )

    # County assignment + aggregation for the map's county friction layer.
    local = [a for a in all_actions if a["level"] == "local"]
    county_feats = county_assign.load_county_features()
    county_assign.assign_counties(local, county_feats, log)
    county_summaries = county_assign.aggregate_counties(local)
    n_county_features = county_assign.write_counties_geojson(county_summaries)
    log["county_category_histogram"] = {}
    for s in county_summaries.values():
        log["county_category_histogram"][s["category"]] = \
            log["county_category_histogram"].get(s["category"], 0) + 1

    # geocode miss accounting (local rows only; rows are reported, never dropped)
    log["geocode_histogram"] = {}
    for act in local:
        log["geocode_histogram"][act["geocode"]] = log["geocode_histogram"].get(act["geocode"], 0) + 1
    log["geocode_misses"] = [
        {"id": a["id"], "state": a["state"], "jurisdiction": a["jurisdiction"]}
        for a in local if a["geocode"] == "none"
    ]

    # Residual same-jurisdiction, same-family pairs across datasets whose dates
    # sit MORE than 60 days apart (kept per the dedup rule — typically an
    # expired moratorium plus its later extension or permanent successor).
    family = {"moratorium": "pause", "ban": "pause", "zoning_exclusion": "zoning",
              "ordinance_conditions": "ordinance", "project_rejection": "rejection"}
    residual_index: dict = {}
    for a in local:
        key = (a["state"], geomod.norm_place(a["jurisdiction"]), family[a["action_type"]])
        residual_index.setdefault(key, []).append(a)
    log["residual_same_family_pairs"] = [
        {"key": list(key), "ids": [(x["id"], x["date"], x["status"]) for x in group]}
        for key, group in residual_index.items()
        if len(group) > 1 and len({x["dataset"] for x in group}) > 1
    ]

    state_status = derive_state_status(all_actions, abbr_to_fips, abbr_to_name)
    footprint, fp_err = build_footprint.build_footprint(abbr_to_fips)
    if fp_err:
        print(f"  [footprint] WARN: {fp_err}")
        log["footprint_warning"] = fp_err
    counts = write_actions_json(all_actions, state_status, dct_used=bool(dct_actions), footprint=footprint)
    write_assets_csv(all_actions)
    config.BUILD_LOG_JSON.write_text(json.dumps(log, indent=1) + "\n")

    print(f"  [actions] {counts['local_documented']} local ({len(mn_actions)} MN + "
          f"{len(dct_actions)} DCT after dedup), {counts['state_actions']} state, "
          f"{counts['tariff_rows_curated']} tariff rows")
    print(f"  [actions] dedup pairs: {len(log['dedup_pairs'])}; "
          f"geocode: {log['geocode_histogram']}")
    print(f"  [actions] counties: {n_county_features} features, "
          f"categories {log['county_category_histogram']}, "
          f"misses {len(log['county_assign_misses'])}, "
          f"nearest-boundary {len(log['county_assign_nearest'])}, "
          f"county-wide promotions {len(log['county_wide_promotions'])}")
    print(f"  [actions] wrote {config.ACTIONS_JSON} and {config.ASSETS_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
