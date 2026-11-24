#!/usr/bin/env python3
"""The joint check: how many comparison utilities could fail the 0.5% rule within one state's remainder.

Touches NO price data. Rules: D-46's ruling 5 as amended in its two addenda
(docs/DECISIONS.md), written before this was run. It describes a limit. It moves
no utility in or out of any set, it does not pick an allocation of any state's
remainder, and it takes the unanchored inventory's assignments as they stand:
it does not also search over the assignment alternatives of ruling 4, so a
utility that passes ruling 4 can still be nearer to 0.5% under another
assignment than this assumes.

For comparison utility i in year t the hidden load that would put it at 0.5% is
    d(i,t) = 0.005 x its 2009-2011 sales - the unanchored inventory's load on it that year   (zero if negative)
The state's budget is its 2024 remainder as D-44 defines it. Hidden load cannot
be negative, cannot exceed the utility's non-residential sales less the
inventory's load in any year, and does not shrink (D-44's assumption). So load
put on a utility in year t has to fit under its sales bound in every year from
t through 2024, and it still counts against the 2024 budget. Years through 2024
only: the 2024 remainder sets no budget for 2025.

Two counts, which are different worst cases:

  somewhere in the period   the largest number of comparison utilities that could EACH fail the
                            0.5% rule in some year of the period, under one feasible spread of
                            hidden load. Each utility's cost is its smallest feasible d(i,t);
                            the costs are sorted and taken from the smallest until the budget
                            is spent. Their cheapest years can be different years.
  in the same year          for each calendar year, the largest number that could be at 0.5% or
                            more in that year: the costs are d(i,t) for that year alone. The
                            largest across years is reported with its year.

That the sort gives the true maximum is tested against a search over every
subset on small made-up states (tests/test_joint_check.py), for both counts.

What neither count can say. The largest number is not the expected number. The
smallest is zero: the remainder may be outside the panel or may be error in the
state total, and none of it is forced onto panel utilities. A utility over 0.5%
fails the eligibility rule; that is not the same as biasing the estimate.

Run:  python3 -I pipeline/facilities/joint_check.py     (after treatment_bounds.py)
Output: data/frozen/joint_check.json, joint_check_by_state.csv, joint_check_by_host.csv
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
KEY = ["utility_id_eia", "state"]
SHARE = 0.005
LAST = 2024                    # the remainder is a 2024 figure and sets no budget for 2025
EPS = 1e-9
TARGETS = (5, 6, 10)           # of a host's ten matches: six leaves fewer than five clean


def deficits(load_gwh: pd.DataFrame, base_gwh: pd.Series, share: float = SHARE) -> pd.DataFrame:
    """d(i,t): the hidden load that would put utility i at `share` of its base in year t. NaN where there is no base."""
    need = share * base_gwh.reindex(load_gwh.index)
    d = (-load_gwh).add(need, axis=0).clip(lower=0.0)
    d.loc[need.isna().values] = np.nan
    return d


def fits(d: pd.DataFrame, room_gwh: pd.DataFrame) -> pd.DataFrame:
    """True where d(i,t) fits under the utility's sales bound in t and in every later year (hidden load does not shrink).

    `room_gwh` is non-residential sales less the inventory's load, by utility and year; a year with no sales
    reported bounds nothing. Both frames cover the same years, the last being the budget's year.
    """
    room = room_gwh.reindex(index=d.index, columns=d.columns).clip(lower=0.0).fillna(np.inf).values
    tightest_from_t = np.minimum.accumulate(room[:, ::-1], axis=1)[:, ::-1]
    return pd.DataFrame(d.values <= tightest_from_t + EPS, index=d.index, columns=d.columns) & d.notna()


def cost_somewhere(d: pd.DataFrame, ok: pd.DataFrame, years=None) -> pd.Series:
    """Each utility's cheapest feasible way to fail the rule in some year of `years`. inf if no year fits."""
    cols = list(d.columns) if years is None else [y for y in years if y in d.columns]
    if not cols:
        return pd.Series(np.inf, index=d.index)
    return d[cols].where(ok[cols]).min(axis=1).fillna(np.inf)


def most(costs, budget: float) -> int:
    """How many of `costs` can be met within `budget`, cheapest first."""
    c = np.sort(np.asarray([x for x in costs if np.isfinite(x)], dtype=float))
    return int(np.searchsorted(np.cumsum(c), budget + EPS, side="right"))


def smallest_to_reach(costs, n: int) -> float:
    """The smallest total that meets `n` of `costs`. inf if fewer than n can be met at any price."""
    c = np.sort(np.asarray([x for x in costs if np.isfinite(x)], dtype=float))
    return float(c[:n].sum()) if n <= len(c) and n > 0 else (0.0 if n <= 0 else math.inf)


def same_year(d: pd.DataFrame, ok: pd.DataFrame, budget: float, years=None) -> tuple[int, int | None, dict]:
    """(largest number at the rule's level in one year, that year, the count for every year)."""
    cols = list(d.columns) if years is None else [y for y in years if y in d.columns]
    by_year = {int(y): most(d[y].where(ok[y]).fillna(np.inf).values, budget) for y in cols}
    if not by_year:
        return 0, None, {}
    best = max(by_year, key=lambda y: (by_year[y], -y))
    return by_year[best], best, by_year


def host_check(match_keys: list, window: list[int], d: pd.DataFrame, ok: pd.DataFrame, budget_by_state: dict) -> dict:
    """One host: how many of its matched comparison utilities could be reached, within the remainders and ignoring them."""
    years = [y for y in window if y <= LAST]
    partly = any(y > LAST for y in window)
    keys = [k for k in match_keys if k in d.index]
    cost = cost_somewhere(d.loc[keys], ok.loc[keys], years) if keys else pd.Series(dtype=float)
    states = sorted({k[1] for k in keys})
    by_state, reached, ladder = {}, 0, {}
    for st in states:
        mine = [k for k in keys if k[1] == st]
        c = np.sort(cost.loc[mine].values)
        n = most(c, budget_by_state.get(st, 0.0))
        reached += n
        fin = c[np.isfinite(c)]
        ladder[st] = {"matches_in_this_state": len(mine), "state_remainder_gwh": round(float(budget_by_state.get(st, 0.0)), 1),
                      "reachable_within_its_remainder": n,
                      "hidden_gwh_to_reach_its_cheapest_1_2_3_and_so_on": [round(float(x), 2) for x in np.cumsum(fin)],
                      "cannot_be_reached_in_this_window": int(len(c) - len(fin))}
        by_state[st] = n
    # In one year: every state's budget spent on this host's matches in that year.
    best_n, best_y = 0, None
    for y in years:
        n = sum(most(d.loc[[k for k in keys if k[1] == st], y].where(ok.loc[[k for k in keys if k[1] == st], y]).fillna(np.inf).values,
                     budget_by_state.get(st, 0.0)) for st in states)
        if n > best_n:
            best_n, best_y = n, y
    tipping = {}
    order = cost[np.isfinite(cost)].sort_values(kind="stable")
    for n in TARGETS:
        if n > len(order):
            tipping[str(n)] = {"total_gwh": None, "note": "fewer than this many can be reached in this window at any size of remainder"}
            continue
        take = order.iloc[:n]
        per_state = take.groupby([k[1] for k in take.index]).sum()
        tipping[str(n)] = {"total_gwh": round(float(take.sum()), 2),
                           "one_combination_by_state_gwh": {st: round(float(v), 2) for st, v in per_state.items()},
                           "within_the_remainders": "feasible" if reached >= n else "not feasible"}
    return {"matched": len(match_keys), "matched_with_a_base": len(keys), "window": [int(window[0]), int(window[-1])],
            "years_assessed": [int(years[0]), int(years[-1])] if years else None, "partly_assessed_2025_left_out": bool(partly),
            "could_fail_somewhere_in_its_window_within_the_remainders": int(reached),
            "could_be_at_the_level_in_one_year_within_the_remainders": int(best_n), "that_year": best_y,
            "clean_left_in_the_worst_case": int(len(match_keys) - reached),
            "by_state": ladder, "tipping_requirement_ignoring_the_remainders": tipping}


def state_check(keys: list, d: pd.DataFrame, ok: pd.DataFrame, budget: float, floor: set, total_twh: float | None) -> dict:
    """One state: the counts for all its eligible comparison utilities and for those above the customer floor."""
    out = {"state_remainder_gwh": round(float(budget), 1), "state_total_twh": None if total_twh is None else round(float(total_twh), 3)}
    for label, ks in (("all", keys), ("above_the_customer_floor", [k for k in keys if k in floor])):
        have = [k for k in ks if k in d.index and d.loc[k].notna().any()]
        cost = cost_somewhere(d.loc[have], ok.loc[have]) if have else pd.Series(dtype=float)
        n_same, y_same, _ = same_year(d.loc[have], ok.loc[have], budget) if have else (0, None, {})
        fin = int(np.isfinite(cost).sum()) if len(cost) else 0
        size = {}
        for name, n in (("one", 1), ("a_tenth", math.ceil(len(have) / 10)), ("half", math.ceil(len(have) / 2)), ("all", len(have))):
            g = smallest_to_reach(cost.values, n) if len(have) else math.inf
            size[name] = {"utilities": int(n), "hidden_gwh": None if not np.isfinite(g) else round(g, 2),
                          "share_of_the_state_total": None if not np.isfinite(g) or not total_twh else round(g / (total_twh * 1000.0), 4)}
        out[label] = {"eligible_comparison_utilities": len(ks), "with_no_2009_2011_sales_to_divide_by_left_out": len(ks) - len(have),
                      "could_fail_one_at_a_time": int((cost <= budget + EPS).sum()) if len(cost) else 0,
                      "could_each_fail_somewhere_in_the_period_under_one_spread": most(cost.values, budget) if len(cost) else 0,
                      "could_be_at_the_level_in_the_same_year": int(n_same), "that_year": y_same,
                      "can_be_reached_at_any_size_of_remainder": fin,
                      "smallest_hidden_load_that_would_reach": size}
    return out


def headline_design(treated, clean, qq, reg_t, fuel, dd, rules=None, ownership=None, usable=None, gas=None,
                    ownership_of=None, unknown_load=None, theta: float = 0.02):
    """The design the by-host check reads: design.build_with_rules under the headline rules (rule 6.4: the same
    eligibility as the design). Inputs not given are loaded from their committed sources by power_simulation.rule_inputs
    (the ownership table, the quantities file's usable flag, the frozen gas shares), as design.main loads them, and the
    unknown-load gate (power_simulation.load_unknown_load(), D-96): a utility whose place the frame cannot settle is
    neither a host nor a match here either."""
    from pipeline.analysis import design
    from pipeline.analysis import power_simulation as ps
    rules = rules or ps.HEADLINE_RULES
    ownership, usable, gas = ps.rule_inputs(rules, qq, ownership=ownership, usable=usable, gas=gas)
    ownership_of = ownership_of if ownership_of is not None else ps.ownership_classes(qq)
    unknown_load = unknown_load if unknown_load is not None else ps.load_unknown_load()
    return design.build_with_rules(treated, clean, qq, reg_t, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                                   ownership_of=ownership_of, unknown_load=unknown_load, theta=theta)


def host_results(dsg, d: pd.DataFrame, ok: pd.DataFrame, budget: dict, names) -> tuple[dict, list]:
    """Each host's check over its matched comparisons, as the design (built under the rules) matched them."""
    from pipeline.analysis import power_simulation as ps
    hosts, host_rows = {}, []
    for h in dsg.hosts.itertuples():
        window = list(range(h.cohort - ps.PRE, h.cohort + ps.POST + 1))
        r = host_check(list(h.match_keys), window, d, ok, budget)
        r["name"], r["cohort"], r["region"] = names.get(h.key), int(h.cohort), h.region
        hosts[f"{h.key[0]}:{h.key[1]}"] = r
        tip = r["tipping_requirement_ignoring_the_remainders"]
        host_rows.append({"utility": f"{h.key[0]}:{h.key[1]}", "name": r["name"], "cohort": r["cohort"], "region": r["region"],
                          "matched": r["matched"], "states_of_its_matches": ";".join(sorted(r["by_state"])),
                          "could_fail_somewhere_in_its_window": r["could_fail_somewhere_in_its_window_within_the_remainders"],
                          "could_be_at_the_level_in_one_year": r["could_be_at_the_level_in_one_year_within_the_remainders"],
                          "clean_left_in_the_worst_case": r["clean_left_in_the_worst_case"], "partly_assessed": r["partly_assessed_2025_left_out"],
                          **{f"tipping_gwh_to_reach_{n}": tip[str(n)]["total_gwh"] for n in TARGETS},
                          **{f"reach_{n}_within_the_remainders": tip[str(n)].get("within_the_remainders", "not feasible") for n in TARGETS}})
    return hosts, host_rows


def main() -> int:
    from pipeline.analysis import design
    from pipeline.analysis import power_simulation as ps
    from pipeline.facilities import assignment, treatment_bounds as tb

    fac, fy, q, units, base, regions = assignment.load_inputs()
    names = q.groupby(KEY).utility_name.last()
    years = [y for y in assignment.YEARS if y <= LAST]
    scale = fac.state_scale
    a = tb.matrix(fy.assign(mw=fy.mw / fy.fid.map(scale).fillna(1.0)), units)[years]      # the unanchored inventory, as assigned
    nonres = (q.assign(v=q.nonres_mwh.fillna(q.total_retail_mwh) / 1000.0)
              .pivot_table(index=KEY, columns="year", values="v").reindex(index=units, columns=years))
    d = deficits(a, base)
    ok = fits(d, nonres - a)
    states = tb.state_remainders(pd.read_parquet(INTERIM / "state_anchor.parquet"))
    budget = (states.remainder_twh * 1000.0).to_dict()
    floor = set(map(tuple, q[q.meets_size_floor][KEY].drop_duplicates().values))

    theta = 0.02
    qq, dose, reg_t, fuel, dd = design.load()
    treated, clean = design.split(theta, ps.HEADLINE_SET, qq, dose)
    eligible = list(map(tuple, clean.values))
    by_state: dict[str, list] = {}
    for k in eligible:
        by_state.setdefault(k[1], []).append(k)

    report = {
        "what_this_is": "D-46, ruling 5 as amended. Within each state's 2024 remainder, the largest number of eligible comparison "
                        "utilities that could fail the 0.5% rule. A description of a limit: it moves no one in or out of any set.",
        "read_this_first": [
            "It takes the unanchored inventory's assignments as they stand and does not search over the assignment alternatives of ruling 4.",
            "'Somewhere in the period' is the number that could each fail in some year under one feasible spread of hidden load that does "
            "not shrink; their years can differ. 'In the same year' is the number that could be at 0.5% or more in one calendar year.",
            "The largest number is not the expected number. The smallest is zero: the remainder may be outside the panel (ERCOT's wires "
            "companies, behind-the-meter and wholesale-direct sites) or may be error in the state total.",
            "Failing the 0.5% rule is not the same as biasing the estimate: hidden load that was steady through a window need not move prices differently.",
            "The state total is itself an estimate (D-2), so the remainder is too. The sales bound is an inference from quantities.",
            "Host figures are each host's own worst case, with every state's remainder spent on that host's matches first. Hosts that share a "
            "state cannot all be at their worst together: 'hosts individually vulnerable; the scenarios need not coexist'.",
        ],
        "eligible_comparison_utilities": len(eligible), "above_the_customer_floor": int(sum(k in floor for k in eligible)),
        "period": [years[0], years[-1]], "states": {}, "hosts": {},
    }
    rows = []
    for st in sorted(by_state):
        total = float(states.epri_twh[st]) if st in states.index else None
        r = state_check(by_state[st], d, ok, budget.get(st, 0.0), floor, total)
        r["kind"] = states.kind[st] if st in states.index else "no_state_total"
        report["states"][st] = r
        for label in ("all", "above_the_customer_floor"):
            x = r[label]
            rows.append({"state": st, "kind": r["kind"], "state_remainder_gwh": r["state_remainder_gwh"], "state_total_twh": r["state_total_twh"],
                         "population": label, **{k: v for k, v in x.items() if not isinstance(v, dict)},
                         **{f"smallest_gwh_to_reach_{k}": v["hidden_gwh"] for k, v in x["smallest_hidden_load_that_would_reach"].items()},
                         **{f"share_of_state_total_to_reach_{k}": v["share_of_the_state_total"] for k, v in x["smallest_hidden_load_that_would_reach"].items()}})
    short = [st for st, r in report["states"].items() if r["kind"] == "falls_short"]
    tot = {}
    for label in ("all", "above_the_customer_floor"):
        # The same-year national figure needs one calendar year across states: recompute by year and add.
        per_year = {y: 0 for y in years}
        for st in short:
            ks = [k for k in by_state[st] if (label == "all" or k in floor) and k in d.index and d.loc[k].notna().any()]
            if ks:
                for y, n in same_year(d.loc[ks], ok.loc[ks], budget.get(st, 0.0))[2].items():
                    per_year[y] += n
        best = max(per_year, key=lambda y: (per_year[y], -y))
        tot[label] = {
            "eligible_comparison_utilities_everywhere": int(sum(report["states"][st][label]["eligible_comparison_utilities"] for st in report["states"])),
            "in_states_that_fall_short": int(sum(report["states"][st][label]["eligible_comparison_utilities"] for st in short)),
            "could_fail_one_at_a_time": int(sum(report["states"][st][label]["could_fail_one_at_a_time"] for st in short)),
            "could_each_fail_somewhere_in_the_period_under_one_spread": int(sum(report["states"][st][label]["could_each_fail_somewhere_in_the_period_under_one_spread"] for st in short)),
            "could_be_at_the_level_in_the_same_year": int(per_year[best]), "that_year": int(best)}
    report["totals_in_states_that_fall_short"] = tot

    # Rule 6.4: the joint check by host runs on the same eligibility as the design (step D: design.build_with_rules with
    # the headline rules: the ownership table, the usable flag, the support rule). The by-state part is unchanged.
    dsg = headline_design(treated, clean, qq, reg_t, fuel, dd)
    report["hosts"], host_rows = host_results(dsg, d, ok, budget, names)
    report["design_rules"] = getattr(getattr(dsg, "rules", None), "label", None)
    hr = pd.DataFrame(host_rows)
    report["hosts_individually_vulnerable_the_scenarios_need_not_coexist"] = {
        "hosts": int(len(hr)),
        "could_be_left_with_fewer_than_five_clean_of_ten": int((hr.clean_left_in_the_worst_case < 5).sum()) if len(hr) else 0,
        "could_be_left_with_none_clean": int((hr.clean_left_in_the_worst_case <= 0).sum()) if len(hr) else 0,
        "names_fewer_than_five": hr[hr.clean_left_in_the_worst_case < 5].name.tolist() if len(hr) else [],
        "names_none": hr[hr.clean_left_in_the_worst_case <= 0].name.tolist() if len(hr) else []}
    (FROZEN / "joint_check.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    pd.DataFrame(rows).to_csv(FROZEN / "joint_check_by_state.csv", index=False)
    hr.to_csv(FROZEN / "joint_check_by_host.csv", index=False)
    print(json.dumps({"totals": tot, "hosts": report["hosts_individually_vulnerable_the_scenarios_need_not_coexist"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
