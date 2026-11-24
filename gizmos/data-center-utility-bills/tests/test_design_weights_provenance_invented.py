"""The design-weights sidecar's comparison with the design records (design_weights.against_the_design_records), on
invented JSON only, written to pytest's tmp_path. No file under data/ is read.

After the ownership repair of 2026-11-19 the every-cohort set's design-inputs hash no longer equals the one the historical
step E record (design_support.json) carries. The sidecar must say so set by set, with the reason in words, and must flag a
difference the repair does not explain.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import design_weights as dw  # noqa: E402


def record(folder: Path, name: str, hashes: dict):
    sets = {w: {"fingerprint": {"of": {"design_inputs": h}}} for w, h in hashes.items()}
    (folder / name).write_text(json.dumps({"sets": sets}))


def info(hashes: dict) -> dict:
    return {w: {"design_inputs_sha256": h} for w, h in hashes.items()}


STEP_E = {"headline_set": "aaa", "every_cohort_utility": "old"}
NOW = {"headline_set": "aaa", "every_cohort_utility": "new"}


def check_expected(r):
    assert r["sets"]["headline_set"]["equal_to_the_step_e_record"] is True
    assert r["sets"]["every_cohort_utility"]["equal_to_the_step_e_record"] is False
    assert r["sets"]["every_cohort_utility"]["equal_to_the_current_design_summary"] is True
    assert r["sets_differing_from_the_step_e_record"] == ["every_cohort_utility"]
    why = r["why_a_set_differs_from_the_step_e_record"]
    assert why == dw.WHY_A_SET_DIFFERS
    for phrase in ("ownership repair of 2026-11-19", "eight matches of three hosts", "not rewritten"):
        assert phrase in why, phrase
    assert "—" not in why


def test_the_every_cohort_set_is_said_to_differ_from_the_step_e_record_and_why(tmp_path):
    record(tmp_path, dw.STEP_E_RECORD, STEP_E)
    record(tmp_path, dw.CURRENT_SUMMARY, NOW)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    r = dw.against_the_design_records(info(NOW), tmp_path)
    check_expected(r)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before          # both records read, neither written


def test_the_check_fails_if_the_weights_were_on_the_step_e_design(tmp_path):
    """A deliberate break in the test process: the weights' hashes taken from the step E record. The expected-difference
    check then fails."""
    record(tmp_path, dw.STEP_E_RECORD, STEP_E)
    record(tmp_path, dw.CURRENT_SUMMARY, NOW)
    with pytest.raises(AssertionError):
        check_expected(dw.against_the_design_records(info(STEP_E), tmp_path))


def test_a_difference_the_repair_does_not_explain_is_flagged_in_words(tmp_path):
    record(tmp_path, dw.STEP_E_RECORD, STEP_E)
    record(tmp_path, dw.CURRENT_SUMMARY, {"headline_set": "bbb", "every_cohort_utility": "new"})
    r = dw.against_the_design_records(info({"headline_set": "bbb", "every_cohort_utility": "new"}), tmp_path)
    assert r["sets_differing_from_the_step_e_record"] == ["every_cohort_utility", "headline_set"]
    assert r["why_a_set_differs_from_the_step_e_record"].startswith("UNEXPECTED")


def test_a_missing_record_gives_none_not_a_guess(tmp_path):
    r = dw.against_the_design_records(info(NOW), tmp_path)
    assert all(v["equal_to_the_step_e_record"] is None and v["equal_to_the_current_design_summary"] is None for v in r["sets"].values())
