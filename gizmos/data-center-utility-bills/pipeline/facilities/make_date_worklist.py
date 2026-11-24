#!/usr/bin/env python3
"""Round 3 worklist: large sites that still carry only a permit-based start year.

A site of 20 MW or more enters the treated-cohort analysis only with a start
year from a public source or from Epoch (docs/DECISIONS.md, D-10). This lists
every site that fails that rule today:

    in the load measure, not crypto, 20 MW or more, not an Epoch row,
    and no hand-verified year.

Sites are ranked by load and cut into tranches (one search-limited turn each),
so the largest are dated first if sources run out. Inside a tranche, batches
group sites by state, operator and county: one search about a campus then
serves several rows.

The checker is NOT shown our permit-based year or the permit year. Round 3
doubles as the measurement of how wrong permit-based years are, and a checker
who can see our guess will tend to find it.

The assignment of sites to tranches and batches is frozen the first time this
runs (pipeline/facilities/verified/r3_worklist.csv, committed). Later runs
only rebuild the per-batch input files from it, so applying one tranche never
reshuffles the next, and reports can still say "of the 222".

Each batch also carries a seeded random order, used to draw the five items
that are checked by hand against their cited source before a batch is applied.

Outputs (data/interim/r3/, not committed):
  in_batch_<k>.json   what a checker is given for batch k
  batches.json        per tranche, the batch numbers, sizes and spot-check order
Results: pipeline/facilities/verified/batch_r3_<k>.json (D-15 for the schema).

Run:  python3 -I pipeline/facilities/make_date_worklist.py
      python3 -I pipeline/facilities/make_date_worklist.py --retry
          builds batches 100 and up from sites already looked up whose year is
          still unsourced, carrying what earlier passes found as leads; results
          go to a new prefix each time, one that sorts after the last
          (batch_r3b_, then batch_r3bb_; see write_r3_batches.py).
      python3 -I pipeline/facilities/make_date_worklist.py --sample
          builds batches 200 and up from the 60-site random sample of smaller
          sites (verified/sample_worklist.csv, drawn in session 1 with a fixed
          seed and frozen) that still lack a sourced year; results go to
          batch_r3s_<k>.json. The sample is the only national read on how
          wrong permit years are for small sites.
"""
from __future__ import annotations

import glob
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import sources  # noqa: E402

MIN_MW = 20
TRANCHE_SIZE = 74      # about 2.5 web searches per site inside a 200-search turn
BATCHES_PER_TRANCHE = 8
SEED = 20261111
VER = ROOT / "pipeline" / "facilities" / "verified"


def needs_year(fac: pd.DataFrame) -> pd.DataFrame:
    """The D-10 worklist rule, in one place so the report can reuse it."""
    return fac[fac.in_dose & ~fac.is_crypto & (fac.mw_full >= MIN_MW) & (fac.src != "epoch")
               & ~fac.verified_fields.fillna("").str.contains("year")]


def prior_leads() -> dict[str, dict]:
    """What rounds 1 and 2 learned about a site without settling its year."""
    out: dict[str, dict] = {}
    for p in sorted(glob.glob(str(VER / "batch_*.json"))):
        if "_r3" in Path(p).name:
            continue
        for r in json.loads(Path(p).read_text()):
            lead = out.setdefault(r["fid"], {})
            if r.get("site_name"):
                lead["site_name_from_earlier_round"] = r["site_name"]
            if r.get("energized_year") is not None and r.get("energized_year_source_url"):
                lead["unconfirmed_year_lead"] = {"year": r["energized_year"],
                                                 "url": r["energized_year_source_url"],
                                                 "confidence_then": r.get("year_confidence")}
    return out


def freeze(work: pd.DataFrame) -> pd.DataFrame:
    """First run only: rank by load, cut into tranches, group batches by state and operator."""
    rows, k = [], 0
    for ti, t0 in enumerate(range(0, len(work), TRANCHE_SIZE)):
        chunk = work.iloc[t0:t0 + TRANCHE_SIZE].sort_values(["state", "operator", "county_name", "lat"])
        n = min(BATCHES_PER_TRANCHE, len(chunk))
        base, extra = divmod(len(chunk), n)  # balanced: sizes differ by at most one
        start = 0
        for j in range(n):
            size = base + (1 if j < extra else 0)
            for pos, r in enumerate(chunk.iloc[start:start + size].itertuples()):
                rows.append({"fid": r.fid, "state": r.state, "tranche": ti, "batch": k, "pos": pos,
                             "mw_at_worklist_time": round(float(r.mw_full), 1)})
            start += size
            k += 1
    return pd.DataFrame(rows)


def round3_leads() -> dict[str, dict]:
    """What the first round 3 pass found for a site without it surviving verification."""
    out: dict[str, dict] = {}
    for p in sorted(glob.glob(str(VER / "batch_r3_*.json")) + glob.glob(str(VER / "batch_r3b*.json"))):
        for r in json.loads(Path(p).read_text()):  # the retry's notes replace the first pass's
            out[r["fid"]] = {"site_name": r.get("site_name"), **(r.get("lead") or {}),
                             "what_the_verifier_found": r.get("verification")}
    return out


def main() -> int:
    retry = "--retry" in sys.argv
    sample = "--sample" in sys.argv
    fac = pd.read_parquet(ROOT / "data" / "interim" / "facilities.parquet")
    terr = gpd.read_file(ROOT / "data" / "raw" / "territories" / "retail_service_territories.geojson",
                         ignore_geometry=True)
    names = {str(k): v for k, v in zip(terr.ID.astype(str), terr.NAME)}
    bi = sources.load_bi().set_index("src_id")
    leads = prior_leads()
    reg_path = ROOT / "pipeline" / "facilities" / "leads" / "energystar_matches.csv"
    if reg_path.exists():  # EPA registry rows at the same address: a lead to corroborate, see match_energystar.py
        for r in pd.read_csv(reg_path).itertuples():
            leads.setdefault(r.fid, {})["epa_energy_star_registry_lead"] = {
                "row": f"{r.registry_name} | {r.registry_owner} | Year Constructed {r.year_constructed}",
                "url": r.source_url,
                "caution": "the building's year: can be decades early for a converted building, or a later phase"}
    rec_path = ROOT / "pipeline" / "facilities" / "leads" / "public_record_leads.csv"
    if rec_path.exists():  # assessor, permit-file and registry records that did not pass the rules: write_public_records_batch.py
        for r in pd.read_csv(rec_path).itertuples():
            leads.setdefault(r.fid, {})["government_record_lead"] = {
                "source": r.source, "record": r.record, "url": r.url,
                "caution": f"{r.caution} A lead, not a source: it needs a dated page that states the opening or the status."}
    open_now = set(needs_year(fac).fid)

    frozen_path = VER / "r3_worklist.csv"
    if not frozen_path.exists():
        work = needs_year(fac).sort_values(["mw_full", "fid"], ascending=[False, True]).reset_index(drop=True)
        freeze(work).to_csv(frozen_path, index=False)
    frozen = pd.read_csv(frozen_path)
    by_fid = fac.set_index("fid")

    def item(fid: str, extra: dict | None = None) -> dict:
        r = by_fid.loc[fid]
        b = bi.loc[fid] if fid in bi.index else None
        return {
            "fid": fid, "state": r.state,
            "county": r.county_name if isinstance(r.county_name, str) else "",
            "lat": round(float(r.lat), 5), "lon": round(float(r.lon), 5),
            "operator": r.operator if isinstance(r.operator, str) else "",
            "address": "" if b is None else b.address,
            "company_on_permit": "" if b is None else b.company,
            "our_load_mw": round(float(r.mw_full), 1) if pd.notna(r.mw_full) else None,
            "our_utility": names.get(str(int(r.utility_id_eia)), "") if pd.notna(r.utility_id_eia) else "",
            "utility_already_verified": "utility" in (r.verified_fields or ""),
            **leads.get(fid, {}), **(extra or {}),
        }

    out_dir = ROOT / "data" / "interim" / "r3"
    out_dir.mkdir(parents=True, exist_ok=True)

    def write_batch(k: int, items: list[dict]) -> dict:
        order = list(range(len(items)))
        random.Random(SEED + k).shuffle(order)
        (out_dir / f"in_batch_{k}.json").write_text(json.dumps({"batch": k, "items": items}, indent=1))
        return {"k": k, "n": len(items), "order": order}

    index: dict = {"tranches": [], "retry": [], "sample": []}
    for ti, t in frozen.groupby("tranche"):
        batches = []
        for k, b in t.groupby("batch"):
            fids = [f for f in b.sort_values("pos").fid if f in by_fid.index]
            batches.append(write_batch(int(k), [item(f) for f in fids]))
        index["tranches"].append(batches)
        print(f"tranche {ti}: batches {[b['k'] for b in batches]}, sizes {[b['n'] for b in batches]}, "
              f"still without a sourced year: {int(t.fid.isin(open_now).sum())} of {len(t)}")

    if retry:
        r3 = round3_leads()
        todo = frozen[frozen.fid.isin(open_now) & frozen.fid.isin(set(r3))].sort_values(["state", "batch", "pos"])
        size = -(-len(todo) // max(1, -(-len(todo) // 10))) if len(todo) else 1
        for j, i0 in enumerate(range(0, len(todo), size)):
            fids = list(todo.fid.iloc[i0:i0 + size])
            index["retry"].append(write_batch(100 + j, [item(f, {"round3_first_pass": r3[f]}) for f in fids]))
        print(f"retry: {len(todo)} sites looked up once and still unsourced, batches {[b['k'] for b in index['retry']]}")

    if sample:
        dated = set(fac[fac.verified_fields.fillna("").str.contains("year|status")].fid)
        sm = pd.read_csv(VER / "sample_worklist.csv")
        # Sample sites of 20 MW or more are also on the round 3 worklist; the retry covers those.
        todo = sm[sm.fid.isin(by_fid.index) & ~sm.fid.isin(dated) & ~sm.fid.isin(set(frozen.fid))].sort_values(["state", "fid"])
        size = 9
        for j, i0 in enumerate(range(0, len(todo), size)):
            fids = list(todo.fid.iloc[i0:i0 + size])
            index["sample"].append(write_batch(200 + j, [item(f) for f in fids]))
        both = int((sm.fid.isin(set(frozen.fid)) & sm.fid.isin(open_now)).sum())
        print(f"sample: {len(todo)} of {len(sm)} sample sites still without a sourced year and not on the "
              f"round 3 worklist ({both} more are, and sit in the retry), batches {[b['k'] for b in index['sample']]}")

    (out_dir / "batches.json").write_text(json.dumps(index, indent=1))
    print("worklist sites:", len(frozen), "| MW at worklist time:", round(float(frozen.mw_at_worklist_time.sum())),
          "| still without a sourced year:", int(frozen.fid.isin(open_now).sum()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
