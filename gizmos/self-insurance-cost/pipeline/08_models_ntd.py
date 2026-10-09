"""Stage 08: transit (NTD) descriptive fits. No causal claim (SCOPING.md).

Outputs output/models_ntd.json: distribution of casualty-and-liability share by structure for labeled agencies,
per-structure OLS fits of log(C&L per revenue mile) on log(revenue miles) (slope, intercept shipped so the
browser does no math), and within-state contrasts for CA / WA / OH where transit pools coexist with
self-insured big agencies. Unlabeled agencies are described but never attributed a structure.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

import config

SELF = {"self_insured", "self_insured_with_excess"}
COVERED = {"pool", "commercial"}


def main(argv: list[str] | None = None) -> int:
    a = pd.read_parquet(config.NTD_PANEL_PARQUET)
    a = a[np.isfinite(a["cl_per_vrm"]) & (a["vrm"] > 0) & (a["cl_expense"] >= 0)]
    a = a.sort_values(["ntd_id", "fy"])
    dm = (a.groupby("ntd_id", as_index=False)
          .agg(agency=("agency", "last"), state=("state", "last"), structure=("structure", "last"), label_source=("label_source", "last"),
               cl_share=("cl_share", "mean"), cl_per_vrm=("cl_per_vrm", "mean"), vrm=("vrm", "mean"),
               total_opex=("total_opex", "mean"), n=("fy", "count")))
    dm["bin"] = dm["structure"].map(lambda s: "self" if s in SELF else "covered" if s in COVERED else "unknown")
    out = {"n_agencies": int(len(dm)), "n_labeled": int((dm.label_source == "document").sum()),
           "years": config.NTD_YEARS, "by_structure": {}, "fits": {}, "within_state": {}}
    for b, g in dm.groupby("bin"):
        out["by_structure"][b] = {"n": int(len(g)), "cl_share_median": round(float(g.cl_share.median()), 4),
                                  "cl_share_p25": round(float(g.cl_share.quantile(.25)), 4), "cl_share_p75": round(float(g.cl_share.quantile(.75)), 4),
                                  "cl_per_vrm_median": round(float(g.cl_per_vrm.median()), 3)}
    for b, g in dm[dm.bin != "unknown"].groupby("bin"):
        if len(g) >= 5:
            d = g.copy(); d["ly"] = np.log(d.cl_per_vrm + 1e-6); d["lx"] = np.log(d.vrm)
            m = smf.ols("ly ~ lx", data=d).fit()
            out["fits"][b] = {"slope": round(float(m.params["lx"]), 4), "intercept": round(float(m.params["Intercept"]), 4), "n": int(m.nobs)}
    # size-adjusted gap: log cl_per_vrm on log vrm + self indicator, labeled only
    lab = dm[dm.bin != "unknown"].copy()
    if lab.bin.nunique() == 2 and len(lab) >= 10:
        lab["ly"] = np.log(lab.cl_per_vrm + 1e-6); lab["lx"] = np.log(lab.vrm); lab["self"] = (lab.bin == "self").astype(int)
        m = smf.ols("ly ~ self + lx + I(lx**2)", data=lab).fit(cov_type="HC1")
        b, se = m.params["self"], m.bse["self"]
        out["size_adjusted_ratio"] = {"coef": round(float(np.exp(b)), 3), "lo": round(float(np.exp(b - 1.96 * se)), 3),
                                      "hi": round(float(np.exp(b + 1.96 * se)), 3), "n": int(m.nobs),
                                      "note": "descriptive; structure is nearly collinear with size across states"}
    for st in ("CA", "WA", "OH"):
        g = dm[dm.state == st]
        out["within_state"][st] = {b: {"n": int(len(h)), "cl_per_vrm_median": round(float(h.cl_per_vrm.median()), 3),
                                       "cl_share_median": round(float(h.cl_share.median()), 4)} for b, h in g.groupby("bin")}
    config.MODELS_NTD_JSON.write_text(json.dumps(out, indent=1))
    print(f"  ntd: {out['n_agencies']} agencies, {out['n_labeled']} labeled; by structure {out['by_structure']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
