# NYC Property Tax Map: Data Source Summary

## 1. Tax Class / Building Designation Data

Available and clean.

- **PVAD (Property Valuation and Assessment Data)** — NYC Open Data. One row per BBL with tax class, building class, assessed value, DOF market value, exemptions.
- **NOPV (Notice of Property Value)** — annual, similar fields.
- **PLUTO** — Dept. of City Planning. Merges DOF tax/assessment fields with land use, year built, units, sqft, and geometry. This is what you join to a map.

Class 2 sub-designations (2a, 2b, 2c, residual) matter because assessment caps differ. Sometimes need to derive from building class + unit count.

## 2. Per-Unit Market Value

No official public dataset. Approximate options:

**Sale-based**
- DOF Annualized Rolling Sales: every arm's-length sale by BBL.
- Works for 1–3 family and condos.
- Useless for co-ops (transfers happen via stock, not ACRIS). Co-op unit values require StreetEasy/PropertyShark/UrbanDigs or RPIE (not published at unit level).

**Model-based**
- Zillow ZHVI / Redfin: neighborhood-level medians, free, monthly. Good for nabe-resolution choropleth, not building-level.
- Zestimate: per-address but no bulk API; scraping unreliable and against ToS.

**Academic / advocacy**
- Furman Center: effective tax rate maps in *State of NYC's Housing and Neighborhoods*.
- NYU Stern Moses Center: similar work.
- NYC Advisory Commission on Property Tax Reform (2021 final report): closest precedent. I am uncertain whether parcel-level estimates were released publicly. Worth checking before replicating.

## 3. Recommended Approach by Building Type

| Type | Method |
|---|---|
| 1–3 family, condos | Hedonic regression on rolling sales + PLUTO features |
| Rental buildings | Capitalize NOI from RPIE (FOIL for unit-level), or use DOF's income-capitalized market value |
| Co-ops | DOF market value (known low) or StreetEasy-derived comps |

Effective tax rate = tax bill / estimated market value. Map the ratio.

## 4. Framing Flag

Meaningful denominator is market value. Meaningful comparison is ETR against a uniform benchmark (citywide median, or statutory rate applied uniformly).

Class 1 assessment growth cap means two identical brownstones can have very different ETRs based on owner tenure. Furman has shown long-tenured Class 1 owners in Park Slope / Bed-Stuy with ETRs under 0.3%, while new Class 1 buyers in southeast Queens or Staten Island pay 1%+. That's the headline and the map would visualize it well.
