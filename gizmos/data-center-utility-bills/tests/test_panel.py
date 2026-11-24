"""Unit tests for residential price construction. Synthetic rows only."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.electricity import panel  # noqa: E402
from pipeline.electricity import succession as succ  # noqa: E402


def row(uid, state, year, cls, svc, rev, mwh, cust, entity="Investor Owned", observed=True):
    return dict(utility_id_eia=uid, state=state, year=year, customer_class=cls,
                service_type=svc, entity_type=entity, data_observed=observed,
                utility_name_eia=f"U{uid}", balancing_authority_code_eia="PJM",
                customers=cust, sales_mwh=mwh, sales_revenue=rev)


def build(rows, succession=None):
    # Synthetic ids must never meet the real succession table.
    q, o = panel.build(pd.DataFrame(rows), succession=succession or {})
    return q.merge(o, on=panel.KEYS).set_index("utility_id_eia")


def test_bundled_only_is_revenue_over_sales():
    m = build([row(1, "GA", 2020, "residential", "bundled", 1_500_000, 10_000, 1000)])
    assert m.loc[1, "res_price"] == pytest.approx(15.0)  # cents/kWh
    assert m.loc[1, "res_bill_per_customer_month"] == pytest.approx(125.0)
    assert m.loc[1, "res_kwh_per_customer_month"] == pytest.approx(10_000 * 1000 / 1000 / 12)


def test_delivery_rows_get_state_energy_price_added():
    rows = [
        # wires utility: 4,000 MWh default service at 16c, 6,000 MWh delivery-only at 8c
        row(2, "PA", 2020, "residential", "bundled", 640_000, 4_000, 400),
        row(2, "PA", 2020, "residential", "delivery", 480_000, 6_000, 600),
        # suppliers in the state sell energy at 9c
        row(90, "PA", 2020, "residential", "energy", 900_000, 10_000, 900, entity="Retail Power Marketer"),
    ]
    m = build(rows)
    expected = (640_000 + 480_000 + 90.0 * 6_000) / 10_000 / 10.0
    assert m.loc[2, "res_price"] == pytest.approx(expected)  # 16.6
    assert m.loc[2, "res_price_delivery_only"] == pytest.approx(8.0)
    assert m.loc[2, "res_price_default_service"] == pytest.approx(16.0)
    assert m.loc[2, "delivery_share"] == pytest.approx(0.6)
    assert 90 not in m.index  # a supplier is never a unit


def test_delivery_without_state_energy_price_is_missing_not_cheap():
    m = build([row(3, "TX", 2020, "residential", "delivery", 100_000, 5_000, 300)])
    assert pd.isna(m.loc[3, "res_price"])
    assert m.loc[3, "res_price_delivery_only"] == pytest.approx(2.0)


def test_imputed_rows_are_dropped():
    m = build([
        row(4, "OH", 2020, "residential", "bundled", 1_000_000, 10_000, 900),
        row(5, "OH", 2020, "residential", "bundled", 1_000_000, 10_000, 900, observed=False),
    ])
    assert 4 in m.index and 5 not in m.index


def test_nonresidential_load_and_size_floor():
    m = build([
        row(6, "VA", 2020, "residential", "bundled", 1_200_000, 10_000, 1_500),
        row(6, "VA", 2020, "commercial", "bundled", 2_000_000, 30_000, 50),
        row(6, "VA", 2020, "industrial", "delivery", 100_000, 20_000, 2),
    ])
    assert m.loc[6, "nonres_mwh"] == pytest.approx(50_000)
    assert m.loc[6, "total_retail_mwh"] == pytest.approx(60_000)
    assert not m.loc[6, "meets_size_floor"]


def test_outcomes_are_blinded_before_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "GATE_FILE", tmp_path / "GATE1_SIGNED")
    with pytest.raises(PermissionError):
        panel.load_outcomes(purpose="analysis")


def outcome_rows():
    return pd.DataFrame({"utility_id_eia": [1, 1, 2, 3], "state": ["GA", "GA", "GA", "OH"], "year": [2019, 2020, 2020, 2020],
                         "res_price": [10.0, 11.0, 12.0, 13.0]})


def test_power_simulation_reads_only_the_units_it_names(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "GATE_FILE", tmp_path / "GATE1_SIGNED")
    monkeypatch.setattr(panel, "BLIND", tmp_path / "blind")
    monkeypatch.setattr(panel, "INTERIM", tmp_path / "interim")
    panel.write(outcome_rows()[["utility_id_eia", "state", "year"]], outcome_rows())
    with pytest.raises(PermissionError):
        panel.load_outcomes(purpose="power_simulation")
    got = panel.load_outcomes(purpose="power_simulation", units=pd.DataFrame({"utility_id_eia": [1], "state": ["GA"]}))
    assert sorted(got.res_price) == [10.0, 11.0]


def test_power_simulation_never_opens_another_utilitys_rows(tmp_path, monkeypatch):
    """The reader must work when every file it was not asked for is unreadable (D-26, D-27).

    The whole outcome file and the files of utilities 2 and 3 are overwritten with
    bytes that are not a parquet file. If the reader opened any of them it would
    raise. It also must not go through pandas' reader for anything but the named files.
    """
    monkeypatch.setattr(panel, "GATE_FILE", tmp_path / "GATE1_SIGNED")
    monkeypatch.setattr(panel, "BLIND", tmp_path / "blind")
    monkeypatch.setattr(panel, "INTERIM", tmp_path / "interim")
    panel.write(outcome_rows()[["utility_id_eia", "state", "year"]], outcome_rows())
    for f in (panel.BLIND / "panel_outcomes.parquet", panel.unit_file(2, "GA"), panel.unit_file(3, "OH")):
        f.write_bytes(b"not a parquet file")
    opened = []
    real_read = pd.read_parquet
    monkeypatch.setattr(pd, "read_parquet", lambda path, *a, **k: (opened.append(Path(path).name), real_read(path, *a, **k))[1])
    got = panel.load_outcomes(purpose="power_simulation", units=pd.DataFrame({"utility_id_eia": [1], "state": ["GA"]}))
    assert opened == ["1_GA.parquet"]
    assert set(zip(got.utility_id_eia, got.state)) == {(1, "GA")} and len(got) == 2
    # a named unit with no residential rows has no file and is skipped, not an error
    none = panel.load_outcomes(purpose="power_simulation", units=pd.DataFrame({"utility_id_eia": [99], "state": ["GA"]}))
    assert len(none) == 0


def test_rebuilding_removes_the_files_of_units_that_no_longer_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "BLIND", tmp_path / "blind")
    monkeypatch.setattr(panel, "INTERIM", tmp_path / "interim")
    o = outcome_rows()
    panel.write(o[["utility_id_eia", "state", "year"]], o)
    keep = o[o.utility_id_eia != 3]
    panel.write(keep[["utility_id_eia", "state", "year"]], keep)
    assert sorted(f.name for f in (panel.BLIND / panel.BY_UNIT).iterdir()) == ["1_GA.parquet", "2_GA.parquet"]


def test_state_supply_price_uses_observed_rows_only():
    """An imputed supplier row must not move the price used to fill in retail-choice customers (D-27)."""
    rows = [
        row(2, "PA", 2020, "residential", "delivery", 480_000, 6_000, 600),
        row(90, "PA", 2020, "residential", "energy", 900_000, 10_000, 900, entity="Retail Power Marketer"),   # 9c observed
        row(91, "PA", 2020, "residential", "energy", 3_000_000, 10_000, 900, entity="Retail Power Marketer", observed=False),
    ]
    e = panel.state_energy_price(pd.DataFrame(rows)).set_index(["state", "year"]).energy_price_state
    assert e[("PA", 2020)] == pytest.approx(90.0)                    # $/MWh, not the 195 the imputed row would give
    m = build(rows)
    assert m.loc[2, "res_price"] == pytest.approx((480_000 + 90.0 * 6_000) / 6_000 / 10.0)
    # a state whose only supplier rows are imputed has no supply price, and its delivery customers are not priced
    only_imputed = [rows[0], rows[2]]
    m = build(only_imputed)
    assert pd.isna(m.loc[2, "res_price"]) and m.loc[2, "supply_price_basis"] == "none_available"


def test_a_trace_of_delivery_customers_does_not_unprice_a_utility_when_the_state_has_no_observed_supplier():
    """Default service at 16c, delivery-only at 6c: the unit's own implied supply price is 10c."""
    def rows(delivery_mwh):
        return [row(2, "MI", 2020, "residential", "bundled", 160.0 * 1_000_000, 1_000_000, 90_000),
                row(2, "MI", 2020, "residential", "delivery", 60.0 * delivery_mwh, delivery_mwh, 10),
                row(91, "MI", 2020, "residential", "energy", 500_000, 10_000, 9, entity="Retail Power Marketer", observed=False)]
    m = build(rows(100))                       # 0.01% of sales
    assert m.loc[2, "supply_price_basis"] == "own_default_service_small_share"
    assert m.loc[2, "res_price"] == pytest.approx(16.0)          # 16c on both kinds of customer
    m = build(rows(100_000))                   # 9% of sales: too many to fill in from the unit's own price
    assert pd.isna(m.loc[2, "res_price"]) and m.loc[2, "supply_price_basis"] == "none_available"
    assert m.loc[2, "res_price_delivery_only"] == pytest.approx(6.0)


def test_balancing_authority_is_kept_by_state_and_year():
    """One utility id, two states in two markets, and a change of market in one of them (D-27)."""
    def r(state, year, code):
        return {**row(7, state, year, "residential", "bundled", 1_000_000, 10_000, 3_000), "balancing_authority_code_eia": code}
    rows = [r("ND", 2012, "UNK"), r("ND", 2013, "SWPP"), r("ND", 2016, "MISO"), r("ND", 2017, "MISO"),
            r("WY", 2013, "WACM"), r("WY", 2017, "WACM")]
    q, _ = panel.build(pd.DataFrame(rows), succession={})
    ba = q.set_index(["state", "year"]).balancing_authority
    assert pd.isna(ba[("ND", 2012)])                                # EIA's "UNK" is missing, not a code
    assert ba[("ND", 2013)] == "SWPP" and ba[("ND", 2017)] == "MISO"
    assert ba[("WY", 2013)] == "WACM" and ba[("WY", 2017)] == "WACM"   # Wyoming does not inherit North Dakota's code


def test_a_unit_year_with_two_codes_keeps_the_one_with_more_sales():
    big = {**row(8, "OH", 2015, "residential", "bundled", 1_000_000, 10_000, 3_000), "balancing_authority_code_eia": "PJM"}
    small = {**row(8, "OH", 2015, "commercial", "bundled", 100_000, 1_000, 30), "balancing_authority_code_eia": "MISO"}
    q, _ = panel.build(pd.DataFrame([big, small]), succession={})
    assert list(q.balancing_authority) == ["PJM"]


# ---- successions (docs/DECISIONS.md, D-21) ---------------------------------

def table(rows):
    cols = dict.fromkeys(succ.COLUMNS)
    return pd.DataFrame([{**cols, "action": "sum", "source_url": "https://example.org/order", "confidence": "high", **r}
                         for r in rows]).astype({"predecessor_id": "Int64", "successor_id": "Int64"})


def merger_rows():
    """Utility 10 is folded into utility 20 in Ohio at the end of 2010. Utility 10 also serves West Virginia."""
    rows = []
    for y in (2009, 2010):
        rows += [row(10, "OH", y, "residential", "bundled", 1_000_000, 10_000, 5_000),    # 10.0 c/kWh
                 row(10, "OH", y, "industrial", "bundled", 600_000, 10_000, 10),
                 row(20, "OH", y, "residential", "bundled", 3_600_000, 30_000, 15_000),   # 12.0 c/kWh
                 row(20, "OH", y, "commercial", "bundled", 1_000_000, 10_000, 100),
                 row(10, "WV", y, "residential", "bundled", 800_000, 10_000, 4_000)]
    rows += [row(20, "OH", 2011, "residential", "bundled", 4_800_000, 40_000, 20_000),
             row(20, "OH", 2011, "commercial", "bundled", 1_000_000, 10_000, 100),
             row(20, "OH", 2011, "industrial", "bundled", 600_000, 10_000, 10),
             row(10, "WV", 2011, "residential", "bundled", 800_000, 10_000, 4_000)]
    return rows


def test_predecessor_is_summed_into_successor_for_every_year():
    mapping = succ.resolve(table([dict(predecessor_id=10, state="OH", successor_id=20)]))
    q, o = panel.build(pd.DataFrame(merger_rows()), succession=mapping)
    m = q.merge(o, on=panel.KEYS).set_index(["utility_id_eia", "state", "year"])
    assert (10, "OH", 2009) not in m.index                      # the predecessor is no longer a unit in Ohio
    assert m.loc[(20, "OH", 2009), "res_mwh"] == pytest.approx(40_000)
    assert m.loc[(20, "OH", 2009), "total_retail_mwh"] == pytest.approx(60_000)
    assert m.loc[(20, "OH", 2009), "res_customers"] == pytest.approx(20_000)
    # no jump at the merger: the unit sold 60,000 MWh before and after
    assert m.loc[(20, "OH", 2011), "total_retail_mwh"] == pytest.approx(60_000)
    # before the merger the price is the sales-weighted blend of the two tariffs
    assert m.loc[(20, "OH", 2010), "res_price"] == pytest.approx((1_000_000 + 3_600_000) / 40_000 / 10.0)  # 11.5
    assert m.loc[(20, "OH", 2010), "n_ids_reporting"] == 2
    assert m.loc[(20, "OH", 2011), "n_ids_reporting"] == 1
    assert bool(m.loc[(20, "OH", 2011), "has_predecessors"])


def test_succession_is_by_state():
    mapping = succ.resolve(table([dict(predecessor_id=10, state="OH", successor_id=20)]))
    q, _ = panel.build(pd.DataFrame(merger_rows()), succession=mapping)
    wv = q[(q.utility_id_eia == 10) & (q.state == "WV")]
    assert sorted(wv.year) == [2009, 2010, 2011]                # the West Virginia arm is untouched
    assert (wv.res_mwh == 10_000).all()
    assert not wv.has_predecessors.any()


def test_base_years_use_the_summed_unit():
    """The 2009-2011 mean, the denominator of the load share, must not jump with the merger."""
    rows = merger_rows()
    as_reported, _ = panel.build(pd.DataFrame(rows), succession={})
    summed, _ = panel.build(pd.DataFrame(rows), succession=succ.resolve(table([dict(predecessor_id=10, state="OH", successor_id=20)])))
    base = lambda q: q[(q.utility_id_eia == 20) & q.year.isin([2009, 2010, 2011])].total_retail_mwh.mean()  # noqa: E731
    assert base(as_reported) == pytest.approx((40_000 + 40_000 + 60_000) / 3)   # understated, the bug
    assert base(summed) == pytest.approx(60_000)


def test_chains_are_followed_to_the_last_successor():
    t = table([dict(predecessor_id=1, state="IL", successor_id=2), dict(predecessor_id=2, state="IL", successor_id=3)])
    assert succ.resolve(t) == {(1, "IL"): 3, (2, "IL"): 3}
    rows = [row(1, "IL", 2004, "residential", "bundled", 100_000, 1_000, 500),
            row(2, "IL", 2004, "residential", "bundled", 200_000, 2_000, 900),
            row(3, "IL", 2004, "residential", "bundled", 300_000, 3_000, 1_500)]
    m = build(rows, succession=succ.resolve(t))
    assert list(m.index) == [3]
    assert m.loc[3, "res_mwh"] == pytest.approx(6_000)
    assert m.loc[3, "n_ids_reporting"] == 3


def test_summed_unit_takes_the_survivors_name_and_ownership():
    rows = [row(30, "LA", 2009, "residential", "bundled", 500_000, 5_000, 3_000, entity="Cooperative"),
            row(30, "LA", 2010, "residential", "bundled", 500_000, 5_000, 3_000, entity="Cooperative"),
            row(40, "LA", 2010, "residential", "bundled", 900_000, 9_000, 4_000),
            row(40, "LA", 2011, "residential", "bundled", 1_400_000, 14_000, 7_000)]
    m = build(rows, succession=succ.resolve(table([dict(predecessor_id=30, state="LA", successor_id=40)])))
    assert set(m.index) == {40}
    assert (m.ownership == "investor_owned").all()
    assert (m.utility_name == "U40").all()


def test_reported_ids_point_old_names_at_their_unit():
    mapping = succ.resolve(table([dict(predecessor_id=10, state="OH", successor_id=20)]))
    x = panel.reported_ids(pd.DataFrame(merger_rows()), succession=mapping).set_index(["utility_id_reported", "state"])
    assert x.loc[(10, "OH"), "utility_id_eia"] == 20
    assert x.loc[(10, "OH"), "reported_name"] == "U10"
    assert x.loc[(10, "OH"), "last_year"] == 2010
    assert x.loc[(10, "WV"), "utility_id_eia"] == 10


@pytest.mark.parametrize("bad, message", [
    ([dict(predecessor_id=1, state="OH", successor_id=2), dict(predecessor_id=1, state="OH", successor_id=3)], "one fate"),
    ([dict(predecessor_id=1, state="OH", successor_id=2), dict(predecessor_id=2, state="OH", successor_id=1)], "cycle"),
    ([dict(predecessor_id=1, state="OH", successor_id=2, source_url=None)], "source"),
    ([dict(predecessor_id=1, state="OH", successor_id=2, confidence="low")], "source"),
    ([dict(predecessor_id=1, state="OH", successor_id=1)], "itself"),
    ([dict(predecessor_id=1, state="OH", action="not_linked", successor_id=None)], "reason"),
    ([dict(predecessor_id=1, state="OH", action="guess", successor_id=2)], "unknown action"),
])
def test_unusable_tables_are_refused(bad, message):
    with pytest.raises(ValueError, match=message):
        succ.validate(table(bad))


# ---- the committed table itself ---------------------------------------------

def test_committed_table_is_valid_and_fully_sourced():
    t = succ.load()
    summed = t[t.action == "sum"]
    assert len(summed) >= 30
    assert summed.source_url.str.startswith("https://").all()
    assert summed.source_quote.notna().all() and summed.checked_on.notna().all()
    assert summed.effective_date.notna().all()
    blocked = ("baxtel", "datacentermap", "datacenters.com", "cleanview", "datacenterhawk")
    assert not summed.source_url.str.lower().str.contains("|".join(blocked)).any()
    assert t[t.action == "not_linked"].note.notna().all()


def test_committed_table_resolves_the_chains_we_know():
    m = succ.resolve(succ.load())
    assert m[(4062, "OH")] == 14006        # Columbus Southern Power -> Ohio Power
    assert m[(12796, "OH")] == 14006       # Monongahela Power's Ohio territory, by way of Columbus Southern
    assert m[(19436, "IL")] == 56697       # Union Electric's Illinois territory, by way of CIPS
    assert m[(7806, "LA")] == 11241        # Entergy Gulf States, by way of Entergy Gulf States Louisiana
    assert m[(7806, "TX")] == 55937
    assert {m[(i, "PA")] for i in (12390, 14711, 14716, 20387)} == {66101}
    assert (12796, "WV") not in m          # Monongahela Power is still itself in West Virginia
