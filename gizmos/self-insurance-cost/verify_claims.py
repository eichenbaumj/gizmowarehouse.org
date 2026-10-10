#!/usr/bin/env python3
"""Verify gate for the self-insurance-cost gizmo.

Locks four surfaces to each other:
  - src/config/selfInsuranceCost.ts            (constants, parsed by regex)
  - public/data/self-insurance-cost/*.json     (pipeline outputs)
  - src/content/self-insurance-cost.ts         (the prose, Methodology, Sources)
  - public/assets/self-insurance-cost-*.csv/.md (the downloads) and the card in src/data/gizmos.ts

Rebuilt after the 2026-10-10 adversarial audit (gizmos/self-insurance-cost/research/AUDIT_2026-10-10.md, not
mirrored): wherever the prose states a number or a quantifier ("every", "about twice", "a third", a range), the
gate recomputes it from the pipeline outputs and requires the prose's words to match, instead of pinning a phrase.

Sections:
  1. Config literals == models.json / ny_entities.json
  2. Prose numbers and quantifiers, recomputed
  3. Prose MUST-NOT (never-claim list, client language, causal verbs, policy-not-person, AI and stats tells)
  4. Style budgets (words, em dashes, semicolons, colon setups, embed tags)
  5. Downloads and card surfaces
  6. Intervention section: every would/could/should sentence anchored or labeled

Exit non-zero on any failure. Run from anywhere: python3 gizmos/self-insurance-cost/verify_claims.py
"""

from __future__ import annotations

import csv
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
CROSSWALKS = ROOT / f"gizmos/{SLUG}/crosswalks"
RAW_ACFR = ROOT / f"gizmos/{SLUG}/pipeline/raw/acfr"
PRIMARY = "ny_core_classbin_cor_liab_pc"

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


def near(text: str, a: str, b: str, window: int = 160) -> bool:
    return bool(re.search(rf"{a}.{{0,{window}}}{b}|{b}.{{0,{window}}}{a}", text, re.S | re.I))


def spec(models: dict, sid: str) -> dict | None:
    return next((s for s in models["ny"]["specs"] if s["spec_id"] == sid), None)


NUM = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


# ---- words the prose must use for a given number ----------------------------------------------------------
def level_words(c: float) -> str:
    if 0.9 <= c <= 1.15:
        return "as much as"
    if 1.15 < c <= 1.3:
        return "a fifth more than"
    return f"{c:.1f} times"


def lo_words(lo: float) -> str:
    return "about half" if 0.45 <= lo < 0.55 else f"about {lo:.1f} times"


def hi_words(hi: float) -> str:
    return "about double" if 1.95 <= hi < 2.05 else f"about {hi:.1f} times"


def times_words(x: float) -> str:
    if 1.9 <= x < 2.1:
        return "about twice"
    if 1.45 <= x < 1.55:
        return "about one and a half times"
    return f"about {x:.1f} times"


def share_words(x: float) -> str:
    for lo, hi, w in ((0.28, 0.38, "a third"), (0.38, 0.45, "two-fifths"), (0.45, 0.56, "half"), (0.2, 0.28, "a quarter")):
        if lo <= x < hi:
            return w
    return f"{round(x * 100)} percent"


def main() -> int:
    config = CONFIG_TS.read_text()
    content = CONTENT_TS.read_text()
    body = content.split("<details", 1)[0]
    meth = content.split("<details", 1)[1] if "<details" in content else ""
    words = len(re.findall(r"\b\w+\b", body))
    models = json.loads((DATA_DIR / "models.json").read_text())
    ents = json.loads((DATA_DIR / "ny_entities.json").read_text())
    ny = models["ny"]
    vol, expo, het, big, sw = ny["volatility"], ny["exposure"], ny["heterogeneity"], ny["big_governments"], ny["statewide"]
    prim = spec(models, PRIMARY)
    check(prim is not None, f"models.json lacks the primary spec {PRIMARY}")
    rows = ents["rows"]
    plotted = [r for r in rows if r.get("plotted")]
    doc = [r for r in rows if r["label_source"] == "document"]

    # ---- 1. config == data -------------------------------------------------
    if prim:
        for key, val in (("ratioCentral", prim["coef"]), ("ratioLow", prim["lo"]), ("ratioHigh", prim["hi"]),
                         ("coreSelf", prim["n_self"]), ("coreCovered", prim["n_covered"])):
            check(ts_number(config, key) == val, f"config {key} != models {val}")
        check("B=2000" in prim["se_type"], f"primary range must come from 2,000 bootstrap draws ({prim['se_type']})")
    for key, val in (("swingSelf", vol["yoy_cv_self"]), ("swingCovered", vol["yoy_cv_covered"]), ("swingMatched", vol["matched_ratio"]),
                     ("worstSelf", vol["max_over_mean_self"]), ("worstCovered", vol["max_over_mean_covered"]),
                     ("policeDeptRatio", expo["dept_model"]["police_dept"]["ratio"])):
        check(ts_number(config, key) == val, f"config {key} != models {val}")
    check(ts_number(config, "nRead") == len(doc), f"config nRead != {len(doc)} document-labeled governments")
    check(ts_number(config, "nCountiesRead") == 57 and sum(r["cls"] == "county" for r in doc) == 57, "all 57 counties must be labeled")
    check(ts_number(config, "windowStart") == ny["sample"]["window"][0] and ts_number(config, "windowEnd") == ny["sample"]["window"][1], "window mismatch")
    check(re.search(r'snapshotDate:\s*"' + re.escape(models["snapshot"]) + '"', config) is not None, "snapshotDate != models.snapshot")

    # ---- 2. prose numbers and quantifiers, recomputed ----------------------
    header = next((ln.strip() for ln in content.splitlines() if ln.strip().startswith("*Up to date")), "")
    check("AI help" in header and "update or rerun" in header and re.search(r"as of \w+ \d+, 20\d\d", header) is not None,
          "as-of header must carry the date, the AI-help disclosure, and 'update or rerun'")
    check(f"{len(doc)} governments in all" in body, f"prose must say how many governments were read ({len(doc)})")
    check(f"Each of the {len(plotted)} marks" in body, f"chart mark count must match the plotted governments ({len(plotted)})")
    if prim:
        lw, lo_w, hi_w = level_words(prim["coef"]), lo_words(prim["lo"]), hi_words(prim["hi"])
        check(near(body, "spent about " + lw, "the covered", 20), f"level sentence must say 'spent about {lw} the covered' (primary {prim['coef']})")
        check(near(body, lo_w, hi_w, 20), f"range must read '{lo_w} to {hi_w}' (primary {prim['lo']}-{prim['hi']})")
        check(prim["lo"] <= 1 <= prim["hi"], "'about as much' needs a range that contains 1")
    # the verdict follows the headline: it leans the colleague's way only while the best estimate is above 1.1, and the
    # prose must say the range leaves room for no gap while the range's low end is at or below 1
    if prim:
        check(("leans my colleague's way" in body) == (prim["coef"] > 1.1), f"'leans my colleague's way' must track the headline ({prim['coef']})")
        check(("leaves room for no gap" in body) == (prim["lo"] <= 1), f"'leaves room for no gap' must track the range's low end ({prim['lo']})")
        check(prim["hi"] < 3 and "falls short of far more" in body, f"'a fifth more falls short of far more' needs the top of the range under 3x ({prim['hi']})")
        check(prim["coef"] > 1 and prim["lo"] <= 1 and "if anything, pays less for it" in body, "'if anything, pays less' needs a best estimate above 1 with a range containing 1")
    sbc = ents["summary_by_class"]
    higher = all(sbc[c]["self"]["median_cor_pc"] > sbc[c]["covered"]["median_cor_pc"] for c in sbc if "self" in sbc[c] and "covered" in sbc[c])
    check(higher and "the typical dark mark sits higher" in body, "'the typical dark mark sits higher' needs the self-insured median above the covered median in every type")
    # cities: Schenectady is the largest covered city
    cc = big["ceilings"].get("city", {})
    check(cc.get("largest_covered") == "City of Schenectady" and 60_000 <= cc.get("largest_covered_pop", 0) <= 70_000 and near(body, "Schenectady", "67,000"),
          "cities sentence: Schenectady (about 67,000) must be the largest covered city read")
    cv = het["cities_and_villages"]
    check(near(body, f"only {NUM.get(cv['n_covered'], cv['n_covered'])} covered ones", "too few"), f"cities and villages: prose must say only {cv['n_covered']} covered ones")
    # police
    pd_ = expo["dept_model"]["police_dept"]  # the department contrast itself (no share term)
    pw = "roughly twice as much" if 1.9 <= pd_["ratio"] < 2.15 else f"roughly {pd_['ratio']:.1f} times as much"
    check(near(body, "police department", pw, 120), f"police sentence must say '{pw}' (ratio {pd_['ratio']})")
    check(near(body, f"{pd_['lo']:.1f} to {pd_['hi']:.1f} times as much", "police department", 200), f"police range must read '{pd_['lo']:.1f} to {pd_['hi']:.1f} times as much'")
    check(f"{pd_['ratio']:.2f} times the cost (range {pd_['lo']:.2f} to {pd_['hi']:.2f})" in meth, "Methodology must give the department contrast from the no-share model")
    selfs = [expo[k]["self"] for k in ("dept_model", "police_share_model", "law_enf_share_model")]
    check(all(x["ratio"] > 1 and x["lo"] <= 1 <= x["hi"] for x in selfs) and "the self-insured still come out somewhat higher, with ranges that include no difference" in body,
          f"'still come out somewhat higher, with ranges that include no difference' needs every police-model structure ratio above 1 with a range containing 1 ({selfs})")
    groups = [k for k in het if k != "cities_and_villages"]
    check(all(het[k]["lo"] <= 1 <= het[k]["hi"] for k in groups), f"'no group ... clearly paying more' needs every subgroup range to contain 1 ({groups})")
    yd = models["ntd"]["yardsticks"]
    check("transit" not in body.lower() or near(body, "per mile", "per passenger"), "if the body mentions transit it must give both the per-mile and per-passenger readings")
    check(near(meth, "per vehicle revenue mile", "per passenger trip", 200) and yd["per_trip"]["lo"] <= 1 <= yd["per_trip"]["hi"] and "description, not a test" in meth,
          "Methodology must describe transit on every yardstick and call it a description, not a test")
    # swing
    ratio_pool = vol["yoy_cv_self"] / vol["yoy_cv_covered"]
    check(1.7 <= vol["matched_ratio"] < 1.95 and 1.7 <= vol["controlled_ratio"] < 1.95 and near(body, "swing nearly twice", "same type and size", 200),
          f"'swing nearly twice' needs the matched ({vol['matched_ratio']}) and controlled ({vol['controlled_ratio']}) ratios in 1.7-1.95")
    check(vol["matched_lo"] > 1 and vol["controlled_lo"] > 1, "the swing gap's ranges must exclude no difference")
    check(all((c["yoy_cv_self"] or 0) > (c["yoy_cv_covered"] or 9) for c in vol["by_class"].values()) and "every type of government" in body,
          "'more in every class' requires self-insured swing above covered in every class")
    check(near(body, "worst year", times_words(vol["max_over_mean_self"]) + " its average") and times_words(vol["max_over_mean_covered"]) in body,
          f"worst-year sentence must say '{times_words(vol['max_over_mean_self'])} its average' against '{times_words(vol['max_over_mean_covered'])}'")
    wy = f"{vol['worst_year_budget_share_self'] * 100:.1f}"
    check(near(body, "worst year added about " + re.escape(wy) + " percent", "spending"), f"budget sentence must say 'about {wy} percent' of spending")
    bands = list(big["self_worst_year_budget_share_by_band"].values())
    check(bands == sorted(bands, reverse=True) and "more for small governments than large ones" in body, "'more for small governments' needs the worst-year share to fall with size")
    check(vol["premium_share_covered"] > 0.75 and vol["cv_judgments_covered"] >= vol["cv_judgments_self"] * 0.9 and "mostly a steady premium" in body,
          "'mostly a steady premium ... as lumpy as anyone's' needs covered bills mostly premium and covered judgments as lumpy as self-insured")
    # big governments
    county_ceiling = big["ceilings"]["county"]
    others = [c["largest_covered_pop"] for k, c in big["ceilings"].items() if k != "county"]
    check(county_ceiling["largest_covered"] == "County of Albany" and county_ceiling["n_above"] == county_ceiling["n_above_self"]
          and all(c["n_above"] == c["n_above_self"] for c in big["ceilings"].values()) and max(others) < county_ceiling["largest_covered_pop"]
          and near(body, "larger than Albany County", "312,000") and "larger than the biggest of its kind that buys coverage" in body,
          "big-government sentence: nothing covered above each type's largest covered peer (Albany County, about 312,000, for counties)")
    check(near(body, "about " + share_words(big["share_of_liability_dollars_above_ceilings"]), "liability dollars"),
          f"big-government share must read 'about {share_words(big['share_of_liability_dollars_above_ceilings'])}'")
    # statewide order of magnitude and named figures
    vals = sw["liability_as_booked"] + sw["liability_net_flagged"]
    check(all(200e6 <= v <= 900e6 for v in vals) and near(body, "several hundred million dollars", "outside New York City"),
          f"'several hundred million dollars' must hold for FY2022-24 as booked and net of flagged lines ({[round(v / 1e6) for v in vals]})")
    check(near(body, r"about \$1 billion", "injury and property-damage"), "NYC: about $1 billion of injury and property-damage claims (FY2024 tort, $1.04B)")
    check(near(body, r"\$43 million", "Nassau", 200) and "lawsuit judgments and settlements" in body, "Nassau: $43 million in lawsuit judgments and settlements")
    nassau = RAW_ACFR / "nassau_2024.txt"
    if nassau.exists():
        check("Suits and Damages" in nassau.read_text() and "42.9 million" in nassau.read_text(), "Nassau ACFR no longer shows $42.9M of suits and damages")
    roster = CROSSWALKS / "ny_pool_rosters.csv"
    if roster.exists():
        with roster.open(encoding="utf-8") as f:
            n_gp = sum(1 for r in csv.DictReader(f) if re.match(r"(County|City|Town|Village) of ", r.get("entity_name", "")))
        check(900 <= n_gp < 1000 and "nearly a thousand" in body, f"NYMIR: roster has {n_gp} general-purpose subscribers; prose must say 'nearly a thousand'")
    check(near(body, r"\$750,000", "NYMIR") and "passing the rest to its own insurers" in body, "NYMIR's $750,000 retention, described as its own retention before its reinsurers")
    check(near(body, "Vallejo", r"\$500,000") and near(body, "Vallejo", r"\$2\.5 million", 400) and near(body, r"\$392,000", r"\$2\.4 million")
          and near(body, "working paper", "Vallejo", 300) and "market-based" in body, "Vallejo retention, premium, working-paper label, and Clark's 'market-based' required")
    check(near(body, "One risk-pool expert", "100,000", 200) and "Schwartz" in body, "Schwartz: the 100,000 line is one expert's estimate")
    check("mixed together" not in content and "rescue the hypothesis" not in content and "no clear extra cost" not in content,
          "leftover framing from the old null result")
    check(near(body, "very weak", "2024 review", 80) and near(body, "cannot say how much", "nationally", 80), "the in-house evidence must carry its strength caveats")
    check("Counties spend less per resident" in body and all(
        ents["summary_by_class"]["county"][t]["median_cor_pc"] < min(ents["summary_by_class"][c][t]["median_cor_pc"] for c in ("city", "town", "village") if t in ents["summary_by_class"][c])
        for t in ("self", "covered")), "'Counties spend less per resident' needs county medians below the other classes on both sides")

    # ---- 3. prose MUST-NOT -------------------------------------------------
    banned = [r"statistically significant", r"\bsignificant\b", r"p-value", r"\bp\s*[<=]", r"\brobust\b", r"\bproves?\b", r"confidence interval",
              r"\bleverage\b", r"\bseamless\b", r"\bholistic\b", r"\bdelve\b", r"\bmoreover\b", r"\bfurthermore\b", r"\bunderscore", r"not just",
              r"\bSCOPING\b", r"\bTODO\b", r"\bFIXME\b", r"\bClaude\b", r"working title", r"\bpills?\b", r"coefficient of variation",
              r"only thing that moves", r"\b(drives|raises) (the bill|liability|cost)", r"police (sets|drives|raises)", r"\bAs it turns out\b"]
    for pat in banned:
        if re.search(pat, content, re.I):
            fail(f"banned phrase in content: /{pat}/")
    # client rule (Joe, 2026-10-10): agencies may be named from public data among peers; never as a client
    surfaces = [content, config, *[f.read_text() for f in COMPONENTS.glob("*.tsx")], (ASSETS / f"{SLUG}-methodology.md").read_text()]
    for p in surfaces:
        if re.search(r"\bclients?\b|\bengagements?\b", p, re.I):
            fail("client rule: no surface may describe any agency as a client or mention an engagement")
    check(not re.search(r"\b(Mayor|Governor|Comptroller|Commissioner|Executive|Supervisor|Treasurer)\s+[A-Z][a-z]+", body),
          "policy-not-person: a titled official's name appears in the body")
    check(not re.search(r"\b(blame|mismanag|incompeten)", content, re.I), "policy-not-person: blame/mismanagement language")
    check(not re.search(r"self-insurance causes|causes? (higher|more)", body, re.I), "no causal claim from the cross-section")
    check("total per New Yorker" not in body, "never stack layers into a per-New-Yorker total")

    # ---- 4. style budgets ----------------------------------------------------
    check(words <= 1500, f"body words {words} > 1500 hard cap")  # raised from 1,200 by Joe, 2026-10-09
    if words > 800:
        warn(f"body words {words} > 800 target")
    check(body.count("—") == 0, f"em dashes in body: {body.count('—')}")
    check(meth.count("—") == 0, f"em dashes in Methodology/Sources: {meth.count('—')}")
    check(body.count(";") <= 3, f"semicolons in body: {body.count(';')} > 3")
    colon_setups = [m.group(0) for m in re.finditer(r"[a-z]{3,}: [A-Za-z][^\n]{0,80}", body) if not re.search(r"https?:|tell me:", m.group(0))]
    if colon_setups:
        warn(f"mid-sentence colon setups: {colon_setups[:4]}")
    tags = re.findall(r"<(sic-[a-z-]+)>", body)
    check(not re.search(r"<sic-[a-z-]+\s*/>", content), "self-closing embed tags are not allowed (use a pair)")
    comp = {"sic-core-chart": "SicCoreChart.tsx", "sic-volatility": "SicVolatility.tsx", "sic-transit-scatter": "SicTransitScatter.tsx"}
    for tg in set(tags):
        check(body.count(f"<{tg}></{tg}>") == 1, f"embed {tg} must appear exactly once as a pair")
        check((COMPONENTS / comp.get(tg, "missing")).exists(), f"no component file for {tg}")
    embeds_tsx = (ROOT / "src/content/embeds.tsx").read_text()
    for tg in set(tags):
        check(tg in embeds_tsx and tg in (ROOT / "src/content/embeds.static.tsx").read_text(), f"{tg} must be registered in embeds.tsx and embeds.static.tsx")
    for f in COMPONENTS.glob("*.tsx"):
        t = f.read_text()
        check("cor_pc_p90" not in t, f"{f.name}: a chart must not label the 90th-percentile year as the worst year")

    # ---- 5. downloads and card ---------------------------------------------
    for name in (f"{SLUG}-ny-panel.csv", f"{SLUG}-ntd-panel.csv", f"{SLUG}-treatment-labels.csv"):
        p = ASSETS / name
        if not p.exists():
            fail(f"download missing: {name}")
            continue
        first = p.open(encoding="utf-8").readline()
        check(first.startswith("#") and models["snapshot"] in first and "CC-BY-4.0" in first and "joe@group17a.com" in first and "—" not in first,
              f"{name}: attribution header line malformed")
    labels = ASSETS / f"{SLUG}-treatment-labels.csv"
    if labels.exists():
        with labels.open(encoding="utf-8") as f:
            f.readline()
            lrows = list(csv.DictReader(f))
        bad = [r.get("entity_name") or r.get("agency") for r in lrows if not (r.get("source_doc_url") or "").strip() or not (r.get("quote") or "").strip()]
        check(not bad, f"label rows without source_doc_url + quote: {bad[:5]}")
        check(any(r.get("compared_as") for r in lrows), "labels download must say how each government was compared")
    md = ASSETS / f"{SLUG}-methodology.md"
    check(md.exists(), "methodology download missing")
    if md.exists():
        mt = md.read_text()
        check(PRIMARY in mt or f"{prim['coef']}" in mt, "methodology download must state the current headline")
        check("population-weighted" not in mt and "placebo" not in mt, "methodology download: no population-weighting or never-run placebo claims")
        check("90th percentile" not in mt or "worst year" not in mt.split("90th percentile")[0][-80:], "methodology download: worst year is the maximum, not the 90th percentile")
    card_src = GIZMOS_TS.read_text()
    m = re.search(rf'slug: "{SLUG}".*?\n  \}},', card_src, re.S)
    check(m is not None, "card entry not found in gizmos.ts")
    if m:
        card = m.group(0)
        for fld in ("dek", "summary", "metaDescription"):
            v = re.search(rf'{fld}:\s*"([^"]*)"', card)
            if v:
                check("—" not in v.group(1), f"card {fld}: no em dash")
                check(not re.search(r"don't pay more|\bdrives\b|\braises\b|\bclient", v.group(1), re.I), f"card {fld}: no 'don't pay more', causal verbs, or client language")
        md_ = re.search(r'metaDescription:\s*"([^"]*)"', card)
        check(md_ is not None and len(md_.group(1)) <= 155, "metaDescription: <=155 chars")
        sm = re.search(r'summary:\s*"([^"]*)"', card)
        if sm and re.search(r"\d{2,3} New York governments", sm.group(1)):
            n = int(re.search(r"(\d{2,3}) New York governments", sm.group(1)).group(1))
            check(n == len(doc) and re.search(r"read", sm.group(1)), f"card summary: {n} must be the number read ({len(doc)}) and say 'read'")

    # ---- 6. intervention section ---------------------------------------------
    sec = re.search(r"## What a government could do(.*?)## Housekeeping", body, re.S)
    check(sec is not None, "intervention section missing")
    if sec:
        anchors = r"Vallejo|NYMIR|ClaimStat|Schwartz|Chicago|pool|retention|illustrative|cannot say|insurer|hospital"
        for sent in re.split(r"(?<=[.!?])\s+", sec.group(1).strip()):
            if re.search(r"\b(would|could|should)\b", sent) and not re.search(anchors, sent):
                fail(f"intervention sentence without an anchor or 'illustrative': {sent[:90]}")
    check("My firm, 17A" in body, "the 17A disclosure line is required next to the in-house capacity point")

    for w in warnings:
        print(f"WARN  {w}")
    for f_ in failures:
        print(f"FAIL  {f_}")
    print(f"{'FAIL' if failures else 'PASS'}: {len(failures)} failures, {len(warnings)} warnings, {words} body words")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
