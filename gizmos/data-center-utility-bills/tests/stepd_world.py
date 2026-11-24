"""Made-up inventories for the step D tests (no real data). Load and sales only.

`make(sites, base_mw, epri)` builds a pass_c_expand.Inputs from a list of site dicts:
  fid, state, mw (raw full load), year (energized year, or None), utility, assign (utility_assign, default "unique"),
  candidates (default the utility), date_basis (default the permit label), src (default "bi"), measured (default False),
  first_permit_year (default year - 1).
`base_mw` maps (utility, state) to the MW that is 2% of its base, so a utility crosses 2% when its load reaches it.
`epri` maps a state to its EPRI 2024 total in TWh; with None the factor is 1 (EPRI equal to the permit total).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import buildout  # noqa: E402
from pipeline.facilities import corrections as cx  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

YEARS = asg.YEARS


def make(sites: list[dict], base_mw: dict, epri: dict | None = None, phases: dict | None = None) -> px.Inputs:
    phases = phases or {}
    rows = []
    for s in sites:
        y = s.get("year")
        rows.append({"fid": s["fid"], "state": s["state"], "src": s.get("src", "bi"),
                     "load_history": "verified_phases" if s["fid"] in phases else "three_year_ramp",
                     "mw_basis": "verified_public_figure" if s.get("measured") else "generator_capacity_x_kappa",
                     "energized_year": np.nan if y is None else float(y), "mw_full_raw": float(s["mw"]),
                     "utility_id_eia": float(s["utility"]) if s.get("utility") is not None else np.nan,
                     "utility_assign": s.get("assign", "unique"),
                     "utility_candidates": s.get("candidates", str(s.get("utility"))),
                     "is_crypto": False, "date_basis": s.get("date_basis", cx.PERMIT_LABEL),
                     "first_permit_year": float(s.get("first_permit_year", (y - 1) if y is not None else np.nan)),
                     "load_unknown": bool(s.get("load_unknown", False)),
                     "date_inventory_year": s.get("date_inventory_year", np.nan)})
    fac = pd.DataFrame(rows).set_index("fid")
    measured = fac.mw_basis.eq("verified_public_figure") | fac.src.eq("epoch")
    states = sorted(fac.state.unique())
    a24 = {}
    for fid, r in fac.iterrows():
        h = ("phases", phases[fid]) if fid in phases else (("ramp", r.energized_year) if pd.notna(r.energized_year) else ("never",))
        a24[fid] = px.site_mw(h, r.mw_full_raw, px.ANCHOR_YEAR) * 8.76 / 1000.0 if pd.notna(r.energized_year) else 0.0
    a24 = pd.Series(a24)
    permit_twh = a24[~measured].groupby(fac.state[~measured]).sum().reindex(states).fillna(0.0)
    meas_twh = a24[measured].groupby(fac.state[measured]).sum().reindex(states).fillna(0.0)
    ep = pd.Series({st: (epri or {}).get(st, permit_twh[st] + meas_twh[st]) for st in states})
    factor = pd.Series({st: px._factor(ep[st], meas_twh[st], permit_twh[st]) for st in states})
    fac["state_scale"] = np.where(measured, 1.0, fac.state.map(factor))
    fac["mw_full"] = fac.mw_full_raw * fac.state_scale
    fac["in_dose"] = fac.energized_year.notna() & fac.utility_id_eia.notna()
    fy = []
    for fid, r in fac[fac.in_dose].iterrows():
        for y in YEARS:
            mw = buildout.phased_mw(r.mw_full, phases[fid], y) if fid in phases else buildout.ramp_mw(r.mw_full, r.energized_year, y)
            if mw > 0:
                fy.append((fid, int(r.utility_id_eia), r.state, y, mw))
    fy = pd.DataFrame(fy, columns=["fid"] + asg.KEY + ["year", "mw"])
    units = pd.MultiIndex.from_tuples(sorted(base_mw), names=asg.KEY)
    base = pd.Series([base_mw[k] * 8.76 / 0.02 for k in sorted(base_mw)], index=units)
    regions = pd.Series("West", index=units)
    names = pd.Series([f"U{k[0]}" for k in sorted(base_mw)], index=units)
    anchor = pd.DataFrame({"epri_twh": ep, "permit_twh": permit_twh, "epoch_twh": meas_twh, "factor": factor})
    return px.Inputs.build(fac, fy, units, base, regions, names, anchor, phases, frozen_2024_mw={})


def date(fid, earliest, latest, convention, ends="tested", never=False, **kw) -> dict:
    return {"fid": fid, "kind": "date", "earliest": earliest, "latest": latest, "never_is_possible": never,
            "convention": convention, "ends": ends, **kw}
