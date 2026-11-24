"""The design-weights driver (pipeline/analysis/design_weights.py), on invented designs only.

It must write the rows inference_check.implied_weights gives, in the columns and formatting inference_check.main uses,
report a rank-deficient set in words with no rows, and touch no file but its CSV and its sidecar: never
inference_check.json or second_number_leverage.csv, which hold preserved results.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design_weights as dw  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from test_gas_share import make, mixed  # noqa: E402
from test_matching_rules import COOP, ladder  # noqa: E402

COLUMNS = ["block_host", "cohort", "utility", "is_host", "event_year", "weight", "set"]


def one_host():
    return make([(1, "AA", 10_000, COOP)], mixed(10, 12))


def two_hosts():
    return make([(1, "AA", 10_000, COOP), (2, "AB", 10_400, COOP)], mixed(10, 16))


def rank_deficient():
    return make([(1, "AA", 10_000, COOP)], ladder(10, 12, state="BB"))      # the gas columns leave the event times unidentified


def as_inference_check_main_writes(frames: list) -> pd.DataFrame:
    """inference_check.main's lines 510-513, restated: keys as "id:state", the weight rounded to 8 places."""
    w = pd.concat(frames, ignore_index=True)
    w["block_host"] = [f"{k[0]}:{k[1]}" for k in w.block_host]
    w["utility"] = [f"{k[0]}:{k[1]}" for k in w.utility]
    return w.assign(weight=w.weight.round(8))


def test_the_driver_writes_exactly_the_rows_implied_weights_gives(tmp_path):
    designs = {"headline_set": one_host(), "every_cohort_utility": two_hosts()}
    expected = [ic.implied_weights(d).assign(set=name) for name, d in designs.items()]
    frames, info = dw.weights_for(designs)
    assert all(e["weights_computed"] for e in info.values())
    assert [e["hosts_in_the_estimate"] for e in info.values()] == [1, 2]
    for got, want in zip(frames, expected):
        pd.testing.assert_frame_equal(got, want, check_exact=True)          # the same rows, unrounded, before writing
    dw.write(frames, {"sets": info}, tmp_path)
    on_disk = pd.read_csv(tmp_path / dw.CSV_NAME)
    assert list(on_disk.columns) == COLUMNS
    want = as_inference_check_main_writes(expected)
    want_disk = tmp_path / "want.csv"
    want.to_csv(want_disk, index=False)
    assert (tmp_path / dw.CSV_NAME).read_bytes() == want_disk.read_bytes()   # byte for byte as inference_check.main writes
    # each design's host weights on event years 2 and 3 sum to one (the headline is their mean less the reference year)
    for name in designs:
        s = on_disk[(on_disk.set == name) & on_disk.is_host & on_disk.event_year.isin([2, 3])].weight.sum()
        assert abs(s - 1.0) < 1e-6


def test_the_driver_touches_no_preserved_file_and_records_the_csv_hash(tmp_path):
    preserved = {"inference_check.json": b'{"preserved": "2026-11-14"}\n', "second_number_leverage.csv": b"a,b\n1,2\n"}
    for name, body in preserved.items():
        (tmp_path / name).write_bytes(body)
    frames, info = dw.weights_for({"headline_set": one_host()})
    prov = dw.write(frames, {"sets": info}, tmp_path)
    for name, body in preserved.items():
        assert (tmp_path / name).read_bytes() == body
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([*preserved, dw.CSV_NAME, dw.PROVENANCE_NAME])
    assert prov["csv"]["sha256"] == hashlib.sha256((tmp_path / dw.CSV_NAME).read_bytes()).hexdigest()
    assert json.loads((tmp_path / dw.PROVENANCE_NAME).read_text())["csv"]["sha256"] == prov["csv"]["sha256"]


def test_a_rank_deficient_set_is_reported_in_words_and_has_no_rows(tmp_path):
    frames, info = dw.weights_for({"headline_set": one_host(), "every_cohort_utility": rank_deficient()})
    assert info["every_cohort_utility"]["weights_computed"] is False
    assert isinstance(info["every_cohort_utility"]["implied_weights"]["not_computed"], str)
    assert info["every_cohort_utility"]["implied_weights"]["not_computed"]
    assert [f.set.iloc[0] for f in frames] == ["headline_set"]
    dw.write(frames, {"sets": info}, tmp_path)
    assert set(pd.read_csv(tmp_path / dw.CSV_NAME).set) == {"headline_set"}


def test_the_driver_calls_nothing_in_inference_check_but_implied_weights():
    """No made-up dataset, no leverage table, no report: the only inference_check name the module uses is implied_weights."""
    tree = ast.parse((ROOT / "pipeline" / "analysis" / "design_weights.py").read_text())
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "ic"}
    assert used == {"implied_weights"}
    used_ps = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "ps"}
    assert not used_ps & {"load_outcomes", "read_listed_outcomes", "main", "_run", "run_second_number", "run_new_hosts", "one_draw"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "panel" not in names                                        # never reaches panel.load_outcomes


def test_no_rows_at_all_writes_no_csv_and_says_why(tmp_path):
    frames, info = dw.weights_for({"headline_set": rank_deficient()})
    prov = dw.write(frames, {"sets": info}, tmp_path)
    assert not (tmp_path / dw.CSV_NAME).exists()
    assert prov["csv"]["written"] is False and prov["csv"]["sha256"] is None
    assert sorted(p.name for p in tmp_path.iterdir()) == [dw.PROVENANCE_NAME]
