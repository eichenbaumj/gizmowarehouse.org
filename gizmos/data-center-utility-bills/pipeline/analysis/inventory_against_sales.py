#!/usr/bin/env python3
"""Does the inventory show up in sales? (PREANALYSIS.md, "Reported checks", the bullet of that name; registry id
`inventory_against_sales` in run_outcomes.py.) Reads NO price, revenue or bill, and opens NO file.

The plan's definition, verbatim:

    "For each host: the change in non-residential sales (GWh) from the mean of event years -3 to -1 to the mean of
    event years 1 to 3, minus what its 2009-2011 base would have gained at the mean growth rate of its comparison
    utilities over the same years. That is excess non-residential growth; it can be negative when other load fell, and
    enters as it is. It is set against the load the inventory adds over the same years. Reported: the slope of one on
    the other across hosts, and the share of hosts whose excess growth is at least half the inventory's figure. Slope
    between 0.5 and 1.5: "The inventory's load shows up in the utilities' own sales." Below 0.5: "The inventory
    overstates load at these utilities, or puts it on the wrong utility or in the wrong years; the per-point estimate is
    then too small, and the main estimate includes utilities that were less exposed than it assumes." Above 1.5: "These
    utilities grew more than the inventory explains.""

This check sits in the plan's order of unblinding. It is NOT run on the real panel or the real design before the freeze
(Joe, 2026-11-19, D-107: "It is not run on the real panel"). Every input is an argument: the hosts with their cohorts and
matched comparison utilities (from a design.Design through hosts_from_design, or written out), a quantities frame with
`nonres_mwh`, and the inventory's utility-year frame with `dc_gwh`. There is no main() and nothing runs at import.

The guard against a run on real data before the freeze
-------------------------------------------------------
`check` takes a required keyword `inputs_are`, with no default:
  INVENTED_INPUTS              the caller states that the frames are invented (tests). The check runs.
  RESEARCH_DATA_AFTER_THE_FREEZE
                               the explicit post-freeze call. Refused in words (InventoryCheckRefused) unless the gate file
                               pipeline/electricity/panel.GATE_FILE exists AND the environment variable AUTH_ENV is "1",
                               the same two conditions run_outcomes.load_outcomes_after_the_freeze tests. Neither holds
                               before the freeze.
Any other value is refused. A caller that omits the keyword gets a TypeError. This is a stated guard and not a proof: a
caller who passes INVENTED_INPUTS with real frames defeats it, and it says so here.

The four settings (Joe, 2026-11-19, D-107, adopting D-106 section 9, R7)
-----------------------------------------------------------------------
R7's words: "The base is the host's non-residential sales averaged over 2009 to 2011; the slope is an ordinary regression
of excess growth on the inventory's added load with an intercept; a host with a missing year is left out and named; a
comparison utility with a missing year is left out of that host's mean and named." They are the module's settings, as
named constants (BASE, SLOPE, HOST_MISSING, MATCH_MISSING, together ADOPTED). Readings refuses any other value in words.
Until 2026-11-19 each was a required argument with no default (D-104); the alternatives that were offered then
(BASE_TOTAL_RETAIL, SLOPE_THROUGH_ORIGIN, HOST_STOP, MATCH_EXCLUDE_HOST, MATCH_STOP) are kept as names only, so that a
caller that still passes one is refused in words and not by a NameError; no code path computes with them.

What the plan's words state, and how each is coded
--------------------------------------------------
before, after        the calendar years cohort-3 .. cohort-1 and cohort+1 .. cohort+3 (event years -3 to -1 and 1 to 3,
                     the event year being calendar year minus the host's cohort, its first crossing). Means are plain
                     means of the three years. The comparison utilities' years are the host's ("over the same years").
host change          mean non-residential sales after less mean before, in GWh (nonres_mwh / 1000). In the panel build
                     nonres_mwh is commercial, industrial and transportation sales, bundled and delivery-only together
                     (pipeline/electricity/panel.py, NONRES_CLASSES), so load served under retail choice is in it.
its comparison utilities
                     the host's matched comparison utilities in the design supplied (its ten, or fewer after a removal),
                     each once. Reading "its comparison utilities" as the matched set, and not the host's whole eligible
                     pool in its region, was adopted by Joe on 2026-11-19 (D-111).
comparison rate      for each matched comparison utility, (mean after / mean before) - 1 of its non-residential sales;
                     the host's rate is the plain mean of these over its matches ("the mean growth rate of its
                     comparison utilities"). That the rate is of NON-RESIDENTIAL sales, adopted by Joe on 2026-11-19
                     (D-111), follows the sentence, whose subject is non-residential sales and which names the result
                     "excess non-residential growth"; the other candidate is total retail sales. Taking the mean of
                     each utility's own rate, rather than one pooled rate (total after over total before), is the
                     most direct reading of "mean growth rate of its comparison utilities"; the pooled rate is the
                     other candidate. Both choices were adopted by Joe on 2026-11-19 (D-111); neither is an argument
                     here.
expected gain        the host's 2009-2011 base times the comparison rate; the base is its non-residential sales
                     averaged over 2009 to 2011 (BASE; D-107).
excess growth        host change less expected gain. Negative values enter as they are.
inventory figure     mean data center load after less mean before, in GWh, from `dc_gwh` of the frame supplied. The
                     inventory build writes a utility-year row only where it has load (pipeline/facilities/
                     build_inventory.py, the facility-year loop keeps `mw > 0`, and the dose frame is grouped from it),
                     so a utility-year with no row is read as no inventory load, as the build means it. That is a
                     reading of the build's code and is labelled the agent's reading. `dc_gwh` carries no crypto load
                     (build_inventory: data centers only). The history of the inventory is settled by Joe's ruling of
                     2026-11-20 (D-119), in his words: "Use the inventory as built, the load history underlying the
                     headline design, for the inventory-against-sales check." So the frame is the inventory as built,
                     the load history the headline design is built on, which run_outcomes supplies as
                     RunInputs.side.dose (INVENTORY_HISTORY_D119). The other histories once named (no anchoring, a
                     ruling 4 case) are not used for this check. This module cannot detect a frame built from another
                     history, since it takes whatever frame it is given (the row C price series text says the same of
                     its own case); that the frame is the inventory as built is the caller's responsibility.
slope                ordinary least squares of excess growth (left side) on the inventory figure (right side), across
                     the hosts with a figure, each host once and unweighted. The side each variable is on follows from
                     the plan's three readings: below 0.5 is read as the inventory overstating load, which is excess
                     growth smaller than the inventory's figure, so the inventory is the regressor. Unweighted ordinary
                     least squares is the agent's reading of "the slope". The line has an intercept (SLOPE; D-107).
share                the hosts whose excess growth is at least half the inventory's figure ("at least": >=), over the
                     hosts with a figure.
readings             0.5 <= slope <= 1.5: SENTENCE_BETWEEN; slope < 0.5: SENTENCE_BELOW; slope > 1.5: SENTENCE_ABOVE.
                     The two ends belong to "between", since the other two readings are "below" and "above". A slope
                     that cannot be computed takes no sentence and its failure is given in words.

The settings as coded, and what stays the session's reading
-----------------------------------------------------------
base           BASE_NON_RESIDENTIAL (adopted): the mean of the host's non-residential sales over 2009, 2010 and 2011,
               in GWh (nonres_mwh / 1000). A host missing any of the three is a host with a missing year.
slope          SLOPE_WITH_INTERCEPT (adopted): unweighted ordinary least squares of excess growth on the inventory's
               figure, with an intercept, across the hosts with a figure.
host_missing   HOST_EXCLUDE (adopted): a host with a missing or non-finite value in a year it needs (its own
               non-residential sales in a before or after year or a base year, or a non-finite inventory value) is left
               out of the slope and the share and named with the years. Nothing is filled.
match_missing  MATCH_LEAVE_OUT (adopted): a matched comparison utility with a missing or non-finite year is left out of
               that host's mean rate and named; the host keeps the rest.

Not settled by D-107, and stopped in words here (adopted by Joe on 2026-11-19, D-111): a matched comparison utility whose
before mean is zero or below has no growth rate, and that is not a missing year. Until 2026-11-19 it fell under the
match_missing argument by the agent's reading; R7's setting names a missing year only, so the check now stops
(CheckStopped) and names the unit, rather than extend the adopted setting to a case it does not name.

A host with no matched comparison utility, or one left with none after its matches with a missing year are left out, has
no comparison rate. It is named and left out of the slope and the share (the agent's reading; nothing is filled).

The module's five other coded readings are NOT among the four D-107 settled; they were adopted by Joe on 2026-11-19
(D-111; HANDOVER_session23_2026-11-19 section 10, items 26 to 30): growth is non-residential growth; the comparison
rate is the plain mean of each comparison utility's own rate; growth is over the whole span (event years -3 to -1
against 1 to 3); the comparison utilities are the host's matched set; excess growth is on the left of the regression.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["utility_id_eia", "state"]
BEFORE_EVENT_YEARS = (-3, -2, -1)
AFTER_EVENT_YEARS = (1, 2, 3)
BASE_YEARS = (2009, 2010, 2011)                 # build_inventory.BASE_YEARS, the treatment's denominator years
HALF = 0.5
BETWEEN = (0.5, 1.5)

# The plan's fixed sentences, verbatim (Reported checks, "Does the inventory show up in sales?").
SENTENCE_BETWEEN = "The inventory's load shows up in the utilities' own sales."
SENTENCE_BELOW = ("The inventory overstates load at these utilities, or puts it on the wrong utility or in the wrong years; "
                  "the per-point estimate is then too small, and the main estimate includes utilities that were less "
                  "exposed than it assumes.")
SENTENCE_ABOVE = "These utilities grew more than the inventory explains."

# Every value that was offered for the four elements (D-104). Only the adopted one of each is accepted (ADOPTED).
BASE_TOTAL_RETAIL = "total_retail_2009_2011"
BASE_NON_RESIDENTIAL = "non_residential_2009_2011"
SLOPE_WITH_INTERCEPT = "ols_with_intercept"
SLOPE_THROUGH_ORIGIN = "ols_through_origin"
HOST_EXCLUDE = "exclude_host_and_name"
HOST_STOP = "stop"
MATCH_LEAVE_OUT = "leave_out_match_and_name"
MATCH_EXCLUDE_HOST = "exclude_host_and_name"
MATCH_STOP = "stop"

# The four settings, adopted by Joe on 2026-11-19 (D-107, adopting D-106 section 9, R7). Not arguments: settings.
SETTINGS_SOURCE = "Joe, 2026-11-19, D-107 (adopting D-106 section 9, R7)"
BASE = BASE_NON_RESIDENTIAL              # "the host's non-residential sales averaged over 2009 to 2011"
SLOPE = SLOPE_WITH_INTERCEPT             # "an ordinary regression of excess growth on the inventory's added load with an intercept"
HOST_MISSING = HOST_EXCLUDE              # "a host with a missing year is left out and named"
MATCH_MISSING = MATCH_LEAVE_OUT          # "a comparison utility with a missing year is left out of that host's mean and named"
SETTINGS = {"base": BASE, "slope": SLOPE, "host_missing": HOST_MISSING, "match_missing": MATCH_MISSING}
# The history of the inventory the check is given, settled by Joe on 2026-11-20 (D-119), his words verbatim.
INVENTORY_HISTORY_RULED_D119 = "Joe, 2026-11-20 (D-119)"
INVENTORY_HISTORY_D119_WORDS = ("Use the inventory as built, the load history underlying the headline design, for the "
                                "inventory-against-sales check.")
INVENTORY_HISTORY_D119 = (
    "The inventory as built, the load history underlying the headline design, settled by Joe on 2026-11-20 (D-119), in "
    "his words: \"Use the inventory as built, the load history underlying the headline design, for the "
    "inventory-against-sales check.\" run_outcomes supplies it as RunInputs.side.dose (dc_gwh), the dose frame the "
    "headline design's sets are split on. This module cannot detect a frame built from another history, since it takes "
    "whatever frame it is given; that the frame is the inventory as built is the caller's responsibility.")
SETTING_WORDS = {
    "base": "the host's non-residential sales averaged over 2009 to 2011",
    "slope": "an ordinary regression of excess growth on the inventory's added load with an intercept",
    "host_missing": "a host with a missing year is left out and named",
    "match_missing": "a comparison utility with a missing year is left out of that host's mean and named",
}

# The guard (see the module docstring).
INVENTED_INPUTS = "invented_inputs"
RESEARCH_DATA_AFTER_THE_FREEZE = "research_data_after_the_freeze"
AUTH_ENV = "DCUB_OUTCOME_RUN_AUTHORIZED"          # the same variable run_outcomes.AUTH_ENV names (tested)

NO_MATCHES = "no matched comparison utility, so no comparison growth rate"
NO_MATCH_LEFT = "every matched comparison utility was left out, so no comparison growth rate"
NOT_ABOVE_ZERO = "mean non-residential sales before is not above zero, so its growth rate cannot be computed"
NOT_ABOVE_ZERO_STOP = ("is not a missing year, and D-107's setting for a comparison utility names a missing year only, so "
                       "the check stops rather than extend it (adopted by Joe on 2026-11-19, D-111)")


class CheckStopped(ValueError):
    """The check stops in words: a malformed input, or a case the settings do not cover."""


class InventoryCheckRefused(PermissionError):
    """The check is not run on research data: the plan is not frozen or the run is not authorized."""


@dataclass(frozen=True)
class Readings:
    """The four elements D-107 settled. Every field defaults to its setting; any other value is refused in words."""
    base: str = BASE
    slope: str = SLOPE
    host_missing: str = HOST_MISSING
    match_missing: str = MATCH_MISSING

    def __post_init__(self):
        for name, adopted in SETTINGS.items():
            v = getattr(self, name)
            if v != adopted:
                raise ValueError(f"Readings.{name} is {v!r}; {SETTINGS_SOURCE} settled it as {adopted!r} "
                                 f"({SETTING_WORDS[name]}), and no other value is accepted")


ADOPTED = Readings()


def _gate(inputs_are: str) -> None:
    """Refuses in words unless the inputs are invented or this is the explicit post-freeze call with the gate file present
    and AUTH_ENV set to "1"."""
    if inputs_are == INVENTED_INPUTS:
        return
    if inputs_are != RESEARCH_DATA_AFTER_THE_FREEZE:
        raise InventoryCheckRefused(f"inputs_are is {inputs_are!r}; it must be {INVENTED_INPUTS!r} or "
                                    f"{RESEARCH_DATA_AFTER_THE_FREEZE!r}")
    import os
    from pipeline.electricity import panel
    if not Path(panel.GATE_FILE).exists():
        raise InventoryCheckRefused(f"the inventory against sales is not run on research data: the gate file "
                                    f"{Path(panel.GATE_FILE).name} does not exist (the plan is not frozen; D-107)")
    if os.environ.get(AUTH_ENV) != "1":
        raise InventoryCheckRefused(f"the inventory against sales is not run on research data: the environment variable "
                                    f"{AUTH_ENV} is not set to 1 (no authorization for this run)")


def label(key) -> str:
    return f"{int(key[0])}:{key[1]}"


def _norm(key) -> tuple:
    return (int(key[0]), str(key[1]))


def hosts_from_design(d) -> list:
    """[{"host", "cohort", "matches"}] from a design.Design's `hosts` frame (key, cohort, match_keys), in its order.
    Duck-typed: anything with a `hosts` frame carrying those columns will do. Reads nothing else."""
    h = d.hosts
    if not len(h):
        return []
    return [{"host": _norm(k), "cohort": int(g), "matches": [_norm(m) for m in mk]}
            for k, g, mk in zip(h.key, h.cohort, h.match_keys)]


def _lookup(frame: pd.DataFrame, column: str, what: str) -> dict:
    """{(utility_id_eia, state, year): value} for one column. Stops on a missing column or a duplicate key; a value that
    is not finite is kept as NaN, which reads as missing. Only the named column is touched."""
    need = KEY + ["year", column]
    miss = [c for c in need if c not in frame.columns]
    if miss:
        raise CheckStopped(f"the {what} frame has no column {miss}")
    f = frame[need]
    dup = f.duplicated(KEY + ["year"])
    if dup.any():
        first = f[dup].iloc[0]
        raise CheckStopped(f"the {what} frame has a duplicate key {int(first.utility_id_eia)}:{first.state} "
                           f"{int(first.year)}; nothing is chosen between duplicates")
    vals = pd.to_numeric(f[column], errors="coerce").astype(float)
    return {(int(u), str(s), int(y)): float(v) for u, s, y, v in zip(f.utility_id_eia, f.state, f.year, vals)}


def _mean(lookup: dict, key: tuple, years, *, absent_is_zero: bool = False) -> tuple:
    """(mean over `years`, the years that are missing or not finite). With absent_is_zero, a year with no row is 0.0
    (the inventory frame's convention); a row whose value is not finite is still missing."""
    vals, missing = [], []
    for y in years:
        k = (key[0], key[1], int(y))
        if k not in lookup:
            if absent_is_zero:
                vals.append(0.0)
                continue
            missing.append(int(y))
            continue
        v = lookup[k]
        if not math.isfinite(v):
            missing.append(int(y))
        else:
            vals.append(v)
    return (float(np.mean(vals)) if not missing else float("nan")), missing


def comparison_rate(match: tuple, cohort: int, nonres: dict) -> dict:
    """One matched comparison utility's growth rate of non-residential sales, (mean after / mean before) - 1, over the
    host's years. Returns {"utility", "rate", "problem"}; problem is None or words."""
    before, mb = _mean(nonres, match, [cohort + e for e in BEFORE_EVENT_YEARS])
    after, ma = _mean(nonres, match, [cohort + e for e in AFTER_EVENT_YEARS])
    if mb or ma:
        return {"utility": label(match), "rate": None, "problem": f"non-residential sales missing in {sorted(mb + ma)}"}
    if not before > 0:
        return {"utility": label(match), "rate": None, "problem": NOT_ABOVE_ZERO}
    return {"utility": label(match), "rate": after / before - 1.0, "problem": None}


def host_figures(host: dict, nonres: dict, dc: dict) -> dict:
    """Every figure for one host under the four settings. `nonres` and `dc` are lookups in GWh. Returns a row with
    `computed` True or False and, when False, `why` in words. Raises CheckStopped for a matched comparison utility whose
    before mean is not above zero (a case the settings do not name)."""
    key, g = _norm(host["host"]), int(host["cohort"])
    before_years = [g + e for e in BEFORE_EVENT_YEARS]
    after_years = [g + e for e in AFTER_EVENT_YEARS]
    row = {"host": label(key), "cohort": g, "before_years": before_years, "after_years": after_years,
           "matches_given": len(host["matches"]), "matches_used": [], "matches_left_out": [], "computed": False, "why": None}
    # The host's own figures. A host with a missing year is left out and named (HOST_MISSING).
    nb, mb = _mean(nonres, key, before_years)
    na, ma = _mean(nonres, key, after_years)
    problems = []
    if mb or ma:
        problems.append(f"its non-residential sales are missing in {sorted(mb + ma)}")
    base, mbase = _mean(nonres, key, BASE_YEARS)                      # BASE: non-residential, 2009 to 2011
    if mbase:
        problems.append(f"its non-residential sales are missing in base years {mbase}")
    db, mdb = _mean(dc, key, before_years, absent_is_zero=True)
    da, mda = _mean(dc, key, after_years, absent_is_zero=True)
    if mdb or mda:
        problems.append(f"its inventory load is not finite in {sorted(mdb + mda)}")
    if problems:
        row["why"] = "left out and named (a host with a missing year; D-107): " + "; ".join(problems)
        return row
    row.update(nonres_before_gwh=nb, nonres_after_gwh=na, nonres_change_gwh=na - nb, base_gwh=float(base),
               base_kind=BASE, inventory_before_gwh=db, inventory_after_gwh=da, inventory_added_gwh=da - db)
    # The comparison rate. A comparison utility with a missing year is left out of this host's mean and named
    # (MATCH_MISSING).
    if not host["matches"]:
        row["why"] = NO_MATCHES
        return row
    rates = []
    for m in host["matches"]:
        r = comparison_rate(_norm(m), g, nonres)
        if r["problem"] is None:
            rates.append(r["rate"])
            row["matches_used"].append({"utility": r["utility"], "rate": r["rate"]})
            continue
        if r["problem"] == NOT_ABOVE_ZERO:
            raise CheckStopped(f"host {label(key)} (cohort {g}), matched comparison utility {r['utility']}: {r['problem']}; "
                               f"this {NOT_ABOVE_ZERO_STOP}")
        row["matches_left_out"].append({"utility": r["utility"], "why": r["problem"]})
    if not rates:
        row["why"] = NO_MATCH_LEFT
        return row
    rate = float(np.mean(rates))
    expected = float(base) * rate
    excess = (na - nb) - expected
    added = da - db
    row.update(comparison_mean_rate=rate, expected_gain_gwh=expected, excess_growth_gwh=excess, computed=True,
               excess_at_least_half_the_inventory=bool(excess >= HALF * added))
    return row


def slope(x, y) -> dict:
    """Ordinary least squares of y (excess growth) on x (the inventory's figure), unweighted, with an intercept (SLOPE).
    Returns {"form", "slope", "intercept", "hosts", "failure"}; failure is None or words, and then slope is None."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    n = len(x)
    out = {"form": SLOPE, "slope": None, "intercept": None, "hosts": int(n), "failure": None}
    if n < 2:
        out["failure"] = f"{n} host(s) with a figure; a line with an intercept needs at least two"
        return out
    xc = x - x.mean()
    sxx = float(xc @ xc)
    if not sxx > 0:
        out["failure"] = "the inventory's figure is the same at every host, so the slope is not identified"
        return out
    b = float(xc @ (y - y.mean())) / sxx
    a = float(y.mean() - b * x.mean())
    if not math.isfinite(b):
        out["failure"] = "the slope is not finite"
        return out
    out.update(slope=b, intercept=a)
    return out


def reading(s) -> str | None:
    """The plan's sentence for a slope; None when there is no slope."""
    if s is None or not math.isfinite(s):
        return None
    if s < BETWEEN[0]:
        return SENTENCE_BELOW
    if s > BETWEEN[1]:
        return SENTENCE_ABOVE
    return SENTENCE_BETWEEN


def check(hosts: list, quantities: pd.DataFrame, dose: pd.DataFrame, readings: Readings = ADOPTED, *,
          inputs_are: str) -> dict:
    """The whole check on the hosts given (hosts_from_design(d), or [{"host", "cohort", "matches"}] written out).

    quantities  utility_id_eia, state, year, nonres_mwh (MWh); only these columns are touched
    dose        utility_id_eia, state, year, dc_gwh (the inventory's utility-year frame); only these columns are touched
    readings    ADOPTED (the default); any Readings is the adopted one, since Readings refuses every other value
    inputs_are  required keyword, no default: INVENTED_INPUTS, or RESEARCH_DATA_AFTER_THE_FREEZE, which is refused before
                the freeze (see the module docstring)

    Returns the per-host rows, the hosts left out (named, with why), the slope with its form, the plan's sentence for it
    (or the failure in words), and the share of hosts whose excess growth is at least half the inventory's figure.
    """
    _gate(inputs_are)
    if not isinstance(readings, Readings):
        raise TypeError(f"readings must be a Readings (ADOPTED); the four elements are settled ({SETTINGS_SOURCE})")
    nonres = {k: v / 1000.0 for k, v in _lookup(quantities, "nonres_mwh", "quantities").items()}
    dc = _lookup(dose, "dc_gwh", "inventory")
    seen = set()
    for h in hosts:
        k = (_norm(h["host"]), int(h["cohort"]))
        if k in seen:
            raise CheckStopped(f"host {label(k[0])} cohort {k[1]} is given twice")
        seen.add(k)
    rows = [host_figures(h, nonres, dc) for h in hosts]
    done = [r for r in rows if r["computed"]]
    left = [{"host": r["host"], "cohort": r["cohort"], "why": r["why"]} for r in rows if not r["computed"]]
    fit = slope([r["inventory_added_gwh"] for r in done], [r["excess_growth_gwh"] for r in done])
    n_half = sum(r["excess_at_least_half_the_inventory"] for r in done)
    return {
        "what_this_is": ("The plan's check 'Does the inventory show up in sales?' on the inputs given. Quantities only. "
                         f"The four elements the plan's bullet left open are settled ({SETTINGS_SOURCE}). The "
                         "inventory's history is the inventory as built, the load history underlying the headline "
                         "design (Joe, 2026-11-20, D-119); this check cannot detect a frame built from another history "
                         "and takes the frame it is given."),
        "inputs_are": inputs_are,
        "settings": dict(SETTINGS), "settings_source": SETTINGS_SOURCE,
        "hosts_given": len(rows),
        "hosts_with_a_figure": len(done),
        "hosts_left_out": left,
        "comparison_utilities_left_out": [{"host": r["host"], **m} for r in rows for m in r["matches_left_out"]],
        "by_host": rows,
        "slope": fit,
        "reading": reading(fit["slope"]),
        "reading_failure": fit["failure"],
        "share_with_excess_at_least_half_the_inventory": (n_half / len(done)) if done else None,
        "hosts_with_excess_at_least_half_the_inventory": int(n_half),
        "hosts_where_the_inventory_adds_no_load": [r["host"] for r in done if not r["inventory_added_gwh"] > 0],
    }
