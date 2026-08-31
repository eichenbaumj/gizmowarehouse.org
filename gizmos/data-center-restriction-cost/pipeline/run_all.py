"""Orchestrate the data-center-restriction-cost pipeline and print a QA report.

Usage:
    python3 run_all.py            # full run: fetch, build, validate
    python3 run_all.py --check    # re-validate existing outputs, no refetch

Hard gates (exit non-zero):
  - Moratorium Nation data-center row count < 330
  - any action row with empty source_url or an invalid enum value
  - > 20% of local rows with geocode "none"
  - state_status missing any of the 51 state FIPS
  - outcomes tally mismatch, invalid outcome enum, a destination on a
    non-rerouted project, a rerouted project without destination coordinates,
    or a followup marker that is malformed (needs name + coords + its own
    sources), sits on an outcome other than died/pending_litigating, or
    coexists with a destination
DCT being unavailable is NOT a failure (documented fallback).
"""
from __future__ import annotations

import csv
import json
import sys

import config

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


class Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []
        self.failed = False

    def add(self, level: str, msg: str) -> None:
        self.lines.append((level, msg))
        if level == FAIL:
            self.failed = True

    def render(self) -> str:
        out = ["", "=" * 72, "QA REPORT — data-center-restriction-cost pipeline", "=" * 72]
        for level, msg in self.lines:
            out.append(f"[{level}] {msg}")
        out.append("=" * 72)
        out.append("RESULT: " + ("FAIL (hard gate tripped)" if self.failed else "GREEN"))
        out.append("=" * 72)
        return "\n".join(out)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(report: Report) -> None:
    # ---- MN row-count gate -------------------------------------------------
    if not config.MN_DC_ROWS_CSV.exists():
        report.add(FAIL, "raw/mn_dc_rows.csv missing — Moratorium Nation fetch did not run")
        return
    with open(config.MN_DC_ROWS_CSV, newline="", encoding="utf-8") as f:
        mn_count = sum(1 for _ in csv.DictReader(f))
    if mn_count < config.MN_DC_MIN_ROWS:
        report.add(FAIL, f"MN data-center rows {mn_count} < {config.MN_DC_MIN_ROWS}")
    elif mn_count > config.MN_DC_WARN_ROWS:
        report.add(WARN, f"MN data-center rows {mn_count} > {config.MN_DC_WARN_ROWS} "
                         f"(sector filter keeps multi-sector + pending rows; published "
                         f"since-2023 adoption count is {config.MN_PUBLISHED_DC_TOTAL})")
    else:
        report.add(PASS, f"MN data-center rows: {mn_count} (gate >= {config.MN_DC_MIN_ROWS})")

    # ---- DCT availability (informational) ---------------------------------
    if config.DCT_STATUS_JSON.exists():
        dct_status = json.loads(config.DCT_STATUS_JSON.read_text())
        if dct_status.get("dct_available"):
            report.add(PASS, f"DCT available: {dct_status.get('rows')} raw rows; "
                             f"spot-check sample at raw/{config.DCT_SPOTCHECK_CSV.name}")
        else:
            report.add(WARN, f"DCT unavailable (accepted fallback): {dct_status.get('error')}")
    else:
        report.add(WARN, "DCT status file missing (fetch skipped?)")

    # ---- actions.json ------------------------------------------------------
    if not config.ACTIONS_JSON.exists():
        report.add(FAIL, "actions.json missing")
        return
    doc = json.loads(config.ACTIONS_JSON.read_text())
    if doc.get("sample"):
        report.add(FAIL, "actions.json still carries the sample flag")
    if doc.get("snapshot_date") != config.SNAPSHOT_DATE:
        report.add(FAIL, f"actions.json snapshot_date {doc.get('snapshot_date')} != "
                         f"{config.SNAPSHOT_DATE}")

    actions = doc["actions"]
    ids = [a["id"] for a in actions]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        report.add(FAIL, f"duplicate action ids: {dupes[:8]}")

    enum_errors, url_errors = [], []
    for a in actions:
        if not (a.get("source_url") or "").strip():
            url_errors.append(a["id"])
        checks = [
            (a["level"], config.VALID_LEVELS, "level"),
            (a["class"], config.VALID_CLASSES, "class"),
            (a["status"], config.VALID_STATUSES, "status"),
            (a["action_type"], config.VALID_ACTION_TYPES, "action_type"),
            (a["jurisdiction_type"], config.VALID_JURISDICTION_TYPES, "jurisdiction_type"),
            (a["geocode"], config.VALID_GEOCODE, "geocode"),
        ]
        for value, valid, field in checks:
            if value not in valid:
                enum_errors.append(f"{a['id']}:{field}={value!r}")
    if url_errors:
        report.add(FAIL, f"{len(url_errors)} action rows with empty source_url "
                         f"(first: {url_errors[:5]})")
    else:
        report.add(PASS, f"all {len(actions)} action rows have a source_url")
    if enum_errors:
        report.add(FAIL, f"{len(enum_errors)} enum violations (first: {enum_errors[:5]})")
    else:
        report.add(PASS, "all enum fields valid across action rows")

    # ---- county friction layer gates ---------------------------------------
    local_all = [a for a in actions if a["level"] == "local"]
    if not config.COUNTIES_OUT_JSON.exists():
        report.add(FAIL, "counties.geojson missing — county assignment did not run")
    else:
        cdoc = json.loads(config.COUNTIES_OUT_JSON.read_text())
        feats = cdoc["features"]
        size = config.COUNTIES_OUT_JSON.stat().st_size
        if size > config.COUNTIES_MAX_BYTES:
            report.add(FAIL, f"counties.geojson {size} bytes > {config.COUNTIES_MAX_BYTES}")
        elif size > config.COUNTIES_WARN_BYTES:
            report.add(WARN, f"counties.geojson {size} bytes (warn > {config.COUNTIES_WARN_BYTES})")
        geoids = [f["properties"]["GEOID"] for f in feats]
        if len(geoids) != len(set(geoids)):
            report.add(FAIL, "duplicate GEOIDs in counties.geojson")
        bad_cat = [f["properties"]["GEOID"] for f in feats
                   if f["properties"]["category"] not in config.VALID_COUNTY_CATEGORIES]
        if bad_cat:
            report.add(FAIL, f"invalid county categories: {bad_cat[:5]}")
        # Recompute the default aggregation from actions.json and diff — the
        # anti-drift lock between rows, the emitted file, and the frontend twin.
        import county_assign as ca
        recomputed = ca.aggregate_counties(local_all)
        drift = []
        for f in feats:
            p = f["properties"]
            r = recomputed.get(p["GEOID"])
            if not r or r["category"] != p["category"] or sorted(r["action_ids"]) != sorted(p["action_ids"]):
                drift.append(p["GEOID"])
        if set(recomputed) != set(geoids):
            drift.append("feature-set-mismatch")
        if drift:
            report.add(FAIL, f"county aggregation drift vs actions.json: {drift[:6]}")
        row_ids = {a["id"] for a in local_all}
        orphan = [i for f in feats for i in f["properties"]["action_ids"] if i not in row_ids]
        if orphan:
            report.add(FAIL, f"counties.geojson references unknown action ids: {orphan[:5]}")
        cmisses = [a for a in local_all if not a.get("county_fips")]
        if len(cmisses) > config.COUNTY_ASSIGN_MISS_MAX:
            report.add(FAIL, f"{len(cmisses)} local rows without county_fips (gate {config.COUNTY_ASSIGN_MISS_MAX})")
        not_wide = [a["id"] for a in local_all
                    if a["jurisdiction_type"] == "county" and not a.get("county_wide")]
        if not_wide:
            report.add(FAIL, f"county-type rows not county_wide: {not_wide[:5]}")
        if not any(r.startswith("FAIL") for r in []):
            hist_c: dict[str, int] = {}
            for f in feats:
                hist_c[f["properties"]["category"]] = hist_c.get(f["properties"]["category"], 0) + 1
            report.add(PASS, f"counties: {len(feats)} features {hist_c}, {size} bytes, "
                             f"{len(cmisses)} unassigned rows "
                             f"({', '.join(a['id'] for a in cmisses) or 'none'})")

    # ---- geocode gate ------------------------------------------------------
    local = [a for a in actions if a["level"] == "local"]
    misses = [a for a in local if a["geocode"] == "none"]
    hist: dict[str, int] = {}
    for a in local:
        hist[a["geocode"]] = hist.get(a["geocode"], 0) + 1
    miss_share = (len(misses) / len(local)) if local else 0.0
    line = f"geocode over {len(local)} local rows: {hist} — miss rate {miss_share:.1%}"
    if miss_share > 0.20:
        report.add(FAIL, line + " (> 20% gate)")
    else:
        report.add(PASS, line)
    for a in misses[:20]:
        report.add(WARN, f"  geocode none: {a['id']} ({a['state']} {a['jurisdiction']})")
    coord_bad = [a["id"] for a in local
                 if a["geocode"] != "none" and (a["lat"] is None or a["lon"] is None)]
    if coord_bad:
        report.add(FAIL, f"local rows with provenance but missing coords: {coord_bad[:5]}")

    # ---- state_status coverage --------------------------------------------
    with open(config.US_STATES_GEOJSON, encoding="utf-8") as f:
        expected_fips = {ftr["properties"]["STATEFP"] for ftr in json.load(f)["features"]}
    got_fips = set(doc["state_status"].keys())
    if got_fips != expected_fips:
        report.add(FAIL, f"state_status FIPS mismatch: missing {sorted(expected_fips - got_fips)}, "
                         f"extra {sorted(got_fips - expected_fips)}")
    else:
        report.add(PASS, f"state_status covers all {len(expected_fips)} state FIPS")
    bad_status = [f for f, s in doc["state_status"].items()
                  if s["status"] not in config.VALID_STATE_STATUS
                  or s["tariff"] not in (None, "approved", "pending")]
    if bad_status:
        report.add(FAIL, f"invalid state_status values for FIPS {bad_status}")
    non_none = {f: s["status"] for f, s in doc["state_status"].items() if s["status"] != "none"}
    tariff_states = sorted(s["abbr"] for s in doc["state_status"].values() if s["tariff"])
    report.add(PASS, f"{len(non_none)} states with non-none status; "
                     f"tariff approved (curated rows): {tariff_states}")

    # sanity pins from the research corpus
    pins = {"23": "none", "36": "enacted_restriction", "54": "preemption",
            "39": "incentive_rollback", "48": "enacted_conditions", "51": "enacted_conditions"}
    for fips, want in pins.items():
        got = doc["state_status"][fips]["status"]
        if got != want:
            report.add(FAIL, f"state_status pin: FIPS {fips} expected {want}, got {got} "
                             f"(ME must stay 'none' — LD 307 was vetoed)")

    # ---- counts consistency ------------------------------------------------
    counts = doc["counts"]
    computed = {
        "local_documented": sum(1 for a in actions if a["level"] == "local"),
        "state_actions": sum(1 for a in actions if a["level"] == "state"),
        "tariff_rows_curated": sum(1 for a in actions if a["level"] == "puc"),
    }
    mismatch = {k: (counts.get(k), v) for k, v in computed.items() if counts.get(k) != v}
    if mismatch:
        report.add(FAIL, f"counts mismatch {mismatch}")
    else:
        report.add(PASS, f"counts: {computed} + EEI {counts['tariff_states_approved_eei']}/"
                         f"{counts['tariff_states_pending_eei']} ({counts['eei_vintage']}), "
                         f"MN published {counts['mn_dc_moratoria_published']}")

    # ---- dedup log ---------------------------------------------------------
    if config.BUILD_LOG_JSON.exists():
        blog = json.loads(config.BUILD_LOG_JSON.read_text())
        report.add(PASS, f"dedup pairs logged: {len(blog.get('dedup_pairs', []))}; "
                         f"MN ban recodes: {len(blog.get('mn_ban_recodes', []))}; "
                         f"DCT dropped by status: {len(blog.get('dct_dropped_status', []))}; "
                         f"DCT pre-2023 dropped: {len(blog.get('dct_dropped_pre2023', []))}")
        residual = blog.get("residual_same_family_pairs", [])
        level = WARN if len(residual) > 40 else PASS
        report.add(level, f"residual same-family cross-dataset pairs kept per 60-day rule: "
                          f"{len(residual)} (mostly expired moratoria plus later "
                          f"extensions/successors; listed in raw/build_actions_log.json)")

    # ---- assets CSV --------------------------------------------------------
    if not config.ASSETS_CSV.exists():
        report.add(FAIL, "assets CSV export missing")
    else:
        with open(config.ASSETS_CSV, encoding="utf-8") as f:
            first = f.readline()
            n_csv = sum(1 for _ in f) - 1  # minus header row
        ok = first.startswith("#") and config.SNAPSHOT_DATE in first and "CC-BY-4.0" in first \
            and "Moratorium Nation" in first
        if not ok:
            report.add(FAIL, "assets CSV header comment missing snapshot/license/attribution")
        elif n_csv != len(actions):
            report.add(FAIL, f"assets CSV rows {n_csv} != actions {len(actions)}")
        else:
            report.add(PASS, f"assets CSV: {n_csv} rows, attribution header present")

    # ---- outcomes ----------------------------------------------------------
    if not config.OUTCOMES_JSON.exists():
        report.add(FAIL, "outcomes.json missing")
    else:
        odoc = json.loads(config.OUTCOMES_JSON.read_text())
        projects = odoc["projects"]
        tally = {"died": 0, "rerouted": 0, "delayed_then_built": 0, "pending_litigating": 0}
        bad = []
        n_followup = 0
        far_followups = []
        for p in projects:
            if p["outcome"] not in config.VALID_OUTCOMES:
                bad.append(f"{p['id']}:outcome={p['outcome']}")
                continue
            tally[p["outcome"]] += 1
            dest = p.get("destination")
            fup = p.get("followup")
            # Relocation-marker implication gates: destination only on rerouted
            # rows; followup (soft tier) only on died/pending rows; never both.
            if dest is not None and p["outcome"] != "rerouted":
                bad.append(f"{p['id']}: destination on non-rerouted outcome {p['outcome']}")
            if p["outcome"] == "rerouted":
                if (dest or {}).get("lat") is None or (dest or {}).get("lon") is None:
                    bad.append(f"{p['id']}: rerouted without destination coords")
            if fup is not None:
                n_followup += 1
                if p["outcome"] not in ("died", "pending_litigating"):
                    bad.append(f"{p['id']}: followup on outcome {p['outcome']}")
                if dest is not None:
                    bad.append(f"{p['id']}: followup and destination on the same project")
                if not fup.get("name") or fup.get("lat") is None or fup.get("lon") is None:
                    bad.append(f"{p['id']}: followup missing name or coords")
                if not fup.get("sources"):
                    bad.append(f"{p['id']}: followup without its own sources")
                if fup.get("distance_mi") is None:
                    bad.append(f"{p['id']}: followup missing computed distance_mi")
                elif fup["distance_mi"] > 100:
                    far_followups.append(f"{p['id']}: {fup['distance_mi']} mi")
            if not p.get("sources"):
                bad.append(f"{p['id']}: no sources")
            if p.get("lat") is None or p.get("lon") is None:
                bad.append(f"{p['id']}: missing origin coords")
        if bad:
            report.add(FAIL, f"outcomes issues: {bad[:6]}")
        if far_followups:
            report.add(WARN, f"followup distance over 100 mi (check 'nearby' claim): {far_followups}")
        if tally != odoc["tally"]:
            report.add(FAIL, f"outcomes tally mismatch: stored {odoc['tally']} vs computed {tally}")
        elif not bad:
            report.add(PASS, f"outcomes: {len(projects)} projects, tally {tally}, "
                             f"{n_followup} followup marker(s), snapshot {odoc.get('snapshot_date')}, "
                             f"relocation-marker gates hold")

        # ---- assets outcomes CSV (public download) -------------------------
        if not config.OUTCOMES_ASSETS_CSV.exists():
            report.add(FAIL, "assets outcomes CSV export missing")
        else:
            with open(config.OUTCOMES_ASSETS_CSV, encoding="utf-8") as f:
                first = f.readline()
                n_csv = sum(1 for _ in f) - 1  # minus header row
            ok = first.startswith("#") and str(odoc.get("snapshot_date")) in first \
                and "CC-BY-4.0" in first and "joe@group17a.com" in first
            if not ok:
                report.add(FAIL, "assets outcomes CSV header missing snapshot/license/contact")
            elif n_csv != len(projects):
                report.add(FAIL, f"assets outcomes CSV rows {n_csv} != projects {len(projects)}")
            else:
                report.add(PASS, f"assets outcomes CSV: {n_csv} rows, attribution header present")

    # ---- benchmarks --------------------------------------------------------
    if not config.BENCHMARKS_JSON.exists():
        report.add(FAIL, "benchmarks.json missing")
    else:
        bdoc = json.loads(config.BENCHMARKS_JSON.read_text())
        regime_ids = [r["id"] for r in bdoc.get("regimes", [])]
        want = ["aggressive_abatement", "partial_abatement", "unabated_equipment_tax"]
        if regime_ids != want:
            report.add(FAIL, f"benchmarks regimes {regime_ids} != {want}")
        elif "haircut" in bdoc or bdoc.get("horizon_years") != 10:
            report.add(FAIL, "benchmarks haircut/horizon drifted from spec "
                             "(no haircut block since 2026-08-17; horizon 10 yr)")
        else:
            report.add(PASS, "benchmarks: 3 regimes, no counterfactual discount, horizon 10 yr, "
                             "reference campus Project Blue")


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    config.ensure_dirs()

    if not check_only:
        import build_actions
        import build_benchmarks
        import build_outcomes
        import fetch_datacentertracker
        import fetch_moratorium_nation

        print("[1/5] fetch Moratorium Nation")
        if fetch_moratorium_nation.main() != 0:
            print("FATAL: Moratorium Nation fetch failed — this layer is required.")
            return 1
        print("[2/5] fetch datacentertracker.org (non-fatal)")
        fetch_datacentertracker.main()
        print("[3/5] build actions")
        if build_actions.main() != 0:
            return 1
        print("[4/5] build outcomes")
        if build_outcomes.main() != 0:
            return 1
        print("[5/5] build benchmarks")
        if build_benchmarks.main() != 0:
            return 1
    else:
        print("--check: validating existing outputs (no refetch)")

    report = Report()
    validate(report)
    print(report.render())
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
