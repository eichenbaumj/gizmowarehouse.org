"""pipeline/facilities/pass_c_exact_s18.py: the driver that reruns the exact attribution with the host list the headline set
gives. It must write what pass_c_exact.main writes, byte for byte in the CSV and key for key in the JSON (bar the run's
timings and the one added key, host_list), and must not stop on the host count. Load and sales only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import pass_c_exact as pe  # noqa: E402
from pipeline.facilities import pass_c_exact_s18 as s18  # noqa: E402

STATES = "WY,NM"


def _strip_seconds(x):
    if isinstance(x, dict):
        return {k: _strip_seconds(v) for k, v in x.items() if k != "seconds"}
    if isinstance(x, list):
        return [_strip_seconds(v) for v in x]
    return x


@pytest.fixture(scope="module")
def hosts():
    return pe.hosts_from_headline(pd.read_csv(pe.HEADLINE))


@pytest.fixture(scope="module")
def runs(tmp_path_factory, hosts):
    """The same small run through pass_c_exact.main (its guard set to the current count) and through the new driver."""
    d = tmp_path_factory.mktemp("s18")
    corr = d / "corrections.json"
    corr.write_text("[]")
    out = {}
    saved = pe.HOSTS_EXPECTED
    try:
        pe.HOSTS_EXPECTED = len(hosts)
        assert pe.main([str(corr), "--out", str(d / "old.json"), "--csv", str(d / "old.csv"), "--also-states", STATES]) == 0
    finally:
        pe.HOSTS_EXPECTED = saved
    assert s18.main([str(corr), "--out", str(d / "new.json"), "--csv", str(d / "new.csv"), "--also-states", STATES]) == 0
    for name in ("old", "new"):
        out[name] = (json.loads((d / f"{name}.json").read_text()), (d / f"{name}.csv").read_text())
    return out


def test_the_guard_still_stops_pass_c_exact_when_the_count_differs(tmp_path, hosts):
    if len(hosts) == pe.HOSTS_EXPECTED:
        pytest.skip("the headline set gives HOSTS_EXPECTED hosts; the guard does not fire")
    corr = tmp_path / "c.json"
    corr.write_text("[]")
    with pytest.raises(SystemExit):
        pe.main([str(corr), "--also-states", "WY"])


def test_the_csv_is_byte_identical_to_pass_c_exact_main(runs):
    assert runs["new"][1] == runs["old"][1]


def test_the_json_equals_pass_c_exact_main_bar_timings_and_the_label(runs):
    old, new = runs["old"][0], runs["new"][0]
    assert set(new) - set(old) == {"host_list"}
    assert _strip_seconds({k: v for k, v in new.items() if k != "host_list"}) == _strip_seconds(old)


def test_the_label_carries_the_count_and_the_source(runs, hosts):
    lab = runs["new"][0]["host_list"]
    assert lab["n"] == len(hosts) == len(runs["new"][0]["hosts"])
    # counts.hosts.n counts the listed hosts found in the states run, here only those in WY and NM
    assert runs["new"][0]["counts"]["hosts"]["n"] == sum(s in STATES.split(",") for _, s in hosts)
    assert lab["source"] == "data/frozen/headline_set.csv"
    assert lab["pass_c_exact_HOSTS_EXPECTED"] == pe.HOSTS_EXPECTED
    assert str(len(hosts)) in lab["csv_column_note"]


def test_the_csv_columns_are_unchanged(runs):
    assert runs["new"][1].splitlines()[0].split(",") == pe.CSV_COLUMNS
