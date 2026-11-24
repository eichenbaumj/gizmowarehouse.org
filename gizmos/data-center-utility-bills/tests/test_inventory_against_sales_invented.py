"""The check 'Does the inventory show up in sales?' (pipeline/analysis/inventory_against_sales.py), on invented inputs only.

No file under data/ is read. Every world here is built in the test: a few invented hosts with invented cohorts and matched
comparison utilities, invented non-residential sales and invented inventory load. Covers: the four settings Joe adopted
on 2026-11-19 (D-107), each with a test that it is the one computed and that every other value is refused in words (the
base is non-residential sales averaged over 2009 to 2011; the slope has an intercept; a host with a missing year is left
out and named; a comparison utility with a missing year is left out of that host's mean and named); a planted slope and
intercept recovered; the plan's three sentences at their edges; negative excess growth entering as it is; a host with no
matches; a comparison utility whose before mean is zero (stopped in words, a case the settings do not name); the share
at exactly half; the absent-row convention of the inventory frame; malformed inputs; and the guard against a run on
research data before the freeze.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import inventory_against_sales as ias  # noqa: E402

TOL = 1e-10
YEARS = range(2005, 2026)


INVENTED = ias.INVENTED_INPUTS


def run(hosts, q, dose, **kw):
    return ias.check(hosts, q, dose, inputs_are=INVENTED, **kw)


def flat_then(before_gwh: float, after_gwh: float, cohort: int, base_gwh: float | None = None) -> dict:
    """Non-residential GWh by year: `base_gwh` in 2009-2011 (if given), `before_gwh` through cohort-1, `after_gwh` from
    cohort+1, and the mean of the two in the cohort year (which the check never reads)."""
    out = {}
    for y in YEARS:
        out[y] = before_gwh if y < cohort else (after_gwh if y > cohort else 0.5 * (before_gwh + after_gwh))
    if base_gwh is not None:
        for y in ias.BASE_YEARS:
            out[y] = base_gwh
    return out


class World:
    """An invented world. Hosts are utility ids 1.., comparison utilities 100.., all in state 'ZZ' unless given."""

    def __init__(self):
        self.nonres = {}           # key -> {year: GWh}
        self.dc = {}               # key -> {year: GWh}, only years with load (as the inventory build writes them)
        self.base = {}             # key -> base_retail_gwh
        self.hosts = []

    def unit(self, key, nonres_by_year: dict, dc_by_year: dict | None = None, base_retail: float | None = None):
        self.nonres[key] = dict(nonres_by_year)
        if dc_by_year:
            self.dc[key] = dict(dc_by_year)
        if base_retail is not None:
            self.base[key] = base_retail

    def host(self, key, cohort, matches):
        self.hosts.append({"host": key, "cohort": cohort, "matches": list(matches)})

    def quantities(self) -> pd.DataFrame:
        rows = [(k[0], k[1], y, v * 1000.0, "noise") for k, d in self.nonres.items() for y, v in d.items()]
        return pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "nonres_mwh", "some_other_column"])

    def dose(self) -> pd.DataFrame:
        rows = []
        for k, b in self.base.items():
            years = self.dc.get(k, {})
            if not years:                      # a utility with a base and no load still has a row for its base
                rows.append((k[0], k[1], 2001, 0.0, b))
            for y, v in years.items():
                rows.append((k[0], k[1], y, v, b))
        return pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "dc_gwh", "base_retail_gwh"])

    def run(self):
        return run(self.hosts, self.quantities(), self.dose())


def planted(slope_true: float, intercept_true: float = 0.0):
    """Five hosts, each with three comparison utilities whose growth rates are 0.05, 0.10 and 0.15 (mean 0.10) on
    different levels, so the mean of rates (0.10) differs from the pooled rate. Each host's excess growth is planted as
    intercept_true + slope_true * (inventory added), against the host's non-residential base over 2009 to 2011 (the
    adopted base). Each host's total retail base is set to a different number, which the check must not use."""
    w = World()
    added = {1: 50.0, 2: 120.0, 3: 200.0, 4: 310.0, 5: 80.0}
    cohorts = {1: 2015, 2: 2017, 3: 2019, 4: 2020, 5: 2022}
    base_retail = {1: 1000.0, 2: 2500.0, 3: 4000.0, 4: 1800.0, 5: 3000.0}
    base_nonres = {1: 600.0, 2: 1500.0, 3: 2000.0, 4: 900.0, 5: 1700.0}
    rate = 0.10
    truth = {}
    for h, g in cohorts.items():
        comps = []
        for j, (lvl, r) in enumerate(((100.0, 0.05), (400.0, 0.10), (900.0, 0.15))):
            ck = (100 + 10 * h + j, "ZZ")
            w.unit(ck, flat_then(lvl, lvl * (1 + r), g))
            comps.append(ck)
        base = base_nonres[h]
        excess = intercept_true + slope_true * added[h]
        before = 700.0 + 10 * h
        after = before + base * rate + excess
        dc = {y: added[h] for y in range(g, 2026)}          # load from the cohort year on; none before
        w.unit((h, "ZZ"), flat_then(before, after, g, base_gwh=base_nonres[h]), dc, base_retail=base_retail[h])
        w.host((h, "ZZ"), g, comps)
        truth[f"{h}:ZZ"] = {"excess": excess, "added": added[h], "expected": base * rate, "base_retail": base_retail[h]}
    return w, truth


# ---- the four settings (Joe, 2026-11-19, D-107) ------------------------------------------------------------------------

def test_the_settings_are_the_adopted_four_and_every_other_value_is_refused_in_words():
    assert ias.ADOPTED == ias.Readings()
    assert ias.SETTINGS == {"base": ias.BASE_NON_RESIDENTIAL, "slope": ias.SLOPE_WITH_INTERCEPT,
                            "host_missing": ias.HOST_EXCLUDE, "match_missing": ias.MATCH_LEAVE_OUT}
    assert "D-107" in ias.SETTINGS_SOURCE and "2026-11-19" in ias.SETTINGS_SOURCE
    for field, other in (("base", ias.BASE_TOTAL_RETAIL), ("slope", ias.SLOPE_THROUGH_ORIGIN), ("host_missing", ias.HOST_STOP),
                         ("match_missing", ias.MATCH_EXCLUDE_HOST), ("match_missing", ias.MATCH_STOP), ("base", "retail")):
        with pytest.raises(ValueError, match=f"Readings.{field} is .*D-107.*no other value is accepted"):
            ias.Readings(**{field: other})
    w, _ = planted(1.0)
    with pytest.raises(TypeError):
        run(w.hosts, w.quantities(), w.dose(), readings={"base": ias.BASE_NON_RESIDENTIAL})
    out = w.run()
    assert out["settings"] == ias.SETTINGS and out["settings_source"] == ias.SETTINGS_SOURCE


def test_setting_1_the_base_is_non_residential_sales_averaged_over_2009_to_2011():
    w, truth = planted(1.0)
    w.nonres[(1, "ZZ")][2009] = 500.0                  # base years 500, 600, 700: mean 600, the planted base
    w.nonres[(1, "ZZ")][2011] = 700.0
    out = w.run()
    r = {x["host"]: x for x in out["by_host"]}
    assert abs(r["1:ZZ"]["base_gwh"] - 600.0) < TOL and r["1:ZZ"]["base_kind"] == ias.BASE_NON_RESIDENTIAL
    assert abs(r["1:ZZ"]["expected_gain_gwh"] - 60.0) < 1e-8                   # 600 x the comparison rate 0.10
    assert abs(r["1:ZZ"]["expected_gain_gwh"] - truth["1:ZZ"]["base_retail"] * 0.10) > 1.0   # not the retail base
    d = w.dose().drop(columns="base_retail_gwh")       # the retail base is not read at all
    assert run(w.hosts, w.quantities(), d)["hosts_with_a_figure"] == 5


def test_setting_2_the_slope_has_an_intercept():
    w, _ = planted(1.2, intercept_true=30.0)
    out = w.run()
    assert out["slope"]["form"] == ias.SLOPE_WITH_INTERCEPT
    assert abs(out["slope"]["slope"] - 1.2) < TOL and abs(out["slope"]["intercept"] - 30.0) < 1e-8
    x = np.array([50.0, 120.0, 200.0, 310.0, 80.0])
    through_origin = float(x @ (30.0 + 1.2 * x) / (x @ x))
    assert abs(through_origin - 1.2) > 0.05                                     # the guard: the two forms differ here


def test_setting_3_a_host_with_a_missing_year_is_left_out_and_named_never_filled():
    w, _ = planted(1.0)
    del w.nonres[(2, "ZZ")][2016]              # host 2, cohort 2017: event year -1
    out = w.run()
    assert [x["host"] for x in out["hosts_left_out"]] == ["2:ZZ"]
    assert "2016" in out["hosts_left_out"][0]["why"] and "a host with a missing year" in out["hosts_left_out"][0]["why"]
    assert out["hosts_with_a_figure"] == 4 and abs(out["slope"]["slope"] - 1.0) < TOL
    w2, _ = planted(1.0)
    del w2.nonres[(1, "ZZ")][2010]             # a base year
    out = w2.run()
    assert out["hosts_left_out"][0]["host"] == "1:ZZ" and "base years [2010]" in out["hosts_left_out"][0]["why"]
    w3, _ = planted(1.0)
    w3.nonres[(4, "ZZ")][2023] = float("nan")  # host 4, cohort 2020: event year 3, not finite
    assert [x["host"] for x in w3.run()["hosts_left_out"]] == ["4:ZZ"]


def test_setting_4_a_comparison_utility_with_a_missing_year_is_left_out_of_that_hosts_mean_and_named():
    w, truth = planted(1.0)
    gone = w.hosts[0]["matches"][2]            # host 1's comparison growing at 0.15
    del w.nonres[gone][2017]                   # host 1, cohort 2015: event year 2
    out = w.run()
    r = next(x for x in out["by_host"] if x["host"] == "1:ZZ")
    assert r["computed"] and abs(r["comparison_mean_rate"] - 0.075) < TOL
    assert r["matches_left_out"] == [{"utility": f"{gone[0]}:{gone[1]}", "why": "non-residential sales missing in [2017]"}]
    assert out["comparison_utilities_left_out"] == [{"host": "1:ZZ", "utility": f"{gone[0]}:{gone[1]}",
                                                     "why": "non-residential sales missing in [2017]"}]
    assert abs(r["excess_growth_gwh"] - (truth["1:ZZ"]["excess"] + 600.0 * 0.025)) < 1e-8
    assert out["hosts_with_a_figure"] == 5 and out["hosts_left_out"] == []
    # The same unit stays in another host's mean where it has every year that host needs (host 1's matches are its own).


def test_every_match_left_out_names_the_host():
    w, _ = planted(1.0)
    for m in w.hosts[1]["matches"]:
        del w.nonres[m][2016]
    out = w.run()
    assert {"host": "2:ZZ", "cohort": 2017, "why": ias.NO_MATCH_LEFT} in out["hosts_left_out"]


def test_a_match_with_a_zero_before_mean_is_not_a_missing_year_and_stops_in_words():
    w, _ = planted(1.0)
    m = w.hosts[0]["matches"][0]
    w.nonres[m] = {y: (0.0 if y < 2015 else 50.0) for y in YEARS}
    with pytest.raises(ias.CheckStopped, match=r"not a missing year.*adopted by Joe on 2026-11-19, D-111"):
        w.run()


# ---- the guard: no run on research data before the freeze --------------------------------------------------------------

def test_inputs_are_is_required_and_research_data_is_refused_before_the_freeze(monkeypatch, tmp_path):
    from pipeline.electricity import panel
    w, _ = planted(1.0)
    with pytest.raises(TypeError):
        ias.check(w.hosts, w.quantities(), w.dose())                          # noqa: the point of the test
    with pytest.raises(ias.InventoryCheckRefused, match="must be"):
        ias.check(w.hosts, w.quantities(), w.dose(), inputs_are="real")
    assert not Path(panel.GATE_FILE).exists()                                 # the plan is not frozen in this repository
    with pytest.raises(ias.InventoryCheckRefused, match="gate file .* does not exist"):
        ias.check(w.hosts, w.quantities(), w.dose(), inputs_are=ias.RESEARCH_DATA_AFTER_THE_FREEZE)
    gate = tmp_path / "GATE1_SIGNED"
    gate.write_text("invented gate in a test\n")
    monkeypatch.setattr(panel, "GATE_FILE", gate)
    monkeypatch.delenv(ias.AUTH_ENV, raising=False)
    with pytest.raises(ias.InventoryCheckRefused, match="not set to 1"):
        ias.check(w.hosts, w.quantities(), w.dose(), inputs_are=ias.RESEARCH_DATA_AFTER_THE_FREEZE)
    monkeypatch.setenv(ias.AUTH_ENV, "1")
    out = ias.check(w.hosts, w.quantities(), w.dose(), inputs_are=ias.RESEARCH_DATA_AFTER_THE_FREEZE)
    assert out["inputs_are"] == ias.RESEARCH_DATA_AFTER_THE_FREEZE and out["hosts_with_a_figure"] == 5


def test_the_auth_variable_is_the_registrys_and_nothing_runs_at_import():
    import ast
    from pipeline.analysis import run_outcomes
    assert ias.AUTH_ENV == run_outcomes.AUTH_ENV
    tree = ast.parse(Path(ias.__file__).read_text())
    assert not [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
    assert not [n for n in tree.body if isinstance(n, ast.If)]                # no `if __name__ == "__main__"`
    assert all(isinstance(n, (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef,
                              ast.ClassDef)) for n in tree.body)
    assert all(isinstance(n.value, ast.Constant) for n in tree.body if isinstance(n, ast.Expr))   # the docstring only
    calls = {c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", None)
             for c in ast.walk(tree) if isinstance(c, ast.Call)}
    assert not {"read_parquet", "read_csv", "read_text", "load_outcomes", "open"} & calls


# ---- a planted slope is recovered ---------------------------------------------------------------------------------------

def test_planted_slope_and_excess_recovered():
    w, truth = planted(0.8)
    out = w.run()
    assert out["hosts_with_a_figure"] == 5 and out["hosts_left_out"] == []
    for r in out["by_host"]:
        t = truth[r["host"]]
        assert abs(r["comparison_mean_rate"] - 0.10) < TOL           # the mean of 0.05, 0.10, 0.15, not the pooled rate
        assert abs(r["expected_gain_gwh"] - t["expected"]) < 1e-8
        assert abs(r["excess_growth_gwh"] - t["excess"]) < 1e-8
        assert abs(r["inventory_added_gwh"] - t["added"]) < TOL
    assert abs(out["slope"]["slope"] - 0.8) < TOL
    assert abs(out["slope"]["intercept"]) < 1e-8
    assert out["reading"] == ias.SENTENCE_BETWEEN
    assert out["share_with_excess_at_least_half_the_inventory"] == 1.0


def test_the_planted_check_fails_when_the_base_is_broken(monkeypatch):
    """Deliberate break in the test process: the base years read as 2010 to 2012, where the host's sales are its
    before level, not its base. The planted excess is then not recovered."""
    monkeypatch.setattr(ias, "BASE_YEARS", (2010, 2011, 2012))
    w, truth = planted(0.8)
    w.nonres[(1, "ZZ")][2012] = 900.0
    out = w.run()
    r = next(x for x in out["by_host"] if x["host"] == "1:ZZ")
    with pytest.raises(AssertionError):
        assert abs(r["excess_growth_gwh"] - truth["1:ZZ"]["excess"]) < 1e-8


def test_mean_of_rates_differs_from_the_pooled_rate_here():
    # Guards the planted world: if the two readings coincided, the test above could not tell them apart.
    pooled = (100 * 1.05 + 400 * 1.10 + 900 * 1.15) / (100 + 400 + 900) - 1
    assert abs(pooled - 0.10) > 0.02


# ---- the three readings, at their edges --------------------------------------------------------------------------------

@pytest.mark.parametrize("s,expected", [
    (0.5, ias.SENTENCE_BETWEEN), (1.5, ias.SENTENCE_BETWEEN), (1.0, ias.SENTENCE_BETWEEN),
    (0.5 - 1e-12, ias.SENTENCE_BELOW), (1.5 + 1e-12, ias.SENTENCE_ABOVE), (-3.0, ias.SENTENCE_BELOW),
    (40.0, ias.SENTENCE_ABOVE), (None, None), (float("nan"), None)])
def test_reading_edges(s, expected):
    assert ias.reading(s) == expected


@pytest.mark.parametrize("s,expected", [(0.3, ias.SENTENCE_BELOW), (1.0, ias.SENTENCE_BETWEEN), (2.0, ias.SENTENCE_ABOVE),
                                        (-0.5, ias.SENTENCE_BELOW)])
def test_reading_through_the_check(s, expected):
    w, _ = planted(s)
    out = w.run()
    assert abs(out["slope"]["slope"] - s) < TOL
    assert out["reading"] == expected and out["reading_failure"] is None


def test_sentences_are_the_plans_verbatim():
    text = " ".join((ROOT / "PREANALYSIS.md").read_text().split())
    for s in (ias.SENTENCE_BETWEEN, ias.SENTENCE_BELOW, ias.SENTENCE_ABOVE):
        assert f'"{s}"' in text


# ---- negative excess growth enters as it is ----------------------------------------------------------------------------

def test_negative_excess_growth_enters_as_it_is():
    w, truth = planted(-0.5)
    out = w.run()
    assert all(r["excess_growth_gwh"] < 0 for r in out["by_host"])
    assert out["hosts_with_a_figure"] == 5
    assert out["share_with_excess_at_least_half_the_inventory"] == 0.0
    assert abs(out["slope"]["slope"] + 0.5) < TOL


def _exact_world(excess_by_host: dict) -> World:
    """Comparison utilities with no growth (rate exactly 0) and whole-number GWh, so excess growth is exact in binary."""
    w = World()
    for h, (excess, added) in excess_by_host.items():
        g = 2016
        ck = (200 + h, "ZZ")
        w.unit(ck, flat_then(300.0, 300.0, g))
        w.unit((h, "ZZ"), flat_then(500.0, 500.0 + excess, g), {y: added for y in range(g, 2026)}, base_retail=1000.0)
        w.host((h, "ZZ"), g, [ck])
    return w


def test_share_counts_exactly_half_and_not_below():
    w = _exact_world({1: (50.0, 100.0), 2: (49.0, 100.0), 3: (51.0, 100.0), 4: (-10.0, 100.0)})
    out = w.run()
    r = {x["host"]: x for x in out["by_host"]}
    assert r["1:ZZ"]["excess_growth_gwh"] == 50.0 and r["1:ZZ"]["excess_at_least_half_the_inventory"] is True
    assert r["2:ZZ"]["excess_at_least_half_the_inventory"] is False
    assert r["3:ZZ"]["excess_at_least_half_the_inventory"] is True
    assert r["4:ZZ"]["excess_at_least_half_the_inventory"] is False
    assert out["hosts_with_excess_at_least_half_the_inventory"] == 2
    assert out["share_with_excess_at_least_half_the_inventory"] == 0.5


# ---- a host with no matches ------------------------------------------------------------------------------------------

def test_host_with_no_matches_is_named_and_left_out():
    w, _ = planted(1.0)
    w.hosts[2]["matches"] = []
    out = w.run()
    assert out["hosts_left_out"] == [{"host": "3:ZZ", "cohort": 2019, "why": ias.NO_MATCHES}]
    assert out["hosts_with_a_figure"] == 4
    assert abs(out["slope"]["slope"] - 1.0) < TOL


# ---- the inventory frame ------------------------------------------------------------------------------------------------

def test_absent_inventory_row_is_no_load_and_a_host_with_none_added_is_listed():
    w, _ = planted(1.0)
    w.dc[(5, "ZZ")] = {}                       # host 5 has a base row and no load in any year
    out = w.run()
    r = next(x for x in out["by_host"] if x["host"] == "5:ZZ")
    assert r["inventory_before_gwh"] == 0.0 and r["inventory_after_gwh"] == 0.0
    assert out["hosts_where_the_inventory_adds_no_load"] == ["5:ZZ"]


def test_load_before_the_window_is_netted_out():
    w, truth = planted(1.0)
    for y in range(2005, 2026):
        w.dc[(3, "ZZ")][y] = w.dc[(3, "ZZ")].get(y, 0.0) + 25.0     # 25 GWh present throughout
    r = next(x for x in w.run()["by_host"] if x["host"] == "3:ZZ")
    assert abs(r["inventory_before_gwh"] - 25.0) < TOL and abs(r["inventory_added_gwh"] - truth["3:ZZ"]["added"]) < TOL


# ---- slope failures and malformed inputs ------------------------------------------------------------------------------

def test_slope_failures_are_in_words_with_no_reading():
    w, _ = planted(1.0)
    w.hosts = w.hosts[:1]
    out = w.run()
    assert out["slope"]["slope"] is None and "at least two" in out["reading_failure"] and out["reading"] is None
    s = ias.slope([5.0, 5.0], [1.0, 3.0])
    assert s["slope"] is None and "same at every host" in s["failure"]
    s = ias.slope([], [])
    assert "at least two" in s["failure"]


def test_malformed_inputs_stop_in_words():
    w, _ = planted(1.0)
    q = w.quantities()
    with pytest.raises(ias.CheckStopped, match="duplicate"):
        run(w.hosts, pd.concat([q, q.head(1)]), w.dose())
    with pytest.raises(ias.CheckStopped, match="nonres_mwh"):
        run(w.hosts, q.drop(columns="nonres_mwh"), w.dose())
    with pytest.raises(ias.CheckStopped, match="dc_gwh"):
        run(w.hosts, q, w.dose().drop(columns="dc_gwh"))
    with pytest.raises(ias.CheckStopped, match="given twice"):
        run(w.hosts + w.hosts[:1], q, w.dose())


def test_hosts_from_design_reads_key_cohort_and_match_keys():
    hosts = pd.DataFrame([{"key": (7, "AA"), "cohort": 2018, "row": 0, "matches": [1, 2], "match_keys": [(8, "AA"), (9, "AB")]},
                          {"key": (6, "AB"), "cohort": 2015, "row": 3, "matches": [], "match_keys": []}])
    out = ias.hosts_from_design(SimpleNamespace(hosts=hosts))
    assert out == [{"host": (7, "AA"), "cohort": 2018, "matches": [(8, "AA"), (9, "AB")]},
                   {"host": (6, "AB"), "cohort": 2015, "matches": []}]
    assert ias.hosts_from_design(SimpleNamespace(hosts=pd.DataFrame())) == []


# ---- Joe's ruling of 2026-11-20 on which history of the inventory the check is given (D-119) -------------------------
IAS_D119_WORDS = ("Use the inventory as built, the load history underlying the headline design, for the "
                  "inventory-against-sales check.")


def _ias_history_problems(texts: dict) -> list:
    bad = []
    for name, t in texts.items():
        t = " ".join(str(t).split())
        low = t.lower()
        for phrase in ("caller's choice", "not settled by the plan", "which history of the inventory"):
            if phrase in low:
                bad.append((name, phrase))
        if "inventory as built" not in t or "D-119" not in t:
            bad.append((name, "no 'inventory as built' or no D-119"))
    return bad


def test_d119_the_inventory_history_is_settled_and_carried_verbatim():
    assert ias.INVENTORY_HISTORY_D119_WORDS == IAS_D119_WORDS
    assert ias.INVENTORY_HISTORY_RULED_D119 == "Joe, 2026-11-20 (D-119)"
    assert IAS_D119_WORDS in ias.INVENTORY_HISTORY_D119 and "RunInputs.side.dose" in ias.INVENTORY_HISTORY_D119
    assert "cannot detect a frame built from another history" in ias.INVENTORY_HISTORY_D119
    doc = " ".join(ias.__doc__.split())
    assert IAS_D119_WORDS in doc and "cannot detect a frame built from another history" in doc
    w, _ = planted(1.0)
    out = w.run()
    texts = {"constant": ias.INVENTORY_HISTORY_D119,
             "docstring": doc.split("inventory figure")[1].split("slope ")[0],
             "what_this_is": out["what_this_is"]}
    assert _ias_history_problems(texts) == []


def test_d119_the_inventory_history_check_can_fail():
    """Break: the D-107 era sentence given to the same check in the test process."""
    old = ("Which history of the inventory (as built, no anchoring, a ruling 4 case) is supplied is the caller's choice "
           "and is not settled by the plan.")
    assert _ias_history_problems({"x": old}) == [("x", "caller's choice"), ("x", "not settled by the plan"),
                                                 ("x", "which history of the inventory"),
                                                 ("x", "no 'inventory as built' or no D-119")]
