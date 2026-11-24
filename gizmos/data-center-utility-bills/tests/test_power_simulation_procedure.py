"""The power and range-width simulation under the selected procedure (step E: C; D-59 rule 4.7). Invented inputs only.

Every range, width, detectable effect, recovery figure and early-years rate comes from the procedure the run names: C by
default (the CR2 t range with Satterthwaite degrees of freedom, the approximate Hotelling test), A only as the labelled run
"figures for the bootstrap as built", written to its own file. C is accepted as "the selected procedure" only on step E's
stage-1 selection of C and stage-2 verdicts both "passed". Prices are read only through read_listed_outcomes.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import estimator as es  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_matching_rules import COOP, FUEL, YEARS, table, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
STATES = ["AA", "AB", "BB", "BC"]
NONE = ps.UnknownLoad.none("invented data: no load-unknown site")


def invented(n_comps=28, seed=0):
    hosts = [(1, "AA", 10_000, COOP), (2, "BB", 12_000, COOP)]
    comps = [(100 + i, STATES[i % 4], 9_500 + 90 * i, COOP) for i in range(n_comps)]
    treated, clean, q, regions, dd = world(hosts, comps)
    q["utility_name"] = "x"
    rng = np.random.default_rng(seed)
    prices = q[ps.KEY + ["year"]].assign(res_price=np.exp(rng.normal(-2, 0.05, len(q))))
    usable = {(u, st, y) for u, st, *_ in hosts + comps for y in YEARS}
    errs = {(1, "AA"): np.array([0, -1, 1]), (2, "BB"): np.array([0, 2])}
    return treated, clean, q, regions, dd, prices, usable, errs


def run(procedure, draws=3, seed=(1, 2), provenance=None, **kw):
    treated, clean, q, regions, dd, prices, usable, errs = invented()
    return ps.run_new_hosts("t", treated, clean, q, regions, FUEL, dd, prices, errs, seed, draws=draws, boot=19, ownership=table([]),
                            usable=usable, gas=GAS, unknown_load=NONE, procedure=procedure, provenance=provenance, **kw)


def a_draw():
    """One assembled draw on the invented design with made-up outcomes and a misdating error on one stand-in."""
    from test_inference_comparison import invented_design
    d, *_ = invented_design(hosts=3, comps=16, cohorts=(2014, 2016))
    rng = np.random.default_rng(4)
    for w in d.windows.values():
        w.y = rng.normal(size=(len(w.keys), ps.T)) * 0.05 + rng.normal(size=(len(w.keys), 1))
    blocks = d.blocks()
    errors = {(blocks[0][0], int(blocks[0][1][0])): -2}
    return d, blocks, errors


# ---- C's numbers are candidates' C, on the same design and outcomes --------------------------------------------------

def test_the_simulation_under_c_equals_candidates_c_run_directly():
    d, blocks, errors = a_draw()
    draw = ps.one_draw(d.windows, blocks, errors, np.random.default_rng(0), boot=19, gas=GAS_ALL(d), taus=(0, 3, 5), procedure="C")
    a = ps.assemble(d.windows, blocks, errors, gas=GAS_ALL(d))
    prob = cd.Problem(a["X"], a["groups"], a["cluster"], combo=ps.headline_combo(a["X"].shape[1]), pre=ps.PRE_IDX)
    cand = cd.CandidateC(prob)
    for name, j in (("exact", 0), ("misdated", 1)):
        for i, pct in enumerate((0, 3, 5)):
            tau = float(np.log1p(pct / 100))
            direct = cand.run(a["y"] + tau * a["paths"][:, j], 0.0, planted=None)
            sim = draw[name][i]
            assert sim["numerical_failure"] is None and direct["failure"] is None
            assert sim["est"] == pytest.approx(direct["estimate"], abs=1e-12)
            assert (sim["lo"], sim["hi"]) == pytest.approx((direct["lo"], direct["hi"]), abs=1e-12)
            assert (sim["pre_p"] < 0.10) == direct["early_rejected"]
            assert (sim["lo"] <= 0 <= sim["hi"]) == direct["covered"]


def GAS_ALL(d):
    return d.gas


def test_c_and_a_consume_the_same_random_numbers_so_both_see_the_same_stand_ins():
    d, blocks, errors = a_draw()
    ra, rc = np.random.default_rng(9), np.random.default_rng(9)
    ps.one_draw(d.windows, blocks, errors, ra, boot=19, gas=d.gas, taus=(0,), procedure="A")
    ps.one_draw(d.windows, blocks, errors, rc, boot=19, gas=d.gas, taus=(0,), procedure="C")
    assert ra.integers(0, 10**9) == rc.integers(0, 10**9)


def test_run_new_hosts_under_c_computes_every_reading_with_c(monkeypatch):
    built = []
    real = cd.CandidateC.__init__

    def spy(self, *a, **k):
        built.append(1)
        real(self, *a, **k)
    monkeypatch.setattr(cd.CandidateC, "__init__", spy)
    monkeypatch.setattr(es.Fit, "summary", lambda *a, **k: pytest.fail("the bootstrap as built was used in a run labelled C"))
    out = run("C", draws=3)
    assert len(built) == 3 and out["procedure"]["name"] == "C"
    assert out["early_years_test"]["statistic"] == ps.PROCEDURE_TEXT["C"]["early_years_test"]
    assert out["bootstrap_replications"] is None and out["nothing_planted"]["analytic_range_covers_zero"] is None
    assert out["early_years_test"]["share_failing_at_the_chi_square_10pct_value"] is None
    assert "selected_procedure" in out["numerical_failures"]


def test_run_size_check_under_c_computes_every_reading_with_c(monkeypatch):
    treated, clean, q, regions, dd, prices, usable, errs = invented()
    monkeypatch.setattr(es.Fit, "summary", lambda *a, **k: pytest.fail("the bootstrap as built was used in a run labelled C"))
    out = ps.run_size_check("t", treated, clean, q, regions, FUEL, dd, (1, 3), datasets=3, boot=19, ownership=table([]), usable=usable,
                            gas=GAS, unknown_load=NONE, procedure="C")
    assert out["procedure"]["name"] == "C" and out["fails_at_the_chi_square_10pct_value"] is None
    assert out["datasets"] == 3 and "selected_procedure" in out["numerical_failures"]


def test_the_labelled_a_run_still_reads_the_bootstrap_as_built():
    out = run("A", draws=2)
    assert out["procedure"]["name"] == "A" and out["bootstrap_replications"] == 19
    assert out["early_years_test"]["statistic"] == ps.PROCEDURE_TEXT["A"]["early_years_test"]
    assert out["early_years_test"]["share_failing_at_the_chi_square_10pct_value"] is not None


def test_the_fingerprint_carries_the_procedure_and_what_it_rests_on():
    c1 = run("C", draws=2, provenance={"procedure": "C", "stage1_sha256": "a", "stage2_sha256": "b"})
    c2 = run("C", draws=2, provenance={"procedure": "C", "stage1_sha256": "a", "stage2_sha256": "c"})
    a = run("A", draws=2, provenance=ps.as_built_provenance())
    shas = {x["fingerprint"]["sha256"] for x in (c1, c2, a)}
    assert len(shas) == 3
    assert c1["procedure_provenance"]["stage2_sha256"] == "b"


# ---- failures stay in every denominator ---------------------------------------------------------------------------

def readings(fail_one: bool):
    base = {"est": 0.0, "se": 0.01, "lo": -0.02, "hi": 0.02, "clusters": 4, "pre_wald": 1.0, "pre_p": 0.5,
            "numerical_failure": None, "analytic_failure": None, "procedure": "C"}
    planted = {**base, "est": 0.06, "lo": 0.03, "hi": 0.09}
    draws = []
    for i in range(10):
        bad = fail_one and i == 0
        z = {**base, "lo": np.nan, "hi": np.nan, "pre_p": np.nan, "numerical_failure": cd.UNDEFINED_DEGREES_OF_FREEDOM,
             "analytic_failure": cd.UNDEFINED_DEGREES_OF_FREEDOM} if bad else base
        p = {**planted, "lo": np.nan, "hi": np.nan, "numerical_failure": cd.UNDEFINED_DEGREES_OF_FREEDOM} if bad else planted
        draws.append({"exact": [z] + [p] * (len(ps.TAUS_PCT) - 1), "misdated": [z] + [p] * (len(ps.TAUS_PCT) - 1)})
    return draws


def test_a_failed_draw_under_c_is_a_miss_a_rejection_and_no_detection_and_is_reported_apart():
    out = ps.read_draws(readings(True), hosts=2, procedure="C")
    assert out["draws"] == 10 and out["rates_include_numerical_failures"]
    assert out["nothing_planted"]["range_covers_zero"] == 0.9
    assert out["early_years_test"]["share_of_flat_histories_failing_at_p_below_0.10"] == 0.1
    assert out["start_years_exact"]["range_entirely_above_zero_by_planted_pct"]["5"] == 0.9
    assert out["numerical_failures"]["selected_procedure"]["count"] == 1
    assert out["numerical_failures"]["selected_procedure"]["by_cause"] == {cd.UNDEFINED_DEGREES_OF_FREEDOM: 1}
    clean = ps.read_draws(readings(False), hosts=2, procedure="C")
    assert clean["nothing_planted"]["range_covers_zero"] == 1.0 and clean["early_years_test"]["share_of_flat_histories_failing_at_p_below_0.10"] == 0.0
    assert clean["numerical_failures"]["selected_procedure"]["count"] == 0                 # reported even when zero (Stop 3)
    assert clean["start_years_exact"]["planted_5pct"]["numerical_failures"]["count"] == 0


def test_c_reading_fails_in_words_when_the_aht_degrees_of_freedom_are_undefined(monkeypatch):
    d, blocks, errors = a_draw()
    monkeypatch.setattr(cd, "aht_degrees_of_freedom", lambda P: 1.5)
    draw = ps.one_draw(d.windows, blocks, errors, np.random.default_rng(0), boot=19, gas=d.gas, taus=(0, 5), procedure="C")
    assert all(r["numerical_failure"] == cd.UNDEFINED_DEGREES_OF_FREEDOM for r in draw["exact"] + draw["misdated"])
    assert all(np.isnan(r["lo"]) for r in draw["exact"])


def test_a_rank_deficient_draw_under_c_fails_every_reading():
    from test_gas_share import make
    from test_matching_rules import ladder
    d = make([(1, "AA", 10_000, COOP)], ladder(10, 12, state="BB"))
    draw = ps.one_draw(d.windows, d.blocks(), {}, np.random.default_rng(1), boot=9, gas=GAS, taus=(0, 5), procedure="C")
    assert [r["numerical_failure"] for r in draw["exact"] + draw["misdated"]] == [es.RANK_DEFICIENT] * 4


# ---- the selected procedure is accepted only as step E left it ----------------------------------------------------

def stage_files(tmp_path, selected="C", candidate="C", range_v="passed", early_v="passed", fp1="f", fp2="f"):
    (tmp_path / ps.STAGE1_FILE).write_text(json.dumps({"selection": {"selected": selected}, "fingerprint": {"sha256": fp1}}))
    (tmp_path / ps.STAGE2_FILE).write_text(json.dumps({"candidate": candidate, "range": {"verdict": range_v},
                                                       "early_years_test": {"verdict": early_v}, "fingerprint": {"sha256": fp2},
                                                       "datasets_per_process": 20000}))


def test_the_selected_procedure_rests_on_both_stage_files_with_their_hashes(tmp_path):
    stage_files(tmp_path)
    p = ps.selected_procedure(tmp_path)
    import hashlib
    assert p["procedure"] == "C" and p["stage2_verdicts"] == {"range": "passed", "early_years_test": "passed"}
    assert p["stage1_sha256"] == hashlib.sha256((tmp_path / ps.STAGE1_FILE).read_bytes()).hexdigest()
    assert p["stage2_sha256"] == hashlib.sha256((tmp_path / ps.STAGE2_FILE).read_bytes()).hexdigest()
    assert p["comparison_fingerprint"] == "f" and p["validated_datasets_per_process"] == 20000


@pytest.mark.parametrize("kw, words", [
    ({"selected": "B"}, "stage 1 selected"),
    ({"selected": None}, "stage 1 selected"),
    ({"candidate": "B"}, "stage 2 validated"),
    ({"range_v": "observed excess rejection"}, "not validated on both rates"),
    ({"early_v": "insufficient precision to certify"}, "not validated on both rates"),
    ({"fp2": "g"}, "different comparison fingerprints"),
])
def test_the_selected_procedure_is_refused_unless_stage_1_chose_c_and_stage_2_passed_both(tmp_path, kw, words):
    stage_files(tmp_path, **kw)
    with pytest.raises(SystemExit, match=words):
        ps.selected_procedure(tmp_path)


def test_without_the_stage_files_the_selected_procedure_stops_in_words(tmp_path):
    with pytest.raises(SystemExit, match="--procedure=A"):
        ps.selected_procedure(tmp_path)


def test_main_checks_the_selected_procedure_before_reading_anything(tmp_path, monkeypatch):
    stage_files(tmp_path, early_v="observed excess rejection")
    monkeypatch.setattr(ps, "FROZEN", tmp_path)
    monkeypatch.setattr(ps.panel, "load_quantities", lambda *a, **k: pytest.fail("nothing may be read before the procedure is settled"))
    monkeypatch.setattr(ps.panel, "load_outcomes", lambda *a, **k: pytest.fail("no price may be read"))
    monkeypatch.setattr(sys, "argv", ["power_simulation.py"])
    with pytest.raises(SystemExit, match="not validated"):
        ps.main()


def test_procedure_from_argv():
    assert ps.procedure_from_argv([]) == "C" and ps.procedure_from_argv(["x", "--procedure=A"]) == "A"
    with pytest.raises(SystemExit):
        ps.procedure_from_argv(["--procedure=B"])
    assert inspect.signature(ps.run_new_hosts).parameters["procedure"].default == "C"
    assert inspect.signature(ps.run_size_check).parameters["procedure"].default == "C"


# ---- the labelled A run never writes over the headline file -----------------------------------------------------

def test_the_a_run_writes_its_own_file_and_never_the_headline(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "FROZEN", tmp_path)
    head = ps.output_path("power_simulation.json", ps.HEADLINE_RULES)
    a = ps.output_path("power_simulation.json", ps.HEADLINE_RULES, "A")
    assert head.name == "power_simulation.json" and a.name == "power_simulation_figures_for_the_bootstrap_as_built.json"
    assert ps.output_path("power_simulation.json", ps.NO_FUEL_CONTROL, "A").name == \
        "power_simulation_sensitivity_no_fuel_control_figures_for_the_bootstrap_as_built.json"
    head.write_text("{}")
    written = ps.write_report({"procedure": ps.as_built_provenance()}, ps.HEADLINE_RULES, "A")
    assert written == a and head.read_text() == "{}"
    with pytest.raises(RuntimeError, match="being written as"):
        ps.write_report({"procedure": ps.as_built_provenance()}, ps.HEADLINE_RULES, "C")
    assert ps.output_path("inference_check.json", ps.HEADLINE_RULES).name == "inference_check.json"     # job U's path unchanged


def test_main_and_run_added_write_through_the_procedure():
    src = inspect.getsource(ps.main)
    assert "write_report(report, rules, procedure)" in src and "procedure_from_argv(sys.argv)" in src
    assert src.index("selected_procedure()") < src.index("panel.load_quantities()")
    assert "write_report(report, rules, AS_BUILT)" in inspect.getsource(ps.run_added)
    assert ".write_text(" not in src


# ---- who is read stays as it was ---------------------------------------------------------------------------------

def test_prices_are_read_only_through_read_listed_outcomes(monkeypatch):
    src = inspect.getsource(ps)
    code = [ln for ln in src.split("\n") if "load_outcomes(" in ln and not ln.lstrip().startswith(("#", "(", "(c)"))]
    assert len(code) == 1 and "return panel.load_outcomes" in code[0]
    assert "read_listed_outcomes(clean)" in inspect.getsource(ps.main) and "restrict_to_access_list(clean)" in inspect.getsource(ps.main)
    monkeypatch.setattr(ps.panel, "load_outcomes", lambda *a, **k: pytest.fail("no price may be read by the simulation's workers"))
    run("C", draws=1)


def test_the_second_number_is_labelled_as_not_under_the_selected_procedure():
    from test_unknown_load import second_number_world
    q, dose, regions, clean = second_number_world()
    rng = np.random.default_rng(0)
    prices = q[ps.KEY + ["year"]].assign(res_price=np.exp(rng.normal(-2, 0.05, len(q))))
    out = ps.run_second_number(q, dose, clean, regions, prices, (1, 2), draws=2, boot=9, unknown_load=NONE)
    for name in ("long_difference", "panel"):
        assert out[name]["inference"].startswith("not under the selected procedure: the comparison did not cover this estimator")
