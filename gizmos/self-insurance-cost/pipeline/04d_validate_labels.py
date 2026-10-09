"""Stage 04d: agreement between the premium-only signature and the document labels.

Writes output/label_validation.json {n, accuracy, precision_self, recall_self, confusion, by_class}
and a markdown twin. 'self' = {self_insured, self_insured_with_excess}; 'covered' = {pool, commercial};
'mixed' and 'unknown' document labels are excluded from the agreement computation but counted.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

import config

SELF = {"self_insured", "self_insured_with_excess"}
COVERED = {"pool", "commercial"}


def main(argv: list[str] | None = None) -> int:
    ent = pd.read_parquet(config.LABELS_INFERRED_PARQUET)
    doc = ent[ent["label_source"] == "document"].copy()
    out = {"n_document": int(len(doc)), "n_entities": int(len(ent))}
    if len(doc) == 0:
        out.update({"accuracy": None, "note": "no document labels yet"})
    else:
        doc["doc_bin"] = doc["structure"].map(lambda s: "self" if s in SELF else "covered" if s in COVERED else "other")
        doc["sig_bin"] = doc["sig_structure"].map({"signature_self_insured": "self", "signature_insured": "covered"}).fillna("unknown")
        use = doc[doc["doc_bin"].isin(["self", "covered"]) & doc["sig_bin"].isin(["self", "covered"])]
        conf = pd.crosstab(use["doc_bin"], use["sig_bin"]).reindex(index=["self", "covered"], columns=["self", "covered"], fill_value=0)
        tp = int(conf.loc["self", "self"]); fn = int(conf.loc["self", "covered"]); fp = int(conf.loc["covered", "self"]); tn = int(conf.loc["covered", "covered"])
        n = tp + fn + fp + tn
        out.update({
            "n_compared": n,
            "accuracy": round((tp + tn) / n, 3) if n else None,
            "precision_self": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall_self": round(tp / (tp + fn), 3) if tp + fn else None,
            "confusion": {"doc_self_sig_self": tp, "doc_self_sig_covered": fn, "doc_covered_sig_self": fp, "doc_covered_sig_covered": tn},
            "excluded_other_or_unknown": int(len(doc) - n),
            "by_class": {c: round(((g["doc_bin"] == g["sig_bin"]).mean()), 3) for c, g in use.groupby("cls")},
            "disagreements": use[use["doc_bin"] != use["sig_bin"]][["cls", "entity_name", "structure", "sig_structure", "ins_pc_mean", "jc_pc_mean"]]
                               .round(1).to_dict(orient="records"),
            "contaminated_confirmed": doc[doc["jc_contaminated"]][["entity_name", "structure"]].to_dict(orient="records"),
        })
    config.LABEL_VALIDATION_JSON.write_text(json.dumps(out, indent=2))
    md = ["# Signature vs document labels", "", f"Entities: {out['n_entities']}, document-labeled: {out['n_document']}", ""]
    for k, v in out.items():
        if k not in ("disagreements", "contaminated_confirmed"):
            md.append(f"- **{k}**: {v}")
    if out.get("disagreements"):
        md += ["", "## Disagreements", ""] + [f"- {d}" for d in out["disagreements"]]
    (config.OUTPUT_DIR / "label_validation.md").write_text("\n".join(md) + "\n")
    print(f"  validation: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
