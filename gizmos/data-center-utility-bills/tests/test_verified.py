"""Rules for hand-verified facts, and integrity of the committed verification files.

The first group uses synthetic values. The second reads the files under
pipeline/facilities/verified/ and fails if a committed value breaks a rule in
docs/DECISIONS.md (D-8, D-10, D-15): no source, a directory site as source, or
a low-confidence year.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import apply_verified as av  # noqa: E402
from pipeline.facilities import build_inventory as bi  # noqa: E402
from pipeline.facilities import dating_report  # noqa: E402
from pipeline.facilities import write_r3_batches as wr  # noqa: E402

VER = ROOT / "pipeline" / "facilities" / "verified"
R3 = sorted(glob.glob(str(VER / "batch_r3_*.json")))


# ---- rules, synthetic -------------------------------------------------

@pytest.mark.parametrize("url,conf,ok", [
    ("https://www.datacenterfrontier.com/x", "high", True),
    ("https://about.fb.com/news/2014/11/x", "medium", True),
    ("https://www.datacenterfrontier.com/x", "low", False),          # low confidence never becomes an override
    ("https://baxtel.com/data-center/x", "high", False),             # directory sites are leads, not sources
    ("https://www.datacentermap.com/usa/x", "high", False),
    ("https://cleanview.co/data-centers/x", "medium", False),
    (None, "high", False),                                           # no source, no override
    ("", "high", False),
])
def test_usable_requires_a_non_directory_source_and_confidence(url, conf, ok):
    assert av.usable(url, conf) is ok


def test_error_stats_counts_late_and_early_permits():
    d = pd.DataFrame({"err": [0, 1, -1, 2, 5, 12, -3, -6]})
    s = dating_report.error_stats(d)
    assert s["n"] == 8
    assert s["within_1_year"] == pytest.approx(3 / 8)
    assert s["within_2_years"] == pytest.approx(4 / 8)
    assert s["permit_5_or_more_years_late"] == pytest.approx(2 / 8)
    assert s["permit_3_or_more_years_early"] == pytest.approx(2 / 8)
    assert dating_report.error_stats(d.iloc[:0]) == {"n": 0}


@pytest.mark.parametrize("d,ok", [("2025", True), ("2026-09", True), ("2026-09-23", True), ("2024-12-31", False),
                                  ("Undated live operator page; fetched 2026-11-11", False), (None, False), ("", False)])
def test_status_page_needs_a_real_date(d, ok):
    assert wr.dated_2025_or_later(d) is ok


def test_writer_keeps_unverified_claims_out_of_the_active_fields():
    item = {"fid": "bi:1-0", "site_name": "X", "operator": "Y", "state": "VA", "energized_year": 2019,
            "energized_year_source_url": "https://baxtel.com/x", "year_confidence": "high", "notes": "n"}
    # no verdict, a refusal, a directory source, and a low-confidence verdict all leave the year empty
    for v in (None,
              {"verdict": "not_verified", "comment": "no"},
              {"verdict": "verified_year", "year": 2019, "source_url": "https://baxtel.com/x", "confidence": "high"},
              {"verdict": "verified_year", "year": 2019, "source_url": "https://example.org/x", "confidence": None}):
        r = wr.record(item, v)
        assert r["energized_year"] is None and r["operating_status"] is None
        assert r["lead"]["energized_year"] == 2019 and r["lead"]["unverified"] is True
        assert r["is_data_center"] is True and r["load_mw_2025"] is None
    r = wr.record(item, {"verdict": "verified_year", "year": 2018, "source_url": "https://example.org/x",
                         "confidence": "medium", "basis": "operator_statement", "quote": "opened in 2018"})
    assert (r["energized_year"], r["year_confidence"]) == (2018, "medium")  # the verifier's year wins over the claim
    r = wr.record(item, {"verdict": "verified_not_yet_operating", "source_url": "https://example.org/x",
                         "page_date": "Undated live page", "confidence": "medium"})
    assert r["operating_status"] is None
    r = wr.record(item, {"verdict": "verified_not_yet_operating", "source_url": "https://example.org/x",
                         "page_date": "2026-09-23", "confidence": "medium"})
    assert r["operating_status"] == "not_yet_operating" and r["energized_year"] is None


def test_overrides_date_a_site_or_take_its_load_away():
    fac = pd.DataFrame({
        "fid": ["a", "b", "c", "d", "e"], "src": ["bi", "bi", "bi", "epoch", "bi"],
        "energized_year": [2022.0, 2023.0, 2024.0, 2021.0, 2019.0],
        "date_basis": ["first_generator_permit_plus_lag"] * 3 + ["epoch_timeline", "first_generator_permit_plus_lag"],
        "left_censored": [True, False, False, False, False],
        "mw_full": [50.0, 60.0, 70.0, 300.0, 5.0], "mw_basis": ["generator_capacity_x_kappa"] * 5,
    })
    ov = pd.DataFrame({
        "fid": ["a", "b", "d", "e"],
        "energized_year": [2010.0, None, None, None],          # a: opened twelve years before its permit
        "not_yet_operating": [None, True, None, None],         # b: still under construction
        "load_mw_2025": [None, None, 120.0, None],             # d: a verified load on an Epoch row is ignored
        "drop_not_data_center": [None, None, None, True],      # e: not a data center
    }).set_index("fid")
    out = bi.apply_overrides(fac, ov).set_index("fid")
    assert list(out.index) == ["a", "b", "c", "d"]
    assert out.loc["a", "energized_year"] == 2010 and out.loc["a", "date_basis"] == "verified_public_source"
    assert not out.loc["a", "left_censored"] and out.loc["a", "verified_fields"] == "year;"
    assert pd.isna(out.loc["b", "energized_year"]) and out.loc["b", "date_basis"] == "verified_not_yet_operating"
    assert out.loc["b", "verified_fields"] == "status;"
    assert out.loc["c", "energized_year"] == 2024 and out.loc["c", "verified_fields"] == ""   # untouched
    assert out.loc["d", "mw_full"] == 300 and out.loc["d", "verified_fields"] == ""


# ---- committed files --------------------------------------------------

def test_every_override_year_has_a_usable_source():
    ov = pd.read_csv(VER / "overrides.csv")
    yr = ov[ov.energized_year.notna()]
    assert yr.energized_year_source_url.notna().all()
    assert not yr.energized_year_source_url.map(av.domain).isin(av.BLOCKED_DOMAINS).any()
    assert yr.energized_year.between(1990, 2026).all()


def test_not_yet_operating_is_sourced_and_never_also_dated():
    ov = pd.read_csv(VER / "overrides.csv")
    if "not_yet_operating" not in ov:
        pytest.skip("no site marked not yet operating")
    nyo = ov[ov.not_yet_operating.eq(True)]
    assert nyo.status_source_url.notna().all()
    assert not nyo.status_source_url.map(av.domain).isin(av.BLOCKED_DOMAINS).any()
    assert nyo.energized_year.isna().all()


@pytest.mark.skipif(not R3, reason="no round 3 files yet")
def test_round3_files_follow_the_round3_rules():
    work = set(pd.read_csv(VER / "r3_worklist.csv").fid)
    overrides_fids = set(pd.read_csv(VER / "overrides.csv").fid)
    seen: set[str] = set()
    for p in R3:
        for r in json.loads(Path(p).read_text()):
            fid = r["fid"]
            assert fid in work, f"{fid} is not on the round 3 worklist"
            assert fid not in seen, f"{fid} appears twice in round 3"
            seen.add(fid)
            assert r.get("is_data_center") is not False, "round 3 never drops a site on a lookup's say-so"
            if r.get("duplicate_of"):   # the one allowed removal: a second permit row for a site we keep
                assert r["duplicate_of"] in overrides_fids and r["duplicate_of"] != fid
            if r.get("energized_year") is not None:
                assert av.usable(r.get("energized_year_source_url"), r.get("year_confidence")), fid
                assert r.get("year_evidence_quote"), f"{fid}: a year needs the passage that supports it"
                assert r.get("operating_status") != "not_yet_operating", fid
            if r.get("operating_status") == "not_yet_operating":
                assert av.usable(r.get("status_source_url"), r.get("status_confidence")), fid
                assert wr.dated_2025_or_later(r.get("status_as_of")), f"{fid}: status page must be dated 2025 or later"
            # Round 3 settles dates only. Loads and utilities from the lookup pass were not
            # verified, so they live under "lead" and must not reach the override table.
            for k in ("load_mw_2025", "load_source_url", "serving_utility", "utility_source_url"):
                assert r.get(k) is None, f"{fid}: {k} must be null in round 3"


def test_retry_and_sample_files_carry_only_verified_facts():
    """Second retry (batch_r3bb_) and the small-site sample (batch_r3s_) follow round 3's rules."""
    files = sorted(glob.glob(str(VER / "batch_r3b*_*.json")) + glob.glob(str(VER / "batch_r3s_*.json")))
    sample = set(pd.read_csv(VER / "sample_worklist.csv").fid)
    work = set(pd.read_csv(VER / "r3_worklist.csv").fid)
    for p in files:
        for r in json.loads(Path(p).read_text()):
            fid = r["fid"]
            assert fid in (sample if "_r3s_" in p else work), f"{fid} is not on the list {Path(p).name} was built from"
            assert r.get("is_data_center") is not False
            if r.get("energized_year") is not None:
                assert av.usable(r.get("energized_year_source_url"), r.get("year_confidence")), fid
                assert r.get("year_evidence_quote"), fid
                assert r.get("operating_status") != "not_yet_operating", fid
            if r.get("operating_status") == "not_yet_operating":
                assert av.usable(r.get("status_source_url"), r.get("status_confidence")), fid
                assert wr.dated_2025_or_later(r.get("status_as_of")), fid
            for k in ("load_mw_2025", "load_source_url", "serving_utility", "utility_source_url"):
                assert r.get(k) is None, f"{fid}: {k} must be null"


def test_county_gis_batch_is_medium_recent_and_points_at_the_county_record():
    p = VER / "batch_r3c_0.json"
    if not p.exists():
        pytest.skip("no county batch")
    for r in json.loads(p.read_text()):
        assert r["group"] == "county" and r["year_confidence"] == "medium"
        assert 2005 <= r["energized_year"] <= 2026, r["fid"]
        assert av.domain(r["energized_year_source_url"]) in ("logis.loudoun.gov", "gisweb.pwcva.gov")
        assert str(r["energized_year"]) in r["year_evidence_quote"] or "occupancy" in r["year_evidence_quote"]
        assert r["load_mw_2025"] is None and r["serving_utility"] is None


def test_public_record_batch_is_medium_recent_sourced_and_matches_the_script():
    from pipeline.facilities import write_public_records_batch as pr
    p = VER / "batch_r3c_1.json"
    if not p.exists():
        pytest.skip("no public-record batch")
    recs = json.loads(p.read_text())
    assert recs == pr.batch_records(), "batch_r3c_1.json is stale: rerun write_public_records_batch.py"
    work = set(pd.read_csv(VER / "r3_worklist.csv").fid)
    for r in recs:
        assert r["group"] == "public_record" and r["group"] in av.BULK_RECORD_GROUPS
        assert r["fid"] in work, f"{r['fid']} is not on the round 3 worklist"
        assert r["year_confidence"] == "medium" and av.usable(r["energized_year_source_url"], "medium")
        assert 2005 <= r["energized_year"] <= 2026, r["fid"]
        assert r["year_evidence_quote"] and r["year_site_match"], r["fid"]
        assert str(r["energized_year"]) in r["year_evidence_quote"], f"{r['fid']}: the quote must carry the year"
        assert r["load_mw_2025"] is None and r["serving_utility"] is None
    assert not {r["fid"] for r in pr.RECORDS} & {r["fid"] for r in pr.LEADS}


def test_a_record_year_fills_gaps_only():
    """A government-record year never replaces a page-sourced year or a verified 'not yet operating'."""
    src = Path(av.__file__).read_text()
    assert 'o.get("energized_year") is not None or o.get("not_yet_operating")' in src
    ov = pd.read_csv(VER / "overrides.csv").set_index("fid")
    for p in sorted(glob.glob(str(VER / "batch_r3c_*.json"))):
        for r in json.loads(Path(p).read_text()):
            if r["fid"] in ov.index and "not_yet_operating" in ov and ov.not_yet_operating.get(r["fid"]) is True:
                assert pd.isna(ov.energized_year[r["fid"]]), r["fid"]


def test_a_county_year_never_replaces_a_year_sourced_from_a_page():
    assert "county" in av.BULK_RECORD_GROUPS
    ov = pd.read_csv(VER / "overrides.csv").set_index("fid")
    paged = {}
    for p in sorted(glob.glob(str(VER / "batch_*.json"))):
        if "_r3c_" in p:
            continue
        for r in json.loads(Path(p).read_text()):
            if r.get("energized_year") is not None and av.usable(r.get("energized_year_source_url"), r.get("year_confidence")):
                paged[r["fid"]] = r["energized_year"]   # later files win, as in apply_verified
    county = {r["fid"] for r in json.loads((VER / "batch_r3c_0.json").read_text())} if (VER / "batch_r3c_0.json").exists() else set()
    for fid in county & set(paged):
        assert ov.energized_year[fid] == paged[fid], fid


# ---- utility successions in the inventory (docs/DECISIONS.md, D-21) ---------

def test_a_territory_polygon_with_an_old_id_is_read_as_its_successor():
    """The map still carries West Penn Power's id; the panel carries the merged company."""
    fac = pd.DataFrame({"fid": ["a", "b"], "state": ["PA", "WV"], "mw_full": [10.0, 10.0],
                        "candidates": [[20387], [20387]]})
    capacity = pd.Series({(66101, "PA"): 50_000.0, (20387, "WV"): 9_000.0})
    capacity.index = pd.MultiIndex.from_tuples(capacity.index)
    got = bi.pick_utilities(fac, capacity, {(20387, "PA"): 66101})
    assert got.loc["a", "utility_id_eia"] == 66101      # Pennsylvania: folded into the successor
    assert got.loc["b", "utility_id_eia"] == 20387      # the mapping is by state
    assert got.loc["a", "utility_assign"] == "unique"


def test_two_old_ids_of_one_unit_are_one_candidate():
    fac = pd.DataFrame({"fid": ["a"], "state": ["PA"], "mw_full": [10.0], "candidates": [[14716, 20387]]})
    capacity = pd.Series({(66101, "PA"): 50_000.0})
    capacity.index = pd.MultiIndex.from_tuples(capacity.index)
    got = bi.pick_utilities(fac, capacity, {(20387, "PA"): 66101, (14716, "PA"): 66101})
    assert got.loc["a", "utility_id_eia"] == 66101
    assert got.loc["a", "utility_candidates"] == "66101" and got.loc["a", "n_candidates"] == 1


def test_no_override_points_at_a_utility_that_was_folded_into_another():
    from pipeline.electricity import succession as succ
    absorbed = succ.resolve(succ.load())
    ov = pd.read_csv(ROOT / "pipeline" / "facilities" / "verified" / "overrides.csv")
    ov = ov[ov.utility_id_eia.notna()]
    stale = [(f, int(u), s) for f, u, s in zip(ov.fid, ov.utility_id_eia, ov.state) if (int(u), s) in absorbed]
    assert stale == []
