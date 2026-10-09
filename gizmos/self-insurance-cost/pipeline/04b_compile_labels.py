"""Stage 04b: compile the hand-read risk-management notes into crosswalks/ny_treatment_labels.csv.

Inputs: raw/acfr/worklist_results_*.csv (one row per entity: the arrangement as read from the GASB 10
note, the SIR / excess figures, a verbatim quote, the document URL and page). The reading itself is done
in-session (Claude + human review), never by an API call in the pipeline. This stage only normalizes:
  structure  <- first token of general_liability_arrangement, mapped to config.VALID_STRUCTURES
  sir_per_occurrence <- first dollar figure in the SIR column (blank if 'not stated')
  entity_name <- "County of X" / "City of X" to match the OSC panel
Rows whose structure is 'unclear' are kept with structure=unknown so the validation stage can count them.
"""

from __future__ import annotations

import glob
import re
import sys

import pandas as pd

import config

MAP = {"self_insured": "self_insured", "self_insured_with_excess": "self_insured_with_excess", "pool": "pool",
       "commercial": "commercial", "mixed": "mixed", "unclear": "unknown"}


def dollars(s) -> str:
    if not isinstance(s, str):
        return ""
    if re.search(r"not stated|none|n/a", s, re.I) and not re.search(r"\$\s?[\d,]+", s):
        return ""
    m = re.search(r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|M)?", s, re.I)
    if not m:
        return ""
    v = float(m.group(1).replace(",", ""))
    if m.group(2):
        v *= 1e6
    return str(int(v))


def main(argv: list[str] | None = None) -> int:
    rows = []
    for f in sorted(glob.glob(str(config.RAW_ACFR / "worklist_results_*.csv"))):
        d = pd.read_csv(f, dtype=str).fillna("")
        kind = "county" if "county" in d.columns and "entity" not in d.columns else "city" if "city" in d.columns else "entity"
        for _, r in d.iterrows():
            if kind == "entity":
                full = r["entity"].strip()
                cls_ = "town" if full.startswith("Town of") else "village" if full.startswith("Village of") else "other"
            else:
                name = r["county"] if kind == "county" else r["city"]
                full = f"{'County' if kind == 'county' else 'City'} of {name}"
                cls_ = kind
            arr = r["general_liability_arrangement"].strip()
            tok = re.split(r"[\s(]", arr, maxsplit=1)[0].lower()
            structure = MAP.get(tok, "unknown")
            pool = ""
            m = re.search(r"\b(NYMIR|NYSIR|PERMA|reciprocal)\b", arr, re.I)
            if m and structure in ("pool", "mixed"):
                pool = m.group(1)
            rows.append({
                "entity_name": full,
                "cls": cls_, "fiscal_year": r["fiscal_year"], "structure": structure,
                "arrangement_text": arr, "pool_name": pool,
                "sir_per_occurrence": dollars(r["sir_per_occurrence"]), "excess_limit": dollars(r["excess_limit"]),
                "self_funded_health": r.get("has_self_funded_health_plan", "").split(" ")[0].lower(),
                "wc_self_insured": r.get("has_wc_self_insurance_plan", "").split(" ")[0].lower(),
                "liability_claims_paid_latest_fy": dollars(r.get("liability_claims_paid_latest_fy", "")),
                "source_doc_url": r["pdf_url"], "source_page": r.get("page_hint", ""), "quote": r["quote"],
                "status": r["status"], "labeled_on": config.SNAPSHOT_DATE, "confidence": "high" if structure not in ("unknown", "mixed") else "low",
            })
    out = pd.DataFrame(rows)
    # a statement that was read but has no risk note stays in the core as 'unknown' (counted, not compared)
    out = out[out["status"].isin(["ok", "note_not_found"])]
    out.loc[out["status"] == "note_not_found", "structure"] = "unknown"
    nn = (out["status"] == "note_not_found") & (out["quote"].str.strip() == "")
    out.loc[nn, "quote"] = "(the audited statements contain no risk-management or insurance note)"
    out.to_csv(config.NY_LABELS_CSV, index=False)
    print(f"  wrote {config.NY_LABELS_CSV.name}: {len(out)} rows; {out['structure'].value_counts().to_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
