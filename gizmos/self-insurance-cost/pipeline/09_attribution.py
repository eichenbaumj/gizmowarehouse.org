"""Stage 09: how much of the raw gap is size, services, place, and how much is left over.

Oaxaca–Blinder decomposition of the difference in mean log(1 + liability cost of risk per resident) between
self-insured and covered entities, pooled coefficients, covariates grouped: size (log pop, log pop^2),
service mix (police share, capital share, b-fund share), place (class, region). The unexplained
residual is reported as the CEILING on what insurance structure could explain (SCOPING.md). Bootstrap
(county clusters) gives low/central/high for every component. Group-level only; nothing per entity.
Uses the same sample rules as stage 07 (document labels first, signature second).
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm

import config

sys.path.insert(0, str(config.PIPELINE_DIR))
import importlib
m07 = importlib.import_module("07_models_ny")

GROUPS = {"size": ["lpop", "lpop2"], "service mix": ["police_share", "capital_share", "b_fund_share"]}
RNG = np.random.default_rng(7)
B = 500


def design(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    X = pd.DataFrame({"lpop": np.log(d["pop_mean"]), "police_share": d["police_share"].fillna(0),
                      "capital_share": d["capital_share"].fillna(0), "b_fund_share": d["b_fund_share"].fillna(0)})
    X["lpop2"] = X["lpop"] ** 2
    place = pd.get_dummies(d["cls"].astype(str) + "|" + d["region"].astype(str), drop_first=True, dtype=float)
    X = pd.concat([X, place], axis=1)
    groups = dict(GROUPS); groups["place"] = list(place.columns)
    return sm.add_constant(X), groups


def decompose(d: pd.DataFrame) -> dict:
    y = np.log1p(d["cor_liab_pc_mean_w"].values)
    X, groups = design(d)
    self_ = (d["treat"] == "self").values
    beta = sm.OLS(y, X).fit().params  # pooled coefficients
    xa, xb = X[self_].mean(), X[~self_].mean()
    raw = float(y[self_].mean() - y[~self_].mean())
    explained = {g: float(sum((xa[c] - xb[c]) * beta[c] for c in cols if c in beta)) for g, cols in groups.items()}
    expl_total = sum(explained.values())
    return {"raw_gap_log": raw, "explained": explained, "unexplained_log": raw - expl_total}


def main(argv: list[str] | None = None) -> int:
    ent = pd.read_parquet(config.LABELS_INFERRED_PARQUET)
    ent["region"] = ent["county"].map(m07.region_of)
    ent["treat"] = ent.apply(m07.treat_of, axis=1)
    base = m07.usable(ent)
    base = base[base["label_source"] == "document"].copy()
    base["cor_liab_pc_mean_w"] = base.groupby("cls")["cor_liab_pc_mean"].transform(m07.winsor)
    if (base.treat == "self").sum() < 10:
        config.ATTRIBUTION_JSON.write_text(json.dumps({"note": "fewer than 10 self-insured entities; no decomposition"}))
        print("  attribution skipped (too few self-insured)")
        return 0
    central = decompose(base)
    counties = base["county"].unique()
    boots = []
    for _ in range(B):
        pick = RNG.choice(counties, size=len(counties), replace=True)
        bs = pd.concat([base[base.county == c] for c in pick])
        if bs.treat.nunique() == 2 and (bs.treat == "self").sum() >= 5:
            try:
                boots.append(decompose(bs))
            except Exception:  # noqa: BLE001
                pass

    def band(get):
        v = np.array([get(b) for b in boots])
        return [round(float(np.percentile(v, 2.5)), 3), round(float(get(central)), 3), round(float(np.percentile(v, 97.5)), 3)]

    out = {
        "outcome": "log(1 + cost of risk per resident, 2024$, 2015-2024 mean)",
        "n_self": int((base.treat == "self").sum()), "n_covered": int((base.treat == "covered").sum()),
        "raw_gap_ratio": band(lambda b: np.exp(b["raw_gap_log"])),
        "components_ratio": {g: band(lambda b, g=g: np.exp(b["explained"][g])) for g in central["explained"]},
        "unexplained_ratio": band(lambda b: np.exp(b["unexplained_log"])),
        "share_of_gap_unexplained": band(lambda b: b["unexplained_log"] / b["raw_gap_log"] if abs(b["raw_gap_log"]) > 1e-6 else 0.0),
        "bootstrap_reps": len(boots),
        "note": "pooled-coefficient Oaxaca-Blinder; the unexplained part is the ceiling on what structure could explain, not an estimate of it",
    }
    config.ATTRIBUTION_JSON.write_text(json.dumps(out, indent=1))
    print(f"  attribution: raw ratio {out['raw_gap_ratio']}, unexplained ratio {out['unexplained_ratio']}, share unexplained {out['share_of_gap_unexplained']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
