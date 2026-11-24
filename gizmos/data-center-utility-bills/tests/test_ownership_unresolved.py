"""Hosts whose ownership is unresolved, the step F sensitivity that excludes them, and the table as it stands at Stop 3.

The owner's ruling of 2026-11-18 (Stop 3): retain the affected hosts with the limitation recorded, adopt the step F
sensitivity excluding all hosts with unresolved ownership, "defined consistently now", never describe their
investor-owned matches as verified unaffiliated, and never switch them to public or cooperative matches.

The definition implemented (put to the owner with this change): an investor-owned host's ownership is UNRESOLVED if, for
any year of its event window (cohort year g minus 6 through g plus 3), no row of the ownership table covers that year, or a
row covering it has both from_year_basis and to_year_basis "assumed". Public and cooperative hosts are never unresolved.

Invented tables only, except the tests on the shipped table, which read pipeline/analysis/ownership.csv (no price).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, ownership  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import COHORT, COOP, FUEL, IOU, PUBLIC, WINDOW, YEARS, keys_of, ladder, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
NONE = ps.UnknownLoad.none("invented data: no load-unknown site")
D, A = "documented", "assumed"


def rows(*specs):
    """specs: (id, state, parent, from, to, from_basis, to_basis) -> an ownership table as ownership.load returns it."""
    base = {"name": "x", "how_it_changed": "", "source_url": "https://example.org", "source_kind": "sec_filing", "quote": "q",
            "date_opened": "2026-11-18"}
    t = pd.DataFrame([{**base, "utility_id_eia": u, "state": st, "ultimate_parent": p, "from_year": lo, "to_year": hi,
                       "from_year_basis": fb, "to_year_basis": tb} for u, st, p, lo, hi, fb, tb in specs],
                     columns=ownership.COLUMNS + list(ownership.BASIS))
    return t.astype({"utility_id_eia": int, "from_year": int, "to_year": int})


HOST = (1, "AA")
OWN = {HOST: IOU}


def unresolved(t, own=OWN, hosts=((HOST, COHORT),)):
    return ownership.unresolved_ownership_hosts(t, list(hosts), own)


# ---- the definition, on invented tables -------------------------------------------------------------------------

def test_the_window_is_the_event_window_of_the_simulation_and_the_design():
    assert (ownership.WINDOW_BEFORE, ownership.WINDOW_AFTER) == (ps.PRE, ps.POST)
    assert ownership.window_years(COHORT) == WINDOW


def test_an_investor_owned_host_with_no_row_is_unresolved_in_every_window_year():
    got = unresolved(rows())
    assert set(got) == {HOST}
    x = got[HOST]
    assert x["cohort"] == COHORT and x["years"] == WINDOW
    assert set(x["reason_by_year"].values()) == {ownership.UNRESOLVED_NO_ROW}
    assert x["utility"] == "1:AA" and "no row" in x["reason"]


def test_a_row_assumed_at_both_ends_leaves_the_host_unresolved():
    got = unresolved(rows((1, "", "P", 2001, 2025, A, A)))
    assert got[HOST]["years"] == WINDOW
    assert set(got[HOST]["reason_by_year"].values()) == {ownership.UNRESOLVED_ASSUMED}


@pytest.mark.parametrize("fb, tb", [(D, A), (A, D), (D, D)])
def test_a_row_documented_at_one_end_or_both_resolves_the_years_it_covers(fb, tb):
    assert unresolved(rows((1, "", "P", 2001, 2025, fb, tb))) == {}


def test_a_window_straddling_two_spells_is_unresolved_only_in_the_years_of_the_spell_assumed_at_both_ends():
    # 2009-2012 under a spell documented at its end; 2013-2018 only under a spell assumed at both ends. 2012 is the year
    # the sale closes (rule 2.1: both parents count), covered by both rows; a row covering it is assumed at both ends.
    t = rows((1, "", "P", 2001, 2012, A, D), (1, "", "Q", 2012, 2025, A, A))
    got = unresolved(t)
    assert got[HOST]["years"] == list(range(2012, 2019))
    assert set(got[HOST]["reason_by_year"].values()) == {ownership.UNRESOLVED_ASSUMED}


def test_a_gap_between_spells_is_unresolved_for_want_of_a_row():
    t = rows((1, "", "P", 2001, 2011, D, D), (1, "", "Q", 2014, 2025, D, D))
    got = unresolved(t)
    assert got[HOST]["years"] == [2012, 2013]
    assert set(got[HOST]["reason_by_year"].values()) == {ownership.UNRESOLVED_NO_ROW}


def test_a_row_for_another_state_of_the_id_does_not_cover_the_host_but_a_blank_state_does():
    assert set(unresolved(rows((1, "BB", "P", 2001, 2025, D, D)))) == {HOST}
    assert unresolved(rows((1, "AA", "P", 2001, 2025, D, D))) == {}
    assert unresolved(rows((1, "", "P", 2001, 2025, D, D))) == {}


@pytest.mark.parametrize("cls", [PUBLIC, COOP])
def test_a_public_or_cooperative_host_with_no_row_is_never_unresolved(cls):
    """Rule 2.2: municipal systems, public power districts and distribution cooperatives with no row are their own owners."""
    assert unresolved(rows(), own={HOST: cls}) == {}
    assert unresolved(rows((1, "", "P", 2001, 2025, A, A)), own={HOST: cls}) == {}


def test_an_unknown_ownership_class_fails_loudly():
    with pytest.raises(ValueError, match="no ownership class"):
        unresolved(rows(), own={})


def test_a_table_without_basis_columns_shows_no_row_documented_and_a_bad_basis_stops_in_words():
    t = rows((1, "", "P", 2001, 2025, D, D)).drop(columns=list(ownership.BASIS))
    assert set(unresolved(t)[HOST]["reason_by_year"].values()) == {ownership.UNRESOLVED_NO_BASIS}
    bad = rows((1, "", "P", 2001, 2025, "probably", D))
    with pytest.raises(ValueError, match="basis"):
        unresolved(bad)
    assert set(unresolved(rows().drop(columns=list(ownership.BASIS)))) == {HOST}   # no covering row: no basis needed


def test_several_hosts_each_get_their_own_window():
    t = rows((1, "", "P", 2001, 2012, D, D), (3, "", "P", 2001, 2012, D, D))
    own = {(1, "AA"): IOU, (2, "AA"): IOU, (3, "AA"): IOU}
    got = ownership.unresolved_ownership_hosts(t, [((1, "AA"), 2008), ((2, "AA"), 2008), ((3, "AA"), 2015)], own)
    assert set(got) == {(2, "AA"), (3, "AA")}           # 2002-2011 is covered for unit 1; unit 2 has no row
    assert got[(3, "AA")]["cohort"] == 2015 and got[(3, "AA")]["years"] == list(range(2013, 2019))
    with pytest.raises(ValueError, match="twice"):
        ownership.unresolved_ownership_hosts(t, [((1, "AA"), 2008), ((1, "AA"), 2015)], own)


def test_load_keeps_and_checks_the_basis_columns(tmp_path):
    good = {"utility_id_eia": "7", "state": "", "name": "x", "ultimate_parent": "P", "from_year": "2001", "to_year": "2025",
            "how_it_changed": "", "source_url": "https://example.org", "source_kind": "company_page", "quote": "q",
            "date_opened": "2026-11-18", "from_year_basis": "assumed", "to_year_basis": "documented"}
    path = tmp_path / "ownership.csv"
    pd.DataFrame([good]).to_csv(path, index=False)
    t = ownership.load(path)
    assert list(t.columns) == ownership.COLUMNS + list(ownership.BASIS)
    assert (t.from_year_basis.iloc[0], t.to_year_basis.iloc[0]) == ("assumed", "documented")
    pd.DataFrame([{**good, "to_year_basis": "probably"}]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="row 2 .*to_year_basis"):
        ownership.load(path)


# ---- the rules: the headline keeps such a host and states the limitation; the sensitivity drops it -----------

def usable_for(units):
    return {(u, st, y) for u, st, *_ in units for y in YEARS}


def two_host_world():
    """Host 1 (investor-owned, row assumed at both ends) and host 2 (investor-owned, documented). Comparisons: investor-
    owned units with documented rows of their own parents, and public units nearer in size than some of them."""
    hosts = [(1, "AA", 10_000, IOU), (2, "AA", 10_000, IOU)]
    comps = ladder(30, 6, own=IOU) + ladder(50, 8, own=PUBLIC, start=10_075)
    treated, clean, q, regions, dd = world(hosts, comps)
    t = rows((1, "", "P1", 2001, 2025, A, A), (2, "", "P2", 2001, 2025, D, A),
             *[(30 + i, "", f"O{i}", 2001, 2025, D, D) for i in range(6)])
    return treated, clean, q, regions, dd, t, usable_for(hosts + comps)


def build(rules, world_):
    treated, clean, q, regions, dd, t, usable = world_
    return design.build_with_rules(treated, clean, q, regions, FUEL, dd, rules, ownership=t, usable=usable, gas=GAS, unknown_load=NONE)


def test_the_sensitivity_is_a_labelled_variant_that_changes_nothing_else():
    s = ps.UNRESOLVED_OWNERSHIP_EXCLUDED
    assert s.label == "sensitivity_hosts_with_unresolved_ownership_excluded" and ps.RULE_VARIANTS[s.label] is s
    assert s.unresolved_ownership == "hosts_excluded" and ps.HEADLINE_RULES.unresolved_ownership == "kept"
    h = ps.HEADLINE_RULES
    assert (s.ownership, s.usable, s.support, s.fuel_control) == (h.ownership, h.usable, h.support, h.fuel_control)
    assert ps.rules_from_argv(["--rules=sensitivity_hosts_with_unresolved_ownership_excluded"]) is s
    with pytest.raises(ValueError, match="unresolved"):
        ps.Rules("bad", unresolved_ownership="rematched")
    with pytest.raises(ValueError, match="ownership table"):
        ps.Rules("bad", ownership="off", unresolved_ownership="hosts_excluded")


def test_the_headline_keeps_a_host_with_unresolved_ownership_and_lists_it_as_a_limitation():
    d = build(ps.HEADLINE_RULES, two_host_world())
    assert [tuple(k) for k in d.hosts.key] == [(1, "AA"), (2, "AA")]
    assert [x["utility"] for x in d.unresolved_ownership] == ["1:AA"]
    assert d.unresolved_ownership[0]["in_this_run"] == "kept"


def test_the_sensitivity_drops_only_those_hosts_and_leaves_every_other_match_as_it_was():
    w = two_host_world()
    head, sens = build(ps.HEADLINE_RULES, w), build(ps.UNRESOLVED_OWNERSHIP_EXCLUDED, w)
    assert [tuple(k) for k in sens.hosts.key] == [(2, "AA")]
    assert keys_of(sens, 0) == keys_of(head, 1)                        # the remaining host's matches are unchanged
    assert sens.hosts.excluded_from_its_pool.iloc[0] == head.hosts.excluded_from_its_pool.iloc[1]
    named = [x for x in sens.dropped if x["utility"] == "1:AA"]
    assert len(named) == 1 and named[0]["why"].startswith(ownership.UNRESOLVED_EXCLUDED)
    assert sens.unresolved_ownership[0]["in_this_run"] == "excluded"


def test_no_rematching_to_public_or_cooperative_units_for_an_unresolved_host():
    """The headline matches an unresolved investor-owned host exactly as the table gives (ruling: do not switch them)."""
    w = two_host_world()
    treated, clean, q, regions, dd, t, usable = w
    d = build(ps.HEADLINE_RULES, w)
    plain = design.build(treated, clean, q, regions, FUEL, dd, ownership=t, usable=usable)
    assert keys_of(d, 0) == keys_of(plain, 0)
    assert any(k[0] in range(30, 36) for k in keys_of(d, 0))           # it keeps investor-owned matches


def test_design_main_states_the_limitation_and_never_calls_the_matches_verified(monkeypatch, tmp_path):
    from test_entry_points import invented
    import json
    from pipeline.analysis import usable_flag
    treated, clean, q, regions, dd, flags, dose = invented()
    path = tmp_path / "ownership.csv"                                  # a header: host 1 (investor-owned) has no row
    path.write_text(",".join(ownership.COLUMNS + list(ownership.BASIS)) + "\n")
    real_load = ownership.load
    monkeypatch.setattr(ownership, "load", lambda p=None: real_load(path))
    monkeypatch.setattr(design, "load", lambda: (q, dose, regions, FUEL, dd))
    monkeypatch.setattr(design, "split", lambda theta, which, q_, dose_, frozen=None: (treated, clean))
    monkeypatch.setattr(design, "SETS", (ps.HEADLINE_SET,))
    monkeypatch.setattr(usable_flag, "read", lambda p=None: flags)
    monkeypatch.setattr(ps, "load_gas_share", lambda frozen=None: GAS)
    monkeypatch.setattr(ps, "load_unknown_load", lambda *a, **k: NONE)
    monkeypatch.setattr(design, "FROZEN", tmp_path)
    monkeypatch.setattr(sys, "argv", ["design.py"])
    assert design.main() == 0
    r = json.loads((tmp_path / "design_support.json").read_text())
    entry = r["sets"][ps.HEADLINE_SET]["hosts_with_unresolved_ownership"]
    assert "not shown to be unaffiliated" in entry["limitation"] and "kept" in entry["limitation"]
    assert [(h["utility"], h["name"], h["in_this_run"]) for h in entry["hosts"]] == [("1:AA", "Utility 1", "kept")]
    assert "1:AA" in [h["utility"] for h in r["sets"][ps.HEADLINE_SET]["hosts"]]
    assert r["rules"]["unresolved_ownership"] == "kept"
    text = json.dumps(r).lower()
    assert "verified unaffiliated" not in text and "verified as unaffiliated" not in text
    import re
    for m in re.finditer(r"shown to be unaffiliated", text):          # only ever in the negative ("not", "cannot be")
        assert re.search(r"(not|cannot be|never)\s*$", text[max(0, m.start() - 12):m.start()]), text[m.start() - 40:m.end()]


# ---- the shipped table at Stop 3 (2026-11-18) ----------------------------------------------------------------------

LEADS = Path(__file__).resolve().parents[1] / "pipeline" / "analysis" / "leads"


def test_the_shipped_table_loads_with_its_basis_columns_and_its_stop_3_counts():
    t = ownership.load()
    assert list(t.columns) == ownership.COLUMNS + list(ownership.BASIS)
    assert len(t) == 104 and t.utility_id_eia.nunique() == 88
    both = ((t.from_year_basis == D) & (t.to_year_basis == D)).sum()
    neither = ((t.from_year_basis == A) & (t.to_year_basis == A)).sum()
    assert (both, len(t) - both - neither, neither) == (5, 66, 33)


def test_stop_3_rows_for_arizona_public_service_and_public_service_of_new_mexico():
    t = ownership.load()
    for uid, parent, url in ((803, "Pinnacle West Capital", "https://www.pinnaclewest.com/about-us/default.aspx"),
                             (15473, "TXNM Energy (formerly PNM Resources: the former name is from the lead, not from the page)",
                              "https://www.txnmenergy.com/")):
        r = t[t.utility_id_eia == uid]
        assert len(r) == 1, uid
        r = r.iloc[0]
        assert (r.ultimate_parent, r.source_url, r.source_kind, r.date_opened) == (parent, url, "company_page", "2026-11-18")
        assert (r.from_year, r.to_year, r.from_year_basis, r.to_year_basis) == (2001, 2025, A, A)
        assert "assumed" in r.how_it_changed and "current parent" in r.how_it_changed
    nm = t[t.utility_id_eia == 15473].iloc[0].how_it_changed
    assert '"PNM"' in nm and "headline" in nm and "who owns TXNM Energy" in nm


def test_united_illuminating_is_unsourced_at_stop_3_and_on_the_unsourced_list():
    assert 19497 not in set(ownership.load().utility_id_eia)
    u = pd.read_csv(LEADS / "ownership_unsourced_2026-11-18.csv", dtype=str, keep_default_na=False)
    ui = u[u.utility_id_eia == "19497"]
    assert len(ui) == 2 and all("combined report" in r for r in ui.reason) and all("Stop 3" in r for r in ui.reason)
    for uid in ("803", "15473"):
        notes = u[u.utility_id_eia == uid].stop_3_note
        assert len(notes) and all("current-parent row" in n for n in notes)


def test_the_stop_3_requests_are_in_the_fetch_log_once_each():
    log = pd.read_csv(LEADS / "ownership_opened_2026-11-18.csv", dtype=str, keep_default_na=False)
    assert log.fetch_no.astype(int).tolist() == list(range(1, len(log) + 1))
    for url in ("https://www.pinnaclewest.com/about-us/default.aspx", "https://www.txnmenergy.com/"):
        r = log[(log.url == url) & log.status_note.str.startswith("Stop 3")]
        assert len(r) == 1 and r.iloc[0].http_status == "200" and r.iloc[0].client == "research-client/1.0 (plain client)"


def test_no_two_parent_strings_differ_only_in_a_parenthetical():
    """Parents are compared as exact strings (ownership.parents). "TXNM Energy" and "TXNM Energy (formerly ...)" would
    silently fail to match; a later row for Texas-New Mexico Power must use the identical string."""
    names = sorted(set(ownership.load().ultimate_parent))
    base = {}
    for n in names:
        base.setdefault(n.split(" (")[0].strip().lower(), []).append(n)
    assert {k: v for k, v in base.items() if len(v) > 1} == {}


def test_the_new_mexico_parent_matches_no_other_unit_in_the_table():
    t = ownership.load()
    nm = t[t.utility_id_eia == 15473].ultimate_parent.iloc[0]
    assert set(t[t.ultimate_parent == nm].utility_id_eia) == {15473}
    assert 40051 not in set(t.utility_id_eia)                          # Texas-New Mexico Power: no row (left unsourced)
