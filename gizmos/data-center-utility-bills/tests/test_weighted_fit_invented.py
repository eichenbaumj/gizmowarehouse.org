"""The customer-weighted fit (pipeline/analysis/weighted_fit.py) on invented quantities and invented outcomes only.

The invented world is tests/test_outcome_analysis_invented.py's: four hosts (cohorts 2013, 2015, 2015, 2017) in four
states, forty comparison utilities over eight states, built by design.build with the gas-share control. The planted
customers put the hosts' nominal shares at exactly 10%, 20%, 30% and 40%.

The planted answers:
- With every weight equal, the weighted fit IS the kernel's unweighted fit: the same point estimate and event-year
  coefficients as outcome_analysis.estimate, the same implied weights as inference_check.implied_weights, and the same
  host sums as the kernel's host_headline_weights, each to 1e-10.
- A heterogeneous effect: host h's price moves by its own level L_h in event years 2 and 3 only (0.01, 0.03, 0.05, 0.07)
  on top of unit effects, calendar-year effects and 0.02 x heating degree days, with no noise. The fixed effects take the
  unit and year effects and the degree-day column is a regressor, so each fit returns exactly the sum over hosts of its
  effective contribution times L_h: the weighted fit with the weighted contributions, the kernel with the unweighted ones.
  The contributions are computed from the regressors and the weights alone, before the outcome is drawn, so the two
  estimates and their difference are known in advance (tolerance 1e-10).
- An absorbed host (in its matches' region only in its reference year): its effective contribution is zero under any
  weights while its nominal share is 40%. The nominal share and the effective contribution differ by a known amount.
No file under data/ is read.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import weighted_fit as wf  # noqa: E402
from test_outcome_analysis_invented import COMPS, HDD_BETA, HOSTS, KEY, ONE_STATE_COMPS, ONE_STATE_HOSTS, YEARS, make  # noqa: E402

TOL = 1e-10
CUSTOMERS = {(1, "AA"): 100.0, (2, "AC"): 200.0, (3, "BA"): 300.0, (4, "BC"): 400.0}
LEVELS = {(1, "AA"): 0.01, (2, "AC"): 0.03, (3, "BA"): 0.05, (4, "BC"): 0.07}
def ABSORBED_REGION(key, year):          # noqa: N802  host 4 meets its matches' region only in its reference year, 2014
    return "East" if key == (4, "BC") and year != 2014 else "West"


def customers_frame(q, planted=CUSTOMERS):
    """The quantities frame with the hosts' residential customers set to `planted` in every year."""
    f = q[KEY + ["year", "res_customers"]].copy()
    for (u, st), v in planted.items():
        f.loc[(f.utility_id_eia == u) & (f.state == st), "res_customers"] = v
    return f


def outcome(dd, levels=LEVELS, noise=0.0, seed=7, hosts=HOSTS, comps=COMPS):
    rng = np.random.default_rng(seed)
    year_fx = dict(zip(YEARS, rng.normal(0, 0.05, len(YEARS))))
    cohort = {(h[0], h[1]): h[4] for h in hosts}
    rows = []
    for u, st, *_ in [h[:4] for h in hosts] + list(comps):
        a = rng.normal(0, 0.2)
        for y in YEARS:
            v = a + year_fx[y] + HDD_BETA * float(dd.hdd[(st, y)]) + noise * rng.normal()
            g = cohort.get((u, st))
            if g is not None and y - g in ps.HEADLINE:
                v += levels[(u, st)]
            rows.append((u, st, y, v))
    return pd.DataFrame(rows, columns=KEY + ["year", "value"])


@pytest.fixture(scope="module")
def built():
    return make()


# ---- equal weights: the kernel's fit, exactly -------------------------------------------------------------------------

@pytest.mark.parametrize("scale", [1.0, 5_000.0])
def test_equal_weights_return_the_kernels_unweighted_fit_to_1e_10(built, scale):
    d, q, regions, dd = built
    y = oa.outcome_vector(d, outcome(dd, noise=0.01), "value")
    k = oa.estimate(d, y, validated_design=False)
    w = {oa._host_label(h): scale for h in d.hosts.key}
    r = wf.weighted_fit(d, y, w)
    assert r["estimated"] and abs(r["estimate_log_points"] - k["headline"]["log_points"]) < TOL
    assert all(abs(r["event_year_coefficients"][e] - k["event_year_coefficients"][e]) < TOL for e in k["event_year_coefficients"])
    ec = wf.effective_contributions(d, w)
    iw = ic.implied_weights(oa.stackable(d), ps.GAS_SHARE).weight.to_numpy()
    assert np.abs(ec["omega"] - iw).max() < TOL
    assert all(abs(ec["by_host"][h] - k["host_headline_weights"][h]) < TOL for h in k["host_headline_weights"])
    assert all(abs(ec["by_host"][h] - v) < TOL for h, v in oa.host_weights(d, ps.GAS_SHARE).items())


# ---- the heterogeneous planted effect ---------------------------------------------------------------------------------

def check_planted(d, q, dd):
    w = wf.customer_weights(d, customers_frame(q))
    eff_w = wf.effective_contributions(d, w)["by_host"]                       # before the outcome is drawn
    eff_u = wf.effective_contributions(d, {h: 1.0 for h in w})["by_host"]
    lv = {oa._host_label(k): v for k, v in LEVELS.items()}
    expect_w = sum(eff_w[h] * lv[h] for h in lv)
    expect_u = sum(eff_u[h] * lv[h] for h in lv)
    y = oa.outcome_vector(d, outcome(dd), "value")
    r = wf.weighted_fit(d, y, w)
    k = oa.estimate(d, y, validated_design=False)
    assert abs(r["estimate_log_points"] - expect_w) < TOL
    assert abs(k["headline"]["log_points"] - expect_u) < TOL
    assert abs((r["estimate_log_points"] - k["headline"]["log_points"]) - (expect_w - expect_u)) < TOL
    assert abs(expect_w - expect_u) > 1e-3                                    # the weights matter here
    assert abs(r["estimate_as_omega_times_y"] - r["estimate_log_points"]) < TOL
    return r


def test_a_heterogeneous_effect_moves_the_weighted_and_unweighted_fits_by_the_known_amounts(built):
    d, q, regions, dd = built
    r = check_planted(d, q, dd)
    assert r["nominal_customer_weight_shares"] == pytest.approx({"1:AA": 0.1, "2:AC": 0.2, "3:BA": 0.3, "4:BC": 0.4}, abs=1e-15)
    assert abs(r["effective_contributions_sum"] - 1.0) < TOL
    assert r["range_90_log_points"] is None and r["label"] == wf.DESCRIPTIVE_LABEL and "descriptive" in r["label"]


def test_the_check_fails_when_the_weights_are_dropped(built, monkeypatch):
    """A deliberate break in the test process: every row weight set to one inside the fit. The weighted fit then returns
    the unweighted estimate and the planted assertions fail."""
    d, q, regions, dd = built
    real = wf.row_weights
    monkeypatch.setattr(wf, "row_weights", lambda d_, w_: np.ones_like(real(d_, w_)))
    with pytest.raises(AssertionError):
        check_planted(d, q, dd)


def test_with_weights_proportional_to_the_planted_customers_the_estimate_differs_from_the_kernel():
    d, q, regions, dd = make()
    y = oa.outcome_vector(d, outcome(dd), "value")
    w = wf.customer_weights(d, customers_frame(q))
    assert abs(wf.weighted_fit(d, y, w)["estimate_log_points"] - oa.estimate(d, y, validated_design=False)["headline"]["log_points"]) > 1e-3


# ---- nominal shares against effective contributions -------------------------------------------------------------------

def test_an_absorbed_host_has_a_nominal_share_and_no_effective_contribution():
    d, q, regions, dd = make(region=ABSORBED_REGION)
    w = wf.customer_weights(d, customers_frame(q))
    nominal = wf.nominal_shares(w)
    eff = wf.effective_contributions(d, w)["by_host"]
    assert nominal["4:BC"] == pytest.approx(0.4, abs=1e-15) and abs(eff["4:BC"]) < 1e-9
    assert abs(sum(eff.values()) - 1.0) < TOL
    r = wf.weighted_fit(d, oa.outcome_vector(d, outcome(dd), "value"), w)
    assert r["nominal_customer_weight_shares"]["4:BC"] == pytest.approx(0.4, abs=1e-15)
    assert abs(r["effective_contributions_to_the_weighted_headline"]["4:BC"]) < 1e-9
    # the two readings are kept under their own names and never merged
    assert "nominal_customer_weight_shares" in r and "effective_contributions_to_the_weighted_headline" in r
    assert r["nominal_definition"] != r["effective_definition"]


# ---- failures in words -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value,words", [(None, "no row"), (np.nan, "not finite"), (0.0, "not above zero")])
def test_a_host_with_no_usable_customer_count_stops_in_words(built, value, words):
    d, q, regions, dd = built
    f = customers_frame(q)
    sel = (f.utility_id_eia == 3) & (f.state == "BA") & (f.year == 2015 + ps.REF)
    f = f[~sel] if value is None else f.assign(res_customers=np.where(sel, value, f.res_customers))
    with pytest.raises(wf.CustomerWeightMissing, match=words) as e:
        wf.customer_weights(d, f)
    assert "3:BA, reference year 2012" in str(e.value)


def test_a_missing_weight_is_a_failure_in_words_and_no_estimate(built):
    d, q, regions, dd = built
    w = wf.customer_weights(d, customers_frame(q))
    w.pop("2:AC")
    r = wf.weighted_fit(d, oa.outcome_vector(d, outcome(dd), "value"), w)
    assert r["estimated"] is False and "2:AC" in r["failure_in_words"] and r["estimate_log_points"] != r["estimate_log_points"]


def test_the_kernels_alignment_guard_holds(built):
    d, q, regions, dd = built
    other, *_ = make(hosts=HOSTS[:3])
    y_other = oa.outcome_vector(other, outcome(dd), "value")
    w = wf.customer_weights(d, customers_frame(q))
    with pytest.raises(oa.OutcomeMisaligned):
        wf.weighted_fit(d, y_other, w)
    y = oa.outcome_vector(d, outcome(dd), "value")
    assert wf.weighted_fit(d, y, w)["outcome_alignment"] == oa.ALIGNMENT_CHECKED
    assert wf.weighted_fit(d, np.asarray(y) + 0.0, w)["outcome_alignment"] == oa.ALIGNMENT_LENGTH_ONLY


def test_a_rank_deficient_design_gives_no_estimate_and_says_why():
    d, q, regions, dd = make(hosts=ONE_STATE_HOSTS, comps=ONE_STATE_COMPS)
    y = oa.outcome_vector(d, outcome(dd, levels={(1, "AA"): 0.0, (2, "AA"): 0.0}, hosts=ONE_STATE_HOSTS,
                                     comps=ONE_STATE_COMPS), "value")
    r = wf.weighted_fit(d, y, {"1:AA": 1.0, "2:AA": 2.0})
    assert r["estimated"] is False and "RankDeficient" in r["failure_in_words"] and r["range_90_log_points"] is None


def test_the_validated_path_is_not_touched_and_no_file_is_read():
    tree = ast.parse(Path(wf.__file__).read_text())
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not {"load_outcomes", "read_listed_outcomes", "read_parquet", "read_csv"} & calls
    src = Path(wf.__file__).read_text()
    assert "data/blind" not in src and "availability" not in src
    assert "ic.fixed_parts(oa.stackable(d)" in src          # the kernel's own construction, called
