#!/usr/bin/env python3
"""The expansion test of the verification pass (docs/DECISIONS.md, D-61 section 4, with section 5's date rules;
D-46 ruling 4 as amended; first written for D-59 item 2 and D-58 rule 3.7; D-63 rules 4, 7 and 8).

Load and sales only. Nothing here reads a price or revenue column, opens data/blind, or imports the price code. It
writes nothing under data/frozen or data/interim: every rebuild is a scratch copy in memory. It computes the place of
the utilities a correction touches and nothing else: no set of hosts, support count, precision or calibration.

Two entry points
----------------
`test()` (CLI `--assignment-only`) is the assignment-only test the ledger's D-60 results cite. It is kept unchanged:
assignment corrections only, every state's anchoring factor held at its frozen value.

`expand()` (the CLI default) is D-61 section 4. A correction is a dict with `fid` and `kind`:

  assign          {"to": [utility_id_eia, state]} or {"to": "off_panel"}: verified onto that utility, or off the panel
  narrow          {"candidates": [utility_id_eia, ...]}: the site stays unresolved; its candidate list becomes this
  candidates      {"candidates": [utility_id_eia, ...]}: a possible supplier is ADDED to a site the inventory does not
                  carry as verified (D-66 section 1). The new list has to contain every candidate the inventory lists;
                  taking one away is a narrow and has to meet D-63 rule 5. The site is unresolved from then on, also
                  where the map had it alone in one territory. Refused on a verified site (that is a reopen).
  reopen          {"candidates": [utility_id_eia, ...]}: a site the frozen inventory carries as verified whose
                  verification the pass has withdrawn (D-63 rule 8). It becomes unresolved with exactly these
                  candidates; it stays on the utility it is on (the as-mapped reading) when that is among them, and is
                  entered on the first one listed when it is not. Refused: on a site not verified in the frozen inputs,
                  with an assign or narrow on the same site, with no candidates, and on a measured history with no
                  site-years on file.
  size            {"mw_full": x}: the row's full load before the state factor ("measured": true makes it a measured
                  row, unscaled, as an operator's figure entered through overrides.csv would be; default false)
  date            {"earliest": Y|null, "latest": Y|null, "never_is_possible": bool, "convention": Y|"never"|null,
                   "ends": "evidence"|"tested", "convention_is": "provisional"|absent}
                  (ends: default "tested"; see "Tested and admissible ranges". convention_is: "provisional" marks a
                  convention that is a year built from a government record, D-65 on the 115; the exact attribution
                  treats a reference that turns on it as undefined, D-66 section 4. Nothing in this module reads it:
                  the place test's own reference takes a provisional convention as a convention, which is why that
                  reference is a conditional diagnostic and no more, D-90; see "The place test's reference".)
  phases          {"phases": [[year, cumulative_share], ...]}: a dated build-out, held fixed in every case
  capacity_split  {"first_phase_year": Y, "first_share": s|null, "convention": "early"|"late"|null, "rest_earliest": Y|null}
  not_a_site      the row carries no load in any case

Date intervals (D-61 5.1 to 5.4; D-59 item 1). The two ends of an interval are its EARLY end and its LATE end.
`earliest: null` is open below: the row carries full load from 2001 with no ramp inside the panel (a start "in 2001"
with a ramp is a different history and is not what is meant). The late end is "never" (no load in any year) when
`never_is_possible`, otherwise `latest`; `latest: null` requires `never_is_possible`. `convention` is the year the
corrected inventory carries (5.4), or null when the start is UNRESOLVED, in which case no history is manufactured
for it. A capacity split (5.2) dates a first phase and leaves the rest undated: its early case puts the rest with the
first phase, its late case at the inventory year (with `first_share` null: the whole row with the first phase, or
nothing before the inventory year). Neither case is asserted. The corrected inventory has no convention for it, so
`convention` there is optional and null by default: an unresolved capacity question, run both ways like an
unresolved start. A site with a date question and a capacity split dates its first phase by the date question.
`rest_earliest` (D-63 rule 8, the building entered by phase): in the early case the rest of the row arrives at
max(first phase's start, rest_earliest) instead of with the first phase; the late case is unchanged; in the joint
check the rest may arrive in any year from that early year to the late one. It needs `first_share`, and may not be
after the inventory's year.

Tested and admissible ranges (D-63 rule 4). Each touched utility's range of first crossings across the scenarios is
labelled `range_kind`: "admissible" only if every date or capacity question that can affect the utility (as the joint
check reads "can affect") is a date whose two ends both rest on evidence (`ends: "evidence"`); otherwise "tested". A
tested range rests on an assumption about how late a start can be: no later start than a permit-based year is tested,
and a capacity question's late end is the inventory's permit-based year, so it is always tested. A utility that no
date or capacity question can affect is labelled "inventory dates only": its range is what the assignment cases give
on the inventory's own dates, which for permit-dated rows are an assumption and not evidence, so it is not called
admissible either.

Sites with a measured or operator-reported history (Epoch's timeline, site_energy.py's reported electricity) keep
it: a date, size, phases or capacity correction on one is refused in words. A site with a verified phased history
(D-28) keeps its phases: a date or capacity correction on it is refused too.

The scratch rebuild (one state at a time; see `scratch_state`)
--------------------------------------------------------------
A utility is a (utility, state) unit and every site is in one state, so a state's utilities depend only on that
state's sites and that state's factor. Each state with a corrected site is rebuilt on its own and evaluated on its
own; `reproduce()` checks that this gives exactly what the whole-panel evaluation gives.

For a scenario (a choice of history for every corrected site in the state): the corrected sites' loads are rebuilt
from the raw full load, the scenario's start and buildout.ramp_mw / phased_mw. The state's anchoring factor is
recomputed by build_inventory's arithmetic (state_anchor at 2024, mirrored in `_factor`), and where it differs from
the frozen factor every permit-based site in the state is rebuilt at the new factor. `fac.state_scale` carries the
factor each row was scaled by, which is how assignment.matrices recovers the unanchored loads (mw / state_scale), so
the "no anchoring" readings stay consistent.

What it holds fixed, stated:
  * The Epoch timelines and operator-reported histories are not rebuilt. Their 2024 contribution to a state's
    anchoring is carried as the frozen measured total less what the rebuild can recompute (`measured_fixed`).
  * Utility assignment by the map is not rerun. build_inventory's pick_utilities places sites largest first by
    their SCALED load against each utility's sales, so a changed factor could in principle move a map-placed site.
    That is not recomputed here; only an assign correction moves a site.
  * A site moved off the panel stays in its state's anchoring (state_anchor counts every dated site in the state,
    served by a panel utility or not), so an assign correction alone never moves a factor. A size, a date reaching
    2024, `not_a_site` or a measured flag can.

Scenarios (per state)
---------------------
  reference     every corrected site at its convention (D-61 5.4: the corrected inventory as built). Where sites have
                no convention, one reference variant per combination of their two ends. These variants are scenarios
                only: they no longer decide whether a utility has a reference. That is decided by
                pass_c_exact.reference_of, the one function the exact attribution uses too (the reference repair,
                docs/gate1/reference-repair-rule-2026-11-18.md, rules R2 to R4 and R6; D-72 item 4): a touched utility
                has a reference only if its place and as-built first crossing are the same at EVERY admissible setting
                of the date and capacity questions with no convention that are relevant to it (every start year,
                "never", every capacity case or arrival year, one per class of settings merged for the utility), with
                everything else at its convention; agreement at the two ends decides nothing. Over pass_c_exact.CEILING
                combinations the reference is undefined without the search. The place test has never read the
                provisional mark: a provisional convention is a convention here, unlike in the exact attribution. Where
                a reference is defined, every reference variant must show that place and crossing, and the run raises if
                one does not. The scenarios below are unchanged by the repair, and the result is still a test on the
                scenarios run, not an exhaustive one.
  all_earliest  every date and capacity question at its early end; all_latest at its late end.
  flips         each question flipped to its other end (both ends, from an interior convention year) from each
                reference variant, from all_earliest and from all_latest. This is the one-at-a-time check of whether a
                question is decisive. It is NOT every combination of every question, and it is exhaustive only where
                an earlier start means at least as much load in every year (D-58 rule 1.7), which holds for a site's
                own load but fails where a start of 2023 or later, or "never", moves the state's factor.
  envelope      for that failing case: `factor_varies()` checks, per state, whether any corrected site's 2024 load
                differs between its cases (an interval reaching 2023 or later, "never", a late capacity case at 2023
                or later). If so, every combination of those sites' questions is run (with the state's other questions
                all early and all late) when there are at most ENVELOPE_LIMIT combinations; otherwise the state is
                named and the envelope is reported as not run.

The place test, per touched utility
-----------------------------------
Touched: every utility a corrected site is on, was on, lists or listed as a candidate; and, in a state whose factor
changes in any scenario, every panel utility carrying data center load there; and every panel utility an open
question can affect (the joint check, below). Each is evaluated by
assignment.evaluate in every scenario: its place (group of the as-built first crossing; "comparison" if never and
its largest share is under CLEAN_BELOW; else "neither"), its as-built crossing, and ruling 4's four cases. The
output is an audit trail in three parts: the ORIGINAL (frozen inventory, no corrections), the corrected REFERENCE,
and the RANGE across every scenario run, labelled tested or admissible (above). A utility keeps its place if in every scenario its place is the
reference's, a cohort crossing is within one year of the reference's, and the four-case verdict measured against
the reference's group and crossing holds (a comparison utility under 0.5% throughout).

The place test's reference: a conditional diagnostic and no more (Joe, D-90, 2026-11-18)
---------------------------------------------------------------------------------------
The place test's list of reference-defining questions is narrower than the exact attribution's: it does not read the
provisional mark. Its reference is therefore the utility's reference only ON THE CONDITION that every provisional
convention is the site's start, and it is kept as a diagnostic on that condition. It cannot override an undefined exact
reference, and neither it nor "keeps its place" is by itself a ground for eligibility or for pruning a question. Every
row says so: `reference_is` is "conditional diagnostic"; `exact_reference_defined` and
`exact_reference_why_undefined` carry the exact attribution's reference for the same utility
(pass_c_exact.reference_of with the exact attribution's list); and where that reference is undefined (it turns on a
provisional convention, or it was not searched) while the place test still shows one,
`reference_shown_where_exact_is_undefined` is true and `reference_warning` says in words that the row's reference and
its "keeps its place" are the diagnostic only. The result's `place_test_reference` carries the condition once, and the
printed table carries it on every utility. Nothing in this module, in pass_c_exact.py or in anything that imports them
prunes a question or decides eligibility on the place test's reference or on `keeps_its_place` (read 2026-11-18; the
joins come from the joint check, and the exact attribution's kept sets from its own reference).

Decisive on a single flip (kept for the ledger; no longer the source of `joins`)
------------------------------------------------------------------------------
A question is (site, "assignment" | "date" | "capacity"). A date or capacity question is decisive on a single flip
for a utility if two scenarios that differ only in that question give it a different place or a crossing more than
one year apart. An assignment question (an unresolved site on the utility or listing it) is if putting the site off
the utility and on it (ruling 4's lower and upper case for that site, from the reference variants, all_earliest and
all_latest) does. Both readings are compared. Output: `decisive_on_a_single_flip` and `already_decisive_before`.
Flips from a few starting points cannot show which questions matter (two of four equal sites needed: no single flip
from none or from all shows any of them, and every one is pivotal), which is why D-63 rule 7 replaced them.

The joint check (D-63 rule 7; `joint_check()`), the source of `joins`
-------------------------------------------------------------------
Per state. The questions: every unresolved or reopened assignment among the state's sites, as assignment.resolved
reads the corrected inventory, whose site carries load in some setting (settings: each candidate, the utility it is
on, and off the panel, as ruling 4's lower case takes it off); every date question at every year of its interval
(open below = full load from 2001 with no ramp; "never" where possible); every capacity case (with rest_earliest,
every year the rest may arrive). A site with several questions is one site; its settings are their product. Per
utility, year, reading (as built; with no anchoring) and threshold (`theta`; the comparison floor CLEAN_BELOW), the
utility's whole load lies between a lower and an upper bound: fixed measured load, plus the factor's low (high) end,
or 1 with no anchoring, times the settled permit-based raw load plus, site by site, the least (greatest) raw load the
site can put on the utility that year over all its settings, plus the same for measured-type load. The factor's
range is `_factor` at the greatest and the least permit-based 2024 totals (and measured totals: a size correction
marked measured with a date question moves the factor from the measured side) over all settings, widened to 1.0
where the permit total can be zero; a grid check confirms `_factor` is non-increasing there, and if it fails the
band SCALE_LO to SCALE_HI is the range. A status is settled where both bounds are on one side of the threshold. A
question can affect a utility in a year if two settings differing only in it put different load on the utility that
year (its own load), or, as built only, if they differ in the site's 2024 anchoring contribution and the utility
carries factor-scaled load that year in some setting (the factor). A question is dropped for a utility only if no
unsettled cell is one it can affect; otherwise kept, and its site joins.

What it guarantees, and only this (D-65 item 5): over the MODELED loads and the ENUMERATED uncertainties, no question
that could change any threshold status of the utility, in any year, reading or configuration of the other questions,
is dropped. A row with no size or no start year carries no load in any setting; that is a limit of the inventory and
not a finding that its load is nil, and `missing_inputs()` counts such rows, per state and for the inventory, beside
every result. A fixed history on a row not marked measured, and an unresolved row with a size, a start year and
candidates but no current utility, are refused in words (D-66 section 2; the frozen inventory has neither). Its group, first crossing and comparison eligibility are functions
of those statuses, so none of them can turn on a dropped question. It rests on two things: that the bounds are true
outer bounds (they are widened outward by a small tolerance for rounding, and the factor's range by the rebuild's
snapping tolerance), and that "can affect" misses no channel (a site's own load on the utility, through assignment,
date, phase or size; and the state's factor). What it ignores: the one-year tolerance of the place test, which can
only add questions. What is outside it: the map's choice of utility is not rerun when a factor moves (as stated
below); and the three- and five-years-earlier screen on permit-dated sites with no correction (D-58) is a separate
assumption and is not a question here. It over-includes by design: on a utility with one unsettled year, every
question with load there is kept, whether or not it could tip it. A utility with no positive base is read as
assignment.evaluate reads it: it never crosses the host threshold, and any load puts it over the floor.

Touched utilities are those listed above and every panel utility some open question can affect. With no
corrections the joint check still reports the questions the frozen inventory's unresolved sites raise: they are a
property of the inputs (`expand` runs only the states with a correction; call `joint_check` for any other state).

Run:  python3 -I pipeline/facilities/pass_c_expand.py corrections.json [--theta 0.02] [--targets CSV] [--out JSON]
      python3 -I pipeline/facilities/pass_c_expand.py corrections.json --assignment-only     (the old test)
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import buildout  # noqa: E402

KEY = asg.KEY
THETA = 0.02
OFF = "off_panel"

INTERIM = ROOT / "data" / "interim"
YEARS = asg.YEARS
ANCHOR_YEAR = 2024
# Mirrors build_inventory: RAMP_YEARS, SCALE_LO / SCALE_HI, and which rows are measured (not scaled) in main().
RAMP_YEARS = buildout.RAMP_YEARS
SCALE_LO, SCALE_HI = 0.2, 3.0
MEASURED_BASIS = ("verified_public_figure", "operator_reported_energy")
# Open below (D-59 item 1): full load in every panel year with no ramp inside the panel. A ramp that starts here is
# already at full load in 2001.
OPEN_BELOW_START = YEARS[0] - RAMP_YEARS + 1
ENVELOPE_LIMIT = 4096
UNRESOLVED_LIMIT = 10
FACTOR_TOL = 1e-12
KINDS = ("assign", "narrow", "candidates", "reopen", "size", "date", "phases", "capacity_split", "not_a_site")
REOPENED = "reopened"                 # a verification the pass withdrew: unresolved, as assignment.resolved reads it
WIDENED = "candidates_widened"        # a candidates correction: unresolved, as assignment.resolved reads it
GUARANTEE = ("The joint check covers modeled loads and enumerated uncertainties only (D-65 item 5). A row with no size "
             "or no start year carries no load in any setting, which is a limit of the inventory and not a finding. The "
             "generic screen on uncorrected permit-dated rows is not a question in it, and the map's choice of utility "
             "is not rerun when a factor moves.")
ENDS = ("evidence", "tested")
EARLY, LATE, CONV = "early", "late", "convention"
# The place test's reference is a conditional diagnostic and no more (Joe, D-90, 2026-11-18; the module docstring).
REFERENCE_IS = "conditional diagnostic"
REFERENCE_CONDITION = ("The place test's reference is a conditional diagnostic (D-90). It is the utility's reference only on "
                       "the condition that every provisional convention is the site's start: the place test does not read "
                       "the provisional mark, so its list of reference-defining questions is narrower than the exact "
                       "attribution's. It cannot override an undefined exact reference, and neither it nor \"keeps its "
                       "place\" is by itself a ground for eligibility or for pruning a question.")


# ==================================================================================================================
# The assignment-only test (D-59 item 2 as D-60 ran it). Unchanged: the ledger cites its results.
# ==================================================================================================================

def apply_corrections(fac: pd.DataFrame, fy: pd.DataFrame, corrections: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame, set]:
    """Scratch copies of the inventory and the site-year loads with the corrections applied, and the utilities touched."""
    fac, fy = fac.copy(), fy.copy()
    touched = set()
    for c in corrections:
        fid = c["fid"]
        if fid not in fac.index:
            raise KeyError(f"{fid} is not in the inventory")
        old = (int(fac.utility_id_eia[fid]), fac.state[fid]) if pd.notna(fac.utility_id_eia[fid]) else None
        if old:
            touched.add(old)
        for cand in asg.candidates(fac.utility_candidates[fid]):           # a site that leaves the unresolved list changes its candidates' upper cases
            touched.add((cand, fac.state[fid]))
        if c["to"] == OFF:
            fy = fy[fy.fid != fid]
            fac.loc[fid, "utility_assign"] = "wholesale_direct"
        else:
            new = (int(c["to"][0]), c["to"][1])
            fy.loc[fy.fid == fid, "utility_id_eia"] = new[0]
            fac.loc[fid, "utility_id_eia"] = new[0]
            fac.loc[fid, "utility_assign"] = "verified_by_hand"
            touched.add(new)
    return fac, fy, touched


def place(first_year, max_share: float) -> str:
    g = asg.group(first_year)
    if g == "never":
        return "comparison" if max_share < asg.CLEAN_BELOW else "neither"
    return g


def test(corrections: list[dict], inputs=None, theta: float = THETA) -> pd.DataFrame:
    """One row per touched utility: its place before and after, the four-case verdict after, and its still-unresolved sites."""
    fac, fy, q, units, base, regions = inputs or asg.load_inputs()
    th = f"{theta:.0%}"
    before, _, _ = asg.evaluate(fac, fy, units, base, regions, thresholds=(theta,))
    fac2, fy2, touched = apply_corrections(fac, fy, corrections)
    after, _, resolved = asg.evaluate(fac2, fy2, units, base, regions, thresholds=(theta,))
    names = q.groupby(KEY).utility_name.last()
    rows = []
    for k in sorted(u for u in touched if u in before.index):
        pb = place(before.at[k, f"as_built_{th}"], before.at[k, "max_share_as_built"])
        pa = place(after.at[k, f"as_built_{th}"], after.at[k, "max_share_as_built"])
        years = {name: after.at[k, f"{name}_{th}"] for name in asg.CASES}
        shares = {name: after.at[k, f"max_share_{name}"] for name in ("upper_as_built", "upper_no_anchoring")}
        verdict = asg.verdict(pa if pa in ("cohort", "early", "comparison") else "neither", after.at[k, f"as_built_{th}"], years, shares)
        years_b = {name: before.at[k, f"{name}_{th}"] for name in asg.CASES}
        shares_b = {name: before.at[k, f"max_share_{name}"] for name in ("upper_as_built", "upper_no_anchoring")}
        verdict_b = asg.verdict(pb if pb in ("cohort", "early", "comparison") else "neither", before.at[k, f"as_built_{th}"], years_b, shares_b)
        on = fy2[(fy2.utility_id_eia == k[0]) & (fy2.state == k[1])].drop_duplicates("fid").fid
        loose_on = [f for f in on if not resolved.get(f, False)]
        loose_cand = [f for f in fac2.index[~resolved & fac2.in_dose]
                      if k[0] in asg.candidates(fac2.utility_candidates[f]) and fac2.state[f] == k[1] and f not in set(on)]
        rows.append({"utility": f"{k[0]}:{k[1]}", "name": names.get(k), "place_before": pb, "first_crossing_before": asg.fmt(before.at[k, f"as_built_{th}"]),
                     "four_case_verdict_before": verdict_b, "place_after": pa, "first_crossing_after": asg.fmt(after.at[k, f"as_built_{th}"]),
                     "four_case_verdict_after": verdict,
                     # Newly decisive: the corrections changed this utility's place or verdict, and its place still turns on
                     # unresolved sites. A utility whose verdict was the same before the corrections is not new (the session's
                     # reading of "newly decisive", D-59 item 2): its unresolved sites were already known to decide it.
                     "changed_by_the_corrections": bool(pb != pa or verdict_b.split(":")[0] != verdict.split(":")[0]),   # the failing case, not its figure
                     # A utility that is now neither a host nor a comparison (or a late host) is not put through the four cases,
                     # but whether it can be a comparison still turns on any unresolved site on it or listing it.
                     "place_can_change_with_its_unresolved_sites": (verdict not in ("keeps its place", "not tested")
                                                                    or (pa in ("neither", "late") and bool(loose_on or loose_cand))),
                     "unresolved_sites_on_it": loose_on, "unresolved_sites_that_list_it": loose_cand})
    return pd.DataFrame(rows)


# ==================================================================================================================
# The broader test (D-61 section 4)
# ==================================================================================================================

def site_mw(history: tuple, mw_full: float, year: int) -> float:
    """A rebuildable site's load in `year`. Mirrors the ramp and phase branches of build_inventory.site_mw."""
    if pd.isna(mw_full):
        return 0.0
    if history[0] == "ramp":
        return buildout.ramp_mw(mw_full, history[1], year, RAMP_YEARS)
    if history[0] == "phases":
        return buildout.phased_mw(mw_full, history[1], year)
    if history[0] == "never":
        return 0.0
    raise ValueError(f"a {history[0]} history is not rebuilt here")


def _factor(epri: float, measured_twh: float, permit_twh: float) -> float:
    """build_inventory.state_anchor's factor for one state, mirrored: the EPRI total less measured load, over the permit total."""
    raw = max(epri - measured_twh, 0.0) / permit_twh if permit_twh != 0 else math.nan
    return 1.0 if math.isnan(raw) else min(max(raw, SCALE_LO), SCALE_HI)


@dataclass
class Inputs:
    """The frozen inventory, and what the scratch rebuild needs from it. Load and sales only."""
    fac: pd.DataFrame                  # indexed by fid
    fy: pd.DataFrame                   # data-center site-years (no crypto), as assignment.load_inputs gives
    units: pd.MultiIndex
    base: pd.Series
    regions: pd.Series
    names: pd.Series
    anchor: pd.DataFrame               # by state: epri_twh, permit_twh, epoch_twh, factor (state_anchor.parquet)
    phases: dict
    frozen_2024_mw: dict               # fixed-history rows: the MW each counted in its state's 2024 anchoring
    fy_all: pd.DataFrame | None = None
    hist: dict = field(default_factory=dict)
    fixed: pd.Series | None = None     # True for histories this module does not rebuild (Epoch, operator-reported)
    measured: pd.Series | None = None
    a2024: pd.Series | None = None     # TWh each rebuildable dated row counts in the 2024 anchoring
    measured_fixed: pd.Series | None = None

    @classmethod
    def build(cls, fac, fy, units, base, regions, names, anchor, phases, frozen_2024_mw, fy_all=None) -> "Inputs":
        inp = cls(fac, fy, units, base, regions, names, anchor, phases, dict(frozen_2024_mw), fy_all)
        inp.fixed = (fac.src == "epoch") | (fac.load_history == "operator_reported_energy")
        inp.measured = (fac.src == "epoch") | fac.mw_basis.isin(MEASURED_BASIS)       # build_inventory.main's `measured`
        odd = sorted(fac.index[inp.fixed & ~inp.measured])
        if odd:
            raise ValueError(f"{len(odd)} row(s) have a fixed history (Epoch's timeline or operator-reported energy) but are "
                             f"not marked measured, so their load would be scaled by the state's factor without being rebuilt: "
                             f"{', '.join(odd[:10])}. That combination is not supported (D-65 item 1, D-66 section 2): the "
                             f"no-anchoring reading of such a row moves with the factor and the joint check does not carry "
                             f"that effect. Mark the row measured or give it a rebuildable history.")
        for fid in fac.index:
            inp.hist[fid] = inp.frozen_history(fid)
        inp.a2024 = pd.Series({fid: inp.anchor_twh(fac.loc[fid], inp.hist[fid]) for fid in fac.index}, dtype=float)
        computed = inp.a2024[inp.measured & ~inp.fixed].groupby(fac.state).sum()
        inp.measured_fixed = (anchor.epoch_twh - computed.reindex(anchor.index).fillna(0.0))
        return inp

    def frozen_history(self, fid: str) -> tuple:
        r = self.fac.loc[fid]
        if self.fixed[fid]:
            return ("fixed",)
        if fid in self.phases:                                             # build_inventory.site_mw checks phases first
            return ("phases", self.phases[fid])
        return ("ramp", float(r.energized_year)) if pd.notna(r.energized_year) else ("never",)

    @staticmethod
    def anchor_twh(r, history) -> float:
        """What a row counts for in its state's 2024 anchoring: state_anchor takes rows with a year and a load."""
        if history[0] == "fixed" or pd.isna(r.energized_year) or pd.isna(r.mw_full_raw):
            return 0.0
        return site_mw(history, r.mw_full_raw, ANCHOR_YEAR) * 8.76 / 1000.0

    def frozen_factor(self, st: str) -> float:
        return float(self.anchor.factor[st]) if st in self.anchor.index else 1.0


SNAPSHOT_NAME = "snapshot-2026-11-14"
FROZEN_FRAME_FILES = ("facilities.parquet", "facility_year.parquet", "utility_year_dose.parquet", "state_anchor.parquet",
                      "epoch_gaps.parquet")


def frozen_frame_dir(interim: Path | None = None) -> Path:
    """Where the frozen inventory of 2026-11-14 is: data/interim itself, unless the live inventory is a step D rebuild
    (its facilities.parquet carries `date_rule`, the test the step D modules use), in which case its snapshot. The pass's
    corrections are written against the frozen inventory and must never be read against the rebuild (step D)."""
    import pyarrow.parquet as pq
    interim = Path(interim or INTERIM)
    live = interim / "facilities.parquet"
    if not live.exists() or "date_rule" not in pq.read_schema(live).names:
        return interim
    snap = interim / SNAPSHOT_NAME
    missing = [f for f in FROZEN_FRAME_FILES if not (snap / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"data/interim is the step D rebuild and the frozen inventory of 2026-11-14 is not in {snap} (missing: "
            f"{', '.join(missing)}). The pass's tools read the frozen inventory only. Recreate it: run "
            f"`python3 -I pipeline/facilities/apply_verified.py --no-pass-records` and "
            f"`python3 -I pipeline/facilities/build_inventory.py --no-step-d`, copy the six inventory files "
            f"(facilities, facility_year, utility_year_dose, state_anchor, state_load_by_year, epoch_gaps) into {snap}, "
            f"then rebuild step D again.")
    return snap


def load_frozen(interim: Path | None = None) -> Inputs:
    """The frozen inputs (load and sales only; nothing is written): the frozen inventory of 2026-11-14 from
    frozen_frame_dir (data/interim, or its snapshot once data/interim is the step D rebuild); the sales side from
    data/interim."""
    frame = frozen_frame_dir(interim)
    fac, fy, q, units, base, regions = asg.load_inputs(frame_dir=frame)
    fy_all = pd.read_parquet(frame / "facility_year.parquet")
    anchor = pd.read_parquet(frame / "state_anchor.parquet").set_index("state")
    gaps = pd.read_parquet(frame / "epoch_gaps.parquet").set_index("fid")
    phases = buildout.phases_by_site(buildout.load())
    names = q.groupby(KEY).utility_name.last()
    # A fixed-history row's 2024 anchoring contribution is its 2024 site-year, except in an Epoch gap year: the
    # anchoring counts Epoch's timeline there (zero before its first entry), not the assumed line (build_inventory, D-45).
    fixed = fac.index[(fac.src == "epoch") | (fac.load_history == "operator_reported_energy")]
    y24 = fy_all[fy_all.year == ANCHOR_YEAR].groupby("fid").mw.sum()
    frozen_2024 = {}
    for fid in fixed:
        if fid in gaps.index and gaps.sourced_start[fid] <= ANCHOR_YEAR < gaps.first_entry_year[fid]:
            frozen_2024[fid] = 0.0
        elif bool(fac.in_dose[fid]):
            frozen_2024[fid] = float(y24.get(fid, 0.0))
    return Inputs.build(fac, fy, units, base, regions, names, anchor, phases, frozen_2024, fy_all)


# ---- corrections -------------------------------------------------------------------------------------------------

@dataclass
class Correction:
    """Every correction to one site, validated."""
    fid: str
    state: str
    assign: object = None              # None, OFF, or (utility_id_eia, state)
    narrow: list | None = None
    widen: list | None = None          # a candidates correction: the inventory's list with possible suppliers added
    reopen: list | None = None
    size: float | None = None
    size_measured: bool = False
    date: dict | None = None
    phases: list | None = None
    split: dict | None = None
    not_a_site: bool = False
    inventory_year: float | None = None

    def questions(self) -> list[str]:
        return (["date"] if self.date else []) + (["capacity"] if self.split else [])

    def convention(self, q: str):
        """The question's convention as early / late / convention (an interior year), or None if unresolved."""
        if q == "capacity":
            return self.split.get("convention")
        d = self.date
        c = d.get("convention")
        if c is None:
            return None
        if c == "never":
            return LATE
        if d.get("earliest") is not None and c == d["earliest"]:
            return EARLY
        if not d.get("never_is_possible") and d.get("latest") is not None and c == d["latest"]:
            return LATE
        return CONV

    def start(self, value):
        """The start year (or 'never') the date question takes at `value`: an end, the convention, or a year itself
        (the joint check sets a date question at every year of its interval, and at "never" where that is possible)."""
        d = self.date
        if isinstance(value, str):
            if value == EARLY:
                return d["earliest"] if d.get("earliest") is not None else OPEN_BELOW_START
            if value == LATE:
                return "never" if d.get("never_is_possible") else d["latest"]
            if value == "never":
                return "never"
            return d["convention"]
        return value

    def history(self, choice: dict) -> tuple | None:
        """The site's history in a scenario, or None if the corrections leave its frozen history alone."""
        if self.not_a_site:
            return ("never",)
        if self.phases:
            return ("phases", [(int(y), float(s)) for y, s in self.phases])
        if not self.date and not self.split:
            return None
        pick = {q: choice.get((self.fid, q), CONV) for q in self.questions()}
        for q, v in pick.items():
            if v == CONV:
                v = self.convention(q)
                if v is None:
                    raise ValueError(f"{self.fid}: its {q} question is unresolved (no convention); a scenario has to choose an end")
                pick[q] = v
        first = self.start(pick["date"]) if self.date else self.split["first_phase_year"]
        if first == "never":
            return ("never",)
        if not self.split:
            return ("ramp", float(first))
        v, rest_earliest = pick["capacity"], self.split.get("rest_earliest")
        if v == EARLY and rest_earliest is None:
            return ("ramp", float(first))
        # The rest of the row: with the first phase but not before `rest_earliest` (early), at the inventory year (late),
        # or in a given year (the joint check's settings), never before the first phase.
        rest = max(float(first), float(rest_earliest if v == EARLY else self.inventory_year if v == LATE else v))
        if self.split.get("first_share") is None:
            return ("ramp", rest)
        return ("phases", [(float(first), float(self.split["first_share"])), (rest, 1.0)])


def check_unresolved_count(corrections: list[dict]) -> None:
    loose = sorted({c["fid"] for c in corrections
                    if c.get("kind") in ("date", "capacity_split") and c.get("convention") is None})
    if len(loose) > UNRESOLVED_LIMIT:
        raise ValueError(f"{len(loose)} sites have an unresolved start or capacity question, more than {UNRESOLVED_LIMIT}: "
                         f"the place test would run 2^{len(loose)} reference variants (one per combination of their two "
                         f"ends) as scenarios. Split the run. Sites: {', '.join(loose)}")


def parse_corrections(corrections: list[dict], inp: Inputs) -> dict[str, Correction]:
    """Validate the corrections against the inventory, one Correction per site. Refuses in words what cannot be applied."""
    out: dict[str, Correction] = {}
    seen: set = set()
    for c in corrections:
        fid, kind = c.get("fid"), c.get("kind")
        if fid not in inp.fac.index:
            raise ValueError(f"{fid} is not in the inventory")
        if kind not in KINDS:
            raise ValueError(f"{fid}: unknown kind of correction {kind!r}; known: {', '.join(KINDS)}")
        if (fid, kind) in seen:
            raise ValueError(f"{fid}: two {kind} corrections; give one")
        seen.add((fid, kind))
        r = inp.fac.loc[fid]
        x = out.setdefault(fid, Correction(fid=fid, state=r.state, inventory_year=r.energized_year))
        fixed = bool(inp.fixed[fid])
        if kind in ("date", "size", "phases", "capacity_split") and fixed:
            raise ValueError(f"{fid} has a measured or operator-reported history ({r.load_history}); it keeps that history, "
                             f"and a {kind} correction cannot be applied to it")
        if kind in ("date", "capacity_split") and fid in inp.phases:
            raise ValueError(f"{fid} has a verified phased history (D-28); its phases stay where their records put them, "
                             f"and a {kind} correction cannot be applied to it")
        if kind == "assign":
            to = c["to"]
            if to != OFF:
                to = (int(to[0]), str(to[1]))
                if to[1] != r.state:
                    raise ValueError(f"{fid} is in {r.state}; it cannot be assigned to a utility in {to[1]}")
            x.assign = to
        elif kind == "reopen":
            cands = [int(u) for u in (c.get("candidates") or [])]
            if not cands:
                raise ValueError(f"{fid}: a reopened site's candidate list cannot be empty")
            if r.utility_assign not in asg.VERIFIED:
                raise ValueError(f"{fid} is not verified in the frozen inventory (it is placed '{r.utility_assign}'); only a "
                                 f"verified site's verification can be withdrawn and reopened")
            if fixed and fid not in set(inp.fy.fid):
                raise ValueError(f"{fid} has a measured history with no site-years on file (it carries no load in the dose); "
                                 f"its load cannot be put on a candidate here")
            x.reopen = list(dict.fromkeys(cands))
        elif kind == "candidates":
            cands = list(dict.fromkeys(int(u) for u in (c.get("candidates") or [])))
            if r.utility_assign in asg.VERIFIED:
                raise ValueError(f"{fid} is verified in the frozen inventory ('{r.utility_assign}'); its candidates change only "
                                 f"when its verification is withdrawn, with a reopen correction")
            if pd.isna(r.utility_id_eia):
                raise ValueError(f"{fid} is on no utility in the inventory; a candidates correction adds possible suppliers to "
                                 f"a site the map has placed")
            missing = [u for u in asg.candidates(r.utility_candidates) if u not in cands]
            if missing:
                raise ValueError(f"{fid}: a candidates correction adds possible suppliers; this list leaves out {missing}, which "
                                 f"the inventory lists. Taking a candidate away is a narrow correction and has to meet D-63 rule 5")
            if int(r.utility_id_eia) not in cands:
                raise ValueError(f"{fid} is on utility {int(r.utility_id_eia)}, which has to stay among its candidates")
            x.widen = cands
        elif kind == "narrow":
            cands = [int(u) for u in c["candidates"]]
            if not cands:
                raise ValueError(f"{fid}: a narrowed candidate list cannot be empty")
            if pd.notna(r.utility_id_eia) and int(r.utility_id_eia) not in cands:
                raise ValueError(f"{fid} is on utility {int(r.utility_id_eia)}, which is not among the narrowed candidates "
                                 f"{cands}; move it with an assign correction instead")
            x.narrow = cands
        elif kind == "size":
            if not c["mw_full"] > 0:
                raise ValueError(f"{fid}: a size has to be positive; a site with no load is not_a_site")
            x.size, x.size_measured = float(c["mw_full"]), bool(c.get("measured", False))
        elif kind == "date":
            e, l, never, conv = c.get("earliest"), c.get("latest"), bool(c.get("never_is_possible", False)), c.get("convention")
            ends = c.get("ends", "tested")
            if ends not in ENDS:
                raise ValueError(f"{fid}: a date's ends are 'evidence' (both ends rest on evidence) or 'tested', not {ends!r}")
            if l is None and not never:
                raise ValueError(f"{fid}: an interval open above has to allow 'never' (never_is_possible: true)")
            if e is not None and l is not None and e > l:
                raise ValueError(f"{fid}: earliest {e} is after latest {l}")
            if conv == "never" and not never:
                raise ValueError(f"{fid}: the convention is 'never' but the interval does not allow it")
            if conv not in (None, "never"):
                hi = math.inf if never else l
                if (e is not None and conv < e) or conv > hi:
                    raise ValueError(f"{fid}: the convention year {conv} is outside its interval")
            prov = c.get("convention_is")
            if prov not in (None, "provisional"):
                raise ValueError(f"{fid}: convention_is is 'provisional' or absent, not {prov!r}")
            if prov and conv in (None, "never"):
                raise ValueError(f"{fid}: a provisional convention is a year; this date has none")
            x.date = {"earliest": e, "latest": l, "never_is_possible": never, "convention": conv, "ends": ends,
                      "convention_is": prov}
        elif kind == "phases":
            p = [(int(y), float(s)) for y, s in c["phases"]]
            if not p or any(b[1] < a[1] or b[0] < a[0] for a, b in zip(p, p[1:])) or abs(p[-1][1] - 1.0) > 1e-9:
                raise ValueError(f"{fid}: phases must be in year order with cumulative shares rising to 1")
            x.phases = p
        elif kind == "capacity_split":
            s = c.get("first_share")
            if s is not None and not 0 < s < 1:
                raise ValueError(f"{fid}: a first phase's share has to be between 0 and 1")
            if c.get("convention") not in (None, EARLY, LATE):
                raise ValueError(f"{fid}: a capacity split's convention is 'early', 'late' or null")
            if pd.isna(r.energized_year):
                raise ValueError(f"{fid}: a capacity split needs the inventory's year for the rest, and the row has none")
            re_ = c.get("rest_earliest")
            if re_ is not None:
                if s is None:
                    raise ValueError(f"{fid}: rest_earliest holds back the rest of the row, so it needs the first phase's share "
                                     f"(first_share)")
                if re_ > r.energized_year:
                    raise ValueError(f"{fid}: rest_earliest {re_} is after the inventory's year {int(r.energized_year)}, where "
                                     f"the late case puts the rest")
                re_ = int(re_)
            x.split = {"first_phase_year": c.get("first_phase_year"), "first_share": s, "convention": c.get("convention"),
                       "rest_earliest": re_}
        elif kind == "not_a_site":
            x.not_a_site = True
    for fid, x in out.items():
        if x.not_a_site and (x.date or x.phases or x.split or x.size):
            raise ValueError(f"{fid}: not_a_site carries no load in any case; drop its other load corrections")
        if x.phases and (x.date or x.split):
            raise ValueError(f"{fid}: a dated build-out is held fixed in every case; it cannot also have a date or capacity question")
        if x.assign is not None and x.narrow is not None:
            raise ValueError(f"{fid}: an assigned site has no candidates left to narrow")
        if x.reopen is not None and (x.assign is not None or x.narrow is not None):
            raise ValueError(f"{fid}: a reopen gives the site its candidates; it cannot come with an assign or a narrow "
                             f"correction on the same site")
        if x.widen is not None and (x.assign is not None or x.narrow is not None or x.reopen is not None):
            raise ValueError(f"{fid}: a candidates correction cannot come with an assign, a narrow or a reopen on the same site")
        if x.split and not x.date and x.split["first_phase_year"] is None:
            raise ValueError(f"{fid}: a capacity split needs its first phase's year, or a date question that dates it")
        if (x.date or x.phases or x.split) and pd.isna(inp.fac.mw_full_raw[fid]) and x.size is None:
            raise ValueError(f"{fid}: the row has no full load to rebuild; give a size correction with the date")
        if pd.isna(x.state):
            raise ValueError(f"{fid}: the row has no state")
    return out


# ---- the scratch rebuild -----------------------------------------------------------------------------------------

def _apply_fields(fac: pd.DataFrame, measured: pd.Series, c: Correction) -> None:
    """A site's assignment, candidates and size as the corrections set them, on a scratch copy (in place).

    Shared by the scratch rebuild and the joint check so that the two cannot read a correction differently.
    A reopened site is unresolved with exactly the given candidates; it stays on the utility it is on when that is
    among them (the as-mapped reading), otherwise it is entered on the first candidate listed.
    """
    fid = c.fid
    if c.assign == OFF:
        fac.loc[fid, ["utility_id_eia", "utility_assign"]] = [np.nan, "wholesale_direct"]       # any of asg.VERIFIED's off-panel kinds
    elif c.assign is not None:
        fac.loc[fid, ["utility_id_eia", "utility_assign"]] = [float(c.assign[0]), "verified_by_hand"]
    if c.narrow is not None:
        fac.loc[fid, "utility_candidates"] = ";".join(str(u) for u in c.narrow)
    if c.widen is not None:
        fac.loc[fid, ["utility_assign", "utility_candidates"]] = [WIDENED, ";".join(str(u) for u in c.widen)]
    if c.reopen is not None:
        now = fac.utility_id_eia[fid]
        on = int(now) if pd.notna(now) and int(now) in c.reopen else c.reopen[0]
        fac.loc[fid, ["utility_id_eia", "utility_assign", "utility_candidates"]] = [float(on), REOPENED,
                                                                                    ";".join(str(u) for u in c.reopen)]
    if c.size is not None:
        fac.loc[fid, "mw_full_raw"] = c.size
        if c.size_measured:
            fac.loc[fid, "mw_basis"] = "verified_public_figure"
            measured[fid] = True


def scratch_state(inp: Inputs, corr: dict[str, Correction], st: str, choice: dict) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """One state's inventory and site-year loads with the corrections applied, for one scenario, and the state's factor.

    `choice` maps (fid, "date" | "capacity") to "early" | "late" | "convention"; a question left out takes its convention.
    """
    fac = inp.fac[inp.fac.state == st].copy()
    fy = inp.fy[inp.fy.state == st].copy()
    measured = inp.measured.reindex(fac.index).copy()
    a = inp.a2024.reindex(fac.index).copy()
    removed_fixed_twh = 0.0
    hist = {}
    mine = {fid: c for fid, c in corr.items() if c.state == st}
    for fid, c in mine.items():
        _apply_fields(fac, measured, c)
        h = c.history(choice)
        if c.not_a_site and inp.fixed[fid]:
            if fid not in inp.frozen_2024_mw:
                raise ValueError(f"{fid}: what this measured row counts in {st}'s 2024 anchoring is not on file "
                                 f"(it carries no load in the dose), so taking it out cannot be computed here")
            removed_fixed_twh += inp.frozen_2024_mw[fid] * 8.76 / 1000.0
            fac.loc[fid, "energized_year"] = np.nan
        if inp.fixed[fid] and not c.not_a_site:
            continue                                                       # an assignment only: its rows are moved below
        h = h or inp.hist[fid]
        hist[fid] = h
        fac.loc[fid, "energized_year"] = (np.nan if h[0] == "never" else
                                          h[1] if h[0] == "ramp" else
                                          fac.energized_year[fid] if pd.notna(fac.energized_year[fid]) else h[1][0][0])
        a[fid] = 0.0 if h[0] == "never" or inp.fixed[fid] else Inputs.anchor_twh(fac.loc[fid], h)

    rebuild_fixed = set(hist)
    permit = ~measured
    permit_twh = float(a[permit & ~inp.fixed.reindex(fac.index)].sum())
    measured_twh = float(inp.measured_fixed.get(st, 0.0)) - removed_fixed_twh + float(a[measured & ~inp.fixed.reindex(fac.index)].sum())
    epri = float(inp.anchor.epri_twh.get(st, 0.0)) if "epri_twh" in inp.anchor else 0.0
    factor = _factor(epri, measured_twh, permit_twh)
    frozen = inp.frozen_factor(st)
    if abs(factor - frozen) <= FACTOR_TOL * max(1.0, abs(frozen)):
        factor = frozen                                                    # summation order only; no change
    rebuild = set(rebuild_fixed)
    if factor != frozen:
        fac.loc[permit[permit].index, "state_scale"] = factor
        rebuild |= {f for f in fac.index[permit] if not inp.fixed[f]}
    # Fixed-history sites that were moved or taken off.
    for fid, c in mine.items():
        if inp.fixed[fid] and not c.not_a_site and c.assign is not None:
            if c.assign == OFF:
                fy = fy[fy.fid != fid]
            else:
                fy.loc[fy.fid == fid, "utility_id_eia"] = c.assign[0]
        if inp.fixed[fid] and c.reopen is not None:
            fy.loc[fy.fid == fid, "utility_id_eia"] = int(fac.utility_id_eia[fid])
        if inp.fixed[fid] and c.not_a_site:
            fy = fy[fy.fid != fid]
    fac["in_dose"] = fac.energized_year.notna() & fac.mw_full_raw.notna() & fac.utility_id_eia.notna()
    for fid, c in mine.items():
        if c.not_a_site:
            fac.loc[fid, "in_dose"] = False
    if not rebuild:
        return fac, fy, factor
    rows = []
    for fid in rebuild:
        scale = 1.0 if measured[fid] else factor
        fac.loc[fid, "state_scale"] = scale
        fac.loc[fid, "mw_full"] = fac.mw_full_raw[fid] * scale
        if not fac.in_dose[fid] or bool(fac.is_crypto[fid]):
            continue
        h = hist.get(fid, inp.hist[fid])
        u = int(fac.utility_id_eia[fid])
        for y in YEARS:
            mw = site_mw(h, fac.mw_full[fid], y)
            if mw > 0:
                rows.append((fid, u, st, y, mw))
    new = pd.DataFrame(rows, columns=["fid"] + KEY + ["year", "mw"]).astype({"utility_id_eia": fy.utility_id_eia.dtype,
                                                                               "year": fy.year.dtype})
    kept_rows = fy[~fy.fid.isin(rebuild)]
    fy = pd.concat([kept_rows, new], ignore_index=True) if len(new) else kept_rows.reset_index(drop=True)
    return fac, fy, factor


def factor_varies(inp: Inputs, corr: dict[str, Correction], st: str) -> dict:
    """Does the state's factor vary across scenarios? It does where any corrected site's 2024 load differs between its cases.

    D-58 rule 1.7 as D-61 5.3 keeps it: two corners are enough only where earlier starts mean at least as much load in
    every year, which fails where a date of 2023 or later (a ramp not full by 2024), or "never", moves the factor.
    Computed directly: each site's 2024 load under every combination of its own questions.
    """
    loads = {}
    for fid, c in corr.items():
        if c.state != st or not c.questions():
            continue
        r = inp.fac.loc[fid].copy()
        if c.size is not None:
            r["mw_full_raw"] = c.size
        vals = set()
        for combo in itertools.product((EARLY, LATE), repeat=len(c.questions())):
            h = c.history(dict(zip([(fid, q) for q in c.questions()], combo)))
            vals.add(round(0.0 if h[0] == "never" else site_mw(h, r.mw_full_raw, ANCHOR_YEAR), 9))
        if len(vals) > 1:
            loads[fid] = sorted(vals)
    return {"varies": bool(loads), "sites_whose_2024_load_varies": sorted(loads), "their_2024_mw_raw": loads}


# ---- the joint check (D-63 rule 7) -------------------------------------------------------------------------------

READINGS = ("as_built", "no_anchoring")
BOUND_EPS_ABS, BOUND_EPS_REL = 1e-6, 1e-9      # GWh: bounds are widened outward by this much before a status is settled
FACTOR_GRID = (65, 9)                          # the monotonicity check's grid: permit totals x measured totals


def _date_values(c: Correction) -> list:
    """Every setting of a date question: each start year of its interval, and "never" where that is possible.

    Starts at or before OPEN_BELOW_START all give full load from 2001 (open below), and starts after the last panel
    year all give no load in any panel year or in 2024; each is entered once, at the year nearest the panel.
    """
    d, top = c.date, YEARS[-1] + 1
    hi = top if d["latest"] is None else min(int(d["latest"]), top)
    lo = OPEN_BELOW_START if d["earliest"] is None else max(int(d["earliest"]), OPEN_BELOW_START)
    return list(range(min(lo, hi), hi + 1)) + (["never"] if d["never_is_possible"] else [])


def _capacity_values(c: Correction) -> list:
    """Every setting of a capacity question: its two cases, or with rest_earliest every year the rest may arrive."""
    re_ = c.split.get("rest_earliest")
    return [EARLY, LATE] if re_ is None else list(range(int(re_), int(c.inventory_year) + 1))


@dataclass
class _Site:
    fid: str
    kind: str                       # "permit" (scaled by the factor) or "measured" (not scaled)
    questions: list                 # names, in the order of the columns of idx
    values: list                    # each question's settings
    idx: np.ndarray                 # settings x questions: the index of each question's value
    unit: list                      # per setting: the panel unit the site is on, or None
    load: np.ndarray                # settings x years: MW (raw for a permit site, as carried for a measured one)
    a: np.ndarray                   # per setting: TWh it counts in its state's 2024 anchoring (permit or measured side)
    na_div: tuple = (1.0, 1.0)      # a measured site's divisor range for the no-anchoring reading (mw / state_scale)


def _sites(inp: Inputs, corr: dict[str, Correction], st: str, units) -> tuple[list, list, float]:
    """Every site of the state with its settings, as the scratch rebuild would build each one. Load and sales only."""
    unit_set = set(units)
    fac = inp.fac[inp.fac.state == st].copy()
    measured = inp.measured.reindex(fac.index).copy()
    mine = {fid: c for fid, c in corr.items() if c.state == st}
    removed_fixed_twh = 0.0
    for fid, c in mine.items():
        _apply_fields(fac, measured, c)
        if c.not_a_site and inp.fixed[fid]:
            if fid not in inp.frozen_2024_mw:
                raise ValueError(f"{fid}: what this measured row counts in {st}'s 2024 anchoring is not on file, so taking it "
                                 f"out cannot be bounded here")
            removed_fixed_twh += inp.frozen_2024_mw[fid] * 8.76 / 1000.0
    ercot = {k for k in units if inp.regions.get(k) == asg.ERCOT_REGION}
    res = asg.resolved(fac, ercot)
    fy_st = inp.fy[inp.fy.state == st]
    fixed_rows = {fid: g.groupby("year").mw.sum().reindex(YEARS).fillna(0.0).values for fid, g in fy_st.groupby("fid")}
    zeros = np.zeros(len(YEARS))
    sites, no_load = [], []
    for fid in fac.index:
        c, r = mine.get(fid), fac.loc[fid]
        fixed = bool(inp.fixed[fid])
        crypto = bool(r.is_crypto) if "is_crypto" in fac else False
        hq = c.questions() if (c is not None and not fixed) else []
        hist = []                                                          # (values of the date/capacity questions, MW by year, TWh in 2024)
        if fixed:
            # Not rebuilt: its site-years as frozen (moved with its assignment); its 2024 anchoring is in measured_fixed.
            hist.append(((), zeros if (c is not None and c.not_a_site) else fixed_rows.get(fid, zeros), 0.0))
        else:
            raw = r.mw_full_raw

            def one(h, corrected):
                if not corrected:
                    has, a = bool(inp.fac.in_dose[fid]), float(inp.a2024[fid])
                else:
                    never = h[0] == "never"
                    has = not never and pd.notna(raw) and not c.not_a_site
                    a = 0.0 if never or pd.isna(raw) else site_mw(h, raw, ANCHOR_YEAR) * 8.76 / 1000.0
                vec = np.array([site_mw(h, raw, y) for y in YEARS]) if has and not crypto else zeros
                return vec, a
            if c is None:
                hist.append(((), *one(inp.hist[fid], False)))
            elif not hq:
                hist.append(((), *one(c.history({}) or inp.hist[fid], True)))
            else:
                vals = [_date_values(c) if q == "date" else _capacity_values(c) for q in hq]
                for combo in itertools.product(*vals):
                    hist.append((combo, *one(c.history({(fid, q): v for q, v in zip(hq, combo)}), True)))
        u0 = int(r.utility_id_eia) if pd.notna(r.utility_id_eia) else None
        has_load = any(v.any() for _, v, _ in hist)
        if (not res[fid] and u0 is None and not crypto and asg.candidates(r.utility_candidates)
                and pd.notna(r.mw_full_raw) and r.mw_full_raw > 0
                and (pd.notna(r.energized_year) or (c is not None and (c.date or c.phases)))
                and not (c is not None and c.not_a_site)):
            raise ValueError(f"{fid} in {st} is unresolved, has a size, a start year and candidates "
                             f"({r.utility_candidates}) but is on no utility. The joint check has no as-mapped reading for "
                             f"such a row and does not invent one (D-65 item 5, D-66 section 2). Place it with a reopen or an "
                             f"assign correction, or mark it not_a_site.")
        if not res[fid] and u0 is not None and has_load:
            avals = list(dict.fromkeys([u0] + asg.candidates(r.utility_candidates))) + [None]   # on each candidate, or off the panel
            names = ["assignment"] + hq
        else:
            if not res[fid]:
                no_load.append(fid)
            avals, names = [u0], hq
        hvals = [_date_values(c) if q == "date" else _capacity_values(c) for q in hq] if hq else []
        idx, unit, load, a = [], [], [], []
        for ai, au in enumerate(avals):
            for combo, vec, tw in hist:
                pos = [hvals[i].index(v) for i, v in enumerate(combo)]
                idx.append(([ai] if names[:1] == ["assignment"] else []) + pos)
                unit.append((au, st) if au is not None and (au, st) in unit_set else None)
                load.append(vec)
                a.append(tw)
        kind = "measured" if (fixed or bool(measured[fid])) else "permit"
        s0 = float(inp.fac.state_scale[fid]) if pd.notna(inp.fac.state_scale[fid]) else 1.0
        if fixed:
            div = (s0, s0)                                                 # not rebuilt: the scale it carries (Inputs.build refuses one not measured)
        elif kind == "measured":
            div = (1.0, 1.0) if c is not None else (min(1.0, s0), max(1.0, s0))   # rebuilt at 1, or as frozen if not rebuilt
        else:
            div = (1.0, 1.0)
        sites.append(_Site(fid, kind, names, ([avals] if names[:1] == ["assignment"] else []) + hvals,
                           np.array(idx, dtype=int).reshape(len(idx), len(names)), unit, np.vstack(load), np.array(a), div))
    return sites, no_load, removed_fixed_twh


def missing_inputs(inp: Inputs, st: str | None = None) -> dict:
    """Rows counted by what is missing (D-65 item 5), for one state or, with st None, for the whole frozen inventory.

    A row with no size or no start year carries no load in any setting of the joint check. That is a limit of the
    inventory and not a finding. A row with no state sits in no state's check. Counted on the frozen inventory, before
    corrections; crypto rows included.
    """
    fac = inp.fac if st is None else inp.fac[inp.fac.state == st]
    ercot = {k for k in inp.units if inp.regions.get(k) == asg.ERCOT_REGION}
    res = asg.resolved(fac, ercot)
    no_size, no_year, no_util = fac.mw_full_raw.isna(), fac.energized_year.isna(), fac.utility_id_eia.isna()
    off = fac.utility_assign.isin([a for a in asg.VERIFIED if a != "verified_by_hand"])
    out = {"rows": int(len(fac)),
           "no_size": int(no_size.sum()), "no_start_year": int(no_year.sum()),
           "no_size_or_no_start_year": int((no_size | no_year).sum()),
           "no_current_utility": int(no_util.sum()),
           "no_current_utility_verified_off_the_panel": int((no_util & off).sum()),
           "no_current_utility_other": int((no_util & ~off).sum()),
           "unresolved": int((~res).sum()),
           "unresolved_no_size": int((~res & no_size).sum()), "unresolved_no_start_year": int((~res & no_year).sum()),
           "unresolved_with_no_load_in_the_inventory": int((~res & (no_size | no_year | no_util)).sum())}
    if st is None:
        ns = inp.fac.state.isna()
        out["no_state"] = int(ns.sum())
        out["no_state_rows"] = [{"fid": f, "mw_full_raw": (None if pd.isna(inp.fac.mw_full_raw[f]) else float(inp.fac.mw_full_raw[f])),
                                 "utility_assign": str(inp.fac.utility_assign[f])} for f in inp.fac.index[ns]]
    return out


def _factor_range(inp: Inputs, st: str, sites: list, removed_fixed_twh: float) -> dict:
    """The state's factor over every setting: _factor at the greatest totals and at the least, after a grid check."""
    epri = float(inp.anchor.epri_twh.get(st, 0.0)) if "epri_twh" in inp.anchor else 0.0
    perm = [s for s in sites if s.kind == "permit"]
    meas = [s for s in sites if s.kind == "measured"]
    p_lo, p_hi = sum(s.a.min() for s in perm), sum(s.a.max() for s in perm)
    m0 = float(inp.measured_fixed.get(st, 0.0)) - removed_fixed_twh
    m_lo, m_hi = m0 + sum(s.a.min() for s in meas), m0 + sum(s.a.max() for s in meas)
    can_be_zero = p_lo <= 0.0
    p_lo, p_hi, m_lo, m_hi = float(p_lo), float(p_hi), float(m_lo), float(m_hi)
    out = {"permit_twh_range": [p_lo, p_hi], "measured_twh_range": [m_lo, m_hi], "permit_total_can_be_zero": bool(can_be_zero),
           "band_used": False, "monotonicity_check": "not needed: the permit-based total is zero in every setting"}
    if p_hi <= 0.0:
        lo = hi = 1.0
    else:
        # The least positive permit total: with the settled total zero, at least one site is at its least positive setting.
        pos = [x for s in perm for x in s.a if x > 0]
        p_a = p_lo if p_lo > 0 else min(pos)
        lo, hi = _factor(epri, m_hi, p_hi), _factor(epri, m_lo, p_a)
        P = np.linspace(p_a, p_hi, FACTOR_GRID[0])
        M = np.linspace(m_lo, m_hi, FACTOR_GRID[1])
        F = np.array([[_factor(epri, m, p) for p in P] for m in M])
        ok = bool((np.diff(F, axis=1) <= 0).all() and (np.diff(F, axis=0) <= 0).all()
                  and F.min() >= lo and F.max() <= hi)
        out["monotonicity_check"] = (f"passed on a {FACTOR_GRID[0]} x {FACTOR_GRID[1]} grid of permit and measured totals" if ok else
                                     "FAILED: the band is used")
        if not ok:
            lo, hi, out["band_used"] = SCALE_LO, SCALE_HI, True
    if can_be_zero:
        lo, hi = min(lo, 1.0), max(hi, 1.0)
    out.update(low=float(lo), high=float(hi))
    return out


def joint_check(inp: Inputs, corr: dict[str, Correction], st: str, theta: float = THETA) -> dict:
    """D-63 rule 7 for one state: which open questions can change any threshold status of each panel utility there.

    Returns the questions considered, the factor's range, and per utility (keyed "utility:state") its unsettled
    (year, reading, threshold) cells, the questions that can affect it, the questions kept and their sites (joins).
    `bounds` holds the lower and upper bound on each utility's GWh by year in each reading (numpy arrays).
    """
    units = inp.units[inp.units.get_level_values("state") == st]
    sites, no_load, removed = _sites(inp, corr, st, units)
    fr = _factor_range(inp, st, sites, removed)
    tol = FACTOR_TOL * max(1.0, abs(inp.frozen_factor(st)))                # the rebuild snaps a factor this close to the frozen one
    f_lo, f_hi = fr["low"] - tol, fr["high"] + tol
    n = len(YEARS)
    z = lambda: np.zeros(n)  # noqa: E731
    acc = {k: {"r_lo": z(), "r_hi": z(), "m_lo": z(), "m_hi": z(), "mn_lo": z(), "mn_hi": z()} for k in units}
    for s in sites:
        if s.kind == "measured":
            d_lo, d_hi = s.na_div
        for k in {u for u in s.unit if u is not None}:
            on = np.array([u == k for u in s.unit])[:, None]
            lu = s.load * on
            lo, hi = lu.min(axis=0), lu.max(axis=0)
            if s.kind == "permit":
                acc[k]["r_lo"] += lo
                acc[k]["r_hi"] += hi
            else:
                acc[k]["m_lo"] += lo
                acc[k]["m_hi"] += hi
                acc[k]["mn_lo"] += lo / d_hi
                acc[k]["mn_hi"] += hi / d_lo
    thresholds = (theta, asg.CLEAN_BELOW)
    bounds, unsettled, scaled_up = {}, {}, {}
    for k in units:
        a = acc[k]
        b = {"as_built": (8.76 * (a["m_lo"] + f_lo * a["r_lo"]), 8.76 * (a["m_hi"] + f_hi * a["r_hi"])),
             "no_anchoring": (8.76 * (a["mn_lo"] + a["r_lo"]), 8.76 * (a["mn_hi"] + a["r_hi"]))}
        bounds[k] = b
        scaled_up[k] = f_hi * a["r_hi"] > 0
        base_k = inp.base.get(k, np.nan)
        cells = {}
        for reading, (lo, hi) in b.items():
            lo_e = lo - (BOUND_EPS_ABS + BOUND_EPS_REL * np.abs(lo))
            hi_e = hi + (BOUND_EPS_ABS + BOUND_EPS_REL * np.abs(hi))
            for th in thresholds:
                if pd.notna(base_k) and base_k > 0:
                    t = th * base_k
                    cells[(reading, th)] = ~((lo_e >= t) | (hi_e < t))
                elif th == theta and th != asg.CLEAN_BELOW:
                    cells[(reading, th)] = np.zeros(n, dtype=bool)          # no positive base: assignment never finds a crossing
                else:
                    cells[(reading, th)] = ~((lo_e > 0) | (hi == 0))         # no positive base: any load makes the share infinite
        unsettled[k] = cells
    # Can each question affect each utility, year by year? Own load: two settings that differ only in this question put
    # different load on the utility. Factor: two such settings differ in the site's 2024 anchoring contribution.
    questions, affect = [], {k: [] for k in units}
    for s in sites:
        for qi, q in enumerate(s.questions):
            questions.append({"fid": s.fid, "question": q, "settings": len(s.values[qi])})
            others = np.delete(s.idx, qi, axis=1)
            _, grp = np.unique(others, axis=0, return_inverse=True) if others.shape[1] else (None, np.zeros(len(s.idx), dtype=int))
            grp = np.asarray(grp).ravel()
            # The factor channel needs the factor to be able to move: where its outer bounds coincide (a state held at the
            # band's edge in every setting) it is one number in every configuration and no question reaches anyone through it.
            moves_factor = fr["high"] > fr["low"] and any(np.ptp(s.a[grp == g]) > 0 for g in np.unique(grp))
            own = {}
            for k in {u for u in s.unit if u is not None}:
                lu = s.load * np.array([u == k for u in s.unit])[:, None]
                own[k] = np.zeros(n, dtype=bool)
                for g in np.unique(grp):
                    rows = lu[grp == g]
                    own[k] |= rows.max(axis=0) != rows.min(axis=0)
            for k in (units if moves_factor else own):
                o = own.get(k, np.zeros(n, dtype=bool))
                f = (moves_factor & scaled_up[k]) if moves_factor else np.zeros(n, dtype=bool)
                if o.any() or f.any():
                    affect[k].append((s.fid, q, o, f))
    utilities = {}
    for k in units:
        cells = unsettled[k]
        ab = cells[("as_built", theta)] | cells[("as_built", asg.CLEAN_BELOW)]
        na = cells[("no_anchoring", theta)] | cells[("no_anchoring", asg.CLEAN_BELOW)]
        kept = []
        for fid, q, o, f in affect[k]:
            by_own, by_factor = bool((o & (ab | na)).any()), bool((f & ab).any())
            if by_own or by_factor:
                kept.append({"fid": fid, "question": q,
                             "channel": "both" if by_own and by_factor else "own load" if by_own else "factor"})
        cell_list = [[int(y), reading, th] for (reading, th), v in cells.items() for y, x in zip(YEARS, v) if x]
        cell_list.sort(key=lambda c: (c[0], c[1], c[2]))
        utilities[f"{k[0]}:{k[1]}"] = {
            "unsettled": cell_list, "n_unsettled": len(cell_list),
            "can_affect": [{"fid": fid, "question": q} for fid, q, _, _ in affect[k]],
            "kept_questions": kept, "joins": sorted({x["fid"] for x in kept})}
    return {"state": st, "questions": questions, "factor_range": fr,
            "unresolved_sites_with_no_load_in_any_setting": sorted(no_load),
            "missing_inputs": missing_inputs(inp, st), "guarantee": GUARANTEE,
            "utilities": utilities, "bounds": bounds}


# ---- evaluation --------------------------------------------------------------------------------------------------

def _outcomes(t: pd.DataFrame, m: dict, base: pd.Series, theta: float) -> dict:
    """Per utility: place, crossing, the no-anchoring place and crossing, the four cases and the upper-case shares."""
    th = f"{theta:.0%}"
    na = asg.first_crossing(m["no_anchoring"], base, theta)
    na_share = asg.max_share(m["no_anchoring"], base)
    out = {}
    for k in t.index:
        ab = t.at[k, f"as_built_{th}"]
        out[k] = {"place": place(ab, t.at[k, "max_share_as_built"]), "crossing": ab,
                  "place_na": place(na[k], na_share[k]), "crossing_na": na[k],
                  "cases": {c: t.at[k, f"{c}_{th}"] for c in asg.CASES},
                  "shares": {c: t.at[k, f"max_share_{c}"] for c in ("upper_as_built", "upper_no_anchoring")}}
    return out


def _row_outcome(ab: np.ndarray, na: np.ndarray, base_k: float, theta: float) -> tuple:
    """(place, crossing, place with no anchoring, crossing with no anchoring) from one utility's GWh by year."""
    def one(v):
        hit = (v >= theta * base_k) & (base_k > 0)
        first = float(YEARS[int(np.argmax(hit))]) if hit.any() else np.nan
        top = v.max()
        share = (top / base_k) if top > 0 else 0.0
        return place(first, share), first
    p, c = one(ab)
    pn, cn = one(na)
    return p, c, pn, cn


def _differs(a: tuple, b: tuple) -> bool:
    """Two outcomes differ if the place differs or a crossing moves by more than a year, as built or with no anchoring."""
    return a[0] != b[0] or not asg.same_place(a[1], b[1]) or a[2] != b[2] or not asg.same_place(a[3], b[3])


def _key4(o: dict) -> tuple:
    return (o["place"], o["crossing"], o["place_na"], o["crossing_na"])


def _vplace(p: str) -> str:
    return p if p in ("cohort", "early", "comparison") else "neither"


def _same_value(a, b) -> bool:
    return (pd.isna(a) and pd.isna(b)) or a == b


def _assignment_decisive(fac, fy, m, res, k, base_k, theta) -> set:
    """Unresolved sites on utility k, or listing it, whose being off it or on it changes its place (ruling 4, site by site)."""
    u, st = k
    scale = fac.state_scale.reindex(fy.fid).fillna(1.0).values
    rows = fy.assign(gwh=fy.mw.values * 8.76, gwh_a=fy.mw.values / scale * 8.76)
    ab0 = m["as_built"].loc[k].reindex(YEARS).values.astype(float)
    na0 = m["no_anchoring"].loc[k].reindex(YEARS).values.astype(float)
    loose = fac.index[~res.reindex(fac.index).fillna(False).astype(bool) & fac.in_dose.astype(bool)]
    out = set()
    for fid in loose:
        on = pd.notna(fac.utility_id_eia[fid]) and int(fac.utility_id_eia[fid]) == u
        lists = u in asg.candidates(fac.utility_candidates[fid])
        if not (on or lists):
            continue
        s = rows[rows.fid == fid]
        if not len(s):
            continue
        v = s.groupby("year").gwh.sum().reindex(YEARS).fillna(0.0).values
        va = s.groupby("year").gwh_a.sum().reindex(YEARS).fillna(0.0).values
        if on:
            with_it, without = (ab0, na0), (ab0 - v, na0 - va)
        else:
            with_it, without = (ab0 + v, na0 + va), (ab0, na0)
        if _differs(_row_outcome(*with_it, base_k, theta), _row_outcome(*without, base_k, theta)):
            out.add(fid)
    return out


def _fmt(y):
    return asg.fmt(y)


def reference_diagnostic(place_test_has_reference: bool, exact: dict) -> dict:
    """The fields that mark a place-test row's reference as a conditional diagnostic (Joe, D-90).

    `exact` is the exact attribution's reference record for the same utility: pass_c_exact.reference_of with the exact
    attribution's list of reference-defining questions, which reads the provisional mark. Where it is undefined (it turns
    on a question, or it was not searched) and the place test still shows a reference, the row is flagged and says in
    words that its reference and its "keeps its place" are the diagnostic only. The place test's reference never
    overrides the exact one, and this function is the only place the two are put side by side."""
    shown = bool(place_test_has_reference and not exact["defined"])
    warning = None
    if shown:
        warning = (f"The exact attribution's reference for this utility is undefined ({exact['why_undefined']}). The "
                   f"reference and \"keeps its place\" on this row are the place test's conditional diagnostic only: they "
                   f"do not override the undefined exact reference, and they are not a ground for eligibility or for "
                   f"pruning a question (D-90).")
    return {"reference_is": REFERENCE_IS, "exact_reference_defined": bool(exact["defined"]),
            "exact_reference_why_undefined": exact["why_undefined"],
            "reference_shown_where_exact_is_undefined": shown, "reference_warning": warning}


def run_state(inp: Inputs, corr: dict[str, Correction], st: str, theta: float) -> dict:
    """Every scenario for one state, and the place test for every utility it touches there."""
    units = inp.units[inp.units.get_level_values("state") == st]
    base, regions = inp.base.reindex(units), inp.regions.reindex(units)
    mine = {fid: c for fid, c in corr.items() if c.state == st}
    qs = [(fid, q) for fid, c in mine.items() for q in c.questions()]
    loose = [q for q in qs if mine[q[0]].convention(q[1]) is None]

    scen: dict = {}

    def add(name: str, choice: dict) -> tuple:
        norm = {q: (mine[q[0]].convention(q[1]) or v) if v == CONV else v for q, v in choice.items()}
        # A convention that sits at an end of its interval is that end: one history, one scenario.
        key = tuple(sorted(norm.items()))
        scen.setdefault(key, {"names": [], "choice": norm})
        if name not in scen[key]["names"]:
            scen[key]["names"].append(name)
        return key

    ref_keys = []
    for combo in itertools.product((EARLY, LATE), repeat=len(loose)):
        pick = dict(zip(loose, combo))
        label = "reference" + (" [" + ", ".join(f"{f} {q}={v}" for (f, q), v in pick.items()) + "]" if pick else "")
        ref_keys.append(add(label, {q: pick.get(q, CONV) for q in qs}))
    ae = add("all_earliest", {q: EARLY for q in qs})
    al = add("all_latest", {q: LATE for q in qs})
    bases = list(dict.fromkeys(ref_keys + [ae, al]))
    for b in bases:
        bname = scen[b]["names"][0]
        for q in qs:
            v = scen[b]["choice"][q]
            for o in ((EARLY, LATE) if v == CONV else (LATE,) if v == EARLY else (EARLY,)):
                add(f"{q[0]} {q[1]}={o}, from {bname}", {**scen[b]["choice"], q: o})
    fv = factor_varies(inp, corr, st)
    envelope = {"ran": False, "combinations": 0, "note": "not needed: no corrected site's 2024 load varies between its cases"}
    if fv["varies"]:
        vq = [q for q in qs if q[0] in fv["sites_whose_2024_load_varies"]]
        others = [q for q in qs if q not in vq]
        n = 2 ** len(vq)
        envelope["combinations"] = n
        if n > ENVELOPE_LIMIT:
            envelope["note"] = (f"NOT RUN in {st}: {n} combinations of {len(vq)} questions whose 2024 load varies, over the "
                                f"limit of {ENVELOPE_LIMIT}; the state's factor varies and the corners do not bound it")
        else:
            for combo in itertools.product((EARLY, LATE), repeat=len(vq)):
                for end in ((EARLY, LATE) if others else (None,)):
                    ch = {**dict(zip(vq, combo)), **({q: end for q in others} if end else {})}
                    add("envelope [" + ", ".join(f"{f} {q}={v}" for (f, q), v in ch.items()) + "]", ch)
            envelope.update(ran=True, note=f"every combination of {len(vq)} questions whose 2024 load varies, with the state's "
                                           f"other questions all early and all late")

    # ---- the joint check (D-63 rule 7): the source of `joins` ----
    jc = joint_check(inp, corr, st, theta)

    # ---- the reference (R6): the exact attribution's function, with the place test's list of defining questions ----
    from pipeline.facilities import pass_c_exact as pe                     # lazy: pass_c_exact imports this module
    ref_state = pe._State(inp, corr, st)
    ref_defining = ref_state.defining("place_test")
    exact_defining = ref_state.defining("exact")                            # D-90: shown beside the place test's, never replaced by it

    # ---- evaluate every scenario ----
    frozen_factor = inp.frozen_factor(st)
    fac0, fy0 = inp.fac[inp.fac.state == st], inp.fy[inp.fy.state == st]
    t0, m0, r0 = asg.evaluate(fac0, fy0, units, base, regions, thresholds=(theta,))
    before = _outcomes(t0, m0, base, theta)
    results, factors, carries, kept = {}, {}, set(map(tuple, fy0[KEY].drop_duplicates().values)), {}
    for key, s in scen.items():
        fac_s, fy_s, f = scratch_state(inp, corr, st, dict(s["choice"]))
        t, m, r = asg.evaluate(fac_s, fy_s, units, base, regions, thresholds=(theta,))
        results[key] = _outcomes(t, m, base, theta)
        factors[key] = f
        carries |= set(map(tuple, fy_s[KEY].drop_duplicates().values))
        if key in bases:
            kept[key] = (fac_s, fy_s, m, r)
    factor_changes = any(f != frozen_factor for f in factors.values())

    # ---- who is touched ----
    touched = set()
    for fid, c in mine.items():
        r = inp.fac.loc[fid]
        if pd.notna(r.utility_id_eia):
            touched.add((int(r.utility_id_eia), st))
        touched |= {(u, st) for u in asg.candidates(r.utility_candidates)}
        if c.assign not in (None, OFF):
            touched.add(tuple(c.assign))
        touched |= {(u, st) for u in (c.narrow or []) + (c.widen or []) + (c.reopen or [])}
    if factor_changes:
        touched |= {(int(u), s2) for u, s2 in carries}
    touched |= {(int(key.split(":")[0]), st) for key, u in jc["utilities"].items() if u["can_affect"]}
    date_q = {fid: c.date for fid, c in mine.items() if c.date}
    unit_set = set(units)
    off_panel = sorted(f"{u}:{s2}" for u, s2 in touched if (u, s2) not in unit_set)
    touched = sorted(k for k in touched if k in unit_set)

    rows = []
    for k in touched:
        base_k = float(base[k]) if pd.notna(base[k]) else np.nan
        o_b = before[k]
        original = {"place": o_b["place"], "crossing": _fmt(o_b["crossing"]),
                    "verdict": asg.verdict(_vplace(o_b["place"]), o_b["crossing"], o_b["cases"], o_b["shares"])}
        refs = [results[rk][k] for rk in ref_keys]
        rec, _ = pe.reference_of(ref_state, k, base_k, theta, ref_defining, pe.CEILING)
        reference_rule = {"settings_enumerated": rec["settings_enumerated"], "searched": rec["searched"],
                          "undefined_by": rec["undefined_by"], "why_undefined": rec["why_undefined"]}
        rec_exact, _ = pe.reference_of(ref_state, k, base_k, theta, exact_defining, pe.CEILING)
        if rec["defined"]:
            # Every reference variant is an admissible reference setting, so each must show the reference's place and
            # crossing; a variant that does not means the two computations disagree, and the run stops (R6).
            for rk, x in zip(ref_keys, refs):
                if x["place"] != rec["place"] or str(_fmt(x["crossing"])) != rec["crossing"]:
                    raise ValueError(f"{k[0]}:{k[1]} in {st}: the shared reference (pass_c_exact.reference_of) is "
                                     f"{rec['place']} {rec['crossing']}, but the place test's reference variant "
                                     f"{scen[rk]['names'][0]!r} gives {x['place']} {_fmt(x['crossing'])} through the scratch "
                                     f"rebuild. The two must agree where the reference is defined; the run stops.")
            ref = refs[0]
            verdicts = [asg.verdict(_vplace(x["place"]), x["crossing"], x["cases"], x["shares"]) for x in refs]
            reference = {"place": ref["place"], "crossing": _fmt(ref["crossing"]),
                         "verdict": next((v for v in verdicts if v != "keeps its place"), verdicts[0])}
        else:
            ref = None
            reference = f"none ({rec['why_undefined']})"
        crossings = [results[key][k]["crossing"] for key in scen]
        dated = [c for c in crossings if pd.notna(c)]
        rng = {"earliest_crossing": _fmt(min(dated)) if dated else "never",
               "latest_crossing": "never" if any(pd.isna(c) for c in crossings) else _fmt(max(dated)),
               "places": sorted({results[key][k]["place"] for key in scen}), "scenarios": len(scen)}
        keeps, why = (ref is not None), ("" if ref is not None else "no single reference")
        if ref is not None:
            vp = _vplace(ref["place"])
            for key, s in scen.items():
                o = results[key][k]
                bad = None
                if o["place"] != ref["place"]:
                    bad = f"place {o['place']} against {ref['place']}"
                elif ref["place"] == "cohort" and not asg.same_place(ref["crossing"], o["crossing"]):
                    bad = f"first crossing {_fmt(o['crossing'])} against {_fmt(ref['crossing'])}"
                elif vp != "neither":
                    v = asg.verdict(vp, ref["crossing"], o["cases"], o["shares"])
                    if v != "keeps its place":
                        bad = v
                if bad:
                    keeps, why = False, f"{s['names'][0]}: {bad}"
                    break
        # ---- decisive on a single flip (kept because the ledger cites it; no longer the source of joins) ----
        after = set()
        for q in qs:
            groups: dict = {}
            for key, s in scen.items():
                rest = tuple(sorted((qq, v) for qq, v in s["choice"].items() if qq != q))
                groups.setdefault(rest, []).append(_key4(results[key][k]))
            if any(_differs(a, b) for g in groups.values() for a, b in itertools.combinations(g, 2)):
                after.add((q[0], "date" if q[1] == "date" else "capacity"))
        for b in bases:
            fac_s, fy_s, m, r = kept[b]
            after |= {(f, "assignment") for f in _assignment_decisive(fac_s, fy_s, m, r, k, base_k, theta)}
        before_q = {(f, "assignment") for f in _assignment_decisive(fac0, fy0, m0, r0, k, base_k, theta)}
        j = jc["utilities"][f"{k[0]}:{k[1]}"]
        # D-63 rule 4: "admissible" only if every date or capacity question that can affect the utility has both ends on
        # evidence. A capacity question's late end is the inventory's permit-based year, so it is always tested.
        timing = [q for q in j["can_affect"] if q["question"] in ("date", "capacity")]
        admissible = all(q["question"] == "date" and date_q[q["fid"]].get("ends") == "evidence" for q in timing)
        rows.append({
            "utility": f"{k[0]}:{k[1]}", "name": inp.names.get(k),
            "original": original, "reference": reference, "reference_rule": reference_rule, "range": rng,
            "range_kind": "inventory dates only" if not timing else "admissible" if admissible else "tested",
            "reference_differs_from_original": (None if ref is None else
                                                bool(ref["place"] != o_b["place"] or not _same_value(ref["crossing"], o_b["crossing"]))),
            "keeps_its_place": keeps, "first_failure": why,
            "decisive_on_a_single_flip": [list(q) for q in sorted(after)],
            "already_decisive_before": [list(q) for q in sorted(after & before_q)],
            "n_unsettled": j["n_unsettled"], "unsettled": j["unsettled"],
            "kept_questions": j["kept_questions"], "joins": j["joins"],
            # D-90: the reference above is a conditional diagnostic; the exact reference is shown beside it.
            **reference_diagnostic(ref is not None, rec_exact)})
    named ={n: f for key, f in factors.items() for n in scen[key]["names"] if not n.startswith("envelope")}
    env_f = [f for key, f in factors.items() if any(n.startswith("envelope") for n in scen[key]["names"])]
    if env_f:
        envelope["factor_range"] = [min(env_f), max(env_f)]
    return {"state": {"frozen_factor": frozen_factor, "factor_changes": factor_changes,
                      "factor_by_scenario": {n: f for n, f in named.items() if f != frozen_factor},
                      "factor_varies_across_scenarios": fv["varies"], "sites_whose_2024_load_varies": fv["their_2024_mw_raw"],
                      "envelope": envelope, "scenarios": len(scen), "scenario_questions": [list(q) for q in qs],
                      "questions": jc["questions"], "factor_range": jc["factor_range"],
                      "unresolved_sites_with_no_load_in_any_setting": jc["unresolved_sites_with_no_load_in_any_setting"],
                      "missing_inputs": jc["missing_inputs"],
                      "touched_utilities_not_on_the_panel": off_panel},
            "utilities": rows}


def expand(corrections: list[dict], inputs: Inputs | None = None, theta: float = THETA, targets=None) -> dict:
    """D-61 section 4: the place of every utility the corrections touch, before and after, and the questions that join."""
    check_unresolved_count(corrections)
    inp = inputs or load_frozen()
    corr = parse_corrections(corrections, inp)
    listed = None
    if targets:
        t = pd.read_csv(targets)
        listed = set(t["site"].astype(str)) if "site" in t else set(t["fid"].astype(str))
    out = {"theta": theta, "what_this_is": "D-61 section 4: the expansion test on scratch copies; load and sales only; the place of "
                                           "touched utilities and nothing else",
           "guarantee": GUARANTEE, "place_test_reference": REFERENCE_CONDITION,
           "missing_inputs_in_the_inventory": missing_inputs(inp), "states": {}, "utilities": []}
    for st in sorted({c.state for c in corr.values()}):
        r = run_state(inp, corr, st, theta)
        out["states"][st] = r["state"]
        for u in r["utilities"]:
            sites = u["joins"]
            u["joins_on_target_list"] = ({f: ("on the list" if f in listed else "new") for f in sites} if listed is not None else {})
            out["utilities"].append(u)
    return out


# ---- the reproduction ------------------------------------------------------------------------------------------

def reproduce(inp: Inputs) -> dict:
    """The scratch rebuild with no corrections, against the frozen files: anchoring, every rebuildable site's rows, evaluation."""
    fac = inp.fac
    permit = ~inp.measured & ~inp.fixed
    permit_twh = inp.a2024[permit].groupby(fac.state[permit]).sum().reindex(inp.anchor.index).fillna(0.0)
    factors = pd.Series({st: _factor(float(inp.anchor.epri_twh[st]), float(inp.anchor.epoch_twh[st]), float(permit_twh[st]))
                         for st in inp.anchor.index})
    perm_rows = fac.index[~inp.measured]
    scale = fac.state[perm_rows].map(factors).fillna(1.0)
    # Every rebuildable site carrying load, crypto included, from its raw load, its history and the recomputed factor.
    rows = []
    for fid in fac.index[fac.in_dose & ~inp.fixed]:
        s = 1.0 if inp.measured[fid] else factors.get(fac.state[fid], 1.0)
        for y in YEARS:
            mw = site_mw(inp.hist[fid], fac.mw_full_raw[fid] * s, y)
            if mw > 0:
                rows.append((fid, y, mw))
    rebuilt = pd.DataFrame(rows, columns=["fid", "year", "mw"]).set_index(["fid", "year"]).mw
    frozen = inp.fy_all[inp.fy_all.fid.isin(fac.index[fac.in_dose & ~inp.fixed])].set_index(["fid", "year"]).mw
    both = rebuilt.index.intersection(frozen.index)
    # The measured histories not rebuilt, against what they carry in 2024 in the dose.
    fixed_in = sum(v for v in inp.frozen_2024_mw.values()) * 8.76 / 1000.0
    # One state at a time against the whole panel.
    th = f"{THETA:.0%}"
    t_all, _, _ = asg.evaluate(fac, inp.fy, inp.units, inp.base, inp.regions, thresholds=(THETA,))
    diffs = []
    for st in sorted(fac.state.dropna().unique()):
        u = inp.units[inp.units.get_level_values("state") == st]
        if not len(u):
            continue
        t, _, _ = asg.evaluate(fac[fac.state == st], inp.fy[inp.fy.state == st], u, inp.base.reindex(u), inp.regions.reindex(u),
                               thresholds=(THETA,))
        a, b = t.astype(float), t_all.loc[u, t.columns].astype(float)
        d = (a - b).abs().where(~(a.isna() & b.isna()), 0.0)
        diffs.append(float(np.nanmax(d.values)) if d.size else 0.0)
        if (a.isna() != b.isna()).any().any():
            diffs.append(math.inf)
    return {"anchor_states": int(len(inp.anchor)),
            "anchor_permit_twh_max_abs_diff": float((permit_twh - inp.anchor.permit_twh).abs().max()),
            "anchor_factor_max_abs_diff": float((factors - inp.anchor.factor).abs().max()),
            "state_scale_max_abs_diff": float((scale - fac.state_scale[perm_rows]).abs().max()),
            "rebuilt_sites": int(rebuilt.index.get_level_values("fid").nunique()),
            "frozen_sites": int(frozen.index.get_level_values("fid").nunique()),
            "rebuilt_rows": int(len(rebuilt)), "frozen_rows": int(len(frozen)),
            "rows_missing": int(len(frozen.index.difference(rebuilt.index))),
            "rows_extra": int(len(rebuilt.index.difference(frozen.index))),
            "rebuilt_mw_max_abs_diff": float((rebuilt[both] - frozen[both]).abs().max()),
            "fixed_history_sites": int(inp.fixed.sum()),
            "measured_residual_min_twh": float(inp.measured_fixed.min()),
            "measured_residual_total_twh": float(inp.measured_fixed.sum()),
            "fixed_history_2024_in_the_dose_twh": float(fixed_in),
            "per_state_evaluation_max_abs_diff": float(max(diffs) if diffs else 0.0),
            "threshold_checked": th}


# ---- CLI ---------------------------------------------------------------------------------------------------------

def check_out_path(p: Path) -> Path:
    p = Path(p).resolve()
    data = (ROOT / "data").resolve()
    if p == data or data in p.parents:
        raise ValueError(f"{p}: the result is a scratch file and goes outside data/")
    return p


def _table(res: dict) -> str:
    lines = []
    for st, s in res["states"].items():
        lines.append(f"{st}: frozen factor {s['frozen_factor']:.4f}; changes: {s['factor_changes']}; "
                     f"{s['scenarios']} scenarios; envelope: {s['envelope']['note']}")
        for n, f in s["factor_by_scenario"].items():
            lines.append(f"    factor {f:.4f} under {n}")
        fr = s["factor_range"]
        lines.append(f"    joint check: {len(s['questions'])} open questions; factor range {fr['low']:.4f} to {fr['high']:.4f}"
                     + (" (the band: the monotonicity check failed)" if fr["band_used"] else ""))
        if s["touched_utilities_not_on_the_panel"]:
            lines.append(f"    touched but not panel units: {', '.join(s['touched_utilities_not_on_the_panel'])}")
    lines.append("")
    lines.append("Each utility: original, reference, tested or admissible range (D-63 rule 4), the place test, the single "
                 "flips, and the joint check (D-63 rule 7)")
    lines.append(REFERENCE_CONDITION)
    lines.append("")
    for u in res["utilities"]:
        o, r, g = u["original"], u["reference"], u["range"]
        ref = r if isinstance(r, str) else f"{r['place']} {r['crossing']} ({r['verdict']})"
        lines.append(f"{u['utility']} {u['name']}")
        lines.append(f"    original   {o['place']} {o['crossing']} ({o['verdict']})")
        lines.append(f"    reference  {ref}" + ("  [differs from the original]" if u["reference_differs_from_original"] else "")
                     + f"  [{u['reference_is']}]")
        if u["reference_shown_where_exact_is_undefined"]:
            lines.append(f"    NOTE  {u['reference_warning']}")
        lines.append(f"    range ({u['range_kind']})  crossings {g['earliest_crossing']} to {g['latest_crossing']}; "
                     f"places {', '.join(g['places'])}; {g['scenarios']} scenarios")
        lines.append(f"    keeps its place (diagnostic only): {u['keeps_its_place']}"
                     + (f" ({u['first_failure']})" if u["first_failure"] else ""))
        lines.append(f"    decisive on a single flip: {u['decisive_on_a_single_flip'] or 'none'}; already before: "
                     f"{u['already_decisive_before'] or 'none'}")
        kq = ", ".join(f"{q['fid']} {q['question']} ({q['channel']})" for q in u["kept_questions"])
        lines.append(f"    joint check: {u['n_unsettled']} unsettled cells; kept: {kq or 'none'}")
        lines.append(f"    joins: {u['joins'] or 'none'}" + (f"  {u['joins_on_target_list']}" if u["joins_on_target_list"] else ""))
    return "\n".join(lines)


def main_assignment_only(corrections: list[dict]) -> int:
    for c in corrections:
        if c["to"] != OFF:
            c["to"] = tuple(c["to"])
    pd.set_option("display.width", 250, "display.max_colwidth", 80)
    t = test(corrections)
    if not len(t):                                                         # no corrections: nothing touched (guard added 2026-11-15)
        print("touched: 0")
        return 0
    new = t[t.changed_by_the_corrections]
    print("touched:", len(t), "| changed by the corrections:", len(new))
    print(new.to_string(index=False) if len(new) else "no touched utility's place or verdict changed")
    add = new[new.place_can_change_with_its_unresolved_sites]
    print("sites that join the list:", sorted({f for r in add.itertuples() for f in r.unresolved_sites_on_it + r.unresolved_sites_that_list_it}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("corrections")
    ap.add_argument("--theta", type=float, default=THETA)
    ap.add_argument("--targets")
    ap.add_argument("--out")
    ap.add_argument("--assignment-only", action="store_true", help="the D-60 assignment-only test, unchanged")
    a = ap.parse_args()
    corrections = json.loads(Path(a.corrections).read_text())
    if a.assignment_only:
        return main_assignment_only(corrections)
    out = check_out_path(Path(a.out)) if a.out else None
    res = expand(corrections, theta=a.theta, targets=a.targets)
    print(_table(res))
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, indent=2, default=lambda x: None if isinstance(x, float) and math.isnan(x) else str(x)) + "\n")
        print("written:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
