#!/usr/bin/env python3
"""Quantity-side exercises and summaries the plan still owes before the freeze (PREANALYSIS.md, Open before freezing,
required items 5, 6, 13, 16 and 22; Comparison utilities, "Rows with no size"). Design side and counts only.

Reads NO price, NO revenue and NO bill. It opens the quantities file (through design.load and usable_flag.read, as
design.main does), the dose and facility files under data/interim, the ownership and supplier tables, and frozen
files under data/frozen. It never opens data/blind, data/interim/availability or any outcome file, and it runs no
simulation, no inference comparison and no regression. The three step E result files are read for summary figures only.

Which design summary it reads (Joe, 2026-11-19: "Write current design summaries under distinct names and have the
prefreeze summary reader explicitly use those current files"): every design check here reads DESIGN_SUMMARY,
data/frozen/design_support_current.json, written by pipeline/analysis/design_support_current.py on the design as it stands
after the ownership repair of 2026-11-19. It never reads the historical step E record data/frozen/design_support.json for
a design check; that file stays untouched and is the kernel's validation reference (outcome_analysis.py). The output says
which file was read, with its sha256, under `design_summary_read`.

One function per item:

  supplier_exercise        rule 2.4's run on a design (the shared-supplier exercise), with its three lists reported
                           separately: detected exclusions, unknown pairs, known omissions; then the design after
                           removal with no rematching.
  load_known_omissions     the list of known omissions (supplier_known_omissions.csv), checked.
  omission_pairs           which host and match pairs of a design each known omission reaches.
  unresolved_ownership_sensitivity
                           the labelled sensitivity that excludes hosts with unresolved ownership, set by set.
  assumed_spell_count      how many selected comparison units rely on ownership spells assumed at one end or both.
  unsized_reach            the reach of inventory rows with no size into a design's comparison units and hosts.
  late_hosts_and_shares    the number of late hosts and the four shares of 2025 data center load (Question).
  step_e_figures           the selected procedure's rates and detectable effects as the step E files hold them, and
                           whether the figures the plan quotes match those files.
  g12_descriptive_diagnostics
                           G12's and G11's mean estimate with nothing planted, slope and root-mean-square error, carried
                           from the record of that exercise with the source and the unit of each. Descriptive only.
  tariff_pairing           whether the tariff check's sampling list pairs every cohort utility.
  usable_flag_removals     hosts and comparison units the usable flag removes, by cohort, as the design summary read
                           (DESIGN_SUMMARY) records them.
  read_design_summary      the design summary named by DESIGN_SUMMARY, with a record of which file was read.

How rule 2.4's removal is coded (the plan's text: "Every comparison that shares its host's supplier in a year of the
host's window ... is removed; each host keeps its remaining matches with no rematching"): a removal is per host and
match pair. A comparison utility that shares its supplier with one host leaves that host's stack only; it stays in the
stack of any other host it is matched to and does not share a supplier with. That is not influence.leave_out, which
removes a unit from every stack (rule 7). remove_pairs does the per-pair removal; influence.estimable (rank test) and
influence.zero_weight_hosts (through estimable) are then applied unchanged.

Readings that are the agent's, not the plan's (each stated where it is used):
  - A removal "rests on assumed years" when in none of the shared years both units' rows naming the shared supplier are
    documented for that year. A row is documented for a year when both its ends are documented, or the year is an end
    marked documented. Interior years of a row with one assumed end are assumed.
  - A pair "could be tested at all" when, in at least one year of the host's window, both the host and the match have a
    known row (own generation counts as known). It is "tested in every year" when that holds in all ten.
  - A pair reached by a known omission and not detected as sharing a supplier is "unresolved by this exercise". It is
    flagged and counted; it is not removed, since the plan says flagged, not removed.
  - No supplier name is mapped to an EIA id (suppliers.shared_with_host's supplier_ids is not passed), because the plan
    rules out a new name-matching system. The supplier names spelled exactly as a panel unit's name are listed as a
    diagnostic, with whether any such unit is a host or a match in the design.

Run:  python3 -I pipeline/analysis/prefreeze_summaries.py     writes data/frozen/prefreeze_quantity_summaries.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import design, influence  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import suppliers as sp  # noqa: E402

FROZEN = design.FROZEN
INTERIM = design.INTERIM
OUT = FROZEN / "prefreeze_quantity_summaries.json"
DESIGN_SUMMARY_NAME = "design_support_current.json"   # the current design summary (design_support_current.py), read BY NAME
DESIGN_SUMMARY = FROZEN / DESIGN_SUMMARY_NAME           # never the historical step E record, design_support.json
G12_RECORD_NAME = "g12_mean_estimate_nothing_planted.json"        # the record of one authorized exercise; read by name
DRIFT_RECORD_NAME = "early_years_drift_selected_procedure.json"   # the record of another; named in a text, never read here
OMISSIONS = Path(__file__).resolve().parent / "supplier_known_omissions.csv"
OMISSION_COLUMNS = ("host", "match_or_unit", "kind", "evidence", "source_file", "entered", "amended")
OMISSION_KINDS = ("alias", "direct_supply", "system_agreement")
ALIAS_SEPARATOR = " | "
INADEQUATE = influence.INADEQUATE           # rule 2.4 and rule 7: fewer than five matches is inadequate support
KEY = ps.KEY
BASES = ("documented_at_both_ends", "assumed_at_one_end", "assumed_at_both_ends")
SUPPLIER_SETS = (ps.HEADLINE_SET, "every_cohort_utility")
DETECTED, UNKNOWN, NOT_SHARED, UNRESOLVED = "detected_exclusion", "unknown", "no_shared_supplier_detected_in_this_table", \
    "unresolved_by_this_exercise"
COHORTS = ps.COHORTS
LATE = (2023, 2025)


def label(key) -> str:
    return f"{int(key[0])}:{key[1]}"


def _key(x) -> tuple:
    if isinstance(x, str):
        u, st = x.split(":")
        return (int(u), st)
    return (int(x[0]), str(x[1]))


def _name(names, key):
    if names is None:
        return None
    v = names.get(_key(key))
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)


# ---- 2. the list of known omissions -------------------------------------------------------------------------------

def load_known_omissions(path: Path | str | None = None) -> pd.DataFrame:
    """The supplier exercise's list of known omissions, checked. Same convention as suppliers.csv: a header row and no
    comment lines. A row's `host` and `match_or_unit` are "id:ST" units for a pair kind (direct_supply, system_agreement);
    for an alias, `host` is blank and `match_or_unit` holds the two supplier names separated by " | ", as they are spelled
    in suppliers.csv. `entered` is the date the row was fixed; a later factual amendment is a new dated row (its date in
    `amended`), never a silent edit of an old one."""
    path = Path(path or OMISSIONS)
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in OMISSION_COLUMNS if c not in t.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns: {missing}")
    t = t[list(OMISSION_COLUMNS)].apply(lambda c: c.str.strip())
    for i, r in t.iterrows():
        where = f"row {i + 2} of {path.name}"
        if r.kind not in OMISSION_KINDS:
            raise ValueError(f"{where} has kind {r.kind!r}, not one of {list(OMISSION_KINDS)}")
        if not r.evidence or not r.source_file:
            raise ValueError(f"{where} has no evidence or no source_file: the list is fixed from evidence already on file")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.entered):
            raise ValueError(f"{where} has no entered date (YYYY-MM-DD)")
        if r.amended and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.amended):
            raise ValueError(f"{where} has an amended value that is not a date")
        if r.kind == "alias":
            if r.host or len([s for s in r.match_or_unit.split(ALIAS_SEPARATOR) if s.strip()]) != 2:
                raise ValueError(f"{where}: an alias row leaves host blank and names two supplier names separated by ' | '")
        else:
            try:
                _key(r.host), _key(r.match_or_unit)
            except (ValueError, IndexError):
                raise ValueError(f"{where}: a {r.kind} row names two units as 'id:ST'") from None
    return t.reset_index(drop=True)


def _supplier_names(table: pd.DataFrame, key: tuple, y: int) -> set:
    """Supplier names on unit `key`'s known rows covering year y, own generation left out."""
    rows = sp._known(sp._covering(table, key, y))
    return {s for s, k in zip(rows.supplier.str.strip(), rows.supplier_kind) if k != sp.OWN_GENERATION}


def omission_pairs(omissions: pd.DataFrame, pairs, table: pd.DataFrame) -> list:
    """Which of `pairs` [(host key, cohort, match key)] each known omission reaches, with the years for an alias.

    A pair kind reaches the pair whose host and match are its two units, in either order. An alias reaches a pair when, in
    a year of the host's window, one side's known rows name one of its two supplier names and the other side's name the
    other. Returns one entry per (omission row, pair) reached."""
    out = []
    for i, r in omissions.iterrows():
        for host, g, m in pairs:
            host, m = _key(host), _key(m)
            if r.kind == "alias":
                a, b = [s.strip() for s in r.match_or_unit.split(ALIAS_SEPARATOR)]
                years = []
                for y in own_rules.window_years(g):
                    hn, mn = _supplier_names(table, host, y), _supplier_names(table, m, y)
                    if (a in hn and b in mn) or (b in hn and a in mn):
                        years.append(y)
                if years:
                    out.append({"omission_row": int(i) + 2, "kind": r.kind, "host": label(host), "cohort": int(g), "match": label(m),
                                "years": years})
            else:
                u, v = _key(r.host), _key(r.match_or_unit)
                if {host, m} == {u, v}:
                    out.append({"omission_row": int(i) + 2, "kind": r.kind, "host": label(host), "cohort": int(g), "match": label(m),
                                "years": own_rules.window_years(g)})
    return out


# ---- 1. the shared-supplier exercise --------------------------------------------------------------------------------

def _documented_in(row, y: int) -> bool:
    fb, tb = str(row.from_year_basis), str(row.to_year_basis)
    if fb == "documented" and tb == "documented":
        return True
    return (y == int(row.from_year) and fb == "documented") or (y == int(row.to_year) and tb == "documented")


def _documented_years(table: pd.DataFrame, host: tuple, m: tuple, suppliers: list, years: list) -> list:
    """Shared years in which both units' rows naming a shared supplier are documented for that year (the agent's reading)."""
    out = []
    for y in years:
        for s in suppliers:
            h = sp._known(sp._covering(table, host, y))
            mm = sp._known(sp._covering(table, m, y))
            h, mm = h[h.supplier.str.strip() == s], mm[mm.supplier.str.strip() == s]
            if any(_documented_in(r, y) for r in h.itertuples()) and any(_documented_in(r, y) for r in mm.itertuples()):
                out.append(y)
                break
    return out


def remove_pairs(d: design.Design, removals: dict) -> design.Design:
    """A new Design with each host's listed matches removed from THAT host's stack only (rule 2.4: per host and match pair).

    `removals` maps (host key, cohort) to a set of match keys. Hosts are never removed; each keeps its remaining matches in
    their order; nothing is rematched; a unit removed from one host's stack stays in every other host's. `d` is not changed.
    The new design keeps `d`'s rules and lists (carry_design_attributes); before session 19 it lost them.
    """
    hosts = d.hosts.copy()
    matches, match_keys = [], []
    for h in d.hosts.itertuples():
        gone = {_key(k) for k in removals.get((_key(h.key), int(h.cohort)), set())}
        kept = [(int(r), mk) for r, mk in zip(h.matches, h.match_keys) if _key(mk) not in gone]
        matches.append([r for r, _ in kept])
        match_keys.append([mk for _, mk in kept])
    if len(hosts):
        hosts["matches"] = pd.Series(matches, index=hosts.index, dtype=object)
        hosts["match_keys"] = pd.Series(match_keys, index=hosts.index, dtype=object)
    e = design.Design(hosts, d.windows, d.is_comp, list(d.dropped), dict(d.region_names), dict(d.unit_code), dict(d.state_code), d.gas)
    return carry_design_attributes(d, e)


CARRIED = ("rules", "unresolved_ownership", "load_unknown_excluded", "unknown_load_source", "names")


def carry_design_attributes(src: design.Design, dst: design.Design) -> design.Design:
    """`dst`, a design made from `src` by removing comparison utilities or pairs (no host removed, nothing rematched), given
    the attributes design.build_with_rules attached to `src` and design.Design's constructor does not carry: the rules it
    was built under (the kernel reads the fuel control from them, and a validation claim checks them), the hosts with
    unresolved ownership, the load-unknown exclusions and their source, and the names. The support table is set to None:
    it describes the matches before the removal (as side_runs.remove_units does). Returns `dst` (session 19, trap 3)."""
    for attr in CARRIED:
        if hasattr(src, attr):
            setattr(dst, attr, getattr(src, attr))
    dst.support_table = None
    return dst


def after_removal(d: design.Design, removals: dict, fuel_control: str = ps.GAS_SHARE, names=None) -> dict:
    """The design after rule 2.4's removals, no rematching: matches left per host, hosts with fewer than five (named,
    inadequate support, KEPT in the estimate), hosts with none and hosts with zero weight (named, not estimable), and
    whether the fit can be computed by the rank test made before any fit (influence.estimable, unchanged)."""
    e = remove_pairs(d, removals)
    left = {label(h.key): len(h.matches) for h in e.hosts.itertuples()}
    r = influence.estimable(e, fuel_control)
    short = [h for h, n in left.items() if 0 < n < INADEQUATE]
    none = list(r["hosts_with_no_matches"])
    zero = list(r["hosts_with_zero_weight"])
    not_estimable = sorted(set(none) | set(zero))
    return {"matches_left_by_host": [{"host": h, "name": _name(names, h), "matches_left": n} for h, n in left.items()],
            "hosts_with_fewer_than_five_matches_inadequate_support_kept": [{"host": h, "name": _name(names, h), "matches_left": left[h]}
                                                                           for h in short],
            "hosts_with_no_matches_not_estimable": [{"host": h, "name": _name(names, h)} for h in none],
            "hosts_with_zero_weight_not_estimable": [{"host": h, "name": _name(names, h)} for h in zero],
            "zero_weight_checked": ("influence.zero_weight_hosts, through influence.estimable" if r["estimable"]
                                    else "not computed: the fit is not estimable by the rank test, so no weight is computed"),
            "fit_estimable_by_the_rank_test": bool(r["estimable"]),
            "smallest_singular_value_ratio": float(r["smallest_singular_value_ratio"]),
            "hosts_in_the_estimate_after_removal": len(left) - len(not_estimable),
            "the_estimate_is_over": [h for h in left if h not in not_estimable]}


def supplier_exercise(d: design.Design, table: pd.DataFrame, omissions: pd.DataFrame | None = None, names=None,
                      fuel_control: str = ps.GAS_SHARE) -> dict:
    """Rule 2.4's run on design `d` (D-58 rule 2.4; Joe at Stop 3, D-98 answer 4; D-99's readings as coded).

    For each host, over the ten years of its window, suppliers.shared_with_host on its matches, with no supplier_ids
    mapping. Three lists, reported separately: detected exclusions, unknown pairs (counted, never removed), and the known
    omissions with the pairs they reach (flagged unresolved by this exercise where not detected). Then the design after
    the detected removals, per host and match pair, with no rematching (after_removal)."""
    detected, unknown, unresolved, pairs, per_host = [], [], [], [], []
    tested_any = tested_all = 0
    removals: dict = {}
    for h in d.hosts.itertuples():
        host, g = _key(h.key), int(h.cohort)
        years = own_rules.window_years(g)
        mks = [_key(m) for m in h.match_keys]
        r = sp.shared_with_host(table, host, years, mks)
        host_known = {y: bool(len(sp._known(sp._covering(table, host, y)))) for y in years}
        removals[(host, g)] = {x["key"] for x in r["shares"]}
        for x in r["shares"]:
            doc_years = _documented_years(table, host, x["key"], [s for s in x["suppliers"]], x["years"])
            detected.append({"host": label(host), "host_name": _name(names, host), "cohort": g, "match": x["utility"],
                             "match_name": _name(names, x["key"]), "shared_supplier": x["suppliers"], "how": x["how"],
                             "years": x["years"], "rests_on_membership_alone": x["tag"] == sp.MEMBERSHIP_ONLY,
                             "membership_only_years": x["membership_only_years"],
                             "years_documented_on_both_sides": doc_years,
                             "rests_on_assumed_years": not doc_years})
        for x in r["unknown"]:
            unknown.append({"host": label(host), "host_name": _name(names, host), "cohort": g, "match": x["utility"],
                            "match_name": _name(names, x["key"]), "host_unknown_years": x["host_unknown_years"],
                            "match_unknown_years": x["match_unknown_years"]})
        for m in mks:
            if m[0] == host[0]:
                continue
            pairs.append((host, g, m))
            both = [y for y in years if host_known[y] and len(sp._known(sp._covering(table, m, y)))]
            tested_any += bool(both)
            tested_all += len(both) == len(years)
        per_host.append({"host": label(host), "name": _name(names, host), "cohort": g, "window": [years[0], years[-1]],
                         "host_supplier_unknown_years": r["host_supplier_unknown_years"],
                         "host_supplier_unknown_in_every_window_year": len(r["host_supplier_unknown_years"]) == len(years),
                         "counts": r["counts"], "own_utility_not_assessed": r["own_utility_not_assessed"]})
    reached = omission_pairs(omissions, pairs, table) if omissions is not None and len(omissions) else []
    det = {(x["host"], x["match"]) for x in detected}
    for x in reached:
        status = "detected and removed; also reached by a known omission" if (x["host"], x["match"]) in det else UNRESOLVED
        unresolved.append({**x, "status": status, "host_name": _name(names, x["host"]), "match_name": _name(names, x["match"])})
    n = len(pairs)
    return {
        "per_host": per_host,
        "pairs": n,
        "detected_exclusions": detected,
        "detected_exclusions_resting_on_membership_alone": [x for x in detected if x["rests_on_membership_alone"]],
        "unknown_pairs": unknown,
        "known_omissions_reaching_this_design": unresolved,
        "counts": {"host_match_pairs": n, "detected_exclusions": len(detected),
                   "of_which_resting_on_membership_alone": sum(x["rests_on_membership_alone"] for x in detected),
                   "of_which_resting_on_assumed_years": sum(x["rests_on_assumed_years"] for x in detected),
                   "unknown_pairs_counted_not_removed": len(unknown),
                   "pairs_unresolved_by_this_exercise": sum(x["status"] == UNRESOLVED for x in unresolved),
                   "no_shared_supplier_detected_in_this_table": n - len(detected) - len(unknown),
                   "pairs_that_could_be_tested_at_all": tested_any,
                   "share_of_pairs_that_could_be_tested_at_all": round(tested_any / n, 4) if n else None,
                   "pairs_tested_in_every_window_year": tested_all,
                   "share_of_pairs_tested_in_every_window_year": round(tested_all / n, 4) if n else None},
        "after_removal_no_rematching": after_removal(d, removals, fuel_control, names),
        "negative_finding_means": "no shared-supplier link detected in this table, not verified absence of shared supply (Joe, D-99)",
    }


def supplier_name_diagnostics(table: pd.DataFrame, q_names: pd.Series, design_units: set) -> dict:
    """Two checks on the table, reported and acted on nowhere: supplier names that differ only in case, spacing or a
    parenthetical (a possible spelling alias the exact-string comparison misses), and supplier names spelled exactly as a
    panel unit's name (the route "one supplied the other" would need them mapped; the plan rules out new name matching)."""
    names = sorted({s for s, k in zip(table.supplier.str.strip(), table.supplier_kind) if k not in (sp.UNKNOWN, sp.OWN_GENERATION) and s})
    norm: dict = {}
    for s in names:
        norm.setdefault(re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", s)).strip().lower(), []).append(s)
    by_name: dict = {}
    for (u, st), nm in q_names.items():
        by_name.setdefault(str(nm).strip().lower(), set()).add((int(u), st))
    exact = []
    for s in names:
        units = sorted(by_name.get(s.lower(), set()))
        if units:
            exact.append({"supplier": s, "panel_units_with_that_name": [label(k) for k in units],
                          "of_which_hosts_or_matches_in_the_designs": [label(k) for k in units if k in design_units]})
    return {"supplier_names_differing_only_in_case_spacing_or_a_parenthetical": [v for v in norm.values() if len(v) > 1],
            "supplier_names_spelled_as_a_panel_unit": exact}


# ---- 3. the sensitivity excluding hosts with unresolved ownership, and the assumed-spell count ------------------------

def unresolved_ownership_sensitivity(head: design.Design, sens: design.Design, names=None, fuel_control: str = ps.GAS_SHARE) -> dict:
    """The labelled sensitivity (power_simulation.UNRESOLVED_OWNERSHIP_EXCLUDED) against the headline-rules design of the
    same set: the hosts it excludes (from ownership.unresolved_ownership_hosts, through design.build_with_rules) with their
    years and reasons, the hosts remaining, whether each remaining host's matches are unchanged, support, and whether the
    fit is estimable by the rank test."""
    excluded = [{"host": x["utility"], "name": _name(names, x["utility"]), "cohort": x["cohort"], "years": x["years"], "reason": x["reason"]}
                for x in (sens.unresolved_ownership or []) if x.get("in_this_run") == "excluded"]
    hk = {(label(k), int(g)): [label(m) for m in mk] for k, g, mk in zip(head.hosts.key, head.hosts.cohort, head.hosts.match_keys)}
    remaining, changed = [], []
    for k, g, mk in zip(sens.hosts.key, sens.hosts.cohort, sens.hosts.match_keys):
        mine = [label(m) for m in mk]
        same = hk.get((label(k), int(g))) == mine
        remaining.append({"host": label(k), "name": _name(names, k), "cohort": int(g), "matches": mine, "matches_unchanged": same})
        if not same:
            changed.append(label(k))
    support = []
    if len(sens.hosts) and sens.support_table is not None:      # the support table is the one before the exclusion (design.py)
        for r in sens.support_table.itertuples():
            if any(x["host"] == f"{int(r.utility_id_eia)}:{r.state}" for x in remaining):
                support.append({"host": f"{int(r.utility_id_eia)}:{r.state}", "pool_in_the_reference_year": int(r.pool_in_the_reference_year),
                                "matched_in_region_event_year_2": int(r.matched_in_region_event_year_2),
                                "matched_in_region_event_year_3": int(r.matched_in_region_event_year_3), "keeps_its_place": bool(r.keeps_its_place)})
    est = influence.estimable(sens, fuel_control)
    return {"hosts_under_the_headline_rules": len(head.hosts), "hosts_excluded": excluded,
            "hosts_remaining": len(sens.hosts), "remaining": remaining,
            "every_remaining_hosts_matches_unchanged": not changed, "hosts_whose_matches_changed": changed,
            "support_of_the_remaining_hosts": support,
            "fit_estimable_by_the_rank_test": bool(est["estimable"]),
            "hosts_with_zero_weight": est["hosts_with_zero_weight"], "hosts_with_no_matches": est["hosts_with_no_matches"],
            "smallest_singular_value_ratio": float(est["smallest_singular_value_ratio"]),
            "note": ("applied after the support rule; nothing rematched to public or cooperative units; headline eligibility unchanged. "
                     "This sensitivity does not address the separate comparison-side uncertainty of assumed ownership spells (the plan's "
                     "sentence, Comparison utilities, Rows assumed at both ends).")}


def _year_basis(cover: pd.DataFrame) -> str | None:
    """The weakest basis among the rows covering one year: assumed at both ends, then at one end, then documented."""
    if not len(cover):
        return None
    fb, tb = cover.from_year_basis.astype(str), cover.to_year_basis.astype(str)
    if ((fb == "assumed") & (tb == "assumed")).any():
        return "assumed_at_both_ends"
    if ((fb == "assumed") | (tb == "assumed")).any():
        return "assumed_at_one_end"
    return "documented_at_both_ends"


def assumed_spell_count(d: design.Design, ownership: pd.DataFrame, ownership_of: dict, names=None) -> dict:
    """How many SELECTED comparison units (the matched units of design `d`) rely on ownership spells assumed at one end or at
    both ends over the windows of the hosts they serve, named, with the host pairs they serve.

    Per host and match pair, each window year takes the weakest basis among the match's rows covering it (assumed at both
    ends, at one end, documented at both ends), or "no row". The pair takes the weakest year; a unit takes the weakest of
    its pairs. A unit with no covering row in any year of a pair is classed by its EIA ownership class: a public or
    cooperative unit is its own owner by convention (rule 2.2); an investor-owned unit with no row is eligible only against
    a host that is not investor-owned (rule 2.2), and is listed so. The plan's check of 2026-11-19 is recomputed: whether
    every pair of an investor-owned host and an investor-owned match has a row for every window year."""
    order = {None: -1, "documented_at_both_ends": 0, "assumed_at_one_end": 1, "assumed_at_both_ends": 2}
    units: dict = {}
    pair_rows, iou_pairs = [], []
    for h in d.hosts.itertuples():
        host, g = _key(h.key), int(h.cohort)
        years = own_rules.window_years(g)
        for m in h.match_keys:
            m = _key(m)
            by_year = {y: _year_basis(own_rules._rows(ownership, m, [y])) for y in years}
            covered = [y for y in years if by_year[y] is not None]
            worst = max(by_year.values(), key=lambda v: order[v]) if covered else None
            cls = ownership_of.get(m)
            entry = {"host": label(host), "host_name": _name(names, host), "cohort": g, "match": label(m), "match_name": _name(names, m),
                     "match_ownership_class": cls, "host_ownership_class": ownership_of.get(host),
                     "basis": worst if worst else ("no_row_own_owner_by_convention" if cls != own_rules.INVESTOR_OWNED
                                                   else "no_row_investor_owned"),
                     "window_years_without_a_row": [y for y in years if by_year[y] is None]}
            pair_rows.append(entry)
            u = units.setdefault(label(m), {"match": label(m), "name": _name(names, m), "ownership_class": cls, "basis": None, "serves": []})
            u["serves"].append({"host": label(host), "cohort": g, "basis": entry["basis"]})
            if ownership_of.get(host) == own_rules.INVESTOR_OWNED and cls == own_rules.INVESTOR_OWNED:
                iou_pairs.append(entry)
    rank = {**{k: order[k] for k in BASES}, "no_row_own_owner_by_convention": -1, "no_row_investor_owned": -1}
    for u in units.values():
        u["basis"] = max((s["basis"] for s in u["serves"]), key=lambda b: rank[b])
    count = lambda rows, b: sorted({r["match"] if "match" in r else r for r in rows if r["basis"] == b})  # noqa: E731
    vals = list(units.values())
    return {
        "selected_comparison_units": len(units),
        "host_match_pairs": len(pair_rows),
        "units_by_weakest_basis": {b: len(count(vals, b)) for b in BASES + ("no_row_own_owner_by_convention", "no_row_investor_owned")},
        "units_relying_on_a_spell_assumed_at_both_ends": [u for u in vals if u["basis"] == "assumed_at_both_ends"],
        "units_relying_on_a_spell_assumed_at_one_end_and_none_at_both": [u for u in vals if u["basis"] == "assumed_at_one_end"],
        "units_documented_at_both_ends_throughout": [u for u in vals if u["basis"] == "documented_at_both_ends"],
        "units_with_no_row_own_owner_by_convention": [u for u in vals if u["basis"] == "no_row_own_owner_by_convention"],
        "units_with_no_row_investor_owned": [u for u in vals if u["basis"] == "no_row_investor_owned"],
        "pairs_by_basis": {b: sum(1 for r in pair_rows if r["basis"] == b)
                           for b in BASES + ("no_row_own_owner_by_convention", "no_row_investor_owned")},
        "investor_owned_host_and_investor_owned_match_pairs": len(iou_pairs),
        "of_which_with_a_row_in_every_window_year": sum(1 for r in iou_pairs if not r["window_years_without_a_row"]),
        "investor_owned_pairs_with_an_uncovered_window_year": [r for r in iou_pairs if r["window_years_without_a_row"]],
        "how_counted": ("per pair, each window year takes the weakest basis of the match's rows covering it; the pair takes its weakest "
                        "year; a unit takes the weakest of its pairs. Matches on such rows are 'eligible under the ownership convention', "
                        "not verified historically unaffiliated (Joe, D-99)."),
    }


# ---- 4. rows with no size ----------------------------------------------------------------------------------------------

NO_SIZE = ("mw_full is missing (NaN) in data/interim/facilities.parquet. build_inventory.py writes the inventory's "
           "'no_load_estimate' count as fac.mw_full.isna().sum() and puts a row in the dose only if energized_year, mw_full and "
           "utility_id_eia are all present (in_dose), so a row with no size carries no load in the dose.")


def _candidates(x) -> list:
    out = []
    for c in str(x or "").split(";"):
        c = c.strip()
        if c:
            try:
                out.append(int(float(c)))
            except ValueError:
                continue
    return out


def unsized_reach(facilities: pd.DataFrame, d: design.Design, net_weight: dict | None = None, names=None) -> dict:
    """The reach of inventory rows with no size into the design's comparison units and its hosts. Counts and names only: no
    imputation, no sensitivity, nothing changes eligibility (Joe, 2026-11-19).

    A unit (id, ST) is the assigned utility of a row when the row's utility_id_eia is id and its state is ST; it is a candidate
    when id is in the row's utility_candidates and the row's state is ST. `net_weight` maps a comparison unit to its net weight
    in the headline estimate (inference_check.net_weights); its share is over the sum of every comparison unit's net weight."""
    f = facilities
    unsized = f[f.mw_full.isna()]
    assigned, cand = {}, {}
    for r in unsized.itertuples():
        st = str(r.state)
        if pd.notna(r.utility_id_eia):
            assigned.setdefault((int(r.utility_id_eia), st), []).append(r.fid)
        for c in _candidates(r.utility_candidates):
            cand.setdefault((c, st), []).append(r.fid)
    total_net = float(sum(net_weight.values())) if net_weight else None

    def entry(key, serves):
        a, c = assigned.get(key, []), cand.get(key, [])
        out = {"unit": label(key), "name": _name(names, key), "rows_assigned": len(a), "rows_as_a_candidate": len(c),
               "rows_as_a_candidate_not_assigned": len(set(c) - set(a)), "rows_assigned_or_candidate": len(set(a) | set(c)),
               "assigned_rows": sorted(a), "serves": serves}
        if net_weight is not None:
            w = net_weight.get(key)
            out["net_weight"] = None if w is None else round(float(w), 6)
            out["share_of_the_comparison_sides_net_weight"] = None if w is None or not total_net else round(float(w) / total_net, 6)
        return out

    serves: dict = {}
    for h in d.hosts.itertuples():
        for m in h.match_keys:
            serves.setdefault(_key(m), []).append(label(h.key))
    comps = [entry(k, v) for k, v in sorted(serves.items())]
    reached = [x for x in comps if x["rows_assigned_or_candidate"]]
    hosts = [entry(_key(h.key), None) for h in d.hosts.itertuples()]
    out = {"definition_of_no_size": NO_SIZE, "inventory_rows": int(len(f)), "rows_with_no_size": int(len(unsized)),
           "rows_with_no_size_in_the_dose": int(unsized.in_dose.sum()) if "in_dose" in unsized.columns else None,
           "comparison_units_in_the_design": len(comps),
           "comparison_units_reached": len(reached),
           "comparison_units_reached_as_the_assigned_utility": sum(1 for x in comps if x["rows_assigned"]),
           "comparison_units_reached_as_a_candidate_only": sum(1 for x in comps if x["rows_as_a_candidate"] and not x["rows_assigned"]),
           "reached_comparison_units": reached,
           "hosts_in_the_design": len(hosts), "hosts_reached": sum(1 for x in hosts if x["rows_assigned_or_candidate"]),
           "hosts_reached_as_the_assigned_utility": sum(1 for x in hosts if x["rows_assigned"]), "hosts": hosts}
    if net_weight is not None:
        out["sum_of_comparison_net_weights"] = round(total_net, 6) if total_net is not None else None
        out["net_weight_of_reached_comparison_units"] = round(sum(x["net_weight"] or 0.0 for x in reached), 6)
        out["share_of_comparison_net_weight_reached"] = (round(sum(x["net_weight"] or 0.0 for x in reached) / total_net, 6)
                                                         if total_net else None)
    out["reading"] = ("This changes no one's eligibility; the existing influence exercises remain required, and their results do not "
                      "establish that missing load is harmless (Joe, 2026-11-19).")
    return out


# ---- 5. figures of open item 13 ----------------------------------------------------------------------------------------

def late_hosts_and_shares(dose: pd.DataFrame, theta: float, headline: set, history: dict | None = None, year: int = 2025) -> dict:
    """The number of late hosts and the four shares of the inventory's `year` data center load (Question): long-time hosts
    (first crossing before 2011), cohort utilities (2011 to 2022), the headline set, and late hosts (2023 to 2025).

    Groups follow power_simulation.design's first crossing (the first year the dose reaches `theta`, with D-34's histories
    applied), on the inventory as built. Load is dc_mw in `year` from utility_year_dose.parquet (data centers only, crypto
    excluded); the denominator is every utility-state's dc_mw that year, which is every row of the inventory in the dose.
    The headline set is a subset of the cohort utilities, so the four shares do not add to one; the remainder (utilities
    with load that never reach `theta`) is given so that the groups that do partition the load can be checked."""
    first = dose[dose.dose >= theta].groupby(KEY).year.min()
    first.index = [(int(u), st) for u, st in first.index]
    for k, v in (history or {}).items():
        k = _key(k)
        if v["group"] == "cohort":
            first[k] = int(v["first_crossing"])
        else:
            first = first.drop(k, errors="ignore")
            if v["group"] == "early":
                first[k] = COHORTS[0] - 1
    group = {k: ("early" if g < COHORTS[0] else "cohort" if g <= COHORTS[1] else "late" if LATE[0] <= g <= LATE[1] else "other")
             for k, g in first.items()}
    load = dose[dose.year == year].groupby(KEY).dc_mw.sum()
    load.index = [(int(u), st) for u, st in load.index]
    total = float(load.sum())
    share = lambda keys: round(float(load.reindex(list(keys)).fillna(0).sum()) / total, 6) if total else None  # noqa: E731
    by = {g: sorted(k for k, v in group.items() if v == g) for g in ("early", "cohort", "late", "other")}
    never = [k for k in load.index if k not in group]
    return {"threshold": f"{theta:.0%}", "year": year, "inventory_dc_mw_in_the_year": round(total, 3),
            "counts": {"long_time_hosts": len(by["early"]), "cohort_utilities": len(by["cohort"]), "headline_set": len(headline),
                       "late_hosts": len(by["late"])},
            "late_hosts": [label(k) for k in by["late"]],
            "late_hosts_first_crossing": {label(k): int(first[k]) for k in by["late"]},
            "shares_of_the_years_data_center_load": {"long_time_hosts": share(by["early"]), "cohort_utilities": share(by["cohort"]),
                                                     "headline_set": share(headline), "late_hosts": share(by["late"]),
                                                     "remainder_never_reaching_the_threshold": share(never)},
            "how": ("first crossing as power_simulation.design reads it (dose >= threshold, D-34 histories applied), on the inventory "
                    "as built; long-time hosts before 2011, cohort 2011 to 2022, late hosts 2023 to 2025. Load: dc_mw (data centers "
                    "only) in utility_year_dose.parquet for the year. The late hosts here are as built; E2's late hosts carry further "
                    "conditions (every admissible history, not set aside, price hold) and are not counted here.")}


PLAN_QUOTES = {   # the stand-in table and the second number's coverage, as PREANALYSIS.md quotes them (read 2026-11-19)
    "table": [
        ("Headline, 2% (7)", ("new_host_estimate", "2%", "headline_set"), 7, -0.15, 3.07, 6.65, 95.0, 3.3),
        ("With the ten-year case, 2% (6)", ("new_host_estimate", "2%", "headline_set_with_the_ten_year_case"), 6, -1.19, 2.99, 6.75, 94.0, 1.6),
        ("Every cohort utility as built, 2% (36)", ("new_host_estimate", "2%", "every_cohort_utility"), 36, -0.38, 1.26, 3.11, 97.6, 9.8),
        ("Headline, 5% (5)", ("new_host_estimate", "5%", "headline_set"), 5, -1.47, 4.89, 10.32, 90.2, 0.0),
        ("Every cohort utility as built, 5% (30)", ("new_host_estimate", "5%", "every_cohort_utility"), 30, -0.70, 1.85, 3.76, 92.0, 5.2),
        ("Side run, own-state comparisons, headline (7)", ("side_runs", "comparison_utilities_from_the_hosts_own_state_headline_set"),
         7, 0.69, 3.04, 6.66, 92.5, 5.4),
        ("Side run, own-state comparisons, every cohort utility (36)",
         ("side_runs", "comparison_utilities_from_the_hosts_own_state_every_cohort_utility"), 36, 0.52, 1.40, 3.33, 96.3, 6.1),
    ],
    "second_number_covers_zero": {"capped_at_25_points": 96.6, "capped_at_50_points": 94.9, "uncapped": 84.9},
    "drawn_errors_zero_headline_2pct": 94.4,
}


def _dig(doc, path):
    for p in path:
        doc = doc[p]
    return doc


def step_e_figures(stage1: dict, stage2: dict, sim: dict) -> dict:
    """The selected procedure's rates and detectable effects as the three step E files hold them, and whether each figure the
    plan quotes matches its file field (rounded as the plan rounds). Read only; nothing is rerun or derived."""
    sel = stage1["selection"]
    rates = {}
    for which in ("range", "early_years_test"):
        bp = stage2[which]["by_process"]
        hi = max(bp, key=lambda k: bp[k]["rate"])
        lo = min(bp, key=lambda k: bp[k]["rate"])
        rates[which] = {"verdict": stage2[which]["verdict"], "datasets_per_process": stage2["datasets_per_process"],
                        "highest_rate": {"process": hi, "rate": bp[hi]["rate"], "upper_bound_95": bp[hi]["upper_bound_95"]},
                        "lowest_rate": {"process": lo, "rate": bp[lo]["rate"], "upper_bound_95": bp[lo]["upper_bound_95"]},
                        "largest_upper_bound": max(v["upper_bound_95"] for v in bp.values()),
                        "by_process": {k: {"count": v["count"], "rate": v["rate"], "upper_bound_95": v["upper_bound_95"]} for k, v in bp.items()},
                        "source": f"data/frozen/inference_validation_stage2.json, {which}.by_process"}
    detect = {}
    for t, sets in sim["new_host_estimate"].items():
        for s, v in sets.items():
            detect[f"{s} at {t}"] = {
                "hosts": v["hosts_in_the_panel_for_their_whole_window"],
                "smallest_increase_detected_in_the_correct_direction_four_times_in_five_pct":
                    v["start_years_exact"]["smallest_increase_detected_in_the_correct_direction_four_times_in_five"],
                "same_with_permit_dated_start_years_redrawn_from_measured_permit_errors_pct":
                    v["start_years_misdated"]["smallest_increase_detected_in_the_correct_direction_four_times_in_five"],
                "numerical_failures": v["numerical_failures"]["selected_procedure"]["count"],
                "highest_power_on_the_planted_grid": max(v["start_years_exact"]["range_entirely_above_zero_by_planted_pct"].values()),
                "note": (f"None in the file: the 80% line is not reached on the planted grid of 0 to {max(int(x) for x in v['start_years_exact']['range_entirely_above_zero_by_planted_pct'])}%"
                         if v["start_years_exact"]["smallest_increase_detected_in_the_correct_direction_four_times_in_five"] is None else None),
                "source": f"data/frozen/power_simulation.json, new_host_estimate.{t}.{s}.start_years_exact / start_years_misdated"}
    checks = []
    for row, path, n, mean, sd, half, cover, fail in PLAN_QUOTES["table"]:
        v = _dig(sim, path)
        np_ = v["nothing_planted"]
        got = {"hosts": v["hosts_in_the_panel_for_their_whole_window"], "mean": np_["mean_estimate"],
               "sd": np_["sd_of_estimates"], "half_width": np_["range_half_width_mean"],
               "covers_zero_pct": 100 * np_["range_covers_zero"],
               "early_years_fails_pct": 100 * v["early_years_test"]["share_of_flat_histories_failing_at_p_below_0.10"]}
        quoted = {"hosts": n, "mean": mean, "sd": sd, "half_width": half, "covers_zero_pct": cover, "early_years_fails_pct": fail}
        # The plan rounds to two decimals (one for percentages); a quote matches when the file's value rounds half-up to it.
        tol = {"hosts": 0, "mean": 0.005, "sd": 0.005, "half_width": 0.005, "covers_zero_pct": 0.05, "early_years_fails_pct": 0.05}
        checks.append({"row": row, "quoted_in_plan": quoted, "in_file": {k: round(x, 4) for k, x in got.items()},
                       "matches": all(abs(got[k] - quoted[k]) <= tol[k] + 1e-9 for k in quoted),
                       "source": "data/frozen/power_simulation.json, " + ".".join(path) + ".nothing_planted / early_years_test"})
    ld = sim["per_point_of_load"]["long_difference"]
    for k, q in PLAN_QUOTES["second_number_covers_zero"].items():
        got = round(100 * ld[k]["range_covers_zero"], 1)
        checks.append({"row": f"second number, {k}, range covers zero", "quoted_in_plan": q, "in_file": got, "matches": abs(got - q) < 0.051,
                       "source": f"data/frozen/power_simulation.json, per_point_of_load.long_difference.{k}.range_covers_zero"})
    z = round(100 * sim["new_host_estimate"]["2%"]["headline_set"]["date_errors_drawn_for_these_hosts"]["exact"], 1)
    checks.append({"row": "headline 2%: share of drawn date errors that are zero", "quoted_in_plan": PLAN_QUOTES["drawn_errors_zero_headline_2pct"],
                   "in_file": z, "matches": abs(z - PLAN_QUOTES["drawn_errors_zero_headline_2pct"]) < 0.051,
                   "source": "data/frozen/power_simulation.json, new_host_estimate.2%.headline_set.date_errors_drawn_for_these_hosts.exact"})
    s1c = stage1["by_candidate"]
    return {
        "selected_procedure": {"selected": sel["selected"], "why": sel["why"], "stage1_survivors": sel["screen"]["survivors"],
                               "stage1_cells_at_or_over_the_threshold": sel["screen"]["cells_at_or_over_the_threshold"],
                               "stage1_threshold_count": sel["screen"]["threshold_count"],
                               "pooled_median_width": {k: s1c[k]["pooled_widths"]["median"] for k in s1c},
                               "source": "data/frozen/inference_comparison_stage1.json, selection and by_candidate.*.pooled_widths"},
        "validation_rates_of_the_selected_procedure": rates,
        "detectable_effects": detect,
        "plan_quotes_checked_against_the_files": checks,
        "early_years_test_catches_a_drift_of_1pct_a_year_under_the_selected_procedure_on_the_design_as_it_stands": (
            "not in the three step E files. Stage 1 and stage 2 hold the flat-history rate and the range's miss rate by process; "
            "power_simulation.json holds the flat-history rate and power for planted level effects; none holds a planted drift. "
            "inference_check.json holds 'with_a_pre_trend_of_1pct_a_year' for the bootstrap as built on an earlier design (D-49, D-53); "
            "it is not under the selected procedure or on this design and is not substituted. On file since 2026-11-20 in a record of "
            f"its own, data/frozen/{DRIFT_RECORD_NAME} (one authorized exercise, D-113 and D-114), which this module does not read."),
        "g12_mean_estimate_with_nothing_planted": (
            "not in the three step E files. inference_comparison_stage1.json, by_candidate.C.by_process.G12_fuel_shocks_not_linear_in_the_share "
            "holds its rates, widths, power at a planted 5% ramp and realised_path (slope of the estimate on the realised change "
            f"{s1c['C']['by_process']['G12_fuel_shocks_not_linear_in_the_share']['realised_path']['slope_of_the_estimate_on_the_realised_change']:.6f}, "
            f"root mean square error {s1c['C']['by_process']['G12_fuel_shocks_not_linear_in_the_share']['realised_path']['root_mean_square_error']:.6f}); "
            "no mean estimate. inference_validation_stage2.json holds rates only. On file since 2026-11-20 in a record of its own, "
            f"data/frozen/{G12_RECORD_NAME} (one authorized exercise, D-113 and D-114); the mean, the slope and the root-mean-square "
            "error are carried from that record, with their sources and units, under g12_descriptive_diagnostics beside this entry "
            "(Joe, 2026-11-20, D-115)."),
    }


G12_PROCESSES = {"G12": "G12_fuel_shocks_not_linear_in_the_share", "G11": "G11_fuel_shocks_linear_in_the_share"}
G12_STATEMENT = ("The mean is zero in expectation under the construction and cannot establish adequacy of the fuel adjustment, and a "
                 "mean away from zero would not necessarily identify a failure of that adjustment either. The mean, the slope and "
                 "the root-mean-square error are descriptive diagnostics, not a new validation verdict or selection criterion "
                 "(Joe, 2026-11-20, D-115). No threshold is set for any of them, no fuel control is changed, and no simulation was "
                 "run to produce them.")
G12_UNITS = {
    "mean_estimate_pct": ("the mean of the headline estimate with nothing planted, in log points, reported as percent (100 times "
                          "log points)"),
    "slope_of_the_estimate_on_the_realised_change": (
        "the change in the headline estimate, in log points, for one log point of realised change in the common walk between a "
        "host's reference year and its event years 2 and 3 (their mean), averaged over hosts with the design's weights "
        "(inference_comparison.realised_change); a ratio of log points to log points, so it has no unit"),
    "root_mean_square_error_pct": ("the root-mean-square error of the estimate about the true value of zero, in log points, "
                                   "reported as percent (100 times log points), the unit of the mean"),
}


def g12_descriptive_diagnostics(doc: dict) -> dict:
    """The mean estimate with nothing planted, the slope of the estimate on the realised change and the root-mean-square
    error, for G12 and G11 and for each stage, carried from the record `doc` (data/frozen/g12_mean_estimate_nothing_planted.json
    as loaded) with the source and the unit of each (Joe, 2026-11-20, D-115: "Keep the mean and report the existing slope and
    root-mean-square error for G12 and G11, identifying their sources and units."). Read only: nothing is recomputed, no
    record of a stage is opened, no threshold is applied and nothing here is a verdict. A figure missing from the record
    raises KeyError; none is derived in its place."""
    out = {"statement": G12_STATEMENT, "units": dict(G12_UNITS), "record": f"data/frozen/{G12_RECORD_NAME}",
           "record_is": "the record of one authorized exercise (D-113, D-114); read by name, not regenerated", "processes": {}}
    for short, name in G12_PROCESSES.items():
        fig = doc["figures"][name]
        rp = fig["realised_path"]
        stages = {}
        for stage, mean_key, rp_key in (("stage2", "stage2_20000_datasets", "stage2_recomputed"),
                                        ("stage1", "stage1_2000_datasets", "stage1_stored")):
            m, r = fig[mean_key], rp[rp_key]
            stages[stage] = {
                "datasets": m["datasets"], "datasets_used_for_the_mean": m["datasets_used"],
                "mean_estimate_pct": m["percent"]["mean_estimate"],
                "interval_of_the_mean_95_pct": list(m["percent"]["interval_of_the_mean_95"]),
                "mean_source": f"data/frozen/{G12_RECORD_NAME}, figures.{name}.{mean_key}.percent",
                "slope_of_the_estimate_on_the_realised_change": r["slope_of_the_estimate_on_the_realised_change"],
                "root_mean_square_error_pct": 100.0 * r["root_mean_square_error_log_points"],
                "datasets_used_for_the_slope_and_the_error": r["datasets_used"],
                "slope_and_error_source": f"data/frozen/{G12_RECORD_NAME}, figures.{name}.realised_path.{rp_key}",
                "slope_and_error_source_as_the_record_states_it": r["source"]}
        out["processes"][short] = {"process": name, "is_the_named_figure": bool(fig["is_the_named_figure"]), "by_stage": stages}
    return out


def tariff_pairing(sample: pd.DataFrame, cohort: dict) -> dict:
    """Whether the tariff check's sampling list pairs every cohort utility (`cohort`: key -> name, at 2%)."""
    paired = {(int(r.host_id), r.state) for r in sample.itertuples() if str(r.comparison_id).strip() not in ("", "nan")}
    listed = {(int(r.host_id), r.state) for r in sample.itertuples()}
    unpaired = sorted(k for k in cohort if k not in paired)
    return {"sample_rows": int(len(sample)), "cohort_utilities_at_2pct": len(cohort), "cohort_utilities_paired": len(set(cohort) & paired),
            "every_cohort_utility_paired": not unpaired,
            "unpaired": [{"utility": label(k), "name": cohort[k], "in_the_sample_without_a_comparison": k in listed} for k in unpaired],
            "sample_hosts_not_cohort_utilities_at_2pct": sorted(label(k) for k in listed - set(cohort)),
            "source": "data/frozen/tariff_check_sample.csv (host_id, state, comparison_id) against data/frozen/headline_set.csv rows at 2%"}


def usable_flag_removals(support_doc: dict, source: str = DESIGN_SUMMARY_NAME) -> dict:
    """Hosts and comparison units the usable flag removes, by cohort, as the design summary `support_doc` records them in its
    full_window_eligibility block (reason codes only; no price or revenue). `source` is that summary's file name under
    data/frozen (DESIGN_SUMMARY_NAME by default), written into each set's `source`. A comparison unit is counted once per
    cohort window in which it lacks a full usable window, among the set's eligible comparison candidates before matching."""
    out = {}
    for s, v in support_doc["sets"].items():
        fw = v.get("full_window_eligibility")
        if fw is None:
            out[s] = None
            continue
        hosts_by_cohort: dict = {}
        for x in fw["hosts"]["hosts_without_a_full_window"]:
            hosts_by_cohort.setdefault(str(x["cohort"]), []).append({"utility": x["utility"], "name": x["name"]})
        out[s] = {"hosts_in_the_set": v["hosts_in_the_set"],
                  "hosts_removed_by_the_flag_by_cohort": hosts_by_cohort,
                  "hosts_removed_by_the_flag": sum(len(x) for x in hosts_by_cohort.values()),
                  "comparison_candidates": fw["comparisons"]["candidates"],
                  "comparison_units_without_a_full_window_by_cohort": {g: c["without_a_full_window"] for g, c in fw["comparisons"]["by_cohort"].items()},
                  "comparison_units_with_a_full_window_by_cohort": {g: c["with_a_full_window"] for g, c in fw["comparisons"]["by_cohort"].items()},
                  "source": f"data/frozen/{source}, sets.{s}.full_window_eligibility"}
    out["reading"] = ("'Removes' counts units without a full usable window among the set's eligible candidates; some of them would be "
                      "out on other grounds too (the flag includes the customer floor). The flag is derived from the outcome's inputs and "
                      "this plan does not claim the selection is unrelated to the outcome (PREANALYSIS.md, Missing data).")
    return out


# ---- the run ---------------------------------------------------------------------------------------------------------

def read_design_summary(path: Path | str | None = None) -> tuple[dict, dict]:
    """(the design summary, a record of which file was read). With no `path` it reads DESIGN_SUMMARY, the current summary,
    by name. The record gives the file under data/frozen, its sha256, and the summary's own `what_this_is` and `written_by`,
    so the output says which file the design checks read."""
    import hashlib
    p = Path(DESIGN_SUMMARY if path is None else path)
    raw = p.read_bytes()
    doc = json.loads(raw)
    rec = {"file": f"data/frozen/{p.name}", "sha256": hashlib.sha256(raw).hexdigest(),
           "what_this_is": doc.get("what_this_is"), "written_by": doc.get("written_by"),
           "why_this_file": ("the current design summary, read by name (DESIGN_SUMMARY); the historical step E record "
                             "data/frozen/design_support.json is not read for any design check here (Joe, 2026-11-19)")}
    return doc, rec


def _matches_as_recorded(support_doc: dict, which: str) -> dict:
    return {(h["utility"], int(h["cohort"])): [m["utility"] for m in h["matched_utilities"]] for h in support_doc["sets"][which]["hosts"]}


def _matches_of(d: design.Design) -> dict:
    return {(label(k), int(g)): [label(m) for m in mk] for k, g, mk in zip(d.hosts.key, d.hosts.cohort, d.hosts.match_keys)}


def main() -> int:
    """Builds the designs as design.main does (headline rules and the labelled sensitivity), checks they reproduce the matches in
    the current design summary (DESIGN_SUMMARY, data/frozen/design_support_current.json), runs items 1 to 5 and writes OUT.
    Quantities only; no price, no revenue, no outcome."""
    from pipeline.analysis import usable_flag
    q, dose, regions, fuel, dd = design.load()
    names = q.groupby(KEY).utility_name.last()
    names.index = [(int(u), st) for u, st in names.index]
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(ps.HEADLINE_RULES, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    support_doc, summary_read = read_design_summary()
    table = sp.load()
    omissions = load_known_omissions()

    built, sens, repro = {}, {}, {}
    for which in design.SETS:
        treated, clean = design.split(0.02, which, q, dose)
        kw = dict(ownership=ownership, usable=usable, gas=gas, ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
        built[which] = design.build_with_rules(treated, clean, q, regions, fuel, dd, ps.HEADLINE_RULES, **kw)
        sens[which] = design.build_with_rules(treated, clean, q, regions, fuel, dd, ps.UNRESOLVED_OWNERSHIP_EXCLUDED, **kw)
        repro[which] = _matches_of(built[which]) == _matches_as_recorded(support_doc, which)
        print(which, "hosts", len(built[which].hosts), f"| matches reproduce {summary_read['file']}:", repro[which], flush=True)
    if not all(repro.values()):
        raise SystemExit(f"the rebuilt designs do not reproduce the matches in {summary_read['file']} ({repro}); stopping, nothing written")

    report = {
        "what_this_is": ("Quantity-side exercises and summaries owed before the freeze (PREANALYSIS.md, Open before freezing, required items "
                         "5, 6, 13, 16 and 22; Comparison utilities, Rows with no size). PROVISIONAL: the design stands as it is after the "
                         "ownership repair of 2026-11-19 and the plan is a DRAFT, not frozen; every figure here moves with the design. The "
                         "design checks read the current design summary, data/frozen/design_support_current.json (design_summary_read), "
                         "not the historical step E record design_support.json. Design side and counts only: no price, revenue, "
                         "bill, estimate or range is read or computed; the step E result files are read for their summary figures only."),
        "written_by": "pipeline/analysis/prefreeze_summaries.py",
        "design_summary_read": summary_read,
        "design_reproduced": {"file": summary_read["file"], "matches_reproduce_the_design_summary_read": repro,
                              "fingerprints_in_the_design_summary_read": {w: support_doc["sets"][w]["fingerprint"]["sha256"] for w in design.SETS},
                              "design_inputs_in_the_design_summary_read": {w: support_doc["sets"][w]["fingerprint"]["of"]["design_inputs"]
                                                                           for w in design.SETS}},
        "rules": "headline (ownership table, usable flag, support rule applied, gas-share control); threshold 2%",
    }

    # 1 and 2
    design_units = set()
    for d in built.values():
        for k, mk in zip(d.hosts.key, d.hosts.match_keys):
            design_units.add(_key(k))
            design_units.update(_key(m) for m in mk)
    report["shared_supplier_exercise"] = {
        "rule": ("rule 2.4 as written: a removal is per host and match pair (a comparison that shares the host's supplier leaves that "
                 "host's stack only); each host keeps its remaining matches with no rematching; hosts left with fewer than five are named "
                 "and kept; hosts left with none or with no weight are named as not estimable. influence.leave_out (every stack) is NOT "
                 "used, since it is rule 7's deletion."),
        "supplier_table": "pipeline/analysis/suppliers.csv (suppliers.load)",
        "known_omissions_file": "pipeline/analysis/supplier_known_omissions.csv",
        "known_omissions": omissions.to_dict("records"),
        "diagnostics": supplier_name_diagnostics(table, names, design_units),
        "sets": {}}
    for which in SUPPLIER_SETS:
        r = supplier_exercise(built[which], table, omissions, names)
        r["label"] = "the headline set at 2%" if which == ps.HEADLINE_SET else "labelled companion: every cohort utility as built at 2%"
        report["shared_supplier_exercise"]["sets"][which] = r
    hs = {x["host"]: x for x in report["shared_supplier_exercise"]["sets"][ps.HEADLINE_SET]["per_host"]}
    claim = {"14127:NE": "every year", "15473:NM": "every year", "17166:NV": "every year but 2017"}
    report["shared_supplier_exercise"]["plan_statement_checked"] = [
        {"host": h, "name": _name(names, h), "plan_says_unknown_in": c, "unknown_years_in_the_table": hs[h]["host_supplier_unknown_years"],
         "window": hs[h]["window"]} for h, c in claim.items()]
    report["shared_supplier_exercise"]["headline_hosts_whose_supplier_is_unknown_in_every_window_year"] = [
        {"host": h, "name": x["name"]} for h, x in hs.items() if x["host_supplier_unknown_in_every_window_year"]]
    sier = [x for x in built[ps.HEADLINE_SET].hosts.itertuples() if label(x.key) == "17166:NV"]
    report["shared_supplier_exercise"]["nevada_power_in_sierra_pacific_pool"] = (
        [e for e in sier[0].excluded_from_its_pool if e["utility"] == "13407:NV"] if sier else None)

    # 3
    report["unresolved_ownership_sensitivity"] = {
        "definition": "Joe, D-99: exclude an investor-owned host if any window year lacks an ownership row or is covered only by a row "
                      "assumed at both ends (ownership.unresolved_ownership_hosts; power_simulation.UNRESOLVED_OWNERSHIP_EXCLUDED)",
        "sets": {w: unresolved_ownership_sensitivity(built[w], sens[w], names) for w in design.SETS}}
    report["assumed_ownership_spells"] = {
        "headline_set": assumed_spell_count(built[ps.HEADLINE_SET], ownership, ownership_of, names),
        "every_cohort_utility": assumed_spell_count(built["every_cohort_utility"], ownership, ownership_of, names),
        "source": "pipeline/analysis/ownership.csv (from_year_basis, to_year_basis) over each host's window, on the matches as built",
        "plan_sentence_kept": ("the write-up says that the sensitivity excluding hosts with unresolved ownership does not address this "
                               "separate comparison-side uncertainty (PREANALYSIS.md, Comparison utilities, Rows assumed at both ends)")}

    # 4
    fac = pd.read_parquet(INTERIM / "facilities.parquet", columns=["fid", "state", "mw_full", "utility_id_eia", "utility_candidates", "in_dose"])
    d = built[ps.HEADLINE_SET]
    nw = ic.net_weights(ic.implied_weights(d, ps.GAS_SHARE)).net_weight
    net = {_key(k): float(v) for k, v in nw.items()}
    reach = unsized_reach(fac, d, net, names)
    elp = [x for x in reach["reached_comparison_units"] if x["unit"].startswith("5701:")]
    reach["el_paso_electric"] = {"units": elp, "rows_assigned": sum(x["rows_assigned"] for x in elp),
                                 "combined_net_weight": round(sum(x["net_weight"] for x in elp), 6),
                                 "combined_share_of_the_comparison_sides_net_weight": round(sum(x["net_weight"] for x in elp) / reach["sum_of_comparison_net_weights"], 6),
                                 "influence_on_quantities_json_largest_company_net_weight_removed":
                                     json.loads((FROZEN / "influence_on_quantities.json").read_text())["sets"][ps.HEADLINE_SET]["largest_net_weight_removed_by_one_company"]}
    reach["el_paso_electric"]["reading"] = (
        "0.4276 is the two units' net weight as inference_check.net_weights defines it (signed weights summed by unit and calendar "
        "year, then magnitudes summed over years), on the scale on which the hosts' headline weights sum to one; it equals "
        "influence_on_quantities.json's largest company net weight removed. The comparison units' net weights sum to more than one "
        "(sum_of_comparison_net_weights), so as a share of that sum the two units carry the figure in "
        "combined_share_of_the_comparison_sides_net_weight. Which of the two the handover's '0.43 of the comparison side's net "
        "weight' means is not stated there.")
    reach["sources"] = {"rows": "data/interim/facilities.parquet (mw_full, utility_id_eia, utility_candidates, state, in_dose)",
                        "net_weight": "inference_check.implied_weights then inference_check.net_weights on the headline design, gas-share control"}
    reach["every_cohort_utility_companion"] = {k: v for k, v in unsized_reach(fac, built["every_cohort_utility"], None, names).items()
                                               if k not in ("hosts",)}
    report["rows_with_no_size"] = reach

    # 5
    hl = pd.read_csv(FROZEN / "headline_set.csv")
    hl2 = hl[hl.threshold == "2%"]
    headline_keys = {(int(u), st) for u, st, inh in zip(hl2.utility_id_eia, hl2.state, hl2.in_headline_set) if bool(inh)}
    cohort = {(int(u), st): n for u, st, n in zip(hl2.utility_id_eia, hl2.state, hl2.name)}
    lh = late_hosts_and_shares(dose, 0.02, headline_keys, ps.history_settled(0.02))
    lh["late_hosts"] = [{"utility": u, "name": _name(names, u), "first_crossing": lh["late_hosts_first_crossing"][u]} for u in lh["late_hosts"]]
    lh["sources"] = {"dose": "data/interim/utility_year_dose.parquet (dose, dc_mw)", "headline_set": "data/frozen/headline_set.csv, threshold 2%, in_headline_set"}
    lh["check"] = {"cohort_utilities_in_headline_set_csv_at_2pct": len(cohort), "agree": lh["counts"]["cohort_utilities"] == len(cohort)}
    stage1 = json.loads((FROZEN / "inference_comparison_stage1.json").read_text())
    stage2 = json.loads((FROZEN / "inference_validation_stage2.json").read_text())
    sim = json.loads((FROZEN / "power_simulation.json").read_text())
    report["open_item_13"] = {
        "late_hosts_and_shares_of_2025_load": lh,
        "step_e": step_e_figures(stage1, stage2, sim),
        "g12_descriptive_diagnostics": g12_descriptive_diagnostics(json.loads((FROZEN / G12_RECORD_NAME).read_text())),
        "tariff_check_sample": tariff_pairing(pd.read_csv(FROZEN / "tariff_check_sample.csv"), cohort),
        "usable_flag_removals": usable_flag_removals(support_doc, Path(summary_read["file"]).name),
        "e7_sites_operating_status": "not computed here (not in this module's brief)",
    }
    report["open_item_16_status"] = ("Things to check, not corrections: the inventory point for bi:1055-0 (Meta Henrico) on a parcel the "
                                     "county records as a state government building; the FedEx (bi:446-0) and NSA (bi:937-0) points, "
                                     "unresolved on location. Status: open, not looked up (no lookup is authorized in this pass).")
    OUT.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
