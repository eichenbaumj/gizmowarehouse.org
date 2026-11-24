"""Integrity of the two control-variable builds: fuel-mix groups and degree days.

Reads the committed outputs in data/frozen/ (never the network). No price data.
The by-eye values below were summed straight from the raw CPC files
(data/raw/cpc_degree_days/<year>/StatesCONUS.{Heating,Cooling}.txt, row for the
two-letter state code, 365 daily values added with awk) and typed in here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "data" / "frozen"
CONTIGUOUS = ("AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
              "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()


@pytest.fixture(scope="module")
def fuel() -> pd.DataFrame:
    return pd.read_csv(FROZEN / "fuel_mix_groups.csv", keep_default_na=False, na_values=[""])


@pytest.fixture(scope="module")
def fuel_report() -> dict:
    return json.loads((FROZEN / "fuel_mix_report.json").read_text())


@pytest.fixture(scope="module")
def dd() -> pd.DataFrame:
    return pd.read_csv(FROZEN / "degree_days.csv", keep_default_na=False)


@pytest.fixture(scope="module")
def dd_report() -> dict:
    return json.loads((FROZEN / "degree_days_report.json").read_text())


# ---------------------------------------------------------------- fuel mix

def test_fuel_mix_has_51_unique_rows_and_columns(fuel):
    assert list(fuel.columns) == ["state", "gas_share_2008", "gas_share_2009", "gas_share_2010",
                                  "gas_share_mean", "fuel_mix_group", "in_tercile_sample", "gas_row_absent"]
    assert len(fuel) == 51 and fuel.state.is_unique
    assert set(fuel.state) == set(CONTIGUOUS) | {"DC", "AK", "HI"}


def test_no_blank_share_or_group_and_nothing_reported_missing(fuel, fuel_report):
    assert fuel[["gas_share_2008", "gas_share_2009", "gas_share_2010", "gas_share_mean", "fuel_mix_group"]].notna().all().all()
    assert fuel_report["states_with_missing_data"] == []


def test_absent_gas_rows_are_zero_only_where_the_sources_reconcile(fuel, fuel_report):
    absent = fuel[fuel.gas_row_absent]
    assert set(absent.state) == {"DC", "HI"}
    for c in ("gas_share_2008", "gas_share_2009", "gas_share_2010", "gas_share_mean"):
        assert (absent[c] == 0.0).all()
    assert not fuel[~fuel.gas_row_absent].gas_share_mean.eq(0.0).any()
    log = fuel_report["gas_row_absent_state_years"]
    assert {(r["state"], r["year"]) for r in log} == {(s, y) for s in ("DC", "HI") for y in (2008, 2009, 2010)}
    for r in log:
        assert abs(r["total_mwh"] - r["sum_of_other_listed_sources_mwh"]) <= 1.0 and r["gas_share_set_to"] == 0.0
    assert fuel[fuel.state == "DC"].iloc[0].in_tercile_sample
    assert not fuel[fuel.state == "HI"].iloc[0].in_tercile_sample


def test_shares_between_0_and_1_and_mean_is_mean_of_three(fuel, fuel_report):
    have = fuel
    # One published value is slightly negative: North Dakota 2008 natural gas net generation
    # is -51 MWh in EIA's table (station use exceeding output). Kept as published, not clipped.
    assert fuel_report["shares_outside_0_1"] == [{"state": "ND", "year": 2008, "share": pytest.approx(-0.000002, abs=1e-6)}]
    for c in ("gas_share_2008", "gas_share_2009", "gas_share_2010", "gas_share_mean"):
        assert have[c].between(-1e-5, 1).all(), c
        assert have[c][have[c] < 0].shape[0] == (1 if c == "gas_share_2008" else 0), c
    m = have[["gas_share_2008", "gas_share_2009", "gas_share_2010"]].mean(axis=1)
    assert (m - have.gas_share_mean).abs().max() < 2e-6   # rounding to 6 decimals


def test_sample_split_is_as_even_as_ties_allow(fuel, fuel_report):
    s = fuel[fuel.in_tercile_sample]
    assert len(s) == 49 and set(s.state) == set(CONTIGUOUS) | {"DC"}
    counts = s.fuel_mix_group.value_counts().reindex(["low", "mid", "high"]).fillna(0).astype(int)
    assert counts.sum() == len(s) == fuel_report["units_in_tercile_sample"]
    assert counts.max() - counts.min() <= 1 and counts.to_dict() == {"low": 16, "mid": 17, "high": 16}
    assert fuel_report["count_per_group_sample"] == counts.to_dict()


def test_group_labels_follow_the_cut_points(fuel, fuel_report):
    lo, hi = fuel_report["cut_points"]["cut_low"], fuel_report["cut_points"]["cut_high"]
    assert lo < hi
    have = fuel
    expect = have.gas_share_mean.map(lambda x: "low" if x < lo else ("high" if x > hi else "mid"))
    assert (expect == have.fuel_mix_group).all()


def test_alaska_gets_a_group_but_is_off_sample(fuel, fuel_report):
    ak = fuel[fuel.state == "AK"].iloc[0]
    assert not ak.in_tercile_sample and ak.fuel_mix_group in {"low", "mid", "high"}
    assert fuel_report["off_sample_groups"]["AK"] == ak.fuel_mix_group


def test_spot_checks_the_data_support(fuel):
    g = fuel.set_index("state").fuel_mix_group
    assert g["RI"] == "high" and g["NV"] == "high"
    assert g["VT"] == "low" and g["WV"] == "low"


# ------------------------------------------------------------ degree days

def test_degree_days_columns_and_every_state_year(dd, dd_report):
    assert list(dd.columns) == ["state", "year", "hdd", "cdd", "basis"]
    last = dd_report["years_in_output"][1]
    assert dd_report["years_in_output"][0] == 2001 and last >= 2024
    native = dd[dd.basis == "NOAA state value"]
    assert set(native.state) == set(CONTIGUOUS)
    full = {(s, y) for s in CONTIGUOUS for y in range(2001, last + 1)}
    assert set(zip(native.state, native.year)) == full
    assert not dd.duplicated(["state", "year"]).any()


def test_no_negative_values_and_basis_labels(dd):
    assert (dd.hdd >= 0).all() and (dd.cdd >= 0).all()
    assert set(dd.basis) == {"NOAA state value", "Maryland, used for DC"}
    assert set(dd[dd.basis != "NOAA state value"].state) == {"DC"}


def test_dc_is_a_copy_of_maryland(dd):
    md = dd[dd.state == "MD"].set_index("year")[["hdd", "cdd"]]
    dc = dd[dd.state == "DC"].set_index("year")[["hdd", "cdd"]]
    assert md.equals(dc)


def test_florida_hotter_and_maine_colder_every_year(dd):
    p = dd.pivot(index="year", columns="state", values=["hdd", "cdd"])
    assert (p[("cdd", "FL")] > p[("cdd", "ME")]).all()
    assert (p[("hdd", "ME")] > p[("hdd", "FL")]).all()


# Annual sums of the raw daily files, read by eye (awk) for the state's own row,
# so a wrong state mapping or a column mix-up between heating and cooling fails here.
@pytest.mark.parametrize("state,year,col,value", [
    ("FL", 2010, "cdd", 3112),
    ("ME", 2010, "hdd", 7100),
    ("WI", 2001, "hdd", 7024),
    ("TX", 2025, "cdd", 3009),
    ("NV", 2018, "hdd", 3212),
])
def test_state_values_match_raw_file_read_by_eye(dd, state, year, col, value):
    r = dd[(dd.state == state) & (dd.year == year)].iloc[0]
    assert r[col] == value


def test_report_documents_weighting_and_absences(dd_report):
    assert "population weighted State" in dd_report["population_weighting"]["noaa_sentence_verbatim"]
    assert "65" in dd_report["base_temperature"]["sentence_verbatim"]
    assert dd_report["jurisdictions_absent_from_product"] == ["AK", "DC", "HI"]
    assert dd_report["state_years_dropped_for_missing_days"] == []
