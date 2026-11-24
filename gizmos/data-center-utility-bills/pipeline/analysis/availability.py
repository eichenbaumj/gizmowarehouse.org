"""Eligibility from the availability mask, the provisional narrowing, and the design-side exclusion report.

Route: docs/gate1/availability-audit-route.md, as Joe ruled on it on 2026-11-16. Reads no price: its inputs
are the mask the audit writes (flags and first exclusion reasons by utility, state and year), quantities,
regions and controls.

Outcome availability and design eligibility are kept apart (ruling, item 4). This module's first part is the
outcome rule only: a utility-state is outcome-eligible for an estimate whose window is the set of years W if
and only if it is usable in every year of W. A utility-year missing from the mask, or a utility missing from
it altogether, is not usable. The function is not told whether a unit is a host, so it decides hosts and
comparison utilities alike. Region, the fuel control, degree days and reference-year size stay with the
design code (power_simulation.build_windows and the second estimate's sample); `design_exclusions` reports
who they drop and why, separately, without changing them.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from pipeline.analysis import power_simulation as ps

KEY = ["utility_id_eia", "state"]


# ---- the outcome rule ------------------------------------------------------------------------------

def stacked_window(cohort: int) -> tuple[int, ...]:
    """The ten years of cohort g's sub-experiment, g-6 to g+3, the reference year g-3 included."""
    return tuple(range(cohort - ps.PRE, cohort + ps.POST + 1))


def second_estimate_windows() -> dict[str, tuple[int, ...]]:
    """Both forms of the second estimate (power_simulation.run_second_number): the long difference and the panel form."""
    return {"long_difference": tuple(ps.LONG_PRE + ps.LONG_POST), "panel": tuple(ps.PANEL_YEARS)}


def permitted_windows() -> dict[str, tuple[int, ...]]:
    """Every window any estimate in the plan uses: each possible cohort's ten years, and both forms of the second estimate."""
    out = {f"cohort_{g}": stacked_window(g) for g in range(ps.COHORTS[0], ps.COHORTS[1] + 1)}
    out.update({f"second_estimate_{k}": v for k, v in second_estimate_windows().items()})
    return out


def usable_set(mask: pd.DataFrame) -> set[tuple[int, str, int]]:
    """{(utility_id_eia, state, year)} usable, in the form design.build(usable=...) takes."""
    m = mask[mask.usable.astype(bool)]
    return {(int(u), s, int(y)) for u, s, y in m[["utility_id_eia", "state", "year"]].itertuples(index=False)}


def eligible(usable: set, unit: tuple[int, str], years) -> bool:
    """The outcome rule. A unit absent from the mask is not eligible (ruling, item 2)."""
    u, s = int(unit[0]), unit[1]
    return all((u, s, int(y)) in usable for y in years)


# ---- the provisional narrowing (ruling, item 8) ----------------------------------------------------

def provisional_narrowing(mask: pd.DataFrame, units) -> dict:
    """Which potential comparison utilities fail EVERY permitted window, and so may have their own eligibility
    work deferred while the pass is open. Provisional; computed over every possible cohort and both forms of the
    second estimate, so no host's crossing moves it. It removes no site and no load from anything."""
    usable = usable_set(mask)
    windows = permitted_windows()
    narrowed, kept = set(), {}
    for unit in {(int(u), s) for u, s in units}:
        ok = [name for name, w in windows.items() if eligible(usable, unit, w)]
        if ok:
            kept[unit] = ok
        else:
            narrowed.add(unit)
    return {"narrowed": narrowed, "kept": kept, "fingerprint": screen_fingerprint(mask, windows)}


def retirable_questions(questions, narrowed: set) -> dict:
    """Which eligibility questions may be deferred along with the narrowed utilities.

    `questions`: iterable of dicts with `question_id`, `utilities` (every (utility_id_eia, state) whose place
    the question can change, in any setting), `moves_anchoring` (whether any setting moves a state's factor).
    A question is retirable only if every utility it can touch is narrowed AND it cannot move any state's
    anchoring. Anything else is kept, with the reason, because it can affect another eligible utility or a
    state's factor (ruling, item 8).

    `moves_anchoring` retires nothing unless it is exactly False. Absent, None or anything else is unknown, and
    unknown means retain (D-72 item 3). Corrected 2026-11-18 (D-83): a None used to be read as "does not move".
    """
    retire, keep = [], {}
    for q in questions:
        touched = {(int(u), s) for u, s in q["utilities"]}
        moves = q.get("moves_anchoring", None)
        if moves is True:
            keep[q["question_id"]] = "can move a state's anchoring"
        elif moves is not False:
            keep[q["question_id"]] = "anchoring unknown: retained"
        elif not touched:
            keep[q["question_id"]] = "names no utility: cannot show it affects none"
        elif not touched <= narrowed:
            keep[q["question_id"]] = "can affect a utility that is not narrowed: " + ", ".join(
                f"{u}:{s}" for u, s in sorted(touched - narrowed))
        else:
            retire.append(q["question_id"])
    return {"retirable": retire, "kept": keep}


def screen_fingerprint(mask: pd.DataFrame, windows: dict) -> str:
    """A hash of the mask's rows and the windows used. If either changes, the screen is stale and deferred work reopens."""
    m = mask.sort_values(["utility_id_eia", "state", "year"], kind="stable")
    h = hashlib.sha256(m[["utility_id_eia", "state", "year", "usable"]].to_csv(index=False).encode())
    h.update(json.dumps({k: list(v) for k, v in sorted(windows.items())}).encode())
    return h.hexdigest()


def screen_still_valid(fingerprint: str, mask: pd.DataFrame, windows: dict | None = None) -> bool:
    """False when the mask or the adopted windows have changed since the screen was made: reopen the deferred work."""
    return fingerprint == screen_fingerprint(mask, windows or permitted_windows())


# ---- the design-side exclusion report (ruling, item 4) ----------------------------------------------

def design_exclusions(cohorts, usable: set, units, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict,
                      dd: pd.DataFrame) -> pd.DataFrame:
    """For each cohort, every unit with a full usable window that build_windows nonetheless drops, and why.

    Replicates the `keep` test of power_simulation.build_windows (region every window year, a fuel-mix group,
    heating and cooling degree days every window year, residential customers above zero in the reference year)
    and reports each failing part by name. It changes nothing in the design; a test holds its kept set to
    build_windows' on made-up data.
    """
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    codes = {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}
    rows = []
    for g in cohorts:
        years = list(stacked_window(g))
        full = [(int(u), s) for u, s in units if eligible(usable, (u, s), years)]
        if not full:
            continue
        idx = pd.MultiIndex.from_tuples(sorted(full), names=KEY)
        rt = ps.region_matrix(regions, idx, years, codes)
        for i, (u, s) in enumerate(idx):
            why = []
            if np.isnan(rt[i]).any():
                why.append("no region in some window year")
            if pd.isna(fuel.get(s, np.nan)):
                why.append("no fuel-mix group")
            if any(pd.isna(dd.hdd.get((s, y), np.nan)) for y in years):
                why.append("no heating degree days in some window year")
            if any(pd.isna(dd.cdd.get((s, y), np.nan)) for y in years):
                why.append("no cooling degree days in some window year")
            size = cust.loc[(u, s), g + ps.REF] if (u, s) in cust.index and g + ps.REF in cust.columns else np.nan
            if not (size > 0):
                why.append("no residential customers in the reference year")
            if why:
                rows.append({"cohort": int(g), "utility_id_eia": u, "state": s, "why": "; ".join(why)})
    return pd.DataFrame(rows, columns=["cohort", "utility_id_eia", "state", "why"])


def second_estimate_exclusions(usable: set, units, q: pd.DataFrame, regions: pd.DataFrame) -> pd.DataFrame:
    """Both forms of the second estimate: every unit with a full usable window that its sample nonetheless drops, and why.

    Replicates the `keep` test of power_simulation.run_second_number (a region in every year of the form's
    window, residential customers above zero in its size year: 2010 for the long difference, 2005 for the
    panel form). Changes nothing in the design.
    """
    cust = q.pivot_table(index=KEY, columns="year", values="res_customers")
    codes = {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}
    forms = {"long_difference": (list(ps.LONG_PRE + ps.LONG_POST), ps.LONG_PRE[-1]), "panel": (list(ps.PANEL_YEARS), ps.PANEL_YEARS[0])}
    rows = []
    for name, (years, size_year) in forms.items():
        full = sorted((int(u), s) for u, s in units if eligible(usable, (u, s), years))
        if not full:
            continue
        idx = pd.MultiIndex.from_tuples(full, names=KEY)
        rt = ps.region_matrix(regions, idx, years, codes)
        for i, (u, s) in enumerate(idx):
            why = []
            if np.isnan(rt[i]).any():
                why.append("no region in some year of the window")
            size = cust.loc[(u, s), size_year] if (u, s) in cust.index and size_year in cust.columns else np.nan
            if not (size > 0):
                why.append(f"no residential customers in {size_year}")
            if why:
                rows.append({"form": name, "utility_id_eia": u, "state": s, "why": "; ".join(why)})
    return pd.DataFrame(rows, columns=["form", "utility_id_eia", "state", "why"])
