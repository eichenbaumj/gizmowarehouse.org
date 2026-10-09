"""Stage 04e: compile the hand-read transit risk notes (raw/acfr_ntd/labels_*.csv) into
crosswalks/ntd_treatment_labels.csv. Same normalization as 04b; ok and note_not_found rows kept
(the latter as 'unknown'); rows without an NTD id are kept for the download but cannot join the panel."""

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
    m = re.search(r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|M)?", s, re.I)
    if not m:
        return ""
    v = float(m.group(1).replace(",", ""))
    if m.group(2):
        v *= 1e6
    return str(int(v))


def main(argv: list[str] | None = None) -> int:
    frames = []
    for f in sorted(glob.glob(str(config.RAW_DIR / "acfr_ntd" / "labels_*_*.csv"))):
        d = pd.read_csv(f, dtype=str).fillna("")
        if "structure" not in d.columns:
            continue
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d = d[d["status"].isin(["ok", "note_not_found"])]
    out = pd.DataFrame({
        "ntd_id": d["ntd_id"].map(lambda s: s.zfill(5) if s.strip() else ""),
        "agency": d["agency"], "fiscal_year": d["fiscal_year"],
        "structure": d["structure"].str.strip().str.lower().map(lambda s: MAP.get(s.split()[0] if s else "", "unknown")),
        "pool_name": d.get("pool_name", ""), "captive": d.get("captive", ""),
        "sir_per_occurrence": d["sir_per_occurrence"].map(dollars), "excess_limit": d["excess_limit"].map(dollars),
        "liability_claims_paid_latest_fy": d["liability_claims_paid_latest_fy"].map(dollars),
        "source_doc_url": d["pdf_url"], "source_page": d["page_hint"], "quote": d["quote"], "status": d["status"],
        "labeled_on": config.SNAPSHOT_DATE,
    })
    out.loc[out["status"] == "note_not_found", "structure"] = "unknown"
    nn = (out["status"] == "note_not_found") & (out["quote"].str.strip() == "")
    out.loc[nn, "quote"] = "(the audited statements contain no risk-management note covering the transit operation)"
    out = out.drop_duplicates(subset=["ntd_id", "agency"], keep="last")
    out.to_csv(config.NTD_LABELS_CSV, index=False)
    print(f"  wrote {config.NTD_LABELS_CSV.name}: {len(out)} rows; {out['structure'].value_counts().to_dict()}; with ntd_id {(out['ntd_id'] != '').sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
