"""Stage 06: agency × year (and × mode) transit panel with casualty-and-liability share.

Keeps full reporters and directly-operated service only (purchased transportation
carries liability inside the contractor's price). Joins the hand-labeled structure
file and the state tort-cap file when present; otherwise label_source = 'unknown'.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import config

NUM_OPEX = ["casualty_and_liability", "total", "fringe_benefits", "services", "purchased_transportation"]


def _load(name: str, ds: str) -> pd.DataFrame:
    p = config.RAW_NTD / f"{name}_{ds}.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} missing; run 05_fetch_ntd.py")
    return pd.DataFrame(json.loads(p.read_text()))


def main(argv: list[str] | None = None) -> int:
    opex = _load("opex_by_type", config.NTD_OPEX_BY_TYPE)
    svc = _load("service_by_mode", config.NTD_SERVICE_BY_MODE)
    for c in NUM_OPEX:
        opex[c] = pd.to_numeric(opex.get(c), errors="coerce")
    opex["fy"] = pd.to_numeric(opex["report_year"], errors="coerce").astype("Int64")
    opex = opex[opex["reporter_type"].str.startswith(config.NTD_FULL_REPORTER)
                & (opex["type_of_service"] == config.NTD_DIRECTLY_OPERATED)]
    # service: annual rows only (time_period == 'Annual Total'), directly operated
    svc["fy"] = pd.to_numeric(svc["report_year"], errors="coerce").astype("Int64")
    svc = svc[(svc["type_of_service"] == config.NTD_DIRECTLY_OPERATED)]
    if "time_period" in svc:
        annual = svc[svc["time_period"].str.contains("Annual", case=False, na=False)]
        if len(annual):
            svc = annual
    svc = svc.rename(columns={"_5_digit_ntd_id": "ntd_id"})
    for c in ("actual_vehicles_passenger_car_revenue_miles", "unlinked_passenger_trips_upt", "mode_voms",
              "service_area_population", "primary_uza_population"):
        svc[c] = pd.to_numeric(svc.get(c), errors="coerce")
    svc_mode = (svc.groupby(["ntd_id", "fy", "mode"], as_index=False)
                .agg(vrm=("actual_vehicles_passenger_car_revenue_miles", "sum"),
                     upt=("unlinked_passenger_trips_upt", "sum"),
                     mode_voms=("mode_voms", "max")))
    # agency × year × mode
    m = opex.merge(svc_mode, on=["ntd_id", "fy", "mode"], how="left")
    m = m.rename(columns={"casualty_and_liability": "cl_expense", "total": "total_opex"})
    m["cl_share"] = m["cl_expense"] / m["total_opex"]
    m["cl_per_vrm"] = m["cl_expense"] / m["vrm"]
    m["cl_per_1k_upt"] = m["cl_expense"] / (m["upt"] / 1000)
    # agency × year (all modes)
    a = (m.groupby(["ntd_id", "agency", "city", "state", "organization_type", "fy"], as_index=False)
         .agg(cl_expense=("cl_expense", "sum"), total_opex=("total_opex", "sum"),
              vrm=("vrm", "sum"), upt=("upt", "sum"),
              modes=("mode", lambda s: ",".join(sorted(set(s)))),
              primary_uza_population=("primary_uza_population", "first"),
              uza_name=("uza_name", "first")))
    a["cl_share"] = a["cl_expense"] / a["total_opex"]
    a["cl_per_vrm"] = a["cl_expense"] / a["vrm"]
    a["cl_per_1k_upt"] = a["cl_expense"] / (a["upt"] / 1000)
    a["primary_uza_population"] = pd.to_numeric(a["primary_uza_population"], errors="coerce")
    # labels
    a["structure"] = "unknown"
    a["label_source"] = "unknown"
    if config.NTD_LABELS_CSV.exists():
        lab = pd.read_csv(config.NTD_LABELS_CSV, dtype=str).fillna("")
        lab["ntd_id"] = lab["ntd_id"].str.zfill(5)
        a = a.drop(columns=["structure", "label_source"]).merge(
            lab[["ntd_id", "structure"]].drop_duplicates("ntd_id"), on="ntd_id", how="left")
        a["label_source"] = np.where(a["structure"].notna(), "document", "unknown")
        a["structure"] = a["structure"].fillna("unknown")
    if config.STATE_CAPS_CSV.exists():
        caps = pd.read_csv(config.STATE_CAPS_CSV, dtype=str).fillna("")
        a = a.merge(caps[["state", "cap_type", "cap_per_occurrence"]], on="state", how="left")
    a = a.dropna(subset=["cl_share"])
    a = a[np.isfinite(a["cl_share"])]
    a.to_parquet(config.NTD_PANEL_PARQUET, index=False)
    m.to_parquet(config.OUTPUT_DIR / "ntd_panel_by_mode.parquet", index=False)
    print(f"  wrote {config.NTD_PANEL_PARQUET.name}: {len(a):,} agency-years, {a['ntd_id'].nunique()} agencies; "
          f"by-mode rows {len(m):,}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
