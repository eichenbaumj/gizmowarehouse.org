"""Made-up EIA-861 sales rows for the availability tests. Every number here is invented.

One row per case the availability flag has to get right. Unit 1's revenue carries the canary digits: no
rendering of them may appear in anything the flag build or the audit prints or writes.
"""
from __future__ import annotations

import math

import pandas as pd

from pipeline.electricity import succession as succ

CANARY_REVENUE = 1_731_593.7                      # unit 1, 2020: price 17.315937 cents/kWh
CANARY_STRINGS = ("1731593", "17.315", "17.316", "17.32", "17.31", "173.159", "173.16", "0.17316")
YEAR = 2020


def row(uid, state, year, cls, svc, rev, mwh, cust, entity="Investor Owned", observed=True):
    return dict(utility_id_eia=uid, state=state, year=year, customer_class=cls, service_type=svc, entity_type=entity,
                data_observed=observed, utility_name_eia=f"U{uid}", balancing_authority_code_eia="PJM",
                customers=cust, sales_mwh=mwh, sales_revenue=rev)


def res(uid, state, svc, rev, mwh, cust=3000, year=YEAR, **k):
    return row(uid, state, year, "residential", svc, rev, mwh, cust, **k)


NAN = float("nan")

# (unit, state) -> the first exclusion reason it must get in 2020, or None if it must have no row.
EXPECTED = {
    (1, "GA"): "none",
    (2, "GA"): "under_customer_floor",
    (3, "GA"): "no_residential_sales",
    (4, "TX"): "no_supply_price",
    (5, "GA"): "bundled_revenue_missing",
    (6, "PA"): "delivery_revenue_missing",
    (7, "GA"): "price_not_above_zero",
    (8, "GA"): "price_not_above_zero",
    (9, "TX"): "none",                         # the fallback: share exactly 1%, own supply price above zero
    (10, "TX"): "no_supply_price",             # share 1.5%: no fallback
    (11, "TX"): "no_supply_price",             # share 0.5%, own supply price exactly zero
    (12, "TX"): "no_supply_price",             # share 0.5%, own supply price below zero
    (13, "TX"): "no_supply_price",             # share 0.5%, bundled revenue missing: the supply test comes first
    (14, "PA"): "none",                        # delivery-only sales priced at the state's observed supplier average
    (15, "GA"): None,                          # every residential row flagged imputed: no row in the panel
    (16, "GA"): "none",                        # bundled observed, delivery imputed: priced from the bundled rows
    (17, "GA"): "none",                        # no imputation flag: kept as observed, status "unknown"
    (19, "GA"): "none",                        # 18 summed into 19; 18's revenue missing, 19's present: present, as the code sums
    (20, "GA"): "under_customer_floor",        # under the floor AND a negative price: the floor comes first
    (21, "GA"): "no_residential_sales",        # no sales AND under the floor: no sales comes first
    (22, "NJ"): "none",                        # delivery-only, priced at NJ's supplier average; one NJ supplier row unflagged
}
# The supplier-row status (D-72 item 2): only where the state's supplier average sets the supply price.
SUPPLIER_STATUS = {(6, "PA"): "known", (14, "PA"): "known", (22, "NJ"): "unknown"}      # every other unit-year: not_used
# Whether the supply price is unavailable (supply_price_basis == none_available), stated from the inputs alone.
NONE_AVAILABLE = {(4, "TX"), (10, "TX"), (11, "TX"), (12, "TX"), (13, "TX")}
UNKNOWN_STATUS = {(17, "GA")}


def rows() -> list[dict]:
    r = [
        res(1, "GA", "bundled", CANARY_REVENUE, 10_000),
        res(1, "GA", "bundled", 1_500_000, 10_000, year=2019),
        res(2, "GA", "bundled", 1_200_000, 10_000, cust=1500),
        res(3, "GA", "bundled", 0.0, 0.0),
        res(4, "TX", "delivery", 100_000, 5_000),
        res(5, "GA", "bundled", NAN, 10_000),
        res(6, "PA", "bundled", 640_000, 4_000), res(6, "PA", "delivery", NAN, 6_000),
        res(7, "GA", "bundled", 0.0, 10_000),
        res(8, "GA", "bundled", -50_000, 10_000),
        res(9, "TX", "bundled", 1_188_000, 9_900), res(9, "TX", "delivery", 5_000, 100),
        res(10, "TX", "bundled", 1_182_000, 9_850), res(10, "TX", "delivery", 7_500, 150),
        res(11, "TX", "bundled", 497_500, 9_950), res(11, "TX", "delivery", 2_500, 50),
        res(12, "TX", "bundled", 398_000, 9_950), res(12, "TX", "delivery", 3_000, 50),
        res(13, "TX", "bundled", NAN, 9_950), res(13, "TX", "delivery", 2_500, 50),
        res(14, "PA", "delivery", 480_000, 6_000),
        res(15, "GA", "bundled", 1_000_000, 10_000, observed=False),
        res(16, "GA", "bundled", 1_100_000, 10_000), res(16, "GA", "delivery", 90_000, 1_000, observed=False),
        res(17, "GA", "bundled", 1_300_000, 10_000, observed=None),
        res(18, "GA", "bundled", NAN, 5_000, cust=1000), res(19, "GA", "bundled", 1_400_000, 10_000),
        res(20, "GA", "bundled", -10_000, 10_000, cust=1500),
        res(21, "GA", "bundled", 0.0, 0.0, cust=1500),
        row(90, "PA", YEAR, "residential", "energy", 900_000, 10_000, 900, entity="Retail Power Marketer"),
        res(22, "NJ", "delivery", 300_000, 5_000),
        row(91, "NJ", YEAR, "residential", "energy", 400_000, 4_000, 400, entity="Retail Power Marketer"),
        row(92, "NJ", YEAR, "residential", "energy", 100_000, 1_000, 100, entity="Retail Power Marketer", observed=None),
        row(93, "NJ", YEAR, "residential", "energy", 9_999_999, 1_000, 100, entity="Retail Power Marketer", observed=False),
    ]
    return r


SUCCESSION_ROW = {"predecessor_id": 18, "state": "GA", "predecessor_name": "U18", "action": "sum", "successor_id": 19,
                  "successor_name": "U19", "effective_date": "2021-01-01", "source_url": "https://example.org/made-up",
                  "source_type": "made_up", "source_quote": "made up", "confidence": "high", "checked_on": "2026-11-16",
                  "note": "synthetic"}


def succession_table(with_row: bool = True) -> pd.DataFrame:
    return pd.DataFrame([SUCCESSION_ROW] if with_row else [], columns=succ.COLUMNS)


def mapping() -> dict:
    return {(18, "GA"): 19}


def sales_frame(rs=None) -> pd.DataFrame:
    return pd.DataFrame(rs if rs is not None else rows())


def write_sales_parquet(df: pd.DataFrame, path) -> None:
    """The raw file's shape: a report_date instead of a year, as panel.load_sales expects."""
    out = df.copy()
    out["report_date"] = pd.to_datetime(out.pop("year").astype(str) + "-01-01")
    out["data_observed"] = out.data_observed.astype("boolean")
    out.to_parquet(path, index=False)


def with_infinite_revenue(rs=None) -> list[dict]:
    rs = list(rs if rs is not None else rows())
    rs.append(res(30, "GA", "bundled", math.inf, 10_000))
    return rs
