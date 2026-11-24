"""Integrity of the rebuilt CEPR instrument inputs (docs/DECISIONS.md, D-16).

These read the committed outputs in data/frozen/ and check them against each
other and against the paper's printed spending table. No price data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.instrument import build_fiber_share as b  # noqa: E402

FROZEN = ROOT / "data" / "frozen"


@pytest.fixture(scope="module")
def share() -> pd.DataFrame:
    return pd.read_csv(FROZEN / "fiber_share.csv")


@pytest.fixture(scope="module")
def report() -> dict:
    return json.loads((FROZEN / "instrument_report.json").read_text())


def test_one_row_per_utility_state_and_fiber_never_exceeds_blocks(share):
    assert not share.duplicated(["utility_id_eia", "state"]).any()
    assert set(share.state) <= set(b.FIPS.values()) - {"AK", "HI"}   # contiguous U.S. only
    for f in b.FILINGS:
        assert (share[f"fiber_blocks_{f}"] <= share.n_blocks).all()
        assert (share[f"fiber_blocks_{f}"] >= 0).all()


def test_primary_share_is_the_mean_of_the_december_shares(share, report):
    nat = report["national_fiber_blocks_contiguous"]
    dec = sum(share[f"fiber_blocks_{f}"] / nat[f] for f in b.DEC) / len(b.DEC)
    assert dec.values == pytest.approx(share.fiber_share_dec.values, rel=1e-8, abs=1e-12)
    assert share.fiber_share_dec.between(0, 1).all()
    assert share.fiber_share_dec.sum() == pytest.approx(report["sum_of_shares_dec"], abs=1e-3)


def test_fiber_grew_every_filing_and_every_fcc_block_was_placed(report):
    nat = [report["national_fiber_blocks_contiguous"][f] for f in b.FILINGS]
    assert nat == sorted(nat) and nat[0] > 2_000_000
    for f in b.FILINGS:
        assert report["fcc_fiber_blocks_not_in_census_block_file"][f].startswith("0 of ")


def test_spending_matches_the_papers_table_except_revised_2024():
    s = pd.read_csv(FROZEN / "dc_construction_spending.csv").set_index("year")
    for year, paper_bn in b.PAPER_S3_REAL_2024_BN.items():
        ours_bn = s.real_2024_musd[year] / 1000
        assert s.paper_table_s3_real_2024_bn[year] == paper_bn
        if year < 2024:
            assert ours_bn == pytest.approx(paper_bn, rel=0.006), year   # their table prints three digits
    assert s.real_2024_musd[2024] == pytest.approx(s.nominal_musd[2024])       # 2024 dollars
    assert s.real_2024_musd[2024] / 1000 > b.PAPER_S3_REAL_2024_BN[2024]       # Census revised it up


# ---- folding into panel units ---------------------------------------------

def test_fold_sums_counts_recomputes_shares_and_lists_ids():
    from pipeline.electricity import succession
    national = {f: 1000 for f in b.FILINGS}
    rows = []
    for uid, st, n, fib in [(1, "OH", 100, [10, 20, 30, 40, 50, 60]),
                            (2, "OH", 50, [1, 2, 3, 4, 5, 6]),
                            (3, "OH", 70, [7, 7, 7, 7, 7, 7])]:
        r = {"utility_id_eia": uid, "state": st, "n_blocks": n}
        r.update({f"fiber_blocks_{f}": v for f, v in zip(b.FILINGS, fib)})
        rows.append(r)
    c = pd.DataFrame(rows)
    u = b.fold_to_units(c, {(2, "OH"): 1}, national)
    assert len(u) == 2
    a = u[u.utility_id_eia == 1].iloc[0]
    assert a.n_blocks == 150 and a["fiber_blocks_2019-12"] == 66 and a["fiber_blocks_2017-12"] == 22
    assert a.ids_folded == "1;2" and a.n_ids_folded == 2
    assert a.fiber_share_dec == pytest.approx((22 + 44 + 66) / 3 / 1000)
    assert a.fiber_share_jun == pytest.approx((11 + 33 + 55) / 3 / 1000)
    assert a.fiber_share_all6 == pytest.approx((11 + 22 + 33 + 44 + 55 + 66) / 6 / 1000)
    t = u[u.utility_id_eia == 3].iloc[0]
    assert t.ids_folded == "3" and t.n_ids_folded == 1 and t.n_blocks == 70
    assert t.fiber_share_dec == pytest.approx(0.007)
    # a distinct-block override replaces the sum for that unit only, and shares follow it
    d = pd.DataFrame([{"utility_id_eia": 1, "state": "OH", "n_blocks": 120,
                       **{f"fiber_blocks_{f}": 10 for f in b.FILINGS}}])
    u2 = b.fold_to_units(c, {(2, "OH"): 1}, national, d)
    a2 = u2[u2.utility_id_eia == 1].iloc[0]
    assert a2.n_blocks == 120 and a2.n_blocks_summed == 150 and a2.fiber_share_dec == pytest.approx(0.01)
    assert u2[u2.utility_id_eia == 3].iloc[0].n_blocks == 70


def test_unit_file_keys_unique_and_no_absorbed_id_remains():
    from pipeline.electricity import succession
    u = pd.read_csv(FROZEN / "fiber_share_by_unit.csv")
    assert not u.duplicated(["utility_id_eia", "state"]).any()
    mapping = succession.resolve(succession.load())
    keys = set(zip(u.utility_id_eia, u.state))
    assert not [k for k in mapping if k in keys]
    assert (u.n_ids_folded == u.ids_folded.str.count(";") + 1).all()
    assert u.n_ids_folded.gt(1).sum() >= 1
    for f in b.FILINGS:
        assert (u[f"fiber_blocks_{f}"] <= u.n_blocks).all()
