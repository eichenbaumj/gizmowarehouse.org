"""power_simulation.main end to end, under C and under --procedure=A, on an invented tree; and the file run as a script.

The first real run stopped in design.build_with_rules: "pass unknown_load=load_unknown_load() (D-96)". main did pass the
object; the cause was that `python3 -I pipeline/analysis/power_simulation.py` loads the module twice (as __main__, and as
pipeline.analysis.power_simulation when design imports it), so the UnknownLoad that main's copy made failed the other
copy's isinstance check. Tests that called the runs (or main) through the imported module never had two copies.
Invented inputs only: nothing under data/ is read or written, and no price file is opened.
"""
from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import misdating, ownership, usable_flag  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import simulation_access_list as sal  # noqa: E402
from test_entry_points import GAS, NONE, invented  # noqa: E402
from test_matching_rules import FUEL  # noqa: E402
from test_power_simulation_procedure import stage_files  # noqa: E402

SCRIPT = ROOT / "pipeline" / "analysis" / "power_simulation.py"


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Invented quantities, design, usable flag, ownership table, gas shares, misdating errors, an access list with its
    hash, per-unit outcomes served only through panel.load_outcomes, and the two stage files."""
    treated, clean, q, regions, dd, flags, dose = invented()
    hosts = {(1, "AA"), (2, "BB")}
    dose["dose"] = [0.03 if (u, st) in hosts and y >= 2014 else 0.0 for u, st, y in zip(dose.utility_id_eia, dose.state, dose.year)]
    dose.to_parquet(tmp_path / "utility_year_dose.parquet")
    header = tmp_path / "ownership.csv"
    header.write_text(",".join(ownership.COLUMNS) + "\n")
    real_load = ownership.load
    monkeypatch.setattr(ownership, "load", lambda path=None: real_load(header))
    monkeypatch.setattr(usable_flag, "read", lambda path=None: flags)
    monkeypatch.setattr(ps, "FROZEN", tmp_path)
    monkeypatch.setattr(ps, "INTERIM", tmp_path)
    monkeypatch.setattr(ps.panel, "load_quantities", lambda *a, **k: q)
    monkeypatch.setattr(ps.market_region, "by_unit_year", lambda *a, **k: regions)
    monkeypatch.setattr(ps, "load_controls", lambda frozen=None: (FUEL, dd))
    monkeypatch.setattr(ps, "load_gas_share", lambda frozen=None: GAS)
    monkeypatch.setattr(ps, "load_unknown_load", lambda *a, **k: NONE)
    monkeypatch.setattr(ps, "design", lambda q_, dose_, theta, history=None, **k: (treated, clean))
    monkeypatch.setattr(ps, "history_settled", lambda theta, frozen=None: {})
    monkeypatch.setattr(ps, "set_aside", lambda theta, frozen=None, ten_year_case=False: set())
    monkeypatch.setattr(misdating, "host_errors", lambda theta, *a, **k: {(1, "AA"): np.array([0, -1]), (2, "BB"): np.array([0, 2])})
    lp, hp = tmp_path / "list.csv", tmp_path / "list.sha256"
    sal.write(clean.assign(name="x"), pd.DataFrame(columns=["utility_id_eia", "state", "name", "reason"]), lp, tmp_path / "ex.csv", hp)
    monkeypatch.setattr(sal, "LIST_PATH", lp)
    monkeypatch.setattr(sal, "HASH_PATH", hp)
    rng = np.random.default_rng(0)
    prices = q[ps.KEY + ["year"]].assign(res_price=np.exp(rng.normal(-2, 0.05, len(q))))
    read = []

    def load_outcomes(*, purpose, units):
        assert purpose == "power_simulation"
        read.append(len(units))
        return prices.merge(units, on=ps.KEY)
    monkeypatch.setattr(ps.panel, "load_outcomes", load_outcomes)
    seen = []
    for name, size in (("run_new_hosts", "draws"), ("run_size_check", "datasets"), ("run_second_number", "draws")):
        orig = getattr(ps, name)

        def small(*a, _orig=orig, _name=name, _size=size, **k):
            seen.append((_name, k.get("unknown_load"), k.get("procedure")))
            return _orig(*a, **{**k, _size: 2, "boot": 9, "workers": 1})
        monkeypatch.setattr(ps, name, small)
    stage_files(tmp_path)
    return tmp_path, seen, read


def test_main_runs_end_to_end_under_c_and_writes_the_headline_file(tree, monkeypatch):
    tmp, seen, read = tree
    monkeypatch.setattr(sys, "argv", ["power_simulation.py"])
    assert ps.main() == 0
    r = json.loads((tmp / "power_simulation.json").read_text())
    assert r["procedure"]["procedure"] == "C" and r["procedure"]["stage2_verdicts"] == {"range": "passed", "early_years_test": "passed"}
    assert len(r["procedure"]["stage1_sha256"]) == 64 and r["procedure"]["comparison_fingerprint"] == "f"
    assert set(r["new_host_estimate"]) == {"2%", "5%"} and set(r["new_host_estimate"]["2%"]) == {ps.HEADLINE_SET, "every_cohort_utility", ps.TEN_YEAR_SET}
    for t in ("2%", "5%"):
        for out in r["new_host_estimate"][t].values():
            assert out["procedure"]["name"] == "C" and out["draws"] == 2
    assert len(r["early_years_test_size_on_made_up_prices"]) == 3 and len(r["side_runs"]) == 2
    assert r["per_point_of_load"]["long_difference"]["inference"].startswith("not under the selected procedure")
    assert r["access_list"] == sal.DESCRIPTION and r["readings_adopted"] == ps.READINGS_ADOPTED       # wording of Stop 3
    for t in ("2%", "5%"):
        for out in r["new_host_estimate"][t].values():
            assert out["power"]["name"] == "smallest increase detected in the correct direction four times in five"
            assert ps.SMALLEST_INCREASE_KEY in out["start_years_exact"]
            assert "hosts_with_unresolved_ownership" in out
    assert not (tmp / "power_simulation_figures_for_the_bootstrap_as_built.json").exists()
    # every run was handed the one unknown-load object and the procedure, on every set and threshold
    assert len(seen) == 5 + 3 + 2 + 1 and all(u is NONE for _, u, _ in seen)
    assert all(p == "C" for n, _, p in seen if n != "run_second_number") and read


def test_main_with_procedure_a_writes_its_own_file_only(tree, monkeypatch):
    tmp, seen, _ = tree
    monkeypatch.setattr(sys, "argv", ["power_simulation.py", "--procedure=A"])
    assert ps.main() == 0
    r = json.loads((tmp / "power_simulation_figures_for_the_bootstrap_as_built.json").read_text())
    assert r["procedure"]["procedure"] == "A" and r["procedure"]["label"] == ps.AS_BUILT_LABEL
    assert not (tmp / "power_simulation.json").exists()
    assert all(u is NONE for _, u, _ in seen) and all(p == "A" for n, _, p in seen if n != "run_second_number")


def test_every_keyword_main_passes_through_rk_is_accepted_by_its_callees():
    src = inspect.getsource(ps.main)
    rk = {"rules", "ownership", "usable", "gas", "unknown_load", "procedure", "provenance"}
    for key in rk:
        assert f'"{key}":' in src.split("rk = {", 1)[1].split("}", 1)[0]
    for fn in (ps.run_new_hosts, ps.run_size_check):
        assert rk <= set(inspect.signature(fn).parameters)
    call = src.split("run_second_number(", 1)[1].split("\n\n", 1)[0].split("write_report", 1)[0]
    assert "unknown_load=unknown" in call
    assert "simulation_hosts(tr, cl, q, regions, fuel, dd, rules, ownership, usable, gas, unknown, 0.02)" in inspect.getsource(ps.run_added)


def test_run_as_a_script_everything_runs_in_one_copy_of_the_module():
    """Executed as __main__ (as `python3 -I pipeline/analysis/power_simulation.py` does), the file must hand over to the
    module design imports, so that one UnknownLoad, Rules and Exclusions class is in play. Safe on any code: quantities and
    outcomes raise if touched, and --procedure=A skips the stage files."""
    code = f"""
import runpy, sys
sys.path.insert(0, {str(ROOT)!r})
from pipeline.electricity import panel
def refuse(*a, **k):
    raise RuntimeError("TWO COPIES: the script's own main ran and tried to read quantities")
panel.load_quantities = refuse
panel.load_outcomes = refuse
from pipeline.analysis import power_simulation as ps
ps.main = lambda: print("ONE COPY") or 0
sys.argv = ["power_simulation.py", "--procedure=A"]
try:
    runpy.run_path({str(SCRIPT)!r}, run_name="__main__")
except SystemExit as e:
    print("exit", e.code)
"""
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert "ONE COPY" in r.stdout and "exit 0" in r.stdout, r.stdout + r.stderr[-2000:]
