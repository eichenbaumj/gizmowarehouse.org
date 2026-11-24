#!/usr/bin/env python3
"""The later-start sensitivity (D-65 point 3; D-94 "Step D's scope"; Joe's rulings of 2026-11-18 on R7): every
permit-dated phase started 1, 3 and 5 years later. Chosen stress sizes, not estimates of dating error. Reported beside the
primary result; it sets no one aside. Load and sales only.

Which rows move (Joe, R7: no size floor; respecting sourced bounds and known phases):
  * every row whose start is a permit-based year with no interval (date_basis first_generator_permit_plus_lag), crypto
    included because it counts in its state's anchoring;
  * a date question whose convention or late end is the row's permit-based year (first permit year plus one): that
    convention and that end move k years later;
  * a capacity split's rest, which arrives in its late case at the inventory's (permit-based) year: that year moves too.
Never moved: D-28 phased histories, operator-reported electricity, Epoch timelines, a capacity split's dated first
phase, a provisional (year-built) convention, and anything the evidence dates.

Sourced bounds: a shift that would put a start after an evidence end (an interval whose ends are both evidence, or an
operating-by or stated-start year in date_evidence.csv at or after the convention) stops at that end, and the site and
scenario are listed as incompatible. Nothing is clipped silently (D-61 section 6).

Recomputed: every state's factor in every configuration, every load, every first crossing, and the place test of
timing.py, against the UNSHIFTED reference.

Output: data/frozen/later_start_sensitivity.json (fingerprinted).
Run:  python3 -I pipeline/facilities/later_start.py [--corrections FILE]      (after timing.py)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import corrections as cx  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from pipeline.facilities import timing as tm  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
SHIFTS = (1, 3, 5)
PERMIT_LAG = 1
EVIDENCE_KINDS = ("operating_by", "stated_start")


def evidence_bounds(evidence: pd.DataFrame | None) -> dict:
    """fid -> the operating-by and stated-start years on file (D-61 5.1's kinds), a start cannot be later than these."""
    if evidence is None or not len(evidence):
        return {}
    col = "kind_d61" if "kind_d61" in evidence else "kind"
    e = evidence[evidence[col].isin(EVIDENCE_KINDS)]
    return {fid: sorted(int(y) for y in g.year) for fid, g in e.groupby("site")}


def _bound(fid: str, c: dict, conv, bounds: dict):
    if c.get("ends") == "evidence" and c.get("latest") is not None:
        return int(c["latest"])
    ys = [y for y in bounds.get(fid, []) if conv is None or y >= conv]
    return min(ys) if ys else None


def shifted(inp: px.Inputs, entries: list[dict], k: int, bounds: dict, st: str | None = None) -> tuple[list[dict], list[dict], dict]:
    """(the entries with every permit-dated phase k years later, the incompatible shifts, inventory years to patch)."""
    out, incompatible, patch = [], [], {}
    have = {c["fid"] for c in entries}
    for c in entries:
        c = dict(c)
        fid = c["fid"]
        r = inp.fac.loc[fid]
        pb = int(r.first_permit_year) + PERMIT_LAG if pd.notna(r.get("first_permit_year", np.nan)) else None
        if c["kind"] == "date" and pb is not None and c.get("convention_is") != "provisional":
            conv = c.get("convention") if isinstance(c.get("convention"), int) else None
            b = _bound(fid, c, conv, bounds)
            moved = False
            for key in ("convention", "latest"):
                v = c.get(key)
                if isinstance(v, int) and v == pb:
                    want = v + k
                    got = want if b is None else min(want, b)
                    if got != want:
                        incompatible.append({"site": fid, "shift": k, "field": key, "wanted": want, "held_at": got,
                                             "why": "a sourced bound: the start cannot be later than this (D-61 section 6)"})
                    c[key] = got
                    moved = True
            if moved and c.get("latest") is not None and c.get("earliest") is not None and c["earliest"] > c["latest"]:
                c["earliest"] = c["latest"]
        if c["kind"] == "capacity_split" and pb is not None and pd.notna(r.energized_year) and int(r.energized_year) == pb:
            patch[fid] = float(pb + k)
        out.append(c)
    f = inp.fac
    generic = f.index[(f.date_basis == cx.PERMIT_LABEL) & f.energized_year.notna() & f.mw_full_raw.notna()
                      & ((f.state == st) if st is not None else True)]
    for fid in generic:
        if fid in have or fid in inp.phases or bool(inp.fixed[fid]):
            continue
        out.append(tm.fixed_date(fid, int(f.energized_year[fid]) + k))
    return out, incompatible, patch


def with_years(inp: px.Inputs, patch: dict) -> px.Inputs:
    if not patch:
        return inp
    fac = inp.fac.copy()
    for fid, y in patch.items():
        fac.loc[fid, "energized_year"] = y
    return px.Inputs.build(fac, inp.fy, inp.units, inp.base, inp.regions, inp.names, inp.anchor, inp.phases,
                           inp.frozen_2024_mw, inp.fy_all)


def state_factor(run: tm.StateRun) -> float:
    S = run.cases[0]["S"]
    P = float(S.a_ref[S.permit].sum())
    M = S.m0 + float(S.a_ref[~S.permit].sum())
    return float(S.factor(np.array([M]), np.array([P]))[0])


def run(inp: px.Inputs, corrections: list[dict], shifts=SHIFTS, thetas=tm.THRESHOLDS, states=None,
        evidence: pd.DataFrame | None = None, ceiling: int = tm.CEILING) -> dict:
    entries = tm.timing_entries(corrections)
    bounds = evidence_bounds(evidence)
    states = sorted(states or set(inp.units.get_level_values("state")))
    out = {"shifts": {}, "primary": {}}
    for st in states:
        prim = tm.StateRun(inp, entries, st, screen=(0,))
        units = prim.cases[0]["S"].units
        for theta in thetas:
            for k in units:
                out["primary"][(f"{k[0]}:{k[1]}", theta)] = prim.evaluate(k, theta, ceiling)
        for s in shifts:
            ent, bad, patch = shifted(inp, [c for c in entries if inp.fac.state.get(c["fid"]) == st], s, bounds, st)
            inp_s = with_years(inp, patch)
            sr = tm.StateRun(inp_s, ent, st, screen=(0,), refs=dict(prim.refs))
            block = out["shifts"].setdefault(s, {"utilities": [], "incompatible": [], "factor_by_state": {}})
            block["incompatible"] += bad
            block["factor_by_state"][st] = {"primary": state_factor(prim), "shifted": state_factor(sr)}
            for theta in thetas:
                for k in units:
                    p = out["primary"][(f"{k[0]}:{k[1]}", theta)]
                    x = sr.evaluate(k, theta, ceiling)
                    block["utilities"].append({"utility": x["utility"], "theta": theta, "primary_keeps": p["keeps_its_place"],
                                               "keeps_under_the_later_start": x["keeps_its_place"], "status": x["status"],
                                               "failure": x["failure"], "range": x["range"],
                                               "weakened": bool(p["keeps_its_place"] is True and x["keeps_its_place"] is not True)})
    return out


def summary(res: dict) -> dict:
    s = {}
    for k, b in res["shifts"].items():
        u = pd.DataFrame(b["utilities"])
        s[f"{k}_years_later"] = {
            "utilities_whose_place_is_weakened": (u[u.weakened].groupby("theta").utility.apply(sorted).to_dict() if len(u) else {}),
            "incompatible_shifts": len(b["incompatible"])}
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrections", default=str(cx.CORRECTIONS))
    ap.add_argument("--states", default=None)
    args = ap.parse_args(argv)
    corrections = cx.load(args.corrections)
    inp = tm.load_rebuilt()
    ev = pd.read_csv(cx.DATE_EVIDENCE)
    res = run(inp, corrections, states=args.states.split(",") if args.states else None, evidence=ev)
    tp, up = FROZEN / "timing_place_test.json", FROZEN / "unknown_load_sites_and_affected_utilities.json"
    if not tp.exists() or not up.exists():
        raise SystemExit("run timing.py and build_inventory.py first: the primary's stress and unknown-load lists are carried here")
    stress = {(r["utility"], r["theta"]) for r in json.loads(tp.read_text())["utilities"] if r.get("unresolved_by_stress")}
    unknown = set(json.loads(up.read_text())["every_affected_utility"])
    for b in res["shifts"].values():
        for u in b["utilities"]:
            u["primary_unresolved_by_a_stress_scenario"] = (u["utility"], u["theta"]) in stress
            u["a_load_unknown_site_reaches_it"] = u["utility"] in unknown
    fp = cx.fingerprint([args.corrections, cx.DATE_EVIDENCE, cx.LOCATIONS, *cx.code_files(),
                         tm.INTERIM / "facilities.parquet", tm.INTERIM / "facility_year.parquet", tm.INTERIM / "state_anchor.parquet"],
                        shifts=list(SHIFTS), thresholds=list(tm.THRESHOLDS), size_floor=None, ceiling=tm.CEILING)
    doc = {"what_this_is": "The later-start sensitivity: every permit-dated phase 1, 3 and 5 years later (D-65 point 3, D-94, "
                           "Joe on R7). Chosen stress sizes, not estimates; reported beside the primary result; no set-aside.",
           "fingerprint": fp, "summary": summary(res),
           "utilities_unresolved_by_a_stress_scenario_in_the_primary": sorted(f"{u} at {t:.0%}" for u, t in stress),
           "unknown_load_affected_utilities": sorted(unknown),
           "shifts": {str(k): v for k, v in res["shifts"].items()}}
    (FROZEN / "later_start_sensitivity.json").write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps(doc["summary"], indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
