#!/usr/bin/env python3
"""Step D's independent checks on the rebuilt inventory (design note section 4; Joe's rulings in its addendum).
Load and sales only. Writes data/frozen/step_d_check.json and exits 1 on anything unexplained.

  reproduce   after `apply_verified.py --no-pass-records` and `build_inventory.py --no-step-d`: every inventory file
              must equal the snapshot of 2026-11-14 exactly (the claim "with no corrections the rebuild reproduces the
              frozen inventory").
  reference   after the corrected build: every utility whose exact reference is defined in the reference attribution
              must show that place and first crossing at 2% on the rebuilt inventory as built. The reference attribution
              is docs/gate1/expansion-test-2026-11-19-s18.json, the exact attribution rerun on 2026-11-19 on the
              corrections in force (66 entries, pipeline/facilities/verified/pass_c_corrections_s17.json) by
              pipeline/facilities/pass_c_exact_s18.py. Until 2026-11-19 the reference was
              docs/gate1/expansion-test-2026-11-18-s17.json, built on an earlier state of that corrections file.
              Legitimate differences, each traced to a named site: a coordinate correction (the pass never modelled
              location), a map-placed site the rerun moved (Joe, R5), a convention entered after the reference run (the
              corrections in force against the corrections file the reference attribution was built on), a utility a
              LOAD UNKNOWN site reaches (compared through timing.py's enumerated reference instead of the frame), a load
              within 1e-9 of a threshold.
              Also: every batch_c site the corrections do not assign or reopen is on its snapshot utility.

Run:  python3 -I pipeline/facilities/step_d_check.py reproduce
      python3 -I pipeline/facilities/step_d_check.py reference [--corrections FILE]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import corrections as cx  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

INTERIM = ROOT / "data" / "interim"
FROZEN = ROOT / "data" / "frozen"
SNAPSHOT = INTERIM / "snapshot-2026-11-14"
EXACT = ROOT / "docs" / "gate1" / "expansion-test-2026-11-19-s18.json"     # the reference attribution (s18, 2026-11-19)
# The corrections file the reference attribution was built on: the s18 run read this file with its 66 entries, the
# corrections in force. A correction that differs from this file's entry was entered after the reference run.
REFERENCE_CORRECTIONS = cx.VER / "pass_c_corrections_s17.json"
INVENTORY_FILES = ("facilities.parquet", "facility_year.parquet", "utility_year_dose.parquet", "state_anchor.parquet",
                   "state_load_by_year.parquet", "epoch_gaps.parquet")
MAP_KINDS = ("unique", "smallest_polygon", "next_larger_load_feasible", "fallback_largest_flagged")


def reproduce(snapshot: Path = SNAPSHOT, interim: Path = INTERIM) -> dict:
    out = {}
    for name in INVENTORY_FILES:
        a, b = snapshot / name, interim / name
        if not a.exists():
            out[name] = "missing from the snapshot"
            continue
        x, y = pd.read_parquet(a), pd.read_parquet(b)
        try:
            pd.testing.assert_frame_equal(x, y, check_exact=True)
            out[name] = "identical"
        except AssertionError as e:
            out[name] = f"DIFFERS: {str(e)[:300]}"
    return out


def places(fac: pd.DataFrame, fy: pd.DataFrame, theta: float = 0.02) -> dict:
    """Each utility's place and as-built first crossing on an inventory, as pass_c_exact names them."""
    _, _, _, units, base, regions = asg.load_inputs()
    t, m, _ = asg.evaluate(fac, fy, units, base, regions, thresholds=(theta,))
    th = f"{theta:.0%}"
    out = {}
    for k in units:
        c = t.at[k, f"as_built_{th}"]
        out[f"{int(k[0])}:{k[1]}"] = {"place": px.place(c, t.at[k, "max_share_as_built"]),
                                     "crossing": "never" if pd.isna(c) else str(int(c)),
                                     "margin": _margin(m["as_built"].loc[k].values, float(base.get(k, np.nan)), theta)}
    return out


def _margin(gwh, base_k, theta) -> float:
    """Smallest relative distance of any year's load share from the threshold (rounding can matter below 1e-9)."""
    if not (base_k > 0):
        return float("inf")
    return float(np.min(np.abs(gwh / base_k - theta)) / theta)


def explained(rebuilt: pd.DataFrame, snap: pd.DataFrame, report: dict, corrections: list[dict], reference_corrections: list[dict],
              unknown: set) -> dict:
    """utility -> the named reasons a difference from the reference attribution is legitimate.

    `reference_corrections` is the corrections list the reference attribution was built on (REFERENCE_CORRECTIONS for
    the s18 reference); a correction in force that differs from its entry there was entered after the reference run."""
    why: dict[str, list[str]] = {}

    def add(st, utilities, reason):
        for u in utilities:
            why.setdefault(f"{int(u)}:{st}", []).append(reason)

    for fid in report.get("locations_corrected", {}):
        st = rebuilt.state[fid]
        us = set(asg.candidates(rebuilt.utility_candidates[fid])) | set(asg.candidates(snap.utility_candidates.get(fid)))
        add(st, us, f"{fid}: coordinate corrected to a parcel centroid (Joe, R8)")
    both = rebuilt.index.intersection(snap.index)
    moved = [f for f in both if snap.utility_assign[f] in MAP_KINDS and rebuilt.utility_assign[f] in MAP_KINDS
             and not (pd.isna(snap.utility_id_eia[f]) and pd.isna(rebuilt.utility_id_eia[f]))
             and snap.utility_id_eia[f] != rebuilt.utility_id_eia[f]]
    for f in moved:
        add(rebuilt.state[f], [u for u in (snap.utility_id_eia[f], rebuilt.utility_id_eia[f]) if pd.notna(u)],
            f"{f}: moved by the map rerun (Joe, R5)")
    key = lambda c: (c["fid"], c["kind"])  # noqa: E731
    old = {key(c): {k: v for k, v in c.items() if k != "why"} for c in reference_corrections}
    for c in corrections:
        if old.get(key(c)) != {k: v for k, v in c.items() if k != "why"}:
            st = rebuilt.state.get(c["fid"])
            add(st, [u for u, s in {k for k in _units_in(rebuilt, st)}], f"{c['fid']}: a correction entered after the reference run")
    for u in unknown:
        why.setdefault(u, []).append("a LOAD UNKNOWN site reaches it: compared through the enumerated reference (Joe, R2)")
    return {"by_utility": why, "moved_by_the_map": moved}


def _units_in(fac, st):
    return {(int(u), st) for u in fac.utility_id_eia[fac.state == st].dropna().unique()} | {
        (int(u), st) for s in fac.utility_candidates[fac.state == st].dropna() for u in asg.candidates(s)}


def reference_check(corrections_path: Path) -> dict:
    exact = json.loads(EXACT.read_text())["exact"]
    fac = pd.read_parquet(INTERIM / "facilities.parquet").set_index("fid")
    fy = pd.read_parquet(INTERIM / "facility_year.parquet")
    fy = fy[~fy.crypto][["fid"] + asg.KEY + ["year", "mw"]]
    snap = pd.read_parquet(SNAPSHOT / "facilities.parquet").set_index("fid")
    report = json.loads((FROZEN / "inventory_report.json").read_text()).get("step_d", {})
    unknown = set(json.loads((FROZEN / "unknown_load_sites_and_affected_utilities.json").read_text())["every_affected_utility"])
    timing = {r["utility"]: r for r in json.loads((FROZEN / "timing_place_test.json").read_text())["utilities"]
              if abs(r["theta"] - 0.02) < 1e-12}
    corrections = cx.load(corrections_path)
    ex = explained(fac, snap, report, corrections, json.loads(REFERENCE_CORRECTIONS.read_text()), unknown)
    got = places(fac, fy)
    rows, unexplained = [], []
    for st, s in exact.items():
        for u, rec in s["utilities"].items():
            ref = rec["reference"]
            if not ref["defined"]:
                continue
            if u in unknown:
                t = timing.get(u, {}).get("reference", {})
                mine = {"place": t.get("place"), "crossing": t.get("crossing"), "margin": float("inf"), "via": "timing.py"}
            else:
                mine = {**got.get(u, {"place": None, "crossing": None, "margin": float("inf")}), "via": "the rebuilt frame"}
            same = mine["place"] == ref["place"] and str(mine["crossing"]) == str(ref["crossing"])
            if same:
                continue
            reasons = list(ex["by_utility"].get(u, []))
            if mine["margin"] < 1e-9:
                reasons.append("a load within 1e-9 of the threshold")
            r = {"utility": u, "reference": {"place": ref["place"], "crossing": ref["crossing"]}, "rebuilt": mine,
                 "explained_by": reasons}
            rows.append(r)
            if not reasons:
                unexplained.append(u)
    # batch_c records the corrections neither assign nor reopen: on their snapshot utility.
    skip = set(cx.withdrawn_fids()) | cx.reopened_fids(corrections)
    assigned = {c["fid"] for c in corrections if c["kind"] in ("assign", "reopen")}
    off = []
    for p in sorted(glob.glob(str(cx.VER / "batch_c_*.json"))):
        for r in json.loads(Path(p).read_text()):
            f = r["fid"]
            if f in skip or f in assigned or f not in fac.index or f not in snap.index:
                continue
            a, b = snap.utility_id_eia[f], fac.utility_id_eia[f]
            if not ((pd.isna(a) and pd.isna(b)) or a == b) and f not in report.get("locations_corrected", {}):
                off.append({"site": f, "snapshot_utility": a, "rebuilt_utility": b})
    return {"reference_attribution": {"file": str(EXACT.relative_to(ROOT)),
                                      "built_on_corrections": str(REFERENCE_CORRECTIONS.relative_to(ROOT)),
                                      "what": "the exact attribution rerun on 2026-11-19 on the corrections in force (s18); "
                                              "each difference's `reference` is that attribution's place and first crossing at 2%"},
            "differences": rows, "unexplained": unexplained, "moved_by_the_map": ex["moved_by_the_map"],
            "batch_c_sites_off_their_snapshot_utility": off}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("reproduce", "reference"))
    ap.add_argument("--corrections", default=str(cx.CORRECTIONS))
    args = ap.parse_args(argv)
    if not SNAPSHOT.exists():
        raise SystemExit(f"{SNAPSHOT} is missing; snapshot data/interim before any rebuild")
    if args.what == "reproduce":
        res = {"reproduce": reproduce()}
        bad = [k for k, v in res["reproduce"].items() if v != "identical"]
    else:
        res = {"reference": reference_check(Path(args.corrections))}
        bad = res["reference"]["unexplained"] + [x["site"] for x in res["reference"]["batch_c_sites_off_their_snapshot_utility"]]
    res["fingerprint"] = cx.fingerprint([args.corrections, EXACT, *cx.code_files(), *[INTERIM / n for n in INVENTORY_FILES],
                                         *[SNAPSHOT / n for n in INVENTORY_FILES]], check=args.what)
    path = FROZEN / f"step_d_check_{args.what}.json"
    path.write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "fingerprint"}, indent=1, default=str)[:4000])
    if bad:
        print(f"STOP: {len(bad)} unexplained: {bad[:20]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
