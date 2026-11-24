"""Tests for pipeline/analysis/e7_presentation.py on an invented block with a known answer, plus one test that reads the two
stored quantity files. No price is read and nothing is drawn. Each test is written as a check function that takes the function
under test, so the test can also run the check against a deliberately wrong version and see it fail (a break made in the test
process only)."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

GIZMO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("e7_presentation", GIZMO / "pipeline" / "analysis" / "e7_presentation.py")
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)
TOL = 1e-9


def block(statuses=None, partial=False):
    """Four roster hosts. A, B, C retained, D out. exact: A .8, B .6, C .4, D 1.0 gives .6 over the three and .7 over four;
    within_1_year: A .9, B .7, C .5, D 1.0 gives .7 and .775 (stored .775 is exact at 3 decimals)."""
    status = statuses or {"1:AA": "retained", "2:BB": "retained", "3:CC": "retained", "4:DD": "out"}
    ex = {"1:AA": .8, "2:BB": .6, "3:CC": .4, "4:DD": 1.0}
    wi = {"1:AA": .9, "2:BB": .7, "3:CC": .5, "4:DD": 1.0}
    by = {u: {"exact": ex[u], "within_1_year": wi[u], "true_crossing_2_or_more_years_earlier": round(.1 * i, 3),
              "true_crossing_5_or_more_years_earlier": round(.05 * i, 3), "true_crossing_2_or_more_years_later": round(.02 * i, 3),
              "never_reaches_the_threshold": 0.0, "share_of_draws_in_the_design": 0.0 if u == "4:DD" else 1.0}
          for i, u in enumerate(ex)}
    pooled = {s: round(sum(by[u][s] for u in by) / len(by), 3) for s in ep.SHARES}
    d = {"draws_attempted": 10, "draws_computed": 10, "by_host": by, "set_pooled_over_host_draws": pooled}
    return {"partial_timing_run": partial,
            "reference": {"hosts": [{"utility": u, "name": f"n{u}", "crossing": 2015, "status": status[u],
                                     "matches": ["9:ZZ"] if status[u] == "retained" else None} for u in ex]},
            "directions": {"earlier": copy.deepcopy(d), "later": copy.deepcopy(d)}}


def fails(check, wrong):
    """The check passes on the real function and raises AssertionError on the wrong one."""
    check(ep.denominators)
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        check(wrong)


def wrong_roster_only(b):  # a wrong version: ignores the reference list and uses the roster for both figures
    r = ep.denominators(b)
    for d in r["directions"].values():
        for v in d["shares"].values():
            v["over_reference_design_hosts_primary"] = v["over_roster_beside"]
    return r


def check_known(fn):
    r = fn(block())
    e = r["directions"]["earlier"]["shares"]
    assert abs(e["exact"]["over_reference_design_hosts_primary"] - 0.6) < TOL
    assert abs(e["exact"]["over_roster_beside"] - 0.7) < TOL
    assert abs(e["within_1_year"]["over_reference_design_hosts_primary"] - 0.7) < TOL
    assert abs(e["within_1_year"]["over_roster_beside"] - 0.775) < TOL
    assert r["hosts_in_reference_design"] == 3 and r["hosts_in_roster"] == 4
    assert abs(r["directions"]["later"]["shares"]["exact"]["over_reference_design_hosts_primary"] - 0.6) < TOL


def test_known_figures_over_both_denominators():
    fails(check_known, wrong_roster_only)


def test_out_host_is_named_with_its_fields():
    def check(fn):
        out = fn(block())["roster_hosts_not_in_reference_design"]
        assert [o["host_record"]["utility"] for o in out] == ["4:DD"]
        assert out[0]["host_record"]["status"] == "out" and out[0]["host_record"]["name"] == "n4:DD"
        assert out[0]["share_of_draws_in_the_design"] == {"earlier": 0.0, "later": 0.0}
    def wrong(b):
        r = ep.denominators(b)
        r["roster_hosts_not_in_reference_design"] = []
        return r
    fails(check, wrong)


def test_mismatch_with_stored_pooled_figure_raises():
    def check(fn):
        b = block()
        b["directions"]["later"]["set_pooled_over_host_draws"]["exact"] = 0.75   # the roster mean is 0.7
        with pytest.raises(ValueError, match="differs from the stored"):
            fn(b)
        fn(block())                                                              # an unaltered block passes
    def wrong(b):                                                                # a version that silently reconciles
        return {}
    fails(check, wrong)


def test_partial_timing_run_refused():
    def check(fn):
        with pytest.raises(ValueError, match="partial"):
            fn(block(partial=True))
    def wrong(b):
        return {}
    fails(check, wrong)


def test_host_missing_either_way_refused():
    def check(fn):
        b = block()
        del b["directions"]["earlier"]["by_host"]["2:BB"]
        with pytest.raises(ValueError, match="different hosts"):
            fn(b)
        b = block()
        b["reference"]["hosts"].pop()
        with pytest.raises(ValueError, match="different hosts"):
            fn(b)
    def wrong(b):
        return {}
    fails(check, wrong)


def test_unknown_status_refused():
    def check(fn):
        b = block()
        b["reference"]["hosts"][0]["status"] = "maybe"
        with pytest.raises(ValueError, match="unknown status"):
            fn(b)
    def wrong(b):
        return {}
    fails(check, wrong)


def test_input_not_mutated():
    def check(fn):
        b = block()
        before = copy.deepcopy(b)
        fn(b)
        assert b == before
    def wrong(b):
        b["reference"]["hosts"][3]["status"] = "retained"
        return ep.denominators(b)
    fails(check, wrong)


def test_stored_files_agree():
    def check(fn):
        stored = json.loads((GIZMO / "data" / "frozen" / "inventory_run_designs.json").read_text())["E7_every_cohort_utility"]
        written = json.loads((GIZMO / "data" / "frozen" / "e7_reporting_denominator.json").read_text())
        assert written["result"] == fn(stored)
        assert written["result"]["hosts_in_reference_design"] == 36 and written["result"]["hosts_in_roster"] == 41
        e = written["result"]["directions"]["earlier"]["shares"]["exact"]
        assert round(e["over_reference_design_hosts_primary"], 3) == 0.538 and e["stored_set_pooled_over_host_draws"] == 0.558
    def wrong(b):
        r = ep.denominators(b)
        r["hosts_in_roster"] = 40
        return r
    fails(check, wrong)
