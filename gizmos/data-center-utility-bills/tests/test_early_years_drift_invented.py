"""Exercise 4a's runner (pipeline/analysis/early_years_drift.py) on INVENTED designs only.

The invented designs are the inference comparison's own (tests/test_inference_comparison.invented_design). Nothing here
builds the real design, reads anything under data/, or writes under data/frozen: every output path is in tmp_path. No
rate computed here bears on anything; the designs are made up.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import early_years_drift as edd  # noqa: E402
from pipeline.analysis import estimator  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import inference_comparison as icp  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_inference_comparison import invented_design  # noqa: E402
from test_matching_rules import table  # noqa: E402

LARGE = 0.10           # a drift of 10% a year, ten times the exercise's, on an invented design with sd 0.03 noise
NEARLY_EVERY = 0.95    # tolerance for "detected in nearly every dataset": at least 95% of the datasets
EXACT = 1e-10          # numerical tolerance for identities that hold in exact arithmetic


def invented_inputs(hosts=3, comps=16, cohorts=(2014, 2016)):
    """The tuple inference_comparison.real_design returns, on an invented design."""
    d, regions, q, usable = invented_design(hosts=hosts, comps=comps, cohorts=cohorts)
    return d, regions, q, table([]), None, "ownership only (test)", ps.HEADLINE_RULES, usable


@pytest.fixture(scope="module")
def world():
    inputs = invented_inputs()
    d, regions, q, ownership, suppliers, mode, rules, usable = inputs
    built = edd.build(d, regions, q, ownership, suppliers, mode, rules)
    return {"inputs": inputs, "d": d, "ctx": built["ctx"], "quantities": built["quantities"]}


# ================================================================================================================
# The constants and the planted vector
# ================================================================================================================

def test_the_constants_are_the_specifications():
    assert edd.SEED == 20261206 and edd.DRIFT == 0.01 and edd.DATASETS == 2000 and edd.BLOCK == 25
    assert edd.PROCESS_INDEX == {"G0_as_in_D38": 0, "G6_all_of_it": 6}
    assert edd.REQUIRED_DESIGN_INPUTS == "b8515c35cba1" and edd.CANDIDATE == "C" and edd.MAX_WORKERS == 6
    assert edd.HEADLINE_MULTIPLIER == 5.5
    assert edd.OUT.relative_to(edd.ROOT).as_posix() == "data/frozen/early_years_drift_selected_procedure.json"
    from pipeline.analysis import design as dsg
    assert edd.CODE_FILES == dsg.CODE_FILES + icp.OWN_FILES + ("pipeline/analysis/early_years_drift.py",)


def test_the_generator_is_the_comparisons_data_stream_layout(world):
    for p, k in ((0, 0), (6, 1999), (6, 7)):
        a = edd.generator(p, k).normal(size=5)
        b = icp.streams(edd.SEED, p, k)[0].normal(size=5)
        assert np.array_equal(a, b)
    assert not np.array_equal(edd.generator(0, 1).normal(size=5), edd.generator(6, 1).normal(size=5))


def test_trend_is_the_host_indicator_times_years_past_the_reference_year(world):
    d, trend = world["d"], world["ctx"]["trend"]
    want, i = np.zeros_like(trend), 0
    for g, tr, comp in d.blocks():
        for j in range(len(tr) + len(comp)):
            for t in range(ps.T):
                want[i] = (t - ps.PRE - ps.REF) if j < len(tr) else 0.0
                i += 1
    assert i == len(trend) and np.array_equal(trend, want)
    assert np.array_equal(ic.TREND_PATH, np.array([e - ps.REF for e in ps.EVENT_TIMES], dtype=float))


def test_planting_on_the_outcome_is_d49s_path_argument(world):
    """y + d * trend read directly equals estimator.Fit's outcome under path 0 at size d (D-49's way of planting)."""
    ctx, d = world["ctx"], 0.01
    P, _ = icp.draw(0, edd.generator(0, 3), ctx)
    y = P[ctx["obs_unit"], ctx["obs_year"]]
    pr = ctx["problem"]
    via_path = estimator.Fit(y, pr.X, pr.groups, pr.cluster, ctx["trend"][:, None], projection=pr.projection)
    direct = estimator.Fit(y + d * ctx["trend"], pr.X, pr.groups, pr.cluster, projection=pr.projection)
    assert via_path.coef(path=0, tau=d) == pytest.approx(direct.coef(), abs=EXACT)
    assert via_path.vcov(path=0, tau=d) == pytest.approx(direct.vcov(), abs=EXACT)
    c = ctx["candidates"]["C"].run(y + d * ctx["trend"], 0.0, planted=None)
    assert c["estimate"] == pytest.approx(float(pr.combo @ via_path.coef(path=0, tau=d)), abs=EXACT)


def test_the_design_inputs_hash_is_outcome_analysiss(world):
    d, *_, rules, usable = world["inputs"]
    assert edd.design_inputs_hash(d, rules, usable) == oa.design_hashes(d, usable, rules.fuel_control)["design_inputs"]


# ================================================================================================================
# (1) a planted drift of zero gives the flat reading exactly
# ================================================================================================================

def test_1_a_drift_of_zero_gives_exactly_the_flat_reading(world):
    ctx = world["ctx"]
    for p in (0, 6):
        for k in range(6):
            r = edd.one_dataset(p, k, ctx, drift=0.0)
            assert json.dumps(r["drift"], sort_keys=True) == json.dumps(r["flat"], sort_keys=True)
    recs = [edd.one_dataset(0, k, ctx, drift=0.0) for k in range(20)]
    s = edd.summarise_process(recs, drift=0.0)
    flat = s["mechanics_reading_not_a_validation_figure_same_datasets_with_nothing_planted"]
    ordinary = sum(r["flat"]["failure"] is None and r["flat"]["early_rejected"] is True for r in recs)
    assert s["early_years_test_detects_the_drift"]["count"] == ordinary
    assert flat["early_years_test_rejects_a_flat_history"]["count"] == sum(r["flat"]["reject"] for r in recs)


# ================================================================================================================
# (2) a large drift is detected in nearly every dataset
# ================================================================================================================

def wide_inputs(n_states=16, hosts=8, comps=48, cohorts=(2014, 2016), seed=3):
    """invented_design's construction on more states. On invented_design's six states the approximate Hotelling test has
    eta near 2.2, so its F has about 0.2 denominator degrees of freedom and fails at p below 0.10 for no drift however
    large (the agent's reading, checked in a scratch run). Sixteen states give eleven clusters and eta near 7."""
    import pandas as pd
    from pipeline.analysis import design
    from test_matching_rules import COOP
    years = list(range(2001, 2026))
    states = [f"S{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(n_states)]
    fuel = {st: i % 3 for i, st in enumerate(states)}
    gas = {st: 0.05 + 0.6 * i / n_states for i, st in enumerate(states)}
    hs = [(1 + i, states[i % n_states], 10_000 + 40 * i, COOP, cohorts[i % len(cohorts)]) for i in range(hosts)]
    cs = [(100 + i, states[(i + 1) % n_states], 10_050 + 60 * i, COOP, None) for i in range(comps)]
    units = hs + cs
    q = pd.DataFrame([(u, st, y, own, size, 1.0, True) for u, st, size, own, _ in units for y in years],
                     columns=ps.KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    q["utility_name"] = [f"U{u}" for u in q.utility_id_eia]
    regions = pd.DataFrame([(u, st, y, "West") for u, st, *_ in units for y in years], columns=ps.KEY + ["year", "region"])
    rng = np.random.default_rng(seed)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in states for y in years],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    treated = pd.DataFrame({"utility_id_eia": [h[0] for h in hs], "state": [h[1] for h in hs], "cohort": [h[4] for h in hs]})
    clean = pd.DataFrame([(u, st) for u, st, *_ in cs], columns=ps.KEY)
    usable = {(u, st, y) for u, st, *_ in units for y in years}
    d = design.build_with_rules(treated, clean, q, regions, fuel, dd, ps.HEADLINE_RULES, ownership=table([]), usable=usable,
                                gas=gas, unknown_load=ps.UnknownLoad.none("invented data: no load-unknown site"))
    return d, regions, q, table([]), None, "ownership only (test)", ps.HEADLINE_RULES, usable


@pytest.fixture(scope="module")
def wide():
    return edd.build(*wide_inputs()[:7])["ctx"]


def test_2_a_large_drift_is_detected_in_nearly_every_dataset(wide):
    ctx = wide
    assert ctx["candidates"]["C"].eta > 5 and ctx["candidates"]["C"].p.G >= 10
    n = 40
    for p in (0, 6):
        recs = [edd.one_dataset(p, k, ctx, drift=LARGE) for k in range(n)]
        s = edd.summarise_process(recs, drift=LARGE)["early_years_test_detects_the_drift"]
        assert s["count"] >= NEARLY_EVERY * n, (p, s)
        assert s["datasets"] == n


# ================================================================================================================
# (3) a dataset that fails numerically stays in the denominator, by cause, as no detection
# ================================================================================================================

def test_3_a_numerical_failure_is_counted_by_cause_and_is_no_detection(wide):
    ctx = wide
    good = [edd.one_dataset(0, k, ctx, drift=LARGE) for k in range(5)]
    broken_trend = ctx["trend"].copy()
    broken_trend[np.flatnonzero(broken_trend)[0]] = np.nan          # an invented non-finite planted outcome
    bad = edd.one_dataset(0, 5, {**ctx, "trend": broken_trend}, drift=LARGE)
    assert bad["drift"]["failure"]["cause"] == cd.NON_FINITE_OUTCOME and bad["flat"]["failure"] is None
    s = edd.summarise_process(good + [bad], drift=LARGE)
    det = s["early_years_test_detects_the_drift"]
    assert det["datasets"] == 6 and s["datasets"] == 6                               # kept in the denominator
    assert det["count"] == sum(edd.detected(r["drift"]) for r in good) == 5 and not edd.detected(bad["drift"])
    assert s["numerical_failures_under_the_drift_counted_as_no_detection"] == {
        "count": 1, "causes": {cd.NON_FINITE_OUTCOME: 1}, "where": {"fit": 1}}
    assert s["mean_headline_estimate_with_the_drift_planted"]["datasets_used"] == 5


def test_3_a_failure_is_never_a_detection_even_if_a_stand_in_says_the_test_failed():
    """A stand-in candidate's record with a failure and early_rejected True: still no detection."""
    stand_in = {"estimate": 0.2, "early_rejected": True, "failure": {"cause": cd.SINGULAR_WALD_VARIANCE,
                                                                      "where": "early_years_test", "detail": ""}, "reject": True}
    ok = {"estimate": 0.2, "early_rejected": True, "failure": None, "reject": True}
    assert edd.detected(stand_in) is False and edd.detected(ok) is True
    recs = [{"process": "G0_as_in_D38", "p": 0, "k": i, "flat": ok, "drift": r} for i, r in enumerate([ok, stand_in, ok, ok])]
    s = edd.summarise_process(recs)
    assert s["early_years_test_detects_the_drift"]["count"] == 3 and s["early_years_test_detects_the_drift"]["datasets"] == 4
    assert s["numerical_failures_under_the_drift_counted_as_no_detection"]["causes"] == {cd.SINGULAR_WALD_VARIANCE: 1}
    assert s["mean_headline_estimate_with_the_drift_planted"]["datasets_used"] == 3


# ================================================================================================================
# (4) the drift moves the headline by exactly 5.5 times its yearly size
# ================================================================================================================

def test_4_the_drift_moves_the_headline_by_five_and_a_half_times_its_size(world):
    ctx = world["ctx"]
    for p in (0, 6):
        for k in range(8):
            for size in (0.01, 0.003, LARGE):
                r = edd.one_dataset(p, k, ctx, drift=size)
                assert r["drift"]["estimate"] - r["flat"]["estimate"] == pytest.approx(5.5 * size, abs=EXACT)
    recs = [edd.one_dataset(6, k, ctx) for k in range(10)]
    s = edd.summarise_process(recs)
    m_d = s["mean_headline_estimate_with_the_drift_planted"]["log_points"]
    m_f = s["mechanics_reading_not_a_validation_figure_same_datasets_with_nothing_planted"]["mean_headline_estimate"]["log_points"]
    assert m_d - m_f == pytest.approx(0.055, abs=EXACT)
    assert s["bias_the_drift_puts_in_the_headline_by_construction"]["log_points"] == pytest.approx(0.055, abs=1e-15)


# ================================================================================================================
# (5) a dataset's numbers do not depend on the block or the worker count
# ================================================================================================================

def test_5_numbers_do_not_depend_on_block_or_workers(world):
    ctx = world["ctx"]
    dump = lambda r: json.dumps(r, sort_keys=True, default=str)  # noqa: E731
    one = edd.run_all(ctx, 5, workers=1, block=25)
    other = edd.run_all(ctx, 5, workers=2, block=2)
    assert dump(one) == dump(other)
    assert [r["k"] for r in one["G6_all_of_it"]] == list(range(5))
    assert dump(one["G6_all_of_it"][3]) == dump(edd.one_dataset(6, 3, ctx))           # alone, outside any block
    assert edd.plan_blocks(60, 25) == [(0, 0, 25), (0, 25, 50), (0, 50, 60), (6, 0, 25), (6, 25, 50), (6, 50, 60)]


# ================================================================================================================
# (6) the reading rule's three outcomes
# ================================================================================================================

@pytest.mark.parametrize("g0, g6, want", [
    (0.30, 0.45, edd.ADDED), (0.4995, 0.0, edd.ADDED),
    (0.50, 0.90, edd.NOT_ADDED), (0.80, 0.50, edd.NOT_ADDED),
    (0.49, 0.50, edd.SPLIT), (0.70, 0.20, edd.SPLIT)])
def test_6_the_reading_rule_has_three_outcomes_and_the_split_is_never_a_boolean(g0, g6, want):
    got = edd.reading_rule(g0, g6)
    assert got == want and isinstance(got, str) and not isinstance(got, bool)
    assert len({edd.ADDED, edd.NOT_ADDED, edd.SPLIT}) == 3 and set(edd.RULE_WORDS) == {edd.ADDED, edd.NOT_ADDED, edd.SPLIT}
    assert "chooses no rule" in edd.RULE_WORDS[edd.SPLIT]


# ================================================================================================================
# (7) main stops in words on another design and refuses an existing output
# ================================================================================================================

def test_7_main_stops_in_words_on_a_design_inputs_hash_other_than_the_required_one(world, tmp_path, monkeypatch, capsys):
    out = tmp_path / "early_years_drift_selected_procedure.json"
    drawn = []
    monkeypatch.setattr(edd, "run_all", lambda *a, **k: drawn.append(1))
    assert edd.main([], out=out, inputs_from=lambda: world["inputs"]) == 2
    err = capsys.readouterr().err
    assert "b8515c35cba1" in err and "stopping before any dataset is drawn" in err
    assert not out.exists() and not drawn


def test_7_main_refuses_when_the_output_exists_before_building_anything(tmp_path, capsys):
    out = tmp_path / "early_years_drift_selected_procedure.json"
    out.write_text("{}\n")

    def never():
        raise AssertionError("the design was built although the output exists")
    assert edd.main([], out=out, inputs_from=never) == 2
    assert "exists" in capsys.readouterr().err and out.read_text() == "{}\n"


def test_7_one_run_on_an_invented_design_writes_once_and_then_refuses(world, tmp_path):
    out = tmp_path / "early_years_drift_selected_procedure.json"
    d, *_, rules, usable = world["inputs"]
    h = edd.design_inputs_hash(d, rules, usable)
    r = edd.execute(out, world["inputs"], workers=1, datasets=4, required=h[:12])
    j = json.loads(out.read_text())
    assert j["seed"] == 20261206 and j["datasets_per_process"] == 4 and j["design_inputs_sha256"] == h
    assert set(j["by_process"]) == {"G0_as_in_D38", "G6_all_of_it"}
    assert j["reading_rule"]["outcome"] in (edd.ADDED, edd.NOT_ADDED, edd.SPLIT)
    assert j["fingerprint"]["sha256"] == r["fingerprint"]["sha256"] and "D-113" in j["what_this_is"]
    assert j["specification_sha256"] == edd.sha256_file(edd.ROOT / edd.SPEC)
    assert set(j["fingerprint"]["of"]) >= {"design_inputs", "code_version", "seeds"}
    assert list(json.loads(json.dumps(r["fingerprint"]))["of"]) == list(j["fingerprint"]["of"])
    with pytest.raises(icp.Refused, match="never extended or rerun"):
        edd.execute(out, world["inputs"], workers=1, datasets=4, required=h[:12])


# ================================================================================================================
# (8) a source scan: no stage driver, no blind path, no interim write
# ================================================================================================================

FORBIDDEN_CALLS = {"stage1", "stage2", "run_blocks", "benchmark", "benchmark_timings", "write_budget", "load_outcomes",
                   "read_listed_outcomes", "run_candidates"}


def source_problems(text: str) -> list:
    tree = ast.parse(text)
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    bad = sorted(names & FORBIDDEN_CALLS)
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    bad += [s for s in strings if "blind" in s.lower() or "interim" in s.lower() or "availability" in s.lower()]
    bad += [n for n in names if n in ("INTERIM",)]
    return bad


def test_8_the_module_names_no_stage_function_and_no_protected_path():
    text = (edd.ROOT / edd.THIS_FILE).read_text()
    assert source_problems(text) == []
    assert "blind" not in text.lower()
