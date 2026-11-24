#!/usr/bin/env python3
"""The second number's two sensitivity scenarios (Joe, 2026-11-19, D-107, adopting R2 of D-106 with its early-end
settings). Pre-freeze implementation on a DRAFT pre-analysis plan that is not frozen. Load, sales, the usable flag and
the corrections in force only: nothing here reads, opens or prints a price, a revenue or a bill, and nothing here
estimates anything on research outcomes. A function that will one day take outcomes takes them as an argument.

His words: "Adopt R2's scenarios, including the explicit early-end settings, but describe them as sensitivity scenarios,
not bounds or necessarily one-change comparisons with the primary analysis. Report sample differences." And: "Require
the per-state reconstruction check outside Oregon. Report any discrepancy and stop the affected scenario work rather
than changing rules to obtain agreement."

The definitions (R2, word for word where quoted)
-----------------------------------------------
Scenario A, runner-up placement. "Every load-carrying site whose serving utility is unresolved (460 sites with a state;
none is a crypto mine) is moved to its runner-up under the inventory's own placement rule. The rule, fixed here: the
site's stored candidate list in stored order (smallest territory polygon first), kept to panel units, with the utility
it is on now moved to the end; sites taken in descending size, ties by site id; each site takes the first candidate that
can hold its full load on top of what that candidate already carries, capacity being the unit's largest annual retail
sales in 2020 to 2025 as `pick_utilities` computes it; a candidate with no sales row is skipped; if no other candidate
fits, the site stays where it is; off the panel is never chosen. Every date, capacity and basis stays as the inventory
has it." (runner_up_placement)

What a candidate "already carries", Joe's rule (D-111, 2026-11-19): "lift the 460 unresolved sites first, keeping all
other load counted, then place them in the adopted descending-size order". Adopted by Joe on 2026-11-19 (D-111) on the
condition, met, that a check made first and apart from this module found that lifting first neither introduces a
capacity exceedance nor increases a pre-existing one (docs/gate1/scenario-a-exceedance-check-2026-11-19.md). So the
starting load of every unit leaves the 460 out and counts every other site of the inventory where it is, and each of
the 460 counts where it lands. Matching the earlier count is not the reason for the rule. A site for which no other
candidate fits, or that has no other panel candidate, stays where it is and counts on its unit from its own turn in the
order, so that smaller sites tested after it see it. That clause stands by Joe's ruling of 2026-11-20 (D-113), and no
further placement variant is tested; counting such a site only after every site has been placed was not tried.

Scenario B, the other end of every dated interval. "Every assignment stays as the inventory has it. Each of the 48 date
entries in force that has a convention goes to the end of its interval that its convention does not sit at: a
convention at the late end goes to the early end and the reverse; the one interior convention (`bi:1250-0`) goes to the
end farther from it, the early end on a tie; a one-year interval keeps its year; open below is entered as the
enumeration enters it, full load from 2001." (other_end)

In both, "the two sites with no load history take the early end of each of their questions (`bi:852-0` starts in 2024;
`bi:837-0`'s date and the rest of its capacity at 2011), and each state's factor is recomputed from the history."
(LOAD_UNKNOWN_EARLY_END; realise_history recomputes the factor in every state through pass_c_exact.realise.)

What they are not, his: sensitivity scenarios, not bounds or necessarily one-change comparisons with the primary
analysis. Each differs from the primary run in its own kind of question AND in the two load-unknown sites' settings
(which the primary run leaves out), in Oregon's factor (recomputed with those sites carrying load) and in its sample
(Portland General and Umatilla enter; any unit with load and no base leaves). LABELS says so for each.

What is here
------------
runner_up_placement, other_end      the two rules, pure: they take sites, candidate lists, loads and sales, or one
                                    date entry, and refuse a dose, a price or an estimate (refuse_outcome_columns).
scenario_a_settings, scenario_b_settings
                                    the realise settings, state by state, each site once with one setting per question.
realise_history                     the loop over states: pass_c_exact.realise per state with the corrections in force,
                                    each state's factor recomputed, the GWh matrix and the factors.
reconstruction_check                the check Joe requires before any scenario is built: every setting at the
                                    inventory's, every state, against utility_year_dose.parquet (docs/gate1/
                                    second-number-reconstruction-check-2026-11-19.md).
scenario_points, scenario_frame, run_scenario
                                    the wrapper that feeds second_number: load share in points, the sample through
                                    second_number.build_frame, and second_number.run (bootstrap seed by default).
main                                runs the check, writes its result into the check document, and only if it passes in
                                    a state builds the scenarios there; writes data/frozen/second_number_scenarios.json.

Run:  python3 -I pipeline/analysis/second_number_scenarios.py
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import second_number as sn  # noqa: E402
from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import pass_c_exact as pe  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
OUT = FROZEN / "second_number_scenarios.json"
CHECK_DOC = ROOT / "docs" / "gate1" / "second-number-reconstruction-check-2026-11-19.md"
UNKNOWN_FILE = FROZEN / "unknown_load_sites_and_affected_utilities.json"
KEY = asg.KEY
YEARS = asg.YEARS

SCENARIO_A = "sensitivity_scenario_a_runner_up_placement"
SCENARIO_B = "sensitivity_scenario_b_other_end_of_every_dated_interval"
SCENARIOS = (SCENARIO_A, SCENARIO_B)
# R2's early-end settings for the two sites with no load history, as realise writes settings ("<fid> <question>").
LOAD_UNKNOWN_EARLY_END = {"bi:852-0 date": 2024, "bi:837-0 date": 2011, "bi:837-0 capacity": 2011}
TOLERANCE_REL = 1e-9          # the check's tolerance (the agent's reading: none is stated for the Oregon check on file)
MOVES = ("earlier", "later", "none")
# Column-name fragments the two rules refuse: neither takes a dose, a price or an estimate (R2).
REFUSED = ("dose", "price", "revenue", "bill", "estimate", "outcome", "slope", "points", "share")
R2_COUNTS = {SCENARIO_A: {"sites": 460, "sites_moved": 380, "units_carrying_different_load": 121},
             SCENARIO_B: {"date_entries_with_a_convention": 48, "rows_moved": 45, "earlier": 24, "later": 21}}
COMMON_DIFFERENCES = ("Besides its own kind of question it differs from the primary run in three ways: the two sites with "
                      "no load history carry load at the early end of each of their questions (bi:852-0 from 2024; "
                      "bi:837-0's date and the rest of its capacity at 2011), where the primary run leaves out every "
                      "utility they reach; Oregon's factor is recomputed with those sites carrying load; and its sample "
                      "differs (Portland General and Umatilla enter at the dose this history gives them, and any unit "
                      "with load in this history and no 2009-2011 base leaves). It is a sensitivity scenario, not a bound "
                      "and not necessarily a one-change comparison with the primary analysis.")
LABELS = {
    SCENARIO_A: ("Sensitivity scenario A, runner-up placement (Joe, D-107; R2 of D-106): every unresolved load-carrying "
                 "site moved to the first other candidate that can hold its full load under the inventory's own placement "
                 "rule, every date, capacity and basis as the inventory has it, each state's factor recomputed. "
                 "Under Joe's rule (D-111) for what a candidate already carries, the 460 unresolved sites are lifted "
                 "first, all other load kept counted, and placed in descending size, each counting where it lands; "
                 "matching the earlier count is not the reason for the rule. Umatilla enters at 25.0 and 50.0 points at "
                 "the caps (462 uncapped) and Portland General at 18.8 points. "
                 + COMMON_DIFFERENCES),
    SCENARIO_B: ("Sensitivity scenario B, the other end of every dated interval (Joe, D-107; R2 of D-106): each date "
                 "entry in force that has a convention at the end of its interval its convention does not sit at, every "
                 "assignment as the inventory has it, each state's factor recomputed. Umatilla enters at 0.0 points "
                 "at both caps (316 uncapped) and Portland General at 18.9 points. " + COMMON_DIFFERENCES),
}
RULE_A = ("What a candidate already carries (Joe's rule, adopted on 2026-11-19, D-111): \"lift the 460 unresolved sites "
          "first, keeping all other load counted, then place them in the adopted descending-size order\". Adopted on the "
          "condition, met, that a check made first and apart from the module found that lifting first neither introduces "
          "a capacity exceedance nor increases a pre-existing one (docs/gate1/scenario-a-exceedance-check-2026-11-19.md). "
          "Matching the earlier count is not the reason for the rule. A site for which no other candidate fits, or with "
          "no other panel candidate, stays where it is and counts on its unit from its own turn in the order. That "
          "clause stands by Joe's ruling of 2026-11-20 (D-113), and no further placement variant is tested; counting "
          "it only after every site is placed was not tried. "
          "Against the earlier reading (every site counted where it sat until it moved), 27 sites change destination "
          "and one more site moves (docs/gate1/scenario-a-count-reconciliation-2026-11-19.md).")
UNCERTAIN = (
    "I am uncertain whether the capacity test's starting load matches what the build used before its overrides: the "
    "rule here starts from what each candidate carries in the inventory as assigned less the 460 sites being placed "
    "(every other site on it, at its scaled full load, as pick_utilities counts load) and adds each of the 460 where "
    "it lands; build_inventory.pick_utilities started from nothing and placed every site in one pass before the "
    "overrides. The rule is stated, not a replication.",
    "Whether Texas's factor moves under B: it is clipped at 3.0 in the inventory; the factor recomputed under B is "
    "reported in the factor table, and the raw factor before the clip is not reported.",
)


# ================================================================================================================
# 0. Guards
# ================================================================================================================

def refuse_outcome_columns(frame: pd.DataFrame, what: str) -> None:
    """Neither rule takes a dose, a price or an estimate: a frame carrying a column whose name says it is one is
    refused in words."""
    bad = [c for c in frame.columns if any(r in str(c).lower() for r in REFUSED)]
    if bad:
        raise ValueError(f"{what} carries {bad}: the scenario rules take no dose, price or estimate (R2), so a frame with "
                         "such a column is refused")


def _candidates(v) -> list:
    if isinstance(v, (list, tuple)):
        return [int(x) for x in v]
    return asg.candidates(v)


# ================================================================================================================
# 1. Scenario A: runner-up placement (pure)
# ================================================================================================================

def runner_up_placement(sites: pd.DataFrame, carried: dict, capacity: dict, panel_units) -> pd.DataFrame:
    """R2's runner-up placement. Pure: no file is read.

    sites      one row per site to place: fid, state, utility_id_eia (the unit it is on now), candidates (stored order,
               a list or the inventory's ';' string), load_gwh (its full load, scaled MW x 8.76, as pick_utilities)
    carried    {(utility, state): GWh} what each unit carries in the inventory as assigned with the sites being placed
               lifted off (every other site placed on it, at its full load; carried_without). Each site being placed
               is added where it lands, moved or staying, at its turn in the order: Joe's rule, "lift the 460
               unresolved sites first, keeping all other load counted, then place them in the adopted
               descending-size order", adopted by Joe on 2026-11-19 (D-111). That a staying site counts from its own
               turn stands by Joe's ruling of 2026-11-20 (D-113), and no further placement variant is tested
               (see the module docstring)
    capacity   {(utility, state): GWh} the unit's largest annual retail sales in 2020 to 2025
    panel_units  the panel's (utility, state) units

    Order: descending load_gwh, ties by fid. Candidates: stored order, repeats dropped, kept to panel units in the site's
    state, the unit it is on moved to the end (so it is never tried as a move). A candidate with no capacity (no sales
    row) is skipped. The first that holds carried + load_gwh <= capacity takes the site. If none does, the site stays,
    with no capacity test on the unit it is on, and its load is added there.
    Off the panel is never a candidate. Returns one row per site: fid, state, from_utility, to_utility, moved, rank (its
    place in the order), tried ([(candidate, why)]), why."""
    if not isinstance(sites, pd.DataFrame):
        raise TypeError("sites must be a DataFrame")
    refuse_outcome_columns(sites, "the sites")
    need = ["fid", "state", "utility_id_eia", "candidates", "load_gwh"]
    miss = [c for c in need if c not in sites.columns]
    if miss:
        raise ValueError(f"the sites lack {miss}")
    if sites.fid.duplicated().any():
        raise ValueError(f"a site appears twice: {sorted(sites.fid[sites.fid.duplicated()])}; each is placed once")
    if sites.load_gwh.isna().any() or (sites.load_gwh < 0).any():
        raise ValueError("every site to place needs a full load that is a number and not negative")
    if sites.utility_id_eia.isna().any() or sites.state.isna().any():
        raise ValueError("every site to place is on a utility in a state (R2: sites with a state, on the utility they are on)")
    units = {(int(u), str(s)) for u, s in panel_units}
    carried = {(int(u), str(s)): float(v) for (u, s), v in carried.items()}
    cap = {(int(u), str(s)): float(v) for (u, s), v in capacity.items()}
    order = sites.assign(_fid=sites.fid.astype(str)).sort_values(["load_gwh", "_fid"], ascending=[False, True])
    rows = []
    for rank, r in enumerate(order.itertuples(index=False)):
        st, now, g = str(r.state), int(r.utility_id_eia), float(r.load_gwh)
        cands = [c for c in dict.fromkeys(_candidates(r.candidates)) if (c, st) in units]
        others = [c for c in cands if c != now]
        tried, to, why = [], None, None
        for c in others:
            cp = cap.get((c, st), np.nan)
            if not np.isfinite(cp):
                tried.append((c, "skipped: no sales row (no capacity)"))
                continue
            have = carried.get((c, st), 0.0)
            if have + g <= cp:
                tried.append((c, f"fits: {have:.3f} + {g:.3f} <= {cp:.3f} GWh"))
                to = c
                break
            tried.append((c, f"does not fit: {have:.3f} + {g:.3f} > {cp:.3f} GWh"))
        if to is None:
            why = ("no other panel candidate" if not others else "no other candidate can hold its full load") + \
                  "; the site stays where it is"
            to = now
            carried[(now, st)] = carried.get((now, st), 0.0) + g      # lifted first, it counts where it lands
        else:
            carried[(to, st)] = carried.get((to, st), 0.0) + g
            why = "moved to the first other candidate that can hold its full load"
        rows.append({"fid": r.fid, "state": st, "from_utility": now, "to_utility": int(to), "moved": int(to) != now,
                     "rank": rank, "tried": tried, "why": why})
    return pd.DataFrame(rows, columns=["fid", "state", "from_utility", "to_utility", "moved", "rank", "tried", "why"])


# ================================================================================================================
# 2. Scenario B: the other end of every dated interval (pure)
# ================================================================================================================

def _early_end(e: dict):
    return px.OPEN_BELOW_START if e.get("earliest") is None else int(e["earliest"])


def _late_end(e: dict):
    return "never" if e.get("never_is_possible") else int(e["latest"])


def other_end(entry: dict) -> dict:
    """R2's setting for one date entry in force that has a convention. Pure.

    The early end is `earliest`, or open below entered as the enumeration enters it (pass_c_expand.OPEN_BELOW_START:
    under the three-year ramp, full load from 2001). The late end is "never" where never_is_possible, otherwise
    `latest`. A one-year interval keeps its year. A convention at the late end goes to the early end and the reverse.
    An interior convention goes to the end farther from it, the early end on a tie; the distance to an open lower end is
    taken to OPEN_BELOW_START and the distance to "never" is taken as larger than any (the agent's reading; neither
    arises for the one interior entry). Returns {"fid", "convention", "setting", "moves", "why"}."""
    if not isinstance(entry, dict) or entry.get("kind") != "date":
        raise ValueError(f"a date entry is needed, not {entry!r}")
    bad = [k for k in entry if any(r in str(k).lower() for r in REFUSED)]
    if bad:
        raise ValueError(f"the entry carries {bad}: the scenario rules take no dose, price or estimate (R2)")
    conv = entry.get("convention")
    if conv is None:
        raise ValueError(f"{entry.get('fid')}: no convention; R2 moves only the date entries that have one (the two sites "
                         "with no load history take LOAD_UNKNOWN_EARLY_END)")
    lo, hi = _early_end(entry), _late_end(entry)
    if entry.get("earliest") is not None and entry.get("latest") is not None and int(entry["earliest"]) == int(entry["latest"]) \
            and not entry.get("never_is_possible"):
        return {"fid": entry["fid"], "convention": conv, "setting": int(entry["earliest"]), "moves": "none",
                "why": "a one-year interval keeps its year"}
    if conv == "never" or (hi != "never" and conv == hi):
        setting, why = lo, "convention at the late end: to the early end"
    elif entry.get("earliest") is not None and conv == lo:
        setting, why = hi, "convention at the early end: to the late end"
    else:
        d_lo = int(conv) - int(lo)
        d_hi = np.inf if hi == "never" else int(hi) - int(conv)
        setting, why = ((lo, "interior convention: the early end is at least as far from it") if d_lo >= d_hi else
                        (hi, "interior convention: the late end is farther from it"))
    if setting == "never":
        moves = "later"
    elif conv == "never":
        moves = "earlier"
    else:
        moves = "earlier" if int(setting) < int(conv) else "later" if int(setting) > int(conv) else "none"
    if setting == px.OPEN_BELOW_START and entry.get("earliest") is None:
        why += " (open below, entered as the enumeration enters it: full load from 2001)"
    return {"fid": entry["fid"], "convention": conv, "setting": setting, "moves": moves, "why": why}


# ================================================================================================================
# 3. Settings, state by state
# ================================================================================================================

def _add(out: dict, state_of, key: str, value) -> None:
    fid = key.rsplit(" ", 1)[0]
    st = state_of.get(fid) if hasattr(state_of, "get") else state_of[fid]
    if st is None or (isinstance(st, float) and np.isnan(st)):
        raise ValueError(f"{fid} has no state; a setting needs one")
    d = out.setdefault(str(st), {})
    if key in d:
        raise ValueError(f"{key} is set twice; one history gives each question one setting")
    d[key] = value


def load_unknown_settings(state_of) -> dict:
    """{state: {"<fid> <question>": setting}} for the two sites with no load history at R2's early end."""
    out: dict = {}
    for k, v in LOAD_UNKNOWN_EARLY_END.items():
        _add(out, state_of, k, v)
    return out


def scenario_a_settings(placement: pd.DataFrame, state_of) -> dict:
    """realise settings for scenario A: every moved site's assignment, and the load-unknown sites' early end."""
    out = load_unknown_settings(state_of)
    for r in placement[placement.moved].itertuples(index=False):
        if str(state_of.get(r.fid)) != str(r.state):
            raise ValueError(f"{r.fid}: placed in {r.state} but the inventory has it in {state_of.get(r.fid)}")
        _add(out, state_of, f"{r.fid} assignment", int(r.to_utility))
    return out


def scenario_b_settings(entries: list, state_of) -> tuple[dict, list]:
    """realise settings for scenario B, and other_end's record for each date entry with a convention."""
    out = load_unknown_settings(state_of)
    unknown = {k.rsplit(" ", 1)[0] for k in LOAD_UNKNOWN_EARLY_END}
    rec = []
    for e in entries:
        if e.get("kind") != "date" or e.get("convention") is None:
            continue
        if e["fid"] in unknown:
            raise ValueError(f"{e['fid']} has a convention but is one of the sites with no load history")
        r = other_end(e)
        rec.append(r)
        if r["moves"] != "none":
            _add(out, state_of, f"{e['fid']} date", r["setting"])
    return out, rec


# ================================================================================================================
# 4. The loop over states
# ================================================================================================================

def _choice(inp, corr: dict, st: str, settings: dict) -> tuple[dict, dict]:
    """pass_c_exact.realise's reading of `settings`, written out so the state's factor can be read from the same
    scratch rebuild (realise returns the matrices only). realise_history checks the two agree exactly."""
    import dataclasses
    corr = dict(corr)
    choice = {}
    for key, v in settings.items():
        fid, q = key.rsplit(" ", 1)
        if q == "assignment":
            to = px.OFF if v == px.OFF else (int(v), st)
            c = corr.get(fid) or px.Correction(fid=fid, state=st, inventory_year=inp.fac.energized_year[fid])
            corr[fid] = dataclasses.replace(c, assign=to, reopen=None, narrow=None, widen=None)
        else:
            choice[(fid, q)] = v
    for fid, c in corr.items():
        if c.state == st:
            for q in c.questions():
                if (fid, q) not in choice and c.convention(q) is None:
                    choice[(fid, q)] = (px._date_values(c) if q == "date" else px._capacity_values(c))[0]
    return corr, choice


def _matrix(fy: pd.DataFrame, units) -> pd.DataFrame:
    if not len(fy):
        return pd.DataFrame(0.0, index=units, columns=YEARS)
    g = (fy.groupby(KEY + ["year"]).mw.sum() * 8.76).unstack("year")
    return g.reindex(index=units, columns=YEARS).fillna(0.0)


def realise_history(inp, entries: list, settings_by_state: dict, states=None) -> dict:
    """One whole-inventory history, state by state through pass_c_exact.realise (the scratch rebuild and
    assignment.evaluate), with the history entries in force for each state's sites (screen shift 0) and each state's
    factor recomputed by the rebuild. `settings_by_state`: {state: {"<fid> <question>": setting}}; a question left out
    takes its convention (realise's rule). Returns {"gwh": units x years as built, "factor": {state: factor},
    "frozen_factor": {state: factor}, "sites_on_two_utilities": []}. Stops in words if a setting names a site of another
    state, if a site ends on two utilities, or if the factor's scratch rebuild and realise's matrices differ."""
    panel_states = sorted({s for _, s in inp.units})
    states = panel_states if states is None else list(states)
    extra = sorted(set(settings_by_state) - set(panel_states))
    if extra:
        raise ValueError(f"settings for states with no panel unit: {extra}")
    blocks, factor, frozen, empty = [], {}, {}, []
    for st in states:
        s = dict(settings_by_state.get(st, {}))
        for key in s:
            fid = key.rsplit(" ", 1)[0]
            if fid not in inp.fac.index or inp.fac.state[fid] != st:
                raise ValueError(f"{key}: the site is not in {st}")
        u = inp.units[inp.units.get_level_values("state") == st]
        if not (inp.fac.state == st).any():
            # No site of the inventory is in the state: realise cannot be called on it (assignment.matrices fails on an
            # empty frame), and no history can put load on its units. They carry zero, compared as such by the check.
            blocks.append(pd.DataFrame(0.0, index=u, columns=YEARS))
            factor[st] = frozen[st] = float(inp.frozen_factor(st))
            empty.append(st)
            continue
        mine = [e for e in entries if inp.fac.state.get(e["fid"]) == st]
        corr = px.parse_corrections(mine, inp)
        m = pe.realise(inp, corr, st, s)
        c2, choice = _choice(inp, corr, st, s)
        _fac, fy, f = px.scratch_state(inp, c2, st, choice)
        mine_m = _matrix(fy, u)
        if not mine_m.equals(m["as_built"].reindex(index=u, columns=YEARS).astype(float)):
            raise ValueError(f"{st}: the scratch rebuild read for the factor does not give realise's matrix; stopping")
        two = fy.groupby("fid").utility_id_eia.nunique()
        if (two > 1).any():
            raise ValueError(f"{st}: sites on two utilities in one history: {sorted(two.index[two > 1])}")
        blocks.append(m["as_built"].reindex(index=u, columns=YEARS).astype(float))
        factor[st] = float(f)
        frozen[st] = float(inp.frozen_factor(st))
    gwh = pd.concat(blocks) if blocks else pd.DataFrame(columns=YEARS, dtype=float)
    return {"gwh": gwh, "factor": factor, "frozen_factor": frozen, "states_with_no_site": empty}


def points_of(gwh: pd.DataFrame, base: pd.Series) -> tuple[pd.DataFrame, list]:
    """Load share in points (GWh over the 2009-2011 base, times 100). A unit with load and no positive base has no dose:
    NaN, named in the list. A unit with no load and no base carries zero (as second_number.case_points reads it)."""
    b = base.reindex(gwh.index)
    pos = (b > 0).values
    p = gwh.div(b.where(b > 0), axis=0) * 100.0
    p[~pos] = 0.0
    loaded = gwh.gt(0).any(axis=1).values
    bad = ~pos & loaded
    p[bad] = np.nan
    return p, sorted(gwh.index[bad])


# ================================================================================================================
# 5. The reconstruction check (Joe: required before any scenario is built)
# ================================================================================================================

def agree(a, b, rel: float = TOLERANCE_REL) -> np.ndarray:
    """Equality to floating-point rounding: |a - b| <= rel x max(|a|, |b|); exact equality where either is zero."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return np.abs(a - b) <= rel * np.maximum(np.abs(a), np.abs(b))


def reconstruction_check(gwh: pd.DataFrame, base: pd.Series, dose_file: pd.DataFrame, affected, factor: dict | None = None,
                         frozen_factor: dict | None = None, rel: float = TOLERANCE_REL) -> dict:
    """The realised history at every setting of the inventory against the dose file, per state, every unit no
    load-unknown site reaches, every year. Load share in points where the base is positive, GWh where it is not (the
    unit is listed). Returns {state: {"units_compared", "units_agree", "max_abs_difference", "max_rel_difference",
    "disagreements": [...], "units_with_no_positive_base": [...], "factor", "frozen_factor", "passes"}}."""
    affected = {(int(u), str(s)) for u, s in affected}
    d = dose_file.set_index(KEY + ["year"])
    file_pts = (d.dose * 100.0).unstack("year").reindex(columns=YEARS)
    file_gwh = d.dc_gwh.unstack("year").reindex(columns=YEARS)
    out = {}
    for st in sorted({s for _, s in gwh.index}):
        ks = [k for k in gwh.index if k[1] == st and (int(k[0]), k[1]) not in affected]
        rec = {"units_compared": len(ks), "units_agree": 0, "max_abs_difference": 0.0, "max_rel_difference": 0.0,
               "disagreements": [], "units_with_no_positive_base": [], "units_left_out_as_reached_by_a_load_unknown_site":
               sorted(f"{int(u)}:{s}" for u, s in gwh.index if s == st and (int(u), s) in affected)}
        for k in ks:
            b = float(base.get(k, np.nan))
            if np.isfinite(b) and b > 0:
                mine = gwh.loc[k].values / b * 100.0
                theirs = file_pts.reindex([k]).fillna(0.0).values[0]
                unit = "points"
            else:
                mine = gwh.loc[k].values
                theirs = file_gwh.reindex([k]).fillna(0.0).values[0]
                unit = "GWh"
                rec["units_with_no_positive_base"].append(f"{int(k[0])}:{k[1]}")
            ok = agree(mine, theirs, rel)
            diff = np.abs(mine - theirs)
            den = np.maximum(np.abs(mine), np.abs(theirs))
            relv = np.where(den > 0, diff / np.where(den > 0, den, 1.0), 0.0)
            rec["max_abs_difference"] = max(rec["max_abs_difference"], float(diff.max()))
            rec["max_rel_difference"] = max(rec["max_rel_difference"], float(relv.max()))
            if ok.all():
                rec["units_agree"] += 1
            else:
                rec["disagreements"].append({"utility": f"{int(k[0])}:{k[1]}", "in": unit,
                                             "years": [int(y) for y, o in zip(YEARS, ok) if not o],
                                             "realised": [float(x) for x, o in zip(mine, ok) if not o],
                                             "dose_file": [float(x) for x, o in zip(theirs, ok) if not o]})
        rec["passes"] = rec["units_agree"] == rec["units_compared"]
        if factor is not None:
            rec["factor_recomputed"] = factor.get(st)
            rec["factor_frozen"] = (frozen_factor or {}).get(st)
        out[st] = rec
    return out


# ================================================================================================================
# 6. The wrapper that feeds second_number
# ================================================================================================================

def scenario_frame(points: pd.DataFrame, units, q: pd.DataFrame, regions: pd.DataFrame, usable: set, codes: dict,
                   no_dose: list) -> sn.Frame:
    """A scenario's sample: second_number.build_frame over `units` (every panel unit less the price hold, the
    load-unknown units included, since the scenario gives them a dose), less every unit with load in this history and
    no positive base (`no_dose`, named in left_out). The fixed effects and clusters are build_frame's."""
    f = sn.build_frame(units, q, regions, usable, codes=codes)
    nd = {(int(u), str(s)) for u, s in no_dose}
    left = list(f.left_out) + [{"utility": sn._uid(k), "why": "load in this history and no positive 2009-2011 sales: no dose"}
                               for k in f.keys if k in nd]
    f = sn.sub_frame(f, [i for i, k in enumerate(f.keys) if k not in nd])
    f.left_out = left
    if points.reindex(pd.MultiIndex.from_tuples(f.keys, names=KEY))[list(f.years)].isna().any().any():
        raise ValueError("a unit of the scenario's sample has no load share in some year of the comparison")
    return f


def run_scenario(frame: sn.Frame, points: pd.DataFrame, outcome: pd.DataFrame, rng: np.random.Generator | None = None,
                 boot: int = sn.BOOT, outcome_col: str = "log_price") -> dict:
    """The second number on one sensitivity scenario: second_number.run on the scenario's frame and load shares, with
    the outcome as an argument (never read here). The bootstrap draws from second_number.bootstrap_rng() by default."""
    r = sn.run(frame, points, outcome, rng, boot=boot, outcome_col=outcome_col)
    r["label"] = "sensitivity scenario: " + sn.INFERENCE_LABEL
    return r


def _check_rule_signatures() -> None:
    """Neither rule takes a dose, a price or an estimate as an argument (R2), checked on the parameter names."""
    for fn in (runner_up_placement, other_end, scenario_a_settings, scenario_b_settings):
        bad = [p for p in inspect.signature(fn).parameters if any(r in p.lower() for r in REFUSED)]
        if bad:
            raise AssertionError(f"{fn.__name__} takes {bad}")


_check_rule_signatures()


# ================================================================================================================
# main
# ================================================================================================================

def real_inputs():
    """The inputs exactly as second_number.oregon_state builds them (the live inventory, timing.patch_unknown, the
    buildout records, frozen_2024_mw empty), the history entries in force, the dose file and the affected list."""
    from pipeline.facilities import corrections as cx
    from pipeline.facilities import timing as tm
    unk = json.loads(UNKNOWN_FILE.read_text())
    fids = [s["fid"] for s in unk["sites"]]
    _S, inp = sn.oregon_state(fids)
    entries = tm.timing_entries(cx.load(cx.CORRECTIONS))
    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    affected = [(int(x.split(":")[0]), x.split(":")[1]) for x in unk["every_affected_utility"]]
    return inp, entries, dose, affected, fids


def carried_without(fac: pd.DataFrame, placed) -> dict:
    """{(utility, state): GWh} what every unit carries at scaled full load (MW x 8.76, a missing load counting zero),
    every site of the inventory on a unit in a state counted except the sites in `placed` (fids), which are lifted off
    first (Joe's rule, D-111). Pure. fac is indexed by fid."""
    on = fac[fac.utility_id_eia.notna() & fac.state.notna() & ~fac.index.isin(list(placed))]
    return (on.mw_full.fillna(0.0) * 8.76).groupby([on.utility_id_eia.astype(int), on.state]).sum().to_dict()


def placement_inputs(inp) -> tuple[pd.DataFrame, dict, dict]:
    """Scenario A's inputs from the inventory: the unresolved load-carrying sites with a state (assignment.resolved;
    in_dose; not crypto), what every unit carries at full load with those sites lifted off (carried_without), and each
    unit's largest annual retail sales 2020-2025."""
    ercot = {k for k in inp.units if inp.regions.get(k) == asg.ERCOT_REGION}
    res = asg.resolved(inp.fac, ercot)
    f = inp.fac
    pick = ~res & f.in_dose.astype(bool) & f.state.notna() & ~f.is_crypto.astype(bool)
    sites = pd.DataFrame({"fid": f.index[pick], "state": f.state[pick].values,
                          "utility_id_eia": f.utility_id_eia[pick].values, "candidates": f.utility_candidates[pick].values,
                          "load_gwh": f.mw_full[pick].values * 8.76})
    carried = carried_without(f, set(sites.fid))
    q = pd.read_parquet(INTERIM / "panel_quantities.parquet", columns=KEY + ["year", "total_retail_mwh"])
    capacity = (q[q.year >= 2020].groupby(KEY).total_retail_mwh.max() / 1000.0).to_dict()
    return sites, carried, capacity


def _write_check(result: dict, stopped: dict, no_site: list) -> None:
    text = CHECK_DOC.read_text()
    head = text.split("## 2. The result")[0]
    lines = ["## 2. The result", "",
             f"Run on 2026-11-19 by `pipeline/analysis/second_number_scenarios.py` (`reconstruction_check`), tolerance "
             f"{TOLERANCE_REL:g} relative as stated above. Load shares in points unless a unit has no positive base.", ""]
    ok = all(r["passes"] for r in result.values())
    tot = sum(r["units_compared"] for r in result.values())
    agree_n = sum(r["units_agree"] for r in result.values())
    lines.append(f"**{'Every state passes' if ok else 'A discrepancy was found'}: {agree_n} of {tot} units agree in "
                 f"{len(result)} states.**" + ("" if ok else " The scenario work in each state that fails is stopped "
                                                            "(section 3)."))
    lines += ["", "| State | Units compared | Agree | Largest absolute difference | Largest relative difference | "
                  "Factor recomputed | Factor frozen | Left out (reached by a load-unknown site) |",
              "|---|---|---|---|---|---|---|---|"]
    for st, r in result.items():
        lines.append(f"| {st} | {r['units_compared']} | {r['units_agree']} | {r['max_abs_difference']:.3g} | "
                     f"{r['max_rel_difference']:.3g} | {r.get('factor_recomputed')} | {r.get('factor_frozen')} | "
                     f"{', '.join(r['units_left_out_as_reached_by_a_load_unknown_site']) or 'none'} |")
    lines += ["", "States with no site of the inventory, where realise cannot be called (assignment.matrices fails on an "
              "empty frame) and every unit carries zero load in any history, compared as zero against the dose file: "
              + (", ".join(no_site) if no_site else "none") + ". Their factor is reported as the inventory's."]
    moved = [st for st, r in result.items() if r.get("factor_recomputed") != r.get("factor_frozen")]
    lines += ["", "States whose recomputed factor differs from the inventory's: " + (", ".join(moved) if moved else "none")
              + ". In Oregon this is expected and does not reach a unit compared: realise sets the two sites with no load "
              "history at their first setting (bi:852-0 from 2024; bi:837-0's date and the rest of its capacity at 2011), "
              "where the inventory carries no load for them, so the 2024 permit total and the factor move; in the live "
              "inventory every permit-based Oregon site in the dose is on Portland General or Umatilla (checked on "
              "facilities.parquet), the two units left out, so every Oregon unit compared carries measured load or none."]
    nob = sorted(u for r in result.values() for u in r["units_with_no_positive_base"])
    lines += ["", "Units with no positive base, compared in GWh: " + (", ".join(nob) if nob else "none") + "."]
    dis = [(st, d) for st, r in result.items() for d in r["disagreements"]]
    lines += ["", "Every unit that disagrees, with its years and both values: " + ("none." if not dis else "")]
    for st, d in dis:
        lines.append(f"- {d['utility']} ({d['in']}): years {d['years']}; realised {d['realised']}; dose file {d['dose_file']}")
    lines += ["", "## 3. What stopped", ""]
    lines.append("Nothing stopped: every state reproduces the dose file, so both scenarios were built in every state."
                 if not stopped else "Stopped, with the reason: " + "; ".join(f"{k}: {v}" for k, v in stopped.items()))
    CHECK_DOC.write_text(head + "\n".join(lines) + "\n")


def _primary(doc: dict) -> dict:
    """The primary run's sample and classes, from the regenerated second_number_design.json."""
    labs = [sn.cap_label(c) for c in sn.CAPS]
    cls = {u["utility"]: u["class_by_form"] for u in doc["utilities"]}
    dose = {u["utility"]: u["assigned_change_in_dose_points"] for u in doc["utilities"]}
    for uid, e in doc["utilities_with_no_assigned_dose"].items():
        if "by_form" in e:
            cls[uid] = {lab: e["by_form"][lab]["class"] for lab in labs}
    return {"sample": {u["utility"] for u in doc["utilities"]}, "class": cls, "dose": dose}


def _vs_r2(ours: dict, which: dict, r2: dict) -> dict:
    """Every count that differs from R2's, with both; nothing is adjusted to match (the prompt's rule)."""
    return {k: {"r2": r2[k], "here": ours[mine], "here_counted_as": mine} for k, mine in which.items() if ours[mine] != r2[k]}


def _uids(keys) -> set:
    return {sn._uid(k) for k in keys}


def main() -> int:
    from pipeline.analysis import power_simulation as ps
    from pipeline.analysis import usable_flag
    from pipeline.electricity import market_region, panel
    inp, entries, dose_file, affected, fids = real_inputs()
    state_of = inp.fac.state

    # ---- the check, first: every setting at the inventory's
    rec0 = realise_history(inp, entries, {})
    check = reconstruction_check(rec0["gwh"], inp.base, dose_file, affected, rec0["factor"], rec0["frozen_factor"])
    failed = sorted(st for st, r in check.items() if not r["passes"])
    stopped = {st: "the per-state reconstruction does not reproduce the dose file there; both scenarios recompute this "
                   "state through the same realise call, so neither is built or summarized there" for st in failed}
    _write_check(check, stopped, rec0["states_with_no_site"])

    # ---- the two scenarios' settings (pure rules)
    sites, carried, capacity = placement_inputs(inp)
    placement = runner_up_placement(sites, carried, capacity, set(inp.units))
    set_a = scenario_a_settings(placement, state_of)
    set_b, b_rec = scenario_b_settings(entries, state_of)
    ok_states = [st for st in sorted({s for _, s in inp.units}) if st not in stopped]
    hist = {SCENARIO_A: realise_history(inp, entries, {k: v for k, v in set_a.items() if k in ok_states}, ok_states),
            SCENARIO_B: realise_history(inp, entries, {k: v for k, v in set_b.items() if k in ok_states}, ok_states)}

    # ---- the sample, as second_number builds it (no design, no ownership; see the dependency note)
    q = panel.load_quantities()
    usable = usable_flag.read().usable
    regions = market_region.by_unit_year(q)
    codes = sn.region_codes(regions)
    hold = ps.price_hold()
    aff = set(affected)
    names = q.groupby(KEY).utility_name.last()
    cands, _named = sn._sample_candidates(q, hold, aff)
    doc = json.loads((FROZEN / "second_number_design.json").read_text())
    prim = _primary(doc)
    labs = [sn.cap_label(c) for c in sn.CAPS]
    years = list(sn.PRE) + list(sn.POST)
    file_pts = sn.dose_points(dose_file)
    base = inp.base
    reach_a = ({(int(r.from_utility), r.state) for r in placement[placement.moved].itertuples()} |
               {(int(r.to_utility), r.state) for r in placement[placement.moved].itertuples()})

    out_sc = {}
    for name in SCENARIOS:
        h = hist[name]
        pts, no_dose = points_of(h["gwh"], base)
        units_ok = [k for k in cands + sorted(aff) if k[1] in ok_states]
        f = scenario_frame(pts, units_ok, q, regions, usable, codes, no_dose)
        sample = _uids(f.keys)
        prim_s = {u for u in prim["sample"] if u.split(":")[1] in ok_states}
        x = sn.dose_matrix(pts, f.keys, years)
        ch = {lab: dict(zip(map(sn._uid, f.keys), sn.change(x, len(sn.PRE), c))) for lab, c in zip(labs, sn.CAPS)}

        def row(u, why=None):
            k = (int(u.split(":")[0]), u.split(":")[1])
            return {"utility": u, "name": names.get(k),
                    "change_in_dose_points_this_scenario": ({lab: round(float(ch[lab][u]), 6) for lab in labs}
                                                            if u in sample else None),
                    "change_in_dose_points_primary_as_assigned": prim["dose"].get(u),
                    "class_in_the_primary_classification": prim["class"].get(u),
                    **({"why": why} if why else {})}
        added = [row(u) for u in sorted(sample - prim_s)]
        dropped = [row(u, next((x["why"] for x in f.left_out if x["utility"] == u), "not in this scenario's frame"))
                   for u in sorted(prim_s - sample)]
        # units whose load differs from the dose file in some year, and whose change in dose differs
        g0 = rec0["gwh"]
        diff_units = sorted(sn._uid(k) for k in h["gwh"].index if not agree(h["gwh"].loc[k].values, g0.loc[k].values).all())
        prim_pts = file_pts.reindex(pd.MultiIndex.from_tuples(f.keys, names=KEY)).fillna(0.0)[years].values
        pch = {lab: dict(zip(map(sn._uid, f.keys), sn.change(prim_pts, len(sn.PRE), c))) for lab, c in zip(labs, sn.CAPS)}
        moved_dose = [{"utility": u, "name": names.get((int(u.split(":")[0]), u.split(":")[1])),
                       "this_scenario": {lab: round(float(ch[lab][u]), 6) for lab in labs},
                       "primary_as_assigned_from_the_dose_file": {lab: round(float(pch[lab][u]), 6) for lab in labs}}
                      for u in sorted(sample & prim_s) if any(not agree(ch[lab][u], pch[lab][u]) for lab in labs)]
        fac_rows = {st: {"recomputed": h["factor"][st], "inventory": h["frozen_factor"][st]}
                    for st in sorted(h["factor"]) if h["factor"][st] != h["frozen_factor"][st] or st in ("OR", "TX")}
        e = {"label": LABELS[name], "states_built": ok_states, "states_stopped": stopped,
             "sample": {"utilities": len(sample), "primary_run_utilities": len(prim_s),
                        "in_this_scenario_not_in_the_primary_run": added,
                        "in_the_primary_run_not_in_this_scenario": dropped,
                        "frame_left_out_by_usability_region_size_or_no_dose": len(f.left_out)},
             "states_whose_factor_differs_from_the_inventory_and_OR_TX": fac_rows,
             "units_whose_load_differs_from_the_reconstruction_in_some_year": {
                 "count": len(diff_units), "units": diff_units,
                 "what": ("against the reconstruction at every setting of the inventory (realise with no settings), in "
                          "which the two sites with no load history already sit at their early end, so the count is "
                          "what this scenario's own kind of question moves; the reconstruction equals the dose file for "
                          "every unit no load-unknown site reaches (the check)")},
             "sample_units_whose_change_in_dose_differs_from_the_primary_at_some_form": moved_dose,
             "units_with_load_and_no_positive_base_no_dose": [sn._uid(k) for k in no_dose]}
        if name == SCENARIO_A:
            mv = placement[placement.moved]
            e["counts"] = {"sites": int(len(placement)), "sites_moved": int(len(mv)),
                           "sites_staying": int((~placement.moved).sum()),
                           "units_gaining_or_losing_a_site_by_placement": len(reach_a),
                           "units_carrying_different_load_on_realised_load": len(diff_units),
                           "r2_counts": R2_COUNTS[SCENARIO_A]}
            e["counts"]["differs_from_r2"] = _vs_r2(e["counts"], {"sites": "sites", "sites_moved": "sites_moved",
                                                                  "units_carrying_different_load":
                                                                      "units_gaining_or_losing_a_site_by_placement"},
                                                    R2_COUNTS[SCENARIO_A])
            e["rule"] = RULE_A
            e["moves"] = [{"fid": r.fid, "state": r.state, "from": int(r.from_utility), "to": int(r.to_utility)}
                          for r in mv.sort_values("rank").itertuples()]
            e["staying_why"] = placement[~placement.moved].why.value_counts().to_dict()
        else:
            mv = [r for r in b_rec if r["moves"] != "none"]
            e["counts"] = {"date_entries_with_a_convention": len(b_rec), "rows_moved": len(mv),
                           "earlier": sum(r["moves"] == "earlier" for r in mv), "later": sum(r["moves"] == "later" for r in mv),
                           "kept_one_year_intervals": [r["fid"] for r in b_rec if r["moves"] == "none"],
                           "units_carrying_different_load_on_realised_load": len(diff_units),
                           "r2_counts": R2_COUNTS[SCENARIO_B]}
            e["counts"]["differs_from_r2"] = _vs_r2(e["counts"], {k: k for k in R2_COUNTS[SCENARIO_B]},
                                                    R2_COUNTS[SCENARIO_B])
            e["settings"] = b_rec
        out_sc[name] = e

    mods = sorted(m for m in sys.modules if m.startswith("pipeline.analysis."))
    doc_out = {
        "what_this_is": ("Quantity-only and PROVISIONAL: the second number's two sensitivity scenarios (Joe, 2026-11-19, "
                         "D-107; R2 of D-106) on the design as it stands on 2026-11-19, with the per-state reconstruction "
                         "check that comes first, the sites and rows each moves, each state's factor, and the sample "
                         "differences from the primary run. The plan is a DRAFT and not frozen. No price, revenue or bill "
                         "was read; no estimate is here. They are sensitivity scenarios, not bounds or necessarily "
                         "one-change comparisons with the primary analysis."),
        "built_by": "pipeline/analysis/second_number_scenarios.py",
        "reconstruction_check": {"document": "docs/gate1/second-number-reconstruction-check-2026-11-19.md",
                                 "tolerance_relative": TOLERANCE_REL,
                                 "passes_in_every_state": not failed, "states_failing": failed,
                                 "units_compared": sum(r["units_compared"] for r in check.values()),
                                 "units_agree": sum(r["units_agree"] for r in check.values())},
        "early_end_settings_of_the_two_sites_with_no_load_history": LOAD_UNKNOWN_EARLY_END,
        "reading_of_report_sample_differences": (
            "the session's reading, Joe's to strike: for each scenario, every utility in its sample that is not in the "
            "primary run's and the reverse, by name, with its dose at each form; the class given is the utility's class "
            "in the primary classification at each form, since a single history defines no classes of its own (the "
            "agent's reading)"),
        "scenarios": out_sc,
        "dependency_on_the_ownership_repair": {
            "reads_a_design_eligibility_list_or_matched_set": False,
            "pipeline_analysis_modules_imported_by_this_run": mods,
            "ownership_imported": "pipeline.analysis.ownership" in sys.modules,
            "why": ("the scenario sample is second_number.build_frame over every panel unit less the price hold "
                    "(usability, market region, size band) and the doses are realised loads over sales; no design, "
                    "eligibility list, matched set or ownership table is read. The primary classes are read from "
                    "second_number_design.json's per-utility classes, which come from doses and histories only.")},
        "uncertain": list(UNCERTAIN),
    }
    OUT.write_text(json.dumps(doc_out, indent=1, default=str) + "\n")
    print("reconstruction:", "passes" if not failed else f"FAILS in {failed}",
          f"{doc_out['reconstruction_check']['units_agree']}/{doc_out['reconstruction_check']['units_compared']}")
    for name in SCENARIOS:
        print(name, out_sc[name]["counts"], "sample", out_sc[name]["sample"]["utilities"],
              "added", [x["utility"] for x in out_sc[name]["sample"]["in_this_scenario_not_in_the_primary_run"]],
              "dropped", [x["utility"] for x in out_sc[name]["sample"]["in_the_primary_run_not_in_this_scenario"]])
    print("ownership imported:", doc_out["dependency_on_the_ownership_repair"]["ownership_imported"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
