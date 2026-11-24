#!/usr/bin/env python3
"""Turn one round 3 workflow result into pipeline/facilities/verified/batch_r3_<k>.json.

Input: a JSON file holding what pipeline/facilities/workflows/date_sites_r3.js
returns, a list of {k, lookup: {items}, verify: {results}}.

The rule this script enforces (docs/DECISIONS.md, D-15): only what the
verification layer confirmed on a page it opened goes into the fields the
inventory reads. Everything the lookup pass claimed but could not be confirmed
is kept under "lead" for a later retry and is ignored by apply_verified.py.

  * verified_year with a non-directory source and confidence high or medium
    -> energized_year, energized_year_source_url, year_confidence, year_basis,
       year_evidence_quote
  * verified_not_yet_operating with a non-directory source dated 2025 or later
    -> operating_status "not_yet_operating", status_source_url, status_as_of
  * anything else -> no year, no status
  * loads and serving utilities are never taken from round 3
  * round 3 never drops a site from the inventory

Run:  python3 -I pipeline/facilities/write_r3_batches.py data/interim/r3/<result>.json
          [--prefix batch_r3bb_] [--k 100:199]
      --prefix  file-name prefix. Later files overwrite earlier ones in apply_verified.py, which
                reads them in name order, so a second retry must sort after the first:
                batch_r3_ < batch_r3b_ < batch_r3bb_ < batch_r3c_ (county, gap-fill) < batch_r3s_ (sample).
      --k       write only batches whose number is in this range, for a result that mixes
                retry batches (100-199) with sample batches (200 and up).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.facilities.apply_verified import BLOCKED_DOMAINS, domain  # noqa: E402

VER = ROOT / "pipeline" / "facilities" / "verified"


def ok_source(url) -> bool:
    return bool(domain(url)) and domain(url) not in BLOCKED_DOMAINS


def dated_2025_or_later(page_date) -> bool:
    """A status page must carry a real date. 'Undated live page' does not count."""
    return bool(re.match(r"20(2[5-9]|[3-9]\d)(-\d\d){0,2}$", str(page_date or "").strip()))


def record(item: dict, v: dict | None) -> dict:
    r = {
        "fid": item["fid"], "group": "big", "round": 3, "is_data_center": True,
        "site_name": item.get("site_name"), "operator": item.get("operator"), "state": item.get("state"),
        "energized_year": None, "energized_year_source_url": None, "year_confidence": None,
        "year_basis": None, "year_evidence_quote": None, "year_site_match": None,
        "operating_status": None, "status_source_url": None, "status_confidence": None, "status_as_of": None,
        "load_mw_2025": None, "load_basis": None, "load_source_url": None,
        "serving_utility": None, "utility_source_url": None, "utility_confidence": None,
        "verification": "no claim to verify" if v is None else v.get("comment"),
    }
    verdict = (v or {}).get("verdict")
    if verdict == "verified_year" and v.get("year") is not None and ok_source(v.get("source_url")) \
            and v.get("confidence") in ("high", "medium"):
        r.update(energized_year=int(v["year"]), energized_year_source_url=v["source_url"],
                 year_confidence=v["confidence"], year_basis=v.get("basis"),
                 year_evidence_quote=v.get("quote"), year_site_match=v.get("site_match"))
    elif verdict == "verified_not_yet_operating" and ok_source(v.get("source_url")) \
            and dated_2025_or_later(v.get("page_date")):
        r.update(operating_status="not_yet_operating", status_source_url=v["source_url"],
                 status_confidence=v.get("confidence") or "medium", status_as_of=v.get("page_date"),
                 year_evidence_quote=v.get("quote"), year_site_match=v.get("site_match"))
    # What the lookup pass said, kept for a retry. Not read by apply_verified.py.
    claimed = {k: item.get(k) for k in ("energized_year", "energized_year_source_url", "year_confidence", "year_basis",
                                         "year_evidence_quote", "operating_status", "status_source_url",
                                         "other_urls", "phases", "notes") if item.get(k) not in (None, [], "")}
    if r["energized_year"] is None and r["operating_status"] is None:
        claimed["unverified"] = True
    r["lead"] = claimed
    return r


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    prefix = sys.argv[sys.argv.index("--prefix") + 1] if "--prefix" in sys.argv else "batch_r3_"
    if "--prefix" in sys.argv:
        args.remove(prefix)
    k_lo, k_hi = 0, 10**9
    if "--k" in sys.argv:
        span = sys.argv[sys.argv.index("--k") + 1]
        args.remove(span)
        k_lo, k_hi = (int(x) for x in span.split(":"))
    res = [b for b in json.loads(Path(args[0]).read_text()) if k_lo <= b["k"] <= k_hi]
    tally = {"sites": 0, "year": 0, "not_yet_operating": 0, "open": 0}
    for b in res:
        if not b.get("lookup"):
            print(f"batch {b['k']}: lookup agent returned nothing; no file written")
            continue
        verdicts = {v["fid"]: v for v in ((b.get("verify") or {}).get("results") or [])}
        recs = [record(i, verdicts.get(i["fid"])) for i in b["lookup"]["items"]]
        (VER / f"{prefix}{b['k']}.json").write_text(json.dumps(recs, indent=1, ensure_ascii=False) + "\n")
        y = sum(r["energized_year"] is not None for r in recs)
        n = sum(r["operating_status"] == "not_yet_operating" for r in recs)
        tally["sites"] += len(recs); tally["year"] += y; tally["not_yet_operating"] += n; tally["open"] += len(recs) - y - n
        print(f"batch {b['k']}: {len(recs)} sites, {y} with a verified year, {n} verified not yet operating")
    print(tally)
    return 0


if __name__ == "__main__":
    sys.exit(main())
