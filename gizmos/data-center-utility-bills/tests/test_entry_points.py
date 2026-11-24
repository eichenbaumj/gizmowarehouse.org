"""The expensive runs' entry points, end to end on invented inputs (no real file is read and nothing is written to data/).

design.main and the inference check's quantities-only part under the headline rules, and the simulation's new-host
estimate and size check with a few draws: each runs with the rules on by default, names what the rules exclude, and
writes a fingerprint.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, ownership, usable_flag  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import COOP, FUEL, IOU, YEARS, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
STATES = ["AA", "AB", "BB", "BC"]
NONE = ps.UnknownLoad.none("invented data: no load-unknown site")


def invented():
    hosts = [(1, "AA", 10_000, IOU), (2, "BB", 12_000, COOP), (3, "AB", 11_000, COOP)]
    comps = [(10 + i, STATES[i % 4], 9_000 + 150 * i, IOU if i % 5 == 0 else COOP) for i in range(28)] + [(1, "BC", 10_100, IOU)]
    treated, clean, q, regions, dd = world(hosts, comps)
    q["utility_name"] = [f"Utility {u}" for u in q.utility_id_eia]
    usable = {(u, st, y) for u, st, *_ in hosts + comps for y in YEARS} - {(3, "AB", 2012)}
    reasons = {(u, st, y): ("none" if (u, st, y) in usable else "under_customer_floor") for u, st, *_ in hosts + comps for y in YEARS}
    flags = usable_flag.Flags(usable=usable, reason=reasons, rows=len(reasons), source="invented")
    dose = q[ps.KEY + ["year"]].assign(dose=0.0, crypto_mw=0.0, base_retail_gwh=1000.0)
    return treated, clean, q, regions, dd, flags, dose


@pytest.fixture
def patched(monkeypatch, tmp_path):
    treated, clean, q, regions, dd, flags, dose = invented()
    header = tmp_path / "ownership.csv"
    header.write_text(",".join(ownership.COLUMNS) + "\n")
    monkeypatch.setattr(design, "load", lambda: (q, dose, regions, FUEL, dd))
    monkeypatch.setattr(design, "split", lambda theta, which, q_, dose_, frozen=None: (treated, clean))
    monkeypatch.setattr(design, "SETS", (ps.HEADLINE_SET,))
    monkeypatch.setattr(usable_flag, "read", lambda path=None: flags)
    real_load = ownership.load
    monkeypatch.setattr(ownership, "load", lambda path=None: real_load(header))      # a header-only table, never the shared file
    monkeypatch.setattr(ps, "load_gas_share", lambda frozen=None: GAS)
    monkeypatch.setattr(ps, "load_unknown_load", lambda *a, **k: NONE)
    monkeypatch.setattr(design, "FROZEN", tmp_path)
    monkeypatch.setattr(ic, "FROZEN", tmp_path)
    monkeypatch.setattr(ps, "FROZEN", tmp_path)
    return tmp_path, treated, clean, q, regions, dd, flags


def test_design_main_runs_under_the_headline_rules_and_names_what_they_exclude(patched, monkeypatch):
    tmp, *_ = patched
    monkeypatch.setattr(sys, "argv", ["design.py"])
    assert design.main() == 0
    r = json.loads((tmp / "design_support.json").read_text())
    assert r["rules"]["label"] == "headline" and "gas share" in r["gas_share_assumption"]
    s = r["sets"][ps.HEADLINE_SET]
    assert {"utility": "3:AB", "cohort": 2015, "why": design.NOT_USABLE} in s["hosts_dropped"]
    no_row = {x["utility"] for x in s["investor_owned_units_with_no_ownership_row"]}
    assert {"1:AA", "1:BC", "10:AA"} <= no_row                          # every IOU with no row, by name, host or comparison
    host1 = next(h for h in s["hosts"] if h["utility"] == "1:AA")
    why = {e["utility"]: e["why"] for e in host1["excluded_from_its_pool"]}
    assert why["1:BC"] == ownership.OWN_UTILITY and why["10:AA"] == ownership.NO_ROW
    elig = s["full_window_eligibility"]["hosts"]["hosts_without_a_full_window"]
    assert [x["utility"] for x in elig] == ["3:AB"]
    assert {x["utility"] for x in s["gas_share_against_matches"]} == {h["utility"] for h in s["hosts"]}
    assert len(s["fingerprint"]["sha256"]) == 64 and s["support_rule_by_host"]


def test_a_labelled_variant_writes_beside_the_headline_never_over_it(patched, monkeypatch):
    tmp, *_ = patched
    monkeypatch.setattr(sys, "argv", ["design.py", "--rules=sensitivity_affiliates_readmitted"])
    assert design.main() == 0
    assert (tmp / "design_support_sensitivity_affiliates_readmitted.json").exists() and not (tmp / "design_support.json").exists()


def test_the_inference_checks_quantities_part_runs_under_the_headline_rules(patched, monkeypatch):
    tmp, *_ = patched
    monkeypatch.setattr(sys, "argv", ["inference_check.py", "--quantities-only"])
    assert ic.main() == 0
    r = json.loads((tmp / "inference_check.json").read_text())
    e = r["sets"][ps.HEADLINE_SET]
    assert r["rules"]["fuel_control"] == ps.GAS_SHARE
    assert any(c.startswith("gas_share_x_") for c in e["regressors"]["columns"])
    assert e["regressors"]["control_columns_left_out"][0]["why"] == ps.FIRST_YEAR_LEFT_OUT
    assert "fully_absorbed_hosts" in e and "fingerprint" in e and "investor_owned_units_with_no_ownership_row" in e
    assert abs(e["implied_weights"]["host_weights_sum_to"] - 1.0) < 1e-6


def test_the_simulation_runs_with_the_rules_on_and_a_fingerprint(patched):
    tmp, treated, clean, q, regions, dd, flags = patched
    rng = np.random.default_rng(0)
    prices = q[ps.KEY + ["year"]].assign(res_price=np.exp(rng.normal(-2, 0.05, len(q))))
    errs = {(1, "AA"): np.array([0, 0, -1]), (2, "BB"): np.array([0]), (3, "AB"): np.array([0])}
    out = ps.run_new_hosts("test", treated, clean, q, regions, FUEL, dd, prices, errs, (1, 2), draws=3, boot=19, unknown_load=NONE)
    assert out["rules"] == "headline" and out["fuel_control"] == ps.GAS_SHARE and out["draws"] == 3
    assert any(x["utility"] == "3:AB" for x in out["hosts_not_given_a_stand_in"])
    assert "numerical_failures" in out and len(out["fingerprint"]["sha256"]) == 64
    size = ps.run_size_check("test", treated, clean, q, regions, FUEL, dd, (1, 3), datasets=3, boot=19, unknown_load=NONE)
    assert size["rules"] == "headline" and size["datasets"] == 3 and "numerical_failures" in size
    old = ps.run_size_check("test", treated, clean, q, regions, FUEL, dd, (1, 3), datasets=3, boot=19, rules=ps.AS_BEFORE_STEP_D,
                             unknown_load=NONE)
    assert old["rules"] == "as_built_before_step_d"
    assert out["fingerprint"]["sha256"] != ps.run_new_hosts("test", treated, clean, q, regions, FUEL, dd, prices, errs, (1, 9),
                                                            draws=3, boot=19, unknown_load=NONE)["fingerprint"]["sha256"]


# ---- full-window eligibility in the frozen report: a summary, never a per-comparison list (ledger rule 6.3) --------

def big_world(n_comps: int):
    """One host and n_comps comparisons, a third of them missing one or two window years, for the size test."""
    host = [(1, "AA", 10_000, COOP)]
    comps = [(100 + i, STATES[i % 4], 9_000 + 10 * i, COOP) for i in range(n_comps)]
    treated, clean, q, regions, dd = world(host, comps)
    q["utility_name"] = [f"Utility {u}" for u in q.utility_id_eia]
    usable = {(u, st, y) for u, st, *_ in host + comps for y in YEARS}
    usable -= {(100 + i, STATES[i % 4], 2012) for i in range(0, n_comps, 3)}
    usable -= {(100 + i, STATES[i % 4], 2016) for i in range(0, n_comps, 6)}
    reasons = {(u, st, y): ("none" if (u, st, y) in usable else "no_residential_sales") for u, st, *_ in host + comps for y in YEARS}
    reasons = {k: v for k, v in reasons.items() if k[2] != 2016 or v == "none"}          # 2016 rows absent: not_in_panel
    flags = usable_flag.Flags(usable=usable, reason=reasons, rows=len(reasons), source="invented")
    dose = q[ps.KEY + ["year"]].assign(dose=0.0, crypto_mw=0.0, base_retail_gwh=1000.0)
    return treated, clean, q, regions, dd, flags, dose


def run_design_main(monkeypatch, tmp_path, n_comps):
    treated, clean, q, regions, dd, flags, dose = big_world(n_comps)
    header = tmp_path / "ownership.csv"
    header.write_text(",".join(ownership.COLUMNS) + "\n")
    real_load = ownership.load
    monkeypatch.setattr(ownership, "load", lambda path=None: real_load(header))
    monkeypatch.setattr(design, "load", lambda: (q, dose, regions, FUEL, dd))
    monkeypatch.setattr(design, "split", lambda theta, which, q_, dose_, frozen=None: (treated, clean))
    monkeypatch.setattr(design, "SETS", (ps.HEADLINE_SET, "every_cohort_utility"))
    monkeypatch.setattr(usable_flag, "read", lambda path=None: flags)
    monkeypatch.setattr(ps, "load_gas_share", lambda frozen=None: GAS)
    monkeypatch.setattr(ps, "load_unknown_load", lambda *a, **k: NONE)
    monkeypatch.setattr(design, "FROZEN", tmp_path)
    monkeypatch.setattr(sys, "argv", ["design.py"])
    assert design.main() == 0
    return json.loads((tmp_path / "design_support.json").read_text()), (tmp_path / "design_support.json").stat().st_size


@pytest.mark.parametrize("n_comps", [60, 600])
def test_the_report_summarises_comparisons_without_listing_them_and_stays_small(monkeypatch, tmp_path, n_comps):
    r, size = run_design_main(monkeypatch, tmp_path, n_comps)
    for which, s in r["sets"].items():
        e = s["full_window_eligibility"]
        comp = e["comparisons"]
        assert comp["by_cohort"] == {"2015": {"without_a_full_window": len(range(0, n_comps, 3)), "with_a_full_window": n_comps - len(range(0, n_comps, 3)),
                                              "missing_unit_years_by_first_exclusion_reason": {
                                                  "no_residential_sales": len(range(0, n_comps, 3)),
                                                  "not_in_panel": len(range(0, n_comps, 6))}}}
        assert comp["with_a_full_window_in_every_cohort_window"] == n_comps - len(range(0, n_comps, 3))
        flat = json.dumps(e)
        assert not re.search(r'"1\d\d:[A-Z]{2}"', flat)                    # no comparison unit is named anywhere in it
        assert e["hosts"]["hosts_without_a_full_window"] == []
        assert e["per_unit_detail"] == "data/frozen/full_window_eligibility.csv (written once for every set)"
    # what grows with the number of comparisons is the matched-set and support detail the report always had, not this entry
    assert len(json.dumps(r["sets"][ps.HEADLINE_SET]["full_window_eligibility"])) < 3_000
    assert size < 120_000, size                                         # a 600-comparison design stays well under the old 160 KB


def test_the_per_unit_detail_is_written_once_with_reason_codes_only(monkeypatch, tmp_path):
    run_design_main(monkeypatch, tmp_path, 60)
    t = pd.read_csv(tmp_path / "full_window_eligibility.csv")
    assert list(t.columns) == ["utility_id_eia", "state", "cohort", "missing_years", "first_missing_year", "first_exclusion_reason"]
    assert len(t) == len(range(0, 60, 3)) and not t.duplicated(["utility_id_eia", "state", "cohort"]).any()   # once, not per set
    two = t[t.utility_id_eia == 100].iloc[0]
    assert (two.missing_years, two.first_missing_year, two.first_exclusion_reason) == (2, 2012, "no_residential_sales")
    assert set(t.first_exclusion_reason) <= set(usable_flag.VALID_REASONS) | {"not_in_panel"}


def test_a_host_without_a_full_window_is_named_with_its_reason_per_missing_year(patched, monkeypatch):
    tmp, *_ = patched
    monkeypatch.setattr(sys, "argv", ["design.py"])
    assert design.main() == 0
    e = json.loads((tmp / "design_support.json").read_text())["sets"][ps.HEADLINE_SET]["full_window_eligibility"]
    assert e["hosts"]["hosts_without_a_full_window"] == [
        {"utility": "3:AB", "name": "Utility 3", "cohort": 2015, "missing_years": [{"year": 2012, "first_exclusion_reason": "under_customer_floor"}]}]
    assert e["hosts"]["with_a_full_window"] == 2


def test_the_fingerprint_does_not_depend_on_the_eligibility_report(monkeypatch, tmp_path):
    a, _ = run_design_main(monkeypatch, tmp_path, 60)
    monkeypatch.setattr(design, "eligibility_summary", lambda *x, **k: {"replaced": True})
    b, _ = run_design_main(monkeypatch, tmp_path, 60)
    assert a["sets"][ps.HEADLINE_SET]["fingerprint"] == b["sets"][ps.HEADLINE_SET]["fingerprint"]
