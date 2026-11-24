#!/usr/bin/env python3
"""The design side of the runs that change the facility inventory and so move event dates: E4(a) the slow path, E4(b)
anchoring off, E7 the redraw of permit-dated start years in both directions, and the later-start sensitivity on outcomes
at +1, +3 and +5 years (PREANALYSIS.md, "Other outcomes and robustness", G-a, E4 and E7; "Other runs", the later-start
sensitivity and its "On outcomes").

Load and sales only. Nothing here reads a price, opens data/blind or touches the availability files, and nothing is
written under data/interim: every alternative inventory is a frame in memory.

What each run produces
----------------------
For an alternative inventory (a set of rows whose load history changes, with each state's factor recomputed or set to
one): each host's event year (its first crossing on the alternative inventory), its group, comparison eligibility re-read
on the alternative inventory through power_simulation.design (the function the main design uses), and then G-a: the
host's window re-centred on the new date and the design's matching rule applied at the new reference year through
design.build_with_rules (the ten closest in size in the host's region that year among comparison-eligible units, the
ownership rules over the new window, usability over the new window, the support rule).

The roster rule (plan, E4 "The roster"; the later-start sensitivity "On outcomes"): the hosts are the set's. A host is
retained wherever it has a crossing in 2011 to 2022 on the alternative inventory and a full supported window. A host whose
group changes (its crossing leaves 2011 to 2022, or it never crosses) is left out and named; a host the window or support
rules drop is named with build_with_rules' own reason. No event date is invented, no host is substituted, no original
event year is kept for a host whose crossing moved, and no fixed-match version is built.

How the alternative inventory is computed (the agent's reading of "reuse the existing functions")
-------------------------------------------------------------------------------------------------
A row's load in a year is pass_c_expand.site_mw on its history (a three-year ramp from a start year, dated phases, or
never), which mirrors build_inventory.site_mw's ramp and phase branches; the slow path is buildout.slow_mw. A state's
factor is pass_c_expand._factor (build_inventory.state_anchor's arithmetic for one state: EPRI's 2024 total less measured
load, over the permit-based 2024 total, clipped to [0.2, 3]) on the state's row of state_anchor.parquet with the changed
rows' 2024 load moved in or out of the permit-based or measured total, the method dating_sensitivity.factor_after_shift
uses. build_inventory.state_anchor itself cannot be called here: it needs Epoch's dated timeline and the operator-reported
energy from data/raw (not readable in this pass), and its site_mw has no slow-path branch. On the unchanged inventory the
arithmetic returns every state's factor in state_anchor.parquet exactly, and the dose frame built from the site-years
(dose_frame, build_inventory.main's own aggregation, which is not a function there) returns utility_year_dose.parquet
exactly; main() checks both on the real inventory and records the check.

Rows whose history is fixed (Epoch's timeline, operator-reported electricity) never move in any run here.

Provisional
-----------
The design stands as of 2026-11-18 and the plan is a DRAFT, not frozen. E7's error distribution is fixed "at the freeze";
everything this module writes is provisional.

E7 for every cohort utility (added 2026-11-20, session 25, under Joe's words of that day: "Complete E7's already
specified quantity-side checks for both the headline set and every cohort utility")
------------------------------------------------------------------------------------------------------------------
main runs E7 on each set of E7_SETS through the same functions (e7_all_sets, e7_run, e7_draw, e7_summary), with the same rows
redrawn (e7_rows), the same errors (load_errors), seed E7_SEED and E7_DRAWS draws a direction, each set with its own
reference design and roster (set_reference, from design.split and design.build_with_rules for that set). The headline set's
block keeps its key "E7" and its fields; every cohort utility's block is "E7_every_cohort_utility" and names its set.
The time box applies to each set on its own; a run that does not fit is labelled a partial timing run.

Run:  python3 -I pipeline/analysis/inventory_runs.py [--e7-draws N] [--e7-budget-minutes M]
      [--e7-budget-minutes-every-cohort-utility M2] [--e7-timing-draws K]
      writes data/frozen/inventory_run_designs.json (quantity-only). A full E7 on both sets needs a budget high enough
      for each set's projected 400 draws, e.g. --e7-budget-minutes 600.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import misdating  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.facilities import buildout  # noqa: E402
from pipeline.facilities import corrections as cx  # noqa: E402
from pipeline.facilities import dating_sensitivity as dsens  # noqa: E402
from pipeline.facilities import later_start as ls  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
OUT = FROZEN / "inventory_run_designs.json"
KEY = ps.KEY
YEARS = list(range(2001, 2026))
BASE_YEARS = (2009, 2010, 2011)              # build_inventory.BASE_YEARS (not imported: that module imports geopandas)
ANCHOR_YEAR = px.ANCHOR_YEAR
THETA = 0.02

E7_SEED = 20261203                           # the plan's seed for E7, used nowhere else (grep of pipeline/ and tests/)
E7_DRAWS = 200
DIRECTIONS = ("earlier", "later")
E7_BUDGET_MINUTES = 25.0
EVERY_COHORT_UTILITY = "every_cohort_utility"   # design.SETS' name for the companion set (the plan's Sets paragraph)
# The sets E7 is run on, and the key of each set's block in the output file. The headline set's block keeps the key and
# fields it had before every cohort utility was added (Joe, 2026-11-20: E7 "for both the headline set and every cohort
# utility").
E7_SETS = (ps.HEADLINE_SET, EVERY_COHORT_UTILITY)
E7_BLOCK_KEY = {ps.HEADLINE_SET: "E7", EVERY_COHORT_UTILITY: "E7_every_cohort_utility"}
LATER_START_SHIFTS = ls.SHIFTS               # (1, 3, 5)
NEVER = misdating.NEVER                      # a host with no crossing in the draw: its error is recorded as this

# Why a host is out of an alternative design, in words used in every output.
GROUP_CHANGED = "left out: its group changes on the alternative inventory (E4 'In each'; the roster rule)"
NO_CROSSING = "left out: no crossing at the threshold on the alternative inventory (a missing crossing; no date is invented)"
CROSSING_OUTSIDE = "left out: its crossing on the alternative inventory is outside 2011 to 2022"


# ======================================================================================================================
# The inventory as built, in memory
# ======================================================================================================================

@dataclass
class Inventory:
    """The rebuilt inventory (data/interim, read only) and what the alternative inventories are built from."""
    inp: px.Inputs                     # pass_c_expand.Inputs on the rebuilt frame (load-unknown rows patched, as timing.py does)
    fy: pd.DataFrame                   # every site-year as built, crypto included: fid, utility_id_eia, state, year, mw, crypto
    entries: list                      # the timing corrections in force (timing.timing_entries)
    conv: dict                         # fid -> its history at its convention, for every row a timing entry touches
    base: pd.Series                    # (utility, state) -> 2009-2011 retail sales in GWh, as build_inventory.main computes it
    evidence: pd.DataFrame | None = None

    @property
    def fac(self) -> pd.DataFrame:
        return self.inp.fac

    def history(self, fid: str) -> tuple:
        """The row's history as built: its convention where a timing entry touches it, else pass_c_expand's frozen history."""
        return self.conv.get(fid) or self.inp.hist[fid]


def conventions(entries: list, inp: px.Inputs) -> dict:
    """fid -> history at the convention for every row a timing entry touches (Correction.history with no choice).

    A row with a question that has no convention is LOAD UNKNOWN and carries no load in the frame (corrections.apply_timing;
    Joe, R2): its history here is ("never",), which is what the frame carries, not a statement about the site. A size
    correction alone leaves the history as the frame has it (None from Correction.history), so it is not listed.
    """
    out = {}
    for fid, c in px.parse_corrections(entries, inp).items():
        try:
            h = c.history({})
        except ValueError:
            h = ("never",)
        if h is not None:
            out[fid] = h
    return out


def build_inputs(fac: pd.DataFrame, fy_all: pd.DataFrame, units, base: pd.Series, regions, names, anchor: pd.DataFrame,
                 phases: dict, entries: list, evidence: pd.DataFrame | None = None) -> Inventory:
    """An Inventory from frames (real or invented). `fac` is indexed by fid; `fy_all` carries a boolean `crypto`."""
    from pipeline.facilities import timing as tm
    fac = tm.patch_unknown(fac)
    fy = fy_all[~fy_all.crypto][["fid"] + KEY + ["year", "mw"]]
    inp = px.Inputs.build(fac, fy, units, base, regions, names, anchor, phases, frozen_2024_mw={}, fy_all=fy_all)
    return Inventory(inp, fy_all[["fid"] + KEY + ["year", "mw", "crypto"]].copy(), list(entries), conventions(entries, inp),
                     base, evidence)


def load_inventory() -> Inventory:
    """The rebuilt inventory from the quantity files this pass may read: facilities, facility_year, utility_year_dose,
    state_anchor and panel_quantities (through assignment.load_inputs), the corrections in force and date_evidence.csv.

    timing.load_rebuilt also reads epoch_gaps.parquet, for the 2024 anchoring contribution of measured rows a correction
    takes off the panel (`frozen_2024_mw`). No run here takes a measured row off, so it is passed empty and that file is
    not read; pass_c_expand.scratch_state, which needs it, is not called.
    """
    from pipeline.facilities import assignment as asg
    from pipeline.facilities import timing as tm
    fac, _, q, units, base, regions = asg.load_inputs()
    fy_all = pd.read_parquet(INTERIM / "facility_year.parquet")
    anchor = pd.read_parquet(INTERIM / "state_anchor.parquet").set_index("state")
    phases = buildout.phases_by_site(buildout.load())
    names = q.groupby(KEY).utility_name.last()
    entries = tm.timing_entries(cx.load())
    sales_base = base_sales(q)
    return build_inputs(fac, fy_all, units, sales_base, regions, names, anchor, phases, entries,
                        pd.read_csv(cx.DATE_EVIDENCE))


def base_sales(q: pd.DataFrame) -> pd.Series:
    """build_inventory.main's denominator: mean total retail sales 2009-2011, in GWh."""
    return (q[q.year.isin(BASE_YEARS)].groupby(KEY).total_retail_mwh.mean() / 1000.0).rename("base_retail_gwh")


def dose_frame(fy: pd.DataFrame, base: pd.Series) -> pd.DataFrame:
    """The utility-year dose from site-years, exactly as build_inventory.main aggregates it (its lines under "utility x
    state x year dose"; not a function there). Checked against utility_year_dose.parquet in main()."""
    k = KEY + ["year"]
    dose = fy[~fy.crypto].groupby(k).agg(dc_mw=("mw", "sum"), n_facilities=("fid", "nunique")).reset_index()
    crypto = fy[fy.crypto].groupby(k).mw.sum().rename("crypto_mw").reset_index()
    dose = dose.merge(crypto, on=k, how="outer").fillna({"dc_mw": 0.0, "crypto_mw": 0.0, "n_facilities": 0})
    dose["dc_gwh"] = dose.dc_mw * 8.76
    dose = dose.join(base.rename("base_retail_gwh"), on=KEY)
    dose["dose"] = dose.dc_gwh / dose.base_retail_gwh
    dose["dose_with_crypto"] = (dose.dc_mw + dose.crypto_mw) * 8.76 / dose.base_retail_gwh
    return dose


# ======================================================================================================================
# Rebuilding the site-years with some histories changed
# ======================================================================================================================

def row_mw(history: tuple, mw_full: float, year: int) -> float:
    """A row's load in `year` on `history`. ("slow", start, latest_permit_year) is buildout.slow_mw (D-28's alternative);
    every other history is pass_c_expand.site_mw (the ramp, phase and never branches of build_inventory.site_mw)."""
    if history[0] == "slow":
        return buildout.slow_mw(mw_full, history[1], history[2], year)
    return px.site_mw(history, mw_full, year)


def anchor_twh(history: tuple, mw_full_raw) -> float:
    """What a row counts for in its state's 2024 anchoring on `history` (state_anchor counts rows with a year and a load)."""
    if history[0] in ("never", "fixed") or pd.isna(mw_full_raw):
        return 0.0
    return row_mw(history, float(mw_full_raw), ANCHOR_YEAR) * 8.76 / 1000.0


@dataclass
class Rebuilt:
    fy: pd.DataFrame
    factors: dict                      # state -> {"as_built": f0, "alternative": f1} for every state whose factor was read
    changed_rows: int


def rebuild(inv: Inventory, changed: dict, anchoring: str = "recompute") -> Rebuilt:
    """Site-years with the rows in `changed` (fid -> new history) rebuilt.

    anchoring "recompute": each state a changed row is in gets its factor recomputed (pass_c_expand._factor on the state's
    anchoring row, the changed rows' 2024 load moved in its permit-based or measured total), snapped to the built value
    within pass_c_expand.FACTOR_TOL as pass_c_expand.scratch_state does; every permit-based (not measured) row in a state
    whose factor changed is rescaled to it. anchoring "off": every factor is one (E4(b)): each row's load is divided by
    the scale it was built with (`state_scale`, one for measured rows).
    """
    if anchoring not in ("recompute", "off"):
        raise ValueError(f"anchoring is 'recompute' or 'off', not {anchoring!r}")
    fac, inp = inv.fac, inv.inp
    bad = sorted(f for f in changed if bool(inp.fixed[f]))
    if bad:
        raise ValueError(f"rows with a fixed history (Epoch's timeline or operator-reported electricity) never move here: {bad[:5]}")
    anchor = inp.anchor
    factors: dict[str, dict] = {}
    if anchoring == "recompute":
        delta: dict[str, list] = {}
        for fid, h in changed.items():
            r = fac.loc[fid]
            d = anchor_twh(h, r.mw_full_raw) - anchor_twh(inv.history(fid), r.mw_full_raw)
            if d == 0.0:
                continue
            slot = delta.setdefault(r.state, [0.0, 0.0])
            slot[1 if bool(inp.measured[fid]) else 0] += d
        for st in sorted({fac.state[f] for f in changed} - {None}):
            if not isinstance(st, str):
                continue
            dp, dm = delta.get(st, [0.0, 0.0])
            if st not in anchor.index:
                if dp or dm:                                   # build_inventory.main maps a state with no row to one
                    raise ValueError(f"{st} has no row in state_anchor.parquet and a changed row moves its 2024 load; "
                                     f"its factor cannot be recomputed here")
                factors[st] = {"as_built": 1.0, "alternative": 1.0}
                continue
            a = anchor.loc[st]
            f0 = float(a.factor)
            f1 = px._factor(float(a.epri_twh), float(a.epoch_twh) + dm, float(a.permit_twh) + dp)
            if abs(f1 - f0) <= px.FACTOR_TOL * max(1.0, abs(f0)):
                f1 = f0
            factors[st] = {"as_built": f0, "alternative": f1}
        new_factor = {st: v["alternative"] for st, v in factors.items()}
        ratio = {st: v["alternative"] / v["as_built"] for st, v in factors.items() if v["alternative"] != v["as_built"]}
    else:
        new_factor = {}
        for st in anchor.index:
            factors[st] = {"as_built": float(anchor.factor[st]), "alternative": 1.0}
        ratio = None

    keep = inv.fy[~inv.fy.fid.isin(list(changed))].copy()
    if anchoring == "off":
        scale = keep.fid.map(fac.state_scale).astype(float)
        if scale.isna().any() or (scale <= 0).any():
            raise ValueError("a site-year's row has no positive state_scale; anchoring cannot be taken off")
        keep["mw"] = keep.mw.values / scale.values
    elif ratio:
        meas = keep.fid.map(inp.measured).astype(bool).values
        r = keep.state.map(ratio).fillna(1.0).values
        keep["mw"] = keep.mw.values * np.where(meas, 1.0, r)
    rows = []
    for fid, h in changed.items():
        r = fac.loc[fid]
        if h[0] == "never" or pd.isna(r.mw_full_raw) or pd.isna(r.utility_id_eia):
            continue
        if bool(inp.measured[fid]):
            s = 1.0
        elif anchoring == "off":
            s = 1.0
        else:
            s = new_factor.get(r.state, float(r.state_scale))
        mw_full = float(r.mw_full_raw) * s
        for y in YEARS:
            mw = row_mw(h, mw_full, y)
            if mw > 0:
                rows.append((fid, int(r.utility_id_eia), r.state, y, mw, bool(r.is_crypto)))
    new = pd.DataFrame(rows, columns=["fid"] + KEY + ["year", "mw", "crypto"])
    fy = pd.concat([keep, new.astype({"utility_id_eia": keep.utility_id_eia.dtype, "year": keep.year.dtype})],
                   ignore_index=True) if len(new) else keep.reset_index(drop=True)
    return Rebuilt(fy, factors, len(changed))


def as_built_check(inv: Inventory) -> dict:
    """Every rebuildable row given its own history as built: the site-years and the dose must come back unchanged."""
    changed = {fid: inv.history(fid) for fid in inv.fac.index if not bool(inv.inp.fixed[fid])}
    rb = rebuild(inv, changed)
    k = ["fid", "year"]
    a = inv.fy.set_index(k).mw.sort_index()
    b = rb.fy.set_index(k).mw.sort_index()
    same_rows = a.index.equals(b.index)
    diff = float((a - b.reindex(a.index)).abs().max()) if same_rows else math.inf
    moved = {st: v for st, v in rb.factors.items() if v["alternative"] != v["as_built"]}
    return {"rows_rebuilt": len(changed), "same_site_year_rows": bool(same_rows), "largest_mw_difference": diff,
            "states_whose_factor_moved": moved}


# ======================================================================================================================
# The common core: an alternative dose -> re-dated hosts, eligibility re-read, then G-a
# ======================================================================================================================

@dataclass
class Context:
    """Everything the design rules need besides the dose. Quantities only."""
    q: pd.DataFrame
    regions: pd.DataFrame
    fuel: dict
    dd: pd.DataFrame
    rules: ps.Rules
    ownership: pd.DataFrame | None
    usable: set | None
    gas: dict | None
    ownership_of: dict
    unknown: ps.UnknownLoad
    theta: float
    history: dict                      # power_simulation.history_settled: utilities whose own count fixes the crossing (D-34)
    aside: set                         # power_simulation.set_aside: out of the set on either side
    hold: set | None = None            # the price hold (None: power_simulation.design reads price_hold.csv)

    @classmethod
    def from_files(cls, theta: float = THETA, rules: ps.Rules = ps.HEADLINE_RULES, which: str = ps.HEADLINE_SET) -> "Context":
        """The context for the named set. The set-aside list is the one design.split applies to that set's comparison
        utilities (aside_for); every cohort utility has none."""
        q, _, regions, fuel, dd = dsg.load()
        ownership, usable, gas = ps.rule_inputs(rules, q)
        return cls(q, regions, fuel, dd, rules, ownership, usable, gas, ps.ownership_classes(q), ps.load_unknown_load(), theta,
                   ps.history_settled(theta), aside_for(theta, which))


def aside_for(theta: float, which: str) -> set:
    """The units taken out of the named set's comparison utilities, exactly as design.split takes them. Every cohort
    utility has none (split returns power_simulation.design's frames unchanged); the ten-year list for the set with the
    ten-year case, and the headline list for the headline set and for the set with the unsettled hosts put back (whose
    comparison utilities are the headline's).

    Corrected on 2026-11-20 (session 25). Until then Context.from_files gave every cohort utility the headline list, so
    a context built for that set left out of its comparison pool the comparison-eligible units on that list, which
    design.split keeps (68 of 3,087 on the design as it stands that day). inventory_runs.main built only the headline set's
    context until that date, so data/frozen/inventory_run_designs.json as stored then does not depend on it.
    """
    if which not in dsg.SETS:
        raise ValueError(f"{which!r} is not one of design.SETS {dsg.SETS}")
    if which == EVERY_COHORT_UTILITY:
        return set()
    return ps.set_aside(theta, ten_year_case=(which == ps.TEN_YEAR_SET))


def crossings(dose: pd.DataFrame, theta: float, history: dict) -> dict:
    """(utility, state) -> (group, first crossing or None) at `theta`, with the utility-level histories of D-34 applied as
    power_simulation.design applies them (a cohort history fixes the year; an early or outside history fixes the group)."""
    first = dose[dose.dose >= theta].groupby(KEY).year.min()
    out = {(int(u), st): (buildout.group(y), int(y)) for (u, st), y in first.items()}
    for k, v in (history or {}).items():
        if v["group"] == "cohort":
            out[k] = ("cohort", int(v["first_crossing"]))
        elif v["group"] == "early":
            out[k] = ("early", ps.COHORTS[0] - 1)
        else:
            out[k] = (str(v["group"]), None)
    return out


def comparison_pool(ctx: Context, dose: pd.DataFrame) -> pd.DataFrame:
    """Comparison-eligible units on this dose, through power_simulation.design (under 0.5% in every year, crypto under 2%,
    a base to divide by, not price-held), less the set's set-aside list, as design.split applies it."""
    _, clean = ps.design(ctx.q, dose, ctx.theta, ctx.history, hold=ctx.hold)
    return clean[[(int(u), s) not in ctx.aside for u, s in zip(clean.utility_id_eia, clean.state)]].reset_index(drop=True)


def build(ctx: Context, treated: pd.DataFrame, clean: pd.DataFrame):
    """design.build_with_rules under the context's rules (G-a's matching, ownership, usability and support rules)."""
    if not len(treated):
        return None
    return dsg.build_with_rules(treated, clean, ctx.q, ctx.regions, ctx.fuel, ctx.dd, ctx.rules, ownership=ctx.ownership,
                                usable=ctx.usable, gas=ctx.gas, ownership_of=ctx.ownership_of, unknown_load=ctx.unknown,
                                theta=ctx.theta)


@dataclass
class Redated:
    hosts: list                        # one dict per roster host
    design: object                     # design.Design, or None when no host is left
    clean: pd.DataFrame
    pool_entered: list
    pool_left: list

    def retained(self) -> list:
        return [h["utility"] for h in self.hosts if h["status"] == "retained"]


def _label(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def redate(ctx: Context, dose: pd.DataFrame, roster: pd.DataFrame, reference=None) -> Redated:
    """The common core. `roster` is the set's hosts with their reference crossings (utility_id_eia, state, cohort);
    `reference` is the reference design (a Redated or a design.Design with its pool) to report changes against.

    Each host's event year is its first crossing on `dose` (D-34 histories applied). A host with no crossing in 2011 to
    2022 is left out and named, never re-dated or substituted. Comparison eligibility is re-read on `dose`, then
    design.build_with_rules re-centres each window on the new date and matches at the new reference year.
    """
    cross = crossings(dose, ctx.theta, ctx.history)
    keep, hosts = [], []
    for r in roster.itertuples():
        k = (int(r.utility_id_eia), r.state)
        g0 = int(r.cohort)
        grp, y = cross.get(k, ("never", None))
        h = {"utility": _label(k), "reference_crossing": g0, "crossing": y, "group": grp,
             "moved_by": None if y is None else int(y - g0), "status": None, "why": None}
        if grp == "cohort":
            keep.append((k[0], k[1], int(y)))
        elif grp == "never":
            h.update(status="out", why=NO_CROSSING)
        else:
            h.update(status="out", why=f"{GROUP_CHANGED}: {grp} ({CROSSING_OUTSIDE})")
        hosts.append(h)
    treated = pd.DataFrame(keep, columns=KEY + ["cohort"])
    clean = comparison_pool(ctx, dose)
    d = build(ctx, treated, clean)
    if d is not None:
        in_design = ({(_label(k), int(g)): list(m) for k, g, m in zip(d.hosts.key, d.hosts.cohort, d.hosts.match_keys)}
                     if len(d.hosts) else {})
        dropped = {x["utility"]: x["why"] for x in d.dropped}
        for h in hosts:
            if h["status"] is not None:
                continue
            key = (h["utility"], h["crossing"])
            if key in in_design:
                h.update(status="retained", matches=[_label(m) for m in in_design[key]])
            else:
                h.update(status="out", why=dropped.get(h["utility"], "not in the design (no reason recorded by build_with_rules)"))
    ref_clean = None
    if reference is not None:
        ref_clean = reference.clean if isinstance(reference, Redated) else None
    now = set(map(tuple, clean[KEY].itertuples(index=False)))
    before = set(map(tuple, ref_clean[KEY].itertuples(index=False))) if ref_clean is not None else now
    out = Redated(hosts, d, clean, sorted(_label(k) for k in now - before), sorted(_label(k) for k in before - now))
    if isinstance(reference, Redated):
        compare(out, reference)
    return out


def compare(alt: Redated, ref: Redated) -> None:
    """Writes, on each host of `alt`, what changed against `ref`: timing (the crossing) apart from the sample (whether it
    is in the design) and the comparisons (its matches)."""
    r = {h["utility"]: h for h in ref.hosts}
    for h in alt.hosts:
        b = r.get(h["utility"], {})
        h["crossing_moved"] = h["crossing"] != b.get("crossing")
        h["in_reference_design"] = b.get("status") == "retained"
        h["sample_changed"] = (h["status"] == "retained") != h["in_reference_design"]
        if h["status"] == "retained" and b.get("status") == "retained":
            m0, m1 = set(b["matches"]), set(h["matches"])
            h["matches_added"] = sorted(m1 - m0)
            h["matches_removed"] = sorted(m0 - m1)
            h["matches_changed"] = len(m1 - m0)


def summarise(alt: Redated) -> dict:
    hosts = alt.hosts
    return {"hosts_in_the_set": len(hosts),
            "hosts_retained": [h["utility"] for h in hosts if h["status"] == "retained"],
            "hosts_out_and_why": {h["utility"]: h["why"] for h in hosts if h["status"] != "retained"},
            "crossings": {h["utility"]: {"reference": h["reference_crossing"], "alternative": h["crossing"],
                                         "moved_by": h["moved_by"], "group": h["group"]} for h in hosts},
            "timing_changes": sorted(h["utility"] for h in hosts if h.get("crossing_moved")),
            "estimable_sample_changes": sorted(h["utility"] for h in hosts if h.get("sample_changed")),
            "missing_crossings": sorted(h["utility"] for h in hosts if h["why"] == NO_CROSSING),
            "group_changes": sorted(h["utility"] for h in hosts if h["why"] and h["why"].startswith(GROUP_CHANGED)),
            "lost_support_or_window": {h["utility"]: h["why"] for h in hosts if h["status"] == "out" and h["group"] == "cohort"},
            "matches_changed": {h["utility"]: {"added": h.get("matches_added"), "removed": h.get("matches_removed")}
                                for h in hosts if h.get("matches_changed")},
            "comparison_pool": {"eligible": int(len(alt.clean)), "entered": alt.pool_entered, "left": alt.pool_left}}


def roster_of(design_or_treated) -> pd.DataFrame:
    return design_or_treated[KEY + ["cohort"]].reset_index(drop=True)


# ======================================================================================================================
# E4(a) the slow path, E4(b) anchoring off
# ======================================================================================================================

def slow_path_rows(inv: Inventory) -> tuple[dict, dict]:
    """E4(a): fid -> ("slow", start, latest permit year) for every row on the default three-year ramp whose slow path
    differs (buildout.slow_end_year later than the ramp's end), and a record of what was taken and what was not.

    Not moved (plan, E4(a)): Epoch timelines and operator-reported electricity (fixed histories), applied D-28 histories
    (verified/buildout.csv phases), single buildings (load_history single_building_record: buildout.csv and the county
    rule), split phases and phases set by a correction (their history at the convention is not a plain ramp), stress
    scenarios (not in the as-built inventory), and load-unknown rows (no load). "Every site whose load follows the
    default three-year ramp" includes rows with no serving utility (adopted by Joe on 2026-11-19, D-111) and crypto rows
    (the agent's reading), since both count in their state's anchoring; buildout.py's own report takes only data-center
    rows on a utility.
    """
    fac = inv.fac
    out, skipped = {}, {"fixed_history": 0, "verified_or_correction_phases": 0, "single_building": 0, "load_unknown": 0,
                        "no_year_or_no_size": 0, "slow_path_equals_the_ramp": 0}
    extra = {"no_serving_utility": [], "crypto": []}
    for fid, r in fac.iterrows():
        if bool(inv.inp.fixed[fid]):
            skipped["fixed_history"] += 1
            continue
        if bool(r.get("load_unknown", False)):
            skipped["load_unknown"] += 1
            continue
        h = inv.history(fid)
        if h[0] == "phases" or r.load_history == "verified_phases":
            skipped["verified_or_correction_phases"] += 1
            continue
        if r.load_history == "single_building_record":
            skipped["single_building"] += 1
            continue
        if h[0] != "ramp" or pd.isna(r.mw_full_raw):
            skipped["no_year_or_no_size"] += 1
            continue
        start = float(h[1])
        if buildout.slow_end_year(start, r.latest_permit_year) <= start + buildout.RAMP_YEARS - 1:
            skipped["slow_path_equals_the_ramp"] += 1
            continue
        out[fid] = ("slow", start, float(r.latest_permit_year))
        if pd.isna(r.utility_id_eia):
            extra["no_serving_utility"].append(fid)
        if bool(r.is_crypto):
            extra["crypto"].append(fid)
    return out, {"rows_on_the_slow_path": len(out), "not_moved": skipped,
                 "beyond_buildout_py_selection": {k: sorted(v) for k, v in extra.items()}}


def e4a(inv: Inventory) -> tuple[Rebuilt, dict]:
    changed, record = slow_path_rows(inv)
    return rebuild(inv, changed, "recompute"), record


def e4b(inv: Inventory) -> Rebuilt:
    return rebuild(inv, {}, "off")


# ======================================================================================================================
# The later-start sensitivity on outcomes (+1, +3, +5)
# ======================================================================================================================

def later_start_rows(inv: Inventory, k: int) -> tuple[dict, list]:
    """later_start.shifted's inventory at +k years (which rows shift, sourced ends, incompatible shifts), as histories:
    fid -> new history for every row whose history at the convention changes. Returns (changed, incompatible)."""
    bounds = ls.evidence_bounds(inv.evidence)
    ent, bad, patch = [], [], {}
    fac_state = inv.fac.state
    for st in sorted(set(inv.inp.units.get_level_values("state"))):       # state by state, as later_start.run calls it
        e, b, p = ls.shifted(inv.inp, [c for c in inv.entries if fac_state.get(c["fid"]) == st], k, bounds, st)
        ent += e
        bad += b
        patch.update(p)
    inp_s = ls.with_years(inv.inp, patch)
    conv_s = conventions(ent, inp_s)
    changed = {}
    for fid, h in conv_s.items():
        if h != inv.history(fid):
            changed[fid] = h
    return changed, bad


def later_start(inv: Inventory, k: int) -> tuple[Rebuilt, list]:
    changed, bad = later_start_rows(inv, k)
    return rebuild(inv, changed, "recompute"), bad


# ======================================================================================================================
# E7: permit-dated start years redrawn from the measured permit errors
# ======================================================================================================================

def load_errors(path: Path | None = None) -> dict:
    """`errors_in_years_by_generator_based_size_mw` from dating_report.json. Sign (dating_report.error_stats and its
    `definition`): permit-based year minus the sourced year, positive where the permit dated the site too late."""
    rep = json.loads((path or FROZEN / "dating_report.json").read_text())["permit_dating_error"]
    return {k: np.array(v, dtype=float) for k, v in rep["errors_in_years_by_generator_based_size_mw"].items()}


def date_bounds(evidence: pd.DataFrame | None) -> tuple[dict, dict]:
    """(fid -> latest not-before year, fid -> earliest not-after year) from date_evidence.csv. The not-after kinds are
    later_start.evidence_bounds' (operating-by and stated-start, read from kind_d61 where present); not-before is kind
    not_before, read the same way. Generator activity bounds nothing (rule 1.2)."""
    after = {f: min(v) for f, v in ls.evidence_bounds(evidence).items() if v}
    before = {}
    if evidence is not None and len(evidence):
        col = "kind_d61" if "kind_d61" in evidence else "kind"
        e = evidence[evidence[col] == "not_before"]
        before = {fid: int(g.year.max()) for fid, g in e.groupby("site")}
    return before, after


@dataclass
class E7Rows:
    redrawn: pd.DataFrame              # fid, start (the permit-based year), size class
    no_load: list                      # the four sites whose operating status is unsettled: no load in every draw
    not_redrawn_permit_rows: dict      # permit-dated rows that cannot be redrawn, by reason
    not_before: dict
    not_after: dict


def e7_rows(inv: Inventory, unsettled: dict | None = None) -> E7Rows:
    """Rows redrawn: date_basis first_generator_permit_plus_lag (plan, E7). The four sites of dating_sensitivity.
    UNSETTLED_STATUS carry no load in every draw. A permit-dated row with no year or no size carries no load either way;
    one with phases or a fixed history would have only part redrawn, which no row on the rebuilt inventory needs (listed)."""
    fac = inv.fac
    unsettled = dsens.UNSETTLED_STATUS if unsettled is None else unsettled
    rows = fac[fac.date_basis == cx.PERMIT_LABEL]
    none_load = [f for f in unsettled if f in fac.index]
    why: dict[str, list] = {"no_year_or_no_size": [], "has_phases_or_a_fixed_history": []}
    take = []
    for fid, r in rows.iterrows():
        if fid in none_load:
            continue
        if pd.isna(r.energized_year) or pd.isna(r.mw_full_raw):
            why["no_year_or_no_size"].append(fid)
            continue
        if bool(inv.inp.fixed[fid]) or fid in inv.inp.phases or inv.history(fid)[0] != "ramp":
            why["has_phases_or_a_fixed_history"].append(fid)
            continue
        take.append((fid, float(inv.history(fid)[1]), misdating.size_class(r.get("generator_kw", np.nan))))
    before, after = date_bounds(inv.evidence)
    return E7Rows(pd.DataFrame(take, columns=["fid", "start", "size"]), none_load, why, before, after)


def e7_starts(rows: E7Rows, errors: dict, direction: str, draw: int, seed: int = E7_SEED) -> tuple[dict, list]:
    """One draw's redrawn start years: fid -> year, and the holds [(fid, "not_before" | "not_after", wanted, held_at)].

    Errors are drawn with replacement within the row's size class, independently by row, from a generator keyed by
    (seed, draw), so a draw can be produced on its own. For "its mirror", draw i uses the same drawn errors in both
    directions, the earlier run subtracting them and the later run adding them (adopted by Joe on 2026-11-19, D-111).
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction is one of {DIRECTIONS}, not {direction!r}")
    rng = np.random.default_rng([seed, int(draw)])
    sign = -1.0 if direction == "earlier" else 1.0
    out, holds = {}, []
    for fid, start, size in rows.redrawn.itertuples(index=False):
        pool = errors[size]
        e = float(pool[rng.integers(0, len(pool))])
        want = start + sign * e
        got = want
        if fid in rows.not_before and got < rows.not_before[fid]:
            got = float(rows.not_before[fid])
            holds.append((fid, "not_before", want, got))
        if fid in rows.not_after and got > rows.not_after[fid]:
            got = float(rows.not_after[fid])
            holds.append((fid, "not_after", want, got))
        out[fid] = got
    return out, holds


def e7_changed(rows: E7Rows, starts: dict) -> dict:
    """Histories for one draw: each redrawn row on the default ramp from its redrawn year (the ramp governs at both ends
    of the panel: buildout.ramp_mw), and the four unsettled sites at no load."""
    changed = {fid: ("ramp", float(s)) for fid, s in starts.items()}
    changed.update({fid: ("never",) for fid in rows.no_load})
    return changed


@dataclass
class E7Draw:
    direction: str
    draw: int
    holds: list
    redated: Redated | None
    errors: dict                       # host -> crossing in the draw minus the recorded crossing (NEVER if none)
    failure: str | None = None


def e7_draw(ctx: Context, inv: Inventory, rows: E7Rows, errors: dict, roster: pd.DataFrame, direction: str, draw: int,
            reference: Redated | None = None, seed: int = E7_SEED) -> E7Draw:
    """One draw, computed on its own: redraw, rebuild with the factor recomputed, re-read eligibility, then G-a. A draw
    that cannot be computed is returned with its failure, never dropped."""
    try:
        starts, holds = e7_starts(rows, errors, direction, draw, seed)
        rb = rebuild(inv, e7_changed(rows, starts), "recompute")
        alt = redate(ctx, dose_frame(rb.fy, inv.base), roster, reference)
    except Exception as exc:                                    # counted and reported by cause (plan, numerical failures)
        return E7Draw(direction, draw, [], None, {}, f"{type(exc).__name__}: {exc}")
    errs = {h["utility"]: (NEVER if h["crossing"] is None else int(h["crossing"] - h["reference_crossing"])) for h in alt.hosts}
    return E7Draw(direction, draw, holds, alt, errs)


def e7_designs(ctx: Context, inv: Inventory, roster: pd.DataFrame, direction: str, draws=range(E7_DRAWS),
               reference: Redated | None = None, errors: dict | None = None, seed: int = E7_SEED) -> Iterator[E7Draw]:
    """Lazily, the draws of one direction: for the post-freeze run to fit a point estimate draw by draw."""
    errors = load_errors() if errors is None else errors
    rows = e7_rows(inv)
    for i in draws:
        yield e7_draw(ctx, inv, rows, errors, roster, direction, i, reference, seed)


def e7_summary(results: list, roster: pd.DataFrame, rows: E7Rows) -> dict:
    """The plan's quantity-side figures for one direction: per host the share of draws reproducing its recorded crossing
    exactly and within one year (misdating.describe), the set's pooled share over host-draws, the mean number of hosts per
    draw, draws held at a bound (by row), draws that could not be computed (by cause)."""
    ok = [r for r in results if r.failure is None]
    hosts = [_label((u, s)) for u, s in zip(roster.utility_id_eia, roster.state)]
    per = {}
    for h in hosts:
        e = np.array([r.errors[h] for r in ok], dtype=int)
        per[h] = {**(misdating.describe(e) if len(e) else {}),
                  "share_of_draws_with_a_crossing_in_2011_to_2022": round(float(np.mean([
                      next(x for x in r.redated.hosts if x["utility"] == h)["group"] == "cohort" for r in ok])), 3) if ok else None,
                  "share_of_draws_in_the_design": round(float(np.mean([h in r.redated.retained() for r in ok])), 3) if ok else None}
    pooled = np.concatenate([np.array([r.errors[h] for r in ok], dtype=int) for h in hosts]) if ok else np.zeros(0, int)
    held: dict[str, dict] = {}
    for r in ok:
        for fid, kind, *_ in r.holds:
            held.setdefault(fid, {}).setdefault(kind, 0)
            held[fid][kind] += 1
    causes: dict[str, int] = {}
    for r in results:
        if r.failure is not None:
            c = r.failure.split(":", 1)[0]
            causes[c] = causes.get(c, 0) + 1
    return {"draws_attempted": len(results), "draws_computed": len(ok),
            "draws_that_could_not_be_computed": {"count": len(results) - len(ok), "by_cause": causes},
            "by_host": per,
            "set_pooled_over_host_draws": misdating.describe(pooled) if len(pooled) else None,
            "mean_hosts_per_draw_in_the_design": round(float(np.mean([len(r.redated.retained()) for r in ok])), 3) if ok else None,
            "mean_hosts_per_draw_with_a_crossing_in_2011_to_2022": round(float(np.mean(
                [sum(x["group"] == "cohort" for x in r.redated.hosts) for r in ok])), 3) if ok else None,
            "draws_held_at_a_bound_by_row": held,
            "draws_with_any_hold": int(sum(bool(r.holds) for r in ok))}


# ======================================================================================================================
# E7 on each named set: the same functions, each set with its own reference design and roster
# ======================================================================================================================

SEED_AND_STREAMS = (
    "Seed 20261203 (E7_SEED) and the streams exactly as e7_starts builds them. Draw i uses numpy's generator keyed by "
    "(E7_SEED, i) over the redrawn rows of e7_rows in their order, which do not depend on the set. So draw i redraws the "
    "inventory identically for every set, and only the set's hosts, reference design and roster differ. The agent's "
    "reading (session 25, 2026-11-20), since the existing functions give no other stream for a second set without a new rule.")


@dataclass
class SetReference:
    which: str
    ctx: Context
    roster: pd.DataFrame               # the set's hosts with their recorded crossings (design.split's hosts)
    ref: Redated                       # the common core on the dose as built


def context_for(ctx: Context, which: str) -> Context:
    """`ctx` with the named set's set-aside list (aside_for). Everything else is shared across sets."""
    return replace(ctx, aside=aside_for(ctx.theta, which))


def _keys(frame: pd.DataFrame) -> set:
    return set(map(tuple, frame[KEY].itertuples(index=False)))


def set_reference(ctx: Context, which: str, dose_built: pd.DataFrame) -> SetReference:
    """The named set's reference, made of its hosts and comparison utilities as design.split gives them, design.build_with_rules
    on them, and the common core (redate) on the dose as built, which must return the same design and the same comparison
    pool. Stops in words if it does not."""
    treated, clean = dsg.split(ctx.theta, which, ctx.q, dose_built)
    official = dsg.build_with_rules(treated, clean, ctx.q, ctx.regions, ctx.fuel, ctx.dd, ctx.rules, ownership=ctx.ownership,
                                    usable=ctx.usable, gas=ctx.gas, ownership_of=ctx.ownership_of, unknown_load=ctx.unknown,
                                    theta=ctx.theta)
    roster = roster_of(treated)
    ref = redate(ctx, dose_built, roster)
    if _keys(ref.clean) != _keys(clean):
        raise SystemExit(f"{which}: the core's comparison pool is not design.split's ({len(ref.clean)} against {len(clean)} "
                         f"units); the context's set-aside list is not the set's")
    try:
        pd.testing.assert_frame_equal(ref.design.hosts, official.hosts)
    except AssertionError as exc:
        raise SystemExit(f"{which}: the core on the dose as built does not return design.build_with_rules' design: {exc}")
    if ref.design.dropped != official.dropped:
        raise SystemExit(f"{which}: the core on the dose as built drops other hosts than design.build_with_rules")
    return SetReference(which, ctx, roster, ref)


def e7_run(ctx: Context, inv: Inventory, rows: E7Rows, errors: dict, roster: pd.DataFrame, ref: Redated,
           draws: int = E7_DRAWS, budget_minutes: float = E7_BUDGET_MINUTES, timing_draws: int = 10,
           clock=time.time) -> tuple[dict, dict]:
    """E7 for one set, time-boxed. It times the first draws (alternating directions), then runs the full set only if the
    projected time for 2 x `draws` draws is within `budget_minutes`; otherwise the timing draws are kept and labelled a
    partial timing run. Returns (the block, draws run by direction). The block has the fields main wrote for the headline set
    before 2026-11-20, in the same order; only the label of a run with other than 200 draws a direction is new. The budget is the existing flag and not a research rule; a high budget runs the
    set in full. Only draws equal to E7_DRAWS (200) a direction, run in full, are labelled the specified run."""
    results = {d: [] for d in DIRECTIONS}
    n_t = max(1, min(int(timing_draws), 2 * int(draws)))
    t0 = clock()
    for i in range(n_t):
        d = DIRECTIONS[i % 2]
        results[d].append(e7_draw(ctx, inv, rows, errors, roster, d, len(results[d]), ref, seed=E7_SEED))
    per_draw = (clock() - t0) / n_t
    projected = per_draw * 2 * draws / 60.0
    full = projected <= budget_minutes
    if full:
        for d in DIRECTIONS:
            for i in range(len(results[d]), draws):
                results[d].append(e7_draw(ctx, inv, rows, errors, roster, d, i, ref, seed=E7_SEED))
    n_run = {d: len(v) for d, v in results.items()}
    if not full:
        label = f"a partial timing run of {n_run} draws, not the specified {E7_DRAWS} a direction"
    elif draws == E7_DRAWS:
        label = f"the specified {E7_DRAWS} draws a direction"
    else:
        label = f"{draws} draws a direction set by --e7-draws, not the specified {E7_DRAWS}"
    block = {"partial_timing_run": not full,
             "label": label,
             "seconds_per_draw": round(per_draw, 2), "projected_minutes_for_400_draws": round(per_draw * 400 / 60.0, 1),
             "budget_minutes": budget_minutes, "seed": E7_SEED,
             "rows_redrawn": int(len(rows.redrawn)), "rows_redrawn_by_size_class": rows.redrawn["size"].value_counts().to_dict(),
             "permit_dated_rows_on_the_rebuilt_inventory": int((inv.fac.date_basis == cx.PERMIT_LABEL).sum()),
             "permit_dated_rows_not_redrawn": {k2: len(v) for k2, v in rows.not_redrawn_permit_rows.items()},
             "rows_with_a_sourced_bound": {"not_before": sorted(set(rows.not_before) & set(rows.redrawn.fid)),
                                           "not_after": sorted(set(rows.not_after) & set(rows.redrawn.fid))},
             "unsettled_operating_status_no_load_in_every_draw": {
                 f: {"why": dsens.UNSETTLED_STATUS.get(f), "date_basis_on_the_rebuilt_inventory": inv.fac.date_basis[f],
                     "start_year_on_the_rebuilt_inventory": None if pd.isna(inv.fac.energized_year[f]) else int(inv.fac.energized_year[f]),
                     "carries_load_as_built": bool(inv.fac.in_dose[f]), "state": inv.fac.state[f],
                     "utility": None if pd.isna(inv.fac.utility_id_eia[f]) else _label((inv.fac.utility_id_eia[f], inv.fac.state[f]))}
                 for f in rows.no_load},
             "error_sign": "dating_report.json: permit-based year minus sourced year, positive where the permit dated the site too "
                           "late. Earlier: start = permit-based year minus the drawn error; later: plus it.",
             "directions": {d: e7_summary(results[d], roster, rows) for d in DIRECTIONS}}
    return block, n_run


def reference_block(ref: Redated, names) -> dict:
    """The reference design as the output file records it: each host's crossing, status and matches, and the pool size."""
    return {"hosts": [{"utility": h["utility"], "name": names.get((int(h["utility"].split(":")[0]), h["utility"].split(":")[1])),
                       "crossing": h["reference_crossing"], "status": h["status"], "matches": h.get("matches")}
                      for h in ref.hosts],
            "eligible_comparison_utilities": int(len(ref.clean))}


def e7_all_sets(ctx: Context, inv: Inventory, dose_built: pd.DataFrame, rows: E7Rows, errors: dict, names,
                headline: SetReference, draws: int = E7_DRAWS, budget_minutes: float = E7_BUDGET_MINUTES,
                timing_draws: int = 10, sets=E7_SETS, clock=time.time, budgets: dict | None = None) -> tuple[dict, dict]:
    """E7 on each set of `sets` through the same e7_run, each with its own reference design and roster, the same seed,
    errors, rows and draws, and its own time box. Returns ({output key: block}, {set: draws run by direction}).
    `budgets` ({set: minutes}) overrides `budget_minutes` for the sets it names; the time box is not a research rule.

    The headline set's block is e7_run's block alone, under the key "E7", with the file's top-level `set` and `reference`
    naming its set as before. Every other set's block carries its own `set`, `reference` and checks beside e7_run's fields.
    """
    blocks, n_runs = {}, {}
    for which in sets:
        if which == ps.HEADLINE_SET:
            sr = headline
        else:
            sr = set_reference(context_for(ctx, which), which, dose_built)
        budget = (budgets or {}).get(which, budget_minutes)
        block, n_run = e7_run(sr.ctx, inv, rows, errors, sr.roster, sr.ref, draws=draws, budget_minutes=budget,
                              timing_draws=timing_draws, clock=clock)
        n_runs[which] = n_run
        if which == ps.HEADLINE_SET:
            blocks[E7_BLOCK_KEY[which]] = block
            continue
        blocks[E7_BLOCK_KEY[which]] = {
            "set": which, "threshold": sr.ctx.theta,
            "what_this_is": (f"E7's redraw of permit-dated start years for {which} at {sr.ctx.theta:.0%}, by the same functions "
                             "and under the same rule as the headline set's block E7: the same rows redrawn from the same "
                             "errors, the same seed and draws, the hosts and reference design this set's own (design.split "
                             "and design.build_with_rules for this set). PROVISIONAL: the design stands as of 2026-11-18, the "
                             "plan is a draft and not frozen, and E7's error distribution is fixed at the freeze. No price, "
                             "revenue or bill is read."),
            "seed_and_draw_streams": SEED_AND_STREAMS,
            "checks": {"core_on_the_dose_as_built_equals_design_build_with_rules": True,
                       "core_comparison_pool_equals_design_split": True},
            "reference": reference_block(sr.ref, names),
            "settings": {"e7_seed": E7_SEED, "e7_draws_specified": E7_DRAWS, "e7_draws_requested": draws, "e7_draws_run": n_run},
            **block}
    return blocks, n_runs


# ======================================================================================================================
# main: the quantity-only summary for the headline set at 2%, with E7 also for every cohort utility
# ======================================================================================================================

def factors_for(rb: Rebuilt, states) -> dict:
    return {st: rb.factors.get(st, {"as_built": None, "alternative": None, "note": "no changed row in this state"})
            for st in sorted(states)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--e7-draws", type=int, default=E7_DRAWS)
    ap.add_argument("--e7-budget-minutes", type=float, default=E7_BUDGET_MINUTES,
                    help="the time box, applied to each set's E7 run on its own; set it high to run each set in full")
    ap.add_argument("--e7-budget-minutes-every-cohort-utility", type=float, default=None,
                    help="the time box for every cohort utility's E7 alone (default: --e7-budget-minutes)")
    ap.add_argument("--e7-timing-draws", type=int, default=10)
    args = ap.parse_args(argv)
    t_all = time.time()
    inv = load_inventory()
    ctx = Context.from_files(THETA)

    # Checks that the arithmetic reproduces the inventory as built.
    dose_built = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    k = KEY + ["year"]
    mine = dose_frame(inv.fy, inv.base)[dose_built.columns].sort_values(k).reset_index(drop=True)
    pd.testing.assert_frame_equal(mine, dose_built.sort_values(k).reset_index(drop=True), check_exact=True)
    f_check = max(abs(px._factor(float(r.epri_twh), float(r.epoch_twh), float(r.permit_twh)) - float(r.factor))
                  for _, r in inv.inp.anchor.iterrows())
    built = as_built_check(inv)
    if not built["same_site_year_rows"] or built["largest_mw_difference"] > 1e-9 or built["states_whose_factor_moved"]:
        raise SystemExit(f"the rebuild does not reproduce the inventory as built: {built}")

    # The reference: the headline set's design as design.split and build_with_rules give it, and the core on the dose as built.
    headline = set_reference(ctx, ps.HEADLINE_SET, dose_built)
    roster, ref = headline.roster, headline.ref
    states = sorted(set(roster.state))
    names = ctx.q.groupby(KEY).utility_name.last()

    runs = {}
    rb, rec = e4a(inv)
    a = redate(ctx, dose_frame(rb.fy, inv.base), roster, ref)
    runs["E4a_slow_path"] = {**summarise(a), "rows": rec, "factor_by_state_of_the_hosts": factors_for(rb, states),
                             "states_whose_factor_moved": sorted(s for s, v in rb.factors.items() if v["alternative"] != v["as_built"])}
    rb = e4b(inv)
    b = redate(ctx, dose_frame(rb.fy, inv.base), roster, ref)
    runs["E4b_anchoring_off"] = {**summarise(b), "factor_by_state_of_the_hosts": factors_for(rb, states)}
    for s in LATER_START_SHIFTS:
        changed, bad = later_start_rows(inv, s)
        rb = rebuild(inv, changed, "recompute")
        x = redate(ctx, dose_frame(rb.fy, inv.base), roster, ref)
        runs[f"later_start_plus_{s}"] = {**summarise(x), "rows_whose_history_changes": len(changed),
                                         "incompatible_shifts": bad, "incompatible_shift_count": len(bad),
                                         "factor_by_state_of_the_hosts": factors_for(rb, states),
                                         "states_whose_factor_moved": sorted(st for st, v in rb.factors.items()
                                                                             if v["alternative"] != v["as_built"])}

    # E7 on the headline set and on every cohort utility, each time-boxed on its own: time the first draws, then run the
    # set in full only if its 400 draws fit the budget.
    errors = load_errors()
    rows = e7_rows(inv)
    e7_blocks, e7_n_runs = e7_all_sets(ctx, inv, dose_built, rows, errors, names, headline, draws=args.e7_draws,
                                       budget_minutes=args.e7_budget_minutes, timing_draws=args.e7_timing_draws,
                                       budgets=({EVERY_COHORT_UTILITY: args.e7_budget_minutes_every_cohort_utility}
                                                if args.e7_budget_minutes_every_cohort_utility is not None else None))
    e7 = e7_blocks[E7_BLOCK_KEY[ps.HEADLINE_SET]]
    n_run = e7_n_runs[ps.HEADLINE_SET]
    others = {k2: v for k2, v in e7_blocks.items() if k2 != E7_BLOCK_KEY[ps.HEADLINE_SET]}

    doc = {
        "what_this_is": ("Quantity-only design side of the runs that change the facility inventory and move event dates "
                         "(E4(a) slow path, E4(b) anchoring off, the later-start sensitivity on outcomes at +1, +3 and +5 "
                         "years, and E7's redraw of permit-dated start years), for the headline set at 2%. Each host's event "
                         "year is its first crossing on the alternative inventory; comparison eligibility is re-read there; "
                         "then G-a rematches at the new reference year. Timing sensitivity with rematching, not an isolated "
                         "timing effect. PROVISIONAL: the design stands as of 2026-11-18, the plan is a draft and not "
                         "frozen, and E7's error distribution is fixed at the freeze. No price, revenue or bill is read."),
        "threshold": THETA, "set": ps.HEADLINE_SET,
        "checks": {"dose_from_site_years_equals_utility_year_dose_parquet": True,
                   "largest_factor_difference_from_state_anchor_parquet": f_check, "rebuild_with_every_history_as_built": built,
                   "core_on_the_dose_as_built_equals_design_build_with_rules": True},
        "reference": reference_block(ref, names),
        "runs": runs, "E7": e7,
        **others,
        "E7_blocks_by_set": {ps.HEADLINE_SET: "E7 (its set and reference design are the file's top-level `set` and `reference`)",
                             **{w: E7_BLOCK_KEY[w] for w in E7_SETS if w != ps.HEADLINE_SET}},
        "fingerprint": cx.fingerprint([ROOT / "pipeline/analysis/inventory_runs.py", *cx.code_files(),
                                       ROOT / "pipeline/analysis/design.py", ROOT / "pipeline/analysis/power_simulation.py",
                                       ROOT / "pipeline/analysis/misdating.py", cx.CORRECTIONS, cx.DATE_EVIDENCE,
                                       INTERIM / "facilities.parquet", INTERIM / "facility_year.parquet",
                                       INTERIM / "utility_year_dose.parquet", INTERIM / "state_anchor.parquet",
                                       FROZEN / "dating_report.json"],
                                      threshold=THETA, e7_seed=E7_SEED, e7_draws_specified=args.e7_draws, e7_draws_run=n_run,
                                      later_start_shifts=list(LATER_START_SHIFTS)),
        "seconds": round(time.time() - t_all, 1),
    }
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps({k2: v for k2, v in doc.items() if k2 in ("checks", "seconds")}, indent=1, default=str))
    print(json.dumps({r: {k2: v[k2] for k2 in ("hosts_retained", "hosts_out_and_why", "timing_changes")} for r, v in runs.items()},
                     indent=1, default=str))
    print(json.dumps({key: {k2: b[k2] for k2 in ("label", "partial_timing_run", "seconds_per_draw",
                                                  "projected_minutes_for_400_draws")}
                      for key, b in e7_blocks.items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
