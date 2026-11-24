#!/usr/bin/env python3
"""Write the hand-verification worklist for the facility inventory.

Two groups, split into batches so several people (or agents) can work at once:

  big       every facility of 50 MW or more: confirm the serving utility, the
            year it began drawing power, and its load. These sites carry most
            of the load, so errors here move results.
  sample    a size-stratified random sample of smaller dated facilities, used
            only to measure how wrong the permit-based dates are.
  epoch     Epoch AI sites whose street address the Census geocoder could not
            place; they need coordinates before they can enter the inventory.

Verifiers never see price data. Output of verification goes to
pipeline/facilities/verified/batch_<k>.json and is committed.

Run:  python3 -I pipeline/facilities/make_verify_worklist.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import sources  # noqa: E402

N_BIG_BATCHES = 10
SAMPLE_PER_BATCH = 6
SEED = 20261111


def main() -> int:
    fac = pd.read_parquet(ROOT / "data" / "interim" / "facilities.parquet")
    terr = gpd.read_file(ROOT / "data" / "raw" / "territories" / "retail_service_territories.geojson",
                         ignore_geometry=True)
    names = {str(k): v for k, v in zip(terr.ID.astype(str), terr.NAME)}
    bi = sources.load_bi().set_index("src_id")

    def item(r, group):
        b = bi.loc[r.fid] if r.fid in bi.index else None
        cands = [c for c in str(r.utility_candidates or "").split(";") if c]
        return {
            "fid": r.fid, "group": group, "source": r.src, "state": r.state,
            "lat": round(float(r.lat), 5), "lon": round(float(r.lon), 5),
            "operator": (r.operator if isinstance(r.operator, str) else "") or "",
            "name": next((v for v in (getattr(r, "name", None), getattr(r, "Name", None)) if isinstance(v, str) and v), ""),
            "address": "" if b is None else b.address,
            "company_on_permit": "" if b is None else b.company,
            "first_generator_permit_year": None if pd.isna(r.first_permit_year) else int(r.first_permit_year),
            "our_energized_year": None if pd.isna(r.energized_year) else int(r.energized_year),
            "our_load_mw": None if pd.isna(r.mw_full) else round(float(r.mw_full), 1),
            "our_utility": names.get(str(int(r.utility_id_eia)) if pd.notna(r.utility_id_eia) else "", ""),
            "our_utility_id_eia": None if pd.isna(r.utility_id_eia) else int(r.utility_id_eia),
            "how_assigned": r.utility_assign,
            "other_candidate_utilities": [names.get(c, c) for c in cands
                                          if pd.isna(r.utility_id_eia) or c != str(int(r.utility_id_eia))],
        }

    big = fac[fac.verify_by_hand].sort_values("mw_full", ascending=False)
    small = fac[(~fac.verify_by_hand) & fac.in_dose & (fac.src == "bi")].copy()
    small["size_bin"] = pd.cut(small.mw_full, [0, 5, 20, 50], labels=["<5", "5-20", "20-50"])
    per_bin = N_BIG_BATCHES * SAMPLE_PER_BATCH // 3
    sample = pd.concat([g.sample(min(per_bin, len(g)), random_state=SEED)
                        for _, g in small.groupby("size_bin", observed=True)])

    batches: list[list[dict]] = [[] for _ in range(N_BIG_BATCHES)]
    for i, r in enumerate(big.itertuples()):
        batches[i % N_BIG_BATCHES].append(item(r, "big"))
    for i, r in enumerate(sample.sample(frac=1, random_state=SEED).itertuples()):
        batches[i % N_BIG_BATCHES].append(item(r, "sample"))

    ep_sites, _ = sources.load_epoch()
    ep_us = ep_sites[ep_sites.Country == "United States"]
    placed = set(fac[fac.src == "epoch"].fid.str.split(":", n=1).str[1])
    missing = ep_us[~ep_us.Name.isin(placed)]
    epoch_items = [{"fid": f"epoch:{r.Name}", "group": "epoch", "name": r.Name,
                    "owner": str(r.Owner), "address_as_published": "" if pd.isna(r.Address) else r.Address,
                    "current_power_mw": None if pd.isna(r._3) else float(r._3)}
                   for r in missing.itertuples()]
    half = (len(epoch_items) + 1) // 2
    batches += [epoch_items[:half], epoch_items[half:]]

    out = ROOT / "data" / "interim" / "verify_worklist.json"
    out.write_text(json.dumps({"batches": batches}, indent=1))
    (ROOT / "pipeline" / "facilities" / "verified").mkdir(exist_ok=True)
    print("batches:", [len(b) for b in batches], "| big", len(big), "sample", len(sample), "epoch", len(epoch_items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
