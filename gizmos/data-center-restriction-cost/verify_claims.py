#!/usr/bin/env python3
"""Verify gate for the data-center-restriction-cost gizmo.

Locks three surfaces to each other so they cannot drift:
  - src/config/dataCenterRestrictionCost.ts  (the widget's constants, parsed by regex)
  - public/data/data-center-restriction-cost/*.json  (the pipeline's outputs)
  - src/content/data-center-restriction-cost.ts  (the prose)

Sections:
  0. Ground truth pins (Tucson reference, partial-abatement arithmetic)
  1. TS literals == benchmarks.json
  2. Prose MUST-contain (framing the scoping memo requires verbatim)
  3. Prose MUST-NOT (the claims-never-to-make list, as greps)
  4. Style budgets (em dashes, semicolons, AI tells, self-closing embeds)
  5. Data-file consistency (outcome tally vs prose, followup-marker gates,
     downloads exist)

Exit non-zero on any failure. Run from the repo root or this directory.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_TS = ROOT / "src/config/dataCenterRestrictionCost.ts"
CONTENT_TS = ROOT / "src/content/data-center-restriction-cost.ts"
DATA_DIR = ROOT / "public/data/data-center-restriction-cost"
ASSETS = ROOT / "public/assets"

failures: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def check(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


def ts_number(src: str, key: str) -> float:
    m = re.search(rf"\b{key}:\s*(-?[\d.]+)", src)
    if not m:
        fail(f"config: literal `{key}` not found as a single-line numeric literal")
        return float("nan")
    return float(m.group(1))


def main() -> int:
    config = CONFIG_TS.read_text()
    content = CONTENT_TS.read_text()

    # The prose as the reader sees it: strip the TS wrapper, split body vs details.
    prose = content
    body = prose.split("<details", 1)[0]
    words = len(re.findall(r"\b\w+\b", prose))

    # ---- 0 + 1. Config literals vs benchmarks.json --------------------------
    bench_path = DATA_DIR / "benchmarks.json"
    if not bench_path.exists():
        fail("benchmarks.json missing — run the pipeline (run_all.py) first")
        bench = None
    else:
        bench = json.loads(bench_path.read_text())

    horizon = ts_number(config, "horizonYears")
    if bench:
        check(horizon == bench["horizon_years"], "horizonYears != benchmarks.horizon_years")
        check(
            ts_number(config, "jobsPerFacilityPermanent") == bench["jobs_per_facility_permanent"],
            "jobsPerFacilityPermanent mismatch",
        )
        rc = bench["reference_campus"]
        check(ts_number(config, "referenceCapexUsdB") == rc["capex_usd_b"], "referenceCapexUsdB mismatch")
        check(ts_number(config, "referenceMw") == rc["mw"], "referenceMw mismatch")
        check(
            ts_number(config, "referenceLocal10yrUsdM") == rc["local_10yr_usd_m"],
            "referenceLocal10yrUsdM mismatch",
        )
        # Tucson pin: 97 + 60 = 157, and the reference constant carries it.
        check(rc["local_10yr_usd_m"] == 157, "Tucson pin: reference_campus.local_10yr_usd_m != 157 ($97M city + $60M county)")

        # Regimes: parse the REGIMES literal rows and compare to JSON.
        ts_regimes = re.findall(
            r'id:\s*"([a-z_]+)",\s*label:[^}]*?lowM:\s*([\d.]+),\s*highM:\s*([\d.]+)', config
        )
        check(len(ts_regimes) == 3, f"expected 3 REGIMES rows in config, found {len(ts_regimes)}")
        json_regimes = {r["id"]: r for r in bench["regimes"]}
        for rid, low, high in ts_regimes:
            jr = json_regimes.get(rid)
            if not jr:
                fail(f"regime `{rid}` in config but not benchmarks.json")
                continue
            check(float(low) == jr["annual_local_usd_m_low"], f"regime {rid} lowM mismatch")
            check(float(high) == jr["annual_local_usd_m_high"], f"regime {rid} highM mismatch")

        # Arithmetic pin: partial abatement, 1.0x, 10 years = [278, 560] — the
        # calculator's central case (no counterfactual discount by design).
        pa = json_regimes.get("partial_abatement")
        if pa:
            check(
                abs(pa["annual_local_usd_m_low"] * 10 - 278) < 1e-6
                and abs(pa["annual_local_usd_m_high"] * 10 - 560) < 1e-6,
                "partial-abatement 10-yr gross should be $278M-$560M (27.8/56 x 10)",
            )

    # ---- 2. Prose MUST-contain ---------------------------------------------
    first_line = next((ln for ln in prose.splitlines() if ln.strip()), "")
    # first non-empty line after the export wrapper
    lines = [ln.strip() for ln in prose.splitlines() if ln.strip()]
    header = lines[1] if lines and lines[0].startswith("export default") else lines[0] if lines else ""
    check(
        header.startswith("*") and "August 15, 2026" in header and ("update or rerun" in header),
        "italic as-of header (date + goes-stale + may update/rerun) missing or malformed at top of piece",
    )
    check("documented actions, not a census" in prose.lower(), "missing 'documented actions, not a census'")
    m = re.search(r"budgeted.{0,80}1,135\.7|1,135\.7.{0,80}budgeted", prose, re.S)
    check(bool(m), "'1,135.7' must appear within 80 chars of 'budgeted' (FY26 is a budgeted figure)")
    m = re.search(r"Data Center Watch.{0,400}\$64", prose, re.S) or re.search(
        r"\$64.{0,400}Data Center Watch", prose, re.S
    )
    check(bool(m), "the $64B figure must be attributed to Data Center Watch within 400 chars")
    check("70%" in prose and "90%" in prose, "both but-for anchors (70% Georgia, ~90% JLARC) must appear")
    # The calculator applies no counterfactual discount (2026-08-17 design
    # decision) — the live-proposal assumption must be stated in prose instead.
    check(
        "assumes a live proposal" in prose or "assumes the proposal is real" in prose,
        "the calculator's no-discount (live-proposal) assumption must be stated in prose",
    )
    m = re.search(r"(Mills|Maine).{0,120}vetoed|vetoed.{0,120}(Mills|Maine)", prose, re.S)
    check(bool(m), "'vetoed' must appear near Maine/Mills")
    m = re.search(r"55%.{0,200}Republican", prose, re.S)
    check(bool(m), "the 55% Republican-opposition figure must appear")
    m = re.search(r"55%.{0,400}(Data Center Watch|10a)", prose, re.S) or re.search(
        r"(Data Center Watch|10a).{0,400}55%", prose, re.S
    )
    check(bool(m), "the 55% figure must be attributed (Data Center Watch/10a Labs)")
    check("in force today" in prose, "map framing must say 'in force today' (default-view honesty)")
    m = re.search(r"EPRI.{0,300}2024|2024.{0,300}EPRI", prose, re.S)
    check(bool(m), "footprint figures must be attributed to EPRI near the 2024 vintage")
    check("medium scenario" in prose, "the 2030 footprint projection must be labeled as EPRI's medium scenario")
    check(
        "even when the action is a single town" in prose,
        "methodology must carry the single-town county-shading honesty phrase",
    )

    # ---- 3. Prose MUST-NOT -------------------------------------------------
    check(
        not re.search(r"America (lost|loses|gave up|is losing)", prose, re.I),
        "national aggregate loss framing detected ('America lost ...')",
    )
    check(
        not re.search(r"\$2\.5\s?(B\b|billion)", body),
        "the $2.5B Georgia figure appears in the body (allowed only as the methodology disclaimer)",
    )
    check(
        not re.search(r"Maine[^.]{0,80}enacted", prose),
        "Maine described as having enacted something — LD 307 was vetoed",
    )
    check(not re.search(r"blue[- ]state phenomenon", prose, re.I), "'blue-state phenomenon' framing")
    check(
        not re.search(r"\b20(3[7-9]|[4-9]\d)\b", body),
        "a year beyond 2036 appears in the body — the piece must not project past 2036",
    )
    check(not re.search(r"\$[\d,.]+[MBk]? per (permanent )?job", prose), "per-job dollar framing detected")
    for word in ["leverage", "robust", "seamless", "holistic", "delve", "moreover", "furthermore", "underscore"]:
        check(word not in prose.lower(), f"AI-tell word present: '{word}'")
    check("not just" not in prose.lower(), "'not just X but Y' construction present")
    # Narrator setup/reveal tells (Joe, 2026-08-09): the piece must not announce
    # its own storytelling.
    for pat in [
        r"[Hh]ere is what happened",
        r"this piece is the (result|story)",
        r"the shape of this (whole )?story",
        r"the full story",
        r"needs careful reading",
    ]:
        check(not re.search(pat, prose), f"narrator-reveal tell present: /{pat}/")
    for tell in ["SCOPING", "TODO", "FIXME", "Claude", "pricing-the-fear"]:
        check(tell not in prose, f"internal tell present in prose: '{tell}'")

    # ---- 4. Style budgets --------------------------------------------------
    em_count = prose.count("—") + prose.count("&mdash;")
    em_budget = max(3, words // 150)
    check(em_count <= em_budget, f"em-dash budget exceeded: {em_count} > {em_budget}")
    # Semicolons in reader-visible text (exclude URLs and HTML entities).
    visible = re.sub(r"https?://\S+", "", prose)
    visible = re.sub(r"&[a-z]+;", "", visible)
    visible = re.sub(r'class="[^"]*"', "", visible)
    semis_body = re.sub(r"https?://\S+", "", body).count(";") - len(re.findall(r"&[a-z]+;", body))
    semis_all = visible.count(";")
    check(semis_body <= 3, f"semicolon budget (body) exceeded: {semis_body} > 3")
    check(semis_all <= 6, f"semicolon budget (whole piece) exceeded: {semis_all} > 6")
    check(not re.search(r"<[a-z][a-z-]*\s*/>", prose), "self-closing embed tag found — embeds must be paired")
    for tag in ["dcr-map", "dcr-town-calc", "dcr-footprint-bars"]:
        check(f"<{tag}></{tag}>" in prose, f"embed <{tag}></{tag}> missing from the piece")

    # ---- 5. Data-file consistency ------------------------------------------
    out_path = DATA_DIR / "outcomes.json"
    if out_path.exists():
        outcomes = json.loads(out_path.read_text())
        tally = outcomes["tally"]
        recomputed: dict[str, int] = {}
        for p in outcomes["projects"]:
            recomputed[p["outcome"]] = recomputed.get(p["outcome"], 0) + 1
        for k, v in tally.items():
            check(recomputed.get(k, 0) == v, f"outcomes tally[{k}]={v} != recomputed {recomputed.get(k, 0)}")
        n = len(outcomes["projects"])
        check(str(n) in prose, f"prose does not mention the traced-project count ({n})")
        # The prose's outcome sentence must match the tally.
        for k, num in tally.items():
            label = {
                "died": "died",
                "rerouted": "reroute",
                "delayed_then_built": "delayed",
                "pending_litigating": "pending",
            }[k]
            m = re.search(rf"\b{num}\b.{{0,80}}{label}|{label}.{{0,80}}\b{num}\b", prose, re.S | re.I)
            check(bool(m), f"prose outcome numbers out of sync: expected {num} near '{label}'")
        if outcomes.get("sample"):
            fail("outcomes.json is still the SAMPLE file — run the pipeline")
        # Followup (soft relocation tier) gates. Counts recomputed from data,
        # never pinned; run_all.py recomputes the same invariants independently.
        n_fup = 0
        for p in outcomes["projects"]:
            fup = p.get("followup")
            dest = p.get("destination")
            if dest and p["outcome"] != "rerouted":
                fail(f"outcomes: {p['id']} has a destination on non-rerouted outcome {p['outcome']}")
            if not fup:
                continue
            n_fup += 1
            if p["outcome"] not in ("died", "pending_litigating"):
                fail(f"outcomes: {p['id']} followup on outcome {p['outcome']}")
            if dest:
                fail(f"outcomes: {p['id']} carries followup and destination together")
            if not fup.get("name") or fup.get("lat") is None or fup.get("lon") is None:
                fail(f"outcomes: {p['id']} followup missing name or coords")
            if not fup.get("sources"):
                fail(f"outcomes: {p['id']} followup without its own sources")
            dist = fup.get("distance_mi")
            if not isinstance(dist, int) or not 0 < dist <= 150:
                fail(f"outcomes: {p['id']} followup distance_mi missing or implausible ({dist})")
        if n_fup:
            m = re.search(
                rf"\b{n_fup}\b.{{0,80}}(?:nearby|same developer)|(?:nearby|same developer).{{0,80}}\b{n_fup}\b",
                prose, re.S | re.I)
            check(bool(m), f"prose does not carry the followup count ({n_fup}) near 'nearby'/'same developer'")
            caveat = "not confirmed as the same project"
            check(caveat in prose, f"content prose missing verbatim followup caveat: '{caveat}'")
            meth_path = ASSETS / "data-center-restriction-cost-methodology.md"
            check(meth_path.exists() and caveat in meth_path.read_text(),
                  f"methodology.md missing verbatim followup caveat: '{caveat}'")
            map_path = ROOT / "src/components/dcr/DcrMap.tsx"
            check(map_path.exists() and caveat in map_path.read_text(),
                  "DcrMap.tsx popup missing the followup caveat phrase")
    else:
        fail("outcomes.json missing")

    act_path = DATA_DIR / "actions.json"
    actions = None
    if act_path.exists():
        actions = json.loads(act_path.read_text())
        if actions.get("sample"):
            fail("actions.json is still the SAMPLE file — run the pipeline")
        check(actions.get("snapshot_date") == "2026-08-15", "actions.json snapshot_date != 2026-08-15")
    else:
        fail("actions.json missing")

    # County friction layer: recompute the default aggregation from the rows
    # and pin the shipped counties.geojson to it (the anti-drift lock across
    # the pipeline, the shipped file, and the TS derivation).
    if actions:
        fp = actions.get("footprint")
        if not fp:
            fail("footprint block missing from actions.json (EPRI state layer)")
        else:
            fps = fp["states"]
            check(len(fps) == 51, f"footprint covers {len(fps)} states, expected 51")
            vals = {k: v["twh_2024"] for k, v in fps.items() if v["twh_2024"] is not None}
            va = fps.get("51", {}).get("twh_2024") or 0
            check(va == max(vals.values()), "Virginia should carry the largest 2024 footprint (EPRI)")
            check(fps.get("11", {}).get("twh_2024") is None, "DC should be null (EPRI covers 50 states)")
            # The concentration claims in prose, recomputed from the data:
            total = sum(vals.values())
            check(0.17 <= va / total <= 0.20, f"VA share {va / total:.1%} no longer matches the prose's 18%")
            bottom35 = sum(sorted(vals.values())[:35])
            check(va > bottom35, "VA no longer exceeds the bottom 35 states combined — fix the prose")
            check(
                "thirty-five states combined" in prose,
                "the bottom-35 concentration line is missing from the prose",
            )

    counties_path = DATA_DIR / "counties.geojson"
    if not counties_path.exists():
        fail("counties.geojson missing — run the pipeline")
    elif actions:
        cdoc = json.loads(counties_path.read_text())
        feats = cdoc["features"]
        check(len(feats) >= 400, f"counties.geojson has only {len(feats)} features")
        check(counties_path.stat().st_size < 700_000, "counties.geojson exceeds 700KB")
        geoids = [f["properties"]["GEOID"] for f in feats]
        check(len(geoids) == len(set(geoids)), "duplicate GEOIDs in counties.geojson")
        valid_cats = {"county_restriction", "town_restriction", "conditions_only", "pending_only", "lapsed_only"}
        check(
            all(f["properties"]["category"] in valid_cats for f in feats),
            "invalid county category in counties.geojson",
        )
        local_rows = [a for a in actions["actions"] if a["level"] == "local"]
        unassigned = [a["id"] for a in local_rows if not a.get("county_fips")]
        check(len(unassigned) <= 5, f"{len(unassigned)} local rows without county_fips")
        check(
            all(a.get("county_wide") for a in local_rows if a["jurisdiction_type"] == "county"),
            "a county-typed row is not county_wide",
        )
        live_set = {"enacted", "in_force"}
        by_county: dict[str, list] = {}
        for a in local_rows:
            if a.get("county_fips"):
                by_county.setdefault(a["county_fips"], []).append(a)
        for f in feats:
            p = f["properties"]
            rows = by_county.get(p["GEOID"], [])
            live_restr = [r for r in rows if r["status"] in live_set and r["class"] == "restriction"]
            live_cond = [r for r in rows if r["status"] in live_set and r["class"] == "condition"]
            pend = [r for r in rows if r["status"] == "pending"]
            if any(r.get("county_wide") for r in live_restr):
                expect = "county_restriction"
            elif live_restr:
                expect = "town_restriction"
            elif live_cond:
                expect = "conditions_only"
            elif pend:
                expect = "pending_only"
            else:
                expect = "lapsed_only"
            if p["category"] != expect:
                fail(f"county {p['GEOID']} category drift: shipped {p['category']}, recomputed {expect}")
                break

    for f in [
        ASSETS / "data-center-restriction-cost-actions.csv",
        ASSETS / "data-center-restriction-cost-methodology.md",
        ASSETS / "data-center-restriction-cost-outcomes.csv",
    ]:
        check(f.exists(), f"download missing: {f.name}")

    # ---- 6. Claim-surface guard (card + LinkedIn draft) ---------------------
    # The 2026-08-19 displacement audit found the overreach lived in the
    # shallowest, most-shared surfaces (card summary, post) while the body
    # prose was hedged correctly. Rule: no frequency adverb may sit next to a
    # project-fate word in those surfaces — write counts with denominators.
    freq_near_fate = re.compile(
        r"\b(?:usually|rarely|mostly|typically|often)\b[^.]{0,60}\b(?:projects?|reroutes?|relocat\w*|moves?|moved|kills?|died?|dead)\b"
        r"|\b(?:projects?|reroutes?|relocat\w*|moves?|moved|kills?|died?|dead)\b[^.]{0,60}\b(?:usually|rarely|mostly|typically|often)\b",
        re.I)
    gz = (ROOT / "src/data/gizmos.ts").read_text()
    m = re.search(r'slug: "data-center-restriction-cost".*?summary:\s*"([^"]+)"', gz, re.S)
    if not m:
        fail("gizmos.ts: could not locate the DCR card summary string")
    else:
        card = m.group(1)
        check(not freq_near_fate.search(card),
              "card summary: frequency adverb next to a project-fate word (write counts with denominators)")
        check("usually moves one jurisdiction over" not in card,
              "card summary still carries the pre-audit overreach")
    post_path = ROOT / "gizmos/data-center-restriction-cost/linkedin/post.md"
    if post_path.exists():
        post_body = post_path.read_text().split("\n---\n", 1)[-1]
        check(not freq_near_fate.search(post_body),
              "linkedin/post.md: frequency adverb next to a project-fate word (write counts with denominators)")
        check("rarely kills the project" not in post_body,
              "linkedin/post.md still carries the pre-audit overreach")

    # ---- report -------------------------------------------------------------
    print(f"verify_claims: {words} words, {em_count} em dashes (budget {em_budget}), body semicolons {semis_body}")
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print("  ~", w)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f_ in failures:
            print("  ✗", f_)
        return 1
    print("ALL CHECKS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
