#!/usr/bin/env python3
"""Stage 03 — join PLUTO geometry + PVAD valuation, compute estimated tax bill.

Inputs (in raw/):
    pluto.<tag>.geojson   from stage 01 (DCP MapPLUTO ArcGIS export)
    pvad.<tag>.csv        from stage 02 (DOF 8y4t-faws on Socrata)

Outputs (in output/):
    parcels_with_tax.geojson   PLUTO geometry + selected attrs + tax_bill,
                               etr, tax_per_sqft, data_quality flags

Tax-bill formula:
    bill = max(0, curtxbtot - curtxbextot) * rate[class]

    curtxbtot is the gross billable AV (post-transitional, pre-exemption).
    curtxbextot is the BILLABLE exempt total — the part of curtxbtot
    exempted under 421-a, 485-x, and other pre-bill exemptions. For
    actively-abated 421-a / 485-x parcels curtxbextot can equal
    curtxbtot, leaving a real bill near zero. (An earlier version of
    this pipeline read curtxbtot as "already net of exemptions" and
    skipped the subtraction; that overstated bills by a factor of
    ~1/(1 - exempt_fraction) on the entire abated stock.)

    Still missed: post-bill dollar abatements (J-51, ICAP, SCHE/DHE)
    that are credited as a flat amount AFTER the rate is applied.
    Those can show ~5–10% divergence from DOF's published bill on
    affected parcels.

ETR denominator: PVAD curmkttot (DOF estimated market value). This is the
canonical "fair share" denominator used by Furman / IBO / the 2021 NYC
Advisory Commission on Property Tax Reform.
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

import config

CLASS_1 = {"1", "1A", "1B", "1C", "1D"}
CLASS_2_SMALL = {"2A", "2B", "2C"}
CLASS_2_LARGE = {"2"}
CLASS_4 = {"4"}


def normalize_bbl(value) -> str | None:
    """Both PLUTO BBL ('3000430021.0') and PVAD parid ('3000430021 XXX')
    normalize to the same 10-char zero-padded string."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    # parid format: '3000430021 XXX' or '3000430021EX1' — take leading digits.
    s_clean = "".join(c for c in s.split()[0] if c.isdigit() or c == ".")
    try:
        return str(int(float(s_clean))).zfill(10)
    except (ValueError, TypeError):
        return None


def clean_class(value) -> str | None:
    """PVAD tax-class strings come through as '4.0' or '2A'; normalize to '4' / '2A'."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip().upper()
    if not s:
        return None
    # Drop trailing '.0' on numeric-only classes.
    if s.endswith(".0"):
        s = s[:-2]
    return s


def get_billable(row) -> tuple[float, float, float, str | None]:
    """Return (market_value, billable_av, billable_exempt, tax_class).

    MV / billable AV / billable exempt come from the first period
    (cur > fin > ten) that has a positive curmkttot. Tax class is taken
    from the FIRST non-null class across all four prefixes
    (cur > fin > cbn > ten), even if its MV row was empty. Some parcels
    have MV populated only on the 'cur' row but tax class only on 'ten'
    or 'fin' (~10% of citywide parcels).

    billable_exempt = curtxbextot is the portion of curtxbtot exempt
    under 421-a, 485-x, and other pre-bill exemptions; the caller
    subtracts it before applying the rate."""
    mv_val = 0.0
    txb_val = 0.0
    txbex_val = 0.0
    for prefix in ("cur", "fin", "ten"):
        mv = row.get(f"{prefix}mkttot")
        txb = row.get(f"{prefix}txbtot")
        txbex = row.get(f"{prefix}txbextot")
        if pd.notna(mv) and float(mv) > 0:
            mv_val = float(mv)
            txb_val = float(txb) if pd.notna(txb) else 0.0
            txbex_val = float(txbex) if pd.notna(txbex) else 0.0
            break
    cls: str | None = None
    for prefix in ("cur", "fin", "cbn", "ten"):
        c = clean_class(row.get(f"{prefix}taxclass"))
        if c:
            cls = c
            break
    return (mv_val, txb_val, txbex_val, cls)


def compute_bill(
    billable_av: float,
    billable_exempt: float,
    tax_class: str | None,
    rates: dict,
) -> float | None:
    if not tax_class:
        return None
    cls = tax_class.upper().strip()
    if cls in CLASS_1:
        rate = rates.get("1", 0)
    elif cls in CLASS_2_SMALL or cls in CLASS_2_LARGE:
        rate = rates.get("2", 0)
    elif cls in CLASS_4:
        rate = rates.get("4", 0)
    else:
        return None  # Class 3 utilities — billed differently
    return max(0.0, billable_av - billable_exempt) * rate


def parse_condo_number(value) -> tuple[int, int] | None:
    """Parse PVAD's condo_number ('100944') into (borocode, condono) matching
    PLUTO's (BoroCode, CondoNo). PVAD format is f"{borocode}{condono:05d}":
    leading digit is borough (1-5), remaining 5 digits are zero-padded
    CondoNo. Returns None for missing/invalid values.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s.isdigit() or len(s) < 2:
        return None
    boro = int(s[0])
    if boro not in (1, 2, 3, 4, 5):
        return None
    try:
        condono = int(s[1:])
    except ValueError:
        return None
    if condono <= 0:
        return None
    return (boro, condono)


def build_condo_lot_lookup(pluto_features: list) -> dict:
    """From PLUTO features, build (BoroCode, CondoNo) -> [(lot_bbl, weight), ...].

    Each condominium has at least one PLUTO polygon at the "lot BBL" — by NYC
    convention typically Lot in [7501, 7599] (the billing-lot range). Most
    condos resolve to a single lot; about 0.2% of CondoNos span 2+ lot
    polygons (multi-tower complexes like Tribeca Green or Yorkville Towers
    where two physical buildings share one condo declaration).

    For multi-lot condos we return all the lots with weights proportional
    to BldgArea, so the aggregated financials get split across the polygons
    rather than dumped onto one and missing on the others.

    For groups with no Lot in [7501, 7599], we fall back to using all
    candidate polygons (still weighted by BldgArea) since the billing-lot
    convention isn't universal.
    """
    candidates: dict[tuple[int, int], list[tuple[str, int, float]]] = {}
    for feat in pluto_features:
        p = feat.get("properties", {})
        condono_raw = p.get("CondoNo")
        if condono_raw is None or (isinstance(condono_raw, float) and pd.isna(condono_raw)):
            continue
        try:
            condono_i = int(condono_raw)
        except (TypeError, ValueError):
            continue
        if condono_i <= 0:
            continue
        try:
            borocode_i = int(p.get("BoroCode") or 0)
        except (TypeError, ValueError):
            continue
        if borocode_i not in (1, 2, 3, 4, 5):
            continue
        bbl_n = normalize_bbl(p.get("BBL") or p.get("bbl"))
        if not bbl_n:
            continue
        try:
            lot_i = int(p.get("Lot") or 0)
        except (TypeError, ValueError):
            lot_i = 0
        try:
            ba_f = float(p.get("BldgArea") or 0)
        except (TypeError, ValueError):
            ba_f = 0.0
        candidates.setdefault((borocode_i, condono_i), []).append((bbl_n, lot_i, ba_f))

    lookup: dict[tuple[int, int], list[tuple[str, float]]] = {}
    multi_lot = 0
    fallback_used = 0
    for key, cands in candidates.items():
        billing = [c for c in cands if 7501 <= c[1] <= 7599]
        chosen = billing if billing else cands
        if not billing:
            fallback_used += 1
        if len(chosen) > 1:
            multi_lot += 1
        total_area = sum(c[2] for c in chosen)
        if total_area > 0:
            weights = [(c[0], c[2] / total_area) for c in chosen]
        else:
            # No BldgArea — split evenly.
            even = 1.0 / len(chosen)
            weights = [(c[0], even) for c in chosen]
        lookup[key] = weights
    print(f"  condo lot lookup: {len(lookup):,} CondoNos, "
          f"{multi_lot:,} multi-lot ({multi_lot*100/max(1,len(lookup)):.1f}%)"
          f"{f', {fallback_used:,} fallback (no Lot in [7501,7599])' if fallback_used else ''}")
    return lookup


def aggregate_condo_units(pvad: "pd.DataFrame", condo_lookup: dict, rates: dict) -> "pd.DataFrame":
    """Replace per-unit PVAD rows with one aggregated row per condo lot.

    Condo units in NYC are billed per-unit (each unit has its own BBL), but
    PLUTO publishes one polygon per condo *lot*. To make the lot polygon
    paint with real values, we sum the unit-level financials and key the
    result by the lot BBL (looked up via PLUTO's CondoNo).

    Tax bills are computed per-unit using each unit's own tax class (units
    can span Class 2 residential and Class 4 commercial within a single
    condo), then summed. Aggregating billable AVs and applying a single rate
    would be wrong for mixed-class condos.
    """
    if "condo_number" not in pvad.columns:
        return pvad

    pvad = pvad.copy()
    keys = pvad["condo_number"].apply(parse_condo_number)
    pvad["_condo_key"] = keys
    is_condo_unit = pvad["_condo_key"].apply(
        lambda k: k is not None and k in condo_lookup
    )
    units = pvad[is_condo_unit].copy()
    non_condo = pvad[~is_condo_unit].drop(columns=["_condo_key"])

    if len(units) == 0:
        print("  condo aggregation: 0 unit rows matched a PLUTO condo lot")
        return non_condo

    # Per-parid: pick the most recent year, max curmkttot within that year.
    # PVAD ships 5 year-rows per parid (2023–2027) and 2× duplicate rows per
    # (parid, year) (sometimes tentative vs. final roll with different MVs).
    # Without this collapse the aggregator sums all of them — ~8× inflation
    # on every condo, plus uneven coverage when condos lag a year. Doing it
    # per-parid (rather than globally taking max(year) across the whole set)
    # keeps condos whose latest available data is 2026 — taking a global
    # 2027 max would drop their lot polygon from the join entirely.
    n_before = len(units)
    if "year" in units.columns:
        units = (
            units.sort_values(
                ["parid", "year", "curmkttot"],
                ascending=[True, False, False],
                na_position="last",
            )
            .drop_duplicates(subset=["parid"], keep="first")
        )
        year_counts = units["year"].astype(str).value_counts().sort_index(ascending=False)
        year_breakdown = ", ".join(f"{y}={n:,}" for y, n in year_counts.head(3).items())
    else:
        units = units.drop_duplicates(subset=["parid"], keep="first")
        year_breakdown = "(no year column)"
    print(
        f"  condo units after per-parid year+dedup: {len(units):,} "
        f"(from {n_before:,}); years: {year_breakdown}"
    )

    # Per-unit bill: replicate get_billable's logic inline so we can compute
    # one bill per unit using its own class and its own billable exempt.
    def _per_unit(row):
        mv, txb, txbex, cls = 0.0, 0.0, 0.0, None
        for prefix in ("cur", "fin", "ten"):
            mv_v = row.get(f"{prefix}mkttot")
            if pd.notna(mv_v) and float(mv_v) > 0:
                mv = float(mv_v)
                txb_v = row.get(f"{prefix}txbtot")
                txbex_v = row.get(f"{prefix}txbextot")
                txb = float(txb_v) if pd.notna(txb_v) else 0.0
                txbex = float(txbex_v) if pd.notna(txbex_v) else 0.0
                break
        for prefix in ("cur", "fin", "cbn", "ten"):
            c = clean_class(row.get(f"{prefix}taxclass"))
            if c:
                cls = c
                break
        bill = compute_bill(txb, txbex, cls, rates) if cls else None
        return pd.Series({
            "_unit_mv": mv,
            "_unit_txb": txb,
            "_unit_txbex": txbex,
            "_unit_cls": cls,
            "_unit_bill": bill or 0.0,
        })

    print(f"  computing per-unit bills for {len(units):,} condo unit rows...")
    per_unit_df = units.apply(_per_unit, axis=1)
    units = pd.concat([units, per_unit_df], axis=1)

    def _modal(s):
        s = s.dropna()
        if len(s) == 0:
            return None
        m = s.mode()
        return m.iat[0] if len(m) else s.iat[0]

    # Build the aggregation dict dynamically so we don't reference columns
    # that aren't present (some PVAD periods may be missing in older raw files).
    agg_spec = {
        "curmkttot": ("curmkttot", "sum"),
        "curacttot": ("curacttot", "sum"),
        "curactextot": ("curactextot", "sum"),
        "curtxbtot": ("curtxbtot", "sum"),
        "curtxbextot": ("curtxbextot", "sum"),
        "_bill_sum": ("_unit_bill", "sum"),
        "_mv_sum": ("_unit_mv", "sum"),
        "_txb_sum": ("_unit_txb", "sum"),
        "_txbex_sum": ("_unit_txbex", "sum"),
        "curtaxclass": ("curtaxclass", _modal),
        "bldg_class": ("bldg_class", _modal),
        "units_aggregated": ("parid", "count"),
    }
    for c in ("finmkttot", "finacttot", "finactextot", "fintxbtot", "fintxbextot",
             "tenmkttot", "fintaxclass", "tentaxclass"):
        if c in units.columns:
            agg_spec[c] = (c, "sum" if not c.endswith("taxclass") else _modal)

    grouped = units.groupby("_condo_key", dropna=False).agg(**agg_spec).reset_index()

    # Expand each (boro, condono) group into one row per lot polygon, splitting
    # financials by BldgArea weight. Most condos are single-lot (weight=1.0);
    # multi-tower condos sharing one CondoNo get proportionally distributed
    # so each tower polygon paints with its share of the burden.
    weighted_cols = [
        "curmkttot", "curacttot", "curactextot", "curtxbtot", "curtxbextot",
        "_bill_sum", "_mv_sum", "_txb_sum", "_txbex_sum",
        "finmkttot", "finacttot", "finactextot", "fintxbtot", "fintxbextot",
        "tenmkttot",
    ]
    expanded_rows = []
    n_emitted_for_multi = 0
    for _, row in grouped.iterrows():
        key = row["_condo_key"]
        lot_weights = condo_lookup.get(key) or []
        if not lot_weights:
            continue
        if len(lot_weights) > 1:
            n_emitted_for_multi += len(lot_weights)
        for bbl_n, weight in lot_weights:
            new = row.to_dict()
            for col in weighted_cols:
                if col in new and new[col] is not None and not pd.isna(new[col]):
                    new[col] = float(new[col]) * weight
            new["bbl_norm"] = bbl_n
            new["parid"] = bbl_n
            new["aggregation"] = "condo"
            ua_val = row.get("units_aggregated")
            try:
                ua_int = int(ua_val) if ua_val is not None and not pd.isna(ua_val) else 0
            except (TypeError, ValueError):
                ua_int = 0
            new["units_aggregated"] = int(round(ua_int * weight))
            # Pre-aggregated bill / MV — used in the main loop to override the
            # standard class*rate computation, which doesn't work for mixed-
            # class condos.
            new["_pre_aggregated_bill"] = new["_bill_sum"]
            new["_pre_aggregated_mv"] = new["_mv_sum"]
            # MV-by-year history is per-unit-BBL; summing across units fakes
            # growth when unit count drifted (newer condo declarations missing
            # rows in early years). Suppress so the popup shows methodology
            # only, no delta. The condo-aggregation caveat already explains
            # why per-unit detail is rolled up.
            new["mv_y2023"] = None
            new["mv_y2026"] = None
            # Owner: blank out so the main loop falls back to PLUTO's
            # OwnerName (modal unit-owner is misleading for a multi-unit
            # building).
            new["owner"] = None
            expanded_rows.append(new)

    expanded_df = pd.DataFrame(expanded_rows)
    expanded_df = expanded_df.drop(
        columns=["_condo_key", "_bill_sum", "_mv_sum", "_txb_sum", "_txbex_sum"],
        errors="ignore",
    )

    print(f"  condo aggregation: {len(units):,} unit rows -> "
          f"{len(expanded_df):,} condo lot rows ({len(grouped):,} CondoNos, "
          f"{n_emitted_for_multi:,} extra rows from multi-lot splits)")
    if len(expanded_df):
        big_idx = expanded_df["units_aggregated"].astype(int).idxmax()
        big = expanded_df.loc[big_idx]
        print(f"  largest aggregate: parid={big['parid']} "
              f"({int(big['units_aggregated']):,} units, "
              f"${float(big['_pre_aggregated_mv']):,.0f} MV, "
              f"${float(big['_pre_aggregated_bill']):,.0f} bill)")

    return pd.concat([non_condo, expanded_df], ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pluto", required=True)
    ap.add_argument(
        "--pvad",
        required=True,
        nargs="+",
        help="One or more PVAD CSV paths (multiple = concatenated). "
        "Use shell globs to pass all 5 boroughs.",
    )
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    print(f"Loading PLUTO: {args.pluto}")
    with open(args.pluto) as f:
        pluto_fc = json.load(f)
    n_pluto = len(pluto_fc["features"])
    print(f"  {n_pluto:,} features")

    print(f"Loading PVAD: {args.pvad}")
    parts = []
    for path in args.pvad:
        # `on_bad_lines="skip"` defends against the rare truncated row at EOF
        # when the Socrata stream gets cut off mid-line.
        df = pd.read_csv(path, dtype=str, low_memory=False, on_bad_lines="skip")
        # Drop rows with no current market value before dedup. PVAD ships
        # multiple period rows per BBL (TENT, FINAL, CURR, etc.); the zero-
        # everything rows are placeholders we don't need.
        cur = pd.to_numeric(df["curmkttot"], errors="coerce")
        df = df.loc[(cur.notna()) & (cur > 0)]
        print(f"  {path}: {len(df):,} rows after dropping zero-curmkttot")
        parts.append(df)
    pvad = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
    print(f"  concatenated: {len(pvad):,} rows")
    pvad["bbl_norm"] = pvad["parid"].apply(normalize_bbl)
    # Numeric coerce. EXCLUDE *taxclass — those are string codes like "2A"
    # that pd.to_numeric would silently turn into NaN.
    numeric_cols = [
        c for c in pvad.columns
        if (c.startswith(("cur", "fin", "ten", "cbn", "py"))
            and not c.endswith("taxclass"))
        or c in {"gross_sqft", "residential_area_gross", "office_area_gross",
                 "retail_area_gross", "factory_area_gross", "warehouse_area_gross",
                 "garage_area", "land_area", "num_bldgs", "yrbuilt", "units",
                 "coop_apts"}
    ]
    for c in numeric_cols:
        if c in pvad.columns and pvad[c].dtype == object:
            pvad[c] = pd.to_numeric(pvad[c], errors="coerce")

    # Extract per-BBL MV history by PVAD year. Each BBL has up to 5 year-rows
    # (2023-2027) all carrying curmkttot. We project two snapshots into the
    # output: mv_y2023 (the oldest fully-populated FY in the dataset) and
    # mv_y2026 (the most recent finalized roll). The popup uses the pair to
    # render "Up X% since 2023" — directly answering "when was this MV
    # determined?" without trying to fold the whole trajectory into a chart.
    print("Extracting MV-by-year per BBL (mv_y2023, mv_y2026)...")
    mv_by_year = (
        pvad[["bbl_norm", "year", "curmkttot"]]
        .dropna(subset=["bbl_norm", "year", "curmkttot"])
        .groupby(["bbl_norm", "year"])["curmkttot"]
        .max()
        .unstack(fill_value=None)
    )
    for year_str in ("2023", "2026"):
        out_col = f"mv_y{year_str}"
        if year_str in mv_by_year.columns:
            pvad[out_col] = pvad["bbl_norm"].map(mv_by_year[year_str])
        else:
            pvad[out_col] = None

    rates = config.TAX_RATES_DEFAULT
    print(f"Tax rates (verify with DOF Annual Tax Rate notice): {rates}")

    # Condo aggregation. PLUTO has one polygon per condo lot; PVAD has one
    # row per condo unit. We sum the per-unit financials and re-key the
    # aggregate to the lot BBL via PLUTO's CondoNo, so the lot polygon paints
    # with real values instead of rendering blank/em-dash.
    print("Building PLUTO condo lot lookup...")
    condo_lookup = build_condo_lot_lookup(pluto_fc["features"])
    if len(condo_lookup):
        pvad = aggregate_condo_units(pvad, condo_lookup, rates)
        print(f"  PVAD rows after condo aggregation: {len(pvad):,}")

    # If multiple PVAD rows share a BBL, keep the one with the highest curmkttot
    # (drops stub records with all-zero values).
    pvad = pvad.sort_values("curmkttot", ascending=False, na_position="last")
    pvad = pvad.drop_duplicates("bbl_norm", keep="first")
    pvad_by_bbl = pvad.set_index("bbl_norm").to_dict(orient="index")

    matched = 0
    out_features = []
    for feat in pluto_fc["features"]:
        props = feat.get("properties", {})
        bbl = normalize_bbl(props.get("BBL") or props.get("bbl"))
        pv = pvad_by_bbl.get(bbl) if bbl else None

        out_props = {
            "bbl": bbl,
            "address": props.get("Address"),
            "borough": props.get("Borough"),
            "cd": props.get("CD"),
            "bct2020": props.get("BCT2020"),
            "owner": (pv or {}).get("owner") or props.get("OwnerName"),
            "bldg_class": props.get("BldgClass") or (pv or {}).get("bldg_class"),
            "land_use": props.get("LandUse"),
            "year_built": props.get("YearBuilt") or (pv or {}).get("yrbuilt"),
            "lot_area": props.get("LotArea") or (pv or {}).get("land_area"),
            "bldg_area": props.get("BldgArea") or (pv or {}).get("gross_sqft"),
            "units_res": props.get("UnitsRes"),
            "units_total": props.get("UnitsTotal") or (pv or {}).get("units"),
            "num_floors": props.get("NumFloors"),
            "lat": props.get("Latitude"),
            "lon": props.get("Longitude"),
            "zipcode": props.get("ZipCode") or (pv or {}).get("zip_code"),
        }

        if pv:
            matched += 1
            agg_field = pv.get("aggregation")
            is_condo_agg = isinstance(agg_field, str) and agg_field == "condo"
            if is_condo_agg:
                # Pre-summed in aggregate_condo_units. Use the per-unit-then-
                # summed bill rather than recomputing — units in one condo can
                # span tax classes (Class 2 residential + Class 4 garage), and
                # applying a single class rate to a summed billable AV would
                # be wrong.
                def _f(v):
                    if v is None or (isinstance(v, float) and pd.isna(v)):
                        return 0.0
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return 0.0
                mv = _f(pv.get("_pre_aggregated_mv"))
                bill = _f(pv.get("_pre_aggregated_bill"))
                billable_av = _f(pv.get("curtxbtot"))
                billable_exempt = _f(pv.get("curtxbextot"))
                tax_class = pv.get("curtaxclass") or pv.get("fintaxclass")
                if isinstance(tax_class, str):
                    tax_class = tax_class.strip().upper() or None
                else:
                    tax_class = None
                out_props["aggregation"] = "condo"
                ua = pv.get("units_aggregated")
                try:
                    out_props["units_aggregated"] = int(ua) if ua is not None and not pd.isna(ua) else None
                except (TypeError, ValueError):
                    out_props["units_aggregated"] = None
            else:
                mv, billable_av, billable_exempt, tax_class = get_billable(pv)
                bill = compute_bill(billable_av, billable_exempt, tax_class, rates)
            out_props["tax_class"] = tax_class
            out_props["market_value"] = round(mv, 2) if mv else None
            out_props["billable_av"] = round(billable_av, 2) if billable_av else None
            out_props["billable_exempt"] = (
                round(billable_exempt, 2) if billable_exempt else None
            )
            out_props["tax_bill"] = round(bill, 2) if bill is not None else None
            out_props["etr"] = round(bill / mv, 5) if (bill is not None and mv > 0) else None

            # MV history. Stored as integer dollars (no need for cents on
            # multi-million-dollar denominators) for tile compression.
            for hist_col in ("mv_y2023", "mv_y2026"):
                v = pv.get(hist_col)
                try:
                    f = float(v) if v is not None and not pd.isna(v) else None
                except (TypeError, ValueError):
                    f = None
                out_props[hist_col] = int(round(f)) if (f is not None and f > 0) else None
            try:
                ba_f = float(out_props["bldg_area"] or 0)
            except (TypeError, ValueError):
                ba_f = 0
            out_props["tax_per_sqft"] = (
                round(bill / ba_f, 2) if (bill is not None and ba_f > 0) else None
            )
            # Abatement / exemption signal. PVAD's curactextot is the
            # current actual exempt total (the AV that DOF subtracts before
            # taxing). Ratio against curacttot gives a 0–1 abatement-
            # intensity score; absolute value goes in the parcel detail.
            actextot = pv.get("curactextot")
            acttot = pv.get("curacttot") or pv.get("curactextot")
            try:
                actextot_f = float(actextot) if actextot is not None and not pd.isna(actextot) else 0.0
                acttot_f = float(acttot) if acttot is not None and not pd.isna(acttot) else 0.0
            except (TypeError, ValueError):
                actextot_f, acttot_f = 0.0, 0.0
            out_props["exempt_total"] = round(actextot_f, 2) if actextot_f > 0 else None
            if acttot_f > 0 and actextot_f > 0:
                out_props["exempt_fraction"] = round(min(1.0, actextot_f / acttot_f), 4)
            else:
                out_props["exempt_fraction"] = 0.0 if acttot_f > 0 else None
        else:
            out_props.update({
                "tax_class": None, "market_value": None, "billable_av": None,
                "billable_exempt": None,
                "tax_bill": None, "etr": None, "tax_per_sqft": None,
                "exempt_total": None, "exempt_fraction": None,
                "mv_y2023": None, "mv_y2026": None,
            })

        # Quality flags (surfaced in the map UI).
        flags = []
        if not pv:
            flags.append("no_pvad_match")
        elif not out_props["market_value"]:
            flags.append("no_market_value")
        bc = (out_props["bldg_class"] or "").upper()
        if bc.startswith("C6"):
            flags.append("coop_dof_mv_low")
        out_props["data_quality"] = ",".join(flags) if flags else "ok"

        out_features.append({
            "type": "Feature",
            "geometry": feat.get("geometry"),
            "properties": out_props,
        })

    n_condo_agg = sum(
        1 for f in out_features if f["properties"].get("aggregation") == "condo"
    )
    units_in_condo_agg = sum(
        f["properties"].get("units_aggregated") or 0
        for f in out_features
        if f["properties"].get("aggregation") == "condo"
    )
    print(f"PLUTO features: {n_pluto:,}")
    print(f"PVAD-matched:   {matched:,}  ({matched / max(1, n_pluto):.1%})")
    print(f"Condo aggregates in output: {n_condo_agg:,} lots covering {units_in_condo_agg:,} unit BBLs")
    bills = [f["properties"]["tax_bill"] for f in out_features if f["properties"]["tax_bill"]]
    etrs = [f["properties"]["etr"] for f in out_features if f["properties"]["etr"]]
    if bills:
        s = pd.Series(bills)
        print(f"Tax bill: median ${s.median():,.0f}, p90 ${s.quantile(0.9):,.0f}, max ${s.max():,.0f}")
    if etrs:
        s = pd.Series(etrs)
        print(f"ETR:      median {s.median():.4f} ({s.median()*100:.2f}%), p10 {s.quantile(0.1):.4f}, p90 {s.quantile(0.9):.4f}")

    out = args.out or str(config.OUTPUT_DIR / "parcels_with_tax.geojson")
    with open(out, "w") as f:
        json.dump({"type": "FeatureCollection", "features": out_features}, f)
    print(f"Wrote {out} ({len(out_features):,} features)")

    # Per-class ETR medians for the "ETR vs same-class median" frontend mode.
    # Tiny lookup; ships in /public/data/.
    cls_df = pd.DataFrame(
        [f["properties"] for f in out_features if f["properties"].get("etr")]
    )
    if not cls_df.empty:
        meds = (
            cls_df.dropna(subset=["tax_class"])
            .groupby("tax_class")["etr"]
            .median()
            .round(5)
            .to_dict()
        )
        config.PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
        (config.PUBLIC_DATA_DIR / "nyc-property-tax-class-medians.json").write_text(
            json.dumps({
                "tax_year": getattr(config, "TAX_RATES_FISCAL_YEAR", None),
                "class_medians": meds,
            }, indent=2)
        )
        print(f"Wrote class medians: {meds}")


if __name__ == "__main__":
    main()
