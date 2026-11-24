"""The simulation's reporting wording, as the owner adopted it on 2026-11-18 (Stop 3), after the results were available.

1. Full-window usability is an additional access-list requirement, not a substitute for the never-host and price-hold
   restrictions.
2. The reported power is the probability that the 90% interval lies entirely above zero under a planted positive effect;
   the result is the "smallest increase detected in the correct direction four times in five"; never a one-sided 10% test.
3. Numerical failures stay in the denominator and count as no detection for power, separately from the calibration
   rates; the failure count is reported, including zero.

Wording only: no number and no computation changes. Invented readings; no price is read.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import simulation_access_list as sal  # noqa: E402

PLAIN = "smallest increase detected in the correct direction four times in five"


def reading(lo, hi, est, failure=None):
    return {"est": est, "se": 0.01, "lo": lo, "hi": hi, "clusters": 6, "pre_wald": 1.0, "pre_p_bootstrap": 0.5, "pre_p": 0.5,
            "max_abs_early": 0.0, "lo_analytic": lo, "hi_analytic": hi, "numerical_failure": failure, "analytic_failure": failure}


def draws(n=10):
    out = []
    for _ in range(n):
        exact = [reading(-0.02, 0.02, 0.0)] + [reading(t / 100 - 0.02, t / 100 + 0.02, t / 100) for t in ps.TAUS_PCT[1:]]
        out.append({"exact": exact, "misdated": list(exact)})
    return out


@pytest.mark.parametrize("procedure", ps.PROCEDURES)
def test_the_power_figure_carries_its_definition_and_its_plain_name(procedure):
    out = ps.read_draws(draws(), hosts=2, procedure=procedure)
    p = out["power"]
    assert p["name"] == PLAIN
    assert "probability" in p["definition"] and "entirely above zero" in p["definition"] and "planted positive effect" in p["definition"]
    assert "90%" in p["definition"]
    for block in ("start_years_exact", "start_years_misdated"):
        b = out[block]
        assert ps.SMALLEST_INCREASE_KEY in b and ps.POWER_BY_TAU_KEY in b
        assert "smallest_effect_whose_range_excludes_zero_in_80pct_of_draws" not in b and "range_excludes_zero_by_planted_pct" not in b
    # the same numbers as before the rename: lower end above zero from a 2% planted effect on (lo = t - 2%)
    assert out["start_years_exact"][ps.POWER_BY_TAU_KEY]["2"] == 0.0 and out["start_years_exact"][ps.POWER_BY_TAU_KEY]["3"] == 1.0
    assert out["start_years_exact"][ps.SMALLEST_INCREASE_KEY] == ps.detectable(
        [float(t > 2) for t in ps.TAUS_PCT])
    assert "entirely above zero" in out["procedure"]["told_from_zero"]


def test_numerical_failures_are_no_detection_for_power_and_apart_from_calibration_and_reported_at_zero():
    out = ps.read_draws(draws(), hosts=2, procedure=ps.SELECTED)
    note = out["power"]["numerical_failures"]
    assert "denominator" in note and "no detection" in note and "calibration" in note and "miss" in note and "rejection" in note
    assert "including zero" in note or "even when zero" in note
    assert out["numerical_failures"]["selected_procedure"]["count"] == 0
    for block in ("start_years_exact", "start_years_misdated"):
        assert out[block]["planted_5pct"]["numerical_failures"]["count"] == 0


def test_a_failed_draw_lowers_power_and_stays_in_the_denominator():
    d = draws()
    bad = reading(np.nan, np.nan, np.nan, failure="rank deficient")
    d[0] = {"exact": [dict(bad) for _ in ps.TAUS_PCT], "misdated": [dict(bad) for _ in ps.TAUS_PCT]}
    out = ps.read_draws(d, hosts=2, procedure=ps.SELECTED)
    assert out["start_years_exact"][ps.POWER_BY_TAU_KEY]["5"] == 0.9
    assert out["start_years_exact"]["planted_5pct"]["numerical_failures"]["count"] == 1


def test_nothing_in_the_module_or_its_output_calls_the_power_figure_a_one_sided_test():
    src = (ROOT / "pipeline" / "analysis" / "power_simulation.py").read_text()
    assert not re.search(r"one[- ]sided", src, re.I)
    text = json.dumps(ps.read_draws(draws(), hosts=2, procedure=ps.SELECTED)) + json.dumps(ps.PROCEDURE_TEXT)
    assert not re.search(r"one[- ]sided|10% test", text, re.I)


def test_the_module_records_that_these_readings_were_adopted_after_the_results_were_available():
    for mod in (ps, sal):
        doc = " ".join(mod.__doc__.split())
        assert "2026-11-18" in doc and "after the simulation's results were available" in doc, mod.__name__


def test_the_access_list_says_full_window_usability_is_in_addition_and_replaces_nothing():
    for text in (" ".join(sal.__doc__.split()), sal.DESCRIPTION):
        assert "in addition to" in text and "never-host" in text and "price-hold" in text and "replaces none" in text


def test_the_access_list_prints_its_description(monkeypatch, capsys, tmp_path):
    import pandas as pd
    monkeypatch.setattr(ps, "rebuilt_inventory", lambda *a, **k: False)
    monkeypatch.setattr(ps, "load_unknown_load", lambda *a, **k: ps.UnknownLoad.none("invented"))
    from pipeline.analysis import design, usable_flag
    monkeypatch.setattr(design, "load", lambda: (None, None, None, None, None))
    monkeypatch.setattr(usable_flag, "read", lambda p=None: type("F", (), {"usable": set()})())
    empty = pd.DataFrame(columns=["utility_id_eia", "state", "name"])
    monkeypatch.setattr(sal, "generate", lambda *a, **k: (empty, empty.assign(reason=[])))
    monkeypatch.setattr(sal, "write", lambda *a, **k: "0" * 64)
    assert sal.main() == 0
    assert sal.DESCRIPTION in capsys.readouterr().out

