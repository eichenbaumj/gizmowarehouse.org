"""A brute-force evaluator for the dependency adapter (docs/gate1/dependency-adapter-brief-2026-11-18.md, section 7.1).

Load and sales only. No price or revenue column is read, no availability mask on disk is referred to, nothing under
data/ is opened and nothing is written. Written from sections 1 to 5 of the brief, apart from the adapter (which this
file never imports and was never seen by its author).

What it does, for one made-up state:

* It lists every question of the state and every setting of each, itself, from the corrections and the inventory
  (brief 4.3: every question the pass lists, not only kept ones). It calls `pass_c_expand._apply_fields` on a copy to
  read the corrected assignment, candidates and size of each site, `assignment.resolved` and `assignment.candidates`
  to tell unresolved sites, and `pass_c_expand._date_values` and `_capacity_values` for the lists of years.
* It enumerates the full product of every question's settings and realises each configuration through
  `pass_c_expand.scratch_state` and `assignment.evaluate`, the way `_realize` in tests/test_pass_c_expand.py does.
* From the realised configurations alone it works out which utilities each question reaches (two configurations that
  differ only in that question give the utility a different no-anchoring load in some year: brief 4.1 and 7.1),
  whether each question moves the state's 2024 anchoring (brief 4.2), and which utilities cross the host threshold in
  some configuration in either reading.
* The state's 2024 anchoring totals of each configuration (measured side and permit side) are computed here, by this
  file's own arithmetic, from the configuration's rebuilt inventory (see `_anchoring`). They are checked against the
  factor `scratch_state` returns, so that a difference between this file's reading and the module's is a failure and
  not a silent disagreement.

It never calls `pass_c_expand._sites`, `joint_check`, `_factor_range` or anything in `pass_c_exact.py`.

Readings this file makes where the brief does not settle a point (each is marked where it is used):

* R1. Two loads are "different" when they differ by more than 1e-9 GWh plus one part in 1e12. The no-anchoring
  reading of a permit-based site is its scaled load divided by the factor, and when another question moves the factor
  that quotient can differ from the raw load in the last binary place. Real differences in the made-up states are at
  least a third of a megawatt-year (about 2.9 GWh). The same tolerance is used in `violations`.
* R2. A site's 2024 contribution "differs" between two settings when the two numbers are not exactly equal (the
  conservative reading: any difference at all moves anchoring). A contribution that is not a finite number makes the
  answer None (unknown). The state totals in `violations` are compared with a tolerance of 1e-12 TWh, since they are
  sums in a fixed order of numbers that are exactly equal when no contribution changed.
* R3. An assignment question is listed for an unresolved site that is on a utility after the corrections and carries
  load in some panel year in some setting of its own date and capacity questions, as the module's docstring
  describes the joint check's questions. Its settings are the utility it is on, then each candidate, then off the panel
  (None). An unresolved site with load, candidates and no current utility is refused in words, as the pass refuses it.
"""
from __future__ import annotations

import dataclasses
import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

YEARS = list(asg.YEARS)                    # 2001 to 2025
ANCHOR_YEAR = 2024
GWH_PER_MW_YEAR = 8.76
RAMP = 3                                   # buildout.RAMP_YEARS: a third in the start year, two thirds, then full
OPEN_BELOW = YEARS[0] - RAMP + 1           # a start this early is at full load in 2001
# Rows measured rather than scaled, as Inputs.build reads them: Epoch's timeline, or one of these size bases.
MEASURED_BASIS = ("verified_public_figure", "operator_reported_energy")
LOAD_ABS_TOL, LOAD_REL_TOL = 1e-9, 1e-12   # reading R1
TWH_TOL = 1e-12                            # reading R2, for state totals only
FACTOR_CHECK_TOL = 1e-9


# ---- this file's own load arithmetic -------------------------------------------------------------------------------

def ramp(mw_full: float, start: float, year: int) -> float:
    """A three-year linear ramp: (age + 1) / 3 of full load at age 0 and 1, full from age 2; nothing before the start."""
    age = year - start
    if age < 0:
        return 0.0
    return float(mw_full) * min(1.0, (age + 1) / RAMP)


def phased(mw_full: float, steps: list, year: int) -> float:
    """Dated steps, each a cumulative share of full load; each step's increment ramps like a new site."""
    total, prev = 0.0, 0.0
    for y, share in steps:
        total += ramp(mw_full * (share - prev), y, year)
        prev = share
    return total


def mw_in(history: tuple, raw: float, year: int) -> float:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return 0.0
    if history[0] == "never":
        return 0.0
    if history[0] == "ramp":
        return ramp(raw, history[1], year)
    if history[0] == "phases":
        return phased(raw, history[1], year)
    raise ValueError(f"no load arithmetic here for a {history[0]} history")


def _is_fixed(r) -> bool:
    return r.src == "epoch" or r.load_history == "operator_reported_energy"


def _is_measured(r) -> bool:
    return r.src == "epoch" or r.mw_basis in MEASURED_BASIS


def _frozen_history(inp, fid: str) -> tuple:
    """The inventory's own history of a rebuildable row: verified phases first, else a ramp from its year, else none."""
    if fid in inp.phases:
        return ("phases", [(float(y), float(s)) for y, s in inp.phases[fid]])
    y = inp.fac.energized_year[fid]
    return ("ramp", float(y)) if pd.notna(y) else ("never",)


def _history(inp, c, fid: str, date_value=None, cap_value=None) -> tuple:
    """The site's history under one setting of its own date and capacity questions, read from the module docstring's
    rules (date intervals and capacity splits), not from Correction.history.

    A date setting is a start year or "never". A capacity setting is "early", "late" or the year the rest arrives.
    """
    if c is None:
        return _frozen_history(inp, fid)
    if c.not_a_site:
        return ("never",)
    if c.phases:
        return ("phases", [(float(y), float(s)) for y, s in c.phases])
    if not c.date and not c.split:
        return _frozen_history(inp, fid)
    if c.date:
        if date_value == "never":
            return ("never",)
        first = float(date_value)
    else:
        first = float(c.split["first_phase_year"])
    if not c.split:
        return ("ramp", first)
    rest_earliest = c.split.get("rest_earliest")
    if cap_value == px.EARLY:
        # The early case: the rest comes with the first phase, but not before rest_earliest when that is given.
        rest = first if rest_earliest is None else max(first, float(rest_earliest))
    elif cap_value == px.LATE:
        rest = max(first, float(c.inventory_year))       # the late case: the rest at the inventory's year
    else:
        rest = max(first, float(cap_value))              # a year the rest may arrive in, never before the first phase
    if c.split.get("first_share") is None:
        return ("ramp", rest)                            # the whole row arrives with the rest
    if rest == first:
        return ("ramp", first)
    return ("phases", [(first, float(c.split["first_share"])), (rest, 1.0)])


# ---- questions ------------------------------------------------------------------------------------------------------

def list_questions(inp, corr: dict, st: str) -> list[tuple]:
    """Every question of the state in a fixed order: [((fid, question), [settings]), ...].

    Site by site in inventory order; for each site its assignment question, then date, then capacity.
    """
    units = inp.units[inp.units.get_level_values("state") == st]
    fac = inp.fac[inp.fac.state == st].copy()
    measured = inp.measured.reindex(fac.index).copy()
    for fid, c in corr.items():
        if c.state == st:
            px._apply_fields(fac, measured, c)
    ercot = {k for k in units if inp.regions.get(k) == asg.ERCOT_REGION}
    res = asg.resolved(fac, ercot)
    out = []
    for fid in fac.index:
        c = corr.get(fid)
        r = fac.loc[fid]
        fixed = _is_fixed(inp.fac.loc[fid])
        crypto = bool(r.is_crypto) if "is_crypto" in fac.columns else False
        own = c.questions() if (c is not None and not fixed) else []
        vals = [px._date_values(c) if q == "date" else px._capacity_values(c) for q in own]
        # Does the site carry load in some panel year in some setting of its own questions (reading R3)?
        if fixed:
            has_load = (not (c is not None and c.not_a_site)) and bool((inp.fy.fid == fid).any())
        elif crypto or pd.isna(r.mw_full_raw) or (c is not None and c.not_a_site):
            has_load = False
        elif c is None or not own:
            h = _history(inp, c, fid)
            has_load = h[0] != "never" and pd.notna(r.energized_year) and any(mw_in(h, r.mw_full_raw, y) > 0 for y in YEARS)
        else:
            has_load = False
            for combo in itertools.product(*vals):
                s = dict(zip(own, combo))
                h = _history(inp, c, fid, s.get("date"), s.get("capacity"))
                if any(mw_in(h, r.mw_full_raw, y) > 0 for y in YEARS):
                    has_load = True
                    break
        u0 = int(r.utility_id_eia) if pd.notna(r.utility_id_eia) else None
        cands = asg.candidates(r.utility_candidates)
        if not res[fid] and u0 is None and has_load and cands:
            raise ValueError(f"{fid} in {st} is unresolved, carries load and has candidates ({r.utility_candidates}) but is "
                             f"on no utility; the pass refuses such a row and so does this evaluator")
        if not res[fid] and u0 is not None and has_load:
            out.append(((fid, "assignment"), list(dict.fromkeys([u0] + cands)) + [None]))
        for q, v in zip(own, vals):
            out.append(((fid, q), list(v)))
    return out


# ---- realising one configuration ------------------------------------------------------------------------------------

def realise(inp, corr: dict, st: str, config: dict):
    """One configuration through scratch_state and assignment.evaluate, as tests/test_pass_c_expand.py's _realize does.

    Returns (rebuilt inventory, rebuilt site-years, factor, {reading: utility-by-year GWh}).
    """
    corr = dict(corr)
    choice = {}
    for (fid, q), v in config.items():
        if q == "assignment":
            c = corr.get(fid) or px.Correction(fid=fid, state=st, inventory_year=inp.fac.energized_year[fid])
            corr[fid] = dataclasses.replace(c, assign=px.OFF if v is None else (int(v), st), reopen=None, narrow=None,
                                            widen=None)
        else:
            choice[(fid, q)] = v
    fac, fy, factor = px.scratch_state(inp, corr, st, choice)
    u = inp.units[inp.units.get_level_values("state") == st]
    _, m, _ = asg.evaluate(fac, fy, u, inp.base.reindex(u), inp.regions.reindex(u), thresholds=(0.02,))
    return fac, fy, factor, {r: m[r] for r in ("as_built", "no_anchoring")}


# ---- the 2024 anchoring totals, by this file's arithmetic ------------------------------------------------------------

def _fixed_measured_twh(inp, st: str) -> float:
    """The part of the state's measured 2024 total that the rebuild does not recompute (Epoch timelines and
    operator-reported histories): the state's measured total on file less what this file computes for the rebuildable
    measured rows of the frozen inventory. This is the quantity Inputs.build calls measured_fixed, worked out again."""
    on_file = float(inp.anchor.epoch_twh[st]) if ("epoch_twh" in inp.anchor and st in inp.anchor.index) else 0.0
    rebuildable = 0.0
    for fid, r in inp.fac[inp.fac.state == st].iterrows():
        if _is_measured(r) and not _is_fixed(r):
            if pd.notna(r.energized_year) and pd.notna(r.mw_full_raw):
                rebuildable += mw_in(_frozen_history(inp, fid), r.mw_full_raw, ANCHOR_YEAR) * GWH_PER_MW_YEAR / 1000.0
    return on_file - rebuildable


def _anchoring(inp, corr: dict, st: str, config: dict, fac_rebuilt: pd.DataFrame) -> tuple[dict, float, float]:
    """Each site's 2024 contribution (TWh) and the state's (measured, permit) totals in one configuration.

    A rebuildable row counts its 2024 load times 8.76 / 1000 when the rebuilt inventory gives it a year and a size,
    on the measured side if it is measured in the rebuilt inventory (Epoch, or a measured size basis) and on the
    permit side otherwise. Its load is this file's own reading of its history in the configuration. A fixed-history
    row (Epoch or operator-reported) is not rebuilt; its part is `_fixed_measured_twh`, less what any not_a_site
    correction takes out of it (the MW on file for that row in 2024). Where a site is (assignment, off the panel or
    not) does not enter: a site off the panel stays in its state's anchoring.
    """
    contrib = {}
    measured_twh = _fixed_measured_twh(inp, st)
    permit_twh = 0.0
    for fid in fac_rebuilt.index:
        r0 = inp.fac.loc[fid]
        c = corr.get(fid)
        if _is_fixed(r0):
            if c is not None and c.not_a_site:
                measured_twh -= inp.frozen_2024_mw[fid] * GWH_PER_MW_YEAR / 1000.0
            continue
        r = fac_rebuilt.loc[fid]
        h = _history(inp, c, fid, config.get((fid, "date")), config.get((fid, "capacity")))
        if pd.isna(r.energized_year) or pd.isna(r.mw_full_raw):
            a = 0.0
        else:
            a = mw_in(h, r.mw_full_raw, ANCHOR_YEAR) * GWH_PER_MW_YEAR / 1000.0
        contrib[fid] = a
        if _is_measured(r):
            measured_twh += a
        else:
            permit_twh += a
    return contrib, measured_twh, permit_twh


def own_factor(epri: float, measured_twh: float, permit_twh: float) -> float:
    """The state factor written out again from the module docstring: (EPRI less measured) over permit, held between
    0.2 and 3.0; 1 where the permit total is zero."""
    if permit_twh == 0:
        return 1.0
    raw = max(epri - measured_twh, 0.0) / permit_twh
    return min(max(raw, 0.2), 3.0)


def _check_site_loads(inp, corr, st, config, fac, fy, factor) -> None:
    """This file's reading of every rebuildable site's load must match the rows scratch_state built. A mismatch means
    the two readings of a history differ, and the anchoring arithmetic here cannot be trusted; it is raised."""
    by_site = fy.groupby(["fid", "year"]).mw.sum()
    for fid in fac.index:
        if _is_fixed(inp.fac.loc[fid]):
            continue
        r = fac.loc[fid]
        c = corr.get(fid)
        h = _history(inp, c, fid, config.get((fid, "date")), config.get((fid, "capacity")))
        if (h[0] == "never") != pd.isna(r.energized_year) and c is not None and (c.date or c.split or c.not_a_site):
            raise AssertionError(f"{fid}: this file reads its history as {h} but the rebuild gives year {r.energized_year}")
        if not bool(r.in_dose) or (bool(r.is_crypto) if "is_crypto" in fac.columns else False):
            continue
        scale = float(r.state_scale) if pd.notna(r.state_scale) else 1.0
        for y in YEARS:
            mine = mw_in(h, r.mw_full_raw, y) * scale
            theirs = float(by_site.get((fid, y), 0.0))
            if abs(mine - theirs) > 1e-9 + 1e-9 * abs(mine):
                raise AssertionError(f"{fid} {y}: this file computes {mine} MW, the rebuild carries {theirs} MW ({config})")


# ---- the brute force ------------------------------------------------------------------------------------------------

def _differs(a, b) -> bool:
    return abs(a - b) > LOAD_ABS_TOL + LOAD_REL_TOL * max(abs(a), abs(b))


def _unit_key(k) -> tuple:
    return (int(k[0]), str(k[1]))


def brute_force(inp, corrections: list[dict], st: str, theta: float = 0.02) -> dict:
    """Every configuration of every question of state `st`, realised; reaches, moves_anchoring and can_cross from them.

    Returns
      configurations   the number of configurations in the full product
      questions        [(fid, question), ...] in the order of the configuration keys
      settings         {(fid, question): [settings]} (an assignment's off-panel setting is None)
      units            [(utility_id_eia, state), ...]
      reaches          {(fid, question): {(utility_id_eia, state), ...}}            brief 4.1, by enumeration
      moves_anchoring  {(fid, question): True | False | None}                     brief 4.2, by enumeration
      can_cross        {(utility_id_eia, state), ...}                             the host threshold, either reading
      loads            {configuration key: {unit: {"as_built": [...], "no_anchoring": [...]}}}
      anchoring        {configuration key: (measured total, permit total)}        TWh, 2024
      contributions    {configuration key: {fid: TWh}}
      factor           {configuration key: the factor scratch_state used}
      near_ties        [(configuration key, unit, reading, year, load, threshold)] loads within 1e-6 of a threshold
    A configuration key is the tuple of settings in the order of `questions`.
    """
    # The corrections as given (a list of dicts), or already parsed (a dict of Correction, as parse_corrections gives).
    corr = corrections if isinstance(corrections, dict) else px.parse_corrections(corrections, inp)
    qlist = list_questions(inp, corr, st)
    questions = [k for k, _ in qlist]
    settings = {k: v for k, v in qlist}
    units = [_unit_key(k) for k in inp.units[inp.units.get_level_values("state") == st]]
    base = {k: inp.base.get(k, np.nan) for k in units}
    epri = float(inp.anchor.epri_twh.get(st, 0.0)) if "epri_twh" in inp.anchor else 0.0
    loads, anchoring, contributions, factors, near = {}, {}, {}, {}, []
    for combo in itertools.product(*(settings[q] for q in questions)):
        config = dict(zip(questions, combo))
        fac, fy, factor, m = realise(inp, corr, st, config)
        _check_site_loads(inp, corr, st, config, fac, fy, factor)
        contrib, meas, perm = _anchoring(inp, corr, st, config, fac)
        # The factor from this file's totals has to be the one the rebuild used (it snaps to the frozen factor within
        # 1e-12; a looser tolerance here covers that).
        mine = own_factor(epri, meas, perm)
        if abs(mine - factor) > FACTOR_CHECK_TOL * max(1.0, abs(factor)):
            raise AssertionError(f"{st} {config}: the factor from this file's totals is {mine}, the rebuild used {factor}")
        key = tuple(combo)
        loads[key] = {}
        for k in units:
            loads[key][k] = {}
            for reading in ("as_built", "no_anchoring"):
                v = [float(x) for x in m[reading].loc[k].reindex(YEARS).values]
                loads[key][k][reading] = v
                b = base[k]
                if pd.notna(b) and b > 0:
                    for th in (theta, asg.CLEAN_BELOW):
                        t = th * b
                        for y, x in zip(YEARS, v):
                            if abs(x - t) <= 1e-6 * t:
                                near.append((key, k, reading, y, x, t))
        anchoring[key] = (meas, perm)
        contributions[key] = contrib
        factors[key] = factor

    reaches, moves = {}, {}
    keys = list(loads)
    for i, q in enumerate(questions):
        groups: dict = {}
        for key in keys:
            groups.setdefault(key[:i] + key[i + 1:], []).append(key)
        hit, mv = set(), False
        unknown = False
        fid = q[0]
        for g in groups.values():
            first = g[0]
            for k in units:
                v0 = loads[first][k]["no_anchoring"]
                for other in g[1:]:
                    if any(_differs(a, b) for a, b in zip(v0, loads[other][k]["no_anchoring"])):
                        hit.add(k)
                        break
            vals = [contributions[key].get(fid, 0.0) for key in g]
            if any(not math.isfinite(x) for x in vals):
                unknown = True
            elif any(x != vals[0] for x in vals[1:]):              # reading R2: exact
                mv = True
        reaches[q] = hit
        moves[q] = None if unknown else mv

    can_cross = set()
    for k in units:
        b = base[k]
        if not (pd.notna(b) and b > 0):
            continue                                                 # no positive base: never a host
        t = theta * b
        if any(x >= t for key in keys for reading in ("as_built", "no_anchoring") for x in loads[key][k][reading]):
            can_cross.add(k)

    return {"configurations": len(keys), "questions": questions, "settings": settings, "units": units,
            "reaches": reaches, "moves_anchoring": moves, "can_cross": can_cross, "loads": loads,
            "anchoring": anchoring, "contributions": contributions, "factor": factors, "near_ties": near}


# ---- the guarantee of brief section 2 ---------------------------------------------------------------------------------

def _question_key(q) -> tuple:
    if isinstance(q, str):
        fid, name = q.rsplit(" ", 1)
        return (fid, name)
    return (q[0], q[1])


def _narrowed_key(u) -> tuple:
    if isinstance(u, str):
        uid, st = u.split(":")
        return (int(uid), st)
    return _unit_key(u)


def violations(result: dict, deferrable: set, narrowed: set) -> list:
    """Every breach of the guarantee in brief section 2 for the deferred questions of this result's state.

    For each deferrable question, every pair of configurations that differ only in it is checked: (a) every utility
    not in `narrowed` has the same load in every panel year in both readings, and (b) the state's 2024 anchoring
    totals, measured and permit, are the same. A deferrable question this state does not list is reported too, since
    nothing here can show it is harmless. Questions may be given as (fid, question) or "<fid> <question>"; utilities
    as (utility_id_eia, state) or "<utility_id_eia>:<state>".
    """
    out = []
    narrowed = {_narrowed_key(u) for u in narrowed}
    questions = result["questions"]
    keys = list(result["loads"])
    for q in sorted({_question_key(q) for q in deferrable}):
        if q not in questions:
            out.append({"question": q, "breach": "not a question of this state; it cannot be shown harmless here"})
            continue
        i = questions.index(q)
        groups: dict = {}
        for key in keys:
            groups.setdefault(key[:i] + key[i + 1:], []).append(key)
        for g in groups.values():
            first = g[0]
            for other in g[1:]:
                for k in result["units"]:
                    if k in narrowed:
                        continue
                    for reading in ("as_built", "no_anchoring"):
                        a, b = result["loads"][first][k][reading], result["loads"][other][k][reading]
                        for y, x0, x1 in zip(YEARS, a, b):
                            if _differs(x0, x1):
                                out.append({"question": q, "breach": "load", "unit": k, "reading": reading, "year": y,
                                            "configurations": (first, other), "loads": (x0, x1)})
                                break
                (m0, p0), (m1, p1) = result["anchoring"][first], result["anchoring"][other]
                if abs(m0 - m1) > TWH_TOL or abs(p0 - p1) > TWH_TOL:
                    out.append({"question": q, "breach": "anchoring", "configurations": (first, other),
                                "totals": ((m0, p0), (m1, p1))})
    return out


# ---- the permitted windows of brief 4.6, written out from the brief ---------------------------------------------------

def brief_windows() -> dict:
    """Each cohort g from 2011 to 2022: g-6 to g+3; the second estimate's long difference and its panel form."""
    out = {f"cohort_{g}": tuple(range(g - 6, g + 4)) for g in range(2011, 2023)}
    out["second_estimate_long_difference"] = (2008, 2009, 2010, 2023, 2024, 2025)
    out["second_estimate_panel"] = tuple(range(2005, 2026))
    return out


def windows_passed(mask: pd.DataFrame, unit: tuple, windows: dict | None = None) -> list[str]:
    """The windows a unit passes on a mask (columns utility_id_eia, state, year, usable): usable in every year of the
    window. A year missing from the mask is not usable, and a unit absent from the mask passes nothing."""
    windows = windows or brief_windows()
    u, s = _unit_key(unit)
    rows = mask[(mask.utility_id_eia.astype(int) == u) & (mask.state == s)]
    ok_years = {int(y) for y, f in zip(rows.year, rows.usable) if bool(f)}
    return [name for name, w in windows.items() if all(int(y) in ok_years for y in w)]
