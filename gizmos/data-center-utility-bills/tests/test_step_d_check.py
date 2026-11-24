"""Step D's checks (pipeline/facilities/step_d_check.py) on made-up inputs."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.facilities import step_d_check as sc  # noqa: E402


def test_reproduce_says_identical_or_differs(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    df = pd.DataFrame({"x": [1.0, 2.0]})
    for name in sc.INVENTORY_FILES:
        df.to_parquet(a / name)
        df.to_parquet(b / name)
    assert set(sc.reproduce(a, b).values()) == {"identical"}
    pd.DataFrame({"x": [1.0, 2.0000000001]}).to_parquet(b / "facility_year.parquet")
    assert sc.reproduce(a, b)["facility_year.parquet"].startswith("DIFFERS")


def frames():
    snap = pd.DataFrame({"state": ["AA", "AA", "AA"], "utility_id_eia": [1.0, 2.0, 3.0],
                         "utility_assign": ["smallest_polygon", "unique", "verified_by_hand"],
                         "utility_candidates": ["1;4", "2", "3"]}, index=["m", "n", "v"])
    reb = snap.copy()
    reb.loc["m", "utility_id_eia"] = 4.0                              # the map rerun moved it
    return reb, snap


def test_differences_are_explained_only_by_named_sites():
    reb, snap = frames()
    corr = [{"fid": "n", "kind": "date", "earliest": 2010, "latest": 2012, "convention": 2012}]
    ex = sc.explained(reb, snap, {"locations_corrected": {"v": "c"}}, corr, [], {"9:AA"})
    w = ex["by_utility"]
    assert ex["moved_by_the_map"] == ["m"]
    assert any("map rerun" in x for x in w["1:AA"]) and any("map rerun" in x for x in w["4:AA"])
    assert any("coordinate" in x for x in w["3:AA"])
    assert any("after the reference run" in x for x in w["2:AA"])
    assert any("LOAD UNKNOWN" in x for x in w["9:AA"])


def test_a_correction_unchanged_from_the_reference_corrections_explains_nothing():
    reb, snap = frames()
    reb.loc["m", "utility_id_eia"] = 1.0
    corr = [{"fid": "n", "kind": "date", "earliest": 2010, "latest": 2012, "convention": 2012, "why": "a"}]
    ex = sc.explained(reb, snap, {}, corr, [{**corr[0], "why": "b"}], set())
    assert ex["by_utility"] == {} and ex["moved_by_the_map"] == []


def test_the_reference_is_the_s18_attribution_built_on_the_corrections_in_force():
    # 2026-11-19: the reference check reads the exact attribution rerun on the corrections in force (s18), and the
    # guard for corrections entered after the reference run compares against the file that run was built on.
    assert sc.EXACT.name == "expansion-test-2026-11-19-s18.json"
    assert sc.REFERENCE_CORRECTIONS.name == "pass_c_corrections_s17.json"
    assert not hasattr(sc, "S17")


def test_the_margin_flags_a_load_at_the_threshold():
    assert sc._margin(np.array([0.02 * 100]), 100.0, 0.02) == 0.0
    assert sc._margin(np.array([1.0]), 0.0, 0.02) == float("inf")
