"""Build the blocked-project outcome layer.

Preferred input: raw/workflow_traced_projects.json — the adversarially
verified outcome trace produced by the parallel research workflow. When it is
present, pipeline/outcomes.csv is REGENERATED from it (flattened, sources as
semicolon-joined "name|url" pairs) and outcomes.json is emitted per the
frozen sample schema with the tally recomputed.

Fallback: if the trace file is absent, outcomes.csv (hand-seeded) is read and
outcomes.json is built from it.

Beyond the outcome enum, a project may carry ONE of two relocation markers:
- destination (rerouted rows only): the confirmed reroute site.
- followup (died / pending_litigating rows only): the softest tier — the same
  developer explicitly reported building or seeking a site nearby, not
  confirmed as the same project. Requires its own sources.
distance_mi on both markers is computed here (haversine, whole miles), never
hand-entered, and stays out of the CSVs so the CSV round-trips exactly.

The emitted snapshot_date is the TRACE's own snapshot_date (the date the
outcome research was current), falling back to config.SNAPSHOT_DATE only on
the hand-seeded-CSV path. The actions snapshot in config is a different date
and stays untouched by this builder.

A public copy of the flat CSV is written to public/assets/ with an
attribution header so the piece's "sources in the download" claim is backed
by a real download.
"""
from __future__ import annotations

import csv
import json
import math
import sys

import config

CSV_COMMENT = "# regenerated from workflow trace when available\n"
CSV_FIELDS = [
    "id", "name", "developer", "jurisdiction", "state", "lat", "lon",
    "claimed_capex_usd_b", "capex_label", "mw", "decision_date", "outcome",
    "destination_name", "destination_lat", "destination_lon",
    "destination_same_metro", "followup_name", "followup_lat", "followup_lon",
    "followup_same_metro", "followup_note", "followup_sources",
    "months_lost", "confidence", "note", "sources",
]


def _safe_name(name: str) -> str:
    """The flat sources column is semicolon-joined "name|url" pairs, so the
    delimiters must not appear inside a name (found in the wild: a source
    name containing '; moratorium'). Commas/slashes read fine in a CSV."""
    return (name or "").replace(";", ",").replace("|", "/")


def _safe_url(url: str) -> str:
    if ";" in (url or "") or "|" in (url or ""):
        raise ValueError(f"source url contains a reserved delimiter: {url}")
    return url or ""


def _flatten_sources(sources: list[dict]) -> str:
    return ";".join(f"{_safe_name(s['name'])}|{_safe_url(s['url'])}" for s in sources or [])


def _parse_sources(flat: str) -> list[dict]:
    return [
        {"name": pair.split("|", 1)[0], "url": pair.split("|", 1)[1]}
        for pair in (flat or "").split(";") if "|" in pair
    ]


def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    rad = math.pi / 180
    a = (math.sin((lat2 - lat1) * rad / 2) ** 2
         + math.cos(lat1 * rad) * math.cos(lat2 * rad)
         * math.sin((lon2 - lon1) * rad / 2) ** 2)
    return round(2 * 3958.8 * math.asin(math.sqrt(a)))


def _capex_label(project: dict):
    if project.get("claimed_capex_usd_b") is None:
        return None
    if "capex_label" in project and project["capex_label"]:
        return project["capex_label"]
    note = (project.get("note") or "").lower()
    if "county finance office" in note:
        return "county-estimate"
    return "developer-announced"


def _load_trace() -> tuple[str | None, list[dict]]:
    doc = json.loads(config.WORKFLOW_TRACE_JSON.read_text())
    projects = []
    for p in doc["projects"]:
        projects.append({
            "id": p["id"],
            "name": p["name"],
            "developer": p["developer"],
            "jurisdiction": p["jurisdiction"],
            "state": p["state"],
            "lat": p["lat"],
            "lon": p["lon"],
            "claimed_capex_usd_b": p["claimed_capex_usd_b"],
            "capex_label": _capex_label(p),
            "mw": p["mw"],
            "decision_date": p["decision_date"],
            "outcome": p["outcome"],
            "destination": p["destination"],
            "followup": p.get("followup"),
            "months_lost": p["months_lost"],
            "confidence": p["confidence"],
            "note": p["note"],
            "sources": p["sources"],
        })
    return doc.get("snapshot_date"), projects


def _projects_from_csv() -> list[dict]:
    projects = []
    with open(config.OUTCOMES_CSV, newline="", encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.startswith("#")]
    for row in csv.DictReader(lines):
        def num(key, cast=float):
            val = (row.get(key) or "").strip()
            return cast(val) if val else None
        destination = None
        if (row.get("destination_name") or "").strip():
            destination = {
                "name": row["destination_name"].strip(),
                "lat": num("destination_lat"),
                "lon": num("destination_lon"),
                "same_metro": (row.get("destination_same_metro") or "").strip().lower() == "true",
            }
        followup = None
        if (row.get("followup_name") or "").strip():
            followup = {
                "name": row["followup_name"].strip(),
                "lat": num("followup_lat"),
                "lon": num("followup_lon"),
                "same_metro": (row.get("followup_same_metro") or "").strip().lower() == "true",
                "note": (row.get("followup_note") or "").strip(),
                "sources": _parse_sources(row.get("followup_sources") or ""),
            }
        projects.append({
            "id": row["id"], "name": row["name"], "developer": row["developer"],
            "jurisdiction": row["jurisdiction"], "state": row["state"],
            "lat": num("lat"), "lon": num("lon"),
            "claimed_capex_usd_b": num("claimed_capex_usd_b"),
            "capex_label": (row.get("capex_label") or "").strip() or None,
            "mw": num("mw"),
            "decision_date": (row.get("decision_date") or "").strip() or None,
            "outcome": row["outcome"].strip(),
            "destination": destination,
            "followup": followup,
            "months_lost": num("months_lost"),
            "confidence": row["confidence"].strip(),
            "note": row["note"].strip(),
            "sources": _parse_sources(row.get("sources") or ""),
        })
    return projects


def _stamp_distances(projects: list[dict]) -> None:
    """Compute distance_mi into destination/followup on every load path, so
    the value is always derived from coordinates and never hand-entered."""
    for p in projects:
        for marker in ("destination", "followup"):
            m = p.get(marker)
            if m and m.get("lat") is not None and m.get("lon") is not None \
                    and p.get("lat") is not None and p.get("lon") is not None:
                m["distance_mi"] = _haversine_mi(p["lat"], p["lon"], m["lat"], m["lon"])


def _write_csv(projects: list[dict], path, header: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(header)
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for p in projects:
            dest = p.get("destination") or {}
            fup = p.get("followup") or {}
            writer.writerow({
                "id": p["id"], "name": p["name"], "developer": p["developer"],
                "jurisdiction": p["jurisdiction"], "state": p["state"],
                "lat": p["lat"], "lon": p["lon"],
                "claimed_capex_usd_b": "" if p["claimed_capex_usd_b"] is None else p["claimed_capex_usd_b"],
                "capex_label": p["capex_label"] or "",
                "mw": "" if p["mw"] is None else p["mw"],
                "decision_date": p["decision_date"] or "",
                "outcome": p["outcome"],
                "destination_name": dest.get("name", ""),
                "destination_lat": "" if dest.get("lat") is None else dest.get("lat"),
                "destination_lon": "" if dest.get("lon") is None else dest.get("lon"),
                "destination_same_metro": "" if not dest else str(dest.get("same_metro", "")).lower(),
                "followup_name": fup.get("name", ""),
                "followup_lat": "" if fup.get("lat") is None else fup.get("lat"),
                "followup_lon": "" if fup.get("lon") is None else fup.get("lon"),
                "followup_same_metro": "" if not fup else str(fup.get("same_metro", "")).lower(),
                "followup_note": fup.get("note", ""),
                "followup_sources": _flatten_sources(fup.get("sources") or []),
                "months_lost": "" if p["months_lost"] is None else p["months_lost"],
                "confidence": p["confidence"],
                "note": p["note"],
                "sources": _flatten_sources(p["sources"]),
            })


def main() -> int:
    config.ensure_dirs()
    trace_snapshot = None
    if config.WORKFLOW_TRACE_JSON.exists():
        trace_snapshot, projects = _load_trace()
        origin = f"workflow trace ({config.WORKFLOW_TRACE_JSON.name})"
    elif config.OUTCOMES_CSV.exists():
        projects = _projects_from_csv()
        origin = "hand-seeded outcomes.csv (workflow trace not present)"
    else:
        print("  [outcomes] FATAL: neither workflow trace nor outcomes.csv exists")
        return 1

    _stamp_distances(projects)
    if trace_snapshot is not None:
        _write_csv(projects, config.OUTCOMES_CSV, CSV_COMMENT)

    snapshot = trace_snapshot or config.SNAPSHOT_DATE
    assets_header = (
        f"# Blocked data-center project outcome trace — snapshot {snapshot}. "
        f"License CC-BY-4.0. Compiled from local press and government records, "
        f"one or more sources per project (sources column, name|url pairs joined "
        f"by semicolons). followup_* columns mark the softest tier: same "
        f"developer, nearby build, not confirmed as the same project. "
        f"Corrections: joe@group17a.com. Documented statuses, not a census.\n"
    )
    _write_csv(projects, config.OUTCOMES_ASSETS_CSV, assets_header)

    tally = {"died": 0, "rerouted": 0, "delayed_then_built": 0, "pending_litigating": 0}
    for p in projects:
        tally[p["outcome"]] += 1
    n_followup = sum(1 for p in projects if p.get("followup"))

    payload = {
        "snapshot_date": snapshot,
        "tally": tally,
        "projects": projects,
    }
    config.OUTCOMES_JSON.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(f"  [outcomes] {len(projects)} projects from {origin}; tally {tally}; "
          f"{n_followup} followup marker(s)")
    print(f"  [outcomes] wrote {config.OUTCOMES_JSON}, regenerated {config.OUTCOMES_CSV.name}, "
          f"and exported {config.OUTCOMES_ASSETS_CSV.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
