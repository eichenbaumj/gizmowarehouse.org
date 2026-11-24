"""The influence checks' specification (D-58, rule 7), on quantities only. Synthetic data only."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, influence  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import COOP, FUEL, ladder, table, world  # noqa: E402


# Made-up 2008-2010 gas shares: the gas-share control is the default from step D (D-59 item 7). Tests about D-57's
# categorical cells name that control explicitly (CAT), as the labelled sensitivity it now is.
GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
CAT = ps.CATEGORICAL


def build(hosts, comps, region=None, **kw):
    treated, clean, q, regions, dd = world(hosts, comps, region=region)
    d = design.build(treated, clean, q, regions, FUEL, dd, **kw)
    d.gas = GAS
    return d


def two_regions(key, year):
    return "East" if key[0] >= 100 else "West"


def mixed_fuel_comps(first_id, n, start=10_050):
    """Comparison utilities alternating over the four states, so both fuel-mix groups and both states in each are present."""
    states = ["AA", "AB", "BB", "BC"]
    return [(first_id + i, states[i % 4], start + 100 * i, COOP) for i in range(n)]


# ---- leave_out -------------------------------------------------------------------------------------

def test_leave_out_removes_every_copy_across_hosts_and_keeps_the_rest_in_order():
    hosts = [(1, "AA", 10_000, COOP), (2, "AA", 10_500, COOP)]        # one region, so they share most of their matches
    d = build(hosts, ladder(10, 14))
    before = copy.deepcopy(d.hosts)
    shared = set(map(tuple, d.hosts.match_keys.iloc[0])) & set(map(tuple, d.hosts.match_keys.iloc[1]))
    gone = sorted(shared)[2]
    e = influence.leave_out(d, {gone})
    pd.testing.assert_frame_equal(d.hosts, before)                     # the input is not changed
    assert len(e.hosts) == len(d.hosts)                                 # hosts are never removed
    for i in range(2):
        old_keys, old_rows = list(d.hosts.match_keys.iloc[i]), list(d.hosts.matches.iloc[i])
        assert gone in old_keys and gone not in e.hosts.match_keys.iloc[i]
        assert list(e.hosts.match_keys.iloc[i]) == [k for k in old_keys if k != gone]
        assert list(e.hosts.matches.iloc[i]) == [r for r, k in zip(old_rows, old_keys) if k != gone]
    assert e.windows is d.windows


# ---- estimable ------------------------------------------------------------------------------------

def test_the_fit_is_not_estimable_when_the_only_hosts_remaining_matches_are_outside_its_fuel_mix_group():
    d = build([(1, "AA", 10_000, COOP)], mixed_fuel_comps(10, 16))
    full = influence.estimable(d, CAT)
    assert full["estimable"] and full["hosts_with_zero_weight"] == [] and full["hosts_with_no_matches"] == []
    own_group = {tuple(k) for k in d.hosts.match_keys.iloc[0] if FUEL[k[1]] == FUEL["AA"]}
    assert own_group and len(own_group) < 10
    e = influence.leave_out(d, own_group)
    r = influence.estimable(e, CAT)                                     # the host's event regressors are all absorbed (D-57)
    assert r["estimable"] is False
    assert 0.0 <= r["smallest_singular_value_ratio"] < influence.RANK_TOLERANCE
    assert np.isfinite(r["smallest_singular_value_ratio"]) and r["hosts_with_zero_weight"] == []


def test_a_host_with_no_matches_is_reported_and_does_not_crash_the_rank_test():
    hosts = [(1, "AA", 10_000, COOP), (101, "BB", 10_000, COOP)]
    d = build(hosts, mixed_fuel_comps(10, 12) + mixed_fuel_comps(110, 12), region=two_regions)
    e = influence.leave_out(d, set(map(tuple, d.hosts.match_keys.iloc[0])))
    r = influence.estimable(e)
    assert r["hosts_with_no_matches"] == ["1:AA"] and r["estimable"]
    alone = influence.leave_out(d, {tuple(k) for ks in d.hosts.match_keys for k in ks})
    r = influence.estimable(alone)
    assert r["hosts_with_no_matches"] == ["1:AA", "101:BB"] and r["estimable"] is False


# ---- deletions ------------------------------------------------------------------------------------

def zero_weight_design():
    """Host 1 (West, state AA) has one match in its fuel-mix group; host 101 (East, state BB) carries the fit (D-57's mechanism)."""
    west = [(10, "AB", 10_050, COOP)] + [(11 + i, "BB" if i % 2 else "BC", 10_100 + 100 * i, COOP) for i in range(11)]
    east = [(110 + i, "BB" if i % 2 else "BC", 10_050 + 100 * i, COOP) for i in range(12)]
    return build([(1, "AA", 10_000, COOP), (101, "BB", 10_000, COOP)], west + east, region=two_regions)


def test_removing_a_hosts_only_same_group_match_leaves_it_with_zero_weight():
    d = zero_weight_design()
    assert (10, "AB") in set(map(tuple, d.hosts.match_keys.iloc[0]))
    assert influence.estimable(d, CAT)["hosts_with_zero_weight"] == []
    out = influence.deletions(d, None, fuel_control=CAT)
    assert set(out.kind) == {"comparison"} and "omitted" in out.attrs["company_rows"]
    assert len(out) == len({tuple(k) for ks in d.hosts.match_keys for k in ks})
    row = out.set_index("removed").loc["10:AB"]
    assert row.estimable and row.hosts_with_zero_weight == ["1:AA"] and row.units_removed == 1
    assert row.net_weight_removed > 0.5                                 # it carried the offsetting weight for host 1
    others = out[out.removed != "10:AB"]
    assert all(z == [] for z in others.hosts_with_zero_weight) and others.estimable.all()


def test_a_deletion_leaving_a_host_four_matches_is_inadequate_support():
    d = build([(1, "AA", 10_000, COOP)], mixed_fuel_comps(10, 12), k=5)
    out = influence.deletions(d, None)
    assert len(out) == 5 and influence.INADEQUATE == 5
    assert all(h == ["1:AA"] for h in out.hosts_with_fewer_than_five_matches)
    assert all(h == [] for h in out.hosts_with_no_matches)


def test_company_rows_remove_every_unit_of_one_parent():
    d = build([(1, "AA", 10_000, COOP)], mixed_fuel_comps(10, 14))
    matched = [tuple(k) for k in d.hosts.match_keys.iloc[0]]
    firm = matched[:6]
    t = table([{"utility_id_eia": u, "state": s, "ultimate_parent": "Big Holding Co", "from_year": 2001, "to_year": 2025} for u, s in firm])
    own = {k: COOP for k in matched}
    out = influence.deletions(d, t, own)
    comp = out[out.kind == "company"].set_index("removed")
    assert set(comp.index) == {"Big Holding Co"} | {f"{u}:{s}" for u, s in matched[6:]}
    big = comp.loc["Big Holding Co"]
    assert big.units_removed == 6 and big.hosts_with_fewer_than_five_matches == ["1:AA"]
    assert big.investor_owned_units_with_no_row == []
    full = ic.net_weights(ic.implied_weights(d)).net_weight
    assert abs(big.net_weight_removed - sum(float(full[k]) for k in firm)) < 1e-12
    assert (out.kind == "comparison").sum() == 10 and "ownership table" in out.attrs["company_rows"]


# ---- main: rule 7's deletions on quantities only, before the freeze (step E) ---------------------------------------

import json  # noqa: E402

import pytest  # noqa: E402

from pipeline.analysis import ownership as own_mod  # noqa: E402
from pipeline.analysis import usable_flag  # noqa: E402


def run_main(monkeypatch, tmp_path, table_rows=()):
    from test_entry_points import GAS as EGAS, NONE, invented
    treated, clean, q, regions, dd, flags, dose = invented()
    path = tmp_path / "ownership.csv"
    t = pd.DataFrame([{c: "" for c in own_mod.COLUMNS} | r for r in table_rows], columns=own_mod.COLUMNS)
    t.to_csv(path, index=False)
    real_load = own_mod.load
    monkeypatch.setattr(own_mod, "load", lambda p=None: real_load(path))
    monkeypatch.setattr(design, "load", lambda: (q, dose, regions, FUEL, dd))
    monkeypatch.setattr(design, "split", lambda theta, which, q_, dose_, frozen=None: (treated, clean))
    monkeypatch.setattr(usable_flag, "read", lambda p=None: flags)
    monkeypatch.setattr(ps, "load_gas_share", lambda frozen=None: EGAS)
    monkeypatch.setattr(ps, "load_unknown_load", lambda *a, **k: NONE)
    monkeypatch.setattr(influence, "FROZEN", tmp_path)
    monkeypatch.setattr(ps.panel, "load_outcomes", lambda **k: pytest.fail("rule 7 before the freeze reads no outcome"))
    monkeypatch.setattr(ps, "read_listed_outcomes", lambda *a, **k: pytest.fail("rule 7 before the freeze reads no price"))
    assert influence.main() == 0
    return json.loads((tmp_path / "influence_on_quantities.json").read_text())


def test_main_runs_both_sets_on_quantities_only_and_writes_what_rule_7_asks(monkeypatch, tmp_path, capsys):
    src = {"source_url": "https://example.org", "source_kind": "sec_filing", "quote": "q", "date_opened": "2026-11-18",
           "name": "x", "how_it_changed": ""}
    rows = [{**src, "utility_id_eia": str(u), "state": "", "ultimate_parent": "Big Holding Co", "from_year": "2001", "to_year": "2025"}
            for u in (11, 12, 13)]
    r = run_main(monkeypatch, tmp_path, rows)
    assert set(r["sets"]) == {ps.HEADLINE_SET, ps.TEN_YEAR_SET}
    assert r["fuel_control"] == ps.GAS_SHARE and "no price" in r["what_this_is"].lower()
    s = r["sets"][ps.HEADLINE_SET]
    assert s["deletions"]["comparison"] > 0 and s["deletions"]["company"] > 0 and s["full_design_estimable"] is True
    for key in ("leave_a_host_with_fewer_than_five_matches", "leave_a_host_with_no_matches", "leave_a_host_with_zero_weight",
                "make_the_fit_not_estimable"):
        assert isinstance(s[key], list)
    top = s["ten_deletions_removing_the_most_net_weight"]
    assert 0 < len(top) <= 10 and [x["net_weight_removed"] for x in top] == sorted((x["net_weight_removed"] for x in top), reverse=True)
    big = s["largest_net_weight_removed_by_one_company"]
    assert set(big) == {"company", "net_weight_removed", "units", "investor_owned_units_with_no_row"} and big["net_weight_removed"] >= 0
    assert len(s["fingerprint"]["sha256"]) == 64
    out = capsys.readouterr().out.strip().split("\n")
    assert len(out) == 2 and all("deletions" in line and "largest net weight removed" in line for line in out)


def test_summary_names_every_deletion_that_leaves_a_host_short_absorbed_or_the_fit_not_estimable():
    out = pd.DataFrame([
        {"kind": "comparison", "removed": "10:AA", "units": ["10:AA"], "units_removed": 1, "net_weight_removed": 0.30,
         "hosts_with_fewer_than_five_matches": ["1:AA"], "hosts_with_no_matches": [], "hosts_with_zero_weight": [], "estimable": True,
         "investor_owned_units_with_no_row": []},
        {"kind": "company", "removed": "Big Co", "units": ["11:AA", "12:AA"], "units_removed": 2, "net_weight_removed": 0.55,
         "hosts_with_fewer_than_five_matches": [], "hosts_with_no_matches": ["2:BB"], "hosts_with_zero_weight": ["3:AB"], "estimable": False,
         "investor_owned_units_with_no_row": ["12:AA"]},
        {"kind": "company", "removed": "13:AA", "units": ["13:AA"], "units_removed": 1, "net_weight_removed": 0.05,
         "hosts_with_fewer_than_five_matches": [], "hosts_with_no_matches": [], "hosts_with_zero_weight": [], "estimable": True,
         "investor_owned_units_with_no_row": []}])
    out.attrs["full_design"] = {"estimable": True}
    out.attrs["company_rows"] = "computed from the ownership table"
    s = influence.summarise(out)
    assert s["deletions"] == {"comparison": 1, "company": 2}
    assert [x["removed"] for x in s["leave_a_host_with_fewer_than_five_matches"]] == ["10:AA"]
    assert s["leave_a_host_with_no_matches"] == [{"kind": "company", "removed": "Big Co", "hosts": ["2:BB"]}]
    assert s["leave_a_host_with_zero_weight"] == [{"kind": "company", "removed": "Big Co", "hosts": ["3:AB"]}]
    assert s["make_the_fit_not_estimable"] == [{"kind": "company", "removed": "Big Co"}]
    assert [x["removed"] for x in s["ten_deletions_removing_the_most_net_weight"]] == ["Big Co", "10:AA", "13:AA"]
    assert s["largest_net_weight_removed_by_one_company"] == {"company": "Big Co", "net_weight_removed": 0.55, "units": ["11:AA", "12:AA"],
                                                              "investor_owned_units_with_no_row": ["12:AA"]}
    out.attrs["full_design"] = {"estimable": False}
    out["net_weight_removed"] = float("nan")
    s = influence.summarise(out)
    assert s["ten_deletions_removing_the_most_net_weight"] == [] and s["largest_net_weight_removed_by_one_company"] is None
    assert "not estimable" in s["net_weight_note"]


def test_the_module_never_reads_an_outcome():
    src = Path(influence.__file__).read_text()
    assert "load_outcomes" not in src and "read_listed_outcomes" not in src and "read_parquet" not in src
