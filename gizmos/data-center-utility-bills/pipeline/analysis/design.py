#!/usr/bin/env python3
"""The design that will be run, built from load and sales only: hosts, their matched comparison utilities, and support.

Reads NO price. A utility has a price wherever it has residential sales, so which utility-years
are in each cohort's sub-experiment can be worked out from quantities (as the size check of D-38 does).

For a named set of hosts (the headline set, the side set with the ten-year case, or every cohort
utility) this gives, per host: its window, its region in the reference year, and the ten eligible
comparison utilities in that region closest to it in residential customers in the reference year
(PREANALYSIS.md; D-32). The set is matched once, on the reference year, and never again year by year.

Support is two counts for every host and window year (D-46, second addendum):
  pool      eligible comparison utilities in the host's sub-experiment that are in the host's region that year
  matched   of the host's ten matched comparison utilities, how many are in the host's region that year
The second is the one that describes the regression: a matched utility that is in another region in
some year does not set the host's year effect in that year (D-37).

Run:  python3 -I pipeline/analysis/design.py        writes data/frozen/design_support.json and design_support.csv
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.electricity import market_region, panel  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
KEY = ps.KEY
PLUS_UNSETTLED = "headline_set_plus_hosts_unsettled_on_assignment"      # labelled, beside the headline (Joe, 2026-11-14; D-49's addendum)
SETS = (ps.HEADLINE_SET, ps.TEN_YEAR_SET, "every_cohort_utility", PLUS_UNSETTLED)
THIN = 10                      # what the matched set needs (D-32)


class Design:
    """Hosts with a full window, the windows they sit in, and each host's matched comparison utilities."""

    def __init__(self, hosts: pd.DataFrame, windows: dict, is_comp: dict, dropped: list, region_names: dict,
                 unit_code: dict | None = None, state_code: dict | None = None, gas: dict | None = None):
        self.hosts, self.windows, self.is_comp, self.dropped, self.region_names = hosts, windows, is_comp, dropped, region_names
        self.unit_code, self.state_code = unit_code or {}, state_code or {}
        self.gas = gas                 # state -> 2008-2010 gas share, for the gas-share control (D-59 item 7); None if not set

    def blocks(self) -> list:
        """[(cohort, host row, matched comparison rows)], one per host: what the estimator takes."""
        return [(int(h.cohort), np.array([h.row]), np.array(h.matches)) for h in self.hosts.itertuples()]


def split(theta: float, which: str, q: pd.DataFrame, dose: pd.DataFrame, frozen: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(hosts with their cohort, eligible comparison utilities) for one named set."""
    treated, clean = ps.design(q, dose, theta, ps.history_settled(theta, frozen))
    if which == "every_cohort_utility":
        return treated, clean
    aside = ps.set_aside(theta, frozen, ten_year_case=(which == ps.TEN_YEAR_SET))
    keep = lambda d, out=aside: d[[(int(u), s) not in out for u, s in zip(d.utility_id_eia, d.state)]]  # noqa: E731
    if which == PLUS_UNSETTLED:
        # The headline set with every host that only ruling 4 keeps out put back. Comparison utilities are the headline's.
        lists = ps.bounds_lists(theta, frozen)
        other = {k for k, why in ps.dates_and_histories_reasons(theta, frozen).items() if any(not x.startswith(ps.TEN_YEAR_REASON) for x in why)}
        other |= lists["does_not_keep_its_place"]
        return keep(treated, other), keep(clean)
    return keep(treated), keep(clean)


NOT_USABLE = "no usable outcome in every year of its window (D-58, rule 6.3)"
IN_REGION_OF_TEN = 8           # D-54, ruling 2: at least eight of the ten matched in the host's region in event years 2 and 3


def build(treated: pd.DataFrame, clean: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict, dd: pd.DataFrame,
          k: int = ps.MATCH_K, *, ownership: pd.DataFrame | None = None, ownership_of: dict | None = None,
          affiliates_included: bool = False, no_own_utility: bool = False, usable: set | None = None) -> Design:
    """Windows that hold the hosts and the comparison utilities together, and each host's matched set.

    Every keyword after `k` is opt-in here; with none given the Design is exactly the one built before they existed.
    From step D the runs do not call this bare: design.main, the inference check and the simulation build through
    build_with_rules, which passes the ownership table and the usable flag by default (Rules; HANDOVER.md D.2).

    ownership, ownership_of, affiliates_included
        With an ownership table (ownership.load()), a host's pool loses every candidate ownership.ineligible_for
        names (D-54, ruling 2; D-58, rules 2.2 and 2.3) BEFORE the k nearest in size are taken, so the next
        nearest eligible utility enters. `ownership_of` maps a unit to its EIA ownership class; when it is None
        it is read from q's `ownership` column (each unit's last value). `affiliates_included` is rule 2.3's
        sensitivity: same-parent affiliates come back, the host's own utility never does.
    no_own_utility
        With no ownership table, only the own-utility exclusion of D-54's ruling 2 is applied.
    usable
        A set of (utility_id_eia, state, year) with a usable outcome (D-58, rule 6.3). It replaces "meets the
        customer floor with residential sales above zero" as the template of who has an outcome, for hosts and
        comparison utilities alike: a unit is in a cohort's window only if all ten window years are in it, so
        full-window eligibility is applied before matching, and a host without a full window is dropped by name.

    When an exclusion rule is on, each host row also carries `excluded_from_its_pool`: [{"utility": "id:state",
    "why": reason}] for the candidates in its region pool that were taken out. `pool_in_the_reference_year` then
    counts the eligible pool after the exclusions, which is the pool D-54's ruling 2 tests.
    """
    everyone = pd.concat([treated[KEY], clean[KEY]]).drop_duplicates()
    if usable is None:
        real = ps.real_hosts(treated, q, regions, fuel)
        ok = q[q.meets_size_floor & (q.res_mwh > 0)][KEY + ["year"]].merge(everyone, on=KEY)
    else:
        ok = pd.DataFrame([(int(u), s, int(y)) for u, s, y in usable], columns=KEY + ["year"]).merge(everyone, on=KEY)
    template = ok.assign(log_price=0.0)                       # a price exists wherever there are residential sales (or, with `usable`, where it says)
    unit_code = {key: i for i, key in enumerate(map(tuple, everyone.values))}
    state_code = {st: i for i, st in enumerate(sorted(everyone.state.unique()))}
    cohorts = sorted(int(g) for g in treated.cohort.unique())
    windows = ps.build_windows(cohorts, template, q, regions, fuel, dd, unit_code, state_code)
    comp_keys = set(map(tuple, clean.values))
    is_comp = {g: np.array([key in comp_keys for key in w.keys]) for g, w in windows.items()}
    codes = {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}
    names = {i: r for r, i in codes.items()}
    if usable is None:
        in_window = set(real.key) if len(real) else set()
    else:
        usable_set = {(int(u), s, int(y)) for u, s, y in usable}
    excluding = ownership is not None or no_own_utility
    if ownership is not None and ownership_of is None and not affiliates_included:
        ownership_of = {(int(u), s): o for (u, s), o in q.groupby(KEY).ownership.last().items()}
    rows, dropped = [], []
    for r in treated.itertuples():
        key, g = (int(r.utility_id_eia), r.state), int(r.cohort)
        w = windows[g]
        years = range(g - ps.PRE, g + ps.POST + 1)
        if usable is not None and not all((key[0], key[1], y) in usable_set for y in years):
            dropped.append({"utility": f"{key[0]}:{key[1]}", "cohort": g, "why": NOT_USABLE})
            continue
        if (usable is None and key not in in_window) or key not in w.keys:
            why = ("no residential sales, region, fuel-mix group or degree days in every year of its window" if usable is None
                   else "no region, fuel-mix group or degree days in every year of its window")
            dropped.append({"utility": f"{key[0]}:{key[1]}", "cohort": g, "why": why})
            continue
        j = w.keys.index(key)
        pool = np.flatnonzero(is_comp[g] & (w.region == w.region[j]))
        out = {}
        if ownership is not None:
            out = own_rules.ineligible_for(ownership, key, years, [w.keys[m] for m in pool], ownership_of, affiliates_included)
        elif no_own_utility:
            out = {(int(w.keys[m][0]), w.keys[m][1]): own_rules.OWN_UTILITY for m in pool if int(w.keys[m][0]) == key[0]}
        if out:
            pool = np.array([m for m in pool if (int(w.keys[m][0]), w.keys[m][1]) not in out], dtype=int)
        matches = pool[np.argsort(np.abs(w.size[pool] - w.size[j]), kind="stable")[:k]]
        row = {"key": key, "cohort": g, "row": j, "state": key[1], "region": w.region[j], "matches": [int(m) for m in matches],
               "match_keys": [w.keys[m] for m in matches], "pool_in_the_reference_year": int(len(pool))}
        if excluding:
            row["excluded_from_its_pool"] = [{"utility": f"{c[0]}:{c[1]}", "why": why} for c, why in out.items()]
        rows.append(row)
    return Design(pd.DataFrame(rows), windows, is_comp, dropped, names, unit_code, state_code)


def support(d: Design) -> pd.DataFrame:
    """One row per host and window year: the pool and the matched count, as defined at the top of this file."""
    out = []
    for h in d.hosts.itertuples():
        w = d.windows[h.cohort]
        for t in range(ps.T):
            mine = w.region_t[h.row, t]
            out.append({"utility_id_eia": h.key[0], "state": h.key[1], "cohort": h.cohort, "year": h.cohort - ps.PRE + t,
                        "event_year": t - ps.PRE, "host_region": d.region_names.get(int(mine)),
                        "pool": int((d.is_comp[h.cohort] & (w.region_t[:, t] == mine)).sum()),
                        "matched": int((w.region_t[np.array(h.matches, dtype=int), t] == mine).sum()) if len(h.matches) else 0,
                        "matched_set_size": len(h.matches)})
    return pd.DataFrame(out)


def support_rule(d: Design, s: pd.DataFrame | None = None) -> pd.DataFrame:
    """Who keeps a place in the set under D-54's ruling 2 ("8 of 10, no own-utility"). It reports and moves no one.

    A host keeps its place if at least ten comparison utilities were eligible in its region in its reference
    year and at least eight of its ten matched comparison utilities are in its region in both event years 2
    and 3. The pool is the host row's `pool_in_the_reference_year`, which counts the pool after any exclusions
    `build` applied; the matched counts come from `support` (given as `s`, or computed).
    """
    s = support(d) if s is None else s
    out = []
    for h in d.hosts.itertuples():
        mine = s[(s.utility_id_eia == h.key[0]) & (s.state == h.key[1]) & (s.cohort == h.cohort)].set_index("event_year")
        pool, m2, m3 = int(h.pool_in_the_reference_year), int(mine.matched[2]), int(mine.matched[3])
        why = []
        if pool < THIN:
            why.append(f"{pool} eligible in its region in the reference year, fewer than {THIN}")
        for e, m in ((2, m2), (3, m3)):
            if m < IN_REGION_OF_TEN:
                why.append(f"{m} of its {len(h.matches)} matched in its region in event year {e}, fewer than {IN_REGION_OF_TEN}")
        out.append({"utility_id_eia": h.key[0], "state": h.key[1], "cohort": int(h.cohort), "pool_in_the_reference_year": pool,
                    "matched_in_region_event_year_2": m2, "matched_in_region_event_year_3": m3,
                    "keeps_its_place": not why, "why_not": "; ".join(why)})
    return pd.DataFrame(out, columns=["utility_id_eia", "state", "cohort", "pool_in_the_reference_year", "matched_in_region_event_year_2",
                                      "matched_in_region_event_year_3", "keeps_its_place", "why_not"])


def apply_support_rule(d: Design, s: pd.DataFrame | None = None) -> tuple[Design, pd.DataFrame]:
    """The support rule applied (D-54 ruling 2; PREANALYSIS.md, "Comparison support: ruled"): a host that does not keep its
    place leaves the estimate and is named in `dropped` with the reasons support_rule gives. Returns (Design, the rule's table).
    """
    rule = support_rule(d, s)
    out = {(int(r.utility_id_eia), r.state, int(r.cohort)): r.why_not for r in rule.itertuples() if not r.keeps_its_place}
    if not out:
        return d, rule
    keep = np.array([(int(k[0]), k[1], int(g)) not in out for k, g in zip(d.hosts.key, d.hosts.cohort)])
    dropped = list(d.dropped) + [{"utility": f"{u}:{st}", "cohort": g, "why": f"{SUPPORT_RULE}: {why}"} for (u, st, g), why in out.items()]
    return Design(d.hosts[keep].reset_index(drop=True), d.windows, d.is_comp, dropped, d.region_names, d.unit_code, d.state_code, d.gas), rule


SUPPORT_RULE = "does not keep its place under the support rule (D-54, ruling 2)"


def build_with_rules(treated: pd.DataFrame, clean: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict, dd: pd.DataFrame,
                     rules: ps.Rules = ps.HEADLINE_RULES, *, ownership: pd.DataFrame | None = None, usable: set | None = None,
                     gas: dict | None = None, ownership_of: dict | None = None, k: int = ps.MATCH_K,
                     unknown_load: "ps.UnknownLoad | None" = None, theta: float = 0.02) -> Design:
    """The design under `rules`: from step D the default everywhere (HANDOVER.md D.2; D-94; D-95).

    rules.ownership "table" or "affiliates_readmitted" needs `ownership` (ownership.load()); "usable" == "flag" needs
    `usable` (usable_flag.read().usable); the gas-share control needs `gas` (ps.load_gas_share()). A rule that needs an
    input it was not given stops in words, so a run cannot fall back to an older rule by omission. With the support rule
    applied, hosts that do not keep their place are moved to `dropped`, named. The support table is kept on the Design
    as `support_table` either way.

    `unknown_load` (ps.load_unknown_load(); required) and `theta` (the threshold the hosts were split at; 0.02 for the
    headline): a utility a load-unknown site reaches keeps its place as host or comparison only where the enumeration
    decided it at `theta` (treatment_bounds.json); otherwise it leaves the design before matching and is named with
    ps.LOAD_UNKNOWN in `dropped` (hosts) and in `load_unknown_excluded` (both). Its frame-computed share never makes it a
    comparison (D-96).

    Hosts with unresolved ownership (owner's ruling, 2026-11-18, Stop 3; ownership.unresolved_ownership_hosts): with the
    ownership table, the hosts left after the support rule are tested, and `unresolved_ownership` lists the investor-owned
    ones whose ownership is unresolved in a year of their window. Under rules.unresolved_ownership "kept" (the headline)
    they stay in and are listed as a stated limitation; under "hosts_excluded" (the labelled sensitivity) they leave the
    estimate, named in `dropped`, and nothing else changes: every other host keeps its matches, and no host is rematched.
    Without the table `unresolved_ownership` is None.
    """
    unknown_load = ps.require_unknown_load(unknown_load)
    treated, out_hosts = unknown_load.gate(treated, theta, "host")
    clean, out_comps = unknown_load.gate(clean, theta, "comparison")
    if rules.ownership != "off" and ownership is None:
        raise ValueError(f"rules {rules.label!r} apply the ownership table (D-58 rule 2): pass ownership=ownership.load()")
    if rules.usable == "flag" and usable is None:
        raise ValueError(f"rules {rules.label!r} take full-window eligibility from the usable flag (D-94): pass usable=usable_flag.read().usable")
    if rules.fuel_control == ps.GAS_SHARE and gas is None:
        raise ValueError(f"rules {rules.label!r} use the gas-share control (D-59 item 7): pass gas=ps.load_gas_share()")
    kw = {"usable": usable if rules.usable == "flag" else None}
    if rules.ownership != "off":
        kw.update(ownership=ownership, ownership_of=ownership_of, affiliates_included=rules.ownership == "affiliates_readmitted")
    d = build(treated, clean, q, regions, fuel, dd, k, **kw)
    d.gas = gas if rules.fuel_control == ps.GAS_SHARE else None
    if rules.support == "applied" and len(d.hosts):
        d, table = apply_support_rule(d)
    else:
        table = support_rule(d) if len(d.hosts) else None
    d.support_table = table
    d.unresolved_ownership = None
    if rules.ownership != "off" and len(d.hosts):
        d = _apply_unresolved_ownership(d, rules, ownership, ps.ownership_classes(q) if ownership_of is None else ownership_of)
    elif rules.ownership != "off":
        d.unresolved_ownership = []
    d.rules = rules
    d.dropped = [{"utility": x["utility"], "cohort": None, "why": x["why"]} for x in out_hosts] + list(d.dropped)
    d.load_unknown_excluded = out_hosts + out_comps
    d.unknown_load_source = unknown_load.source
    return d


def _apply_unresolved_ownership(d: Design, rules: ps.Rules, ownership: pd.DataFrame, ownership_of: dict) -> Design:
    """Lists the hosts whose ownership is unresolved and, under the labelled sensitivity, drops them by name (see
    build_with_rules). Returns the Design with `unresolved_ownership` set; the support table is carried over unchanged."""
    found = own_rules.unresolved_ownership_hosts(ownership, [(tuple(k), int(g)) for k, g in zip(d.hosts.key, d.hosts.cohort)], ownership_of)
    excluded = rules.unresolved_ownership == "hosts_excluded"
    listed = [{**v, "reason_by_year": {str(y): r for y, r in v["reason_by_year"].items()},
               "in_this_run": "excluded" if excluded else "kept"} for v in found.values()]
    if not excluded or not found:
        d.unresolved_ownership = listed
        return d
    keep = np.array([(int(k[0]), k[1]) not in found for k in d.hosts.key])
    dropped = list(d.dropped) + [{"utility": v["utility"], "cohort": v["cohort"], "why": f"{own_rules.UNRESOLVED_EXCLUDED}: {v['reason']}"}
                                 for v in found.values()]
    out = Design(d.hosts[keep].reset_index(drop=True), d.windows, d.is_comp, dropped, d.region_names, d.unit_code, d.state_code, d.gas)
    out.support_table = d.support_table
    out.unresolved_ownership = listed
    return out


def investor_owned_without_rows(table: pd.DataFrame, units, ownership_of: dict, names: pd.Series | None = None) -> list:
    """Every investor-owned unit among `units` with no row in the ownership table, by name (D-58 rule 2.2).

    Such a unit is not eligible as a comparison for an investor-owned host: it cannot be shown to be unaffiliated. A
    missing row is never read as "unaffiliated". Each entry says whether the unit is a host or a comparison in the set.
    """
    have = set(zip(table.utility_id_eia.astype(int), table.state)) if len(table) else set()
    ids_all_states = set(table[table.state == ""].utility_id_eia.astype(int)) if len(table) else set()
    out = []
    for key, role in units:
        key = (int(key[0]), key[1])
        if ownership_of.get(key) != own_rules.INVESTOR_OWNED:
            continue
        if key in have or key[0] in ids_all_states:
            continue
        out.append({"utility": f"{key[0]}:{key[1]}", "name": None if names is None else names.get(key), "role": role,
                    "consequence": "not eligible as a comparison for an investor-owned host whose window has a year with no ownership row covering it (D-58 rule 2.2, read year by year, 2026-11-19)"})
    return out


def gas_share_ranges(d: Design, gas: dict, names: pd.Series | None = None) -> list:
    """Per host: its state's 2008-2010 gas share beside the lowest and highest among its matched comparisons (D-59 item 7).

    A host outside that range is named as extrapolation: its gas-share adjustment rests on the linear form beyond the
    shares its own comparisons cover.
    """
    out = []
    for h in d.hosts.itertuples():
        mine = float(gas[h.key[1]])
        theirs = [float(gas[k[1]]) for k in h.match_keys]
        lo, hi = (min(theirs), max(theirs)) if theirs else (float("nan"), float("nan"))
        inside = bool(theirs) and lo <= mine <= hi
        out.append({"utility": f"{h.key[0]}:{h.key[1]}", "name": None if names is None else names.get(h.key), "cohort": int(h.cohort),
                    "host_gas_share": round(mine, 6), "lowest_among_its_matches": round(lo, 6), "highest_among_its_matches": round(hi, 6),
                    "inside_its_matches_range": inside, "extrapolation": not inside})
    return out


# ---- fingerprints (D-58 rule 10, widened by D-59 item 5) ----------------------------------------------------------
# Every expensive run records a fingerprint of its design inputs (hosts and cohort years, each host's matches, the usable
# set, the regressors and the clusters), the code version, the simulation's assumptions, the procedure's settings and the
# seeds. A matching fingerprint allows reuse; any difference means the run is redone unless a logged explanation shows
# the changed item cannot affect it.

CODE_FILES = ("pipeline/analysis/design.py", "pipeline/analysis/estimator.py", "pipeline/analysis/power_simulation.py",
              "pipeline/analysis/inference_check.py", "pipeline/analysis/influence.py", "pipeline/analysis/ownership.py",
              "pipeline/analysis/usable_flag.py", "pipeline/electricity/availability_codes.py",
              "pipeline/electricity/market_region.py")


def _canonical(x):
    """A JSON-ready form that does not depend on set or dict order or on numpy types."""
    if isinstance(x, dict):
        return {str(k): _canonical(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (set, frozenset)):
        return sorted((_canonical(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(x, (list, tuple)):
        return [_canonical(v) for v in x]
    if isinstance(x, np.ndarray):
        return {"dtype": str(x.dtype), "shape": list(x.shape), "sha256": hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest()}
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return repr(float(x))
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def _sha(x) -> str:
    return hashlib.sha256(json.dumps(_canonical(x), sort_keys=True).encode()).hexdigest()


def code_version(files=CODE_FILES, root: Path = ROOT) -> dict:
    """sha256 of each module file involved, relative to the gizmo folder."""
    return {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in files}


def design_inputs(d: Design, fuel_control: str, usable: set | None) -> dict:
    """The design inputs of rule 10: hosts and cohort years, each host's matches, the usable set, the regressors, the clusters.

    The regressors are the assembled matrix itself (built with outcomes set to zero; no outcome is read), its column
    labels and the control columns left out; the clusters are each stacked row's state.
    """
    hosts = [(int(k[0]), k[1], int(g)) for k, g in zip(d.hosts.key, d.hosts.cohort)] if len(d.hosts) else []
    matches = {f"{k[0]}:{k[1]}:{int(g)}": [f"{m[0]}:{m[1]}" for m in mk] for k, g, mk in zip(d.hosts.key, d.hosts.cohort, d.hosts.match_keys)} if len(d.hosts) else {}
    out = {"hosts_and_cohorts": hosts, "matches": matches, "usable": None if usable is None else {(int(u), s, int(y)) for u, s, y in usable},
           "fuel_control": fuel_control}
    blocks = [b for b in d.blocks() if len(b[2])] if len(d.hosts) else []
    if blocks:
        saved = {g: w.y for g, w in d.windows.items()}
        try:
            for w in d.windows.values():
                w.y = np.zeros((len(w.keys), ps.T))
            a = ps.assemble(d.windows, blocks, fuel_control=fuel_control, gas=d.gas)
        finally:
            for g, w in d.windows.items():
                w.y = saved[g]
        names = {i: st for st, i in d.state_code.items()}
        out["regressors"] = {"X": a["X"], "columns": a["columns"], "left_out": a["control_columns_left_out"],
                             "gas_shares": None if d.gas is None else {st: d.gas[st] for st in sorted({k[1] for w in d.windows.values() for k in w.keys}) if st in d.gas}}
        out["clusters"] = [names.get(int(c), str(c)) for c in a["cluster"]]
    else:
        out["regressors"], out["clusters"] = None, None
    return out


def fingerprint(components: dict) -> dict:
    """A sha256 over the named components, with one per component so a difference can be traced to what moved."""
    parts = {name: _sha(value) for name, value in components.items()}
    return {"sha256": _sha(parts), "of": parts, "version": 1}


def run_fingerprint(d: Design, *, rules: ps.Rules, usable: set | None, assumptions: dict, settings: dict, seeds,
                    code_files=CODE_FILES) -> dict:
    """The fingerprint written into each expensive run's output (design.main, the inference check, the simulation)."""
    return fingerprint({"design_inputs": design_inputs(d, rules.fuel_control, usable),
                        "rules": {"label": rules.label, "ownership": rules.ownership, "usable": rules.usable, "support": rules.support,
                                  "fuel_control": rules.fuel_control, "unresolved_ownership": rules.unresolved_ownership},
                        "code_version": code_version(code_files), "assumptions": assumptions, "settings": settings, "seeds": seeds})


def load():
    q = panel.load_quantities()
    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    regions = market_region.by_unit_year(q)
    fuel, dd = ps.load_controls()
    return q, dose, regions, fuel, dd


GAP_COLUMNS = ["utility_id_eia", "state", "cohort", "missing_years", "first_missing_year", "first_exclusion_reason"]


def unit_windows(treated: pd.DataFrame, clean: pd.DataFrame) -> list:
    """[((utility, state), cohort)]: each host in its own window, each comparison candidate in every cohort's window."""
    cohorts = sorted(int(g) for g in treated.cohort.unique())
    return ([((int(u), st), int(g)) for u, st, g in zip(treated.utility_id_eia, treated.state, treated.cohort)]
            + [((int(u), st), g) for u, st in zip(clean.utility_id_eia, clean.state) for g in cohorts])


def window_gaps(flags, windows: list) -> pd.DataFrame:
    """One row per unit and cohort window that lacks a full usable window: how many years are missing, the first, and its
    first exclusion reason code (availability_codes.NOT_IN_PANEL where the unit-year has no row). Reason codes only."""
    from pipeline.analysis import usable_flag
    from pipeline.electricity import availability_codes as av
    rows = []
    for (u, st), g in windows:
        miss = [y for y in usable_flag.window_years(g) if (u, st, y) not in flags.usable]
        if miss:
            rows.append((u, st, g, len(miss), miss[0], flags.reason.get((u, st, miss[0]), av.NOT_IN_PANEL)))
    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def eligibility_summary(flags, treated: pd.DataFrame, clean: pd.DataFrame, names: pd.Series, rules) -> dict:
    """Full-window eligibility for one set, as rule 6.3 asks: "counts by reason and the names of hosts without a full window"
    (D-58), hosts and comparisons alike, no price or revenue. Hosts are named with the first exclusion reason code of each
    missing year; comparison candidates are counted per cohort window, never listed (the per-unit rows go once to
    full_window_eligibility.csv)."""
    from pipeline.analysis import usable_flag
    host_rep = usable_flag.report(flags, [((int(u), st), int(g)) for u, st, g in zip(treated.utility_id_eia, treated.state, treated.cohort)], "host")
    lacking = [{"utility": x["utility"], "name": names.get(_key_of(x["utility"])), "cohort": x["cohort"], "missing_years": x["missing_years"]}
               for x in host_rep["hosts_without_a_full_window"]]
    by_cohort, full_everywhere = {}, set()
    comps = [(int(u), st) for u, st in zip(clean.utility_id_eia, clean.state)]
    cohorts = sorted(int(g) for g in treated.cohort.unique())
    ok_in = {k: 0 for k in comps}
    for g in cohorts:
        rep = usable_flag.report(flags, [(k, g) for k in comps], "comparison")
        by_cohort[str(g)] = {"without_a_full_window": len(rep["comparisons_without_a_full_window"]),
                             "with_a_full_window": rep["with_a_full_window"],
                             "missing_unit_years_by_first_exclusion_reason": rep["missing_unit_years_by_first_exclusion_reason"]}
        missing = {_key_of(x["utility"]) for x in rep["comparisons_without_a_full_window"]}
        for k in comps:
            ok_in[k] += k not in missing
    full_everywhere = sum(1 for k in comps if cohorts and ok_in[k] == len(cohorts))
    suffix = "" if rules == ps.HEADLINE_RULES else f"_{rules.label}"
    return {"rule": host_rep["rule"],
            "hosts": {"hosts_without_a_full_window": lacking, "with_a_full_window": host_rep["with_a_full_window"],
                      "missing_unit_years_by_first_exclusion_reason": host_rep["missing_unit_years_by_first_exclusion_reason"]},
            "comparisons": {"candidates": len(comps), "by_cohort": by_cohort,
                            "with_a_full_window_in_every_cohort_window": full_everywhere},
            "per_unit_detail": f"data/frozen/full_window_eligibility{suffix}.csv (written once for every set)"}


def _key_of(label: str) -> tuple:
    u, st = label.split(":")
    return (int(u), st)


def main() -> int:
    """Every named set under the headline rules (or a labelled variant: --rules=<label>), with support, exclusions and a fingerprint.

    Load and sales only: the usable flag is read by usable_flag.read (five columns, no price), the ownership table and the
    frozen gas shares. No price, no revenue.
    """
    from pipeline.analysis import usable_flag
    rules = ps.rules_from_argv(sys.argv)
    q, dose, regions, fuel, dd = load()
    names = q.groupby(KEY).utility_name.last()
    flags = usable_flag.read() if rules.usable == "flag" else None    # read once: the five columns, validated (D-94)
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=None if flags is None else flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()                  # stops in words on a rebuilt inventory without its file (D-96)
    report = {"what_this_is": "For each set of hosts at the 2% threshold: every host's matched comparison utilities and two support counts "
                              "in every year of its window. Load and sales only; no price is read.",
              "rules": {"label": rules.label, "ownership": rules.ownership, "usable": rules.usable, "support": rules.support,
                        "fuel_control": rules.fuel_control, "unresolved_ownership": rules.unresolved_ownership},
              "ownership_assumption": "municipal systems, public power districts and distribution cooperatives with no row in the "
                                      "ownership table are each taken as their own owner, from EIA's ownership class (D-58 rule 2.2)",
              "gas_share_assumption": ps.GAS_ASSUMPTION if rules.fuel_control == ps.GAS_SHARE else None,
              "pool": "eligible comparison utilities in the host's sub-experiment that are in the host's region that year",
              "matched": "of the host's ten matched comparison utilities (matched once, on the reference year), how many are in the host's region that year",
              "sets": {}}
    if flags is not None:
        report["usable_flag"] = {"source": "the quantities file's res_price_usable column, read by explicit columns (D-94)",
                                 "rows_read": flags.rows, "usable_unit_years": len(flags.usable)}
    tables, gaps = [], []
    for which in SETS:
        treated, clean = split(0.02, which, q, dose)
        d = build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas, ownership_of=ownership_of,
                             unknown_load=unknown, theta=0.02)
        s = support(d)
        s["set"] = which
        tables.append(s)
        hosts = []
        for h in d.hosts.itertuples():
            mine = s[(s.utility_id_eia == h.key[0]) & (s.state == h.key[1])].set_index("event_year")
            row = {"utility": f"{h.key[0]}:{h.key[1]}", "name": names.get(h.key), "cohort": h.cohort, "region_in_the_reference_year": h.region,
                   "pool": {"reference_year": int(mine.pool[ps.REF]), "event_year_2": int(mine.pool[2]), "event_year_3": int(mine.pool[3]),
                            "smallest_in_the_window": int(mine.pool.min())},
                   "matched": {"reference_year": int(mine.matched[ps.REF]), "event_year_2": int(mine.matched[2]), "event_year_3": int(mine.matched[3]),
                               "smallest_in_the_window": int(mine.matched.min())},
                   "matched_set_size": len(h.matches),
                   "matched_utilities": [{"utility": f"{k[0]}:{k[1]}", "name": names.get(k)} for k in h.match_keys],
                   "host_changes_region_in_its_window": bool(mine.host_region.nunique() > 1)}
            if "excluded_from_its_pool" in d.hosts.columns:
                row["excluded_from_its_pool"] = h.excluded_from_its_pool
            hosts.append(row)
        thin = [x["name"] for x in hosts if x["pool"]["reference_year"] < THIN]
        units = [((int(u), st), "host") for u, st in zip(treated.utility_id_eia, treated.state)] + \
                [((int(u), st), "comparison") for u, st in zip(clean.utility_id_eia, clean.state)]
        entry = {
            "hosts_in_the_set": int(len(treated)), "hosts_in_the_estimate": int(len(d.hosts)), "hosts_dropped": d.dropped,
            "eligible_comparison_utilities": int(len(clean)),
            "load_unknown_excluded": d.load_unknown_excluded, "load_unknown_source": d.unknown_load_source,
            "support_rule": ("applied: a host that does not keep its place is dropped and named (D-54 ruling 2)" if rules.support == "applied"
                             else "reported only (labelled variant)"),
            "support_rule_by_host": [] if d.support_table is None else d.support_table.to_dict("records"),
            "hosts_with_fewer_than_ten_eligible_in_their_region_in_the_reference_year": thin,
            "hosts_with_fewer_than_ten_matched_in_their_region_in_event_year_2_or_3":
                [x["name"] for x in hosts if min(x["matched"]["event_year_2"], x["matched"]["event_year_3"]) < THIN],
            "hosts": hosts}
        if ownership is not None:
            entry["investor_owned_units_with_no_ownership_row"] = investor_owned_without_rows(ownership, units, ownership_of, names)
            fate = "excluded" if rules.unresolved_ownership == "hosts_excluded" else "kept in the estimate"
            entry["hosts_with_unresolved_ownership"] = {
                "limitation": own_rules.UNRESOLVED_LIMITATION.format(fate=fate),
                "hosts": [{"utility": x["utility"], "name": names.get(_key_of(x["utility"])), "cohort": x["cohort"], "years": x["years"],
                           "reason": x["reason"], "in_this_run": x["in_this_run"]} for x in (d.unresolved_ownership or [])]}
        if flags is not None:
            entry["full_window_eligibility"] = eligibility_summary(flags, treated, clean, names, rules)
            gaps.append(window_gaps(flags, unit_windows(treated, clean)))
        if gas is not None and len(d.hosts):
            entry["gas_share_against_matches"] = gas_share_ranges(d, gas, names)
        entry["fingerprint"] = run_fingerprint(d, rules=rules, usable=usable, assumptions={"kind": "design", "set": which, "threshold": 0.02},
                                               settings={"match_k": ps.MATCH_K, "thin": THIN, "in_region_of_ten": IN_REGION_OF_TEN}, seeds=None)
        report["sets"][which] = entry
        print(which, "| hosts", len(treated), "| in the estimate", len(d.hosts), "| pool under ten in the reference year:", thin)
    suffix = "" if rules == ps.HEADLINE_RULES else f"_{rules.label}"
    pd.concat(tables, ignore_index=True).to_csv(FROZEN / f"design_support{suffix}.csv", index=False)
    if gaps:                                         # once for every set: the same unit and window is one row
        (pd.concat(gaps, ignore_index=True).drop_duplicates(["utility_id_eia", "state", "cohort"])
         .sort_values(["state", "utility_id_eia", "cohort"]).to_csv(FROZEN / f"full_window_eligibility{suffix}.csv", index=False))
    (FROZEN / f"design_support{suffix}.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
