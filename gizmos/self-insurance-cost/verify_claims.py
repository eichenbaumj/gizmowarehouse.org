#!/usr/bin/env python3
"""Verify gate for the self-insurance-cost gizmo.

Locks four surfaces to each other:
  - src/config/selfInsuranceCost.ts            (constants, parsed by regex)
  - public/data/self-insurance-cost/*.json     (pipeline outputs)
  - src/content/self-insurance-cost.ts         (the prose)
  - public/assets/self-insurance-cost-*.csv/.md (the downloads)

Sections:
  1. Config literals == models.json / ny_entities.json
  2. Prose MUST-contain (co-location of each number with its framing)
  3. Prose MUST-NOT (the never-claim list, the MTA rule, policy-not-person, AI and stats tells)
  4. Style budgets (words, em dashes, semicolons, colon setups, embed tags)
  5. Downloads and card surfaces
  6. Intervention section: every would/could/should sentence anchored or labeled illustrative

Exit non-zero on any failure. Run from anywhere: python3 gizmos/self-insurance-cost/verify_claims.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SLUG = "self-insurance-cost"
CONFIG_TS = ROOT / "src/config/selfInsuranceCost.ts"
CONTENT_TS = ROOT / f"src/content/{SLUG}.ts"
DATA_DIR = ROOT / f"public/data/{SLUG}"
ASSETS = ROOT / "public/assets"
COMPONENTS = ROOT / "src/components/sic"
GIZMOS_TS = ROOT / "src/data/gizmos.ts"
CHECKLIST = ROOT / f"gizmos/{SLUG}/PUBLISH_CHECKLIST.md"

failures: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def check(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


def ts_number(src: str, key: str) -> float:
    m = re.search(rf"\b{key}:\s*(-?[\d.]+)", src)
    if not m:
        fail(f"config: literal `{key}` not found as a single-line numeric literal")
        return float("nan")
    return float(m.group(1))


def near(text: str, a: str, b: str, window: int = 120) -> bool:
    return bool(re.search(rf"{a}.{{0,{window}}}{b}|{b}.{{0,{window}}}{a}", text, re.S | re.I))


def main() -> int:
    config = CONFIG_TS.read_text()
    content = CONTENT_TS.read_text()
    body = content.split("<details", 1)[0]
    words = len(re.findall(r"\b\w+\b", body))

    # ---- 1. config == data -------------------------------------------------
    models_p, ents_p = DATA_DIR / "models.json", DATA_DIR / "ny_entities.json"
    if not models_p.exists() or not ents_p.exists():
        fail("public data missing; run pipeline/run_all.py first")
        models, ents = None, None
    else:
        models = json.loads(models_p.read_text())
        ents = json.loads(ents_p.read_text())
    if models:
        prim_id = "ny_core_classbin_cor_pc"
        prim = next((s for s in models["ny"]["specs"] if s["spec_id"] == prim_id), None)
        check(prim is not None, f"models.json lacks the primary spec {prim_id}")
        if prim:
            check(ts_number(config, "ratioCentral") == prim["coef"], f"ratioCentral != models {prim['coef']}")
            check(ts_number(config, "ratioLow") == prim["lo"], f"ratioLow != models {prim['lo']}")
            check(ts_number(config, "ratioHigh") == prim["hi"], f"ratioHigh != models {prim['hi']}")
            check(ts_number(config, "coreSelf") == prim["n_self"], f"coreSelf != models {prim['n_self']}")
            check(ts_number(config, "coreCovered") == prim["n_covered"], f"coreCovered != models {prim['n_covered']}")
        vol, expo = models["ny"].get("volatility", {}), models["ny"].get("exposure", {})
        check(bool(vol) and bool(expo), "models.json lacks the volatility/exposure blocks (stage 07)")
        if vol and expo:
            check(ts_number(config, "swingSelf") == vol["yoy_cv_self"], f"swingSelf != {vol['yoy_cv_self']}")
            check(ts_number(config, "swingCovered") == vol["yoy_cv_covered"], f"swingCovered != {vol['yoy_cv_covered']}")
            check(ts_number(config, "policeRatioPer10pts") == expo["ratio_per_10pts"], f"policeRatioPer10pts != {expo['ratio_per_10pts']}")
            pr = round((expo["ratio_per_10pts"] - 1) * 100 / 10) * 10
            check(near(body, "police", rf"roughly {pr} percent", 200), f"police effect sentence must say 'roughly {pr} percent'")
            ratio_sw = vol["yoy_cv_self"] / vol["yoy_cv_covered"]
            check(1.6 <= ratio_sw <= 2.6 and near(body, "swing", "twice", 120), f"prose says swing 'twice'; models give {ratio_sw:.2f}")
            p90 = vol["p90_over_mean_self"]
            check(abs(p90 - 1.4) < 0.1 and near(body, "worst year", "40 percent"), f"worst-year sentence says 40 percent; models give {p90}")
            check(expo["self_ratio_same_model"] is not None and 0.8 <= expo["self_ratio_same_model"] <= 1.25, "'adds nothing' requires the structure ratio near 1 in the exposure model")
            het = models["ny"].get("heterogeneity", {})
            check(all(h["lo"] <= 1 <= h["hi"] for h in het.values()), "'no type of government shows a credible premium' requires every heterogeneity range to span 1")
            every = all((c["yoy_cv_self"] or 0) > (c["yoy_cv_covered"] or 0) for c in vol["by_class"].values() if c["yoy_cv_self"] and c["yoy_cv_covered"])
            check(every, "'in every class' requires self-insured swing above covered swing in every class")
        samp = models["ny"].get("sample", {})
        check(ts_number(config, "windowStart") == samp.get("window", [0, 0])[0], "windowStart mismatch")
        check(ts_number(config, "windowEnd") == samp.get("window", [0, 0])[1], "windowEnd mismatch")
        check(re.search(r'snapshotDate:\s*"' + re.escape(models["snapshot"]) + '"', config) is not None, "snapshotDate != models.snapshot")
        # the primary ratio's range must contain 1 if the prose says "about as much"; and the prose must carry the range
        if prim and prim["lo"] is not None:
            lo, hi = prim["lo"], prim["hi"]
            hi_word = "roughly double" if 1.85 <= hi <= 2.15 else "roughly 1.8 times" if 1.65 <= hi < 1.85 else f"roughly {hi:.1f} times"
            lo_word = "roughly half" if 0.4 <= lo <= 0.6 else f"roughly {lo:.1f} times"
            check(near(body, lo_word, hi_word), f"prose must carry the primary range as '{lo_word} to {hi_word}' (models: {lo}, {hi})")
            # "about as much" and "I found no difference overall" are honest only while the range contains 1; the range sentence is the bound
            check(lo <= 1 <= hi, "prose says 'about as much' / 'no difference overall' but the primary range excludes 1")
    if ents:
        s = ents.get("summary", {})
        if "self" in s and "covered" in s:
            check(s["self"]["median_ins_pc"] < s["self"]["median_jc_pc"], "mix claim: self-insured medians should be judgments-heavy")
            check(s["covered"]["median_ins_pc"] > s["covered"]["median_jc_pc"], "mix claim: covered medians should be premium-heavy")
        check(ts_number(config, "nCountiesRead") == 57, "nCountiesRead != 57")
        n_doc_county = sum(1 for r in ents["rows"] if r["label_source"] == "document" and r["cls"] == "county")
        n_doc_city = sum(1 for r in ents["rows"] if r["label_source"] == "document" and r["cls"] == "city")
        check(n_doc_county == 57, f"document-labeled counties in ny_entities.json: {n_doc_county} != 57")
        check(n_doc_city == ts_number(config, "nCitiesRead"), f"document-labeled cities {n_doc_city} != nCitiesRead")

    # ---- 2. prose MUST-contain ---------------------------------------------
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    header = lines[1] if lines and lines[0].startswith("export default") else (lines[0] if lines else "")
    check(header.startswith("*") and "October 8, 2026" in header and "update or rerun" in header,
          "italic as-of header (date + may update/rerun) missing or malformed")
    check(near(body, "57 counties", "20 largest cities"), "prose must say how many statements were read (57 counties, 20 largest cities)")
    check(near(body, r"\$750,000", "NYMIR"), "NYMIR's $750,000 retention must sit near its name")
    check(near(body, r"more than a thousand", r"1,600"), "NYMIR subscriber framing (more than a thousand of ~1,600) required")
    check(near(body, r"\$87 million", "Nassau"), "Nassau 2024 judgments figure must sit near its name")
    if "650 percent" in body:
        check(near(body, "650 percent", "National League of Cities"), "the 650 percent figure must be attributed to NLC")
    check(near(body, "Vallejo", r"\$500,000 to \$2\.5 million") and near(body, r"\$392,000", r"\$2\.4 million"), "Vallejo retention and premium figures required")
    check(near(body, "working paper", "Vallejo", 400), "Vallejo must be labeled a working paper")
    check(near(body, "Cities cannot be tested", "45,000"), "the cities-cannot-be-tested sentence with the 45,000 threshold is required")
    check(near(body, "the same or less", "every size band"), "the per-band finding sentence is required")
    check(near(body, "understate what self-insurers pay", "booked elsewhere"), "the measurement-direction sentence is required")
    if "sic-transit-scatter" in body or "transit agencies" in body.lower():
        check("picture, not a test" in body, "transit must be labeled 'a picture, not a test'")
    check(near(body, "no type of government", "credible self-insurance premium", 160), "the no-type-shows-a-premium sentence is required")
    check(near(body, "cannot see", "rescue the hypothesis", 200), "the what-the-books-cannot-see paragraph is required")
    check(near(body, "hypothesis is wrong", "do not pay far more", 200), "the rejection sentence (hypothesis wrong in its strong form; do not pay far more) is required")
    check(near(body, "found no difference overall", "certain kinds of governments"), "the no-difference-overall / maybe-for-some-kinds sentence is required")
    check(near(body, "do seem to pay more", "too few to trust"), "the police-heavy cities/villages lean must carry its too-few-comparators caveat")
    check(near(body, "cannot say", "public books") or near(body, "cannot say", "illustrative", 200), "the intervention section must disclaim with 'cannot say' and 'illustrative'")
    check(near(body, "Schwartz", "100,000"), "the Schwartz 100,000 threshold must be attributed")
    # order-of-magnitude sentence: NY outside NYC, cost of risk summed across counties/cities/towns/villages, nominal, FY2022-2024
    check(near(body, r"\$500 million to \$650 million", r"outside New York City"), "the statewide-spend sentence ($500 million to $650 million outside NYC) is required")
    check(near(body, r"\$1\.9 billion", r"New York City"), "the NYC $1.9 billion (FY2024 Comptroller dashboard) figure is required")
    panel_csv = ASSETS / f"{SLUG}-ny-panel.csv"
    if panel_csv.exists():
        import csv
        tot = {}
        with panel_csv.open(encoding="utf-8") as f:
            f.readline()
            for r in csv.DictReader(f):
                if r["cls"] in ("county", "city", "town", "village") and r["fy"] in ("2022", "2023", "2024") and r["cost_of_risk"]:
                    tot[r["fy"]] = tot.get(r["fy"], 0.0) + float(r["cost_of_risk"])
        if len(tot) == 3:
            check(all(450e6 <= v <= 700e6 for v in tot.values()), f"'$500 million to $650 million' no longer matches FY2022-24 totals: { {k: round(v/1e6) for k, v in tot.items()} }")
    check("MTA" not in body and "Metropolitan Transportation Authority" not in body, "MTA rule: not in the body")

    # ---- 3. prose MUST-NOT -------------------------------------------------
    banned = [r"statistically significant", r"\bsignificant\b", r"p-value", r"\bp\s*[<=]", r"\brobust\b", r"\bproves?\b", r"confidence interval",
              r"\bleverage\b", r"\bseamless\b", r"\bholistic\b", r"\bdelve\b", r"\bmoreover\b", r"\bfurthermore\b", r"\bunderscore", r"not just",
              r"\bSCOPING\b", r"\bTODO\b", r"\bFIXME\b", r"\bClaude\b", r"working title"]
    for pat in banned:
        if re.search(pat, content, re.I):
            fail(f"banned phrase in content: /{pat}/")
    for pat in [r"\bMTA\b", r"Metropolitan Transportation Authority", r"New York City Transit"]:
        for p in [config, *[f.read_text() for f in COMPONENTS.glob("*.tsx")], (ASSETS / f"{SLUG}-methodology.md").read_text()]:
            if re.search(pat, p):
                fail(f"MTA rule: /{pat}/ found in config, components, or methodology")
    check(not re.search(r"\b(Mayor|Governor|Comptroller|Commissioner|Executive|Supervisor|Treasurer)\s+[A-Z][a-z]+", body),
          "policy-not-person: a titled official's name appears in the body")
    check(not re.search(r"\b(blame|mismanag|incompeten)", content, re.I), "policy-not-person: blame/mismanagement language")
    check(not re.search(r"self-insurance causes|causes? (higher|more)", body, re.I), "no causal claim from the cross-section")
    check("total per New Yorker" not in body, "never stack layers into a per-New-Yorker total")

    # ---- 4. style budgets ----------------------------------------------------
    check(words <= 1450, f"body words {words} > 1450 hard cap")  # raised from 1,200 by Joe, 2026-10-09
    if words > 800:
        warn(f"body words {words} > 800 target")
    em = body.count("—")
    check(em <= max(3, words // 150), f"em dashes {em} over budget")
    check(body.count(";") <= 3, f"semicolons in body: {body.count(';')} > 3")
    colon_setups = [m.group(0) for m in re.finditer(r"[a-z]{3,}: [A-Za-z][^\n]{0,80}", body) if not re.search(r"https?:|Downloads:|tell me:", m.group(0))]
    if colon_setups:
        warn(f"mid-sentence colon setups: {colon_setups[:4]}")
    tags = re.findall(r"<(sic-[a-z-]+)>", body)
    check(not re.search(r"<sic-[a-z-]+\s*/>", content), "self-closing embed tags are not allowed (use a pair)")
    for tg in set(tags):
        check(body.count(f"<{tg}></{tg}>") == 1, f"embed {tg} must appear exactly once as a pair")
        check((COMPONENTS / {"sic-core-chart": "SicCoreChart.tsx", "sic-mix-bars": "SicMixBars.tsx", "sic-volatility": "SicVolatility.tsx", "sic-transit-scatter": "SicTransitScatter.tsx"}.get(tg, "missing")).exists(),
              f"no component file for {tg}")
    embeds_tsx = (ROOT / "src/content/embeds.tsx").read_text()
    if "sic-core-chart" in embeds_tsx:
        for tg in set(tags):
            check(tg in embeds_tsx and tg in (ROOT / "src/content/embeds.static.tsx").read_text(), f"{tg} registered in embeds.tsx but not embeds.static.tsx (or vice versa)")

    # ---- 5. downloads and card ---------------------------------------------
    for name in (f"{SLUG}-ny-panel.csv", f"{SLUG}-ntd-panel.csv", f"{SLUG}-treatment-labels.csv"):
        p = ASSETS / name
        if not p.exists():
            fail(f"download missing: {name}")
            continue
        first = p.open(encoding="utf-8").readline()
        check(first.startswith("#") and "2026-10-08" in first and "CC-BY-4.0" in first and "joe@group17a.com" in first, f"{name}: attribution header line malformed")
    labels = ASSETS / f"{SLUG}-treatment-labels.csv"
    if labels.exists():
        import csv
        with labels.open(encoding="utf-8") as f:
            f.readline()
            rows = list(csv.DictReader(f))
        bad = [r.get("entity_name") or r.get("agency") for r in rows if not (r.get("source_doc_url") or "").strip() or not (r.get("quote") or "").strip()]
        check(not bad, f"label rows without source_doc_url + quote: {bad[:5]}")
    meth = ASSETS / f"{SLUG}-methodology.md"
    check(meth.exists(), "methodology download missing")
    if meth.exists():
        mt = meth.read_text()
        check("cannot say what a large self-insured city would pay" in mt, "methodology must carry the no-counterfactual caveat")
        check("agreed with the documents only about half the time" in mt, "methodology must carry the signature-validation caveat")
    # card surfaces: the gizmos.ts entry (if published) or the checklist block
    card_src = GIZMOS_TS.read_text() if f'slug: "{SLUG}"' in GIZMOS_TS.read_text() else CHECKLIST.read_text()
    m = re.search(rf'slug: "{SLUG}".*?\n  \}},', card_src, re.S)
    if m:
        card = m.group(1) if m.groups() else m.group(0)
        md = re.search(r'metaDescription:\s*"([^"]*)"', card)
        if md:
            check(len(md.group(1)) <= 155 and "—" not in md.group(1) and "TODO" not in md.group(1), "metaDescription: <=155 chars, no em dash, no TODO")
        sm = re.search(r'summary:\s*"([^"]*)"', card)
        if sm:
            check("—" not in sm.group(1) and not re.search(r"\b(usually|rarely|mostly|typically|often)\b.{0,60}(self-insur|pool|overspend|cost)", sm.group(1), re.I),
                  "card summary: no em dash, no frequency adverbs near fate words")
            check("MTA" not in sm.group(1), "card summary: MTA rule")

    # ---- 6. intervention section ---------------------------------------------
    sec = re.search(r"## What a government could do(.*?)## Housekeeping", body, re.S)
    check(sec is not None, "intervention section missing")
    if sec:
        anchors = r"Vallejo|NYMIR|ClaimStat|Schwartz|Chicago|pool|retention|illustrative|cannot say"
        for sent in re.split(r"(?<=[.!?])\s+", sec.group(1).strip()):
            if re.search(r"\b(would|could|should)\b", sent) and not re.search(anchors, sent):
                fail(f"intervention sentence without an anchor or 'illustrative': {sent[:90]}")

    for w in warnings:
        print(f"WARN  {w}")
    for f_ in failures:
        print(f"FAIL  {f_}")
    print(f"{'FAIL' if failures else 'PASS'}: {len(failures)} failures, {len(warnings)} warnings, {words} body words")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
