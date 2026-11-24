"""EIA-861 utility x state x year panel.

Unit of analysis: one distribution utility in one state in one year. That is the
level at which a residential tariff is actually set, which is why we do not use
counties (a county "price" is an average of utility prices, and two counties
served by the same utility have the identical price by construction).

Residential price, one formula for every utility
-------------------------------------------------
EIA-861 records retail sales three ways:

  bundled   the utility sells energy AND delivers it (most of the country)
  delivery  the utility only delivers; a competitive supplier sells the energy
  energy    the competitive supplier's side of those same kWh

In retail-choice states a wires utility's own revenue understates what its
customers pay, because the supply charge is booked under the supplier. EIA does
not publish supplier revenue by wires territory, so we price those kWh at the
state's average residential energy-only price for that year:

  P = (Rev_bundled + Rev_delivery + pE_state_year * MWh_delivery)
      / (MWh_bundled + MWh_delivery)

The state price is computed from supplier rows EIA observed, not the ones it
imputed. In 42 state-years every supplier row is imputed and there is no such
price; a unit whose delivery-only customers are 1% of its sales or less is then
priced with its own implied supply price (default-service price minus
delivery-only price), and a unit above 1% is left unpriced (D-27).

For a bundled-only utility the delivery terms are zero and P is simply
revenue / sales. We also keep two secondary series for retail-choice
utilities: the delivery-only price (cleanest read on wires costs, which is
where a host utility's local grid upgrades would land) and the default-service
price (bundled rows only).

Caveat that travels with every use of P: revenue per kWh is NOT a tariff. It
moves with usage per customer and with fixed charges. The analysis therefore
always reports price, kWh per customer, and bill per customer side by side.

Known hole: in ERCOT's competitive areas retail providers report statewide, so
Oncor, CenterPoint, AEP Texas and TNMP have no usable residential revenue and
are absent from this panel. Texas co-ops and municipal utilities are present.

Successions
-----------
EIA gives a utility a new id, or folds one into another, when companies merge.
build() adds a predecessor's rows into its successor's for every year, using
the sourced table in succession.csv, so a unit is one retail territory
throughout. Before the merger the unit's price is therefore a sales-weighted
blend of tariffs that were set separately; `n_ids_reporting` marks those
unit-years (docs/DECISIONS.md, D-21).

Blinding
--------
build() returns two frames. `quantities` (sales, customers, ownership, load)
is safe to join to the data-center inventory at any time. `outcomes`
(residential revenue, price, bill) is written to data/blind/ and may only be
read through load_outcomes(), which refuses until the Gate 1 sign-off file
exists. This keeps price data out of every modeling decision made before the
pre-analysis plan is frozen. The power simulation is allowed the prices of
utilities that never host material load; it reads them from per-utility files
and does not open the file that holds everyone's.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from pipeline.electricity import availability_codes as av
from pipeline.electricity import succession as succ

ROOT = Path(__file__).resolve().parents[2]
RAW_PUDL = ROOT / "data" / "raw" / "pudl"
INTERIM = ROOT / "data" / "interim"
BLIND = ROOT / "data" / "blind"
BY_UNIT = "outcomes_by_unit"     # under BLIND: one file per utility-state
GATE_FILE = ROOT / "GATE1_SIGNED"

# Entities that own wires and set (or are assigned) a residential tariff.
# Power marketers, community choice aggregators and behind-the-meter sellers
# are suppliers, not territories, and are excluded as units.
DISTRIBUTION_ENTITIES = {
    "Investor Owned",
    "Cooperative",
    "Municipal",
    "Political Subdivision",
    "State",
    "Federal",
}
OWNERSHIP_GROUP = {
    "Investor Owned": "investor_owned",
    "Cooperative": "cooperative",
    "Municipal": "public",
    "Political Subdivision": "public",
    "State": "public",
    "Federal": "public",
}
NONRES_CLASSES = ("commercial", "industrial", "transportation")
MIN_RES_CUSTOMERS = 2000
SMALL_DELIVERY_SHARE = 0.01   # see build(): when a state-year has no observed supplier price
KEYS = ["utility_id_eia", "state", "year"]


class NonFinitePrice(ArithmeticError):
    """A priceable row's constructed price is not finite. The message never carries a value (Joe's ruling of 2026-11-16, item 1)."""


def load_sales(path: Path | None = None) -> pd.DataFrame:
    """Read the PUDL EIA-861 sales table (via DuckDB; see docs/data-sources.md)."""
    path = path or RAW_PUDL / "core_eia861__yearly_sales.parquet"
    con = duckdb.connect()
    return con.execute(
        "select utility_id_eia, state, cast(year(report_date) as integer) as year, "
        "customer_class, service_type, entity_type, data_observed, utility_name_eia, "
        "balancing_authority_code_eia, customers, sales_mwh, sales_revenue "
        f"from read_parquet('{path}')"
    ).df()


def state_energy_price(sales: pd.DataFrame) -> pd.DataFrame:
    """State-year residential energy-only price ($/MWh) from supplier rows EIA observed.

    Rows EIA imputed are left out here as they are everywhere else in the panel:
    an imputed revenue is a model, not an observation (docs/DECISIONS.md, D-27).
    """
    e = sales[(sales.customer_class == "residential") & (sales.service_type == "energy")
              & sales.data_observed.fillna(True).astype(bool)]
    g = e.groupby(["state", "year"], as_index=False)[["sales_revenue", "sales_mwh"]].sum(min_count=1)
    g = g[g.sales_mwh > 0]
    g["energy_price_state"] = g.sales_revenue / g.sales_mwh
    return g[["state", "year", "energy_price_state"]]


def state_supplier_imputation_status(sales: pd.DataFrame) -> pd.DataFrame:
    """State-year: "unknown" if any supplier row behind the state's observed energy price had no imputation flag.

    The same rows, and the same state-years, as state_energy_price (residential energy rows not flagged imputed;
    state-years with supplier sales above zero). Describes; changes nothing in the price (D-72 item 2).
    """
    kept = sales.data_observed.isna() | (sales.data_observed == True)  # noqa: E712 - object column of True/False/None
    e = sales[(sales.customer_class == "residential") & (sales.service_type == "energy") & kept]
    e = e.assign(_unknown=e.data_observed.isna())
    g = e.groupby(["state", "year"], as_index=False).agg(_mwh=("sales_mwh", lambda x: x.sum(min_count=1)), _unknown=("_unknown", "any"))
    g = g[g._mwh > 0]
    return g.assign(_supplier=g._unknown.map({True: "unknown", False: "known"}))[["state", "year", "_supplier"]]


def balancing_authority_by_year(s: pd.DataFrame) -> pd.DataFrame:
    """The balancing authority code a unit reports in a state in a year.

    Kept by utility, state and year (D-27): a utility that serves several states
    can buy in a different market in each, and a utility can change market. EIA
    reports "UNK" before 2013; that is missing, not a code. Where the rows of
    one unit-year carry more than one code (a summed unit before its merger, or
    a utility that reports two), the code with the most sales is kept.
    """
    b = s[s.balancing_authority_code_eia.notna() & (s.balancing_authority_code_eia != "UNK")]
    g = (b.assign(w=b.sales_mwh.fillna(0.0)).groupby(KEYS + ["balancing_authority_code_eia"], as_index=False).w.sum()
         .sort_values(KEYS + ["w", "balancing_authority_code_eia"], ascending=[True, True, True, False, True])
         .drop_duplicates(KEYS))
    return g.rename(columns={"balancing_authority_code_eia": "balancing_authority"})[KEYS + ["balancing_authority"]]


def _pivot(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    g = df.groupby(KEYS + ["service_type"])[["sales_revenue", "sales_mwh", "customers"]].sum(min_count=1)
    w = g.unstack("service_type")
    w.columns = [f"{prefix}_{m.replace('sales_', '')}_{s}" for m, s in w.columns]
    return w.reset_index()


def _observed_with_units(sales: pd.DataFrame, mapping: succ.Mapping) -> pd.DataFrame:
    """Observed rows, with the id EIA reported kept and `utility_id_eia` set to the unit."""
    s = sales.copy()
    # EIA flags imputed rows; an imputed revenue is a model, not an observation.
    s = s[s.data_observed.fillna(True)]
    s["utility_id_reported"] = s.utility_id_eia
    s["utility_id_eia"] = succ.apply_ids(s, mapping)
    return s


def build(sales: pd.DataFrame, succession: succ.Mapping | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (quantities, outcomes), both keyed by utility_id_eia, state, year.

    `succession` maps (reported id, state) to the unit it is summed into. The
    default is the sourced table in succession.csv; pass {} for ids as reported.
    """
    mapping = succ.resolve(succ.load()) if succession is None else succession
    s = _observed_with_units(sales, mapping)

    # Ownership: modal entity type across the utility's history (types rarely
    # change; when they do it is usually a relabel, not a change of owner).
    # A summed unit takes the type and name of the id that survives, from that
    # id's own filings.
    own_rows = s[s.utility_id_reported == s.utility_id_eia]
    ent = (
        own_rows.dropna(subset=["entity_type"])
        .groupby("utility_id_eia")["entity_type"]
        .agg(lambda x: x.value_counts().index[0])
        .rename("entity_type")
    )
    units = ent[ent.isin(DISTRIBUTION_ENTITIES)].index
    s = s[s.utility_id_eia.isin(units) & s.service_type.isin(["bundled", "delivery"])]
    own_rows = s[s.utility_id_reported == s.utility_id_eia]

    res = _pivot(s[s.customer_class == "residential"], "res")
    # Rows with no imputation flag are kept as observed (above). Say so per unit-year rather than silently:
    # "unknown" if any residential row the unit-year is built from had no flag (availability route, ruling 2).
    res_rows = s[s.customer_class == "residential"]
    imputation_status = (res_rows.assign(_unknown=res_rows.data_observed.isna()).groupby(KEYS)._unknown.any()
                         .map({True: "unknown", False: "known"}).rename(av.UNKNOWN_COL).reset_index())
    non = (
        s[s.customer_class.isin(NONRES_CLASSES)]
        .groupby(KEYS, as_index=False)["sales_mwh"].sum(min_count=1)
        .rename(columns={"sales_mwh": "nonres_mwh"})
    )
    tot = (
        s.groupby(KEYS, as_index=False)["sales_mwh"].sum(min_count=1)
        .rename(columns={"sales_mwh": "total_retail_mwh"})
    )
    names = own_rows.sort_values("year").groupby("utility_id_eia").agg(utility_name=("utility_name_eia", "last"))
    ba = balancing_authority_by_year(s)
    # How many reported ids were added together in each unit-year. More than one
    # means the price that year blends tariffs that were set separately.
    n_ids = (
        s.groupby(KEYS).utility_id_reported.nunique().rename("n_ids_reporting").reset_index()
    )
    absorbed = {(u, st) for (_, st), u in mapping.items()}

    p = (res.merge(non, on=KEYS, how="left").merge(tot, on=KEYS, how="left").merge(n_ids, on=KEYS, how="left")
         .merge(ba, on=KEYS, how="left"))
    p["has_predecessors"] = [(u, st) in absorbed for u, st in zip(p.utility_id_eia, p.state)]
    for c in ["res_revenue_bundled", "res_mwh_bundled", "res_customers_bundled",
              "res_revenue_delivery", "res_mwh_delivery", "res_customers_delivery"]:
        if c not in p:
            p[c] = np.nan
    p = p.merge(state_energy_price(sales), on=["state", "year"], how="left")
    p = p.join(ent, on="utility_id_eia").join(names, on="utility_id_eia")
    p["ownership"] = p.entity_type.map(OWNERSHIP_GROUP)

    z = lambda c: p[c].fillna(0.0)  # noqa: E731
    p["res_mwh"] = z("res_mwh_bundled") + z("res_mwh_delivery")
    p["res_customers"] = z("res_customers_bundled") + z("res_customers_delivery")
    p["delivery_share"] = np.where(p.res_mwh > 0, z("res_mwh_delivery") / p.res_mwh, np.nan)

    # Supply for delivery-only customers is priced at the state's observed supplier
    # average. Where a state-year has no observed supplier row (EIA imputed them all),
    # there is no such price. If the unit's delivery-only customers are a trace of its
    # sales (SMALL_DELIVERY_SHARE or less) their supply is priced at the unit's own
    # implied supply price, default-service price minus delivery-only price, so a
    # large utility is not dropped for a few customers on competitive supply. Above
    # that share the row is left missing rather than silently treating supply as free.
    needs_energy = z("res_mwh_delivery") > 0
    own_supply = np.where(
        (z("res_mwh_bundled") > 0) & needs_energy,
        p.res_revenue_bundled / p.res_mwh_bundled.replace(0, np.nan)
        - p.res_revenue_delivery / p.res_mwh_delivery.replace(0, np.nan), np.nan)
    use_own = needs_energy & p.energy_price_state.isna() & (p.delivery_share <= SMALL_DELIVERY_SHARE) & (own_supply > 0)
    supply_price = np.where(use_own, own_supply, p.energy_price_state)
    p["supply_price_basis"] = np.select(
        [~needs_energy, use_own, p.energy_price_state.notna()],
        ["no_delivery_only_customers", "own_default_service_small_share", "state_observed_suppliers"], "none_available")
    imputed_supply = z("res_mwh_delivery") * supply_price
    full_rev = z("res_revenue_bundled") + z("res_revenue_delivery") + np.nan_to_num(imputed_supply, nan=0.0)
    priceable = (p.res_mwh > 0) & ~(needs_energy & np.isnan(supply_price.astype(float)))
    # Revenue must exist wherever sales exist.
    priceable &= ~((z("res_mwh_bundled") > 0) & p.res_revenue_bundled.isna())
    priceable &= ~((z("res_mwh_delivery") > 0) & p.res_revenue_delivery.isna())

    p["res_revenue_full"] = np.where(priceable, full_rev, np.nan)
    p["res_price"] = p.res_revenue_full / p.res_mwh / 10.0  # cents per kWh
    p["res_price_delivery_only"] = np.where(
        z("res_mwh_delivery") > 0, p.res_revenue_delivery / p.res_mwh_delivery / 10.0, np.nan)
    p["res_price_default_service"] = np.where(
        z("res_mwh_bundled") > 0, p.res_revenue_bundled / p.res_mwh_bundled / 10.0, np.nan)
    p["res_kwh_per_customer_month"] = np.where(
        p.res_customers > 0, p.res_mwh * 1000.0 / p.res_customers / 12.0, np.nan)
    p["res_bill_per_customer_month"] = np.where(
        p.res_customers > 0, p.res_revenue_full / p.res_customers / 12.0, np.nan)

    p["meets_size_floor"] = p.res_customers >= MIN_RES_CUSTOMERS

    # Outcome availability (D-58 rule 6; docs/gate1/availability-audit-route.md, Joe's ruling of 2026-11-16).
    # The flag IS the analysis's filter (power_simulation.py: meets_size_floor & res_price > 0, a missing price
    # failing). The reason is the first applicable exclusion reason, from the masks above and nothing else.
    # Nothing here changes how the price is built.
    if (priceable & ~np.isfinite(p.res_price.astype(float))).any():
        raise NonFinitePrice("a priceable row's constructed price is not finite; stopped without showing values")
    p[av.FLAG_COL] = (p.meets_size_floor & (p.res_price > 0)).astype(bool)
    no_supply = needs_energy & np.isnan(supply_price.astype(float))
    p[av.REASON_COL] = np.select(
        [~(p.res_mwh > 0), ~p.meets_size_floor, no_supply,
         (z("res_mwh_bundled") > 0) & p.res_revenue_bundled.isna(),
         (z("res_mwh_delivery") > 0) & p.res_revenue_delivery.isna(),
         ~(p.res_price > 0)],
        list(av.BUILD_REASONS), av.NO_EXCLUSION)
    if not ((p[av.REASON_COL] == av.NO_EXCLUSION) == p[av.FLAG_COL]).all():
        raise AssertionError("the availability flag and the first exclusion reason disagree on some row")
    p = p.merge(imputation_status, on=KEYS, how="left")
    p = p.merge(state_supplier_imputation_status(sales), on=["state", "year"], how="left")
    uses_suppliers = p.supply_price_basis == "state_observed_suppliers"
    if p.loc[uses_suppliers, "_supplier"].isna().any():
        raise AssertionError("a unit-year priced at the state's supplier average has no supplier rows behind it")
    p[av.SUPPLIER_COL] = np.where(uses_suppliers, p["_supplier"], "not_used")
    p = p.drop(columns="_supplier")

    quantity_cols = KEYS + [
        "utility_name", "entity_type", "ownership", "balancing_authority",
        "res_mwh", "res_mwh_bundled", "res_mwh_delivery", "res_customers",
        "delivery_share", "supply_price_basis", "nonres_mwh", "total_retail_mwh", "meets_size_floor",
        "n_ids_reporting", "has_predecessors", *av.NEW_QUANTITY_COLS,
    ]
    outcome_cols = KEYS + [
        "res_revenue_full", "res_price", "res_price_delivery_only",
        "res_price_default_service", "res_bill_per_customer_month",
        "res_kwh_per_customer_month", "energy_price_state",
    ]
    return p[quantity_cols].copy(), p[outcome_cols].copy()


def reported_ids(sales: pd.DataFrame, succession: succ.Mapping | None = None) -> pd.DataFrame:
    """One row per id as EIA reported it in a state: its last name and the unit it belongs to.

    Hand verification names utilities as sources name them ("West Penn Power").
    This is how such a name finds its unit after the unit has been summed.
    """
    mapping = succ.resolve(succ.load()) if succession is None else succession
    s = _observed_with_units(sales, mapping)
    s = s[s.service_type.isin(["bundled", "delivery"])]
    g = (
        s.sort_values("year").groupby(["utility_id_reported", "state"])
        .agg(reported_name=("utility_name_eia", "last"), utility_id_eia=("utility_id_eia", "last"),
             first_year=("year", "min"), last_year=("year", "max"))
        .reset_index()
    )
    return g


def unit_file(utility_id_eia, state) -> Path:
    """The file that holds one utility-state's outcome rows and nobody else's."""
    return BLIND / BY_UNIT / f"{int(utility_id_eia)}_{state}.parquet"


def write(quantities: pd.DataFrame, outcomes: pd.DataFrame) -> None:
    """Write quantities, the whole outcome file, and one outcome file per utility-state.

    The per-unit files exist so that a reader allowed to see some utilities'
    prices can open those utilities' files and no others (load_outcomes).
    """
    INTERIM.mkdir(parents=True, exist_ok=True)
    BLIND.mkdir(parents=True, exist_ok=True)
    quantities.to_parquet(INTERIM / "panel_quantities.parquet", index=False)
    outcomes.to_parquet(BLIND / "panel_outcomes.parquet", index=False)
    by_unit = BLIND / BY_UNIT
    if by_unit.exists():
        shutil.rmtree(by_unit)          # a unit that no longer exists must not leave a file behind
    by_unit.mkdir(parents=True)
    for (u, st), rows in outcomes.groupby(["utility_id_eia", "state"], sort=False):
        rows.to_parquet(unit_file(u, st), index=False)


def load_quantities() -> pd.DataFrame:
    return pd.read_parquet(INTERIM / "panel_quantities.parquet")


def load_reported_ids() -> pd.DataFrame:
    return pd.read_parquet(INTERIM / "panel_reported_ids.parquet")


def load_outcomes(*, purpose: str, units: pd.DataFrame | None = None) -> pd.DataFrame:
    """Read residential price outcomes. Refuses before the Gate 1 sign-off.

    Two exceptions, both from docs/DECISIONS.md (D-6, D-12):

    `purpose="construction_qa"` permits summary checks of the price series on
    its own (coverage, plausibility against EIA's published averages). It must
    never be joined to treatment before sign-off.

    `purpose="power_simulation"` returns the rows of the utilities named in
    `units` (columns utility_id_eia, state) and nothing else. It opens one file
    per named utility-state and never opens the whole outcome file, so the rows
    of every other utility stay on disk, unread by the program (D-26, D-27).
    The caller passes utilities that never host material data center load. A
    named unit with no outcome file has no residential rows and is skipped.
    """
    if purpose == "power_simulation":
        if units is None:
            raise PermissionError("The power simulation must name the never-treated utilities it reads.")
        named = units[["utility_id_eia", "state"]].drop_duplicates()
        files = [f for f in (unit_file(u, st) for u, st in zip(named.utility_id_eia, named.state)) if f.exists()]
        if not files:
            return pd.DataFrame(columns=["utility_id_eia", "state", "year"])
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    if purpose != "construction_qa" and not GATE_FILE.exists():
        raise PermissionError(
            "Residential price outcomes are blinded until the pre-analysis plan is "
            "frozen and GATE1_SIGNED exists at the repo root."
        )
    return pd.read_parquet(BLIND / "panel_outcomes.parquet")
